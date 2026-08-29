---
id: TICKET-086
stage: done
class: bugfix
branch: ticket/086
test_file: tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child
files_declared:
- CLAUDE.md
- pipeline/core/worktree.py
- pipeline/daemon/supervisor.py
- pipeline/pty/host.py
- tests/test_dispatch.py
- tests/test_pty.py
- tests/test_worktree.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 9
  plan_files: 7
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 314be7d2-29db-4e82-a1bb-84f370066381
  log: .project/logs/TICKET-086-review-314be7d2.log
  cost_usd: 2.12151
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified: except PipelineError at supervisor.py:858,
  pty.fork at pty/host.py:169, Stop(Exception) at test_dispatch.py:911, Stop(BaseException)
  precedent at :957, the AssertionError at :1005 -- all real. BlockingIOError subclasses
  OSError so step 4''s widening catches it. Step 6 correctly converts both loop detectors
  before step 7''s catch would swallow them. Noted: retry_eagain stalls the select
  loop up to 1.75s on a spawn; within budget next to ensure_worktree.'
approved_at: '2026-08-29T04:25:29.434290+00:00'
---

## Summary

Fixed: a transient BlockingIOError from fork used to kill the dispatcher
under `pipeline run`.

`retry_eagain()` in `pipeline/core/worktree.py` retries a `BlockingIOError`
3 times with 0.25/0.5/1.0 s backoff, and wraps all four spawn primitives:
both `subprocess.Popen` calls in `pipeline/daemon/supervisor.py`,
`subprocess.run` in `run_cmd()`, and `pty.fork()` in `pipeline/pty/host.py`.
`run()` now catches per tick like `serve()` does, so a failing tick no longer
reaches `finally: shut_down(project, inflight)`. `start()` widens its catch
to `(PipelineError, OSError)` and the `child()` closure's `spawn_command`
call gets its own `except OSError`, so an exhausted EAGAIN escalates one
ticket through `bail()` instead of taking down the loop.

All 9 plan steps executed in order with TDD. Two loop detectors in
`tests/test_dispatch.py` were converted from `Exception` to `BaseException`
(step 6) before the new catch could swallow them, and a pinning test,
`test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception`,
was added. The repro test's body was rewritten (step 7), keeping its name,
because the version committed at `f0b91c9` could never drain and pass.

Review pass 1 returned `ok`: no blocking findings, four minor ones in
`## Thread`. The largest is `.project/decisions/DEC-069.md:32`, which still
reads "`run()` does not wrap its `tick()` call"; step 8 scoped that fix to
`pipeline/daemon/supervisor.py`.

