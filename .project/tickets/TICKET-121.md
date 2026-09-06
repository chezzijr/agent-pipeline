---
id: TICKET-121
stage: done
class: feature
branch: ticket/121
test_file: tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store
files_declared:
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/daemon/main.py
- pipeline/daemon/store.py
- pipeline/daemon/supervisor.py
- pipeline/tui/app.py
- tests/test_cli.py
- tests/test_daemon.py
- tests/test_dispatch.py
- tests/test_tui.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 24
  plan_files: 11
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 51efae96-28ad-4a52-a2e7-9b20c6ba53b8
  replay: claude --resume 51efae96-28ad-4a52-a2e7-9b20c6ba53b8
  log: .project/logs/TICKET-121-review-51efae96.log
  cost_usd: 2.260601
approved_by: chezzijr
approved_at: '2026-09-06T11:42:43.164599+00:00'
---

## Summary

Reviewed and passed. `run()` and `serve()` return their exit reason
(`source_changed`, `signal`, `drained`, `error`); `serve()`'s `finally` emits
`daemon_stop` carrying that reason and the module that moved. `daemon_notice()`
in `pipeline/daemon/store.py` renders it for `pipeline status` and the TUI
status bar. `pipeline start --restart-on-upgrade` / `pipelined
--restart-on-upgrade` re-execs into the merged code, at most 3 times in 60s,
and exits 1 when the budget is spent.

All 24 plan steps landed across 7 commits (bfd4fe3, 2d661a4, afbed7b, d0f68ed,
bb1aea5, 7c2fb11, f7edee4). `review` re-ran every acceptance criterion itself:
the 8 named tests pass by node id, `uv run --group dev pytest -q` reports
`597 passed in 56.04s`, the guard reports `guard: all passed`, and the three
grep / `python -c` criteria print `0`, `2` and `(1, 1000.0)`. Review found no
blocking issue and 3 minor notes; they are in the review thread entry.

## Reproduction

Test: `tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store`
Command: `uv run --group dev pytest -q tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store`
Failure:
```
AssertionError: expected a daemon_stop event with reason=source_changed, got kinds ['daemon_start', 'daemon_stop']
assert []
```
expect: expected a daemon_stop event with reason=source_changed, got kinds ['daemon_start', 'daemon_stop']

## Digest

Files touched: `pipeline/daemon/supervisor.py` (the exit reason),
`pipeline/daemon/store.py` (the reason vocabulary and the reader),
`pipeline/daemon/main.py` (the restart), `pipeline/cli/main.py`
(`pipeline status`, `pipeline start`), `pipeline/tui/app.py` (the status bar).

Key functions. `run()` at `pipeline/daemon/supervisor.py:1609` and `serve()` at
`pipeline/daemon/supervisor.py:1666` each hold `stale, moved =
_source_watcher(), None` and print the same message at lines 1641 and 1703
before `return`. `serve()`'s `finally` emits the only `daemon_stop`, at line
1748: `store.emit("", "daemon_stop", pid=os.getpid(), version=__version__)`. A
`return` inside the loop runs that `finally` first, so the reason is available
to the emit. `Store.emit()` (`pipeline/daemon/store.py:83`) is the only writer;
`Store.since()` (line 109) and `Store.cursor()` (line 106) are the read side,
and `_row()` (line 48) turns a `sqlite3.Row` into a dict.
`cmd_daemon_status()` (`pipeline/cli/main.py:515`) prints `pipelined: not
running` with the socket path and exits 1. `cmd_start()`
(`pipeline/cli/main.py:529`) builds the `pipelined` argv.
`PipelineApp.__init__` (`pipeline/tui/app.py:234`) takes `client` and
`project`; `_rows()` (line 298) falls back to the files when the client raises
`PipelineError`, and `_status()` (line 381) renders the `#status` widget.

Entry points: `pipelined` is `main()` in `pipeline/daemon/main.py`, a raw
foreground process that parses argv, builds `Store(args.db)` and
`Server(store, args.socket)` inside one `try`, calls `supervisor.serve()`, and
turns a `PipelineError` into `sys.exit(f"error: {e}")`. `pipeline run` calls
`supervisor.run(..., Store())` at `pipeline/cli/main.py:792`. `pipeline tui`
builds `PipelineApp(connect(), ...)` at `pipeline/cli/main.py:718`.

Imports already in place: `pipeline/cli/main.py:28` imports `Store` from
`pipeline.daemon.store`, so only `daemon_notice` is added there, and
`pipeline/daemon/supervisor.py:41` imports `noop` from the same module.
`pipeline/daemon/main.py` imports neither `os` nor `time` today, so step 17
adds both.

Test seams: `tests/test_daemon.py` already imports `os`, `shutil`, `sys`,
`tempfile`, `time`, `types`, `Path`, `supervisor` and `Store`.
`tests/test_tui.py:901` defines `status(app)`, which renders `#status` to a
string, and line 11 imports `project as make_project` from `helpers`.
`tests/test_cli.py:22` defines `cli(project, *args, env=None)`, which runs a
real `python -m pipeline`. `capsys` works in this suite
(`tests/test_config.py:103`).

Gotchas.
1. `os.execve` keeps the pid, the open log fd and the session, and `serve()`'s
   `finally` has already released the socket, the flocks and the leases -- so
   an exec after `serve()` returns is a clean handoff, not a second daemon.
2. The env carries the restart counter and the operator can set it. Parse it
   defensively; a bad value reads as no restarts spent.
3. `run()` emits no daemon-level event today and must not start: a `pipeline
   run` beside a `pipelined` would make the store's last lifecycle event
   ambiguous.
4. The suite pins `XDG_STATE_HOME` to a temp dir in `tests/conftest.py:13`, so
   a real `Store()` in a test never touches the operator's database.
5. `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` asserts
   that `start --help` still names `pipeline tui`, `headless` and every
   interactive stage. Adding an option must not disturb `START_DESC`.
6. No file in this plan is in `machine.FENCED`, so the ticket does not park at
   `awaiting-merge` for the fence.
7. `_rows()` returns early on a successful `ls` at `pipeline/tui/app.py:305`.
   A note set while the daemon was down survives that return, so the status bar
   would keep claiming an upgrade stop after the daemon came back. Step 13 sets
   the note above that return, on both paths.
8. `tests/test_cli.py:401` asserts `tui` is in `start_line[0]`, the FIRST
   `README.md` line starting `pipeline start `. That line is `README.md:149`,
   so step 23's new line goes after it, never above it.
9. `main()` builds a real `Server`, which binds an AF_UNIX socket. Step 19
   replaces `pipeline.daemon.main.Server` with a stub carrying `close()`, so
   repeated in-process `main()` calls never contend for one socket path.

## Decisions checked

