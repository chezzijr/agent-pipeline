"""What the dispatcher does with a ticket it cannot run."""
import argparse
import json
import shutil
import subprocess
import tempfile
import time
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
from pipeline.daemon.server import ticket_rows, waiting_text


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


def test_a_done_ticket_runs_worktree_teardown():
    """The dispatcher's cleanup path must pass the project config through to
    `drop_worktree()`, or a project's `worktree_teardown` never runs."""
    d, _ = git_project()
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    marker = Path(tempfile.mkdtemp()) / "TICKET-001.marker"
    marker.write_text("keyed cache\n")
    with open(d / ".project" / "pipeline.toml", "a") as f:
        f.write(f'worktree_teardown = "rm -f {marker}"\n')
    wt = supervisor.ensure_worktree(d, meta, {"base": "main"})
    (d / ".project/tickets/TICKET-001.md").write_text(
        FIXTURE.replace("stage: plan-validation", "stage: done"))
    supervisor.start(d, d / ".project/tickets/TICKET-001.md", harness("fake"), {})
    assert not marker.exists(), "worktree_teardown never ran through the dispatcher cleanup path"
    shutil.rmtree(d, ignore_errors=True)


def test_a_done_ticket_without_a_config_still_releases_its_worktree():
    """`project_config()` raises for a project with no `.project/pipeline.toml`.
    The cleanup path must fall back rather than strand the worktree."""
    d, _ = git_project()
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    wt = supervisor.ensure_worktree(d, meta, {"base": "main"})
    (d / ".project" / "pipeline.toml").unlink()
    (d / ".project/tickets/TICKET-001.md").write_text(
        FIXTURE.replace("stage: plan-validation", "stage: done"))
    supervisor.start(d, d / ".project/tickets/TICKET-001.md", harness("fake"), {})
    assert not wt.is_dir(), "a missing project config stranded a finished ticket's worktree"
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


def test_a_spawn_tells_the_guard_where_its_worktree_is():
    """`PIPELINE_WORKTREE`, `PIPELINE_TICKET` and `PIPELINE_RESULT` are what
    the guard's path rule compares a file tool's path against."""
    d, _ = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: implementing"))
    dump = d / "dump.txt"

    hcfg = dict(harness("fake"))
    hcfg["cmd"] = (
        'printf "%s\\n%s\\n%s\\n" "$PIPELINE_WORKTREE" "$PIPELINE_TICKET" '
        f'"$PIPELINE_RESULT" > {dump}; '
        'printf "result: ok\\nsummary: x\\n" > {result_file}')

    did, rec = supervisor.start(d, path, hcfg, {})
    assert did and rec is not None
    rec["proc"].wait()

    lines = dump.read_text().splitlines()
    assert lines == [
        str(d / ".worktrees" / "TICKET-001"),
        str(path),
        str(d / ".project/tickets/TICKET-001.result"),
    ], lines
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


def test_verifying_substitutes_the_name_placeholder_in_test_suite():
    """`test_suite` was the one command the dispatcher never formatted, so a
    project could not select by `{name}` there -- TICKET-067."""
    d, _ = git_project()
    (d / ".project/pipeline.toml").write_text(
        'test_one = "true"\n'
        'test_suite = "echo GOT:{name}"\n'
        'test_suite_without_new = "true"\nbase = "main"\n')
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: verifying"))

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec and rec["kind"] == "suite"
    rec["proc"].wait()
    supervisor.finish(d, rec)

    assert "GOT:test_broken" in rec["log"].read_text()
    assert Ticket.load(path).stage in ("awaiting-merge", "merging")
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


def _gating_project():
    """A git project whose Tier A gate can be run: a committed test file and
    a `pipeline.toml` whose `test_one` fails and whose `test_suite_without_new`
    reads a file base can add, so "another ticket landed and broke it" is one
    commit."""
    d, sh = git_project()
    (d / "test_thing.py").write_text("")
    sh("git add test_thing.py && git commit -qm 'the test file'")
    (d / ".project/pipeline.toml").write_text(
        'test_one = "echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "! test -f broken"\n'
        'base = "main"\n')
    return d, sh


def _ticket_awaiting_approval():
    """A git project whose ticket is parked at the human gate, with a worktree
    on its branch -- where every re-gate case starts."""
    d, sh = _gating_project()
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
    agent spawned, `finish()` on the gate child is what records that the
    stage ran at all.
    """
    d, sh = git_project()
    (d / "test_thing.py").write_text("")
    sh("git add test_thing.py && git commit -qm 'the test file'")
    # `test_one` must exit non-zero without naming the node, or the run reads
    # as passing on both trees and now returns `load-flaky` (TICKET-109),
    # which escalates without charging -- this test needs the bound reached.
    (d / ".project/pipeline.toml").write_text(
        'test_one="false"\ntest_suite="true"\ntest_suite_without_new="true"\nbase="main"\n')
    path = d / ".project/tickets/TICKET-001.md"
    # one attempt already spent; `bugfix` has a bound of 2
    path.write_text(FIXTURE.replace("counters: {}",
                                    "counters: {plan_validation_attempts: 1}"))
    s = Store(Path(tempfile.mkdtemp()) / "events.db")
    # the gate fails because `test_one` exits non-zero without naming the
    # test, which is a substantive gate failure (`bad-plan`) and this test
    # needs the bound reached.
    did, rec = supervisor.start(d, path, harness("fake"), {}, None, s.emitter(str(d)))
    rec["proc"].wait()
    supervisor.finish(d, rec, s.emitter(str(d)))

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
    incapable = dict(harness("fake"), supports_hooks=False)
    assert config.stage_config("implementing").get("hooks")

    did, rec = supervisor.start(d, path, incapable, {})

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


def test_a_project_max_parallel_caps_ticket_concurrency():
    """`.project/pipeline.toml` can lower the daemon's `-j` for one project.
    Two triage-stage tickets, `max_parallel = 1` in the project config, one
    `tick()` at the CLI's default `-j 3` -- only one should start."""
    d, sh = git_project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\n'
        'base="main"\nmax_parallel = 1\n')
    sh("git add -A && git commit -qm 'lower max_parallel'")
    for n, fname in (("001", "thing.py"), ("002", "other.py")):
        (d / f".project/tickets/TICKET-{n}.md").write_text(
            FIXTURE.replace("stage: plan-validation", "stage: triage")
            .replace("id: TICKET-001", f"id: TICKET-{n}")
            .replace("branch: ticket/001", f"branch: ticket/{n}")
            .replace("files_declared: [thing.py]", f"files_declared: [{fname}]"))

    inflight = {}
    supervisor.tick(d, harness("fake"), inflight, 3)
    assert len(inflight) == 1, \
        f"project max_parallel=1 should cap this project at 1, got {len(inflight)}"
    shutil.rmtree(d, ignore_errors=True)


