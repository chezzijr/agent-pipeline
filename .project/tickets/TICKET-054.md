---
id: TICKET-054
stage: done
class: bugfix
branch: ticket/054
test_file: tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only
files_declared:
- pipeline/core/gate.py
- pipeline/stages/planning.md
- tests/test_gate.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 13
  plan_files: 3
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: ec212023-df4b-42fa-b948-61deb4ff3e16
  log: .project/logs/TICKET-054-review-ec212023.log
approved_by: chezzijr
approved_at: '2026-08-24T12:20:06.920735+00:00'
---

## Summary
a wrapped acceptance criterion is checked as if each of its lines were a separate criterion

The Tier A rule that every acceptance criterion must name a test iterates over
lines, with no notion of a continuation:

    pipeline/core/gate.py:272
    for line in [l for l in crit.splitlines() if CRIT_ITEM_RE.match(l)]:

A criterion that wraps is therefore checked twice: once as itself, and once as
whatever its second line looks like. When that second line begins with a flag
-- `--porcelain`, `--force`, `-v` -- `CRIT_ITEM_RE` matches the leading `-`,
the line is treated as a criterion of its own, and it names no test.

Seen on main at 1a6a276. TICKET-036 carries this criterion, one bullet over two
lines:

    - `grep -rF probe-mcp tests/ pipeline/` prints nothing and `git status
      --porcelain` prints nothing at the end of step 5: both throwaway files,

The gate passed the first line and failed the second:

    acceptance criterion names no test: --porcelain` prints nothing at the
    end of step 5: both throwaway files,

That finding was TICKET-036's fourth plan-validation failure and escalated it,
with thirteen sound criteria and a plan Tier B had stopped objecting to. A
human rewrapped the bullet onto one line and the gate passed it unchanged.

The `## Plan` scan in the same function already solves this, and its solution
is the model:

    pipeline/core/gate.py
    elif in_step and re.match(r"^\s+\S", line):
        # a continuation of the previous step, not a step of its own
        steps[-1] += " " + line.strip()

Expected: a criterion is the item marker plus every indented line under it, and
the test-shape check runs against that whole text. The wrapped form above must
pass, because `tests/` appears in it.

This is not new. `startswith(("-", "*"))` had the same behaviour before
TICKET-042 widened the markers, so TICKET-042 neither caused it nor covered it:
that ticket fixed which markers count, this one is about what a criterion is.

The failure a test should show is `gate()` reporting `names no test` for a
criterion whose wrapped continuation begins with `--porcelain`, where the
criterion as a whole names a test.

**Planning settled the two open questions (2026-08-24).**

1. Indentation marks a continuation. An unindented second line stays a
   criterion of its own and keeps failing.
2. `## Acceptance criteria` consults `_fenced()`, like `## Plan`. A fence
   indented under a criterion joins onto it; a fence at column 0 is quoted
   output and is skipped with no finding.

The plan is 13 steps over `pipeline/core/gate.py`, `tests/test_gate.py` and
`pipeline/stages/planning.md`. The continuation arm must run before the marker
arm, unlike the `## Plan` scan, because `CRIT_ITEM_RE` matches the leading `-`
of `--porcelain`. The committed reproduction test does not reach that shape;
step 1 adds a test that does. `## Digest` carries the rest; the thread adds
nothing a later stage needs.

**plan-validation passed the plan (2026-08-24).** All eight judgment items
pass. Two notes for `implementing`, neither a blocker. Step 5 (one sentence in
`pipeline/stages/planning.md`) maps to no acceptance criterion and is accepted
as the writer-facing half of the indentation rule. Step 10 tests
`raw[:1].isspace()` per line, so a column-0 line inside an indented fence is
skipped, not joined; it draws no finding either way. Implement the plan as
written.

**implementing executed the plan as written (2026-08-24).** All 13 steps done,
three commits (86d6667, a7d5025, 437f7da). `pipeline/core/gate.py`'s criteria
scan now joins an indented continuation onto the criterion above it before the
marker check runs, and consults `_fenced()` for a criteria-section fence. Six
new tests in `tests/test_gate.py`, `uv run --group dev pytest -q` reports 288
passed, 0 failed.

