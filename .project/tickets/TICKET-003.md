---
id: TICKET-003
stage: done
class: bugfix
branch: ticket/003
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

re-gate a stale plan on approval instead of trusting it

A ticket can sit in `awaiting-approval` for days while other tickets merge into
base. Tier A facts recorded at plan time -- the suite was green, the new test was
the only red, no file overlap -- are stale by the time you approve.

Expected: on `awaiting-approval -> implementing`, rebase the ticket branch onto
current base and re-run the Tier A gate. Failure bounces to plan-validation and
must NOT count against plan_validation_attempts -- this is staleness, not a bad plan.

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

    b1679b9 + a1ee39c fix(003): re-gate a stale plan on approval (returns to planning)

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
