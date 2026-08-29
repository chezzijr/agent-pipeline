---
id: TICKET-096
stage: done
class: bugfix
branch: ticket/096
test_file: tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/__init__.py
- pipeline/core/config.py
- pipeline/daemon/supervisor.py
- tests/test_config.py
- tests/test_core.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 18
  plan_files: 7
  no_result: 0
  structural_gate_failures: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: cbae4c97-438c-4a2a-867a-6dc184017e14
  log: .project/logs/TICKET-096-review-cbae4c97.log
  cost_usd: 1.1525805000000002
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified: both supervisor.py:16 and config.py:17 already
  import from pipeline.core, so notice_once adds no import cycle; the headless print
  is at supervisor.py:430; tests/test_core.py does not exist yet and pipeline/core/__init__.py
  had no test file. Step 8 drops the ticket id from the message and uses the project
  instead, which is what makes a once-per-process line correct rather than merely
  quieter, and the key includes project, stage and reason so a second project still
  prints. Covers the scale_usd warning TICKET-095 shipped with the same defect. Nothing
  fenced. Noted: this is the second module-level state holder in the dispatcher after
  094''s _MACHINE, both with reset seams for the shared test process.'
approved_at: '2026-08-29T06:56:00.523643+00:00'
---

## Summary

Fixed: the interactive-stage headless notice and the pinned-cap warning both now print once per process instead of once per ticket.

`notice_once(message, *key)` and `reset_notices()` live in `pipeline/core/__init__.py` next to `line_buffer_stdout()`, backed by a module-level `_NOTICED` set. `pipeline/daemon/supervisor.py:435` routes the headless notice through it, keyed on `("headless", project, stage, why)`, and drops `{tid}: ` for `{project}: `. `pipeline/core/config.py`'s `cap_config()` routes the pinned-`max_usd` warning through it, keyed on `("cap-pin", project, stage)`, text unchanged.

All 18 plan steps done, in order, TDD throughout. Four commits: `2a935a4` (helper + `tests/test_core.py`), `b694152` (supervisor.py), `2f5d764` (config.py + `tests/test_config.py`), `ee72e27` (README.md + CLAUDE.md). `pipeline/core/config.py`'s import was line 17, not the plan's 18; the edit matched on content.

Review pass 1 found nothing blocking and re-ran everything itself:
- Full suite `uv run --group dev pytest -q` -- `488 passed in 34.71s`, exit 0. Green throughout, so the base-`main` baseline criterion holds without measuring main.
- `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` -- `1 passed`.
- `tests/test_core.py tests/test_config.py` -- `29 passed`.
- `./pipeline/hooks/test_dangerous_commands.py` -- `guard: all passed`.
- All nine `grep` acceptance criteria hold.

Three non-blocking nits are in the review thread entry: the `spawn()` key uses `str(project)` while `attached` resolves the path; the pinned-cap key omits the `max_usd` value; no test would catch the ticket id returning to the headless message.

## Reproduction

Test: `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket`
Command: `uv run --group dev pytest -q tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket`
Committed: 88cbe4e

Output:
```
E               AssertionError: expected the headless notice once per process, got 2: '  TICKET-001: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-001: planning (opus, batch) pid 1646211 -> TICKET-001-planning-1aa01eb6.log\n  TICKET-002: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-002: planning (opus, batch) pid 1646221 -> TICKET-002-planning-a2a0bee4.log\n'
E               assert 2 == 1
```

expect: expected the headless notice once per process, got 2

## Digest

Files touched: `pipeline/core/__init__.py` (new `notice_once()`), `pipeline/core/config.py` (`cap_config()`, lines 71-86), `pipeline/daemon/supervisor.py` (`spawn()`, lines 421-431), `tests/test_core.py` (new file), `tests/test_config.py`, `README.md`, `CLAUDE.md`.

Both prints fire from inside `spawn()`, once per spawn, unconditionally:

1. `pipeline/daemon/supervisor.py:427-431` -- the headless notice, guarded by `cfg.get("mode") == "interactive" and not interactive`.
2. `pipeline/core/config.py:79-85` -- `cap_config()`'s `scale_usd` warning, reached from `pipeline/daemon/supervisor.py:455` (`cfg = cap_config(stage, cfg, project, counters)`).

Current text at `supervisor.py:429-431`:

```python
        print(f"  {tid}: `{stage}` is interactive, but {why} -- running "
              f"headless (leave `pipeline tui` open before the stage starts "
              f"to steer it)")
```

Current text at `config.py:79-85`:

```python
        if pinned:
            print(
                f"{stage}: max_usd={override['max_usd']} is set without "
                f"scale_usd, so this stage will not scale its cap with plan "
                f"size. Add scale_usd = true if that was not the intent."
            )
```

