---
id: TICKET-140
stage: done
class: feature
branch: ticket/140
test_file:
- tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
- tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
files_declared:
- README.md
- pipeline/cli/main.py
- pipeline/core/ticket.py
- pipeline/templates/skills/file-ticket/SKILL.md
- tests/test_cli.py
- tests/test_ticket.py
counters:
  plan_validation_attempts: 0
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 3
  plan_files: 6
  no_result: 0
  plan_rejections: 1
  api_errors: 1
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: holistic-review
  id: 01a0bc9a-c7a9-7222-a108-773fe37856b9
  replay: codex exec resume 01a0bc9a-c7a9-7222-a108-773fe37856b9
  log: .project/logs/TICKET-140-holistic-review-6cd59cd4.log
  cost_usd: null
approved_by: chezzijr
approved_at: '2026-09-18T17:03:36.722534+00:00'
---

## Summary

`pipeline new` races triage on the Summary, and there is no way to close a ticket that is not at `awaiting-approval`

Expected change files: `pipeline/cli/main.py`, `pipeline/templates/skills/file-ticket/SKILL.md`, `README.md`, `tests/test_cli.py` (or wherever the CLI is already tested).

Two gaps in the ticket lifecycle CLI, filed together because both live in `pipeline/cli/main.py` and the file-ticket skill.

1. Race. `cmd_new` (`pipeline/cli/main.py:133`, main at f09c5d6) writes the ticket at `stage: new` with the bare title as `## Summary`, and the file-ticket skill (SKILL.md:101) then tells the filer to rewrite `## Summary` as a second step. A running dispatcher can claim the ticket in between. Observed: triage leased three tickets between `pipeline new` and the Summary write, and all three escalated with `Summary changed while `triage` held the ticket` (`pipeline/daemon/supervisor.py:1309`). Suggested fix: `pipeline new --summary-file PATH` (and `-` for stdin) so the ticket is born complete; the skill then uses it instead of the post-hoc edit. The ticket must still be written in one step (never a half-written file the dispatcher can glob).

2. No close. `cmd_reject` (`main.py:337`) dies unless the stage is `awaiting-approval`, and it sends the ticket back to `planning`, not to `rejected`. Closing a superseded ticket needs `pipeline resume <id> --stage rejected`, which records it as a "resume". Suggested: `pipeline close <id> --reason TEXT` -> `stage: rejected`, reason appended to `## Thread` attributed to the human, lease released, same live-lease refusal and `--force` as `cmd_resume` (`main.py:406`). An empty reason is refused.

Expected: `pipeline new "t" --summary-file f` produces a ticket whose `## Summary` is the file's content and never exists with the bare title; `pipeline close TICKET-X --reason "superseded by Y"` on an `escalated` ticket leaves `stage: rejected` and a human thread entry containing the reason. README and the file-ticket skill document both.

## Reproduction

`tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket`

`uv run --group dev pytest -q tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason`

expect: unrecognized arguments: --summary-file

The command exits 2. The new-command proof reports `unrecognized arguments: --summary-file /tmp/tmp3kna69bh/summary.md`.

`tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` runs in the same command.

expect: argument cmd: invalid choice: 'close'

The command exits 2. The close-command proof reports `argument cmd: invalid choice: 'close'`.

## Digest

- This revision addresses both human rejection reasons: `cmd_close` refuses `done` and `rejected`, and close reasons use a retained `close` kind instead of `rejection`.
- `pipeline/cli/main.py` owns `cmd_new`, lifecycle commands, `record`, and argparse registration; import `write_atomic` for complete ticket publication.
- `cmd_resume` defines the lease rule: refuse only when `Ticket.lease_active()` and `holder_alive(holder)` are both true, unless `--force` is set.
- `pipeline/core/ticket.py` validates append kinds through `KINDS` and permanently retains human kinds through `VIEW_KEEP_KINDS`; add `close` to both sets.
- `KINDS` and `VIEW_KEEP_KINDS` are not fenced; `pipeline/core/machine.py:FENCED` protects only `validate_meta` within `pipeline/core/ticket.py`.
- `tests/test_cli.py` drives the real CLI; commit `c1b721f` adds failing proofs for file-backed summaries and closing an escalated ticket.
- `tests/test_ticket.py::test_the_stage_view_keeps_every_human_entry` is the existing bounded-view regression pattern for an old `close` marker.
- `README.md` documents operators; `pipeline/templates/skills/file-ticket/SKILL.md` currently instructs filers to rewrite `## Summary` after creation.
- `pipeline/templates/ticket.md` needs no change: `cmd_new` can render `{{title}}` from the complete summary before atomic publication.

## Decisions checked

