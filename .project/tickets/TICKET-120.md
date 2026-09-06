---
id: TICKET-120
stage: done
class: bugfix
branch: ticket/120
test_file: tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable
files_declared:
- CLAUDE.md
- README.md
- pipeline/daemon/supervisor.py
- pipeline/stream/events.py
- tests/test_daemon.py
- tests/test_dispatch.py
- tests/test_stream.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 11
  plan_files: 7
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 261b610d-cd74-4046-a98f-ba49737276d1
  replay: claude --resume 261b610d-cd74-4046-a98f-ba49737276d1
  log: .project/logs/TICKET-120-review-261b610d.log
  cost_usd: 1.4746855000000003
approved_by: chezzijr
approved_at: '2026-09-06T07:19:27.446704+00:00'
---

## Summary

Codex token usage disappears when dollar cost is unavailable

Codex logs contain terminal records such as:

    {"type":"turn.completed","usage":{"input_tokens":438060,"cached_input_tokens":400384,"output_tokens":3719}}

`pipeline/stream/events.py:110-125` parses that usage, but TICKET-113's session
entries contain no token line. `pipeline/daemon/supervisor.py:308-309` returns
an empty `cost_report()` whenever `cost_usd` is unavailable, discarding valid
token data together with the absent dollar amount. Codex intentionally has no
fabricated USD cap or cost.

Expected: record and display real Codex token usage in ticket sessions and
metrics even when cost is unknown. Keep unknown cost visibly unknown, preserve
Claude's exactly-once cost/token accounting and interactive transcript path,
and never synthesize prices or double-count `turn.completed` events.

Triage confirmed the bug: `cost_report()` returns `""` on `cost_usd is None`
before it looks at `usage`, so a Codex run's real tokens are dropped along
with the absent dollar cost. Failing test:
`tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable`.

Planning wrote an 11-step plan. The fix splits `cost_report()` in
`pipeline/daemon/supervisor.py` into two independent lines: the cost line
renders only when `cost_usd` is known, the token line whenever a count is
non-zero. An unknown cost prints `unknown (the harness reported none)`; no
price is synthesized. A known Claude cost renders byte-identically to today,
and an interactive stage still renders `""`, because its `usage` is empty
(DEC-085, DEC-077). One step beyond triage's scope maps Codex's
`reasoning_output_tokens` to `output_tokens_details.thinking_tokens` in
`pipeline/stream/events.py`, in its own commit. Metrics need no change: the
event log already holds Codex `usage` with a null `total_cost_usd`. Suite
baseline on `ac87719`: `1 failed, 560 passed`, the failure being the repro.

