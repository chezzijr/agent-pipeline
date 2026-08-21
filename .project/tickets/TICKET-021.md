---
id: TICKET-021
stage: escalated
class: feature
branch: ticket/021
test_file: tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc
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
  stage: planning
  id: cecf2d3b-4963-4c25-8ab4-aebb16a45b87
  log: .project/logs/TICKET-021-planning-cecf2d3b.log
approved_by: chezzijr
approved_at: '2026-08-21T05:56:07.038391+00:00'
---

## Summary

**Replanned 2026-08-21 (third planning pass), against the reset branch.** No
human `rejection` in the thread -- the ticket came back through a resume after
the aborted revalidate rebase and a triage re-run. The design, the key table and
every step's code are unchanged from the plan the gate and plan-validation both
passed; what changed is that all of it was re-measured on `364ac41`, the tree
this branch actually is.

**One correction to the re-triage note, and it matters because it is an
acceptance criterion.** That note says "criterion 6's post-fix expectation is
`15 passed`". It is **16**. 15 is the count *before* the change (`1 failed,
14 passed`, measured); step 13 adds one test, so a correct implementation
reports 16. Prototyped end to end on this tree and measured `16 passed in
4.08s`, plus `176 passed` for the whole suite.

**Bug:** `i` in `pipeline tui` suspends the whole app and blocks on `input()`
(`action_send` -> `_ask`, `pipeline/tui/app.py:459`), so answering one prompt on
an attached stage takes the tree, the PTY pane and the prompt itself off screen,
and arrows/Tab/ctrl-C never reach the child at all. Reproduced on this branch as
`364ac41`: only `b"\r"` ever reaches the pty.

**Fix (client-side only):** a raw mode. `i` sets `self.raw`; an override of
`App.on_event` catches every key *before* Textual's bindings and before the
focused `Tree`, maps it to the bytes a terminal would send (`RAW_KEYS` +
`key_bytes`, needed because Textual hands over a key *name*), and feeds the
existing `_send_keys`. `Esc Esc` exits, a lone Esc is held back, and the mode
shows in the `#status` line and is cleared by `_detach`. No protocol change:
`input` already carries arbitrary base64.

**Files:** `pipeline/tui/app.py`, `tests/test_tui.py`.

**Two things the implementer must not skip.** (a) Step 2: the committed
reproduction test cannot pass as written even with raw mode working --
`_flush_keys` keeps one `input` op in flight and `FakeStream` never acks, so
`tab` never leaves. Step 2 adds the ack to the fake; the assertions stay
untouched and the test still fails on base with the original `b'\r'` symptom
(re-measured on this tree, step 3). (b) The `on_event` guard stays
`isinstance(event, events.Key)` -- broaden it and a swallowed `Resize` breaks
DEC-019's pane sizing.

## Reproduction

Test: `tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc`

Command:

    uv run --group dev pytest -q "tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc"

Output:

    >           assert sent == b"\x1b[B\t", f"raw mode never reached the pty: {sent!r}"
    E           AssertionError: raw mode never reached the pty: b'\r'
    E           assert b'\r' == b'\x1b[B\t'
    tests/test_tui.py:482: AssertionError
    1 failed in 0.90s

expect: raw mode never reached the pty: b'\r'

Re-triaged 2026-08-21 after the human resume. The branch had been reset to
`4ed4307` by the aborted revalidate rebase, so neither the merge `e8b505c` nor
the triage commit `f22598f` was on `ticket/021` any more. The test is back on
the branch as `364ac41`, a cherry-pick of `f22598f` -- same conflict the rebase
hit (both sides append tests to the end of `tests/test_tui.py`), resolved by
keeping both. `main` is an ancestor of `HEAD`. Whole-file run is
`1 failed, 14 passed`, so the post-fix count is **15**, not the 16 the Digest
quotes off the old merge tree.

The test drives the app with Textual's own pilot, sets `attached`/`stream`/
`pty_screen` the way `test_keystrokes_are_chunked_and_a_short_write_is_resent`
does, presses `i`, then `down` and `tab`, and asserts those two keys arrive at
the pty as `\x1b[B\t`. The second half presses `escape escape` and asserts no
further bytes are sent -- that half is what will keep raw mode escapable.

## Digest

**One file changes, plus its test.** `pipeline/tui/app.py` (**606** lines on
this tree) and `tests/test_tui.py` (15 tests). Nothing in `pipeline/daemon/`
moves: `_op_input` (`pipeline/daemon/server.py`) already base64-decodes
arbitrary bytes, caps them at `PTY_INPUT` (4096) and `os.write`s them verbatim
to the master fd.

**Tree state, measured not quoted.** `HEAD` is `364ac41` (the cherry-picked
repro on top of `4ed4307`). `git merge-base --is-ancestor main HEAD` passes --
main IS an ancestor. `git status --porcelain` is empty, so nothing is
pre-applied. `grep -c "^def test_" tests/test_tui.py` -> **15**.
`uv run --group dev pytest -q tests/test_tui.py` -> `1 failed, 14 passed`.

**All nine line anchors are exact on this tree** -- the cherry-pick reproduced
the merge tree's content, so the numbers the previous pass measured on `e8b505c`
still hold: `from textual import work` 28, `def marker` 53,
`("i", "send", "type")` 125, `self.keys_flight = None` 144, `self._status(rows)`
216, `def _status` 230, `def _detach` 357, `self.keys_out, self.keys_flight` 366,
`def action_send` 459. Verified by grep, one hit each. Every anchor *string*
quoted in a step is unique in its file, so a grep still beats a line number if
they ever disagree.

**The path a keystroke takes today.** `BINDINGS` (`pipeline/tui/app.py:117-126`)
binds `i` -> `action_send` (`:459`) -> `_ask` (`:513`) -> `self.suspend()` +
`input()`. The bytes side is already right and is reused unchanged:
`_send_keys` (`:421`) appends to `self.keys_out`, `_flush_keys` (`:425`) sends
at most `PTY_INPUT` per `input` op on the SUBSCRIPTION connection, and
`_keys_acked` (`:444`) resends the tail of a short write. Raw mode only has to
call `_send_keys` with the right bytes.

**Where a key can be intercepted -- this is the whole design.** Textual 8.2.8
dispatches a key in `App.on_event` (`textual/app.py:4060`): *priority* bindings
first (`_check_bindings(..., priority=True)`, `:4136`), then
`(self.focused or self.screen)._forward_event(event)` (`:4138`), and only if the
focused widget lets it bubble does `App._on_key` (`:4341`) check the app's own
bindings. The `Tree` consumes `down`/`up` with its own bindings, so an `on_key`
handler on the App never sees them. Overriding `async def on_event` and
returning early is the only seam that gets *every* key, ctrl+c included
(`Binding("ctrl+c", "help_quit", system=True)` lives in the priority pass, which
runs after our override).

**Textual gives a key *name*, not bytes.** `events.Key.character` is `None` for
`down` and for `ctrl+c` under the pilot, and it is *wrong* for `backspace`
(Textual says `\x08`; a real terminal sends `\x7f`). So raw mode needs an
explicit name -> bytes table, and `character` is only the fallback for printable
keys. Ctrl combos are derived from the name (`ctrl+c` -> `0x43 ^ 0x40 = \x03`),
not from `character`, because the pilot does not set it.

