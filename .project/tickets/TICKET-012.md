---
id: TICKET-012
stage: done
class: feature
branch: ticket/012
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

stream-json parsing and a live view of a headless stage

Design phase 3. `claude -p` in text mode emits one blob at the end, so a stage
log shows nothing for minutes and then everything.

Expected: spawn headless stages with `--input-format stream-json
--output-format stream-json --verbose`, parse events into typed records
(assistant text, tool_use, tool_result, hook_started/hook_response, result,
rate_limit_event), and render them live. Guard blocks arrive as hook events, so
the guard can be watched biting in real time.

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

    18778f8 feat(012): stream-json parsing and `pipeline logs`

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
