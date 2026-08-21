"""The six metrics views, against a hand-written event log -- no daemon, no
sleeps. A real `Store` (DEC-011's schema) backs the fixture; `metrics.py`
queries it through a second connection, exactly like the CLI queries the
daemon's live database.

Timestamps are inserted directly rather than through `Store.emit()` (which
always stamps `time.time()`), because view 6 needs an exact, known gap
between two rows. This goes through the same INSERT `emit()` uses, on the
same connection, so it is still exercising the real schema and the real
append-only triggers -- just with `ts` under the test's control.
"""
import json
import sqlite3
import tempfile
import time
from pathlib import Path

from pipeline.cli import metrics
from pipeline.daemon.store import Store

BASE = 1_700_000_000.0


def _log() -> Store:
    tmp = Path(tempfile.mkdtemp())
    return Store(tmp / "events.db")


def _at(s: Store, ts: float, kind: str, ticket=None, stage=None, session=None,
       project="/proj", **data) -> None:
    s.conn.execute(
        "INSERT INTO events(ts,project,ticket,stage,session,kind,data)"
        " VALUES(?,?,?,?,?,?,?)",
        (ts, project, ticket, stage, session, kind, json.dumps(data, default=str)))


def build_log() -> Store:
    s = _log()

    # TICKET-100: escalated in `planning` -- 2 runs of `planning`, 1
    # escalation -> escalation_rate("planning") == 0.5
    _at(s, BASE + 0, "stage_end", ticket="TICKET-100", stage="planning",
       result="ok", next_stage="plan-validation", exit_code=0)
    _at(s, BASE + 1, "gate", ticket="TICKET-100", stage="plan-validation",
       verdict="fail", findings=["section `## Rollback` missing or empty"])
    _at(s, BASE + 2, "stage_end", ticket="TICKET-100", stage="planning",
       result="needs-input", next_stage="needs-input", exit_code=0)
    _at(s, BASE + 3, "escalated", ticket="TICKET-100", stage="planning",
       reason="lease expired twice")

    # TICKET-200: reaches `done` through `merging`, 2 review loops, and a
    # `result` event (authoritative, non-estimated cost) on every headless
    # stage it ran -- $1.80 across 3 `implementing` runs, $0.45 across 3
    # `review` runs, $2.25 total, the only merged ticket in this log.
    def leg(ts, ticket, stage, cost, frm, to, result_, loops):
        _at(s, ts, "result", ticket=ticket, stage=stage, total_cost_usd=cost)
        _at(s, ts + 0.5, "transition", ticket=ticket, stage=stage,
           **{"from": frm, "to": to, "result": result_, "counters": {"review_loops": loops}})

    leg(BASE + 10, "TICKET-200", "implementing", 0.50, "implementing", "review", "ok", 0)
    leg(BASE + 12, "TICKET-200", "review",        0.10, "review", "implementing", "fail", 1)
    leg(BASE + 20, "TICKET-200", "implementing", 0.60, "implementing", "review", "ok", 1)
    leg(BASE + 22, "TICKET-200", "review",        0.15, "review", "implementing", "fail", 2)
    leg(BASE + 30, "TICKET-200", "implementing", 0.70, "implementing", "review", "ok", 2)
    leg(BASE + 32, "TICKET-200", "review",        0.20, "review", "verifying", "ok", 2)
    _at(s, BASE + 34, "transition", ticket="TICKET-200", stage="verifying",
       **{"from": "verifying", "to": "merging", "result": "ok", "counters": {"review_loops": 2}})
    _at(s, BASE + 35, "transition", ticket="TICKET-200", stage="merging",
       **{"from": "merging", "to": "done", "result": "ok", "counters": {"review_loops": 2}})

    # TICKET-300: a second gate FAIL, one finding shared with TICKET-100's --
    # proves view 4 sums counts across tickets rather than per-ticket.
    _at(s, BASE + 40, "gate", ticket="TICKET-300", stage="plan-validation",
       verdict="fail",
       findings=["section `## Rollback` missing or empty", "files_declared is empty"])

    # TICKET-400: parked in `awaiting-approval` for exactly 2520s (42m),
    # closed by the next transition on the same ticket.
    _at(s, BASE + 5000, "transition", ticket="TICKET-400", stage="planning",
       **{"from": "planning", "to": "awaiting-approval", "result": "ok", "counters": {}})
    _at(s, BASE + 5000 + 2520, "transition", ticket="TICKET-400", stage="awaiting-approval",
       **{"from": "awaiting-approval", "to": "revalidating", "result": "ok", "counters": {}})

    return s


