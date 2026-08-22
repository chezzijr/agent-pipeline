"""Per-ticket checkouts, and the venv the project's commands must not inherit."""
import json
import os
import shutil
import subprocess

from helpers import git_project
from pipeline.core import worktree as W


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
