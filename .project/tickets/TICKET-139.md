---
id: TICKET-139
stage: done
class: bugfix
branch: ticket/139
test_file: tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
files_declared:
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- pipeline/templates/skills/file-ticket/SKILL.md
- tests/test_dispatch.py
- tests/test_machine.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 3
  plan_files: 5
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 01a0b565-7be8-7900-8421-de7f26511300
  replay: codex exec resume 01a0b565-7be8-7900-8421-de7f26511300
  log: .project/logs/TICKET-139-review-54a3a587.log
  cost_usd: null
approved_by: chezzijr
approved_at: '2026-09-18T16:37:23.512594+00:00'
---

## Summary

An escalated `depends_on` target escalates its dependent, and nothing un-escalates it

Expected change files: `pipeline/core/machine.py`, `pipeline/daemon/supervisor.py`, `pipeline/templates/skills/file-ticket/SKILL.md`, `tests/test_machine.py`, `tests/test_dispatch.py`.

`dep_unsatisfiable()` treats every terminal stage except `done` as permanent -- `pipeline/core/machine.py:379` on main at f09c5d6:

    if stages[dep] in TERMINAL and stages[dep] != "done":
        return f"{cur} depends_on {dep}, which is {stages[dep]} and can never reach done"

`start()` (`pipeline/daemon/supervisor.py:878`) then `bail()`s the dependent to `escalated`. But `escalated` is not permanent: a human resumes it with `pipeline resume`, and it can then reach `done`. The dependent is now terminal itself, `start()` returns early for terminal stages (`supervisor.py:827`), and it never resumes and never shows a `waiting:` block. Seen in a real project: TICKET-131 with `depends_on: [TICKET-134]` sat escalated after 134 was resumed and finished; it had to be resumed by hand.

Expected: a dependency at `escalated` makes the dependent WAIT, exactly like a dependency at any non-terminal stage -- `waiting: {on: TICKET-134, stage: escalated}`, visible in `pipeline ls` -- and the dependent advances on its own once the dependency reaches `done`. `rejected`, a missing id and a cycle still escalate the dependent (they truly can never reach `done`). A test: dependency at `escalated` -> `dep_unsatisfiable()` returns `None` and `dep_holder()` returns `(dep, "escalated")`; flip the dependency to `done` -> the dependent advances out of `new`. The file-ticket skill's `depends_on` paragraph (SKILL.md:153-157, "a dependency that is missing, `escalated`, `rejected`, or part of a cycle escalates the dependent") must say the same.

## Reproduction

