---
id: TICKET-132
stage: done
class: feature
branch: ticket/132
test_file: tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
files_declared:
- README.md
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- pipeline/templates/pipeline.toml
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_config.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
  plan_steps: 2
  plan_files: 6
lease:
  holder: null
  expires: null
depends_on:
- TICKET-129
last_session:
  stage: review
  id: 01a096d1-3e2e-7123-8260-ab482a05fafa
  replay: codex exec resume 01a096d1-3e2e-7123-8260-ab482a05fafa
  log: .project/logs/TICKET-132-review-8edab120.log
  cost_usd: null
approved_by: chezzijr
approved_at: '2026-09-12T18:06:40.006242+00:00'
---

## Summary

`implementing`'s `max_usd` does not scale with plan size, so a long plan dies mid-step

`USD_SCALED` names three stages and `implementing` is not one --
`pipeline/core/machine.py:33`, on main at 3fd72b0:

    USD_SCALED = {"review", "quick-review", "holistic-review"}

`cap_for()` beside it already does the arithmetic, and
`SIZE_SCALED = {"plan_validation_attempts"}` already applies the same idea to a
counter, for the reason stated in that file: a bigger plan has proportionally
more places to spend.

`implementing` is the stage whose work scales most directly with plan length --
one commit per step -- and it has a flat `max_usd: 8`
(`pipeline/stages/implementing.md:7`).

Observed on the chezzilang project, wave 12 (2026-09): a 21-step VM plan on
sonnet was killed at the $8 cap mid-step, with uncommitted work in the
worktree. The resume only worked because a human raised the cap by hand and
told the implementer to continue rather than restart. A budget kill escalates
on the FIRST occurrence by design (`terminal_reason == "budget_exhausted"`),
so there is no retry to absorb it.

Expected: `implementing` joins `USD_SCALED`, so `cap_for()` raises its cap with
`plan_steps` and `plan_files` the way `bound_for()` already raises
`plan_validation_attempts`, capped by `USD_CEILING_FACTOR`. A project that sets
its own `implementing.max_usd` keeps the existing TICKET-069 rule: the computed
cap never exceeds the operator's number unless the project also sets
`scale_usd = true`.

The exact failure a test should show is `cap_for("implementing", ...)` with a
20-step plan returning the flat `8` rather than a scaled number.
`tests/test_config.py` already covers `cap_for()` for the three scaled stages.

## Reproduction

`tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap`

```sh
uv run --group dev pytest -q tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
```

```
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}
```

expect: AssertionError: expected implementing's 20-step plan to receive its size counters

## Digest

`pipeline/core/machine.py`: add `implementing` to `USD_SCALED`; `cap_for()` already supplies the shared arithmetic and two-times ceiling.
`tests/test_config.py`: committed `test_the_project_decides_which_stages_scale_their_cap` proves 20 plan steps attach counters and raise implementing's `$8` cap to `$10`.
`pipeline/daemon/supervisor.py`: revise `spawn()`'s review-only comment; its existing `cap_config()` rebind keeps the rendered cap and child record on one value.
`README.md`, `pipeline/templates/pipeline.toml`, and `pipeline/templates/skills/pipeline-config/SKILL.md`: each lists only the three review stages as default-scaled and must add `implementing`.
Entry point: `spawn()` passes ticket `plan_steps` and `plan_files` through `cap_config()` into `stage_cap()` before rendering the harness command and recording the child cap.
Gotcha: preserve project `max_usd` pins, explicit `scale_usd` overrides, shared sizing constants, and `USD_CEILING_FACTOR = 2`; do not special-case implementing in `cap_for()`.

## Decisions checked

DEC-078 requires cap scaling through `stage_cap()`, existing plan counters, and `cap_config()`; it permits adding a stage to `USD_SCALED` only after an observed cap kill.
DEC-077 requires the rendered cap and budget-kill report to share `stage_cap()`, and it forbids retrying a budget-killed stage.
DEC-047 defines `plan_steps` and `plan_files` as dispatcher-owned counters populated before transition; this plan reuses them without changing their formula.
DEC-084 requires `[stages.<name>]` budget knobs to stay documented in the shipped `pipeline-config` skill and configuration template.

## Plan

