---
id: TICKET-032
stage: done
class: bugfix
branch: ticket/032
test_file: tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop
files_declared:
- CLAUDE.md
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: a1f5f95b-f8d0-4373-90b5-92304975da5f
  log: .project/logs/TICKET-032-review-a1f5f95b.log
approved_by: chezzijr
approved_at: '2026-08-21T11:31:32.057810+00:00'
---

## Summary

A merged change to `pipeline/core/` or `pipeline/daemon/` is inert until the
dispatcher process restarts, and nothing says so. The loop keeps running the
modules it imported at start; `_harness_reloader()` (DEC-028) fixes this for
harness *data* and cannot fix it for Python modules.

Observed twice on 2026-08-21: after the 16:38 restart, TICKET-030's gate text
and TICKET-029's and TICKET-026's `transition()` rows were all merged and none
were loaded. The dangerous case is TICKET-026: `pipeline/stages/quick-review.md`
is read per spawn, so a triage agent can return `result: chore` while the loaded
`transition()` has no row for it -- and an unknown `(stage, result)` escalates.

Plan (2026-08-21): detect by module mtime, not by `git rev-parse HEAD`. A new
`_source_watcher()` in `pipeline/daemon/supervisor.py` snapshots the mtimes of
the loaded `pipeline` modules; when one moves, `run()` and `serve()` stop
claiming tickets, reap what is inflight and return, so whatever started the
process runs the merged code. No `importlib.reload()`: the supervisor holds live
child records, an open SQLite handle and registered signal handlers.

One correction to the reproduction test: its final `assert len(seen) == 2` is
unreachable. The bump lands *during* tick 1, so every check after tick 1 sees
it; a prototype exited after tick 1 and reported `AssertionError: expected the
loop to exit after tick 2, got 1 ticks`. Step 1 changes that assertion to
`== 1`. The `Stop`-at-tick-3 mechanism -- the part that fails on unfixed code --
is untouched.

The plan ran as a prototype in the ticket worktree and was reverted: the three
tests reported `3 passed, 24 deselected in 1.08s` and the suite `201 passed in
10.08s`.

Plan validation passed on 2026-08-21, all eight items. The root cause is that
`run()` and `serve()` bind module objects at import; a merged `.py` changes the
file and the process keeps executing what it loaded. DEC-028 and DEC-011 both
permit this plan: it does not touch `_harness_reloader()`, watches
`module.__file__` only, and registers no fd. Step 1's assertion change does not
weaken the reproduction -- `assert len(seen) == 2` is reached only when the fix
works, and the `raise Stop(...)` at tick 3 that fails on unfixed code is
untouched. The riskiest steps are 8 and 9, the edits to the two live loops;
`## Rollback` states the fallback. The regression surface is five
`supervisor.run|serve` call sites in `tests/`, and criteria 4 and 5 cover all
five. One consequence to accept: a `merging` stage that lands a `pipeline/`
change now ends the dispatcher's own loop, and a human runs `pipeline start`
again.

Implemented on 2026-08-21, all 13 plan steps, no deviation: `_source_watcher()`
and `_mtime()` added to `pipeline/daemon/supervisor.py`, both loops edited,
the CLAUDE.md gotcha bullet appended. All three tests pass
(`3 passed, 26 deselected in 1.04s`); full suite `207 passed in 10.08s`; guard
script `guard: all passed`. Committed as `37a81dc`.

Review passed on 2026-08-21, no blocking findings. The diff is the Digest
blocks (A)-(G) verbatim across three files, no drift from `## Plan`. All five
acceptance criteria measured: the three tests `3 passed, 26 deselected in
1.04s`, the DEC-028 reloader tests `3 passed, 12 deselected in 0.03s`, the
suite `207 passed in 9.92s`. The two new tests are not vacuous: with
`_source_watcher` replaced in memory by `lambda: (lambda: None)`, they failed
with `AssertionError: daemon source changed at tick 1, still looping at tick 3`
and `AssertionError: a stale loop never exited`. Both loops return from inside
their `try`, so `run()` reaches `shut_down()` and `serve()` releases every
project lock in its `finally` -- criterion 2. Five nits recorded in the thread
and none of them blocks: the `startswith("pipeline")` prefix match, modules
imported after the snapshot, a stale `serve()` locking new projects, deferred
`done` cleanup, and the new `serve()` test writing the real
`~/.config/pipeline/projects`. One command could not run: the guard's own
allowlist blocks `./pipeline/hooks/test_dangerous_commands.py` for a read-only
stage, and the guard is not in the delta.

## Reproduction

Test: `tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop`

Command:

    uv run --group dev pytest -q tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop

The test replaces `supervisor.tick`, bumps the mtime of
`pipeline/daemon/supervisor.py` by 10s during tick 1, and restores it after.
`run()` keeps looping, so tick 3 raises and the test reports:

    E           AssertionError: dispatcher source changed at tick 1, still looping at tick 3: still running the code it imported at startup

    tests/test_dispatch.py:651: AssertionError
    FAILED tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop
    1 failed in 0.18s

