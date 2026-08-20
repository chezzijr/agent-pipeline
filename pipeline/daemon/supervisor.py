"""The dispatcher loop: claim a ticket, spawn one stateless agent per stage,
reap it, apply its verdict. The state machine decides; this only obeys."""
import os
import shlex
import signal
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.core.config import (compose_prompt, harness, is_readonly,
                                  project_config, stage_config, stage_settings)
from pipeline.core.gate import gate
from pipeline.core.machine import (CLEANUP_STAGES, CONTROL_FIELDS, HUMAN_GATES,
                                   MAX_ATTEMPTS, TERMINAL, apply_claims,
                                   files_conflict, transition)
from pipeline.core.ticket import (LEASE_MINUTES, all_tickets, append_thread,
                                  drop_result, load_ticket, now, read_result,
                                  record_decision, save_ticket, ticket_path,
                                  tickets_dir, validate_meta)
from pipeline.core.worktree import (drop_worktree, ensure_worktree,
                                    project_env, run_cmd, tree_snapshot,
                                    worktree)

def lease_active(meta: dict) -> bool:
    exp = (meta.get("lease") or {}).get("expires")
    return bool(exp) and now() < datetime.fromisoformat(exp)


def escalate(path: Path, meta: dict, body: str, reason: str) -> None:
    meta["stage"] = "escalated"
    meta["lease"] = {"holder": None, "expires": None}  # a human must be able to resume
    save_ticket(path, meta, append_thread(body, f"**escalated**: {reason}"))
    print(f"  {path.stem}: -> escalated ({reason})")

def advance(project: Path, path: Path, meta: dict, body: str, result: str, note: str) -> None:
    nxt, counters = transition(meta["stage"], result, meta.get("counters") or {},
                               meta.get("class", "bugfix"))
    body = append_thread(body, f"**{meta['stage']} -> {nxt}** (result: `{result}`)\n\n{note}")
    if nxt == "done":
        did = record_decision(project, meta, body)
        body = append_thread(body, f"decision recorded as `{did}`" if did else
                             "no `## Decisions` section -- nothing recorded for "
                             "future planning agents to find")
    meta["counters"] = counters
    meta["stage"] = nxt
    meta["lease"] = {"holder": None, "expires": None}
    save_ticket(path, meta, body)
    print(f"  {path.stem}: -> {nxt} {counters}")


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

def start(project: Path, path: Path, hcfg: dict, inflight: dict) -> tuple[bool, dict | None]:
    """Try to move one ticket forward.

    Returns (did_work, record). `did_work` is True for a synchronous advance as
    well as a spawn -- `--once` drains the queue, and a pass that only advanced
    `new -> triage` has still done work worth looping on.
    """
    meta, body = load_ticket(path)
    stage = meta.get("stage", "new")
    tid = meta["id"]

    bad = validate_meta(meta)
    if bad and stage not in TERMINAL:
        escalate(path, meta, body, "unusable frontmatter: " + "; ".join(bad))
        return True, None

    if stage in HUMAN_GATES:
        return False, None

    if stage in TERMINAL:
        # an escalated ticket keeps its worktree: the uncommitted state is the
        # evidence the human was escalated to look at
        if stage in CLEANUP_STAGES and worktree(project, meta).is_dir():
            drop_worktree(project, meta)
            print(f"  cleaned worktree for {tid} ({stage})")
            return True, None
        return False, None

    if lease_active(meta):
        return False, None

    if (meta.get("lease") or {}).get("expires"):  # expired -> crash recovery
        n = meta.get("counters", {}).get("lease_expiries", 0) + 1
        meta.setdefault("counters", {})["lease_expiries"] = n
        if n >= MAX_ATTEMPTS:
            escalate(path, meta, body, "lease expired twice")
            return True, None
        body = append_thread(body, f"lease expired, respawning `{stage}` fresh (expiry {n})")
        meta["lease"] = {"holder": None, "expires": None}
        save_ticket(path, meta, body)  # persist now: later returns skip the save

    if stage == "new":
        advance(project, path, meta, body, "new", "dispatcher pickup")
        return True, None

    if files_conflict(meta, [r["meta"] for r in inflight.values()]):
        return False, None  # wait, do not fail -- cheap ordering without a scheduler

    try:
        cfg = project_config(project)
    except PipelineError as e:
        # one unconfigured project must not take the loop -- and every other
        # ticket's agent -- down with it
        escalate(path, meta, body, str(e))
        return True, None
    wt = ensure_worktree(project, meta, cfg)
    if wt is None:
        escalate(path, meta, body, "could not create a worktree")
        return True, None

    if stage == "verifying":
        # ponytail: run inline. A slow suite stalls the loop; move it to the
        # in-flight table like an agent if that ever bites.
        code, out = run_cmd(cfg["test_suite"], wt)
        advance(project, path, meta, body, "ok" if code == 0 else "fail",
                f"regression suite exit {code}\n```\n{out[-1500:]}\n```")
        return True, None

    if stage == "plan-validation":
        ok, failures = gate(project, tid, wt)
        if not ok:
            meta, body = load_ticket(path)  # gate wrote its findings to the thread
            advance(project, path, meta, body, "fail",
                    "Tier A gate failed:\n" + "\n".join(f"- {f}" for f in failures))
            return True, None
        meta, body = load_ticket(path)

    meta["lease"] = {"holder": f"{stage}-{os.getpid()}",
                     "expires": (now() + timedelta(minutes=LEASE_MINUTES)).isoformat()}
    save_ticket(path, meta, body)

    before = tree_snapshot(wt) if is_readonly(stage) else None  # before Popen
    drop_result(project, tid)  # L3: never let a previous run's verdict be reused
    rec = spawn(project, wt, tid, stage, hcfg)
    rec["path"] = path
    rec["tid"] = tid
    rec["meta"] = meta
    rec["before"] = before
    return True, rec