**review passed the delta (2026-08-24), no blocking findings.** The diff
`f85cb13..HEAD` matches the plan step for step and the `## Decisions` text. All
eight acceptance criteria hold: `288 passed in 12.26s` for the whole suite, and
the ten criteria tests report `10 passed, 28 deselected`. Two non-blocking nits
are in the thread: the indented-fence test passes with the `crit_fenced` branch
deleted, and `in_crit` survives a column-0 fence. Neither needs work.

## Reproduction

`tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only`,
run with `uv run --group dev pytest -q tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only`.

```
E       AssertionError: ['acceptance criterion names no test: - passes once the fix lands:']
E       assert False
```

expect: acceptance criterion names no test: - passes once the fix lands:

## Digest

Files touched: `pipeline/core/gate.py` (the criteria scan), `tests/test_gate.py`
(five new tests), `pipeline/stages/planning.md` (one sentence stating the wrap
rule to the writer).

Key functions: `gate()` in `pipeline/core/gate.py` -- the `## Acceptance
criteria` scan is its last check, at `pipeline/core/gate.py:347-357`. It reads
`CRIT_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])")` (line 46) and filters
`crit.splitlines()` with it, one line at a time. The `## Plan` scan above it
(lines 278-338) is the model: it joins `elif in_step and re.match(r"^\s+\S",
line)` onto `steps[-1]` and consults `_fenced(raws)` from
`pipeline/core/ticket.py`.

Entry points: `gate(project, tid)` is called by `plan-validation`; the tests
call it directly on a throwaway project from `tests/helpers.py::project()`,
whose `FIXTURE` carries the single criterion `- ``test_broken`` passes`.

Gotchas:

1. The continuation arm must run BEFORE the marker arm, the opposite of the
   `## Plan` scan. `PLAN_STEP_RE` is `^\s*\d+[.)]`, which wrapped prose rarely
   matches; `CRIT_ITEM_RE` matches a bare leading `-`, so an indented
   `--porcelain` continuation matches it and would still read as a criterion of
   its own if the marker arm ran first.
2. Consequence of that ordering, accepted: an indented sub-bullet under a
   criterion joins onto its parent instead of being checked alone. Today each
   is checked alone.
3. The committed reproduction test does not cover the ticket's reported shape.
   `tests/test_gate.py:178` wraps onto `  ``test_broken`` no longer errors`,
   whose continuation starts with a backtick, so it passes under either arm
   ordering. Step 1 adds the `--porcelain` case, which is what forces the
   ordering in gotcha 1.
4. `_fenced()` marks fence delimiter lines `True` too, and `FENCE_RE` is
   `^ {0,3}(?P<f>`{3,}|~{3,})`, so a fence indented two spaces is still a real
   fence, not a plain continuation line.
5. `secs["Acceptance criteria"]` is the stripped section body, so `_fenced()`
   indices line up with its own `splitlines()`.

## Decisions checked

- DEC-042 -- the record this plan changes. It fixed which markers count and
  recorded both of this ticket's targets as "Deliberately not fixed": the
  wrapped criterion, and the criteria scan not consulting `_fenced()`. Still
  active, so `## Decisions` below supersedes it and restates what stays true.
- DEC-016 -- fence state is parsed once, in `_fenced()`; a new scan over a
  ticket body consults it rather than matching backticks itself. This plan
  complies: step 9 calls `_fenced()`.
- DEC-030 -- a `## Plan` finding states the rule that would fix it, and
  `tests/test_gate.py` must not import gate constants (DEC-017/DEC-018: the
  gate runs this file on a checkout of base). The new tests assert on literal
  substrings only. Its narrow-scope note about `acceptance criterion names no
  test` was already closed by DEC-042.
- DEC-050 -- `pipeline plan` prints `## Acceptance criteria`; read-only, no
  interaction with this change.

Grep terms used against `.project/decisions/`: `criteri`, `criterion`,
`acceptance`, `_fenced`, `gate.py`, `continuation`, `indent`.

## Plan

