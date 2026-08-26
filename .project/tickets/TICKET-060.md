---
id: TICKET-060
stage: done
class: feature
branch: ticket/060
test_file: tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones
files_declared:
- README.md
- pipeline/tui/app.py
- tests/test_tui.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 15
  plan_files: 3
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 5180a1e3-91d0-4008-bb80-3fdfcb36700f
  log: .project/logs/TICKET-060-review-5180a1e3.log
approved_by: chezzijr
approved_at: '2026-08-26T19:15:36.661164+00:00'
---

## Summary

Fixed: the TUI tree now hides `done`/`rejected` behind a new `f` key (default
hidden), keeps `escalated` and the selected row painted always, and opens the
cursor on the first non-terminal ticket instead of the root. Implemented on
`ticket/060` in 7 commits: `3f35082` (repro test, pre-existing),
`a6d02d3`, `a342ade`, `d2c541f`, `bf8b5fa`, `216a5b8`, `0cfd0c6`. Files:
`pipeline/tui/app.py`, `tests/test_tui.py`, `README.md`.

`pipeline/tui/app.py`: `FINISHED = TERMINAL - {"escalated"}`,
`self.show_finished`, `_visible(rows)` filters what `_paint()` groups into the
tree; the cursor-restore block in `_paint()` now falls back to the first row
whose stage is `not in TERMINAL` when `self.selected` cannot be restored,
using `tree.last_line` before `move_cursor()` to force the line build (a leaf
added this tick has `_line == -1` otherwise, which clamps to the root). `f` ->
`action_finished()` toggles `show_finished`, clears `self.sig` to force a
repaint, and `_status()` reports the hidden count.

All 7 acceptance criteria pass:
`uv run --group dev pytest -q tests/test_tui.py tests/test_cli.py
tests/test_stages.py` -> `73 passed`.

Review passed with no blocking findings. It re-ran the full suite
(`322 passed in 13.79s`), ran the 6 criteria tests by name, and confirmed the
working tree is clean. Two mutation runs prove the new tests fail when the
selected-row exception or the `escalated` carve-out is removed. Three non-blocking
notes are in the thread: the module docstring still says "those eight" at
`app.py:8` while line 4 says "Ten keys"; `tree.last_line` at `app.py:315` is a
bare expression pyright would flag; one test now drives the tree from the
keyboard.

## Reproduction

`tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` -- seeds a
project with 50 `done` tickets (TICKET-001..050) and one `implementing`
ticket (TICKET-060), then asserts the first row in the tree is TICKET-060.

Command: `uv run --group dev pytest -q tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones`

Failure output:
```
    assert got[0].startswith("TICKET-060"), got[:3]
E   AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']
E   assert False
```
expect: AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']

## Digest

Files touched: `pipeline/tui/app.py` (the tree), `tests/test_tui.py` (the
suite), `README.md` (the documented key list, line 249).

Key functions, all in `pipeline/tui/app.py`: `_paint()` (line 272) rebuilds the
tree and returns early when `sig` is unchanged; `label()` (86) formats one row;
`_status()` (296) writes the status line; `_show()` (384) fills the right pane;
`on_tree_node_highlighted()` (378) sets `self.selected` and returns early when
`event.node.data` is not a tuple; `BINDINGS` (180) holds nine keys and `f` is
free. `machine.TERMINAL` (`pipeline/core/machine.py:26`) is `{"done",
"rejected", "escalated"}`; `HUMAN_GATES` is already imported here.

Entry point: `pipeline tui` -> `cmd_tui` (`pipeline/cli/main.py:490`) ->
`PipelineApp.on_mount` -> `_paint`. Tests:
`uv run --group dev pytest -q tests/test_tui.py`.

Gotchas:

1. `tree.move_cursor(leaf)` immediately after `add_leaf()` does nothing. A leaf
   added this tick still has `_line == -1`, and `Tree.validate_cursor_line`
   clamps that to 0, the root. Measured against textual 8.2.8: the naive call
   leaves `cursor=0 node=None`; after reading `tree.last_line` (public, forces
   the line build) the same call gives `cursor=3 node=("alpha",
   "TICKET-002")`. This is why the existing restore of `self.selected` in
   `_paint()` puts the cursor on the root today.
2. Step 9 is the riskiest step of this plan, because it rests on that read.
   `Tree.last_line` is `len(self._tree_lines) - 1`
   (`textual/widgets/_tree.py:843`), and the `_tree_lines` property calls
   `self._build()` when `_tree_lines_cached is None` (line 1241). A textual
   upgrade that caches differently breaks the placement silently. Step 10 is
   the fallback: `self.call_after_refresh(tree.move_cursor, first)`
   (`textual/message_pump.py:451`), which defers the move to after the repaint
   that builds the lines. `tree.move_cursor_to_line()` is not a second
   fallback: it indexes `self._tree_lines` and rests on the same build.
