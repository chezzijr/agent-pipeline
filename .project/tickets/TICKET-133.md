---
id: TICKET-133
stage: done
class: bugfix
branch: ticket/133
test_file:
- tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal
- tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
files_declared:
- pipeline/daemon/supervisor.py
- pipeline/harnesses/codex.toml
- pipeline/stream/events.py
- tests/test_dispatch.py
- tests/test_stream.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
  plan_steps: 2
  plan_files: 5
lease:
  holder: null
  expires: null
depends_on:
- TICKET-129
last_session:
  stage: review
  id: 01a09848-ac69-7300-b982-77d4d7e3aad9
  replay: codex exec resume 01a09848-ac69-7300-b982-77d4d7e3aad9
  log: .project/logs/TICKET-133-review-7d9e2e70.log
  cost_usd: null
approved_by: chezzijr
approved_at: '2026-09-13T01:34:18.814604+00:00'
---

## Summary

an API refusal is invisible under codex and has no backoff under either harness, so one outage escalates every in-flight ticket

Two defects, one cause, one file pair. Both must land together or the fix is
harness-specific.

**One: codex refusals are never classified.** `parse()` hardcodes
`"terminal_reason": None` for codex's `turn.completed`
(`pipeline/stream/events.py:128`) and has no rule at all for codex's failure
shapes. Observed 2026-09-12, in
`.project/logs/TICKET-129-implementing-ec546d20.log`:

    {"type":"error","message":"You've hit your usage limit. ... try again at 3:17 PM."}
    {"type":"turn.failed","error":{"message":"You've hit your usage limit. ..."}}

Neither line is mapped. The `item_type == "error"` branch
(`pipeline/stream/events.py:106`) matches an item inside `item.completed`, not
a top-level `turn.failed`. So the run reaches `_finish()` with
`terminal_reason = None`, skips the `budget_exhausted` case
(`pipeline/daemon/supervisor.py:1291`) and the `api_error` case (`:1302`), and
falls into the generic no-sidecar path. The ticket records:

    `implementing` wrote no .result sidecar 2 times

which says the agent is broken when the API was merely unavailable. The real
reason survives only in a log nobody reads.

**Two: neither harness backs off.** `_finish()` charges `api_errors` and
respawns immediately (`pipeline/daemon/supervisor.py:1302-1311`). There is no
sleep. `api_errors` is a dispatcher counter bounded by `MAX_ATTEMPTS`, so both
attempts are spent against the same unavailable API within one tick.

Measured cost of the two together, 2026-09-12 in this repo: one codex usage
limit escalated TICKET-129 on two instant `no_result` attempts, and
TICKET-130, 132, 133, 134, 135 and 136 cascaded through `depends_on` in the
same tick -- seven tickets, one outage, zero agent faults. The chezzilang
project's wave 12 (2026-09) recorded the same shape on the other harness: 15
API refusals and 6 dependency cascades out of 25 escalations, each needing
`pipeline resume <id> --reset api_errors` by hand.

Expected, part one: a refusal is classified whatever the harness. `parse()`
maps codex's top-level `{"type":"error"}` and `{"type":"turn.failed"}` to a
record carrying `terminal_reason`, the way Claude Code's `result` event
already supplies one, so `_finish()` reaches the same branch for both. `parse()`
must stay total and never raise (`pipeline/stream/events.py` says so), and an
unrecognised failure must keep today's behaviour rather than guess.

Expected, part two: a run that ends in a refusal backs off before it is
charged -- a bounded retry window with increasing delay, after which it charges
and escalates as it does today. `retry_eagain()`
(`pipeline/core/worktree.py`) is the existing precedent for a bounded retry
with backoff around a transient failure; match its shape rather than invent a
second one.

The backoff must not block the select loop. A ticket waiting out a refusal must
not stop other tickets being claimed, so the delay belongs in the dispatcher's
scheduling -- a not-before timestamp the next `start()` honours -- never a
`sleep` inside `_finish()`.