1. Add `test_a_wrapped_criterion_whose_continuation_starts_with_a_flag_passes` to `tests/test_gate.py` after `test_a_wrapped_criterion_is_checked_whole_not_first_line_only`: `d = project(FIXTURE.replace("- `test_broken` passes", "- `grep -rF probe tests/` prints nothing and `git status\n  --porcelain` prints nothing"))`, then `ok, failures = gate(d, "TICKET-001")`, `assert ok, failures`, `shutil.rmtree(d)`; docstring: TICKET-036 escalated on this shape because `CRIT_ITEM_RE` matches the leading `-` of `--porcelain`.
2. Run `uv run --group dev pytest -q tests/test_gate.py::test_a_wrapped_criterion_whose_continuation_starts_with_a_flag_passes` and watch it fail with `AssertionError: ['acceptance criterion names no test: --porcelain` prints nothing']` -- the ticket's reported failure, which the committed test at `tests/test_gate.py:178` does not reach.
3. In `pipeline/core/gate.py`, replace the criteria filter at lines 347-348 with a joining scan that builds `crits: list[str]` from `crit_lines = secs.get("Acceptance criteria", "").splitlines()`: iterate `enumerate(crit_lines)`, `continue` on a blank line without clearing `in_crit`, then `if in_crit and re.match(r"^\s+\S", raw): crits[-1] += " " + raw.strip()`, `elif CRIT_ITEM_RE.match(raw): crits.append(raw.strip()); in_crit = True`, `else: in_crit = False`.
4. In `pipeline/core/gate.py`, run the existing test-shape `re.search(r"\bpytest\b|\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/", c, re.I)` over each entry `c` of `crits` instead of over each line, keeping the finding string `f"acceptance criterion names no test: {c}"`, and comment that the continuation arm runs before the marker arm because `CRIT_ITEM_RE` matches a leading `-`.
5. In `pipeline/stages/planning.md`, extend the `## Acceptance criteria` bullet at line 73 to read: `- ``## Acceptance criteria`` -- each one falsifiable and mapped to a named test. A criterion that wraps must indent its continuation lines; an unindented line reads as a criterion of its own and is checked alone.`
6. Run `uv run --group dev pytest -q tests/test_gate.py` and expect every test green, including `test_a_wrapped_criterion_is_checked_whole_not_first_line_only` and the step 1 test; commit `pipeline/core/gate.py`, `pipeline/stages/planning.md` and `tests/test_gate.py` as `fix(TICKET-054): join a wrapped acceptance criterion before checking it`.
7. Add two over-fixing guards to `tests/test_gate.py`: `test_an_unindented_second_line_is_a_criterion_of_its_own`, which replaces the fixture criterion with `- `test_broken` passes and `git status\n--porcelain` prints nothing` and asserts `not ok` and `any("names no test" in f for f in failures)`; and `test_a_wrapped_criterion_naming_no_test_anywhere_still_fails`, which replaces it with `- the code is clean and\n  the latency drops below `10ms`` and asserts the same two things.
8. Run `uv run --group dev pytest -q tests/test_gate.py -k "unindented or naming_no_test_anywhere"` and expect `2 passed`; both fail if `pipeline/core/gate.py` drops the indent condition or the test-shape check; commit `tests/test_gate.py` as `test(TICKET-054): an unindented second line is still its own criterion`.
9. Add `test_a_top_level_fence_in_acceptance_criteria_is_not_read_as_criteria` to `tests/test_gate.py`: replace the fixture criterion with `- `test_broken` passes\n\n```\n- code should be clean\n``` ` and assert `ok, failures`; run `uv run --group dev pytest -q tests/test_gate.py::test_a_top_level_fence_in_acceptance_criteria_is_not_read_as_criteria` and watch it fail with `AssertionError: ['acceptance criterion names no test: - code should be clean']`.
10. In `pipeline/core/gate.py`, add `crit_fenced = _fenced(crit_lines)` above the step 3 loop and give the loop a first branch after the blank-line skip: `if crit_fenced[i]:` joins the line onto `crits[-1]` when `in_crit and raw[:1].isspace()`, then `continue` either way -- an indented fence is part of the criterion above it, a column-0 fence is quoted output and is skipped with no finding.
11. Add `test_a_fenced_block_indented_under_a_criterion_is_part_of_it` to `tests/test_gate.py`: replace the fixture criterion with `- this prints nothing:\n\n  ```\n  pytest tests/test_thing.py\n  ``` ` and assert `ok, failures`; it fails if `pipeline/core/gate.py` skips an indented fenced line instead of joining it.
12. Run `uv run --group dev pytest -q tests/test_gate.py` and expect every test green; commit `pipeline/core/gate.py` and `tests/test_gate.py` as `fix(TICKET-054): read a fenced block in the criteria section like the plan scan does`.
13. Run `uv run --group dev pytest -q` and expect the whole dispatcher suite green -- `pipeline/core/gate.py` reaches `tests/test_gate.py`, `tests/test_supervisor.py` and `tests/test_cli.py`.

