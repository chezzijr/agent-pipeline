---
id: TICKET-050
stage: done
class: feature
branch: ticket/050
test_file: tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria
files_declared:
- README.md
- pipeline/cli/main.py
- tests/test_cli.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
  plan_steps: 8
  plan_files: 3
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 2aaf5a93-05f1-4712-b1c9-a0471740caf6
  log: .project/logs/TICKET-050-review-2aaf5a93.log
approved_by: chezzijr
approved_at: '2026-08-24T09:58:42.389445+00:00'
---

## Summary

`pipeline plan <id>` prints `## Plan` and `## Acceptance criteria` and nothing
else, exit 0. Read-only, no approve/reject flag (see `## Decisions`).

`implementing` re-landed `cmd_plan()` at commit d3f2d7e. `review` passed the
delta with no blocking findings.

Every acceptance criterion holds. `uv run --group dev pytest -q` reports
`269 passed in 11.20s`, including
`test_plan_prints_only_the_plan_and_acceptance_criteria` and
`test_plan_errors_on_an_unknown_ticket`. `git diff main...HEAD --stat` lists
`pipeline/cli/main.py` (+9), `tests/test_cli.py` (+32) and `README.md` (+1) only,
matching `## Rollback`. `README.md:68` documents the command. Criterion 4 names
252 passed; the real count is 269 because `revalidating` rebased onto a base
carrying 16 more tests.

`review` did not run `./pipeline/hooks/test_dangerous_commands.py` -- the guard
denies it to a read-only stage. `implementing` ran it and it passed; the delta
touches no file under `pipeline/hooks/`.

Next: `verifying` / `awaiting-merge`.

## Reproduction

Test: `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria`
Command: `uv run --group dev pytest -q tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria`
Also reproduced directly: `uv run --group dev pipeline plan TICKET-050` exits 2 with:
`pipeline: error: argument cmd: invalid choice: 'plan' (choose from init, new, gate, approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)`
expect: invalid choice: 'plan'

## Digest

Files touched: `pipeline/cli/main.py` (the `pipeline` command), `tests/test_cli.py`
(the CLI suite, subprocess-based), `README.md` (the `## Use` command block, lines 57-71).

Key functions: `cmd_gate(args)` at `pipeline/cli/main.py:78` is the pattern to
copy -- `proj(args)` at `pipeline/cli/main.py:26` resolves the project,
`Ticket.find(project, args.id)` at `pipeline/core/ticket.py:535` loads it, and
`Ticket.section(name)` at `pipeline/core/ticket.py:568` returns one section's
body, `""` when it is missing.

Entry point: `main()` in `pipeline/cli/main.py` builds one subparser per line at
`pipeline/cli/main.py:461-466`; the `gate` line is the template. `args.fn(args)`
is called at `pipeline/cli/main.py:495` inside a `try` that turns `PipelineError`
into `die()`.

Gotcha 1: a bad id needs no handling in `cmd_plan`. `Ticket.load` wraps the
`FileNotFoundError` in `PipelineError` (`pipeline/core/ticket.py:520`) and
`main()` turns it into `error: <path>: [Errno 2] No such file or directory`,
exit 1. Verified by running `pipeline gate TICKET-999` in a scratch project.

Gotcha 2: the branch must stay red until `plan-validation` runs. `gate()` in
`pipeline/core/gate.py` runs `test_one` in the ticket worktree and records
"PASSES -- it must fail before implementation" as a failure. That is why ad4116e
exists; do not re-land `cmd_plan` before the approval gate.

Gotcha 3: `Ticket.section()` returns the body without its heading, so `cmd_plan`
prints the heading itself. Two headless section bodies printed back to back are
indistinguishable to the operator this command is for.

Verified RED after ad4116e:

    >       assert r.returncode == 0, r.stderr
    E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
    E         __main__.py: error: argument cmd: invalid choice: 'plan' (choose from init, new, gate, ...)
    E       assert 2 == 0
    FAILED tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria

and `uv run --group dev pytest --deselect tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria -q` reports `250 passed, 1 deselected`.

`.claude/skills/file-ticket/SKILL.md` is deliberately not touched. It tells a
filing session what to write and what not to run; `pipeline plan` is an
operator's read command at the approval gate, and nothing the skill states
becomes wrong. `README.md` is where the operator command block lives.

