---
id: TICKET-146
stage: done
class: bugfix
branch: ticket/146
test_file:
- tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage
- tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure
deletes: []
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/gate.py
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
  id: d919bdbb-9b7d-4710-996f-e594a8980c61
  replay: claude --resume d919bdbb-9b7d-4710-996f-e594a8980c61
  log: .project/logs/TICKET-146-review-d919bdbb.log
  cost_usd: 0.5871618
approved_by: chezzijr
approved_at: '2026-10-01T12:26:06.096940+00:00'
---

## Summary

The Tier A gate blames the plan for failures the plan did not cause

Expected change files: `pipeline/core/gate.py` and `tests/test_gate.py`.

Two findings in `gate()` are classified `bad-plan` and charge `plan_validation_attempts` although no re-plan can fix them. They share one file and one cause -- the gate misreads a failure that is not the plan's -- so they are filed together. Each needs its own failing test.

**1. A test added on the branch but absent from `test_file` reads as pre-existing breakage**

`gate()` excludes only the ticket's declared tests (plus quarantine) from the suite run -- `pipeline/core/gate.py:929`, on main at 7e7545a:

    suite_tests = list(dict.fromkeys([*tests, *quarantine]))
    ...
    suite_cmd = format_tests_cmd(cfg["test_suite_without_new"], suite_tests)

When triage commits more than one red test (seen 5 times on a Rust project: triage committed a grid of red tests and listed one in `test_file`), the other red tests stay in the suite run. The worktree suite goes red; `_base_suite()` runs base's own files (TICKET-104), where those tests do not exist, so base is green and the gate appends:

    suite excluding `<test_file>` is RED -- pre-existing breakage, fix that first

That finding is wrong on both counts: the breakage is the branch's own, not pre-existing, and it is not structural, so `gate_result()` returns `bad-plan` and charges `plan_validation_attempts`. A re-plan cannot fix it, because the red tests are triage's commit.

Expected: a test that the branch added (not present on base) and that fails in the worktree is never reported as pre-existing breakage. Either it is excluded from the suite run like the ticket's own tests, or the gate names it as "added on this branch but not listed in `test_file`" -- a finding that does not read as a bad plan. A test should show the current gate output containing `pre-existing breakage` for a branch that adds two failing tests and declares one.

**2. `test_one` exiting 127 (command not found) reads as an errored test**

`pipeline/core/gate.py:812`, on main at 7e7545a:

    elif node not in out:
        findings.append(
            f"`{test}` exited non-zero but its name never appears in the "
            f"output -- it errored rather than failed\n```\n{out[-1200:]}\n```")

A shell exit of 127 (or 126) means the test runner itself never started -- e.g. `sh: npm: command not found` in a JS worktree with no `node_modules`. The gate files it under the same generic "errored rather than failed" finding as an import error. That finding matches none of the `ENVIRONMENT_MARKS` / `STRUCTURAL_MARKS` prefixes, so `gate_result()` classifies it `bad-plan` and charges `plan_validation_attempts`. Seen on the first JavaScript project: every worktree and the base checkout exited 127, and planning was re-run against a plan that was never the problem.

`register` already knows these codes: `SHELL_CANNOT_RUN = {126: ..., 127: "the shell could not find it"}` in `pipeline/core/config.py:374`.

Expected: when `test_one` exits 126 or 127, the finding carries `ENVIRONMENT_MARK`, says the command could not run (and points at `worktree_setup` as the usual cause), and the ticket escalates without charging `plan_validation_attempts`. A test with `test_one = "no-such-runner {test}"` should currently get verdict `bad-plan`; after the fix, `environment`.


## Reproduction

Tests (both fail before the fix, committed on `ticket/146`):
1. `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` -- the gate returns "suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first".
2. `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure` -- `assert 'bad-plan' == 'environment'`.

Command: `uv run --group dev pytest -q tests/test_gate.py -k "added_on_the_branch or cannot_start"`

expect: AssertionError

## Digest

