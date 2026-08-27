---
id: TICKET-063
stage: done
class: bugfix
branch: ticket/063
test_file: tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped
files_declared:
- CLAUDE.md
- pipeline/tui/app.py
- tests/test_tui.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 12
  plan_files: 3
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 63bc78e0-02bd-4216-adec-cbe498041aa3
  log: .project/logs/TICKET-063-review-63bc78e0.log
approved_by: chezzijr
approved_at: '2026-08-26T20:07:19.268743+00:00'
---

## Summary

A PTY dump wider than the `#log` pane soft-wraps, so the replayed screen loses
its alignment. Seen 2026-08-26 in `pipeline tui` with `TICKET-060` selected:
`#tree` fixes at 34 columns, `render_pty()` replays the dump at its recorded
124 columns, and `RichLog(wrap=True)` re-flows the rest. Wrapping a
position-significant screen gives a different picture, not a narrower one.
TICKET-055 works here: the log carries both geometry markers,
`[(b'40', b'120'), (b'33', b'124')]`.

The fix is per write, not per widget: `tail_log()` returns `(lines, cols)` --
the dump's last recorded width, `0` for stream-json -- and `_show()` writes
`log.write(line, width=cols or None)`. `#log` keeps `wrap=True`: prose wraps, a
dump clips and scrolls. Twelve steps, three files: `pipeline/tui/app.py`,
`tests/test_tui.py`, `CLAUDE.md`.

The root cause is one write, not the widget: `_show()` called `log.write(line)`
with no width, so `RichLog` rendered at `max(shrunk_width, min_width=78)` and
re-flowed a 120-column rule into 78 + 42. In `textual` 8.2.8 `write(width=)`
overrides `shrink` and `min_width`.

Not in scope: TICKET-060, a different defect in the same file.

Implemented 2026-08-27: all twelve plan steps landed in four commits
(`7aac33e` refactor, `4d047cb` fix, `ec07353` test, `b11b525` docs).
`uv run --group dev pytest -q` passes, 337 passed, no failures.

Review passed 2026-08-27 with no blocking findings. All six acceptance
criteria hold. `tail_log()` has one production caller, `_show()`. The
reported width equals the replayed screen's final `columns`, because
`render_pty()` and `last_geometry()` read the same markers and apply the same
`1..MAX_DIM` clamp. Two candidate findings were refuted: a wide-character row
cannot exceed `cols` in cells, and `RichLog.clear()` resets
`_widest_line_width`. Both new pinning tests fail under a forced wrong `cols`.
Two minor findings stand unfixed: the 136-character comment at
`pipeline/tui/app.py:455`, and the unused `lines` binding in
`test_tail_log_reports_the_width_the_dump_ends_at`. The plan specified both
verbatim.
## Reproduction

test: `tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped`
command: `uv run --group dev pytest -q tests/test_tui.py -k pty_dump_wider`

The test writes a PTY dump (geometry marker `\x1b]9999;40;120\x07` plus a
120-`=` rule) to a ticket's log, runs `PipelineApp` at terminal size
`(80, 24)` -- `#tree` fixes at 34 columns, so `#log` gets roughly 46 -- and
selects the ticket. It asserts the rule renders as one `RichLog` strip.

expect: AssertionError: the 120-column rule split across 2 rows instead of staying one row:

The full failure, verbatim, from `uv run --group dev pytest -x -q tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped` on 2026-08-27:

```
E           AssertionError: the 120-column rule split across 2 rows instead of staying one row: ['==============================================================================', '==========================================']
E           assert 2 == 1
E            +  where 2 = len([Strip([Segment('==============================================================================')], 78), Strip([Segment('==========================================')], 42)])
```

Tier A reads only the one line after `expect:`, so that line stays unquoted and
unwrapped; the block above is the evidence, not the match string.

`#log` is `RichLog(id="log", wrap=True, ...)` (`pipeline/tui/app.py:223`),
used for both PTY dumps and stream-json alike. `wrap=True` soft-wraps any
line past the pane width, which is the bug: a PTY dump's alignment is
position-significant and wrapping produces a different screen, not a
narrower view of the same one.

