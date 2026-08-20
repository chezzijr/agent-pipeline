"""`pipeline` -- the human side: scaffold, file, inspect and unblock tickets."""
import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.core.config import CONFIG_TEMPLATE, TICKET_TEMPLATE
from pipeline.core.gate import gate
from pipeline.core.machine import HUMAN_GATES, KNOWN_STAGES, TERMINAL
from pipeline.core.ticket import Ticket, all_tickets, now, tickets_dir
from pipeline.core.worktree import worktree
from pipeline.daemon.supervisor import run

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
    t.stage = "implementing"
    t.extra["approved_by"] = args.by or os.environ.get("USER", "unknown")
    t.extra["approved_at"] = now().isoformat()
    t.append("human", "approval", f"**approved by {t.extra['approved_by']}**",
             by=t.extra["approved_by"])
    t.save()
    print(f"{args.id}: -> implementing")


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=".", help="target project dir")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.add_argument("dir", nargs="?", default="."); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("new"); p.add_argument("title"); p.add_argument("--class", dest="cls", default="bugfix"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("gate"); p.add_argument("id"); p.set_defaults(fn=cmd_gate)
    p = sub.add_parser("approve"); p.add_argument("id"); p.add_argument("--by"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("answer"); p.add_argument("id"); p.add_argument("text"); p.set_defaults(fn=cmd_answer)
    p = sub.add_parser("resume"); p.add_argument("id"); p.add_argument("--stage", required=True); p.add_argument("--reset", nargs="*"); p.set_defaults(fn=cmd_resume)
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
