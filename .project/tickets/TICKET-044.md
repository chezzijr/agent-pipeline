---
id: TICKET-044
stage: done
class: bugfix
branch: ticket/044
test_file: tests/test_config.py::test_an_uncommitted_stage_extra_must_not_reach_stage_extra
files_declared:
- pipeline/core/config.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: quick-review
  id: cdb4c7e2-15de-40e3-ab44-778011c1d10f
  log: .project/logs/TICKET-044-quick-review-cdb4c7e2.log
---

## Summary

Fixed. `stage_extra()` (pipeline/core/config.py) now reads `.project/stages/<stage>.extra.md` through `head_file()`, falling back to disk only when git has no copy at all -- mirrors `project_config()`'s HEAD-then-disk-fallback exactly. An uncommitted edit to a `.extra.md` file no longer reaches the next spawn's composed prompt.

Reproducing test tests/test_config.py::test_an_uncommitted_stage_extra_must_not_reach_stage_extra passes. Full tests/test_config.py and tests/test_worktree.py pass (12 tests). Committed at a733a56.

quick-review: ok. Test fails without the diff -- old code read straight off disk with no `head_file()` call. Diff touches only `pipeline/core/config.py` and `tests/test_config.py`, both named in Summary/Reproduction.

## Reproduction

test: tests/test_config.py::test_an_uncommitted_stage_extra_must_not_reach_stage_extra
command: uv run --group dev pytest -q tests/test_config.py::test_an_uncommitted_stage_extra_must_not_reach_stage_extra
output:
    AssertionError: assert 'INJECTED-9137' not in 'INJECTED-9137\n'
expect: AssertionError: assert 'INJECTED-9137' not in 'INJECTED-9137\n'

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-24 08:05:50Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 · triage · finding

**triage** (result: `chore`)

Reproduced. `stage_extra()` (pipeline/core/config.py) reads `.project/stages/<stage>.extra.md` straight off disk instead of through `head_file()`, unlike `project_config()`. An uncommitted edit therefore reaches the next spawn's composed prompt with no commit, no diff, no snapshot and no gate.

Test: tests/test_config.py::test_an_uncommitted_stage_extra_must_not_reach_stage_extra, committed at 3523957.
Fails with: AssertionError: assert 'INJECTED-9137' not in 'INJECTED-9137\n'

Fix is a chore: mirror `project_config()`'s HEAD-then-disk-fallback exactly, applied to `.project/stages/<stage>.extra.md` instead of `.project/pipeline.toml`. One file, pipeline/core/config.py, a few lines, no design choice left.

### 2026-08-24 08:11:31Z · triage · session · session=5ad2f9b1-b5d5-4493-8d36-a924b65097cf

`triage` ran as session `5ad2f9b1-b5d5-4493-8d36-a924b65097cf`
- replay: `claude --resume 5ad2f9b1-b5d5-4493-8d36-a924b65097cf`
- log: `.project/logs/TICKET-044-triage-5ad2f9b1.log`

### 2026-08-24 08:11:31Z · triage · transition · to=implementing · result=chore · marker=yes

**triage -> implementing** (result: `chore`)

✓ reproduced -- stage_extra() reads .project/stages/*.extra.md off disk instead of head_file(); fix mirrors project_config()s fallback, a few-line change

### 2026-08-24 · implementing · finding

**implementing** (result: `ok`)

Todo:
1. Confirm RED on tests/test_config.py::test_an_uncommitted_stage_extra_must_not_reach_stage_extra -- done
2. Fix stage_extra() in pipeline/core/config.py to read via head_file(), fall back to disk -- done
3. Confirm GREEN, run tests/test_config.py and tests/test_worktree.py -- done
4. Commit -- done

`stage_extra()` now calls `head_file(project, f".project/stages/{stage}.extra.md")`, falling back to `f.read_text()` off disk only when `head_file()` returns `None`. Mirrors `project_config()` exactly.

Verified RED: `AssertionError: assert 'INJECTED-9137' not in 'INJECTED-9137\n'`, matching the ticket's reproduction.
Verified GREEN: `tests/test_config.py` 4 passed, `tests/test_worktree.py` 8 passed (12 total, no regressions).
Committed at a733a56: `fix(TICKET-044): read stage_extra() from HEAD, falling back to disk`.

No design choice left, per triage. No files touched beyond pipeline/core/config.py.

### 2026-08-24 08:12:29Z · implementing · session · session=3382aa53-0325-4d8e-9cfe-e7d433171c6a

`implementing` ran as session `3382aa53-0325-4d8e-9cfe-e7d433171c6a`
- replay: `claude --resume 3382aa53-0325-4d8e-9cfe-e7d433171c6a`
- log: `.project/logs/TICKET-044-implementing-3382aa53.log`

### 2026-08-24 08:12:29Z · implementing · transition · to=quick-review · result=ok · marker=yes

**implementing -> quick-review** (result: `ok`)

✓ fixed stage_extra() to read via head_file() with disk fallback, mirroring project_config(); reproducing test and full test_config.py/test_worktree.py pass

### 2026-08-24 · quick-review · finding

**quick-review** (result: `ok`)

1. Does the committed test fail without this diff? Yes. Ran `git diff 3523957 HEAD -- tests/test_config.py`, no output -- test unchanged since triage committed it. Ran `git diff 47fed3b...HEAD -- pipeline/core/config.py`: old `stage_extra()` read `f.read_text()` straight off disk with no `head_file()` call, so the test's uncommitted `INJECTED-9137` write would reach the return value and fail `assert "INJECTED-9137" not in stage_extra(...)`.

2. Does the diff touch a file the ticket did not name? No. `git diff --name-only 47fed3b...HEAD` lists `pipeline/core/config.py` and `tests/test_config.py`. `## Reproduction` names `pipeline/core/config.py` ("`stage_extra()` (pipeline/core/config.py) now reads...") and `test_file: tests/test_config.py::test_an_uncommitted_stage_extra_must_not_reach_stage_extra`; `## Summary` line 6/8 name both.

### 2026-08-24 08:13:09Z · quick-review · session · session=cdb4c7e2-15de-40e3-ab44-778011c1d10f

`quick-review` ran as session `cdb4c7e2-15de-40e3-ab44-778011c1d10f`
- replay: `claude --resume cdb4c7e2-15de-40e3-ab44-778011c1d10f`
- log: `.project/logs/TICKET-044-quick-review-cdb4c7e2.log`

### 2026-08-24 08:13:09Z · quick-review · transition · to=verifying · result=ok · marker=yes

**quick-review -> verifying** (result: `ok`)

✓ test fails without the diff (old code read off disk, no head_file()); diff touches only config.py and test_config.py, both named in the ticket

### 2026-08-24 08:13:22Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 08:13:23Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/044


Already up to date.
error: Your local changes to the following files would be overwritten by merge:
	tests/test_config.py
Please commit your changes or stash them before you merge.
Aborting
Updating 47fed3b..a733a56

```

### 2026-08-24 08:26:47Z · human · note

**resumed** by human -> `merging`, reset []

### 2026-08-24 08:27:06Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/044


Already up to date.
Updating 47fed3b..a733a56
Fast-forward
 pipeline/core/config.py | 14 ++++++++++----
 tests/test_config.py    | 17 ++++++++++++++++-
 2 files changed, 26 insertions(+), 5 deletions(-)

```

### 2026-08-24 08:27:06Z · merging · decision

no `## Decisions` section -- nothing recorded for future planning agents to find
