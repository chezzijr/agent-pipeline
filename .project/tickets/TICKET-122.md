---
id: TICKET-122
stage: done
class: bugfix
branch: ticket/122
test_file: tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back
files_declared:
- README.md
- pipeline/cli/client.py
- pipeline/tui/app.py
- tests/test_daemon.py
- tests/test_tui.py
counters:
  plan_validation_attempts: 1
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 23
  plan_files: 5
  no_result: 0
  rebase_conflicts: 1
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 0dd64526-439a-463b-8203-94807f55b293
  replay: claude --resume 0dd64526-439a-463b-8203-94807f55b293
  log: .project/logs/TICKET-122-review-0dd64526.log
  cost_usd: 1.4627229999999998
approved_by: chezzijr
approved_at: '2026-09-06T12:57:20.435186+00:00'
---

## Summary

`pipeline tui` stayed on file rows forever once its daemon went away:
`PipelineApp.client` was assigned once in `__init__`. The fix adds
`socket_dead()` to `pipeline/cli/client.py` -- positive evidence only, so
`daemon: timed out` from a busy daemon keeps its client, its subscription and
its PTY attach (DEC-061, DEC-062) -- plus `_reconnect()`, `_close()`,
`_start_stream()` and `_reattach()` in `pipeline/tui/app.py`, where `_rows()`
now assigns `rows` and returns once, at the bottom (DEC-121). Five new tests.
Committed as `e16f2ac`; no code has changed since.

`review` passed the delta on pass 1 and on pass 2. All 12 acceptance criteria
pass on `e16f2ac`. `uv run --group dev pytest -q` -> `602 passed in 57.75s`.

Caveat for the next suite run: `test_pipelined_execs_only_for_a_source_change_inside_budget`
(`tests/test_daemon.py:1128`, from TICKET-121) reads ambient
`PIPELINE_UPGRADE_RESTARTS` and fails when it is set. That is what `verifying`
hit. Unset both `PIPELINE_UPGRADE_*` vars before running.

Four advisories carry forward, none blocking. The two `review` thread entries
hold the evidence for each.

## Reproduction

Test: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back`

Command: `uv run --group dev pytest -q tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back`

Failure output:

    assert 'batch' == 'interactive'

      - interactive
      + batch

    AssertionError: TUI never reconnected once the daemon was reachable again

expect: AssertionError: TUI never reconnected once the daemon was reachable again

Commit: 421ca51 on branch ticket/122.

## Digest

- Files this plan touches: `pipeline/cli/client.py` (the classifier), `pipeline/tui/app.py` (the fix), `tests/test_tui.py` (three tests), `tests/test_daemon.py` (one test), `README.md` (the TUI paragraph).
- Every line number below was re-read on 421ca51, the recut branch. The recut moved them: `pipeline/tui/app.py` is about 8 lines longer than when this plan was first written, and `README.md` about 55.
- `PipelineApp.__init__` (`pipeline/tui/app.py:235-257`) assigns `self.client` once. `self.stream` (`pipeline/tui/app.py:239`) is the subscription's own connection, assigned by `_subscribe()` from a worker thread.
- `_rows()` (`pipeline/tui/app.py:301-320`) is the only caller of `ls`. It ASSIGNS `rows` and returns at the bottom, because `self.daemon_down = rows is None` and `self.daemon_note = ...` (`pipeline/tui/app.py:315-317`) sit between the daemon branch and the file fallback. `_carry()` (`pipeline/tui/app.py:322-334`) restores `running`/`mode` onto a file row from the last daemon answer. `refresh_tree()` (`pipeline/tui/app.py:336-337`) has 8 callers in the file, so anything added there runs on every key action too.
- Evidence that a socket is dead, and where it comes from: `Client.request()` (`pipeline/cli/client.py:36-51`) raises `PipelineError(f"daemon: {e}") from e` for an `OSError`/`ValueError`, so `err.__cause__.errno` is `EPIPE` for a broken pipe and `ECONNRESET` for a reset, while a `socket.timeout` is a `TimeoutError` whose `errno` is `None` and whose message is `timed out`. The EOF case -- the daemon closed its end mid-request -- raises `PipelineError("daemon closed the connection without replying")` (`pipeline/cli/client.py:51`) with no `__cause__` at all, so its own message is the only evidence there. Both channels are needed; neither alone covers both.
- `connect()` (`pipeline/cli/client.py:70-78`) returns a `Client` or `None`; it catches `FileNotFoundError`, `ConnectionRefusedError`, `PermissionError` and `OSError` and never raises. `Client.path` exists and `clone()` uses it (`pipeline/cli/client.py:63`).
- `on_unmount()` (`pipeline/tui/app.py:289-299`) already holds the shutdown-then-close loop a reconnect needs. Extract it as `_close(*clients)` instead of writing a second copy.
- `_subscribe()` (`pipeline/tui/app.py:409-426`) is `@work(thread=True, exclusive=True)`. A second call cancels the first worker, but a thread parked in `recv` wakes only on `sock.shutdown()`, which is why `_close()` shuts down before it closes.
- `_detach()` (`pipeline/tui/app.py:538-549`) clears `attached`, `pty_id`, `pty_screen`, `pty_writer`, the queued keystrokes and raw mode. Call it before dropping a stream: `pty_id` numbers frames on that socket.
- Gotcha, and the reason the first plan was rejected: `_paint()`'s re-attach branch (`pipeline/tui/app.py:364-372`) needs `old.get(sel, {}).get("mode") != "interactive"`. Across a reconnect the mode is `"interactive"` on both sides, so that branch never fires and the attach needs explicit restoring. `_pty()` also returns False while `self.stream is None` (`pipeline/tui/app.py:523`), and the new stream is assigned from a worker thread, so the restore lands one refresh later, not on the reconnecting one.
- Gotcha, and the reason step 14 changed from the approved wording: an early `return self.client.request("ls", ...)` skips `pipeline/tui/app.py:315-317`, so the status bar keeps a stale `daemon_down` and a stale `daemon_note` (the daemon-stopped reason DEC-121 put there) after a successful reconnect. The rewrite assigns `rows` and falls through to those two lines.
- Gotcha: call `client_mod.connect(...)` through the module. `tests/test_tui.py:603` patches `pipeline.cli.client.connect`, and a `from pipeline.cli.client import connect` binds a name that patch cannot reach. `tests/test_tui.py:13` already imports the module as `client_mod`.
- Gotcha: `tests/test_tui.py` does not override `XDG_RUNTIME_DIR` (`tests/test_daemon.py:23` and `tests/test_pty.py:18` do). An unpatched `connect()` therefore reaches the operator's real `/tmp/pipeline-<uid>/daemon.sock`, and a live daemon answers it. Every test whose `ls` fails must pin `connect`, including the existing `Flaky` test at `tests/test_tui.py:544`.
- Gotcha: `FakeClient.clone()` (`tests/test_tui.py:83`) raises `OSError`, so `_subscribe()` never sets `self.stream` under test. A test that needs a stream assigns `app.stream = FakeStream()` itself, exactly as `tests/test_tui.py:673` does. `FakeStream` is defined at `tests/test_tui.py:648` and its `ops()` at `tests/test_tui.py:662`.
- Gotcha: `tests/test_daemon.py` already imports `socket`, `shutil`, `tempfile`, `Path` and `PipelineError` (`tests/test_daemon.py:7-27`), so the new unit test adds no import beyond `Client, socket_dead`.
- Gotcha: a file row reports `mode: None` and `running: None` (`pipeline/daemon/server.py:138,147`), never `"batch"`/`False`.
- Entry point: `cmd_tui()` in `pipeline/cli/main.py` builds `PipelineApp(connect(), ...)`, so a TUI started before the daemon holds `client=None` forever -- the same assignment-once defect, and the same code path covers it.
- Baselines re-measured on 421ca51 in this worktree: `uv run --group dev pytest -q tests/test_tui.py` prints `1 failed, 43 passed in 12.12s`, and `uv run --group dev pytest -q` prints `1 failed, 597 passed in 57.78s`. The one failure is this ticket's repro test, `assert 'batch' == 'interactive'` at `tests/test_tui.py:613`. Both totals moved with the recut: the earlier plan measured `42 passed` and `560 passed` on ecad420.

## Decisions checked

- DEC-062 (active) -- `running`/`mode` are `None` when nobody answered, `_carry()` keeps the last daemon answer, and one timed-out `ls` must not make a live interactive stage unreachable. This is the record the first plan broke. `socket_dead()` is the compliance: a timed-out `ls` is not evidence of a dead socket, so the client, the subscription and the attach all survive it, and `test_a_timed_out_ls_keeps_the_client_and_its_pty_attach` fails if that stops being true.
- DEC-061 (active) -- running the Tier A gate inline made the daemon answer nothing for the length of a `test_one`, and the TUI showed `daemon: timed out`. It records that a daemon which answers nothing for seconds at a time is a normal state of a LIVE daemon, which is why a timeout must not read as death. It also rejected raising the client's 5s timeout, so that toast stays reachable.
- DEC-059 (active) -- an interactive stage is gated on a client being subscribed, not on the socket existing. This plan drops one subscription and starts another, so it re-subscribes on the same refresh that adopts the new client. The window with no watcher belongs to a daemon that is already gone: a live daemon never loses its watcher here, because a live daemon's error never reads as dead.
- DEC-121 (active) -- the daemon records WHY it stopped as a field on `daemon_stop`, and the TUI reads it back through `daemon_notice()` into `self.daemon_note`. That note is computed in `_rows()` from `rows is None`, which is why step 14 assigns `rows` instead of returning early: a reconnect that skipped those lines would leave "the daemon stopped for an upgrade" on screen after the new daemon answered.
- DEC-021 (active) -- raw mode is app-level state. `_detach()` clears it, and `_reconnect()` calls `_detach()` before it drops the stream, so a reconnect leaves raw mode off rather than typing into a socket that is gone.
- DEC-011 (active) -- the socket protocol is frozen. This plan adds no op and no field; it opens a second connection with the ops already there.
- Grep terms over `.project/decisions/`: `connect`, `fallback`, `subscri`, `tui`, `client`, `reconnect`, `timeout`, `timed out`, `errno`. DEC-039, DEC-055, DEC-063, DEC-073, DEC-096, DEC-107 and DEC-116 came back on those terms and none constrains this change: they cover logs, geometry, panes, once-per-process notices and `pipeline ls` selectors. None of the six records cited above carries a `superseded-by:` line.

## Plan

1. Run `uv run --group dev pytest -q tests/test_tui.py` and confirm the only failure is `test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` in `tests/test_tui.py`, matching the baseline in `## Digest`.
2. Append `test_a_dead_socket_is_told_from_a_daemon_that_is_merely_slow` to `tests/test_daemon.py`, proving the classifier against two real AF_UNIX sockets rather than a hand-written message.
    Docstring: a daemon that exited and a daemon that is busy both fail an `ls`, and only the first may cost the TUI its client, so `socket_dead()` must tell them apart from what `Client.request()` actually raises.
    Body: `from pipeline.cli.client import Client, socket_dead`; `tmp = Path(tempfile.mkdtemp())`; then in a `try:` set `path = tmp / "d.sock"`, `srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)`, `srv.bind(str(path))`, `srv.listen(1)`.
    Dead case: `c = Client(path, timeout=0.3)`; `conn, _ = srv.accept()`; `conn.close()`; then `try: c.request("ls")` with `assert False, "a closed peer answered"` under it, and `except PipelineError as e: assert socket_dead(e), f"a closed socket read as live: {e}"`.
    Live case: `c2 = Client(path, timeout=0.3)`; `conn2, _ = srv.accept()` and never reply on it; then `try: c2.request("ls")` with `assert False, "a silent daemon answered"` under it, and `except PipelineError as e: assert not socket_dead(e), f"a timed-out ls read as a dead socket: {e}"`; then `conn2.close()` and `srv.close()`, and `finally: shutil.rmtree(tmp, ignore_errors=True)`.
