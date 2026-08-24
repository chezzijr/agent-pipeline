---
id: TICKET-047
stage: done
class: feature
branch: ticket/047
test_file: tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size
files_declared:
- .claude/skills/file-ticket/SKILL.md
- CLAUDE.md
- README.md
- pipeline/core/gate.py
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
- tests/test_gate.py
- tests/test_machine.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: ace5f7bb-93fe-4f39-aa25-0fb64b2dff0e
  log: .project/logs/TICKET-047-review-ace5f7bb.log
approved_by: chezzijr
approved_at: '2026-08-24T10:07:30.672621+00:00'
---

## Summary

Implemented and committed, 4 commits on `ticket/047`:

1. `ed48a3f` -- `plan_steps()` in `pipeline/core/gate.py`, counting unfenced
   numbered plan lines; `gate()`'s inline regex now reuses the same
   `PLAN_STEP_RE`.
2. `5b4c3a5` -- `pipeline/core/machine.py` gains `SIZE_SCALED`,
   `STEPS_PER_ATTEMPT` (8), `FILES_PER_ATTEMPT` (4), `BOUND_CEILING` (5),
   `_size()` and `bound_for(klass, key, counters)`; `charge()` now calls
   `bound_for()` instead of a raw `BOUNDS` lookup.
3. `1338d23` -- `advance()` (`pipeline/daemon/supervisor.py`) seeds
   `t.counters["plan_steps"]` and `["plan_files"]` from the ticket before
   calling `transition()`; the escalation reason uses `bound_for()`.
4. `a8eff30` -- `README.md`, `CLAUDE.md`, `.claude/skills/file-ticket/SKILL.md`
   updated to describe the size-scaled bound.

All 23 plan steps executed in order, each new test written red-first and
verified failing for the expected reason before the matching code landed. No
deviation from the accepted plan.

Reviewed at `b06ed44..a8eff30`, first pass, no blocking findings. `uv run
--group dev pytest -q` -- `269 passed in 10.64s`; the eight tests the
acceptance criteria name pass in one run -- `8 passed in 0.07s`. Five candidate
findings were refuted at a line: the `charged` scan, a stale plan or file list,
a second `transition()` caller, an off-by-one at the ceiling, a dangling
`BOUNDS` import. Two minor findings recorded, neither blocking: the counters
column in `pipeline ls` now shows the two size keys, and `README.md`'s "two
failures for most" is loose for `refactor`.

The review stage could not run `./pipeline/hooks/test_dangerous_commands.py` --
the guard blocks it for a read-only stage. The delta touches no file under
`pipeline/hooks/`. `implementing` ran it and recorded it as passing.

`transition()` is fenced (`pipeline/core/machine.py`), so this ticket parks at
`awaiting-merge` for a human, as the plan expected.

## Reproduction

`tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`

Command: `uv run --group dev pytest -q tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`

Output:
```
AssertionError: a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a 1-step/1-file plan, but it escalated at the same attempt count: 2 == 2
assert 'escalated' != 'escalated'
```

expect: assert 'escalated' != 'escalated'

The test drives `transition("plan-validation", "fail", ..., "bugfix")` twice each
for a `tiny` counters dict and a `huge` counters dict -- `transition()` has no
plan-size parameter at all, so both reach `escalated` at
`plan_validation_attempts == 2`, matching TICKET-041's actual behavior
(two attempts, 24 steps, 10 files, on main at 47fed3b).

## Digest

Files touched: `pipeline/core/machine.py` (the bound), `pipeline/core/gate.py`
(counting a plan's steps), `pipeline/daemon/supervisor.py` (feeding the size
in), `tests/test_machine.py`, `tests/test_gate.py`, `tests/test_dispatch.py`,
and three prose copies of the bound rule: `README.md`, `CLAUDE.md`,
`.claude/skills/file-ticket/SKILL.md`.

Key functions: `transition()`'s inner `charge(key, target)` reads
`BOUNDS.get(klass, {}).get(key, MAX_ATTEMPTS)` -- that one lookup is the fix
site. `advance()` (`pipeline/daemon/supervisor.py:103`) is the only caller of
`transition()` and the only place holding both the ticket and its counters.
`gate()` (`pipeline/core/gate.py:210-275`) already counts numbered steps with
`re.match(r"^\s*\d+[.)]", line)` over `_fenced()`-filtered lines.

Entry points: `advance(project, t, result, note, emit, agent)` seeds the size
counters; `Ticket.section("Plan")` and `t.files_declared` are the two size
inputs; `plan_steps()` is the new helper in `pipeline/core/gate.py`.

Gotchas:

- The escalation reason (`pipeline/daemon/supervisor.py:117-121`) picks
  `charged` as the FIRST counter whose value differs from `t.counters`. Seed
  the size keys onto `t.counters` BEFORE calling `transition()`, or
  `plan_steps` reads as the charged counter.
- Those same lines print the bound with a raw `BOUNDS.get(...)` lookup. It must
  use `bound_for()` or the message prints `2` while the machine used `5`.
- `_base_findings()` copies `tests/test_machine.py` onto a checkout of base and
  runs one node there. A MODULE-LEVEL reference to a name that exists only on
  this branch (`bound_for`, `BOUND_CEILING`) makes that import fail, the node
  name never reaches the output, and the gate blocks the ticket -- the trap
  DEC-030 records. Keep new names inside test bodies.
- Measured plan sizes, TICKET-031 through TICKET-046: 7 to 24 numbered steps,
  1 to 10 declared files. TICKET-041 is the largest at 24 steps / 10 files.
- `git log -S "BOUNDS" -- pipeline/core/machine.py` returns `bd3671a` and
  `6e3c3d6` only. No earlier size-scaling attempt was reverted.
