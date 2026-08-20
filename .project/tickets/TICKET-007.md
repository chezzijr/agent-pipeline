---
id: TICKET-007
stage: new
class: refactor
branch: ticket/007
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

verifying runs the suite inline and stalls the dispatcher loop

`start()` runs `cfg["test_suite"]` inline for the `verifying` stage, so a slow
suite blocks the whole dispatcher -- no other ticket advances and no agent is
reaped while it runs. Marked in the code as a known ceiling:
`# ponytail: run inline. A slow suite stalls the loop`.

Expected: verification runs as a tracked child in the in-flight table like an
agent, with its exit code driving the transition. It must stay script-run --
no agent, no model judgment on test results.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
