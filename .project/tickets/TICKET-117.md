---
id: TICKET-117
stage: done
class: bugfix
branch: ticket/117
test_file: tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected
files_declared:
- pipeline/core/gate.py
- pipeline/stages/planning.md
- tests/test_gate.py
- tests/test_stages.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 4
  plan_files: 4
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 36b505d6-682b-495a-b967-5ad915fcca62
  replay: claude --resume 36b505d6-682b-495a-b967-5ad915fcca62
  log: .project/logs/TICKET-117-review-36b505d6.log
  cost_usd: 1.1106915
approved_by: chezzijr
approved_at: '2026-09-05T17:41:43.821755+00:00'
---

## Summary

Implemented and reviewed. `pipeline/core/gate.py` runs `command_interpreter_mismatch()` on every captured command span before both acceptance shortcuts, using `shlex.split` and the shell/Python/Node suffix maps from `## Digest`. `pipeline/stages/planning.md` documents the families, suffixes, static-only rule, and unclassified fallback.

Review found no blocking findings in `main..HEAD` (`6af6745`, `c541d28`, `e1bf3ac`) and recorded two minor nits. It re-ran all seven acceptance criteria: the five named nodes pass, `uv run --group dev pytest -q tests/test_gate.py tests/test_stages.py` gives `128 passed`, and `uv run --group dev pytest -q` gives `564 passed`.

Review also proved the two new-behavior tests fail when the classifier is neutralized, and probed 15 realistic criteria for false positives without finding one.

## Reproduction

path: `tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected`

command: `uv run --group dev pytest -q tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected`

expect: AssertionError: []

output:

```text
E       AssertionError: []
E       assert (not True)
tests/test_gate.py:748: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected
1 failed in 0.39s
```

## Digest

- `pipeline/core/gate.py` owns `CRIT_CMD_RE`, `CRIT_OUTCOME_RE`, the acceptance loop, and the new compatibility helper; import stdlib `shlex` beside its existing imports.
- Recognized shell executables are `sh`, `bash`, `dash`, `ksh`, `mksh`, and `zsh`; compatible suffixes are `.sh`, `.bash`, `.ksh`, and `.zsh`.
- Recognized Python executables match `python(?:\d+(?:\.\d+)*)?`; compatible suffixes are `.py` and `.pyw`.
- Recognized Node executables are `node` and `nodejs`; compatible suffixes are `.js`, `.mjs`, and `.cjs`.
- Parse every `CRIT_CMD_RE` span with `shlex.split`; use the executable basename and only `argv[1]`, or `argv[2]` after a lone `--`, as the script target.
- Treat wrappers, pre-target interpreter options, inline/module modes, `shlex` failures, unknown executable names, and unknown suffixes as unclassified.
- Reject only when both families are known and the target suffix is outside the interpreter family's compatible set; compare suffixes case-insensitively and never execute criteria.
- `tests/test_gate.py` holds the behavior matrix without new `helpers.py` imports; `tests/test_stages.py` pins the prose contract in `pipeline/stages/planning.md`.
- The test-name shortcut currently accepts `sh ./pipeline/hooks/test_dangerous_commands.py`; compatibility must run before both acceptance shortcuts.
- Keep the finding prefix `acceptance criterion names no test`; `STRUCTURAL_MARKS` and the structural budget depend on it.
- Riskiest step: classifier false positives could reject valid project commands. Runtime fallback classifies every ambiguous shape as unknown and applies the existing command-outcome rule.
- If a recognized shape proves ambiguous, narrow only that executable or suffix mapping so it takes the unknown fallback; keep both acceptance arms unchanged.

## Decisions checked

DEC-079 requires test and command acceptance arms to remain alternatives, keeps `CRIT_CMD_RE` discriminating command spans, and freezes the finding prefix.

DEC-065 requires structural findings to retain an allowlisted `startswith` prefix or gain a new `STRUCTURAL_MARKS` entry.

DEC-054 requires criterion continuations and fences to stay assembled before validation; the classifier consumes `crits` without changing that parser.

DEC-018 forbids new branch-only imports from `tests/helpers.py` because the gate copies `tests/test_gate.py` onto base.

## Plan

