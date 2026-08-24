---
id: TICKET-042
stage: done
class: bugfix
branch: ticket/042
test_file: tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught
files_declared:
- pipeline/core/gate.py
- tests/test_gate.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 4425bad6-99d1-47d8-81eb-6e98f5992ccb
  log: .project/logs/TICKET-042-review-4425bad6.log
approved_by: chezzijr
approved_at: '2026-08-24T08:36:44.115790+00:00'
---

## Summary

acceptance criteria written as a numbered list are never checked for a test

The Tier A rule that every acceptance criterion must name a test only inspects
lines that begin with `-` or `*`:

    gate.py:273  for line in [l for l in crit.splitlines()
                              if l.strip().startswith(("-", "*"))]

A `## Acceptance criteria` written as `1.` or `1)` yields zero lines to that
loop, so the check passes vacuously. Seen on main at 783170c; TICKET-039 passed
the gate with four numbered criteria, none of them checked.

Expected: a criterion is a criterion whether it is written `- `, `* `, `1. ` or
`1) `, and a numbered criterion naming no test produces `acceptance criterion
names no test:` exactly as a bulleted one does.

Triage reproduced it and committed the failing test at e713c0d:
`tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught`
fails with `AssertionError: []`. See `## Reproduction`.

Planning wrote the plan twice; no questions. The fix adds
`CRIT_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])")` to `pipeline/core/gate.py`
and uses it in place of the `startswith` filter at `gate.py:273`, plus one new
test for the `1)` form and for numbered criteria that do name a test. Files:
`pipeline/core/gate.py`, `tests/test_gate.py`.

Plan-validation rejected the first plan on one acceptance criterion, not on the
fix: the running gate is an installed copy that predates 2b167c8, so it does
not accept a bare `pytest`. Every criterion now names `tests/test_gate.py` or
`tests/`. See the second `planning` thread entry.

Plan-validation then passed the second plan on all eight items: the plan fixes
the selector, complies with DEC-030 and the DEC-017/DEC-018 import constraint,
stays inside two files, and states a fallback for the filter swap
(`\d+[.)]\s`). `gate.py:273` is the only copy of the filter in the package, and
both suite callers of `gate()` use the bulleted `FIXTURE`, so the regression
surface is the criteria block alone. Implementation may proceed on the plan as
written; the line numbers in it match the worktree.

Related: TICKET-043 is the same class of hole in a different rule -- a
mechanical check trusted as though it were total. This one is about formatting;
that one is about scope.

Implementation executed the plan as written. `CRIT_ITEM_RE` now matches `-`,
`*`, `1.` and `1)` at the criteria filter, `gate.py:280` after the new
constant; both new tests and the whole suite pass (248 tests). Committed at
`42a83a6`.

Review passed the delta on the first pass, no blocking findings. The diff is
the plan and nothing else: two files, the finding string and test-shape regex
byte-for-byte unchanged, no branch-only import in the new test. All four
acceptance criteria pass -- `3 passed in 0.04s` for the named tests, `248
passed in 10.38s` for the suite. Rebinding `CRIT_ITEM_RE` to the pre-fix
`r"^\s*[-*]"` in memory makes the new test fail with `AssertionError: []`, so
it is not vacuous. Two minor findings, neither blocking, are in the `review`
thread entry: the second half of the new test does not catch the over-fix its
docstring names, and the fix widens the fenced-block hole `## Decisions`
already records as out of scope.

## Reproduction

`tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught`

Command: `uv run --group dev pytest tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught -v`

Output:
```
AssertionError: []
assert (not True)
```

expect: AssertionError: []

The test writes an `## Acceptance criteria` of `1. code should be clean` (numbered,
names no test) and asserts `gate()` returns `not ok` with a `names no test`
finding. `gate()` returns `ok=True, failures=[]` instead -- the vacuous pass the
ticket reports, reproduced.

## Digest