## Decisions checked

- DEC-017 -- the Tier A reproduction is a two-run fact: the test must fail in
  the worktree and again on base. This plan complies. ad4116e makes the branch
  red, and the branch's test file copied onto `main` fails there too, because
  `main` has no `plan` subparser either.
- DEC-016 -- `sections()` consults `_fenced()`; every heading scan over a
  ticket body must. `cmd_plan` reads through `Ticket.section()`, so it inherits
  that scan and adds no fourth one.
- DEC-020 -- `line_buffer_stdout()` is called inside `main()`, never by a
  spawner. `cmd_plan` prints to stdout and needs no buffering of its own.
- DEC-026 -- on the cheap route `implementing` writes `files_declared` itself,
  which is why `quick-review` checks the diff against the files `## Summary`
  names. This ticket left that route; `planning` owns `files_declared` now.
- DEC-033 -- names `quick-review` returning `fail` as the tripwire on Sonnet
  triage over-calling `chore`. This ticket is the first such run; that note is
  in `## Thread`, not a constraint on this plan.
- Grep terms used against `.project/decisions/`: `cli/main.py`, `argparse`,
  `add_parser`, `Ticket.find`, `.section(`, `sections()`, `superseded-by`.
  No record carries a `superseded-by:` line.

## Plan

1. Re-add `cmd_plan(args)` to `pipeline/cli/main.py` directly below `cmd_gate` (line 88): `def cmd_plan(args) -> None:` then `t = Ticket.find(proj(args), args.id)`, then `print("## Plan\n")`, `print(t.section("Plan"))`, `print("\n## Acceptance criteria\n")`, `print(t.section("Acceptance criteria"))`. Add no try/except -- `main()` already turns `PipelineError` into `die()`.
2. Register the subcommand in `pipeline/cli/main.py` on a new line directly after the `gate` line at line 463: `p = sub.add_parser("plan"); p.add_argument("id"); p.set_defaults(fn=cmd_plan)`.
3. Extend `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` (line 229) with two assertions placed after `assert "widget moved." in r.stdout`: `assert "## Plan" in r.stdout` and `assert "## Acceptance criteria" in r.stdout`. Leave the four existing assertions and the ticket-body seeding untouched.
4. Add `test_plan_errors_on_an_unknown_ticket()` at the end of `tests/test_cli.py`: it makes a temp project with `d = Path(tempfile.mkdtemp())`, runs `cli(d, "new", "t")`, then `r = cli(d, "plan", "TICKET-999")`, and asserts `r.returncode == 1`, `"TICKET-999.md" in r.stderr`, `"Traceback" not in r.stderr`, then calls `shutil.rmtree(d)`.
5. Run `uv run --group dev pytest -q tests/test_cli.py` from the worktree root; expect both tests in `tests/test_cli.py` green and no other failure in that file.
6. Document the command in `README.md` in the `## Use` block, on a new line directly after the `pipeline --project ~/code/myproject ls` line (line 67): `pipeline --project ~/code/myproject plan TICKET-001    # the plan and its acceptance criteria, nothing else`.
7. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py` from the worktree root; expect 252 passed from `tests/test_cli.py` and the rest of the suite, and every guard case passing.
8. Commit the changes from steps 1-7 as one commit in the worktree, message `feat: pipeline plan prints a ticket's plan and acceptance criteria (TICKET-050)`, touching only `pipeline/cli/main.py`, `tests/test_cli.py` and `README.md`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` passes, and its assertions cover both printed headings.
- `uv run --group dev pytest -q tests/test_cli.py::test_plan_errors_on_an_unknown_ticket` passes: `pipeline plan TICKET-999` exits 1, names the missing path, prints no traceback.
- `git diff main...HEAD --stat` lists exactly `pipeline/cli/main.py`, `tests/test_cli.py` and `README.md`, and the `pipeline/cli/main.py` half adds only `cmd_plan` and one `sub.add_parser("plan")` line.
- `uv run --group dev pytest -q` reports 252 passed: the 250 that pass after ad4116e, plus `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` and `tests/test_cli.py::test_plan_errors_on_an_unknown_ticket`.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.
- `grep -n "plan TICKET-001" README.md` prints the line from step 6. No pytest test asserts README prose; that grep is this criterion's whole check.

