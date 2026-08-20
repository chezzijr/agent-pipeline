---
id: TICKET-011
stage: new
class: feature
branch: ticket/011
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

daemon with a unix socket and a sqlite event log

Design phase 2. Today the dispatcher IS the terminal: close it and the work
stops, and metrics exist only while it runs.

Expected: `pipelined` watches many registered projects, records typed events to
SQLite at ~/.local/state/pipeline/, and serves NDJSON over a unix socket at
$XDG_RUNTIME_DIR/pipeline/daemon.sock. `pipeline ls` is the first client.
Ticket files stay the only source of truth for ticket state; the database holds
the event log only.

Spec: ~/.claude/plans/2026-08-20-pipeline-app-design.md

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
