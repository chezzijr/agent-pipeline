"""Which projects the one global daemon watches, and who owns each of them.

A text file, not SQLite: deleting `events.db` must lose history and never
state, and the project list is state. It is also greppable and hand-editable,
like every other file this tool owns.
"""
import fcntl
import os
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.core.ticket import write_atomic


def config_dir() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(root) / "pipeline"


def registry_path() -> Path:
    return config_dir() / "projects"


def _raw() -> list[str]:
    """The file as written, comments and all. Rewriting the registry preserves
    what a human put there; `projects()` is the filtered view for consumers."""
    p = registry_path()
    return p.read_text().splitlines() if p.is_file() else []


def _write(lines: list[str]) -> None:
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # atomic, like every other file this tool rewrites: the daemon re-reads
    # this on every tick, and a reader that caught a truncated file would see
    # an empty registry and release every project it is watching
    write_atomic(p, "".join(f"{l}\n" for l in lines))


def projects() -> list[Path]:
    """One absolute path per line, `#` comments. Re-read every tick -- a stat
    plus a 200-byte read is cheaper than the cache that would avoid it.

    A line is hand-editable, so it is checked like any other input: only an
    absolute path to an existing `.project/` is returned. Without that,
    `lock()`'s `mkdir(parents=True)` would happily scaffold a `.project/` at
    whatever a typo named, and `serve()` would then tick it.
    """
    out: list[Path] = []
    for line in _raw():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        q = Path(line)
        if q.is_absolute() and (q / ".project").is_dir() and q not in out:
            out.append(q)
    return out


def register(project: Path) -> Path:
    project = Path(project).resolve()
    if not (project / ".project").is_dir():
        raise PipelineError(f"{project} has no .project/ -- run `pipeline init` first")
    if "\n" in str(project) or "#" in str(project):
        # one path per line, `#` comments: a path carrying either would inject
        # a second entry or silently truncate this one
        raise PipelineError(f"{project!r} cannot be registered: newline or '#'")
    if project in projects():
        return project
    _write(_raw() + [str(project)])
    return project


def unregister(project: Path) -> bool:
    """Drops the line, not the filtered entry: a project whose directory has
    since been deleted no longer shows up in `projects()` and must still be
    removable."""
    project = Path(project).resolve()
    keep = [l for l in _raw() if Path(l.split("#", 1)[0].strip() or "/dev/null")
            != project]
    if len(keep) == len(_raw()):
        return False
    _write(keep)
    return True


def lock(project: Path):
    """Exclusive claim on one project's dispatcher.

    Two supervisors on one project double-spawn: the ticket lease does not stop
    it, because both see no lease in the same second and both take one. `flock`
    does, and the kernel releases it on crash -- so there is no stale-lockfile
    path to get wrong. Returns the open file (keep it: closing it unlocks) or
    None if someone else already owns this project.
    """
    d = Path(project) / ".project"
    d.mkdir(parents=True, exist_ok=True)
    fh = (d / ".lock").open("w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh
