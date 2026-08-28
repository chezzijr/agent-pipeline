---
id: TICKET-085
stage: done
class: feature
branch: ticket/085
test_file: tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens
files_declared:
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/daemon/supervisor.py
- tests/test_cli.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 13
  plan_files: 6
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 88d3555e-a96f-4dcb-9933-6ba381f28b40
  log: .project/logs/TICKET-085-review-88d3555e.log
approved_by: 'chezzijr (via Claude Code, while away; reviewer also filed this ticket
  -- audit in thread). Verified anchors: terminal_sink at supervisor.py:272, rec[''cap'']
  at :469, t.extra[''last_session''] at :1070 and read at cli/main.py:337 -- all from
  TICKET-077 and earlier. It respects the ticket''s fence: reporting only, no token
  cap. Step 8''s test is the one that matters -- an interactive stage emits no result
  event and must not gain a zero-dollar line.'
approved_at: '2026-08-28T09:13:11.314107+00:00'
---

## Summary

A stage's cost and token usage reach no human-readable place. `parse()`
(`pipeline/stream/events.py`) normalises `total_cost_usd` and `usage` off the
harness's `result` event; `terminal_sink()` (`pipeline/daemon/supervisor.py`)
keeps only `terminal_reason`, so the session entry `_finish()` appends to
`## Thread` names the session and the log and nothing else. Today an operator
learns a cost only when a budget kill escalates.

Planning wrote the plan. `terminal_sink()` keeps `cost_usd` and `usage` on the
child record, a new `cost_report()` renders two lines, and `_finish()` appends
them to the session entry: `- cost: $6.09 of a $10 cap` and `- tokens: 80,906
out (31,412 thinking) · 74 in · 4,393,384 cache read · 186,837 cache write`.
`pipeline ls -v` gains `cost=$6.09`. No token cap is added. An interactive
stage gets neither line -- it emits no `result` event (DEC-077).

Plan-validation passed the plan, Tier A and Tier B. All eight items pass: the
root cause is `terminal_sink()` dropping the numbers plus a fixed entry text,
the plan derives both lines from `rec` rather than hardcoding the test's string,
DEC-077, DEC-078, DEC-011 and DEC-033 all hold, and 6 files matches
`class: feature`. Implementing may work the plan as written.

Implementing executed all 13 plan steps. `cost_report()` renders the two
lines, `terminal_sink()`/`spawn()`/`_finish()` carry `cost_usd` and `usage`
onto `rec`, and `cmd_ls -v` prints `cost=$X.XX`. Committed `a53b6bc` on
`ticket/085`.

Review passed `a53b6bc` with no blocking findings. I re-ran all 8 acceptance
criteria: `uv run --group dev pytest -q tests/test_dispatch.py
tests/test_cli.py` -> `101 passed in 9.85s`, both `cost_report()` one-liners
print their specified output, and `grep -c "cost=" README.md` prints `1`. The
change matches the plan step for step and drifts from it nowhere.

Three findings were charged and all three refuted: a non-numeric `cost_usd`
cannot reach `cost_report()`, because `parse()` coerces it through `_num()`
(`pipeline/stream/events.py:93`) and `feed()` is the only production feeder;
the non-dict `usage` and the hand-edited-frontmatter `cmd_ls` crashes are
speculative and not regressions. One doc nit stands, not blocking:
`terminal_sink()`'s docstring (`supervisor.py:273`) names only
`terminal_reason` though the function now keeps `cost_usd` and `usage`.

## Reproduction

`tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens`

command: `uv run --group dev pytest -q tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens`

output:
```
AssertionError: session thread entry has no trace of the run's cost:
`plan-validation` ran as session `s1`
- replay: `claude --resume s1`
- log: `.project/logs/TICKET-001.log`
assert ('6.09' in '`plan-validation` ran as session `s1`\n- replay: `claude --resume s1`\n- log: `.project/logs/TICKET-001.log`' or '$6' in '`plan-validation` ran as session `s1`\n- replay: `claude --resume s1`\n- log: `.project/logs/TICKET-001.log`')
```
expect: AssertionError: session thread entry has no trace of the run's cost:

## Digest

