"""Running project commands, and the per-ticket checkout they run in."""
import os
import shlex
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


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


def worktree(project: Path, meta: dict) -> Path:
    return project / ".worktrees" / meta["id"]


def base_ref(cfg: dict) -> str:
    """One default for base, so the gate and the ticket's own checkout can
    never drift apart."""
    return str(cfg.get("base", "main"))


def ensure_worktree(project: Path, meta: dict, cfg: dict) -> Path | None:
    """A ticket owns a checkout. Two tickets cannot share one, which is why
    concurrency and worktrees arrive together. Scripted, never improvised by an
    agent -- that is where 'forgot the env file' bugs come from."""
    wt = worktree(project, meta)
    if wt.is_dir():
        return wt
    wt.parent.mkdir(parents=True, exist_ok=True)
    branch = shlex.quote(meta["branch"])
    rc, _ = run_cmd(f"git rev-parse --verify --quiet {branch}", project)
    branch_exists = rc == 0
    # Never `-B`: it RESETS the branch to base, so re-creating a worktree after
    # a resume would silently discard every commit the ticket already made.
    add = (f"git worktree add {shlex.quote(str(wt))} {branch}" if branch_exists else
           f"git worktree add -b {branch} {shlex.quote(str(wt))} "
           f"{shlex.quote(base_ref(cfg))}")
    code, out = run_cmd(add, project)
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


@contextmanager
def base_checkout(project: Path, cfg: dict):
    """A throwaway detached checkout of base, outside the repo, for running a
    ticket's test against the code the ticket branched from. Yields
    `(path, "")`, or `(None, git's output)` when base cannot be checked out.

    Always removed. It is not a ticket's checkout: nothing resumes in it and
    nothing may be left behind for a human to look at."""
    tmp = Path(tempfile.mkdtemp(prefix="pipeline-base-"))
    wt = tmp / "base"
    code, out = run_cmd(
        f"git worktree add --detach {shlex.quote(str(wt))} "
        f"{shlex.quote(base_ref(cfg))}", project)
    try:
        if code:
            yield None, out
        else:
            if cfg.get("worktree_setup"):
                run_cmd(cfg["worktree_setup"], wt)
            yield wt, ""
    finally:
        if not code:
            run_cmd(f"git worktree remove --force {shlex.quote(str(wt))}", project)
        shutil.rmtree(tmp, ignore_errors=True)


SETTINGS_SOURCES = (".claude/settings.json", ".claude/settings.local.json")


def strip_settings_sources(wt: Path) -> list[str]:
    """Remove the worktree's own settings sources before a spawn.

    `--settings` registers the guard hook, but Claude Code merges the
    worktree's project settings source ahead of it -- no flag ordering can
    win, so the file has to be gone before launch. A tracked file is marked
    `--skip-worktree` after the delete, so the removal never shows up in
    `git status` and never enters the ticket's own diff.
    """
    removed = []
    for rel in SETTINGS_SOURCES:
        path = wt / rel
        if not (path.is_file() or path.is_symlink()):
            continue
        tracked = run_cmd(f"git ls-files --error-unmatch -- {shlex.quote(rel)}", wt)[0] == 0
        path.unlink()
        if tracked:
            run_cmd(f"git update-index --skip-worktree -- {shlex.quote(rel)}", wt)
        removed.append(rel)
    return removed


def tree_snapshot(project: Path) -> str:
    """What a read-only stage must not change. `.project/` is excluded: writing
    to the ticket and the .result sidecar is every stage's job, including the
    read-only ones."""
    _, head = run_cmd("git rev-parse HEAD", project)
    _, dirty = run_cmd("git status --porcelain -- . ':(exclude).project'", project)
    return head + dirty
