"""The CLI as a human runs it: a real process, not an in-process call."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from helpers import ROOT
from pipeline.core.ticket import Ticket


# Every `pipeline` process writes its events to $XDG_STATE_HOME/pipeline. With
# the real environment inherited, these tests wrote into the developer's own
# event log: 29 rows from 25 throwaway /tmp projects, which then showed up in a
# bare `pipeline metrics`. Sandbox it here, once, rather than in each caller.
_STATE = Path(tempfile.mkdtemp(prefix="pipeline-test-state-"))


def cli(project, *args, env=None):
    env = {**os.environ, "XDG_STATE_HOME": str(_STATE), **(env or {})}
    return subprocess.run([sys.executable, "-m", "pipeline",
                           "--project", str(project), *args],
                          cwd=ROOT, capture_output=True, text=True, env=env)


def test_resume_refuses_a_stage_that_does_not_exist():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    r = cli(d, "resume", "TICKET-001", "--stage", "implementng")   # typo
    assert r.returncode != 0 and "is not a stage" in r.stderr, r
    r = cli(d, "resume", "TICKET-001", "--stage", "planning")
    assert r.returncode == 0, r.stderr
    shutil.rmtree(d)


def test_resume_reset_only_zeroes_it_cannot_grant_back_one():
    """--grant hands back exactly what was spent (2 -> 1); --reset still
    zeroes the whole counter."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    cli(d, "resume", "TICKET-001", "--stage", "planning")
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.counters["plan_validation_attempts"] = 2
    t.save()

    r = cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--grant", "plan_validation_attempts")
    assert r.returncode == 0, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.counters["plan_validation_attempts"] == 1, (
        f"expected --grant to hand back exactly one spent attempt "
        f"(2 -> 1), got {t.counters['plan_validation_attempts']}"
    )

    r = cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--reset", "plan_validation_attempts")
    assert r.returncode == 0, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.counters["plan_validation_attempts"] == 0, (
        f"expected --reset to zero the counter, got "
        f"{t.counters['plan_validation_attempts']}"
    )

    body = (d / ".project/tickets/TICKET-001.md").read_text()
    assert "granted `plan_validation_attempts` 2 -> 1" in body, body
    assert f"by={os.environ.get('USER', 'human')}" in body, body
    shutil.rmtree(d)


def test_resume_grant_refuses_to_hand_back_more_than_was_spent():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    cli(d, "resume", "TICKET-001", "--stage", "planning")
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.counters["plan_validation_attempts"] = 2
    t.save()

    r = cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--grant", "plan_validation_attempts=3")
    assert r.returncode != 0, r.stdout
    assert "cannot grant 3" in r.stderr, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.counters["plan_validation_attempts"] == 2
    shutil.rmtree(d)


def test_resume_grant_refuses_a_counter_the_ticket_does_not_have():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    cli(d, "resume", "TICKET-001", "--stage", "planning")

    r = cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--grant", "plan_validaton_attempts")   # typo, spelled exactly so
    assert r.returncode != 0, r.stdout
    assert "has no counter" in r.stderr, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert "plan_validaton_attempts" not in t.counters
    shutil.rmtree(d)


def test_resume_grant_refuses_a_repeated_key_that_would_sum_past_have():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    cli(d, "resume", "TICKET-001", "--stage", "planning")
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.counters["plan_validation_attempts"] = 1
    t.save()

    r = cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--grant", "plan_validation_attempts", "plan_validation_attempts")
    assert r.returncode != 0, r.stdout
    assert "cannot grant 2" in r.stderr, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.counters["plan_validation_attempts"] == 1
    shutil.rmtree(d)


def test_resume_refuses_reset_and_grant_on_one_counter():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    cli(d, "resume", "TICKET-001", "--stage", "planning")
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.counters["plan_validation_attempts"] = 2
    t.save()

    r = cli(d, "resume", "TICKET-001", "--stage", "triage",
            "--reset", "plan_validation_attempts",
            "--grant", "plan_validation_attempts")
    assert r.returncode != 0, r.stdout
    assert "pick one" in r.stderr, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.counters["plan_validation_attempts"] == 2
    assert t.stage == "planning"
    shutil.rmtree(d)


