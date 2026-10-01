---
id: TICKET-148
stage: done
class: bugfix
branch: ticket/148
test_file:
- tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result
- tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease
deletes: []
files_declared:
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/daemon/server.py
- pipeline/daemon/supervisor.py
- pipeline/pty/host.py
- pipeline/templates/skills/file-ticket/SKILL.md
- tests/test_cli.py
- tests/test_stop.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 9
  plan_files: 9
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: e572e4a0-f59e-43ad-8e50-934d675784b4
  replay: claude --resume e572e4a0-f59e-43ad-8e50-934d675784b4
  log: .project/logs/TICKET-148-review-e572e4a0.log
  cost_usd: 0.7877908
approved_by: chezzijr
approved_at: '2026-10-01T12:48:46.549697+00:00'
---

## Summary

A running stage cannot be stopped cleanly: a stalled interactive stage is never detected, and an operator kill respawns and then escalates

Expected change files: `pipeline/daemon/supervisor.py`, `pipeline/pty/host.py`, `pipeline/cli/main.py`, `pipeline/cli/client.py` and `tests/test_daemon.py`.

Both halves meet in the same place: what the dispatcher does with a stage that has stopped making progress, in `renew_leases()` and in `_finish()`'s no-`.result` path. Each needs its own failing test.

**1. An interactive stage parked at a permission prompt holds its slot forever**

`spawn()` makes a `mode: interactive` stage (planning, by default) interactive whenever any client is subscribed -- `pipeline/daemon/supervisor.py:431`:

    attached = (poller.watchers(str(project.resolve()))
                if getattr(poller, "attachable", False) else 0)
    interactive = cfg.get("mode") == "interactive" and attached > 0

Interactive spawns use `interactive_permission_mode = "acceptEdits"` (`pipeline/harnesses/claude-code.toml`), which auto-accepts file edits only, so the first Bash command stops at "This command requires approval". An operator who opened `pipeline tui` only to watch never sees it. Then `renew_leases()` (`supervisor.py:1602`) renews the lease of any child whose `proc.poll() is None` -- so the parked stage keeps its lease and its `-j` slot until the daemon dies. Lease expiry, the only existing recovery, can never fire.

Observed on a JS project with `-j 3`: two planning sessions sat at the prompt for about 35 minutes, holding 2 of 3 slots, with no thread entry, no event and no stage change.

Expected: an interactive stage whose screen has not changed for a bounded time is detected, gets a thread entry naming what its screen shows, emits an event, and either escalates or is restarted headless -- it never holds a slot indefinitely. Planning should choose the mechanism; options include idle detection on the pyte screen, not renewing a lease for an idle interactive child, making interactive mode opt-in per ticket instead of "any watcher at spawn", or a permission mode that does not prompt (that last one touches the fenced `claude-code.toml`).

**2. No CLI command stops a stage, and kill-then-resume escalates**

The only ways to stop one stage are the TUI's `k` and the daemon socket's `kill` op (`pipeline/daemon/server.py:553`, on main at 7e7545a); `pipeline stop` stops the whole daemon. A killed stage writes no `.result`, so `_finish()` (`supervisor.py:1350`) charges `no_result`, releases the lease and respawns it:

    t.append(stage, "note",
             f"`{stage}` wrote no .result sidecar (attempt {n}) -- will respawn")

An operator who kills a stage to redirect it then runs `pipeline resume <id> --stage X --force`, which races that respawn: the respawned stage's `_finish()` sees `stage` changed and escalates with "frontmatter changed while <stage> held the ticket". Seen twice on one JS project run; the operator had to call the socket from Python to kill at all. A second operator kill also escalates on the `no_result` bound, which is meant for crashing harnesses, not human intent.

Expected: `pipeline kill <id>` stops the running stage, and the ticket then waits for the human -- it is not respawned and `no_result` is not charged. A following `pipeline resume <id> --stage X [--note ...]` works without `--force` and does not escalate. Optionally one command does both (`pipeline kill <id> --resume-at X --note ...`).


## Reproduction

Tests: `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` and `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease`.
Command: `uv run --group dev pytest -q tests/test_stop.py`

Both fail on base. Kill: `Server._op_kill` then `finish()` charges `no_result` and appends "will respawn". Frozen screen: `renew_leases()` renews the lease of a child whose pyte screen has not changed for 2 hours.

expect: AssertionError: a screen frozen for 2 hours still had its lease renewed

## Digest

Files and responsibilities:
- `pipeline/pty/host.py` -- gains `screen_text(screen, last=None)`: the non-blank, right-stripped lines of `screen.display`. It must accept a bare `pyte.Screen` too, because the repro test puts one in `rec["screen"]` (`host.Screen` also exposes `.display`).
- `pipeline/daemon/supervisor.py` -- `renew_leases()` (line 1602), `tick()` (1632), `end_interactive()` (1396), `_finish()`'s `res is None` branch (1350-1385), `spawn()` (387; interactive decision at 431-441, ticket load at 450-458).
- `pipeline/daemon/server.py` -- `Server._op_kill()` (553): today `rec["proc"].terminate()` and nothing else.
- `pipeline/cli/main.py` -- new `cmd_kill`; reuses `connect` (already imported from `pipeline/cli/client.py`, which needs no change), `live_holder()` (509) and `cmd_resume()` (399). Parser rows at 949-978.
- Tests: `tests/test_stop.py` (repro file; the new tests join it), `tests/test_cli.py` (fake-client pattern at 693-731: patch `clim.connect`).
- Docs: `README.md` (command block 74-85, escalation table 586-592), `pipeline/templates/skills/file-ticket/SKILL.md` (escalated-ticket bullet at 274), `CLAUDE.md` (gotcha at 172-181).

Gotchas:
- Skipping renewal alone frees no slot. `tick()` skips any `tid in inflight`, and an expired lease on an inflight child is reaped only during a source-change drain (DEC-123). The idle child must be terminated.
- The repro test patches `supervisor.now`; read time through the module-global `now`, never `T.now()`. Its rec has no `mode` key and its `proc` has no `terminate`, so `renew_leases()` must only mark and skip, never signal.
- `tick()` runs `reap()` (and so `end_interactive()`) before `renew_leases()`: an idle child is marked on tick N and terminated on tick N+1.
- The kill repro rec has no `mode`; `_signal_child()` then calls `proc.terminate()`, so it is safe there. For a batch rec (`mode: "batch"`) it `killpg`s the group; `_op_kill` today signals only the `sh` pid.
- `server.py` cannot import `supervisor` at module level (supervisor imports `Poller` from server). Import `_signal_child` inside `_op_kill`.
- A dispatcher child (`kind` set: gate, suite, merge, regate, unwind) returns from `_finish()` before the `res is None` branch, so a kill of one keeps today's exit-code verdict. Out of scope.
- TUI `k` and `e` (`pipeline/tui/app.py:879`, `:850`) use the same `kill` op, so after this change they park the ticket at `escalated` instead of respawning it. No TUI code changes.
- Baseline on 7da51ba: `uv run --group dev pytest -q tests/test_stop.py tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py tests/test_pty.py tests/test_tui.py` -> `2 failed, 331 passed`; the 2 are this ticket's repro tests.

## Decisions checked

