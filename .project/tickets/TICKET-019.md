---
id: TICKET-019
stage: done
class: bugfix
branch: ticket/019
test_file: tests/test_tui.py::test_attaching_sends_the_pane_size
files_declared:
- pipeline/tui/app.py
- tests/test_tui.py
counters:
  plan_validation_attempts: 0
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 32041b3f-f0e6-41e9-929d-a3fef13d5040
  log: .project/logs/TICKET-019-review-32041b3f.log
approved_by: chezzijr
approved_at: '2026-08-21T05:15:33.024198+00:00'
---

## Summary

**Review (2026-08-21, loop 2): PASS, no blocking findings.** The delta is
`d9c0c26..HEAD` = `bcd57a9`, nine added lines in
`tests/test_tui.py::test_resizing_the_terminal_resizes_the_child` and nothing
else (`git status --short` empty). The previous loop's one blocking finding is
resolved and I verified it myself rather than trusting the thread: with
`_resize()` monkeypatched in-process to drop only the equal-dims early return,
the suite now fails at `tests/test_tui.py:437` with `re-attaching re-sent a
size the daemon already has`. The reattach assertion is real evidence, not a
restatement. Full suite re-run here: **164 passed**. Four non-blocking notes
are in `## Thread` (one new, three carried forward); none needs work in this
ticket.

**Implementing (2026-08-21, retry): done, committed as `bcd57a9`.** Fixed the
one blocking finding from review: the third `resize_terminal(300, 60)` in
`test_resizing_the_terminal_resizes_the_child` was vacuous (Textual sends no
`Resize` event when a widget's size does not change, so it never exercised the
early-return guard). Added the reattach exercise review specified verbatim
(`dropped` frame -> `attach` reply reporting the size already imposed ->
assert `resize` count stays 2), verified RED against a mutant with the
equal-dims guard removed (`3 == 2` failure), then GREEN against the real code.
Also corrected the acceptance criterion's falsification clause in `##
Acceptance criteria` to name the reattach input instead of the repeated
terminal resize, per review's instruction. `_resize()` itself was not
touched. Full suite still **164 passed**, guard script's 79 cases still pass.

**Review (2026-08-21): FAIL, one blocking finding, and it is a test problem,
not a code problem.** The shipped behaviour in `pipeline/tui/app.py` is correct
and I re-ran the suite myself: **164 passed**. What fails review is the third
bullet of `## Acceptance criteria` -- "the third `resize_terminal(300, 60)` ...
adds no op. Falsified by removing the `(rows, cols) == (self.pty_screen.rows,
self.pty_screen.cols)` early return". Measured: that mutation does **not**
redden `test_resizing_the_terminal_resizes_the_child`, because Textual delivers
no `Resize` at all when the size is unchanged, so `_resize()` is never called
and the assertion passes either way. The early return is real and load-bearing
-- just on the *reattach* path, not that one. Fix is ~4 lines in a test; the
exact falsifying input and its measured output are in `## Thread`. Do not
change `_resize()`.

**Implementing (2026-08-21): done, committed as `d9c0c26`.** Applied the
verified diff verbatim: `PtyPane(Static)` with `on_resize`, `#pty { height:
1fr; }`, `pty_writer`/`resize_id` state, `_resize()`, the `resize_id` branch in
`on_frame`, and the four `Static` -> `PtyPane` call-site swaps in
`pipeline/tui/app.py`; the two relaxed assertions plus
`test_resizing_the_terminal_resizes_the_child` and
`test_a_read_only_viewer_never_sends_a_resize` in `tests/test_tui.py`.
`tests/test_tui.py::test_attaching_sends_the_pane_size` passes.
`tests/test_tui.py` (14 tests) and the full suite (**164 passed**, not the
predicted 163 -- see `## Thread`) are green, and the guard script's 79 cases
still pass unmodified. Review confirmed the 164 and the verbatim application;
only `files_declared` changed and the daemon half has no diff.

the TUI never sends `resize`, so an attached stage is stuck at 40x120

**Plan validation (2026-08-21): PASS on all eight items.** Root cause is the
missing caller, not the missing op: `_op_resize` (`daemon/server.py:599`) is
complete and `grep -c resize pipeline/tui/app.py` is 0. Every anchor in the plan
was re-checked against this tree and all of them hold (`host.py:28 ROWS, COLS =
40, 120`; `Screen.rows/.cols/.resize` at `host.py:107/111/124`; the four
`query_one("#pty", Static)` sites at `app.py:155/308/337/369`; `_attached` at
350; the `keys_flight` branch at `on_frame` 259). DEC-011 does not constrain a
client-only change and the plan adds no op. Implement steps 1-15 as written.
Two non-blocking notes for the implementer are in `## Thread`.

**Planning (2026-08-21): plan written and prototyped green.** Client-side only,
two files: `pipeline/tui/app.py` and `tests/test_tui.py`. The daemon half
(`_op_resize`, `host.set_winsize`, `host.Screen.resize`) is complete and already
covered end to end by
`tests/test_pty.py::test_resize_reaches_both_the_child_and_the_screen` -- do not
touch it, and do not add a protocol op (DEC-011). The whole change was applied
to a scratch copy of this worktree and the full suite run there: **161 passed**.
The verified diff is in `## Digest`; apply it verbatim.

The fix: a `PtyPane(Static)` that reports its own resizes, `#pty { height: 1fr; }`
so the pane has a real region to report, and a `_resize()` that sends the pane's
size and resizes the local `pyte` screen to match.

Four gotchas measured, not guessed:

1. `events.Resize` has `bubble = False` (textual 8.2.8), so the hook goes on the
   pane widget, never on `App`.
2. Textual does **not** deliver a `Resize` when a widget's `display` flips
   `False -> True` -- the pane is laid out once at mount, long before
   `pty_screen` exists. Relying on `on_resize` alone leaves the target test
   failing with `['attach']`; `_attached()` must call `_resize()` itself. This
   was tried and measured.
3. `_op_resize` is **writer-only and claims the writer slot**, exactly like
   `_op_input`. A read-only viewer must not send it -- hence `self.pty_writer`,
   set from the attach reply.
4. The local `pyte` screen is resized **optimistically at send time**, not on
   the ack: `test_attaching_sends_the_pane_size` delivers only the attach reply
   and then asserts `app.pty_screen.cols == kw["cols"]`.

Two assertions in `test_an_interactive_stage_attaches_and_a_dropped_frame_reattaches`
are over-specified against `ops()` and must be relaxed to attach *counts*.

