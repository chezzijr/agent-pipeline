---
id: TICKET-081
stage: new
class: bugfix
branch: ticket/081
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a criterion that pins an absolute count is true when written and false when checked

A plan measures a total while planning, writes it into an acceptance
criterion, and the number moves before the criterion is checked. Twice on
another project on 2026-08-27, both caught by a human at the approval gate and
neither by any stage:

    criterion 9 and step 12 hardcode '630 passed' for the tests/chz suite
    -> a sibling ticket merged four new tests; main measured 639

    criterion 6 asserts 26 open rows, twice
    -> W8-39 is one of those 26, and this ticket strikes it: after the change
       the count is 25, not 26

The two are different failures with one shape. The first is a number a SIBLING
ticket moved -- `stale_regate` exists for a moved base, but it re-runs the
gate, and the gate does not know 630 was ever meaningful. The second is a
number THIS ticket moves: the plan measured before its own change, so a
correct implementation fails its own criterion.

The same shape produced a third, slower failure on that project: `CLAUDE.md`'s
open-row count and `docs/gaps.md`'s table drifted six apart across ten
tickets, each of which was locally correct. Nothing checks a doc invariant
that spans two files, so ten correct changes summed to an inconsistent tree.
The one ticket that closed it stated the criterion as a RELATION -- main holds
26 rows to this branch's 27 -- rather than as a pair of absolute numbers.

Expected: a criterion whose truth depends on a total states it as a relation
to a measured baseline, or re-measures at check time -- not as a literal
copied out of `## Digest`. A plan that pins an absolute count should be
rejected with that reason, the way a vacuous criterion already is.

Two suggestions, neither a decision:

- A Tier B check: a criterion containing a bare integer that also appears in
  `## Digest` is the signature, and the validator already reads both sections.
- A rule in `pipeline/stages/planning.md`: a count that any other ticket can
  move is not a property of this change; state the delta.

The cross-file half may want its own answer -- a criterion cannot assert an
invariant between two files unless someone writes the check -- but it is the
same defect seen over a longer window, so it belongs here until a plan shows
otherwise.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