Grep terms: `kill`, `_op_kill`, `renew_lease`, `idle`, `frozen`, `interactive`, `no_result`, `watchers`, `respawn`.
- DEC-059 (active): interactive mode is gated on an attached client; `acceptEdits` in `pipeline/harnesses/claude-code.toml` deliberately stays. This plan complies: it keeps the watcher gate and leaves the fenced toml untouched, and adds idle detection after the spawn.
- DEC-096 (active): dropping `mode: interactive` to silence the headless notice is forbidden. Complied: `planning` keeps `mode: interactive`; only a ticket with `idle_kills > 0` spawns headless.
- DEC-123 (active): reaping an expired lease runs during a drain only. Complied: the idle termination keys on an unchanged screen, never on lease expiry, and touches interactive children only.
- DEC-141 (active, supersedes DEC-011): renewal fresh-loads, compares to `rec["meta"].lease`, and renews below half-life only. Complied: the idle check only adds a skip ahead of that logic.
- DEC-011 (superseded by DEC-141): history only. It froze the event vocabulary and the `kill` op; this plan adds the `stage_idle` event kind and the `killed` and `idle` `stage_end.result` values.

## Plan

1. In `pipeline/pty/host.py`, add `def screen_text(screen, last: int | None = None) -> str` after `class Screen`: right-strip each line of `screen.display`, drop the empty ones, keep the final `last` lines when `last` is set, and join them with newlines; the docstring says it takes a `host.Screen` or a bare `pyte.Screen`.
2. In `pipeline/daemon/supervisor.py`, add `IDLE_MINUTES = 15` and `screen_idle(rec) -> float` above `renew_leases()`; give `renew_leases` an `emit=noop` parameter and pass `emit` from `tick()`; this makes `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` pass.
   `screen_idle`: return `0.0` when `rec.get("screen") is None`; `text = host.screen_text(rec["screen"])`; if `rec.get("screen_seen")` is None or its text differs, set `rec["screen_seen"] = (text, now())` and return `0.0`; else return `(now() - seen[1]).total_seconds() / 60`.
   In `renew_leases`, right after the `poll() is not None` continue: `idle = screen_idle(rec)`; if `idle >= IDLE_MINUTES`: when `rec.get("idle") is None`, set `rec["idle"] = host.screen_text(rec["screen"], last=12)`, print `  {tid}: {stage} screen unchanged for {int(idle)} minutes -- ending it`, and `emit("stage_idle", ticket=tid, stage=rec["stage"], session=rec.get("session"), minutes=int(idle), screen=rec["idle"])`; then `continue` (no renewal).
3. In `pipeline/daemon/supervisor.py` `end_interactive()`, also terminate an interactive, still-running child whose `rec.get("idle") is not None`, printing `  {tid}: {stage} sat on one screen for {IDLE_MINUTES}+ minutes; ending the session`; add `tests/test_stop.py::test_an_idle_interactive_session_is_ended`, which starts `host.start("read x", tmp, env)`, builds `rec = {"proc": proc, "mode": "interactive", "stage": "planning", "idle": "x"}`, calls `end_interactive(tmp, {"TICKET-001": rec})` and asserts `rec["proc"].wait(5) is not None`.
4. In `pipeline/daemon/supervisor.py` `_finish()`, in the `if res is None:` branch right after the operator-kill check of step 6, handle `rec.get("idle") is not None`: charge `n = t.counters.get("idle_kills", 0) + 1`; if `n >= MAX_ATTEMPTS` escalate naming the screen and return `"idle"`; else `t.release_lease()`, append a `note` starting `{stage} showed one screen for {IDLE_MINUTES} minutes with nobody answering it (attempt {n}) -- terminated; it respawns headless. Its last screen:` followed by the text in a fenced block, `t.save()`, return `"idle"`.
   Add `tests/test_stop.py::test_an_idle_kill_charges_idle_kills_and_quotes_the_screen`: build the rec exactly as the kill repro test does, set `rec["idle"] = "This command requires approval"`, call `supervisor.finish(d, rec)`, and assert `counters["idle_kills"] == 1`, `counters.get("no_result", 0) == 0`, the stage is unchanged, the lease is released, and the thread contains `This command requires approval`.
5. In `pipeline/daemon/supervisor.py` `spawn()`, move the `try: t = Ticket.find(...)` block (the one setting `counters, view`) above the `attached = ...` line; set `interactive = cfg.get("mode") == "interactive" and attached > 0 and not counters.get("idle_kills")`; when the mode is interactive and `idle_kills` is set, print `  {tid}: {stage} sat unanswered at a prompt before -- running headless` (per ticket, not through `notice_once`) instead of the existing headless notice.
   Add `tests/test_stop.py::test_a_ticket_with_an_idle_kill_spawns_headless`: `d = project()`, set `counters["idle_kills"] = 1` on TICKET-001 and save, call `supervisor.spawn(d, d, "TICKET-001", "planning", harness("fake"), poller)` with a `Poller` subclass whose `attachable = True` and whose `watchers()` returns `1` (copy `Attachable` from `tests/test_pty.py:395`), assert `rec["mode"] == "batch"`, then `rec["proc"].wait()`, `supervisor.close_child(rec)` and `poller.close()`.
6. In `pipeline/daemon/server.py` `_op_kill`, set `rec["operator_kill"] = True` and replace `rec["proc"].terminate()` with a function-local `from pipeline.daemon.supervisor import _signal_child` plus `_signal_child(rec, signal.SIGTERM)`; in `pipeline/daemon/supervisor.py` `_finish()`, make the first check of the `res is None` branch `if rec.get("operator_kill"):`, which calls `escalate(t, ...)` with the reason `{stage} was stopped by an operator kill; nothing was charged -- pipeline resume {tid} --stage <stage> continues it` and returns `"killed"`.
   This makes `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` pass. Add `tests/test_stop.py::test_a_killed_stage_resumes_without_force`: the same rec, `_op_kill`, `finish`, then `pipeline.cli.main.cmd_resume(argparse.Namespace(project=str(d), id="TICKET-001", stage="planning", note="redirect", grant=None, reset=None, force=False))`; assert the stage is `planning`, `no_result` is 0, and no `SystemExit` was raised.
7. In `pipeline/cli/main.py`, add `KILL_WAIT = 60` and `cmd_kill(args)` after `cmd_resume`, plus the parser row `kill` with `id`, `--resume-at` (metavar STAGE) and `--note` (metavar TEXT); add two tests to `tests/test_cli.py`.
   `cmd_kill` order in `pipeline/cli/main.py`: die if `--note` is given without `--resume-at` ("--note goes with --resume-at"); die if `--resume-at` is not in `KNOWN_STAGES`; `t = Ticket.find(project, args.id)`; `c = connect()`; if None, die with `no daemon is running -- pipeline kill stops a stage the daemon runs; stop pipeline run with Ctrl-C`; `d = c.request("kill", project=str(project), ticket=t.id)`, turning `PipelineError` into `die(f"kill: {e}")`, with `c.close()` in `finally`.
   Then in `pipeline/cli/main.py`, poll until `live_holder(Ticket.find(project, t.id)) is None`, every 0.25 s up to `KILL_WAIT` seconds on a `time.monotonic()` deadline; on timeout die naming `pipeline ls {id}`; print `{id}: stopped (pid {pid}) -> {stage}`; if `--resume-at` is set, call `cmd_resume(argparse.Namespace(project=args.project, id=t.id, stage=args.resume_at, note=args.note, grant=None, reset=None, force=False))`.
   Tests: `tests/test_cli.py::test_kill_stops_the_stage_and_resumes_at_the_named_stage` gives TICKET-001 a live lease `planning-{os.getpid()}`, patches `clim.connect` with a fake client whose `request("kill", ...)` loads TICKET-001, sets `stage = "escalated"`, calls `release_lease()`, saves and returns `{"ticket": "TICKET-001", "project": str(d), "pid": 1}`, and asserts the final stage is `planning` and the thread holds `note from`; `tests/test_cli.py::test_kill_without_a_daemon_dies` sets `clim.connect = lambda: None` and asserts `SystemExit` and a byte-identical ticket file.
