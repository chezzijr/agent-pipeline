---
id: TICKET-095
stage: done
class: bugfix
branch: ticket/095
test_file:
- tests/test_config.py::test_pinning_max_usd_without_scale_usd_warns
- tests/test_config.py::test_pinning_max_usd_with_scale_usd_does_not_warn
files_declared:
- pipeline/core/config.py
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
  id: 721b5998-9012-4e2b-9287-6df763f84762
  log: .project/logs/TICKET-095-quick-review-721b5998.log
  cost_usd: 0.27113699999999996
cheap_route_head: 1e49618c66b44f052a7822cd569026b6b62c5a37
---

## Summary

a stage's own `max_usd` silently disables size-scaling with no warning

`cap_config()` decides whether a stage's dollar cap scales with plan size:

    # pipeline/core/config.py:77-79
    want = override.get("scale_usd")
    if want is None:
        want = stage in USD_SCALED and "max_usd" not in override

So an operator who sets `max_usd` on `review`, `quick-review` or `holistic-review`
(the three in `USD_SCALED`) to RAISE the cap also turns scaling off -- the pinned
number then applies to a 40-step plan exactly as to a 3-step one. The rule is
documented (`README.md:532`, the `pipeline-config` skill) and correct; what is
missing is any signal at the moment it takes effect. The failure shows up later as
a budget kill on a big ticket, which reads as "the cap is too low", not as "your
own `max_usd` opted this stage out of scaling".

Expected: one printed line when a stage sets `max_usd` without `scale_usd`, naming
both the pinned cap and the scaling it turned off, so the operator can add
`scale_usd = true` if that was not the intent. Behaviour does not change.
Falsifiable: a project config with `[stages.review] max_usd = 9` must produce that
line; the same config with `scale_usd = true` must not.

Triage: reproduced. `cap_config()` prints nothing in the `max_usd`-without-
`scale_usd` case. Fix is one line in `pipeline/core/config.py`: `chore`, no
plan needed. See `## Reproduction` and `## Thread` for the two tests.

Implemented: `cap_config()` now prints `"<stage>: max_usd=<n> is set without
scale_usd, so this stage will not scale its cap with plan size. Add
scale_usd = true if that was not the intent."` when a `USD_SCALED` stage's
own `max_usd` disables scaling. Both tests pass. Committed as `e2c461c`.

Quick-review: ok, both files touched are named and the recorded failure
still holds. See `## Thread` for the two answers.

## Reproduction

`tests/test_config.py::test_pinning_max_usd_without_scale_usd_warns` fails:

    AssertionError: expected a warning naming the pinned max_usd=9 and the
    scaling it disabled, got: ''
    assert ('max_usd' in '')

expect: assert ('max_usd' in '')

Run: `uv run --group dev pytest -q tests/test_config.py::test_pinning_max_usd_without_scale_usd_warns`

`tests/test_config.py::test_pinning_max_usd_with_scale_usd_does_not_warn` passes
today, confirming `cap_config()` emits nothing in either case (correct
absence for `scale_usd = true`, missing presence otherwise).

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-29 03:52:45Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 · triage · result=chore

Confirmed: `cap_config()` (pipeline/core/config.py:70-79) prints nothing when
`max_usd` on a `USD_SCALED` stage disables scaling. Added two tests to
`tests/test_config.py`:

1. `test_pinning_max_usd_without_scale_usd_warns` -- fails today, expecting
   `"max_usd"` and `"9"` in stdout after `cap_config("review", ..., {"max_usd": 9})`
   with no `scale_usd`. Got `''`.
2. `test_pinning_max_usd_with_scale_usd_does_not_warn` -- passes today
   (confirms no false-positive warning when `scale_usd = true`).

Committed as `1e49618`. Fix is one line: a `print()` in `cap_config()` when
`want` is `False` because of the `"max_usd" not in override` branch,
naming the stage's pinned `max_usd` and that scaling is off. Only file
touched: `pipeline/core/config.py`.

### 2026-08-29 04:57:49Z · triage · session · session=5382735e-52a8-4892-ad1d-1f312c66e516

`triage` ran as session `5382735e-52a8-4892-ad1d-1f312c66e516`
- replay: `claude --resume 5382735e-52a8-4892-ad1d-1f312c66e516`
- log: `.project/logs/TICKET-095-triage-5382735e.log`
- cost: $0.27 of a $3 cap
- tokens: 3,732 out (128 thinking) · 30 in · 545,999 cache read · 31,352 cache write

