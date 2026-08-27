---
id: TICKET-068
stage: new
class: feature
branch: ticket/068
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

register accepts a project whose test_suite does not run

`cmd_register()` is one line -- `registry.register(Path(args.path))`
(`pipeline/cli/main.py:292`). Nothing checks that the project's three test
commands work, so a repo scaffolded with the packaged defaults registers
clean and every ticket filed against it dies at the gate, each one reporting a
different symptom of the same broken config.

    $ pipeline init ~/code/other-project     # writes test_suite = "pytest"
    $ pipeline register ~/code/other-project
    registered /home/me/code/other-project   # pytest is not this project's runner

Expected: `register` runs the project's `test_suite` once and refuses to
register -- naming the command and quoting its output -- when it cannot run at
all. "Cannot run at all" is the distinction that matters: a suite that runs and
reports failures is a normal state for a project with an open bug, and must
still register. A shell that cannot find the command, or a runner that exits
without running anything, must not.

An escape hatch belongs here (`--force`, or similar), because the check runs a
project command and a slow suite should not block registering. Whether `init`
should also detect `Cargo.toml` / `package.json` / `pyproject.toml` and
scaffold accordingly is a separate question and not part of this ticket -- the
check catches a wrong config however it got there, and a detector only narrows
how often one is written.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
