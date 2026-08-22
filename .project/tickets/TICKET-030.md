---
id: TICKET-030
stage: done
class: bugfix
branch: ticket/030
test_file: tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it
files_declared:
- pipeline/core/gate.py
- tests/test_gate.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 0a7c5ebf-38f7-4bf8-b105-ca88b916fcdd
  log: .project/logs/TICKET-030-review-0a7c5ebf.log
approved_by: chezzijr
approved_at: '2026-08-21T09:32:15.160672+00:00'
---

## Summary

Implemented: the Tier A gate now appends the rule that would fix a `## Plan`
finding, not just the offending line. `pipeline/core/gate.py` gained
`PLAN_STEP_RULE` and `PLAN_FILE_RULE` below `DEC_ID_RE`, appended to all four
findings in the `## Plan` step loop (prose, `plan line names no declared
file`, `` `## Plan` has zero numbered steps ``, `plan step names no declared
file`). `tests/test_gate.py` gained one `files_declared` assert in
`test_gate_blocks_a_plan_step_citing_an_undeclared_path`; the `indent` assert
was already committed as `c971b88` (the ticket earlier recorded this commit as
`1be5aa4`; the `revalidating` rebase rewrote the sha). No import of the new
constants was added to `tests/test_gate.py`, per DEC-017/DEC-018. Committed as
`3f87848`.

Reviewed: PASS, no blocking findings. The review read the delta `main...HEAD`
(`c971b88` and `3f87848`), confirmed all 13 plan steps landed as written, and
ran `uv run --group dev pytest -q` -- `195 passed in 8.83s`. Every acceptance
criterion holds. Three low-severity findings are recorded in `## Thread` and
none of them blocks: no test asserts the new text on two of the four findings,
`pipeline metrics` prints each finding about 120 characters wider, and
`PLAN_FILE_RULE` offers `pipeline/core/machine.py` as a literal example path.

Original report: `plan-validation` returned `plan line is not a numbered step
-- the plan reads as prose: '```python'` on TICKET-024, naming the failing
line but not the indentation rule that would have avoided it. See
`## Reproduction` for the failing test this fix now passes.

## Reproduction

Test: `tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it`

Command:

    uv run --group dev pytest -q "tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it"

The test puts a fenced code block under a numbered step in `## Plan`, then
asserts the resulting finding mentions indentation. It fails:

    E       AssertionError: ["plan line is not a numbered step -- the plan reads as prose: '```python'", "plan line is not a numbered step -- the plan reads as prose: 'x = 1'", "plan line is not a numbered step -- the plan reads as prose: '```'"]
    E       assert False

The first finding matches the TICKET-024 message in `## Summary` verbatim. No
finding names the rule.

expect: assert any("indent" in f.lower() for f in prose)

## Digest

- Files touched: `pipeline/core/gate.py` (the four `## Plan` findings) and `tests/test_gate.py` (one added assert; the failing test is already committed as `1be5aa4`).
- Key function: `gate()` in `pipeline/core/gate.py`, the `## Plan` step loop at lines 192-220. `re.match(r"^\s*\d+[.)]", line)` opens a step, `elif in_step and re.match(r"^\s+\S", line)` folds an indented line into the previous step, and the `else` branch emits the prose finding TICKET-024 hit.
- The four findings this ticket rewrites, all inside that block: prose (line 209), `plan line names no declared file` (line 213), `` `## Plan` has zero numbered steps `` (line 217), `plan step names no declared file` (line 220).
- The rule already exists as prose in `pipeline/stages/planning.md` lines 48-58: "the gate only recognizes a wrapped continuation if it is indented under the step it continues, and a plain unindented wrap reads as prose". Nothing copies it into the message.
- Entry points: `gate()` is called by the `plan-validation` path in `pipeline/daemon/supervisor.py` and by `pipeline gate` in `pipeline/cli/main.py`. Findings reach `## Thread` as `- {f}` markdown bullets, not inside a fence, so backticks in the new text cannot corrupt anything.
- Gotcha, load-bearing: `tests/test_gate.py` is copied whole onto a checkout of base and imported there (`pipeline/core/gate.py:_base_findings`). A name imported from `pipeline.core.gate` that exists only on the branch is an `ImportError` on base, which the gate reports as "errored rather than failed on base" -- blocking this ticket. Assert on literal substrings.
- Gotcha: no test asserts a full finding string. Three tests substring-match `"names no declared file"` (`tests/test_gate.py` lines 81, 89, 101) and one matches `"not a numbered step"` (line 268). Appending to the end of each message keeps all four green.
- The verdict split is `failed = [f for f in findings if not f.startswith("ok:")]`. None of the four messages carries an `ok:` prefix, so appending text cannot move a finding across that line.
- Measured before planning: the fenced block in the failing test emits six findings, two per line. This ticket makes each one actionable; it does not dedupe them.

