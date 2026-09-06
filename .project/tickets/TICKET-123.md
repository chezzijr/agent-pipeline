---
id: TICKET-123
stage: done
class: bugfix
branch: ticket/123
test_file: tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage
files_declared:
- CLAUDE.md
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 14
  plan_files: 3
  no_result: 0
  rebase_conflicts: 1
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 0515b3e0-bd84-49d7-8ebb-b535f401d390
  replay: claude --resume 0515b3e0-bd84-49d7-8ebb-b535f401d390
  log: .project/logs/TICKET-123-review-0515b3e0.log
  cost_usd: 1.5107489999999995
approved_by: chezzijr
approved_at: '2026-09-06T12:57:20.589926+00:00'
---

## Summary

A source-change drain waits forever on an inflight stage that never exits.
`run()` (pipeline/daemon/supervisor.py:1658) and `serve()` (:1724) end the
drain only when nothing is inflight, and `reap()` (:1362) pops a record only
when its child exits. Observed 2026-09-06: daemon pid 214565 held one child
for 8h20m, 7h38m past that child lease expiry, while `pipeline status` still
answered.

The plan bounds the drain by the lease. Extract `stop_child()` from
`shut_down()`, add `drain_expired()` -- terminate an inflight child whose
`rec["meta"].lease_active()` is false -- and `drain_notice()` -- one
`notice_once()` line naming what the drain holds -- then call both from `run()`
and `serve()` while `moved` is true. 14 steps over
pipeline/daemon/supervisor.py, tests/test_dispatch.py and CLAUDE.md. Three new
tests join the committed repro. This complies with DEC-032 ruling 3: a child
whose lease is still live is waited for, not killed.

`plan-validation` passed the plan on all eight items, Tier A and Tier B.
`implementing` executed all 14 steps and committed three times: `417a969` the
`stop_child()` extraction, `4d7f321` the source-change drain fix, `28137be` the
daemon drain plus the CLAUDE.md sentence.

`review` passed the delta `1ec448b..28137be` with no blocking findings, and
re-measured every acceptance criterion it can run:

1. `uv run --group dev pytest -q` -> `601 passed in 60.73s (0:01:00)`.
2. `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`.
3. `grep -c 'def stop_child' pipeline/daemon/supervisor.py` -> `1`.
4. `grep -c 'outlives its lease during that drain' CLAUDE.md` -> `1`.

`review` raised three findings and refuted all three, each against a
`file:line`; they are in its thread entry with the refutations. Nobody has
measured the mutation half of five criteria ("and it fails with X against a
wrong implementation") on this branch: `planning`, `plan-validation` and
`review` are all read-only or guard-blocked from a write.

## Reproduction

Test: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage`
Command: `uv run --group dev pytest -q tests/test_dispatch.py -k test_source_change_drain_completes_with_a_stuck_inflight_stage`

Failure output:
```
AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever
```
expect: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

`run()`'s loop only ends a source-change drain when `moved and not inflight`
(pipeline/daemon/supervisor.py:1658). `reap()` only pops an inflight record
when `rec["proc"].poll() is not None` (line 1362) -- a stage whose child never
exits is never popped, so `inflight` never empties and the loop ticks forever
instead of returning for a restart. `serve()` has the identical `moved and not
any(states.values())` check at line 1724.

## Digest

What changed since the rejected plan: `plan-validation` failed that plan on one
item, regression surface. `drain_notice()` and `drain_expired()` raised
`KeyError` on the bare record
`tests/test_dispatch.py::test_a_stale_dispatcher_reaps_its_children_before_it_exits`
plants, and making them total was not enough -- that record has no `meta`, so a
`meta`-only check terminated it and ended `run()` one tick early. This plan
discriminates on `proc`, not on `meta`: `drain_expired()` skips a record with no
`proc` (nothing to terminate, and `stop_child()` has no handle to use), and a
record with a `proc` but no `meta` still counts as expired. That keeps the
committed repro's record -- `{"proc": stuck, "stage": "implementing"}`,
`tests/test_dispatch.py:1368` -- terminated, and leaves the stale-dispatcher
record `{"fake": True}` (`tests/test_dispatch.py:1325`) untouched. Every read of
`stage` moves to `rec.get("stage", "?")`, in `stop_child()` and in
`drain_notice()`.

Measurement provenance, two sources. Measured by THIS planning run on `1ec448b`
with a clean worktree: `uv run --group dev pytest -q` printed
`1 failed, 597 passed in 61.47s (0:01:01)`, the one failure being this ticket's
repro, and `./pipeline/hooks/test_dangerous_commands.py` exited 0 printing
`guard: all passed`. NOT re-measured here: the suite with the change applied.
The guard refuses a write from `planning` -- `Blocked by the pipeline guard
(planning)` on the edit attempt -- so this run could not build it. The earlier
planning run did build and run it on the pre-recut tree, and each new test
failed against the wrong implementation its criterion names.

Files this change touches:
- `pipeline/daemon/supervisor.py` -- the two drain checks, a new reaper, a new notice.
- `tests/test_dispatch.py` -- the committed repro plus three new tests.
- `CLAUDE.md` -- one sentence on the bullet that documents `_source_watcher()`.

Key functions, all in `pipeline/daemon/supervisor.py` unless named otherwise:
- `run()` lines 1656-1661: `moved = moved or stale()`, then `if moved and not inflight:` prints and returns.
- `serve()` lines 1722-1727: the same shape against `if moved and not any(states.values()):`.
- `reap()` line 1362: pops a record only when `rec["proc"].poll() is not None`, which is why a child that never exits is never popped.
- `shut_down()` line 1375: per record it terminates, waits 10s, kills, waits 5s, calls `close_child(rec)`, unlinks `prompt`/`settings`/`mcp`, loads the ticket, releases the lease, appends a note, saves, prints the stopped line. It reads `rec["proc"]` at line 1380 and `rec["stage"]` at lines 1401 and 1406 by subscript today; the extraction moves both to `.get()`. Its `project` parameter is unused by the body.
- `close_child()` line 376 is already total on a bare record: it reads `pipe`, `poller` and `fh` with `.get()`, so `stop_child()` can call it on a record carrying only `proc` and `stage`.
- `start()` line 890: `rec["path"], rec["tid"], rec["meta"], rec["before"] = path, tid, t, None`, under the comment that `meta` is not optional. `spawn()` line 397 builds the record with `proc` and `stage` already in it. Nothing re-assigns `rec["meta"]` and nothing renews a lease while its child is inflight, so `rec["meta"].lease_active()` answers the lease question with no disk read.
- `Ticket.lease_active()` (`pipeline/core/ticket.py:700`) is total: `now() < lease_expiry(expires)`, and `LEASE_MINUTES = 30` at `pipeline/core/ticket.py:20`.
- `notice_once(message, *key)` (`pipeline/core/__init__.py:28`) is already imported at `pipeline/daemon/supervisor.py:16`; `reset_notices()` (`pipeline/core/__init__.py:42`) is its test seam.

Entry points: `run()` behind `pipeline run`, `serve()` behind `pipelined`. Tests drive both by assigning `supervisor.tick` and bumping the mtime of `Path(supervisor.__file__)`. `serve()` passes `states[key]` as `tick()`'s third positional argument, so one fake `tick()` shape plants an inflight record in either loop.

Gotchas:
- `drain_all(inflight)` already exists at `pipeline/daemon/supervisor.py:191`. It pumps every child's stdout pipe before a blocking call and has nothing to do with a source-change drain. `drain_expired()` and `drain_notice()` are new names beside it; do not fold any of the three together.
- A runaway-loop detector raised from a fake `tick()` must subclass `BaseException`. Both loops catch `Exception` around `tick()`.
- The fake records these tests plant carry no `path` and no `meta`, and one carries no `proc` and no `stage` either. `stop_child()` and `drain_expired()` must be total against all four: `Ticket.load(rec["path"])` raises `KeyError` inside the existing `except Exception: pass`, `proc` and `stage` need `.get()`, and a record with no `proc` must be skipped.
- `shut_down()` in `run()`'s `finally` already terminates the stuck child on the way out -- the repro's captured stdout is `  stopped STUCK (implementing)` -- so a test asserts on how many ticks the loop takes, never on `inflight` after the return.
- The drain block goes ABOVE the `if moved and not inflight:` return, so a record it pops ends the loop on the same iteration.
- `pipeline/daemon/supervisor.py` is not in `machine.FENCED`, so this diff does not park at `awaiting-merge` for the fence.

Step 1 body, for `pipeline/daemon/supervisor.py`:

```python
def stop_child(tid: str, rec: dict, note: str | None = None) -> None:
    """Terminate one child and release its lease. This is `shut_down()`'s
    per-record body, extracted so a source-change drain reaps an expired child
    through the same path -- a second copy of it is how one of the two callers
    later forgets to release a lease.

    Total on a partial record: a failed spawn can leave one with no `proc`, no
    `stage` and no `path`, and raising here would take `run()`'s `finally` down
    and strand every OTHER ticket's lease for 30 minutes.
    """
    proc = rec.get("proc")
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)   # a PtyProc is reaped here or never
            except subprocess.TimeoutExpired:
                pass
    close_child(rec)
    if rec.get("prompt"):
        rec["prompt"].unlink(missing_ok=True)
    if rec.get("settings"):
        rec["settings"].unlink(missing_ok=True)
    if rec.get("mcp"):
        rec["mcp"].unlink(missing_ok=True)
    stage = rec.get("stage", "?")
    try:
        t = Ticket.load(rec["path"])
        t.release_lease()
        t.append(stage, "note",
                 note or f"`{stage}` was interrupted; lease released")
        t.save()
    except Exception:
        pass
    print(f"  stopped {tid} ({stage})")
