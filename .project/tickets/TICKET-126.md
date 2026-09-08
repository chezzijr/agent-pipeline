---
id: TICKET-126
stage: done
class: bugfix
branch: ticket/126
test_file: tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others
files_declared:
- pipeline/cli/main.py
- tests/test_cli.py
counters:
  plan_validation_attempts: 1
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 6
  plan_files: 2
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 01a0812c-201a-7fb0-b235-411ca095754a
  replay: codex exec resume 01a0812c-201a-7fb0-b235-411ca095754a
  log: .project/logs/TICKET-126-review-9def6fe3.log
  cost_usd: null
approved_by: chezzijr
approved_at: '2026-09-08T12:41:10.791730+00:00'
---

## Summary

Review passed commit `74193e5` with no blocking findings. `cmd_ls()` now checks `registry.is_worktree()` before constructing the registration notice.

The regression creates a real linked worktree and returns a successful global daemon reply. It confirms the daemon row remains and the impossible command stays absent.

Implementing evidence reports 8 focused tests, 65 CLI tests, and 608 total tests passed. Review confirmed `git diff --check` exits 0.

## Reproduction

Test: `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others`

Command:

    uv run --group dev pytest -q tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others

Observed output:

    E AssertionError: TICKET-999   escalated         bugfix    {}
    E
    E assert '1 tickets in /tmp/tmp3e9d_4ru, which is not registered -- run `pipeline register .`' in 'TICKET-999   escalated         bugfix    {}\n'

The output has no local-project notice.

expect: which is not registered -- run `pipeline register .`

## Digest

- `pipeline/cli/main.py` owns `cmd_ls()`, `proj()`, daemon retrieval, file fallback, filtering, and row rendering.
- `tests/test_cli.py` contains the committed reproduction `test_ls_names_an_unregistered_project_when_the_daemon_lists_others` and its fake daemon client.
- The CLI entry point passes `project=None` for bare `pipeline ls`; `cmd_ls()` then requests every registered project from the daemon.
- `registry.projects()` is the read-only membership source. `ticket_rows(proj(args))` can count local tickets without changing daemon rows.
- Gotcha: `rows is None` means the daemon failed. Successful global rows do not prove that the current project is registered.
- Gotcha: bare `ls` remains a registered-project view. The fix reports unregistered local rows but does not append them.
- Riskiest step: capture successful-global-response state before fallback, then print the notice after selector validation and before row rendering.
- Fallback: if inline placement couples retrieval and presentation, extract a notice helper while leaving fallback, filtering, and rendering unchanged.
- Named-project coverage: `test_cli_new_then_ls`; daemon-failure coverage: `test_ls_says_running_is_unknown_when_no_daemon_answers`.
- Selector coverage: `test_ls_filters_all_stage_and_ticket_views`; default-filter coverage: `test_ls_hides_finished_tickets_by_default`.
- Row-rendering coverage: `test_ls_v_prints_the_last_session_cost` and `test_ls_v_uses_a_harness_specific_replay_command`.

## Decisions checked

- DEC-011 requires global daemon `ls` to list registered projects and keeps `ticket_rows()` as the shared row builder.
- DEC-114 requires read-only CLI commands to report missing registration without enlisting the project.
- DEC-116 requires CLI selectors to run after daemon or file retrieval without changing dispatcher or socket behavior.
- DEC-072 keeps registration as operator state and filters linked worktrees from `registry.projects()`; this fix only reads membership.
- DEC-062 requires file-fallback rows to retain unknown `running` and `mode` values when no daemon answers.

## Plan

1. Strengthen `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` in `tests/test_cli.py`. Assert the local row stays absent, the daemon row renders, the client closes, and `registry.projects()` stays unchanged.
2. Extend `tests/test_cli.py::test_ls_says_running_is_unknown_when_no_daemon_answers` in `tests/test_cli.py`. Assert daemon failure keeps file-fallback output and emits no registration remediation.
3. Run `uv run --group dev pytest -q tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` against `tests/test_cli.py`. Expect the missing-notice assertion alone to fail.
4. Treat conditional placement as the riskiest change in `pipeline/cli/main.py`. In `cmd_ls()`, capture a successful bare global response before fallback. Build the notice only when `proj(args)` is absent from `registry.projects()` and `ticket_rows()` is non-empty. Preserve daemon rows. Print after selector validation and before row rendering. If regression tests expose coupling, extract this decision into a notice helper without moving fallback, filtering, or rendering.
5. Run the named regression matrix in `tests/test_cli.py`: `test_cli_new_then_ls`, `test_ls_says_running_is_unknown_when_no_daemon_answers`, `test_ls_filters_all_stage_and_ticket_views`, `test_ls_hides_finished_tickets_by_default`, `test_ls_v_prints_the_last_session_cost`, and `test_ls_v_uses_a_harness_specific_replay_command`.
6. Run `uv run --group dev pytest -q tests/test_cli.py`, `uv run --group dev pytest -q`, and `git diff --check` for `pipeline/cli/main.py` and `tests/test_cli.py`; commit the passing bugfix.