1. Update `pipeline/core/machine.py` to add `implementing` to `USD_SCALED` and record both observed cap kills in the adjacent evidence comment; update `pipeline/daemon/supervisor.py` to describe all default-scaled stages without changing the `cap_config()` ordering; use the committed `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` regression to prove a 20-step implementing plan receives counters and renders `$10`, run the focused and complete config tests, then commit as `fix(TICKET-132): scale implementing cap with plan size`.
2. Update `README.md`, `pipeline/templates/pipeline.toml`, and `pipeline/templates/skills/pipeline-config/SKILL.md` to list `implementing` with the three review stages, while retaining the one-dollar slope, two-times ceiling, project pin, explicit opt-in, and opt-out rules; run the documentation consistency search and stage tests, then commit as `docs(TICKET-132): document implementing cap scaling`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` exits `0`.
- `uv run --group dev pytest -q tests/test_config.py` exits `0`.
- `rg -l 'implementing.*review.*quick-review.*holistic-review' README.md pipeline/templates/pipeline.toml pipeline/templates/skills/pipeline-config/SKILL.md` prints all three named paths and exits `0`.
- `uv run --group dev pytest -q tests/test_stages.py` exits `0`.
- `uv run --group dev pytest -q` exits `0`.

## Decisions

`implementing` scales its default dollar cap from dispatcher-owned `plan_steps` and `plan_files` after an observed 21-step run exhausted its flat `$8` cap. The shared formula and two-times ceiling remain unchanged. A project-defined `max_usd` remains a pin unless the project sets `scale_usd = true`, and `scale_usd = false` opts out. User-facing configuration references must list implementing among the default-scaled stages.

## Rollback

Plan step 1 is riskiest because it raises implementing spend by default. If its focused or config-suite check fails, remove `implementing` from `USD_SCALED` in `pipeline/core/machine.py`, restore the review-only comments in `pipeline/core/machine.py` and `pipeline/daemon/supervisor.py`, and leave the committed `tests/test_config.py` regression red as evidence; do not alter `cap_for()` or project override semantics. If the change breaks after shipment, revert both implementation commits while retaining the triage reproduction commit so code and configuration documentation return to the same behavior.

## Thread

### 2026-09-12 05:01:13Z · new · escalation

TICKET-132 depends_on TICKET-129, which is escalated and can never reach done

### 2026-09-12 11:09:14Z · human · note · by=chezzijr

**resumed** by chezzijr -> `new`, reset ['no_result']

### 2026-09-12 11:18:48Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-12 11:24:00Z · triage · reproduction

Reproduced and committed `564b139`.

`cap_config()` excludes `implementing` because it is absent from `USD_SCALED`.

The focused 20-step test fails with the recorded assertion.

Expected fix files: `pipeline/core/machine.py` and `tests/test_config.py`.

### 2026-09-12 11:20:27Z · triage · session · session=01a09557-98dd-7f63-8e79-7bb9e7ea19ff

`triage` ran as session `01a09557-98dd-7f63-8e79-7bb9e7ea19ff`
- replay: `codex exec resume 01a09557-98dd-7f63-8e79-7bb9e7ea19ff`
- log: `.project/logs/TICKET-132-triage-b151ceb4.log`
- cost: unknown (the harness reported none)
- tokens: 3,042 out (633 thinking) · 433,354 in · 399,104 cache read · 0 cache write

### 2026-09-12 11:20:27Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced implementing cap scaling failure in a committed regression test

### 2026-09-12 11:23:39Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails as required
```
=================
____________ test_the_project_decides_which_stages_scale_their_cap _____________

    def test_the_project_decides_which_stages_scale_their_cap():
        """Implementing and review scale by default; projects can opt out."""
        d, _ = git_project()
        counters = {"plan_files": 0, "plan_steps": 20}
        assert "counters" in cap_config("review", stage_config("review", d), d, counters)
        implementing = cap_config("implementing", stage_config("implementing", d), d, counters)
>       assert "counters" in implementing, (
            "expected implementing's 20-step plan to receive its size counters")
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}

tests/test_config.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.12s ===============================

```
- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails on base `main` too -- the bug is not already fixed upstream
```
plementing, (
            "expected implementing's 20-step plan to receive its size counters")
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}

tests/test_config.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-t1_3u9io/base
      Built pipeline @ file:///tmp/pipeline-base-t1_3u9io/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 1.32s

