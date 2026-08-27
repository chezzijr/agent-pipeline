---
id: TICKET-079
stage: new
class: feature
branch: ticket/079
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a command acceptance criterion is rejected for naming no test

`gate()` requires every `## Acceptance criteria` item to name a test. A
criterion that names a COMMAND and its expected result is rejected:

    - acceptance criterion names no test: 7. `cargo clippy --all-targets -- -D warnings` is clean.
    - acceptance criterion names no test: 5. `grep -c 'on an unreadable root' docs/stdlib.md` prints `0`
    - acceptance criterion names no test: 7. `grep -cF '~~**W8-39**~~' docs/gaps.md` prints `1`

Those are falsifiable. `grep -c ... prints 0` is arguably MORE falsifiable
than a test name: it states the command, the expected output, and can be
checked by anyone in one line. The rule rejects them anyway, because the only
shape it recognises is a test node id.

Measured on another project 2026-08-27: this rule fired on 5 of 11 tickets
(004, 006, 009, 010, 011) and was the single largest source of re-plans there.
TICKET-065 has since made it stop CHARGING `plan_validation_attempts` -- it is
in `STRUCTURAL_MARKS`, so it charges `structural_gate_failures` instead -- but
the rejection still stands, so every such plan still pays a full planning run
and a full validation run to reword a criterion that was correct.

Expected: an acceptance criterion that names a command and the observable
result of running it satisfies the check. A criterion that states an opinion
("the code is cleaner") still does not.

The hard part is telling those apart mechanically, and it is planning's to
solve. A shape like "a backticked command plus a stated expected output or
exit status" is checkable; "mentions backticks" is not, because prose quotes
identifiers in backticks all the time.

Do not solve this by dropping the check. Its purpose is that a criterion must
be something a machine can decide, and an unfalsifiable criterion is exactly
what `plan-validation`'s Tier B pass exists to catch -- see the vacuous
criterion it caught on TICKET-009, which printed 4 whether or not the code
under test was correct.

Related but separate: TICKET-081, a criterion whose command is fine but whose
pinned NUMBER goes stale.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
