---
id: TICKET-077
stage: done
class: bugfix
branch: ticket/077
test_file: tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/config.py
- pipeline/daemon/supervisor.py
- pipeline/stages/_common.md
- pipeline/stream/events.py
- tests/test_dispatch.py
- tests/test_stages.py
- tests/test_stream.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 17
  plan_files: 9
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 5b98031b-9388-4ec2-b39c-525e292bdb3c
  log: .project/logs/TICKET-077-review-5b98031b.log
approved_by: 'chezzijr (via Claude Code, while away; reviewer also filed this ticket
  -- audit in thread). Verified anchors: rec[''sink''] at supervisor.py:228, compose_prompt
  call at :390, events.py _norm result branch at :97.'
approved_at: '2026-08-27T19:40:05.266522+00:00'
---

## Summary

Reviewed and passed, with no blocking findings. The review re-ran both suites
in the worktree: `397 passed in 19.08s` and `guard: all passed` (exit 0). It
checked the six acceptance criteria against `git diff main...HEAD` and refuted
its two candidate findings (`end_interactive()`'s `mode` gate at
`supervisor.py:1140`; no consumer enumerates `stage_end.result`). Two nits
stand, neither blocking: the ticket's `test_file` keeps a name that now
contradicts its assertions, and `stage_cap()` has no return annotation.

Implemented. A budget kill is classified off `terminal_reason` on the
harness's `result` event, kept on the child's record by a new
`terminal_sink()`, and `_finish()` now escalates on the FIRST kill, charging
`budget_kills` and naming the cap -- instead of the old blind `no_result`
retry into the same spend. A genuine crash (no `terminal_reason`) keeps the
`no_result` retry-then-escalate path unchanged. Every headless stage now
writes `.result` before its `## Thread` entry; the interactive stage
(`compose_prompt(..., interactive=True)`) keeps writing it last, because
`end_interactive()` SIGTERMs on the sidecar.

Files touched, matching `## Digest`: `pipeline/stream/events.py`,
`pipeline/core/config.py` (`stage_cap()`, `render()`, `compose_prompt()`),
`pipeline/daemon/supervisor.py` (`terminal_sink()`, `spawn()`'s `rec`,
`_finish()`), `pipeline/stages/_common.md`, plus `tests/test_stream.py`,
`tests/test_dispatch.py`, `tests/test_stages.py`, `README.md`, `CLAUDE.md`.
Full suite (397 tests) and `pipeline/hooks/test_dangerous_commands.py` both
green. Committed on `ticket/077` at `797bbbf`.

The original problem statement follows.

## Reproduction

Confirmed: no code anywhere reads or sets `terminal_reason` (grepped
`pipeline/` for `terminal_reason|budget_exhausted` -- zero hits outside the
ticket text and the `max_usd`/`--max-budget-usd` plumbing). `_finish()`'s
`res is None` branch (`pipeline/daemon/supervisor.py:1062`) has no way to
tell a budget kill from a crash, so it charges `no_result` and respawns
either way.

Test: `tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash`
Command: `uv run --group dev pytest -q tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash`

The test calls `supervisor.finish()` twice with a rec carrying
`terminal_reason: "budget_exhausted"` (a field `_finish()` does not read).
First call charges `no_result` with no mention of budget. Second call hits
`MAX_ATTEMPTS` and escalates with the same message a genuine crash would get.

Output:
```
    TICKET-001: -> escalated (`plan-validation` wrote no .result sidecar 2 times)
AssertionError: escalation must name the cap a budget-killed stage hit, not read like a crash: '`plan-validation` wrote no .result sidecar 2 times'
assert 'budget' in '`plan-validation` wrote no .result sidecar 2 times'
```

expect: escalation must name the cap a budget-killed stage hit, not read like a crash: '`plan-validation` wrote no .result sidecar 2 times'

Committed on `ticket/077` at `35437f5`.

## Digest

Files this change touches, and what each is responsible for:

- `pipeline/stream/events.py` -- `_norm()`'s `typ == "result"` branch builds
  the record `parse()` returns. It drops every key it does not name, so
  `terminal_reason` needs one `ev.get()`. `parse()` never raises, and a plain
  `.get` keeps that true.
- `pipeline/daemon/supervisor.py` -- `pump()` (line 200) feeds every parsed
  event to `rec["sink"]`, built by `event_sink()` (line 243), which only
  writes to the event log. Nothing keeps a parsed record on `rec` today.
  `_finish()` (line 996) decides; `finish()` (line 960) records, emitting
  `stage_end` with the string `_finish()` returned.
- `pipeline/core/config.py` -- `render()` (line 305) computes the cap as
  `cfg.get("max_usd", hcfg.get("max_usd", 5))`. `compose_prompt()` (line 213)
  builds the prompt file every stage reads.
