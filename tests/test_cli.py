"""The CLI as a human runs it: a real process, not an in-process call."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from helpers import ROOT, project
from pipeline.core.ticket import Ticket, stage_view


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


def test_resume_reset_drops_the_forgiveness_credit_too():
    """--reset on a counter that has a `_cleared` credit drops the credit
    with it; --grant lowers the credit by the same amount it grants."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    cli(d, "resume", "TICKET-001", "--stage", "planning")
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.counters["stale_regate"] = 2
    t.counters["stale_regate_cleared"] = 1
    t.save()

    r = cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--reset", "stale_regate")
    assert r.returncode == 0, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.counters["stale_regate"] == 0, "the reset left a credit behind"
    assert t.counters["stale_regate_cleared"] == 0, "the reset left a credit behind"

    t.counters["stale_regate"] = 2
    t.counters["stale_regate_cleared"] = 2
    t.save()

    r = cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--grant", "stale_regate")
    assert r.returncode == 0, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert (t.counters["stale_regate"], t.counters["stale_regate_cleared"]) == (1, 1)
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


def test_resume_records_an_operator_note():
    """`answer` refuses outside `needs-input`, so an escalated ticket being
    resumed has nowhere for the operator's reasoning to go. `resume` should
    accept `--note` the way `answer` accepts its text, and the note must
    survive as a kind the stage view never omits."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    env = {"USER": "operator-marker"}
    r = cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--note", "granted because the escalation was a flaky test", env=env)
    assert r.returncode == 0, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    e = [e for e in t.thread() if e.kind == "answer"][-1]
    assert "granted because the escalation was a flaky test" in e.text, e.text
    assert "operator-marker" in e.text, e.text
    for i in range(9):
        t.append("planning", "note", f"filler {i}")
    t.save()
    view = stage_view(Ticket.load(t.path), "planning")
    assert "granted because the escalation was a flaky test" in view, view


def test_resume_note_is_optional_and_may_not_be_empty():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    r = cli(d, "resume", "TICKET-001", "--stage", "planning", "--note", "   ")
    assert r.returncode != 0, r.stdout
    assert "a note needs text" in r.stderr, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert t.stage == "new"

    r = cli(d, "resume", "TICKET-001", "--stage", "planning")
    assert r.returncode == 0, r.stderr
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert [e for e in t.thread() if e.kind == "answer"] == []
    shutil.rmtree(d)


def test_note_appends_at_any_stage_without_touching_control_fields():
    """`pipeline note` should append a human thread entry at ANY stage,
    escalated included, and leave stage/counters/branch/lease untouched.
    Today there is no `note` subcommand at all."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    r = cli(d, "resume", "TICKET-001", "--stage", "implementing")
    assert r.returncode == 0, r.stderr
    before = Ticket.load(d / ".project/tickets/TICKET-001.md")
    before_stage, before_counters, before_branch, before_lease = (
        before.stage, dict(before.counters), before.branch, before.lease)

    r = cli(d, "note", "TICKET-001", "watch out for the flaky cache test")
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)

    after = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert after.stage == before_stage, after.stage
    assert after.counters == before_counters, after.counters
    assert after.branch == before_branch, after.branch
    assert after.lease == before_lease, after.lease
    notes = [e for e in after.thread() if e.kind == "note"
             and "watch out for the flaky cache test" in e.text]
    assert len(notes) == 1, after.thread()
    shutil.rmtree(d)