def test_a_project_cannot_raise_the_daemons_max_parallel():
    """A project `max_parallel = 5` must never widen the daemon's own `-j 1`
    -- the config a ticket branch can reach must only lower the ceiling."""
    d, sh = git_project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\n'
        'base="main"\nmax_parallel = 5\n')
    sh("git add -A && git commit -qm 'raise max_parallel'")
    for n, fname in (("001", "thing.py"), ("002", "other.py")):
        (d / f".project/tickets/TICKET-{n}.md").write_text(
            FIXTURE.replace("stage: plan-validation", "stage: triage")
            .replace("id: TICKET-001", f"id: TICKET-{n}")
            .replace("branch: ticket/001", f"branch: ticket/{n}")
            .replace("files_declared: [thing.py]", f"files_declared: [{fname}]"))

    inflight = {}
    supervisor.tick(d, harness("fake"), inflight, 1)
    assert len(inflight) == 1, \
        f"the daemon -j 1 must win over the project 5, got {len(inflight)}"
    shutil.rmtree(d, ignore_errors=True)


def test_a_bad_project_max_parallel_never_leaves_tick(capsys):
    """A committed `max_parallel = 0` must not raise out of `tick()` -- it
    reaches `run()`'s bare `tick()` call, which does not wrap it, and a raise
    there would SIGTERM every inflight child via `shut_down()`."""
    d, sh = git_project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\n'
        'base="main"\nmax_parallel = 0\n')
    sh("git add -A && git commit -qm 'zero max_parallel'")
    for n, fname in (("001", "thing.py"), ("002", "other.py")):
        (d / f".project/tickets/TICKET-{n}.md").write_text(
            FIXTURE.replace("stage: plan-validation", "stage: triage")
            .replace("id: TICKET-001", f"id: TICKET-{n}")
            .replace("branch: ticket/001", f"branch: ticket/{n}")
            .replace("files_declared: [thing.py]", f"files_declared: [{fname}]"))

    inflight = {}
    supervisor.tick(d, harness("fake"), inflight, 3)
    assert len(inflight) == 2, \
        f"a bad max_parallel must leave -j 3 standing, got {len(inflight)}"
    assert "ignoring max_parallel" in capsys.readouterr().out
    shutil.rmtree(d, ignore_errors=True)


def test_a_malformed_project_pipeline_toml_never_leaves_tick(capsys):
    """A committed `.project/pipeline.toml` that fails to parse must not raise
    out of `tick()` -- `project_config()` raises `tomllib.TOMLDecodeError`
    (a `ValueError`, not a `PipelineError`), and `run()`'s bare `tick()` call
    does not wrap it, so an unhandled raise would SIGTERM every inflight
    child via `shut_down()`."""
    d, sh = git_project()
    (d / ".project" / "pipeline.toml").write_text('[[[bad')
    sh("git add -A && git commit -qm 'break pipeline.toml'")
    for n, fname in (("001", "thing.py"), ("002", "other.py")):
        (d / f".project/tickets/TICKET-{n}.md").write_text(
            FIXTURE.replace("stage: plan-validation", "stage: triage")
            .replace("id: TICKET-001", f"id: TICKET-{n}")
            .replace("branch: ticket/001", f"branch: ticket/{n}")
            .replace("files_declared: [thing.py]", f"files_declared: [{fname}]"))

    inflight = {}
    supervisor.tick(d, harness("fake"), inflight, 3)  # must not raise
    out = capsys.readouterr().out
    assert "ignoring max_parallel" in out
    assert "start failed" in out
    shutil.rmtree(d, ignore_errors=True)


def test_the_daemons_max_parallel_is_not_machine_wide():
    """TICKET-094: `-j` is passed unchanged into every registered project's own
    `tick()`, each with its own `inflight` dict, so N projects multiply the
    daemon's `-j` instead of sharing it. With a machine cap of 1 and two
    projects each holding two queued triage tickets, the total number of
    inflight children across both projects must never exceed 1."""
    max_parallel = 1
    projects = []
    for i in range(2):
        d, sh = git_project()
        for n, fname in (("001", "thing.py"), ("002", "other.py")):
            (d / f".project/tickets/TICKET-{n}.md").write_text(
                FIXTURE.replace("stage: plan-validation", "stage: triage")
                .replace("id: TICKET-001", f"id: TICKET-{n}")
                .replace("branch: ticket/001", f"branch: ticket/{n}")
                .replace("files_declared: [thing.py]", f"files_declared: [{fname}]"))
        projects.append(d)

    inflights = [{} for _ in projects]
    for d, inflight in zip(projects, inflights):
        supervisor.tick(d, harness("fake"), inflight, max_parallel)

    total = sum(len(i) for i in inflights)
    for d in projects:
        shutil.rmtree(d, ignore_errors=True)
    assert total <= max_parallel, \
        f"machine cap is {max_parallel}, but {total} children are inflight " \
        f"across {len(projects)} projects"


def test_the_machine_cap_is_shared_when_both_projects_have_work():
    """A machine cap of 2 over two projects that both have work must split 1
    and 1, not let whichever project ticks first take both slots."""
    max_parallel = 2
    projects = []
    for i in range(2):
        d, sh = git_project()
        for n, fname in (("001", "thing.py"), ("002", "other.py")):
            (d / f".project/tickets/TICKET-{n}.md").write_text(
                FIXTURE.replace("stage: plan-validation", "stage: triage")
                .replace("id: TICKET-001", f"id: TICKET-{n}")
                .replace("branch: ticket/001", f"branch: ticket/{n}")
                .replace("files_declared: [thing.py]", f"files_declared: [{fname}]"))
        projects.append(d)

    supervisor.machine_watch(projects)
    inflights = [{} for _ in projects]
    for d, inflight in zip(projects, inflights):
        supervisor.tick(d, harness("fake"), inflight, max_parallel)

    counts = [len(i) for i in inflights]
    for d in projects:
        shutil.rmtree(d, ignore_errors=True)
    assert counts == [1, 1], \
        f"a machine cap of 2 over two busy projects must be 1 each, got {counts}"


def test_a_quiet_project_does_not_shrink_a_busy_ones_share():
    """A quiet project reports no demand, so it must not be counted among the
    rivals a busy project divides `-j` with."""
    busy, sh = git_project()
    for n, fname in (("001", "thing.py"), ("002", "other.py")):
        (busy / f".project/tickets/TICKET-{n}.md").write_text(
            FIXTURE.replace("stage: plan-validation", "stage: triage")
            .replace("id: TICKET-001", f"id: TICKET-{n}")
            .replace("branch: ticket/001", f"branch: ticket/{n}")
            .replace("files_declared: [thing.py]", f"files_declared: [{fname}]"))
    quiet, _ = git_project()

    supervisor.machine_watch([busy, quiet])
    supervisor.tick(quiet, harness("fake"), {}, 2)
    inflight = {}
    supervisor.tick(busy, harness("fake"), inflight, 2)

    count = len(inflight)
    shutil.rmtree(busy, ignore_errors=True)
    shutil.rmtree(quiet, ignore_errors=True)
    assert count == 2, \
        f"a quiet project takes no share of -j 2, expected 2 children, got {count}"


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
    # the dispatcher measured the FIXTURE plan; no attempt was charged
    assert t.counters == {"plan_steps": 1, "plan_files": 1}


