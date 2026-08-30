---
id: TICKET-103
stage: done
class: feature
branch: ticket/103
test_file: tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts
files_declared:
- pipeline/cli/metrics.py
- tests/test_metrics.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 13
  plan_files: 2
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 6bfdae07-a8b3-41d8-9bfe-9150862176a3
  log: .project/logs/TICKET-103-review-6bfdae07.log
  cost_usd: 1.6419375000000003
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified: no import cycle -- supervisor imports neither
  cli nor metrics, and metrics already imports daemon.store, so this is the same direction;
  pipeline metrics reaches supervisor through cli/main anyway, so pyte is already
  on that path. charged_round asks transition() rather than hardcoding which verdicts
  charge, so 087''s no-test-file and 089''s environment rows are counted for free
  and a future row needs no edit; verdict casing is handled with .upper(), the trap
  gate_failure_reasons already documents. Step 2 pins that view 1''s escalation denominator
  stays at 1 while gate_rounds reports 3, which is the phase design this ticket must
  not break. Noted, not re-planned: gate_result is a pure verdict function and core/gate.py
  is where it belongs, which would keep the reporting layer off the daemon -- churn
  on a function 087 and 089 just edited, so leave it.'
approved_at: '2026-08-30T10:35:12.235811+00:00'
---

## Summary

Fixed: view 7, `gate_rounds()`, added to `pipeline/cli/metrics.py`. It groups
`kind='gate'` events by `(project, ticket)` into `rounds` (every event) and
`charged` (routed through `gate_result()` then `transition(stage, result, {})`,
charged when the counters dict grew). Wired into `collect()`'s
`"gate_rounds"` key and a `render()` block between `gate failures:` and
`guard blocks:`.

All 13 plan steps done. Committed as `1dade0b`
("feat(TICKET-103): count gate rounds per ticket, charged and uncharged"),
`pipeline/cli/metrics.py` and `tests/test_metrics.py` only, matching
`files_declared`.

Review passed with no blocking findings. It re-ran the suite: `uv run --group
dev pytest -q` printed `496 passed in 35.23s`, and all seven acceptance
criteria hold. It also checked the four things the change could have got
wrong: no cli->daemon import cycle, `charged_round()` total for an unknown
`(stage, result)`, the event's `stage` column equal to the stage
`finish_gate()` judges with, and `data` never NULL.

Two non-blocking notes, in the review thread entry: `pipeline/cli/main.py:701`
still says `help="six views over the event log"` (outside `files_declared`),
and `render()`'s uncharged/total line sums every row while listing
`GATE_ROUNDS_TOP = 10`.

## Reproduction

Test: `tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts`
Command: `uv run --group dev pytest -q tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts`
Failure:
```
AttributeError: module 'pipeline.cli.metrics' has no attribute 'gate_rounds'
```
expect: AttributeError: module 'pipeline.cli.metrics' has no attribute 'gate_rounds'

No view over `gate` events exists yet. `pipeline/cli/metrics.py` has views 1-6
(`escalation_rates`, `review_loop_distribution`, `cost_per_merged`,
`cost_by_stage`, `gate_failure_reasons`, `guard_blocks`, `parked_spans`) and
`collect()`/`render()`, but nothing groups `kind='gate'` events by ticket to
report total rounds vs. charged rounds. The test builds a log with 3 `gate`
events for one ticket (2 PASS, 1 FAIL) and calls a not-yet-existing
`metrics.gate_rounds(conn)`.

## Digest

