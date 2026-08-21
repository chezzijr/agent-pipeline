"""The state machine. Pure and total: no I/O, no mutation of its inputs, and
an unknown `(stage, result)` escalates rather than guessing."""

MAX_ATTEMPTS = 2  # default bound: unknown classes, and the dispatcher's own counters
# Per-class loop budgets, owned by the dispatcher alone -- no stage prompt ever
# learns what its budget is. Missing class or key falls back to MAX_ATTEMPTS.
BOUNDS = {
    "bugfix":   {"review_loops": 2, "plan_validation_attempts": 2, "blocked_count": 2},
    "feature":  {"review_loops": 2, "plan_validation_attempts": 2, "blocked_count": 2},
    "refactor": {"review_loops": 3, "plan_validation_attempts": 3, "blocked_count": 2},
}
TERMINAL = {"done", "rejected", "escalated"}
HUMAN_GATES = {"awaiting-approval", "needs-input"}
KNOWN_STAGES = TERMINAL | HUMAN_GATES | {
    "new", "triage", "planning", "plan-validation", "revalidating",
    "implementing", "review", "quick-review", "holistic-review", "verifying", "merging"}
# only these leave a worktree behind for a human to look at
CLEANUP_STAGES = {"done", "rejected"}
# stages the dispatcher runs itself, with no agent and so no prompt file. A
# test subtracts this set rather than hard-coding the exceptions.
DISPATCHER_STAGES = {"verifying", "merging", "revalidating"}


def transition(stage: str, result: str, counters: dict, klass: str = "bugfix"):
    """(next_stage, new_counters). Pure: never mutates `counters`.

    `result` is what the agent claimed about its own stage only. Every
    escalation and retry decision is made here, never by an agent.
    """
    c = dict(counters)

    def charge(key: str, target: str) -> tuple[str, dict]:
        c[key] = c.get(key, 0) + 1
        bound = BOUNDS.get(klass, {}).get(key, MAX_ATTEMPTS)
        return ("escalated" if c[key] >= bound else target), c

    match (stage, result):
        case ("new", _):
            return "triage", c
        case ("triage", "ok"):
            return "planning", c
        case ("triage", "rejected"):
            return "rejected", c
        case ("triage", "chore"):
            # the cheap route. TICKET-025 changed one line and paid $6.28 for
            # planning, plan-validation, an approval gate and a full review.
            # The flag lives in `counters` -- dispatcher-owned and restored
            # from the pre-spawn snapshot -- so no agent can put a ticket on
            # this route, and `class` keeps meaning what it meant: loop
            # budgets, and whether a holistic review runs.
            c["cheap_route"] = 1
            return "implementing", c
        case ("planning", "ok"):
            return "plan-validation", c
        case ("planning", "needs-input"):
            # planning is the stage that genuinely needs the human; parking the
            # ticket is better than guessing an answer into the plan
            return "needs-input", c
        case ("plan-validation", "ok"):
            return "awaiting-approval", c
        case ("plan-validation", "fail"):
            return charge("plan_validation_attempts", "planning")
        case ("revalidating", "ok"):
            return "implementing", c
        case ("revalidating", "fail"):
            # the plan went stale while it waited for a human -- base moved
            # under it. That is not a bad plan, so it never charges
            # `plan_validation_attempts`: doing so would escalate a good plan
            # for the crime of waiting and corrupt the escalation rate. Its own
            # counter is left out of BOUNDS deliberately -- staleness is base
            # churn, not a property of the ticket's class, so it takes the
            # dispatcher's default bound like every other counter the
            # dispatcher raises itself.
            # Target is `planning`, not `plan-validation`: a post-rebase gate
            # failure means base moved -- new files, new overlap, a suite gone
            # red underneath. Re-validating the same stale plan reruns the
            # identical gate, fails identically, and charges
            # plan_validation_attempts a tick later -- the exact cost this row
            # exists to avoid. Re-planning is what can actually fix it.
            return charge("stale_regate", "planning")
        case ("implementing", "ok"):
            # CONSUMED here, not cleared later. `implementing` is the cheap
            # route's only exit, so a ticket bounced back by a red suite takes
            # the full `review` on its second pass. One-way by construction:
            # nothing routes back onto the cheap path.
            if c.pop("cheap_route", None):
                return "quick-review", c
            return "review", c
        case ("implementing", "blocked"):
            if c.pop("cheap_route", None):
                # there is no plan to re-gate, so the normal target would fail
                # its own Tier A gate on the missing sections and burn one of
                # the two plan attempts before landing here anyway
                return "planning", c
            return charge("blocked_count", "plan-validation")
        case ("quick-review", "ok"):
            return "verifying", c
        case ("quick-review", "fail"):
            # promotion, not a retry, so it charges no counter: the cheap check
            # found something outside its two questions, and the ticket takes
            # the full path from `planning`. It cannot come back -- the flag
            # was consumed at `implementing`.
            return "planning", c
        case ("review", "ok"):
            # a one-line bugfix's incremental review already saw the whole diff
            return ("verifying" if klass == "bugfix" else "holistic-review"), c
        case ("review", "fail"):
            return charge("review_loops", "implementing")
        case ("holistic-review", "ok"):
            return "verifying", c
        case ("holistic-review", "fail"):
            return charge("review_loops", "implementing")
        case ("verifying", "ok"):
            return "merging", c
        case ("verifying", "fail"):
            return charge("review_loops", "implementing")
        case ("merging", "ok"):
            return "done", c
        case ("merging", "fail"):
            # a conflict is never retried and never auto-resolved: the
            # conflicted worktree is what the human is being called for
            return "escalated", c

    # unknown (stage, result) is a bug or a lying agent -- never guess
    return "escalated", c


# Frontmatter the dispatcher owns outright. An agent that changes any of these
# has broken the contract, and the ticket is escalated rather than trusted.
CONTROL_FIELDS = {"id", "stage", "class", "branch", "counters", "lease",
                  "approved_by", "approved_at"}

# Which stage is allowed to set which frontmatter field. Without this any
# stage could rewrite `files_declared` -- a reviewer shrinking the set would
# silently unblock a ticket that overlaps one already in flight.
CLAIMS = {"test_file": ("triage",), "files_declared": ("planning", "implementing")}


def apply_claims(meta: dict, stage: str, res: dict) -> None:
    for field, owners in CLAIMS.items():
        if not res.get(field) or stage not in owners:
            continue
        if field == "files_declared" and stage == "implementing":
            # implementation may discover more files, never fewer
            meta[field] = sorted(set(meta.get(field) or []) | set(res[field]))
        else:
            meta[field] = res[field]


def files_conflict(meta: dict, inflight_meta: list[dict]) -> bool:
    """Two tickets touching the same file are ordered, not run together --
    otherwise their branches merge into a conflict nobody asked for."""
    mine = set(meta.get("files_declared") or [])
    return any(mine & set(o.get("files_declared") or []) for o in inflight_meta)