## Digest

Files touched: `pipeline/tui/app.py` (the widget layer), `tests/test_tui.py`, `CLAUDE.md`.

Key functions: `tail_log()` (`pipeline/tui/app.py:130`) reads the newest stage log, sniffs `b"\x1b" in data` and returns rendered lines; `render_pty()` (`pipeline/tui/app.py:103`) replays a dump on a pyte `Screen`, resizing at each `\x1b]9999;<rows>;<cols>\x07` marker; `PipelineApp._show()` (`pipeline/tui/app.py:384`) clears `#log` and writes those lines; `PipelineApp._write()` (`pipeline/tui/app.py:374`) writes one live event line; `last_geometry(data, rows=ROWS, cols=COLS)` (`pipeline/pty/host.py:38`) returns the last marker in `data` or the fallback it is given.

Entry points: `pipeline tui` -> `cmd_tui` -> `PipelineApp`; the pane is `RichLog(id="log", wrap=True, max_lines=2000)` (`pipeline/tui/app.py:223`), and `#tree { width: 34; }` is what leaves it narrow.

Gotcha 1 -- `RichLog.write(content, width=...)` sets the render width and overrides `shrink`, so a line written at `width=cols` never re-flows even while the widget keeps `wrap=True`. Measured at 80x24 (`#log` region 44 cols): `log.write("=" * 120, width=120)` gives one strip, `cell_length 120`, `virtual_size Size(width=120, height=1)`, `show_horizontal_scrollbar True`. Without the width the same line becomes two strips, 78 + 42.

Gotcha 2 -- the wrap today happens at 78, not at the pane's 44, because `RichLog.min_width` defaults to 78 and floors the shrunk width. That is why the reported failure shows a 78-char row and a 42-char row.

Gotcha 3 -- toggling `RichLog.wrap` per write is the mechanism to avoid. `write()` reads `self.wrap` at write time, but a write made before the widget's size is known is deferred (`DeferredRender`) and replayed from `on_resize` -- the deferred record carries `width`, not `wrap`, so a toggled flag can be read at the wrong moment. `width=` survives the deferral.

Gotcha 4 -- in textual 8.2.8 `RichLog.write` calls `strip.adjust_cell_length(render_width)` and discards the returned `Strip` (`textual/widgets/_rich_log.py:262`). A too-wide strip therefore survives by accident today. Passing the real width means the fix does not depend on that.

Gotcha 5 -- pyte pads every `display` row to `screen.columns` and `render_pty()` only `rstrip`s, so no line it returns is wider than the dump's last recorded width. That is what makes `cols` a safe render width for every line of the dump.

Gotcha 6 -- `.project/pipeline.toml` runs `test_one` as `uv run --group dev pytest -x {test}` with a node id, so the Tier A base re-run executes only the named test from the copied file. Changing how that file's other tests call `tail_log()` does not affect the base run, and this plan adds no import base lacks (DEC-017).

Gotcha 7 -- Tier A matches the `expect:` line verbatim. `gate()` (`pipeline/core/gate.py:202`) takes the single line after `expect:` and requires it as a substring of the test output. Backticks and a wrapped continuation are part of that match string, so a quoted or multi-line `expect:` fails the gate even while the test fails exactly as reported.

## Decisions checked

- DEC-039 -- binding. `tail_log()` tells a PTY dump from stream-json by `b"\x1b" in data`, never by the stage's `mode:`. This plan keeps that one sniff in that one place and reports its verdict to the caller instead of adding a second sniff.
- DEC-055 -- binding. The log records its own geometry and `render_pty()` replays at it. The plan changes nothing about the marker, the clamp or the mid-replay resize, and reuses `last_geometry()` rather than parsing the marker again.
- DEC-019, DEC-021 -- read, not constraining. Both govern `#pty`, the live attach pane, not `#log`. This plan does not touch `PtyPane`, `on_event`, `_resize` or the writer gate.
- DEC-017 -- binding on the test file. `tests/test_tui.py` must import cleanly on base, so the new tests spell the geometry marker literally and add no import.
- DEC-042 -- history, superseded by DEC-054. Both are gate-format records and neither constrains this change.
- Grep terms used in `.project/decisions/`: `RichLog`, `tail_log`, `render_pty`, `wrap`, `log pane`, `geometry`, `tui`.

