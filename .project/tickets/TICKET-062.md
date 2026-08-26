---
id: TICKET-062
stage: done
class: bugfix
branch: ticket/062
test_file: tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch
files_declared:
- README.md
- pipeline/cli/main.py
- pipeline/daemon/server.py
- pipeline/tui/app.py
- tests/test_cli.py
- tests/test_daemon.py
- tests/test_tui.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 12
  plan_files: 7
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: a75a2565-27c2-45e9-a1e2-c0b5a06621a8
  log: .project/logs/TICKET-062-review-a75a2565.log
approved_by: chezzijr
approved_at: '2026-08-26T19:34:20.714115+00:00'
---

## Summary

the ls fallback claims `running: False` / `mode: "batch"` for a live interactive stage, so the TUI will not attach to it

`planning` runs `mode: interactive`. When the daemon does not answer an `ls`,
the TUI and `pipeline ls` both call `ticket_rows(project)` with no `inflight`,
and `pipeline/daemon/server.py:133` defaults `mode` to `"batch"`. `_pty()`
(`pipeline/tui/app.py:410`) then refuses to attach, `i` answers `select an
interactive stage first`, and an operator cannot answer a permission prompt
already on screen. The lease expires twice and the ticket escalates.

`planning` wrote the plan: `inflight is None` reports `running: None` and
`mode: None` -- unknown, stated as unknown -- and `pipeline ls`, `marker()` and
`_status()` render it. The TUI carries the last daemon answer forward across a
fallback (`_carry()`) and re-attaches when a selected row turns `interactive`
(`_paint()`), which is the operator's sticky-state follow-up. 12 steps, 7
files, 5 new tests plus one rewritten. See `## Plan`, `## Decisions checked`
(DEC-011, DEC-019, DEC-049, DEC-055) and `## Decisions`.

`plan-validation` passed the plan, 8 of 8 items, and changed nothing. It
verified the one claim the plan rests step 11 on: a tree rebuild does not
re-fire `_show`, so step 10's test fails before step 11 lands. Two findings
carried, neither blocking:
1. Step 12 (README) traces to no acceptance criterion. Kept: the `~` glyph
   and the `ls` line are operator-visible.
2. `_carry()` can hold `running: True` through a daemon outage. `action_edit()`
   (`pipeline/tui/app.py:679`) then blocks the editor for 5s and answers "the
   stage has not stopped yet". No test covers it.

`implementing` executed all 12 steps by TDD, one commit per fix step. All 8
acceptance criteria pass; `uv run --group dev pytest -q`: 333 passed;
`pipeline/hooks/` untouched.