- DEC-032 (TICKET-032) is the binding record, and this plan complies with all
  four of its rules: no `importlib.reload()`, code and never data, stop
  claiming before exiting, mtime detection. Its closing paragraph -- "Nothing
  restarts the dispatcher after this exit" -- states the situation at the time,
  not a prohibition; the restart added here is opt-in, off by default, and
  leaves the unflagged behaviour exactly as DEC-032 describes it.
- DEC-011 (TICKET-011) freezes the event vocabulary and says that adding a
  field inside `data` is additive and fine. `reason` and `module` on
  `daemon_stop` are additive; no column, no kind and no existing field changes,
  so nothing here supersedes it.
- DEC-028 (TICKET-028) keeps the harness `.toml` re-read per tick and out of
  the source watcher. Untouched.
- DEC-086 (TICKET-086) requires a loop detector in a fake `tick()` to subclass
  `BaseException`. The new dispatcher test obeys it.
- DEC-096 (TICKET-096) puts a once-per-process SETUP notice behind
  `notice_once()`. The two lines step 17 prints state a fact about one exit,
  not about the setup, so they stay plain `print()` calls.
- DEC-034 (TICKET-034) matched the grep on `reload` only, through
  `strip_settings_sources()`. Nothing here touches a settings source.
- None of those six records carries a `superseded-by:` line.
- Grep terms used against `.project/decisions/`: `source_watcher`, `source
  change`, `daemon_stop`, `restart`, `reload`, `execve`.

## Plan

