---
id: TICKET-116
stage: done
class: feature
branch: ticket/116
test_file:
- tests/test_cli.py::test_ls_hides_finished_tickets_by_default
- tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones
files_declared:
- README.md
- pipeline/cli/main.py
- pipeline/templates/skills/file-ticket/SKILL.md
- pipeline/tui/app.py
- tests/test_cli.py
- tests/test_tui.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 6
  plan_files: 6
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: e4efa53b-6fe6-41ca-b51c-56c4a0bad477
  replay: claude --resume e4efa53b-6fe6-41ca-b51c-56c4a0bad477
  log: .project/logs/TICKET-116-review-e4efa53b.log
  cost_usd: 1.5247134999999998
approved_by: chezzijr
approved_at: '2026-09-05T17:41:43.985046+00:00'
---

## Summary

Reviewed and passed. `filter_ls_rows()` in `pipeline/cli/main.py` applies after
shared daemon/file retrieval: bare `pipeline ls` hides `done`/`rejected`;
`--all`, `--stage`, and a positional ticket ID expose history and intersect, in
source order. `_paint()` in `pipeline/tui/app.py` sorts restored rows
active-first (`FINISHED`), then by ticket ID within each bucket.

The review found no blocking issue in the four-commit delta and filed three
non-blocking nits in `## Thread`. Verified: `uv run --group dev pytest -q` --
`571 passed`; the three acceptance modules -- `140 passed`; the docs `rg` check
-- exit 0. `test_the_f_key_toggles_finished_tickets_back_into_the_tree` was the
only existing test changed, to the new active-first bucket order.

## Reproduction

tests: `tests/test_cli.py::test_ls_hides_finished_tickets_by_default`, `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones`
command: `uv run --group dev pytest -q tests/test_cli.py::test_ls_hides_finished_tickets_by_default tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones`
expect: TICKET-001

```text
E       AssertionError: -- no daemon: running/mode unknown for these rows
E         TICKET-001   done              bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0}
E         TICKET-002   new               bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0}
E           AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7f01aadf4930>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7f01aadf4930> = 'TICKET-001 done'.startswith
```

## Digest

Files: `pipeline/cli/main.py` owns argument parsing, row filtering, the no-daemon banner, and `-v` rendering.
Files: `pipeline/tui/app.py` owns `FINISHED`, `_visible()`, `_paint()`, `f`, cursor restoration, and project grouping.
Tests: `tests/test_cli.py` runs real CLI processes; `tests/test_tui.py` drives `PipelineApp` with `FakeClient` rows.
Docs: `README.md` and `pipeline/templates/skills/file-ticket/SKILL.md` must describe CLI behavior because this changes the operator interface.
Entry points: `cmd_ls()` retrieves identical daemon/file rows before presentation; `PipelineApp._paint()` builds each project's ordered labels.
Gotcha: keep `ticket_rows()` and server `ls` untouched; `tests/test_daemon.py::test_ls_answers_the_same_with_and_without_a_daemon` protects equivalence.
Gotcha: `escalated` is terminal but actionable; `FINISHED = TERMINAL - {"escalated"}` hides only `done` and `rejected`.
Gotcha: `_paint()` must retain project ordering, cursor restoration, selected finished rows, and ticket-ID order inside each activity bucket.
Baseline: the two reproduction tests fail on commit `9a14dcd`; default CLI output includes `TICKET-001`, and restored TUI history starts there.

## Decisions checked

DEC-011 requires one `ticket_rows()` implementation for daemon and file paths, unchanged socket row shapes, and `--project` as a filter.
DEC-048 keeps wait data in shared `ticket_rows()` output and treats it as display-only; filtering must occur after row retrieval.
DEC-060 hides only `done` and `rejected`, keeps `escalated` visible, preserves selected finished rows, and constrains cursor restoration.
Search terms: `ls`, `tui`, `filter`, `finished`, `terminal`, `history`, `ordering`, `presentation`, `fallback`, `response shape`.

## Plan

