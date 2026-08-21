---
id: TICKET-010
stage: done
class: refactor
branch: ticket/010
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

extract a Ticket model with a structured thread

Design phase 1. Ticket access is `load_ticket`/`save_ticket` plus ad-hoc dict
poking in eight places, and the thread is freeform prose that a later stage
cannot read as data.

Expected: a `Ticket` model with typed fields, validation on save, and a single
writer path; thread entries gain a machine-readable header
(`### <ts> · <stage> · <kind>`) while staying hand-editable markdown. Storage
stays markdown in git -- moving it to a database would kill hand-editing, which
is the property that makes the system interactive.

Spec: ~/.claude/plans/2026-08-20-pipeline-app-design.md

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

    5f12a19..cbc51e6 + b0fec96 refactor(010): package split, Ticket model, single writer path

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