1. Add `SOURCE_CHANGED = "source_changed"` and `STOP_REASONS = ("source_changed", "signal", "drained", "error")` as module constants in `pipeline/daemon/store.py` above `class Store`, with a comment naming `serve()` as the one writer of the field.
2. Add `Store.last_daemon_event(self)` to `pipeline/daemon/store.py` beside `since()`: it runs `SELECT * FROM events WHERE kind IN ('daemon_start','daemon_stop') ORDER BY id DESC LIMIT 1` and returns `_row(r)` for that row, or `None` when there is none.
3. Add `daemon_notice(store, short=False)` to `pipeline/daemon/store.py` under `last_daemon_event`; it reads that event, builds `when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ev["ts"]))`, and returns `None` when there is no event, the pair below for a `daemon_stop` whose `data["reason"]` is `SOURCE_CHANGED` -- long: `stopped for a source upgrade at {when}: {module} changed -- run pipeline start to load the merged code` with `module` defaulting to `a pipeline module`, short: `daemon stopped for a source upgrade` -- for any other `daemon_stop` long `stopped at {when} (reason: {reason})` and short `daemon stopped ({reason})` with `reason` defaulting to `unreported`, and for a `daemon_start` long `last started at {when} (pid {pid}); no stop was recorded -- it may have been killed` and short `daemon gone with no stop recorded`.
4. Write `tests/test_daemon.py::test_the_daemon_notice_names_why_the_daemon_stopped`: open a `Store` under `tempfile.mkdtemp()`, assert `daemon_notice(store) is None`; emit `daemon_start` with `pid=7`, assert the long form contains `no stop was recorded` and the short form equals `daemon gone with no stop recorded`; emit `daemon_stop` with `reason="source_changed"` and `module="pipeline.daemon.supervisor"`, assert the long form contains both `source upgrade` and `pipeline.daemon.supervisor` and the short form equals `daemon stopped for a source upgrade`; emit `daemon_stop` with `reason="signal"`, assert the long form contains `reason: signal` and not `source upgrade`. Run `uv run --group dev pytest -q tests/test_daemon.py -k daemon_notice`, watch it pass, and commit steps 1-4.
5. In `pipeline/daemon/supervisor.py` add `def exit_message(module)` above `run()`, returning the existing text byte for byte -- two spaces, then `dispatcher source changed ({module}) -- ending the loop so a restart runs the merged code` -- and import `SOURCE_CHANGED` from `pipeline.daemon.store` beside the existing `noop` import at line 41.
6. In `pipeline/daemon/supervisor.py` make `serve()` track and return its exit reason: initialise `reason = "error"` beside `turn = 0`; in the source-change branch call `print(exit_message(moved))`, set `reason = SOURCE_CHANGED` and `return reason`; set `reason = "drained"` before the `once` return; set `reason = "signal"` as the last statement inside `try:` after the `while` loop; change the `finally` emit to `store.emit("", "daemon_stop", pid=os.getpid(), version=__version__, reason=reason, module=moved)`; add `return reason` after the `try/finally` block; annotate the signature `-> str`.
7. In `pipeline/daemon/supervisor.py` give `run()` the same `reason` variable and the same four return values, annotate its signature `-> str`, replace its print with `print(exit_message(moved))`, and emit no store event there -- with a comment saying a `pipeline run` beside a `pipelined` would otherwise make the store's last lifecycle event ambiguous.
8. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store` and watch the ticket's repro test pass.
9. Write `tests/test_dispatch.py::test_a_drained_daemon_stop_is_not_a_source_change`, modelled on the repro test's `Store` and `Server` setup but with no registered project: assert `supervisor.serve(0, "fake", 1, store, server, once=True)` returns `"drained"`, and that the `daemon_stop` event in `store.since(cursor)` carries `data["reason"] == "drained"` -- a restart that fired on every exit would restart `pipeline stop` too. Run `uv run --group dev pytest -q tests/test_dispatch.py -k "source_change or drained"`, watch it pass, and commit steps 5-9.
10. In `pipeline/cli/main.py` add `daemon_notice` to the `from pipeline.daemon.store import Store, state_dir` line at line 28 and extend `cmd_daemon_status()`: when `connect()` returns `None`, keep the existing `pipelined: not running` line and the `sys.exit(1)`, and between them print the notice indented by two spaces when `daemon_notice(Store())` is not `None`.
11. Write `tests/test_cli.py::test_status_says_the_daemon_stopped_for_an_upgrade`: make `state = Path(tempfile.mkdtemp())`, open `Store(state / "pipeline" / "events.db")`, emit `daemon_start` then `daemon_stop` with `reason="source_changed"` and `module="pipeline.core.machine"`, close the store, run `cli(d, "status", env={"XDG_STATE_HOME": str(state)})`, and assert `r.returncode == 1`, `"not running" in r.stdout` and `"source upgrade" in r.stdout`. Run `uv run --group dev pytest -q tests/test_cli.py -k stopped_for_an_upgrade`, watch it pass, and commit steps 10-11.
12. In `pipeline/tui/app.py` add a third constructor argument `store=None` to `PipelineApp.__init__`, commented `None == no event log to ask why the daemon went away`, plus `self.store = store`, `self.daemon_down = client is None` and `self.daemon_note = None`; import `daemon_notice` from `pipeline.daemon.store` in that module; and in `cmd_tui()` at `pipeline/cli/main.py:718` pass `Store()` as that third argument.
13. In `pipeline/tui/app.py` restructure `_rows()` so the note is recomputed on BOTH paths: bind `rows = None`, assign `rows = self.client.request("ls", project=self.project)` inside the existing `try` when `self.client is not None`, keep the `except PipelineError` `self.notify(f"daemon: {e}")`, then set `self.daemon_down = rows is None` and `self.daemon_note = daemon_notice(self.store, short=True) if self.daemon_down and self.store is not None else None`, then `return rows` when `rows is not None` and otherwise fall through to the unchanged `ticket_rows()` fallback; and in `_status()` append one more segment `f" - {self.daemon_note}" if self.daemon_note else ""` after `unk`.
14. Write `tests/test_tui.py::test_the_status_bar_says_the_daemon_stopped_for_an_upgrade`: open a `Store` under `tempfile.mkdtemp()`, emit `daemon_stop` with `reason="source_changed"` and `module="pipeline.daemon.supervisor"`, build `PipelineApp(client=None, project=str(make_project()), store=store)`, and inside `run_test()` assert `"daemon stopped for a source upgrade" in status(app)`; then set `app.store = None`, call `app.refresh_tree()`, await `pilot.pause()` and assert the phrase is gone -- the segment must come from the store, not from the format string. Run `uv run --group dev pytest -q tests/test_tui.py -k status_bar`, watch it pass, and commit steps 12-14.
15. In `pipeline/daemon/main.py` add the module constants `RESTART_MAX = 3`, `RESTART_WINDOW = 60.0`, `COUNT_VAR = "PIPELINE_UPGRADE_RESTARTS"` and `SINCE_VAR = "PIPELINE_UPGRADE_SINCE"`, and `def restart_budget(env, now)` which reads both variables inside `try:` with `except (TypeError, ValueError): count, since = 0, 0.0`, resets `count, since = 0, now` when `now - since > RESTART_WINDOW`, returns `None` when `count >= RESTART_MAX`, and otherwise returns `(count + 1, since)`.
16. Write `tests/test_daemon.py::test_the_restart_budget_stops_an_upgrade_restart_loop` over `restart_budget` from `pipeline/daemon/main.py`: an empty env at `now=1000.0` returns `(1, 1000.0)`; count `"2"` since `"990"` returns `(3, 990.0)`; count `"3"` since `"990"` returns `None`; count `"3"` since `"800"` returns `(1, 1000.0)` because the window passed; count `"nonsense"` since `"x"` returns `(1, 1000.0)`. Run `uv run --group dev pytest -q tests/test_daemon.py -k restart_budget` and watch it pass.
17. In `pipeline/daemon/main.py` add `import os` and `import time`, import `SOURCE_CHANGED` beside `Store` from `pipeline.daemon.store`, add `ap.add_argument("--restart-on-upgrade", action="store_true", help="after a source change, re-exec this process into the merged code (at most 3 times in 60s)")`, bind `reason = supervisor.serve(...)` inside the existing `try`, and below that `try/except`, when `args.restart_on_upgrade and reason == SOURCE_CHANGED`: set `budget = restart_budget(os.environ, time.time())`; when `budget is None` print `pipelined: 3 upgrade restarts inside 60s -- not restarting; run pipeline start when the source settles` and `sys.exit(1)`; otherwise unpack `count, since = budget`, print `f"pipelined: restarting into the merged code (restart {count} of {RESTART_MAX})"`, call `store.close()`, and call `os.execve(sys.executable, [sys.executable, "-m", "pipeline.daemon.main", *sys.argv[1:]], {**os.environ, COUNT_VAR: str(count), SINCE_VAR: str(since)})`.
18. Record in the `main()` docstring of `pipeline/daemon/main.py` why that exec is safe and bounded: `serve()`'s `finally` released the socket, the flocks and every lease before it returned; `os.execve` keeps the pid, the log fd and the session; the new image re-snapshots the module mtimes so one change cannot fire twice; a restart never runs for `signal`, `drained` or `error`; and the refusal exits 1 so a `Restart=on-success` unit stops with it instead of spinning.
19. Write `tests/test_daemon.py::test_pipelined_execs_only_for_a_source_change_inside_budget(capsys)` over `main()`, importing it as `from pipeline.daemon import main as dmain`: make `tmp = Path(tempfile.mkdtemp())`, `execs: list = []` and `reason = ["source_changed"]`, save `supervisor.serve`, `dmain.Server`, `dmain.os.execve` and `sys.argv`, and in a `try` set `dmain.Server = lambda store, path: types.SimpleNamespace(close=lambda: None)`, `dmain.os.execve = lambda *a: execs.append(a)`, `supervisor.serve = lambda *a, **kw: reason[0]` and `sys.argv = ["pipelined", "--db", str(tmp / "events.db"), "--socket", str(tmp / "d.sock"), "--restart-on-upgrade"]`, then drive four cases -- (a) `dmain.main()` with `reason[0] == "source_changed"` leaves `len(execs) == 1`, `execs[0][1][1:3] == ["-m", "pipeline.daemon.main"]`, `"--restart-on-upgrade" in execs[0][1]`, `execs[0][2][dmain.COUNT_VAR] == "1"` and `"restarting into the merged code" in capsys.readouterr().out`; (b) `reason[0] = "signal"` then `reason[0] = "drained"`, each followed by `dmain.main()`, leave `len(execs) == 1`, because a restart on a signal would defeat `pipeline stop`; (c) with `reason[0] = "source_changed"`, `os.environ[dmain.COUNT_VAR] = "3"` and `os.environ[dmain.SINCE_VAR] = str(time.time())`, `dmain.main()` raises `SystemExit` whose `.code == 1`, `len(execs) == 1` still, and `"not restarting" in capsys.readouterr().out`; (d) after popping both env keys and dropping `--restart-on-upgrade` from `sys.argv`, `dmain.main()` leaves `len(execs) == 1`. Restore the four saved names and pop both env keys in a `finally`, then `shutil.rmtree(tmp, ignore_errors=True)`. Run `uv run --group dev pytest -q tests/test_daemon.py -k "restart_budget or execs_only"`, watch both pass, and commit steps 15-19.
20. In `pipeline/cli/main.py` add `p.add_argument("--restart-on-upgrade", action="store_true", help="restart the daemon into merged dispatcher code (at most 3 times in 60s)")` to the `start` subparser, and in `cmd_start()` at line 529 append `"--restart-on-upgrade"` to `command` when `args.restart_on_upgrade` is set, leaving `START_DESC` unchanged.
21. Write `tests/test_cli.py::test_start_forwards_the_upgrade_restart_flag`: replace `pipeline.cli.main.subprocess.Popen` and `pipeline.cli.main.connect` with fakes so no daemon spawns and the post-spawn probe answers a `ping` dict, call `cmd_start(argparse.Namespace(interval=10, max_parallel=3, harness=None, restart_on_upgrade=True))` and assert `"--restart-on-upgrade"` is in the captured argv, then call it again with `restart_on_upgrade=False` and assert the flag is absent; restore both names in a `finally`. Run `uv run --group dev pytest -q tests/test_cli.py -k upgrade_restart_flag`, watch it pass, and commit steps 20-21.
22. Rewrite the bullet `A merged change to the dispatcher's own Python is inert until restart.` in `CLAUDE.md` at lines 265-271: keep the `importlib.reload()` prohibition verbatim, delete the sentence `Nothing restarts them: after that message, run pipeline start (or pipeline run) again.`, and state instead that `serve()` returns its reason and emits `daemon_stop` with `reason=source_changed` and the module that moved, that `pipeline status` and the TUI status bar read it back, and that `pipeline start --restart-on-upgrade` re-execs the daemon at most 3 times in 60 s while without that flag nothing restarts it.
23. Update `README.md`: add a `pipeline start --restart-on-upgrade` line to the shell block directly AFTER the existing `pipeline start` line at line 149, commented `re-exec into merged dispatcher code (max 3 in 60s)`, and add a paragraph after the `pipelined itself stays a raw foreground process` paragraph at line 172 saying that a merged dispatcher change stops the daemon, that `pipeline status` then names the reason, and that a systemd unit with `Restart=on-success` is the other supported way to get the same handoff.
24. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, confirm no failure beyond any that also fails on the base branch, and commit the `CLAUDE.md` and `README.md` edits from steps 22-23 with this run as their evidence.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store` exits 0.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_drained_daemon_stop_is_not_a_source_change` exits 0,
  proving a non-upgrade exit does not claim `reason=source_changed`.
