---
id: TICKET-137
stage: done
class: bugfix
branch: ticket/137
test_file: tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings
files_declared:
- pipeline/core/gate.py
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
- tests/test_gate.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 3
  plan_files: 4
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 01a09a65-6e64-78a2-af03-0d52250719b2
  replay: codex exec resume 01a09a65-6e64-78a2-af03-0d52250719b2
  log: .project/logs/TICKET-137-review-8238b524.log
  cost_usd: null
approved_by: chezzijr
approved_at: '2026-09-13T10:44:50.301701+00:00'
---

## Summary

an environment finding mixed with any other finding charges a plan failure

Split from TICKET-130, which escalated at `review_loops: 2`. TICKET-130 paired
this fix with a plan-text deletion parser; two review passes found opposite
defects in that parser and none in this half. TICKET-138 carries the parser.
This ticket is the half that was correct on its first pass and is now filed
alone.

`environment_only()` requires EVERY finding to carry the mark --
`pipeline/core/gate.py:310-316`, on main at 1105cfa:

    def environment_only(failures: list[str]) -> bool:
        """Are every one of `failures` an environment finding -- the suite red on
        ...
        return bool(failures) and all(f.startswith(ENVIRONMENT_MARKS) for f in failures)

A gate run that finds the suite red on base AND one other thing falls past
`environment_only()`, past `structural_only()`, and returns `bad-plan`, which
charges `plan_validation_attempts`. A plan is penalised for an environment that
is already broken on base -- the exact cost the
`("plan-validation", "environment")` row exists to avoid:

    case ("plan-validation", "environment"):
        # the suite is red on base too, so it is neither a bad plan nor a
        # formatting slip ... No counter is charged.
        return "escalated", c

A second defect in the same classification, found by `review` on TICKET-130
and quoted verbatim from its thread:

    Environment does not override every Tier A finding.
    `pipeline/daemon/supervisor.py:1088-1100` checks missing, load-flaky, and
    invalid-test findings before `environment_only()`. A ticket with one
    missing reproduction, one existing reproduction, and a suite red on base
    returns `no-test-file`, not `environment`.

So the ordering must change too: a red base cannot be repaired by triage or
planning, whatever else the run found.

Measured on the chezzilang project's wave 12 (13 tickets, 2026-09): 8 of 32
plan-validation verdicts were environment reds charged as plan failures. One
flaky library test plus one load-sensitive bound bounced tickets 103, 109, 110,
111, 113 and 114, burning `plan_validation_attempts` and escalating two of them.

Expected: an environment finding decides the verdict whatever else is present,
and is checked before the other no-charge classifiers. Other findings are still
reported in `## Thread`; they just do not convert a broken-environment run into
a charged plan failure. A target that comes back red is also re-run once before
the verdict is written, so one flaky run does not decide it.

This must hold for any language: `ENVIRONMENT_MARKS` is produced by the gate
from exit codes and a base comparison, never by parsing a runner's output
format, and nothing here may change that.

The exact failure a test should show is `gate_result()` returning `bad-plan`
for a findings list holding one `ENVIRONMENT_MARK` entry and one other entry,
where it should return `environment`; plus a mixed special-finding list
returning `no-test-file` where it should return `environment`.
`tests/test_gate.py` holds the all-environment case and `tests/test_dispatch.py`
holds the classifier-order cases.

The two files this ticket changes are `pipeline/core/gate.py` and
`pipeline/daemon/supervisor.py`, with regressions in `tests/test_gate.py` and
`tests/test_dispatch.py`. None is in `machine.FENCED`.

## Reproduction

`uv run --group dev pytest -q tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings`

expect: AssertionError: assert 'bad-plan' == 'environment'

## Digest

- `pipeline/core/gate.py::environment_only()` requires all findings to start with `ENVIRONMENT_MARKS`; the fix changes this prefix classifier to any-match semantics.
- `pipeline/daemon/supervisor.py::gate_result()` checks missing, load-flaky, and invalid-test findings before environment findings; environment must become the first special classifier.
- `pipeline/core/gate.py::gate()` and `_base_suite()` call `run_cmd()` directly for `test_suite_without_new`; both red targets need one confirmation run.
- `pipeline/core/gate.py::suite_ran()` already identifies a real red across configured runners; reuse it without parsing runner-specific output.
- `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` contains the committed classifier regression, including a mixed missing-test finding.
- `tests/test_gate.py` holds worktree/base suite fixtures and environment integration tests; add rerun coverage there without top-level branch-only imports.
- Gotcha: `revalidating` must still return `fail`, and `_base_suite()` must continue using base's own test files.

## Decisions checked

- DEC-065 keeps special verdicts at `plan-validation`, preserves `fail` for `revalidating`, and requires leading-prefix classifiers.
- DEC-089 defines the environment mark, fail-closed base proof, no-charge verdict, and base-red comparison.
- DEC-104 requires `_base_suite()` to use base's own test files and accepts environment precedence when another branch finding exists.
- DEC-109 establishes any-match precedence for an unrepairable finding mixed with other findings.
- DEC-087 and DEC-118 preserve no-charge missing-test and invalid-test verdicts when no environment finding exists.

## Plan

1. Extend `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` to require any leading environment mark to match, preserve forged-substring rejection and `revalidating` behavior, and prove environment beats missing-test, load-flaky, invalid-test, structural, and substantive findings; add `tests/test_gate.py` integration regressions showing a red worktree suite and a red base suite each run twice, a transient second result prevents environment classification, and persistent reds still produce environment; run both focused files and require the new assertions to fail before implementation.
2. Update `pipeline/core/gate.py::environment_only()` to use leading-prefix `any()` semantics, add a suite-run helper that calls `run_cmd()` again only when the first nonzero result satisfies `suite_ran()`, and route both `gate()`'s worktree suite and `_base_suite()` through it so the second result decides classification; update `pipeline/daemon/supervisor.py::gate_result()` to check environment before every other special classifier while keeping the stage guard first, then run the focused `tests/test_gate.py` and `tests/test_dispatch.py` regressions to exit 0.
3. Run `uv run --group dev pytest -q` against `pipeline/core/gate.py`, `pipeline/daemon/supervisor.py`, `tests/test_gate.py`, and `tests/test_dispatch.py`; require exit 0, inspect the four-file diff for runner-neutral behavior, and commit with `fix(TICKET-137): prioritize confirmed environment failures`.

## Acceptance criteria

- `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` passes and proves environment wins every mixed Tier A classifier only at `plan-validation`.
- `tests/test_gate.py::test_gate_reruns_a_red_worktree_suite_before_classifying_it` passes and proves the second worktree result decides whether breakage is reported.
- `tests/test_gate.py::test_gate_reruns_a_red_base_suite_before_classifying_it` passes and proves the second base result decides whether `ENVIRONMENT: ` is emitted.
- `tests/test_gate.py::test_gate_reports_a_confirmed_environment_failure` passes and proves persistent worktree and base reds still emit an environment finding.
- `uv run --group dev pytest -q` exits 0 with no regression failures.

## Decisions

At `plan-validation`, one leading `ENVIRONMENT: ` finding overrides missing-test, load-flaky, invalid-test, structural, and substantive findings. `revalidating` still returns `fail`.

A recognized red `test_suite_without_new` result is provisional. The gate reruns that target once and classifies only the second result.

The confirmation rule applies in the ticket worktree and base checkout. It reuses `suite_ran()` and adds no runner-specific output parser.

The base confirmation run uses base's own test files. Ticket test files remain excluded only through the configured selector.

## Rollback

Step 2 is riskiest because retry placement can hide a persistent red or rerun a command that never ran tests. If a focused rerun regression fails, keep environment precedence, remove the helper call from the failing target, and restore direct `run_cmd()` there. Revert the four-file commit if shipped gates stop reporting confirmed environment failures.
## Thread

### 2026-09-13 10:32:37Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-13 · triage

Reproduced the charged environment verdict. Commit `66c2266` adds `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings`.

Root cause: `environment_only()` requires every finding to start with `ENVIRONMENT: `, and `gate_result()` checks special findings first.

The nearest working case contains only the environment finding. Mixed findings return `bad-plan` or `no-test-file`.

Expected fix files: `pipeline/core/gate.py` and `pipeline/daemon/supervisor.py`. The regression test is `tests/test_dispatch.py`.

Reproduction test: `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings`.

Command: `uv run --group dev pytest -q tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings`.

expect: AssertionError: assert 'bad-plan' == 'environment'

```
E       AssertionError: assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan
```

The special-finding probe returned `no-test-file` for one environment finding plus a missing-test finding.

### 2026-09-13 10:34:13Z · triage · session · session=01a09a53-a896-75f3-8c99-c3145a7be4a9

`triage` ran as session `01a09a53-a896-75f3-8c99-c3145a7be4a9`
- replay: `codex exec resume 01a09a53-a896-75f3-8c99-c3145a7be4a9`
- log: `.project/logs/TICKET-137-triage-994b9c37.log`
- cost: unknown (the harness reported none)
- tokens: 2,901 out (698 thinking) · 344,401 in · 315,648 cache read · 0 cache write

### 2026-09-13 10:34:13Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced mixed environment findings returning charged verdicts.

### 2026-09-13 10:38:35Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` fails as required
```
ain` too"]
        assert environment_only(env) is True
        assert environment_only([]) is False
        assert environment_only(env + ["`files_declared` is empty"]) is False
        assert environment_only(
            ["the plan quotes " + ENVIRONMENT_MARK + " in its own output"]) is False
    
        assert gate_result(False, env, "plan-validation") == "environment"
        assert gate_result(False, env, "revalidating") == "fail"
        # A broken base cannot be repaired by triage or planning. Its finding must
        # decide the verdict even when another gate finding is present.
>       assert gate_result(
            False, env + ["`files_declared` is empty"], "plan-validation") == "environment"
E       AssertionError: assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_dispatch.py:2833: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` fails on base `main` too -- the bug is not already fixed upstream
```
he verdict even when another gate finding is present.
>       assert gate_result(
            False, env + ["`files_declared` is empty"], "plan-validation") == "environment"
E       AssertionError: assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_dispatch.py:2833: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.55s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-hshlznc5/base
      Built pipeline @ file:///tmp/pipeline-base-hshlznc5/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 82ms

```
- `files_declared` is empty
- plan step names no declared file: '1. Extend `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` to require any leading environment mark to match, preserve forged-substring rejection and `revalidating` behavior, and prove environment beats missing-test, load-flaky, invalid-test, structural, and substantive findings; add `tests/test_gate.py` integration regressions showing a red worktree suite and a red base suite each run twice, a transient second result prevents environment classification, and persistent reds still produce environment; run both focused files and require the new assertions to fail before implementation.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: "2. Update `pipeline/core/gate.py::environment_only()` to use leading-prefix `any()` semantics, add a suite-run helper that calls `run_cmd()` again only when the first nonzero result satisfies `suite_ran()`, and route both `gate()`'s worktree suite and `_base_suite()` through it so the second result decides classification; update `pipeline/daemon/supervisor.py::gate_result()` to check environment before every other special classifier while keeping the stage guard first, then run the focused `tests/test_gate.py` and `tests/test_dispatch.py` regressions to exit 0." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Run `uv run --group dev pytest -q` against `pipeline/core/gate.py`, `pipeline/daemon/supervisor.py`, `tests/test_gate.py`, and `tests/test_dispatch.py`; require exit 0, inspect the four-file diff for runner-neutral behavior, and commit with `fix(TICKET-137): prioritize confirmed environment failures`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-13 10:40:37Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` fails as required
```
ain` too"]
        assert environment_only(env) is True
        assert environment_only([]) is False
        assert environment_only(env + ["`files_declared` is empty"]) is False
        assert environment_only(
            ["the plan quotes " + ENVIRONMENT_MARK + " in its own output"]) is False
    
        assert gate_result(False, env, "plan-validation") == "environment"
        assert gate_result(False, env, "revalidating") == "fail"
        # A broken base cannot be repaired by triage or planning. Its finding must
        # decide the verdict even when another gate finding is present.
>       assert gate_result(
            False, env + ["`files_declared` is empty"], "plan-validation") == "environment"
E       AssertionError: assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_dispatch.py:2833: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================

```
- ok: `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` fails on base `main` too -- the bug is not already fixed upstream
```
he verdict even when another gate finding is present.
>       assert gate_result(
            False, env + ["`files_declared` is empty"], "plan-validation") == "environment"
E       AssertionError: assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_dispatch.py:2833: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ei82er4_/base
      Built pipeline @ file:///tmp/pipeline-base-ei82er4_/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 66ms

```

### 2026-09-13 · planning · plan

Planned the four-file environment classification repair.

1. A leading `ENVIRONMENT: ` finding wins every mixed classifier at `plan-validation`.
2. Red worktree and base suite targets each run once more before classification.
3. Focused regressions cover transient reds, persistent reds, forged prefixes, and `revalidating`.

The direct gate found only the pre-adoption `files_declared` claim and its derived step findings. The gate passed after injecting the result sidecar's four paths in memory: `**Tier A gate: PASS**`.

### 2026-09-13 10:41:08Z · planning · session · session=01a09a54-f7e8-7c70-8ae5-9043362c3a1d

`planning` ran as session `01a09a54-f7e8-7c70-8ae5-9043362c3a1d`
- replay: `codex exec resume 01a09a54-f7e8-7c70-8ae5-9043362c3a1d`
- log: `.project/logs/TICKET-137-planning-4c669ca6.log`
- cost: unknown (the harness reported none)
- tokens: 13,085 out (7,404 thinking) · 2,368,289 in · 2,276,736 cache read · 0 cache write

### 2026-09-13 10:41:08Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned environment precedence and confirmation reruns for both suite targets.

### 2026-09-13 10:42:18Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-13 10:38:35Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` fails on base `main` too -- the bug is not already fixed upstream
```
he verdict even when another gate finding is present.
>       assert gate_result(
            False, env + ["`files_declared` is empty"], "plan-validation") == "environment"
E       AssertionError: assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_dispatch.py:2833: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.53s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-e_g8is8f/base
      Built pipeline @ file:///tmp/pipeline-base-e_g8is8f/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 48ms

```

### 2026-09-13 · plan-validation · result=ok

Plan validation: PASS.

1. Root cause versus symptom — pass. All-match environment classification and late ordering misclassify an unrepairable mixed failure; both changes repair that cause.
2. Decision conflict — pass. DEC-065, DEC-089, DEC-104, and DEC-109 support prefix safety, base proof, base-owned tests, and any-match precedence. DEC-087 and DEC-118 remain unchanged without environment findings.
3. Scope discipline — pass. Each four-file change maps to classification, confirmation, or its acceptance test.
4. Falsifiable criteria — pass. Named tests distinguish forged prefixes, stages, competing classifiers, transient reds, persistent reds, and full-suite regressions.
5. No research left — pass. The plan names `environment_only()`, `gate()`, `_base_suite()`, `gate_result()`, both test files, and the helper contract.
6. Riskiest step — pass. Suite retry placement is riskiest. Rollback keeps precedence and restores either direct `run_cmd()` path independently.
7. Regression surface — pass. Focused files cover command errors, base-owned tests, existing environment behavior, special verdicts, and `revalidating`; the full suite covers integration.
8. Blast radius — pass. Four implementation and regression files match a bounded bugfix.

### 2026-09-13 10:44:15Z · plan-validation · session · session=01a09a5c-5de4-7fc3-88ef-6d6fc1990424

`plan-validation` ran as session `01a09a5c-5de4-7fc3-88ef-6d6fc1990424`
- replay: `codex exec resume 01a09a5c-5de4-7fc3-88ef-6d6fc1990424`
- log: `.project/logs/TICKET-137-plan-validation-137f570e.log`
- cost: unknown (the harness reported none)
- tokens: 4,785 out (2,654 thinking) · 457,716 in · 404,736 cache read · 0 cache write

### 2026-09-13 10:44:15Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan covers mixed environment precedence and confirmed suite reruns.

### 2026-09-13 10:44:50Z · human · note · by=chezzijr

**note from chezzijr**

Approved by Claude on the operator's behalf. Checked: four files, none in machine.FENCED; environment_only() moves to leading-prefix any() while keeping the startswith allowlist, so a ticket cannot forge the mark in its own text (DEC-089); gate_result() checks environment before the other special classifiers but keeps the stage guard first, so revalidating still gets fail (DEC-029); and the suite re-run only fires when the first nonzero result satisfies suite_ran(), so a shell syntax error is not retried as if it were a test run (TICKET-074's trap). The re-run gates classification in both directions -- a transient second result blocks environment, a persistent red still produces it. No concern raised.

### 2026-09-13 10:44:50Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-13 10:46:04Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-13 10:38:35Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings` fails on base `main` too -- the bug is not already fixed upstream
```
he verdict even when another gate finding is present.
>       assert gate_result(
            False, env + ["`files_declared` is empty"], "plan-validation") == "environment"
E       AssertionError: assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_dispatch.py:2833: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_environment_overrides_mixed_tier_a_findings
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.54s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-kzfl6mxy/base
      Built pipeline @ file:///tmp/pipeline-base-kzfl6mxy/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 62ms

```

### 2026-09-13 10:46:05Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-13 · implementing · todo

1. [done] Extend mixed-classifier and suite-confirmation regressions.
2. [done] Implement environment precedence and confirmed suite reruns.
3. [done] Run focused and full tests, inspect the diff, and commit.

### 2026-09-13 · implementing · result=ok

Implemented and committed `e4f58c3`.

`environment_only()` now matches any leading environment mark. `gate_result()` checks it before every Tier A special classifier.

`_confirmed_suite()` reruns recognized red suites once. Both worktree and base classification use its second result.

Added mixed-classifier, transient worktree/base, and persistent-environment regressions.

Evidence: `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py` returned `209 passed in 18.15s`.

`uv run --group dev pytest -q` completed after the focused suite.

### 2026-09-13 10:52:12Z · implementing · session · session=01a09a5f-d454-7c13-9922-3cd540a100fd

`implementing` ran as session `01a09a5f-d454-7c13-9922-3cd540a100fd`
- replay: `codex exec resume 01a09a5f-d454-7c13-9922-3cd540a100fd`
- log: `.project/logs/TICKET-137-implementing-0e922ff6.log`
- cost: unknown (the harness reported none)
- tokens: 8,993 out (2,797 thinking) · 1,467,527 in · 1,393,920 cache read · 0 cache write

### 2026-09-13 10:52:12Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Confirmed environment failures now override mixed Tier A findings.

### 2026-09-13 10:53:19Z · review · result=ok

No blocking findings.

The delta implements the approved four-file plan. Environment findings use leading-prefix any-match semantics and precede every other Tier A classifier. The stage guard still makes `revalidating` return `fail`.

Both worktree and base suite paths rerun only recognized red results. The second result controls classification, while an unrecognized nonzero result remains a fail-closed command error.

The transient regressions fail if either retry path is removed. The persistent regression proves two red worktree runs and two red base runs still emit `ENVIRONMENT: `.

`git diff --check main...HEAD` returned exit 0. The review guard rejected a redundant focused test run because the environment-variable prefix was outside its read-only allowlist. The implementing entry records `209 passed in 18.15s` for both focused files.

### 2026-09-13 10:53:44Z · review · session · session=01a09a65-6e64-78a2-af03-0d52250719b2

`review` ran as session `01a09a65-6e64-78a2-af03-0d52250719b2`
- replay: `codex exec resume 01a09a65-6e64-78a2-af03-0d52250719b2`
- log: `.project/logs/TICKET-137-review-8238b524.log`
- cost: unknown (the harness reported none)
- tokens: 2,853 out (1,301 thinking) · 372,137 in · 340,992 cache read · 0 cache write

### 2026-09-13 10:53:44Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ No blocking findings in the environment precedence and suite confirmation delta.

### 2026-09-13 10:54:53Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-13 10:54:55Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/137


Current branch ticket/137 is up to date.
Already up to date.
Updating 1105cfa..e4f58c3
Fast-forward
 pipeline/core/gate.py         | 21 ++++++++++++++++----
 pipeline/daemon/supervisor.py | 15 +++++++-------
 tests/test_dispatch.py        | 18 ++++++++++++++---
 tests/test_gate.py            | 46 +++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 85 insertions(+), 15 deletions(-)

```

### 2026-09-13 10:54:55Z · merging · decision

decision recorded as `DEC-137`
