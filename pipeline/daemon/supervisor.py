"""The dispatcher loop: claim a ticket, spawn one stateless agent per stage,
reap it, apply its verdict. The state machine decides; this only obeys."""
import fcntl
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path

from pipeline import __version__
from pipeline.core import PipelineError
from pipeline.core.config import (cap_config, compose_prompt,
                                  format_tests_cmd, harness, is_readonly,
                                  mcp_config, mcp_servers, project_config,
                                  project_max_parallel, readonly_allow,
                                  render, stage_cap, stage_config,
                                  stage_settings)
from pipeline.core.fence import fenced_touches
from pipeline.core.gate import environment_only, gate, plan_steps, structural_only
from pipeline.core.machine import (CLEANUP_STAGES, CONTROL_FIELDS,
                                   HUMAN_GATES, MAX_ATTEMPTS, TERMINAL,
                                   apply_claims, bound_for, conflict_holder,
                                   transition)
from pipeline.core.ticket import (Ticket, all_tickets, drop_result,
                                  now, read_result, record_decision,
                                  result_file, stage_view, ticket_path,
                                  tickets_dir, validate_meta)
from pipeline.core.worktree import (base_ref, dirty_snapshot, drop_worktree,
                                    ensure_worktree, git_ignored, project_env,
                                    retry_eagain, run_cmd, strip_settings_sources,
                                    tree_snapshot, worktree)
from pipeline.daemon import registry
from pipeline.daemon.server import Poller
from pipeline.daemon.store import noop
from pipeline.pty import host
from pipeline.stream import StreamReader


def _pid_of(holder) -> int | None:
    """A lease holder is `f"{stage}-{os.getpid()}"` -- the supervisor's pid."""
    m = re.search(r"-(\d{1,9})$", str(holder or ""))
    return int(m.group(1)) if m else None


def holder_alive(holder) -> bool:
    """A daemon restart must not park every in-flight ticket for half an hour.
    The lease holder is a pid: if it is gone, the supervisor that took the
    lease died and the lease is stale whatever its clock says.

    Fail-safe, never fail-open: an unparseable holder, or a pid that has been
    recycled onto some live process, reads as alive and we wait out the normal
    30-minute expiry instead of spawning a second agent onto a live one.
    """
    pid = _pid_of(holder)
    if pid is None or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True      # someone else's process: alive, just not ours
    return True


def escalate(t: Ticket, reason: str, emit=noop) -> None:
    emit("escalated", ticket=t.id, stage=t.stage, reason=reason)
    t.append(t.stage, "escalation", reason)
    t.stage = "escalated"
    t.release_lease()  # a human must be able to resume
    # the one unvalidated write: unusable frontmatter is itself a reason to
    # escalate, and refusing that write would leave the ticket un-quarantined
    t.save(validate=False)
    print(f"  {t.path.stem}: -> escalated ({reason})")


# `pipeline/stages/_common.md` tells every stage to start `summary:` with
# this character. It is evidence about the agent's context, never a
# verdict: nothing below acts on its absence.
MARKER = "✓"

# A commit sha `t.extra["cheap_route_head"]` must match before it reaches a
# shell, per invariant 5 -- it is hostile input, same as every other ticket
# field.
SAFE_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def has_marker(note: str) -> bool:
    """Did this summary still carry the shared prose rules' marker?

    The character, NOT the character plus a space: `loose_result()`
    (`pipeline/core/ticket.py`) takes `rest.strip()`, so a sidecar whose
    YAML broke arrives with the space already gone, and a `"✓ "` prefix
    test would report a marked stage as unmarked.
    """
    return str(note or "").lstrip().startswith(MARKER)


def advance(project: Path, t: Ticket, result: str, note: str, emit=noop,
            agent: bool = True) -> None:
    # `agent` says this note is an agent's `.result` summary. The
    # dispatcher's own notes are nobody's prose, so they get no `marker`
    # key at all -- absent means "not applicable", False means "a stage
    # prompt lost the rule", and collapsing the two would count every
    # dispatcher pickup as a failure.
    stage = t.stage
    # The size arrives through counters because `transition()` may not read a
    # file. It is recomputed at every advance, so a re-plan is measured as it
    # lands. It is written onto `t.counters` first, so the `charged` scan
    # below still sees exactly one changed key.
    t.counters = {**t.counters, "plan_steps": plan_steps(t.section("Plan")),
                  "plan_files": len(t.files_declared)}
    nxt, counters = transition(stage, result, t.counters, t.klass)
    marker = has_marker(note) if agent else None   # BEFORE t.append copies the note
    ev = {} if marker is None else {"marker": marker}
    attrs = {} if marker is None else {"marker": "yes" if marker else "no"}
    emit("transition", ticket=t.id, stage=stage, **{"from": stage, "to": nxt,
         "result": result, "counters": counters}, **ev)
    if nxt == "escalated":
        # The other route into `escalated`. `escalate()` covers the paths it
        # owns -- a crash, a tamper, an unusable ticket -- and it sets the
        # stage itself, so it never reaches here and the two cannot
        # double-emit. Without this, a ticket that escalated by burning a loop
        # bound left only a `transition` row, and "escalation rate per stage"
        # -- the view that exists to catch a miscalibrated prompt -- read zero
        # for exactly the stage the prompt was miscalibrated in.
        charged = next((k for k, v in counters.items()
                        if v != t.counters.get(k, 0)), None)
        emit("escalated", ticket=t.id, stage=stage, reason=(
            f"`{charged}` reached its bound "
            f"({counters[charged]}/{bound_for(t.klass, charged, counters)})"
            if charged else f"`{stage}` escalated on result `{result}`"))
    t.append(stage, "transition", f"**{stage} -> {nxt}** (result: `{result}`)\n\n{note}",
             to=nxt, result=result, **attrs)
    if nxt == "done":
        did = record_decision(project, t)
        t.append(stage, "decision", f"decision recorded as `{did}`" if did else
                 "no `## Decisions` section -- nothing recorded for "
                 "future planning agents to find")
    t.counters = counters
    t.stage = nxt
    t.release_lease()
    t.save()
    print(f"  {t.path.stem}: -> {nxt} {counters}")
    # ...and only now is the record final enough to commit. `escalated` is
    # excluded with the same reasoning that keeps its worktree: its ticket is
    # evidence a human is about to edit, and committing it would land a
    # half-finished thread on the base branch.
    if nxt in CLEANUP_STAGES:
        code, head = run_cmd("git rev-parse --abbrev-ref HEAD", project)
        base = str(project_config(project).get("base", "main"))
        ignored = git_ignored(project, ".project")
        if ignored:
            # A shared repo where not everyone runs the pipeline: `.project/`
            # is excluded (`.gitignore`, or `.git/info/exclude` for one clone
            # only) and the tickets stay a local queue. `git add` refuses an
            # ignored path, so this was already a no-op -- it just said
            # nothing, which reads the same as a commit that failed.
            print(f"  {t.id}: not recording -- `.project` is git-ignored here")
        elif code or head.strip() != base:
            print(f"  {t.id}: not committing the record -- checkout is on "
                  f"`{head.strip() or '?'}`, not `{base}`")
        elif commit_record(project, t):
            print(f"  {t.id}: recorded the finished ticket on `{base}`")


PIPE_SZ = 1 << 20   # the usual /proc/sys/fs/pipe-max-size for an unprivileged user


def _widen(fd: int) -> None:
    """Grow the child's stdout buffer from 64K to 1M, best-effort.

    Headroom, not a fix. The loop makes blocking calls -- `ensure_worktree`
    runs git and `worktree_setup` -- and for their duration NOTHING drains
    any pipe. At 64K a chatty agent fills up in seconds and blocks in
    `write()` holding its lease.
    """
    try:
        fcntl.fcntl(fd, getattr(fcntl, "F_SETPIPE_SZ", 1031), PIPE_SZ)
    except OSError:
        pass                 # not a pipe, or the cap is lower. Best-effort.


def drain_all(inflight: dict) -> None:
    """Pump every in-flight child. Called immediately before the loop makes a
    blocking call, so a stage does not sit at a full buffer for the length of
    somebody else's test run."""
    for rec in list(inflight.values()):
        if rec.get("pipe") is not None:
            try:
                pump(rec)
            except Exception as e:
                print(f"  pump: {e.__class__.__name__}: {e}")


