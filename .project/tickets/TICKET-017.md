---
id: TICKET-017
stage: new
class: bugfix
branch: ticket/017
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

Tier A runs the failing test on the ticket branch, not on base

The design conversation's Tier A list says: "Failing test FAILS on base branch -- run it,
capture output in ticket". `gate()` runs it in the ticket's worktree, which is the ticket
branch. That is weaker: it proves the test fails *here*, not that the bug exists on base.

Weakest exactly where it matters most -- the post-approval re-gate (`revalidating`) exists
to re-establish stale facts after base moved, and this is the fact most likely to have
gone stale: someone else may have fixed the bug, or the test may now fail for a reason
base introduced.

Expected: run the ticket's test against base as well, and record both results. A test that
fails identically on base and branch is the reproduction the gate is supposed to demand.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