**Gotcha that costs a debugging session: one `input` op is in flight at a
time.** `_flush_keys` returns early while `self.keys_flight` is set
(`pipeline/tui/app.py:434`); the ack (`_keys_acked`) or the next pty frame
(`_pty_frame`, `:418`) is what releases the next chunk. Against the real daemon
that is a sub-millisecond round trip and keystrokes coalesce losslessly in
`keys_out`. Against `FakeStream` (`tests/test_tui.py:190`) -- which records and
never replies -- the second keystroke never leaves. **The committed reproduction
test presses `down` and `tab` back to back with no ack in between, so it cannot
pass as written even with raw mode fully working** (`sent == b"\x1b[B"`, tab
still in `keys_out`). Step 2 fixes the test's fake, not its assertions.

**The status line, not the `Footer` widget.** `compose` (`:153`) yields a
one-line `Static(id="status")` (`:163`) directly above `Footer()`; `_status`
(`:230`) rewrites it, and the 5s `refresh_tree` re-runs it through `_paint`
(`:206`) -- so the raw indicator has to live *inside* `_status` or it is erased
within five seconds. `Footer` itself renders `BINDINGS`; making it show a mode
would mean dynamic bindings, which is machinery this does not need.

**`_detach` is the one place that ends an attachment.** Three call sites
(`:300` stage_end, `:324` selecting a non-interactive row, `:345`) all funnel
through it, so clearing raw mode there covers all three. It already resets
`pty_writer`, `resize_id`, `keys_out` and `keys_flight` (`:365-366`). All three
run inside a mounted UI, so the added `self._status()` cannot hit `NoMatches`.

**`PtyPane` (`:99-105`) exists because `events.Resize` does not bubble** -- its
`on_resize` is the only thing that learns the pane's real size (DEC-019). The
`on_event` override must therefore intercept **only** `events.Key`; a wider
guard would swallow events the pane and the app still need.

**No orphans, and step 10's grep is real.** `grep -rn "action_send\|_status("
pipeline/ tests/` returns exactly three source hits: `app.py:216`
(`self._status(rows)`), `app.py:230` (the def) and `app.py:459`
(`def action_send`). Nothing else in `pipeline/` or `tests/` calls either, and
`_ask` keeps its two other callers (`:503`, `:508`), so removing `action_send`
orphans nothing.

**Verified end to end on THIS tree before this plan was written.** The exact
code in the steps below was applied to a scratch copy of this worktree
(`/tmp/scratch021`, since deleted): `tests/test_tui.py` is **16 passed in
4.08s**, and the whole suite is **176 passed in 8.78s**. With
`pipeline/tui/app.py` reverted and only the step-2 test amendment in place, the
repro still fails with the original `AssertionError: raw mode never reached the
pty: b'\r'`, so the gate's base run (DEC-017) still reproduces.
`git status --porcelain` in the worktree is empty; nothing here is applied.

## Decisions checked

Read from `/home/chezzijr/proj/claude-setup/.project/decisions/` (**not** the
worktree -- only `DEC-011.md` is committed, so a worktree `ls` shows one record
where there are five; that repo-hygiene issue is noted in `## Thread`, not
fixed here). Grepped for
`tui|TUI|keystroke|pty|PTY|keybinding|suspend|input|status|Esc|escape|writer|raw|on_event|Key`.
**Five** records exist -- DEC-011, DEC-016, DEC-017, DEC-019, DEC-020 -- and
`grep -l "superseded-by" *.md` returns nothing, so all five are active.

