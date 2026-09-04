---
id: TICKET-111
stage: done
class: bugfix
branch: ticket/111
test_file: tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged
files_declared:
- pipeline/core/gate.py
- pipeline/stages/planning.md
- tests/test_gate.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 7
  plan_files: 3
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 405beae9-96f7-4171-862b-003a520bbbf0
  replay: claude --resume 405beae9-96f7-4171-862b-003a520bbbf0
  log: .project/logs/TICKET-111-review-405beae9.log
  cost_usd: 1.3427764999999998
approved_by: claude-for-chezzijr
approved_at: '2026-09-03T16:45:13.333171+00:00'
---

## Summary

Fixed and reviewed. `assertion_clause()` and `CRIT_BASELINE_RE`, new in
`pipeline/core/gate.py`, cut a criterion at the `Measured ...` or
`baseline ...` opening its baseline clause; the count loop in `gate()` now
scans `assertion_clause(c)` in place of `c`. `pipeline/stages/planning.md`
gained the matching baseline-clause sentence in `## Acceptance criteria`.

Added 3 tests to `tests/test_gate.py`, confirmed RED before the fix,
GREEN after: `test_a_parenthesised_baseline_clause_is_not_flagged`,
`test_a_count_pinned_before_a_baseline_clause_is_still_flagged`,
`test_re_measured_is_not_read_as_a_baseline_marker`. The repro test
`test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged` now
passes.

Committed `a64ffd1`: `pipeline/core/gate.py`, `tests/test_gate.py`,
`pipeline/stages/planning.md`. None is in `machine.FENCED`.

Review passed on 2026-09-04 with no blocking findings. It re-ran every
acceptance criterion: `uv run --group dev pytest -q` -> `537 passed in
55.59s`, `tests/test_gate.py` -> `86 passed in 2.96s`,
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`, and both
`grep -c` counts as required. It left 2 nits, both making the marker stricter
rather than looser; the review entry in `## Thread` holds them.

## Reproduction

`tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged`

    uv run --group dev pytest -q tests/test_gate.py -k relation_and_a_baseline