3. Run `uv run --group dev pytest -q tests/test_daemon.py::test_a_dead_socket_is_told_from_a_daemon_that_is_merely_slow` and watch it fail with `ImportError: cannot import name 'socket_dead' from 'pipeline.cli.client'`.
4. Add `import errno` to `pipeline/cli/client.py` and, below `connect()`, `DEAD_ERRNOS = frozenset({errno.EPIPE, errno.ECONNRESET, errno.ECONNABORTED, errno.ENOTCONN, errno.EBADF, errno.ESHUTDOWN})`, `DEAD_MARKS = ("broken pipe", "connection reset", "closed the connection", "bad file descriptor", "not connected")`, and `def socket_dead(err: Exception) -> bool:` whose body is the three lines `cause = err.__cause__`, `if isinstance(cause, OSError) and cause.errno in DEAD_ERRNOS: return True`, `return any(m in str(err).lower() for m in DEAD_MARKS)`.
    Its docstring: is this the error of a connection that can never answer again? Positive evidence only -- an error it does not recognise reads as live, because a busy daemon answers nothing for the length of a `test_one` (DEC-061), and throwing its client away costs the TUI a working socket and the PTY attach on it (DEC-062). Two channels, because `request()` fails two ways: it chains the `OSError` it caught, so `__cause__` carries the errno, and the EOF case raises with no cause and only its own message.
5. Run the step-3 command again and confirm `1 passed`, with `pipeline/tui/app.py` still untouched.
6. Add `test_a_timed_out_ls_keeps_the_client_and_its_pty_attach` to `tests/test_tui.py`, after `test_a_failed_ls_keeps_the_last_daemon_answer_for_a_live_interactive_stage`; it passes before the fix and after it, and it is the test that fails the design `plan-validation` rejected.
    Docstring: DEC-062's failure one layer down. A busy daemon answers nothing for the length of a `test_one` (DEC-061) and the 5s deadline reads as `daemon: timed out`; swapping the client there closes the socket the PTY attach lives on.
    Body: `d = make_project()`; a local `class Slow(FakeClient)` setting `self.slow = False` in `__init__`, whose `request` raises `PipelineError("daemon: timed out")` when `op == "ls" and self.slow` and otherwise returns `super().request(op, **kw)`.
    Then `slow = Slow([row(d, "TICKET-001", "planning", running=True, mode="interactive")])`; `app = PipelineApp(client=slow, project=str(d))`; `with patch.object(client_mod, "connect", return_value=FakeClient([])) as conn:` -- a WORKING client, so a swap shows up as a failed assertion instead of reaching the operator's real socket.
    Inside `async with app.run_test() as pilot:`: `app.stream = FakeStream()`; `app.query_one(Tree).focus()`; `await select(app, pilot, str(d), "TICKET-001")`; `await pilot.pause()`; `assert app.attached == (str(d), "TICKET-001")`.
    Then `slow.slow = True`; `app.refresh_tree()`; `await pilot.pause()`; and three asserts: `conn.call_count == 0` with `"a timed-out ls asked connect() for a new client"`, `app.client is slow` with `"a timed-out ls threw away a live daemon's client"`, and `app.attached == (str(d), "TICKET-001")` with `"a timed-out ls detached the pane from a live interactive stage"`.
    Close with `await pilot.press("q")` and `assert app.return_code == 0`, and call it through `asyncio.run(go())` like every other test in `tests/test_tui.py`.
7. Add `test_a_reconnect_puts_the_pty_attach_back_on_the_new_stream` to `tests/test_tui.py`, after `test_the_tui_reconnects_once_the_daemon_it_lost_comes_back`, with its own local `DeadForever` copy -- do not refactor the repro test's copy out of it, that test is the ticket's evidence and stays byte-identical.
    Docstring: the reconnect drops the subscription the attach lived on, and `_paint()`'s interactive-transition branch cannot restore it, because `mode` is `"interactive"` on both sides of the swap and there is no transition to see.
    Body: `d = make_project()`; a local `class DeadForever(FakeClient)` setting `self.broken = False` in `__init__`, whose `request` raises `PipelineError("[Errno 32] Broken pipe")` while `self.broken` and otherwise returns `super().request(op, **kw)`.
    Then `live = row(d, "TICKET-001", "planning", running=True, mode="interactive")`; `dead = DeadForever([live])`; `fresh = FakeClient([live])`; `app = PipelineApp(client=dead, project=str(d))`; `with patch.object(client_mod, "connect", return_value=fresh):`.
    Inside `async with app.run_test() as pilot:`: `app.stream = FakeStream()`; `app.query_one(Tree).focus()`; `await select(app, pilot, str(d), "TICKET-001")`; `await pilot.pause()`; `assert app.attached == (str(d), "TICKET-001")`.
    Then `dead.broken = True`; `app.refresh_tree()`; `await pilot.pause()`; and three asserts: `app.client is fresh`, `app.attached is None` with `"the dead stream kept its attach"`, and `app.pending_attach == (str(d), "TICKET-001")`.
    Then `app.stream = FakeStream()` -- the socket the new subscription worker cannot open under test -- and `app.refresh_tree()`; `await pilot.pause()`; and three asserts: `app.attached == (str(d), "TICKET-001")` with `"the reconnect dropped the pty attach and never put it back"`, `app.stream.ops() == ["attach"]`, and `app.pending_attach is None`.
    Close with `await pilot.press("q")` and `assert app.return_code == 0`, and call it through `asyncio.run(go())`.
8. Add `test_a_tui_started_before_the_daemon_picks_it_up` to `tests/test_tui.py`, after the step-7 test, docstringed: `cmd_tui` builds `PipelineApp(connect(), ...)`, so a TUI opened before `pipeline start` holds `client=None`, which is the same assignment-once defect.
    Body: `d = make_project()`; `fresh = FakeClient([row(d, "TICKET-001", "planning", running=True, mode="interactive")])`; `app = PipelineApp(client=None, project=str(d))`; `with patch.object(client_mod, "connect", return_value=None) as conn:`.
    Inside `async with app.run_test() as pilot:`: `await pilot.pause()`; `assert app.client is None`; `assert app.rows[(str(d), "TICKET-001")]["mode"] is None, "a file row cannot know the mode (DEC-062)"`.
    Then `conn.return_value = fresh`; `app.refresh_tree()`; `await pilot.pause()`; and three asserts: `app.client is fresh` with `"a TUI started before the daemon never picked it up"`, `app.rows[(str(d), "TICKET-001")]["mode"] == "interactive"`, and `app.daemon_down is False` with `"the status bar still said no daemon after one answered"`.
    Close with `await pilot.press("q")` and `assert app.return_code == 0`, and call it through `asyncio.run(go())`.