- DEC-031: keep `pipeline reject` limited to plan rejection at `awaiting-approval`; implement terminal cancellation as the separate `pipeline close` command.
- DEC-110: a live lease blocks mutation only while its holder process lives; `--force` releases it and may cause the running child to escalate later.
- DEC-114: `pipeline new` must preserve its unregistered-project warning and must not register the project as a side effect.
- DEC-128: the filing skill must keep requiring every expected change file in `## Summary` for cheap-route scope review.
- DEC-129: bounded views still retain human entries and announce omissions; classify `close` as a retained human kind.
- DEC-139: a `rejected` dependency is unsatisfiable, so `pipeline close` must not rewrite a completed `done` ticket to `rejected`.

## Plan

1. Extend `tests/test_cli.py` with real-process cases for stdin summaries, unreadable or blank summary refusal, empty close reasons, live and dead holders, forced attribution, transition recording, separate `done` and `rejected` refusal, help, and documentation; extend `tests/test_ticket.py::test_the_stage_view_keeps_every_human_entry` with an old `close` marker; run these nodes red and commit the tests.
2. Update `pipeline/cli/main.py` so `cmd_new` reads a path or `-` stdin completely, rejects unreadable or blank input before creating the ticket, publishes with `write_atomic`, and preserves title-only creation and registry warnings; add a shared live-holder helper for `cmd_resume` and `cmd_close`; make close reject `done` and `rejected` with the current stage, validate the reason, enforce DEC-110 including `--force`, append an attributed `close` entry, release the lease, save `stage: rejected`, record the saved transition, and register `close ID --reason TEXT [--force]`; update `pipeline/core/ticket.py` to accept `close` in `KINDS` and preserve it in `VIEW_KEEP_KINDS`; run the focused `tests/test_cli.py` and `tests/test_ticket.py` nodes green and commit the fix.
3. Revise `README.md` to document atomic path/stdin creation, non-terminal close, terminal-state refusal, lease handling, forced-close consequences, and the distinction from plan rejection; revise `pipeline/templates/skills/file-ticket/SKILL.md` to build the complete summary before `pipeline new --summary-file`, stop post-creation edits, and hand users `pipeline close --reason` only for non-terminal abandoned tickets; run the documentation contract test and commit the documentation.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket tests/test_cli.py::test_new_reads_the_summary_from_stdin_before_publishing` exits 0 and preserves title-only creation.
- `uv run --group dev pytest -q tests/test_cli.py::test_new_refuses_an_unreadable_or_blank_summary_before_publishing` exits 0 and leaves no ticket file.
- `uv run --group dev pytest -q tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason tests/test_cli.py::test_close_refuses_an_empty_reason tests/test_ticket.py::test_the_stage_view_keeps_every_human_entry` exits 0 and retains the close reason as kind `close` in old bounded views.
- `uv run --group dev pytest -q tests/test_cli.py::test_close_refuses_a_done_ticket tests/test_cli.py::test_close_refuses_an_already_rejected_ticket` exits 0 and each error names its unchanged current stage.
- `uv run --group dev pytest -q tests/test_cli.py::test_close_refuses_a_live_lease_without_force tests/test_cli.py::test_close_force_releases_a_live_lease_and_records_the_holder tests/test_cli.py::test_close_treats_a_dead_lease_holder_as_free` exits 0.
- `uv run --group dev pytest -q tests/test_cli.py::test_close_records_a_transition tests/test_cli.py::test_new_and_close_help_and_docs_name_the_safe_workflows` exits 0.
- `uv run --group dev pytest -q tests/test_cli.py` exits 0 with no CLI regression.
- `uv run --group dev pytest -q tests/test_ticket.py` exits 0 with no ticket-model regression.
- `uv run --group dev pytest -q` exits 0 with no suite regression.

## Decisions

- `pipeline new --summary-file` reads and validates the entire source before atomically publishing the ticket; `-` selects standard input.
- `pipeline close` is terminal cancellation, not plan rejection. It requires a human reason and moves any non-`done`, non-`rejected` ticket to `rejected`.
- Closing a `done` or `rejected` ticket is refused without mutation because rewriting terminal history can invalidate dependent tickets.
- Close reasons use the human `close` thread kind. `stage_view` never omits that kind, and planning never mistakes it for plan rejection.
- Closing follows DEC-110 lease semantics. A live, living holder requires `--force`; a stale holder does not.
- Forced close releases the lease but does not suppress the running child's later tamper escalation.
- `pipeline reject` remains restricted to `awaiting-approval` and continues charging `plan_rejections`.

## Rollback

Revert the three commits together to restore title-only creation, existing thread kinds, and the previous lifecycle commands. Step 2 is riskiest because it mutates control fields around live leases; if its terminal-state, kind-retention, or lease tests fail, remove `close` registration and its `close` kind while leaving `cmd_resume` unchanged.

## Thread

### 2026-09-18 16:19:00Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-18 16:25:00Z · triage · reproduction

Reproduced both CLI gaps with committed tests in `c1b721f`.

1. `cmd_new` parses no `--summary-file`; its direct template write publishes the title as `## Summary`.
2. The parser registers no `close` command; `cmd_reject` only accepts `awaiting-approval` and returns to `planning`.
3. `cmd_resume` contains the live-lease refusal and `--force` behavior that `close` must preserve.