Files touched: `pipeline/core/gate.py` (the check) and `tests/test_gate.py` (the tests).
Key function: `gate()` in `pipeline/core/gate.py`; the criteria check is its last block, at `gate.py:273-284`.
The filter is `for line in [l for l in crit.splitlines() if l.strip().startswith(("-", "*"))]`, and the finding string is `f"acceptance criterion names no test: {line.strip()}"`.
The test-shape regex on the next lines is `r"\bpytest\b|\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/"` with `re.I`; it stays exactly as is.
Entry point: `gate(project, tid, workdir=None)`, called by the dispatcher at `plan-validation`; tests call it directly as `gate(d, "TICKET-001")`.
The `## Plan` scan above already matches numbered markers with `re.match(r"^\s*\d+[.)]", line)` (`gate.py:247`). Reuse that marker syntax so the two scans agree.
Test fixture: `FIXTURE` in `tests/helpers.py` holds `## Acceptance criteria` followed by one bulleted criterion, `- ` plus `` `test_broken` `` plus ` passes`, and `project(body)` builds a throwaway project. Criteria tests replace that one line.
Gotcha (DEC-017, DEC-018): the gate copies `tests/test_gate.py` onto a checkout of base and imports it there. A new test must not import a branch-only name -- importing the new regex constant from `pipeline.core.gate` turns the base run into a collection error and blocks this ticket. Assert on the literal substring `names no test`, as every neighbouring test does.
Gotcha: today's bullet arm matches a prefix, not a marker plus space, so `**bold prose**` and `--- ` are checked. Requiring `\s` after the marker would stop checking lines the gate checks today. Keep the bullet arm a prefix match and add the numbered arm beside it.
Gotcha (found on the first plan-validation run, 2026-08-24): the dispatcher does not run this checkout's gate. It runs `/home/chezzijr/.local/share/uv/tools/pipeline/lib/python3.13/site-packages/pipeline/core/gate.py`, whose criteria regex is `r"\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/"` -- the pre-2b167c8 text, with no `\bpytest\b` arm. A criterion whose only test word is `pytest` draws `acceptance criterion names no test` there, and passes in this checkout. Write every criterion so it names `tests/` or a `tests/...::...` node; both copies accept that. The installed copy is stale against `main`; reinstalling it is outside this ticket.
The failing test `tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught` is already committed at e713c0d, at `tests/test_gate.py:138-143`.

## Decisions checked

Grep terms in `/home/chezzijr/proj/agent-pipeline/.project/decisions/`: `acceptance`, `criterion`, `names no test`, `numbered`, `list marker`, `Tier A`, `pytest`, `gate.py`.

DEC-030 is the one relevant record, and it is active (no `superseded-by:` line). It fixed the four `## Plan` findings and states: "`acceptance criterion names no test` has the same shape and is not touched." That is a scope note about TICKET-030, not a rule against changing the check, so this plan complies with DEC-030 rather than superseding it. Two of its rules bind this plan: the rule text lives in `pipeline/core/gate.py` and stays duplicated from `pipeline/stages/planning.md`, and `tests/test_gate.py` asserts on literal substrings, never on a constant imported from `pipeline.core.gate`.

DEC-017 and DEC-018 carry the same import constraint, cited in `## Digest`. DEC-026 (no Tier A gate on the chore route) is not relevant: this change only alters what the gate reports when it does run. DEC-041 does not touch `pipeline/core/gate.py`; the `\bpytest\b` arm landed at 2b167c8 with no decision record of its own.

## Plan

