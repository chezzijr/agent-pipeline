---
id: TICKET-070
stage: done
class: feature
branch: ticket/070
test_file: tests/test_stages.py::test_plan_validation_can_mark_an_item_unverified
files_declared:
- pipeline/stages/plan-validation.md
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 0
  plan_files: 1
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: quick-review
  id: 192a0797-7f58-4352-8e50-039989705f05
  log: .project/logs/TICKET-070-quick-review-192a0797.log
cheap_route_head: 73985338e153f9b3155fce817cedbfbfedf2cdcf
---

## Summary

Fixed: `pipeline/stages/plan-validation.md` now has an `unverified` item
channel and points at `[readonly] allow` in `.project/pipeline.toml`.

An `unverified` item is not counted as a scored finding against the plan --
the stage states what it would have run and reports it separately from
per-item findings. The stage is told to ask a human to add a needed read-only
command to `[readonly] allow` rather than work around the guard.
`readonly_rules()` and `readonly_allow()` are untouched; this is a
prompt-only change to one file.

Test: `tests/test_stages.py::test_plan_validation_can_mark_an_item_unverified`
now passes. `pipeline/stages/plan-validation.md` is the only source file
changed; the test itself lives in `tests/test_stages.py`.

quick-review: ok. Test fails without the diff and its triage is unchanged
since commit 7398533. Diff touches only the two files named above, both
named in this ticket.

## Reproduction

Test: `tests/test_stages.py::test_plan_validation_can_mark_an_item_unverified`

Command: `uv run --group dev pytest -q tests/test_stages.py::test_plan_validation_can_mark_an_item_unverified`

Output:
```
AssertionError: plan-validation has no channel for an item it could not measure
assert 'unverified' in '---\nmodel: opus\n# high: ...\n`result`: `ok` (all items pass) | `fail` (append per-item findings first; the dispatcher records it as `bad-plan`)\n'
```

expect: plan-validation has no channel for an item it could not measure

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-27 08:59:34Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-27 · triage · result=ok

Reproduced. `pipeline/stages/plan-validation.md` names neither "unverified"
nor `[readonly] allow` anywhere in its text.

Added `tests/test_stages.py::test_plan_validation_can_mark_an_item_unverified`,
asserting both strings appear in the stage prompt. It fails today with
`AssertionError: plan-validation has no channel for an item it could not measure`.
Committed at 7398533.

This is a `chore`: the fix is two additions to
`pipeline/stages/plan-validation.md` alone -- an "unverified" item type with
its scoring rule, and a line pointing at `[readonly] allow` in
`.project/pipeline.toml`. No other file needs to change; `readonly_allow()`
and `readonly_rules()` already exist and are untouched by this ticket.

files_declared: pipeline/stages/plan-validation.md

### 2026-08-27 16:16:48Z · triage · session · session=fb98a79e-41ad-429d-9806-3633e32da240

`triage` ran as session `fb98a79e-41ad-429d-9806-3633e32da240`
- replay: `claude --resume fb98a79e-41ad-429d-9806-3633e32da240`
- log: `.project/logs/TICKET-070-triage-fb98a79e.log`

### 2026-08-27 16:16:48Z · triage · transition · to=implementing · result=chore · marker=yes

**triage -> implementing** (result: `chore`)

✓ reproduced with a failing test on plan-validation.md missing "unverified" and "[readonly] allow"; fix is a one-file prompt edit

### 2026-08-27 · implementing · result=ok

Todo:
1. Add an `unverified` item channel to `pipeline/stages/plan-validation.md` -- done
2. Point the prompt at `[readonly] allow` in `.project/pipeline.toml` -- done

Edited `pipeline/stages/plan-validation.md`: added a paragraph telling the
stage to mark an unmeasurable item `unverified` and state what it would have
run, and that `unverified` items do not count against the plan in the
pass/fail decision. Added a paragraph pointing at `[readonly] allow` in
`.project/pipeline.toml` for a project-specific read-only command, instead of
working around the guard. No change to `readonly_rules()` or `readonly_allow()`.

`uv run --group dev pytest -q tests/test_stages.py::test_plan_validation_can_mark_an_item_unverified`
passes. Full `tests/test_stages.py`: `26 passed`. Committed at ac8e203.

### 2026-08-27 16:18:01Z · implementing · session · session=d1cf7ce9-ce11-44cd-8efd-f33ad9e31aa5

`implementing` ran as session `d1cf7ce9-ce11-44cd-8efd-f33ad9e31aa5`
- replay: `claude --resume d1cf7ce9-ce11-44cd-8efd-f33ad9e31aa5`
- log: `.project/logs/TICKET-070-implementing-d1cf7ce9.log`

### 2026-08-27 16:18:01Z · implementing · transition · to=quick-review · result=ok · marker=yes

**implementing -> quick-review** (result: `ok`)

✓ added an unverified-item channel and a [readonly] allow pointer to pipeline/stages/plan-validation.md; failing test now passes

### 2026-08-27 · quick-review · result=ok

1. Test fails without the diff, and the test triage is unchanged. `git diff main...HEAD -- tests/test_stages.py` shows `test_plan_validation_can_mark_an_item_unverified` added, byte-identical to the version committed at 7398533 (`git diff 7398533 HEAD -- tests/test_stages.py` is empty). `uv run --group dev pytest -q tests/test_stages.py::test_plan_validation_can_mark_an_item_unverified` passes against current HEAD; `## Reproduction` recorded the same test failing before the fix with `AssertionError: plan-validation has no channel for an item it could not measure`.

2. No unnamed file touched. `git diff --name-only main...HEAD` lists two files: `pipeline/stages/plan-validation.md`, named in `## Summary` ("pipeline/stages/plan-validation.md is the only file changed") and `## Reproduction`; and `tests/test_stages.py`, named in `## Reproduction` ("Added tests/test_stages.py::test_plan_validation_can_mark_an_item_unverified").

### 2026-08-27 16:18:43Z · quick-review · session · session=192a0797-7f58-4352-8e50-039989705f05

`quick-review` ran as session `192a0797-7f58-4352-8e50-039989705f05`
- replay: `claude --resume 192a0797-7f58-4352-8e50-039989705f05`
- log: `.project/logs/TICKET-070-quick-review-192a0797.log`

### 2026-08-27 16:18:43Z · quick-review · transition · to=verifying · result=ok · marker=yes

**quick-review -> verifying** (result: `ok`)

✓ test fails without the diff (triage unchanged since 7398533), and the diff touches only the two files the ticket names

### 2026-08-27 16:19:02Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 16:19:03Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/070


Current branch ticket/070 is up to date.
Already up to date.
Updating e8d55e6..ac8e203
Fast-forward
 pipeline/stages/plan-validation.md | 14 +++++++++++++-
 tests/test_stages.py               | 13 +++++++++++++
 2 files changed, 26 insertions(+), 1 deletion(-)

```

### 2026-08-27 16:19:03Z · merging · decision

no `## Decisions` section -- nothing recorded for future planning agents to find
