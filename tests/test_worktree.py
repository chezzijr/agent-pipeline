"""Per-ticket checkouts, and the venv the project's commands must not inherit."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from helpers import git_project
from pipeline.core import worktree as W
from pipeline.core.ticket import Ticket, stage_view

TICKET_TEXT = """---
id: TICKET-001
stage: new
class: bugfix
branch: ticket/001
test_file: null
files_declared: []
counters: {}
lease: {holder: null, expires: null}
---

## Summary
x
## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Rollback

## Thread
"""


def test_recreating_a_worktree_never_resets_the_branch():
    """`git worktree add -B` resets to base -- it would silently discard every
    commit a ticket made before it was escalated or resumed."""
    d, sh = git_project()
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    cfg = {"base": "main"}
    wt = W.ensure_worktree(d, meta, cfg)
    (wt / "new.py").write_text("ticket work\n")
    subprocess.run("git add -A && git commit -qm 'ticket commit'", shell=True,
                   cwd=wt, capture_output=True)
    before = sh("git rev-parse ticket/001").stdout.strip()

    W.drop_worktree(d, meta)
    W.ensure_worktree(d, meta, cfg)          # the resume path
    after = sh("git rev-parse ticket/001").stdout.strip()

    assert after == before, "recreating the worktree discarded the ticket's commits"
    assert "ticket commit" in sh("git log --oneline ticket/001").stdout
    shutil.rmtree(d, ignore_errors=True)


def test_project_commands_do_not_inherit_the_dispatchers_venv():
    """Assert the stripping actually happens, rather than passing by luck when
    the suite is run outside a venv."""
    fake = "/tmp/fake-venv-xyz"
    saved = dict(os.environ)
    os.environ["VIRTUAL_ENV"] = fake
    os.environ["PYTHONPATH"] = "/tmp/leak"
    os.environ["PATH"] = f"{fake}/bin:/usr/bin"
    try:
        env = W.project_env()
    finally:
        os.environ.clear(); os.environ.update(saved)
    assert "VIRTUAL_ENV" not in env
    assert "PYTHONPATH" not in env
    assert env["PATH"] == "/usr/bin", env["PATH"]


def test_the_main_checkout_baseline_ignores_a_merge_moving_head():
    """`dirty_snapshot()` is the main-checkout baseline: it must not move when
    `merging` fast-forwards the base branch there, only when a file changes.
    `tree_snapshot()` is the worktree baseline and tracks both."""
    d, sh = git_project()
    base = W.dirty_snapshot(d)
    tbase = W.tree_snapshot(d)

    sh("git commit -q --allow-empty -m moved")

    assert W.dirty_snapshot(d) == base
    assert W.tree_snapshot(d) != tbase
    tmid = W.tree_snapshot(d)

    (d / "stray.py").write_text("x\n")

    assert W.dirty_snapshot(d) != base
    assert W.tree_snapshot(d) != tmid
    shutil.rmtree(d, ignore_errors=True)


def test_stripping_settings_sources_removes_both_project_files():
    """`.claude/settings.json` = `{"disableAllHooks": true}` is a project
    settings source Claude Code merges ahead of `--settings`, so it drops the
    guard hook for every spawn in the worktree. `strip_settings_sources()` is
    the dispatcher-side removal; a second call must be a no-op."""
    d, sh = git_project()
    (d / ".claude").mkdir(parents=True)
    (d / ".claude" / "settings.json").write_text(json.dumps({"disableAllHooks": True}))
    (d / ".claude" / "settings.local.json").write_text(json.dumps({"disableAllHooks": True}))

    removed = W.strip_settings_sources(d)

    assert removed == [".claude/settings.json", ".claude/settings.local.json"], removed
    assert not (d / ".claude" / "settings.json").exists()
    assert not (d / ".claude" / "settings.local.json").exists()
    assert W.strip_settings_sources(d) == []
    shutil.rmtree(d, ignore_errors=True)


def test_a_tracked_settings_file_is_stripped_without_entering_the_diff():
    """A plain delete of a tracked file leaves ` D .claude/settings.json` in
    `git status`, which `implementing`'s `git commit -a` would fold into the
    ticket's own diff. `--skip-worktree` hides the deletion instead."""
    d, sh = git_project()
    (d / ".claude").mkdir(parents=True)
    (d / ".claude" / "settings.json").write_text(json.dumps({"disableAllHooks": True}))
    sh("git add .claude/settings.json && git commit -qm settings")

    W.strip_settings_sources(d)

    assert not (d / ".claude" / "settings.json").exists()
    status = sh("git status --porcelain").stdout
    assert ".claude/settings.json" not in status, status
    shutil.rmtree(d, ignore_errors=True)


def test_private_init_hides_the_project_dir_from_this_clone_only():
    """A shared repo where only you run the pipeline. `.gitignore` is the wrong
    file -- it is tracked, so it puts a line about a tool the rest of the team
    does not use into their diffs. `.git/info/exclude` is per-clone and never
    committed."""
    d, sh = git_project()
    wrote = W.exclude_project_dir(d)

    assert wrote and wrote.endswith(".git/info/exclude")
    assert not (d / ".gitignore").is_file(), "wrote a TRACKED ignore file"
    assert sh("git check-ignore -q .project").returncode == 0, \
        ".project is still visible to git"
    assert W.exclude_project_dir(d) is None, "not idempotent -- init re-run would duplicate"


