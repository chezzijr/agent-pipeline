---
id: TICKET-022
stage: done
class: feature
branch: ticket/022
test_file: tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied
files_declared:
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 0
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: holistic-review
  id: 908b4f4d-5456-4958-93e7-b2b3adf4f5fc
  log: .project/logs/TICKET-022-holistic-review-908b4f4d.log
approved_by: chezzijr
approved_at: '2026-08-21T08:41:02.871910+00:00'
---

## Summary

`pipeline/stages/_common.md:60` tells every stage to start `summary:` with `✓`.
Nothing in `pipeline/` reads it, so a stage that drops the marker advances
exactly like one that keeps it. The failing test is
`tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied`,
committed as `9ce9675`.

The plan records the marker in `advance()` (`pipeline/daemon/supervisor.py:73`),
in two places at once:

1. a `marker` boolean inside the `transition` event's `data`, for counting;
2. a `marker=yes` / `marker=no` attribute on the thread entry's header, for a
   human reading the ticket.

`advance()` reads the note before `t.append()` copies it into the thread.

Only an agent's `.result` summary is judged. `advance()` takes a new
`agent: bool = True` parameter, and the four dispatcher-owned call sites
(`pipeline/daemon/supervisor.py` lines 460, 523, 574, 595) pass `agent=False`.
Their events carry no `marker` key at all, because "the dispatcher wrote this
note" and "an agent dropped the rule" are different facts.

A missing marker is evidence only. It changes no transition and escalates no
ticket.

Plan validation passed on 2026-08-21. All eight items scored pass; the
per-item findings are in `## Thread`. Every file, line and call site the plan
names exists as written: `advance()` at `pipeline/daemon/supervisor.py:73`, the
five call sites at lines 460, 523, 574, 595, 715, and `t.append(...)` at lines
92-93. Implement the plan as written.

One correction for the implementer, in step 3 only. The plan predicts
`KeyError: 'marker'` first. The step-1 test runs all four `run()` calls before
its first assertion, so the first failure is
`TypeError: advance() got an unexpected keyword argument 'agent'`. Both errors
are the plan's; only the order is wrong. Nothing else changes.

**Implemented on 2026-08-21, committed as `436e483`.** All ten plan steps done
as written, including the step-3 correction above. `advance()`
(`pipeline/daemon/supervisor.py`) gained `MARKER`, `has_marker()`, and an
`agent: bool = True` parameter; the four dispatcher-owned call sites (lines
486, 549, 600, 621) pass `agent=False`; line 742 (`_finish()`) is untouched.
Three marker tests pass (`3 passed, 20 deselected in 0.05s`); the five-file
regression set passes (`93 passed in 4.26s`); the ticket's named failing test
now passes (`1 passed in 0.04s`). Only the two declared files changed.

**Review pass 1 on 2026-08-21: FAIL, one blocking finding.** Every acceptance
criterion passes and I reran both commands to confirm (`3 passed, 20
deselected in 0.04s` and `93 passed in 4.15s`). The blocking finding is a
regression the delta introduced, outside the criteria.

`has_marker()` calls `note.lstrip()`, and `_finish()`
(`pipeline/daemon/supervisor.py:742`) passes it `res.get("summary", "")`, an
agent value nothing validates -- `summary` is not in `CLAIMS`. A sidecar
written as `summary:` with no value parses to `None` and raises
`AttributeError: 'NoneType' object has no attribute 'lstrip'`. `summary:
2026-08-21` arrives as a `datetime.date` by the same route.

The cost is a lost stage run. `drop_result()` runs at line 739, one line
before `advance()`, so the sidecar is gone when the exception fires; `reap()`
catches it at line 771, `advance()` never runs, and the lease is held until it
expires. `log_tail()`'s docstring records the same failure from a previous
occurrence.

Fix: `str(note or "").lstrip().startswith(MARKER)` in `has_marker()`, plus the
`summary: None` case in
`test_the_marker_record_names_the_agents_summary_and_nothing_else`. Two
non-blocking findings and the checks that found nothing are in `## Thread`
under `severity=blocking`.

**Fixed on 2026-08-21, committed as `0f16551`.** `has_marker()` now reads
`str(note or "").lstrip().startswith(MARKER)`. Added the `summary: None`
case to `test_the_marker_record_names_the_agents_summary_and_nothing_else`
and confirmed it raised `AttributeError: 'NoneType' object has no attribute
'lstrip'` before the fix. Three marker tests pass (`3 passed, 20 deselected in
0.05s`); the five-file regression set passes (`93 passed in 4.16s`); the
ticket's named failing test still passes (`1 passed in 0.03s`). Only the two
declared files changed.

**Review pass 2 on 2026-08-21: PASS, no blocking findings.** Delta reviewed:
commit `0f16551` alone, the only commit since the pass-1 review entry. Pass 1's
blocking finding is resolved: `has_marker()` returns `False` for a `None`
summary and for a `datetime.date`, instead of raising, and still returns `True`
for `✓x`. I reran both commands the ticket names -- `3 passed, 20 deselected in
0.04s` and `93 passed in 4.08s`. `git status --short` is empty and the branch
diff touches only the two declared files.

Three non-blocking findings are in `## Thread` under the pass-2 `review · note`
entry. The one worth acting on later: `has_marker()`'s annotation still says
`note: str` and its docstring does not mention the coercion, so a future reader
could revert `str(note or "")` and restore the bug. The branch is ready to
merge.

**Holistic review on 2026-08-21: PASS, coherent.** The three commits
(`9ce9675`, `436e483`, `0f16551`) sum to what `## Plan` described: 2 files, 112
insertions, 7 deletions, both files declared, `git status --short` empty. The
`0f16551` fix widens `has_marker()`'s coercion and undoes nothing from
`436e483`. All five `advance()` call sites are consistent -- lines 486, 549,
600, 621 pass `agent=False`, line 742 takes the default. Nothing landed outside
the acceptance criteria except the `summary: None` regression test that pass 1
required. I reran both commands: `3 passed, 20 deselected in 0.04s` and `93
passed in 4.11s`. The one carried-forward, non-blocking finding is
`has_marker()`'s `note: str` annotation, which no longer matches the coerced
body.

## Reproduction

Test: `tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied`

Command:

    uv run --group dev pytest -q "tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied"

The test calls `supervisor.advance()` twice on identical tickets, once with a
summary that starts with the marker and once without. It captures the emitted
events and the ticket body, with the summary text stripped out so the thread
echo cannot pass it vacuously. Both runs leave identical evidence.

