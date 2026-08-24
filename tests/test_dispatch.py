"""What the dispatcher does with a ticket it cannot run."""
import argparse
import json
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
    assert M.transition("verifying", "clean", {})[0] == "merging"
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


def test_a_fenced_diff_parks_before_merging():
    """A diff that edits `transition()` is exactly what `CLAUDE.md` fences off
    from unattended merge -- the suite passing is not enough to land it."""
    d, sh = git_project()
    (d / "pipeline/core").mkdir(parents=True)
    (d / "pipeline/core/machine.py").write_text("def transition():\n    return 1\n")
    sh("git add -A && git commit -qm 'add machine.py'")
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: verifying"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "pipeline/core/machine.py").write_text("def transition():\n    return 2\n")
    _commit(wt, "'edit transition'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec
    rec["proc"].wait()
    supervisor.finish(d, rec)

    assert Ticket.load(path).stage == "awaiting-merge"
    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert not did and not rec, "a human gate must not spawn"
    shutil.rmtree(d, ignore_errors=True)


def test_an_unfenced_diff_merges_without_a_human():
    """An edit outside the fenced list reaches `merging` on its own."""
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: verifying"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "g.py").write_text("the fix\n")
    _commit(wt, "'ticket commit'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec
    rec["proc"].wait()
    supervisor.finish(d, rec)

    assert Ticket.load(path).stage == "merging"
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


def test_a_dirty_worktree_still_lands_through_the_merge_fallback():
    """TICKET-045: `git rebase` refuses a worktree with unstaged changes --
    `error: cannot rebase: You have unstaged changes.`, exit 128 -- where
    `git merge` lands the same case today. The rebase step must not fail the
    merge child, or worktrees that land today start escalating."""
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "ticket.py").write_text("the ticket's own change\n")
    _commit(wt, "'ticket commit'")
    (wt / "leftover.py").write_text("a file base never touches\n")
    _commit(wt, "'a file base never touches'")
    (wt / "leftover.py").write_text("uncommitted edit\n")   # left dirty, not committed

    (d / "other.py").write_text("an unrelated ticket lands\n")
    sh("git add -A && git commit -qm 'other ticket'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec and rec["kind"] == "merge"
    rec["proc"].wait()
    supervisor.finish(d, rec)

    assert Ticket.load(path).stage == "done"
    assert "ticket commit" in sh("git log --oneline main").stdout
    shutil.rmtree(d, ignore_errors=True)


def test_a_merging_rebase_lands_a_linear_history_on_base():
    """TICKET-045: the catch-up onto base at `merging` must be a replay, not a
    merge -- a merge commit on base means the rebase step never ran."""
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "ticket.py").write_text("the ticket's own change\n")
    _commit(wt, "'ticket commit'")

    (d / "other1.py").write_text("an unrelated ticket lands\n")
    sh("git add -A && git commit -qm 'other ticket 1'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec and rec["kind"] == "merge"
    rec["proc"].wait()
    supervisor.finish(d, rec)

    assert Ticket.load(path).stage == "done"
    log = sh("git log --oneline main").stdout
    assert "ticket commit" in log
    assert "other ticket 1" in log
    assert sh("git log --merges --oneline main").stdout.strip() == "", \
        "the catch-up put a merge commit on base instead of replaying the branch"
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


def test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage():
    """A conflicting rebase is repaired by discarding the branch's commits,
    not by resolving them: abort the rebase, reset the branch onto base, and
    hand the ticket back to `triage`, which rewrites its test against the
    tree that now exists."""
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
    assert t.stage == "triage"
    assert t.counters["rebase_conflicts"] == 1
    assert t.counters.get("stale_regate", 0) == 0, "a conflict is not a stale plan"
    assert not t.lease_active()
    assert wt.is_dir(), "the branch is recut, not discarded"
    assert sh(f"git -C {wt} diff --name-only --diff-filter=U").stdout == "", \
        "the conflict was left unresolved instead of being discarded"
    assert (wt / "f.py").read_text() == "base side\n"
    log = sh(f"git -C {wt} log --oneline").stdout
    assert "base moved" in log
    assert "ticket commit" not in log
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


# --------------------------------------------------------------------------
# the adversarial review's confirmed findings
# --------------------------------------------------------------------------
def test_a_harness_that_cannot_register_hooks_escalates_one_ticket():
    """`spawn()` refuses a stage whose hooks a harness cannot register
    (invariant 4). That refusal came out AFTER `take_lease()/save()`, through
    `tick` and `run`, and `finally: shut_down` then terminated every other
    in-flight agent: one ticket's harness mismatch killed the dispatcher.
    Invariant 6 -- the library raises, one broken ticket does not take the
    loop down."""
    d, _ = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: implementing"))
    assert not harness("codex").get("supports_hooks")
    assert config.stage_config("implementing").get("hooks")

    did, rec = supervisor.start(d, path, harness("codex"), {})

    assert (did, rec) == (True, None), "the refusal escaped start()"
    t = Ticket.load(path)
    assert t.stage == "escalated", t.stage
    assert not t.lease_active(), "escalated with the lease it took still held"
    assert "hooks" in t.section("Thread"), t.section("Thread")
    shutil.rmtree(d, ignore_errors=True)


def test_a_ticket_that_raises_in_start_does_not_take_the_tick_down():
    """The general form of the same invariant: whatever `start()` raises for
    one ticket, the other tickets in the pass still get their turn and the
    in-flight agents keep their leases."""
    d = project()
    boom = []
    real = supervisor.start

    def explode(project, path, *a, **kw):
        boom.append(path)
        raise RuntimeError("kaboom")

    supervisor.start = explode
    try:
        supervisor.tick(d, harness("fake"), {})
    finally:
        supervisor.start = real
    assert boom, "the ticket was never tried"
    shutil.rmtree(d, ignore_errors=True)


def test_two_tickets_never_merge_in_the_same_tick():
    """Both would `git merge base` against the same base; the first
    `--ff-only` to land moves base, and the second -- a fully verified,
    non-overlapping ticket -- escalates for a merge that succeeds a tick
    later. `transition("merging","fail")` has no retry, by design."""
    d, sh = git_project()
    paths = []
    for n, files in (("001", "[f.py]"), ("002", "[g.py]")):
        p = d / f".project/tickets/TICKET-{n}.md"
        p.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging")
                     .replace("id: TICKET-001", f"id: TICKET-{n}")
                     .replace("branch: ticket/001", f"branch: ticket/{n}")
                     .replace("files_declared: [thing.py]", f"files_declared: {files}"))
        wt = supervisor.ensure_worktree(
            d, {"id": f"TICKET-{n}", "branch": f"ticket/{n}"}, {"base": "main"})
        (wt / f"{n}.py").write_text("the fix\n")
        _commit(wt, f"'commit {n}'")
        paths.append(p)

    inflight = {}
    supervisor.tick(d, harness("fake"), inflight)
    assert len(inflight) == 1, "two merges ran against one base"

    for _ in range(6):                       # drain: one merge per tick
        for rec in list(inflight.values()):
            rec["proc"].wait()
        supervisor.tick(d, harness("fake"), inflight)

    stages = [Ticket.load(p).stage for p in paths]
    assert stages == ["done", "done"], stages
    log = sh("git log --oneline main").stdout
    assert "commit 001" in log and "commit 002" in log, log
    shutil.rmtree(d, ignore_errors=True)


def test_an_escalation_before_any_child_still_ends_the_stage():
    """View 1 is `escalated / stage_end` per stage. `escalate()`'s pre-spawn
    call sites emitted only the numerator, so one completed run plus two
    lease-expiry escalations rendered a 200% escalation rate."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: implementing")
                    .replace("counters: {}", "counters: {lease_expiries: 1}")
                    .replace("lease: {holder: null, expires: null}",
                             "lease: {holder: 'implementing-1', expires: '2000-01-01T00:00:00+00:00'}"))
    s = Store(Path(tempfile.mkdtemp()) / "events.db")
    supervisor.start(d, path, harness("fake"), {}, None, s.emitter(str(d)))

    assert Ticket.load(path).stage == "escalated"
    conn = metrics.connect(s.path)
    try:
        rates = {r["stage"]: r for r in metrics.escalation_rates(conn)}
        r = rates["implementing"]
        assert r["escalated"] == 1 and r["runs"] == 1, r
        assert r["rate"] == 1.0, r
    finally:
        conn.close()
    s.close()
    shutil.rmtree(d, ignore_errors=True)


def test_a_child_log_that_is_not_utf8_still_advances_the_ticket():
    """`read_text()` decodes strict utf-8 over output we did not write. One
    stray byte from git or a test runner raised inside `finish()`, `reap()`
    caught and printed it, and the lease was held until it expired."""
    d, _ = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: verifying"))
    (d / ".project/pipeline.toml").write_text(
        "test_one='true'\ntest_suite='exit 1'\n"
        "test_suite_without_new='true'\nbase='main'\n")

    _, rec = supervisor.start(d, path, harness("fake"), {})
    rec["proc"].wait()
    # the child writes to this fd directly, so this is exactly what a test
    # runner emitting one latin-1 byte leaves behind
    with rec["log"].open("ab") as fh:
        fh.write(b"E: caf\xe9 not found\n")
    try:
        rec["log"].read_text()
        assert False, "the log decodes cleanly -- this test proves nothing"
    except UnicodeDecodeError:
        pass
    supervisor.finish(d, rec)

    t = Ticket.load(path)
    assert t.stage == "implementing", "the verdict never reached advance()"
    assert not t.lease_active(), "the lease outlived the child"
    shutil.rmtree(d, ignore_errors=True)


def test_the_summary_marker_is_recorded_when_a_verdict_is_applied():
    """`pipeline/stages/_common.md` tells every stage to start `summary:` with
    `✓ `. The marker is evidence that the shared prose rules were still in the
    agent's context at the end of a long run. Nothing reads it, so a stage that
    drops the marker advances exactly like one that keeps it.

    Design-neutral on purpose: the record may be an event field, a thread note,
    or both. What it may not be is nothing. The summary text itself is stripped
    from the ticket body before comparing, or the note echo alone would pass
    this vacuously.
    """
    def run(summary: str) -> tuple[list, str]:
        d = project()
        path = d / ".project/tickets/TICKET-001.md"
        seen: list = []
        t = Ticket.load(path)
        supervisor.advance(d, t, "ok", summary,
                           lambda kind, **kw: seen.append((kind, kw)))
        body = path.read_text().replace(summary, "")
        shutil.rmtree(d, ignore_errors=True)
        return seen, body

    with_marker, body_with = run("✓ reproduced, failing test committed")
    without, body_without = run("reproduced, failing test committed")

    assert (with_marker, body_with) != (without, body_without), (
        "the marker is not recorded: a summary with it and a summary without "
        "it leave identical events and identical ticket text\n"
        f"events: {with_marker}")


def test_the_marker_record_names_the_agents_summary_and_nothing_else():
    """The marker is evidence about a stage prompt, never a verdict, so it
    is recorded per stage in two places: a `marker` field on the
    `transition` event, and a `marker=` attr on the thread entry header.

    The dispatcher's own notes -- `dispatcher pickup`, a failed gate, a
    merge exit code -- were written by no agent, so they carry no field
    at all. A `False` there would read as a prompt that dropped the rule.
    """
    def run(summary: str, **kw) -> tuple[dict, str]:
        d = project()
        path = d / ".project/tickets/TICKET-001.md"
        seen: list = []
        supervisor.advance(d, Ticket.load(path), "ok", summary,
                           lambda kind, **k: seen.append(k), **kw)
        body = path.read_text()
        shutil.rmtree(d, ignore_errors=True)
        return seen[0], body

    marked, marked_body = run("✓ planned")
    tight, _ = run("✓planned")           # loose_result() ate the space
    bare, bare_body = run("planned")
    pickup, pickup_body = run("dispatcher pickup", agent=False)
    none_case, _ = run(None)             # summary: with no value parses to None

    assert marked["marker"] is True
    assert tight["marker"] is True, "match the character, not character+space"
    assert bare["marker"] is False
    assert "marker=yes" in marked_body and "marker=no" in bare_body
    assert "marker" not in pickup, pickup
    assert "marker=" not in pickup_body
    assert none_case["marker"] is False


def test_a_missing_marker_changes_no_transition_and_no_counter():
    """Evidence, not a verdict: an unmarked summary must advance exactly
    like a marked one. If this ever fails, someone turned a prose-rule
    reminder into a gate on the agent's work."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    supervisor.advance(d, Ticket.load(path), "ok", "no marker here")
    t = Ticket.load(path)
    shutil.rmtree(d, ignore_errors=True)
    assert t.stage == "awaiting-approval"
    assert t.counters == {}


def test_a_rebase_conflict_at_revalidating_leaves_a_way_back():
    """TICKET-029: a conflict at `revalidating` is terminal, so a ticket whose
    triage test collided with a sibling's costs a full re-triage by hand.
    `finish_regate()` calls `escalate()` directly -- `transition()` never sees
    the conflict, so no counter is charged and no stage can fix it."""
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
    shutil.rmtree(d, ignore_errors=True)
    assert t.stage not in M.TERMINAL, \
        f"a rebase conflict parked the ticket at {t.stage} with no way back"


def test_a_merged_dispatcher_change_reaches_the_running_loop():
    """A harness `.toml` edit reaches the next tick (`_harness_reloader`), but
    a merged change to the dispatcher's own Python does not: the loop keeps
    running the code it imported at startup. `run()` must notice its source
    changed and return, so whatever supervises it starts the new code."""
    import os

    src = Path(supervisor.__file__)
    before = src.stat().st_mtime

    class Stop(Exception):
        pass

    d = project()
    seen, orig_tick = [], supervisor.tick

    def fake_tick(proj, hcfg, *a, **kw):
        seen.append(len(seen))
        if len(seen) == 1:
            os.utime(src, (before + 10, before + 10))  # a merge lands
        if len(seen) >= 3:
            raise Stop("still running the code it imported at startup")
        return False

    supervisor.tick = fake_tick
    try:
        supervisor.run(d, once=False, interval=0, harness_name="fake")
    except Stop as e:
        raise AssertionError(
            f"dispatcher source changed at tick 1, still looping at tick 3: {e}")
    finally:
        supervisor.tick = orig_tick
        os.utime(src, (before, before))
        shutil.rmtree(d, ignore_errors=True)

    assert len(seen) == 1, \
        f"expected the loop to exit at the first tick boundary, got {len(seen)} ticks"


def test_a_merged_dispatcher_change_ends_the_daemon_loop_too():
    """`serve()` is `run()`'s loop with `run()`'s defect. Triage covered
    `run()` only."""
    import os
    import tempfile

    from pipeline.daemon import registry
    from pipeline.daemon.server import Server

    src = Path(supervisor.__file__)
    before = src.stat().st_mtime
    tmp = Path(tempfile.mkdtemp())
    d = project()
    store = Store(tmp / "events.db")
    server = Server(store, tmp / "daemon.sock")
    seen, orig_tick = [], supervisor.tick

    class Stop(BaseException):     # serve() catches Exception around tick()
        pass

    def fake_tick(proj, hcfg, *a, **kw):
        seen.append(len(seen))
        if len(seen) == 1:
            os.utime(src, (before + 10, before + 10))   # a merge lands
        if len(seen) >= 3:
            raise Stop("still running the code it imported at startup")
        return False

    supervisor.tick = fake_tick
    registry.register(d)
    try:
        supervisor.serve(0, "fake", 1, store, server, once=False)
    except Stop as e:
        raise AssertionError(
            f"daemon source changed at tick 1, still looping at tick 3: {e}")
    finally:
        supervisor.tick = orig_tick
        os.utime(src, (before, before))
        registry.unregister(d)
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    assert len(seen) == 1, f"expected serve() to exit after tick 1, got {len(seen)}"


def test_a_stale_dispatcher_reaps_its_children_before_it_exits():
    """The exit is at a tick boundary with no children running: a stale loop
    stops claiming tickets (`tick()` sees `stopping() is True`) and keeps
    reaping until `inflight` is empty."""
    import os

    src = Path(supervisor.__file__)
    before = src.stat().st_mtime
    d = project()
    seen, flags, orig_tick = [], [], supervisor.tick

    def fake_tick(proj, hcfg, inflight, max_parallel, poller, emit, stopping):
        seen.append(len(seen))
        flags.append(stopping())
        if len(seen) == 1:
            inflight["TICKET-001"] = {"fake": True}   # a child is running
            os.utime(src, (before + 10, before + 10))
        if len(seen) == 2:
            inflight.clear()                          # it finished; shut_down
        if len(seen) >= 4:                            # must not see the fake
            raise AssertionError("a stale loop never exited")
        return False

    supervisor.tick = fake_tick
    try:
        supervisor.run(d, once=False, interval=0, harness_name="fake")
    finally:
        supervisor.tick = orig_tick
        os.utime(src, (before, before))
        shutil.rmtree(d, ignore_errors=True)

    assert len(seen) == 2, f"expected a reaping tick 2, got {len(seen)} ticks"
    assert flags == [False, True], \
        f"a stale loop must stop claiming tickets: stopping() was {flags}"


def test_a_readonly_stage_snapshots_after_the_settings_strip():
    """A baseline taken before the strip would read the strip's own removal as
    a write the read-only stage made -- `wrote-in-readonly`."""
    d, sh = git_project()
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    wt = supervisor.ensure_worktree(d, meta, {"base": "main"})
    (wt / ".claude").mkdir(parents=True)
    (wt / ".claude" / "settings.json").write_text(json.dumps({"disableAllHooks": True}))
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: review"))

    did, rec = supervisor.start(d, path, harness("fake"), {})
    rec["proc"].wait()
    supervisor.close_child(rec)

    assert not (wt / ".claude" / "settings.json").exists()
    assert rec["before"] == supervisor.tree_snapshot(wt), \
        "the read-only baseline was taken before the strip, so the removal " \
        "reads as wrote-in-readonly"
    shutil.rmtree(d, ignore_errors=True)


def test_a_readonly_stage_that_writes_the_main_checkout_escalates():
    """A read-only stage's `--add-dir` reaches `<project>/.project`, but Bash
    or a human can still dirty the main checkout outside it. That must
    escalate exactly like a write inside the worktree does."""
    d, _ = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: review"))

    did, rec = supervisor.start(d, path, harness("fake"), {})
    (d / "f.py").write_text("an edit the stage made in the wrong tree\n")
    rec["proc"].wait()
    supervisor.finish(d, rec)

    assert Ticket.load(path).stage == "escalated"
    assert "main checkout" in path.read_text()
    shutil.rmtree(d, ignore_errors=True)


def test_a_finished_ticket_and_its_decision_are_committed_to_the_base_branch():
    """Nothing used to put a ticket into git. `.project/` is tracked, but no
    code path and no stage prompt ran `git add` on it -- a stage cannot, since
    its cwd is the worktree while the ticket lives in the main checkout. So the
    record of what the pipeline did was whatever somebody remembered to commit
    by hand.

    The decision file is the half that matters: `planning` greps
    `.project/decisions/` so it does not re-decide settled questions, and one
    that never reaches a commit is invisible to every future clone.
    """
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging"))
    t = T.Ticket.load(path)

    supervisor.advance(d, t, "ok", "landed", agent=False)

    assert T.Ticket.load(t.path).stage == "done", "fixture assumption broken"
    tracked = sh("git ls-files .project/tickets/").stdout
    assert ".project/tickets/TICKET-001.md" in tracked, \
        "the finished ticket never reached a commit"
    assert not sh("git status --porcelain .project/tickets/").stdout.strip(), \
        "the ticket was committed but left dirty -- stage: done came after"


def test_the_record_is_not_committed_onto_a_branch_that_is_not_the_base():
    """The commit lands in the operator's main checkout, so it refuses for the
    same reason `merge_cmd` refuses: a checkout parked elsewhere is somebody
    working, and a ticket left untracked is where it already was."""
    d, sh = git_project()
    sh("git checkout -qb somewhere-else")
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging"))
    t = T.Ticket.load(path)

    supervisor.advance(d, t, "ok", "landed", agent=False)

    assert T.Ticket.load(t.path).stage == "done", "the ticket must still advance"
    assert ".project" not in sh("git ls-files .project/").stdout, \
        "committed onto a branch that is not the base"


def test_a_git_ignored_project_dir_is_left_alone_and_says_so(capsys):
    """A shared repo where not everyone runs the pipeline: `.project/` is
    excluded and the tickets are a local queue. `git add` refuses an ignored
    path, so the record was already skipped -- silently, which reads exactly
    like a commit that failed. The ticket must still finish."""
    d, sh = git_project()
    (d / ".gitignore").write_text(".project/\n")
    sh("git add .gitignore && git commit -qm ignore")
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging"))

    supervisor.advance(d, T.Ticket.load(path), "ok", "landed", agent=False)

    assert T.Ticket.load(path).stage == "done", "an ignored .project must not block the ticket"
    assert not sh("git ls-files .project/").stdout.strip(), "committed an ignored path"
    assert "git-ignored" in capsys.readouterr().out, \
        "skipped the record without saying why"


def test_a_project_override_reaches_the_spawned_command_and_prompt():
    """TICKET-038: a project's `[stages.<name>]` table and its
    `.project/stages/<name>.extra.md` both reach a real spawn, not just the
    functions in isolation."""
    d = project()
    with (d / ".project" / "pipeline.toml").open("a") as f:
        f.write('\n[stages.review]\nmodel = "haiku"\n')
    (d / ".project" / "stages").mkdir(parents=True)
    (d / ".project" / "stages" / "review.extra.md").write_text(
        "## Project rule\n\n- EXTRA-MARKER-4471\n")

    recorded = {}
    real_compose_prompt = supervisor.compose_prompt

    def recorder(*args, **kwargs):
        path = real_compose_prompt(*args, **kwargs)
        recorded["text"] = path.read_text()
        return path

    supervisor.compose_prompt = recorder
    try:
        rec = supervisor.spawn(d, d, "TICKET-001", "review", harness("fake"))
        rec["proc"].wait()
        supervisor.close_child(rec)
    finally:
        supervisor.compose_prompt = real_compose_prompt

    logs = list((d / ".project" / "logs").glob("TICKET-001-review-*.log"))
    assert logs, "no spawn log written"
    first_line = logs[0].read_text().splitlines()[0]
    assert "haiku" in first_line, first_line
    assert "EXTRA-MARKER-4471" in recorded["text"]


def test_a_ticket_held_at_merging_is_rebased_before_the_merge_is_attempted():
    """TICKET-045: `revalidating` rebases a ticket onto base once, right after
    approval. Nothing rebases it again. `files_conflict` and `start()`'s merge
    serialisation can then hold an approved, verified ticket at `merging` for
    an arbitrarily long time while base moves underneath it, so the eventual
    `git merge --no-edit <base>` in `merge_cmd()` can fail on a conflict that
    a rebase closer to the merge would have caught, or avoided, sooner.

    This reproduces the wait: the ticket's branch is left exactly where the
    approval-time rebase put it, base then moves twice (two other tickets'
    changes land), and `start()` runs the ticket's `merging` stage. The
    dispatcher should rebase the branch onto the now-current base before
    attempting the merge -- it does not."""
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "ticket.py").write_text("the ticket's own change\n")
    _commit(wt, "'ticket commit'")

    (d / "other1.py").write_text("first unrelated ticket lands\n")
    sh("git add -A && git commit -qm 'other ticket 1'")
    (d / "other2.py").write_text("second unrelated ticket lands\n")
    sh("git add -A && git commit -qm 'other ticket 2'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec and rec["kind"] == "merge"
    rec["proc"].wait()

    log_text = rec["log"].read_text()
    cmd_line = log_text.splitlines()[0]
    assert "rebase" in cmd_line, (
        "merging attempted no rebase before merge_cmd()'s first step -- "
        f"the command run was: {cmd_line!r}. A ticket held at `merging` "
        "while base moves underneath it gets no chance to catch up before "
        "the merge is attempted.")

    supervisor.finish(d, rec)
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(d, ignore_errors=True)
