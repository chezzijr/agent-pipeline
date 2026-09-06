---
id: TICKET-114
stage: done
class: bugfix
branch: ticket/114
test_file: tests/test_cli.py::test_init_registers_the_project_for_the_daemon
files_declared:
- .project/known-issues.md
- README.md
- pipeline/cli/main.py
- pipeline/templates/skills/file-ticket/SKILL.md
- tests/test_cli.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 4
  plan_files: 5
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 94ad2b4e-0472-4f0e-80d2-9076ed2053c5
  replay: claude --resume 94ad2b4e-0472-4f0e-80d2-9076ed2053c5
  log: .project/logs/TICKET-114-review-94ad2b4e.log
  cost_usd: 1.6264419999999997
approved_by: chezzijr
approved_at: '2026-09-05T17:42:30.178456+00:00'
---

## Summary

Plan `pipeline init` to register its resolved project by default and print that
state. Add `--no-register` for CI and other scaffold-only callers.

Plan `pipeline new` to warn when the resolved project is absent from the global
registry. It must still create the ticket without enlisting the project.

Keep `ls`, `status`, `logs`, and `metrics` read-only. Update the CLI tests,
README, installed file-ticket template, and known-issues record.

Plan validation passed. The plan fixes the missing registry write, preserves
all cited registry constraints, and supplies meaningful side-effect tests.
`--no-register` and commit reversion cover the riskiest state mutation.

Implemented. `cmd_init()` calls `registry.register()` after scaffolding and
prints `registered <path>`; `--no-register` prints `skipped registration
(--no-register)` instead and never removes existing state; a `PipelineError`
from `register()` (worktree, `PIPELINE_STAGE`) prints as a warning, not
`die()`. `cmd_new()` prints a warning naming `pipeline start`, `pipeline
register <path>`, and the project-local `pipeline run` when the project is
absent from the registry, and still creates the ticket. `ls`, `status`,
`logs`, `metrics` are unchanged. Four tests added to `tests/test_cli.py`;
the reproduction test now also asserts the `registered <path>` message.
README, the file-ticket `SKILL.md`, and known-issues item 2 updated.
`uv run --group dev pytest -q` (565 passed) and
`./pipeline/hooks/test_dangerous_commands.py` both pass.

Review passed on the first pass, with no blocking finding. The reviewer
re-ran both suites (`565 passed`, `guard: all passed`) and checked every
acceptance criterion, including `init --help`, the doc `rg`, and
`git diff --check`. Three non-blocking findings are recorded in the thread:
`new` warns inside a linked worktree and recommends a `register` the
registry refuses; the read-only test asserts no return codes, so its
`status` leg proves little; the `not registered:` line is indented and the
`--no-register` line is not.

## Reproduction

path: `tests/test_cli.py::test_init_registers_the_project_for_the_daemon`
command: `uv run --group dev pytest -q tests/test_cli.py -k init_registers_the_project_for_the_daemon`
expect: pipeline init left

```text
E               AssertionError: pipeline init left /tmp/tmpfzna268g unregistered:
E                 
E               assert '/tmp/tmpfzna268g' in ''
```

## Digest

- `pipeline/cli/main.py`: `cmd_init()` scaffolds config and skills; `cmd_new()` writes the ticket; `main()` owns both argument parsers.
- `pipeline/daemon/registry.py`: `registry.register()` validates and atomically adds state; `registry.projects()` is the filtered, read-only membership view.
- `pipeline/cli/main.py`: `cmd_register()` alone runs `suite_failure()` and `selector_failure()` before calling the registry library.
- `tests/test_cli.py`: committed proof `18dbaff` adds `test_init_registers_the_project_for_the_daemon`; subprocess tests isolate registry state with `XDG_CONFIG_HOME`.
- `README.md` documents setup and daemon use; `pipeline/templates/skills/file-ticket/SKILL.md` is the canonical installed filing workflow.
- Gotcha: `--no-register` skips adding state but must not unregister a project already present. `new`, `ls`, `status`, `logs`, and `metrics` must never register implicitly.