Both gates passed the plan. Tier A: PASS. Tier B: PASS on every item -- the
plan fixes the root cause (`cost_usd is None` used as a proxy for "no `result`
event arrived"), supersedes DEC-085's stated mechanism with justification while
keeping its observable property, and states a fallback for its riskiest step.
Implementation may proceed on the plan as written. Two facts a reviewer will
want: the quoted `CLAUDE.md` and `README.md` anchors match the files verbatim,
and none of the four touched source or doc files is in `machine.FENCED`.

Implementing executed all 11 plan steps as written, no deviation. Three commits
on `ticket/120`: `03761c0` splits `cost_report()`, `ba205d8` maps Codex
`reasoning_output_tokens` to `output_tokens_details.thinking_tokens`, `ba8d22e`
updates `CLAUDE.md`/`README.md`. Every new test failed for the stated reason
before its fix (verified: `''` result, `KeyError: 'output_tokens_details'`).

Review passed the delta on the first pass, with no blocking finding. Review
re-ran every acceptance criterion: `uv run --group dev pytest -q` -> `581
passed in 55.97s`, `./pipeline/hooks/test_dangerous_commands.py` -> exit 0,
`grep -c 'reported none' pipeline/daemon/supervisor.py` -> `1`, and
`cost_report({'cost_usd': None, 'usage': {}})` -> `''`. A known Claude cost
renders byte-identically to TICKET-085's line. No touched file is in
`machine.FENCED`, and the working tree is clean. Two nits sit in the thread,
neither blocking: `cost_report()` renders `''` when every count coerces to 0,
and it still raises on a truthy non-dict `usage` -- a hazard TICKET-085's own
review logged, which the split widens to the unknown-cost path.

## Reproduction

`tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable`

Command: `uv run --group dev pytest -q tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable`

Failure:
```
AssertionError: assert '' != ''
 +  where '' = <function cost_report at 0x7f1eb884e700>({'cost_usd': None, 'usage': {'input_tokens': 438060, 'cached_input_tokens': 400384, 'output_tokens': 3719}})
```
expect: AssertionError: assert '' != ''

`pipeline/daemon/supervisor.py:308` (`cost_report()`) returns `""` as soon as
`rec["cost_usd"] is None`, before it looks at `rec["usage"]` at all. A Codex
`turn.completed` record has real `usage` but no `cost_usd`, so the whole
report -- tokens included -- is dropped, not just the cost line.

## Digest

Files touched: `pipeline/daemon/supervisor.py` (the fix), `pipeline/stream/events.py`
(one Codex usage key), `tests/test_daemon.py`, `tests/test_dispatch.py`,
`tests/test_stream.py`, `CLAUDE.md`, `README.md`.

Key functions:
- `cost_report(rec)` -- `pipeline/daemon/supervisor.py:300-325`. Returns `""` when
  `rec["cost_usd"] is None`, before it reads `rec["usage"]`. This is the bug.
- `terminal_sink(rec, inner)` -- `pipeline/daemon/supervisor.py:280-291`. Puts
  `cost_usd` and `usage` on the child record off the `result` event.
- `_int(v)` -- `pipeline/daemon/supervisor.py:303-307`. Coerces every number, so a
  malformed `usage` renders zeros instead of raising.
- `parse(line)` -- `pipeline/stream/events.py:109-124`. Turns Codex's
  `turn.completed` into a `result` record: `total_cost_usd` from `cost_microusd`
  (absent -> `None`), and `cached_input_tokens` -> `cache_read_input_tokens`,
  `cache_write_input_tokens` -> `cache_creation_input_tokens` by `setdefault`.

Entry points: `_finish()` at `pipeline/daemon/supervisor.py:1242` appends
`cost_report(rec)` to the session `## Thread` entry. `spawn()` at
`pipeline/daemon/supervisor.py:520` seeds the child record with
`"cost_usd": None, "usage": {}`, which is what an interactive stage keeps.

Gotchas:
- Metrics already carry Codex tokens; no metrics change is needed. Verified against
  the live event log at `~/.local/state/pipeline/events.db`: a `kind='result'` row
  for `TICKET-118 planning` holds `total_cost_usd` `None` with
  `{"input_tokens": 2010961, ..., "cache_read_input_tokens": ...}`.
  `_cost_events()` in `pipeline/cli/metrics.py:232-244` reads `total_cost_usd or 0.0`
  and `_tokens()` reads `cache_read_input_tokens`, so the tokens land and the dollar
  figure is 0.0. Only the ticket session entry drops the numbers.
- DEC-085 makes an interactive stage print neither line. It has no `result` event, so
  its `usage` stays `{}` -- the emptiness of `usage`, not `cost_usd is None`, is what
  must keep that property after the fix.
- One `turn.completed` per `codex exec` run in every captured log, so nothing here
  double-counts. `terminal_sink()` overwrites on each `result`, so a second turn would
  replace the first rather than add to it -- the same behaviour Claude already has.
- Codex's `input_tokens` includes `cached_input_tokens` (438,060 against 400,384 in
  `.project/logs/TICKET-120-triage-eccac16a.log`). The plan prints both verbatim and
  subtracts nothing.
- Codex reports reasoning tokens as `reasoning_output_tokens`; Claude reports
  `output_tokens_details.thinking_tokens`, which is what `cost_report()` and
  `_tokens()` in `pipeline/cli/metrics.py:211-230` read. Codex thinking tokens are
  dropped from both today.
- `pipeline/daemon/supervisor.py` and `pipeline/stream/events.py` are not in
  `machine.FENCED`; `CLAUDE.md` and `README.md` are not either.
- Suite baseline, measured 2026-09-06 on `ac87719`: `uv run --group dev pytest -q`
  printed `1 failed, 560 passed in 52.05s`, the one failure being this ticket's repro.

## Decisions checked

- DEC-085 -- constrains this change. It fixes cost and tokens to the `result` event on
  the child record, keeps `cost_report()` formatting-only (never a control decision),
  requires the cap printed beside a known cost, requires nothing on this path to raise,
  and requires an interactive stage to get no cost line. The plan complies: the cap
  stays, every number stays coerced, and the interactive case still renders `""`.
- DEC-077 -- an interactive stage emits no `result` event. This is why an empty `usage`
  must keep meaning "unmeasured".
- DEC-011 -- the event-log schema: a `result` event carries
  `{total_cost_usd, num_turns, duration_ms, usage, modelUsage, ...}`, and `usage` is
  the interactive-only event. The plan adds no event kind and changes no payload.
- Grep terms used over `.project/decisions/`: `cost`, `token`, `usage_source`,
  `turn.completed`, `cost_microusd`, `codex`. `turn.completed` and `cost_microusd`
  match no record.

## Plan