def test_metrics_views_over_a_canned_event_log():
    s = build_log()
    db_path = s.path
    s.close()

    conn = metrics.connect(db_path)
    try:
        # view 1: escalation rate per stage -- the headline
        assert metrics.escalation_rate(conn, "planning") == 0.5

        # view 2: review-loop distribution over tickets reaching a terminal
        # stage. Only TICKET-200 shows up: TICKET-100's escalation is a bare
        # `escalated` event, never a `transition` whose `to` is `escalated`,
        # so it correctly does not appear here (or inflate this view).
        dist = metrics.review_loop_distribution(conn)
        assert dist == [{"review_loops": 2, "tickets": 1}], dist

        # view 3: cost per MERGED ticket, by stage -- only TICKET-200 reached
        # `done` through `merging`; its `result` events sum to exactly $2.25
        assert metrics.merged_tickets(conn) == {("/proj", "TICKET-200")}
        cost, estimated = metrics.cost_per_merged(conn)
        assert abs(cost - 2.25) < 1e-9
        assert estimated is False   # every leg was a `result` event, none a `usage` estimate
        by_stage = {r["stage"]: r for r in metrics.cost_by_stage(conn)}
        assert by_stage["implementing"]["p50_cost"] == 0.60       # median(.50,.60,.70)
        assert by_stage["implementing"]["estimated"] is False     # `result`, not `usage`
        assert by_stage["review"]["p50_cost"] == 0.15              # median(.10,.15,.20)

        # view 4: gate failure reasons, grouped and counted across tickets
        reasons = {r["finding"]: r["n"] for r in metrics.gate_failure_reasons(conn)}
        assert reasons["section `## Rollback` missing or empty"] == 2
        assert reasons["files_declared is empty"] == 1

        # view 5: guard blocks -- structurally absent today (nothing in the
        # supervisor emits `hook_response` into the store yet -- `rec["sink"]`
        # is a no-op), so this must say so truthfully rather than render an
        # empty, falsely-clean table.
        assert metrics.guard_blocks(conn) is None

        # view 6: time parked in a human gate -- exact duration
        spans = metrics.parked_spans(conn)
        assert len(spans) == 1
        assert spans[0] == {"project": "/proj", "ticket": "TICKET-400",
                            "gate": "awaiting-approval", "parked_s": 2520.0}

        # and the assembled view + text renderer both run end to end
        data = metrics.collect(conn)
        text = metrics.render(data)
        assert "planning" in text
        assert "no data -- no stream events in this log at all" in text
        assert "$2.25" in text
    finally:
        conn.close()


def test_parse_since_relative_and_iso():
    now = time.time()
    assert abs(metrics.parse_since("24h") - (now - 86400)) < 5
    assert abs(metrics.parse_since("7d") - (now - 7 * 86400)) < 5
    assert metrics.parse_since("2026-01-01") > 0


def test_estimate_cost_flags_pty_tokens_as_an_estimate():
    # a model outside the price table falls back to the sonnet-tier default
    # rather than raising or silently costing $0
    cost = metrics.estimate_cost("some-future-model",
                                 {"input_tokens": 1_000_000, "output_tokens": 0})
    assert cost == metrics.DEFAULT_PRICE["input"]
    known = metrics.estimate_cost("claude-sonnet-4-5",
                                  {"input_tokens": 1_000_000, "output_tokens": 0})
    assert known == metrics.PRICE_PER_MTOK["claude-sonnet-4-5"]["input"]


def test_connect_refuses_a_missing_db_instead_of_creating_a_stray_file():
    """`sqlite3.connect` on a missing path silently creates an empty,
    schema-less, default-permission file -- and if that happens before the
    daemon's own `Store` ever opens the path, `Store` never chmods it to
    0600 (it only does so when it is the one to create the file). So this
    must refuse up front, not fall through to `sqlite3.connect`."""
    from pipeline.core import PipelineError
    missing = Path(tempfile.mkdtemp()) / "no-such" / "events.db"
    try:
        metrics.connect(missing)
        assert False, "must refuse rather than silently create the path"
    except PipelineError as e:
        assert "no event log" in str(e)
    assert not missing.exists(), "must not have created the file it refused to open"