## Decisions checked

Grepped `/home/chezzijr/proj/claude-setup/.project/decisions/` for `gate`, `finding`, `message`, `plan`, `prose`, `indent`.

- DEC-017 (active) -- binding on the test change. The gate copies `tests/test_gate.py` onto a checkout of base and imports it there, so that file may only import names base already has. This plan adds no import to it.
- DEC-018 (active) -- restates DEC-017's rule with the measured `ImportError`, and records that the `ok:` prefix is what excludes a finding from the verdict. This plan touches no `ok:` finding.
- DEC-024 (active) -- `planning: high` because a rejected plan costs a full re-run of the most expensive stage. That is the same cost this ticket attacks from the message side. Context, not a constraint on this code.
- No decision record governs finding text.

## Plan

1. Run `uv run --group dev pytest -q "tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it"` and confirm it fails on `assert any("indent" in f.lower() for f in prose)`; the test is already committed in `tests/test_gate.py`.
2. In `pipeline/core/gate.py`, directly below `DEC_ID_RE` (line 27), add a comment saying the next two constants paraphrase `## Plan` in `pipeline/stages/planning.md` and must be changed together.
3. In `pipeline/core/gate.py`, under that comment, add `PLAN_STEP_RULE = ("a step starts with `N.` or `N)`, and a line that continues a step must be indented under it -- an unindented line reads as prose")`.
4. In `pipeline/core/gate.py`, under `PLAN_STEP_RULE`, add `PLAN_FILE_RULE = ("spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`")`.
5. In `pipeline/core/gate.py`, append `f" -- {PLAN_STEP_RULE}"` to the prose finding in the `else` branch of the `## Plan` step loop (lines 209-211), leaving `{line.strip()!r}` exactly as it is.
6. In `pipeline/core/gate.py`, append `f" -- {PLAN_FILE_RULE}"` to the `plan line names no declared file` finding (lines 212-214).
7. In `pipeline/core/gate.py`, append `f" -- {PLAN_STEP_RULE}"` to the `` `## Plan` has zero numbered steps `` finding (line 217).
8. In `pipeline/core/gate.py`, append `f" -- {PLAN_FILE_RULE}"` to the `plan step names no declared file` finding (lines 219-220).
9. In `tests/test_gate.py`, add `assert any("files_declared" in f for f in failures), failures` as the last assert of `test_gate_blocks_a_plan_step_citing_an_undeclared_path` (lines 85-91), immediately before `shutil.rmtree(d)`.
10. Add no `import` and no `from ... import` line to `tests/test_gate.py`; assert on the literal substrings `indent` and `files_declared`, never on a constant imported from `pipeline.core.gate`.
11. Run `uv run --group dev pytest -q tests/test_gate.py` and confirm every test in `tests/test_gate.py` passes.
12. Run `uv run --group dev pytest -q` and confirm the full suite is green, since `pipeline/core/gate.py` is imported outside `tests/test_gate.py`.
13. Commit `pipeline/core/gate.py` and `tests/test_gate.py` together with `fix: a gate plan finding states the rule that would fix it`.

## Acceptance criteria

- `tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it` passes: the prose finding contains `indent`.
- `tests/test_gate.py::test_gate_blocks_a_plan_step_citing_an_undeclared_path` passes with its added assert: the finding contains `files_declared`.
- `tests/test_gate.py::test_gate_blocks_a_plan_of_prose` still passes: its `names no declared file` substring match survives the appended text.
- `tests/test_gate.py::test_gate_blocks_a_plan_step_whose_only_match_is_an_accidental_substring` still passes: `_cites()` is unchanged.
- `tests/test_gate.py::test_gate_passes_a_complete_ticket` still passes: a plan with no failing line emits none of the four rewritten findings.
- `uv run --group dev pytest -q` reports no failures across `tests/`.

