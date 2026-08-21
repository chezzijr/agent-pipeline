"""Six views over the append-only event log DEC-011 froze.

No ORM, no plotting: six SQL strings and a `render()`. SQL does the grouping
and filtering; `statistics.median` does the percentiles SQLite has no
function for short of an extension (three lines of Python beats a
correlated-subquery puzzle).

Cost is per MERGED ticket, not per token -- a cheaper model that bounces
twice through review is the more expensive system, which is the entire
reason view 3 filters on tickets that actually reached `done` through
`merging` rather than summing every attempt.

Two cost sources, one of them a measurement and the other an estimate. A
headless (`claude -p`) stage's `result` event carries the harness's own
`total_cost_usd` -- authoritative. A PTY stage (TICKET-013) never gets a
`result` event; its `usage` event carries only token counts, so its cost is
tokens x a price table, computed here at query time and rendered with a `~`
prefix. Presenting an estimate as a measurement is the one thing that would
make these numbers actively misleading.
"""
import json
import re
import sqlite3
import statistics
import time
from datetime import datetime
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.core.machine import HUMAN_GATES, TERMINAL
from pipeline.daemon.store import db_path

# -- price table -----------------------------------------------------------
# $ per MILLION tokens. Config, not a query literal: a wrong number here is a
# re-render (nothing in the event log is derived from it), which is the whole
# point of storing tokens and computing cost at query time instead of at
# emit time. Update by editing this dict -- keys are `message.model` from a
# session transcript / the `model` field on a `usage` event; `input` also
# covers cache-read and cache-creation tokens, which is an overcount (both
# are cheaper than a fresh input token) but a defensible one until someone
# needs the extra precision.
PRICE_PER_MTOK = {
    "claude-opus-4-5":   {"input": 5.00,  "output": 25.00},
    "claude-sonnet-4-5": {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":  {"input": 1.00,  "output": 5.00},
}
DEFAULT_PRICE = {"input": 3.00, "output": 15.00}  # unrecognised model: sonnet-tier guess


def estimate_cost(model: str | None, usage: dict) -> float:
    """A `usage` event's data -> a `~`-flagged dollar estimate."""
    price = PRICE_PER_MTOK.get(model, DEFAULT_PRICE)
    inp = ((usage.get("input_tokens") or 0)
           + (usage.get("cache_read") or usage.get("cache_read_input_tokens") or 0)
           + (usage.get("cache_creation") or usage.get("cache_creation_input_tokens") or 0))
    out = usage.get("output_tokens") or 0
    return inp / 1e6 * price["input"] + out / 1e6 * price["output"]


# -- since/project parsing --------------------------------------------------
_REL = re.compile(r"^(\d+)([hdw])$")
_UNIT_S = {"h": 3600, "d": 86400, "w": 604800}


def parse_since(s: str) -> float:
    """`7d`, `24h`, `2w` -- else an ISO date, and a bad one raises
    `ValueError`, which `main.py` turns into `die()`."""
    m = _REL.match(s.strip())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return time.time() - n * _UNIT_S[unit]
    return datetime.fromisoformat(s).timestamp()


def connect(db: Path | str | None = None) -> sqlite3.Connection:
    """A second connection onto the daemon's WAL database -- readers never
    block `emit()`, which is why WAL is the mode in the first place.

    `sqlite3.connect` silently creates a missing path: a stray 0-byte,
    schema-less, default-permission file. That is not merely an ugly
    `OperationalError: no such table: events` on the next query -- if it
    happens before the daemon's own `Store` ever opens this path, `Store`
    sees `new = not self.path.exists()` as False and never runs its 0600
    chmod (`daemon/store.py`), permanently leaving the event log -- which
    holds every project's gate findings -- at the OS default permissions.
    So: refuse up front instead of ever calling `sqlite3.connect` on a path
    that doesn't exist yet.
    """
    path = Path(db) if db else db_path()
    if not path.is_file():
        raise PipelineError(f"no event log at {path} -- has `pipelined` ever run? "
                            f"(or pass --db)")
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA busy_timeout=5000")  # match store.py: a checkpoint can hold X-lock
    conn.row_factory = sqlite3.Row
    return conn


# `ev` is the common prefix every view starts from: the time/project window,
# nothing else. Re-stated per query rather than shared across calls -- a CTE
# does not outlive its statement.
_EV = "WITH ev AS (SELECT * FROM events WHERE ts >= :since AND (:project IS NULL OR project = :project))\n"
# TERMINAL/HUMAN_GATES are fixed Python constants (machine.py), not values
# from a ticket file, so inlining them as a literal SQL list is safe -- the
# hostile-input rule (CLAUDE.md invariant 5) is about `events` row content,
# which every query below still only ever touches through a bound parameter.
_TERMINAL_SQL = ",".join(f"'{s}'" for s in sorted(TERMINAL))
_GATES_SQL = ",".join(f"'{s}'" for s in sorted(HUMAN_GATES))


def _rows(conn: sqlite3.Connection, sql: str, since: float, project: str | None) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, {"since": since, "project": project})]


