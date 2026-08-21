"""The dispatcher loop: claim a ticket, spawn one stateless agent per stage,
reap it, apply its verdict. The state machine decides; this only obeys."""
import fcntl
import os
import re
import shlex
import signal
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

from pipeline import __version__
from pipeline.core import PipelineError
from pipeline.core.config import (compose_prompt, harness, is_readonly,
                                  project_config, render, stage_config,
                                  stage_settings)
from pipeline.core.gate import gate
from pipeline.core.machine import (CLEANUP_STAGES, CONTROL_FIELDS, HUMAN_GATES,
                                   MAX_ATTEMPTS, TERMINAL, apply_claims,
                                   files_conflict, transition)
from pipeline.core.ticket import (Ticket, all_tickets, drop_result,
                                  read_result, record_decision, ticket_path,
                                  tickets_dir, validate_meta)
from pipeline.core.worktree import (drop_worktree, ensure_worktree,
                                    project_env, tree_snapshot, worktree)
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


def advance(project: Path, t: Ticket, result: str, note: str, emit=noop) -> None:
    stage = t.stage
    nxt, counters = transition(stage, result, t.counters, t.klass)
    emit("transition", ticket=t.id, stage=stage, **{"from": stage, "to": nxt,
         "result": result, "counters": counters})
    t.append(stage, "transition", f"**{stage} -> {nxt}** (result: `{result}`)\n\n{note}",
             to=nxt, result=result)
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


PIPE_SZ = 1 << 20   # the usual /proc/sys/fs/pipe-max-size for an unprivileged user


