---
model: opus
effort: low
write: true
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
   command that produces it.

Put the test's id in your result file as `test_file:` (e.g.
`test_file: tests/test_cache.py::test_evicts`). The dispatcher copies it into
the frontmatter -- you must not edit frontmatter yourself. Every later stage
depends on this field, so a triage that omits it has not finished.

`result`:
- `ok` -- reproduced, failing test committed
- `rejected` -- cannot reproduce, or the ticket is invalid. Append everything
  you tried to `## Thread` first; a rejection nobody can audit is worthless.