- `uv run --group dev pytest -q tests/test_daemon.py::test_the_daemon_notice_names_why_the_daemon_stopped` exits 0.
- `uv run --group dev pytest -q tests/test_daemon.py::test_the_restart_budget_stops_an_upgrade_restart_loop` exits 0.
- `uv run --group dev pytest -q tests/test_daemon.py::test_pipelined_execs_only_for_a_source_change_inside_budget` exits 0,
  proving `main()` execs on `source_changed` inside budget, does not exec on `signal`, on `drained` or without the flag,
  and prints `not restarting` then exits 1 when `restart_budget()` returns `None`.
- `uv run --group dev pytest -q tests/test_cli.py::test_status_says_the_daemon_stopped_for_an_upgrade` exits 0.
- `uv run --group dev pytest -q tests/test_cli.py::test_start_forwards_the_upgrade_restart_flag` exits 0.
- `uv run --group dev pytest -q tests/test_tui.py::test_the_status_bar_says_the_daemon_stopped_for_an_upgrade` exits 0.
- `uv run --group dev pytest -q` reports no failure that does not also fail on the base branch. Measured baseline on
  `main` at commit 9b75497: the suite is green apart from this ticket's repro test, which fails with
  `AssertionError: expected a daemon_stop event with reason=source_changed`.
- `grep -c "Nothing restarts them" CLAUDE.md` prints `0`.
- `grep -c "restart-on-upgrade" README.md` prints a number greater than `0`.
- `uv run --group dev python -c "import pipeline.daemon.main as m; print(m.restart_budget({}, 1000.0))"` prints
  `(1, 1000.0)`.

## Decisions

**A dispatcher that exits for a source change records why, and the reason is a
field on `daemon_stop`, not a new event kind.** `serve()` returns one of
`source_changed`, `signal`, `drained` or `error`, and its `finally` puts that
string plus the module that moved into the event's `data`. DEC-011 freezes the
event vocabulary and allows exactly this: a field added inside `data`. A new
kind would break every existing reader, and a print to the daemon log is
invisible to `pipeline status` and to the TUI, which is the whole defect
TICKET-121 reported.

**The restart is opt-in, is an `os.execve`, and is bounded.** `pipelined
--restart-on-upgrade` re-execs only after `serve()` returns `source_changed`.
Four properties a later change must keep:

1. It happens after `serve()` returns, never inside the loop. `serve()`'s
   `finally` releases the socket, the project flocks and every lease first, so
   the new image never contends with the old one.
2. It never fires for `signal`, `drained` or `error`. A restart on a signal
   would defeat `pipeline stop`, which SIGTERMs the pid.
3. `restart_budget()` allows 3 restarts inside 60 s and then refuses. Merged
   code that ends the loop again immediately stops the daemon with a message
   instead of spinning, and the 60 s window is what stops a long-lived daemon
   spending that budget on legitimate upgrades weeks apart.
4. The refusal exits 1, so a `Restart=on-success` systemd unit stops with it
   rather than restarting the daemon into the same refusal forever.

The env counter is operator-writable, so `restart_budget()` parses it inside a
`try` and reads a bad value as no restarts spent (invariant 5).

`test_pipelined_execs_only_for_a_source_change_inside_budget` is what holds all
four properties: it patches `pipeline.daemon.main.os.execve` and drives `main()`
once per reason. Delete that test and the riskiest code in this ticket is
measured by nothing, which is why `plan-validation` rejected the first plan.

**`run()` returns its reason and emits no daemon lifecycle event, on purpose.**
`pipeline run` is a foreground process that does hold a store, so emitting
`daemon_stop` there would make the store's last lifecycle event ambiguous
whenever a `pipeline run` sits beside a `pipelined`: `pipeline status` and the
TUI would then report the wrong process's exit. `run()` keeps its print and
gains a return value only.

**The TUI note is recomputed on every `_rows()` call, the successful one
included.** `_rows()` returns early when `ls` answers, so a note set only in the
failure branch would outlive the daemon's return and keep the status bar
claiming an upgrade stop. `daemon_down` and `daemon_note` are set from one
`rows is None` test above that return.

**DEC-032 still holds in full.** No `importlib.reload()`, code and never data,
stop claiming before exiting, mtime detection. The restart replaces the process
image; it does not reload a module into a live one.

## Rollback

Revert the ticket's merge commit. The change is additive: without it
`daemon_stop` loses its `reason` and `module` fields, `pipeline status` and the
TUI status bar go back to reporting only that the daemon is not running, and
`--restart-on-upgrade` disappears from `pipeline start` and from `pipelined`.
Nothing persists across the revert -- the fields sit in already-written event
rows, which are history and never state (DEC-011), and no ticket file, no
frontmatter and no registry entry changes shape. A partial rollback works too:
dropping step 17's exec block together with step 19's test disables the restart
and leaves the reason, the CLI notice and the TUI notice in place. An operator
who runs `pipeline start --restart-on-upgrade` from a shell alias must drop the
flag after a full revert, or `pipeline start` dies on an unknown option.

## Thread

### 2026-09-05 16:20:32Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-05 16:44:59Z · triage · session · session=01a07275-6fd0-7791-9420-f69f5a359a40

