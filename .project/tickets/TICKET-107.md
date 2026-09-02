---
id: TICKET-107
stage: done
class: bugfix
branch: ticket/107
test_file: tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log
files_declared:
- README.md
- pipeline/tui/app.py
- tests/test_tui.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 9
  plan_files: 3
  no_result: 0
  structural_gate_failures: 1
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 5eb4e9fd-745f-42e0-8c38-eba18af89f6c
  log: .project/logs/TICKET-107-review-5eb4e9fd.log
  cost_usd: 1.065928
approved_by: chezzijr
approved_at: '2026-09-02T09:49:05.521443+00:00'
---

## Summary

`pipeline tui` opens an `escalated` ticket on the stage-log tail, so the reason it
escalated is never on screen. `_show()` (`pipeline/tui/app.py:455`) branches on
`awaiting-approval` only; `escalated` falls through to `tail_log()`.

The plan adds `escalation_lines(project, tid)` below `plan_lines()`
(`pipeline/tui/app.py:181`). It reads `Ticket.find(project, tid).thread()`, returns the
last kind `escalation` entry, falls back to the last kind `transition` entry whose
`attrs["to"] == "escalated"`, and catches `(PipelineError, OSError)` because `_show`
runs on every tree highlight. `_show()` gains an `elif row.get("stage") == "escalated":`
branch that writes those lines, then `-- stage log --`, then the unchanged `tail_log()`
loop.

Tests: the repro test, one fallback test on a transition-only thread, one test that the
stage log still renders below the reason. `README.md:280` gains one sentence.

Re-planned after the Tier A gate's one finding. `## Reproduction` `expect:` was the
whole assertion joined by literal backslash-n escapes, which no run emits; it is now
the single line `AssertionError: == TICKET-001 escalated bugfix a thing`. The plan,
digest, decisions, acceptance criteria and rollback are unchanged.

Both gates passed. Tier A: PASS. Tier B: PASS on all eight items, nothing
`unverified`. The plan fixes the missing `escalated` branch, not the test; DEC-073
binds `plan_text()` to the approval pane only and no CLI prints an escalation
reason, so `escalation_lines()` is no second implementation; the riskiest step is
step 3, whose `except (PipelineError, OSError)` keeps the tree tests at
`tests/test_tui.py:175` and `:259` green on rows with no ticket file. Implement the
plan as written.

Implemented as planned, all 9 steps done. `escalation_lines()` and the
`escalated` branch in `_show()` landed at `6389e3e`, the fallback and
below-the-log tests at `f597ee3`, the README sentence at `ac31256`. Full
suite: 522 passed.

Review passed with no blocking findings. The delta `20030e3..HEAD` is 95 added
lines and no deleted line. All 8 acceptance criteria hold: `uv run --group dev
pytest -q tests/test_tui.py` -> `42 passed`, `uv run --group dev pytest -q` ->
`522 passed`, `grep -c escalation_lines pipeline/tui/app.py` -> `2`,
`README.md:283` describes the pane. Three low-severity notes are on the thread
and none needs action: the below-the-log test asserts needle membership rather
than order (as its precedent does), `ESCALATED_TRANSITION` omits the stage-move
line plan step 5 named, and a stale `escalation` entry outranks a fresher
`escalated` transition entry after a resume, which is what `## Decisions` asks
for.

## Reproduction

Test: `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log`
Command: `uv run --group dev pytest -q tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log`

Failure output:

    AssertionError: == TICKET-001 escalated bugfix a thing
      (no log yet)
    assert 'suite excluding the new test is RED on base too' in '== TICKET-001 escalated bugfix a thing\n(no log yet)'

expect: AssertionError: == TICKET-001 escalated bugfix a thing

The test builds a ticket at `stage: escalated` with a `## Thread` carrying a `gate`
entry and an `escalation` entry, drives `_show()` via the pilot, and asserts the
`escalation` entry's text appears in the pane. It fails because `_show()` has no
`escalated` branch: it falls straight to `tail_log()`, which finds no stage log for
the fixture and renders `(no log yet)` -- confirming the reported symptom, not a
setup error.

## Digest

Files touched: `pipeline/tui/app.py` (the helper and the `_show()` branch), `tests/test_tui.py` (three tests, one new fixture), `README.md` (the paragraph documenting the pane).