def pump(rec: dict) -> None:
    """Drain one child's stdout and tee it to its log.

    This is what makes `stdout=PIPE` safe: nothing else reads this pipe, so a
    stage that filled the kernel's 64K buffer would block in `write()` while
    holding its lease, forever. Registered with the poller, it drains on every
    tick instead.

    It TEES rather than redirects: the log file is what `claude --resume` and
    `pipeline logs` both read, and a pipe nobody wrote down is a debugging
    session nobody can have. Parsed events go to `rec["sink"]`, which is where
    a stream consumer attaches -- the default drops them.
    """
    fd = rec["pipe"].fileno()
    while True:
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            chunk = b""
        if not chunk:                      # EOF: the child is done writing
            if rec.get("poller"):          # a test may host a PTY with no loop
                rec["poller"].unwatch(fd)
            return
        rec["fh"].write(chunk)
        rec["fh"].flush()
        for ev in rec["reader"].feed(chunk):
            rec["sink"](ev)


# What a parsed stream event may be stored as. DEC-011 froze the vocabulary
# and `other` is not in it: an unknown or truncated line is noise, and a row
# per line of it would be the log file again, in SQLite.
STREAM_KINDS = {"init", "assistant", "tool_result", "hook_started",
                "hook_response", "rate_limit", "result"}


# `Store.emit(project, kind, ticket=, stage=, session=, **data)` -- the
# keywords a parsed record may never supply.
EMIT_COLUMNS = ("kind", "project", "ticket", "stage", "session")


def event_sink(tid: str, stage: str, session: str, emit):
    """TICKET-012's parser -> TICKET-011's event log. This is the seam: `pump`
    hands every parsed record to `rec["sink"]`, which used to drop it, so
    `result` and `hook_response` never reached the store and the metrics views
    built on them read "no data" against a live system.

    Wrapped, because the event log is observability and the dispatcher is the
    product: a full disk or a locked database costs history, never the lease
    of every stage in flight.
    """
    def sink(ev: dict) -> None:
        kind = ev.get("kind")
        if kind not in STREAM_KINDS:
            return
        try:
            emit(kind, ticket=tid, stage=stage, session=session,
                 # These are `emit()`'s own columns, not payload. A parsed
                 # record carrying one of them (`init` has its own `session`;
                 # a `rate_limit_event` is a passthrough, so a child's stdout
                 # can name any of them) raised `TypeError: multiple values
                 # for 'ticket'` and the event was swallowed by the wrapper
                 # below -- silent loss driven by the child.
                 **{k: v for k, v in ev.items() if k not in EMIT_COLUMNS})
        except Exception as e:
            print(f"  {tid}: event not recorded ({e.__class__.__name__}: {e})")
    return sink


def terminal_sink(rec: dict, inner):
    """Wrap a sink to keep the harness's own reason for stopping on `rec`.

    The harness names why it stopped on its `result` event, the child then
    exits like any other failure, and `event_sink()` writes to the event log,
    which nothing reads back inside one tick.
    """
    def sink(ev: dict) -> None:
        if ev.get("kind") == "result":
            if ev.get("terminal_reason"):
                rec["terminal_reason"] = ev["terminal_reason"]
            rec["cost_usd"] = ev.get("total_cost_usd")
            rec["usage"] = ev.get("usage") or {}
        inner(ev)
    return sink


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def cost_report(rec: dict) -> str:
    """Render a run's cost and tokens for the session thread entry.

    `""` when no `result` event arrived (an interactive stage, DEC-077):
    a zero-dollar line there would read as a free run rather than an
    unmeasured one. Every number is coerced, so a malformed `usage` never
    raises -- it renders zeros instead.
    """
    if rec.get("cost_usd") is None:
        return ""
    cost = f"${float(rec['cost_usd']):.2f}"
    if rec.get("cap"):
        cost += f" of a ${rec['cap']} cap"
    usage = rec.get("usage") or {}
    out = _int(usage.get("output_tokens"))
    thinking = _int(usage.get("output_tokens_details", {}).get("thinking_tokens")
                     if isinstance(usage.get("output_tokens_details"), dict) else None)
    inp = _int(usage.get("input_tokens"))
    cache_read = _int(usage.get("cache_read_input_tokens"))
    cache_write = _int(usage.get("cache_creation_input_tokens"))
    out_part = f"{out:,} out"
    if thinking:
        out_part += f" ({thinking:,} thinking)"
    tokens = (f"{out_part} · {inp:,} in · {cache_read:,} cache read "
              f"· {cache_write:,} cache write")
    return f"\n- cost: {cost}\n- tokens: {tokens}"


def usage_events(session: str) -> list[dict]:
    """One interactive stage's token usage, summed per model, off its session
    transcript.

    A PTY stage never produces a `result` event, and there is no cost to read
    anywhere else: `claude agents --json` carries none and a transcript has no
    `cost`/`usd` key at any depth. What every `type:"assistant"` line does
    have is `message.model` and a full `message.usage`.

    Glob on the uuid rather than reimplementing the cwd-to-slug rule -- a
    worktree path contains dots and `.worktrees`, and getting that rule subtly
    wrong reads exactly like a stage that cost nothing. No transcript (a stage
    that died early) is not an error: no events.
    """
    totals: dict[str, dict] = {}
    for path in Path.home().glob(f".claude/projects/*/{session}.jsonl"):
        for line in path.read_text(errors="replace").splitlines():
            try:
                ev = json.loads(line)
                msg = ev.get("message") or {}
                u = msg.get("usage") or {}
            except Exception:
                continue            # same rule as the parser: never raise on a line
            if ev.get("type") != "assistant" or not isinstance(u, dict) or not u:
                continue
            t = totals.setdefault(msg.get("model") or "unknown",
                                  {"input_tokens": 0, "output_tokens": 0,
                                   "cache_read": 0, "cache_creation": 0})
            for key, src in (("input_tokens", "input_tokens"),
                             ("output_tokens", "output_tokens"),
                             ("cache_read", "cache_read_input_tokens"),
                             ("cache_creation", "cache_creation_input_tokens")):
                try:
                    t[key] += int(u.get(src) or 0)
                except (TypeError, ValueError):
                    pass
    return [{"model": m, **t} for m, t in totals.items()]


def close_child(rec: dict) -> None:
    """Every path that used to be `rec["fh"].close()`. Drains the pipe first:
    the last thing a child writes lands between its exit and our poll.

    Idempotent, because `finish()` calls it in a `finally` as well: an fd left
    registered with the poller after its record is gone would have its callback
    fire on every tick, forever, against a closed file.
    """
    pipe = rec.get("pipe")
    if pipe is not None:
        try:
            pump(rec)               # the tail the child wrote as it exited
        finally:
            rec["pipe"] = None      # what makes a second call a no-op
            if rec.get("poller"):
                rec["poller"].unwatch(pipe.fileno())
            pipe.close()
    if rec.get("fh") is not None:
        rec["fh"].close()