Files this change touches:
- `pipeline/daemon/supervisor.py` -- `terminal_sink()` (line 272) keeps only `terminal_reason` off the `result` event; `_finish()` (line 1021) writes the session entry at line 1067 and `t.extra["last_session"]` at line 1070; `spawn()` seeds the child record at line 465.
- `pipeline/cli/main.py` -- `cmd_ls()` prints `last_session` at lines 337-340, only under `-v`.
- `tests/test_dispatch.py` -- the failing test at line 1622. `tests/test_cli.py` -- the `cli()` helper and the `ls` tests at lines 265-287.
- `README.md` lines 361-372 (the `pipeline ls -v` sample) and `CLAUDE.md` (the gotcha list).

Key functions and entry points:
- `parse()` (`pipeline/stream/events.py`) already returns `total_cost_usd` through `_num()`, so always a float, and `usage`, always a dict. This plan does not touch it.
- `rec["cap"]` is set in `spawn()` from `stage_cap(cfg, hcfg)`, and `_finish()` already names it in the budget-kill escalation. Every `max_usd` is an int (`5`, `8`, `10`), so an f-string prints `$10`, not `$10.0`.
- `Ticket.append(stage, "session", text, session=...)` is the only writer of the session entry: `grep -rn "ran as session" pipeline/` returns one hit, `pipeline/daemon/supervisor.py:1067`.

Gotchas:
- The ticket says the numbers reach no view. `pipeline metrics` is a partial exception: `cost_by_stage()` (`pipeline/cli/metrics.py:245`) renders p50 cost plus summed out, thinking and cache-read tokens per stage. It covers merged tickets only and aggregates them, so no single run's number is visible anywhere. The ticket's demand stands.
- Do not import `pipeline/cli/metrics.py` from the daemon. It imports `pipeline.daemon.store`, so daemon to cli inverts the layering, and its `_tokens()` drops `input_tokens` and cache-creation.
- An interactive stage emits no `result` event (DEC-077), so it carries no cost here. Its per-model token totals already reach the event log through `usage_events()` (`pipeline/daemon/supervisor.py:285`), called from `finish()`.
- `terminal_sink()` is fed hand-built dicts by tests, not only `parse()` output. The formatter coerces every number and never raises.
- `t.extra["last_session"]` crosses the socket (`pipeline/daemon/server.py:135`) and is read by `cmd_ls`. A ticket written before this change has no cost key, so read it with `.get`.

## Decisions checked

- DEC-077 (active). `terminal_sink()` is the one place the `result` event's `terminal_reason` is kept, and a budget kill cannot be observed for an interactive stage, which emits no `result` event. This plan extends that same sink for cost and usage, reports nothing for an interactive stage, and leaves the budget-kill escalation path unchanged.
- DEC-078 (active). `rec["cap"]` and the rendered `--max-budget-usd` flag must come from one `stage_cap()` call. The plan only reads `rec["cap"]`; it adds no second computation of the cap.
- DEC-011 (active, frozen). The event vocabulary and the `result` payload. The plan adds no event kind and no field inside `data`; `last_session` is ticket frontmatter, not an event.
- DEC-033 (active). On a Max plan the metered unit is tokens, and Opus draws on a weekly limit of its own. That is the reason to print tokens next to dollars rather than dollars alone.
- grep terms used against `/home/chezzijr/proj/agent-pipeline/.project/decisions/`: `cost`, `token`, `usage`, `total_cost_usd`, `thread entry`, `session entry`. Nothing there constrains the text of a thread entry.

## Plan