```

Step 2 body, for `pipeline/daemon/supervisor.py`:

```python
def shut_down(project: Path, inflight: dict) -> None:
    """Terminate children and release their leases. Without this an interrupted
    dispatcher leaves agents writing into worktrees it no longer tracks, and the
    lease expiry later spawns a SECOND agent onto the same stage."""
    for tid, rec in list(inflight.items()):
        stop_child(tid, rec)
    inflight.clear()
```

Step 4 body, for `pipeline/daemon/supervisor.py`:

```python
def drain_expired(inflight: dict) -> None:
    """Bound a source-change drain by the lease. A child whose lease has
    already expired is forfeit -- `start()` treats it that way -- so the drain
    terminates it instead of waiting forever for a child that never exits.

    Two records are skipped. One whose lease is still live is waited for, per
    DEC-032 ruling 3. One with no `proc` is not a running child at all: there
    is nothing to terminate, and popping it would end the drain a tick early.
    """
    for tid, rec in list(inflight.items()):
        if rec.get("proc") is None:
            continue
        meta = rec.get("meta")
        if meta is not None and meta.lease_active():
            continue
        stage = rec.get("stage", "?")
        print(f"  drain: {tid} ({stage}) outlived its lease -- terminating")
        stop_child(tid, rec, f"`{stage}` outlived its lease during a "
                             f"source-change drain; terminated and lease released")
        inflight.pop(tid, None)
```

Step 5 body, for `pipeline/daemon/supervisor.py`:

```python
def drain_notice(project: Path, inflight: dict) -> None:
    """One line naming what a source-change drain is waiting on. Without it the
    drain is silent: the loop stops claiming tickets and nothing says why."""
    if not inflight:
        return
    held = ", ".join(f"{tid} ({rec.get('stage', '?')})"
                     for tid, rec in sorted(inflight.items()))
    notice_once(f"  dispatcher source changed -- draining {len(inflight)} "
                f"inflight stage(s): {held}", "drain", str(project))
```

Step 8 test body, for `tests/test_dispatch.py`:

```python
def test_a_source_change_drain_waits_for_a_child_whose_lease_is_still_active():
    """The bound is the lease, not an unconditional kill. DEC-032 ruling 3
    keeps the drain waiting so a live agent's work is not thrown away, so a
    child whose lease is still active must survive the drain and finish."""
    import os
    import types

    src = Path(supervisor.__file__)
    before = src.stat().st_mtime

    class Stop(BaseException):     # run() catches Exception around tick()
        pass

    d = project()
    seen, killed, orig_tick = [], [], supervisor.tick
    live = types.SimpleNamespace(poll=lambda: None,
                                 terminate=lambda: killed.append("TICKET-001"),
                                 wait=lambda timeout=None: None, kill=lambda: None)
    meta = types.SimpleNamespace(lease_active=lambda: True)

    def fake_tick(proj, hcfg, inflight, *a, **kw):
        seen.append(len(seen))
        if len(seen) == 1:
            inflight["TICKET-001"] = {"proc": live, "stage": "implementing",
                                      "meta": meta}
            os.utime(src, (before + 10, before + 10))   # a merge lands
        if len(seen) == 3:
            inflight.clear()                            # the agent finishes
        if len(seen) >= 5:
            raise Stop("the loop never ended after the child finished")
        return False

    supervisor.tick = fake_tick
    try:
        supervisor.run(d, once=False, interval=0, harness_name="fake")
    except Stop as e:
        raise AssertionError(str(e))
    finally:
        supervisor.tick = orig_tick
        os.utime(src, (before, before))
        shutil.rmtree(d, ignore_errors=True)

    assert killed == [], "the drain terminated a child whose lease is still active"
    assert len(seen) == 3, f"expected the loop to end after tick 3, got {len(seen)}"