3. Moving the cursor at mount stops `await pilot.press("down", "down")` from
   selecting anything in eight existing tests (`tests/test_tui.py` lines 161,
   181, 248, 324, 375, 407, 433, 472): the cursor already sits on the only
   ticket, `watch_cursor_line` returns early when the line does not change, and
   no `NodeHighlighted` fires. The four pty tests install `app.stream` after
   mount and would never attach. Step 2 replaces those eight; step 5 adds back
   one test that presses an arrow key, over two rows instead of one.
4. `tests/test_tui.py:511` also presses `down`, inside raw mode, where the key
   is forwarded to the pty as the three bytes ESC, bracket, B and never reaches
   the tree. Leave that line alone: it is not tree navigation.
5. `test_an_event_reseeds_the_tree_and_a_dropped_marker_says_so` (line 117)
   asserts the tree shows `["TICKET-001 escalated"]`, so `escalated` must stay
   visible. It is also the one terminal stage a human must open.
6. `_paint()` returns early when `sig == self.sig`, so the toggle must set
   `self.sig = None` before repainting, or a project whose visible labels did
   not change never rebuilds.
7. `self.rows` feeds `_show()`, `_stopped()` and `action_edit()` by key. The
   filter applies to what the tree paints, never to `self.rows`.
8. `tests/test_tui.py` already has the helpers `row()` (line 65), `labels()`
   (73) and `status()` (520). Reuse them; add only `select()`.

## Decisions checked

Grep terms in `.project/decisions/`: `tui`, `tree`, `_paint`, `cursor`,
`selected`, `TERMINAL`, `BINDINGS`, `footer`, `keybind`.

- DEC-021 (active) -- the mode indicator lives in `#status` and must be
  produced inside `_status()`, because the 5s `refresh_tree` -> `_paint`
  re-runs it. The hidden count goes in `_status()` for that reason.
- DEC-011 (active) -- "Four TUI keybindings with zero protocol surface -- do
  not spend it." `f` adds no daemon op; it filters rows the client already has.
- DEC-019 (active) -- `resize` is writer-only and `_attached()` must call
  `_resize()`. Untouched: no step changes the pty path.
- DEC-039 (active) -- `tail_log()` tells a PTY dump from stream-json by the
  bytes. Untouched: `_show()` still calls it unchanged.

No record constrains which rows the tree paints, or where the cursor opens.

## Plan