1. Add `test_numbered_criteria_are_checked_in_both_marker_forms` to `tests/test_gate.py`, directly after `test_a_numbered_acceptance_criterion_naming_no_test_is_caught` (ends at line 143), with a docstring saying it fails today because a `1)` criterion naming no test produces no finding, and that the second half guards against over-fixing.
2. Write that test in `tests/test_gate.py` as two halves in one function: first `d = project(FIXTURE.replace("- `test_broken` passes", "1) code should be clean"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert not ok and any("names no test" in f for f in failures), failures`, then `shutil.rmtree(d)`; second `d = project(FIXTURE.replace("- `test_broken` passes", "1. `tests/test_cache.py::test_evicts` passes\n2) `test_broken` passes"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert ok, failures`, then `shutil.rmtree(d)`.
3. Run `uv run --group dev pytest tests/test_gate.py -k numbered -v` and confirm both tests in `tests/test_gate.py` fail: the committed one with `AssertionError: []`, the new one on its first half with an empty `failures` list.
4. In `pipeline/core/gate.py`, add a module constant after `PLAN_FILE_RULE` (ends at line 36): `CRIT_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])")`, with a comment saying a criterion is a criterion in any list form, that the numbered markers are the same `\d+[.)]` the `## Plan` scan at `gate.py:247` accepts, and that the bullet arm stays a prefix match because requiring a space after `-`/`*` would stop checking the `**bold prose**` lines the gate checks today.
5. In `pipeline/core/gate.py` line 273, replace `for line in [l for l in crit.splitlines() if l.strip().startswith(("-", "*"))]:` with `for line in [l for l in crit.splitlines() if CRIT_ITEM_RE.match(l)]:`, and change nothing else in that block -- the test-shape regex, the `re.I` flag and the finding string stay byte-for-byte as they are.
6. Run `uv run --group dev pytest tests/test_gate.py -q` and confirm every test in `tests/test_gate.py` passes, `test_an_acceptance_criterion_must_name_something_test_shaped` included.
7. Run `uv run --group dev pytest -q` for the whole dispatcher suite and confirm it is green with the edits to `pipeline/core/gate.py` and `tests/test_gate.py` in place.
8. Commit `pipeline/core/gate.py` and `tests/test_gate.py` on `ticket/042` with the message `fix: the gate checks numbered acceptance criteria, not only bulleted ones`.

## Acceptance criteria

- `tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught` passes: `gate()` returns `ok=False` with a `names no test` finding for `1. code should be clean`.
- `tests/test_gate.py::test_numbered_criteria_are_checked_in_both_marker_forms` passes: the `1)` criterion naming no test produces a `names no test` finding, and numbered criteria naming a test return `ok=True`.
- `tests/test_gate.py::test_an_acceptance_criterion_must_name_something_test_shaped` still passes, which proves the bulleted path is unchanged.
- The whole dispatcher suite under `tests/` reports no failures: `uv run --group dev pytest -q`.

## Decisions

**The `## Acceptance criteria` scan matches four list markers: `-`, `*`, `1.` and `1)`.** `CRIT_ITEM_RE` in `pipeline/core/gate.py` is the one place that decides what a criterion line is. Before this, the filter was `startswith(("-", "*"))`, so a section written as a numbered list produced zero lines to check and the rule passed vacuously -- TICKET-039 shipped four numbered criteria, none of which the gate read. The numbered markers are spelled `\d+[.)]`, the same as the `## Plan` scan at `gate.py:247`; change the two together.

**The bullet arm is a prefix match, not a marker followed by whitespace.** `- ` is not required. Adding `\s` after the marker looks like a tidy-up and silently narrows the rule: `**bold prose**` and `--- ` are lines the gate checks today and would stop checking.

**Deliberately not fixed: the criteria scan does not consult `_fenced()`.** A `- ` line inside a fenced block in `## Acceptance criteria` is still read as a criterion, unlike in `## Plan`. That is the pre-existing behaviour and is outside this ticket; TICKET-043 covers the same class of hole in a different rule.

**Deliberately not fixed: a wrapped criterion is checked on its first line only.** The `## Plan` scan joins an indented continuation line onto the step above; the criteria scan does not. A criterion whose test name falls on its second line is reported as naming no test. Pre-existing, and unchanged by this ticket.

This closes the scope note in DEC-030 ("`acceptance criterion names no test` has the same shape and is not touched"). DEC-030 stays active for everything else it says.

## Rollback