Fails with:

    AssertionError: ['acceptance criterion pins an absolute count copied
    from `## Digest` (318): - the test count equals `ls
    judge/problems/*/samples/*.in | wc -l` re-measured at that moment.
    Measured on the prototype: `done: 318 case(s), 0 failure(s)` in 40.9
    s. -- a total any other ticket can move is not a property of this
    change -- state it as a relation to a measured baseline, or
    re-measure at check time; one `count-pinned: <why it cannot move>`
    line in `## Acceptance criteria` waives this check']

expect: acceptance criterion pins an absolute count copied from `## Digest` (318)

The blocking case in `test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`
still passes; only the new baseline-clause case is wrong.

## Digest

Files touched: `pipeline/core/gate.py` (the constant block at lines 54-84 and
the count loop at lines 815-825), `tests/test_gate.py` (the count tests at
lines 567-648), `pipeline/stages/planning.md` (the `## Acceptance criteria`
bullet at lines 80-85). `pipeline/stages/planning.md` is NOT in
`machine.FENCED`; `.project/stages/planning.extra.md` is, and this plan does
not touch it.

Key functions: `gate()` in `pipeline/core/gate.py` builds `crits`, one joined
string per criterion, then runs the count check in its own loop above the
names-a-test loop -- `dig_counts = set(COUNT_RE.findall(dig))`, then per
criterion `sorted(set(CRIT_COUNT_RE.findall(c)) & dig_counts, key=int)`. That
loop is the only reader of `CRIT_COUNT_RE`.

Entry point: Tier A runs as a spawned child through `gate_cmd()`; the tests
call `gate(project, "TICKET-001")` directly and assert on the failure list it
returns.

Gotchas:
1. `COUNT_RE` scans `## Digest`; `CRIT_COUNT_RE`, which needs a count noun
   AFTER the number, scans the criterion. Only the criterion side changes.
2. The word `re-measured` contains `measured`. A marker anchored on a bare
   word boundary matches inside it and would silence every criterion using the
   word the rule itself asks for.
3. The finding prefix `acceptance criterion pins an absolute count` is a
   `STRUCTURAL_MARKS` entry matched with `startswith`. Leave it byte-identical
   or the failure moves onto `plan_validation_attempts`.
4. Measured baseline on `ticket/111` at 164148c: `uv run --group dev pytest -q
   tests/test_gate.py` prints `1 failed, 80 passed in 3.34s`, the one failure
   being the repro test.
5. Prototype run against the real `CRIT_COUNT_RE`: with `CRIT_BASELINE_RE` as
   spelled in step 3, the repro criterion loses `318`, and both existing
   blocking criteria keep `630`.

## Decisions checked

- DEC-081 (TICKET-081, the check itself) -- binding. It requires the count
  check to stay in its own loop over `crits`, above the names-a-test loop;
  requires the count noun to follow the number; and keeps `count-pinned:` a
  waiver. This plan changes only the string that loop scans, so all three hold.
- DEC-079 -- binding. The finding prefix `acceptance criterion names no test`
  and `CRIT_RULE` are untouched.
- DEC-030 -- binding. `CRIT_COUNT_RULE` in `pipeline/core/gate.py` paraphrases
  `## Acceptance criteria` in `pipeline/stages/planning.md`; the two copies are
  deliberate and change together, which is why step 6 exists. DEC-030 also
  forbids importing a gate constant into `tests/test_gate.py`, so the new tests
  assert on literal substrings only.
- DEC-065 -- binding. A new structural finding needs its own
  `STRUCTURAL_MARKS` prefix. This plan adds no finding, so that list is
  unchanged.
- DEC-016 -- binding, and untouched: `_fenced()` stays the one parse of fence
  state in the criteria scan.
- DEC-042 -- history, marked `superseded-by: DEC-054`. Cited for context on
  what `CRIT_ITEM_RE` reads as a criterion line.
- Grep terms used over `.project/decisions/`: `count`, `CRIT_COUNT`,
  `count-pinned`, `absolute count`, `acceptance criteri`.

## Plan

1. Add three tests to `tests/test_gate.py` after `test_a_count_pinned_line_waives_the_absolute_count_check` (ends line 613), each built like its neighbours with `project(_set_digest(DIGEST).replace("- `test_broken` passes", CRITERIA))` and closing with `shutil.rmtree(d)`, where DIGEST is the same three-line string the two existing count tests use (`thing.py holds it`, `630 passed in tests/chz`, `eviction runs on write, not read`): `test_a_parenthesised_baseline_clause_is_not_flagged` uses criteria ``- `test_broken` passes`` plus ``- `pytest -q tests/chz` reports no new failures (baseline: 630 passed)`` and asserts `ok, failures`; `test_a_count_pinned_before_a_baseline_clause_is_still_flagged` uses the single criterion ``- `tests/chz` suite: 630 passed. Measured before: 629 passed`` and asserts `not ok and any("absolute count" in f for f in failures)`; `test_re_measured_is_not_read_as_a_baseline_marker` uses the single criterion ``- `tests/chz` re-measured at check time still reports 630 passed`` and asserts the same pair.
2. Run `uv run --group dev pytest -q tests/test_gate.py -k "baseline or re_measured"` and confirm two tests fail with `acceptance criterion pins an absolute count` -- `test_a_parenthesised_baseline_clause_is_not_flagged` and the repro `test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged` -- while the other two pass. This step changes no file.
3. In `pipeline/core/gate.py`, below the `CRIT_COUNT_RULE` block (ends line 84), add the constant `CRIT_BASELINE_RE` compiled with `re.I` from the pattern `(?:^|[.;:)(\[]|--)\s*(?:measured|baseline)\b`, and add `def assertion_clause(crit: str) -> str:` beside it, which searches `crit` with that regex and returns `crit[:m.start()]` on a match and `crit` otherwise; comment it with three facts -- a baseline is evidence and not an assertion, the marker opens a clause only at the criterion start or after one of `.;:()[` or after `--` so `re-measured` is not one, and the clause runs to the end of the criterion so a total stated before the marker stays in scope.
4. In `pipeline/core/gate.py`, replace the count loop's line 820, `shared = sorted(set(CRIT_COUNT_RE.findall(c)) & dig_counts, key=int)`, with two lines: `counts = set(CRIT_COUNT_RE.findall(assertion_clause(c)))` then `shared = sorted(counts & dig_counts, key=int)`. Change nothing else in that loop; the finding string, its prefix and `CRIT_COUNT_RULE` stay byte-identical.
5. Run `uv run --group dev pytest -q tests/test_gate.py` and confirm it reports no failures, in particular that `test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` and `test_a_test_shaped_criterion_pinning_a_count_is_still_flagged` still pass.
6. In `pipeline/stages/planning.md`, append one sentence to the `## Acceptance criteria` bullet (lines 80-85), after `section waives that check.`: a baseline clause is exempt, because the gate stops scanning a criterion at the `Measured ...` or `baseline ...` that opens the clause, so quote the total you measured there. DEC-030 requires this copy to move with the meaning of `CRIT_COUNT_RULE`.
7. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, confirm both are green, then commit `pipeline/core/gate.py`, `tests/test_gate.py` and `pipeline/stages/planning.md` with the message `fix: scan only a criterion's assertion clause for a pinned count`.

## Acceptance criteria

- `tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged`
  passes.
- `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`
  and `tests/test_gate.py::test_a_test_shaped_criterion_pinning_a_count_is_still_flagged`
  both still pass.
- `tests/test_gate.py::test_a_parenthesised_baseline_clause_is_not_flagged`,
  `tests/test_gate.py::test_a_count_pinned_before_a_baseline_clause_is_still_flagged`
  and `tests/test_gate.py::test_re_measured_is_not_read_as_a_baseline_marker`
  all pass.
- `uv run --group dev pytest -q` exits 0 and its summary line contains no
  `failed`. Measured before the fix, the only failure was the repro test named
  above.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.
- `grep -c 'acceptance criterion pins an absolute count' pipeline/core/gate.py`
  prints `2` -- the finding string and its `STRUCTURAL_MARKS` entry, unchanged
  by this ticket.
- `grep -c 'baseline clause' pipeline/stages/planning.md` prints `1`, so the
  prompt states the exemption DEC-030 requires it to state.

## Decisions

**The absolute-count check reads a criterion's ASSERTION clause, not the whole
criterion.** `assertion_clause()` in `pipeline/core/gate.py` cuts the criterion
at its baseline marker, and the count scan sees only what comes before.
`CRIT_COUNT_RULE` asks a criterion to state a relation to a measured baseline;
quoting that baseline's total is complying with the rule, and the scan flagged
the very evidence it asked for. TICKET-047 in the `chezzilang` project paid two
`structural_gate_failures` for exactly that.

**The marker opens a clause only at the start of a criterion or after one of
`.;:()[` or after `--`.** Not on a bare word boundary. `re-measured` is the
word the rule itself uses, and a bare boundary matches inside it, so every
criterion that re-measures would go unscanned -- the check deleted rather than
fixed. `tests/test_gate.py::test_re_measured_is_not_read_as_a_baseline_marker`
is the guard.

**The baseline clause runs to the END of the criterion. That is a deliberate
trade-off.** A baseline is quoted after the assertion it supports, so a total
stated before the marker is still scanned, and
`test_a_count_pinned_before_a_baseline_clause_is_still_flagged` holds that.
The cost: an assertion written after a baseline clause goes unscanned.
Sentence-level splitting was rejected because the quoted evidence itself
carries periods and colons -- `in 40.9 s.` and `done: 318 case(s)` -- so no
cheap sentence split is reliable.

**Excluding every backticked span was considered and rejected.** TICKET-111
offers it as a second option. It would silence a criterion reading ``
`pytest -q` prints `630 passed` ``, which is a genuine pinned total, and both
known false positives are baseline clauses. One exclusion, not two.

**`count-pinned:` remains the waiver and is unchanged (DEC-081).** It waives
the whole section for every criterion in it, which is why it is not the fix
for one criterion.

## Rollback

Revert the commit from step 7. The three files stand apart from the rest of the
dispatcher: `assertion_clause()` has one caller, and reverting restores the
scan over the whole criterion. The false positive returns; nothing else moves.
No data, no schema and no frontmatter field changes, so the revert needs no
migration and leaves no ticket in a bad state.

## Thread

### 2026-09-03 12:35:52Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-03 · triage · ok

Reproduced. `test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged`
in `tests/test_gate.py`, committed as `164148c` on `ticket/111`, fails with
`acceptance criterion pins an absolute count copied from `## Digest` (318)`
for a criterion whose only shared number is inside its "Measured on the
prototype:" clause and which re-measures the value under test via `wc -l`.
The existing blocking test still passes.

Expected files for the fix: `pipeline/core/gate.py` (the scan at line 820),
per the ticket's own suggestion of scanning only the assertion clause.
Verdict is `ok`, not `chore`: the fix requires choosing how to separate an
assertion clause from a baseline clause in `crits`, which is a design
choice left to `planning`.

### 2026-09-03 12:50:15Z · triage · session · session=be2a7ec4-8e29-4b86-9cb8-1f41496268eb

`triage` ran as session `be2a7ec4-8e29-4b86-9cb8-1f41496268eb`
- replay: `claude --resume be2a7ec4-8e29-4b86-9cb8-1f41496268eb`
- log: `.project/logs/TICKET-111-triage-be2a7ec4.log`
- cost: $0.44 of a $3 cap
- tokens: 7,446 out (1,130 thinking) · 46 in · 992,161 cache read · 42,268 cache write

### 2026-09-03 12:50:15Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- a criterion stating a relation to a measured baseline AND re-measuring the checked value is still flagged as pinning an absolute count

### 2026-09-03 · planning · ok

Plan written. The fix cuts a criterion at its baseline marker and scans only
the text before it: `assertion_clause()` plus `CRIT_BASELINE_RE` in
`pipeline/core/gate.py`, called from the count loop at line 820.

I prototyped the regex against the real `CRIT_COUNT_RE` before writing the
plan. On the repro criterion it drops `318`; on both criteria the existing
blocking tests use it keeps `630`; on `- the run is measured at 630 passed` it
keeps `630`, because a mid-sentence `measured` opens no clause.

Baseline measured on `ticket/111` at 164148c: `uv run --group dev pytest -q
tests/test_gate.py` prints `1 failed, 80 passed in 3.34s`, the one failure
being the repro test.

Scope note, for a later ticket and not for this one: the ticket's second
option -- exempting a backticked span that quotes captured output -- is
rejected in `## Decisions`, because it would also silence a criterion
asserting that a command prints `630 passed`.

`pipeline/stages/planning.md` is not in `machine.FENCED`, so step 6 does not
park this ticket at `awaiting-merge`. `.project/stages/planning.extra.md`
already permits a measured baseline and needs no edit.

### 2026-09-03 12:57:37Z · planning · session · session=0ca9d4f5-90c0-418d-8ac0-15dc8eb8ad3d

`planning` ran as session `0ca9d4f5-90c0-418d-8ac0-15dc8eb8ad3d`
- replay: `claude --resume 0ca9d4f5-90c0-418d-8ac0-15dc8eb8ad3d`
- log: `.project/logs/TICKET-111-planning-0ca9d4f5.log`
- cost: $2.58 of a $10 cap
- tokens: 34,582 out (12,724 thinking) · 56 in · 1,711,071 cache read · 86,241 cache write

### 2026-09-03 12:57:37Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: scan only the assertion clause -- cut a criterion at its baseline marker before the absolute-count check

### 2026-09-03 12:58:22Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged` fails as required
```
set_digest(
            "- the sweep takes 40.9 s on release for 318 cases\n"
            "- eviction runs on write, not read\n"
            "- thing.py holds it\n").replace(
            "- `test_broken` passes",
            "- `test_broken` passes\n"
            "- the test count equals `ls judge/problems/*/samples/*.in | wc -l` "
            "re-measured at that moment. Measured on the prototype: "
            "`done: 318 case(s), 0 failure(s)` in 40.9 s."))
        ok, failures = gate(d, "TICKET-001")
>       assert ok, failures
E       AssertionError: ['acceptance criterion pins an absolute count copied from `## Digest` (318): - the test count equals `ls judge/problem...re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check']
E       assert False

tests/test_gate.py:599: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: `tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged` fails on base `main` too -- the bug is not already fixed upstream
```
   AssertionError: ['acceptance criterion pins an absolute count copied from `## Digest` (318): - the test count equals `ls judge/problem...re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check']
E       assert False

tests/test_gate.py:599: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.32s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-owigx1qh/base
      Built pipeline @ file:///tmp/pipeline-base-owigx1qh/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-09-03 · plan-validation · ok

Plan passes all eight items.
long: eight scored items, one line each, plus one note and the unverified line.

- Root cause: the count loop runs `CRIT_COUNT_RE.findall(c)` over the whole
  joined criterion, so a total quoted as evidence reads as a pinned assertion.
  The plan cuts that string at the baseline marker and still scans the
  assertion, so it fixes the cause, not the test.
- Decisions: DEC-081 requires the check to keep its own loop above the
  names-a-test loop, the count noun after the number, and `count-pinned:` as
  the waiver. Step 4 changes one line inside that loop; all three hold.
  DEC-030 requires the `pipeline/stages/planning.md` copy to move with the
  rule, and step 6 moves it.
- Scope: all seven steps trace to a criterion. Steps 2, 5 and 7 change no file.
- Criteria: falsifiable. `test_a_count_pinned_before_a_baseline_clause_is_still_flagged`
  and `test_re_measured_is_not_read_as_a_baseline_marker` fail against a marker
  on a bare word boundary, or against a cut at the first `:`.
- Research: steps 3 and 4 name the file, the constant, the function and the
  exact line text to replace.
- Riskiest step: 3, the regex. Fallback: `## Rollback` reverts one commit and
  `assertion_clause()` has one caller; `## Decisions` names the rejected
  alternative.
- Regression: `tests/test_dispatch.py:1780` asserts the finding prefix
  classifies as structural. Step 4 keeps the finding byte-identical and step 7
  runs the whole suite.
- Blast radius: `bugfix`, 3 files, one replaced line plus one new function.

I hand-traced `CRIT_BASELINE_RE` over all five criteria against the real
`CRIT_COUNT_RE` at `pipeline/core/gate.py:62-72`. It cuts the repro criterion
before `318` and cuts neither blocking criterion.

Note, not a finding: the pattern's `^` arm never fires, because `CRIT_ITEM_RE`
makes every criterion start with its list marker. Behaviour is unaffected.

unverified: I executed neither the regex nor the suite. The guard blocks
`python -c` and command substitution at this stage. Every item above rests on
reading `pipeline/core/gate.py` and hand-tracing it.

### 2026-09-03 13:01:40Z · plan-validation · session · session=4b59314e-5aad-4dd2-8bd6-e168f67e3af0

`plan-validation` ran as session `4b59314e-5aad-4dd2-8bd6-e168f67e3af0`
- replay: `claude --resume 4b59314e-5aad-4dd2-8bd6-e168f67e3af0`
- log: `.project/logs/TICKET-111-plan-validation-4b59314e.log`
- cost: $1.25 of a $3 cap
- tokens: 15,929 out (9,217 thinking) · 28 in · 612,916 cache read · 54,215 cache write

### 2026-09-03 13:01:40Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items: cutting a criterion at its baseline marker fixes the root cause, DEC-081 and DEC-030 hold, and I hand-traced CRIT_BASELINE_RE over all five criteria

### 2026-09-03 16:45:13Z · human · note · by=chezzijr

**note from chezzijr**

Plan gate reviewed by Claude on chezzijr's instruction (they are asleep). Checked: assertion_clause() truncates at the baseline marker only when it opens a clause (start, after .;:()[ or --), so 're-measured' is not a marker; two falsifiers kept (a count pinned BEFORE the baseline still fails; the existing block test still fails); the finding string and CRIT_COUNT_RULE stay byte-identical, so STRUCTURAL_MARKS is untouched. Accepted ceiling: a criterion that states its assertion AFTER the word 'Measured' goes unscanned. Approving.

### 2026-09-03 16:45:13Z · human · approval · by=claude-for-chezzijr

**approved by claude-for-chezzijr**

### 2026-09-03 17:12:49Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged` fails as required
```
set_digest(
            "- the sweep takes 40.9 s on release for 318 cases\n"
            "- eviction runs on write, not read\n"
            "- thing.py holds it\n").replace(
            "- `test_broken` passes",
            "- `test_broken` passes\n"
            "- the test count equals `ls judge/problems/*/samples/*.in | wc -l` "
            "re-measured at that moment. Measured on the prototype: "
            "`done: 318 case(s), 0 failure(s)` in 40.9 s."))
        ok, failures = gate(d, "TICKET-001")
>       assert ok, failures
E       AssertionError: ['acceptance criterion pins an absolute count copied from `## Digest` (318): - the test count equals `ls judge/problem...re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check']
E       assert False

tests/test_gate.py:599: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.33s ===============================

```
- ok: `tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged` fails on base `main` too -- the bug is not already fixed upstream
```
   AssertionError: ['acceptance criterion pins an absolute count copied from `## Digest` (318): - the test count equals `ls judge/problem...re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check']
E       assert False

tests/test_gate.py:599: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.53s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-6v_55vkg/base
      Built pipeline @ file:///tmp/pipeline-base-6v_55vkg/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 33ms

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-09-03 17:12:49Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-04 · implementing · todo

**Todo list**

1. [ ] Add 3 tests to `tests/test_gate.py` after `test_a_count_pinned_line_waives_the_absolute_count_check`.
2. [ ] Run the new tests, confirm 2 fail with `acceptance criterion pins an absolute count`, 2 pass.
3. [ ] Add `CRIT_BASELINE_RE` and `assertion_clause()` to `pipeline/core/gate.py`.
4. [ ] Replace the `shared = sorted(...)` line in the count loop with the two-line version.
5. [ ] Run full `tests/test_gate.py`, confirm no failures.
6. [ ] Append the baseline-clause sentence to `pipeline/stages/planning.md`.
7. [x] Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, commit.

### 2026-09-04 · implementing · done

**Plan executed, all 7 steps done.**

- Added 3 tests to `tests/test_gate.py`: RED confirmed --
  `test_a_criterion_stating_a_relation_and_a_baseline_is_not_flagged` and
  `test_a_parenthesised_baseline_clause_is_not_flagged` failed with
  `acceptance criterion pins an absolute count`; the other two new tests
  passed already, as the plan expected.
- Added `CRIT_BASELINE_RE` and `assertion_clause()` to `pipeline/core/gate.py`,
  changed the count loop to scan `assertion_clause(c)` instead of `c`.
- `uv run --group dev pytest -q tests/test_gate.py` -> `86 passed in 3.01s`.
- Appended the baseline-clause sentence to `pipeline/stages/planning.md`.
- `grep -c 'acceptance criterion pins an absolute count' pipeline/core/gate.py`
  -> `2`. `grep -c 'baseline clause' pipeline/stages/planning.md` -> `1`.
- `uv run --group dev pytest -q` -> `537 passed in 55.99s`.
  `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`.
- Committed `a64ffd1`: `pipeline/core/gate.py`, `tests/test_gate.py`,
  `pipeline/stages/planning.md`.

result: ok

### 2026-09-03 17:15:44Z · implementing · session · session=79b338be-cc04-42fa-81f0-6dd2a8d82fd1

`implementing` ran as session `79b338be-cc04-42fa-81f0-6dd2a8d82fd1`
- replay: `claude --resume 79b338be-cc04-42fa-81f0-6dd2a8d82fd1`
- log: `.project/logs/TICKET-111-implementing-79b338be.log`
- cost: $0.49 of a $8 cap
- tokens: 7,931 out (364 thinking) · 44 in · 1,100,447 cache read · 48,203 cache write

### 2026-09-03 17:15:44Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added assertion_clause()/CRIT_BASELINE_RE, cut the count scan there, updated planning.md, all tests green, committed a64ffd1.

### 2026-09-04 · review · ok

**Reviewed the delta `main...HEAD` (`8ba7e16`, `a64ffd1`): no blocking findings.**

Every acceptance criterion holds, measured fresh:
- `uv run --group dev pytest -q tests/test_gate.py` -> `86 passed in 2.96s`.
  The 6 named tests, run alone -> `6 passed, 80 deselected in 0.22s`.
- `uv run --group dev pytest -q` -> `537 passed in 55.59s`, exit 0.
- `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`, exit 0.
- `grep -c 'acceptance criterion pins an absolute count' pipeline/core/gate.py`
  -> `2`; `grep -c 'baseline clause' pipeline/stages/planning.md` -> `1`.

No drift from `## Plan`. The diff touches only the 3 planned files,
`assertion_clause()` has one caller (`pipeline/core/gate.py:876`), the count
loop stays above the names-a-test loop (DEC-081), and `CRIT_COUNT_RULE` plus
the finding prefix are byte-identical. `pipeline/stages/planning.md` is not in
`FENCED` (`pipeline/core/machine.py:43-60`).

Non-blocking findings:

1. nit. The `^` branch of `CRIT_BASELINE_RE` is unreachable for a `-` or `*`
   criterion: `crits` keeps the bullet (`pipeline/core/gate.py:864`), so
   `- Measured on main: 630 passed` is still scanned. Stricter, never looser.
2. nit. A continuation line joins with a space (`pipeline/core/gate.py:862`),
   so a baseline opening a continuation line matches no marker. Same direction.

Two charges dropped. "A count stated after a baseline goes unscanned" is the
trade-off `## Decisions` states and the human note of 2026-09-03 16:45:13Z
approves. "`re-measured` reads as a marker" is refuted by
`tests/test_gate.py::test_re_measured_is_not_read_as_a_baseline_marker`, which
passes and asserts the criterion is still flagged.

result: ok

### 2026-09-03 17:20:23Z · review · session · session=405beae9-96f7-4171-862b-003a520bbbf0

`review` ran as session `405beae9-96f7-4171-862b-003a520bbbf0`
- replay: `claude --resume 405beae9-96f7-4171-862b-003a520bbbf0`
- log: `.project/logs/TICKET-111-review-405beae9.log`
- cost: $1.34 of a $4 cap
- tokens: 15,019 out (7,239 thinking) · 42 in · 906,925 cache read · 51,259 cache write

### 2026-09-03 17:20:23Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed a64ffd1 and 8ba7e16: every acceptance criterion holds, 537 passed, guard green; 2 non-blocking nits appended.

### 2026-09-03 17:21:03Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-04 01:48:36Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/111


Rebasing (1/2)Rebasing (2/2)Successfully rebased and updated refs/heads/ticket/111.
Already up to date.
Updating d983536..0e4c455
Fast-forward
 pipeline/core/gate.py       | 18 ++++++++++++-
 pipeline/stages/planning.md |  3 +++
 tests/test_gate.py          | 64 +++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 84 insertions(+), 1 deletion(-)

```

### 2026-09-04 01:48:36Z · merging · decision

decision recorded as `DEC-111`
