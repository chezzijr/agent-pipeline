---
id: TICKET-092
stage: done
class: feature
branch: ticket/092
test_file: tests/test_cli.py::test_note_appends_at_any_stage_without_touching_control_fields
files_declared:
- pipeline/cli/main.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 0
  plan_files: 1
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: quick-review
  id: 87736cb9-425b-479e-8afc-9ddf804ea5db
  log: .project/logs/TICKET-092-quick-review-87736cb9.log
  cost_usd: 0.2197192
cheap_route_head: 872ebf1cb85a04ba74e9a7de39a293123d380ea6
---

## Summary

`pipeline note`: hand a running or escalated ticket guidance without editing frontmatter

`pipeline answer` is the only way to get human text into a ticket, and it refuses
anywhere but one stage:

    # pipeline/cli/main.py:234
    if t.stage != "needs-input":
        die(f"{args.id} is in `{t.stage}`, not `needs-input`")

So an operator who sees a stage going wrong -- or reads an escalation and wants to
record what the agent should know before a `pipeline resume` -- has two options:
wait for the ticket to park itself, or edit the file by hand. Hand-editing is what
`.result` handling and `CONTROL_FIELDS` exist to prevent.

Expected: `pipeline note <id> "<text>"` appends a human-written thread entry at
ANY stage, escalated included, and touches no control field. `stage_view()`
(`pipeline/core/ticket.py`) already keeps every human-written kind whole, so the
next spawn sees it without any change to the view. Falsifiable: `note` on a ticket
in `implementing` must leave `stage`, `counters`, `branch` and `lease` byte-identical
and add one thread entry; today it exits 1 without writing anything.

Note for planning: a note written while a stage holds its lease reaches that stage
only on its NEXT spawn, since the prompt is composed once. Say so in the command's
output rather than trying to deliver it mid-run.