## Decisions

**A Tier A `## Plan` finding states the rule that would fix it, not only the line that failed.**
The rule text lives in `pipeline/core/gate.py` as `PLAN_STEP_RULE` and `PLAN_FILE_RULE`, and it paraphrases `## Plan` in `pipeline/stages/planning.md`. TICKET-024 paid $3.60 for a re-plan and $2.11 for its re-validation because the message named the offending line and stopped; it came within one bounce of escalating. The gate is the code that just applied the rule, so it is the one place that can state it for free.

**The duplication with `planning.md` is deliberate. Do not deduplicate it.**
The obvious fix is to read the rule out of `pipeline/stages/planning.md` at gate time so there is one copy. That would make a deterministic Tier A check depend on prose an agent can edit, and it would give `pipeline/core/gate.py` a dependency on a stage prompt it has none on today. Keep the two copies and change them together; the comment above the constants says so.

**`tests/test_gate.py` asserts on the literal substrings `indent` and `files_declared`, never on `PLAN_STEP_RULE` imported from `pipeline.core.gate`.**
Importing the constant reads cleaner and breaks the gate. DEC-017 and DEC-018 record why: the gate copies `tests/test_gate.py` onto a checkout of base and imports it there, where a branch-only name does not exist. The result is `ImportError`, pytest exits non-zero with a collection error, the node name never appears in the output, and the gate reports "errored rather than failed on base" -- blocking the ticket that added the constant. Consequence: the rule text may be reworded freely, but the words `indent` and `files_declared` must survive in it.

**Not fixed here, deliberately: the fenced block in the failing test still emits six findings, two per line.**
Making each finding actionable was this ticket. Deduplicating repeated findings for one contiguous block is a separate change with its own risk of hiding a real second problem.

**Scope, deliberately narrow: only the four `## Plan` findings.**
`acceptance criterion names no test` has the same shape and is not touched. The ticket asked for the failures where the fix is mechanical and the rule is already written in `planning.md`; widening past that trades a small verified change for an unverified one.

## Rollback

Revert the single commit touching `pipeline/core/gate.py` and `tests/test_gate.py`. Nothing reads a finding string programmatically: findings are written into `## Thread` as markdown bullets by `Ticket.append()` and consumed by a human at the gate and by the next stage's prompt. Reverting restores the four old messages and re-reds `tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it`, which is the intended signal that the fix is gone.

## Thread

### 2026-08-21 09:06:59Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 · triage · reproduce · result=ok

Reproduced. `gate()` in `pipeline/core/gate.py` emits the prose finding in the
`else` branch of the `## Plan` step loop. The message quotes the line and stops.
It never states that an indented continuation under a step is accepted.

Test committed as `1be5aa4` on `ticket/030`:
`tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it`.

Out of scope for triage, for the next stage: the same fenced block also produces
one `plan line names no declared file` finding per line, with the same omission.

### 2026-08-21 09:15:46Z · triage · session · session=55280e4c-d409-450b-bb44-efb57e3d8fd4

`triage` ran as session `55280e4c-d409-450b-bb44-efb57e3d8fd4`
- replay: `claude --resume 55280e4c-d409-450b-bb44-efb57e3d8fd4`
- log: `.project/logs/TICKET-030-triage-55280e4c.log`

### 2026-08-21 09:15:46Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

✓ Reproduced: gate prose finding quotes the line, never states the indentation rule. Failing test committed 1be5aa4.

### 2026-08-21 · planning · plan · result=ok

Plan written. The fix appends a rule to each of the four `## Plan` findings in
`gate()` (`pipeline/core/gate.py`), sourced from two new module constants.

Triage's handover is covered: step 6 rewrites `plan line names no declared file`,
the sibling finding triage flagged as out of scope for its own stage.

Verified before writing the plan, not assumed:

1. The named test fails today, on `assert any("indent" in f.lower() for f in prose)`.
2. No test asserts a full finding string, so appending text breaks none of the
   four existing substring matches (`tests/test_gate.py` lines 81, 89, 101, 268).
