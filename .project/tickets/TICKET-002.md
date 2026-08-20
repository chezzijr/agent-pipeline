---
id: TICKET-002
stage: new
class: feature
branch: ticket/002
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

reject a plan with feedback instead of hand-editing the stage

`approve` is the only exit from `awaiting-approval`. Disliking a plan means
running `resume --stage planning` by hand, and the reason you rejected it is
recorded nowhere -- so the next planning agent repeats the mistake.

Expected: `pipeline.py reject <id> "why"` appends the reason to the thread as a
human entry and returns the ticket to planning. The planning prompt must be told
to read it. Open question: should a reject burn a plan_validation_attempt?

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