def test_advance_seeds_the_plan_size_from_the_ticket():
    plan = "\n".join(f"{i}. touch thing.py" for i in range(1, 25))
    files = "\n".join(f"- f{i}.py" for i in range(10))
    body = FIXTURE.replace(
        "files_declared: [thing.py]", f"files_declared:\n{files}"
    ).replace(
        "counters: {}", "counters: {plan_validation_attempts: 1}"
    ).replace(
        "## Plan\n1. fix thing.py\n", f"## Plan\n{plan}\n"
    )
    d = project(body)
    path = d / ".project/tickets/TICKET-001.md"
    t = Ticket.load(path)
    t.stage = "plan-validation"
    supervisor.advance(d, t, "bad-plan", "n", agent=False)
    t = Ticket.load(path)
    shutil.rmtree(d, ignore_errors=True)
    assert t.stage == "planning"
    assert t.counters["plan_steps"] == 24
    assert t.counters["plan_files"] == 10


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

    class Stop(BaseException):     # run() catches Exception around tick()
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


def test_serve_rotates_which_project_ticks_first():
    """The share stops one project taking the whole cap, but whoever ticks
    first still gets first refusal on a slot that just freed. `serve()` must
    rotate which project it ticks first each pass."""
    import tempfile

    from pipeline.daemon import registry
    from pipeline.daemon.server import Server

    tmp = Path(tempfile.mkdtemp())
    p1, p2 = project(), project()
    store = Store(tmp / "events.db")
    server = Server(store, tmp / "daemon.sock")
    seen, orig_tick = [], supervisor.tick

    class Stop(BaseException):     # serve() catches Exception around tick()
        pass

    def fake_tick(proj, hcfg, *a, **kw):
        seen.append(str(proj))
        if len(seen) >= 4:
            raise Stop("rotation never changed the first project ticked")
        return False

    supervisor.tick = fake_tick
    registry.register(p1)
    registry.register(p2)
    try:
        supervisor.serve(0, "fake", 1, store, server, once=False)
    except Stop:
        pass
    finally:
        supervisor.tick = orig_tick
        registry.unregister(p1)
        registry.unregister(p2)
        shutil.rmtree(p1, ignore_errors=True)
        shutil.rmtree(p2, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    assert seen[0] != seen[2], f"pass 2 must not tick the same project first: {seen}"
    assert set(seen[:2]) == set(seen[2:])


def test_an_unwatched_project_stops_holding_machine_slots():
    """The two prunes that keep the machine budget from leaking: dropping a
    project the dispatcher no longer watches, and dropping one whose
    directory is gone."""
    import tempfile

    p1 = Path(tempfile.mkdtemp())
    p2 = Path(tempfile.mkdtemp())

    supervisor.machine_watch([p1, p2])
    supervisor.machine_share(p1, {"TICKET-001": {}, "TICKET-002": {}}, 2)
    assert supervisor.machine_share(p2, {}, 2) == 0, "p1 holds both slots"

    supervisor.machine_watch([p2])
    assert supervisor.machine_share(p2, {}, 2) == 2, \
        "an unwatched project must stop holding machine slots"

    supervisor.machine_watch([p1, p2])
    supervisor.machine_share(p1, {"TICKET-001": {}, "TICKET-002": {}}, 2)
    shutil.rmtree(p1)
    assert supervisor.machine_share(p2, {}, 2) == 2, \
        "a project directory that is gone must stop holding machine slots"

    supervisor.machine_watch([])
    shutil.rmtree(p1, ignore_errors=True)
    shutil.rmtree(p2, ignore_errors=True)


def test_a_stale_dispatcher_reaps_its_children_before_it_exits():
    """The exit is at a tick boundary with no children running: a stale loop
    stops claiming tickets (`tick()` sees `stopping() is True`) and keeps
    reaping until `inflight` is empty."""
    import os

    src = Path(supervisor.__file__)
    before = src.stat().st_mtime
    d = project()
    seen, flags, orig_tick = [], [], supervisor.tick

    class Stop(BaseException):     # run() catches Exception around tick()
        pass

    def fake_tick(proj, hcfg, inflight, max_parallel, poller, emit, stopping):
        seen.append(len(seen))
        flags.append(stopping())
        if len(seen) == 1:
            inflight["TICKET-001"] = {"fake": True}   # a child is running
            os.utime(src, (before + 10, before + 10))
        if len(seen) == 2:
            inflight.clear()                          # it finished; shut_down
        if len(seen) >= 4:                            # must not see the fake
            raise Stop("a stale loop never exited")
        return False

    supervisor.tick = fake_tick
    try:
        supervisor.run(d, once=False, interval=0, harness_name="fake")
    except Stop as e:
        raise AssertionError(str(e))
    finally:
        supervisor.tick = orig_tick
        os.utime(src, (before, before))
        shutil.rmtree(d, ignore_errors=True)

    assert len(seen) == 2, f"expected a reaping tick 2, got {len(seen)} ticks"
    assert flags == [False, True], \
        f"a stale loop must stop claiming tickets: stopping() was {flags}"


def test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception():
    """TICKET-086: `run()` catches `Exception` around `tick()`, so a test
    that detects a runaway loop by raising from a fake `tick()` must raise
    a `BaseException` subclass -- an `Exception` one is eaten by that catch
    and the test hangs at its timeout instead of failing."""
    d = project()

    class Stop(BaseException):
        pass

    calls, orig_tick = {"n": 0}, supervisor.tick

    def fake_tick(proj, hcfg, inflight, max_parallel, poller, emit, stopping):
        calls["n"] += 1
        raise Stop("a runaway loop detector must reach the test")

    supervisor.tick = fake_tick
    try:
        supervisor.run(d, once=True, interval=0, harness_name="fake")
        raise AssertionError("run() swallowed a BaseException loop detector")
    except Stop:
        pass
    finally:
        supervisor.tick = orig_tick
        shutil.rmtree(d, ignore_errors=True)

    assert calls["n"] == 1, f"expected one tick, got {calls['n']}"


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


def test_spawn_threads_the_tickets_counters_into_the_review_cap():
    """A review spawn's cap grows with the plan it has to read, and
    `rec["cap"]` -- the number `_finish()` names in a budget-kill escalation
    -- must carry the same scaled number `render()` used."""
    d = project(FIXTURE.replace("stage: plan-validation", "stage: review")
                .replace("counters: {}", "counters: {plan_files: 15, plan_steps: 40}"))
    rec = supervisor.spawn(d, d, "TICKET-001", "review", harness("fake"))
    rec["proc"].wait()
    supervisor.close_child(rec)
    assert rec["cap"] == 8, \
        "spawn() did not scale the 4 dollar review cap by the ticket plan size"

    d2 = project()
    rec2 = supervisor.spawn(d2, d2, "TICKET-001", "review", harness("fake"))
    rec2["proc"].wait()
    supervisor.close_child(rec2)
    assert rec2["cap"] == 4, "an empty counters map must not scale the cap"


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


def test_a_ticket_parked_at_a_human_gate_holds_no_file_claim():
    """TICKET-105: `conflict_holder()` only sees `inflight.values()`, and a
    ticket sitting at a `HUMAN_GATES` stage like `awaiting-merge` was never
    given a running child -- `start()` returns `(False, None)` for it before
    reaching the worktree/spawn code, so it is never added to `inflight`.

    A second ticket declaring the SAME file is therefore never held by
    `files_conflict()`. If that second ticket lands the identical change
    directly on base while the first still waits for human approval, the
    first ticket's own commit becomes a no-op patch. `git rebase` silently
    DROPS an empty commit by default, so `merge_cmd()`'s
    `git rebase {base} || git rebase --abort` step discards TICKET-001's
    branch commit before the `git merge --ff-only` step ever runs, and the
    merge reports success with none of TICKET-001's own history landed."""
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: merging"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "thing.py").write_text("the fix\n")
    _commit(wt, "'TICKET-001: the fix'")
    ticket_sha = subprocess.run(
        "git rev-parse HEAD", shell=True, cwd=wt,
        capture_output=True, text=True).stdout.strip()

    # TICKET-001 sits at `awaiting-merge`/`merging` waiting for a human.
    # Meanwhile an unrelated ticket lands the SAME change directly on base --
    # `files_conflict()` never held it, because TICKET-001 was never inflight.
    (d / "thing.py").write_text("the fix\n")
    sh("git add -A && git commit -qm 'other ticket: same fix, landed first'")

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec and rec["kind"] == "merge"
    rec["proc"].wait()
    supervisor.finish(d, rec)

    main_shas = sh("git log main --format=%H").stdout
    assert ticket_sha in main_shas, (
        "TICKET-001's own commit did not land on base -- the rebase step in "
        "merge_cmd() silently dropped it as an empty/no-op patch because an "
        "unrelated ticket landed the identical change while TICKET-001 sat "
        f"at a human gate. git log main --format=%H returned: {main_shas!r}"
    )
    shutil.rmtree(d, ignore_errors=True)


def test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate():
    """TICKET-105: `conflict_holder()` sees `inflight` only, so a ticket parked
    at a human gate (e.g. `awaiting-approval`) holds no claim on its
    `files_declared` while `start()` decides whether another ticket can merge.
    A second ticket declaring the same file must wait behind the parked one
    instead of landing its merge."""
    d = project()
    t1 = Ticket.find(d, "TICKET-001")
    t1.stage = "awaiting-approval"
    t1.save()
    (d / ".project/tickets/TICKET-002.md").write_text(
        FIXTURE.replace("id: TICKET-001", "id: TICKET-002")
               .replace("branch: ticket/001", "branch: ticket/002")
               .replace("stage: plan-validation", "stage: merging"))

    did, rec = supervisor.start(d, d / ".project/tickets/TICKET-002.md", harness("fake"), {})

    assert (did, rec) == (False, None), (
        "a merge must wait behind a ticket parked at a human gate whose "
        f"files_declared overlap, got (did, rec) = {(did, rec)!r}")
    waiting = Ticket.find(d, "TICKET-002").extra["waiting"]
    assert waiting["on"] == "TICKET-001" and waiting["file"] == "thing.py", (
        f"waiting must name the parked holder and the shared file, got {waiting!r}")


def test_a_merge_is_not_held_by_a_parked_ticket_that_shares_no_file():
    """The over-blocking guard: a ticket parked at a human gate whose
    `files_declared` overlap NOTHING must delay no one. If `parked_meta()`
    is ever widened past `files_declared` overlap, this must catch it."""
    d, sh = git_project()
    (d / ".project/tickets/TICKET-001.md").write_text(
        FIXTURE.replace("stage: plan-validation", "stage: awaiting-approval")
               .replace("files_declared: [thing.py]", "files_declared: [other.py]"))
    (d / ".project/tickets/TICKET-002.md").write_text(
        FIXTURE.replace("id: TICKET-001", "id: TICKET-002")
               .replace("branch: ticket/001", "branch: ticket/002")
               .replace("stage: plan-validation", "stage: merging"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-002", "branch": "ticket/002"}, {"base": "main"})
    (wt / "thing.py").write_text("the fix\n")
    _commit(wt, "'TICKET-002: the fix'")

    did, rec = supervisor.start(d, d / ".project/tickets/TICKET-002.md", harness("fake"), {})

    assert did and rec and rec["kind"] == "merge", (
        f"a parked ticket sharing no file must delay no merge, got (did, rec) = {(did, rec)!r}")
    rec["proc"].wait()
    supervisor.finish(d, rec)
    shutil.rmtree(d, ignore_errors=True)


def test_the_unwind_refuses_a_sha_that_is_not_on_the_branch():
    """`unwind_cmd()` resets a branch to a recorded tip -- but only if that tip
    is really on the branch. A stale or hand-edited sha must refuse rather than
    reset onto whatever it happens to name."""
    d, sh = git_project()
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "test_thing.py").write_text("")
    _commit(wt, "'triage: the failing test'")
    triage_sha = subprocess.run("git rev-parse HEAD", shell=True, cwd=wt,
                                capture_output=True, text=True).stdout.strip()
    (wt / "f.py").write_text("fixed\n")
    _commit(wt, "'implementing: the fix'")
    (wt / "scratch.py").write_text("untracked leftover\n")
    (d / "g.py").write_text("base moved\n")
    sh("git add -A && git commit -qm 'base moved'")
    main_sha = sh("git rev-parse HEAD").stdout.strip()

    head_before = subprocess.run("git rev-parse HEAD", shell=True, cwd=wt,
                                 capture_output=True, text=True).stdout.strip()
    bad = subprocess.run(supervisor.unwind_cmd(main_sha), shell=True, cwd=wt,
                         capture_output=True, text=True)
    assert bad.returncode != 0, "a sha not on the branch must not reset it"
    assert "is not an ancestor of HEAD" in bad.stdout + bad.stderr
    head_after = subprocess.run("git rev-parse HEAD", shell=True, cwd=wt,
                                capture_output=True, text=True).stdout.strip()
    assert head_after == head_before, "a refused unwind must not move HEAD"

    good = subprocess.run(supervisor.unwind_cmd(triage_sha), shell=True, cwd=wt,
                          capture_output=True, text=True)
    assert good.returncode == 0, good.stdout + good.stderr
    head_final = subprocess.run("git rev-parse HEAD", shell=True, cwd=wt,
                                capture_output=True, text=True).stdout.strip()
    assert head_final == triage_sha
    assert (wt / "test_thing.py").is_file(), "triage's test commit was discarded"
    assert (wt / "f.py").read_text() == "base\n", "the fix's edit to f.py survived"
    assert not (wt / "scratch.py").exists(), "an untracked leftover survived the unwind"
    shutil.rmtree(d, ignore_errors=True)


def test_the_cheap_routes_branch_tip_is_recorded_before_the_fix_is_written():
    """`cheap_route` is popped at `implementing` (DEC-026), so by the time
    `quick-review` fails the flag is gone. The branch tip has to be recorded
    here, the last moment the flag still says which commits are the route's
    own."""
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: implementing")
                    .replace("counters: {}", "counters: {cheap_route: 1}"))
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    expect_head = subprocess.run("git rev-parse HEAD", shell=True, cwd=wt,
                                 capture_output=True, text=True).stdout.strip()

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec
    rec["proc"].wait()

    assert Ticket.load(path).extra["cheap_route_head"] == expect_head

    path2 = d / ".project/tickets/TICKET-002.md"
    path2.write_text(FIXTURE.replace("TICKET-001", "TICKET-002")
                     .replace("ticket/001", "ticket/002")
                     .replace("stage: plan-validation", "stage: implementing"))
    did2, rec2 = supervisor.start(d, path2, harness("fake"), {})
    assert did2 and rec2
    rec2["proc"].wait()
    assert "cheap_route_head" not in Ticket.load(path2).extra, \
        "a non-cheap-route implementing spawn recorded a tip anyway"
    shutil.rmtree(d, ignore_errors=True)


def test_a_promoted_cheap_route_ticket_reaches_planning_with_its_fix_unwound():
    """A ticket promoted out of `quick-review` still carries the cheap route's
    commit. `unwinding` discards it before `planning` sees the branch, and
    triage's own test commit survives."""
    d, sh = git_project()
    wt = supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
    (wt / "test_thing.py").write_text("")
    _commit(wt, "'triage: the failing test'")
    triage_sha = subprocess.run("git rev-parse HEAD", shell=True, cwd=wt,
                                capture_output=True, text=True).stdout.strip()
    (wt / "f.py").write_text("fixed\n")
    _commit(wt, "'implementing: the fix'")

    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: quick-review"))
    t = Ticket.load(path)
    t.extra["cheap_route_head"] = triage_sha
    t.save()
    supervisor.advance(d, Ticket.load(path), "fail", "quick-review failed", agent=False)
    assert Ticket.load(path).stage == "unwinding"

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did and rec and rec["kind"] == "unwind"
    rec["proc"].wait()
    supervisor.finish(d, rec)

    t = Ticket.load(path)
    assert t.stage == "planning"
    log = sh(f"git -C {wt} log --oneline").stdout
    assert "triage: the failing test" in log
    assert "implementing: the fix" not in log
    assert (wt / "test_thing.py").is_file()
    assert (wt / "f.py").read_text() == "base\n"
    assert not t.lease_active()
    shutil.rmtree(d, ignore_errors=True)


def test_an_unwind_with_no_recorded_head_escalates_instead_of_guessing():
    """A malformed or missing `cheap_route_head` must never be guessed at --
    escalate before any child exists."""
    d, sh = git_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: unwinding"))
    supervisor.ensure_worktree(
        d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})

    did, rec = supervisor.start(d, path, harness("fake"), {})
    assert did is True and rec is None
    assert Ticket.load(path).stage == "escalated"
    shutil.rmtree(d, ignore_errors=True)


