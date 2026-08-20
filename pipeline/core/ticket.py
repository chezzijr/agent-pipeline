"""Ticket files: read, validate, write, and the thread they carry.

The ticket is the whole protocol between stages, so it stays hand-editable
markdown in git. `Ticket` is a typed view over it, not a schema it must obey:
every key the model does not know is round-tripped in `extra`, and a thread
header that does not parse comes back as a freeform note rather than an error.
"""
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from pipeline.core import PipelineError
from pipeline.core.machine import KNOWN_STAGES

LEASE_MINUTES = 30
TS_FMT = "%Y-%m-%d %H:%M:%SZ"


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


def render(meta: dict, body: str) -> str:
    fm = yaml.safe_dump(meta, sort_keys=False, default_flow_style=False)
    return f"---\n{fm}---\n{body}"


def write_atomic(path: Path, text: str) -> None:
    """The daemon and the TUI read these files while the supervisor writes
    them; a half-written ticket must never be observable."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


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


def append_entry(body: str, header: str, text: str) -> str:
    """Append at the end of the `## Thread` SECTION, not the end of the body.
    Today's template happens to put `## Thread` last; the moment anything
    follows it -- a section a human added, a template that changes -- entries
    written past it land outside the thread and `thread()` stops seeing them."""
    entry = f"\n### {header}\n\n{text.strip()}\n"
    lines = body.splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines)
                  if re.match(r"^##\s+Thread\s*$", l)), None)
    if start is None:
        return body.rstrip() + "\n\n## Thread\n" + entry
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^##\s+\S", lines[i])), len(lines))
    rest = "".join(lines[end:])
    return "".join(lines[:end]).rstrip() + "\n" + entry + (f"\n{rest}" if rest else "")


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


def record_decision(project: Path, t: "Ticket") -> str | None:
    """Copy the ticket's `## Decisions` into `.project/decisions/`. Planning
    greps that directory; until now nothing ever wrote to it, so the check that
    is supposed to stop you reverting a deliberate fix had no data."""
    text = t.section("Decisions").strip()
    if not text:
        return None
    d = project / ".project" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    did = f"DEC-{t.id.split('-')[-1]}"
    (d / f"{did}.md").write_text(
        f"# {did}\n\n"
        f"- ticket: {t.id} ({t.klass})\n"
        f"- branch: {t.branch}\n"
        f"- files: {', '.join(t.files_declared) or 'n/a'}\n"
        f"- decided: {now().date().isoformat()}\n\n{text}\n")
    return did


# --------------------------------------------------------------------------
# the model
# --------------------------------------------------------------------------

# The vocabulary a stage may write. Reading stays lenient; writing does not,
# because an invented kind is a typo nothing would ever notice.
KINDS = frozenset({"note", "transition", "gate", "question", "answer", "finding",
                   "escalation", "approval", "rejection", "session", "decision"})

# `class` is a Python keyword, so the attribute is `klass`; the YAML key stays
# `class`. `frontmatter()` is the only place that translation lives.
TYPED_KEYS = ("id", "stage", "class", "branch", "test_file", "files_declared",
              "counters", "lease")


@dataclass(frozen=True)
class ThreadEntry:
    ts: datetime | None      # None when a hand-written header does not parse
    stage: str               # "" for freeform
    kind: str                # "note" for freeform
    attrs: dict[str, str]
    text: str


def _parse_header(line: str) -> tuple[datetime | None, str, str, dict[str, str]]:
    """`2026-08-20 14:59:31Z · review · finding · severity=blocking`.

    Never raises: a header a human typed by hand is a note, not an error."""
    parts = [p.strip() for p in line.split("·")]
    try:
        ts = datetime.strptime(parts[0], TS_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None, "", "note", {}
    stage = parts[1] if len(parts) > 1 else ""
    kind = parts[2] if len(parts) > 2 else "note"
    attrs = dict(p.split("=", 1) for p in parts[3:] if "=" in p)
    return ts, stage, kind, attrs


@dataclass
class Ticket:
    """One ticket file. `extra` carries every key the model does not name, so a
    field a human (or a later version) added survives a save."""
    path: Path
    id: str
    stage: str = "new"
    klass: str = "bugfix"
    branch: str = ""
    test_file: str | None = None
    files_declared: list[str] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    lease: dict = field(default_factory=lambda: {"holder": None, "expires": None})
    extra: dict = field(default_factory=dict)
    body: str = ""

    # -- io ---------------------------------------------------------------
    @classmethod
    def load(cls, path) -> "Ticket":
        path = Path(path)
        try:
            meta, body = split_frontmatter(path)
        except Exception as e:
            raise PipelineError(f"{path}: {e}") from e
        if not isinstance(meta, dict):
            raise PipelineError(f"{path}: frontmatter is not a mapping")
        meta = dict(meta)
        lease = meta.pop("lease", None) or {"holder": None, "expires": None}
        return cls(path=path, id=str(meta.pop("id", "")),
                   stage=meta.pop("stage", None) or "new",
                   klass=meta.pop("class", None) or "bugfix",
                   branch=meta.pop("branch", None) or "",
                   test_file=meta.pop("test_file", None),
                   files_declared=meta.pop("files_declared", None) or [],
                   counters=meta.pop("counters", None) or {},
                   lease=lease, extra=meta, body=body)

    @classmethod
    def find(cls, project: Path, tid: str) -> "Ticket":
        return cls.load(ticket_path(project, tid))

    def frontmatter(self) -> dict:
        """Typed fields first in a stable order, then everything else."""
        fm = {"id": self.id, "stage": self.stage, "class": self.klass,
              "branch": self.branch, "test_file": self.test_file,
              "files_declared": self.files_declared, "counters": self.counters,
              "lease": self.lease}
        fm.update({k: v for k, v in self.extra.items() if k not in TYPED_KEYS})
        return fm

    def errors(self) -> list[str]:
        return validate_meta(self.frontmatter())

    def save(self, validate: bool = True) -> None:
        """Validated on the way in, not only on the next load, and written
        atomically -- something is always reading these files.

        `validate=False` exists for exactly one caller: escalating a ticket
        whose frontmatter is what is wrong. That write adds no hostile value --
        it read one off disk -- and marking the ticket terminal is what stops
        the value ever reaching a shell. Refusing it would refuse to quarantine.
        """
        bad = self.errors() if validate else []
        if bad:
            raise PipelineError(f"{self.path}: refusing to write: " + "; ".join(bad))
        write_atomic(self.path, render(self.frontmatter(), self.body))

    # -- body -------------------------------------------------------------
    def sections(self) -> dict[str, str]:
        return sections(self.body)

    def section(self, name: str) -> str:
        return self.sections().get(name, "")

    def append(self, stage: str, kind: str, text: str, **attrs) -> None:
        if kind not in KINDS:
            raise PipelineError(f"unknown thread kind {kind!r}")
        head = " · ".join([now().strftime(TS_FMT), stage, kind]
                               + [f"{k}={v}" for k, v in attrs.items()])
        self.body = append_entry(self.body, head, text)

    def thread(self) -> list[ThreadEntry]:
        out: list[ThreadEntry] = []
        head, buf = None, []
        for line in self.section("Thread").splitlines():
            if line.startswith("### "):
                if head is not None:
                    out.append(ThreadEntry(*head, "\n".join(buf).strip()))
                head, buf = _parse_header(line[4:]), []
            elif head is not None:
                buf.append(line)
        if head is not None:
            out.append(ThreadEntry(*head, "\n".join(buf).strip()))
        return out

    # -- lease ------------------------------------------------------------
    def lease_active(self) -> bool:
        exp = (self.lease or {}).get("expires")
        return bool(exp) and now() < datetime.fromisoformat(exp)

    def take_lease(self, holder: str, minutes: int = LEASE_MINUTES) -> None:
        self.lease = {"holder": holder,
                      "expires": (now() + timedelta(minutes=minutes)).isoformat()}

    def release_lease(self) -> None:
        self.lease = {"holder": None, "expires": None}
