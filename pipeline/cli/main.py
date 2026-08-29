"""`pipeline` -- the human side: scaffold, file, inspect and unblock tickets."""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from pipeline.cli import metrics
from pipeline.cli.client import connect
from pipeline.core import PipelineError, line_buffer_stdout
from pipeline.core.config import (CONFIG_TEMPLATE, TICKET_TEMPLATE,
                                  config_source, install_skill, mark_skill,
                                  pin_dir, pin_path, project_config,
                                  selector_failure, skill_marks, skill_status,
                                  suite_failure, sync_pins)
from pipeline.core.gate import gate
from pipeline.core.machine import KNOWN_STAGES, cleared_key
from pipeline.core.ticket import Ticket, now, tickets_dir
from pipeline.core.worktree import exclude_project_dir, worktree
from pipeline.daemon import registry
from pipeline.daemon.server import (STALE_HOURS, socket_path, ticket_rows,
                                    waiting_text)
from pipeline.daemon.store import Store, state_dir
from pipeline.daemon.supervisor import run
from pipeline.stream import StreamReader

def proj(args) -> Path:
    return Path(args.project or ".").resolve()


def die(msg: str) -> None:
    """The one place a bad input ends the process. The library raises
    `PipelineError` instead, so one broken project cannot kill the loop."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def cmd_init(args) -> None:
    # `init` is the one command with a positional target, because
    # `pipeline init ~/code/myproject` reads better than the flag. But every
    # other command takes `--project`, so accepting only the positional means
    # `pipeline --project X init` silently scaffolds the current directory
    # instead -- and says "initialised" while doing it.
    # ... and neither given is the documented default for `--project`: the
    # cwd. `Path(None)` raised a bare TypeError past main()'s handler.
    project = proj(args) if not args.dir else Path(args.dir).resolve()
    tickets_dir(project).mkdir(parents=True, exist_ok=True)
    (project / ".project" / "decisions").mkdir(exist_ok=True)
    cfg = project / ".project" / "pipeline.toml"
    if not cfg.exists():
        cfg.write_text(CONFIG_TEMPLATE.read_text())
    print(f"initialised {project / '.project'} -- edit {cfg} for this project's commands")
    # Every packaged skill, not a named one: a skill added to
    # `pipeline/templates/skills/` should reach the projects `init` scaffolds
    # without a second edit here. Each is kept if the project customised it,
    # exactly as `.project/pipeline.toml` is -- `init` never overwrites
    # (DEC-056); only `pipeline skills --refresh` writes.
    KEPT = {
        "current": "  {name} skill already at {dst} -- kept",
        "linked": "  {name} skill already at {dst} -- kept "
                  "(a symlink to the packaged template)",
        "stale": "  {name} skill at {dst} is stale -- kept; run "
                 "pipeline --project {project} skills --refresh",
        "customised": "  {name} skill at {dst} differs from the packaged "
                      "template -- kept (customised)",
        "unknown": "  {name} skill at {dst} differs from the packaged "
                   "template -- kept (no install record; skills --refresh "
                   "--force overwrites it)",
    }
    for name, dst, state in skill_status(project):
        if state == "absent":
            install_skill(project, name)
            print(f"  installed the {name} skill at {dst}")
            continue
        if state == "current" and name not in skill_marks(project):
            mark_skill(project, name, dst.read_text())
        print(KEPT[state].format(name=name, dst=dst, project=project))
    # `--private` is for a shared repo where you are the only one running the
    # pipeline. It writes `.git/info/exclude`, which is per-clone and never
    # committed, so nothing about this tool reaches a teammate's diff. A team
    # that all runs it and still wants tickets out of history wants a tracked
    # `.gitignore` line instead -- a shared decision, made deliberately, not a
    # side effect of a CLI flag.
    if getattr(args, "private", False):
        wrote = exclude_project_dir(project)
        print(f"  excluded `.project/` in {wrote} -- this clone only" if wrote
              else "  `.project/` already excluded (or this is not a git repo)")
        print(f"  {cfg} will never be in git here -- it is pinned at "
              f"{pin_path(project, '.project/pipeline.toml')}")
        print(f"  an unsynced edit is inert -- run "
              f"`pipeline --project {project} config --sync` to adopt it")


def cmd_new(args) -> None:
    project = proj(args)
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
    project = proj(args)
    wt = worktree(project, Ticket.find(project, args.id).frontmatter())
    # the ticket's test lives on its branch; running in the main checkout would
    # report a bogus "test file does not exist" straight into the thread
    ok, failures = gate(project, args.id, wt if wt.is_dir() else None)
    if args.findings:
        # the dispatcher's gate child sends its stdout to a log file it never
        # reads back; this is how the verdict and findings reach it instead --
        # the exit code alone can't carry the findings for the thread note.
        Path(args.findings).write_text(json.dumps({"ok": ok, "findings": failures}))
    for f in failures:
        print(f"FAIL: {f}")
    print("gate: PASS" if ok else "gate: FAIL")
    sys.exit(0 if ok else 1)


SKILLS_HINT = {
    "stale": " -- run pipeline --project {project} skills --refresh",
    "customised": " -- kept; add --force to overwrite it",
    "unknown": " -- kept; add --force to overwrite it",
    "linked": " -- a symlink to the packaged template; never rewritten",
    "current": "",
    "absent": "",
}


def cmd_skills(args) -> None:
    project = proj(args)
    if args.force and not args.refresh:
        die("--force applies to --refresh only")
    for name, dst, state in skill_status(project):
        if args.refresh and state == "absent":
            install_skill(project, name)
            print(f"{name}: installed at {dst}")
        elif args.refresh and state == "stale":
            install_skill(project, name)
            print(f"{name}: refreshed at {dst}")
        elif args.refresh and args.force and state in ("customised", "unknown"):
            install_skill(project, name)
            print(f"{name}: overwritten at {dst}")
        else:
            print(f"{name}: {state} at {dst}"
                  + SKILLS_HINT[state].format(project=project))


def cmd_config(args) -> None:
    project = proj(args)
    if args.sync:
        removed = sync_pins(project)
        print(f"unpinned {len(removed)} file(s) from {pin_dir(project)}" if removed
              else "nothing pinned for this project")
    src = config_source(project)
    print(f"project: {project}")
    print(f"source:  {src}")
    if src == "pinned":
        pin = pin_path(project, ".project/pipeline.toml")
        print(f"pin:     {pin}")
        disk = project / ".project" / "pipeline.toml"
        if pin.is_file() and (not disk.is_file() or pin.read_text() != disk.read_text()):
            print("warning: the working tree differs from the pin -- "
                  "run `pipeline config --sync` to adopt it")
    cfg = project_config(project)
    for k in ("test_one", "test_suite", "test_suite_without_new", "base"):
        print(f"{k} = {cfg.get(k)!r}")


# what the approval gate asks about: the plan, its criteria, its undo path
PLAN_SECTIONS = ("Plan", "Acceptance criteria", "Rollback")


def plan_text(t: Ticket) -> str:
    """Render the sections an approval gate needs to see.

    `Ticket.section()` strips the `## <name>` heading, so this prints it
    back. The TUI's `awaiting-approval` pane renders this same string.
    """
    parts = []
    for name in PLAN_SECTIONS:
        body = t.section(name) or "(empty)"
        parts.append(f"## {name}\n\n{body}")
    return "\n\n".join(parts)


def cmd_plan(args) -> None:
    print(plan_text(Ticket.find(proj(args), args.id)))


def record(project: Path, t: Ticket, frm: str, result: str) -> None:
    """A human gate is left in THIS process, not the daemon's.

    With nothing emitted here, "time parked in a human gate" (metrics view 6)
    closed each span at the *next* transition on the ticket -- which is the
    following stage's, so every span carried a whole agent run on top of the
    human's actual wait. `transition` with the same shape `advance()` emits is
    the whole fix; the vocabulary already has it.

    Observability, so it never fails the command that did the real work: the
    ticket file is the source of truth and it is already saved.
    """
    try:
        store = Store()
        try:
            store.emit(str(project), "transition", ticket=t.id, stage=frm,
                       **{"from": frm, "to": t.stage, "result": result,
                          "counters": t.counters})
        finally:
            store.close()
    except Exception as e:
        print(f"note: not recorded in the event log "
              f"({e.__class__.__name__}: {e})", file=sys.stderr)


GATE_NEXT = {"awaiting-approval": "revalidating", "awaiting-merge": "merging"}


def cmd_approve(args) -> None:
    project = proj(args)
    t = Ticket.find(project, args.id)
    gate = t.stage
    if gate not in GATE_NEXT:
        die(f"{args.id} is in `{t.stage}`, not a gate `approve` handles "
            f"({', '.join(GATE_NEXT)})")
    # not `implementing`: the Tier A facts behind this plan were recorded
    # before the ticket sat here, and base has moved since. `revalidating`
    # rebases and re-gates. Approval returns now rather than waiting on it.
    t.stage = GATE_NEXT[gate]
    t.extra["approved_by"] = args.by or os.environ.get("USER", "unknown")
    t.extra["approved_at"] = now().isoformat()
    t.append("human", "approval", f"**approved by {t.extra['approved_by']}**",
             by=t.extra["approved_by"])
    t.save()
    record(project, t, gate, "approved")
    print(f"{args.id}: -> {t.stage}")


def cmd_reject(args) -> None:
    """A human rejecting a plan they simply do not want -- distinct from
    plan-validation's mechanical/judgment rejection, so it charges its own
    counter (`plan_rejections`) instead of `plan_validation_attempts`. At the
    bound this refuses rather than escalating: escalation means "a human must
    look", and one already is, holding the keyboard. The counter is lifetime,
    not "in a row" -- like every other counter here it only clears via an
    explicit `--reset`, which is why the escape hatch below names it."""
    project = proj(args)
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
    record(project, t, "awaiting-approval", "rejected")
    print(f"{args.id}: -> planning")


def cmd_note(args) -> None:
    """Appends a human note at any stage, escalated included. No control
    field changes -- a stage already holding a lease sees it only on its
    next spawn, since the prompt is composed once."""
    project = proj(args)
    t = Ticket.find(project, args.id)
    who = os.environ.get("USER", "human")
    t.append("human", "note", f"**note from {who}**\n\n{args.text}", by=who)
    t.save()
    print(f"{args.id}: note added"
          + (f" (`{t.stage}` holds a lease; it reaches the stage on its next spawn)"
             if t.lease_active() else ""))


def cmd_answer(args) -> None:
    project = proj(args)
    t = Ticket.find(project, args.id)
    if t.stage != "needs-input":
        die(f"{args.id} is in `{t.stage}`, not `needs-input`")
    t.stage = "planning"
    t.append("human", "answer",
             f"**answer from {os.environ.get('USER', 'human')}**\n\n{args.text}")
    t.save()
    record(project, t, "needs-input", "answered")
    print(f"{args.id}: -> planning")


def parse_grant(spec: str) -> tuple[str, int]:
    """`<counter>` or `<counter>=<n>`: which counter, and how many spent
    attempts to hand back. Bare means one."""
    key, eq, raw = spec.partition("=")
    if not key or (eq and not (raw.isdigit() and int(raw) >= 1)):
        die(f"`--grant {spec}`: want `<counter>` or `<counter>=<n>` with n >= 1")
    return key, int(raw) if eq else 1


def cmd_resume(args) -> None:
    project = proj(args)
    if args.stage not in KNOWN_STAGES:
        die(f"`{args.stage}` is not a stage: {', '.join(sorted(KNOWN_STAGES))}")
    if args.note is not None and not args.note.strip():
        die("a note needs text -- an empty one tells the resumed stage nothing")
    t = Ticket.find(project, args.id)
    grants: dict[str, int] = {}
    for key, n in (parse_grant(s) for s in args.grant or []):
        grants[key] = grants.get(key, 0) + n
    clash = set(grants) & set(args.reset or [])
    if clash:
        die(f"`--reset` and `--grant` both name {', '.join(sorted(clash))}: pick one")
    for key, n in grants.items():
        have = t.counters.get(key)
        if have is None:
            die(f"{t.id} has no counter `{key}` "
                f"(it has: {', '.join(sorted(t.counters)) or 'none'})")
        if n > have:
            die(f"{t.id}: cannot grant {n} back to `{key}`, which is {have} -- "
                f"a grant only returns attempts already spent; "
                f"`--reset {key}` zeroes it if that is what you want")
    t.stage = args.stage
    for key in args.reset or []:
        t.counters[key] = 0
    granted = []
    for key, n in grants.items():
        have = t.counters[key]
        t.counters[key] = have - n
        granted.append(f"`{key}` {have} -> {have - n}")
    # charge() subtracts this credit, so a counter a human lowered would
    # keep a credit that outlives the failures it forgave.
    for key in (*(args.reset or []), *grants):
        cred = cleared_key(key)
        if cred in t.counters:
            t.counters[cred] = min(t.counters[cred], t.counters.get(key, 0))
    t.release_lease()
    who = os.environ.get("USER", "human")
    note = f"**resumed** by {who} -> `{args.stage}`, reset {args.reset or []}"
    if granted:
        note += f", granted {', '.join(granted)}"
    t.append("human", "note", note, by=who)
    if args.note:
        t.append("human", "answer",
                 f"**note from {who}**\n\n{args.note}", by=who)
    t.save()
    print(f"{args.id}: -> {args.stage}" +
          (f" ({', '.join(granted)})" if granted else ""))


def cmd_ls(args) -> None:
    """`--project` is a filter, not a target: without one, every registered
    project. The daemon and the files answer with the same rows, built by the
    same `ticket_rows()` -- a fallback that reported different columns would
    make `ls` mean two things.

    The fallback is also wider than the daemon on purpose: the daemon can only
    speak for projects it watches, but a named `--project` is just a directory,
    so `pipeline --project X ls` works whether or not X was ever registered.
    """
    c = connect()
    rows = None
    if c is not None:
        try:
            rows = c.request("ls", project=str(proj(args))
                             if args.project else None)
        except PipelineError:
            rows = None    # unregistered, or a daemon in trouble: read the files
        finally:
            c.close()
    if rows is None:
        targets = [proj(args)] if args.project else registry.projects()
        rows = [r for p in targets for r in ticket_rows(p)]
    if any(r.get("running", False) is None for r in rows):
        # one line, not one token per row: with no daemon EVERY row is
        # unknown, and the per-row marks below are all file facts
        # (`leased`, `stale`) which are still true
        print("-- no daemon: running/mode unknown for these rows")
    for r in rows:
        mark = ("LEASED" if r.get("running") or r.get("leased")
                else f"STALE>{STALE_HOURS}h" if r.get("stale") else "")
        mark = " ".join(x for x in (mark, waiting_text(r.get("waiting"))) if x)
        print(f"{r['id']:<12} {r.get('stage', '?'):<17} "
              f"{r.get('class', '?'):<9} {r.get('counters', {})} {mark}")
        last = r.get("last_session")
        if last and args.verbose:
            cost = (f" cost=${last['cost_usd']:.2f}"
                    if last.get("cost_usd") is not None else "")
            print(f"{'':<12} last: {last['stage']} log={last['log']} "
                  f"replay=`claude --resume {last['id']}`{cost}")


# -- the registry -------------------------------------------------------
def cmd_register(args) -> None:
    # a project whose test commands are wrong registers clean otherwise,
    # and every ticket filed against it then dies at the gate reporting a
    # different symptom of the one broken config
    #
    # `check()` first: it holds DEC-072's `PIPELINE_STAGE` and worktree
    # refusals, and a stage running `pipeline register .` must get that
    # error rather than a run of the project's suite
    path = registry.check(Path(args.path))
    if args.force:
        print("--force: registering without checking this project's test commands")
    else:
        print("checking this project's test commands (--force skips this)")
        # `test_suite` first: the reproduction test asserts its message
        # wins over `test_one`'s, and `or` skips the second command once
        # the first has already refused
        problem = suite_failure(path) or selector_failure(path)
        if problem:
            raise PipelineError(problem)
    print(f"registered {registry.register(path)}")
    if config_source(path) == "pinned":
        print(f"  its .project/pipeline.toml is pinned -- run "
              f"`pipeline --project {path} config --sync` after an edit")


def cmd_unregister(args) -> None:
    p = Path(args.path).resolve()
    print(f"unregistered {p}" if registry.unregister(p) else f"{p} was not registered")


def cmd_projects(args) -> None:
    c = connect()
    watched = set()
    if c is not None:
        try:
            watched = {r["project"] for r in c.request("projects") if r["watched"]}
        except PipelineError:
            pass
        finally:
            c.close()
    for p in registry.projects():
        print(f"{p} {'watched' if str(p) in watched else ''}".rstrip())


# -- daemon control (no --project: there is one daemon) -----------------
def cmd_daemon_status(args) -> None:
    c = connect()
    if c is None:
        print(f"pipelined: not running ({socket_path()})")
        sys.exit(1)
    try:
        d = c.request("ping")
    finally:
        c.close()
    print(f"pipelined {d['version']}: pid {d['pid']} on {d['socket']}, "
          f"{d['projects']} project(s) watched")


def cmd_start(args) -> None:
    c = connect()
    if c is not None:
        c.close()
        die("pipelined is already running")
    logdir = state_dir()
    logdir.mkdir(parents=True, exist_ok=True)
    log = (logdir / "daemon.log").open("a")
    # start_new_session: the daemon outlives the terminal that started it,
    # which is the whole point of it existing.
    subprocess.Popen([sys.executable, "-m", "pipeline.daemon.main",
                      "--interval", str(args.interval),
                      "--harness", args.harness,
                      "-j", str(args.max_parallel)],
                     stdout=log, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(100):
        c = connect()
        if c is not None:
            try:
                d = c.request("ping")
            finally:
                c.close()
            return print(f"pipelined {d['version']}: pid {d['pid']} on {d['socket']}")
        time.sleep(0.05)
    die(f"pipelined did not come up within 5s -- see {logdir / 'daemon.log'}")


def cmd_stop(args) -> None:
    c = connect()
    if c is None:
        die("pipelined is not running")
    try:
        pid = c.request("ping")["pid"]
    finally:
        c.close()
    os.kill(pid, signal.SIGTERM)
    # Watch the PID, not the socket. A daemon inside shut_down() waits up to
    # 10s per child before releasing its leases and unlinking the socket, and
    # while it is in there it accepts nothing -- so a failed connect would mean
    # "still busy" just as often as "gone", and reporting `stopped` while the
    # flocks are still held is the one answer that must never be wrong.
    for _ in range(1200):                      # 60s
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return print(f"pipelined {pid}: stopped")
        except PermissionError:
            break                              # not ours to watch; not ours to wait on
        time.sleep(0.05)
    die(f"pipelined {pid} did not stop within 60s -- still holding its leases")


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
    # Everything the parser could not name. Three different things arrive here
    # and they do not deserve the same line:
    #
    #  * a line that was never JSON -- a DISPATCHER stage (`verifying`,
    #    `merging`) logs plain shell output, so `?? Fast-forward` marks as
    #    unparseable something there was nothing to parse in. Print it as it
    #    came: git output should look like git output.
    #  * `system/thinking_tokens` -- a token counter emitted once per model
    #    turn. 45 of one implementing stage's 189 events were this. Dropped.
    #  * anything else -- name it `type/subtype` and carry whatever text it
    #    has, because `?? system` says nothing a human can act on.
    if ev.get("raw") is not None:
        return _one(ev["raw"])
    if ev.get("subtype") == "thinking_tokens":
        return ""
    label = "/".join(x for x in (ev.get("raw_type"), ev.get("subtype")) if x)
    return f"?? {label or '?'} {_one(ev.get('text') or ev.get('error') or '')}".rstrip()


def cmd_logs(args) -> None:
    """Pretty-print a stage's stream-json log. `-f` follows it and returns when
    the stage's `result` event lands. Today the log file is the stream: the
    child writes it, this reads it. When the daemon (TICKET-011) owns the
    child's fd it feeds the same `StreamReader` from the pipe instead."""
    project = proj(args)
    logs = sorted((project / ".project" / "logs").glob(f"{args.id}-*.log"),
                  key=lambda p: p.stat().st_mtime)
    if not logs:
        die(f"no log for {args.id} under .project/logs")
    log = logs[-1]
    print(f"-- {log.relative_to(project)}")
    reader = StreamReader()
    shown = False
    try:
        with log.open("rb") as fh:
            while True:
                chunk = fh.read(1 << 16)
                if not chunk:
                    if not args.follow:
                        # an interactive stage's log is raw terminal output, so
                        # there is no stream-json in it to render. Say so, or
                        # this prints a header and nothing else and looks broken
                        if not shown:
                            print(f"(no stream-json here -- an interactive "
                                  f"stage's log is the raw terminal stream: "
                                  f"cat {log})")
                        return
                    time.sleep(0.4)
                    continue
                for ev in reader.feed(chunk):
                    line = render(ev)
                    if line:
                        shown = True
                        print(line, flush=True)
                    if ev["kind"] == "result":
                        return
    except KeyboardInterrupt:
        return