8. Document `pipeline kill` and `idle_kills`: in `README.md` add `pipeline --project ~/code/myproject kill TICKET-001 --resume-at planning --note "..."` to the command block and an escalation-table row `| the operator stopped it (pipeline kill) | pipeline resume TICKET-017 --stage <stage> |`; in `pipeline/templates/skills/file-ticket/SKILL.md` add one sentence to the escalated-ticket bullet that an operator kill escalates and charges nothing; in `CLAUDE.md` extend the "An interactive stage is only interactive while a client is attached" gotcha with the idle rule (15 minutes, `idle_kills`, headless respawn, `--reset idle_kills`).
9. Run `uv run --group dev pytest -q tests/test_stop.py tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py tests/test_pty.py tests/test_tui.py` and commit `pipeline/pty/host.py`, `pipeline/daemon/supervisor.py`, `pipeline/daemon/server.py`, `pipeline/cli/main.py`, `tests/test_stop.py`, `tests/test_cli.py`, `README.md`, `pipeline/templates/skills/file-ticket/SKILL.md` and `CLAUDE.md` as `fix(TICKET-148): end idle interactive stages and add pipeline kill`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_stop.py` exits 0, including `test_an_operator_kill_does_not_respawn_or_charge_no_result` and `test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease`.
- `tests/test_stop.py::test_an_idle_interactive_session_is_ended` passes.
- `tests/test_stop.py::test_an_idle_kill_charges_idle_kills_and_quotes_the_screen` passes.
- `tests/test_stop.py::test_a_ticket_with_an_idle_kill_spawns_headless` passes.
- `tests/test_stop.py::test_a_killed_stage_resumes_without_force` passes.
- `tests/test_cli.py::test_kill_stops_the_stage_and_resumes_at_the_named_stage` passes.
- `tests/test_cli.py::test_kill_without_a_daemon_dies` passes.
- `uv run --group dev pytest -q tests/test_stop.py tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py tests/test_pty.py tests/test_tui.py` reports no failed test. Measured baseline on 7da51ba: `2 failed, 331 passed`, the 2 being this ticket's repro tests.
- `uv run pipeline kill --help` exits 0 and prints `--resume-at`.
- `git diff --name-only main -- pipeline/harnesses` prints nothing (DEC-059: the fenced toml stays untouched).

## Decisions

- An operator kill is human intent, not a crash. `Server._op_kill` sets `rec["operator_kill"]`, and `_finish()` escalates such a stage without charging `no_result` and without respawning. `no_result` stays the bound for crashing harnesses only. The TUI's `k` and `e` keys use the same op, so they park the ticket at `escalated` too. `pipeline resume` then needs no `--force`, because `escalate()` released the lease.
- `pipeline kill` waits until the dispatcher reaps the stage (lease released) before it resumes. Resuming earlier rewrites `stage` under a live lease, and `_finish()` escalates that as tampering.
- An interactive stage whose `screen_text()` has not changed for `IDLE_MINUTES` (15) is not renewed, is terminated by `end_interactive()`, charges `idle_kills` (bound `MAX_ATTEMPTS`), and respawns headless. Skipping renewal alone frees no slot: an inflight child is never reaped on lease expiry outside a drain (DEC-123).
- `idle_kills > 0` makes `spawn()` run every interactive stage of that ticket headless for the ticket's life; `pipeline resume <id> --reset idle_kills` re-enables the PTY. Idle time is read through `supervisor.now`, so tests can move it.
- `pipeline/harnesses/claude-code.toml` keeps `acceptEdits` (DEC-059). Idle detection is the recovery for a prompt nobody answers; a non-prompting mode was not adopted.

## Rollback

Revert the step commits on `ticket/148`, or the merge commit on `main`; nothing migrates data. A ticket left with an `idle_kills` counter is inert after a revert, because nothing reads it.
Riskiest step: step 5 (moving the ticket load above the interactive decision in `spawn()`), because `tests/test_pty.py` calls `spawn()` on a project with no ticket on disk. Fallback if `tests/test_pty.py` goes red: leave the existing block where it is, and add a separate `Ticket.find(project, tid).counters.get("idle_kills", 0)` read directly above `attached = ...`, wrapped so `PipelineError` yields `0`.
Second risk: step 2 marks an attended session idle when a human reads a static screen for 15 minutes. Fallback if an operator reports that: raise `IDLE_MINUTES`; do not remove the check.

## Thread

### 2026-10-01 12:07:29Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-10-01 triage · note

Reproduced both halves in `tests/test_stop.py` (commit 7da51ba). Kill test fails with `{'no_result': 1}` against `assert t.counters.get("no_result", 0) == 0`. The frozen-screen test patches `supervisor.now`, so the fix must read time through it. Verdict `ok`, not `chore`: planning must choose the mechanism.

### 2026-10-01 12:08:39Z · triage · session · session=2cc73a1a-1a5f-4f5f-bbbf-38ea9cbd7d1c

`triage` ran as session `2cc73a1a-1a5f-4f5f-bbbf-38ea9cbd7d1c`
- replay: `claude --resume 2cc73a1a-1a5f-4f5f-bbbf-38ea9cbd7d1c`
- log: `.project/logs/TICKET-148-triage-2cc73a1a.log`
- cost: $0.35 of a $3 cap
- tokens: 7,399 out (811 thinking) · 30 in · 533,860 cache read · 42,020 cache write

### 2026-10-01 12:08:39Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ both halves reproduced in tests/test_stop.py; kill charges no_result, frozen screen keeps lease

### 2026-10-01 12:16:46Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` fails as required
```
None, "proc": child}
        me = types.SimpleNamespace(_running=lambda req: (str(d), rec))
        Server._op_kill(me, None, 1, {"ticket": "TICKET-001"})
    
        supervisor.finish(d, rec)
        t = Ticket.load(path)
>       assert t.counters.get("no_result", 0) == 0, t.counters
E       AssertionError: {'no_result': 1}
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7ff1082c8f40>('no_result', 0)
E        +    where <built-in method get of dict object at 0x7ff1082c8f40> = {'no_result': 1}.get
E        +      where {'no_result': 1} = Ticket(path=PosixPath('/tmp/tmp7qdvn44c/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...-10-01 12:15:27Z · plan-validation · note\n\n`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn\n').counters

tests/test_stop.py:34: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` fails as required
```
ease = t2.lease
            before = dict(t2.lease)
            supervisor.renew_leases(d, inflight)
        finally:
            supervisor.now = real
        after = Ticket.load(path)