## Acceptance criteria

- `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` passes and asserts the exact remediation, unchanged daemon rows, closed client, and unchanged registry membership.
- `tests/test_cli.py::test_cli_new_then_ls` passes for named-project retrieval, and `tests/test_cli.py::test_ls_says_running_is_unknown_when_no_daemon_answers` passes for daemon failure.
- `tests/test_cli.py::test_ls_filters_all_stage_and_ticket_views` passes for selectors, and `tests/test_cli.py::test_ls_hides_finished_tickets_by_default` passes for default filtering.
- `tests/test_cli.py::test_ls_v_prints_the_last_session_cost` and `tests/test_cli.py::test_ls_v_uses_a_harness_specific_replay_command` pass for row rendering.
- `uv run --group dev pytest -q tests/test_cli.py` exits `0`.
- `uv run --group dev pytest -q` exits `0`.
- `git diff --check` exits `0`.

## Decisions

Bare `pipeline ls` remains a view of registered projects. When the current project is unregistered, `cmd_ls()` reports its local ticket count without adding those rows.

The notice is read-only. Only the operator may run `pipeline register .` and change registry state.

The notice applies only to a successful bare global daemon response. Named-project and daemon-failure paths keep their existing file-fallback behavior.

## Rollback

Revert the commits modifying `pipeline/cli/main.py` and `tests/test_cli.py`. This restores the silent omission and requires no data migration.

## Thread

### 2026-09-08 12:04:13Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-08 12:10:00Z · triage · finding

Reproduced and committed the failure in `002c4b6`.

`cmd_ls()` receives a successful global daemon reply and skips the local-file fallback.
The mocked reply prints `TICKET-999` but no local unregistered-project notice.

Root cause: `rows is None` only detects a failed daemon request.
It does not detect that the current project is absent from a successful global response.

The nearest working case is the no-daemon test.
It reaches the fallback because `connect()` returns no client.

Expected fix scope: `pipeline/cli/main.py` and `tests/test_cli.py`.

### 2026-09-08 12:06:43Z · triage · session · session=01a080e7-cb2a-7a12-9707-26e41ab14344

`triage` ran as session `01a080e7-cb2a-7a12-9707-26e41ab14344`
- replay: `codex exec resume 01a080e7-cb2a-7a12-9707-26e41ab14344`
- log: `.project/logs/TICKET-126-triage-4f83f028.log`
- cost: unknown (the harness reported none)
- tokens: 4,374 out (1,085 thinking) · 479,263 in · 439,040 cache read · 0 cache write

### 2026-09-08 12:06:43Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced the daemon-backed omission in a committed CLI test.

### 2026-09-08 12:11:47Z · planning · plan

The plan preserves global daemon rows and adds one read-only notice for an unregistered current project with local tickets.

`cmd_ls()` will use `registry.projects()` for membership and `ticket_rows()` for the local count. It will not append unregistered rows or register the project.

The regression will also assert unchanged registry membership. Relevant constraints are DEC-011, DEC-114, DEC-116, and DEC-072.

Files: `pipeline/cli/main.py`, `tests/test_cli.py`.

