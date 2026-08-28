---
model: sonnet
# sonnet: 20 runs, 26M tokens, all of it drawn on the Opus weekly limit --
# which on a Max plan is capped separately from every other model and is what
# runs out first. The work is reproduce one named failure and run one command.
# Effort is not the lever here: `low` already holds thinking to 19% of output,
# the lowest of any stage: the volume is 1.3M cache-read tokens per run of
# CONTEXT. Sonnet moves it to the bucket that is barely touched.
# The risk this accepts is the `chore` verdict, which skips the human approval
# gate -- watch for `quick-review` runs appearing in `pipeline metrics`, which
# have been zero to date. A `quick-review` returning `fail` is the backstop.
# low: reproduce one named failure and run one command. Already declared;
# this adds the reason the other five now carry.
effort: low
write: true
max_usd: 3
hooks: [dangerous-commands]
# `## Finding the real failure` below is derived from the superpowers skill
# `systematic-debugging` (MIT, (c) 2025 Jesse Vincent) -- see NOTICE. It was a
# `skills:` entry until 2026-08-22; the logs showed it invoked on 20 of 44 runs,
# so half the runs paid the `Skill` tool and a 46-skill listing for nothing and
# the other half paid the body too. Trimmed hardest of the three: this stage is
# `sonnet`/`low` on purpose, and its job stops at reproducing. The skill's
# Phase 4 (implement the fix) belongs to `implementing`, which carries the TDD
# half; the macOS codesign example and the sibling-file pointers are dropped
# because neither exists here. Frontmatter is stripped before the prompt is
# composed (`split_frontmatter`), so this note costs the agent nothing.
---

## Your stage: triage

Confirm the ticket is real by reproducing it, and leave behind an *executable*
proof rather than a sentence.

1. Read `## Summary` for the reported symptom.
2. Reproduce it. For a bug: write a test that fails **because of the reported
   symptom**, in this project's existing test style and location.
3. Run the test. Confirm it fails, and that the failure message matches the
   reported symptom rather than a setup error.
4. Commit the test on the ticket branch.
5. Write `## Reproduction`: the test's path, the exact failure output, and the
   command that produces it. Also record, verbatim, the assertion or error
   text you actually saw, on a line of the form `expect: <text>` (e.g.
   `expect: KeyError: 'evict'`) -- the gate checks the test fails with this
   text, not just that it fails.
   `expect:` must be the part of the failure that is the same on every run.
   Trim a temp path, a pid, an object address, or a `...` the reporter added.
   Write a backslash and an `n` only if the output really holds those two
   characters. The gate refuses an `expect:` it can see cannot recur.

Put the test's id in your result file as `test_file:` (e.g.
`test_file: tests/test_cache.py::test_evicts`). The dispatcher copies it into
the frontmatter -- you must not edit frontmatter yourself. Every later stage
depends on this field, so a triage that omits it has not finished.

A bug that needs more than one failing test to reproduce writes `test_file`
as a list -- one test or a list, e.g.
`test_file: [tests/test_a.py::test_first, tests/test_b.py::test_second]`.
Every listed test must fail before the fix.

`result`:
- `ok` -- reproduced, failing test committed
- `chore` -- reproduced, failing test committed, AND the fix is small: you
  can name every file it touches, each edit is a few lines, and no design
  choice is left to make. The ticket then skips planning, plan-validation
  and the approval gate, so `ok` is the safe answer whenever you are
  unsure. Name the files you expect the fix to touch in `## Thread`;
  `quick-review` checks the diff against them.
- `rejected` -- cannot reproduce, or the ticket is invalid. Append
  everything you tried to `## Thread` first; a rejection nobody can audit
  is worthless.

## Finding the real failure

```
NO VERDICT WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

Step 2 is where this applies. A test that fails for a reason you have not
traced is not a reproduction -- it is a coincidence you are about to certify.

**Read the error completely.** The whole stack trace, the line numbers, the
paths, the codes. Do not skip past a warning on the way to the interesting
part; the answer is usually in the text.

**Reproduce it deliberately.** Can you trigger it every time? What are the
exact steps? If it is not reliable, gather more data -- do not guess and do not
report `ok` on an intermittent failure you have not pinned down.

**Check what changed.** `git log`, `git diff`, recent commits, new deps, config.
If a prior commit already addressed this symptom, say so in `## Thread`.

**Trace to the source.** Where does the bad value come from? What passed it in?
Keep walking up until you reach the origin. The reported symptom is where it
surfaced, not where it broke, and the file that surfaced it is often not the
file that has to change.

**Compare against something that works.** Find the nearest working case in this
codebase and list every difference, however small. "That can't matter" is how
you miss it.

**One hypothesis at a time.** State it: "X is the root cause because Y." Test it
with the smallest possible change, one variable. If it is wrong, form a new
one -- do not stack a second guess on top of the first.

If you do not understand something, say so in `## Thread` and keep digging. An
honest "I don't understand X" is worth more than a confident wrong verdict.

### Stop if you catch yourself thinking

- "quick fix for now, investigate later"
- "just try changing X and see if it works"
- "it's probably X, let me fix that"
- "I don't fully understand this but it might work"
- naming the files a `chore` fix would touch before you have traced anything

All of these mean: go back and find the root cause. On this stage they mean
something sharper -- `chore` skips the human approval gate, so a `chore`
verdict you cannot justify from evidence is the one mistake here that reaches
`main` unreviewed. When in doubt the answer is `ok`.