- Files touched: `pipeline/cli/metrics.py` (views 1-6, `collect()`, `render()`) and `tests/test_metrics.py` (a hand-written `Store` log, no daemon, no sleeps).
- Entry point: `cmd_metrics()` in `pipeline/cli/main.py` calls `metrics.collect(conn, since, project)` and prints `render(data)` or `json.dumps(data)`. A new `collect()` key reaches both, so `pipeline/cli/main.py` needs no change.
- Key functions: `_EV` (the `ts`/`project` CTE every view starts from), `_rows()` (binds `:since` and `:project`), `gate_failure_reasons()` (the only existing view over `kind='gate'`), `render()` (already binds `scope = data["scope"]`).
- `gate_result(ok, failures, stage)` is at `pipeline/daemon/supervisor.py:969`; `transition(stage, result, counters)` is at `pipeline/core/machine.py:111`. Both are pure. `pipeline/daemon/supervisor.py` imports nothing from `pipeline.cli`, so `pipeline/cli/metrics.py` can import `gate_result` with no cycle; `pipeline/cli/main.py` already imports the supervisor.
- Charged-ness is decidable from one `gate` event: route `verdict` and `findings` through `gate_result()`, then through `transition()` against an empty counters dict. A charged round grows that dict. Probe output, verbatim:
```
('plan-validation', 'pass', []) ('awaiting-approval', {})
('plan-validation', 'fail', ['files_declared is empty']) ('planning', {'plan_validation_attempts': 1})
('plan-validation', 'fail', ['section `## Rollback missing']) ('planning', {'structural_gate_failures': 1})
('plan-validation', 'fail', ['test file x does not exist']) ('escalated', {})
('plan-validation', 'fail', ['ENVIRONMENT: suite red on base']) ('escalated', {})
('revalidating', 'fail', ['whatever']) ('planning', {'stale_regate': 1})
('revalidating', 'pass', []) ('implementing', {})
('planning', 'fail', ['x']) ('escalated', {})
```
- Gotcha: `finish_gate()` emits `verdict="pass"`/`"fail"` in lowercase, while `gate.py`'s thread text writes PASS/FAIL. `gate_failure_reasons()` compares with SQL `UPPER()`; the new code uppercases in Python for the same reason.
- Gotcha: the identity is `(project, ticket)`, never a bare ticket id -- `TICKET-001` exists in every project.
- Gotcha: view 1 counts `kind='stage_end'`. Nothing in this change emits or counts `stage_end`, so its denominator cannot move; step 2's test pins that.
- Gotcha: `tests/test_metrics.py` inserts rows through its own `_at()` helper, not `Store.emit()`, so a test controls `ts`.
- Baseline measured 2026-08-30: `uv run --group dev pytest -q tests/test_metrics.py` printed `1 failed, 13 passed in 0.05s`, the one failure being this ticket's repro test.

## Decisions checked

Grep terms over `.project/decisions/`: `metrics`, `cli/metrics`, `view 1`, `escalation rate`, `gate_ok`, `plan_validation_attempts`, `event log`, `render()`.

- DEC-011 -- the schema and the event-kind vocabulary are frozen; adding a `kind` or a `data` field is additive. This plan adds neither: it queries `gate` events that already exist. Complies.
- DEC-061 -- a Tier A PASS at `plan-validation` is a phase and emits no `stage_end`, so one run cannot put two rows in view 1's denominator. That is the fact this view works around, and it stays true. Complies.
- DEC-093 -- `render()` learns its project scope through `data["scope"]`, never a second parameter, and `collect()` feeds both the text and `--json`. The new view is one more `collect()` key that `render(data)` reads. Complies.
- DEC-029 -- `revalidating` gets `fail` whatever the findings say; `no-test-file` and `environment` apply at `plan-validation` only. The plan calls `gate_result()` instead of restating that rule. Complies.
- DEC-022 -- history: it declined a marker-rate view and noted "six views to copy". Advisory, not a constraint; this plan adds the seventh.

## Plan

1. Run `timeout 300 uv run --group dev pytest -q tests/test_metrics.py` and confirm `tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts` fails with `AttributeError: module 'pipeline.cli.metrics' has no attribute 'gate_rounds'`.
2. Add `test_gate_rounds_leaves_view_1s_escalation_denominator_alone` to `tests/test_metrics.py`: build a log with one `stage_end` for `TICKET-501` at stage `plan-validation` (`result="ok"`, `next_stage="awaiting-approval"`, `exit_code=0`) plus three `gate` events for `TICKET-501` at `plan-validation` (two `verdict="pass"` with `findings=[]`, one `verdict="fail"` with `findings=["files_declared is empty"]`), then assert `next(r for r in metrics.escalation_rates(conn) if r["stage"] == "plan-validation")["runs"] == 1` and `next(r for r in metrics.gate_rounds(conn) if r["ticket"] == "TICKET-501")["rounds"] == 3`.
3. Run `timeout 300 uv run --group dev pytest -q tests/test_metrics.py` and watch step 2's test fail with the same `AttributeError: module 'pipeline.cli.metrics' has no attribute 'gate_rounds'`.
4. In `pipeline/cli/metrics.py`, change the import to `from pipeline.core.machine import HUMAN_GATES, TERMINAL, transition` and add `from pipeline.daemon.supervisor import gate_result` below it.
5. In `pipeline/cli/metrics.py`, under a new `# -- view 7: gate rounds per ticket` banner after `guard_blocks()`, add `def charged_round(stage: str, data: dict) -> bool:` that computes `ok = str(data.get("verdict") or "").upper() == "PASS"` and `findings = list(data.get("findings") or [])`, then `_next, counters = transition(stage or "", gate_result(ok, findings, stage or ""), {})`, and returns `bool(counters)`; its docstring states that charged-ness is asked of `transition()` so a new verdict row needs no list here, and cites DEC-061 for why a PASS at `plan-validation` charges nothing.
6. In `pipeline/cli/metrics.py`, add `def gate_rounds(conn, since: float = 0.0, project: str | None = None) -> list[dict]:` running `_EV + "SELECT project, ticket, stage, data FROM ev WHERE kind='gate' AND ticket IS NOT NULL"` through `_rows()`, decoding each row with `d = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]`, accumulating per `(project, ticket)` key into `{"project": ..., "ticket": ..., "rounds": 0, "charged": 0}` with `rounds += 1` and `charged += 1 if charged_round(r["stage"], d) else 0`, and returning `sorted(rows.values(), key=lambda a: (-a["rounds"], a["project"], a["ticket"]))`.
7. Run `timeout 300 uv run --group dev pytest -q tests/test_metrics.py` and expect the repro test and step 2's test to pass.
8. In `pipeline/cli/metrics.py`, add `"gate_rounds": gate_rounds(conn, since, project),` to `collect()` immediately after the `"gate_failures"` key.
9. In `pipeline/cli/metrics.py`, add `GATE_ROUNDS_TOP = 10` beside `DEFAULT_PRICE` and render view 7 in `render()` between the `gate failures:` block and the `guard blocks:` block: a header line `gate rounds (Tier A runs per ticket; a PASS at plan-validation charges no counter):`, then for the first `GATE_ROUNDS_TOP` rows of `data["gate_rounds"]` a line `f"  {label:<24} {r['rounds']:>3} rounds {r['charged']:>3} charged"` where `label` is `r["ticket"]` when `scope["project"]` is set and `f"{Path(r['project']).name}/{r['ticket']}"` otherwise, then `f"  {uncharged} of {total} rounds charged no counter -- churn no other view sees"` with `uncharged = sum(r["rounds"] - r["charged"] for r in gr)` and `total = sum(r["rounds"] for r in gr)`, and the single line `  no gate events in this window` when `data["gate_rounds"]` is empty.
10. Add `test_render_reports_gate_rounds_and_uncharged_churn` to `tests/test_metrics.py`: build a log with three `gate` events for `TICKET-502` at `plan-validation` (two `verdict="pass"` with `findings=[]`, one `verdict="fail"` with `findings=["files_declared is empty"]`), then assert both `"gate rounds"` and `"2 of 3 rounds charged no counter"` are in `metrics.render(metrics.collect(conn))`.
11. In `pipeline/cli/metrics.py`, change the module docstring's first line to `"""Seven views over the append-only event log DEC-011 froze.` and its next sentence to say seven SQL strings instead of six, then run `timeout 300 uv run --group dev pytest -q tests/test_metrics.py` and expect every test in the file to pass.
12. Run `timeout 600 uv run --group dev pytest -q tests/test_metrics.py tests/test_dispatch.py tests/test_cli.py` and expect no failures -- `tests/test_dispatch.py` calls `metrics.escalation_rates()` and `metrics.gate_failure_reasons()` and must stay green.
13. Commit with `git add pipeline/cli/metrics.py tests/test_metrics.py && git commit -m "feat(TICKET-103): count gate rounds per ticket, charged and uncharged"`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts` exits 0.
- `tests/test_metrics.py::test_gate_rounds_leaves_view_1s_escalation_denominator_alone` passes: view 1 reports 1 run at `plan-validation` while view 7 reports 3 rounds for the same ticket.
- `tests/test_metrics.py::test_render_reports_gate_rounds_and_uncharged_churn` passes, which also proves `collect()` carries the `gate_rounds` key, since `render()` reads it.
- `uv run --group dev pytest -q tests/test_metrics.py` reports no failures. At planning time its only failure was this ticket's repro test.
- `uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py` reports no failures; re-run any failure on the merge-base commit to confirm it predates this ticket.
- `grep -c "Seven views" pipeline/cli/metrics.py` prints `1`.
- `uv run --group dev pytest -q tests/test_metrics.py -k gate_rounds` reports no failures.

## Decisions

**Charged-ness is asked of `transition()`, never restated in the view.**
`charged_round()` in `pipeline/cli/metrics.py` routes a `gate` event's verdict
through `gate_result()` and then `transition(stage, result, {})`, and calls the
round charged when the counters dict grew. A verdict that escalates without
charging -- `no-test-file`, `environment` (DEC-029) -- is therefore reported as
uncharged automatically, and a new verdict row added to `transition()` needs no
edit here. A hard-coded list of charging verdicts reintroduces exactly the
drift `STRUCTURAL_MARKS` already costs.

**View 7 is a query, not instrumentation.** No new event kind, no new counter,
no `stage_end` for a gate PASS. DEC-061's phase design and DEC-011's frozen
vocabulary both stay intact, and view 1's escalation-rate denominator is
untouched by construction --
`tests/test_metrics.py::test_gate_rounds_leaves_view_1s_escalation_denominator_alone`
is what keeps it that way.

**`pipeline/cli/metrics.py` imports `gate_result` from
`pipeline/daemon/supervisor.py`.** The direction is cli -> daemon, which
`pipeline/cli/main.py` already takes. A future import of `pipeline.cli` from
the supervisor closes the cycle and breaks `pipeline metrics`.

**Rows are keyed by `(project, ticket)`.** Ticket ids are sequential per
project, so a bare id merges two projects' tickets whenever `--project` is
omitted.

## Rollback

Revert the single commit from step 13 (`git revert <sha>`): the change is
additive -- one import, `charged_round()`, `gate_rounds()`, one `collect()` key
and one `render()` block. No schema, no emitted event and no ticket field
changes, so nothing else depends on it; `pipeline metrics` returns to six
views. If only the rendered block is unwanted, delete the `render()` block from
`pipeline/cli/metrics.py` and keep `gate_rounds()` and the `collect()` key,
which `pipeline metrics --json` still reports.

## Thread

### 2026-08-30 01:49:14Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-30 · triage · result=ok

**triage** (result: `ok`)

Confirmed: `pipeline/cli/metrics.py` has no query grouping `kind='gate'`
events by ticket. Added
`tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts`,
which builds a log with 3 `gate` events for one ticket (2 PASS, 1 FAIL) and
calls `metrics.gate_rounds(conn)`.

Failure:
```
AttributeError: module 'pipeline.cli.metrics' has no attribute 'gate_rounds'
```

Committed on `ticket/103` at `396e547`.

Not a `chore`: adding the view touches `collect()` and `render()` too, and
the falsifiable criterion also requires proving view 1's escalation-rate
denominator is unaffected -- a design choice worth a plan, not a
few-line patch.

### 2026-08-30 02:01:33Z · triage · session · session=0b69f228-e4af-40c4-adca-db708d462347

`triage` ran as session `0b69f228-e4af-40c4-adca-db708d462347`
- replay: `claude --resume 0b69f228-e4af-40c4-adca-db708d462347`
- log: `.project/logs/TICKET-103-triage-0b69f228.log`
- cost: $0.42 of a $3 cap
- tokens: 5,163 out (749 thinking) · 44 in · 989,576 cache read · 43,146 cache write

### 2026-08-30 02:01:33Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced: metrics.gate_rounds does not exist, so charged counters (gate_ok/plan_validation_attempts) alone cannot recover gate-round churn

### 2026-08-30 · planning · result=ok

**planning** (result: `ok`)

Plan written: view 7 `gate_rounds()` in `pipeline/cli/metrics.py`, one row per
`(project, ticket)` with `rounds` and `charged`, plus a `collect()` key and a
`render()` block. 13 steps, 2 files.

The design question was how a query decides "charged" from a `gate` event. The
plan asks the state machine instead of restating its rules: route `verdict` and
`findings` through `gate_result()` (`pipeline/daemon/supervisor.py:969`) and
then `transition(stage, result, {})` (`pipeline/core/machine.py:111`), and call
the round charged when the counters dict grew. Probe output, verbatim:

```
('plan-validation', 'pass', []) ('awaiting-approval', {})
('plan-validation', 'fail', ['files_declared is empty']) ('planning', {'plan_validation_attempts': 1})
('plan-validation', 'fail', ['test file x does not exist']) ('escalated', {})
('plan-validation', 'fail', ['ENVIRONMENT: suite red on base']) ('escalated', {})
('revalidating', 'fail', ['whatever']) ('planning', {'stale_regate': 1})
```

So `no-test-file` and `environment` read as uncharged with no list to maintain.

Baseline: `uv run --group dev pytest -q tests/test_metrics.py` prints
`1 failed, 13 passed in 0.05s`, the failure being this ticket's repro test.

Out of scope, noted not fixed: `pipeline/cli/metrics.py` still says "Six
views" in two places; step 11 updates both.

### 2026-08-30 02:08:43Z · planning · session · session=e543428d-dd33-45d0-9ab9-fd77fdab21ef

`planning` ran as session `e543428d-dd33-45d0-9ab9-fd77fdab21ef`
- replay: `claude --resume e543428d-dd33-45d0-9ab9-fd77fdab21ef`
- log: `.project/logs/TICKET-103-planning-e543428d.log`
- cost: $2.89 of a $10 cap
- tokens: 35,984 out (16,791 thinking) · 58 in · 2,018,104 cache read · 97,879 cache write

### 2026-08-30 02:08:43Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned view 7 (gate_rounds) in metrics.py: rounds from `gate` events, charged decided by gate_result()+transition()

### 2026-08-30 02:09:25Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts` fails as required
```
vents -- 2 PASS, 1 FAIL -- must report 3 rounds and 1 charged
        # (only the FAIL charges a counter; a PASS at plan-validation never
        # does, per finish_gate()/GATE_PASS).
        s = _log()
        _at(s, BASE + 0, "gate", ticket="TICKET-500", stage="plan-validation",
           verdict="pass", findings=[])
        _at(s, BASE + 1, "gate", ticket="TICKET-500", stage="plan-validation",
           verdict="fail", findings=["files_declared is empty"])
        _at(s, BASE + 2, "gate", ticket="TICKET-500", stage="plan-validation",
           verdict="pass", findings=[])
    
        conn = metrics.connect(s.path)
        try:
>           rounds = metrics.gate_rounds(conn)
                     ^^^^^^^^^^^^^^^^^^^
E           AttributeError: module 'pipeline.cli.metrics' has no attribute 'gate_rounds'

tests/test_metrics.py:159: AttributeError
=========================== short test summary info ============================
FAILED tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts` fails on base `main` too -- the bug is not already fixed upstream
```
,
           verdict="pass", findings=[])
    
        conn = metrics.connect(s.path)
        try:
>           rounds = metrics.gate_rounds(conn)
                     ^^^^^^^^^^^^^^^^^^^
E           AttributeError: module 'pipeline.cli.metrics' has no attribute 'gate_rounds'

tests/test_metrics.py:159: AttributeError
=========================== short test summary info ============================
FAILED tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jyu1y2uo/base
      Built pipeline @ file:///tmp/pipeline-base-jyu1y2uo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 17ms

```

