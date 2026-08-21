---
model: opus
# low: reproduce one named failure and run one command. Already declared;
# this adds the reason the other five now carry.
effort: low
write: true
max_usd: 3
hooks: [dangerous-commands]
skills: [superpowers:systematic-debugging]
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

Put the test's id in your result file as `test_file:` (e.g.
`test_file: tests/test_cache.py::test_evicts`). The dispatcher copies it into
the frontmatter -- you must not edit frontmatter yourself. Every later stage
depends on this field, so a triage that omits it has not finished.

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