expect: dispatcher source changed at tick 1, still looping at tick 3

## Digest

Files touched: `pipeline/daemon/supervisor.py` (the fix), `tests/test_dispatch.py`
(three tests), `CLAUDE.md` (one gotcha bullet).

Key functions in `pipeline/daemon/supervisor.py`: `run()` (line 933) and
`serve()` (line 974) hold the two loops; `tick()` (line 838) reaps first, then
claims tickets and breaks out of the claim loop when its `stopping()` argument
is true; `_harness_reloader()` (line 903) is the per-tick data reload;
`shut_down()` (line 805) terminates children and releases their leases and runs
in both loops' `finally`.

Entry points: `pipeline run` -> `supervisor.run()` (foreground, one project);
`pipelined` -> `pipeline/daemon/main.py` -> `supervisor.serve()` (every
registered project). Neither is auto-restarted: `cmd_start` in
`pipeline/cli/main.py:249` `Popen`s the daemon once with no supervisor, so the
exit message must tell the human to run `pipeline start` again.

Gotcha 1: `tick()` already takes `stopping`, and uses it only to stop claiming
new tickets while still reaping. Passing `lambda: True` into it is the whole
"stop starting work, finish what is running" mechanism -- no signature change.

Gotcha 2: watch code, never data. Stage prompts (`pipeline/stages/*.md`, read
per spawn) and the harness `.toml` (re-read per tick, DEC-028) already reach a
running loop; ending the loop for those would undo DEC-028.

Gotcha 3: `serve()` wraps its `tick()` call in `except Exception`, so a test
that signals from inside a fake tick must raise a `BaseException` subclass or
serve() swallows it and loops forever.

Gotcha 4: the committed test's `assert len(seen) == 2` cannot pass. Measured,
not assumed: a prototype with the check at the top of `run()`'s loop printed
`dispatcher source changed (pipeline.daemon.supervisor); exiting` and failed
with `AssertionError: expected the loop to exit after tick 2, got 1 ticks`.

Gotcha 5: `supervisor.py` has no `import sys` today. The helper needs one.

Gotcha 6: a test that puts a fake record in `inflight` must clear it before the
loop returns, or `shut_down()` raises `KeyError: 'proc'` in the `finally`.

**(A) the helper, after `_harness_reloader()` in `pipeline/daemon/supervisor.py`**

```python
def _mtime(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return -1.0            # a module file that vanished is a change too


def _source_watcher():
    """The mtimes of the loaded `pipeline` modules, sampled once at the top of
    a loop. `_harness_reloader()` does this for harness *data*; a Python module
    already imported does not change because its file did, so the loop reports
    and ends instead. Never `importlib.reload()`: the supervisor holds live
    child records, an open SQLite handle and registered signal handlers, and
    reloading swaps classes out from under objects that already exist.

    Code only. Stage prompts are read per spawn and the harness `.toml` per
    tick (DEC-028); ending the loop for those would undo that."""
    mods = {n: m.__file__ for n, m in list(sys.modules.items())
            if n.startswith("pipeline") and getattr(m, "__file__", None)}
    snap = {n: _mtime(f) for n, f in mods.items()}

    def changed() -> str | None:
        for n, f in mods.items():
            if _mtime(f) != snap[n]:
                return n
        return None

    return changed
```

**(B) `run()`'s loop in `pipeline/daemon/supervisor.py`**

```python
    stale, moved = _source_watcher(), None

    try:
        while not stopping():
            moved = moved or stale()
            if moved and not inflight:
                print(f"  dispatcher source changed ({moved}) -- ending the "
                      f"loop so a restart runs the merged code")
                return
            worked = tick(project, reload(), inflight, max_parallel, poller,
                          emit, (lambda: True) if moved else stopping)
            if once and not inflight and not worked:
                return  # --once drains the queue, it does not do a single pass
            poller.poll(1 if inflight else interval)
```

**(C) `serve()`'s loop in `pipeline/daemon/supervisor.py`**

```python
    stale, moved = _source_watcher(), None

    try:
        while not stopping():
            moved = moved or stale()
            if moved and not any(states.values()):
                print(f"  dispatcher source changed ({moved}) -- ending the "
                      f"loop so a restart runs the merged code")
                return
            hcfg = reload()
            ...
                try:
                    worked |= tick(proj, hcfg, states[key], max_parallel,
                                   server, store.emitter(key),
                                   (lambda: True) if moved else stopping)
```

**(D) the amended assertion in `tests/test_dispatch.py`**

```python
    assert len(seen) == 1, \
        f"expected the loop to exit at the first tick boundary, got {len(seen)} ticks"
```

**(E) the `serve()` test in `tests/test_dispatch.py`**