# -- view 1: escalation rate per stage --------------------------------------
# The headline: if plan-validation escalates constantly, the planning prompt
# is miscalibrated. `stale_regate` and `plan_rejections` never emit a `kind`
# of `escalated` -- `stale_regate` routes back to `planning` via a plain
# `transition` event unless it exhausts its own bound, and `plan_rejections`
# is a human's CLI call that never reaches the dispatcher's `escalate()` at
# all -- so neither counter inflates this view. It counts exactly what
# DEC-011 names: kind='escalated'.
def escalation_rates(conn: sqlite3.Connection, since: float = 0.0,
                     project: str | None = None) -> list[dict]:
    sql = _EV + """
    SELECT stage,
           COUNT(*) FILTER (WHERE kind='stage_end') AS runs,
           COUNT(*) FILTER (WHERE kind='escalated') AS escalated
    FROM ev
    WHERE stage IS NOT NULL
    GROUP BY stage
    """
    rows = _rows(conn, sql, since, project)
    for r in rows:
        r["rate"] = (r["escalated"] / r["runs"]) if r["runs"] else None
    return rows


def escalation_rate(conn: sqlite3.Connection, stage: str, since: float = 0.0,
                    project: str | None = None) -> float | None:
    return next((r["rate"] for r in escalation_rates(conn, since, project)
                 if r["stage"] == stage), None)


# -- view 2: review-loop distribution ----------------------------------------
# How many review loops a ticket burned before it stopped moving, for every
# ticket that stopped moving via a `transition` event landing in TERMINAL.
# Terminal stages are absorbing, so a ticket has at most one such row -- one
# row in, one ticket counted.
#
# This underclaims `escalated` specifically: `supervisor.escalate()` (bad
# frontmatter, a dead lease, a failed worktree/rebase, a tampering agent, a
# missing `.result`) emits only a bare `kind='escalated'` event with no
# `counters` snapshot, never a `transition` row -- there is nothing here to
# read a review-loop count off of for that path. Only the state machine's own
# bound-exceeded route (`transition()`'s `charge()`, e.g. `review_loops`
# hitting its cap) produces a `transition` to `escalated`, and only that
# route is counted below. `render()`'s label says so explicitly.
def review_loop_distribution(conn: sqlite3.Connection, since: float = 0.0,
                             project: str | None = None) -> list[dict]:
    sql = _EV + f"""
    SELECT CAST(json_extract(data,'$.counters.review_loops') AS INTEGER) AS review_loops,
           COUNT(*) AS tickets
    FROM ev
    WHERE kind='transition' AND json_extract(data,'$.to') IN ({_TERMINAL_SQL})
    GROUP BY review_loops
    ORDER BY review_loops
    """
    return _rows(conn, sql, since, project)


