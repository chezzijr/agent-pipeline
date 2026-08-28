---
id: TICKET-085
stage: new
class: feature
branch: ticket/085
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

every stage reports its dollar cost and nothing reports its tokens

`pipeline/stream/events.py` already normalises both numbers off the harness's
`result` event:

    return {"kind": "result", "total_cost_usd": _num(ev.get("total_cost_usd")),
            ...
            "usage": ev.get("usage") or {}, "modelUsage": ev.get("modelUsage") or {},

Nothing reads either one. `grep -rn "total_cost\|cost_usd" pipeline/daemon/
pipeline/tui/` matches nothing on 2026-08-28. The numbers are parsed, handed
to the sink, written to the event log, and never surface where a human looks:
not in `## Thread`, not in `pipeline ls`, not in `pipeline metrics`.

The one place cost appears at all is a failure. TICKET-077 made a
budget-killed stage say `was killed at its $5 budget cap`, so today an
operator learns what a stage costs only when it costs too much.

What is actually available, from TICKET-066's successful `planning` run:

    total_cost_usd:              6.089121
    cache_read_input_tokens:     4,393,384
    cache_creation_input_tokens:   186,837
    output_tokens:                  80,906
      of which thinking_tokens:     31,412
    input_tokens:                       74

That run finished inside a $10 cap that had just been raised from $5. Nobody
could see it landed at $6.09 rather than $9.90, which is the difference
between a cap that is right-sized and one that is about to bite again.

Expected: a stage's cost AND its token usage are visible after it runs,
without reading a JSON log by hand. The shape is planning's call -- a line in
the stage's `## Thread` session entry is the obvious candidate, since that
entry already exists and already names the session and the log path.

Why tokens and not just dollars, since the harness only caps in dollars
(`--max-budget-usd`; there is no token cap flag -- `--autocompact` sizes the
compaction window, not a budget): dollars are the right unit for an
API-billed run and already account for model mix and cache hits. They are a
proxy for a subscription, where the binding constraint is quota, not price.
Reporting both lets an operator see which constraint they are actually near.
The cache-read figure above -- 4.4M tokens, two orders of magnitude over the
output -- is invisible in a dollar number and is most of what a long stage
does.

Two constraints on any answer:

- `parse()` must keep never raising (`pipeline/stream/events.py`). A missing
  or malformed `usage` is normal, not an error.
- Do not add a token CAP. The harness owns budget enforcement and exposes no
  token flag; watching the stream and killing the child duplicates what
  `--max-budget-usd` already does and would need its own bound. This ticket
  is about visibility only.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