>       assert after.stage == "escalated" or after.lease == before, \
            "a screen frozen for 2 hours still had its lease renewed"
E       AssertionError: a screen frozen for 2 hours still had its lease renewed
E       assert ('plan-validation' == 'escalated'
E         
E         - escalated
E         + plan-validation or {'holder': 'p...097699+00:00'} == {'holder': 'p...095454+00:00'}
E         
E         Omitting 1 identical items, use -vv to show
E         Differing items:
E         {'expires': '2026-10-01T12:45:28.097699+00:00'} != {'expires': '2026-10-01T14:16:28.095454+00:00'}
E         Use -v to get more diff)

tests/test_stop.py:69: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` fails on base `main` too -- the bug is not already fixed upstream
```
       +      where {'no_result': 1} = Ticket(path=PosixPath('/tmp/tmps7khpc3y/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...-10-01 12:15:29Z · plan-validation · note\n\n`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn\n').counters

tests/test_stop.py:34: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.24s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-gjv07_6p/base
      Built pipeline @ file:///tmp/pipeline-base-gjv07_6p/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 83ms

```
- ok: `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` fails on base `main` too -- the bug is not already fixed upstream
```
ease = t2.lease
            before = dict(t2.lease)
            supervisor.renew_leases(d, inflight)
        finally:
            supervisor.now = real
        after = Ticket.load(path)
>       assert after.stage == "escalated" or after.lease == before, \
            "a screen frozen for 2 hours still had its lease renewed"
E       AssertionError: a screen frozen for 2 hours still had its lease renewed
E       assert ('plan-validation' == 'escalated'
E         
E         - escalated
E         + plan-validation or {'holder': 'p...758060+00:00'} == {'holder': 'p...755941+00:00'}
E         
E         Omitting 1 identical items, use -vv to show
E         Differing items:
E         {'expires': '2026-10-01T12:45:29.758060+00:00'} != {'expires': '2026-10-01T14:16:29.755941+00:00'}
E         Use -v to get more diff)

tests/test_stop.py:69: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: DEC-011 is superseded -- history, not binding
- `files_declared` is empty
- plan step names no declared file: '1. In `pipeline/pty/host.py`, add `def screen_text(screen, last: int | None = None) -> str` after `class Screen`: right-strip each line of `screen.display`, drop the empty ones, keep the final `last` lines when `last` is set, and join them with newlines; the docstring says it takes a `host.Screen` or a bare `pyte.Screen`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. In `pipeline/daemon/supervisor.py`, add `IDLE_MINUTES = 15` and `screen_idle(rec) -> float` above `renew_leases()`; give `renew_leases` an `emit=noop` parameter and pass `emit` from `tick()`; this makes `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` pass. `screen_idle`: return `0.0` when `rec.get("screen") is None`; `text = host.screen_text(rec["screen"])`; if `rec.get("screen_seen")` is None or its text differs, set `rec["screen_seen"] = (text, now())` and return `0.0`; else return `(now() - seen[1]).total_seconds() / 60`. In `renew_leases`, right after the `poll() is not None` continue: `idle = screen_idle(rec)`; if `idle >= IDLE_MINUTES`: when `rec.get("idle") is None`, set `rec["idle"] = host.screen_text(rec["screen"], last=12)`, print `  {tid}: {stage} screen unchanged for {int(idle)} minutes -- ending it`, and `emit("stage_idle", ticket=tid, stage=rec["stage"], session=rec.get("session"), minutes=int(idle), screen=rec["idle"])`; then `continue` (no renewal).' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. In `pipeline/daemon/supervisor.py` `end_interactive()`, also terminate an interactive, still-running child whose `rec.get("idle") is not None`, printing `  {tid}: {stage} sat on one screen for {IDLE_MINUTES}+ minutes; ending the session`; add `tests/test_stop.py::test_an_idle_interactive_session_is_ended`, which starts `host.start("read x", tmp, env)`, builds `rec = {"proc": proc, "mode": "interactive", "stage": "planning", "idle": "x"}`, calls `end_interactive(tmp, {"TICKET-001": rec})` and asserts `rec["proc"].wait(5) is not None`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '4. In `pipeline/daemon/supervisor.py` `_finish()`, in the `if res is None:` branch right after the operator-kill check of step 6, handle `rec.get("idle") is not None`: charge `n = t.counters.get("idle_kills", 0) + 1`; if `n >= MAX_ATTEMPTS` escalate naming the screen and return `"idle"`; else `t.release_lease()`, append a `note` starting `{stage} showed one screen for {IDLE_MINUTES} minutes with nobody answering it (attempt {n}) -- terminated; it respawns headless. Its last screen:` followed by the text in a fenced block, `t.save()`, return `"idle"`. Add `tests/test_stop.py::test_an_idle_kill_charges_idle_kills_and_quotes_the_screen`: build the rec exactly as the kill repro test does, set `rec["idle"] = "This command requires approval"`, call `supervisor.finish(d, rec)`, and assert `counters["idle_kills"] == 1`, `counters.get("no_result", 0) == 0`, the stage is unchanged, the lease is released, and the thread contains `This command requires approval`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '5. In `pipeline/daemon/supervisor.py` `spawn()`, move the `try: t = Ticket.find(...)` block (the one setting `counters, view`) above the `attached = ...` line; set `interactive = cfg.get("mode") == "interactive" and attached > 0 and not counters.get("idle_kills")`; when the mode is interactive and `idle_kills` is set, print `  {tid}: {stage} sat unanswered at a prompt before -- running headless` (per ticket, not through `notice_once`) instead of the existing headless notice. Add `tests/test_stop.py::test_a_ticket_with_an_idle_kill_spawns_headless`: `d = project()`, set `counters["idle_kills"] = 1` on TICKET-001 and save, call `supervisor.spawn(d, d, "TICKET-001", "planning", harness("fake"), poller)` with a `Poller` subclass whose `attachable = True` and whose `watchers()` returns `1` (copy `Attachable` from `tests/test_pty.py:395`), assert `rec["mode"] == "batch"`, then `rec["proc"].wait()`, `supervisor.close_child(rec)` and `poller.close()`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '6. In `pipeline/daemon/server.py` `_op_kill`, set `rec["operator_kill"] = True` and replace `rec["proc"].terminate()` with a function-local `from pipeline.daemon.supervisor import _signal_child` plus `_signal_child(rec, signal.SIGTERM)`; in `pipeline/daemon/supervisor.py` `_finish()`, make the first check of the `res is None` branch `if rec.get("operator_kill"):`, which calls `escalate(t, ...)` with the reason `{stage} was stopped by an operator kill; nothing was charged -- pipeline resume {tid} --stage <stage> continues it` and returns `"killed"`. This makes `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` pass. Add `tests/test_stop.py::test_a_killed_stage_resumes_without_force`: the same rec, `_op_kill`, `finish`, then `pipeline.cli.main.cmd_resume(argparse.Namespace(project=str(d), id="TICKET-001", stage="planning", note="redirect", grant=None, reset=None, force=False))`; assert the stage is `planning`, `no_result` is 0, and no `SystemExit` was raised.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '7. In `pipeline/cli/main.py`, add `KILL_WAIT = 60` and `cmd_kill(args)` after `cmd_resume`, plus the parser row `kill` with `id`, `--resume-at` (metavar STAGE) and `--note` (metavar TEXT); add two tests to `tests/test_cli.py`. `cmd_kill` order in `pipeline/cli/main.py`: die if `--note` is given without `--resume-at` ("--note goes with --resume-at"); die if `--resume-at` is not in `KNOWN_STAGES`; `t = Ticket.find(project, args.id)`; `c = connect()`; if None, die with `no daemon is running -- pipeline kill stops a stage the daemon runs; stop pipeline run with Ctrl-C`; `d = c.request("kill", project=str(project), ticket=t.id)`, turning `PipelineError` into `die(f"kill: {e}")`, with `c.close()` in `finally`. Then in `pipeline/cli/main.py`, poll until `live_holder(Ticket.find(project, t.id)) is None`, every 0.25 s up to `KILL_WAIT` seconds on a `time.monotonic()` deadline; on timeout die naming `pipeline ls {id}`; print `{id}: stopped (pid {pid}) -> {stage}`; if `--resume-at` is set, call `cmd_resume(argparse.Namespace(project=args.project, id=t.id, stage=args.resume_at, note=args.note, grant=None, reset=None, force=False))`. Tests: `tests/test_cli.py::test_kill_stops_the_stage_and_resumes_at_the_named_stage` gives TICKET-001 a live lease `planning-{os.getpid()}`, patches `clim.connect` with a fake client whose `request("kill", ...)` loads TICKET-001, sets `stage = "escalated"`, calls `release_lease()`, saves and returns `{"ticket": "TICKET-001", "project": str(d), "pid": 1}`, and asserts the final stage is `planning` and the thread holds `note from`; `tests/test_cli.py::test_kill_without_a_daemon_dies` sets `clim.connect = lambda: None` and asserts `SystemExit` and a byte-identical ticket file.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '8. Document `pipeline kill` and `idle_kills`: in `README.md` add `pipeline --project ~/code/myproject kill TICKET-001 --resume-at planning --note "..."` to the command block and an escalation-table row `| the operator stopped it (pipeline kill) | pipeline resume TICKET-017 --stage <stage> |`; in `pipeline/templates/skills/file-ticket/SKILL.md` add one sentence to the escalated-ticket bullet that an operator kill escalates and charges nothing; in `CLAUDE.md` extend the "An interactive stage is only interactive while a client is attached" gotcha with the idle rule (15 minutes, `idle_kills`, headless respawn, `--reset idle_kills`).' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '9. Run `uv run --group dev pytest -q tests/test_stop.py tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py tests/test_pty.py tests/test_tui.py` and commit `pipeline/pty/host.py`, `pipeline/daemon/supervisor.py`, `pipeline/daemon/server.py`, `pipeline/cli/main.py`, `tests/test_stop.py`, `tests/test_cli.py`, `README.md`, `pipeline/templates/skills/file-ticket/SKILL.md` and `CLAUDE.md` as `fix(TICKET-148): end idle interactive stages and add pipeline kill`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-10-01 12:18:10Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` fails as required
```
None, "proc": child}
        me = types.SimpleNamespace(_running=lambda req: (str(d), rec))
        Server._op_kill(me, None, 1, {"ticket": "TICKET-001"})
    
        supervisor.finish(d, rec)
        t = Ticket.load(path)
>       assert t.counters.get("no_result", 0) == 0, t.counters
E       AssertionError: {'no_result': 1}
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f2d3baf9100>('no_result', 0)
E        +    where <built-in method get of dict object at 0x7f2d3baf9100> = {'no_result': 1}.get
E        +      where {'no_result': 1} = Ticket(path=PosixPath('/tmp/tmpkx7jmlpo/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...-10-01 12:16:51Z · plan-validation · note\n\n`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn\n').counters

tests/test_stop.py:34: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` fails as required
```
ease = t2.lease
            before = dict(t2.lease)
            supervisor.renew_leases(d, inflight)
        finally:
            supervisor.now = real
        after = Ticket.load(path)
>       assert after.stage == "escalated" or after.lease == before, \
            "a screen frozen for 2 hours still had its lease renewed"
E       AssertionError: a screen frozen for 2 hours still had its lease renewed
E       assert ('plan-validation' == 'escalated'
E         
E         - escalated
E         + plan-validation or {'holder': 'p...991506+00:00'} == {'holder': 'p...989321+00:00'}
E         
E         Omitting 1 identical items, use -vv to show
E         Differing items:
E         {'expires': '2026-10-01T12:46:51.991506+00:00'} != {'expires': '2026-10-01T14:17:51.989321+00:00'}
E         Use -v to get more diff)

tests/test_stop.py:69: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` fails on base `main` too -- the bug is not already fixed upstream
```
       +      where {'no_result': 1} = Ticket(path=PosixPath('/tmp/tmp1v5_iv66/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...-10-01 12:16:53Z · plan-validation · note\n\n`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn\n').counters

tests/test_stop.py:34: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ublbv40d/base
      Built pipeline @ file:///tmp/pipeline-base-ublbv40d/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 62ms

```
- ok: `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` fails on base `main` too -- the bug is not already fixed upstream
```
ease = t2.lease
            before = dict(t2.lease)
            supervisor.renew_leases(d, inflight)
        finally:
            supervisor.now = real
        after = Ticket.load(path)
>       assert after.stage == "escalated" or after.lease == before, \
            "a screen frozen for 2 hours still had its lease renewed"
E       AssertionError: a screen frozen for 2 hours still had its lease renewed
E       assert ('plan-validation' == 'escalated'
E         
E         - escalated
E         + plan-validation or {'holder': 'p...825310+00:00'} == {'holder': 'p...823124+00:00'}
E         
E         Omitting 1 identical items, use -vv to show
E         Differing items:
E         {'expires': '2026-10-01T12:46:53.825310+00:00'} != {'expires': '2026-10-01T14:17:53.823124+00:00'}
E         Use -v to get more diff)

tests/test_stop.py:69: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: DEC-011 is superseded -- history, not binding
- `files_declared` is empty
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '1. In `pipeline/pty/host.py`, add `def screen_text(screen, last: int | None = None) -> str` after `class Screen`: right-strip each line of `screen.display`, drop the empty ones, keep the final `last` lines when `last` is set, and join them with newlines; the docstring says it takes a `host.Screen` or a bare `pyte.Screen`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '2. In `pipeline/daemon/supervisor.py`, add `IDLE_MINUTES = 15` and `screen_idle(rec) -> float` above `renew_leases()`; give `renew_leases` an `emit=noop` parameter and pass `emit` from `tick()`; this makes `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` pass. `screen_idle`: return `0.0` when `rec.get("screen") is None`; `text = host.screen_text(rec["screen"])`; if `rec.get("screen_seen")` is None or its text differs, set `rec["screen_seen"] = (text, now())` and return `0.0`; else return `(now() - seen[1]).total_seconds() / 60`. In `renew_leases`, right after the `poll() is not None` continue: `idle = screen_idle(rec)`; if `idle >= IDLE_MINUTES`: when `rec.get("idle") is None`, set `rec["idle"] = host.screen_text(rec["screen"], last=12)`, print `  {tid}: {stage} screen unchanged for {int(idle)} minutes -- ending it`, and `emit("stage_idle", ticket=tid, stage=rec["stage"], session=rec.get("session"), minutes=int(idle), screen=rec["idle"])`; then `continue` (no renewal).' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '3. In `pipeline/daemon/supervisor.py` `end_interactive()`, also terminate an interactive, still-running child whose `rec.get("idle") is not None`, printing `  {tid}: {stage} sat on one screen for {IDLE_MINUTES}+ minutes; ending the session`; add `tests/test_stop.py::test_an_idle_interactive_session_is_ended`, which starts `host.start("read x", tmp, env)`, builds `rec = {"proc": proc, "mode": "interactive", "stage": "planning", "idle": "x"}`, calls `end_interactive(tmp, {"TICKET-001": rec})` and asserts `rec["proc"].wait(5) is not None`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '4. In `pipeline/daemon/supervisor.py` `_finish()`, in the `if res is None:` branch right after the operator-kill check of step 6, handle `rec.get("idle") is not None`: charge `n = t.counters.get("idle_kills", 0) + 1`; if `n >= MAX_ATTEMPTS` escalate naming the screen and return `"idle"`; else `t.release_lease()`, append a `note` starting `{stage} showed one screen for {IDLE_MINUTES} minutes with nobody answering it (attempt {n}) -- terminated; it respawns headless. Its last screen:` followed by the text in a fenced block, `t.save()`, return `"idle"`. Add `tests/test_stop.py::test_an_idle_kill_charges_idle_kills_and_quotes_the_screen`: build the rec exactly as the kill repro test does, set `rec["idle"] = "This command requires approval"`, call `supervisor.finish(d, rec)`, and assert `counters["idle_kills"] == 1`, `counters.get("no_result", 0) == 0`, the stage is unchanged, the lease is released, and the thread contains `This command requires approval`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '5. In `pipeline/daemon/supervisor.py` `spawn()`, move the `try: t = Ticket.find(...)` block (the one setting `counters, view`) above the `attached = ...` line; set `interactive = cfg.get("mode") == "interactive" and attached > 0 and not counters.get("idle_kills")`; when the mode is interactive and `idle_kills` is set, print `  {tid}: {stage} sat unanswered at a prompt before -- running headless` (per ticket, not through `notice_once`) instead of the existing headless notice. Add `tests/test_stop.py::test_a_ticket_with_an_idle_kill_spawns_headless`: `d = project()`, set `counters["idle_kills"] = 1` on TICKET-001 and save, call `supervisor.spawn(d, d, "TICKET-001", "planning", harness("fake"), poller)` with a `Poller` subclass whose `attachable = True` and whose `watchers()` returns `1` (copy `Attachable` from `tests/test_pty.py:395`), assert `rec["mode"] == "batch"`, then `rec["proc"].wait()`, `supervisor.close_child(rec)` and `poller.close()`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '6. In `pipeline/daemon/server.py` `_op_kill`, set `rec["operator_kill"] = True` and replace `rec["proc"].terminate()` with a function-local `from pipeline.daemon.supervisor import _signal_child` plus `_signal_child(rec, signal.SIGTERM)`; in `pipeline/daemon/supervisor.py` `_finish()`, make the first check of the `res is None` branch `if rec.get("operator_kill"):`, which calls `escalate(t, ...)` with the reason `{stage} was stopped by an operator kill; nothing was charged -- pipeline resume {tid} --stage <stage> continues it` and returns `"killed"`. This makes `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` pass. Add `tests/test_stop.py::test_a_killed_stage_resumes_without_force`: the same rec, `_op_kill`, `finish`, then `pipeline.cli.main.cmd_resume(argparse.Namespace(project=str(d), id="TICKET-001", stage="planning", note="redirect", grant=None, reset=None, force=False))`; assert the stage is `planning`, `no_result` is 0, and no `SystemExit` was raised.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '7. In `pipeline/cli/main.py`, add `KILL_WAIT = 60` and `cmd_kill(args)` after `cmd_resume`, plus the parser row `kill` with `id`, `--resume-at` (metavar STAGE) and `--note` (metavar TEXT); add two tests to `tests/test_cli.py`. `cmd_kill` order in `pipeline/cli/main.py`: die if `--note` is given without `--resume-at` ("--note goes with --resume-at"); die if `--resume-at` is not in `KNOWN_STAGES`; `t = Ticket.find(project, args.id)`; `c = connect()`; if None, die with `no daemon is running -- pipeline kill stops a stage the daemon runs; stop pipeline run with Ctrl-C`; `d = c.request("kill", project=str(project), ticket=t.id)`, turning `PipelineError` into `die(f"kill: {e}")`, with `c.close()` in `finally`. Then in `pipeline/cli/main.py`, poll until `live_holder(Ticket.find(project, t.id)) is None`, every 0.25 s up to `KILL_WAIT` seconds on a `time.monotonic()` deadline; on timeout die naming `pipeline ls {id}`; print `{id}: stopped (pid {pid}) -> {stage}`; if `--resume-at` is set, call `cmd_resume(argparse.Namespace(project=args.project, id=t.id, stage=args.resume_at, note=args.note, grant=None, reset=None, force=False))`. Tests: `tests/test_cli.py::test_kill_stops_the_stage_and_resumes_at_the_named_stage` gives TICKET-001 a live lease `planning-{os.getpid()}`, patches `clim.connect` with a fake client whose `request("kill", ...)` loads TICKET-001, sets `stage = "escalated"`, calls `release_lease()`, saves and returns `{"ticket": "TICKET-001", "project": str(d), "pid": 1}`, and asserts the final stage is `planning` and the thread holds `note from`; `tests/test_cli.py::test_kill_without_a_daemon_dies` sets `clim.connect = lambda: None` and asserts `SystemExit` and a byte-identical ticket file.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '8. Document `pipeline kill` and `idle_kills`: in `README.md` add `pipeline --project ~/code/myproject kill TICKET-001 --resume-at planning --note "..."` to the command block and an escalation-table row `| the operator stopped it (pipeline kill) | pipeline resume TICKET-017 --stage <stage> |`; in `pipeline/templates/skills/file-ticket/SKILL.md` add one sentence to the escalated-ticket bullet that an operator kill escalates and charges nothing; in `CLAUDE.md` extend the "An interactive stage is only interactive while a client is attached" gotcha with the idle rule (15 minutes, `idle_kills`, headless respawn, `--reset idle_kills`).' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '9. Run `uv run --group dev pytest -q tests/test_stop.py tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py tests/test_pty.py tests/test_tui.py` and commit `pipeline/pty/host.py`, `pipeline/daemon/supervisor.py`, `pipeline/daemon/server.py`, `pipeline/cli/main.py`, `tests/test_stop.py`, `tests/test_cli.py`, `README.md`, `pipeline/templates/skills/file-ticket/SKILL.md` and `CLAUDE.md` as `fix(TICKET-148): end idle interactive stages and add pipeline kill`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)

### 2026-10-01 planning · note

Plan written. Both gate runs above are this stage's own `pipeline gate` checks. Each printed only the two findings expected before dispatch: `files_declared` is empty, and steps name no declared file. Every step's path is in the result's `files_declared`.

Mechanism choices:
1. Frozen screen: `renew_leases()` marks an interactive child idle after 15 unchanged minutes and skips renewal. `end_interactive()` terminates it. `_finish()` charges `idle_kills` and respawns the stage headless. Skipping renewal alone frees no slot, because an inflight child is never reaped on lease expiry outside a drain (DEC-123).
2. Kill: `_op_kill` flags the rec, and `_finish()` escalates it and charges nothing. `pipeline kill` waits for the lease release and then optionally runs `cmd_resume`.

`pipeline/harnesses/claude-code.toml` stays untouched (DEC-059), so no fenced file is in the diff.

Outside this ticket's scope, not planned: a kill of a dispatcher child (`kind` gate/suite/merge) still yields an exit-code verdict. The TUI `e` key now leaves the ticket at `escalated` after its kill. This follows from the shared `kill` op.

### 2026-10-01 12:18:43Z · planning · session · session=e8e82ec8-a0f0-408b-9377-6ad4917120d9

`planning` ran as session `e8e82ec8-a0f0-408b-9377-6ad4917120d9`
- replay: `claude --resume e8e82ec8-a0f0-408b-9377-6ad4917120d9`
- log: `.project/logs/TICKET-148-planning-e8e82ec8.log`
- cost: $2.27 of a $10 cap
- tokens: 38,620 out (18,111 thinking) · 54 in · 2,376,199 cache read · 127,658 cache write

### 2026-10-01 12:18:43Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan: idle interactive stage is marked, terminated, charged idle_kills and respawned headless; operator kill escalates without no_result; new pipeline kill --resume-at

### 2026-10-01 12:24:50Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` fails as required
```
None, "proc": child}
        me = types.SimpleNamespace(_running=lambda req: (str(d), rec))
        Server._op_kill(me, None, 1, {"ticket": "TICKET-001"})
    
        supervisor.finish(d, rec)
        t = Ticket.load(path)
>       assert t.counters.get("no_result", 0) == 0, t.counters
E       AssertionError: {'no_result': 1}
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7fb5f59b4540>('no_result', 0)
E        +    where <built-in method get of dict object at 0x7fb5f59b4540> = {'no_result': 1}.get
E        +      where {'no_result': 1} = Ticket(path=PosixPath('/tmp/tmp57l2o5sw/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...-10-01 12:23:35Z · plan-validation · note\n\n`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn\n').counters

tests/test_stop.py:34: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` fails as required
```
ease = t2.lease
            before = dict(t2.lease)
            supervisor.renew_leases(d, inflight)
        finally:
            supervisor.now = real
        after = Ticket.load(path)
>       assert after.stage == "escalated" or after.lease == before, \
            "a screen frozen for 2 hours still had its lease renewed"
E       AssertionError: a screen frozen for 2 hours still had its lease renewed
E       assert ('plan-validation' == 'escalated'
E         
E         - escalated
E         + plan-validation or {'holder': 'p...495973+00:00'} == {'holder': 'p...493897+00:00'}
E         
E         Omitting 1 identical items, use -vv to show
E         Differing items:
E         {'expires': '2026-10-01T12:53:35.495973+00:00'} != {'expires': '2026-10-01T14:24:35.493897+00:00'}
E         Use -v to get more diff)

tests/test_stop.py:69: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` fails on base `main` too -- the bug is not already fixed upstream
```
       +      where {'no_result': 1} = Ticket(path=PosixPath('/tmp/tmpb6z79xcn/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...-10-01 12:23:36Z · plan-validation · note\n\n`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn\n').counters

tests/test_stop.py:34: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.22s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-6pjaeu9w/base
      Built pipeline @ file:///tmp/pipeline-base-6pjaeu9w/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 75ms

```
- ok: `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` fails on base `main` too -- the bug is not already fixed upstream
```
ease = t2.lease
            before = dict(t2.lease)
            supervisor.renew_leases(d, inflight)
        finally:
            supervisor.now = real
        after = Ticket.load(path)
>       assert after.stage == "escalated" or after.lease == before, \
            "a screen frozen for 2 hours still had its lease renewed"
E       AssertionError: a screen frozen for 2 hours still had its lease renewed
E       assert ('plan-validation' == 'escalated'
E         
E         - escalated
E         + plan-validation or {'holder': 'p...392307+00:00'} == {'holder': 'p...390234+00:00'}
E         
E         Omitting 1 identical items, use -vv to show
E         Differing items:
E         {'expires': '2026-10-01T12:53:37.392307+00:00'} != {'expires': '2026-10-01T14:24:37.390234+00:00'}
E         Use -v to get more diff)

tests/test_stop.py:69: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: DEC-011 is superseded -- history, not binding

### 2026-10-01 plan-validation · note

long: eight scored items, each with its evidence.

**Verdict: ok.** All eight items pass. Step 6 has one gap: `pipeline/daemon/server.py` imports no `signal` (imports at lines 12-33), so `signal.SIGTERM` raises `NameError` until the implementer adds `import signal`. The kill repro test exposes this on its first run.

1. Root cause: pass. `renew_leases()` renews any child with `poll() is None`, and an inflight tid is never reaped outside a drain. An unanswered REPL therefore keeps its lease and its slot forever. A killed stage reaches `_finish()` with `res is None`, and that branch cannot tell an operator kill from a crash. Steps 2-4 and 6 fix both causes, not just the assertions.
2. Decisions: pass. The idle check keys on the screen, not on lease expiry (DEC-123). `acceptEdits` and the watcher gate stay (DEC-059). `planning` keeps `mode: interactive` (DEC-096). The new per-ticket print names a ticket fact, so it does not belong in `notice_once`.
3. Scope: pass. Step 8 (docs) has no criterion. CLAUDE.md requires the `file-ticket` skill to match a CLI change.
4. Falsifiable: pass. Each new test fails on base. `test_a_killed_stage_resumes_without_force` holds no lease, so its no-`--force` half is vacuous. Its `no_result == 0` assert still fails on base. The `test_cli` kill test covers lease release.
5. No research left: pass, apart from the `import signal` gap.
6. Riskiest step: the plan names step 5 and gives a fallback. The `try` already yields `counters = {}` with no ticket on disk (`supervisor.py:450-458`). Step 2's screen heuristic is the real-world risk, and the plan gives it a fallback too.
7. Regression surface: `test_pty` spawn and `end_interactive`, `test_daemon` renewal (a rec with no `screen` returns 0.0), and TUI `k`/`e`, which now park at `escalated`. The criteria's six-file suite run covers these.
8. Blast radius: pass. Four code files, two test files and three docs, against the filer's five-file estimate.

Unverified: DEC-011's text. The guard blocked a loop over `.project/decisions/`, and DEC-011 is superseded.

### 2026-10-01 12:27:00Z · plan-validation · session · session=af822e14-c925-4c4a-83f9-fad220ce305a

`plan-validation` ran as session `af822e14-c925-4c4a-83f9-fad220ce305a`
- replay: `claude --resume af822e14-c925-4c4a-83f9-fad220ce305a`
- log: `.project/logs/TICKET-148-plan-validation-af822e14.log`
- cost: $0.95 of a $3 cap
- tokens: 11,931 out (5,721 thinking) · 28 in · 803,914 cache read · 68,722 cache write

### 2026-10-01 12:27:00Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items; it fixes both root causes in renew_leases/end_interactive and in _finish's no-result branch; one gap noted: server.py needs import signal

### 2026-10-01 12:48:46Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-01 14:00:06Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` fails as required
```
None, "proc": child}
        me = types.SimpleNamespace(_running=lambda req: (str(d), rec))
        Server._op_kill(me, None, 1, {"ticket": "TICKET-001"})
    
        supervisor.finish(d, rec)
        t = Ticket.load(path)
>       assert t.counters.get("no_result", 0) == 0, t.counters
E       AssertionError: {'no_result': 1}
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f50dc810940>('no_result', 0)
E        +    where <built-in method get of dict object at 0x7f50dc810940> = {'no_result': 1}.get
E        +      where {'no_result': 1} = Ticket(path=PosixPath('/tmp/tmprej4q6y3/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...-10-01 13:57:23Z · plan-validation · note\n\n`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn\n').counters

tests/test_stop.py:34: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.12s ===============================

```
- ok: `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` fails as required
```
ease = t2.lease
            before = dict(t2.lease)
            supervisor.renew_leases(d, inflight)
        finally:
            supervisor.now = real
        after = Ticket.load(path)
>       assert after.stage == "escalated" or after.lease == before, \
            "a screen frozen for 2 hours still had its lease renewed"
E       AssertionError: a screen frozen for 2 hours still had its lease renewed
E       assert ('plan-validation' == 'escalated'
E         
E         - escalated
E         + plan-validation or {'holder': 'p...096756+00:00'} == {'holder': 'p...094373+00:00'}
E         
E         Omitting 1 identical items, use -vv to show
E         Differing items:
E         {'expires': '2026-10-01T14:27:24.096756+00:00'} != {'expires': '2026-10-01T15:58:24.094373+00:00'}
E         Use -v to get more diff)

tests/test_stop.py:69: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result` fails on base `main` too -- the bug is not already fixed upstream
```
       +      where {'no_result': 1} = Ticket(path=PosixPath('/tmp/tmpzwp81_v9/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...-10-01 13:57:26Z · plan-validation · note\n\n`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn\n').counters

tests/test_stop.py:34: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_operator_kill_does_not_respawn_or_charge_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-bz51cydv/base
      Built pipeline @ file:///tmp/pipeline-base-bz51cydv/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 94ms

```
- ok: `tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease` fails on base `main` too -- the bug is not already fixed upstream
```
ease = t2.lease
            before = dict(t2.lease)
            supervisor.renew_leases(d, inflight)
        finally:
            supervisor.now = real
        after = Ticket.load(path)
>       assert after.stage == "escalated" or after.lease == before, \
            "a screen frozen for 2 hours still had its lease renewed"
E       AssertionError: a screen frozen for 2 hours still had its lease renewed
E       assert ('plan-validation' == 'escalated'
E         
E         - escalated
E         + plan-validation or {'holder': 'p...088507+00:00'} == {'holder': 'p...086089+00:00'}
E         
E         Omitting 1 identical items, use -vv to show
E         Differing items:
E         {'expires': '2026-10-01T14:27:27.088507+00:00'} != {'expires': '2026-10-01T15:58:27.086089+00:00'}
E         Use -v to get more diff)

tests/test_stop.py:69: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stop.py::test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: DEC-011 is superseded -- history, not binding

### 2026-10-01 14:00:06Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-10-01 · implementing · note

Plan steps 1-9 done, commit 48fd8f8. Todo: all steps checked.
- Both repro tests pass. Seven new tests (5 in `tests/test_stop.py`, 3 in `tests/test_cli.py`) each failed before the code: `test_a_session_that_is_not_idle_is_left_running` is a must-still-pass guard and passed on base by design.
- Added `import signal` to `server.py` (the gap plan-validation noted).
- Suite: `386 passed` over test_stop, daemon, cli, dispatch, pty, tui, stages.
- `git diff --name-only main -- pipeline/harnesses` prints nothing.
- `pipeline kill --help` prints `--resume-at`.
- Fixed two of my own test mistakes during RED (`host.start` returns a tuple; a released lease is `{holder: None}`). No existing test was edited.

### 2026-10-01 14:03:42Z · implementing · session · session=205623d8-b55c-4903-a63f-747a62476323

`implementing` ran as session `205623d8-b55c-4903-a63f-747a62476323`
- replay: `claude --resume 205623d8-b55c-4903-a63f-747a62476323`
- log: `.project/logs/TICKET-148-implementing-205623d8.log`
- cost: $0.77 of a $10 cap
- tokens: 17,380 out (471 thinking) · 48 in · 1,467,197 cache read · 75,983 cache write

### 2026-10-01 14:03:42Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ idle interactive stages end and respawn headless; operator kill escalates uncharged; new pipeline kill command

### 2026-10-01 · review · note

**Review of `main...48fd8f8`: no blocking findings.**

Acceptance criteria, checked fresh:
- `pytest -q tests/test_stop.py tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py tests/test_pty.py tests/test_tui.py` -> `341 passed in 68.97s`.
- All 7 named tests pass, plus `test_a_session_that_is_not_idle_is_left_running` and `test_kill_refuses_a_note_without_resume_at`.
- `pipeline kill --help` prints `--resume-at`. `git diff --name-only main -- pipeline/harnesses` prints nothing.

Plan steps 1-8 match the diff. `server.py` gained `import signal`, which plan-validation flagged.

Non-blocking notes:
1. (nit) The `n >= MAX_ATTEMPTS` escalation in `_finish()`'s idle branch is unreachable in normal flow. `MAX_ATTEMPTS = 2`, and `idle_kills >= 1` makes `spawn()` run headless with `rec["screen"] = None`, so `screen_idle()` returns `0.0`. `--reset idle_kills` sets the counter back to 0. The branch fires only after a hand-edit of the counter. It is harmless as a bound.
2. (info) TUI `e` (`pipeline/tui/app.py:854`) now leaves the ticket `escalated` after its kill. The edited ticket needs `pipeline resume`. The ticket's Digest accepts this.

### 2026-10-01 14:06:35Z · review · session · session=e572e4a0-f59e-43ad-8e50-934d675784b4

`review` ran as session `e572e4a0-f59e-43ad-8e50-934d675784b4`
- replay: `claude --resume e572e4a0-f59e-43ad-8e50-934d675784b4`
- log: `.project/logs/TICKET-148-review-e572e4a0.log`
- cost: $0.79 of a $6 cap
- tokens: 8,051 out (3,417 thinking) · 30 in · 737,374 cache read · 59,897 cache write

### 2026-10-01 14:06:35Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review pass on 48fd8f8; all acceptance criteria met (341 passed, kill --help shows --resume-at, harnesses untouched); two non-blocking notes

### 2026-10-01 14:07:53Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-10-01 14:07:55Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/148


Current branch ticket/148 is up to date.
Already up to date.
Updating e717cd4..48fd8f8
Fast-forward
 CLAUDE.md                                      |   6 +
 README.md                                      |   2 +
 pipeline/cli/main.py                           |  36 ++++++
 pipeline/daemon/server.py                      |   5 +-
 pipeline/daemon/supervisor.py                  |  88 +++++++++++---
 pipeline/pty/host.py                           |   9 ++
 pipeline/templates/skills/file-ticket/SKILL.md |   3 +-
 tests/test_cli.py                              |  81 +++++++++++++
 tests/test_stop.py                             | 162 +++++++++++++++++++++++++
 9 files changed, 376 insertions(+), 16 deletions(-)
 create mode 100644 tests/test_stop.py

```

### 2026-10-01 14:07:55Z · merging · decision

decision recorded as `DEC-148`