## Decisions checked

- DEC-011: the registry is durable text state, re-read by the daemon and rewritten atomically through `registry.register()`.
- DEC-056: `pipeline/templates/skills/file-ticket/SKILL.md` is the canonical skill; edit it instead of installed or symlinked copies.
- DEC-068: test-command probes belong only to `cmd_register()`; library callers use `registry.register()` without spawning project commands.
- DEC-072: `registry.register()` must retain linked-worktree and `PIPELINE_STAGE` refusals.
- Grep terms: `init`, `register`, `registry`, `daemon`, `discover`, `ticket creation`, `read-only`, `side effect`.

## Plan

1. Extend `tests/test_cli.py` with `test_init_no_register_skips_daemon_registration`, `test_new_warns_when_project_is_not_registered`, and `test_read_only_commands_do_not_register_a_project`; isolate each registry through `XDG_CONFIG_HOME`, retain the committed default-registration proof, assert `--no-register` appears in init help, assert a registered project gets no warning, and run the focused cases to observe failures before production edits.
2. Modify `pipeline/cli/main.py` so the init parser accepts `--no-register`; after scaffolding, `cmd_init()` calls `registry.register(project)` and prints `registered <path>` unless opted out, while the opt-out prints `skipped registration (--no-register)` and never removes existing state; after `cmd_new()` prints the ticket path, check `project not in registry.projects()` and print a warning that `pipeline start` cannot discover it plus `pipeline register <path>` and project-local `pipeline run` remedies; leave `cmd_ls()`, `cmd_daemon_status()`, `cmd_logs()`, and `cmd_metrics()` unchanged, then run the focused `tests/test_cli.py` cases and commit the CLI with its tests.
3. Update `README.md` to state that `pipeline init` registers by default, show `--no-register` for CI, distinguish automatic no-probe setup from explicit validated `pipeline register`, and document the unregistered `pipeline new` warning; update `pipeline/templates/skills/file-ticket/SKILL.md` so filing guidance expects init registration, explains the warning, and retains explicit registration as remediation; mark issue 2 fixed by TICKET-114 in `.project/known-issues.md`, then commit these documentation changes.
4. Validate `pipeline/cli/main.py`, `tests/test_cli.py`, `README.md`, `pipeline/templates/skills/file-ticket/SKILL.md`, and `.project/known-issues.md` with the focused CLI tests, the full pytest suite, and the direct dangerous-command guard suite; inspect `git diff --check` and commit any test or documentation correction with its owning change.

## Acceptance criteria

- `tests/test_cli.py::test_init_registers_the_project_for_the_daemon` passes and asserts both the registration message and `pipeline projects` membership.
- `tests/test_cli.py::test_init_no_register_skips_daemon_registration` passes for a fresh registry and proves re-running with the flag does not remove existing membership.
- `tests/test_cli.py::test_new_warns_when_project_is_not_registered` passes, naming both daemon discovery and a recovery command, while a registered project emits no warning.
- `tests/test_cli.py::test_read_only_commands_do_not_register_a_project` passes after invoking `ls`, `status`, `logs`, and `metrics` against isolated registry state.
- `uv run python -m pipeline init --help` exits `0` and prints `--no-register` with its scaffold-only purpose.
- `uv run --group dev pytest -q tests/test_cli.py -k 'init or new or read_only'` exits `0`.
- `uv run --group dev pytest -q` exits `0` with no failures or errors.
- `./pipeline/hooks/test_dangerous_commands.py` exits `0` with every guard case reporting `ok`.
- `rg -n -- '--no-register|not registered' README.md pipeline/templates/skills/file-ticket/SKILL.md .project/known-issues.md` exits `0` and finds the setup opt-out plus filing warning guidance.

## Decisions

`pipeline init` registers the resolved main project by default through `registry.register()` and prints the result. It does not run test-command probes because setup writes an unedited template; explicit `pipeline register` remains the validated path. `--no-register` suppresses only the new write and never unregisters existing state.