1. Expand `tests/test_gate.py` with `test_command_criteria_validate_every_recognized_interpreter_family`, covering every shell, Python, and Node executable/suffix mapping plus one mismatch per family, and add `test_command_criteria_preserve_unclassified_commands` for wrappers, options, parse errors, unknown executables, and unknown suffixes; run these nodes with the committed regression and confirm each mismatch remains accepted before the fix.
2. Update `pipeline/core/gate.py` with the exact maps and parser from `## Digest`, scan every captured command before the test-name shortcut, emit the existing `acceptance criterion names no test` finding for known mismatches, return unclassified for every ambiguous shape, then run the three TICKET-117 behavior nodes in `tests/test_gate.py` and commit the green classifier with its tests.
3. Add `tests/test_stages.py::test_planning_prompt_documents_static_interpreter_compatibility`, first proving it fails because `pipeline/stages/planning.md` omits the families, suffixes, static-only rule, and unknown fallback; update `pipeline/stages/planning.md` with those requirements, rerun the named test, and commit the green contract change.
4. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_stages.py` and `uv run --group dev pytest -q` against `pipeline/core/gate.py`, `pipeline/stages/planning.md`, `tests/test_gate.py`, and `tests/test_stages.py`; require both commands to exit 0 before handing off the commits.

## Acceptance criteria

- `tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected` passes and returns the existing structural finding prefix.
- `tests/test_gate.py::test_command_criteria_validate_every_recognized_interpreter_family` passes for every declared executable and compatible suffix, and rejects one known mismatch per family.
- `tests/test_gate.py::test_command_criteria_preserve_unclassified_commands` passes for wrappers, interpreter options, parse failures, unknown executables, and unknown suffixes.
- `tests/test_gate.py::test_a_criterion_naming_a_command_and_an_exit_status_is_accepted` passes, preserving the existing arbitrary-command criterion.
- `tests/test_stages.py::test_planning_prompt_documents_static_interpreter_compatibility` passes and asserts the prompt names all three families, their suffixes, static validation, and the unknown fallback.
- `uv run --group dev pytest -q tests/test_gate.py tests/test_stages.py` exits 0.
- `uv run --group dev pytest -q` exits 0.

## Decisions

Acceptance-command validation stays static. The gate must never execute a criterion because criteria can be destructive or project-specific.

A known interpreter-target mismatch is checked before both acceptance shortcuts. Otherwise, a test-shaped script filename bypasses validation.

Only direct option-free shell, Python, and Node invocations, plus their `--` form, enter compatibility validation.

Wrappers, interpreter options, parse failures, unknown interpreters, and unknown suffixes remain eligible for the existing command-outcome rule. Static validation must not reject commands it cannot classify.

## Rollback

First remove the offending executable or suffix mapping from `pipeline/core/gate.py`; unclassified commands safely regain existing behavior without weakening `CRIT_CMD_RE`.

If the feature must be removed, revert the compatibility helper in `pipeline/core/gate.py`, its contract in `pipeline/stages/planning.md`, and its controls in `tests/test_gate.py` and `tests/test_stages.py`. This restores syntax-only command acceptance.

## Thread

### 2026-09-05 17:00:00Z · planning · plan

The plan adds static interpreter-target compatibility validation before either acceptance shortcut.

Evidence: `sh ./pipeline/hooks/test_dangerous_commands.py` matches both `CRIT_CMD_RE` and the earlier test-name regex. Checking only the command arm would leave the regression green for the wrong reason.

DEC-079 preserves the two acceptance arms and the `acceptance criterion names no test` prefix. DEC-065 makes that prefix load-bearing for structural-budget classification.

The gate will parse command text without running it. Recognized suffix mismatches fail; unknown combinations retain current behavior to avoid rejecting project-specific commands.

### 2026-09-05 16:20:32Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-05 16:35:00Z · triage · investigation

The acceptance criterion `` `sh ./pipeline/hooks/test_dangerous_commands.py` exits 0 `` passes `gate()` today.

The command exits 2 because `sh` parses Python source. The shell reports `import: command not found` and `syntax error near unexpected token '('`.

`CRIT_CMD_RE` and `CRIT_OUTCOME_RE` at `pipeline/core/gate.py:125-130` only validate command shape and outcome text.

The nearest accepted command is `` `uv run ruff check .` exits 0 `` in `tests/test_gate.py`.

The difference is executable meaning, which the current criterion scan does not inspect.

Committed `e4e62a7` adds the failing regression. Expected fix files: `pipeline/core/gate.py` and `tests/test_gate.py`.

### 2026-09-05 16:29:16Z · triage · session · session=01a07265-a040-7e72-82b6-015d18bec22d

`triage` ran as session `01a07265-a040-7e72-82b6-015d18bec22d`
- replay: `codex exec resume 01a07265-a040-7e72-82b6-015d18bec22d`
- log: `.project/logs/TICKET-117-triage-20ac3696.log`

### 2026-09-05 16:29:16Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced syntax-only acceptance-command validation with a committed failing regression.

### 2026-09-05 16:33:10Z · planning · session · session=01a07267-2774-7fc1-b279-12bcde671ba6

`planning` ran as session `01a07267-2774-7fc1-b279-12bcde671ba6`
- replay: `codex exec resume 01a07267-2774-7fc1-b279-12bcde671ba6`
- log: `.project/logs/TICKET-117-planning-b9f1e33c.log`

### 2026-09-05 16:33:10Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned static interpreter-target validation before the test-name shortcut.

### 2026-09-05 16:34:06Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected` fails as required
```
test_gate.py F

=================================== FAILURES ===================================
________ test_a_command_criterion_with_a_wrong_interpreter_is_rejected _________

    def test_a_command_criterion_with_a_wrong_interpreter_is_rejected():
        """TICKET-117: command shape and an expected exit status do not prove
        the named interpreter can execute its target.  `sh` parses this Python
        test script and exits 2, yet the current syntax-only check accepts it.
        """
        d = project(FIXTURE.replace(
            "- `test_broken` passes",
            "- `sh ./pipeline/hooks/test_dangerous_commands.py` exits 0"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:748: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.13s ===============================

```
- ok: `tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected` fails on base `main` too -- the bug is not already fixed upstream
```
      "- `test_broken` passes",
            "- `sh ./pipeline/hooks/test_dangerous_commands.py` exits 0"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:748: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.36s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-pjm4trqr/base
      Built pipeline @ file:///tmp/pipeline-base-pjm4trqr/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 27ms

```