Revert the commit from step 8 on `ticket/042`. It touches `pipeline/core/gate.py` and `tests/test_gate.py` only, and no data or state, so the revert restores the previous filter exactly. The visible effect of a revert: numbered acceptance criteria stop being checked again. If the fix over-reports -- a numbered line in `## Acceptance criteria` that is not a criterion draws a `names no test` finding -- the narrower repair is to keep `CRIT_ITEM_RE` and require whitespace after the numbered marker (`\d+[.)]\s`), which leaves the bulleted path untouched.

## Thread

### 2026-08-24 08:05:50Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 · triage · result=ok

Reproduced. `gate.py:273` filters `## Acceptance criteria` lines to only
`l.strip().startswith(("-", "*"))`, so a numbered criterion (`1.`, `1)`)
contributes zero lines to the `names no test` check regardless of content.

Confirmed with `git log -S "names no test" -- pipeline/core/gate.py`: the check
has never matched numbered lists.

Added `tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught`,
committed on `ticket/042` at e713c0d. It fails today with `AssertionError: []`
(`gate()` returns `ok=True`, no findings). See `## Reproduction`.

Fix touches `pipeline/core/gate.py` only: widen the `startswith` filter (or
switch to a regex) to also match `1.` / `1)` markers, same as the existing
`-`/`*` handling. This is `result: ok`, not `chore` -- the right implementation
(regex vs. tuple of prefixes, and whether to normalize other list markers too)
is a small design choice, not purely mechanical.

### 2026-08-24 08:09:23Z · triage · session · session=57d75ac1-d580-4f2d-bd25-609ce7d6c4e1

`triage` ran as session `57d75ac1-d580-4f2d-bd25-609ce7d6c4e1`
- replay: `claude --resume 57d75ac1-d580-4f2d-bd25-609ce7d6c4e1`
- log: `.project/logs/TICKET-042-triage-57d75ac1.log`

### 2026-08-24 08:09:23Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- numbered acceptance criteria bypass gate.py's `names no test` check; failing test committed at e713c0d

### 2026-08-24 · planning · result=ok

Plan written. Eight steps, two files: `pipeline/core/gate.py` and
`tests/test_gate.py`.

The fix adds `CRIT_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])")` and uses it
in place of `l.strip().startswith(("-", "*"))` at `gate.py:272`. The numbered
markers match the `## Plan` scan at `gate.py:248`. The bullet arm stays a
prefix match: adding `\s` after the marker would stop checking `**bold
prose**` and `--- `, which the gate checks today.

Scope: one subsystem, one check. Two things I found and did not plan, recorded
in `## Decisions`. First, the criteria scan does not consult `_fenced()`, so a
`- ` line inside a fenced block in `## Acceptance criteria` still reads as a
criterion; `## Plan` excludes fenced lines. Second, the scan does not join a
wrapped criterion's continuation line, so a criterion whose test name falls on
its second line is reported as naming no test. Both are pre-existing and
outside this ticket.

DEC-030 says `acceptance criterion names no test` "has the same shape and is
not touched" -- a scope note on TICKET-030, not a rule against this change.
DEC-017 and DEC-018 bind the new test: no import of a branch-only name, assert
on the literal `names no test`.

### 2026-08-24 08:13:45Z · planning · session · session=b1197c9a-ac5e-481c-bcf6-543b74da628e

`planning` ran as session `b1197c9a-ac5e-481c-bcf6-543b74da628e`
- replay: `claude --resume b1197c9a-ac5e-481c-bcf6-543b74da628e`
- log: `.project/logs/TICKET-042-planning-b1197c9a.log`

### 2026-08-24 08:13:45Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: CRIT_ITEM_RE replaces the `-`/`*` startswith filter at gate.py:272, plus one new test for the `1)` form

### 2026-08-24 08:13:57Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught` fails as required
```
== test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-042
configfile: pyproject.toml
collected 1 item

tests/test_gate.py F

=================================== FAILURES ===================================
________ test_a_numbered_acceptance_criterion_naming_no_test_is_caught _________

    def test_a_numbered_acceptance_criterion_naming_no_test_is_caught():
        """Numbered criteria must be checked exactly like bulleted ones."""
        d = project(FIXTURE.replace("- `test_broken` passes", "1. code should be clean"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:142: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught` fails on base `main` too -- the bug is not already fixed upstream