The selected command failed both tests. The failure output is recorded in `## Reproduction`.

Expected fix files: `pipeline/cli/main.py`, `pipeline/templates/skills/file-ticket/SKILL.md`, `README.md`, and `tests/test_cli.py`.

### 2026-09-18 16:20:54Z · triage · session · session=01a0b550-99f1-7350-9950-8a6ca11f941c

`triage` ran as session `01a0b550-99f1-7350-9950-8a6ca11f941c`
- replay: `codex exec resume 01a0b550-99f1-7350-9950-8a6ca11f941c`
- log: `.project/logs/TICKET-140-triage-acca5f02.log`
- cost: unknown (the harness reported none)
- tokens: 3,541 out (1,123 thinking) · 413,960 in · 377,088 cache read · 0 cache write

### 2026-09-18 16:20:54Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Added committed failing CLI proofs for summary-file creation and ticket close.

### 2026-09-18 16:26:01Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails as required
```

et.\n")
    
        r = cli(d, "new", "placeholder title", "--summary-file", str(summary))
    
>       assert r.returncode == 0, r.stderr
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: unrecognized arguments: --summary-file /tmp/tmp1btp34ku/summary.md
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmp1btp34ku/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails as required
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.39s ===============================

```
- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails on base `main` too -- the bug is not already fixed upstream
```
     assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-rljsp1uo/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmplj...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmpljfi48a0/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.67s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-rljsp1uo/base
      Built pipeline @ file:///tmp/pipeline-base-rljsp1uo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 81ms

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails on base `main` too -- the bug is not already fixed upstream
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-rljsp1uo/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpqv...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.39s ===============================

```
- `files_declared` is empty
- plan step names no declared file: '1. Extend `tests/test_cli.py` with real-process cases for `--summary-file -`, unreadable or blank summary refusal, close reason validation, live and dead lease holders, forced close attribution, transition recording, CLI help, and both documentation contracts; run the focused nodes red and commit the tests.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Update `pipeline/cli/main.py` so `cmd_new` reads a path or stdin completely before rendering, refuses blank or unreadable input before publication, and publishes through `write_atomic`; keep title-only creation and registry warnings unchanged. Add a shared live-holder helper used by `cmd_resume` and new `cmd_close`; make close require a reason, refuse a live holder before mutation, support `--force`, append an attributed human rejection, release the lease, save `stage: rejected`, record the transition after saving, and register `close ID --reason TEXT [--force]`; run the focused `tests/test_cli.py` nodes green and commit the fix.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Revise `README.md` to document atomic file/stdin creation, terminal close, lease refusal, forced-close consequences, and the distinction from plan rejection. Revise `pipeline/templates/skills/file-ticket/SKILL.md` to build the complete summary first, pass it with `--summary-file`, stop post-creation edits, and hand users `pipeline close --reason` for abandoned tickets; run the documentation contract tests and commit the documentation.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-18 16:28:09Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails as required
```
et.\n")
    
        r = cli(d, "new", "placeholder title", "--summary-file", str(summary))
    
>       assert r.returncode == 0, r.stderr
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: unrecognized arguments: --summary-file /tmp/tmp3zl1oaou/summary.md
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmp3zl1oaou/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.24s ===============================

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails as required
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.41s ===============================

```
- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails on base `main` too -- the bug is not already fixed upstream
```
     assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-ab11bht2/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpa8...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmpa8ti9bq5/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.61s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ab11bht2/base
      Built pipeline @ file:///tmp/pipeline-base-ab11bht2/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 58ms

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails on base `main` too -- the bug is not already fixed upstream
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-ab11bht2/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpzc...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.40s ===============================

```

### 2026-09-18 16:29:00Z · planning · note

Planned three test-first commits across `tests/test_cli.py`, `pipeline/cli/main.py`, `README.md`, and `pipeline/templates/skills/file-ticket/SKILL.md`.

The direct gate found only the pre-claim `files_declared` gap. The dispatcher applies that claim from this stage's sidecar after exit. The same gate passed with the four-file claim overlaid in memory: `gate: PASS`.

The plan preserves DEC-031's plan-only rejection and DEC-110's live-holder rule. It also preserves DEC-114's registry behavior and DEC-128's summary guidance.

### 2026-09-18 16:29:05Z · planning · session · session=01a0b552-2b5e-7922-b134-941b6d78fee0

