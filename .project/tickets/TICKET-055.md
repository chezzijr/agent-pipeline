---
id: TICKET-055
stage: planning
class: bugfix
branch: ticket/055
test_file: tests/test_tui.py::test_tail_log_renders_a_pty_dump_at_its_own_width_not_120
files_declared:
- pipeline/pty/host.py
- pipeline/pty/__init__.py
- pipeline/daemon/supervisor.py
- pipeline/daemon/server.py
- pipeline/tui/app.py
- tests/test_pty.py
- tests/test_tui.py
- CLAUDE.md
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 17
  plan_files: 8
  no_result: 0
lease:
  holder: planning-1115322
  expires: '2026-08-24T15:33:57.944321+00:00'
last_session:
  stage: plan-validation
  id: 8b6dc99a-5d6a-4374-a84c-946cc6331f03
  log: .project/logs/TICKET-055-plan-validation-8b6dc99a.log
---

## Summary

tui renders a PTY log at 120 columns whatever width wrote it: `render_pty()`
(`pipeline/tui/app.py:103`) always replays on `Screen()`, 40x120
(`pipeline/pty/host.py:28`), and `_op_resize` (`pipeline/daemon/server.py:624`)
records the new width nowhere. See `## Reproduction` for the failing test.

plan-validation rejected the plan on one item of eight. Step 13's test cannot
pass as written: `b"pad\n"` is a bare line feed, so the filler fills the screen,
`\x1b[1A` lands on a pad row instead of clamping at row 0, and the `B` frame
survives below `SHORT` at 150 and at 120 alike. Verified fix in the thread: put
`b"\x1b[H\x1b[2J"` before `b"B" * 140`, as step 10 already does. Every other
item passes, and steps 1, 9, 10, 11 and 12 were re-run and hold.

Planning wrote a 17-step plan. The log carries its own geometry, as an OSC
marker `\x1b]9999;<rows>;<cols>\x07`: `spawn()` writes one when it opens an
interactive log, `_op_resize` writes one per resize, and `render_pty()` replays
segment by segment, resizing where the marker says the daemon resized. Verified
in this worktree: pyte ignores the marker, and that replay reproduces the live
screen exactly.

Three gotchas the implementer must keep. No marker in a batch log -- the raw ESC
is what tells `tail_log` a log is not stream-json (DEC-039). A marker is hostile
input, clamped to 1..1000. `tests/test_tui.py` adds no import base lacks, or the
gate's base run errors at collection instead of failing (DEC-017).

Evidence from triage, unchanged:
`.project/logs/TICKET-035-planning-ee0c98d7.log` is a real 660 KB dump written
at 124 columns. Rendering it through the shipped code:

    $ uv run python -c "from pipeline.tui.app import tail_log; \
        print('\n'.join(map(repr, tail_log('.', 'TICKET-035')[:4])))"
    '●dfash(python3 /tmp/claude-1000/...-TICKET-035/ee0c98d7-d6b5-40bf-9e4d-31160bd'
    "4dfa\xa0T6/scratchpad/check.py)quick side question without interrupting Claude's current work"
    '  ⎿ \xa0steps: 10'
    "  ⎿ \xa0W 1: OK ['tests/test_stages.py'] (320 chars)"

Two frames superimposed: `Bash(` and `dfash(`, a tool call and a tip on one
line. Feeding the identical bytes to `Screen(40, 124)` instead is clean:

    '● Bash(python3 /tmp/claude-1000/...-TICKET-035/ee0c98d7-d6b5-40bf-9e4d-31160bd4dfa'
    '      6/scratchpad/check.py)'
    '  ⎿ \xa0steps: 10'
    "       1: OK ['tests/test_stages.py'] (320 chars)"

The `MAX_TAIL` truncation is not involved: full file and truncated tail render
byte-identically at each width.

Expected: a PTY dump renders at the width it was written at, so no line of the
final screen carries characters from an earlier frame. A dump produced on a
screen of width W != 120 must come back through `render_pty()` matching that
screen's own `display`.

long: the summary keeps the filer's 660 KB example above, because it is the only
real-world dump on record and `## Reproduction` holds a synthetic one. The
filer's "suggestion only, planning decides" paragraph is gone: planning took the
suggestion, and `## Decisions` now states it as a rule with its bounds.

