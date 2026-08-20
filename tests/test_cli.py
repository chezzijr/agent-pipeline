"""The CLI as a human runs it: a real process, not an in-process call."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from helpers import ROOT


def cli(project, *args):
    return subprocess.run([sys.executable, "-m", "pipeline",
                           "--project", str(project), *args],
                          cwd=ROOT, capture_output=True, text=True)


def test_resume_refuses_a_stage_that_does_not_exist():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    r = cli(d, "resume", "TICKET-001", "--stage", "implementng")   # typo
    assert r.returncode != 0 and "is not a stage" in r.stderr, r
    r = cli(d, "resume", "TICKET-001", "--stage", "planning")
    assert r.returncode == 0, r.stderr
    shutil.rmtree(d)


def test_cli_new_then_status():
    d = Path(tempfile.mkdtemp())
    r = cli(d, "new", "cache leaks", "--class", "bugfix")
    assert r.returncode == 0, r.stderr
    assert (d / ".project/tickets/TICKET-001.md").is_file()
    r = cli(d, "status")
    assert "TICKET-001" in r.stdout and "new" in r.stdout, r.stdout
    r = cli(d, "approve", "TICKET-001")
    assert r.returncode != 0, "approve must refuse a ticket that is not awaiting-approval"
    shutil.rmtree(d)