### 2026-09-08 12:15:39Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` fails as required
```

s.chdir(d)
            clim.connect = lambda: Client()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                clim.cmd_ls(argparse.Namespace(project=None, ticket=None,
                                               all=False, stage=None,
                                               verbose=False))
            text = out.getvalue()
            assert "TICKET-999" in text, text
>           assert (f"1 tickets in {d}, which is not registered -- "
                    "run `pipeline register .`") in text, text
E                   AssertionError: TICKET-999   escalated         bugfix    {} 
E                     
E                   assert '1 tickets in /tmp/tmphdmnlizf, which is not registered -- run `pipeline register .`' in 'TICKET-999   escalated         bugfix    {} \n'

tests/test_cli.py:619: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.13s ===============================

```
- ok: `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` fails on base `main` too -- the bug is not already fixed upstream
```
 text, text
E                   AssertionError: TICKET-999   escalated         bugfix    {} 
E                     
E                   assert '1 tickets in /tmp/tmp6qpp8ur2, which is not registered -- run `pipeline register .`' in 'TICKET-999   escalated         bugfix    {} \n'

tests/test_cli.py:619: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.49s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-kb9pxtr9/base
      Built pipeline @ file:///tmp/pipeline-base-kb9pxtr9/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 907ms

```
- `files_declared` is empty
- plan step names no declared file: '1. Extend `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` in `tests/test_cli.py` to assert registry membership remains unchanged.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Run `uv run --group dev pytest -q tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` against `tests/test_cli.py`; expect only the missing-notice assertion to fail.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Update `cmd_ls()` in `pipeline/cli/main.py` to count current-project rows when bare `ls` finds that project absent from `registry.projects()`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '4. Keep daemon rows unchanged in `pipeline/cli/main.py`; print the exact ticket-count remediation only when the unregistered current project has rows.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '5. Run the focused test, `tests/test_cli.py`, and the full suite for `pipeline/cli/main.py` and `tests/test_cli.py`; commit the passing implementation.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-08 12:16:46Z · planning · note

The manual Tier A preflight ran before the dispatcher adopted `files_declared` from the result sidecar.

It reported only `` `files_declared` is empty `` and the five derived path findings. It reported no plan-format, decision-citation, or acceptance-criterion finding.

The result sidecar declares `pipeline/cli/main.py` and `tests/test_cli.py`. The dispatcher will apply those declarations before its Tier A run.

### 2026-09-08 12:17:23Z · planning · session · session=01a080e9-dbac-7e82-97c5-6223f04137ad

`planning` ran as session `01a080e9-dbac-7e82-97c5-6223f04137ad`
- replay: `codex exec resume 01a080e9-dbac-7e82-97c5-6223f04137ad`
- log: `.project/logs/TICKET-126-planning-6edb53fa.log`
- cost: unknown (the harness reported none)
- tokens: 15,327 out (8,966 thinking) · 1,620,180 in · 1,534,720 cache read · 0 cache write

### 2026-09-08 12:17:23Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned a read-only local-project notice for successful global daemon listings.

### 2026-09-08 12:19:09Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` fails as required
```
s.chdir(d)
            clim.connect = lambda: Client()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                clim.cmd_ls(argparse.Namespace(project=None, ticket=None,
                                               all=False, stage=None,
                                               verbose=False))
            text = out.getvalue()
            assert "TICKET-999" in text, text
>           assert (f"1 tickets in {d}, which is not registered -- "
                    "run `pipeline register .`") in text, text
E                   AssertionError: TICKET-999   escalated         bugfix    {} 
E                     
E                   assert '1 tickets in /tmp/tmppiqusljt, which is not registered -- run `pipeline register .`' in 'TICKET-999   escalated         bugfix    {} \n'

tests/test_cli.py:619: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.13s ===============================

```
- ok: `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` fails on base `main` too -- the bug is not already fixed upstream
```
n text, text
E                   AssertionError: TICKET-999   escalated         bugfix    {} 
E                     
E                   assert '1 tickets in /tmp/tmp8soe2u9c, which is not registered -- run `pipeline register .`' in 'TICKET-999   escalated         bugfix    {} \n'

tests/test_cli.py:619: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.80s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-sblxpwkm/base
      Built pipeline @ file:///tmp/pipeline-base-sblxpwkm/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 62ms

```

### 2026-09-08 12:21:17Z · plan-validation · finding · severity=blocking

Verdict: fail.

1. **Root cause vs symptom — pass.** A non-`None` daemon response bypasses file fallback, so `cmd_ls()` never checks current-project membership or local tickets. The plan fixes that cause without adding local rows.
2. **Decision conflict — pass.** The read-only membership check complies with DEC-011, DEC-072, DEC-114, and DEC-116. It changes no registry, socket, dispatcher, or selector semantics.
3. **Scope discipline — pass.** Both file changes trace to the notice and non-mutation criteria.
4. **Falsifiable criteria — pass.** Exact output, retained daemon rows, client closure, unchanged membership, and exit codes fail under concrete regressions.
5. **No research left — pass.** Every step names `cmd_ls()` or the focused test in its concrete file.
6. **Riskiest step — fail.** The plan never identifies conditional placement in `cmd_ls()` as risky or provides an implementation fallback. Rollback only restores the defect.
7. **Regression surface — fail.** The plan does not map named-project, daemon-failure, selector, filtering, or row-rendering behavior to specific tests. A whole-file run is not that mapping.
8. **Blast radius matches class — pass.** Two focused files fit a bugfix.

