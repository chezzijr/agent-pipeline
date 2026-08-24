---
id: TICKET-048
stage: done
class: feature
branch: ticket/048
test_file: tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one
files_declared:
- pipeline/cli/main.py
- pipeline/core/machine.py
- pipeline/daemon/server.py
- pipeline/daemon/supervisor.py
- tests/test_daemon.py
- tests/test_machine.py
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
  id: cb7808e9-22a4-4c4c-a43c-45250c6dc463
  log: .project/logs/TICKET-048-review-cb7808e9.log
approved_by: chezzijr
approved_at: '2026-08-24T09:06:05.057263+00:00'
---

## Summary

`pipeline ls` does not say why a ticket is waiting, so ordering is
indistinguishable from a hang.

`files_conflict()` (`pipeline/core/machine.py:194`) holds a ticket whose
`files_declared` overlaps an inflight ticket's, and `start()`
(`pipeline/daemon/supervisor.py:570`) returns `(False, None)` without writing
to the ticket. `ticket_rows()` (`pipeline/daemon/server.py:86`) has no field
for a wait reason, so the held ticket's row is byte-identical to an idle one's.
Triage committed the failing test at 2df435f.

Planning answered the open design question: the wait reason is **recorded in
the ticket's frontmatter** under a new non-control key `waiting`, written only
by the dispatcher. See `## Decisions`. The plan adds `conflict_holder()`
(`pipeline/core/machine.py`), `note_wait()` (`pipeline/daemon/supervisor.py`),
a `waiting` row key and `waiting_text()` (`pipeline/daemon/server.py`), and one
mark in `cmd_ls` (`pipeline/cli/main.py`). Tests go in `tests/test_machine.py`
and `tests/test_daemon.py`.

Both gates passed. Tier A: PASS. Tier B: PASS on all eight items, scored
against the code -- the plan fixes the cause, complies with DEC-011 and
DEC-029, and its blast radius (4 source files, 4 commits) matches `bugfix`.

**Implemented as written**, four commits on `ticket/048`: `ac6f91b`
(`conflict_holder()`), `7210abb` (`waiting_text()` and the `waiting` row key),
`1f27e96` (`note_wait()` wired into `start()`), `44218c7` (`cmd_ls` prints
it). All 9 acceptance criteria pass individually; full suite 261 passed, 0
failed; `./pipeline/hooks/test_dangerous_commands.py` passed; working tree
clean. Triage's committed test passes unmodified. Full detail in `## Thread`.

**Review passed with no blocking findings.** Review read
`git diff c84f88f...HEAD` (4 source files, 2 test files, +189/-13) and ran
`tests/test_daemon.py tests/test_machine.py tests/test_dispatch.py
tests/test_cli.py tests/test_tui.py` -- `120 passed in 9.71s`. The code matches
the plan step for step and drifts from it nowhere. Three non-blocking findings
are in `## Thread`: a no-op `frontmatter()` assignment in the new tests, a
`since`/mtime reset when the holder changes, and the TUI not rendering
`waiting`. Review could not run the guard script -- the read-only allowlist
blocks it -- and the delta touches no file under `pipeline/hooks/`.

## Reproduction

`tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one`

Command: `uv run --group dev pytest -q tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one`

Output:
```
AssertionError: a ticket held by files_conflict must say so -- naming the ticket and the file that holds it -- instead of reading identical to an idle ticket's row: {'project': '/tmp/tmpibdw8d8g', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', 'counters': {}, 'lease': {'holder': None, 'expires': None}, 'running': False, 'leased': False, 'stale': False, 'last_session': None, 'mode': 'batch', 'title': 'x'}
1 failed, 0 passed
```

expect: a ticket held by files_conflict must say so -- naming the ticket and the file that holds it -- instead of reading identical to an idle ticket's row

The test builds TICKET-001 at `verifying` with `files_declared: [thing.py]`,
takes its `ticket_rows()` row as the idle baseline, then calls
`supervisor.start()` with an inflight record for a stand-in TICKET-002
declaring the same file. `start()` returns `(False, None)` as designed
(`files_conflict` holds it), but the row `ticket_rows()` builds afterward is
byte-for-byte identical to the idle baseline -- confirming the ticket's
own claim that ordering is indistinguishable from a hang.

## Digest

Files touched: `pipeline/core/machine.py` (`files_conflict` at 194, `CLAIMS`
at 179), `pipeline/daemon/supervisor.py` (`start()` at 461, the conflict check
at 570, `_finish` at 799), `pipeline/daemon/server.py` (`STALE_HOURS` at 47,
`ticket_rows()` at 86), `pipeline/cli/main.py` (`cmd_ls` at 192),
`tests/test_machine.py`, `tests/test_daemon.py`.

