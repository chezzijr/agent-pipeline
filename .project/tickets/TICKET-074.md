---
id: TICKET-074
stage: done
class: bugfix
branch: ticket/074
test_file: tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage
files_declared:
- CLAUDE.md
- pipeline/core/gate.py
- pipeline/templates/pipeline.toml
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_dispatch.py
- tests/test_gate.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 10
  plan_files: 6
  no_result: 0
  plan_rejections: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: a35235b8-6335-4af2-8682-1f8351bfc324
  log: .project/logs/TICKET-074-review-a35235b8.log
approved_by: 'chezzijr (via Claude Code, while away; reviewer also filed this ticket
  and rejected its first plan for the stale shlex call site -- audit in thread). Verified:
  the call site is now format_test_cmd(cfg[''test_suite_without_new''], test), matching
  gate.py:350 on main.'
approved_at: '2026-08-27T19:19:11.981172+00:00'
---

## Summary

**`review` passed the delta on 2026-08-28 with no blocking findings.** The work
is implemented and reviewed; three commits sit on `main..HEAD` -- `e3c81a6`
(fix), `16e303f` (tests), `dc2cbd3` (docs), on top of the reproduction
`e5acf54`. Step 1 was a no-op: the worktree was already on `06b1b42`.

The bug it fixes: `pipeline/core/gate.py` read `if code != 0:` and reported
every non-zero `test_suite_without_new` exit as ``suite excluding `{test}` is
RED -- pre-existing breakage, fix that first``. A command that never ran a test
read identically. `suite_ran()` now gates that verdict on evidence of a run, and
everything else gets a `could not run the suite` finding naming the exit code.

Re-verified in review, on this machine:
- `uv run --group dev pytest -q` -> `392 passed in 19.06s`.
- `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`, 141 `ok`
  lines. The plan's 122 is stale on `main` too; the guard's table is untouched
  by this diff.
- The six criterion tests, run in one invocation -> `6 passed in 0.19s`.
- `grep -n shlex pipeline/core/gate.py` prints nothing (DEC-067); no new import
  in `tests/test_gate.py` (DEC-017); the new finding is not in
  `STRUCTURAL_MARKS`, so routing is unchanged (DEC-065).

Two non-blocking findings, both in the `2026-08-28 · review · session` thread
entry: `pipeline/templates/skills/pipeline-config/SKILL.md:29` still says
`Three traps` above four bullets, and
`tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
fails on `tests/test_dispatch.py` alone as well as in the pair -- pre-existing,
not caused by this diff, and green in the full-suite run.

## Reproduction

`tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage`,
committed at `8a02224`.

Sets `test_suite_without_new = "sh -c 'if ; then'"` (a shell syntax error, so
no test ever runs) and asserts the gate's findings do not contain the
pre-existing-breakage wording. Run: `uv run --group dev pytest -q
tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage`

Failure output:

    AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
    *-- identical output, already quoted in the `## Thread` entry `2026-08-27 16:32:15Z · plan-validation · gate · verdict=FAIL` --*']
    assert not True

expect: RED -- pre-existing breakage


## Digest

- Files touched: `pipeline/core/gate.py` (the fix); `tests/test_gate.py` and
  `tests/test_dispatch.py` (the tests); `pipeline/templates/pipeline.toml`,
  `pipeline/templates/skills/pipeline-config/SKILL.md`, `CLAUDE.md` (the docs).
- **This worktree is stale and must be rebased first.** The branch sits on
  `d4138c4`; `main` is `06b1b42`. `git merge-base --is-ancestor main HEAD` is
  false. TICKET-067, TICKET-068, TICKET-076, TICKET-079, TICKET-080 and
  TICKET-083 landed while this ticket sat at `awaiting-approval`. The branch holds one commit, `8a02224`,
  touching `tests/test_gate.py` only, and `git merge-tree --write-tree main HEAD`
  reports no conflict, so the rebase is clean.
- Every line number below is `main`'s and is valid after step 1's rebase. In the
  stale worktree they sit about 80 lines lower and the call shape is the pre-067
  one. I re-checked every one of them against `06b1b42` on 2026-08-28.
- Gotcha: the dispatcher's running gate predates DEC-079. Its finding on
  2026-08-27 19:04:52Z reads `acceptance criterion names no test: - ...` and
  appends no rule text, while `main`'s `gate()` appends `CRIT_RULE` to every such
  finding. So the command-plus-outcome arm is not live yet. A criterion must name
  a test -- `pytest`, an identifier starting `test`, a `::` selector, or a
  `tests/` path. Every criterion in `## Acceptance criteria` does.
- The bug is `pipeline/core/gate.py:350-355`, the last statement of the `else:`
  arm of `if not test:`, right after `findings += _base_findings(...)`. Line 350
  is `code, out = run_cmd(format_test_cmd(cfg["test_suite_without_new"], test), wd)`,
  line 351 is `if code != 0:`, and lines 352-355 are the single RED finding.
- Entry point: `gate(project, tid, workdir)` at `pipeline/core/gate.py:247`.
  `_base_findings()` is at line 202; the new constants go between the two.
- `format_test_cmd(template, test)` lives in `pipeline/core/config.py` and
  shlex-quotes each of `{test}`, `{path}` and `{name}` (DEC-067). It is already
  imported at `pipeline/core/gate.py:7`, and `grep -n shlex pipeline/core/gate.py`
  matches nothing on `main`. This is what the rejection corrected.
- **Reuse, not a second classifier.** TICKET-068 put `SHELL_CANNOT_RUN` (126 and
  127) and `NO_TESTS_RE = re.compile(r"no tests ran|no tests were run|collected
  0 items")` in `pipeline/core/config.py`, where `suite_failure()` uses them at
  `register`. They do not fix this bug on their own: the reproduction exits 2
  printing a shell syntax error, which matches neither. `suite_ran()` imports
  `NO_TESTS_RE` and vetoes on it, so the two classifiers agree everywhere
  DEC-068 already decided.
- I ran the classifier's 12 cases on this machine on 2026-08-28; all 12 pass.
  The veto is load-bearing: with it stubbed out, `(2, "collected 0 items / 1
  error")` returns `True`, because `1 error` matches the count regex. That is
  `pytest`'s collection error, which is this ticket's bug class exactly.