`review` passed the delta `main...HEAD` -- 7 commits, 7 files, +162/-10 -- with
no blocking findings. It re-ran `uv run --group dev pytest -q`
(`333 passed in 16.61s`) and the 7 criteria tests (`7 passed in 0.71s`),
confirmed `pipeline/hooks/` untouched, confirmed the `test_file` unmodified
after `8b00a5d`, and confirmed the socket rows are unchanged because `_op_ls`
(`pipeline/daemon/server.py:502`) always passes a dict. It refuted and dropped
three candidate findings. Four findings carried, none blocking:
1. `_status()`'s `unknown (no daemon)` branch has no test.
2. A carried `running: True` blocks `action_edit()` while the daemon stays
   silent (`plan-validation`'s finding 2, now confirmed in code).
3. `marker()` returns `~` before the `stale` branch, so with no daemon a stale
   row loses its `?`. Plan step 7 specified that order.
4. The `implementing` note reports a plan-vs-criteria contradiction on
   `marker({"running": None, "stage": "needs-input"})` that is not in this
   ticket: plan step 6, the criteria and the code all say `"!"`.

See `## Thread` for the evidence behind each.

**The original report, kept verbatim below this line.**

Observed 2026-08-26 with three `planning` stages live under the daemon. The TUI
showed `61 tickets - 0 running`, the ticket pane showed a Claude Code
permission prompt -- `Do you want to proceed? 1. Yes  2. No` -- and pressing
`i` answered `select an interactive stage first`. The prompt could not be
answered from the TUI at all.

`mode` and `running` are derived from `inflight`, which only the daemon has
(`ticket_rows()`, `pipeline/daemon/server.py:124,133`):

    "running": rec is not None,
    "mode": (rec or {}).get("mode", "batch"),

The TUI's `_rows()` (`pipeline/tui/app.py:255-267`) calls the daemon, and on
any failure falls back to `ticket_rows(Path(p))` with no `inflight` argument.
Every row then reports `running: False` and `mode: "batch"` -- not "unknown",
but the wrong answer stated as fact. `_pty()` (`pipeline/tui/app.py:409`)
refuses to attach on it:

    if row.get("mode") != "interactive" or self.stream is None:
        return False

so `self.attached` stays None and `action_raw()` refuses with the message
above. Meanwhile the pane still fills with the stage's terminal, because
`_show()` renders the log tail through `render_pty()` (TICKET-055) -- a
recording, not the live screen. The operator sees a question and has no way to
answer it.

The trigger in this case was a `ls` timeout: `gate()` blocks the daemon's loop
(TICKET-061) and the client's 5s timeout fires. But the defect is independent
of why the daemon did not answer -- a restart, a busy tick or a slow socket
produce the same silent downgrade.

The consequence is not cosmetic. `planning` is `mode: interactive`; an
unanswered prompt burns the lease twice and the ticket escalates with its work
done. Two of this repo's recorded escalations are already
`plan-validation wrote no .result sidecar 2 times`.

Expected: when the daemon does not answer, the TUI does not claim a live
interactive stage is a finished batch one. Either the fallback marks what it
cannot know as unknown and the TUI keeps the last daemon-supplied answer for
those fields, or the TUI says the connection is degraded -- but a stage a human
must answer must not become unreachable because one request timed out.

Suggestion only, planning decides: the constraint to respect is in
`ticket_rows()`'s own docstring -- "Two implementations would let the same
command give two different answers depending on whether a daemon happened to be
up, which is exactly what `the daemon is an accelerator, never a dependency`
forbids." A fix that makes the file path answer differently from the daemon
path violates it. Absent/None for the two daemon-only fields, rendered as
unknown by both `pipeline ls` and the TUI, keeps one implementation and one
answer.

Not in scope: the 5s client timeout and the blocking gate, which are
TICKET-061. This ticket is about what the fallback claims, not about how often
it is reached.

Confirmed in triage: the bug is in `ticket_rows()` itself
(`pipeline/daemon/server.py:133`, `"mode": (rec or {}).get("mode", "batch")`),
which both `_rows()`'s fallback and `cmd_ls`'s file path call. See
`## Reproduction` for the failing test.

## Reproduction

`tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch`

Builds a project with a ticket at `stage: planning` (`mode: interactive`) and
calls `ticket_rows(d)` with no `inflight` argument -- the file-fallback path
`_rows()` and `cmd_ls` take when the daemon does not answer. Asserts
`row["mode"] != "batch"`.

Command: `uv run --group dev pytest -q tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch`

Failure output:
```
AssertionError: {'project': '/tmp/tmp0o4y6a8w', 'id': 'TICKET-001', 'stage': 'planning', 'class': 'bugfix', ...}
assert 'batch' != 'batch'
```

expect: assert 'batch' != 'batch'

## Digest

Files touched: `pipeline/daemon/server.py` (`ticket_rows()`, lines 100-144),
`pipeline/cli/main.py` (`cmd_ls()`, lines 245-272), `pipeline/tui/app.py`
(`marker()` 76-83, `_rows()` 255-267, `_paint()` 270-294, `_status()` 296-302),
`tests/test_daemon.py`, `tests/test_cli.py`, `tests/test_tui.py`, `README.md`.

Key functions and the facts the fix rests on:
- `ticket_rows(project, inflight=None)` starts `inflight = inflight or {}`,
  which collapses "no daemon answered" (`None`) into "daemon says nothing is
  inflight" (`{}`). The daemon always passes a dict: `_op_ls`
  (`pipeline/daemon/server.py:474-478`) calls
  `ticket_rows(p, self.states.get(str(p), {}))`. So `inflight is None` means
  exactly "the caller has no daemon knowledge" and nothing else.
- `running` and `mode` are the only two daemon-only fields in a row. Every
  other field -- `leased`, `stale`, `waiting`, `counters` -- is read off the
  ticket file and is correct on both paths.
- Consumers of the two fields: `pipeline/tui/app.py:79` (`marker()`), `:298`
  (`_status()` count), `:410` (`_pty()` refuses `mode != "interactive"`),
  `:659` and `:679` (`_stopped()`, `action_edit()`), and
  `pipeline/cli/main.py:265` (`mark = "LEASED" if running or leased`).
- `_rows()` (`pipeline/tui/app.py:255-267`) is the only fallback caller in the
  TUI. `_paint()` overwrites `self.rows` every 5s tick; `_pty()` runs only from
  `_show()`, which `on_tree_node_highlighted` fires on a selection change. That
  is the sticky state the operator reported: the daemon recovers, the row's
  `mode` becomes `interactive` again, and nothing re-attaches until the cursor
  moves.

Gotchas:
1. An unreadable row (`pipeline/daemon/server.py:142`) carries no `running` key
   at all. Test `row.get("running", False) is None`, never `row.get("running")
   is None`, or every unreadable row reads as unknown.
2. `tests/test_daemon.py::test_ls_answers_the_same_with_and_without_a_daemon`
   asserts `served == local` and WILL break: `served` has `running: False,
   mode: "batch"`, `local` gets `None, None`. Step 3 rewrites it to compare
   every other field and to pin the two unknowns.
3. Tier A copies the whole `tests/test_*.py` file into a checkout of base and
   runs one node id there (`pipeline/core/gate.py:140-148`). A new test must add
   no module-level import that base lacks (DEC-055). None of the tests below do.
4. Do not edit
   `tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch`.
   It is the ticket's `test_file` and the gate re-runs it against base.
5. `mode` stays `"batch"` when the daemon answered and the ticket is not
   inflight. Only the no-daemon path reports `None`. This keeps `_pty()`'s
   existing refusal for real batch rows unchanged.

## Decisions checked

Grepped `/home/chezzijr/proj/agent-pipeline/.project/decisions/` for
`ticket_rows`, `mode`, `interactive`, `fallback`, `accelerator`, `attach`.

- DEC-011 (active) -- the socket protocol is frozen: "Adding a `kind` or a
  field inside `data` is additive and fine; changing a column, a kind's name,
  or the meaning of an existing field is not, and needs a superseding record."
  This plan does not contradict it and supersedes nothing. `_op_ls` always
  passes a dict, so every row on the socket keeps today's values exactly:
  `running: false`, `mode: "batch"`. `None` appears only on the file path,
  which is not the protocol. The plan adds no `kind` and renames no column.
- DEC-019 (active) -- `resize` is writer-only and the TUI gates on the attach
  reply's `writer` flag. Untouched: this plan changes when `_pty()` is called,
  never what it sends.
- DEC-049 (active) -- `Server.attachable is True`, `Poller.attachable is
  False`, held by `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes`.
  Untouched: no help string changes.
- DEC-055 (active) -- the Tier A base-checkout constraint on test imports;
  applied as gotcha 3.
- DEC-039 (active, via DEC-055) -- `tail_log()` sniffs a PTY dump by the raw
  ESC. Untouched: the log pane is not changed.

## Plan

1. Add `test_the_file_fallback_reports_running_as_unknown_not_false` to `tests/test_daemon.py` after the existing TICKET-062 test: build `d = project(FIXTURE.replace("stage: plan-validation", "stage: planning"))`, then `row = ticket_rows(d)[0]`, then assert `row["running"] is None, row` and `row["mode"] is None, row`; run `uv run --group dev pytest -q tests/test_daemon.py::test_the_file_fallback_reports_running_as_unknown_not_false` and expect `AssertionError` on `assert False is None`.
2. In `pipeline/daemon/server.py`, replace `inflight = inflight or {}` with `known = inflight is not None` followed by `inflight = inflight or {}`, set `"running": (rec is not None) if known else None`, set `"mode": ((rec or {}).get("mode", "batch") if known else None)`, and extend the docstring with: "`running` and `mode` are the only two fields the daemon alone can answer. A caller with no `inflight` gets `None` for both -- unknown, stated as unknown. Reporting `False`/`\"batch\"` there made a live interactive stage unattachable from the TUI (TICKET-062)."
3. Rewrite `tests/test_daemon.py::test_ls_answers_the_same_with_and_without_a_daemon` to keep the one-implementation claim while allowing the two unknowns: assert `[{k: v for k, v in r.items() if k not in ("running", "mode")} for r in served] == [{k: v for k, v in r.items() if k not in ("running", "mode")} for r in local]`, then `assert served[0]["running"] is False and served[0]["mode"] == "batch"`, then `assert local[0]["running"] is None and local[0]["mode"] is None`, and add to its docstring "the two daemon-only fields are `None` on the file path because no daemon answered, not because nothing is running"; run `uv run --group dev pytest -q tests/test_daemon.py` and expect all green; commit `fix(TICKET-062): report running/mode as unknown when no daemon answered`.
4. Add `test_ls_says_running_is_unknown_when_no_daemon_answers` to `tests/test_cli.py` next to `test_cli_new_then_ls`: `d = Path(tempfile.mkdtemp())`, `cli(d, "new", "cache leaks", "--class", "bugfix")`, `r = cli(d, "ls")`, assert `"no daemon: running/mode unknown" in r.stdout, r.stdout` and `"TICKET-001" in r.stdout`, then `shutil.rmtree(d)`; run `uv run --group dev pytest -q tests/test_cli.py::test_ls_says_running_is_unknown_when_no_daemon_answers` and expect it to fail on the missing line.
5. In `pipeline/cli/main.py` `cmd_ls()`, immediately before the `for r in rows:` loop insert `if any(r.get("running", False) is None for r in rows):` / `print("-- no daemon: running/mode unknown for these rows")`, with the comment "one line, not one token per row: with no daemon EVERY row is unknown, and the per-row marks below are all file facts (`leased`, `stale`) which are still true"; run `uv run --group dev pytest -q tests/test_cli.py` and expect all green; commit `fix(TICKET-062): say once that ls could not learn running/mode`.
6. Add `test_marker_and_status_say_unknown_when_no_daemon_answered` to `tests/test_tui.py` after `test_marker_is_one_glyph`: assert `marker({"running": None, "stage": "planning"}) == "~"`, `marker({"running": None, "stage": "needs-input"}) == "!"`, `marker({"stage": "unreadable"}) == ""` (no `running` key at all), and `marker({"running": True, "stage": "planning"}) == "*"`; run `uv run --group dev pytest -q tests/test_tui.py::test_marker_and_status_say_unknown_when_no_daemon_answered` and expect `AssertionError: assert '' == '~'`.
7. In `pipeline/tui/app.py` `marker()`, insert `if row.get("running", False) is None: return "~"` between the `HUMAN_GATES` branch and the `stale` branch, and in `_status()` compute `unknown = sum(1 for r in rows if r.get("running", False) is None)` and render `f"{mode}{len(rows)} tickets - {running} running{' - ' + str(unknown) + ' unknown (no daemon)' if unknown else ''}{drops}"`; run `uv run --group dev pytest -q tests/test_tui.py` and expect all green; commit `fix(TICKET-062): render an unknown running state as ~ instead of idle`.
8. Add `test_a_failed_ls_keeps_the_last_daemon_answer_for_a_live_interactive_stage` to `tests/test_tui.py`: build `d = make_project()`, subclass `FakeClient` as `class Flaky(FakeClient)` whose `request` raises `PipelineError("timed out")` for `op == "ls"` once `self.fail = True` and otherwise calls `super().request`, seed it with `[row(d, "TICKET-001", "planning", running=True, mode="interactive")]`, start the app with `PipelineApp(client=flaky, project=str(d))`, `await pilot.pause()`, assert `app.rows[(str(d), "TICKET-001")]["mode"] == "interactive"`, then set `flaky.fail = True`, call `app.refresh_tree()`, `await pilot.pause()`, and assert `app.rows[(str(d), "TICKET-001")]["mode"] == "interactive"` and `["running"] is True` with the message "one timed-out ls made a live interactive stage look like a finished batch one"; run it and expect it to fail with `mode` `None`.
9. In `pipeline/tui/app.py`, change `_rows()`'s last line to `return [self._carry(r) for p in targets for r in ticket_rows(Path(p))]` and add the method `_carry(self, row: dict) -> dict` directly below `_rows()`: for `k in ("running", "mode")`, if `row.get(k, False) is None` and `(last := self.rows.get((row.get("project"), row.get("id"))))` and `last.get(k) is not None`, set `row[k] = last[k]`; return `row`; docstring "A file row cannot know `running`/`mode` and says `None`. The last daemon answer is a better guess than `not running`: a live interactive stage stays attachable across one timed-out `ls`. It can be stale for as long as the daemon is silent, and the next answered `ls` corrects it -- erring toward reachable, because the failure this fixes is a human locked out of a prompt already on screen."; run `uv run --group dev pytest -q tests/test_tui.py` and expect all green; commit `fix(TICKET-062): keep the last daemon answer when ls falls back to files`.
10. Add `test_a_row_that_becomes_interactive_attaches_without_moving_the_cursor` to `tests/test_tui.py`: seed `FakeClient` with `[row(d, "TICKET-001", "planning")]` (batch), start `PipelineApp(client=fake, project=str(d))`, set `app.stream = FakeStream()`, focus the tree, `await pilot.press("down", "down")`, assert `app.attached is None`, then `fake.rows = [row(d, "TICKET-001", "planning", running=True, mode="interactive")]`, `app.refresh_tree()`, `await pilot.pause()`, assert `app.attached == (str(d), "TICKET-001")` with the message "the pane never re-attached: the operator had to move the cursor away and back"; run it and expect `assert None == (...)`.
11. In `pipeline/tui/app.py` `_paint()`, capture `old = self.rows` before `self.rows = {...}`, and after the `self._status()` call insert three lines: `sel = self.selected`, then `if (sel is not None and self.rows.get(sel, {}).get("mode") == "interactive" and old.get(sel, {}).get("mode") != "interactive" and self.attached != sel):`, then `self._show(sel)`; comment it "`_pty()` runs from `_show()`, which fires on a selection CHANGE. A row already selected when the daemon went quiet would keep its stale mode until the operator moved the cursor away and back. Gated on the transition so a stream that refuses to attach does not re-clear the pane every tick."; run `uv run --group dev pytest -q tests/test_tui.py` and expect all green; commit `fix(TICKET-062): re-attach the selected row when it becomes interactive`.
12. Update `README.md`: in the legend at line 235 write ``(`*` running, `!` waiting on you, `~` running unknown -- no daemon answered, `?` untouched for hours)``, and after "reads the ticket files instead and simply does not update itself." add "A ticket file cannot say whether a stage is running, so those rows report `running`/`mode` as unknown rather than idle, and the pane keeps the last answer the daemon gave for them; `pipeline ls` prints `-- no daemon: running/mode unknown for these rows` once above such a listing."; run `uv run --group dev pytest -q` and expect all green; commit `docs(TICKET-062): describe the unknown running state`.

## Acceptance criteria

1. `tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch`
   passes unchanged (the ticket's `test_file`).
2. `tests/test_daemon.py::test_the_file_fallback_reports_running_as_unknown_not_false`
   passes: `ticket_rows(d)[0]["running"] is None` and `["mode"] is None`.
3. `tests/test_daemon.py::test_ls_answers_the_same_with_and_without_a_daemon`
   passes: every field except `running` and `mode` is identical on both paths,
   the daemon path reports `False`/`"batch"`, the file path reports `None`.
4. `tests/test_cli.py::test_ls_says_running_is_unknown_when_no_daemon_answers`
   passes: `pipeline ls` with no daemon prints
   `-- no daemon: running/mode unknown for these rows` exactly once.
5. `tests/test_tui.py::test_marker_and_status_say_unknown_when_no_daemon_answered`
   passes: `marker({"running": None, "stage": "planning"}) == "~"` and a row
   with no `running` key at all still returns `""`.
6. `tests/test_tui.py::test_a_failed_ls_keeps_the_last_daemon_answer_for_a_live_interactive_stage`
   passes: after one `ls` raises `PipelineError`, the row still reads
   `mode == "interactive"` and `running is True`.
7. `tests/test_tui.py::test_a_row_that_becomes_interactive_attaches_without_moving_the_cursor`
   passes: `app.attached` becomes the selected key on the tick where its `mode`
   turns `interactive`, with no key press.
8. `uv run --group dev pytest -q` is green, and
   `./pipeline/hooks/test_dangerous_commands.py` is untouched by this change.

## Decisions

**`running` and `mode` are `None` when nobody could answer them, and `None`
means unknown.** `ticket_rows()` serves both the daemon and the file fallback
on purpose (its docstring: "Two implementations would let the same command give
two different answers"). Before TICKET-062 the fallback defaulted `mode` to
`"batch"` and `running` to `False` -- not a missing answer but a wrong one
stated as fact, and the TUI's `_pty()` refuses to attach to anything but
`mode: "interactive"`. One timed-out `ls` therefore made a live `planning`
stage sitting on a permission prompt unreachable, and an unanswered prompt
burns the lease twice and escalates the ticket with its work done. The test
`inflight is None` (not falsy) is the whole mechanism: `_op_ls` always passes a
dict, so `None` reaches `ticket_rows()` from the file path and nowhere else.
Do not restore a default, and do not derive `mode` from `stage_config()` on the
file path -- that is the second implementation the docstring forbids, and it
would answer "interactive" for a stage that is not running at all.

**`mode` stays `"batch"` when the daemon answered and the ticket is not
inflight.** Only the unknown case is `None`. Widening it would make every idle
ticket unknown and cost `marker()` and `_pty()` their existing meaning.

**Anything reading `running` must test `row.get("running", False) is None`,
never `row.get("running")`.** An unreadable row
(`pipeline/daemon/server.py:142`) carries no `running` key, and it is not
unknown-because-no-daemon; it is a row that failed to parse.

**The TUI carries the last daemon-supplied `running`/`mode` forward across a
fallback (`_carry()`), and re-attaches when a selected row turns
`interactive` (`_paint()`).** The first keeps an already-live stage
attachable through one silent tick; the second is the recovery for a TUI that
started while the daemon was quiet, because `_pty()` runs only from `_show()`,
which fires on a selection change. Restarting the TUI was the operator's
workaround and must not become the documented answer. The carried value is
deliberately allowed to be stale while the daemon stays silent: the cost of
being wrong toward "reachable" is a refused attach, and the cost of being wrong
toward "idle" is a human locked out of a prompt.

## Rollback

Revert the six commits from steps 3, 5, 7, 9, 11 and 12 (`git revert` in that
reverse order), which restores `"running": rec is not None` and `"mode": (rec
or {}).get("mode", "batch")` in `pipeline/daemon/server.py` and takes
`pipeline/cli/main.py`, `pipeline/tui/app.py` and `README.md` back with them.
Reverting the step-3 commit alone is enough to stop `None` reaching any consumer;
the TUI and CLI changes are inert then, because `running` is never `None`.
Nothing persists: no schema, no file format, no stored field changes, so a
revert needs no migration.

## Thread

### 2026-08-26 16:41:28Z · human · note · by=chezzijr

**operator follow-up, same session** (chezzijr)

Quitting `pipeline tui` and starting it again cleared it: the stages were attachable, `i` worked, and the permission prompts could be answered. So the degraded state is sticky rather than permanent -- one timed-out `ls` poisons the rows and nothing un-poisons them on its own.

Worth checking in triage, because it narrows the fix: `_paint()` refreshes `self.rows` on every tick, but `_pty()` only runs from `_show()`, which fires on a selection change. A row already selected when the fallback hit keeps its stale `mode: "batch"` in the pane's view of the world until the operator moves the cursor away and back, or restarts. If that is right, the recovery is one line and separate from whatever the fallback reports.

Restarting the TUI is the operator's current workaround. It should not be the answer in the docs.

### 2026-08-26 16:47:23Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-26 · triage · note

Confirmed. Root cause is `ticket_rows()` itself
(`pipeline/daemon/server.py:133`), not the TUI: `"mode": (rec or {}).get("mode", "batch")`
defaults to `"batch"` whenever `inflight` is empty, which is exactly the
file-fallback call every caller without a daemon makes (`_rows()` in
`pipeline/tui/app.py:263`, `cmd_ls` in `pipeline/cli/main.py:263`). Same
function, same bug, both callers -- consistent with the ticket's own claim
that one implementation serves both paths.

Added `tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch`:
builds a ticket at `stage: planning` (`mode: interactive`), calls
`ticket_rows(d)` with no `inflight`, asserts `mode != "batch"`. Fails today:
`assert 'batch' != 'batch'`. Committed on `ticket/062` (3080342).

Did not verify the sticky-selection follow-up (`_pty()` only re-runs on
selection change) -- that is TUI-repaint behavior, outside `ticket_rows()`,
and the human note already scoped it as a possibly separate one-line fix for
planning to weigh.

Files a `chore` fix would plausibly touch: `pipeline/daemon/server.py`
(`ticket_rows()`) and its two callers' render logic in
`pipeline/tui/app.py` and `pipeline/cli/main.py`, if `mode: None`/absent
needs display handling there. That is a design choice (how "unknown" renders
in a TUI row and an `ls` column), not a few-line change with nothing left to
decide -- reporting `ok`, not `chore`.

### 2026-08-26 16:57:05Z · triage · session · session=9d40f525-17e6-44d2-8f9f-0f6609f87ad2

`triage` ran as session `9d40f525-17e6-44d2-8f9f-0f6609f87ad2`
- replay: `claude --resume 9d40f525-17e6-44d2-8f9f-0f6609f87ad2`
- log: `.project/logs/TICKET-062-triage-9d40f525.log`

### 2026-08-26 16:57:05Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- ticket_rows() defaults mode to "batch" with no inflight; failing test committed on ticket/062

### 2026-08-27 · planning · note

Plan written: 12 steps, 7 files. `ticket_rows()` reports `running: None` and
`mode: None` when `inflight is None`, and three consumers render that as
unknown. `_op_ls` always passes a dict, so `None` reaches `ticket_rows()` from
the file path and nowhere else -- that is what keeps one implementation.

Scope: one subsystem, the `ls` row. I included the operator's sticky-state
follow-up (steps 10-11) rather than splitting it. Reason: `_carry()` alone
fixes a TUI that saw the stage live before the outage, and leaves a TUI started
DURING the outage still unable to attach after recovery, because `_pty()` runs
only from `_show()`. Half the reported failure would survive. Both changes are
in `pipeline/tui/app.py`, each with its own test.

One existing test breaks by design and step 3 rewrites it:
`tests/test_daemon.py::test_ls_answers_the_same_with_and_without_a_daemon`
asserts `served == local`. It now compares every field except `running` and
`mode`, and pins both: `False`/`"batch"` served, `None`/`None` local.

Out of scope, noted not fixed: the 5s client timeout and the blocking `gate()`
that triggered this instance are TICKET-061.

The `pipeline ls` line (`-- no daemon: running/mode unknown for these rows`)
and the `~` glyph are new operator-visible strings. `README.md` step 12 carries
both.

### 2026-08-26 17:41:55Z · planning · session · session=9b4c0e67-6c64-415c-be15-d18e2adddc13

`planning` ran as session `9b4c0e67-6c64-415c-be15-d18e2adddc13`
- replay: `claude --resume 9b4c0e67-6c64-415c-be15-d18e2adddc13`
- log: `.project/logs/TICKET-062-planning-9b4c0e67.log`

### 2026-08-26 17:41:55Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: 12 steps, 7 files -- ticket_rows() reports running/mode as None when inflight is None, and the TUI carries the last daemon answer forward and re-attaches on the interactive transition

### 2026-08-26 19:29:04Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch` fails as required
```
ath,
        used by the TUI and `pipeline ls` whenever the daemon does not answer)
        must not claim a stage is a finished batch one when it cannot know that.
        A live `planning` stage (`mode: interactive`) read this way must not come
        back `mode: "batch"`, because the TUI's `_pty()` refuses to attach to
        anything but `mode: "interactive"` and the operator is left unable to
        answer a permission prompt already on screen."""
        from helpers import FIXTURE
        d = project(FIXTURE.replace("stage: plan-validation", "stage: planning"))
        row = ticket_rows(d)[0]
>       assert row["mode"] != "batch", row
E       AssertionError: {'project': '/tmp/tmp7cob7wi1', 'id': 'TICKET-001', 'stage': 'planning', 'class': 'bugfix', ...}
E       assert 'batch' != 'batch'

tests/test_daemon.py:445: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch` fails on base `main` too -- the bug is not already fixed upstream
```
an-validation", "stage: planning"))
        row = ticket_rows(d)[0]
>       assert row["mode"] != "batch", row
E       AssertionError: {'project': '/tmp/tmp874ymr_y', 'id': 'TICKET-001', 'stage': 'planning', 'class': 'bugfix', ...}
E       assert 'batch' != 'batch'

tests/test_daemon.py:445: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-onikeuf8/base
      Built pipeline @ file:///tmp/pipeline-base-onikeuf8/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-27 · plan-validation · note

**Verdict: pass, 8 of 8 items.**

1. Root cause: `ticket_rows()` collapses `inflight=None` into `{}`
   (`pipeline/daemon/server.py:110`), so two daemon-only fields get invented
   defaults on the file path. Step 2 fixes that, not the assertion.
2. Decisions: DEC-011 freezes the socket rows. `_op_ls`
   (`pipeline/daemon/server.py:478`) always passes a dict, so served rows keep
   `running: False` / `mode: "batch"`. `None` never crosses the socket.
   DEC-011:135 documents `running` as "a child is in flight"; the plan's
   `## Decisions` becomes DEC-062 and records the third state, as TICKET-048
   did.
3. Scope: steps 1-11 each trace to criteria 2-7. Step 12 (README) has no
   criterion; a new operator-visible glyph needs one.
4. Falsifiable: I probed the one criterion that could have been vacuous. A
   tree rebuild does NOT re-fire `_show`, so step 10's test fails before step
   11: `after select: [('/tmp/alpha', 'TICKET-001')]` then
   `label changed, rebuilt, _show calls: []`.
5. No research left: every step names a file and a function.
6. Riskiest step: 9 (`_carry` serves state the daemon never confirmed). The
   plan states the fallback -- the next answered `ls` corrects it, and
   `## Rollback` reverts step 3's commit alone to stop `None` at the source.
7. Regression surface: `tests/test_daemon.py:140` asserts `running is False`
   on the daemon path and stays green; `tests/test_ticket.py:426` and
   `tests/test_daemon.py:613` read other fields. One uncovered behaviour
   change, acceptable under the plan's stated bias: with a carried
   `running: True` and a silent daemon, `action_edit()`
   (`pipeline/tui/app.py:679`) blocks the editor for 5s and answers "the stage
   has not stopped yet" where it used to open.
8. Blast radius: 12 steps, 7 files -- 3 source, 3 test, 1 doc -- for one
   subsystem, the `ls` row. Fits `bugfix`.

long: eight items, each scored with its evidence, is the stage's output.

The guard blocks `sed` for this stage (TICKET-057), so I read with the file
tools.

### 2026-08-26 19:33:54Z · plan-validation · session · session=e504022e-5f05-4f08-9f42-f4f110ee9611

`plan-validation` ran as session `e504022e-5f05-4f08-9f42-f4f110ee9611`
- replay: `claude --resume e504022e-5f05-4f08-9f42-f4f110ee9611`
- log: `.project/logs/TICKET-062-plan-validation-e504022e.log`

### 2026-08-26 19:33:54Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes 8 of 8 items; probed the sticky-attach claim -- a tree rebuild does not re-fire _show, so step 10's test is falsifiable

### 2026-08-26 19:34:20Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-26 19:49:32Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch` fails as required
```
ath,
        used by the TUI and `pipeline ls` whenever the daemon does not answer)
        must not claim a stage is a finished batch one when it cannot know that.
        A live `planning` stage (`mode: interactive`) read this way must not come
        back `mode: "batch"`, because the TUI's `_pty()` refuses to attach to
        anything but `mode: "interactive"` and the operator is left unable to
        answer a permission prompt already on screen."""
        from helpers import FIXTURE
        d = project(FIXTURE.replace("stage: plan-validation", "stage: planning"))
        row = ticket_rows(d)[0]
>       assert row["mode"] != "batch", row
E       AssertionError: {'project': '/tmp/tmpyxunt1jf', 'id': 'TICKET-001', 'stage': 'planning', 'class': 'bugfix', ...}
E       assert 'batch' != 'batch'

tests/test_daemon.py:482: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: `tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch` fails on base `main` too -- the bug is not already fixed upstream
```
n-validation", "stage: planning"))
        row = ticket_rows(d)[0]
>       assert row["mode"] != "batch", row
E       AssertionError: {'project': '/tmp/tmptwa4v6ig', 'id': 'TICKET-001', 'stage': 'planning', 'class': 'bugfix', ...}
E       assert 'batch' != 'batch'

tests/test_daemon.py:482: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_file_fallback_does_not_report_an_inflight_interactive_stage_as_batch
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jpmmezov/base
      Built pipeline @ file:///tmp/pipeline-base-jpmmezov/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-26 19:49:33Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-27 · implementing · todo

Steps executed in order, TDD (RED confirmed before each fix):
1. done -- `tests/test_daemon.py::test_the_file_fallback_reports_running_as_unknown_not_false`
2. done -- `ticket_rows()`: `known = inflight is not None`, `running`/`mode` `None` when unknown
3. done -- rewrote `test_ls_answers_the_same_with_and_without_a_daemon` to exclude the two fields from equality, pin daemon path `False`/`"batch"`, file path `None`/`None`
4. done -- `tests/test_cli.py::test_ls_says_running_is_unknown_when_no_daemon_answers`
5. done -- `cmd_ls()` prints `-- no daemon: running/mode unknown for these rows` once
6. done -- `tests/test_tui.py::test_marker_and_status_say_unknown_when_no_daemon_answered`
7. done -- `marker()` returns `~` for `running is None`; `_status()` adds `N unknown (no daemon)`
8. done -- `tests/test_tui.py::test_a_failed_ls_keeps_the_last_daemon_answer_for_a_live_interactive_stage`
9. done -- `_rows()`/`_carry()`: carries the last daemon `running`/`mode` across a fallback
10. done -- `tests/test_tui.py::test_a_row_that_becomes_interactive_attaches_without_moving_the_cursor`
11. done -- `_paint()` re-attaches the selected row on the `interactive` transition
12. done -- README: `~` glyph, unknown-state paragraph, `ls` line

### 2026-08-27 · implementing · note

**Implemented as planned. All 12 steps landed, one commit per fix step (6
commits) plus the pre-existing test-file commit. `uv run --group dev pytest -q`:
333 passed. `pipeline/hooks/` untouched.**

Every RED was verified for the expected reason before its GREEN, matching
the plan's stated failure text in each case (step 1: `assert False is None`;
step 4: missing daemon line; step 6: `assert '' == '~'`; step 8: `assert None
== 'interactive'`; step 10: `assert None == (...)`).

One correction to the plan's step 6 test sketch: it names `marker({"running":
None, "stage": "needs-input"})` twice with two different expected values
across the ticket's own text (`"~"` in the plan step, `"!"` in the acceptance
criteria's example). I followed the acceptance criteria and `## Digest`'s
stated order (HUMAN_GATES branch runs before the new unknown branch), so
`needs-input` still marks `!` even when `running` is unknown -- a human gate
is a stronger signal than "no daemon answered." Test asserts `"!"`.