### 2026-08-30 · plan-validation · result=ok

**plan-validation** (result: `ok`)

Tier B: all 8 items pass.

1. Root cause: no view aggregates `kind='gate'` events per ticket, and the
   counters that exist grow only on charging verdicts. The plan adds the
   missing query, not a stub returning the test's numbers.
2. Decisions: I read DEC-061 and DEC-093; both say what the plan quotes.
   DEC-011 holds -- step 6 reads columns `project, ticket, stage, data`, all
   in `pipeline/daemon/store.py:16`. DEC-029 holds -- `gate_result()`
   (`pipeline/daemon/supervisor.py:983`) returns `fail` for every stage but
   `plan-validation`.
3. Scope: 13 steps, 2 files, class `feature`. Every step traces to a
   criterion; step 11 traces to `grep -c "Seven views"`.
4. Falsifiable: the repro test asserts `rounds == 3` AND `charged == 1`. A
   view counting only charged rounds gives 1; one charging every round gives
   3. Step 2's test fails if the change ever emits a `stage_end`.
5. No research left: `_EV` (line 102), `_rows()` (111), `DEFAULT_PRICE` (47),
   the `"gate_failures"` key in `collect()` (417) and `render()`'s two blocks
   (510, 519) all exist in `pipeline/cli/metrics.py` where the plan says.