```python
def test_a_merged_dispatcher_change_ends_the_daemon_loop_too():
    """`serve()` is `run()`'s loop with `run()`'s defect. Triage covered
    `run()` only."""
    import os
    import tempfile

    from pipeline.daemon import registry
    from pipeline.daemon.server import Server

    src = Path(supervisor.__file__)
    before = src.stat().st_mtime
    tmp = Path(tempfile.mkdtemp())
    d = project()
    store = Store(tmp / "events.db")
    server = Server(store, tmp / "daemon.sock")
    seen, orig_tick = [], supervisor.tick

    class Stop(BaseException):     # serve() catches Exception around tick()
        pass

    def fake_tick(proj, hcfg, *a, **kw):
        seen.append(len(seen))
        if len(seen) == 1:
            os.utime(src, (before + 10, before + 10))   # a merge lands
        if len(seen) >= 3:
            raise Stop("still running the code it imported at startup")
        return False

    supervisor.tick = fake_tick
    registry.register(d)
    try:
        supervisor.serve(0, "fake", 1, store, server, once=False)
    except Stop as e:
        raise AssertionError(
            f"daemon source changed at tick 1, still looping at tick 3: {e}")
    finally:
        supervisor.tick = orig_tick
        os.utime(src, (before, before))
        registry.unregister(d)
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    assert len(seen) == 1, f"expected serve() to exit after tick 1, got {len(seen)}"
```

**(F) the drain test in `tests/test_dispatch.py`**

```python
def test_a_stale_dispatcher_reaps_its_children_before_it_exits():
    """The exit is at a tick boundary with no children running: a stale loop
    stops claiming tickets (`tick()` sees `stopping() is True`) and keeps
    reaping until `inflight` is empty."""
    import os

    src = Path(supervisor.__file__)
    before = src.stat().st_mtime
    d = project()
    seen, flags, orig_tick = [], [], supervisor.tick

    def fake_tick(proj, hcfg, inflight, max_parallel, poller, emit, stopping):
        seen.append(len(seen))
        flags.append(stopping())
        if len(seen) == 1:
            inflight["TICKET-001"] = {"fake": True}   # a child is running
            os.utime(src, (before + 10, before + 10))
        if len(seen) == 2:
            inflight.clear()                          # it finished; shut_down
        if len(seen) >= 4:                            # must not see the fake
            raise AssertionError("a stale loop never exited")
        return False

    supervisor.tick = fake_tick
    try:
        supervisor.run(d, once=False, interval=0, harness_name="fake")
    finally:
        supervisor.tick = orig_tick
        os.utime(src, (before, before))
        shutil.rmtree(d, ignore_errors=True)

    assert len(seen) == 2, f"expected a reaping tick 2, got {len(seen)} ticks"
    assert flags == [False, True], \
        f"a stale loop must stop claiming tickets: stopping() was {flags}"
```

**(G) the gotcha bullet for `CLAUDE.md`, last in the Gotchas list**

```markdown
- **A merged change to the dispatcher's own Python is inert until restart.**
  `_source_watcher()` in `pipeline/daemon/supervisor.py` snapshots the mtimes of
  the loaded `pipeline` modules. When one moves, `run()` and `serve()` stop
  claiming tickets, reap what is inflight and return -- so whatever started them
  runs the merged code. Nothing restarts them: after that message, run
  `pipeline start` (or `pipeline run`) again. Never `importlib.reload()`; live
  child records, an open SQLite handle and signal handlers outlive the modules.
```

## Decisions checked

Grepped `/home/chezzijr/proj/claude-setup/.project/decisions/` for `harness`,
`reload`, `restart`, `mtime`, `import`, `loop`, `serve`, `supervisor`,
`shut_down`, `stopping`, `signal`, `exit`, `lease`. No record there carries a
`superseded-by:` line, so every hit is active.

- DEC-028 (active) is the binding one: the harness `.toml` is re-read per tick,
  and its three properties (unguarded first read, last-good dict on error,
  deduped warning) must survive. This plan does not touch `_harness_reloader()`
  and does not watch data files, so a harness edit still reaches the next tick
  instead of ending the loop.
- DEC-011 (active) owns the select loop's extension points (`watch`/`unwatch`).
  This plan adds no fd and no callback; it reads mtimes inline in the loop body.
- DEC-029, DEC-022, DEC-017, DEC-030 read and not relevant: they constrain
  `transition()` rows, the `✓` marker, and what `tests/test_gate.py` may import.

## Plan

