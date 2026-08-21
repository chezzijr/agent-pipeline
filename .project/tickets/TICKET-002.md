---
id: TICKET-002
stage: done
class: feature
branch: ticket/002
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

A human `reject` does not burn a `plan_validation_attempts` charge. That
counter measures the *validator* rejecting a plan on mechanical/judgment
grounds; a human rejecting a plan they simply do not want is a different
signal, and merging the two would corrupt the escalation-rate metric -- the
single headline metric the whole system reports on. `reject` charges its own
counter, `plan_rejections`, and the bound lives in the CLI rather than the
state machine: on the 3rd rejection the command refuses outright instead of
escalating, because escalation means "a human must look" and one already is,
holding the keyboard. Like every other counter in this system, `plan_rejections`
is lifetime, not "in a row" -- nothing auto-clears it on a successful replan,
so the refusal message's `resume --stage triage` names `--reset
plan_rejections` explicitly rather than leaving the human to discover that
resume alone leaves the count intact. No `--force` -- `resume` is right there
if the human means it.

## Rollback

## Thread

### 2026-08-21 03:13:21Z · human · note

Implemented outside the pipeline during the initial build, before any real agent could run (the claude-code harness could not pass its prompt -- see `.project/known-issues.md`). Landed as:

    f0dbdf1 feat(002): pipeline reject returns a plan to planning with its reason

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