def test_merged_and_cost_do_not_cross_project_on_a_shared_ticket_id():
    """Ticket ids are `TICKET-\\d{1,6}`, numbered per project -- `TICKET-001`
    exists independently in every project. A metrics run with no `--project`
    filter must key every ticket-shaped query on (project, ticket), or one
    project's merged `TICKET-001` would make an unrelated project's
    unmerged `TICKET-001` count as merged too."""
    s = _log()
    # /proj-a: TICKET-001 merges, cost $1.00
    _at(s, BASE, "result", ticket="TICKET-001", stage="implementing",
       project="/proj-a", total_cost_usd=1.00)
    _at(s, BASE + 1, "transition", ticket="TICKET-001", stage="merging", project="/proj-a",
       **{"from": "merging", "to": "done", "result": "ok", "counters": {}})
    # /proj-b: TICKET-001 never merges (still `implementing`), cost $99 -- must
    # never be counted as merged, and its cost must never leak into /proj-a's
    _at(s, BASE, "result", ticket="TICKET-001", stage="implementing",
       project="/proj-b", total_cost_usd=99.00)

    db_path = s.path
    s.close()
    conn = metrics.connect(db_path)
    try:
        assert metrics.merged_tickets(conn) == {("/proj-a", "TICKET-001")}
        cost, estimated = metrics.cost_per_merged(conn)
        assert abs(cost - 1.00) < 1e-9, cost   # not $100 or $50 -- /proj-b never merged
        assert estimated is False
    finally:
        conn.close()


def test_parked_spans_do_not_close_across_projects_on_a_shared_ticket_id():
    """Same collision, applied to view 6: project A's `TICKET-001` enters a
    gate and never leaves; project B's unrelated `TICKET-001` later
    transitions. That must not "close" project A's still-open span."""
    s = _log()
    _at(s, BASE, "transition", ticket="TICKET-001", stage="planning", project="/proj-a",
       **{"from": "planning", "to": "awaiting-approval", "result": "ok", "counters": {}})
    _at(s, BASE + 10, "transition", ticket="TICKET-001", stage="implementing", project="/proj-b",
       **{"from": "implementing", "to": "review", "result": "ok", "counters": {}})
    db_path = s.path
    s.close()
    conn = metrics.connect(db_path)
    try:
        assert metrics.parked_spans(conn) == [], \
            "/proj-a's open gate must not be fabricated-closed by /proj-b's event"
    finally:
        conn.close()


def test_a_merged_ticket_with_any_pty_stage_flags_the_blended_cost_as_an_estimate():
    """`cost_per_merged` blends `result` (real) and `usage` (PTY-estimated)
    cost into one number -- the moment any component is an estimate, the
    number AS A WHOLE must render with `~`, both in text and in `--json`
    (`collect()["cost"]["per_merged_estimated"]`), never silently presented
    as a real measurement."""
    s = _log()
    _at(s, BASE, "result", ticket="TICKET-900", stage="implementing", total_cost_usd=0.50)
    _at(s, BASE + 1, "usage", ticket="TICKET-900", stage="planning",
       model="claude-sonnet-4-5", input_tokens=1_000_000, output_tokens=0)
    _at(s, BASE + 2, "transition", ticket="TICKET-900", stage="merging",
       **{"from": "merging", "to": "done", "result": "ok", "counters": {}})
    db_path = s.path
    s.close()
    conn = metrics.connect(db_path)
    try:
        cost, estimated = metrics.cost_per_merged(conn)
        assert estimated is True
        assert abs(cost - (0.50 + metrics.PRICE_PER_MTOK["claude-sonnet-4-5"]["input"])) < 1e-9

        data = metrics.collect(conn)
        assert data["cost"]["per_merged_estimated"] is True
        text = metrics.render(data)
        assert f"cost/merged: ~${cost:.2f}" in text, text
    finally:
        conn.close()


def test_a_ticket_that_never_leaves_a_gate_is_not_counted_as_parked():
    """An open span (entered a gate, no further transition yet) must not be
    reported with a fabricated duration -- it is simply absent from
    `parked_spans()` until it closes."""
    s = _log()
    _at(s, BASE, "transition", ticket="TICKET-500", stage="planning",
       **{"from": "planning", "to": "needs-input", "result": "ok", "counters": {}})
    db_path = s.path
    s.close()
    conn = metrics.connect(db_path)
    try:
        assert metrics.parked_spans(conn) == []
    finally:
        conn.close()