def finish(project: Path, rec: dict) -> None:
    rec["fh"].close()
    rec["prompt"].unlink(missing_ok=True)
    if rec.get("settings"):
        rec["settings"].unlink(missing_ok=True)
    path, tid, stage = rec["path"], rec["tid"], rec["stage"]
    session, log, wt = rec["session"], rec["log"], rec["wt"]

    res = read_result(project, tid, keep=True)
    agent_meta, body = load_ticket(path)

    # The agent had write access to this file. Its prose sections are its own;
    # its frontmatter is not. Every control field is restored from the snapshot
    # taken before the spawn, so "an agent never writes `stage`" is enforced by
    # the dispatcher rather than requested in a prompt.
    meta = dict(rec["meta"])
    tampered = {k: v for k, v in agent_meta.items()
                if k in CONTROL_FIELDS and v != meta.get(k)}

    body = append_thread(body, f"`{stage}` ran as session `{session}`\n"
                               f"- replay: `claude --resume {session}`\n"
                               f"- log: `{log.relative_to(project)}`")
    meta["last_session"] = {"stage": stage, "id": session,
                            "log": str(log.relative_to(project))}

    if tampered:
        drop_result(project, tid)
        escalate(path, meta, body,
                 f"`{stage}` edited dispatcher-owned frontmatter: "
                 + ", ".join(f"{k}={v!r}" for k, v in tampered.items()))
        return

    if rec["before"] is not None and tree_snapshot(wt) != rec["before"]:
        escalate(path, meta, body,
                 f"read-only stage `{stage}` modified the working tree")
        return

    if res is None:
        # L4: a harness that dies before writing a result must not respawn
        # forever. Same budget as every other bounded loop.
        n = (meta.get("counters") or {}).get("no_result", 0) + 1
        meta.setdefault("counters", {})["no_result"] = n
        if n >= MAX_ATTEMPTS:
            escalate(path, meta, body,
                     f"`{stage}` wrote no .result sidecar {n} times")
            return
        meta["lease"] = {"holder": None, "expires": None}
        save_ticket(path, meta, append_thread(
            body, f"`{stage}` wrote no .result sidecar (attempt {n}) -- will respawn"))
        return

    apply_claims(meta, stage, res)
    bad = validate_meta(meta)
    if bad:
        drop_result(project, tid)
        escalate(path, meta, body, "`.result` claimed an unusable value: "
                 + "; ".join(bad))
        return
    meta["counters"] = {**(meta.get("counters") or {}), "no_result": 0}
    save_ticket(path, meta, body)
    drop_result(project, tid)

    advance(project, path, meta, body, res.get("result", "fail"), res.get("summary", ""))


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
        rec["prompt"].unlink(missing_ok=True)
        if rec.get("settings"):
            rec["settings"].unlink(missing_ok=True)
        try:
            meta, body = load_ticket(rec["path"])
            meta["lease"] = {"holder": None, "expires": None}
            save_ticket(rec["path"], meta, append_thread(
                body, f"`{rec['stage']}` was interrupted; lease released"))
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
                    meta, _ = load_ticket(path)
                except Exception as e:
                    print(f"  skipping {path.name}: {e}")  # loudly, not silently
                    continue
                if meta.get("id") in inflight:
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