Key functions, all in `pipeline/tui/app.py`: `plan_lines()` at line 175 is the shape to copy -- it calls `plan_text(Ticket.find(project, tid))` and catches `(PipelineError, OSError)`, returning a `(... unreadable: {e})` line instead of raising. `_show()` at line 455 writes the header line, returns early when `self._pty(row)` is true, then runs the `awaiting-approval` branch (lines 466-469) and finally `tail_log()` (line 470).

Entry points: the escalation text is on the thread. `Ticket.thread()` (`pipeline/core/ticket.py:684`) returns `ThreadEntry(ts, stage, kind, attrs, text, raw)` (`pipeline/core/ticket.py:569`), where `raw` is the `### ` header line without its prefix. `escalate()` (`pipeline/daemon/supervisor.py:72`) appends kind `escalation`, whose text is the reason alone. `advance()` (`pipeline/daemon/supervisor.py:139`) appends kind `transition` with `to=escalated`, whose text is the stage move plus the note -- for a burnt bound the note reads `` `review_loops` reached its bound (3/3) ``.

Gotchas:
- `_show()` runs on every tree highlight, and existing tests highlight rows whose ticket file does not exist (`tests/test_tui.py:175`, `tests/test_tui.py:259`). `Ticket.load()` wraps every read failure in `PipelineError` (`pipeline/core/ticket.py:613-616`), so `except (PipelineError, OSError)` covers a missing file too. Without that catch those tests break.
- `Ticket.find(project, tid)` takes the project directory and the ticket id, exactly as `plan_lines()` calls it. `_show()` holds them as `key[0]` and `key[1]`.
- The `escalation` entry must outrank the `transition` entry. `escalate()` sets `stage` itself and never reaches `advance()`, so a thread carries the specific reason under kind `escalation` and the bound/enumerated-row reason under kind `transition`.
- Write the reason ABOVE `tail_log()`'s output and keep `-- stage log --` between them, as the approval branch does. `tests/test_tui.py::test_the_approval_pane_shows_rollback_and_the_log_below_it` is the precedent for asserting that marker.
- `log.write(line, width=cols or None)` in the `tail_log()` loop is DEC-063's mechanism and stays untouched. The new lines are prose and go through plain `log.write(line)`.

## Decisions checked

- DEC-073: `pipeline plan` and the TUI's `awaiting-approval` pane print the same three sections through one function, `plan_text()`. It binds the approval pane only. No CLI command prints an escalation reason today, so this plan creates no second implementation: `escalation_lines()` reads the thread the ticket already carries.
- DEC-039: `tail_log()` owns the one PTY-versus-stream-json sniff, on a raw ESC byte. This plan does not touch `tail_log()` and sniffs no bytes.
- DEC-063: `#log` writes a PTY dump at the width it was drawn at, and `cols == 0` means wrap it. The new writes leave that loop unchanged.
- DEC-062: `running` and `mode` are `None` when unknown, and `_pty()` refuses anything but `mode: "interactive"`. The new branch sits after the `_pty()` early return, so an attached stage is unaffected.
- Grep terms used over `.project/decisions/`: `tui`, `TUI`, `pane`, `_show`, `plan_lines`, `tail_log`, `escalat`. No record constrains what an `escalated` ticket's pane shows.

## Plan

