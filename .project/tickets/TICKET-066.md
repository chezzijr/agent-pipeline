---
id: TICKET-066
stage: new
class: feature
branch: ticket/066
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

test_file holds one test, so a two-test reproduction cannot be filed

`test_file` is a single `<path>::<name>` string (`SAFE_TEST`,
`pipeline/core/ticket.py:29`). A bug that needs two failing tests to be
reproduced -- one per engine, one per code path -- has nowhere to record the
second, and `test_suite_without_new` can never go green: it excludes one test
and the other is still red, which the gate reports as pre-existing breakage.

    test_file: tests/test_a.py::test_first    # the second repro test has no home

    # gate: suite excluding `tests/test_a.py::test_first` is RED --
    #       pre-existing breakage, fix that first

The workaround is deleting the second test, letting the ticket through, and
re-adding it in a later commit -- which removes it from exactly the check it
was written for.

Expected: `test_file` accepts a list, and every place the gate consumes it
handles more than one -- the existence check, the `test_one` run and its
name-in-output check, the copy onto the base checkout, and the exclusion in
`test_suite_without_new`, which needs to exclude all of them at once. A single
string must keep working: every existing ticket in `.project/tickets/` has one,
and `validate_meta()` sees this field before anything else does.

This is a data-model change, not a patch: `SAFE_TEST`, `Ticket.test_file`,
three call sites in `pipeline/core/gate.py`, `_base_findings()`, and whatever
substitution TICKET-067 settles on all read it.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