Key functions: `files_conflict(meta, inflight_meta) -> bool` returns a bool and
throws the detail away; `start()` calls it with
`[r["meta"].frontmatter() for r in inflight.values()]`, so each inflight record
already carries the holder's `id` and `files_declared`. `ticket_rows()` is the
single source of `ls` rows for both the daemon (`_op_ls`, `server.py:460`,
which passes `inflight`) and the file fallback (`cmd_ls`, `main.py:214`, which
does not).

Entry points: `pipeline ls` -> `cmd_ls` -> daemon `_op_ls` or `ticket_rows()`
directly; `pipeline/tui/app.py:249` calls `ticket_rows()` too and ignores keys
it does not render.

Gotchas found while planning:

1. The committed test calls `ticket_rows(d)` with **no** `inflight`, and its
   holder `TICKET-002` exists only as an in-memory stand-in -- no file on disk.
   A reason derived at read time cannot name it. The reason must be persisted
   by `start()`.
2. `Ticket.load()` puts unknown frontmatter keys in `extra` and
   `frontmatter()` re-emits them, so a new `waiting` key round-trips with no
   schema change. `t.extra["last_session"]` (`supervisor.py:830`) is the
   existing precedent for a dispatcher-written non-control key.
3. `_finish` rebuilds the ticket as `replace(snap, body=agent.body)`, so every
   frontmatter key an agent wrote -- `waiting` included -- is discarded. No
   tamper check is needed and `CONTROL_FIELDS` does not change.
4. `validate_meta` is FENCED (`machine.py:31`, `("validate_meta",)`), so
   validating `waiting` there would park the ticket at `awaiting-merge`.
   `waiting` reaches no shell, only a terminal line, exactly like the
   unvalidated `last_session` and `title` already in the row. Do not touch it.
5. `machine.py` is fenced only on `transition`, `CONTROL_FIELDS` and `FENCED`.
   `files_conflict` sits at 194, below all three, so adding a function beside
   it shifts no fenced line and merges unattended. Do not insert code above
   `transition`.
6. `ticket_rows()` computes `stale` from the file's mtime, so writing the
   ticket every tick would reset the STALE clock forever. `note_wait()`
   therefore writes only when the recorded reason changes.
7. `project()` (`tests/helpers.py`) is not a git repo, so a `start()` that
   passes the conflict check reaches `bail("could not create a worktree")` and
   escalates. That is expected in the clear test; assert on `waiting` only.
8. DEC-011 freezes the event vocabulary. This plan emits no new event kind.

## Decisions checked

Grepped `.project/decisions/` for `files_conflict`, `ticket_rows`, `ls`,
`inflight`, `overlap`, `fallback`, `waiting`, `frontmatter`.

- DEC-011 (active) -- the socket protocol is frozen: adding a field is
  additive and fine, changing an existing field's meaning is not. This plan
  adds the `waiting` key to the `ls` row and changes no existing key.
- DEC-029 (active) -- `files_conflict` is consulted against `inflight` alone,
  and widening it to every non-terminal ticket "is a different change, and
  this plan does not make it". This plan keeps that scope: it reports the
  conflicts `inflight` already produces and adds no new ordering.
- DEC-043 (active) -- `FENCED` fences itself and `machine.py` is fenced by
  symbol, not whole-file. Digest gotcha 5 is how this plan stays unattended.
- DEC-026 (active) -- a chore ticket's `files_declared` is empty until
  `implementing` reports, so a chore ticket may show no wait reason. That is
  the pre-existing ordering gap, not a regression here.
- DEC-016 (active) -- `stage_view()` copies sections, not frontmatter, so
  `waiting` never reaches a stage prompt.

## Plan

