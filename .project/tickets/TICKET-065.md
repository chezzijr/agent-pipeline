---
id: TICKET-065
stage: done
class: bugfix
branch: ticket/065
test_file: tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt
files_declared:
- pipeline/core/gate.py
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- pipeline/stages/plan-validation.md
- tests/test_machine.py
- tests/test_dispatch.py
- README.md
- CLAUDE.md
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 10
  plan_files: 8
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: f9f1d875-186e-41de-abdf-5a7fcb34cba8
  log: .project/logs/TICKET-065-review-f9f1d875.log
approved_by: chezzijr (via Claude Code, on explicit instruction)
approved_at: '2026-08-27T15:00:17.642520+00:00'
---

## Summary

structural gate failures charge a plan-validation attempt

`transition()` charges `plan_validation_attempts` for every Tier A gate
failure (`pipeline/core/machine.py:119`), including failures where the gate
never read the plan's content. Two prose lines above step 1 fail
`PLAN_STEP_RULE`, the gate stops, and the ticket goes back to `planning` one
attempt poorer -- with no judgement of the plan it was carrying.

The fix splits the gate's verdict in two. `("plan-validation", "bad-plan")`
charges `plan_validation_attempts` exactly as today; `("plan-validation",
"fail")` charges a new `structural_gate_failures`, out of `BOUNDS` and
`SIZE_SCALED`, the same shape as `stale_regate`. `structural_only()` in
`pipeline/core/gate.py` classifies findings by a `startswith` prefix
allowlist, `gate_result()` in `pipeline/daemon/supervisor.py` picks the result
string, and `_finish()` remaps a Tier B agent's `fail` to `bad-plan`.

Ten steps, eight files. plan-validation approved this plan on 2026-08-27: all
eight items pass. The first plan failed one item, regression surface, because
step 8 turned
`tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`
red; step 3 repoints that test at `("plan-validation", "bad-plan")` and keeps
DEC-047's size scaling under test.

Implementing took the plan as written: all ten steps, five commits,
`f5cc72b..aec872a`. One precision note from plan-validation, recorded and not a
blocker: the `STRUCTURAL_MARKS` prefix "`## Decisions checked` cites" also
matches the unresolvable-citation finding at `gate.py:297`, so that finding
charges `structural_gate_failures`. Both counters bound at 2, so planning still
stops at four runs.

**Reviewed on 2026-08-27: no blocking findings.** `uv run --group dev pytest -q`
-- `349 passed in 17.20s`. `./pipeline/hooks/test_dangerous_commands.py` --
`guard: all passed`, exit 0. The ten tests the acceptance criteria name pass as
one selection: `10 passed`. `README.md:386` and `CLAUDE.md:245` document the
counter. Review refuted three candidate findings: no unclassified emitter of
`("plan-validation", "fail")` exists, `gate_result()` never returns `bad-plan`
at `revalidating`, and every mark matches a finding `gate()` writes. Three low
findings stand and block nothing; they are in the review thread entry.

## Reproduction

`tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt`

Run: `uv run --group dev pytest -q tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt`

The test builds a plan with one prose line ahead of the numbered step (citing
the declared file, so the only Tier A finding is the structural one), runs
`gate()`, confirms every real finding is `"is not a numbered step"`, then
calls `transition("plan-validation", "fail", {})` and asserts
`plan_validation_attempts` stays 0.

expect: AssertionError: a structural-only gate failure charged plan_validation_attempts: {'plan_validation_attempts': 1}

```
E       AssertionError: a structural-only gate failure charged plan_validation_attempts: {'plan_validation_attempts': 1}
E       assert 1 == 0
```

## Digest

**How this plan differs from the one plan-validation rejected on 2026-08-27.**
The design is unchanged; seven of eight items passed. The rejected plan turned
`tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`
(line 229) red at step 8, because that test drives `("plan-validation",
"fail")` twice and asserts `huge_next != "escalated"` and
`huge["plan_validation_attempts"] == 5` -- the size-scaled bound
`structural_gate_failures` does not have. Step 3 of this plan repoints that
test at `("plan-validation", "bad-plan")`, in the same step that adds the
`bad-plan` row, so the test is green before step 8 and after it, and DEC-047's
size scaling stays under test.

Files touched: `pipeline/core/gate.py` (the classifier), `pipeline/core/machine.py`
(two `transition()` rows), `pipeline/daemon/supervisor.py` (`gate_result()`,
`finish_gate()`, `_finish()`), `pipeline/stages/plan-validation.md`,
`tests/test_machine.py`, `tests/test_dispatch.py`, `README.md`, `CLAUDE.md`.

Key functions:
- `gate()` (`pipeline/core/gate.py:164`) returns `(passed, failures)`. `failures`
  is every finding that does not start with `ok:` (`gate.py:394`).
- `finish_gate()` (`pipeline/daemon/supervisor.py:889`) calls
  `advance(project, t, "ok" if ok else "fail", note, emit, agent=False)` at
  `supervisor.py:909` and returns the same string.
- `_finish()` ends with `result = res.get("result", "fail")`
  (`supervisor.py:1076`); `stage` is bound at `supervisor.py:1012`. That is the
  Tier B agent path.
- `advance()` (`supervisor.py:105`) is the only caller of `transition()`. It
  seeds `plan_steps`/`plan_files` into `counters` before transitioning, and
  names the charged counter in the `escalated` event's reason.

Entry points: the gate runs as a spawned child. `gate_cmd()` runs
`pipeline gate --findings <json>` (`pipeline/cli/main.py::cmd_gate`), and
`read_findings()` hands the JSON to `finish_gate()`. `finish_regate()` also ends
in `finish_gate()`, with `t.stage == "revalidating"`.