1. Extend `tests/test_cli.py` with a filter matrix covering defaults, explicit history, selector intersection, stable order, invalid stages, and `-v`; run it failing.
2. Add positional ticket, `--all`, and validated `--stage` arguments in `pipeline/cli/main.py`; keep the existing `-v` contract.
3. Add `filter_ls_rows()` in `pipeline/cli/main.py` after row retrieval; selectors expose matching history, combine by intersection, and preserve input order.
4. Extend `tests/test_tui.py` to require active-first restored history and ticket-ID order within active and finished buckets; run it failing.
5. Change `pipeline/tui/app.py` `_paint()` sorting to an active-first key using `FINISHED`; preserve project grouping, `_visible()`, selection, and cursor behavior.
6. Update `README.md` and `pipeline/templates/skills/file-ticket/SKILL.md` with default, `--all`, `--stage`, positional-ticket, and active-first TUI examples.

## Acceptance criteria

- `tests/test_cli.py::test_ls_filters_all_stage_and_ticket_views` proves default, `--all`, `--stage`, positional-ID, intersection, and ordering behavior.
- `tests/test_cli.py::test_ls_v_prints_the_last_session_cost` and `tests/test_cli.py::test_ls_v_uses_a_harness_specific_replay_command` pass unchanged.
- `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` keeps the live row first before and after pressing `f`.
- `tests/test_tui.py::test_the_f_key_toggles_finished_tickets_back_into_the_tree` proves actionable and finished bucket ordering.
- `tests/test_daemon.py::test_ls_answers_the_same_with_and_without_a_daemon` passes with unchanged row keys and socket response shape.
- `uv run --group dev pytest -q tests/test_cli.py tests/test_tui.py tests/test_daemon.py` exits `0`.
- `rg -n -- '--all|--stage|pipeline ls TICKET' README.md pipeline/templates/skills/file-ticket/SKILL.md` exits `0` and reports both files.

## Decisions

CLI selectors operate only after daemon or file retrieval; dispatcher state, storage, `ticket_rows()`, and socket responses remain unchanged.

Bare `pipeline ls` hides `done` and `rejected` but keeps `escalated`, matching the TUI's actionable-queue boundary.

An explicit `--stage` or ticket ID can select finished history without `--all`. When both exist, their filters intersect.

The TUI's all-history view stable-partitions rows by `FINISHED`, then orders each partition by ticket ID.

## Rollback

Revert the CLI parser/filter helper, TUI sort key, regression tests, and documentation together; this restores unfiltered CLI and ID-only TUI ordering.
## Thread

### 2026-09-05 16:20:32Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-05 16:29:00Z · triage · investigation

Reproduced the queue-ordering failure after pressing `f`.

`PipelineApp._paint()` sorts restored rows only by ticket ID.
Completed `TICKET-001` through `TICKET-050` precede active `TICKET-060`.

The default view hides completed rows, so its initial active ordering passes.
The failure occurs only after history returns to the tree.

Commit `9a14dcd` adds failing CLI and TUI regression assertions.
Expected fix files: `pipeline/tui/app.py` and `tests/test_tui.py`.

### 2026-09-05 16:34:00Z · triage · scope-update

The CLI also exposes completed tickets by default.

`cmd_ls()` prints every `ticket_rows()` result without filtering terminal stages.
`PipelineApp._paint()` orders restored history only by ticket ID.

Both causes bury active tickets after historical entries.
Commit `9a14dcd` reproduces both failures.

Expected fix files: `pipeline/cli/main.py`, `pipeline/tui/app.py`, `tests/test_cli.py`, and `tests/test_tui.py`.

### 2026-09-05 16:23:40Z · triage · session · session=01a0725f-515f-7000-9ca4-28e533d0d4bb

`triage` ran as session `01a0725f-515f-7000-9ca4-28e533d0d4bb`
- replay: `codex exec resume 01a0725f-515f-7000-9ca4-28e533d0d4bb`
- log: `.project/logs/TICKET-116-triage-c7f04d0f.log`

### 2026-09-05 16:23:40Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced the active queue ordering failure after history is restored.

### 2026-09-05 16:26:18Z · planning · plan

Plan filtering at presentation boundaries only.

The CLI keeps shared daemon/file rows intact, then applies default or explicit selectors. The TUI stable-partitions restored history behind actionable rows.

The plan preserves `escalated`, `-v`, project grouping, cursor restoration, row shapes, and ordering within activity buckets.