1. Add `test_cost_report_renders_codex_tokens_and_an_unknown_cost` to `tests/test_daemon.py`, directly after `test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable` (line 1068), feeding the real Codex terminal line through `parse()` and `terminal_sink()`:

        def test_cost_report_renders_codex_tokens_and_an_unknown_cost():
            """TICKET-120: a Codex `turn.completed` has real tokens and no dollar
            amount. The tokens must show and the cost must read `unknown` -- not
            `$0.00`, which would price a run nobody priced."""
            from pipeline.stream.events import parse
            line = ('{"type":"turn.completed","usage":{"input_tokens":438060,'
                    '"cached_input_tokens":400384,"output_tokens":3719}}')
            rec = {}
            supervisor.terminal_sink(rec, lambda ev: None)(parse(line))
            assert rec["cost_usd"] is None
            assert supervisor.cost_report(rec) == (
                "\n- cost: unknown (the harness reported none)"
                "\n- tokens: 3,719 out · 438,060 in · 400,384 cache read · 0 cache write")

2. Add `test_the_session_entry_reports_codex_tokens_with_an_unknown_cost` to `tests/test_dispatch.py`, directly after `test_the_session_entry_omits_cost_when_no_result_event_arrived` (line 2170), modelled on `test_the_session_thread_entry_reports_cost_and_tokens` at line 2067:

        def test_the_session_entry_reports_codex_tokens_with_an_unknown_cost():
            """TICKET-120: `cost_report()` dropped a Codex run's tokens along with
            its absent dollar cost, so the session entry named neither."""
            d = project()
            path = d / ".project/tickets/TICKET-001.md"
            snap = Ticket.load(path)
            log = d / ".project" / "logs" / "TICKET-001.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            (d / ".project/tickets/TICKET-001.result").write_text(
                "result: ok\nsummary: x\n")
            rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
                   "path": path, "tid": "TICKET-001", "stage": "planning",
                   "session": "s1", "log": log, "wt": d, "meta": snap,
                   "before": None}
            supervisor.terminal_sink(rec, lambda ev: None)(
                {"kind": "result", "total_cost_usd": None,
                 "usage": {"input_tokens": 438060, "output_tokens": 3719,
                           "cache_read_input_tokens": 400384},
                 "terminal_reason": None})
            supervisor.finish(d, rec)
            msg = [e.text for e in Ticket.load(path).thread()
                   if "ran as session" in e.text][-1]
            assert "- cost: unknown (the harness reported none)" in msg
            assert ("- tokens: 3,719 out · 438,060 in · 400,384 cache read "
                    "· 0 cache write") in msg
            shutil.rmtree(d, ignore_errors=True)

3. Run the two new tests plus the repro in `tests/test_daemon.py` and `tests/test_dispatch.py` and watch all three fail: `uv run --group dev pytest -q tests/test_daemon.py -k cost_report tests/test_dispatch.py::test_the_session_entry_reports_codex_tokens_with_an_unknown_cost` prints `3 failed`, each on an empty `cost_report()` result.
4. Rewrite `cost_report()` in `pipeline/daemon/supervisor.py:300-325` so the cost line and the token line are independent -- replace the whole function with:

        def cost_report(rec: dict) -> str:
            """Render a run's cost and tokens for the session thread entry.

            The two lines are independent (TICKET-120). The cost line renders only
            when `cost_usd` is known; the token line renders whenever a count is
            non-zero, which a Codex `turn.completed` has and a dollar amount is not.
            An unknown cost prints `unknown`, never `$0.00`: no price is invented.

            `""` when no `result` event arrived (an interactive stage, DEC-077): its
            `usage` stays `{}`, so neither line renders and a zero-dollar line never
            reads as a free run. Every number is coerced, so a malformed `usage`
            never raises -- it renders zeros instead.
            """
            usage = rec.get("usage") or {}
            out = _int(usage.get("output_tokens"))
            thinking = _int(usage.get("output_tokens_details", {}).get("thinking_tokens")
                             if isinstance(usage.get("output_tokens_details"), dict) else None)
            inp = _int(usage.get("input_tokens"))
            cache_read = _int(usage.get("cache_read_input_tokens"))
            cache_write = _int(usage.get("cache_creation_input_tokens"))
            known = rec.get("cost_usd") is not None
            if not known and not (out or inp or cache_read or cache_write):
                return ""
            if known:
                cost = f"${float(rec['cost_usd']):.2f}"
                if rec.get("cap"):
                    cost += f" of a ${rec['cap']} cap"
            else:
                cost = "unknown (the harness reported none)"
            out_part = f"{out:,} out"
            if thinking:
                out_part += f" ({thinking:,} thinking)"
            tokens = (f"{out_part} · {inp:,} in · {cache_read:,} cache read "
                      f"· {cache_write:,} cache write")
            return f"\n- cost: {cost}\n- tokens: {tokens}"