## Reproduction

`tests/test_tui.py::test_tail_log_renders_a_pty_dump_at_its_own_width_not_120`

Writes a synthetic PTY dump: a first frame that wraps into two rows at a
native width of 150 (`b'B' * 140`), then a cursor-relative redraw
(`\x1b[1A\r\x1b[KSHORT\n`) that erases only the row the cursor moved to and
writes `SHORT`. Replayed on `Screen()` -- the hardcoded 40x120 `render_pty()`
always uses -- the 140-char frame wraps into two rows instead of one at width
150, the redraw's up-move and erase land on the wrong row, and the second
row's leftover `B`s survive under `SHORT`. At the log's actual width (150)
the same bytes render clean.

Command: `uv run --group dev pytest -q tests/test_tui.py -k test_tail_log_renders_a_pty_dump_at_its_own_width_not_120`

Output:
```
AssertionError: replaying at the log's own width (150) should be clean, got ['SHORT', 'BBBBBBBBBBBBBBBBBBBB']
assert ['SHORT', 'BB...BBBBBBBBBBBB'] == ['SHORT']
```

expect: AssertionError: replaying at the log's own width (150) should be clean, got ['SHORT', 'BBBBBBBBBBBBBBBBBBBB']

Committed on `ticket/055` as `57bf3a5`.

## Digest

Files this plan touches, one responsibility each:
- `pipeline/pty/host.py` -- owns the marker format: `geom_marker()` writes it, `last_geometry()` parses it, `MAX_DIM` bounds it. Nothing else knows the bytes.
- `pipeline/daemon/supervisor.py` -- `spawn()` (line 387, `fh = log.open("wb")`) writes the opening marker, for an interactive stage only.
- `pipeline/daemon/server.py` -- `_op_resize()` (line 624) writes a marker at every resize, next to `host.set_winsize` + `rec["screen"].resize`.
- `pipeline/tui/app.py` -- `render_pty()` (line 103) and `tail_log()` (line 118) read the markers back.
- `pipeline/pty/__init__.py` -- the package facade's `__all__`.
- `tests/test_pty.py`, `tests/test_tui.py` -- the checks.

Key functions and entry points:
- `render_pty(data)` builds `Screen()` = `pyte.Screen(120, 40)` and feeds the whole dump at that one width. `tail_log()` is its only caller; the sniff `b"\x1b" in data` routes a log to it (DEC-039).
- `Screen.resize(rows, cols)` (`pipeline/pty/host.py:123`) forwards to `pyte.Screen.resize`, which truncates and pads without reflow -- the same call `_op_resize` makes on the live screen.
- `rec["fh"]` is the open log file handle of every child, and `supervisor.pump()` tees the child's bytes into it. `tests/test_pty.py:child()` builds a record with the same key, so a server test can read the log back.
- `_dim()` (`pipeline/daemon/server.py:78`) already bounds a socket-supplied dimension to `1..MAX_DIM` (1000).

Gotchas, each checked against the code:
- The marker must NOT go into a batch log. `tail_log()` decides "PTY dump, not stream-json" on `b"\x1b" in data` (DEC-039), so an ESC in a headless stage's log would send stream-json through pyte.
- The gate re-runs the reproduction with the branch's test file copied into a checkout of base (`_base_findings`, `pipeline/core/gate.py:123`, DEC-017). An import at the top of `tests/test_tui.py` that base lacks turns that run into a collection error, whose output does not carry the test's name, and the gate reports "base proves nothing". So `tests/test_tui.py` adds no import base lacks: it spells the marker literally as `b"\x1b]9999;40;150\x07"` and imports only `render_pty` and `MAX_TAIL`, which both exist today.
- `_op_resize` writes the marker at the same point it calls `rec["screen"].resize`, and does NOT drain the pty first. Bytes still unread in the master reach the live screen after the resize; feeding them after the marker on replay reproduces that screen exactly. Draining first would produce a screen the daemon never showed.
- Verified in this worktree: `pyte.ByteStream` ignores `\x1b]9999;40;150\x07` entirely -- a `Screen(4, 20)` fed the marker plus `hi` shows `hi` -- so an old log with no marker, and a real terminal `cat`-ing a new one, are both unaffected.
- Verified: replaying `b"\x1b]9999;40;120\x07" + b"A"*130 + b"\x1b]9999;40;150\x07" + b"\r\x1b[Ktail\n"` with a resize at the marker gives `['AAA...A' (120 chars), 'tail']`, equal to a live `Screen(40, 120)` fed, resized to 150, fed. Replaying the same bytes wholly at 150 gives `['tail']` -- a different screen, which is why the replay resizes mid-stream instead of picking one width up front.
- `MAX_TAIL` (256 KiB, `pipeline/tui/app.py:44`) cuts the head off a big log, and `spawn()`'s marker sits in that head. `tail_log()` already reads the whole file (`read_bytes()`), so it scans the head for the geometry and still feeds pyte only the tail. Measured: 256 KiB of `pad\n` through pyte takes 0.4 s.
- `\d{1,4}` plus the clamp is the whole hostile-input answer: the child's stdout is teed into the same file, so a child can print a marker. The worst case is a replay at a bounded wrong size in one TUI pane.
- No file here is in `machine.FENCED`, so this ticket does not park at `awaiting-merge` for that reason.

