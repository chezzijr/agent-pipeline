---
id: TICKET-078
stage: done
class: feature
branch: ticket/078
test_file: tests/test_config.py::test_render_cap_does_not_scale_with_diff_size
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/config.py
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- pipeline/templates/pipeline.toml
- tests/test_config.py
- tests/test_dispatch.py
- tests/test_machine.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 23
  plan_files: 9
  no_result: 0
  rebase_conflicts: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 6d248d1c-5fee-4485-a6c6-686669417094
  log: .project/logs/TICKET-078-review-6d248d1c.log
approved_by: 'chezzijr (via Claude Code, while away; reviewer also filed this ticket
  -- audit in thread). The rebase conflict with 077 produced a better design: scaling
  inside stage_cap() rather than at the render() call site, so rec[''cap''] names
  the enforced number.'
approved_at: '2026-08-27T20:15:13.863335+00:00'
---

## Summary

Re-planned 2026-08-28 against the post-TICKET-077 code. The design is
unchanged: `cap_for()` (`pipeline/core/machine.py`) grows a stage's dollar
cap by one dollar per 4 declared files or per 8 plan steps, capped at
`USD_CEILING_FACTOR = 2` times the stage's own number. `cap_config()`
(`pipeline/core/config.py`) decides which spawns scale: `USD_SCALED` holds
the three review stages, a project's own `max_usd` pins the cap, and
`scale_usd` forces either way. `spawn()` puts the ticket's counters in
`cfg["counters"]`. Review's $4 cap on a 15-file, 40-step plan becomes $8.

Implemented 2026-08-28: all 23 plan steps done via TDD, one RED/GREEN cycle
per step group, four commits (`c635292`, `85d4573`, `06f53c7`, `7617a65`).
The reproduction test passes: `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size`.
Full suite green (`403 passed`) and the guard script passes
(`./pipeline/hooks/test_dangerous_commands.py`). No deviation from the plan.

Review passed on 2026-08-28 with no blocking findings. It re-ran both suites
(`403 passed in 19.30s`, `guard: all passed`), confirmed `spawn()` is the only
production caller of `render()` and that both `stage_cap()` calls sit below the
`cap_config()` rebind, and confirmed `fenced_touches(Path('.'), 'main')`
returns `[]`. Three nits stand, none blocking: `cap_config()` costs one extra
`git show` per spawn; the reproduction test asserts the absence of `4` rather
than the presence of `8`; and a project writing a literal `counters` key into
`[stages.<name>]` scales its own pinned cap.

One composition change from the previous plan. TICKET-077 made
`stage_cap()` the single definition of a stage's cap, and
`pipeline/daemon/supervisor.py:460` uses it for `rec["cap"]`, the number
`_finish()` names in a budget-kill escalation. So `cap_for()` goes INSIDE
`stage_cap()`, not around its call site at `pipeline/core/config.py:403`.
Wrapping the call site would leave `rec["cap"]` unscaled and the
escalation message wrong.

Every line reference below was re-verified on this branch. Constraining
records: DEC-047, DEC-065, DEC-058, DEC-077. Nothing is superseded. No
questions for the human.

Plan-validation passed the plan on 2026-08-28 and re-verified every anchor
independently. `stage_cap()` has exactly two callers,
`pipeline/core/config.py:403` and `pipeline/daemon/supervisor.py:460`, so
scaling inside it is the only edit that makes the rendered flag and
`rec["cap"]` one number. The plan supersedes the human collision note's
call-site wrapper for that reason, and says so. Implementing may proceed as
written. Two anchors drift by one line and do not change any edit: the
`spawn()` ticket load is 397-403, not 397-402, and the README Settings
bullet naming `max_usd` is line 497 inside the 495-500 block the plan cites.

the review budget does not scale with the diff it has to read

`max_usd` is a per-stage constant in the stage's own frontmatter
(`pipeline/stages/<name>.md`), so `review` is given the same cap whether the
diff is four lines or four files. `BOUNDS` already rejects that model for the
other resource it hands out: `bound_for()` scales
`plan_validation_attempts` by `plan_steps // 8` and `plan_files // 4`, capped
at `BOUND_CEILING`, precisely because a bigger plan needs more tries.

Observed 2026-08-27 on another project: a $4 review cap covered ten small
tickets and was exhausted by the one 677-line, 15-file diff. The stage was
killed mid-verdict (see TICKET-077 for what that costs). The cap was not wrong
for ten of the eleven tickets; it was wrong for the one whose diff was an
order of magnitude larger.

Expected: the cap a review stage is spawned with grows with the size of what
it must read, the way an attempt budget already grows with the size of what it
must judge -- with a ceiling, so a runaway diff cannot buy an unbounded spend.

