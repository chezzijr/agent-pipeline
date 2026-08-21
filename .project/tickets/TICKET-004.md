---
id: TICKET-004
stage: done
class: bugfix
branch: ticket/004
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

Tier A must check the failing test matches the reported symptom

The gate checks that the ticket's test fails and that its name appears in the
output, which catches an import error masquerading as a failure. It does not
check that the failure is the *reported* one. A triage agent can write a test
that fails for an unrelated reason and pass the gate.

Expected: `## Reproduction` records the expected assertion/error string, and the
gate greps the captured failure output for it.

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

    b89c424 fix(004): Tier A checks the failure matches the reported symptom

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