Test: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume`

Command: `uv run --group dev pytest -q tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume`

Output:

```
E       AssertionError: assert 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' is None
```

expect: TICKET-002 depends_on TICKET-001, which is escalated and can never reach done

## Digest

- `pipeline/core/machine.py::dep_unsatisfiable()` is the only transitive graph walk; it must keep rejecting missing ids, `rejected` dependencies, and cycles while allowing `escalated` dependencies to wait.
- `pipeline/core/machine.py::dep_holder()` already returns a direct `escalated` dependency as `(id, "escalated")`; keep the direct-only and sorted-holder behavior.
- `pipeline/daemon/supervisor.py::start()` checks dependencies before advancing `new`; `note_wait()` persists advisory `{on, stage, since}` state and must clear it when the dependency reaches `done`.
- A resolved dependency at `new` can only replace a dependency wait, because file-conflict checks run after the `new` advance; remove that wait in memory and let `advance()` persist the removal.
- A resolved dependency after `new` must fall through to the existing inflight and parked-file holder checks; their single `note_wait()` call must choose the final wait reason without a dependency-level clear.
- `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` is the committed failing reproduction at `b44338c`; `tests/test_dispatch.py` has the project fixtures and existing dependency integration tests.
- `pipeline/templates/skills/file-ticket/SKILL.md` is the installed user interface; its ordering paragraph currently misstates `escalated` as permanent.
- Keep `escalated` in `TERMINAL`: its scheduler, TUI, and worktree-evidence semantics remain unchanged outside dependency satisfiability.

## Decisions checked

DEC-100 applies. This plan supersedes only its rule that an `escalated` dependency can never reach `done`; it retains human ownership, direct holders, disk-based recomputation, and missing-id, rejected, and cycle escalation.
DEC-048 applies. `waiting` remains advisory, changes only when its reason changes, and clears when the recomputed dependency holder disappears.
DEC-060 applies. It confirms that `escalated` is terminal for scheduling but actionable and recoverable by a human.
DEC-105 applies. A tick must make one final `note_wait()` decision so a persistent file holder retains its `since` value and does not reset the stale clock.
DEC-029 applies. File conflicts remain below the `new` advance, and parked-file holders remain restricted to `merging`.
Search terms: `depends_on`, `dependency`, `escalated`, `resume`, `terminal`, `waiting`, `note_wait`, `holder`, `stale`.

## Plan

1. Update `pipeline/core/machine.py` so `dep_unsatisfiable()` treats only `rejected` as a permanent terminal dependency, revises its docstring, and preserves missing-id and cycle detection; retain and run `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` plus the existing unsatisfiable-dependency test.
2. Update `pipeline/daemon/supervisor.py` so a direct dependency holder keeps the existing early `note_wait()` return, while a resolved dependency at `new` removes `waiting` in memory before `advance()` saves; preserve the existing post-`new` inflight and parked-file computation as the only `note_wait()` path for non-`new` tickets, then add `tests/test_dispatch.py::test_an_escalated_dependency_waits_then_advances_after_resume` and `tests/test_dispatch.py::test_a_resolved_dependency_keeps_one_stable_file_wait`, with the latter holding a non-`new` ticket behind an inflight file owner across two ticks and asserting the full `{on, file, since}` record stays unchanged.
3. Update `pipeline/templates/skills/file-ticket/SKILL.md` to state that missing, rejected, and cyclic dependencies escalate while an escalated dependency waits for human resume, then run the targeted dependency tests and the dispatcher suite.

## Acceptance criteria

- `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` passes and proves `dep_unsatisfiable()` returns `None` while `dep_holder()` returns the escalated dependency.
- `tests/test_machine.py::test_a_dependency_that_can_never_land_escalates_instead_of_waiting` passes and preserves escalation for rejected, missing, and cyclic dependencies.
- `tests/test_dispatch.py::test_an_escalated_dependency_waits_then_advances_after_resume` passes and proves `pipeline ls` data records the escalated holder, then the dependent leaves `new` and clears `waiting` after the blocker reaches `done`.
- `tests/test_dispatch.py::test_a_resolved_dependency_keeps_one_stable_file_wait` passes and proves a completed dependency plus a persistent file holder retains one unchanged `{on, file, since}` record across two ticks.
- `rg -U "missing,[\\s\\S]*rejected[\\s\\S]*escalated[\\s\\S]*waits" pipeline/templates/skills/file-ticket/SKILL.md` exits `0` and finds the corrected dependency guidance.
- `uv run --group dev pytest -q tests/test_machine.py tests/test_dispatch.py` exits `0`.

## Decisions

supersedes: DEC-100 -- an `escalated` dependency can reach `done` after human resume, so it is waitable rather than permanently unsatisfiable.
An `escalated` dependency blocks through `dep_holder()` and records advisory `{on, stage, since}` state. Missing ids, `rejected` dependencies, and reachable cycles still escalate without charging a counter.
Keep `escalated` in the global `TERMINAL` set. Only dependency satisfiability treats it as recoverable; terminal cleanup and worktree preservation retain their existing behavior.
Recompute dependencies from ticket files every tick. Clear a resolved dependency wait before advancing the dependent, and never read `waiting` as control state.
Make at most one `note_wait()` decision per tick. A resolved dependency after `new` falls through to the file-holder decision so a persistent file wait keeps its original `since` value.
Keep holder reporting direct-only and sorted. Use the transitive graph walk only to detect missing ids and cycles.

## Rollback

The riskiest step is step 2 because it changes when `start()` clears advisory state. If its dispatcher tests fail on save ordering, keep the machine classification fix, remove the new-branch clear, and let the existing post-`new` `note_wait()` clear the stale display on the next tick while automatic advancement remains intact.
## Thread

### 2026-09-18 16:19:00Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-18 16:25:00Z · triage · finding

Reproduced and committed `b44338c`.

`pipeline/core/machine.py:379` treats every terminal dependency except `done` as unsatisfiable:

```
if stages[dep] in TERMINAL and stages[dep] != "done":
    return f"{cur} depends_on {dep}, which is {stages[dep]} and can never reach done"
```

`escalated` is terminal but resumable, so this prevents `dep_holder()` from reporting the wait.

The nearby `dep_holder()` returns each direct dependency whose stage is not `done`.

Expected fix files: `pipeline/core/machine.py`, `pipeline/daemon/supervisor.py`, `pipeline/templates/skills/file-ticket/SKILL.md`, `tests/test_machine.py`, and `tests/test_dispatch.py`.

### 2026-09-18 16:20:47Z · triage · session · session=01a0b550-98cb-7cb2-8336-8765197e3ce5

`triage` ran as session `01a0b550-98cb-7cb2-8336-8765197e3ce5`
- replay: `codex exec resume 01a0b550-98cb-7cb2-8336-8765197e3ce5`
- log: `.project/logs/TICKET-139-triage-24afff6d.log`
- cost: unknown (the harness reported none)
- tokens: 3,194 out (536 thinking) · 449,885 in · 414,464 cache read · 0 cache write

### 2026-09-18 16:20:47Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced escalated dependency classification with a failing machine test.

### 2026-09-18 16:24:52Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails as required
```
== FAILURES ===================================
_____________ test_an_escalated_dependency_waits_for_human_resume ______________

    def test_an_escalated_dependency_waits_for_human_resume():
        deps = {"TICKET-002": ["TICKET-001"]}
        stages = {"TICKET-001": "escalated", "TICKET-002": "new"}
    
>       assert M.dep_unsatisfiable("TICKET-002", deps, stages) is None
E       AssertionError: assert 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' is None
E        +  where 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7fc30c60bd80>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7fc30c60bd80> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails on base `main` too -- the bug is not already fixed upstream
```
KET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7f4375ee8a40>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7f4375ee8a40> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-2h1z6na4/base
      Built pipeline @ file:///tmp/pipeline-base-2h1z6na4/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 994ms

```
- `files_declared` is empty
- plan step names no declared file: '1. Update `pipeline/core/machine.py` so `dep_unsatisfiable()` treats only `rejected` as a permanent terminal dependency, revises its docstring, and preserves missing-id and cycle detection; retain and run `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` plus the existing unsatisfiable-dependency test.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Update `pipeline/daemon/supervisor.py` to pass either the direct dependency holder or `None` through `note_wait()` before returning, then add `tests/test_dispatch.py::test_an_escalated_dependency_waits_then_advances_after_resume` that observes `{on, stage}` while blocked, changes the blocker to `done`, and verifies the dependent advances from `new` with no stale wait.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Update `pipeline/templates/skills/file-ticket/SKILL.md` to state that missing, rejected, and cyclic dependencies escalate while an escalated dependency waits for human resume, then run the targeted dependency tests and the dispatcher suite.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-18 16:26:06Z · planning · finding

Planned the five-file change and explicit DEC-100 supersession.

The self-gate reproduced the test failure on the branch and base. Its only plan findings came from the pre-adoption ticket state: `` `files_declared` is empty `` and three consequent undeclared-path findings.

The planning sidecar now declares all five paths. The dispatcher adopts that claim before its plan-validation gate, so the next gate evaluates the complete plan state.

### 2026-09-18 16:26:24Z · planning · session · session=01a0b552-0d38-7770-935c-0a6ac8ffd969

`planning` ran as session `01a0b552-0d38-7770-935c-0a6ac8ffd969`
- replay: `codex exec resume 01a0b552-0d38-7770-935c-0a6ac8ffd969`
- log: `.project/logs/TICKET-139-planning-508c66ad.log`
- cost: unknown (the harness reported none)
- tokens: 11,994 out (6,640 thinking) · 1,236,008 in · 1,169,920 cache read · 0 cache write

### 2026-09-18 16:26:24Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned resumable dependency waiting while preserving permanent dependency failures.

### 2026-09-18 16:28:47Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails as required
```
== FAILURES ===================================
_____________ test_an_escalated_dependency_waits_for_human_resume ______________

    def test_an_escalated_dependency_waits_for_human_resume():
        deps = {"TICKET-002": ["TICKET-001"]}
        stages = {"TICKET-001": "escalated", "TICKET-002": "new"}
    
>       assert M.dep_unsatisfiable("TICKET-002", deps, stages) is None
E       AssertionError: assert 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' is None
E        +  where 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7f6dc85cbd80>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7f6dc85cbd80> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails on base `main` too -- the bug is not already fixed upstream
```
CKET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7f362b6eca40>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7f362b6eca40> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-7p8ju5zt/base
      Built pipeline @ file:///tmp/pipeline-base-7p8ju5zt/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 93ms

```

### 2026-09-18 16:30:21Z · plan-validation · finding

- **Decision conflict — fail.** Step 2 can call `note_wait(None)` after dependencies finish, then call `note_wait()` again for a file holder. A persistent file conflict would clear and re-set `waiting` every tick. DEC-105 forbids this because repeated saves reset the stale clock. Consolidate dependency, inflight-file, and parked-file holders into one final call, or limit dependency clearing to the `new` advance path.
- **Root cause vs symptom — pass.** The plan corrects the false permanent-terminal classification while preserving genuine impossibility checks.
- **Scope discipline — pass.** All five files serve behavior, tests, or the required installed interface.
- **Falsifiable criteria — pass.** The machine and dispatcher assertions distinguish incorrect classification, waiting, advancement, and cleanup.
- **No research left — fail.** The plan names files and functions but leaves the DEC-105 holder interaction unresolved.
- **Riskiest step — pass.** Step 2 has a bounded fallback that preserves automatic advancement.
- **Regression surface — fail.** Add a combined regression where dependencies are done while a file holder persists; prove one stable wait record.
- **Blast radius matches class — pass.** Three production/interface files and two test files fit this bugfix.

### 2026-09-18 16:30:58Z · plan-validation · session · session=01a0b559-6598-7ff2-841a-d0716b65bd2a

`plan-validation` ran as session `01a0b559-6598-7ff2-841a-d0716b65bd2a`
- replay: `codex exec resume 01a0b559-6598-7ff2-841a-d0716b65bd2a`
- log: `.project/logs/TICKET-139-plan-validation-89be7e3f.log`
- cost: unknown (the harness reported none)
- tokens: 5,175 out (3,311 thinking) · 441,181 in · 403,328 cache read · 0 cache write

### 2026-09-18 16:30:58Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ Plan must preserve DEC-105's single note_wait call across dependency and file waits.

### 2026-09-18 16:34:02Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails as required
```
== FAILURES ===================================
_____________ test_an_escalated_dependency_waits_for_human_resume ______________

    def test_an_escalated_dependency_waits_for_human_resume():
        deps = {"TICKET-002": ["TICKET-001"]}
        stages = {"TICKET-001": "escalated", "TICKET-002": "new"}
    
>       assert M.dep_unsatisfiable("TICKET-002", deps, stages) is None
E       AssertionError: assert 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' is None
E        +  where 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7fbbcfa1fd80>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7fbbcfa1fd80> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails on base `main` too -- the bug is not already fixed upstream
```
CKET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7fa6079e4a40>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7fa6079e4a40> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.19s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-tra7r1d7/base
      Built pipeline @ file:///tmp/pipeline-base-tra7r1d7/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 44ms

```

### 2026-09-18 16:34:13Z · planning · finding

Revised step 2 to preserve DEC-105's single wait decision.

The dependency holder still returns through `note_wait()`. A resolved dependency at `new` removes `waiting` in memory before `advance()` saves. A resolved dependency after `new` falls through to the existing file-holder computation and its single `note_wait()` call.

Added a planned regression for a completed dependency plus a persistent file holder across two ticks. It asserts the full `{on, file, since}` record stays unchanged.

