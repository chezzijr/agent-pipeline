---
id: TICKET-077
stage: new
class: bugfix
branch: ticket/077
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a budget-exhausted stage looks identical to a crashed one and is retried

`_finish()` (`pipeline/daemon/supervisor.py:1062`) charges `no_result` for
every spawn that ends without a `.result` sidecar:

    # L4: a harness that dies before writing a result must not respawn
    # forever. Same budget as every other bounded loop.
    n = t.counters.get("no_result", 0) + 1

A stage killed by `--max-budget-usd` reaches that branch too. The harness
passes `--max-budget-usd {cap}` (`pipeline/harnesses/claude-code.toml:187`,
`max_usd = 5` by default, per-stage overridable), and a stage that spends its
cap is terminated with `terminal_reason: budget_exhausted`.

Observed 2026-08-27 on another project: `review` ran to completion TWICE,
wrote its full verdict into the thread both times, and was killed while
writing the sidecar. The dispatcher saw `no_result` twice, escalated at
`MAX_ATTEMPTS`, and in between respawned the identical stage -- which spent
the identical budget and died at the identical point. The work was finished
and thrown away, twice, then charged to the ticket as if the harness had
crashed.

Two things are wrong and they are separable:

- **Ordering.** The sidecar is written after the thread entry, so a kill
  between them loses the verdict while keeping the evidence that it existed.
  Writing `.result` first makes a budget kill survivable: the stage's own
  conclusion is already on disk.
- **Classification.** `budget_exhausted` is not a crash. Retrying a crash is
  reasonable -- it may be transient. Retrying a budget kill is not: the same
  prompt against the same tree spends the same money and dies at the same
  point. It needs its own outcome and its own counter, and arguably a bound of
  one, since the second attempt is knowably futile.

Expected: a stage terminated for budget is reported as such -- naming the cap
it hit -- and is not respawned into the identical failure. A stage that
genuinely crashed keeps today's retry.

`pipeline/stream/events.py` is where a `terminal_reason` would be read off the
stream, and `parse()` must keep never raising. Whether the signal is available
there or only from the child's exit status is the first thing to establish;
this ticket asserts the behaviour, not the mechanism.

OUT of scope: raising `max_usd`. That is TICKET-078, and a bigger cap does not
make a budget kill distinguishable from a crash.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