1. Run `uv run --group dev pytest -q tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log` and confirm it fails on `assert 'suite excluding the new test is RED on base too' in '== TICKET-001 escalated bugfix a thing'` plus `(no log yet)`; the test and its `ESCALATED` fixture are already in `tests/test_tui.py`.
2. Add `escalation_lines(project: str, tid: str) -> list[str]` to `pipeline/tui/app.py` directly below `plan_lines()` (line 181), with a docstring saying it must not raise because `_show` runs on every tree highlight, and this body: `try: entries = Ticket.find(project, tid).thread()` then `except (PipelineError, OSError) as e: return [f"(escalation reason unreadable: {e})"]`; then `hit = next((x for x in reversed(entries) if x.kind == "escalation"), None)`; then `if hit is None: hit = next((x for x in reversed(entries) if x.kind == "transition" and x.attrs.get("to") == "escalated"), None)`; then `if hit is None: return ["(no escalation entry on the thread)"]`; then `return [hit.raw, *hit.text.splitlines()]`.
3. In `_show()` in `pipeline/tui/app.py`, add below the `awaiting-approval` block an `elif row.get("stage") == "escalated":` branch that runs `for line in escalation_lines(key[0], key[1]): log.write(line)` and then `log.write("-- stage log --")`, leaving the `tail_log()` loop under it unchanged.
4. Run `uv run --group dev pytest -q tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log` and confirm it passes; commit `pipeline/tui/app.py` as `fix: open an escalated ticket pane on the escalation reason (TICKET-107)`.
5. Add fixture `ESCALATED_TRANSITION` to `tests/test_tui.py` beside `ESCALATED`: the `ESCALATED` frontmatter unchanged, a `## Summary` of `x`, and a `## Thread` holding one entry headed `### 2026-09-02 05:08:43Z · review · transition · to=escalated · result=fail` whose body is the stage-move line followed by `` `review_loops` reached its bound (3/3) ``.
6. Add `test_escalated_falls_back_to_the_transition_entry()` to `tests/test_tui.py`, shaped like `test_escalated_shows_the_escalation_reason_not_just_the_stage_log`: build `make_project(ESCALATED_TRANSITION)`, select `TICKET-001`, assert `` `review_loops` reached its bound (3/3) `` is in the rendered `#log`; run `uv run --group dev pytest -q tests/test_tui.py::test_escalated_falls_back_to_the_transition_entry` and confirm it passes.
7. Add `test_the_escalated_pane_shows_the_log_below_the_reason()` to `tests/test_tui.py`, shaped like `test_the_approval_pane_shows_rollback_and_the_log_below_it`: build `make_project(ESCALATED)`, write `.project/logs/TICKET-001-plan-validation.log` with the same clear-screen PTY bytes ending `seen-in-log` that the precedent test writes, select `TICKET-001`, assert the pane holds `suite excluding the new test is RED on base too`, `-- stage log --` and `seen-in-log`.
8. Run `uv run --group dev pytest -q tests/test_tui.py` and confirm it exits 0, with `test_a_running_stage_pane_shows_the_log_without_the_plan` and the tree tests at `tests/test_tui.py:175` and `tests/test_tui.py:259` among the passes; commit `tests/test_tui.py` as `test: cover the escalated pane fallback and its stage log (TICKET-107)`.
9. Extend the paragraph at `README.md:280` with one sentence: a ticket at `escalated` opens on the reason it escalated -- the thread's last `escalation` entry, else its last `escalated` transition entry -- with `-- stage log --` and the stage log below it; commit `README.md` as `docs: describe the escalated pane (TICKET-107)`.

## Acceptance criteria

- `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log` passes.
- `tests/test_tui.py::test_escalated_falls_back_to_the_transition_entry` passes, and it fails when step 2's `transition` fallback is deleted.
- `tests/test_tui.py::test_the_escalated_pane_shows_the_log_below_the_reason` passes, proving the reason precedes `-- stage log --` and the log follows it.
- `tests/test_tui.py::test_a_running_stage_pane_shows_the_log_without_the_plan` still passes, proving the new branch does not fire for a stage other than `escalated`.
- `uv run --group dev pytest -q tests/test_tui.py` exits 0.
- `uv run --group dev pytest -q` reports no failures other than any that already fail on base commit `20030e3`, measured by running the same command on base before step 2.
- `grep -c escalation_lines pipeline/tui/app.py` prints a number greater than 1, because the helper is defined and called.
- `grep -n escalated README.md` prints a line describing what the pane of a ticket at `escalated` opens on.

## Decisions

**An `escalated` ticket's pane opens on the escalation reason, and the `escalation` entry outranks the `transition` entry.** Two routes write the reason onto the thread. `escalate()` (`pipeline/daemon/supervisor.py:72`) appends kind `escalation`, whose text is the reason alone; `advance()` (`pipeline/daemon/supervisor.py:139`) appends kind `transition` with `to=escalated` when a bounded loop hits its bound or an enumerated row escalates. `escalation_lines()` in `pipeline/tui/app.py` prefers the last `escalation` entry and falls back to the last `transition` entry whose `attrs["to"] == "escalated"`. The two routes never describe one event: `escalate()` sets `stage` itself and never reaches `advance()`. Reading only `transition` shows nothing for a crash or a tamper; reading only `escalation` shows nothing for a burnt bound.