6. Riskiest step: 4-5, `pipeline/cli/metrics.py` importing `gate_result`.
   `grep -rn 'from pipeline.cli' pipeline/daemon/ pipeline/core/` returns
   nothing, so no cycle today. `## Rollback` is its fallback.
7. Regressions: view 1's denominator (step 2's test plus
   `tests/test_dispatch.py:553`) and the rendered text
   (`tests/test_metrics.py:134, 305, 362, 378` -- all substring asserts, no
   exact-equality compare). Step 12 runs both files.
8. Blast radius: additive, one import and two functions. Matches `feature`.

unverified: I did not run pytest. `[readonly] allow` in
`.project/pipeline.toml` lists no test command, so
`uv run --group dev pytest -q tests/test_metrics.py` was blocked. The gate's
own run of the repro test is in the entry above.

Noted, not fixed (outside the declared files): `pipeline/cli/main.py:701`
reads `help="six views over the event log"`. Step 11 updates the two
occurrences in `pipeline/cli/metrics.py` only, which is what the criterion
checks.

Noted: `finish_gate()` sets `t.counters["gate_ok"] = 1` on a PASS
(`pipeline/daemon/supervisor.py:1010`), so step 9's header line "charges no
counter" is loose -- `gate_ok` is a latch `start()` pops (line 850), not a
bound. The metric is right; the wording is the review stage's call.