1. In `tests/test_dispatch.py`, change the final assertion of `test_a_merged_dispatcher_change_reaches_the_running_loop` to Digest block (D) -- `== 1`, because the mtime bump lands during tick 1 and no immediate detector can produce a second tick.
2. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop` and confirm it still fails on unfixed code with `AssertionError: dispatcher source changed at tick 1, still looping at tick 3`.
3. Add `test_a_merged_dispatcher_change_ends_the_daemon_loop_too` to `tests/test_dispatch.py` exactly as Digest block (E), directly below the existing test.
4. Add `test_a_stale_dispatcher_reaps_its_children_before_it_exits` to `tests/test_dispatch.py` exactly as Digest block (F), below block (E)'s test.
5. Run `uv run --group dev pytest -q tests/test_dispatch.py -k "merged_dispatcher or stale_dispatcher"` and confirm all three tests fail before the fix.
6. Add `import sys` to the import block of `pipeline/daemon/supervisor.py`, in alphabetical order after `import subprocess`.
7. Add `_mtime()` and `_source_watcher()` to `pipeline/daemon/supervisor.py` exactly as Digest block (A), immediately after `_harness_reloader()`.
8. Edit `run()` in `pipeline/daemon/supervisor.py` to Digest block (B): create the watcher after `_stopper()`, and inside the loop set `moved`, return when `moved and not inflight`, and pass `(lambda: True) if moved else stopping` to `tick()`.
9. Edit `serve()` in `pipeline/daemon/supervisor.py` to Digest block (C): the same three changes, with `any(states.values())` in place of `inflight` and the `tick()` call inside the per-project loop.
10. Run `uv run --group dev pytest -q tests/test_dispatch.py -k "merged_dispatcher or stale_dispatcher"` and confirm the three tests pass.
11. Run `uv run --group dev pytest -q` and confirm the whole suite passes -- `tests/test_dispatch.py` in full, plus `tests/test_harness.py`'s DEC-028 reloader tests.
12. Append the gotcha bullet from Digest block (G) to the end of the "Gotchas, each found the hard way" list in `CLAUDE.md`.
13. Commit `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py` and `CLAUDE.md` as `fix: a dispatcher whose modules moved ends its loop instead of running dead code`.

## Acceptance criteria

- `tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop` passes: `run()` returns after one tick once `pipeline/daemon/supervisor.py`'s mtime moves.
- `tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too` passes: `serve()` returns the same way, and releases each project's lock through its `finally`.
- `tests/test_dispatch.py::test_a_stale_dispatcher_reaps_its_children_before_it_exits` passes: with a child inflight the stale loop still ticks, `tick()` sees `stopping() is True`, and the loop exits only once `inflight` is empty. The test asserts `flags == [False, True]`.
- `tests/test_harness.py::test_a_harness_edit_mid_run_reaches_the_next_tick` and `tests/test_harness.py::test_a_harness_edit_mid_run_reaches_the_daemon_loop_too` still pass: a data edit reaches the next tick and does not end the loop (DEC-028).
- `uv run --group dev pytest -q` reports no failures across `tests/`.

## Decisions

**A dispatcher whose loaded modules moved ends its loop; it never reloads
them.** `_source_watcher()` in `pipeline/daemon/supervisor.py` snapshots the
mtimes of every imported `pipeline` module at the top of `run()` and `serve()`.
When one moves, the loop stops claiming tickets, reaps what is inflight, prints
`dispatcher source changed (<module>) -- ending the loop so a restart runs the
merged code`, and returns. Before this, a merged change to `pipeline/core/` or
`pipeline/daemon/` did nothing until someone restarted the process, and a merged
`transition()` row could make a ticket that used the new feature escalate.

Four things a later change must not undo:

1. No `importlib.reload()`. The supervisor holds live child records, an open
   SQLite handle and registered signal handlers; reloading swaps classes out
   from under objects that already exist. Ending the loop is the boring answer
   and `shut_down()` already leaves a clean state.
2. Code only, never data. Stage prompts are read per spawn and the harness
   `.toml` per tick (DEC-028); watching those would end the loop for a change
   that already reaches it.
3. Stop claiming before exiting. The stale loop passes `lambda: True` as
   `tick()`'s `stopping` argument, which reaps without claiming, and returns
   only when `inflight` (or `any(states.values())` in `serve()`) is empty.
   Returning immediately would SIGTERM live agents through `shut_down()` and
   throw away their work.
4. Detection is mtime, not `git rev-parse HEAD`. HEAD is one `run_cmd` per tick
   and misses an uncommitted or `uv tool install`ed tree; the mtimes of
   `module.__file__` are what the process actually loaded, and they are what
   `tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop`
   drives.

Nothing restarts the dispatcher after this exit. `cmd_start` in
`pipeline/cli/main.py` `Popen`s `pipelined` once and returns; systemd, tmux or a
human runs it again. That is why the message names the condition instead of
just returning.

## Rollback

Revert the one commit (`pipeline/daemon/supervisor.py`, `tests/test_dispatch.py`,
`CLAUDE.md`). Behaviour returns to today's: the loop keeps running the modules it
imported and a merged dispatcher change stays inert until a manual restart.
Nothing else depends on the new helper, no state is persisted, and no frontmatter
or ticket field changes. Symptom to revert for: a loop that exits every tick --
that means the watcher is seeing a file the running code rewrites, and the fix is
to narrow `mods`, not to widen `snap`.

## Thread

### implementing todo
1. [x] fix assertion in existing repro test to `== 1`
2. [x] confirm repro test still fails on unfixed code
3. [x] add `test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
4. [x] add `test_a_stale_dispatcher_reaps_its_children_before_it_exits`
5. [x] confirm all three new/changed tests fail before the fix
6. [x] add `import sys` to supervisor.py
7. [x] add `_mtime()` / `_source_watcher()`
8. [x] edit `run()`
9. [x] edit `serve()`
10. [x] confirm the three tests pass
11. [x] run full suite
12. [x] append CLAUDE.md gotcha bullet
13. [x] commit