- Files touched: `pipeline/core/gate.py` (both fixes), `tests/test_gate.py` (two new tests beside triage's two), `CLAUDE.md` and `README.md` (the `invalid-test` verdict now also covers `UNLISTED-TEST: `).
- Entry point: `gate()` in `pipeline/core/gate.py`. Finding 2 lives in its per-test loop (`for test in runnable:`, the `elif node not in out:` arm, ~line 812). Finding 1 lives in the suite block, the `elif not why:` arm after `_base_suite()` (~line 959).
- Verdict routing: `gate_result()` in `pipeline/daemon/supervisor.py:1090` checks `environment_only()`, `missing_test_file()`, `load_flaky()`, `invalid_test()`, then `structural_only()`. All are `startswith` allowlists over gate.py constants. `invalid_test()` reads `INVALID_TEST_MARKS` (gate.py ~line 338), so adding a mark to that tuple routes a finding to the existing `("plan-validation", "invalid-test") -> escalated` row with no counter. No change to `pipeline/core/machine.py` or `supervisor.py` is needed.
- Reused helpers: `SHELL_CANNOT_RUN` (`pipeline/core/config.py:374`, `{126: ..., 127: ...}`), `base_checkout()` / `base_ref()` / `run_cmd()` (`pipeline/core/worktree.py`), `_copy_tests()`, `_confirmed_suite()`, `suite_ran()`, `_unsafe_rel()` (all gate.py).
- Finding 1 design: "added on the branch" means a file present at `HEAD` and absent from base's tree (`git diff --diff-filter=A <base> HEAD`), outside `.project/`, not a declared `test_file` path, and sharing a file suffix with a declared `test_file` path. Proof: copy only those files onto a base checkout and rerun `test_suite_without_new`. Red there means the added files carry the red test. Copying an ADDED file overwrites nothing base has, so DEC-104's hazard does not apply.
- Known limit: a red test added inside a file that base already has (a modified file, e.g. a Rust `#[test]` grid in a listed file) is not detected. That keeps today's `bad-plan` finding. DEC-104 rejected per-runner failing-name parsing, which is the only way to see it.
- Gotcha: `tests/test_gate.py` is copied onto a base checkout and imported there (DEC-017, DEC-018). New tests must not import any name this branch adds (`UNLISTED_TEST_MARK`); assert on the literal `"UNLISTED-TEST: "` string.
- Gotcha: `test_a_suite_red_only_in_the_worktree_still_charges_the_plan` (branch adds suffix-less `broken`) and `test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` (branch MODIFIES `test_thing.py`) must keep `bad-plan`. The suffix filter and `--diff-filter=A` are what keep them there.
- Gotcha: finding 1's new text must not contain `pre-existing breakage`; triage's repro test greps for that substring.
- Baseline measured 2026-10-01 on `ticket/146` (cbc6f00): `tests/test_gate.py` 2 failed, 106 passed (the two failures are triage's repro tests); `tests/test_dispatch.py tests/test_machine.py` 167 passed.

## Decisions checked

- DEC-089: unproven "not the plan's fault" must fail closed to `bad-plan`. Complied: the unlisted-test finding fires only after the base rerun with the added files is RED and `suite_ran()`; every other outcome keeps today's finding. DEC-089 also keeps the phrase `RED -- pre-existing breakage` in the environment finding; untouched.
- DEC-104: `_base_suite()` must not copy the branch's test files. Complied: `_base_suite()` is unchanged. The new `_added_red_on_base()` copies only files absent from base, so it cannot carry a branch edit of a base file onto base.
- DEC-074: the gate allowlists "ran" for the suite; `register` allowlists "cannot run". Complied: `suite_ran()` is unchanged. `SHELL_CANNOT_RUN` is used only for `test_one` in the worktree, where it reroutes an existing failure finding and never turns a failure into a pass.
- DEC-118: `INVALID-TEST: ` leads its finding; `invalid_test()` asks `any`; `revalidating` keeps `fail`. Complied: `UNLISTED-TEST: ` joins `INVALID_TEST_MARKS` with the same `any` semantics and the same `plan-validation`-only scope.
- DEC-137: one `ENVIRONMENT: ` finding overrides every other class at `plan-validation`. Complied: the exit-126/127 finding carries `ENVIRONMENT_MARK`.
- DEC-017, DEC-018: `tests/test_gate.py` is imported on a base checkout. Complied: new tests import no branch-only name.
- Grep terms used in `.project/decisions/`: `pre-existing`, `_base_suite`, `127`, `test_suite_without_new`, `ENVIRONMENT_MARK`, `environment_only`, `invalid-test`, `INVALID_TEST`, `SHELL_CANNOT_RUN`, `worktree_setup`.

## Plan

1. Exit 126/127 from `test_one` becomes an environment finding in `pipeline/core/gate.py`; triage's red test is `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure`.
    - Write the failing test first: add `test_a_test_runner_that_cannot_start_names_the_cause` to the end of `tests/test_gate.py`. Body: `d = project()`; write `.project/pipeline.toml` with `test_one = "no-such-runner {test}"`, `test_suite = "true"`, `test_suite_without_new = "true"`; `ok, failures = gate(d, "TICKET-001")`; `env = [f for f in failures if f.startswith("ENVIRONMENT: ")]`; assert `len(env) == 1`, `"exited 127" in env[0]`, `"worktree_setup" in env[0]`, and `not any("errored rather than failed" in f for f in failures)`; `shutil.rmtree(d)`.
    - Run `uv run --group dev pytest -q tests/test_gate.py -k cannot_start`. Expect 2 failed.
    - In `pipeline/core/gate.py`, add `SHELL_CANNOT_RUN` to the `from pipeline.core.config import (...)` list.
    - In `gate()`'s loop `for test in runnable:`, insert this arm between `if code == 0: passing.append((test, out))` and `elif node not in out:`:
      `elif code in SHELL_CANNOT_RUN and node not in out:` followed by `findings.append(f"{ENVIRONMENT_MARK}`{test}`: `test_one` could not start -- the shell exited {code}, {SHELL_CANNOT_RUN[code]}, so no test ran and no plan can fix it. The usual cause is a runner that `worktree_setup` did not install (e.g. `node_modules`); fix `test_one` or `worktree_setup` in `.project/pipeline.toml`, then `pipeline resume {tid}`\n```\n{out[-1200:]}\n```")`.
      Add a two-line comment above it: the shell's own 126/127 means the runner never started (`SHELL_CANNOT_RUN`, the codes `register` already knows), and the mark must lead because the classifiers are `startswith` (DEC-065, DEC-089).
    - Run `uv run --group dev pytest -q tests/test_gate.py -k "cannot_start or errors_instead_of_failing"`. Expect 3 passed. Commit `fix(TICKET-146): report a test_one the shell cannot start as an environment failure`.
2. A red test file added on the branch but not listed in `test_file` gets its own `UNLISTED-TEST: ` finding in `pipeline/core/gate.py`; triage's red test is `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage`.
    - Write two tests first, at the end of `tests/test_gate.py`, each building the same git fixture as triage's `test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` (a `git init -qb main` project, `FIXTURE` ticket committed on main, worktree `ticket/001` at `.worktrees/TICKET-001`, `base = "main"`, `test_one = "echo test_broken; exit 1"`, `test_suite = "true"`). Copy the fixture code into each test body; do not import a helper this branch adds.
    - `test_a_red_test_added_on_the_branch_escalates_without_charging_the_plan`: `test_suite_without_new = "echo 1 failed; ! test -f test_extra.py"`; the branch commits `test_thing.py` and `test_extra.py`. Assert `not ok`; `hits = [f for f in failures if f.startswith("UNLISTED-TEST: ")]`; `len(hits) == 1` and "`test_extra.py`" in `hits[0]`; `res = gate_result(ok, failures, "plan-validation")`; `res == "invalid-test"`; `_, counters = transition("plan-validation", res, {})`; `counters.get("plan_validation_attempts", 0) == 0`; `gate_result(ok, failures, "revalidating") == "fail"`.
    - `test_an_added_file_that_leaves_base_green_keeps_the_pre_existing_finding`: `test_suite_without_new = "echo 1 failed; ! test -f broken"`; the branch commits `test_thing.py`, `test_extra.py` and an empty `broken`. Assert `not ok`, `not any(f.startswith("UNLISTED-TEST: ") for f in failures)`, `any("RED -- pre-existing breakage" in f for f in failures)`, and `gate_result(ok, failures, "plan-validation") == "bad-plan"`.
    - Run `uv run --group dev pytest -q tests/test_gate.py -k "added_on_the_branch or leaves_base_green"`. Expect 2 failed (triage's repro and the escalation test), 1 passed.
    - In `pipeline/core/gate.py`, replace `INVALID_TEST_MARKS = (INVALID_TEST_MARK,)` with `UNLISTED_TEST_MARK = "UNLISTED-TEST: "` then `INVALID_TEST_MARKS = (INVALID_TEST_MARK, UNLISTED_TEST_MARK)`, with a comment: a red test the branch ADDED in a file `test_file` does not list belongs to `triage` like an unreachable assertion does (`CLAIMS`), so it routes to the same no-charge `invalid-test` verdict (TICKET-146).
    - In `pipeline/core/gate.py`, add `_branch_added(wd: Path, cfg: dict, tests: list[str]) -> list[str]` after `_copy_tests()`. It runs `run_cmd(f"git -c core.quotePath=false diff --name-only --no-renames --diff-filter=A {shlex.quote(base_ref(cfg))} HEAD", wd)`, returns `[]` on a non-zero exit, and otherwise returns each output line `p` where `p` is non-empty, `not p.startswith(".project/")`, `p` is not in `declared = {x.split("::")[0] for x in tests}`, `Path(p).suffix` is in `{Path(x).suffix for x in declared} - {""}`, and `(wd / p).is_file()`. The `is_file()` guard drops a line `bounded_output()` truncated. Docstring: files absent from base that look like the ticket's own tests; empty when git cannot answer, so the caller keeps DEC-089's fail-closed finding.
    - In `pipeline/core/gate.py`, add `_added_red_on_base(project: Path, cfg: dict, wd: Path, suite_tests: list[str], added: list[str]) -> str | None` after `_base_suite()`. Body: `with base_checkout(project, cfg) as (base_wt, _):` return `None` if `base_wt is None`; else `_copy_tests(wd, base_wt, added)` and `code, out = _confirmed_suite(format_tests_cmd(cfg["test_suite_without_new"], suite_tests), base_wt)`. After the `with`, return `out if code != 0 and suite_ran(code, out) else None`. Docstring: the added files are absent from base, so the copy overwrites nothing base has, unlike the copy DEC-104 forbids in `_base_suite()`.
    - In `pipeline/core/gate.py`, change `_copy_tests()`'s docstring line to `Called by _base_findings() and _added_red_on_base(); _base_suite() must not call it (TICKET-104).`
    - In `gate()`'s `elif not why:` arm, compute `added = _branch_added(wd, cfg, tests)` and `added_out = (_added_red_on_base(project, cfg, wd, suite_tests, added) if added and not _unsafe_rel(added) else None)`. When `added_out is not None`, append `f"{UNLISTED_TEST_MARK}suite excluding {names} is RED in the ticket's worktree and green on base `{base_ref(cfg)}`, and base turns RED once this branch's added file(s) {listed} are copied onto it -- the branch added a failing test that `test_file` does not list. Only `triage` may write `test_file` (`CLAIMS`), so no re-plan can repair it: list the test in `test_file` or remove it, then `pipeline resume {tid} --stage triage`"` plus the two fences ```` ```on base with the added files ```` (`added_out[-1200:]`) and ```` ```in the ticket's worktree ```` (`out[-1200:]`), where `listed = " ".join(f"`{x}`" for x in added)`. Otherwise append today's `suite excluding {names} is RED -- pre-existing breakage, fix that first` finding unchanged.
    - Run `uv run --group dev pytest -q tests/test_gate.py`. Expect 0 failed. Commit `fix(TICKET-146): name a red test the branch added but test_file does not list`.
3. Document the widened `invalid-test` verdict and the exit-127 environment finding in `CLAUDE.md` and `README.md`.
    - In `CLAUDE.md`, in the `gate_result()` bullet, change `` `invalid-test` (the selected test hides statically unreachable statements) `` to `` `invalid-test` (the selected test hides statically unreachable statements, or a test file the branch added but `test_file` does not list turns the suite red -- `UNLISTED-TEST: `) `` and change `` `environment` (the suite is red on base too) `` to `` `environment` (the suite is red on base too, or the shell exits 126/127 running `test_one`) ``.
    - In `README.md`, after the paragraph that opens `A Tier A failure at `plan-validation` whose findings include an` and names `INVALID-TEST: `, add one paragraph: an `UNLISTED-TEST: ` finding takes the same `invalid-test` route; the gate raises it only when the suite is red in the worktree, green on base, and red again on base once the files the branch added (same suffix as a `test_file` path, outside `.project/`) are copied onto it. In the `ENVIRONMENT: ` paragraph after it, add one sentence: `test_one` exiting 126 or 127 with no test name in its output is an `ENVIRONMENT: ` finding, usually a runner `worktree_setup` did not install.
    - Run `uv run --group dev pytest -q tests/test_stages.py`. Expect 0 failed. Commit `docs(TICKET-146): document the unlisted-test and cannot-start gate findings`.

## Acceptance criteria

- `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` passes.
- `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure` passes.
- `tests/test_gate.py::test_a_test_runner_that_cannot_start_names_the_cause` passes.
- `tests/test_gate.py::test_a_red_test_added_on_the_branch_escalates_without_charging_the_plan` passes.
- `tests/test_gate.py::test_an_added_file_that_leaves_base_green_keeps_the_pre_existing_finding` passes.
- `tests/test_gate.py::test_a_suite_red_only_in_the_worktree_still_charges_the_plan` passes unchanged.
- `tests/test_gate.py::test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` passes unchanged.
- `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py tests/test_machine.py tests/test_stages.py` exits 0. Measured baseline: test_gate 2 failed 106 passed; test_dispatch plus test_machine 167 passed.
- `git diff --name-only main...HEAD -- pipeline/core/machine.py pipeline/daemon/supervisor.py` prints nothing.

## Decisions

- **A red test the branch ADDED in a file `test_file` does not list routes to `invalid-test`, not to a new verdict.** The finding opens `UNLISTED-TEST: ` and joins `INVALID_TEST_MARKS`, so `gate_result()` and `transition()` needed no new row. Both verdicts mean the same thing: `triage`'s committed tests are wrong and only `triage` owns `test_file`. A future split into its own verdict needs a `transition()` row (FENCED).
- **"Added on the branch" is proven, not inferred.** The gate copies only files absent from base's tree onto a base checkout and reruns `test_suite_without_new`. Only a RED, `suite_ran()` result there raises the finding; every other outcome keeps the old `bad-plan` finding (DEC-089 fails closed). Copying an added file overwrites nothing base has, which is why this does not reopen DEC-104.
- **The candidate set is files absent from base, sharing a suffix with a declared `test_file` path.** The suffix filter keeps a branch-added non-test file (TICKET-089's `broken`) on `bad-plan`. A red test added inside a file base already has is not detected; DEC-104 rejected the per-runner name parsing that would find it.
- **`test_one` exiting 126/127 with no node name in its output is `ENVIRONMENT: `.** The shell's own codes mean the runner never started. No base proof is required: no plan changes `test_one` or the installed tools. A runner that prints the node name keeps today's verdicts.

## Rollback

Revert the step commits with `git revert` and rerun `uv run --group dev pytest -q tests/test_gate.py`. Step 1 and step 2 are independent; either reverts alone.
Riskiest step: step 2, the candidate filter plus the extra base checkout. Its check is `uv run --group dev pytest -q tests/test_gate.py`. If `test_a_suite_red_only_in_the_worktree_still_charges_the_plan` or `test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file` goes red, the filter is too wide. Fallback: do not edit those tests. Revert step 2's code, keep step 1, and return `blocked` with the failing output quoted in `## Thread`.

## Thread

### 2026-10-01 12:07:29Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-10-01 12:15:00Z · triage · note

Both findings reproduce on main at 7e7545a. Two tests added, both red, committed on `ticket/146`. Result is `ok`, not `chore`: finding 1 has a design choice (exclude added tests from the suite run, or name them). Fix touches `pipeline/core/gate.py` and `tests/test_gate.py`. The `expect:` line is `AssertionError` because the two tests share no longer text.

### 2026-10-01 12:08:41Z · triage · session · session=154b45e0-85a8-4d7c-8e7f-4c65842893bf

`triage` ran as session `154b45e0-85a8-4d7c-8e7f-4c65842893bf`
- replay: `claude --resume 154b45e0-85a8-4d7c-8e7f-4c65842893bf`
- log: `.project/logs/TICKET-146-triage-154b45e0.log`
- cost: $0.31 of a $3 cap
- tokens: 5,597 out (347 thinking) · 24 in · 440,559 cache read · 41,191 cache write

### 2026-10-01 12:08:41Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ two red tests reproduce both gate misclassifications

### 2026-10-01 12:15:57Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` fails as required
```
  (wt / "test_thing.py").write_text("def test_broken(): assert False")
        (wt / "test_extra.py").write_text("def test_extra(): assert False")
        sh("git add -A && git commit -qm branch", cwd=wt)
        ok, failures = gate(d, "TICKET-001", workdir=wt)
        assert not ok
>       assert not any("pre-existing breakage" in f for f in failures), failures
E       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, already quoted in the `## Thread` entry `2026-10-01 12:14:36Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage.<locals>.<genexpr> at 0x7f4b4e587ed0>)

tests/test_gate.py:1792: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================

```
- ok: `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure` fails as required
```
CKET-146: exit 127 means the runner never started, not that the
        test errored; no re-plan fixes it."""
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "no-such-runner {test}"\n'
            'test_suite = "true"\ntest_suite_without_new = "true"\n')
        ok, failures = gate(d, "TICKET-001")
        assert not ok
>       assert gate_result(ok, failures, "plan-validation") == "environment", failures
E       AssertionError: ['`test_thing.py::test_broken` exited non-zero but its name never appears in the output -- it errored rather than fail...al output, already quoted in the `## Thread` entry `2026-10-01 12:14:36Z · plan-validation · gate · verdict=FAIL` --*']
E       assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_gate.py:1805: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` fails on base `main` too -- the bug is not already fixed upstream
```
hread` entry `2026-10-01 12:14:38Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage.<locals>.<genexpr> at 0x7fceb29f3ac0>)

tests/test_gate.py:1792: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.46s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-szna8bka/base
      Built pipeline @ file:///tmp/pipeline-base-szna8bka/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 77ms

```
- ok: `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure` fails on base `main` too -- the bug is not already fixed upstream
```
CKET-146: exit 127 means the runner never started, not that the
        test errored; no re-plan fixes it."""
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "no-such-runner {test}"\n'
            'test_suite = "true"\ntest_suite_without_new = "true"\n')
        ok, failures = gate(d, "TICKET-001")
        assert not ok
>       assert gate_result(ok, failures, "plan-validation") == "environment", failures
E       AssertionError: ['`test_thing.py::test_broken` exited non-zero but its name never appears in the output -- it errored rather than fail...al output, already quoted in the `## Thread` entry `2026-10-01 12:14:38Z · plan-validation · gate · verdict=FAIL` --*']
E       assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_gate.py:1805: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- `files_declared` is empty
- plan step names no declared file: '1. Exit 126/127 from `test_one` becomes an environment finding in `pipeline/core/gate.py`; triage\'s red test is `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure`. - Write the failing test first: add `test_a_test_runner_that_cannot_start_names_the_cause` to the end of `tests/test_gate.py`. Body: `d = project()`; write `.project/pipeline.toml` with `test_one = "no-such-runner {test}"`, `test_suite = "true"`, `test_suite_without_new = "true"`; `ok, failures = gate(d, "TICKET-001")`; `env = [f for f in failures if f.startswith("ENVIRONMENT: ")]`; assert `len(env) == 1`, `"exited 127" in env[0]`, `"worktree_setup" in env[0]`, and `not any("errored rather than failed" in f for f in failures)`; `shutil.rmtree(d)`. - Run `uv run --group dev pytest -q tests/test_gate.py -k cannot_start`. Expect 2 failed. - In `pipeline/core/gate.py`, add `SHELL_CANNOT_RUN` to the `from pipeline.core.config import (...)` list. - In `gate()`\'s loop `for test in runnable:`, insert this arm between `if code == 0: passing.append((test, out))` and `elif node not in out:`: `elif code in SHELL_CANNOT_RUN and node not in out:` followed by `findings.append(f"{ENVIRONMENT_MARK}`{test}`: `test_one` could not start -- the shell exited {code}, {SHELL_CANNOT_RUN[code]}, so no test ran and no plan can fix it. The usual cause is a runner that `worktree_setup` did not install (e.g. `node_modules`); fix `test_one` or `worktree_setup` in `.project/pipeline.toml`, then `pipeline resume {tid}`\\n```\\n{out[-1200:]}\\n```")`. Add a two-line comment above it: the shell\'s own 126/127 means the runner never started (`SHELL_CANNOT_RUN`, the codes `register` already knows), and the mark must lead because the classifiers are `startswith` (DEC-065, DEC-089). - Run `uv run --group dev pytest -q tests/test_gate.py -k "cannot_start or errors_instead_of_failing"`. Expect 3 passed. Commit `fix(TICKET-146): report a test_one the shell cannot start as an environment failure`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. A red test file added on the branch but not listed in `test_file` gets its own `UNLISTED-TEST: ` finding in `pipeline/core/gate.py`; triage\'s red test is `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage`. - Write two tests first, at the end of `tests/test_gate.py`, each building the same git fixture as triage\'s `test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` (a `git init -qb main` project, `FIXTURE` ticket committed on main, worktree `ticket/001` at `.worktrees/TICKET-001`, `base = "main"`, `test_one = "echo test_broken; exit 1"`, `test_suite = "true"`). Copy the fixture code into each test body; do not import a helper this branch adds. - `test_a_red_test_added_on_the_branch_escalates_without_charging_the_plan`: `test_suite_without_new = "echo 1 failed; ! test -f test_extra.py"`; the branch commits `test_thing.py` and `test_extra.py`. Assert `not ok`; `hits = [f for f in failures if f.startswith("UNLISTED-TEST: ")]`; `len(hits) == 1` and "`test_extra.py`" in `hits[0]`; `res = gate_result(ok, failures, "plan-validation")`; `res == "invalid-test"`; `_, counters = transition("plan-validation", res, {})`; `counters.get("plan_validation_attempts", 0) == 0`; `gate_result(ok, failures, "revalidating") == "fail"`. - `test_an_added_file_that_leaves_base_green_keeps_the_pre_existing_finding`: `test_suite_without_new = "echo 1 failed; ! test -f broken"`; the branch commits `test_thing.py`, `test_extra.py` and an empty `broken`. Assert `not ok`, `not any(f.startswith("UNLISTED-TEST: ") for f in failures)`, `any("RED -- pre-existing breakage" in f for f in failures)`, and `gate_result(ok, failures, "plan-validation") == "bad-plan"`. - Run `uv run --group dev pytest -q tests/test_gate.py -k "added_on_the_branch or leaves_base_green"`. Expect 2 failed (triage\'s repro and the escalation test), 1 passed. - In `pipeline/core/gate.py`, replace `INVALID_TEST_MARKS = (INVALID_TEST_MARK,)` with `UNLISTED_TEST_MARK = "UNLISTED-TEST: "` then `INVALID_TEST_MARKS = (INVALID_TEST_MARK, UNLISTED_TEST_MARK)`, with a comment: a red test the branch ADDED in a file `test_file` does not list belongs to `triage` like an unreachable assertion does (`CLAIMS`), so it routes to the same no-charge `invalid-test` verdict (TICKET-146). - In `pipeline/core/gate.py`, add `_branch_added(wd: Path, cfg: dict, tests: list[str]) -> list[str]` after `_copy_tests()`. It runs `run_cmd(f"git -c core.quotePath=false diff --name-only --no-renames --diff-filter=A {shlex.quote(base_ref(cfg))} HEAD", wd)`, returns `[]` on a non-zero exit, and otherwise returns each output line `p` where `p` is non-empty, `not p.startswith(".project/")`, `p` is not in `declared = {x.split("::")[0] for x in tests}`, `Path(p).suffix` is in `{Path(x).suffix for x in declared} - {""}`, and `(wd / p).is_file()`. The `is_file()` guard drops a line `bounded_output()` truncated. Docstring: files absent from base that look like the ticket\'s own tests; empty when git cannot answer, so the caller keeps DEC-089\'s fail-closed finding. - In `pipeline/core/gate.py`, add `_added_red_on_base(project: Path, cfg: dict, wd: Path, suite_tests: list[str], added: list[str]) -> str | None` after `_base_suite()`. Body: `with base_checkout(project, cfg) as (base_wt, _):` return `None` if `base_wt is None`; else `_copy_tests(wd, base_wt, added)` and `code, out = _confirmed_suite(format_tests_cmd(cfg["test_suite_without_new"], suite_tests), base_wt)`. After the `with`, return `out if code != 0 and suite_ran(code, out) else None`. Docstring: the added files are absent from base, so the copy overwrites nothing base has, unlike the copy DEC-104 forbids in `_base_suite()`. - In `pipeline/core/gate.py`, change `_copy_tests()`\'s docstring line to `Called by _base_findings() and _added_red_on_base(); _base_suite() must not call it (TICKET-104).` - In `gate()`\'s `elif not why:` arm, compute `added = _branch_added(wd, cfg, tests)` and `added_out = (_added_red_on_base(project, cfg, wd, suite_tests, added) if added and not _unsafe_rel(added) else None)`. When `added_out is not None`, append `f"{UNLISTED_TEST_MARK}suite excluding {names} is RED in the ticket\'s worktree and green on base `{base_ref(cfg)}`, and base turns RED once this branch\'s added file(s) {listed} are copied onto it -- the branch added a failing test that `test_file` does not list. Only `triage` may write `test_file` (`CLAIMS`), so no re-plan can repair it: list the test in `test_file` or remove it, then `pipeline resume {tid} --stage triage`"` plus the two fences ```` ```on base with the added files ```` (`added_out[-1200:]`) and ```` ```in the ticket\'s worktree ```` (`out[-1200:]`), where `listed = " ".join(f"`{x}`" for x in added)`. Otherwise append today\'s `suite excluding {names} is RED -- pre-existing breakage, fix that first` finding unchanged. - Run `uv run --group dev pytest -q tests/test_gate.py`. Expect 0 failed. Commit `fix(TICKET-146): name a red test the branch added but test_file does not list`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Document the widened `invalid-test` verdict and the exit-127 environment finding in `CLAUDE.md` and `README.md`. - In `CLAUDE.md`, in the `gate_result()` bullet, change `` `invalid-test` (the selected test hides statically unreachable statements) `` to `` `invalid-test` (the selected test hides statically unreachable statements, or a test file the branch added but `test_file` does not list turns the suite red -- `UNLISTED-TEST: `) `` and change `` `environment` (the suite is red on base too) `` to `` `environment` (the suite is red on base too, or the shell exits 126/127 running `test_one`) ``. - In `README.md`, after the paragraph that opens `A Tier A failure at `plan-validation` whose findings include an` and names `INVALID-TEST: `, add one paragraph: an `UNLISTED-TEST: ` finding takes the same `invalid-test` route; the gate raises it only when the suite is red in the worktree, green on base, and red again on base once the files the branch added (same suffix as a `test_file` path, outside `.project/`) are copied onto it. In the `ENVIRONMENT: ` paragraph after it, add one sentence: `test_one` exiting 126 or 127 with no test name in its output is an `ENVIRONMENT: ` finding, usually a runner `worktree_setup` did not install. - Run `uv run --group dev pytest -q tests/test_stages.py`. Expect 0 failed. Commit `docs(TICKET-146): document the unlisted-test and cannot-start gate findings`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-10-01 12:20:00Z · planning · note

Plan written: three steps across `pipeline/core/gate.py`, `tests/test_gate.py`, `CLAUDE.md` and `README.md`.

1. Design for finding 1: name the test, not exclude it. Excluding a file needs a per-runner file-level deselect, and it would hide triage's red test from Tier A.
2. The new `UNLISTED-TEST: ` finding joins `INVALID_TEST_MARKS`, so it reuses the existing no-charge `invalid-test` row. `machine.py` and `supervisor.py` stay untouched, which matches the ticket's expected files.
3. Known limit: a red test added inside a file base already has keeps `bad-plan`. DEC-104 rejected the name parsing that would catch it. The Rust grid case is caught only when the grid spans added files.

Out of scope, not edited: the `invalid-test` comments in `pipeline/core/machine.py` (FENCED) and the `gate_result()` docstring in `pipeline/daemon/supervisor.py` still describe only unreachable code. A later ticket can widen them.

The gate-run entry above (12:15:57Z) is my own `pipeline gate` run. Its findings are the two expected pre-dispatch kinds: `files_declared` empty, and steps naming files the result declares.

### 2026-10-01 12:16:23Z · planning · session · session=4b7f928b-bf2e-47e1-aad4-54b742d3c9de

`planning` ran as session `4b7f928b-bf2e-47e1-aad4-54b742d3c9de`
- replay: `claude --resume 4b7f928b-bf2e-47e1-aad4-54b742d3c9de`
- log: `.project/logs/TICKET-146-planning-4b7f928b.log`
- cost: $1.88 of a $10 cap
- tokens: 35,132 out (22,200 thinking) · 42 in · 1,588,421 cache read · 106,858 cache write

### 2026-10-01 12:16:23Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ 3-step plan: exit 126/127 from test_one becomes ENVIRONMENT; a red test file the branch added but test_file omits, proven red on base with only the added files, becomes UNLISTED-TEST routed to invalid-test

### 2026-10-01 12:18:52Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` fails as required
```
  (wt / "test_thing.py").write_text("def test_broken(): assert False")
        (wt / "test_extra.py").write_text("def test_extra(): assert False")
        sh("git add -A && git commit -qm branch", cwd=wt)
        ok, failures = gate(d, "TICKET-001", workdir=wt)
        assert not ok
>       assert not any("pre-existing breakage" in f for f in failures), failures
E       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, already quoted in the `## Thread` entry `2026-10-01 12:17:33Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage.<locals>.<genexpr> at 0x7f0063043e00>)

tests/test_gate.py:1792: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.23s ===============================

```
- ok: `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure` fails as required
```
CKET-146: exit 127 means the runner never started, not that the
        test errored; no re-plan fixes it."""
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "no-such-runner {test}"\n'
            'test_suite = "true"\ntest_suite_without_new = "true"\n')
        ok, failures = gate(d, "TICKET-001")
        assert not ok
>       assert gate_result(ok, failures, "plan-validation") == "environment", failures
E       AssertionError: ['`test_thing.py::test_broken` exited non-zero but its name never appears in the output -- it errored rather than fail...al output, already quoted in the `## Thread` entry `2026-10-01 12:17:33Z · plan-validation · gate · verdict=FAIL` --*']
E       assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_gate.py:1805: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` fails on base `main` too -- the bug is not already fixed upstream
```
hread` entry `2026-10-01 12:17:35Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage.<locals>.<genexpr> at 0x7f098957eb50>)

tests/test_gate.py:1792: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.49s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-k5s84yfa/base
      Built pipeline @ file:///tmp/pipeline-base-k5s84yfa/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 69ms

```
- ok: `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure` fails on base `main` too -- the bug is not already fixed upstream
```
CKET-146: exit 127 means the runner never started, not that the
        test errored; no re-plan fixes it."""
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "no-such-runner {test}"\n'
            'test_suite = "true"\ntest_suite_without_new = "true"\n')
        ok, failures = gate(d, "TICKET-001")
        assert not ok
>       assert gate_result(ok, failures, "plan-validation") == "environment", failures
E       AssertionError: ['`test_thing.py::test_broken` exited non-zero but its name never appears in the output -- it errored rather than fail...al output, already quoted in the `## Thread` entry `2026-10-01 12:17:35Z · plan-validation · gate · verdict=FAIL` --*']
E       assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_gate.py:1805: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```

### 2026-10-01 12:30:00Z · plan-validation · note

**Plan validation: PASS on all eight items.**

long: eight scored items plus one unverified item; each needs its evidence.

1. **Root cause: pass.** `gate()` cannot tell a branch-added red file from base breakage, because `_base_suite()` runs base's own files (DEC-104). Separately, the `elif node not in out:` arm (gate.py:812) ignores exit 126/127. Both fixes change classification, not the tests.
2. **Decisions: pass.** `_base_suite()` stays unchanged (DEC-104). Only a rerun that is RED and passes `suite_ran()` raises `UNLISTED-TEST: `; every other outcome keeps `bad-plan` (DEC-089). `machine.py:203` already has the `("plan-validation", "invalid-test")` row (DEC-118). The 126/127 arm skips base proof. `## Decisions` justifies that: at `plan-validation` no plan affects `test_one`.
3. **Scope: pass.** Step 3 has no test criterion. Without it, the `gate_result()` bullet in `CLAUDE.md` turns false.
4. **Falsifiable: pass.** Remove the suffix filter, and the `broken` file reaches base: `leaves_base_green` goes red. Remove the arm, and `names_the_cause` still sees `errored rather than failed`.
5. **No research: pass.** Every named function and line exists.
6. **Riskiest step: pass.** Step 2 names a fallback: revert step 2, keep step 1, return `blocked`.
7. **Regression: pass.** `test_a_suite_red_only_in_the_worktree_still_charges_the_plan` and `tests/test_dispatch.py::_gating_project` add only `broken`, a file with no suffix. `test_gate_base_suite_does_not_inherit...` modifies `test_thing.py` (`--diff-filter=A` skips it). `tests/test_gate.py:391` tests the suite command, not `test_one`.
8. **Blast radius: pass.** 2 code files, 2 doc files.

**Unverified:** that dash and bash omit the arguments from a 127 "not found" message. I would have run `uv run --group dev pytest -q tests/test_gate.py -k cannot_start`.

### 2026-10-01 12:21:36Z · plan-validation · session · session=e4121d12-d6fa-444a-aacb-dd895fde9750

`plan-validation` ran as session `e4121d12-d6fa-444a-aacb-dd895fde9750`
- replay: `claude --resume e4121d12-d6fa-444a-aacb-dd895fde9750`
- log: `.project/logs/TICKET-146-plan-validation-e4121d12.log`
- cost: $1.11 of a $3 cap
- tokens: 15,579 out (7,480 thinking) · 34 in · 1,012,739 cache read · 74,897 cache write

### 2026-10-01 12:21:36Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items; root cause, DEC-089/104/074/118/137 compliance and both fixtures checked against gate.py and the tests

### 2026-10-01 12:26:06Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-01 12:28:18Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` fails as required
```
  (wt / "test_thing.py").write_text("def test_broken(): assert False")
        (wt / "test_extra.py").write_text("def test_extra(): assert False")
        sh("git add -A && git commit -qm branch", cwd=wt)
        ok, failures = gate(d, "TICKET-001", workdir=wt)
        assert not ok
>       assert not any("pre-existing breakage" in f for f in failures), failures
E       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, already quoted in the `## Thread` entry `2026-10-01 12:27:02Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage.<locals>.<genexpr> at 0x7f025df9be00>)

tests/test_gate.py:1792: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================

```
- ok: `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure` fails as required
```
CKET-146: exit 127 means the runner never started, not that the
        test errored; no re-plan fixes it."""
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "no-such-runner {test}"\n'
            'test_suite = "true"\ntest_suite_without_new = "true"\n')
        ok, failures = gate(d, "TICKET-001")
        assert not ok
>       assert gate_result(ok, failures, "plan-validation") == "environment", failures
E       AssertionError: ['`test_thing.py::test_broken` exited non-zero but its name never appears in the output -- it errored rather than fail...al output, already quoted in the `## Thread` entry `2026-10-01 12:27:02Z · plan-validation · gate · verdict=FAIL` --*']
E       assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_gate.py:1805: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: `tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage` fails on base `main` too -- the bug is not already fixed upstream
```
hread` entry `2026-10-01 12:27:03Z · plan-validation · gate · verdict=FAIL` --*']
E       assert not True
E        +  where True = any(<generator object test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage.<locals>.<genexpr> at 0x7f063bb605f0>)

tests/test_gate.py:1792: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_red_test_added_on_the_branch_is_not_reported_as_pre_existing_breakage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.44s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-t5h1hlwy/base
      Built pipeline @ file:///tmp/pipeline-base-t5h1hlwy/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 91ms

```
- ok: `tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure` fails on base `main` too -- the bug is not already fixed upstream
```
CKET-146: exit 127 means the runner never started, not that the
        test errored; no re-plan fixes it."""
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "no-such-runner {test}"\n'
            'test_suite = "true"\ntest_suite_without_new = "true"\n')
        ok, failures = gate(d, "TICKET-001")
        assert not ok
>       assert gate_result(ok, failures, "plan-validation") == "environment", failures
E       AssertionError: ['`test_thing.py::test_broken` exited non-zero but its name never appears in the output -- it errored rather than fail...al output, already quoted in the `## Thread` entry `2026-10-01 12:27:04Z · plan-validation · gate · verdict=FAIL` --*']
E       assert 'bad-plan' == 'environment'
E         
E         - environment
E         + bad-plan

tests/test_gate.py:1805: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_test_runner_that_cannot_start_is_an_environment_failure
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```

### 2026-10-01 12:28:19Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-10-01 · implementing · note

**Implementing: all 3 plan steps done.**

- [x] 1. exit 126/127 -> `ENVIRONMENT: ` finding (eb6cb98)
- [x] 2. `UNLISTED-TEST: ` finding via `_branch_added()` + `_added_red_on_base()` (fe4c903)
- [x] 3. `CLAUDE.md` and `README.md` updated (8af2bef)

Both triage repro tests and the three new tests pass (each new test was red first; the `leaves_base_green` test passed before the code, as the plan expected, because it guards the suffix filter). `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py tests/test_machine.py tests/test_stages.py`: 323 passed. `git diff --name-only main...HEAD -- pipeline/core/machine.py pipeline/daemon/supervisor.py` prints nothing.

### 2026-10-01 12:30:12Z · implementing · session · session=4a2eafb0-7702-44c2-8998-24e0bb2d7adf

`implementing` ran as session `4a2eafb0-7702-44c2-8998-24e0bb2d7adf`
- replay: `claude --resume 4a2eafb0-7702-44c2-8998-24e0bb2d7adf`
- log: `.project/logs/TICKET-146-implementing-4a2eafb0.log`
- cost: $0.48 of a $9 cap
- tokens: 9,835 out (80 thinking) · 36 in · 838,418 cache read · 52,539 cache write

### 2026-10-01 12:30:12Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ exit 126/127 from test_one is now ENVIRONMENT; a red test file added on the branch but not in test_file is UNLISTED-TEST routed to invalid-test; 323 tests pass

### 2026-10-01 · review · note

**Review (pass 1, delta `main...HEAD`, eb6cb98..8af2bef): no blocking findings.**

Evidence:
- `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py tests/test_machine.py tests/test_stages.py`: `323 passed in 22.28s`.
- The 7 named acceptance tests: `7 passed, 104 deselected`.
- `git diff --name-only main...HEAD -- pipeline/core/machine.py pipeline/daemon/supervisor.py` prints nothing.
- Both code arms match `## Plan` step 1 and step 2. `_base_suite()` is unchanged (DEC-104). The UNLISTED-TEST arm runs only under `elif not why:` after a `suite_ran()` RED on base with the added files (DEC-089).

Non-blocking notes:
1. (nit, plan drift) The plan said to copy the fixture into each test body. `tests/test_gate.py` instead defines `_branch_added_fixture()` in the same file. This does not break DEC-017: the helper travels with the copied file, and no new name is imported from another module.
2. (minor, edge case) `_branch_added()` runs a two-dot `git diff --diff-filter=A <base> HEAD`, as the plan specifies. A file base DELETED after the branch cut also reads as `A`. If that file is red, the gate reports UNLISTED-TEST ("the branch added") for a file the branch never added, and the ticket escalates instead of charging `bad-plan`. A three-dot `<base>...HEAD` would restrict the set to the branch's own additions. This is untested; it is not a regression of an existing test.

### 2026-10-01 12:31:41Z · review · session · session=d919bdbb-9b7d-4710-996f-e594a8980c61

`review` ran as session `d919bdbb-9b7d-4710-996f-e594a8980c61`
- replay: `claude --resume d919bdbb-9b7d-4710-996f-e594a8980c61`
- log: `.project/logs/TICKET-146-review-d919bdbb.log`
- cost: $0.59 of a $5 cap
- tokens: 5,618 out (2,113 thinking) · 18 in · 384,489 cache read · 49,729 cache write

### 2026-10-01 12:31:41Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ no blocking findings; all 7 named tests and the 4-file run (323 passed) pass, machine.py and supervisor.py untouched; 2 non-blocking notes in Thread

### 2026-10-01 12:32:58Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-10-01 13:07:43Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/146


Current branch ticket/146 is up to date.
Already up to date.
Updating ed2fa9a..8af2bef
Fast-forward
 CLAUDE.md             |   6 ++-
 README.md             |   9 ++++-
 pipeline/core/gate.py |  84 +++++++++++++++++++++++++++++++++++++----
 tests/test_gate.py    | 101 ++++++++++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 190 insertions(+), 10 deletions(-)

```

### 2026-10-01 13:07:43Z · merging · decision

decision recorded as `DEC-146`