- **DEC-019** (TICKET-019, `files: pipeline/tui/app.py, tests/test_tui.py` --
  this ticket's exact two files). Scored clause by clause:
  - *"`resize` is writer-only, and the TUI gates on the attach reply's `writer`
    flag."* Raw mode sends no `resize`. `_resize`'s guard
    (`if ... or not self.pty_writer: return`, `pipeline/tui/app.py:396`) and
    `self.pty_writer` are untouched, and `_detach` keeps its
    `self.pty_writer, self.resize_id = False, None` line -- the new
    `self.raw, self.esc = False, 0` goes *after* it, not over it. Complies.
  - *"The local `pyte` screen is resized optimistically, at send time, not on
    the ack."* Untouched: no step goes near `_resize` or `_attached`.
    `test_attaching_sends_the_pane_size` passes in the prototype.
  - *"`_attached()` must call `_resize()` itself."* Untouched; the direct call
    at `:387` stays.
  - *"`events.Resize` does not bubble"* -- **the one clause that constrains new
    code here.** The `on_event` override sits upstream of Textual's whole
    dispatch, so a guard broader than `isinstance(event, events.Key)` would
    swallow the `Resize` `PtyPane.on_resize` depends on. The plan's guard is
    exactly that narrow, and the three TICKET-019 resize tests passing in the
    prototype is the check. Recorded as a constraint in `## Decisions` below.
  - *"`#pty { height: 1fr; }` is load-bearing."* No CSS change in any step.
  - **Not superseded, nothing to supersede.** DEC-019 scopes the writer gate to
    `resize` specifically, and deliberately: its objection is a read-only viewer
    stealing the keyboard *silently*, "merely by having a differently sized
    window". Raw mode is a deliberate keypress on a pane whose `_attached`
    already notified "another client holds the writer: read-only", and it sends
    `input` through the same ungated `_send_keys` `action_send` used. So raw
    mode is exactly as writer-polite as the code it replaces. Adding a
    `pty_writer` gate to `action_raw` would be a behaviour change DEC-019 does
    not ask for and this ticket did not; see `## Decisions`.
- **DEC-011** (frozen daemon protocol). It freezes the socket op vocabulary and
  says additive changes are fine. This plan is *not even additive*: it sends the
  existing `input` op with the same `data`/`written`/`short` contract and adds
  no op, no field and no event kind. Its one line about keybindings -- "Four TUI
  keybindings with zero protocol surface, do not spend it" -- is an argument
  *for* keeping `approve`/`reject`/`answer` off the wire, and this plan spends
  no protocol surface at all: it rebinds `i` from `action_send` to `action_raw`,
  both of which reach the daemon only through the existing `input` op. Complies;
  nothing to supersede.
- **DEC-016** (fence state parsed once in `pipeline/core/ticket.py`) -- matches
  the grep only on the word "input"; it is about ticket parsing. Not relevant.
- **DEC-017** (the gate's two-run reproduction) -- read because step 3 depends
  on it: the amended test must still fail on base, which is exactly what
  DEC-017 says the gate requires. Measured on this tree, not assumed (see
  `## Digest`). Step 3 exists to honour it. No conflict.
- **DEC-020** (line-buffered stdout in entry points) -- read, touches neither
  the TUI nor key handling. Not relevant.

No decision anywhere explains the suspend-and-`input()` design of `action_send`;
it is documented only by its own docstring ("capturing every keystroke would
mean giving up the keybindings this app is"), which this plan answers directly:
the keybindings are given up *only while raw mode is on*, and `Esc Esc` gives
them back. Nothing is being removed that a record asked for.

## Plan

1. Confirm the tree the counts below were measured on: `uv run --group dev pytest -q tests/test_tui.py` must report `1 failed, 14 passed` (15 tests in `tests/test_tui.py`, the failure being the committed repro) -- if it reports any other count the worktree is not `364ac41` and every count in this plan is wrong; stop and report rather than adjusting the numbers.

2. In `tests/test_tui.py`, inside `test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc`, replace the four lines `await pilot.press("i")` / `await pilot.pause()` / `await pilot.press("down", "tab")` / `await pilot.pause()` with the per-key loop below -- `FakeStream` never acks, and `_flush_keys` holds the second keystroke while one op is in flight, so without this the assertion sees only `b"\x1b[B"`. Assertions are untouched. `PTY_INPUT` is already imported at `tests/test_tui.py:14`.

    ```python
            await pilot.press("i")
            await pilot.pause()
            for key in ("down", "tab"):
                await pilot.press(key)
                await pilot.pause()
                # one op is in flight at a time and the daemon ack is what
                # releases the next keystroke; the fake stream never acks
                app.on_frame({"id": app.stream._id, "ok": True,
                              "data": {"written": PTY_INPUT}})
    ```

3. Run `uv run --group dev pytest -q "tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc"` and confirm `tests/test_tui.py` is still RED with `AssertionError: raw mode never reached the pty: b'\r'` -- the amended test must still reproduce the bug, or the gate's base run (DEC-017) has nothing to prove.

4. In `pipeline/tui/app.py` change the import line `from textual import work` to `from textual import events, work` (line 28).

5. In `pipeline/tui/app.py`, immediately above `def marker(row: dict) -> str:` (line 53), add the key table and its decoder.

    ```python
    # What a terminal sends for a key Textual hands us only the *name* of. Raw
    # mode needs the bytes: `Key.character` is None for a cursor key, and wrong for
    # backspace -- Textual says \x08, a terminal sends \x7f.
    RAW_KEYS = {
        "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D",
        "home": b"\x1b[H", "end": b"\x1b[F", "insert": b"\x1b[2~",
        "delete": b"\x1b[3~", "pageup": b"\x1b[5~", "pagedown": b"\x1b[6~",
        "shift+tab": b"\x1b[Z", "tab": b"\t", "enter": b"\r", "escape": b"\x1b",
        "backspace": b"\x7f", "space": b" ",
    }


    def key_bytes(event) -> bytes:
        """One Textual key event -> the bytes the terminal would have sent. Total:
        a key with no sequence (f5, alt+x) is dropped, never guessed."""
        if event.key in RAW_KEYS:
            return RAW_KEYS[event.key]
        name = event.key.removeprefix("ctrl+")
        if name != event.key and len(name) == 1 and name.isalpha():
            return bytes([ord(name.upper()) ^ 0x40])
        return event.character.encode("utf-8") if event.is_printable else b""
    ```

6. In `pipeline/tui/app.py` change the `BINDINGS` row `("i", "send", "type"),` (line 125) to `("i", "raw", "type"),`.

7. In `pipeline/tui/app.py`, in `__init__`, add two fields directly under the line `self.keys_flight = None       # (request id, chunk) currently with it` (line 144).

    ```python
            self.raw = False              # raw mode: every keystroke goes to the pty
            self.esc = 0                  # escapes held back, waiting for the second
    ```

8. In `pipeline/tui/app.py`, replace the whole of `action_send` (lines 459-466, from `def action_send` up to but not including the blank line before `    # -- the keys that only touch the ticket file`) with the interception seam, the key handler and the new action; `_ask` keeps its two other callers (`:503`, `:508`) so nothing is orphaned.

    ```python
        async def on_event(self, event) -> None:
            """Raw mode has to catch a key HERE, before Textual checks the bindings
            and before it forwards to the focused Tree -- anywhere later and `down`
            moves the ticket cursor instead of reaching the child. It is also the
            only point at which ctrl+c is still ours to pass on. The guard stays
            narrowed to `events.Key`: DEC-019's pane sizing needs `Resize` through."""
            if self.raw and isinstance(event, events.Key) and not event.is_forwarded:
                return self._raw_key(event)
            await super().on_event(event)

        def _raw_key(self, event) -> None:
            """Every keystroke goes to the child except `Esc Esc`, the way back out.
            A lone Esc is held rather than sent: an agent prompt reads Esc as
            cancel, so a stray one on the way out of raw mode would answer the
            question you attached to read."""
            if event.key == "escape":
                self.esc += 1
                if self.esc > 1:
                    self.raw, self.esc = False, 0
                    self._status()
                return
            # ponytail: a held Esc is flushed by the next key, never by a timer.
            # Upgrade = a timeout, if "Esc alone does nothing" ever bites.
            pending, self.esc = b"\x1b" * self.esc, 0
            data = pending + key_bytes(event)
            if data:
                self._send_keys(data)

        def action_raw(self) -> None:
            """Hand the keyboard to the attached terminal until `Esc Esc`. The old
            `i` suspended the whole app to read one line through `input()`, which
            took the tree, the pane and the prompt off screen to answer it."""
            if self.attached is None:
                return self.notify("select an interactive stage first")
            self.raw, self.esc = True, 0
            self._status()
    ```

9. In `pipeline/tui/app.py`, make `_status` read its own rows and show the mode -- change the signature `def _status(self, rows: list[dict]) -> None:` (line 230) to `def _status(self) -> None:` with `rows = list(self.rows.values())` as its first line, add `mode = "RAW (esc esc to exit) - " if self.raw else ""` after the `drops = ...` line, and change the f-string to `f"{mode}{len(rows)} tickets - {running} running{drops}"`; `_paint` sets `self.rows` (line 210) before it calls `_status`, so the rows are the same set.

10. In `pipeline/tui/app.py` change the one call site `self._status(rows)` in `_paint` (line 216) to `self._status()`; a stale `self._status(rows)` anywhere is a `TypeError` at the next 5s refresh, not a test failure, so grep the file for `_status(` and confirm exactly two hits (the def and this call).

11. In `pipeline/tui/app.py`, in `_detach` (line 357), add `self.raw, self.esc = False, 0` and then `self._status()` immediately after the `self.keys_out, self.keys_flight = b"", None` line (line 366) -- a stage that ends (`on_frame` -> `stage_end` -> `_detach`) must hand the keyboard back, or every keystroke goes to a pane that is no longer attached. Do not disturb the `self.pty_writer, self.resize_id = False, None` line above it: DEC-019 owns it.

12. Run `uv run --group dev pytest -q "tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc"` and confirm `tests/test_tui.py` is GREEN (`1 passed`).

13. Append to the end of `tests/test_tui.py` the status helper and the second test, which covers what the reproduction test does not: the mode is on screen, `i` refuses with nothing attached, and detaching leaves raw mode.

    ```python
    def status(app) -> str:
        return str(app.query_one("#status").render())


    def test_raw_mode_is_visible_and_does_not_outlive_the_attachment():
        """A keyboard that silently belongs to the child is worse than no raw mode,
        and raw mode pointed at a detached pane types into nothing."""
        async def go():
            app = PipelineApp(client=FakeClient([]))
            async with app.run_test() as pilot:
                app.stream = FakeStream()
                app.pty_screen = Screen(4, 24)
                await pilot.press("i")
                await pilot.pause()
                assert app.raw is False, "raw mode with nothing to type into"

                app.attached = ("/tmp/alpha", "TICKET-001")
                await pilot.press("i")
                await pilot.pause()
                assert app.raw is True
                assert "RAW" in status(app), status(app)

                app._detach()
                await pilot.pause()
                assert app.raw is False, "raw mode outlived the attachment"
                assert "RAW" not in status(app), status(app)

        asyncio.run(go())
    ```

14. Run `uv run --group dev pytest -q tests/test_tui.py` and confirm `16 passed` -- the 15 tests step 1 counted plus the one added in step 13 (measured in the prototype: `16 passed in 4.08s`; the re-triage note's "15" is the pre-change count, not this one). A failure in `test_tui_renders_tree_from_ls` means the `_status` signature change in `pipeline/tui/app.py` missed a call site (step 10); a failure in `test_attaching_sends_the_pane_size`, `test_resizing_the_terminal_resizes_the_child` or `test_a_read_only_viewer_never_sends_a_resize` means the `on_event` guard in `pipeline/tui/app.py` is swallowing more than `events.Key` (DEC-019).

15. Commit both files: `git add pipeline/tui/app.py tests/test_tui.py && git commit -m "feat: raw mode hands every keystroke to the attached pty until esc esc"`.

## Acceptance criteria

1. Pressing `i` on an attached interactive stage sends `down` and `tab` to the pty as `b"\x1b[B\t"` and does not suspend the app -- `tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc` (first half), which currently fails with `b'\r'`.
2. `Esc Esc` leaves raw mode and a following `down` sends nothing to the pty -- same test, second half (`after == sent`).
3. Raw mode is visible while it is on: `#status` contains `RAW`, and does not once it is off -- `tests/test_tui.py::test_raw_mode_is_visible_and_does_not_outlive_the_attachment`.
4. `i` with nothing attached notifies and does **not** enter raw mode (`app.raw is False`) -- same test, first assertion.
5. Detaching (which is what `stage_end` does) clears raw mode -- same test, last two assertions.
6. Nothing else in the dashboard regresses: `uv run --group dev pytest -q tests/test_tui.py` reports **`16 passed`**. (15 on this tree today: 14 passing + the red repro, plus the one step 13 adds. Measured in the prototype, not projected: `16 passed in 4.08s`.)
7. DEC-019's pane sizing still works, i.e. the `on_event` override lets `Resize` through: `test_attaching_sends_the_pane_size`, `test_resizing_the_terminal_resizes_the_child` and `test_a_read_only_viewer_never_sends_a_resize` are among the 16 in criterion 6 and all pass.
8. Nothing outside the TUI regresses: `uv run --group dev pytest -q` reports `176 passed` (measured in the prototype: `176 passed in 8.78s`).
9. The daemon protocol is untouched: `git diff --name-only main...` lists exactly `pipeline/tui/app.py` and `tests/test_tui.py`.

## Decisions

**Raw mode is intercepted in `App.on_event`, and that is not a style choice.**
Textual checks priority bindings and then forwards the key to the focused widget
*before* the app's own `on_key` runs, and the `Tree` eats `down`/`up`/`enter`
with its own bindings. An `on_key` handler, a `Binding`, or `check_action` all
sit downstream of that and cannot see those keys. `on_event` is also the only
point where `ctrl+c` is still ours -- Textual's `help_quit` is a system binding
in the priority pass, which runs immediately after. If a future Textual changes
this dispatch order, the symptom is arrows moving the ticket cursor while raw
mode is on; the fix is a new interception point, not a wider key table.

**The `on_event` guard is narrowed to `events.Key` because of DEC-019.**
The override sits upstream of Textual's entire dispatch, so anything it returns
early on is an event no widget ever sees. `PtyPane` exists precisely because
`events.Resize` does not bubble (DEC-019), and `PtyPane.on_resize` is the only
thing that learns the pane's real size. Widening the guard to "swallow
everything while raw mode is on" would silently freeze the child's size at
whatever it was when `i` was pressed. The three TICKET-019 resize tests are the
tripwire; keep them in the same file.

**In raw mode `Esc Esc` is the only way out, deliberately.** `ctrl+c`, `q` and
every other binding belong to the child while it is on -- that is the entire
feature, since the prompts this exists to answer use ctrl+c and arrow keys. The
mode is therefore *required* to be visible (`RAW (esc esc to exit)` in the
status line) and *required* to end when the attachment does (`_detach`). Remove
either and a user is locked out of their own dashboard with no way to tell why.

**A lone `Esc` is held, not sent.** The first Esc is buffered and only reaches
the child prefixed to the *next* keystroke; the second exits raw mode. An agent
prompt reads Esc as "cancel", so sending it eagerly would answer the question
you attached to read on your way out of the mode. The cost is that Esc alone
does nothing until another key follows -- the same trade tmux makes with its
prefix. The upgrade, if it ever bites, is a timeout, not eager sending.

**`backspace` maps to `\x7f`, not to `events.Key.character`.** Textual reports
`\x08` for backspace; a terminal with default `stty erase` sends `\x7f`, and a
readline prompt ignores `\x08`. `RAW_KEYS` wins over `character` for exactly
this reason -- do not "simplify" `key_bytes` down to `event.character`.

**`action_raw` is deliberately NOT gated on `pty_writer`, and that was checked
against DEC-019, not overlooked.** DEC-019 makes `resize` writer-only because a
read-only viewer would steal the keyboard *silently*, by nothing more than
having a differently sized window. Typing is not silent: it takes a keypress on
a pane whose `_attached` already said "another client holds the writer:
read-only", and the `action_send` raw mode replaces was ungated in exactly the
same way. Adding the gate here would be a new behaviour nobody asked for;
removing DEC-019's gate from `_resize` because "raw mode does not need one"
would be the actual violation. Leave both as they are.

**One `input` op stays in flight at a time.** Raw mode reuses `_send_keys` /
`_flush_keys` unchanged, so short writes are still resent in order. The visible
consequence is that a test with a fake stream must ack an op before the next
keystroke can leave; `FakeStream` never does, which is why the reproduction test
acks per key. If someone later "fixes" typing latency by sending ops
concurrently, the tail of a short write can land after the keystrokes that
followed it -- reordered input, which looks like a flaky terminal.

**The mode indicator lives in the `#status` line, not the `Footer` widget.**
`Footer` renders `BINDINGS`; a mode there would mean dynamic bindings. `_status`
is re-run by the 5s `refresh_tree` -> `_paint`, so the indicator must be produced
*inside* `_status` -- setting the Static from `action_raw` alone would be erased
within five seconds. That is why `_status` loses its `rows` parameter and reads
`self.rows` instead: it now has two callers that have no rows list to hand it
(`action_raw`, `_detach`).

## Rollback

Revert the single commit (`git revert <sha>`, or `git checkout main --
pipeline/tui/app.py tests/test_tui.py`). Nothing persists outside those two
files: no protocol op, no daemon state, no ticket-file field, no config key. The
old behaviour returns with `action_send` -- `i` suspends the app and reads one
line -- and `tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc`
goes red again, which is the intended signal. The cherry-picked repro commit
`364ac41` is *not* part of the rollback: it only carries the failing test.

If raw mode turns out to be unescapable in a real terminal (the failure worth
watching for, since it locks the keyboard), the one-line mitigation without a
revert is deleting the `("i", "raw", "type")` binding from `BINDINGS` in
`pipeline/tui/app.py`: nothing else can turn `self.raw` on.

## Thread

### 2026-08-21 04:29:43Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 · triage · result=ok

Reproduced and committed `f22598f` on `ticket/021`.

- Traced the path: `BINDINGS` binds `i` -> `action_send` (`pipeline/tui/app.py:422`)
  -> `_ask` (`:476`) -> `self.suspend()` + `input()`. Nothing between the key and
  the pty is missing on the protocol side; `_send_keys`/`_flush_keys` (`:385-419`)
  already chunk to `PTY_INPUT` and honour short writes, so raw mode only needs a
  key handler that feeds `_send_keys`.
- Test lives in `tests/test_tui.py` (plain asserts, `asyncio.run` + Textual pilot,
  same shape as the neighbouring pty tests). It fails on the *symptom*: the arrow
  key never reaches the pty and the only byte sent is the `\r` `action_send`
  appends to the empty line `_ask` returns.
- Note for the next stage, not acted on here: the ticket also asks for the mode to
  be visible in the footer. The committed test does not cover that -- it asserts
  keystroke routing and the `Esc Esc` exit only. Add the footer assertion when the
  acceptance criteria are written.
- Note: `tests/test_tui.py` is also touched by TICKET-019 per the ticket body, so
  expect `files_conflict` serialization.

### 2026-08-21 05:11:36Z · triage · session · session=d178e941-3c41-4f1c-a7a3-711f4816365e

`triage` ran as session `d178e941-3c41-4f1c-a7a3-711f4816365e`
- replay: `claude --resume d178e941-3c41-4f1c-a7a3-711f4816365e`
- log: `.project/logs/TICKET-021-triage-d178e941.log`

### 2026-08-21 05:11:36Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

reproduced -- `i` suspends the app and only `\r` reaches the pty; failing raw-mode test committed as f22598f

### 2026-08-21 · planning · result=ok

Plan written and pre-validated by prototyping it in a scratch copy of the
worktree, then reverting (`git status --porcelain` empty; nothing is applied).

- **Design settled by measurement, not by reading docs.** Textual 8.2.8 forwards
  a key to the focused widget before the app's own bindings, and the `Tree` eats
  `down`. A probe app confirmed that overriding `App.on_event` sees every key
  including `ctrl+c`: `[('i', 'i'), ('down', None), ('tab', '\t'),
  ('escape', '\x1b'), ('ctrl+c', None), ('a', 'a')]`. `character` is `None` for
  cursor keys, so a name -> bytes table is unavoidable.
- **The committed reproduction test cannot pass as written.** `_flush_keys`
  allows one `input` op in flight and `FakeStream` never acks, so with raw mode
  fully working the assertion still sees `b"\x1b[B"` (tab stranded in
  `keys_out`). Measured, not guessed. Step 1 of the plan acks per key inside the
  test; the assertions are unchanged, and the amended test still fails on an
  unpatched `pipeline/tui/app.py` with the original `b'\r' != b'\x1b'` symptom,
  so the gate's base run still reproduces.
- Prototype results: reproduction test `1 passed`, full `tests/test_tui.py`
  `13 passed` (11 existing + 2 raw-mode).
- **Out of scope, noted not acted on:** F-keys and `alt+<key>` have no entry in
  `RAW_KEYS` and are dropped rather than guessed at; TICKET-019's pane sizing is
  still what makes a 40x120 child look wrong inside a wide pane.

### 2026-08-21 05:33:57Z · planning · session · session=b4fda581-32b4-4305-82ec-58c645010180

`planning` ran as session `b4fda581-32b4-4305-82ec-58c645010180`
- replay: `claude --resume b4fda581-32b4-4305-82ec-58c645010180`
- log: `.project/logs/TICKET-021-planning-b4fda581.log`

### 2026-08-21 05:33:57Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

raw mode plan written and pre-validated in a scratch copy; step 1 fixes the committed reproduction test, which cannot pass as written because FakeStream never acks the one in-flight input op

### 2026-08-21 05:34:04Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc` fails as required
```
 _ _ 

    async def go():
        app = PipelineApp(client=FakeClient([]))
        async with app.run_test() as pilot:
            app.stream = FakeStream()
            app.attached = ("/tmp/alpha", "TICKET-001")
            app.pty_screen = Screen(4, 24)
    
            await pilot.press("i")
            await pilot.pause()
            await pilot.press("down", "tab")
            await pilot.pause()
            sent = b"".join(base64.b64decode(kw["data"])
                            for op, kw in app.stream.sent if op == "input")
>           assert sent == b"\x1b[B\t", f"raw mode never reached the pty: {sent!r}"
E           AssertionError: raw mode never reached the pty: b'\r'
E           assert b'\r' == b'\x1b[B\t'
E             
E             At index 0 diff: b'\r' != b'\x1b'
E             Use -v to get more diff

tests/test_tui.py:391: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.55s ===============================

```

### 2026-08-21 · plan-validation · result=fail

Six of eight items pass and were re-derived from source rather than taken on the
plan's word. Two fail, both from one root: **the plan was measured against a
branch that is behind `main`, and `main` already carries TICKET-019's merge of
these same two files.**

**FAIL -- blast radius / regression surface / criterion 6 is wrong.**
`git merge-base --is-ancestor main HEAD` reports main is *not* an ancestor.
TICKET-019 is `stage: done` and merged (`4ed4307 Merge branch 'main' into
ticket/019`). Measured across the two trees:

| | this branch | `main` |
|---|---|---|
| `PtyPane`/`pty_writer` in `pipeline/tui/app.py` | 0 | 12 |
| tests in `tests/test_tui.py` | 12 | 14 |

Main's three extra tests are `test_attaching_sends_the_pane_size`,
`test_resizing_the_terminal_resizes_the_child`,
`test_a_read_only_viewer_never_sends_a_resize`. This branch's 12 = the 11 shared
+ 021's committed repro. Post-merge the file holds **16** tests
(11 + 3 + repro + the new raw-mode one), so acceptance criterion 6's `13 passed`
and step 13's "11 existing tests plus the two raw-mode ones" both fail on a
*correct* implementation, and step 13's stated diagnostic ("a failure here means
the `_status` signature change missed a call site") would misdiagnose it. The
planning entry's "Prototype results: ... `13 passed`" is the same stale
measurement.

**FAIL -- decision conflict, one record unevaluated.** "Decisions checked" says
"Four records exist"; `ls .project/decisions/` returns **five**: DEC-011,
DEC-016, DEC-017, **DEC-019**, DEC-020. DEC-019 is one of only two matching the
plan's own grep (`tui|TUI|keystroke|pty|PTY|keybinding|suspend|input`), is
`files: pipeline/tui/app.py, tests/test_tui.py` -- this ticket's exact declared
files -- and carries no `superseded-by:`. The plan neither cites nor complies
with nor supersedes it. I checked its constraints myself and they are
*compatible*: DEC-019's writer gate is resize-only ("`resize` is writer-only"),
and `_send_keys`/`_flush_keys`/`action_send` are byte-identical between this
branch and main, so raw mode reusing `_send_keys` is no worse than `action_send`
was and steals no keyboard DEC-019 protects. But that is a conclusion the plan
did not reach, and an unevaluated decision on the same two files is exactly the
item this stage exists to score. Relatedly, the Summary's "Both are also
TICKET-019's, so the two serialize on `files_conflict`" treats 019 as pending
when it is done.

**PASS -- root cause vs symptom.** Root cause in my own words: `i` is bound to
`action_send`, which reads *one line* through `self.suspend()` + `input()`
(`pipeline/tui/app.py:422-429` -> `_ask:476`); and even without the suspend, a
key handler on the App could not fix it, because Textual dispatches a key to
priority bindings and then to the focused widget *before* the app's own
bindings, and the focused `Tree` consumes `down`/`up`/`enter`. So there is no
point in the current app where an arrow key is still available to forward. The
plan creates that point. It fixes why, not just the assertion.

**PASS -- the interception seam, verified against the installed source, not the
docs.** `textual/app.py:4060` is `async def on_event(self, event: events.Event)
-> None`, and `:4136-4138` is exactly `if not await self._check_bindings(
event.key, priority=True): forward_target = self.focused or self.screen;
forward_target._forward_event(event)`. Overriding `on_event` and returning
before `super()` is therefore genuinely the only seam upstream of both. The
override's signature and `await super().on_event(event)` match. `is_forwarded`
exists (`textual/message.py:94`), so the `not event.is_forwarded` guard is real.

**PASS -- step 1's claim that the committed test cannot pass as written.**
Confirmed against `_flush_keys` (`:396`): `if self.keys_flight or not
self.keys_out or self.stream is None: return`. With raw mode working, `down`
sends and sets `keys_flight`; `tab` lands in `keys_out` and never leaves, so the
assertion sees `b"\x1b[B"`. The ack the step adds is well-formed:
`FakeStream.send` increments and returns `_id` (`tests/test_tui.py:199-202`), and
`on_frame` routes on `msg["id"] == self.keys_flight[0]` (`:259`), so
`app.stream._id` is the right id -- the same idiom
`test_keystrokes_are_chunked_and_a_short_write_is_resent:274` already uses. On an
unpatched app.py the extra `on_frame` call is inert (falls through to
`ev = msg.get("event")` -> `None` -> return), so the amended test still fails
with `b'\r'`. Step 2 requires exactly that re-check.

**PASS -- falsifiable criteria.** 1-5 each name a test and a byte-level or
boolean assertion that a wrong implementation fails: routing `b"\x1b[B\t"`,
`after == sent` after `Esc Esc`, `"RAW" in status(app)`, `app.raw is False` with
nothing attached, and raw cleared by `_detach`. None is vacuous. 7 is
mechanically checkable and `main...` (merge-base) keeps it correct even once the
branch merges main.

**PASS -- scope discipline.** Every step traces: 3/4/5/6/7 -> criteria 1-2,
8/9 -> criterion 3 (and the `_status` signature change is *required*, not
incidental -- the 5s `refresh_tree` -> `_paint` -> `_status` would erase an
indicator written anywhere else), 10 -> criterion 5, 12 -> criteria 3-5,
2/11/13 verification, 14 the commit. Nothing unattributable. `action_send` is
removed with no orphan: `_ask` keeps two callers (`:466`, `:471`) and no test
references `action_send`.

**PASS -- riskiest step and its fallback.** Riskiest is step 7's `on_event`
override: it takes the entire keyboard, so a bug makes the dashboard
unescapable. The plan states the fallback explicitly -- delete the
`("i", "raw", "type")` row from `BINDINGS`, after which nothing can set
`self.raw` -- plus the forward-looking symptom if Textual's dispatch order ever
changes (arrows move the ticket cursor while raw is on). Adequate.

**PASS -- no research left, with one nit.** Every step names the file, the
function and the literal code. Some cited line numbers drift (the digest puts
`BINDINGS` at 129-138; it is 106-116 here and 125 on main. Steps 4/6/10 are each
off by one). Every anchor *string* is unique in the file and survives the merge
into main, so this costs the implementer a grep, not a decision -- noted, not
charged.

**What a retry has to change:** merge `main` into `ticket/021` first, then
re-run the plan's own verification against the merged tree and correct the count
in criterion 6 and step 13; and score DEC-019 explicitly in "Decisions checked"
(the compatibility argument above is available, but the plan must make it). The
design, the key table, and steps 1-12's code do not need to change.

### 2026-08-21 05:39:45Z · plan-validation · session · session=d5b37dd1-6049-4df9-aac1-dedd7b0c517b

`plan-validation` ran as session `d5b37dd1-6049-4df9-aac1-dedd7b0c517b`
- replay: `claude --resume d5b37dd1-6049-4df9-aac1-dedd7b0c517b`
- log: `.project/logs/TICKET-021-plan-validation-d5b37dd1.log`

### 2026-08-21 05:39:45Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

plan measured against a branch behind main -- TICKET-019 is already merged there (14 tests vs 12, PtyPane/pty_writer absent here), so criterion 6's "13 passed" fails on a correct implementation (post-merge count is 16); and DEC-019, scoped to these exact two files, was never read (plan says four decision records exist, there are five)

### 2026-08-21 · planning · result=ok

Second pass, after the plan-validation `fail`. Both charged items are fixed and
the fix for each was measured, not asserted. The design, the key table and the
step code are unchanged -- validation said they did not need to change.

- **`main` merged into `ticket/021`: `e8b505c`.** One conflict, in
  `tests/test_tui.py`, and it was the benign kind: both sides appended a test to
  the end of the file (HEAD the TICKET-021 repro, main TICKET-019's three
  pty/resize tests). Resolved by keeping both, in that order. Post-merge:
  `git merge-base --is-ancestor main HEAD` passes, `tests/test_tui.py` holds 15
  tests, and `uv run --group dev pytest -q tests/test_tui.py` is
  `1 failed, 14 passed` -- the one failure being the committed repro, still with
  the original `b'\r'` symptom.
- **The counts are corrected to 16**, and re-measured rather than projected: the
  plan's exact code applied to a scratch copy of the merged worktree gives
  `16 passed in 4.50s`. Criterion 6 and step 14 say 16; step 1 pins the
  pre-change count at 15 so a wrong tree is caught before any edit.
- **DEC-019 read and scored clause by clause** in `## Decisions checked`. It is
  compatible -- its writer gate is scoped to `resize`, and `_send_keys` /
  `_flush_keys` / `action_send` are untouched by this change -- but it is not
  vacuous either: its *"`events.Resize` does not bubble"* clause is what forces
  the `on_event` guard to stay `isinstance(event, events.Key)`. That is now a
  recorded decision, a comment in the code the plan writes, criterion 7, and a
  named diagnostic in step 14. The previous pass said four decision records
  exist; there are five, all active, none superseded.
- **Every line number re-taken from the merged tree** (`import` 28, `marker` 53,
  `BINDINGS` 125, `keys_flight` 144, `self._status(rows)` 216, `_status` 230,
  `_detach` 357/366, `action_send` 459). Each anchor string was re-confirmed
  unique in the file.
- **Reverted claim:** the Summary previously said TICKET-019 was pending and the
  two tickets would serialize on `files_conflict`. 019 is `done` and merged;
  that sentence is gone.
- Scratch copy deleted; `git status --porcelain` in the worktree is empty. The
  only thing this pass committed is the merge.
- **Out of scope, noted not acted on:** F-keys and `alt+<key>` have no entry in
  `RAW_KEYS` and are dropped rather than guessed at. `skydeckai-conversation-316269.md`
  sits untracked-but-committed at the repo root and looks like it does not
  belong there; not this ticket's business.

### 2026-08-21 05:47:02Z · planning · session · session=cbe86125-ecf5-4985-8b9f-b4b4400bd22e

`planning` ran as session `cbe86125-ecf5-4985-8b9f-b4b4400bd22e`
- replay: `claude --resume cbe86125-ecf5-4985-8b9f-b4b4400bd22e`
- log: `.project/logs/TICKET-021-planning-cbe86125.log`

### 2026-08-21 05:47:02Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

replanned against the merged tree - main merged into ticket/021 (e8b505c), counts corrected to 16 and re-measured in a scratch prototype, DEC-019 read and scored clause by clause

### 2026-08-21 05:47:11Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc` fails as required
```
 _ _ 

    async def go():
        app = PipelineApp(client=FakeClient([]))
        async with app.run_test() as pilot:
            app.stream = FakeStream()
            app.attached = ("/tmp/alpha", "TICKET-001")
            app.pty_screen = Screen(4, 24)
    
            await pilot.press("i")
            await pilot.pause()
            await pilot.press("down", "tab")
            await pilot.pause()
            sent = b"".join(base64.b64decode(kw["data"])
                            for op, kw in app.stream.sent if op == "input")
>           assert sent == b"\x1b[B\t", f"raw mode never reached the pty: {sent!r}"
E           AssertionError: raw mode never reached the pty: b'\r'
E           assert b'\r' == b'\x1b[B\t'
E             
E             At index 0 diff: b'\r' != b'\x1b'
E             Use -v to get more diff

tests/test_tui.py:484: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.55s ===============================

```

### 2026-08-21 · plan-validation · result=ok

Eight items, all scored from source. Both charges from the first pass are
discharged by measurement.

**PASS -- root cause vs symptom.** Root cause in my own words: there is no point
in the current app where an arrow key is still available to forward to the
child. Two layers, and the plan fixes both. (1) `i` is bound to `action_send`
(`pipeline/tui/app.py:459`), which reads *one line* via `_ask` (`:513`) ->
`self.suspend()` + `input()`, so the whole dashboard leaves the screen and only
the trailing `b"\r"` ever reaches `_send_keys`. (2) Even deleting the suspend
would not do it: `textual/app.py:4136-4138` checks priority bindings and then
does `forward_target = self.focused or self.screen; forward_target
._forward_event(event)` *before* `App._on_key` reaches the app's own bindings,
and the focused `Tree` consumes `down`/`up`/`enter` with its own. So the plan's
`on_event` override is not a stylistic pick -- it is the only seam upstream of
both, and `ctrl+c` (`system=True`, priority pass) is only ours there. Verified
in the installed source, not from the docs.

**PASS -- decision conflict.** Five records in `.project/decisions/`, none
carrying `superseded-by` (grepped). Only DEC-019 binds: `files: pipeline/tui/
app.py, tests/test_tui.py`, this ticket's exact pair. I read it and its five
clauses match the plan's clause-by-clause scoring verbatim -- the writer gate is
scoped to `resize` ("`resize` is writer-only"), so raw mode reusing the ungated
`_send_keys` that `action_send` already used is no new keyboard theft; and
*"`events.Resize` does not bubble"* is a real constraint the plan converts into
the `isinstance(event, events.Key)` guard, a code comment, criterion 7 and step
14's diagnostic. The plan complies rather than supersedes, correctly: DEC-019's
stated objection is a viewer taking the keyboard *silently*, "merely by having a
differently sized window", which a deliberate keypress is not. DEC-011 (frozen
protocol, additive changes fine) is satisfied trivially -- no new op, field or
event kind; `input` is reused with the same `data`/`written` contract. DEC-016
(fence parsing in `pipeline/core/ticket.py`) and DEC-020 (line-buffered stdout
in entry points) are correctly dismissed; I checked both headers. DEC-017's
"test files copied onto base may only import what base has" holds: the amended
test adds no import, and `PTY_INPUT` (`tests/test_tui.py:14`) is already on main.

**PASS -- scope discipline.** Every step traces to a criterion: 4-8 -> 1-2,
9/10 -> 3 (the `_status` signature change is *required*, not incidental: the 5s
`refresh_tree` -> `_paint` -> `_status` (`:203-216`) would erase an indicator
written anywhere else), 11 -> 5, 13 -> 3/4/5, 1/3/12/14 verification, 2 the test
fix, 15 the commit. `action_send` is removed with no orphan: `_ask` keeps its
callers at `:503` and `:508`, and nothing in `pipeline/` or `tests/` references
`action_send` (grepped; the only other `_status(` hit is the unrelated
`cmd_daemon_status`). The one place I looked hard for creep is `RAW_KEYS`
carrying home/end/insert/delete/pageup/pagedown/shift+tab beyond the two keys
criterion 1 names -- for a "hand the keyboard to the child" feature a two-entry
table would be the defect, and F-keys/`alt+` are explicitly dropped rather than
guessed. Not charged.

**PASS -- falsifiable criteria.** 1: byte equality `b"\x1b[B\t"`; a wrong table
or a missed interception fails it. 2: `after == sent`; an unescapable mode
fails. 3: `"RAW" in status(app)` and absent after. 4: `app.raw is False` with
nothing attached. 5: raw cleared by `_detach`. 6: an exact count, 16. 7: three
named resize tests. 8: `git diff --name-only main...` -- today it prints only
`tests/test_tui.py` (checked), so it is a real check, not a tautology. None
vacuous.

**PASS -- no research left.** Every step names file, function and literal code,
and all nine cited lines are exact in the merged tree: `from textual import
work` 28, `def marker` 53, `("i", "send", "type")` 125, `self.keys_flight = None`
144, `self._status(rows)` 216, `def _status` 230, `def _detach` 357,
`self.keys_out, self.keys_flight` 366, `def action_send` 459 (block ends 466,
followed by the blank line before `# -- the keys that only touch the ticket
file`, exactly as step 8 describes). The API the new code leans on exists:
`App.on_event` is `async` at `textual/app.py:4060`, `Message.is_forwarded` at
`message.py:94`, `Key.is_printable` at `events.py:305` -- and it returns `False`
when `character is None`, so `key_bytes` is total for f5/`alt+x` as claimed.
`_paint` sets `self.rows` (`:210`) before calling `_status` (`:216`), so step 9's
`rows = list(self.rows.values())` is the same set. All three `_detach` call
sites (`:300`, `:324`, `:345`) run inside a mounted UI, so the added
`self._status()` cannot hit `NoMatches`.

**PASS -- riskiest step, with a fallback.** Step 8's `on_event` override: it
takes the entire keyboard, so a bug locks the user out of their own dashboard.
The plan states the mitigation without a revert -- delete the `("i", "raw",
"type")` row from `BINDINGS`, after which nothing can set `self.raw` -- plus the
forward symptom if Textual's dispatch order ever changes (arrows move the ticket
cursor while raw is on). Adequate. Second-riskiest, the `_status` signature
change, is a `TypeError` at the next 5s refresh rather than a test failure; step
10 pre-empts it with a grep for exactly two hits, which matches what I measured.

**PASS -- regression surface, and step 2's premise re-derived.** `_flush_keys`
(`:433`) is `if self.keys_flight or not self.keys_out or self.stream is None:
return`, and `FakeStream` (`tests/test_tui.py:190-205`) records without
replying, so with raw mode fully working `tab` would strand in `keys_out` and
the assertion would see `b"\x1b[B"` -- the committed test genuinely cannot pass
as written, and step 2 fixes the fake, not the assertions. The ack it adds is
well-formed: `send` returns the incremented `_id`, `on_frame` routes on
`self.keys_flight and msg.get("id") == self.keys_flight[0]` (`:276`), and a
surplus ack with `keys_flight is None` falls through to `ev = msg.get("event")`
-> `None` -> return, so on unpatched code the test still fails with `b'\r'`
(DEC-017's base run keeps its evidence). Breakage candidates and their covers:
the `_status` call site -> `test_tui_renders_tree_from_ls`; a guard wider than
`events.Key` -> the three TICKET-019 resize tests; `_ask`'s other two prompts ->
`test_a_wrong_stage_refuses_without_taking_the_app_down`. Step 14 names the
first two as diagnostics.

**PASS -- blast radius matches class.** `feature`, two files, one of them the
test. `git diff --name-only main...` prints one file today and will print two.
No daemon, protocol, config or ticket-schema surface.

Measured here, not quoted from the plan:

- `git merge-base --is-ancestor main HEAD` -> main IS ancestor; `HEAD` is
  `e8b505c`; `git status --porcelain` empty, so nothing is pre-applied.
- `grep -c "^def test_" tests/test_tui.py` -> **15**, including main's
  `test_attaching_sends_the_pane_size`, `test_resizing_the_terminal_resizes_the_child`,
  `test_a_read_only_viewer_never_sends_a_resize`.
- `uv run --group dev pytest -q tests/test_tui.py` -> `1 failed, 14 passed in
  4.05s`, the failure being the repro. Step 1's tripwire number is right and
  criterion 6's 16 follows.

Two nits, neither charged, neither needing a replan: the digest calls
`pipeline/tui/app.py` "612 lines after the merge" and it is **606** (every line
*number* it cites is nonetheless exact); and `.project/decisions/` is untracked
in git -- only `DEC-011.md` is committed on either branch, so DEC-016/017/019/020
exist solely in the main checkout's working tree. That is a repo hygiene issue
outside this ticket, but it means a future stage reading decisions from a
worktree sees one record where there are five.

### 2026-08-21 05:51:50Z · plan-validation · session · session=5d2eda22-ae5a-4614-a01e-735dbcbe8b39

`plan-validation` ran as session `5d2eda22-ae5a-4614-a01e-735dbcbe8b39`
- replay: `claude --resume 5d2eda22-ae5a-4614-a01e-735dbcbe8b39`
- log: `.project/logs/TICKET-021-plan-validation-5d2eda22.log`

### 2026-08-21 05:51:50Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

all eight items pass, re-derived from source - main is an ancestor (e8b505c), tests/test_tui.py measures 1 failed 14 passed so criterion 6's 16 is right, DEC-019 scored against its actual text, and all nine cited line anchors are exact

### 2026-08-21 05:56:07Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 05:56:08Z · revalidating · escalation

rebase onto base conflicted (exit 1)
```
$ git rebase main

Rebasing (1/1)
Auto-merging tests/test_tui.py
CONFLICT (content): Merge conflict in tests/test_tui.py
error: could not apply f22598f... test: raw mode routes keystrokes to the attached pty (TICKET-021)
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply f22598f... # test: raw mode routes keystrokes to the attached pty (TICKET-021)

```

### 2026-08-21 05:56:30Z · human · note

**resumed** by human -> `triage`, reset ['plan_validation_attempts', 'review_loops', 'blocked_count', 'no_result', 'lease_expiries']

### 2026-08-21 · triage (re-run) · result=ok

Reproduced on the reset branch. `ticket/021` was at `4ed4307`, not the
`e8b505c` the Digest records: the revalidate rebase aborted and took both the
`main` merge and the triage commit `f22598f` off the branch. Cherry-picked
`f22598f` back (`364ac41`); the one conflict is the same append-to-end-of-file
one the rebase reported, kept both sides. The test fails with the reported
symptom, not a setup error:
`AssertionError: raw mode never reached the pty: b'\r'`.

Two things later stages must not take from `## Digest` verbatim, both a
consequence of the reset:

- Its line anchors (28, 53, 125, 144, 216, 230, 357, 366, 459) were measured on
  `e8b505c`. Grep the quoted anchor *strings*, which the Digest itself says win
  over the numbers.
- `tests/test_tui.py` holds **15** tests on this branch, not 16, so criterion
  6's post-fix expectation is `15 passed`.

Out of scope for triage, noted only: the plan's step 2 (teach `FakeStream` to
ack so the second keystroke leaves `keys_out`) is still required -- the
committed test cannot pass on raw mode alone.

### 2026-08-21 05:58:34Z · triage · session · session=db80c663-412d-4662-8206-08d4d13a18af

`triage` ran as session `db80c663-412d-4662-8206-08d4d13a18af`
- replay: `claude --resume db80c663-412d-4662-8206-08d4d13a18af`
- log: `.project/logs/TICKET-021-triage-db80c663.log`

### 2026-08-21 05:58:34Z · triage · transition · to=escalated · result=fail

**triage -> escalated** (result: `fail`)

### 2026-08-21 05:59:49Z · human · note

**resumed** by human -> `planning`, reset ['blocked_count', 'no_result', 'lease_expiries']

### 2026-08-21 · planning · result=ok

Third planning pass, after the human resume (no `rejection` in this thread -- I
read every human entry: the two are a `resumed` note after the revalidate rebase
escalation and a second after the triage re-run's `fail`). The design, the key
table and every step's code are byte-for-byte what plan-validation passed; what
this pass adds is that all of it was re-measured on `364ac41` rather than on the
`e8b505c` that is no longer on the branch.

- **Every count re-measured on this tree.** `git merge-base --is-ancestor main
  HEAD` passes; `git status --porcelain` empty; `grep -c "^def test_"
  tests/test_tui.py` -> 15; `uv run --group dev pytest -q tests/test_tui.py` ->
  `1 failed, 14 passed in 3.57s`, the failure being the repro with the reported
  `b'\r'` symptom.
- **Corrected the re-triage note, and this is the one substantive change.** It
  says "criterion 6's post-fix expectation is `15 passed`". That conflates the
  pre-change count with the post-change one: 15 tests exist now, step 13 adds a
  sixteenth, so a correct implementation reports **16**. Measured in a scratch
  copy of this worktree: `16 passed in 4.08s`. Criterion 6 and step 14 say 16;
  step 1 pins the pre-change tripwire at `1 failed, 14 passed` so a wrong tree
  is caught before any edit.
- **All nine line anchors re-verified by grep on this tree and all nine are
  exact** (28, 53, 125, 144, 216, 230, 357, 366, 459) -- the cherry-pick
  reproduced the merge tree's content, so the re-triage warning that they were
  measured on `e8b505c` turns out to cost nothing. The Digest's other stale
  number is fixed: `pipeline/tui/app.py` is **606** lines, not 612.
- **Prototyped end to end on this tree, then deleted.** `/tmp/scratch021`, a
  copy of this worktree with the exact step code applied: `tests/test_tui.py`
  `16 passed`, whole suite `176 passed in 8.78s` (new datum, now criterion 8).
  With `pipeline/tui/app.py` reverted and only step 2's test amendment applied,
  the repro still fails with `AssertionError: raw mode never reached the pty:
  b'\r'` -- DEC-017's base run keeps its evidence. Scratch deleted;
  `git status --porcelain` in the worktree is empty, nothing is pre-applied.
- **Decisions re-read from the main checkout, not the worktree.** All five
  (DEC-011, 016, 017, 019, 020); `grep -l "superseded-by" *.md` returns nothing,
  so all five are active. DEC-019 is scored clause by clause and is compatible;
  its *"`events.Resize` does not bubble"* clause is what forces the `on_event`
  guard to stay `isinstance(event, events.Key)`. New this pass: DEC-011's "Four
  TUI keybindings with zero protocol surface -- do not spend it" line was read
  in context and is an argument against new socket ops, not against rebinding a
  key; this plan adds no op, field or event kind.
- **Verified there are no orphans:** `grep -rn "action_send\|_status("
  pipeline/ tests/` returns three source hits, all in `pipeline/tui/app.py`
  (216, 230, 459). Nothing else calls either, so step 10's "exactly two hits"
  check is accurate and removing `action_send` breaks no caller.
- **Out of scope, noted not acted on:** (a) `.project/decisions/` is untracked
  in git -- only `DEC-011.md` is committed, so any stage reading decisions from
  a worktree sees one record where there are five. That is a repo-hygiene bug
  worth its own ticket; the previous plan-validation flagged it too. (b) F-keys
  and `alt+<key>` have no entry in `RAW_KEYS` and are dropped rather than
  guessed at. (c) `skydeckai-conversation-316269.md` sits at the repo root and
  looks like it does not belong there.

### 2026-08-21 06:06:02Z · planning · session · session=cecf2d3b-4963-4c25-8ab4-aebb16a45b87

`planning` ran as session `cecf2d3b-4963-4c25-8ab4-aebb16a45b87`
- replay: `claude --resume cecf2d3b-4963-4c25-8ab4-aebb16a45b87`
- log: `.project/logs/TICKET-021-planning-cecf2d3b.log`

### 2026-08-21 06:06:02Z · planning · transition · to=escalated · result=fail

**planning -> escalated** (result: `fail`)