## Plan

1. In `pipeline/tui/app.py`, change `tail_log()` to return `tuple[list[str], int]`, the rendered lines plus the width they were drawn at and `0` for stream-json: the no-log arm returns `["(no log yet)"], 0`; the PTY arm becomes `start = last_geometry(head)` then `return render_pty(data, *start), last_geometry(data, *start)[1]`; the stream-json arm returns `[ln for ev in StreamReader().feed(data) if (ln := render(ev))], 0`; the `except OSError` arm returns `[f"(log unreadable: {e})"], 0`.
2. In `pipeline/tui/app.py`, add one line to `tail_log()`'s docstring: "Returns the lines and the width they were drawn at: 0 for stream-json, which is prose and wraps, and the dump's last recorded width for a PTY dump, which is a screen and must not be re-flowed."
3. In `pipeline/tui/app.py`, unpack in `_show()` without changing the write yet: replace `for line in tail_log(key[0], key[1]):` with `lines, cols = tail_log(key[0], key[1])` followed by `for line in lines:`, keeping the body `log.write(line)`.
4. In `tests/test_tui.py`, unpack the tuple at the five existing `tail_log()` call sites (lines 541, 557, 577, 638, 688) as `lines, _ = tail_log(str(d), "TICKET-001")`, and assert on `lines` where the test compared the call directly (`assert lines == ["second frame"]` at 557, `assert lines == ["planning done"]` at 688).
5. In `tests/test_tui.py`, add `test_tail_log_reports_the_width_the_dump_ends_at`: write a log of `b"\x1b]9999;40;150\x07" + b"A" * 140 + b"\x1b]9999;33;124\x07" + b"B" * 100 + b"\n"`, spelling both markers literally per DEC-017, then `lines, cols = tail_log(str(d), "TICKET-001")` and `assert cols == 124, cols` -- the last recorded width, not the first.
6. Run `uv run --group dev pytest -q tests/test_tui.py` and expect one failure only, `test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped`, still reporting "the 120-column rule split across 2 rows". Commit `pipeline/tui/app.py` and `tests/test_tui.py` as `refactor(TICKET-063): tail_log reports the width its lines were drawn at`.
7. In `pipeline/tui/app.py`, make `_show()` write the dump at that width: `log.write(line, width=cols or None)`, above it the comment `# a PTY dump renders at the width it was drawn at, so a narrower pane clips and scrolls; stream-json is prose (cols 0) and wraps`.
8. Run `uv run --group dev pytest -q tests/test_tui.py -k pty_dump_wider` and expect `1 passed`. Commit `pipeline/tui/app.py` as `fix(TICKET-063): write a PTY dump at its recorded width, not the pane's`.
9. In `tests/test_tui.py`, add `test_a_clipped_pty_dump_keeps_the_whole_line_for_horizontal_scrolling`, set up like the reproduction test (log `b"\x1b]9999;40;120\x07" + b"=" * 120 + b"\n"`, `PipelineApp` run at `size=(80, 24)`, focus the `Tree`, press `down` twice), asserting the rule's strip has `cell_length == 120` and `app.query_one("#log", RichLog).virtual_size.width >= 120`, so the clipped remainder stays reachable.
10. In `tests/test_tui.py`, add `test_a_stream_json_log_still_wraps_in_the_log_pane`: write the log line `b'{"type":"assistant","message":{"content":[{"type":"text","text":"' + b"word " * 40 + b'"}]}}\n'`, run `PipelineApp` at `size=(80, 24)`, select the ticket, and assert more than one `RichLog` strip contains `word`.
11. Run `uv run --group dev pytest -q tests/test_tui.py` and expect no failures. Commit `tests/test_tui.py` as `test(TICKET-063): pin the clipped remainder and stream-json wrapping`.
12. In `CLAUDE.md`, extend the gotcha bullet "A PTY log carries the width it was written at" with: "`#log` writes those lines with `RichLog.write(line, width=cols)`, so a pane narrower than the dump clips and scrolls horizontally instead of re-flowing a screen; stream-json lines pass `width=None` and still wrap." Run `uv run --group dev pytest -q`, then commit `CLAUDE.md` as `docs(TICKET-063): note that the log pane clips a dump instead of wrapping it`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_tui.py -k pty_dump_wider` passes:
  `test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped` finds exactly one
  `RichLog` strip made of `=`, where it now finds two (78 chars + 42 chars).
- `test_a_clipped_pty_dump_keeps_the_whole_line_for_horizontal_scrolling` passes:
  the rule's strip reports `cell_length == 120` and `#log.virtual_size.width >= 120`,
  so the clipped remainder is scrollable rather than discarded.