def _widen(fd: int) -> None:
    """Grow the child's stdout buffer from 64K to 1M, best-effort.

    Headroom, not a fix. The loop makes blocking calls -- `gate()` runs the
    project's `test_one`, `ensure_worktree` runs git and `worktree_setup` --
    and for their duration NOTHING drains any pipe. At 64K a chatty agent
    fills up in seconds and blocks in `write()` holding its lease.
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
    cfg = stage_config(stage)
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
    interactive = cfg.get("mode") == "interactive"
    if interactive and poller is None:
        # nothing would drain the master, so the child blocks at a full buffer
        # holding its lease -- and nobody could attach to it anyway
        raise PipelineError(f"`{stage}` is interactive and needs a poller to "
                            f"host its PTY")
    session = str(uuid.uuid4())
    logs = project / ".project" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{tid}-{stage}-{session[:8]}.log"
    prompt = compose_prompt(stage)
    settings = stage_settings(stage, cfg)
    cmd = render(hcfg, cfg, tid=tid, project=project,
                ticket=ticket_path(project, tid),
                result_file=tickets_dir(project) / f"{tid}.result",
                session=session, prompt=prompt, settings=settings,
                key="interactive_cmd" if interactive else "cmd")
    fh = log.open("wb")
    fh.write(f"$ {cmd}\n\n".encode())
    fh.flush()
    env = project_env()
    env["PIPELINE_STAGE"] = stage
    env["PIPELINE_READONLY"] = "0" if cfg.get("write") else "1"
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
        proc = subprocess.Popen(cmd, shell=True, cwd=wt,
                                stdout=subprocess.PIPE if poller else fh,
                                stderr=subprocess.STDOUT, env=env)
        pipe = proc.stdout
    mode = "interactive" if interactive else "batch"
    rec = {"proc": proc, "fh": fh, "prompt": prompt, "settings": settings,
           "session": session, "mode": mode,
           "log": log, "stage": stage, "wt": wt,
           "poller": poller, "pipe": None, "reader": None,
           "screen": None, "writer": None,
           "sink": lambda ev: None}
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


def spawn_command(project: Path, wt: Path, tid: str, stage: str, cmd: str,
                  kind: str = "command", emit=noop) -> dict:
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
    proc = subprocess.Popen(cmd, shell=True, cwd=wt, stdout=fh,
                            stderr=subprocess.STDOUT, env=project_env())
    print(f"  start {tid}: {stage} (script) pid {proc.pid} -> {log.name}")
    emit("stage_start", ticket=tid, stage=stage, model=None, mode=kind,
         pid=proc.pid, log=str(log), wt=str(wt))
    return {"kind": kind, "proc": proc, "fh": fh, "prompt": None,
            "settings": None, "session": None, "mode": kind,
            "log": log, "stage": stage, "wt": wt,
            "poller": None, "pipe": None, "reader": None,
            "sink": lambda ev: None}


def merge_cmd(project: Path, t: Ticket, cfg: dict) -> str:
    """Land the ticket branch on base, in two steps that both refuse to guess.

    The base merge runs in the ticket's OWN worktree, so a conflict surfaces in
    the checkout the escalated human is already going to open, and the step
    after it never runs, leaving base untouched. The main checkout then only
    ever fast-forwards, and only while it is actually sitting on `base`: a
    dirty, diverged or elsewhere-parked checkout escalates rather than landing
    the ticket half-way or onto some other branch. Nothing resolves a conflict.
    """
    # ponytail: two tickets merging in the same tick race on the main
    # checkout's index.lock and the loser escalates spuriously. Fails safe --
    # nothing lands half-merged -- so serialise merges only if it shows up.
    base = shlex.quote(str(cfg.get("base", "main")))
    proj = shlex.quote(str(project))
    return (f"git merge --no-edit {base} || exit 1\n"
            f"head=$(git -C {proj} rev-parse --abbrev-ref HEAD) || exit 1\n"
            f'[ "$head" = {base} ] || {{ echo "main checkout is parked on'
            f' $head, not the base branch -- refusing to land"; exit 1; }}\n'
            f"git -C {proj} merge --ff-only {shlex.quote(t.branch)}\n")


def start(project: Path, path: Path, hcfg: dict, inflight: dict,
          poller: Poller | None = None, emit=noop) -> tuple[bool, dict | None]:
    """Try to move one ticket forward.

    Returns (did_work, record). `did_work` is True for a synchronous advance as
    well as a spawn -- `--once` drains the queue, and a pass that only advanced
    `new -> triage` has still done work worth looping on.
    """
    t = Ticket.load(path)
    stage, tid = t.stage, t.id

    bad = t.errors()
    if bad and stage not in TERMINAL:
        escalate(t, "unusable frontmatter: " + "; ".join(bad), emit)
        return True, None

    if stage in HUMAN_GATES:
        return False, None

    if stage in TERMINAL:
        # an escalated ticket keeps its worktree: the uncommitted state is the
        # evidence the human was escalated to look at
        if stage in CLEANUP_STAGES and worktree(project, t.frontmatter()).is_dir():
            drop_worktree(project, t.frontmatter())
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
            escalate(t, "lease expired twice", emit)
            return True, None
        t.append(stage, "note", f"lease expired, respawning `{stage}` fresh (expiry {n})")
        t.release_lease()
        t.save()  # persist now: later returns skip the save

    if stage == "new":
        advance(project, t, "new", "dispatcher pickup", emit)
        return True, None

    if files_conflict(t.frontmatter(),
                      [r["meta"].frontmatter() for r in inflight.values()]):
        return False, None  # wait, do not fail -- cheap ordering without a scheduler

    try:
        cfg = project_config(project)
    except PipelineError as e:
        # one unconfigured project must not take the loop -- and every other
        # ticket's agent -- down with it
        escalate(t, str(e), emit)
        return True, None
    drain_all(inflight)      # `git worktree add` + worktree_setup both block
    wt = ensure_worktree(project, t.frontmatter(), cfg)
    if wt is None:
        escalate(t, "could not create a worktree", emit)
        return True, None

    def child(cmd: str, kind: str) -> tuple[bool, dict]:
        # a child that outlives the tick must lease exactly like an agent, or a
        # crash mid-command leaves nothing for the expiry path to recover
        t.take_lease(f"{stage}-{os.getpid()}")
        t.save()
        rec = spawn_command(project, wt, tid, stage, cmd, kind, emit)
        # `meta` is not optional: start()'s own overlap check reads it off every
        # in-flight record
        rec["path"], rec["tid"], rec["meta"], rec["before"] = path, tid, t, None
        return True, rec

    if stage == "verifying":
        return child(cfg["test_suite"], "suite")

    if stage == "merging":
        return child(merge_cmd(project, t, cfg), "merge")

    if stage == "revalidating":
        # the Tier A facts were recorded before the ticket sat at the human
        # gate; base has moved since. Rebase first, re-gate in finish().
        return child(f"git rebase {shlex.quote(str(cfg.get('base', 'main')))}",
                     "regate")

    if stage == "plan-validation":
        # ponytail: `gate()` runs the project's `test_one` synchronously, and
        # for its duration no pipe is drained -- a very chatty agent can still
        # fill 1M and block. Upgrade = run the gate as a spawned child like
        # `verifying` does, which is a `DISPATCHER_STAGES` change, not a
        # daemon one.
        drain_all(inflight)
        ok, failures = gate(project, tid, wt)
        emit("gate", ticket=tid, stage=stage,
             verdict="pass" if ok else "fail", findings=failures)
        t = Ticket.load(path)  # the gate wrote its findings to the thread
        if not ok:
            advance(project, t, "fail",
                    "Tier A gate failed:\n" + "\n".join(f"- {f}" for f in failures),
                    emit)
            return True, None

    t.take_lease(f"{stage}-{os.getpid()}")
    t.save()

    before = tree_snapshot(wt) if is_readonly(stage) else None  # before Popen
    drop_result(project, tid)  # L3: never let a previous run's verdict be reused
    rec = spawn(project, wt, tid, stage, hcfg, poller, emit)
    rec["path"] = path
    rec["tid"] = tid
    rec["meta"] = t   # the pre-spawn snapshot: control fields come back from here
    rec["before"] = before
    return True, rec


def finish_child(project: Path, rec: dict, label: str, emit=noop) -> str:
    """Apply a dispatcher-owned child's verdict: its exit code, nothing else."""
    close_child(rec)
    code = rec["proc"].returncode
    result = "ok" if code == 0 else "fail"
    advance(project, Ticket.load(rec["path"]), result,
            f"{label} exit {code}\n```\n{rec['log'].read_text()[-1500:]}\n```", emit)
    return result