Unverified: none.

### 2026-09-08 12:22:12Z · plan-validation · session · session=01a080f5-3fd8-7e12-99fc-80e576c908c6

`plan-validation` ran as session `01a080f5-3fd8-7e12-99fc-80e576c908c6`
- replay: `codex exec resume 01a080f5-3fd8-7e12-99fc-80e576c908c6`
- log: `.project/logs/TICKET-126-plan-validation-4654c129.log`
- cost: unknown (the harness reported none)
- tokens: 4,294 out (2,281 thinking) · 448,737 in · 400,384 cache read · 0 cache write

### 2026-09-08 12:22:12Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ Plan omits its riskiest-step fallback and explicit regression-surface coverage.

### 2026-09-08 12:30:00Z · planning · plan

Revised the plan after the blocking validation finding.

The plan marks daemon-response provenance and notice placement as the riskiest change. It supplies helper extraction as the implementation fallback.

Specific tests now cover named-project retrieval, daemon failure, selectors, default filtering, and row rendering. The reproduction also checks unchanged daemon rows and registry membership.

### 2026-09-08 12:28:04Z · planning · session · session=01a080f8-0840-7fb2-8904-70a83047f991

`planning` ran as session `01a080f8-0840-7fb2-8904-70a83047f991`
- replay: `codex exec resume 01a080f8-0840-7fb2-8904-70a83047f991`
- log: `.project/logs/TICKET-126-planning-e67c7899.log`
- cost: unknown (the harness reported none)
- tokens: 8,802 out (4,016 thinking) · 877,500 in · 816,000 cache read · 0 cache write

### 2026-09-08 12:28:04Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Revised the plan with a conditional-placement fallback and named regression coverage.

### 2026-09-08 12:29:09Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` fails as required
```
s.chdir(d)
            clim.connect = lambda: Client()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                clim.cmd_ls(argparse.Namespace(project=None, ticket=None,
                                               all=False, stage=None,
                                               verbose=False))
            text = out.getvalue()
            assert "TICKET-999" in text, text
>           assert (f"1 tickets in {d}, which is not registered -- "
                    "run `pipeline register .`") in text, text
E                   AssertionError: TICKET-999   escalated         bugfix    {} 
E                     
E                   assert '1 tickets in /tmp/tmpyd1ydsmz, which is not registered -- run `pipeline register .`' in 'TICKET-999   escalated         bugfix    {} \n'

tests/test_cli.py:619: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.12s ===============================

```
- ok: `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` fails on base `main` too -- the bug is not already fixed upstream
```
n text, text
E                   AssertionError: TICKET-999   escalated         bugfix    {} 
E                     
E                   assert '1 tickets in /tmp/tmplxy9snk_, which is not registered -- run `pipeline register .`' in 'TICKET-999   escalated         bugfix    {} \n'

tests/test_cli.py:619: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.45s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-0woq6bng/base
      Built pipeline @ file:///tmp/pipeline-base-0woq6bng/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 68ms

```

### 2026-09-08 12:34:49Z · plan-validation · finding

Verdict: pass.

1. **Root cause vs symptom — pass.** A successful global daemon reply bypasses fallback, so `cmd_ls()` performs no local membership check. The plan fixes that omission without adding local rows.
2. **Decision conflict — pass.** DEC-011 preserves registered daemon rows and shared `ticket_rows()`. DEC-072, DEC-114, DEC-116, and DEC-062 retain registry, selector, and fallback semantics.
3. **Scope discipline — pass.** Both planned files trace to the notice and regression criteria.
4. **Falsifiable criteria — pass.** Exact output, absent local rows, retained daemon rows, client closure, registry immutability, and exit codes expose incorrect implementations.
5. **No research left — pass.** Each change names `cmd_ls()` or a concrete test function in its target file.
6. **Riskiest step — pass.** Step 4 identifies response provenance and placement. It falls back to a notice helper if inline logic couples retrieval and presentation.
7. **Regression surface — pass.** Named tests cover named retrieval, daemon failure, selectors, default filtering, and verbose row rendering.
8. **Blast radius matches class — pass.** Two focused files match a bugfix.

Unverified: none.

### 2026-09-08 12:36:43Z · plan-validation · session · session=01a08102-0048-7773-9510-8876329a737a

