---
id: TICKET-090
stage: done
class: bugfix
branch: ticket/090
test_file: tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes
files_declared:
- CLAUDE.md
- pipeline/core/gate.py
- tests/test_gate.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 15
  plan_files: 3
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: da7eaff7-4b3b-4a81-b655-d62c0fa04be9
  log: .project/logs/TICKET-090-review-da7eaff7.log
  cost_usd: 1.57668
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified: gate.py:648 filters findings starting with
  ''ok:'' out of the failure list, so step 10''s ok-prefixed finding really clears
  the gate. The credit is guarded three ways: step 2 pins that a test passing in BOTH
  places still fails; _base_verdict''s node-not-in-output arm keeps a test that errors
  on base out of on_base, so a selector matching nothing is never credited; and expect:
  is matched against base''s output, the only failing output such a test has. Step
  11 avoids paying for a second base checkout. Nothing fenced.'
approved_at: '2026-08-29T06:03:24.214954+00:00'
---

## Summary

Tier A cannot pass once the branch already fixes the repro -- fixed.

`implementing` executed the 15-step plan: result `ok`, committed `e8bed14`
`fix(TICKET-090): an exit-0 repro run falls through to the base check`.

The bug: Tier A required the recorded test to FAIL in the worktree. Once
`implementing` lands the fix the test passes, `gate()` reported the exit-0
finding, and a ticket resumed to `plan-validation` was unsatisfiable.

The fix: in `pipeline/core/gate.py` an exit-0 `test_one` run in the worktree is
bucketed into `passing`. `_base_findings()` runs before `expect:` is judged and
returns findings plus the base output of every test that FAILS on base;
`_base_verdict()` returns `(bool, str)` to feed it. Failing on base is the PASS;
failing nowhere keeps DEC-071's exit-0 finding, byte-identical (verified
`grep -c "exited 0 -- it must fail before implementation" pipeline/core/gate.py`
= 1, `grep -c "selector matched nothing" pipeline/core/gate.py` = 0). `expect:`
is matched against base's output for a test that passes here.

Verified: both TICKET-090 tests pass; the 6 named pre-existing acceptance
tests still pass; `tests/test_gate.py tests/test_dispatch.py tests/test_cli.py
tests/test_config.py` -> `207 passed`, no state change from the step-1
baseline; `tests/test_stages.py` -> `30 passed`. CLAUDE.md gotcha added,
`grep -c "falls through to the base run" CLAUDE.md` = 1.

Files touched: `pipeline/core/gate.py`, `tests/test_gate.py`, `CLAUDE.md`.

`review` returned `ok` on the first pass: no blocking findings. It re-ran all
11 acceptance criteria, got `uv run --group dev pytest -q` -> `471 passed`, and
refuted its own two candidate findings (a credited no-match selector, a
shadowed `base` name). Two low notes stand and are already accepted in
`## Decisions`: a base output that can be fenced twice before `_dedupe()`
folds it, and the `passing` loop's missing `ESCAPE_RE` arm.

## Reproduction

test: tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes
command: uv run --group dev pytest -q tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes
expect: exited 0 -- it must fail before implementation

The test builds a real git project (`_git_ticket_project`) where base is buggy
and the ticket branch already carries the fix, simulating a worktree resumed
to `plan-validation` after `implementing` landed. `gate()` fails at the
exit-0 branch check in `pipeline/core/gate.py` (around line 394-404) before
`_base_findings()` ever runs, so the fact that base still fails -- the
durable proof the branch already fixed it -- is never consulted. Confirmed
`git log --oneline -S "_base_findings" -- pipeline/core/gate.py`: no prior
commit addressed this ordering.

`planning` trimmed `expect:` on 2026-08-29. Triage had recorded the whole
`AssertionError`, which ends in an entry reference `gate()` mints per run:
`2026-08-29 04:06:11Z · plan-validation · gate · verdict=FAIL`. The command
printed a different time on every run -- `04:06:11Z` at triage, `05:19:24Z`
at the gate, `05:20:41Z` here -- so the old `expect:` matched no run at all,
including the one it was copied from. DEC-068 and DEC-076 both require the
invariant part of the failure instead. The trimmed string still discriminates:
only the exit-0 finding this ticket is about produces it.

## Digest