# -- view 3: cost per MERGED ticket, by stage --------------------------------
# Ticket IDs (`TICKET-\d{1,6}`, `pipeline/core/ticket.py`) are sequential per
# PROJECT, not globally -- `TICKET-001` exists independently in every
# project. Every identity used below is `(project, ticket)`, never a bare
# ticket id, or two unrelated tickets that happen to share a number would be
# conflated the moment `--project` is omitted (the documented "every
# project" mode).
def merged_tickets(conn: sqlite3.Connection, since: float = 0.0,
                   project: str | None = None) -> set[tuple[str, str]]:
    """A ticket counts as merged when it reached `done` THROUGH `merging` --
    the real outcome the state machine now has, not an approximation from
    every ticket that happened to end at `done`."""
    sql = _EV + """
    SELECT DISTINCT project, ticket FROM ev
    WHERE kind='transition' AND json_extract(data,'$.from')='merging'
      AND json_extract(data,'$.to')='done' AND ticket IS NOT NULL
    """
    return {(r["project"], r["ticket"]) for r in _rows(conn, sql, since, project)}


def _cost_events(conn: sqlite3.Connection, since: float, project: str | None):
    """(project, ticket, stage, cost_usd, estimated) for every `result`/
    `usage` event in the window, restricted to nothing yet -- callers filter
    to merged."""
    sql = _EV + "SELECT project, ticket, stage, kind, data FROM ev WHERE kind IN ('result','usage')"
    for r in _rows(conn, sql, since, project):
        d = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
        if r["kind"] == "result":
            yield r["project"], r["ticket"], r["stage"], float(d.get("total_cost_usd") or 0.0), False
        else:  # usage: a PTY stage, no result event, tokens x price table
            yield r["project"], r["ticket"], r["stage"], estimate_cost(d.get("model"), d), True


def cost_by_stage(conn: sqlite3.Connection, since: float = 0.0,
                  project: str | None = None) -> list[dict]:
    """Per-stage p50 cost, merged tickets only. Grouping in SQL would need a
    correlated-subquery for the median; pulling the (small) merged set into
    Python and calling `statistics.median` is three lines instead."""
    merged = merged_tickets(conn, since, project)
    if not merged:
        return []
    by_stage: dict[str, list[tuple[float, bool]]] = {}
    for proj, ticket, stage, cost, estimated in _cost_events(conn, since, project):
        if (proj, ticket) not in merged:
            continue
        by_stage.setdefault(stage, []).append((cost, estimated))
    out = []
    for stage, items in sorted(by_stage.items()):
        costs = [c for c, _ in items]
        out.append({"stage": stage, "n": len(items),
                     "p50_cost": statistics.median(costs),
                     "estimated": any(e for _, e in items)})
    return out


def cost_per_merged(conn: sqlite3.Connection, since: float = 0.0,
                    project: str | None = None) -> tuple[float, bool]:
    """(cost, estimated) -- total cost across every merged ticket, divided
    by how many merged, NOT total cost across every attempt. A cheaper model
    that bounces twice through review is the more expensive system; this is
    the number that says so.

    `estimated` is True the moment any of the underlying cost is a PTY
    `usage`-derived guess rather than a `result` event's authoritative
    `total_cost_usd` -- callers must flag the number with `~` rather than
    render a blend of measurement and estimate as if it were all measured.
    """
    merged = merged_tickets(conn, since, project)
    if not merged:
        return 0.0, False
    total, estimated = 0.0, False
    for proj, ticket, _stage, cost, est in _cost_events(conn, since, project):
        if (proj, ticket) in merged:
            total += cost
            estimated = estimated or est
    return total / len(merged), estimated


# -- view 4: gate failure reasons --------------------------------------------
# Raw counts, not bucketed near-duplicate prose -- at this volume the raw
# findings read fine, and de-duplicating similar-but-not-identical strings is
# a judgment call this view does not need to make.
def gate_failure_reasons(conn: sqlite3.Connection, since: float = 0.0,
                         project: str | None = None, top: int = 15) -> list[dict]:
    sql = _EV + """
    SELECT je.value AS finding, COUNT(*) AS n
    FROM ev, json_each(ev.data, '$.findings') je
    WHERE ev.kind='gate' AND UPPER(json_extract(ev.data,'$.verdict'))='FAIL'
    GROUP BY je.value
    ORDER BY n DESC, finding
    LIMIT :top
    """
    return [dict(r) for r in conn.execute(sql, {"since": since, "project": project, "top": top})]
    # UPPER(): supervisor.py's own `emit("gate", verdict=...)` call sites use
    # lowercase pass/fail, but gate.py's *thread* text and DEC-011's sketch
    # both write PASS/FAIL. Comparing case-insensitively is correct either
    # way and does not depend on that inconsistency ever getting fixed.