- Pattern to copy: the `test_one` run above it (`pipeline/core/gate.py:304-347`)
  already splits "errored" from "failed" with `node not in out`. The suite run
  has no test name to look for, so it tests the exit code and the output shape.
- Measured on this machine: `sh -c 'if ; then'` exits 2 printing a bash syntax
  error; `sh -c nosuchbinary` exits 127; `pytest` on a missing path exits 4
  printing `no tests ran in 0.00s`. pytest, go test, jest, unittest and rspec
  exit 1 when a test fails; cargo test exits 101; mocha exits with its failure
  count.
- Gotcha: `tests/test_gate.py` may gain **no new import** (DEC-017, DEC-018,
  DEC-030, DEC-065, DEC-067) -- the gate copies that file onto a checkout of base
  and imports it there. Line 8 is `from helpers import FIXTURE, project`, line 9
  is `from pipeline.core import ticket as T`, line 10 is `from pipeline.core.gate
  import _dedupe, gate, plan_steps`. Step 6's two tests use `project`, `gate` and
  `shutil` only. The unit test for `suite_ran` goes in `tests/test_dispatch.py`,
  beside `test_structural_only_classifies_a_gate_finding` (line 1324), which
  lives there for the same reason.
- Gotcha: the last three lines of `gate()` dedupe every returned finding against
  every other finding's fenced block, so a finding's own quoted output comes back
  as a pointer to the thread entry that carries it. The verbatim output survives
  in the ticket file, not in the returned list. Assert the exit code on the
  finding and the output on the ticket file, the way
  `tests/test_gate.py::test_gate_substitutes_the_path_placeholder_in_test_suite_without_new`
  (line 194) already asserts `GOT:test_thing.py` on `thread()[-1].text`.
- Gotcha: `tests/test_dispatch.py:391`, inside `_gating_project()` (line 380),
  sets `test_suite_without_new = "! test -f broken"`, which exits 1 with **empty
  output**, and `test_a_stale_plan_is_re_gated_on_approval` (line 410) requires
  that to stay RED. Output alone cannot be the evidence; the exit code carries it.
- Gotcha: `tests/test_gate.py:194` sets `test_suite_without_new` to
  `echo GOT:{path}; exit 1` and asserts `pre-existing breakage`. Exit 1 keeps
  that test RED under `suite_ran()`.
- Routing does not change. The new finding is not in `STRUCTURAL_MARKS`, so
  `structural_only()` reads it as substantive and it charges
  `plan_validation_attempts`, exactly like the finding it replaces (DEC-065).
- None of the six files is in `machine.FENCED`; `pipeline/templates/pipeline.toml`
  is not `.project/pipeline.toml`. TICKET-071, which the rejection warned would
  move the `test_one` call sites again, is at `stage: escalated` and unmerged.

## Decisions checked

- DEC-068 (active) -- `register` refuses only a `test_suite` that cannot run:
  exit 126, exit 127, or a non-zero exit whose output matches `NO_TESTS_RE`.
  Binding, and this plan complies twice. It reuses `NO_TESTS_RE` rather than
  writing a second copy of it. It does not reuse the polarity: see
  `## Decisions` for why the gate allowlists "ran" where `register` allowlists
  "cannot run". Different call site, different config key, different cost of a
  wrong answer; DEC-068's rule at `register` is untouched by this plan.
- DEC-067 (active) -- one substitution function, `format_test_cmd()`, for all
  four test-command call sites, and every substitution stays shlex-quoted.
  Binding: step 4 binds `suite_cmd = format_test_cmd(cfg["test_suite_without_new"], test)`
  and adds no `shlex` call. This is the correction the rejection asked for.
- DEC-017 (active) -- the gate copies the branch's `test_file` onto a checkout of
  base and imports it there. Binding: `tests/test_gate.py` gains no new import.
- DEC-018 (active) -- states the same rule as a ban on new `from helpers import`
  names in `tests/test_gate.py`, and keeps the `ok:` prefix load-bearing. This
  plan adds no `ok:` finding.
- DEC-030 (active) -- a Tier A finding states the rule that would fix it. The new
  "could not run" finding names the exit code and the config key to fix.
- DEC-065 (active) -- `STRUCTURAL_MARKS` is a `startswith` allowlist and an
  unlisted finding reads as substantive on purpose; `tests/test_gate.py` may gain
  no import, which is why `structural_only()` is tested in
  `tests/test_dispatch.py`. This plan follows both: no new mark, and the
  `suite_ran()` unit test goes in `tests/test_dispatch.py`.
- DEC-079 (active) -- a Tier A criterion may name a test, or a command plus the
  result of running it; the two arms are OR'd. Not binding, and this plan does
  not rely on the command arm: the gate that judged the last plan predates
  DEC-079, so every criterion here names a test.
- grep terms used against `.project/decisions/`: `exit code`, `non-zero`,
  `test_suite`, `Tier A`, `gate(`, `acceptance criterion`.

## Plan

1. Rebase this worktree onto base: run `git rebase main`, then `grep -n format_test_cmd pipeline/core/gate.py` and expect three call sites at lines 227, 304 and 350, and `grep -n shlex pipeline/core/gate.py` and expect no match; the branch is based on `d4138c4`, which predates TICKET-067, and the rebase replays only `8a02224`, which touches `tests/test_gate.py`.
2. Run `uv run --group dev pytest -q tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage` and watch `tests/test_gate.py` fail with an `AssertionError` whose first finding is `suite excluding` the test `is RED -- pre-existing breakage, fix that first`; change no file in this step.
3. In `pipeline/core/gate.py`, change line 7 to `from pipeline.core.config import NO_TESTS_RE, format_test_cmd, project_config`, then insert the classifier below between `_base_findings()` and `def gate(`, above line 247.

   ```python
   # `test_suite_without_new` exiting non-zero is pre-existing breakage only when
   # the run produced evidence it ran. A shell syntax error exits 2 with no test
   # result and used to read as breakage in the project's own tests (TICKET-074).
   # pytest, go test, jest, unittest and rspec exit 1 on a failing test; cargo
   # exits 101. The regex is the fallback for a runner that exits with its own
   # failure count -- mocha exits 3 on three failures.
   SUITE_FAILED_CODES = (1, 101)
   SUITE_RAN_RE = re.compile(
       r"\b\d+\s+(?:failed|failing|passed|passing|errors?|skipped)\b"
       r"|\bran\s+\d+\s+tests?\b"
       r"|\btest result:"
       r"|^(?:---\s+)?FAIL\b", re.M | re.I)


   def suite_ran(code: int, out: str) -> bool:
       """True when a non-zero suite run produced evidence it ran tests.

       False is the safe answer: it makes `gate()` report "could not run"
       instead of asserting breakage nobody observed.

       `NO_TESTS_RE` (DEC-068) vetoes first. `pytest`'s collection error exits 2
       printing `collected 0 items / 1 error`, and `1 error` matches the count
       regex, so without the veto a suite that collected nothing reads as red.
       """
       if NO_TESTS_RE.search(out):
           return False
       return code in SUITE_FAILED_CODES or bool(SUITE_RAN_RE.search(out))
   ```