## Acceptance criteria

- `tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only` passes: the reproduction test triage committed at f85cb13.
- `tests/test_gate.py::test_a_wrapped_criterion_whose_continuation_starts_with_a_flag_passes` passes: an indented continuation beginning with `--porcelain` is part of the criterion above it, not a criterion of its own.
- `tests/test_gate.py::test_an_unindented_second_line_is_a_criterion_of_its_own` passes: a second line at column 0 still draws `acceptance criterion names no test`.
- `tests/test_gate.py::test_a_wrapped_criterion_naming_no_test_anywhere_still_fails` passes: joining the lines does not make a vacuous criterion pass.
- `tests/test_gate.py::test_a_top_level_fence_in_acceptance_criteria_is_not_read_as_criteria` passes: a `- ` line inside a column-0 fenced block produces no finding.
- `tests/test_gate.py::test_a_fenced_block_indented_under_a_criterion_is_part_of_it` passes: a test name inside a fence indented under a criterion satisfies the test-shape check.
- `uv run --group dev pytest -q tests/test_gate.py` reports no failures, so `test_gate_blocks_a_vacuous_acceptance_criterion`, `test_a_numbered_acceptance_criterion_naming_no_test_is_caught`, `test_numbered_criteria_are_checked_in_both_marker_forms` and `test_a_whole_suite_criterion_naming_pytest_is_accepted` still hold.
- `uv run --group dev pytest -q` reports no failures.

## Decisions

supersedes: DEC-042 -- its two "Deliberately not fixed" notes are exactly what
this ticket fixes: a wrapped criterion checked on its first line only, and the
criteria scan not consulting `_fenced()`. Everything else DEC-042 decided
stands and is restated below.

**A criterion is its marker line plus every line indented under it.** The
`## Acceptance criteria` scan in `pipeline/core/gate.py` joins continuation
lines exactly as the `## Plan` scan joins them onto a step. TICKET-036
escalated with thirteen sound criteria because one bullet wrapped onto a line
starting with `--porcelain`, which was read as a criterion naming no test.

**The continuation arm runs before the marker arm, the opposite order to the
`## Plan` scan. Do not "align" them.** `PLAN_STEP_RE` is `^\s*\d+[.)]`;
`CRIT_ITEM_RE` matches a bare leading `-`, so wrapped prose beginning with a
flag matches it. Checking the marker first leaves the escalating bug in place.
The accepted cost: an indented sub-bullet joins onto its parent criterion
instead of being checked on its own.

**Indentation is what marks a continuation.** A second line at column 0 is a
formatting error, not a wrap, and still fails --
`test_an_unindented_second_line_is_a_criterion_of_its_own` holds that line.

**The criteria scan consults `_fenced()`, per DEC-016.** A fenced block
indented under a criterion joins onto it, so a criterion may quote the command
that checks it. A fence at column 0 is quoted output: its lines are skipped
silently, with no finding. That is deliberately unlike the `## Plan` scan,
which reports a column-0 fence, because a numbered step hidden in a fence
evades the `files_declared` check and a hidden bullet evades nothing.

**Unchanged from DEC-042, still binding:** `CRIT_ITEM_RE` matches four markers
(`-`, `*`, `1.`, `1)`), the numbered arm is spelled `\d+[.)]` like the
`## Plan` scan and changes with it, and the bullet arm stays a prefix match --
adding `\s` after `-`/`*` would silently stop checking `**bold prose**` and
`--- ` lines.

## Rollback

Revert the two commits from steps 6 and 12 on `ticket/054`, plus the test-only
commit from step 8. That restores the one-line-at-a-time filter at
`pipeline/core/gate.py:348`, and the gate goes back to failing a wrapped
criterion on its first line -- a false `names no test` finding, not a missed
one, so nothing unsound lands while it is reverted. Keep f85cb13, the
reproduction test; it fails again after the revert and is the ticket's
evidence.