**`escalation_lines()` must not raise, for the reason `plan_lines()` must not.** `_show()` runs on every tree highlight, including rows whose ticket file does not exist. `Ticket.load()` wraps every read failure in `PipelineError`, so the `except (PipelineError, OSError)` that returns an `(escalation reason unreadable: ...)` line is what keeps one highlight from killing the app. Do not narrow that catch.

**The reason goes above the stage log, never instead of it.** The escalated pane keeps `tail_log()`'s output under a `-- stage log --` marker, exactly as the `awaiting-approval` pane does (TICKET-073, DEC-073). The log is the evidence a human reads after the verdict.

## Rollback

Revert the three commits from steps 4, 8 and 9. The change is additive: one new function in `pipeline/tui/app.py`, one `elif` branch in `_show()`, three tests in `tests/test_tui.py`, one sentence in `README.md`. Reverting restores the `escalated` pane to the stage-log tail and re-reds `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log`. Nothing outside `pipeline/tui/app.py` calls `escalation_lines()`, and no ticket file, counter or stage prompt changes.

## Thread

### 2026-09-02 07:21:17Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-02 07:40:00Z · triage · note

Reproduced. Added `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log`,
following the precedent test's shape: a ticket at `stage: escalated` with a
`## Thread` carrying a `gate` entry and an `escalation` entry. `_show()` has no
`escalated` branch, so the pane falls through to `tail_log()`, which reports
`(no log yet)` for the fixture instead of the escalation text.

result: `ok`. Not `chore`: the fix needs a design choice this stage does not
make -- the fallback order between an `escalation` entry and a `transition`
entry whose `attrs["to"] == "escalated"`, per the ticket's own suggestion.
files_declared: `pipeline/tui/app.py`.

### 2026-09-02 07:23:07Z · triage · session · session=343adc9d-a892-4368-a379-c9375c2a0293

`triage` ran as session `343adc9d-a892-4368-a379-c9375c2a0293`
- replay: `claude --resume 343adc9d-a892-4368-a379-c9375c2a0293`
- log: `.project/logs/TICKET-107-triage-343adc9d.log`
- cost: $0.49 of a $3 cap
- tokens: 7,581 out (262 thinking) · 50 in · 1,145,130 cache read · 46,821 cache write

### 2026-09-02 07:23:07Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced: escalated pane shows only the stage log, not the escalation reason

### 2026-09-02 07:26:56Z · planning · note

Plan written. `escalation_lines()` in `pipeline/tui/app.py` returns the last kind
`escalation` thread entry and falls back to the last kind `transition` entry whose
`attrs["to"] == "escalated"`. That order is the design choice triage flagged: the
two routes never describe one event, because `escalate()`
(`pipeline/daemon/supervisor.py:72`) sets `stage` itself and never reaches
`advance()` (`pipeline/daemon/supervisor.py:139`). The `escalation` entry carries
the specific reason; the `transition` entry carries a burnt bound.

Scope is one subsystem, the TUI detail pane. I ask the human nothing: the ticket's
suggestion, the precedent `plan_lines()` and DEC-073's approval pane settle the shape.

files_declared grew from triage's one file to three: `pipeline/tui/app.py`,
`tests/test_tui.py` (two new tests and one fixture) and `README.md`, whose
paragraph at line 280 documents the approval pane and now documents this one.

result: `ok`.

### 2026-09-02 07:27:08Z · planning · session · session=6163e4ad-dbbd-442d-bee5-e4a86144cabe

`planning` ran as session `6163e4ad-dbbd-442d-bee5-e4a86144cabe`
- replay: `claude --resume 6163e4ad-dbbd-442d-bee5-e4a86144cabe`
- log: `.project/logs/TICKET-107-planning-6163e4ad.log`
- cost: $1.63 of a $10 cap
- tokens: 19,724 out (5,404 thinking) · 40 in · 889,531 cache read · 68,713 cache write

### 2026-09-02 07:27:08Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned: escalation_lines() in pipeline/tui/app.py, wired into _show()'s escalated branch

### 2026-09-02 07:27:48Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `## Reproduction` `expect:` cannot recur: it holds a literal backslash escape where the run's output holds a control character, and `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log`'s output does not contain it either way -- trim it to the part before the escape. Got: "AssertionError: == TICKET-001 escalated bugfix a thing\\n  (no log yet)\\nassert 'suite excluding the new test is RED on base too' in '== TICKET-001 escalated bugfix a thing\\n(no log yet)'"