- `pipeline/core/machine.py` is in `machine.FENCED` for `transition`, so this
  ticket parks at `awaiting-merge` for a human. That is expected, not a failure.
- `tests/helpers.py` `FIXTURE` has 1 plan step and 1 declared file, so its bound
  stays 2 and the existing dispatch tests keep their expected numbers. Its
  counters become `{"plan_steps": 1, "plan_files": 1}` after any `advance()`,
  and that breaks one exact-equality assert: `tests/test_dispatch.py:643`, in
  `test_a_missing_marker_changes_no_transition_and_no_counter`, asserts
  `t.counters == {}`. Step 18 updates it. `grep -rn "counters" tests/*.py` finds
  no second exact-equality assert on a ticket's counters; every other test reads
  one key (`t.counters["review_loops"]`, `t.counters.get("stale_regate", 0)`).

This plan differs from the plan `plan-validation` rejected in two places and
nowhere else -- seven of that plan's eight items passed.

1. Step 18 is new: it updates `tests/test_dispatch.py:643`, the regression the
   rejection called blocking, and the fifth acceptance criterion names that
   test. Old steps 18 to 22 are now 19 to 23, with their text unchanged.
2. Step 2 anchors `PLAN_STEP_RE` on `PLAN_STEP_RULE` (`pipeline/core/gate.py:31`)
   instead of `CRIT_ITEM_RE`, which the rejection showed exists nowhere:
   `grep -rn "CRIT_ITEM_RE" pipeline/ tests/` returns nothing.

## Decisions checked

Grepped `/home/chezzijr/proj/agent-pipeline/.project/decisions/` for `BOUNDS`,
`plan_validation_attempts`, `files_declared`, `budget`, `MAX_ATTEMPTS`,
`ceiling`, `attempts` and `superseded-by`. No record in that directory carries a
`superseded-by:` line, so all five cited below are active.

- DEC-026 -- `counters` already carries a non-attempt, dispatcher-owned value
  (`cheap_route`), it is deliberately absent from `BOUNDS`, and a test asserts
  that absence. This plan takes the same shape: `plan_steps` and `plan_files`
  ride in `counters` and never enter `BOUNDS`.
- DEC-029 -- `stale_regate` and `rebase_conflicts` are deliberately outside
  `BOUNDS` and take `MAX_ATTEMPTS`, because staleness and base churn are not
  properties of the work's size. This plan leaves both out of `SIZE_SCALED`.
- DEC-030 -- the plan-step rule is duplicated between `pipeline/core/gate.py`
  and `pipeline/stages/planning.md` on purpose; do not deduplicate across that
  boundary. `plan_steps()` therefore lives in `pipeline/core/gate.py`, beside
  `PLAN_STEP_RULE`, and shares one `PLAN_STEP_RE` with `gate()` itself.
- DEC-011 -- the event vocabulary is frozen, but "adding a field inside `data`
  is additive and fine". `transition`'s `data.counters` gains two keys; no
  column, kind or field meaning changes. `metrics.review_loop_distribution()`
  reads `$.counters.review_loops` by name and is unaffected.
- DEC-031 -- `machine.FENCED` matches symbols, not whole files, and
  `transition` is one of them. This ticket edits `transition`, so it parks at
  `awaiting-merge`; that is the intended route for a bounds change.

## Plan