## Decisions checked

Grepped `.project/decisions/` for `pty|PTY|pyte|screen|render_pty|tui|TUI|width|resize|log`; 15 records matched and 4 constrain this change.
- DEC-039 (active) -- `tail_log()` tells a PTY dump from stream-json by `b"\x1b" in data`, never by the stage's `mode:`, and the fallback direction is the safe one. This plan complies and strengthens it: the marker goes only into an interactive log, so a batch log still carries no ESC, and an interactive stage whose output happens to hold no escape now still routes to pyte. DEC-039's `render_pty()` clause also holds: the trailing-blank drop and the `["(blank screen)"]` return both stay.
- DEC-019 (active) -- `resize` is writer-only and claims the slot exactly as `input` does. The log write goes after the `self._writer(rec, conn)` claim, so a read-only client still cannot move the width.
- DEC-017 (active) -- the Tier A reproduction is a two-run fact and the base run is load-bearing. Step 9 rewrites the reproduction test in place, keeps its name, and adds no import base lacks, so the base run still fails with the test's name in its output.
- DEC-011 (active) -- the stored event vocabulary is frozen and `other` is not in it. That is why the geometry is not a new event kind in the SQLite store; the log carries it instead.
Read and not binding: DEC-021, DEC-023, DEC-046 -- key handling and thread growth, no overlap. No record is superseded by this plan.

## Plan

