---
id: TICKET-109
stage: done
class: bugfix
branch: ticket/109
test_file: tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/gate.py
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
- tests/test_gate.py
- tests/test_machine.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 17
  plan_files: 8
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 77696303-5f3b-44c9-b9bb-d2c111926228
  replay: claude --resume 77696303-5f3b-44c9-b9bb-d2c111926228
  log: .project/logs/TICKET-109-review-77696303.log
  cost_usd: 2.196444
approved_by: chezzijr
approved_at: '2026-09-04T01:48:10.673266+00:00'
---

## Summary

Fixed: a `test_file` that exits 0 in the ticket's worktree AND on base now
returns its own gate verdict, `load-flaky`, and escalates charging no
counter -- it previously charged `plan_validation_attempts` and asked
`planning` to fix a plan that was not wrong, since `CLAIMS` gives `test_file`
to `triage` alone and no re-plan could repoint it.

`pipeline/core/gate.py` gained a fourth `startswith` allowlist
`LOAD_FLAKY_MARK = "LOAD-FLAKY: "`, a `load_flaky()` classifier and a finding
that names base's own PASS; `_base_findings()` now returns a third dict,
`zero_on_base`, of tests whose base run exited 0; `gate_result()` in
`pipeline/daemon/supervisor.py` returns the new `load-flaky` verdict at
`plan-validation` only; `transition()` in `pipeline/core/machine.py` gained
an enumerated `("plan-validation", "load-flaky")` row that escalates
charging no counter. `README.md` and `CLAUDE.md` document the new verdict.

Implemented in four commits, `d66b230`, `07d715f`, `e1d5e2d`, `cd089fd` --
the last was not in `## Plan`: the full suite, run after landing the source
change, found two `tests/test_dispatch.py` tests (already a declared file)
whose `test_one="true"` fixture now genuinely exits 0 on both trees and was
reclassified from `bad-plan` to `load-flaky`; `test_one` was pinned to a real
failure (`"false"`) to preserve their original intent. See the `implementing`
report entry for the full account.

Verified: `uv run --group dev pytest -q` -- `536 passed`.
`./pipeline/hooks/test_dangerous_commands.py` -- all 138 cases pass.

`review` re-ran both, fresh, and found no blocking issue: `536 passed in
55.28s`, `guard: all passed`, the five acceptance tests `5 passed in 0.28s`,
and every `grep` criterion. It recorded two nits it did not fix: the finding
writes `pipeline resume {t.id}` where `## Plan` step 10 said `{tid}`, and
`charged_round()`'s docstring (`pipeline/cli/metrics.py:402`) still lists
only `no-test-file` and `environment`.

`transition()` and `pipeline/core/machine.py` are in `machine.FENCED`, so this
ticket's diff parks at `awaiting-merge` for human review.

## Reproduction

`tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt`,
run with `uv run --group dev pytest -q tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt`.
It builds a `_git_ticket_project("fixed\n", "fixed\n")` -- exit 0 in the
worktree and on base -- calls `gate_result()` then `transition()`, and
asserts `plan_validation_attempts == 0`.

Failure:

    AssertionError: a load-flaky test_file charged plan_validation_attempts: {'plan_validation_attempts': 1}
    assert 1 == 0

expect: a load-flaky test_file charged plan_validation_attempts

## Digest

Files touched: `pipeline/core/gate.py`, `pipeline/daemon/supervisor.py`, `pipeline/core/machine.py`, `tests/test_gate.py`, `tests/test_dispatch.py`, `tests/test_machine.py`, `README.md`, `CLAUDE.md`.

Entry points: `gate_result()` at `pipeline/daemon/supervisor.py:1047`, called by `finish_gate()` at `pipeline/daemon/supervisor.py:1092`; `transition()`'s `plan-validation` rows at `pipeline/core/machine.py:156-183`.

Key functions in `pipeline/core/gate.py`: the `passing` loop at `:569-598` (the exit-0 finding is the `test not in on_base` arm at `:576-584`); `_base_findings()` at `:371-408`, which returns `(verdicts, on_base)` where `on_base` holds only tests that FAIL on base; `_base_verdict()` at `:325`, whose `hit` is True only on a base failure and whose `code == 0` arm produces the "exited 0 on base" verdict; the three classifiers `structural_only()` `:179`, `environment_only()` `:195`, `missing_test_file()` `:204`, over the marks `STRUCTURAL_MARKS` `:124`, `MISSING_TEST_MARK` `:140`, `ENVIRONMENT_MARK` `:191`.

Today's path for this bug: worktree exit 0 parks the test in `passing` (`:548`), `_base_findings()` runs, base exits 0 so `on_base` stays empty, the `test not in on_base` arm fires, no allowlist matches its opener, and `gate_result()` returns `bad-plan`.

Gotcha 1 -- `tests/test_gate.py` may gain NO module-level import (DEC-065): DEC-017 copies that file onto a checkout of base, where a branch-only name is a collection error. The new classifier's unit test therefore goes in `tests/test_dispatch.py`, beside `test_a_missing_test_file_escalates_instead_of_charging_planning` at `tests/test_dispatch.py:1851`.

Gotcha 2 -- `gate()` must keep returning a 2-tuple (DEC-065, DEC-089), because findings reach the dispatcher as JSON. `_base_findings()` is private and carries no such promise; `tests/test_gate.py:910` is its only unpack outside `pipeline/core/gate.py`.