**Triage (2026-08-21): reproduced.** Failing test committed on `ticket/019`:
`tests/test_tui.py::test_attaching_sends_the_pane_size` -- attach on a 200x50
terminal sends `['attach']` and no `resize`. See `## Reproduction`.

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

### Where everything is (nobody should re-explore this)

| What | Where | Note |
|---|---|---|
| the fixed child size | `pipeline/pty/host.py:28` | `ROWS, COLS = 40, 120`, set on the slave in the child before `exec` |
| the daemon op | `pipeline/daemon/server.py:599` `_op_resize` | complete: `_dim` bounds 1..`MAX_DIM` (1000), `_writer` claims, `host.set_winsize`, `rec["screen"].resize` |
| the writer slot | `pipeline/daemon/server.py:519` `_writer` | one variable, one comparison; `resize` claims it just like `input` |
| the client attach | `pipeline/tui/app.py` `_pty` / `_attached` / `_detach` | attach rides the SUBSCRIPTION connection; the reply lands in `on_frame` |
| the local emulator | `pipeline/tui/app.py` `_attached` | `Screen(rows, cols)` built from the daemon's reported dims |
| `host.Screen` API | `pipeline/pty/host.py:95-125` | `.rows` / `.cols` properties, `.resize(rows, cols)`, `.display` |
| daemon end-to-end proof | `tests/test_pty.py::test_resize_reaches_both_the_child_and_the_screen` | already green; this ticket does not touch it |

Measurements from the scratch prototype (`run_test(size=(200, 50))`, tree is 34
columns, status and footer one row each):

    AFTER ATTACH:  [('attach', {...}), ('resize', {'rows': 48, 'cols': 166})]
    AFTER RESIZE:  ... ('resize', {'rows': 58, 'cols': 266})     # resize_terminal(300, 60)
    SCREEN:        58 266                                        # local pyte followed
    AFTER SAME:    ... no third resize                           # idempotent
    READONLY:      [('attach', {...})]                           # writer=False sends nothing

Two more things the implementer needs and cannot see from the diff:

- Keep the `Static` import in `pipeline/tui/app.py`: `#status` is still a plain
  `Static`. Only the `#pty` widget changes class.
- In `on_frame`, the new `resize_id` branch goes **between** the `pty_id`
  (attach reply) branch and the `keys_flight` branch, and the `keys_flight`
  branch must survive the edit. Dropping it makes
  `test_keystrokes_are_chunked_and_a_short_write_is_resent` fail on the last
  chunk -- that mistake was made once in the prototype and cost a run.
- The reattach-after-`dropped` path needs no extra code: it re-runs `attach`,
  the reply lands in `_attached`, and `_attached` calls `_resize` again. If the
  daemon reports the size we already asked for, `_resize` sends nothing.

### The verified diff -- apply verbatim

```diff
diff --git a/pipeline/tui/app.py b/pipeline/tui/app.py
index 075ea04..24a3ad4 100644
--- a/pipeline/tui/app.py
+++ b/pipeline/tui/app.py
@@ -96,10 +96,20 @@ def tail_log(project: str, tid: str) -> list[str]:
         return [f"(log unreadable: {e})"]
 
 
+class PtyPane(Static):
+    """The attached terminal. A widget and not a bare `Static` for one reason:
+    `events.Resize` does NOT bubble, so the only place that learns this pane
+    real size is the pane itself."""
+
+    def on_resize(self, event) -> None:
+        self.app._resize()
+
+
 class PipelineApp(App):
     CSS = """
     #tree { width: 34; }
     #log { height: 1fr; }
+    #pty { height: 1fr; }
     #status { height: 1; background: $panel; color: $text; }
     """
 
@@ -128,6 +138,8 @@ class PipelineApp(App):
         self.attached = None          # (project, ticket) the PTY pane is showing
         self.pty_id = None            # the request id its `attach` frames carry
         self.pty_screen = None        # our own emulator, fed by those frames
+        self.pty_writer = False       # resize is writer-only
+        self.resize_id = None         # the resize awaiting its reply
         self.keys_out = b""           # keystrokes the daemon has not taken yet
         self.keys_flight = None       # (request id, chunk) currently with it
 
@@ -147,12 +159,12 @@ class PipelineApp(App):
                 # this pane is fed raw terminal output. One bracketed path on
                 # the attached screen (`ls [/home/x]`) raises MarkupError
                 # inside the frame handler and takes the pane down.
-                yield Static(id="pty", markup=False)
+                yield PtyPane(id="pty", markup=False)
         yield Static("", id="status")
         yield Footer()
 
     def on_mount(self) -> None:
-        self.query_one("#pty", Static).display = False
+        self.query_one("#pty", PtyPane).display = False
         self.query_one(Tree).root.expand()
         rows = self._rows()
         self.projects = sorted({r["project"] for r in rows}) or (
@@ -256,6 +268,11 @@ class PipelineApp(App):
             return self._pty_frame(msg["pty"])
         if self.pty_id is not None and msg.get("id") == self.pty_id:
             return self._attached(msg)
+        if self.resize_id is not None and msg.get("id") == self.resize_id:
+            self.resize_id = None
+            if not msg.get("ok"):
+                self.notify("resize: %s" % msg.get("error"))
+            return
         if self.keys_flight and msg.get("id") == self.keys_flight[0]:
             return self._keys_acked(msg)
         if "dropped" in msg:
@@ -305,7 +322,7 @@ class PipelineApp(App):
         if self._pty(row):
             return
         self._detach()
-        self.query_one("#pty", Static).display = False
+        self.query_one("#pty", PtyPane).display = False
         log.display = True
         for line in tail_log(key[0], key[1]):
             log.write(line)
@@ -334,7 +351,7 @@ class PipelineApp(App):
                 return False
             self.attached = (row["project"], row["id"])
         self.query_one("#log", RichLog).display = False
-        self.query_one("#pty", Static).display = True
+        self.query_one("#pty", PtyPane).display = True
         return True
 
     def _detach(self) -> None:
@@ -345,6 +362,7 @@ class PipelineApp(App):
             except (OSError, ValueError):
                 pass
         self.attached = self.pty_id = self.pty_screen = None
+        self.pty_writer, self.resize_id = False, None
         self.keys_out, self.keys_flight = b"", None
 
     def _attached(self, msg: dict) -> None:
@@ -361,15 +379,34 @@ class PipelineApp(App):
         lines = [str(x) for x in (d.get("screen") or [])]
         self.pty_screen.feed(b"\x1b[H" + "\r\n".join(
             l.rstrip() for l in lines).encode("utf-8", "replace"))
+        self.pty_writer = bool(d.get("writer"))
         self._paint_pty()
-        if not d.get("writer"):
+        self._resize()
+        if not self.pty_writer:
             self.notify("another client holds the writer: read-only")
 
     def _paint_pty(self) -> None:
-        pane = self.query_one("#pty", Static)
+        pane = self.query_one("#pty", PtyPane)
         pane.update("\n".join(self.pty_screen.display))
         pane.display = True
 
+    def _resize(self) -> None:
+        """Tell the daemon how big this pane is, and keep our own emulator the
+        same size."""
+        if self.pty_screen is None or self.stream is None or not self.pty_writer:
+            return
+        size = self.query_one("#pty", PtyPane).size
+        rows, cols = size.height, size.width
+        if rows < 1 or cols < 1 or (rows, cols) == (self.pty_screen.rows,
+                                                    self.pty_screen.cols):
+            return
+        try:
+            self.resize_id = self.stream.send("resize", rows=rows, cols=cols)
+        except (OSError, ValueError) as e:
+            return self.notify("resize: %s" % e)
+        self.pty_screen.resize(rows, cols)
+        self._paint_pty()
+
     def _pty_frame(self, blob: str) -> None:
         if self.pty_screen is None:
             return
diff --git a/tests/test_tui.py b/tests/test_tui.py
index 6717874..f6dbc57 100644
--- a/tests/test_tui.py
+++ b/tests/test_tui.py
@@ -243,11 +243,11 @@ def test_an_interactive_stage_attaches_and_a_dropped_frame_reattaches():
             assert "yes" in pty_pane(app), pty_pane(app)
             assert "Allow Bash?" in pty_pane(app), \
                 "the pre-attach screen was lost: the emulator started blank"
-            assert app.stream.ops() == ["attach"], app.stream.sent
+            assert app.stream.ops().count("attach") == 1, app.stream.sent
 
             app.on_frame({"sub": app.pty_id, "dropped": 3})
             await pilot.pause()
-            assert app.stream.ops() == ["attach", "attach"], \
+            assert app.stream.ops().count("attach") == 2, \
                 "a dropped frame left a silent gap instead of re-attaching"
             assert app.dropped == 3
 
```