1. Add `test_the_geometry_marker_round_trips_and_clamps` to `tests/test_pty.py`: assert `host.geom_marker(40, 124) == b"\x1b]9999;40;124\x07"`; `host.last_geometry(b"") == (host.ROWS, host.COLS)`; `host.last_geometry(b"no marker here") == (host.ROWS, host.COLS)`; `host.last_geometry(host.geom_marker(40, 124)) == (40, 124)`; `host.last_geometry(host.geom_marker(40, 124) + host.geom_marker(50, 160)) == (50, 160)` (last wins); `host.last_geometry(b"\x1b]9999;99999;99999\x07") == (host.ROWS, host.COLS)` (five digits do not match); `host.last_geometry(b"\x1b]9999;0;0\x07") == (1, 1)`; `host.last_geometry(b"\x1b]9999;40;9999\x07") == (40, host.MAX_DIM)`; and that pyte ignores the marker -- `s = host.Screen(4, 20)`, `s.feed(host.geom_marker(40, 124) + b"hi")`, `assert s.display[0].strip() == "hi"`.
2. Run `uv run --group dev pytest -q tests/test_pty.py -k geometry_marker` and expect `AttributeError: module 'pipeline.pty.host' has no attribute 'geom_marker'`.
3. Implement the marker in `pipeline/pty/host.py`: add `import re`; below `ROWS, COLS = 40, 120` add `MAX_DIM = 1000`, `GEOM_OSC = re.compile(rb"\x1b\]9999;(\d{1,4});(\d{1,4})\x07")`, `def geom_marker(rows, cols) -> bytes` returning `b"\x1b]9999;%d;%d\x07" % (rows, cols)`, and `def last_geometry(data, rows=ROWS, cols=COLS) -> tuple` which walks `GEOM_OSC.finditer(data)` keeping the last match, returns `(rows, cols)` when there is none, and otherwise returns both groups as ints clamped by `min(max(v, 1), MAX_DIM)`; comment that the child's stdout is teed into the same log so this is hostile input, and that only an interactive log gets a marker because an ESC in a batch log sends stream-json through pyte (DEC-039).
4. Wire the new names: in `pipeline/pty/__init__.py` import `MAX_DIM`, `geom_marker` and `last_geometry` and add all three to `__all__`; in `pipeline/daemon/server.py` replace `MAX_DIM = 1000   # a terminal, not a memory allocator: pyte allocates rows*cols` with `MAX_DIM = host.MAX_DIM   # one bound for the ioctl, the pyte allocation and the log marker`, leaving `_dim()` and its message unchanged. Run `uv run --group dev pytest -q tests/test_pty.py -k geometry_marker`, expect `1 passed`, and commit as `feat(TICKET-055): record a pty log's geometry in an OSC marker`.
5. Add `test_resize_records_the_width_in_the_log` to `tests/test_pty.py` after `test_resize_reaches_both_the_child_and_the_screen`: build `rec = child(tmp, server, cmd=r'read x')`, `attach`, `ask(server, a, id=2, op="resize", rows=50, cols=160)`, then assert `host.geom_marker(50, 160) in (tmp / "stage.log").read_bytes()`, with the same `finally:` teardown as its neighbour (`rec["proc"].terminate()`, `supervisor.close_child(rec)`, `server.close()`).
6. Add `test_an_interactive_log_opens_with_its_geometry` to `tests/test_pty.py` after `test_an_interactive_stage_runs_headless_when_nothing_can_attach`, copying its two-spawn shape: `supervisor.spawn(tmp, tmp, "TICKET-001", "planning", harness("fake"), Poller())` then assert `b"\x1b]9999;" not in rec["log"].read_bytes()` (a batch log keeps no ESC, DEC-039), and the same spawn with `Attachable()` then assert `host.geom_marker(host.ROWS, host.COLS) in rec["log"].read_bytes()`.
7. Run `uv run --group dev pytest -q tests/test_pty.py -k "records_the_width or opens_with_its_geometry"` and expect two failures, each on a log with no `\x1b]9999;` in it.
8. Write the markers. In `pipeline/daemon/supervisor.py`, between `fh.write(f"$ {cmd}\n\n".encode())` and `fh.flush()`, add `if interactive:` / `fh.write(host.geom_marker(host.ROWS, host.COLS))`, commented as the width `render_pty()` replays at, interactive-only because a batch log must keep no ESC (DEC-039). In `pipeline/daemon/server.py` `_op_resize`, after `rec["screen"].resize(rows, cols)`, add `rec["fh"].write(host.geom_marker(rows, cols))` then `rec["fh"].flush()`, commented that the marker lands at the same point the live screen resizes, so a replay reproduces that screen rather than reflowing bytes the daemon fed after the resize. Run `uv run --group dev pytest -q tests/test_pty.py`, expect every test to pass, and commit as `fix(TICKET-055): write the geometry marker at spawn and at every resize`.
9. Rewrite the reproduction in `tests/test_tui.py`, keeping the name `test_tail_log_renders_a_pty_dump_at_its_own_width_not_120` that `test_file` cites: the log becomes `b"\x1b]9999;40;150\x07" + b"B" * 140 + b"\x1b[1A\r\x1b[KSHORT\n"`, the assertion stays `lines == ["SHORT"]` with its existing message, and the docstring says the width now rides in the log and is spelled literally here so the file still imports on base (DEC-017).
10. Add `test_render_pty_matches_the_screen_the_dump_was_written_on` to `tests/test_tui.py`, extending the module import to `from pipeline.tui.app import MAX_TAIL, PipelineApp, event_line, marker, render_pty, tail_log` (both new names exist on base): set `frames = b"\x1b[H\x1b[2J" + b"B" * 140 + b"\x1b[1A\r\x1b[KSHORT\n"`, feed a `Screen(40, 150)`, rstrip its `display` and pop trailing blanks into `want`, then assert `render_pty(b"\x1b]9999;40;150\x07" + frames) == want`.
11. Add `test_render_pty_resizes_where_the_log_says_the_screen_did` to `tests/test_tui.py`: build `want` the same way from a `Screen(40, 120)` fed `b"A" * 130`, resized to `(40, 150)`, fed `b"\r\x1b[Ktail\n"`, then assert `render_pty(b"\x1b]9999;40;120\x07" + b"A" * 130 + b"\x1b]9999;40;150\x07" + b"\r\x1b[Ktail\n") == want` and `want == ["A" * 120, "tail"]`, with a comment that replaying those same bytes wholly at 150 gives `["tail"]`.
12. Add `test_render_pty_ignores_a_hostile_width_marker` to `tests/test_tui.py`: assert `render_pty(b"\x1b]9999;99999;99999\x07hello") == ["hello"]` (five digits do not match, so the default 40x120 stands) and `[len(l) for l in render_pty(b"\x1b]9999;9999;9999\x07" + b"x" * 1500)] == [1000, 500]` (clamped to `MAX_DIM` columns).
13. Add `test_tail_log_keeps_a_width_marker_the_tail_cut_dropped` to `tests/test_tui.py`: write `b"\x1b]9999;40;150\x07" + b"pad\n" * (MAX_TAIL // 4 + 1) + b"\x1b[H\x1b[2J" + b"B" * 140 + b"\x1b[1A\r\x1b[KSHORT\n"` to `.project/logs/TICKET-001-planning.log` under a `make_project()` directory, bind `lines = tail_log(str(d), "TICKET-001")`, then assert `lines == ["SHORT"]`, and comment that `b"\x1b[H\x1b[2J"` is load-bearing: `b"pad\n"` is a bare line feed that fills the screen, so without the clear `\x1b[1A` lands on a pad row instead of clamping at row 0 and the B row of the frame survives below `SHORT` at every width.
14. Run `uv run --group dev pytest -q tests/test_tui.py -k "own_width or render_pty or tail_cut"` and expect five failures, each showing a 120-column screen; the reproduction reports `got ['SHORT', 'BBBBBBBBBBBBBBBBBBBB']`.
15. Teach `render_pty()` the markers in `pipeline/tui/app.py`: change the import to `from pipeline.pty.host import COLS, GEOM_OSC, ROWS, Screen, last_geometry`, give it the signature `def render_pty(data: bytes, rows: int = ROWS, cols: int = COLS) -> list[str]`, build `screen = Screen(rows, cols)`, then walk `GEOM_OSC.finditer(data)` feeding `data[pos:m.start()]`, calling `screen.resize(*last_geometry(m.group(0)))` and setting `pos = m.end()`, feed the remaining `data[pos:]`, and keep the existing rstrip, trailing-blank pop and `["(blank screen)"]` return (DEC-039); extend the docstring to say `rows`/`cols` are the geometry the dump opens at, that a marker inside it resizes the screen where the daemon resized the live one, and that replaying at the wrong width re-wraps every frame so a later redraw lands on a leftover row.
16. Give `tail_log()` in `pipeline/tui/app.py` the head geometry: replace the one-line tail slice with `cut = max(0, len(raw) - MAX_TAIL)` and `head, data = raw[:cut], raw[cut:]`; when `cut` is non-zero do `first, sep, rest = data.partition(b"\n")` and only if `sep` set `head, data = head + first + sep, rest`, so a tail with no newline keeps all its bytes exactly as `split(b"\n", 1)[-1]` did; change the PTY branch to `return render_pty(data, *last_geometry(head))`; comment that `spawn()`'s marker can sit before the cut.
17. Run `uv run --group dev pytest -q tests/test_tui.py tests/test_pty.py` and expect every test to pass, then `uv run --group dev pytest -q` for the whole suite and `./pipeline/hooks/test_dangerous_commands.py` for the guard; add one bullet to the gotcha list in `CLAUDE.md` -- an interactive stage's log opens with `\x1b]9999;<rows>;<cols>\x07` and gains one more per resize, `render_pty()` replays at that geometry, and a batch log must never get one because `tail_log()`'s sniff is the raw ESC. Commit as `fix(TICKET-055): replay a pty log at the width it was written at`.