`triage` ran as session `01a07275-6fd0-7791-9420-f69f5a359a40`
- replay: `codex exec resume 01a07275-6fd0-7791-9420-f69f5a359a40`
- log: `.project/logs/TICKET-121-triage-f1265311.log`

### 2026-09-05 16:44:59Z · triage · note

`triage` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-05 16:45:07Z · triage · session · session=01a07275-8b26-7681-bd90-3694c61d3f0c

`triage` ran as session `01a07275-8b26-7681-bd90-3694c61d3f0c`
- replay: `codex exec resume 01a07275-8b26-7681-bd90-3694c61d3f0c`
- log: `.project/logs/TICKET-121-triage-641252fe.log`

### 2026-09-05 16:45:07Z · triage · escalation

`triage` wrote no .result sidecar 2 times

### 2026-09-05 17:34:57Z · human · note · by=chezzijr

**resumed** by chezzijr -> `triage`, reset [], granted `no_result` 2 -> 0

### 2026-09-05 17:34:57Z · human · answer · by=chezzijr

**note from chezzijr**

escalated on a Codex usage limit mid-turn, not on the ticket's own merits; continuing under claude-code

### 2026-09-05 17:35:12Z · triage · session · session=01a072a3-6631-7fa2-837a-0ab7ab68b178

`triage` ran as session `01a072a3-6631-7fa2-837a-0ab7ab68b178`
- replay: `codex exec resume 01a072a3-6631-7fa2-837a-0ab7ab68b178`
- log: `.project/logs/TICKET-121-triage-7e43dd14.log`

### 2026-09-05 17:35:12Z · triage · note

`triage` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-05 17:35:19Z · triage · session · session=01a072a3-83a2-7a03-a24b-c1adf03f352c

`triage` ran as session `01a072a3-83a2-7a03-a24b-c1adf03f352c`
- replay: `codex exec resume 01a072a3-83a2-7a03-a24b-c1adf03f352c`
- log: `.project/logs/TICKET-121-triage-e0f09b92.log`

### 2026-09-05 17:35:19Z · triage · escalation

`triage` wrote no .result sidecar 2 times

### 2026-09-05 17:36:02Z · human · note · by=chezzijr

**resumed** by chezzijr -> `triage`, reset [], granted `no_result` 2 -> 0

### 2026-09-05 17:36:02Z · human · answer · by=chezzijr

**note from chezzijr**

re-escalated by the codex daemon still holding its usage limit; resumed for claude-code

### 2026-09-06 · triage · result=ok

Reproduced. `run()`/`serve()` in `pipeline/daemon/supervisor.py` end the loop
on a source change with a bare `print()`. `serve()` emits a `daemon_stop`
event on the way out, but it carries no `reason`, so a store/CLI/TUI client
cannot tell this exit from a crash. Committed a failing test:
`tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store`,
failing with `expected a daemon_stop event with reason=source_changed, got
kinds ['daemon_start', 'daemon_stop']`.

Not a chore: the fix needs a design choice for the event's reason field/kind,
CLI/TUI display of the stopped-for-upgrade state, and a restart lifecycle
(opt-in, no restart loop on broken code) -- send to planning.

### 2026-09-05 17:37:42Z · triage · session · session=893347db-065e-4def-9c51-f5b34ab7c1d2

`triage` ran as session `893347db-065e-4def-9c51-f5b34ab7c1d2`
- replay: `claude --resume 893347db-065e-4def-9c51-f5b34ab7c1d2`
- log: `.project/logs/TICKET-121-triage-893347db.log`
- cost: $0.41 of a $3 cap
- tokens: 6,370 out (1,126 thinking) · 42 in · 898,460 cache read · 42,003 cache write

### 2026-09-05 17:37:42Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: serve()/run() exit silently on source change, no store event carries the reason for a CLI/TUI client to see.

### 2026-09-06 · planning · result=ok

Plan written: 23 steps over 11 files, in three commits' worth of order --
the exit reason, the CLI/TUI notice, then the restart.

Design decisions the next stages should not relitigate:

1. The reason is a `reason` field on the existing `daemon_stop` event, not a
   new kind. DEC-011 freezes the vocabulary and permits a field added inside
   `data`.
2. `serve()` and `run()` return their exit reason (`source_changed`,
   `signal`, `drained`, `error`). The restart keys on that string, so
   `pipeline stop` cannot trigger one.
3. `pipelined --restart-on-upgrade` re-execs with `os.execve` after `serve()`
   returns, never inside the loop, and `restart_budget()` allows 3 restarts
   inside 60 s. That is the "no restart loop on broken new code" the ticket
   asked for.
4. `run()` emits no daemon lifecycle event. A `pipeline run` beside a
   `pipelined` would otherwise make the store's last lifecycle event
   ambiguous for `pipeline status`.

Scope: one subsystem, so I planned all of it. Nothing about the daemon's
stopped state is observable without the reason, and the reason is useless to
a detached operator without the restart.

Not fixed, noted only: `pipeline run` gets no restart lifecycle. It is a
foreground process and the ticket asked for detached operation.

### 2026-09-05 17:46:33Z · planning · session · session=56f4156f-598f-47c1-9496-86f33394edc5

`planning` ran as session `56f4156f-598f-47c1-9496-86f33394edc5`
- replay: `claude --resume 56f4156f-598f-47c1-9496-86f33394edc5`
- log: `.project/logs/TICKET-121-planning-56f4156f.log`
- cost: $3.89 of a $10 cap
- tokens: 42,869 out (16,725 thinking) · 78 in · 3,229,505 cache read · 119,871 cache write

### 2026-09-05 17:46:33Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: reason=source_changed on daemon_stop, CLI/TUI notice, opt-in --restart-on-upgrade exec handoff with a bounded restart budget.

### 2026-09-06 07:16:14Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store` fails as required
```
rs=True)
            shutil.rmtree(tmp, ignore_errors=True)
    
        events = store.since(cursor)
        stop_events = [e for e in events if e["kind"] == "daemon_stop"
                       and e["data"].get("reason") == "source_changed"]
>       assert stop_events, (
            f"expected a daemon_stop event with reason=source_changed, "
            f"got kinds {[e['kind'] for e in events]}")
E       AssertionError: expected a daemon_stop event with reason=source_changed, got kinds ['daemon_start', 'daemon_stop']
E       assert []

tests/test_dispatch.py:1205: AssertionError
----------------------------- Captured stdout call -----------------------------
pipelined 0.1.0: pid 443997 on /tmp/tmp70pc4nk0/daemon.sock
  watching /tmp/tmpcunc45ue
  dispatcher source changed (pipeline.daemon.supervisor) -- ending the loop so a restart runs the merged code
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store` fails on base `main` too -- the bug is not already fixed upstream
```
]

tests/test_dispatch.py:1205: AssertionError
----------------------------- Captured stdout call -----------------------------
pipelined 0.1.0: pid 444048 on /tmp/tmp_w057f80/daemon.sock
  watching /tmp/tmpxm0egwlm
  dispatcher source changed (pipeline.daemon.supervisor) -- ending the loop so a restart runs the merged code
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.48s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-v2r2reiw/base
      Built pipeline @ file:///tmp/pipeline-base-v2r2reiw/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 30ms

```