The inputs already exist. `counters["plan_files"]` and `counters["plan_steps"]`
are recorded, and the diff itself is measurable at spawn time
(`git diff --stat` against base in the ticket's worktree). Which of those is
the honest measure is planning's call: `plan_files` is what the plan DECLARED,
and the review reads what was actually written.

Two constraints on any answer:

- The ceiling matters more than the slope. An uncapped scale turns one large
  ticket into an unbounded bill, which is the failure `BOUND_CEILING` exists
  to prevent for attempts.
- `max_usd` is read from the stage's frontmatter and merged with the project's
  `[stages.<name>]` table (`stage_config()`). A scaled value has to compose
  with a project override without silently overriding the operator's number --
  same direction rule as TICKET-069's `min()`: a computed cap should not
  exceed what the operator asked for unless the operator asked for scaling.

## Reproduction

test: `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size`
command: `uv run --group dev pytest -q tests/test_config.py::test_render_cap_does_not_scale_with_diff_size`

output:
```
E       AssertionError: expected the cap to grow with plan_files/plan_steps the way bound_for() scales plan_validation_attempts, but render() emitted the same --max-budget-usd 4 for a 15-file, 40-step plan as for one with no counters at all
E       assert '--max-budget-usd 4' not in 'claude -p -...p/t.result" '
E
E         '--max-budget-usd 4' is contained here:
E           rmissions --max-budget-usd 4 --add-dir /tmp/.project -- "Work ticket TICKET-001. Your prompt carries a bounded view of /tmp/t.md; open that file only for what the view says it omitted, and read only the lines you need. When finished write /tmp/t.result"
```

expect: expected the cap to grow with plan_files/plan_steps the way bound_for() scales plan_validation_attempts, but render() emitted the same --max-budget-usd 4 for a 15-file, 40-step plan as for one with no counters at all

Reproduced 2026-08-28 on the branch recut from base after the earlier rebase
conflict. TICKET-077 has since merged and moved the cap line: `render()`
computes `cap=stage_cap(cfg, hcfg)` at `pipeline/core/config.py:403`, not
line 305/388 as the plan and human collision-note say, and `stage_cap()`
(line 336) is the single place `cap=cfg.get(...)` used to live. The bug is
unchanged: neither function reads `cfg["counters"]`, so the cap still does
not scale. The test above is written and committed against this current
code and passes the reproduction check. Every line reference in `## Digest`
and `## Plan` below predates the TICKET-077 merge and needs re-verification
before implementing; step 6's collision note is now moot since `stage_cap()`
already exists -- the correct target is `cap=cap_for(stage_cap(cfg, hcfg), cfg.get("counters") or {})`
at line 403.

## Digest

Files touched: `pipeline/core/machine.py` (the numbers and a new `cap_for()`), `pipeline/core/config.py` (`stage_cap()` scales, and a new `cap_config()`), `pipeline/daemon/supervisor.py` (`spawn()` threads the ticket's counters), `tests/test_machine.py`, `tests/test_config.py`, `tests/test_dispatch.py`, plus `README.md`, `CLAUDE.md` and `pipeline/templates/pipeline.toml` for the new project key.

Key functions, every line number re-verified on this branch at `787680a`: `stage_cap(cfg, hcfg)` (`pipeline/core/config.py:336`) returns `cfg.get("max_usd", hcfg.get("max_usd", 5))` and is the single definition of a stage's dollar cap (TICKET-077). `render()` (`pipeline/core/config.py:344`) calls it at line 403 as `cap=stage_cap(cfg, hcfg)`. `bound_for()` (`pipeline/core/machine.py:70`) is the model to mirror: `min(base + max(steps // STEPS_PER_ATTEMPT, files // FILES_PER_ATTEMPT), BOUND_CEILING)`, with `_size()` (`pipeline/core/machine.py:62`) reading a hostile counter as 0. `BOUND_CEILING = 5` is at `pipeline/core/machine.py:25`; `bound_for()` ends at line 78 and `transition` starts at line 81. `stage_config()` (`pipeline/core/config.py:51`) merges packaged frontmatter with `project_stage_config()` (`pipeline/core/config.py:28`), the only place the operator's own `[stages.<name>]` table is visible on its own.

Entry points: `spawn()` (`pipeline/daemon/supervisor.py:345`) builds `cfg = stage_config(stage, project)` at line 349, loads the ticket for the view at lines 397-402, calls `render()` at line 409, and builds the child record at lines 454-461. It is the only caller of `render()` in the package; `tests/test_pty.py:376` and `tests/test_harness.py` call `render()` directly.

Gotcha, and the one change from the previously validated plan: `stage_cap()` is called TWICE, at `pipeline/core/config.py:403` for `render()` and at `pipeline/daemon/supervisor.py:460` for `rec["cap"]`. `_finish()` reads `rec["cap"]` at `pipeline/daemon/supervisor.py:1085` and names it in the budget-kill escalation. Wrapping only the call site at line 403, which is what the human collision note and the earlier plan text both say, would scale the rendered flag and leave the escalation naming the unscaled number. Putting `cap_for()` inside `stage_cap()` scales both from one definition, which is what the TICKET-077 docstring demands: "it must be the number `render()` passed". `cfg` is bound once in `spawn()`, at line 349, so a rebind before line 409 also covers line 460.

Gotcha: the reproduction test passes the size inside `cfg`, as `cfg["counters"]`, and calls `render()` with no new argument (`tests/test_config.py:26`). So the scaling must read `cfg.get("counters")`; a new keyword argument leaves the test red.

Gotcha: `advance()` (`pipeline/daemon/supervisor.py:115`) rewrites `counters["plan_steps"]` and `counters["plan_files"] = len(t.files_declared)` before every transition, so both keys are on the ticket when `review` is spawned. No `git diff --stat` is needed at spawn time, and this plan adds none.

Gotcha: `spawn()` already loads the `Ticket` for `stage_view()` inside a `try/except PipelineError`, because `tests/test_pty.py` spawns with no ticket on disk. The counters must ride that same load, and the no-ticket path must still yield an empty dict.

Gotcha: `rec["cap"]` makes a spawn-level assertion possible without replacing `supervisor.render`. `pipeline/harnesses/fake.toml` has `max_usd = 0` and no cap placeholder in its `cmd`, but `stage_cap()` prefers `cfg["max_usd"]`, which is 4 for `review`, so a fake-harness spawn still records the real scaled number.

Gotcha: `cap_for(0, counters)` is `min(0 + max(5, 3), 0)`, which is 0, so `pipeline/harnesses/fake.toml` and `pipeline/harnesses/codex.toml` keep their `max_usd = 0`.

Gotcha: `machine.FENCED` fences `pipeline/core/machine.py` at symbol granularity (`fenced_touches()`, `pipeline/core/fence.py`) for `transition`, `CONTROL_FIELDS` and `FENCED` only. New constants beside `BOUND_CEILING` (line 25) and a new function after `bound_for()` (ends line 78) do not overlap those spans. `.project/pipeline.toml` is not edited here; `pipeline/templates/pipeline.toml` is a different file and is not fenced.

Gotcha: `pipeline/core/machine.py` has no import line at all, so `pipeline/core/config.py` importing it adds no cycle.

## Decisions checked

- DEC-047 (TICKET-047) -- binding, and the model this plan copies: "The formula is base + max(steps // 8, files // 4), capped at 5" and "a bound that grows without limit is not a bound". It also fixes that the plan size reaches the dispatcher through `counters`, never through a read. This plan keeps both: the same shape of formula, an explicit ceiling, and the size still arriving via `counters`.
- DEC-065 (TICKET-065) -- binding on `SIZE_SCALED` membership: a counter joins only when a bigger plan really earns more of that resource. The new `USD_SCALED` set follows the same rule and holds the three diff-reading review stages only.
- DEC-058 (TICKET-058) -- binding on provenance: `project_config()` reads `.project/pipeline.toml` from HEAD, so a stage cannot widen its own budget by committing a config on its branch. The new `scale_usd` key inherits that by going through `project_stage_config()`.
- DEC-077 (TICKET-077) -- binding, and the reason step 6 changed shape from the previously validated plan. It fixes that a budget kill escalates on the first kill naming the cap, and `stage_cap()` exists so `rec["cap"]` and the rendered flag are one number. This plan complies by scaling inside `stage_cap()` rather than around its call site.
- DEC-037 and DEC-038 -- cited by DEC-058 for that same provenance rule.
- DEC-051 (TICKET-051) -- read, not binding here: it constrains `--grant`, which touches attempt counters and not `max_usd`.
- DEC-079 (TICKET-079) -- read, not binding here: it constrains how a Tier A acceptance criterion is written, not what a cap is.
- TICKET-069 carries the direction rule this plan applies to money, and has no decision record on disk; `ls .project/decisions | grep 069` returns nothing.

Grep terms used against `.project/decisions/`: `max_usd`, `budget`, `cap`, `stage_cap`, `bound_for`, `BOUND_CEILING`, `SIZE_SCALED`, `plan_files`, `plan_steps`, `scale`, `ceiling`, `min(`, `superseded-by`.

## Plan

1. Add `test_cap_for_scales_with_plan_size_and_stops_at_the_ceiling` to `tests/test_machine.py`, below `test_plan_validation_budget_ignores_the_plans_size` which ends at line 249, asserting `M.cap_for(4, {}) == 4`, `M.cap_for(4, {"plan_files": 8}) == 6`, `M.cap_for(4, {"plan_files": 15, "plan_steps": 40}) == 8`, `M.cap_for(4, {"plan_files": 4000}) == 8` with the message `"the ceiling is the point"`, `M.cap_for(4, {"plan_files": "many"}) == 4` with the message `"a hostile counter reads as 0"`, and `M.cap_for(0, {"plan_files": 15}) == 0` with the message `"a harness with no cap flag keeps its 0"`.
2. Run `uv run --group dev pytest -q tests/test_machine.py::test_cap_for_scales_with_plan_size_and_stops_at_the_ceiling` and expect `AttributeError: module 'pipeline.core.machine' has no attribute 'cap_for'`.
3. In `pipeline/core/machine.py`, directly below `BOUND_CEILING = 5` at line 25, add `USD_SCALED = {"review", "quick-review", "holistic-review"}`, `USD_FILES_PER_DOLLAR = 4`, `USD_STEPS_PER_DOLLAR = 8` and `USD_CEILING_FACTOR = 2`, with a comment stating four things: the cap grows one dollar per 4 declared files or per 8 plan steps; a $4 review cap covered ten small tickets on 2026-08-27 and was exhausted by one 677-line, 15-file diff; the ceiling is twice the stage's own number, so one runaway diff cannot buy an unbounded spend; the other stages stay out until evidence says otherwise.
4. In `pipeline/core/machine.py`, directly below `bound_for()` which ends at line 78 and above `def transition` at line 81, add `def cap_for(base, counters: dict):` which returns `base` when `counters` is not a dict or is empty, and when `base` is not an `int` or `float` with `bool` excluded, and otherwise returns `min(base + max(_size(counters, "plan_steps") // USD_STEPS_PER_DOLLAR, _size(counters, "plan_files") // USD_FILES_PER_DOLLAR), base * USD_CEILING_FACTOR)`; its docstring says empty `counters` means no scaling and that `cap_config()` in `pipeline/core/config.py` decides which spawns get it.
5. Run `uv run --group dev pytest -q tests/test_machine.py`, expect no failures, and commit `pipeline/core/machine.py` and `tests/test_machine.py` as `feat(TICKET-078): cap_for() scales a USD cap by plan size`.
6. In `pipeline/core/config.py`, add `from pipeline.core.machine import USD_SCALED, cap_for` below the `from pipeline.core import PipelineError` import at line 15, and change the body of `stage_cap()` at line 341 from `return cfg.get("max_usd", hcfg.get("max_usd", 5))` to `return cap_for(cfg.get("max_usd", hcfg.get("max_usd", 5)), cfg.get("counters") or {})`, adding one docstring paragraph saying `cfg["counters"]` is the plan size the cap scales by, that its absence means no scaling, and that the scaling lives here rather than at the `render()` call site so `rec["cap"]` in `pipeline/daemon/supervisor.py` names the same number (DEC-077).
7. Run `uv run --group dev pytest -q tests/test_config.py tests/test_pty.py tests/test_harness.py tests/test_dispatch.py` and expect no failures: `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size` now passes, and `tests/test_pty.py::test_planning_is_interactive_and_never_rendered_under_print_mode` still finds `--max-budget-usd 5`.
8. In `tests/test_config.py`, add `cap_config` to the `from pipeline.core.config import ...` list at line 7, and add a module-level helper `def cmd(cfg):` above `test_render_cap_does_not_scale_with_diff_size` returning `render(harness("claude-code"), cfg, tid="TICKET-001", project=Path("/tmp"), ticket=Path("/tmp/t.md"), result_file=Path("/tmp/t.result"), session="s", prompt=Path("/tmp/t.md"))`.
9. Add `test_a_project_max_usd_override_is_not_scaled_past` to `tests/test_config.py`: `d, sh = git_project()`, append the two lines `[stages.review]` and `max_usd = 2` to `d / ".project" / "pipeline.toml"`, run `sh("git add -A && git commit -qm config")`, set `cfg = cap_config("review", stage_config("review", d), d, {"plan_files": 15, "plan_steps": 40})`, assert `"counters" not in cfg` with the message `"an operator own max_usd was scaled past"`, and assert `"--max-budget-usd 2" in cmd(cfg)`.
10. Add `test_a_project_can_ask_for_scaling_on_top_of_its_own_cap` to `tests/test_config.py`: the same `git_project()` setup ending in `sh("git add -A && git commit -qm config")`, appending the three lines `[stages.review]`, `max_usd = 6` and `scale_usd = true`, then assert `"--max-budget-usd 11" in cmd(cap_config("review", stage_config("review", d), d, {"plan_files": 15, "plan_steps": 40}))`, since 6 + max(40 // 8, 15 // 4) is 11 and the ceiling is 12.
11. Add `test_the_project_decides_which_stages_scale_their_cap` to `tests/test_config.py`: with `d, _ = git_project()` and `counters = {"plan_files": 15, "plan_steps": 40}`, assert `"counters" in cap_config("review", stage_config("review", d), d, counters)`, assert `"counters" not in cap_config("implementing", stage_config("implementing", d), d, counters)` and `"--max-budget-usd 8" in cmd(cap_config("implementing", stage_config("implementing", d), d, counters))`, then on a second project `d2, sh2 = git_project()` carrying the lines `[stages.review]` and `scale_usd = false` committed with `sh2("git add -A && git commit -qm config")`, assert `"counters" not in cap_config("review", stage_config("review", d2), d2, counters)`.
12. Run `uv run --group dev pytest -q tests/test_config.py` and expect the three new tests to fail with `ImportError: cannot import name 'cap_config' from 'pipeline.core.config'`.
13. In `pipeline/core/config.py`, directly below `stage_config()` which ends at line 60 and above `agent_stages()` at line 63, add `def cap_config(stage: str, cfg: dict, project: Path | None, counters: dict) -> dict:` which reads `override = project_stage_config(project, stage)`, takes `want = override.get("scale_usd")`, sets `want = stage in USD_SCALED and "max_usd" not in override` when `want is None`, and returns `{**cfg, "counters": counters}` when `want` is truthy and `cfg` otherwise; its docstring says a computed cap never exceeds the operator's own `max_usd` unless the operator sets `scale_usd = true`, the same direction as the TICKET-069 rule.
14. Run `uv run --group dev pytest -q tests/test_config.py`, expect no failures, and commit `pipeline/core/config.py` and `tests/test_config.py` as `feat(TICKET-078): scale a review cap, never past the operator own number`.
15. Add `test_spawn_threads_the_tickets_counters_into_the_review_cap` to `tests/test_dispatch.py` beside `test_a_project_override_reaches_the_spawned_command_and_prompt` at line 1030: build `d = project(FIXTURE.replace("stage: plan-validation", "stage: review").replace("counters: {}", "counters: {plan_files: 15, plan_steps: 40}"))`, call `rec = supervisor.spawn(d, d, "TICKET-001", "review", harness("fake"))`, then `rec["proc"].wait()` and `supervisor.close_child(rec)`, assert `rec["cap"] == 8` with the message `"spawn() did not scale the 4 dollar review cap by the ticket plan size"`, then repeat those three spawn calls on `d2 = project()` and assert `rec2["cap"] == 4` with the message `"an empty counters map must not scale the cap"`.
16. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_spawn_threads_the_tickets_counters_into_the_review_cap` and expect it to fail on `assert 4 == 8`, because `spawn()` never puts the ticket's counters in `cfg`.
17. In `pipeline/daemon/supervisor.py`, add `cap_config` to the `from pipeline.core.config import (...)` list at lines 17-21 before `compose_prompt`, and rewrite the ticket load at lines 397-402 as `counters: dict = {}` above the `try`, with `t = Ticket.find(project, tid)` and `counters, view = t.counters, stage_view(t, stage)` inside it, keeping the existing `except PipelineError: view = ""` and its comment unchanged.
18. In `pipeline/daemon/supervisor.py`, insert `cfg = cap_config(stage, cfg, project, counters)` immediately above the `cmd = render(...)` call at line 409, with a comment saying a review cap scales with the plan its diff came from the way `bound_for()` scales an attempt budget (DEC-047), that the counters ride the ticket load the view already pays for, and that this rebind must precede the `stage_cap(cfg, hcfg)` call at line 460 so `rec["cap"]` carries the scaled number.
19. Run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_pty.py tests/test_harness.py tests/test_daemon.py`, expect no failures, and commit `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py` as `feat(TICKET-078): spawn() gives the cap the ticket plan size`.
20. Document the key in `pipeline/templates/pipeline.toml` in the stage-override comment block at lines 30-35: add the commented example `# scale_usd = true` under `# skills = []` at line 35, plus two comment lines saying a review stage grows its `max_usd` with the plan's declared files and steps up to twice its value, and that a `max_usd` set here pins the cap instead unless `scale_usd = true` is set with it.
21. Document the behaviour in `README.md` in the `## Per-project stage config` section, inserting after line 500, which ends the Settings bullet naming `max_usd` at lines 495-500, and before the Prose bullet at line 501: three sentences saying `review`, `quick-review` and `holistic-review` are spawned with `max_usd` grown by one dollar per 4 declared files or per 8 plan steps, whichever is larger, capped at twice the stage's own number; that a project's own `max_usd` pins the cap and is never scaled past unless the table also sets `scale_usd = true`; and that `scale_usd = false` turns scaling off for a stage that has it by default.
22. Add one sentence to invariant 3 in `CLAUDE.md`, directly after the sentence ending "`lease_expiries` and `no_result` stay on `MAX_ATTEMPTS`" at line 29, saying `cap_for()` scales the `max_usd` of a stage the same way for the stages in `USD_SCALED`, capped at `USD_CEILING_FACTOR` times the stage's own number, and that a project's own `max_usd` is never scaled past unless it also sets `scale_usd = true`.
23. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect no failures from either, and commit `README.md`, `CLAUDE.md` and `pipeline/templates/pipeline.toml` as `docs(TICKET-078): a review cap scales with the plan, up to twice its number`.

## Acceptance criteria

- `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size` passes: `render()` emits `--max-budget-usd 8` for the 15-file, 40-step counters and `--max-budget-usd 4` for none.
- `tests/test_machine.py::test_cap_for_scales_with_plan_size_and_stops_at_the_ceiling` passes, and it goes red if the ceiling is dropped:
  `cap_for(4, {"plan_files": 4000})` must be `8`, not `1004`.
- `tests/test_config.py::test_a_project_max_usd_override_is_not_scaled_past` passes: with `[stages.review]` and `max_usd = 2` committed, the rendered command carries `--max-budget-usd 2`.
- `tests/test_config.py::test_a_project_can_ask_for_scaling_on_top_of_its_own_cap` passes: with `max_usd = 6` and `scale_usd = true` committed, the rendered command carries `--max-budget-usd 11`.
- `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` passes: `implementing` still renders `--max-budget-usd 8`, and `scale_usd = false` removes scaling from `review`.
- `tests/test_dispatch.py::test_spawn_threads_the_tickets_counters_into_the_review_cap` passes: a `review` spawn on a 15-file, 40-step ticket records `rec["cap"] == 8`, the number `_finish()` would name in a budget-kill escalation, and a spawn with empty counters records `rec["cap"] == 4`.
- `tests/test_pty.py::test_planning_is_interactive_and_never_rendered_under_print_mode` still passes: `planning` is outside `USD_SCALED`, so it still renders `--max-budget-usd 5`.
- `uv run --group dev pytest -q` reports no failures, and `./pipeline/hooks/test_dangerous_commands.py` reports no failures.

## Decisions

**`cap_for()` goes inside `stage_cap()`, not around its call site in `render()`.** DEC-077 made `stage_cap()` the one definition of a stage's dollar cap, because `_finish()` names that cap when a budget kill escalates and `pipeline/daemon/supervisor.py:460` reads it separately for `rec["cap"]`. Scaling at the `render()` call site would render `--max-budget-usd 8` and then escalate saying the stage was killed at its 4 dollar cap. Any future change that moves the cap must keep the rendered flag and `rec["cap"]` computed by the same call. `spawn()` binds `cfg` once, so the `cap_config()` rebind must sit above `render()` and therefore above the child record too.

**The cap scales on `counters["plan_files"]` and `counters["plan_steps"]`, not on a measured `git diff --stat`.** The ticket left the measure to planning. Both counters are already on the ticket -- `advance()` rewrites them before every transition (DEC-047) -- so `spawn()` reads them off the `Ticket` it already loads for `stage_view()`, and the spawn path gains no subprocess. A measured diff is the more exact number for a review, but it is 0 for every stage spawned before any code lands, so one function would mean two things by stage. The declared count is close to what a review reads, and the ceiling absorbs the error. If a ticket ever shows the declared count badly under-reporting its diff, the fix is to measure the diff in `spawn()` and pass it as `counters["plan_files"]`; `cap_for()` does not change.

**The ceiling is a multiple of the stage's own cap, not one global dollar figure.** `BOUND_CEILING` can be a single number because every attempt costs about the same. A dollar cap cannot: `quick-review` asks 2 dollars and `implementing` asks 8, so a flat ceiling either strangles one or hands the other a raise. `USD_CEILING_FACTOR = 2` means the worst case of a stage is exactly twice what its frontmatter says. That is the property to keep if the slope is ever retuned. It also makes `cap_for(0, c)` return 0, which is what keeps `codex.toml` and `fake.toml` capless.

**`USD_SCALED` holds the three review stages and nothing else.** The cost of a review is set by how much diff it reads, which is what this ticket measured. `implementing` is bounded by what it writes and `planning` by what it decides; neither has evidence behind it, and DEC-065 is the rule that keeps an unevidenced member out of a scaled set. Add a stage here only with a run that was killed at its cap.

**A project's own `max_usd` is a pin, not a base, unless the table also sets `scale_usd = true`.** Same direction as the TICKET-069 rule: the computed number never exceeds the operator's. `scale_usd` is read through `project_stage_config()`, so it comes from `.project/pipeline.toml` at HEAD (DEC-058) and a ticket branch cannot grant itself money by committing one. `scale_usd = false` is the opt-out for a stage that scales by default; the key absent leaves `USD_SCALED` to decide.

**The size reaches the cap through `cfg["counters"]`, not through a new argument.** `cfg` is the one channel every existing `render()` caller shares, and the reproduction test drives that shape. The consequence: `cap_config()`, not `stage_cap()`, decides which spawns scale. `stage_cap()` scales whenever the `cfg` it is handed carries counters, so putting a `counters` key in a stage config is what asks for scaling.

**`USD_FILES_PER_DOLLAR` and `USD_STEPS_PER_DOLLAR` repeat the values of `FILES_PER_ATTEMPT` and `STEPS_PER_ATTEMPT` deliberately.** They are the same numbers in different units, attempts and dollars. One shared constant would tie a retune of one to the other. Retune them independently.

## Rollback

Revert the four commits from steps 5, 14, 19 and 23 with `git revert`, newest first, and the flat cap returns: `stage_cap()` goes back to `cfg.get("max_usd", hcfg.get("max_usd", 5))` and every stage is spawned with its frontmatter number. Nothing persists across the revert. No counter and no config key is required by anything else, and a project that had added `scale_usd` to `.project/pipeline.toml` keeps an inert key, exactly as any unknown stage-table key is inert today. For a partial rollback that keeps the plumbing, set `USD_SCALED = set()` in `pipeline/core/machine.py`: every cap is the operator's number again, and only `tests/test_config.py::test_the_project_decides_which_stages_scale_their_cap` and `tests/test_dispatch.py::test_spawn_threads_the_tickets_counters_into_the_review_cap` go red.

## Thread

### 2026-08-27 16:15:56Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-28 · triage · result=ok

Confirmed: `render()` (`pipeline/core/config.py`) computes
`cap=cfg.get("max_usd", hcfg.get("max_usd", 5))` with no size input, unlike
`bound_for()` (`pipeline/core/machine.py`), which scales
`plan_validation_attempts` by `plan_steps`/`plan_files`. `spawn()`
(`pipeline/daemon/supervisor.py:395`) never forwards the ticket's counters
into `render()` either, so there is no code path today that could vary the
cap by diff size.

Wrote and committed a failing test,
`tests/test_config.py::test_render_cap_does_not_scale_with_diff_size`, on
branch `ticket/078`, commit `af60a51`. It calls `render()` with the same
`max_usd` and two different `counters` payloads and asserts the emitted
`--max-budget-usd` flag differs; it does not.

This is not a `chore`: which of `plan_files` vs a measured `git diff --stat`
to scale on, the slope, the ceiling, and how a scaled value composes with a
project's `[stages.<name>]` override are all open design choices the ticket
itself defers to planning. Files it will likely touch:
`pipeline/core/config.py` (`render()`), `pipeline/core/machine.py`
(new scaling function or extended `SIZE_SCALED`), and
`pipeline/daemon/supervisor.py` (`spawn()`, to thread counters through).

### 2026-08-27 17:08:24Z · triage · session · session=52a0eb48-cf27-45fd-a3b3-7081692312b4

`triage` ran as session `52a0eb48-cf27-45fd-a3b3-7081692312b4`
- replay: `claude --resume 52a0eb48-cf27-45fd-a3b3-7081692312b4`
- log: `.project/logs/TICKET-078-triage-52a0eb48.log`

### 2026-08-27 17:08:24Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced flat review cap with failing test tests/test_config.py::test_render_cap_does_not_scale_with_diff_size

### 2026-08-28 · planning · result=ok

Plan written, 23 steps, 9 files. Scope is one subsystem: the USD cap a spawn
is given. Nothing else is touched.

Three seams, in order: `cap_for()` (`pipeline/core/machine.py`) computes the
scaled number, `cap_config()` (`pipeline/core/config.py`) decides which spawns
get it, and `spawn()` (`pipeline/daemon/supervisor.py`) supplies the size. The
size travels in `cfg["counters"]` because the reproduction test at
`tests/test_config.py:94` passes it there and calls `render()` with no new
argument.

The slope is one dollar per 4 declared files or per 8 plan steps, whichever is
larger -- the same arms `bound_for()` uses. The ceiling is twice the stage's
own `max_usd`, not one global figure, because `quick-review` asks $2 and
`implementing` asks $8. Review at $4 on the 15-file, 40-step counters renders
`--max-budget-usd 8`; the observed 677-line, 15-file diff asks for $7.

Two notes for later stages, both outside this ticket:

- `pipeline/harnesses/fake.toml` has no `{cap}` in its `cmd`, so no spawn-level
  test can read a cap out of a log. Step 15 records `cfg` by replacing
  `supervisor.render` instead.
- TICKET-069's `min()` direction rule has no record in `.project/decisions/`.
  I cited `TICKET-069.md:107` for it rather than a DEC id.

### 2026-08-27 17:17:01Z · planning · session · session=93fca4c3-c5e0-4cf8-910f-6f929fa556fb

`planning` ran as session `93fca4c3-c5e0-4cf8-910f-6f929fa556fb`
- replay: `claude --resume 93fca4c3-c5e0-4cf8-910f-6f929fa556fb`
- log: `.project/logs/TICKET-078-planning-93fca4c3.log`

### 2026-08-27 17:17:01Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned cap_for()/cap_config(): a review cap grows per 4 files or 8 steps, capped at 2x the stage's own max_usd

### 2026-08-27 19:39:28Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size` fails as required
```
nder() emitted the same --max-budget-usd 4 for a 15-file, 40-step plan as for one with no counters at all[0m
[1m[31mE       assert '--max-budget-usd 4' not in 'claude -p -...p/t.result" '[0m
[1m[31mE         [0m
[1m[31mE         '--max-budget-usd 4' is contained here:[0m
[1m[31mE         ?           ^^^^^^^^^^[0m
[1m[31mE           rmissions --max-budget-usd 4 --add-dir /tmp/.project -- "Work ticket TICKET-001. Your prompt carries a bounded view of /tmp/t.md; open that file only for what the view says it omitted, and read only the lines you need. When finished write /tmp/t.result" [0m
[1m[31mE         ?           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^[0m

[1m[31mtests/test_config.py[0m:98: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_config.py::[1mtest_render_cap_does_not_scale_with_diff_size[0m - AssertionError: expected the cap to grow with plan_files/plan_steps the way...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.04s[0m[31m ===============================[0m

```
- ok: `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size` fails on base `main` too -- the bug is not already fixed upstream
```
ests/test_config.py[0m:98: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_config.py::[1mtest_render_cap_does_not_scale_with_diff_size[0m - AssertionError: expected the cap to grow with plan_files/plan_steps the way...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-jd41fq1y/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-jd41fq1y/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-28 · plan-validation · result=ok

Tier B: PASS on all eight items.
long: the stage scores eight items and an unexplained pass is a fail.

1. Root cause: `render()` computes the cap from static config alone
   (`cap=cfg.get("max_usd", hcfg.get("max_usd", 5))`,
   `pipeline/core/config.py:305`) and `spawn()` never hands it the ticket's
   size. No path can vary a cap by plan size. The plan opens that path.
2. Decisions: DEC-047 fixes the formula shape and the counters channel,
   DEC-065 requires evidence for a scaled set, DEC-058 requires HEAD
   provenance. The plan complies on all three: `cap_config()` reads
   `project_stage_config()`, which reads HEAD.
3. Scope: 23 steps, 9 files, `class: feature`. Steps 20-22 document the new
   public key `scale_usd`; every other step traces to a criterion.
4. Criteria are falsifiable: `cap_for(4, {"plan_files": 4000}) == 8` goes red
   if the ceiling is dropped, where the unbounded value is 1004.
5. No research left. I verified every anchor: `BOUND_CEILING = 5`
   (`machine.py:25`), `bound_for()` ends at line 78, `transition` starts at
   line 81, `FENCED` spans lines 32-50. `symbol_lines()` spans against
   `--unified=0` hunks mean neither insertion trips the fence.
6. Riskiest step: 17, the `spawn()` ticket load. Python evaluates the right
   side of `counters, view = t.counters, stage_view(t, stage)` first, so a
   raising `stage_view` leaves `counters` at `{}`; `tests/test_pty.py:393`
   covers the no-ticket path. `## Rollback` adds `USD_SCALED = set()`.
7. Regression surface: every spawn's cap, covered by `tests/test_pty.py:391`
   (`--max-budget-usd 5` for `planning`) and `render()`'s callers in
   `tests/test_harness.py`. `cfg` gains a `counters` key; after `render()`,
   `spawn()` reads only `cfg.get("write")` (line 410) and `cfg.get('model')`
   (line 458), so the key is inert. `cap_for(0, c)` is 0, so `fake.toml` and
   `codex.toml` keep their 0.
8. Blast radius matches `class: feature`.

Two location errors, both corrected in `## Summary`: the ticket load is at
`supervisor.py:383-389`, not 385-390, and `README.md` has no standalone
`max_usd` bullet.

Note for `implementing`, not a finding: `cap_config()` calls
`project_stage_config()`, so every spawn runs one more
`git show HEAD:./.project/pipeline.toml`. `spawn()` already runs several.

### 2026-08-27 19:45:56Z · plan-validation · session · session=a84236a0-ff0d-4736-8660-0ba9f2b9b11e

`plan-validation` ran as session `a84236a0-ff0d-4736-8660-0ba9f2b9b11e`
- replay: `claude --resume a84236a0-ff0d-4736-8660-0ba9f2b9b11e`
- log: `.project/logs/TICKET-078-plan-validation-a84236a0.log`

### 2026-08-27 19:45:56Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items; corrected two line references (supervisor.py:383-389, README max_usd bullet)

### 2026-08-27 19:46:47Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread).

COLLISION NOTE for implementing: TICKET-077 is ahead of you at revalidating and rewrites the SAME line. render()'s cap is pipeline/core/config.py:388 (your plan says 305 -- the text is exact, the number drifted). 077 changes it to cap=stage_cap(cfg, hcfg), introducing stage_cap() as the single definition of a stage's dollar cap. Your step 6 changes the same line to cap=cap_for(cfg.get('max_usd', hcfg.get('max_usd', 5)), ...). If 077 has merged by the time you run, compose them -- cap=cap_for(stage_cap(cfg, hcfg), <counters>) -- rather than reverting stage_cap(). Re-read the line before editing it either way.

Verified: machine.py has no imports at all, so the new config -> machine import is not a cycle.

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread).

COLLISION NOTE for implementing: TICKET-077 is ahead of you at revalidating and rewrites the SAME line. render()'s cap is pipeline/core/config.py:388 (your plan says 305 -- the text is exact, the number drifted). 077 changes it to cap=stage_cap(cfg, hcfg), introducing stage_cap() as the single definition of a stage's dollar cap. Your step 6 changes the same line to cap=cap_for(cfg.get('max_usd', hcfg.get('max_usd', 5)), ...). If 077 has merged by the time you run, compose them -- cap=cap_for(stage_cap(cfg, hcfg), <counters>) -- rather than reverting stage_cap(). Re-read the line before editing it either way.

Verified: machine.py has no imports at all, so the new config -> machine import is not a cycle.**

### 2026-08-27 19:55:57Z · revalidating · transition · to=triage · result=conflict

**revalidating -> triage** (result: `conflict`)

rebase onto base conflicted; branch recut from base:
```
$ git rebase main || exit 3
/home/chezzijr/.local/share/uv/tools/pipeline/bin/python -P -m pipeline --project /home/chezzijr/proj/agent-pipeline gate TICKET-078 --findings /home/chezzijr/proj/agent-pipeline/.project/logs/TICKET-078-gate-53cb32a1.json

Rebasing (1/1)
Auto-merging tests/test_config.py
CONFLICT (content): Merge conflict in tests/test_config.py
error: could not apply af60a51... test(TICKET-078): review cap does not scale with diff size
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply af60a51... # test(TICKET-078): review cap does not scale with diff size

af60a51 test(TICKET-078): review cap does not scale with diff size
HEAD is now at 0471bd8 chore(TICKET-077): record the finished ticket

```

### 2026-08-28 · triage · result=ok

Reproduced on the recut branch and recommitted the test:
`tests/test_config.py::test_render_cap_does_not_scale_with_diff_size`
(`787680a`).

TICKET-077 merged after the earlier plan-validation pass and now defines
`stage_cap(cfg, hcfg)` at `pipeline/core/config.py:336`, called at line 403
as `cap=stage_cap(cfg, hcfg)`. This replaces the inline
`cfg.get("max_usd", hcfg.get("max_usd", 5))` the plan's step 6 and the
human's collision note both cite at line 305/388. The bug itself is
unchanged: neither `stage_cap()` nor `render()` reads `cfg["counters"]`.

The compose target the human's collision note asked for is now simple,
since `stage_cap()` already exists on `main`: step 6 should read
`cap=cap_for(stage_cap(cfg, hcfg), cfg.get("counters") or {})`, not the
`cap_for(cfg.get("max_usd", hcfg.get("max_usd", 5)), ...)` text currently in
the plan. `## Digest`'s line numbers for `render()` (305), `spawn()`'s
ticket load (385-390) and `render()`'s call site (395) are all stale by the
same merge and need re-verification, not just step 6.

`## Plan`, `## Digest`, `## Decisions checked` and `## Acceptance criteria`
are otherwise unchanged from the prior validated pass; I did not re-run
plan-validation, that is not this stage's job.

### 2026-08-27 19:57:16Z · triage · session · session=848fe917-8508-42e4-ac68-4de57dbef9a1

`triage` ran as session `848fe917-8508-42e4-ac68-4de57dbef9a1`
- replay: `claude --resume 848fe917-8508-42e4-ac68-4de57dbef9a1`
- log: `.project/logs/TICKET-078-triage-848fe917.log`

### 2026-08-27 19:57:16Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ recut branch after rebase conflict; reproduced and recommitted the failing test, corrected stale line refs from the TICKET-077 merge

### 2026-08-28 · planning · result=ok

Plan rewritten against the post-TICKET-077 code. One design change, forced by
that merge; everything else is the previously validated plan with re-verified
line numbers.

The change: `cap_for()` goes inside `stage_cap()`, not around its call site.
`stage_cap()` is called twice, not once -- `pipeline/core/config.py:403` for
the rendered `--max-budget-usd` flag, and `pipeline/daemon/supervisor.py:460`
for `rec["cap"]`. `_finish()` reads `rec["cap"]` at
`pipeline/daemon/supervisor.py:1085` and names it: "`review` was killed at its
$N budget cap". The compose target in the human approval note and in the
2026-08-28 triage entry, `cap=cap_for(stage_cap(cfg, hcfg), cfg.get("counters")
or {})`, wraps only line 403. It would render 8 and escalate naming 4. Scaling
inside `stage_cap()` keeps DEC-077's one definition and needs no edit at line
403 at all.

Consequence for the tests: step 15 asserts `rec["cap"] == 8` off the spawn
record instead of replacing `supervisor.render` with a recorder. That is a
stronger check and the `pipeline/harnesses/fake.toml` gotcha about a missing
cap placeholder no longer applies.

Verified anchors: `stage_cap()` at `pipeline/core/config.py:336`, `render()` at
344, `BOUND_CEILING = 5` at `pipeline/core/machine.py:25`, `bound_for()` 70-78,
`transition` at 81, `spawn()` at `pipeline/daemon/supervisor.py:345`, its
ticket load 397-402, `render()` call 409, README Settings bullet 495-500,
`pipeline/templates/pipeline.toml` stage block 30-35, `CLAUDE.md` invariant 3
line 29.

Not fixed, noted only: `pipeline/harnesses/codex.toml` has `max_usd = 0` and no
cap placeholder, so no cap reaches a codex spawn at all. Out of scope here.

### 2026-08-27 20:08:30Z · planning · session · session=688228cf-3f91-410f-a48c-c0347367ad3a

`planning` ran as session `688228cf-3f91-410f-a48c-c0347367ad3a`
- replay: `claude --resume 688228cf-3f91-410f-a48c-c0347367ad3a`
- log: `.project/logs/TICKET-078-planning-688228cf.log`

### 2026-08-27 20:08:30Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned on post-TICKET-077 code; cap_for() now goes inside stage_cap() so render() and rec[cap] scale as one number

### 2026-08-28 · plan-validation · result=ok

Tier B: PASS on all eight items. Written after the gate entry below, which
ran first; the ticket file has no unique anchor at its end, so this entry
sits above it.

long: eight items, each with the evidence its pass rests on.

1. Root cause: `stage_cap()` returns `cfg.get("max_usd", hcfg.get("max_usd",
   5))` (`pipeline/core/config.py:341`) and takes no plan size. The plan
   changes that expression, so it fixes the cause, not the symptom.
2. Decisions: DEC-047, DEC-065, DEC-058 and DEC-077 constrain and the plan
   complies. It supersedes the human collision note's
   `cap_for(stage_cap(cfg, hcfg), ...)` at the call site, with a reason I
   verified: `grep -rn stage_cap pipeline` returns two calls,
   `pipeline/core/config.py:403` and `pipeline/daemon/supervisor.py:460`.
   Wrapping 403 alone renders 8 and leaves `rec["cap"]` at 4.
3. Scope: every one of the 23 steps traces to an acceptance criterion.
4. Falsifiable: drop the ceiling and `cap_for(4, {"plan_files": 4000})`
   returns 1004, not 8, and step 1's assertion fails.
5. No research left: each step names a file, a symbol and a line.
6. Riskiest step is 6, the `stage_cap()` body, which every spawn's cap flows
   through. `## Rollback` states the fallback and the partial one,
   `USD_SCALED = set()`.
7. Regression surface: `tests/test_pty.py:391` asserts
   `--max-budget-usd 5` and `planning` is outside `USD_SCALED`;
   `tests/test_dispatch.py:1430` builds `"cap": 3` by hand and is untouched.
   No other test asserts a cap.
8. Blast radius: 3 source files, 3 test files, 3 docs, for a `bugfix` that
   rewrites one expression and adds two functions.

Claims of the plan I checked myself: `pipeline/core/machine.py` has no
import statement, so `config -> machine` is no cycle; `fenced_touches()`
diffs at `--unified=0`, so a hunk ending above `def transition` cannot
overlap its span; `advance()` writes `plan_steps` and `plan_files` at
`pipeline/daemon/supervisor.py:115` before every transition;
`Ticket.counters` exists at `pipeline/core/ticket.py:509`;
`tests/helpers.py:8` FIXTURE carries `stage: plan-validation` and
`counters: {}`, so step 15's two `.replace()` calls both hit. Arithmetic:
4 -> 6, 4 -> 8, 6 -> 11, 0 -> 0.

Anchor drift, neither changing an edit: the `spawn()` ticket load is lines
397-403, not 397-402; the README Settings bullet naming `max_usd` is line
497, inside the 495-500 block the plan cites.

Noted, not fixed: `pipeline/harnesses/codex.toml` has `max_usd = 0` and no
`{cap}` placeholder, so no cap reaches a codex spawn at all. Planning
flagged it as out of scope and I agree.

### 2026-08-27 20:08:51Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size` fails as required
```
nder() emitted the same --max-budget-usd 4 for a 15-file, 40-step plan as for one with no counters at all[0m
[1m[31mE       assert '--max-budget-usd 4' not in 'claude -p -...p/t.result" '[0m
[1m[31mE         [0m
[1m[31mE         '--max-budget-usd 4' is contained here:[0m
[1m[31mE         ?           ^^^^^^^^^^[0m
[1m[31mE           rmissions --max-budget-usd 4 --add-dir /tmp/.project -- "Work ticket TICKET-001. Your prompt carries a bounded view of /tmp/t.md; open that file only for what the view says it omitted, and read only the lines you need. When finished write /tmp/t.result" [0m
[1m[31mE         ?           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^[0m

[1m[31mtests/test_config.py[0m:30: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_config.py::[1mtest_render_cap_does_not_scale_with_diff_size[0m - AssertionError: expected the cap to grow with plan_files/plan_steps the way...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.04s[0m[31m ===============================[0m

```
- ok: `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size` fails on base `main` too -- the bug is not already fixed upstream
```
ests/test_config.py[0m:30: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_config.py::[1mtest_render_cap_does_not_scale_with_diff_size[0m - AssertionError: expected the cap to grow with plan_files/plan_steps the way...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-mkr2_ujl/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-mkr2_ujl/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 20:14:32Z · plan-validation · session · session=fd2aba71-ed91-4708-99c5-b46e52ca37d3

`plan-validation` ran as session `fd2aba71-ed91-4708-99c5-b46e52ca37d3`
- replay: `claude --resume fd2aba71-ed91-4708-99c5-b46e52ca37d3`
- log: `.project/logs/TICKET-078-plan-validation-fd2aba71.log`

### 2026-08-27 20:14:32Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B PASS on all eight items; verified stage_cap() has exactly two callers, so scaling inside it is the only edit that keeps rec[cap] and the rendered flag one number

### 2026-08-27 20:15:13Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). The rebase conflict with 077 produced a better design: scaling inside stage_cap() rather than at the render() call site, so rec['cap'] names the enforced number.

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). The rebase conflict with 077 produced a better design: scaling inside stage_cap() rather than at the render() call site, so rec['cap'] names the enforced number.**

### 2026-08-27 20:20:20Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-27 20:08:51Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_config.py::test_render_cap_does_not_scale_with_diff_size` fails on base `main` too -- the bug is not already fixed upstream
```
tests/test_config.py[0m:30: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_config.py::[1mtest_render_cap_does_not_scale_with_diff_size[0m - AssertionError: expected the cap to grow with plan_files/plan_steps the way...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-a8u4fc5l/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-a8u4fc5l/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 9ms[0m[0m

```

### 2026-08-27 20:20:21Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-28 · implementing · todo

Todo list, one entry per plan step:

1. [x] test_cap_for_scales_with_plan_size_and_stops_at_the_ceiling (RED)
2. [x] verify RED
3. [x] add USD_SCALED/USD_FILES_PER_DOLLAR/USD_STEPS_PER_DOLLAR/USD_CEILING_FACTOR to machine.py
4. [x] add cap_for() to machine.py
5. [x] verify GREEN, commit machine.py + test_machine.py
6. [x] stage_cap() scales via cap_for(), import in config.py
7. [x] verify test_config.py/test_pty.py/test_harness.py/test_dispatch.py pass
8. [x] add cap_config import + cmd() helper to test_config.py
9. [x] test_a_project_max_usd_override_is_not_scaled_past (RED)
10. [x] test_a_project_can_ask_for_scaling_on_top_of_its_own_cap (RED)
11. [x] test_the_project_decides_which_stages_scale_their_cap (RED)
12. [x] verify RED (ImportError cap_config)
13. [x] add cap_config() to config.py
14. [x] verify GREEN, commit config.py + test_config.py
15. [x] test_spawn_threads_the_tickets_counters_into_the_review_cap (RED)
16. [x] verify RED
17. [x] supervisor.py: import cap_config, thread counters through ticket load
18. [x] supervisor.py: cfg = cap_config(...) above render()
19. [x] verify test_dispatch/test_pty/test_harness/test_daemon pass, commit supervisor.py + test_dispatch.py
20. [x] document scale_usd in templates/pipeline.toml
21. [x] document in README.md
22. [x] document in CLAUDE.md invariant 3
23. [x] full suite + guard test, commit docs

### 2026-08-27 20:24:22Z · implementing · session · session=c846df19-671d-4a26-bd85-2b035558a667

`implementing` ran as session `c846df19-671d-4a26-bd85-2b035558a667`
- replay: `claude --resume c846df19-671d-4a26-bd85-2b035558a667`
- log: `.project/logs/TICKET-078-implementing-c846df19.log`

### 2026-08-27 20:24:22Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Implemented all 23 plan steps via TDD; cap_for()/cap_config() scale a review cap by plan size, capped at 2x, pinned by an operator's max_usd unless scale_usd=true; full suite (403) and guard pass.

### 2026-08-28 · review · findings · verdict=PASS

Reviewed the delta `main...HEAD`: five commits, 179 insertions across 9 files.
No blocking findings.

Verified against the acceptance criteria:
1. `uv run --group dev pytest -q` reports `403 passed in 19.30s`.
2. `./pipeline/hooks/test_dangerous_commands.py` reports `guard: all passed`.
3. `spawn()` is the only production caller of `render()`, and both
   `stage_cap(cfg, hcfg)` calls (`pipeline/core/config.py:421`,
   `pipeline/daemon/supervisor.py:468`) sit below the `cap_config()` rebind at
   `pipeline/daemon/supervisor.py:415`, so `rec["cap"]` and the rendered flag
   are one number (DEC-077).
4. `fenced_touches(Path('.'), 'main')` returns `[]`: the new constants and
   `cap_for()` miss every fenced symbol.

Findings I refuted before writing them down:
- A negative `plan_files` cannot produce a negative cap. `_size()`
  (`pipeline/core/machine.py:106`) returns 0 when `v > 0` is false.
- A `counters` key in `cfg` cannot leak into the spawned command. `render()`
  (`pipeline/core/config.py:362`) reads named keys only.

Non-blocking observations:
1. nit: `cap_config()` calls `project_stage_config()` a second time per spawn.
   `project_config()` (`pipeline/core/config.py:102`) is uncached, so each
   spawn runs one more `git show HEAD:./.project/pipeline.toml`.
2. nit: `test_render_cap_does_not_scale_with_diff_size` asserts only
   `"--max-budget-usd 4" not in scaled`. The criterion's `8` is asserted in
   `tests/test_machine.py` and `tests/test_dispatch.py` instead.
3. nit: a project writing a literal `counters` key into `[stages.<name>]`
   scales its own cap even with `max_usd` pinned, because `stage_cap()` scales
   on any `counters` in `cfg`. That value comes from HEAD (DEC-058), so it
   grants a ticket branch nothing.

### 2026-08-27 20:27:47Z · review · session · session=6d248d1c-5fee-4485-a6c6-686669417094

`review` ran as session `6d248d1c-5fee-4485-a6c6-686669417094`
- replay: `claude --resume 6d248d1c-5fee-4485-a6c6-686669417094`
- log: `.project/logs/TICKET-078-review-6d248d1c.log`

### 2026-08-27 20:27:47Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the 5-commit delta: no blocking findings; 403 passed, guard all passed, both stage_cap() calls below the cap_config() rebind, fence clean; 3 nits recorded

### 2026-08-27 20:28:08Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 20:28:09Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/078


Current branch ticket/078 is up to date.
Already up to date.
Updating 0471bd8..7617a65
Fast-forward
 CLAUDE.md                        |  4 +++
 README.md                        |  7 ++++
 pipeline/core/config.py          | 22 ++++++++++--
 pipeline/core/machine.py         | 24 +++++++++++++
 pipeline/daemon/supervisor.py    | 14 ++++++--
 pipeline/templates/pipeline.toml |  6 ++++
 tests/test_config.py             | 76 +++++++++++++++++++++++++++++++++++++++-
 tests/test_dispatch.py           | 19 ++++++++++
 tests/test_machine.py            | 13 +++++++
 9 files changed, 179 insertions(+), 6 deletions(-)

```

### 2026-08-27 20:28:09Z · merging · decision

decision recorded as `DEC-078`