### 2026-08-21 · implementing · result=ok

Ran the plan's 13 steps in order.

1. Changed the repro test's final assertion to `== 1`. Confirmed it still fails on unfixed code: `AssertionError: dispatcher source changed at tick 1, still looping at tick 3`.
2. Added `test_a_merged_dispatcher_change_ends_the_daemon_loop_too` and `test_a_stale_dispatcher_reaps_its_children_before_it_exits` to `tests/test_dispatch.py`, exactly as Digest blocks (E) and (F). All three tests failed before the fix:
```
FAILED tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop
FAILED tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too
FAILED tests/test_dispatch.py::test_a_stale_dispatcher_reaps_its_children_before_it_exits
3 failed, 26 deselected in 1.15s
```
3. Added `import sys`, `_mtime()`, `_source_watcher()` to `pipeline/daemon/supervisor.py` exactly as Digest block (A), after `_harness_reloader()`.
4. Edited `run()` and `serve()` exactly as Digest blocks (B) and (C).
5. `uv run --group dev pytest -q tests/test_dispatch.py -k "merged_dispatcher or stale_dispatcher"` -> `3 passed, 26 deselected in 1.04s`.
6. `uv run --group dev pytest -q` -> `207 passed in 10.08s`.
7. `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed` (unaffected by this change, ran per CLAUDE.md).
8. Appended the Digest block (G) gotcha bullet to `CLAUDE.md`'s Gotchas list.
9. Committed `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py`, `CLAUDE.md` as `37a81dc fix: a dispatcher whose modules moved ends its loop instead of running dead code`.

No deviation from the plan.

### 2026-08-21 10:09:25Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 · triage · result=ok

Reproduced. `run()` loops forever on a dispatcher whose source changed under it.

- Test: `tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop`, commit `2d951f5`.
- Failure: `AssertionError: dispatcher source changed at tick 1, still looping at tick 3: still running the code it imported at startup`.
- The test covers `run()` only. `serve()` has the same loop and the same defect; it is not covered.
- The test uses the mtime of `pipeline/daemon/supervisor.py`. It restores the original mtime in a `finally` block, so it leaves the tree unchanged.
- A fix built on `git rev-parse HEAD` will not pass this test. Pick the detector in the plan and say which; if it is HEAD, the plan must also rewrite this test.

Files a fix is likely to touch: `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py`. Not a chore: the detector, the scope (`run()` alone or `serve()` too) and the exit path are open design choices.

### 2026-08-21 10:11:06Z · triage · session · session=d8899714-b651-4283-aac3-e33bfdc11c8b

`triage` ran as session `d8899714-b651-4283-aac3-e33bfdc11c8b`
- replay: `claude --resume d8899714-b651-4283-aac3-e33bfdc11c8b`
- log: `.project/logs/TICKET-032-triage-d8899714.log`

### 2026-08-21 10:11:06Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced: run() keeps looping after its own source changed; failing test committed as 2d951f5

### 2026-08-21 10:17:09Z · planning · note

`planning` was interrupted; lease released

### 2026-08-21 · planning · result=ok

Plan written. Detector: module mtimes, not `git rev-parse HEAD`.

- `_source_watcher()` in `pipeline/daemon/supervisor.py` snapshots the mtimes of
  the loaded `pipeline` modules; `run()` and `serve()` both stop claiming
  tickets and return once `inflight` is empty.
- Scope covers `serve()` as well as `run()`, per the triage note that `serve()`
  has the same defect and no coverage.