def test_note_claims_a_lease_only_when_one_is_actually_held():
    """`{}` is the empty lease every unleased ticket carries, and a dict is
    truthy -- so `if t.lease` claimed a stage was holding one on a ticket
    that has never been spawned. `lease_active()` is the total reader."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    path = d / ".project/tickets/TICKET-001.md"

    r = cli(d, "note", "TICKET-001", "no stage is running")
    assert r.returncode == 0, r.stderr
    assert "holds a lease" not in r.stdout, r.stdout

    t = Ticket.load(path)
    t.take_lease("implementing-1")
    t.save()
    r = cli(d, "note", "TICKET-001", "a stage is running")
    assert r.returncode == 0, r.stderr
    assert "holds a lease" in r.stdout, r.stdout
    shutil.rmtree(d)


def test_resume_help_and_readme_name_the_note_flag():
    r = subprocess.run([sys.executable, "-m", "pipeline", "resume", "--help"],
                        cwd=ROOT, capture_output=True, text=True)
    assert "--note" in r.stdout, r.stdout
    readme = (Path(ROOT) / "README.md").read_text()
    assert "resume  TICKET-001 --stage planning --note" in readme, readme


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
    assert Poller().watchers() == 0, "a supervisor with no socket has no watchers"

    interactive = [s for s in C.agent_stages()
                   if C.stage_config(s).get("mode") == "interactive"]
    assert interactive, "no stage declares `mode: interactive`"

    def help_of(cmd):
        r = subprocess.run([sys.executable, "-m", "pipeline", cmd, "--help"],
                            cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return " ".join(r.stdout.split()).lower()   # argparse wraps at $COLUMNS

    start, run = help_of("start"), help_of("run")
    assert "attached" in start and "attached" in run, (start, run)
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


def test_cli_new_records_a_declared_dependency():
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "first", "--class", "bugfix")
    r = cli(d, "new", "second", "--depends-on", "TICKET-001")
    assert r.returncode == 0, r.stderr
    assert "depends_on: [TICKET-001]" in (d / ".project/tickets/TICKET-002.md").read_text()
    r = cli(d, "new", "third", "--depends-on", "not-a-ticket")
    assert r.returncode != 0
    shutil.rmtree(d)


def test_ls_says_running_is_unknown_when_no_daemon_answers():
    """No daemon means every row's `running`/`mode` is unknown, not idle --
    `ls` must say so once, not per row."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "cache leaks", "--class", "bugfix")
    r = cli(d, "ls")
    assert "-- no daemon: running/mode unknown for these rows" in r.stdout, r.stdout
    assert "TICKET-001" in r.stdout
    shutil.rmtree(d)