def _metrics_project(args) -> str | None:
    """`--project` here is `PATH|name`: a bare name matches a registered
    project's directory basename, so `--project agent-pipeline` works from
    anywhere without typing the absolute path events are stored under.
    `--project` is a filter everywhere in this CLI, never a target -- omit
    it and every project's events count."""
    value = getattr(args, "project", None)
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        return str(p)
    for r in registry.projects():
        if r.name == value:
            return str(r)
    return str(p.resolve())


def cmd_metrics(args) -> None:
    try:
        since = metrics.parse_since(args.since) if args.since else 0.0
    except ValueError:
        die(f"--since {args.since!r} is not `\\d+[hdw]` or an ISO date")
    conn = metrics.connect(args.db)
    try:
        data = metrics.collect(conn, since, _metrics_project(args))
    finally:
        conn.close()
    print(json.dumps(data, default=str, indent=2) if args.json else metrics.render(data))

def cmd_tui(args) -> None:
    """The dashboard. `--project` is a filter here too, exactly as for `ls`.

    The `textual` import is inside the function on purpose: it pulls in rich
    and a few thousand lines of widget, and `pipeline approve` has no business
    paying for that.
    """
    from pipeline.tui.app import PipelineApp

    app = PipelineApp(connect(), str(proj(args)) if args.project else None)
    app.run()
    sys.exit(app.return_code or 0)