def spawn(project: Path, wt: Path, tid: str, stage: str, hcfg: dict,
          poller: Poller | None = None, emit=noop) -> dict:
    """Start an agent and return immediately. The dispatcher never blocks on an
    agent, which is what makes this a pipeline rather than a call tree."""
    cfg = stage_config(stage, project)
    # Above the `supports_hooks` refusal: a harness that cannot register the
    # guard hook must still not launch on top of a settings source that would
    # have disabled it, so the strip runs whether or not this spawn proceeds.
    stripped = strip_settings_sources(wt)
    if stripped:
        print(f"  {tid}: removed {', '.join(stripped)} from the worktree -- "
              f"a settings source there disables the guard for every spawn in it")
        emit("guard_strip", ticket=tid, stage=stage, files=stripped)
    if cfg.get("hooks") and not hcfg.get("supports_hooks", True):
        # invariant 4: a hook is the only layer that decides with code. A
        # harness that cannot register one would run this stage with only the
        # tree-snapshot backstop -- detection after the fact, not prevention --
        # so refuse instead of silently downgrading the one layer that promises.
        raise PipelineError(f"harness cannot register hooks -- refusing to run "
                            f"`{stage}` unguarded (declares hooks: {cfg['hooks']})")
    # A stage a human has to steer: `--permission-mode` is ignored under `-p`
    # and AskUserQuestion is not in the headless toolset, so a permission
    # prompt or an option picker only exists on a real terminal.
    #
    # `mode: interactive` therefore means "interactive WHEN a human can reach
    # it". Under `pipeline run` there is no socket, so nothing can ever
    # `attach`, and a REPL nobody attaches to sits at its prompt until the
    # lease expires twice and the ticket escalates -- which would make the
    # daemon a dependency for every ticket that reaches `planning`, not an
    # accelerator. Headless is what the stage did before it grew a PTY, and
    # its prompt already carries the escape hatch: `result: needs-input`
    # parks the ticket at a human gate instead of asking on a terminal.
    # A daemon is not a human: attachable only says a socket exists, so
    # pipeline start with nobody on it spawned the REPL anyway and parked it
    # at a permission prompt nobody could see (TICKET-059). watchers() is the
    # second question -- a client subscribed right now. A TUI that attaches
    # after the spawn gets a headless stage, deliberately: the alternative is
    # holding a ticket for a human who may never arrive.
    attached = (poller.watchers(str(project.resolve()))
                if getattr(poller, "attachable", False) else 0)
    interactive = cfg.get("mode") == "interactive" and attached > 0
    if cfg.get("mode") == "interactive" and not interactive:
        why = ("nothing can attach to it here"
               if not getattr(poller, "attachable", False)
               else "no client is attached")
        print(f"  {tid}: `{stage}` is interactive, but {why} -- running "
              f"headless (leave `pipeline tui` open before the stage starts "
              f"to steer it)")
    session = str(uuid.uuid4())
    logs = project / ".project" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{tid}-{stage}-{session[:8]}.log"
    counters: dict = {}
    try:
        t = Ticket.find(project, tid)
        counters, view = t.counters, stage_view(t, stage)
    except PipelineError:
        # Total: `spawn()` is called directly with no ticket on disk
        # (tests/test_pty.py:393). No view means the agent reads the file,
        # which is exactly what it did before this existed.
        view = ""
    prompt = compose_prompt(stage, hcfg, view, project, interactive=interactive)
    settings = stage_settings(stage, cfg)
    servers = mcp_servers(project, cfg)
    mcp = mcp_config(servers)
    allow = readonly_allow(project)
    # A review cap scales with the plan its diff came from, the way
    # `bound_for()` scales an attempt budget (DEC-047). The counters ride
    # the ticket load the view already pays for. This rebind must precede
    # the `stage_cap(cfg, hcfg)` call below so `rec["cap"]` carries the
    # scaled number.
    cfg = cap_config(stage, cfg, project, counters)
    cmd = render(hcfg, cfg, tid=tid, project=project,
                ticket=ticket_path(project, tid),
                result_file=tickets_dir(project) / f"{tid}.result",
                session=session, prompt=prompt, settings=settings, mcp=mcp,
                key="interactive_cmd" if interactive else "cmd")
    fh = log.open("wb")
    fh.write(f"$ {cmd}\n\n".encode())
    if interactive:
        # the width `render_pty()` replays at; interactive-only, because an
        # ESC in a batch log sends stream-json through pyte instead of
        # rendering it (DEC-039)
        fh.write(host.geom_marker(host.ROWS, host.COLS))
    fh.flush()
    env = project_env()
    env["PIPELINE_STAGE"] = stage
    env["PIPELINE_READONLY"] = "0" if cfg.get("write") else "1"
    # The guard's file-tool rule compares a Write/Edit path against these.
    # The two exceptions -- the ticket file and the `.result` sidecar -- are
    # exported by path rather than re-derived inside the hook.
    env["PIPELINE_WORKTREE"] = str(wt)
    env["PIPELINE_TICKET"] = str(ticket_path(project, tid))
    env["PIPELINE_RESULT"] = str(tickets_dir(project) / f"{tid}.result")
    env["PIPELINE_MCP_ALLOW"] = ",".join(servers)
    env["PIPELINE_MCP_READONLY"] = ",".join(n for n, s in servers.items()
                                            if s.get("readonly"))
    # A broken [readonly] table surfaces here exactly as a broken [mcp.<name>]
    # one does; a project with no config at all yields [] and spawns as before.
    env["PIPELINE_READONLY_ALLOW"] = json.dumps(allow)
    if interactive:
        # ponytail: the master fd dies with the daemon, so the child gets
        # SIGHUP and an interactive stage does NOT survive a daemon restart --
        # the lease expiry path recovers the ticket. Upgrade = an abduco/dtach
        # style per-session helper holding the pty instead of us.
        env.setdefault("TERM", "xterm-256color")
        proc, pipe = host.start(cmd, wt, env)
    else:
        # PIPE only when someone is going to drain it. With no poller -- a
        # direct `spawn()` call, or a caller that predates the daemon --
        # redirect straight to the log, because an undrained pipe deadlocks
        # the child at 64K.
        proc = retry_eagain(lambda: subprocess.Popen(
            cmd, shell=True, cwd=wt, stdout=subprocess.PIPE if poller else fh,
            stderr=subprocess.STDOUT, env=env))
        pipe = proc.stdout
    mode = "interactive" if interactive else "batch"
    rec = {"proc": proc, "fh": fh, "prompt": prompt, "settings": settings,
           "mcp": mcp,
           "session": session, "mode": mode,
           "log": log, "stage": stage, "wt": wt,
           "poller": poller, "pipe": None, "reader": None,
           "screen": None, "writer": None,
           "terminal_reason": None, "cap": stage_cap(cfg, hcfg),
           "cost_usd": None, "usage": {},
           "sink": event_sink(tid, stage, session, emit)}
    rec["sink"] = terminal_sink(rec, rec["sink"])
    if interactive or poller:
        # `Screen` is shaped like `StreamReader`, so pump() tees the raw bytes
        # to the log and feeds this with no PTY branch of its own.
        rec["reader"] = host.Screen() if interactive else StreamReader()
        rec["screen"] = rec["reader"] if interactive else None
        rec["pipe"] = pipe
        os.set_blocking(pipe.fileno(), False)
        if not interactive:
            _widen(pipe.fileno())
        if poller:
            poller.watch(pipe.fileno(), lambda fd: pump(rec))
    print(f"  start {tid}: {stage} ({cfg.get('model')}, {mode}) "
          f"pid {proc.pid} -> {log.name}")
    emit("stage_start", ticket=tid, stage=stage, session=session,
         model=cfg.get("model"), mode=mode, pid=proc.pid,
         log=str(log), wt=str(wt))
    return rec


GATE_PASS = "gate-pass"


def gate_cmd(project: Path, tid: str, findings: Path) -> str:
    """The Tier A gate as a spawned child, instead of an inline `gate()` call
    that stalled the loop for the length of the project's `test_one`.

    Runs the DISPATCHER's own interpreter, not `project_env()`'s -- this is
    the dispatcher's own code (`pipeline gate`), and the project commands it
    runs re-apply `project_env()` inside `run_cmd()` already.

    `-P` is load-bearing: `spawn_command()` runs its child with `cwd=wt`
    (`pipeline/daemon/supervisor.py:463`), and a bare `-m` prepends that cwd
    to `sys.path`, so it would import the TICKET WORKTREE's own copy of
    `pipeline` -- the code under review judging itself. `-P` drops the cwd
    entry and keeps `PYTHONPATH`, so the dispatcher's own copy judges the gate.
    """
    return (f"{shlex.quote(sys.executable)} -P -m pipeline "
            f"--project {shlex.quote(str(project))} gate {shlex.quote(tid)} "
            f"--findings {shlex.quote(str(findings))}")


REBASE_FAILED = 3


def regate_cmd(project: Path, tid: str, base: str, findings: Path) -> str:
    """Rebase onto base, then gate -- one child for two steps, because the
    gate has to judge the tree the rebase produced. `REBASE_FAILED` (3) marks
    a rebase conflict distinctly from `pipeline gate`'s own 0/1, so
    `finish_regate()` can tell DEC-029's repair path from a gate failure."""
    return (f"git rebase {shlex.quote(base)} || exit {REBASE_FAILED}\n"
            f"{gate_cmd(project, tid, findings)}")


