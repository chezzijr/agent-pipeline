---
id: TICKET-016
stage: new
class: bugfix
branch: ticket/016
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

sections() splits on a `## ` line inside a fenced code block

`sections()` maps `## Name` to its content by scanning lines, with no notion of a fenced
code block. The gate and the verifying stage both embed up to 1500 characters of raw test
output inside ``` fences in a thread entry. A line of that output beginning with `## ` --
a diff hunk of a markdown file, a pytest capture of a heading -- is read as a new section.

Consequence: the entry is split, `Ticket.thread()` truncates at that point, and every
later thread entry becomes unreachable to a stage that reads the thread as data. Since
TICKET-010 that is the mechanism later stages are supposed to use to receive prior
findings as typed input rather than re-parsing prose.

Found during the TICKET-010 wiring pass. `append_entry` was made to use the same boundary
rule so read and write at least agree, but the underlying split is still there.

Expected: `sections()` tracks fence state (``` and ~~~, respecting the opening fence's
length and info string) and ignores headings inside one. Storage stays plain markdown --
this is a parser fix, not a format change.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