Gotcha 3 -- the allowlists are `startswith`, so a new finding must START with its mark. The DEC-071 sentence is kept verbatim BEHIND the mark, not appended to it.

Gotcha 4 -- two existing tests grep the exit-0 finding: `tests/test_gate.py:846` (`test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector`, worktree and base both exit 0 -- the load-flaky path) asserts `"exited 0"` and `"PASSES"`, and `tests/test_gate.py:831` (`test_gate_fails_an_exit_zero_test_and_names_both_causes`, no worktree, base never consulted) asserts `"PASSES"` and `"matched no test"`. Both substrings must survive in the new text.

Gotcha 5 -- `_base_findings()` has two call sites in `pipeline/core/gate.py`: `:567` (at least one test exited 0) and `:633` (every test failed, map discarded).

Baseline measured on `9dceb43`: `uv run --group dev pytest -q tests/test_gate.py` printed `1 failed, 80 passed in 1.69s`, the one failure being this ticket's repro test.

## Decisions checked

- DEC-065 -- binding. `structural_only()` is a `startswith` allowlist and a new finding needs its own mark; `gate()` keeps returning a 2-tuple; `tests/test_gate.py` may gain no import, which is why the new classifier is unit-tested in `tests/test_dispatch.py`; only `plan-validation` splits the verdict.
- DEC-087 -- binding, and the shape this plan mirrors. `no-test-file` is its own verdict with an enumerated `transition()` row that charges nothing, because `CLAIMS` gives `test_file` to `triage` alone. The alternative rejected there -- adding the opener to `STRUCTURAL_MARKS` -- is rejected here for the same reason: `fail` routes to `planning` and charges `structural_gate_failures`.
- DEC-089 -- binding. `ENVIRONMENT: ` is a `startswith` prefix for the anti-forgery reason, and its `("plan-validation", "environment")` row is explicit rather than left to the unknown-pair fallback. `LOAD-FLAKY: ` copies both choices.
- DEC-090 -- binding, and narrowed by this plan (see `## Decisions`). Its "failing nowhere stays a FAIL, with DEC-071's finding text byte-identical" clause now holds on the arm where base did NOT exit 0; the base-exit-0 arm keeps that sentence verbatim behind the new mark.
- DEC-071 -- binding. One finding names both causes of an exit-0 run; the new text still names both.
- DEC-017 -- binding. The branch's test file is copied onto the base checkout, which is what gotcha 1 above is about.
- DEC-029 -- binding. `revalidating` keeps `fail` whatever the findings say, so `gate_result()`'s new branch stays under its `stage != "plan-validation"` guard.
- DEC-103 -- binding, and satisfied without an edit. `charged_round()` in `pipeline/cli/metrics.py` asks `transition()` whether a verdict charged, so a new verdict row needs no change there.
- Grep terms used in `.project/decisions/`: `startswith`, `STRUCTURAL_MARKS`, `ENVIRONMENT_MARK`, `no-test-file`, `exited 0`, `test_file`, `CLAIMS`, `plan_validation_attempts`.

## Plan