## Decisions

`pipeline plan <id>` is read-only. It prints `## Plan` and `## Acceptance
criteria` and exits. It has no approve/reject flag. Approving from inside a
plan viewer would let an operator land a decision without scrolling past it.
The gate stays `pipeline approve` / `pipeline reject`.

**A ticket promoted from `quick-review` to `planning` arrives with its fix
already committed, and Tier A rejects it in that state.** `gate()` runs
`test_one` in the ticket worktree and fails the ticket with "PASSES -- it must
fail before implementation". `plan-validation` runs immediately after
`planning`, so no plan step can fix this: `implementing` runs later. `planning`
therefore reverts the implementation half of the cheap route's commit itself --
here `git revert --no-commit eea468d`, then `git checkout HEAD -- tests/test_cli.py`,
committed as ad4116e -- and leaves the test in place. Keep the *rewritten* test,
not triage's original: triage's asserted `invalid choice: 'plan'`, the absence of
the feature, so it would pass again the moment the feature returned. If a future
change stops `planning` from writing to the branch, this promotion path needs a
dispatcher-side revert instead, or it escalates every time.

`cmd_plan` prints each heading itself. `Ticket.section()` returns a body with
the heading stripped, so printing the two bodies alone gives an operator two
runs of prose with no boundary between them. The test asserts both headings are
present and that `## Summary` and `## Reproduction` are not.

## Rollback

Revert the single commit from step 8. That removes `cmd_plan`, its
`sub.add_parser("plan")` line, both test changes and the `README.md` line
together. Nothing else imports `cmd_plan`, and no stage, hook or harness
invokes `pipeline plan`, so no caller breaks. The branch is then back at
ad4116e, which is red only at
`tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria`.

## Thread

### 2026-08-24 08:05:50Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 · triage · note

Reproduced: `pipeline` has no `plan` subcommand. `pipeline plan TICKET-001`
exits 2 with `invalid choice: 'plan'`, matching the ticket's expected failure.
Committed a failing test at c3f812c:
`tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria`.

Fix is a chore: one `sub.add_parser("plan")` line plus one `cmd_plan(args)`
function in `pipeline/cli/main.py`, using `Ticket.find` + `.section("Plan")`
and `.section("Acceptance criteria")`, the same building blocks `cmd_gate`
already uses. No other file needs to change.

### 2026-08-24 08:55:49Z · triage · session · session=d1d98022-664b-4a74-a699-aedaf3183d30

`triage` ran as session `d1d98022-664b-4a74-a699-aedaf3183d30`
- replay: `claude --resume d1d98022-664b-4a74-a699-aedaf3183d30`
- log: `.project/logs/TICKET-050-triage-d1d98022.log`

### 2026-08-24 08:55:49Z · triage · transition · to=implementing · result=chore · marker=yes

**triage -> implementing** (result: `chore`)

✓ Confirmed pipeline has no `plan` subcommand; committed a failing CLI test (c3f812c) and expect the fix to touch only pipeline/cli/main.py.

### 2026-08-24 · implementing · note

Todo:
1. Add `cmd_plan()` to `pipeline/cli/main.py` -- done.
2. Register `sub.add_parser("plan")` -- done.
3. Verify RED: ran the triage test against the new command, it passed
   because it still asserted the old bug (`invalid choice`), so it no
   longer tested real behaviour -- done.
4. Rewrite the test to assert the new command's actual output -- done.
5. Verify GREEN: new test passes; sanity-checked it fails if `cmd_plan`
   prints the whole ticket body instead of the two sections -- done.
6. Run `tests/test_cli.py` and the full suite -- done, 251 passed.
7. Commit -- done, eea468d.

`cmd_plan(args)` calls `Ticket.find(proj(args), args.id)` then prints
`.section("Plan")` and `.section("Acceptance criteria")`, same building
blocks `cmd_gate` uses. New parser line:
`sub.add_parser("plan"); p.add_argument("id"); p.set_defaults(fn=cmd_plan)`.

`tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria`
(triage's reproduction test) asserted `invalid choice: 'plan'`, the absence
of the feature, not its correct behaviour: once the command existed, that
assertion failed (`0 != 0`). Rewrote it to seed a ticket's `## Plan` /
`## Acceptance criteria` with marker text, run `pipeline plan`, and assert
the markers are in stdout while `## Summary` / `## Reproduction` are not.

Recorded the read-only, no-approve-shortcut design in `## Decisions`, as the
ticket's Summary asked.

files_declared: pipeline/cli/main.py, tests/test_cli.py

### 2026-08-24 08:59:19Z · implementing · session · session=05f4a892-9361-4641-b66c-769e444a7210

`implementing` ran as session `05f4a892-9361-4641-b66c-769e444a7210`
- replay: `claude --resume 05f4a892-9361-4641-b66c-769e444a7210`
- log: `.project/logs/TICKET-050-implementing-05f4a892.log`

### 2026-08-24 08:59:19Z · implementing · transition · to=quick-review · result=ok · marker=yes

**implementing -> quick-review** (result: `ok`)

✓ Added `pipeline plan <id>`, printing only Plan and Acceptance criteria; rewrote the reproduction test to assert real output; 251 tests pass.

### 2026-08-24 · quick-review · note

1. Does the committed test fail without this diff? No. Ran
   `git diff main...HEAD -- tests/test_cli.py`: the test committed by
   triage (c3f812c) asserted the failure `invalid choice: 'plan'`.
   `implementing` rewrote
   `test_plan_prints_only_the_plan_and_acceptance_criteria` to assert
   different output (marker text present/absent) instead. The `##
   Reproduction` section's recorded failure describes a test that no
   longer exists in HEAD, so it proves nothing about the test now
   committed. Cannot verify without reverting the diff, which this stage
   cannot do.

2. Does the diff touch a file the ticket did not name? No. Ran
   `git diff --name-only main...HEAD`: `pipeline/cli/main.py`,
   `tests/test_cli.py`. `## Summary` line 28: "Implemented as `cmd_plan()`
   in `pipeline/cli/main.py`". `## Summary` lines 30-32: "Test
   `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria`
   rewritten". Both files are named.

result: fail (question 1 answered no)

### 2026-08-24 09:20:05Z · quick-review · session · session=20fe5670-110a-4de8-a9b0-edc8a6e23c97

`quick-review` ran as session `20fe5670-110a-4de8-a9b0-edc8a6e23c97`
- replay: `claude --resume 20fe5670-110a-4de8-a9b0-edc8a6e23c97`
- log: `.project/logs/TICKET-050-quick-review-20fe5670.log`

### 2026-08-24 09:20:05Z · quick-review · transition · to=planning · result=fail · marker=yes

**quick-review -> planning** (result: `fail`)

✓ Test was rewritten from the triage reproduction; recorded failure no longer proves the committed test fails without the diff.

### 2026-08-24 09:26:38Z · planning · note

Scope: one subsystem, the `pipeline` CLI. No split needed.

`quick-review` was right and the branch state was the problem, not the plan.
I reverted the `pipeline/cli/main.py` half of eea468d and kept the rewritten
test, committed as ad4116e. Reason: `plan-validation` runs `gate()` next, and
`gate()` fails a ticket whose `test_file` PASSES in the worktree
("PASSES -- it must fail before implementation"). No plan step could have fixed
that -- `implementing` runs after the gate. Recorded in `## Decisions`.

Evidence, run in the worktree after ad4116e:

    FAILED tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria
    E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
    E         __main__.py: error: argument cmd: invalid choice: 'plan' (choose from init, new, gate, ...)
    E       assert 2 == 0

So `## Reproduction`'s `expect: invalid choice: 'plan'` matches the committed
test's own failure verbatim; I left that section unchanged.
`uv run --group dev pytest --deselect <that node> -q` reports
`250 passed, 1 deselected`, so the rest of the suite is green on base and here.

Outside my stage, noted not fixed: DEC-033 named a failing `quick-review` as
the tripwire for Sonnet `triage` over-calling `chore`. This is the first one.
The promotion path itself has no way to un-commit a cheap-route fix, which is
the gap `## Decisions` now records.

### 2026-08-24 09:28:49Z · planning · session · session=81f6e4a9-ea3c-406a-9248-a37046f7ab23

`planning` ran as session `81f6e4a9-ea3c-406a-9248-a37046f7ab23`
- replay: `claude --resume 81f6e4a9-ea3c-406a-9248-a37046f7ab23`
- log: `.project/logs/TICKET-050-planning-81f6e4a9.log`

### 2026-08-24 09:28:49Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Reverted the cheap route's fix at ad4116e so the branch is red before Tier A, then planned the re-land of `pipeline plan` in 8 steps across 3 files.

### 2026-08-24 09:48:31Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` fails as required
```
write_text(body)
        r = cli(d, "plan", "TICKET-001")
>       assert r.returncode == 0, r.stderr
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E                            {init,new,gate,approve,reject,answer,resume,logs,ls,status,tui,register,unregister,projects,start,stop,run,metrics} ...
E         __main__.py: error: argument cmd: invalid choice: 'plan' (choose from init, new, gate, approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-050/.venv/bin/python', '-m', 'pipeline', ... approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:241: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================

```
- ok: `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` fails on base `main` too -- the bug is not already fixed upstream
```
      assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-jmhjbl2w/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpks... approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:241: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jmhjbl2w/base
      Built pipeline @ file:///tmp/pipeline-base-jmhjbl2w/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 11ms

```
- acceptance criterion names no test: - `uv run --group dev pytest -q` reports 252 passed.

### 2026-08-24 09:48:31Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion names no test: - `uv run --group dev pytest -q` reports 252 passed.

### 2026-08-24 · planning · note

Tier A raised one finding: "acceptance criterion names no test: - `uv run
--group dev pytest -q` reports 252 passed." I rewrote that criterion to name
`tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` and
`tests/test_cli.py::test_plan_errors_on_an_unknown_ticket`. I changed nothing
else. The 8 plan steps, `## Digest`, `## Decisions checked` and `## Decisions`
stand as written; the gate reported `ok:` on the reproduction in the worktree
and again on base.

Cause, outside my stage and not fixed: the dispatcher runs an installed copy of
the gate that predates commit 2b167c8, "fix: gate accepts an acceptance
criterion naming pytest". Line 275 of
`~/.local/share/uv/tools/pipeline/lib/python3.13/site-packages/pipeline/core/gate.py`
matches `\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/`;
`pipeline/core/gate.py:342` on `main` also allows `\bpytest\b`. `py` is a word
character, so the old pattern rejects a criterion whose only test word is
`pytest`. All six criteria now match the old pattern too, so this plan passes
either version. Closing the drift means reinstalling the tool from `main`. That
is an operator action, not a step in this ticket.

### 2026-08-24 09:54:07Z · planning · session · session=c31e085a-4574-4f0a-812a-556d47261410

`planning` ran as session `c31e085a-4574-4f0a-812a-556d47261410`
- replay: `claude --resume c31e085a-4574-4f0a-812a-556d47261410`
- log: `.project/logs/TICKET-050-planning-c31e085a.log`

### 2026-08-24 09:54:07Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Rewrote the whole-suite acceptance criterion to name both test node ids; the 8 plan steps are unchanged.

### 2026-08-24 09:54:19Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` fails as required
```
write_text(body)
        r = cli(d, "plan", "TICKET-001")
>       assert r.returncode == 0, r.stderr
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E                            {init,new,gate,approve,reject,answer,resume,logs,ls,status,tui,register,unregister,projects,start,stop,run,metrics} ...
E         __main__.py: error: argument cmd: invalid choice: 'plan' (choose from init, new, gate, approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-050/.venv/bin/python', '-m', 'pipeline', ... approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:241: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` fails on base `main` too -- the bug is not already fixed upstream
```
       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-qu5md8bx/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpkg... approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:241: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-qu5md8bx/base
      Built pipeline @ file:///tmp/pipeline-base-qu5md8bx/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 · plan-validation · note

**Tier B: PASS on all eight items.** Every claim below was checked against the
worktree, not against the ticket's own prose.

1. Root cause: `main()` registers no `plan` subparser, so argparse rejects the
   token before any handler runs. Confirmed at `pipeline/cli/main.py:461-488`.
   Steps 1-2 add the handler and the parser line; that is the cause, not the
   symptom.
2. Decisions: DEC-016 holds -- `Ticket.section()` (`pipeline/core/ticket.py:568`)
   goes through `sections()`, adding no fourth heading scan. DEC-020 holds --
   `line_buffer_stdout()` is `main()`'s first statement, line 455. DEC-017 holds;
   the gate recorded `ok:` on both runs. No record carries `superseded-by`.
3. Scope: 8 steps, 3 files, class `feature`. Each step traces to a criterion.
4. Falsifiable: the template has `## Summary` and `## Reproduction`
   (`pipeline/templates/ticket.md:12,16`), so `not in r.stdout` catches a
   print-everything implementation. `die()` prints to stderr and exits 1
   (`pipeline/cli/main.py:30-34`), so criterion 2 is checkable.
5. No research left: lines 88, 463, 229 and 67 are all accurate.
6. Riskiest step: 8, the commit that turns the branch green. `## Rollback`
   names the fallback and the resulting sha, ad4116e.
7. Regression surface: adding a subcommand changes argparse's choices string.
   `grep -rn "add_parser|invalid choice|choose from" tests/` returns nothing,
   so no test asserts that list. Step 7's whole-suite run covers the rest.
8. Blast radius: `git diff main...HEAD --stat` is `tests/test_cli.py | 20 ++`
   today; the plan adds two files. Fits `feature`.

Checked and accepted, not a finding: `.claude/skills/file-ticket/SKILL.md` stays
untouched. Its command block at lines 147-149 lists watch commands, not a
complete CLI index, and it tells a filing session not to act at the approval
gate. No sentence in it becomes false.

### 2026-08-24 09:57:25Z · plan-validation · session · session=653f1282-0339-4664-9731-a3fd9716c26f

`plan-validation` ran as session `653f1282-0339-4664-9731-a3fd9716c26f`
- replay: `claude --resume 653f1282-0339-4664-9731-a3fd9716c26f`
- log: `.project/logs/TICKET-050-plan-validation-653f1282.log`

### 2026-08-24 09:57:25Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B scored all eight judgment items PASS; every file, function and line number the plan cites is accurate, and no test asserts argparse's subcommand list.

### 2026-08-24 09:58:42Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 10:03:14Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` fails as required
```
write_text(body)
        r = cli(d, "plan", "TICKET-001")
>       assert r.returncode == 0, r.stderr
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E                            {init,new,gate,approve,reject,answer,resume,logs,ls,status,tui,register,unregister,projects,start,stop,run,metrics} ...
E         __main__.py: error: argument cmd: invalid choice: 'plan' (choose from init, new, gate, approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)
E         
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-050/.venv/bin/python', '-m', 'pipeline', ... approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:288: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.19s ===============================

```
- ok: `tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria` fails on base `main` too -- the bug is not already fixed upstream
```
      assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/tmp/pipeline-base-8d2x_q9g/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpip... approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)\n").returncode

tests/test_cli.py:288: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-8d2x_q9g/base
      Built pipeline @ file:///tmp/pipeline-base-8d2x_q9g/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 10:03:14Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 · implementing · note

**Todo (plan steps 1-8), all done:**

1. Add `cmd_plan(args)` to `pipeline/cli/main.py` -- done.
2. Register `plan` subparser -- done.
3. Extend `test_plan_prints_only_the_plan_and_acceptance_criteria` with two heading assertions -- done.
4. Add `test_plan_errors_on_an_unknown_ticket` -- done.
5. Run `tests/test_cli.py` -- 13 passed.
6. Document `plan` in `README.md` -- done, line 68.
7. Run full suite + guard script -- 269 passed, guard all passed.
8. Commit -- done, d3f2d7e.

RED confirmed before the edit:
```
E       AssertionError: usage: __main__.py [-h] [--project PROJECT]
E         __main__.py: error: argument cmd: invalid choice: 'plan' (choose from init, new, gate, ...)
E       assert 2 == 0
FAILED tests/test_cli.py::test_plan_prints_only_the_plan_and_acceptance_criteria
```

GREEN confirmed after: `tests/test_cli.py` 13 passed, full suite 269 passed,
`./pipeline/hooks/test_dangerous_commands.py` all passed.
`test_plan_errors_on_an_unknown_ticket` needed no new production code -- Gotcha 1
in `## Digest` already covers the unknown-id path via `Ticket.find` /
`PipelineError` / `die()`; verified it passes on the first run for that reason,
not skipped TDD.

`git diff main...HEAD --stat`: `README.md | 1 +`, `pipeline/cli/main.py | 9 +++++++++`,
`tests/test_cli.py | 32 ++++++++++++++++++++++++++++++++`. Matches `## Rollback`'s
single-commit description.

### 2026-08-24 · implementing · transition · to=verifying · result=ok · marker=yes

**implementing -> verifying** (result: `ok`)

✓ Re-landed `cmd_plan` at d3f2d7e; both new/extended tests pass, full suite 269 passed, guard script passed.

### 2026-08-24 10:05:19Z · implementing · session · session=b5b31569-cbe2-42c1-b3ec-2c9385948481

`implementing` ran as session `b5b31569-cbe2-42c1-b3ec-2c9385948481`
- replay: `claude --resume b5b31569-cbe2-42c1-b3ec-2c9385948481`
- log: `.project/logs/TICKET-050-implementing-b5b31569.log`

### 2026-08-24 10:05:19Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Re-landed cmd_plan and its parser at d3f2d7e; both plan tests, full suite (269) and the guard script pass.

### 2026-08-24 10:06:12Z · review · note

`review` was interrupted; lease released

### 2026-08-24 · review · note

**Review of the branch delta: PASS. No blocking findings.**

Delta: `git diff main...HEAD` (`main` is an ancestor of HEAD) -- 3 files, 42
insertions: `pipeline/cli/main.py` +9, `tests/test_cli.py` +32, `README.md` +1.
The `pipeline/cli/main.py` half adds `cmd_plan` (line 91) and one
`sub.add_parser("plan")` line (line 495), nothing else.

Verified in this worktree:
1. `uv run --group dev pytest -q` -- `269 passed in 11.20s`; tree clean.
2. Both plan tests -- `2 passed in 0.28s`.
3. `grep -n "plan TICKET-001" README.md` -- `68:pipeline --project ~/code/myproject plan TICKET-001    # the plan and its acceptance criteria, nothing else`.
4. `pipeline plan TICKET-050` on this 65KB ticket prints exactly `## Plan` and
   `## Acceptance criteria`, and no `### 2026` thread entry.

Non-blocking:
1. minor: criterion 4 names 252 passed; the run reports 269. `revalidating`
   rebased onto base, which added 16 tests. 269 = 267 + 2. The count is stale.
2. minor: I did not run `./pipeline/hooks/test_dangerous_commands.py`. The guard
   blocks it here: "`test_dangerous_commands.py` is not on the read-only
   allowlist". The delta touches no file under `pipeline/hooks/`.
3. minor: `.claude/skills/file-ticket/SKILL.md` stays untouched per `## Digest`.
   It lists a filing session's commands; `plan` is an operator gate command.

Refuted, so not filed: "`cmd_plan` accepts a traversing id". `Ticket.find` uses
`ticket_path` (`pipeline/core/ticket.py:183`), the same helper `cmd_gate` calls
at `pipeline/cli/main.py:79` -- pre-existing, and `cmd_plan` reaches no shell.

### 2026-08-24 10:09:53Z · review · session · session=2aaf5a93-05f1-4712-b1c9-a0471740caf6

`review` ran as session `2aaf5a93-05f1-4712-b1c9-a0471740caf6`
- replay: `claude --resume 2aaf5a93-05f1-4712-b1c9-a0471740caf6`
- log: `.project/logs/TICKET-050-review-2aaf5a93.log`

### 2026-08-24 10:09:54Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the 3-file delta at d3f2d7e: no blocking findings; 269 passed, diff matches Rollback, 3 minor notes in Thread.

### 2026-08-24 10:10:52Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 10:10:54Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/050


Rebasing (1/4)Rebasing (2/4)Rebasing (3/4)Rebasing (4/4)Successfully rebased and updated refs/heads/ticket/050.
Already up to date.
Updating 49e1aa7..2ca434b
Fast-forward
 README.md            |  1 +
 pipeline/cli/main.py |  9 +++++++++
 tests/test_cli.py    | 32 ++++++++++++++++++++++++++++++++
 3 files changed, 42 insertions(+)

```

### 2026-08-24 10:10:54Z · merging · decision

decision recorded as `DEC-050`