## Acceptance criteria

1. `uv run --group dev pytest -q tests/test_tui.py -k test_tail_log_renders_a_pty_dump_at_its_own_width_not_120` passes, and the same test still fails on base with `AssertionError: replaying at the log's own width (150) should be clean, got ['SHORT', 'BBBBBBBBBBBBBBBBBBBB']`.
2. `tests/test_tui.py::test_render_pty_matches_the_screen_the_dump_was_written_on` passes: a dump written at width 150 comes back equal to that screen's own `display`, which is the ticket's stated expectation.
3. `tests/test_tui.py::test_render_pty_resizes_where_the_log_says_the_screen_did` passes, and its `["A" * 120, "tail"]` differs from replaying the same bytes wholly at 150 (`["tail"]`).
4. `tests/test_tui.py::test_render_pty_ignores_a_hostile_width_marker` passes: a five-digit marker is ignored and a four-digit one is clamped to 1000 columns.
5. `tests/test_tui.py::test_tail_log_keeps_a_width_marker_the_tail_cut_dropped` passes with `lines == ["SHORT"]`: the geometry survives the `MAX_TAIL` cut. The same bytes replayed at 120 give `["SHORT", "BBBBBBBBBBBBBBBBBBBB"]`, so the test discriminates.
6. `tests/test_pty.py::test_resize_records_the_width_in_the_log` passes: `host.geom_marker(50, 160)` is in the log after a `resize` op.
7. `tests/test_pty.py::test_an_interactive_log_opens_with_its_geometry` passes: an interactive log opens with the marker and a batch log holds no `\x1b]9999;` (DEC-039).
8. `tests/test_pty.py::test_the_geometry_marker_round_trips_and_clamps` passes, including the hostile cases and pyte ignoring the marker.
9. `tests/test_tui.py::test_tail_log_still_renders_a_stream_json_log` and `tests/test_tui.py::test_tail_log_renders_a_pty_dump_as_the_final_screen` still pass, unchanged.
10. `uv run --group dev pytest -q` passes whole, and `./pipeline/hooks/test_dangerous_commands.py` reports its 79 guard cases passing.
11. `grep -F 9999 CLAUDE.md` finds the gotcha bullet of step 17, which names the opening marker, the per-resize marker and the batch-log ban.