def test_the_tier_a_gate_runs_as_a_spawned_child():
    """The daemon must answer other tickets and drain other children's pipes
    while a project's `test_one` runs -- so the Tier A gate must not block the
    loop the way an inline `gate()` call did."""
    d, sh = git_project()
    (d / "test_thing.py").write_text("")
    sh("git add test_thing.py && git commit -qm 'the test file'")
    (d / ".project/pipeline.toml").write_text(
        'test_one = "sleep 5; echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "true"\n'
        'base = "main"\n')
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE)

    t0 = time.monotonic()
    did, rec = supervisor.start(d, path, harness("fake"), {})
    elapsed = time.monotonic() - t0

    assert did and rec
    assert rec["kind"] == "gate"
    assert elapsed < 2, f"start() blocked for {elapsed}s waiting on the gate"
    assert rec["proc"].poll() is None, "the gate child already finished"
    t = Ticket.load(path)
    assert t.stage == "plan-validation"
    assert t.lease_active()

    rec["proc"].kill()
    rec["proc"].wait()
    supervisor.close_child(rec)
    shutil.rmtree(d, ignore_errors=True)


def test_a_failing_gate_child_sends_the_ticket_back_to_planning():
    """A failed Tier A gate charges `plan_validation_attempts` and lands the
    ticket at `planning`, exactly like the inline gate used to -- and it must
    still write the one `stage_end` view 1 counts as a `plan-validation` run."""
    d, sh = git_project()
    (d / "test_thing.py").write_text("")
    sh("git add test_thing.py && git commit -qm 'the test file'")
    # `test_one` must exit non-zero without naming the node, or the run reads
    # as passing on both trees and now returns `load-flaky` (TICKET-109)
    # instead of `bad-plan`.
    (d / ".project/pipeline.toml").write_text(
        'test_one="false"\ntest_suite="true"\ntest_suite_without_new="true"\nbase="main"\n')
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE)
    s = Store(Path(tempfile.mkdtemp()) / "events.db")

    did, rec = supervisor.start(d, path, harness("fake"), {}, None, s.emitter(str(d)))
    assert did and rec and rec["kind"] == "gate"
    rec["proc"].wait()
    supervisor.finish(d, rec, s.emitter(str(d)))

    t = Ticket.load(path)
    assert t.stage == "planning"
    assert t.counters["plan_validation_attempts"] == 1
    assert not t.lease_active()
    thread = t.section("Thread")
    assert "Tier A gate: FAIL" in thread or "Tier A gate failed" in thread, thread
    events = s.since(0)
    assert [e["kind"] for e in events if e["kind"] == "gate"] == ["gate"]
    assert [e["kind"] for e in events if e["kind"] == "stage_end"] == ["stage_end"]
    assert not Path(rec["findings"]).exists()
    s.close()
    shutil.rmtree(d, ignore_errors=True)


