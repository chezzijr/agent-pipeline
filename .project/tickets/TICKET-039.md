---
id: TICKET-039
stage: done
class: bugfix
branch: ticket/039
test_file: tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump
files_declared:
- pipeline/tui/app.py
- tests/test_tui.py
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
  id: 6ba47c37-03fd-4665-b2d0-d2a564d8f437
  log: .project/logs/TICKET-039-review-6ba47c37.log
approved_by: chezzijr
approved_at: '2026-08-23T16:34:22.674972+00:00'
---

## Summary

`pipeline tui` writes raw terminal escape sequences into the ticket pane when
it shows a finished `planning` stage's log. `tail_log()`
(`pipeline/tui/app.py:117`) feeds every log to `StreamReader`; `parse()`
(`pipeline/stream/events.py:123`) hands a PTY line back verbatim as
`{"kind": "other", "raw": <line>}`, and `app.py:355` writes it into a
`RichLog`. Triage committed the failing test at `9daf8c7`.

Planning settled the open design decision with a count. `tail_log()` sniffs
the log tail for a raw `\x1b` byte; it does not read the stage's
`mode: interactive`. Of 233 logs in this repo's `.project/logs`, 8 carry a raw
escape byte and all 8 are `planning` logs; 35 other `planning` logs carry
none, because a stage runs headless when nothing can attach. The stage name
does not decide the format.

The fix adds `render_pty()` to `pipeline/tui/app.py` and branches `tail_log()`
on that sniff. Files: `pipeline/tui/app.py`, `tests/test_tui.py`.

`plan-validation` passed the plan on all eight items and re-ran the count: 235
logs today, 8 with a raw escape byte, all 8 `planning`. Implement the plan as
written. Two things to carry forward. First, `spawn()` merges the child's
stderr into the log (`stderr=subprocess.STDOUT`,
`pipeline/daemon/supervisor.py:392`), so "a stream-json log can never take the
other branch" in `## Decisions` is measured, not structural: 0 of the 227
non-`planning` logs carry an ESC. Second, no test covered `tail_log()`'s
stream-json path before this ticket, so step 7's test is that path's only
guard.

`implementing` executed the plan as written, all 9 steps. `render_pty()` is
new in `pipeline/tui/app.py`; `tail_log()` branches on `b"\x1b" in data`. Two
tests added to `tests/test_tui.py` alongside triage's. `uv run --group dev
pytest -q tests/test_tui.py` reports `19 passed`. Committed `6d50445`.

`review` read that commit and found nothing blocking. All four acceptance
criteria hold: `19 passed in 3.88s`, and the three named tests give `3 passed,
16 deselected`. The code matches `## Plan` steps 2-4 verbatim and deletes no
line, so triage's test is unmodified. One minor finding, carried forward and
not blocking: `render_pty()` replays on a fixed 40x120 `Screen()`, so a dump
from a PTY a client had widened re-wraps at 120 columns.

## Reproduction

`tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump`

Command: `uv run --group dev pytest -q tests/test_tui.py -k tail_log`

Writes a raw PTY dump (the same kind of bytes a finished `planning` stage
leaves) to `.project/logs/TICKET-001-planning.log`, calls `tail_log()`, and
asserts no returned line contains `\x1b`. It fails on `git diff`'s current
HEAD with:

```
AssertionError: raw escape byte reached the log line: '\x1b[2C\x1b[3A\x1b[?25h\x1b[?25l\x1b[2D\x1b[3B hello\x1b[7A\x1b[38;5;174m*\x1b[39m'
```

expect: raw escape byte reached the log line

## Digest