1. Add the helper `select()` to `tests/test_tui.py` directly above `def test_tui_renders_tree_from_ls`, as `async def select(app, pilot, project, tid):` with the body `tree = app.query_one(Tree)`, then `node = next(c for n in tree.root.children for c in n.children if c.data == (str(project), tid))`, then `tree.move_cursor(None)`, then `tree.move_cursor(node)`, then `await pilot.pause()`; the docstring says re-selecting the row the cursor already sits on must fire a highlight, which `press("down", "down")` cannot do once the tree opens on the first live ticket.
2. In `tests/test_tui.py`, replace each of the eight `await pilot.press("down", "down")` lines (161, 181, 248, 324, 375, 407, 433, 472) with `await select(app, pilot, d, "TICKET-001")`, keep the `app.query_one(Tree).focus()` line above each, and leave the `await pilot.press("down")` on line 511 alone because raw mode forwards it to the pty; run `uv run --group dev pytest -q tests/test_tui.py`, expect exactly one failure -- the known `test_finished_tickets_do_not_bury_live_ones` -- and commit as `test(TICKET-060): select a ticket by node instead of two arrow keys`.
3. Add `test_the_cursor_opens_on_a_live_ticket` to `tests/test_tui.py`: rows `TICKET-001 done`, `TICKET-002 done`, `TICKET-003 awaiting-approval` on `/tmp/alpha`, and after `run_test()` plus `await pilot.pause()` assert `app.selected == ("/tmp/alpha", "TICKET-003")`; run it and expect `AssertionError: None`.
4. Add `test_the_f_key_toggles_finished_tickets_back_into_the_tree` to `tests/test_tui.py`: rows `TICKET-001 done`, `TICKET-002 rejected`, `TICKET-003 escalated`, `TICKET-004 implementing` with `running=True`; assert `labels(app)["alpha"] == ["TICKET-003 escalated", "TICKET-004 implementing *"]` and `"2 finished hidden (f)" in status(app)`, then `await pilot.press("f")` with `await pilot.pause()` gives all four rows in id order and `"hidden" not in status(app)`, then a second `f` returns the two-row list; run it and expect the first assertion to fail with all four labels.
5. Add `test_the_down_key_moves_the_cursor_off_the_opening_row` to `tests/test_tui.py`: rows `TICKET-001 implementing` with `running=True` and `TICKET-002 awaiting-approval` on `/tmp/alpha`, call `app.query_one(Tree).focus()`, assert `app.selected == ("/tmp/alpha", "TICKET-001")`, then `await pilot.press("down")` with `await pilot.pause()` and assert `app.selected == ("/tmp/alpha", "TICKET-002")`; this is the arrow-key coverage step 2 takes off line 161, it holds `down` to a real cursor move over two rows instead of a walk up from the root, and it fails today at the first assertion with `assert None == ('/tmp/alpha', 'TICKET-001')`.
6. Add `test_a_selected_ticket_stays_in_the_tree_when_it_finishes` to `tests/test_tui.py`: one row `TICKET-001 implementing` with `running=True` on `/tmp/alpha`, assert `app.selected == (d, "TICKET-001")`, set `fake.rows = [row(d, "TICKET-001", "done")]`, deliver `app.on_frame({"sub": 1, "event": {"project": d, "ticket": "TICKET-001", "kind": "transition", "data": {}}})`, `await pilot.pause()`, then assert `labels(app)["alpha"] == ["TICKET-001 done"]` and `app.selected == (d, "TICKET-001")`; this is the guard on the selected-row exception in step 7, and it fails with `[]` if that exception is dropped; commit the four new tests as `test(TICKET-060): pin the cursor, the toggle, the down key and the selected row`.
7. In `pipeline/tui/app.py`, import `TERMINAL` next to `HUMAN_GATES` from `pipeline.core.machine`, add the module constant `FINISHED = TERMINAL - {"escalated"}` under `TREE_KINDS` with the comment that `escalated` is terminal and is exactly the row a human has to open, add `self.show_finished = False` to `__init__` next to `self.sig`, and add the method `_visible(self, rows)` returning `rows` when `self.show_finished` is true and otherwise `[r for r in rows if r.get("stage") not in FINISHED or (r["project"], r["id"]) == self.selected]`.
8. In `pipeline/tui/app.py`, group only the visible rows in `_paint()`: keep `self.rows = {(r["project"], r["id"]): r for r in rows}` unchanged, build `grouped: dict[str, list[dict]] = {r["project"]: [] for r in rows}`, then fill it with `for r in self._visible(rows): grouped[r["project"]].append(r)` so a project whose every ticket is hidden keeps an empty node; run `uv run --group dev pytest -q tests/test_tui.py`, expect `test_finished_tickets_do_not_bury_live_ones` and `test_a_selected_ticket_stays_in_the_tree_when_it_finishes` to pass, and commit as `fix(TICKET-060): keep finished tickets out of the TUI tree`.
9. In `pipeline/tui/app.py`, replace the cursor block of `_paint()` -- the riskiest step of this plan, whose fallback is step 10: set `keep, restored, first = self.selected, False, None` before `tree.root.remove_children()`, use `if leaf.data == keep: restored, first = True, leaf` and `elif not restored and first is None and self.rows.get(leaf.data, {}).get("stage") not in TERMINAL: first = leaf` inside the leaf loop, and after both loops write `if first is not None:` followed by `tree.last_line` on a line of its own, commented as forcing the line build because a leaf added this tick has `_line == -1` and `move_cursor` would clamp it to the root, then `tree.move_cursor(first)`; run `uv run --group dev pytest -q tests/test_tui.py`, expect `test_the_cursor_opens_on_a_live_ticket` and `test_the_down_key_moves_the_cursor_off_the_opening_row` to pass, and commit as `fix(TICKET-060): open the TUI cursor on a live ticket`.
10. Run this step only if step 9 left `test_the_cursor_opens_on_a_live_ticket` failing with `AssertionError: None`, which means the `tree.last_line` read no longer forces the line build: in `pipeline/tui/app.py` delete that read and the `tree.move_cursor(first)` under it, write `self.call_after_refresh(tree.move_cursor, first)` in their place, keep the comment, re-run `uv run --group dev pytest -q tests/test_tui.py` and commit with the step 9 message; if the test still fails, stop and report that neither placement puts the cursor on the ticket, because a cursor silently parked on the root is the behaviour this ticket reports.
11. In `pipeline/tui/app.py`, add `("f", "finished", "finished")` to `BINDINGS` after `("i", "raw", "type")`, and add `action_finished()` which sets `self.show_finished = not self.show_finished`, then `self.sig = None`, then calls `self.refresh_tree()`; the docstring says hidden is the default and `self.sig = None` is what forces the rebuild when the visible labels did not change.
12. In `pipeline/tui/app.py`, add the hidden count to `_status()`: keep `rows = list(self.rows.values())`, add `hidden = len(rows) - len(self._visible(rows))` and `finished = f" - {hidden} finished hidden (f)" if hidden else ""`, and update the `Static` with `f"{mode}{len(rows)} tickets - {running} running{finished}{drops}"`; run `uv run --group dev pytest -q tests/test_tui.py`, expect every test to pass, and commit as `feat(TICKET-060): the f key shows the finished tickets again`.
13. In `pipeline/tui/app.py`, change the module docstring line "Eight keys along the bottom." to "Ten keys along the bottom." and add one sentence there: `f` shows the `done` and `rejected` tickets the tree hides by default, and `escalated` is never hidden.
14. In `README.md`, add `f` finished to the key list on line 249, and add one sentence after the paragraph that ends "tamper detection.": the tree hides `done` and `rejected` tickets, opens the cursor on the first ticket that is not terminal, `f` brings the hidden ones back, and `escalated` is never hidden; commit as `docs(TICKET-060): document the f key and the hidden finished tickets`.
15. Run `uv run --group dev pytest -q tests/test_tui.py tests/test_cli.py tests/test_stages.py` -- `tests/test_cli.py` and `tests/test_stages.py` both read `README.md` for drift -- and expect `0 failed`; commit any fix that run demands.