**Harness-neutrality is the point of this ticket, not a caveat.** A third
harness must get the same treatment by adding data, not code: the strings and
event types that mean "refused" belong beside the other per-harness facts in
`pipeline/harnesses/*.toml`, which `CLAUDE.md` already calls "data, not code. A
new harness is a new file." Do not hardcode `"You've hit your usage limit"` or
any vendor's wording in `pipeline/stream/events.py`; match on the event's
shape, and let a harness declare its own terminal-failure event types.

The exact failures a test should show:

- `parse('{"type":"turn.failed","error":{"message":"..."}}')` returning a
  record whose `terminal_reason` is unset, where it should name a refusal.
  `tests/test_stream.py` already holds the codex cases
  (`test_codex_jsonl_is_normalised_without_inventing_cost`, line 129).
- a child whose record carries a refusal charging its counter on the first
  reap with no delay recorded, where it should defer. `tests/test_dispatch.py`
  holds the `api_error` and `budget_exhausted` cases.

The files this ticket changes are `pipeline/stream/events.py`,
`pipeline/daemon/supervisor.py`, `pipeline/harnesses/codex.toml`,
`tests/test_stream.py` and `tests/test_dispatch.py`. `pipeline/harnesses/codex.toml`
IS in `machine.FENCED`, so this ticket parks at `awaiting-merge` for human
review before it lands -- expected, not a fault.

## Reproduction

`tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal`

Command:

```sh
uv run --group dev pytest -q tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal
```

Output:

```text
E       AssertionError: assert 'other' == 'result'
E         
E         - result
E         + other
1 failed in 0.15s
```

expect: AssertionError: assert 'other' == 'result'

`tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result`

Command:

```sh
uv run --group dev pytest -q tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
```

Output:

```text
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
1 failed in 0.49s
```

expect: AssertionError: an API refusal must defer before charging

## Digest

- `pipeline/stream/events.py`: `_norm()`, `parse()`, and `StreamReader` own total, harness-neutral stream normalization; only `kind: result` reaches `terminal_sink()` as a terminal failure.
- `pipeline/harnesses/codex.toml` will declare Codex refusal event types as data; `pipeline/daemon/supervisor.py::spawn()` supplies that list only to the live batch reader.
- `pipeline/daemon/supervisor.py`: `_finish()` handles a parsed `api_error`, while `start()` is the non-blocking scheduling entry point and `MAX_ATTEMPTS` remains the bound.
- Persist `api_retry_at` in `Ticket.extra`, release the lease during the wait, and parse the timestamp with the existing total `lease_expiry()` helper.
- `tests/test_stream.py` covers both Codex failure shapes and unknown fallback; `tests/test_dispatch.py` covers deferral, exponential delay, later charging, and bounded escalation.
- Gotcha: `StreamReader()` also renders stored logs without harness context, so its new failure-type argument must remain optional and undeclared events must retain `kind: other`.

## Decisions checked

- DEC-028: harness TOML reloads once per tick, so declarative refusal types reach later spawns without a process restart.
- DEC-061: dispatcher work must not stall the select loop; an API retry therefore waits in scheduling state.
- DEC-077: terminal failures are classified from stream events and retained on the child by `terminal_sink()`.
- DEC-085: `parse()` and `terminal_sink()` must remain total because they run on the poller callback path.
- DEC-086: reuse its bounded exponential-delay shape, but do not reuse its blocking sleep because API waits span dispatcher ticks.

## Plan

1. Extend `tests/test_stream.py` for top-level `error`, `turn.failed`, and undeclared failure events; add `api_error_types = ["error", "turn.failed"]` to `pipeline/harnesses/codex.toml`; update `pipeline/stream/events.py` so `parse()` and `StreamReader` accept optional declared types and `_norm()` returns a complete `kind: result`, `terminal_reason: api_error` record using top-level or nested error text without matching vendor wording; pass the selected harness list from `pipeline/daemon/supervisor.py::spawn()` and run the focused stream tests before committing.
2. Extend `tests/test_dispatch.py` with `test_an_api_error_waits_without_blocking_then_charges` and `test_api_error_backoff_increases_and_escalates_at_bound`; update `pipeline/daemon/supervisor.py` so `_finish()` releases the lease, records `api_retry_at`, and leaves counters unchanged, while `start()` parses that timestamp with `lease_expiry()`, returns before spawn while it is future, charges after expiry, respawns after the first 30-second wait, and escalates after the second 60-second wait at `MAX_ATTEMPTS`; run both focused modules and the full suite before committing.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` exits `0` after both types declared by `pipeline/harnesses/codex.toml` normalize to `terminal_reason: api_error` without message matching.
- `uv run --group dev pytest -q tests/test_stream.py` exits `0`, including malformed-input totality and an undeclared failure type that remains `kind: other`.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_an_api_error_waits_without_blocking_then_charges tests/test_dispatch.py::test_api_error_backoff_increases_and_escalates_at_bound` exits `0`; the tests prove no sleep or charge occurs before each timestamp, waits increase from 30 to 60 seconds, and the second expiry escalates.
- `uv run --group dev pytest -q` exits `0` with no regressions relative to the suite run at check time.
- `./pipeline/hooks/test_dangerous_commands.py` exits `0` because the fenced Codex harness edit must preserve every guard case.