Gotchas:
- Findings cross a process boundary as JSON strings (`{"ok", "findings"}`), so
  the classifier reads strings. `gate()` must keep returning a 2-tuple: a
  3-tuple would make the branch's own `tests/test_gate.py` unpack three values
  on the checkout of base, where `gate()` still returns two (DEC-017).
- Every structural finding is one line with a fixed opener. Every substantive
  one carries a fenced block of captured output that can contain any string,
  and the "does not mention the expected string" finding (`gate.py:233`) puts a
  repr of `expect:` on its own first line. Match with `str.startswith`, never
  substring.
- `_dedupe()` (`gate.py:393`) rewrites only a repeated fence body, never a
  finding's first line, so the classifier reads the same opener the gate wrote.
- `tests/test_gate.py` is copied onto a checkout of base and imported there, so
  it must not import `structural_only`. Those tests go in `tests/test_dispatch.py`.
- `transition` is in `machine.FENCED`, so this ticket parks at `awaiting-merge`
  for a human instead of merging itself.
- `("revalidating", "fail")` must keep receiving `fail`: `("revalidating",
  "bad-plan")` is an unknown pair and escalates.
- The findings `read_findings()` synthesises for a crashed gate child
  ("gate child exit ...") are not in the allowlist, so they stay substantive.
  DEC-061 wants that path to fail closed.
- Three tests drive a real gate child on `FIXTURE`, whose `test_file` does not
  exist in the checkout. "test file ... does not exist" (`gate.py:214`) is
  substantive, so all three keep charging `plan_validation_attempts` and need no
  edit: `tests/test_dispatch.py::test_a_failing_gate_child_sends_the_ticket_back_to_planning`
  (line 1244), `tests/test_dispatch.py::test_a_bound_escalation_emits_an_escalated_event`
  (line 463, which asserts the escalation reason names `plan_validation_attempts`
  and the bound `2`), and the gate cases in `tests/test_gate.py`.
- `tests/test_dispatch.py::test_a_stale_plan_is_re_gated_on_approval` (line 388)
  asserts `plan_validation_attempts == 0` and `stale_regate == 1` on the
  `revalidating` path. `gate_result()` returns `fail` there, so it is unaffected.
- `tests/test_cli.py` charges `plan_validation_attempts` only through
  `pipeline resume --grant/--reset` and `pipeline reject`; neither calls
  `transition("plan-validation", ...)`.

## Decisions checked

- DEC-047 -- `BOUNDS`, `SIZE_SCALED` and `bound_for()`. Only
  `plan_validation_attempts` scales, because a Tier A finding is raised per plan
  step. `structural_gate_failures` stays out of both and takes `MAX_ATTEMPTS`
  (2). This plan complies, and step 3 keeps the size scaling under test by
  repointing `test_plan_validation_budget_ignores_the_plans_size` at the pair
  that still carries it.
- DEC-061 -- the gate runs as a spawned child, a PASS is a phase carried in
  `counters["gate_ok"]`, and a missing or contradictory findings file is a
  FAILED gate. This plan adds no stage and no `stage_end`, and leaves
  `read_findings()`'s fail-closed findings substantive.
- DEC-030, DEC-017, DEC-018 -- `tests/test_gate.py` is copied onto base and
  imported there, so it may gain no import. This is why the classifier's tests
  go in `tests/test_dispatch.py`.
- DEC-029 -- `("revalidating", "fail")` charges `stale_regate`, never
  `plan_validation_attempts`. Untouched: `gate_result()` splits the verdict only
  at `plan-validation`.
- DEC-046 -- `gate()` replaces a repeated fence with a reference line. It never
  rewrites a finding's first line, which is what the classifier reads.
- DEC-051 -- `pipeline resume --grant/--reset` take any counter name, so
  `structural_gate_failures` needs no registration.

Grep terms used in `.project/decisions/`: `plan_validation_attempts`, `Tier A`,
`counter`, `finish_gate`, `gate(`, `superseded-by`.

## Plan

