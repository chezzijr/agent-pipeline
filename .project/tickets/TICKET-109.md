---
id: TICKET-109
stage: new
class: bugfix
branch: ticket/109
test_file: null
files_declared: []
depends_on: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a `test_file` that exits 0 in the worktree AND on base charges `planning` for a field only `triage` may write

A load-flaky test -- one that reproduces the bug under load and passes on an
idle box -- makes Tier A permanently unsatisfiable, and the ticket burns
`plan_validation_attempts` until it escalates. On main at 10b44e3 the run
goes: exit 0 in the worktree is parked as `passing`
(`pipeline/core/gate.py:548`), the base run also exits 0 so the test never
enters `on_base` (`pipeline/core/gate.py:325`), and `gate()` reports

    `{test}` exited 0 -- it must fail before implementation. Either it
    PASSES, or `test_one` matched no test at all; ...

at `pipeline/core/gate.py:584`. That opener is in none of the three
`startswith` allowlists -- not `STRUCTURAL_MARKS`, not `MISSING_TEST_MARK`,
not `ENVIRONMENT_MARKS` -- so `gate_result()` returns `bad-plan` and
`pipeline/core/machine.py:172` runs:

    case ("plan-validation", "bad-plan"):
        return charge("plan_validation_attempts", "planning")

`planning` is then asked to fix a plan that is not wrong. The one thing that
would fix it is out of reach: `pipeline/core/machine.py:297` reads

    CLAIMS = {"test_file": ("triage",), "files_declared": ("planning", "implementing")}

so a `planning` sidecar that repoints `test_file` is rejected and the ticket
escalates as tampering instead. Every re-plan reruns the identical gate and
fails identically. Seen on four planning runs across two tickets in a
the `chezzilang` project. Its
`.project/tickets/TICKET-050.md:352` carries the worktree finding and
`:387` the base one, for
`src/checker/tests.rs::polymorphic_recursion_through_a_func_type_argument_is_refused_in_bounded_time`
-- a bounded-time test that reproduces under load and passes on an idle box
-- and both repeat at `:430` and `:432` on the re-plan. The planning agent
diagnosed it correctly and parked rather than thrash; the only way out was a
human `pipeline resume <id> triage`.

Expected: this verdict does not charge `planning`. The row it should reach
already exists in shape at `pipeline/core/machine.py:174`, which escalates
`("plan-validation", "no-test-file")` charging no counter because `CLAIMS`
gives the field to `triage` -- and the gate's own message should say the test
passes on base too, so a human re-runs `triage` rather than reading it as a
bad plan. The failing test belongs in `tests/test_gate.py` beside
`test_a_nonexistent_test_file_does_not_charge_a_plan_validation_attempt`,
whose shape it mirrors; today the same scenario ends with
`plan_validation_attempts == 1`.

Note for whoever plans it: `transition()` is in `machine.FENCED`, so this
ticket's diff parks at `awaiting-merge` for human review.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
