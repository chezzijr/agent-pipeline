---
id: TICKET-093
stage: done
class: feature
branch: ticket/093
test_file: tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md
files_declared:
- pipeline/cli/metrics.py
- tests/test_metrics.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 9
  plan_files: 2
  no_result: 0
  structural_gate_failures: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 7543f655-d8f2-4cc4-8a51-009cdf27c6b1
  log: .project/logs/TICKET-093-review-7543f655.log
  cost_usd: 0.8580725000000001
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified: collect() at metrics.py:395-408 and no test
  pins its key set, so adding ''scope'' is safe; render()''s gate_failures branch
  at :490-491 with the else arm left alone; _EV binds :since/:project so the header
  counts the same window. Project count comes from the log, not the registry -- the
  right number.'
approved_at: '2026-08-29T04:54:27.674979+00:00'
---

## Summary

`pipeline metrics` does not name its project scope and does not point at `.extra.md`

Two operator-facing gaps in one renderer, `pipeline/cli/metrics.py`.

1. `render()` (`pipeline/cli/metrics.py:437`) prints no header saying which
project it counted. With no `--project` it sums every project in the event log.
An operator with two registered repos read one combined table as one project's
numbers.

2. View 4, "gate failure reasons" (`pipeline/cli/metrics.py:300`), never names
`.project/stages/<stage>.extra.md`, the project rule file that fixes a finding
that keeps repeating.

Triage reproduced both with
`tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md`
(commit `efad79d`): the rendered text contains neither `/proj` nor `.extra.md`.

Planning wrote the plan. `collect()` gains a `"scope"` key holding the project
filter and a count of distinct projects in the log; `render()` prints
`project: <path>` or `project: all (N in this log)` above the stage table, and
one `.extra.md` pointer under view 4's rows when view 4 has any row. Two files
change: `pipeline/cli/metrics.py` and `tests/test_metrics.py`. Nine steps, in
`## Plan`. Design rationale is in `## Decisions`; read it before changing how
the scope reaches `render()`.

The Tier A gate rejected the first plan on one finding, in `## Reproduction`,
not in `## Plan`. The `expect:` line carried the whole rendered table with
literal newline escapes; pytest truncates that repr with `...`, so it matched
no run. Planning trimmed `expect:` to the part before the first escape and
left every plan step, decision and acceptance criterion unchanged. The second
Tier A gate passed.

Plan-validation passed the plan on all eight items; the per-item reasoning is
the last `## Thread` entry. Implementation notes it left: the two `grep`
acceptance criteria are shape-only, so criterion 1 (the repro test) is what
actually proves the `.extra.md` pointer; every render assertion in
`tests/test_metrics.py` is a substring, so the new header line breaks none;
and plan-validation ran no command, reading `pipeline/cli/metrics.py` and
`tests/test_metrics.py` instead.

Outside this ticket, noted and not planned: the metrics header names no
`--since` window.

Implementing executed the plan in nine steps, TDD throughout, two commits
(`f2afa7e`, `581c754`). Both new/changed asserts were watched RED for the
expected reason before the fix, then GREEN after. Both the repro test and all
five acceptance criteria pass; `tests/test_metrics.py`, `tests/test_dispatch.py`
and `tests/test_cli.py` together report 121 passed, 0 failed.

Review passed the delta with no blocking finding, on the first pass. It re-ran
all five acceptance criteria: 121 passed, the two named tests pass alone, both
greps exit `0`, and the rendered header reads `project: /proj` when filtered and
`project: all (1 in this log) -- filter with --project PATH|name` when not. The
delta is three commits and touches only the two declared files. One nit, not
blocking: the continuation lines of the two new `out.append(f"...")` calls sit
one column left of the opening paren.

## Reproduction

`tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md`

Command: `uv run --group dev pytest -q tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md`

`metrics.collect(conn, project="/proj")` then `metrics.render(data)` on the
canned log's output contains no `/proj` and no `.extra.md`, though view 4 has
two rows. `render(data)` takes only `data`; the project string never reaches
it, and `gate_failure_reasons()`'s rows carry no pointer to `.extra.md`.

expect: assert '/proj' in 'stage             runs escalated   rate   p50 cost  turns  out tok   think  cache rd

## Digest

Files touched: `pipeline/cli/metrics.py` (the renderer and the assembled view),
`tests/test_metrics.py` (the repro test plus one new test).