5. Run the same selection over `tests/test_daemon.py` plus the Claude and interactive cases in `tests/test_dispatch.py` and watch them pass: `uv run --group dev pytest -q tests/test_daemon.py -k cost_report tests/test_dispatch.py -k "cost or session_entry"` reports no failure, then commit `pipeline/daemon/supervisor.py`, `tests/test_daemon.py` and `tests/test_dispatch.py` as `fix(TICKET-120): report Codex tokens when the cost is unknown`.
6. Add `test_codex_reasoning_tokens_map_to_the_thinking_field` to `tests/test_stream.py`, after `test_live_codex_fixture_captures_thread_guard_and_usage` (line 152), and watch it fail with `KeyError: 'output_tokens_details'`:

        def test_codex_reasoning_tokens_map_to_the_thinking_field():
            """TICKET-120: Codex reports `reasoning_output_tokens`; `cost_report()`
            and `metrics._tokens()` both read Claude's
            `output_tokens_details.thinking_tokens`, so an unmapped key showed 0."""
            u = parse('{"type":"turn.completed","usage":{"input_tokens":29748,'
                      '"cached_input_tokens":22016,"cache_write_input_tokens":0,'
                      '"output_tokens":135,"reasoning_output_tokens":15}}')["usage"]
            assert u["output_tokens_details"]["thinking_tokens"] == 15
            assert u["reasoning_output_tokens"] == 15
            kept = parse('{"type":"turn.completed","usage":{"output_tokens":9,'
                         '"reasoning_output_tokens":15,'
                         '"output_tokens_details":{"thinking_tokens":2}}}')["usage"]
            assert kept["output_tokens_details"]["thinking_tokens"] == 2