9. Run `uv run --group dev pytest -q tests/test_tui.py` and confirm exactly three failures: the repro test, `test_a_reconnect_puts_the_pty_attach_back_on_the_new_stream` (`AssertionError: assert <FakeClient object> is <FakeClient object>`), and `test_a_tui_started_before_the_daemon_picks_it_up` (`AssertionError: assert None is <FakeClient object>`). Step 6's test already passes.
10. In `pipeline/tui/app.py`, add `from pipeline.cli import client as client_mod` above `from pipeline.cli.main import (...)`, with the comment `# the module, not the name: tests patch client_mod.connect`.
11. In `pipeline/tui/app.py`, turn `on_unmount`'s loop into `def _close(self, *clients) -> None:` that runs `for c in clients:` over the existing `for call in (lambda: c.sock.shutdown(socket.SHUT_RDWR), lambda: c.close())` body under `except (OSError, AttributeError): pass`, move the existing docstring onto `_close`, and leave `on_unmount` as the single line `self._close(self.stream, self.client)`.
12. In `pipeline/tui/app.py` `__init__`, add `self.resubscribe = False` commented `# a new client needs a new subscription worker` and `self.pending_attach = None` commented `# the attach a reconnect dropped, to restore`, both directly under `self.stream = None`.
13. In `pipeline/tui/app.py`, add `def _reconnect(self) -> bool:` next to `_rows()`, its body the seven lines `new = client_mod.connect(getattr(self.client, "path", None))`, `if new is None and self.client is None: return False`, `if self.attached is not None: self.pending_attach = self.attached`, `self._detach()`, `self._close(self.stream, self.client)`, `self.client, self.stream = new, None`, `self.resubscribe = new is not None`, then `return new is not None`.
    Its docstring: ask for a new client and drop the one whose socket is dead. Only a dead socket gets here (`socket_dead()`), so a timed-out `ls` from a live daemon keeps its client, its subscription and its attach. The old request socket and the old subscription both belong to the daemon that went away; `_detach()` runs before they close because `pty_id` numbers frames on the stream being dropped, and `pending_attach` remembers what it dropped so `_reattach()` can put it back. The early return is what stops a daemon-less TUI detaching itself every 5 seconds.
14. In `pipeline/tui/app.py`, rewrite `_rows()`'s daemon branch so it ASSIGNS `rows` and never returns early, keeping the `rows = None` line above it and the `daemon_down`/`daemon_note`/`targets`/`_carry` lines below it exactly as they are: `if self.client is None: self._reconnect()`, then `if self.client is not None:` holding `try: rows = self.client.request("ls", project=self.project)` and `except PipelineError as e:` whose body is `self.notify(f"daemon: {e}")` then `if client_mod.socket_dead(e) and self._reconnect():` holding a second `try: rows = self.client.request("ls", project=self.project)` / `except PipelineError as e: self.notify(f"daemon: {e}")`.
    Extend its docstring with two sentences: `self.client is None` means "no daemon is reachable right now", never "this app was started without one". The retry assigns rather than returns, because `daemon_down` and `daemon_note` below it are what the status bar reads (DEC-121).
15. In `pipeline/tui/app.py`, add `def _start_stream(self) -> None:` that sets `self.resubscribe = False` and then calls `self._subscribe()`, docstringed as the one caller of `_subscribe()` -- `_rows()` only ever sets the flag, because `on_mount` calls `_rows()` and then subscribes on its own, and a `_subscribe()` from inside `_rows()` would start a second worker there and cancel the first mid-connect -- and replace `self._subscribe()` in `on_mount` with `self._start_stream()`.
16. In `pipeline/tui/app.py`, add `def _reattach(self) -> None:` whose body is `key = self.pending_attach`, `if key is None: return`, `row = self.rows.get(key) if key == self.selected else None`, then `if row is None or row.get("mode") != "interactive":` setting `self.pending_attach = None` and returning, then `if self.stream is not None and self._pty(row): self.pending_attach = None`.
    Its docstring: put back the PTY attach `_reconnect()` dropped, once the new subscription has a socket. `_paint()`'s interactive-transition branch cannot do it -- the row's `mode` never left `"interactive"`, so the transition it tests for never happens. The operator moving the cursor while the daemon was gone cancels the restore: that selection is the newer instruction.
17. In `pipeline/tui/app.py`, rewrite `refresh_tree()` as the four lines `rows = self._rows()`, `if self.resubscribe: self._start_stream()`, `self._paint(rows)`, `self._reattach()`.
18. Run `uv run --group dev pytest -q tests/test_tui.py` and confirm it exits 0 with no failures.
19. In `tests/test_tui.py`, wrap the body of `test_a_failed_ls_keeps_the_last_daemon_answer_for_a_live_interactive_stage` in `with patch.object(client_mod, "connect", return_value=None) as conn:`, comment that patch `# pinned: this file does not override XDG_RUNTIME_DIR, and a real daemon would answer`, and add `assert conn.call_count == 0` after the existing asserts with the message `"a timed-out ls asked connect() for a new client"`.
20. In `pipeline/tui/app.py`, extend the module docstring under the "constructor argument" paragraph: the app also replaces that client itself, because a `Client` whose daemon died can never answer again; `_rows()` asks `connect()` for a new one on the failed `ls` that proves the socket dead, and only then, since a timed-out `ls` from a busy daemon keeps the client, the subscription and the PTY attach; the file fallback lasts exactly as long as no daemon is reachable.
21. Run `uv run --group dev pytest -q` over the whole suite and confirm it exits 0 with no failures, so `pipeline/cli/client.py` and `pipeline/tui/app.py` broke nothing outside `tests/test_tui.py`.
22. In `README.md`, append to the TUI paragraph that ends "and simply does not update itself." -- line 331 on 421ca51, found with `grep -n "does not update itself" README.md` -- that each 5s refresh asks `connect()` for a new connection when the one it holds is dead, a broken pipe rather than a request a busy daemon merely timed out, so a TUI left open across `pipeline stop` and `pipeline start` returns to daemon rows by itself, and an attached pane re-attaches on the new subscription.
23. Commit `pipeline/cli/client.py`, `pipeline/tui/app.py`, `tests/test_tui.py`, `tests/test_daemon.py` and `README.md` together as `fix(TICKET-122): reconnect the TUI when its daemon comes back`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` exits 0.
- `uv run --group dev pytest -q tests/test_tui.py::test_a_reconnect_puts_the_pty_attach_back_on_the_new_stream` exits 0.
- `uv run --group dev pytest -q tests/test_tui.py::test_a_tui_started_before_the_daemon_picks_it_up` exits 0. It pins `app.daemon_down is False` after the reconnect, so a `_rows()` that returns early past the status-bar lines fails it (DEC-121).
- `uv run --group dev pytest -q tests/test_tui.py::test_a_timed_out_ls_keeps_the_client_and_its_pty_attach` exits 0. This is the DEC-062 guard: it fails if a timed-out `ls` swaps the client or drops the attach.
- `uv run --group dev pytest -q tests/test_daemon.py::test_a_dead_socket_is_told_from_a_daemon_that_is_merely_slow` exits 0.
- `uv run --group dev pytest -q tests/test_tui.py::test_a_failed_ls_keeps_the_last_daemon_answer_for_a_live_interactive_stage` exits 0 whether or not a daemon is running on the machine.
- `uv run --group dev pytest -q tests/test_tui.py` exits 0 with no failures. Baseline measured on 421ca51 in this worktree: `1 failed, 43 passed in 12.12s`.
- `uv run --group dev pytest -q` exits 0 with no failures. Baseline measured on 421ca51 in this worktree: `1 failed, 597 passed in 57.78s`, the failure being this ticket's repro test.
- `grep -c "returns to daemon rows by itself" README.md` prints `1`.
- `grep -q "def socket_dead" pipeline/cli/client.py` exits 0.
- `grep -q "from pipeline.cli import client as client_mod" pipeline/tui/app.py` exits 0.
- `grep -c "return self.client.request" pipeline/tui/app.py` prints `0`, because `_rows()` assigns `rows` and returns once, at the bottom.

## Decisions

**A `Client` is thrown away only on evidence its socket is dead.** `socket_dead()` in `pipeline/cli/client.py` reads that evidence off the `PipelineError`: the chained `OSError`'s errno (`EPIPE`, `ECONNRESET`, `ECONNABORTED`, `ENOTCONN`, `EBADF`, `ESHUTDOWN`), or a message mark (`broken pipe`, `connection reset`, `closed the connection`, `bad file descriptor`, `not connected`). It is an allowlist on purpose: an error it does not recognise reads as LIVE, so the cost of a missing mark is one more refresh on the file fallback, never a working socket discarded. `daemon: timed out` carries no mark and a `TimeoutError` carries no errno, which is the point -- a daemon running a `test_one` inside its select loop answers nothing for that whole span (DEC-061) and is not dead, and a client thrown away there takes the PTY attach with it, locking the operator out of the prompt DEC-062 exists to keep reachable. Both channels are needed: `request()` chains the `OSError` it caught, but the EOF case (`daemon closed the connection without replying`) raises with no `__cause__` at all. Keeping a dead client and retrying it is the TICKET-122 defect: the file fallback was correct but permanent, and a TUI open across `pipeline stop` / `pipeline start` -- which `_source_watcher()` triggers on every self-hosted merge -- stayed on file rows until a human relaunched it.

**`_rows()` assigns `rows` and returns once, at the bottom.** The reconnect retry must not `return` the second `ls` answer directly, because `self.daemon_down = rows is None` and `self.daemon_note = daemon_notice(...)` sit between the daemon branch and the file fallback. Skipping them leaves the status bar saying no daemon answered, and leaves DEC-121's "stopped for an upgrade" note on screen, after the new daemon has answered. `test_a_tui_started_before_the_daemon_picks_it_up` asserts `app.daemon_down is False` for exactly this reason.

**A reconnect replaces the subscription, detaches before it does, and restores the attach afterwards.** The dead client's `clone()`d stream belongs to the same daemon and `pty_id` numbers frames on it, so `_reconnect()` in `pipeline/tui/app.py` calls `_detach()` and then `_close()` on both sockets before adopting the new client. `_close()` shuts a socket down before closing it because the subscription worker parks in `recv`; that is `on_unmount`'s reasoning, which is why the two share one method. The attach is then restored by `_reattach()`, NOT by `_paint()`'s interactive-transition branch: that branch requires the row's `mode` to have CHANGED to `"interactive"`, and across a reconnect it is `"interactive"` on both sides. `_reattach()` waits for `self.stream`, which the worker thread assigns, so the restore lands on the refresh after the reconnect; a cursor move in between cancels it, because the operator's newer selection wins.

**`refresh_tree()` starts the subscription worker, not `_rows()`.** `_rows()` sets `resubscribe` and nothing else, because `on_mount` calls `_rows()` and then subscribes on its own; a `_subscribe()` from inside `_rows()` would start a second worker on the mount path and leave the first one's socket to be cancelled mid-connect. `_start_stream()` is the only caller of `_subscribe()` and clears the flag as it goes.

**A TUI test that fails an `ls` must patch `pipeline.cli.client.connect`.** `tests/test_tui.py` does not override `XDG_RUNTIME_DIR`, so an unpatched `connect()` reaches the operator's real daemon socket and a live daemon answers with its own projects' rows. That makes the test pass or fail according to whether the machine happens to be running a daemon.

## Rollback

Revert the single commit from step 23 (`git revert <sha>`): it touches `pipeline/cli/client.py`, `pipeline/tui/app.py`, `tests/test_tui.py`, `tests/test_daemon.py` and `README.md` only. `socket_dead()` is additive -- nothing outside `pipeline/tui/app.py` calls it, and `Client.request()` is unchanged, so every other caller of the client sees exactly what it saw before; no other module imports `_reconnect`, `_close`, `_start_stream` or `_reattach`. The TUI returns to a client assigned once in `__init__` and a permanent file fallback -- the TICKET-122 behaviour, which is degraded but not broken. Nothing on disk, in the ticket schema or in the socket protocol changes, so no data migration is involved and a running daemon needs no restart.

## Thread

### 2026-09-05 17:46:34Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-06 · triage · result=ok

Reproduced. Confirmed `self.client` is set once in `PipelineApp.__init__`
(`pipeline/tui/app.py:236`) and never reassigned anywhere in the file.
`_rows()` (`pipeline/tui/app.py:298-310`) catches `PipelineError` from a dead
client and falls back to file rows, but keeps the same broken `Client`
object forever, so a later-restarted daemon is never noticed.

The existing `Flaky` fake (`tests/test_tui.py:540`) models recovery by
toggling a bool flag on the SAME client object, which does not match a real
socket after a broken pipe -- that object never works again. I added
`DeadForever`, whose `request` raises permanently once broken, and a second
`FakeClient` (`fresh`) representing a new daemon connection. I patched
`pipeline.cli.client.connect` to return `fresh` and confirmed the app never
calls it: `mode` stays `"batch"` (the dead client's last value) instead of
becoming `"interactive"` (what `fresh` would report).

Test: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back`,
committed as ecad420 on branch ticket/122.