```

Step 11 test body, for `tests/test_dispatch.py`:

```python
def test_the_daemon_drain_completes_with_a_stuck_inflight_stage():
    """`serve()` carries `run()`'s drain check against `any(states.values())`,
    so it carries the same defect: a per-project inflight dict that never
    empties parks the daemon while it still answers its socket."""
    import os
    import tempfile
    import types

    from pipeline.daemon import registry
    from pipeline.daemon.server import Server

    src = Path(supervisor.__file__)
    before = src.stat().st_mtime
    tmp = Path(tempfile.mkdtemp())
    d = project()
    store = Store(tmp / "events.db")
    server = Server(store, tmp / "daemon.sock")
    seen, orig_tick = [], supervisor.tick
    stuck = types.SimpleNamespace(poll=lambda: None, terminate=lambda: None,
                                  wait=lambda timeout=None: None, kill=lambda: None)

    class Stop(BaseException):     # serve() catches Exception around tick()
        pass

    def fake_tick(proj, hcfg, inflight, *a, **kw):
        seen.append(len(seen))
        if len(seen) == 1:
            inflight["STUCK"] = {"proc": stuck, "stage": "implementing"}
            os.utime(src, (before + 10, before + 10))   # a merge lands
        if len(seen) >= 5:
            raise Stop("an inflight stage that never exits blocks the drain forever")
        return False

    supervisor.tick = fake_tick
    registry.register(d)
    try:
        supervisor.serve(0, "fake", 1, store, server, once=False)
    except Stop as e:
        raise AssertionError(f"the daemon drain never completed: {e}")
    finally:
        supervisor.tick = orig_tick
        os.utime(src, (before, before))
        registry.unregister(d)
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    assert len(seen) < 5, f"expected the daemon loop to end, got {len(seen)} ticks"
```

Step 12 test body, for `tests/test_dispatch.py`:

```python
def test_a_source_change_drain_names_what_it_waits_on(capsys):
    """The drain was silent: the loop stopped claiming tickets, the log
    stopped, and five tickets sat unworked for eight hours with nothing
    saying why. One line names what the drain is waiting on."""
    import os
    import types

    from pipeline.core import reset_notices

    src = Path(supervisor.__file__)
    before = src.stat().st_mtime
    d = project()
    seen, orig_tick = [], supervisor.tick
    live = types.SimpleNamespace(poll=lambda: None, terminate=lambda: None,
                                 wait=lambda timeout=None: None, kill=lambda: None)
    meta = types.SimpleNamespace(lease_active=lambda: True)

    def fake_tick(proj, hcfg, inflight, *a, **kw):
        seen.append(len(seen))
        if len(seen) == 1:
            inflight["TICKET-001"] = {"proc": live, "stage": "implementing",
                                      "meta": meta}
            os.utime(src, (before + 10, before + 10))   # a merge lands
        if len(seen) == 2:
            inflight.clear()                            # the agent finishes
        return False

    reset_notices()
    supervisor.tick = fake_tick
    try:
        supervisor.run(d, once=False, interval=0, harness_name="fake")
    finally:
        supervisor.tick = orig_tick
        os.utime(src, (before, before))
        shutil.rmtree(d, ignore_errors=True)

    out = capsys.readouterr().out
    assert "draining 1 inflight stage(s): TICKET-001 (implementing)" in out, out