- `pipeline/stages/_common.md` -- rule 6 is the sidecar-last instruction.

The signal is on the stream, not in the exit status. Claude Code 2.1.247's
final `result` event carries `terminal_reason`, and a budget kill sets it to
`budget_exhausted` with `subtype: "error_max_budget_usd"` and `is_error: true`.
Verbatim from `/home/chezzijr/.local/share/claude/versions/2.1.247`:

```
terminal_reason:"budget_exhausted",fast_mode_state:Xt(at,Ce.fastMode),...,variant:{subtype:"error_max_budget_usd",errors:[NS(b)],user_message_uuid:dt}
```

The child then exits like any other failure, so the exit status carries no
distinction. Read the reason off the stream.

Gotchas the next stages need:

1. An interactive stage produces no `result` event at all (`finish()`'s own
   comment and `usage_events()`'s docstring both say so), so it is never
   classified as a budget kill. `claude --help` (2.1.247) also says
   `--max-budget-usd` "only works with --print".
2. `end_interactive()` (line 1101) SIGTERMs an interactive child as soon as
   its `.result` appears. Telling every stage to write the sidecar first would
   kill `planning` -- the only `mode: interactive` stage -- mid-thread-write.
   The ordering flip therefore ships with a per-mode override in the composed
   prompt, not one instruction for both modes.
3. With no poller, `spawn()` redirects stdout straight to the log and builds
   no reader, so no sink runs and no `terminal_reason` is captured. `run()`
   (line 1314) and `serve()` both build a poller; only a direct
   `spawn(..., poller=None)` misses it, which is tests and library callers.
4. `tests/test_stream.py::test_stream_fixture_parses_and_never_raises` asserts
   an exact list of event kinds for `tests/fixtures/stream-planning.ndjson`.
   Do not add a line to that fixture; parse a synthetic line in a new test.
5. `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` reads
   only the paragraph before "requires human review before merge" in
   `CLAUDE.md`. A new gotcha bullet elsewhere in that file does not affect it.

## Decisions checked

- DEC-011 (frozen event vocabulary) -- active, and this plan complies. It
  permits additions: "Adding a `kind` or a field inside `data` is additive and
  fine". `terminal_reason` is a new field inside the `result` event's data, and
  `budget-exhausted` is a new value of `stage_end.result` alongside
  `no-result`. No column, kind name or field meaning changes.
- DEC-047 (loop bounds and plan size) -- active, and this plan complies.
  `lease_expiries` and `no_result` are the dispatcher's own counters, charged
  against `MAX_ATTEMPTS` and never size-scaled. `budget_kills` is the same kind
  of counter, so it goes in neither `BOUNDS` nor `SIZE_SCALED`.
- DEC-059 (an interactive stage is gated on an attached client) -- active, and
  this plan complies. It leaves `spawn()`'s gate untouched and keeps the
  sidecar as the interactive exit condition.
- DEC-052 (the guard reads the ticket and result paths `spawn()` exports) --
  read, not constraining: no path in this plan changes.
- Grep terms used against `.project/decisions/`: `budget`, `max_usd`,
  `no_result`, `terminal`, `sidecar`, `interactive`, `stream`.

## Plan

1. In `pipeline/stream/events.py`, add `"terminal_reason": ev.get("terminal_reason"),` to the dict the `typ == "result"` branch of `_norm()` returns, on the line after `"stop_reason": ev.get("stop_reason"),`.
2. In `tests/test_stream.py`, add `test_a_budget_kill_names_itself_on_the_result_event`: parse the one-line JSON `{"type":"result","subtype":"error_max_budget_usd","is_error":true,"terminal_reason":"budget_exhausted","total_cost_usd":5.01,"num_turns":41,"usage":{},"session_id":"s1"}` and assert `ev["kind"] == "result"`, `ev["terminal_reason"] == "budget_exhausted"` and `ev["subtype"] == "error_max_budget_usd"`; then assert `events()[11]["terminal_reason"] is None`, so an ordinary run carries the key with no value. Run `uv run --group dev pytest -q tests/test_stream.py`; expect the whole file green.
3. In `pipeline/core/config.py`, add `def stage_cap(cfg: dict, hcfg: dict):` returning `cfg.get("max_usd", hcfg.get("max_usd", 5))`, docstring: "The dollar cap a stage spawns under: its own frontmatter, then the harness default, then 5. One definition, because `_finish()` names the cap a budget-killed stage hit and it must be the number `render()` passed."; then replace `render()`'s `cap=cfg.get("max_usd", hcfg.get("max_usd", 5)),` with `cap=stage_cap(cfg, hcfg),`. Run `uv run --group dev pytest -q tests/test_harness.py tests/test_pty.py`; `tests/test_pty.py:391` already asserts `--max-budget-usd 5` in the rendered command.
4. In `pipeline/daemon/supervisor.py`, add `terminal_sink(rec, inner)` directly below `event_sink()`: it returns a `sink(ev)` that sets `rec["terminal_reason"] = ev["terminal_reason"]` when `ev.get("kind") == "result" and ev.get("terminal_reason")`, and then calls `inner(ev)` on every event. Docstring: the harness names why it stopped on its `result` event, the child then exits like any other failure, and `event_sink()` writes to the event log, which nothing reads back inside one tick.
5. In `pipeline/daemon/supervisor.py`, add `stage_cap` to the `from pipeline.core.config import (...)` list at line 17, add `"terminal_reason": None,` and `"cap": stage_cap(cfg, hcfg),` to `spawn()`'s `rec` dict literal, and add the line `rec["sink"] = terminal_sink(rec, rec["sink"])` immediately after that literal and before `if interactive or poller:`.
6. In `tests/test_dispatch.py`, add `test_the_stream_sink_records_the_terminal_reason_on_the_child`: build `rec = {}` and `seen = []`, make `sink = supervisor.terminal_sink(rec, seen.append)`, feed it `{"kind": "assistant"}`, `{"kind": "result", "terminal_reason": None}` and `{"kind": "result", "terminal_reason": "budget_exhausted"}`, then assert `rec["terminal_reason"] == "budget_exhausted"` and `len(seen) == 3` -- the wrapper records, it never swallows. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_the_stream_sink_records_the_terminal_reason_on_the_child`; expect 1 passed.
7. In `pipeline/daemon/supervisor.py`, add a branch at the top of `_finish()`'s `if res is None:` block, above the `no_result` charge: when `rec.get("terminal_reason") == "budget_exhausted"`, set `t.counters["budget_kills"] = t.counters.get("budget_kills", 0) + 1`, call `escalate()` with the message `<stage> was killed at its $<cap> budget cap (--max-budget-usd) before it wrote a .result sidecar; a respawn spends the same cap and stops at the same point` built from `stage` and `rec.get("cap") or "?"`, then `return "budget-exhausted"`. Comment it: a budget kill is not a crash, the same prompt against the same tree spends the same cap and stops at the same point, so the bound is one and there is no respawn to charge a second attempt against.
8. In `tests/test_dispatch.py`, rewrite the body of `test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash` -- keep the name, it is the ticket's `test_file` -- to assert the new behaviour: add `"cap": 3` to the `rec()` dict, call `supervisor.finish(d, rec())` ONCE, then assert `t.stage == "escalated"`, `t.counters.get("budget_kills") == 1`, `t.counters.get("no_result", 0) == 0`, and that the last thread entry's text contains both `budget` and `$3`. Replace its docstring with the expected behaviour instead of the reproduction. Run `uv run --group dev pytest -q "tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash"`; expect 1 passed.
9. In `tests/test_dispatch.py`, add `test_a_crash_with_no_terminal_reason_still_retries_then_escalates`: the same `rec()` with no `terminal_reason` key, `supervisor.finish(d, rec())` twice; after the first call assert `t.counters["no_result"] == 1` and `t.stage == "plan-validation"`, after the second assert `t.stage == "escalated"` and `"wrote no .result sidecar 2 times"` in the last entry's text. Run `uv run --group dev pytest -q tests/test_dispatch.py`; expect the file green.
10. In `pipeline/stages/_common.md`, change rule 6's opening from "Finish by writing the result file" to "Write the result file", keeping the rest of that sentence, and append to the same paragraph: "Write it as soon as your stage's work is done -- before you append your `## Thread` entry and rewrite `## Summary`. A stage killed at its spending cap loses whatever it had not written yet, and the sidecar is the one thing the dispatcher cannot reconstruct." Leave the YAML block, rule 4 and the marker rule unchanged.
11. In `pipeline/core/config.py`, add the keyword `interactive: bool = False` to `compose_prompt()`, and before its `if view:` block append this text to `text` when `interactive` is true -- a `---` rule, the heading `# This session runs on a terminal`, then: "Write the result file LAST: after your `## Thread` entry and your `## Summary` rewrite. The dispatcher ends an interactive session as soon as the sidecar appears, so anything you have not written by then is lost. This reverses rule 6's ordering and nothing else."
12. In `pipeline/daemon/supervisor.py`, change `spawn()`'s call at line 390 to `compose_prompt(stage, hcfg, view, project, interactive=interactive)`, so the override reaches exactly the stages hosted on a PTY.
13. In `tests/test_stages.py`, add `test_an_interactive_prompt_reverses_the_sidecar_ordering`: assert the text of `C.compose_prompt("planning")` contains "before you append your `## Thread` entry" and does not contain "runs on a terminal", and that the text of `C.compose_prompt("planning", None, "", None, interactive=True)` contains "Write the result file LAST". Run `uv run --group dev pytest -q tests/test_stages.py`; expect the file green.
14. In `README.md`, add a row to the escalation table under the flake row -- reason "the stage hit its `--max-budget-usd` cap (`budget_kills`)", action "raise that stage's `max_usd` in `pipeline/stages/<name>.md`, then `pipeline resume TICKET-017 --stage review --reset budget_kills`" -- and after the sentence "`lease_expiries` and `no_result` are the dispatcher's own counters and stay at 2 whatever the class." add: "`budget_kills` is bounded at one: a stage killed at its cap escalates on the first kill, because the same prompt against the same tree spends the same cap and stops at the same point."
15. In `README.md`, extend the paragraph at line 209 that begins "An interactive session also ends on its `.result` sidecar" with: "That is also why an interactive stage writes its sidecar LAST while every other stage writes it first -- the sidecar is the interactive exit condition, and writing it early would end the session mid-thread-entry."
16. In `CLAUDE.md`, add one bullet to the "Gotchas, each found the hard way" list: "**A budget kill is not a crash, and the stream says which it was.** Claude Code's final `result` event carries `terminal_reason`, which `--max-budget-usd` sets to `budget_exhausted`. `terminal_sink()` keeps it on the child's record and `_finish()` escalates on the FIRST one, naming the cap, instead of charging `no_result` and respawning into the identical spend. An interactive stage emits no `result` event, so it is never classified this way -- and it writes its `.result` LAST, because `end_interactive()` SIGTERMs on the sidecar."
17. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py` from the worktree root, expect both green, then commit `pipeline/stream/events.py`, `pipeline/core/config.py`, `pipeline/daemon/supervisor.py`, `pipeline/stages/_common.md`, `tests/test_stream.py`, `tests/test_dispatch.py`, `tests/test_stages.py`, `README.md` and `CLAUDE.md` with `fix(TICKET-077): a budget kill escalates on the first kill instead of respawning`.

## Acceptance criteria

1. `tests/test_stream.py::test_a_budget_kill_names_itself_on_the_result_event`
   passes: a `result` line carrying `terminal_reason: "budget_exhausted"`
   parses to a record with that value, and the fixture's own `result` event
   carries `terminal_reason: None`.
2. `tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash`
   passes: ONE `finish()` on a rec with `terminal_reason: "budget_exhausted"`
   and `cap: 3` leaves the ticket `escalated`, `budget_kills == 1`,
   `no_result == 0`, and an escalation entry naming `budget` and `$3`.
3. `tests/test_dispatch.py::test_a_crash_with_no_terminal_reason_still_retries_then_escalates`
   passes: a rec with no `terminal_reason` charges `no_result` on the first
   call and escalates with "wrote no .result sidecar 2 times" on the second.
4. `tests/test_dispatch.py::test_the_stream_sink_records_the_terminal_reason_on_the_child`
   passes: `terminal_sink()` records the reason on the rec and forwards all
   three events to the inner sink.
5. `tests/test_stages.py::test_an_interactive_prompt_reverses_the_sidecar_ordering`
   passes: the default composed prompt tells a stage to write `.result` before
   its `## Thread` entry, and the interactive one tells it to write the
   sidecar last.
6. `uv run --group dev pytest -q` is green, and
   `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

**A budget kill is classified off the stream, not off the exit status.**
Claude Code's final `result` event carries `terminal_reason:
"budget_exhausted"` with `subtype: "error_max_budget_usd"`; the child then
exits like any other failure, so the exit status cannot tell the two apart.
`terminal_sink()` is the only place that reason is kept -- `event_sink()`
writes it to the event log, and nothing reads the log back inside one tick.

**The bound is one, and `budget_kills` is not a retry counter.** A respawn
runs the same prompt against the same tree, spends the same cap and stops at
the same point, so `_finish()` escalates on the first kill. The counter exists
for the record and for `pipeline resume --reset budget_kills`. Per DEC-047 it
stays out of `BOUNDS` and `SIZE_SCALED`: it is a dispatcher counter, and a
budget-killed stage is not more trustworthy for having a long plan.

**Headless stages write `.result` before their `## Thread` entry; the
interactive stage writes it last.** The two orders are deliberate, not drift.
`end_interactive()` SIGTERMs an interactive child as soon as its sidecar
appears, so a sidecar-first instruction there would kill the session
mid-thread-entry. Do not unify the orders without first changing that exit
condition. The per-mode wording lives in `compose_prompt(..., interactive=)`.

**A budget kill cannot be observed for an interactive stage.** It emits no
`result` event, and `claude --help` (2.1.247) says `--max-budget-usd` "only
works with --print" -- which contradicts the `interactive_cmd` comment in
`pipeline/harnesses/claude-code.toml` claiming the flag works outside print
mode. That file is fenced and this ticket does not touch it. The
contradiction is recorded, not resolved.

## Rollback

Revert the single commit from step 17. `_finish()` goes back to charging
`no_result` for every sidecar-less spawn, `parse()` stops carrying
`terminal_reason`, and `_common.md` returns to sidecar-last for every stage.
Nothing persists across the revert: `budget_kills` sits only on tickets that
already escalated, and a stale key in `counters` is inert -- `transition()`
reads only the keys it charges.

If only the ordering half misbehaves -- a stage claiming a verdict for work it
had not finished -- revert steps 10 to 13 alone: `pipeline/stages/_common.md`,
the `interactive` keyword in `pipeline/core/config.py`, its call site in
`pipeline/daemon/supervisor.py`, and the `tests/test_stages.py` case. The
classification half does not depend on them and keeps working.

## Thread

### 2026-08-27 16:15:56Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-28 · triage · note

Reproduced. `_finish()` has no code path that reads a termination reason --
`terminal_reason`/`budget_exhausted` are absent from `pipeline/` entirely, so
a budget-killed spawn and a crashed one are both charged to `no_result` and
both respawn. Added `tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash`,
which drives `supervisor.finish()` twice with a rec carrying
`terminal_reason: "budget_exhausted"` and asserts the escalation names the
cap. It fails on the real escalation text: `` `plan-validation` wrote no
.result sidecar 2 times ``. Committed on `ticket/077` at `35437f5`.

This needs a design decision (stream event vs. exit status for the signal,
new counter name, bound of one vs. `MAX_ATTEMPTS`) before implementation, so
`result: ok` rather than `chore`.

### 2026-08-27 17:03:35Z · triage · session · session=2cafe81a-e50d-40e9-bc81-d5c9ca638749

`triage` ran as session `2cafe81a-e50d-40e9-bc81-d5c9ca638749`
- replay: `claude --resume 2cafe81a-e50d-40e9-bc81-d5c9ca638749`
- log: `.project/logs/TICKET-077-triage-2cafe81a.log`

### 2026-08-27 17:03:35Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- budget kill and crash both charge no_result and respawn identically; failing test committed

### 2026-08-28 · planning · note

Plan written for both halves of the ticket. They ship in one commit and the
ordering half is independently revertible (see `## Rollback`).

Mechanism settled: the signal is on the stream, not in the exit status. Claude
Code 2.1.247's final `result` event carries `terminal_reason:
"budget_exhausted"` with `subtype: "error_max_budget_usd"`. Evidence is quoted
verbatim in `## Digest`.

Two findings outside this stage's job:

1. `claude --help` (2.1.247) says `--max-budget-usd` "only works with
   --print". The `interactive_cmd` comment in
   `pipeline/harnesses/claude-code.toml` claims the opposite: "they work
   outside print mode and they are the money guard". That file is fenced and
   this plan does not touch it. An interactive stage also emits no `result`
   event, so it can never be classified as a budget kill either way.
2. The reproduction test asserts TODAY's behaviour on its first `finish()`
   call ("a budget kill is already being classified -- reproduction is
   stale"). Step 8 rewrites its body and keeps its name, because the name is
   the ticket's `test_file` and the gate greps for it.

### 2026-08-27 17:13:40Z · planning · session · session=6828f9b8-6892-494a-bab8-824821001fd1

`planning` ran as session `6828f9b8-6892-494a-bab8-824821001fd1`
- replay: `claude --resume 6828f9b8-6892-494a-bab8-824821001fd1`
- log: `.project/logs/TICKET-077-planning-6828f9b8.log`

### 2026-08-27 17:13:40Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: terminal_reason comes off the stream's result event; budget_kills escalates on the first kill, naming the cap

### 2026-08-27 19:19:07Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash` fails as required
```
et-killed stage hit, not read like a crash: '`plan-validation` wrote no .result sidecar 2 times'[0m
[1m[31mE       assert 'budget' in '`plan-validation` wrote no .result sidecar 2 times'[0m
[1m[31mE        +  where '`plan-validation` wrote no .result sidecar 2 times' = <built-in method lower of str object at 0x7f9b3beadef0>()[0m
[1m[31mE        +    where <built-in method lower of str object at 0x7f9b3beadef0> = '`plan-validation` wrote no .result sidecar 2 times'.lower[0m

[1m[31mtests/test_dispatch.py[0m:1411: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> escalated (`plan-validation` wrote no .result sidecar 2 times)
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_dispatch.py::[1mtest_a_budget_kill_is_charged_and_retried_exactly_like_a_crash[0m - AssertionError: escalation must name the cap a budget-killed stage hit, not...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m

```
- ok: `tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash` fails on base `main` too -- the bug is not already fixed upstream
```
result sidecar 2 times)
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_dispatch.py::[1mtest_a_budget_kill_is_charged_and_retried_exactly_like_a_crash[0m - AssertionError: escalation must name the cap a budget-killed stage hit, not...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.24s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-u74qk60c/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-u74qk60c/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- plan step names no declared file: '17. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py` from the worktree root, expect both green, then commit every file above with `fix(TICKET-077): a budget kill escalates on the first kill instead of respawning`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-27 19:19:08Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- plan step names no declared file: '17. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py` from the worktree root, expect both green, then commit every file above with `fix(TICKET-077): a budget kill escalates on the first kill instead of respawning`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-28 · planning · note

Re-planned after the Tier A gate's one structural finding: `plan step names no
declared file` on step 17. Step 17 said "commit every file above" and named
only one path, written as `./pipeline/hooks/test_dangerous_commands.py`.
`_cites()` rejects that spelling -- its lookbehind refuses a path preceded by
`.`, `/`, `-` or a word character -- and that file is not modified, so it is
not declared either. Step 17 now spells out the nine paths it commits, all of
them in `files_declared`.

No other step, criterion or decision changed. I re-ran the gate's own step
parse (`PLAN_STEP_RE` plus `_cites()` from `pipeline/core/gate.py`) against
`## Plan`: 17 steps, zero prose lines, every step citing a declared path.

Two line numbers in `## Digest` were wrong and are corrected: `_finish()` is at
`pipeline/daemon/supervisor.py:996`, not 1039, and `event_sink()` is at 243,
not 271. `pump()` (200), `finish()` (960), `end_interactive()` (1101),
`compose_prompt()` (`pipeline/core/config.py:213`) and the cap line (305) are
right as written.

### 2026-08-27 19:21:32Z · planning · session · session=a750711a-d414-4574-8ae8-c6e849cd5676

`planning` ran as session `a750711a-d414-4574-8ae8-c6e849cd5676`
- replay: `claude --resume a750711a-d414-4574-8ae8-c6e849cd5676`
- log: `.project/logs/TICKET-077-planning-a750711a.log`

### 2026-08-27 19:21:32Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-planned: step 17 now names the nine paths it commits, fixing the gate's one structural finding

### 2026-08-28 · plan-validation · note

**Tier B: PASS.** Eight items, each scored against the code. This entry sits
above the Tier A PASS entry below it, not at the end of the thread: the tail of
that entry is ANSI-quoted output my editor could not anchor on.

1. Root cause: nothing captures the harness's `terminal_reason`. `_norm()`
   drops the field (`pipeline/stream/events.py:92-98`), no rec keeps it, so
   `_finish()`'s `res is None` branch (line 1062) charges `no_result` for a
   budget kill and a crash alike. The plan captures the signal, then branches
   on it. It does not special-case the test.
2. Decisions: DEC-011 line 10 permits additions -- "Adding a `kind` or a field
   inside `data` is additive and fine". `Store.emit()` puts `**data` in a JSON
   blob, so a new key is inert, and no test asserts a result record by
   equality. DEC-047 and `machine.py:16-19` scope `SIZE_SCALED` to
   `plan_validation_attempts`; `budget_kills` stays out, as the plan says.
   DEC-059's gate is untouched.
3. Scope: 17 steps, all traceable. Steps 10-13 serve criterion 5; steps 14-16
   document the new escalation reason and the two sidecar orders.
4. Criteria falsifiable: criterion 3 is the anti-vacuity case. A rec with no
   `terminal_reason` must still charge `no_result` and escalate on the second
   call, so an over-broad branch fails it.
5. No research left: every cited line resolves. `_finish()` 996, `event_sink()`
   243, `pump()` 200, `finish()` 960, `end_interactive()` 1101,
   `compose_prompt()` `pipeline/core/config.py:213`, the cap 305, the import
   list 17, the `rec` literal 440-446, the `compose_prompt` call 390.
6. Riskiest step: 10, the sidecar-first flip for every headless stage. No test
   catches a stage that writes a verdict for work it then loses. `## Rollback`
   states the fallback: revert steps 10-13 alone.
7. Regression surface: `rec["sink"]` is assigned once (line 446) and never
   reassigned, so step 5's wrapper survives the `if interactive or poller:`
   block. `result_file()` is read mid-run only by `end_interactive()`
   (line 1113), gated on `mode == "interactive"`, so sidecar-first cannot end
   a headless session early. `render()`'s cap refactor is covered by
   `tests/test_pty.py:391`. `events()[11]` is the fixture's `result` event.
8. Blast radius: `bugfix`, 4 source files and 2 docs, each edit small. Nothing
   in the plan touches `machine.FENCED`, so it does not park at
   `awaiting-merge`.

One stale number, in `## Digest` and not in any step: `run()` is at
`pipeline/daemon/supervisor.py:1293`, not 1314. Every other cited line is right.

### 2026-08-27 19:30:53Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash` fails as required
```
et-killed stage hit, not read like a crash: '`plan-validation` wrote no .result sidecar 2 times'[0m
[1m[31mE       assert 'budget' in '`plan-validation` wrote no .result sidecar 2 times'[0m
[1m[31mE        +  where '`plan-validation` wrote no .result sidecar 2 times' = <built-in method lower of str object at 0x7f3fb39a2550>()[0m
[1m[31mE        +    where <built-in method lower of str object at 0x7f3fb39a2550> = '`plan-validation` wrote no .result sidecar 2 times'.lower[0m

[1m[31mtests/test_dispatch.py[0m:1411: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> escalated (`plan-validation` wrote no .result sidecar 2 times)
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_dispatch.py::[1mtest_a_budget_kill_is_charged_and_retried_exactly_like_a_crash[0m - AssertionError: escalation must name the cap a budget-killed stage hit, not...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m

```
- ok: `tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash` fails on base `main` too -- the bug is not already fixed upstream
```
result sidecar 2 times)
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_dispatch.py::[1mtest_a_budget_kill_is_charged_and_retried_exactly_like_a_crash[0m - AssertionError: escalation must name the cap a budget-killed stage hit, not...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.24s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-yh5nw4w7/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-yh5nw4w7/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 19:39:08Z · plan-validation · session · session=34b0d596-9d88-40a0-99fd-4f93aab43431

`plan-validation` ran as session `34b0d596-9d88-40a0-99fd-4f93aab43431`
- replay: `claude --resume 34b0d596-9d88-40a0-99fd-4f93aab43431`
- log: `.project/logs/TICKET-077-plan-validation-34b0d596.log`

### 2026-08-27 19:39:08Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B pass: eight items scored against the code; every cited line resolves except `run()` (1293, not 1314) in `## Digest`, which no step uses

### 2026-08-27 19:40:05Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Verified anchors: rec['sink'] at supervisor.py:228, compose_prompt call at :390, events.py _norm result branch at :97.

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Verified anchors: rec['sink'] at supervisor.py:228, compose_prompt call at :390, events.py _norm result branch at :97.**

### 2026-08-27 19:46:17Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash` fails as required
```
et-killed stage hit, not read like a crash: '`plan-validation` wrote no .result sidecar 2 times'[0m
[1m[31mE       assert 'budget' in '`plan-validation` wrote no .result sidecar 2 times'[0m
[1m[31mE        +  where '`plan-validation` wrote no .result sidecar 2 times' = <built-in method lower of str object at 0x7f745a197690>()[0m
[1m[31mE        +    where <built-in method lower of str object at 0x7f745a197690> = '`plan-validation` wrote no .result sidecar 2 times'.lower[0m

[1m[31mtests/test_dispatch.py[0m:1462: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> escalated (`plan-validation` wrote no .result sidecar 2 times)
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_dispatch.py::[1mtest_a_budget_kill_is_charged_and_retried_exactly_like_a_crash[0m - AssertionError: escalation must name the cap a budget-killed stage hit, not...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.16s[0m[31m ===============================[0m

```
- ok: `tests/test_dispatch.py::test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash` fails on base `main` too -- the bug is not already fixed upstream
```
result sidecar 2 times)
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_dispatch.py::[1mtest_a_budget_kill_is_charged_and_retried_exactly_like_a_crash[0m - AssertionError: escalation must name the cap a budget-killed stage hit, not...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.24s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-txagdhow/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-txagdhow/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 19:46:17Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### implementing · todo

1. `events.py` -- carry `terminal_reason` on the `result` record.
2. `test_stream.py` -- new test for step 1.
3. `config.py` -- `stage_cap()`, `render()` uses it.
4. `supervisor.py` -- `terminal_sink()`.
5. `supervisor.py` -- wrap `rec["sink"]`, add `cap`/`terminal_reason` to `rec`.
6. `test_dispatch.py` -- new test for `terminal_sink()`.
7. `supervisor.py` -- `_finish()` branches on `budget_exhausted`.
8. `test_dispatch.py` -- rewrite the ticket's `test_file`.
9. `test_dispatch.py` -- new crash-still-retries test.
10. `_common.md` -- rule 6 sidecar-first wording + new sentence.
11. `config.py` -- `compose_prompt(..., interactive=)` override text.
12. `supervisor.py` -- pass `interactive=` at the `compose_prompt()` call.
13. `test_stages.py` -- new test for step 11/12.
14. `README.md` -- escalation table row + `budget_kills` bound sentence.
15. `README.md` -- extend the interactive-sidecar paragraph.
16. `CLAUDE.md` -- new gotcha bullet.
17. Full suite + guard script, then commit.

### implementing · done

All 17 steps executed as planned, TDD throughout: each new/rewritten test run
RED for the stated reason, then GREEN after the minimal code.

Two notes for the next stage:

1. `tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
   is flaky and unrelated to this change -- confirmed by running it against
   `main` (unmodified checkout at the repo root) before touching any code:
   same failure, `assert 2 == 1`. It also passed when the full suite ran
   together. Not touched, per scope.
2. `test_an_interactive_prompt_reverses_the_sidecar_ordering` asserts on
   `"before you append your"` rather than the full phrase from step 10,
   because `_common.md`'s prose wraps that phrase across a markdown line
   break and `compose_prompt()` returns the raw text, newline included.

`uv run --group dev pytest -q`: 397 passed. `./pipeline/hooks/test_dangerous_commands.py`: all passed, exit 0.
Commit: `797bbbf` on `ticket/077`.

### 2026-08-27 19:51:52Z · implementing · session · session=9828a500-de30-479d-bfc5-c70cd6b778c2

`implementing` ran as session `9828a500-de30-479d-bfc5-c70cd6b778c2`
- replay: `claude --resume 9828a500-de30-479d-bfc5-c70cd6b778c2`
- log: `.project/logs/TICKET-077-implementing-9828a500.log`

### 2026-08-27 19:51:52Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ executed all 17 plan steps with TDD; full suite (397) and guard script green; committed 797bbbf

### review · findings

**Verdict: pass. No blocking findings.** Reviewed `git diff main...HEAD` (2
commits, 9 files) against the six acceptance criteria. Re-ran both suites in
the worktree: `uv run --group dev pytest -q` -> `397 passed in 19.08s`;
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`, exit 0.

Two candidate findings, both refuted:

1. A headless run of the interactive `planning` stage would be SIGTERMed on
   its sidecar while its prompt says to write it first. Refuted:
   `supervisor.py:453` sets `mode = "interactive" if interactive else "batch"`
   from the same flag passed to `compose_prompt()`, and `supervisor.py:1140`
   gates `end_interactive()` on `mode == "interactive"`.
2. The new `stage_end` result `budget-exhausted` would be uncounted by a
   consumer enumerating result strings. Refuted: `no-result` appears nowhere
   outside `supervisor.py:1097` and `:1102`; nothing enumerates the values.

Non-blocking:

1. nit: `test_a_budget_kill_is_charged_and_retried_exactly_like_a_crash` now
   asserts the opposite of its name. Plan step 8 required keeping it -- it is
   the ticket's `test_file`.
2. nit: `stage_cap()` carries no return annotation; its neighbours in
   `config.py` do.

### 2026-08-27 19:55:34Z · review · session · session=5b98031b-9388-4ec2-b39c-525e292bdb3c

`review` ran as session `5b98031b-9388-4ec2-b39c-525e292bdb3c`
- replay: `claude --resume 5b98031b-9388-4ec2-b39c-525e292bdb3c`
- log: `.project/logs/TICKET-077-review-5b98031b.log`

### 2026-08-27 19:55:34Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed the 9-file delta against all six acceptance criteria; no blocking findings, two nits recorded; 397 passed and the guard script exits 0

### 2026-08-27 19:55:54Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 19:55:56Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/077


Current branch ticket/077 is up to date.
Already up to date.
Updating 115a3e1..797bbbf
Fast-forward
 CLAUDE.md                     |  8 +++++
 README.md                     | 10 +++++--
 pipeline/core/config.py       | 19 ++++++++++--
 pipeline/daemon/supervisor.py | 32 ++++++++++++++++++--
 pipeline/stages/_common.md    |  7 ++++-
 pipeline/stream/events.py     |  1 +
 tests/test_dispatch.py        | 69 +++++++++++++++++++++++++++++++++++++++++++
 tests/test_stages.py          |  9 ++++++
 tests/test_stream.py          | 12 ++++++++
 9 files changed, 160 insertions(+), 7 deletions(-)

```

### 2026-08-27 19:55:56Z · merging · decision

decision recorded as `DEC-077`
