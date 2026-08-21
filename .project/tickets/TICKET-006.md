---
id: TICKET-006
stage: done
class: bugfix
branch: ticket/006
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

Tier A must verify every plan step names its target files

The conversation's Tier A list had 11 deterministic checks; the gate implements 9.
Missing here: `## Plan` must be an ordered step list where every step names its
target files. Today a plan of prose paragraphs passes Tier A and only the
judgment-based validator might catch it.

Expected: a deterministic check that each plan step is numbered and cites at
least one path that appears in `files_declared`.

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

    8025997 fix(006): gate rejects a plan of prose; steps must cite declared files

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