def spawn_command(project: Path, wt: Path, tid: str, stage: str, cmd: str,
                  kind: str = "command", emit=noop, env: dict | None = None) -> dict:
    """Start a dispatcher-owned command as a tracked child, shaped like
    `spawn()`'s record so `reap()` collects it with everything else. Run inline
    the suite stalled the loop: no other ticket advanced and no finished agent
    was reaped while a real project's suite took its minutes. `kind` is what
    `finish()` branches on -- these children have no agent to check."""
    logs = project / ".project" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{tid}-{stage}-{uuid.uuid4().hex[:8]}.log"
    fh = log.open("w")
    fh.write(f"$ {cmd}\n\n")
    fh.flush()
    proc = retry_eagain(lambda: subprocess.Popen(
        cmd, shell=True, cwd=wt, stdout=fh,
        stderr=subprocess.STDOUT, env=env or project_env()))
    print(f"  start {tid}: {stage} (script) pid {proc.pid} -> {log.name}")
    emit("stage_start", ticket=tid, stage=stage, model=None, mode=kind,
         pid=proc.pid, log=str(log), wt=str(wt))
    return {"kind": kind, "proc": proc, "fh": fh, "prompt": None,
            "settings": None, "session": None, "mode": kind,
            "log": log, "stage": stage, "wt": wt,
            "poller": None, "pipe": None, "reader": None,
            "sink": lambda ev: None}


def commit_record(project: Path, t: Ticket) -> str | None:
    """Commit the finished ticket and its decision record onto the base branch.

    Until 2026-08-22 nothing did this. `.project/` is tracked and not ignored,
    but no code path and no stage prompt ever ran `git add` on it -- a stage
    structurally cannot, since its cwd is the worktree and the ticket lives in
    the main checkout. So 12 of 34 tickets and 13 decisions sat untracked, and
    the 22 that were in history got there in hand-made batches ("chore: close
    the 15 tickets implemented during the build"). That history recorded when
    somebody tidied up, not when work finished.

    The decisions are why this is a correctness fix and not tidiness:
    `planning` greps `.project/decisions/` to avoid re-deciding what is already
    settled, so a decision that never reaches a commit is invisible to every
    future clone.

    Called from `advance()` AFTER `t.save()`, which is the only point where all
    three files are final: `record_decision()` writes the new record and may
    append a `superseded-by:` footer to an older one, and `t.stage` is not
    `done` until the save. `merge_cmd()` is the wrong place for the same
    reason -- it runs while the ticket still says `stage: merging`.

    Refuses rather than guesses, like everything else that touches the main
    checkout: it stages exactly the paths it wrote (never `git add .`, which
    would sweep up whatever the operator has in flight) and skips entirely if
    the checkout is parked off the base branch. A skipped commit is a ticket
    that stays untracked, which is where it was anyway -- never a failed one.
    """
    files = [str(t.path.relative_to(project))]
    dec = project / ".project" / "decisions"
    if dec.is_dir():
        code, out = run_cmd("git status --porcelain -- .project/decisions", project)
        if code == 0:
            files += [ln[3:].strip().strip('"') for ln in out.splitlines() if ln[3:].strip()]
    paths = " ".join(shlex.quote(f) for f in dict.fromkeys(files))
    code, out = run_cmd(f"git add -- {paths} && git commit -q -m "
                        f"{shlex.quote(f'chore({t.id}): record the finished ticket')} "
                        f"-- {paths}", project)
    return None if code else paths


def merge_cmd(project: Path, t: Ticket, cfg: dict) -> str:
    """Land the ticket branch on base, in two steps that both refuse to guess.

    The base merge runs in the ticket's OWN worktree, so a conflict surfaces in
    the checkout the escalated human is already going to open, and the step
    after it never runs, leaving base untouched. The main checkout then only
    ever fast-forwards, and only while it is actually sitting on `base`: a
    dirty, diverged or elsewhere-parked checkout escalates rather than landing
    the ticket half-way or onto some other branch. Nothing resolves a conflict.

    The leading `git rebase {base}` is the catch-up when the tree allows it,
    and it is what keeps base linear. It may not fail the child: `git rebase`
    refuses a worktree with unstaged changes (`error: cannot rebase: You have
    unstaged changes.`, exit 128) that `git merge` lands. `git rebase --abort`
    restores the branch on any rebase failure, and the unchanged merge below
    decides. After a successful rebase the merge prints `Already up to date.`.
    """
    # Only one merge runs at a time (see `start()`), so the base this reads is
    # the base the fast-forward below lands on, and nothing races the main
    # checkout's index.lock either.
    base = shlex.quote(base_ref(cfg))
    proj = shlex.quote(str(project))
    return (f"git rebase {base} || git rebase --abort 2>/dev/null\n"
            f"git merge --no-edit {base} || exit 1\n"
            f"head=$(git -C {proj} rev-parse --abbrev-ref HEAD) || exit 1\n"
            f'[ "$head" = {base} ] || {{ echo "main checkout is parked on'
            f' $head, not the base branch -- refusing to land"; exit 1; }}\n'
            f"git -C {proj} merge --ff-only {shlex.quote(t.branch)}\n")


def unwind_cmd(sha: str) -> str:
    """Discard every commit after `sha` on the current branch.

    `sha` is the branch tip recorded when the cheap route's `implementing` was
    spawned, so everything after it is that stage's own work. The ancestor
    guard is what stops a stale or hand-edited value from resetting the branch
    onto an unrelated commit instead of refusing. `git clean -fd` runs because
    an untracked file `implementing` left behind survives `git reset --hard`
    and can make `test_file` pass at the very gate this repair exists to
    satisfy; `-x` is left off so ignored build artefacts, not the cheap
    route's work, survive.
    """
    q = shlex.quote(sha)
    return (f'git merge-base --is-ancestor {q} HEAD || {{ echo "{q} is not an '
            f'ancestor of HEAD -- refusing to unwind"; exit 1; }}\n'
            f"git log --oneline {q}..HEAD\n"
            f"git reset --hard {q} && git clean -fd\n")


def note_wait(t: Ticket, held: tuple[str, str] | None) -> None:
    """Record why `files_conflict` is holding `t`, so `ls` can say so.

    Advisory display only, never read back as control flow. Writes only when
    the reason changes -- `ticket_rows()` computes `stale` from this file's
    mtime, and a write every tick would hide a stuck ticket forever.
    """
    if held is None:
        if t.extra.pop("waiting", None) is not None:
            t.save()
        return
    prev = t.extra.get("waiting")
    if isinstance(prev, dict) and prev.get("on") == held[0] and prev.get("file") == held[1]:
        return
    t.extra["waiting"] = {"on": held[0], "file": held[1], "since": now().isoformat()}
    t.save()


