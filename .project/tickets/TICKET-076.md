---
id: TICKET-076
stage: new
class: bugfix
branch: ticket/076
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

an expect: string carrying a per-run path can never match again

`## Reproduction`'s `expect:` line is the string `gate()` greps the test's
output for, so a red test proves it is red for the REPORTED reason and not
some other one. Triage writes it by copying the failure verbatim. When that
failure names a temporary directory, the copy pins a value that only existed
during triage's own run, and every later gate fails on it.

Twice on 2026-08-27, in two different projects:

    `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run`
    fails, but its output does not mention the expected string
    'registered /tmp/tmpn7w0imby'

    `tests/chz/stdlib/fs_walk_unreadable_subdir_test.chz::walk_error_names_the_unreadable_subdir_not_the_root`
    fails, but its output does not mention the expected string
    'expected error to name the unreadable subdir /tmp/chz_w8_39_2424171/sub,
    got: /tmp/chz_w8_39_2424171: Permission denied (os error 13)'

`tmpn7w0imby` is a fresh `mkdtemp` suffix; `2424171` is a pid. Neither can
recur. The test is red, it is red for exactly the reported reason, and the
gate rejects it anyway -- then charges `plan_validation_attempts`, because an
`expect` mismatch is substantive by `structural_only()` and not in
`STRUCTURAL_MARKS` (correctly: a mismatch usually means the test is red for
the wrong reason). Two attempts lost across the two tickets, neither plan read.

The check itself is right and must stay -- `pipeline/core/gate.py`, the
`elif expect and expect not in out` arm, exists because a test failing for an
unrelated reason looks exactly like evidence. What is wrong is that nothing
stops an unmatchable `expect` from being recorded in the first place.

Expected: an `expect:` string that cannot match a second run is refused when
it is written, or reported as the malformed-frontmatter problem it is rather
than as a failed reproduction. A ticket whose `expect` is stable behaves
exactly as today.

Two shapes, neither a decision:

- Refuse it in `gate()`: a finding when `expect` contains a volatile token --
  a path under the system temp dir, a bare pid-like integer, a hex suffix --
  saying the string cannot recur and to trim it to the invariant part. This is
  enforceable in code and testable. It is structural, not substantive, so it
  would want a `STRUCTURAL_MARKS` entry too (see `CLAUDE.md`'s gotcha: a new
  structural finding without a mark silently charges like a bad plan).
- Say it in `pipeline/stages/triage.md`: `expect` must be the part of the
  failure that is the same on every run. Cheaper, but nothing checks it, and
  the two cases above were both written by a triage agent that had the failure
  in front of it.

The first looks right because the value reaching `gate()` is what breaks, but
a volatile-token detector has false positives of its own -- a test whose whole
point is a path would be refused for naming one. Whoever plans this should say
what happens to that case rather than leaving it to the regex.

OUT of scope: the wider question of the gate trusting output text
(TICKET-071, TICKET-074). This ticket is only about the value being
unmatchable the moment it is recorded.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