def test_a_passing_gate_child_hands_the_ticket_to_the_plan_validation_agent():
    """A Tier A pass is a phase of `plan-validation`, not an ended attempt: no
    `stage_end`, and the next `start()` spawns the Tier B agent with
    `gate_ok` consumed."""
    d, sh = _gating_project()
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(FIXTURE)
    s = Store(Path(tempfile.mkdtemp()) / "events.db")

    did, rec = supervisor.start(d, path, harness("fake"), {}, None, s.emitter(str(d)))
    assert did and rec and rec["kind"] == "gate"
    rec["proc"].wait()
    supervisor.finish(d, rec, s.emitter(str(d)))

    t = Ticket.load(path)
    assert t.stage == "plan-validation"
    assert t.counters["gate_ok"] == 1
    assert not t.lease_active()
    assert [e["kind"] for e in s.since(0) if e["kind"] == "stage_end"] == []

    did, rec = supervisor.start(d, path, harness("fake"), {}, None, s.emitter(str(d)))
    assert did and rec and "kind" not in rec
    assert rec["stage"] == "plan-validation"
    assert "gate_ok" not in Ticket.load(path).counters

    rec["proc"].wait()
    supervisor.close_child(rec)
    s.close()
    shutil.rmtree(d, ignore_errors=True)