7. Map that key in `pipeline/stream/events.py`, beside the two `setdefault` calls at lines 111-117, by adding `if "reasoning_output_tokens" in raw_usage:` and under it `usage.setdefault("output_tokens_details", {"thinking_tokens": raw_usage["reasoning_output_tokens"]})` -- reasoning tokens are a subset of `output_tokens`, exactly as Claude's thinking tokens are, so the `(N thinking)` parenthesis keeps its meaning.
8. Run `uv run --group dev pytest -q tests/test_stream.py tests/test_metrics.py tests/test_daemon.py`, expect no failure, then commit `pipeline/stream/events.py` and `tests/test_stream.py` as `fix(TICKET-120): map Codex reasoning tokens to the thinking field`.
9. Rewrite the last sentence of the `CLAUDE.md` gotcha at lines 358-363 -- "An interactive stage emits no `result` event, so it gets neither line; its tokens reach the event log through `usage_events()` instead." -- as two sentences: "The two lines are independent: a Codex `turn.completed` has tokens and no dollar amount, so the cost reads `unknown` and the tokens still show (TICKET-120). An interactive stage emits no `result` event at all, so its `usage` stays empty and it gets neither line; its tokens reach the event log through `usage_events()` instead."
10. Append one sentence to `README.md` at line 450-452, after "the ticket's `## Thread` session entry carries the same number plus the run's token counts.": "A harness that reports no cost -- Codex -- gets `cost: unknown` in that entry and its token counts all the same."
11. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect no failure from either, then commit `CLAUDE.md` and `README.md` as `docs(TICKET-120): record the split cost and token lines`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable`
  exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_daemon.py::test_cost_report_renders_codex_tokens_and_an_unknown_cost`
  exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_the_session_entry_reports_codex_tokens_with_an_unknown_cost`
  exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_the_session_entry_omits_cost_when_no_result_event_arrived`
  exits 0 and prints `1 passed` -- an interactive stage still gets neither line.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_the_session_entry_names_the_budget_cap_and_the_thinking_tokens`
  exits 0 and prints `1 passed` -- a known Claude cost still prints its cap.
- `uv run --group dev pytest -q tests/test_stream.py::test_codex_reasoning_tokens_map_to_the_thinking_field`
  exits 0 and prints `1 passed`.
- `uv run --group dev python -c "from pipeline.daemon import supervisor as s; print(repr(s.cost_report({'cost_usd': None, 'usage': {}})))"`
  prints `''` -- an unmeasured run invents no line.
- `grep -c 'reported none' pipeline/daemon/supervisor.py` prints `1`.
- `uv run --group dev pytest -q` reports no failing test. Measured baseline on
  `ac87719`, 2026-09-06: `1 failed, 560 passed in 52.05s`, the one failure being this
  ticket's repro test.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

**The cost line and the token line are independent.** A run can have real tokens and
no dollar amount: Codex's `turn.completed` carries `usage` and no `cost_microusd`, so
`parse()` sets `total_cost_usd` to `None`. Gating the token line on a known cost, as
`cost_report()` did until TICKET-120, threw away measured numbers to report an
unmeasured one.

**An unknown cost prints `unknown (the harness reported none)`, never `$0.00`.** A
zero would enter the ticket as a price nobody charged, and DEC-085 already refused the
same zero for an interactive stage. No price is ever synthesized from tokens.

**DEC-085's interactive property now rests on `usage` being empty, not on `cost_usd`
being `None`.** An interactive stage emits no `result` event, so `spawn()`'s seed
`{"cost_usd": None, "usage": {}}` survives and `cost_report()` still returns `""`. A
future harness that reports usage without a cost gets both lines instead. Keep the
emptiness check if this function is reworked.

**A known cost renders exactly what it rendered before**, zero-valued token counts
included, so Claude's line in the thread stays byte-identical to TICKET-085's.

**Codex's `input_tokens` includes its `cached_input_tokens`** (438,060 against 400,384
in one run) and both are printed verbatim. Subtracting one from the other would report
a number the harness never gave.

**Codex reasoning tokens are mapped in `parse()`, not in each reader.**
`reasoning_output_tokens` becomes `output_tokens_details.thinking_tokens` beside the
two cache-key mappings already there, so `cost_report()` and `_tokens()` in
`pipeline/cli/metrics.py` both see them without a second Codex-specific branch. The
mapping uses `setdefault`, so a harness that sends the Claude shape keeps it.

## Rollback

Revert the three commits on `ticket/120`: the `cost_report()` split, the
`reasoning_output_tokens` mapping, and the docs. Nothing else calls `cost_report()`
and it feeds no control decision (DEC-085), so reverting only restores the silent
Codex session entry. If the token display alone is wrong, revert
`pipeline/stream/events.py` by itself: the `cost_report()` split does not depend on it.

## Thread

### 2026-09-05 16:20:32Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-05 16:44:56Z · triage · session · session=01a07275-6325-78c0-9aaf-0b0bc7858bdb

`triage` ran as session `01a07275-6325-78c0-9aaf-0b0bc7858bdb`
- replay: `codex exec resume 01a07275-6325-78c0-9aaf-0b0bc7858bdb`
- log: `.project/logs/TICKET-120-triage-b6482074.log`

### 2026-09-05 16:44:56Z · triage · note

`triage` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-05 16:45:05Z · triage · session · session=01a07275-7d9c-71d2-9242-3c95a7141865

`triage` ran as session `01a07275-7d9c-71d2-9242-3c95a7141865`
- replay: `codex exec resume 01a07275-7d9c-71d2-9242-3c95a7141865`
- log: `.project/logs/TICKET-120-triage-43e2f6f1.log`

### 2026-09-05 16:45:05Z · triage · escalation

`triage` wrote no .result sidecar 2 times

### 2026-09-05 17:34:57Z · human · note · by=chezzijr

**resumed** by chezzijr -> `triage`, reset [], granted `no_result` 2 -> 0

### 2026-09-05 17:34:57Z · human · answer · by=chezzijr

**note from chezzijr**

escalated on a Codex usage limit mid-turn, not on the ticket's own merits; continuing under claude-code

### 2026-09-05 17:35:11Z · triage · session · session=01a072a3-654c-7151-b7bb-750f5e697532

`triage` ran as session `01a072a3-654c-7151-b7bb-750f5e697532`
- replay: `codex exec resume 01a072a3-654c-7151-b7bb-750f5e697532`
- log: `.project/logs/TICKET-120-triage-ef0dcff0.log`

### 2026-09-05 17:35:11Z · triage · note

`triage` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-05 17:35:20Z · triage · session · session=01a072a3-7f22-7c82-ba26-11cb1965a082

`triage` ran as session `01a072a3-7f22-7c82-ba26-11cb1965a082`
- replay: `codex exec resume 01a072a3-7f22-7c82-ba26-11cb1965a082`
- log: `.project/logs/TICKET-120-triage-eccac16a.log`

### 2026-09-05 17:35:20Z · triage · escalation

`triage` wrote no .result sidecar 2 times

### 2026-09-05 17:36:02Z · human · note · by=chezzijr

**resumed** by chezzijr -> `triage`, reset [], granted `no_result` 2 -> 0

### 2026-09-05 17:36:02Z · human · answer · by=chezzijr

**note from chezzijr**

re-escalated by the codex daemon still holding its usage limit; resumed for claude-code

### 2026-09-06 · implementing · todo

1. [x] add `test_cost_report_renders_codex_tokens_and_an_unknown_cost` to tests/test_daemon.py
2. [x] add `test_the_session_entry_reports_codex_tokens_with_an_unknown_cost` to tests/test_dispatch.py
3. [x] run new tests plus repro, confirm RED
4. [x] rewrite cost_report() in pipeline/daemon/supervisor.py
5. [x] run tests, confirm GREEN, commit fix
6. [x] add test_codex_reasoning_tokens_map_to_the_thinking_field to tests/test_stream.py, confirm RED
7. [x] map reasoning_output_tokens in pipeline/stream/events.py
8. [x] run tests, confirm GREEN, commit
9. [x] update CLAUDE.md gotcha
10. [x] update README.md
11. [x] run full suite plus hook tests, commit docs

### 2026-09-06 · implementing · report

Executed all 11 plan steps. Three commits on `ticket/120`:
`03761c0` fix(TICKET-120): report Codex tokens when the cost is unknown,
`ba205d8` fix(TICKET-120): map Codex reasoning tokens to the thinking field,
`ba8d22e` docs(TICKET-120): record the split cost and token lines.

Each new test failed for the expected reason before its fix, verified:
`test_cost_report_renders_codex_tokens_and_an_unknown_cost` and
`test_the_session_entry_reports_codex_tokens_with_an_unknown_cost` both
returned `''`/no cost-or-tokens lines pre-fix;
`test_codex_reasoning_tokens_map_to_the_thinking_field` raised
`KeyError: 'output_tokens_details'` pre-fix.

All acceptance criteria met:
- `uv run --group dev pytest -q` -> `581 passed` (baseline was `1 failed, 560 passed`).
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.
- `cost_report({'cost_usd': None, 'usage': {}})` -> `''`.
- `grep -c 'reported none' pipeline/daemon/supervisor.py` -> `1`.

No plan deviation.

### 2026-09-06 · triage · note

Reproduced: `cost_report()` in `pipeline/daemon/supervisor.py:300-325` checks
`rec["cost_usd"] is None` first and returns `""` immediately, so a Codex
`turn.completed` record's `usage` (real tokens, no dollar cost) is dropped
along with the missing cost. Added
`tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable`,
which fails with `AssertionError: assert '' != ''`. Committed as `ac87719`
on branch `ticket/120`.

Fix should split the cost line (rendered only when `cost_usd` is not None)
from the token line (rendered whenever `usage` has data), so unknown cost
stays visibly unknown while tokens still show. `files_declared` expected:
`pipeline/daemon/supervisor.py`.

### 2026-09-05 17:37:22Z · triage · session · session=da982f24-1d46-45a6-9079-a42bd5acdc26

`triage` ran as session `da982f24-1d46-45a6-9079-a42bd5acdc26`
- replay: `claude --resume da982f24-1d46-45a6-9079-a42bd5acdc26`
- log: `.project/logs/TICKET-120-triage-da982f24.log`
- cost: $0.37 of a $3 cap
- tokens: 4,450 out (136 thinking) · 46 in · 906,423 cache read · 35,177 cache write

### 2026-09-05 17:37:22Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced cost_report dropping Codex token usage when cost_usd is None

### 2026-09-06 · planning · note

Plan written. The fix splits `cost_report()` in `pipeline/daemon/supervisor.py`
into two independent lines: the cost line renders only when `cost_usd` is known,
the token line whenever a count is non-zero. An unknown cost prints
`unknown (the harness reported none)`.

Scope note, one addition beyond triage's `supervisor.py`: Codex reports reasoning
tokens as `reasoning_output_tokens`, and both `cost_report()` and
`_tokens()` in `pipeline/cli/metrics.py` read Claude's
`output_tokens_details.thinking_tokens`, so Codex thinking tokens are dropped
today. Step 7 maps the key in `pipeline/stream/events.py` beside the two cache-key
mappings already there. It is its own step and its own commit; a reviewer can
reject it without touching the fix.

Metrics need no change. The live event log already holds Codex `result` rows with
`total_cost_usd` `null` and full `usage`, and `_cost_events()` reads them.

Not in scope, noted for a later ticket: `pipeline ls -v` prints no cost for a
Codex run, because `cmd_ls` at `pipeline/cli/main.py:462` omits the field when
`last_session["cost_usd"]` is `None`. The ticket asks for the session entry and
metrics; the `ls` line is a separate display.

### 2026-09-05 17:45:18Z · planning · session · session=00b45d75-6b17-4e29-bee6-17a615554940

`planning` ran as session `00b45d75-6b17-4e29-bee6-17a615554940`
- replay: `claude --resume 00b45d75-6b17-4e29-bee6-17a615554940`
- log: `.project/logs/TICKET-120-planning-00b45d75.log`
- cost: $2.88 of a $10 cap
- tokens: 35,518 out (13,392 thinking) · 62 in · 2,010,155 cache read · 98,335 cache write

### 2026-09-05 17:45:18Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned the cost/token split in cost_report() plus the Codex reasoning-token mapping

### 2026-09-06 07:12:53Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable` fails as required
```
ts/test_daemon.py F

=================================== FAILURES ===================================
______ test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable _______

    def test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable():
        rec = {"cost_usd": None, "usage": {"input_tokens": 438060,
                                            "cached_input_tokens": 400384,
                                            "output_tokens": 3719}}
>       assert supervisor.cost_report(rec) != ""
E       AssertionError: assert '' != ''
E        +  where '' = <function cost_report at 0x7fa34c90ccc0>({'cost_usd': None, 'usage': {'input_tokens': 438060, 'cached_input_tokens': 400384, 'output_tokens': 3719}})
E        +    where <function cost_report at 0x7fa34c90ccc0> = supervisor.cost_report

tests/test_daemon.py:1072: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.12s ===============================

```
- ok: `tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable` fails on base `main` too -- the bug is not already fixed upstream
```
 assert '' != ''
E        +  where '' = <function cost_report at 0x7f9b85221e40>({'cost_usd': None, 'usage': {'input_tokens': 438060, 'cached_input_tokens': 400384, 'output_tokens': 3719}})
E        +    where <function cost_report at 0x7f9b85221e40> = supervisor.cost_report

tests/test_daemon.py:1072: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.35s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-piou0s4w/base
      Built pipeline @ file:///tmp/pipeline-base-piou0s4w/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-09-06 · plan-validation · note

**Tier B: PASS.** Every item scored against the code the plan names.

1. Root cause: `cost_report()` uses `cost_usd is None` as a proxy for "no
   `result` event arrived". A harness that reports `usage` without a price
   fails that proxy, so both lines vanish. The plan fixes the proxy -- empty
   `usage` becomes the predicate -- not just the symptom.
2. Decisions: DEC-085 constrains this plan and states the interactive property
   as "`rec["cost_usd"]` stays `None` and `cost_report()` returns `""`". The
   plan supersedes that mechanism explicitly and keeps the observable
   property; the cap, the coercion and the formatting-only rule survive.
3. Scope: 11 steps, 7 files, all traceable. Steps 6-7 (`reasoning_output_tokens`)
   sit beyond triage's declared file but carry their own criterion and commit.
   Steps 9-10 keep the CLAUDE.md gotcha at lines 358-363 from stating the old
   behaviour; I verified both quoted anchors match the files verbatim.
4. Criteria: falsifiable. `cost_report({'cost_usd': None, 'usage': {}})` must
   print `''`; a wrong split prints a line.
5. No research left: every step names a file, a function and a line.
6. Riskiest step: 4, the whole-function replacement. Fallback stated -- step 5
   runs the Claude and interactive tests before the commit, and `## Rollback`
   reverts that commit alone.