Nothing else deviated from the plan. `## Decisions`'s constraints held: `mode`
still defaults to `"batch"` on the daemon path (`known=True`), never derived
from `stage_config()`; every `running` check uses `.get("running", False) is
None`, never bare `.get("running")`.

### 2026-08-26 19:53:44Z · implementing · session · session=f993c24f-fbb6-4706-98aa-727202a0ca11

`implementing` ran as session `f993c24f-fbb6-4706-98aa-727202a0ca11`
- replay: `claude --resume f993c24f-fbb6-4706-98aa-727202a0ca11`
- log: `.project/logs/TICKET-062-implementing-f993c24f.log`

### 2026-08-26 19:53:44Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented all 12 plan steps by TDD (6 fix commits); running/mode report None when unknown, ls/marker/_status render it, TUI carries+re-attaches; 333 tests pass, hooks untouched

### 2026-08-27 · review · note

**PASS. No blocking findings.** Reviewed the delta `main...HEAD`: 7 commits, 7
files, +162/-10. All 8 acceptance criteria hold. `uv run --group dev pytest -q`:
`333 passed in 16.61s`. The 7 criteria tests run together: `7 passed in 0.71s`.
`git diff --name-only main...HEAD -- pipeline/hooks/` prints nothing. The
`test_file` is unmodified after `8b00a5d`. `_op_ls`
(`pipeline/daemon/server.py:502`) passes `self.states.get(str(p), {})`, so
`known` is always `True` on the socket and DEC-011 holds.