`plan-validation` ran as session `01a08102-0048-7773-9510-8876329a737a`
- replay: `codex exec resume 01a08102-0048-7773-9510-8876329a737a`
- log: `.project/logs/TICKET-126-plan-validation-adc06fd0.log`
- cost: unknown (the harness reported none)
- tokens: 4,920 out (1,763 thinking) · 525,677 in · 479,744 cache read · 0 cache write

### 2026-09-08 12:36:43Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Revised plan passes all eight judgment checks with a concrete fallback and named regression coverage.

### 2026-09-08 12:41:10Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-08 12:42:16Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` fails as required
```
s.chdir(d)
            clim.connect = lambda: Client()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                clim.cmd_ls(argparse.Namespace(project=None, ticket=None,
                                               all=False, stage=None,
                                               verbose=False))
            text = out.getvalue()
            assert "TICKET-999" in text, text
>           assert (f"1 tickets in {d}, which is not registered -- "
                    "run `pipeline register .`") in text, text
E                   AssertionError: TICKET-999   escalated         bugfix    {} 
E                     
E                   assert '1 tickets in /tmp/tmpr6616iix, which is not registered -- run `pipeline register .`' in 'TICKET-999   escalated         bugfix    {} \n'

tests/test_cli.py:619: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.12s ===============================

```
- ok: `tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others` fails on base `main` too -- the bug is not already fixed upstream
```
n text, text
E                   AssertionError: TICKET-999   escalated         bugfix    {} 
E                     
E                   assert '1 tickets in /tmp/tmpamwn33by, which is not registered -- run `pipeline register .`' in 'TICKET-999   escalated         bugfix    {} \n'

tests/test_cli.py:619: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_ls_names_an_unregistered_project_when_the_daemon_lists_others
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.45s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-wv2h3kqj/base
      Built pipeline @ file:///tmp/pipeline-base-wv2h3kqj/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 73ms

```

### 2026-09-08 12:42:16Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-08 12:45:00Z · implementing · todo

1. [in progress] Strengthen the daemon-response regression in `tests/test_cli.py`.
2. [pending] Verify the focused test fails for the missing notice.
3. [pending] Add the read-only notice in `pipeline/cli/main.py`.
4. [pending] Run focused and regression tests.
5. [pending] Run both suites, check the diff, and commit.

### 2026-09-08 12:48:00Z · implementing · finding

Implemented the approved fix in commit `5f7252d`.

1. [done] Strengthened the daemon-response regression. It keeps `TICKET-999`, excludes `TICKET-001`, closes the client, and preserves registry membership.
2. [done] Ran the focused test before production code. It failed only on the missing remediation assertion.
3. [done] Recorded a successful bare global response before fallback. The notice uses read-only membership and local-row checks.
4. [done] Ran seven named regression tests. All passed.
5. [done] Ran `tests/test_cli.py` (64 passed), the full suite (607 passed), and `git diff --check` (exit 0).

The daemon-failure test now asserts no registration remediation. Its input is a local ticket with no daemon response. The successful-global test fails without the new notice.

### 2026-09-08 12:47:48Z · implementing · session · session=01a0810a-65ef-7862-af1f-c2b307204574

`implementing` ran as session `01a0810a-65ef-7862-af1f-c2b307204574`
- replay: `codex exec resume 01a0810a-65ef-7862-af1f-c2b307204574`
- log: `.project/logs/TICKET-126-implementing-15db00b8.log`
- cost: unknown (the harness reported none)
- tokens: 5,614 out (2,142 thinking) · 951,237 in · 899,584 cache read · 0 cache write

### 2026-09-08 12:47:48Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added the read-only unregistered-project notice and committed 5f7252d.

### 2026-09-08 12:52:30Z · review · finding

Verdict: fail.

1. **blocking** — Bare `pipeline ls` in a linked worktree prints an impossible remediation. `pipeline/cli/main.py:499` treats every path absent from `registry.projects()` as registrable. `pipeline/daemon/registry.py:60` deliberately excludes linked worktrees, while `pipeline/daemon/registry.py:168-170` makes `pipeline register .` fail with `is a git worktree, not a project`. A linked worktree with copied ticket files reaches the notice whenever the daemon returns global rows. Add the existing `is_worktree()` distinction and a regression covering this call sequence.

Refutation failed: no caller or earlier guard blocks `cmd_ls()` in a linked worktree. `tests/test_cli.py:808-824` proves that state is supported and registration is refused.