Key functions: `collect()` (`pipeline/cli/metrics.py:395`) assembles the dict
`render()` prints; `render()` (`pipeline/cli/metrics.py:437`) takes only `data`;
`gate_failure_reasons()` (`pipeline/cli/metrics.py:300`) is view 4;
`_EV` (`pipeline/cli/metrics.py:102`) is the `WITH ev AS (...)` prefix that binds
`:since` and `:project` for every query.

Entry points: `cmd_metrics()` (`pipeline/cli/main.py:568`) calls
`metrics.collect(conn, since, _metrics_project(args))` then prints
`metrics.render(data)` or `json.dumps(data)`. `pipeline/tui/app.py:721` shells out
to `pipeline metrics | less -R`, so it renders through the same CLI and needs no
change.

Gotchas:
1. The repro test calls `metrics.render(data)` with one argument, so the project
   string must reach `render()` inside `data`, not as a new parameter.
2. `render()`'s output is also `--json`'s dict, so a new `data` key shows up in
   `pipeline metrics --json` too. Nothing asserts a fixed key set.
3. `gate_failure_reasons()` rows carry `finding` and `n` only, no stage, so the
   `.extra.md` pointer names `<stage>` as a placeholder.
4. `stage_extra()` (`pipeline/core/config.py:419`) reads
   `.project/stages/<stage>.extra.md` from HEAD, not from disk, so the pointer
   must tell the operator to commit the file.
5. `tests/test_metrics.py::_at` stamps `project="/proj"` by default, so a second
   project in a fixture log needs `project=` passed explicitly.
6. Repro test output today ends `1 failed in 0.03s`. `## Reproduction`'s
   `expect:` stops at `cache rd`, before pytest's first newline escape: pytest
   truncates the long repr with `...`, so the whole rendered table never
   appears on one output line. Do not paste the table back into `expect:`.

## Decisions checked

DEC-038 (still active) fences `.project/stages/` and states an `.extra.md` is
prose appended after the packaged rules -- it is the file this ticket points an
operator at, and this plan only adds a pointer to it. DEC-011 (still active)
froze the event log schema this renderer queries; no schema change here.
DEC-029 and DEC-022 mention `pipeline/cli/metrics.py` but constrain the machine
and marker counting, not rendering. Grep terms used against
`.project/decisions/`: `metrics`, `render(`, `extra.md`, `collect(`, `project
scope`, `registry`.

## Plan

1. Run `uv run --group dev pytest -q tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md` and confirm it fails on `assert '/proj' in ...` in `tests/test_metrics.py`; this is the starting state, no edit yet.
2. Add to `tests/test_metrics.py` a test `test_render_says_all_and_counts_the_projects_it_summed()`: build a log with `_at(s, BASE, "stage_end", ticket="TICKET-100", stage="planning", result="ok", next_stage="review", exit_code=0)` and a second identical event with `project="/other"`, then assert `"project: all (2 in this log)" in metrics.render(metrics.collect(conn))`. Run it and watch it fail with `AssertionError`.
3. In `pipeline/cli/metrics.py`, add `def project_scope(conn, since=0.0, project=None) -> dict` just above `collect()`, returning `{"project": project, "projects": conn.execute(_EV + "SELECT COUNT(DISTINCT project) FROM ev", {"since": since, "project": project}).fetchone()[0]}`, with a comment saying it is a header over the same window, not a seventh view, and that the count comes from the log rather than `registry.projects()` so a registered project with no events cannot inflate it.
4. In `pipeline/cli/metrics.py`, add `"scope": project_scope(conn, since, project),` to the dict `collect()` returns, so `pipeline metrics --json` carries it too.
5. In `pipeline/cli/metrics.py`, make `render()` emit the scope header before the stage table: read `scope = data["scope"]`, append `f"project: {scope['project']}"` when `scope["project"]` is set, else `f"project: all ({scope['projects']} in this log) -- filter with --project PATH|name"`, then append `""` before the existing `out.append(f"{'stage':<17} ...")` header line.
6. Run `uv run --group dev pytest -q tests/test_metrics.py` and confirm the step 2 test passes and the repro test now fails on its second assert, `assert '.extra.md' in text`; commit `pipeline/cli/metrics.py` and `tests/test_metrics.py` as `fix(TICKET-093): name the project scope in metrics render()`.
7. In `pipeline/cli/metrics.py`, inside `render()`'s `if data["gate_failures"]:` branch, after the `for f in data["gate_failures"]:` loop, append one line: `"  a finding that repeats is a missing project rule: pin it in .project/stages/<stage>.extra.md (read from HEAD -- commit it)"`; leave the `else:` branch ("no FAIL gate events in this window") unchanged so an empty view 4 prints no pointer.
8. Run `uv run --group dev pytest -q tests/test_metrics.py` and confirm every test passes, including the repro test named in `## Reproduction`; commit `pipeline/cli/metrics.py` as `fix(TICKET-093): point a repeated gate finding at .project/stages/<stage>.extra.md`.
9. Run `uv run --group dev pytest -q tests/test_metrics.py tests/test_dispatch.py tests/test_cli.py` and confirm no failure other than any that already failed on the base commit; these three are the files that touch `pipeline/cli/metrics.py` or run `pipeline metrics`.

