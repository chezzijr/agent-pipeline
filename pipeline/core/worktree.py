"""Running project commands, and the per-ticket checkout they run in."""
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

EAGAIN_TRIES = 4
EAGAIN_BACKOFF = 0.25
OUTPUT_EDGE = 2000
FETCH_TIMEOUT = 20
# The prefix `gate._base_findings()` matches to tell a setup failure from a
# failed `git worktree add`.
SETUP_FAILED = "worktree_setup exited "


def retry_eagain(fn, tries: int = EAGAIN_TRIES, backoff: float = EAGAIN_BACKOFF, sleep=time.sleep):
    """Call `fn()`, retrying a transient `BlockingIOError` with backoff.

    `fork` returns EAGAIN when the machine is at its process limit
    (systemd `TasksMax`, `RLIMIT_NPROC`); Python raises `BlockingIOError` and
    the condition clears within a second. Every spawn primitive goes through
    here, so one EAGAIN ends neither the stage, the tick, nor the loop.
    """
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except BlockingIOError as e:
            if attempt == tries:
                raise
            delay = backoff * 2 ** (attempt - 1)
            print(f"  spawn hit EAGAIN ({e}); retry {attempt}/{tries - 1} in {delay:.2f}s")
            sleep(delay)


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


def bounded_output(output: str) -> str:
    if len(output) <= OUTPUT_EDGE * 2:
        return output
    omitted = len(output) - OUTPUT_EDGE * 2
    return (output[:OUTPUT_EDGE] + f"\n... {omitted} characters omitted ...\n"
            + output[-OUTPUT_EDGE:])


def run_cmd(cmd: str, cwd: Path) -> tuple[int, str]:
    p = retry_eagain(lambda: subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                                             text=True, env=project_env()))
    return p.returncode, bounded_output(p.stdout + p.stderr)


def worktree(project: Path, meta: dict) -> Path:
    return project / ".worktrees" / meta["id"]


def base_ref(cfg: dict) -> str:
    """One default for base, so the gate and the ticket's own checkout can
    never drift apart."""
    return str(cfg.get("base", "main"))


def _first_line(out: str) -> str:
    return next((l.strip() for l in out.splitlines() if l.strip()), "")


def base_upstream(project: Path, cfg: dict) -> str | None:
    """The upstream ref base tracks (`origin/main`), or None when it tracks nothing."""
    code, out = run_cmd("git rev-parse --abbrev-ref --symbolic-full-name "
                        + shlex.quote(base_ref(cfg) + "@{upstream}"), project)
    return (_first_line(out) or None) if code == 0 else None


def base_lag(project: Path, cfg: dict) -> tuple[str, int] | None:
    """(upstream, commits local base is behind it) as of the last fetch. Read-only."""
    up = base_upstream(project, cfg)
    if up is None:
        return None
    base = base_ref(cfg)
    code, out = run_cmd("git rev-list --count " + shlex.quote(f"{base}..{base}@{{upstream}}"), project)
    n = _first_line(out)
    return (up, int(n)) if code == 0 and n.isdigit() else None


def fetch_base(project: Path, cfg: dict, timeout: int = FETCH_TIMEOUT) -> str | None:
    """Fetch base's remote. None on success or when there is nothing to fetch, else the error.

    A plain remote fetch only updates `refs/remotes/`, never a local branch, so
    the main checkout's branch cannot move. Bounded: this runs on the
    dispatcher's loop."""
    if base_upstream(project, cfg) is None:
        return None
    _, out = run_cmd("git config --get " + shlex.quote(f"branch.{base_ref(cfg)}.remote"), project)
    remote = _first_line(out)
    if not remote or remote == "." or remote.startswith("-"):
        return None
    try:
        p = retry_eagain(lambda: subprocess.run(
            ["git", "fetch", "--quiet", remote], cwd=project, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=timeout,
            env={**project_env(), "GIT_TERMINAL_PROMPT": "0"}))
    except subprocess.TimeoutExpired:
        return f"git fetch {remote} timed out after {timeout}s"
    except OSError as e:
        return f"git fetch {remote} failed: {e}"
    if p.returncode:
        return f"git fetch {remote} exited {p.returncode}: {_first_line(p.stderr)}"
    return None


LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock",
             "poetry.lock", "Gemfile.lock")


def unset_setup_lockfile(project: Path, cfg: dict) -> str | None:
    """The lockfile at the project root when `worktree_setup` is unset, else None.

    A ticket worktree is a fresh checkout with no dependencies installed; a
    lockfile at the project root says the project needs some."""
    if cfg.get("worktree_setup"):
        return None
    return next((n for n in LOCKFILES if (project / n).is_file()), None)


def ensure_worktree(project: Path, meta: dict, cfg: dict,
                    notes: list[str] | None = None) -> Path | None:
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
    if not branch_exists:
        base = base_ref(cfg)
        msgs = []
        err = fetch_base(project, cfg)
        if err:
            msgs.append(f"could not fetch `{base}`'s upstream ({err}); comparing against the last fetched copy")
        lag = base_lag(project, cfg)
        if lag and lag[1] > 0:
            msgs.append(f"`{meta['branch']}` is cut from local `{base}`, which is {lag[1]} commit(s) "
                        f"behind `{lag[0]}` -- every stage of this ticket sees the older code. "
                        f"`git pull --ff-only` on `{base}` in the main checkout catches it up for later tickets.")
        for m in msgs:
            print(f"  {meta['id']}: {m}")
            if notes is not None:
                notes.append(m)
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
        # per-project: copy .env, install deps, key a build cache to THIS
        # worktree. A cache shared across worktrees unkeyed serves one
        # ticket's artifact into another's build -- see README.
        code, out = run_cmd(cfg["worktree_setup"], wt)
        if code:
            print(f"  worktree_setup failed for {meta['id']} (exit {code}): {out.strip()[:300]}")
            # A checkout left behind is returned as ready by the `wt.is_dir()`
            # early return and setup never re-runs. The branch is kept.
            drop_worktree(project, meta, cfg)
            return None
    return wt


def drop_worktree(project: Path, meta: dict, cfg: dict | None = None) -> None:
    wt = worktree(project, meta)
    if wt.is_dir():
        if (cfg or {}).get("worktree_teardown"):
            code, out = run_cmd(cfg["worktree_teardown"], wt)
            if code:
                print(f"  worktree_teardown failed for {meta['id']}: {out.strip()[:300]}")
        run_cmd(f"git worktree remove --force {shlex.quote(str(wt))}", project)