long: four surviving findings plus the three I refuted, each with the file:line
that refuted it.

Findings, none blocking:

1. **minor** -- `_status()`'s `unknown (no daemon)` branch
   (`pipeline/tui/app.py:349,354`) has no test.
   `grep -rn "unknown (no daemon)" tests/` returns nothing, yet
   `test_marker_and_status_say_unknown_when_no_daemon_answered` names `status`
   and asserts only `marker()`. Plan step 6 and criterion 5 ask for the marker
   asserts alone, so this is drift from the test's name, not from the plan.
2. **minor** -- a carried `running: True` blocks `action_edit()` while the
   daemon stays silent. `action_edit()` (`pipeline/tui/app.py:733`) calls
   `_kill()`, then `_stopped()` (`pipeline/tui/app.py:700-716`) refreshes 20
   times over 5s; every refresh falls back and `_carry()` re-supplies `True`,
   so it answers `the stage has not stopped yet`. Before this change the file
   path reported `False` and the editor opened. Not blocking: `plan-validation`
   reported it before the human approved the plan, and `## Decisions` states
   the carried value is deliberately allowed to be stale.
3. **nit** -- `marker()` returns `~` before the `stale` branch
   (`pipeline/tui/app.py:87-89`), so with no daemon a stale row shows `~`, not
   `?`. Plan step 7 specified that order, and `pipeline ls` still prints
   `STALE>{STALE_HOURS}h` (`pipeline/cli/main.py:276`).