## Decisions

Harness adapters declare top-level API-refusal event types; the parser matches event shape, never vendor message text. Undeclared failure events remain `kind: other`.

API refusals persist `api_retry_at` and release the lease. The dispatcher waits 30 seconds, then 60 seconds, charging only after each wait expires; the second charge reaches `MAX_ATTEMPTS` and escalates.

The retry timestamp is durable ticket state so a dispatcher restart cannot erase the wait. An unreadable timestamp escalates instead of spawning or waiting forever.

## Rollback

Revert both implementation commits together because parser configuration and scheduling depend on each other. Step 2 is riskiest; if its focused tests show blocking, an occupied lease, or an unbounded wait, restore immediate bounded `api_errors` charging while retaining Step 1 refusal classification.

## Thread

### 2026-09-12 05:01:13Z · new · escalation

TICKET-133 depends_on TICKET-129, which is escalated and can never reach done

### 2026-09-12 11:09:14Z · human · note · by=chezzijr

**resumed** by chezzijr -> `new`, reset ['no_result']

### 2026-09-12 11:18:48Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-12 · triage · evidence

Reproduced both defects in commit `afd69ac`.

`turn.failed` reaches `_norm()` without a matching branch and returns `kind: other`.
Claude's `result` branch forwards its `terminal_reason`; Codex has no corresponding failure mapping.

`_finish()` increments `api_errors`, releases the lease, and saves the ticket on its first refusal.
No scheduling timestamp is recorded, so `start()` can respawn immediately.

The tests fail with the `expect:` lines in `## Reproduction`.
Expected fix scope: `pipeline/stream/events.py`, `pipeline/daemon/supervisor.py`, `pipeline/harnesses/codex.toml`, and both test files.

### 2026-09-12 11:20:38Z · triage · session · session=01a09557-99bd-78a3-9343-7f6bef40a172

`triage` ran as session `01a09557-99bd-78a3-9343-7f6bef40a172`
- replay: `codex exec resume 01a09557-99bd-78a3-9343-7f6bef40a172`
- log: `.project/logs/TICKET-133-triage-df122ffb.log`
- cost: unknown (the harness reported none)
- tokens: 3,993 out (1,136 thinking) · 402,570 in · 359,936 cache read · 0 cache write

### 2026-09-12 11:20:38Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced Codex refusal loss and immediate API-error charging.

### 2026-09-12 11:27:17Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails as required
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-133
configfile: pyproject.toml
collected 1 item

tests/test_stream.py F

=================================== FAILURES ===================================
__________________ test_codex_turn_failure_is_an_api_refusal ___________________

    def test_codex_turn_failure_is_an_api_refusal():
        """A Codex refusal must reach the dispatcher's external-error path."""
        ev = parse('{"type":"turn.failed","error":{"message":"usage limit"}}')
>       assert ev["kind"] == "result"
E       AssertionError: assert 'other' == 'result'
E         
E         - result
E         + other

tests/test_stream.py:155: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails as required
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7fce23e87380>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7fce23e87380> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmpgya48r54/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================

```
- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails on base `main` too -- the bug is not already fixed upstream
```
    """A Codex refusal must reach the dispatcher's external-error path."""
        ev = parse('{"type":"turn.failed","error":{"message":"usage limit"}}')