Files touched: `pipeline/tui/app.py` (`render_pty()` is new, `tail_log()`
gains one branch) and `tests/test_tui.py` (two tests beside triage's).

Key functions:
- `tail_log(project, tid)` -- `pipeline/tui/app.py:103`. Picks the newest
  `.project/logs/<tid>-*.log` by mtime, keeps the last `MAX_TAIL` (256 KiB),
  drops the partial first line, then feeds `StreamReader().feed(data)` and
  renders each event with `pipeline.cli.main.render`.
- `Screen` -- `pipeline/pty/host.py:88`. `feed(chunk) -> ()` plus `display`,
  40x120 by default. `pipeline/tui/app.py:39` already imports `Screen`, `ROWS`
  and `COLS`. `pipeline/pty/host.py` needs no change.
- `PipelineApp._show()` -- `pipeline/tui/app.py:344`. The one caller: it
  writes each returned line into the `RichLog`.
- `PipelineApp._attached()` -- `pipeline/tui/app.py:398`. The precedent for
  `rstrip()` on `Screen.display`: pyte pads every line to the full width.

Entry point: `pipeline tui`, then select a ticket whose newest log is a PTY
dump (TICKET-035 or TICKET-036 in this repo).

Gotchas, each measured on this machine today:
- pyte raised on none of three hostile inputs: a truncated escape sequence
  (`b"partial \x1b[38;5;1"` renders as `'partial'`), invalid UTF-8, and a cut
  mid-stream. `render_pty()` needs no try/except around `feed()`.
- Feeding the 256 KiB tail of `TICKET-035-planning-ee0c98d7.log` (660631
  bytes) took 0.121 s and produced 39 lines. `_show()` runs on the UI thread,
  so that delay is the whole cost of this change.
- A tail that starts mid-stream leaves stale cells from the frame it cut into.
  That is inherent to `MAX_TAIL`; widening the cap is out of scope.
- `render_pty(b"\x1b[2J\x1b[H")` leaves every line blank, so the helper
  returns `["(blank screen)"]` rather than `[]`.
- `spawn()` names a log `<tid>-<stage>-<session[:8]>.log`
  (`pipeline/daemon/supervisor.py:357`), but triage's test writes
  `TICKET-001-planning.log` with no session field. A rule that parsed the
  stage name out of the filename would have to accept both forms.
- `spawn()` runs a `mode: interactive` stage headless when nothing can attach
  (`pipeline/daemon/supervisor.py:348`), which is why `planning` produces logs
  of both formats.

## Decisions checked

None relevant. Grep terms over `.project/decisions/`: `tail_log`,
`StreamReader`, `stream-json`, `pyte`, `RichLog`, `interactive`, `log`,
`superseded-by`. No record names `tail_log`.

Consulted, none binding on this change:
- DEC-019 (TICKET-019, `pipeline/tui/app.py`) -- the local pyte screen is
  resized optimistically and `resize` is writer-only. It governs the attached
  live pane. `render_pty()` builds its own `Screen`, sends nothing to the
  daemon and never resizes.
- DEC-021 (TICKET-021, `pipeline/tui/app.py`) -- raw mode is intercepted in
  `App.on_event`. This change adds no key handling.
- DEC-011 (the frozen daemon contract: schema, event kinds, socket protocol)
  -- this change adds no event kind and no field. The rendering happens inside
  the TUI, off the wire.

No record in that directory carries a `superseded-by:` line, so none of the
three is advisory history.

## Plan

1. Run `uv run --group dev pytest -q tests/test_tui.py -k tail_log` and confirm `tests/test_tui.py` is red with `AssertionError: raw escape byte reached the log line: '\x1b[2C\x1b[3A...'` and the summary line `1 failed, 16 deselected`.
2. Add `render_pty()` to `pipeline/tui/app.py` directly above `tail_log()` (line 103), exactly this:

        def render_pty(data: bytes) -> list[str]:
            """A raw PTY dump -> the final screen, as plain text lines.

            An interactive stage that ran attached leaves terminal bytes, not
            stream-json. Replay them through the same pyte `Screen` the live
            pane uses: 40 lines of what the stage last showed, instead of
            2852 spinner frames with their cursor codes intact.
            """
            screen = Screen()
            screen.feed(data)
            lines = [ln.rstrip() for ln in screen.display]
            while lines and not lines[-1]:
                lines.pop()
            return lines or ["(blank screen)"]

3. In `tail_log()` in `pipeline/tui/app.py`, replace the final line `return [ln for ev in StreamReader().feed(data) if (ln := render(ev))]` with this, keeping the `except OSError` clause below it unchanged:

        # A stage that ran attached leaves a PTY dump, and valid stream-json
        # never carries a raw ESC (JSON escapes it), so the byte is the test.
        # The stage's name is not: `planning` runs headless whenever nothing
        # can attach to it, and then its log IS stream-json.
        if b"\x1b" in data:
            return render_pty(data)
        return [ln for ev in StreamReader().feed(data) if (ln := render(ev))]

4. Append this sentence to `tail_log()`'s docstring in `pipeline/tui/app.py`, after the sentence "Same `StreamReader` and same `render` as `pipeline logs`.": "A log carrying a raw ESC is a PTY dump instead, and goes through render_pty()."
5. Run `uv run --group dev pytest -q tests/test_tui.py -k tail_log` and expect `1 passed, 16 deselected` from `tests/test_tui.py`.
6. Add this test to `tests/test_tui.py`, below `test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump` (line 543):

        def test_tail_log_renders_a_pty_dump_as_the_final_screen():
            """Escape-free is not enough: the pyte screen is the point. A dump
            whose second frame clears and overwrites the first must come back
            as the last screen, once."""
            d = make_project()
            logs = d / ".project" / "logs"
            logs.mkdir(parents=True)
            (logs / "TICKET-001-planning.log").write_bytes(
                b"\x1b[H\x1b[2Jfirst frame\x1b[H\x1b[2Jsecond frame\x1b[K\n")

            assert tail_log(str(d), "TICKET-001") == ["second frame"]

7. Add this test to `tests/test_tui.py`, below the test step 6 added:

        def test_tail_log_still_renders_a_stream_json_log():
            """The sniff must not divert a headless stage's log into pyte: 35
            of the 43 `planning` logs in this repo are stream-json, from runs
            where nothing could attach."""
            d = make_project()
            logs = d / ".project" / "logs"
            logs.mkdir(parents=True)
            (logs / "TICKET-001-planning.log").write_bytes(
                b'{"type":"assistant","message":{"content":'
                b'[{"type":"text","text":"planning done"}]}}\n')

            assert tail_log(str(d), "TICKET-001") == ["planning done"]

8. Run `uv run --group dev pytest -q tests/test_tui.py` and expect `19 passed`.
9. Commit `pipeline/tui/app.py` and `tests/test_tui.py` together with `git commit -am "fix: render a finished interactive stage's log through pyte (TICKET-039)"`.

## Acceptance criteria

1. `tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump` passes -- no line `tail_log()` returns contains `\x1b`. Triage's test, unmodified.
2. `tests/test_tui.py::test_tail_log_renders_a_pty_dump_as_the_final_screen` passes -- a two-frame dump returns exactly `["second frame"]`, so the log shows the final screen and not every frame.
3. `tests/test_tui.py::test_tail_log_still_renders_a_stream_json_log` passes -- a one-line stream-json log returns `["planning done"]`, so the sniff leaves a headless stage's log on the `StreamReader` path.
4. `uv run --group dev pytest -q tests/test_tui.py` reports `19 passed`.

## Decisions

**`tail_log()` tells a PTY dump from stream-json by the bytes, never by the
stage's `mode:`.** The rule is `b"\x1b" in data`. Valid stream-json cannot
carry a raw ESC, because JSON escapes every control character; a raw
`\x1b` therefore means the log is not stream-json. Reading the stage's
`mode: interactive` was the obvious alternative and it is wrong: `spawn()`
runs an interactive stage headless when nothing can attach
(`pipeline/daemon/supervisor.py:348`), so `planning` writes both formats. The
count on 2026-08-23 in this repo's `.project/logs`: 233 logs, 8 with a raw
escape byte and all 8 `planning`, 35 further `planning` logs with none, 0
non-`planning` logs with one. A stage-name rule would have sent those 35
stream-json logs through pyte and shown a screen of raw JSON.

**The fallback direction is the safe one.** A PTY dump that happens to contain
no escape at all goes to `StreamReader`, which returns its lines verbatim --
plain text, which is readable. A stream-json log can never take the other
branch. If the sniff is ever changed, keep that asymmetry.

**`render_pty()` drops trailing blank lines and returns `["(blank screen)"]`
for an empty screen.** A pyte screen is always 40 lines; returning them all
would pad the `RichLog` with blanks, and returning `[]` would make a cleared
screen look like a missing log.

## Rollback

Revert the single commit from step 9 (`git revert <sha>`, both files in one
commit). The TUI goes back to writing raw escape sequences into the `RichLog`
for a finished interactive stage, which is this ticket's bug and nothing
worse. `pipeline/pty/host.py` is not modified, so the live attached pane and
`pipeline logs` behave the same before and after; nothing outside
`pipeline/tui/app.py` imports `render_pty()`.

## Thread

### 2026-08-23 14:21:54Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-23 14:22:11Z · triage · note

`triage` was interrupted; lease released

### 2026-08-23 · triage · note

Reproduced. Added `tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump`,
committed at `9daf8c7`. It fails with `AssertionError: raw escape byte
reached the log line: ...` — matches the ticket's reported symptom.

Root cause: `tail_log()` (`pipeline/tui/app.py:117`) always runs a log's
bytes through `StreamReader`/`parse()` (`pipeline/stream/events.py:123`),
which cannot detect a raw PTY dump and returns it verbatim as
`{"kind": "other", "raw": <line>}`. The fix needs to route a finished
`mode: interactive` stage's log through the pyte `Screen`
(`pipeline/pty/host.py`) instead — the same emulator `_pty()` already uses
while the stage is live.

Not a `chore`: picking how `tail_log()` distinguishes a PTY dump from a
stream-json log (ticket stage metadata vs. content sniffing) is a design
choice, and the fix touches `pipeline/tui/app.py` plus likely
`pipeline/pty/host.py`.

result: ok

### 2026-08-23 14:27:28Z · triage · session · session=f26794db-e437-46e8-a37b-6121cd8756a4

`triage` ran as session `f26794db-e437-46e8-a37b-6121cd8756a4`
- replay: `claude --resume f26794db-e437-46e8-a37b-6121cd8756a4`
- log: `.project/logs/TICKET-039-triage-f26794db.log`

### 2026-08-23 14:27:28Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced raw-escape leak; committed failing test tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump at 9daf8c7

### 2026-08-23 · planning · note

Plan written. `tail_log()` tells a PTY dump from stream-json by sniffing the
log tail for a raw `\x1b` byte. It does not read the stage's
`mode: interactive`.

Evidence for that choice: of 233 logs in `.project/logs`, 8 carry a raw escape
byte and all 8 are `planning`; 35 further `planning` logs carry none, and no
other stage's log carries one. `spawn()` runs an interactive stage headless
when nothing can attach (`pipeline/daemon/supervisor.py:348`), so `planning`
writes both formats and the stage name cannot decide.

Measured, not assumed: pyte raised on none of a truncated escape sequence,
invalid UTF-8, or a cut mid-stream. Feeding the 256 KiB tail of
`TICKET-035-planning-ee0c98d7.log` took 0.121 s.

Out of scope, noted and not fixed: `cmd_logs()` (`pipeline/cli/main.py:389`)
has the same blind spot from the other side. It prints `(no stream-json here
-- an interactive stage's log is the raw terminal stream: cat <log>)` rather
than rendering the screen. The same sniff would fix it. This ticket's
reproduction test covers `tail_log()` only.

result: ok

### 2026-08-23 14:34:20Z · planning · session · session=8523da6a-234a-4745-9f4e-5e3edcaf91a7

`planning` ran as session `8523da6a-234a-4745-9f4e-5e3edcaf91a7`
- replay: `claude --resume 8523da6a-234a-4745-9f4e-5e3edcaf91a7`
- log: `.project/logs/TICKET-039-planning-8523da6a.log`

### 2026-08-23 14:34:20Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: tail_log() sniffs the tail for a raw ESC byte and renders a PTY dump through the pyte Screen; 9 steps, 2 new tests

### 2026-08-23 14:34:32Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump` fails as required
```
s, not hand escape bytes to a `RichLog`."""
        d = make_project()
        logs = d / ".project" / "logs"
        logs.mkdir(parents=True)
        (logs / "TICKET-001-planning.log").write_bytes(
            b"\x1b[2C\x1b[3A\x1b[?25h\x1b[?25l\x1b[2D\x1b[3B hello\x1b[7A\x1b[38;5;174m*\x1b[39m\n")
    
        lines = tail_log(str(d), "TICKET-001")
    
        for line in lines:
>           assert "\x1b" not in line, f"raw escape byte reached the log line: {line!r}"
E           AssertionError: raw escape byte reached the log line: '\x1b[2C\x1b[3A\x1b[?25h\x1b[?25l\x1b[2D\x1b[3B hello\x1b[7A\x1b[38;5;174m*\x1b[39m'
E           assert '\x1b' not in '\x1b[2C\x1b...74m*\x1b[39m'
E             
E             '\x1b' is contained here:
E               [2C[3A[?25h[?25l[2D[3B hello[7A[38;5;174m*[39m
E             ? +

tests/test_tui.py:543: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump` fails on base `main` too -- the bug is not already fixed upstream
```
1b[2C\x1b[3A\x1b[?25h\x1b[?25l\x1b[2D\x1b[3B hello\x1b[7A\x1b[38;5;174m*\x1b[39m'
E           assert '\x1b' not in '\x1b[2C\x1b...74m*\x1b[39m'
E             
E             '\x1b' is contained here:
E               [2C[3A[?25h[?25l[2D[3B hello[7A[38;5;174m*[39m
E             ? +

tests/test_tui.py:543: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.50s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-gfb48c4b/base
      Built pipeline @ file:///tmp/pipeline-base-gfb48c4b/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-23 · plan-validation · note

Plan validated. All eight items pass.

1. Root cause: `tail_log()` assumes every stage log is stream-json. A finished
   interactive stage's log is a raw PTY dump, `parse()` returns it as
   `{"kind": "other", "raw": <line>}`, and `render` hands the escape bytes to
   the `RichLog`. The plan routes by content, so it fixes the assumption.
2. Decisions: DEC-019 governs the live pane's resize and writer slot;
   `render_pty()` builds its own `Screen`, never resizes, sends nothing.
   DEC-021 is key handling, DEC-011 is the wire contract. None constrain this.
3. Scope: every step maps to a criterion. Step 4 edits one docstring in the
   function step 3 changes. `cmd_logs()` stayed out.
4. Criteria falsify: criterion 2 fails if the fix replays frames, criterion 3
   fails if the sniff diverts stream-json.
5. No research left: steps name `pipeline/tui/app.py:103`, the exact line 117
   they replace, and both test bodies verbatim.
6. Riskiest step is 3, the sniff. Fallback stated: an escape-free PTY dump
   falls to `StreamReader`, plus the one-commit revert.
7. Regression surface: `_show()` (`pipeline/tui/app.py:354`) is the only
   caller. No test covered the stream-json path before; criterion 3's test is
   the guard.
8. Blast radius: `bugfix`, 2 files, both in `files_declared`.

Confirmed on this machine: 235 logs in `.project/logs`, 8 carry a raw escape
byte, all 8 `planning` (planning counted 233; this ticket added two since).
pyte returns `['second frame', '', '', '']` for criterion 2's input, so the
helper returns `["second frame"]`.

One correction to `## Decisions`. "A stream-json log can never take the other
branch" is empirical, not structural. `spawn()` merges the child's stderr into
the same log (`stderr=subprocess.STDOUT`,
`pipeline/daemon/supervisor.py:392`), so an ANSI-colored stderr line would put
a raw ESC in an otherwise stream-json log and divert it to pyte. It has not
happened: 0 of the 227 non-`planning` logs carry one. Keep the sniff; read
that sentence as measured, not proven.

result: ok

### 2026-08-23 14:37:40Z · plan-validation · session · session=00712a60-d232-4748-af5c-4e852416928f

`plan-validation` ran as session `00712a60-d232-4748-af5c-4e852416928f`
- replay: `claude --resume 00712a60-d232-4748-af5c-4e852416928f`
- log: `.project/logs/TICKET-039-plan-validation-00712a60.log`

### 2026-08-23 14:37:40Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight items; verified the sniff count (8 of 235 logs carry a raw ESC, all planning) and pyte's two-frame output

### 2026-08-23 16:34:22Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-23 16:34:35Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump` fails as required
```
s, not hand escape bytes to a `RichLog`."""
        d = make_project()
        logs = d / ".project" / "logs"
        logs.mkdir(parents=True)
        (logs / "TICKET-001-planning.log").write_bytes(
            b"\x1b[2C\x1b[3A\x1b[?25h\x1b[?25l\x1b[2D\x1b[3B hello\x1b[7A\x1b[38;5;174m*\x1b[39m\n")
    
        lines = tail_log(str(d), "TICKET-001")
    
        for line in lines:
>           assert "\x1b" not in line, f"raw escape byte reached the log line: {line!r}"
E           AssertionError: raw escape byte reached the log line: '\x1b[2C\x1b[3A\x1b[?25h\x1b[?25l\x1b[2D\x1b[3B hello\x1b[7A\x1b[38;5;174m*\x1b[39m'
E           assert '\x1b' not in '\x1b[2C\x1b...74m*\x1b[39m'
E             
E             '\x1b' is contained here:
E               [2C[3A[?25h[?25l[2D[3B hello[7A[38;5;174m*[39m
E             ? +

tests/test_tui.py:543: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================

```
- ok: `tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump` fails on base `main` too -- the bug is not already fixed upstream
```
1b[2C\x1b[3A\x1b[?25h\x1b[?25l\x1b[2D\x1b[3B hello\x1b[7A\x1b[38;5;174m*\x1b[39m'
E           assert '\x1b' not in '\x1b[2C\x1b...74m*\x1b[39m'
E             
E             '\x1b' is contained here:
E               [2C[3A[?25h[?25l[2D[3B hello[7A[38;5;174m*[39m
E             ? +

tests/test_tui.py:543: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-4nsutj2v/base
      Built pipeline @ file:///tmp/pipeline-base-4nsutj2v/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-23 16:34:35Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-23 · implementing · todo

1. [x] Confirm RED: `test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump` fails
2. [x] Add `render_pty()` to `pipeline/tui/app.py`
3. [x] Branch `tail_log()` on `b"\x1b" in data`
4. [x] Append docstring sentence
5. [x] Confirm GREEN: triage's test passes
6. [x] Add `test_tail_log_renders_a_pty_dump_as_the_final_screen`
7. [x] Add `test_tail_log_still_renders_a_stream_json_log`
8. [x] Run full `tests/test_tui.py`, expect `19 passed`
9. [x] Commit both files

### 2026-08-23 · implementing · note

Executed the plan exactly, all 9 steps, no deviation.

1. Confirmed RED: `AssertionError: raw escape byte reached the log line: '\x1b[2C\x1b[3A\x1b[?25h\x1b[?25l\x1b[2D\x1b[3B hello\x1b[7A\x1b[38;5;174m*\x1b[39m'`, `1 failed, 16 deselected`.
2. Added `render_pty()` above `tail_log()` in `pipeline/tui/app.py`, verbatim from the plan.
3. Replaced `tail_log()`'s final line with the `b"\x1b" in data` branch, verbatim.
4. Appended the docstring sentence.
5. Confirmed GREEN: `1 passed, 16 deselected`.
6. Added `test_tail_log_renders_a_pty_dump_as_the_final_screen`, verbatim.
7. Added `test_tail_log_still_renders_a_stream_json_log`, verbatim.
8. `uv run --group dev pytest -q tests/test_tui.py` -> `19 passed in 4.08s`.
9. Committed `pipeline/tui/app.py` and `tests/test_tui.py` as `6d50445`, message `fix: render a finished interactive stage's log through pyte (TICKET-039)`.

All four acceptance criteria met by the step-8 run. No file outside `files_declared` touched.

result: ok

### 2026-08-23 16:35:38Z · implementing · session · session=75c35c3c-508c-4a15-b46d-27a1dbd0f0d4

`implementing` ran as session `75c35c3c-508c-4a15-b46d-27a1dbd0f0d4`
- replay: `claude --resume 75c35c3c-508c-4a15-b46d-27a1dbd0f0d4`
- log: `.project/logs/TICKET-039-implementing-75c35c3c.log`

### 2026-08-23 16:35:38Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added render_pty() and branched tail_log() on a raw ESC byte; 19 passed in tests/test_tui.py; committed 6d50445

### 2026-08-23 · review · note

Reviewed the delta: commit `6d50445`, the only commit since triage's test. No
blocking findings.

Checked the four acceptance criteria. `uv run --group dev pytest -q
tests/test_tui.py` reports `19 passed in 3.88s`; the three named tests report
`3 passed, 16 deselected`. The diff adds 23 lines to `pipeline/tui/app.py` and
27 to `tests/test_tui.py` and deletes none, so triage's test is unmodified.
`render_pty()` and the `b"\x1b" in data` branch match `## Plan` steps 2-4
verbatim. No drift.

Refuted two candidate findings.

1. "Bracketed pyte text raises MarkupError in the `RichLog`" -- refuted:
   `RichLog.__init__` defaults `markup: bool = False` (textual 8.2.8) and
   `pipeline/tui/app.py:205` passes no `markup`.
2. "pyte raises on a truncated escape or on invalid UTF-8" -- refuted:
   `render_pty(b"partial \x1b[38;5;1")` returns `['partial']`, and
   `render_pty(b"\xff\xfe bad \x1b[31mred")` returns `['�� bad red']`.

Surviving finding.

1. minor, not blocking: `render_pty()` replays on a fixed 40x120 `Screen()`. A
   client can widen the real PTY (`host.set_winsize`,
   `pipeline/daemon/server.py:616`), and a wider dump then re-wraps at 120
   columns. The log records no size, so the original width is not recoverable
   here.

result: ok

### 2026-08-23 16:38:09Z · review · session · session=6ba47c37-03fd-4665-b2d0-d2a564d8f437

`review` ran as session `6ba47c37-03fd-4665-b2d0-d2a564d8f437`
- replay: `claude --resume 6ba47c37-03fd-4665-b2d0-d2a564d8f437`
- log: `.project/logs/TICKET-039-review-6ba47c37.log`

### 2026-08-23 16:38:09Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed 6d50445: matches the plan verbatim, 19 passed, no blocking findings; one minor note on the fixed 40x120 replay screen

### 2026-08-23 16:38:20Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-23 16:38:21Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/039


Already up to date.
Updating bdf24aa..6d50445
Fast-forward
 pipeline/tui/app.py | 23 +++++++++++++++++++++++
 tests/test_tui.py   | 45 ++++++++++++++++++++++++++++++++++++++++++++-
 2 files changed, 67 insertions(+), 1 deletion(-)

```

### 2026-08-23 16:38:21Z · merging · decision

decision recorded as `DEC-039`