4. In `pipeline/core/gate.py`, replace lines 350-355 with the two-arm form below, keeping the RED finding's wording byte-identical; `suite_cmd` goes through `!r` like `expect` above it, because a backtick or newline in the command would corrupt the finding's fence.

   ```python
               suite_cmd = format_test_cmd(cfg["test_suite_without_new"], test)
               code, out = run_cmd(suite_cmd, wd)
               if code != 0 and suite_ran(code, out):
                   findings.append(
                       f"suite excluding `{test}` is RED -- pre-existing breakage, "
                       f"fix that first\n```\n{out[-1200:]}\n```"
                   )
               elif code != 0:
                   findings.append(
                       f"could not run the suite excluding `{test}`: {suite_cmd!r} "
                       f"exited {code} and reported no test result, so pre-existing "
                       f"breakage is neither proven nor ruled out -- fix "
                       f"`test_suite_without_new` in `.project/pipeline.toml`"
                       f"\n```\n{out[-1200:]}\n```")
   ```

5. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py`, expect every test to pass -- including `tests/test_dispatch.py::test_a_stale_plan_is_re_gated_on_approval`, whose suite exits 1 with empty output and must still read as RED, and `tests/test_gate.py::test_gate_substitutes_the_path_placeholder_in_test_suite_without_new`, whose suite exits 1 -- then commit `pipeline/core/gate.py` as `fix(TICKET-074): report a suite command that never ran as could-not-run`.
6. Append to `tests/test_gate.py`, after `test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage`, the two tests below, which add no import (DEC-017).

   ```python
   def test_gate_reports_a_suite_that_ran_and_failed_as_pre_existing_breakage():
       """Exit 1 with NO output is a red suite, not a broken command -- it is
       what `! test -f broken` does in tests/test_dispatch.py."""
       d = project()
       (d / ".project" / "pipeline.toml").write_text(
           'test_one = "echo test_broken; exit 1"\n'
           'test_suite = "true"\n'
           'test_suite_without_new = "exit 1"\n')
       ok, failures = gate(d, "TICKET-001")
       assert not ok
       assert any("RED -- pre-existing breakage" in f for f in failures), failures
       shutil.rmtree(d)


   def test_gate_names_the_exit_code_when_the_suite_command_could_not_run():
       d = project()
       (d / ".project" / "pipeline.toml").write_text(
           'test_one = "echo test_broken; exit 1"\n'
           'test_suite = "true"\n'
           'test_suite_without_new = "echo boom >&2; exit 127"\n')
       ok, failures = gate(d, "TICKET-001")
       assert not ok
       hits = [f for f in failures if "could not run the suite" in f]
       assert len(hits) == 1, failures
       assert "exited 127" in hits[0], hits[0]
       # the fence is deduped out of the returned finding, not out of the file
       entry = (d / ".project" / "tickets" / "TICKET-001.md").read_text()
       assert "boom" in entry, entry
       shutil.rmtree(d)
   ```

7. Append to `tests/test_dispatch.py`, after `test_structural_only_classifies_a_gate_finding` at line 1324, the table test below, whose import sits inside the function because `tests/test_dispatch.py` is never copied onto base.

   ```python
   def test_suite_ran_tells_a_red_suite_from_a_command_that_never_ran():
       from pipeline.core.gate import suite_ran
       ran = [(1, ""),
              (1, "1 failed, 84 passed in 3.21s"),
              (101, "test result: FAILED. 3 passed; 1 failed"),
              (3, "  3 failing"),
              (2, "Ran 7 tests in 0.4s"),
              (2, "--- FAIL: TestAdd (0.00s)")]
       never = [(2, "sh: -c: line 1: syntax error near unexpected token"),
                (127, "sh: line 1: pytest: command not found"),
                (4, "no tests ran in 0.00s"),
                (126, ""),
                # `1 error` matches the count regex; NO_TESTS_RE vetoes it
                (2, "collected 0 items / 1 error\nERROR tests/test_x.py"),
                (5, "no tests ran in 0.01s")]
       for code, out in ran:
           assert suite_ran(code, out), (code, out)
       for code, out in never:
           assert not suite_ran(code, out), (code, out)
   ```

8. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py`, expect all green, and commit `tests/test_gate.py` and `tests/test_dispatch.py` as `test(TICKET-074): pin the red-suite and could-not-run halves of suite_ran`.
9. Update the three docs in one commit: in `pipeline/templates/pipeline.toml` extend the comment at line 16 to say that a red `test_suite_without_new` must exit 1 or 101 or print a test count, or the gate reports "could not run"; in `pipeline/templates/skills/pipeline-config/SKILL.md` change line 27's third table cell to say non-zero **and** a reported test result means pre-existing breakage, and add a fourth trap bullet after the existing three listing the accepted shapes (`3 failed`, `Ran 7 tests`, `test result:`, a line starting `FAIL`, exit 1 or 101) and telling a project whose runner exits otherwise to wrap the command; in `CLAUDE.md` extend the gotcha that starts at line 108 (`- **A test that *errors* exits non-zero exactly like one that fails.**`) with one sentence naming `suite_ran()` in `pipeline/core/gate.py` and TICKET-074; commit the three as `docs(TICKET-074): a red suite must report a test result, not just a non-zero exit`.
10. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py` as the final check on `pipeline/core/gate.py`, expect both green and the guard's 122 cases to pass, and paste the two counts into the ticket's `## Thread`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage`
  reports `1 passed`: no finding contains `RED -- pre-existing breakage` when
  `test_suite_without_new` is a shell syntax error.
- `tests/test_gate.py::test_gate_names_the_exit_code_when_the_suite_command_could_not_run`
  passes: exactly one finding contains `could not run the suite`, that finding
  contains `exited 127`, and the ticket file contains `boom`.