### 2026-08-29 04:57:49Z · triage · transition · to=implementing · result=chore · marker=yes

**triage -> implementing** (result: `chore`)

✓ reproduced missing warning in cap_config() with a failing test; fix is a one-line print in pipeline/core/config.py

### 2026-08-29 · implementing

Todo:
1. Verify RED: run `test_pinning_max_usd_without_scale_usd_warns` -- done, failed as expected (`got: ''`).
2. Add the print in `cap_config()` (`pipeline/core/config.py`) naming the pinned `max_usd` and that scaling is off -- done.
3. Verify GREEN: both new tests plus `tests/test_config.py` full suite -- done, 25 passed.
4. Run `tests/test_daemon.py` for the one caller in `supervisor.py` -- done, 65 passed.
5. Commit -- done, `e2c461c`.

No plan file existed (chore route); worked from `## Summary` and `## Reproduction`. Only `pipeline/core/config.py` touched, matching the triage's stated fix location. No new test files -- the two tests already existed from triage.

### 2026-08-29 04:58:39Z · implementing · session · session=8d538b96-183c-4377-bbbe-fd9113732715

`implementing` ran as session `8d538b96-183c-4377-bbbe-fd9113732715`
- replay: `claude --resume 8d538b96-183c-4377-bbbe-fd9113732715`
- log: `.project/logs/TICKET-095-implementing-8d538b96.log`
- cost: $0.27 of a $8 cap
- tokens: 3,296 out (45 thinking) · 32 in · 575,644 cache read · 30,196 cache write

### 2026-08-29 04:58:39Z · implementing · transition · to=quick-review · result=ok · marker=yes

**implementing -> quick-review** (result: `ok`)

✓ added the print() in cap_config() naming pinned max_usd and the scaling it disabled; both tests pass

### 2026-08-29 · quick-review

1. Test diff unchanged from triage's commit. `git diff ae2bf7080447135401809151ad9a96a752fefc7b...HEAD -- tests/test_config.py` shows both `test_pinning_max_usd_without_scale_usd_warns` and `test_pinning_max_usd_with_scale_usd_does_not_warn` as pure additions, byte-identical to the triage entry's description. `## Reproduction`'s recorded failure (`got: ''`) still applies to this exact test. Both pass now: `uv run --group dev pytest -q tests/test_config.py::test_pinning_max_usd_without_scale_usd_warns tests/test_config.py::test_pinning_max_usd_with_scale_usd_does_not_warn` -> `2 passed in 0.08s`.

2. No unnamed file. `git diff --name-only ae2bf7080447135401809151ad9a96a752fefc7b...HEAD` -> `pipeline/core/config.py`, `tests/test_config.py`. Both named: Summary says "Only file touched: `pipeline/core/config.py`" (implementing) and "Fix is one line in `pipeline/core/config.py`" (triage); triage's thread entry says "Added two tests to `tests/test_config.py`".

### 2026-08-29 04:59:46Z · quick-review · session · session=721b5998-9012-4e2b-9287-6df763f84762

`quick-review` ran as session `721b5998-9012-4e2b-9287-6df763f84762`
- replay: `claude --resume 721b5998-9012-4e2b-9287-6df763f84762`
- log: `.project/logs/TICKET-095-quick-review-721b5998.log`
- cost: $0.27 of a $2 cap
- tokens: 4,091 out (219 thinking) · 32 in · 552,520 cache read · 29,655 cache write

### 2026-08-29 04:59:46Z · quick-review · transition · to=verifying · result=ok · marker=yes

**quick-review -> verifying** (result: `ok`)

✓ test diff unmodified from triage's commit; both touched files named in Summary/Reproduction

### 2026-08-29 05:00:21Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 05:00:22Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/095


Current branch ticket/095 is up to date.
Already up to date.
Updating ae2bf70..e2c461c
Fast-forward
 pipeline/core/config.py |  7 +++++++
 tests/test_config.py    | 29 +++++++++++++++++++++++++++++
 2 files changed, 36 insertions(+)

```

### 2026-08-29 05:00:22Z · merging · decision

no `## Decisions` section -- nothing recorded for future planning agents to find