`planning` ran as session `01a0b552-2b5e-7922-b134-941b6d78fee0`
- replay: `codex exec resume 01a0b552-2b5e-7922-b134-941b6d78fee0`
- log: `.project/logs/TICKET-140-planning-62253af2.log`
- cost: unknown (the harness reported none)
- tokens: 15,706 out (7,887 thinking) · 2,376,280 in · 2,278,912 cache read · 0 cache write

### 2026-09-18 16:29:05Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned atomic summary creation and lease-safe terminal ticket closure.

### 2026-09-18 16:38:11Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails as required
```
et.\n")
    
        r = cli(d, "new", "placeholder title", "--summary-file", str(summary))
    
>       assert r.returncode == 0, r.stderr
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: unrecognized arguments: --summary-file /tmp/tmplfgnq0m7/summary.md
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmplfgnq0m7/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.23s ===============================

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails as required
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.42s ===============================

```

- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails on base `main` too -- the bug is not already fixed upstream
```
     assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-25llpv2v/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmps5...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmps5524ht5/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.59s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-25llpv2v/base
      Built pipeline @ file:///tmp/pipeline-base-25llpv2v/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 70ms

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails on base `main` too -- the bug is not already fixed upstream
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-25llpv2v/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpgx...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.42s ===============================

```

### 2026-09-18 16:53:12Z · plan-validation · note

**Plan validation: PASS**

- **Root cause vs symptom — Pass.** `cmd_new` publishes a placeholder before the filer’s second edit. Missing terminal closure forces misuse of `resume`. The plan fixes both causes.
- **Decision conflict — Pass.** It preserves DEC-031 rejection scope, DEC-110 lease semantics, DEC-114 warnings, and DEC-128 filing guidance.
- **Scope discipline — Pass.** Every change traces to atomic creation, terminal closure, regression coverage, or their documentation.
- **Falsifiable criteria — Pass.** Real-process tests distinguish missing, blank, stdin, lease, attribution, transition, and documentation failures with concrete outcomes.
- **No research left — Pass.** Steps name `tests/test_cli.py`, `cmd_new`, `cmd_resume`, `cmd_close`, `README.md`, and the filing skill.
- **Riskiest step — Pass.** Lease-aware closure is identified. Its fallback removes `close` registration and preserves `cmd_resume` when lease tests fail.
- **Regression surface — Pass.** Risks include title-only creation, registry warnings, reject/resume leases, event recording, and help. Focused CLI tests and the full suite cover them.
- **Blast radius — Pass.** Four files match this lifecycle bugfix.

**Unverified:** None.

### 2026-09-18 16:54:24Z · plan-validation · session · session=01a0b56e-5636-7df2-bce6-a2ba09c06205

`plan-validation` ran as session `01a0b56e-5636-7df2-bce6-a2ba09c06205`
- replay: `codex exec resume 01a0b56e-5636-7df2-bce6-a2ba09c06205`
- log: `.project/logs/TICKET-140-plan-validation-f29026a2.log`
- cost: unknown (the harness reported none)
- tokens: 6,989 out (3,059 thinking) · 731,385 in · 687,360 cache read · 0 cache write

### 2026-09-18 16:54:24Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan fixes both lifecycle causes with atomic publication, lease-safe closure, focused tests, and documented fallbacks.

### 2026-09-18 16:54:45Z · human · rejection

Plan is close; two gaps, add them and resubmit. (1) cmd_close must refuse a ticket already at `done` or `rejected` (die with the current stage) -- closing a merged ticket as rejected would falsify history, and dependents would then escalate via dep_unsatisfiable. Add a test for each. (2) Do not record the close reason with kind `rejection`: planning.md treats every `rejection` entry as 'the human did not want the last plan', so a closed-then-resumed ticket would replan against a reason that is not about its plan. Use a distinct kind (e.g. `close`) and add it to the human-written kinds stage_view keeps (VIEW_KEEP_KINDS / the set at pipeline/core/ticket.py:539) -- check neither set is fenced (validate_meta is the only fenced symbol in ticket.py). Keep everything else as planned.

### 2026-09-18 17:08:00Z · planning · note

Revised the plan for both rejection reasons.

- `pipeline close` now refuses `done` and `rejected`; separate CLI tests require each error to name the unchanged stage.
- Close reasons use kind `close`, added to `KINDS` and `VIEW_KEEP_KINDS`; the bounded-view test keeps an old close marker.
- Added `pipeline/core/ticket.py` and `tests/test_ticket.py` to the six-file scope.

Checked DEC-129 for bounded human entries and DEC-139 for rejected dependency semantics. Neither edited ticket symbol is fenced.

`uv run pipeline --project /home/chezzijr/proj/agent-pipeline gate TICKET-140` printed `gate: PASS`.