>       assert ev["kind"] == "result"
E       AssertionError: assert 'other' == 'result'
E         
E         - result
E         + other

tests/test_stream.py:155: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-6vlsarbk/base
      Built pipeline @ file:///tmp/pipeline-base-6vlsarbk/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 54ms

```
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails on base `main` too -- the bug is not already fixed upstream
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7fa609705e80>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7fa609705e80> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmpz51v_4ki/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.54s ===============================

```
- `files_declared` is empty
- plan step names no declared file: '1. Extend `tests/test_stream.py` for top-level `error`, `turn.failed`, and undeclared failure events; add `api_error_types = ["error", "turn.failed"]` to `pipeline/harnesses/codex.toml`; update `pipeline/stream/events.py` so `parse()` and `StreamReader` accept optional declared types and `_norm()` returns a complete `kind: result`, `terminal_reason: api_error` record using top-level or nested error text without matching vendor wording; pass the selected harness list from `pipeline/daemon/supervisor.py::spawn()` and run the focused stream tests before committing.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Extend `tests/test_dispatch.py` with `test_an_api_error_waits_without_blocking_then_charges` and `test_api_error_backoff_increases_and_escalates_at_bound`; update `pipeline/daemon/supervisor.py` so `_finish()` releases the lease, records `api_retry_at`, and leaves counters unchanged, while `start()` parses that timestamp with `lease_expiry()`, returns before spawn while it is future, charges after expiry, respawns after the first 30-second wait, and escalates after the second 60-second wait at `MAX_ATTEMPTS`; run both focused modules and the full suite before committing.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-12 11:28:20Z · planning · finding

The implementation plan is complete, but Tier A cannot validate it during this run.

`pipeline gate TICKET-133` reported `FAIL: files_declared is empty`. Both path findings follow from the same empty dispatcher-owned field.

Planning cannot edit YAML frontmatter. The `.result` sidecar declares all five planned files so a resumed planning run can validate the preserved plan.

### 2026-09-12 11:28:39Z · planning · session · session=01a09559-1bcb-75a2-808e-d2e576b5a60e

`planning` ran as session `01a09559-1bcb-75a2-808e-d2e576b5a60e`
- replay: `codex exec resume 01a09559-1bcb-75a2-808e-d2e576b5a60e`
- log: `.project/logs/TICKET-133-planning-0ae3fef5.log`
- cost: unknown (the harness reported none)
- tokens: 14,424 out (7,884 thinking) · 2,503,568 in · 2,391,936 cache read · 0 cache write

### 2026-09-12 11:28:39Z · planning · transition · to=escalated · result=fail · marker=yes

**planning -> escalated** (result: `fail`)

✓ Tier A cannot validate because dispatcher-owned files_declared is empty.

### 2026-09-12 18:06:40Z · human · note · by=chezzijr

**resumed** by chezzijr -> `planning`, reset []

### 2026-09-12 18:35:55Z · planning · note

`planning` was interrupted; lease released

### 2026-09-12 18:38:57Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails as required
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-133
configfile: pyproject.toml
collected 1 item

tests/test_stream.py F

=================================== FAILURES ===================================
__________________ test_codex_turn_failure_is_an_api_refusal ___________________

    def test_codex_turn_failure_is_an_api_refusal():
        """A Codex refusal must reach the dispatcher's external-error path."""
        ev = parse('{"type":"turn.failed","error":{"message":"usage limit"}}')
>       assert ev["kind"] == "result"
E       AssertionError: assert 'other' == 'result'
E         
E         - result
E         + other

tests/test_stream.py:155: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails as required
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f2e17b8bd80>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7f2e17b8bd80> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmpphxg49b3/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================

```
- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails on base `main` too -- the bug is not already fixed upstream
```
    """A Codex refusal must reach the dispatcher's external-error path."""
        ev = parse('{"type":"turn.failed","error":{"message":"usage limit"}}')
>       assert ev["kind"] == "result"
E       AssertionError: assert 'other' == 'result'
E         
E         - result
E         + other

tests/test_stream.py:155: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ua73w2fx/base
      Built pipeline @ file:///tmp/pipeline-base-ua73w2fx/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 67ms