```
ulleted ones."""
        d = project(FIXTURE.replace("- `test_broken` passes", "1. code should be clean"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:142: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-1us5bxvk/base
      Built pipeline @ file:///tmp/pipeline-base-1us5bxvk/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- acceptance criterion names no test: - `uv run --group dev pytest -q` reports no failures.

### 2026-08-24 08:13:57Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion names no test: - `uv run --group dev pytest -q` reports no failures.

### 2026-08-24 · planning · result=ok

Plan rewritten after the Tier A gate failed the first one. The gate's only
finding was one acceptance criterion, not the fix:

```
acceptance criterion names no test: - `uv run --group dev pytest -q` reports no failures.
```

Cause: the dispatcher runs an installed copy of the gate, not this checkout's.
`/home/chezzijr/.local/share/uv/tools/pipeline/lib/python3.13/site-packages/pipeline/core/gate.py`
filters criteria with `r"\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/"` -- no
`\bpytest\b` arm, so `pytest` on its own matches nothing there. `main` has the
arm; it landed at 2b167c8. The installed copy is stale against `main`.

Change: every criterion now names `tests/` or a `tests/...::...` node, which
both copies accept. The fix, the eight steps and `files_declared` are unchanged.
Line numbers corrected against the worktree: the criteria filter is
`gate.py:273` (was 272), the `## Plan` numbered match is `gate.py:247` (was
248), `PLAN_FILE_RULE` ends at line 36 (was 37).

Flagged, outside this ticket: the stale install means the gate that runs is not
the gate in `main`, for every ticket and not only this one. Reinstalling it is
an operator action and needs its own ticket.

### 2026-08-24 08:31:01Z · planning · session · session=0eb13ac8-1ecb-4aef-96a4-9ba30948c95e

`planning` ran as session `0eb13ac8-1ecb-4aef-96a4-9ba30948c95e`
- replay: `claude --resume 0eb13ac8-1ecb-4aef-96a4-9ba30948c95e`
- log: `.project/logs/TICKET-042-planning-0eb13ac8.log`

### 2026-08-24 08:31:01Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan rewritten: same CRIT_ITEM_RE fix at gate.py:273, criteria now name tests/ paths -- the gate that runs is an installed copy predating 2b167c8

### 2026-08-24 08:31:13Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught` fails as required
```
== test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-042
configfile: pyproject.toml
collected 1 item

tests/test_gate.py F

=================================== FAILURES ===================================
________ test_a_numbered_acceptance_criterion_naming_no_test_is_caught _________

    def test_a_numbered_acceptance_criterion_naming_no_test_is_caught():
        """Numbered criteria must be checked exactly like bulleted ones."""
        d = project(FIXTURE.replace("- `test_broken` passes", "1. code should be clean"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:142: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught` fails on base `main` too -- the bug is not already fixed upstream
```
bulleted ones."""
        d = project(FIXTURE.replace("- `test_broken` passes", "1. code should be clean"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:142: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-neaqel1b/base
      Built pipeline @ file:///tmp/pipeline-base-neaqel1b/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 · plan-validation · finding · result=ok

Plan accepted. Eight items scored against the code, not against the plan's
description of it.

1. Root cause: the criteria filter selects candidate lines by bullet prefix, so
   a section written `1.`/`1)` produces an empty list and the loop body never
   runs. The plan replaces the selector; it leaves the test-shape regex at
   `gate.py:281` untouched. That fixes why the test fails, not the symptom.
2. Decisions: DEC-030 binds and the plan complies. The rule text stays in
   `pipeline/core/gate.py`, and the new test asserts the literal `names no
   test`, importing no branch-only name -- the DEC-017/DEC-018 constraint.
3. Scope: eight steps, two files, every step traceable to a criterion.
4. Falsifiable: I read the halves. First half fails today (`assert not ok` on
   `ok=True`); second half fails a fix that flags numbered lines regardless of
   test shape. Criterion 3's test at `tests/test_gate.py:146-156` asserts both
   directions on the bulleted path, so it proves bullets are unchanged.
5. No research left: steps 4 and 5 name `gate.py:273` and the anchor
   `PLAN_FILE_RULE` (ends at line 36). Both verified in the worktree.
6. Riskiest step is 5, the filter swap. `## Rollback` states the fallback:
   keep `CRIT_ITEM_RE`, require `\d+[.)]\s`.
