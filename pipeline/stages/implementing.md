---
model: sonnet
# medium: execution, not design. plan-validation already scored the plan on
# eight checks, and the plan names every file and command.
effort: medium
write: true
max_usd: 8
hooks: [dangerous-commands]
skills: [superpowers:test-driven-development]
---

## Your stage: implementing

The plan is already researched and approved. Execute it.

1. Write a todo list into `## Thread`, one entry per plan step, and keep it
   updated as you go.
2. Work the steps in order. Reuse what `## Digest` points at.
3. Stop when the acceptance criteria are met -- no extra refactors, no
   opportunistic cleanups, no "while I was in here".
4. Confirm the ticket's failing test now passes, cover the change, and commit.

## Coverage

`test_file` proves the symptom is gone, nothing more. Add what the diff needs:

- **must still fail** -- what the change must not start allowing. Required of
  any diff that widens or skips a check.
- **must still pass** -- the behaviour beside the one you changed.
- **boundary** -- the value each side of the line the code draws.
- **hostile input** -- anything parsing text an agent or a ticket wrote.

State the input that makes each new test fail. If you cannot, delete it. New
test files go in `files_declared` like any other file.

Edit an existing test only when the plan says its behaviour changed; name that
step in `## Thread`. If the plan does not, that is `blocked` -- never weaken a
test to turn the suite green.

A ticket on the cheap route has no `## Plan` and no `## Digest`: `triage`
judged the fix small, and the dispatcher skipped planning. If `## Plan` is
empty, work from `## Summary` and `## Reproduction` instead, keep the diff
inside the files those two sections name, and report every file you touched
in `files_declared`. If the fix needs a file the ticket never names, that
is `blocked`, not a wider diff -- `blocked` sends it to `planning`, which
is where a fix that size belonged.

If the plan turns out to be wrong -- an API does not work as the plan assumed,
a step is impossible, the fix would require touching files outside
`files_declared` -- **do not improvise a different plan**:

1. Commit what you have as `WIP: blocked`. The partial work is the best
   evidence of why the plan fails.
2. Append a blocked report to `## Thread`: what you attempted, what contradicts
   the plan, and the smallest reproduction of that contradiction.
3. `result: blocked`.

`result`: `ok` (plan executed, test passes) | `blocked` (plan contradicted)