## Acceptance criteria

- `tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md`
  passes.
- `tests/test_metrics.py::test_render_says_all_and_counts_the_projects_it_summed`
  passes: unfiltered `render()` output contains `project: all (2 in this log)`
  for a log holding events from `/proj` and `/other`.
- `uv run --group dev pytest -q tests/test_metrics.py tests/test_dispatch.py tests/test_cli.py`
  reports no failure other than one already failing at commit `efad79d`.
- `grep -n 'extra.md' pipeline/cli/metrics.py` exits `0`.
- `grep -n 'scope' pipeline/cli/metrics.py` exits `0`, and `collect()` returns a
  `"scope"` key, so `pipeline metrics --json` carries the project filter it used.

## Decisions

**`render()` learns its project scope through `data["scope"]`, never through a
second parameter.** The reproduction test calls `metrics.render(data)` with one
argument, and `cmd_metrics()` (`pipeline/cli/main.py:568`) prints either
`render(data)` or `json.dumps(data)` from the same dict -- routing the scope
through `data` keeps the text and the JSON describing the same window. A future
change that adds a `render(data, project)` parameter reintroduces the split.

**The registered-project count comes from the event log, not from
`registry.projects()`.** `pipeline/cli/metrics.py` queries one SQLite file and
nothing else; reading the registry would make a pure view over the log depend on
`$XDG_CONFIG_HOME/pipeline/projects`, make the count non-deterministic under
test, and count a registered project whose events are not in the number
displayed. The header therefore says "in this log", which is what was actually
summed.

**The `.extra.md` pointer prints only when view 4 has a row.** An empty gate
table means no finding to pin, and a standing advice line under
"no FAIL gate events in this window" is noise. The pointer names HEAD because
`stage_extra()` (`pipeline/core/config.py:419`) reads the file from HEAD, so an
uncommitted `.extra.md` reaches no spawn.

## Rollback

Revert the two commits from steps 6 and 8 (`git revert <sha>` each, newest
first). Only `pipeline/cli/metrics.py` and `tests/test_metrics.py` change, and
nothing else reads the new `data["scope"]` key, so reverting restores the
previous rendering exactly. No schema, no config, no stage prompt is touched.

## Thread

### 2026-08-29 03:52:45Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 · triage · result=ok

Reproduced both gaps with one test:
`tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md`.
`metrics.collect(conn, project="/proj")` then `render(data)` produces text
containing neither `/proj` nor `.extra.md`, confirmed by running the test
(fails on `assert '/proj' in text`). Committed as `efad79d`.

Not a `chore`: fixing this needs a design choice on how the resolved project
string reaches `render()` (new parameter vs. a key in `data`) and where in
view 4's loop the `.extra.md` line belongs. Leaving both to planning.

### 2026-08-29 04:25:09Z · triage · session · session=4fc37ca1-56a5-471a-b97d-b1e4c0c3abff

`triage` ran as session `4fc37ca1-56a5-471a-b97d-b1e4c0c3abff`
- replay: `claude --resume 4fc37ca1-56a5-471a-b97d-b1e4c0c3abff`
- log: `.project/logs/TICKET-093-triage-4fc37ca1.log`
- cost: $0.38 of a $3 cap
- tokens: 5,303 out (257 thinking) · 40 in · 828,451 cache read · 39,632 cache write

