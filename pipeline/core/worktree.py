"""Running project commands, and the per-ticket checkout they run in."""
import os
import shlex
import subprocess
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
           f"{shlex.quote(str(cfg.get('base', 'main')))}")
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


def tree_snapshot(project: Path) -> str:
    """What a read-only stage must not change. `.project/` is excluded: writing
    to the ticket and the .result sidecar is every stage's job, including the
    read-only ones."""
    _, head = run_cmd("git rev-parse HEAD", project)
    _, dirty = run_cmd("git status --porcelain -- . ':(exclude).project'", project)
    return head + dirty