1. Run `uv run --group dev pytest -q tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size` and confirm the baseline failure `assert 'escalated' != 'escalated'`.
2. In `pipeline/core/gate.py`, add module-level `PLAN_STEP_RE = re.compile(r"^\s*\d+[.)]")` next to `PLAN_STEP_RULE` (`pipeline/core/gate.py:31`), and replace the inline `re.match(r"^\s*\d+[.)]", line)` inside `gate()` with `PLAN_STEP_RE.match(line)`, so one regex defines what a step is.
3. In `pipeline/core/gate.py`, add `def plan_steps(plan: str) -> int:` -- `raws = plan.splitlines()`, `fenced = _fenced(raws)`, `return sum(1 for i, l in enumerate(raws) if not fenced[i] and PLAN_STEP_RE.match(l))` -- with a docstring saying it is the counting half of `PLAN_STEP_RULE` and the source of `counters["plan_steps"]`.
4. Add `test_plan_steps_counts_only_unfenced_numbered_steps` to `tests/test_gate.py`, importing `plan_steps` beside `gate` at the top: a plan of 3 numbered steps, one indented continuation line, and an indented triple-backtick fence holding the line `2. not a step`; assert `plan_steps(plan) == 3`.
5. Run `uv run --group dev pytest -q tests/test_gate.py`, expect every test to pass, then commit `pipeline/core/gate.py` and `tests/test_gate.py` as `feat(TICKET-047): count a plan's numbered steps`.
6. In `pipeline/core/machine.py`, below `BOUNDS`, add `SIZE_SCALED = {"plan_validation_attempts"}`, `STEPS_PER_ATTEMPT = 8`, `FILES_PER_ATTEMPT = 4` and `BOUND_CEILING = 5`, with the reasoning from this ticket's `## Decisions` as their comment.
7. In `pipeline/core/machine.py`, add `def _size(counters: dict, key: str) -> int:` which sets `v = counters.get(key, 0)` and returns `v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 0` -- a hostile counters value must read as 0 and never raise, because `transition()` is total.
8. In `pipeline/core/machine.py`, add `def bound_for(klass: str, key: str, counters: dict) -> int:` -- `base = BOUNDS.get(klass, {}).get(key, MAX_ATTEMPTS)`; return `base` when `key not in SIZE_SCALED`; otherwise return `min(base + max(_size(counters, "plan_steps") // STEPS_PER_ATTEMPT, _size(counters, "plan_files") // FILES_PER_ATTEMPT), BOUND_CEILING)`.
9. In `pipeline/core/machine.py`, change `charge()`'s `bound = BOUNDS.get(klass, {}).get(key, MAX_ATTEMPTS)` to `bound = bound_for(klass, key, c)`, leaving the rest of `charge()` untouched.
10. In `tests/test_machine.py`, edit `test_plan_validation_budget_ignores_the_plans_size` to read `tiny = {"plan_validation_attempts": 0, "plan_steps": 1, "plan_files": 1}` and `huge = {"plan_validation_attempts": 0, "plan_steps": 24, "plan_files": 10}`, keep both existing asserts, then drive `huge` through 3 further `M.transition("plan-validation", "fail", huge, "bugfix")` calls and assert `huge_next == "escalated"` and `huge["plan_validation_attempts"] == 5`.
11. Run `uv run --group dev pytest -q tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size` and expect `1 passed`.
12. Add `test_the_size_scaled_bound_has_a_ceiling_and_spares_the_dispatchers_counters` to `tests/test_machine.py`, naming `M.bound_for`, `M.BOUND_CEILING` and `M.MAX_ATTEMPTS` inside the body only (never at module level), asserting `M.bound_for("refactor", "plan_validation_attempts", {"plan_steps": 400, "plan_files": 900}) == M.BOUND_CEILING`, `M.bound_for("bugfix", "lease_expiries", {"plan_steps": 400}) == M.MAX_ATTEMPTS`, `M.bound_for("bugfix", "no_result", {"plan_steps": 400}) == M.MAX_ATTEMPTS`, `M.bound_for("bugfix", "review_loops", {"plan_steps": 400}) == 2`, and `M.bound_for("bugfix", "plan_validation_attempts", {"plan_steps": "24"}) == 2`.
13. Run `uv run --group dev pytest -q tests/test_machine.py`, expect every test to pass including `test_bounds_escalate_on_the_second_failure` and `test_bounds_come_from_the_ticket_class`, then commit `pipeline/core/machine.py` and `tests/test_machine.py` as `fix(TICKET-047): scale the plan-validation bound with the plan's size`.
14. In `pipeline/daemon/supervisor.py`, import `bound_for` from `pipeline.core.machine` and `plan_steps` from `pipeline.core.gate`, beside the existing `gate` import.
15. In `pipeline/daemon/supervisor.py`, in `advance()` directly after `stage = t.stage`, add `t.counters = {**t.counters, "plan_steps": plan_steps(t.section("Plan")), "plan_files": len(t.files_declared)}` with a comment stating three things: the size arrives through counters because `transition()` may not read a file, it is recomputed at every advance so a re-plan is measured as it lands, and it is written onto `t.counters` first so the `charged` scan below still sees exactly one changed key.
16. In `pipeline/daemon/supervisor.py`, change the escalation reason's `BOUNDS.get(t.klass, {}).get(charged, MAX_ATTEMPTS)` to `bound_for(t.klass, charged, counters)`, so the message names the bound the machine actually used.
17. Add `test_advance_seeds_the_plan_size_from_the_ticket` to `tests/test_dispatch.py`: build `project()` from `FIXTURE` with `## Plan` replaced by 24 numbered steps each naming `thing.py`, `files_declared` replaced by the 10 entries `f0.py` through `f9.py`, and `counters: {}` replaced by `counters: {plan_validation_attempts: 1}`; load the ticket, set `t.stage = "plan-validation"`, call `supervisor.advance(d, t, "fail", "n", agent=False)`, then assert `t.stage == "planning"`, `t.counters["plan_steps"] == 24` and `t.counters["plan_files"] == 10`.
18. In `tests/test_dispatch.py`, in `test_a_missing_marker_changes_no_transition_and_no_counter`, change `assert t.counters == {}` to `assert t.counters == {"plan_steps": 1, "plan_files": 1}` and add the comment `# the dispatcher measured the FIXTURE plan; no attempt was charged` -- the assert stays exact, so a charged counter still fails this test.
19. Run `uv run --group dev pytest -q tests/test_dispatch.py`, expect every test to pass including `test_a_bound_escalation_emits_an_escalated_event`, then commit `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py` as `fix(TICKET-047): feed the plan's size into the dispatcher's bounds`.
20. In `README.md`, replace the bounded-loops bullet's "the second failure of any loop escalates to a human" with "a loop escalates to a human at its bound -- two failures for most, more for plan-validation on a large plan, never more than five".
21. In `CLAUDE.md`, extend invariant 3 with one sentence: `BOUNDS[class][counter]` is the base, `bound_for()` adds one attempt per 8 plan steps or 4 declared files for the counters in `SIZE_SCALED`, capped at `BOUND_CEILING`, and `lease_expiries` / `no_result` stay on `MAX_ATTEMPTS`; leave the fenced-list paragraph untouched.
22. In `.claude/skills/file-ticket/SKILL.md`, add one line under the class table: class sets the base budget, and a large plan buys plan-validation attempts on top of it -- one per 8 steps or 4 declared files, capped at 5 -- so a class no longer has to be inflated to buy attempts.
23. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect both green, then commit `README.md`, `CLAUDE.md` and `.claude/skills/file-ticket/SKILL.md` as `docs(TICKET-047): record the size-scaled loop bound`.

## Acceptance criteria

- `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`
  passes: a 24-step/10-file `bugfix` returns `planning` at
  `plan_validation_attempts == 2` and `escalated` at 5, while a 1-step/1-file
  `bugfix` still escalates at 2.
- `tests/test_machine.py::test_the_size_scaled_bound_has_a_ceiling_and_spares_the_dispatchers_counters`
  passes: `bound_for()` caps at `BOUND_CEILING` (5), returns `MAX_ATTEMPTS` for
  `lease_expiries` and `no_result` at any size, and reads a non-int
  `plan_steps` as 0.