### 2026-08-30 02:13:11Z · plan-validation · session · session=ebaf2ab1-6536-4e5c-b827-6588e6f5db3d

`plan-validation` ran as session `ebaf2ab1-6536-4e5c-b827-6588e6f5db3d`
- replay: `claude --resume ebaf2ab1-6536-4e5c-b827-6588e6f5db3d`
- log: `.project/logs/TICKET-103-plan-validation-ebaf2ab1.log`
- cost: $1.50 of a $3 cap
- tokens: 16,243 out (7,473 thinking) · 40 in · 955,340 cache read · 61,449 cache write

### 2026-08-30 02:13:11Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all 8 items: root cause named, 5 decisions verified against their files, 13 steps trace to criteria, import cli->daemon has no cycle today

### 2026-08-30 10:35:12Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: no import cycle -- supervisor imports neither cli nor metrics, and metrics already imports daemon.store, so this is the same direction; pipeline metrics reaches supervisor through cli/main anyway, so pyte is already on that path. charged_round asks transition() rather than hardcoding which verdicts charge, so 087's no-test-file and 089's environment rows are counted for free and a future row needs no edit; verdict casing is handled with .upper(), the trap gate_failure_reasons already documents. Step 2 pins that view 1's escalation denominator stays at 1 while gate_rounds reports 3, which is the phase design this ticket must not break. Noted, not re-planned: gate_result is a pure verdict function and core/gate.py is where it belongs, which would keep the reporting layer off the daemon -- churn on a function 087 and 089 just edited, so leave it.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: no import cycle -- supervisor imports neither cli nor metrics, and metrics already imports daemon.store, so this is the same direction; pipeline metrics reaches supervisor through cli/main anyway, so pyte is already on that path. charged_round asks transition() rather than hardcoding which verdicts charge, so 087's no-test-file and 089's environment rows are counted for free and a future row needs no edit; verdict casing is handled with .upper(), the trap gate_failure_reasons already documents. Step 2 pins that view 1's escalation denominator stays at 1 while gate_rounds reports 3, which is the phase design this ticket must not break. Noted, not re-planned: gate_result is a pure verdict function and core/gate.py is where it belongs, which would keep the reporting layer off the daemon -- churn on a function 087 and 089 just edited, so leave it.**

