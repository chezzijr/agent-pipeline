---
id: TICKET-065
stage: new
class: bugfix
branch: ticket/065
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

structural gate failures charge a plan-validation attempt

`transition()` charges `plan_validation_attempts` for every Tier A gate
failure (`pipeline/core/machine.py:119`), including failures where the gate
never read the plan's content at all. Two prose lines above step 1 fail
`PLAN_STEP_RULE`, the gate stops, and the ticket goes back to `planning` one
attempt poorer -- with no judgement of the plan it was carrying. A ticket can
spend its whole budget and escalate without a single scored plan.

    ## Plan
    DEC-003 sets the commit structure: tests commit first.
    1. edit pipeline/core/gate.py

    # gate: "plan line is not a numbered step -- the plan reads as prose"
    # counters: plan_validation_attempts 0 -> 1

The precedent is already in the same file, one row down
(`pipeline/core/machine.py:122`):

    case ("revalidating", "fail"):
        # the plan went stale ... That is not a bad plan, so it never charges
        # `plan_validation_attempts`
        return charge("stale_regate", "planning")

A parse failure is the same argument: the plan may be entirely sound, and the
budget exists to bound *bad plans*, not bad formatting.

Expected: a gate failure whose findings are only structural -- a missing
section, an unparsed plan step, an uncited declared file -- charges its own
counter and leaves `plan_validation_attempts` alone. A gate failure that
includes a substantive finding (the test passes, the suite is red, base is
already fixed) charges `plan_validation_attempts` exactly as it does today. A
suggestion, not a decision: `stale_regate` shows the shape, including staying
out of `BOUNDS` so it takes the dispatcher's default bound.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
