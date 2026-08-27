"""register() must refuse a worktree of an already-registered project.

TICKET-072: `pipeline register .` inside a stage's own worktree checkout
succeeds, because `git worktree add` copies `.project/` along with
everything else and `register()` never checks for that relationship. The
daemon then ticks the worktree as a second project, whose `.project/tickets/`
that same stage can write via Bash -- outside every containment the design
has (tree_snapshot, machine.FENCED, review).
"""
import os
import subprocess
import tempfile
from pathlib import Path

from helpers import git_project, project

for var in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
    os.environ[var] = tempfile.mkdtemp()
from pipeline.daemon import registry
from pipeline.core import PipelineError


def test_register_refuses_a_worktree_of_a_registered_project():
    d, sh = git_project()
    r = sh("git add -A .project && git commit -qm 'add .project'")
    assert r.returncode == 0, r.stderr
    registry.register(d)

    wt = d / ".worktrees" / "TICKET-068"
    r = sh(f"git worktree add -b ticket/068 {wt} main")
    assert r.returncode == 0, r.stderr
    assert (wt / ".project").is_dir()

    try:
        registry.register(wt)
        assert False, "register() accepted a worktree of a registered project"
    except PipelineError as e:
        assert "worktree" in str(e), e

    assert wt not in registry.projects(), (
        f"register() accepted a worktree of a registered project: {wt} is "
        f"in {registry.projects()}"
    )


def test_projects_skips_a_worktree_line_already_in_the_registry():
    d, sh = git_project()
    r = sh("git add -A .project && git commit -qm 'add .project'")
    assert r.returncode == 0, r.stderr

    wt = d / ".worktrees" / "TICKET-068"
    r = sh(f"git worktree add -b ticket/068 {wt} main")
    assert r.returncode == 0, r.stderr

    registry.registry_path().parent.mkdir(parents=True, exist_ok=True)
    registry.registry_path().write_text(f"{d}\n{wt}\n")

    assert registry.projects() == [d], registry.projects()


def test_register_still_accepts_a_main_checkout_and_a_plain_directory():
    d, sh = git_project()
    r = sh("git add -A .project && git commit -qm 'add .project'")
    assert r.returncode == 0, r.stderr
    p = project()

    try:
        assert registry.register(d) == d
        assert registry.register(p) == p
        assert d in registry.projects()
        assert p in registry.projects()
    finally:
        # `p` carries a real TICKET-001, unlike the git_project() fixtures
        # elsewhere in this file -- leaving it registered would collide with
        # tests/test_daemon.py's own TICKET-001 project on the shared registry.
        registry.unregister(p)


def test_a_stage_cannot_register_or_unregister():
    d, sh = git_project()
    r = sh("git add -A .project && git commit -qm 'add .project'")
    assert r.returncode == 0, r.stderr
    registry.register(d)

    os.environ["PIPELINE_STAGE"] = "planning"
    try:
        try:
            registry.register(d)
            assert False, "register() ran under PIPELINE_STAGE"
        except PipelineError as e:
            assert "operator state" in str(e), e

        try:
            registry.unregister(d)
            assert False, "unregister() ran under PIPELINE_STAGE"
        except PipelineError as e:
            assert "operator state" in str(e), e
    finally:
        del os.environ["PIPELINE_STAGE"]

    assert d in registry.projects()