## Decisions checked

Grepped `.project/decisions/` for `resize|pty|tui|winsize|attach|writer|protocol|
socket|op\b`. One record exists and it is active (no `superseded-by:` line):

- **DEC-011** (the daemon's cross-agent contract) -- **binding, and this plan
  complies.** It freezes the socket protocol and says adding a field is
  additive and fine, but changing an op is not. This plan adds **no** op and
  changes **no** frame shape: `resize` already exists at
  `pipeline/daemon/server.py:599`, with its dims bounded by `_dim` and its
  reply `{"rows": ..., "cols": ...}`. The client is the only thing that changes.
- DEC-011 also says the socket is same-uid and not a privilege boundary, and
  that the writer slot is "one variable and one comparison, no lease, no
  priorities". The read-only guard in this plan (`self.pty_writer`) is a client
  courtesy that keeps a viewer from stealing that slot -- it deliberately does
  **not** add a lease, a priority or a protocol field.

Nothing in the decisions directory constrains the TUI's layout, the pane widget
class, or `host.ROWS/COLS`.

## Plan

1. In `pipeline/tui/app.py`, add `class PtyPane(Static)` immediately above `class PipelineApp(App)`, with one method `on_resize(self, event) -> None: self.app._resize()` and a docstring saying `events.Resize` does not bubble so the pane is the only thing that learns its own size.
2. In `pipeline/tui/app.py`, add `#pty { height: 1fr; }` to `PipelineApp.CSS`, on the line above the `#status` rule -- without a real region the pane reports a 0-row size and `_resize` bails.
3. In `pipeline/tui/app.py`, change `compose()` to `yield PtyPane(id="pty", markup=False)` and replace all four `self.query_one("#pty", Static)` calls with `self.query_one("#pty", PtyPane)`; leave the `Static` import and the `#status` widget alone.
4. In `pipeline/tui/app.py` `__init__`, add `self.pty_writer = False` and `self.resize_id = None` after `self.pty_screen = None`, commented `resize is writer-only` and `the resize awaiting its reply`.
5. In `pipeline/tui/app.py` `_detach()`, add `self.pty_writer, self.resize_id = False, None` after the line that clears `attached` / `pty_id` / `pty_screen`, so a viewer flag never survives into the next attach.
6. In `pipeline/tui/app.py`, add `_resize()` directly above `_pty_frame()`, exactly as in the verified diff: bail if `pty_screen`/`stream` is missing or `pty_writer` is false, read `self.query_one("#pty", PtyPane).size`, bail if either dim is `< 1` or already equals the local screen, `self.resize_id = self.stream.send("resize", rows=rows, cols=cols)` inside `try/except (OSError, ValueError)` that notifies, then `self.pty_screen.resize(rows, cols)` and `self._paint_pty()`.
7. In `pipeline/tui/app.py` `_attached()`, set `self.pty_writer = bool(d.get("writer"))` before `self._paint_pty()`, call `self._resize()` after it, and change the read-only notify to test `self.pty_writer`.
8. In `pipeline/tui/app.py` `on_frame()`, insert the `resize_id` branch between the attach-reply branch and the `keys_flight` branch -- clear `self.resize_id`, notify `resize: <error>` when `ok` is false, `return` -- and confirm the `if self.keys_flight and msg.get("id") == self.keys_flight[0]:` line is still there afterwards.
9. Run `uv run --group dev pytest -q "tests/test_tui.py::test_attaching_sends_the_pane_size"` from the worktree root; it must pass, and `tests/test_tui.py::test_an_interactive_stage_attaches_and_a_dropped_frame_reattaches` must now fail on `['attach', 'resize'] == ['attach']`.
10. In `tests/test_tui.py`, relax the two over-specified assertions in `test_an_interactive_stage_attaches_and_a_dropped_frame_reattaches` to `app.stream.ops().count("attach") == 1` and `app.stream.ops().count("attach") == 2`, keeping their existing failure messages; leave the earlier `assert app.stream.ops() == ["attach"]` that runs *before* the attach reply exactly as it is, because it proves no size is sent until the reply lands.
11. In `tests/test_tui.py`, add `test_resizing_the_terminal_resizes_the_child` -- attach as in the target test, answer with `writer: True`, `await pilot.resize_terminal(300, 60)`, then assert `app.stream.ops().count("resize") == 2`, `app.pty_screen.cols == 266`, `app.pty_screen.rows == 58`, and that a second `resize_terminal(300, 60)` sends no third `resize`.
12. In `tests/test_tui.py`, add `test_a_read_only_viewer_never_sends_a_resize` -- same attach but answered with `writer: False` -- then `await pilot.resize_terminal(300, 60)` and assert `"resize" not in app.stream.ops()`, with the message that `resize` claims the writer slot on the daemon.
13. Run `uv run --group dev pytest -q tests/test_tui.py` and confirm every test in `tests/test_tui.py` passes, including the two new ones.
14. Run `uv run --group dev pytest -q tests/` and confirm 163 passed (161 in the prototype plus the two new tests in `tests/test_tui.py`); `tests/test_pty.py::test_resize_reaches_both_the_child_and_the_screen` must still be green and unmodified.
15. Run `./pipeline/hooks/test_dangerous_commands.py` unchanged, then commit `pipeline/tui/app.py` and `tests/test_tui.py` with `fix: the TUI sends its pane size so the attached child is not stuck at 40x120`.

## Acceptance criteria

- Attaching sends the pane's real size: `tests/test_tui.py::test_attaching_sends_the_pane_size` passes -- an op named `resize` is sent, its `cols` exceeds 120, and `app.pty_screen.cols` equals what was sent. Falsified by removing the `_resize()` call from `_attached()` (measured: it fails with `attached without sending a size: ['attach']`).
- A terminal resize after attach reaches the daemon and the local screen follows: `tests/test_tui.py::test_resizing_the_terminal_resizes_the_child` sees exactly two `resize` ops after `pilot.resize_terminal(300, 60)` and `app.pty_screen` at 58x266. Falsified by dropping `PtyPane.on_resize`.
- The same size is not re-sent: reattaching (a `dropped` frame followed by an `attach` reply reporting the size already imposed) in `tests/test_tui.py::test_resizing_the_terminal_resizes_the_child` adds no third `resize` op. Falsified by removing the `(rows, cols) == (self.pty_screen.rows, self.pty_screen.cols)` early return -- measured: with that guard dropped the reattach sends a third `resize` and the count-2 assertion fails (`3 == 2`). The repeated `resize_terminal(300, 60)` in the same test is not falsifying: Textual delivers no `Resize` event at all when a widget's size does not change, so `_resize()` is never called on that path regardless of the guard.
- A read-only viewer never claims the writer slot: `tests/test_tui.py::test_a_read_only_viewer_never_sends_a_resize` sees no `resize` op. Falsified by dropping the `not self.pty_writer` guard in `_resize()`.
- The reattach path still works and keystrokes still flow: `tests/test_tui.py::test_an_interactive_stage_attaches_and_a_dropped_frame_reattaches` and `tests/test_tui.py::test_keystrokes_are_chunked_and_a_short_write_is_resent` both pass.
- The daemon half is untouched and still correct: `tests/test_pty.py::test_resize_reaches_both_the_child_and_the_screen` passes with no diff to `pipeline/pty/host.py` or `pipeline/daemon/server.py`.
- Nothing else regressed: `uv run --group dev pytest -q tests/` reports 163 passed.

## Decisions

**`resize` is writer-only, and the TUI gates on the attach reply's `writer`
flag.** `_op_resize` claims the writer slot exactly as `_op_input` does, so a
second client watching a stage read-only would silently steal the keyboard from
whoever is answering the prompt merely by having a differently sized window.
`self.pty_writer` exists for that and nothing else. Do not "simplify" it away,
and do not send `resize` before the attach reply has said who the writer is.

**The local `pyte` screen is resized optimistically, at send time, not on the
ack.** Keystrokes wait for their ack (`_keys_acked`) because a short write loses
bytes; a resize cannot short-write, and waiting would leave the pane rendering
at the old width for a round trip -- which is the exact garbage this ticket is
about. `tests/test_tui.py::test_attaching_sends_the_pane_size` encodes the
choice: it delivers only the attach reply and then requires the local screen to
already match what was sent.

**`_attached()` must call `_resize()` itself; `on_resize` alone is not enough.**
Textual lays the pane out once at mount and does *not* re-deliver `Resize` when
`display` flips `False -> True`, so by the time a screen exists no further
`Resize` is coming. Measured, not assumed: with the direct call commented out,
`test_attaching_sends_the_pane_size` fails with `['attach']`.

**`events.Resize` does not bubble.** That is the whole reason `PtyPane` exists
as a class rather than the pane staying a bare `Static`. Putting `on_resize` on
`PipelineApp` compiles, runs, and never fires for the pane.

**`#pty { height: 1fr; }` is load-bearing.** A `Static` with auto height reports
the size of its content, so the pane would ask the child to be as tall as
whatever it has already printed. The rule gives the pane the region the child is
then told to fill.

## Rollback

`git revert` the single commit, or `git checkout main -- pipeline/tui/app.py
tests/test_tui.py`. Nothing outside those two files changes: no protocol op, no
daemon code, no on-disk format, no dependency. Reverting puts every attached
stage back at the daemon's forked 40x120 -- the symptom, not a broken state --
and re-breaks only `tests/test_tui.py::test_attaching_sends_the_pane_size`,
which was red before this ticket anyway.

If only the *terminal-resize* half misbehaves (a Textual version that delivers
`Resize` storms, say), the narrow rollback is to delete `PtyPane.on_resize`'s
body and keep the `_attached()` call: attach-time sizing survives, and only
mid-session resizes stop tracking.

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

### 2026-08-21 · planning · plan written

Prototyped the whole change in a scratch copy of this worktree before writing
the plan (`cp -r` to `/tmp/p019`, patch, `pytest`), so nothing below is a guess.

- Target test passes with the change: `1 passed`.
- Full suite in the prototype: **161 passed** (the two new tests in step 11 and
  step 12 are not in it, so the implementer should land on 163).
- Measured, not assumed: `on_resize` alone does **not** fire when the pane's
  `display` flips to `True`; with `_attached()`'s direct `_resize()` call
  commented out the target test fails with `attached without sending a size:
  ['attach']`. That is why the plan has both call sites.
- Measured: `pilot.resize_terminal(300, 60)` produces a second `resize`
  (58x266), the local `pyte` screen follows, and a repeat of the same size
  sends nothing.
- Measured: an attach answered with `writer: False` sends no `resize` at all.
- Cost of one mistake worth flagging: replacing the `keys_flight` line in
  `on_frame` instead of inserting above it silently broke
  `test_keystrokes_are_chunked_and_a_short_write_is_resent`. Step 8 says so.

Outside this stage's scope, noted rather than fixed:

- `pipeline/pty/host.py:28` still forks every child at 40x120. That is correct
  as a default (the daemon has no client at fork time) but it means the first
  frames a stage draws are 120 columns wide until a TUI attaches. Nothing in
  this ticket changes that, and a headless-but-interactive stage nobody attaches
  to stays at 40x120 forever.
- No client other than the TUI ever sends `resize`; `pipeline attach`-style CLI
  access, if it is ever added, will need the same two call sites.

### 2026-08-21 05:09:21Z · planning · session · session=aea276a5-36be-4800-a9bd-3f7a8276f1f4

`planning` ran as session `aea276a5-36be-4800-a9bd-3f7a8276f1f4`
- replay: `claude --resume aea276a5-36be-4800-a9bd-3f7a8276f1f4`
- log: `.project/logs/TICKET-019-planning-aea276a5.log`

### 2026-08-21 05:09:21Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

plan written and prototyped green in a scratch copy (161 passed); client-side only, PtyPane + _resize in pipeline/tui/app.py

### 2026-08-21 05:09:28Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_attaching_sends_the_pane_size` fails as required
```
       await pilot.press("down", "down")
            await pilot.pause()
            app.on_frame({"id": app.pty_id, "ok": True,
                          "data": {"screen": ["Allow Bash?"], "rows": 40,
                                   "cols": 120, "writer": True}})
            await pilot.pause()
    
>           assert "resize" in app.stream.ops(), \
                f"attached without sending a size: {app.stream.ops()}"
E           AssertionError: attached without sending a size: ['attach']
E           assert 'resize' in ['attach']
E            +  where ['attach'] = ops()
E            +    where ops = <test_tui.FakeStream object at 0x7fe92648a3c0>.ops
E            +      where <test_tui.FakeStream object at 0x7fe92648a3c0> = PipelineApp(title='PipelineApp', classes={'-dark-mode'}, pseudo_classes={'focus', 'dark'}).stream

tests/test_tui.py:394: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_attaching_sends_the_pane_size - AssertionError...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.49s ===============================

```

### 2026-08-21 · plan-validation · PASS

Read-only. Re-checked every claim the plan makes about this tree rather than
trusting the prototype's word for it. Item by item:

**Root cause vs symptom -- pass.** In my words: the child's window size is set
once, in the child before `exec` (`pipeline/pty/host.py:28`, `ROWS, COLS = 40,
120`), and the only thing that can ever change it is a client sending `resize`.
The daemon side of that op is finished -- `daemon/server.py:599` bounds the dims
with `_dim`, claims the writer, calls `host.set_winsize()` on the master (which
is what makes the kernel raise SIGWINCH at the child) and resizes its own pyte
screen -- and no client has ever called it (`grep -c resize
pipeline/tui/app.py` == 0). So the bug is a missing caller, and the fix adds the
caller. It is not a fix aimed at the assertion: `_resize()` sends the pane's
actual `size.width/height`, so the test's `cols > 120` passes because the pane
really is wider, not because a constant was chosen to beat the comparison.

**Decision conflict -- pass.** `.project/decisions/` contains exactly one
record, DEC-011, with no `superseded-by:`. It freezes the socket protocol and
the event vocabulary; a client-side change touches neither. The plan adds no op
and no frame field. Note for the record: DEC-011's prose still says "**Five
ops:** `ping`, `ls`, `projects`, `subscribe`, `kill`" while `attach`, `input`,
`resize` and `detach` all exist in `server.py` (TICKET-013, which DEC-011
anticipates elsewhere in the same document). The doc is stale, the code is the
ground truth, and this ticket must not fix it -- flagged only so a later reader
does not mistake it for a violation.

**Scope discipline -- pass.** 15 steps, 2 files, and every one traces to a
criterion: 1-8 are the change, 9 and 13-14 are the verification the criteria
name, 10-12 are the tests three criteria cite by name, 15 is the guard script
this repo requires plus the commit. Nothing touches the daemon, `host.py`, the
protocol or the harness files.

**Falsifiable criteria -- pass.** Each of the four behavioural criteria names
the test *and* the mutation that reddens it (drop the `_resize()` call in
`_attached`; drop `PtyPane.on_resize`; drop the equal-dims early return; drop
the `not self.pty_writer` guard). Those are four different lines of the diff, so
the four tests are not one test wearing hats. The first mutation is not a guess
-- planning measured it and the failure text matches the one the gate captured.

**No research left -- pass.** Every step names the file, the function and the
insertion point, and the verified diff is in `## Digest`. I re-checked the
anchors against this worktree: `app.py:100-104` CSS block (no `#pty` rule yet),
`compose()` at 141 with `yield Static(id="pty", markup=False)` at 150, the four
`query_one("#pty", Static)` sites at 155 / 308 / 337 / 369, `__init__` fields at
128-132, `_detach` at 347, `_attached` at 350-366, `on_frame`'s attach branch at
257 and its `keys_flight` branch at 259, `Screen.rows/.cols/.resize` at
`host.py:107/111/124`. Every hunk's context matches, so the diff applies to this
tree as-is.

**Riskiest step -- pass, with a stated fallback.** Step 1 (`PtyPane.on_resize`)
is the riskiest: it is the one behaviour that depends on Textual's event
delivery rather than on this repo's code, and it fires on a path
(`_paint_pty()` -> `pane.update()`) that could in principle re-enter. `##
Rollback` names exactly this and gives the narrow fallback -- empty
`PtyPane.on_resize`'s body, keep `_attached()`'s direct call, and attach-time
sizing survives while only mid-session tracking stops. Re-entry is bounded by
the same equal-dims early return that step 11's third assertion pins, so a paint
that does not change the pane's size sends nothing.

**Regression surface -- pass.** Four behaviours could plausibly break and all
four are covered: the keystroke pipeline, if the new `on_frame` branch replaces
instead of precedes the `keys_flight` line
(`test_keystrokes_are_chunked_and_a_short_write_is_resent`, and step 8 calls out
the mistake by name); the reattach-after-`dropped` path, whose two assertions
step 10 relaxes from `ops() == [...]` to attach *counts*
(`test_an_interactive_stage_attaches_and_a_dropped_frame_reattaches`); the pane
dying on raw output, since the pane changes class
(`test_a_bracketed_path_on_the_attached_screen_does_not_crash_the_pane`); and
the detach-on-`stage_end` ordering, which asserts `ops()[-1] == "detach"` and
survives because that test never delivers an attach reply, so `pty_writer` stays
`False` and no `resize` is sent
(`test_the_pane_stops_claiming_to_be_live_when_the_stage_ends`). Step 10's
instruction to leave `tests/test_tui.py:232` alone is right and load-bearing:
that assertion runs *before* the attach reply and is what proves no size goes
out until the daemon has said who the writer is. The daemon half is asserted
unchanged by the last criterion.

**Blast radius matches class -- pass.** `bugfix`, two files, both in
`files_declared`, roughly 40 added lines and no new dependency, no on-disk
format, no protocol surface.

Two notes, neither blocking and neither in scope for the implementer to fix:

- `pty_writer` is set once, from the attach reply, and never re-read. A viewer
  that attaches read-only and later *becomes* the writer (the slot frees when
  its holder disconnects, and the next `input` claims it -- `server.py:519`)
  will type fine but never send a `resize` until it re-attaches. Strictly better
  than today, and outside every acceptance criterion.
- Step 11's `58` and `266` are geometry constants measured against the current
  layout (`#tree { width: 34; }` plus one status row and the footer). They are
  correct and they were measured, but any future change to the tree width or the
  status bar will redden that test for a reason unrelated to resizing. Fine to
  land as written.

### 2026-08-21 05:12:31Z · plan-validation · session · session=f2069b90-36b4-4aa9-9836-453c875afd38

`plan-validation` ran as session `f2069b90-36b4-4aa9-9836-453c875afd38`
- replay: `claude --resume f2069b90-36b4-4aa9-9836-453c875afd38`
- log: `.project/logs/TICKET-019-plan-validation-f2069b90.log`

### 2026-08-21 05:12:31Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

plan validated on all eight items; root cause is the missing client caller for the existing _op_resize, anchors re-checked against the tree, DEC-011 not violated

### 2026-08-21 05:15:33Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 05:17:02Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_attaching_sends_the_pane_size` fails as required
```
       await pilot.press("down", "down")
            await pilot.pause()
            app.on_frame({"id": app.pty_id, "ok": True,
                          "data": {"screen": ["Allow Bash?"], "rows": 40,
                                   "cols": 120, "writer": True}})
            await pilot.pause()
    
>           assert "resize" in app.stream.ops(), \
                f"attached without sending a size: {app.stream.ops()}"
E           AssertionError: attached without sending a size: ['attach']
E           assert 'resize' in ['attach']
E            +  where ['attach'] = ops()
E            +    where ops = <test_tui.FakeStream object at 0x7ff50e6923c0>.ops
E            +      where <test_tui.FakeStream object at 0x7ff50e6923c0> = PipelineApp(title='PipelineApp', classes={'-dark-mode'}, pseudo_classes={'dark', 'focus'}).stream

tests/test_tui.py:394: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_attaching_sends_the_pane_size - AssertionError...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================

```

### 2026-08-21 05:17:02Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 · implementing · todo

1. [x] `PtyPane(Static)` + `on_resize` above `PipelineApp`
2. [x] `#pty { height: 1fr; }` in `CSS`
3. [x] `compose()` yields `PtyPane`; four `query_one("#pty", Static)` -> `PtyPane`
4. [x] `__init__`: `pty_writer`, `resize_id`
5. [x] `_detach()` clears `pty_writer`/`resize_id`
6. [x] `_resize()` above `_pty_frame()`
7. [x] `_attached()` sets `pty_writer`, calls `_resize()`, gates the notify on it
8. [x] `on_frame()` `resize_id` branch between attach-reply and `keys_flight`
9. [x] target test passes; dropped-reattach test now fails on attach count
10. [x] relax the two `ops()` assertions to attach counts
11. [x] add `test_resizing_the_terminal_resizes_the_child`
12. [x] add `test_a_read_only_viewer_never_sends_a_resize`
13. [x] `tests/test_tui.py` green (14 passed)
14. [x] `tests/` green
15. [x] guard script, then commit

### 2026-08-21 · implementing · done

Applied the verified diff from `## Digest` verbatim -- no deviation, no
research needed. Every anchor the plan named matched this tree exactly.

One number needed correcting, not the plan's design: `## Acceptance criteria`
and the planning note in `## Thread` predicted **163** for the full suite.
Measured: baseline before this stage was **162** (161 passing + the triage
commit's failing `test_attaching_sends_the_pane_size`, confirmed by stashing
this stage's diff and re-running -- `git stash push -u`, count, `git stash
apply <sha>` by sha, `git stash drop`, never bare `stash pop`, per this
worktree's shared-stash rule). Plus the two new tests from steps 11-12, the
correct total is **164**, which is what `uv run --group dev pytest -q tests/`
reports now. The planning-stage prototype's "161" evidently did not carry the
already-committed triage test forward into its count. Nothing in the diagnosis
or the fix is affected -- this is a stale arithmetic prediction, not a
contradiction of the plan.

Verified:
- `tests/test_tui.py::test_attaching_sends_the_pane_size` -- 1 passed
- `tests/test_tui.py` -- 14 passed (12 pre-existing + 2 new)
- `tests/` -- 164 passed, 0 failed
- `./pipeline/hooks/test_dangerous_commands.py` -- all 79 cases pass, script
  untouched
- `tests/test_pty.py::test_resize_reaches_both_the_child_and_the_screen` is in
  the 164 and green; `pipeline/pty/host.py` and `pipeline/daemon/server.py`
  have no diff (`git status --short` after commit shows only the two declared
  files)

Committed as `d9c0c26`
`fix: the TUI sends its pane size so the attached child is not stuck at
40x120`, `pipeline/tui/app.py` and `tests/test_tui.py` only, 99 insertions(+),
8 deletions(-).

### 2026-08-21 05:20:10Z · implementing · session · session=342ae9ee-4cce-4a37-9c2d-72d215dc5fb3

`implementing` ran as session `342ae9ee-4cce-4a37-9c2d-72d215dc5fb3`
- replay: `claude --resume 342ae9ee-4cce-4a37-9c2d-72d215dc5fb3`
- log: `.project/logs/TICKET-019-implementing-342ae9ee.log`

### 2026-08-21 05:20:10Z · implementing · transition · to=review · result=ok

**implementing -> review** (result: `ok`)

applied the verified diff verbatim (PtyPane + _resize), added the two new tests, target test and full suite (164 passed) and guard script green, committed d9c0c26

### 2026-08-21 · review · FAIL (1 blocking)

Reviewed the delta `main...HEAD` -- two commits (`1736f66` triage test,
`d9c0c26` fix), two files, both in `files_declared`. `git status --short` is
empty and `git diff --stat main...HEAD -- pipeline/pty/host.py
pipeline/daemon/server.py pipeline/hooks/` is empty, so the daemon half and the
guard are untouched as the last acceptance criterion requires.

Re-run here, not taken from the thread: `uv run --group dev pytest -q tests/`
-- **164 passed in 7.14s**. The implementer's arithmetic is right and the
plan's `163` was the stale number; nothing to fix there.

Diff read line by line against `## Digest`: applied verbatim, every hunk
matches, and `tests/test_tui.py:232` (`assert app.stream.ops() == ["attach"]`,
*before* the attach reply) is untouched exactly as step 10 required.

One thing I could **not** run: `./pipeline/hooks/test_dangerous_commands.py` is
not on the read-only stage's allowlist, so the guard blocked it. It is outside
this delta (`pipeline/hooks/` has no diff) and `implementing` ran it green --
recorded so the gap is not mistaken for a check that passed.

1. **BLOCKING** -- the third acceptance criterion is not met: its assertion is
   vacuous. The criterion says the same-size case is "Falsified by removing the
   `(rows, cols) == (self.pty_screen.rows, self.pty_screen.cols)` early
   return". It is not. Textual delivers **no** `Resize` when the size does not
   change, so after the second `pilot.resize_terminal(300, 60)` nothing calls
   `_resize()` and the assertion holds with or without the guard. Both halves
   measured in-process against this worktree (no files touched):

       # instrumented PtyPane.on_resize, real code
       after attach: [(48, 166)]
       after 300x60: [(48, 166), (58, 266)]
       after SAME:   []                       # no event, so no call to _resize

       # _resize monkeypatched to drop ONLY the equal-dims early return
       MUTANT after 300x60, resize count: 2
       MUTANT after SAME,   resize count: 2   assertion count==2 still passes: True

   The early return is not dead code -- it is load-bearing on the *reattach*
   path, which `## Digest` already names ("If the daemon reports the size we
   already asked for, `_resize` sends nothing") and which nothing asserts.
   That path *is* falsifiable, measured both ways:

       real code: after first attach ['attach', 'resize']
                  after reattach at the size we imposed ['attach', 'resize', 'attach']
       mutant:    ['attach', 'resize', 'attach', 'resize']   (resize count 2)

   Smallest fix, and the only change this finding asks for -- in
   `tests/test_tui.py::test_resizing_the_terminal_resizes_the_child`, after the
   58x266 assertions, replace the repeat-`resize_terminal` block (or keep it
   and add to it) with the reattach exercise:

       app.on_frame({"sub": app.pty_id, "dropped": 3})
       await pilot.pause()
       app.on_frame({"id": app.pty_id, "ok": True,
                     "data": {"screen": ["Allow Bash?"], "rows": 58,
                              "cols": 266, "writer": True}})
       await pilot.pause()
       assert app.stream.ops().count("resize") == 2, \
           "re-attaching re-sent a size the daemon already has"

   and correct the criterion's falsification clause to name the reattach input
   instead of the repeated terminal resize. **Do not touch `_resize()` itself**
   -- the code is right; only the evidence for it is missing.

2. **minor** -- a failed `resize` leaves the client desynced in exactly the
   direction this ticket is about. `_resize()` resizes the local pyte screen
   optimistically (a deliberate decision, see `## Decisions`) but the daemon
   can still reject: `_op_resize` raises "another client holds the writer" when
   the slot was stolen since the attach reply, and `_dim` rejects anything over
   `MAX_DIM`. The `resize_id` branch in `on_frame` notifies and stops there, so
   the pane keeps rendering at a width the child never got. Today the only
   consequence is a toast plus a wrong-width pane until the next attach --
   strictly better than the 40x120 this ticket fixes, and `pty_writer` going
   stale is already noted by `plan-validation`. A later ticket could resize the
   local screen from the reply's `{"rows", "cols"}` on failure.

3. **minor** -- two `resize` ops in flight lose the first reply. `_resize()`
   overwrites `self.resize_id`, so an earlier reply matches no branch in
   `on_frame`, falls through to `msg.get("event")`, is not a dict, and returns.
   Harmless (a resize carries no state the client needs back), but an error on
   the superseded resize is silently swallowed. Not worth a mechanism.

4. **minor** -- `PtyPane.on_resize` calls `self.app._resize()` unguarded, so
   the widget is only usable inside `PipelineApp`. Fine as written; noted only
   because the class is now importable on its own.

None of 2-4 block. Only finding 1 does, and it is confined to
`tests/test_tui.py` plus the one criterion's wording.

### 2026-08-21 05:25:25Z · review · session · session=b2426072-a14e-4936-847f-00ab3121e4ed

`review` ran as session `b2426072-a14e-4936-847f-00ab3121e4ed`
- replay: `claude --resume b2426072-a14e-4936-847f-00ab3121e4ed`
- log: `.project/logs/TICKET-019-review-b2426072.log`

### 2026-08-21 05:25:25Z · review · transition · to=implementing · result=fail

**review -> implementing** (result: `fail`)

code is correct and 164 tests pass, but the same-size acceptance criterion is vacuous - the stated mutation (dropping the equal-dims early return) does not redden the test; measured fix and falsifying input in the thread

### 2026-08-21 · implementing (retry) · todo

1. [x] add the reattach exercise to `test_resizing_the_terminal_resizes_the_child` per review's exact snippet
2. [x] verify RED: mutant with the equal-dims early return dropped fails the new assertion (`3 == 2`)
3. [x] verify GREEN: real code passes the new assertion
4. [x] `tests/test_tui.py` and `tests/` still green (164 passed)
5. [x] guard script still green (79 cases)
6. [x] correct the acceptance criterion's falsification clause to name the reattach input
7. [x] commit

### 2026-08-21 · implementing (retry) · done

Applied review's finding exactly, no deviation. Built the mutant by removing
only the `(rows, cols) == (self.pty_screen.rows, self.pty_screen.cols)` early
return (a copy of `pipeline/tui/app.py` swapped in and back out, no working
tree diff), ran just the new test against it: failed with
`assert 3 == 2 -- re-attaching re-sent a size the daemon already has`, ops
`['attach', 'resize', 'resize', 'attach', 'resize']`. Swapped the real file
back, same test passes. `_resize()` was never touched, matching the review's
explicit instruction.

Verified:
- `tests/test_tui.py::test_resizing_the_terminal_resizes_the_child` -- 1 passed (real code)
- `tests/` -- 164 passed, 0 failed (same total; no new test added, existing one extended)
- `./pipeline/hooks/test_dangerous_commands.py` -- all 79 cases pass, script untouched
- `git diff --stat` before commit: `tests/test_tui.py | 9 +++++++++`, nothing else

Committed as `bcd57a9`
`fix: TICKET-019 the resize idempotency test now exercises the reattach path`,
`tests/test_tui.py` only. Also edited `## Acceptance criteria` in this ticket
(not frontmatter) to name the reattach input as the falsifying case, per
review's instruction -- that edit lives in `.project/`, outside the worktree's
tracked diff, so it has no separate commit.

### 2026-08-21 05:27:01Z · implementing · session · session=256d2d01-96f4-49d8-be03-978d38d71f93

`implementing` ran as session `256d2d01-96f4-49d8-be03-978d38d71f93`
- replay: `claude --resume 256d2d01-96f4-49d8-be03-978d38d71f93`
- log: `.project/logs/TICKET-019-implementing-256d2d01.log`

### 2026-08-21 05:27:01Z · implementing · transition · to=review · result=ok

**implementing -> review** (result: `ok`)

fixed review's one blocking finding (vacuous same-size assertion) by adding the reattach exercise to test_resizing_the_terminal_resizes_the_child, verified RED against the equal-dims-guard mutant then GREEN; 164 passed, guard script's 79 cases pass, committed bcd57a9

### 2026-08-21 · review (loop 2) · PASS

Delta reviewed: `git diff d9c0c26..HEAD`, i.e. commit `bcd57a9` alone. Nine
added lines in `tests/test_tui.py::test_resizing_the_terminal_resizes_the_child`
and nothing else -- `git status --short` is empty and no source file moved.
`_resize()` was not touched, as the previous loop required.

**Previous loop's blocking finding: resolved, and I re-measured it rather than
taking the thread's word.** In-process, no file in the tree touched
(`PipelineApp._resize` replaced at runtime with a copy that drops *only* the
`(rows, cols) == (self.pty_screen.rows, self.pty_screen.cols)` early return,
everything else identical):

    AssertionError: re-attaching re-sent a size the daemon already has
    tests/test_tui.py:437, in test_resizing_the_terminal_resizes_the_child

Line 437 is the new reattach assertion, not the older repeat-`resize_terminal`
one at 428 -- so the guard's falsifying input is now genuinely exercised and it
is the new block that carries it. Against the real code the same test passes.
Full suite re-run here: **164 passed in 7.41s**.

Path traced in the code, not inferred: `{"sub": ..., "dropped": 3}` carries no
`id`, so it misses the `pty_id` branch and lands in `on_frame`'s `dropped`
branch (`app.py:278`), which clears `attached` and re-runs `_pty()` -> a fresh
`attach` and a fresh `pty_id`. The test's reply matches that new id, so
`_attached()` (`app.py:368`) builds `Screen(58, 266)`, sets `pty_writer`, and
calls `_resize()`, whose pane is already 58x266. The mutant proves `_resize()`
really is reached there; the guard is the only thing that stops the send.

1. **minor** -- the older assertion the finding was about is still in the test.
   Lines 426-429 (`await pilot.resize_terminal(300, 60)` a second time, then
   `count("resize") == 2` with the message "the same size was re-sent") remain
   vacuous for the reason the last loop measured: Textual delivers no `Resize`
   when the size is unchanged, so `_resize()` is never called on that path and
   the assertion holds with or without the guard. The implementer kept it and
   added the reattach block beside it, which the finding explicitly permitted
   ("or keep it and add to it"), and the criterion's wording now names the
   reattach input. Harmless -- a passing assertion that proves nothing costs
   nothing here -- but it is dead weight a future reader may mistake for
   coverage. Not blocking.

2. **minor, carried forward** -- a rejected `resize` leaves the client
   desynced: `_resize()` resizes the local pyte screen optimistically (a
   deliberate decision) while `_op_resize` can still reject on the writer slot
   or `_dim`, and the `resize_id` branch only notifies. Unchanged by this
   delta. A later ticket could adopt the reply's `{"rows", "cols"}` on failure.

3. **minor, carried forward** -- two `resize` ops in flight: `_resize()`
   overwrites `self.resize_id`, so the superseded reply matches no branch and
   its error is swallowed. Harmless; not worth a mechanism.

4. **minor, carried forward** -- `PtyPane.on_resize` calls `self.app._resize()`
   unguarded, so the widget only works inside `PipelineApp`.

`plan-validation`'s two notes also still stand and are still out of scope: a
viewer that later *becomes* the writer sends no `resize` until it re-attaches,
and the `58`/`266` constants are geometry measured against the current layout,
so a future change to `#tree { width: 34; }` or the status row will redden that
test for an unrelated reason.

Same gap as last loop, recorded so it is not mistaken for a check that passed:
`./pipeline/hooks/test_dangerous_commands.py` is not on the read-only stage's
allowlist and the guard blocked it. `pipeline/hooks/` has no diff in this delta
or in `main...HEAD`, and `implementing` reports it green at 79 cases.

### 2026-08-21 05:30:28Z · review · session · session=32041b3f-f0e6-41e9-929d-a3fef13d5040

`review` ran as session `32041b3f-f0e6-41e9-929d-a3fef13d5040`
- replay: `claude --resume 32041b3f-f0e6-41e9-929d-a3fef13d5040`
- log: `.project/logs/TICKET-019-review-32041b3f.log`

### 2026-08-21 05:30:28Z · review · transition · to=verifying · result=ok

**review -> verifying** (result: `ok`)

delta bcd57a9 reviewed - the reattach assertion kills the equal-dims-guard mutant (re-measured in-process, fails at tests/test_tui.py:437), 164 passed, four non-blocking notes in the thread

### 2026-08-21 05:30:36Z · verifying · transition · to=merging · result=ok

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

### 2026-08-21 05:30:37Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/019


Merge made by the 'ort' strategy.
 pipeline/cli/main.py             |  3 +-
 pipeline/core/__init__.py        | 16 +++++++++
 pipeline/core/gate.py            | 45 +++++++++++++++++++++++++-
 pipeline/core/ticket.py          | 47 +++++++++++++++++++++++----
 pipeline/core/worktree.py        | 37 ++++++++++++++++++++-
 pipeline/daemon/main.py          |  3 +-
 pipeline/templates/pipeline.toml |  1 +
 tests/test_daemon.py             | 70 ++++++++++++++++++++++++++++++++++++++++
 tests/test_gate.py               | 53 ++++++++++++++++++++++++++++++
 tests/test_ticket.py             | 68 ++++++++++++++++++++++++++++++++++++++
 10 files changed, 333 insertions(+), 10 deletions(-)
Updating f7377cf..4ed4307
Fast-forward
 pipeline/tui/app.py | 49 +++++++++++++++++++++++----
 tests/test_tui.py   | 97 +++++++++++++++++++++++++++++++++++++++++++++++++++--
 2 files changed, 138 insertions(+), 8 deletions(-)

```

### 2026-08-21 05:30:37Z · merging · decision

decision recorded as `DEC-019`
