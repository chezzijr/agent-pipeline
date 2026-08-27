---
id: TICKET-080
stage: new
class: feature
branch: ticket/080
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

resume and answer cannot be combined, so a resumed ticket cannot be given guidance

`pipeline resume` moves the stage. `pipeline answer` refuses outside
`needs-input`:

    $ pipeline answer TICKET-068 "..."
    error: TICKET-068 is in `planning`, not `needs-input`

So the two cannot be used together. Resuming an escalated ticket restarts it
with nothing but the thread it already had, at precisely the moment the
operator has the most to say -- they have just read an escalation, decided it
was recoverable, and chosen which stage to restart from. That judgement is
exactly what the next stage needs and there is nowhere to put it.

Observed 2026-08-27, twice in one session: an escalated ticket was resumed to
`planning` with a granted attempt, and the operator's reasoning for the grant
went nowhere. A second ticket needed guidance while at `planning` and the
answer was refused, so the guidance waited for the ticket to reach a gate that
accepts one.

`answer`'s stage check is correct on its own terms -- an answer appended to a
running stage races the agent holding the lease, and `## Thread` is the
protocol both sides read. This ticket is not asking to relax it.

Expected: an operator resuming a ticket can attach a note that the resumed
stage sees, recorded in `## Thread` the way `answer` records one and attributed
to the human. `pipeline resume --note "..."` is the obvious shape -- the ticket
holds no lease when it is escalated, so the write is unraced, and `resume`
already writes to the ticket.

Whether the same should work for a ticket parked at a gate that is not
`needs-input` is a separate and harder question -- a running stage's lease is
the thing that makes it hard, and this ticket does not need it answered. Keep
the scope at `resume`.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
