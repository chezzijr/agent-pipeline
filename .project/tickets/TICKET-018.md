---
id: TICKET-018
stage: triage
class: bugfix
branch: ticket/018
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

`## Digest` and `## Decisions checked` are checked for non-emptiness only

The design conversation specifies two Tier A checks with real content requirements:

- "Context digest section exists: files touched, key functions, entry points, gotchas --
  minimum N entries or explicit justification for fewer"
- "Decisions file was read: plan cites which decision entries were checked (list of
  decision IDs, or explicit 'none relevant' with grep terms used)"

`gate()` implements both as "the section is a non-empty string". A digest of one word
passes. A `## Decisions checked` citing `DEC-999` passes even though no such record
exists -- the IDs are never resolved against `.project/decisions/`, though
`active_decisions()` now exists and would make that a one-line lookup.

This is the check that is supposed to stop a plan reverting a deliberate fix, so a
citation nobody verifies is the weakest possible version of it.

Expected: a minimum entry count for the digest (or an explicit justification line), and
cited decision IDs resolved against the decisions directory -- an unknown ID is a finding,
and a superseded one is noted rather than treated as binding.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-21 03:13:42Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup
