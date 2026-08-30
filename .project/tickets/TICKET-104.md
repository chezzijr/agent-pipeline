---
id: TICKET-104
stage: done
class: bugfix
branch: ticket/104
test_file: tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/gate.py
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_gate.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 10
  plan_files: 5
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 3008f32b-f4b9-4ae3-94c8-194178cc36ae
  log: .project/logs/TICKET-104-review-3008f32b.log
  cost_usd: 1.6258244999999998
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified the load-bearing assumption empirically rather
  than trusting the plan: pytest -q --deselect nosuch.py::test_x exits 0 and runs
  the rest, so excluding a node base does not have is a no-op and dropping the copy
  leaves the base suite run correct. It takes the smaller of the two shapes the ticket
  offered -- delete _copy_tests from _base_suite, keep it in _base_findings -- and
  documents the asymmetry in both docstrings so it cannot be tidied back. Step 5 is
  what keeps the fix honest: a regression test that the TICKET-089 case, a suite red
  on both for a reason neither branch introduced, still returns environment after
  the copy is gone. Step 9 documents the caveat for a runner that errors on an unknown
  selector rather than ignoring it. Nothing fenced.'
approved_at: '2026-08-30T11:19:44.283040+00:00'
---

## Summary

Reviewed and passed, no blocking findings. The delta is four commits
(`b5c9d73`..`8f2b18f`) over five files, and it matches `## Plan` step for
step -- no drift.

The fix is one deleted call: `_base_suite()` (`pipeline/core/gate.py:459`)
no longer calls `_copy_tests()`, so the base suite run judges base's OWN
test files. `_base_findings()` (`gate.py:402`) keeps its copy (DEC-017).
The branch's defect in shared test code can no longer ride onto base and
turn the branch's own bug into an `ENVIRONMENT` verdict that charges
nothing. The ticket's nodes are kept out of the base run by
`test_suite_without_new`'s selector, a no-op for a node base lacks.

I re-ran every acceptance-criteria check: `uv run --group dev pytest -q
tests` prints `501 passed`, the four named tests pass,
`./pipeline/hooks/test_dangerous_commands.py` prints `guard: all passed`,
and the three greps report `2` / `0` / non-zero in each doc file.

One non-blocking nit, in `## Thread`: `tests/test_gate.py:416` leaks a
temp dir.

TICKET-089 added a base re-run so a suite that is red for the operator's
environment stops being charged to the ticket. It copies the branch's test
files onto the base checkout before running the suite there:

    # pipeline/core/gate.py, _base_suite()
    _copy_tests(wd, base_wt, tests)     # the whole FILE each listed test lives in
    code, out = run_cmd(format_tests_cmd(cfg["test_suite_without_new"], tests), base_wt)

`_copy_tests` copies `test.split("::")[0]` -- the file, not the one test. So
every OTHER new test in that file is carried onto base too, where it runs
against base's code, which does not have the branch's feature. It fails there.
The suite is then red in both places, and `gate()` reports:

    ENVIRONMENT: suite excluding `tests/test_cli.py::test_decisions_command_lists_decision_records`
    is RED -- pre-existing breakage, and it is RED on base `main` too, so it is
    not this branch's doing and no plan can fix it.

It was this branch's doing. Observed on TICKET-101 at 2026-08-30 10:39:31Z:
that branch's `tests/test_cli.py` carried a second new test with a wrong
assertion, and the ticket escalated as `environment`, charging no counter, with
a message telling the operator to go fix their machine.

That is the exact inversion the verdict exists to prevent. An environment
finding is trusted precisely because it says "no plan can fix this", and here a
plan could -- the test was one line wrong.

The copy is not itself wrong: the base run needs the branch's test file, or the
listed test does not exist on base at all. What is wrong is running the WHOLE
suite against a checkout carrying half a branch.

Expected: a suite red on base is only evidence of an environment problem when
base's redness does not come from the branch's own new tests. Two shapes the
plan may weigh, and it should say which and why:

- Run the base suite on a checkout of base WITHOUT the branch's test files
  copied in, and exclude the ticket's own tests there. The copy is needed for
  the per-test base run (`_base_findings`), not for the suite run.
- Compare the two runs by which tests failed rather than by exit code, and
  count only failures present in both AND absent from the branch's new tests.

Constraint: `suite_ran()` (`pipeline/core/gate.py`) must still gate the verdict
on evidence a run happened, and a genuinely broken environment -- the
TICKET-089 case, an operator's `TasksMax` making 473 unrelated tests fail --
must still classify as `environment` and charge nothing.

Falsifiable: a branch whose new test file contains one failing test that base's
code cannot satisfy, where the gate today returns `environment` and afterwards
returns `bad-plan`; plus the TICKET-089 case, a suite failing identically on
both for a reason neither branch introduced, which must still return
`environment`.

Anchors: `_base_suite()` and `_copy_tests()` in `pipeline/core/gate.py`,
`environment_only()` and `ENVIRONMENT_MARK` in the same file, `gate_result()`
at `pipeline/daemon/supervisor.py`, and the `("plan-validation", "environment")`
row in `pipeline/core/machine.py` -- the row is right and does not change; only
the evidence feeding it does. That row is fenced, so leave it alone and this
ticket stays unfenced.

## Reproduction

`tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file`

Run: `uv run --group dev pytest -q tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file`

Failure:
```
AssertionError: ['ENVIRONMENT: suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, and it is RED on base `ma...al output, already quoted in the `## Thread` entry `2026-08-30 10:42:32Z · plan-validation · gate · verdict=FAIL` --*']
assert not True
```
expect: is RED on base

## Digest

- Files touched: `pipeline/core/gate.py` (the fix), `tests/test_gate.py` (the committed repro plus one regression guard), `CLAUDE.md`, `README.md`, `pipeline/templates/skills/pipeline-config/SKILL.md` (documentation).
- Key functions: `_base_suite()` (`pipeline/core/gate.py:383`) checks out base, calls `_copy_tests()`, then runs `test_suite_without_new` there; `_copy_tests()` (`pipeline/core/gate.py:304`) copies `test.split("::")[0]`, the whole FILE; `_base_findings()` (`pipeline/core/gate.py:313`) needs that copy and keeps it; `suite_ran()` (`pipeline/core/gate.py:368`); `environment_only()` and `ENVIRONMENT_MARK` (`pipeline/core/gate.py:172`).
- Entry points: `gate()` (`pipeline/core/gate.py:411`) calls `_base_suite()` only when the worktree suite exits non-zero AND `suite_ran()` is true; `gate_result()` (`pipeline/daemon/supervisor.py:987`) turns an all-`ENVIRONMENT: ` failure list into `environment`; `gate()` returns only findings that do not start with `ok:`, so an `ok:` line never blocks `environment_only()`.
- The design choice this ticket asked for: drop the `_copy_tests(wd, base_wt, tests)` call from `_base_suite()` only. Base then runs its OWN test files, and the ticket's own nodes are already excluded there by `test_suite_without_new`'s selector. The other shape the ticket weighed -- comparing which test NAMES failed in the two runs -- needs per-runner output parsing; the test commands are project configuration (`pipeline/templates/pipeline.toml` ships pytest, cargo and jest forms), so no parser in this codebase can read them all. `suite_ran()` stays the only evidence test, unchanged, so the ticket's constraint holds.
- Gotcha: an exclusion selector naming a node base does not have must be a no-op, or a ticket that ADDS a test file loses the environment verdict. Verified for pytest on 2026-08-30 in a one-test throwaway project: `pytest -q --deselect nosuch.py::test_x` exits 0 and prints `1 passed`.
- Gotcha: `_base_findings()` must keep the copy (DEC-017). Base has no branch test at all otherwise, and a missing file exits non-zero, which reads as a successful reproduction.
- Gotcha: `_base_findings()` copies `tests/test_gate.py` onto base and imports it there (DEC-017), so a new test in that file may use only names base already has. Today's imports there: `re`, `shutil`, `subprocess`, `tempfile`, `Path`, `helpers.FIXTURE`, `helpers.project`, `ticket as T`, `project_config`, `_base_findings`, `_dedupe`, `gate`, `plan_steps`, `transition`, `gate_result`.
- Gotcha: `_unsafe_rel()` stays in `_base_suite()` even though nothing there writes a path any more. Dropping it would give a ticket whose paths `_base_findings()` refuses a half-consulted base, and a non-empty `why` is DEC-089's fail-closed arm.
- Baseline measured 2026-08-30 in this worktree: `uv run --group dev pytest -q tests` prints `1 failed, 482 passed in 41.11s`, and `uv run --group dev pytest -q tests/test_gate.py` prints `1 failed, 72 passed`. The single failure in both is this ticket's repro test.
- `machine.FENCED` names `.project/pipeline.toml`, `pipeline/hooks/dangerous-commands.py`, `pipeline/harnesses/claude-code.toml`, `transition`/`CONTROL_FIELDS`/`FENCED`, `validate_meta`, `strip_settings_sources` and `.project/stages/`. None of the five files this plan touches is fenced, so the ticket stays unfenced.

## Decisions checked

Grep terms used in `.project/decisions/`: `_base_suite`, `_copy_tests`, `environment`, `ENVIRONMENT`, `suite_ran`, `base run`, `base suite`. None of the records below carries a `superseded-by:` line.

- DEC-089 -- the base suite re-run and the `ENVIRONMENT: ` prefix. This plan keeps every clause: `suite_ran()` judges base's run as it judges the worktree's, the prefix stays a `startswith` allowlist, an unproven question keeps `bad-plan`, `environment` fires at `plan-validation` only, and the phrase `RED -- pre-existing breakage` stays inside the finding. DEC-089 nowhere requires the copy: copying was TICKET-089's implementation, not a clause of the record.
- DEC-017 -- "the branch's test file is copied onto base; base is never asked for its own copy". That clause scopes to the reproduction run, `_base_findings()`, the only run DEC-017 was written about, and this plan leaves it copying. The suite run is a later, separate run (TICKET-089), and only that one changes. DEC-017's "test files the gate copies onto base may only import what base has" rule therefore still binds `tests/test_gate.py`.
- DEC-090 -- the exit-0 fall-through through `_base_findings()`. Untouched: that path keeps its copy and its ordering.
- DEC-074 -- `suite_ran()` allowlists "ran". Untouched, and still the evidence test on both the worktree run and the base run.
- DEC-065 -- findings travel as a 2-tuple of strings and the marks are `startswith` allowlists. No new finding text and no new mark, so routing is unchanged.
- DEC-029 -- `revalidating` keeps `fail` whatever the findings say. Untouched.

## Plan

1. Run `uv run --group dev pytest -q tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` in the worktree and confirm the assertion at `tests/test_gate.py:372` fails with `AssertionError: ['ENVIRONMENT: suite excluding ...`.
2. In `pipeline/core/gate.py`, delete the line `_copy_tests(wd, base_wt, tests)` from `_base_suite()` -- it sits between the `if base_wt is None:` guard and the `code, out = run_cmd(format_tests_cmd(cfg["test_suite_without_new"], tests), base_wt)` call -- and put in its place the comment `# Base runs its OWN test files here (TICKET-104). Copying the branch's carries a defect the branch introduced in shared test code onto base, the suite comes back red there for a reason base never had, and gate() reports the branch's own bug as an environment problem no plan can fix. The ticket's own nodes are excluded by test_suite_without_new's selector; one naming a node base does not have is a no-op (pytest: --deselect nosuch.py::test_x exits 0). _base_findings() still copies -- DEC-017.`
3. In `pipeline/core/gate.py`, append to `_base_suite()`'s docstring the sentence `The branch's test files are NOT copied onto that checkout: _base_findings() copies them so the ticket's node exists on base at all, and this run must not (TICKET-104).`, and append to `_copy_tests()`'s docstring the sentence `Called by _base_findings() only; _base_suite() must not call it (TICKET-104).`
4. Run `uv run --group dev pytest -q tests/test_gate.py` and confirm it exits 0 -- the baseline in `## Digest` minus its one failure.
5. Add a regression guard to `tests/test_gate.py`, directly below `test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file`, named `test_gate_still_reports_environment_when_base_lacks_the_branchs_test_file`, using only names already imported in that file (DEC-017), with docstring `TICKET-104: the base suite run no longer copies the branch's test files, so a ticket whose test file is new leaves base without it. The TICKET-089 verdict must survive that -- a suite red on both for a reason neither branch introduced is still environment.` and this body, in order: `d = Path(tempfile.mkdtemp())`; `sh = lambda c, cwd=d: subprocess.run(c, shell=True, cwd=cwd, capture_output=True, text=True)`; `sh("git init -qb main && git config user.email t@t && git config user.name t")`; `(d / ".project" / "tickets").mkdir(parents=True)`; write `(d / ".project" / "pipeline.toml")` holding `test_one = "echo test_broken; exit 1"`, `test_suite = "true"`, `test_suite_without_new = "echo 1 failed; exit 1"` and `base = "main"`; write `(d / ".project" / "tickets" / "TICKET-001.md")` holding `FIXTURE`; `sh("git add -A && git commit -qm init")`; `wt = d / ".worktrees" / "TICKET-001"`; `sh(f"git worktree add -q -b ticket/001 {wt} main")`; the branch-only test file `(wt / "test_thing.py").write_text("def test_broken(): assert False")`; `sh("git add -A && git commit -qm branch", cwd=wt)`; `ok, failures = gate(d, "TICKET-001", workdir=wt)`; `assert not ok`; `assert any(f.startswith("ENVIRONMENT: ") for f in failures), failures`; `assert gate_result(ok, failures, "plan-validation") == "environment", failures`; `shutil.rmtree(d, ignore_errors=True)`.
6. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py`, confirm it exits 0, then commit `pipeline/core/gate.py` and `tests/test_gate.py` as `fix(TICKET-104): the base suite run uses base's own test files`.
7. In `CLAUDE.md`, insert a gotcha bullet after the bullet `An exit-0 repro run in the worktree falls through to the base run.` (it ends at line 130), reading: `**The base SUITE run uses base's own test files; only the per-test base run copies the branch's.** _base_findings() copies the ticket's test file onto the base checkout, because the new node does not exist on base at all (DEC-017). _base_suite() must not: a defect the branch introduced in shared code in that same file rides along, base comes back red for a reason its own file never had, and gate() reports the branch's own bug as ENVIRONMENT -- "not this branch's doing" -- escalating and charging nothing (TICKET-104). The ticket's nodes are kept out of the base run by test_suite_without_new's selector instead.`
8. In `README.md`, extend the paragraph that begins at line 505 with `A Tier A failure at ` by adding the sentence `That base run uses base's own test files -- the branch's are not copied onto it -- so a defect the branch introduced in a test file cannot make base look broken.`
9. In `pipeline/templates/skills/pipeline-config/SKILL.md`, extend the bullet near line 54 that begins `test_suite_without_new` is re-run on a checkout of ` by adding the sentence `Base runs its own test files -- the branch's are not copied onto base for that run -- so your selector alone keeps the ticket's nodes out of it, and that selector must be a no-op when it names a test base does not have yet (pytest's `--deselect` is; a runner that errors on an unknown selector must be wrapped, like the selector trap above).`
10. Run `uv run --group dev pytest -q tests` and `./pipeline/hooks/test_dangerous_commands.py`, confirm both exit 0, then commit `CLAUDE.md`, `README.md` and `pipeline/templates/skills/pipeline-config/SKILL.md` as `docs(TICKET-104): the base suite run uses base's own test files`.

## Acceptance criteria

- `tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` passes: `uv run --group dev pytest -q tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` exits 0.
- `tests/test_gate.py::test_gate_still_reports_environment_when_base_lacks_the_branchs_test_file` passes: `uv run --group dev pytest -q tests/test_gate.py::test_gate_still_reports_environment_when_base_lacks_the_branchs_test_file` exits 0.
- `tests/test_gate.py::test_a_suite_red_identically_on_base_does_not_charge_plan_validation_attempts` and
  `tests/test_gate.py::test_a_suite_red_only_in_the_worktree_still_charges_the_plan` both still pass, so the
  TICKET-089 verdict and the `bad-plan` charge are unchanged.
- `uv run --group dev pytest -q tests` exits 0 and prints no `FAILED` line; the baseline recorded in `## Digest` failed on this ticket's repro test and nothing else.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.
- `sed -n '/^def _base_suite/,/^def gate/p' pipeline/core/gate.py | grep -c _copy_tests` prints `0`.
- `grep -c _copy_tests pipeline/core/gate.py` prints a number that is one lower than it is on base `main`, measured with
  `git show main:pipeline/core/gate.py | grep -c _copy_tests`.
- `grep -c "own test files" CLAUDE.md README.md pipeline/templates/skills/pipeline-config/SKILL.md` prints a non-zero count for each of the three files.

## Decisions

**The base SUITE run reads base's own test files; only the per-test base run copies the branch's.** `_base_findings()` copies the ticket's test file onto the base checkout because the new node does not exist on base at all (DEC-017), and that copy stays. `_base_suite()` must not copy. On TICKET-101, at 2026-08-30 10:39:31Z, a second new test in the branch's `tests/test_cli.py` carried a wrong assertion, rode onto base with the file, made base's suite red, and `gate()` reported the branch's own one-line defect as `ENVIRONMENT` -- "not this branch's doing and no plan can fix it" -- escalating to a human and charging no counter. An environment finding is trusted precisely because no plan can fix it. Do not re-add the call.

**The ticket's own tests are kept out of the base suite run by `test_suite_without_new`'s selector alone.** That selector now names nodes base may not have. It must be a no-op there: pytest's `--deselect nosuch.py::test_x` exits 0, verified 2026-08-30. A runner that errors on an unknown selector makes the base run report no test result, `_base_suite()` returns a non-empty `why`, and the verdict falls back to `bad-plan` -- DEC-089's fail-closed arm, not a new failure mode.

**Comparing exit codes was kept; comparing which test NAMES failed was rejected.** The name-set shape would also catch a branch defect that coincides with a genuinely red base, which this fix does not. It needs per-runner output parsing, and the test commands are project configuration (pytest, cargo and jest forms all ship in `pipeline/templates/pipeline.toml`), so no parser here can read them all. The accepted limit: when base is red for a real environment reason AND the branch broke its own test file, the verdict is still `environment`; the operator fixes the environment first, and the re-gate then returns `bad-plan`.

**`_unsafe_rel()` stays in `_base_suite()` although nothing there writes a path any more.** It refuses the same tickets `_base_findings()` refuses, so one gate run never half-consults base. Removing it is a separate change.

## Rollback

Revert the two commits from step 6 and step 10 with `git revert`, or, for the code alone, restore the `_copy_tests(wd, base_wt, tests)` line in `_base_suite()` in `pipeline/core/gate.py`. Reverting brings back the TICKET-101 misverdict: a defect in a shared part of the ticket's test file is reported as `ENVIRONMENT`, escalates to a human and charges no counter. Nothing else depends on the change -- no frontmatter field, no counter and no `transition()` row moves.

## Thread

### 2026-08-30 10:40:24Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-30 · triage · ok

Reproduced. `_copy_tests()` (`pipeline/core/gate.py:304`) copies the entire
test file named by `test_file` onto the base checkout before
`_base_suite()` runs `test_suite_without_new` there. If the branch also
changed shared code in that same file (a fixture, a constant, a helper),
that change rides along onto base and can make the base run fail for a
reason base's own original file never had -- `gate()` then reports it as
`ENVIRONMENT`/pre-existing breakage "not this branch's doing", which is
wrong.

Committed a failing test:
`tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file`
(commit a9e1dd7). It builds a real git project where base's `test_thing.py`
holds `SHARED = "good"` and the branch's copy holds `SHARED = "broken"`
alongside the new failing node; `gate()` reports the base run as RED too,
which the test asserts against.

Verdict `ok`, not `chore`: fixing `_copy_tests`/`_base_suite` needs a design
choice (isolate just the new node vs. some other way to keep the file's
shared code off the base run) that planning should make.

### 2026-08-30 10:43:08Z · triage · session · session=6f871822-2017-4a34-910c-b939689fe48c

`triage` ran as session `6f871822-2017-4a34-910c-b939689fe48c`
- replay: `claude --resume 6f871822-2017-4a34-910c-b939689fe48c`
- log: `.project/logs/TICKET-104-triage-6f871822.log`
- cost: $0.68 of a $3 cap
- tokens: 13,267 out (6,305 thinking) · 58 in · 1,428,109 cache read · 63,910 cache write

### 2026-08-30 10:43:08Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- _copy_tests copies the whole test file onto base, so a branch defect in shared test code makes gate() misreport it as pre-existing/environment breakage.

### 2026-08-30 · planning · ok

Plan written. Chose the ticket's first shape: `_base_suite()`
(`pipeline/core/gate.py:383`) drops its `_copy_tests(wd, base_wt, tests)` call,
so the base suite run reads base's own test files. `_base_findings()` keeps the
copy -- without it the ticket's node does not exist on base at all (DEC-017).

Rejected the second shape (compare which test NAMES failed in the two runs): it
needs per-runner output parsing, and the test commands are project
configuration; `pipeline/templates/pipeline.toml` ships pytest, cargo and jest
forms. Recorded in `## Decisions`, with the limit it leaves.

Checked the one thing the shape depends on: the exclusion selector now names
nodes base may not have. `pytest -q --deselect nosuch.py::test_x` in a one-test
throwaway project exits 0 and prints `1 passed`. A runner that errors instead
falls back to `bad-plan` through DEC-089's fail-closed arm.

Baseline measured in this worktree: `uv run --group dev pytest -q tests` prints
`1 failed, 482 passed in 41.11s`; the failure is this ticket's repro test.

Out of scope, noted rather than fixed: `suite_ran()` is not applied to
`test_suite` at `verifying` (`pipeline/daemon/supervisor.py`), which DEC-074
already records as a separate ticket's work.

No questions for the human: the ticket named both candidate shapes and the
choice is settled by what the code can read.

### 2026-08-30 10:51:49Z · planning · session · session=987dfaff-5cb2-4ba3-ae0d-1d9fb565865b

`planning` ran as session `987dfaff-5cb2-4ba3-ae0d-1d9fb565865b`
- replay: `claude --resume 987dfaff-5cb2-4ba3-ae0d-1d9fb565865b`
- log: `.project/logs/TICKET-104-planning-987dfaff.log`
- cost: $3.08 of a $10 cap
- tokens: 36,274 out (17,637 thinking) · 68 in · 2,255,574 cache read · 104,005 cache write

### 2026-08-30 10:51:49Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: `_base_suite()` stops copying the branch's test files onto base, so the base suite run judges base's own files; `_base_findings()` keeps its copy (DEC-017)

### 2026-08-30 11:05:02Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` fails as required
```
wt} main")
        # the branch's own defect: it broke SHARED, unrelated to the new test
        (wt / "test_thing.py").write_text('SHARED = "broken"\n')
        sh("git add -A && git commit -qm branch", cwd=wt)
        ok, failures = gate(d, "TICKET-001", workdir=wt)
        assert not ok
>       assert not any("is RED on base" in f for f in failures), failures
E       AssertionError: ['ENVIRONMENT: suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, and it is RED on base `ma...al output, already quoted in the `## Thread` entry `2026-08-30 11:04:24Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file.<locals>.<genexpr> at 0x7fef09d15f20>)

tests/test_gate.py:372: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` fails on base `main` too -- the bug is not already fixed upstream
```
`## Thread` entry `2026-08-30 11:04:25Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file.<locals>.<genexpr> at 0x7fbffd7e8e10>)

tests/test_gate.py:372: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.36s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-mnaiasdf/base
      Built pipeline @ file:///tmp/pipeline-base-mnaiasdf/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```

### 2026-08-30 · plan-validation · ok

Validated. All eight items pass.
long: eight scored items, one anchor discrepancy, one unverified probe.

1. Root cause: `_base_suite()` runs base's suite on a checkout carrying the
   branch's whole test FILES, so a defect the branch introduced in one counts
   as base's own failure. Deleting the copy fixes that, not the symptom.
2. Decisions: I read DEC-017 and DEC-089. DEC-017's copy clause is written
   about the reproduction run, which keeps its copy (`gate.py:344`). DEC-089
   nowhere requires the copy. The plan complies with both.
3. Scope: 10 steps, each traceable to a criterion. Step 3's docstrings sit
   inside the function step 2 changes.
4. Criteria falsifiable: `_copy_tests` matches 3 lines in `gate.py` today
   (304, 344, 402) and 2 after; neither sentence the plan adds contains that
   name, so the count moves only if the call goes.
5. No research left: every step names a file and a function I confirmed.
6. Riskiest step: step 2. Fallback stated -- a runner that errors on an
   unknown selector reports no test result, `_base_suite()` returns a
   non-empty `why`, and the verdict falls back to `bad-plan` (DEC-089).
7. Regression surface: `_base_suite()`'s one caller. Outside the two
   TICKET-089 tests, every `test_suite_without_new` in `tests/` is `true`,
   `exit 1`, `! test -f broken` or runs without a worktree, so none depends
   on the copy.
8. Blast radius: `bugfix`, one deleted line, one test, three doc sentences.

Not a finding, fix while implementing: step 7 names the CLAUDE.md bullet
`An exit-0 repro run in the worktree falls through to the base run.` and
gives line 130. That bullet ends at line 128; line 130 ends the next bullet.
Follow the bullet text.

Unverified: `pytest -q --deselect nosuch.py::test_x` exits 0. Building a
throwaway project writes files, which the read-only guard blocks. I would
have run the plan's own check.

### 2026-08-30 11:08:52Z · plan-validation · session · session=e405e402-9d65-4933-994d-7d4241cb9c38

`plan-validation` ran as session `e405e402-9d65-4933-994d-7d4241cb9c38`
- replay: `claude --resume e405e402-9d65-4933-994d-7d4241cb9c38`
- log: `.project/logs/TICKET-104-plan-validation-e405e402.log`
- cost: $1.57 of a $3 cap
- tokens: 16,640 out (10,833 thinking) · 40 in · 1,005,935 cache read · 65,264 cache write

### 2026-08-30 11:08:52Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan validated: all 8 items pass; the root cause is _base_suite() running base's suite on a checkout carrying the branch's whole test files, and deleting that one copy fixes it

### 2026-08-30 11:19:44Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified the load-bearing assumption empirically rather than trusting the plan: pytest -q --deselect nosuch.py::test_x exits 0 and runs the rest, so excluding a node base does not have is a no-op and dropping the copy leaves the base suite run correct. It takes the smaller of the two shapes the ticket offered -- delete _copy_tests from _base_suite, keep it in _base_findings -- and documents the asymmetry in both docstrings so it cannot be tidied back. Step 5 is what keeps the fix honest: a regression test that the TICKET-089 case, a suite red on both for a reason neither branch introduced, still returns environment after the copy is gone. Step 9 documents the caveat for a runner that errors on an unknown selector rather than ignoring it. Nothing fenced.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified the load-bearing assumption empirically rather than trusting the plan: pytest -q --deselect nosuch.py::test_x exits 0 and runs the rest, so excluding a node base does not have is a no-op and dropping the copy leaves the base suite run correct. It takes the smaller of the two shapes the ticket offered -- delete _copy_tests from _base_suite, keep it in _base_findings -- and documents the asymmetry in both docstrings so it cannot be tidied back. Step 5 is what keeps the fix honest: a regression test that the TICKET-089 case, a suite red on both for a reason neither branch introduced, still returns environment after the copy is gone. Step 9 documents the caveat for a runner that errors on an unknown selector rather than ignoring it. Nothing fenced.**

### 2026-08-30 11:24:54Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` fails as required
```
wt} main")
        # the branch's own defect: it broke SHARED, unrelated to the new test
        (wt / "test_thing.py").write_text('SHARED = "broken"\n')
        sh("git add -A && git commit -qm branch", cwd=wt)
        ok, failures = gate(d, "TICKET-001", workdir=wt)
        assert not ok
>       assert not any("is RED on base" in f for f in failures), failures
E       AssertionError: ['ENVIRONMENT: suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, and it is RED on base `ma...al output, already quoted in the `## Thread` entry `2026-08-30 11:24:15Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file.<locals>.<genexpr> at 0x7f1013e86190>)

tests/test_gate.py:451: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================

```
- ok: `tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` fails on base `main` too -- the bug is not already fixed upstream
```
`## Thread` entry `2026-08-30 11:24:16Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file.<locals>.<genexpr> at 0x7f58b15141e0>)

tests/test_gate.py:451: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.38s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-fkgzgl3z/base
      Built pipeline @ file:///tmp/pipeline-base-fkgzgl3z/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 19ms

```

### 2026-08-30 11:24:55Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

### 2026-08-30 · implementing · todo

Todo list, one entry per plan step:

1. [x] confirm repro test fails as described
2. [x] delete `_copy_tests` call from `_base_suite()`, add comment
3. [x] append docstring sentences to `_base_suite()` and `_copy_tests()`
4. [x] confirm `tests/test_gate.py` exits 0
5. [x] add regression guard test
6. [x] confirm `tests/test_gate.py tests/test_dispatch.py` exit 0, commit code
7. [x] CLAUDE.md gotcha bullet
8. [x] README.md sentence
9. [x] SKILL.md sentence
10. [x] confirm full suite + guard script exit 0, commit docs

### 2026-08-30 · implementing · ok

Implemented as planned, no deviation.

1. Deleted `_copy_tests(wd, base_wt, tests)` from `_base_suite()` in
   `pipeline/core/gate.py` (`gate.py:402` now removed); replaced with the
   comment the plan gave, and both docstring sentences.
2. Added `test_gate_still_reports_environment_when_base_lacks_the_branchs_test_file`
   below the existing repro test in `tests/test_gate.py`. TDD check: it
   passes both with and without the fix, since it protects the
   TICKET-089 case, which the fix does not touch -- verified by
   temporarily reverting `gate.py` via a tagged git stash and re-running.
3. `tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file`
   fails without the fix (`assert not True` on `is RED on base`), passes
   with it.
4. `uv run --group dev pytest -q tests`: `501 passed`, no `FAILED` line.
   `./pipeline/hooks/test_dangerous_commands.py` exits 0.
5. Committed as `fix(TICKET-104): the base suite run uses base's own test
   files` (`pipeline/core/gate.py`, `tests/test_gate.py`), then
   `docs(TICKET-104): the base suite run uses base's own test files`
   (`CLAUDE.md`, `README.md`, `SKILL.md`).
6. Acceptance-criteria sweep found the SKILL.md sentence's markdown line
   wrap split `own test files` across two lines, so
   `grep -c "own test files"` reported 0 for that file. Fixed the wrap in
   a follow-up commit `docs(TICKET-104): fix line-wrap so 'own test
   files' matches the acceptance grep`; not a plan deviation, a
   formatting bug in my own step-9 edit.

All eight acceptance criteria verified passing after the fix-up.

re-gated after rebasing onto base: passed

### 2026-08-30 11:30:29Z · implementing · session · session=68803e66-f66d-40c7-8d5e-dc2f2bd36489

`implementing` ran as session `68803e66-f66d-40c7-8d5e-dc2f2bd36489`
- replay: `claude --resume 68803e66-f66d-40c7-8d5e-dc2f2bd36489`
- log: `.project/logs/TICKET-104-implementing-68803e66.log`
- cost: $1.21 of a $8 cap
- tokens: 16,772 out (1,526 thinking) · 118 in · 3,769,760 cache read · 70,689 cache write

### 2026-08-30 11:30:29Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ deleted _copy_tests call from _base_suite(); both repro and regression-guard tests pass; full suite 501 passed, guard 0

### 2026-08-30 · review · ok

Reviewed `b5c9d73`..`8f2b18f`, the whole branch: first review pass, no
earlier review entry to check against. No blocking findings. The delta
matches `## Plan` step for step; the step-9 SKILL.md wording was re-wrapped
to keep `own test files` on one line, which the thread already records.

I re-ran every acceptance-criteria check myself:
`uv run --group dev pytest -q tests` prints `501 passed in 35.25s`;
`tests/test_gate.py` prints `80 passed`; the four named tests print
`4 passed`; `./pipeline/hooks/test_dangerous_commands.py` prints
`guard: all passed`; `grep -c _copy_tests pipeline/core/gate.py` prints `2`
against `3` on `main`; the `_base_suite` slice prints `0`;
`grep -c "own test files"` prints `1` for each of the three doc files.

Findings:

1. minor -- `tests/test_gate.py:416`
   (`test_a_numbered_acceptance_criterion_naming_no_test_is_caught`) lost its
   `shutil.rmtree(d)` when `b5c9d73` inserted the repro test above that line.
   The line now cleans up the repro test's own `d` instead. One temp dir
   leaks per run. Not blocking: no assertion changes.

Two candidate findings I dropped:

- "`_base_findings()`'s copy leaks into the base suite run." Refuted:
  `base_checkout()` (`pipeline/core/worktree.py:110`) mkdtemps a fresh
  worktree per call and removes it in `finally`.
- "The regression guard is vacuous -- it passes without the fix." Refuted:
  it asserts `gate_result(...) == "environment"` on a base checkout that
  lacks the branch's test file, a state only this fix produces, and it fails
  if `_base_suite()` is later made to fail closed there.

long: the acceptance list has eight items and each one needs its own quoted
result.

### 2026-08-30 11:34:38Z · review · session · session=3008f32b-f4b9-4ae3-94c8-194178cc36ae

`review` ran as session `3008f32b-f4b9-4ae3-94c8-194178cc36ae`
- replay: `claude --resume 3008f32b-f4b9-4ae3-94c8-194178cc36ae`
- log: `.project/logs/TICKET-104-review-3008f32b.log`
- cost: $1.63 of a $5 cap
- tokens: 15,343 out (7,743 thinking) · 46 in · 1,184,321 cache read · 64,882 cache write

### 2026-08-30 11:34:38Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed the 4-commit delta: the fix matches the plan, all 8 acceptance criteria pass, 501 passed; one non-blocking nit

### 2026-08-30 11:35:16Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-30 11:35:17Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/104


Current branch ticket/104 is up to date.
Already up to date.
Updating 7e9601a..8f2b18f
Fast-forward
 CLAUDE.md                                          |  9 ++++
 README.md                                          |  4 +-
 pipeline/core/gate.py                              | 16 ++++--
 pipeline/templates/skills/pipeline-config/SKILL.md |  7 ++-
 tests/test_gate.py                                 | 59 ++++++++++++++++++++++
 5 files changed, 90 insertions(+), 5 deletions(-)

```

### 2026-08-30 11:35:17Z · merging · decision

decision recorded as `DEC-104`