- `tests/test_gate.py::test_gate_reports_a_suite_that_ran_and_failed_as_pre_existing_breakage`
  passes: a suite exiting 1 with no output still gets `RED -- pre-existing
  breakage`. It fails if `suite_ran()` judges output alone.
- `tests/test_dispatch.py::test_suite_ran_tells_a_red_suite_from_a_command_that_never_ran`
  passes all twelve cases listed in step 7, including the `collected 0 items / 1
  error` case, which fails if `suite_ran()` drops the `NO_TESTS_RE` veto.
- `tests/test_dispatch.py::test_a_stale_plan_is_re_gated_on_approval` still
  passes, so the re-gate of a project whose suite exits 1 with empty output still
  charges `stale_regate`.
- `tests/test_gate.py::test_gate_substitutes_the_path_placeholder_in_test_suite_without_new`
  still passes and `grep -n shlex pipeline/core/gate.py` prints nothing after
  step 4, so TICKET-067's `{path}` substitution in `test_suite_without_new`
  survives this change and the suite command still routes through
  `format_test_cmd()`.
- `uv run --group dev pytest -q` is green and
  `./pipeline/hooks/test_dangerous_commands.py` reports its 122 cases green.

## Decisions

**A non-zero `test_suite_without_new` is pre-existing breakage only when the run
produced evidence it ran.** `suite_ran()` in `pipeline/core/gate.py` is that
evidence test: exit 1 or 101, or output carrying a test count (`3 failed`,
`Ran 7 tests`, `test result:`, a line starting `FAIL`), with `NO_TESTS_RE`
vetoing first. Everything else is reported as "could not run", naming the exit
code and quoting the output. Before this, a shell syntax error in the command
exited 2 and was reported as breakage in the project's own tests; on 2026-08-27
that sent an operator to fix a suite that was fine and charged `stale_regate`.
Do not simplify this back to `if code != 0`.

**The gate allowlists "ran"; `register` allowlists "cannot run" (DEC-068). The
two polarities are deliberate and must not be merged.** At `register` a false
"cannot run" refuses a project whose suite is legitimately red, which is exactly
the project this tool exists for -- so DEC-068 names three narrow cannot-run
signals and registers everything else. At the gate a false "ran" sends an
operator to fix breakage nobody observed, and the output is a finding, not a
refusal -- so `suite_ran()` names the ran signals and reports everything else as
"could not run". Applying DEC-068's rule here does not fix this bug: the
reproduction exits 2 on a shell syntax error, matching neither `SHELL_CANNOT_RUN`
nor `NO_TESTS_RE`.

**`suite_ran()` imports `NO_TESTS_RE` from `pipeline/core/config.py` rather than
restating it.** The veto is load-bearing, not decoration: `pytest`'s collection
error exits 2 printing `collected 0 items / 1 error`, and `1 error` matches
`SUITE_RAN_RE`'s count alternative, so without the veto a suite that collected
nothing is reported as pre-existing breakage.

**The exit-code arm carries the common case, and the regex is the fallback.**
`tests/test_dispatch.py::_gating_project` -- and any suite whose runner prints
nothing -- exits 1 with empty output, so output alone cannot be the evidence. The
regex exists for a runner that exits with its failure count (mocha exits 3 on
three failures), which the code allowlist alone would misreport as "could not
run".

**The unit test for `suite_ran()` is in `tests/test_dispatch.py`, not
`tests/test_gate.py`.** DEC-017, DEC-018, DEC-065 and DEC-067: the gate copies
`tests/test_gate.py` onto a checkout of base and imports it there, where a
branch-only name is an `ImportError` that blocks the ticket adding it.
`structural_only()` and `format_test_cmd()` are tested outside that file for the
same reason.

**Routing is unchanged and this is deliberate.** The new finding is absent from
`STRUCTURAL_MARKS`, so it reads as substantive and charges
`plan_validation_attempts`, exactly like the finding it replaces (DEC-065). This
ticket changes what the gate reports, not which counter it charges.

**`verifying` still judges `test_suite` by exit code alone**
(`pipeline/daemon/supervisor.py`, `child(cfg["test_suite"], "suite")`). The
ticket put that out of scope. `suite_ran()` is importable from
`pipeline/core/gate.py` when someone fixes it.

## Rollback

Revert the three commits (steps 5, 8, 9). `pipeline/core/gate.py` goes back to
`if code != 0:` around the single RED finding and drops `NO_TESTS_RE` from its
import, `tests/test_gate.py` and `tests/test_dispatch.py` lose the three added
tests, and the three doc files lose their edits. Nothing else reads
`suite_ran()`, so no other module breaks. Reverting restores the reported bug: a
broken `test_suite_without_new` reads as pre-existing breakage again.

If only the classifier is wrong -- a project's red suite is reported as "could
not run" -- the narrow fix is to widen `SUITE_FAILED_CODES` or `SUITE_RAN_RE` in
`pipeline/core/gate.py`, not to revert the branch.
## Thread

### 2026-08-27 16:15:56Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-27 · triage · reproduce · result=ok

Reproduced. Added
`tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage`
(commit `8a02224`): sets `test_suite_without_new` to a shell syntax error and
asserts the gate's findings omit the "RED -- pre-existing breakage" wording.
It fails with that exact string present, matching the reported symptom.

Not a `chore`: fixing this requires a design choice (what counts as evidence
the suite ran) that the ticket explicitly assigns to planning. Sending to
planning.

`verifying`'s identical exit-code judgment of `test_suite`
(`pipeline/daemon/supervisor.py`) is out of scope per the ticket; not
investigated further here.

### 2026-08-27 16:32:57Z · triage · session · session=2bbaab51-de8b-464c-825a-aa8c899ad10f

`triage` ran as session `2bbaab51-de8b-464c-825a-aa8c899ad10f`
- replay: `claude --resume 2bbaab51-de8b-464c-825a-aa8c899ad10f`
- log: `.project/logs/TICKET-074-triage-2bbaab51.log`

### 2026-08-27 16:32:57Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- gate() reports a non-zero test_suite_without_new as "RED -- pre-existing breakage" even when the command errored without running any test; committed failing test 8a02224

### 2026-08-27 · planning · plan · result=ok