1. Add the classifier to `pipeline/core/gate.py`: a module constant `STRUCTURAL_MARKS` and `def structural_only(failures: list[str]) -> bool`, under `PLAN_STEP_RE`. `STRUCTURAL_MARKS` is the tuple of the ten prefixes that open a structural finding: "section `## ", "`## Digest` has ", "`## Reproduction` has no `expect:` line", "`## Decisions checked` cites", "`files_declared` is empty", "`## Plan` has zero numbered steps", "plan line is not a numbered step", "plan line names no declared file", "plan step names no declared file", "acceptance criterion names no test". `structural_only` returns `bool(failures) and all(f.startswith(STRUCTURAL_MARKS) for f in failures)`; empty is False, because no findings is a PASS and not this function's question. Comment it as an allowlist: an unlisted finding reads as substantive, which is what every finding did before this ticket, and `startswith` rather than `in` is what stops captured test output inside a fenced block from faking a structural verdict.
2. Test step 1 in `tests/test_dispatch.py`, never in `tests/test_gate.py` (DEC-017): add `test_structural_only_classifies_a_gate_finding`, importing `structural_only` from `pipeline.core.gate`. Assert True for a one-item list holding the finding that opens "plan line is not a numbered step -- the plan reads as prose:"; False for a one-item list holding a finding that opens "`t.py::x` PASSES -- it must fail before implementation" and carries a fenced block whose body line is "plan line is not a numbered step"; False for a two-item list holding both; False for `[]`; and False for a one-item list holding "gate child exit 2 left no readable findings (JSONDecodeError: x)". Run `uv run --group dev pytest -q tests/test_dispatch.py -k structural_only`, expect `1 passed`, and commit.
3. Add the substantive row to `pipeline/core/machine.py`: `case ("plan-validation", "bad-plan"): return charge("plan_validation_attempts", "planning")`, immediately after the existing `("plan-validation", "fail")` row, which this step leaves alone. Comment it as the verdict the gate reached by judging the plan's content: the test passes already, the suite is red, base is already fixed, or the Tier B agent rejected the plan. Then repoint two tests in `tests/test_machine.py` at the new pair, so the size-scaled bound stays tested when step 8 moves `fail` off it: in `test_plan_validation_budget_ignores_the_plans_size` (line 229) change all three `M.transition("plan-validation", "fail", ...)` calls (lines 238, 239, 246) to `"bad-plan"`, leaving every assertion as it is; and in `test_bounds_escalate_on_the_second_failure` add the row `("plan-validation", "bad-plan", "plan_validation_attempts")` to the table, keeping its existing `("plan-validation", "fail", ...)` row. Run `uv run --group dev pytest -q tests/test_machine.py`, expect all passed, and commit. Nothing emits `bad-plan` outside the tests yet, so dispatcher behaviour is unchanged.
4. Wire the gate's verdict in `pipeline/daemon/supervisor.py`: change line 22 to `from pipeline.core.gate import gate, plan_steps, structural_only`, and add `def gate_result(ok: bool, failures: list[str], stage: str) -> str` directly above `finish_gate()`. It returns "ok" when `ok`; "bad-plan" when `stage == "plan-validation" and not structural_only(failures)`; "fail" otherwise. Replace `finish_gate()`'s `advance(project, t, "ok" if ok else "fail", note, emit, agent=False)` and its `return "ok" if ok else "fail"` with `res = gate_result(ok, failures, t.stage)`, then `advance(project, t, res, note, emit, agent=False)`, then `return res`. Give `gate_result()` a docstring saying only `plan-validation` splits the verdict, because `("revalidating", "bad-plan")` is an unknown pair that would escalate a stale plan instead of charging `stale_regate`.
5. Test step 4 in `tests/test_dispatch.py`: add `test_a_gate_verdict_picks_its_result_string`, asserting `supervisor.gate_result(True, [], "plan-validation") == "ok"`, `supervisor.gate_result(False, ["`files_declared` is empty"], "plan-validation") == "fail"`, `supervisor.gate_result(False, ["test file /x/test_thing.py does not exist"], "plan-validation") == "bad-plan"`, and `supervisor.gate_result(False, ["`files_declared` is empty"], "revalidating") == "fail"`, with the revalidating reason in the docstring. Run `uv run --group dev pytest -q tests/test_dispatch.py`, expect all passed, and commit.
6. Remap the Tier B agent's claim in `pipeline/daemon/supervisor.py`, in `_finish()`: after `result = res.get("result", "fail")` (line 1076), add `if stage == "plan-validation" and result == "fail": result = "bad-plan"`. Comment it: Tier B judges the plan's content and has no structural half, so its `fail` is a bad plan by definition, and the dispatcher classifies rather than the prompt, because a stage that could pick `fail` over `bad-plan` would be choosing its own budget (invariant 1). In `pipeline/stages/plan-validation.md`, extend the last line to read: `result`: `ok` (all items pass) | `fail` (append per-item findings first; the dispatcher records it as `bad-plan`).
7. Test step 6 in `tests/test_dispatch.py`: add `test_a_tier_b_rejection_charges_the_plan_not_the_structural_counter`, built like `test_an_agent_that_rewrote_stage_is_still_caught` at line 103 -- `d = project()`, write a two-line sidecar to `T.result_file(d, "TICKET-001")` whose first line is `result: fail` and whose second is `summary: the plan skips the migration`, then call `supervisor.finish(d, rec)` with that test's hand-built `rec` dict and `"stage": "plan-validation"`. Assert the reloaded ticket's stage is `planning`, `t.counters["plan_validation_attempts"] == 1`, and `"structural_gate_failures" not in t.counters`. Run `uv run --group dev pytest -q tests/test_dispatch.py`, expect all passed, and commit.
8. Flip the structural row in `pipeline/core/machine.py` to `case ("plan-validation", "fail"): return charge("structural_gate_failures", "planning")`. Comment it with the argument this ticket rests on: the findings are all structural, the gate stopped before judging the plan, and charging `plan_validation_attempts` spends a budget meant for bad plans on formatting. Record that the counter stays out of `BOUNDS` (formatting is not a property of the ticket's class) and out of `SIZE_SCALED` (a longer plan does not earn more tries at the same typo), the same shape as `stale_regate`.
9. Test step 8: in `tests/test_machine.py`, replace the `("plan-validation", "fail", "plan_validation_attempts")` row of `test_bounds_escalate_on_the_second_failure` with `("plan-validation", "fail", "structural_gate_failures")`, keeping the `bad-plan` row step 3 added, and add `test_a_structural_gate_failure_charges_its_own_counter` asserting that `t("plan-validation", "fail")` returns `planning` with `structural_gate_failures == 1` and no `plan_validation_attempts` key, that a second `fail` returns `escalated`, that `t("plan-validation", "bad-plan")` charges `plan_validation_attempts` and writes no `structural_gate_failures`, and that "structural_gate_failures" is in neither `M.SIZE_SCALED` nor any value of `M.BOUNDS`. In `tests/test_dispatch.py`, change `test_advance_seeds_the_plan_size_from_the_ticket` (line 743) to call `supervisor.advance(d, t, "bad-plan", "n", agent=False)`, so it still exercises the size-scaled counter it was written for. Run `uv run --group dev pytest -q tests/test_machine.py tests/test_dispatch.py tests/test_gate.py`, expect all passed including the reproduction, and commit.
10. Document the counter in `README.md` and `CLAUDE.md`. In `README.md`, after the paragraph ending "`lease_expiries` and `no_result` are the dispatcher's own counters and stay at 2 whatever the class." (line 382), add a paragraph: a Tier A failure whose findings are all structural -- a missing section, a plan line that is not a numbered step, a step citing no declared file -- charges `structural_gate_failures` instead, because `plan_validation_attempts` bounds bad plans and the gate never judged that plan. In `CLAUDE.md`, add one bullet to the gotchas list directly under the "The Tier A gate runs as a spawned child" bullet (line 233), naming `gate_result()`, `structural_only()`'s prefix allowlist, and that an unlisted finding reads as substantive on purpose. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect both green, and commit.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt`
  passes: `gate()` returns only "is not a numbered step" findings, and
  `transition("plan-validation", "fail", {})` leaves `plan_validation_attempts` at 0.
- `tests/test_machine.py::test_a_structural_gate_failure_charges_its_own_counter`
  passes: `fail` charges `structural_gate_failures` to 1 and returns `planning`,
  a second `fail` returns `escalated`, `bad-plan` charges only
  `plan_validation_attempts`, and `structural_gate_failures` is in neither
  `SIZE_SCALED` nor `BOUNDS`.
- `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`
  passes on `("plan-validation", "bad-plan")`, with its existing assertions
  `huge_next != "escalated"` and `huge["plan_validation_attempts"] == 5`
  unchanged: DEC-047's size scaling is still under test after step 8.
- `tests/test_machine.py::test_bounds_escalate_on_the_second_failure` passes with
  rows for both `("plan-validation", "fail", "structural_gate_failures")` and
  `("plan-validation", "bad-plan", "plan_validation_attempts")`.
- `tests/test_dispatch.py::test_structural_only_classifies_a_gate_finding` passes,
  including the case where a substantive finding's fenced output quotes a
  structural finding's text verbatim.
- `tests/test_dispatch.py::test_a_gate_verdict_picks_its_result_string` passes for
  all four cases, including `revalidating` never returning `bad-plan`.
- `tests/test_dispatch.py::test_a_tier_b_rejection_charges_the_plan_not_the_structural_counter`
  passes: an agent sidecar of `result: fail` at `plan-validation` leaves
  `plan_validation_attempts` at 1 and writes no `structural_gate_failures`.
- `tests/test_dispatch.py::test_a_failing_gate_child_sends_the_ticket_back_to_planning`
  and `tests/test_dispatch.py::test_a_bound_escalation_emits_an_escalated_event`
  pass unedited: their missing `test_thing.py` is a substantive finding, so the
  first still charges `plan_validation_attempts` to 1 and the second still
  escalates with a reason naming `plan_validation_attempts` and the bound `2`.
- `tests/test_dispatch.py::test_advance_seeds_the_plan_size_from_the_ticket`
  passes on `"bad-plan"`, still asserting `plan_steps == 24` and
  `plan_files == 10`.
- `uv run --group dev pytest -q` is green and `./pipeline/hooks/test_dangerous_commands.py`
  exits 0.
- `grep -n structural_gate_failures README.md CLAUDE.md` prints at least one line
  for each file. No automated test covers that prose; check it by hand next to
  `uv run --group dev pytest -q tests/test_stages.py`.

## Decisions

**A Tier A failure has two verdicts, and `plan_validation_attempts` bounds only
one of them.** `("plan-validation", "bad-plan")` charges
`plan_validation_attempts`; `("plan-validation", "fail")` charges
`structural_gate_failures`. The budget exists to bound bad plans, and a prose
line above step 1 is a typo the gate stopped at before reading the plan. Same
argument as `stale_regate` (DEC-029), and the same shape: out of `BOUNDS`, so it
takes the dispatcher's default of 2, because formatting is not a property of the
ticket's class; and out of `SIZE_SCALED`, because a longer plan does not earn
more tries at the same typo.

**`bad-plan` is what carries DEC-047's size scaling now.** `SIZE_SCALED` holds
`plan_validation_attempts` alone, and after this ticket only the `bad-plan` row
charges it, so
`tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`
drives that pair. A future change that retires `bad-plan` retires the only
test of `bound_for()`'s per-8-steps arm with it; move the test, do not delete
it.

**`fail` is the structural verdict and `bad-plan` the substantive one, which is
the inverse of the safer-sounding naming.** The reproduction test asserts that
`transition("plan-validation", "fail", {})` charges nothing, so `fail` cannot be
the strict row. The cost is that a future emitter of a bare `fail` at
`plan-validation` undercharges; the two counters still bound planning at four
runs. `_finish()` remaps the Tier B agent's `fail` to `bad-plan` for exactly this
reason. Do not move that decision into `pipeline/stages/plan-validation.md`: a
stage that picks its own result string picks its own budget (invariant 1).

**`structural_only()` is an allowlist, matched with `startswith`.** A finding
nobody listed in `STRUCTURAL_MARKS` reads as substantive and charges
`plan_validation_attempts`, which is what every finding did before this ticket,
so forgetting to list a new structural finding costs precision, never a promise.
Substring matching would be wrong rather than merely loose: a substantive finding
carries captured test output in a fenced block, and the "does not mention the
expected string" finding puts a repr of `expect:` on its own first line, so a
ticket about the gate could quote a structural finding's text and buy itself a
free attempt. Add a mark whenever a structural finding is added to `gate()`.

**The classifier reads strings, because `gate()` must keep returning a
2-tuple.** Findings reach the dispatcher as JSON (`{"ok", "findings"}`) written
by `pipeline gate --findings`. Returning a third element from `gate()` would make
the branch's `tests/test_gate.py` unpack three values on the checkout of base
that DEC-017 describes, where `gate()` still returns two: a collection error that
blocks the very ticket that changes it. For the same reason `structural_only()`
is tested in `tests/test_dispatch.py`, because `tests/test_gate.py` may gain no
import.

**Only `plan-validation` splits the verdict.** `gate_result()` returns `fail` at
`revalidating` whatever the findings say, because `finish_gate()` serves both
stages and `("revalidating", "bad-plan")` is an unknown pair: it would escalate a
stale plan instead of charging `stale_regate` (DEC-029). A crashed gate child
keeps charging `plan_validation_attempts`, because `read_findings()`'s own
findings are not in the allowlist and DEC-061 wants that path to fail closed.

## Rollback

Revert the commits from steps 1 through 10 with `git revert`, or revert
`pipeline/core/machine.py` alone: with the `("plan-validation", "fail")` row back
on `charge("plan_validation_attempts", "planning")` the old behaviour returns,
and `bad-plan` charges the same counter, so a ticket already carrying
`structural_gate_failures` still advances and the key is simply never read again.
The counter is additive. No ticket file, template or frontmatter field changes,
so nothing on disk needs migrating.

## Thread

### 2026-08-27 08:59:34Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-27 · triage · ok

Reproduced. `tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt`
builds a plan with one prose line ahead of the numbered step (citing the
declared file, so the only Tier A finding is structural), confirms `gate()`
returns only "is not a numbered step" findings, then asserts
`transition("plan-validation", "fail", {})` leaves `plan_validation_attempts`
at 0. It gets 1 today.

expect: AssertionError: a structural-only gate failure charged plan_validation_attempts: {'plan_validation_attempts': 1}

Not a `chore`: the fix needs a design choice on how the gate communicates
"structural-only" past `finish_gate()` into `transition()` -- a new result
string, a new counter name, and wiring through `pipeline/core/gate.py`,
`pipeline/daemon/supervisor.py::finish_gate()`, and
`pipeline/core/machine.py::transition()`. Leaving that choice to planning.

### 2026-08-27 09:01:31Z · triage · session · session=1d2566ff-b0ae-4706-b2ab-e15ed8fbddf3

`triage` ran as session `1d2566ff-b0ae-4706-b2ab-e15ed8fbddf3`
- replay: `claude --resume 1d2566ff-b0ae-4706-b2ab-e15ed8fbddf3`
- log: `.project/logs/TICKET-065-triage-1d2566ff.log`

### 2026-08-27 09:01:31Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- transition() charges plan_validation_attempts on a structural-only gate failure, test committed on ticket/065

### 2026-08-27 · planning · ok

Plan written: 10 steps, 8 files. The design choice triage left open is settled
by the reproduction test, which asserts that `transition("plan-validation",
"fail", {})` charges nothing. So `fail` becomes the structural verdict and
charges a new `structural_gate_failures`, and a new `bad-plan` result carries
the substantive one onto `plan_validation_attempts`. `structural_only()` in
`pipeline/core/gate.py` classifies findings by a `startswith` allowlist,
`gate_result()` in `pipeline/daemon/supervisor.py` picks the result string, and
`_finish()` remaps the Tier B agent's `fail` to `bad-plan` so no prompt chooses
its own budget.

Scope: one subsystem, planned whole. No question for the human.

Two things noticed and deliberately not planned, outside this ticket:
- `pipeline/daemon/supervisor.py:22` imports `gate` from `pipeline.core.gate`,
  but the gate has run as a spawned child since DEC-061. The import looks dead.
- `finish_regate()` unlinks its findings file on the rebase-conflict path;
  `read_findings()` unlinks on every other path. Both paths are covered today,
  but the split ownership is easy to break.

Verified before planning: `machine.FENCED` names `transition`, so this ticket
parks at `awaiting-merge` for a human rather than merging itself.

### 2026-08-27 09:12:23Z · planning · session · session=c952e541-6723-42ce-85c7-3b13f1328d68

`planning` ran as session `c952e541-6723-42ce-85c7-3b13f1328d68`
- replay: `claude --resume c952e541-6723-42ce-85c7-3b13f1328d68`
- log: `.project/logs/TICKET-065-planning-c952e541.log`

### 2026-08-27 09:12:23Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned: `fail` charges a new structural_gate_failures, a new `bad-plan` result charges plan_validation_attempts; 10 steps, 8 files

### 2026-08-27 · plan-validation · fail

long: eight scored items, and an unexplained pass is a fail.
This entry sits above the gate entry below it, not after: the file ends inside
that entry's ANSI test dump, and no tool this stage may use can append past it.

**Rejected on regression surface.** One item fails, seven pass.

- Regression surface: FAIL. Step 8 moves `("plan-validation", "fail")` onto
  `structural_gate_failures`, which is not in `SIZE_SCALED`, so its bound is 2
  at every plan size. `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`
  (line 229) drives that pair twice and asserts `huge_next != "escalated"` and
  `huge["plan_validation_attempts"] == 5`. It passes today -- `1 passed, 19
  deselected in 0.02s` -- and goes red at step 8. The plan edits no such test,
  so step 10's `uv run --group dev pytest -q` cannot be green. Re-plan: point
  that test at `("plan-validation", "bad-plan")`, which keeps DEC-047's size
  scaling under test.
- Root cause: PASS. One counter serves both verdicts because `finish_gate()`
  collapses every Tier A failure to `fail` (`supervisor.py:909`). The plan
  splits the verdict there, not at the assert.
- Decision conflict: PASS. DEC-047 (the counter stays out of `BOUNDS` and
  `SIZE_SCALED`), DEC-029 (`gate_result()` splits only at `plan-validation`, so
  `revalidating` keeps charging `stale_regate`), DEC-017 (`structural_only` is
  tested in `tests/test_dispatch.py`, `gate()` still returns a 2-tuple) and
  DEC-061 (`read_findings()`'s findings stay substantive). The plan complies.
- Scope discipline: PASS. Every step traces to a criterion; step 10 traces to
  the `grep -n structural_gate_failures` criterion.
- Falsifiable criteria: PASS. Each names a test node and the value it asserts.
- No research left: PASS. Every anchor exists: `PLAN_STEP_RE` (`gate.py:39`),
  `finish_gate()` (`supervisor.py:889`), `result = res.get("result", "fail")`
  (`supervisor.py:1076`) with `stage` bound at `supervisor.py:1012`, and the
  README paragraph at `README.md:382`.
- Riskiest step: PASS. Step 8. `## Rollback` names the `machine.py`-only revert
  and argues the counter is additive.
- Blast radius: PASS. `bugfix`, 8 files: 3 source, 3 test, 2 docs.

One note for the re-plan, not a reject: the allowlist prefix "`## Decisions
checked` cites" also matches the finding "cites DEC-999, which is not a record
in ...", so a plan citing a decision nobody can resolve reads as structural.

### 2026-08-27 09:12:44Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt` fails as required
```
ural-only gate failure charged plan_validation_attempts: [39;49;00m[33m"[39;49;00m[90m[39;49;00m
            [33mf[39;49;00m[33m"[39;49;00m[33m{[39;49;00mcounters[33m}[39;49;00m[33m"[39;49;00m)[90m[39;49;00m
[1m[31mE       AssertionError: a structural-only gate failure charged plan_validation_attempts: {'plan_validation_attempts': 1}[0m
[1m[31mE       assert 1 == 0[0m
[1m[31mE        +  where 1 = <built-in method get of dict object at 0x7f4377bcc7c0>('plan_validation_attempts', 0)[0m
[1m[31mE        +    where <built-in method get of dict object at 0x7f4377bcc7c0> = {'plan_validation_attempts': 1}.get[0m

[1m[31mtests/test_gate.py[0m:130: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt[0m - AssertionError: a structural-only gate failure charged plan_validation_atte...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.06s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt[0m - AssertionError: a structural-only gate failure charged plan_validation_atte...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.12s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ji4j8w6t/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ji4j8w6t/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 16ms[0m[0m

```

### 2026-08-27 09:19:28Z · plan-validation · session · session=1d7cc7c8-8172-4158-a5e6-08425fbe75e3

`plan-validation` ran as session `1d7cc7c8-8172-4158-a5e6-08425fbe75e3`
- replay: `claude --resume 1d7cc7c8-8172-4158-a5e6-08425fbe75e3`
- log: `.project/logs/TICKET-065-plan-validation-1d7cc7c8.log`

### 2026-08-27 09:19:28Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ rejected on regression surface: step 8 turns test_plan_validation_budget_ignores_the_plans_size red and the plan edits no such test; seven other items pass

### 2026-08-27 · planning · ok

Re-planned after plan-validation rejected the first plan on regression surface.
The design is unchanged and needed no change: seven of eight items passed.

The one fix. `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`
(line 229) drives `("plan-validation", "fail")` three times and asserts
`huge_next != "escalated"` and `huge["plan_validation_attempts"] == 5`. Step 8
moves that pair onto `structural_gate_failures`, which is not in `SIZE_SCALED`,
so the test would go red and step 10's `uv run --group dev pytest -q` could not
be green. Step 3 now repoints all three `M.transition` calls (lines 238, 239,
246) at `("plan-validation", "bad-plan")`, in the same step that adds the
`bad-plan` row. The test is green before step 8 and after it, and DEC-047's size
scaling stays under test.

Two more tests checked against the split and left unedited, both because
"test file ... does not exist" is substantive:
`tests/test_dispatch.py::test_a_failing_gate_child_sends_the_ticket_back_to_planning`
and `tests/test_dispatch.py::test_a_bound_escalation_emits_an_escalated_event`,
which asserts the escalation reason names `plan_validation_attempts` and the
bound `2`. Both are now acceptance criteria.

Scope: one subsystem, planned whole. No question for the human.

### 2026-08-27 09:24:06Z · planning · session · session=a704a1e0-4499-4f82-86b7-ea1f8ff5903b

`planning` ran as session `a704a1e0-4499-4f82-86b7-ea1f8ff5903b`
- replay: `claude --resume a704a1e0-4499-4f82-86b7-ea1f8ff5903b`
- log: `.project/logs/TICKET-065-planning-a704a1e0.log`

### 2026-08-27 09:24:06Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-planned: step 3 repoints test_plan_validation_budget_ignores_the_plans_size at bad-plan, the one item plan-validation rejected; design unchanged, 10 steps, 8 files

### 2026-08-27 · plan-validation · ok

long: eight scored items, and an unexplained pass is a fail.
This entry sits above the gate entry below it, not after: the file ends inside
that entry's ANSI test dump, and no tool this stage may use can append past it.

**Approved. Eight items pass.** The one item that failed the first plan is fixed.

- Root cause: PASS. `finish_gate()` collapses every Tier A verdict to one
  string -- `advance(project, t, "ok" if ok else "fail", ...)`
  (`supervisor.py:909`) -- and `transition()` has one row for it
  (`machine.py:118-119`), so a gate that stopped on formatting spends the
  budget for bad plans. The plan splits the verdict at 909, not at the assert.
- Regression surface: PASS, the item the first plan failed. I drove every
  caller of the pair: `tests/test_machine.py:41,238,239,246` (steps 3 and 9
  repoint all four), `tests/test_gate.py:129` (the reproduction),
  `machine.py:118`. Nothing else in `pipeline/` or `tests/` emits
  `("plan-validation", "fail")`. `tests/test_dispatch.py:757` still passes
  unedited -- its asserts are `stage`, `plan_steps`, `plan_files`, none of them
  a counter -- and step 9 changes it anyway so it keeps exercising the
  size-scaled counter it was written for.
- Decision conflict: PASS. `SIZE_SCALED = {"plan_validation_attempts"}`
  (`machine.py:19`), so DEC-047's scaling follows `bad-plan`, which step 3
  keeps under test. `("revalidating", "fail")` still charges `stale_regate`
  (`machine.py:137`) and `tests/test_dispatch.py:410-412` asserts it. DEC-017:
  `gate()` keeps its 2-tuple (`gate.py:403`) and `structural_only`'s tests go
  in `tests/test_dispatch.py`. DEC-061: `read_findings()`'s "gate child exit"
  findings (`supervisor.py:881,884`) are outside the allowlist, so that path
  stays substantive.
- Scope discipline: PASS. Ten steps, three source files, three test files, two
  doc files. Every step traces to a criterion; step 10 traces to the
  `grep -n structural_gate_failures README.md CLAUDE.md` criterion.
- Falsifiable criteria: PASS. Each names a test node and the value it asserts.
  The doc criterion names a grep and says no test covers it.
- No research left: PASS. Every anchor exists as written: `PLAN_STEP_RE`
  (`gate.py:39`), `_dedupe()` (`gate.py:100`, rewrites fence bodies only),
  `finish_gate()` (`supervisor.py:889`), the import at `supervisor.py:22` is
  `from pipeline.core.gate import gate, plan_steps`,
  `result = res.get("result", "fail")` (`supervisor.py:1076`) with `stage`
  bound at `supervisor.py:1012`, README's paragraph ends at line 382, and
  CLAUDE.md's gate bullet runs 233-238. `bad-plan` appears nowhere in the repo
  today, so no existing consumer reads it.
- Riskiest step: PASS. Step 8, the flip of the live `("plan-validation",
  "fail")` row -- it changes dispatcher behaviour for every Tier A failure.
  `## Rollback` is its fallback and is specific: revert `machine.py` alone,
  both rows charge `plan_validation_attempts` again, and a ticket already
  carrying `structural_gate_failures` still advances because the counter is
  additive. Step order is the second mitigation: steps 3 and 9 land the test
  moves before and with the flip.
- Blast radius: PASS. A `bugfix` of 8 files, of which 2 are docs. `transition`
  is in `machine.FENCED`, so it parks at `awaiting-merge` for a human.

One precision note, not a blocker. `STRUCTURAL_MARKS` lists the prefix
"`## Decisions checked` cites", which also opens the finding at
`gate.py:260-262` -- a citation that resolves to no record on disk. That
finding reads as a plan-content fault, so the allowlist will classify it as
structural and charge `structural_gate_failures`. The effect is bounded: both
counters are 2, so planning still stops at four runs. Narrowing the mark to
"`## Decisions checked` cites no decision IDs" would charge it as substantive.

### 2026-08-27 09:24:26Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt` fails as required
```
ural-only gate failure charged plan_validation_attempts: [39;49;00m[33m"[39;49;00m[90m[39;49;00m
            [33mf[39;49;00m[33m"[39;49;00m[33m{[39;49;00mcounters[33m}[39;49;00m[33m"[39;49;00m)[90m[39;49;00m
[1m[31mE       AssertionError: a structural-only gate failure charged plan_validation_attempts: {'plan_validation_attempts': 1}[0m
[1m[31mE       assert 1 == 0[0m
[1m[31mE        +  where 1 = <built-in method get of dict object at 0x7f9e71895000>('plan_validation_attempts', 0)[0m
[1m[31mE        +    where <built-in method get of dict object at 0x7f9e71895000> = {'plan_validation_attempts': 1}.get[0m

[1m[31mtests/test_gate.py[0m:130: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt[0m - AssertionError: a structural-only gate failure charged plan_validation_atte...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.05s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt[0m - AssertionError: a structural-only gate failure charged plan_validation_atte...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-7ksa6k0v/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-7ksa6k0v/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 09:28:30Z · plan-validation · session · session=538ab1e0-08d6-4552-89ad-40617026fd96

`plan-validation` ran as session `538ab1e0-08d6-4552-89ad-40617026fd96`
- replay: `claude --resume 538ab1e0-08d6-4552-89ad-40617026fd96`
- log: `.project/logs/TICKET-065-plan-validation-538ab1e0.log`

### 2026-08-27 09:28:30Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ approved: all eight items pass; every plan anchor verified in the checkout, and steps 3 and 9 cover all four drivers of (plan-validation, fail) in tests/test_machine.py

### 2026-08-27 09:35:58Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-27 14:30:07Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt` fails as required
```
ural-only gate failure charged plan_validation_attempts: [39;49;00m[33m"[39;49;00m[90m[39;49;00m
            [33mf[39;49;00m[33m"[39;49;00m[33m{[39;49;00mcounters[33m}[39;49;00m[33m"[39;49;00m)[90m[39;49;00m
[1m[31mE       AssertionError: a structural-only gate failure charged plan_validation_attempts: {'plan_validation_attempts': 1}[0m
[1m[31mE       assert 1 == 0[0m
[1m[31mE        +  where 1 = <built-in method get of dict object at 0x7f72d5477f00>('plan_validation_attempts', 0)[0m
[1m[31mE        +    where <built-in method get of dict object at 0x7f72d5477f00> = {'plan_validation_attempts': 1}.get[0m

[1m[31mtests/test_gate.py[0m:130: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt[0m - AssertionError: a structural-only gate failure charged plan_validation_atte...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt[0m - AssertionError: a structural-only gate failure charged plan_validation_atte...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-7d8dard7/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-7d8dard7/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 14:30:08Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-27 · implementing · todo

**implementing todo, one entry per plan step**

1. [x] `STRUCTURAL_MARKS` + `structural_only()` in `gate.py`
2. [x] test `structural_only` in `tests/test_dispatch.py`
3. [x] `("plan-validation", "bad-plan")` row in `machine.py`; repoint two tests in `test_machine.py`
4. [x] `gate_result()` in `supervisor.py`, wired into `finish_gate()`
5. [x] test `gate_result()` in `tests/test_dispatch.py`
6. [x] `_finish()` remaps Tier B `fail` to `bad-plan`; update `plan-validation.md`
7. [x] test the remap in `tests/test_dispatch.py`
8. [x] flip `("plan-validation", "fail")` row to charge `structural_gate_failures`
9. [x] test step 8, repoint bounds-escalation table row, repoint `test_advance_seeds_the_plan_size_from_the_ticket`
10. [x] document `structural_gate_failures` in `README.md` and `CLAUDE.md`

### 2026-08-27 · implementing · done

**All ten steps complete, all four commits.**

- `uv run --group dev pytest -q` -- 349 passed, including the reproduction
  `tests/test_gate.py::test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt`.
- `./pipeline/hooks/test_dangerous_commands.py` -- "guard: all passed".
- `grep -n structural_gate_failures README.md CLAUDE.md` -- one hit each
  (README.md:386, CLAUDE.md:245).
- Commits: `27406db` (classifier + machine.py bad-plan row),
  `feat(TICKET-065): wire gate_result() and remap Tier B fail to bad-plan`,
  `feat(TICKET-065): charge structural_gate_failures for structural-only gate
  rejections`, `docs(TICKET-065): document structural_gate_failures counter`.
- No plan step turned out wrong; every anchor plan-validation verified matched
  the checkout.

### 2026-08-27 14:35:16Z · implementing · session · session=a4d19069-a218-4c13-b331-f023764b4c10

`implementing` ran as session `a4d19069-a218-4c13-b331-f023764b4c10`
- replay: `claude --resume a4d19069-a218-4c13-b331-f023764b4c10`
- log: `.project/logs/TICKET-065-implementing-a4d19069.log`

### 2026-08-27 14:35:16Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ executed all ten plan steps, splitting the gate verdict into bad-plan/structural fail; full suite (349) and guard suite green.

### 2026-08-27 · review · ok

**review: no blocking findings.** I reviewed the whole branch, `f5cc72b..aec872a`,
five commits, nine files. This is the first review pass, so the delta is the
branch point.

Verified: `uv run --group dev pytest -q` -- `349 passed in 17.20s`.
`./pipeline/hooks/test_dangerous_commands.py` -- `guard: all passed`, exit 0.
The ten tests the acceptance criteria name pass as one selection: `10 passed`.
`grep -n structural_gate_failures README.md CLAUDE.md` -- `README.md:386`,
`CLAUDE.md:245`. `tests/test_gate.py` imports `_dedupe, gate, plan_steps` and
`transition`, not `structural_only` (DEC-017 holds).

Findings I checked and refuted:
1. A bare `fail` at `plan-validation` from a path that never classified its
   findings would undercharge. `advance()` is the only caller of `transition()`,
   and its call sites are `supervisor.py:691, 828, 845, 854, 858, 922, 952,
   1096`. Only 922 (`finish_gate`, through `gate_result()`) and 1096
   (`_finish`, through the remap at 1094) can carry `plan-validation`.
2. `("revalidating", "bad-plan")` would escalate a stale plan. `gate_result()`
   returns `bad-plan` only when `stage == "plan-validation"`
   (`supervisor.py:896`), and `finish_regate()` reaches `finish_gate()` with
   `t.stage == "revalidating"`.
3. A mark might match no finding `gate()` writes. All ten match one:
   `gate.py:217, 225, 237, 285, 297, 305, 352, 368, 377, 381, 422`.

Findings that stand, none blocking:
1. **low** -- `no \`test_file\` recorded in frontmatter` (`gate.py:241`) is
   structural and has no mark, so it charges `plan_validation_attempts`. That
   is the pre-ticket behaviour the allowlist defaults to on purpose.
2. **low** -- `structural_only()` calls `.startswith` on entries of
   `read_findings()`'s `data["findings"]`, which is JSON a child wrote. Only
   `gate()` writes that file and it writes strings. A non-string entry would
   raise inside `finish_gate()` and hold the lease until it expires.
3. **low** -- `structural_only()`'s docstring opens "Are every one of
   `failures`". Grammar only.

### 2026-08-27 14:39:50Z · review · session · session=f9f1d875-186e-41de-abdf-5a7fcb34cba8

`review` ran as session `f9f1d875-186e-41de-abdf-5a7fcb34cba8`
- replay: `claude --resume f9f1d875-186e-41de-abdf-5a7fcb34cba8`
- log: `.project/logs/TICKET-065-review-f9f1d875.log`

### 2026-08-27 14:39:50Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed f5cc72b..aec872a: no blocking findings; 349 passed, guard exit 0, three candidate findings refuted, three low findings recorded

### 2026-08-27 14:40:09Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/core/machine.py:transition`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-065` lands it; `pipeline resume TICKET-065 --stage planning` sends it back.

### 2026-08-27 15:00:17Z · human · approval · by=chezzijr (via Claude Code, on explicit instruction)

**approved by chezzijr (via Claude Code, on explicit instruction)**

### 2026-08-27 15:05:53Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/065


Current branch ticket/065 is up to date.
Already up to date.
Updating f726acd..aec872a
Fast-forward
 CLAUDE.md                          |  7 +++++
 README.md                          |  6 ++++
 pipeline/core/gate.py              | 27 ++++++++++++++++++
 pipeline/core/machine.py           | 14 ++++++++++
 pipeline/daemon/supervisor.py      | 25 +++++++++++++++--
 pipeline/stages/plan-validation.md |  2 +-
 tests/test_dispatch.py             | 57 +++++++++++++++++++++++++++++++++++++-
 tests/test_gate.py                 | 21 ++++++++++++++
 tests/test_machine.py              | 30 +++++++++++++++++---
 9 files changed, 180 insertions(+), 9 deletions(-)

```

### 2026-08-27 15:05:53Z · merging · decision

decision recorded as `DEC-065`