```

## Decisions checked

DEC-032 is active and binding here, and this plan complies with it. Its ruling 3 says the stale loop stops claiming tickets and returns only when `inflight` (or `any(states.values())`) is empty, because returning immediately would SIGTERM live agents through `shut_down()` and throw away their work. The plan keeps that return condition unchanged: it empties `inflight` only of children whose lease has ALREADY expired, whose run `start()` already treats as forfeit. Rulings 1 and 4 are untouched -- no `importlib.reload()`, and detection stays mtime-based.

DEC-121 landed on `main` after the last plan was written, and it does not constrain this change. It rules that `serve()` returns `source_changed` and that its `finally` carries the reason on `daemon_stop`, and that `pipelined --restart-on-upgrade` re-execs only on that return, bounded to 3 restarts in 60s. This plan touches neither the return value, the event, nor `restart_budget()`. It makes the `source_changed` return REACHABLE when a child never exits, which is the case the restart already expects.

DEC-110 rules that `pipeline resume` refuses on `lease_active()` AND `holder_alive()`. The drain reaper checks the lease only: the holder of an inflight lease is the running dispatcher itself, so `holder_alive()` is always true there and would defeat the bound.

DEC-086 rules that a loop detector raised from a fake `tick()` must subclass `BaseException`, and that a repro asserts on what the next tick sees rather than on `inflight` after `shut_down()`. Both new loop tests follow it.

DEC-011 rules that an expiry is read through `Ticket.lease_active()` and never off `lease["expires"]`, which survives an expiry. `drain_expired()` calls `meta.lease_active()`, so it complies.

DEC-069 is superseded by DEC-094, so it binds nothing here; it is cited as history. It records that a failing `tick()` must not reach `finally: shut_down(project, inflight)` and SIGTERM every other ticket's agent. Steps 6 and 10 put the drain call above that `try:`, which is why `drain_notice()` and `drain_expired()` are total rather than free to raise `KeyError`.

Grep terms used over `.project/decisions/`: `drain`, `source change`, `_source_watcher`, `shut_down`, `lease`, `lease_active`, `restart`, `reload`, `mtime`, `SIGTERM`, `terminate`, `superseded-by`. They also matched DEC-028, DEC-048, DEC-055, DEC-061 and DEC-105; each was read and none constrains a source-change drain.

## Plan

1. In `pipeline/daemon/supervisor.py`, add `def stop_child(tid: str, rec: dict, note: str | None = None) -> None:` directly above `shut_down()` at line 1375, copying it verbatim from the "Step 1 body" block in `## Digest`: it is the current per-record body of `shut_down()` with `proc` and `stage` read through `.get()`, with `close_child(rec)` and the three unlinks unchanged, and with the appended note defaulting to the existing f-string.
2. In `pipeline/daemon/supervisor.py`, reduce `shut_down(project, inflight)` to the "Step 2 body" block in `## Digest` -- a loop calling `stop_child(tid, rec)` then `inflight.clear()` -- keeping its signature and docstring; `project` stays an unused parameter because both call sites pass it positionally.
3. Run `uv run --group dev pytest -q tests/test_dispatch.py` and confirm the extraction is inert -- the only failure is `test_source_change_drain_completes_with_a_stuck_inflight_stage` -- then commit `pipeline/daemon/supervisor.py` as `refactor(TICKET-123): extract stop_child() from shut_down()`.
4. In `pipeline/daemon/supervisor.py`, add `drain_expired(inflight)` directly below `shut_down()`, copying the function verbatim from the "Step 4 body" block in `## Digest`: it skips a record whose `proc` is missing and a record whose `meta` reports `lease_active()`, and otherwise prints one line, calls `stop_child()` with the drain note, and pops the record.
5. In `pipeline/daemon/supervisor.py`, add `drain_notice(project, inflight)` directly below `drain_expired()`, copying the function verbatim from the "Step 5 body" block in `## Digest`: it returns on an empty `inflight`, else builds `held` from `sorted(inflight.items())` with `rec.get('stage', '?')` and calls `notice_once()` keyed on the string "drain" and `str(project)`.
6. In `pipeline/daemon/supervisor.py`, insert into `run()` between `moved = moved or stale()` at line 1657 and `if moved and not inflight:` at line 1658 a block of `if moved:` followed by `drain_notice(project, inflight)` and `drain_expired(inflight)`, leaving the existing return and its printed line unchanged.
7. Run `uv run --group dev pytest -q tests/test_dispatch.py -k 'drain or stale_dispatcher'` and confirm `test_source_change_drain_completes_with_a_stuck_inflight_stage` and `test_a_stale_dispatcher_reaps_its_children_before_it_exits` both pass, so the drain neither hangs on the stuck child nor pops the bare record the second test plants.
8. Append `test_a_source_change_drain_waits_for_a_child_whose_lease_is_still_active` to the end of `tests/test_dispatch.py`, copying its body verbatim from the "Step 8 test body" block in `## Digest`.
9. Run `uv run --group dev pytest -q tests/test_dispatch.py -k drain`, confirm the three drain tests pass, and commit `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py` as `fix(TICKET-123): bound the source-change drain by the inflight lease`.
10. In `pipeline/daemon/supervisor.py`, insert into `serve()` between `moved = moved or stale()` at line 1723 and `if moved and not any(states.values()):` at line 1724 a block of `if moved:` followed by `for key, st in list(states.items()):` and, indented under it, `drain_notice(Path(key), st)` and `drain_expired(st)`, leaving the existing return unchanged.
11. Append `test_the_daemon_drain_completes_with_a_stuck_inflight_stage` to the end of `tests/test_dispatch.py`, copying its body verbatim from the "Step 11 test body" block in `## Digest`.
12. Append `test_a_source_change_drain_names_what_it_waits_on` to the end of `tests/test_dispatch.py`, copying its body verbatim from the "Step 12 test body" block in `## Digest`.
13. In `CLAUDE.md`, append two sentences to the bullet at line 265 that begins with the bolded sentence "A merged change to the dispatcher's own Python is inert until restart.": "The drain is bounded by the lease: `drain_expired()` terminates an inflight child that outlives its lease during that drain, through the same `stop_child()` path `shut_down()` uses, so one stage that never exits cannot park the dispatcher while it still answers its socket (TICKET-123). A child whose lease is still live is waited for, exactly as DEC-032 requires."
14. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, confirm no failures remain against the measured baseline, and commit `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py` and `CLAUDE.md` as `fix(TICKET-123): bound the daemon drain too, and document the lease bound`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py -k test_source_change_drain_completes_with_a_stuck_inflight_stage` exits 0, where today it raises `AssertionError: source-change drain never completed with a stuck inflight stage`.
- `tests/test_dispatch.py::test_a_stale_dispatcher_reaps_its_children_before_it_exits` still passes, and it fails with `expected a reaping tick 2, got 1 ticks` against a `drain_expired()` that pops the bare record it plants.
- `tests/test_dispatch.py::test_a_source_change_drain_waits_for_a_child_whose_lease_is_still_active` passes, and it fails with `the drain terminated a child whose lease is still active` against a `drain_expired()` that kills unconditionally.
- `tests/test_dispatch.py::test_the_daemon_drain_completes_with_a_stuck_inflight_stage` passes, and it fails with `the daemon drain never completed` while `serve()` still waits on `any(states.values())` alone.
- `tests/test_dispatch.py::test_a_source_change_drain_names_what_it_waits_on` passes, and it fails when `run()` calls `drain_expired()` without `drain_notice()`.
- `uv run --group dev pytest -q` reports no failures at all, and its passed count is the baseline count plus the three tests steps 8, 11 and 12 add. Measured baseline on 1ec448b: `1 failed, 597 passed in 61.47s (0:01:01)`, the single failure being this ticket's repro.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0 and prints `guard: all passed`.
- `grep -c 'def stop_child' pipeline/daemon/supervisor.py` prints `1`, so `shut_down()` and the drain share one teardown path.
- `grep -c 'outlives its lease during that drain' CLAUDE.md` prints `1`.

## Decisions

**A source-change drain is bounded by the lease, not by a timer and not by an unconditional kill.** `run()` and `serve()` call `drain_notice()` and `drain_expired()` only while `moved` is true, and `drain_expired()` terminates an inflight child only when `rec["meta"].lease_active()` is false. This keeps DEC-032 ruling 3 intact: both loops still return only on an empty `inflight` or `states`, and a child whose lease is live is still waited for, so its work is not thrown away. The worst case falls from unbounded -- observed 8h20m on a child whose lease had expired 7h38m earlier -- to the lease that remains, at most `LEASE_MINUTES`.

**The reaper runs during a drain only.** Reaping an expired lease in normal operation would terminate any agent that overruns 30 minutes, and would bypass the crash-recovery path in `start()`, which charges `lease_expiries` and is what bounds that loop under invariant 3. A future change that calls `drain_expired()` unconditionally from `tick()` breaks both.

**`drain_expired()` discriminates on `proc`, and counts a missing `meta` as expired.** A record with no `proc` is not a running child: there is nothing to terminate, `stop_child()` has no handle to use, and popping it would end the drain one tick early. That is what `tests/test_dispatch.py::test_a_stale_dispatcher_reaps_its_children_before_it_exits` catches: it plants a record carrying only a `fake` key and asserts the loop still takes its reaping tick. A record that HAS a `proc` and no `meta` is terminated, because every record `start()` builds carries a `meta` -- the field is documented as not optional at `pipeline/daemon/supervisor.py:890` -- so one without it cannot be shown to hold a live lease, and holding the loop open for it is the failure this ticket reports. Do not reorder the two checks.

**The lease is read from `rec["meta"]`, the pre-spawn snapshot, never from the ticket file.** The snapshot is dispatcher-owned, so a stage that rewrites its own ticket cannot extend its own drain, and the check costs no disk read per tick.

**`stop_child()` is the one teardown path, and it is total on a partial record.** `shut_down()` and `drain_expired()` both go through it, so the lease release, the `close_child()` drain, the three temp-file unlinks and the printed stopped line cannot drift apart. It reads `proc` and `stage` with `.get()` and `path` inside the existing `except Exception: pass`, because a record left half-built by a failed spawn must not take the loop down through the `finally` in `run()`. Its `note` argument is what distinguishes the two callers in the ticket thread; a second copy of that block is how one of them later forgets to release a lease.

**`drain_expired()` and `drain_notice()` are not `drain_all()`.** `drain_all()` at `pipeline/daemon/supervisor.py:191` pumps every inflight child's stdout pipe before a blocking call, and it runs on every tick. The two new functions run only while `moved` is true. Merging them on the strength of the shared word would put a lease check on every tick, which the ruling above forbids.

## Rollback

Revert the three commits from steps 3, 9 and 14, in reverse order. That restores the inlined body of `shut_down()` and both `if moved and not ...` checks, and the drain hangs again on a child that never exits. Revert the code and the tests together: the tests from steps 8, 11 and 12 fail against the reverted `pipeline/daemon/supervisor.py`. This change writes nothing that survives a revert -- no schema, no config key, no new file.

## Thread

### 2026-09-06 07:07:54Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-06 · triage · result=ok

Reproduced. `run()`'s source-change drain (pipeline/daemon/supervisor.py:1640)
ends only when `moved and not inflight`. `reap()` (line 1350) pops an inflight
record only when its child's `proc.poll()` returns non-None. A stage whose
child never exits is never popped, so `inflight` never empties and the loop
ticks forever instead of returning. `serve()` has the same check at line 1702
against `states`.

Test: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage`.
It fakes `tick()` to plant a never-polling `proc` in `inflight` after tick 1,
bumps the supervisor module's mtime to simulate a merge, and fails at tick 5
with the loop still running.