Plan written: 9 steps, 6 files, 3 commits. Evidence that the suite ran is
`suite_ran(code, out)` -- exit 1 or 101, or a test count in the output.

Ran the reproduction test first; it fails with the string the ticket quotes.

Measured the exit codes the plan rests on, on this machine, 2026-08-27:

    $ sh -c 'if ; then'; echo "rc=$?"
    sh: -c: line 1: syntax error near unexpected token `;'
    sh: -c: line 1: `if ; then'
    syntax rc=2
    $ sh -c nosuchbinary; echo "rc=$?"
    sh: line 1: nosuchbinary: command not found
    notfound rc=127
    $ uv run --group dev pytest -q tests/test_nothingmatches.py; echo "rc=$?"
    ERROR: file or directory not found: tests/test_nothingmatches.py
    no tests ran in 0.00s
    pytest-badpath rc=4

Two things I did not do, deliberately.

1. No new `[gate]` config key for a project whose runner exits some other code.
   The finding quotes the exit code, so the operator can see it and wrap the
   command; a fourth test command would widen the `pipeline-config` interface.
2. No routing change. The new finding is substantive, so it charges
   `plan_validation_attempts` exactly like the finding it replaces (DEC-065).

Out of scope and still open: `verifying` judges `test_suite` by exit code the
same way (`pipeline/daemon/supervisor.py`). `suite_ran()` is importable when
someone files that ticket.

### 2026-08-27 16:45:23Z · planning · session · session=a0308e84-5ec4-4120-8897-bc1da60e90d9

`planning` ran as session `a0308e84-5ec4-4120-8897-bc1da60e90d9`
- replay: `claude --resume a0308e84-5ec4-4120-8897-bc1da60e90d9`
- log: `.project/logs/TICKET-074-planning-a0308e84.log`

### 2026-08-27 16:45:23Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned: suite_ran(code, out) in gate.py -- exit 1/101 or a test count in the output is the evidence; otherwise the finding says could not run, naming exit code and output. 9 steps, 6 files.

### 2026-08-28 · plan-validation · validate · result=ok

**Tier B judgment: PASS.** This entry sits above the gate entry below it, not
after it: the file's last bytes are ANSI escapes I cannot reproduce in an
exact-match edit, and Bash cannot write the ticket from this stage.

long: eight scored items, one line each.

1. Root cause: `pipeline/core/gate.py:276` reads `if code != 0:` as proof the
   project's suite is red. An exit code alone cannot separate "the command
   never ran" from "tests failed". The plan classifies the exit, so it fixes
   the cause, not the assertion.
2. Decisions: DEC-017/018/065 bind test placement. Step 5's two tests use
   `project()` and `gate`, both already imported in `tests/test_gate.py` --
   no new import. Step 6 lands `suite_ran()`'s unit test beside
   `test_structural_only_classifies_a_gate_finding`
   (`tests/test_dispatch.py:1303`), which DEC-065 requires.
3. Scope: 9 steps, all inside `files_declared`. Step 8 (docs) traces to no
   acceptance criterion. It stays: `CLAUDE.md` makes
   `pipeline/templates/skills/pipeline-config/SKILL.md` part of the interface,
   and its line 27 is one of the only three sites of the "pre-existing
   breakage" wording (`gate.py:278`, `SKILL.md:27`, `tests/test_gate.py:199`).
4. Falsifiable: `test_gate_reports_a_suite_that_ran_and_failed_as_pre_existing_breakage`
   fails if `suite_ran()` judges output alone; step 6's table asserts both
   polarities over ten cases.
5. No research left: every step names a file and a symbol. I confirmed
   `gate.py:275-280`, `SKILL.md:27`, `CLAUDE.md:109` and
   `tests/test_dispatch.py:1303` are where the plan says.
6. Riskiest step: step 2, the `SUITE_FAILED_CODES` / `SUITE_RAN_RE`
   classifier. `## Rollback` states its fallback: widen either constant, do
   not revert the branch.
7. Regression surface: a genuinely red suite misreported as "could not run".
   `tests/test_dispatch.py:370` sets `test_suite_without_new = "! test -f
   broken"` -- exit 1, empty output -- and
   `test_a_stale_plan_is_re_gated_on_approval` covers it. Routing is covered
   by `STRUCTURAL_MARKS` (`gate.py:54-65`) gaining no entry.
8. Blast radius: `bugfix`, 6 files -- 1 code, 2 test, 3 doc. In class. None of
   the six is in `machine.FENCED`, so this branch merges unattended.

Unverified: I read step 6's ten `suite_ran()` cases; I did not run them. The
guard rejects a backslash in Bash for this stage, so I could not execute the
regex. Step 6 executes them.