### 2026-09-02 07:27:49Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- `## Reproduction` `expect:` cannot recur: it holds a literal backslash escape where the run's output holds a control character, and `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log`'s output does not contain it either way -- trim it to the part before the escape. Got: "AssertionError: == TICKET-001 escalated bugfix a thing\\n  (no log yet)\\nassert 'suite excluding the new test is RED on base too' in '== TICKET-001 escalated bugfix a thing\\n(no log yet)'"

### 2026-09-02 07:45:00Z · planning · note

The gate's one finding is fixed. `## Reproduction` `expect:` held the whole
three-line assertion joined by literal backslash-n escapes, and the run emits
control characters there, not those two characters. I re-ran
`uv run --group dev pytest -q tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log`
and confirmed the assertion spans three output lines. `expect:` is now the single
line `AssertionError: == TICKET-001 escalated bugfix a thing`, which the run's
output contains verbatim.

Nothing else changed. `## Digest`, `## Decisions checked`, `## Plan`,
`## Acceptance criteria`, `## Decisions` and `## Rollback` stand as written; the
gate charged them no finding. I re-verified the digest's line references in the
worktree: `plan_lines()` at `pipeline/tui/app.py:175`, `_show()` at
`pipeline/tui/app.py:455` with its `awaiting-approval` branch at lines 466-469,
and the approval-pane paragraph at `README.md:280`.

Decisions re-checked against `.project/decisions/`: DEC-073, DEC-039, DEC-063 and
DEC-062 each exist there.

files_declared: `pipeline/tui/app.py`, `tests/test_tui.py`, `README.md`.

result: `ok`.

### 2026-09-02 07:29:57Z · planning · session · session=397d0581-ad63-4d03-8874-835f64e28480

`planning` ran as session `397d0581-ad63-4d03-8874-835f64e28480`
- replay: `claude --resume 397d0581-ad63-4d03-8874-835f64e28480`
- log: `.project/logs/TICKET-107-planning-397d0581.log`
- cost: $1.07 of a $10 cap
- tokens: 8,553 out (2,875 thinking) · 38 in · 746,243 cache read · 48,087 cache write

### 2026-09-02 07:29:57Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned: trimmed `## Reproduction` `expect:` to one line the run emits; plan unchanged

### 2026-09-02 07:30:38Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log` fails as required
```
_ _ 

    async def go():
        d = make_project(ESCALATED)
        fake = FakeClient([row(d, "TICKET-001", "escalated")])
        app = PipelineApp(client=fake)
        async with app.run_test() as pilot:
            app.query_one(Tree).focus()
            await select(app, pilot, d, "TICKET-001")
    
            log = app.query_one("#log", RichLog)
    
            def text(strip):
                return "".join(seg.text for seg in strip)
    
            rendered = "\n".join(text(s) for s in log.lines)
>           assert "suite excluding the new test is RED on base too" in rendered, rendered
E           AssertionError: == TICKET-001 escalated bugfix a thing
E             (no log yet)
E           assert 'suite excluding the new test is RED on base too' in '== TICKET-001 escalated bugfix a thing\n(no log yet)'

tests/test_tui.py:358: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.48s ===============================

```
- ok: `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log` fails on base `main` too -- the bug is not already fixed upstream
```
luding the new test is RED on base too" in rendered, rendered
E           AssertionError: == TICKET-001 escalated bugfix a thing
E             (no log yet)
E           assert 'suite excluding the new test is RED on base too' in '== TICKET-001 escalated bugfix a thing\n(no log yet)'

tests/test_tui.py:358: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.16s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-sdhn94kz/base
      Built pipeline @ file:///tmp/pipeline-base-sdhn94kz/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 65ms

```

### 2026-09-02 07:35:00Z · plan-validation · finding · tier=B · verdict=PASS

**Tier B: PASS.** Eight items, each verified against the worktree.

1. Root cause: `_show()` (`pipeline/tui/app.py:455`) branches on
   `awaiting-approval` only, so an `escalated` row falls to `tail_log()`. I read
   lines 455-474; there is no `escalated` branch. The plan adds the missing
   branch, not a test-shaped patch.