```
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails on base `main` too -- the bug is not already fixed upstream
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f7503fb2c40>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7f7503fb2c40> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmphwwbqkdt/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.53s ===============================

```

### 2026-09-12 18:39:25Z · planning · plan

The preserved plan is complete and matches the current implementation seams.

`pipeline gate TICKET-133` printed `gate: PASS` from the main checkout. The gate confirmed both reproduction tests still fail on the ticket worktree and base branch.

The five declared files cover stream normalization, harness data, dispatcher scheduling, and focused regression tests. No rejection entries exist in the thread.

### 2026-09-12 18:40:23Z · planning · session · session=01a096e8-377e-7e60-afcc-f3fcd6e62f8e

`planning` ran as session `01a096e8-377e-7e60-afcc-f3fcd6e62f8e`
- replay: `codex exec resume 01a096e8-377e-7e60-afcc-f3fcd6e62f8e`
- log: `.project/logs/TICKET-133-planning-8280a9b1.log`
- cost: unknown (the harness reported none)
- tokens: 6,166 out (2,789 thinking) · 1,196,742 in · 1,076,864 cache read · 0 cache write

### 2026-09-12 18:40:23Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Validated the preserved harness-neutral refusal and non-blocking backoff plan with Tier A.

### 2026-09-12 18:41:59Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-12 11:27:17Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails as required
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f4dda828880>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7f4dda828880> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmp9r6z068_/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================

```
- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails on base `main` too -- the bug is not already fixed upstream
```
    """A Codex refusal must reach the dispatcher's external-error path."""
        ev = parse('{"type":"turn.failed","error":{"message":"usage limit"}}')
>       assert ev["kind"] == "result"
E       AssertionError: assert 'other' == 'result'
E         
E         - result
E         + other

tests/test_stream.py:155: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-hhspw898/base
      Built pipeline @ file:///tmp/pipeline-base-hhspw898/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 52ms

```
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails on base `main` too -- the bug is not already fixed upstream
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7ff3f7325e80>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7ff3f7325e80> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmp1y_1c4b5/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.46s ===============================

```

### 2026-09-12 18:42:14Z · plan-validation · session · session=01a096ed-2cce-7d60-8974-5dec47f0a0ad

`plan-validation` ran as session `01a096ed-2cce-7d60-8974-5dec47f0a0ad`
- replay: `codex exec resume 01a096ed-2cce-7d60-8974-5dec47f0a0ad`
- log: `.project/logs/TICKET-133-plan-validation-3fd3ab9f.log`

### 2026-09-12 18:42:14Z · plan-validation · note

`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-12 18:42:47Z · plan-validation · note

`plan-validation` was interrupted; lease released

### 2026-09-12 22:16:33Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-12 11:27:17Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails as required
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7fb8cde48e00>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7fb8cde48e00> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmp1q94you8/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================

```
- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails on base `main` too -- the bug is not already fixed upstream
```
    """A Codex refusal must reach the dispatcher's external-error path."""
        ev = parse('{"type":"turn.failed","error":{"message":"usage limit"}}')
>       assert ev["kind"] == "result"
E       AssertionError: assert 'other' == 'result'
E         
E         - result
E         + other

tests/test_stream.py:155: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ojj72kv9/base
      Built pipeline @ file:///tmp/pipeline-base-ojj72kv9/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 82ms

```
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails on base `main` too -- the bug is not already fixed upstream
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f69bec301c0>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7f69bec301c0> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmppy8oyh_z/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.46s ===============================