## Thread

### 2026-08-24 12:01:43Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 12:03:18Z · triage · session · session=5fabbb18-0cdf-4fe2-aad0-f644ad6bec6b

### 2026-08-24 · triage · note

Reproduced. `pipeline/core/gate.py:348` scans `## Acceptance criteria` line
by line with no continuation join, unlike the `## Plan` scan at the same
file (which joins `re.match(r"^\s+\S", line)` onto `steps[-1]`). A
two-line criterion whose test name is on the second line therefore fails
the test-shape check on the first line alone.

Wrote `tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only`,
committed at f85cb13. It wraps `- \`test_broken\` passes` onto two lines
with the test name on line two and asserts `gate()` still passes it.

Confirmed red for the reported reason:
`AssertionError: ['acceptance criterion names no test: - passes once the
fix lands:']`. Matches the ticket's example (`--porcelain` case): both are
the criteria scan reading a continuation line as its own item.

Not a chore: the ticket names two open design questions (whether an
unindented second line should still fail, and whether `_fenced()` should
guard `## Acceptance criteria` too) that planning must settle, not just a
one-line fix.

`triage` ran as session `5fabbb18-0cdf-4fe2-aad0-f644ad6bec6b`
- replay: `claude --resume 5fabbb18-0cdf-4fe2-aad0-f644ad6bec6b`
- log: `.project/logs/TICKET-054-triage-5fabbb18.log`

### 2026-08-24 12:03:18Z · triage · note

`triage` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-08-24 12:04:00Z · triage · session · session=c538c55c-ac6a-4f13-9ad0-6cbc0fb49aac

`triage` ran as session `c538c55c-ac6a-4f13-9ad0-6cbc0fb49aac`
- replay: `claude --resume c538c55c-ac6a-4f13-9ad0-6cbc0fb49aac`
- log: `.project/logs/TICKET-054-triage-c538c55c.log`

### 2026-08-24 12:04:00Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced with tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only, committed at f85cb13

### 2026-08-24 12:09:44Z · planning · note

Plan written: 13 steps over `pipeline/core/gate.py`, `tests/test_gate.py` and
`pipeline/stages/planning.md`.

Settled the ticket's two questions. (1) Indentation marks a continuation; an
unindented second line stays its own criterion and keeps failing. (2) The
criteria scan consults `_fenced()`, per DEC-016: a fence indented under a
criterion joins onto it, a column-0 fence is skipped with no finding.

One finding the implementer needs: the reproduction test committed at f85cb13
does not cover the shape the ticket reports. `tests/test_gate.py:178` wraps
onto ``  `test_broken` no longer errors``, whose continuation starts with a
backtick, so it passes whether the marker arm or the continuation arm runs
first. The `--porcelain` shape does not, because `CRIT_ITEM_RE` matches its
leading `-`. Step 1 adds
`test_a_wrapped_criterion_whose_continuation_starts_with_a_flag_passes` for
that shape, and it is what forces the continuation arm to run first.

`## Decisions` supersedes DEC-042. Its two "Deliberately not fixed" notes name
exactly this ticket's two targets; everything else DEC-042 decided is restated
and kept.

Scope check: one subsystem, one function. No split needed.

### 2026-08-24 12:10:10Z · planning · session · session=ea7712e3-aff0-4192-b283-728cd3a10455

`planning` ran as session `ea7712e3-aff0-4192-b283-728cd3a10455`
- replay: `claude --resume ea7712e3-aff0-4192-b283-728cd3a10455`
- log: `.project/logs/TICKET-054-planning-ea7712e3.log`

### 2026-08-24 12:10:10Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ 13-step plan: join wrapped acceptance criteria in gate.py, continuation arm before marker arm, criteria scan consults _fenced(); supersedes DEC-042

