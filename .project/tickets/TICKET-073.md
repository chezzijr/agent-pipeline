---
id: TICKET-073
stage: new
class: feature
branch: ticket/073
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

the approval gate shows the validator's log, not the plan being approved

`awaiting-approval` is the one human gate in the normal route, and the
question it asks is "is this plan right?". The TUI answers a different one.
`a`/`r`/`A` are bound at `pipeline/tui/app.py:193` and the pane keeps
rendering `#log` -- the plan-validation stream. That is the validator's
VERDICT on the plan, not the plan.

Reported by the operator while approving a real ticket: "when awaiting
approval it should show me the plan not just log (it seems that it is the
plan validation log, I need to know the plan to approve)".

The data and the reader already exist and are one command away:

    $ pipeline plan TICKET-007
    ## Plan
    ...
    ## Acceptance criteria
    ...

`cmd_plan` (`pipeline/cli/main.py:108`) reads them off the ticket with
`t.section()`. The TUI already calls CLI functions directly for exactly this
kind of reuse -- `action_approve` calls `cmd_approve` at
`pipeline/tui/app.py:659`. Nothing new has to be read, parsed or stored.

Expected: with a ticket at `awaiting-approval` selected, the pane shows what
is being approved -- `## Plan`, `## Acceptance criteria` and `## Rollback` --
and the operator can still reach the stage log. Which is the default and which
is the keypress is planning's call, but the plan is what the gate is for, and
the log is what the operator has been reading instead.

Two notes, neither a decision:

- `cmd_plan` prints `## Plan` and `## Acceptance criteria` but not
  `## Rollback`. Approving a plan is agreeing to its undo path too, and it is
  one more `t.section()` call. Whether the CLI command gains it as well, so
  the two stay the same view, is worth deciding once rather than twice.
- `awaiting-merge` is a different gate asking a different question -- there
  the thing to look at is the diff, not the plan. OUT of scope here; do not
  widen into it. If it deserves the same treatment it deserves its own ticket.

`tests/test_tui.py` drives the dashboard through a fake client, which is where
a test that fails today belongs: a ticket parked at `awaiting-approval` whose
rendered pane does not contain its `## Plan` text.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