- Files touched: `pipeline/core/gate.py` (the fix), `tests/test_gate.py` (the recorded repro plus one new negative test), `CLAUDE.md` (one gotcha line).
- Key functions: `gate()` at `pipeline/core/gate.py:328`; its per-test loop at lines 390-404; the `matched` line at 418; the `if matched and reproduced:` base call at 450. `_base_findings()` at line 262 and `_base_verdict()` at line 239.
- Entry points: `cmd_gate()` (`pipeline/cli/main.py:103`) and `gate_cmd()` (`pipeline/daemon/supervisor.py:534`). Both pass the ticket worktree as `workdir`, so `_base_findings()` runs for every dispatcher gate.
- Gotcha: `gate()` returns its failures through `_dedupe(f, mine, here)` at `pipeline/core/gate.py:656`, and `here` is the timestamp of the entry it just appended. A repro test that asserts on `gate()`'s returned failures therefore fails with a per-run string, which is what made this ticket's first `expect:` unmatchable. `unmatchable()` (line 140) has no rule for that shape; adding one is out of scope, recorded in `## Decisions`.
- Gotcha: `ok:`-prefixed findings are excluded from the verdict at `pipeline/core/gate.py:648`. The "already fixed" finding must carry that prefix.
- Gotcha: three tests call `gate()` with no worktree, so `_base_findings()` takes its `wd.resolve() == project.resolve()` skip and reports no base failure. The exit-0 finding must survive there. They are `test_gate_blocks_a_test_that_already_passes` (`tests/test_gate.py:175`), `test_gate_fails_an_exit_zero_test_and_names_both_causes` (182) and `test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector` (198). The second asserts exactly one RETURNED failure contains `exited 0`; the base-skip finding starts `ok:` and is never returned, so it cannot disturb that.
- Gotcha: `expect:` is matched only against `reproduced` outputs today (line 418). A test that passes in the worktree emits no failure, so `expect:` must be matched against the BASE output or the check silently stops applying to that test.
- Gotcha: `tests/test_gate.py` is copied onto a checkout of base and imported there (DEC-017, DEC-018, DEC-030, DEC-066). It may gain no module-level import of a name base lacks. `_base_findings` is already imported at its line 11 and stays importable; only its return shape changes, and no test body other than the ticket's own runs on base.
- Gotcha: a `test_one` whose selector matches nothing exits 0 on base too, so it is absent from the failing-on-base map and still FAILs. The fall-through credits only a test that FAILS on base.
- Baseline measured 2026-08-29 in this worktree: `uv run --group dev pytest -q tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` prints `1 failed`, and its output contains the string `exited 0 -- it must fail before implementation` once.

## Decisions checked

Grepped `/home/chezzijr/proj/agent-pipeline/.project/decisions/` for `base`, `_base_findings`, `on base`, `exited 0`, `exit 0`, `repro`, `expect:`, `unmatchable`, `cannot recur`, `dedupe`.

- DEC-068 (active) -- "an `expect:` line must survive a second run ... record the invariant part of the failure ... not the run". This plan complies by trimming `expect:`, and it is the record that authorises the change made to `## Reproduction`.
- DEC-076 (active) -- the same rule in code: `unmatchable()` refuses only tokens that cannot recur by construction, and a test keeps its proof by trimming `expect:` to the invariant prefix. This plan adds no rule to `unmatchable()`, see `## Decisions`.
- DEC-017 (active) -- the base run is the load-bearing half of the reproduction, and its "known cost" note bounds a base checkout to a branch test that already passed its checks. This plan widens that cost, see `## Decisions`; it does not drop the base run. Its `node not in out` second line of defence on the base run stays.
- DEC-071 (active) -- exit 0 is one finding with two causes. The finding must contain `PASSES` and must not contain `selector matched nothing`, and it stays out of `STRUCTURAL_MARKS`. This plan keeps that string byte-identical and only moves where it is emitted.
- DEC-066 (active) -- `test_one` runs once per test, `_base_findings()` covers a list of tests in one checkout, and `expect:` must appear in at least one failing test's output rather than in every one. This plan keeps all three.
- DEC-065 (active) -- `structural_only()` is a `startswith` allowlist over FAILING findings. This plan adds one new failing finding, an `expect:` variant, which is substantive, so `STRUCTURAL_MARKS` is unchanged.
- DEC-018 (active) -- `tests/test_gate.py` may gain no new `from helpers import` name. The new test uses only `_git_ticket_project`, `gate` and `shutil`, all already imported there.
- DEC-030 (active) -- `tests/test_gate.py` asserts on literal substrings, never on a constant imported from `pipeline.core.gate`. The new test asserts on `"exited 0"` and `"PASSES"`.
- DEC-026 (active) -- records that the cheap route runs no Tier A gate and therefore no base check. Unchanged here.

## Plan