def finish_regate(project: Path, rec: dict, emit=noop) -> str:
    """A rebase onto current base, then the Tier A gate again -- an approval is
    only as good as the tree it was given against."""
    close_child(rec)
    code = rec["proc"].returncode
    t = Ticket.load(rec["path"])
    if code != 0:
        # same rule as a merge conflict: never auto-resolved, never retried.
        # The half-rebased worktree stays -- `escalated` is not in CLEANUP_STAGES.
        escalate(t, f"rebase onto base conflicted (exit {code})\n```\n"
                    f"{rec['log'].read_text()[-1500:]}\n```", emit)
        return "escalated"
    ok, failures = gate(project, rec["tid"], rec["wt"])
    emit("gate", ticket=rec["tid"], stage=rec["stage"],
         verdict="pass" if ok else "fail", findings=failures)
    t = Ticket.load(rec["path"])  # the gate wrote its findings to the thread
    advance(project, t, "ok" if ok else "fail",
            "re-gated after rebasing onto base:\n"
            + ("- clean" if ok else "\n".join(f"- {f}" for f in failures)), emit)
    return "ok" if ok else "fail"


def finish(project: Path, rec: dict, emit=noop) -> None:
    """`_finish` decides; this only records what it decided. Splitting them is
    what lets one `stage_end` cover every exit path without a dozen emit calls
    scattered through the branches."""
    try:
        result = _finish(project, rec, emit)
    finally:
        # whatever _finish did or raised, this child's fd leaves the poller
        close_child(rec)
    try:
        nxt = Ticket.load(rec["path"]).stage
    except Exception:
        nxt = None
    proc = rec.get("proc")
    emit("stage_end", ticket=rec["tid"], stage=rec["stage"],
         session=rec.get("session"), result=result, next_stage=nxt,
         exit_code=proc.returncode if proc is not None else None)