### 2026-08-30 10:35:50Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-30 02:09:25Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts` fails on base `main` too -- the bug is not already fixed upstream
```
,
           verdict="pass", findings=[])
    
        conn = metrics.connect(s.path)
        try:
>           rounds = metrics.gate_rounds(conn)
                     ^^^^^^^^^^^^^^^^^^^
E           AttributeError: module 'pipeline.cli.metrics' has no attribute 'gate_rounds'

tests/test_metrics.py:159: AttributeError
=========================== short test summary info ============================
FAILED tests/test_metrics.py::test_gate_rounds_counts_every_gate_run_not_just_charged_attempts
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-7qq6l3tg/base
      Built pipeline @ file:///tmp/pipeline-base-7qq6l3tg/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```

### 2026-08-30 10:35:51Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-30 · implementing · todo

**implementing todo** (13 plan steps)

1. [x] confirm repro test fails as expected
2. [x] add test_gate_rounds_leaves_view_1s_escalation_denominator_alone
3. [x] confirm step-2 test fails (RED)
4. [x] add imports (transition, gate_result)
5. [x] add charged_round()
6. [x] add gate_rounds()
7. [x] confirm repro + step-2 tests pass (GREEN)
8. [x] add gate_rounds to collect()
9. [x] add GATE_ROUNDS_TOP + render() block
10. [x] add test_render_reports_gate_rounds_and_uncharged_churn
11. [x] docstring "Seven views"; full test_metrics.py green
12. [x] run test_metrics.py + test_dispatch.py + test_cli.py
13. [x] commit