- The reproduction test's `assert len(seen) == 2` is unreachable and step 1
  changes it to `== 1`. Measured with a prototype: the check at the top of
  `run()`'s loop printed `dispatcher source changed
  (pipeline.daemon.supervisor); exiting` and the test reported `AssertionError:
  expected the loop to exit after tick 2, got 1 ticks`. The bump lands during
  tick 1, so every check after tick 1 sees it. The `Stop`-at-tick-3 mechanism,
  which is what fails on unfixed code, is untouched.
- Out of scope, noted not fixed: `pipeline start` still `Popen`s the daemon with
  no restart supervisor, so after this exit a human runs it again.

Validated as a throwaway prototype in the ticket worktree, then reverted (`git
status --porcelain` is empty): `3 passed, 24 deselected in 1.08s` for the three
tests, and `201 passed in 10.08s` for `uv run --group dev pytest -q`.

`files_declared`: `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py`,
`CLAUDE.md`.

### 2026-08-21 10:25:17Z · planning · session · session=4e6b86b9-b265-4d36-b2d7-1d289ca80c3a

`planning` ran as session `4e6b86b9-b265-4d36-b2d7-1d289ca80c3a`
- replay: `claude --resume 4e6b86b9-b265-4d36-b2d7-1d289ca80c3a`
- log: `.project/logs/TICKET-032-planning-4e6b86b9.log`

### 2026-08-21 10:25:17Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: module-mtime watcher ends run() and serve() at a tick boundary; step 1 corrects the reproduction test's unreachable `== 2` assertion

### 2026-08-21 10:25:28Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop` fails as required
```

            pass
    
        d = project()
        seen, orig_tick = [], supervisor.tick
    
        def fake_tick(proj, hcfg, *a, **kw):
            seen.append(len(seen))
            if len(seen) == 1:
                os.utime(src, (before + 10, before + 10))  # a merge lands
            if len(seen) >= 3:
                raise Stop("still running the code it imported at startup")
            return False
    
        supervisor.tick = fake_tick
        try:
            supervisor.run(d, once=False, interval=0, harness_name="fake")
        except Stop as e:
>           raise AssertionError(
                f"dispatcher source changed at tick 1, still looping at tick 3: {e}")
E           AssertionError: dispatcher source changed at tick 1, still looping at tick 3: still running the code it imported at startup

tests/test_dispatch.py:651: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop` fails on base `main` too -- the bug is not already fixed upstream
```
        except Stop as e:
>           raise AssertionError(
                f"dispatcher source changed at tick 1, still looping at tick 3: {e}")
E           AssertionError: dispatcher source changed at tick 1, still looping at tick 3: still running the code it imported at startup

tests/test_dispatch.py:651: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-rndlc7h1/base
      Built pipeline @ file:///tmp/pipeline-base-rndlc7h1/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 11ms

```

### 2026-08-21 · plan-validation · result=ok

Plan passes all eight items. Read `pipeline/daemon/supervisor.py`, the
reproduction test, DEC-028, DEC-011 and every `supervisor.run|serve` call site
in `tests/`.

**Root cause.** `run()` and `serve()` bind module objects at import and never
re-read them. A merged `.py` under `pipeline/` changes the file; the process
keeps executing the code it loaded. Python cannot re-execute it in place, so
the only honest fix ends the loop. The plan fixes that, not the test: it exits
at a tick boundary and names the condition on stdout.

**Decision conflict: none.** DEC-028 (active) binds. Its three properties live
in `_harness_reloader()`, which the plan does not touch, and the plan watches
`module.__file__` only -- a harness `.toml` edit still reaches the next tick.
DEC-028's "not chosen: comparing the file's mtime in `spawn()`" rejects an
mtime check on harness *data* as a substitute for reloading it. This plan
checks mtimes on code that cannot be reloaded at all. Different file,
different site, no conflict. DEC-011 (active) freezes `watch(fd, cb)` as the
select loop's extension point; the plan registers no fd and adds no callback.

**Scope.** Steps 1-11 and 13 each trace to a criterion. Step 12 (the CLAUDE.md
gotcha bullet) traces to none. It follows DEC-028, whose `files:` line also
carries CLAUDE.md. In scope by repo convention, not by criterion.

**Criteria are falsifiable.** Traced block (B) against each test by hand:

1. Repro test: iteration 1 ticks and bumps the mtime; iteration 2 sees `moved`
   with `inflight` empty and returns. `len(seen) == 1`. An implementation that
   returned before ticking gives 0 and fails.
2. Block (F): iteration 1 ticks with `stopping() is False` and sets
   `inflight["TICKET-001"]`; iteration 2 sees `moved` but `inflight` is
   non-empty, so it ticks again with `lambda: True` and clears `inflight`;
   iteration 3 returns. `flags == [False, True]` fails for an implementation
   that skips the reaping tick or never passes `lambda: True`.
3. Block (E): `states[key]` is `{}` at the end of iteration 1, so
   `any(states.values())` is False and iteration 2 returns. `len(seen) == 1`.

**Step 1 does not weaken the reproduction.** `assert len(seen) == 2` sits at
`tests/test_dispatch.py:658`, after the loop. It is reached only when the fix
works. The failure on unfixed code comes from `raise Stop(...)` at tick 3,
caught into an `AssertionError` at lines 650-652, and step 1 leaves that
untouched. The gate confirmed the test still fails on base `main`.

**No research left.** Every step names a file, and steps 6-9 name `import
sys`, `_mtime()`, `_source_watcher()`, `run()` and `serve()` with the code to
write. Verified `supervisor.py` has no `import sys` (its imports end at
`import uuid`, line 10) and that `serve()` wraps `tick()` in `except Exception`
(line 1024), which is why block (E) subclasses `BaseException`.

**Riskiest step: 8 and 9, the edits to the two live loops.** `moved` is sticky
(`moved = moved or stale()`), so one spurious mtime move ends the loop
permanently. The plan states the fallback in `## Rollback`: the symptom is a
loop that exits every tick, and the remedy is to narrow `mods`, not to widen
`snap`.