Declared six files, including README and the installed `file-ticket` skill required for an operator-facing CLI change.

### 2026-09-05 16:27:34Z · planning · session · session=01a07262-0557-7af1-960b-be659002f662

`planning` ran as session `01a07262-0557-7af1-960b-be659002f662`
- replay: `codex exec resume 01a07262-0557-7af1-960b-be659002f662`
- log: `.project/logs/TICKET-116-planning-745b00a1.log`

### 2026-09-05 16:27:34Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned presentation-only CLI filters and stable active-first TUI history ordering.

### 2026-09-05 16:28:31Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_ls_hides_finished_tickets_by_default` fails as required
```
, r.stdout
E       AssertionError: -- no daemon: running/mode unknown for these rows
E         TICKET-001   done              bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0} 
E         TICKET-002   new               bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0} 
E         
E       assert 'TICKET-001' not in "-- no daemo...ries': 0} \n"
E         
E         'TICKET-001' is contained here:
E           hese rows
E           TICKET-001   done              bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0} 
E         ? ++++++++++
E           TICKET-002   new               bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0}

tests/test_cli.py:432: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_hides_finished_tickets_by_default - Asserti...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.56s ===============================

```
- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails as required
```
ICKET-060", "implementing",
                        running=True))
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            got = labels(app)["alpha"]
            assert got[0].startswith("TICKET-060"), got[:3]
    
            # Restoring history must not undo the active-queue ordering.
            await pilot.press("f")
            await pilot.pause()
            got = labels(app)["alpha"]
>           assert got[0].startswith("TICKET-060"), got[:3]
E           AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7f014ffde8f0>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7f014ffde8f0> = 'TICKET-001 done'.startswith

tests/test_tui.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.66s ===============================

```
- ok: `tests/test_cli.py::test_ls_hides_finished_tickets_by_default` fails on base `main` too -- the bug is not already fixed upstream
```
01   done              bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0} 
E         ? ++++++++++
E           TICKET-002   new               bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0}

tests/test_cli.py:432: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_hides_finished_tickets_by_default - Asserti...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.91s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-uq1yrhix/base
      Built pipeline @ file:///tmp/pipeline-base-uq1yrhix/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 36ms

```
- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-060", "implementing",
                        running=True))
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            got = labels(app)["alpha"]
            assert got[0].startswith("TICKET-060"), got[:3]
    
            # Restoring history must not undo the active-queue ordering.
            await pilot.press("f")
            await pilot.pause()
            got = labels(app)["alpha"]
>           assert got[0].startswith("TICKET-060"), got[:3]
E           AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7f7689084cb0>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7f7689084cb0> = 'TICKET-001 done'.startswith

tests/test_tui.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.16s ===============================

