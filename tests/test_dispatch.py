"""What the dispatcher does with a ticket it cannot run."""
import shutil

from helpers import FIXTURE, git_project, project
from pipeline.core import ticket as T
from pipeline.core import config
from pipeline.core.config import harness
from pipeline.core.ticket import Ticket
from pipeline.daemon import supervisor


def test_escalation_clears_the_lease_so_a_human_can_resume():
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    t = Ticket.load(path)
    t.take_lease("x")
    t.save()
    supervisor.escalate(Ticket.load(path), "test")
    t = Ticket.load(path)
    assert t.stage == "escalated"
    assert not t.lease_active(), "a leased escalated ticket cannot be resumed"
    shutil.rmtree(d)


def test_an_escalated_ticket_keeps_its_worktree_and_its_evidence():
    d, _ = git_project()
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    wt = supervisor.ensure_worktree(d, meta, {"base": "main"})
    (wt / "half-finished.py").write_text("uncommitted evidence\n")

    (d / ".project/tickets/TICKET-001.md").write_text(
        FIXTURE.replace("stage: plan-validation", "stage: escalated"))
    supervisor.start(d, d / ".project/tickets/TICKET-001.md", harness("fake"), {})

    assert wt.is_dir(), "the worktree a human was escalated to inspect was deleted"
    assert (wt / "half-finished.py").exists()
    shutil.rmtree(d, ignore_errors=True)


def test_a_done_ticket_does_release_its_worktree():
    d, _ = git_project()
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    wt = supervisor.ensure_worktree(d, meta, {"base": "main"})
    (d / ".project/tickets/TICKET-001.md").write_text(
        FIXTURE.replace("stage: plan-validation", "stage: done"))
    supervisor.start(d, d / ".project/tickets/TICKET-001.md", harness("fake"), {})
    assert not wt.is_dir(), "a finished ticket should not leave a worktree behind"
    shutil.rmtree(d, ignore_errors=True)


def test_a_broken_project_config_escalates_one_ticket_not_the_process():
    """`project_config` used to `sys.exit(1)`, so one unconfigured project took
    the whole loop -- and every other ticket's agent -- down with it."""
    d, _ = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: implementing"))
    (d / ".project/pipeline.toml").unlink()

    did, rec = supervisor.start(d, path, harness("fake"), {})

    assert did and rec is None
    assert Ticket.load(path).stage == "escalated"
    shutil.rmtree(d, ignore_errors=True)


def test_an_agent_that_rewrote_stage_is_still_caught():
    """Invariant 1 through the typed model: control fields come back from the
    pre-spawn snapshot, and a ticket whose control fields moved is escalated."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    snap = Ticket.load(path)                      # what the dispatcher spawned on

    agent = Ticket.load(path)                     # what the agent left behind
    agent.stage = "done"
    agent.body += "\n(prose the agent wrote)\n"
    agent.save()

    log = d / ".project" / "logs" / "TICKET-001.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    T.result_file(d, "TICKET-001").write_text("result: ok\nsummary: fine\n")
    supervisor.finish(d, {"fh": log.open("w"), "prompt": d / "gone.md",
                          "settings": None, "path": path, "tid": "TICKET-001",
                          "stage": "plan-validation", "session": "s1", "log": log,
                          "wt": d, "meta": snap, "before": None})

    t = Ticket.load(path)
    assert t.stage == "escalated", "a tampered `stage` was accepted"
    assert "edited dispatcher-owned frontmatter" in t.thread()[-1].text
    assert T.read_result(d, "TICKET-001") is None, "the verdict was still applied"
    shutil.rmtree(d, ignore_errors=True)


def test_verifying_runs_as_a_tracked_child():
    """`verifying` used to run the suite inline, so a slow suite stalled the
    whole loop: nothing else advanced and no finished agent was reaped."""
    assert "verifying" not in config.agent_stages(), \
        "verifying must stay script-run -- no agent may judge a test result"
    d, _ = git_project()
    (d / ".project/pipeline.toml").write_text(
        'test_one = "true"\n'
        'test_suite = "sh -c \'sleep 0.3; exit 1\'"\n'
        'test_suite_without_new = "true"\nbase = "main"\n')
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: verifying"))
    # an earlier stage's leftover verdict: if the suite's result ever came from
    # this file instead of an exit code, the ticket would reach `done`
    T.result_file(d, "TICKET-001").write_text("result: ok\nsummary: planted\n")

    did, rec = supervisor.start(d, path, harness("fake"), {})

    assert did and rec and rec["kind"] == "suite"
    assert rec["proc"].poll() is None, "the suite blocked the dispatcher loop"
    assert Ticket.load(path).stage == "verifying"
    assert Ticket.load(path).lease_active(), "a child outliving the tick must lease"

    rec["proc"].wait()
    supervisor.finish(d, rec)

    t = Ticket.load(path)
    assert t.stage == "implementing", "the suite's exit code did not decide it"
    assert t.counters["review_loops"] == 1
    assert not t.lease_active()
    shutil.rmtree(d, ignore_errors=True)


def test_ctrl_c_during_a_suite_does_not_crash_on_its_missing_prompt():
    """`shut_down` unlinked `rec["prompt"]` unconditionally; a suite record has
    none, so Ctrl-C during `verifying` raised and left every lease held."""
    d, _ = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: verifying"))
    _, rec = supervisor.start(d, path, harness("fake"), {})

    supervisor.shut_down(d, {"TICKET-001": rec})

    assert not Ticket.load(path).lease_active(), "an interrupted suite kept its lease"
    shutil.rmtree(d, ignore_errors=True)