1. In `tests/test_machine.py`, add `test_conflict_holder_names_the_first_holder_and_its_file`: assert `M.conflict_holder({"files_declared": ["a.py", "shared.py"]}, [{"id": "TICKET-002", "files_declared": ["b.py"]}, {"id": "TICKET-003", "files_declared": ["shared.py", "a.py"]}]) == ("TICKET-003", "a.py")`, assert it returns `None` for `[]` and for a disjoint holder, and assert `M.files_conflict` still answers `True`/`False` on the same three inputs.
2. Run `uv run --group dev pytest -q tests/test_machine.py` and watch it fail with `AttributeError: module 'pipeline.core.machine' has no attribute 'conflict_holder'`.
3. In `pipeline/core/machine.py`, add `def conflict_holder(meta: dict, inflight_meta: list[dict]) -> tuple[str, str] | None` directly above `files_conflict` (below `CLAIMS`, never above `transition`): it computes `mine = set(meta.get("files_declared") or [])`, loops `for o in inflight_meta`, takes `overlap = mine & set(o.get("files_declared") or [])`, and returns `(str(o.get("id") or "?"), sorted(overlap)[0])` for the first non-empty overlap, else `None`; `sorted(...)[0]` is there so one holder always names the same file.
4. In `pipeline/core/machine.py`, rewrite the body of `files_conflict` as `return conflict_holder(meta, inflight_meta) is not None`, keeping its docstring and adding one line to it: the bool is the ordering decision, the tuple is what `ls` reports.
5. Run `uv run --group dev pytest -q tests/test_machine.py`, expect `passed` with no failures, then commit `feat: conflict_holder names the ticket and file that hold a ticket back`.
6. In `tests/test_daemon.py`, add `test_a_recorded_wait_reason_reaches_the_ls_row`: set `t.extra["waiting"] = {"on": "TICKET-002", "file": "thing.py", "since": "2026-08-24T08:00:00+00:00"}` on TICKET-001 and `t.save()`, then assert `ticket_rows(d)[0]["waiting"]` equals that same dict and that `waiting_text(ticket_rows(d)[0]["waiting"])` starts with `"waiting on TICKET-002 (thing.py)"`.
7. In `tests/test_daemon.py`, add `test_an_unreadable_wait_reason_does_not_break_ls`: set `t.extra["waiting"] = "nonsense"` and `t.save()`, assert `ticket_rows(d)[0]["waiting"] is None`, then assert `waiting_text(None) == ""` and `waiting_text({"on": "TICKET-002", "file": "thing.py"}) == "waiting on TICKET-002 (thing.py)"` -- a missing `since` renders no age.
8. Run `uv run --group dev pytest -q tests/test_daemon.py` and watch both new tests fail with `ImportError: cannot import name 'waiting_text' from 'pipeline.daemon.server'`.
9. In `pipeline/daemon/server.py`, add `def waiting_text(w) -> str` above `ticket_rows()`: return `""` unless `w` is a dict carrying both `on` and `file`; else build `f"waiting on {w['on']} ({w['file']})"`, compute `since = lease_expiry(w.get("since"))` and `m = int((now() - since).total_seconds() // 60)`, and append `f" {m}m"` when `m < 60`, `f" {m // 60}h"` otherwise, appending nothing when `since is None`.
10. In `pipeline/daemon/server.py`, extend the import on line 29 to `from pipeline.core.ticket import Ticket, all_tickets, lease_expiry, now`, with a comment that `lease_expiry()` is reused as this codebase's one total ISO parser because a hand-edited `since` must not raise inside `ls`.
11. In `pipeline/daemon/server.py`, add `"waiting": w if isinstance(w := t.extra.get("waiting"), dict) else None,` to the row dict `ticket_rows()` builds, beside `"last_session"`, with a comment that the value is the dispatcher's last observation and is advisory display only, never read back as control flow.
12. In `pipeline/daemon/server.py`, rewrite the `STALE_HOURS` comment on line 47 (`overlap ordering is silent; surface anything sitting still`) to say that overlap ordering now reports itself in `waiting`, and that this bound still surfaces a ticket sitting still for any other reason.
13. Run `uv run --group dev pytest -q tests/test_daemon.py`, expect the two new tests to pass and `test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one` to be the only failure left, then commit `feat: the ls row carries the wait reason recorded on the ticket`.
14. In `tests/test_daemon.py`, add `test_a_ticket_held_by_files_conflict_names_its_holder`: build the held state exactly as `test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one` builds it, call `supervisor.start(...)`, assert it returned `(False, None)`, then assert `ticket_rows(d)[0]["waiting"]["on"] == "TICKET-002"`, `["file"] == "thing.py"`, and `Ticket.find(d, "TICKET-001").stage == "verifying"` -- recording a wait must not move the ticket.
15. In `tests/test_daemon.py`, add `test_a_repeated_wait_does_not_rewrite_the_ticket`: after that held `start()`, read `(d / ".project/tickets/TICKET-001.md").stat().st_mtime_ns`, call the identical `supervisor.start(...)` again, and assert the mtime is unchanged, because `ticket_rows()` computes `stale` from that mtime and a per-tick write would hide a stuck ticket forever.
16. In `tests/test_daemon.py`, add `test_the_wait_reason_clears_when_the_conflict_clears`: after that held `start()`, call `supervisor.start(d, d / ".project/tickets/TICKET-001.md", harness("fake"), {})` with empty inflight and assert `ticket_rows(d)[0]["waiting"] is None`; say in the docstring that this second call goes on to `bail("could not create a worktree")` because `project()` is not a git repo, and that the assertion is on `waiting` alone.
17. Run `uv run --group dev pytest -q tests/test_daemon.py` and watch the three new tests fail on `row["waiting"]` being `None`.
18. In `pipeline/daemon/supervisor.py`, extend the `pipeline.core.machine` import to include `conflict_holder` and the `pipeline.core.ticket` import to include `now`.
19. In `pipeline/daemon/supervisor.py`, add module-level `def note_wait(t: Ticket, held: tuple[str, str] | None) -> None` above `start()`: for `held is None` it pops `waiting` from `t.extra` and calls `t.save()` only when a key was there; otherwise it returns without writing if the stored dict already carries the same `on` and `file`, and else sets `t.extra["waiting"] = {"on": held[0], "file": held[1], "since": now().isoformat()}` and calls `t.save()`.
20. In `pipeline/daemon/supervisor.py`, replace the conflict check at line 570 with `held = conflict_holder(t.frontmatter(), [r["meta"].frontmatter() for r in inflight.values()])`, then `note_wait(t, held)`, then `if held is not None: return False, None`, keeping the existing `wait, do not fail` comment and adding that the same call clears a stale reason once the holder is gone.
21. Run `uv run --group dev pytest -q tests/test_daemon.py tests/test_machine.py tests/test_dispatch.py`, expect `passed` with no failures including the triage test from 2df435f, then commit `fix: a ticket held by files_conflict records what holds it`.
22. In `tests/test_daemon.py`, add `test_ls_reports_the_wait_reason_with_no_daemon`: build the held state, run `subprocess.run([sys.executable, "-m", "pipeline", "--project", str(d), "ls"], capture_output=True, text=True)`, then assert `returncode == 0` and `"waiting on TICKET-002 (thing.py)" in r.stdout`.
23. Run `uv run --group dev pytest -q tests/test_daemon.py::test_ls_reports_the_wait_reason_with_no_daemon` and watch it fail on the missing substring.
24. In `pipeline/cli/main.py`, add `waiting_text` to the `pipeline.daemon.server` import on line 21 and, in `cmd_ls` right after the existing `mark` expression, set `mark = " ".join(x for x in (mark, waiting_text(r.get("waiting"))) if x)`, so a held ticket prints `waiting on TICKET-002 (thing.py) 3m` and a held ticket older than `STALE_HOURS` prints both marks.
25. Run `uv run --group dev pytest -q tests/test_daemon.py tests/test_machine.py tests/test_dispatch.py tests/test_ticket.py tests/test_tui.py` and `./pipeline/hooks/test_dangerous_commands.py`, expect no failures from either, then commit `feat: pipeline ls prints why a ticket is waiting`.

