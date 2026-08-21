---
id: TICKET-019
stage: planning
class: bugfix
branch: ticket/019
test_file: tests/test_tui.py::test_attaching_sends_the_pane_size
files_declared: []
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
  stage: triage
  id: b4014330-d867-4113-8807-38634c9a7c15
  log: .project/logs/TICKET-019-triage-b4014330.log
---

## Summary

the TUI never sends `resize`, so an attached stage is stuck at 40x120

**Planning (2026-08-21): plan written, client-side only.** Two files:
`pipeline/tui/app.py` and `tests/test_tui.py`. The daemon half (`_op_resize`,
`host.set_winsize`, `host.Screen.resize`) is complete and already covered end
to end by `tests/test_pty.py::test_resize_reaches_both_the_child_and_the_screen`
-- do not touch it. The fix: a `PtyPane(Static)` that reports its own resizes,
`#pty { height: 1fr; }` so the pane has a real region to report, and a
`_resize()` that sends the pane's size and resizes the local `pyte` screen to
match. Three gotchas the implementer must not rediscover: `_op_resize` is
**writer-only and claims the writer slot**, so a read-only viewer must not send
it; `events.Resize` is `bubble=False`, so the hook goes on the pane widget and
not on `App`; and two assertions in the existing
`test_an_interactive_stage_attaches_and_a_dropped_frame_reattaches` are
over-specified against `ops()` and must be relaxed to attach *counts*. The
whole approach was prototyped before this plan was written -- see `## Digest`.

**Triage (2026-08-21): reproduced.** Failing test committed on `ticket/019`:
`tests/test_tui.py::test_attaching_sends_the_pane_size` -- attach on a 200x50
terminal sends `['attach']` and no `resize`. Daemon side (`_op_resize`,
`host.Screen.resize`, `host.set_winsize`) is already complete and correct; the
fix is client-side in `pipeline/tui/app.py` only: send `resize` on attach and
on `on_resize`, and keep the local `pyte` `Screen` at the same dims. See
`## Reproduction` and `## Digest`.

`pipeline tui` attaches to an interactive stage and paints its screen, but it never
tells the daemon how big its pane actually is. The child is sized once, in
`pipeline/pty/host.py:28` (`ROWS, COLS = 40, 120`), set on the slave before `exec`
and never changed again. On a 1920px-wide terminal the agent's output occupies a
120-column box in the corner and the rest of the pane is dead space.

The protocol half already exists and is unused:

    $ grep -n "_op_resize" pipeline/daemon/server.py
    599:    def _op_resize(self, conn, rid, req) -> dict:
    $ grep -c resize pipeline/tui/app.py
    0

`_op_resize` is writer-only and documented there as "MUST-HAVE, not a nicety: a pane
and a child that disagree about width render garbage".

Expected: on attach, and on every terminal resize afterwards, the TUI sends its
current pane size; the daemon applies `TIOCSWINSZ` to the master and the child
redraws at that size. The local `pyte` screen has to be rebuilt to the same
dimensions or the two disagree again in the other direction.

Suggestion, not a decision: Textual delivers `on_resize`, and `Screen` already takes
`(rows, cols)` at construction (`tui/app.py:356`).

## Reproduction

`tests/test_tui.py::test_attaching_sends_the_pane_size`

    uv run --group dev pytest -q "tests/test_tui.py::test_attaching_sends_the_pane_size"

Attaches to an interactive stage in a 200x50 pilot terminal, answers the
`attach` with the daemon's 40x120 snapshot, then asks what the client sent:

    >           assert "resize" in app.stream.ops(), \
                    f"attached without sending a size: {app.stream.ops()}"
    E           AssertionError: attached without sending a size: ['attach']
    E           assert 'resize' in ['attach']

    tests/test_tui.py:394: AssertionError
    1 failed in 0.87s

expect: attached without sending a size: ['attach']

The two later assertions (`kw["cols"] > 120`, and the local `pyte` screen
matching what was sent) are unreachable today and cover the other half of the
symptom: the pane and the child agreeing on width in both directions.

## Digest

Confirmed real, and the diagnosis in `## Summary` holds:

- `pipeline/pty/host.py:28` `ROWS, COLS = 40, 120`, set on the slave in the
  child before `exec` (`start()`), never changed after.
- `pipeline/daemon/server.py:599` `_op_resize` is complete -- bounds-checks the
  dims, claims the writer, `host.set_winsize()` on the master and
  `rec["screen"].resize()`. `host.Screen.resize()` exists too. Nothing calls
  either: `grep -c resize pipeline/tui/app.py` is still 0.
- `pipeline/tui/app.py:356` `_attached()` builds `Screen(rows, cols)` from the
  daemon's reported size, so the client currently *adopts* 40x120 rather than
  imposing its own.

So the fix is client-side only: send `resize` on attach and on `on_resize`,
and rebuild/resize the local `Screen` to the same dims.

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-21 04:29:43Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 · triage · reproduced

Wrote `tests/test_tui.py::test_attaching_sends_the_pane_size` in the file's
existing style (Textual pilot + `FakeClient`/`FakeStream`, plain asserts,
`asyncio.run`). It fails on the reported symptom -- `attached without sending a
size: ['attach']` -- not on setup: the attach itself succeeds and the pane
paints, only the size op is missing. Committed as `ccc22c6`.

Read before writing: `pty/host.py` (`ROWS, COLS = 40, 120`, `set_winsize`,
`Screen.resize`), `daemon/server.py:599` `_op_resize`, `tui/app.py`
`_pty`/`_attached`/`_detach`. Daemon half needs no change.

Note for later stages, outside triage's scope:

- The test asserts the *client* half only (an op named `resize` with a `cols`
  wider than 120, and `pty_screen.cols` matching it). Nothing here exercises
  `_op_resize` end to end; `tests/test_server.py` is where that would go if the
  implementer wants it.
- `_attached()` currently sizes the local `Screen` from the daemon's reply. If
  the fix sends `resize` before or alongside `attach`, that reply's dims and
  the pane's must not fight -- the ticket's "disagree again in the other
  direction" warning is about exactly this line.
- The reattach path (`dropped` frame) re-runs `attach`, so whatever sends the
  size on attach has to cover that path too or a drop silently reverts to
  40x120.

### 2026-08-21 04:31:38Z · triage · session · session=b4014330-d867-4113-8807-38634c9a7c15

`triage` ran as session `b4014330-d867-4113-8807-38634c9a7c15`
- replay: `claude --resume b4014330-d867-4113-8807-38634c9a7c15`
- log: `.project/logs/TICKET-019-triage-b4014330.log`

### 2026-08-21 04:31:38Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

reproduced - attach sends no resize op; failing test committed as ccc22c6

### 2026-08-21 04:37:45Z · planning · note

`planning` was interrupted; lease released