## Decisions

**A PTY log records the geometry it was written at, in the log, as `\x1b]9999;<rows>;<cols>\x07`.** `render_pty()` has no other way to know: the width exists in `_op_resize`'s arguments and nowhere else, and a log is usually read long after the daemon that hosted it exited. An unknown OSC is ignored by pyte and by every real terminal, so the marker is inert for `cat`, for `pipeline logs` and for any old log that has none. `pipeline/pty/host.py` owns the bytes -- `geom_marker()` writes them, `last_geometry()` reads them -- because a second copy of that pattern is how a writer and a reader drift apart.

**The marker goes into an interactive log only, never a batch one.** `tail_log()` decides "PTY dump, not stream-json" on `b"\x1b" in data` (DEC-039). A marker in a headless stage's log would send its stream-json through pyte and show a screen of raw JSON. The `if interactive:` in `spawn()` is that rule, not a micro-optimisation.

**`_op_resize` writes the marker where it resizes the live screen, and deliberately does not drain the pty first.** Bytes the child wrote before the resize that nobody has read yet reach the live `pyte.Screen` after `screen.resize`. Putting the marker at the same point makes the replay reproduce the screen the daemon actually showed. Draining first would look tidier and would produce a screen that never existed.

**A marker is hostile input.** The child's own stdout is teed into the same log, so anything can print one. `GEOM_OSC` bounds each field to four digits and `last_geometry()` clamps both to `1..MAX_DIM` (1000, the bound `_dim()` already applies to a socket-supplied dimension), so the worst a malicious marker achieves is a replay at a bounded wrong size in one TUI pane. Never widen the digit count without keeping the clamp.

**`render_pty()` resizes mid-replay rather than picking one final width.** `pyte.Screen.resize` truncates and pads without reflow, so where the resize happens changes the result: the verified example replays to `['A'*120, 'tail']` in order and to `['tail']` at one width. Feeding the log through the same sequence of resizes the daemon made is the only thing that reproduces the daemon's screen.

**The reproduction test spells the marker literally and adds no import base lacks.** The Tier A gate copies `tests/test_tui.py` into a checkout of base and re-runs it there (DEC-017). An import of `geom_marker` at the top of that file would turn the base run into a collection error whose output does not carry the test's name, and the gate would report that base proves nothing.

## Rollback