3. None of the four messages carries an `ok:` prefix, so appending cannot move a
   finding across `failed = [f for f in findings if not f.startswith("ok:")]`.

Noted, not fixed, for whoever wants it later: `acceptance criterion names no
test` omits its rule the same way, and the fenced block in the failing test still
emits six findings for three lines. Both are separate tickets.

### 2026-08-21 09:25:46Z · planning · session · session=9d060f46-8cf3-43be-b127-543fe41fdaa4

`planning` ran as session `9d060f46-8cf3-43be-b127-543fe41fdaa4`
- replay: `claude --resume 9d060f46-8cf3-43be-b127-543fe41fdaa4`
- log: `.project/logs/TICKET-030-planning-9d060f46.log`

### 2026-08-21 09:25:47Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

✓ Plan written: two rule constants in gate.py appended to all four `## Plan` findings; 13 steps, all Tier A parsers self-checked green.

### 2026-08-21 09:25:57Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it` fails as required
```
 the failure."""
        fence = "```"
        d = project(FIXTURE.replace(
            "## Plan\n1. fix thing.py\n",
            "## Plan\n1. fix thing.py\n%spython\nx = 1\n%s\n" % (fence, fence)))
        ok, failures = gate(d, "TICKET-001")
        assert not ok
        prose = [f for f in failures if "not a numbered step" in f]
        assert prose, failures
>       assert any("indent" in f.lower() for f in prose), prose
E       AssertionError: ["plan line is not a numbered step -- the plan reads as prose: '```python'", "plan line is not a numbered step -- the plan reads as prose: 'x = 1'", "plan line is not a numbered step -- the plan reads as prose: '```'"]
E       assert False
E        +  where False = any(<generator object test_a_prose_finding_states_the_rule_that_would_fix_it.<locals>.<genexpr> at 0x7f63a0ec45f0>)

tests/test_gate.py:270: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it` fails on base `main` too -- the bug is not already fixed upstream
```
s not a numbered step -- the plan reads as prose: 'x = 1'", "plan line is not a numbered step -- the plan reads as prose: '```'"]
E       assert False
E        +  where False = any(<generator object test_a_prose_finding_states_the_rule_that_would_fix_it.<locals>.<genexpr> at 0x7f6504d83920>)

tests/test_gate.py:270: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-y1kfg1bm/base
      Built pipeline @ file:///tmp/pipeline-base-y1kfg1bm/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-21 · plan-validation · validate · result=ok

Plan accepted. Eight items scored below; every line number and claim in the
plan was checked against the code, not taken from the ticket.

1. **Root cause.** `gate()` applies the step-parsing rule and reports only the
   line that broke it. The rule itself lives in `pipeline/stages/planning.md`
   lines 48-58 and never reaches the agent. The plan appends the rule at the
   point of application, to all four `## Plan` findings, so it fixes the
   omission and not only the one finding the test reads.
2. **Decision conflict.** DEC-017 and DEC-018 bind the test change: a name
   imported from `pipeline.core.gate` that exists only on the branch is an
   `ImportError` on base. Plan step 10 forbids the import and step 9 asserts
   the literal `files_declared`. Complies; supersedes nothing. DEC-024 is
   context.
3. **Scope.** Two files, 13 steps, one commit -- steps 2-8 in
   `pipeline/core/gate.py`, steps 9-10 in `tests/test_gate.py`, steps 1/11/12
   verification, step 13 commit. No step touches `acceptance criterion names
   no test`.
4. **Falsifiable criteria.** Criterion 1 fails today, on
   `assert any("indent" in f.lower() for f in prose)`. Criterion 2's new assert
   fails if step 8 is skipped, because
   `test_gate_blocks_a_plan_step_citing_an_undeclared_path` hits the step
   finding at `pipeline/core/gate.py:220`. Criteria 3-5 are regression guards.
   None is vacuous.
5. **No research left.** Every step names the file, the constant, the line
   range and the exact text to insert. I confirmed the four target lines: prose
   209-211, `plan line names no declared file` 212-214, `` `## Plan` has zero
   numbered steps `` 217, `plan step names no declared file` 219-220, and
   `DEC_ID_RE` at 27.
