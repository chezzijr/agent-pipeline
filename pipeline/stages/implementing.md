---
model: sonnet
# medium: execution, not design. plan-validation already scored the plan on
# eight checks, and the plan names every file and command.
effort: medium
write: true
max_usd: 8
hooks: [dangerous-commands]
# `## Test-driven development` below is derived from the superpowers skill
# `test-driven-development` (MIT, (c) 2025 Jesse Vincent) -- see NOTICE. It was
# a `skills:` entry until 2026-08-22; the logs showed it invoked on 19 of 21
# runs, so the body was paid on almost every run anyway and the `Skill` tool
# plus a 46-skill listing rode on top of it. Inlined, trimmed to the operative
# rules, and de-TypeScripted. Frontmatter is stripped before the prompt is
# composed (`split_frontmatter`), so this note costs the agent nothing.
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

## Test-driven development

This governs step 2 above, for every test the plan asks for and every test
`## Coverage` asks you to add.

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Wrote code before its test? Delete it and start over from the test. Not "keep
it as reference", not "adapt it while writing the test" -- you will adapt it,
and that is testing after. Delete means delete.

**RED.** One minimal test for one behaviour, named for the behaviour. Real
code, not mocks, unless a mock is unavoidable.

**Verify RED -- mandatory, never skip.** Run it and read the output. Confirm:

- it *fails*, not *errors* -- an import error or a typo is not a red test, and
  in this repo a test that errors exits non-zero exactly like one that fails
- the failure message is the one you expected
- it fails because the behaviour is missing

Passes already? You are testing behaviour that exists; the test is wrong.
Errors? Fix the error and re-run until it fails for the right reason.

**GREEN.** The simplest code that passes. No options nobody asked for, no
refactoring of code beside it, no "improving" past the test.

**Verify GREEN -- mandatory.** Confirm the test passes, the tests around it
still pass, and the output is clean. If the new test fails, fix the code, not
the test. If a neighbouring test fails, fix it now.

**REFACTOR.** Only once green: remove duplication, improve names, extract
helpers. No new behaviour. Stay green.

Then the next failing test.

### Red flags -- stop and start over

- code written before its test
- the test was added after the implementation
- the test passed the first time you ran it
- you cannot say why it failed
- you are telling yourself "too simple to test", "I'll test after", "I already
  ran it by hand", or "just this once"

### Before you report `ok`

- every new function has a test
- you watched each one fail first, for the expected reason
- you wrote the minimal code that passed it
- the affected tests pass and the output is clean
- tests use real code; mocks only where unavoidable
- boundaries and hostile input are covered

Cannot tick all of them? You skipped TDD. Go back.

`result`: `ok` (plan executed, test passes) | `blocked` (plan contradicted)