def test_start_and_run_help_explain_the_interactive_stage_difference():
    """A `mode: interactive` stage waits for a human under `start` (attach via
    `pipeline tui`) but runs headless under `run` (nothing can attach). Neither
    --help currently says so."""
    r_start = subprocess.run([sys.executable, "-m", "pipeline", "start", "--help"],
                              cwd=ROOT, capture_output=True, text=True)
    r_run = subprocess.run([sys.executable, "-m", "pipeline", "run", "--help"],
                            cwd=ROOT, capture_output=True, text=True)
    assert "interactive" in r_start.stdout.lower(), r_start.stdout
    assert "interactive" in r_run.stdout.lower(), r_run.stdout


def test_the_help_text_matches_the_code_it_describes():
    """A help string asserting a behaviour is a promise, and an untested one
    drifts. `start --help` says an interactive stage waits at `pipeline tui`;
    `run --help` says it runs headless. Both rest on `Server.attachable` being
    true and the bare `Poller`'s being false, and on which stages declare
    `mode: interactive`. Flip either, or add a second interactive stage, and
    this fails until the help text and the README say the new truth."""
    from pipeline.core import config as C
    from pipeline.daemon.server import Poller, Server

    assert Server.attachable is True and Poller.attachable is False

    interactive = [s for s in C.agent_stages()
                   if C.stage_config(s).get("mode") == "interactive"]
    assert interactive, "no stage declares `mode: interactive`"

    def help_of(cmd):
        r = subprocess.run([sys.executable, "-m", "pipeline", cmd, "--help"],
                            cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return " ".join(r.stdout.split()).lower()   # argparse wraps at $COLUMNS

    start, run = help_of("start"), help_of("run")
    for stage in interactive:
        assert stage in start and stage in run, f"{stage} is unnamed: {start} {run}"
    assert "pipeline tui" in start and "headless" in start, start
    assert "headless" in run and "pipeline tui" in run, run

    readme = (Path(ROOT) / "README.md").read_text().splitlines()
    run_line = [ln for ln in readme if "myproject run  " in ln]
    start_line = [ln for ln in readme if ln.startswith("pipeline start ")]
    assert run_line and "headless" in run_line[0], run_line
    assert start_line and "tui" in start_line[0], start_line


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

    # and neither: `--project` documents "default: cwd", and `proj()` means it
    # everywhere else. `Path(None)` raised a TypeError straight past `die()`.
    bare = d / "bare"
    bare.mkdir()
    r = subprocess.run([sys.executable, "-m", "pipeline", "init"], cwd=bare,
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert r.returncode == 0, r.stderr
    assert (bare / ".project" / "pipeline.toml").is_file(), r.stdout + r.stderr
    shutil.rmtree(d, ignore_errors=True)


def test_a_human_gate_records_the_moment_the_human_acted():
    """View 6 measures time parked in a human gate: entering it is a
    `transition` event, and leaving it was "the next transition on that
    ticket" -- which, with nothing emitted here, was the *following stage's*
    transition. Every parked span therefore carried a whole stage's run time
    on top of the human's actual wait.

    These commands run in this process, not the daemon's, so they open the
    store themselves.
    """
    d = Path(tempfile.mkdtemp())
    state = Path(tempfile.mkdtemp())
    env = {**os.environ, "XDG_STATE_HOME": str(state)}
    cli(d, "new", "t", env=env)
    cli(d, "resume", "TICKET-001", "--stage", "awaiting-approval", env=env)
    r = cli(d, "approve", "TICKET-001", env=env)
    assert r.returncode == 0, r.stderr

    db = state / "pipeline" / "events.db"
    assert db.is_file(), f"no event log at {db}: {r.stdout} {r.stderr}"
    conn = sqlite3.connect(db)
    rows = [(t, s, k, json.loads(dat)) for t, s, k, dat in conn.execute(
        "SELECT ticket, stage, kind, data FROM events")]
    conn.close()
    assert rows, "approve emitted nothing at all"
    tid, stage, kind, data = rows[-1]
    assert (tid, stage, kind) == ("TICKET-001", "awaiting-approval",
                                 "transition"), rows
    assert data["from"] == "awaiting-approval" and data["to"] == "revalidating", data
    assert data["result"] == "approved", data
    shutil.rmtree(d)
    shutil.rmtree(state)


def test_approve_lands_a_fenced_ticket():
    """`approve` also lands the second human gate, `awaiting-merge`, into
    `merging` -- not `revalidating`, which is what `awaiting-approval` gets."""
    d = Path(tempfile.mkdtemp())
    state = Path(tempfile.mkdtemp())
    env = {**os.environ, "XDG_STATE_HOME": str(state)}
    cli(d, "new", "t", env=env)
    cli(d, "resume", "TICKET-001", "--stage", "awaiting-merge", env=env)
    r = cli(d, "approve", "TICKET-001", env=env)
    assert r.returncode == 0, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.stage == "merging"

    db = state / "pipeline" / "events.db"
    conn = sqlite3.connect(db)
    rows = [(t, s, k, json.loads(dat)) for t, s, k, dat in conn.execute(
        "SELECT ticket, stage, kind, data FROM events")]
    conn.close()
    tid, stage, kind, data = rows[-1]
    assert (tid, stage, kind) == ("TICKET-001", "awaiting-merge", "transition"), rows
    assert data["from"] == "awaiting-merge" and data["to"] == "merging", data
    shutil.rmtree(d)
    shutil.rmtree(state)


def test_answer_and_reject_record_too():
    """One command emitting and the other two not is the same bug with a
    smaller blast radius."""
    d = Path(tempfile.mkdtemp())
    state = Path(tempfile.mkdtemp())
    env = {**os.environ, "XDG_STATE_HOME": str(state)}
    cli(d, "new", "t", env=env)
    cli(d, "resume", "TICKET-001", "--stage", "needs-input", env=env)
    assert cli(d, "answer", "TICKET-001", "use the cache", env=env).returncode == 0
    cli(d, "resume", "TICKET-001", "--stage", "awaiting-approval", env=env)
    assert cli(d, "reject", "TICKET-001", "wrong layer", env=env).returncode == 0

    conn = sqlite3.connect(state / "pipeline" / "events.db")
    got = [(s, json.loads(dat)["to"], json.loads(dat)["result"]) for s, dat
           in conn.execute("SELECT stage, data FROM events WHERE kind='transition'")]
    conn.close()
    assert got == [("needs-input", "planning", "answered"),
                   ("awaiting-approval", "planning", "rejected")], got
    shutil.rmtree(d)
    shutil.rmtree(state)


def test_plan_prints_only_the_plan_and_acceptance_criteria():
    """The approval gate needs a decision, not a search through a ticket
    file that can exceed 65KB."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    path = d / ".project/tickets/TICKET-001.md"
    body = path.read_text()
    body = body.replace("## Plan\n\n", "## Plan\n\nmove the widget.\n\n")
    body = body.replace("## Acceptance criteria\n\n",
                         "## Acceptance criteria\n\nwidget moved.\n\n")
    path.write_text(body)
    r = cli(d, "plan", "TICKET-001")
    assert r.returncode == 0, r.stderr
    assert "move the widget." in r.stdout
    assert "widget moved." in r.stdout
    assert "## Plan" in r.stdout
    assert "## Acceptance criteria" in r.stdout
    assert "## Summary" not in r.stdout
    assert "## Reproduction" not in r.stdout
    shutil.rmtree(d)


def test_plan_errors_on_an_unknown_ticket():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    r = cli(d, "plan", "TICKET-999")
    assert r.returncode == 1, r.stderr
    assert "TICKET-999.md" in r.stderr
    assert "Traceback" not in r.stderr
    shutil.rmtree(d)