def test_ls_v_prints_the_last_session_cost():
    """TICKET-085: `-v` names the cost of a ticket's last spawned session,
    read with `.get` because a ticket written before this change has no
    `cost_usd` key."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.extra["last_session"] = {"stage": "planning", "id": "s1",
                                "log": ".project/logs/x.log",
                                "cost_usd": 6.089121}
    t.save()
    r = cli(d, "ls", "-v")
    assert "cost=$6.09" in r.stdout, r.stdout
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


def test_init_installs_the_file_ticket_skill():
    """CLAUDE.md calls `.claude/skills/file-ticket/SKILL.md` part of the
    interface: it is what a session reads before filing a ticket into this
    pipeline. `init` scaffolds `.project/` but never copies it, so a project
    it creates has a queue and no description of the protocol."""
    d = Path(tempfile.mkdtemp())
    r = cli(d, "init")
    assert r.returncode == 0, r.stderr
    skill = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"
    assert skill.is_file(), (
        f"expected {skill} to exist after `pipeline init`, "
        f"found: {list(d.rglob('SKILL.md'))}"
    )
    shutil.rmtree(d, ignore_errors=True)


def test_init_installs_every_packaged_skill():
    """`init` loops `SKILLS_DIR`, so a skill added to the package reaches the
    projects it scaffolds with no second edit in `cmd_init`. Naming one skill
    there is what left `pipeline-config` uninstalled."""
    from pipeline.core.config import SKILLS_DIR
    d = Path(tempfile.mkdtemp())
    r = cli(d, "init")
    assert r.returncode == 0, r.stderr
    for src in SKILLS_DIR.iterdir():
        skill = d / ".claude" / "skills" / src.name / "SKILL.md"
        assert skill.is_file(), f"{src.name} not installed: {list(d.rglob('SKILL.md'))}"
        assert skill.read_text() == (src / "SKILL.md").read_text(), src.name
    shutil.rmtree(d, ignore_errors=True)


def test_init_keeps_a_customised_file_ticket_skill():
    """`init` mirrors `.project/pipeline.toml`: a project that customised its
    skill file keeps it on re-init, and `init` prints the skill's path either
    way so a human knows where it went."""
    d = Path(tempfile.mkdtemp())
    r = cli(d, "init")
    assert r.returncode == 0, r.stderr
    skill = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"
    assert str(skill) in r.stdout, r.stdout
    skill.write_text("# ours\n")
    r = cli(d, "init")
    assert r.returncode == 0, r.stderr
    assert skill.read_text() == "# ours\n", "re-init overwrote a customised skill"
    assert "kept" in r.stdout, r.stdout
    shutil.rmtree(d, ignore_errors=True)


def test_reinit_does_not_detect_a_packaged_skill_update():
    """A scaffolded project's skill copy is a one-time write: `init` only
    checks the file exists, never whether it matches the packaged template.
    So when the packaged `file-ticket` skill changes (a real upstream edit,
    not a project customisation), a project scaffolded before the change
    silently keeps the old copy forever, and `init` never says so."""
    from pipeline.core.config import SKILL_TEMPLATE
    d = Path(tempfile.mkdtemp())
    r = cli(d, "init")
    assert r.returncode == 0, r.stderr
    skill = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"
    original = SKILL_TEMPLATE.read_text()
    try:
        SKILL_TEMPLATE.write_text(original + "\n<!-- upstream update -->\n")
        r = cli(d, "init")
        assert r.returncode == 0, r.stderr
        assert skill.read_text() != SKILL_TEMPLATE.read_text(), (
            "the scaffolded copy and the packaged template have drifted")
        assert "stale" in r.stdout or "differs" in r.stdout or "drift" in r.stdout, (
            f"expected `init` to report the drift between {skill} and "
            f"{SKILL_TEMPLATE}, got: {r.stdout!r}")
    finally:
        SKILL_TEMPLATE.write_text(original)
    shutil.rmtree(d, ignore_errors=True)


def test_skills_refresh_updates_a_stale_copy_and_keeps_a_customised_one():
    """`pipeline skills --refresh` rewrites a stale copy from the packaged
    template, and leaves a customised copy alone -- the distinction `init`
    alone cannot make without --force."""
    from pipeline.core.config import SKILL_TEMPLATE
    d = Path(tempfile.mkdtemp())
    r = cli(d, "init")
    assert r.returncode == 0, r.stderr
    pipeline_config = d / ".claude" / "skills" / "pipeline-config" / "SKILL.md"
    pipeline_config.write_text("# ours\n")
    original = SKILL_TEMPLATE.read_text()
    try:
        SKILL_TEMPLATE.write_text(original + "\n<!-- upstream update -->\n")
        r = cli(d, "skills")
        assert r.returncode == 0, r.stderr
        assert "file-ticket: stale" in r.stdout, r.stdout
        assert "pipeline-config: customised" in r.stdout, r.stdout

        r = cli(d, "skills", "--refresh")
        assert r.returncode == 0, r.stderr
        file_ticket = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"
        assert file_ticket.read_text() == SKILL_TEMPLATE.read_text()
        assert pipeline_config.read_text() == "# ours\n"

        r = cli(d, "skills")
        assert r.returncode == 0, r.stderr
        assert "file-ticket: current" in r.stdout, r.stdout
    finally:
        SKILL_TEMPLATE.write_text(original)
    shutil.rmtree(d, ignore_errors=True)


def test_skills_force_overwrites_a_customised_copy_but_never_a_symlink():
    """`--refresh --force` overwrites a customised copy, and `--force`
    without `--refresh` is refused. A symlinked copy -- this repo's own
    layout -- is never written, even under `--force`."""
    from pipeline.core.config import SKILL_TEMPLATE
    d = Path(tempfile.mkdtemp())
    r = cli(d, "init")
    assert r.returncode == 0, r.stderr
    file_ticket = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"
    file_ticket.write_text("# ours\n")
    linked_target = d / "linked-elsewhere.md"
    linked_target.write_text("# linked elsewhere\n")
    pipeline_config = d / ".claude" / "skills" / "pipeline-config" / "SKILL.md"
    pipeline_config.unlink()
    pipeline_config.symlink_to(linked_target)

    r = cli(d, "skills", "--refresh", "--force")
    assert r.returncode == 0, r.stderr
    assert file_ticket.read_text() == SKILL_TEMPLATE.read_text()
    assert pipeline_config.is_symlink(), "--force rewrote a symlinked skill copy"
    assert linked_target.read_text() == "# linked elsewhere\n"

    r = cli(d, "skills", "--force")
    assert r.returncode != 0
    assert "--force applies to --refresh only" in r.stderr, r.stderr
    shutil.rmtree(d, ignore_errors=True)


def test_skills_with_no_flags_never_installs_an_absent_copy():
    """`pipeline skills` with no flags is a report; it must not write. Run
    against a project directory with no scaffolded skills, it must leave
    every copy missing and print `absent`, not `installed`."""
    d = Path(tempfile.mkdtemp())
    file_ticket = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"

    r = cli(d, "skills")
    assert r.returncode == 0, r.stderr
    assert "file-ticket: absent" in r.stdout, r.stdout
    assert "installed" not in r.stdout, r.stdout
    assert not file_ticket.exists(), (
        "`pipeline skills` with no flags installed a copy into an empty project")
    assert not (d / ".project" / "skills.json").exists()
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


def test_plan_prints_the_plan_criteria_and_rollback():
    """The approval gate needs a decision, not a search through a ticket
    file that can exceed 65KB. Approving a plan approves its undo path too,
    so the rollback must be in view alongside the plan."""
    d = Path(tempfile.mkdtemp())
    cli(d, "new", "t")
    path = d / ".project/tickets/TICKET-001.md"
    body = path.read_text()
    body = body.replace("## Plan\n\n", "## Plan\n\nmove the widget.\n\n")
    body = body.replace("## Acceptance criteria\n\n",
                         "## Acceptance criteria\n\nwidget moved.\n\n")
    body = body.replace("## Rollback\n\n",
                         "## Rollback\n\nput the widget back.\n\n")
    path.write_text(body)
    r = cli(d, "plan", "TICKET-001")
    assert r.returncode == 0, r.stderr
    assert "move the widget." in r.stdout
    assert "widget moved." in r.stdout
    assert "put the widget back." in r.stdout
    assert "## Plan" in r.stdout
    assert "## Acceptance criteria" in r.stdout
    assert "## Rollback" in r.stdout
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


def test_gate_writes_its_findings_where_the_dispatcher_asked():
    """`--findings PATH` is how the dispatcher's spawned gate child hands its
    verdict back, since its stdout goes straight to a log file it never reads."""
    d = project(test_passes=True)
    out = Path(tempfile.mkdtemp()) / "findings.json"
    r = cli(d, "gate", "TICKET-001", "--findings", str(out))
    assert r.returncode == 1, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert data["ok"] is False
    assert len(data["findings"]) == 1
    assert not any("```" in f for f in data["findings"])
    shutil.rmtree(d)


def test_register_refuses_a_project_whose_test_suite_cannot_run():
    """A project scaffolded with the packaged defaults (e.g. `test_suite =
    "pytest"` against a repo pytest is not installed for) registers clean
    today, and every ticket filed against it fails at the gate instead.
    `register` must run `test_suite` once and refuse when the command itself
    cannot run -- not when it runs and reports failures."""
    d = Path(tempfile.mkdtemp())
    (d / ".project").mkdir()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "true"\n'
        'test_suite = "pipeline-068-nonexistent-command-xyz"\n'
        'test_suite_without_new = "true"\n')
    r = cli(d, "register", str(d), env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
    assert r.returncode != 0, r.stdout + r.stderr
    assert "pipeline-068-nonexistent-command-xyz" in r.stdout + r.stderr
    shutil.rmtree(d, ignore_errors=True)


def register_project(test_one="false", test_suite="true", config=True):
    """A throwaway project for `pipeline register`. Not named `test_*`:
    pytest would collect it."""
    d = Path(tempfile.mkdtemp()).resolve()
    (d / ".project").mkdir()
    if config:
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "%s"\ntest_suite = "%s"\n'
            'test_suite_without_new = "true"\n' % (test_one, test_suite))
    return d


def test_register_accepts_a_project_whose_test_suite_runs_and_fails():
    """A red suite is the normal state of a project with an open bug."""
    d = register_project(test_suite="echo 1 failed; exit 1")
    r = cli(d, "register", str(d), env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"registered {d}" in r.stdout
    shutil.rmtree(d, ignore_errors=True)


def test_register_refuses_a_test_one_that_exits_0_on_a_selector_matching_nothing():
    """`gate()` would read that exit 0 as `the reproduction PASSES`."""
    d = register_project(test_one="true")
    r = cli(d, "register", str(d), env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
    assert r.returncode != 0, r.stdout + r.stderr
    assert "test_one" in r.stdout + r.stderr
    assert "pipeline_register_probe_no_such_test" in r.stdout + r.stderr
    shutil.rmtree(d, ignore_errors=True)


def test_register_refuses_a_project_directory_with_no_pipeline_toml():
    """`register` accepted a bare `.project/` before this ticket. Both
    checks read the config, so it refuses one now -- intended, pinned here,
    and `--force` still registers it."""
    d = register_project(config=False)
    r = cli(d, "register", str(d), env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
    assert r.returncode != 0, r.stdout + r.stderr
    assert "pipeline init" in r.stdout + r.stderr
    forced = cli(d, "register", "--force", str(d),
                 env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
    assert forced.returncode == 0, forced.stdout + forced.stderr
    shutil.rmtree(d, ignore_errors=True)


def test_register_force_skips_both_test_command_checks():
    """`--force` is what a slow suite wants: register without running it."""
    d = register_project(test_one="true",
                         test_suite="pipeline-068-nonexistent-command-xyz")
    r = cli(d, "register", "--force", str(d),
            env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"registered {d}" in r.stdout
    shutil.rmtree(d, ignore_errors=True)


def test_config_reports_the_pinned_source_and_sync_adopts_an_edit():
    """`pipeline config` names the pin and warns on divergence; `--sync` is
    the only way to adopt an edit on a project git will never have."""
    d = Path(tempfile.mkdtemp())
    subprocess.run("git init -qb main", shell=True, cwd=d)
    cli(d, "init", "--private")
    assert "source:  pinned" in cli(d, "config").stdout
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="edited"\ntest_suite="true"\n'
        'test_suite_without_new="true"\nbase="main"\n')
    out = cli(d, "config").stdout
    assert "pipeline config --sync" in out
    assert "'edited'" not in out
    synced = cli(d, "config", "--sync")
    assert synced.returncode == 0, synced.stdout + synced.stderr
    assert "'edited'" in cli(d, "config").stdout
    shutil.rmtree(d, ignore_errors=True)


def test_init_private_and_register_both_name_the_pin():
    """Both commands print the sync command on a `--private` project."""
    d = Path(tempfile.mkdtemp())
    subprocess.run("git init -qb main", shell=True, cwd=d)
    assert "config --sync" in cli(d, "init", "--private").stdout
    assert "pinned" in cli(d, "register", "--force", str(d)).stdout
    shutil.rmtree(d, ignore_errors=True)