1. In `tests/test_dispatch.py`, add `test_a_load_flaky_test_escalates_instead_of_charging_planning` directly below `test_a_missing_test_file_escalates_instead_of_charging_planning` (which ends at `tests/test_dispatch.py:1867`): a docstring citing TICKET-109, then `from pipeline.core.gate import LOAD_FLAKY_MARK, load_flaky` INSIDE the function body (DEC-065 -- this file may import freely, `tests/test_gate.py` may not), then `assert load_flaky([LOAD_FLAKY_MARK + "`t.py::x` exited 0"]) is True`, `assert load_flaky(["`t.py::x` exited 0 -- it must fail before implementation"]) is False`, `assert load_flaky([]) is False`, `assert supervisor.gate_result(False, [LOAD_FLAKY_MARK + "`t.py::x` exited 0"], "plan-validation") == "load-flaky"`, and `assert supervisor.gate_result(False, [LOAD_FLAKY_MARK + "`t.py::x` exited 0"], "revalidating") == "fail"`.
2. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_load_flaky_test_escalates_instead_of_charging_planning` and watch it fail with `ImportError: cannot import name 'LOAD_FLAKY_MARK' from 'pipeline.core.gate'`; this is the failing test the next four steps turn green, and `tests/test_dispatch.py` needs no other edit.
3. In `pipeline/core/gate.py`, below `ENVIRONMENT_MARKS` at `:192`, add `LOAD_FLAKY_MARK = "LOAD-FLAKY: "` and `LOAD_FLAKY_MARKS = (LOAD_FLAKY_MARK,)` under a comment reading "A fourth `startswith` allowlist, same shape and same reason as `ENVIRONMENT_MARKS` (DEC-089): a substantive finding carries captured test output, and a substring match would let a ticket quote itself a free escalation."
4. In `pipeline/core/gate.py`, below `missing_test_file()` at `:210`, add `def load_flaky(failures: list[str]) -> bool:` returning `any(f.startswith(LOAD_FLAKY_MARKS) for f in failures)`, with the docstring "Does `failures` include a `test_file` that exited 0 in the ticket's worktree AND on base? `any`, not `all`, exactly like `missing_test_file()`: `CLAIMS` gives `test_file` to `triage` alone, so no re-plan can repoint it and a plan that is ALSO bad still cannot satisfy Tier A."; rerun the step 2 command and watch it fail on `assert supervisor.gate_result(...) == "load-flaky"` with `'bad-plan'`.
5. In `pipeline/daemon/supervisor.py`, add `load_flaky` to the `from pipeline.core.gate import (...)` list at `:24-25` (alphabetical: `environment_only, gate, load_flaky, missing_test_file, plan_steps, structural_only`), and in `gate_result()` insert `if load_flaky(failures): return "load-flaky"` between the `missing_test_file(failures)` branch at `:1063-1064` and the `environment_only(failures)` branch at `:1065`, commented "checked beside `missing_test_file()` and before `environment_only()`: both verdicts belong to `triage`'s field and either escalates charging nothing, so the order between them only picks the verdict string a human reads."
6. In `pipeline/daemon/supervisor.py`, rewrite `gate_result()`'s docstring at `:1048-1058` so it says `plan-validation` splits `fail` into FIVE verdicts, naming `load-flaky` (TICKET-109) as "the `test_file` exited 0 in the worktree and on base" beside `no-test-file` and `environment`, and add `("revalidating", "load-flaky")` to the list of unknown pairs the `revalidating` guard exists to avoid; rerun the step 2 command and watch it pass.
7. In `pipeline/core/gate.py`, change `_base_findings()` (`:371`) to return the 3-tuple `(verdicts, on_base, zero_on_base)`: declare `zero_on_base: dict[str, str] = {}` beside `on_base`, add `elif code == 0: zero_on_base[test] = out` after the `if hit:` block in its loop at `:405-406`, give the three early returns at `:392`, `:398` and `:403` a third `{}`, and extend the docstring with "The third dict maps each test whose base run exited 0 to that run's output -- base proves nothing there, and a test that exits 0 on BOTH trees is load-flaky (TICKET-109)."
8. In `pipeline/core/gate.py`, unpack the new element at both call sites -- `base, on_base, zero_on_base = _base_findings(project, cfg, wd, candidates)` at `:567` and `base, _, _ = _base_findings(project, cfg, wd, candidates)` at `:633` -- and declare `zero_on_base: dict[str, str] = {}` beside `on_base: dict[str, str] = {}` at `:565`, so the loop below sees an empty dict when the base run never happened.
9. In `pipeline/core/gate.py`, split the `passing` loop's `if test not in on_base:` arm at `:576` into `if test in zero_on_base:` first and `elif test not in on_base:` second, leaving the second arm's finding text byte-identical (DEC-090); the first arm appends one f-string, described in full by step 10, above a comment recording that the mark must lead because the allowlists are `startswith`.
10. The finding step 9's first arm appends to `findings` in `pipeline/core/gate.py` reads, as one f-string: `LOAD_FLAKY_MARK`, then "`{test}` exited 0 -- it must fail before implementation. Either it PASSES, or `test_one` matched no test at all; a runner that names a node only on failure makes the two identical here. It exited 0 on base `{base_ref(cfg)}` too, where this branch's fix is absent, so it PASSES there as well and no re-plan can make it fail. Only `triage` may write `test_file` (`CLAIMS`): repoint it at a test that fails on an idle box, then `pipeline resume {tid} triage`", then a newline and a fenced block opened ```on base holding `zero_on_base[test][-1200:]`, then a newline and a fenced block opened ```in the ticket's worktree holding `out[-1200:]` -- the two-fence shape the `ENVIRONMENT: ` finding at `:661-668` already uses.
11. In `tests/test_gate.py`, change the `_base_findings()` unpack at `:910` from `out, on_base = ...` to `out, on_base, zero = ...` and add `assert zero == {}, zero` below the existing `set(on_base)` assert; add NO module-level import to this file (DEC-065).
12. Run `uv run --group dev pytest -q tests/test_gate.py` and check it exits 0 -- `test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt` now passes, because `gate_result()` returns `load-flaky` and `transition()` escalates it through the unknown-pair fallback charging nothing -- then commit `pipeline/core/gate.py`, `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py` and `tests/test_gate.py` as `fix(TICKET-109): report a test that exits 0 on base too as load-flaky`.
13. In `tests/test_machine.py`, add `test_a_load_flaky_test_file_is_an_enumerated_row_that_escalates` below `test_an_environment_verdict_escalates_and_charges_no_counter` (`tests/test_machine.py:364-365`), mirroring `test_a_missing_test_file_is_an_enumerated_row_that_escalates`: `nxt, c = t("plan-validation", "load-flaky")`, `assert nxt == "escalated"`, `assert c == {}`, and `assert '"load-flaky"' in inspect.getsource(M.transition), "the pair must be an enumerated row, not the unknown-pair fallback"`, with a docstring saying the first two asserts pass vacuously through the unknown-pair fallback so the source assert is the only part that fails before the row exists; run `uv run --group dev pytest -q tests/test_machine.py::test_a_load_flaky_test_file_is_an_enumerated_row_that_escalates` and watch it fail on the source assert.
14. In `pipeline/core/machine.py`, add `case ("plan-validation", "load-flaky"): return "escalated", c` directly below the `no-test-file` row (`:174-178`), commented "the ticket's `test_file` exited 0 in the worktree AND on base -- it reproduces the bug only under load, so Tier A can never be satisfied. `CLAIMS` gives that field to `triage` alone, so no counter is charged and no stage is retried: a human repoints the test or re-runs triage. The row is explicit rather than left to the unknown-pair fallback, which escalates identically but without a row a reader can find (DEC-089)."; rerun the step 13 command, check it passes, and commit `pipeline/core/machine.py` and `tests/test_machine.py` as `fix(TICKET-109): escalate a load-flaky test_file through its own transition row`.
15. In `README.md`, add this paragraph after the `no-test-file` paragraph at `:505-509`: "A Tier A failure at `plan-validation` whose findings include a `LOAD-FLAKY: ` finding -- `test_file` exited 0 in the ticket's worktree and on base, so it reproduces the bug only under load -- charges nothing either. `gate_result()` returns `load-flaky` and the ticket escalates on the first one, for the same reason: only `triage` may write `test_file`, so no re-plan can repoint it, and the finding says base PASSES too, so a human re-runs triage instead of reading it as a bad plan."
16. In `CLAUDE.md`, update the `gate_result()` gotcha at `:318-331`: "four verdicts" becomes "five verdicts", the verdict list gains "`load-flaky` (the `test_file` exits 0 in the worktree and on base)", "the last two escalate and charge nothing" becomes "the last three escalate and charge nothing", and the allowlist sentence becomes "`MISSING_TEST_MARK`, `LOAD_FLAKY_MARKS` and `ENVIRONMENT_MARKS` are three more `startswith` allowlists beside it, checked by `missing_test_file()`, `load_flaky()` and `environment_only()` in that order, all before `structural_only()`", with "both apply at `plan-validation` only" becoming "all three apply at `plan-validation` only"; commit `README.md` and `CLAUDE.md` as `docs(TICKET-109): document the load-flaky gate verdict`.
17. Run `uv run --group dev pytest -q` and check it exits 0, then run `./pipeline/hooks/test_dangerous_commands.py` and check it exits 0 -- no guard file changed, so this second run is a regression check on the `pipeline/core/machine.py` edit's neighbours only.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt` exits 0.
- `uv run --group dev pytest -q tests/test_gate.py` exits 0; the baseline measured on `9dceb43` failed on exactly that repro test and no other, so no other test in the file may regress.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_load_flaky_test_escalates_instead_of_charging_planning` exits 0.
- `uv run --group dev pytest -q tests/test_machine.py::test_a_load_flaky_test_file_is_an_enumerated_row_that_escalates` exits 0.
- `uv run --group dev pytest -q tests/test_gate.py::test_gate_fails_an_exit_zero_test_and_names_both_causes tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector` exits 0, which is DEC-071's "PASSES" and "matched no test" phrasing surviving on both arms.
- `uv run --group dev pytest -q` exits 0.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.
- `grep -q 'load-flaky' README.md` exits 0, and `grep -q 'load_flaky()' CLAUDE.md` exits 0.
- `grep -c 'into four' CLAUDE.md` prints `0`.
- `grep -q 'LOAD-FLAKY: ' pipeline/core/gate.py` exits 0, and `grep -q 'load_flaky' pipeline/daemon/supervisor.py` exits 0.

## Decisions

**A `test_file` that exits 0 in the ticket's worktree AND on base is its own gate verdict, `load-flaky`, and it escalates charging no counter.** It is DEC-087's argument for `no-test-file`, on a second field of the same kind: `CLAIMS` gives `test_file` to `triage` alone, so `planning` cannot repoint the test, every re-plan reruns the identical gate, and the ticket burns `plan_validation_attempts` to reach the escalation it could have had on the first run. Adding the opener to `STRUCTURAL_MARKS` was rejected for DEC-087's reason: `fail` routes to `planning` and charges `structural_gate_failures`, which is one counter to the left of the same wasted loop.

**`load_flaky()` asks `any`, not `all`.** `missing_test_file()` is the model. A plan that is ALSO bad still cannot satisfy Tier A while this finding stands, so a second finding must not cancel the escalation. It also means the base run's own "exited 0 on base, so base proves nothing" verdict, which rides in the same list, does not change the outcome.

**`LOAD-FLAKY: ` leads the finding, and DEC-090's byte-identical clause now holds on one arm only.** The classifiers are `startswith` allowlists (DEC-065, DEC-089), so the mark cannot be appended. DEC-071's sentence is preserved verbatim behind the mark, and the arm where base did NOT exit 0 -- base errored, base was never consulted, or there is no ticket worktree -- keeps the finding byte-identical as DEC-090 requires. Everything unproven still falls through to the old finding and the old charge, which is DEC-089's fail-closed rule.

**`_base_findings()` returns a 3-tuple; `gate()` still returns a 2-tuple.** DEC-065's constraint is on `gate()`, whose findings travel to the dispatcher as JSON, and on `tests/test_gate.py`, which DEC-017 copies onto a checkout of base where a branch-only name is a collection error. `_base_findings()` is private and has one unpack outside its own module. The new classifier is therefore unit-tested in `tests/test_dispatch.py` and never imported at the top of `tests/test_gate.py`.

**`revalidating` keeps `fail`.** `("revalidating", "load-flaky")` has no row, and returning the verdict there would escalate a stale plan instead of charging `stale_regate` (DEC-029, DEC-065). A load-flaky `test_file` reaching `revalidating` is rare, because `plan-validation` already escalated every ticket carrying one.

## Rollback

Revert the branch's three commits. The gate goes back to charging `plan_validation_attempts` for a `test_file` that exits 0 on both trees, which is this ticket's bug and not a broken pipeline.

For a narrower repair, delete the two `load_flaky(failures)` lines from `gate_result()` in `pipeline/daemon/supervisor.py`: the verdict returns to `bad-plan` while the clearer finding text, which names base's own PASS, stays in place. Do that if the new verdict escalates tickets whose plans really were bad.

Reverting `README.md` and `CLAUDE.md` alone is safe and changes no behaviour.

## Thread

### 2026-09-03 12:35:52Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-03 12:39:20Z · triage · session · session=a53dc580-d0f4-4b67-9df7-eb6594b3d93f

`triage` ran as session `a53dc580-d0f4-4b67-9df7-eb6594b3d93f`
- replay: `claude --resume a53dc580-d0f4-4b67-9df7-eb6594b3d93f`
- log: `.project/logs/TICKET-109-triage-a53dc580.log`
- cost: $0.00 of a $3 cap
- tokens: 0 out · 0 in · 0 cache read · 0 cache write

### 2026-09-03 12:39:20Z · triage · note

`triage` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-03 · triage · reproduction

Reproduced on `9dceb43`. Added
`test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt` to
`tests/test_gate.py`, mirroring
`test_a_nonexistent_test_file_does_not_charge_a_plan_validation_attempt`.
It builds a project where `test_one` exits 0 in the worktree and on base,
calls `gate_result()` then `transition()`, and asserts
`plan_validation_attempts == 0`. It fails today with
`plan_validation_attempts == 1`, confirming `gate_result()` returns
`bad-plan` for this finding instead of a verdict `machine.py` charges no
counter for.

`chore` files, if it stays a `chore`: `pipeline/core/gate.py` (a fourth
`startswith` allowlist beside `STRUCTURAL_MARKS`/`MISSING_TEST_MARK`/
`ENVIRONMENT_MARKS`, and the message naming base's own PASS), and a new
`("plan-validation", "load-flaky")` row in `pipeline/core/machine.py`
beside the `no-test-file` row it mirrors. Both files are `machine.FENCED`,
so this ticket parks at `awaiting-merge` however it lands.

### 2026-09-03 12:42:10Z · triage · session · session=9d0c7ad9-7699-435d-8295-a03c4cb62dfa

`triage` ran as session `9d0c7ad9-7699-435d-8295-a03c4cb62dfa`
- replay: `claude --resume 9d0c7ad9-7699-435d-8295-a03c4cb62dfa`
- log: `.project/logs/TICKET-109-triage-9d0c7ad9.log`
- cost: $0.41 of a $3 cap
- tokens: 4,921 out (718 thinking) · 36 in · 837,061 cache read · 43,911 cache write

### 2026-09-03 12:42:10Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- gate_result charges plan_validation_attempts for an exit-0-on-both-worktree-and-base test

### 2026-09-03 12:51:20Z · planning · plan

Plan written: 17 steps over 8 files, test-first, three commits.

The verdict split is the shape DEC-087 already built for `no-test-file`.
`pipeline/core/gate.py` gains `LOAD_FLAKY_MARK = "LOAD-FLAKY: "`, a fourth
`startswith` allowlist beside `STRUCTURAL_MARKS`, `MISSING_TEST_MARK` and
`ENVIRONMENT_MARKS`, plus `load_flaky()`, which asks `any` like
`missing_test_file()`. `_base_findings()` returns a third dict mapping each
test whose base run exited 0 to that output, so the `passing` loop can tell
"base also exits 0" from "base errored" and "base was never consulted"; only
the first arm gets the new finding, and the second keeps DEC-071's text
byte-identical as DEC-090 requires. `gate_result()` in
`pipeline/daemon/supervisor.py` returns `load-flaky` at `plan-validation`
only, and `transition()` in `pipeline/core/machine.py` gains the enumerated
row that escalates charging no counter.

Two constraints found while reading, both in `## Digest`: `gate()` must keep
returning a 2-tuple, and `tests/test_gate.py` may gain no module-level import,
because DEC-017 copies it onto a checkout of base. The new classifier is
therefore unit-tested in `tests/test_dispatch.py`.

