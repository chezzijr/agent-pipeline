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
TERMINAL = {"done", "rejected", "escalated"}

# `## Thread` is deliberately absent: it starts empty on every ticket and the
# gate itself is what first writes to it.
REQUIRED_SECTIONS = [
    "Summary", "Reproduction", "Digest", "Decisions checked",
    "Plan", "Acceptance criteria", "Rollback",
]

STAGES_DIR = HERE / "stages"


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


def gate(project: Path, tid: str) -> tuple[bool, list[str]]:
    """Tier A checks. Returns (passed, findings)."""
    path = ticket_path(project, tid)
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
        test_path = project / test.split("::")[0]
        if not test_path.is_file():
            findings.append(f"test file {test_path} does not exist")
        else:
            code, out = run_cmd(cfg["test_one"].format(test=test), project)
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
            code, out = run_cmd(cfg["test_suite_without_new"].format(test=test), project)
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

def harness(name: str = "claude-code") -> dict:
    p = HERE / "harnesses" / f"{name}.toml"
    if not p.is_file():
        die(f"no harness config {p}")
    return tomllib.loads(p.read_text())


def compose_prompt(stage: str) -> Path:
    """_common.md + this stage's body, frontmatter stripped, as one file."""
    _, body = split_frontmatter(STAGES_DIR / f"{stage}.md")
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
    f.write((STAGES_DIR / "_common.md").read_text() + "\n" + body)
    f.close()
    return Path(f.name)


def spawn(project: Path, tid: str, stage: str, hcfg: dict) -> tuple[str, Path]:
    """Returns (session_id, log_path) so both can be recorded in the ticket."""
    cfg = stage_config(stage)
    session = str(uuid.uuid4())
    logs = project / ".project" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{tid}-{stage}-{session[:8]}.log"
    prompt = compose_prompt(stage)
    cmd = hcfg["cmd"].format(
        model=cfg.get("model", "sonnet"),
        effort_flag=(hcfg.get("effort_flag", "").format(effort=cfg["effort"])
                     if cfg.get("effort") else ""),
        session_flag=hcfg.get("session_flag", "").format(session=session),
        stage_prompt=shlex.quote(str(prompt)),
        tools=hcfg["write_tools"] if cfg.get("write") else hcfg["readonly_tools"],
        cap=hcfg.get("max_usd", 5),
        project=shlex.quote(str(project)),
        id=tid,
    )
    print(f"  spawn: {stage} ({cfg.get('model')}) session {session[:8]} -> {log}")
    with log.open("w") as fh:
        fh.write(f"$ {cmd}\n\n")
        fh.flush()
        subprocess.run(cmd, shell=True, cwd=project, stdout=fh,
                       stderr=subprocess.STDOUT, env=project_env())
    prompt.unlink(missing_ok=True)
    return session, log


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


def advance(project: Path, path: Path, meta: dict, body: str, result: str, note: str) -> None:
    nxt, counters = transition(meta["stage"], result, meta.get("counters") or {},
                               meta.get("class", "bugfix"))
    body = append_thread(body, f"**{meta['stage']} -> {nxt}** (result: `{result}`)\n\n{note}")
    meta["counters"] = counters
    meta["stage"] = nxt
    meta["lease"] = {"holder": None, "expires": None}
    save_ticket(path, meta, body)
    print(f"  {path.stem}: -> {nxt} {counters}")


def step(project: Path, path: Path, hcfg: dict) -> bool:
    """Advance one ticket by one stage. Returns True if it did work."""
    meta, body = load_ticket(path)
    stage = meta.get("stage", "new")
    tid = meta["id"]

    if stage in TERMINAL or stage == "awaiting-approval":
        return False

    if lease_active(meta):
        return False

    if (meta.get("lease") or {}).get("expires"):  # expired -> crash recovery
        n = meta.get("counters", {}).get("lease_expiries", 0) + 1
        meta.setdefault("counters", {})["lease_expiries"] = n
        if n >= MAX_ATTEMPTS:
            escalate(path, meta, body, "lease expired twice")
            return True
        body = append_thread(body, f"lease expired, respawning `{stage}` fresh (expiry {n})")

    if stage == "new":
        advance(project, path, meta, body, "new", "dispatcher pickup")
        return True

    if stage == "verifying":
        cfg = project_config(project)
        code, out = run_cmd(cfg["test_suite"], project)
        advance(project, path, meta, body, "ok" if code == 0 else "fail",
                f"regression suite exit {code}\n```\n{out[-1500:]}\n```")
        return True

    if stage == "plan-validation":
        ok, failures = gate(project, tid)
        if not ok:
            meta, body = load_ticket(path)  # gate wrote findings to the thread
            advance(project, path, meta, body, "fail",
                    "Tier A gate failed:\n" + "\n".join(f"- {f}" for f in failures))
            return True
        meta, body = load_ticket(path)

    before = tree_snapshot(project) if is_readonly(stage) else None

    meta["lease"] = {"holder": f"{stage}-{os.getpid()}",
                     "expires": (now() + timedelta(minutes=LEASE_MINUTES)).isoformat()}
    save_ticket(path, meta, body)

    session, log = spawn(project, tid, stage, hcfg)

    res = read_result(project, tid)
    meta, body = load_ticket(path)
    body = append_thread(body, f"`{stage}` ran as session `{session}`\n"
                               f"- replay: `claude --resume {session}`\n"
                               f"- log: `{log.relative_to(project)}`")
    meta["last_session"] = {"stage": stage, "id": session,
                            "log": str(log.relative_to(project))}

    if before is not None and tree_snapshot(project) != before:
        escalate(path, meta, body,
                 f"read-only stage `{stage}` modified the working tree")
        return True

    if res is None:
        meta["lease"] = {"holder": None, "expires": None}
        save_ticket(path, meta, append_thread(
            body, f"`{stage}` wrote no .result sidecar -- will respawn"))
        return True

    for field in ("files_declared", "test_file"):
        if res.get(field):
            meta[field] = res[field]
    save_ticket(path, meta, body)

    advance(project, path, meta, body, res.get("result", "fail"), res.get("summary", ""))
    return True


def run(project: Path, once: bool, interval: int, harness_name: str) -> None:
    hcfg = harness(harness_name)
    while True:
        worked = any([step(project, p, hcfg) for p in all_tickets(project)])
        if once:
            return
        if not worked:
            time.sleep(interval)


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
        lease = "LEASED" if lease_active(meta) else ""
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
    p = sub.add_parser("resume"); p.add_argument("id"); p.add_argument("--stage", required=True); p.add_argument("--reset", nargs="*"); p.set_defaults(fn=cmd_resume)
    p = sub.add_parser("status"); p.add_argument("-v", "--verbose", action="store_true"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("run"); p.add_argument("--once", action="store_true"); p.add_argument("--interval", type=int, default=10); p.add_argument("--harness", default="claude-code"); p.set_defaults(fn=None)

    args = ap.parse_args()
    if args.cmd == "run":
        run(Path(args.project).resolve(), args.once, args.interval, args.harness)
    else:
        args.fn(args)


if __name__ == "__main__":
    main()
