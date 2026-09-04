---
id: TICKET-112
stage: done
class: bugfix
branch: ticket/112
test_file: tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
files_declared:
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 0
  plan_files: 2
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: quick-review
  id: 3450d979-0768-419e-952f-fb3d8d32ccd5
  replay: claude --resume 3450d979-0768-419e-952f-fb3d8d32ccd5
  log: .project/logs/TICKET-112-quick-review-3450d979.log
  cost_usd: 0.3564110000000001
cheap_route_head: e2c8c320207e1655cec4eba5a7793ee10ceb5e31
---

## Summary

Fixed: `finish()` no longer charges `no_result` when `terminal_reason ==
"api_error"` (a stage the API refused, e.g. 529 overloaded).

`pipeline/daemon/supervisor.py:1247`, `finish()`, `res is None` branch: added
an `api_error` arm beside the existing `budget_exhausted` one. It increments
its own `counters["api_errors"]` (not `no_result`), releases the lease and
respawns, and only escalates once `api_errors >= MAX_ATTEMPTS` (2) --
matching how `budget_exhausted` already got its own accounting instead of
sharing `no_result`'s.

Proof: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result`
(added by `triage`, commit `e2c8c32`) failed RED (`no_result` == 1, expected
0) before the fix and passes GREEN after. Full `tests/test_dispatch.py`: 87
passed. Fix commit: `6867a90`.

Not done, out of scope for this cheap-route fix (no `## Plan` scoped them
in): a back-off delay before the respawn using `retry_delay_ms` from the
`api_retry` stream line, and quoting the API's own error message in the
eventual escalation. Both need `pipeline/stream/events.py::parse()` to stop
dropping `api_retry` fields -- a wider change than the counter fix this
ticket's test proves. Left as suggestions for a future ticket if wanted.

`quick-review`: `ok`. Test confirmed RED at `cheap_route_head` (e2c8c32)
structurally -- the fix's `api_error` arm did not exist there, so the run
fell into the `no_result` charge the test rejects -- and the test file is
unchanged since. Diff touches only the two files `## Summary` names.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-09-03 16:33:31Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-03 16:35:16Z · triage · session · session=ef36a67e-acef-4c16-a546-465c697ae7b9

`triage` ran as session `ef36a67e-acef-4c16-a546-465c697ae7b9`
- replay: `claude --resume ef36a67e-acef-4c16-a546-465c697ae7b9`
- log: `.project/logs/TICKET-112-triage-ef36a67e.log`

### 2026-09-03 16:35:16Z · triage · transition · to=implementing · result=chore · marker=yes

**triage -> implementing** (result: `chore`)

✓ reproduced api_error burning no_result; added failing test, small fix confined to finish()'s terminal_reason branch

### 2026-09-03 · implementing · todo

1. Verify RED: `test_an_api_error_kill_is_not_charged_to_no_result` fails today. Done.
2. Add an `api_error` arm in `finish()` beside `budget_exhausted`, charging its own `api_errors` counter instead of `no_result`, bounded at `MAX_ATTEMPTS`. Done.
3. Verify GREEN: new test passes, `tests/test_dispatch.py` full suite passes. Done.
4. Commit. Done.

### 2026-09-03 · implementing · note

Fixed `pipeline/daemon/supervisor.py:1247` (`finish()`): a `res is None` run
with `terminal_reason == "api_error"` now increments its own
`counters["api_errors"]` instead of `no_result`, and respawns (release lease,
no escalation) until `api_errors >= MAX_ATTEMPTS`, matching the ticket's
`test_an_api_error_kill_is_not_charged_to_no_result` (commit e2c8c32).
Confirmed RED before the fix (`no_result` == 1 after one call, test asserted
0), GREEN after: `tests/test_dispatch.py` 87 passed.

Left the two other suggestions in `## Summary` undone: no back-off delay
before the respawn, and the eventual escalation still names `api_error`
generically rather than quoting the API's own message. Both need
`parse()` to carry `retry_delay_ms`/the result text, which is a wider change
than the counter fix the ticket's own test proves; they were marked
"suggestions only" and no `## Plan` scoped them in.

Commit: `6867a90` "fix: don't charge no_result on an api_error terminal_reason (TICKET-112)".

### 2026-09-03 16:37:05Z · implementing · session · session=8f3b3528-c185-46d4-a25b-f53c9c962de0

`implementing` ran as session `8f3b3528-c185-46d4-a25b-f53c9c962de0`
- replay: `claude --resume 8f3b3528-c185-46d4-a25b-f53c9c962de0`
- log: `.project/logs/TICKET-112-implementing-8f3b3528.log`
- cost: $0.45 of a $8 cap
- tokens: 7,897 out (1,895 thinking) · 44 in · 957,850 cache read · 43,950 cache write

### 2026-09-03 16:37:05Z · implementing · transition · to=quick-review · result=ok · marker=yes

**implementing -> quick-review** (result: `ok`)

✓ finish() no longer charges no_result on terminal_reason=api_error; new counter api_errors bounds respawn at MAX_ATTEMPTS

### 2026-09-03 · quick-review · note

1. Does the committed test fail without this diff? Yes. `git diff
cheap_route_head(e2c8c32)..HEAD -- tests/test_dispatch.py` produced no
output: the test is byte-identical to the version `triage` committed RED, so
the recorded failure still proves something. The guard blocks a direct
re-run (`git worktree add`, `mkdir`, `rm`, command substitution all refused
by `dangerous-commands.py` for this read-only stage), so RED was confirmed
structurally instead: `git diff e2c8c32..HEAD -- pipeline/daemon/supervisor.py`
shows the fix inserts a new `if rec.get("terminal_reason") == "api_error":`
arm above the existing `no_result`-charging code. At e2c8c32 that arm does
not exist, so a run with `terminal_reason=api_error` falls straight into the
`no_result` charge the test asserts against -- the test fails there.

2. Does the diff touch a file the ticket did not name? No. `git diff
--name-only 3c6643f..HEAD` lists exactly `pipeline/daemon/supervisor.py` and
`tests/test_dispatch.py`. `## Summary` names both:
"`pipeline/daemon/supervisor.py:1247`, `finish()`, `res is None` branch:
added an `api_error` arm" and "`tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result`
(added by `triage`, commit `e2c8c32`)".

result: ok

### 2026-09-03 16:39:11Z · quick-review · session · session=3450d979-0768-419e-952f-fb3d8d32ccd5

`quick-review` ran as session `3450d979-0768-419e-952f-fb3d8d32ccd5`
- replay: `claude --resume 3450d979-0768-419e-952f-fb3d8d32ccd5`
- log: `.project/logs/TICKET-112-quick-review-3450d979.log`
- cost: $0.36 of a $2 cap
- tokens: 8,074 out (4,307 thinking) · 34 in · 652,980 cache read · 35,992 cache write

### 2026-09-03 16:39:11Z · quick-review · transition · to=verifying · result=ok · marker=yes

**quick-review -> verifying** (result: `ok`)

✓ test fails without the diff (structural check) and diff touches only the two named files

### 2026-09-03 16:40:14Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-04 01:48:48Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/112


Rebasing (1/2)Rebasing (2/2)Successfully rebased and updated refs/heads/ticket/112.
Already up to date.
Updating 7d2b23b..a63085d
Fast-forward
 pipeline/daemon/supervisor.py | 16 ++++++++++++++++
 tests/test_dispatch.py        | 25 +++++++++++++++++++++++++
 2 files changed, 41 insertions(+)

```

### 2026-09-04 01:48:48Z · merging · decision

no `## Decisions` section -- nothing recorded for future planning agents to find
