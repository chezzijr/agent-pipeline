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


def lease_expiry(exp) -> datetime | None:
    """`lease.expires` -> an aware datetime, or None if it is not a timestamp.

    Total, because this field is hostile like every other one: an unquoted
    `expires: 2026-08-21 10:00:00` is a YAML *datetime* (not a str, so
    `fromisoformat` raised TypeError) and a naive ISO string compares against
    an aware `now()` with another TypeError. Naive means UTC here -- the
    dispatcher writes UTC and the only other author is a human editing the
    file it wrote.
    """
    if isinstance(exp, datetime):
        return exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
    if not isinstance(exp, str):
        return None
    try:
        d = datetime.fromisoformat(exp)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


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
    # The lease decides whether a second agent is spawned onto a live stage, so
    # a shape nobody can read is as unusable as a hostile branch name. It was
    # the one field this function never looked at (CLAUDE.md invariant 5 named
    # the other four), so a hand-edited one crashed `lease_active()` instead of
    # escalating the ticket: `ls` died for every project and the tick aborted
    # that project's whole pass, every tick, forever.
    lease = meta.get("lease")
    if lease is not None and not isinstance(lease, dict):
        bad.append(f"lease {lease!r} is not a mapping")
    elif isinstance(lease, dict):
        exp = lease.get("expires")
        if exp is not None and lease_expiry(exp) is None:
            bad.append(f"lease.expires {exp!r} is not an ISO-8601 timestamp")
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


FENCE_RE = re.compile(r"^ {0,3}(?P<f>`{3,}|~{3,})(?P<info>.*)$")


def _fenced(lines: list[str]) -> list[bool]:
    """One bool per line: is it inside a fenced code block (delimiters count)?

    Every heading scan in this module consults this. Ticket bodies carry raw
    test output inside fences -- gate.py embeds up to 1200 chars of it -- so a
    `## ` or `### ` line in that output is captured data, not a heading.
    Reading it as one splits the section and truncates the thread, and every
    later entry becomes unreachable to a stage reading the thread as data.

    CommonMark's closing rule, because the cheap version gets the embeds
    wrong: a closing fence is the same character, at least as long as the
    opener, and carries no info string.
    """
    out: list[bool] = []
    fence: tuple[str, int] | None = None
    for line in lines:
        m = FENCE_RE.match(line)
        if m is None:
            out.append(fence is not None)
            continue
        out.append(True)  # a delimiter is never a heading either way
        f, info = m.group("f"), m.group("info")
        if fence is None:
            fence = (f[0], len(f))
        elif f[0] == fence[0] and len(f) >= fence[1] and not info.strip():
            fence = None
    return out


def sections(body: str) -> dict[str, str]:
    """Map '## Name' -> its content. Content may be empty."""
    out, name, buf = {}, None, []
    lines = body.splitlines()
    for line, fenced in zip(lines, _fenced(lines)):
        m = None if fenced else re.match(r"^##\s+(.+?)\s*$", line)
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
    fenced = _fenced([l.rstrip("\n") for l in lines])
    start = next((i for i, l in enumerate(lines)
                  if not fenced[i] and re.match(r"^##\s+Thread\s*$", l)), None)
    if start is None:
        return body.rstrip() + "\n\n## Thread\n" + entry
    end = next((i for i in range(start + 1, len(lines))
                if not fenced[i] and re.match(r"^##\s+\S", lines[i])), len(lines))
    rest = "".join(lines[end:])
    return "".join(lines[:end]).rstrip() + "\n" + entry + (f"\n{rest}" if rest else "")


def tickets_dir(project: Path | str) -> Path:
    # Coerce: every caller here holds a Path, but the CLI, the daemon's
    # registry and the socket protocol all carry projects as strings, and
    # `"/tmp/x" / ".project"` is a TypeError naming neither the argument nor
    # the function.
    return Path(project) / ".project" / "tickets"


def ticket_path(project: Path | str, tid: str) -> Path:
    return tickets_dir(project) / f"{tid}.md"


def all_tickets(project: Path | str) -> list[Path]:
    d = tickets_dir(project)
    return sorted(d.glob("*.md")) if d.is_dir() else []