1. Run `uv run --group dev pytest -q tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` and confirm `tests/test_gate.py` reports `1 failed` with the finding `` `test_thing.py::test_broken` exited 0 -- it must fail before implementation ``.
2. Add `test_gate_still_fails_when_the_worktree_and_base_both_pass` to `tests/test_gate.py` directly after `test_gate_falls_through_to_base_when_the_worktree_test_already_passes` (after its line 681). Body: `d, wt = _git_ticket_project("fixed\n", "fixed\n")`, then `ok, failures = gate(d, "TICKET-001", workdir=wt)`, then `assert not ok, failures`, then `assert any("exited 0" in f and "PASSES" in f for f in failures), failures`, then `shutil.rmtree(d, ignore_errors=True)`. Docstring: the fall-through credits only a test that FAILS on base, so a branch whose test passes where base's passes too is still not a reproduction.
3. Run `uv run --group dev pytest -q tests/test_gate.py::test_gate_still_fails_when_the_worktree_and_base_both_pass` and confirm `1 passed` against the unchanged `pipeline/core/gate.py` -- it is a regression guard, not a second repro.
4. In `pipeline/core/gate.py` change `_base_verdict()` (line 239) to return `tuple[bool, str]`, where the bool means "this test FAILS on base": the `code == 0` arm returns `(False, <its existing text>)`, the `node not in out` arm returns `(False, <its existing text>)`, and the final arm returns `(True, <its existing "ok: ... fails on base ... too" text>)`. Keep all three strings byte-identical and add one docstring line naming the bool.
5. In `pipeline/core/gate.py` change `_base_findings()` (line 262) to return `tuple[list[str], dict[str, str]]`: the findings list exactly as today, plus a dict mapping each test that fails on base to that base run's output. Its three early returns (lines 272, 279, 286) return their existing one-element list and `{}`. In the final loop write `hit, verdict = _base_verdict(test, test.split("::")[-1], base, code, out)`, append `verdict` to the verdict list, and set the dict entry for `test` to `out` when `hit` is true. Add to the docstring: membership of the dict is the durable proof the bug is upstream, and the output is what `expect:` is matched against for a test that already passes in the worktree.
6. In `tests/test_gate.py` update `test_the_base_run_covers_every_listed_test` (its line 714) to unpack the new shape as `out, on_base = _base_findings(d, project_config(d), wt, [...])`, keep its two existing `ok: ... fails on base` assertions over `out`, and add `assert set(on_base) == {"test_thing.py::test_broken", "test_thing2.py::test_broken2"}, on_base`. Run `uv run --group dev pytest -q tests/test_gate.py::test_the_base_run_covers_every_listed_test` and confirm `1 passed`.
7. In `pipeline/core/gate.py` rewrite the per-test loop at lines 390-404 so an exit-0 run is bucketed instead of reported: declare `passing: list[tuple[str, str]] = []` next to `reproduced`, commented "exit 0 in the worktree carries no evidence of its own; the base run below decides it"; change the `if code == 0:` arm to `passing.append((test, out))` and delete the finding it appends; leave the `node not in out` arm and the `else` arm untouched.
8. In `pipeline/core/gate.py` insert, immediately after that loop and before the `matched` line (currently 418), the base-first block: `base: list[str] = []`, `on_base: dict[str, str] = {}`, `candidates = [x for x, _ in reproduced + passing]`, then `if passing: base, on_base = _base_findings(project, cfg, wd, candidates)`. Comment it: base does not carry the branch's fix, so its verdict does not depend on the branch's current state; a ticket resumed to `plan-validation` after `implementing` landed the fix has a worktree where `test_file` now PASSES, and the run must reach base before `expect:` is judged, because base's output is the only failing output such a test has (TICKET-090).
9. In `pipeline/core/gate.py` widen the `matched` expression (line 418) to `matched = (not expect or any(expect in o for _, o in reproduced) or any(expect in on_base.get(t, "") for t, _ in passing))`, and extend its existing comment with one sentence: for a test that already passes here, the failing output `expect:` is checked against is base's.
10. In `pipeline/core/gate.py` add the `passing` reporting loop directly after that `matched` expression and before the `for test, out in reproduced:` loop, as `for test, out in passing:` with three arms: (a) `if test not in on_base:` append the exit-0 finding moved out of step 7, byte-identical, with the worktree `out[-1200:]` fence and its TICKET-071 comment; (b) `elif matched or bad:` append an `ok:`-prefixed finding reading "`<test>` exited 0 here and fails on base `<base_ref(cfg)>` -- the branch already carries the fix, and base is where the reproduction still holds", with no fence, because the base verdict from step 5 already quotes that output; (c) `else:` append "`<test>` exited 0 here and fails on base `<base_ref(cfg)>`, but base's output does not mention the expected string `<repr of expect>`" followed by a fence of `on_base[test][-1200:]`.
11. In `pipeline/core/gate.py` replace the `if matched and reproduced:` call at line 450 with `if not passing and matched and reproduced: base, _ = _base_findings(project, cfg, wd, candidates)` and then `findings += base` unconditionally, commented: a non-empty `passing` already paid for the one checkout in step 8, so this arm covers only the ordinary case where every listed test failed in the worktree.
12. Run `uv run --group dev pytest -q tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes tests/test_gate.py::test_gate_still_fails_when_the_worktree_and_base_both_pass` and confirm `2 passed` for those two tests in `tests/test_gate.py`.
13. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py tests/test_cli.py tests/test_config.py` and confirm no failures; if any test other than the two named in step 12 changed state against step 1's baseline, fix `pipeline/core/gate.py` rather than the test.
14. Add one gotcha bullet to `CLAUDE.md`, in the "Gotchas, each found the hard way" list, directly after the bullet beginning "**A test that *errors* exits non-zero exactly like one that fails.**" (that bullet ends at `CLAUDE.md` line 122): "**An exit-0 repro run in the worktree falls through to the base run.** A ticket resumed to `plan-validation` after `implementing` landed the fix has a worktree where `test_file` passes, and failing on that made Tier A permanently unsatisfiable. `gate()` reports the exit-0 finding only when the test does not also FAIL on base; failing on base is the durable proof the branch already carries the fix (TICKET-090)."
15. Run `uv run --group dev pytest -q tests/test_stages.py`, confirm no failures, then commit `pipeline/core/gate.py`, `tests/test_gate.py` and `CLAUDE.md` with the message `fix(TICKET-090): an exit-0 repro run falls through to the base check`.

## Acceptance criteria

- `tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` passes: a branch that already carries the fix gates PASS, because base still fails.
- `tests/test_gate.py::test_gate_still_fails_when_the_worktree_and_base_both_pass` passes: a test passing in the worktree AND on base still gates FAIL, with a finding naming `PASSES`.
- `tests/test_gate.py::test_gate_blocks_a_test_that_already_passes` still passes: with no worktree the base check is skipped and the exit-0 finding survives.
- `tests/test_gate.py::test_gate_fails_an_exit_zero_test_and_names_both_causes` still passes: one returned failure, and only one, contains `exited 0`.
- `tests/test_gate.py::test_gate_names_both_causes_when_the_test_exits_zero_on_base` still passes: `_base_verdict()`'s three strings stay byte-identical.
- `tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` and `tests/test_gate.py::test_gate_passes_a_test_that_fails_on_base_too` still pass: the ordinary reproduction path is unchanged.
- `tests/test_gate.py::test_the_base_run_covers_every_listed_test` passes against the new two-value return of `_base_findings()`.
- `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py tests/test_cli.py tests/test_config.py` reports no failures, and no test other than this ticket's two changes state against the baseline measured in step 1.
- `grep -c "falls through to the base run" CLAUDE.md` prints `1`.
- `grep -c "selector matched nothing" pipeline/core/gate.py` prints `0`, so DEC-071's banned phrase stays out.
- `grep -c "exited 0 -- it must fail before implementation" pipeline/core/gate.py` prints `1`, so the string `## Reproduction` now records as `expect:` still names a live finding after step 10 moves it.