1. Add `cost_report(rec) -> str` to `pipeline/daemon/supervisor.py` directly below `terminal_sink()`: it returns `""` when `rec.get("cost_usd") is None`; otherwise it returns a newline, then `- cost: $6.09` formatted `f"${float(rec['cost_usd']):.2f}"`, then ` of a $10 cap` formatted `f" of a ${rec['cap']} cap"` only when `rec.get("cap")` is truthy, then a newline, then `- tokens: 80,906 out (31,412 thinking) · 74 in · 4,393,384 cache read · 186,837 cache write` built from `rec.get("usage") or {}` keys `output_tokens`, `output_tokens_details.thinking_tokens`, `input_tokens`, `cache_read_input_tokens` and `cache_creation_input_tokens`, each read through a local coercion `int(v or 0)` wrapped in `try/except (TypeError, ValueError)` returning `0`, each count formatted `f"{n:,}"`, with the ` (N thinking)` parenthetical omitted when thinking is 0, so a malformed `usage` renders zeros instead of raising.
2. Extend `terminal_sink()` in `pipeline/daemon/supervisor.py` so a `result` event also sets `rec["cost_usd"] = ev.get("total_cost_usd")` and `rec["usage"] = ev.get("usage") or {}`, keeping `if ev.get("terminal_reason"): rec["terminal_reason"] = ev["terminal_reason"]` inside the same `kind == "result"` branch and still calling `inner(ev)` on every event.
3. Seed the two keys in `spawn()`'s child record in `pipeline/daemon/supervisor.py`, next to `"terminal_reason": None, "cap": stage_cap(cfg, hcfg),`, as `"cost_usd": None, "usage": {},`, so every record carries them whether or not a `result` event arrives.
4. Wire the report into the entry in `_finish()` (`pipeline/daemon/supervisor.py`): append `+ cost_report(rec)` to the text passed to `t.append(stage, "session", ...)`, and add `"cost_usd": rec.get("cost_usd")` as a fourth key of the `t.extra["last_session"]` dict on the following statement.
5. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens` and confirm it prints `1 passed`, where before this change it failed with `AssertionError: session thread entry has no trace of the run's cost:` (`tests/test_dispatch.py`).
6. Strengthen `tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens` to check tokens as well as cost: after the existing assertion add `assert "- cost: $6.09" in msg` and `assert "- tokens: 80,906 out · 0 in · 4,393,384 cache read · 0 cache write" in msg`, which is what the `usage` dict the test already feeds produces, then re-run the command from step 5.
7. Add `test_the_session_entry_names_the_budget_cap_and_the_thinking_tokens` to `tests/test_dispatch.py`, built like the test above but with `"cap": 10` on `rec` and a `usage` of `{"output_tokens": 80906, "input_tokens": 74, "cache_read_input_tokens": 4393384, "cache_creation_input_tokens": 186837, "output_tokens_details": {"thinking_tokens": 31412}}`, asserting the entry holds `- cost: $6.09 of a $10 cap` and `- tokens: 80,906 out (31,412 thinking) · 74 in · 4,393,384 cache read · 186,837 cache write`.
8. Add `test_the_session_entry_omits_cost_when_no_result_event_arrived` to `tests/test_dispatch.py`: build the same `rec`, feed the sink nothing at all, call `supervisor.finish(d, rec)`, then assert `"- replay:" in msg`, `"- cost:" not in msg` and `"- tokens:" not in msg`, because an interactive stage emits no `result` event and must not gain a zero-dollar line.
9. Print the number in `cmd_ls()` (`pipeline/cli/main.py`): extend the `-v` `last:` print with ` cost=$6.09` formatted `f" cost=${last['cost_usd']:.2f}"` when `last.get("cost_usd") is not None`, reading with `.get` because a ticket written before this change has no such key.
10. Add `test_ls_v_prints_the_last_session_cost` to `tests/test_cli.py`: run `cli(d, "new", "t")`, load `d / ".project/tickets/TICKET-001.md"`, set `t.extra["last_session"] = {"stage": "planning", "id": "s1", "log": ".project/logs/x.log", "cost_usd": 6.089121}`, call `t.save()`, run `cli(d, "ls", "-v")`, and assert `cost=$6.09` is in its stdout.
11. Update the `pipeline ls -v` sample block in `README.md` under "Watching a run" so its `last:` line reads `last: review log=.project/logs/TICKET-001-review-3582ef02.log cost=$6.09`, and add one sentence below the block: "The cost is that run's own `total_cost_usd` from the harness's `result` event; the ticket's `## Thread` session entry carries the same number plus the run's token counts."
12. Add one bullet to the gotcha list in `CLAUDE.md`, directly after the "A budget kill is not a crash" bullet: "**A run's cost and tokens are reported once, in its session thread entry.** `terminal_sink()` keeps `total_cost_usd` and `usage` off the same `result` event it already reads `terminal_reason` from, and `cost_report()` renders the two lines `_finish()` appends next to the replay command. An interactive stage emits no `result` event, so it gets neither line; its tokens reach the event log through `usage_events()` instead."
13. Run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py`, confirm it exits 0, and commit every file with `git commit -am "feat(TICKET-085): report a run's cost and tokens in its session thread entry"`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens` exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_the_session_entry_names_the_budget_cap_and_the_thinking_tokens` exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_the_session_entry_omits_cost_when_no_result_event_arrived` exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_cli.py::test_ls_v_prints_the_last_session_cost` exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py` exits 0, reporting no failures and no errors.
- `uv run python -c "from pipeline.daemon.supervisor import cost_report; print(cost_report({'cost_usd': 6.089121, 'cap': 10, 'usage': {}}))"` prints `- cost: $6.09 of a $10 cap`, then
  `- tokens: 0 out · 0 in · 0 cache read · 0 cache write` on the next line.