Triaged: confirmed. There is no `note` subcommand at all (not a stage check that
refuses -- argparse rejects `note` as an unknown choice, exit code 2, not the
ticket's stated exit 1). Fix is small: add a `note` subparser in
`pipeline/cli/main.py` mirroring `cmd_answer`/`cmd_resume`'s `t.append("human",
"note", ...)` pattern, with no stage guard. Failing test committed at
872ebf1.

Implemented: added `cmd_note` and a `note` subparser in `pipeline/cli/main.py`,
committed at 82c622e. No stage guard, no control-field write, no `record()`
call. `test_note_appends_at_any_stage_without_touching_control_fields` passes;
full `tests/test_cli.py` (36 tests) passes.

Quick-reviewed: ok, both questions answered yes.

## Reproduction

Test: `tests/test_cli.py::test_note_appends_at_any_stage_without_touching_control_fields`
Command: `uv run --group dev pytest -q tests/test_cli.py -k test_note_appends_at_any_stage_without_touching_control_fields`

Output:
```
E       AssertionError: (2, '', 'usage: __main__.py [-h] [--project PROJECT]
                     {init,new,gate,config,plan,approve,reject,answer,resume,logs,ls,status,tui,register,unregister,projects,start,stop,run,metrics}
                     ...
                     __main__.py: error: argument cmd: invalid choice: 'note' (choose from init, new, gate, config, plan, approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)
E       assert 2 == 0
```
expect: invalid choice: 'note' (choose from init, new, gate, config, plan, approve, reject, answer, resume, logs, ls, status, tui, register, unregister, projects, start, stop, run, metrics)

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-29 03:52:45Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 · triage · note

Reproduced: `pipeline note <id> "<text>"` has no subcommand. `python -m
pipeline note TICKET-001 "x"` exits 2 with argparse's `invalid choice: 'note'`,
not the ticket's stated exit 1 -- there is no `note` verb registered at all,
so the failure is one level earlier than a stage-guard rejection.

Added `tests/test_cli.py::test_note_appends_at_any_stage_without_touching_control_fields`:
resumes a ticket to `implementing`, snapshots stage/counters/branch/lease,
runs `pipeline note`, asserts it exits 0, those four fields are unchanged, and
exactly one `note`-kind thread entry with the given text exists. It fails
today on the `returncode == 0` assertion with the invalid-choice usage error
above. Committed at 872ebf1.

Fix (chore-sized): add a `note` subparser in `pipeline/cli/main.py` next to
`answer`/`resume`, calling `t.append("human", "note", args.text)` then
`t.save()` with no stage check. Touches only `pipeline/cli/main.py`.

### 2026-08-29 04:18:57Z · triage · session · session=bca9a260-c81e-410a-82af-67a5b836e8bc

`triage` ran as session `bca9a260-c81e-410a-82af-67a5b836e8bc`
- replay: `claude --resume bca9a260-c81e-410a-82af-67a5b836e8bc`
- log: `.project/logs/TICKET-092-triage-bca9a260.log`
- cost: $0.42 of a $3 cap
- tokens: 5,734 out (431 thinking) · 52 in · 1,053,240 cache read · 38,128 cache write

### 2026-08-29 04:18:57Z · triage · transition · to=implementing · result=chore · marker=yes

**triage -> implementing** (result: `chore`)

✓ reproduced: no `pipeline note` subcommand exists; added failing test, committed

### 2026-08-29 · implementing · note

Todo:
1. Add `cmd_note` in `pipeline/cli/main.py` and a `note` subparser -- done.
2. Confirm RED: run the failing test, read the failure -- done, exit 2, argparse
   invalid choice, as expected.
3. Confirm GREEN: implement, re-run the test -- done, passes.
4. Run `tests/test_cli.py` for regressions -- done, 36 passed.
5. Commit -- done.

`cmd_note` calls `t.append("human", "note", f"**note from {who}**\n\n{args.text}",
by=who)` then `t.save()`. No stage guard, no `record()` call (that emits a
transition event and this command makes none), no touch to `stage`, `counters`,
`branch`, or `lease`. Output names the current stage and warns the note reaches
it only on the next spawn when a lease is held, per the ticket's planning note.

Committed at 82c622e (`feat(TICKET-092): add pipeline note command for any
stage`). `test_note_appends_at_any_stage_without_touching_control_fields`
passes; full `tests/test_cli.py` (36 tests) passes.

### 2026-08-29 04:20:40Z · implementing · session · session=369ccacf-94a5-40de-9b67-625cdebbfaa9

`implementing` ran as session `369ccacf-94a5-40de-9b67-625cdebbfaa9`
- replay: `claude --resume 369ccacf-94a5-40de-9b67-625cdebbfaa9`
- log: `.project/logs/TICKET-092-implementing-369ccacf.log`
- cost: $0.35 of a $8 cap
- tokens: 4,923 out (485 thinking) · 42 in · 809,099 cache read · 34,988 cache write

### 2026-08-29 04:20:40Z · implementing · transition · to=quick-review · result=ok · marker=yes

**implementing -> quick-review** (result: `ok`)

✓ added `pipeline note` subparser calling t.append("human","note",...); test_note_appends_at_any_stage_without_touching_control_fields passes

### 2026-08-29 · quick-review · note

1. Test fails without diff: yes. `git diff 872ebf1...HEAD -- tests/test_cli.py`
is empty, so the test committed at triage's reproduction is unchanged by
implementing. `## Reproduction` already recorded its RED run: exit 2,
`argument cmd: invalid choice: 'note'`. With the diff in, `uv run --group dev
pytest -q tests/test_cli.py -k
test_note_appends_at_any_stage_without_touching_control_fields` gives
`1 passed, 35 deselected`.

2. Diff touches only named files: yes. `git diff --name-only main...HEAD`
gives `pipeline/cli/main.py` and `tests/test_cli.py`. `## Summary` names
`pipeline/cli/main.py`: "added `cmd_note` and a `note` subparser in
`pipeline/cli/main.py`, committed at 82c622e." `## Reproduction` names
`tests/test_cli.py`: "Test:
`tests/test_cli.py::test_note_appends_at_any_stage_without_touching_control_fields`."

### 2026-08-29 04:23:50Z · quick-review · session · session=87736cb9-425b-479e-8afc-9ddf804ea5db

`quick-review` ran as session `87736cb9-425b-479e-8afc-9ddf804ea5db`
- replay: `claude --resume 87736cb9-425b-479e-8afc-9ddf804ea5db`
- log: `.project/logs/TICKET-092-quick-review-87736cb9.log`
- cost: $0.22 of a $2 cap
- tokens: 2,717 out (424 thinking) · 24 in · 403,011 cache read · 27,715 cache write

### 2026-08-29 04:23:50Z · quick-review · transition · to=verifying · result=ok · marker=yes

**quick-review -> verifying** (result: `ok`)

✓ test fails without diff (unchanged since 872ebf1) and diff touches only main.py + test_cli.py, both named

### 2026-08-29 04:24:24Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 04:24:25Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/092


Current branch ticket/092 is up to date.
Already up to date.
Updating 56377bd..82c622e
Fast-forward
 pipeline/cli/main.py | 15 +++++++++++++++
 tests/test_cli.py    | 26 ++++++++++++++++++++++++++
 2 files changed, 41 insertions(+)

```

### 2026-08-29 04:24:25Z · merging · decision

no `## Decisions` section -- nothing recorded for future planning agents to find