def test_structural_only_classifies_a_gate_finding():
    """An allowlist matched with `startswith`: a substantive finding whose
    fenced output quotes a structural finding's text verbatim must not read
    as structural."""
    from pipeline.core.gate import structural_only

    structural = "plan line is not a numbered step -- the plan reads as prose: 'x'"
    substantive = ("`t.py::x` exited 0 -- it must fail before implementation\n"
                   "```\nplan line is not a numbered step\n```")
    assert structural_only([structural]) is True
    assert structural_only([substantive]) is False
    assert structural_only([structural, substantive]) is False
    assert structural_only([]) is False
    assert structural_only(
        ["gate child exit 2 left no readable findings (JSONDecodeError: x)"]) is False


def test_an_absolute_count_finding_is_structural():
    """A criterion pinning an absolute count from `## Digest` charges
    `structural_gate_failures`, not `plan_validation_attempts`."""
    from pipeline.core.gate import structural_only

    finding = ("acceptance criterion pins an absolute count copied from "
               "`## Digest` (630): `tests/chz` suite: 630 passed -- state it "
               "as a relation to a measured baseline")
    assert structural_only([finding]) is True


def test_suite_ran_tells_a_red_suite_from_a_command_that_never_ran():
    from pipeline.core.gate import suite_ran
    ran = [(1, ""),
           (1, "1 failed, 84 passed in 3.21s"),
           (101, "test result: FAILED. 3 passed; 1 failed"),
           (3, "  3 failing"),
           (2, "Ran 7 tests in 0.4s"),
           (2, "--- FAIL: TestAdd (0.00s)")]
    never = [(2, "sh: -c: line 1: syntax error near unexpected token"),
             (127, "sh: line 1: pytest: command not found"),
             (4, "no tests ran in 0.00s"),
             (126, ""),
             # `1 error` matches the count regex; NO_TESTS_RE vetoes it
             (2, "collected 0 items / 1 error\nERROR tests/test_x.py"),
             (5, "no tests ran in 0.01s")]
    for code, out in ran:
        assert suite_ran(code, out), (code, out)
    for code, out in never:
        assert not suite_ran(code, out), (code, out)


def test_unmatchable_names_only_tokens_that_cannot_recur():
    """The detector fires on a temp path, a pid inside one, an object address
    and a trailing ellipsis; it stays silent on an exit status, a hex
    constant, a project path and an ordinary error (TICKET-076)."""
    from pipeline.core.gate import unmatchable

    assert unmatchable("registered /tmp/tmpn7w0imby") is not None
    assert unmatchable("names the unreadable subdir /tmp/chz_w8_39_2424171/sub") is not None
    assert unmatchable("<Cache object at 0x7f3a2b1c9d50>") is not None
    assert unmatchable('got: [CheckError { message: x, ...') is not None

    assert unmatchable("exit status 137") is None
    assert unmatchable("0xdeadbeef is wrong") is None
    assert unmatchable("no such file: .project/pipeline.toml") is None
    assert unmatchable("KeyError: 'evict'") is None


def test_an_unmatchable_expect_finding_is_structural():
    """The new finding must be classified structural, or a malformed
    `expect:` line charges `plan_validation_attempts` like a bad plan
    instead of `structural_gate_failures` (TICKET-076, DEC-065)."""
    from pipeline.core.gate import UNMATCHABLE_MARK, structural_only

    assert structural_only(
        [UNMATCHABLE_MARK + ": 'x' is a path under the system temp dir"]) is True
    assert structural_only(
        ["`t.py::x` fails, but its output does not mention the expected "
         "string 'y'"]) is False


def test_a_gate_verdict_picks_its_result_string():
    """Only `plan-validation` splits `fail` into `bad-plan`: `revalidating`
    always gets `fail`, so a stale plan charges `stale_regate` (DEC-029) and
    never escalates through an unknown `(revalidating, bad-plan)` pair."""
    assert supervisor.gate_result(True, [], "plan-validation") == "ok"
    assert supervisor.gate_result(
        False, ["`files_declared` is empty"], "plan-validation") == "fail"
    assert supervisor.gate_result(
        False, ["test file /x/test_thing.py does not exist"],
        "plan-validation") == "no-test-file"
    assert supervisor.gate_result(
        False, ["`files_declared` is empty"], "revalidating") == "fail"


def test_a_missing_test_file_escalates_instead_of_charging_planning():
    """A `test_file` naming no file is a triage typo, not a bad plan: it
    escalates through its own verdict and charges neither planning
    counter. `revalidating` keeps `fail` per DEC-065, so `stale_regate`
    still charges there."""
    from pipeline.core.gate import missing_test_file

    assert missing_test_file(["test file /x/vm does not exist"]) is True
    assert missing_test_file(["unusable frontmatter: x"]) is False
    assert missing_test_file([]) is False

    assert supervisor.gate_result(
        False, ["test file /x/vm does not exist"],
        "plan-validation") == "no-test-file"
    assert supervisor.gate_result(
        False, ["test file /x/vm does not exist"],
        "revalidating") == "fail"


def test_a_load_flaky_test_escalates_instead_of_charging_planning():
    """A `test_file` that exits 0 in the ticket's worktree AND on base
    reproduces the bug only under load: `CLAIMS` gives `test_file` to
    `triage` alone, so no re-plan can repoint it. It escalates through its
    own verdict and charges neither planning counter. `revalidating` keeps
    `fail` per DEC-029, so `stale_regate` still charges there. (TICKET-109)"""
    from pipeline.core.gate import LOAD_FLAKY_MARK, load_flaky

    assert load_flaky([LOAD_FLAKY_MARK + "`t.py::x` exited 0"]) is True
    assert load_flaky(
        ["`t.py::x` exited 0 -- it must fail before implementation"]) is False
    assert load_flaky([]) is False

    assert supervisor.gate_result(
        False, [LOAD_FLAKY_MARK + "`t.py::x` exited 0"],
        "plan-validation") == "load-flaky"
    assert supervisor.gate_result(
        False, [LOAD_FLAKY_MARK + "`t.py::x` exited 0"],
        "revalidating") == "fail"


def test_a_tier_b_rejection_charges_the_plan_not_the_structural_counter():
    """Tier B judges the plan's content and has no structural half, so its
    `fail` is a bad plan by definition: `_finish()` remaps it to `bad-plan`
    before it reaches `transition()`."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    snap = Ticket.load(path)

    T.result_file(d, "TICKET-001").write_text(
        "result: fail\nsummary: the plan skips the migration\n")
    log = d / ".project" / "logs" / "TICKET-001.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
           "path": path, "tid": "TICKET-001", "stage": "plan-validation",
           "session": "s1", "log": log, "wt": d, "meta": snap, "before": None}
    supervisor.finish(d, rec)

    t = Ticket.load(path)
    assert t.stage == "planning"
    assert t.counters["plan_validation_attempts"] == 1
    assert "structural_gate_failures" not in t.counters
    shutil.rmtree(d, ignore_errors=True)


def test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash():
    """A stage killed at its `--max-budget-usd` cap escalates on the FIRST
    kill, charged to its own counter, naming the cap it hit -- not a blind
    `no_result` retry into the same spend."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    snap = Ticket.load(path)

    log = d / ".project" / "logs" / "TICKET-001.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    def rec():
        return {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
                "path": path, "tid": "TICKET-001", "stage": "plan-validation",
                "session": "s1", "log": log, "wt": d, "meta": snap,
                "before": None, "terminal_reason": "budget_exhausted", "cap": 3}

    supervisor.finish(d, rec())
    t = Ticket.load(path)
    assert t.stage == "escalated"
    assert t.counters.get("budget_kills") == 1
    assert t.counters.get("no_result", 0) == 0
    msg = t.thread()[-1].text
    assert "budget" in msg.lower() and "$3" in msg
    shutil.rmtree(d, ignore_errors=True)