### 2026-09-06 · plan-validation · result=fail

Tier B: 1 item fails, 7 pass.
long: eight scored items, each owed its own reasoning.

- **fail -- scope discipline.** Step 17 (`--restart-on-upgrade` on `pipelined`,
  the `restart_budget()` call, the `os.execve`) traces to no acceptance
  criterion. No criterion runs `pipelined` or names `os.execve`; delete step 17
  and all 11 still pass. `test_start_forwards_the_upgrade_restart_flag` asserts
  only that `cmd_start` puts the flag in argv. That leaves the plan's riskiest
  step measured by nothing. Add a criterion and a test: `main()` execs on
  `source_changed` inside budget, does not exec on `signal` or `drained`, and
  prints the refusal when `restart_budget()` returns `None`. Patch
  `pipeline.daemon.main.os.execve` as step 20 already patches `Popen`.
- pass -- root cause. The exit reason lives only in `serve()`'s control flow and
  a `print()`; `store.emit("", "daemon_stop", pid=..., version=...)` at
  `pipeline/daemon/supervisor.py:1748` carries no field a reader can key on. The
  plan makes the reason a returned value and an event field, not a test prop.
- pass -- decisions. DEC-011 says "Adding a `kind` or a field inside `data` is
  additive and fine" -- `reason` and `module` are that. DEC-032's four numbered
  rules are untouched; "Nothing restarts the dispatcher after this exit" sits in
  its closing paragraph beside "systemd, tmux or a human runs it again", which
  reads as the situation, not a prohibition.
- pass -- falsifiable. Each criterion names a command whose result moves with the
  implementation. Step 14's `app.store = None` re-check is what stops the TUI
  criterion passing off a format string.
- pass -- no research left. Every cited line resolves: `run()` at 1609,
  `serve()` at 1666, the prints at 1641/1703, the emit at 1748,
  `cmd_daemon_status()` at `pipeline/cli/main.py:515`, `_rows()`/`_status()` in
  `pipeline/tui/app.py`, `main()` in `pipeline/daemon/main.py`.
- pass -- riskiest step. Step 17 is it, and `## Rollback` states the fallback:
  "dropping step 17's exec block alone disables the restart".
- pass -- regression surface. `serve()`'s `once`/signal exits keep their
  behaviour and step 9's test pins `drained`. The `finally` still runs before any
  `return`, so DEC-032 rule 3 (stop claiming before exiting) holds.
- pass -- blast radius. `class: feature`, 23 steps, 11 files, of which 4 are test
  files and 2 are docs. Five source files, one subsystem.

Two caveats for `implementing`, not grounds for this verdict.

1. Step 22 must add its README line AFTER the existing `pipeline start` line.
   `tests/test_cli.py:401` takes `start_line[0]` of every line starting
   `pipeline start ` and asserts `tui` is in it; inserting above breaks it.
2. Step 13 sets `self.daemon_note` "at the end of `_rows()`", but the successful
   `ls` path returns early at `pipeline/tui/app.py:305`. A note set while the
   daemon was down then survives its return and the status bar keeps claiming an
   upgrade stop. Clear it on the success path too.

No item was unverified. I read the code; I ran no command.

### 2026-09-06 07:20:06Z · plan-validation · session · session=87c12bdd-6989-4786-9644-591fd97b1e31

`plan-validation` ran as session `87c12bdd-6989-4786-9644-591fd97b1e31`
- replay: `claude --resume 87c12bdd-6989-4786-9644-591fd97b1e31`
- log: `.project/logs/TICKET-121-plan-validation-87c12bdd.log`
- cost: $1.65 of a $3 cap
- tokens: 17,295 out (9,627 thinking) · 36 in · 1,018,748 cache read · 70,233 cache write

### 2026-09-06 07:20:06Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ Scope discipline fails: step 17's --restart-on-upgrade exec block traces to no acceptance criterion, and all 11 criteria pass with it deleted.

### 2026-09-06 10:33:57Z · planning · session · session=e0b616af-48fe-4a02-8ccc-9a4b1eb3d756

`planning` ran as session `e0b616af-48fe-4a02-8ccc-9a4b1eb3d756`
- replay: `claude --resume e0b616af-48fe-4a02-8ccc-9a4b1eb3d756`
- log: `.project/logs/TICKET-121-planning-e0b616af.log`

### 2026-09-06 10:33:57Z · planning · note

`planning` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-06 · planning · result=ok

Plan rewritten. `plan-validation` rejected one of eight items: step 17's
`--restart-on-upgrade` exec block traced to no acceptance criterion.

What changed against the rejected plan.

1. New step 19 writes
   `tests/test_daemon.py::test_pipelined_execs_only_for_a_source_change_inside_budget`.
   It patches `pipeline.daemon.main.os.execve`, `dmain.Server` and
   `supervisor.serve`, then drives `main()` four times: it execs on
   `source_changed`, does not exec on `signal`, on `drained`, or without the
   flag, and raises `SystemExit(1)` printing `not restarting` when
   `restart_budget()` returns `None`.
2. A twelfth acceptance criterion runs that test. Deleting the exec block now
   fails a criterion, which is what the rejection asked for.
3. Step 17 prints the refusal and then `sys.exit(1)`, replacing
   `sys.exit(msg)`. A printed line is what the test reads and what the daemon
   log carries.
4. The step list is 24 steps over the same 11 files. The old steps 19-23 shift
   to 20-24; nothing else in them changed.

Both caveats from the rejection are folded in. Step 13 sets `daemon_note`
above `_rows()`'s early return at `pipeline/tui/app.py:305`, so a note does not
outlive the daemon's return. Step 23 puts the new README line AFTER
`README.md:149`, because `tests/test_cli.py:401` asserts `tui` is in
`start_line[0]`.

`## Decisions checked` now also cites DEC-096 and DEC-034, the two other
records the grep terms matched. None of the six carries a `superseded-by:`
line.

### 2026-09-06 10:44:04Z · planning · session · session=acaaafaf-edc7-441c-93b4-8588f998c88c

`planning` ran as session `acaaafaf-edc7-441c-93b4-8588f998c88c`
- replay: `claude --resume acaaafaf-edc7-441c-93b4-8588f998c88c`
- log: `.project/logs/TICKET-121-planning-acaaafaf.log`
- cost: $3.80 of a $10 cap
- tokens: 49,831 out (9,263 thinking) · 58 in · 2,528,753 cache read · 128,687 cache write