Failure output:

    E       AssertionError: the marker is not recorded: a summary with it and a summary without it leave identical events and identical ticket text
    E         events: [('transition', {'ticket': 'TICKET-001', 'stage': 'plan-validation', 'from': 'plan-validation', 'to': 'awaiting-approval', 'result': 'ok', 'counters': {}})]
    tests/test_dispatch.py:541: AssertionError
    1 failed in 0.07s

expect: AssertionError: the marker is not recorded

The test is design-neutral: it passes if the record lands in the event payload,
in the thread, or in both. It fails only if nothing records the marker.

Committed as `9ce9675`.

## Digest

Files this change touches:

- `pipeline/daemon/supervisor.py` -- `advance()` and its five call sites.
- `tests/test_dispatch.py` -- the committed test plus two new ones.

Key functions:

- `advance(project, t, result, note, emit=noop)` at
  `pipeline/daemon/supervisor.py:73`. It calls `transition()`, emits
  `transition`, may emit `escalated`, then calls
  `t.append(stage, "transition", ...)`, then sets `t.counters` / `t.stage`,
  releases the lease and saves. The `note` argument is the agent's `summary`
  verbatim; nothing strips it before `advance()` sees it.
- `Ticket.append(stage, kind, text, **attrs)` at `pipeline/core/ticket.py:507`
  renders attrs into the entry header as `k=v` joined by ` · `, e.g.
  `### 2026-08-21 08:22:13Z · triage · transition · to=planning · result=ok`.
  `_parse_header()` (`pipeline/core/ticket.py:418`) reads them back as strings.
  Nothing in `pipeline/` consumes a transition entry's attrs today.
- `loose_result()` at `pipeline/core/ticket.py:198` is the fallback sidecar
  parser. It takes `rest.strip()`, so a YAML-broken sidecar can arrive with the
  space after the marker already gone.

Entry points -- the five `advance()` call sites, all in
`pipeline/daemon/supervisor.py`:

- line 460 `advance(project, t, "new", "dispatcher pickup", emit)` -- dispatcher.
- line 523, the failed Tier A gate note -- dispatcher.
- line 574 in `finish_child()`, `"<label> exit <code>"` -- dispatcher.
- line 595 in `finish_regate()`, the re-gate note -- dispatcher.
- line 715 in `_finish()`, `res.get("summary", "")` -- the agent's summary, the
  only call site this ticket is about.

`pipeline/cli/main.py:95` emits a second `transition` event for the human gates
(`approve` / `reject` / `answer`). It never calls `advance()`, has no summary,
and stays untouched: its events carry no `marker` key.

Gotchas:

- Match the character, not the character plus a space. `loose_result()` strips
  it; a `startswith("✓ ")` test reads a YAML-broken but correctly marked
  sidecar as unmarked.
- Read the note before `t.append()` runs, not after: `advance()` writes the
  summary into the thread and later readers see the copy.
- Tier A parses `## Plan`: every non-blank line must be a numbered step or an
  indented continuation, so the code in the steps below is indented.
- The committed test compares `(events, body)` between two runs with the summary
  text stripped out. An event field alone satisfies it; the thread attr alone
  satisfies it; this plan does both.
- `tests/test_cli.py:196` and `tests/test_metrics.py` read `transition` event
  data by key (`json_extract(data,'$.to')`), never by whole-dict equality, so an
  added key breaks nothing.

## Decisions checked

Grep terms used against `/home/chezzijr/proj/claude-setup/.project/decisions/`:
`marker`, `summary`, `transition`, `event`, `advance`, `thread`, `superseded-by`.
No record carries a `superseded-by:` line, so every citation below is active.

- **DEC-011** (the frozen daemon contract) is the binding one. It says: "Adding
  a `kind` or a field inside `data` is additive and fine; changing a column, a
  kind's name, or the meaning of an existing field is not." This plan adds
  `marker` inside the `transition` event's `data` and changes no existing field,
  so it complies without superseding anything. DEC-011's kind table lists
  `transition | {from, to, result, counters}`; the new key is additive to that
  row, and this ticket's `## Decisions` records it rather than editing the
  frozen table.
- **DEC-016** constrains the thread: fence state is parsed once in `_fenced()`
  and all three heading scans consult it. This plan adds an attribute to an
  existing `Ticket.append()` call and adds no fourth scan over a ticket body, so
  the rule is untouched.
- **DEC-018** is why the citations above resolve against the project root
  `.project/decisions/`, not the worktree copy.

## Plan

1. Add this test to `tests/test_dispatch.py`, directly after `test_the_summary_marker_is_recorded_when_a_verdict_is_applied`:

        def test_the_marker_record_names_the_agents_summary_and_nothing_else():
            """The marker is evidence about a stage prompt, never a verdict, so it
            is recorded per stage in two places: a `marker` field on the
            `transition` event, and a `marker=` attr on the thread entry header.

            The dispatcher's own notes -- `dispatcher pickup`, a failed gate, a
            merge exit code -- were written by no agent, so they carry no field
            at all. A `False` there would read as a prompt that dropped the rule.
            """
            def run(summary: str, **kw) -> tuple[dict, str]:
                d = project()
                path = d / ".project/tickets/TICKET-001.md"
                seen: list = []
                supervisor.advance(d, Ticket.load(path), "ok", summary,
                                   lambda kind, **k: seen.append(k), **kw)
                body = path.read_text()
                shutil.rmtree(d, ignore_errors=True)
                return seen[0], body

            marked, marked_body = run("✓ planned")
            tight, _ = run("✓planned")           # loose_result() ate the space
            bare, bare_body = run("planned")
            pickup, pickup_body = run("dispatcher pickup", agent=False)

            assert marked["marker"] is True
            assert tight["marker"] is True, "match the character, not character+space"
            assert bare["marker"] is False
            assert "marker=yes" in marked_body and "marker=no" in bare_body
            assert "marker" not in pickup, pickup
            assert "marker=" not in pickup_body

2. Add this second test to `tests/test_dispatch.py`, directly after the test from step 1:

        def test_a_missing_marker_changes_no_transition_and_no_counter():
            """Evidence, not a verdict: an unmarked summary must advance exactly
            like a marked one. If this ever fails, someone turned a prose-rule
            reminder into a gate on the agent's work."""
            d = project()
            path = d / ".project/tickets/TICKET-001.md"
            supervisor.advance(d, Ticket.load(path), "ok", "no marker here")
            t = Ticket.load(path)
            shutil.rmtree(d, ignore_errors=True)
            assert t.stage == "awaiting-approval"
            assert t.counters == {}

