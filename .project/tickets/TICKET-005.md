---
id: TICKET-005
stage: done
class: feature
branch: ticket/005
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

ticket class should select bounds, not just prompts

`class` picks the model and skips holistic review for bugfixes. The original
design also had it select the bounds: a refactor deserves 3 review loops and a
mandatory holistic pass; a one-line bugfix needs neither.

MAX_ATTEMPTS is currently a single module-level constant shared by every loop and
every class. Expected: bounds come from a per-class table owned by the dispatcher,
never from an agent prompt.

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

    e79071a feat(005): loop bounds come from the ticket class, not one constant

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
