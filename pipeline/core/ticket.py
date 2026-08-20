"""Ticket files: read, validate, write, and the thread they carry."""
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pipeline.core.machine import KNOWN_STAGES

LEASE_MINUTES = 30


def now() -> datetime:
    return datetime.now(timezone.utc)


SAFE_ID = re.compile(r"^TICKET-\d{1,6}$")
SAFE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,80}$")
SAFE_TEST = re.compile(r"^[A-Za-z0-9._/-]{1,200}(::[A-Za-z0-9_\[\].-]{1,100})*$")
SAFE_FILE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")

def validate_meta(meta: dict) -> list[str]:
    """Every one of these fields reaches a shell command or the state machine,
    and every one of them sits in a file an agent can write. Validate on the way
    in; do not rely on quoting alone."""
    bad = []
    if not SAFE_ID.match(str(meta.get("id", ""))):
        bad.append(f"id {meta.get('id')!r} is not TICKET-<digits>")
    if not SAFE_BRANCH.match(str(meta.get("branch", ""))):
        bad.append(f"branch {meta.get('branch')!r} is not a plain branch name")
    if meta.get("stage") is not None and meta["stage"] not in KNOWN_STAGES:
        bad.append(f"stage {meta.get('stage')!r} is not a known stage")
    if meta.get("test_file") and not SAFE_TEST.match(str(meta["test_file"])):
        bad.append(f"test_file {meta['test_file']!r} contains shell metacharacters")
    for f in meta.get("files_declared") or []:
        if not SAFE_FILE.match(str(f)) or ".." in str(f) or str(f).startswith("/"):
            bad.append(f"files_declared entry {f!r} is not a plain relative path")
    return bad


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

def result_file(project: Path, tid: str) -> Path:
    return tickets_dir(project) / f"{tid}.result"


def read_result(project: Path, tid: str, keep: bool = False) -> dict | None:
    p = result_file(project, tid)
    if not p.is_file():
        return None
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if not keep:
        p.unlink()
    # L7: the verdict stays on disk until it has actually been acted on, so a
    # crash between reading and applying it does not lose the stage's work
    return data


def drop_result(project: Path, tid: str) -> None:
    result_file(project, tid).unlink(missing_ok=True)

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
