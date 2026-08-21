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
4. Confirm the ticket's failing test now passes and commit.

If the plan turns out to be wrong -- an API does not work as the plan assumed,
a step is impossible, the fix would require touching files outside
`files_declared` -- **do not improvise a different plan**:

1. Commit what you have as `WIP: blocked`. The partial work is the best
   evidence of why the plan fails.
2. Append a blocked report to `## Thread`: what you attempted, what contradicts
   the plan, and the smallest reproduction of that contradiction.
3. `result: blocked`.

`result`: `ok` (plan executed, test passes) | `blocked` (plan contradicted)
