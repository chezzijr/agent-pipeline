---
id: TICKET-008
stage: done
class: feature
branch: ticket/008
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

a plan must be able to supersede an existing decision record

`record_decision` writes `.project/decisions/DEC-<n>.md` when a ticket lands, and
`planning.md` greps that directory. Nothing can ever retire or contradict an
entry. The plan-validation checklist says a plan must "comply or explicitly
supersede with justification", but there is no mechanism for superseding.

Expected: a decision record can be marked superseded by a later ticket, with the
reason recorded, and planning agents see that status when they grep.

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

    42039da feat(008): let a plan supersede an earlier decision record

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