`result: ok`, not `chore`: the fix needs a design choice (a grace period vs.
an unconditional kill of inflight children once `moved` is true, and whether
`serve()`'s per-project drain needs the same treatment), not just an edit.

Expected files: pipeline/daemon/supervisor.py (both `run()` and `serve()`).

### 2026-09-06 07:09:51Z · triage · session · session=a156dea7-744c-47b5-b52d-582f2b85c164

`triage` ran as session `a156dea7-744c-47b5-b52d-582f2b85c164`
- replay: `claude --resume a156dea7-744c-47b5-b52d-582f2b85c164`
- log: `.project/logs/TICKET-123-triage-a156dea7.log`
- cost: $0.59 of a $3 cap
- tokens: 8,146 out (2,333 thinking) · 56 in · 1,318,269 cache read · 60,306 cache write

### 2026-09-06 07:09:51Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: run()'s source-change drain loops forever when reap() never pops a stuck inflight stage.


### 2026-09-06 · planning · result=ok

Plan written. The drain bound is the lease: not a timer, not an unconditional
kill.

Triage flagged the design choice -- a grace period versus an unconditional kill,
and whether `serve()` needs the same treatment. The ticket text settles it, so I
asked nothing: it requires that a child which outlives its lease during a drain
cannot hold the loop open, so `drain_expired()` terminates exactly those
children, and both loops call it. A wall-clock grace period was rejected because
the committed repro drives four ticks with near-zero elapsed time, so a timer
would never fire there.

DEC-032 ruling 3 binds this change and the plan complies: both loops still return
only on an empty `inflight`, and a live-lease child is still waited for. DEC-110
explains why `holder_alive()` is not checked here -- the holder of an inflight
lease is the running dispatcher, so that half is always true.

Checked the plan against the Tier A structural rules offline: 14 steps, no prose
line in `## Plan`, every step cites a declared file, 8 criteria, and DEC-032,
DEC-086 and DEC-110 all resolve to records.

Measured baseline: `uv run --group dev pytest -q` prints
`1 failed, 577 passed in 63.02s (0:01:03)`, the failure being this ticket repro.

### 2026-09-06 07:21:52Z · planning · session · session=336787b0-8963-48e7-8092-a005f58d9ff4

`planning` ran as session `336787b0-8963-48e7-8092-a005f58d9ff4`
- replay: `claude --resume 336787b0-8963-48e7-8092-a005f58d9ff4`
- log: `.project/logs/TICKET-123-planning-336787b0.log`
- cost: $4.33 of a $10 cap
- tokens: 56,219 out (26,185 thinking) · 76 in · 3,182,634 cache read · 133,025 cache write

### 2026-09-06 07:21:52Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: bound the source-change drain by the inflight lease in run() and serve().

### 2026-09-06 10:49:15Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage` fails as required
```
UCK"] = {"proc": stuck_proc, "stage": "implementing"}
                os.utime(src, (before + 10, before + 10))  # a merge lands
            if len(seen) >= 5:
                raise Stop("an inflight stage that never exits blocks the drain forever")
            return False
    
        supervisor.tick = fake_tick
        try:
            supervisor.run(d, once=False, interval=0, harness_name="fake")
        except Stop as e:
>           raise AssertionError(
                f"source-change drain never completed with a stuck inflight stage: {e}")
E           AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

tests/test_dispatch.py:1189: AssertionError
----------------------------- Captured stdout call -----------------------------
  stopped STUCK (implementing)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 4.29s ===============================

```
- ok: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage` fails on base `main` too -- the bug is not already fixed upstream
```
ge: {e}")
E           AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

tests/test_dispatch.py:1189: AssertionError
----------------------------- Captured stdout call -----------------------------
  stopped STUCK (implementing)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 4.61s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-sfudv0l4/base
      Built pipeline @ file:///tmp/pipeline-base-sfudv0l4/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 49ms

```

### 2026-09-06 · plan-validation · result=fail

**Regression surface: fail.** Steps 5 and 6 break
`tests/test_dispatch.py::test_a_stale_dispatcher_reaps_its_children_before_it_exits`
(line 1271). Its fake `tick()` plants `inflight["TICKET-001"] = {"fake": True}`
(line 1289) and bumps the source mtime, so the next iteration runs the drain on
a record with no `stage`, no `proc` and no `meta`. `drain_notice()` builds
`f"{tid} ({rec['stage']})"` and raises `KeyError: 'stage'`. Step 6 puts that
call above the `try:` that wraps `tick()` (supervisor.py:1645), so the KeyError
leaves `run()` through `finally: shut_down(...)`. `stop_child()` then raises
`KeyError: 'proc'` on the same record. Reading both keys with `.get()` still
fails the test: no `meta` counts as expired, the drain terminates the record,
and `run()` returns at iteration 2, where the test asserts `len(seen) == 2` and
`flags == [False, True]`. The digest anticipated the missing `path` and `meta`
keys for `stop_child()` only. Baseline `1 failed, 577 passed` includes this
test passing, so criterion 5 is unsatisfiable as planned.

Passing items:
1. Root cause: `reap()` pops only on `proc.poll()`, and the drain returns only
   on an empty `inflight`, so a child that never exits holds the loop. The plan
   empties `inflight` of forfeit children; it does not weaken the return check.
2. Decision conflict: DEC-032 ruling 3 binds and the plan complies -- both loops
   still return on empty, and a live-lease child is waited for. DEC-086 binds
   the two new loop tests; both detectors subclass `BaseException`.
   DEC-110's `holder_alive()` half is correctly excluded.
3. Scope: every step maps to a criterion. Steps 1-3 to `grep -c 'def
   stop_child'`, 13 to the CLAUDE.md grep, 4-12 to the four named tests.
4. Falsifiable criteria: each names the wrong implementation it fails against.
   The step 8 test fails on `killed == []` against an unconditional kill; the
   step 11 test fails at 5 ticks against `serve()` unchanged.
5. No research left: every step names a function and a file; steps 8, 11 and 12
   carry full test bodies.
6. Riskiest step: 10, `serve()`'s per-project drain. Fallback is step 3's
   inertness check plus `## Rollback`'s three-commit revert.
7. Blast radius: `bugfix`, 3 files, 14 steps, one new function pair and one
   extraction. Matches the class.

long: seven passing items each need their reason, and the failing one needs its
evidence quoted.

I did not run `pytest`. This stage is read-only and the guard blocks it, so the
`KeyError` finding rests on reading supervisor.py:1637-1660 and
tests/test_dispatch.py:1271-1308, not on an execution.

### 2026-09-06 10:52:34Z · plan-validation · session · session=b0ea98b7-a807-458e-b9a6-9db718d201d6

`plan-validation` ran as session `b0ea98b7-a807-458e-b9a6-9db718d201d6`
- replay: `claude --resume b0ea98b7-a807-458e-b9a6-9db718d201d6`
- log: `.project/logs/TICKET-123-plan-validation-b0ea98b7.log`
- cost: $1.35 of a $3 cap
- tokens: 14,789 out (8,199 thinking) · 34 in · 805,666 cache read · 57,810 cache write

### 2026-09-06 10:52:34Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ Bad plan: drain_notice() and drain_expired() raise KeyError on the bare inflight record test_a_stale_dispatcher_reaps_its_children_before_it_exits plants, then terminate it.

### 2026-09-06 · planning · result=ok

Replanned against the gate's one finding. The drain reaper now discriminates on
`proc`, not on `meta`: a record with no `proc` is not a running child, so
`drain_expired()` skips it. That leaves `{"fake": True}` in
`test_a_stale_dispatcher_reaps_its_children_before_it_exits` untouched and its
reaping tick intact, while the repro's `{"proc": stuck_proc, "stage":
"implementing"}` is still terminated, because a record with a `proc` and no
`meta` counts as expired. `stop_child()` and `drain_notice()` read `stage` with
`rec.get("stage", "?")`, so neither raises `KeyError` above `run()`'s `try:`.

I built the whole change, ran it, then reverted it; `git status` is clean at
d6a886a. Measured with the change: `581 passed in 61.25s (0:01:01)`. Measured
without it: `1 failed, 577 passed in 59.98s`, the failure being the repro.
`./pipeline/hooks/test_dangerous_commands.py` exited 0 both ways. I also ran
each new test against the wrong implementation its criterion names, and each
failed there -- the unconditional kill, `serve()` unchanged, and
`drain_expired()` without `drain_notice()`.

DEC-032 ruling 3 still binds and the plan still complies. DEC-069 is superseded
by DEC-094; I cite it as history for why the drain call must not raise above
the `try:`.

Out of scope, noted not fixed: `shut_down()`'s `project` parameter is unused.

### 2026-09-06 11:00:57Z · planning · session · session=820f5a12-90cd-40a3-a236-803dd1095185

`planning` ran as session `820f5a12-90cd-40a3-a236-803dd1095185`
- replay: `claude --resume 820f5a12-90cd-40a3-a236-803dd1095185`
- log: `.project/logs/TICKET-123-planning-820f5a12.log`
- cost: $2.99 of a $10 cap
- tokens: 38,389 out (8,309 thinking) · 58 in · 2,062,934 cache read · 99,801 cache write

### 2026-09-06 11:00:57Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Replanned: the drain reaper skips a record with no `proc`, so it bounds the stuck child without breaking the stale-dispatcher test.

### 2026-09-06 11:02:04Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage` fails as required
```
UCK"] = {"proc": stuck_proc, "stage": "implementing"}
                os.utime(src, (before + 10, before + 10))  # a merge lands
            if len(seen) >= 5:
                raise Stop("an inflight stage that never exits blocks the drain forever")
            return False
    
        supervisor.tick = fake_tick
        try:
            supervisor.run(d, once=False, interval=0, harness_name="fake")
        except Stop as e:
>           raise AssertionError(
                f"source-change drain never completed with a stuck inflight stage: {e}")
E           AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

tests/test_dispatch.py:1189: AssertionError
----------------------------- Captured stdout call -----------------------------
  stopped STUCK (implementing)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 4.27s ===============================

```
- ok: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage` fails on base `main` too -- the bug is not already fixed upstream
```
ge: {e}")
E           AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