7. Regression surface: `test_the_session_entry_names_the_budget_cap_and_the_thinking_tokens`
   (2108) and `test_the_session_entry_omits_cost_when_no_result_event_arrived`
   (2146) cover the two paths at risk; I traced the proposed body against both
   and against `tests/test_stream.py:152`, which the step-7 `setdefault` leaves
   intact. Blast radius fits `bugfix`.
8. Verified: `CLAUDE.md`, `README.md`, `supervisor.py` and `events.py` are
   absent from `machine.FENCED`; `tests/fixtures/stream-codex.ndjson:7` holds
   the exact numbers step 6 asserts.

Unverified: I did not execute the proposed `cost_report()`. I traced it by
reading. I would have run
`uv run --group dev pytest -q tests/test_dispatch.py -k "cost or session_entry"`
against a patched tree, which a read-only stage cannot produce.

### 2026-09-06 07:15:18Z · plan-validation · session · session=1306633c-61fd-4788-b14c-1bfb2207d138

`plan-validation` ran as session `1306633c-61fd-4788-b14c-1bfb2207d138`
- replay: `claude --resume 1306633c-61fd-4788-b14c-1bfb2207d138`
- log: `.project/logs/TICKET-120-plan-validation-1306633c.log`
- cost: $1.11 of a $3 cap
- tokens: 10,569 out (5,204 thinking) · 30 in · 658,098 cache read · 51,662 cache write

