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
        ("plan-validation", "fail", "structural_gate_failures"),
        ("plan-validation", "bad-plan", "plan_validation_attempts"),
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


def test_conflict_holder_names_the_first_holder_and_its_file():
    mine = {"files_declared": ["a.py", "shared.py"]}
    inflight = [{"id": "TICKET-002", "files_declared": ["b.py"]},
                {"id": "TICKET-003", "files_declared": ["shared.py", "a.py"]}]
    assert M.conflict_holder(mine, inflight) == ("TICKET-003", "a.py")
    assert M.conflict_holder(mine, []) is None
    assert M.conflict_holder(mine, [{"id": "TICKET-004", "files_declared": ["z.py"]}]) is None

    assert M.files_conflict(mine, [{"files_declared": ["shared.py"]}])
    assert not M.files_conflict(mine, [{"files_declared": ["b.py"]}])
    assert not M.files_conflict(mine, []), "nothing in flight cannot conflict"


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


def test_a_non_reproducing_regate_failure_still_exhausts_the_budget():
    """TICKET-082: `stale_regate` never resets on an intervening `ok`, so two
    flaky, non-reproducing regate failures separated by a passing regate
    still escalate a good ticket -- the same cost as two genuinely stale
    plans. A confirmed-flaky failure (proven non-reproducing by the `ok` that
    follows it) must not count toward the bound."""
    nxt, c = t("revalidating", "fail")
    assert c["stale_regate"] == 1
    nxt2, c2 = t("revalidating", "ok", c)
    assert nxt2 == "implementing"
    assert c2["stale_regate"] == 1, "the failure was confirmed flaky by the ok that followed it"
    nxt3, c3 = t("revalidating", "fail", c2)
    assert nxt3 != "escalated", (
        "two non-reproducing regate failures, separated by a passing regate, "
        f"exhausted the budget: got {nxt3!r}"
    )


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
    assert t("quick-review", "fail")[0] == "unwinding", \
        "the promoted ticket reaches planning with the cheap route's fix still committed"
    assert "quick-review" in M.KNOWN_STAGES
    nxt, c = t("triage", "chore")
    assert c["cheap_route"] == 1, "nothing carries the route as far as `implementing`"
    assert t("implementing", "ok", c) == ("quick-review", {}), \
        "the cheap route pays for the full review, or leaks its flag past the stage that consumes it"
    assert t("implementing", "ok", {})[0] == "review", "the full route changed"
    assert t("implementing", "blocked", {"cheap_route": 1})[0] == "planning", \
        "a blocked chore re-gates a plan that does not exist"
    assert t("quick-review", "fail", {"cheap_route": 1})[0] == "unwinding"
    assert "cheap_route" not in M.BOUNDS.get("bugfix", {}), \
        "a route flag is not a bounded loop counter"
    assert t("unwinding", "ok")[0] == "planning"
    assert t("unwinding", "fail")[0] == "escalated"
    assert "unwinding" in M.KNOWN_STAGES
    assert "unwinding" in M.DISPATCHER_STAGES


def test_plan_validation_budget_ignores_the_plans_size():
    """TICKET-047: a `bugfix`'s plan-validation budget is fixed at 2 attempts
    by `BOUNDS[class]` alone. `transition()` takes no plan-size argument, so a
    one-step, one-file plan and a 24-step, 10-file plan (TICKET-041's actual
    shape) escalate at the identical attempt count. A budget that should scale
    with the size of the work does not take the size as input at all."""
    tiny = {"plan_validation_attempts": 0, "plan_steps": 1, "plan_files": 1}
    huge = {"plan_validation_attempts": 0, "plan_steps": 24, "plan_files": 10}
    for _ in range(2):
        tiny_next, tiny = M.transition("plan-validation", "bad-plan", tiny, "bugfix")
        huge_next, huge = M.transition("plan-validation", "bad-plan", huge, "bugfix")
    assert tiny_next == "escalated", "a 1-step/1-file plan exhausted its budget as expected"
    assert huge_next != "escalated", \
        "a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a " \
        "1-step/1-file plan, but it escalated at the same attempt count: " \
        f"{huge['plan_validation_attempts']} == {tiny['plan_validation_attempts']}"
    for _ in range(3):
        huge_next, huge = M.transition("plan-validation", "bad-plan", huge, "bugfix")
    assert huge_next == "escalated"
    assert huge["plan_validation_attempts"] == 5


def test_cap_for_scales_with_plan_size_and_stops_at_the_ceiling():
    """`cap_for()` mirrors `bound_for()`, but for a stage's dollar cap
    instead of an attempt budget (DEC-047's model, TICKET-078)."""
    assert M.cap_for(4, {}) == 4
    assert M.cap_for(4, {"plan_files": 8}) == 6
    assert M.cap_for(4, {"plan_files": 15, "plan_steps": 40}) == 8
    assert M.cap_for(4, {"plan_files": 4000}) == 8, "the ceiling is the point"
    assert M.cap_for(4, {"plan_files": "many"}) == 4, \
        "a hostile counter reads as 0"
    assert M.cap_for(0, {"plan_files": 15}) == 0, \
        "a harness with no cap flag keeps its 0"


def test_a_structural_gate_failure_charges_its_own_counter():
    """A purely structural Tier A failure charges `structural_gate_failures`,
    never `plan_validation_attempts`: the budget for bad plans stays untouched
    by a typo the gate stopped on before reading the plan."""
    nxt, c = t("plan-validation", "fail")
    assert nxt == "planning"
    assert c["structural_gate_failures"] == 1
    assert "plan_validation_attempts" not in c
    nxt, c = t("plan-validation", "fail", c)
    assert nxt == "escalated"

    nxt, c = t("plan-validation", "bad-plan")
    assert nxt == "planning"
    assert c["plan_validation_attempts"] == 1
    assert "structural_gate_failures" not in c

    assert "structural_gate_failures" not in M.SIZE_SCALED
    assert all("structural_gate_failures" not in bounds
               for bounds in M.BOUNDS.values())


def test_the_size_scaled_bound_has_a_ceiling_and_spares_the_dispatchers_counters():
    assert M.bound_for("refactor", "plan_validation_attempts",
                        {"plan_steps": 400, "plan_files": 900}) == M.BOUND_CEILING
    assert M.bound_for("bugfix", "lease_expiries", {"plan_steps": 400}) == M.MAX_ATTEMPTS
    assert M.bound_for("bugfix", "no_result", {"plan_steps": 400}) == M.MAX_ATTEMPTS
    assert M.bound_for("bugfix", "review_loops", {"plan_steps": 400}) == 2
    assert M.bound_for("bugfix", "plan_validation_attempts", {"plan_steps": "24"}) == 2
