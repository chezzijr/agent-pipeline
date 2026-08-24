"""The transition table's bounds, the claims table, and overlap ordering.
Pure functions: nothing here touches the disk."""
from pipeline.core import config as C
from pipeline.core import machine as M


def t(stage, result, counters=None, klass="bugfix"):
    return M.transition(stage, result, counters or {}, klass)


def test_holistic_review_runs_only_on_a_diff_that_bounced():
    """It reviews an ACCUMULATED diff. A review that passed first time
    accumulated nothing, so there is nothing for it to find -- 6 runs, 6 `ok`,
    0 findings before this row learned that. The bounce, not the class, is
    what makes the pass worth its cost."""
    for klass in ("feature", "refactor"):
        assert t("review", "ok", {"review_loops": 0}, klass)[0] == "verifying", klass
        assert t("review", "ok", {"review_loops": 1}, klass)[0] == "holistic-review", klass
    # bugfix skips it either way -- its incremental review saw the whole diff
    assert t("review", "ok", {"review_loops": 1}, "bugfix")[0] == "verifying"


def test_happy_path():
    assert t("new", "-")[0] == "triage"
    assert t("triage", "ok")[0] == "planning"
    assert t("planning", "ok")[0] == "plan-validation"
    assert t("plan-validation", "ok")[0] == "awaiting-approval"
    assert t("implementing", "ok")[0] == "review"
    assert t("review", "ok", klass="bugfix")[0] == "verifying", "bugfix skips holistic"
    assert t("review", "ok", {"review_loops": 1}, "refactor")[0] == "holistic-review"
    assert t("holistic-review", "ok")[0] == "verifying"
    assert t("verifying", "clean")[0] == "merging", "`done` must mean landed"
    assert t("verifying", "ok")[0] == "awaiting-merge", "plain `ok` parks for a human"
    assert t("merging", "ok")[0] == "done"
    assert t("merging", "fail")[0] == "escalated", "a conflict is never retried"
    assert t("triage", "rejected")[0] == "rejected"


def test_bounds_escalate_on_the_second_failure():
    for stage, result, key in [
        ("plan-validation", "fail", "plan_validation_attempts"),
        ("review", "fail", "review_loops"),
        ("holistic-review", "fail", "review_loops"),
        ("verifying", "fail", "review_loops"),
        ("implementing", "blocked", "blocked_count"),
    ]:
        nxt, c = t(stage, result)
        assert nxt != "escalated", f"{stage}: first {result} must retry, got {nxt}"
        assert c[key] == 1, f"{stage}: counter not charged"
        nxt, c = t(stage, result, c)
        assert nxt == "escalated", f"{stage}: second {result} must escalate, got {nxt}"
        assert c[key] == 2


def test_a_fenced_file_is_gated_before_merge():
    """CLAUDE.md fences nine things off from unattended merge:
    `pipeline/hooks/dangerous-commands.py`, `pipeline/harnesses/claude-code.toml`,
    `transition()`, `validate_meta()`, `CONTROL_FIELDS`, `FENCED`,
    `strip_settings_sources()`, `.project/pipeline.toml` and `.project/stages/`.
    The dispatcher holds no such list, and no human gate
    stands between `implementing` and `done` -- a diff touching a fenced file
    lands with the plan gate as its only human."""
    assert getattr(M, "FENCED", None), "no fenced-file list in the dispatcher"

    stage, c, path = "implementing", {}, []
    while stage not in M.TERMINAL and len(path) < 10:
        stage, c = M.transition(stage, "ok", c, "feature")
        path.append(stage)
    assert set(path) & M.HUMAN_GATES, f"no human gate between implementing and done: {path}"


def test_bounds_come_from_the_ticket_class():
    """A refactor gets a third review loop; a bugfix does not."""
    assert t("review", "fail", {"review_loops": 1}, "refactor")[0] == "implementing"
    assert t("review", "fail", {"review_loops": 1}, "bugfix")[0] == "escalated"
    assert t("review", "fail", {"review_loops": 2}, "refactor")[0] == "escalated"
    # an unknown class falls back to MAX_ATTEMPTS
    assert t("review", "fail", {"review_loops": 1}, "spelunking")[0] == "escalated"
    c = {"review_loops": 1}
    t("review", "fail", c, "refactor")
    assert c == {"review_loops": 1}, "transition mutated its input"


def test_review_loops_are_a_shared_budget():
    """A review fail then a holistic fail must escalate -- not reset per stage."""
    _, c = t("review", "fail")
    assert t("holistic-review", "fail", c)[0] == "escalated"


def test_transition_is_pure():
    c = {"review_loops": 0}
    t("review", "fail", c)
    assert c == {"review_loops": 0}, "transition mutated its input"


def test_unknown_result_escalates_rather_than_guesses():
    assert t("review", "lgtm!")[0] == "escalated"
    assert t("implementing", "")[0] == "escalated"