## Decisions

**An exit-0 `test_one` run in the ticket's worktree is not a gate failure on its own; the base run decides it.** A ticket resumed to `plan-validation` after `implementing` landed the fix has a worktree where `test_file` PASSES, and reporting that outright made Tier A permanently unsatisfiable -- the only way forward was skipping the gate by hand. The proof that the repro is real does not depend on the branch's current state: base does not carry the fix, and `_base_findings()` already re-runs the branch's test file against a checkout of base. Failing on base is therefore a PASS carrying that sentence. Failing nowhere stays a FAIL, with DEC-071's finding text byte-identical. Do not restore the unconditional finding.

**No new frontmatter field records this.** A `repro-verified-at` marker would be a control field an agent could forge, which invariant 1 forbids. The state is re-derived from the two test runs on every gate.

**The base run happens BEFORE `expect:` is judged whenever a listed test exited 0.** Such a test emits no failing output, so base's output is the only one that can carry the expected string; `matched` therefore ORs over the `reproduced` outputs and the base outputs of the passing tests. Without this ordering the `expect:` check silently stops applying to an already-fixed test, which is the quiet hole it exists to close.

**DEC-017's "known cost" bound is widened, deliberately.** That record bounds a base checkout to a branch test that already passed its checks -- "a failing branch test never pays for a base checkout". An exit-0 branch test now pays for one too. That is the price of the fall-through, and it is bounded the same way: one checkout for all listed tests, and only when at least one of them exited 0.

**A selector that matches no test is still caught.** The branch's test file is copied onto base, so a selector matching nothing there matches nothing on base either: base exits 0, the test is absent from the failing-on-base map, and DEC-071's finding stands. The fall-through credits only a test that FAILS on base, never one that merely exits non-zero -- `_base_verdict()`'s `node not in out` guard (DEC-017) is what keeps an import error out of the map.

**The `passing` loop does not replicate the reproduced loop's `ESCAPE_RE` arm.** That arm turns an `expect:` holding a literal backslash escape into a structural finding rather than a substantive one. A second copy of the rule was judged not worth it on this rarer path: a passing test whose base output misses `expect:` gets the plain substantive finding instead. Fold the two loops if that path ever fires in practice.

**A repro test that asserts on `gate()`'s returned failures cannot copy that assertion into `expect:`.** `gate()` returns `_dedupe(f, mine, here)` (`pipeline/core/gate.py:656`) and `here` is the timestamp of the thread entry it just appended, so the assertion text carries a wall-clock time that changes every run. This ticket's own `expect:` was recorded that way and matched no run, including the one it was copied from -- `plan-validation` failed Tier A on it once. `unmatchable()` gained no rule for that shape here: that is a `gate()` behaviour change with its own tests, and it belongs to a ticket of its own. Until then, trim `expect:` to the finding text, as DEC-068 and DEC-076 already require.

**Out of scope, recorded:** `unwinding` exists so `planning` is not handed a branch where `test_file` already passes (`pipeline/core/machine.py:223`). This fix makes the gate survive such a tree, but it does not make `unwinding` redundant -- the plan itself would still be written against an already-fixed tree. Removing that stage is a separate ticket.

## Rollback

Revert the commit from step 15 (`fix(TICKET-090): an exit-0 repro run falls through to the base check`) with `git revert <sha>`. It touches `pipeline/core/gate.py`, `tests/test_gate.py` and `CLAUDE.md` only, and nothing outside `gate()`, `_base_findings()` and `_base_verdict()` reads those two return shapes. Tier A then returns to reporting every exit-0 worktree run as a failure, and a ticket resumed to `plan-validation` after `implementing` is again unsatisfiable without a hand bypass. The trimmed `expect:` in `## Reproduction` is not part of that commit and must stay trimmed either way.

## Thread

### 2026-08-29 03:52:45Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 · triage · result=ok