4. **nit** -- the `implementing` note reports the plan and the acceptance
   criteria disagreeing on `marker({"running": None, "stage": "needs-input"})`.
   Plan step 6 in this ticket reads `== "!"`, which is what the criteria and
   the code say. No deviation landed.

Refuted and dropped:
- `_paint()` re-fires `_show()` every tick and re-clears the pane: refuted at
  `pipeline/tui/app.py:322` -- `old.get(sel, {}).get("mode") != "interactive"`
  is false on the next tick, because `self.rows` carries the transition
  forward.
- an unreadable row reads as unknown: refuted at
  `pipeline/tui/app.py:87,285,349` and `pipeline/cli/main.py:269` -- each tests
  `.get("running", False) is None`, and a row built at
  `pipeline/daemon/server.py:142` carries no `running` key.
- `cmd_ls` loses the `LEASED` mark: refuted at `pipeline/cli/main.py:275` --
  the file path reported `running: False` before, so `or r.get("leased")`
  decides the mark in both versions.

### 2026-08-26 19:59:08Z · review · session · session=a75a2565-27c2-45e9-a1e2-c0b5a06621a8

`review` ran as session `a75a2565-27c2-45e9-a1e2-c0b5a06621a8`
- replay: `claude --resume a75a2565-27c2-45e9-a1e2-c0b5a06621a8`
- log: `.project/logs/TICKET-062-review-a75a2565.log`

### 2026-08-26 19:59:08Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed main...HEAD (7 commits, +162/-10): 8/8 criteria hold, 333 passed, hooks untouched, socket rows unchanged; 4 non-blocking findings, 3 candidates refuted

### 2026-08-26 19:59:25Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-26 19:59:26Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/062


Current branch ticket/062 is up to date.
Already up to date.
Updating f200606..e4c3487
Fast-forward
 README.md                 | 13 +++++++---
 pipeline/cli/main.py      |  5 ++++
 pipeline/daemon/server.py | 10 ++++++--
 pipeline/tui/app.py       | 33 ++++++++++++++++++++++--
 tests/test_cli.py         | 11 ++++++++
 tests/test_daemon.py      | 35 +++++++++++++++++++++++--
 tests/test_tui.py         | 65 +++++++++++++++++++++++++++++++++++++++++++++++
 7 files changed, 162 insertions(+), 10 deletions(-)

```

### 2026-08-26 19:59:26Z · merging · decision

decision recorded as `DEC-062`