# -- view 5: guard blocks by rule --------------------------------------------
# Needs `hook_response` events in the log. Nothing in this codebase writes
# one today -- `rec["sink"]` (supervisor.py) is a no-op, so the stream parser
# TICKET-012 built is never wired to `store.emit()`. That is a structural
# absence, not "zero blocks happened", so this returns `None` -- a sentinel
# `render()`/`--json` both turn into a truthful "no data" rather than an
# empty table that reads as a clean guard.
def guard_blocks(conn: sqlite3.Connection, since: float = 0.0,
                 project: str | None = None) -> list[dict] | None:
    any_hook_events = conn.execute(
        "SELECT COUNT(*) FROM events WHERE kind='hook_response'").fetchone()[0]
    if not any_hook_events:
        return None
    sql = _EV + """
    SELECT json_extract(data,'$.hook') AS hook,
           json_extract(data,'$.stderr') AS stderr,
           COUNT(*) AS n
    FROM ev
    WHERE kind='hook_response'
      AND CAST(json_extract(data,'$.exit_code') AS INTEGER) != 0
    GROUP BY hook, stderr
    ORDER BY n DESC
    """
    return _rows(conn, sql, since, project)


# -- view 6: time parked in human gates --------------------------------------
# The cheapest view: it needs only `transition` events, which TICKET-011
# alone already emits. Entering a gate is a `transition` whose `to` lands in
# HUMAN_GATES; leaving it is simply the next `transition` on that ticket,
# whatever it is.
def parked_spans(conn: sqlite3.Connection, since: float = 0.0,
                 project: str | None = None) -> list[dict]:
    sql = _EV + """
    SELECT id, ts, project, ticket, json_extract(data,'$.to') AS to_stage
    FROM ev
    WHERE kind='transition' AND ticket IS NOT NULL
    ORDER BY project, ticket, id
    """
    # keyed by (project, ticket): a bare ticket id repeats across projects
    # (TICKET-001 in every one of them), and without the project half of the
    # key, project B's next transition could wrongly "close" project A's
    # still-open gate entry and fabricate a parked duration.
    pending: dict[tuple[str, str], tuple[str, float]] = {}
    spans: list[dict] = []
    for r in _rows(conn, sql, since, project):
        key = (r["project"], r["ticket"])
        if key in pending:
            gate, enter_ts = pending.pop(key)
            spans.append({"project": r["project"], "ticket": r["ticket"], "gate": gate,
                          "parked_s": r["ts"] - enter_ts})
        if r["to_stage"] in HUMAN_GATES:
            pending[key] = (r["to_stage"], r["ts"])
    return spans


def parked_summary(conn: sqlite3.Connection, since: float = 0.0,
                   project: str | None = None) -> dict | None:
    spans = parked_spans(conn, since, project)
    if not spans:
        return None
    secs = sorted(s["parked_s"] for s in spans)
    by_gate: dict[str, int] = {}
    for s in spans:
        by_gate[s["gate"]] = by_gate.get(s["gate"], 0) + 1
    # nearest-rank p90: no interpolation, fine at this scale, and the
    # question this view answers ("is the human gate the bottleneck") does
    # not turn on a fraction of a rank
    p90_idx = min(len(secs) - 1, int(len(secs) * 0.9))
    return {"n": len(secs), "p50": statistics.median(secs), "p90": secs[p90_idx],
            "by_gate": by_gate}