### 2026-09-05 16:35:41Z · plan-validation · findings

Result: FAIL.

- Root cause vs symptom: PASS. Syntax-only command acceptance and the earlier test-name shortcut cause the false acceptance. Step 2 addresses both causes.
- Decision conflict: PASS. The plan preserves DEC-079's alternative arms and finding prefix, DEC-065's structural classification, and DEC-018's local-test constraint.
- Scope discipline: FAIL. The `pipeline/stages/planning.md` edit has no acceptance criterion that detects a stale contract.
- Falsifiable criteria: PASS. The named mismatch, matching, arbitrary-command, module, and suite checks can fail on incorrect behavior.
- No research left: FAIL. Step 2 does not enumerate recognized interpreter families, compatible suffixes, or parsing rules for options and wrappers.
- Riskiest step: FAIL. Interpreter classification can reject valid project commands. The plan neither identifies this risk nor gives a targeted fallback beyond reverting everything.
- Regression surface: FAIL. One matching control cannot cover the unspecified interpreter families. No criterion covers the planning prompt change.
- Blast radius matches class: PASS. Three files fit a focused gate bugfix.

Unverified: none.

### 2026-09-05 16:36:16Z · plan-validation · session · session=01a0726b-9446-75e0-b992-256b4e8d53fc

`plan-validation` ran as session `01a0726b-9446-75e0-b992-256b4e8d53fc`
- replay: `codex exec resume 01a0726b-9446-75e0-b992-256b4e8d53fc`
- log: `.project/logs/TICKET-117-plan-validation-f8fcb55e.log`

### 2026-09-05 16:36:16Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ Rejected an underspecified classifier with incomplete regression and documentation criteria.

### 2026-09-05 17:10:00Z · planning · plan

The revised plan defines three conservative interpreter families and every compatible suffix.

`shlex.split` handles each captured command. Only direct option-free calls and their `--` form are classifiable.

Wrappers, options, parse failures, unknown executables, and unknown suffixes keep the existing command-outcome behavior.

The behavior matrix tests every declared executable and suffix, one mismatch per family, and each unknown fallback category. A named `tests/test_stages.py` test pins the `pipeline/stages/planning.md` contract.

Classifier false positives are the riskiest change. The targeted fallback removes only the ambiguous alias or suffix from the recognized map.

### 2026-09-05 16:40:18Z · planning · session · session=01a0726d-8ff1-74e2-a2b1-204973e58845

`planning` ran as session `01a0726d-8ff1-74e2-a2b1-204973e58845`
- replay: `codex exec resume 01a0726d-8ff1-74e2-a2b1-204973e58845`
- log: `.project/logs/TICKET-117-planning-1ea0c92a.log`

### 2026-09-05 16:40:18Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Specified the interpreter matrix, conservative parser, complete controls, documentation test, and false-positive fallback.