def start(project: Path, path: Path, hcfg: dict, inflight: dict,
          poller: Poller | None = None, emit=noop) -> tuple[bool, dict | None]:
    """Try to move one ticket forward.

    Returns (did_work, record). `did_work` is True for a synchronous advance as
    well as a spawn -- `--once` drains the queue, and a pass that only advanced
    `new -> triage` has still done work worth looping on.
    """
    t = Ticket.load(path)
    stage, tid = t.stage, t.id

    def bail(reason: str) -> tuple[bool, None]:
        """Escalate before any child exists.

        The `stage_end` matters: view 1 is `escalated / stage_end` per stage,
        and these four paths emitted only the numerator, so one completed
        `implementing` run plus two lease-expiry escalations rendered `200%`.
        An attempt that ended before it could spawn is still an attempt at
        this stage -- the same reasoning that makes `finish()` emit
        `stage_end` for a failed Tier A gate, even though it spawns a gate
        child rather than an agent.
        """
        escalate(t, reason, emit)
        emit("stage_end", ticket=tid, stage=stage, result="escalated",
             next_stage="escalated", exit_code=None)
        return True, None

    bad = t.errors()
    if bad and stage not in TERMINAL:
        return bail("unusable frontmatter: " + "; ".join(bad))

    if stage in HUMAN_GATES:
        return False, None

    if stage in TERMINAL:
        # an escalated ticket keeps its worktree: the uncommitted state is the
        # evidence the human was escalated to look at
        if stage in CLEANUP_STAGES and worktree(project, t.frontmatter()).is_dir():
            try:
                cfg = project_config(project)
            except (PipelineError, ValueError) as e:
                print(f"  {tid}: no worktree_teardown ({e})")
                cfg = {}
            drop_worktree(project, t.frontmatter(), cfg)
            print(f"  cleaned worktree for {tid} ({stage})")
            return True, None
        return False, None

    # A live lease held by a dead pid is a daemon that was killed, not work in
    # progress. Falling through here charges `lease_expiries` and takes the
    # existing respawn path, instead of parking the ticket for 30 minutes.
    if t.lease_active() and holder_alive((t.lease or {}).get("holder")):
        return False, None

    if (t.lease or {}).get("expires"):  # expired (or orphaned) -> crash recovery
        n = t.counters.get("lease_expiries", 0) + 1
        t.counters["lease_expiries"] = n
        if n >= MAX_ATTEMPTS:
            return bail("lease expired twice")
        t.append(stage, "note", f"lease expired, respawning `{stage}` fresh (expiry {n})")
        t.release_lease()
        t.save()  # persist now: later returns skip the save

    if stage == "new":
        advance(project, t, "new", "dispatcher pickup", emit, agent=False)
        return True, None

    held = conflict_holder(t.frontmatter(),
                           [r["meta"].frontmatter() for r in inflight.values()])
    note_wait(t, held)  # also clears a stale reason once the holder is gone
    if held is not None:
        return False, None  # wait, do not fail -- cheap ordering without a scheduler

    try:
        cfg = project_config(project)
    except PipelineError as e:
        # one unconfigured project must not take the loop -- and every other
        # ticket's agent -- down with it
        return bail(str(e))
    drain_all(inflight)      # `git worktree add` + worktree_setup both block
    wt = ensure_worktree(project, t.frontmatter(), cfg)
    if wt is None:
        return bail("could not create a worktree")

    def child(cmd: str, kind: str, env: dict | None = None) -> tuple[bool, dict]:
        # a child that outlives the tick must lease exactly like an agent, or a
        # crash mid-command leaves nothing for the expiry path to recover
        t.take_lease(f"{stage}-{os.getpid()}")
        t.save()
        try:
            rec = spawn_command(project, wt, tid, stage, cmd, kind, emit, env=env)
        except OSError as e:
            return bail(f"spawn failed: {e}")
        # `meta` is not optional: start()'s own overlap check reads it off every
        # in-flight record
        rec["path"], rec["tid"], rec["meta"], rec["before"] = path, tid, t, None
        rec["before_main"] = None
        return True, rec

    if stage == "verifying":
        return child(format_tests_cmd(cfg["test_suite"], t.tests or [""]), "suite")

    if stage == "merging":
        if any(r.get("kind") == "merge" for r in inflight.values()):
            # Merges are serialised, not ordered by `files_declared`: two
            # DISJOINT tickets reaching `merging` in one tick both `git merge
            # base` against the same base, and the first `--ff-only` to land
            # moves base under the second, whose merge then fails. That is a
            # lost update, not the index.lock race the old comment named, and
            # `transition("merging","fail")` escalates with no retry -- a
            # fully verified ticket parked for a human over a merge that
            # succeeds a tick later. Wait, exactly like `files_conflict` does.
            return False, None
        return child(merge_cmd(project, t, cfg), "merge")

    if stage == "revalidating":
        # the Tier A facts were recorded before the ticket sat at the human
        # gate; base has moved since. Rebase first, re-gate in finish().
        base = base_ref(cfg)
        out = project / ".project" / "logs" / f"{tid}-gate-{uuid.uuid4().hex[:8]}.json"
        ok, rec = child(regate_cmd(project, tid, base, out), "regate", env=dict(os.environ))
        if rec is not None:
            rec["base"] = base
            rec["findings"] = out
        return ok, rec

    if stage == "unwinding":
        head = str(t.extra.get("cheap_route_head") or "")
        if not SAFE_SHA.match(head):
            return bail(f"cannot unwind the cheap route: cheap_route_head is "
                        f"{head!r}, not a commit sha")
        return child(unwind_cmd(head), "unwind")

    if stage == "plan-validation":
        if not t.counters.get("gate_ok"):
            # the Tier A gate runs as a spawned child: run inline, `gate()`'s
            # `test_one` stalled the loop for its whole duration, so the
            # daemon answered no client request and drained no child's pipe.
            out = project / ".project" / "logs" / f"{tid}-gate-{uuid.uuid4().hex[:8]}.json"
            ok, rec = child(gate_cmd(project, tid, out), "gate", env=dict(os.environ))
            if rec is not None:
                rec["findings"] = out
            return ok, rec
        # a Tier A PASS is a phase of this stage, not an ended attempt --
        # consume it and fall through to the Tier B agent spawn below
        t.counters.pop("gate_ok", None)

    if stage == "implementing" and t.counters.get("cheap_route") and not t.extra.get("cheap_route_head"):
        # the last moment `counters["cheap_route"]` is still set -- it is
        # popped at `("implementing", "ok")` -- so this is the last chance to
        # record which commits are the cheap route's own. The `not
        # t.extra.get(...)` guard keeps a lease-expiry respawn from
        # re-recording a tip that already carries the route's own commits.
        code, out = run_cmd("git rev-parse HEAD", wt)
        head = out.strip()
        if code == 0 and SAFE_SHA.match(head):
            t.extra["cheap_route_head"] = head

    t.take_lease(f"{stage}-{os.getpid()}")
    t.save()

    # Strip before the baseline: a snapshot taken while the file is still
    # there would read its own removal as `wrote-in-readonly`.
    strip_settings_sources(wt)
    before = tree_snapshot(wt) if is_readonly(stage, project) else None  # before Popen
    before_main = dirty_snapshot(project) if is_readonly(stage, project) else None
    drop_result(project, tid)  # L3: never let a previous run's verdict be reused
    try:
        rec = spawn(project, wt, tid, stage, hcfg, poller, emit)
    except (PipelineError, OSError) as e:
        # The lease is already taken. Letting this out leaves the ticket
        # holding a lease whose holder pid is the live dispatcher, so nothing
        # retries it until the lease expires 30 minutes later. A harness that
        # cannot register hooks, or a fork that cannot get a pid, is a fact
        # about this ticket's stage; escalate the ticket, keep the loop.
        return bail(str(e))
    rec["path"] = path
    rec["tid"] = tid
    rec["meta"] = t   # the pre-spawn snapshot: control fields come back from here
    rec["before"] = before
    rec["before_main"] = before_main
    return True, rec


def log_tail(rec: dict, n: int = 1500) -> str:
    """The tail of a child's log, decoded the way `pump()` decodes it.

    `read_text()` here decodes STRICT utf-8 over output we did not write: one
    stray byte from `git merge` or a test runner raised `UnicodeDecodeError`
    inside `finish()`, `reap()` caught and printed it, and `advance()` never
    ran -- so the lease `child()` took was held until it expired.
    """
    try:
        return rec["log"].read_bytes()[-n:].decode("utf-8", "replace")
    except OSError as e:
        return f"(log unreadable: {e})"


def finish_child(project: Path, rec: dict, label: str, emit=noop) -> str:
    """Apply a dispatcher-owned child's verdict: its exit code, nothing else."""
    close_child(rec)
    code = rec["proc"].returncode
    result = "ok" if code == 0 else "fail"
    advance(project, Ticket.load(rec["path"]), result,
            f"{label} exit {code}\n```\n{log_tail(rec)}\n```", emit, agent=False)
    return result


def finish_suite(project: Path, rec: dict, emit=noop) -> str:
    """The suite's exit code, and then the fence check.

    `ok` PARKS at `awaiting-merge`; only `clean` reaches `merging`. The
    polarity is the guard: a git failure, an unparseable diff or a bug in
    `fenced_touches()` all yield `ok`, and a human looks at the diff. A guard
    that fails open is not a guard.
    """
    close_child(rec)
    code = rec["proc"].returncode
    t = Ticket.load(rec["path"])
    if code != 0:
        advance(project, t, "fail",
                f"regression suite exit {code}\n```\n{log_tail(rec)}\n```",
                emit, agent=False)
        return "fail"
    try:
        hits = fenced_touches(rec["wt"], base_ref(project_config(project)))
    except Exception as e:
        hits = [f"fence check failed ({e.__class__.__name__}: {e})"]
    if not hits:
        advance(project, t, "clean",
                "regression suite passed; the diff touches no fenced code",
                emit, agent=False)
        return "clean"
    advance(project, t, "ok",
            "regression suite passed, but the diff touches fenced code:\n"
            + "\n".join(f"- `{h}`" for h in hits)
            + f"\n\n`CLAUDE.md` requires a human to see this diff before it "
              f"lands. `pipeline approve {rec['tid']}` lands it; "
              f"`pipeline resume {rec['tid']} --stage planning` sends it back.",
            emit, agent=False)
    return "ok"