### 2026-08-24 12:16:32Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only` fails as required
```
======================
________ test_a_wrapped_criterion_is_checked_whole_not_first_line_only _________

    def test_a_wrapped_criterion_is_checked_whole_not_first_line_only():
        """DEC-042: the criteria scan does not join an indented continuation
        line onto the bullet above it, unlike the `## Plan` scan. A criterion
        whose test name falls on its second line draws a false `names no test`
        finding even though the whole criterion does name one.
        """
        d = project(FIXTURE.replace(
            "- `test_broken` passes",
            "- passes once the fix lands:\n  `test_broken` no longer errors"))
        ok, failures = gate(d, "TICKET-001")
>       assert ok, failures
E       AssertionError: ['acceptance criterion names no test: - passes once the fix lands:']
E       assert False

tests/test_gate.py:188: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only` fails on base `main` too -- the bug is not already fixed upstream
```
t_broken` passes",
            "- passes once the fix lands:\n  `test_broken` no longer errors"))
        ok, failures = gate(d, "TICKET-001")
>       assert ok, failures
E       AssertionError: ['acceptance criterion names no test: - passes once the fix lands:']
E       assert False

tests/test_gate.py:188: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-y_otp_09/base
      Built pipeline @ file:///tmp/pipeline-base-y_otp_09/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 · plan-validation · note

**Judgment review: PASS on all eight items.**

1. Root cause: the criteria scan has no notion of a criterion spanning lines.
   `pipeline/core/gate.py:348` filters `crit.splitlines()` with `CRIT_ITEM_RE`,
   so a wrapped line beginning `--porcelain` matches the leading `-` and is
   checked as a criterion of its own. The plan fixes the scan, not the test.
2. Decisions: DEC-042 lines 12 and 14 record both targets as "Deliberately not
   fixed"; `## Decisions` supersedes them and restates the rest. Step 10 calls
   `_fenced()`, so DEC-016 holds. The new tests assert literal substrings, so
   DEC-030's no-import rule holds.
3. Scope: step 5 (one sentence in `pipeline/stages/planning.md`) maps to no
   criterion. Accepted: it states the indentation rule this fix makes binding,
   in a declared file. Every other step maps to a criterion.
4. Criteria: falsifiable in both directions. Steps 7 and 8 add the over-fixing
   guards, so joining lines cannot make a vacuous criterion pass.
5. No research left: every step names its file, line and regex.
6. Riskiest: step 10, the `_fenced()` branch. `## Rollback` isolates it in the
   step 12 commit and states the reverted behaviour is a false finding, not a
   missed one.
7. Regression: the five criteria tests at `tests/test_gate.py` lines 131, 138,
   146, 165 and 406, plus step 13's whole suite.
8. Blast radius: three files, one function. A bugfix.

One note for `implementing`, not a blocker: step 10 tests `raw[:1].isspace()`
per line, so a column-0 line inside an indented fence is skipped, not joined.
It draws no finding either way.

### 2026-08-24 12:19:14Z · plan-validation · session · session=875e46f8-88c2-4f81-9b70-eedc22e70065

`plan-validation` ran as session `875e46f8-88c2-4f81-9b70-eedc22e70065`
- replay: `claude --resume 875e46f8-88c2-4f81-9b70-eedc22e70065`
- log: `.project/logs/TICKET-054-plan-validation-875e46f8.log`

### 2026-08-24 12:19:14Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight judgment items; root cause is the criteria scan reading each line as its own criterion, DEC-042 superseded with justification, riskiest step 10 has a stated rollback

### 2026-08-24 12:20:06Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 12:20:21Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-24 12:16:32Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only` fails on base `main` too -- the bug is not already fixed upstream
```
st_broken` passes",
            "- passes once the fix lands:\n  `test_broken` no longer errors"))
        ok, failures = gate(d, "TICKET-001")
>       assert ok, failures
E       AssertionError: ['acceptance criterion names no test: - passes once the fix lands:']
E       assert False

tests/test_gate.py:188: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_wrapped_criterion_is_checked_whole_not_first_line_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-vhirnbzk/base
      Built pipeline @ file:///tmp/pipeline-base-vhirnbzk/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 12:20:21Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 · implementing · todo

**Todo (13 plan steps):**

1. [x] add `--porcelain` continuation test
2. [x] run it, confirm RED with the ticket's reported failure
3. [x] gate.py: join scan replacing the crit filter
4. [x] gate.py: run test-shape check over joined `crits`
5. [x] planning.md: state the indentation rule
6. [x] run `tests/test_gate.py`, commit steps 3-6
7. [x] add two over-fixing guard tests
8. [x] run guard tests, commit
9. [x] add top-level-fence test, confirm RED
10. [x] gate.py: `_fenced()` branch for criteria
11. [x] add indented-fence-is-part-of-criterion test
12. [x] run full `test_gate.py`, commit
13. [x] run whole dispatcher suite

### 2026-08-24 · implementing · report

**All 13 steps done, plan followed as written, no deviation.**

Step 2 RED matched the ticket exactly:
`AssertionError: ['acceptance criterion names no test: --porcelain\` prints nothing']`.
Step 9 RED matched its expected failure exactly:
`AssertionError: ['acceptance criterion names no test: - code should be clean']`.

Three commits on `ticket/054`:
- 86d6667 `fix(TICKET-054): join a wrapped acceptance criterion before checking it`
- a7d5025 `test(TICKET-054): an unindented second line is still its own criterion`
- 437f7da `fix(TICKET-054): read a fenced block in the criteria section like the plan scan does`

`uv run --group dev pytest -q tests/test_gate.py` -- 38 passed.
`uv run --group dev pytest -q` (whole suite) -- 288 passed.

Six new tests, each fails if reverted independently: the flag-continuation
test, the unindented-second-line guard, the vacuous-wrapped-criterion guard,
the top-level-fence test, the indented-fence test, plus the committed
reproduction test now passing.

### 2026-08-24 12:22:43Z · implementing · session · session=9704988a-294f-4c1f-9386-6c1ae2806b17

`implementing` ran as session `9704988a-294f-4c1f-9386-6c1ae2806b17`
- replay: `claude --resume 9704988a-294f-4c1f-9386-6c1ae2806b17`
- log: `.project/logs/TICKET-054-implementing-9704988a.log`

### 2026-08-24 12:22:43Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Joined wrapped acceptance criteria before checking them; 6 new tests, 288 passed, no deviation from plan.

### 2026-08-24 · review · findings

**No blocking findings. Delta reviewed: `git diff f85cb13..HEAD` -- three
files, 96 insertions, 3 deletions.**

The code matches the plan step for step and the `## Decisions` text. All eight
acceptance criteria hold: `uv run --group dev pytest -q` reports `288 passed in
12.26s`, and the ten criteria tests named in `## Acceptance criteria` report
`10 passed, 28 deselected`. `git status --porcelain` prints nothing; I edited
only this ticket. No path in the diff is in `machine.FENCED`.

Two candidate findings, both refuted:

1. `crits[-1]` on an empty list. Refuted: `in_crit` is set True only at
   `pipeline/core/gate.py:371-373`, in the arm that appends first.
2. Over-fixing -- joining makes a vacuous criterion pass. Refuted:
   `tests/test_gate.py:216` asserts the finding on a two-line criterion naming
   no test, and passes.

Two non-blocking notes:

1. **nit.** `test_a_fenced_block_indented_under_a_criterion_is_part_of_it`
   still passes if the whole `crit_fenced` branch at
   `pipeline/core/gate.py:360-363` is deleted -- the continuation arm joins
   those indented lines anyway. It fails only under the narrower mutation of
   skipping an indented fenced line, which is the mutation plan step 11 named.
2. **nit.** `in_crit` survives a column-0 fence, so an indented line after
   quoted output joins onto the criterion above the fence. Same class as the
   sub-bullet cost `## Decisions` already accepted.

### 2026-08-24 12:26:08Z · review · session · session=ec212023-df4b-42fa-b948-61deb4ff3e16

`review` ran as session `ec212023-df4b-42fa-b948-61deb4ff3e16`
- replay: `claude --resume ec212023-df4b-42fa-b948-61deb4ff3e16`
- log: `.project/logs/TICKET-054-review-ec212023.log`

### 2026-08-24 12:26:08Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ delta f85cb13..HEAD matches the plan; 288 passed, 10 criteria tests pass; no blocking findings, two nits in the thread

### 2026-08-24 12:26:21Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 12:26:22Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/054


Current branch ticket/054 is up to date.
Already up to date.
Updating 1a6a276..437f7da
Fast-forward
 pipeline/core/gate.py       | 34 ++++++++++++++++++--
 pipeline/stages/planning.md |  2 ++
 tests/test_gate.py          | 77 +++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 110 insertions(+), 3 deletions(-)

```

### 2026-08-24 12:26:22Z · merging · decision

decision recorded as `DEC-054`