Verified twice, by `implementing` and by `review`: `uv run --group dev pytest
-q` -- `452 passed`, and every criterion in `## Acceptance criteria` run
individually. `implementing` also ran the falsifiable mutation (widening
`run()`'s catch to `BaseException` makes the pinning test fail with `run()
swallowed a BaseException loop detector`; reverted with `git checkout`);
`review` is read-only and did not re-run it.

## Reproduction

`tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child`

Command: `uv run --group dev pytest -q tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child`

A fake `tick()` puts `TICKET-999` in `inflight` then raises `BlockingIOError`
once (simulating fork EAGAIN). `run(..., once=True)` propagates the exception
uncaught from `pipeline/daemon/supervisor.py:1430`, and its `finally` calls
`shut_down(project, inflight)` with `TICKET-999` still in it -- confirming
issue 2 from the ticket (`run()` does not catch per-tick like `serve()` does).

Failure output:
```
pipeline/daemon/supervisor.py:1430: in run
    worked = tick(project, reload(), inflight, max_parallel, poller,
tests/test_dispatch.py:1755: in fake_tick
    raise BlockingIOError(11, "Resource temporarily unavailable")
E           BlockingIOError: [Errno 11] Resource temporarily unavailable
```

expect: BlockingIOError: [Errno 11] Resource temporarily unavailable

## Digest

- Files this plan modifies: `pipeline/core/worktree.py`, `pipeline/daemon/supervisor.py`, `pipeline/pty/host.py`, `tests/test_worktree.py`, `tests/test_dispatch.py`, `tests/test_pty.py`, `CLAUDE.md`.
- Entry point for issue 2: `run()` calls `tick()` unguarded at `pipeline/daemon/supervisor.py:1430`; `serve()` at `pipeline/daemon/supervisor.py:1496` already wraps its `tick()` call in `try/except Exception` and prints `  {key}: tick failed ({e.__class__.__name__}: {e})`. Copy that shape.
- The four spawn primitives for issue 1, line numbers re-read on `ticket/086` at `f0b91c9`: `subprocess.Popen` in `spawn()`'s batch branch (`pipeline/daemon/supervisor.py:496`), `subprocess.Popen` in `spawn_command()` (`pipeline/daemon/supervisor.py:577`), `subprocess.run` in `run_cmd()` (`pipeline/core/worktree.py:26`), `pty.fork()` in `host.start()` (`pipeline/pty/host.py:169`). Each raises `BlockingIOError` (an `OSError`, errno 11) when fork hits EAGAIN.
- `start()` (`pipeline/daemon/supervisor.py:697`) already wraps its `spawn()` call in `try/except PipelineError as e:` at `pipeline/daemon/supervisor.py:858` and calls `bail()`, which escalates the ticket and emits `stage_end`. Its inner `child()` closure (`pipeline/daemon/supervisor.py:776`) calls `spawn_command()` with no try at all, right after `t.take_lease()` and `t.save()`.
- Gotcha, why this plan is version 2: `run()`'s new `except Exception` swallows any `Exception`-subclass raise a fake `tick()` uses as a runaway-loop detector. Two exist: `class Stop(Exception):` at `tests/test_dispatch.py:911` and `raise AssertionError("a stale loop never exited")` at `tests/test_dispatch.py:1005`. Neither changes colour today -- each test returns at the loop's `if moved and not inflight` check before its detector fires -- so the suite stays green and a later source-watcher regression hangs instead of failing. The repo already records the fix for the other entry point at `tests/test_dispatch.py:957`: `class Stop(BaseException):     # serve() catches Exception around tick()`. Step 6 gives both `run()` detectors the same treatment, before step 7 adds the catch.
- Gotcha, measured: the reproduction test committed at `f0b91c9` cannot pass as written. Its `fake_tick` re-inserts `TICKET-999` into `inflight` on every call, so `if once and not inflight and not worked` is never true. With a `try/except` added around `run()`'s `tick()` call, the test looped until a 60 s timeout and its `finally: shut_down` legitimately saw the ticket: `1 failed in 59.88s`, `AssertionError: ... but shut_down saw ['TICKET-999']`. Step 7 rewrites the body and keeps the name.
- Gotcha: `machine.FENCED` fences `pipeline/core/worktree.py` by the symbol `strip_settings_sources` only, and `fence.py` trips when a diff hunk overlaps that symbol's own line range. Put `retry_eagain()` beside `run_cmd()` at the top of the file so this ticket does not park at `awaiting-merge`.
- Gotcha: `pipeline/core/worktree.py` imports stdlib only, so `pipeline/pty/host.py` can import `retry_eagain` from it with no import cycle. `pipeline/pty/host.py` already imports `pty` at its line 19.
- Gotcha: `tests/test_pty.py` does not import `pty` today; step 5 adds the import. `tests/test_worktree.py` already imports `subprocess` and `pipeline.core.worktree as W`.
- Test patterns already in the suite: `supervisor.spawn(d, d, "TICKET-001", "review", harness("fake"))` (`tests/test_dispatch.py:1144`), and `git_project()` plus `FIXTURE.replace("stage: plan-validation", "stage: implementing")` plus `supervisor.start(d, path, harness("fake"), {})` (`tests/test_dispatch.py:60`). Tests replace a module attribute and restore it in `finally`.
- Baseline measured on `ticket/086` at commit `f0b91c9`: `uv run --group dev pytest -q tests/test_worktree.py tests/test_pty.py` printed `29 passed in 0.79s`.

## Decisions checked

grep terms used against `.project/decisions/`: `shut_down`, `tick()`, `inflight`, `spawn(`, `max_parallel`, `BlockingIOError`, `EAGAIN`, `retry`, `backoff`.

- DEC-028 (harness `.toml` re-read per tick) and DEC-069 (`_start_cap()` swallows a bad `max_parallel`) each justify a local catch with the sentence "`run()` does not wrap its `tick()` call". Step 7 makes that premise false. Both catches stay, and step 8 updates their comments: each keeps a fault out of the tick and names the value or the file, where the new generic catch names only the exception class. Neither record forbids wrapping `tick()`, so this plan supersedes nothing.
- DEC-032 (the source watcher ends the loop and lets `shut_down()` clean up) is unaffected: the new catch changes no loop-exit path. Its two `run()` tests carry the detectors step 6 converts; the conversion changes the detector's class, not the loop-exit property the test asserts.
- DEC-047 and DEC-077 (counters, bounds, budget kills): this plan adds no counter. An EAGAIN that outlives the retries escalates through the existing `bail()`.
- DEC-034 is relevant only as the source of the `strip_settings_sources` fence noted in `## Digest`.

## Plan

1. Add the retry helper to `pipeline/core/worktree.py`, test first, next to `run_cmd()` and far from `strip_settings_sources()`. Write `test_retry_eagain_retries_a_transient_blockingioerror_and_then_returns` and `test_retry_eagain_gives_up_after_the_last_try` in `tests/test_worktree.py`: the first passes a callable that raises `BlockingIOError(11, "Resource temporarily unavailable")` twice then returns `"spawned"`, with `sleep=slept.append`, and asserts the return is `"spawned"`, the callable ran 3 times and `slept == [0.25, 0.5]`; the second passes a callable that always raises, asserts `BlockingIOError` propagates, the callable ran `W.EAGAIN_TRIES == 4` times and `slept == [0.25, 0.5, 1.0]`. Run `uv run --group dev pytest -q tests/test_worktree.py`, watch both fail on `AttributeError: module 'pipeline.core.worktree' has no attribute 'retry_eagain'`, then add `import time`, `EAGAIN_TRIES = 4`, `EAGAIN_BACKOFF = 0.25` and this function:
       def retry_eagain(fn, tries: int = EAGAIN_TRIES, backoff: float = EAGAIN_BACKOFF, sleep=time.sleep):
           """Call `fn()`, retrying a transient `BlockingIOError` with backoff.

           `fork` returns EAGAIN when the machine is at its process limit
           (systemd `TasksMax`, `RLIMIT_NPROC`); Python raises
           `BlockingIOError` and the condition clears within a second. Every
           spawn primitive goes through here, so one EAGAIN ends neither the
           stage, the tick, nor the loop.
           """
           for attempt in range(1, tries + 1):
               try:
                   return fn()
               except BlockingIOError as e:
                   if attempt == tries:
                       raise
                   delay = backoff * 2 ** (attempt - 1)
                   print(f"  spawn hit EAGAIN ({e}); retry {attempt}/{tries - 1} in {delay:.2f}s")
                   sleep(delay)
   Re-run the file, see both tests pass, and commit.
2. Route `run_cmd()` in `pipeline/core/worktree.py` through the helper. Add `test_run_cmd_survives_a_transient_blockingioerror_from_fork` to `tests/test_worktree.py`: it replaces `W.subprocess` with a shim object whose `run(*a, **kw)` raises `BlockingIOError(11, "Resource temporarily unavailable")` on the first call and delegates to the real `subprocess.run` afterwards, restores `W.subprocess = subprocess` in `finally`, and asserts `W.run_cmd("echo hi", Path(tempfile.mkdtemp()))` returns exit code 0 with `out.strip() == "hi"` and the shim called twice. Run it, watch it fail with the raw `BlockingIOError`, then rewrite the body as `p = retry_eagain(lambda: subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, env=project_env()))`, keeping `return p.returncode, (p.stdout + p.stderr)[-4000:]` unchanged. Re-run `uv run --group dev pytest -q tests/test_worktree.py`, see it pass, and commit.
3. Route both `subprocess.Popen` calls in `pipeline/daemon/supervisor.py` through the helper. Add `test_a_spawn_survives_a_transient_blockingioerror_from_fork` and `test_spawn_command_survives_a_transient_blockingioerror_from_fork` to `tests/test_dispatch.py`: each replaces `supervisor.subprocess` with a shim carrying `PIPE = subprocess.PIPE`, `STDOUT = subprocess.STDOUT` and a `Popen(*a, **kw)` that raises `BlockingIOError(11, "Resource temporarily unavailable")` once then delegates to the real `subprocess.Popen`, restores `supervisor.subprocess = subprocess` in `finally`, and asserts the shim ran twice and the child exits; the first calls `supervisor.spawn(d, d, "TICKET-001", "review", harness("fake"))` on a `project()` fixture then `rec["proc"].wait()` and `supervisor.close_child(rec)`, the second calls `supervisor.spawn_command(d, d, "TICKET-001", "verifying", "true")` then `rec["proc"].wait()` and `rec["fh"].close()`. Run `uv run --group dev pytest -q tests/test_dispatch.py -k blockingioerror`, watch both fail, then wrap each call site -- in `spawn()` `proc = retry_eagain(lambda: subprocess.Popen(cmd, shell=True, cwd=wt, stdout=subprocess.PIPE if poller else fh, stderr=subprocess.STDOUT, env=env))`, and in `spawn_command()` `proc = retry_eagain(lambda: subprocess.Popen(cmd, shell=True, cwd=wt, stdout=fh, stderr=subprocess.STDOUT, env=env or project_env()))` -- and add `retry_eagain` to the `from pipeline.core.worktree import (...)` list at `pipeline/daemon/supervisor.py:33`. Re-run, see both pass, and commit.
4. Escalate one ticket when a spawn keeps failing, in `pipeline/daemon/supervisor.py`. Add `test_a_spawn_that_keeps_failing_escalates_one_ticket_and_keeps_the_loop` to `tests/test_dispatch.py`: build `d, _ = git_project()`, write `FIXTURE.replace("stage: plan-validation", "stage: implementing")` to `path = d / ".project/tickets/TICKET-001.md"`, replace `supervisor.spawn` with a function that always raises `BlockingIOError(11, "Resource temporarily unavailable")`, restore it in `finally`, and assert `supervisor.start(d, path, harness("fake"), {})` returns `(True, None)` and `Ticket.load(path).stage == "escalated"`. Run it, watch it fail with the raw `BlockingIOError`, then widen `start()`'s existing handler at `pipeline/daemon/supervisor.py:858` from `except PipelineError as e:` to `except (PipelineError, OSError) as e:`, and wrap the `child()` closure's call as `try: rec = spawn_command(project, wt, tid, stage, cmd, kind, emit, env=env)` with `except OSError as e: return bail(f"spawn failed: {e}")`, leaving `t.take_lease()` and `t.save()` above the try. Re-run `uv run --group dev pytest -q tests/test_dispatch.py`, see it pass, and commit.
5. Route `pty.fork()` in `pipeline/pty/host.py` through the helper. Add `import pty` and `test_an_interactive_spawn_survives_a_transient_blockingioerror_from_fork` to `tests/test_pty.py`: the test replaces `host.pty` with a shim whose `fork()` raises `BlockingIOError(11, "Resource temporarily unavailable")` on the first call and delegates to the real `pty.fork` afterwards, restores `host.pty = pty` in `finally`, calls `host.start("printf hello; exit 0", Path(tempfile.mkdtemp()), dict(os.environ, TERM="xterm-256color"))`, and asserts the shim ran twice in the parent, `proc.wait(timeout=5) is not None`, then closes `pipe`. Run `uv run --group dev pytest -q tests/test_pty.py`, watch it fail, then change `pid, fd = pty.fork()` at `pipeline/pty/host.py:169` to `pid, fd = retry_eagain(pty.fork)`, add `from pipeline.core.worktree import retry_eagain` to the import block, and add one docstring line: the retry runs in the parent only, because the child returns from `pty.fork()` with pid 0 and never raises there. Re-run, see it pass, and commit.
6. Convert both runaway-loop detectors in `tests/test_dispatch.py` to `BaseException` before step 7 adds the catch that would swallow them, matching `serve()`'s detector at `tests/test_dispatch.py:957`. Make three edits in `tests/test_dispatch.py`: (a) in `test_a_merged_dispatcher_change_reaches_the_running_loop`, change line 911 `class Stop(Exception):` to `class Stop(BaseException):     # run() catches Exception around tick()`; (b) in `test_a_stale_dispatcher_reaps_its_children_before_it_exits`, add `class Stop(BaseException):     # run() catches Exception around tick()` with a `pass` body just above its `def fake_tick`, change `raise AssertionError("a stale loop never exited")` at line 1005 to `raise Stop("a stale loop never exited")`, and add an `except Stop as e:` clause raising `AssertionError(str(e))` between its `supervisor.run(d, once=False, interval=0, harness_name="fake")` call and its `finally:`; (c) add this test, which pins the property both detectors now depend on:
       def test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception():
           """TICKET-086: `run()` catches `Exception` around `tick()`, so a test
           that detects a runaway loop by raising from a fake `tick()` must raise
           a `BaseException` subclass -- an `Exception` one is eaten by that catch
           and the test hangs at its timeout instead of failing."""
           d = project()

           class Stop(BaseException):
               pass

           calls, orig_tick = {"n": 0}, supervisor.tick

           def fake_tick(proj, hcfg, inflight, max_parallel, poller, emit, stopping):
               calls["n"] += 1
               raise Stop("a runaway loop detector must reach the test")

           supervisor.tick = fake_tick
           try:
               supervisor.run(d, once=True, interval=0, harness_name="fake")
               raise AssertionError("run() swallowed a BaseException loop detector")
           except Stop:
               pass
           finally:
               supervisor.tick = orig_tick
               shutil.rmtree(d, ignore_errors=True)

           assert calls["n"] == 1, f"expected one tick, got {calls['n']}"
   This step changes no test's colour -- all three pass before step 7 and after it, because nothing catches around `tick()` yet -- and its guard value is the mutation named in `## Acceptance criteria`: widening step 7's catch to `except BaseException` makes the new test fail. Run `uv run --group dev pytest -q tests/test_dispatch.py -k "baseexception or dispatcher_change or stale_dispatcher"`, see `4 passed`, and commit.
7. Make `run()` catch per tick in `pipeline/daemon/supervisor.py`, and rewrite the reproduction test in `tests/test_dispatch.py` so it asserts what survives. Keep the name `test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child`; in `fake_tick`, insert `TICKET-999` into `inflight` and raise only on call 1, and on call 2 append `sorted(inflight)` to a `seen` list and then call `inflight.clear()` so `once=True` can drain and return; assert `calls["n"] >= 2`, `seen[0] == ["TICKET-999"]` and `not killed`. Run it, watch it fail with `BlockingIOError: [Errno 11] Resource temporarily unavailable` out of `pipeline/daemon/supervisor.py:1430`, then wrap the call:
       try:
           worked = tick(project, reload(), inflight, max_parallel, poller,
                         emit, (lambda: True) if moved else stopping)
       except Exception as e:
           # one failing tick must never reach `finally: shut_down(project,
           # inflight)` and SIGTERM every OTHER ticket's agent -- `serve()`
           # has caught per project since it existed (invariant 6). A test
           # that detects a runaway loop from a fake `tick()` must raise a
           # BaseException subclass or this catch eats it: see
           # test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception
           print(f"  {project}: tick failed ({e.__class__.__name__}: {e})")
           worked = False
   Re-run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child`, see `1 passed`, then run `uv run --group dev pytest -q tests/test_dispatch.py`, see no failures, and commit.
8. Correct the three comments in `pipeline/daemon/supervisor.py` that assert the old premise, in one commit. In `_start_cap()`'s docstring (`pipeline/daemon/supervisor.py:1253`) and in `_harness_reloader()`'s docstring (`pipeline/daemon/supervisor.py:1344`), replace the sentence "`run()` ... does not wrap its `tick()` call" with the new fact: `run()` catches per tick since TICKET-086, and this local catch stays because it keeps the fault out of the tick and names the offending value or file, where the generic catch names only the exception class. In `start()`'s handler comment at `pipeline/daemon/supervisor.py:859`, replace "Letting this out propagates through tick() and run(), `finally: shut_down` terminates every OTHER in-flight agent, and the process dies" with: letting this out leaves the ticket holding a lease whose holder pid is the live dispatcher, so nothing retries it until the lease expires 30 minutes later. Run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_worktree.py tests/test_pty.py`, see no failures, and commit.
9. Add one gotcha bullet to `CLAUDE.md`, at the end of "Gotchas, each found the hard way" -- after the `test_file` bullet and before `## Conventions` -- reading: **A transient `fork` EAGAIN must not end a stage or the loop.** `retry_eagain()` in `pipeline/core/worktree.py` retries a `BlockingIOError` 3 times with 0.25/0.5/1.0 s backoff, and every spawn primitive goes through it -- both `subprocess.Popen` calls in `pipeline/daemon/supervisor.py`, `subprocess.run` in `run_cmd()`, and `pty.fork()` in `pipeline/pty/host.py`. `run()` catches per tick like `serve()` does, so an error that outlives the retries escalates one ticket through `bail()` and never reaches `finally: shut_down(project, inflight)`. Two consequences: a new spawn primitive that skips the helper reopens TICKET-086, and a test that detects a runaway loop by raising from a fake `tick()` must raise a `BaseException` subclass, or either catch eats it and the test hangs instead of failing. Then run `uv run --group dev pytest -q`, confirm no failures, and commit.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child` exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_worktree.py tests/test_pty.py tests/test_dispatch.py` exits 0 and prints no line containing `failed`.
- `uv run --group dev pytest -q` exits 0 and prints no line containing `failed`.
- `uv run --group dev pytest -q tests/test_worktree.py -k retry_eagain` exits 0 and prints `2 passed`, which are
  `test_retry_eagain_retries_a_transient_blockingioerror_and_then_returns` and
  `test_retry_eagain_gives_up_after_the_last_try`.
- `uv run --group dev pytest -q tests/test_worktree.py::test_run_cmd_survives_a_transient_blockingioerror_from_fork tests/test_pty.py::test_an_interactive_spawn_survives_a_transient_blockingioerror_from_fork` exits 0 and prints `2 passed`.
- `uv run --group dev pytest -q tests/test_dispatch.py -k blockingioerror_from_fork` exits 0 and prints `2 passed`.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_spawn_that_keeps_failing_escalates_one_ticket_and_keeps_the_loop` exits 0 and prints `1 passed`.
- `grep -c "class Stop(Exception)" tests/test_dispatch.py` prints `0`, so no loop detector raises a class `run()`'s new catch swallows.
- `timeout 120 uv run --group dev pytest -q tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop tests/test_dispatch.py::test_a_stale_dispatcher_reaps_its_children_before_it_exits tests/test_dispatch.py::test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception` exits 0 and prints `3 passed`; exit status 124 means a detector was swallowed and the loop ran away.
- The regression guard is falsifiable: edit `except Exception as e:` in `run()` to read `except BaseException as e:`, then
  `timeout 120 uv run --group dev pytest -q tests/test_dispatch.py::test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception`
  exits non-zero and prints `run() swallowed a BaseException loop detector`; `git checkout -- pipeline/daemon/supervisor.py` restores the file.
- `grep -c "retry_eagain(lambda: subprocess.Popen" pipeline/daemon/supervisor.py` prints `2`, one per spawn call site.
- `grep -c retry_eagain pipeline/pty/host.py` prints `2`, the import and the wrapped `pty.fork()` call.
- `git diff main --unified=0 -- pipeline/core/worktree.py | grep -c strip_settings_sources` prints `0`, so the fenced symbol stays out of this diff.

## Decisions

**A spawn EAGAIN is retried in exactly one place.** `retry_eagain()` in `pipeline/core/worktree.py` wraps all four spawn primitives: both `subprocess.Popen` calls in `pipeline/daemon/supervisor.py`, `subprocess.run` in `run_cmd()`, and `pty.fork()` in `pipeline/pty/host.py`. A fifth spawn primitive added without the wrapper reopens TICKET-086 -- `fork` returning EAGAIN under a systemd `TasksMax` is a machine condition, not a fault in the command being spawned.

**A test that detects a runaway loop from a fake `tick()` must raise a `BaseException` subclass.** Both entry points catch `Exception` around `tick()`: `serve()` always did, `run()` does since TICKET-086. An `Exception`-subclass detector -- `class Stop(Exception)`, or a bare `raise AssertionError(...)` -- is swallowed by that catch, so the test hangs at its timeout instead of failing with its own message, and it keeps passing until the day the property it guards regresses. `tests/test_dispatch.py:957` recorded this for `serve()`; TICKET-086 converted the two `run()` detectors, in `test_a_merged_dispatcher_change_reaches_the_running_loop` and `test_a_stale_dispatcher_reaps_its_children_before_it_exits`, and `test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception` pins the property. Do not "simplify" a detector back to `AssertionError`.

**`run()` catches its `tick()` call, and the local defences that existed because it did not are kept.** `_start_cap()` (DEC-069) still swallows a bad `max_parallel`, and `_harness_reloader()` (DEC-028) still keeps the last good harness dict. Each names the offending value or file, where the generic catch prints only the exception class, and each keeps the fault out of the tick rather than out of the loop. Do not delete either as "now redundant".

**The retry sleeps inside the select loop, deliberately.** The worst case is 1.75 s (0.25 + 0.5 + 1.0) with `EAGAIN_TRIES = 4`, during which no child's pipe is drained and no `.result` is reaped. A spawn already blocks the loop, and the alternative -- deferring the ticket to the next tick -- would have to release a lease it has already taken. Raising `EAGAIN_TRIES` raises that stall; setting it to 1 disables retrying without touching a call site.

**An exhausted EAGAIN escalates one ticket, it does not park it.** `start()` catches `OSError` from `spawn()` and from `spawn_command()` and calls `bail()`. The lease is already taken at that point and its holder pid is the live dispatcher, so `lease_active() and holder_alive(...)` would hold the ticket for the full 30-minute lease before anything retried it. A machine that cannot fork is something a human should see now, with the errno in the ticket.

**The reproduction test asserts on what the next tick sees, not on `shut_down` alone.** `shut_down(project, inflight)` in `run()`'s `finally` is correct on every exit path, so a test whose fake `tick()` leaves a ticket in `inflight` forever can never observe an empty `inflight` there -- the version committed at `f0b91c9` failed for that reason even with the fix applied. The property under test is that `tick()` runs again after the raise with `TICKET-999` still inflight and un-SIGTERMed.

## Rollback

Revert this ticket's merge commit. Nothing else depends on it, and the branch touches no data format, no frontmatter field and no state machine row; the dispatcher then returns to dying on the first `BlockingIOError` from a spawn. The revert also restores the two loop detectors to `Exception`, which is correct once `run()` no longer catches. For the narrower failure -- retries stalling the select loop on a machine permanently at its `TasksMax` -- set `EAGAIN_TRIES = 1` in `pipeline/core/worktree.py`, which restores raise-immediately at every call site while keeping `run()`'s per-tick catch and `start()`'s escalation.

## Thread

### 2026-08-29 03:52:45Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 · triage · ok

Reproduced. `run()` at `pipeline/daemon/supervisor.py:1430` does not catch
`tick()`'s exceptions; a `BlockingIOError` propagates to `finally:
shut_down(project, inflight)`, killing every OTHER inflight child, confirming
issue 2 in `## Summary`. Verified the four raise-straight-out call sites named
in `## Summary` exist as described: `spawn()` batch path
(`subprocess.Popen` at `pipeline/daemon/supervisor.py:495`) and
`spawn_command()` (`pipeline/daemon/supervisor.py:571`); did not open
`pipeline/core/worktree.py` or `pipeline/pty/host.py` -- triage only needed
one call site to reproduce issue 1's symptom via issue 2's uncaught path.

Committed a failing test,
`tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child`,
on this ticket's branch (commit `f0b91c9`). It fakes `tick()` to raise
`BlockingIOError` once with another ticket already in `inflight`, and asserts
`shut_down` sees an empty `inflight` -- i.e. no OTHER child gets killed. It
fails today with the raw `BlockingIOError` escaping `run()`.

Not a `chore`: fixing this needs retry/backoff added at multiple spawn call
sites plus a decision on how `run()` mirrors `serve()`'s per-tick catch --
design choices belong to planning.

### 2026-08-29 03:54:46Z · triage · session · session=041becb4-25de-4fc7-b8d0-7b1555f6463d

`triage` ran as session `041becb4-25de-4fc7-b8d0-7b1555f6463d`
- replay: `claude --resume 041becb4-25de-4fc7-b8d0-7b1555f6463d`
- log: `.project/logs/TICKET-086-triage-041becb4.log`
- cost: $0.57 of a $3 cap
- tokens: 9,617 out (1,500 thinking) · 58 in · 1,236,567 cache read · 55,250 cache write

### 2026-08-29 03:54:46Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced: run() does not wrap tick(), so BlockingIOError from a transient fork EAGAIN kills every inflight child

### 2026-08-29 · planning · ok

Plan written: 8 steps, 7 files, one new helper. `retry_eagain()` in
`pipeline/core/worktree.py` wraps all four spawn primitives; `run()` catches
per tick like `serve()`; `start()` widens its handler to `OSError` so an
exhausted EAGAIN escalates that one ticket through `bail()` instead of
parking it for the 30-minute lease.

One finding the implementer must act on. The reproduction test committed at
`f0b91c9` cannot pass as written. I applied the `run()` catch and ran it:

```
E       AssertionError: a transient BlockingIOError from one tick() must not kill every other inflight ticket's child, but shut_down saw ['TICKET-999']
1 failed in 59.88s
```

Its `fake_tick` re-inserts `TICKET-999` into `inflight` on every call, so
`if once and not inflight and not worked` is never true and the loop only ended
on the 60 s timeout; `finally: shut_down(project, inflight)` is correct on every
exit path, so it saw the ticket. Step 6 rewrites the body, keeps the name, and
asserts on what the next tick sees. I reverted that probe: the tree is clean at
`f0b91c9`.

Noted outside this stage's scope, not fixed: `_start_cap()` and
`_harness_reloader()` docstrings and `start()`'s handler comment all assert
"`run()` does not wrap its `tick()` call". Step 7 corrects all three.

### 2026-08-29 04:05:27Z · planning · session · session=f3807bab-ef6b-4143-81f7-6e22162f2fe4

`planning` ran as session `f3807bab-ef6b-4143-81f7-6e22162f2fe4`
- replay: `claude --resume f3807bab-ef6b-4143-81f7-6e22162f2fe4`
- log: `.project/logs/TICKET-086-planning-f3807bab.log`
- cost: $3.33 of a $10 cap
- tokens: 43,969 out (20,015 thinking) · 74 in · 2,403,535 cache read · 102,604 cache write

### 2026-08-29 04:05:27Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned: one retry_eagain() helper wrapping all four spawn primitives, run() catching per tick like serve(), and start() escalating an exhausted EAGAIN

### 2026-08-29 04:06:22Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child` fails as required
```
ht, max_parallel, poller,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

project = PosixPath('/tmp/tmpqe61_73l')
hcfg = {'effort_flag': '', 'session_flag': '', 'settings_flag': '', 'readonly_tools': '', ...}
inflight = {'TICKET-999': {'proc': None}}, max_parallel = 3
poller = <pipeline.daemon.server.Poller object at 0x7f26ee2c6a50>
emit = <function noop at 0x7f26ee18a660>
stopping = <function _stopper.<locals>.<lambda> at 0x7f26edfcf9c0>

    def fake_tick(project, hcfg, inflight, max_parallel, poller, emit, stopping):
        inflight["TICKET-999"] = other_rec
        calls["n"] += 1
        if calls["n"] == 1:
>           raise BlockingIOError(11, "Resource temporarily unavailable")
E           BlockingIOError: [Errno 11] Resource temporarily unavailable

tests/test_dispatch.py:1755: BlockingIOError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: `tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child` fails on base `main` too -- the bug is not already fixed upstream
```
emit, stopping):
        inflight["TICKET-999"] = other_rec
        calls["n"] += 1
        if calls["n"] == 1:
>           raise BlockingIOError(11, "Resource temporarily unavailable")
E           BlockingIOError: [Errno 11] Resource temporarily unavailable

tests/test_dispatch.py:1755: BlockingIOError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.42s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-bf5yg1ax/base
      Built pipeline @ file:///tmp/pipeline-base-bf5yg1ax/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 · plan-validation · fail

Tier B: seven items pass, one fails.

long: eight scored items each need their own finding line.

**fail -- regression surface.** Step 6 wraps `run()`'s `tick()` call in `except
Exception`. Two existing tests raise from a fake `tick()` as their runaway-loop
detector, and both raises subclass `Exception`: `tests/test_dispatch.py:911`
`class Stop(Exception):` and `tests/test_dispatch.py:1005` `raise
AssertionError("a stale loop never exited")`. The new catch swallows both.
Neither test changes colour today -- each returns at the loop's `if moved and
not inflight` check before its detector fires -- so `pytest -q` stays green and
nothing signals. A later source-watcher regression then hangs instead of
failing. The repo already records this hazard for the other entry point:
`tests/test_dispatch.py:957` reads `class Stop(BaseException):     # serve()
catches Exception around tick()`. Give the two `run()` detectors the same
treatment.

**pass -- root cause.** A transient EAGAIN is fatal at two levels: no spawn
call site retries `fork`, and `run()` has no per-tick catch, so any raise
reaches `finally: shut_down(project, inflight)` and SIGTERMs every inflight
child. The plan fixes both levels, not just the test.

**pass -- decision conflict.** DEC-069 and DEC-028 each justify a local catch
with "`run()` does not wrap its `tick()` call"; step 6 falsifies that sentence.
Both catches stay, as DEC-069 ("Do not 'simplify' `_start_cap()` by dropping
the `except PipelineError`") and DEC-028 property 2 require. Step 7 corrects
all three in-code statements; I read them at
`pipeline/daemon/supervisor.py:1253`, `:1344` and `:859`. DEC-032's loop-exit
paths are untouched -- the new catch sits inside the loop body and leaves the
`moved and not inflight` return alone.

**pass -- scope discipline.** Steps 1-6 each trace to a named criterion. Steps
7 and 8 have no criterion: they correct comments step 6 makes false and record
the gotcha. That is repair of this change, not creep.

**pass -- falsifiable criteria.** Criterion 1 fails today with the raw
`BlockingIOError` (the Tier A gate quoted it). The `retry_eagain` tests do not
exist, so `-k retry_eagain` cannot print `2 passed` by accident. Both `grep -c`
criteria change if a call site is skipped.

**pass -- no research left.** I confirmed all four spawn primitives:
`subprocess.Popen` at `pipeline/daemon/supervisor.py:496` and `:577`,
`subprocess.run` at `pipeline/core/worktree.py:26`, `pty.fork()` at
`pipeline/pty/host.py:169`. The digest cites `:495` and `:571`; it names the
functions, so the drift misleads nobody. Both gotchas hold: `worktree.py`
imports stdlib only (lines 2-8), so `host.py` gets `retry_eagain` with no
cycle, and `tests/test_pty.py` has no `pty` import.

**pass -- riskiest step.** Step 6, and `## Rollback` states its fallback:
revert the merge commit. The retry stall gets its own narrower fallback,
`EAGAIN_TRIES = 1`.

**pass -- blast radius.** `bugfix`, 8 steps, 7 files -- 3 source, 3 test, 1
doc. The ticket itself names four call sites across those three source files.

**pass -- fence.** `symbol_lines()` in `pipeline/core/fence.py` parses the NEW
source and `hunks()` takes new-side ranges, so a hunk near `run_cmd()` (line
25) cannot overlap `strip_settings_sources` (line 104). The plan's placement is
right. Note on the criterion that greps that diff: `grep -c` exits 1 when the
count is `0`, so read it as printed output, never chained with `&&`.

**unverified -- test colour under the fix.** I did not apply step 6 and run the
two tests; the stage is read-only. That both raises subclass `Exception` is
certain from the source. That each test returns before its detector fires I
derived by reading the loop, not by running it. I would have run `uv run
--group dev pytest -q tests/test_dispatch.py -k "dispatcher_change or
stale_dispatcher"` with the catch applied.

### 2026-08-29 04:11:21Z · plan-validation · session · session=31e9c6d5-47c2-46e3-bf87-152dcc2cb710

`plan-validation` ran as session `31e9c6d5-47c2-46e3-bf87-152dcc2cb710`
- replay: `claude --resume 31e9c6d5-47c2-46e3-bf87-152dcc2cb710`
- log: `.project/logs/TICKET-086-plan-validation-31e9c6d5.log`
- cost: $2.01 of a $3 cap
- tokens: 23,079 out (12,340 thinking) · 44 in · 1,267,989 cache read · 79,307 cache write

### 2026-08-29 04:11:21Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ regression surface: step 6's `except Exception` in run() swallows the Exception-subclass raises two existing tests use as runaway-loop detectors (tests/test_dispatch.py:911, :1005); seven other items pass

### 2026-08-29 · planning · ok

Replanned. The plan is 9 steps, up from 8, and addresses the one item
plan-validation rejected: regression surface.

**What changed.** The rejected plan added `except Exception` around `run()`'s
`tick()` call with nothing done about the two runaway-loop detectors that raise
`Exception` subclasses from a fake `tick()`. I read both. `tests/test_dispatch.py:911`
is `class Stop(Exception):`; `tests/test_dispatch.py:1005` is
`raise AssertionError("a stale loop never exited")`. The catch swallows both, and
neither test changes colour, so a later source-watcher regression would hang
instead of failing.

New step 6 converts both, before the catch lands:

1. `class Stop(Exception):` becomes `class Stop(BaseException):`, matching
   `tests/test_dispatch.py:957` -- `class Stop(BaseException):     # serve() catches Exception around tick()`.
2. `test_a_stale_dispatcher_reaps_its_children_before_it_exits` gains its own
   `Stop(BaseException)` and an `except Stop` clause that re-raises `AssertionError`.
3. A new test, `test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception`,
   pins the property.

The old step 6 is now step 7, and its catch carries a comment naming that test.
Steps 7 and 8 renumbered to 8 and 9; their content is unchanged. Two new
acceptance criteria cover the conversion, including the mutation
(`except BaseException`) that makes the new test fail.

The other seven items the gate passed are carried forward unchanged.

### 2026-08-29 04:17:57Z · planning · session · session=d31c7229-feab-4480-8d9a-a734df492c50

`planning` ran as session `d31c7229-feab-4480-8d9a-a734df492c50`
- replay: `claude --resume d31c7229-feab-4480-8d9a-a734df492c50`
- log: `.project/logs/TICKET-086-planning-d31c7229.log`
- cost: $2.74 of a $10 cap
- tokens: 37,626 out (10,103 thinking) · 46 in · 1,674,514 cache read · 95,808 cache write

### 2026-08-29 04:17:57Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned: step 6 converts both run() runaway-loop detectors to BaseException before step 7 adds the except Exception catch that would swallow them

### 2026-08-29 04:18:30Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child` fails as required
```
ht, max_parallel, poller,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

project = PosixPath('/tmp/tmpvgzi56z_')
hcfg = {'effort_flag': '', 'session_flag': '', 'settings_flag': '', 'readonly_tools': '', ...}
inflight = {'TICKET-999': {'proc': None}}, max_parallel = 3
poller = <pipeline.daemon.server.Poller object at 0x7fd143f1aa50>
emit = <function noop at 0x7fd143cfe660>
stopping = <function _stopper.<locals>.<lambda> at 0x7fd143b479c0>

    def fake_tick(project, hcfg, inflight, max_parallel, poller, emit, stopping):
        inflight["TICKET-999"] = other_rec
        calls["n"] += 1
        if calls["n"] == 1:
>           raise BlockingIOError(11, "Resource temporarily unavailable")
E           BlockingIOError: [Errno 11] Resource temporarily unavailable

tests/test_dispatch.py:1755: BlockingIOError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: `tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child` fails on base `main` too -- the bug is not already fixed upstream
```
emit, stopping):
        inflight["TICKET-999"] = other_rec
        calls["n"] += 1
        if calls["n"] == 1:
>           raise BlockingIOError(11, "Resource temporarily unavailable")
E           BlockingIOError: [Errno 11] Resource temporarily unavailable

tests/test_dispatch.py:1755: BlockingIOError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.42s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-4_5h7gfv/base
      Built pipeline @ file:///tmp/pipeline-base-4_5h7gfv/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 · plan-validation · ok

Tier B: eight items pass.

long: eight scored items each need their own finding line.

**pass -- root cause.** A transient fork EAGAIN is fatal at two levels. No
spawn primitive retries it, and `run()` calls `tick()` unguarded at
`pipeline/daemon/supervisor.py:1430`, so any raise reaches `finally:
shut_down(project, inflight)` and SIGTERMs every inflight child. The plan fixes
both levels: `retry_eagain()` at the four primitives, and a per-tick catch that
copies `serve()`'s at `pipeline/daemon/supervisor.py:1502`.

**pass -- regression surface.** This is the item the last round rejected, and
step 6 closes it. I re-read both detectors: `tests/test_dispatch.py:911` is
`class Stop(Exception):`, `:1005` is `raise AssertionError("a stale loop never
exited")`. Step 6 converts both before step 7 adds the catch. I searched wider
for the same hazard and found no third case -- the four other `run()` fakes are
in `tests/test_harness.py` at `:434`, `:469`, `:505` and `:531`, and none
raises from `fake_tick`. `tests/test_harness.py:531` still gets its
`PipelineError`, because `_harness_reloader()` does its first, unguarded read
at `pipeline/daemon/supervisor.py:1410`, above the loop and outside step 7's
`try`.