Files a fix will likely touch: `pipeline/tui/app.py` (`_rows()` needs to call
`connect()` again and adopt the result on failure).

### 2026-09-05 17:49:29Z · triage · session · session=9ac442c7-1339-403f-8127-3b58099eb212

`triage` ran as session `9ac442c7-1339-403f-8127-3b58099eb212`
- replay: `claude --resume 9ac442c7-1339-403f-8127-3b58099eb212`
- log: `.project/logs/TICKET-122-triage-9ac442c7.log`
- cost: $0.60 of a $3 cap
- tokens: 13,492 out (7,108 thinking) · 56 in · 1,349,960 cache read · 48,725 cache write

### 2026-09-05 17:49:29Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced the stuck daemon client with a failing test at tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back

### 2026-09-06 01:59:22Z · planning · session · session=cabac697-e271-4d3e-bc5f-d2bc910db5f1

`planning` ran as session `cabac697-e271-4d3e-bc5f-d2bc910db5f1`
- replay: `claude --resume cabac697-e271-4d3e-bc5f-d2bc910db5f1`
- log: `.project/logs/TICKET-122-planning-cabac697.log`

### 2026-09-06 01:59:22Z · planning · note

`planning` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-06 · planning · result=ok

Plan written. The fix is `_reconnect()` in `pipeline/tui/app.py`: `_rows()`
asks `client_mod.connect()` for a new client when `ls` fails, retries the `ls`
once, and sets `self.client = None` when no daemon answers, so the file
fallback lasts exactly as long as the outage.

Scope: one subsystem, `pipeline/tui/app.py`, plus its tests and the README
paragraph. I extended the fix to a TUI started before the daemon
(`client=None` from `cmd_tui`, `pipeline/cli/main.py:718`), because it is the
same assignment-once defect and the same code path covers it. Step 4 adds
`test_a_tui_started_before_the_daemon_picks_it_up` for it.

One finding outside the fix: `tests/test_tui.py` does not override
`XDG_RUNTIME_DIR`, unlike `tests/test_daemon.py:23` and `tests/test_pty.py:18`.
Once the app calls `connect()`, the existing `Flaky` test
(`tests/test_tui.py:539`) would reach the operator's real
`/tmp/pipeline-<uid>/daemon.sock` and a live daemon would answer it. Step 2
pins `connect` to `None` in that test rather than change the file env.

Baseline measured on ecad420: `uv run --group dev pytest -q` prints
`1 failed, 560 passed in 52.19s`, the failure being this ticket repro test.

### 2026-09-06 02:08:22Z · planning · session · session=da9f5874-2aa6-4041-afdd-b02f13fb99ae

`planning` ran as session `da9f5874-2aa6-4041-afdd-b02f13fb99ae`
- replay: `claude --resume da9f5874-2aa6-4041-afdd-b02f13fb99ae`
- log: `.project/logs/TICKET-122-planning-da9f5874.log`
- cost: $2.61 of a $10 cap
- tokens: 34,620 out (20,326 thinking) · 50 in · 1,634,765 cache read · 92,423 cache write

### 2026-09-06 02:08:22Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned the TUI reconnect: _rows() asks connect() for a new client on a failed ls, drops the dead one and re-subscribes

### 2026-09-06 10:49:02Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` fails as required
```
ect(client_mod, "connect", return_value=fresh):
            async with app.run_test() as pilot:
                await pilot.pause()
                dead.broken = True
                app.refresh_tree()
                await pilot.pause()
                # the daemon is reachable again -- connect() would now hand
                # back `fresh`, which knows the stage is interactive
                app.refresh_tree()
                await pilot.pause()
>               assert app.rows[(str(d), "TICKET-001")]["mode"] == "interactive", \
                    "TUI never reconnected once the daemon was reachable again"
E               AssertionError: TUI never reconnected once the daemon was reachable again
E               assert 'batch' == 'interactive'
E                 
E                 - interactive
E                 + batch

tests/test_tui.py:605: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.08s ===============================

```
- ok: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` fails on base `main` too -- the bug is not already fixed upstream
```
               "TUI never reconnected once the daemon was reachable again"
E               AssertionError: TUI never reconnected once the daemon was reachable again
E               assert 'batch' == 'interactive'
E                 
E                 - interactive
E                 + batch

tests/test_tui.py:605: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.37s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-nh6loegm/base
      Built pipeline @ file:///tmp/pipeline-base-nh6loegm/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 46ms