6. **Riskiest step: 9**, the edit to `tests/test_gate.py`, because that file is
   copied onto a checkout of base and imported there. Its fallback is step 10:
   assert on literal substrings, add no import. `## Rollback` gives the second
   fallback -- revert one commit.
7. **Regression surface.** Findings are consumed in three places, all checked:
   four substring matches in `tests/test_gate.py` (lines 81, 89, 101, 268),
   which appended text cannot break; `failed = [f for f in findings if not
   f.startswith("ok:")]` at `pipeline/core/gate.py:228`, which reads a prefix,
   not a suffix; and `"\n".join(f"- {f}" for f in findings)` at line 231, which
   renders bullets outside a fence, so the single backticks in the new
   constants are inline code. Criteria 3-6 cover it.
8. **Blast radius matches `bugfix`.** Two files, one commit.

Two gaps, named rather than bounced. Neither blocks implementation.

1. Steps 6 and 7 add text that no acceptance criterion asserts. Step 6 appends
   to `plan line names no declared file`; the test that reaches that finding,
   `test_gate_blocks_a_plan_of_prose`, matches only `names no declared file`.
   Step 7 appends to `` `## Plan` has zero numbered steps ``, which no test
   reaches. An implementation that skips either step still passes every
   criterion. Review must read the diff for both.
2. Step 9 cites `tests/test_gate.py` lines 85-91 for
   `test_gate_blocks_a_plan_step_citing_an_undeclared_path`; the function is
   lines 85-90. The anchor in the step -- the last assert, immediately before
   `shutil.rmtree(d)` -- is unambiguous.

The plan's own three verified claims hold. I re-checked claim 2 directly: the
four substring matches are at `tests/test_gate.py` lines 81, 89, 101, 268, and
each matches a prefix of its message.

### 2026-08-21 09:28:26Z · plan-validation · session · session=3975415c-cd2b-4071-8e85-f2003a803a11

`plan-validation` ran as session `3975415c-cd2b-4071-8e85-f2003a803a11`
- replay: `claude --resume 3975415c-cd2b-4071-8e85-f2003a803a11`
- log: `.project/logs/TICKET-030-plan-validation-3975415c.log`

### 2026-08-21 09:28:26Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan accepted: all eight items pass; two gaps named for review -- steps 6 and 7 have no criterion asserting their new text, and step 9 cites lines 85-91 for a function at 85-90.

### 2026-08-21 09:32:15Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 09:39:40Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it` fails as required
```
 the failure."""
        fence = "```"
        d = project(FIXTURE.replace(
            "## Plan\n1. fix thing.py\n",
            "## Plan\n1. fix thing.py\n%spython\nx = 1\n%s\n" % (fence, fence)))
        ok, failures = gate(d, "TICKET-001")
        assert not ok
        prose = [f for f in failures if "not a numbered step" in f]
        assert prose, failures
>       assert any("indent" in f.lower() for f in prose), prose
E       AssertionError: ["plan line is not a numbered step -- the plan reads as prose: '```python'", "plan line is not a numbered step -- the plan reads as prose: 'x = 1'", "plan line is not a numbered step -- the plan reads as prose: '```'"]
E       assert False
E        +  where False = any(<generator object test_a_prose_finding_states_the_rule_that_would_fix_it.<locals>.<genexpr> at 0x7efe94bd0d40>)

tests/test_gate.py:270: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it` fails on base `main` too -- the bug is not already fixed upstream
```
s not a numbered step -- the plan reads as prose: 'x = 1'", "plan line is not a numbered step -- the plan reads as prose: '```'"]
E       assert False
E        +  where False = any(<generator object test_a_prose_finding_states_the_rule_that_would_fix_it.<locals>.<genexpr> at 0x7f0afd6b7920>)

tests/test_gate.py:270: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_prose_finding_states_the_rule_that_would_fix_it
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-vsirptmh/base
      Built pipeline @ file:///tmp/pipeline-base-vsirptmh/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-21 09:39:40Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 · implementing · progress

Todo, one entry per plan step:

1. [x] Confirm `test_a_prose_finding_states_the_rule_that_would_fix_it` fails on the `indent` assert.
2. [x] Add comment above `PLAN_STEP_RULE`/`PLAN_FILE_RULE` in `pipeline/core/gate.py`.
3. [x] Add `PLAN_STEP_RULE`.
4. [x] Add `PLAN_FILE_RULE`.
5. [x] Append `PLAN_STEP_RULE` to the prose finding.
6. [x] Append `PLAN_FILE_RULE` to `plan line names no declared file`.
7. [x] Append `PLAN_STEP_RULE` to `` `## Plan` has zero numbered steps ``.
8. [x] Append `PLAN_FILE_RULE` to `plan step names no declared file`.
9. [x] Add `files_declared` assert to `test_gate_blocks_a_plan_step_citing_an_undeclared_path`.
10. [x] No import added to `tests/test_gate.py`; asserted on literal substrings.
11. [x] `uv run --group dev pytest -q tests/test_gate.py` -- 19 passed.
12. [x] `uv run --group dev pytest -q` -- 195 passed.
13. [x] Committed `pipeline/core/gate.py` and `tests/test_gate.py` as `3f87848`.

### 2026-08-21 · implementing · transition · to=(dispatcher decides) · result=ok

**implementing -> ?** (result: `ok`)

✓ Plan executed as written, all 13 steps done. Full suite green (195 passed), target test passes. Committed `3f87848`.

### 2026-08-21 09:40:58Z · implementing · session · session=8813ef5e-dc11-40b2-84b7-564ee99d0cd9

`implementing` ran as session `8813ef5e-dc11-40b2-84b7-564ee99d0cd9`
- replay: `claude --resume 8813ef5e-dc11-40b2-84b7-564ee99d0cd9`
- log: `.project/logs/TICKET-030-implementing-8813ef5e.log`

### 2026-08-21 09:40:58Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed plan as written: added PLAN_STEP_RULE/PLAN_FILE_RULE to gate.py, appended to all four ## Plan findings, added files_declared assert to test_gate.py; full suite 195 passed; committed 3f87848.

### 2026-08-21 · review · findings · result=ok

**review: PASS** -- no blocking findings. Reviewed the delta `main...HEAD`, two
commits: `c971b88` (the failing test) and `3f87848` (the fix). This is the
first review pass; `## Thread` holds no earlier review entry.

Every acceptance criterion holds. `uv run --group dev pytest -q` reports
`195 passed in 8.83s`. The five named tests run green together:
`test_a_prose_finding_states_the_rule_that_would_fix_it`,
`test_gate_blocks_a_plan_step_citing_an_undeclared_path`,
`test_gate_blocks_a_plan_of_prose`,
`test_gate_blocks_a_plan_step_whose_only_match_is_an_accidental_substring`,
`test_gate_passes_a_complete_ticket` -- `5 passed in 0.04s`.

Checked against the plan: all 13 steps landed as written. `PLAN_STEP_RULE` and
`PLAN_FILE_RULE` match the plan's text character for character; the comment
above them names `pipeline/stages/planning.md` and the change-together rule.
All four `## Plan` findings append the rule at the end of the message, so the
three `names no declared file` substring matches (`tests/test_gate.py` lines
81, 89, 102) and the `not a numbered step` match (line 269) still hold.

Checked against DEC-017 and DEC-018: `tests/test_gate.py` gained no `import`
and no `from ... import` line. The new test asserts the literal substrings
`indent` and `files_declared`. The `plan-validation` gate at 09:39:40Z already
ran this file on base and got an `AssertionError`, not an `ImportError`.

Checked the backtick risk. `PLAN_STEP_RULE` and `PLAN_FILE_RULE` contain
backticks, and the comment at `pipeline/core/gate.py:216-217` warns about a
finding's fence. The four rewritten findings carry no fence: `gate()` renders
them as `- {f}` bullets (`pipeline/core/gate.py:243`,
`pipeline/daemon/supervisor.py:558` and `:631`). Only the `ok:` finding at
`pipeline/core/gate.py:162` opens a fence, and this delta does not touch it.
Backticks in a markdown bullet are inline code.

Checked the verdict split. `failed = [f for f in findings if not
f.startswith("ok:")]` (`pipeline/core/gate.py:240`) reads the start of each
message; all four changes append to the end.