`pipeline new` reports absent registry membership but never changes it. The warning preserves ticket creation and names both explicit registration and project-local `pipeline run`. Read-only CLI commands never enlist a project into a background process.

## Rollback

Revert the TICKET-114 commits touching `pipeline/cli/main.py`, `tests/test_cli.py`, `README.md`, `pipeline/templates/skills/file-ticket/SKILL.md`, and `.project/known-issues.md`. Reverting stops future automatic registration and warnings but does not remove registry lines already written. Run `pipeline unregister <path>` only for projects whose operators request removal.

## Thread

### 2026-09-05 16:20:32Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-05 16:34:00Z · triage · finding

Reproduced: `pipeline init` leaves the new project absent from the registry.

`tests/test_cli.py::test_init_registers_the_project_for_the_daemon` initializes
a temporary project, then runs `pipeline projects` with the same XDG config.
It fails because output is empty. The failure is `pipeline init left …
unregistered:`.

Root cause: `pipeline/cli/main.py:42` creates the project directories and
configuration but does not call `registry.register()`. The working registration
path is `pipeline/cli/main.py:471`, where `cmd_register()` validates commands
before calling `registry.register(path)`.

Committed failing proof: `18dbaff` (`test(TICKET-114): reproduce unregistered
project setup`). Expected fix scope begins with `pipeline/cli/main.py` and
`tests/test_cli.py`; broader warning and TUI behavior need planning.

### 2026-09-05 16:23:08Z · triage · session · session=01a0725f-503a-7203-952e-7c2386342605

`triage` ran as session `01a0725f-503a-7203-952e-7c2386342605`
- replay: `codex exec resume 01a0725f-503a-7203-952e-7c2386342605`
- log: `.project/logs/TICKET-114-triage-269009f0.log`

### 2026-09-05 16:23:08Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced setup leaving a project unregistered; committed failing CLI regression test.

### 2026-09-05 16:26:24Z · planning · finding

Planned default registration in `cmd_init()` with a non-destructive
`--no-register` escape hatch. Automatic setup uses `registry.register()` and
does not run the explicit `cmd_register()` test-command probes.

Planned an unregistered-project warning in `cmd_new()`. The command still
creates the ticket and never changes registry state. Tests pin the purity of
`ls`, `status`, `logs`, and `metrics`.

Declared five files: `pipeline/cli/main.py`, `tests/test_cli.py`, `README.md`,
`pipeline/templates/skills/file-ticket/SKILL.md`, and
`.project/known-issues.md`.

### 2026-09-05 16:27:36Z · planning · session · session=01a07261-8a51-7552-9a9b-4f7e278f3fee

`planning` ran as session `01a07261-8a51-7552-9a9b-4f7e278f3fee`
- replay: `codex exec resume 01a07261-8a51-7552-9a9b-4f7e278f3fee`
- log: `.project/logs/TICKET-114-planning-aab2121a.log`

### 2026-09-05 16:27:36Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned explicit init registration, CI opt-out, unregistered-ticket warnings, purity checks, and matching documentation.

### 2026-09-05 16:29:27Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_init_registers_the_project_for_the_daemon` fails as required
```
       try:
            made = cli(d, "init", env={"XDG_CONFIG_HOME": str(config)})
            assert made.returncode == 0, made.stdout + made.stderr
            watched = cli(d, "projects", env={"XDG_CONFIG_HOME": str(config)})
>           assert str(d) in watched.stdout, (
                f"pipeline init left {d} unregistered:\n{watched.stdout}{watched.stderr}")
E               AssertionError: pipeline init left /tmp/tmpai7p89nl unregistered:
E                 
E               assert '/tmp/tmpai7p89nl' in ''
E                +  where '/tmp/tmpai7p89nl' = str(PosixPath('/tmp/tmpai7p89nl'))
E                +  and   '' = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-114/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpai7p89nl', 'projects'], returncode=0, stdout='', stderr='').stdout

tests/test_cli.py:578: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_registers_the_project_for_the_daemon - As...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.37s ===============================

```
- ok: `tests/test_cli.py::test_init_registers_the_project_for_the_daemon` fails on base `main` too -- the bug is not already fixed upstream
```
               +  where '/tmp/tmpi6c8cjn2' = str(PosixPath('/tmp/tmpi6c8cjn2'))
E                +  and   '' = CompletedProcess(args=['/tmp/pipeline-base-i1x4zf2t/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpi6c8cjn2', 'projects'], returncode=0, stdout='', stderr='').stdout

tests/test_cli.py:578: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_registers_the_project_for_the_daemon - As...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.70s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-i1x4zf2t/base
      Built pipeline @ file:///tmp/pipeline-base-i1x4zf2t/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 34ms

```

