---
id: TICKET-078
stage: new
class: feature
branch: ticket/078
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

the review budget does not scale with the diff it has to read

`max_usd` is a per-stage constant in the stage's own frontmatter
(`pipeline/stages/<name>.md`), so `review` is given the same cap whether the
diff is four lines or four files. `BOUNDS` already rejects that model for the
other resource it hands out: `bound_for()` scales
`plan_validation_attempts` by `plan_steps // 8` and `plan_files // 4`, capped
at `BOUND_CEILING`, precisely because a bigger plan needs more tries.

Observed 2026-08-27 on another project: a $4 review cap covered ten small
tickets and was exhausted by the one 677-line, 15-file diff. The stage was
killed mid-verdict (see TICKET-077 for what that costs). The cap was not wrong
for ten of the eleven tickets; it was wrong for the one whose diff was an
order of magnitude larger.

Expected: the cap a review stage is spawned with grows with the size of what
it must read, the way an attempt budget already grows with the size of what it
must judge -- with a ceiling, so a runaway diff cannot buy an unbounded spend.

The inputs already exist. `counters["plan_files"]` and `counters["plan_steps"]`
are recorded, and the diff itself is measurable at spawn time
(`git diff --stat` against base in the ticket's worktree). Which of those is
the honest measure is planning's call: `plan_files` is what the plan DECLARED,
and the review reads what was actually written.

Two constraints on any answer:

- The ceiling matters more than the slope. An uncapped scale turns one large
  ticket into an unbounded bill, which is the failure `BOUND_CEILING` exists
  to prevent for attempts.
- `max_usd` is read from the stage's frontmatter and merged with the project's
  `[stages.<name>]` table (`stage_config()`). A scaled value has to compose
  with a project override without silently overriding the operator's number --
  same direction rule as TICKET-069's `min()`: a computed cap should not
  exceed what the operator asked for unless the operator asked for scaling.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