tests/test_dispatch.py:1189: AssertionError
----------------------------- Captured stdout call -----------------------------
  stopped STUCK (implementing)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 4.59s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-8us0yzoz/base
      Built pipeline @ file:///tmp/pipeline-base-8us0yzoz/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 63ms

```
- ok: DEC-069 is superseded -- history, not binding

### 2026-09-06 · plan-validation · result=ok

**Tier B: PASS on all eight items.** I read every function and test the plan
cites; I ran nothing (pytest is not in `[readonly] allow`).

1. Root cause: the drain's exit condition depends on the child. `reap()` pops
   only on `rec["proc"].poll() is not None` (supervisor.py:1350), so a child
   that never exits makes `moved and not inflight` (:1640) unreachable. The
   plan moves that condition onto something the dispatcher owns, the lease. It
   fixes the loop, not the test.
2. Decision conflict: DEC-032 ruling 3 binds and the plan complies. Both
   returns stay unchanged, and `drain_expired()` skips a live-lease record.
   `start()` (:821-826) already treats an expired lease as forfeit and charges
   `lease_expiries`, so the plan matches existing semantics. DEC-110 excludes
   `holder_alive()` correctly: the holder is the running dispatcher.
3. Scope: 14 steps over 3 files, all traceable. Steps 1-3 to the `stop_child`
   grep, 4-12 to the four named tests, 13 to the CLAUDE.md grep.
4. Falsifiable: I traced each criterion's wrong implementation. A `meta`-only
   `drain_expired()` pops `{"fake": True}` (tests/test_dispatch.py:1289) and
   returns at iteration 1, printing exactly `expected a reaping tick 2, got 1
   ticks` (:1307).
5. No research left: every step names a file, a function and a line.
6. Riskiest step: 10, `serve()`'s per-project drain. `## Rollback` states the
   fallback -- revert the step 3, 9 and 14 commits in reverse order.
7. Regression surface: `test_a_stale_dispatcher_reaps_its_children_before_it_exits`
   (:1271) survives -- `{"fake": True}` has no `proc`, so `drain_expired()`
   skips it, and `drain_notice()` reads `rec.get('stage', '?')`.
   `test_ctrl_c_during_a_suite_does_not_crash_on_its_missing_prompt` (:266)
   and `tests/test_pty.py:123` cover the `stop_child()` extraction.
8. Blast radius: 3 files for a `bugfix`, proportionate.

Unverified, resting on the plan's measurement alone: every suite number. I
would have run `uv run --group dev pytest -q tests/test_dispatch.py -k 'drain
or stale_dispatcher'`; the guard blocks it in this stage.

Out of scope, noted not fixed: a drained child's lease is released and no
counter is charged, so the next dispatcher run respawns that stage fresh.
`shut_down()` already does this for every interrupted child, so the drain adds
no new case.

### 2026-09-06 11:05:30Z · plan-validation · session · session=163cb0c7-0b63-4ff3-97d4-09360e065985

`plan-validation` ran as session `163cb0c7-0b63-4ff3-97d4-09360e065985`
- replay: `claude --resume 163cb0c7-0b63-4ff3-97d4-09360e065985`
- log: `.project/logs/TICKET-123-plan-validation-163cb0c7.log`
- cost: $1.53 of a $3 cap
- tokens: 15,398 out (7,712 thinking) · 38 in · 979,897 cache read · 64,909 cache write

### 2026-09-06 11:05:30Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight items: the proc discrimination keeps the stale-dispatcher record untouched, and every criterion names a wrong implementation it fails against.

### 2026-09-06 11:42:43Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-06 12:01:38Z · revalidating · transition · to=triage · result=conflict

**revalidating -> triage** (result: `conflict`)

rebase onto base conflicted; branch recut from base:
```
$ git rebase main || exit 3
/home/chezzijr/.local/share/uv/tools/pipeline/bin/python3 -P -m pipeline --project /home/chezzijr/proj/agent-pipeline gate TICKET-123 --findings /home/chezzijr/proj/agent-pipeline/.project/logs/TICKET-123-gate-ae34a414.json

Rebasing (1/1)
Auto-merging tests/test_dispatch.py
CONFLICT (content): Merge conflict in tests/test_dispatch.py
error: could not apply d6a886a... test(TICKET-123): reproduce source-change drain never completing with a stuck inflight stage
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply d6a886a... # test(TICKET-123): reproduce source-change drain never completing with a stuck inflight stage

d6a886a test(TICKET-123): reproduce source-change drain never completing with a stuck inflight stage
HEAD is now at 01eed4f chore(TICKET-121): record the finished ticket

```

### 2026-09-06 · triage · result=ok

Recut branch onto `main` (01eed4f) and recommitted the repro test as
`1ec448b test(TICKET-123): reproduce source-change drain never completing
with a stuck inflight stage`.

`uv run --group dev pytest -q tests/test_dispatch.py -k
test_source_change_drain_completes_with_a_stuck_inflight_stage` fails:
```
AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever
```
expect: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

`test_a_stale_dispatcher_reaps_its_children_before_it_exits` still passes.
TICKET-121 shifted the drain checks in `pipeline/daemon/supervisor.py` from
lines 1640/1702 to 1658/1724; the plan's line numbers are stale and need a
re-check before editing. No other content changed; plan, digest and decisions
still apply as written.

### 2026-09-06 12:03:00Z · triage · session · session=1a6c3a88-373f-468d-8a36-addd9c64cb53

`triage` ran as session `1a6c3a88-373f-468d-8a36-addd9c64cb53`
- replay: `claude --resume 1a6c3a88-373f-468d-8a36-addd9c64cb53`
- log: `.project/logs/TICKET-123-triage-1a6c3a88.log`
- cost: $0.42 of a $3 cap
- tokens: 4,264 out (308 thinking) · 32 in · 767,958 cache read · 56,061 cache write