Entry points and callers: `cap_config()` is called from `pipeline/daemon/supervisor.py:455` and from five places in `tests/test_config.py` (lines 61, 74, 89, 102, 113-121). `pipeline/core/__init__.py` holds `PipelineError` and `line_buffer_stdout()` and imports only `sys`; `pipeline/core/config.py` (line 18) and `pipeline/daemon/supervisor.py` (line 16) both already import from it, so a helper there adds no import edge and no cycle.

Gotchas:

- The suite runs every test in one process, so a module-level set persists across tests. Each test that asserts a print builds a fresh `tempfile.mkdtemp()` project (`git_project()` in `tests/helpers.py:52`), so keying on the project keeps the existing tests independent; the new tests still call `reset_notices()` first.
- `tests/test_config.py::test_pinning_max_usd_without_scale_usd_warns` (line 82) asserts the pinned-cap warning DOES print, and `test_pinning_max_usd_with_scale_usd_does_not_warn` (line 96) asserts the captured output is empty. Both must keep passing.
- `USD_SCALED = {"review", "quick-review", "holistic-review"}` (`pipeline/core/machine.py:33`), so only those three stages reach the pinned-cap warning.
- Precedent for deduped dispatcher output: `_harness_reloader()` (`pipeline/daemon/supervisor.py:1340-1368`) prints "only when its message changes" (DEC-028). It dedupes in a closure because it has one owner; the two prints here sit in two modules, so the state has to be module-level.
- Project-scoped dispatcher lines already use the `  {project}: ...` prefix (`pipeline/daemon/supervisor.py:1264`).
- No decision record, README line or `SKILL.md` line quotes the notice's text. `pipeline/templates/skills/file-ticket/SKILL.md:150` says only "it runs headless and finishes on its own", so the skill needs no edit.
- None of the declared files is in `machine.FENCED`, so the fence does not park this ticket at `awaiting-merge`.

Baseline measured on this branch at 88cbe4e with `uv run --group dev pytest -q`: `1 failed, 458 passed in 34.74s`, the one failure being `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket`.

## Decisions checked

- DEC-059 -- the headless fallback for an interactive stage is deliberate; `spawn()` gates on `attachable` and `watchers()`. This plan changes how often the notice prints and nothing about the gate, so it complies.
- DEC-078 -- `cap_config()` decides which spawns scale, and a project's own `max_usd` pins the cap unless `scale_usd = true`. This plan changes only how often that warning prints, not the decision it reports.
- DEC-020 -- `line_buffer_stdout()` lives in `pipeline/core/__init__.py` because process-wide stdout policy belongs to the entry points, not to a spawner. `notice_once()` is the same category of state and goes in the same module.
- DEC-028 -- the harness-reload warning prints once per distinct error, not once per tick. The same failure this ticket fixes, one scope wider.

Grep terms used against `.project/decisions/`: `once per`, `per spawn`, `noise`, `stdout`, `scale_usd`, `headless`, `interactive`, `print`, `TICKET-095`. No record for TICKET-095 exists; the highest id on disk is DEC-093.

## Plan