### 2026-09-06 07:15:18Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes every item: root cause named, DEC-085 superseded with justification, criteria falsifiable

### 2026-09-06 07:19:27Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-06 07:36:13Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable` fails as required
```
ts/test_daemon.py F

=================================== FAILURES ===================================
______ test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable _______

    def test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable():
        rec = {"cost_usd": None, "usage": {"input_tokens": 438060,
                                            "cached_input_tokens": 400384,
                                            "output_tokens": 3719}}
>       assert supervisor.cost_report(rec) != ""
E       AssertionError: assert '' != ''
E        +  where '' = <function cost_report at 0x7fd799df9760>({'cost_usd': None, 'usage': {'input_tokens': 438060, 'cached_input_tokens': 400384, 'output_tokens': 3719}})
E        +    where <function cost_report at 0x7fd799df9760> = supervisor.cost_report

tests/test_daemon.py:1072: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================

```
- ok: `tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable` fails on base `main` too -- the bug is not already fixed upstream
```
 assert '' != ''
E        +  where '' = <function cost_report at 0x7f3286789e40>({'cost_usd': None, 'usage': {'input_tokens': 438060, 'cached_input_tokens': 400384, 'output_tokens': 3719}})
E        +    where <function cost_report at 0x7f3286789e40> = supervisor.cost_report

tests/test_daemon.py:1072: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_cost_report_keeps_codex_token_usage_when_cost_is_unavailable
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.33s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-v66nlnqc/base
      Built pipeline @ file:///tmp/pipeline-base-v66nlnqc/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 25ms

```

