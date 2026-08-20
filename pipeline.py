#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Ticket-driven agent pipeline dispatcher.

Deliberately dumb: the state machine lives here, all judgment lives in the
agents. An agent never writes the `stage` field -- it writes a `.result`
sidecar and this script decides what happens next.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import json
import tempfile
import time
import tomllib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
MAX_ATTEMPTS = 2  # every bounded loop gets the same budget
LEASE_MINUTES = 30
STALE_HOURS = 4  # overlap ordering is silent; surface anything sitting still
TERMINAL = {"done", "rejected", "escalated"}
HUMAN_GATES = {"awaiting-approval", "needs-input"}

# `## Thread` is deliberately absent: it starts empty on every ticket and the
# gate itself is what first writes to it.
REQUIRED_SECTIONS = [
    "Summary", "Reproduction", "Digest", "Decisions checked",
    "Plan", "Acceptance criteria", "Rollback",
]

STAGES_DIR = HERE / "stages"
HOOKS_DIR = HERE / "hooks"


def stage_config(stage: str) -> dict:
    """Model, effort and write access come from the stage prompt's own
    frontmatter, so a stage is one self-contained file."""
    meta, _ = split_frontmatter(STAGES_DIR / f"{stage}.md")
    return meta


def agent_stages() -> list[str]:
    return sorted(p.stem for p in STAGES_DIR.glob("*.md") if not p.stem.startswith("_"))


def is_readonly(stage: str) -> bool:
    return not stage_config(stage).get("write", False)


# --------------------------------------------------------------------------
# ticket io
# --------------------------------------------------------------------------

def split_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no frontmatter")
    _, fm, body = text.split("---\n", 2)
    return (yaml.safe_load(fm) or {}), body


def load_ticket(path: Path) -> tuple[dict, str]:
    return split_frontmatter(path)


def save_ticket(path: Path, meta: dict, body: str) -> None:
    fm = yaml.safe_dump(meta, sort_keys=False, default_flow_style=False)
    path.write_text(f"---\n{fm}---\n{body}")


def sections(body: str) -> dict[str, str]:
    """Map '## Name' -> its content. Content may be empty."""
    out, name, buf = {}, None, []
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if name is not None:
                out[name] = "\n".join(buf).strip()
            name, buf = m.group(1), []
        elif name is not None:
            buf.append(line)
    if name is not None:
        out[name] = "\n".join(buf).strip()
    return out