## Acceptance criteria

1. `uv run --group dev pytest -q tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` passes: the first row of the tree is `TICKET-060 implementing *` while the `ls` answer still carries 50 `done` tickets.
2. `tests/test_tui.py::test_the_cursor_opens_on_a_live_ticket` passes:
   `app.selected` is the `awaiting-approval` ticket after mount, not `None`.
3. `tests/test_tui.py::test_the_f_key_toggles_finished_tickets_back_into_the_tree`
   passes: `f` paints all four rows in id order, a second `f` hides `done` and
   `rejected` again, `escalated` shows in both states, and the status line
   reads `2 finished hidden (f)` while they are hidden.
4. `tests/test_tui.py::test_the_down_key_moves_the_cursor_off_the_opening_row`
   passes: one `down` press moves `app.selected` from `TICKET-001` to
   `TICKET-002`, so an arrow key still drives the tree.
5. `tests/test_tui.py::test_a_selected_ticket_stays_in_the_tree_when_it_finishes`
   passes: the row under the cursor stays painted after it transitions to
   `done`, and `app.selected` is unchanged.
6. `tests/test_tui.py::test_an_event_reseeds_the_tree_and_a_dropped_marker_says_so`
   still passes: an `escalated` ticket is still the only row of the tree.
7. `uv run --group dev pytest -q tests/test_tui.py tests/test_cli.py tests/test_stages.py`
   reports `0 failed`.

## Decisions

**The TUI tree hides `done` and `rejected`, and never hides `escalated`.**
`FINISHED = TERMINAL - {"escalated"}` in `pipeline/tui/app.py`. An escalated
ticket is terminal, but it is the one terminal stage a human must open, and
`tests/test_tui.py::test_an_event_reseeds_the_tree_and_a_dropped_marker_says_so`
asserts it stays on screen. Hidden is not gone: `f` paints them all, and the
status line carries the hidden count, so the operator can see that rows exist
off the tree.

**The selected row is painted even when it is finished.** `_visible()` keeps
`self.selected` whatever its stage. Without that exception, a ticket that
reaches `done` while you read its log takes its own row out from under the
cursor, and `_show()` loses the pane you were watching.

**The cursor moves only when a repaint could not restore `self.selected`.**
`_paint()` runs every 5s. Moving the cursor on a repaint that did restore the
selection is what the docstring of `_paint()` calls "the difference between a
dashboard and a toy".

**`move_cursor()` needs the tree lines built first.** A leaf added in this
repaint has `_line == -1`, and `Tree.validate_cursor_line` clamps that to line
0 -- the root. Reading `tree.last_line` forces the build and gives every new
leaf its line. Delete that read and the cursor goes to the root instead of to
the ticket, silently, which is what it did before this ticket. If a textual
upgrade breaks the read, `self.call_after_refresh(tree.move_cursor, first)` is
the replacement; `move_cursor_to_line()` is not, because it indexes the same
unbuilt `_tree_lines`.

**One test presses an arrow key at the tree, and it is the only one.**
`test_the_down_key_moves_the_cursor_off_the_opening_row` seeds two live rows
for that reason: with one row the cursor already sits on it, `watch_cursor_line`
returns early, and no highlight fires -- which is why the other eight tests
select by node through `select()` instead. Delete that test and nothing checks
that the tree still answers the keyboard.

## Rollback

Revert the commits from steps 2 to 15 on `ticket/060`. `pipeline/tui/app.py`,
`tests/test_tui.py` and `README.md` are the only files touched, no data
migrates, and nothing outside `pipeline tui` reads any of it -- the daemon,
`ticket_rows()` and every CLI command are unchanged. The revert restores a tree
that paints every ticket in id order with the cursor on the root, which is the
behaviour this ticket reports.