## Acceptance criteria

1. `tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one` (triage's test, commit 2df435f) passes unmodified.
2. `tests/test_daemon.py::test_a_ticket_held_by_files_conflict_names_its_holder` passes: the held row's `waiting` carries `on == "TICKET-002"` and `file == "thing.py"`, and the ticket's stage is still `verifying`.
3. `tests/test_daemon.py::test_the_wait_reason_clears_when_the_conflict_clears` passes: `row["waiting"] is None` after a `start()` whose inflight set is empty.
4. `tests/test_daemon.py::test_a_repeated_wait_does_not_rewrite_the_ticket` passes: `st_mtime_ns` is unchanged across two identical held `start()` calls.
5. `tests/test_daemon.py::test_ls_reports_the_wait_reason_with_no_daemon` passes: `pipeline --project <d> ls` prints `waiting on TICKET-002 (thing.py)` with no daemon running.
6. `tests/test_daemon.py::test_a_recorded_wait_reason_reaches_the_ls_row` and `tests/test_daemon.py::test_an_unreadable_wait_reason_does_not_break_ls` pass: a dict reaches the row verbatim, a non-dict reads as `None`.
7. `tests/test_machine.py::test_conflict_holder_names_the_first_holder_and_its_file` passes, and the four existing `files_conflict` assertions in `tests/test_machine.py` pass unchanged.
8. `tests/test_daemon.py::test_ls_answers_the_same_with_and_without_a_daemon` passes unmodified, so the daemon row and the file row carry the same `waiting`.
9. `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

**The wait reason is recorded in the ticket's frontmatter, not held in the
dispatcher's memory.** `ticket_rows()` is the single source of `ls` rows and
the file fallback calls it with no `inflight` at all, so a reason derived at
read time can only name holders still on disk -- it cannot name the record
that caused this tick's wait. `start()` is the only code that knows, so it
writes what it saw: `waiting: {on, file, since}`, a new non-control
frontmatter key that round-trips through `Ticket.extra`.

**`waiting` is advisory display, never control flow.** Nothing reads it back
to decide anything; `conflict_holder()` is recomputed from `inflight` every
tick. CLAUDE.md invariant 1 forbids reading control state back from an
agent-writable file, and this key sits in one. An agent's write to it is
discarded anyway: `_finish` rebuilds the ticket as
`replace(snap, body=agent.body)`, taking every frontmatter key from the
pre-spawn snapshot.

**`note_wait()` writes only when the reason changes.** `ticket_rows()`
computes `stale` from the ticket file's mtime, so a save on every tick would
reset the STALE clock forever and hide the exact stuck ticket `ls` exists to
surface. Do not simplify it into an unconditional `t.save()`.

**`since` is recorded because a dead daemon leaves the reason behind.**
`start()` clears `waiting` on the first tick the conflict is gone, so a stale
reason survives only when nothing is ticking. `ls` prints the age beside the
reason rather than claiming the wait is live.

**`waiting` is deliberately not validated in `validate_meta()`.** That symbol
is FENCED, and the value reaches a terminal line, never a shell -- the same
treatment `last_session` and `title` already get in the same row.
`ticket_rows()` drops a non-dict instead, so a hand-edited value cannot break
`ls`.

**Only `files_conflict` reports itself; the merge wait does not.** `start()`
also returns `(False, None)` when another merge is inflight
(`supervisor.py:604`), and that wait stays silent. Same shape, different
ticket. Do not read this record as saying the merge wait was judged
acceptable.

## Rollback

Revert the commits from steps 5, 13, 21 and 25 on `ticket/048`. The change is
additive: `files_conflict()` keeps its signature and its callers, `waiting` is
a frontmatter key nothing reads back, and the `ls` row keeps every key it had.
A revert leaves stray `waiting:` keys in ticket frontmatter; they round-trip
harmlessly through `extra` and can be deleted by hand.

## Thread

### 2026-08-24 08:05:50Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 · triage · note · result=ok

Reproduced. `files_conflict()` at `pipeline/core/machine.py:194` and its
call site `pipeline/daemon/supervisor.py:570` are unchanged from the ticket's
description: `start()` returns `(False, None)` on conflict with no write to
the ticket and no emit. `ticket_rows()` (`pipeline/daemon/server.py:86`) has
no field for a wait reason.

Committed a failing test on this branch:
`tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one`
(commit 2df435f). It asserts the held row differs from the idle row; both are
currently identical, so it fails with the text in `## Reproduction`.

Not a `chore`: the ticket itself asks `## Decisions` to choose whether the
wait reason lives in the ticket frontmatter or only in the dispatcher's
in-memory state, and that choice changes which files the fix touches
(`machine.py` + `ticket.py` schema vs. `supervisor.py` + `server.py` only).
Routing to planning to make that call.

### 2026-08-24 08:46:04Z · triage · session · session=bca2a27b-ee68-4323-b136-84c299ef9b6b

`triage` ran as session `bca2a27b-ee68-4323-b136-84c299ef9b6b`
- replay: `claude --resume bca2a27b-ee68-4323-b136-84c299ef9b6b`
- log: `.project/logs/TICKET-048-triage-bca2a27b.log`

### 2026-08-24 08:46:04Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced files_conflict silently hiding the wait; committed failing test tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one

### 2026-08-24 08:53:18Z · planning · note

Plan written. The open design question is answered in `## Decisions`: the wait
reason is recorded in the ticket's frontmatter as `waiting: {on, file, since}`,
not held in the dispatcher's memory. The deciding fact is in the committed test
-- it calls `ticket_rows(d)` with no `inflight`, and its holder `TICKET-002`
exists only in memory, so nothing derived at read time can name it.

Three things this plan deliberately leaves out, each noted rather than fixed:

1. The merge wait (`pipeline/daemon/supervisor.py:604`) stays silent. It is the
   same silence for a different reason and wants its own ticket.
2. `pipeline/tui/app.py` reads the same rows and will carry the new `waiting`
   key without rendering it. Adding a TUI column is a separate change.
3. No new event kind is emitted. DEC-011 allows one, but a `waiting` event per
   tick would grow the append-only log for a fact `ls` already reports.

### 2026-08-24 08:54:25Z · planning · session · session=520854fa-5867-4433-a31d-4f8668c2d7b1

`planning` ran as session `520854fa-5867-4433-a31d-4f8668c2d7b1`
- replay: `claude --resume 520854fa-5867-4433-a31d-4f8668c2d7b1`
- log: `.project/logs/TICKET-048-planning-520854fa.log`

### 2026-08-24 08:54:25Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: the wait reason is recorded in the ticket's frontmatter as `waiting: {on, file, since}`, surfaced by ticket_rows() and printed by cmd_ls

### 2026-08-24 08:59:31Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one` fails as required
```
iles_conflict must say so -- naming the ticket "
            "and the file that holds it -- instead of reading identical to an "
            f"idle ticket's row: {held_row}")
E       AssertionError: a ticket held by files_conflict must say so -- naming the ticket and the file that holds it -- instead of reading identical to an idle ticket's row: {'project': '/tmp/tmp7uahvc7i', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', 'counters': {}, 'lease': {'holder': None, 'expires': None}, 'running': False, 'leased': False, 'stale': False, 'last_session': None, 'mode': 'batch', 'title': 'x'}
E       assert {'project': '/tmp/tmp7uahvc7i', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', ...} != {'project': '/tmp/tmp7uahvc7i', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', ...}

tests/test_daemon.py:476: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one` fails on base `main` too -- the bug is not already fixed upstream
```
: False, 'last_session': None, 'mode': 'batch', 'title': 'x'}
E       assert {'project': '/tmp/tmpyialqqm6', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', ...} != {'project': '/tmp/tmpyialqqm6', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', ...}

tests/test_daemon.py:476: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-kk3cyspu/base
      Built pipeline @ file:///tmp/pipeline-base-kk3cyspu/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 11ms

```

### 2026-08-24 · plan-validation · note · result=ok

**Tier B: PASS.** Eight items, each scored against the code.

1. Root cause: `files_conflict()` returns a bool, `start()` discards it and
   writes nothing, and the row has no field for it, so the wait leaves no
   trace anywhere. The plan persists the reason at the only point that knows
   it. It fixes the cause, not the assertion.
2. Decisions: DEC-011 says "Adding a `kind` or a field inside `data` is
   additive and fine" -- the plan adds one row key. DEC-029 confirms the
   `inflight`-only scope, which the plan keeps. No uncited decision conflicts.
3. Scope: every step traces to a criterion except step 12, a comment-only
   edit correcting `STALE_HOURS`'s claim that "overlap ordering is silent".
   Accepted.
4. Criteria falsifiable: AC 4 breaks on an unconditional `t.save()`, AC 6
   breaks if a non-dict reaches the row, AC 3 breaks if `waiting` is never
   popped.
5. No research left: every step names a file and a symbol.
6. Riskiest step: 19-20, `note_wait()` writing the ticket inside `start()`.
   Fallback stated: revert commit 21; `files_conflict()` keeps its signature
   and both callers.
7. Regression surface: `files_conflict`'s two callers (AC 7), the three row
   consumers `cmd_ls`, `_op_ls` and `pipeline/tui/app.py:249` (AC 5, AC 8).
8. Blast radius: 4 source files, 4 commits. Matches `bugfix`.

long: four claims I checked in the code rather than took from the plan.

- `FENCED["pipeline/core/machine.py"] == ("transition", "CONTROL_FIELDS",
  "FENCED")`, and `fenced_touches()` intersects hunks with the symbol's `ast`
  span (DEC-031). `files_conflict` at 194 is unfenced; steps 3 and 4 merge
  unattended.
- `validate_meta()` reads six named fields and ignores unknown keys, so a
  `waiting` of any shape passes `t.save()` and `t.errors()`. Step 7 holds.
- `Server.send()` is `json.dumps(obj, default=str)`, so a hand-edited
  `since:` that YAML parses as a datetime serialises instead of raising.
- `t1.frontmatter()["files_declared"] = ["thing.py"]` in triage's test is a
  no-op, because `frontmatter()` returns a fresh dict. Harmless: the fixture
  (`tests/helpers.py:14`) already declares `files_declared: [thing.py]`, so
  the conflict and the AC 2 / AC 5 string are both real.

Two notes for `implementing`, neither blocking:

1. Step 25 omits `tests/test_cli.py`, whose `test_cli_new_then_ls` is the one
   existing test of the `cmd_ls` print path step 24 edits. Its assertions are
   substrings, so it should pass. Run it anyway.
2. `STALE_HOURS` is at `pipeline/daemon/server.py:50`, not 47 as step 12 and
   the digest say. The quoted comment text matches; edit by text, not line.

### 2026-08-24 09:03:27Z · plan-validation · session · session=62ac1408-d4c2-4d41-a457-456e20665063

`plan-validation` ran as session `62ac1408-d4c2-4d41-a457-456e20665063`
- replay: `claude --resume 62ac1408-d4c2-4d41-a457-456e20665063`
- log: `.project/logs/TICKET-048-plan-validation-62ac1408.log`

### 2026-08-24 09:03:27Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B PASS on all eight items: root cause fixed not masked, DEC-011/DEC-029 complied with, blast radius matches bugfix; noted STALE_HOURS is at server.py:50 not 47 and step 25 omits tests/test_cli.py

### 2026-08-24 09:06:05Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 09:08:00Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one` fails as required
```
iles_conflict must say so -- naming the ticket "
            "and the file that holds it -- instead of reading identical to an "
            f"idle ticket's row: {held_row}")
E       AssertionError: a ticket held by files_conflict must say so -- naming the ticket and the file that holds it -- instead of reading identical to an idle ticket's row: {'project': '/tmp/tmpceh3rhmd', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', 'counters': {}, 'lease': {'holder': None, 'expires': None}, 'running': False, 'leased': False, 'stale': False, 'last_session': None, 'mode': 'batch', 'title': 'x'}
E       assert {'project': '/tmp/tmpceh3rhmd', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', ...} != {'project': '/tmp/tmpceh3rhmd', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', ...}

tests/test_daemon.py:476: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one` fails on base `main` too -- the bug is not already fixed upstream
```
: False, 'last_session': None, 'mode': 'batch', 'title': 'x'}
E       assert {'project': '/tmp/tmp79h_oidc', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', ...} != {'project': '/tmp/tmp79h_oidc', 'id': 'TICKET-001', 'stage': 'verifying', 'class': 'bugfix', ...}

tests/test_daemon.py:476: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-czprc0w4/base
      Built pipeline @ file:///tmp/pipeline-base-czprc0w4/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 09:08:00Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 · implementing · note · result=ok

**todo list**

1. [ ] machine.py: test_conflict_holder_names_the_first_holder_and_its_file (RED)
2. [ ] machine.py: add conflict_holder(), rewrite files_conflict() (GREEN), commit
3. [ ] server.py: test_a_recorded_wait_reason_reaches_the_ls_row, test_an_unreadable_wait_reason_does_not_break_ls (RED)
4. [ ] server.py: add waiting_text(), extend import, add "waiting" row key, edit STALE_HOURS comment (GREEN), commit
5. [ ] supervisor.py: test_a_ticket_held_by_files_conflict_names_its_holder, test_a_repeated_wait_does_not_rewrite_the_ticket, test_the_wait_reason_clears_when_the_conflict_clears (RED)
6. [ ] supervisor.py: add note_wait(), wire into start(), extend imports (GREEN), run triage test + full daemon/machine/dispatch suites, commit
7. [ ] main.py: test_ls_reports_the_wait_reason_with_no_daemon (RED)
8. [ ] main.py: import waiting_text, extend mark in cmd_ls (GREEN), run full suite + guard script, commit
9. [x] verify all 9 acceptance criteria

### 2026-08-24 · implementing · note · result=ok

**implementing done.** All 25 plan steps executed as written, four commits on
`ticket/048`:

1. `ac6f91b` -- `conflict_holder()` in `pipeline/core/machine.py`, above
   `files_conflict` (unfenced, below `transition`/`CONTROL_FIELDS`/`FENCED`).
2. `7210abb` -- `waiting_text()` and the `waiting` row key in
   `pipeline/daemon/server.py`; `STALE_HOURS` comment updated.
3. `1f27e96` -- `note_wait()` in `pipeline/daemon/supervisor.py`, wired into
   `start()` in place of the bare `files_conflict()` call.
4. `44218c7` -- `waiting_text` wired into `cmd_ls` in `pipeline/cli/main.py`.

Verified against the code, not assumed:
- All 9 acceptance criteria pass individually (ran each by name).
- Full suite: `uv run --group dev pytest -q` -- 261 passed, 0 failed.
- `./pipeline/hooks/test_dangerous_commands.py` -- "guard: all passed".
- `git status --short` clean; `git diff main...HEAD --stat` touches the 4
  source files the plan named plus their two test files, matching `bugfix`.
- Triage's committed test
  `test_a_ticket_held_by_files_conflict_reads_the_same_as_an_idle_one`
  passes unmodified.

One deviation worth naming: plan steps 15-16
(`test_a_repeated_wait_does_not_rewrite_the_ticket`,
`test_the_wait_reason_clears_when_the_conflict_clears`) pass vacuously before
`note_wait()` exists -- `start()` writes nothing at all pre-fix, which
trivially satisfies "mtime unchanged" and "`waiting is None`". Only
`test_a_ticket_held_by_files_conflict_names_its_holder` fails red on its own
before the fix. Both tests still guard real regressions post-fix (an
unconditional `t.save()`, or a `note_wait` that never clears), so I kept them
as the plan specifies rather than dropping them.

No scope beyond the plan: no refactors, no touched files outside
`files_declared`.

### 2026-08-24 09:12:49Z · implementing · session · session=ec3ee57c-3e44-48c4-9810-b1ec2b25700e

`implementing` ran as session `ec3ee57c-3e44-48c4-9810-b1ec2b25700e`
- replay: `claude --resume ec3ee57c-3e44-48c4-9810-b1ec2b25700e`
- log: `.project/logs/TICKET-048-implementing-ec3ee57c.log`

### 2026-08-24 09:12:49Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Implemented the plan as written across 4 commits: conflict_holder(), waiting_text(), note_wait() wired into start(), and cmd_ls printing the reason; all 9 acceptance criteria and the full 261-test suite plus the dangerous-commands guard pass.

### 2026-08-24 · review · note · result=ok

**No blocking findings.** Reviewed `git diff c84f88f...HEAD`: 4 source files,
2 test files, +189/-13. Ran `uv run --group dev pytest -q tests/test_daemon.py
tests/test_machine.py tests/test_dispatch.py tests/test_cli.py
tests/test_tui.py` -- `120 passed in 9.71s`. Triage's test at 2df435f is
unmodified in the diff and passes.

Findings I dropped after refuting them:

- A hand-edited unquoted `since:` is a YAML `datetime`, not a `str`. It cannot
  raise in `waiting_text()` (`lease_expiry` takes a `datetime`,
  `pipeline/core/ticket.py:43`) and cannot break the daemon's JSON frame
  (`json.dumps(obj, default=str)`, `pipeline/daemon/server.py:209`).
- `conflict_holder` is not fenced. `FENCED` names `transition`,
  `CONTROL_FIELDS` and `FENCED` in `pipeline/core/machine.py:29`, and the new
  function sits below all three.

Surviving findings, none blocking:

1. **minor** -- The three new supervisor tests set
   `t1.frontmatter()["files_declared"] = ["thing.py"]`, which mutates a
   throwaway dict: `frontmatter()` builds a new one per call
   (`pipeline/core/ticket.py:538`). The tests still exercise the conflict,
   because `tests/helpers.py:14` already declares `files_declared: [thing.py]`.
   The line reads as setup and does nothing. It copies triage's test.
2. **minor** -- `note_wait()` rewrites the ticket whenever the holder changes,
   so a ticket blocked by alternating holders resets both `since` and the mtime
   `stale` is computed from. The row still prints the wait line, so `ls` is not
   silent about it.
3. **nit** -- `pipeline/tui/app.py:249` calls `ticket_rows()` and renders only
   `stale` (`app.py:83`), so the dashboard still reads a held ticket as idle.
   The plan scoped the display to `cmd_ls`.

I did not run `./pipeline/hooks/test_dangerous_commands.py`. The guard blocked
it: "`test_dangerous_commands.py` is not on the read-only allowlist". The delta
touches no file under `pipeline/hooks/`.

### 2026-08-24 09:16:38Z · review · session · session=cb7808e9-22a4-4c4c-a43c-45250c6dc463

`review` ran as session `cb7808e9-22a4-4c4c-a43c-45250c6dc463`
- replay: `claude --resume cb7808e9-22a4-4c4c-a43c-45250c6dc463`
- log: `.project/logs/TICKET-048-review-cb7808e9.log`

### 2026-08-24 09:16:38Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the 4-source-file delta against the plan and the 9 acceptance criteria: no blocking findings, 120 tests pass, 3 minor findings recorded in the thread

### 2026-08-24 09:16:49Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 09:16:50Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/048


Already up to date.
Updating 4959f6c..44218c7
Fast-forward
 pipeline/cli/main.py          |   4 +-
 pipeline/core/machine.py      |  20 +++++-
 pipeline/daemon/server.py     |  22 ++++++-
 pipeline/daemon/supervisor.py |  32 ++++++++--
 tests/test_daemon.py          | 140 +++++++++++++++++++++++++++++++++++++++++-
 tests/test_machine.py         |  13 ++++
 6 files changed, 217 insertions(+), 14 deletions(-)

```

### 2026-08-24 09:16:50Z · merging · decision

decision recorded as `DEC-048`
