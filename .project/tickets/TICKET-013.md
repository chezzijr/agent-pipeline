---
id: TICKET-013
stage: new
class: feature
branch: ticket/013
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

interactive PTY stage mode for planning

Design phase 4. Probing showed `--permission-mode manual` is ignored under
`-p` (`init.permissionMode = default`, Bash ran unprompted) and AskUserQuestion
is not in the headless toolset. Option pickers and permission prompts only
exist in a real interactive session.

Expected: `mode: interactive` in stage frontmatter; the daemon hosts such stages
under a PTY (stdlib pty + pyte, both verified available) and clients attach and
detach without killing the session. `planning` and `needs-input` use it;
everything else stays headless.

Spec: ~/.claude/plans/2026-08-20-pipeline-app-design.md

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