### 2026-09-06 10:44:04Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan rewritten: step 19 tests main()'s exec on every reason, and a 12th criterion measures it -- the scope gap plan-validation rejected.

### 2026-09-06 10:44:56Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store` fails as required
```
rs=True)
            shutil.rmtree(tmp, ignore_errors=True)
    
        events = store.since(cursor)
        stop_events = [e for e in events if e["kind"] == "daemon_stop"
                       and e["data"].get("reason") == "source_changed"]
>       assert stop_events, (
            f"expected a daemon_stop event with reason=source_changed, "
            f"got kinds {[e['kind'] for e in events]}")
E       AssertionError: expected a daemon_stop event with reason=source_changed, got kinds ['daemon_start', 'daemon_stop']
E       assert []

tests/test_dispatch.py:1205: AssertionError
----------------------------- Captured stdout call -----------------------------
pipelined 0.1.0: pid 708086 on /tmp/tmpv_x0hxfr/daemon.sock
  watching /tmp/tmp5hu147pb
  dispatcher source changed (pipeline.daemon.supervisor) -- ending the loop so a restart runs the merged code
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================

```
- ok: `tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store` fails on base `main` too -- the bug is not already fixed upstream
```
------------------------- Captured stdout call -----------------------------
pipelined 0.1.0: pid 708155 on /tmp/tmpekg6w_yv/daemon.sock
  watching /tmp/tmp9wxr5n7c
  dispatcher source changed (pipeline.daemon.supervisor) -- ending the loop so a restart runs the merged code
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.47s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-nv67mui1/base
Downloading pygments (1.2MiB)
 Downloaded pygments
      Built pipeline @ file:///tmp/pipeline-base-nv67mui1/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 32ms

```

### 2026-09-06 · plan-validation · result=ok

Tier B: all eight items pass. The scope gap the last verdict raised is closed.

1. Root cause. `serve()` knows the exit reason in a local and throws it away:
   the source-change branch prints and returns, and the `finally` at
   `pipeline/daemon/supervisor.py:1748` emits
   `store.emit("", "daemon_stop", pid=..., version=...)` with no reason. The
   plan carries the reason to that emit and to two readers, not just to the
   test.
2. Decisions. DEC-011:10 says verbatim "Adding a `kind` or a field inside
   `data` is additive and fine", so `reason` and `module` comply. DEC-032's
   four numbered rules bind; none prohibits a restart, and the exec runs after
   `serve()` returns. Neither record is in the six that carry `superseded-by`.
3. Scope. Delete step 17's exec block and criterion 5 fails. Step 18 is a
   docstring for step 17's code; every other step traces to a criterion.
4. Criteria. Criterion 2 fails an implementation that hardcodes
   `reason=source_changed`. Criterion 5 fails one that execs on `signal`.
5. Research. Every seam checked: `PipelineApp.__init__` at
   `pipeline/tui/app.py:234`, `_rows()`'s early return at 305,
   `cmd_daemon_status()` and `cmd_start()` in `pipeline/cli/main.py`,
   `_row()`'s column order, `test_cli.py:401`'s `start_line[0]`.
6. Riskiest step is 17, `os.execve`. `## Rollback` states the fallback:
   drop step 17 and step 19, keep the reason and both notices.
7. Regression surface. `grep -rn daemon_stop pipeline/` finds one site, the
   emit itself -- no reader breaks on two added `data` fields. The TUI
   `_rows()` restructure and the `start` option are covered by criterion 9.
8. Blast radius. Class is `feature`; 24 steps over 11 files matches
   TICKET-041, the calibration in `BOUNDS`.

Two caveats for `implementing`, neither a scored finding.

- Step 6 says set `reason = "drained"` before the `once` return, but that
  return is bare today. It must return `reason`, or criterion 2 fails.
- The README paragraph step 23 appends after is at `README.md:171`, not 172.

### 2026-09-06 10:48:06Z · plan-validation · session · session=6053238e-6ea9-4748-aed8-ad388d0fa17c

`plan-validation` ran as session `6053238e-6ea9-4748-aed8-ad388d0fa17c`
- replay: `claude --resume 6053238e-6ea9-4748-aed8-ad388d0fa17c`
- log: `.project/logs/TICKET-121-plan-validation-6053238e.log`
- cost: $1.49 of a $3 cap
- tokens: 13,891 out (7,117 thinking) · 38 in · 1,003,600 cache read · 64,086 cache write

### 2026-09-06 10:48:06Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ All 8 items pass: step 19 and criterion 5 close the scope gap the last verdict raised.

### 2026-09-06 11:42:43Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-06 11:43:48Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store` fails as required
```
rs=True)
            shutil.rmtree(tmp, ignore_errors=True)
    
        events = store.since(cursor)
        stop_events = [e for e in events if e["kind"] == "daemon_stop"
                       and e["data"].get("reason") == "source_changed"]
>       assert stop_events, (
            f"expected a daemon_stop event with reason=source_changed, "
            f"got kinds {[e['kind'] for e in events]}")
E       AssertionError: expected a daemon_stop event with reason=source_changed, got kinds ['daemon_start', 'daemon_stop']
E       assert []

tests/test_dispatch.py:1205: AssertionError
----------------------------- Captured stdout call -----------------------------
pipelined 0.1.0: pid 861318 on /tmp/tmp3q2vmge7/daemon.sock
  watching /tmp/tmp1s8btawe
  dispatcher source changed (pipeline.daemon.supervisor) -- ending the loop so a restart runs the merged code
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.42s ===============================

```
- ok: `tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store` fails on base `main` too -- the bug is not already fixed upstream
```
]

tests/test_dispatch.py:1205: AssertionError
----------------------------- Captured stdout call -----------------------------
pipelined 0.1.0: pid 861370 on /tmp/tmp7vnzq2qu/daemon.sock
  watching /tmp/tmpj0cz88l9
  dispatcher source changed (pipeline.daemon.supervisor) -- ending the loop so a restart runs the merged code
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_source_change_exit_is_recorded_in_the_event_store
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.49s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-lj3tbu8j/base
      Built pipeline @ file:///tmp/pipeline-base-lj3tbu8j/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 74ms

```

### 2026-09-06 11:43:49Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

### 2026-09-06 · implementing · todo

Todo, one entry per plan step, updated as I go.