Non-blocking findings:

1. Low -- steps 6 and 7 of the plan have no test asserting their new text. The
   findings `plan line names no declared file` and `## Plan has zero numbered
   steps` now carry a rule, and nothing asserts it. `plan-validation` named
   this gap at 09:28:26Z and the human approved anyway. No test asserts on
   `zero numbered steps` at all; that gap predates this ticket.
2. Low -- `pipeline metrics` prints one finding per line untruncated
   (`pipeline/cli/metrics.py:442`), and each of the four findings grew by
   roughly 120 characters. `gate_failure_reasons()` groups by the whole
   finding string (`pipeline/cli/metrics.py:276`), and the prose findings
   already differ per line because they embed `repr(line)`, so grouping counts
   do not change. Only the printed width does.
3. Low -- `PLAN_FILE_RULE` puts the literal path `pipeline/core/machine.py`
   into a message that reaches the next stage's prompt as an example. A
   planning agent could copy the example path into a plan. Speculative; no
   evidence it has happened.

### 2026-08-21 09:43:20Z · review · session · session=0a7c5ebf-38f7-4bf8-b105-ca88b916fcdd

`review` ran as session `0a7c5ebf-38f7-4bf8-b105-ca88b916fcdd`
- replay: `claude --resume 0a7c5ebf-38f7-4bf8-b105-ca88b916fcdd`
- log: `.project/logs/TICKET-030-review-0a7c5ebf.log`

### 2026-08-21 09:43:20Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Review PASS on delta main...HEAD (c971b88, 3f87848): all 13 plan steps landed, every acceptance criterion holds, 195 passed in 8.83s; three low findings recorded, none blocking.

### 2026-08-21 09:43:29Z · verifying · transition · to=merging · result=ok

**verifying -> merging** (result: `ok`)

regression suite exit 0
```
...HEAD
ok  allow [always] cargo build --release
ok  BLOCK [readonly] sed -i s/a/b/ x.py
ok  BLOCK [readonly] echo hi > file.txt
ok  BLOCK [readonly] git commit -am wip
ok  BLOCK [readonly] cp a b
ok  BLOCK [readonly] pip install requests
ok  BLOCK [readonly] mv a b
ok  BLOCK [readonly] python3 -c "open('/tmp/x','a').write(1)"
ok  BLOCK [readonly] git -C . commit -am wip
ok  BLOCK [readonly] pytest 2>out
ok  BLOCK [readonly] pytest >> log.txt
ok  BLOCK [readonly] git worktree add /tmp/x main
ok  BLOCK [readonly] python3 setup.py install
ok  BLOCK [readonly] tee /tmp/x
ok  BLOCK [readonly] curl https://example.com -o /tmp/x
ok  BLOCK [readonly] make install
ok  BLOCK [readonly] cargo run
ok  BLOCK [readonly] npm install
ok  BLOCK [readonly] echo $(whoami)
ok  allow [readonly] pytest -x
ok  allow [readonly] git diff main...HEAD
ok  allow [readonly] grep -rn foo .
ok  allow [readonly] git log --oneline
ok  allow [readonly] cat thing.py
ok  allow [readonly] python3 -m pytest --deselect x
ok  allow [readonly] ls -la
ok  allow [readonly] git show HEAD
ok  allow [readonly] git blame thing.py
ok  allow [readonly] rg evict src/
ok  allow [readonly] pytest -x 2>&1
ok  allow [readonly] find . -name '*.py'
ok  allow [readonly] cargo test
ok  allow [readonly] go test ./...
ok  allow [readonly] git status --porcelain
ok  allow [readonly] wc -l thing.py
ok  allow [readonly] python3 -m unittest
ok  allow [readonly] git diff main...HEAD | head -50
ok  end-to-end exit codes

guard: all passed

```

### 2026-08-21 09:43:30Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/030


Already up to date.
Updating 6adabcc..3f87848
Fast-forward
 pipeline/core/gate.py | 20 ++++++++++++++++----
 tests/test_gate.py    | 18 ++++++++++++++++++
 2 files changed, 34 insertions(+), 4 deletions(-)

```

### 2026-08-21 09:43:30Z · merging · decision

decision recorded as `DEC-030`