7. Regression surface: `gate.py:273` is the only copy of the filter in the
   package. Two suite callers reach `gate()` -- `tests/test_gate.py` and
   `tests/test_ticket.py:290` -- and both use the bulleted `FIXTURE`.
8. Blast radius matches `bugfix`: one line changed, one constant, one test.

`CRIT_ITEM_RE.match(l)` and `l.strip().startswith(("-", "*"))` accept the same
bulleted lines: `^\s*` covers the leading whitespace `strip()` removed.

Noted, outside this ticket: `pipeline/stages/planning.md:73` states the rule as
"each one falsifiable and mapped to a named test" and prescribes no marker, so
the fix needs no prompt change.

### 2026-08-24 08:33:44Z · plan-validation · session · session=d4f0e459-24af-47ae-8918-6ad4b08e9f6d

`plan-validation` ran as session `d4f0e459-24af-47ae-8918-6ad4b08e9f6d`
- replay: `claude --resume d4f0e459-24af-47ae-8918-6ad4b08e9f6d`
- log: `.project/logs/TICKET-042-plan-validation-d4f0e459.log`

### 2026-08-24 08:33:44Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan accepted on all eight items: fixes the selector at gate.py:273, complies with DEC-030 and the DEC-017/DEC-018 import constraint, fallback stated

### 2026-08-24 08:36:44Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 08:38:38Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught` fails as required
```
== test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-042
configfile: pyproject.toml
collected 1 item

tests/test_gate.py F

=================================== FAILURES ===================================
________ test_a_numbered_acceptance_criterion_naming_no_test_is_caught _________

    def test_a_numbered_acceptance_criterion_naming_no_test_is_caught():
        """Numbered criteria must be checked exactly like bulleted ones."""
        d = project(FIXTURE.replace("- `test_broken` passes", "1. code should be clean"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:142: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught` fails on base `main` too -- the bug is not already fixed upstream
```
ulleted ones."""
        d = project(FIXTURE.replace("- `test_broken` passes", "1. code should be clean"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:142: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ueee69o2/base
      Built pipeline @ file:///tmp/pipeline-base-ueee69o2/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 08:38:38Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 · implementing · todo

Todo, one per plan step:
1. [x] add `test_numbered_criteria_are_checked_in_both_marker_forms` after the committed test
2. [x] write the two-half test body
3. [x] confirm both tests fail RED (`-k numbered`)
4. [x] add `CRIT_ITEM_RE` after `PLAN_FILE_RULE`
5. [x] swap the `startswith` filter for `CRIT_ITEM_RE.match` at `gate.py:273`
6. [x] `tests/test_gate.py -q` green (27 passed)
7. [x] whole suite green (248 passed)
8. [x] commit on `ticket/042`

### 2026-08-24 · implementing · result=ok

Executed the plan unchanged. Verified RED first:
`tests/test_gate.py::test_a_numbered_acceptance_criterion_naming_no_test_is_caught`
and the new `test_numbered_criteria_are_checked_in_both_marker_forms` both
failed with `AssertionError: []` on their first half, before any production
change. Added `CRIT_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])")` to
`pipeline/core/gate.py` and swapped it in at the criteria filter, `gate.py:273`
(now shifted by the new constant). No other line in that block changed.

GREEN: `uv run --group dev pytest tests/test_gate.py -q` -- 27 passed.
Whole suite: `uv run --group dev pytest -q` -- 248 passed, clean output.