@contextmanager
def base_checkout(project: Path, cfg: dict):
    """A throwaway detached checkout of base, outside the repo, for running a
    ticket's test against the code the ticket branched from. Yields
    `(path, "")`, or `(None, git's output)` when base cannot be checked out.
    It also yields `(None, ...)` when `worktree_setup` fails, because a base
    run without the project's dependencies proves nothing.

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
            setup_code, setup_out = (run_cmd(cfg["worktree_setup"], wt)
                                     if cfg.get("worktree_setup") else (0, ""))
            if setup_code:
                print(f"  worktree_setup failed in the base checkout (exit {setup_code}): "
                      f"{setup_out.strip()[:300]}")
                yield None, f"{SETUP_FAILED}{setup_code} in the base checkout\n{setup_out}"
                return
            yield wt, ""
    finally:
        if not code:
            if cfg.get("worktree_teardown"):
                code2, out2 = run_cmd(cfg["worktree_teardown"], wt)
                if code2:
                    print(f"  worktree_teardown failed in the base checkout: {out2.strip()[:300]}")
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


def head_file(project: Path, rel: str) -> str | None:
    """The content of `rel` at `project`'s HEAD commit, or None if git has none.

    None means git could not answer -- not a repo, no commit yet, or the
    path is untracked -- and the caller falls back to the working tree.
    `HEAD:./<rel>` resolves relative to cwd, so a project inside a
    subdirectory of its repo reads its own copy.

    Not `run_cmd()`: that bounds and merges stdout with stderr, which would
    corrupt a long tracked file.
    """
    if not project.is_dir():
        return None
    p = subprocess.run(f"git show {shlex.quote('HEAD:./' + rel)}", shell=True,
                       cwd=project, capture_output=True, text=True,
                       errors="replace", env=project_env())
    return p.stdout if p.returncode == 0 else None


def git_ignored(project: Path, rel: str) -> bool:
    """Whether git will NEVER have `rel` -- excluded by `.gitignore` or by the
    `.git/info/exclude` line `pipeline init --private` writes -- as opposed to
    `head_file()` returning None for "git does not have it yet". `check-ignore
    -q` exits 0 ignored, 1 not ignored, 128 outside a repo, so a non-repo
    reads as not ignored."""
    if not project.is_dir():
        return False
    return run_cmd(f"git check-ignore -q -- {shlex.quote(rel)}", project)[0] == 0


def tree_snapshot(project: Path) -> str:
    """What a read-only stage must not change. `.project/` is excluded: writing
    to the ticket and the .result sidecar is every stage's job, including the
    read-only ones."""
    _, head = run_cmd("git rev-parse HEAD", project)
    return head + dirty_snapshot(project)


def dirty_snapshot(project: Path) -> str:
    """The main-checkout baseline for a read-only stage. Omits HEAD: `merging`
    fast-forwards the base branch in the main checkout while other tickets'
    stages run, and a baseline carrying HEAD would escalate every read-only
    stage whose run overlapped that."""
    _, dirty = run_cmd("git status --porcelain -- . ':(exclude).project'", project)
    return dirty


EXCLUDE_LINE = ".project/"
WORKTREES_LINE = ".worktrees/"


def exclude_project_dir(project: Path, extra: tuple[str, ...] = ()) -> str | None:
    """Hide `.project/`, `.worktrees/` and the given skill directories from
    git for THIS clone only, via `.git/info/exclude`.

    For a shared repo where not everyone runs the pipeline. `.gitignore` is the
    wrong file for that: it is tracked, so it puts a line about a tool the rest
    of the team does not use into their diffs. `.git/info/exclude` is per-clone
    and never committed, which is exactly the shape of "I use this, they don't".

    A team that all runs the pipeline and still wants tickets out of history
    wants the tracked file instead -- one deliberate line in `.gitignore`,
    reviewed like any other shared decision. That case is not automated here on
    purpose.

    Returns the path written, or None if this is not a git repo or the line was
    already there. Idempotent: `init` is safe to re-run.
    """
    code, out = run_cmd("git rev-parse --git-dir", project)
    if code:
        return None                      # not a git repo; nothing to exclude
    # `--git-dir` is relative to `project` for a normal checkout and absolute
    # inside a worktree, and `info/` does not exist in a fresh clone.
    git_dir = Path(out.strip())
    if not git_dir.is_absolute():
        git_dir = project / git_dir
    info = git_dir / "info"
    info.mkdir(parents=True, exist_ok=True)
    f = info / "exclude"
    body = f.read_text() if f.is_file() else ""
    held = body.split()
    missing = [ln for ln in dict.fromkeys((EXCLUDE_LINE, WORKTREES_LINE, *extra))
               if ln not in held]
    if not missing:
        return None
    f.write_text(body + ("" if body.endswith("\n") or not body else "\n")
                 + "".join(f"{ln}\n" for ln in missing))
    return str(f)


MIRROR_MODE = 0o444


def mirror_ticket(live: Path, text: str) -> Path | None:
    """Write `text` into the ticket's own worktree, read-only.

    Called only by `Ticket.save()`, so invariant 5 keeps one writer: this
    mirrors the same write, it does not add a second one. The
    `--skip-worktree` mark runs in the worktree's OWN index, never the main
    checkout's, before the write -- so it also repairs a worktree an earlier
    stage already dirtied. A non-zero rc there means the path is untracked in
    that worktree or its index is locked; returning None fails toward a stale
    mirror rather than toward a dirty worktree.
    """
    if live.parent.name != "tickets" or live.parents[1].name != ".project":
        return None
    rel = ".project/tickets/" + live.name
    wt = live.parents[2] / ".worktrees" / live.stem
    dest = wt / rel
    if not dest.is_file():
        return None
    if run_cmd(f"git update-index --skip-worktree -- {shlex.quote(rel)}", wt)[0]:
        return None
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(text)
    os.chmod(tmp, MIRROR_MODE)
    os.replace(tmp, dest)
    return dest
