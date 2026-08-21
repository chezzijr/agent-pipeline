---
id: TICKET-020
stage: triage
class: bugfix
branch: ticket/020
test_file: null
files_declared: []
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
lease:
  holder: null
  expires: null
---

## Summary

the dispatcher's stdout is block-buffered, so its log is minutes stale

`cmd_start` redirects `pipelined`'s stdout to `~/.local/state/pipeline/daemon.log`,
and Python block-buffers stdout when it is not a tty. The daemon prints one line per
stage start and per verdict -- a few hundred bytes an hour -- so nothing reaches the
file until 8 KiB accumulate or the process exits. Watching the log is how you find
out what the pipeline is doing, and it is blank while the pipeline is doing it.

Reproduced 2026-08-21 while three tickets were mid-flight:

    $ pipeline start -j 3
    pipelined 0.1.0: pid 991508 on /run/user/1000/pipeline/daemon.sock
    $ pipeline ls | tail -3            # three stages running, ticket files advancing
    TICKET-016   planning   ... LEASED
    $ tail -2 ~/.local/state/pipeline/daemon.log
      signal 15: stopping              # <- lines from the PREVIOUS daemon
      stopped TICKET-016 (planning)

Same for `pipeline run` with its output redirected: `wc -c run.log` returned `0`
while all three stages were live.

The lines only appeared after the process was stopped, which is exactly when they
stop being useful. A `tail -f` on that file emits nothing for minutes and then a
burst, so anything watching it -- a human or another program -- reads "idle" during
the run.

Expected: a line the dispatcher prints is on disk when it is printed.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-21 04:29:43Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 04:37:45Z · triage · note

`triage` was interrupted; lease released