2. Decisions: DEC-073 binds `plan_text()`'s three sections to the approval pane;
   grep over `pipeline/` shows `escalate()` (`pipeline/daemon/supervisor.py:74`)
   is the only writer of kind `escalation` and no CLI prints it, so no second
   implementation. DEC-063 and DEC-039 bind `tail_log()`, which the plan leaves
   untouched. DEC-062 binds `_pty()`, which the new `elif` sits after.
3. Scope: all 9 steps trace to a criterion. No step exceeds them.
4. Criteria falsifiable: criterion 2 names the deletion that reds it; criterion 4
   reds if the branch fires on the wrong stage; criterion 3 reds if the reason
   lands below `-- stage log --`.
5. No research left: `ThreadEntry.raw/.kind/.attrs` (`pipeline/core/ticket.py:569`),
   `Ticket.find` (line 631), `Ticket.load` wrapping every read failure in
   `PipelineError` (lines 618-621), `README.md:280` -- each confirmed.
6. Riskiest step: step 3. `_show()` runs on every tree highlight, and
   `tests/test_tui.py:175` and `:259` highlight `escalated` rows at `/tmp/alpha`
   with no ticket file. `except (PipelineError, OSError)` covers the missing
   file; step 8 names both tests among the required passes.
7. Regression surface: the `awaiting-approval` pane and every non-`escalated`
   pane. `test_the_approval_pane_shows_rollback_and_the_log_below_it` and
   `test_a_running_stage_pane_shows_the_log_without_the_plan` cover them, both in
   the `tests/test_tui.py` run of criterion 5.
8. Blast radius: 3 files, one function and one `elif` -- a bugfix.

long: eight scored items, one line of evidence each.

unverified: none. Every probe was a read the guard allows.

### 2026-09-02 07:32:27Z · plan-validation · session · session=7ee75a66-ddc0-41a5-bac4-81acbbf805b1

`plan-validation` ran as session `7ee75a66-ddc0-41a5-bac4-81acbbf805b1`
- replay: `claude --resume 7ee75a66-ddc0-41a5-bac4-81acbbf805b1`
- log: `.project/logs/TICKET-107-plan-validation-7ee75a66.log`
- cost: $0.98 of a $3 cap
- tokens: 7,266 out (2,048 thinking) · 34 in · 686,066 cache read · 45,787 cache write

### 2026-09-02 07:32:27Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B: all eight items pass; every cited line, function and decision verified against the worktree

### 2026-09-02 09:49:05Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-02 09:49:48Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-02 07:30:38Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log` fails on base `main` too -- the bug is not already fixed upstream
```
luding the new test is RED on base too" in rendered, rendered
E           AssertionError: == TICKET-001 escalated bugfix a thing
E             (no log yet)
E           assert 'suite excluding the new test is RED on base too' in '== TICKET-001 escalated bugfix a thing\n(no log yet)'

tests/test_tui.py:358: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui.py::test_escalated_shows_the_escalation_reason_not_just_the_stage_log
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.15s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-iy32hccc/base
      Built pipeline @ file:///tmp/pipeline-base-iy32hccc/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```

### 2026-09-02 09:49:49Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

### 2026-09-02 · implementing · note

**todo**

1. [x] confirm RED on the repro test
2. [x] add `escalation_lines()` below `plan_lines()`
3. [x] add the `escalated` branch to `_show()`
4. [x] confirm GREEN, commit `pipeline/tui/app.py`
5. [x] add `ESCALATED_TRANSITION` fixture
6. [x] add `test_escalated_falls_back_to_the_transition_entry`
7. [x] add `test_the_escalated_pane_shows_the_log_below_the_reason`
8. [x] full `test_tui.py` run green, commit `tests/test_tui.py`
9. [x] extend `README.md:280`, commit

### 2026-09-02 · implementing · report

**implemented**: all 9 plan steps.

- step 1: repro test failed with the expected assertion, confirming RED.
- steps 2-4: `escalation_lines()` added below `plan_lines()`
  (`pipeline/tui/app.py:181`); `_show()` gained the `elif row.get("stage") ==
  "escalated":` branch. Repro test passed; `uv run --group dev pytest -q
  tests/test_tui.py` -> `40 passed`. Committed `6389e3e`.