### 2026-08-30 · implementing · result=ok

**implementing** (result: `ok`)

All 13 plan steps done, TDD throughout.

- Step 1: repro test failed with the expected `AttributeError` before any
  code change.
- Steps 2-3: added
  `test_gate_rounds_leaves_view_1s_escalation_denominator_alone` (1
  `stage_end` + 3 `gate` events for one ticket), confirmed it fails RED with
  the same `AttributeError`.
- Steps 4-6: added `from pipeline.core.machine import ... transition` and
  `from pipeline.daemon.supervisor import gate_result`; added
  `charged_round(stage, data)` and `gate_rounds(conn, since, project)` per
  plan.
- Step 7: repro test and step-2 test both pass; view 1's `runs` stayed 1
  while view 7 reported 3 rounds for the same ticket.
- Steps 8-9: added `"gate_rounds"` to `collect()` and the `render()` block
  with `GATE_ROUNDS_TOP = 10`.
- Step 10: added `test_render_reports_gate_rounds_and_uncharged_churn`;
  failed RED (missing "gate rounds" text) before the render block, passed
  after.
- Step 11: docstring now reads "Seven views" /
  "seven SQL strings"; `grep -c "Seven views" pipeline/cli/metrics.py` = 1.
  `uv run --group dev pytest -q tests/test_metrics.py`: `16 passed`.
- Step 12: `uv run --group dev pytest -q tests/test_metrics.py
  tests/test_dispatch.py tests/test_cli.py`: `137 passed in 19.44s`.