### 2026-08-29 04:25:09Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced both gaps: render() has no project param and view 4 never mentions .extra.md

### 2026-08-29 · planning · result=ok

Plan written. Both gaps live in `pipeline/cli/metrics.py`; the ticket is one
scope, no split needed.

Design choice 1: the project string reaches `render()` through a new
`data["scope"]` key, not a second parameter. The reproduction test calls
`metrics.render(data)` with one argument, and `cmd_metrics()` prints either
`render(data)` or `json.dumps(data)` from that same dict.

Design choice 2: the unfiltered header counts distinct projects in the event
log (`SELECT COUNT(DISTINCT project) FROM ev`), not `registry.projects()`. It
reads `project: all (2 in this log) -- filter with --project PATH|name`. The
ticket's wording was "(2 registered)"; the log count is deterministic under
test and cannot name a project whose events are absent from the numbers shown.

Design choice 3: the `.extra.md` line lands after view 4's row loop, inside
the `if data["gate_failures"]:` branch only, and names HEAD because
`stage_extra()` (`pipeline/core/config.py:419`) reads that file from HEAD.

Confirmed the repro still fails at commit `efad79d`: `1 failed in 0.03s`, on
`assert '/proj' in ...`.

Outside this ticket, noted and not planned: the header names no `--since`
window, so a run with `--since 7d` still does not say which window it counted.

### 2026-08-29 04:31:23Z · planning · session · session=22032d86-5e1c-482e-8568-72586dbfc8d5

`planning` ran as session `22032d86-5e1c-482e-8568-72586dbfc8d5`
- replay: `claude --resume 22032d86-5e1c-482e-8568-72586dbfc8d5`
- log: `.project/logs/TICKET-093-planning-22032d86.log`
- cost: $1.70 of a $10 cap
- tokens: 18,663 out (6,802 thinking) · 48 in · 1,176,335 cache read · 64,684 cache write

### 2026-08-29 04:31:23Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: render() reads its scope from data['scope'], view 4 gains an .extra.md pointer

### 2026-08-29 04:38:59Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `## Reproduction` `expect:` cannot recur: it holds a literal backslash escape where the run's output holds a control character, and `tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md`'s output does not contain it either way -- trim it to the part before the escape. Got: "assert '/proj' in 'stage             runs escalated   rate   p50 cost  turns  out tok   think  cache rd\\nawaiting-approval    0         0      -          -      -        -       -         -\\nimplementing         0         0      -      $0.60      -        0       0         0\\nmerging              0         0      -          -      -        -       -         -\\nplan-validation      0         0      -          -      -        -       -         -\\nplanning             2         1    50%          -      -        -       -         -\\nreview               0         0      -      $0.15      -        0       0         0\\nverifying            0         0      -          -      -        -       -         -\\n\\nreview loops (tickets reaching done/rejected, or escalated via a bound): 2x1\\nmerged: 1 · cost/merged: $2.25\\nparked in gates: p50 42m00s · p90 42m00s (awaiting-approval 1)\\n\\ngate failures:\\n    2  section `## Rollback` missing or empty\\n    1  files_declared is empty\\nguard blocks:\\n  no data -- no stream events in this log at all (an interactive-only run emits none)'"

### 2026-08-29 04:39:00Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- `## Reproduction` `expect:` cannot recur: it holds a literal backslash escape where the run's output holds a control character, and `tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md`'s output does not contain it either way -- trim it to the part before the escape. Got: "assert '/proj' in 'stage             runs escalated   rate   p50 cost  turns  out tok   think  cache rd\\nawaiting-approval    0         0      -          -      -        -       -         -\\nimplementing         0         0      -      $0.60      -        0       0         0\\nmerging              0         0      -          -      -        -       -         -\\nplan-validation      0         0      -          -      -        -       -         -\\nplanning             2         1    50%          -      -        -       -         -\\nreview               0         0      -      $0.15      -        0       0         0\\nverifying            0         0      -          -      -        -       -         -\\n\\nreview loops (tickets reaching done/rejected, or escalated via a bound): 2x1\\nmerged: 1 · cost/merged: $2.25\\nparked in gates: p50 42m00s · p90 42m00s (awaiting-approval 1)\\n\\ngate failures:\\n    2  section `## Rollback` missing or empty\\n    1  files_declared is empty\\nguard blocks:\\n  no data -- no stream events in this log at all (an interactive-only run emits none)'"