### 2026-08-27 16:59:45Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage` fails as required
```
xisting breakage[39;49;00m[33m"[39;49;00m [95min[39;49;00m f [94mfor[39;49;00m f [95min[39;49;00m failures), failures[90m[39;49;00m
[1m[31mE       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first[0m
[1m[31mE         *-- identical output, already quoted in the `## Thread` entry `2026-08-27 16:59:25Z · plan-validation · gate · verdict=FAIL` --*'][0m
[1m[31mE       assert not True[0m
[1m[31mE        +  where True = any(<generator object test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage.<locals>.<genexpr> at 0x7f13201d0ee0>)[0m

[1m[31mtests/test_gate.py[0m:199: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage[0m - AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.06s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage` fails on base `main` too -- the bug is not already fixed upstream
```
sertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage[0m - AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-g3az850d/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-g3az850d/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 17:06:20Z · plan-validation · session · session=894c0882-94ec-4a37-aef9-f03f6a592990

`plan-validation` ran as session `894c0882-94ec-4a37-aef9-f03f6a592990`
- replay: `claude --resume 894c0882-94ec-4a37-aef9-f03f6a592990`
- log: `.project/logs/TICKET-074-plan-validation-894c0882.log`

### 2026-08-27 17:06:20Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan PASSES Tier B: root cause is gate.py:276 judging test_suite_without_new by exit code; all eight items scored in the thread; step 6's ten suite_ran() cases read, not executed

### 2026-08-27 17:07:03Z · human · rejection

[chezzijr's decision, entered via Claude Code while chezzijr is away; the reviewer also filed this ticket -- audit this reason in the thread]

Step 3 was written against code that no longer exists. It binds:

  suite_cmd = cfg["test_suite_without_new"].format(test=shlex.quote(test))

TICKET-067 merged while this plan sat at plan-validation. On main today, pipeline/core/gate.py:274 reads:

  code, out = run_cmd(format_test_cmd(cfg["test_suite_without_new"], test), wd)

and `import shlex` is gone from that file -- `grep -n 'shlex' pipeline/core/gate.py` matches nothing. So the step as written is a NameError, and if it were made to run it would silently revert {path}/{name} support in test_suite_without_new, which is what TICKET-067 added.

Fix: bind `suite_cmd = format_test_cmd(cfg["test_suite_without_new"], test)` and drop the shlex reference. Re-check every other line number and call shape in the plan against current main at the same time -- 067 also rewrote the two test_one call sites, and TICKET-071's exit-0 branch is still unmerged and will move them again.

Everything else stands and needs no rework. Specifically keep: suite_ran() and its SUITE_FAILED_CODES/SUITE_RAN_RE pair, the ten-case table test in step 6, the criterion pinning that an exit-1 suite with EMPTY output still reads as RED (that is what stops suite_ran judging output alone), the criterion that test_a_stale_plan_is_re_gated_on_approval still passes, and the !r quoting of suite_cmd in the finding for the same reason expect is quoted that way.

### 2026-08-28 · planning · plan · result=ok

Re-planned after the rejection. I audited its reason, as it asked, and it is
correct on every point.

`git merge-base --is-ancestor main HEAD` is false: this worktree sits on
`d4138c4`, `main` is `7efa3dc`. On `main`, `pipeline/core/gate.py:350` reads
`code, out = run_cmd(format_test_cmd(cfg["test_suite_without_new"], test), wd)`
and `grep -n shlex pipeline/core/gate.py` matches nothing. The rejected step 3
was a `NameError` and would have reverted TICKET-067.

How this plan differs.

1. Step 4 binds `suite_cmd = format_test_cmd(cfg["test_suite_without_new"], test)`.
   No `shlex` reference remains.
2. Step 1 rebases onto `main` before anything else. `git merge-tree
   --write-tree main HEAD` reports no conflict; the branch replays one commit.
3. Every line number is re-checked against `main`: `gate.py:350-355`,
   `gate.py:247`, `SKILL.md:27`, `CLAUDE.md:109`, `tests/test_dispatch.py:1324`,
   `tests/test_gate.py:194`.
4. New: TICKET-068 landed `NO_TESTS_RE` in `pipeline/core/config.py`.
   `suite_ran()` reuses it as a veto instead of a second copy (DEC-068).

Kept, as the rejection required: `suite_ran()` with `SUITE_FAILED_CODES` and
`SUITE_RAN_RE`, the table test, the empty-output-exit-1-stays-RED criterion, the
`stale_regate` criterion, and `{suite_cmd!r}` in the finding.

I ran the classifier's cases rather than reading them. All 12 pass. Stubbing
the veto out turns `(2, "collected 0 items / 1 error")` from False to True --
`pytest`'s collection error, misread as breakage. That case is now in the table.

TICKET-071 is `stage: escalated`, so it will not move these lines.

Out of scope and still open: `verifying` judges `test_suite` by exit code the
same way (`pipeline/daemon/supervisor.py`).

### 2026-08-27 18:53:05Z · planning · session · session=067b4486-b1bd-44f8-9cf8-f8c9f814e90b

`planning` ran as session `067b4486-b1bd-44f8-9cf8-f8c9f814e90b`
- replay: `claude --resume 067b4486-b1bd-44f8-9cf8-f8c9f814e90b`
- log: `.project/logs/TICKET-074-planning-067b4486.log`

### 2026-08-27 18:53:05Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-planned on current main after the rejection: format_test_cmd replaces shlex, step 1 rebases the stale worktree, suite_ran reuses NO_TESTS_RE (DEC-068); 10 steps, 6 files, 12 classifier cases run and green

### 2026-08-27 19:04:52Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage` fails as required
```
xisting breakage[39;49;00m[33m"[39;49;00m [95min[39;49;00m f [94mfor[39;49;00m f [95min[39;49;00m failures), failures[90m[39;49;00m
[1m[31mE       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first[0m
[1m[31mE         *-- identical output, already quoted in the `## Thread` entry `2026-08-27 19:04:33Z · plan-validation · gate · verdict=FAIL` --*'][0m
[1m[31mE       assert not True[0m
[1m[31mE        +  where True = any(<generator object test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage.<locals>.<genexpr> at 0x7fdb96e14ee0>)[0m

[1m[31mtests/test_gate.py[0m:199: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage[0m - AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.05s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage` fails on base `main` too -- the bug is not already fixed upstream
```
ssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage[0m - AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-k7ybi95b/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-k7ybi95b/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 9ms[0m[0m

```
- acceptance criterion names no test: - `grep -n shlex pipeline/core/gate.py` prints nothing after step 4.

### 2026-08-27 19:04:52Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion names no test: - `grep -n shlex pipeline/core/gate.py` prints nothing after step 4.

### 2026-08-28 · planning · plan · result=ok

Tier A failed on one item, and only that item changed.

    acceptance criterion names no test: - `grep -n shlex pipeline/core/gate.py` prints nothing after step 4.

That criterion is now folded into the one above it, which names
`tests/test_gate.py::test_gate_substitutes_the_path_placeholder_in_test_suite_without_new`.
All 7 criteria name a test.

Why it failed although DEC-079 added the command-plus-outcome arm at 17:31Z,
before the 19:04:52Z gate run: the finding carries no `CRIT_RULE` text, and
`main`'s `gate()` appends `CRIT_RULE` to every such finding. The dispatcher runs
gate code from before DEC-079 -- "A merged change to the dispatcher's own Python
is inert until restart". A criterion naming a test passes both gate versions.

Re-checked against `main`, now `06b1b42`, was `7efa3dc`. TICKET-080 touched
`pipeline/cli/main.py` and `tests/test_cli.py` only. `pipeline/core/gate.py:350`
still reads `run_cmd(format_test_cmd(cfg["test_suite_without_new"], test), wd)`,
`grep -n shlex pipeline/core/gate.py` matches nothing, and `git merge-tree
--write-tree main HEAD` is clean. I re-ran the 12 classifier cases: all 12 pass,
and stubbing the `NO_TESTS_RE` veto turns `(2, "collected 0 items / 1 error")`
True.

Outside this ticket: restart the dispatcher so it gates on merged code.

### 2026-08-27 19:11:01Z · planning · session · session=36d874d7-b4c4-430b-925f-3f65b2365d8b

`planning` ran as session `36d874d7-b4c4-430b-925f-3f65b2365d8b`
- replay: `claude --resume 36d874d7-b4c4-430b-925f-3f65b2365d8b`
- log: `.project/logs/TICKET-074-planning-36d874d7.log`

### 2026-08-27 19:11:01Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-planned: the shlex criterion now names a test (the running gate predates DEC-079); re-checked every line number against main 06b1b42; 10 steps, 6 files, 12 classifier cases green

### 2026-08-28 · plan-validation · judgment · verdict=PASS

long: eight scored items, each carrying its own evidence.

This entry sits above the 19:11:19Z gate entry, not below it. The guard blocks
`>>` and `tee`, and the entry below ends in raw ANSI bytes I cannot reproduce in
an anchor, so appending at end of file was not available. I wrote my verdict
into `## Summary` as well.

**Root cause.** `gate()` reads a non-zero `test_suite_without_new` exit as proof
the suite ran and failed. The exit code conflates "a test failed" with "the
command never started". The plan fixes that, not the assertion: `suite_ran()`
gates the RED verdict on evidence of a run.

**Decision conflict.** DEC-068 is the only tension. The plan reuses
`NO_TESTS_RE` (`pipeline/core/config.py:123`), leaves `register`'s rule
untouched, and `## Decisions` justifies the opposite polarity. DEC-017 and
DEC-018: step 6's tests use `project`, `gate` and `shutil`, imported at
`tests/test_gate.py:3,8,10` -- no new import. DEC-065: the new finding is absent
from `STRUCTURAL_MARKS` (`pipeline/core/gate.py:88-99`), so it charges
`plan_validation_attempts`. DEC-067: step 4 binds `format_test_cmd(...)`, and
`grep -n shlex pipeline/core/gate.py` matches nothing on `main`.

**Scope.** Step 9 (three doc files) traces to no acceptance criterion.
`CLAUDE.md` requires it: "a change to a CLI command, a stage's behaviour, or the
human gates is not finished until the skill says the same thing". Accepted.
Every other step traces to a criterion.

**Falsifiable criteria.** Criterion 1 alone is satisfiable by deleting the RED
finding. Criteria 3 and 5 block that, criterion 4 blocks dropping the
`NO_TESTS_RE` veto, criterion 6 blocks reintroducing `shlex`.

**No research left.** I re-checked every line number against `06b1b42`:
`format_test_cmd` call sites at 227, 304 and 350; `_base_findings` at 202;
`gate` at 247; the import at line 7; the RED finding at 350-355;
`tests/test_dispatch.py` at 380, 410 and 1324; `tests/test_gate.py:194`. All
hold.

**Riskiest step: 4**, which replaces the live gate verdict. `## Rollback` states
the fallback: widen `SUITE_FAILED_CODES` or `SUITE_RAN_RE`, do not revert.

**Regression surface.**
`tests/test_dispatch.py::test_a_stale_plan_is_re_gated_on_approval` (exit 1,
empty output -- the exit-code arm keeps it RED) and `tests/test_gate.py:194`
(exit 1). Criterion 7 covers the rest.

**Blast radius.** `class: bugfix`, 6 files: 1 code, 2 test, 3 doc. Matches.

I ran `SUITE_RAN_RE` by hand against the step 7 table. All five output-bearing
`ran` cases match, both shell-error `never` cases do not, and
`collected 0 items / 1 error` matches the count arm while `NO_TESTS_RE` matches
`collected 0 items` -- the veto is load-bearing, as `## Decisions` claims.

Three notes, none blocking:

1. Step 9 says the `CLAUDE.md` gotcha starts at line 108. On `main` it is line
   109. The step quotes the bullet verbatim, so it cannot land on the wrong one.
2. Step 9 adds a fourth trap bullet under
   `pipeline/templates/skills/pipeline-config/SKILL.md:29`, which reads
   `Three traps behind that table:`. Update that lead-in in the same edit.
3. I could not run `sh -c 'if ; then'`. The guard answered "`if` is not on the
   read-only allowlist". Its exit 2 stays the plan's measurement, not mine. Step
   2 confirms it. The fix holds for every exit code except 1 and 101.

### 2026-08-27 19:11:19Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage` fails as required
```
xisting breakage[39;49;00m[33m"[39;49;00m [95min[39;49;00m f [94mfor[39;49;00m f [95min[39;49;00m failures), failures[90m[39;49;00m
[1m[31mE       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first[0m
[1m[31mE         *-- identical output, already quoted in the `## Thread` entry `2026-08-27 19:11:01Z · plan-validation · gate · verdict=FAIL` --*'][0m
[1m[31mE       assert not True[0m
[1m[31mE        +  where True = any(<generator object test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage.<locals>.<genexpr> at 0x7f6b7c55cee0>)[0m

[1m[31mtests/test_gate.py[0m:199: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage[0m - AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.05s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage` fails on base `main` too -- the bug is not already fixed upstream
```
ssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage[0m - AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-pa3nnw4j/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-pa3nnw4j/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 9ms[0m[0m

```

### 2026-08-27 19:18:47Z · plan-validation · session · session=005a6cad-b7df-4456-b126-89c16c56d0f1

`plan-validation` ran as session `005a6cad-b7df-4456-b126-89c16c56d0f1`
- replay: `claude --resume 005a6cad-b7df-4456-b126-89c16c56d0f1`
- log: `.project/logs/TICKET-074-plan-validation-005a6cad.log`

### 2026-08-27 19:18:47Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes judgment: all eight items scored ok; line numbers 7, 202, 227, 247, 304, 350-355 re-verified against main 06b1b42; three non-blocking notes in the thread

### 2026-08-27 19:19:11Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket and rejected its first plan for the stale shlex call site -- audit in thread). Verified: the call site is now format_test_cmd(cfg['test_suite_without_new'], test), matching gate.py:350 on main.

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket and rejected its first plan for the stale shlex call site -- audit in thread). Verified: the call site is now format_test_cmd(cfg['test_suite_without_new'], test), matching gate.py:350 on main.**

### 2026-08-27 19:21:53Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage` fails as required
```
xisting breakage[39;49;00m[33m"[39;49;00m [95min[39;49;00m f [94mfor[39;49;00m f [95min[39;49;00m failures), failures[90m[39;49;00m
[1m[31mE       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first[0m
[1m[31mE         *-- identical output, already quoted in the `## Thread` entry `2026-08-27 19:21:32Z · plan-validation · gate · verdict=FAIL` --*'][0m
[1m[31mE       assert not True[0m
[1m[31mE        +  where True = any(<generator object test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage.<locals>.<genexpr> at 0x7fa309d99490>)[0m

[1m[31mtests/test_gate.py[0m:229: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage[0m - AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.09s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage` fails on base `main` too -- the bug is not already fixed upstream
```
sertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage[0m - AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-3hqf252d/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-3hqf252d/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 19:21:54Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-28 · implementing · session

Todo, one entry per plan step:

1. [x] rebase onto main -- no-op, worktree was already on `06b1b42`
2. [x] watch the reproduction fail RED for the expected reason
3. [x] add `SUITE_FAILED_CODES`, `SUITE_RAN_RE`, `suite_ran()` to `pipeline/core/gate.py`
4. [x] replace the RED finding with the two-arm form using `suite_ran()`
5. [x] run `tests/test_gate.py tests/test_dispatch.py`, commit `e3c81a6`
6. [x] append the two `tests/test_gate.py` tests
7. [x] append the `suite_ran()` table test to `tests/test_dispatch.py`
8. [x] run both files green, commit `16e303f`
9. [x] update the three docs, commit `dc2cbd3`
10. [x] full suite + guard script, paste counts below

Step 1 was a no-op: the worktree's single commit (`e5acf54`) was already based
on `main` at `06b1b42`, matching the Digest's line numbers exactly, so no
rebase ran.

RED confirmed at step 2: `AssertionError: ['suite excluding
\`test_thing.py::test_broken\` is RED -- pre-existing breakage, fix that
first...']`, `assert not True` -- the expected pre-fix failure.

Step 5's combined run hit one failure outside this ticket's files,
`tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
(`AssertionError: expected serve() to exit after tick 1, got 2`). I confirmed
it is pre-existing and unrelated: stashed my diff (`git stash push -u`, entry
`3d9a3845`), reran the same test alone against unmodified `06b1b42`, same
failure, same message; restored the stash (`git stash apply` then `drop`), no
files lost. It also does not reproduce in the full-suite run at step 10 --
test-order dependent, not caused by this change.

Step 10: `uv run --group dev pytest -q` -> `392 passed in 19.06s`.
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`, 141 `ok`
lines (the plan's step 10 says 122; the guard's own table has grown since the
plan was written -- unrelated to this diff, not investigated further).

Three commits, as the plan specifies:
- `e3c81a6` fix(TICKET-074): report a suite command that never ran as could-not-run
- `16e303f` test(TICKET-074): pin the red-suite and could-not-run halves of suite_ran
- `dc2cbd3` docs(TICKET-074): a red suite must report a test result, not just a non-zero exit

### 2026-08-27 19:26:10Z · implementing · session · session=8e151fc6-53b1-4891-802b-0bd15aa3bdbe

`implementing` ran as session `8e151fc6-53b1-4891-802b-0bd15aa3bdbe`
- replay: `claude --resume 8e151fc6-53b1-4891-802b-0bd15aa3bdbe`
- log: `.project/logs/TICKET-074-implementing-8e151fc6.log`

### 2026-08-27 19:26:10Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented the plan's 10 steps as written; suite_ran() gates the RED verdict on evidence of a run; full suite 392 passed, guard all passed

### 2026-08-28 · review · session

**No blocking findings.** I reviewed the delta `main..HEAD` (`e5acf54`,
`e3c81a6`, `16e303f`, `dc2cbd3`; 6 files, +120/-6) against `## Plan` and
`## Acceptance criteria`. The code matches the plan's step 3 and step 4 blocks
byte-for-byte. `grep -n shlex pipeline/core/gate.py` prints nothing;
`format_test_cmd` still wraps `test_suite_without_new` at
`pipeline/core/gate.py:379`; `tests/test_gate.py` gained no import (DEC-017);
the new finding is absent from `STRUCTURAL_MARKS`, as `## Decisions` requires.

Verified on this machine:
- `uv run --group dev pytest -q` -> `392 passed in 19.06s`.
- `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`, 141 `ok`
  lines.
- The six criterion tests, run in one invocation -> `6 passed in 0.19s`.

Two non-blocking findings:

1. **Low.** `pipeline/templates/skills/pipeline-config/SKILL.md:29` still reads
   `Three traps behind that table:` above four bullets. Step 9 did not ask for
   the header change; `plan-validation` flagged the same line.
2. **Low.** The implementing entry scopes
   `tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
   to the combined run. It also fails alone: `uv run --group dev pytest -q
   tests/test_dispatch.py` -> `1 failed, 53 passed`, same
   `AssertionError: expected serve() to exit after tick 1, got 2`. Not caused by
   this diff: the test reads `pipeline/daemon/supervisor.py` mtimes, no file it
   reads differs from `main`, the added test sits at line 1341 below it, and
   deselecting all four added tests keeps the failure.

### 2026-08-27 19:30:12Z · review · session · session=a35235b8-6335-4af2-8682-1f8351bfc324

`review` ran as session `a35235b8-6335-4af2-8682-1f8351bfc324`
- replay: `claude --resume a35235b8-6335-4af2-8682-1f8351bfc324`
- log: `.project/logs/TICKET-074-review-a35235b8.log`

### 2026-08-27 19:30:12Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ delta matches the plan; 392 passed, guard all passed, 6 criterion tests pass; two low non-blocking findings

### 2026-08-27 19:30:32Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 19:30:33Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/074


Current branch ticket/074 is up to date.
Already up to date.
Updating 06b1b42..dc2cbd3
Fast-forward
 CLAUDE.md                                          |  5 ++-
 pipeline/core/gate.py                              | 43 ++++++++++++++++++--
 pipeline/templates/pipeline.toml                   |  4 +-
 pipeline/templates/skills/pipeline-config/SKILL.md |  7 +++-
 tests/test_dispatch.py                             | 21 ++++++++++
 tests/test_gate.py                                 | 46 ++++++++++++++++++++++
 6 files changed, 120 insertions(+), 6 deletions(-)

```

### 2026-08-27 19:30:33Z · merging · decision

decision recorded as `DEC-074`