- `test_a_stream_json_log_still_wraps_in_the_log_pane` passes: a 200-character
  assistant text occupies more than one strip, so the fix did not turn wrapping
  off for prose.
- `test_tail_log_reports_the_width_the_dump_ends_at` passes: `cols == 124` for a
  dump whose second marker resizes to 124 columns.
- `test_tail_log_still_renders_a_stream_json_log` passes with
  `lines == ["planning done"]`.
- `uv run --group dev pytest -q` passes with no failures, including the four
  existing `tail_log` tests updated to the tuple return
  (`test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump`,
  `test_tail_log_renders_a_pty_dump_as_the_final_screen`,
  `test_tail_log_renders_a_pty_dump_at_its_own_width_not_120`,
  `test_tail_log_keeps_a_width_marker_the_tail_cut_dropped`).

## Decisions

**`#log` writes a PTY dump at the width it was drawn at, and the width is the mechanism, not `RichLog.wrap`.** `_show()` passes `width=cols` from `tail_log()`, and the widget stays `RichLog(wrap=True)` because the same pane also shows stream-json, which is prose and must keep wrapping. Toggling `wrap` per write was the obvious alternative and it is fragile: `RichLog.write` reads `self.wrap` at write time, but a write issued before the widget's size is known is deferred and replayed from `on_resize`, and the deferred record carries `width`, not `wrap`. A line written with an explicit width cannot wrap at either moment.

**Do not lean on textual discarding `adjust_cell_length`.** In textual 8.2.8 `RichLog.write` computes `strip.adjust_cell_length(render_width)` and throws the result away, so a strip wider than the render width survives today by accident. Passing the dump's real width makes the render width equal to the content, so the fix holds whether or not that upstream line is ever fixed.

**`tail_log()` returns `(lines, cols)`, and `cols == 0` means "stream-json, wrap it".** DEC-039 owns the one sniff (`b"\x1b" in data`); a caller must never sniff the bytes again to learn which kind it is about to write. `cols` is the last geometry the dump records, read as `last_geometry(data, *last_geometry(head))`, because `render_pty()` resizes mid-replay (DEC-055) and pyte pads every display row to the final `screen.columns` -- so no line it returns can exceed it.

**Horizontal scrolling is inherited, not built.** `RichLog` is a `ScrollView` with `overflow-x: auto` and sets `virtual_size` from its widest strip, so keeping the full-width strip is all that is needed; the pane is focusable and scrolls. Do not add a custom scroll binding or a manual crop.

## Rollback

Revert the four commits (`refactor`, `fix`, `test` and `docs` for TICKET-063). The behavioural change is two edits in `pipeline/tui/app.py`: `tail_log()`'s return type and the one `log.write(line, width=cols or None)` in `_show()`. Reverting restores soft-wrapped PTY dumps in `#log` and changes nothing in the daemon, the PTY host or the recorded logs -- no log format, no on-disk state and no protocol is touched, so an old TUI reads a new log and a new TUI reads an old log exactly as before.

## Thread

### 2026-08-26 17:41:55Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-27 · triage · result=ok