```

### 2026-09-05 16:33:33Z · plan-validation · finding

Plan validation passed all scored items.

1. **Root cause: pass.** `cmd_ls()` renders every retrieved row. `_paint()` sorts restored rows only by ticket ID. The plan fixes both presentation causes.
2. **Decision conflict: pass.** Post-retrieval filtering preserves DEC-011 and DEC-048. `FINISHED` and selected-row behavior preserve DEC-060.
3. **Scope discipline: pass.** All six files implement, test, or document an acceptance criterion. The skill update is required for operator-facing changes.
4. **Falsifiable criteria: pass.** The matrix distinguishes default, explicit, intersected, invalid, ordered, and verbose views. TUI tests distinguish active-first from ID-only sorting.
5. **No research left: pass.** Steps identify `cmd_ls()`, `filter_ls_rows()`, `_paint()`, both test files, and both documentation targets.
6. **Riskiest step: pass.** `_paint()` ordering shares selection and cursor logic. Focused assertions guard it; joint rollback restores prior ordering.
7. **Regression surface: pass.** `-v`, row shapes, project grouping, `f`, selection, and cursor restoration could regress. Named tests and full module suites cover them.
8. **Blast radius: pass.** Six presentation, test, and documentation files fit this interface bugfix.

Unverified: none.

### 2026-09-05 16:35:02Z · plan-validation · session · session=01a07269-c4b5-7e81-b443-7a194e8051fb

`plan-validation` ran as session `01a07269-c4b5-7e81-b443-7a194e8051fb`
- replay: `codex exec resume 01a07269-c4b5-7e81-b443-7a194e8051fb`
- log: `.project/logs/TICKET-116-plan-validation-eb948cdc.log`

### 2026-09-05 16:35:02Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan fixes both presentation defects while preserving shared rows, actionable terminals, selection, and ordering contracts.

### 2026-09-05 17:41:43Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-06 02:11:28Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_ls_hides_finished_tickets_by_default` fails as required
```
, r.stdout
E       AssertionError: -- no daemon: running/mode unknown for these rows
E         TICKET-001   done              bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0} 
E         TICKET-002   new               bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0} 
E         
E       assert 'TICKET-001' not in "-- no daemo...ries': 0} \n"
E         
E         'TICKET-001' is contained here:
E           hese rows
E           TICKET-001   done              bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0} 
E         ? ++++++++++
E           TICKET-002   new               bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0}

tests/test_cli.py:432: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_hides_finished_tickets_by_default - Asserti...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.15s ===============================

```
- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails as required
```
ICKET-060", "implementing",
                        running=True))
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            got = labels(app)["alpha"]
            assert got[0].startswith("TICKET-060"), got[:3]
    
            # Restoring history must not undo the active-queue ordering.
            await pilot.press("f")
            await pilot.pause()
            got = labels(app)["alpha"]
>           assert got[0].startswith("TICKET-060"), got[:3]
E           AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7fdc34cf0b70>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7fdc34cf0b70> = 'TICKET-001 done'.startswith

tests/test_tui.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.77s ===============================

```
- ok: `tests/test_cli.py::test_ls_hides_finished_tickets_by_default` fails on base `main` too -- the bug is not already fixed upstream
```
01   done              bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0} 
E         ? ++++++++++
E           TICKET-002   new               bugfix    {'plan_validation_attempts': 0, 'review_loops': 0, 'blocked_count': 0, 'lease_expiries': 0}

tests/test_cli.py:432: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_hides_finished_tickets_by_default - Asserti...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.26s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-z5xve8hx/base
      Built pipeline @ file:///tmp/pipeline-base-z5xve8hx/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 24ms

```
- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-060", "implementing",
                        running=True))
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            got = labels(app)["alpha"]
            assert got[0].startswith("TICKET-060"), got[:3]
    
            # Restoring history must not undo the active-queue ordering.
            await pilot.press("f")
            await pilot.pause()
            got = labels(app)["alpha"]
>           assert got[0].startswith("TICKET-060"), got[:3]
E           AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7f45d337fa70>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7f45d337fa70> = 'TICKET-001 done'.startswith

tests/test_tui.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.16s ===============================

```

### 2026-09-06 02:11:29Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-06 · implementing · todo

Working the plan in order:

1. [x] Extend `tests/test_cli.py` with the ls filter matrix; run failing.
2. [x] Add `--all`, `--stage`, positional ticket args to `cmd_ls` in `pipeline/cli/main.py`.
3. [x] Add `filter_ls_rows()` after row retrieval in `pipeline/cli/main.py`.
4. [x] Extend `tests/test_tui.py` for active-first restored history; run failing.
5. [x] Change `_paint()` sort key in `pipeline/tui/app.py` to active-first, then ID.
6. [x] Update `README.md` and the `file-ticket` `SKILL.md`.

### 2026-09-06 · implementing · report

Plan executed. Commits: `fc175a6` (CLI filters + `test_ls_filters_all_stage_and_ticket_views`,
TDD-verified RED then GREEN), `b13dc0a` (TUI active-first sort key), `cc20ef3` (docs).

`filter_ls_rows()` hides `FINISHED = TERMINAL - {"escalated"}` on a bare `ls`;
`--all`, `--stage`, and a positional ticket ID expose history and intersect,
in source order. `_paint()`'s sort key became
`(stage in FINISHED, id)`.

Step 4 required editing `test_the_f_key_toggles_finished_tickets_back_into_the_tree`:
its post-`f` assertion moved from ID-only order (`001,002,003,004`) to
active-first order (`003,004,001,002`), matching the new bucket rule. No
other existing test changed.

`uv run --group dev pytest -q` -- 571 passed, including both reproduction
tests, `test_ls_answers_the_same_with_and_without_a_daemon`, and the full
`test_cli.py`/`test_tui.py` modules. `rg -n -- '--all|--stage|pipeline ls
TICKET' README.md pipeline/templates/skills/file-ticket/SKILL.md` exits 0
and reports both files.