def _finish(project: Path, rec: dict, emit=noop) -> str:
    # BEFORE anything agent-specific: the suite's verdict is its exit code, and
    # falling through to read_result() would let a `.result` an earlier stage's
    # agent left behind speak for the test run. It also skips the tamper check,
    # the tree snapshot and apply_claims -- none of which have an agent to check.
    if rec.get("kind") == "suite":
        return finish_child(project, rec, "regression suite", emit)
    # a merge is the dispatcher's own child too: its verdict is the exit code of
    # git, and `fail` means a conflict nobody may auto-resolve. Its worktree
    # stays -- `escalated` is not in CLEANUP_STAGES.
    if rec.get("kind") == "merge":
        return finish_child(project, rec, "merge", emit)
    # a re-gate is two steps, so its verdict is not the exit code alone: the
    # rebase only has to succeed for the gate to have a tree worth judging
    if rec.get("kind") == "regate":
        return finish_regate(project, rec, emit)

    close_child(rec)
    if rec.get("prompt"):
        rec["prompt"].unlink(missing_ok=True)
    if rec.get("settings"):
        rec["settings"].unlink(missing_ok=True)
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
                               f"- log: `{log.relative_to(project)}`", session=session)
    t.extra["last_session"] = {"stage": stage, "id": session,
                               "log": str(log.relative_to(project))}

    if tampered:
        drop_result(project, tid)
        escalate(t, f"`{stage}` edited dispatcher-owned frontmatter: "
                    + ", ".join(f"{k}={v!r}" for k, v in tampered.items()), emit)
        return "tampered"

    if rec["before"] is not None and tree_snapshot(wt) != rec["before"]:
        escalate(t, f"read-only stage `{stage}` modified the working tree", emit)
        return "wrote-in-readonly"

    if res is None:
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
    advance(project, t, result, res.get("summary", ""), emit)
    return result


def reap(project: Path, inflight: dict, emit=noop) -> bool:
    done = [tid for tid, rec in inflight.items() if rec["proc"].poll() is not None]
    for tid in done:
        rec = inflight.pop(tid)
        drain_all(inflight)   # a `regate` finish runs the gate, which blocks
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


def tick(project: Path, hcfg: dict, inflight: dict, max_parallel: int = 3,
         poller: Poller | None = None, emit=noop, stopping=lambda: False) -> bool:
    """One pass over one project: reap what finished, start what can start.
    The whole loop body, so the daemon can run it for many projects and
    `pipeline run` can run it for one."""
    worked = reap(project, inflight, emit)
    for path in all_tickets(project):
        if stopping() or len(inflight) >= max_parallel:
            break
        try:
            tid = Ticket.load(path).id
        except Exception as e:
            print(f"  skipping {path.name}: {e}")  # loudly, not silently
            continue
        if tid in inflight:
            continue
        did_work, rec = start(project, path, hcfg, inflight, poller, emit)
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
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, on_signal)
    return (lambda: state["stop"]), r, w


def run(project: Path, once: bool, interval: int, harness_name: str,
        max_parallel: int = 3, store=None) -> None:
    """Standalone: the daemon minus the socket server. One supervisor
    implementation, two entry points -- the daemon is an accelerator, never a
    dependency. `store` is optional; with none, nothing is recorded and the
    loop is exactly what it was before the daemon existed."""
    hcfg = harness(harness_name)
    emit = store.emitter(project) if store is not None else noop
    inflight: dict[str, dict] = {}
    lock = registry.lock(project)
    if lock is None:
        raise PipelineError(
            f"another dispatcher already holds {project}/.project/.lock -- "
            f"two supervisors on one project double-spawn")
    poller = Poller()
    stopping, wake, wake_w = _stopper()
    poller.watch(wake, lambda fd: os.read(fd, 4096))

    try:
        while not stopping():
            worked = tick(project, hcfg, inflight, max_parallel, poller, emit,
                          stopping)
            if once and not inflight and not worked:
                return  # --once drains the queue, it does not do a single pass
            poller.poll(1 if inflight else interval)
    finally:
        shut_down(project, inflight)
        signal.set_wakeup_fd(-1)
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
    hcfg = harness(harness_name)
    states: dict[str, dict] = server.states
    locks: dict[str, object] = {}
    stopping, wake, wake_w = _stopper()
    server.watch(wake, lambda fd: os.read(fd, 4096))
    store.emit("", "daemon_start", pid=os.getpid(), version=__version__,
               socket=str(server.path))
    print(f"pipelined {__version__}: pid {os.getpid()} on {server.path}")

    def release(key: str) -> None:
        shut_down(Path(key), states.pop(key, {}))
        fh = locks.pop(key, None)
        if fh is not None:
            fh.close()

    try:
        while not stopping():
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
                                   server, store.emitter(key), stopping)
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
        server.close()
        os.close(wake)
        os.close(wake_w)