Consulted DEC-029, DEC-048, DEC-060, DEC-100, and DEC-105. The self-gate reported `gate: PASS`.

### 2026-09-18 16:34:39Z · planning · session · session=01a0b55b-5ef5-7fd1-a910-fa967b51601b

`planning` ran as session `01a0b55b-5ef5-7fd1-a910-fa967b51601b`
- replay: `codex exec resume 01a0b55b-5ef5-7fd1-a910-fa967b51601b`
- log: `.project/logs/TICKET-139-planning-9c0ce64e.log`
- cost: unknown (the harness reported none)
- tokens: 6,604 out (3,534 thinking) · 841,801 in · 781,824 cache read · 0 cache write

### 2026-09-18 16:34:39Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Revised the plan to preserve one stable wait record across dependency and file holders.

### 2026-09-18 16:35:47Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails as required
```
== FAILURES ===================================
_____________ test_an_escalated_dependency_waits_for_human_resume ______________

    def test_an_escalated_dependency_waits_for_human_resume():
        deps = {"TICKET-002": ["TICKET-001"]}
        stages = {"TICKET-001": "escalated", "TICKET-002": "new"}
    
>       assert M.dep_unsatisfiable("TICKET-002", deps, stages) is None
E       AssertionError: assert 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' is None
E        +  where 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7f96afe1fd80>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7f96afe1fd80> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails on base `main` too -- the bug is not already fixed upstream
```
CKET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7f8f1d9eca40>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7f8f1d9eca40> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-otvuj5p3/base
      Built pipeline @ file:///tmp/pipeline-base-otvuj5p3/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 64ms

```

### 2026-09-18 16:36:35Z · plan-validation · finding

- **Root cause vs symptom — pass.** The plan removes `escalated` from permanent dependency failure classification instead of bypassing the failing assertion.
- **Decision conflict — pass.** It explicitly supersedes DEC-100 only for resumable escalation. It preserves DEC-048 advisory state, DEC-105's single wait decision, and DEC-029's file-holder scope.
- **Scope discipline — pass.** Each of the five files implements behavior, regression coverage, or required user guidance.
- **Falsifiable criteria — pass.** Assertions distinguish waiting from escalation, verify automatic advancement, and compare the complete file-wait record across two ticks.
- **No research left — pass.** Every step names concrete files, functions, tests, and the required save path behavior.
- **Riskiest step — pass.** Step 2 identifies wait-state clearing as riskiest. Its fallback preserves classification and automatic advancement while deferring display cleanup.
- **Regression surface — pass.** Existing tests preserve rejected, missing, and cyclic escalation. New dispatcher tests cover dependency display, clearing, advancement, and stable file waits.
- **Blast radius matches class — pass.** Three production/interface files and two test files fit this dependency bugfix.

### 2026-09-18 16:36:58Z · plan-validation · session · session=01a0b55f-cb14-7352-8daf-7ad810a328a1

`plan-validation` ran as session `01a0b55f-cb14-7352-8daf-7ad810a328a1`
- replay: `codex exec resume 01a0b55f-cb14-7352-8daf-7ad810a328a1`
- log: `.project/logs/TICKET-139-plan-validation-4a40bb93.log`
- cost: unknown (the harness reported none)
- tokens: 2,518 out (1,248 thinking) · 332,580 in · 288,896 cache read · 0 cache write

### 2026-09-18 16:36:58Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Revised plan preserves one wait-state decision and covers resumable dependencies.

### 2026-09-18 16:37:23Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-18 16:39:24Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails as required
```
== FAILURES ===================================
_____________ test_an_escalated_dependency_waits_for_human_resume ______________

    def test_an_escalated_dependency_waits_for_human_resume():
        deps = {"TICKET-002": ["TICKET-001"]}
        stages = {"TICKET-001": "escalated", "TICKET-002": "new"}
    