### 2026-09-06 12:03:00Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Recut branch and recommitted the repro test; run()'s drain still hangs on a stuck inflight child.

### 2026-09-06 · planning · result=ok

Plan re-issued on the recut branch. The design is unchanged from the plan the
gate passed; every line number and the suite baseline are re-measured on
`1ec448b`.

Refreshed references in `pipeline/daemon/supervisor.py`: the drain check in
`run()` 1640 -> 1658, the one in `serve()` 1702 -> 1724, `reap()` 1350 -> 1362,
`shut_down()` 1363 -> 1375, `close_child()` 367 -> 376, and the `meta`
assignment in `start()` 887 -> 890. In `tests/test_dispatch.py`: the bare
planted record 1289 -> 1325, the repro's planted record 1284 -> 1368.

New baseline, measured here on a clean worktree:
```
1 failed, 597 passed in 61.47s (0:01:01)
```
The single failure is
`tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage`.
`./pipeline/hooks/test_dangerous_commands.py` exits 0 and prints `guard: all passed`.

I did not rebuild the change on this branch. The guard refuses a write from
`planning`: `Blocked by the pipeline guard (planning)`. The `581 passed` figure
from the earlier planning run is dropped, and no criterion rests on it.

Two additions to the plan. `drain_all()` (`pipeline/daemon/supervisor.py:191`)
already exists and pumps child pipes every tick; `## Digest` and `## Decisions`
now say it is not `drain_expired()`. DEC-121 landed since the last plan and is
cited in `## Decisions checked`; it does not constrain this change.

Out of my stage, noted only: the guard blocks a heredoc whose body contains a
backtick span that is not valid shell, e.g. a quoted pytest summary line, so a
stage editing a markdown ticket through Bash hits it.

### 2026-09-06 12:13:17Z · planning · session · session=79ff3b58-360a-40ca-83f7-1ccafd5f9ba5

`planning` ran as session `79ff3b58-360a-40ca-83f7-1ccafd5f9ba5`
- replay: `claude --resume 79ff3b58-360a-40ca-83f7-1ccafd5f9ba5`
- log: `.project/logs/TICKET-123-planning-79ff3b58.log`
- cost: $3.87 of a $10 cap
- tokens: 48,501 out (14,153 thinking) · 76 in · 2,997,720 cache read · 115,918 cache write

### 2026-09-06 12:13:17Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan re-issued on the recut branch: same design, every line number and the suite baseline re-measured on 1ec448b.

### 2026-09-06 12:14:24Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage` fails as required
```
["STUCK"] = {"proc": stuck, "stage": "implementing"}
                os.utime(src, (before + 10, before + 10))   # a merge lands
            if len(seen) >= 5:
                raise Stop("an inflight stage that never exits blocks the drain forever")
            return False
    
        supervisor.tick = fake_tick
        try:
            supervisor.run(d, once=False, interval=0, harness_name="fake")
        except Stop as e:
>           raise AssertionError(
                f"source-change drain never completed with a stuck inflight stage: {e}")
E           AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

tests/test_dispatch.py:1378: AssertionError
----------------------------- Captured stdout call -----------------------------
  stopped STUCK (implementing)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 4.28s ===============================

```
- ok: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage` fails on base `main` too -- the bug is not already fixed upstream
```
ge: {e}")
E           AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

tests/test_dispatch.py:1378: AssertionError
----------------------------- Captured stdout call -----------------------------
  stopped STUCK (implementing)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 4.69s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-e_1dv6xf/base
      Built pipeline @ file:///tmp/pipeline-base-e_1dv6xf/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 59ms

```
- ok: DEC-069 is superseded -- history, not binding

### 2026-09-06 · plan-validation · result=ok

**Tier B: PASS on all eight items.** Every line number the plan cites is
correct on `1ec448b`.

1. Root cause. The drain has no bound. `run()` returns only on `moved and not
   inflight` (supervisor.py:1658) and `reap()` pops only on
   `rec["proc"].poll() is not None` (:1362), so a child that never exits keeps
   `inflight` non-empty forever. The plan adds the missing bound at the return
   check; it does not make the test pass another way.
2. Decisions. DEC-032 ruling 3 reads "returns only when `inflight` (or
   `any(states.values())` in `serve()`) is empty" -- the plan keeps that
   condition and pops only a child whose lease already expired. DEC-121
   constrains the return value, the event and `restart_budget()`; the plan
   touches none of the three. DEC-110 governs `cmd_resume`; the drain's
   lease-only check is right because `take_lease(f"{stage}-{os.getpid()}")`
   (:882) makes the dispatcher its own holder. DEC-011:136 does say
   `lease_active()`, never `lease["expires"]`. DEC-086's `BaseException` rule
   is met by all three new loop tests.
3. Scope. Every step traces to a criterion. Steps 3, 7, 9 and 14 are runs and
   commits, not new scope.
4. Criteria. Each of the five test criteria names the wrong implementation it
   fails against. Both greps are structural and neither is vacuous.
5. No research left. Four bodies are verbatim, both insert points are line
   numbers, and I re-measured 1657/1658, 1723/1724, 1375, 890, 376 and 191.
6. Riskiest step: 6 and 10, the two call-site inserts -- a wrong reaper kills a
   live agent or ends the loop one tick early. Fallback stated: step 7 runs
   both guard tests before the new tests exist, and step 3 isolates the
   refactor in its own revertable commit.
7. Regression surface, traced against every existing caller.
   `test_a_stale_dispatcher_reaps_its_children_before_it_exits` plants
   `{"fake": True}` (tests/test_dispatch.py:1325), which has no `proc`, so
   `drain_expired()` skips it and the reaping tick 2 still happens.
   `test_a_merged_dispatcher_change_reaches_the_running_loop` and the four
   `serve()` source-change tests plant no inflight record, so both new
   functions iterate nothing. `shut_down(d, {"TICKET-001": rec})`
   (tests/test_dispatch.py:273) passes a full `start()` record, so the
   subscript-to-`.get()` change is inert for it.
8. Blast radius. `bugfix`, three files, two new functions and one extraction.
   Proportionate. `pipeline/daemon/supervisor.py` is not in `machine.FENCED`,
   as the plan states.

Two cautions, neither a scored finding. The criterion `grep -c 'outlives its
lease during that drain' CLAUDE.md` counts lines, so a wrap inside that
36-character phrase prints `0` against a correct edit -- keep it on one line.
`test_a_source_change_drain_names_what_it_waits_on` carries no `Stop` guard, so
an implementation that never ends the loop hangs it instead of failing it; the
wrong implementation its criterion names does terminate and does fail.

Unverified, one item: I did not execute the three new tests. `uv` is not on the
read-only allowlist. I would have run `uv run --group dev pytest -q
tests/test_dispatch.py -k 'drain or stale_dispatcher'`. Their pass and fail
behaviour rests on my trace of each loop's tick count, not on a run.

### 2026-09-06 12:18:24Z · plan-validation · session · session=2381db56-ecf8-461b-aed4-dba1dd211dcd

`plan-validation` ran as session `2381db56-ecf8-461b-aed4-dba1dd211dcd`
- replay: `claude --resume 2381db56-ecf8-461b-aed4-dba1dd211dcd`
- log: `.project/logs/TICKET-123-plan-validation-2381db56.log`
- cost: $1.75 of a $3 cap
- tokens: 17,725 out (7,897 thinking) · 44 in · 1,233,017 cache read · 69,079 cache write