- `tests/test_machine.py::test_bounds_escalate_on_the_second_failure` and
  `tests/test_machine.py::test_bounds_come_from_the_ticket_class` pass
  unchanged: a counters dict with no size keys keeps the old bound.
- `tests/test_gate.py::test_plan_steps_counts_only_unfenced_numbered_steps`
  passes: `plan_steps()` returns 3 for a plan whose fence hides a fourth
  numbered line.
- `tests/test_dispatch.py::test_advance_seeds_the_plan_size_from_the_ticket`
  passes: `advance()` writes `plan_steps: 24` and `plan_files: 10` into the
  ticket's counters and routes a second `plan-validation` failure to `planning`.
- `tests/test_dispatch.py::test_a_missing_marker_changes_no_transition_and_no_counter`
  passes: after `advance()` on the `FIXTURE` ticket the counters are exactly
  `{"plan_steps": 1, "plan_files": 1}` -- the two size keys and no charged
  attempt.
- `tests/test_dispatch.py::test_a_bound_escalation_emits_an_escalated_event`
  passes unchanged: the 1-step/1-file `FIXTURE` still escalates at 2 and the
  reason still names the bound.
- `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`
  both exit 0.

## Decisions

**The plan's size reaches `transition()` through `counters`, never through a
read.** `advance()` (`pipeline/daemon/supervisor.py`) writes `plan_steps` and
`plan_files` onto `t.counters` before every transition, so `transition()` stays
pure and total. Counters are `CONTROL_FIELDS`, restored from the pre-spawn
snapshot, so no agent can hand a budget to itself through the ticket file. The
keys are recomputed at every advance, so a re-plan is measured as it lands
rather than frozen at the first plan.

**Order matters: seed the size keys before calling `transition()`.**
`advance()`'s escalation reason picks the charged counter as the first key whose
value differs from `t.counters`. Seeding after the call would make `plan_steps`
read as the counter that hit its bound.