Out of scope, noted: `pipeline/cli/metrics.py` needs no edit -- DEC-103's
`charged_round()` asks `transition()` which verdicts charge.

### 2026-09-03 12:51:33Z · planning · session · session=a0af2f23-c74b-404a-a14d-1bb3847aeef1

`planning` ran as session `a0af2f23-c74b-404a-a14d-1bb3847aeef1`
- replay: `claude --resume a0af2f23-c74b-404a-a14d-1bb3847aeef1`
- log: `.project/logs/TICKET-109-planning-a0af2f23.log`
- cost: $3.81 of a $10 cap
- tokens: 47,442 out (20,998 thinking) · 68 in · 2,854,779 cache read · 119,957 cache write

### 2026-09-03 12:51:33Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned the load-flaky gate verdict: a fourth LOAD-FLAKY startswith allowlist in gate.py, a load_flaky() branch in gate_result(), and an enumerated (plan-validation, load-flaky) row in transition()

### 2026-09-03 12:52:47Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt` fails as required
```
t gate_result
        ok, failures = gate(d, "TICKET-001", workdir=wt)
        assert not ok
        assert any("exited 0" in f and "PASSES" in f for f in failures), failures
        result = gate_result(ok, failures, "plan-validation")
        nxt, counters = transition("plan-validation", result, {})
>       assert counters.get("plan_validation_attempts", 0) == 0, (
            "a load-flaky test_file charged plan_validation_attempts: "
            f"{counters}")
E       AssertionError: a load-flaky test_file charged plan_validation_attempts: {'plan_validation_attempts': 1}
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f58720dc0c0>('plan_validation_attempts', 0)
E        +    where <built-in method get of dict object at 0x7f58720dc0c0> = {'plan_validation_attempts': 1}.get

tests/test_gate.py:866: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================

```
- ok: `tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt` fails on base `main` too -- the bug is not already fixed upstream
```
empts: {'plan_validation_attempts': 1}
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7fc41d194c80>('plan_validation_attempts', 0)
E        +    where <built-in method get of dict object at 0x7fc41d194c80> = {'plan_validation_attempts': 1}.get

tests/test_gate.py:866: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.63s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-39zj6nci/base
      Built pipeline @ file:///tmp/pipeline-base-39zj6nci/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 52ms

```