def test_excluding_outside_a_git_repo_is_a_no_op_not_a_crash():
    """`pipeline init` works on a directory that is not a repo yet; it must
    still scaffold rather than blow up on the git call."""
    d = Path(tempfile.mkdtemp())
    assert W.exclude_project_dir(d) is None


def test_head_file_reads_the_commit_not_the_working_tree():
    """The dispatcher's own config is read through this. An uncommitted edit
    to a tracked file must be invisible, and a file git does not have must
    read as None so the caller can fall back to disk."""
    d, sh = git_project()
    (d / "f.py").write_text("dirty\n")
    assert W.head_file(d, "f.py") == "base\n"
    assert W.head_file(d, ".project/pipeline.toml") is None   # never committed
    sh("git add -A && git commit -qm commit-config")
    assert 'test_one="true"' in W.head_file(d, ".project/pipeline.toml")
    assert W.head_file(Path(tempfile.mkdtemp()), "f.py") is None  # not a repo


def test_git_ignored_separates_never_from_not_yet():
    """head_file() returns None for both a not-yet-committed file and a file
    git will never have. git_ignored() tells them apart."""
    d, sh = git_project()
    assert not W.git_ignored(d, ".project/pipeline.toml")
    (d / ".git" / "info").mkdir(exist_ok=True)
    (d / ".git" / "info" / "exclude").write_text(".project/\n")
    assert W.git_ignored(d, ".project/pipeline.toml")
    assert not W.git_ignored(Path(tempfile.mkdtemp()), ".project/pipeline.toml")  # not a repo


def test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress():
    """`ensure_worktree` checks out the branch at cut time. `Ticket.save()`
    (main checkout) records a stage's work without committing until merge, so
    the worktree's own `.project/tickets/<id>.md` freezes at `## Reproduction`
    empty while the view a later stage is handed already has it filled in --
    the TICKET-067 incident (see TICKET-083 Summary)."""
    d, sh = git_project()
    (d / ".project" / "tickets" / "TICKET-001.md").write_text(TICKET_TEXT)
    sh("git add -A && git commit -qm file-ticket")
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    cfg = {"base": "main"}
    wt = W.ensure_worktree(d, meta, cfg)

    t = Ticket.find(d, "TICKET-001")
    t.body = t.body.replace("## Reproduction\n\n", "## Reproduction\ntest fails: KeyError\n")
    t.save()

    view = stage_view(Ticket.find(d, "TICKET-001"), "planning")
    worktree_copy = (wt / ".project" / "tickets" / "TICKET-001.md").read_text()

    assert "KeyError" in view
    assert "KeyError" in worktree_copy, (
        "the worktree's own ticket file contradicts the view a stage is "
        "handed -- it is still the branch-cut snapshot")
    shutil.rmtree(d, ignore_errors=True)


def test_the_ticket_mirror_is_read_only_and_never_enters_the_branch_diff():
    """`Ticket.save()` mirrors the live ticket into the worktree at 0444,
    marked `--skip-worktree`, so the mirror never shows up in `git status`,
    never enters `implementing`'s own commit, and never blocks `merging`'s
    rebase (TICKET-083)."""
    d, sh = git_project()
    (d / ".project" / "tickets" / "TICKET-001.md").write_text(TICKET_TEXT)
    sh("git add -A && git commit -qm file-ticket")
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    cfg = {"base": "main"}
    wt = W.ensure_worktree(d, meta, cfg)

    t = Ticket.find(d, "TICKET-001")
    t.body = t.body.replace("## Digest", "## Digest\nmirrored")
    t.save()

    mirror = wt / ".project" / "tickets" / "TICKET-001.md"

    def wsh(cmd):
        return subprocess.run(cmd, shell=True, cwd=wt, capture_output=True, text=True)

    assert "mirrored" in mirror.read_text()
    assert mirror.stat().st_mode & 0o222 == 0
    assert wsh("git status --porcelain").stdout == ""

    (wt / "new.py").write_text("work")
    wsh("git add -A && git commit -qm work")
    assert "mirrored" not in wsh("git show HEAD:.project/tickets/TICKET-001.md").stdout

    assert wsh("git rebase main").returncode == 0
    assert wsh("git status --porcelain").stdout == ""
    shutil.rmtree(d, ignore_errors=True)


def test_mirror_ticket_is_a_no_op_without_a_worktree():
    """No `.worktrees/` for this project, or a path that is not a ticket
    path: `mirror_ticket()` returns None rather than guessing a destination."""
    d, sh = git_project()
    assert W.mirror_ticket(d / ".project" / "tickets" / "TICKET-001.md", "x") is None
    assert W.mirror_ticket(d / "f.py", "x") is None
    shutil.rmtree(d, ignore_errors=True)


def test_retry_eagain_retries_a_transient_blockingioerror_and_then_returns():
    calls, slept = {"n": 0}, []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise BlockingIOError(11, "Resource temporarily unavailable")
        return "spawned"

    result = W.retry_eagain(flaky, sleep=slept.append)
    assert result == "spawned"
    assert calls["n"] == 3
    assert slept == [0.25, 0.5]


def test_retry_eagain_gives_up_after_the_last_try():
    calls, slept = {"n": 0}, []

    def always_fails():
        calls["n"] += 1
        raise BlockingIOError(11, "Resource temporarily unavailable")

    try:
        W.retry_eagain(always_fails, sleep=slept.append)
        raise AssertionError("retry_eagain must re-raise after the last try")
    except BlockingIOError:
        pass
    assert calls["n"] == W.EAGAIN_TRIES == 4
    assert slept == [0.25, 0.5, 1.0]
