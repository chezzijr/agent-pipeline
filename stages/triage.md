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

Record the test's path/id in your result summary so a human can copy it into
the `test_file` frontmatter field -- you must not edit frontmatter yourself.

`result`:
- `ok` -- reproduced, failing test committed
- `rejected` -- cannot reproduce, or the ticket is invalid. Append everything
  you tried to `## Thread` first; a rejection nobody can audit is worthless.