### 2026-09-05 16:31:31Z · plan-validation · finding

- Root cause vs symptom — PASS: `cmd_init()` scaffolds files but never calls
  `registry.register()`. The plan adds that missing state transition.
- Decision conflict — PASS: direct library registration preserves DEC-011 and
  DEC-072. Skipping probes follows DEC-068, and template edits follow DEC-056.
- Scope discipline — PASS: every change supports registration, warnings,
  purity proof, or required operator guidance.
- Falsifiable criteria — PASS: membership, output, non-removal, warning
  suppression, and registry purity distinguish correct from wrong behavior.
- No research left — PASS: all implementation steps name concrete files,
  functions, tests, and commands.
- Riskiest step — PASS: `init` mutates durable operator state. `--no-register`
  is the operational fallback, and the rollback reverts the owning commits.
- Regression surface — PASS: init path resolution, skill installation,
  private setup, registry refusals, ticket creation, and four read-only commands
  could break. Focused CLI tests and the full suite cover them.
- Blast radius matches class — PASS: five files contain one CLI bugfix, its
  tests, and required documentation. The scope fits `bugfix`.

### 2026-09-05 16:32:08Z · plan-validation · session · session=01a07267-54e1-7401-820b-e01babbb6e4d

`plan-validation` ran as session `01a07267-54e1-7401-820b-e01babbb6e4d`
- replay: `codex exec resume 01a07267-54e1-7401-820b-e01babbb6e4d`
- log: `.project/logs/TICKET-114-plan-validation-c447c0d3.log`

### 2026-09-05 16:32:08Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan fixes missing init registration, preserves registry constraints, and covers side effects with meaningful regression tests.

### 2026-09-05 17:42:30Z · human · note · by=chezzijr

**note from chezzijr**

Plan gap found at the approval gate: step 2 has cmd_init() call registry.register(project) unconditionally, but registry.check() (pipeline/daemon/registry.py) raises PipelineError in two cases the plan does not mention -- the project is a git worktree, and PIPELINE_STAGE is set. The CLI turns PipelineError into die(), so `pipeline init` in a worktree would scaffold everything, print its success lines, and only then abort on 'is a git worktree, not a project'. Today it simply succeeds. Catch PipelineError around the register() call and print the reason as a warning (the same shape as the --no-register line) instead of dying: the scaffold is already complete and correct at that point, and failing to enlist the project is not a reason to fail the init. Keep the default-registration test as planned, and add one case for the worktree refusal.

### 2026-09-05 17:42:30Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-05 17:50:03Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_init_registers_the_project_for_the_daemon` fails as required
```
       try:
            made = cli(d, "init", env={"XDG_CONFIG_HOME": str(config)})
            assert made.returncode == 0, made.stdout + made.stderr
            watched = cli(d, "projects", env={"XDG_CONFIG_HOME": str(config)})
>           assert str(d) in watched.stdout, (
                f"pipeline init left {d} unregistered:\n{watched.stdout}{watched.stderr}")
E               AssertionError: pipeline init left /tmp/tmp1ve6lipf unregistered:
E                 
E               assert '/tmp/tmp1ve6lipf' in ''
E                +  where '/tmp/tmp1ve6lipf' = str(PosixPath('/tmp/tmp1ve6lipf'))
E                +  and   '' = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-114/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmp1ve6lipf', 'projects'], returncode=0, stdout='', stderr='').stdout

tests/test_cli.py:578: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_registers_the_project_for_the_daemon - As...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.64s ===============================

```
- ok: `tests/test_cli.py::test_init_registers_the_project_for_the_daemon` fails on base `main` too -- the bug is not already fixed upstream
```
               +  where '/tmp/tmpskmnrmtg' = str(PosixPath('/tmp/tmpskmnrmtg'))
E                +  and   '' = CompletedProcess(args=['/tmp/pipeline-base-vofvhk6n/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpskmnrmtg', 'projects'], returncode=0, stdout='', stderr='').stdout

tests/test_cli.py:578: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_registers_the_project_for_the_daemon - As...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.67s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-vofvhk6n/base
      Built pipeline @ file:///tmp/pipeline-base-vofvhk6n/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 19ms

```

