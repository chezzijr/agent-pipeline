---
id: TICKET-075
stage: new
class: bugfix
branch: ticket/075
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

init --private silently removes the guarantee that a stage cannot rewrite the commands judging it

`project_config()` (`pipeline/core/config.py`) states the invariant and its
one exception:

    The project's config as HEAD has it, not as the working tree has it.
    ...
    Reading off disk let any stage rewrite `test_one`, `test_suite` and
    `base`, the commands Tier A, `verifying` and `merging` trust. Read from
    HEAD, an uncommitted edit is inert
    ...
    The disk fallback covers a project whose config git does not have:
    freshly `pipeline init`-ed and not yet committed, or `.project/` excluded
    from git (`pipeline init --private`).

The second half of that fallback is not a transient state. `init --private`
writes `.project/` into `.git/info/exclude`, so the config is NEVER in HEAD
and the fallback is permanent. Measured on a `--private` project on
2026-08-27:

    $ git check-ignore -v .project/run-test.sh
    .git/info/exclude:225:.project/    .project/run-test.sh

    $ git show HEAD:./.project/pipeline.toml
    (nothing -- read from disk)

So on every `--private` project:

- an edit to `test_one`, `test_suite`, `test_suite_without_new` or `base` is
  live the moment it is saved, including half-saved;
- a stage can rewrite those commands and have the change take effect, with no
  diff, no `machine.FENCED` stop at `awaiting-merge`, and no review. `.project/`
  is excluded from `tree_snapshot()` and Bash reaches it, which is exactly the
  path the HEAD read was added to close;
- `[readonly] allow` is read the same way, so DEC-037 -- "this file is read
  from git HEAD, so a stage cannot widen its own allowlist" -- does not hold
  either.

A live consequence was already observed: a wrapper script saved mid-edit
reached a running gate and was reported as a red suite (TICKET-074).

`CLAUDE.md` and the config template both state the HEAD read as a property of
the tool. For a whole class of project it is not one, and nothing says so at
`init --private` time or afterwards.

Expected: a `--private` project either keeps the guarantee, or the operator is
told plainly that it does not have it -- at `init --private`, and wherever the
docs assert the HEAD read. Which of those is right is planning's call.

Three shapes, none a decision: `--private` could still track
`.project/pipeline.toml` and exclude only `tickets/` and `logs/`, which keeps
the guarantee and the privacy it was actually asked for; or the dispatcher
could snapshot the config when it claims a ticket and refuse a mid-run change;
or `--private` could be documented as trading this away and warn on every
`register` of such a project. The first looks smallest and keeps the stated
invariant true, but `--private` exists so that nothing about this tool reaches
a teammate's diff, and `pipeline.toml` is the file most likely to carry a
project-specific command someone did not want committed -- so it is a real
trade, not an oversight to be patched over.

Do not fix this by removing the disk fallback: a freshly `init`-ed project has
no config in HEAD either, and that arm is load-bearing.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