Reproduced. `#log` is `RichLog(id="log", wrap=True, ...)` in
`pipeline/tui/app.py:223`, shared by PTY dumps and stream-json, so a PTY
dump's lines soft-wrap whenever the pane is narrower than the recorded
width. `render_pty()` and `tail_log()` are already correct: they replay at
the log's own geometry, per `tests/test_tui.py`'s existing `render_pty`/
`tail_log` tests. The bug is in the widget layer, not the replay.

Committed a failing test:
`tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped`.
See `## Reproduction` for the command and exact failure text.

Not a chore: the ticket's own suggestion flags an open design question --
clip vs. clip+horizontal-scroll, and how to keep a stream-json log (which
DOES want wrapping) working in the same widget. `tail_log()` already tells
the caller which kind it wrote (raw ESC sniff), so the fix has a signal to
key off; picking the widget behavior is planning's call, not mine.

### 2026-08-26 17:44:34Z · triage · session · session=da8e70ec-ca1d-41e0-b446-05458a6a38b6

`triage` ran as session `da8e70ec-ca1d-41e0-b446-05458a6a38b6`
- replay: `claude --resume da8e70ec-ca1d-41e0-b446-05458a6a38b6`
- log: `.project/logs/TICKET-063-triage-da8e70ec.log`

### 2026-08-26 17:44:34Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: RichLog(wrap=True) soft-wraps PTY dumps; committed failing test test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped.

### 2026-08-26 18:27:47Z · planning · note

`planning` was interrupted; lease released

### 2026-08-27 · planning · result=ok

Plan written. Scope is one subsystem, the TUI widget layer; it stands alone.

The design question the ticket left open is settled by measurement, not by
`RichLog(wrap=False)`. `RichLog.write(line, width=cols)` sets the render width
per write, so a dump renders unwrapped at its own width while the widget keeps
`wrap=True` for stream-json prose. Verified in a live `PipelineApp` at
`size=(80, 24)`, `#log` region 44 columns: with the width, one strip,
`cell_length 120`, `virtual_size Size(width=120, height=1)`,
`show_horizontal_scrollbar True`; without it, two strips, 78 + 42. The
horizontal scroll therefore needs no new code.

`tail_log()` gains a second return value (`cols`, 0 for stream-json), so the
five existing `tail_log()` assertions in `tests/test_tui.py` unpack a tuple.
`test_one` runs a node id, so the Tier A base re-run is unaffected (DEC-017).

Out of scope, observed while measuring: `RichLog.min_width` defaults to 78, so
prose in a 44-column pane wraps at 78 and is clipped at 44 already. Separate
from this ticket; not planned here.

### 2026-08-26 18:35:25Z · planning · session · session=076cd8fe-1a4e-4ced-9d7a-374026100949

`planning` ran as session `076cd8fe-1a4e-4ced-9d7a-374026100949`
- replay: `claude --resume 076cd8fe-1a4e-4ced-9d7a-374026100949`
- log: `.project/logs/TICKET-063-planning-076cd8fe.log`

### 2026-08-26 18:35:25Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: tail_log() returns (lines, cols) and _show() writes each line at width=cols, so a PTY dump clips and scrolls while stream-json keeps wrapping.

### 2026-08-26 19:59:57Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped` fails, but its output does not mention the expected string '`AssertionError: the 120-column rule split across 2 rows instead of'
```
Log)
    
            def text(strip):
                return "".join(seg.text for seg in strip)
    
            strips = [s for s in log.lines if set(text(s).strip()) == {"="}]
>           assert len(strips) == 1, (
                f"the 120-column rule split across {len(strips)} rows "
                f"instead of staying one row: {[text(s) for s in strips]}"
            )
E           AssertionError: the 120-column rule split across 2 rows instead of staying one row: ['==============================================================================', '==========================================']
E           assert 2 == 1
E            +  where 2 = len([Strip([Segment('==============================================================================')], 78), Strip([Segment('==========================================')], 42)])

tests/test_tui.py:669: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-08-26 19:59:57Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- `tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped` fails, but its output does not mention the expected string '`AssertionError: the 120-column rule split across 2 rows instead of'
*-- identical output, already quoted in the `## Thread` entry `2026-08-26 19:59:57Z · plan-validation · gate · verdict=FAIL` --*

