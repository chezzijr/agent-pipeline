---
id: TICKET-083
stage: new
class: bugfix
branch: ticket/083
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

the ticket file in a stage's worktree is a stale snapshot that contradicts its prompt

A stage is spawned with `cwd` set to the ticket's worktree and a composed
prompt carrying `stage_view()`. The worktree also contains
`.project/tickets/<id>.md` -- its own copy, from the commit the branch was cut
at. The live ticket lives in the MAIN checkout and is not committed until the
ticket finishes, so for a ticket's whole working life the two disagree, and
the copy the agent can actually open is the empty one.

Observed 2026-08-27 on TICKET-067. `implementing` refused to write code:

    the actual committed ticket file (.project/tickets/TICKET-067.md, git log
    shows only the original filing commit 0300869) is still `stage: new` with
    every section after `## Summary` empty -- no reproduction, digest, plan,
    or thread history. Two test-only commits added the reproduction test in
    tests/test_gate.py, but that work was never recorded back into the ticket.

    I appended the contradiction to ## Thread and wrote result: blocked --
    implementing has nothing verified to execute against.

It charged `blocked_count`, sent the ticket back to `plan-validation`, and
threw away a spawn. The plan was fine. The prompt was fine. The file was a
snapshot from before any of the work.

`pipeline/stages/_common.md` rule 4 already tells a stage to read the bounded
view rather than the ticket file, and that rule exists to save tokens. It does
not say the file is stale, so a stage that opens it -- to check the view it
was handed, which is the behaviour every other rule in this repo rewards --
finds what looks like a fabricated prompt and stops.

Expected: a stage cannot be handed a view its own checkout contradicts. Either
the worktree's copy reflects the ticket's current state when the stage is
spawned, or the stage is told plainly that the copy is a historical snapshot
and the view is authoritative.

Two shapes, neither a decision:

- Say it in `pipeline/stages/_common.md` rule 4: the ticket file in your
  worktree is the state at branch-cut and will look empty; the view in this
  prompt is the current ticket; do not reconcile them. Cheapest, and honest,
  but it asks an agent to trust a prompt over a file it can read, which is the
  opposite of what the rest of the rules ask for.
- Refresh the worktree copy at spawn, from the live ticket. Removes the
  contradiction instead of explaining it, but the file then sits in the
  worktree where a stage could edit it -- and `.project/` is excluded from
  `tree_snapshot()`, so nothing would notice. `Ticket.save()` being the only
  writer (invariant 5) is what makes that dangerous, and any plan taking this
  route has to say how the copy stays read-only in practice.

Do not solve this by committing ticket updates to the branch as they happen:
every stage transition would enter the ticket's own diff, `review` would read
its own thread as a change, and the merge would carry the ticket's history
into main as code changes.

This is not TICKET-072 (a stage registering its worktree) or TICKET-075
(`--private` making config disk-read): both are about what a stage can WRITE.
This is about what it can READ being wrong.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