# -- everything, once -------------------------------------------------------
def collect(conn: sqlite3.Connection, since: float = 0.0,
           project: str | None = None) -> dict:
    per_merged, per_merged_estimated = cost_per_merged(conn, since, project)
    return {
        "escalation": escalation_rates(conn, since, project),
        "review_loop_distribution": review_loop_distribution(conn, since, project),
        "cost": {"per_merged": per_merged, "per_merged_estimated": per_merged_estimated,
                 "merged_tickets": len(merged_tickets(conn, since, project)),
                 "by_stage": cost_by_stage(conn, since, project)},
        "gate_failures": gate_failure_reasons(conn, since, project),
        "guard_blocks": guard_blocks(conn, since, project),
        "parked": {"spans": parked_spans(conn, since, project),
                   "summary": parked_summary(conn, since, project)},
    }


# -- rendering ---------------------------------------------------------------
def _fmt_money(x: float, estimated: bool) -> str:
    return f"{'~' if estimated else ''}${x:.2f}"


def _fmt_duration(s: float) -> str:
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{sec:02d}s"
    return f"{sec}s"


def render(data: dict) -> str:
    out: list[str] = []
    esc_by_stage = {r["stage"]: r for r in data["escalation"]}
    cost_by_stage_map = {r["stage"]: r for r in data["cost"]["by_stage"]}
    stages = sorted(set(esc_by_stage) | set(cost_by_stage_map))
    any_estimated = False

    out.append(f"{'stage':<17} {'runs':>4} {'escalated':>9} {'rate':>6} {'p50 cost':>10}")
    for stage in stages:
        e = esc_by_stage.get(stage, {"runs": 0, "escalated": 0, "rate": None})
        c = cost_by_stage_map.get(stage)
        rate = f"{e['rate']:.0%}" if e["rate"] is not None else "-"
        if c:
            cost = _fmt_money(c["p50_cost"], c["estimated"])
            any_estimated = any_estimated or c["estimated"]
        else:
            cost = "-"
        out.append(f"{stage:<17} {e['runs']:>4} {e['escalated']:>9} {rate:>6} {cost:>10}")

    out.append("")
    dist = data["review_loop_distribution"]
    if dist:
        hist = ", ".join(f"{d['review_loops']}x{d['tickets']}" for d in dist)
        # NOT every escalated ticket: `escalate()`'s direct calls (bad
        # frontmatter, dead lease, failed rebase, tampering, no .result)
        # carry no counters snapshot and never appear here -- only a
        # `transition` that landed on `escalated` does.
        out.append(f"review loops (tickets reaching done/rejected, or escalated "
                  f"via a bound): {hist}")
    else:
        out.append("review loops: no data -- needs a transition into a terminal stage")

    cost = data["cost"]
    any_estimated = any_estimated or cost["per_merged_estimated"]
    out.append(f"merged: {cost['merged_tickets']} · "
              f"cost/merged: {_fmt_money(cost['per_merged'], cost['per_merged_estimated'])}")

    parked = data["parked"]["summary"]
    if parked:
        gates = ", ".join(f"{g} {n}" for g, n in sorted(parked["by_gate"].items()))
        out.append(f"parked in gates: p50 {_fmt_duration(parked['p50'])} "
                  f"· p90 {_fmt_duration(parked['p90'])} ({gates})")
    else:
        out.append("parked in gates: no data -- needs a transition out of a human gate")

    out.append("")
    out.append("gate failures:")
    if data["gate_failures"]:
        for f in data["gate_failures"]:
            out.append(f"  {f['n']:>3}  {f['finding']}")
    else:
        out.append("  no FAIL gate events in this window")

    out.append("guard blocks:")
    gb = data["guard_blocks"]
    if gb is None:
        out.append("  no data -- needs stream events (nothing emits `hook_response` "
                  "into the event log yet)")
    elif not gb:
        out.append("  none in this window")
    else:
        for r in gb:
            out.append(f"  {r['n']:>3}  {r['hook']}: {r['stderr']}")

    if any_estimated:
        out.append("")
        out.append("~ estimated from token counts (interactive/PTY stages emit no cost)")
    return "\n".join(out)