The selected test rerun could not start because UV tried to create `/home/chezzijr/.cache/uv/.tmpxp1OO0` on a read-only filesystem. The committed implementing evidence reports 64 CLI tests and 607 total tests passed.

### 2026-09-08 12:53:28Z · review · session · session=01a0810f-774d-7ee1-bccc-35c0fcd9b7e0

`review` ran as session `01a0810f-774d-7ee1-bccc-35c0fcd9b7e0`
- replay: `codex exec resume 01a0810f-774d-7ee1-bccc-35c0fcd9b7e0`
- log: `.project/logs/TICKET-126-review-391191fe.log`
- cost: unknown (the harness reported none)
- tokens: 7,618 out (3,588 thinking) · 1,151,676 in · 1,094,912 cache read · 0 cache write

### 2026-09-08 12:53:28Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ Linked worktrees receive an impossible registration remediation.

### 2026-09-08 13:00:00Z · implementing · todo

1. [done] Added a linked-worktree regression in `tests/test_cli.py`.
2. [done] Verified it failed because `pipeline register .` printed.
3. [done] Excluded linked worktrees from the `cmd_ls()` remediation.
4. [done] Ran focused, CLI, full-suite, and diff checks.
5. [done] Committed the corrected bugfix.

### 2026-09-08 13:05:00Z · implementing · finding

Commit `74193e5` fixes the review finding.

1. The new linked-worktree regression failed before the code change on `assert "pipeline register ." not in text`.
2. `cmd_ls()` now skips remediation when `registry.is_worktree(proj(args))` is true.
3. The successful-global main-checkout notice still passes its existing regression.
4. The focused matrix passed: 8 tests.
5. `tests/test_cli.py` passed: 65 tests. The full suite passed: 608 tests. `git diff --check` exited 0.

### 2026-09-08 13:19:05Z · implementing · session · session=01a08126-e7cc-78c1-816b-4d5f786a89ea

`implementing` ran as session `01a08126-e7cc-78c1-816b-4d5f786a89ea`
- replay: `codex exec resume 01a08126-e7cc-78c1-816b-4d5f786a89ea`
- log: `.project/logs/TICKET-126-implementing-0cc25f49.log`
- cost: unknown (the harness reported none)
- tokens: 5,749 out (1,341 thinking) · 1,156,794 in · 1,102,848 cache read · 0 cache write

### 2026-09-08 13:19:05Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Suppressed the impossible linked-worktree registration notice and committed 74193e5.

### 2026-09-08 13:22:01Z · review · finding

Verdict: ok.

No blocking findings.

1. The prior finding is resolved. `pipeline/cli/main.py:499` uses `registry.is_worktree()` before constructing the notice.
2. `pipeline/daemon/registry.py:65` supplies the same linked-worktree distinction used by registration refusal.
3. `tests/test_cli.py:635` creates a real linked worktree. Its assertion at line 669 fails if the impossible remediation returns.
4. The original main-checkout assertion at `tests/test_cli.py:625` preserves the eligible registration notice.
5. `git diff --check 5f7252d..HEAD` exited 0.

The focused rerun did not start. The read-only guard rejected the required cache override: `ticket-126-uv-cache is not on the read-only allowlist.` Implementing evidence reports 8 focused tests, 65 CLI tests, and 608 total tests passed.

### 2026-09-08 13:22:46Z · review · session · session=01a0812c-201a-7fb0-b235-411ca095754a

`review` ran as session `01a0812c-201a-7fb0-b235-411ca095754a`
- replay: `codex exec resume 01a0812c-201a-7fb0-b235-411ca095754a`
- log: `.project/logs/TICKET-126-review-9def6fe3.log`
- cost: unknown (the harness reported none)
- tokens: 5,156 out (2,695 thinking) · 444,639 in · 411,904 cache read · 0 cache write

### 2026-09-08 13:22:46Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ No blocking findings; the linked-worktree guard resolves the prior review issue.

### 2026-09-08 13:23:53Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-08 13:23:55Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/126


Rebasing (1/3)Rebasing (2/3)Rebasing (3/3)Successfully rebased and updated refs/heads/ticket/126.
Already up to date.
Updating 5dc165f..b851c02
Fast-forward
 pipeline/cli/main.py | 11 ++++++
 tests/test_cli.py    | 98 +++++++++++++++++++++++++++++++++++++++++++++++++++-
 2 files changed, 108 insertions(+), 1 deletion(-)

```

### 2026-09-08 13:23:55Z · merging · decision

decision recorded as `DEC-126`