**The formula is base + max(steps // 8, files // 4), capped at 5.** The cap is
the point: a bound that grows without limit is not a bound. 5 is calibrated on
TICKET-041, the largest plan this repo has produced (24 steps, 10 files,
`class: bugfix`, escalated twice): its findings narrowed every round and it
converged on the fifth planning run. Under this formula it gets exactly 5. At
roughly $5 per planning-plus-validation pair, a ceiling of 5 caps one ticket's
planning spend near $30 before a human is called, and that is the trade the
ceiling encodes. Raise the ceiling only with new measurements of tickets that
were still converging when they hit it.

**Only `plan_validation_attempts` scales, and the set is `SIZE_SCALED`.** A
Tier A finding is raised per plan step, so a 24-step plan has roughly 24 places
to fail where a 1-step plan has one. `review_loops` is charged per pass over the
diff, not per finding, and nothing measured here says a large diff needs more
passes -- adding it is one entry in `SIZE_SCALED` if evidence arrives.
`lease_expiries` and `no_result` are the dispatcher's own counters, are charged
directly against `MAX_ATTEMPTS` in `pipeline/daemon/supervisor.py`, and must
never scale: a crashed harness is not more trustworthy for having a long plan.

**A stage can inflate its own plan, and other mechanisms bound that.** An agent
that pads `## Plan` or `files_declared` buys itself attempts. No stage prompt is
told the formula, every padded step must still name a declared file to clear the
gate, and a padded `files_declared` serialises the ticket against every other
ticket touching those files (`files_conflict()`). Do not answer this by telling
a stage its budget; that is invariant 3.

**`plan_steps()` lives in `pipeline/core/gate.py`, not in the dispatcher.** The
gate already owns what a numbered step is (`PLAN_STEP_RULE`), and the counter
and the gate now share one `PLAN_STEP_RE` and one `_fenced()`. A second
definition in `pipeline/daemon/supervisor.py` would let the budget and the gate
disagree about the same plan. DEC-030 forbids deduplicating the rule across the
`pipeline/stages/planning.md` boundary; this keeps both copies inside one file
instead.

## Rollback

Revert the four commits -- gate, machine, supervisor, docs -- in any order; they
touch disjoint files. Counters written by the shipped code are inert on the old
code, because base `transition()` ignores unknown counter keys, so no ticket
file needs migrating and none has to be hand-edited. A ticket left mid-flight on
a bound that no longer exists is restarted with
`pipeline resume <id> --stage planning --reset plan_validation_attempts`.

## Thread

### 2026-08-24 08:05:50Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 · triage · result=ok

Reproduced. `transition()` (`pipeline/core/machine.py`) takes no plan-size
input, so `BOUNDS[class][counter]` is the whole budget regardless of plan
steps or `files_declared` count. Committed
`tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`
(263e584) on `ticket/047`; it drives two attempts each for a tiny and a huge
counters dict under `klass="bugfix"` and shows both escalate at
`plan_validation_attempts == 2`.

This is `ok`, not `chore`: a formula that scales the bound with plan size or
`len(files_declared)`, keeps a ceiling, and leaves `lease_expiries` /
`no_result` on `MAX_ATTEMPTS` is a design choice, not a named-files edit.
Planning should also check `git log -S "BOUNDS" -- pipeline/core/machine.py`
before choosing a formula, in case a prior attempt was reverted.

### 2026-08-24 08:43:38Z · triage · session · session=56b5e961-f866-4487-ba67-c9c2e81f7a97

`triage` ran as session `56b5e961-f866-4487-ba67-c9c2e81f7a97`
- replay: `claude --resume 56b5e961-f866-4487-ba67-c9c2e81f7a97`
- log: `.project/logs/TICKET-047-triage-56b5e961.log`

### 2026-08-24 08:43:38Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: transition() has no plan-size input, both tiny and 24-step/10-file plans escalate at plan_validation_attempts==2

### 2026-08-24 · planning · result=ok

Plan written: 22 steps across 9 files. The design choice the ticket asked for
is settled two ways.

1. The size arrives through `counters`, not through a new argument. The
   committed test drives `M.transition(...)` with counters dicts only, and on
   base the extra keys are ignored, so the test still fails on base -- which
   `_base_findings()` requires. A fifth positional argument would raise
   `TypeError` there and read as "errored rather than failed".
2. The formula is `min(base + max(steps // 8, files // 4), 5)`, applied to the
   counters in `SIZE_SCALED` -- today `plan_validation_attempts` alone.
   TICKET-041's shape (24 steps, 10 files, `bugfix`) gets 5; `tests/helpers.py`
   `FIXTURE` (1 step, 1 file) keeps 2. `lease_expiries` and `no_result` are not
   in `SIZE_SCALED` and keep `MAX_ATTEMPTS`.

Checked `git log -S "BOUNDS" -- pipeline/core/machine.py` as triage asked: it
returns `bd3671a` and `6e3c3d6` only. No earlier size-scaling attempt was
reverted.

Noticed and not fixed, outside this stage's job: `README.md`, `CLAUDE.md`
invariant 3 and `.claude/skills/file-ticket/SKILL.md` each state the bound rule
in prose. Steps 19 to 21 update all three, because a stale copy sends the next
ticket in wrong.

### 2026-08-24 08:53:24Z · planning · session · session=23c91769-450a-44eb-bab5-28a93fcc3978

`planning` ran as session `23c91769-450a-44eb-bab5-28a93fcc3978`
- replay: `claude --resume 23c91769-450a-44eb-bab5-28a93fcc3978`
- log: `.project/logs/TICKET-047-planning-23c91769.log`

### 2026-08-24 08:53:24Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: plan size rides in counters, bound_for() scales plan_validation_attempts by min(base + max(steps//8, files//4), 5)

### 2026-08-24 09:03:39Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size` fails as required
```
lidation_attempts": 0}
        for _ in range(2):
            tiny_next, tiny = M.transition("plan-validation", "fail", tiny, "bugfix")
            huge_next, huge = M.transition("plan-validation", "fail", huge, "bugfix")
        assert tiny_next == "escalated", "a 1-step/1-file plan exhausted its budget as expected"
>       assert huge_next != "escalated", \
            "a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a " \
            "1-step/1-file plan, but it escalated at the same attempt count: " \
            f"{huge['plan_validation_attempts']} == {tiny['plan_validation_attempts']}"
E       AssertionError: a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a 1-step/1-file plan, but it escalated at the same attempt count: 2 == 2
E       assert 'escalated' != 'escalated'

tests/test_machine.py:224: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size` fails on base `main` too -- the bug is not already fixed upstream
```
   f"{huge['plan_validation_attempts']} == {tiny['plan_validation_attempts']}"
E       AssertionError: a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a 1-step/1-file plan, but it escalated at the same attempt count: 2 == 2
E       assert 'escalated' != 'escalated'

tests/test_machine.py:224: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-pz5ivo7z/base
      Built pipeline @ file:///tmp/pipeline-base-pz5ivo7z/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 · plan-validation · result=fail

The plan misses one regression, so step 18 and the last acceptance criterion
cannot hold as written.

**Blocking: `tests/test_dispatch.py:643` asserts `t.counters == {}` after
`advance()`.** `test_a_missing_marker_changes_no_transition_and_no_counter`
runs `supervisor.advance(d, Ticket.load(path), "ok", "no marker here")` on the
`FIXTURE` ticket, reloads it, and asserts `assert t.counters == {}`. Step 15
seeds `plan_steps` and `plan_files` onto `t.counters`, and
`pipeline/daemon/supervisor.py:130` writes the returned counters back, so the
reloaded ticket carries `{"plan_steps": 1, "plan_files": 1}`. The test passes
today: `1 passed in 0.03s`. The digest's line "`FIXTURE` has 1 plan step and 1
declared file, so its bound stays 2" is right about the bound and does not
cover this assert. Add a step that updates this test, and name it in the
acceptance criteria.

**Minor: step 2 anchors on a symbol that does not exist.** `grep -rn
"CRIT_ITEM_RE" pipeline/ tests/` returns nothing. Place `PLAN_STEP_RE` beside
`PLAN_STEP_RULE` (`pipeline/core/gate.py:31`) instead.

long: this stage must score eight items and an unexplained pass is a fail.

Per-item scoring:

1. Root cause -- pass. The bound is a function of `(class, counter)` alone and
   nothing carries plan size to `transition()`. Routing the size through
   `counters` and computing the bound in `bound_for()` fixes that, not the test.
2. Decisions -- pass. All five records exist and none is superseded. DEC-030
   forbids deduplicating the step rule across the `pipeline/stages/planning.md`
   boundary; `plan_steps()` in `pipeline/core/gate.py` complies. DEC-031: the
   plan edits `charge()` inside `transition`, which `machine.FENCED` names, so
   `awaiting-merge` is correct. `_base_findings()` copies only the ticket's
   `test_file`, so step 4's module-level `plan_steps` import into
   `tests/test_gate.py` is safe and step 12's body-only rule is right.
3. Scope -- pass. Steps 19 to 21 trace to no criterion, but `CLAUDE.md` requires
   `.claude/skills/file-ticket/SKILL.md` to follow a gate change. Step 2 is a
   refactor to one shared regex, identical in behaviour, covered by
   `tests/test_gate.py`.
4. Falsifiable criteria -- pass. Each names a test and a number: 2, 5, 24, 10,
   3. I recomputed the formula: `huge` gets `2 + max(24//8, 10//4) = 5`,
   `tiny` gets 2, `refactor` at 400/900 caps at 5.
5. Research -- fail on one anchor, `CRIT_ITEM_RE`, above. Every other step names
   a file and a symbol that exists.
6. Riskiest step -- pass. Step 15 is riskiest: it changes the counters of every
   ticket at every advance. `## Rollback` states the fallback -- revert the
   supervisor commit, and the shipped keys are inert on old code.
7. Regression surface -- fail, the blocking finding above.
8. Blast radius -- pass. 9 files for a `bugfix` is 3 source, 3 test, and 3 prose
   copies of one rule. No reclassification: the class also sets the base bound
   this ticket changes.

### 2026-08-24 09:07:32Z · plan-validation · session · session=09d47c59-7980-4e0f-92a7-ad35469295a4

`plan-validation` ran as session `09d47c59-7980-4e0f-92a7-ad35469295a4`
- replay: `claude --resume 09d47c59-7980-4e0f-92a7-ad35469295a4`
- log: `.project/logs/TICKET-047-plan-validation-09d47c59.log`

### 2026-08-24 09:07:32Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ Plan rejected on one regression: step 15's counter seeding breaks tests/test_dispatch.py:643 `assert t.counters == {}`; seven of eight items pass

### 2026-08-24 · planning · result=ok

Re-planned after the `plan-validation` rejection. The rejection named two
things; I changed those two and nothing else.

1. Blocking: `tests/test_dispatch.py:643` asserts `t.counters == {}` after
   `advance()` on `FIXTURE`. Confirmed: `FIXTURE` holds one numbered step
   (`1. fix thing.py`) and one declared file (`thing.py`), so step 15's seeding
   writes `{"plan_steps": 1, "plan_files": 1}`. New step 18 changes the assert
   to that exact dict and keeps it exact, so a charged attempt still fails the
   test. The fifth acceptance criterion names the test.
2. Minor: `grep -rn "CRIT_ITEM_RE" pipeline/ tests/` returns nothing. Step 2
   now anchors `PLAN_STEP_RE` on `PLAN_STEP_RULE` (`pipeline/core/gate.py:31`).

Searched for other regressions of that shape: `grep -rn "counters" tests/*.py`
shows line 643 is the only exact-equality assert on a ticket's counters. Every
other test reads one key -- `t.counters["review_loops"]`,
`t.counters.get("stale_regate", 0)`.

Old steps 18 to 22 are now 19 to 23, with their text unchanged. The plan is 23
steps across the same 9 files. `## Decisions checked`, `## Decisions` and
`## Rollback` are unchanged; `plan-validation` passed all three.

### 2026-08-24 09:22:03Z · planning · session · session=e81bc185-80ee-412f-9b37-2b62bb3617fc

`planning` ran as session `e81bc185-80ee-412f-9b37-2b62bb3617fc`
- replay: `claude --resume e81bc185-80ee-412f-9b37-2b62bb3617fc`
- log: `.project/logs/TICKET-047-planning-e81bc185.log`

### 2026-08-24 09:22:03Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Re-planned: 23 steps, new step 18 fixes tests/test_dispatch.py:643 `t.counters == {}`, step 2 anchors on PLAN_STEP_RULE

### 2026-08-24 09:22:14Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size` fails as required
```
lidation_attempts": 0}
        for _ in range(2):
            tiny_next, tiny = M.transition("plan-validation", "fail", tiny, "bugfix")
            huge_next, huge = M.transition("plan-validation", "fail", huge, "bugfix")
        assert tiny_next == "escalated", "a 1-step/1-file plan exhausted its budget as expected"
>       assert huge_next != "escalated", \
            "a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a " \
            "1-step/1-file plan, but it escalated at the same attempt count: " \
            f"{huge['plan_validation_attempts']} == {tiny['plan_validation_attempts']}"
E       AssertionError: a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a 1-step/1-file plan, but it escalated at the same attempt count: 2 == 2
E       assert 'escalated' != 'escalated'

tests/test_machine.py:224: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size` fails on base `main` too -- the bug is not already fixed upstream
```
   f"{huge['plan_validation_attempts']} == {tiny['plan_validation_attempts']}"
E       AssertionError: a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a 1-step/1-file plan, but it escalated at the same attempt count: 2 == 2
E       assert 'escalated' != 'escalated'

tests/test_machine.py:224: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-m563quza/base
      Built pipeline @ file:///tmp/pipeline-base-m563quza/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 · plan-validation · result=ok

Plan accepted. Both rejection findings are fixed, and I verified each against
the code.

- `tests/test_dispatch.py:643` is `assert t.counters == {}` in
  `test_a_missing_marker_changes_no_transition_and_no_counter`. Step 18 changes
  it to `{"plan_steps": 1, "plan_files": 1}`, and the sixth criterion names it.
  `FIXTURE` (`tests/helpers.py:14,31`) holds `files_declared: [thing.py]` and
  one step `1. fix thing.py`, so those values are right and its bound stays
  `2 + max(1 // 8, 1 // 4) == 2`.
- `grep -rn "CRIT_ITEM_RE" pipeline/ tests/` returns nothing.
  `PLAN_STEP_RULE` is at `pipeline/core/gate.py:31`, so step 2's anchor exists.

long: this stage scores eight items, and an unexplained pass is a fail.

1. Root cause -- pass. `charge()` reads
   `BOUNDS.get(klass, {}).get(key, MAX_ATTEMPTS)`
   (`pipeline/core/machine.py:54`), a function of `(class, counter)` only.
   `transition()` takes no plan-size parameter, so size cannot reach the bound.
   Steps 8, 9 and 15 route size through `counters` and compute the bound in
   `bound_for()`. That fixes the input, not the assertion.
2. Decisions -- pass. All five records exist and none is superseded.
   `_base_findings()` (`pipeline/core/gate.py:71`) copies only
   `test.split("::")[0]`, this ticket's `tests/test_machine.py`. Step 4's
   module-level `plan_steps` import into `tests/test_gate.py` is therefore
   safe, and step 12's body-only rule is required. DEC-030 holds:
   `plan_steps()` and `gate()` share one `PLAN_STEP_RE` inside
   `pipeline/core/gate.py`, and `pipeline/stages/planning.md` keeps its copy.
   DEC-031: the plan edits `charge()` inside `transition`, which
   `machine.FENCED` names (`pipeline/core/machine.py:26`), so `awaiting-merge`
   is right.
3. Scope -- pass. Steps 20 to 22 trace to no test criterion. The last criterion
   covers them by suite, and `CLAUDE.md` makes a stale
   `.claude/skills/file-ticket/SKILL.md` an unfinished change. Every other step
   traces to a named test.
4. Falsifiable -- pass. Step 12's five asserts each fail on a specific wrong
   implementation: a missing ceiling returns 228, not 5; `lease_expiries` added
   to `SIZE_SCALED` returns 5, not 2; a `_size()` that trusts `"24"` raises.
   Step 10 pins both the escalating attempt count (5) and the non-escalating
   one (2).
5. No research left -- pass. Every step names a file, and steps 2, 3, 8, 9, 15
   and 16 name the line or symbol they change.
6. Riskiest step -- pass, with a fallback. Step 15 is riskiest: it writes two
   keys onto every ticket's `counters` at every `advance()`, including at `new`
   and `triage`, where `t.section("Plan")` is `""` and both keys read 0. The
   fallback is `## Rollback`: base `transition()` ignores unknown counter keys,
   so shipped counters are inert on reverted code and no ticket file migrates.
7. Regression surface -- pass. Four readers of `counters` outside
   `transition()`: `pipeline/daemon/supervisor.py:560` and `:862` charge
   `lease_expiries` and `no_result` inline against `MAX_ATTEMPTS`, and the plan
   leaves both alone; `pipeline/cli/main.py:152` charges `plan_rejections`, a
   human counter the plan does not touch; `pipeline/cli/main.py:219` prints the
   dict in `pipeline ls`, which is display only. Tests:
   `test_bounds_escalate_on_the_second_failure` and
   `test_bounds_come_from_the_ticket_class` pass a counters dict with no size
   keys, so they cover the unscaled fallback;
   `test_a_bound_escalation_emits_an_escalated_event` covers step 16's message.
8. Blast radius -- pass for `bugfix`. 9 files: 3 source, 3 test, 3 prose. The
   behaviour change is 3 source files and roughly 15 lines.

Non-blocking, for the implementer: step 20's quoted README text spans a line
wrap. `README.md:53-54` reads "every retry is counted, and the second failure
of any / loop escalates to a human instead of ping-ponging." A literal
one-line replace finds nothing. The bullet itself is unambiguous.

### 2026-08-24 09:26:18Z · plan-validation · session · session=a2826e38-c191-4f67-a448-b4b9af0da3da

`plan-validation` ran as session `a2826e38-c191-4f67-a448-b4b9af0da3da`
- replay: `claude --resume a2826e38-c191-4f67-a448-b4b9af0da3da`
- log: `.project/logs/TICKET-047-plan-validation-a2826e38.log`

### 2026-08-24 09:26:18Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan accepted: all eight items pass; both rejection findings fixed and verified in the code

### 2026-08-24 09:27:04Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 09:29:19Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size` fails as required
```
lidation_attempts": 0}
        for _ in range(2):
            tiny_next, tiny = M.transition("plan-validation", "fail", tiny, "bugfix")
            huge_next, huge = M.transition("plan-validation", "fail", huge, "bugfix")
        assert tiny_next == "escalated", "a 1-step/1-file plan exhausted its budget as expected"
>       assert huge_next != "escalated", \
            "a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a " \
            "1-step/1-file plan, but it escalated at the same attempt count: " \
            f"{huge['plan_validation_attempts']} == {tiny['plan_validation_attempts']}"
E       AssertionError: a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a 1-step/1-file plan, but it escalated at the same attempt count: 2 == 2
E       assert 'escalated' != 'escalated'

tests/test_machine.py:237: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size` fails on base `main` too -- the bug is not already fixed upstream
```
    f"{huge['plan_validation_attempts']} == {tiny['plan_validation_attempts']}"
E       AssertionError: a 24-step/10-file plan (TICKET-041's shape) must get more attempts than a 1-step/1-file plan, but it escalated at the same attempt count: 2 == 2
E       assert 'escalated' != 'escalated'

tests/test_machine.py:237: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-zbxd3bz5/base
      Built pipeline @ file:///tmp/pipeline-base-zbxd3bz5/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 09:29:19Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 · implementing · todo

**implementing todo (23 steps)**

- [x] 1. confirm baseline failure
- [x] 2. gate.py: PLAN_STEP_RE from PLAN_STEP_RULE
- [x] 3. gate.py: plan_steps()
- [x] 4. test_gate.py: test_plan_steps_counts_only_unfenced_numbered_steps
- [x] 5. run test_gate.py, commit
- [x] 6. machine.py: SIZE_SCALED, STEPS_PER_ATTEMPT, FILES_PER_ATTEMPT, BOUND_CEILING
- [x] 7. machine.py: _size()
- [x] 8. machine.py: bound_for()
- [x] 9. machine.py: charge() uses bound_for()
- [x] 10. test_machine.py: edit size test
- [x] 11. run size test
- [x] 12. test_machine.py: ceiling/spare test
- [x] 13. run test_machine.py, commit
- [x] 14. supervisor.py: import bound_for, plan_steps
- [x] 15. supervisor.py: advance() seeds plan_steps/plan_files
- [x] 16. supervisor.py: escalation reason uses bound_for()
- [x] 17. test_dispatch.py: test_advance_seeds_the_plan_size_from_the_ticket
- [x] 18. test_dispatch.py: fix counters == {} assert
- [x] 19. run test_dispatch.py, commit
- [x] 20. README.md bullet update
- [x] 21. CLAUDE.md invariant 3 update
- [x] 22. SKILL.md class table line
- [x] 23. full suite + guard script, commit

### 2026-08-24 · implementing · result=ok

**implementing done: 4 commits, 269 tests pass**

Executed all 23 plan steps in order, TDD throughout: each new test verified
RED for the stated reason before its code landed, then GREEN.

Commits on `ticket/047`:
- `ed48a3f` -- `plan_steps()` in `pipeline/core/gate.py`
- `5b4c3a5` -- `bound_for()`, `SIZE_SCALED`, `BOUND_CEILING` in `pipeline/core/machine.py`
- `1338d23` -- `advance()` seeds `plan_steps`/`plan_files`, escalation reason uses `bound_for()`
- `a8eff30` -- README.md, CLAUDE.md, SKILL.md prose

`uv run --group dev pytest -q`: 269 passed.
`./pipeline/hooks/test_dangerous_commands.py`: all passed.
`tests/test_machine.py::test_plan_validation_budget_ignores_the_plans_size`: passes.

No deviation from the plan. `transition()` is in `machine.FENCED`, so this
parks at `awaiting-merge` for a human -- expected per the plan and DEC-031.

### 2026-08-24 09:38:10Z · implementing · session · session=010b606c-08ea-4be3-b79d-eb5783fc3f0d

`implementing` ran as session `010b606c-08ea-4be3-b79d-eb5783fc3f0d`
- replay: `claude --resume 010b606c-08ea-4be3-b79d-eb5783fc3f0d`
- log: `.project/logs/TICKET-047-implementing-010b606c.log`

### 2026-08-24 09:38:10Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed all 23 plan steps TDD, 4 commits, 269 tests + guard script pass; parks at awaiting-merge because transition() is fenced.

### 2026-08-24 · review · result=ok

**review: no blocking findings** (delta `b06ed44..a8eff30`, first review pass)

`uv run --group dev pytest -q` -- `269 passed in 10.64s`. The eight tests the
acceptance criteria name pass in one run -- `8 passed in 0.07s`.

Checked and refuted, each with the line that refutes it:

1. `charged` misreads `plan_steps` as the counter that hit its bound --
   refuted, `pipeline/daemon/supervisor.py:108` seeds `t.counters` before the
   `transition()` call at line 110, so both dicts hold the same value.
2. The seed reads a stale plan or a stale file list -- refuted,
   `supervisor.py:870` builds `t` as `replace(snap, body=agent.body)` and line
   915 assigns `files_declared` from the validated claim, both before
   `advance()` at line 921.
3. A second `transition()` caller skips the seed -- refuted,
   `grep -rn "transition(" pipeline/` returns `supervisor.py:110` only.
4. Off-by-one at the ceiling -- refuted, `charge()` escalates on `>= bound`, so
   a 24-step/10-file `bugfix` gets bound 5 and its fifth planning run.
5. `BOUNDS` left dangling in the supervisor -- refuted, `grep -n "BOUNDS"
   pipeline/daemon/supervisor.py` returns nothing.

Non-blocking:

1. minor -- `pipeline ls` (`pipeline/cli/main.py:221`) and `advance()`'s print
   (`supervisor.py:141`) now render `plan_steps` and `plan_files` in the
   counters column beside the attempt counters.
2. minor -- `README.md`'s "two failures for most" is loose: `refactor` already
   had 3 for `review_loops` and `plan_validation_attempts` before this change.

I did not run `./pipeline/hooks/test_dangerous_commands.py`: the guard refused
it -- "Blocked by the pipeline guard (review): `test_dangerous_commands.py` is
not on the read-only allowlist." The delta touches no file under
`pipeline/hooks/`, so the guard is byte-identical to `main`. `implementing`
recorded that script as passing.

### 2026-08-24 09:43:07Z · review · session · session=ace5f7bb-93fe-4f39-aa25-0fb64b2dff0e

`review` ran as session `ace5f7bb-93fe-4f39-aa25-0fb64b2dff0e`
- replay: `claude --resume ace5f7bb-93fe-4f39-aa25-0fb64b2dff0e`
- log: `.project/logs/TICKET-047-review-ace5f7bb.log`

### 2026-08-24 09:43:07Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed b06ed44..a8eff30: no blocking findings; 269 passed, the 8 acceptance tests pass, 5 candidate findings refuted at a line, 2 minor recorded

### 2026-08-24 09:43:19Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/core/machine.py:transition`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-047` lands it; `pipeline resume TICKET-047 --stage planning` sends it back.

### 2026-08-24 10:07:30Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 10:09:55Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/047


Rebasing (1/5)Rebasing (2/5)Rebasing (3/5)Rebasing (4/5)Rebasing (5/5)Successfully rebased and updated refs/heads/ticket/047.
Already up to date.
Updating 8b1a245..5561539
Fast-forward
 .claude/skills/file-ticket/SKILL.md |  4 ++++
 CLAUDE.md                           |  3 +++
 README.md                           |  5 +++--
 pipeline/core/gate.py               | 15 ++++++++++++++-
 pipeline/core/machine.py            | 35 ++++++++++++++++++++++++++++++++++-
 pipeline/daemon/supervisor.py       | 15 +++++++++++----
 tests/test_dispatch.py              | 25 ++++++++++++++++++++++++-
 tests/test_gate.py                  | 15 ++++++++++++++-
 tests/test_machine.py               | 31 +++++++++++++++++++++++++++++++
 9 files changed, 138 insertions(+), 10 deletions(-)

```

### 2026-08-24 10:09:55Z · merging · decision

decision recorded as `DEC-047`