### 2026-09-03 · plan-validation · judgement

**Plan validated: PASS.** Every item below is scored against the source.

- Root cause: `gate()`'s exit-0 finding carries no allowlist mark, and
  `gate_result()` reads an unmarked finding as substantive, so a `test_file`
  that exits 0 on both trees returns `bad-plan` and charges
  `plan_validation_attempts` at `planning` -- a stage `CLAIMS` forbids from
  writing `test_file`. The plan fixes the classification, not the test.
- Decision conflict: none. DEC-065's 2-tuple constraint binds `gate()`, which
  step 7 leaves alone; `_base_findings()` is private, unpacked once outside
  `pipeline/core/gate.py` (`tests/test_gate.py:910`, inside a function body,
  so no collection error on base). DEC-090's byte-identical clause is
  superseded on one arm, with the `startswith` reason stated.
- Scope: every step traces to a criterion. 8 files, 3 of them source --
  DEC-087's shape.
- Falsifiable: `grep -c 'into four' CLAUDE.md` prints `1` today.
- No research left: I checked each anchor. `gate.py:192, 204, 371, 397, 564,
  567, 577, 633`, `supervisor.py:24-25, 1048-1065`, `machine.py:174-178`,
  `test_dispatch.py:1851-1867`, `test_machine.py:352-365`, `README.md:507-510`,
  `CLAUDE.md:318-331` all hold.