```
- `files_declared` is empty
- plan step names no declared file: '1. Update `pipeline/core/machine.py` to add `implementing` to `USD_SCALED` and replace the review-only evidence comment with the recorded review and 21-step implementing cap kills; use `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` to prove a 20-step implementing plan receives counters and renders `$10`, run the focused and complete config tests, then commit as `fix(TICKET-132): scale implementing cap with plan size`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-12 11:26:42Z · planning · plan

Planned one implementation step across `pipeline/core/machine.py` and the committed `tests/test_config.py` regression.

Consulted DEC-047, DEC-077, and DEC-078. DEC-078 permits adding a scaled stage after an observed cap kill.

The initial CLI gate confirmed the reproduction but could not see planning's unadopted `files_declared` claim. Re-running Tier A with the exact sidecar claim supplied in memory printed `gate: PASS`.

### 2026-09-12 11:27:08Z · planning · session · session=01a09558-f0fd-7de3-9b88-8dae51757925

`planning` ran as session `01a09558-f0fd-7de3-9b88-8dae51757925`
- replay: `codex exec resume 01a09558-f0fd-7de3-9b88-8dae51757925`
- log: `.project/logs/TICKET-132-planning-eccc8cbd.log`
- cost: unknown (the harness reported none)
- tokens: 9,594 out (4,041 thinking) · 1,515,741 in · 1,454,208 cache read · 0 cache write

### 2026-09-12 11:27:08Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned evidence-backed implementing cap scaling through the existing bounded cap path

### 2026-09-12 11:28:18Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-12 11:23:39Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails on base `main` too -- the bug is not already fixed upstream
```
mplementing, (
            "expected implementing's 20-step plan to receive its size counters")
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}

tests/test_config.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-vu4w9hti/base
      Built pipeline @ file:///tmp/pipeline-base-vu4w9hti/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 55ms

```

### 2026-09-12 11:29:48Z · plan-validation · finding

Result: `fail`.

- Root cause vs symptom — pass: `implementing` is absent from `USD_SCALED`, so `cap_config()` withholds counters and `stage_cap()` returns `$8`.
- Decision conflict — pass: DEC-078 permits a new member after an observed cap kill. The plan preserves DEC-047 and DEC-077 paths.
- Scope discipline — pass: the code and regression changes trace to implementing cap scaling.
- Falsifiable criteria — pass: the focused test distinguishes the flat `$8` cap from the required `$10` cap.
- No research left — fail: the plan omits `README.md`, `pipeline/templates/pipeline.toml`, `pipeline/templates/skills/pipeline-config/SKILL.md`, and `pipeline/daemon/supervisor.py`. Each still describes scaling as review-only. Name these files and update those statements.
- Riskiest step — pass: rollback removes the set member, restores the comment, and retains the red regression.
- Regression surface — pass: project pins, explicit opt-out, the shared formula, and the ceiling are covered by the focused and complete config suites.
- Blast radius matches class — pass: one set-member behavior change plus documentation and regression updates remains a bugfix-sized change.

The first read probe was blocked because it included shell redirection. Plain `rg`, `grep`, and `sed` supplied the evidence; no item remains unverified.

### 2026-09-12 11:30:28Z · plan-validation · session · session=01a09560-21b3-7ce2-aba4-1e491ef985e1

`plan-validation` ran as session `01a09560-21b3-7ce2-aba4-1e491ef985e1`
- replay: `codex exec resume 01a09560-21b3-7ce2-aba4-1e491ef985e1`
- log: `.project/logs/TICKET-132-plan-validation-4be13e49.log`
- cost: unknown (the harness reported none)
- tokens: 4,152 out (2,171 thinking) · 471,644 in · 424,960 cache read · 0 cache write

### 2026-09-12 11:30:28Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ Plan leaves configuration documentation and spawn-path commentary describing review-only scaling

### 2026-09-12 11:35:31Z · planning · plan

Revised the plan to cover all six ticket files. The implementation step updates `USD_SCALED`, the spawn-path comment, and the committed regression. The documentation step updates `README.md`, the configuration template, and the shipped `pipeline-config` skill.

Consulted DEC-047, DEC-077, DEC-078, and DEC-084. DEC-078 permits adding `implementing` after the observed cap kill. DEC-084 keeps the configuration template and skill aligned.

The CLI gate saw the previously adopted two-file claim and reported the new documentation step undeclared. Re-running Tier A with the exact six-file sidecar claim printed `gate: PASS`.

### 2026-09-12 11:33:52Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails as required
```
=================
____________ test_the_project_decides_which_stages_scale_their_cap _____________

    def test_the_project_decides_which_stages_scale_their_cap():
        """Implementing and review scale by default; projects can opt out."""
        d, _ = git_project()
        counters = {"plan_files": 0, "plan_steps": 20}
        assert "counters" in cap_config("review", stage_config("review", d), d, counters)
        implementing = cap_config("implementing", stage_config("implementing", d), d, counters)
>       assert "counters" in implementing, (
            "expected implementing's 20-step plan to receive its size counters")
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}