### 2026-09-05 16:41:11Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-05 16:34:06Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected` fails on base `main` too -- the bug is not already fixed upstream
```
      "- `test_broken` passes",
            "- `sh ./pipeline/hooks/test_dangerous_commands.py` exits 0"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:748: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.34s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-_vd0mmv9/base
      Built pipeline @ file:///tmp/pipeline-base-_vd0mmv9/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 34ms

```

### 2026-09-05 16:42:49Z · plan-validation · findings

Result: PASS.

- Root cause vs symptom: PASS. Missing interpreter-target validation and shortcut ordering cause false acceptance. Step 2 checks known mismatches before both shortcuts.
- Decision conflict: PASS. The plan preserves DEC-079's alternative arms and prefix, DEC-065's structural classification, DEC-054's assembled criteria, and DEC-018's import boundary.
- Scope discipline: PASS. All four files support a behavior criterion, regression control, or prompt-contract criterion.
- Falsifiable criteria: PASS. Named tests distinguish matches, mismatches, unknown fallbacks, shortcut preservation, and prompt omissions. Both suite commands require exit 0.
- No research left: PASS. Steps name exact files, tests, interpreter maps, target positions, ambiguity cases, comparison rules, and execution order.
- Riskiest step: PASS. The plan identifies classifier false positives and narrows an offending executable or suffix into the unknown fallback.
- Regression surface: PASS. Existing test-name and command-outcome acceptance could break. The three behavior nodes, arbitrary-command control, prompt test, and full suites cover them.
- Blast radius matches class: PASS. Four focused files fit this gate bugfix.

Unverified: none.

### 2026-09-05 16:44:49Z · plan-validation · session · session=01a07272-114a-7112-818c-3aa5adde8c50

`plan-validation` ran as session `01a07272-114a-7112-818c-3aa5adde8c50`
- replay: `codex exec resume 01a07272-114a-7112-818c-3aa5adde8c50`
- log: `.project/logs/TICKET-117-plan-validation-95078299.log`

### 2026-09-05 16:44:49Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Accepted the specified conservative classifier, complete controls, regression coverage, and targeted fallback.

### 2026-09-05 17:41:43Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-05 17:46:10Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected` fails as required
```
test_gate.py F

=================================== FAILURES ===================================
________ test_a_command_criterion_with_a_wrong_interpreter_is_rejected _________

    def test_a_command_criterion_with_a_wrong_interpreter_is_rejected():
        """TICKET-117: command shape and an expected exit status do not prove
        the named interpreter can execute its target.  `sh` parses this Python
        test script and exits 2, yet the current syntax-only check accepts it.
        """
        d = project(FIXTURE.replace(
            "- `test_broken` passes",
            "- `sh ./pipeline/hooks/test_dangerous_commands.py` exits 0"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:748: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.23s ===============================

```
- ok: `tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected` fails on base `main` too -- the bug is not already fixed upstream
```
      "- `test_broken` passes",
            "- `sh ./pipeline/hooks/test_dangerous_commands.py` exits 0"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok and any("names no test" in f for f in failures), failures
E       AssertionError: []
E       assert (not True)

tests/test_gate.py:748: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_command_criterion_with_a_wrong_interpreter_is_rejected
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.34s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-9s8lmm7g/base
      Built pipeline @ file:///tmp/pipeline-base-9s8lmm7g/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 35ms

```

### 2026-09-05 17:46:11Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-06 · implementing · todo

1. `tests/test_gate.py`: add `test_command_criteria_validate_every_recognized_interpreter_family` and `test_command_criteria_preserve_unclassified_commands`; confirm both fail-or-pass for the right reason on the unfixed code. Done.
2. `pipeline/core/gate.py`: add the suffix maps, `_compatible_suffixes()`, `_script_target()`, `command_interpreter_mismatch()`; run it before both acceptance shortcuts. Done.
3. `tests/test_stages.py`: add `test_planning_prompt_documents_static_interpreter_compatibility`, RED then update `pipeline/stages/planning.md`, GREEN. Done.
4. Run `tests/test_gate.py tests/test_stages.py` and the full suite. Done, both exit 0.

### 2026-09-06 · implementing · report

Implemented the plan as written, no deviation.

`command_interpreter_mismatch()` in `pipeline/core/gate.py` parses each `CRIT_CMD_RE` span with `shlex.split`, resolves the executable basename against the shell/Python/Node maps, and reads the target from `argv[1]` or `argv[2]` after a lone `--`. It runs before both acceptance shortcuts in the criteria loop, and only ever emits the existing `acceptance criterion names no test` prefix -- DEC-079's prefix and DEC-065's structural classification are unchanged.