```

### 2026-09-12 22:18:24Z · plan-validation · finding

**pass — Root cause vs symptom.** Missing harness-declared terminal semantics leaves Codex failures `other`; immediate `_finish()` charging omits retry scheduling. Steps 1-2 fix both causes.

**pass — Decision conflict.** DEC-028/077/085 permit declarative live-reader classification. Durable scheduling obeys DEC-061; the plan borrows DEC-086's bound, not its blocking sleep.

**pass — Scope discipline.** All five files implement parser data, scheduling, or their required tests. The fenced-harness guard run follows the acceptance criteria.

**pass — Falsifiable criteria.** Assertions distinguish declared from undeclared events, pre-expiry from post-expiry state, both delays, counter changes, and terminal escalation.

**pass — No research left.** Both steps name concrete files, functions, configuration, timestamps, and test nodes.

**pass — Riskiest step.** Step 2 is riskiest. Its fallback restores immediate bounded charging if tests expose blocking, retained leases, or unbounded waits.

**pass — Regression surface.** Optional `StreamReader` configuration protects log renderers. Full stream and dispatcher suites cover totality, unknown events, ordinary crashes, budget kills, leases, and scheduling.

**pass — Blast radius matches class.** This five-file bugfix changes one parser/config seam, one scheduler seam, and focused tests; no unrelated behavior is included.

### 2026-09-12 22:19:58Z · plan-validation · session · session=01a097b1-a593-7a50-9276-a4312da13cca

`plan-validation` ran as session `01a097b1-a593-7a50-9276-a4312da13cca`
- replay: `codex exec resume 01a097b1-a593-7a50-9276-a4312da13cca`
- log: `.project/logs/TICKET-133-plan-validation-feb2d9d5.log`
- cost: unknown (the harness reported none)
- tokens: 8,455 out (4,380 thinking) · 730,527 in · 669,056 cache read · 0 cache write

### 2026-09-12 22:19:58Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight judgment checks; refusal classification and bounded scheduling are concrete and testable

### 2026-09-13 00:52:26Z · human · note · by=chezzijr

**note from chezzijr**

Approved by Claude on the operator's behalf. Checked: classification is data, not code -- api_error_types lives in codex.toml and _norm() matches event shape, never vendor wording, so a third harness is a new file (CLAUDE.md's rule). Backoff is scheduling, not a sleep: _finish() records api_retry_at and start() returns before spawn while it is future, so the select loop keeps claiming other tickets. Counters unchanged until the wait expires, escalating at MAX_ATTEMPTS after 30s then 60s. NOTE FOR THE OPERATOR: this ticket changes pipeline/harnesses/codex.toml, which is in machine.FENCED, so it will park at awaiting-merge. I am deliberately NOT clearing that gate -- CLAUDE.md requires human review before a guard/harness change lands.

### 2026-09-13 00:52:27Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-13 00:54:11Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails as required
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-133
configfile: pyproject.toml
collected 1 item

tests/test_stream.py F

=================================== FAILURES ===================================
__________________ test_codex_turn_failure_is_an_api_refusal ___________________

    def test_codex_turn_failure_is_an_api_refusal():
        """A Codex refusal must reach the dispatcher's external-error path."""
        ev = parse('{"type":"turn.failed","error":{"message":"usage limit"}}')
>       assert ev["kind"] == "result"
E       AssertionError: assert 'other' == 'result'
E         
E         - result
E         + other

tests/test_stream.py:155: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails as required
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f3ef4ad0400>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7f3ef4ad0400> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmpwey3iwlr/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.41s ===============================

```
- ok: `tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal` fails on base `main` too -- the bug is not already fixed upstream
```
   """A Codex refusal must reach the dispatcher's external-error path."""
        ev = parse('{"type":"turn.failed","error":{"message":"usage limit"}}')
>       assert ev["kind"] == "result"
E       AssertionError: assert 'other' == 'result'
E         
E         - result
E         + other

tests/test_stream.py:155: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stream.py::test_codex_turn_failure_is_an_api_refusal - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-0r4j_5ft/base
      Built pipeline @ file:///tmp/pipeline-base-0r4j_5ft/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 104ms

```
- ok: `tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result` fails on base `main` too -- the bug is not already fixed upstream
```
None, "terminal_reason": "api_error"}
    
        supervisor.finish(d, rec())
        t = Ticket.load(path)
        assert t.counters.get("no_result", 0) == 0
>       assert t.counters.get("api_errors", 0) == 0, "an API refusal must defer before charging"
E       AssertionError: an API refusal must defer before charging
E       assert 1 == 0
E        +  where 1 = <built-in method get of dict object at 0x7f99252b3bc0>('api_errors', 0)
E        +    where <built-in method get of dict object at 0x7f99252b3bc0> = {'api_errors': 1}.get
E        +      where {'api_errors': 1} = Ticket(path=PosixPath('/tmp/tmp3p_hhs1x/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='plan-validation', kl...alidation · note\n\n`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- will respawn\n').counters