- Riskiest step: 9, splitting the `passing` arm at `:577`. `## Rollback` states
  the fallback: drop the two `load_flaky()` lines from `gate_result()`.
- Regression surface: the finding text (`tests/test_gate.py:282, 298, 843`),
  `_base_findings()`'s arity (`:910`), the new verdict
  (`tests/test_dispatch.py`), the new row (`tests/test_machine.py`). All under
  the full-suite criterion.

Three notes, none of which change a step:

1. `## Digest` gotcha 4 cites the wrong lines and swaps the two tests.
   `test_gate_fails_an_exit_zero_test_and_names_both_causes` is at
   `tests/test_gate.py:282`, not `:831`;
   `test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector` is at
   `:298`, not `:846`, and it is NOT the load-flaky path -- both call
   `gate(d, "TICKET-001")` with no workdir, so `_base_findings()` returns the
   "base check skipped" arm and both keep the byte-identical text. The
   load-flaky path is `test_gate_still_fails_when_the_worktree_and_base_both_pass`
   (`:843`), which asserts `"exited 0"` and `"PASSES"` -- both survive in
   step 10's f-string. The constraint gotcha 4 derives is correct.
2. Behaviour change to record at implementation: a `test_file` whose selector
   matches no test on either tree now escalates as `load-flaky` instead of
   charging `bad-plan`. The finding keeps "matched no test at all", and
   `test_file` is triage's field either way.
3. `charged_round()` in `pipeline/cli/metrics.py:396-407` asks `transition()`
   and names `no-test-file`/`environment` only as examples, so DEC-103 needs
   no edit, as `## Decisions checked` says.

Unverified, measured by reading only: I ran no command. The baseline
`1 failed, 80 passed` and every acceptance criterion's exit code rest on the
gate's own run, not on mine. I would have run
`uv run --group dev pytest -q tests/test_gate.py`.

### 2026-09-03 12:56:15Z · plan-validation · session · session=76ffe853-6624-4872-9f6a-9099c016ef6a

`plan-validation` ran as session `76ffe853-6624-4872-9f6a-9099c016ef6a`
- replay: `claude --resume 76ffe853-6624-4872-9f6a-9099c016ef6a`
- log: `.project/logs/TICKET-109-plan-validation-76ffe853.log`
- cost: $1.58 of a $3 cap
- tokens: 15,244 out (7,936 thinking) · 38 in · 1,054,451 cache read · 67,323 cache write

### 2026-09-03 12:56:15Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan validated: 8 items pass; every anchor line, classifier and test name checked against the source

### 2026-09-03 16:45:23Z · human · note · by=chezzijr

**note from chezzijr**

Plan gate reviewed by Claude on chezzijr's instruction (they are asleep). Checked: LOAD_FLAKY_MARKS is a fourth startswith allowlist (not a substring match, so a ticket cannot quote itself a free escalation); load_flaky() is checked beside missing_test_file() and both escalate charging nothing; ('plan-validation','load-flaky') is an ENUMERATED transition() row, and revalidating still gets 'fail' per DEC-029; the finding names base's own PASS and tells the human to re-run triage. NOTE FOR THE HUMAN: this diff edits transition() in pipeline/core/machine.py, which machine.FENCED covers, so it will park at awaiting-merge. Claude is deliberately NOT clearing that gate -- CLAUDE.md keeps the fenced merge for a human, and chezzijr reviews it. Approving the PLAN only.