Reproduced. `tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes`
builds a real git project where base is buggy and the ticket branch already
carries the fix. `gate()` fails at the worktree exit-0 branch in
`pipeline/core/gate.py` (around line 394-404) before `_base_findings()` ever
runs, so base's still-failing test -- the durable proof -- is never
consulted.

    AssertionError: ['`test_thing.py::test_broken` exited 0 -- it must fail
    before implementation. Either it PASSES, or `test_one` matched...al
    output, already quoted in the `## Thread` entry `2026-08-29 04:06:11Z ·
    plan-validation · gate · verdict=FAIL` --*']

`git log --oneline -S "_base_findings" -- pipeline/core/gate.py` shows two
commits (98a0675, bcbcaa8), neither addresses this ordering.

Fix belongs in `pipeline/core/gate.py`'s exit-0 branch of the per-test loop
(~line 394): fall through to `_base_findings()` instead of appending the
exit-0 finding outright, and treat "fails on base" as a PASS carrying that
sentence.

result: ok
test_file: tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes

### 2026-08-29 04:06:49Z · triage · session · session=c008473d-029a-4b95-8c03-094f03153369

`triage` ran as session `c008473d-029a-4b95-8c03-094f03153369`
- replay: `claude --resume c008473d-029a-4b95-8c03-094f03153369`
- log: `.project/logs/TICKET-090-triage-c008473d.log`
- cost: $0.48 of a $3 cap
- tokens: 5,875 out (979 thinking) · 48 in · 1,153,625 cache read · 47,444 cache write

### 2026-08-29 04:06:49Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: gate() cannot pass a worktree whose test_file already passes, even when base still fails, because the exit-0 branch findings block before the base check runs.

### 2026-08-29 · planning · result=ok

Plan written. The fix is one ordering change in `pipeline/core/gate.py`: an
exit-0 `test_one` run in the worktree is bucketed into `passing` instead of
reported, `_base_findings()` runs before `expect:` is judged, and the exit-0
finding is emitted only when the test does not also FAIL on base.

`_base_findings()` returns `list[str]` today, which cannot say WHICH test
failed on base. It becomes `tuple[list[str], dict[str, str]]` -- findings plus
the base output of each test that failed there. The dict does double duty:
membership is the "already fixed" proof, and the output is what `expect:` is
matched against for a test that passes in the worktree. `_base_verdict()`
returns `(bool, str)` to feed it.

Three existing tests call `gate()` with no worktree, so the base check is
skipped and the exit-0 finding still fires -- `test_gate_blocks_a_test_that_already_passes`,
`test_gate_fails_an_exit_zero_test_and_names_both_causes`,
`test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector`. DEC-071's
finding text is kept byte-identical.

Noted, out of scope: `unwinding` (`pipeline/core/machine.py:223`) exists for
the same tree, and this fix does not make it redundant -- the plan would still
be written against an already-fixed tree.

Baseline: `uv run --group dev pytest -q tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes`
prints `1 failed`.

result: ok
files_declared: pipeline/core/gate.py, tests/test_gate.py, CLAUDE.md

### 2026-08-29 04:15:31Z · planning · session · session=2186b7d0-ba6b-4ebf-b784-9318db9bcd3f

`planning` ran as session `2186b7d0-ba6b-4ebf-b784-9318db9bcd3f`
- replay: `claude --resume 2186b7d0-ba6b-4ebf-b784-9318db9bcd3f`
- log: `.project/logs/TICKET-090-planning-2186b7d0.log`
- cost: $3.45 of a $10 cap
- tokens: 42,681 out (21,370 thinking) · 66 in · 2,519,963 cache read · 111,742 cache write

### 2026-08-29 04:15:31Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: an exit-0 worktree run falls through to _base_findings(), which now returns the tests that FAIL on base; failing on base is the PASS.

### 2026-08-29 05:20:01Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` fails, but its output does not mention the expected string "AssertionError: ['`test_thing.py::test_broken` exited 0 -- it must fail before implementation. Either it PASSES, or `test_one` matched...al output, already quoted in the `## Thread` entry `2026-08-29 04:06:11Z · plan-validation · gate · verdict=FAIL` --*']"
```
ation` after `implementing`
        has already landed the fix has a worktree where `test_file` now PASSES.
        Today that reads as an unresolvable exit-0 ambiguity and the gate can
        never pass again. It must instead fall through to the base check: base
        still has the bug, which is the durable proof the branch already fixed
        it, and the gate must PASS on that."""
        d, wt = _git_ticket_project("buggy\n", "fixed\n")
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert ok, failures
E       AssertionError: ['`test_thing.py::test_broken` exited 0 -- it must fail before implementation. Either it PASSES, or `test_one` matched...al output, already quoted in the `## Thread` entry `2026-08-29 05:19:24Z · plan-validation · gate · verdict=FAIL` --*']
E       assert False

tests/test_gate.py:680: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```

### 2026-08-29 05:20:01Z · plan-validation · transition · to=planning · result=bad-plan

**plan-validation -> planning** (result: `bad-plan`)

Tier A gate failed:
- `tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` fails, but its output does not mention the expected string "AssertionError: ['`test_thing.py::test_broken` exited 0 -- it must fail before implementation. Either it PASSES, or `test_one` matched...al output, already quoted in the `## Thread` entry `2026-08-29 04:06:11Z · plan-validation · gate · verdict=FAIL` --*']"
*-- identical output, already quoted in the `## Thread` entry `2026-08-29 05:20:01Z · plan-validation · gate · verdict=FAIL` --*

### 2026-08-29 · planning · result=ok

Tier A failed the last plan over `## Reproduction`, not over the plan. The
recorded `expect:` ended in an entry reference `gate()` mints per run:
`2026-08-29 04:06:11Z · plan-validation · gate · verdict=FAIL`. The same
command printed `05:19:24Z` at the gate and `05:20:41Z` here, so that
`expect:` matched no run at all, including the one triage copied it from.
`gate()` returns its failures through `_dedupe(f, mine, here)`
(`pipeline/core/gate.py:656`), and `here` is the timestamp of the entry it
just appended -- that is where the per-run string comes from.

I trimmed `expect:` to `exited 0 -- it must fail before implementation`.
DEC-068 and DEC-076 both require the invariant part of the failure rather
than the run. Verified in this worktree: the recorded command prints
`1 failed` and its output contains that string once. This is the one edit
outside planning's own sections; the plan is otherwise unchanged in substance.

Added since the last plan: two acceptance criteria, one `## Digest` gotcha
naming `_dedupe()`, and one `## Decisions` paragraph on the trap.

Noted, out of scope: `unmatchable()` has no rule for that timestamp shape.
Adding one changes `gate()` and needs its own tests, so it is a separate
ticket.

result: ok
files_declared: pipeline/core/gate.py, tests/test_gate.py, CLAUDE.md

### 2026-08-29 05:29:37Z · planning · session · session=4cfaac68-4790-4af0-ac1c-9e2d59d9901e

`planning` ran as session `4cfaac68-4790-4af0-ac1c-9e2d59d9901e`
- replay: `claude --resume 4cfaac68-4790-4af0-ac1c-9e2d59d9901e`
- log: `.project/logs/TICKET-090-planning-4cfaac68.log`
- cost: $4.54 of a $10 cap
- tokens: 44,705 out (21,953 thinking) · 98 in · 4,440,581 cache read · 120,510 cache write

### 2026-08-29 05:29:37Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan rewritten; Tier A had failed on an expect string holding a per-run timestamp, now trimmed to the invariant finding text

### 2026-08-29 05:30:10Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` fails as required
```
ation` after `implementing`
        has already landed the fix has a worktree where `test_file` now PASSES.
        Today that reads as an unresolvable exit-0 ambiguity and the gate can
        never pass again. It must instead fall through to the base check: base
        still has the bug, which is the durable proof the branch already fixed
        it, and the gate must PASS on that."""
        d, wt = _git_ticket_project("buggy\n", "fixed\n")
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert ok, failures
E       AssertionError: ['`test_thing.py::test_broken` exited 0 -- it must fail before implementation. Either it PASSES, or `test_one` matched...al output, already quoted in the `## Thread` entry `2026-08-29 05:29:37Z · plan-validation · gate · verdict=FAIL` --*']
E       assert False

tests/test_gate.py:680: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` fails on base `main` too -- the bug is not already fixed upstream
```
ssertionError: ['`test_thing.py::test_broken` exited 0 -- it must fail before implementation. Either it PASSES, or `test_one` matched...al output, already quoted in the `## Thread` entry `2026-08-29 05:29:39Z · plan-validation · gate · verdict=FAIL` --*']
E       assert False

tests/test_gate.py:680: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-02ydxnw2/base
      Built pipeline @ file:///tmp/pipeline-base-02ydxnw2/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 · plan-validation · result=ok

Plan validated. Every item passes; findings below.

- Root cause: `gate()` appends the exit-0 finding inside the per-test loop
  (`pipeline/core/gate.py:394-404`), before `_base_findings()` at line 451 runs.
  A worktree carrying the fix therefore fails on the branch's current state,
  which base cannot rebut. The plan moves the verdict after the base run and
  credits only a test that FAILS on base. That fixes why, not the test.
- Decisions: DEC-071 is narrowed, not merely quoted. It says of the two exit-0
  causes "nothing is let through". This plan lets one through -- a test failing
  on base -- and supersedes it explicitly in `## Decisions`, justified by Tier A
  being otherwise unsatisfiable. Safe: `_base_verdict()` returns False on both
  its `code == 0` and `node not in out` arms (`pipeline/core/gate.py:242,252`),
  so a selector matching nothing and an import error stay FAILs. DEC-017's
  "known cost" bound is widened and the plan says so.
- Scope: 15 steps, 3 files, `bugfix`. Every step maps to a criterion; steps
  1, 3, 6, 12, 13 and 15 are verification runs.
- Criteria: falsifiable. Step 2's negative test builds a project whose test
  passes in the worktree AND on base, so it fails against an unconditional
  fall-through, which is the vacuous implementation. `grep -c "falls through to
  the base run" CLAUDE.md` prints 0 today.
- Research: every step names a file, a function and a line. Checked: only two
  callers of `_base_findings()` exist (`pipeline/core/gate.py:451` and
  `tests/test_gate.py:722`), and steps 11 and 6 cover both.
- Riskiest step: step 10, the three-arm `passing` loop, because it moves
  DEC-071's finding and adds two more. Fallback stated: step 13 fixes
  `pipeline/core/gate.py`, never the test, on any state change; `## Rollback`
  reverts one commit.
- Regression surface: the three no-worktree tests (`tests/test_gate.py:175`,
  182 and 198) take `_base_findings()`'s `wd.resolve() == project.resolve()`
  skip, whose finding starts `ok:` and is dropped at
  `pipeline/core/gate.py:648`, so the exit-0 finding still returns.
  `test_the_base_run_covers_every_listed_test` covers the new return shape.

long: nine scored items, each needing its own evidence line.

Unverified: I did not run the suite. A read-only stage's allowlist blocks it.
I would have run `uv run --group dev pytest -q tests/test_gate.py`. The
baseline and the post-fix behaviour rest on reading `pipeline/core/gate.py`
and on the Tier A PASS recorded at `2026-08-29 05:30:10Z`.

### 2026-08-29 05:33:33Z · plan-validation · session · session=f128793f-1c44-4897-b60f-dc6ccef91a44

`plan-validation` ran as session `f128793f-1c44-4897-b60f-dc6ccef91a44`
- replay: `claude --resume f128793f-1c44-4897-b60f-dc6ccef91a44`
- log: `.project/logs/TICKET-090-plan-validation-f128793f.log`
- cost: $1.55 of a $3 cap
- tokens: 15,191 out (6,675 thinking) · 44 in · 1,076,622 cache read · 62,973 cache write

### 2026-08-29 05:33:34Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan validated: root cause named, 15 steps all traceable, DEC-071 narrowing explicitly superseded, negative test blocks the vacuous fix

### 2026-08-29 06:03:24Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: gate.py:648 filters findings starting with 'ok:' out of the failure list, so step 10's ok-prefixed finding really clears the gate. The credit is guarded three ways: step 2 pins that a test passing in BOTH places still fails; _base_verdict's node-not-in-output arm keeps a test that errors on base out of on_base, so a selector matching nothing is never credited; and expect: is matched against base's output, the only failing output such a test has. Step 11 avoids paying for a second base checkout. Nothing fenced.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: gate.py:648 filters findings starting with 'ok:' out of the failure list, so step 10's ok-prefixed finding really clears the gate. The credit is guarded three ways: step 2 pins that a test passing in BOTH places still fails; _base_verdict's node-not-in-output arm keeps a test that errors on base out of on_base, so a selector matching nothing is never credited; and expect: is matched against base's output, the only failing output such a test has. Step 11 avoids paying for a second base checkout. Nothing fenced.**

### 2026-08-29 06:06:20Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` fails as required
```
ation` after `implementing`
        has already landed the fix has a worktree where `test_file` now PASSES.
        Today that reads as an unresolvable exit-0 ambiguity and the gate can
        never pass again. It must instead fall through to the base check: base
        still has the bug, which is the durable proof the branch already fixed
        it, and the gate must PASS on that."""
        d, wt = _git_ticket_project("buggy\n", "fixed\n")
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert ok, failures
E       AssertionError: ['`test_thing.py::test_broken` exited 0 -- it must fail before implementation. Either it PASSES, or `test_one` matched...al output, already quoted in the `## Thread` entry `2026-08-29 06:05:43Z · plan-validation · gate · verdict=FAIL` --*']
E       assert False

tests/test_gate.py:681: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.24s ===============================

```
- ok: `tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` fails on base `main` too -- the bug is not already fixed upstream
```
ssertionError: ['`test_thing.py::test_broken` exited 0 -- it must fail before implementation. Either it PASSES, or `test_one` matched...al output, already quoted in the `## Thread` entry `2026-08-29 06:05:44Z · plan-validation · gate · verdict=FAIL` --*']
E       assert False

tests/test_gate.py:681: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.36s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-rdlwiita/base
      Built pipeline @ file:///tmp/pipeline-base-rdlwiita/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 21ms

```

### 2026-08-29 06:06:20Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-29 · implementing · todo

1. [x] Confirm baseline: repro test fails, `1 failed`, finding names `exited 0 -- it must fail before implementation`.
2. [x] Add `test_gate_still_fails_when_the_worktree_and_base_both_pass` after the repro test.
3. [x] Confirm new negative test passes against unchanged `gate.py`.
4. [x] `_base_verdict()` returns `tuple[bool, str]`; all three strings byte-identical.
5. [x] `_base_findings()` returns `tuple[list[str], dict[str, str]]`.
6. [x] Update `test_the_base_run_covers_every_listed_test` for the new shape.
7. [x] Per-test loop buckets exit-0 into `passing` instead of reporting inline.
8. [x] Insert base-first block before `matched` is computed.
9. [x] Widen `matched` to OR over base outputs of `passing` tests.
10. [x] Add the three-arm `passing` reporting loop.
11. [x] Guard the ordinary base call with `not passing`; `findings += base` unconditionally.
12. [x] Confirm both TICKET-090 tests pass: `2 passed`.
13. [x] Confirm `tests/test_gate.py tests/test_dispatch.py tests/test_cli.py tests/test_config.py`: `207 passed`, no other state change from baseline.
14. [x] Add the CLAUDE.md gotcha bullet after the exit-code-errors bullet.
15. [x] Confirm `tests/test_stages.py`: `30 passed`; commit `e8bed14`.

### 2026-08-29 · implementing · result=ok

**Implemented all 15 plan steps.**

- Step 1 baseline: `1 failed`, finding contained `exited 0 -- it must fail before implementation` verbatim.
- Step 7-11 rewired `gate()`'s per-test loop: an exit-0 run now lands in `passing` and is judged only after `_base_findings()` runs, per step 8's ordering. DEC-071's finding text (step 10 arm a) is byte-identical, only moved.
- Step 12: `tests/test_gate.py::test_gate_falls_through_to_base_when_the_worktree_test_already_passes` and `::test_gate_still_fails_when_the_worktree_and_base_both_pass` both pass, `2 passed`.
- Step 13: `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py tests/test_cli.py tests/test_config.py` -> `207 passed`, no other test's state changed against the step-1 baseline.
- Step 15: `uv run --group dev pytest -q tests/test_stages.py` -> `30 passed`. Committed `e8bed14` `fix(TICKET-090): an exit-0 repro run falls through to the base check`, touching `pipeline/core/gate.py`, `tests/test_gate.py`, `CLAUDE.md`.
- Acceptance criteria: all named tests pass individually (8 tests, `8 passed`); `grep -c "falls through to the base run" CLAUDE.md` = 1; `grep -c "selector matched nothing" pipeline/core/gate.py` = 0; `grep -c "exited 0 -- it must fail before implementation" pipeline/core/gate.py` = 1.
- No plan deviation. TDD followed: step 2's test written and confirmed passing against the unmodified code (a regression guard per the plan, not a repro) before any production code changed.

### 2026-08-29 06:09:12Z · implementing · session · session=ed6099ed-1dea-48ee-9df1-ad706f219e8e

`implementing` ran as session `ed6099ed-1dea-48ee-9df1-ad706f219e8e`
- replay: `claude --resume ed6099ed-1dea-48ee-9df1-ad706f219e8e`
- log: `.project/logs/TICKET-090-implementing-ed6099ed.log`
- cost: $0.87 of a $8 cap
- tokens: 14,118 out (488 thinking) · 76 in · 2,324,660 cache read · 66,596 cache write

### 2026-08-29 06:09:12Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Implemented all 15 plan steps: gate() falls through an exit-0 worktree run to a base check before judging expect:; committed e8bed14

### 2026-08-29 · review · result=ok

**Reviewed the delta `main...HEAD` (`1834511`, `e8bed14`): no blocking findings.**

I re-ran every acceptance criterion. `uv run --group dev pytest -q` ->
`471 passed in 33.48s`. The four named files plus `tests/test_stages.py` ->
`237 passed`. `grep -c "falls through to the base run" CLAUDE.md` = 1,
`grep -c "selector matched nothing" pipeline/core/gate.py` = 0,
`grep -c "exited 0 -- it must fail before implementation" pipeline/core/gate.py`
= 1. `git status --porcelain` printed nothing.

Two findings I raised and then refuted:

1. "A selector matching nothing is credited when base names the node in a
   collection error." Refuted: the fall-through runs only when the worktree run
   exits 0, and one runner cannot exit both 0 and non-zero for the same missing
   selector. `pipeline/core/gate.py:271` holds that guard.
2. "The new local `base` list shadows a `base_ref` binding later in `gate()`."
   Refuted: the later uses are `base_out` and `base_ref(cfg)`, at
   `pipeline/core/gate.py:586-596`.

Two non-blocking notes, both already accepted in `## Decisions`:

1. Low. `findings += base` is unconditional, so arm (c) and `_base_verdict()`'s
   `ok:` line can fence the same base output twice. `_dedupe()`
   (`pipeline/core/gate.py:778`) replaces the second copy with a pointer.
2. Low. The `passing` loop has no `ESCAPE_RE` arm, so an `expect:` holding a
   literal backslash escape gets a substantive finding on that path, not a
   structural one.

### 2026-08-29 06:13:44Z · review · session · session=da7eaff7-4b3b-4a81-b655-d62c0fa04be9

`review` ran as session `da7eaff7-4b3b-4a81-b655-d62c0fa04be9`
- replay: `claude --resume da7eaff7-4b3b-4a81-b655-d62c0fa04be9`
- log: `.project/logs/TICKET-090-review-da7eaff7.log`
- cost: $1.58 of a $5 cap
- tokens: 14,056 out (7,630 thinking) · 52 in · 1,272,702 cache read · 58,763 cache write

### 2026-08-29 06:13:44Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed e8bed14 against the 11 acceptance criteria: all met, full suite 471 passed, 2 non-blocking notes

### 2026-08-29 06:14:22Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 06:14:23Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/090


Rebasing (1/2)Rebasing (2/2)Successfully rebased and updated refs/heads/ticket/090.
Already up to date.
Updating ac3015d..8a2a0f8
Fast-forward
 CLAUDE.md             |   6 +++
 pipeline/core/gate.py | 102 +++++++++++++++++++++++++++++++++++---------------
 tests/test_gate.py    |  27 ++++++++++++-
 3 files changed, 104 insertions(+), 31 deletions(-)

```

### 2026-08-29 06:14:23Z · merging · decision

decision recorded as `DEC-090`