def append_thread(body: str, text: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    entry = f"\n### {stamp}\n\n{text.strip()}\n"
    if "## Thread" in body:
        return body.rstrip() + "\n" + entry
    return body.rstrip() + "\n\n## Thread\n" + entry


def tickets_dir(project: Path) -> Path:
    return project / ".project" / "tickets"


def ticket_path(project: Path, tid: str) -> Path:
    return tickets_dir(project) / f"{tid}.md"


def all_tickets(project: Path) -> list[Path]:
    d = tickets_dir(project)
    return sorted(d.glob("*.md")) if d.is_dir() else []


def project_config(project: Path) -> dict:
    cfg = project / ".project" / "pipeline.toml"
    if not cfg.is_file():
        die(f"no {cfg} -- run `pipeline.py init {project}` first")
    return tomllib.loads(cfg.read_text())


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------
# state machine -- pure, so it is testable without spawning anything
# --------------------------------------------------------------------------

def transition(stage: str, result: str, counters: dict, klass: str = "bugfix"):
    """(next_stage, new_counters). Pure: never mutates `counters`.

    `result` is what the agent claimed about its own stage only. Every
    escalation and retry decision is made here, never by an agent.
    """
    c = dict(counters)

    def charge(key: str, target: str) -> tuple[str, dict]:
        c[key] = c.get(key, 0) + 1
        return ("escalated" if c[key] >= MAX_ATTEMPTS else target), c

    match (stage, result):
        case ("new", _):
            return "triage", c
        case ("triage", "ok"):
            return "planning", c
        case ("triage", "rejected"):
            return "rejected", c
        case ("planning", "ok"):
            return "plan-validation", c
        case ("planning", "needs-input"):
            # planning is the stage that genuinely needs the human; parking the
            # ticket is better than guessing an answer into the plan
            return "needs-input", c
        case ("plan-validation", "ok"):
            return "awaiting-approval", c
        case ("plan-validation", "fail"):
            return charge("plan_validation_attempts", "planning")
        case ("implementing", "ok"):
            return "review", c
        case ("implementing", "blocked"):
            return charge("blocked_count", "plan-validation")
        case ("review", "ok"):
            # a one-line bugfix's incremental review already saw the whole diff
            return ("verifying" if klass == "bugfix" else "holistic-review"), c
        case ("review", "fail"):
            return charge("review_loops", "implementing")
        case ("holistic-review", "ok"):
            return "verifying", c
        case ("holistic-review", "fail"):
            return charge("review_loops", "implementing")
        case ("verifying", "ok"):
            return "done", c
        case ("verifying", "fail"):
            return charge("review_loops", "implementing")

    # unknown (stage, result) is a bug or a lying agent -- never guess
    return "escalated", c


# --------------------------------------------------------------------------
# tier A gate -- deterministic, no LLM judgment anywhere in the path
# --------------------------------------------------------------------------

def project_env() -> dict:
    """The dispatcher itself runs inside `uv run`'s venv. Left alone, that venv
    shadows the target project's interpreter and its test dependencies, so
    every project command would run against the wrong Python."""
    env = dict(os.environ)
    venv = env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    if venv:
        env["PATH"] = os.pathsep.join(
            d for d in env.get("PATH", "").split(os.pathsep) if not d.startswith(venv))
    return env


def run_cmd(cmd: str, cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True,
                       env=project_env())
    return p.returncode, (p.stdout + p.stderr)[-4000:]


def gate(project: Path, tid: str, workdir: Path | None = None) -> tuple[bool, list[str]]:
    """Tier A checks, run in the ticket's checkout. Returns (passed, findings)."""
    path = ticket_path(project, tid)
    wd = workdir or project
    cfg = project_config(project)
    findings: list[str] = []

    try:
        meta, body = load_ticket(path)
    except Exception as e:
        return False, [f"frontmatter does not parse: {e}"]

    secs = sections(body)
    for name in REQUIRED_SECTIONS:
        if not secs.get(name):
            findings.append(f"section `## {name}` missing or empty")

    test = meta.get("test_file")
    if not test:
        findings.append("no `test_file` recorded in frontmatter")
    else:
        test_path = wd / test.split("::")[0]
        if not test_path.is_file():
            findings.append(f"test file {test_path} does not exist")
        else:
            code, out = run_cmd(cfg["test_one"].format(test=test), wd)
            node = test.split("::")[-1]
            if code == 0:
                findings.append(f"`{test}` PASSES -- it must fail before implementation")
            elif node not in out:
                # a missing dependency or an import error exits non-zero too, and
                # looks exactly like a failing test unless you check for the name
                findings.append(
                    f"`{test}` exited non-zero but its name never appears in the "
                    f"output -- it errored rather than failed\n```\n{out[-1200:]}\n```")
            else:
                findings.append(f"ok: `{test}` fails as required\n```\n{out[-1200:]}\n```")
            code, out = run_cmd(cfg["test_suite_without_new"].format(test=test), wd)
            if code != 0:
                findings.append(
                    f"suite excluding `{test}` is RED -- pre-existing breakage, "
                    f"fix that first\n```\n{out[-1200:]}\n```"
                )

    dec = secs.get("Decisions checked", "")
    if dec and "none relevant" not in dec.lower() and not re.search(r"\b[A-Z]+-\d+\b|DEC-", dec):
        findings.append("`## Decisions checked` cites no decision IDs and no explicit "
                        "'none relevant' + grep terms")

    if not meta.get("files_declared"):
        findings.append("`files_declared` is empty")

    crit = secs.get("Acceptance criteria", "")
    for line in [l for l in crit.splitlines() if l.strip().startswith(("-", "*"))]:
        if not re.search(r"`[^`]+`|\btest_\w+", line):
            findings.append(f"acceptance criterion names no test: {line.strip()}")

    failed = [f for f in findings if not f.startswith("ok:")]
    verdict = "PASS" if not failed else "FAIL"
    body = append_thread(body, "**Tier A gate: %s**\n\n%s" % (
        verdict, "\n".join(f"- {f}" for f in findings) or "- (no checks ran)"))
    save_ticket(path, meta, body)
    return not failed, failed


# --------------------------------------------------------------------------
# spawning
# --------------------------------------------------------------------------

def worktree(project: Path, meta: dict) -> Path:
    return project / ".worktrees" / meta["id"]


def ensure_worktree(project: Path, meta: dict, cfg: dict) -> Path | None:
    """A ticket owns a checkout. Two tickets cannot share one, which is why
    concurrency and worktrees arrive together. Scripted, never improvised by an
    agent -- that is where 'forgot the env file' bugs come from."""
    wt = worktree(project, meta)
    if wt.is_dir():
        return wt
    wt.parent.mkdir(parents=True, exist_ok=True)
    code, out = run_cmd(
        f"git worktree add -B {meta['branch']} {shlex.quote(str(wt))} "
        f"{cfg.get('base', 'main')}", project)
    if code:
        print(f"  worktree failed for {meta['id']}: {out.strip()[:300]}")
        return None
    if cfg.get("worktree_setup"):
        # per-project: link a shared build cache, copy .env, install deps
        run_cmd(cfg["worktree_setup"], wt)
    return wt


def drop_worktree(project: Path, meta: dict) -> None:
    wt = worktree(project, meta)
    if wt.is_dir():
        run_cmd(f"git worktree remove --force {shlex.quote(str(wt))}", project)


def harness(name: str = "claude-code") -> dict:
    p = HERE / "harnesses" / f"{name}.toml"
    if not p.is_file():
        die(f"no harness config {p}")
    return tomllib.loads(p.read_text())


def compose_prompt(stage: str) -> Path:
    """_common.md + this stage's body, frontmatter stripped, as one file."""
    cfg, body = split_frontmatter(STAGES_DIR / f"{stage}.md")
    text = (STAGES_DIR / "_common.md").read_text() + "\n" + body
    if cfg.get("skills"):
        text += ("\n\n## Skills for this stage\n\n"
                 "Invoke these before you start; they are here because this "
                 "stage's job depends on them.\n\n"
                 + "\n".join(f"- `/{sk}`" for sk in cfg["skills"]) + "\n")
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
    f.write(text)
    f.close()
    return Path(f.name)


def stage_settings(stage: str, cfg: dict) -> Path | None:
    """Per-stage hooks, as a settings file the harness loads. A hook is the only
    layer that decides with code, so this is where a stage's non-negotiables go."""
    names = cfg.get("hooks") or []
    if not names:
        return None
    entries = [{"type": "command", "command": str(HOOKS_DIR / f"{n}.py")}
               for n in names]
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": entries}]}}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(settings, f)
    f.close()
    return Path(f.name)


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


def read_result(project: Path, tid: str) -> dict | None:
    p = tickets_dir(project) / f"{tid}.result"
    if not p.is_file():
        return None
    data = yaml.safe_load(p.read_text()) or {}
    p.unlink()
    return data


def tree_snapshot(project: Path) -> str:
    """What a read-only stage must not change. `.project/` is excluded: writing
    to the ticket and the .result sidecar is every stage's job, including the
    read-only ones."""
    _, head = run_cmd("git rev-parse HEAD", project)
    _, dirty = run_cmd("git status --porcelain -- . ':(exclude).project'", project)
    return head + dirty


# --------------------------------------------------------------------------
# dispatcher
# --------------------------------------------------------------------------

def now() -> datetime:
    return datetime.now(timezone.utc)


def lease_active(meta: dict) -> bool:
    exp = (meta.get("lease") or {}).get("expires")
    return bool(exp) and now() < datetime.fromisoformat(exp)


def escalate(path: Path, meta: dict, body: str, reason: str) -> None:
    meta["stage"] = "escalated"
    meta["lease"] = {"holder": None, "expires": None}  # a human must be able to resume
    save_ticket(path, meta, append_thread(body, f"**escalated**: {reason}"))
    print(f"  {path.stem}: -> escalated ({reason})")


def record_decision(project: Path, meta: dict, body: str) -> str | None:
    """Copy the ticket's `## Decisions` into `.project/decisions/`. Planning
    greps that directory; until now nothing ever wrote to it, so the check that
    is supposed to stop you reverting a deliberate fix had no data."""
    text = sections(body).get("Decisions", "").strip()
    if not text:
        return None
    d = project / ".project" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    did = f"DEC-{meta['id'].split('-')[-1]}"
    (d / f"{did}.md").write_text(
        f"# {did}\n\n"
        f"- ticket: {meta['id']} ({meta.get('class', '')})\n"
        f"- branch: {meta.get('branch')}\n"
        f"- files: {', '.join(meta.get('files_declared') or []) or 'n/a'}\n"
        f"- decided: {now().date().isoformat()}\n\n{text}\n")
    return did


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


# Which stage is allowed to set which frontmatter field. Without this any
# stage could rewrite `files_declared` -- a reviewer shrinking the set would
# silently unblock a ticket that overlaps one already in flight.
CLAIMS = {"test_file": ("triage",), "files_declared": ("planning", "implementing")}


def apply_claims(meta: dict, stage: str, res: dict) -> None:
    for field, owners in CLAIMS.items():
        if not res.get(field) or stage not in owners:
            continue
        if field == "files_declared" and stage == "implementing":
            # implementation may discover more files, never fewer
            meta[field] = sorted(set(meta.get(field) or []) | set(res[field]))
        else:
            meta[field] = res[field]


def files_conflict(meta: dict, inflight_meta: list[dict]) -> bool:
    """Two tickets touching the same file are ordered, not run together --
    otherwise their branches merge into a conflict nobody asked for."""
    mine = set(meta.get("files_declared") or [])
    return any(mine & set(o.get("files_declared") or []) for o in inflight_meta)


def start(project: Path, path: Path, hcfg: dict, inflight: dict) -> dict | None:
    """Try to move one ticket forward. Returns an in-flight record if an agent
    was launched, None if the ticket was handled synchronously or skipped."""
    meta, body = load_ticket(path)
    stage = meta.get("stage", "new")
    tid = meta["id"]

    if stage in HUMAN_GATES:
        return None

    if stage in TERMINAL:
        if worktree(project, meta).is_dir():
            drop_worktree(project, meta)
            print(f"  cleaned worktree for {tid} ({stage})")
        return None

    if lease_active(meta):
        return None

    if (meta.get("lease") or {}).get("expires"):  # expired -> crash recovery
        n = meta.get("counters", {}).get("lease_expiries", 0) + 1
        meta.setdefault("counters", {})["lease_expiries"] = n
        if n >= MAX_ATTEMPTS:
            escalate(path, meta, body, "lease expired twice")
            return None
        body = append_thread(body, f"lease expired, respawning `{stage}` fresh (expiry {n})")

    if stage == "new":
        advance(project, path, meta, body, "new", "dispatcher pickup")
        return None

    if files_conflict(meta, [r["meta"] for r in inflight.values()]):
        return None  # wait, do not fail -- cheap ordering without a scheduler

    cfg = project_config(project)
    wt = ensure_worktree(project, meta, cfg)
    if wt is None:
        escalate(path, meta, body, "could not create a worktree")
        return None

    if stage == "verifying":
        # ponytail: run inline. A slow suite stalls the loop; move it to the
        # in-flight table like an agent if that ever bites.
        code, out = run_cmd(cfg["test_suite"], wt)
        advance(project, path, meta, body, "ok" if code == 0 else "fail",
                f"regression suite exit {code}\n```\n{out[-1500:]}\n```")
        return None

    if stage == "plan-validation":
        ok, failures = gate(project, tid, wt)
        if not ok:
            meta, body = load_ticket(path)  # gate wrote its findings to the thread
            advance(project, path, meta, body, "fail",
                    "Tier A gate failed:\n" + "\n".join(f"- {f}" for f in failures))
            return None
        meta, body = load_ticket(path)

    meta["lease"] = {"holder": f"{stage}-{os.getpid()}",
                     "expires": (now() + timedelta(minutes=LEASE_MINUTES)).isoformat()}
    save_ticket(path, meta, body)

    rec = spawn(project, wt, tid, stage, hcfg)
    rec["path"] = path
    rec["tid"] = tid
    rec["meta"] = meta
    rec["before"] = tree_snapshot(wt) if is_readonly(stage) else None
    return rec


def finish(project: Path, rec: dict) -> None:
    rec["fh"].close()
    rec["prompt"].unlink(missing_ok=True)
    if rec.get("settings"):
        rec["settings"].unlink(missing_ok=True)
    path, tid, stage = rec["path"], rec["tid"], rec["stage"]
    session, log, wt = rec["session"], rec["log"], rec["wt"]

    res = read_result(project, tid)
    meta, body = load_ticket(path)
    body = append_thread(body, f"`{stage}` ran as session `{session}`\n"
                               f"- replay: `claude --resume {session}`\n"
                               f"- log: `{log.relative_to(project)}`")
    meta["last_session"] = {"stage": stage, "id": session,
                            "log": str(log.relative_to(project))}

    if rec["before"] is not None and tree_snapshot(wt) != rec["before"]:
        escalate(path, meta, body,
                 f"read-only stage `{stage}` modified the working tree")
        return

    if res is None:
        meta["lease"] = {"holder": None, "expires": None}
        save_ticket(path, meta, append_thread(
            body, f"`{stage}` wrote no .result sidecar -- will respawn"))
        return

    apply_claims(meta, stage, res)
    save_ticket(path, meta, body)

    advance(project, path, meta, body, res.get("result", "fail"), res.get("summary", ""))


def reap(project: Path, inflight: dict) -> bool:
    done = [tid for tid, rec in inflight.items() if rec["proc"].poll() is not None]
    for tid in done:
        finish(project, inflight.pop(tid))
    return bool(done)


def run(project: Path, once: bool, interval: int, harness_name: str,
        max_parallel: int = 3) -> None:
    """Tickets are the queue, agents are stateless workers, and nothing waits on
    anything except its own bounded stage."""
    hcfg = harness(harness_name)
    inflight: dict[str, dict] = {}
    while True:
        worked = reap(project, inflight)
        for path in all_tickets(project):
            if len(inflight) >= max_parallel:
                break
            meta, _ = load_ticket(path)
            if meta["id"] in inflight:
                continue
            rec = start(project, path, hcfg, inflight)
            worked = True if rec else worked
            if rec:
                inflight[rec["tid"]] = rec
        if once and not inflight and not worked:
            return  # --once drains the queue, it does not do a single pass
        time.sleep(1 if inflight else interval)


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def cmd_init(args) -> None:
    project = Path(args.dir).resolve()
    tickets_dir(project).mkdir(parents=True, exist_ok=True)
    (project / ".project" / "decisions").mkdir(exist_ok=True)
    cfg = project / ".project" / "pipeline.toml"
    if not cfg.exists():
        cfg.write_text((HERE / "pipeline.toml.example").read_text())
    print(f"initialised {project / '.project'} -- edit {cfg} for this project's commands")


def cmd_new(args) -> None:
    project = Path(args.project).resolve()
    d = tickets_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    n = 1 + max((int(m.group(1)) for p in d.glob("TICKET-*.md")
                 if (m := re.match(r"TICKET-(\d+)", p.stem))), default=0)
    tid = f"TICKET-{n:03d}"
    tpl = (HERE / "ticket-template.md").read_text()
    (d / f"{tid}.md").write_text(
        tpl.replace("{{id}}", tid).replace("{{class}}", args.cls)
           .replace("{{branch}}", f"ticket/{n:03d}").replace("{{title}}", args.title))
    print(d / f"{tid}.md")


def cmd_gate(args) -> None:
    ok, failures = gate(Path(args.project).resolve(), args.id)
    for f in failures:
        print(f"FAIL: {f}")
    print("gate: PASS" if ok else "gate: FAIL")
    sys.exit(0 if ok else 1)


def cmd_approve(args) -> None:
    project = Path(args.project).resolve()
    path = ticket_path(project, args.id)
    meta, body = load_ticket(path)
    if meta["stage"] != "awaiting-approval":
        die(f"{args.id} is in `{meta['stage']}`, not `awaiting-approval`")
    meta["stage"] = "implementing"
    meta["approved_by"] = args.by or os.environ.get("USER", "unknown")
    meta["approved_at"] = now().isoformat()
    save_ticket(path, meta, append_thread(body, f"**approved by {meta['approved_by']}**"))
    print(f"{args.id}: -> implementing")


def cmd_answer(args) -> None:
    project = Path(args.project).resolve()
    path = ticket_path(project, args.id)
    meta, body = load_ticket(path)
    if meta["stage"] != "needs-input":
        die(f"{args.id} is in `{meta['stage']}`, not `needs-input`")
    meta["stage"] = "planning"
    save_ticket(path, meta, append_thread(
        body, f"**answer from {os.environ.get('USER', 'human')}**\n\n{args.text}"))
    print(f"{args.id}: -> planning")


def cmd_resume(args) -> None:
    project = Path(args.project).resolve()
    path = ticket_path(project, args.id)
    meta, body = load_ticket(path)
    meta["stage"] = args.stage
    for key in args.reset or []:
        meta.setdefault("counters", {})[key] = 0
    meta["lease"] = {"holder": None, "expires": None}
    save_ticket(path, meta, append_thread(
        body, f"**resumed** by human -> `{args.stage}`, reset {args.reset or []}"))
    print(f"{args.id}: -> {args.stage}")


def cmd_status(args) -> None:
    for p in all_tickets(Path(args.project).resolve()):
        meta, _ = load_ticket(p)
        c = meta.get("counters") or {}
        stale = ""
        if (meta.get("stage") not in TERMINAL | HUMAN_GATES
                and not lease_active(meta)
                and now() - datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
                > timedelta(hours=STALE_HOURS)):
            stale = f"STALE>{STALE_HOURS}h"  # probably waiting behind an overlap
        lease = "LEASED" if lease_active(meta) else stale
        print(f"{meta['id']:<12} {meta.get('stage',''):<17} {meta.get('class',''):<9} "
              f"{c} {lease}")
        last = meta.get("last_session")
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
    if args.cmd == "run":
        run(Path(args.project).resolve(), args.once, args.interval, args.harness,
            args.max_parallel)
    else:
        args.fn(args)


if __name__ == "__main__":
    main()
