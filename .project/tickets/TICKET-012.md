---
id: TICKET-012
stage: new
class: feature
branch: ticket/012
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
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
