---
id: TICKET-014
stage: done
class: feature
branch: ticket/014
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

metrics views over the event log

Design phase 5. Model tiering and prompt tuning are guesswork without data.
The headless `result` event already carries total_cost_usd, modelUsage, usage,
num_turns, duration_ms and permission_denials -- no instrumentation needed.

Expected six views: escalation rate per stage (the headline), review-loop
distribution, cost per MERGED ticket by stage, gate failure reasons, guard
blocks by rule, and time parked in human gates. Cost is per merged ticket, not
per token -- a cheaper model that bounces twice is the more expensive system.

Open: PTY stages emit no result event, so their cost must come from the session
transcript or `claude agents --json`. Verify which before building.

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

    840b196 feat(014): six metrics views over the event log

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
