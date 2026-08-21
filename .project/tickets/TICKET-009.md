---
id: TICKET-009
stage: done
class: feature
branch: ticket/009
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

port to a second harness to prove the seam is in the right place

The repo claims the methodology is harness-neutral, but only
`harnesses/claude-code.toml` exists -- an abstraction with one implementation.
The design deliberately deferred this until real tickets had run, because the
second harness is what reveals where the seam actually belongs.

Expected: one more harness TOML, plus whatever `pipeline.py` change it forces.
If it forces none, the seam was right. Do this only after phase 0 has run real
tickets on Claude Code.

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

    5d00531 feat(009): a second harness (codex), and the two keys it forced

Closed by hand so the dispatcher does not re-triage finished work. The ticket file stays as the record of what was asked for.
