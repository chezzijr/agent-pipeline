"""Which fenced symbols a branch's diff touches.

`CLAUDE.md` fences five things off from unattended merge. `machine.FENCED` is
the machine-readable copy; this is the check. A whole-file entry (`None`) trips
on any hunk. A symbol entry trips only when a hunk overlaps that symbol's own
line range, so a ticket that edited a neighbouring function is not parked.
"""
import ast
import re
import subprocess
from pathlib import Path

from pipeline.core.machine import FENCED
from pipeline.core.worktree import project_env


def hunks(diff: str) -> dict[str, list[tuple[int, int]]]:
    """path -> new-side line ranges, off `git diff --unified=0`.

    A deleted file has `+++ /dev/null`, so the `--- a/` path is carried over:
    dropping it would let "delete the guard entirely" read as an empty diff.
    """
    out: dict[str, list[tuple[int, int]]] = {}
    old = path = None
    for line in diff.splitlines():
        if line.startswith("--- "):
            old = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else old
            if path:
                out.setdefault(path, [])
        elif line.startswith("@@") and path:
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start = int(m.group(1))
                n = 1 if m.group(2) is None else max(int(m.group(2)), 1)
                out[path].append((start, start + n - 1))
    return out


def symbol_lines(src: str, name: str) -> tuple[int, int] | None:
    """A top-level def/class/assignment's line span, or None if it is gone.

    Decorators count: `node.lineno` is the `def` line, so a hunk that edited
    only a decorator would otherwise miss.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        else:
            names = [t.id for t in getattr(node, "targets", [])
                     if isinstance(t, ast.Name)]
        if name in names:
            starts = [node.lineno] + [d.lineno
                                      for d in getattr(node, "decorator_list", [])]
            return min(starts), node.end_lineno
    return None


def fenced_touches(wt: Path, base: str, fenced: dict = FENCED) -> list[str]:
    """Names of the fenced things this worktree's diff touches.

    Two dots against the merge base, NOT `base...HEAD`: three dots sees
    committed work only, and an uncommitted edit to the guard must not slip
    through.
    """
    def git(cmd: str) -> str:
        return subprocess.run(f"git {cmd}", shell=True, cwd=wt, capture_output=True,
                              text=True, env=project_env()).stdout

    mb = git(f"merge-base {base} HEAD").strip()
    if not mb:
        return ["fence check found no merge base"]   # fail closed
    changed = hunks(git(f"diff --unified=0 {mb}"))
    hits = []
    for path, symbols in fenced.items():
        ranges = changed.get(path)
        if ranges is None:
            continue
        if symbols is None:
            hits.append(path)
            continue
        f = Path(wt) / path
        src = f.read_text(errors="replace") if f.is_file() else ""
        for sym in symbols:
            span = symbol_lines(src, sym)
            if span is None:
                hits.append(f"{path}:{sym} (gone)")
            elif any(a <= span[1] and span[0] <= b for a, b in ranges):
                hits.append(f"{path}:{sym}")
    return hits