def result_file(project: Path, tid: str) -> Path:
    return tickets_dir(project) / f"{tid}.result"


SIDECAR_KEYS = ("result", "summary", "test_file")


def loose_result(text: str) -> dict:
    """The sidecar when YAML will not read it.

    A stage's job is to report what it saw, and what it saw is error text:
    `AssertionError: raw mode never reached the pty: b'\\r'`. Written as a
    plain scalar that is a ScannerError -- "mapping values are not allowed
    here" -- and the whole verdict used to become `{}`, which reads as `fail`.
    A correct `result: ok` with a committed test escalated twice in ten minutes
    that way, with an empty reason in the thread, because the summary contained
    a colon.

    So: line-based, first `key: rest-of-line` wins, `- item` collects under
    `files_declared`. Nothing here is trusted -- `apply_claims()` and
    `validate_meta()` check every value exactly as they do for the YAML path,
    which is what makes a looser parser safe rather than a second front door.
    """
    data: dict = {}
    files: list[str] = []
    in_files = False
    for line in text.splitlines():
        if line.startswith("- ") or line.startswith("  - "):
            if in_files:
                files.append(line.split("- ", 1)[1].strip())
            continue
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        in_files = key == "files_declared"
        if key in SIDECAR_KEYS and key not in data:
            data[key] = rest.strip()
    if files:
        data["files_declared"] = files
    return data


def read_result(project: Path, tid: str, keep: bool = False) -> dict | None:
    p = result_file(project, tid)
    if not p.is_file():
        return None
    text = p.read_text()
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        data = loose_result(text)
    if not isinstance(data, dict):
        data = loose_result(text)
    if not keep:
        p.unlink()
    # L7: the verdict stays on disk until it has actually been acted on, so a
    # crash between reading and applying it does not lose the stage's work
    return data


def drop_result(project: Path, tid: str) -> None:
    result_file(project, tid).unlink(missing_ok=True)


# `t.id` is a control field: it only reaches here already checked against
# SAFE_ID (every save() validates on the way out, and start() escalates a
# loaded ticket whose frontmatter fails errors() before it can advance()).
# `supersedes:` is different -- it is agent-written prose living in the same
# body a plan is free to hand-edit, and it becomes a filename below, so it
# gets its own check before touching a path. CLAUDE.md invariant 5.
SUPERSEDES_RE = re.compile(r"^supersedes:\s*(?P<id>\S+)(?:\s*--\s*(?P<reason>.*))?\s*$")
SAFE_DEC_ID = re.compile(r"^DEC-\d{1,6}$")

# The footer `record_decision` appends to a superseded record. A record's
# BODY is agent-written prose too, and could itself contain a line that
# happens to start with "- superseded-by:" -- a loose text scan would then
# drop an unrelated, still-active record from `active_decisions()` on
# nothing more than a coincidental line. The marker is what we actually
# search for, and it is never emitted anywhere except by the append below.
SUPERSEDED_MARKER = "<!-- pipeline:superseded-by -->"


@dataclass(frozen=True)
class Decision:
    """One row of `.project/decisions/` -- what `active_decisions()` hands
    a planning agent instead of a raw grep."""
    id: str
    path: Path
    text: str


def decisions_dir(project: Path) -> Path:
    return project / ".project" / "decisions"


def _refuse_symlink(p: Path) -> None:
    """A decision record's path is built from a name already checked against
    SAFE_DEC_ID, but that check is on the *name*, not the *path* -- nothing
    stops something else from having planted a symlink there first. Following
    it would turn a write (or a planning agent's read) into one against
    whatever the link points at. CLAUDE.md invariant 5: hostile, so refuse
    rather than follow."""
    if p.is_symlink():
        raise PipelineError(f"{p}: refusing to follow a symlink in decisions/")


def active_decisions(project: Path) -> list[Decision]:
    """Decision records nobody has superseded -- what still binds a plan.
    A record carrying the superseded footer stays on disk (it is still the
    reason something was once done that way) but drops out of this list."""
    d = decisions_dir(project)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("DEC-*.md")):
        if p.is_symlink():
            continue  # never follow a planted symlink into an active listing
        text = p.read_text()
        if SUPERSEDED_MARKER not in text:
            out.append(Decision(id=p.stem, path=p, text=text))
    return out


def record_decision(project: Path, t: "Ticket") -> str | None:
    """Copy the ticket's `## Decisions` into `.project/decisions/`. Planning
    greps that directory, so a check meant to stop you reverting a deliberate
    fix needs data there to find.

    A `## Decisions` section may open with `supersedes: DEC-003 -- reason`:
    the new record gets a `supersedes:` header and the old record gets an
    *appended* footer -- never rewritten, since a superseded decision is
    still the reason something was once done that way. A `supersedes:`
    naming a bad, absent, or symlinked id is left as plain text in the new
    record and reported as a `finding` in the thread, not applied and not a
    crash.
    """
    text = t.section("Decisions").strip()
    if not text:
        return None
    d = decisions_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    did = f"DEC-{t.id.split('-')[-1]}"
    if not SAFE_DEC_ID.match(did):
        # Unreachable in the live pipeline -- t.id is SAFE_ID-checked before
        # advance() ever calls this -- but record_decision is a public,
        # directly-callable function and this filename is built from it, so
        # invariant 5 ("both, not either") gets checked here too rather than
        # only trusted upstream.
        raise PipelineError(f"{t.id!r} does not yield a valid decision id")

    lines = text.splitlines()
    m = SUPERSEDES_RE.match(lines[0]) if lines else None
    body_text, supersedes_id, reason = text, None, ""
    if m:
        raw_id = m.group("id")
        reason = (m.group("reason") or "").strip()
        old_path = d / f"{raw_id}.md" if SAFE_DEC_ID.match(raw_id) else None
        if old_path is None:
            t.append(t.stage, "finding",
                     f"`## Decisions` tried to supersede {raw_id!r}, which is "
                     "not a valid decision id (want DEC-<digits>); recorded "
                     "as plain text, nothing superseded", severity="minor")
        elif old_path.is_symlink() or not old_path.is_file():
            t.append(t.stage, "finding",
                     f"`## Decisions` tried to supersede {raw_id!r}, which "
                     "does not name an existing decision record; recorded "
                     "as plain text, nothing superseded", severity="minor")
        else:
            supersedes_id = raw_id
            body_text = "\n".join(lines[1:]).strip()

    header = (f"# {did}\n\n"
              f"- ticket: {t.id} ({t.klass})\n"
              f"- branch: {t.branch}\n"
              f"- files: {', '.join(t.files_declared) or 'n/a'}\n"
              f"- decided: {now().date().isoformat()}\n")
    if supersedes_id:
        header += f"- supersedes: {supersedes_id}\n"
    new_path = d / f"{did}.md"
    _refuse_symlink(new_path)
    # write_atomic, not write_text: planning agents grep this directory
    # concurrently (`max_parallel`), and a half-written record must not be
    # observable any more than a half-written ticket is.
    write_atomic(new_path, f"{header}\n{body_text}\n")

    if supersedes_id:
        old_path = d / f"{supersedes_id}.md"
        _refuse_symlink(old_path)
        old_text = old_path.read_text()
        if SUPERSEDED_MARKER not in old_text:
            # Idempotency guard: a crash-recovery respawn (lease expiry) can
            # replay this same transition and call record_decision() again
            # for the same ticket. Without this check a replay would append a
            # second, duplicate footer every time it fires.
            reason_part = f"{reason}, " if reason else ""
            write_atomic(old_path, old_text.rstrip("\n") +
                         f"\n\n{SUPERSEDED_MARKER}\n- superseded-by: {did} "
                         f"({reason_part}{now().date().isoformat()})\n")

    return did


# --------------------------------------------------------------------------
# the model
# --------------------------------------------------------------------------

# The vocabulary a stage may write. Reading stays lenient; writing does not,
# because an invented kind is a typo nothing would ever notice.
KINDS = frozenset({"note", "transition", "gate", "question", "answer", "finding",
                   "escalation", "approval", "rejection", "session", "decision"})