- `uv run python -c "from pipeline.daemon.supervisor import cost_report; print(repr(cost_report({'cost_usd': None})))"` prints `''`.
- `grep -c "cost=" README.md` prints `1`.

## Decisions

**A run's cost and tokens come off the `result` event, kept on the child record
by `terminal_sink()`.** That sink already keeps `terminal_reason` from the same
event (DEC-077), and `parse()` already normalises `total_cost_usd` and `usage`
beside it. The event log holds both, but nothing reads the log back inside one
tick, so the record is the only place the numbers can reach `_finish()`.

**An interactive stage gets no cost line, deliberately.** It emits no `result`
event (DEC-077), so `rec["cost_usd"]` stays `None` and `cost_report()` returns
`""`. A zero-dollar line there would read as a free run rather than an
unmeasured one. Its per-model token totals still reach the event log through
`usage_events()`, which `finish()` calls only for `mode == "interactive"` --
calling it from `_finish()` as well would bill a merged ticket twice.

**`cost_report()` is formatting only. It must never feed a control decision.**
The harness owns budget enforcement through `--max-budget-usd` and exposes no
token flag. A second enforcer reading these numbers to kill a child would
duplicate the cap and would need a bound of its own; TICKET-085 ruled it out.

**The cap is printed next to the cost on purpose.** `$6.09` alone does not say
whether a cap is right-sized; `$6.09 of a $10 cap` does, and that is the
question TICKET-085 was filed on. Keep both numbers if this line is reworded.

**Nothing on this path may raise.** `parse()` never raises, `terminal_sink()`
runs inside the poller's read callback, and `_finish()` writes the ticket. Every
number `cost_report()` reads is coerced, and a malformed `usage` renders zeros.

## Rollback

Revert the one commit. The change is additive in every direction: `terminal_sink()`
returns to keeping `terminal_reason` alone, the session entry loses its two lines,
`pipeline ls -v` loses `cost=`, and
`tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens`
fails again with its original message. Thread entries already written keep their
cost lines as plain text, and a `last_session` dict carrying a stale `cost_usd`
key is simply not printed, because `cmd_ls` reads it with `.get`.

## Thread

### 2026-08-28 08:59:24Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-28 · triage · reproduction

Confirmed by code reading and a test. `terminal_sink()`
(`pipeline/daemon/supervisor.py`) forwards every `result` event to the inner
sink but records only `terminal_reason` onto `rec`. `_finish()`'s session
entry (`t.append(stage, "session", ...)`, same file) writes replay command
and log path only -- no cost, no tokens, even though `events.py` already
normalised `total_cost_usd` and `usage` off the same event.

Added `tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens`:
feeds a `result` event with `total_cost_usd: 6.089121` and a `usage` dict
through `terminal_sink(rec, event_sink(...))`, then calls `supervisor.finish()`
and asserts the session thread entry mentions the cost. It fails today with
no cost or token text in the entry. Committed on `ticket/085` at `c99f190`.

A `chore` fix touches `terminal_sink()` (to keep the `result` event's cost
and usage on `rec`, the same way it already keeps `terminal_reason`) and the
session-entry text in `_finish()`. Left as `ok`: the ticket's own text asks
the next stage to choose the shape (a line worked into the existing session
entry vs. a separate line), which is a design call, not a mechanical edit.

### 2026-08-28 09:01:38Z · triage · session · session=169e6d6a-825a-4834-b784-511ada5394e8

`triage` ran as session `169e6d6a-825a-4834-b784-511ada5394e8`
- replay: `claude --resume 169e6d6a-825a-4834-b784-511ada5394e8`
- log: `.project/logs/TICKET-085-triage-169e6d6a.log`