### 2026-09-18 16:58:34Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails as required
```
et.\n")
    
        r = cli(d, "new", "placeholder title", "--summary-file", str(summary))
    
>       assert r.returncode == 0, r.stderr
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: unrecognized arguments: --summary-file /tmp/tmpkxe4fpse/summary.md
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmpkxe4fpse/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails as required
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.34s ===============================

```
- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails on base `main` too -- the bug is not already fixed upstream
```
     assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-yye5r7lj/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpoz...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmpozkvkqpl/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.59s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yye5r7lj/base
      Built pipeline @ file:///tmp/pipeline-base-yye5r7lj/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 64ms

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails on base `main` too -- the bug is not already fixed upstream
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-yye5r7lj/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmp34...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.33s ===============================

```

### 2026-09-18 16:59:09Z · planning · session · session=01a0b571-2912-70d0-aed3-a570d381e3a4

`planning` ran as session `01a0b571-2912-70d0-aed3-a570d381e3a4`
- replay: `codex exec resume 01a0b571-2912-70d0-aed3-a570d381e3a4`
- log: `.project/logs/TICKET-140-planning-6f950fc0.log`
- cost: unknown (the harness reported none)
- tokens: 9,005 out (3,901 thinking) · 785,617 in · 727,424 cache read · 0 cache write

### 2026-09-18 16:59:09Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Revised terminal close to preserve completed history and retain a distinct human close reason.

### 2026-09-18 17:01:02Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails as required
```
et.\n")
    
        r = cli(d, "new", "placeholder title", "--summary-file", str(summary))
    
>       assert r.returncode == 0, r.stderr
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: unrecognized arguments: --summary-file /tmp/tmpcmhxtmhl/summary.md
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmpcmhxtmhl/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.22s ===============================

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails as required
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.43s ===============================

```
- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails on base `main` too -- the bug is not already fixed upstream
```
     assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-616jp093/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmps1...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmps17ki_gq/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.59s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-616jp093/base
      Built pipeline @ file:///tmp/pipeline-base-616jp093/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 76ms

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails on base `main` too -- the bug is not already fixed upstream
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-616jp093/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpde...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.43s ===============================

```

### 2026-09-18 17:01:49Z · plan-validation · note

- **Root cause vs symptom — pass.** Atomic publication removes the incomplete-summary window. A distinct close command fills the terminal-cancellation gap without weakening plan rejection.
- **Decision conflict — pass.** The plan follows DEC-031, DEC-110, DEC-114, DEC-128, DEC-129, and DEC-139. Terminal-state refusal and retained `close` entries resolve the prior conflicts.
- **Scope discipline — pass.** All six files support CLI behavior, thread retention, tests, or required documentation.
- **Falsifiable criteria — pass.** Tests can fail on premature publication, mutation, wrong attribution, lost reasons, lease violations, missing transitions, or regressions.
- **No research left — pass.** Each step names concrete files, commands, test nodes, and implementation symbols.
- **Riskiest step — pass.** Step 2 owns lease and terminal mutation. The rollback removes close registration and kind changes while preserving `cmd_resume`.
- **Regression surface — pass.** Title-only creation, registry warnings, resume leases, rejection semantics, bounded views, and CLI parsing have focused or full-module coverage.
- **Blast radius matches class — pass.** Six files are proportionate for two related CLI lifecycle bugs, including tests and documentation.

Unverified: none.

✓ The revised plan passes all judgment checks and addresses both human rejection reasons.

### 2026-09-18 17:03:25Z · plan-validation · session · session=01a0b576-ea59-7a53-abe6-d90825a84187

`plan-validation` ran as session `01a0b576-ea59-7a53-abe6-d90825a84187`
- replay: `codex exec resume 01a0b576-ea59-7a53-abe6-d90825a84187`
- log: `.project/logs/TICKET-140-plan-validation-af295b0e.log`
- cost: unknown (the harness reported none)
- tokens: 5,699 out (2,413 thinking) · 513,318 in · 483,328 cache read · 0 cache write

### 2026-09-18 17:03:25Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Revised plan passes all eight judgment checks and addresses both human rejection reasons.