### 2026-09-06 02:18:05Z · implementing · session · session=a6139c19-2f2a-4680-9225-2181dac18f03

`implementing` ran as session `a6139c19-2f2a-4680-9225-2181dac18f03`
- replay: `claude --resume a6139c19-2f2a-4680-9225-2181dac18f03`
- log: `.project/logs/TICKET-116-implementing-a6139c19.log`
- cost: $1.26 of a $8 cap
- tokens: 18,718 out (5,208 thinking) · 108 in · 3,610,684 cache read · 86,942 cache write

### 2026-09-06 02:18:05Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added ls filters (--all, --stage, ticket ID) and TUI active-first history ordering; full suite passes.

### 2026-09-06 · review · report

**PASS -- no blocking findings.** I reviewed the four commits since the branch
point (`e5c9ace`, `fc175a6`, `b13dc0a`, `cc20ef3`): 120 added lines across the
six files the plan names. Every acceptance criterion holds.

Evidence:
1. `uv run --group dev pytest -q tests/test_cli.py tests/test_tui.py tests/test_daemon.py` -- `140 passed in 37.28s`.
2. `uv run --group dev pytest -q` -- `571 passed in 55.12s`.
3. `rg -n -- '--all|--stage|pipeline ls TICKET' README.md pipeline/templates/skills/file-ticket/SKILL.md` -- `exit=0`, both files reported.
4. `git status --porcelain` -- empty. I changed nothing but this ticket.

Findings I refuted rather than filed:
- `--stage done` dies as an unknown stage: refuted, `TERMINAL` is a member of `KNOWN_STAGES` at `pipeline/core/machine.py:63`.
- A selected finished row loses the cursor under the new sort: refuted, `_paint()` restores by `leaf.data == keep`, not by position, at `pipeline/tui/app.py:369`; `test_a_selected_ticket_stays_in_the_tree_when_it_finishes` passes.
- The guard blocks `pipeline ls --all` in a read-only stage: refuted, `readonly_rules()` matches `GUARDED` on `args[0]` only, at `pipeline/hooks/dangerous-commands.py:345`.

Non-blocking nits, for whoever touches this next:
1. minor: `cmd_ls` validates `--stage` after the daemon round-trip, so `pipeline ls --stage bogus` opens and queries the socket before `die()`.
2. minor: a positional ticket ID that matches no row prints nothing and exits 0. There is no "no such ticket" line.
3. nit: `README.md:174` pads the `pipeline ls TICKET-001` comment to a different column than the two lines above it.

### 2026-09-06 02:23:02Z · review · session · session=e4efa53b-6fe6-41ca-b51c-56c4a0bad477

`review` ran as session `e4efa53b-6fe6-41ca-b51c-56c4a0bad477`
- replay: `claude --resume e4efa53b-6fe6-41ca-b51c-56c4a0bad477`
- log: `.project/logs/TICKET-116-review-e4efa53b.log`
- cost: $1.52 of a $5 cap
- tokens: 14,585 out (7,123 thinking) · 58 in · 1,225,799 cache read · 54,586 cache write

### 2026-09-06 02:23:02Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the 4-commit delta: no blocking findings; 571 tests pass and all 7 acceptance criteria hold.

### 2026-09-06 02:23:58Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-06 07:07:18Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/116


Rebasing (1/4)Rebasing (2/4)Rebasing (3/4)Rebasing (4/4)Successfully rebased and updated refs/heads/ticket/116.
Already up to date.
Updating 2d540dd..9f95684
Fast-forward
 README.md                                      |  9 +++-
 pipeline/cli/main.py                           | 28 ++++++++++-
 pipeline/templates/skills/file-ticket/SKILL.md |  4 +-
 pipeline/tui/app.py                            |  5 +-
 tests/test_cli.py                              | 68 ++++++++++++++++++++++++++
 tests/test_tui.py                              | 16 ++++--
 6 files changed, 120 insertions(+), 10 deletions(-)

```

### 2026-09-06 07:07:18Z · merging · decision

decision recorded as `DEC-116`
