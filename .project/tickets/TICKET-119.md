---
id: TICKET-119
stage: rejected
class: feature
branch: ticket/119
test_file: null
files_declared: []
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 0
  plan_files: 0
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: triage
  id: 01a07273-188b-7391-ad92-095223e6e65e
  replay: codex exec resume 01a07273-188b-7391-ad92-095223e6e65e
  log: .project/logs/TICKET-119-triage-ae2ad675.log
  cost_usd: null
---

## Summary

Live Codex 0.153.4 behavior matches the required write boundary. An isolated
linked-worktree probe committed successfully. The generated hook blocked
`git worktree remove forbidden` and an `apply_patch` outside its worktree.
The ticket identifies missing future conformance coverage, not a reproducible
runtime defect.

## Reproduction

Command: isolated `codex exec` with the generated `triage` hook settings,
`--sandbox danger-full-access`, and `PIPELINE_WORKTREE` set to a linked
worktree.

Output:

```
[ticket/119 ac69c91] probe
 1 file changed, 1 insertion(+)
 create mode 100644 commit-probe.txt
Command blocked by PreToolUse hook: Blocked by the pipeline guard (triage): worktrees are the dispatcher's to manage.
Command blocked by PreToolUse hook: Blocked by the pipeline guard (triage): /tmp/TICKET-119-codex-outside.txt is outside this stage's worktree /tmp/ticket119-codex.HMzKuR/wt.
```

expect: Blocked by the pipeline guard

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-09-05 16:20:32Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-05 16:44:00Z · triage · rejected

Cannot reproduce a runtime defect. Codex CLI `0.153.4` completed an isolated
linked-worktree commit: `[ticket/119 ac69c91] probe`. The generated hook
blocked `git worktree remove forbidden` with `worktrees are the dispatcher's
to manage.` It blocked an `apply_patch` to `/tmp/TICKET-119-codex-outside.txt`
as outside the worktree. `tests/test_harness.py` lacks live coverage, but that
is an enhancement request and cannot supply the required failing bug test.

### 2026-09-05 16:44:52Z · triage · session · session=01a07273-188b-7391-ad92-095223e6e65e

`triage` ran as session `01a07273-188b-7391-ad92-095223e6e65e`
- replay: `codex exec resume 01a07273-188b-7391-ad92-095223e6e65e`
- log: `.project/logs/TICKET-119-triage-ae2ad675.log`

### 2026-09-05 16:44:52Z · triage · transition · to=rejected · result=rejected · marker=yes

**triage -> rejected** (result: `rejected`)

✓ Live Codex 0.153.4 probe passed; the ticket describes missing future coverage, not a current reproducible defect
