---
id: TICKET-069
stage: new
class: feature
branch: ticket/069
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

max_parallel is per-daemon, so one expensive project sets it for all

`-j/--max-parallel` is an argument to `pipeline start` and `pipeline run`
(default 3), passed to `tick()` and compared against the whole inflight set.
The daemon serves every registered project, so one number governs a repo whose
stages run a compiler and a repo whose stages run a script. There is no way to
say "this project, at most one at a time".

Three worktrees each running a release build is the failing case: the machine
runs out of memory and children are killed with exit 137, which reaches the
dispatcher as an ordinary non-zero stage result and charges the ticket's
counters for it.

    $ pipeline start -j 3            # fine for project A, OOMs project B

Expected: `.project/pipeline.toml` can set `max_parallel`, and the dispatcher
uses `min(cli value, project value)` for that project's tickets -- a project
can lower the daemon's number, never raise it above what the operator asked
for. A project with no key behaves exactly as today. The config is read from
git HEAD like every other key, so a stage cannot widen its own concurrency.

Deliberately not in scope: memory or CPU limits per project command. That is a
resource-control subsystem, and `systemd-run --scope -p MemoryMax=...` inside
the project's own test command already covers it in one line. If planning finds
`min()` is wrong -- the daemon's `-j` also bounds the machine as a whole, so a
per-project cap does not by itself stop three projects overlapping -- say so
rather than widening the ticket.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