Followed TDD: wrote `test_command_criteria_validate_every_recognized_interpreter_family` and confirmed it failed on the unfixed code for the mismatch cases (`AssertionError: ('sh', './script.py', [])`), then implemented the classifier and watched it turn green. Same cycle for `test_planning_prompt_documents_static_interpreter_compatibility` against `planning.md` (`AssertionError: planning.md omits \`sh\``, then `... does not say the check is static`).

`test_command_criteria_preserve_unclassified_commands` passed on the first run, by design -- the plan's own step 1 calls it a regression control proving these shapes were ALREADY accepted before the fix, not a new-behavior test.

Verified: `uv run --group dev pytest -q tests/test_gate.py tests/test_stages.py` (128 passed) and `uv run --group dev pytest -q` (564 passed), both exit 0.

Two commits: `fix(TICKET-117): reject command criteria naming a wrong interpreter target` and `docs(TICKET-117): document static interpreter-target compatibility in planning`.

### 2026-09-05 17:52:01Z · implementing · session · session=f2a359c0-e861-4b90-bf9c-3a951396ee61

`implementing` ran as session `f2a359c0-e861-4b90-bf9c-3a951396ee61`
- replay: `claude --resume f2a359c0-e861-4b90-bf9c-3a951396ee61`
- log: `.project/logs/TICKET-117-implementing-f2a359c0.log`
- cost: $1.10 of a $8 cap
- tokens: 22,203 out (8,364 thinking) · 94 in · 2,999,732 cache read · 69,514 cache write

### 2026-09-05 17:52:01Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added static shell/Python/Node interpreter-target check to gate.py, ran before both acceptance shortcuts, and documented it in planning.md; both suites pass.

### 2026-09-06 · review · findings

**Reviewed the delta `main..HEAD` (`6af6745`, `c541d28`, `e1bf3ac`): no blocking findings.**

I ran all seven acceptance criteria myself. The five named nodes pass (`5 passed in 0.44s`). `uv run --group dev pytest -q tests/test_gate.py tests/test_stages.py` gives `128 passed in 3.27s`; `uv run --group dev pytest -q` gives `564 passed in 48.50s`.

The two new-behavior tests are not vacuous. With `command_interpreter_mismatch` replaced by `lambda c: False`, both fail: `AssertionError: ('sh', './script.py', [])`. Base `main`'s `planning.md` contains no `.pyw`, `.mjs`, `nodejs`, `static`, or `unclassified`, so the prose test fails there too.

I probed the classifier for false positives on 15 realistic criteria. `uv run --group dev pytest -q`, `python3 -m pytest -q`, `bash scripts/ci.sh`, `node dist/cli.js --help`, `python manage.py migrate`, `bash ./run.sh ./thing.py`, `PYTHONPATH=. python ./x.sh`, and `python ./setup.cfg` all return False. Only real mismatches return True. The finding keeps the `acceptance criterion names no test` prefix, so DEC-079 and `STRUCTURAL_MARKS` hold.

Nits, neither blocking:

1. minor: `PYTHON_EXEC_RE` is `^python\d*(?:\.\d+)*$`, not `## Digest`'s `python(?:\d+(?:\.\d+)*)?`. It additionally matches `python.3`, which names no real executable.
2. minor: a criterion quoting a mismatching command inside captured output would be rejected. I found no such criterion in this repo.

### 2026-09-05 17:55:37Z · review · session · session=36b505d6-682b-495a-b967-5ad915fcca62

`review` ran as session `36b505d6-682b-495a-b967-5ad915fcca62`
- replay: `claude --resume 36b505d6-682b-495a-b967-5ad915fcca62`
- log: `.project/logs/TICKET-117-review-36b505d6.log`
- cost: $1.11 of a $5 cap
- tokens: 12,314 out (5,493 thinking) · 32 in · 646,325 cache read · 47,848 cache write

### 2026-09-05 17:55:37Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the 3-commit delta: all 7 acceptance criteria hold, both suites exit 0, no blocking findings; 2 nits recorded.

### 2026-09-05 17:56:30Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-05 17:56:31Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/117


Current branch ticket/117 is up to date.
Already up to date.
Updating 8326f96..e1bf3ac
Fast-forward
 pipeline/core/gate.py       | 80 +++++++++++++++++++++++++++++++++++++++++++++
 pipeline/stages/planning.md | 12 +++++++
 tests/test_gate.py          | 72 ++++++++++++++++++++++++++++++++++++++++
 tests/test_stages.py        | 18 ++++++++++
 4 files changed, 182 insertions(+)

```

### 2026-09-05 17:56:31Z · merging · decision

decision recorded as `DEC-117`