**Regression surface: five call sites, all covered.** A grep for
`supervisor\.(run|serve)\(` over `tests/` returns `tests/test_harness.py` lines
245, 281, 315, 331 and `tests/test_dispatch.py` line 649. The four harness
tests bump no mtime, so `stale()` returns `None` and their tick counts do not
change. Criterion 4 names two of them; criterion 5 covers the other two.
`--once` is untouched: block (B) keeps `if once and not inflight and not
worked: return` in place after `tick()`.

**Blast radius matches `bugfix`:** three files, one new helper, one commit.

One consequence a reviewer must accept, stated by the plan and not hidden: a
`merging` stage that lands any `pipeline/` change on the base branch now ends
the dispatcher's own loop, and `cmd_start` (`pipeline/cli/main.py:249`) does
not restart it. A human runs `pipeline start` again. The exit waits for
`inflight` to drain, so no agent loses work.

### 2026-08-21 10:28:36Z · plan-validation · session · session=03e807ab-7148-4bbb-86f4-a6707ec5eb5e

`plan-validation` ran as session `03e807ab-7148-4bbb-86f4-a6707ec5eb5e`
- replay: `claude --resume 03e807ab-7148-4bbb-86f4-a6707ec5eb5e`
- log: `.project/logs/TICKET-032-plan-validation-03e807ab.log`

### 2026-08-21 10:28:36Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items: root cause is modules bound at import, DEC-028 and DEC-011 permit it, step 1's assertion change does not weaken the reproduction

### 2026-08-21 11:31:32Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 11:44:44Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop` fails as required
```

            pass
    
        d = project()
        seen, orig_tick = [], supervisor.tick
    
        def fake_tick(proj, hcfg, *a, **kw):
            seen.append(len(seen))
            if len(seen) == 1:
                os.utime(src, (before + 10, before + 10))  # a merge lands
            if len(seen) >= 3:
                raise Stop("still running the code it imported at startup")
            return False
    
        supervisor.tick = fake_tick
        try:
            supervisor.run(d, once=False, interval=0, harness_name="fake")
        except Stop as e:
>           raise AssertionError(
                f"dispatcher source changed at tick 1, still looping at tick 3: {e}")
E           AssertionError: dispatcher source changed at tick 1, still looping at tick 3: still running the code it imported at startup

tests/test_dispatch.py:695: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop` fails on base `main` too -- the bug is not already fixed upstream
```
        except Stop as e:
>           raise AssertionError(
                f"dispatcher source changed at tick 1, still looping at tick 3: {e}")
E           AssertionError: dispatcher source changed at tick 1, still looping at tick 3: still running the code it imported at startup

tests/test_dispatch.py:695: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_merged_dispatcher_change_reaches_the_running_loop
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.19s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-cauwwper/base
      Built pipeline @ file:///tmp/pipeline-base-cauwwper/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 11ms

```

### 2026-08-21 11:44:44Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 11:47:40Z · implementing · session · session=51f35492-cb25-4353-b24c-2f0b26f69e85

`implementing` ran as session `51f35492-cb25-4353-b24c-2f0b26f69e85`
- replay: `claude --resume 51f35492-cb25-4353-b24c-2f0b26f69e85`
- log: `.project/logs/TICKET-032-implementing-51f35492.log`

### 2026-08-21 11:47:40Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed all 13 plan steps; added _source_watcher()/_mtime() to supervisor.py, edited run() and serve(), all three tests pass, full suite 207 passed, committed as 37a81dc.

### 2026-08-21 · review · result=ok

No blocking findings. Reviewed `git diff 64206fe..37a81dc`: three files,
`pipeline/daemon/supervisor.py`, `tests/test_dispatch.py`, `CLAUDE.md`. This is
the first review pass, so `## Thread` carries no earlier review findings to
verify resolved.

**The diff matches the Digest blocks.** Blocks (A) through (G) landed verbatim,
including the `import sys` placement of step 6. No drift from `## Plan`.

**All five acceptance criteria pass, measured.**

1. The three tests: `3 passed, 26 deselected in 1.04s`.
2. The DEC-028 reloader tests: `uv run --group dev pytest -q tests/test_harness.py -k "mid_run"` reports `3 passed, 12 deselected in 0.03s`. A harness data edit still reaches the next tick and does not end the loop.
3. The whole suite: `207 passed in 9.92s`.

**The two new tests are not vacuous.** Measured, not assumed. I replaced
`supervisor._source_watcher` with `lambda: (lambda: None)` in memory -- no file
changed -- and ran each test function directly. Both failed:

    AssertionError: daemon source changed at tick 1, still looping at tick 3: still running the code it imported at startup
    AssertionError: a stale loop never exited

Test 1's failure on unfixed code is already recorded by the Tier A gate entry.

**Read the two loops end to end.** `run()`'s `return` at line 1031 sits inside
the `try`, so `shut_down()`, `_restore_signals()` and `lock.close()` still run.
`serve()`'s `return` at line 1081 reaches the `finally` at line 1112, which
calls `release(key)` for every key in `states` -- criterion 2's lock release.
`tick()` line 882 confirms Digest gotcha 1: `stopping()` breaks the claim loop
only, and `reap()` at line 880 runs unconditionally, so `lambda: True` reaps
without claiming.

