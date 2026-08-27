---
id: TICKET-064
stage: done
class: bugfix
branch: ticket/064
test_file: tests/test_gate.py::test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass
files_declared:
- pipeline/core/gate.py
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
  id: 14150210-728e-481b-bfec-be47fd106d5b
  log: .project/logs/TICKET-064-quick-review-14150210.log
cheap_route_head: b4c596d6ab98d2bc5eb28a0efdb69a812653a8ac
---

## Summary

gate reads a test command that ran nothing as a passing repro

`gate()` (`pipeline/core/gate.py`) runs the project's `test_one` and treats
exit 0 as "the test passes, so it is not a reproduction". Exit 0 also means
"the runner's filter matched nothing and it ran zero tests" -- a config whose
selector does not fit the project. The gate cannot tell those apart, so a
misconfigured project has every ticket bounced at `plan-validation` with a
finding blaming the ticket.

The fail branch immediately below already guards the mirror image of this, with
the reasoning that applies here (`pipeline/core/gate.py:216`):

    elif node not in out:
        # a missing dependency or an import error exits non-zero too, and
        # looks exactly like a failing test unless you check for the name

Reproduce with a `test_one` that exits 0 without ever naming the test, which is
what any runner does when its filter matches nothing:

    test_one = "true"                        # in .project/pipeline.toml

    >>> ok, findings = gate(project, "TICKET-001")
    # findings says: `test_thing.py::test_broken` PASSES -- it must fail
    #                before implementation

Expected: when `test_one` exits 0 and the test's name never appears in its
output, the finding says the command did not run that test at all -- a config
error -- rather than asserting the test passes. The same distinction the fail
branch already makes. `_base_findings()` runs the same command against a
checkout of base and needs the same check.

The exact string a test should assert on today is `PASSES -- it must fail
before implementation`, produced by a `test_one` that never mentions the test.

## Reproduction

`tests/test_gate.py::test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`

Command: `uv run --group dev pytest -q tests/test_gate.py::test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`

Failure:
```
AssertionError: ['`test_thing.py::test_broken` PASSES -- it must fail before implementation']
assert not True
 +  where True = any(<generator object ...>)
```

expect: PASSES -- it must fail before implementation

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

### 2026-08-27 · triage

Reproduced. `gate()` (`pipeline/core/gate.py:216`, branch run) and
`_base_findings()` (`pipeline/core/gate.py:144`, base run) both check only
`code == 0` before reporting "PASSES", unlike the `elif node not in out`
branch right below each, which already guards the mirror case. A `test_one`
that exits 0 without ever naming the test -- exactly what a runner does when
its filter matches zero tests -- is misread as a passing reproduction.

Added `tests/test_gate.py::test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`,
using `test_one = "true"`. It fails with:
`['`test_thing.py::test_broken` PASSES -- it must fail before implementation']`,
the exact string the ticket names. Committed at `b4c596d`.

result: chore. Fix touches only `pipeline/core/gate.py`: add a `node not in
out` check before both "PASSES" findings (branch at line ~216, base at line
~148), mirroring the existing `elif node not in out` pattern already present
in both functions. No design choice left -- the pattern to copy is already
in the file twice.

### 2026-08-27 09:00:56Z · triage · session · session=a3136902-bb6a-48ff-b879-6e10e8c273e2

`triage` ran as session `a3136902-bb6a-48ff-b879-6e10e8c273e2`
- replay: `claude --resume a3136902-bb6a-48ff-b879-6e10e8c273e2`
- log: `.project/logs/TICKET-064-triage-a3136902.log`

### 2026-08-27 09:00:56Z · triage · transition · to=implementing · result=chore · marker=yes

**triage -> implementing** (result: `chore`)

✓ reproduced gate misreading a zero-match test_one as a pass; fix is a two-line check in pipeline/core/gate.py mirroring the existing node-not-in-out pattern

### 2026-08-27 · implementing

Todo (from `## Summary`, no `## Plan` -- cheap route):
1. Guard the branch-run PASSES finding (`gate()`, line ~218) with `node in out`. Done.
2. Guard the base-run PASSES finding (`_base_findings()`, line ~149) the same way. Done.

Both `code == 0` branches now split into `code == 0 and node in out` (real
pass) versus `code == 0` alone (selector matched nothing, config error). The
new finding text: `` `{test}` exited 0 but its name never appears in the
output -- the selector matched nothing, not a passing test``, and the base
equivalent naming `base` instead. Mirrors the existing `elif node not in out`
pattern already in both functions, per triage's chore call.

`tests/test_gate.py::test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`
now passes (was RED with the ticket's exact string
`` `test_thing.py::test_broken` PASSES -- it must fail before implementation``,
confirmed before the fix). Full suite: `344 passed`. Ran
`uv run --group dev pytest -q tests/test_gate.py` (40 passed) and
`uv run --group dev pytest -q` (344 passed) after the fix.

Committed at `ae3b53b`, on top of triage's `b4c596d`. Only file touched:
`pipeline/core/gate.py`. No new test file -- the ticket's own repro test,
already committed by triage, is the coverage; nothing else in the diff needs
new cases since both changed branches are exercised by existing tests plus
the new one.

### 2026-08-27 09:01:55Z · implementing · session · session=f24924e5-a10f-41da-929b-5dbf8adc5316

`implementing` ran as session `f24924e5-a10f-41da-929b-5dbf8adc5316`
- replay: `claude --resume f24924e5-a10f-41da-929b-5dbf8adc5316`
- log: `.project/logs/TICKET-064-implementing-f24924e5.log`

### 2026-08-27 09:01:55Z · implementing · transition · to=quick-review · result=ok · marker=yes

**implementing -> quick-review** (result: `ok`)

✓ guarded both PASSES findings in gate.py with node-in-out, mirroring the existing pattern; repro test now green, full suite 344 passed

### 2026-08-27 · quick-review

1. Test fails without the diff, and yes without it. `git diff 0300869...HEAD -- tests/test_gate.py` shows only an addition (triage's commit) of `test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`; no line in it changed after triage committed it. Ran `uv run --group dev pytest -q tests/test_gate.py::test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`: `1 passed in 0.03s`.

2. No unnamed file. `git diff --name-only 0300869...HEAD` -- base found via `git merge-base main HEAD` -- lists `pipeline/core/gate.py` and `tests/test_gate.py`. `## Summary` names `pipeline/core/gate.py`: "Fix touches only `pipeline/core/gate.py`". `## Reproduction` names `tests/test_gate.py::test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`. Both files are named.

result: ok

### 2026-08-27 09:02:27Z · quick-review · session · session=14150210-728e-481b-bfec-be47fd106d5b

`quick-review` ran as session `14150210-728e-481b-bfec-be47fd106d5b`
- replay: `claude --resume 14150210-728e-481b-bfec-be47fd106d5b`
- log: `.project/logs/TICKET-064-quick-review-14150210.log`

### 2026-08-27 09:02:27Z · quick-review · transition · to=verifying · result=ok · marker=yes

**quick-review -> verifying** (result: `ok`)

✓ repro test unchanged since triage's commit and passes; diff touches only pipeline/core/gate.py and tests/test_gate.py, both named in Summary/Reproduction

### 2026-08-27 09:02:46Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 09:02:46Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/064


Current branch ticket/064 is up to date.
Already up to date.
Updating 0300869..ae3b53b
Fast-forward
 pipeline/core/gate.py | 13 +++++++++++--
 tests/test_gate.py    | 13 +++++++++++++
 2 files changed, 24 insertions(+), 2 deletions(-)

```

### 2026-08-27 09:02:46Z · merging · decision

no `## Decisions` section -- nothing recorded for future planning agents to find
