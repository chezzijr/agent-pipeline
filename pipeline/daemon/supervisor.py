"""The dispatcher loop: claim a ticket, spawn one stateless agent per stage,
reap it, apply its verdict. The state machine decides; this only obeys."""
import os
import shlex
import signal
import subprocess
import time
import uuid
from dataclasses import replace
from pathlib import Path

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


def escalate(t: Ticket, reason: str) -> None:
    t.append(t.stage, "escalation", reason)
    t.stage = "escalated"
    t.release_lease()  # a human must be able to resume
    # the one unvalidated write: unusable frontmatter is itself a reason to
    # escalate, and refusing that write would leave the ticket un-quarantined
    t.save(validate=False)
    print(f"  {t.path.stem}: -> escalated ({reason})")


def advance(project: Path, t: Ticket, result: str, note: str) -> None:
    stage = t.stage
    nxt, counters = transition(stage, result, t.counters, t.klass)
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


def spawn(project: Path, wt: Path, tid: str, stage: str, hcfg: dict) -> dict:
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
    session = str(uuid.uuid4())
    logs = project / ".project" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{tid}-{stage}-{session[:8]}.log"
    prompt = compose_prompt(stage)
    settings = stage_settings(stage, cfg)
    cmd = render(hcfg, cfg, tid=tid, project=project,
                ticket=ticket_path(project, tid),
                result_file=tickets_dir(project) / f"{tid}.result",
                session=session, prompt=prompt, settings=settings)
    fh = log.open("w")
    fh.write(f"$ {cmd}\n\n")
    fh.flush()
    env = project_env()
    env["PIPELINE_STAGE"] = stage
    env["PIPELINE_READONLY"] = "0" if cfg.get("write") else "1"
    proc = subprocess.Popen(cmd, shell=True, cwd=wt, stdout=fh,
                            stderr=subprocess.STDOUT, env=env)
    print(f"  start {tid}: {stage} ({cfg.get('model')}) pid {proc.pid} -> {log.name}")
    return {"proc": proc, "fh": fh, "prompt": prompt, "settings": settings,
            "session": session,
            "log": log, "stage": stage, "wt": wt}


def spawn_command(project: Path, wt: Path, tid: str, stage: str, cmd: str,
                  kind: str = "command") -> dict:
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
    return {"kind": kind, "proc": proc, "fh": fh, "prompt": None,
            "settings": None, "session": None,
            "log": log, "stage": stage, "wt": wt}


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


def start(project: Path, path: Path, hcfg: dict, inflight: dict) -> tuple[bool, dict | None]:
    """Try to move one ticket forward.

    Returns (did_work, record). `did_work` is True for a synchronous advance as
    well as a spawn -- `--once` drains the queue, and a pass that only advanced
    `new -> triage` has still done work worth looping on.
    """
    t = Ticket.load(path)
    stage, tid = t.stage, t.id

    bad = t.errors()
    if bad and stage not in TERMINAL:
        escalate(t, "unusable frontmatter: " + "; ".join(bad))
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

    if t.lease_active():
        return False, None

    if (t.lease or {}).get("expires"):  # expired -> crash recovery
        n = t.counters.get("lease_expiries", 0) + 1
        t.counters["lease_expiries"] = n
        if n >= MAX_ATTEMPTS:
            escalate(t, "lease expired twice")
            return True, None
        t.append(stage, "note", f"lease expired, respawning `{stage}` fresh (expiry {n})")
        t.release_lease()
        t.save()  # persist now: later returns skip the save

    if stage == "new":
        advance(project, t, "new", "dispatcher pickup")
        return True, None

    if files_conflict(t.frontmatter(),
                      [r["meta"].frontmatter() for r in inflight.values()]):
        return False, None  # wait, do not fail -- cheap ordering without a scheduler

    try:
        cfg = project_config(project)
    except PipelineError as e:
        # one unconfigured project must not take the loop -- and every other
        # ticket's agent -- down with it
        escalate(t, str(e))
        return True, None
    wt = ensure_worktree(project, t.frontmatter(), cfg)
    if wt is None:
        escalate(t, "could not create a worktree")
        return True, None

    def child(cmd: str, kind: str) -> tuple[bool, dict]:
        # a child that outlives the tick must lease exactly like an agent, or a
        # crash mid-command leaves nothing for the expiry path to recover
        t.take_lease(f"{stage}-{os.getpid()}")
        t.save()
        rec = spawn_command(project, wt, tid, stage, cmd, kind)
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
        ok, failures = gate(project, tid, wt)
        t = Ticket.load(path)  # the gate wrote its findings to the thread
        if not ok:
            advance(project, t, "fail",
                    "Tier A gate failed:\n" + "\n".join(f"- {f}" for f in failures))
            return True, None

    t.take_lease(f"{stage}-{os.getpid()}")
    t.save()

    before = tree_snapshot(wt) if is_readonly(stage) else None  # before Popen
    drop_result(project, tid)  # L3: never let a previous run's verdict be reused
    rec = spawn(project, wt, tid, stage, hcfg)
    rec["path"] = path
    rec["tid"] = tid
    rec["meta"] = t   # the pre-spawn snapshot: control fields come back from here
    rec["before"] = before
    return True, rec


