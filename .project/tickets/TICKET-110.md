---
id: TICKET-110
stage: new
class: bugfix
branch: ticket/110
test_file: null
files_declared: []
depends_on: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

`pipeline resume` edits frontmatter while a stage holds the lease, and the stage is blamed for it

`pipeline answer` re-queues silently, so the next tick spawns a stage; a
`pipeline resume` typed after it edits the ticket under that stage's lease,
and the dispatcher reports the human's edit as the agent's. On main at
10b44e3, `cmd_resume` never asks whether the lease is held --
`pipeline/cli/main.py:380`:

    t.stage = args.stage
    for key in args.reset or []:
        t.counters[key] = 0
    ...
    t.release_lease()

`cmd_note` in the same file already asks, and says so
(`pipeline/cli/main.py:331`):

    print(f"{args.id}: note added"
          + (f" (`{t.stage}` holds a lease; it reaches the stage on its next spawn)"
             if t.lease_active() else ""))

The sequence, which escalated two tickets in the `chezzilang` project
(`/home/chezzijr/proj/chezzilang/.project/tickets/TICKET-049.md:677` and
`.../TICKET-050.md:691`, both reading
`` `planning` edited dispatcher-owned frontmatter: stage='triage', lease={'holder': None, 'expires': None} ``):

    pipeline answer TICKET-050 "..."   # -> planning, dispatcher spawns
    pipeline resume TICKET-050 triage  # edits stage/counters/lease mid-run
    # dispatcher: "`planning` edited dispatcher-owned frontmatter: stage='triage', lease=None"

`_finish()` diffs the agent's frontmatter against the pre-spawn snapshot
(`pipeline/daemon/supervisor.py:1209`) and escalates at
`pipeline/daemon/supervisor.py:1230`:

    escalate(t, f"`{stage}` edited dispatcher-owned frontmatter: "
                + ", ".join(f"{k}={v!r}" for k, v in tampered.items()), emit)

The diff proves the fields changed; it cannot prove who changed them, so
naming the stage is an accusation the evidence does not carry, and it sends
the operator to read a stage log that shows nothing.

Expected: `pipeline resume` on a ticket whose `lease_active()` is true does
not silently proceed -- it refuses, or warns naming the holder, the way
`cmd_note` does. The failing test belongs in `tests/test_cli.py` beside
`test_note_appends_at_any_stage_without_touching_control_fields`: resume a
ticket carrying a live lease and assert the command did not rewrite `stage`
(or that its output names the holder); today it rewrites it with no output
about the lease at all.

Second half, for `planning` to weigh: word the escalation as "frontmatter
changed while `planning` held the ticket", asserting only what the snapshot
diff shows. `tests/test_dispatch.py:157` asserts the current wording.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