Revert the three commits from step 4, step 8 and step 17, newest first. Nothing outside them depends on the new names: `MAX_DIM` returns to its literal in `pipeline/daemon/server.py`, `render_pty()` returns to a fixed 40x120 replay, and the markers stop being written. A log that already carries a marker stays readable, because pyte ignores the OSC -- the property this whole design rests on -- so the revert costs only the wrong-width rendering the ticket reported. No migration, and no log left unreadable.

## Thread

### 2026-08-24 14:44:07Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 · triage · result=ok

Reproduced. `tests/test_tui.py::test_tail_log_renders_a_pty_dump_at_its_own_width_not_120`
fails against current code: replaying a PTY dump written at width 150
through the hardcoded `Screen()` (40x120) leaves a leftover wrapped row
under a later frame's redraw. See `## Reproduction` for the command and
verbatim output. Committed on `ticket/055` as `57bf3a5`.

This is not a `chore`: fixing it needs a design decision the ticket itself
flags as open -- how to carry the write width through to replay (the
ticket's own suggestion, an OSC marker parsed out of the log, touches
`pipeline/pty/host.py`'s `Screen`/`_op_resize` wiring and treats the log as
hostile input). That is a design choice, not a small fixed-file patch.

### 2026-08-24 14:47:34Z · triage · session · session=710b236e-f146-4518-94d2-383158581913

`triage` ran as session `710b236e-f146-4518-94d2-383158581913`
- replay: `claude --resume 710b236e-f146-4518-94d2-383158581913`
- log: `.project/logs/TICKET-055-triage-710b236e.log`

### 2026-08-24 14:47:34Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced render_pty replaying at hardcoded 120 cols regardless of write width; failing test committed on ticket/055

### 2026-08-24 · planning · result=ok

Plan written: 17 steps, 7 files. The log records its own geometry as the OSC
marker the ticket suggested, `\x1b]9999;<rows>;<cols>\x07`. `spawn()` writes one
when it opens an interactive log, `_op_resize` writes one per resize, and
`render_pty()` replays segment by segment, resizing where each marker sits.

Scope: one subsystem, no split needed. The two other options were rejected on
evidence. A new SQLite event kind is out -- DEC-011 froze the vocabulary, and
`tail_log()` reads a file, not the store. Inferring the width from the dump is
out -- 140 characters of output are consistent with every width above 140.

Three findings the plan turns on, each verified in this worktree:
1. `pyte.ByteStream` ignores the marker; a `Screen(4, 20)` fed the marker plus
   `hi` shows `hi`.
2. Resizing mid-replay is not the same as replaying at the final width:
   `['A'*120, 'tail']` against `['tail']` on the same bytes.
3. The reproduction test must stay import-clean against base, or the gate's base
   run errors at collection and reports "base proves nothing" (DEC-017).

Noticed outside this stage's job, not fixed: `pipeline logs` prints
`(no stream-json here ...)` for every interactive log
(`pipeline/cli/main.py:436`), so a PTY dump is readable only through the TUI or
`cat`. `render_pty()` would serve it. That is a separate ticket.

### 2026-08-24 14:58:12Z · planning · session · session=5d06ddde-8775-4a36-8b6d-91521452e32f

`planning` ran as session `5d06ddde-8775-4a36-8b6d-91521452e32f`
- replay: `claude --resume 5d06ddde-8775-4a36-8b6d-91521452e32f`
- log: `.project/logs/TICKET-055-planning-5d06ddde.log`

### 2026-08-24 14:58:12Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned: a PTY log records its own geometry as an OSC marker spawn and _op_resize write, and render_pty replays at it -- 17 steps, 7 files

