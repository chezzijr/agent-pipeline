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
                                  project_config, stage_config, stage_settings)
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
    session = str(uuid.uuid4())
    logs = project / ".project" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{tid}-{stage}-{session[:8]}.log"
    prompt = compose_prompt(stage)
    settings = stage_settings(stage, cfg)
    cmd = hcfg["cmd"].format(
        model=cfg.get("model", "sonnet"),
        effort_flag=(hcfg.get("effort_flag", "").format(effort=cfg["effort"])
                     if cfg.get("effort") else ""),
        session_flag=hcfg.get("session_flag", "").format(session=session),
        settings_flag=(hcfg.get("settings_flag", "").format(
            settings=shlex.quote(str(settings))) if settings else ""),
        permission_mode=cfg.get("permission_mode", "acceptEdits"),
        stage_prompt=shlex.quote(str(prompt)),
        tools=cfg.get("tools") or (hcfg["write_tools"] if cfg.get("write")
                                   else hcfg["readonly_tools"]),
        cap=cfg.get("max_usd", hcfg.get("max_usd", 5)),
        project=shlex.quote(str(project)),
        ticket=shlex.quote(str(ticket_path(project, tid))),
        result_file=shlex.quote(str(tickets_dir(project) / f"{tid}.result")),
        id=tid,
    )
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


def spawn_suite(project: Path, wt: Path, tid: str, cfg: dict) -> dict:
    """Start the regression suite as a tracked child, shaped like `spawn()`'s
    record so `reap()` collects it with everything else. Run inline it stalled
    the loop: no other ticket advanced and no finished agent was reaped while a
    real project's suite took its minutes."""
    stage, cmd = "verifying", cfg["test_suite"]
    logs = project / ".project" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{tid}-{stage}-{uuid.uuid4().hex[:8]}.log"
    fh = log.open("w")
    fh.write(f"$ {cmd}\n\n")
    fh.flush()
    proc = subprocess.Popen(cmd, shell=True, cwd=wt, stdout=fh,
                            stderr=subprocess.STDOUT, env=project_env())
    print(f"  start {tid}: {stage} (script) pid {proc.pid} -> {log.name}")
    return {"kind": "suite", "proc": proc, "fh": fh, "prompt": None,
            "settings": None, "session": None,
            "log": log, "stage": stage, "wt": wt}


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

    if stage == "verifying":
        # a child that outlives the tick must lease exactly like an agent, or a
        # crash mid-suite leaves nothing for the expiry path to recover
        t.take_lease(f"{stage}-{os.getpid()}")
        t.save()
        rec = spawn_suite(project, wt, tid, cfg)
        rec["path"], rec["tid"], rec["meta"], rec["before"] = path, tid, t, None
        return True, rec

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


def finish(project: Path, rec: dict) -> None:
    # BEFORE anything agent-specific: the suite's verdict is its exit code, and
    # falling through to read_result() would let a `.result` an earlier stage's
    # agent left behind speak for the test run. It also skips the tamper check,
    # the tree snapshot and apply_claims -- none of which have an agent to check.
    if rec.get("kind") == "suite":
        rec["fh"].close()
        code = rec["proc"].returncode
        advance(project, Ticket.load(rec["path"]), "ok" if code == 0 else "fail",
                f"regression suite exit {code}\n```\n"
                f"{rec['log'].read_text()[-1500:]}\n```")
        return

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