def test_no_agent_can_reach_a_human_gate_or_land_a_ticket():
    """The dispatcher's own stages are not in agent_stages() -- they are
    script-run -- so include them explicitly, otherwise this asserts nothing
    about the stage that guards `done`."""
    stages = C.agent_stages() + sorted(M.DISPATCHER_STAGES)
    for s in M.DISPATCHER_STAGES:
        assert s not in C.agent_stages(), f"{s} must have no agent prompt"
    results = ["ok", "fail", "blocked", "rejected", "junk"]

    for stage in C.agent_stages():          # merging is the dispatcher's own
        for r in results:
            assert t(stage, r)[0] != "done", \
                f"agent stage `{stage}` reached `done` on result {r!r}"

    for stage in stages:
        for r in results:
            assert t(stage, r)[0] != "awaiting-approval" or stage == "plan-validation", \
                f"`{stage}` reached the human approval gate on {r!r}"

    # only these stages may terminate a ticket, and only on these results
    assert t("triage", "rejected")[0] == "rejected"
    assert t("merging", "ok")[0] == "done"


def test_planning_can_park_for_a_human_and_come_back():
    assert t("planning", "needs-input")[0] == "needs-input"
    assert "needs-input" in M.HUMAN_GATES, "the dispatcher would spawn an agent on it"
    assert t("planning", "needs-input")[1] == {}, "asking a question is not a failure"


def test_only_the_owning_stage_can_set_a_frontmatter_field():
    meta = {"files_declared": ["a.py"], "test_file": "t.py::x"}
    M.apply_claims(meta, "review", {"files_declared": ["z.py"], "test_file": "other"})
    assert meta == {"files_declared": ["a.py"], "test_file": "t.py::x"}, \
        "a review stage rewrote fields it does not own"

    M.apply_claims(meta, "implementing", {"files_declared": ["b.py"]})
    assert meta["files_declared"] == ["a.py", "b.py"], "implementation may only add files"

    M.apply_claims(meta, "planning", {"files_declared": ["c.py"]})
    assert meta["files_declared"] == ["c.py"], "planning owns the declared set"


def test_overlapping_tickets_do_not_run_together():
    mine = {"files_declared": ["shared.py", "a.py"]}
    assert M.files_conflict(mine, [{"files_declared": ["shared.py"]}])
    assert not M.files_conflict(mine, [{"files_declared": ["b.py"]}])
    assert not M.files_conflict(mine, []), "nothing in flight cannot conflict"
    assert not M.files_conflict({"files_declared": []}, [{"files_declared": ["a.py"]}])


def test_control_fields_are_the_dispatchers_alone():
    assert {"stage", "counters", "branch", "id", "lease"} <= M.CONTROL_FIELDS
    for field in ("test_file", "files_declared"):
        assert field not in M.CONTROL_FIELDS, f"{field} is claimed via the sidecar"


def test_escalated_tickets_keep_their_worktree():
    assert "escalated" in M.TERMINAL
    assert "escalated" not in M.CLEANUP_STAGES, \
        "removing it destroys the uncommitted evidence a human was called for"
    assert M.CLEANUP_STAGES == {"done", "rejected"}


def test_an_approved_plan_is_re_gated_before_it_is_implemented():
    """A bounce off the re-gate is staleness, not a bad plan: charging
    `plan_validation_attempts` would escalate a good plan for waiting, and
    corrupt the escalation rate the whole system is measured by."""
    assert t("revalidating", "ok")[0] == "implementing"
    nxt, c = t("revalidating", "fail")
    assert nxt == "planning", f"a stale plan must replan, got {nxt}"
    assert c["stale_regate"] == 1
    assert "plan_validation_attempts" not in c, "waiting for a human was charged to the plan"
    assert t("revalidating", "fail", c)[0] == "escalated", "an unbounded stale loop"
    assert "revalidating" in M.DISPATCHER_STAGES and "revalidating" in M.KNOWN_STAGES


def test_a_rebase_conflict_returns_to_triage_and_is_bounded():
    """A conflicting rebase discards the branch's commits, so only `triage`
    can rebuild it. `planning` would replan without removing the conflicting
    commit and conflict again identically."""
    nxt, c = t("revalidating", "conflict")
    assert nxt == "triage"
    assert c["rebase_conflicts"] == 1
    assert "stale_regate" not in c
    assert t("revalidating", "conflict", c)[0] == "escalated", "an unbounded conflict loop"


def test_a_small_fix_takes_the_cheap_route():
    """TICKET-025 changed one line and paid for planning, plan-validation and a
    full review. A triage that reports the fix is small must route
    `triage -> implementing -> quick-review -> verifying`, and `quick-review`
    must be able to promote the ticket back onto the slow path."""
    assert t("triage", "chore")[0] == "implementing", \
        "a small fix still pays for planning, plan-validation and the approval gate"
    assert t("quick-review", "ok")[0] == "verifying"
    assert t("quick-review", "fail")[0] == "planning", \
        "a cheap path that cannot promote itself lands a vacuous test unattended"
    assert "quick-review" in M.KNOWN_STAGES
    nxt, c = t("triage", "chore")
    assert c["cheap_route"] == 1, "nothing carries the route as far as `implementing`"
    assert t("implementing", "ok", c) == ("quick-review", {}), \
        "the cheap route pays for the full review, or leaks its flag past the stage that consumes it"
    assert t("implementing", "ok", {})[0] == "review", "the full route changed"
    assert t("implementing", "blocked", {"cheap_route": 1})[0] == "planning", \
        "a blocked chore re-gates a plan that does not exist"
    assert t("quick-review", "fail", {"cheap_route": 1})[0] == "planning"
    assert "cheap_route" not in M.BOUNDS.get("bugfix", {}), \
        "a route flag is not a bounded loop counter"
