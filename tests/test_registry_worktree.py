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

from helpers import git_project

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
