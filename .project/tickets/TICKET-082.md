---
id: TICKET-082
stage: new
class: bugfix
branch: ticket/082
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a timing test under concurrent load escalates a good ticket

A test that asserts a timing ratio measures the machine, not the code. When
the dispatcher is running other tickets -- and on a compiled project that
means concurrent builds -- the ratio moves, the test goes red, and the ticket
pays for it.

Observed 2026-08-27 on another project:

    threads_one_serializes_cpu_bound_parallel_tasks
    -> failed at ratio 4.31 of a required 8 under concurrent cargo load
    -> passed 3 of 3 runs in isolation, on BOTH branches

The test is not wrong and the code is not wrong. The measurement was taken
while something else had the CPU.

What makes it expensive is where the charge lands. A red suite at
`revalidating` charges `stale_regate`, which is not class-scoped and so takes
`MAX_ATTEMPTS` from the dispatcher's own default. A CPU-load artifact
therefore spends the same budget as a genuinely stale plan, and enough of them
escalate a ticket whose work is sound.

Expected: a suite failure that a re-run does not reproduce does not, on its
own, exhaust a ticket's budget. What that means concretely is planning's call,
and the options differ a lot in cost:

- re-run a failed suite once before charging, and charge only if it fails
  twice -- simple, doubles the cost of a genuine red suite;
- serialise the stages that run a project's suite, so a timing test never
  competes with a build -- this is close to TICKET-069's `max_parallel` and
  may be subsumed by it;
- treat a non-reproducing failure as its own outcome with its own counter, the
  way TICKET-065 split structural from substantive.

There is a fourth answer that is not this pipeline's to make: a timing test
with a hard ratio is fragile on any shared machine, and the project could pin
a floor instead. Say so in the thread if that is the conclusion -- but the
pipeline still should not convert a flaky measurement into an escalation, so
this ticket does not close on that answer alone.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