def finish_child(project: Path, rec: dict, label: str) -> None:
    """Apply a dispatcher-owned child's verdict: its exit code, nothing else."""
    rec["fh"].close()
    code = rec["proc"].returncode
    advance(project, Ticket.load(rec["path"]), "ok" if code == 0 else "fail",
            f"{label} exit {code}\n```\n{rec['log'].read_text()[-1500:]}\n```")


def finish_regate(project: Path, rec: dict) -> None:
    """A rebase onto current base, then the Tier A gate again -- an approval is
    only as good as the tree it was given against."""
    rec["fh"].close()
    code = rec["proc"].returncode
    t = Ticket.load(rec["path"])
    if code != 0:
        # same rule as a merge conflict: never auto-resolved, never retried.
        # The half-rebased worktree stays -- `escalated` is not in CLEANUP_STAGES.
        escalate(t, f"rebase onto base conflicted (exit {code})\n```\n"
                    f"{rec['log'].read_text()[-1500:]}\n```")
        return
    ok, failures = gate(project, rec["tid"], rec["wt"])
    t = Ticket.load(rec["path"])  # the gate wrote its findings to the thread
    advance(project, t, "ok" if ok else "fail",
            "re-gated after rebasing onto base:\n"
            + ("- clean" if ok else "\n".join(f"- {f}" for f in failures)))


def finish(project: Path, rec: dict) -> None:
    # BEFORE anything agent-specific: the suite's verdict is its exit code, and
    # falling through to read_result() would let a `.result` an earlier stage's
    # agent left behind speak for the test run. It also skips the tamper check,
    # the tree snapshot and apply_claims -- none of which have an agent to check.
    if rec.get("kind") == "suite":
        return finish_child(project, rec, "regression suite")
    # a merge is the dispatcher's own child too: its verdict is the exit code of
    # git, and `fail` means a conflict nobody may auto-resolve. Its worktree
    # stays -- `escalated` is not in CLEANUP_STAGES.
    if rec.get("kind") == "merge":
        return finish_child(project, rec, "merge")
    # a re-gate is two steps, so its verdict is not the exit code alone: the
    # rebase only has to succeed for the gate to have a tree worth judging
    if rec.get("kind") == "regate":
        return finish_regate(project, rec)

    rec["fh"].close()
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
                    + ", ".join(f"{k}={v!r}" for k, v in tampered.items()))
        return

    if rec["before"] is not None and tree_snapshot(wt) != rec["before"]:
        escalate(t, f"read-only stage `{stage}` modified the working tree")
        return

    if res is None:
        # L4: a harness that dies before writing a result must not respawn
        # forever. Same budget as every other bounded loop.
        n = t.counters.get("no_result", 0) + 1
        t.counters["no_result"] = n
        if n >= MAX_ATTEMPTS:
            escalate(t, f"`{stage}` wrote no .result sidecar {n} times")
            return
        t.release_lease()
        t.append(stage, "note",
                 f"`{stage}` wrote no .result sidecar (attempt {n}) -- will respawn")
        t.save()
        return

    # claims are validated BEFORE they are adopted: a hostile `test_file` in a
    # sidecar must never reach the ticket file, escalated or not
    claimed = t.frontmatter()
    apply_claims(claimed, stage, res)
    bad = validate_meta(claimed)
    if bad:
        drop_result(project, tid)
        escalate(t, "`.result` claimed an unusable value: " + "; ".join(bad))
        return
    t.test_file, t.files_declared = claimed["test_file"], claimed["files_declared"]
    t.counters["no_result"] = 0
    t.save()
    drop_result(project, tid)

    advance(project, t, res.get("result", "fail"), res.get("summary", ""))


def reap(project: Path, inflight: dict) -> bool:
    done = [tid for tid, rec in inflight.items() if rec["proc"].poll() is not None]
    for tid in done:
        rec = inflight.pop(tid)
        try:
            finish(project, rec)
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
        rec["fh"].close()
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


def run(project: Path, once: bool, interval: int, harness_name: str,
        max_parallel: int = 3) -> None:
    """Tickets are the queue, agents are stateless workers, and nothing waits on
    anything except its own bounded stage."""
    hcfg = harness(harness_name)
    inflight: dict[str, dict] = {}
    stopping = False

    def on_signal(signum, _frame):
        nonlocal stopping
        stopping = True
        print(f"\n  signal {signum}: stopping, releasing {len(inflight)} lease(s)")
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, on_signal)

    try:
        while not stopping:
            worked = reap(project, inflight)
            for path in all_tickets(project):
                if stopping or len(inflight) >= max_parallel:
                    break
                try:
                    tid = Ticket.load(path).id
                except Exception as e:
                    print(f"  skipping {path.name}: {e}")  # loudly, not silently
                    continue
                if tid in inflight:
                    continue
                did_work, rec = start(project, path, hcfg, inflight)
                worked = worked or did_work
                if rec:
                    inflight[rec["tid"]] = rec
            if once and not inflight and not worked:
                return  # --once drains the queue, it does not do a single pass
            time.sleep(1 if inflight else interval)
    finally:
        shut_down(project, inflight)
