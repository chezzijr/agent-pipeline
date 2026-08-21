---
id: TICKET-001
stage: done
class: feature
branch: ticket/001
test_file: null
files_declared: []
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
lease:
  holder: null
  expires: null
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

### 2026-08-21 03:13:21Z · human · note

Implemented outside the pipeline during the initial build, before any real agent could run (the claude-code harness could not pass its prompt -- see `.project/known-issues.md`). Landed as:

    cea9cb7 feat(001): a merging state so a done ticket actually lands on base

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