- Step 13: committed `1dade0b`, `pipeline/cli/metrics.py` and
  `tests/test_metrics.py` only.

No plan deviation. `pipeline/cli/main.py:701`'s stale "six views" help text
is outside `files_declared`; left untouched per `## Summary`'s note, not
this stage's job.

### 2026-08-30 10:37:59Z · implementing · session · session=edc410bf-bde0-412d-a4c6-6626d7f61bb6

`implementing` ran as session `edc410bf-bde0-412d-a4c6-6626d7f61bb6`
- replay: `claude --resume edc410bf-bde0-412d-a4c6-6626d7f61bb6`
- log: `.project/logs/TICKET-103-implementing-edc410bf.log`
- cost: $0.71 of a $8 cap
- tokens: 9,554 out (183 thinking) · 58 in · 1,792,121 cache read · 63,837 cache write

### 2026-08-30 10:37:59Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ added gate_rounds() view 7 to pipeline/cli/metrics.py, wired into collect()/render(); all 13 plan steps done, committed 1dade0b

### 2026-08-30 · review · result=ok

**review** (result: `ok`)

Reviewed the delta `main...HEAD` (`396e547`, `1dade0b`): `pipeline/cli/metrics.py`
+50/-3, `tests/test_metrics.py` +74. No blocking findings.

Verified:
1. `uv run --group dev pytest -q`: `496 passed in 35.23s`. The three suites the
   plan names: `137 passed in 19.60s`. `-k gate_rounds`: `3 passed, 13 deselected`.
   `grep -c "Seven views" pipeline/cli/metrics.py`: `1`.
2. No import cycle: `pipeline/daemon/supervisor.py:3-42` imports no
   `pipeline.cli` module.
3. `charged_round()` is total. `transition()` returns `("escalated", c)` for an
   unknown pair (`pipeline/core/machine.py:280`) with `c` unchanged, so a gate
   row whose `stage` is NULL reports uncharged instead of raising.
4. The view's stage matches the dispatcher's. `emit("gate", ...)` uses
   `rec["stage"]` (`supervisor.py:1003`) and `finish_gate()` judges with
   `t.stage` (`supervisor.py:1014`); both are the stage `start()` spawned the
   gate child at (`supervisor.py:825,844`).
5. `data` is `TEXT NOT NULL DEFAULT '{}'` (`pipeline/daemon/store.py:24`), so
   `json.loads(r["data"])` never sees NULL.
6. Every `render()` caller passes `collect()` output, so the new
   `data["gate_rounds"]` read raises no KeyError.

Non-blocking:
1. minor -- `pipeline/cli/main.py:701` still says `six views over the event log`.
   Outside `files_declared`, already noted by triage and `## Summary`.
2. minor -- `render()` lists `GATE_ROUNDS_TOP = 10` rows but sums `uncharged`
   and `total` over every row, so the totals can exceed the rows shown.

### 2026-08-30 10:42:10Z · review · session · session=6bfdae07-a8b3-41d8-9bfe-9150862176a3

`review` ran as session `6bfdae07-a8b3-41d8-9bfe-9150862176a3`
- replay: `claude --resume 6bfdae07-a8b3-41d8-9bfe-9150862176a3`
- log: `.project/logs/TICKET-103-review-6bfdae07.log`
- cost: $1.64 of a $5 cap
- tokens: 13,736 out (6,490 thinking) · 60 in · 1,415,317 cache read · 58,954 cache write

### 2026-08-30 10:42:10Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review of 1dade0b + 396e547: no blocking findings; 496 passed, all 7 acceptance criteria hold

### 2026-08-30 10:42:47Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-30 10:42:48Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/103


Current branch ticket/103 is up to date.
Already up to date.
Updating 38750fe..1dade0b
Fast-forward
 pipeline/cli/metrics.py | 53 +++++++++++++++++++++++++++++++++--
 tests/test_metrics.py   | 74 +++++++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 124 insertions(+), 3 deletions(-)

```

### 2026-08-30 10:42:48Z · merging · decision

decision recorded as `DEC-103`