Committed `42a83a6`: `fix: the gate checks numbered acceptance criteria, not
only bulleted ones`, touching `pipeline/core/gate.py` and `tests/test_gate.py`
only, as the plan and `files_declared` require.

### 2026-08-24 08:39:49Z · implementing · session · session=6918852c-8d29-439a-afdd-a7175f518ddd

`implementing` ran as session `6918852c-8d29-439a-afdd-a7175f518ddd`
- replay: `claude --resume 6918852c-8d29-439a-afdd-a7175f518ddd`
- log: `.project/logs/TICKET-042-implementing-6918852c.log`

### 2026-08-24 08:39:49Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added CRIT_ITEM_RE and swapped the criteria filter at gate.py:273; both new/existing tests and the full suite (248) pass; committed 42a83a6.

### 2026-08-24 · review · result=ok

Reviewed `main...HEAD` (`04f46e3`, `42a83a6`), the first review pass. No
blocking findings. The diff is the plan: `CRIT_ITEM_RE =
re.compile(r"^\s*(?:[-*]|\d+[.)])")` sits after `PLAN_FILE_RULE` and drives the
criteria filter at `gate.py:280`. The test-shape regex, the `re.I` flag and
`f"acceptance criterion names no test: {line.strip()}"` are byte-for-byte
unchanged. `42a83a6` touches `pipeline/core/gate.py` and `tests/test_gate.py`
only. The new test imports no branch-only name, so DEC-017/DEC-018 hold.

All four acceptance criteria pass: the three named tests report `3 passed in
0.04s`, the whole suite `248 passed in 10.38s`.

I checked non-vacuity by rebinding `gate.CRIT_ITEM_RE` in memory, never on
disk. Under the pre-fix `r"^\s*[-*]"` the new test fails with `AssertionError:
[]` at `tests/test_gate.py:154`.

Findings, both minor:

1. minor -- the second half of
   `test_numbered_criteria_are_checked_in_both_marker_forms` does not catch the
   over-fix its docstring names. Rebound to `re.compile(r"")`, which matches
   every line, the test still passes. The `FIXTURE` section is
   `'## Acceptance criteria\n- `test_broken` passes\n'`, so it holds no
   non-criterion line to over-report. The half does assert what criterion 2
   asks.
2. minor -- the fix widens the fence hole `## Decisions` records: a `1.` or
   `1)` line inside a fenced block in `## Acceptance criteria` now reads as a
   criterion, as `-` lines already did. Inherent to the fix. TICKET-043 covers
   the class.

### 2026-08-24 08:43:17Z · review · session · session=4425bad6-99d1-47d8-81eb-6e98f5992ccb

`review` ran as session `4425bad6-99d1-47d8-81eb-6e98f5992ccb`
- replay: `claude --resume 4425bad6-99d1-47d8-81eb-6e98f5992ccb`
- log: `.project/logs/TICKET-042-review-4425bad6.log`

### 2026-08-24 08:43:17Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ delta matches the plan; all four acceptance criteria pass (248 passed); two minor findings, none blocking

### 2026-08-24 08:43:28Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 08:43:29Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/042


Merge made by the 'ort' strategy.
 .project/decisions/DEC-043.md  |  25 ++
 .project/tickets/TICKET-043.md | 613 +++++++++++++++++++++++++++++++++++++++++
 CLAUDE.md                      |   2 +-
 pipeline/core/fence.py         |   2 +-
 pipeline/core/machine.py       |   7 +-
 tests/test_fence.py            |  54 ++++
 tests/test_machine.py          |   4 +-
 7 files changed, 701 insertions(+), 6 deletions(-)
 create mode 100644 .project/decisions/DEC-043.md
 create mode 100644 .project/tickets/TICKET-043.md
Updating 53875da..a5f7263
Fast-forward
 pipeline/core/gate.py |  9 ++++++++-
 tests/test_gate.py    | 27 +++++++++++++++++++++++++++
 2 files changed, 35 insertions(+), 1 deletion(-)

```

### 2026-08-24 08:43:29Z · merging · decision

decision recorded as `DEC-042`