### 2026-09-18 17:03:36Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-18 17:13:34Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails as required
```
et.\n")
    
        r = cli(d, "new", "placeholder title", "--summary-file", str(summary))
    
>       assert r.returncode == 0, r.stderr
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: unrecognized arguments: --summary-file /tmp/tmp671d0qva/summary.md
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-140/.venv/bin/python', '-m', 'pipeline', ...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmp671d0qva/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.44s ===============================

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-18 16:26:01Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket` fails on base `main` too -- the bug is not already fixed upstream
```
     assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-mrrnsayo/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpkm...cs}\n                   ...\n__main__.py: error: unrecognized arguments: --summary-file /tmp/tmpkm_1zqjd/summary.md\n').returncode

tests/test_cli.py:862: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_new_reads_the_summary_before_publishing_the_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.59s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-mrrnsayo/base
      Built pipeline @ file:///tmp/pipeline-base-mrrnsayo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 72ms

```
- ok: `tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason` fails on base `main` too -- the bug is not already fixed upstream
```
__main__.py [-h] [--project PROJECT]
E                            {init,new,gate,config,skills,plan,decisions,approve,reject,note,answer,resume,logs,ls,status,tui,diagnostics,register,unregister,projects,start,stop,run,metrics}
E                            ...
E         __main__.py: error: argument cmd: invalid choice: 'close' (choose from init, new, gate, config, skills, plan, decisions, approve, reject, note, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-mrrnsayo/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpwq...ote, answer, resume, logs, ls, status, tui, diagnostics, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:880: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_close_rejects_an_escalated_ticket_with_a_human_reason
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.41s ===============================

```

### 2026-09-18 17:13:35Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-19 · implementing · note

Todo:

1. [in progress] Run and extend the scoped CLI and ticket-model tests.
2. [pending] Add atomic summaries, terminal close, and retained close entries.
3. [pending] Document safe summary filing and ticket closing.

### 2026-09-18 17:14:39Z · implementing · session · session=01a0b582-644b-7933-9b18-5ba9189e4ae9

`implementing` ran as session `01a0b582-644b-7933-9b18-5ba9189e4ae9`
- replay: `codex exec resume 01a0b582-644b-7933-9b18-5ba9189e4ae9`
- log: `.project/logs/TICKET-140-implementing-9d7ac9e0.log`

### 2026-09-18 17:14:39Z · implementing · note

`implementing` was refused by the API (terminal_reason=api_error, attempt 1) -- waiting 30 seconds

### 2026-09-20 01:50:46Z · implementing · note

`implementing` API retry wait expired (attempt 1) -- respawning

### 2026-09-20 · implementing · note

Todo:

1. [in progress] Extend and run the scoped CLI and ticket-model tests.
2. [pending] Complete atomic summaries, terminal close, and retained close entries.
3. [pending] Document safe summary filing and ticket closing.

### 2026-09-20 · implementing · note

Completed all plan steps.

1. Added path and stdin summary tests, blank and unreadable refusal tests, close lease tests, terminal-state tests, event tests, help tests, and close-view retention.
2. Added atomic `--summary-file` filing, `close`, shared lease handling, and retained `close` thread entries.
3. Documented atomic filing and safe closing in README and file-ticket.

The new tests failed red on missing parser registration and `close` kind. They pass green after the implementation.

`uv run --group dev pytest -q tests/test_cli.py tests/test_ticket.py` passed: `109 passed in 28.85s`.

`uv run --group dev pytest -q` passed: `648 passed in 70.91s`.

Committed `3f7944f` as `feat(TICKET-140): add atomic filing and ticket close`.

### 2026-09-20 01:59:43Z · implementing · session · session=01a0bc82-43a0-7fe0-b292-5b97231ba9ae

`implementing` ran as session `01a0bc82-43a0-7fe0-b292-5b97231ba9ae`
- replay: `codex exec resume 01a0bc82-43a0-7fe0-b292-5b97231ba9ae`
- log: `.project/logs/TICKET-140-implementing-4666cf3c.log`
- cost: unknown (the harness reported none)
- tokens: 10,558 out (2,426 thinking) · 2,137,401 in · 2,049,536 cache read · 0 cache write

### 2026-09-20 01:59:43Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added atomic summary filing and terminal ticket close.

### 2026-09-20 02:04:19Z · review · finding

1. **Blocking — active leases with a null holder bypass `--force`.** `live_holder()` returns the holder value at `pipeline/cli/main.py:481`. A future expiry with `holder: null` therefore returns `None`, so `cmd_resume` and `cmd_close` treat the lease as free and rewrite control fields. `validate_meta()` checks only the expiry at `pipeline/core/ticket.py:101-107`, so this state is reachable. `tests/test_daemon.py:261` refutes the intended shortcut by asserting `holder_alive(None) is True` for fail-safe handling.
2. **Blocking — four acceptance commands cannot select their required tests.** The implementation combines cases under different names at `tests/test_cli.py:911`, `:928`, and `:950`. Running the three terminal-state selectors exited 4: `ERROR: not found: ...::test_close_refuses_an_empty_reason`; the `done` and `already_rejected` selectors reported the same error. The five required lease, transition, and documentation selectors are also absent. Equivalent combined coverage does not make the specified acceptance commands exit 0.

### 2026-09-20 02:04:59Z · review · session · session=01a0bc8a-733b-7291-a3c7-ffeef34a9c7a

