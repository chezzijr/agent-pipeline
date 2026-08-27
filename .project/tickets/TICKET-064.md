---
id: TICKET-064
stage: new
class: bugfix
branch: ticket/064
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

gate reads a test command that ran nothing as a passing repro

`gate()` (`pipeline/core/gate.py`) runs the project's `test_one` and treats
exit 0 as "the test passes, so it is not a reproduction". Exit 0 also means
"the runner's filter matched nothing and it ran zero tests" -- a config whose
selector does not fit the project. The gate cannot tell those apart, so a
misconfigured project has every ticket bounced at `plan-validation` with a
finding blaming the ticket.

The fail branch immediately below already guards the mirror image of this, with
the reasoning that applies here (`pipeline/core/gate.py:216`):

    elif node not in out:
        # a missing dependency or an import error exits non-zero too, and
        # looks exactly like a failing test unless you check for the name

Reproduce with a `test_one` that exits 0 without ever naming the test, which is
what any runner does when its filter matches nothing:

    test_one = "true"                        # in .project/pipeline.toml

    >>> ok, findings = gate(project, "TICKET-001")
    # findings says: `test_thing.py::test_broken` PASSES -- it must fail
    #                before implementation

Expected: when `test_one` exits 0 and the test's name never appears in its
output, the finding says the command did not run that test at all -- a config
error -- rather than asserting the test passes. The same distinction the fail
branch already makes. `_base_findings()` runs the same command against a
checkout of base and needs the same check.

The exact string a test should assert on today is `PASSES -- it must fail
before implementation`, produced by a `test_one` that never mentions the test.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