tests/test_dispatch.py:2377: AssertionError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_an_api_error_kill_is_not_charged_to_no_result
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.48s ===============================

```

### 2026-09-13 00:54:12Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-13 · implementing · todo

1. [in progress] Declare Codex refusal events and normalize declared failure shapes.
2. [pending] Schedule durable 30- then 60-second API-refusal retries.
3. [pending] Run focused tests, the full suite, and the command-guard checks.

### 2026-09-13 · implementing · note

1. [done] Declared Codex refusal events and normalized declared failure shapes.
2. [done] Added durable 30- then 60-second API-refusal scheduling.
3. [in progress] Focused stream and dispatcher tests pass: `20 passed in 0.47s`.

### 2026-09-13 · implementing · finding

Implemented both plan steps in commit `082431f`.

1. Codex declares `error` and `turn.failed` as API-refusal event types.
2. Declared shapes normalize to `terminal_reason: api_error` without message matching.
3. Refusals release leases and persist 30- then 60-second retry timestamps.
4. Expired waits charge `api_errors`; the second expiry escalates at `MAX_ATTEMPTS`.
5. Focused tests passed: `20 passed in 0.47s`.
6. `uv run --group dev pytest -q` passed.
7. `./pipeline/hooks/test_dangerous_commands.py` passed: `guard: all passed`.

### 2026-09-13 01:01:33Z · implementing · session · session=01a09841-f9ad-7731-88ab-c7304bb141dd

`implementing` ran as session `01a09841-f9ad-7731-88ab-c7304bb141dd`
- replay: `codex exec resume 01a09841-f9ad-7731-88ab-c7304bb141dd`
- log: `.project/logs/TICKET-133-implementing-c1756f1c.log`
- cost: unknown (the harness reported none)
- tokens: 11,284 out (3,294 thinking) · 2,979,265 in · 2,865,408 cache read · 0 cache write

### 2026-09-13 01:01:33Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Classified declared API refusals and scheduled bounded backoff.

### 2026-09-13 01:05:51Z · review · finding

No blocking findings.

1. Declared Codex failure shapes reach `terminal_reason: api_error` without message matching.
2. Retry state releases the lease, persists the timestamp, and charges only after 30- and 60-second waits.
3. Focused verification passed: `20 passed in 0.23s`.
4. The command guard passed: `guard: all passed`.
5. Full-suite review verification reached `116 passed` before sandboxed AF_UNIX `bind()` returned `PermissionError: [Errno 1] Operation not permitted`.
6. The implementing stage recorded a complete full-suite pass outside this review restriction.

### 2026-09-13 01:06:10Z · review · session · session=01a09848-ac69-7300-b982-77d4d7e3aad9

`review` ran as session `01a09848-ac69-7300-b982-77d4d7e3aad9`
- replay: `codex exec resume 01a09848-ac69-7300-b982-77d4d7e3aad9`
- log: `.project/logs/TICKET-133-review-7d9e2e70.log`
- cost: unknown (the harness reported none)
- tokens: 8,415 out (3,782 thinking) · 1,130,908 in · 1,037,568 cache read · 0 cache write

### 2026-09-13 01:06:11Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ No blocking findings; focused tests and guard checks pass.

### 2026-09-13 01:07:20Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/harnesses/codex.toml`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-133` lands it; `pipeline resume TICKET-133 --stage planning` sends it back.

### 2026-09-13 01:34:18Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-13 01:34:26Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/133


Current branch ticket/133 is up to date.
Already up to date.
Updating 87ba3a6..082431f
Fast-forward
 pipeline/daemon/supervisor.py | 31 ++++++++++++-----
 pipeline/harnesses/codex.toml |  1 +
 pipeline/stream/events.py     | 23 ++++++++++---
 tests/test_dispatch.py        | 79 +++++++++++++++++++++++++++++++++++++++++++
 tests/test_stream.py          | 18 ++++++++++
 5 files changed, 139 insertions(+), 13 deletions(-)

```

### 2026-09-13 01:34:26Z · merging · decision

decision recorded as `DEC-133`