def read_findings(rec: dict, code: int) -> tuple[bool, list[str]]:
    """The gate child's verdict, read back from the `--findings` file its
    `pipeline gate` wrote. Fails closed, like `finish_suite()`: a child that
    exited without a readable, consistent file did not run the gate, and
    reporting that as a pass would send an ungated plan to a human."""
    path = Path(rec["findings"])
    try:
        try:
            data = json.loads(path.read_text())
        finally:
            path.unlink(missing_ok=True)
        ok, failures = data["ok"], data["findings"]
    except Exception as e:
        return False, [f"gate child exit {code} left no readable findings "
                        f"({e.__class__.__name__}: {e})\n```\n{log_tail(rec)}\n```"]
    if ok != (code == 0):
        return False, [f"gate child exit {code} disagrees with its findings "
                        f"file (ok={ok})\n```\n{log_tail(rec)}\n```"]
    return ok, failures


def gate_result(ok: bool, failures: list[str], stage: str) -> str:
    """The verdict string a Tier A gate's outcome charges. Only `plan-validation`
    splits `fail` into three: `structural` findings keep `fail`, an all-
    `environment` list of findings (the suite red on base too, TICKET-089)
    returns `environment`, and anything else is `bad-plan`. `revalidating`
    always gets `fail`, because `("revalidating", "bad-plan")` and
    `("revalidating", "environment")` are both unknown pairs that would
    escalate a stale plan instead of charging `stale_regate` (DEC-029)."""
    if ok:
        return "ok"
    if stage != "plan-validation":
        return "fail"
    if environment_only(failures):
        return "environment"
    if not structural_only(failures):
        return "bad-plan"
    return "fail"


def finish_gate(project: Path, rec: dict, emit=noop) -> str:
    """Apply the Tier A gate child's verdict. A PASS at `plan-validation` is a
    phase of the stage, not an ended attempt: it is recorded in
    `counters["gate_ok"]` and consumed by the next `start()`, which spawns the
    Tier B agent. `finish()` skips `stage_end` for that case (see `GATE_PASS`),
    or one `plan-validation` run would put two rows in view 1's denominator."""
    close_child(rec)
    code = rec["proc"].returncode
    ok, failures = read_findings(rec, code)
    emit("gate", ticket=rec["tid"], stage=rec["stage"],
         verdict="pass" if ok else "fail", findings=failures)
    t = Ticket.load(rec["path"])
    prefix = "re-gated after rebasing onto base" if rec.get("base") else "Tier A gate"
    note = f"{prefix}: passed" if ok else (
        f"{prefix} failed:\n" + "\n".join(f"- {f}" for f in failures))
    if ok and t.stage == "plan-validation":
        t.counters["gate_ok"] = 1
        t.release_lease()
        t.save()
        return GATE_PASS
    res = gate_result(ok, failures, t.stage)
    advance(project, t, res, note, emit, agent=False)
    return res


def finish_regate(project: Path, rec: dict, emit=noop) -> str:
    """A rebase onto current base, then the Tier A gate again -- an approval is
    only as good as the tree it was given against. `REBASE_FAILED` (exit 3)
    means the rebase conflicted; any other exit is the gate's own verdict,
    decided by `finish_gate()` so one function judges every gate."""
    close_child(rec)
    code = rec["proc"].returncode
    t = Ticket.load(rec["path"])
    if code == REBASE_FAILED:
        # a conflicting rebase is repaired by discarding the branch's
        # commits, not by resolving them: abort the rebase, then reset the
        # branch onto base. Safe only because `revalidating` runs before
        # `implementing` -- the branch carries triage's test commit and
        # nothing else.
        base = shlex.quote(rec.get("base") or "main")
        rc, repair = run_cmd(f"git rebase --abort && git log --oneline {base}..HEAD",
                              rec["wt"])
        if rc == 0:
            rc, reset_out = run_cmd(f"git reset --hard {base}", rec["wt"])
            repair += reset_out
        Path(rec["findings"]).unlink(missing_ok=True)
        if rc != 0:
            escalate(t, f"rebase onto base conflicted (exit {code}) and the "
                        f"recut back onto base failed too\n```\n"
                        f"{log_tail(rec)}\n{repair}\n```", emit)
            return "escalated"
        advance(project, t, "conflict",
                f"rebase onto base conflicted; branch recut from base:\n```\n"
                f"{log_tail(rec)}\n{repair}\n```", emit, agent=False)
        return "conflict"
    return finish_gate(project, rec, emit)


def finish(project: Path, rec: dict, emit=noop) -> None:
    """`_finish` decides; this only records what it decided. Splitting them is
    what lets one `stage_end` cover every exit path without a dozen emit calls
    scattered through the branches."""
    try:
        result = _finish(project, rec, emit)
    finally:
        # whatever _finish did or raised, this child's fd leaves the poller
        close_child(rec)
    if result == GATE_PASS:
        # a Tier A pass is a phase of `plan-validation`, not an ended attempt
        # -- a `stage_end` here would put two rows in view 1's denominator
        # for one run
        return
    try:
        nxt = Ticket.load(rec["path"]).stage
    except Exception:
        nxt = None
    proc = rec.get("proc")
    emit("stage_end", ticket=rec["tid"], stage=rec["stage"],
         session=rec.get("session"), result=result, next_stage=nxt,
         exit_code=proc.returncode if proc is not None else None)
    if rec.get("mode") == "interactive" and rec.get("session"):
        # a headless stage's `result` event is authoritative and already in
        # the log; an interactive one has no such event, so its cost comes
        # from the transcript here -- and only here, or every merged ticket
        # would be billed twice. Wrapped for the same reason `event_sink` is.
        try:
            for u in usage_events(rec["session"]):
                emit("usage", ticket=rec["tid"], stage=rec["stage"],
                     session=rec["session"], **u)
        except Exception as e:
            print(f"  {rec['tid']}: usage not recorded "
                  f"({e.__class__.__name__}: {e})")


