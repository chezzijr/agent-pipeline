"""Throwaway projects the tests run against. No fixtures, no framework."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FIXTURE = """---
id: TICKET-001
stage: plan-validation
class: bugfix
branch: ticket/001
test_file: test_thing.py::test_broken
files_declared: [thing.py]
counters: {}
lease: {holder: null, expires: null}
---

## Summary
x
## Reproduction
fails
expect: test_broken
## Digest
- thing.py holds it
- cache() is the entry point
- eviction runs on write, not read
## Decisions checked
none relevant (grepped: cache, evict)
## Plan
1. fix thing.py
## Acceptance criteria
- `test_broken` passes
## Rollback
revert
## Thread
"""


def project(ticket_text=FIXTURE, test_passes=False):
    d = Path(tempfile.mkdtemp())
    (d / ".project" / "tickets").mkdir(parents=True)
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; exit %d"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "true"\n' % (0 if test_passes else 1))
    (d / ".project" / "tickets" / "TICKET-001.md").write_text(ticket_text)
    (d / "test_thing.py").write_text("")
    return d


def git_project():
    d = Path(tempfile.mkdtemp())
    sh = lambda c: subprocess.run(c, shell=True, cwd=d, capture_output=True, text=True)
    sh("git init -qb main && git config user.email t@t && git config user.name t")
    (d / "f.py").write_text("base\n")
    sh("git add -A && git commit -qm init")
    (d / ".project" / "tickets").mkdir(parents=True)
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\nbase="main"\n')
    return d, sh


def upstream_ahead(d, sh):
    """Give `main` an origin that holds one commit local `main` lacks. Returns
    the bare remote. Never `git add -A`: it sweeps the untracked `.project/`
    into the commit, and the reset below then deletes the ticket files."""
    remote = Path(tempfile.mkdtemp())
    subprocess.run(f"git clone -q --bare {d} {remote}", shell=True, check=True)
    sh(f"git remote add origin {remote} && git fetch -q origin && git branch -u origin/main main")
    (d / "g.py").write_text("later")
    sh("git add g.py && git commit -qm later && git push -q origin main && git reset -q --hard HEAD~1")
    return remote