# `add_parser(help=...)` reaches the top-level `pipeline --help` listing only:
# argparse pops it for the parent and never sets `description`, so `pipeline
# start --help` printed usage and options alone. `description=` is what a
# subcommand's own --help prints. Both strings are bound by
# tests/test_cli.py::test_the_help_text_matches_the_code_it_describes.
START_DESC = (
    "Start the one daemon for every registered project. A stage whose "
    "frontmatter says `mode: interactive` -- `planning` -- runs on a PTY the "
    "daemon owns only while a client is attached: leave `pipeline tui` open "
    "and it waits there at its first permission prompt. With no client "
    "subscribed it runs headless, exactly as `pipeline run` does."
)
RUN_DESC = (
    "Run one project's dispatcher loop, with no daemon and no socket. Nothing "
    "can attach, so a stage whose frontmatter says `mode: interactive` -- "
    "`planning` -- runs headless here and never waits for a human; its escape "
    "hatch is `result: needs-input`, which parks the ticket for `pipeline "
    "answer`. Under `pipeline start` that same stage waits at `pipeline tui`, "
    "and only if a tui is attached when it spawns."
)


def main() -> None:
    line_buffer_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", help="project dir; a filter for `ls`, "
                    "the target for everything else (default: cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.add_argument("dir", nargs="?", default=None); p.add_argument("--private", action="store_true", help="hide .project/ from git in this clone only (.git/info/exclude)"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("new"); p.add_argument("title"); p.add_argument("--class", dest="cls", default="bugfix"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("gate"); p.add_argument("id"); p.add_argument("--findings", help="write {ok, findings} JSON here; the dispatcher's gate child reads it back"); p.set_defaults(fn=cmd_gate)
    p = sub.add_parser("config", help="where the dispatcher reads this project's pipeline.toml"); p.add_argument("--sync", action="store_true", help="adopt the working tree's config on a project git will never have"); p.set_defaults(fn=cmd_config)
    p = sub.add_parser("skills", help="is this project's skill copy current with the packaged template"); p.add_argument("--refresh", action="store_true", help="rewrite a stale copy from the packaged template; a customised copy is kept"); p.add_argument("--force", action="store_true", help="with --refresh, overwrite a customised copy too"); p.set_defaults(fn=cmd_skills)
    p = sub.add_parser("plan"); p.add_argument("id"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("approve"); p.add_argument("id"); p.add_argument("--by"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("reject"); p.add_argument("id"); p.add_argument("reason"); p.set_defaults(fn=cmd_reject)
    p = sub.add_parser("note"); p.add_argument("id"); p.add_argument("text"); p.set_defaults(fn=cmd_note)
    p = sub.add_parser("answer"); p.add_argument("id"); p.add_argument("text"); p.set_defaults(fn=cmd_answer)
    p = sub.add_parser("resume"); p.add_argument("id"); p.add_argument("--stage", required=True); p.add_argument("--grant", nargs="*", metavar="COUNTER[=N]", help="hand back N spent attempts (default 1) on a counter; a grant only subtracts"); p.add_argument("--reset", nargs="*"); p.add_argument("--note", metavar="TEXT", help="a note for the resumed stage; recorded in the ticket thread, attributed to you"); p.set_defaults(fn=cmd_resume)
    p = sub.add_parser("logs"); p.add_argument("id"); p.add_argument("-f", "--follow", action="store_true"); p.set_defaults(fn=cmd_logs)
    p = sub.add_parser("ls", help="tickets (via the daemon if one is running)"); p.add_argument("-v", "--verbose", action="store_true"); p.set_defaults(fn=cmd_ls)
    p = sub.add_parser("status", help="is the daemon running"); p.set_defaults(fn=cmd_daemon_status)
    p = sub.add_parser("tui", help="watch and steer running stages"); p.set_defaults(fn=cmd_tui)
    p = sub.add_parser("register"); p.add_argument("path", nargs="?", default="."); p.add_argument("--force", action="store_true", help="register without running the project's test commands"); p.set_defaults(fn=cmd_register)
    p = sub.add_parser("unregister"); p.add_argument("path", nargs="?", default="."); p.set_defaults(fn=cmd_unregister)
    p = sub.add_parser("projects"); p.set_defaults(fn=cmd_projects)
    p = sub.add_parser("start", help="start the one daemon (interactive stages wait at `pipeline tui`)", description=START_DESC); p.add_argument("--interval", type=int, default=10); p.add_argument("--harness", default="claude-code"); p.add_argument("-j", "--max-parallel", type=int, default=3, help="agents in flight across every registered project"); p.set_defaults(fn=cmd_start)
    p = sub.add_parser("stop"); p.set_defaults(fn=cmd_stop)
    p = sub.add_parser("run", help="one project, no daemon, no socket (interactive stages run headless)", description=RUN_DESC); p.add_argument("--once", action="store_true"); p.add_argument("--interval", type=int, default=10); p.add_argument("--harness", default="claude-code"); p.add_argument("-j", "--max-parallel", type=int, default=3, help="agents in flight for this project"); p.set_defaults(fn=None)
    p = sub.add_parser("metrics", help="six views over the event log")
    p.add_argument("--since", help="7d|24h|2w|<ISO date> (default: all history)")
    # SUPPRESS: a bare `pipeline metrics` must not clobber a `--project`
    # already parsed off the top-level `ap` with this subparser's own None
    # default -- argparse writes both into the same namespace.
    p.add_argument("--project", default=argparse.SUPPRESS, help="PATH|name (default: every project)")
    p.add_argument("--db", help="override the event db (default: "
                        "$XDG_STATE_HOME/pipeline/events.db, or "
                        "~/.local/state/pipeline/events.db)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_metrics)

    args = ap.parse_args()
    try:
        if args.cmd == "run":
            run(proj(args), args.once, args.interval,
                args.harness, args.max_parallel, Store())
        else:
            args.fn(args)
    except PipelineError as e:
        die(str(e))