`review` ran as session `01a0bc8a-733b-7291-a3c7-ffeef34a9c7a`
- replay: `codex exec resume 01a0bc8a-733b-7291-a3c7-ffeef34a9c7a`
- log: `.project/logs/TICKET-140-review-20db54f6.log`
- cost: unknown (the harness reported none)
- tokens: 9,762 out (4,655 thinking) · 936,135 in · 878,976 cache read · 0 cache write

### 2026-09-20 02:04:59Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ Active null-holder leases bypass force, and required test selectors are missing.

### 2026-09-20 · implementing · note

Todo:

1. [in progress] Add exact acceptance-test selectors and a null-holder live-lease proof.
2. [pending] Make active leases fail safe when their holder is null.
3. [pending] Run focused and full regression tests, then commit the repair.

### 2026-09-20 · implementing · note

Completed the review repair.

1. Added exact acceptance-test selectors and a null-holder active-lease test.
2. Made `live_holder()` return `"None"` for an active null-holder lease, requiring `--force` in both resume and close paths.
3. `uv run --group dev pytest -q tests/test_cli.py tests/test_ticket.py` passed: `115 passed in 28.98s`.
4. `uv run --group dev pytest -q` passed: `654 passed in 72.10s`.

Committed `ce9c9cc` as `fix(TICKET-140): fail safe on null lease holders`.

### 2026-09-20 02:11:10Z · implementing · session · session=01a0bc8f-4362-7453-b258-fe1888a4e9ba

`implementing` ran as session `01a0bc8f-4362-7453-b258-fe1888a4e9ba`
- replay: `codex exec resume 01a0bc8f-4362-7453-b258-fe1888a4e9ba`
- log: `.project/logs/TICKET-140-implementing-a81a524e.log`
- cost: unknown (the harness reported none)
- tokens: 6,875 out (1,619 thinking) · 1,525,693 in · 1,455,872 cache read · 0 cache write

### 2026-09-20 02:11:10Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Closed the null-holder lease bypass and restored required test selectors.

### 2026-09-20 02:12:49Z · review · note

No blocking findings.

1. `live_holder()` now treats an active null-holder lease as live, so resume and close require `--force`.
2. All 14 relevant acceptance selectors passed, including the null-holder regression.
3. `.venv/bin/pytest -q tests/test_cli.py tests/test_ticket.py` passed: `115 passed in 28.99s`.
4. `git diff --check ce9c9cc^..ce9c9cc` passed.

### 2026-09-20 02:13:12Z · review · session · session=01a0bc94-ee80-7d73-b814-5f80710b33b5

`review` ran as session `01a0bc94-ee80-7d73-b814-5f80710b33b5`
- replay: `codex exec resume 01a0bc94-ee80-7d73-b814-5f80710b33b5`
- log: `.project/logs/TICKET-140-review-ac5cec01.log`
- cost: unknown (the harness reported none)
- tokens: 3,077 out (886 thinking) · 338,902 in · 311,552 cache read · 0 cache write

### 2026-09-20 02:13:12Z · review · transition · to=holistic-review · result=ok · marker=yes

**review -> holistic-review** (result: `ok`)

✓ The null-holder lease guard and exact acceptance selectors now pass review.

### 2026-09-20 · holistic-review · finding · severity=blocking

The accumulated README workflow is incoherent.

The `When a ticket escalates` table still maps "the ticket itself is wrong" to `pipeline reject TICKET-017 "why"`. `cmd_reject` refuses every stage except `awaiting-approval`, so that command cannot close the escalated ticket described by the section. The new paragraph below the table instead assigns abandoned non-terminal tickets to `pipeline close`.

Update the table's wrong-ticket row to use `pipeline close TICKET-017 --reason "why"`. This aligns the operator workflow with the new command and the documented reject/close distinction.

### 2026-09-20 02:14:30Z · holistic-review · session · session=01a0bc96-c886-7f21-9f55-dbcfd8bd7bcf

`holistic-review` ran as session `01a0bc96-c886-7f21-9f55-dbcfd8bd7bcf`
- replay: `codex exec resume 01a0bc96-c886-7f21-9f55-dbcfd8bd7bcf`
- log: `.project/logs/TICKET-140-holistic-review-ab4ca2d8.log`
- cost: unknown (the harness reported none)
- tokens: 2,494 out (950 thinking) · 372,717 in · 338,816 cache read · 0 cache write

### 2026-09-20 02:14:30Z · holistic-review · transition · to=escalated · result=fail · marker=yes

**holistic-review -> escalated** (result: `fail`)

✓ README still directs escalated tickets to the plan-only reject command instead of close.

### 2026-09-20 02:15:05Z · human · note · by=chezzijr

**resumed** by chezzijr -> `implementing`, reset [], granted `review_loops` 2 -> 1

### 2026-09-20 02:15:05Z · human · answer · by=chezzijr