def _finish(project: Path, rec: dict, emit=noop) -> str:
    # BEFORE anything agent-specific: the suite's verdict is its exit code, and
    # falling through to read_result() would let a `.result` an earlier stage's
    # agent left behind speak for the test run. It also skips the tamper check,
    # the tree snapshot and apply_claims -- none of which have an agent to check.
    if rec.get("kind") == "suite":
        return finish_suite(project, rec, emit)
    # a merge is the dispatcher's own child too: its verdict is the exit code of
    # git, and `fail` means a conflict nobody may auto-resolve. Its worktree
    # stays -- `escalated` is not in CLEANUP_STAGES.
    if rec.get("kind") == "merge":
        return finish_child(project, rec, "merge", emit)
    # a re-gate is two steps, so its verdict is not the exit code alone: the
    # rebase only has to succeed for the gate to have a tree worth judging
    if rec.get("kind") == "regate":
        return finish_regate(project, rec, emit)
    # a Tier A gate, spawned instead of run inline -- see `gate_cmd()`
    if rec.get("kind") == "gate":
        return finish_gate(project, rec, emit)
    # the reset's exit code is the whole verdict, like the merge
    if rec.get("kind") == "unwind":
        return finish_child(project, rec, "unwind", emit)

    close_child(rec)
    if rec.get("prompt"):
        rec["prompt"].unlink(missing_ok=True)
    if rec.get("settings"):
        rec["settings"].unlink(missing_ok=True)
    if rec.get("mcp"):
        rec["mcp"].unlink(missing_ok=True)
    path, tid, stage = rec["path"], rec["tid"], rec["stage"]
    session, log, wt = rec["session"], rec["log"], rec["wt"]

    res = read_result(project, tid, keep=True)
    agent = Ticket.load(path)

    # The agent had write access to this file. Its prose sections are its own;
    # its frontmatter is not. Every field is restored from the snapshot taken
    # before the spawn, so "an agent never writes `stage`" is enforced by the
    # dispatcher rather than requested in a prompt.
    snap = rec["meta"]
    owned = snap.frontmatter()
    tampered = {k: v for k, v in agent.frontmatter().items()
                if k in CONTROL_FIELDS and v != owned.get(k)}
    t = replace(snap, body=agent.body)

    t.append(stage, "session", f"`{stage}` ran as session `{session}`\n"
                               f"- replay: `claude --resume {session}`\n"
                               f"- log: `{log.relative_to(project)}`"
                               + cost_report(rec), session=session)
    t.extra["last_session"] = {"stage": stage, "id": session,
                               "log": str(log.relative_to(project)),
                               "cost_usd": rec.get("cost_usd")}

    if tampered:
        drop_result(project, tid)
        escalate(t, f"`{stage}` edited dispatcher-owned frontmatter: "
                    + ", ".join(f"{k}={v!r}" for k, v in tampered.items()), emit)
        return "tampered"

    if rec["before"] is not None and tree_snapshot(wt) != rec["before"]:
        escalate(t, f"read-only stage `{stage}` modified the working tree", emit)
        return "wrote-in-readonly"

    if rec.get("before_main") is not None and dirty_snapshot(project) != rec["before_main"]:
        escalate(t, f"read-only stage `{stage}` modified the main checkout outside `.project/`", emit)
        return "wrote-in-readonly"

    if res is None:
        # A budget kill is not a crash: the same prompt against the same
        # tree spends the same cap and stops at the same point, so a respawn
        # buys nothing. The bound is one, and there is no second attempt to
        # charge against.
        if rec.get("terminal_reason") == "budget_exhausted":
            t.counters["budget_kills"] = t.counters.get("budget_kills", 0) + 1
            cap = rec.get("cap") or "?"
            escalate(t, f"`{stage}` was killed at its ${cap} budget cap "
                        f"(--max-budget-usd) before it wrote a .result "
                        f"sidecar; a respawn spends the same cap and stops "
                        f"at the same point", emit)
            return "budget-exhausted"
        # L4: a harness that dies before writing a result must not respawn
        # forever. Same budget as every other bounded loop.
        n = t.counters.get("no_result", 0) + 1
        t.counters["no_result"] = n
        if n >= MAX_ATTEMPTS:
            escalate(t, f"`{stage}` wrote no .result sidecar {n} times", emit)
            return "no-result"
        t.release_lease()
        t.append(stage, "note",
                 f"`{stage}` wrote no .result sidecar (attempt {n}) -- will respawn")
        t.save()
        return "no-result"

    # claims are validated BEFORE they are adopted: a hostile `test_file` in a
    # sidecar must never reach the ticket file, escalated or not
    claimed = t.frontmatter()
    apply_claims(claimed, stage, res)
    bad = validate_meta(claimed)
    if bad:
        drop_result(project, tid)
        escalate(t, "`.result` claimed an unusable value: " + "; ".join(bad), emit)
        return "bad-claim"
    t.test_file, t.files_declared = claimed["test_file"], claimed["files_declared"]
    t.counters["no_result"] = 0
    t.save()
    drop_result(project, tid)

    result = res.get("result", "fail")
    # Tier B judges the plan's content and has no structural half, so its
    # `fail` is a bad plan by definition. The dispatcher classifies rather
    # than the prompt: a stage that could pick `fail` over `bad-plan` would
    # be choosing its own budget (invariant 1).
    if stage == "plan-validation" and result == "fail":
        result = "bad-plan"
    advance(project, t, result, res.get("summary", ""), emit)
    return result


def end_interactive(project: Path, inflight: dict) -> None:
    """An interactive child is a REPL: it ends when a human types `/exit`, and
    writing the `.result` sidecar does not end it. `finish()` fires on
    `proc.poll()`, so without this a `planning` session that had already
    reported its verdict sat at its prompt holding the lease until it expired
    -- twice -- and the ticket escalated with the agent's plan already written.

    The sidecar IS the exit condition, so treat it as one. SIGTERM here, and
    the ordinary `reap()` below collects it on this pass or the next.
    """
    for tid, rec in inflight.items():
        if (rec.get("mode") == "interactive" and rec["proc"].poll() is None
                and result_file(project, tid).is_file()):
            print(f"  {tid}: `{rec['stage']}` reported its result; ending the session")
            rec["proc"].terminate()


def reap(project: Path, inflight: dict, emit=noop) -> bool:
    end_interactive(project, inflight)
    done = [tid for tid, rec in inflight.items() if rec["proc"].poll() is not None]
    for tid in done:
        rec = inflight.pop(tid)
        drain_all(inflight)   # `finish()` may run git for a repair (finish_regate)
        try:
            finish(project, rec, emit)
        except Exception as e:
            # one unparseable ticket must not take the dispatcher down and
            # strand every other agent's lease for 30 minutes
            print(f"  {tid}: finish failed ({e.__class__.__name__}: {e})")
    return bool(done)


def shut_down(project: Path, inflight: dict) -> None:
    """Terminate children and release their leases. Without this an interrupted
    dispatcher leaves agents writing into worktrees it no longer tracks, and the
    lease expiry later spawns a SECOND agent onto the same stage."""
    for tid, rec in list(inflight.items()):
        proc = rec["proc"]
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)   # a PtyProc is reaped here or never
                except subprocess.TimeoutExpired:
                    pass
        close_child(rec)
        if rec.get("prompt"):
            rec["prompt"].unlink(missing_ok=True)
        if rec.get("settings"):
            rec["settings"].unlink(missing_ok=True)
        if rec.get("mcp"):
            rec["mcp"].unlink(missing_ok=True)
        try:
            t = Ticket.load(rec["path"])
            t.release_lease()
            t.append(rec["stage"], "note",
                     f"`{rec['stage']}` was interrupted; lease released")
            t.save()
        except Exception:
            pass
        print(f"  stopped {tid} ({rec['stage']})")
    inflight.clear()


def _start_cap(project: Path, max_parallel: int) -> int:
    """A project's `max_parallel` lowers the daemon `-j`, it never raises it.

    `project_max_parallel()` can raise `PipelineError` on a bad value, and
    `project_config()` underneath it can also raise `tomllib.TOMLDecodeError`
    (a `ValueError`) on a malformed `.project/pipeline.toml`. `run()` catches
    per tick since TICKET-086, and this local catch stays because it keeps
    the fault out of the tick and names the offending value, where the
    generic catch names only the exception class. A bad value is printed and
    ignored instead, falling back to `max_parallel` -- exactly the behaviour
    before this key existed.
    """
    try:
        cap = project_max_parallel(project)
    except (PipelineError, ValueError) as e:
        print(f"  {project}: ignoring max_parallel ({e})")
        return max_parallel
    if cap is None:
        return max_parallel
    return min(max_parallel, cap)


def tick(project: Path, hcfg: dict, inflight: dict, max_parallel: int = 3,
         poller: Poller | None = None, emit=noop, stopping=lambda: False) -> bool:
    """One pass over one project: reap what finished, start what can start.
    The whole loop body, so the daemon can run it for many projects and
    `pipeline run` can run it for one. The start cap is the smaller of the
    `-j` argument and the project's own `max_parallel` key."""
    worked = reap(project, inflight, emit)
    tickets = all_tickets(project)
    cap = _start_cap(project, max_parallel) if tickets else max_parallel
    for path in tickets:
        if stopping() or len(inflight) >= cap:
            break
        try:
            tid = Ticket.load(path).id
        except Exception as e:
            print(f"  skipping {path.name}: {e}")  # loudly, not silently
            continue
        if tid in inflight:
            continue
        try:
            did_work, rec = start(project, path, hcfg, inflight, poller, emit)
        except Exception as e:
            # invariant 6, the other half: one broken ticket must not take the
            # loop -- and every other agent's lease -- down with it. A lease
            # this ticket took before raising expires on the ordinary path and
            # is charged, so the retry stays bounded.
            print(f"  {path.stem}: start failed ({e.__class__.__name__}: {e})")
            continue
        worked = worked or did_work
        if rec:
            inflight[rec["tid"]] = rec
    return worked