def test_a_crash_with_no_terminal_reason_still_retries_then_escalates():
    """A harness that dies with no `terminal_reason` at all is not a budget
    kill: it keeps the `no_result` retry, respawning once before it
    escalates."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    snap = Ticket.load(path)

    log = d / ".project" / "logs" / "TICKET-001.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    def rec():
        return {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
                "path": path, "tid": "TICKET-001", "stage": "plan-validation",
                "session": "s1", "log": log, "wt": d, "meta": snap,
                "before": None}

    supervisor.finish(d, rec())
    t = Ticket.load(path)
    assert t.counters["no_result"] == 1
    assert t.stage == "plan-validation"

    supervisor.finish(d, rec())
    t = Ticket.load(path)
    assert t.stage == "escalated"
    assert "wrote no .result sidecar 2 times" in t.thread()[-1].text
    shutil.rmtree(d, ignore_errors=True)


def test_the_stream_sink_records_the_terminal_reason_on_the_child():
    """`terminal_sink()` records `terminal_reason` on the rec and forwards
    every event to the inner sink -- it must never swallow one."""
    rec = {}
    seen = []
    sink = supervisor.terminal_sink(rec, seen.append)
    sink({"kind": "assistant"})
    sink({"kind": "result", "terminal_reason": None})
    sink({"kind": "result", "terminal_reason": "budget_exhausted"})
    assert rec["terminal_reason"] == "budget_exhausted"
    assert len(seen) == 3


def test_the_session_thread_entry_reports_cost_and_tokens():
    """TICKET-085: `pipeline/stream/events.py` normalises `total_cost_usd` and
    `usage` off the harness's `result` event, and `terminal_sink()` forwards
    every event to the inner sink -- but nothing carries either number onto
    `rec`, so the session entry `_finish()` appends to `## Thread` never
    mentions cost or tokens.
    """
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    snap = Ticket.load(path)

    log = d / ".project" / "logs" / "TICKET-001.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    (d / ".project/tickets/TICKET-001.result").write_text(
        "result: ok\nsummary: x\n")

    rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
           "path": path, "tid": "TICKET-001", "stage": "plan-validation",
           "session": "s1", "log": log, "wt": d, "meta": snap,
           "before": None}

    sink = supervisor.terminal_sink(
        rec, supervisor.event_sink(rec["tid"], rec["stage"], rec["session"],
                                    lambda *a, **k: None))
    sink({"kind": "result", "total_cost_usd": 6.089121,
          "usage": {"output_tokens": 80906, "cache_read_input_tokens": 4393384},
          "terminal_reason": None})

    supervisor.finish(d, rec)
    t = Ticket.load(path)
    entries = [e.text for e in t.thread() if "ran as session" in e.text]
    assert entries, f"no session entry found: {[e.text for e in t.thread()]}"
    msg = entries[-1]
    assert "6.09" in msg or "$6" in msg, (
        f"session thread entry has no trace of the run's cost:\n{msg}")
    assert "- cost: $6.09" in msg
    assert ("- tokens: 80,906 out · 0 in · 4,393,384 cache read · 0 cache write"
            in msg)
    shutil.rmtree(d, ignore_errors=True)


def test_the_session_entry_names_the_budget_cap_and_the_thinking_tokens():
    """TICKET-085: the cap and the thinking-token count are both optional
    parts of the line -- a cap of 0/None omits ` of a $N cap`, and 0 thinking
    tokens omits `(N thinking)`. This is the case where both are present."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    snap = Ticket.load(path)

    log = d / ".project" / "logs" / "TICKET-001.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    (d / ".project/tickets/TICKET-001.result").write_text(
        "result: ok\nsummary: x\n")

    rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
           "path": path, "tid": "TICKET-001", "stage": "plan-validation",
           "session": "s1", "log": log, "wt": d, "meta": snap,
           "before": None, "cap": 10}

    sink = supervisor.terminal_sink(
        rec, supervisor.event_sink(rec["tid"], rec["stage"], rec["session"],
                                    lambda *a, **k: None))
    sink({"kind": "result", "total_cost_usd": 6.089121,
          "usage": {"output_tokens": 80906, "input_tokens": 74,
                     "cache_read_input_tokens": 4393384,
                     "cache_creation_input_tokens": 186837,
                     "output_tokens_details": {"thinking_tokens": 31412}},
          "terminal_reason": None})

    supervisor.finish(d, rec)
    t = Ticket.load(path)
    entries = [e.text for e in t.thread() if "ran as session" in e.text]
    msg = entries[-1]
    assert "- cost: $6.09 of a $10 cap" in msg
    assert ("- tokens: 80,906 out (31,412 thinking) · 74 in · "
            "4,393,384 cache read · 186,837 cache write" in msg)
    shutil.rmtree(d, ignore_errors=True)