tests/test_config.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails on base `main` too -- the bug is not already fixed upstream
```
mplementing, (
            "expected implementing's 20-step plan to receive its size counters")
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}

tests/test_config.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-xxfr7a8k/base
      Built pipeline @ file:///tmp/pipeline-base-xxfr7a8k/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 80ms

```
- plan step names no declared file: '2. Update `README.md`, `pipeline/templates/pipeline.toml`, and `pipeline/templates/skills/pipeline-config/SKILL.md` to list `implementing` with the three review stages, while retaining the one-dollar slope, two-times ceiling, project pin, explicit opt-in, and opt-out rules; run the documentation consistency search and stage tests, then commit as `docs(TICKET-132): document implementing cap scaling`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-12 11:35:17Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-12 11:23:39Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails on base `main` too -- the bug is not already fixed upstream
```
mplementing, (
            "expected implementing's 20-step plan to receive its size counters")
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}

tests/test_config.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.22s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-1_v_c76u/base
      Built pipeline @ file:///tmp/pipeline-base-1_v_c76u/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 63ms

```

### 2026-09-12 11:35:48Z · planning · session · session=01a09562-1c48-7960-8310-f09d24be8311

`planning` ran as session `01a09562-1c48-7960-8310-f09d24be8311`
- replay: `codex exec resume 01a09562-1c48-7960-8310-f09d24be8311`
- log: `.project/logs/TICKET-132-planning-447cd0ec.log`
- cost: unknown (the harness reported none)
- tokens: 7,182 out (3,171 thinking) · 1,005,147 in · 947,200 cache read · 0 cache write

### 2026-09-12 11:35:48Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Expanded the plan to cover implementing cap behavior and every review-only description

### 2026-09-12 11:36:58Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails as required
```
=================
____________ test_the_project_decides_which_stages_scale_their_cap _____________

    def test_the_project_decides_which_stages_scale_their_cap():
        """Implementing and review scale by default; projects can opt out."""
        d, _ = git_project()
        counters = {"plan_files": 0, "plan_steps": 20}
        assert "counters" in cap_config("review", stage_config("review", d), d, counters)
        implementing = cap_config("implementing", stage_config("implementing", d), d, counters)
>       assert "counters" in implementing, (
            "expected implementing's 20-step plan to receive its size counters")
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}

tests/test_config.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.13s ===============================

```
- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails on base `main` too -- the bug is not already fixed upstream
```
mplementing, (
            "expected implementing's 20-step plan to receive its size counters")
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}

tests/test_config.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.22s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-u0kid5ue/base
      Built pipeline @ file:///tmp/pipeline-base-u0kid5ue/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 50ms

```

### 2026-09-12 11:38:10Z · plan-validation · judgment

Plan passes all judgment items.

- Root cause vs symptom — pass. `implementing` is absent from `USD_SCALED`, so `cap_config()` omits counters and leaves the cap flat. Membership fixes shared policy, not only the test.
- Decision conflict — pass. The plan reuses existing counters, `stage_cap()`, and `cap_config()`. It preserves no-retry, pins, opt-ins, and the ceiling.
- Scope discipline — pass. Each file changes scaling, validates it, corrects path commentary, or documents configuration.
- Falsifiable criteria — pass. The focused test fails on missing counters and requires `$10`. Config, stage, full-suite, and three-path search checks can fail independently.
- No research left — pass. Both steps name files, symbols, expected cap, commands, and commits.
- Riskiest step — pass. The plan identifies increased default spend. Rollback removes membership, restores comments, retains the red test, or reverts both commits.
- Regression surface — pass. Risks include cap arithmetic, overrides, ceiling, rendered child cap, and documentation. Focused and config tests cover policy; broader suites cover integration.
- Blast radius matches class — pass. This bugfix changes two runtime files, one regression file, and three documentation files.

Unverified: independent source and decision inspection was blocked because the probe included prohibited stderr redirection. Scores rely on the bounded ticket and Tier A evidence.

### 2026-09-12 11:38:38Z · plan-validation · session · session=01a09568-0fd3-7d30-9e8f-cee34a8d8ede

`plan-validation` ran as session `01a09568-0fd3-7d30-9e8f-cee34a8d8ede`
- replay: `codex exec resume 01a09568-0fd3-7d30-9e8f-cee34a8d8ede`
- log: `.project/logs/TICKET-132-plan-validation-2580e576.log`
- cost: unknown (the harness reported none)
- tokens: 3,303 out (2,235 thinking) · 210,389 in · 188,288 cache read · 0 cache write