```

### 2026-09-06 · plan-validation · result=fail

Two items fail. The other six pass.

- **Decision conflict: fail (DEC-062).** `_reconnect()` calls `_detach()` on
  every failed `ls`, including a timed-out one from a daemon that is alive.
  `connect()` then returns a working client, so the swap happens and the PTY
  attach is gone. DEC-062: "One timed-out `ls` therefore made a live
  `planning` stage sitting on a permission prompt unreachable, and an
  unanswered prompt burns the lease twice." The plan checks DEC-062 for row
  values only; `_carry()` keeps the row, `_detach()` drops the attach.
- **Riskiest step: fail (step 10/11).** The plan names the cost -- "one
  dropped attach, recovered on the next refresh by `_paint()`'s
  interactive-transition branch". That branch cannot fire here. It requires
  `old.get(sel, {}).get("mode") != "interactive"` (`pipeline/tui/app.py:355`),
  and the mode stays `"interactive"` across the swap. `_pty()` also returns
  False while `self.stream is None` (`pipeline/tui/app.py:509`), and
  `_subscribe()` sets `self.stream` from a worker thread, so the same-refresh
  attach fails too. No test covers the attach across a reconnect.

Pass, with reasoning:

- **Root cause: pass.** `self.client` is assigned once
  (`pipeline/tui/app.py:236`) and `_rows()` (298-310) catches `PipelineError`
  and falls back forever, so a `Client` whose socket broke is retried for the
  life of the app. Asking `connect()` again fixes that, not the symptom.
- **Scope: pass.** 16 of 17 steps trace to a criterion. Step 13 (module
  docstring) traces to none; it documents the file the fix changes.
- **Falsifiable: pass.** `mode == "interactive"` is reachable only through a
  new client, and `app.client is fresh` is false if `_rows()` skips the
  `client is None` branch.
- **No research left: pass.** Every step names a file and a function. I
  confirmed `on_unmount` (287-295) holds the loop step 7 extracts,
  `Client.path` exists (`clone()`, `pipeline/cli/client.py:63`), and
  `client_mod` is already imported at `tests/test_tui.py:13`.
- **Regression surface: pass on tests, fail on behaviour (above).** All 31
  `PipelineApp(` constructions in `tests/test_tui.py` pass a client, so the
  new `client is None` branch reaches no existing test, and only the `Flaky`
  test (def at `tests/test_tui.py:536`) fails an `ls`. Step 2 pins it.
- **Blast radius: pass.** 3 files for a `bugfix`.

Second-order, same root: `_reconnect()` closes the subscription
synchronously and re-subscribes from a thread worker, so a live daemon sees
no watcher for a window. `spawn()` gates an interactive stage on
`poller.watchers(project)` (DEC-059), so a spawn in that window is headless.
DEC-059 accepts a TUI that attaches late, not one already attached.

Either swap on evidence the socket is dead rather than on any
`PipelineError`, or restore the attach after the new stream exists, and add
a test for it.

long: eight scored items, each needing its own evidence.

### 2026-09-06 10:52:28Z · plan-validation · session · session=0ce764d9-1458-432a-b88e-adca829299fb

`plan-validation` ran as session `0ce764d9-1458-432a-b88e-adca829299fb`
- replay: `claude --resume 0ce764d9-1458-432a-b88e-adca829299fb`
- log: `.project/logs/TICKET-122-plan-validation-0ce764d9.log`
- cost: $1.33 of a $3 cap
- tokens: 14,774 out (8,858 thinking) · 34 in · 803,320 cache read · 56,053 cache write

### 2026-09-06 10:52:28Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ plan drops the PTY attach on a timed-out ls from a LIVE daemon, and its stated recovery (_paint's interactive-transition branch) cannot fire

### 2026-09-06 · planning · result=ok

Replanned. I took both of `plan-validation`'s options, because each one alone
leaves a hole.

1. Swap on evidence. `socket_dead(err)`, new in `pipeline/cli/client.py`,
   reads a chained `OSError`'s errno or a message mark off the
   `PipelineError`. An unrecognised error reads as LIVE, so `daemon: timed
   out` -- what a daemon running a `test_one` in its select loop produces
   (DEC-061) -- keeps its client, its subscription and its PTY attach. That
   is the DEC-062 conflict, closed.
2. Restore the attach. A dead socket still drops one, so `_reconnect()`
   records it in `self.pending_attach` and `_reattach()` re-sends `attach`
   on the first refresh after the new subscription has a socket.

Two tests are new because of the rejection:
`test_a_timed_out_ls_keeps_the_client_and_its_pty_attach` (patches `connect`
to a WORKING client, so a swap fails an assertion) and
`test_a_reconnect_puts_the_pty_attach_back_on_the_new_stream`. A unit test in
`tests/test_daemon.py` pins `socket_dead()` against two real AF_UNIX sockets:
a peer that closed, and one that accepts and never replies.

Scope grew by one file, `pipeline/cli/client.py`, which holds the classifier
because that module is where the messages it reads are built. `Client.request()`
is unchanged, so no other caller sees anything new.

Baseline re-measured on ecad420 in this worktree: `uv run --group dev pytest
-q` prints `1 failed, 560 passed in 50.23s`; `tests/test_tui.py` alone prints
`1 failed, 42 passed in 11.46s`. The failure is this ticket's repro test.

The repro test stays byte-identical: the new attach test carries its own
`DeadForever` copy rather than refactoring one out of the ticket's evidence.

### 2026-09-06 11:05:42Z · planning · session · session=d621542b-e9b1-4df4-9f09-388b671de314

`planning` ran as session `d621542b-e9b1-4df4-9f09-388b671de314`
- replay: `claude --resume d621542b-e9b1-4df4-9f09-388b671de314`
- log: `.project/logs/TICKET-122-planning-d621542b.log`
- cost: $4.45 of a $10 cap
- tokens: 63,974 out (28,621 thinking) · 66 in · 3,007,686 cache read · 134,794 cache write

### 2026-09-06 11:05:42Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned: socket_dead() gates the client swap on dead-socket evidence, and _reattach() restores the PTY attach on the new stream

### 2026-09-06 11:06:36Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` fails as required
```
ect(client_mod, "connect", return_value=fresh):
            async with app.run_test() as pilot:
                await pilot.pause()
                dead.broken = True
                app.refresh_tree()
                await pilot.pause()
                # the daemon is reachable again -- connect() would now hand
                # back `fresh`, which knows the stage is interactive
                app.refresh_tree()
                await pilot.pause()
>               assert app.rows[(str(d), "TICKET-001")]["mode"] == "interactive", \
                    "TUI never reconnected once the daemon was reachable again"
E               AssertionError: TUI never reconnected once the daemon was reachable again
E               assert 'batch' == 'interactive'
E                 
E                 - interactive
E                 + batch

tests/test_tui.py:605: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.75s ===============================

```
- ok: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` fails on base `main` too -- the bug is not already fixed upstream
```
               "TUI never reconnected once the daemon was reachable again"
E               AssertionError: TUI never reconnected once the daemon was reachable again
E               assert 'batch' == 'interactive'
E                 
E                 - interactive
E                 + batch

tests/test_tui.py:605: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.39s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-35uk06kb/base
      Built pipeline @ file:///tmp/pipeline-base-35uk06kb/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 58ms

```

### 2026-09-06 · plan-validation · result=ok

All eight items pass. The two the first plan failed are closed.

long: eight items, each needs its own evidence.

- **Root cause: pass.** `self.client` is assigned once (`pipeline/tui/app.py:236`)
  and `_rows()` (297-310) catches `PipelineError` and falls back to files
  forever, so a `Client` whose socket died is retried for the life of the app.
  The plan replaces the client, not the assertion.
- **Decision conflict: pass.** DEC-062 is closed. `socket_dead()` reads no mark
  in `daemon: timed out` and `TimeoutError.errno` is not in `DEAD_ERRNOS`, so
  `_rows()` never reaches `_reconnect()` there and the client, the subscription
  and the attach survive. DEC-061 rejected raising the 5s timeout; the plan
  leaves `Client.request()` and `timeout=5.0` unchanged and adds one function,
  so the toast stays reachable. DEC-021: `_detach()`
  (`pipeline/tui/app.py:526-536`) clears `self.raw`, and `_reconnect()` calls it
  before dropping the stream. DEC-011: no new op, no new field.
- **Scope: pass.** 22 of 23 steps trace to a criterion. Step 20 (module
  docstring) traces to none; it extends the constructor-argument paragraph in
  the file the fix changes.
- **Falsifiable: pass.** Step 6's test patches `connect` to a WORKING
  `FakeClient`, so an implementation that swaps on any failed `ls` fails
  `conn.call_count == 0` and `app.client is slow` instead of passing quietly.
  Step 7's test asserts `app.stream.ops() == ["attach"]` on a FakeStream
  assigned after the reconnect; an implementation that never re-sends `attach`
  fails it. The `tests/test_daemon.py` test drives two real AF_UNIX sockets, so
  the classifier is judged against what `Client.request()` raises.
- **No research left: pass.** I checked each named thing against the code:
  `on_unmount` (287-295) holds the loop step 11 extracts, and its
  `except (OSError, AttributeError)` is what makes `_close(FakeStream(),
  FakeClient())` safe under test; `tests/test_tui.py:13` already imports
  `client_mod`; `tests/test_daemon.py` already imports `socket`, `tempfile`,
  `shutil`, `Path` and `PipelineError`; `self.selected` is assigned only on a
  tree highlight (`pipeline/tui/app.py:470`) and `_detach()` never clears it,
  so `_reattach()`'s `key == self.selected` gate holds across a reconnect;
  none of `socket_dead`, `_close`, `_reconnect`, `_start_stream`, `_reattach`,
  `pending_attach`, `resubscribe` exists yet; README line 276 ends
  `and simply does not update itself.` and `grep -c "returns to daemon rows by
  itself" README.md` prints `0` today.
- **Riskiest step: pass.** Step 14, the `_rows()` rewrite: it decides when a
  working client is discarded, which is where the first plan failed. Stated
  fallback: the classifier is a positive-evidence allowlist, so a missing mark
  costs one more refresh on the file fallback and never a live socket. The
  single-commit revert in `## Rollback` is the second.
- **Regression surface: pass.** Four surfaces, each covered. (1) The attach
  path: `test_an_interactive_stage_attaches_and_a_dropped_frame_reattaches`
  and `test_a_row_that_becomes_interactive_attaches_without_moving_the_cursor`;
  `_reattach()` returns on the first line while `pending_attach` is `None`, so
  neither changes. (2) The timeout fallback:
  `test_a_failed_ls_keeps_the_last_daemon_answer_for_a_live_interactive_stage`,
  pinned by step 19. (3) The real-socket hazard: I read every `PipelineApp(`
  construction in the repo -- `pipeline/cli/main.py:718` and 30 tests -- and
  no existing test passes `client=None`; only two fail an `ls`, and after step
  19 both pin `connect`. (4) `refresh_tree()`'s 8 callers now also run
  `_reattach()` and may run `_start_stream()`; both are no-ops while their
  flags are unset, and `_reconnect()` is the only writer of `resubscribe`.
- **Blast radius: pass.** `bugfix`, 5 files: 2 source, 2 test, 1 doc.

Unverified, resting on documented semantics rather than something I ran: that a
`socket.timeout` from `Client.request()` carries `errno is None`. I am
read-only, so I could not run
`python3 -c "import socket; ..."` to see it. The
live-case verdict does not depend on it: `ETIMEDOUT` and `EAGAIN` are both
absent from `DEAD_ERRNOS`, so a timeout reads as live whatever its errno.

One observation, outside this ticket's criteria and not a finding against the
plan. `_subscribe()` sends `subscribe` with no `since`, and the new
subscription does the same, so events emitted while the daemon was gone are
not replayed. DEC-011 offers `since` as an affordance -- "A reconnecting client
passes its last-seen `id` and loses nothing" -- and does not require it. The
cost is log-pane lines, not tree correctness: `_rows()` reseeds from `ls`
every 5s.

### 2026-09-06 11:11:09Z · plan-validation · session · session=3e29d2ef-0560-40e4-990b-27d862607ead

`plan-validation` ran as session `3e29d2ef-0560-40e4-990b-27d862607ead`
- replay: `claude --resume 3e29d2ef-0560-40e4-990b-27d862607ead`
- log: `.project/logs/TICKET-122-plan-validation-3e29d2ef.log`
- cost: $1.83 of a $3 cap
- tokens: 20,883 out (13,372 thinking) · 34 in · 1,072,242 cache read · 76,952 cache write

### 2026-09-06 11:11:09Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items: socket_dead() keeps a timed-out ls on its client (DEC-062), and _reattach() restores the attach _paint() cannot

### 2026-09-06 11:42:43Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-06 12:01:38Z · revalidating · transition · to=triage · result=conflict

**revalidating -> triage** (result: `conflict`)

rebase onto base conflicted; branch recut from base:
```
$ git rebase main || exit 3
/home/chezzijr/.local/share/uv/tools/pipeline/bin/python3 -P -m pipeline --project /home/chezzijr/proj/agent-pipeline gate TICKET-122 --findings /home/chezzijr/proj/agent-pipeline/.project/logs/TICKET-122-gate-d5516ffb.json

Rebasing (1/1)
Auto-merging tests/test_tui.py
CONFLICT (content): Merge conflict in tests/test_tui.py
error: could not apply ecad420... test(TICKET-122): reproduce TUI never reconnecting after daemon dies
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply ecad420... # test(TICKET-122): reproduce TUI never reconnecting after daemon dies

ecad420 test(TICKET-122): reproduce TUI never reconnecting after daemon dies
HEAD is now at 01eed4f chore(TICKET-121): record the finished ticket

```

### 2026-09-06 · triage · result=ok

Recut the branch and recommitted the repro test byte-identical to `ecad420`
(recovered via `git show ecad420`), since the rebase-conflict recut dropped it.

`uv run --group dev pytest -q tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back`
fails with `AssertionError: TUI never reconnected once the daemon was reachable again`
(`assert 'batch' == 'interactive'`), matching `## Reproduction`.
`uv run --group dev pytest -q tests/test_tui.py` prints `1 failed, 43 passed in 13.04s`.
Committed as 421ca51 on branch ticket/122.

Plan and validation are unaffected by the recut; no code files changed, only
the test file. Ready for `implementing` to resume the approved plan.

### 2026-09-06 12:04:20Z · triage · session · session=b5c57516-9bf9-4b27-908f-d16ca33e8cd3

`triage` ran as session `b5c57516-9bf9-4b27-908f-d16ca33e8cd3`
- replay: `claude --resume b5c57516-9bf9-4b27-908f-d16ca33e8cd3`
- log: `.project/logs/TICKET-122-triage-b5c57516.log`
- cost: $0.69 of a $3 cap
- tokens: 8,616 out (2,721 thinking) · 54 in · 1,548,040 cache read · 72,108 cache write

### 2026-09-06 12:04:20Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ recut branch, recovered repro test byte-identical to ecad420, committed as 421ca51, confirmed same failure

### 2026-09-06 · planning · result=ok

Replanned on the recut branch 421ca51. The approved design is unchanged; three
things in it were stale or wrong after the recut.

1. Baselines. `uv run --group dev pytest -q tests/test_tui.py` prints
   `1 failed, 43 passed in 12.12s`, and `uv run --group dev pytest -q` prints
   `1 failed, 597 passed in 57.78s`. The plan carried `42 passed` and
   `560 passed` from ecad420, in step 1, step 9 and two criteria.
2. Line numbers. `pipeline/tui/app.py` moved about 8 lines, `README.md` about
   55. Every reference in `## Digest` was re-read on 421ca51. The README
   paragraph step 22 extends is at line 331, not 276.
3. Step 14. As approved it read `return self.client.request("ls", ...)`, which
   skips `self.daemon_down = rows is None` and `self.daemon_note = ...` at
   `pipeline/tui/app.py:315-317`. After a reconnect the status bar would still
   say no daemon answered, and would keep the DEC-121 upgrade note on screen.
   Step 14 now ASSIGNS `rows` and falls through to those lines. The step-8 test
   asserts `app.daemon_down is False`, and one criterion greps that
   `return self.client.request` is gone.

DEC-121 is new in `## Decisions checked`; it landed after the plan was written.
The five records the approved plan cited are all still active.

### 2026-09-06 12:12:35Z · planning · session · session=941ed4b3-1464-4ee0-9106-6c35e03b8c18

`planning` ran as session `941ed4b3-1464-4ee0-9106-6c35e03b8c18`
- replay: `claude --resume 941ed4b3-1464-4ee0-9106-6c35e03b8c18`
- log: `.project/logs/TICKET-122-planning-941ed4b3.log`
- cost: $2.88 of a $10 cap
- tokens: 39,457 out (9,235 thinking) · 46 in · 1,684,090 cache read · 104,787 cache write

### 2026-09-06 12:12:35Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned on the recut branch 421ca51: baselines re-measured, line numbers corrected, step 14 no longer skips _rows()'s daemon_down/daemon_note

### 2026-09-06 12:13:36Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` fails as required
```
ect(client_mod, "connect", return_value=fresh):
            async with app.run_test() as pilot:
                await pilot.pause()
                dead.broken = True
                app.refresh_tree()
                await pilot.pause()
                # the daemon is reachable again -- connect() would now hand
                # back `fresh`, which knows the stage is interactive
                app.refresh_tree()
                await pilot.pause()
>               assert app.rows[(str(d), "TICKET-001")]["mode"] == "interactive", \
                    "TUI never reconnected once the daemon was reachable again"
E               AssertionError: TUI never reconnected once the daemon was reachable again
E               assert 'batch' == 'interactive'
E                 
E                 - interactive
E                 + batch

tests/test_tui.py:613: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.75s ===============================

```
- ok: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` fails on base `main` too -- the bug is not already fixed upstream
```
               "TUI never reconnected once the daemon was reachable again"
E               AssertionError: TUI never reconnected once the daemon was reachable again
E               assert 'batch' == 'interactive'
E                 
E                 - interactive
E                 + batch

tests/test_tui.py:613: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.46s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-6ek5bavu/base
      Built pipeline @ file:///tmp/pipeline-base-6ek5bavu/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 49ms

```

### 2026-09-06 · plan-validation · result=ok

Tier B PASS on 421ca51. Every item scored against the code, not the plan's prose.

1. Root cause. `Client.__init__` connects its socket once, so a `Client` whose
   daemon died can never answer again, and `PipelineApp.client`
   (`pipeline/tui/app.py:235`) is assigned once. The plan replaces the object.
   That is the cause, not the symptom.
2. Decisions. All six cited files exist under `.project/decisions/`, and a grep
   for `superseded` over them returns nothing. DEC-121 records "a note set only
   in the failure branch would outlive the daemon's return"; step 14 complies.
3. Scope. Steps 11 and 20 name no criterion of their own. Step 11 is a
   prerequisite of step 13, and step 20 documents the contract the same file
   changes. Neither widens scope.
4. Criteria falsifiable. `app.daemon_down is False` (step 8) fails on an early
   return, and `grep -c "return self.client.request"` fails on the approved
   wording step 14 replaced.
5. No research left. Every step names a file and a function. I re-read `_rows()`,
   `_paint()`, `_pty()`, `_detach()`, `_subscribe()`, `on_unmount()`,
   `socket_path()`, `_op_ls()` and `_project()`, and every digest claim held.
6. Riskiest step: 14. The plan states its fallback -- an unrecognised error
   reads as live, which costs one more refresh on file rows.
7. Regression surface. `refresh_tree()` has 8 call sites; `_reattach()` and
   `_start_stream()` are no-ops at all of them while `pending_attach` is None
   and `resubscribe` is False. `tests/test_tui.py` covers them.
8. Blast radius. `bugfix`, 5 files, 2 of them source. Proportionate.

Advisory, not a scored finding.
`test_the_status_bar_says_the_daemon_stopped_for_an_upgrade`
(`tests/test_tui.py:635`) builds `PipelineApp(client=None, ...)` and does not
patch `connect`. After step 14 its `_rows()` calls `client_mod.connect()`, which
reaches the operator's real socket; `/run/user/1000/pipeline/daemon.sock` exists
on this machine now. Its asserts do not flip: `_project()`
(`pipeline/daemon/server.py:487-496`) raises `project not registered: <path>`
for the temp project, so `rows` stays `None` and `daemon_down` stays True. It
does open a live socket and a subscription from a unit test. The plan's own
decision -- "A TUI test that fails an `ls` must patch
`pipeline.cli.client.connect`" -- covers it, and step 19 pins only
`tests/test_tui.py:544`. Pinning line 635 the same way is one line.

unverified: both suite baselines. A read-only stage cannot run `uv run --group
dev pytest`, so `1 failed, 43 passed in 12.12s` and `1 failed, 597 passed in
57.78s` rest on the `planning` entry and the Tier A gate, not on a run of mine.
I also could not execute `socket_dead()` against a real socket. I read
`Client.request()` (`pipeline/cli/client.py:36-51`) instead and confirmed the
two evidence channels the plan needs: the chained `OSError` carrying the errno,
and the causeless `daemon closed the connection without replying`.

### 2026-09-06 12:19:06Z · plan-validation · session · session=2d3154d6-7124-49d0-97f9-ee313b60b5bb

`plan-validation` ran as session `2d3154d6-7124-49d0-97f9-ee313b60b5bb`
- replay: `claude --resume 2d3154d6-7124-49d0-97f9-ee313b60b5bb`
- log: `.project/logs/TICKET-122-plan-validation-2d3154d6.log`
- cost: $2.34 of a $3 cap
- tokens: 24,435 out (15,423 thinking) · 58 in · 1,830,835 cache read · 80,951 cache write

### 2026-09-06 12:19:06Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ all eight items pass on 421ca51; one advisory: tests/test_tui.py:635 fails its ls unpinned and now reaches the live daemon socket

### 2026-09-06 12:57:20Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-06 12:58:22Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` fails as required
```
ect(client_mod, "connect", return_value=fresh):
            async with app.run_test() as pilot:
                await pilot.pause()
                dead.broken = True
                app.refresh_tree()
                await pilot.pause()
                # the daemon is reachable again -- connect() would now hand
                # back `fresh`, which knows the stage is interactive
                app.refresh_tree()
                await pilot.pause()
>               assert app.rows[(str(d), "TICKET-001")]["mode"] == "interactive", \
                    "TUI never reconnected once the daemon was reachable again"
E               AssertionError: TUI never reconnected once the daemon was reachable again
E               assert 'batch' == 'interactive'
E                 
E                 - interactive
E                 + batch

tests/test_tui.py:613: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.74s ===============================

```
- ok: `tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back` fails on base `main` too -- the bug is not already fixed upstream
```
               "TUI never reconnected once the daemon was reachable again"
E               AssertionError: TUI never reconnected once the daemon was reachable again
E               assert 'batch' == 'interactive'
E                 
E                 - interactive
E                 + batch

tests/test_tui.py:613: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_the_tui_reconnects_once_the_daemon_it_lost_comes_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.41s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yhpskt1l/base
      Built pipeline @ file:///tmp/pipeline-base-yhpskt1l/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 57ms

```

### 2026-09-06 12:58:23Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

### 2026-09-06 · implementing · todo

Todo list, one entry per plan step:

1. [x] confirm baseline (1 failed, 43 passed)
2. [x] test_a_dead_socket_is_told_from_a_daemon_that_is_merely_slow (test_daemon.py)
3. [x] watch it fail: ImportError
4. [x] add socket_dead() to client.py
5. [x] watch step-3 test pass
6. [x] test_a_timed_out_ls_keeps_the_client_and_its_pty_attach
7. [x] test_a_reconnect_puts_the_pty_attach_back_on_the_new_stream
8. [x] test_a_tui_started_before_the_daemon_picks_it_up
9. [x] confirm exactly 3 failures
10. [x] import client_mod in app.py
11. [x] extract _close()
12. [x] add resubscribe/pending_attach to __init__
13. [x] add _reconnect()
14. [x] rewrite _rows() daemon branch
15. [x] add _start_stream()
16. [x] add _reattach()
17. [x] rewrite refresh_tree()
18. [x] confirm tests/test_tui.py green
19. [x] pin connect() in test_a_failed_ls_keeps_the_last_daemon_answer...
20. [x] extend module docstring
21. [x] confirm full suite green
22. [x] update README.md
23. [x] commit

### 2026-09-06 · implementing · result=ok

**implementing done, all 23 steps complete**

TDD for all five new tests, watched RED (ImportError / AssertionError) then
GREEN. `tests/test_tui.py` 3 failures after adding steps 6-8's tests, exactly
as the plan predicted; 0 failures after steps 10-17's implementation.

Full suite: `602 passed` (baseline 597 passed + 1 fixed repro + 5 new tests +
0 removed = matches). `tests/test_tui.py` alone: `47 passed` (baseline 43 +
1 fixed + 4 new). Acceptance-criteria tests re-run individually: all 6 pass.

Committed `e16f2ac`, five files: `pipeline/cli/client.py`,
`pipeline/tui/app.py`, `tests/test_tui.py`, `tests/test_daemon.py`,
`README.md`.

re-gated after rebasing onto base: passed

### 2026-09-06 13:04:31Z · implementing · session · session=36d48ccb-5fd0-4be0-841c-6d8c82f8bdbb

`implementing` ran as session `36d48ccb-5fd0-4be0-841c-6d8c82f8bdbb`
- replay: `claude --resume 36d48ccb-5fd0-4be0-841c-6d8c82f8bdbb`
- log: `.project/logs/TICKET-122-implementing-36d48ccb.log`
- cost: $1.27 of a $8 cap
- tokens: 17,327 out (160 thinking) · 108 in · 3,887,884 cache read · 80,644 cache write

### 2026-09-06 13:04:31Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented socket_dead() and the TUI reconnect; all 5 new tests pass, full suite 602 passed, committed as e16f2ac

### 2026-09-06 · review · result=ok

**review pass 1: no blocking findings.** Delta reviewed: `git diff 421ca51
e16f2ac`, five files, `288 insertions(+), 16 deletions(-)`. No drift from
`## Plan`: steps 10-17 and 19-22 land as written, and the repro test is
byte-identical.

All 12 acceptance criteria pass. Each of the six named tests re-run alone:
`1 passed` each. `uv run --group dev pytest -q tests/test_tui.py
tests/test_daemon.py` -> `94 passed in 16.98s`. `uv run --group dev pytest -q`
-> `602 passed in 56.72s`. The four greps print `1`, `1`, `1`, `0` and the two
`grep -q` exit 0.

Findings, none blocking:

1. advisory -- `test_the_status_bar_says_the_daemon_stopped_for_an_upgrade`
   (`tests/test_tui.py:767`) is the one unpinned `client=None` app left, so
   `_rows()` now reaches the operator's real socket. plan-validation's
   advisory. It cannot flip: every `make_project()` path is unregistered and
   `pipeline/daemon/server.py:495` raises `project not registered: <p>`, so
   `rows` stays `None` and `daemon_down` stays `True`. Verified with a live
   socket at `/run/user/1000/pipeline/daemon.sock`.
2. advisory -- two `_subscribe()` worker threads can both assign
   `self.stream` if `_reconnect()` lands while one sits between
   `self.client.clone()` and the assignment (`pipeline/tui/app.py:497`).
   `exclusive=True` cannot interrupt a thread. Unreachable in practice: the
   worker reaches `lines()` milliseconds after mount and never re-enters
   `clone()`, while the earliest `_reconnect()` is 5s later.
3. nit -- `connect()` (`pipeline/cli/client.py:98`) does not catch the
   `PipelineError` `runtime_dir()` raises for a hostile runtime dir, and
   `_rows()` now calls it on a timer. `cmd_tui` (`pipeline/cli/main.py:838`)
   calls `connect()` first and dies there, so the dir must turn hostile
   mid-session to reach it.

Refuted and dropped: a daemon refusal reading as a dead socket -- no message
in `pipeline/daemon/` or `pipeline/core/` matches a `DEAD_MARK`.

### 2026-09-06 13:12:51Z · review · session · session=c65928e6-5b91-491d-b623-68ce40f67ebb

`review` ran as session `c65928e6-5b91-491d-b623-68ce40f67ebb`
- replay: `claude --resume c65928e6-5b91-491d-b623-68ce40f67ebb`
- log: `.project/logs/TICKET-122-review-c65928e6.log`
- cost: $3.19 of a $6 cap
- tokens: 27,453 out (17,120 thinking) · 94 in · 3,213,642 cache read · 89,153 cache write

### 2026-09-06 13:12:51Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed e16f2ac against 421ca51: all 12 acceptance criteria pass, full suite 602 passed, no blocking findings, 3 advisories appended

### 2026-09-06 13:13:54Z · verifying · transition · to=implementing · result=fail

**verifying -> implementing** (result: `fail`)

regression suite exit 1
```
e_budget(capsys):
        from pipeline.daemon import main as dmain
    
        tmp = Path(tempfile.mkdtemp())
        execs: list = []
        reason = ["source_changed"]
        orig_serve = supervisor.serve
        orig_server = dmain.Server
        orig_execve = dmain.os.execve
        orig_argv = sys.argv
        try:
            dmain.Server = lambda store, path: types.SimpleNamespace(close=lambda: None)
            dmain.os.execve = lambda *a: execs.append(a)
            supervisor.serve = lambda *a, **kw: reason[0]
            sys.argv = ["pipelined", "--db", str(tmp / "events.db"),
                        "--socket", str(tmp / "d.sock"), "--restart-on-upgrade"]
    
            reason[0] = "source_changed"
            dmain.main()
            assert len(execs) == 1
            assert execs[0][1][1:3] == ["-m", "pipeline.daemon.main"]
            assert "--restart-on-upgrade" in execs[0][1]
>           assert execs[0][2][dmain.COUNT_VAR] == "1"
E           AssertionError: assert '2' == '1'
E             
E             - 1
E             + 2

tests/test_daemon.py:1150: AssertionError
----------------------------- Captured stdout call -----------------------------
pipelined: restarting into the merged code (restart 2 of 3)
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_pipelined_execs_only_for_a_source_change_inside_budget
======================== 1 failed, 601 passed in 59.38s ========================

### 2026-09-06 · implementing · investigation

**The failing test is ambient environment pollution, not a regression from
this ticket's diff.** `test_pipelined_execs_only_for_a_source_change_inside_budget`
(`tests/test_daemon.py:1128`) calls `dmain.main()`, which reads the real
`os.environ` (`pipeline/daemon/main.py:81`), and asserts
`execs[0][2][dmain.COUNT_VAR] == "1"`. The process this stage ran in had
`PIPELINE_UPGRADE_RESTARTS=1` and `PIPELINE_UPGRADE_SINCE=<ts>` already set:

    $ env | grep PIPELINE_UPGRADE
    PIPELINE_UPGRADE_SINCE=1788700372.0343034
    PIPELINE_UPGRADE_RESTARTS=1

This repo runs its own pipeline; its daemon did a real
`--restart-on-upgrade` re-exec at some point, and `os.execve` carries that
env to every descendant process (`pipeline/daemon/main.py:92`), including
this agent's shell. With the two vars set, `count` starts at 1 instead of 0,
so the assertion computes `"2"`. Reproduced directly:

    $ PIPELINE_UPGRADE_RESTARTS=1 PIPELINE_UPGRADE_SINCE=$(date +%s) \
      uv run --group dev pytest -q tests/test_daemon.py::test_pipelined_execs_only_for_a_source_change_inside_budget
    AssertionError: assert '2' == '1'

    $ env -u PIPELINE_UPGRADE_RESTARTS -u PIPELINE_UPGRADE_SINCE \
      uv run --group dev pytest -q tests/test_daemon.py::test_pipelined_execs_only_for_a_source_change_inside_budget
    1 passed in 0.08s

    $ env -u PIPELINE_UPGRADE_RESTARTS -u PIPELINE_UPGRADE_SINCE \
      uv run --group dev pytest -q
    602 passed in 58.42s

This test predates TICKET-122 (`git log -S COUNT_VAR` -> `bb1aea5`,
TICKET-121) and is outside `## Plan`'s files (`pipeline/cli/client.py`,
`pipeline/tui/app.py`, `tests/test_tui.py`, `tests/test_daemon.py`'s one new
test, `README.md`). Its own isolation defect -- it never clears
`PIPELINE_UPGRADE_RESTARTS`/`PIPELINE_UPGRADE_SINCE` before running, only in
its `finally` after -- is out of scope for this ticket. No code change made;
working tree is clean at `e16f2ac`, matching what `review` already passed.

