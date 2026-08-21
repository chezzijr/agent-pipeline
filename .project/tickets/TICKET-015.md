---
id: TICKET-015
stage: done
class: feature
branch: ticket/015
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

a TUI to watch and steer running stages

The design sketches a TUI as the thing that makes the pipeline monitorable, but the
backlog never ticketed it -- 011 builds the daemon, 012 the event stream, 013 the PTY
host, 014 the metrics, and nothing renders any of it. Without this the app is a daemon
you talk to through `ls`.

Expected: a Textual app. Left pane a tree of registered projects and their tickets; right
pane either a rendered headless event stream or an attached PTY screen; keybindings
`a` approve, `r` reject, `A` answer, `e` edit, `l` logs, `m` metrics, `k` kill, `q` quit.

Four of those keys need no protocol surface at all -- approve/reject/answer mutate the
ticket file, which is the source of truth, and the daemon's next tick notices. `e`/`l`/`m`
are `app.suspend()` plus `$EDITOR` / `less` / `pipeline metrics`. Only `k` needs a daemon
op.

`e` must interrupt a running stage before opening the editor, so a human edit never trips
the dispatcher's tamper detection.

Depends on 011 (socket, `ls`, `subscribe`) and reads 012's event kinds. Defensible MVP is
tree + detail pane + `q`/`l`/`a`/`A`, live-updating from `subscribe`.

Spec: ~/.claude/plans/2026-08-20-pipeline-app-design.md

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-21 03:13:21Z · human · note

Implemented outside the pipeline during the initial build, before any real agent could run (the claude-code harness could not pass its prompt -- see `.project/known-issues.md`). Landed as:

    9ed8fb0 feat(015): the Textual TUI

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