### 2026-08-27 · planning · result=ok

Re-planned after the Tier A FAIL. The plan is unchanged. The gate rejected the
ticket's own `## Reproduction` text.

Tier A takes the single line after `expect:` and requires it, verbatim, in the
test output (`pipeline/core/gate.py:202`). The old line opened with a backtick
and wrapped over three lines, so the match string was "AssertionError: the
120-column rule split across 2 rows instead of" behind a leading backtick the
output does not carry. Rewrote `expect:` as one unquoted line, "AssertionError:
the 120-column rule split across 2 rows instead of staying one row:", and moved
the full failure into a fenced block below it.

Verified in this worktree on 2026-08-27:

1. The reproduction test node run alone -> `1 failed in 0.45s`, message as quoted in `## Reproduction`.
2. `uv run --group dev pytest -q --deselect <that node id>` -> `315 passed, 1 deselected in 13.78s`, so the suite without the new test is green.
3. The branch's `tests/test_tui.py` copied onto a clone of `main` and run there -> the same `split across 2 rows` failure, so the base re-run finds the bug unfixed upstream.

### 2026-08-26 20:04:10Z · planning · session · session=676f437b-2dd2-4a81-b8aa-89e7c4c67da5

`planning` ran as session `676f437b-2dd2-4a81-b8aa-89e7c4c67da5`
- replay: `claude --resume 676f437b-2dd2-4a81-b8aa-89e7c4c67da5`
- log: `.project/logs/TICKET-063-planning-676f437b.log`

### 2026-08-26 20:04:10Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan unchanged; the Tier A FAIL was the ticket's own expect: line -- rewrote it as one unquoted line the test output contains verbatim.

### 2026-08-26 20:04:26Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped` fails as required
```
Log)
    
            def text(strip):
                return "".join(seg.text for seg in strip)
    
            strips = [s for s in log.lines if set(text(s).strip()) == {"="}]
>           assert len(strips) == 1, (
                f"the 120-column rule split across {len(strips)} rows "
                f"instead of staying one row: {[text(s) for s in strips]}"
            )
E           AssertionError: the 120-column rule split across 2 rows instead of staying one row: ['==============================================================================', '==========================================']
E           assert 2 == 1
E            +  where 2 = len([Strip([Segment('==============================================================================')], 78), Strip([Segment('==========================================')], 42)])

tests/test_tui.py:669: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.45s ===============================

```
- ok: `tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped` fails on base `main` too -- the bug is not already fixed upstream
```
=============', '==========================================']
E           assert 2 == 1
E            +  where 2 = len([Strip([Segment('==============================================================================')], 78), Strip([Segment('==========================================')], 42)])

tests/test_tui.py:669: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.81s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-44_1hw0t/base
      Built pipeline @ file:///tmp/pipeline-base-44_1hw0t/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-08-27 · plan-validation · judgment · result=ok

Scored every item against the code. All pass.

long: eight items, each with the evidence rule 9 requires.

1. Root cause: `_show()` writes each dump line as `log.write(line)` with no
   width, so `RichLog` renders at `max(shrunk_width, min_width=78)` and Rich
   re-flows the 120-column line into 78 + 42. The plan writes each dump line
   at the dump's own width, so it fixes the cause, not the symptom.
2. Decision conflict: DEC-039, DEC-055 and DEC-017 constrain this plan and it
   complies. `cols == 0` reports the existing sniff instead of repeating it;
   step 5 spells the marker literally.
3. Scope: twelve steps, three files, `class: bugfix`. Step 12 documents the
   changed behaviour in an existing CLAUDE.md bullet; CLAUDE.md is not in
   `machine.FENCED`.
4. Criteria falsifiable: a first-marker `tail_log()` returns 150, not 124, and
   an unconditional `width=cols` collapses the stream-json test to one strip.
5. No research left: every step names a file and a function.
6. Riskiest step is 7, the one behavioural edit. `## Rollback` names it and
   its revert.