**pass -- decision conflict.** DEC-069 and DEC-028 each justify a local catch
with the sentence "`run()` does not wrap its `tick()` call"; step 7 falsifies
it. Both catches stay, as DEC-069 ("Do not 'simplify' `_start_cap()` by
dropping the `except PipelineError`") requires, and step 8 corrects the three
in-code statements at `pipeline/daemon/supervisor.py:1253`, `:1344` and `:859`,
which I read. DEC-032 is untouched: the new catch sits inside the loop body and
leaves the `moved and not inflight` return at `:1426` alone.

**pass -- scope discipline.** Steps 1-7 each trace to a named criterion. Steps
8 and 9 have none: they correct comments step 7 makes false and record the
gotcha. That is repair of this change, not creep.

**pass -- falsifiable criteria.** The two grep criteria are shape checks, but
each is paired with a behavioural test that fails if the wrapper is absent --
step 3's two shim tests for the `Popen` sites, step 5's for `pty.fork()`. The
mutation criterion is the strongest: widening step 7's catch to `except
BaseException` makes `run()` swallow the new test's `Stop`, so the test reaches
`raise AssertionError("run() swallowed a BaseException loop detector")`. The
`timeout 120` criterion names exit 124 as the swallowed-detector signal.

**pass -- no research left.** Every step names its file, function and line, and
quotes the code it lands. I re-read all of them on `ticket/086` at `f0b91c9`
and every one matches: `pipeline/daemon/supervisor.py:496`, `:577`, `:781`,
`:857`; `pipeline/core/worktree.py:26`; `pipeline/pty/host.py:169`. `bail()`
(`pipeline/daemon/supervisor.py:708`) returns `True, None`, so step 4's
assertion is right. `pipeline/core/worktree.py` imports stdlib only, so step
5's import adds no cycle, and `tests/test_pty.py` does not import `pty` today.

**pass -- riskiest step, step 7.** Its risk is that `except Exception` hides a
persistent fault in `tick()` behind one printed line per second. `serve()` has
carried the same shape since it existed, invariant 6 requires it, and
`KeyboardInterrupt` is a `BaseException` so Ctrl-C still exits. `## Rollback`
states the fallback: revert the merge commit, which also restores both
detectors to `Exception`, correct once nothing catches. The retry-stall failure
has its own narrower fallback, `EAGAIN_TRIES = 1`.

**pass -- blast radius.** `class: bugfix`, 7 files: 3 source, 3 test, 1 doc.
The four spawn primitives live in three files, so the radius is the root
cause's own, not creep.

Two notes, neither a finding. `.project/decisions/DEC-069.md:32` carries the
same sentence step 8 corrects in code, as does the docstring of
`test_a_broken_harness_mid_run_keeps_the_last_good_config`
(`tests/test_harness.py:493`). Both are historical records that keep their
conclusions; `## Decisions` supersedes the premise. `tests/test_harness.py` is
not in `files_declared` and I am not asking for it.

unverified: the fence outcome. I read `fenced_touches()` and `hunks()` in
`pipeline/core/fence.py` -- a symbol entry trips only on a new-side hunk
overlapping the symbol's own range, computed against the post-change file -- so
adding `retry_eagain()` beside `run_cmd()` at `pipeline/core/worktree.py:25`
keeps the hunks above `strip_settings_sources()` at `:104`. That rests on
reading, not on a run. I would have run `fenced_touches()` against the finished
branch; the guard blocks it, and the criterion
`git diff main --unified=0 -- pipeline/core/worktree.py | grep -c strip_settings_sources`
is the implementer's proxy for it.

### 2026-08-29 04:23:10Z · plan-validation · session · session=fa83ae8b-4d24-4453-94bd-168605f66d2e

`plan-validation` ran as session `fa83ae8b-4d24-4453-94bd-168605f66d2e`
- replay: `claude --resume fa83ae8b-4d24-4453-94bd-168605f66d2e`
- log: `.project/logs/TICKET-086-plan-validation-fa83ae8b.log`
- cost: $2.04 of a $3 cap
- tokens: 20,931 out (8,566 thinking) · 54 in · 1,544,964 cache read · 74,374 cache write

### 2026-08-29 04:23:10Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B: eight items pass; step 6 closes the detector hazard that failed the last round, and every cited line number re-read on ticket/086 at f0b91c9 matches

### 2026-08-29 04:25:29Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: except PipelineError at supervisor.py:858, pty.fork at pty/host.py:169, Stop(Exception) at test_dispatch.py:911, Stop(BaseException) precedent at :957, the AssertionError at :1005 -- all real. BlockingIOError subclasses OSError so step 4's widening catches it. Step 6 correctly converts both loop detectors before step 7's catch would swallow them. Noted: retry_eagain stalls the select loop up to 1.75s on a spawn; within budget next to ensure_worktree.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: except PipelineError at supervisor.py:858, pty.fork at pty/host.py:169, Stop(Exception) at test_dispatch.py:911, Stop(BaseException) precedent at :957, the AssertionError at :1005 -- all real. BlockingIOError subclasses OSError so step 4's widening catches it. Step 6 correctly converts both loop detectors before step 7's catch would swallow them. Noted: retry_eagain stalls the select loop up to 1.75s on a spawn; within budget next to ensure_worktree.**

### 2026-08-29 04:27:48Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child` fails as required
```
ht, max_parallel, poller,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

project = PosixPath('/tmp/tmphrwyhq41')
hcfg = {'effort_flag': '', 'session_flag': '', 'settings_flag': '', 'readonly_tools': '', ...}
inflight = {'TICKET-999': {'proc': None}}, max_parallel = 3
poller = <pipeline.daemon.server.Poller object at 0x7f1386eeea50>
emit = <function noop at 0x7f1386cfeb60>
stopping = <function _stopper.<locals>.<lambda> at 0x7f1386416ca0>

    def fake_tick(project, hcfg, inflight, max_parallel, poller, emit, stopping):
        inflight["TICKET-999"] = other_rec
        calls["n"] += 1
        if calls["n"] == 1:
>           raise BlockingIOError(11, "Resource temporarily unavailable")
E           BlockingIOError: [Errno 11] Resource temporarily unavailable

tests/test_dispatch.py:1755: BlockingIOError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.32s ===============================

```
- ok: `tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child` fails on base `main` too -- the bug is not already fixed upstream
```
emit, stopping):
        inflight["TICKET-999"] = other_rec
        calls["n"] += 1
        if calls["n"] == 1:
>           raise BlockingIOError(11, "Resource temporarily unavailable")
E           BlockingIOError: [Errno 11] Resource temporarily unavailable

tests/test_dispatch.py:1755: BlockingIOError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.42s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-umij1b65/base
      Built pipeline @ file:///tmp/pipeline-base-umij1b65/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 04:27:48Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-29 · implementing · todo

**implementing todo list**

1. [x] retry_eagain() in worktree.py, 2 tests
2. [x] route run_cmd() through retry_eagain, 1 test
3. [x] route both subprocess.Popen sites in supervisor.py, 2 tests
4. [x] widen start()'s catch to OSError, wrap child()'s spawn_command call, 1 test
5. [x] route pty.fork() through retry_eagain, 1 test
6. [x] convert 2 run() loop detectors to BaseException, add pinning test
7. [x] run() catches per tick, rewrite repro test body
8. [x] fix 3 stale comments in supervisor.py
9. [x] CLAUDE.md gotcha bullet

### 2026-08-29 · implementing · report · result=ok

**implementing done** (result: `ok`)

All 9 steps done, each committed separately with a RED test verified first.
Findings from `## Summary`:

1. Step 6 converted both loop detectors before step 7's catch, and added
   `test_run_does_not_swallow_a_loop_detector_that_subclasses_baseexception`.
   Verified the guard is falsifiable: widening `run()`'s catch to
   `except BaseException as e:` made that test fail with
   `run() swallowed a BaseException loop detector`; reverted with
   `git checkout -- pipeline/daemon/supervisor.py`.
2. Step 7 rewrote `test_a_transient_blockingioerror_from_tick_must_not_kill_every_inflight_child`,
   keeping the name: `fake_tick` now inserts `TICKET-999` only on call 1 and
   clears `inflight` on call 2, so `once=True` drains.

One deviation from the plan text: step 8's comment fix at `start()`'s
`except PipelineError as e:` handler was made in step 4's commit instead of
step 8's, since both touch the same lines. No behaviour differs from the
plan's wording. Also trimmed one occurrence of the word `retry_eagain` from
a comment in `pipeline/pty/host.py` so
`grep -c retry_eagain pipeline/pty/host.py` reads `2` as the acceptance
criterion requires.

`uv run --group dev pytest -q` -- `452 passed`. Every acceptance criterion
checked individually and passed.

### 2026-08-29 04:37:57Z · implementing · session · session=3b7be058-3d55-4735-a3c5-6dd8e06d6298

`implementing` ran as session `3b7be058-3d55-4735-a3c5-6dd8e06d6298`
- replay: `claude --resume 3b7be058-3d55-4735-a3c5-6dd8e06d6298`
- log: `.project/logs/TICKET-086-implementing-3b7be058.log`
- cost: $2.59 of a $8 cap
- tokens: 30,536 out (1,315 thinking) · 232 in · 9,341,815 cache read · 103,742 cache write

### 2026-08-29 04:37:57Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ executed all 9 plan steps; repro test and full suite (452) pass, every acceptance criterion verified

### 2026-08-29 · review · findings · result=ok

**review pass 1: no blocking findings**

Reviewed the 11 commits `c13660b..068ee19` against `main`. Re-ran the suite:
`452 passed in 32.92s`. Re-ran every acceptance criterion command: `1 passed`,
`2 passed, 13 deselected`, `2 passed`, `2 passed, 69 deselected`, `1 passed`,
`3 passed`, and the four greps print `0`, `2`, `2`, `0`. I did not re-run the
falsifiable mutation: this stage is read-only. The code reads as the plan
specifies and `implementing` reports running it.

Refuted while reviewing: `child()`'s `bail()` after `t.take_lease()` does not
strand a lease -- `escalate()` calls `t.release_lease()`
(`pipeline/daemon/supervisor.py:75`).

1. minor: `.project/decisions/DEC-069.md:32` still reads "`run()` does not
   wrap its `tick()` call". Step 7 made that false. Step 8 scoped the fix to
   `pipeline/daemon/supervisor.py` comments only.
2. minor: the `pty.fork()` retry leaks two fds per retry. When `os.forkpty()`
   raises EAGAIN, `/usr/lib/python3.14/pty.py:78` opens a pty and line 79
   raises from `os.fork()`, leaking `master_fd` and `slave_fd`. Bounded at 6
   fds per interactive spawn, on a path that used to kill the process.
3. minor: `except OSError: return bail(f"spawn failed: {e}")`
   (`pipeline/daemon/supervisor.py:785`) has no test. Step 4's test covers
   the `spawn()` handler at line 862 only.
4. nit: `pipeline run --once` now exits 0 when a tick raises. The failure
   appears only on stdout (`pipeline/daemon/supervisor.py:1444`).

### 2026-08-29 04:43:17Z · review · session · session=314be7d2-29db-4e82-a1bb-84f370066381

`review` ran as session `314be7d2-29db-4e82-a1bb-84f370066381`
- replay: `claude --resume 314be7d2-29db-4e82-a1bb-84f370066381`
- log: `.project/logs/TICKET-086-review-314be7d2.log`
- cost: $2.12 of a $5 cap
- tokens: 18,248 out (10,521 thinking) · 66 in · 1,904,442 cache read · 71,172 cache write

### 2026-08-29 04:43:17Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review: no blocking findings; 452 passed and every acceptance criterion re-run; 4 minor findings appended

### 2026-08-29 04:44:02Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 04:44:02Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/086


Rebasing (1/11)Rebasing (2/11)Rebasing (3/11)Rebasing (4/11)Rebasing (5/11)Rebasing (6/11)Rebasing (7/11)Rebasing (8/11)Rebasing (9/11)Rebasing (10/11)Rebasing (11/11)Successfully rebased and updated refs/heads/ticket/086.
Already up to date.
Updating ce1c424..9f2ba59
Fast-forward
 CLAUDE.md                     |  11 +++
 pipeline/core/worktree.py     |  27 ++++++-
 pipeline/daemon/supervisor.py |  68 +++++++++++-------
 pipeline/pty/host.py          |   6 +-
 tests/test_dispatch.py        | 163 +++++++++++++++++++++++++++++++++++++++++-
 tests/test_pty.py             |  24 +++++++
 tests/test_worktree.py        |  54 ++++++++++++++
 7 files changed, 321 insertions(+), 32 deletions(-)

```

### 2026-08-29 04:44:02Z · merging · decision

decision recorded as `DEC-086`