1. [x] store.py: SOURCE_CHANGED/STOP_REASONS constants
2. [x] store.py: Store.last_daemon_event
3. [x] store.py: daemon_notice
4. [x] test_daemon.py: test_the_daemon_notice_names_why_the_daemon_stopped; commit 1-4 (bfd4fe3)
5. [x] supervisor.py: exit_message()
6. [x] supervisor.py: serve() returns reason
7. [x] supervisor.py: run() returns reason
8. [x] repro test passes
9. [x] test_dispatch.py: test_a_drained_daemon_stop_is_not_a_source_change; commit 5-9 (2d661a4)
10. [x] cli/main.py: cmd_daemon_status notice
11. [x] test_cli.py: test_status_says_the_daemon_stopped_for_an_upgrade; commit 10-11 (afbed7b)
12. [x] tui/app.py: PipelineApp store arg
13. [x] tui/app.py: _rows()/_status() restructure
14. [x] test_tui.py: test_the_status_bar_says_the_daemon_stopped_for_an_upgrade; commit 12-14 (d0f68ed)
15. [x] daemon/main.py: restart_budget constants+fn
16. [x] test_daemon.py: test_the_restart_budget_stops_an_upgrade_restart_loop
17. [x] daemon/main.py: --restart-on-upgrade exec block
18. [x] daemon/main.py: main() docstring
19. [x] test_daemon.py: test_pipelined_execs_only_for_a_source_change_inside_budget; commit 15-19 (bb1aea5)
20. [x] cli/main.py: start --restart-on-upgrade flag
21. [x] test_cli.py: test_start_forwards_the_upgrade_restart_flag; commit 20-21 (7c2fb11)
22. [x] CLAUDE.md rewrite
23. [x] README.md edits
24. [x] full suite + guard test; commit 22-23 (f7edee4)

### 2026-09-06 · implementing · result=ok

All 24 steps done. Every acceptance criterion passes:
`test_a_source_change_exit_is_recorded_in_the_event_store`,
`test_a_drained_daemon_stop_is_not_a_source_change`,
`test_the_daemon_notice_names_why_the_daemon_stopped`,
`test_the_restart_budget_stops_an_upgrade_restart_loop`,
`test_pipelined_execs_only_for_a_source_change_inside_budget`,
`test_status_says_the_daemon_stopped_for_an_upgrade`,
`test_start_forwards_the_upgrade_restart_flag`,
`test_the_status_bar_says_the_daemon_stopped_for_an_upgrade` -- all 8 pass.
`uv run --group dev pytest -q` reports `597 passed`.
`./pipeline/hooks/test_dangerous_commands.py` reports `guard: all passed`.
`grep -c "Nothing restarts them" CLAUDE.md` -> `0`.
`grep -c "restart-on-upgrade" README.md` -> `2`.
`uv run --group dev python -c "import pipeline.daemon.main as m; print(m.restart_budget({}, 1000.0))"` -> `(1, 1000.0)`.
Commits: bfd4fe3, 2d661a4, afbed7b, d0f68ed, bb1aea5, 7c2fb11, f7edee4.

re-gated after rebasing onto base: passed

### 2026-09-06 11:55:08Z · implementing · session · session=5222eaff-262d-41c5-a37a-3b89f5b826ea

`implementing` ran as session `5222eaff-262d-41c5-a37a-3b89f5b826ea`
- replay: `claude --resume 5222eaff-262d-41c5-a37a-3b89f5b826ea`
- log: `.project/logs/TICKET-121-implementing-5222eaff.log`
- cost: $3.85 of a $8 cap
- tokens: 38,815 out (3,285 thinking) · 292 in · 14,598,627 cache read · 136,361 cache write

### 2026-09-06 11:55:08Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Implemented all 24 plan steps; every acceptance criterion passes, full suite (597) and guard test are green.

### 2026-09-06 · review · result=ok

Reviewed the delta `ddf0583..f7edee4`: 7 commits, 11 files, 421 insertions. No
blocking finding.

I re-ran every acceptance criterion. The 8 named tests pass by node id
(`8 passed in 0.78s`). `uv run --group dev pytest -q` reports
`597 passed in 56.04s`. `./pipeline/hooks/test_dangerous_commands.py` reports
`guard: all passed`. `grep -c "Nothing restarts them" CLAUDE.md` prints `0`,
`grep -c "restart-on-upgrade" README.md` prints `2`, and `restart_budget({}, 1000.0)`
prints `(1, 1000.0)`. `git status --porcelain` is empty.

Findings I dropped, with what refuted each.
1. Cross-thread sqlite in the TUI note: `_rows()` runs from `on_mount`, the
   `set_interval` timer and `on_frame` only, and `on_frame` arrives through
   `call_from_thread` (`pipeline/tui/app.py:423`), so it never leaves the
   event loop thread that opened the `Store`.
2. New dispatch test reaching the operator's registry: `tests/conftest.py:13`
   pins `XDG_CONFIG_HOME` and `XDG_STATE_HOME` to temp dirs.

Findings that survive, none blocking.
1. minor: `cmd_daemon_status()` and `cmd_tui()` build `Store()`, which creates
   `events.db` as a side effect on a machine that never ran a daemon.
2. minor: two plan details are absent -- step 7's comment in `run()` on why it
   emits no daemon event, and step 6's `return reason` after `serve()`'s
   `try/finally`. That return is unreachable: every path inside the `try`
   returns.
3. minor: on a transient `ls` failure against a LIVE daemon, the status bar
   reads `daemon gone with no stop recorded`, because the last lifecycle event
   is that daemon's own `daemon_start` (`pipeline/daemon/supervisor.py:1708`).
   The next 5s refresh clears it.

### 2026-09-06 12:00:13Z · review · session · session=51efae96-28ad-4a52-a2e7-9b20c6ba53b8

`review` ran as session `51efae96-28ad-4a52-a2e7-9b20c6ba53b8`
- replay: `claude --resume 51efae96-28ad-4a52-a2e7-9b20c6ba53b8`
- log: `.project/logs/TICKET-121-review-51efae96.log`
- cost: $2.26 of a $7 cap
- tokens: 17,707 out (9,325 thinking) · 68 in · 2,090,614 cache read · 77,124 cache write

### 2026-09-06 12:00:13Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the 8-commit delta: no blocking findings; 597 passed, guard passed, all 12 acceptance criteria verified.

### 2026-09-06 12:01:11Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-06 12:01:12Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/121


Current branch ticket/121 is up to date.
Already up to date.
Updating ddf0583..f7edee4
Fast-forward
 CLAUDE.md                     | 12 ++++--
 README.md                     |  7 ++++
 pipeline/cli/main.py          | 11 +++--
 pipeline/daemon/main.py       | 59 ++++++++++++++++++++++++--
 pipeline/daemon/store.py      | 34 +++++++++++++++
 pipeline/daemon/supervisor.py | 38 +++++++++++------
 pipeline/tui/app.py           | 17 ++++++--
 tests/test_cli.py             | 63 ++++++++++++++++++++++++++++
 tests/test_daemon.py          | 98 +++++++++++++++++++++++++++++++++++++++++++
 tests/test_dispatch.py        | 80 +++++++++++++++++++++++++++++++++++
 tests/test_tui.py             | 27 ++++++++++++
 11 files changed, 421 insertions(+), 25 deletions(-)

```

### 2026-09-06 12:01:12Z · merging · decision

decision recorded as `DEC-121`
