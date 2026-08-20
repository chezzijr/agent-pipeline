---
id: TICKET-001
stage: new
class: feature
branch: ticket/001
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

add a merging state so a done ticket lands on base

The state machine ends at `done` with the fix sitting unmerged on `ticket/<id>`.
The original design had `merging -> done`, with a merge conflict escalating to a
human. Today nothing merges and nothing tells you a branch is waiting.

Expected: a `merging` stage owned by the dispatcher (no agent), which merges the
ticket branch into `base` and escalates on conflict. `done` should mean landed.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