### 2026-09-05 17:50:03Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-06 · implementing · todo

1. [x] Extend `tests/test_cli.py`: `test_init_no_register_skips_daemon_registration`, `test_new_warns_when_project_is_not_registered`, `test_read_only_commands_do_not_register_a_project`, plus `test_init_in_a_worktree_warns_instead_of_dying` for the human's worktree gap; update `test_init_registers_the_project_for_the_daemon` to assert the `registered <path>` message.
2. [x] `pipeline/cli/main.py`: `--no-register` on the init parser; `cmd_init()` calls `registry.register()`, catches `PipelineError` as a warning; `cmd_new()` warns when the project is absent from `registry.projects()`; commit.
3. [x] Update `README.md`, `pipeline/templates/skills/file-ticket/SKILL.md`, `.project/known-issues.md`; commit.
4. [x] Full suite, guard suite, `git diff --check`.

### 2026-09-06 · implementing · report

`cmd_init()` (`pipeline/cli/main.py`) now calls `registry.register(project)`
right after the `initialised ...` line and prints `registered <path>`.
`--no-register` prints `skipped registration (--no-register)` instead and
never calls `register()`. A `PipelineError` from `register()` -- the
worktree or `PIPELINE_STAGE` refusal `registry.check()` raises -- prints as
`  not registered: <reason>` rather than reaching `die()`, per the human's
2026-09-05 17:42:30Z gap report; the scaffold above it has already
succeeded and completed correctly.

`cmd_new()` prints a warning naming `pipeline start`, `pipeline register
<path>`, and the project-local `pipeline run` when `project not in
registry.projects()`, after writing the ticket. `cmd_ls()`,
`cmd_daemon_status()`, `cmd_logs()`, `cmd_metrics()` are untouched.

Four tests added to `tests/test_cli.py`, TDD'd one at a time (RED then
GREEN); the worktree test first passed vacuously because the fixture path
itself contained the literal substring "worktree" -- renamed the fixture
directory and tightened the assertion to the exact refusal text before
re-verifying RED. `test_init_registers_the_project_for_the_daemon` now
also asserts `f"registered {d}"` in stdout.

`README.md`, `pipeline/templates/skills/file-ticket/SKILL.md` (the
canonical DEC-056 template, not an installed copy), and
`.project/known-issues.md` item 2 updated to match.

Verified:
- `uv run --group dev pytest -q tests/test_cli.py -k 'init or new or read_only'` — 13 passed.
- `uv run --group dev pytest -q` — 565 passed.
- `./pipeline/hooks/test_dangerous_commands.py` — all `ok`.
- `uv run python -m pipeline init --help` exits 0 and prints `--no-register`.
- `rg -n -- '--no-register|not registered' README.md pipeline/templates/skills/file-ticket/SKILL.md .project/known-issues.md` — 6 hits, exit 0.
- `git diff --check` — clean.

Three commits on `ticket/114`: `66ad49f` (CLI + tests), `ce3ccff` (docs),
on top of the existing `a4e2804` reproduction commit.

### 2026-09-05 17:58:07Z · implementing · session · session=906a74fa-dcee-4805-8cff-0727645b6e9d

