"""`pipeline` -- the human side: scaffold, file, inspect and unblock tickets."""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.core.config import CONFIG_TEMPLATE, TICKET_TEMPLATE
from pipeline.core.gate import gate
from pipeline.core.machine import HUMAN_GATES, KNOWN_STAGES, TERMINAL
from pipeline.core.ticket import Ticket, all_tickets, now, tickets_dir
from pipeline.core.worktree import worktree
from pipeline.daemon.supervisor import run
from pipeline.stream import StreamReader

STALE_HOURS = 4  # overlap ordering is silent; surface anything sitting still


def die(msg: str) -> None:
    """The one place a bad input ends the process. The library raises
    `PipelineError` instead, so one broken project cannot kill the loop."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def cmd_init(args) -> None:
    project = Path(args.dir).resolve()
    tickets_dir(project).mkdir(parents=True, exist_ok=True)
    (project / ".project" / "decisions").mkdir(exist_ok=True)
    cfg = project / ".project" / "pipeline.toml"
    if not cfg.exists():
        cfg.write_text(CONFIG_TEMPLATE.read_text())
    print(f"initialised {project / '.project'} -- edit {cfg} for this project's commands")


def cmd_new(args) -> None:
    project = Path(args.project).resolve()
    d = tickets_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    n = 1 + max((int(m.group(1)) for p in d.glob("TICKET-*.md")
                 if (m := re.match(r"TICKET-(\d+)", p.stem))), default=0)
    tid = f"TICKET-{n:03d}"
    tpl = TICKET_TEMPLATE.read_text()
    (d / f"{tid}.md").write_text(
        tpl.replace("{{id}}", tid).replace("{{class}}", args.cls)
           .replace("{{branch}}", f"ticket/{n:03d}").replace("{{title}}", args.title))
    print(d / f"{tid}.md")


def cmd_gate(args) -> None:
    project = Path(args.project).resolve()
    wt = worktree(project, Ticket.find(project, args.id).frontmatter())
    # the ticket's test lives on its branch; running in the main checkout would
    # report a bogus "test file does not exist" straight into the thread
    ok, failures = gate(project, args.id, wt if wt.is_dir() else None)
    for f in failures:
        print(f"FAIL: {f}")
    print("gate: PASS" if ok else "gate: FAIL")
    sys.exit(0 if ok else 1)


def cmd_approve(args) -> None:
    project = Path(args.project).resolve()
    t = Ticket.find(project, args.id)
    if t.stage != "awaiting-approval":
        die(f"{args.id} is in `{t.stage}`, not `awaiting-approval`")
    # not `implementing`: the Tier A facts behind this plan were recorded
    # before the ticket sat here, and base has moved since. `revalidating`
    # rebases and re-gates. Approval returns now rather than waiting on it.
    t.stage = "revalidating"
    t.extra["approved_by"] = args.by or os.environ.get("USER", "unknown")
    t.extra["approved_at"] = now().isoformat()
    t.append("human", "approval", f"**approved by {t.extra['approved_by']}**",
             by=t.extra["approved_by"])
    t.save()
    print(f"{args.id}: -> revalidating")


def cmd_reject(args) -> None:
    """A human rejecting a plan they simply do not want -- distinct from
    plan-validation's mechanical/judgment rejection, so it charges its own
    counter (`plan_rejections`) instead of `plan_validation_attempts`. At the
    bound this refuses rather than escalating: escalation means "a human must
    look", and one already is, holding the keyboard. The counter is lifetime,
    not "in a row" -- like every other counter here it only clears via an
    explicit `--reset`, which is why the escape hatch below names it."""
    project = Path(args.project).resolve()
    if not args.reason.strip():
        die("a rejection needs a reason -- that's the whole point")
    t = Ticket.find(project, args.id)
    if t.stage != "awaiting-approval":
        die(f"{args.id} is in `{t.stage}`, not `awaiting-approval`")
    if t.counters.get("plan_rejections", 0) >= 2:
        die(f"{args.id}: 3rd rejection: the ticket is the problem, not the plan.\n"
            f"Try `pipeline resume {args.id} --stage triage --reset plan_rejections`, "
            f"or close the ticket.")
    t.counters["plan_rejections"] = t.counters.get("plan_rejections", 0) + 1
    t.stage = "planning"
    t.append("human", "rejection", args.reason)
    t.save()
    print(f"{args.id}: -> planning")


def cmd_answer(args) -> None:
    project = Path(args.project).resolve()
    t = Ticket.find(project, args.id)
    if t.stage != "needs-input":
        die(f"{args.id} is in `{t.stage}`, not `needs-input`")
    t.stage = "planning"
    t.append("human", "answer",
             f"**answer from {os.environ.get('USER', 'human')}**\n\n{args.text}")
    t.save()
    print(f"{args.id}: -> planning")


def cmd_resume(args) -> None:
    project = Path(args.project).resolve()
    if args.stage not in KNOWN_STAGES:
        die(f"`{args.stage}` is not a stage: {', '.join(sorted(KNOWN_STAGES))}")
    t = Ticket.find(project, args.id)
    t.stage = args.stage
    for key in args.reset or []:
        t.counters[key] = 0
    t.release_lease()
    t.append("human", "note",
             f"**resumed** by human -> `{args.stage}`, reset {args.reset or []}")
    t.save()
    print(f"{args.id}: -> {args.stage}")


def cmd_status(args) -> None:
    for p in all_tickets(Path(args.project).resolve()):
        t = Ticket.load(p)
        stale = ""
        if (t.stage not in TERMINAL | HUMAN_GATES
                and not t.lease_active()
                and now() - datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
                > timedelta(hours=STALE_HOURS)):
            stale = f"STALE>{STALE_HOURS}h"  # probably waiting behind an overlap
        lease = "LEASED" if t.lease_active() else stale
        print(f"{t.id:<12} {t.stage:<17} {t.klass:<9} {t.counters} {lease}")
        last = t.extra.get("last_session")
        if last and args.verbose:
            print(f"{'':<12} last: {last['stage']} log={last['log']} "
                  f"replay=`claude --resume {last['id']}`")


def _one(s, n: int = 160) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "..."


def render(ev: dict) -> str:
    """One parsed event -> one screenful-safe line. Total: every branch returns
    a string and none of them can raise on a shape the parser let through."""
    k = ev["kind"]
    if k == "init":
        return (f"-- init {ev['model']} mode={ev['permission_mode']} "
                f"tools={len(ev['tools'])}")
    if k == "assistant":
        out = [f"   ~ {_one(ev['thinking'])}"] if ev["thinking"] else []
        if ev["text"]:
            out.append(ev["text"])
        out += [f"   -> {t['name']}({_one(json.dumps(t['input'], default=str))})"
                for t in ev["tools"]]
        return "\n".join(out)
    if k == "tool_result":
        return f"   <- {'ERR' if ev['is_error'] else 'ok'} {_one(ev['text'])}"
    if k == "hook_started":
        return f"   [hook {ev['hook']} {ev['tool'] or ''}]"
    if k == "hook_response":
        # the guard biting, live -- the one event worth watching for
        return (f"   [hook {ev['hook']} exit={ev['exit_code']} {ev['outcome'] or ''}] "
                f"{_one(ev['stderr'])}")
    if k == "rate_limit":
        return f"!! rate limit {ev.get('status')} resets {ev.get('resets_at')}"
    if k == "result":
        ms = ev["duration_ms"] if isinstance(ev["duration_ms"], (int, float)) else 0
        return (f"== {ev['subtype']} ${ev['total_cost_usd']:.4f} "
                f"{ev['num_turns']} turns {ms / 1000:.1f}s")
    return f"?? {ev.get('raw_type') or _one(ev.get('raw') or ev.get('error') or '')}"


def cmd_logs(args) -> None:
    """Pretty-print a stage's stream-json log. `-f` follows it and returns when
    the stage's `result` event lands. Today the log file is the stream: the
    child writes it, this reads it. When the daemon (TICKET-011) owns the
    child's fd it feeds the same `StreamReader` from the pipe instead."""
    project = Path(args.project).resolve()
    logs = sorted((project / ".project" / "logs").glob(f"{args.id}-*.log"),
                  key=lambda p: p.stat().st_mtime)
    if not logs:
        die(f"no log for {args.id} under .project/logs")
    log = logs[-1]
    print(f"-- {log.relative_to(project)}")
    reader = StreamReader()
    try:
        with log.open("rb") as fh:
            while True:
                chunk = fh.read(1 << 16)
                if not chunk:
                    if not args.follow:
                        return
                    time.sleep(0.4)
                    continue
                for ev in reader.feed(chunk):
                    line = render(ev)
                    if line:
                        print(line, flush=True)
                    if ev["kind"] == "result":
                        return
    except KeyboardInterrupt:
        return


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=".", help="target project dir")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.add_argument("dir", nargs="?", default="."); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("new"); p.add_argument("title"); p.add_argument("--class", dest="cls", default="bugfix"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("gate"); p.add_argument("id"); p.set_defaults(fn=cmd_gate)
    p = sub.add_parser("approve"); p.add_argument("id"); p.add_argument("--by"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("reject"); p.add_argument("id"); p.add_argument("reason"); p.set_defaults(fn=cmd_reject)
    p = sub.add_parser("answer"); p.add_argument("id"); p.add_argument("text"); p.set_defaults(fn=cmd_answer)
    p = sub.add_parser("resume"); p.add_argument("id"); p.add_argument("--stage", required=True); p.add_argument("--reset", nargs="*"); p.set_defaults(fn=cmd_resume)
    p = sub.add_parser("logs"); p.add_argument("id"); p.add_argument("-f", "--follow", action="store_true"); p.set_defaults(fn=cmd_logs)
    p = sub.add_parser("status"); p.add_argument("-v", "--verbose", action="store_true"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("run"); p.add_argument("--once", action="store_true"); p.add_argument("--interval", type=int, default=10); p.add_argument("--harness", default="claude-code"); p.add_argument("-j", "--max-parallel", type=int, default=3); p.set_defaults(fn=None)

    args = ap.parse_args()
    try:
        if args.cmd == "run":
            run(Path(args.project).resolve(), args.once, args.interval,
                args.harness, args.max_parallel)
        else:
            args.fn(args)
    except PipelineError as e:
        die(str(e))