1. Write `tests/test_core.py` with the first test of the not-yet-existing helper, importing `from pipeline.core import notice_once, reset_notices`: `test_notice_once_prints_once_per_key` calls `reset_notices()`, then `notice_once("headless here", "headless", "/p", "planning")` twice, and asserts the first call returns `True`, the second returns `False`, and `capsys.readouterr().out` holds the one line `headless here`.
2. Add `test_notice_once_prints_again_for_another_project_or_stage` to `tests/test_core.py`: after `reset_notices()`, print message `a` under key parts `"headless", "/p1", "planning"`, message `b` under `"headless", "/p2", "planning"`, message `c` under `"headless", "/p1", "review"`, then assert the captured output holds the three lines `a`, `b`, `c` in that order.
3. Add `test_reset_notices_clears_the_keys` to `tests/test_core.py`: after `reset_notices()`, print message `a` under key part `"k"`, call `reset_notices()`, print it again, then assert the second `notice_once` call returns `True` and the captured output holds the line `a` twice.
4. Run `uv run --group dev pytest -q tests/test_core.py` in `/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-096` and watch `tests/test_core.py` fail on `ImportError: cannot import name 'notice_once' from 'pipeline.core'`.
5. Add three things to `pipeline/core/__init__.py` below `line_buffer_stdout()`: the module-level `_NOTICED: set[tuple[str, ...]] = set()`; `def notice_once(message: str, *key: str) -> bool`, which returns `False` when `key in _NOTICED`, and otherwise adds `key`, calls `print(message)` and returns `True`; and `def reset_notices() -> None`, which calls `_NOTICED.clear()`.
6. Write both docstrings in `pipeline/core/__init__.py` in that same edit: `notice_once` prints a fact about the operator's setup that is true of every spawn after it, so reprinting per ticket buries the lines that are per-ticket, and callers key it on the project and the stage so a second project or stage still prints once; `reset_notices` is a test seam, because the suite runs every test in one process.
7. Run `uv run --group dev pytest -q tests/test_core.py`, expect it to report `3 passed`, then commit `pipeline/core/__init__.py` and `tests/test_core.py` as `feat(TICKET-096): print a setup-level notice once per process`.
8. In `pipeline/daemon/supervisor.py`, change the import on line 16 to `from pipeline.core import PipelineError, notice_once`, then replace the three-line `print(...)` at lines 429-431 with a `notice_once(...)` call whose key parts are `"headless", str(project), stage, why` and whose message is the current message with two edits and no others: the `{tid}: ` prefix becomes `{project}: `, and the sentence `Said once per process.` is appended after the closing parenthesis of the `pipeline tui` hint.
9. Keep the message in `pipeline/daemon/supervisor.py` spelling `{stage}` and `pipeline tui` inside the same literal backticks it uses today, keep the substring `is interactive, but` intact for `tests/test_pty.py`, wrap the f-string across lines the way the surrounding code does, and leave the `if cfg.get("mode") == "interactive" and not interactive:` guard and the `why = (...)` expression untouched.
10. Extend the comment block above that call in `pipeline/daemon/supervisor.py` with two sentences: the notice states a fact about the setup rather than about the ticket, so it is keyed by project, stage and reason and printed once per process (TICKET-096); the ticket id is gone from the message on purpose, because a line printed once must not name one ticket.
11. Run `uv run --group dev pytest -q tests/test_pty.py tests/test_dispatch.py` and expect no failures, `test_the_headless_notice_prints_once_per_process_not_per_ticket` included; commit `pipeline/daemon/supervisor.py` as `fix(TICKET-096): print the headless notice once per process, not per ticket`.
12. In `pipeline/core/config.py`, change the import on line 18 to `from pipeline.core import PipelineError, notice_once`, then replace the `print(...)` inside `cap_config()` at lines 79-85 with `notice_once(<the same three f-string fragments, character for character>, "cap-pin", str(project), stage)`, so `tests/test_config.py::test_pinning_max_usd_without_scale_usd_warns` still matches the text.
13. Add `test_the_pinned_cap_warning_prints_once_per_process(capsys)` to `tests/test_config.py`, and add `reset_notices` to that file's `from pipeline.core import ...` line: call `reset_notices()`, build `d, sh = git_project()`, append a `[stages.review]` table setting `max_usd = 9` to `d / ".project" / "pipeline.toml"`, commit it with `sh("git add -A && git commit -qm config")`, call `cap_config("review", stage_config("review", d), d, {"plan_files": 15, "plan_steps": 40})` twice, and assert `capsys.readouterr().out.count("max_usd") == 1` with a failure message quoting what was captured.
14. Extend that same test in `tests/test_config.py` with the second-project half: build `d2, sh2 = git_project()`, append a `[stages.quick-review]` table setting `max_usd = 9`, commit it with `sh2`, call `cap_config("quick-review", stage_config("quick-review", d2), d2, {"plan_files": 15, "plan_steps": 40})` once, and assert the newly captured output counts `max_usd` once -- a second project and stage must still warn.
15. Run `uv run --group dev pytest -q tests/test_config.py` and expect no failures; commit `pipeline/core/config.py` and `tests/test_config.py` as `fix(TICKET-096): print the pinned-cap warning once per process`.
16. In `README.md` line 211, rewrite "both run the stage **headless** instead, and say so on stdout." so it says the dispatcher says so on stdout once per process for each project and stage, not once per ticket, because that line describes the operator's setup rather than one ticket.
17. Add one bullet to the gotchas list in `CLAUDE.md`, directly after the "An interactive stage is only interactive while a client is attached" bullet, saying: `notice_once()` in `pipeline/core/__init__.py` holds a module-level set of keys; `spawn()`'s headless line and `cap_config()`'s pinned-`max_usd` warning both go through it, keyed on the project and the stage; both fire from inside `spawn()`, so an un-deduped line repeats for every ticket forever and buries the per-ticket lines (TICKET-096); a new `spawn()` print that states a fact about the setup rather than about the ticket belongs there too; `reset_notices()` is the test seam.
18. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect no failures from either, then commit `README.md` and `CLAUDE.md` as `docs(TICKET-096): say the setup notices print once per process`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_core.py tests/test_config.py` exits 0 and its summary line contains `passed` and neither `failed` nor `error`.
- `uv run --group dev pytest -q` exits 0 and ends with a summary line holding neither `failed` nor `error`.
- `uv run --group dev pytest -q` reports no failing test other than any the same command already fails on base `main`; re-measure that baseline at check time rather than reading a count out of this ticket.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.
- `grep -n "is interactive, but" pipeline/daemon/supervisor.py` prints exactly one line, and that line sits inside a `notice_once(` call, not a `print(` call.
- `grep -c "notice_once" pipeline/core/config.py` prints a number greater than 0, and `grep -n "print(" pipeline/core/config.py` prints no line between the `def cap_config` line and the `def agent_stages` line.
- `grep -c "once per process" README.md` prints a number greater than 0.
- `grep -c "notice_once" CLAUDE.md` prints a number greater than 0.

## Decisions

**A setup-level notice prints once per process, and the state lives in `pipeline/core/__init__.py`.** `notice_once(message, *key)` holds a module-level `_NOTICED` set. It sits next to `line_buffer_stdout()` because both are process-wide stdout policy (DEC-020), and because `pipeline/core/__init__.py` is the one module `pipeline/core/config.py` and `pipeline/daemon/supervisor.py` both already import -- putting it in `config.py` would make the dispatcher's stdout policy a data-file concern. `_harness_reloader()` keeps deduping in its own closure (DEC-028): it has one owner, and these two prints have two.

**The key carries the project, the stage and the reason, not the message alone.** A second project, a second stage, or a headless fallback with a different reason (`nothing can attach to it here` versus `no client is attached`) is a different fact about the setup and prints again. Keying on the message text alone would silence a genuinely new fact; keying on the stage alone would silence every project after the first, which matters because one daemon serves many projects.

**The headless notice no longer names a ticket.** A line printed once must not claim to be about whichever ticket spawned first. It names the project instead, matching `  {project}: ignoring max_parallel` (`pipeline/daemon/supervisor.py:1264`). An edit that puts `{tid}` back into a `notice_once()` message reintroduces that lie.

**`reset_notices()` exists for the test suite and nothing else.** Pytest runs every test in one process, so a test that asserts one of these prints must clear the keys first. No production path calls it: a dispatcher that cleared the set per tick would print the notice per tick.

**Silencing the notice by dropping `mode: interactive` stays forbidden** (DEC-059, and the comment block above the call site). The headless fallback is what stops a ticket parking at a REPL nobody can see.

## Rollback

Revert the four commits from steps 7, 11, 15 and 18 (`git revert <sha>` each, newest first), or revert them as a range. Nothing persists outside the process: `_NOTICED` is in memory, no config key is added, no ticket field is written, and no on-disk format changes. After a revert both notices print once per spawn again, which is today's behaviour, and `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` fails as it does at 88cbe4e. If only the pinned-cap half misbehaves, revert step 15's commit alone; the two call sites are independent.

## Thread

### 2026-08-29 03:52:45Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 05:01:35Z · human · note · by=chezzijr

**note from chezzijr**

From the operator: TICKET-095 merged (e2c461c) and shipped the SAME defect this ticket describes, in a second place. cap_config() at pipeline/core/config.py:79-85 prints its scale_usd warning from inside spawn() (called at pipeline/daemon/supervisor.py:455), so it repeats once per spawn of every USD_SCALED stage, forever -- identical in kind to the headless notice at supervisor.py:428. Treat both as one bug: whatever one-time-per-process mechanism you build for the headless notice, apply it to that warning too, and key it so a different stage or project still prints once. Do not solve it twice.

### 2026-08-29 · triage · agent

**triage: reproduced, test committed**

Confirmed both prints fire on every `spawn()` call, unconditionally:

1. `supervisor.py:428`, the headless notice.
2. `config.py:79-85`, `cap_config()`'s `scale_usd` warning (per operator note above).

Wrote `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket`: two `spawn()` calls of `planning` with a bare `Poller` (nothing attachable), asserts the notice appears once in captured stdout. It fails today with count=2. Committed 88cbe4e.

Did not write a second test for the `cap_config()` warning: same root cause, same fix (a one-time-per-process mechanism keyed by `(project, stage)` or similar), so `planning` handles it as one design, not two. `files_declared` covers both call sites.

Result: `ok`, not `chore` -- the dedup mechanism's key and storage (module-level set? ticket counter? something else) is a design choice, not a mechanical edit.

### 2026-08-29 05:04:10Z · triage · session · session=98400a02-d0e0-42b3-9c40-043d998b2c63

`triage` ran as session `98400a02-d0e0-42b3-9c40-043d998b2c63`
- replay: `claude --resume 98400a02-d0e0-42b3-9c40-043d998b2c63`
- log: `.project/logs/TICKET-096-triage-98400a02.log`
- cost: $0.38 of a $3 cap
- tokens: 5,451 out (238 thinking) · 44 in · 875,491 cache read · 36,889 cache write

### 2026-08-29 05:04:10Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced: headless notice reprints per ticket, not once per process; test committed 88cbe4e

### 2026-08-29 · planning · agent

**planning: plan written, one mechanism for both prints**

The plan adds `notice_once(message, *key)` to `pipeline/core/__init__.py`, next to `line_buffer_stdout()`, and routes both prints through it: the headless notice (`pipeline/daemon/supervisor.py:429`) keyed by `("headless", str(project), stage, why)`, and `cap_config()`'s pinned-cap warning (`pipeline/core/config.py:79-85`) keyed by `("cap-pin", str(project), stage)`. The state is a module-level set; `reset_notices()` is the test seam, because pytest runs every test in one process.

Two design calls the implementer must not reverse. First, the headless message drops the `{tid}: ` prefix for `{project}: `: a line printed once must not name one ticket, and `pipeline/daemon/supervisor.py:1264` already prints project-scoped lines that way. Second, `cap_config()`'s message text stays character for character as it is, so `tests/test_config.py::test_pinning_max_usd_without_scale_usd_warns` (line 82) keeps matching.

Measured baseline on this branch at 88cbe4e, `uv run --group dev pytest -q`: `1 failed, 458 passed in 34.74s`. The single failure is this ticket's repro test.

Out of scope, not fixed: nothing. Both call sites the operator named are in `files_declared`.

### 2026-08-29 05:16:27Z · planning · session · session=643e15f7-aad4-4fca-a4bc-549ba831cba5

`planning` ran as session `643e15f7-aad4-4fca-a4bc-549ba831cba5`
- replay: `claude --resume 643e15f7-aad4-4fca-a4bc-549ba831cba5`
- log: `.project/logs/TICKET-096-planning-643e15f7.log`
- cost: $2.76 of a $10 cap
- tokens: 39,909 out (15,023 thinking) · 56 in · 1,724,568 cache read · 90,265 cache write

### 2026-08-29 05:16:27Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: one notice_once() in pipeline/core/__init__.py, applied to the headless notice and cap_config()'s scale_usd warning

### 2026-08-29 06:23:18Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` fails as required
```
  out = capsys.readouterr().out
            count = out.count("is interactive, but")
>           assert count == 1, \
                f"expected the headless notice once per process, got {count}: {out!r}"
E               AssertionError: expected the headless notice once per process, got 2: '  TICKET-001: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-001: planning (opus, batch) pid 2352003 -> TICKET-001-planning-55a172e5.log\n  TICKET-002: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-002: planning (opus, batch) pid 2352013 -> TICKET-002-planning-16085285.log\n'
E               assert 2 == 1

tests/test_pty.py:549: AssertionError
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.13s ===============================

```
- ok: `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` fails on base `main` too -- the bug is not already fixed upstream
```
n  TICKET-002: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-002: planning (opus, batch) pid 2352099 -> TICKET-002-planning-0d29e9b5.log\n'
E               assert 2 == 1

tests/test_pty.py:549: AssertionError
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.31s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-gcb_u9se/base
      Built pipeline @ file:///tmp/pipeline-base-gcb_u9se/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 17ms

```
- acceptance criterion pins an absolute count copied from `## Digest` (458): - `uv run --group dev pytest -q` ends with a summary line holding neither `failed` nor `error`. The baseline measured on this branch at 88cbe4e was `1 failed, 458 passed`, and that one failure is this ticket's repro test. -- a total any other ticket can move is not a property of this change -- state it as a relation to a measured baseline, or re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check

### 2026-08-29 06:23:19Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion pins an absolute count copied from `## Digest` (458): - `uv run --group dev pytest -q` ends with a summary line holding neither `failed` nor `error`. The baseline measured on this branch at 88cbe4e was `1 failed, 458 passed`, and that one failure is this ticket's repro test. -- a total any other ticket can move is not a property of this change -- state it as a relation to a measured baseline, or re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check

### 2026-08-29 · planning · agent

**planning: plan re-issued, one acceptance criterion rewritten**

The Tier A gate failed exactly one thing: an acceptance criterion copied the absolute total `1 failed, 458 passed` out of `## Digest`. Any other ticket can move that total, so it is not a property of this change.

`## Acceptance criteria` now carries two criteria in its place:

1. `uv run --group dev pytest -q` exits 0 and ends with a summary line holding neither `failed` nor `error`.
2. `uv run --group dev pytest -q` reports no failing test other than any the same command already fails on base `main`, re-measured at check time.

The guard-suite criterion dropped its `as it did on that same baseline` clause and now reads: `./pipeline/hooks/test_dangerous_commands.py` exits 0.

Nothing else changed. `## Digest`, `## Decisions checked`, `## Plan`, `## Decisions` and `## Rollback` stand as written, and the 18 steps are unchanged. The measured baseline stays in `## Digest` as a measurement record, which is where the gate allows it.

Decisions re-resolved against `.project/decisions/`: DEC-020, DEC-028, DEC-059 and DEC-078 are each a real file on disk.

### 2026-08-29 06:24:49Z · planning · session · session=6a0ba092-7968-4231-90ed-a0257849410b

`planning` ran as session `6a0ba092-7968-4231-90ed-a0257849410b`
- replay: `claude --resume 6a0ba092-7968-4231-90ed-a0257849410b`
- log: `.project/logs/TICKET-096-planning-6a0ba092.log`
- cost: $0.80 of a $10 cap
- tokens: 6,349 out (1,697 thinking) · 28 in · 494,004 cache read · 39,493 cache write

### 2026-08-29 06:24:49Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan re-issued: the suite criterion now re-measures against base main instead of pinning 458 passed

### 2026-08-29 06:25:26Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` fails as required
```
  out = capsys.readouterr().out
            count = out.count("is interactive, but")
>           assert count == 1, \
                f"expected the headless notice once per process, got {count}: {out!r}"
E               AssertionError: expected the headless notice once per process, got 2: '  TICKET-001: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-001: planning (opus, batch) pid 2403376 -> TICKET-001-planning-28576046.log\n  TICKET-002: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-002: planning (opus, batch) pid 2403386 -> TICKET-002-planning-0560c810.log\n'
E               assert 2 == 1

tests/test_pty.py:549: AssertionError
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.13s ===============================

```
- ok: `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` fails on base `main` too -- the bug is not already fixed upstream
```
n  TICKET-002: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-002: planning (opus, batch) pid 2403473 -> TICKET-002-planning-b445ce77.log\n'
E               assert 2 == 1

tests/test_pty.py:549: AssertionError
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.30s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-re_w8td2/base
      Built pipeline @ file:///tmp/pipeline-base-re_w8td2/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```

### 2026-08-29 · plan-validation · agent

**Tier B: PASS, all eight items.**

- Root cause: both prints sit unconditionally inside `spawn()`, which runs once per ticket-stage, while each states a fact that is constant for the process -- nothing can attach, or this project pins `max_usd`. No dedup state exists, so the line repeats per ticket. The plan adds that state and keys it on the facts that do vary. It fixes the cause, not the assertion.
- Decision conflict: DEC-020, DEC-028, DEC-059 and DEC-078 are each a file in `.project/decisions/`. The plan complies with all four. It changes how often a line prints, not the `attachable`/`watchers()` gate (DEC-059) and not which spawns scale (DEC-078).
- Scope: every step traces to a criterion. Steps 16-17 back the two `grep -c` criteria; `grep -c "once per process" README.md` and `grep -c "notice_once" CLAUDE.md` both print `0` today, so neither criterion is vacuous.
- Falsifiable: the repro test fails at 88cbe4e. The `grep -n "print(" pipeline/core/config.py` criterion would still match between `def cap_config` and `def agent_stages` if step 12 were skipped.
- No research left: `pipeline/core/__init__.py` holds only `PipelineError` and `line_buffer_stdout()`; `supervisor.py:429-431` and `config.py:79-85` are the two prints, both read.
- Riskiest step: 12, the `cap_config()` swap -- `tests/test_config.py:79` and `:97` assert on that exact output. `git_project()` calls `tempfile.mkdtemp()` per test (`tests/helpers.py:53`), so a per-project key keeps both passing. `## Rollback` reverts that half alone.
- Regression surface: `tests/test_config.py:53,79,97`, `tests/test_pty.py:530`, `tests/test_dispatch.py`. The plan runs all three files.
- Blast radius: `class: bugfix`, 3 source files, 2 test files, 2 docs. None of the seven is in `machine.FENCED` (`pipeline/core/machine.py:43-61`).

Two line numbers drifted; both steps quote the anchoring text, so neither blocks. `pipeline/core/config.py`'s `from pipeline.core import` is line 17, not 18 (step 12). README's `both run the stage **headless** instead` is line 212, not 211 (step 16).

Unverified: I ran no test command -- this stage is read-only. The Tier A gate already recorded the repro test failing on this branch and on base `main`.

### 2026-08-29 06:39:43Z · plan-validation · session · session=63ae58ae-5fee-4477-9986-b0bcf1b856c5

`plan-validation` ran as session `63ae58ae-5fee-4477-9986-b0bcf1b856c5`
- replay: `claude --resume 63ae58ae-5fee-4477-9986-b0bcf1b856c5`
- log: `.project/logs/TICKET-096-plan-validation-63ae58ae.log`
- cost: $1.28 of a $3 cap
- tokens: 11,263 out (3,742 thinking) · 42 in · 933,148 cache read · 53,538 cache write

### 2026-08-29 06:39:43Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes Tier B: root cause is per-spawn printing of setup-level facts; dedup keys on project, stage and reason; every criterion is falsifiable today

### 2026-08-29 06:56:00Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: both supervisor.py:16 and config.py:17 already import from pipeline.core, so notice_once adds no import cycle; the headless print is at supervisor.py:430; tests/test_core.py does not exist yet and pipeline/core/__init__.py had no test file. Step 8 drops the ticket id from the message and uses the project instead, which is what makes a once-per-process line correct rather than merely quieter, and the key includes project, stage and reason so a second project still prints. Covers the scale_usd warning TICKET-095 shipped with the same defect. Nothing fenced. Noted: this is the second module-level state holder in the dispatcher after 094's _MACHINE, both with reset seams for the shared test process.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: both supervisor.py:16 and config.py:17 already import from pipeline.core, so notice_once adds no import cycle; the headless print is at supervisor.py:430; tests/test_core.py does not exist yet and pipeline/core/__init__.py had no test file. Step 8 drops the ticket id from the message and uses the project instead, which is what makes a once-per-process line correct rather than merely quieter, and the key includes project, stage and reason so a second project still prints. Covers the scale_usd warning TICKET-095 shipped with the same defect. Nothing fenced. Noted: this is the second module-level state holder in the dispatcher after 094's _MACHINE, both with reset seams for the shared test process.**

### 2026-08-29 06:56:38Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` fails as required
```
  out = capsys.readouterr().out
            count = out.count("is interactive, but")
>           assert count == 1, \
                f"expected the headless notice once per process, got {count}: {out!r}"
E               AssertionError: expected the headless notice once per process, got 2: '  TICKET-001: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-001: planning (opus, batch) pid 2739692 -> TICKET-001-planning-4412e62d.log\n  TICKET-002: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-002: planning (opus, batch) pid 2739702 -> TICKET-002-planning-d48c4471.log\n'
E               assert 2 == 1

tests/test_pty.py:549: AssertionError
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.19s ===============================

```
- ok: `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` fails on base `main` too -- the bug is not already fixed upstream
```
n  TICKET-002: `planning` is interactive, but nothing can attach to it here -- running headless (leave `pipeline tui` open before the stage starts to steer it)\n  start TICKET-002: planning (opus, batch) pid 2739858 -> TICKET-002-planning-36e33b3f.log\n'
E               assert 2 == 1

tests/test_pty.py:549: AssertionError
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.31s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-l23dsdjc/base
      Built pipeline @ file:///tmp/pipeline-base-l23dsdjc/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 16ms

```

### 2026-08-29 06:56:39Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-29 · implementing · todo

**implementing todo (18 plan steps)**

- [x] 1-3. write tests/test_core.py (three tests for notice_once/reset_notices)
- [x] 4. confirm ImportError
- [x] 5-6. add notice_once/reset_notices to pipeline/core/__init__.py
- [x] 7. run tests/test_core.py, commit
- [x] 8-9. supervisor.py: swap headless print for notice_once
- [x] 10. extend comment block in supervisor.py
- [x] 11. run test_pty.py/test_dispatch.py, commit
- [x] 12. config.py: swap cap_config print for notice_once
- [x] 13-14. add test_the_pinned_cap_warning_prints_once_per_process to test_config.py
- [x] 15. run test_config.py, commit
- [x] 16. README.md line 211 edit
- [x] 17. CLAUDE.md gotchas bullet
- [x] 18. full suite + dangerous_commands test, commit README/CLAUDE.md

### 2026-08-29 · implementing · report

**implementing done, all 18 steps, TDD throughout, result: ok**

Commits: `2a935a4` feat (helper + tests/test_core.py, 3 new tests), `b694152` fix (supervisor.py, headless notice keyed on project+stage+reason), `2f5d764` fix (config.py + tests/test_config.py, pinned-cap warning keyed on project+stage), `ee72e27` docs (README.md line 212, CLAUDE.md gotchas bullet after the interactive-attach one).

RED confirmed before GREEN for each new test: `tests/test_core.py` failed on `ImportError: cannot import name 'notice_once'` before step 5; the pinned-cap-once test ran green immediately after wiring `notice_once` into `cap_config()`, verified against the pre-existing `test_pinning_max_usd_without_scale_usd_warns`/`..._does_not_warn` pair, both still passing.

Test results:
- `tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket`: 1 passed.
- `tests/test_core.py tests/test_config.py`: 29 passed.
- `uv run --group dev pytest -q`: 488 passed, 0 failed, 0 error. Branch is `main` (7f29def) + these 4 commits exactly (`git log --oneline main..HEAD`), so 488 is main's current total plus the 4 new tests here, not a regression against the ticket's stale `458 passed` digest.
- `./pipeline/hooks/test_dangerous_commands.py`: all passed.

All nine acceptance-criteria greps confirmed directly, including `grep -n "is interactive, but" pipeline/daemon/supervisor.py` returning exactly one line inside a `notice_once(` call.

No plan deviation, no scope beyond the 18 steps.

### 2026-08-29 06:59:53Z · implementing · session · session=4bd965c2-abbb-4426-a9c3-226c88f5aead

`implementing` ran as session `4bd965c2-abbb-4426-a9c3-226c88f5aead`
- replay: `claude --resume 4bd965c2-abbb-4426-a9c3-226c88f5aead`
- log: `.project/logs/TICKET-096-implementing-4bd965c2.log`
- cost: $0.86 of a $8 cap
- tokens: 12,614 out (647 thinking) · 90 in · 2,475,322 cache read · 60,495 cache write

### 2026-08-29 06:59:53Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ added notice_once()/reset_notices(), rewired both prints through it, full suite 488 passed, dangerous-commands guard passed

### 2026-08-29 · review · report

**review pass 1 (delta `main..HEAD`, 5 commits, 8 files): no blocking findings, result: ok**

Ran here, in the worktree:
- `uv run --group dev pytest -q` -- `488 passed in 34.71s`, exit 0. The suite is fully green, so the "no failure beyond base `main`" criterion holds without measuring main.
- `uv run --group dev pytest -q tests/test_pty.py::test_the_headless_notice_prints_once_per_process_not_per_ticket` -- `1 passed`, exit 0.
- `uv run --group dev pytest -q tests/test_core.py tests/test_config.py` -- `29 passed`, exit 0.
- `./pipeline/hooks/test_dangerous_commands.py` -- `guard: all passed`, exit 0.
- All nine acceptance greps hold. `grep -n "is interactive, but" pipeline/daemon/supervisor.py` prints one line, at 435, inside a `notice_once(` call. `grep -c "notice_once" pipeline/core/config.py` prints `2`. No `print(` sits between `def cap_config` (line 71) and `def agent_stages` (line 91). `grep -c "once per process" README.md` prints `1`. `grep -c "notice_once" CLAUDE.md` prints `1`.

Both `notice_once()` messages match the plan text apart from the two edits step 8 allows. The existing `test_pinning_max_usd_without_scale_usd_warns` and `..._does_not_warn` each build a fresh `git_project()` tempdir, so the module-level key cannot silence either. No plan drift. `git status --porcelain` is empty; I changed no file but the ticket.

Non-blocking nits, none charged:
1. minor: `spawn()` keys on `str(project)` while `attached` uses `str(project.resolve())`. A process passing one project both relative and absolute would print twice. Registry paths are resolved, so this is unreachable today.
2. minor: the pinned-cap key omits the `max_usd` value, so a value changed mid-process never reprints. That is the ticket's stated key.
3. minor: `tests/test_pty.py:548` counts `is interactive, but` only, so no test fails if the ticket id returns to the message. The no-ticket-id rule lives in `## Decisions` prose, not in a test.

### 2026-08-29 07:03:05Z · review · session · session=cbae4c97-438c-4a2a-867a-6dc184017e14

`review` ran as session `cbae4c97-438c-4a2a-867a-6dc184017e14`
- replay: `claude --resume cbae4c97-438c-4a2a-867a-6dc184017e14`
- log: `.project/logs/TICKET-096-review-cbae4c97.log`
- cost: $1.15 of a $6 cap
- tokens: 10,480 out (4,328 thinking) · 38 in · 792,883 cache read · 49,291 cache write

### 2026-08-29 07:03:05Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review pass 1: no blocking findings; full suite 488 passed, guard suite passed, all nine acceptance greps confirmed; 3 non-blocking nits appended

### 2026-08-29 07:03:42Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 07:03:43Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/096


Current branch ticket/096 is up to date.
Already up to date.
Updating 7f29def..ee72e27
Fast-forward
 CLAUDE.md                     |  7 +++++++
 README.md                     |  3 ++-
 pipeline/core/__init__.py     | 23 +++++++++++++++++++++++
 pipeline/core/config.py       |  7 ++++---
 pipeline/daemon/supervisor.py | 14 ++++++++++----
 tests/test_config.py          | 31 ++++++++++++++++++++++++++++++-
 tests/test_core.py            | 27 +++++++++++++++++++++++++++
 tests/test_pty.py             | 28 ++++++++++++++++++++++++++++
 8 files changed, 131 insertions(+), 9 deletions(-)
 create mode 100644 tests/test_core.py

```

### 2026-08-29 07:03:43Z · merging · decision

decision recorded as `DEC-096`