### 2026-08-28 09:01:38Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced, failing test committed

### 2026-08-28 · planning · note

Plan written. The shape the ticket left to planning: two lines appended to the
existing session entry, `- cost:` and `- tokens:`, plus `cost=$6.09` on
`pipeline ls -v`. `terminal_sink()` keeps `total_cost_usd` and `usage` on the
child record the way it already keeps `terminal_reason`.

One correction to the ticket's text, out of scope so left alone: the numbers
are not invisible in every view. `cost_by_stage()`
(`pipeline/cli/metrics.py:245`) already renders p50 cost and summed out,
thinking and cache-read tokens per stage in `pipeline metrics`. It covers
merged tickets only and aggregates them, so a single run's cost is still
unreadable, which is what the plan fixes. `pipeline metrics` is unchanged by
this plan.

Scope check: one subsystem, the child record and the session entry it feeds.
Six files, no split needed.

Not planned, deliberately: an interactive stage gets neither line. It emits no
`result` event (DEC-077), and reading its transcript in `_finish()` would
duplicate the `usage_events()` call `finish()` already makes. See
`## Decisions`.

### 2026-08-28 09:07:54Z · planning · session · session=85ae5726-635b-48bc-9f52-0251d2c2814c

`planning` ran as session `85ae5726-635b-48bc-9f52-0251d2c2814c`
- replay: `claude --resume 85ae5726-635b-48bc-9f52-0251d2c2814c`
- log: `.project/logs/TICKET-085-planning-85ae5726.log`

### 2026-08-28 09:07:54Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: terminal_sink() keeps cost and usage, cost_report() adds two lines to the session thread entry, pipeline ls -v prints the cost

### 2026-08-28 09:08:18Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens` fails as required
```
on thread entry has no trace of the run's cost:[0m
[1m[31mE         `plan-validation` ran as session `s1`[0m
[1m[31mE         - replay: `claude --resume s1`[0m
[1m[31mE         - log: `.project/logs/TICKET-001.log`[0m
[1m[31mE       assert ('6.09' in '`plan-validation` ran as session `s1`\n- replay: `claude --resume s1`\n- log: `.project/logs/TICKET-001.log`' or '$6' in '`plan-validation` ran as session `s1`\n- replay: `claude --resume s1`\n- log: `.project/logs/TICKET-001.log`')[0m

[1m[31mtests/test_dispatch.py[0m:1655: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> awaiting-approval {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_dispatch.py::[1mtest_the_session_thread_entry_reports_cost_and_tokens[0m - AssertionError: session thread entry has no trace of the run's cost:
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.09s[0m[31m ===============================[0m

```
- ok: `tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens` fails on base `main` too -- the bug is not already fixed upstream
```
sult': 0, 'plan_steps': 1, 'plan_files': 1}
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_dispatch.py::[1mtest_the_session_thread_entry_reports_cost_and_tokens[0m - AssertionError: session thread entry has no trace of the run's cost:
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.27s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-9dzl7i95/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-9dzl7i95/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 9ms[0m[0m

```

### 2026-08-28 · plan-validation · verdict

**Tier B: PASS.** Every item passes. Findings, one per item:

1. Root cause: `terminal_sink()` (`pipeline/daemon/supervisor.py:280`) reads the
   `result` event but keeps `terminal_reason` only, and `_finish()`'s entry text
   (line 1067) is fixed to session, replay and log. `parse()` already normalises
   both numbers, so nothing is missing upstream. The plan carries them on `rec`,
   the only carrier that survives to `_finish()` inside one tick.
2. Fix, not symptom: steps 1-4 derive both lines from `rec`. A hardcoded `$6.09`
   would satisfy the committed test, and it fails step 7's cap and thinking case
   and step 8's no-`result`-event case.
3. Decisions: DEC-077 holds -- the plan extends the same sink and reports nothing
   for an interactive stage. DEC-078 holds -- step 4 reads `rec["cap"]` and adds
   no second `stage_cap()` call. DEC-011 holds -- `cost_usd` goes in
   `t.extra["last_session"]`, which `ticket_rows()`
   (`pipeline/daemon/server.py:135`) passes through; it is not an event field.
   DEC-033 is the reason tokens print beside dollars.
