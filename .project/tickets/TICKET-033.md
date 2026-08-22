---
id: TICKET-033
stage: rejected
class: feature
branch: ticket/033
test_file: null
files_declared: []
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: triage
  id: 2e3668c9-2ce4-4fe3-b1d7-cd34dfc0b6e1
  log: .project/logs/TICKET-033-triage-2e3668c9.log
---

## Summary

Rejected at triage: change targets `pipeline/stages/review.md` prompt text, no
reproducible test possible. See Thread for detail.

`review` can fail a ticket on a finding nothing ever checks, and two such findings escalate it

`review` returns `ok` or `fail`. A `fail` charges `review_loops` and routes to
`implementing`, and at `BOUNDS[class]["review_loops"]` the ticket escalates. No
stage, script or hook ever asks whether a finding was correct -- the counter is
spent on the claim alone.

From the event log over 20 tickets:

    review:        fail 4 / ok 16
    each fail  ->  implementing ($1.73) + review ($1.92) = $3.65 to bounce
    BOUNDS bugfix/feature review_loops = 2

So two wrong findings escalate a ticket whose code was fine, and one wrong
finding costs $3.65. This is the same shape as the Tier A fence bug fixed in
f32c1a1: a spurious finding burning a bounded counter.

Suggested direction, not a decision for this ticket to skip: `review.md` could
require the reviewer to try to refute each finding from the code before
returning `fail`, and drop any it can refute with a `file:line` -- an existing
test asserting the opposite, an earlier guard, a type constraint. An adversarial
review of f32c1a1 dismissed 3 of 8 charges on exactly those grounds. "Looks
wrong" is not a finding and "unlikely in practice" is not a refutation.

Expected: a review finding that the code already disproves does not reach
`## Thread` and does not charge `review_loops`.

Note for triage: this is a change to a stage prompt, so there may be no
reproducible failing test. If so, return `rejected` and say why -- that is a
correct answer here, not a failure.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-21 17:16:15Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

### 2026-08-22 · triage · rejected

Ticket is a change to `pipeline/stages/review.md` prompt text, no code path.
Confirmed: this repo's test suites (`tests/`, `pipeline/hooks/test_dangerous_commands.py`)
exercise dispatcher/hook Python, not stage prompt content -- no test can fail
"because of" a reviewer's finding quality, since that quality depends on an
LLM's judgement at review time, not on any assertable code path.
Ticket itself anticipates this: "Note for triage: this is a change to a stage
prompt, so there may be no reproducible failing test. If so, return `rejected`
and say why -- that is a correct answer here, not a failure."
Rejecting per that note.

dispatcher pickup

### 2026-08-21 17:16:49Z · triage · session · session=2e3668c9-2ce4-4fe3-b1d7-cd34dfc0b6e1

`triage` ran as session `2e3668c9-2ce4-4fe3-b1d7-cd34dfc0b6e1`
- replay: `claude --resume 2e3668c9-2ce4-4fe3-b1d7-cd34dfc0b6e1`
- log: `.project/logs/TICKET-033-triage-2e3668c9.log`

### 2026-08-21 17:16:49Z · triage · transition · to=rejected · result=rejected · marker=yes

**triage -> rejected** (result: `rejected`)

✓ change targets review.md prompt text, no code path exists to test — rejected per ticket's own note