## Thread

### 2026-08-26 15:27:52Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-26 · triage · reproduced

Reproduced. `_paint()` (`pipeline/tui/app.py:280-292`) sorts all rows by id
with no filter, so `done`/`rejected`/`escalated` tickets sort ahead of a
later-id live ticket and bury it. Added
`tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones`, committed
on `ticket/060` (836cf28). Fails as expected: tree's first row is
`TICKET-001 done` instead of the live `TICKET-060`.

This needs a design choice (hide-behind-toggle vs. reorder vs. both, per the
ticket's own suggestion) and touches cursor-restore behavior in `_paint()`
that must not regress -- routing to `ok`, not `chore`.

### 2026-08-26 15:29:01Z · triage · session · session=5d57c201-b2e0-4204-b03e-73c4b5fbe4b1

`triage` ran as session `5d57c201-b2e0-4204-b03e-73c4b5fbe4b1`
- replay: `claude --resume 5d57c201-b2e0-4204-b03e-73c4b5fbe4b1`
- log: `.project/logs/TICKET-060-triage-5d57c201.log`

### 2026-08-26 15:29:01Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced: _paint() sorts by id only, no terminal filter; added failing tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones

### 2026-08-26 · planning · plan written

Plan written: hide `done` and `rejected` behind a new `f` key, keep
`escalated` and the selected row painted, and move the cursor to the first
non-terminal ticket when a repaint cannot restore `self.selected`. 13 steps,
three files: `pipeline/tui/app.py`, `tests/test_tui.py`, `README.md`.

Two findings the ticket did not carry:

1. `_paint()` does not restore the cursor today. `tree.move_cursor(leaf)` runs
   on a leaf added in the same tick, whose `_line` is still `-1`, and
   `Tree.validate_cursor_line` clamps `-1` to line 0 -- the root. Measured on
   textual 8.2.8. Step 8 reads `tree.last_line` first, which forces the build.
2. Moving the cursor at mount disarms `await pilot.press("down", "down")` in
   eight existing tests, and the four pty ones would then never attach. Steps
   1 and 2 replace that navigation with a `select()` helper before any
   behaviour changes.

Noted, not fixed: the `daemon: cannot read from timed out object` toast the
ticket puts out of scope, and the module docstring saying "Eight keys" while
`BINDINGS` holds nine -- step 11 corrects it to ten as part of this change.

### 2026-08-26 16:50:50Z · planning · session · session=17b91db6-0d80-4d5b-9192-e4d44a0d24fd

`planning` ran as session `17b91db6-0d80-4d5b-9192-e4d44a0d24fd`
- replay: `claude --resume 17b91db6-0d80-4d5b-9192-e4d44a0d24fd`
- log: `.project/logs/TICKET-060-planning-17b91db6.log`

### 2026-08-26 16:50:50Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: hide done/rejected behind a new f key, pin the selected row, open the cursor on the first non-terminal ticket; 13 steps, 3 files

### 2026-08-26 17:05:08Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails as required
```
^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    async def go():
        rows = [row("/tmp/alpha", f"TICKET-{n:03d}", "done")
                for n in range(1, 51)]
        rows.append(row("/tmp/alpha", "TICKET-060", "implementing",
                        running=True))
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            got = labels(app)["alpha"]
>           assert got[0].startswith("TICKET-060"), got[:3]
E           AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7fbbd7d568f0>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7fbbd7d568f0> = 'TICKET-001 done'.startswith

tests/test_tui.py:110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.22s ===============================

```
- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails on base `main` too -- the bug is not already fixed upstream
```
001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7f120e6d55b0>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7f120e6d55b0> = 'TICKET-001 done'.startswith

tests/test_tui.py:110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.60s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-2wnsyjoj/base
      Built pipeline @ file:///tmp/pipeline-base-2wnsyjoj/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-27 · plan-validation · judgement · verdict=FAIL

Two items fail; the other six pass.

**Riskiest step -- fail.** The plan names no riskiest step and states no
fallback for one. Step 8 is it: `tree.last_line` forcing the line build is
measured against textual 8.2.8, and `_tree_lines` is what makes it work
(`textual/widgets/_tree.py:1240`, `if self._tree_lines_cached is None:
self._build()`). State what step 8 does if that read stops placing the cursor.

**Regression surface -- fail.** Step 2 deletes the only coverage of arrow-key
navigation. `tests/test_tui.py:161-162` presses `down`, `down` and then asserts
`app.selected == (str(d), "TICKET-001")`; after step 2 no test presses an arrow
key at the tree. Add one step: a test that `down` moves the cursor off the
opening row.

Passing, with reasons:

1. Root cause -- `_paint()` filters no stage, and its `move_cursor(leaf)` runs
   on a leaf whose `_line` is `-1`. Steps 6-8 fix both.
2. Decisions -- DEC-011 line 144 bars protocol surface; `f` adds no op.
   DEC-021 wants the count in `_status()`; step 10 puts it there.
3. Scope -- every step traces to a criterion. Step 11's "Eight keys" is stale
   in the file the ticket already edits.
4. Criteria -- 2, 3 and 4 each name a value a wrong implementation returns.
5. No research left -- every step names a file, a function and literal code.
6. Blast radius -- `class: feature`, three files, 13 steps.

Checked, no finding: `tail_log()` catches `OSError`
(`pipeline/tui/app.py:159`), so the mount-time `_show()` the new cursor fires
is safe on a `/tmp/alpha` that does not exist. No existing test seeds a `done`
or `rejected` row. Both `status(app)` assertions use `in`, so the appended
hidden count breaks neither.

### 2026-08-26 17:08:48Z · plan-validation · session · session=4a4dc132-5309-4000-b392-2f321122c1aa

`plan-validation` ran as session `4a4dc132-5309-4000-b392-2f321122c1aa`
- replay: `claude --resume 4a4dc132-5309-4000-b392-2f321122c1aa`
- log: `.project/logs/TICKET-060-plan-validation-4a4dc132.log`

### 2026-08-26 17:08:48Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ plan fails 2 of 8 items: no riskiest step or fallback for step 8's tree.last_line read, and step 2 drops the only arrow-key navigation coverage; the other six pass

### 2026-08-27 · planning · plan revised

Plan revised after plan-validation failed two of eight items. 15 steps, the
same three files.

1. Riskiest step, with a fallback. Step 9 is the riskiest step: the cursor
   placement rests on `tree.last_line` forcing the line build
   (`textual/widgets/_tree.py:1241`, `if self._tree_lines_cached is None:
   self._build()`). Step 10 is its fallback -- drop that read and the direct
   `tree.move_cursor(first)`, write `self.call_after_refresh(tree.move_cursor,
   first)` (`textual/message_pump.py:451`), and stop and report if the cursor
   still lands on the root. `move_cursor_to_line()` is not a second fallback:
   it indexes the same unbuilt `_tree_lines`.
2. Arrow-key coverage restored. New step 5 adds
   `test_the_down_key_moves_the_cursor_off_the_opening_row` to
   `tests/test_tui.py`: two live rows, and one `down` press must move
   `app.selected` from TICKET-001 to TICKET-002. One row cannot test it --
   the cursor already sits there and no highlight fires. Old steps 5 to 13
   are now 6 to 15, and new criterion 4 names that test.

Unchanged: the `f` key, `FINISHED = TERMINAL - {"escalated"}`, the
selected-row exception, and the four decisions cited.

### 2026-08-26 17:46:08Z · planning · session · session=84b4a387-6951-4afc-827e-441a5a5d90f6

`planning` ran as session `84b4a387-6951-4afc-827e-441a5a5d90f6`
- replay: `claude --resume 84b4a387-6951-4afc-827e-441a5a5d90f6`
- log: `.project/logs/TICKET-060-planning-84b4a387.log`

### 2026-08-26 17:46:08Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan revised: step 9 named riskiest with step 10 as its call_after_refresh fallback, and new step 5 restores arrow-key coverage; 15 steps, 3 files

### 2026-08-26 19:10:12Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails as required
```
^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    async def go():
        rows = [row("/tmp/alpha", f"TICKET-{n:03d}", "done")
                for n in range(1, 51)]
        rows.append(row("/tmp/alpha", "TICKET-060", "implementing",
                        running=True))
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            got = labels(app)["alpha"]
>           assert got[0].startswith("TICKET-060"), got[:3]
E           AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7ff8c2cba530>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7ff8c2cba530> = 'TICKET-001 done'.startswith

tests/test_tui.py:110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.22s ===============================

```
- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails on base `main` too -- the bug is not already fixed upstream
```
01 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7f1557aa05b0>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7f1557aa05b0> = 'TICKET-001 done'.startswith

tests/test_tui.py:110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.59s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-snp7k5he/base
      Built pipeline @ file:///tmp/pipeline-base-snp7k5he/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-27 · plan-validation · judgement · verdict=PASS

All eight items pass. The two items the last round failed are answered.

1. Root cause -- `_paint()` paints every row sorted by id, and its restore
   `move_cursor(leaf)` runs on a leaf whose `_line` is `-1`, which
   `validate_cursor_line` clamps to 0. Steps 7-9 fix both.
2. Decisions -- DEC-011 bars protocol surface; `f` adds no daemon op. DEC-021
   wants the count inside `_status()`; step 12 puts it there. DEC-019 and
   DEC-039 touch no step.
3. Scope -- every step traces to a criterion. Step 13's "Eight keys" is stale
   in a file the ticket already edits.
4. Criteria -- 1 to 6 each name a value a wrong implementation returns.
5. No research left -- every step names a file, a function and literal code.
6. Riskiest step -- step 9 is named, step 10 is its fallback, and step 10 stops
   and reports if `call_after_refresh` also lands the cursor on the root.
   Checked against the installed textual 8.2.8: `last_line` is
   `len(self._tree_lines) - 1` (`textual/widgets/_tree.py:845`) and
   `move_cursor` reads `node._line` (line 972).
7. Regression surface -- the eight `press("down", "down")` sites all use `d`
   and `TICKET-001`, so step 2's substitution is uniform. Step 5 restores the
   arrow key. Criterion 6 pins `escalated`. The one `status(app)` assertion
   (`tests/test_tui.py:141`) uses `in`, so the appended count leaves it passing.
8. Blast radius -- `class: feature`, three files, 15 steps.

long: three notes for implementing, none blocking.

- Step 13 rewrites line 4 to "Ten keys" and leaves line 6, "Only one of those
  eight needs a daemon op", stale. That line is stale today: `BINDINGS` holds
  nine keys and README line 250 says `k` and `i` are both daemon ops.
- Step 9 makes the restore work, so `on_tree_node_highlighted` now fires on a
  repaint that moves the selected row's line index, and `_show()` clears the
  RichLog and re-tails it. A label-only change keeps the index and fires
  nothing: `remove_children()` only calls `_invalidate()`
  (`textual/widgets/_tree.py:508`) and leaves `cursor_line` set. `_pty()`
  guards on `self.attached` (`pipeline/tui/app.py:412`), so no re-attach. No
  test covers this.
- No criterion fails if step 9's `not in TERMINAL` clause is dropped. The only
  painted terminal row in the new tests is `TICKET-003 escalated` in step 4,
  and that test asserts labels and status, never `app.selected`. One line in
  step 4 -- `assert app.selected == ("/tmp/alpha", "TICKET-004")` -- would
  falsify the clause.

### 2026-08-26 19:15:16Z · plan-validation · session · session=8a4db4ef-a70d-4222-9684-be392120a739

`plan-validation` ran as session `8a4db4ef-a70d-4222-9684-be392120a739`
- replay: `claude --resume 8a4db4ef-a70d-4222-9684-be392120a739`
- log: `.project/logs/TICKET-060-plan-validation-8a4db4ef.log`

### 2026-08-26 19:15:16Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items: root cause named, step 9 riskiest with step 10 as fallback, step 5 restores arrow-key coverage; three non-blocking notes recorded

### 2026-08-26 19:15:36Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-26 19:15:54Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails as required
```
^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    async def go():
        rows = [row("/tmp/alpha", f"TICKET-{n:03d}", "done")
                for n in range(1, 51)]
        rows.append(row("/tmp/alpha", "TICKET-060", "implementing",
                        running=True))
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            got = labels(app)["alpha"]
>           assert got[0].startswith("TICKET-060"), got[:3]
E           AssertionError: ['TICKET-001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7f6f0c0aeeb0>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7f6f0c0aeeb0> = 'TICKET-001 done'.startswith

tests/test_tui.py:110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================

```
- ok: `tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones` fails on base `main` too -- the bug is not already fixed upstream
```
001 done', 'TICKET-002 done', 'TICKET-003 done']
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7fa0b6da4cb0>('TICKET-060')
E            +    where <built-in method startswith of str object at 0x7fa0b6da4cb0> = 'TICKET-001 done'.startswith

tests/test_tui.py:110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_finished_tickets_do_not_bury_live_ones - Asser...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.64s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-nrjropxe/base
      Built pipeline @ file:///tmp/pipeline-base-nrjropxe/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-26 19:15:54Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-27 · implementing · todo

1. [x] add `select()` helper to `tests/test_tui.py`
2. [x] replace the 8 `press("down", "down")` sites with `select()`, commit
3. [x] add `test_the_cursor_opens_on_a_live_ticket`
4. [x] add `test_the_f_key_toggles_finished_tickets_back_into_the_tree`
5. [x] add `test_the_down_key_moves_the_cursor_off_the_opening_row`
6. [x] add `test_a_selected_ticket_stays_in_the_tree_when_it_finishes`, commit the 4 new tests
7. [x] `app.py`: import `TERMINAL`, add `FINISHED`, `self.show_finished`, `_visible()`
8. [x] `app.py`: group only visible rows in `_paint()`, commit
9. [x] `app.py`: fix cursor-restore block in `_paint()` (riskiest step), commit
10. [x] skipped: step 9's `last_line` read worked, both live-cursor tests passed
11. [x] add `f` binding + `action_finished()`
12. [x] add hidden count to `_status()`, commit
13. [x] update module docstring "Eight keys" -> "Ten keys" + one sentence
14. [x] `README.md`: add `f` to key list + one sentence, commit
15. [x] ran full test_tui/test_cli/test_stages: 73 passed, no drift, nothing to fix

### 2026-08-27 · implementing · report

Plan executed as written, 7 commits on `ticket/060`: `a6d02d3`, `a342ade`,
`d2c541f`, `bf8b5fa`, `216a5b8`, `0cfd0c6` (docs bundles steps 13+14, no
separate commit was named for the docstring alone).

Step 9's `tree.last_line` read worked against installed textual, so step 10's
`call_after_refresh` fallback was not needed.

One checkpoint in the plan did not hold exactly as stated: step 8 named
`test_a_selected_ticket_stays_in_the_tree_when_it_finishes` as passing after
that step alone, but it stayed red (`assert None == (d, "TICKET-001")`) until
step 9 placed the cursor on mount. Both tests are green after step 9; this
did not change any step or require a different approach.

`uv run --group dev pytest -q tests/test_tui.py tests/test_cli.py
tests/test_stages.py`: `73 passed`. All 7 acceptance criteria verified by
name. Working tree clean.

### 2026-08-26 19:21:14Z · implementing · session · session=dfc09587-8065-4040-8d8e-ef41b7e296bb

`implementing` ran as session `dfc09587-8065-4040-8d8e-ef41b7e296bb`
- replay: `claude --resume dfc09587-8065-4040-8d8e-ef41b7e296bb`
- log: `.project/logs/TICKET-060-implementing-dfc09587.log`

### 2026-08-26 19:21:14Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented the plan's 15 steps as written; the f key hides finished tickets, cursor opens on the first live one, all 7 acceptance criteria pass (73 passed)

### 2026-08-27 · review · findings

**review: pass, no blocking findings.** Reviewed the whole delta,
`git diff main...HEAD` over 7 commits: `pipeline/tui/app.py` (+49/-8),
`tests/test_tui.py` (+136), `README.md` (+6/-2).

Verified: `uv run --group dev pytest -q` -> `322 passed in 13.79s`; the three
files the plan names -> `73 passed`; all 6 criteria tests pass by name. The
working tree is clean.

Two mutation runs show the new tests are not vacuous:

1. `_visible()` without the selected-row exception ->
   `test_a_selected_ticket_stays_in_the_tree_when_it_finishes` fails with
   `AssertionError: assert [] == ['TICKET-001 done']`.
2. `FINISHED = TERMINAL` -> `test_the_f_key_toggles_finished_tickets_back_into_the_tree`
   fails with `At index 0 diff: 'TICKET-004 implementing *' != 'TICKET-003 escalated'`.

Three findings I dropped after refuting them:

1. `grouped[r["project"]]` KeyError -- refuted, `_visible()` returns a subset
   of `rows` and `app.py:305` keys the dict from all of `rows`.
2. `f` steals a keystroke from raw mode -- refuted at `app.py:560`, `on_event`
   intercepts every `events.Key` before bindings dispatch.
3. `escalated` gets hidden -- refuted by mutation run 2 above.

Non-blocking, in severity order:

1. minor: `app.py:8` still reads "Only one of those eight needs a daemon op."
   while `app.py:4` now reads "Ten keys along the bottom." The count was
   already stale on `main` (9 bindings), and step 13 changed only line 4.
2. nit: `tree.last_line` on `app.py:315` is a bare expression; pyright's
   `reportUnusedExpression` flags it. No CI runs pyright, and the comment
   above it explains the read.
3. nit: eight tests traded `press("down", "down")` for `select()`, so
   `test_the_down_key_moves_the_cursor_off_the_opening_row` is the only test
   that drives the tree from the keyboard. The plan chose this.

### 2026-08-26 19:25:37Z · review · session · session=5180a1e3-91d0-4008-bb80-3fdfcb36700f

`review` ran as session `5180a1e3-91d0-4008-bb80-3fdfcb36700f`
- replay: `claude --resume 5180a1e3-91d0-4008-bb80-3fdfcb36700f`
- log: `.project/logs/TICKET-060-review-5180a1e3.log`

### 2026-08-26 19:25:37Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed the 7-commit delta: no blocking findings, 322 passed, 3 refuted, 3 non-blocking notes

### 2026-08-26 19:25:52Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-26 19:25:52Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/060


Current branch ticket/060 is up to date.
Already up to date.
Updating 60715f4..0cfd0c6
Fast-forward
 README.md           |   6 ++-
 pipeline/tui/app.py |  49 +++++++++++++++----
 tests/test_tui.py   | 136 ++++++++++++++++++++++++++++++++++++++++++++++++----
 3 files changed, 174 insertions(+), 17 deletions(-)

```

### 2026-08-26 19:25:52Z · merging · decision

decision recorded as `DEC-060`