3. Run the two new tests in `tests/test_dispatch.py` and confirm the first one fails before the implementation exists: `uv run --group dev pytest -q tests/test_dispatch.py -k marker`. Expect `KeyError: 'marker'` from step 1's test, and `TypeError: advance() got an unexpected keyword argument 'agent'` once that `KeyError` is fixed. Step 2's test passes already -- it is a tripwire, not a reproduction.

4. Add the marker reader to `pipeline/daemon/supervisor.py`, immediately above `def advance(` (line 73):

        # `pipeline/stages/_common.md` tells every stage to start `summary:` with
        # this character. It is evidence about the agent's context, never a
        # verdict: nothing below acts on its absence.
        MARKER = "✓"


        def has_marker(note: str) -> bool:
            """Did this summary still carry the shared prose rules' marker?

            The character, NOT the character plus a space: `loose_result()`
            (`pipeline/core/ticket.py`) takes `rest.strip()`, so a sidecar whose
            YAML broke arrives with the space already gone, and a `"✓ "` prefix
            test would report a marked stage as unmarked.
            """
            return note.lstrip().startswith(MARKER)

5. Rewrite the head of `advance()` in `pipeline/daemon/supervisor.py` (lines 73-77) so it takes `agent` and computes the record before anything copies the note:

        def advance(project: Path, t: Ticket, result: str, note: str, emit=noop,
                    agent: bool = True) -> None:
            # `agent` says this note is an agent's `.result` summary. The
            # dispatcher's own notes are nobody's prose, so they get no `marker`
            # key at all -- absent means "not applicable", False means "a stage
            # prompt lost the rule", and collapsing the two would count every
            # dispatcher pickup as a failure.
            stage = t.stage
            nxt, counters = transition(stage, result, t.counters, t.klass)
            marker = has_marker(note) if agent else None   # BEFORE t.append copies the note
            ev = {} if marker is None else {"marker": marker}
            attrs = {} if marker is None else {"marker": "yes" if marker else "no"}
            emit("transition", ticket=t.id, stage=stage, **{"from": stage, "to": nxt,
                 "result": result, "counters": counters}, **ev)

6. In the same function in `pipeline/daemon/supervisor.py` (lines 92-93), pass the header attrs to the thread entry, leaving the `escalated` emit between them untouched:

        t.append(stage, "transition", f"**{stage} -> {nxt}** (result: `{result}`)\n\n{note}",
                 to=nxt, result=result, **attrs)

7. Pass `agent=False` at the four dispatcher-owned call sites in `pipeline/daemon/supervisor.py`: line 460 (`advance(project, t, "new", "dispatcher pickup", emit, agent=False)`), line 523 (the failed Tier A gate note), line 574 (in `finish_child()`), and line 595 (in `finish_regate()`). Leave line 715 in `_finish()` alone -- that call site is the agent's summary and takes the default.

8. Run the three marker tests in `tests/test_dispatch.py` and expect `3 passed`: `uv run --group dev pytest -q tests/test_dispatch.py -k marker`.

9. Run the files that read `transition` events or ticket threads, and expect no failures: `uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py tests/test_daemon.py tests/test_metrics.py tests/test_ticket.py`.

10. Commit `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py` together: `git add pipeline/daemon/supervisor.py tests/test_dispatch.py && git commit -m "feat: record whether a stage's summary carried the prose marker"`.

## Acceptance criteria

- `tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied` passes; it fails today with `AssertionError: the marker is not recorded`.
- `tests/test_dispatch.py::test_the_marker_record_names_the_agents_summary_and_nothing_else` passes: the `transition` event's `marker` is `True` for `"✓ planned"`, `True` for `"✓planned"`, and `False` for `"planned"`.
- The same test proves the thread record: the ticket body contains `marker=yes` after a marked summary and `marker=no` after an unmarked one.
- The same test proves the scope: a call with `agent=False` emits no `marker` key and writes no `marker=` attr.
- `tests/test_dispatch.py::test_a_missing_marker_changes_no_transition_and_no_counter` passes: an unmarked summary still lands in `awaiting-approval` with `counters == {}`.
- `uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py tests/test_daemon.py tests/test_metrics.py tests/test_ticket.py` reports 0 failures.

## Decisions

**The marker is evidence, never a verdict.** `advance()` records whether a
stage's summary began with `✓` and then ignores it: no transition changes, no
counter is charged, nothing escalates. The marker answers one question -- were
the shared prose rules still in the agent's context at the end of a long run --
and a rule that failed the ticket would instead teach every stage to prepend two
characters and prove nothing.
`tests/test_dispatch.py::test_a_missing_marker_changes_no_transition_and_no_counter`
is the tripwire.

**Match the character, not the character plus a space.** `loose_result()`
(`pipeline/core/ticket.py`) parses a sidecar YAML could not read, and it takes
`rest.strip()`, which keeps `✓` and drops the space after it. A
`startswith("✓ ")` check would report exactly the stages whose summary broke
YAML -- the ones most worth measuring -- as unmarked.

**Absent is not False.** Only an agent's `.result` summary is judged, so
`advance(agent=False)` emits no `marker` key at all. The dispatcher's own notes
-- `dispatcher pickup`, a failed Tier A gate, `regression suite exit 0`, a
re-gate -- were written by no agent, and recording `False` for them would count
every dispatcher pickup as a prompt that lost the rule. A new dispatcher-owned
`advance()` call site must pass `agent=False`; the default is `True` because the
agent path is the one this exists for.

**Read the note before the thread copies it.** `advance()` computes the marker
before `t.append()` writes the summary into `## Thread`. Any future reader of the
marker goes in the same place, ahead of anything that rewrites the text.

**The record is both an event field and a thread attribute, deliberately.** The
event field (`data.marker` on `transition`) is what a metrics view can count; the
header attr (`marker=yes|no`) is what a human reading the ticket sees without
opening SQLite. DEC-011 permits the added field: "Adding a `kind` or a field
inside `data` is additive and fine."

**No metrics view was added.** A per-stage marker rate is one SQL string over
`kind='transition'` with `json_extract(data,'$.marker')`, and
`pipeline/cli/metrics.py` already has six views to copy. It was left out because
nothing has asked that question yet; recording the data from now on is the part
that cannot be added retroactively.

## Rollback

Revert the single commit touching `pipeline/daemon/supervisor.py` and
`tests/test_dispatch.py`. Nothing else depends on it:

- No schema change. `marker` lives inside the `events.data` JSON blob, so rows
  written while it shipped stay readable and every existing query ignores the
  key.
- No control flow to unwind. The field is written and never read by the state
  machine, so removing it cannot strand a ticket mid-pipeline.
- Ticket files written while it shipped keep a `marker=yes|no` attr in some
  thread headers. `_parse_header()` reads unknown attrs into a dict nobody
  consumes, so they are inert text after the revert.

## Thread

### 2026-08-21 08:20:07Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 · triage · note

Reproduced. `grep -rn "✓" pipeline tests` returns one line, and it is the
instruction itself:

    pipeline/stages/_common.md:60:Start `summary:` in your result file with `✓ `. It costs two characters, and it

The summary reaches `advance(project, t, result, res.get("summary", ""), emit)`
at `pipeline/daemon/supervisor.py:715`. `advance()` writes the summary into the
thread verbatim and emits `transition` without inspecting the text. That is the
only place the sidecar summary is used.

Two facts for the planning stage, both outside my scope:

1. `read_result()` strips nothing, so the marker survives to `advance()`. A
   reader placed in `advance()` sees the raw text.
2. `loose_result()` takes `rest.strip()`, which keeps the marker but drops the
   space after it. A check for the literal `"✓ "` prefix would read a
   YAML-broken sidecar as unmarked. Match the character, not the character plus
   a space.

### 2026-08-21 08:22:13Z · triage · session · session=c35f8ec7-003f-4b20-9ea2-7b4413e548a7

`triage` ran as session `c35f8ec7-003f-4b20-9ea2-7b4413e548a7`
- replay: `claude --resume c35f8ec7-003f-4b20-9ea2-7b4413e548a7`
- log: `.project/logs/TICKET-022-triage-c35f8ec7.log`

### 2026-08-21 08:22:13Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

✓ reproduced: advance() records nothing about the summary marker; failing test committed as 9ce9675

### 2026-08-21 08:41:00Z · planning · note

Plan written. The ticket left the location open -- event field, thread note, or
both. Resolved as both, and narrowed to the agent's own summary.

1. `advance()` (`pipeline/daemon/supervisor.py:73`) gains `agent: bool = True`.
2. An agent summary emits `marker: true|false` inside the `transition` event's
   `data`, and writes `marker=yes|no` onto the thread entry header.
3. The four dispatcher-owned call sites pass `agent=False` and emit no `marker`
   key. Absent means "no agent wrote this note", not "the rule was dropped".
4. The check is `note.lstrip().startswith("✓")`, per the triage note about
   `loose_result()` stripping the space.

No metrics view was added. `## Decisions` records why, and the one SQL string
that adds one later.

### 2026-08-21 08:29:56Z · planning · session · session=633a2215-5306-499a-9fb1-ee375c91beed

`planning` ran as session `633a2215-5306-499a-9fb1-ee375c91beed`
- replay: `claude --resume 633a2215-5306-499a-9fb1-ee375c91beed`
- log: `.project/logs/TICKET-022-planning-633a2215.log`

### 2026-08-21 08:29:56Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

✓ plan written: advance() records the marker as a transition-event field and a thread header attr, agent summaries only

### 2026-08-21 08:30:06Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied` fails as required
```
ents: [('transition', {'ticket': 'TICKET-001', 'stage': 'plan-validation', 'from': 'plan-validation', 'to': 'awaiting-approval', 'result': 'ok', 'counters': {}})]
E       assert ([('transition', {'ticket': 'TICKET-001', 'stage': 'plan-validation', 'from': 'plan-validation', 'to': 'awaiting-appro...tion · transition · to=awaiting-approval · result=ok\n\n**plan-validation -> awaiting-approval** (result: `ok`)\n\n\n') != ([('transition', {'ticket': 'TICKET-001', 'stage': 'plan-validation', 'from': 'plan-validation', 'to': 'awaiting-appro...tion · transition · to=awaiting-approval · result=ok\n\n**plan-validation -> awaiting-approval** (result: `ok`)\n\n\n')

tests/test_dispatch.py:541: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> awaiting-approval {}
  TICKET-001: -> awaiting-approval {}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied` fails on base `main` too -- the bug is not already fixed upstream
```
tion · transition · to=awaiting-approval · result=ok\n\n**plan-validation -> awaiting-approval** (result: `ok`)\n\n\n')

tests/test_dispatch.py:541: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> awaiting-approval {}
  TICKET-001: -> awaiting-approval {}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ay553ts0/base
      Built pipeline @ file:///tmp/pipeline-base-ay553ts0/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 12ms

```

### 2026-08-21 08:32:04Z · plan-validation · note

**Verdict: PASS.** Eight items, eight passes. Findings per item below.

**Root cause.** The rule at `pipeline/stages/_common.md:60` is asserted to every
stage and observed by nothing. `advance()`
(`pipeline/daemon/supervisor.py:73-103`) receives the agent's `summary`
verbatim, writes it into `## Thread` at line 92 and emits `transition` at line
76 without inspecting the text. The test fails because no code reads the
summary, not because a reader is wrong. The plan puts the reader in `advance()`
-- the one funnel every verdict passes through -- so it fixes the cause. It does
not target the test: the committed test is design-neutral (event, thread, or
both), and the plan records in both places.

**Decision conflict.** DEC-011 binds and the plan complies. I read
`.project/decisions/DEC-011.md` and its text is the plan's quote verbatim:
"Adding a `kind` or a field inside `data` is additive and fine; changing a
column, a kind's name, or the meaning of an existing field is not". `Store.emit`
(`pipeline/daemon/store.py:83-87`) takes `**data` and `json.dumps` it, so
`marker` lands inside the `data` blob and touches no column. DEC-016 binds the
thread and the plan complies: it passes attrs to the existing `Ticket.append()`
call and adds no fourth heading scan. DEC-017, DEC-019, DEC-020 and DEC-021 do
not touch this code. A grep for `superseded-by` over
`/home/chezzijr/proj/claude-setup/.project/decisions/` returns nothing, so all
seven records are active.

**Scope discipline.** Every step traces to a criterion. Steps 1-2 write the two
new tests named in criteria 2-5. Steps 4-7 are the implementation criterion 1
requires. Steps 3, 8 and 9 are the runs criteria 1 and 6 name. Step 10 commits
the two files in `files_declared`. No step touches a third file.