### 2026-09-06 12:18:24Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ All eight items pass: the root cause is the unbounded drain, DEC-032 ruling 3 is complied with, and every cited line number re-measured correct.

### 2026-09-06 12:57:20Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-06 12:58:29Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage` fails as required
```
["STUCK"] = {"proc": stuck, "stage": "implementing"}
                os.utime(src, (before + 10, before + 10))   # a merge lands
            if len(seen) >= 5:
                raise Stop("an inflight stage that never exits blocks the drain forever")
            return False
    
        supervisor.tick = fake_tick
        try:
            supervisor.run(d, once=False, interval=0, harness_name="fake")
        except Stop as e:
>           raise AssertionError(
                f"source-change drain never completed with a stuck inflight stage: {e}")
E           AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

tests/test_dispatch.py:1378: AssertionError
----------------------------- Captured stdout call -----------------------------
  stopped STUCK (implementing)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 4.27s ===============================

```
- ok: `tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage` fails on base `main` too -- the bug is not already fixed upstream
```
ge: {e}")
E           AssertionError: source-change drain never completed with a stuck inflight stage: an inflight stage that never exits blocks the drain forever

tests/test_dispatch.py:1378: AssertionError
----------------------------- Captured stdout call -----------------------------
  stopped STUCK (implementing)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_source_change_drain_completes_with_a_stuck_inflight_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 4.66s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-xq0goojk/base
      Built pipeline @ file:///tmp/pipeline-base-xq0goojk/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 61ms

```
- ok: DEC-069 is superseded -- history, not binding

### 2026-09-06 12:58:30Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-06 · implementing · todo

**implementing todo list**

1. [x] Add `stop_child()`, extracted from `shut_down()`.
2. [x] Reduce `shut_down()` to call `stop_child()`.
3. [x] Run tests, confirm extraction inert, commit refactor.
4. [x] Add `drain_expired(inflight)`.
5. [x] Add `drain_notice(project, inflight)`.
6. [x] Wire drain calls into `run()`.
7. [x] Run drain/stale tests, confirm both pass.
8. [x] Add test: drain waits for live lease.
9. [x] Run drain tests, commit fix.
10. [x] Wire drain calls into `serve()`.
11. [x] Add test: daemon drain completes with stuck inflight stage.
12. [x] Add test: drain names what it waits on.
13. [x] Document lease bound in CLAUDE.md.
14. [x] Run full suite + guard, commit docs+tests.

### 2026-09-06 · implementing · report

**All 14 plan steps executed; three commits.**

1. `417a969` refactor: extract `stop_child()` from `shut_down()`. Ran
   `tests/test_dispatch.py`: `1 failed, 94 passed`, the one failure being the
   ticket's own repro -- extraction inert.
2. `4d7f321` fix: bound the source-change drain (`drain_expired()`,
   `drain_notice()`, wired into `run()`, plus the "waits for a live lease"
   test). `tests/test_dispatch.py -k drain` and `-k stale_dispatcher`: 3
   passed.
3. `28137be` fix: bound the daemon drain in `serve()` too, plus the two
   remaining tests and the CLAUDE.md sentence.

Full suite: `uv run --group dev pytest -q` -> `601 passed in 61.14s` (baseline
597 passed + 1 repro now passing + 3 new tests = 601, matches criterion).
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`.
`grep -c 'def stop_child' pipeline/daemon/supervisor.py` -> `1`.
`grep -c 'outlives its lease during that drain' CLAUDE.md` -> `1`. No
deviation from the plan.

### 2026-09-06 13:02:51Z · implementing · session · session=6649ed95-5ba7-4f30-92b0-b9d172522961

`implementing` ran as session `6649ed95-5ba7-4f30-92b0-b9d172522961`
- replay: `claude --resume 6649ed95-5ba7-4f30-92b0-b9d172522961`
- log: `.project/logs/TICKET-123-implementing-6649ed95.log`
- cost: $0.93 of a $8 cap
- tokens: 13,731 out (166 thinking) · 86 in · 2,673,870 cache read · 63,700 cache write

### 2026-09-06 13:02:51Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Bounded the source-change and daemon drains by the inflight lease; all 14 plan steps done, 3 commits, full suite 601 passed.

### 2026-09-06 · review · result=ok

**No blocking findings on the delta `1ec448b..28137be`.**

The diff is 3 files: `pipeline/daemon/supervisor.py` (+80/-28),
`tests/test_dispatch.py` (+135), `CLAUDE.md` (+1/-1). Every plan step landed
as written. I found no drift from `## Plan`.

Measured here on `28137be`, clean worktree:

1. `uv run --group dev pytest -q` -> `601 passed in 60.73s (0:01:00)`.
2. `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`.
3. `grep -c 'def stop_child' pipeline/daemon/supervisor.py` -> `1`.
4. `grep -c 'outlives its lease during that drain' CLAUDE.md` -> `1`.

Three findings I raised and then refuted:

1. "`drain_expired()` pops the bare record and ends `run()` a tick early" --
   refuted at `pipeline/daemon/supervisor.py:1435`, which skips a record with
   no `proc`; `test_a_stale_dispatcher_reaps_its_children_before_it_exits`
   (`tests/test_dispatch.py:1307`) passes.
2. "`meta` is re-snapshotted mid-run, so a stage extends its own drain" --
   refuted: `meta` is written only at spawn,
   `pipeline/daemon/supervisor.py:890` and `:973`. Nothing else writes it.
3. "`serve()` passes the wrong key type to `drain_notice()`" -- refuted:
   `states` is keyed on `str(p)` at `pipeline/daemon/supervisor.py:1802`, and
   the call wraps it in `Path(key)`.

Two non-blocking notes:

1. `drain_notice()` prints once per process through `notice_once()`, so its
   held list does not update as records drain. That is the plan's design.
2. `start()` reads `r["meta"]` by subscript at
   `pipeline/daemon/supervisor.py:861`. A record with no `meta` raises there.
   Pre-existing, outside this delta, unreachable from records `start()` builds.

I did not re-measure the mutation half of five criteria ("and it fails with X
against a wrong implementation"). This stage is read-only.

### 2026-09-06 13:06:50Z · review · session · session=0515b3e0-bd84-49d7-8ebb-b535f401d390

`review` ran as session `0515b3e0-bd84-49d7-8ebb-b535f401d390`
- replay: `claude --resume 0515b3e0-bd84-49d7-8ebb-b535f401d390`
- log: `.project/logs/TICKET-123-review-0515b3e0.log`
- cost: $1.51 of a $5 cap
- tokens: 12,515 out (5,257 thinking) · 48 in · 1,199,070 cache read · 59,706 cache write

### 2026-09-06 13:06:50Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the delta 1ec448b..28137be: no blocking findings; suite 601 passed, guard all passed, both greps print 1.

### 2026-09-06 13:07:55Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-06 13:07:56Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/123


Current branch ticket/123 is up to date.
Already up to date.
Updating 01eed4f..28137be
Fast-forward
 CLAUDE.md                     |   2 +-
 pipeline/daemon/supervisor.py | 108 +++++++++++++++++++-------
 tests/test_dispatch.py        | 173 ++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 255 insertions(+), 28 deletions(-)

```

### 2026-09-06 13:07:56Z · merging · decision

decision recorded as `DEC-123`