### 2026-08-24 14:58:27Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_tail_log_renders_a_pty_dump_at_its_own_width_not_120` fails as required
```
0 leaves 'BBBBBBBBBBBBBBBBBBBB' from the first
        frame's wrapped second row under the second frame's 'SHORT'."""
        d = make_project()
        logs = d / ".project" / "logs"
        logs.mkdir(parents=True)
        frame1 = b"B" * 140
        redraw = b"\x1b[1A\r\x1b[KSHORT\n"
        (logs / "TICKET-001-planning.log").write_bytes(frame1 + redraw)
    
        lines = tail_log(str(d), "TICKET-001")
    
>       assert lines == ["SHORT"], (
            f"replaying at the log's own width (150) should be clean, got {lines!r}"
        )
E       AssertionError: replaying at the log's own width (150) should be clean, got ['SHORT', 'BBBBBBBBBBBBBBBBBBBB']
E       assert ['SHORT', 'BB...BBBBBBBBBBBB'] == ['SHORT']
E         
E         Left contains one more item: 'BBBBBBBBBBBBBBBBBBBB'
E         Use -v to get more diff

tests/test_tui.py:575: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_tail_log_renders_a_pty_dump_at_its_own_width_not_120
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_tui.py::test_tail_log_renders_a_pty_dump_at_its_own_width_not_120` fails on base `main` too -- the bug is not already fixed upstream
```
     )
E       AssertionError: replaying at the log's own width (150) should be clean, got ['SHORT', 'BBBBBBBBBBBBBBBBBBBB']
E       assert ['SHORT', 'BB...BBBBBBBBBBBB'] == ['SHORT']
E         
E         Left contains one more item: 'BBBBBBBBBBBBBBBBBBBB'
E         Use -v to get more diff

tests/test_tui.py:575: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_tail_log_renders_a_pty_dump_at_its_own_width_not_120
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.51s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-owj7pcxo/base
      Built pipeline @ file:///tmp/pipeline-base-owj7pcxo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 12ms

```

### 2026-08-24 · plan-validation · result=fail

Plan rejected on one item. Acceptance criterion 5 cannot pass: step 13's test
asserts `lines[-1] == "SHORT"`, but its filler leaves the `B` frame below
`SHORT` at every width. I rendered step 13's exact bytes through step 16's cut:

```
150: [(38, "'SHORT'", 5), (39, "'BBBBBBBBBBBB'", 131)]
120: [(38, "'SHORT'", 5), (39, "'BBBBBBBBBBBB'", 71)]
```

`b"pad\n"` is a bare line feed, so each pad line steps three columns right and
the screen is full when the frame starts. `\x1b[1A` then lands on a pad row
instead of clamping at row 0, `SHORT` erases that row, and the frame's row
survives below it. Both widths render alike, so the test does not discriminate
either. Fix, verified: put `b"\x1b[H\x1b[2J"` before `b"B" * 140`, as step 10's
`frames` already does -- 150 then gives `['SHORT']` and 120 gives
`['SHORT', 'BBBBBBBBBBBBBBBBBBBB']`.

The other seven items pass:
1. Root cause: the write width lives only in `_op_resize`'s arguments
   (`server.py:631`) and is recorded nowhere, so `render_pty()` replays every
   dump on a fixed 40x120 `Screen()`. The plan records the geometry in the log
   and replays through the daemon's own resize sequence. That fixes the cause.
2. Decisions: DEC-039's sniff is `b"\x1b" in data` (`app.py:138`) and only an
   interactive log gets a marker; the resize write lands after the writer claim
   (`server.py:632`), per DEC-019.
3. Scope: one step is untraced -- step 17's `CLAUDE.md` bullet, which no
   criterion names.
5. No research left: every step names a file and a function.
6. Riskiest step: 15 and 16, the `render_pty()`/`tail_log()` rewrite.
   `## Rollback` states the fallback and why an old log stays readable.
7. Regression surface: the stream-json path, a batch log's missing ESC and the
   existing `tests/test_pty.py:217` resize test, covered by criteria 7, 9, 10.
8. Blast radius: 7 files, 3 of them code, none in `machine.FENCED`.

I re-ran the plan's other claims in this worktree. Steps 1, 9, 10, 11 and 12
each produce what they state, including `['A' * 120, 'tail']` against `['tail']`
and the `[1000, 500]` clamp.

long: eight scored items plus verbatim evidence for the one that failed.

### 2026-08-24 15:03:57Z · plan-validation · session · session=8b6dc99a-5d6a-4374-a84c-946cc6331f03

`plan-validation` ran as session `8b6dc99a-5d6a-4374-a84c-946cc6331f03`
- replay: `claude --resume 8b6dc99a-5d6a-4374-a84c-946cc6331f03`
- log: `.project/logs/TICKET-055-plan-validation-8b6dc99a.log`

### 2026-08-24 15:03:57Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ plan rejected on criterion 5: step 13's filler leaves the B frame below SHORT at 150 and 120 alike, so the test cannot pass; other seven items pass
