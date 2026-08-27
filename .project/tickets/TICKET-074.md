---
id: TICKET-074
stage: new
class: bugfix
branch: ticket/074
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a test command that cannot run reads as a red suite

`gate()` judges `test_suite_without_new` by its exit code alone
(`pipeline/core/gate.py`, the block after the `test_one` run):

    code, out = run_cmd(cfg["test_suite_without_new"].format(...), wd)
    if code != 0:
        findings.append(
            f"suite excluding `{test}` is RED -- pre-existing breakage, "
            f"fix that first\n```\n{out[-1200:]}\n```")

A command that never ran a test exits non-zero too. Observed on a real ticket
on 2026-08-27: the project's test wrapper was mid-save, so the shell could not
parse it --

    /home/.../.project/run-test.sh: line 103: syntax error near unexpected token `;;'

-- and the gate reported:

    suite excluding `tests/chz/spec/assert_diagnostics_test.chz::bare_assert_shows_operands`
    is RED -- pre-existing breakage, fix that first

Nothing was red. The ticket was sent back from `revalidating` to `planning`
and charged `stale_regate`, and the operator was told to fix breakage that did
not exist. A missing binary, a compile error in the harness, or an unreadable
config produce the same finding.

This is the same trap the `test_one` run guards against three lines above --
`elif node not in out: ... it errored rather than failed` -- and the same one
TICKET-064 addressed for the exit-0 direction. The suite run has never had it.

Expected: a `test_suite_without_new` that exits non-zero without running any
test is reported as a command that could not run, naming the exit code and the
output, rather than as pre-existing breakage in the project's tests. What
counts as evidence a suite ran is the hard part and is planning's to decide --
there is no test name to look for here, unlike the `test_one` run.

`verifying` judges the project's `test_suite` by exit code the same way
(`pipeline/daemon/supervisor.py`, `child(cfg["test_suite"], "suite")`). Whether
it deserves the same treatment is a real question but OUT of scope here: it is
a dispatcher stage judged by a child's exit status, not a `gate()` finding, and
mixing the two makes one ticket that touches both paths. Note it and stop.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