**Falsifiable criteria.** Each criterion names an input and a value an
implementation can get wrong. `tight["marker"] is True` for the summary
`✓planned` fails against a reader matching the character plus a space.
`assert "marker" not in pickup` fails against a reader that records `False` for
dispatcher notes. `t.counters == {}` fails against a reader that charges a
counter. No criterion says "clean" or "correct".

**No research left.** Every step names a file, a symbol and a line, and each one
resolves. A grep for `advance(` in `pipeline/daemon/supervisor.py` returns
exactly the five call sites the plan lists: 460, 523, 574, 595, 715. I read 460,
523, 574 and 595: each is a dispatcher-owned note (`dispatcher pickup`, the
Tier A gate failure, the child's exit code, the re-gate) and each already passes
`emit` positionally, so appending `agent=False` parses. Line 715 is
`res.get("summary", "")`. The head of `advance()` is lines 73-77 and the
`t.append()` call is lines 92-93, as the plan states.

**Riskiest step.** Step 5: it changes the signature and the emit of the function
every ticket in the pipeline passes through, and the new parameter defaults to
`True`, so a future call site is judged whether or not its author thought about
it. `## Rollback` states the fallback and it holds. `_parse_header()`
(`pipeline/core/ticket.py:429`) parses each `k=v` past the kind into a dict, and
a grep for `.attrs` over `pipeline/` and `tests/` finds three hits, all in
`tests/`, none reading a `transition` entry. So a `marker=` attr left behind by
a revert is inert text, exactly as the plan says.

**Regression surface.** Two consumers could break on an added key: a test
comparing a whole event dict, and a query selecting `data` wholesale. Neither
exists. `tests/test_cli.py:195-196` reads `json.loads(dat)["to"]` and
`["result"]` by key. Every `transition` query in `pipeline/cli/metrics.py`
(lines 178, 202, 323) uses `json_extract(data,'$.<key>')`.
`tests/test_dispatch.py:367` and `:374` compare only kind names -- the second is
`assert seen == ["transition", "escalated"], seen`. `pipeline/tui/app.py:47`
uses `transition` as a member of `TREE_KINDS` and reads no field.
`pipeline/cli/main.py:95` emits its own `transition` for the human gates and
never calls `advance()`, so it is unaffected. Step 9's five files cover all of
them.

**Blast radius.** `feature`, two files, both declared:
`pipeline/daemon/supervisor.py` and `tests/test_dispatch.py`. One new constant,
one new function, one new parameter, four call sites given a keyword.
Proportionate to the class. No reclassification.

One defect found, non-blocking, and it sits in a verification step's expected
output rather than in the implementation. Step 3 predicts `KeyError: 'marker'`
first. The step-1 test executes all four `run()` calls before its first
assertion, and the fourth passes `agent=False`, so the first failure is
`TypeError: advance() got an unexpected keyword argument 'agent'`. The step
still fails as required, and both error strings the plan names are the ones the
implementer will see. `## Summary` records the correction.

Guard note, for whoever maintains the stage: the read-only allowlist rejected
`sed -n 60,110p <file>` ("sed -n: not an allowed subcommand") and rejected an
appending heredoc ("command does not parse as a shell command"). I read the
files with the Read tool and wrote this entry with the Edit tool instead. No
finding depended on the blocked commands.

### 2026-08-21 08:33:12Z · plan-validation · session · session=c85e0be6-32d5-4e9d-8a11-ac35acbc00f6

`plan-validation` ran as session `c85e0be6-32d5-4e9d-8a11-ac35acbc00f6`
- replay: `claude --resume c85e0be6-32d5-4e9d-8a11-ac35acbc00f6`
- log: `.project/logs/TICKET-022-plan-validation-c85e0be6.log`

### 2026-08-21 08:33:12Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan validated: eight items pass; call sites 460/523/574/595/715 and advance() lines 73-77, 92-93 all verified; one non-blocking correction to step 3's predicted error order

### 2026-08-21 08:41:02Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 08:44:54Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied` fails as required
```
ents: [('transition', {'ticket': 'TICKET-001', 'stage': 'plan-validation', 'from': 'plan-validation', 'to': 'awaiting-approval', 'result': 'ok', 'counters': {}})]
E       assert ([('transition', {'ticket': 'TICKET-001', 'stage': 'plan-validation', 'from': 'plan-validation', 'to': 'awaiting-appro...tion · transition · to=awaiting-approval · result=ok\n\n**plan-validation -> awaiting-approval** (result: `ok`)\n\n\n') != ([('transition', {'ticket': 'TICKET-001', 'stage': 'plan-validation', 'from': 'plan-validation', 'to': 'awaiting-appro...tion · transition · to=awaiting-approval · result=ok\n\n**plan-validation -> awaiting-approval** (result: `ok`)\n\n\n')

tests/test_dispatch.py:541: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> awaiting-approval {}
  TICKET-001: -> awaiting-approval {}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied` fails on base `main` too -- the bug is not already fixed upstream
```
tion · transition · to=awaiting-approval · result=ok\n\n**plan-validation -> awaiting-approval** (result: `ok`)\n\n\n')

tests/test_dispatch.py:541: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> awaiting-approval {}
  TICKET-001: -> awaiting-approval {}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ivho5gi5/base
      Built pipeline @ file:///tmp/pipeline-base-ivho5gi5/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```

### 2026-08-21 08:44:54Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 · implementing · todo

1. Add `test_the_marker_record_names_the_agents_summary_and_nothing_else` to
   `tests/test_dispatch.py` -- done.
2. Add `test_a_missing_marker_changes_no_transition_and_no_counter` to
   `tests/test_dispatch.py` -- done.
3. Run the two new tests, confirm the predicted failure before implementing --
   done.
4. Add `MARKER` and `has_marker()` above `advance()` in
   `pipeline/daemon/supervisor.py` -- done.
5. Rewrite the head of `advance()` to take `agent` and compute the record
   before `t.append()` copies the note -- done.
6. Pass the header attrs into the `t.append()` call -- done.
7. Pass `agent=False` at the four dispatcher-owned call sites (lines 486, 549,
   600, 621) -- done.
8. Run the three marker tests, confirm `3 passed` -- done.
9. Run the five-file regression set, confirm 0 failures -- done.
10. Commit `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py`
    together -- done.

### 2026-08-21 · implementing · note

Plan executed as written, including the one correction in `## Summary`: the
step-1 test's first failure was `TypeError: advance() got an unexpected
keyword argument 'agent'`, not `KeyError: 'marker'`, exactly as predicted.

Results:

- `uv run --group dev pytest -q tests/test_dispatch.py -k marker` -- `3
  passed, 20 deselected in 0.05s`.
- `uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py
  tests/test_daemon.py tests/test_metrics.py tests/test_ticket.py` -- `93
  passed in 4.26s`.
- `uv run --group dev pytest -q
  "tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied"`
  -- `1 passed in 0.04s`, the ticket's failing test now passes.

`git status --short` before staging showed only the two declared files
changed. Committed as `436e483`: "feat: record whether a stage's summary
carried the prose marker", 2 files changed, 79 insertions(+), 7 deletions(-).

No plan deviation. No file touched outside `files_declared`.

### 2026-08-21 08:46:58Z · implementing · session · session=0bf95789-9806-4ee7-addc-9573eaf82f75

`implementing` ran as session `0bf95789-9806-4ee7-addc-9573eaf82f75`
- replay: `claude --resume 0bf95789-9806-4ee7-addc-9573eaf82f75`
- log: `.project/logs/TICKET-022-implementing-0bf95789.log`

### 2026-08-21 08:46:58Z · implementing · transition · to=review · result=ok

**implementing -> review** (result: `ok`)

✓ plan executed: advance() records the marker as an event field and a thread attr, agent summaries only; 3 marker tests pass, 93 in the five-file regression set pass, committed as 436e483

### 2026-08-21 08:49:06Z · review · finding · severity=blocking

**Verdict: FAIL.** One blocking finding, two non-blocking. Delta reviewed:
`git diff main...HEAD`, commits `9ce9675` and `436e483`, two files,
110 insertions, 7 deletions. No earlier review entry exists, so this is
pass 1 and the whole branch is the delta.

Every acceptance criterion passes. I ran both commands the ticket names:

    uv run --group dev pytest -q tests/test_dispatch.py -k marker
    3 passed, 20 deselected in 0.04s

    uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py tests/test_daemon.py tests/test_metrics.py tests/test_ticket.py
    93 passed in 4.15s

The five `advance()` call sites are 486, 549, 600, 621 and 742. The first
four pass `agent=False`; 742 in `_finish()` takes the default. That matches
the plan.

1. **blocking.** `has_marker()` raises on a summary that is not a string, and
   `_finish()` reaches it with an unvalidated agent value. `summary` is not in
   `CLAIMS`, so `apply_claims()` never touches it and `validate_meta()` never
   sees it. A sidecar whose `summary:` key has no value parses to `None`:

       uv run --group dev python -c 'import yaml; from pipeline.daemon.supervisor import has_marker; d=yaml.safe_load("result: ok\nsummary:\n"); print("parsed:",d); print(has_marker(d.get("summary","")))'

       File "pipeline/daemon/supervisor.py", line 87, in has_marker
           return note.lstrip().startswith(MARKER)
                  ^^^^^^^^^^^
       AttributeError: 'NoneType' object has no attribute 'lstrip'
       parsed: {'result': 'ok', 'summary': None}

   `summary: 2026-08-21` reaches it as a `datetime.date` by the same route.

   This is a regression the delta introduced. Before `436e483`, `note` was
   only interpolated into an f-string, so `None` rendered as `None` in the
   thread and the ticket advanced.

   The cost is a lost stage run, not a wrong marker. `_finish()` calls
   `drop_result(project, tid)` at line 739, one line before `advance()` at 742,
   so the sidecar is already deleted when `has_marker()` raises. `reap()`
   catches the exception at line 771 and prints `finish failed
   (AttributeError: ...)`. `advance()` never runs, the lease is held until it
   expires, `lease_expiries` is charged, and the stage respawns with its
   verdict gone. `log_tail()`'s docstring (line 584) records this exact failure
   from a previous occurrence: "raised `UnicodeDecodeError` inside `finish()`,
   `reap()` caught and printed it, and `advance()` never ran -- so the lease
   `child()` took was held until it expired."

   Fix: coerce in `has_marker()` -- `str(note or "").lstrip().startswith(MARKER)`
   -- and add the `summary: None` case to
   `test_the_marker_record_names_the_agents_summary_and_nothing_else`.

2. **non-blocking.** `test_a_missing_marker_changes_no_transition_and_no_counter`
   passed before the implementation existed. The plan states this and calls it
   a tripwire, not a reproduction, so it is deliberate. It fails only if
   someone turns the marker into a gate, which is what it is for.

3. **non-blocking, for whoever maintains the review stage.** The read-only
   allowlist rejected `sed -n 1,200p <file>` ("sed -n: not an allowed
   subcommand") and rejected a multi-line `python -c` ("command does not parse
   as a shell command"). I read files with the Read tool and reran the check as
   a single-line `python -c`, which the guard allows. No finding depended on a
   blocked command.

Checks that found nothing, recorded so pass 2 does not repeat them:

- No consumer breaks on the added `data.marker` key. Every `transition` reader
  in `tests/` and `pipeline/` selects by key, never by whole-dict equality:
  `tests/test_cli.py:196`, `tests/test_dispatch.py:374`
  (`assert seen == ["transition", "escalated"]`, kind names only),
  `tests/test_daemon.py:109`, `pipeline/tui/app.py`. DEC-011 permits the
  addition.
- `Ticket.append(**attrs)` renders `marker=yes|no` into the header and
  `_parse_header()` (`pipeline/core/ticket.py:429`) reads it back as a string
  into a dict nothing consumes. No parse hazard.
- The signature change is backward compatible: `agent` is keyword-only in
  practice with a default, and the two existing external callers
  (`tests/test_ticket.py:291`, `tests/test_daemon.py:104`) still pass.
- `emit()` has no `marker` key to collide with.
- Reading the marker before `t.append()` is correct as written: line 105
  computes it, line 118 copies the note into the thread.

### 2026-08-21 08:49:57Z · review · session · session=a0fe70cd-7182-42b5-850d-0c63891ef0e1

`review` ran as session `a0fe70cd-7182-42b5-850d-0c63891ef0e1`
- replay: `claude --resume a0fe70cd-7182-42b5-850d-0c63891ef0e1`
- log: `.project/logs/TICKET-022-review-a0fe70cd.log`

### 2026-08-21 08:49:57Z · review · transition · to=implementing · result=fail

**review -> implementing** (result: `fail`)

✓ review pass 1: all criteria pass, but has_marker() raises AttributeError on a non-string summary and _finish() loses the verdict

### 2026-08-21 · implementing · todo

1. Add the `summary: None` case to
   `test_the_marker_record_names_the_agents_summary_and_nothing_else` -- done.
2. Confirm it fails with `AttributeError: 'NoneType' object has no attribute
   'lstrip'` before fixing -- done.
3. Fix `has_marker()` to coerce the note --
   `str(note or "").lstrip().startswith(MARKER)` -- done.
4. Run the three marker tests, confirm `3 passed` -- done.
5. Run the five-file regression set, confirm 0 failures -- done.
6. Commit both files -- done.

### 2026-08-21 · implementing · note

Fixed the review's one blocking finding. `has_marker()`
(`pipeline/daemon/supervisor.py`) now reads
`str(note or "").lstrip().startswith(MARKER)`, so a sidecar `summary: None`
(or any non-string value YAML hands back) records `marker: False` instead of
raising `AttributeError`. Added the `summary: None` case to
`test_the_marker_record_names_the_agents_summary_and_nothing_else`, exactly as
the review's fix named.

Confirmed RED first: before the fix, the new test case raised
`AttributeError: 'NoneType' object has no attribute 'lstrip'` at
`pipeline/daemon/supervisor.py:87`, inside `has_marker()`, matching the
review's finding verbatim.

Results after the fix:

- `uv run --group dev pytest -q tests/test_dispatch.py -k marker` --
  `3 passed, 20 deselected in 0.05s`.
- `uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py
  tests/test_daemon.py tests/test_metrics.py tests/test_ticket.py` --
  `93 passed in 4.16s`.
- `uv run --group dev pytest -q
  "tests/test_dispatch.py::test_the_summary_marker_is_recorded_when_a_verdict_is_applied"`
  -- `1 passed in 0.03s`.

`git status --short` before staging showed only the two declared files
changed. Committed as `0f16551`: "fix: has_marker() coerce non-string summary
before checking marker", 2 files changed, 3 insertions(+), 1 deletion(-).

The review's two non-blocking findings are unchanged by this fix and are not
mine to act on.

### 2026-08-21 08:51:13Z · implementing · session · session=453ba999-d72d-4d4e-a512-f7187d8abbe5

`implementing` ran as session `453ba999-d72d-4d4e-a512-f7187d8abbe5`
- replay: `claude --resume 453ba999-d72d-4d4e-a512-f7187d8abbe5`
- log: `.project/logs/TICKET-022-implementing-453ba999.log`

### 2026-08-21 08:51:13Z · implementing · transition · to=review · result=ok

**implementing -> review** (result: `ok`)

✓ fixed review's blocking finding; has_marker() coerces non-string summaries; 3 marker tests + 93-file regression + named test pass; committed as 0f16551

### 2026-08-21 · review · note

**Verdict: PASS.** No blocking findings. Delta reviewed: commit `0f16551`
only, the single commit since the pass-1 review entry (08:49:57Z). Two files,
3 insertions, 1 deletion.

Pass 1's blocking finding is resolved. `has_marker()`
(`pipeline/daemon/supervisor.py:87`) now reads
`str(note or "").lstrip().startswith(MARKER)`. I reran the reproduction from
that finding and it no longer raises:

    parsed: {'result': 'ok', 'summary': None}
    none: False date: False tight: True bare: False

Both values the finding named -- `None` from a `summary:` key with no value,
and a `datetime.date` from `summary: 2026-08-21` -- record `marker: False`
instead of raising, so `_finish()` reaches `advance()` and the verdict is not
lost. `✓x` still records `True`, so the coercion did not undo the
character-not-character-plus-space rule.

Tests, rerun by me:

    uv run --group dev pytest -q tests/test_dispatch.py -k marker
    3 passed, 20 deselected in 0.04s

    uv run --group dev pytest -q tests/test_dispatch.py tests/test_cli.py tests/test_daemon.py tests/test_metrics.py tests/test_ticket.py
    93 passed in 4.08s

`git status --short` is empty. `git diff --stat main...HEAD` lists only the two
declared files, 112 insertions and 7 deletions.

The new test case is not vacuous: `run(None)` calls `advance()` with
`agent=True`, so the old `note.lstrip()` raises `AttributeError` inside
`has_marker()` before any assertion runs.

Findings:

1. **non-blocking.** `has_marker()`'s signature still says `note: str`, and its
   docstring explains only the space rule, not the coercion. A reader who
   trusts the annotation can "simplify" `str(note or "")` back to
   `note.lstrip()` and restore the lost-stage-run bug. One clause in the
   docstring naming `summary: None` would pin it. The test case added in
   `0f16551` fails if anyone does, which is why this is not blocking.
2. **non-blocking, carried from pass 1, unchanged.**
   `test_a_missing_marker_changes_no_transition_and_no_counter` passed before
   the implementation existed. The plan declares it a tripwire, not a
   reproduction.
3. **non-blocking, for whoever maintains the review stage.** The read-only
   allowlist rejected three commands: `cd <dir> && ...` ("`cd` is not on the
   read-only allowlist"), `sed -n 1,200p <file>` ("sed -n: not an allowed
   subcommand"), and a heredoc append to the ticket ("command does not parse as
   a shell command"). It also rejected a `python -c` whose string literal
   contained `-` followed by `>` ("shell redirection into a file"). Pass 1
   reported the first two. I used the Read and Edit tools instead and rewrote
   the `python -c` without the arrow. No finding depended on a blocked command.

Checks that found nothing:

- Plan drift: the delta departs from plan step 4, which wrote `note.lstrip()`.
  Pass 1's blocking finding directed the change and `## Summary` records it.
  Deliberate, not drift.
- `advance()` touches `note` in exactly two places: `has_marker(note)` at line
  99 and the f-string at line 118. A `None` note renders as the text `None` in
  the thread, which is what it did before `436e483`. No new behaviour.
- `summary` reaches `advance()` from one call site only, line 742
  (`res.get("summary", "")`). `grep -n summary pipeline/daemon/supervisor.py`
  reports lines 73, 80, 92, 742, 916 and no other consumer.
- The five-file regression set covers the `transition` event readers and the
  ticket thread parser. 93 passed.

### 2026-08-21 08:53:42Z · review · session · session=3decb2c0-3c22-47b1-9714-b6ffdbd592f8

`review` ran as session `3decb2c0-3c22-47b1-9714-b6ffdbd592f8`
- replay: `claude --resume 3decb2c0-3c22-47b1-9714-b6ffdbd592f8`
- log: `.project/logs/TICKET-022-review-3decb2c0.log`

### 2026-08-21 08:53:42Z · review · transition · to=holistic-review · result=ok

**review -> holistic-review** (result: `ok`)

✓ review pass 2: 0f16551 resolves the blocking AttributeError; has_marker() returns False for None and date, True for ✓x; 3 marker tests and 93 regression tests pass; 3 non-blocking findings

### 2026-08-21 · holistic-review · note

PASS. The three commits (`9ce9675`, `436e483`, `0f16551`) sum to what `## Plan`
described. No drift, no partial undo, nothing outside the acceptance criteria.

Scope of the review: `git diff main...HEAD`, 2 files, 112 insertions, 7
deletions -- `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py`, the
two declared files. `git status --short` is empty.

1. **The sum does what the plan said.** Plan steps 4-7 land as written:
   `MARKER` and `has_marker()` sit immediately above `advance()`; `advance()`
   takes `agent: bool = True`; `marker` is computed after `transition()` and
   before `emit`, so it reads the note before `t.append()` copies it; the event
   carries `**ev` and the thread entry carries `**attrs`.
2. **The five call sites are consistent.** `grep -rn "advance(" pipeline/`
   returns exactly five calls: lines 486, 549, 600 and 621 pass `agent=False`,
   and line 742 (`_finish()`, `res.get("summary", "")`) takes the default. That
   is the plan's split, and no sixth call site exists.
3. **The later fix does not undo the earlier one.** `436e483` wrote
   `note.lstrip().startswith(MARKER)`; `0f16551` widened it to
   `str(note or "").lstrip().startswith(MARKER)`. The second commit changes
   only the coercion. The marker semantics, the `agent` split and both record
   sites are untouched by it.
4. **Error handling did not drift.** `has_marker()` is the only new branch and
   it is total: `None`, a `datetime.date` and `""` all return `False` instead
   of raising. `advance()` gained no `try` and no new failure mode, so
   `reap()`'s existing catch is unchanged.
5. **Nothing landed that no acceptance criterion asked for.** The only addition
   past the plan text is one line in
   `test_the_marker_record_names_the_agents_summary_and_nothing_else`
   (`none_case, _ = run(None)` and its assert), the regression test for pass
   1's blocking finding. No metrics view, no schema change, no
   `pipeline/cli/main.py` edit -- `## Decisions` states each omission
   deliberately.

I reran both commands the ticket names. `uv run --group dev pytest -q
tests/test_dispatch.py -k marker` reports `3 passed, 20 deselected in 0.04s`.
The five-file regression set reports `93 passed in 4.11s`.

Carried forward, not blocking, already recorded by review pass 2:
`has_marker()`'s annotation reads `note: str` while the body coerces with
`str(note or "")`, and the docstring does not mention the coercion. A future
reader could revert the coercion and restore the `AttributeError`.

### 2026-08-21 08:55:18Z · holistic-review · session · session=908b4f4d-5456-4958-93e7-b2b3adf4f5fc

`holistic-review` ran as session `908b4f4d-5456-4958-93e7-b2b3adf4f5fc`
- replay: `claude --resume 908b4f4d-5456-4958-93e7-b2b3adf4f5fc`
- log: `.project/logs/TICKET-022-holistic-review-908b4f4d.log`

### 2026-08-21 08:55:18Z · holistic-review · transition · to=verifying · result=ok

**holistic-review -> verifying** (result: `ok`)

✓ holistic review passed: 3 commits sum to the plan, 0f16551 undoes nothing, all 5 advance() call sites consistent, 3 marker + 93 regression tests pass

### 2026-08-21 08:55:27Z · verifying · transition · to=merging · result=ok

**verifying -> merging** (result: `ok`)

regression suite exit 0
```
...HEAD
ok  allow [always] cargo build --release
ok  BLOCK [readonly] sed -i s/a/b/ x.py
ok  BLOCK [readonly] echo hi > file.txt
ok  BLOCK [readonly] git commit -am wip
ok  BLOCK [readonly] cp a b
ok  BLOCK [readonly] pip install requests
ok  BLOCK [readonly] mv a b
ok  BLOCK [readonly] python3 -c "open('/tmp/x','a').write(1)"
ok  BLOCK [readonly] git -C . commit -am wip
ok  BLOCK [readonly] pytest 2>out
ok  BLOCK [readonly] pytest >> log.txt
ok  BLOCK [readonly] git worktree add /tmp/x main
ok  BLOCK [readonly] python3 setup.py install
ok  BLOCK [readonly] tee /tmp/x
ok  BLOCK [readonly] curl https://example.com -o /tmp/x
ok  BLOCK [readonly] make install
ok  BLOCK [readonly] cargo run
ok  BLOCK [readonly] npm install
ok  BLOCK [readonly] echo $(whoami)
ok  allow [readonly] pytest -x
ok  allow [readonly] git diff main...HEAD
ok  allow [readonly] grep -rn foo .
ok  allow [readonly] git log --oneline
ok  allow [readonly] cat thing.py
ok  allow [readonly] python3 -m pytest --deselect x
ok  allow [readonly] ls -la
ok  allow [readonly] git show HEAD
ok  allow [readonly] git blame thing.py
ok  allow [readonly] rg evict src/
ok  allow [readonly] pytest -x 2>&1
ok  allow [readonly] find . -name '*.py'
ok  allow [readonly] cargo test
ok  allow [readonly] go test ./...
ok  allow [readonly] git status --porcelain
ok  allow [readonly] wc -l thing.py
ok  allow [readonly] python3 -m unittest
ok  allow [readonly] git diff main...HEAD | head -50
ok  end-to-end exit codes

guard: all passed

```

### 2026-08-21 08:55:28Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/022


Merge made by the 'ort' strategy.
 pipeline/harnesses/claude-code.toml | 13 +++++++++++--
 pipeline/stages/holistic-review.md  |  3 +++
 pipeline/stages/implementing.md     |  3 +++
 pipeline/stages/plan-validation.md  |  3 +++
 pipeline/stages/planning.md         |  3 +++
 pipeline/stages/review.md           |  3 +++
 pipeline/stages/triage.md           |  2 ++
 tests/test_harness.py               | 17 +++++++++++++++++
 tests/test_stages.py                | 17 +++++++++++++++++
 9 files changed, 62 insertions(+), 2 deletions(-)
Updating e74dbaa..5c1483e
Fast-forward
 pipeline/daemon/supervisor.py | 41 +++++++++++++++++++----
 tests/test_dispatch.py        | 78 +++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 112 insertions(+), 7 deletions(-)

```

### 2026-08-21 08:55:28Z · merging · decision

decision recorded as `DEC-022`