```

### 2026-09-06 13:17:30Z · implementing · session · session=48dff607-d5e1-4aaf-8c09-529515f23753

`implementing` ran as session `48dff607-d5e1-4aaf-8c09-529515f23753`
- replay: `claude --resume 48dff607-d5e1-4aaf-8c09-529515f23753`
- log: `.project/logs/TICKET-122-implementing-48dff607.log`
- cost: $0.64 of a $8 cap
- tokens: 10,587 out (4,857 thinking) · 46 in · 1,390,441 cache read · 62,727 cache write

### 2026-09-06 13:17:30Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ verifying's failure is ambient env pollution (PIPELINE_UPGRADE_RESTARTS=1 inherited from this repo's own daemon restart), unrelated to TICKET-122's diff; suite is 602 passed with the var unset, no code change made

### 2026-09-06 13:17:49Z · review · note

`review` was interrupted; lease released

### 2026-09-06 · review · result=ok

**review pass 2: no blocking findings.** The delta since the pass-1 review
entry is empty. `git diff e16f2ac` prints nothing, `git status --porcelain`
prints nothing, and HEAD is still `e16f2ac`. `implementing` changed no file,
so there is no new code to review.

I confirmed its diagnosis from the code, not from its report. `main()` reads
the real `os.environ` (`pipeline/daemon/main.py:81`). `restart_budget()`
(`pipeline/daemon/main.py:24-37`) returns `count + 1` whenever
`now - since <= 60`, pinned by the existing unit case
`restart_budget({"PIPELINE_UPGRADE_RESTARTS": "2", "PIPELINE_UPGRADE_SINCE":
"990"}, 1000.0) == (3, 990.0)` (`tests/test_daemon.py:1122`). An ambient
`PIPELINE_UPGRADE_RESTARTS=1` inside the window therefore produces `"2"`,
which is `verifying`'s `assert '2' == '1'` exactly. This ticket's delta to
`tests/test_daemon.py` is appended after line 1185 -- `git diff 421ca51
e16f2ac -- tests/test_daemon.py` opens at `@@ -1183,3 +1183,38 @@` -- so it
cannot reach the earlier test. That test's `finally`
(`tests/test_daemon.py:1183-1184`) pops both vars, so it leaks nothing
forward.

All 12 acceptance criteria pass, re-measured this pass. The six named tests in
one run: `6 passed in 2.51s`. `uv run --group dev pytest -q` -> `602 passed in
57.75s`. The four greps print `1`, `1`, `1`, `0` and the two `grep -q` exit 0.
This stage's shell carries no `PIPELINE_UPGRADE_*` var.

Findings, none blocking:

1. advisory -- `test_pipelined_execs_only_for_a_source_change_inside_budget`
   (`tests/test_daemon.py:1128`) reads ambient `PIPELINE_UPGRADE_RESTARTS`
   and `PIPELINE_UPGRADE_SINCE`, and fails when either is set. It belongs to
   TICKET-121, not to this diff. Isolating it needs its own ticket.
2. advisory -- the three pass-1 advisories stand unchanged. No code moved
   under them.

I could not reproduce the failure by setting the two vars: the guard blocks an
env-prefixed command in a read-only stage. The code path above is the evidence
instead.

### 2026-09-06 13:21:49Z · review · session · session=0dd64526-439a-463b-8203-94807f55b293

`review` ran as session `0dd64526-439a-463b-8203-94807f55b293`
- replay: `claude --resume 0dd64526-439a-463b-8203-94807f55b293`
- log: `.project/logs/TICKET-122-review-0dd64526.log`
- cost: $1.46 of a $6 cap
- tokens: 12,669 out (4,041 thinking) · 48 in · 1,140,918 cache read · 57,426 cache write

### 2026-09-06 13:21:49Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review pass 2: delta since e16f2ac is empty, implementing's env-pollution diagnosis confirmed from code, full suite 602 passed, no blocking findings

### 2026-09-06 13:22:49Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-06 13:22:51Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/122


Rebasing (1/2)Rebasing (2/2)Successfully rebased and updated refs/heads/ticket/122.
Already up to date.
Updating 23e36cc..99eedc8
Fast-forward
 README.md              |   6 +-
 pipeline/cli/client.py |  24 ++++++
 pipeline/tui/app.py    |  87 ++++++++++++++++++++--
 tests/test_daemon.py   |  35 +++++++++
 tests/test_tui.py      | 197 ++++++++++++++++++++++++++++++++++++++++++++++---
 5 files changed, 333 insertions(+), 16 deletions(-)

```

### 2026-09-06 13:22:51Z · merging · decision

decision recorded as `DEC-122`