### 2026-09-12 11:38:39Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan fixes the shared scaling omission and covers regressions, documentation, and rollback

### 2026-09-12 18:06:40Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-12 18:07:54Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-12 11:23:39Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` fails on base `main` too -- the bug is not already fixed upstream
```
mplementing, (
            "expected implementing's 20-step plan to receive its size counters")
E       AssertionError: expected implementing's 20-step plan to receive its size counters
E       assert 'counters' in {'model': 'sonnet', 'effort': 'medium', 'write': True, 'max_usd': 8, ...}

tests/test_config.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.24s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-vtkc2cqo/base
      Built pipeline @ file:///tmp/pipeline-base-vtkc2cqo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 69ms

```

### 2026-09-12 18:07:55Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-13 · implementing · todo

1. [ ] Add `implementing` to `USD_SCALED` in `pipeline/core/machine.py` and correct `pipeline/daemon/supervisor.py` commentary.
2. [ ] Run the committed cap-scaling regression and config suite, then commit the runtime change.
3. [ ] Document default implementing scaling in `README.md`, `pipeline/templates/pipeline.toml`, and `pipeline/templates/skills/pipeline-config/SKILL.md`.
4. [ ] Run consistency, stage, and full-suite checks, then commit the documentation change.

### 2026-09-13 · implementing · completed

1. [x] Added `implementing` to `USD_SCALED` and corrected spawn commentary. Committed `9cad2e8`.
2. [x] The focused regression passed. `tests/test_config.py` passed: `31 passed in 0.98s`.
3. [x] Documented all four default-scaled stages. Committed `04f395b`.
4. [x] The consistency search printed all three required paths. `tests/test_stages.py` passed: `44 passed in 0.26s`. The full suite passed: `627 passed in 68.56s (0:01:08)`.

The regression's failing input was a 20-step implementing plan without counters. It now renders `$10` from its `$8` base cap.

### 2026-09-12 18:11:29Z · implementing · session · session=01a096cd-fb4b-71f3-ba22-d4ee9ed59a9e

`implementing` ran as session `01a096cd-fb4b-71f3-ba22-d4ee9ed59a9e`
- replay: `codex exec resume 01a096cd-fb4b-71f3-ba22-d4ee9ed59a9e`
- log: `.project/logs/TICKET-132-implementing-233f310a.log`
- cost: unknown (the harness reported none)
- tokens: 4,516 out (1,206 thinking) · 773,765 in · 723,456 cache read · 0 cache write

### 2026-09-12 18:11:29Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Scaled implementing's default cap and documented all four default-scaled stages

### 2026-09-13 · review · findings

No blocking findings.

The delta adds `implementing` to the shared default-scaling set. It preserves the shared formula, two-times ceiling, project pin, and explicit override behavior. The regression proves a 20-step plan raises the implementing cap from `$8` to `$10`. All three user-facing references list the four default-scaled stages. `git diff --check main...HEAD` and the required documentation search passed.

I could not rerun pytest in this read-only stage. Uv stopped before collection with `Read-only file system (os error 30)` under `/home/chezzijr/.cache/uv`, and the guard rejected an environment override. The implementing entry records `31`, `44`, and `627` passing tests for the required suites.

### 2026-09-12 18:13:10Z · review · session · session=01a096d1-3e2e-7123-8260-ab482a05fafa

`review` ran as session `01a096d1-3e2e-7123-8260-ab482a05fafa`
- replay: `codex exec resume 01a096d1-3e2e-7123-8260-ab482a05fafa`
- log: `.project/logs/TICKET-132-review-8edab120.log`
- cost: unknown (the harness reported none)
- tokens: 3,502 out (1,638 thinking) · 472,294 in · 436,096 cache read · 0 cache write

### 2026-09-12 18:13:10Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the cap-scaling delta with no blocking findings

### 2026-09-12 18:14:33Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-12 18:14:35Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/132


Current branch ticket/132 is up to date.
Already up to date.
Updating 95a979d..04f395b
Fast-forward
 README.md                                          |  8 ++++----
 pipeline/core/machine.py                           | 17 +++++++++--------
 pipeline/daemon/supervisor.py                      |  2 +-
 pipeline/templates/pipeline.toml                   |  8 ++++----
 pipeline/templates/skills/pipeline-config/SKILL.md | 11 +++++------
 tests/test_config.py                               | 12 +++++++-----
 6 files changed, 30 insertions(+), 28 deletions(-)

```

### 2026-09-12 18:14:35Z · merging · decision

decision recorded as `DEC-132`