### 2026-08-29 · planning · result=ok

Fixed the one finding the Tier A gate reported. It sat in `## Reproduction`,
not in `## Plan`: the `expect:` line held the whole rendered table with
literal newline escapes, and pytest truncates that repr with `...`, so it
matched no run.

`expect:` is now the part before the first escape:
`assert '/proj' in 'stage             runs escalated   rate   p50 cost  turns  out tok   think  cache rd`.
I ran the repro test and checked the trimmed string against its output: it
matches, it holds no escape, and it does not end with an ellipsis. The run
still ends `1 failed in 0.03s`.

Everything else is unchanged. The gate reported no finding against `## Plan`,
`## Digest`, `## Decisions checked`, `## Acceptance criteria` or `## Rollback`,
so all nine steps, both design decisions and all five criteria stand as
written. `## Digest` gotcha 6 now records why `expect:` stops at `cache rd`,
so a later stage does not paste the table back in.

Outside this ticket, still noted and not planned: the metrics header names no
`--since` window, so `pipeline metrics --since 7d` does not say which window
it counted.

### 2026-08-29 04:40:58Z · planning · session · session=41fde605-55a9-4284-846c-e5beeafca30a

`planning` ran as session `41fde605-55a9-4284-846c-e5beeafca30a`
- replay: `claude --resume 41fde605-55a9-4284-846c-e5beeafca30a`
- log: `.project/logs/TICKET-093-planning-41fde605.log`
- cost: $0.94 of a $10 cap
- tokens: 9,140 out (3,097 thinking) · 28 in · 518,091 cache read · 44,748 cache write

### 2026-08-29 04:40:58Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ trimmed the `## Reproduction` expect: line to the part before its first escape; plan unchanged

### 2026-08-29 04:44:00Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md` fails as required
```
     -        -       -         -
E             
E             review loops (tickets reaching done/rejected, or escalated via a bound): 2x1
E             merged: 1 · cost/merged: $2.25
E             parked in gates: p50 42m00s · p90 42m00s (awaiting-approval 1)
E             
E             gate failures:
E                 2  section `## Rollback` missing or empty
E                 1  files_declared is empty
E             guard blocks:
E               no data -- no stream events in this log at all (an interactive-only run emits none)
E           assert '/proj' in 'stage             runs escalated   rate   p50 cost  turns  out tok   think  cache rd\nawaiting-approval    0         ...eclared is empty\nguard blocks:\n  no data -- no stream events in this log at all (an interactive-only run emits none)'

tests/test_metrics.py:337: AssertionError
=========================== short test summary info ============================
FAILED tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md` fails on base `main` too -- the bug is not already fixed upstream
```
        assert '/proj' in 'stage             runs escalated   rate   p50 cost  turns  out tok   think  cache rd\nawaiting-approval    0         ...eclared is empty\nguard blocks:\n  no data -- no stream events in this log at all (an interactive-only run emits none)'

tests/test_metrics.py:337: AssertionError
=========================== short test summary info ============================
FAILED tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-96di8lkm/base
      Built pipeline @ file:///tmp/pipeline-base-96di8lkm/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 16ms

```

### 2026-08-29 · plan-validation · result=ok

**Tier B: pass on all eight items.**

1. Root cause: `collect()` (`metrics.py:395`) takes `project` and drops it from
   the dict it returns, so `render(data)` (`metrics.py:437`) cannot name the
   window; `gate_failure_reasons()` (`metrics.py:304`) selects `finding, n`
   only, so view 4's loop has no remediation to print. The plan fixes both
   causes, not the assertion.
2. Decisions: DEC-038 fences `.project/stages/` and describes `.extra.md`
   prose -- the plan only points at it. DEC-011 froze the schema; step 3 adds
   a `SELECT COUNT(DISTINCT project)` over `_EV`, no schema change. DEC-033
   and DEC-051 also name metrics; neither constrains rendering. No conflict.
3. Scope: nine steps, all traceable. Steps 3-5 -> criteria 2 and 5, step 7 ->
   criteria 1 and 4, steps 1/6/8/9 -> criterion 3.
4. Criteria: 1 and 2 are falsifiable -- a registry-sourced count or different
   header text fails criterion 2. The two `grep` criteria are shape-only, and
   criterion 1 already covers what they check.
5. No research left: every step names the file, the function and the literal
   string to append.
6. Riskiest step: 5, which changes `render()`'s output shape. Fallback: two
   commits (steps 6 and 8), each reverted alone per `## Rollback`.