Findings, none blocking:

1. **nit.** `_source_watcher()` selects modules with `n.startswith("pipeline")`, a prefix match rather than a package match. A future top-level module named `pipelines` or `pipelinex` would be watched. `n == "pipeline" or n.startswith("pipeline.")` is exact. Nothing in the dependency budget matches today.
2. **nit.** A module imported after the snapshot is never watched. `pipeline.tui.app` is the only lazy `pipeline` import (`cmd_tui`), and it runs in its own process, so this changes nothing today.
3. **nit.** A stale `serve()` whose projects are still busy keeps taking `registry.lock()` on newly registered projects it will never claim work for. The `finally` releases them. Wasteful, not wrong.
4. **nit.** A stale loop breaks out of `tick()`'s ticket loop at line 882 before `start()`, so `done`-stage worktree cleanup is deferred to the restart. This is what `## Decisions` item 3 requires, and the restart cleans up.
5. **nit.** `test_a_merged_dispatcher_change_ends_the_daemon_loop_too` calls `registry.register(d)` without redirecting `XDG_CONFIG_HOME`, so it writes the real `~/.config/pipeline/projects` and `serve()` flocks every project the developer has registered. It copies the pre-existing pattern at `tests/test_harness.py:279`; `tests/test_daemon.py:23` is the module that does redirect. The test unregisters in its `finally`, and the run here printed only `watching /tmp/tmp97fzb77p`.

**One thing I could not run.** `./pipeline/hooks/test_dangerous_commands.py`
is blocked for this stage by the guard itself: `Blocked by the pipeline guard
(review): 'test_dangerous_commands.py' is not on the read-only allowlist.` The
guard is not in the delta, and the `implementing` entry reports
`guard: all passed`.

### 2026-08-21 11:51:26Z · review · session · session=a1f5f95b-f8d0-4373-90b5-92304975da5f

`review` ran as session `a1f5f95b-f8d0-4373-90b5-92304975da5f`
- replay: `claude --resume a1f5f95b-f8d0-4373-90b5-92304975da5f`
- log: `.project/logs/TICKET-032-review-a1f5f95b.log`

### 2026-08-21 11:51:26Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review passed, no blocking findings: diff matches Digest (A)-(G), all five criteria measured (207 passed in 9.92s), both new tests proved non-vacuous; five nits recorded

### 2026-08-21 11:51:38Z · verifying · transition · to=merging · result=ok

**verifying -> merging** (result: `ok`)

regression suite exit 0
```
...HEAD
ok  allow [always] cargo build --release
ok  BLOCK [readonly] sed -i s/a/b/ x.py
ok  BLOCK [readonly] echo hi > file.txt
ok  BLOCK [readonly] git commit -am wip
ok  BLOCK [readonly] cp a b
ok  BLOCK [readonly] pip install requests
ok  BLOCK [readonly] mv a b
ok  BLOCK [readonly] python3 -c "open('/tmp/x','a').write(1)"
ok  BLOCK [readonly] git -C . commit -am wip
ok  BLOCK [readonly] pytest 2>out
ok  BLOCK [readonly] pytest >> log.txt
ok  BLOCK [readonly] git worktree add /tmp/x main
ok  BLOCK [readonly] python3 setup.py install
ok  BLOCK [readonly] tee /tmp/x
ok  BLOCK [readonly] curl https://example.com -o /tmp/x
ok  BLOCK [readonly] make install
ok  BLOCK [readonly] cargo run
ok  BLOCK [readonly] npm install
ok  BLOCK [readonly] echo $(whoami)
ok  allow [readonly] pytest -x
ok  allow [readonly] git diff main...HEAD
ok  allow [readonly] grep -rn foo .
ok  allow [readonly] git log --oneline
ok  allow [readonly] cat thing.py
ok  allow [readonly] python3 -m pytest --deselect x
ok  allow [readonly] ls -la
ok  allow [readonly] git show HEAD
ok  allow [readonly] git blame thing.py
ok  allow [readonly] rg evict src/
ok  allow [readonly] pytest -x 2>&1
ok  allow [readonly] find . -name '*.py'
ok  allow [readonly] cargo test
ok  allow [readonly] go test ./...
ok  allow [readonly] git status --porcelain
ok  allow [readonly] wc -l thing.py
ok  allow [readonly] python3 -m unittest
ok  allow [readonly] git diff main...HEAD | head -50
ok  end-to-end exit codes

guard: all passed

```

### 2026-08-21 11:51:39Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/032


Already up to date.
Updating de7ad39..37a81dc
Fast-forward
 CLAUDE.md                     |   7 +++
 pipeline/daemon/supervisor.py |  48 ++++++++++++++++-
 tests/test_dispatch.py        | 120 ++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 173 insertions(+), 2 deletions(-)

```

### 2026-08-21 11:51:39Z · merging · decision

decision recorded as `DEC-032`