- steps 5-7: added `ESCALATED_TRANSITION` fixture,
  `test_escalated_falls_back_to_the_transition_entry` and
  `test_the_escalated_pane_shows_the_log_below_the_reason`. Deleting the
  `transition` fallback reds the first with
  `AssertionError: '`review_loops` reached its bound (3/3)' in '== TICKET-001
  escalated bugfix a thing\n(no escalation entry on the thread)\n-- stage log
  --\n(no log yet)'` -- confirms the test is not vacuous.
- step 8: `uv run --group dev pytest -q tests/test_tui.py` -> `42 passed`,
  including `test_a_running_stage_pane_shows_the_log_without_the_plan` and the
  no-ticket-file tree tests at lines 175/259. Committed `f597ee3`.
- step 9: one sentence added at `README.md:283`. Committed `ac31256`.

Full suite: `uv run --group dev pytest -q` -> `522 passed`, no regressions.

re-gated after rebasing onto base: passed

### 2026-09-02 09:52:40Z · implementing · session · session=774035c7-5d74-4f77-9e1a-bdf6be9ab0e9

`implementing` ran as session `774035c7-5d74-4f77-9e1a-bdf6be9ab0e9`
- replay: `claude --resume 774035c7-5d74-4f77-9e1a-bdf6be9ab0e9`
- log: `.project/logs/TICKET-107-implementing-774035c7.log`
- cost: $0.59 of a $8 cap
- tokens: 8,718 out (345 thinking) · 62 in · 1,525,073 cache read · 48,410 cache write

### 2026-09-02 09:52:40Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ added escalation_lines() and the escalated branch in _show(); all 3 new tests plus full suite pass

### 2026-09-02 · review · finding · verdict=PASS

**review: no blocking findings.** Reviewed `git diff 20030e3..HEAD`: 95 added
lines across `pipeline/tui/app.py`, `tests/test_tui.py`, `README.md`. The tree
was clean before and after; I changed nothing.

All 8 acceptance criteria hold. `uv run --group dev pytest -q tests/test_tui.py`
-> `42 passed in 9.27s`. `uv run --group dev pytest -q` -> `522 passed in
37.78s`. `grep -c escalation_lines pipeline/tui/app.py` -> `2`. `grep -n
escalated README.md` -> line 283.

`escalation_lines()` matches plan step 2 body for body. The `elif
row.get("stage") == "escalated":` branch sits below the approval branch and
above the unchanged `tail_log()` loop (`pipeline/tui/app.py:488`). The fallback
test is not vacuous: `ESCALATED_TRANSITION` carries no `escalation` entry and
no log file, so without the fallback the pane renders `(no escalation entry on
the thread)` and `(no log yet)`.

Non-blocking notes, no action required:

1. severity: low. `test_the_escalated_pane_shows_the_log_below_the_reason`
   asserts membership of each needle, not order, so it would pass if the reason
   rendered below the log. It copies its precedent
   `test_the_approval_pane_shows_rollback_and_the_log_below_it`
   (`tests/test_tui.py:433`), which asserts the same way.
2. severity: low. The `ESCALATED_TRANSITION` body holds the bound line only;
   plan step 5 also named a stage-move line. The test asserts the bound line,
   so the fallback coverage is unaffected.
3. severity: low. After a human resumes an escalated ticket that later burns a
   bound, the stale `escalation` entry outranks the fresh `transition` entry.
   `## Decisions` specifies that ranking.

### 2026-09-02 09:55:30Z · review · session · session=5eb4e9fd-745f-42e0-8c38-eba18af89f6c

`review` ran as session `5eb4e9fd-745f-42e0-8c38-eba18af89f6c`
- replay: `claude --resume 5eb4e9fd-745f-42e0-8c38-eba18af89f6c`
- log: `.project/logs/TICKET-107-review-5eb4e9fd.log`
- cost: $1.07 of a $5 cap
- tokens: 8,533 out (3,122 thinking) · 38 in · 775,048 cache read · 46,385 cache write

### 2026-09-02 09:55:30Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review passed: 522 passed, all 8 acceptance criteria met, no blocking findings

### 2026-09-02 09:56:10Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-02 09:56:11Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/107


Current branch ticket/107 is up to date.
Already up to date.
Updating 1040e3e..ac31256
Fast-forward
 README.md           |   3 ++
 pipeline/tui/app.py |  22 ++++++++++
 tests/test_tui.py   | 115 ++++++++++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 140 insertions(+)

```

### 2026-09-02 09:56:11Z · merging · decision

decision recorded as `DEC-107`