**note from chezzijr**

Only the holistic-review finding is in scope: in README.md's 'When a ticket escalates' table, change the 'the ticket itself is wrong' row from pipeline reject to `pipeline close TICKET-017 --reason "why"`. Change nothing else, then return ok.

### 2026-09-20 · implementing · note

Todo:

1. Replace the wrong-ticket escalation command with `pipeline close`.
2. Verify the table names the close workflow and no reject command remains in that row.
3. Commit the README-only correction.

Completed:

1. Replaced `pipeline reject TICKET-017 "why"` with `pipeline close TICKET-017 --reason "why"`.
2. Verified the table row and adjacent reject/close distinction are consistent.
3. Committed `99faa35` (`fix(TICKET-140): correct escalation close command`).

`git diff --check` passed. No automated test applies to this README-only correction.

### 2026-09-20 02:16:39Z · implementing · session · session=01a0bc99-0db5-7090-98f1-bd8a574b5d13

`implementing` ran as session `01a0bc99-0db5-7090-98f1-bd8a574b5d13`
- replay: `codex exec resume 01a0bc99-0db5-7090-98f1-bd8a574b5d13`
- log: `.project/logs/TICKET-140-implementing-587bfa12.log`
- cost: unknown (the harness reported none)
- tokens: 1,765 out (249 thinking) · 301,512 in · 275,968 cache read · 0 cache write

### 2026-09-20 02:16:39Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Corrected the README escalation table to use pipeline close with a reason.

### 2026-09-20 · review · note

No blocking findings.

The delta changes only `README.md:554`. It replaces the invalid plan-rejection command with `pipeline close TICKET-017 --reason "why"`.

The invocation matches the `close` parser at `pipeline/cli/main.py:960`. `git diff --check ce9c9cc..HEAD` passed.

### 2026-09-20 02:17:34Z · review · session · session=01a0bc99-f312-73f2-b496-7e8a1168ddc2

`review` ran as session `01a0bc99-f312-73f2-b496-7e8a1168ddc2`
- replay: `codex exec resume 01a0bc99-f312-73f2-b496-7e8a1168ddc2`
- log: `.project/logs/TICKET-140-review-36a081da.log`
- cost: unknown (the harness reported none)
- tokens: 1,567 out (681 thinking) · 178,154 in · 157,440 cache read · 0 cache write

### 2026-09-20 02:17:34Z · review · transition · to=holistic-review · result=ok · marker=yes

**review -> holistic-review** (result: `ok`)

✓ README escalation guidance now uses the supported close command and reason syntax.

### 2026-09-20 · holistic-review · note

No coherence findings.

The accumulated change matches the approved plan. `pipeline new` reads complete path or stdin summaries before atomic publication. `pipeline close` uses the shared live-holder rule, refuses both terminal stages, releases leases, records an attributed `close` entry, and emits the saved transition.

The ticket model retains `close` entries without treating them as plan rejections. The README and file-ticket skill describe the same atomic filing and terminal cancellation workflows. Commit `99faa35` resolves the prior holistic finding by mapping the escalation table's wrong-ticket case to `pipeline close TICKET-017 --reason "why"`.

`git diff --check f9d1063..HEAD` passed. The focused test command could not start because this read-only stage could not create uv's cache lock: `Read-only file system (os error 30)`.

### 2026-09-20 02:19:28Z · holistic-review · session · session=01a0bc9a-c7a9-7222-a108-773fe37856b9

`holistic-review` ran as session `01a0bc9a-c7a9-7222-a108-773fe37856b9`
- replay: `codex exec resume 01a0bc9a-c7a9-7222-a108-773fe37856b9`
- log: `.project/logs/TICKET-140-holistic-review-6cd59cd4.log`
- cost: unknown (the harness reported none)
- tokens: 3,547 out (724 thinking) · 607,579 in · 571,008 cache read · 0 cache write

### 2026-09-20 02:19:28Z · holistic-review · transition · to=verifying · result=ok · marker=yes

**holistic-review -> verifying** (result: `ok`)

✓ The accumulated changes implement atomic summaries and coherent terminal close behavior.

### 2026-09-20 02:20:42Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-20 02:20:44Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/140


Current branch ticket/140 is up to date.
Already up to date.
Updating f9d1063..99faa35
Fast-forward
 README.md                                      |  15 ++-
 pipeline/cli/main.py                           |  58 ++++++++-
 pipeline/core/ticket.py                        |   4 +-
 pipeline/templates/skills/file-ticket/SKILL.md |  20 ++-
 tests/test_cli.py                              | 167 +++++++++++++++++++++++++
 tests/test_ticket.py                           |   3 +-
 6 files changed, 252 insertions(+), 15 deletions(-)

```

### 2026-09-20 02:20:44Z · merging · decision

decision recorded as `DEC-140`