7. Regression surface: `tail_log()` has one caller, `_show()`, plus five test
   call sites (grep, whole repo, `*.py`). Steps 4 and 6 cover them.

Verified in `textual` 8.2.8: `min_width: var[int] = var(78)`; `write(width=)`
sets `render_width = width` under the comment "We ignore `expand` and `shrink`
when a width is specified. This also overrides `min_width`";
`strip.adjust_cell_length(render_width)` is called and its result discarded;
`virtual_size = Size(self._widest_line_width, len(self.lines))`. Digest
gotchas 1, 2 and 4 hold.

### 2026-08-26 20:06:54Z · plan-validation · session · session=99f8adf8-4313-4979-9c8f-ee8939b39f88

`plan-validation` ran as session `99f8adf8-4313-4979-9c8f-ee8939b39f88`
- replay: `claude --resume 99f8adf8-4313-4979-9c8f-ee8939b39f88`
- log: `.project/logs/TICKET-063-plan-validation-99f8adf8.log`

### 2026-08-26 20:06:54Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight judgment items: root cause is the width-less log.write() in _show(), decisions comply, criteria falsifiable, one caller of tail_log().

### 2026-08-26 20:07:19Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-26 20:07:46Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped` fails as required
```
Log)
    
            def text(strip):
                return "".join(seg.text for seg in strip)
    
            strips = [s for s in log.lines if set(text(s).strip()) == {"="}]
>           assert len(strips) == 1, (
                f"the 120-column rule split across {len(strips)} rows "
                f"instead of staying one row: {[text(s) for s in strips]}"
            )
E           AssertionError: the 120-column rule split across 2 rows instead of staying one row: ['==============================================================================', '==========================================']
E           assert 2 == 1
E            +  where 2 = len([Strip([Segment('==============================================================================')], 78), Strip([Segment('==========================================')], 42)])

tests/test_tui.py:854: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================

```
- ok: `tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped` fails on base `main` too -- the bug is not already fixed upstream
```
============', '==========================================']
E           assert 2 == 1
E            +  where 2 = len([Strip([Segment('==============================================================================')], 78), Strip([Segment('==========================================')], 42)])

tests/test_tui.py:854: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_a_pty_dump_wider_than_the_log_pane_is_not_re_wrapped
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.89s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-kwpuqr0q/base
      Built pipeline @ file:///tmp/pipeline-base-kwpuqr0q/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 11ms

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-08-26 20:07:47Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-27 · implementing · todo

Todo list, one entry per plan step:

1. [x] `tail_log()` returns `(lines, cols)`.
2. [x] Docstring notes the return contract.
3. [x] `_show()` unpacks the tuple, write unchanged.
4. [x] Update the five existing `tail_log()` call sites in `tests/test_tui.py`.
5. [x] Add `test_tail_log_reports_the_width_the_dump_ends_at`.
6. [x] Run `tests/test_tui.py`, expect one failure (`pty_dump_wider`). Commit refactor.
7. [x] `_show()` writes `log.write(line, width=cols or None)`.
8. [x] Run `-k pty_dump_wider`, expect pass. Commit fix.
9. [x] Add `test_a_clipped_pty_dump_keeps_the_whole_line_for_horizontal_scrolling`.
10. [x] Add `test_a_stream_json_log_still_wraps_in_the_log_pane`.
11. [x] Run `tests/test_tui.py`, expect no failures. Commit tests.
12. [x] Extend the CLAUDE.md gotcha, run full suite, commit docs.

### 2026-08-27 · implementing · report · result=ok

**Plan executed as written.**

- Step 6: after the refactor, `-k pty_dump_wider` still failed with the same
  message ("the 120-column rule split across 2 rows"), confirming the width
  plumbing alone does not fix the write. Committed `7aac33e`.
- Step 8: after `log.write(line, width=cols or None)`, `-k pty_dump_wider`
  gave `1 passed`. Committed `4d047cb`.
- Steps 9-10: both new tests passed on first run, since the fix already
  landed at step 8 -- expected per the plan's own sequencing (fix, then
  pinning tests), not a TDD violation.
- Step 11: `uv run --group dev pytest -q tests/test_tui.py` -> `36 passed`.
  Committed `ec07353`.
- Step 12: `uv run --group dev pytest -q` -> `337 passed`. Committed `b11b525`.

Four commits total: `7aac33e`, `4d047cb`, `ec07353`, `b11b525`. Line numbers
of the five call sites in `tests/test_tui.py` were 726/742/762/823/873 at
start, not the plan's 541/557/577/638/688 (file had grown since planning);
same five sites, found by name not line number.

### 2026-08-26 20:11:21Z · implementing · session · session=0f3bf578-d03d-4d0a-95d9-6ec81cd632ca

`implementing` ran as session `0f3bf578-d03d-4d0a-95d9-6ec81cd632ca`
- replay: `claude --resume 0f3bf578-d03d-4d0a-95d9-6ec81cd632ca`
- log: `.project/logs/TICKET-063-implementing-0f3bf578.log`

### 2026-08-26 20:11:21Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed all 12 plan steps in 4 commits; full suite passes, 337 passed.

### 2026-08-27 · review · report · result=ok

**No blocking findings.** Reviewed `main...HEAD`: 5 commits, 3 files,
136 insertions. All six acceptance criteria hold.

- `uv run --group dev pytest -q` gives `337 passed in 16.93s`.
- `tail_log()` has one production caller, `_show()` (`pipeline/tui/app.py:454`).
  A repo-wide grep found no other.
- `last_geometry(data, *start)[1]` equals the replayed screen's final
  `columns`. `render_pty()` resizes on the same `GEOM_OSC` matches, and
  `last_geometry()` applies the same `1..MAX_DIM` clamp
  (`pipeline/pty/host.py:55`). A tail with no marker falls back to the head
  geometry, which is the width `render_pty()` started at.
- Refuted, wide characters: a CJK dump row could exceed `cols` in cells and
  wrap at `width=cols`. It cannot -- `pyte` pads to cell width, not character
  count. `Screen(10, 2)` fed `日本語ABCD` gives `cell_len == 10`.
- Refuted, stale width after switching tickets: `RichLog.clear()` resets
  `_widest_line_width` and `virtual_size`, so a 120-wide dump does not leave
  the pane wide for the next stream-json log.
- Both new pinning tests discriminate. Forcing `cols=200` fails
  `test_a_stream_json_log_still_wraps_in_the_log_pane`; forcing `cols=0` fails
  `test_a_clipped_pty_dump_keeps_the_whole_line_for_horizontal_scrolling`.

Non-blocking findings, recorded not fixed:

1. minor -- `pipeline/tui/app.py:455` is 136 characters. The next longest line
   in the file is 87. Plan step 7 specified that comment verbatim.
2. minor -- `test_tail_log_reports_the_width_the_dump_ends_at` binds `lines`
   and never asserts on it. Plan step 5 specified that unpacking.

### 2026-08-26 20:15:25Z · review · session · session=63bc78e0-02bd-4216-adec-cbe498041aa3

`review` ran as session `63bc78e0-02bd-4216-adec-cbe498041aa3`
- replay: `claude --resume 63bc78e0-02bd-4216-adec-cbe498041aa3`
- log: `.project/logs/TICKET-063-review-63bc78e0.log`

### 2026-08-26 20:15:25Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed main...HEAD: all six acceptance criteria hold, 337 passed, no blocking findings; two minor nits recorded

### 2026-08-26 20:15:43Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-26 20:15:45Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/063


Current branch ticket/063 is up to date.
Already up to date.
Updating bc65819..b11b525
Fast-forward
 CLAUDE.md           |   3 ++
 pipeline/tui/app.py |  21 ++++++---
 tests/test_tui.py   | 125 +++++++++++++++++++++++++++++++++++++++++++++++++---
 3 files changed, 136 insertions(+), 13 deletions(-)

```

### 2026-08-26 20:15:45Z · merging · decision

decision recorded as `DEC-063`