`implementing` ran as session `906a74fa-dcee-4805-8cff-0727645b6e9d`
- replay: `claude --resume 906a74fa-dcee-4805-8cff-0727645b6e9d`
- log: `.project/logs/TICKET-114-implementing-906a74fa.log`
- cost: $1.81 of a $8 cap
- tokens: 27,477 out (9,461 thinking) · 148 in · 5,718,079 cache read · 96,837 cache write

### 2026-09-05 17:58:07Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ init registers by default (with --no-register and a worktree/PIPELINE_STAGE warning), new warns when unregistered, docs updated, full suite and guard pass.

### 2026-09-06 · review · report

**PASS.** Reviewed the delta `main...HEAD` (`a4e2804`, `66ad49f`, `ce3ccff`):
`pipeline/cli/main.py`, `tests/test_cli.py`, `README.md`,
`pipeline/templates/skills/file-ticket/SKILL.md`, `.project/known-issues.md`.
No blocking finding.

Verified here: `uv run --group dev pytest -q` — `565 passed in 52.68s`;
`./pipeline/hooks/test_dangerous_commands.py` — `guard: all passed`;
`pytest -q tests/test_cli.py -k 'init or new or read_only'` — `13 passed`;
`uv run python -m pipeline init --help` prints `--no-register`;
`rg -n -- '--no-register|not registered'` over the three doc files — 6 hits,
exit 0; `git diff --check` — exit 0. Every acceptance criterion holds.
`cmd_ls()`, `cmd_daemon_status()`, `cmd_logs()`, `cmd_metrics()` are outside
the diff. No `FENCED` path is touched. `.agents/skills/file-ticket/SKILL.md`
is a tracked symlink to the edited template (`diff` exit 0), so DEC-056 holds.

Refuted before writing: I expected `PIPELINE_STAGE`, set in a stage's
environment, to make `registry.register()` refuse inside the new tests.
`tests/conftest.py:26` pops it, and the focused run passed here under
`PIPELINE_STAGE=review`.

Non-blocking findings:

1. minor — `pipeline new` inside a linked worktree of a registered project
   always warns, because `projects()` skips worktrees
   (`pipeline/daemon/registry.py:59`), and the warning's
   `pipeline register <path>` then refuses (`registry.py:97`). The ticket is
   still filed and the refusal names the main checkout.
2. minor — `test_read_only_commands_do_not_register_a_project` asserts no
   return codes; `cmd_daemon_status()` exits 1 with no daemon
   (`pipeline/cli/main.py:541`), so its `status` leg proves little. The `ls`,
   `logs`, `metrics` legs still bind.
3. nit — `  not registered: <reason>` is indented; `skipped registration
   (--no-register)` is not.

### 2026-09-06 02:04:56Z · review · session · session=94ad2b4e-0472-4f0e-80d2-9076ed2053c5

`review` ran as session `94ad2b4e-0472-4f0e-80d2-9076ed2053c5`
- replay: `claude --resume 94ad2b4e-0472-4f0e-80d2-9076ed2053c5`
- log: `.project/logs/TICKET-114-review-94ad2b4e.log`
- cost: $1.63 of a $5 cap
- tokens: 16,617 out (8,900 thinking) · 52 in · 1,213,356 cache read · 60,304 cache write

### 2026-09-06 02:04:56Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review passed: init registers by default with --no-register and a caught PipelineError, new warns without registering, read-only commands unchanged; 565 tests and the guard suite pass. Three non-blocking findings appended.

### 2026-09-06 02:05:50Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-06 02:05:51Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/114


Rebasing (1/3)Rebasing (2/3)Rebasing (3/3)Successfully rebased and updated refs/heads/ticket/114.
Already up to date.
Updating c4ef358..06c90c5
Fast-forward
 .project/known-issues.md                       |   2 +-
 README.md                                      |  20 ++++-
 pipeline/cli/main.py                           |  25 +++++-
 pipeline/templates/skills/file-ticket/SKILL.md |   9 +-
 tests/test_cli.py                              | 120 ++++++++++++++++++++++++-
 5 files changed, 170 insertions(+), 6 deletions(-)

```

### 2026-09-06 02:05:51Z · merging · decision

decision recorded as `DEC-114`