def test_the_session_entry_omits_cost_when_no_result_event_arrived():
    """TICKET-085: an interactive stage emits no `result` event (DEC-077),
    so its session entry must not gain a zero-dollar line -- that would read
    as a free run rather than an unmeasured one."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    snap = Ticket.load(path)

    log = d / ".project" / "logs" / "TICKET-001.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    (d / ".project/tickets/TICKET-001.result").write_text(
        "result: ok\nsummary: x\n")

    rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
           "path": path, "tid": "TICKET-001", "stage": "plan-validation",
           "session": "s1", "log": log, "wt": d, "meta": snap,
           "before": None, "cap": 10, "cost_usd": None, "usage": {}}

    supervisor.finish(d, rec)
    t = Ticket.load(path)
    entries = [e.text for e in t.thread() if "ran as session" in e.text]
    msg = entries[-1]
    assert "- replay:" in msg
    assert "- cost:" not in msg
    assert "- tokens:" not in msg
    shutil.rmtree(d, ignore_errors=True)


def test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child():
    """TICKET-086: `run()` now wraps its `tick()` call, so a transient
    `BlockingIOError` (fork returning EAGAIN) does not reach `finally:
    shut_down(project, inflight)` and SIGTERM every other ticket still
    running -- exactly the failure `serve()` already avoided per project.
    Expected: `tick()` runs again after the raise, with `TICKET-999` still
    inflight and un-SIGTERMed, and the run then drains and returns."""
    d = project()
    killed = {}

    def fake_lock(project):
        class L:
            def close(self):
                pass
        return L()

    def fake_shut_down(project, inflight):
        killed.update(inflight)

    other_rec = {"proc": None}
    calls = {"n": 0}
    seen = []

    def fake_tick(project, hcfg, inflight, max_parallel, poller, emit, stopping):
        calls["n"] += 1
        if calls["n"] == 1:
            inflight["TICKET-999"] = other_rec
            raise BlockingIOError(11, "Resource temporarily unavailable")
        seen.append(sorted(inflight))
        inflight.clear()
        return False

    from pipeline.daemon import registry as R

    orig_lock, orig_tick, orig_shut_down = R.lock, supervisor.tick, supervisor.shut_down
    R.lock = fake_lock
    supervisor.tick = fake_tick
    supervisor.shut_down = fake_shut_down
    try:
        supervisor.run(d, once=True, interval=1, harness_name="fake")
    finally:
        R.lock, supervisor.tick, supervisor.shut_down = (
            orig_lock, orig_tick, orig_shut_down)
        shutil.rmtree(d, ignore_errors=True)

    assert calls["n"] >= 2, f"expected tick() to run again after the raise, got {calls['n']} calls"
    assert seen[0] == ["TICKET-999"], f"expected TICKET-999 still inflight on tick 2, got {seen}"
    assert not killed, (
        "a transient BlockingIOError from one tick() must not kill every "
        f"other inflight ticket's child, but shut_down saw {list(killed)}")


def test_a_spawn_survives_a_transient_blockingioerror_from_fork():
    d = project()
    calls = {"n": 0}
    real_popen = subprocess.Popen

    class Shim:
        PIPE = subprocess.PIPE
        STDOUT = subprocess.STDOUT

        def Popen(self, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise BlockingIOError(11, "Resource temporarily unavailable")
            return real_popen(*a, **kw)

    orig = supervisor.subprocess
    supervisor.subprocess = Shim()
    try:
        rec = supervisor.spawn(d, d, "TICKET-001", "review", harness("fake"))
        rec["proc"].wait()
        supervisor.close_child(rec)
    finally:
        supervisor.subprocess = orig
        shutil.rmtree(d, ignore_errors=True)
    assert calls["n"] == 2


def test_spawn_command_survives_a_transient_blockingioerror_from_fork():
    d = project()
    calls = {"n": 0}
    real_popen = subprocess.Popen

    class Shim:
        PIPE = subprocess.PIPE
        STDOUT = subprocess.STDOUT

        def Popen(self, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise BlockingIOError(11, "Resource temporarily unavailable")
            return real_popen(*a, **kw)

    orig = supervisor.subprocess
    supervisor.subprocess = Shim()
    try:
        rec = supervisor.spawn_command(d, d, "TICKET-001", "verifying", "true")
        rec["proc"].wait()
        rec["fh"].close()
    finally:
        supervisor.subprocess = orig
        shutil.rmtree(d, ignore_errors=True)
    assert calls["n"] == 2


def test_a_spawn_that_keeps_failing_escalates_one_ticket_and_keeps_the_loop():
    d, _ = git_project()
    path = d / ".project" / "tickets" / "TICKET-001.md"
    path.write_text(FIXTURE.replace("stage: plan-validation", "stage: implementing"))

    def always_fails(*a, **kw):
        raise BlockingIOError(11, "Resource temporarily unavailable")

    orig = supervisor.spawn
    supervisor.spawn = always_fails
    try:
        result = supervisor.start(d, path, harness("fake"), {})
        assert result == (True, None)
        assert Ticket.load(path).stage == "escalated"
    finally:
        supervisor.spawn = orig
        shutil.rmtree(d, ignore_errors=True)


def test_environment_only_classifies_a_suite_red_on_base_and_nothing_else():
    from pipeline.core.gate import environment_only, ENVIRONMENT_MARK
    from pipeline.daemon.supervisor import gate_result
    env = [ENVIRONMENT_MARK + "suite excluding `t` is RED -- pre-existing "
           "breakage, and it is RED on base `main` too"]
    assert environment_only(env) is True
    assert environment_only([]) is False
    assert environment_only(env + ["`files_declared` is empty"]) is False
    assert environment_only(
        ["the plan quotes " + ENVIRONMENT_MARK + " in its own output"]) is False

    assert gate_result(False, env, "plan-validation") == "environment"
    assert gate_result(False, env, "revalidating") == "fail"
    assert gate_result(
        False, env + ["`files_declared` is empty"], "plan-validation") == "bad-plan"
    assert gate_result(True, [], "plan-validation") == "ok"


def test_a_ticket_cannot_declare_that_another_must_land_first():
    """There is no way to file a ticket that waits for another ticket to
    reach `done` before the dispatcher starts it -- `start()` has no field
    it reads for this, unlike `files_declared`, which `conflict_holder()`
    checks against every in-flight ticket."""
    d, _ = git_project()
    blocker = FIXTURE.replace("stage: plan-validation", "stage: implementing")
    (d / ".project/tickets/TICKET-001.md").write_text(blocker)
    dependent = FIXTURE.replace("id: TICKET-001", "id: TICKET-002") \
        .replace("branch: ticket/001", "branch: ticket/002") \
        .replace("stage: plan-validation", "stage: new") \
        .replace("---\n\n## Summary", "depends_on: TICKET-001\n---\n\n## Summary")
    path = d / ".project/tickets/TICKET-002.md"
    path.write_text(dependent)

    did, _ = supervisor.start(d, path, harness("fake"), {})

    assert did is False, (
        "TICKET-002 declared depends_on: TICKET-001, which is still at "
        "`implementing`, but start() advanced it anyway -- nothing in "
        "start() reads a dependency field")
    shutil.rmtree(d, ignore_errors=True)


def test_a_dependency_that_cannot_land_escalates_rather_than_waiting_forever():
    d, _ = git_project()
    dependent = FIXTURE.replace("stage: plan-validation", "stage: new") \
        .replace("---\n\n## Summary", "depends_on: [TICKET-404]\n---\n\n## Summary")
    path = d / ".project/tickets/TICKET-001.md"
    path.write_text(dependent)

    did, _ = supervisor.start(d, path, harness("fake"), {})

    assert did is True
    assert Ticket.load(path).stage == "escalated"
    shutil.rmtree(d, ignore_errors=True)


def test_ls_names_the_ticket_a_dependency_is_waiting_on():
    d, _ = git_project()
    blocker = FIXTURE.replace("stage: plan-validation", "stage: implementing")
    (d / ".project/tickets/TICKET-001.md").write_text(blocker)
    dependent = FIXTURE.replace("id: TICKET-001", "id: TICKET-002") \
        .replace("branch: ticket/001", "branch: ticket/002") \
        .replace("stage: plan-validation", "stage: new") \
        .replace("---\n\n## Summary", "depends_on: TICKET-001\n---\n\n## Summary")
    path = d / ".project/tickets/TICKET-002.md"
    path.write_text(dependent)

    supervisor.start(d, path, harness("fake"), {})

    row = [r for r in ticket_rows(d) if r["id"] == "TICKET-002"][0]
    assert waiting_text(row["waiting"]).startswith(
        "waiting on TICKET-001 (depends_on, at implementing)")
    shutil.rmtree(d, ignore_errors=True)