>       assert M.dep_unsatisfiable("TICKET-002", deps, stages) is None
E       AssertionError: assert 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' is None
E        +  where 'TICKET-002 depends_on TICKET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7fb683c1fd80>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7fb683c1fd80> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume` fails on base `main` too -- the bug is not already fixed upstream
```
CKET-001, which is escalated and can never reach done' = <function dep_unsatisfiable at 0x7fcc46fe8a40>('TICKET-002', {'TICKET-002': ['TICKET-001']}, {'TICKET-001': 'escalated', 'TICKET-002': 'new'})
E        +    where <function dep_unsatisfiable at 0x7fcc46fe8a40> = M.dep_unsatisfiable

tests/test_machine.py:195: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_an_escalated_dependency_waits_for_human_resume
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.20s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-9v8ihrr3/base
      Built pipeline @ file:///tmp/pipeline-base-9v8ihrr3/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 78ms

```

### 2026-09-18 16:39:24Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-18 16:40:00Z · implementing · todo

1. [in progress] Classify only rejected dependencies as permanently unsatisfiable.
2. [pending] Preserve one stable file wait after a dependency resolves.
3. [pending] Correct the file-ticket dependency guidance.
4. [pending] Run the targeted tests and dispatcher suite, then commit.

### 2026-09-18 16:41:00Z · implementing · finding

1. [done] `dep_unsatisfiable()` rejects only `rejected`; missing ids and cycles still reject.
2. [done] A resolved dependency clears `waiting` before a `new` ticket advances.
3. [done] Non-`new` tickets retain one file-holder wait decision and its `since` value.
4. [done] Updated dependency guidance and committed `cd4687b`.

`uv run --group dev pytest -q tests/test_machine.py tests/test_dispatch.py` passed: 144 tests.

`rg -U "missing,[\\s\\S]*rejected[\\s\\S]*escalated[\\s\\S]*waits" pipeline/templates/skills/file-ticket/SKILL.md` passed.

### 2026-09-18 16:42:00Z · implementing · session · session=01a0b563-1adb-7a73-b534-f5cd155b38ec

`implementing` ran as session `01a0b563-1adb-7a73-b534-f5cd155b38ec`
- replay: `codex exec resume 01a0b563-1adb-7a73-b534-f5cd155b38ec`
- log: `.project/logs/TICKET-139-implementing-0d02b0c4.log`
- cost: unknown (the harness reported none)
- tokens: 5,611 out (1,364 thinking) · 648,379 in · 600,320 cache read · 0 cache write

### 2026-09-18 16:42:00Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Escalated dependencies now wait for resume and advance after completion.

### 2026-09-18 16:44:21Z · review · finding

No blocking findings.

The four acceptance tests passed. The documentation matcher and `git diff --check` also passed.

The full scoped run passed 139 tests. Five unrelated daemon-socket tests could not bind AF_UNIX in this sandbox: `PermissionError: [Errno 1] Operation not permitted`.

The delta preserves rejected, missing, and cyclic escalation. It makes `escalated` waitable and keeps one stable file-wait decision.

### 2026-09-18 16:44:40Z · review · session · session=01a0b565-7be8-7900-8421-de7f26511300

`review` ran as session `01a0b565-7be8-7900-8421-de7f26511300`
- replay: `codex exec resume 01a0b565-7be8-7900-8421-de7f26511300`
- log: `.project/logs/TICKET-139-review-54a3a587.log`
- cost: unknown (the harness reported none)
- tokens: 5,661 out (2,604 thinking) · 709,058 in · 658,816 cache read · 0 cache write

### 2026-09-18 16:44:40Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed resumable dependency handling with no blocking findings.

### 2026-09-18 16:45:50Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-18 16:45:52Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/139


Rebasing (1/2)Rebasing (2/2)Successfully rebased and updated refs/heads/ticket/139.
Already up to date.
Updating d33bfb5..6a07172
Fast-forward
 pipeline/core/machine.py                       | 11 +++---
 pipeline/daemon/supervisor.py                  |  5 +++
 pipeline/templates/skills/file-ticket/SKILL.md |  6 +--
 tests/test_dispatch.py                         | 52 ++++++++++++++++++++++++++
 tests/test_machine.py                          | 12 +++++-
 5 files changed, 76 insertions(+), 10 deletions(-)

```

### 2026-09-18 16:45:52Z · merging · decision

decision recorded as `DEC-139`