### 2026-09-06 07:36:13Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-06 07:40:22Z · implementing · session · session=ea499ed1-f72e-41e6-a6a5-39196b9c6afc

`implementing` ran as session `ea499ed1-f72e-41e6-a6a5-39196b9c6afc`
- replay: `claude --resume ea499ed1-f72e-41e6-a6a5-39196b9c6afc`
- log: `.project/logs/TICKET-120-implementing-ea499ed1.log`
- cost: $0.90 of a $8 cap
- tokens: 13,061 out (532 thinking) · 88 in · 2,589,725 cache read · 62,370 cache write

### 2026-09-06 07:40:22Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ split cost_report() cost/token lines and mapped Codex reasoning tokens; full suite 581 passed, guard exit 0

### 2026-09-06 · review · note

**Review: no blocking findings.** I reviewed the whole branch delta
(`git diff main...HEAD`, four commits, 7 files, +94/-13). The thread holds no
earlier review entry, so the delta is the branch.

I re-ran every acceptance criterion. `uv run --group dev pytest -q` prints
`581 passed in 55.97s`. `./pipeline/hooks/test_dangerous_commands.py` prints
`guard: all passed` and exits 0. `grep -c 'reported none'
pipeline/daemon/supervisor.py` prints `1`. `cost_report({'cost_usd': None,
'usage': {}})` returns `''`. `cost_report({'cost_usd': 6.089121, 'cap': 10,
'usage': {}})` returns the `$6.09 of a $10 cap` line TICKET-085 specified,
unchanged.

The code matches the plan step for step. `_norm()` builds
`usage = dict(raw_usage)` (`pipeline/stream/events.py:112`), so the new
`setdefault` mutates no caller's event. `_tokens()` reports `think` as its own
column (`pipeline/cli/metrics.py:227`, `pipeline/cli/metrics.py:273`), so the
mapped reasoning tokens are never added into `out`. No touched file is in
`machine.FENCED` (`pipeline/core/machine.py:43-62`). The working tree is clean.

Two nits, neither blocking:

1. Nit. `cost_report()` returns `''` when `usage` is present but every count
   coerces to 0. Probe: `cost_report({'cost_usd': None, 'usage':
   {'output_tokens': 'x'}})` returns `''`. A real Codex `turn.completed`
   carries a non-zero `input_tokens`, so no captured run reaches this.
2. Nit. `cost_report()` raises `AttributeError` on a truthy non-dict `usage`,
   and the unknown-cost path now reaches that line where it returned early
   before. `parse()` coerces `usage` for `turn.completed`
   (`pipeline/stream/events.py:111`) but not for a Claude `result`
   (`pipeline/stream/events.py:169`). TICKET-085's review logged this as its
   nit 2; the split widens it. It needs a malformed harness line, and `run()`
   escalates one ticket rather than dropping the loop.

### 2026-09-06 07:43:59Z · review · session · session=261b610d-cd74-4046-a98f-ba49737276d1

`review` ran as session `261b610d-cd74-4046-a98f-ba49737276d1`
- replay: `claude --resume 261b610d-cd74-4046-a98f-ba49737276d1`
- log: `.project/logs/TICKET-120-review-261b610d.log`
- cost: $1.47 of a $5 cap
- tokens: 12,283 out (3,715 thinking) · 46 in · 1,141,023 cache read · 59,583 cache write

### 2026-09-06 07:43:59Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ delta matches the plan; suite 581 passed, guard exit 0, every acceptance criterion re-run; two nits, none blocking

### 2026-09-06 07:44:57Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-06 10:34:25Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/120


Rebasing (1/4)Rebasing (2/4)Rebasing (3/4)Rebasing (4/4)Successfully rebased and updated refs/heads/ticket/120.
Already up to date.
Updating a8cb517..0aa9336
Fast-forward
 CLAUDE.md                     |  9 ++++++---
 README.md                     |  3 ++-
 pipeline/daemon/supervisor.py | 27 ++++++++++++++++++---------
 pipeline/stream/events.py     |  3 +++
 tests/test_daemon.py          | 22 ++++++++++++++++++++++
 tests/test_dispatch.py        | 28 ++++++++++++++++++++++++++++
 tests/test_stream.py          | 15 +++++++++++++++
 7 files changed, 94 insertions(+), 13 deletions(-)

```

### 2026-09-06 10:34:25Z · merging · decision

decision recorded as `DEC-120`