### 2026-09-03 16:45:23Z · human · approval · by=claude-for-chezzijr

**approved by claude-for-chezzijr**

### 2026-09-03 16:57:27Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt` fails as required
```
t gate_result
        ok, failures = gate(d, "TICKET-001", workdir=wt)
        assert not ok
        assert any("exited 0" in f and "PASSES" in f for f in failures), failures
        result = gate_result(ok, failures, "plan-validation")
        nxt, counters = transition("plan-validation", result, {})
>       assert counters.get("plan_validation_attempts", 0) == 0, (
            "a load-flaky test_file charged plan_validation_attempts: "
            f"{counters}")
E       AssertionError: a load-flaky test_file charged plan_validation_attempts: {'plan_validation_attempts': 1}
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f594819fe40>('plan_validation_attempts', 0)
E        +    where <built-in method get of dict object at 0x7f594819fe40> = {'plan_validation_attempts': 1}.get

tests/test_gate.py:866: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.38s ===============================

```
- ok: `tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt` fails on base `main` too -- the bug is not already fixed upstream
```
empts: {'plan_validation_attempts': 1}
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f1527d65780>('plan_validation_attempts', 0)
E        +    where <built-in method get of dict object at 0x7f1527d65780> = {'plan_validation_attempts': 1}.get

tests/test_gate.py:866: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_load_flaky_test_does_not_charge_a_plan_validation_attempt
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.62s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-_row4av5/base
      Built pipeline @ file:///tmp/pipeline-base-_row4av5/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 27ms

```

### 2026-09-03 16:57:28Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-03 · implementing · todo

**Todo, one entry per plan step**

1. [x] `tests/test_dispatch.py` new test
2. [x] verify RED (ImportError)
3. [x] `LOAD_FLAKY_MARK`/`LOAD_FLAKY_MARKS` in `gate.py`
4. [x] `load_flaky()` in `gate.py`; verify still RED
5. [x] wire `load_flaky` into `gate_result()` in `supervisor.py`
6. [x] docstring update; verify GREEN
7. [x] `_base_findings()` returns 3-tuple with `zero_on_base`
8. [x] unpack 3-tuple at both call sites
9. [x] split `passing` loop's exit-0 arm
10. [x] load-flaky finding text (two fences)
11. [x] `tests/test_gate.py:910` unpack update
12. [x] full `tests/test_gate.py` run + commit
13. [x] `tests/test_machine.py` new test
14. [x] `transition()` row in `machine.py`; verify GREEN + commit
15. [x] `README.md` paragraph
16. [x] `CLAUDE.md` gotcha update + commit
17. [x] full suite + guard script

### 2026-09-04 · implementing · report

**Plan executed. All 17 steps landed, TDD-verified, three commits.**

- `d66b230` `fix(TICKET-109): report a test that exits 0 on base too as
  load-flaky` -- `LOAD_FLAKY_MARK`, `load_flaky()`, `gate_result()` wiring,
  `_base_findings()`'s third `zero_on_base` dict, the split `passing` arm and
  its two-fence finding.
- `07d715f` `fix(TICKET-109): escalate a load-flaky test_file through its own
  transition row`.
- `e1d5e2d` `docs(TICKET-109): document the load-flaky gate verdict`.
- `cd089fd` `test(TICKET-109): pin test_one to a genuine failure so two
  dispatch tests still exercise bad-plan`.

The fourth commit was not in `## Plan`. Running the full suite after step 14
(per acceptance criteria) found two regressions the plan did not anticipate:
`test_a_bound_escalation_emits_an_escalated_event` and
`test_a_failing_gate_child_sends_the_ticket_back_to_planning`
(`tests/test_dispatch.py`), both built on `git_project()`'s `test_one="true"`.
That command exits 0 unconditionally, so it now genuinely passes on both the
ticket's worktree AND base -- exactly `load_flaky()`'s definition -- and
`gate_result()` correctly reclassified it from `bad-plan` to `load-flaky`,
which escalates instead of charging `plan_validation_attempts`, breaking both
tests' assertions. `tests/test_dispatch.py` is already in `files_declared`, so
I pinned `test_one` to `"false"` (exits non-zero, prints nothing, so the node
name never appears in the output) in each test's own `pipeline.toml`,
preserving their original intent -- a genuine `bad-plan` verdict -- rather
than widen `## Plan` or the file list.

Verification: `uv run --group dev pytest -q` -- `536 passed`.
`./pipeline/hooks/test_dangerous_commands.py` -- `guard: all passed`, exit 0.
Every acceptance criterion re-checked individually; all pass, including the
`grep` checks in README.md and CLAUDE.md.

### 2026-09-03 17:06:00Z · implementing · session · session=13b55bfd-3932-4f6b-9c18-030de6fbdff6

`implementing` ran as session `13b55bfd-3932-4f6b-9c18-030de6fbdff6`
- replay: `claude --resume 13b55bfd-3932-4f6b-9c18-030de6fbdff6`
- log: `.project/logs/TICKET-109-implementing-13b55bfd.log`
- cost: $2.22 of a $8 cap
- tokens: 33,403 out (7,111 thinking) · 168 in · 7,266,238 cache read · 108,093 cache write

### 2026-09-03 17:06:00Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented the load-flaky gate verdict; full suite (536) and guard (138) pass

### 2026-09-04 · review · findings

