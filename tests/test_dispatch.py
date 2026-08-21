"""What the dispatcher does with a ticket it cannot run."""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from helpers import FIXTURE, git_project, project
from pipeline.cli import metrics
from pipeline.daemon.store import Store
from pipeline.core import ticket as T
from pipeline.core import config
from pipeline.core import machine as M
from pipeline.cli.main import cmd_approve
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


def _commit(wt, msg):
    subprocess.run(f"git add -A && git commit -qm {msg}", shell=True, cwd=wt,
                   capture_output=True, text=True)


def test_a_verified_ticket_lands_on_base():
    """`done` means landed. `verifying` used to go straight to `done`, leaving
    the fix on `ticket/<id>` with nothing to say a branch was waiting."""
    assert M.transition("verifying", "ok", {})[0] == "merging"
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: verifying"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "g.py").write_text("the fix\n")
    _commit(wt, "'ticket commit'")

    for expect in ("merging", "done"):           # verifying -> merging -> done
        did, rec = supervisor.start(d, path, harness("fake"), {})
        assert did and rec, f"nothing spawned on the way to {expect}"
        rec["proc"].wait()
        supervisor.finish(d, rec)
        assert Ticket.load(path).stage == expect, f"did not reach {expect}"

    assert "ticket commit" in sh("git log --oneline main").stdout, \
        "`done` but the fix never landed on base"
    supervisor.start(d, path, harness("fake"), {})   # the `done` cleanup pass
    assert not wt.is_dir()
    shutil.rmtree(d, ignore_errors=True)


def test_a_merge_conflict_escalates_and_keeps_the_worktree():
    """The conflicted index is the evidence the human was escalated to look at,
    and it lives in the worktree. Never auto-resolved, never retried."""
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "f.py").write_text("branch side\n")       # both sides edit one line
    _commit(wt, "'ticket commit'")
    (d / "f.py").write_text("base side\n")
    sh("git add -A && git commit -qm 'base moved'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec and rec["kind"] == "merge"
    rec["proc"].wait()
    supervisor.finish(d, rec)

    assert Ticket.load(path).stage == "escalated"
    assert wt.is_dir(), "the conflicted worktree is the evidence"
    assert "f.py" in sh(f"git -C {wt} diff --name-only --diff-filter=U").stdout, \
        "the conflict was resolved instead of left for the human"
    assert "ticket commit" not in sh("git log --oneline main").stdout, \
        "a conflicting branch was merged into base anyway"
    shutil.rmtree(d, ignore_errors=True)


def test_a_main_checkout_parked_elsewhere_does_not_get_the_ticket_landed_on_it():
    """Step 2 merges into whatever the main checkout has checked out. If that
    is not `base`, a fast-forward can still succeed -- onto the wrong branch."""
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "g.py").write_text("the fix\n")
    _commit(wt, "'ticket commit'")
    sh("git checkout -qb sidequest")          # a human left main parked

    did, rec = supervisor.start(d, path, harness("fake"), {})
    rec["proc"].wait()
    supervisor.finish(d, rec)

    assert Ticket.load(path).stage == "escalated"
    assert "ticket commit" not in sh("git log --oneline sidequest").stdout, \
        "the ticket landed on whatever branch happened to be checked out"
    assert "ticket commit" not in sh("git log --oneline main").stdout
    shutil.rmtree(d, ignore_errors=True)