# What a stage is asked to read. The thread is the only part of a ticket
# that grows without bound -- 46168 of TICKET-016's 56294 bytes (82%)
# were inside `## Thread` -- because every other section is REWRITTEN by
# the stage that owns it. These kinds are never omitted: each carries a
# human's words, or the reason a ticket previously stopped, and a stage
# that acts without them acts against a decision somebody already made.
VIEW_KEEP_KINDS = frozenset({"question", "answer", "rejection",
                             "approval", "escalation", "decision"})
VIEW_RECENT = 8      # trailing entries of any kind, always kept
VIEW_CLIP = 2000     # chars per entry that is kept only for recency


def _view_keep(e: "ThreadEntry") -> bool:
    return (e.kind in VIEW_KEEP_KINDS
            or (e.kind == "finding" and e.attrs.get("severity") == "blocking"))


def stage_view(t: "Ticket", stage: str) -> str:
    """The ticket as a stage is asked to read it: every section except
    `## Thread` verbatim, and a bounded slice of the thread.

    The bound does not depend on how many stages ran before. Sections
    are kept whole because they are rewritten, not appended to; only
    the thread grows with stage count.

    DEC-016 is why nothing is dropped silently: an omitted entry
    becomes a counted marker naming the ticket, so a stage that needs
    an older entry knows it exists and where to read it.

    `stage` names the reader in the header. There is deliberately no
    per-stage kind filter: a filter that guesses wrong drops what a
    stage needed, which is the failure TICKET-016 recorded.
    """
    entries = t.thread()
    keep = {i for i, e in enumerate(entries) if _view_keep(e)}
    keep |= set(range(max(0, len(entries) - VIEW_RECENT), len(entries)))
    out = [
        f"# {t.id} -- bounded view for the `{stage}` stage", "",
        f"The full ticket is {t.path}. Every section except `## Thread` "
        f"is below in full; the thread is trimmed to {len(keep)} of "
        f"{len(entries)} entries. To read an omitted entry, run "
        f"`grep -n {chr(39)}^### {chr(39)} {t.path}` and read only that range.", "",
    ]
    for name, text in t.sections().items():
        if name != "Thread":
            out += [f"## {name}", "", text, ""]
    out += ["## Thread (bounded view)", ""]
    gap = 0
    for i, e in enumerate(entries):
        if i not in keep:
            gap += 1
            continue
        if gap:
            out += [f"*-- {gap} earlier entries omitted; "
                    f"they are in {t.path} --*", ""]
            gap = 0
        text = e.text
        if not _view_keep(e) and len(text) > VIEW_CLIP:
            text = (text[:VIEW_CLIP] + f"\n\n*-- clipped here; the full "
                    f"{len(e.text)} chars are in {t.path} --*")
        out += [f"### {e.raw}", "", text, ""]
    return "\n".join(out).rstrip() + "\n"

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
    raw: str = ""            # the `### ` line as written; a view reprints it


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
    def find(cls, project: Path | str, tid: str) -> "Ticket":
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
        head, raw, buf = None, "", []
        lines = self.section("Thread").splitlines()
        for line, fenced in zip(lines, _fenced(lines)):
            if line.startswith("### ") and not fenced:
                if head is not None:
                    out.append(ThreadEntry(*head, "\n".join(buf).strip(), raw))
                head, raw, buf = _parse_header(line[4:]), line[4:], []
            elif head is not None:
                buf.append(line)
        if head is not None:
            out.append(ThreadEntry(*head, "\n".join(buf).strip(), raw))
        return out

    # -- lease ------------------------------------------------------------
    def lease_active(self) -> bool:
        """Total: an unreadable `expires` is not a lease. `validate_meta` is
        what escalates the ticket carrying one -- this must still answer, or
        `ls` (which runs before any validation) dies on one bad file."""
        exp = lease_expiry((self.lease or {}).get("expires"))
        return exp is not None and now() < exp

    def take_lease(self, holder: str, minutes: int = LEASE_MINUTES) -> None:
        self.lease = {"holder": holder,
                      "expires": (now() + timedelta(minutes=minutes)).isoformat()}

    def release_lease(self) -> None:
        self.lease = {"holder": None, "expires": None}