4. Criteria are falsifiable: 8 of 8 name a command whose output changes if the
   implementation is wrong. `grep -c "cost=" README.md` prints `0` today.
5. No research left: every step names a file and a function.
6. Riskiest step: step 2, which runs inside the poller's read callback. The plan
   states its fallback -- coercion returns `0`, `cost_report()` returns `""` when
   `cost_usd is None`, and `## Rollback` reverts one commit.
7. Regression surface: only `tests/test_dispatch.py:1652` greps `ran as session`,
   and `tests/test_daemon.py:472` checks row keys as a subset, so a new
   `last_session` key does not break it.
8. Blast radius: `class: feature`, 6 files, one subsystem. Matches.

Two notes, neither scored against the plan:
- Step 12 (the `CLAUDE.md` bullet) is the one step no acceptance criterion covers.
- `cost_report()` returns a leading newline, so criterion 6's `print()` emits a
  blank line before `- cost: $6.09 of a $10 cap`. Read that criterion as "these
  two lines appear", not as exact stdout.

### 2026-08-28 09:12:15Z · plan-validation · session · session=ddfe3be2-508b-49d3-8ecc-247eae007924

`plan-validation` ran as session `ddfe3be2-508b-49d3-8ecc-247eae007924`
- replay: `claude --resume ddfe3be2-508b-49d3-8ecc-247eae007924`
- log: `.project/logs/TICKET-085-plan-validation-ddfe3be2.log`

### 2026-08-28 09:12:15Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan validated: root cause named, DEC-077/078/011/033 complied with, criteria falsifiable, 6 files matches class feature

### 2026-08-28 09:13:11Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Verified anchors: terminal_sink at supervisor.py:272, rec['cap'] at :469, t.extra['last_session'] at :1070 and read at cli/main.py:337 -- all from TICKET-077 and earlier. It respects the ticket's fence: reporting only, no token cap. Step 8's test is the one that matters -- an interactive stage emits no result event and must not gain a zero-dollar line.

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Verified anchors: terminal_sink at supervisor.py:272, rec['cap'] at :469, t.extra['last_session'] at :1070 and read at cli/main.py:337 -- all from TICKET-077 and earlier. It respects the ticket's fence: reporting only, no token cap. Step 8's test is the one that matters -- an interactive stage emits no result event and must not gain a zero-dollar line.**

### 2026-08-28 09:13:34Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-28 09:08:18Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_dispatch.py::test_the_session_thread_entry_reports_cost_and_tokens` fails on base `main` too -- the bug is not already fixed upstream
```
ult': 0, 'plan_steps': 1, 'plan_files': 1}
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_dispatch.py::[1mtest_the_session_thread_entry_reports_cost_and_tokens[0m - AssertionError: session thread entry has no trace of the run's cost:
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.28s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-u9eqs1di/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-u9eqs1di/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-28 09:13:35Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-28 · implementing · todo

**implementing todo** (plan steps 1-13):

1. [x] cost_report(rec) in supervisor.py
2. [x] extend terminal_sink() to keep cost_usd/usage
3. [x] seed cost_usd/usage in spawn()'s rec
4. [x] wire report into _finish() entry text + last_session
5. [x] confirm failing test passes
6. [x] strengthen that test with cost+token assertions
7. [x] add cap/thinking test
8. [x] add no-result-event test
9. [x] print cost in cmd_ls -v
10. [x] add test_ls_v_prints_the_last_session_cost
11. [x] update README sample + sentence
12. [x] add CLAUDE.md gotcha bullet
13. [x] run full test_dispatch.py + test_cli.py, commit

### 2026-08-28 · implementing · done

Implemented all 13 plan steps as written. `cost_report()` renders the two
lines from `rec["cost_usd"]`/`rec["cap"]`/`rec["usage"]`; `terminal_sink()`
now keeps `cost_usd` and `usage` off the `result` event alongside
`terminal_reason`; `spawn()` seeds both keys `None`/`{}`; `_finish()` appends
`cost_report(rec)` to the session entry and adds `cost_usd` to
`t.extra["last_session"]`; `cmd_ls -v` prints ` cost=$X.XX` when present.

Confirmed RED first: the committed test failed with the exact message quoted
in `## Reproduction`. After steps 1-4 it passed, then I strengthened it
(step 6) and added the two new tests from steps 7-8; both passed without
further code changes, confirming `cost_report()` already matched the plan's
cap/thinking and no-event cases.

`uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py` ->
`101 passed`. All 8 acceptance criteria commands verified individually,
matching the outputs specified in `## Acceptance criteria` exactly,
including `grep -c "cost=" README.md` -> `1`.

Committed `a53b6bc`: "feat(TICKET-085): report a run's cost and tokens in
its session thread entry", 6 files changed (matches `## Digest`'s file list).

### 2026-08-28 09:16:29Z · implementing · session · session=9b5a4f6a-727a-413d-a3d2-734d29537cc6

`implementing` ran as session `9b5a4f6a-727a-413d-a3d2-734d29537cc6`
- replay: `claude --resume 9b5a4f6a-727a-413d-a3d2-734d29537cc6`
- log: `.project/logs/TICKET-085-implementing-9b5a4f6a.log`

### 2026-08-28 09:16:29Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented cost_report(), wired terminal_sink/spawn/_finish and cmd_ls -v, all 8 acceptance criteria verified, committed a53b6bc

### 2026-08-28 · review · findings

**review of `a53b6bc` (delta `c99f190..a53b6bc`, 6 files): PASS, no blocking
findings.**

I re-ran every acceptance criterion. `uv run --group dev pytest -q
tests/test_dispatch.py tests/test_cli.py` -> `101 passed in 9.85s`.
`cost_report({'cost_usd': 6.089121, 'cap': 10, 'usage': {}})` prints
`- cost: $6.09 of a $10 cap` then
`- tokens: 0 out · 0 in · 0 cache read · 0 cache write`;
`cost_report({'cost_usd': None})` prints `''`;
`grep -c "cost=" README.md` prints `1`.

I charged three findings and refuted all three:

1. Nit. `cost_report()` raises `ValueError` on a non-numeric `cost_usd` --
   `float('abc')`. Unreachable: `parse()` coerces it through `_num()`
   (`pipeline/stream/events.py:93`), and `feed()` is the only production
   feeder (`events.py:152`, `supervisor.py:228`).
2. Nit. `cost_report()` raises `AttributeError` on a truthy non-dict `usage`
   (a list). Reachable only if the harness emits `"usage": [...]`;
   `output_tokens_details` is already `isinstance`-guarded
   (`supervisor.py:311`). Speculative, not blocking.
3. Nit. `cmd_ls -v` raises on a hand-edited non-numeric `cost_usd`
   (`pipeline/cli/main.py:339`). Same class as the existing `last['stage']`
   `KeyError` on the next line. Not a regression.

Doc nit: `terminal_sink()`'s docstring (`supervisor.py:273`) still names only
`terminal_reason`; the function now keeps `cost_usd` and `usage` too.

`_finish()` appends the session entry before every escalation path
(`supervisor.py:1106`, escalations from `:1114`), so a budget kill keeps its
cost line. Working tree clean: `git status --porcelain` printed nothing.

### 2026-08-28 09:19:09Z · review · session · session=88d3555e-a96f-4dcb-9933-6ba381f28b40

`review` ran as session `88d3555e-a96f-4dcb-9933-6ba381f28b40`
- replay: `claude --resume 88d3555e-a96f-4dcb-9933-6ba381f28b40`
- log: `.project/logs/TICKET-085-review-88d3555e.log`

### 2026-08-28 09:19:09Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review passed: all 8 acceptance criteria reproduced, 101 passed, no blocking findings; 3 non-blocking nits appended

### 2026-08-28 09:19:32Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-28 09:19:33Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/085


Rebasing (1/2)Rebasing (2/2)Successfully rebased and updated refs/heads/ticket/085.
Already up to date.
Updating 837ca22..af70de2
Fast-forward
 CLAUDE.md                     |   6 +++
 README.md                     |   6 ++-
 pipeline/cli/main.py          |   4 +-
 pipeline/daemon/supervisor.py |  49 +++++++++++++++++--
 tests/test_cli.py             |  16 +++++++
 tests/test_dispatch.py        | 107 ++++++++++++++++++++++++++++++++++++++++++
 6 files changed, 182 insertions(+), 6 deletions(-)

```

### 2026-08-28 09:19:33Z · merging · decision

decision recorded as `DEC-085`