def _ticket_awaiting_approval():
    """A git project whose ticket is parked at the human gate, with a worktree
    on its branch -- where every re-gate case starts. The suite command reads a
    file base can add, so "another ticket landed and broke it" is one commit."""
    d, sh = git_project()
    (d / "test_thing.py").write_text("")
    sh("git add test_thing.py && git commit -qm 'the test file'")
    (d / ".project/pipeline.toml").write_text(
        'test_one = "echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "! test -f broken"\n'
        'base = "main"\n')
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE
                    .replace("stage: plan-validation", "stage: awaiting-approval")
                    .replace("counters: {}", "counters: {plan_validation_attempts: 0}"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    cmd_approve(argparse.Namespace(project=str(d), id="TICKET-001", by="human"))
    return d, sh, path, wt


def test_a_stale_plan_is_re_gated_on_approval():
    """A ticket sits at the human gate for days while other tickets land. Its
    Tier A facts -- suite green, the new test the only red -- were recorded
    against a tree that no longer exists, and approval used to trust them."""
    d, sh, path, wt = _ticket_awaiting_approval()
    assert Ticket.load(path).stage == "revalidating", "approval trusted a stale plan"
    assert Ticket.load(path).extra["approved_by"] == "human", \
        "approval must still stamp, and must not block on the rebase"

    (d / "broken").write_text("another ticket landed and broke the suite\n")
    sh("git add broken && git commit -qm 'base moved'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec and rec["kind"] == "regate"
    rec["proc"].wait()
    supervisor.finish(d, rec)

    assert "base moved" in sh(f"git -C {wt} log --oneline").stdout, \
        "the plan was re-gated without being rebased onto current base"
    t = Ticket.load(path)
    assert t.stage == "planning", "a plan validated against a dead tree was implemented"
    assert t.counters["plan_validation_attempts"] == 0, \
        "a good plan was charged for the crime of waiting"
    assert t.counters["stale_regate"] == 1
    shutil.rmtree(d, ignore_errors=True)


def test_a_still_good_plan_is_implemented_after_the_rebase():
    d, sh, path, wt = _ticket_awaiting_approval()
    (d / "unrelated.py").write_text("someone else's fix\n")
    sh("git add unrelated.py && git commit -qm 'base moved'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    rec["proc"].wait()
    supervisor.finish(d, rec)

    t = Ticket.load(path)
    assert t.stage == "implementing", "a plan that still gates clean was bounced"
    assert (wt / "unrelated.py").exists(), "the branch never picked base up"
    assert not t.lease_active()
    shutil.rmtree(d, ignore_errors=True)


def test_a_rebase_conflict_on_approval_escalates_and_keeps_the_worktree():
    """Same rule as a merge conflict: never auto-resolved, never retried, and
    the conflicted index stays put because it is the evidence."""
    d, sh, path, wt = _ticket_awaiting_approval()
    (wt / "f.py").write_text("branch side\n")
    _commit(wt, "'ticket commit'")
    (d / "f.py").write_text("base side\n")
    sh("git add f.py && git commit -qm 'base moved'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec and rec["kind"] == "regate"
    rec["proc"].wait()
    supervisor.finish(d, rec)

    t = Ticket.load(path)
    assert t.stage == "escalated"
    assert wt.is_dir(), "the conflicted worktree is the evidence"
    assert "f.py" in sh(f"git -C {wt} diff --name-only --diff-filter=U").stdout, \
        "the conflict was resolved instead of left for the human"
    assert t.counters.get("stale_regate", 0) == 0, "a conflict is not a stale plan"
    assert not t.lease_active(), "an escalated ticket a human cannot resume"
    shutil.rmtree(d, ignore_errors=True)


def test_a_bound_escalation_emits_an_escalated_event():
    """`escalate()` emits for the paths it owns -- a crash, a tamper, an
    unusable ticket. The OTHER route into `escalated` is `transition()`
    returning it because `charge()` hit the class bound, and that route wrote
    only a `transition` row. View 1, the headline, therefore reported
    `plan-validation runs 0 escalated 0 rate -` for a ticket that had just
    escalated out of plan-validation: a miscalibrated prompt was invisible
    while a crashed harness was loud.

    The gate's own `stage_end` is the other half of the same number -- with no
    agent spawned, nothing else records that the stage ran at all.
    """
    d, _ = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    # one attempt already spent; `bugfix` has a bound of 2
    path.write_text(FIXTURE.replace("counters: {}",
                                    "counters: {plan_validation_attempts: 1}"))
    s = Store(Path(tempfile.mkdtemp()) / "events.db")
    # the gate fails: FIXTURE's `test_file` does not exist in this checkout
    supervisor.start(d, path, harness("fake"), {}, None, s.emitter(str(d)))

    assert Ticket.load(path).stage == "escalated"
    esc = [e for e in s.since(0) if e["kind"] == "escalated"]
    assert [e["stage"] for e in esc] == ["plan-validation"], \
        [(e["kind"], e["stage"]) for e in s.since(0)]
    assert "plan_validation_attempts" in esc[0]["data"]["reason"], esc
    assert "2" in esc[0]["data"]["reason"], "the reason does not name the bound"

    conn = metrics.connect(s.path)
    try:
        assert metrics.escalation_rate(conn, "plan-validation") == 1.0, \
            [(r["stage"], r["runs"], r["escalated"])
             for r in metrics.escalation_rates(conn)]
        # and the gate's verdict is readable by view 4 whatever its case
        assert metrics.gate_failure_reasons(conn), "view 4 sees no gate failure"
    finally:
        conn.close()
    s.close()
    shutil.rmtree(d, ignore_errors=True)


def test_escalate_and_advance_do_not_both_emit_for_one_ticket():
    """Two emit sites for one kind is one double-count away from a metric that
    reads 200%. `escalate()` sets the stage itself and never routes through
    `advance()`; this pins that."""
    d = project()
    seen = []
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    supervisor.escalate(t, "boom", lambda kind, **kw: seen.append(kind))
    assert seen == ["escalated"], seen

    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.stage = "merging"
    seen.clear()
    supervisor.advance(d, t, "fail", "conflict",
                       lambda kind, **kw: seen.append(kind))
    assert seen == ["transition", "escalated"], seen
    shutil.rmtree(d, ignore_errors=True)
