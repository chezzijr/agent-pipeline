"""The CLI as a human runs it: a real process, not an in-process call."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from helpers import ROOT
from pipeline.core.ticket import Ticket


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


def test_cli_new_then_ls():
    """`ls` lists tickets; `status` is the daemon's own liveness -- there is
    one daemon and many projects, so they cannot be the same command."""
    d = Path(tempfile.mkdtemp())
    r = cli(d, "new", "cache leaks", "--class", "bugfix")
    assert r.returncode == 0, r.stderr
    assert (d / ".project/tickets/TICKET-001.md").is_file()
    r = cli(d, "ls")
    assert "TICKET-001" in r.stdout and "new" in r.stdout, r.stdout
    r = cli(d, "approve", "TICKET-001")
    assert r.returncode != 0, "approve must refuse a ticket that is not awaiting-approval"
    shutil.rmtree(d)


def test_reject_returns_a_plan_with_its_reason():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    cli(d, "resume", "TICKET-001", "--stage", "awaiting-approval")
    r = cli(d, "reject", "TICKET-001", "ignores cache invalidation")
    assert r.returncode == 0, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.stage == "planning"
    assert t.counters["plan_validation_attempts"] == 0
    e = [e for e in t.thread() if e.kind == "rejection"][-1]
    assert e.stage == "human" and "cache invalidation" in e.text

    # the bound: a human's third reject is refused, not escalated -- escalation
    # means "a human must look", and one already is. `plan_rejections` is
    # lifetime (like every other counter here), so the escape hatch the error
    # prints must actually clear it, not just point at `resume`.
    cli(d, "resume", "TICKET-001", "--stage", "awaiting-approval")
    r = cli(d, "reject", "TICKET-001", "still wrong")
    assert r.returncode == 0, r.stderr
    cli(d, "resume", "TICKET-001", "--stage", "awaiting-approval")
    r = cli(d, "reject", "TICKET-001", "nope again")
    assert r.returncode != 0, "3rd reject must refuse, not silently escalate"
    assert "--reset plan_rejections" in r.stderr, \
        "the printed escape hatch must actually clear the counter it refused on"
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.stage == "awaiting-approval"

    # follow the printed advice: resume with the reset it names, and a plan
    # that has never been rejected before must not be refused on first try
    cli(d, "resume", "TICKET-001", "--stage", "awaiting-approval",
        "--reset", "plan_rejections")
    r = cli(d, "reject", "TICKET-001", "a brand new complaint")
    assert r.returncode == 0, r.stderr
    shutil.rmtree(d)


def test_reject_refuses_an_empty_reason():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    cli(d, "resume", "TICKET-001", "--stage", "awaiting-approval")
    r = cli(d, "reject", "TICKET-001", "   ")
    assert r.returncode != 0 and "reason" in r.stderr, r
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.stage == "awaiting-approval" and t.counters.get("plan_rejections", 0) == 0
    shutil.rmtree(d)


def test_logs_pretty_prints_a_stream_json_log():
    """`pipeline logs` is the dogfood view and the fallback when the TUI breaks."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    logs = d / ".project" / "logs"
    logs.mkdir(parents=True)
    fixture = (ROOT / "tests" / "fixtures" / "stream-planning.ndjson").read_bytes()
    (logs / "TICKET-001-planning-6f1c0a2e.log").write_bytes(fixture)
    r = cli(d, "logs", "TICKET-001", "-f")   # -f returns at the `result` event
    assert r.returncode == 0, r.stderr
    assert "-- init claude-sonnet-4-6 mode=plan" in r.stdout, r.stdout
    assert "exit=2" in r.stdout and "== success $0.3412" in r.stdout, r.stdout
    assert cli(d, "logs", "TICKET-002").returncode != 0   # no log, no guessing
    shutil.rmtree(d)


def test_init_honours_project_like_every_other_command():
    """`init` takes a positional dir, every other command takes `--project`.
    Accepting only the positional made `pipeline --project X init` scaffold the
    CURRENT directory and print "initialised" while doing it -- the wrong tree,
    silently, with a success message."""
    d = Path(tempfile.mkdtemp())
    target, other = d / "target", d / "other"
    target.mkdir(); other.mkdir()

    r = cli(target, "init")
    assert r.returncode == 0, r.stderr
    assert (target / ".project" / "pipeline.toml").is_file(), "--project was ignored"
    assert not (Path(ROOT) / "cwd").exists()

    # the positional form the README documents still wins when both are given
    r = subprocess.run([sys.executable, "-m", "pipeline", "--project", str(target),
                        "init", str(other)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (other / ".project" / "pipeline.toml").is_file(), "positional dir ignored"
    shutil.rmtree(d, ignore_errors=True)