**No blocking findings. Reviewed `git diff main...HEAD` -- 5 commits, 8 files.**

Verified against the acceptance criteria, fresh:
`uv run --group dev pytest -q` -- `536 passed in 55.28s`;
`./pipeline/hooks/test_dangerous_commands.py` -- `guard: all passed`, exit 0;
the five named tests together -- `5 passed in 0.28s`; every `grep` criterion,
including `grep -c 'into four' CLAUDE.md` printing `0`.

Checked and refuted, each with the file:line that refutes it:

1. The `passing` loop's two arms cannot both fire, and neither test loses a
   finding: `_base_findings()` fills `on_base` under `if hit:` and
   `zero_on_base` under `elif code == 0:` (`pipeline/core/gate.py:459-462`),
   so the dicts are disjoint and `zero_on_base` is a subset of what the old
   `test not in on_base` arm already caught.
2. `zero_on_base` discarded at the second call site (`:704`) is correct:
   that arm runs only when `passing` is empty, and load-flaky needs exit 0 in
   the worktree.
3. DEC-090 holds -- the `elif test not in on_base:` finding text is unchanged
   in the diff.
4. DEC-029 holds -- `if stage != "plan-validation": return "fail"`
   (`pipeline/daemon/supervisor.py:1063`) runs above the new branch.
5. `commit cd089fd` does not weaken the two dispatch tests: `test_one="false"`
   exits non-zero printing nothing, which is the "errored rather than failed"
   finding, still substantive, still `bad-plan`. `git_project()` writes
   `.project/pipeline.toml` after its only commit (`tests/helpers.py:57-60`),
   so `project_config()`'s disk fallback reads the override.

Non-blocking nits, recorded not fixed:

1. nit: the finding says `pipeline resume {t.id} triage`; `## Plan` step 10
   said `{tid}`, and the sibling `ENVIRONMENT: ` finding uses `{tid}`
   (`pipeline/core/gate.py:732`). Both are validated ids.
2. nit: `charged_round()`'s docstring lists the escalating verdicts as
   "(`no-test-file`, `environment`)" (`pipeline/cli/metrics.py:402`) and does
   not name `load-flaky`. The same docstring says this file needs no edit for
   a new verdict, and DEC-103 is satisfied.

### 2026-09-03 17:10:47Z · review · session · session=77696303-5f3b-44c9-b9bb-d2c111926228

`review` ran as session `77696303-5f3b-44c9-b9bb-d2c111926228`
- replay: `claude --resume 77696303-5f3b-44c9-b9bb-d2c111926228`
- log: `.project/logs/TICKET-109-review-77696303.log`
- cost: $2.20 of a $6 cap
- tokens: 19,625 out (12,266 thinking) · 64 in · 1,901,880 cache read · 75,352 cache write

### 2026-09-03 17:10:47Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed the 5-commit delta: no blocking findings; 536 passed, guard 138 passed

### 2026-09-03 17:11:46Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/core/machine.py:transition`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-109` lands it; `pipeline resume TICKET-109 --stage planning` sends it back.

### 2026-09-03 17:14:11Z · human · note · by=chezzijr

**note from chezzijr**

MERGE GATE REVIEW (Claude, not approving -- this diff is fenced and CLAUDE.md keeps it for a human).

Verified on ticket/109:
- uv run --group dev pytest -q in the worktree: 536 passed in 56.25s.
- Diff is 8 files, +163/-36, exactly the files_declared list.
- The FENCED part is one hunk in pipeline/core/machine.py: a new
  case ('plan-validation', 'load-flaky') that returns ('escalated', c).
  It charges no counter and retries no stage. Before this row the same pair
  already escalated through the unknown-pair fallback, so the row changes NO
  behaviour -- it makes the path findable. transition() stays pure and total;
  nothing else in machine.py moved (no CONTROL_FIELDS, no FENCED, no BOUNDS).
- gate.py adds LOAD_FLAKY_MARK as a fourth startswith allowlist (not a
  substring test, so a ticket cannot quote itself an escalation out of its own
  captured output) and threads a third dict out of _base_findings().
- supervisor.py adds one 'if load_flaky(failures): return "load-flaky"' beside
  missing_test_file(), and the docstring now says five verdicts.
- CLAUDE.md and README.md were updated in the same branch, so the prose and
  machine.FENCED cannot drift.

To land it:  pipeline approve TICKET-109
To send it back:  pipeline reject TICKET-109 "<why>"

Queue note: TICKET-112 declares pipeline/daemon/supervisor.py too, so while
this ticket sits at awaiting-merge it may hold 112's merge behind it.

### 2026-09-04 01:48:10Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-04 01:48:13Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/109


Current branch ticket/109 is up to date.
Already up to date.
Updating 973e2d8..cd089fd
Fast-forward
 CLAUDE.md                     | 20 +++++++-------
 README.md                     |  8 ++++++
 pipeline/core/gate.py         | 62 ++++++++++++++++++++++++++++++++++---------
 pipeline/core/machine.py      |  9 +++++++
 pipeline/daemon/supervisor.py | 28 ++++++++++++-------
 tests/test_dispatch.py        | 38 +++++++++++++++++++++++---
 tests/test_gate.py            | 22 ++++++++++++++-
 tests/test_machine.py         | 12 +++++++++
 8 files changed, 163 insertions(+), 36 deletions(-)

```

### 2026-09-04 01:48:13Z · merging · decision

decision recorded as `DEC-109`
