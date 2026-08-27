---
id: TICKET-071
stage: new
class: bugfix
branch: ticket/071
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a passing repro test is reported as a selector that matched nothing

TICKET-064 (merged at `ae3b53b`) split the gate's exit-0 path in two: the name
must now appear in the output for the finding to say the test passes.

    if code == 0 and node in out:
        findings.append(f"`{test}` PASSES -- it must fail before implementation")
    elif code == 0:
        findings.append(
            f"`{test}` exited 0 but its name never appears in the "
            f"output -- the selector matched nothing, not a passing "
            f"test\n```\n{out[-1200:]}\n```")

pytest names a node only when it FAILS. A passing run prints a dot and a
count, so `node in out` is false for every genuine pass and the second branch
is the one that fires:

    $ uv run --group dev pytest -x tests/test_gate.py::test_gate_passes_a_complete_ticket
    tests/test_gate.py .                                          [100%]
    ============================== 1 passed in 0.03s ==============================

    # occurrences of "test_gate_passes_a_complete_ticket" in that output: 0

So on this repo's own `test_one`, a ticket whose test passes is now told the
selector matched nothing, and the `PASSES -- it must fail before
implementation` finding is unreachable. `_base_findings()`
(`pipeline/core/gate.py:149`) carries the same split and inverts the same way
for the base run.

Neither branch lets anything through -- both are gate failures, and the gate
blocks either way -- so this is a wrong diagnosis, not a hole. The cost is a
ticket being sent back to fix a config that is correct.

Expected: a repro test that genuinely passes produces a finding that says so,
on a project whose runner prints the node name only on failure. TICKET-064's
real case -- a selector that matched nothing, which is what a runner does when
the config does not fit the project -- must still be distinguishable from a
red test, which is what its first branch already achieves.

A suggestion, not a decision: exit 0 with the name absent is genuinely
ambiguous on pytest and genuinely unambiguous on cargo, and no portable signal
separates them. Both are already a FAIL, so one finding naming both causes
loses nothing, and the output fence is right there for a human to read. If
planning finds a portable way to tell them apart, that is better.

Whether the durable answer is a register-time check on the project's own test
commands is TICKET-068's question, not this ticket's -- do not widen into it.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