7. Regression surface: `pipeline metrics --json` gains a `scope` key, and every
   render assertion in `tests/test_metrics.py` is a substring
   (`"planning" in text`, `"$2.25" in text`, `cost/merged: ~$`), so a leading
   header breaks none. `tests/test_dispatch.py:515-521` calls the views
   directly. Step 9 runs both files plus `tests/test_cli.py`.
8. Blast radius: `class: feature`, 2 files, 9 steps. Matches.

I ran no command: the guard blocks `sed` and I read the sources with the file
tool instead. Verified against source, not against a run.

### 2026-08-29 04:46:26Z · plan-validation · session · session=d1de2ba0-5350-4bc9-9acf-fb230940691e

`plan-validation` ran as session `d1de2ba0-5350-4bc9-9acf-fb230940691e`
- replay: `claude --resume d1de2ba0-5350-4bc9-9acf-fb230940691e`
- log: `.project/logs/TICKET-093-plan-validation-d1de2ba0.log`
- cost: $1.06 of a $3 cap
- tokens: 10,539 out (4,357 thinking) · 30 in · 603,894 cache read · 49,488 cache write

### 2026-08-29 04:46:26Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan validated: all eight items pass; scope reaches render() through data['scope'] and the .extra.md pointer prints only under view 4 rows

### 2026-08-29 04:54:27Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: collect() at metrics.py:395-408 and no test pins its key set, so adding 'scope' is safe; render()'s gate_failures branch at :490-491 with the else arm left alone; _EV binds :since/:project so the header counts the same window. Project count comes from the log, not the registry -- the right number.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: collect() at metrics.py:395-408 and no test pins its key set, so adding 'scope' is safe; render()'s gate_failures branch at :490-491 with the else arm left alone; _EV binds :since/:project so the header counts the same window. Project count comes from the log, not the registry -- the right number.**

### 2026-08-29 04:57:35Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md` fails as required
```
     -        -       -         -
E             
E             review loops (tickets reaching done/rejected, or escalated via a bound): 2x1
E             merged: 1 · cost/merged: $2.25
E             parked in gates: p50 42m00s · p90 42m00s (awaiting-approval 1)
E             
E             gate failures:
E                 2  section `## Rollback` missing or empty
E                 1  files_declared is empty
E             guard blocks:
E               no data -- no stream events in this log at all (an interactive-only run emits none)
E           assert '/proj' in 'stage             runs escalated   rate   p50 cost  turns  out tok   think  cache rd\nawaiting-approval    0         ...eclared is empty\nguard blocks:\n  no data -- no stream events in this log at all (an interactive-only run emits none)'

tests/test_metrics.py:337: AssertionError
=========================== short test summary info ============================
FAILED tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md` fails on base `main` too -- the bug is not already fixed upstream
```
        assert '/proj' in 'stage             runs escalated   rate   p50 cost  turns  out tok   think  cache rd\nawaiting-approval    0         ...eclared is empty\nguard blocks:\n  no data -- no stream events in this log at all (an interactive-only run emits none)'

tests/test_metrics.py:337: AssertionError
=========================== short test summary info ============================
FAILED tests/test_metrics.py::test_render_names_its_project_scope_and_points_a_gate_failure_at_extra_md
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-slez90g2/base
      Built pipeline @ file:///tmp/pipeline-base-slez90g2/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 04:57:35Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-29 · implementing · todo

**implementing todo list**

1. [x] confirm repro test fails on `/proj` assert (starting state)
2. [x] add `test_render_says_all_and_counts_the_projects_it_summed`, watch it fail
3. [x] add `project_scope()` above `collect()`
4. [x] add `"scope"` key to `collect()`'s return dict
5. [x] `render()` emits scope header before stage table
6. [x] run test_metrics.py, confirm step-2 test passes and repro fails on `.extra.md`; commit
7. [x] append `.extra.md` pointer line under view 4 when it has rows
8. [x] run test_metrics.py, confirm repro test passes; commit
9. [x] run test_metrics.py + test_dispatch.py + test_cli.py, confirm no new failure

### 2026-08-29 · implementing · result=ok

**implementing done**