def _stopper():
    """SIGINT/SIGTERM -> a flag, plus a pipe fd that wakes `select()`.

    `selectors.select` retries on EINTR (PEP 475), so a signal alone would
    leave the loop asleep until its timeout. The self-pipe is what makes
    `pipeline stop` return in milliseconds instead of `interval` seconds.

    Returns (is_stopping, read_fd, write_fd); the caller closes both fds.
    """
    state = {"stop": False}
    r, w = os.pipe()
    os.set_blocking(w, False)
    os.set_blocking(r, False)
    signal.set_wakeup_fd(w)

    def on_signal(signum, _frame):
        state["stop"] = True
        print(f"\n  signal {signum}: stopping")
    old_handlers = {sig: signal.getsignal(sig)
                    for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in old_handlers:
        signal.signal(sig, on_signal)
    return (lambda: state["stop"]), r, w, old_handlers


def _restore_signals(old_handlers: dict) -> None:
    """Undoes `_stopper()`'s handlers. A library call that returns must not
    leave the process's signal disposition changed -- without this, every
    `pty.fork()` child spawned after `run()`/`serve()` returns inherits
    `on_signal` and never dies on the SIGTERM `end_interactive()` sends it."""
    for sig, handler in old_handlers.items():
        signal.signal(sig, handler)


def _harness_reloader(name: str):
    """Re-reads `<name>.toml` on every call instead of once per process, so a
    harness change that merges mid-run reaches the next tick. The first read
    is unguarded -- an unknown harness must still fail before the caller
    takes the project lock. Every later read keeps the last good dict on any
    exception, because a per-tick read turns a broken or half-written
    `.toml` into a runtime fault where today it is only a startup fault.
    `run()` catches per tick since TICKET-086, and this local catch stays
    because it keeps the fault out of the tick and names the offending
    file, where the generic catch names only the exception class. A warning
    prints only when its message changes, so a file that stays broken does
    not print once a second."""
    cfg = harness(name)
    state = {"cfg": cfg, "err": None}

    def reload() -> dict:
        try:
            new = harness(name)
        except Exception as e:
            msg = f"{e.__class__.__name__}: {e}"
            if msg != state["err"]:
                print(f"  harness {name}: keeping last good config ({msg})")
            state["err"] = msg
            return state["cfg"]
        if new != state["cfg"]:
            print(f"  harness {name}: reloaded")
        state["cfg"], state["err"] = new, None
        return state["cfg"]

    return reload


def _mtime(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return -1.0            # a module file that vanished is a change too


def _source_watcher():
    """The mtimes of the loaded `pipeline` modules, sampled once at the top of
    a loop. `_harness_reloader()` does this for harness *data*; a Python module
    already imported does not change because its file did, so the loop reports
    and ends instead. Never `importlib.reload()`: the supervisor holds live
    child records, an open SQLite handle and registered signal handlers, and
    reloading swaps classes out from under objects that already exist.

    Code only. Stage prompts are read per spawn and the harness `.toml` per
    tick (DEC-028); ending the loop for those would undo that."""
    mods = {n: m.__file__ for n, m in list(sys.modules.items())
            if n.startswith("pipeline") and getattr(m, "__file__", None)}
    snap = {n: _mtime(f) for n, f in mods.items()}

    def changed() -> str | None:
        for n, f in mods.items():
            if _mtime(f) != snap[n]:
                return n
        return None

    return changed


def run(project: Path, once: bool, interval: int, harness_name: str,
        max_parallel: int = 3, store=None) -> None:
    """Standalone: the daemon minus the socket server. One supervisor
    implementation, two entry points -- the daemon is an accelerator, never a
    dependency. `store` is optional; with none, nothing is recorded and the
    loop is exactly what it was before the daemon existed.

    Every stage runs here, interactive ones included: the bare `Poller` is not
    `attachable` and reports no `watchers()`, so `spawn()` runs those headless
    rather than parking a REPL nobody could reach. Under `serve()` the same
    happens whenever no client is subscribed (see `spawn()` and the README).
    What you lose without the daemon is steering, never progress.
    """
    reload = _harness_reloader(harness_name)
    emit = store.emitter(project) if store is not None else noop
    inflight: dict[str, dict] = {}
    lock = registry.lock(project)
    if lock is None:
        raise PipelineError(
            f"another dispatcher already holds {project}/.project/.lock -- "
            f"two supervisors on one project double-spawn")
    poller = Poller()
    stopping, wake, wake_w, old_handlers = _stopper()
    poller.watch(wake, lambda fd: os.read(fd, 4096))
    stale, moved = _source_watcher(), None

    try:
        while not stopping():
            moved = moved or stale()
            if moved and not inflight:
                print(f"  dispatcher source changed ({moved}) -- ending the "
                      f"loop so a restart runs the merged code")
                return
            try:
                worked = tick(project, reload(), inflight, max_parallel, poller,
                              emit, (lambda: True) if moved else stopping)
            except Exception as e:
                # one failing tick must never reach `finally: shut_down(project,
                # inflight)` and SIGTERM every OTHER ticket's agent -- `serve()`
                # has caught per project since it existed (invariant 6). A test
                # that detects a runaway loop from a fake `tick()` must raise a
                # BaseException subclass or this catch eats it: see
                # test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception
                print(f"  {project}: tick failed ({e.__class__.__name__}: {e})")
                worked = False
            if once and not inflight and not worked:
                return  # --once drains the queue, it does not do a single pass
            poller.poll(1 if inflight else interval)
    finally:
        shut_down(project, inflight)
        signal.set_wakeup_fd(-1)
        _restore_signals(old_handlers)
        poller.close()
        os.close(wake)
        os.close(wake_w)
        lock.close()


def serve(interval: int, harness_name: str, max_parallel: int, store, server,
          once: bool = False) -> None:
    """The one global daemon: every registered project, one select loop.

    Per project it holds a `flock` for as long as it watches it. A project
    somebody else already owns is skipped this tick and retried the next --
    no error, no queue, and no second supervisor.
    """
    # ponytail: orphan from a SIGKILLed daemon can still write .result; upgrade
    # = record child pids, reap on startup. Bounded today: the respawn uses a
    # new session id and drop_result() runs pre-spawn, so the worst case is a
    # stale thread summary.
    reload = _harness_reloader(harness_name)
    states: dict[str, dict] = server.states
    locks: dict[str, object] = {}
    stopping, wake, wake_w, old_handlers = _stopper()
    server.watch(wake, lambda fd: os.read(fd, 4096))
    store.emit("", "daemon_start", pid=os.getpid(), version=__version__,
               socket=str(server.path))
    print(f"pipelined {__version__}: pid {os.getpid()} on {server.path}")
    stale, moved = _source_watcher(), None

    def release(key: str) -> None:
        shut_down(Path(key), states.pop(key, {}))
        fh = locks.pop(key, None)
        if fh is not None:
            fh.close()

    try:
        while not stopping():
            moved = moved or stale()
            if moved and not any(states.values()):
                print(f"  dispatcher source changed ({moved}) -- ending the "
                      f"loop so a restart runs the merged code")
                return
            hcfg = reload()
            wanted = {str(p): p for p in registry.projects()}
            for key in [k for k in states if k not in wanted]:
                print(f"  unregistered: releasing {key}")
                try:
                    release(key)
                except Exception as e:
                    # same reason `tick` is wrapped: one project's teardown
                    # must not strand every other project's leases
                    print(f"  {key}: release failed ({e.__class__.__name__}: {e})")
            worked = False
            for key, proj in wanted.items():
                if key not in states:
                    fh = registry.lock(proj)
                    if fh is None:
                        continue      # another supervisor owns it; try next tick
                    locks[key], states[key] = fh, {}
                    print(f"  watching {key}")
                try:
                    worked |= tick(proj, hcfg, states[key], max_parallel,
                                   server, store.emitter(key),
                                   (lambda: True) if moved else stopping)
                except Exception as e:
                    # one broken project must never take the other projects'
                    # agents down with it
                    print(f"  {key}: tick failed ({e.__class__.__name__}: {e})")
            busy = any(states.values())
            if once and not busy and not worked:
                return
            server.poll(1 if busy else interval)
    finally:
        for key in list(states):
            release(key)
        store.emit("", "daemon_stop", pid=os.getpid(), version=__version__)
        signal.set_wakeup_fd(-1)
        _restore_signals(old_handlers)
        server.close()
        os.close(wake)
        os.close(wake_w)