All nine plan steps executed, TDD each time. `project_scope()`
(`pipeline/cli/metrics.py:395`) added; `collect()` gained `"scope"`; `render()`
prints `project: <path>` or `project: all (N in this log) -- filter with
--project PATH|name` above the stage table, and view 4 gains the
`.extra.md` pointer line only when it has rows (its `else` branch untouched).

Two commits: `f2afa7e` (scope header) and `581c754` (`.extra.md` pointer).

Verified:
- `tests/test_metrics.py` alone: 13 passed.
- `tests/test_metrics.py tests/test_dispatch.py tests/test_cli.py`: 121 passed, 0 failed.
- `grep -n 'extra.md' pipeline/cli/metrics.py` and `grep -n 'scope' pipeline/cli/metrics.py`: both exit 0.

No deviation from the plan. No files touched beyond `pipeline/cli/metrics.py`
and `tests/test_metrics.py`.

### 2026-08-29 04:59:21Z · implementing · session · session=7ad57b00-49b5-43d5-a980-f050a1a72900

`implementing` ran as session `7ad57b00-49b5-43d5-a980-f050a1a72900`
- replay: `claude --resume 7ad57b00-49b5-43d5-a980-f050a1a72900`
- log: `.project/logs/TICKET-093-implementing-7ad57b00.log`
- cost: $0.53 of a $8 cap
- tokens: 6,732 out (46 thinking) · 58 in · 1,385,252 cache read · 46,136 cache write

### 2026-08-29 04:59:21Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented plan: render() prints project scope header and .extra.md pointer under view 4; repro test and new scope test both pass

### 2026-08-29 · review · result=ok

**review: no blocking findings**

Reviewed the whole delta, `main...HEAD`, three commits (`e3dbe93`, `f2afa7e`,
`581c754`). First review pass; `## Thread` holds no earlier review entry.
`git diff --name-only main...HEAD` lists only `pipeline/cli/metrics.py` and
`tests/test_metrics.py`; `git status --porcelain` is empty.

Verified against the acceptance criteria:
1. `uv run --group dev pytest -q tests/test_metrics.py tests/test_dispatch.py tests/test_cli.py` prints `121 passed in 17.70s`.
2. The two named tests pass alone: `2 passed in 0.02s`.
3. `grep -n 'extra.md' pipeline/cli/metrics.py` exits `0` (line 515); `scope` matches 7 lines.
4. Rendered `metrics.collect(conn, project="/proj")` starts `project: /proj`; unfiltered starts `project: all (1 in this log) -- filter with --project PATH|name`; the pointer line prints under view 4's two rows.

No drift from `## Plan`. `render()` reads `data["scope"]` unconditionally, and
every caller builds `data` from `collect()` -- `pipeline/cli/main.py:589` and
`tests/test_metrics.py:133,277,335,352` -- so no caller raises `KeyError`.
`COUNT(DISTINCT project)` cannot undercount: `project TEXT NOT NULL`
(`pipeline/daemon/store.py:19`).

Non-blocking (severity: nit): the continuation lines of the two new
`out.append(f"...")` calls sit one column left of the opening paren.

### 2026-08-29 05:01:29Z · review · session · session=7543f655-d8f2-4cc4-8a51-009cdf27c6b1

`review` ran as session `7543f655-d8f2-4cc4-8a51-009cdf27c6b1`
- replay: `claude --resume 7543f655-d8f2-4cc4-8a51-009cdf27c6b1`
- log: `.project/logs/TICKET-093-review-7543f655.log`
- cost: $0.86 of a $5 cap
- tokens: 7,057 out (2,412 thinking) · 36 in · 604,257 cache read · 37,830 cache write

### 2026-08-29 05:01:29Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed the 3-commit delta: no blocking findings; 121 passed, both named tests pass, only the two declared files change

### 2026-08-29 05:03:36Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 05:03:37Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/093


Rebasing (1/3)Rebasing (2/3)Rebasing (3/3)Successfully rebased and updated refs/heads/ticket/093.
Already up to date.
Updating 2562ad1..c566af3
Fast-forward
 pipeline/cli/metrics.py | 23 +++++++++++++++++++++++
 tests/test_metrics.py   | 34 ++++++++++++++++++++++++++++++++++
 2 files changed, 57 insertions(+)

```

### 2026-08-29 05:03:37Z · merging · decision

decision recorded as `DEC-093`
