---
id: TICKET-081
stage: done
class: bugfix
branch: ticket/081
test_file: tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest
files_declared:
- pipeline/core/gate.py
- pipeline/stages/planning.md
- tests/test_dispatch.py
- tests/test_gate.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 14
  plan_files: 4
  no_result: 0
  plan_rejections: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 306c5553-a980-498c-9dcf-45d2df1bab52
  log: .project/logs/TICKET-081-review-306c5553.log
approved_by: chezzijr (via Claude Code, while away; reviewer also filed this ticket
  and rejected its first plan -- audit in thread). Verified gate.py:426 is still 'for
  c in crits:' and gate.py has not moved since 079.
approved_at: '2026-08-27T18:19:10.027230+00:00'
---

## Summary

Implemented. `gate()` (`pipeline/core/gate.py`) now runs a check for a
criterion that pins an absolute count copied from `## Digest`, in its own
loop above `for c in crits:` (not inside it, per the rejection). Four new
constants (`COUNT_RE`, `CRIT_COUNT_RE`, `COUNT_PINNED_RE`, `CRIT_COUNT_RULE`),
one `STRUCTURAL_MARKS` entry, five new tests in `tests/test_gate.py`, one in
`tests/test_dispatch.py`, and two sentences added to
`pipeline/stages/planning.md`. Three commits: `f279bef` (check + tests),
`16fc48b` (STRUCTURAL_MARKS + structural test), `c6e3b65` (planning.md docs).

All 9 acceptance criteria pass, re-run at review:
`uv run --group dev pytest -q` reports `382 passed`, the step 1 baseline of
376 plus 6; `./pipeline/hooks/test_dangerous_commands.py` exits 0;
`grep -c count-pinned pipeline/stages/planning.md` prints `1`.

One deviation from the plan's stated expectation, not from its instructions:
step 12 says the structural filter returns `2 passed`; it returns `3 passed`,
because the pre-existing
`test_a_tier_b_rejection_charges_the_plan_not_the_structural_counter` also
matches `-k structural`. No test was edited.

Review passed on 2026-08-28 with no blocking finding. I reviewed the delta
`main...HEAD` -- 4 commits, 122 insertions, 0 deletions -- and re-ran every
acceptance criterion. The rejection's finding is resolved: the check sits in
its own loop at `gate.py:462`, above `for c in crits:` at `gate.py:467`, and
`test_a_test_shaped_criterion_pinning_a_count_is_still_flagged` guards it.
Three non-blocking nits are in the thread; none asks for rework.

## Reproduction

`tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`
builds a fixture whose `## Digest` reads `- 630 passed in tests/chz` and whose
`## Acceptance criteria` adds `` - `tests/chz` suite: 630 passed `` alongside
the fixture's normal `` - `test_broken` passes ``. `gate()` returns `ok=True`
with `failures=[]`: no check flags a criterion that copies an absolute count
out of `## Digest`.

Command: `uv run --group dev pytest -q tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`

expect: AssertionError: []

## Digest

- `pipeline/core/gate.py` is the only source file this change touches. `gate()`
  (line 209) already reads both sections the check needs:
  `dig = secs.get("Digest", "")` (line 234) and
  `crit = secs.get("Acceptance criteria", "")` (line 397).
- The criteria scan builds the `crits` list (lines 398-425), joining an
  indented continuation onto the criterion above it (DEC-054). The loop
  `for c in crits:` (line 426) is the names-a-test check.
- **The rejection's finding, confirmed.** TICKET-079 rewrote that loop's body.
  Both accept paths now `continue` (lines 435-438): first the test-shaped
  regex, then `CRIT_CMD_RE` plus `CRIT_OUTCOME_RE`. A check appended after
  `findings.append(f"acceptance criterion names no test: ...")` sees only
  criteria that already failed. The fixture criterion
  `` - `tests/chz` suite: 630 passed `` matches `\btests?/` and continues.
  I built that placement in a scratch checkout of `main` and ran the five
  tests of steps 2-5: `2 failed, 3 passed`, with
  `test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` and
  `test_a_test_shaped_criterion_pinning_a_count_is_still_flagged` both failing
  `AssertionError: []`. The check therefore gets its own loop over `crits`,
  placed above line 426.
- `STRUCTURAL_MARKS` (line 68) is a `startswith` allowlist;
  `"acceptance criterion names no test",` is line 78. A finding that is not
  listed reads as substantive and charges `plan_validation_attempts` instead
  of `structural_gate_failures` (DEC-065).
- `CRIT_ITEM_RE` (line 45) is the last constant before the TICKET-079 block
  that opens `# A criterion clears Tier A by naming a test`; the four new
  constants go between them. `DIGEST_SHORT_RE` (line 23) is the precedent for
  the waiver line, and `PLAN_STEP_RULE` (line 30) for a rule string that
  paraphrases `pipeline/stages/planning.md`.
- Measured today against the patched gate over the 83 tickets in
  `.project/tickets`: 469 criteria, 27 flagged by a shared bare integer, 3 by
  `CRIT_COUNT_RE` -- `16 passed` and `176 passed` in TICKET-021, `127 ok
  lines` in TICKET-057. All 3 are the defect. `COUNT_RE` rejects `2.1.238`,
  `gate.py:411`, `DEC-065`, `10ms`, `exit 0` and `v1.2.3`; `CRIT_COUNT_RE`
  additionally rejects `step 12`, `README.md line 65` and `port 8080 open`.
- Verified end to end in a scratch checkout of `main` with the patch of steps
  7-8 applied: `uv run --group dev pytest -q` reports `373 passed`, which is
  `main`'s own count plus the pinning test plus the four tests of steps 2-5.
- Gotcha (DEC-017): `tests/test_gate.py` is copied onto a checkout of base and
  imported there, so it must not import a name that exists only on this
  branch. The new tests use only the already-imported `gate`, `project`,
  `FIXTURE` and the file-local `_set_digest` (line 14). The `structural_only`
  test goes in `tests/test_dispatch.py` with a function-local import, exactly
  as `test_structural_only_classifies_a_gate_finding` (line 1324) does.
- Gotcha: a line in `## Acceptance criteria` that does not match
  `CRIT_ITEM_RE` is not collected as a criterion, so a bare `count-pinned:`
  line raises no `names no test` finding of its own. Verified by the step 2
  test passing.
- Gotcha (DEC-079): `CRIT_RULE` must not contain the word `pytest`, because
  `tests/test_gate.py::test_a_whole_suite_criterion_naming_pytest_is_accepted`
  asserts no finding does. `CRIT_COUNT_RULE` contains no `pytest` either.
- `FIXTURE` in `tests/helpers.py` has a `## Digest` with no digits in it, which
  is what makes the step 4 test a real negative.
- Neither `pipeline/core/gate.py` nor `pipeline/stages/planning.md` is in
  `machine.FENCED`, so this ticket does not park at `awaiting-merge`.

## Decisions checked

- DEC-079 (active) -- the criterion check has two OR'd accept arms, each ending
  in `continue`. This is why the count check cannot live in that loop. The
  finding prefix `acceptance criterion names no test` must stay unchanged;
  this plan adds a second prefix and edits neither the first nor `CRIT_RULE`.
- DEC-054 (active) -- a criterion is its marker line plus every line indented
  under it. The new loop runs on the joined criterion in `crits`, not on a raw
  line, so a count on a continuation line is still seen.
- DEC-042 (superseded by DEC-054; history) -- `CRIT_ITEM_RE` is the one place
  that decides what a criterion line is. This plan does not change it.
- DEC-016 (active) -- fence state is parsed once, in `_fenced()`. The new loop
  adds no scan of its own; it reads the `crits` list the existing scan built.
- DEC-065 (active) -- `structural_only()` is an allowlist matched with
  `startswith`. Step 10 adds the prefix of the new finding, or that finding
  charges the wrong counter.
- DEC-017 (active) -- `tests/test_gate.py` is copied onto base and imported
  there. This is why the test in step 11 lives in `tests/test_dispatch.py`.
- DEC-030 (active) -- a Tier A finding states the rule that would fix it, and
  the duplication between `pipeline/core/gate.py` and
  `pipeline/stages/planning.md` is deliberate. `CRIT_COUNT_RULE` follows both.
- DEC-057 and DEC-058 (both active) -- the guard-case count in `CLAUDE.md` is
  asserted by
  `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases`, and
  DEC-058 moved it from 109 to 122. That is a legitimate pinned count in a
  criterion, and it is why this plan adds a waiver rather than a hard reject.

Grep terms used against `.project/decisions/`: `criteri`, `criterion`,
`Digest`, `digest`, `count`, `integer`, `stale`, `STRUCTURAL_MARKS`,
`superseded-by`.

## Plan

1. Confirm the tree and record the baseline: run `grep -c CRIT_CMD_RE pipeline/core/gate.py` and expect at least 1, which proves the rebase onto base landed TICKET-079 and that every line number in this plan applies; then run `uv run --group dev pytest -q` and `uv run --group dev pytest -q tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`, and write into `## Thread` the suite's passing count and the `1 failed` line with `AssertionError: []` for the single test, which is already in `tests/test_gate.py` from commit `27dedd1`.
2. Add `test_a_count_pinned_line_waives_the_absolute_count_check` to `tests/test_gate.py` directly below `test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`, importing nothing new (DEC-017): `d = project(_set_digest("- thing.py holds it\n- 630 passed in tests/chz\n- eviction runs on write, not read\n").replace("- `test_broken` passes", "count-pinned: this ticket is what moves the number\n- `test_broken` passes\n- `tests/chz` suite: 630 passed"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert ok, failures`, then `shutil.rmtree(d)`; its docstring says a bare `count-pinned:` line does not match `CRIT_ITEM_RE` and so raises no `names no test` finding of its own.
3. Add `test_a_number_a_criterion_refers_to_but_does_not_count_is_not_flagged` to `tests/test_gate.py` below the test from step 2: `d = project(_set_digest("- thing.py holds it\n- README.md line 65 names it\n- eviction runs on write, not read\n").replace("- `test_broken` passes", "- `test_broken` passes, and `README.md` line 65 still names it"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert ok, failures`, then `shutil.rmtree(d)`; its docstring says the count noun follows the number in a count and precedes it in a reference, so a shared integer alone must not flag.
4. Add `test_a_count_a_criterion_measures_itself_is_not_flagged` to `tests/test_gate.py` below the test from step 3, using the unmodified `FIXTURE` whose `## Digest` holds no digits: `d = project(FIXTURE.replace("- `test_broken` passes", "- `test_broken` passes and `pytest -q` reports 630 passed"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert ok, failures`, then `shutil.rmtree(d)`; its docstring says a count that appears in no `## Digest` line was not copied out of the digest.
5. Add `test_a_test_shaped_criterion_pinning_a_count_is_still_flagged` to `tests/test_gate.py` below the test from step 4 -- this is the test the rejection asked for: `d = project(_set_digest("- thing.py holds it\n- 630 passed in tests/chz\n- eviction runs on write, not read\n").replace("- `test_broken` passes", "- `tests/test_x.py::test_suite` passes and the suite reports 630 passed"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert not ok and any("absolute count" in f for f in failures), failures`, then `shutil.rmtree(d)`; its docstring says pinning a total and naming a test are orthogonal, so this fails against any check placed inside `for c in crits:`.
6. Run `uv run --group dev pytest -q tests/test_gate.py -k "absolute_count or does_not_count or measures_itself or count_pinned or test_shaped_criterion_pinning"` and expect `2 failed, 3 passed`: the pinning test and the step 5 test assert `not ok`, the other three assert `ok`, and a gate with no check returns `ok=True`; record that line in `## Thread`, and record that each of the three passing tests guards a distinct wrong regex -- the step 3 test fails if the count-noun requirement drops, the step 2 test fails if the `COUNT_PINNED_RE` skip drops, the step 4 test fails if the check ignores `dig_counts` membership.
7. Add four constants to `pipeline/core/gate.py` between `CRIT_ITEM_RE` (line 45) and the comment `# A criterion clears Tier A by naming a test` (line 47), each with a comment in the style of the file: `COUNT_RE = re.compile(r"(?<![\w.:/-])(\d{2,})(?![\w.:/-])")`, commented as the `## Digest` side, with two digits as the floor because a one-digit number in a criterion is an exit code or an ordinal far more often than a measured total, and lookarounds that reject `2.1.238`, `gate.py:411`, `DEC-065` and `10ms`; `CRIT_COUNT_RE = re.compile(COUNT_RE.pattern + r"[^A-Za-z0-9]{0,3}(?:pass(?:ed|es|ing)|fail(?:ed|s|ing|ures?)|tests?|cases?|rows?|lines?|entries|files?|criteria|steps?|ok)\b", re.I)`, commented as the criterion side requiring the noun to FOLLOW the number because the noun precedes it in a reference such as `step 12` or `README.md line 65`, and recording that over the 83 tickets in `.project/tickets` on 2026-08-28 the bare integer flagged 27 of 469 criteria and this form flagged 3, all 3 the defect; `COUNT_PINNED_RE = re.compile(r"^\s*count-pinned:\s*\S", re.M)`, commented as the waiver, spelled like `DIGEST_SHORT_RE`; and `CRIT_COUNT_RULE`, a plain string reading `a total any other ticket can move is not a property of this change -- state it as a relation to a measured baseline, or re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check`, commented as paraphrasing `pipeline/stages/planning.md` and changing with it, like `PLAN_STEP_RULE` (DEC-030).
8. Add the check to `gate()` in `pipeline/core/gate.py` as its own loop, inserted immediately above `for c in crits:` (line 426) and never inside it: `dig_counts = set(COUNT_RE.findall(dig))`, then `if dig_counts and not COUNT_PINNED_RE.search(crit):`, then `for c in crits:`, then `shared = sorted(set(CRIT_COUNT_RE.findall(c)) & dig_counts, key=int)`, then `if shared:`, then a `findings.append()` of `"acceptance criterion pins an absolute count copied from `## Digest` (%s): %s -- %s" % (", ".join(shared), c, CRIT_COUNT_RULE)`; comment the loop with the reason it is not folded into the one below -- pinning a stale total and naming a test are orthogonal properties, and the loop below `continue`s on every criterion that names a test, so a check inside it would only ever see criteria that already fail the names-no-test rule.
9. Run `uv run --group dev pytest -q tests/test_gate.py` after the edits to `pipeline/core/gate.py`, expect zero failures, and commit steps 2 to 8 as `feat(TICKET-081): gate rejects a criterion pinning an absolute count from the digest`.
10. Add the line `"acceptance criterion pins an absolute count",` to `STRUCTURAL_MARKS` in `pipeline/core/gate.py`, directly after `"acceptance criterion names no test",` (line 78), so the finding charges `structural_gate_failures` rather than `plan_validation_attempts` (DEC-065).
11. Test step 10 in `tests/test_dispatch.py`, never in `tests/test_gate.py` (DEC-017): add `test_an_absolute_count_finding_is_structural` below `test_structural_only_classifies_a_gate_finding` (line 1324), with a function-local `from pipeline.core.gate import structural_only`, asserting `structural_only()` returns True for a one-item list holding a finding that opens ``acceptance criterion pins an absolute count copied from `## Digest` (630):``.
12. Run `uv run --group dev pytest -q tests/test_dispatch.py -k structural` after the edit to `tests/test_dispatch.py`, expect `2 passed`, and commit steps 10 and 11 as `feat(TICKET-081): the absolute-count finding is structural`.
13. Document the rule in `pipeline/stages/planning.md` by appending two sentences to the `## Acceptance criteria` bullet, after its last line `line reads as a criterion of its own and is checked alone.` (line 79) and keeping that bullet's two-space continuation indent: a total any other ticket can move, such as the pass count of a suite or a number of open rows, is not a property of this change, so state it as a relation to a baseline you measured or have the criterion re-measure at check time; the gate rejects a criterion that copies an absolute count out of `## Digest`, and one `count-pinned: <why it cannot move>` line in the section waives that check.
14. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py` from the worktree root after the edit to `pipeline/stages/planning.md`, expect zero failures with a passing count of the step 1 baseline plus 6, expect the guard script to exit 0, and commit step 13 as `docs(TICKET-081): planning states a count as a delta, not a literal`.

## Acceptance criteria

1. `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`
   passes, and step 1 recorded it failing with `AssertionError: []` before step 8.
2. `tests/test_gate.py::test_a_test_shaped_criterion_pinning_a_count_is_still_flagged`
   passes: a criterion naming a test node id and pinning a digest total is
   still flagged. This is the rejection's finding, and it fails against any
   check placed inside `for c in crits:`.
3. `tests/test_gate.py::test_a_count_pinned_line_waives_the_absolute_count_check`
   passes: the pinning fixture plus one `count-pinned:` line gates `ok=True`.
4. `tests/test_gate.py::test_a_number_a_criterion_refers_to_but_does_not_count_is_not_flagged`
   passes: `README.md line 65` in both sections raises no finding.
5. `tests/test_gate.py::test_a_count_a_criterion_measures_itself_is_not_flagged`
   passes: a count that appears in no `## Digest` line raises no finding.
6. `tests/test_dispatch.py::test_an_absolute_count_finding_is_structural`
   passes, so a plan carrying only this finding charges
   `structural_gate_failures`.
7. `uv run --group dev pytest -q` reports zero failures, and its passing count
   equals the baseline step 1 recorded plus 6 -- the pinning test flips from
   failed to passed, and five tests are new. Stated as a delta on purpose: a
   sibling ticket may move the baseline before this is checked.
8. `./pipeline/hooks/test_dangerous_commands.py` exits 0 and prints no failing
   case.
9. `grep -c count-pinned pipeline/stages/planning.md` prints at least 1, and
   `uv run --group dev pytest -q tests/test_stages.py` reports zero failures,
   so the prompt edit breaks no assertion about the stage prompts.

## Decisions

**The absolute-count check runs in its own loop over `crits`, above the
names-a-test loop. Never inside it.** TICKET-079 gave that loop two accept
arms, and both end in `continue` -- a test-shaped token, or `CRIT_CMD_RE` plus
`CRIT_OUTCOME_RE`. A check appended to that loop's body sees only criteria
that already failed the names-no-test rule, which is the opposite of the
population this check is for: a criterion that names a test perfectly well and
still pins a number a sibling ticket moves. The two properties are orthogonal
and the code keeps them apart.
`tests/test_gate.py::test_a_test_shaped_criterion_pinning_a_count_is_still_flagged`
is the guard; it fails if anyone folds the check back in.

**The check is deterministic and lives in `gate()`, not in a stage prompt.**
The ticket says "a Tier B check", but its reproduction test asserts on the
return value of `gate()`. The rule added to `pipeline/stages/planning.md`
documents that same check; it is not a second mechanism, and DEC-030 says to
keep the two copies and change them together.

**The count noun must FOLLOW the number.** `630 passed` is a count; `step 12`
and `README.md line 65` are references. Measured over the 83 tickets in
`.project/tickets` on 2026-08-28: 469 criteria, 27 flagged by any shared bare
integer, 3 by the noun-after form -- `16 passed` and `176 passed` in
TICKET-021, `127 ok lines` in TICKET-057, whose number DEC-058 later moved to
122. Loosen this to any shared integer and the gate blocks roughly one
criterion in seventeen for citing a line number.

**Two digits is the floor.** A one-digit number in a criterion is an exit
code, an ordinal or a count of 1 far more often than a measured total. A
single-digit total goes unflagged; that is the accepted cost of not blocking
`exit 0`.

**`count-pinned:` is a waiver, not a bypass.** Some counts are legitimately
pinned: the guard-case number in `CLAUDE.md` is asserted by
`tests/test_stages.py::test_the_rule_file_counts_the_guard_cases`, and DEC-058
moved it from 109 to 122 in the very ticket that changed the tables. A hard
reject would make that ticket unplannable. The waiver is one line, inside the
section, where a human reviewing the plan sees it -- the same shape as
`digest-short:`.

**The cross-file invariant is deliberately out of scope.** A criterion cannot
assert that a count in one file and a table in another agree unless somebody
writes that check, and the gate cannot know which two files a given project
expects to agree. It needs a project-supplied command, which is a different
mechanism from a regex over two ticket sections. What this ticket does for
that case is make a plan state such a count as a delta, which is what would
have caught the six-apart drift at planning time.

**A new structural finding needs its own `STRUCTURAL_MARKS` prefix**
(DEC-065). Without step 10 the finding reads as substantive and charges
`plan_validation_attempts`, which bounds bad plans, instead of
`structural_gate_failures`, which bounds bad formatting. The existing prefix
`acceptance criterion names no test` is untouched, per DEC-079.

## Rollback

Revert the three commits from steps 9, 12 and 14. The change is additive: four
module constants, one new loop above the existing `for c in crits` loop, one
`STRUCTURAL_MARKS` entry, five tests, and two sentences of prompt prose.
Nothing existing is rewritten, so a revert restores the previous gate exactly.
If only the false-positive rate turns out wrong, revert the loop from step 8
alone and keep the tests: they then fail, which is the correct signal.

## Thread

### 2026-08-27 16:15:56Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-28 · triage · result=ok

Reproduced. `gate()` in `pipeline/core/gate.py` scans `## Acceptance
criteria` (around line 411) for a test-shaped token but has no check for a
bare integer that also appears in `## Digest`. Added
`tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`,
committed on this branch (`27dedd1`). It builds a fixture whose `## Digest`
holds `- 630 passed in tests/chz` and whose criteria repeat `630 passed`, and
asserts `gate()` returns a finding containing "absolute count". Today it
returns `ok=True, failures=[]` -- confirmed miss.

This is not a `chore`: the ticket names two open design choices (Tier B
integer-vs-Digest check, and/or a `pipeline/stages/planning.md` rule to state
counts as a delta) and an unresolved cross-file half (an invariant spanning
two files has no check-writer named yet). Planning should pick one approach,
not both, and decide whether the cross-file case is in scope for this ticket
or deferred.

### 2026-08-27 17:28:56Z · triage · session · session=e8683317-5f6c-4fdf-a155-38075fc33813

`triage` ran as session `e8683317-5f6c-4fdf-a155-38075fc33813`
- replay: `claude --resume e8683317-5f6c-4fdf-a155-38075fc33813`
- log: `.project/logs/TICKET-081-triage-e8683317.log`

### 2026-08-27 17:28:56Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- gate() has no Tier B check for a criterion pinning an absolute count from Digest

### 2026-08-28 · planning · result=ok

Plan written. Scope: one Tier A check in `gate()`, plus the matching rule in
`pipeline/stages/planning.md`. Triage asked planning to pick one of the two
approaches. The prompt rule documents the gate check rather than adding a
second mechanism, so this is one approach.

The cross-file half is deferred; the reason is in `## Decisions`. A criterion
cannot assert a two-file invariant unless somebody writes that check, and the
gate cannot know which two files a project expects to agree. That needs a
project-supplied command, and it is a separate ticket. Nothing in this plan
blocks it.

Measured the false-positive rate before choosing the regex, over the 446
acceptance criteria of this repo on 2026-08-28:

    any shared bare integer          26 criteria flagged
    number then a count noun          3 criteria flagged

All 3 are the defect: `16 passed` and `176 passed` in TICKET-021, and in
TICKET-057 the criterion `- ./pipeline/hooks/test_dangerous_commands.py exits
0, prints 127 ok lines`, whose number DEC-058 later moved to 122. The 23
dropped are references -- `step 12`, `README.md line 65`, a pyte width of
`120`.

### 2026-08-27 17:43:18Z · planning · session · session=aa8bd272-8c65-4f22-b45c-2268b9098d1c

`planning` ran as session `aa8bd272-8c65-4f22-b45c-2268b9098d1c`
- replay: `claude --resume aa8bd272-8c65-4f22-b45c-2268b9098d1c`
- log: `.project/logs/TICKET-081-planning-aa8bd272.log`

### 2026-08-27 17:43:18Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned a Tier A gate check: a criterion whose count is copied from ## Digest, with a count-pinned waiver; cross-file half deferred

### 2026-08-27 17:43:38Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` fails as required
```
       [33m"[39;49;00m[33m- `test_broken` passes[39;49;00m[33m"[39;49;00m,[90m[39;49;00m
            [33m"[39;49;00m[33m- `test_broken` passes[39;49;00m[33m\n[39;49;00m[33m- `tests/chz` suite: 630 passed[39;49;00m[33m"[39;49;00m))[90m[39;49;00m
        ok, failures = gate(d, [33m"[39;49;00m[33mTICKET-001[39;49;00m[33m"[39;49;00m)[90m[39;49;00m
>       [94massert[39;49;00m [95mnot[39;49;00m ok [95mand[39;49;00m [96many[39;49;00m([33m"[39;49;00m[33mabsolute count[39;49;00m[33m"[39;49;00m [95min[39;49;00m f [94mfor[39;49;00m f [95min[39;49;00m failures), failures[90m[39;49;00m
[1m[31mE       AssertionError: [][0m
[1m[31mE       assert (not True)[0m

[1m[31mtests/test_gate.py[0m:333: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest[0m - AssertionError: []
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.05s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` fails on base `main` too -- the bug is not already fixed upstream
```
     assert (not True)[0m

[1m[31mtests/test_gate.py[0m:333: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest[0m - AssertionError: []
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-dbeptmn8/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-dbeptmn8/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-08-28 · plan-validation · result=fail

Tier B: one item fails, seven pass.

**Step 5 predicts the wrong output.** It says `expect 2 failed, 2 passed: the
pinning test and the waiver test fail`. The waiver test passes before step 8:
a gate with no check returns `ok=True`, and the test asserts `ok`. I ran
`gate()` on the exact fixture step 2 builds:

```
WAIVER-SHAPE: (True, [])
```

Step 5 must expect `1 failed, 3 passed`. The waiver test is still a real test.
It fails against a step-8 check that omits the `COUNT_PINNED_RE` skip, which
step 5 already states.

Passing items:
1. Root cause: `gate()` compares no number in `## Acceptance criteria` against
   `## Digest`. The plan adds that comparison, not a special case for `630`.
2. Decisions: DEC-054, DEC-016, DEC-065, DEC-017, DEC-030 and DEC-057/058 all
   read as cited. DEC-058 line 26 does move the guard count 109 to 122.
3. Scope: 14 steps map to criteria 1 to 8. No step is untraceable.
4. Criteria: five named tests, each falsifiable.
5. Concrete: every line number cited resolves -- `CRIT_ITEM_RE` 45,
   `STRUCTURAL_MARKS` 53, `names no test` 63, `dig` 219, `crit` 382,
   `for c in crits:` 411, and `test_structural_only_classifies_a_gate_finding`
   1324.
6. Riskiest step is 6 plus 8, the regex. `## Rollback` states the fallback:
   revert the branch alone, keep the tests. I ran both proposed regexes.
   `630 passed`, `127 ok lines` and `16 passed` match; `step 12`,
   `README.md line 65 still names it`, `2.1.238`, `gate.py:411`, `DEC-065`
   and `10ms` do not.
7. Regression surface: every existing `tests/test_gate.py` case uses a
   `## Digest` holding no digits, so `dig_counts` is empty and the new branch
   is inert. Criterion 6 runs the whole suite.
8. Blast radius: bugfix, 4 files, one source file. It matches the class.

### 2026-08-27 17:47:20Z · plan-validation · session · session=53878aaf-7b31-4a14-8024-9104ed06a0a0

`plan-validation` ran as session `53878aaf-7b31-4a14-8024-9104ed06a0a0`
- replay: `claude --resume 53878aaf-7b31-4a14-8024-9104ed06a0a0`
- log: `.project/logs/TICKET-081-plan-validation-53878aaf.log`

### 2026-08-27 17:47:20Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ seven items pass; step 5 predicts 2 failed, 2 passed but the waiver test passes before step 8 -- gate() returns (True, []) on its fixture, so expect 1 failed, 3 passed

### 2026-08-28 · planning · result=ok

Replanned after the plan-validation failure. Step 5 changed; nothing else.

Step 5 now expects `1 failed, 3 passed` for
`uv run --group dev pytest -q tests/test_gate.py -k "absolute_count or
does_not_count or measures_itself"`. I ran `gate()` on the fixtures of steps
2, 3 and 4 against the current `pipeline/core/gate.py`:

    WAIVER-SHAPE: (True, [])
    REFERENCE-SHAPE: (True, [])
    SELF-MEASURED-SHAPE: (True, [])

Only `test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`
fails before step 8: it asserts `not ok`, while the other three assert `ok`.

Step 5 keeps its second sentence, reworded. Each of the three tests that pass
here guards a distinct wrong regex, and each fails against a step 8 check that
gets that part wrong.

`pyproject.toml` sets no pytest `addopts`, so the command is not `-x` and
reports all four outcomes on one line.

The other seven plan-validation items passed. `## Digest`,
`## Decisions checked`, `## Acceptance criteria`, `## Decisions` and
`## Rollback` are unchanged apart from the one new Digest bullet.

### 2026-08-27 17:49:25Z · planning · session · session=9e8e3d48-8c47-46af-8395-9499af348acd

`planning` ran as session `9e8e3d48-8c47-46af-8395-9499af348acd`
- replay: `claude --resume 9e8e3d48-8c47-46af-8395-9499af348acd`
- log: `.project/logs/TICKET-081-planning-9e8e3d48.log`

### 2026-08-27 17:49:25Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ step 5 now expects 1 failed, 3 passed; gate() returns (True, []) on the fixtures of steps 2, 3 and 4; nothing else changed

### 2026-08-27 17:49:45Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-27 17:43:38Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` fails on base `main` too -- the bug is not already fixed upstream
```
     assert (not True)[0m

[1m[31mtests/test_gate.py[0m:333: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest[0m - AssertionError: []
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-axh72___/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-axh72___/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-08-28 · plan-validation · result=ok

Tier B: eight items pass.

1. Root cause: `gate()` compares no number in `## Acceptance criteria` against
   `## Digest`, so a criterion holding an absolute total passes and goes stale
   when any ticket moves that total. The plan adds that comparison plus a
   waiver, not a special case for `630`.
2. Step 5 now predicts correctly. I ran `gate()` on the fixtures of steps 2, 3
   and 4 against the current `pipeline/core/gate.py`, and on the step 1 one:

```
WAIVER-SHAPE: (True, [])
REFERENCE-SHAPE: (True, [])
SELF-MEASURED-SHAPE: (True, [])
PINNING-SHAPE: (True, [])
```

   Three assert `ok` and pass; the pinning test asserts `not ok` and fails.
   `1 failed, 3 passed` holds, and `pyproject.toml` sets no `addopts`.
3. Decisions: DEC-054, DEC-016, DEC-065, DEC-017, DEC-030, DEC-057 and DEC-058
   carry no `superseded-by` marker; DEC-042 does, naming DEC-054. DEC-058
   line 26 reads "This ticket moved that number from 109 to 122".
4. Riskiest step is 6 plus 8, the regex. I re-measured it over the 83 tickets
   in `.project/tickets`: 463 criteria, 27 flagged by a shared bare integer,
   3 by `CRIT_COUNT_RE` -- `16 passed` and `176 passed` in TICKET-021, and
   `127 ok lines` in TICKET-057. `step 12`, `README.md line 65`, `2.1.238`,
   `gate.py:411`, `DEC-065`, `10ms` and `exit 0` match nothing. `## Rollback`
   states the fallback: revert the step 8 branch alone, keep the four tests.
5. Criteria: falsifiable. Each of the three passing tests fails against a
   distinct wrong step 8 -- the reference test if the noun requirement drops,
   the waiver test if the `COUNT_PINNED_RE` skip drops, the self-measured test
   if the check ignores `dig_counts` membership.
6. Concrete: every cited line resolves -- `CRIT_ITEM_RE` 45,
   `STRUCTURAL_MARKS` 53, `names no test` 63, `crit` 382, `for c in crits:`
   411, the pinning test 324, `test_structural_only_classifies_a_gate_finding`
   1324, the `## Acceptance criteria` bullet 73. One is off by one: `dig` is
   line 219, not 220. No step edits at that anchor, so this does not fail.
7. Regression surface: `tests/test_gate.py` calls `_set_digest` four times,
   and only the TICKET-081 fixture at line 328 puts a digit in `## Digest`, so
   `dig_counts` is empty elsewhere and the branch is inert. Criterion 6 runs
   the whole suite; criterion 8 runs `tests/test_stages.py`.
8. Blast radius: bugfix, 4 files, one source file. Neither
   `pipeline/core/gate.py` nor `pipeline/stages/planning.md` is in
   `machine.FENCED`. The class matches.

long: eight scored items, each with its own evidence, is the stage output.

### 2026-08-27 17:56:26Z · plan-validation · session · session=b354a802-58fd-4ee7-a51b-07c60a955303

`plan-validation` ran as session `b354a802-58fd-4ee7-a51b-07c60a955303`
- replay: `claude --resume b354a802-58fd-4ee7-a51b-07c60a955303`
- log: `.project/logs/TICKET-081-plan-validation-b354a802.log`

### 2026-08-27 17:56:26Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ eight items pass; gate() returns (True, []) on the fixtures of steps 2, 3 and 4, so step 5's 1 failed, 3 passed holds; CRIT_COUNT_RE flags 3 of 463 criteria, all the defect

### 2026-08-27 17:57:40Z · human · rejection

[chezzijr's decision, entered via Claude Code while away; the reviewer also filed this ticket -- audit this reason in the thread]

Step 8 places the new check where it cannot run. TICKET-079 merged while this plan sat at plan-validation and rewrote the body of `for c in crits:`; on main today (pipeline/core/gate.py:426-439) both accept paths `continue`:

    if re.search(r'\bpytest\b|\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/', c, re.I):
        continue
    if CRIT_CMD_RE.search(c) and CRIT_OUTCOME_RE.search(c):
        continue
    findings.append(f'acceptance criterion names no test: {c} -- {CRIT_RULE}')

Step 8 says to add the count check 'inside that loop, after the acceptance criterion names no test append'. Everything that names a test or names a command with a stated result has already `continue`d by then, so the check only ever sees criteria that ALREADY fail the names-no-test rule -- which is not the defect this ticket is about.

Your own fixture demonstrates it: the criterion '- `tests/chz` suite: 630 passed' matches \btests?/ in the first regex and continues. Acceptance criterion 1 cannot pass as planned.

Fix: run the absolute-count check independently of the names-a-test decision -- before the two `continue`s, or in its own loop over `crits`. A criterion can be perfectly test-shaped and still pin a number a sibling ticket moves; those are orthogonal properties and the code should treat them that way.

Two line citations also drifted with 079 and should be re-read rather than trusted: 'acceptance criterion names no test' is at gate.py:78, not 63; `for c in crits:` is at 426, not 411. The anchors you name in prose are correct, so this is secondary -- but re-verify every line number in the plan against current main, because 069, 079 and others are landing in this file while you replan.

Everything else stands and needs no rework, and it is good work. Specifically keep: COUNT_RE's two-digit floor and its lookarounds rejecting 2.1.238, gate.py:411, DEC-065 and 10ms; CRIT_COUNT_RE requiring the count-noun to FOLLOW the number, with the reference-vs-count reasoning; the measurement you did over this repo's 446 criteria (26 flagged by the bare integer, 3 by this form, all 3 real) -- that empirical false-positive check is exactly right and should stay in the comment; the count-pinned: waiver; the three over-fixing guard tests; and step 10/11 adding the finding to STRUCTURAL_MARKS with its test in tests/test_dispatch.py per DEC-017.

### 2026-08-28 · planning · result=ok

Replanned after the human rejection. The rejection is correct and I reproduced
it.

I built the rejected placement -- the count check inside `for c in crits:`,
after the two `continue`s TICKET-079 added -- in a scratch checkout of `main`
and ran the five tests of plan steps 2-5:

    2 failed, 3 passed
    FAILED test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest - AssertionError: []
    FAILED test_a_test_shaped_criterion_pinning_a_count_is_still_flagged - AssertionError: []

With the check in its own loop above `for c in crits:`, the same five pass and
`uv run --group dev pytest -q` reports `373 passed` on that scratch tree.

What changed from the rejected plan:

1. Step 8 puts the check in its own loop over `crits`, above line 426.
2. Step 5 adds `test_a_test_shaped_criterion_pinning_a_count_is_still_flagged`,
   which fails against the rejected placement.
3. Every line number is re-read against `main` at `c0e516d`: `CRIT_ITEM_RE` 45,
   `STRUCTURAL_MARKS` 68, `names no test` 78, `dig` 234, `crit` 397,
   `for c in crits:` 426, the `planning.md` bullet 73-79.
4. Step 1 runs `grep -c CRIT_CMD_RE pipeline/core/gate.py` first: the worktree
   is pre-079 and `revalidating` rebases before `implementing`.
5. DEC-079 added to `## Decisions checked`.
6. Re-measured today: 83 tickets, 469 criteria, 27 flagged by a shared bare
   integer, 3 by `CRIT_COUNT_RE`, all 3 the defect.

Everything the rejection said to keep is kept unchanged.

### 2026-08-27 18:09:00Z · planning · session · session=42da4230-9f0e-4faa-888d-1eacc01eacd9

`planning` ran as session `42da4230-9f0e-4faa-888d-1eacc01eacd9`
- replay: `claude --resume 42da4230-9f0e-4faa-888d-1eacc01eacd9`
- log: `.project/logs/TICKET-081-planning-42da4230.log`

### 2026-08-27 18:09:00Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ the count check moves into its own loop above `for c in crits:`; a new orthogonality test fails against the rejected placement (2 failed, 3 passed); every line number re-read against main c0e516d

### 2026-08-28 · plan-validation · result=ok

Tier B: eight items pass on the replan. This entry sits above the Tier A gate
entry of the same run because the guard blocks every way of appending at the
end of this file.
long: nine findings, each carrying the evidence that decides it.

1. Root cause, two halves. `gate()` compares no number in `## Acceptance
   criteria` against `## Digest`. And both accept arms of `for c in crits:`
   end in `continue`, so a check inside that loop never sees a criterion that
   names a test. The plan fixes both.
2. Anchors. Every line number resolves against `main` at `c0e516d`:
   `CRIT_ITEM_RE` 45, the `# A criterion clears Tier A` comment 47,
   `STRUCTURAL_MARKS` 68, `acceptance criterion names no test` 78, `dig` 234,
   `crit` 397, `for c in crits:` 426, the `planning.md` bullet's last line 79,
   `test_structural_only_classifies_a_gate_finding` 1324. This worktree is
   pre-079: `grep -c CRIT_CMD_RE pipeline/core/gate.py` prints `0`, which is
   what step 1 re-checks after the rebase.
3. Measurement re-derived, with awk over the 83 ticket files: 469 criterion
   marker lines, and the digest-intersected noun-after form flags 3 criteria.
   TICKET-021 criterion 6 (`16 passed`, plus `14 passing` in the same
   criterion), TICKET-021 criterion 8 (`176 passed`), TICKET-057 criterion 1
   (`127 ok lines`, plus `103 cases` on a continuation line DEC-054 joins on).
   All 3 are the defect. The plan's `3` counts criteria, not matches; the two
   extra numbers sit inside criteria the plan already counted.
4. Decisions. DEC-016, DEC-017, DEC-030, DEC-054, DEC-057, DEC-058, DEC-065
   and DEC-079 carry no `superseded-by` marker. DEC-079 requires the prefix
   `acceptance criterion names no test` to stay unchanged and bans `pytest`
   from a rule string. `CRIT_COUNT_RULE` adds a second prefix, edits neither
   the first nor `CRIT_RULE`, and holds no `pytest`.
5. Scope. Every step maps to a criterion: 1 to 1 and 7, 2 to 3, 3 to 4, 4 to
   5, 5 to 2, 6 to 1, 7-9 to 1 and 2, 10-12 to 6, 13 to 9, 14 to 7 and 8.
6. Criteria falsifiable. Criterion 7 is a delta on the step 1 baseline -- the
   rule this ticket adds, applied to itself. I ran the same intersection over
   TICKET-081's own sections: no hit, so this ticket does not flag itself.
7. Riskiest step is 7 plus 8, the regex. `## Rollback` states the fallback:
   revert the step 8 loop alone, keep the five tests, which then fail.
8. Regression surface. The new loop reads every plan's criteria.
   `tests/test_gate.py::test_a_whole_suite_criterion_naming_pytest_is_accepted`
   is the case to watch, and it is safe: `FIXTURE`'s `## Digest` holds no
   digit, so `dig_counts` is empty and the loop skips it. Criterion 7 covers
   the rest of the suite.
9. Blast radius. `class: bugfix`, 4 files, 14 steps, 3 commits, all additive:
   one source file, one prompt sentence, two test files. Proportionate.

### 2026-08-27 18:09:19Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-27 17:43:38Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` fails on base `main` too -- the bug is not already fixed upstream
```
     assert (not True)[0m

[1m[31mtests/test_gate.py[0m:333: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest[0m - AssertionError: []
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ly9ngpbg/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ly9ngpbg/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-08-27 18:18:29Z · plan-validation · session · session=4ac3f99f-e6d9-452d-b26c-599091d01367

`plan-validation` ran as session `4ac3f99f-e6d9-452d-b26c-599091d01367`
- replay: `claude --resume 4ac3f99f-e6d9-452d-b26c-599091d01367`
- log: `.project/logs/TICKET-081-plan-validation-4ac3f99f.log`

### 2026-08-27 18:18:29Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ eight items pass; re-derived the measurement with awk (83 tickets, 469 criteria, 3 flagged, all the defect) and confirmed every line number against main c0e516d

### 2026-08-27 18:19:10Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket and rejected its first plan -- audit in thread). Verified gate.py:426 is still 'for c in crits:' and gate.py has not moved since 079.

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket and rejected its first plan -- audit in thread). Verified gate.py:426 is still 'for c in crits:' and gate.py has not moved since 079.**

### 2026-08-27 18:26:01Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` fails as required
```
       [33m"[39;49;00m[33m- `test_broken` passes[39;49;00m[33m"[39;49;00m,[90m[39;49;00m
            [33m"[39;49;00m[33m- `test_broken` passes[39;49;00m[33m\n[39;49;00m[33m- `tests/chz` suite: 630 passed[39;49;00m[33m"[39;49;00m))[90m[39;49;00m
        ok, failures = gate(d, [33m"[39;49;00m[33mTICKET-001[39;49;00m[33m"[39;49;00m)[90m[39;49;00m
>       [94massert[39;49;00m [95mnot[39;49;00m ok [95mand[39;49;00m [96many[39;49;00m([33m"[39;49;00m[33mabsolute count[39;49;00m[33m"[39;49;00m [95min[39;49;00m f [94mfor[39;49;00m f [95min[39;49;00m failures), failures[90m[39;49;00m
[1m[31mE       AssertionError: [][0m
[1m[31mE       assert (not True)[0m

[1m[31mtests/test_gate.py[0m:333: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest[0m - AssertionError: []
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest` fails on base `main` too -- the bug is not already fixed upstream
```
     assert (not True)[0m

[1m[31mtests/test_gate.py[0m:333: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest[0m - AssertionError: []
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-1tn5fy8n/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-1tn5fy8n/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-08-27 18:26:01Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-28 · implementing · todo

Todo list for the 14-step plan:
1. [x] Confirm tree, baseline. `grep -c CRIT_CMD_RE` = 2 (TICKET-079 present). Suite: `1 failed, 376 passed`, `AssertionError: []` for the pinning test.
2. [x] Add `test_a_count_pinned_line_waives_the_absolute_count_check`.
3. [x] Add `test_a_number_a_criterion_refers_to_but_does_not_count_is_not_flagged`.
4. [x] Add `test_a_count_a_criterion_measures_itself_is_not_flagged`.
5. [x] Add `test_a_test_shaped_criterion_pinning_a_count_is_still_flagged`.
6. [x] Run the five-test filter: `2 failed, 3 passed` -- matches plan.
7. [x] Add four constants to `gate.py`.
8. [x] Add the check loop above `for c in crits:`.
9. [x] Run full `test_gate.py`: `53 passed`. Committed `f279bef`.
10. [x] Add `STRUCTURAL_MARKS` entry.
11. [x] Add `test_an_absolute_count_finding_is_structural` to `test_dispatch.py`.
12. [x] Run structural filter: `3 passed` (plan said 2; a pre-existing test also matches `-k structural`). Committed `16fc48b`.
13. [x] Edit `pipeline/stages/planning.md`.
14. [x] Run full suite (`382 passed`) + guard script (exit 0). Committed `c6e3b65`.

### 2026-08-27 18:28:57Z · implementing · session · session=4b6c6291-1569-4d0b-bd11-2d9e65d4625c

`implementing` ran as session `4b6c6291-1569-4d0b-bd11-2d9e65d4625c`
- replay: `claude --resume 4b6c6291-1569-4d0b-bd11-2d9e65d4625c`
- log: `.project/logs/TICKET-081-implementing-4b6c6291.log`

### 2026-08-27 18:28:57Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ built plan as written; check runs in its own loop above `for c in crits:`; 382 passed (376+6), guard exits 0; 3 commits f279bef/16fc48b/c6e3b65

### 2026-08-28 · review · findings · result=ok

Reviewed the delta `main...HEAD`: 4 commits, 122 insertions, 0 deletions, in
`pipeline/core/gate.py`, `pipeline/stages/planning.md`, `tests/test_gate.py`
and `tests/test_dispatch.py`. No blocking finding.

The rejection's finding is resolved. The check runs in its own loop at
`gate.py:462`, above `for c in crits:` at `gate.py:467`.
`test_a_test_shaped_criterion_pinning_a_count_is_still_flagged` passes and
guards that placement.

Verified, each command run from the worktree:

1. `uv run --group dev pytest -q` reports `382 passed in 18.77s`, the step 1
   baseline of 376 plus 6 (criterion 7).
2. `./pipeline/hooks/test_dangerous_commands.py` prints `guard: all passed`
   and exits 0 (criterion 8).
3. `grep -c count-pinned pipeline/stages/planning.md` prints `1` (criterion 9).
4. The six criterion tests, run as node ids, report `6 passed` (criteria 1-6).
5. `git status --porcelain` is empty. I changed no file but this ticket.

The three negative tests are not vacuous. I ran the constants directly: the
step 3 fixture shares the bare integer `65` across both sections while
`CRIT_COUNT_RE.findall` returns `[]` on its criterion; the step 2 fixture
shares `630` once the waiver line is removed; `FIXTURE`'s `## Digest` gives
`COUNT_RE.findall` an empty list. Each test fails under a distinct wrong regex.

Plan step 12's `2 passed` was wrong, not the code.
`pytest -q tests/test_dispatch.py -k structural --collect-only` lists
`test_a_tier_b_rejection_charges_the_plan_not_the_structural_counter`, which
is on `main`. `3 passed` is correct, and the implementer reported it.

Non-blocking notes. No rework asked:

1. nit -- `COUNT_PINNED_RE` anchors the waiver at the start of a line, so a
   bulleted `- count-pinned: why` does not waive, and raises no finding of its
   own either. A planner who bullets the waiver gets a silent non-waiver. It
   mirrors `DIGEST_SHORT_RE` (`gate.py:23`) exactly, which is why it is a nit.
2. nit -- one `count-pinned:` line waives every criterion in the section, not
   the one it sits under. `## Decisions` states that trade-off.
3. nit -- the finding interpolates the raw criterion unquoted, unlike the
   `## Plan` scan, which uses `repr()`. A `crits` entry is joined to one line,
   and the existing `names no test` finding does the same, so this adds no new
   behaviour.

long: the criterion-by-criterion evidence is what a reviewer at the gate needs
to skip the thread; rule 9 keeps every count and command in it.

### 2026-08-27 18:43:40Z · review · session · session=306c5553-a980-498c-9dcf-45d2df1bab52

`review` ran as session `306c5553-a980-498c-9dcf-45d2df1bab52`
- replay: `claude --resume 306c5553-a980-498c-9dcf-45d2df1bab52`
- log: `.project/logs/TICKET-081-review-306c5553.log`

### 2026-08-27 18:43:40Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ no blocking finding; check sits in its own loop at gate.py:462 above `for c in crits:` at 467; all 9 criteria re-run and pass (382 passed, guard exit 0); 3 nits recorded

### 2026-08-27 20:14:53Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 20:14:54Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/081


Rebasing (1/4)
Rebasing (2/4)
Rebasing (3/4)
Auto-merging pipeline/core/gate.py
CONFLICT (content): Merge conflict in pipeline/core/gate.py
Auto-merging tests/test_dispatch.py
CONFLICT (content): Merge conflict in tests/test_dispatch.py
error: could not apply 16fc48b... feat(TICKET-081): the absolute-count finding is structural
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply 16fc48b... # feat(TICKET-081): the absolute-count finding is structural
Auto-merging pipeline/core/gate.py
CONFLICT (content): Merge conflict in pipeline/core/gate.py
Auto-merging tests/test_dispatch.py
CONFLICT (content): Merge conflict in tests/test_dispatch.py
Auto-merging tests/test_gate.py
Automatic merge failed; fix conflicts and then commit the result.

```

### 2026-08-28 01:35:18Z · human · note · by=chezzijr

**resumed** by chezzijr -> `merging`, reset []

### 2026-08-28 01:35:18Z · human · answer · by=chezzijr

**note from chezzijr**

Two merge conflicts resolved by hand (chezzijr, via Claude Code, on explicit instruction), both union-of-both-sides. pipeline/core/gate.py: this branch's STRUCTURAL_MARKS entry plus TICKET-076's UNMATCHABLE_MARK, kept both. tests/test_dispatch.py: this branch's test_an_absolute_count_finding_is_structural plus main's test_suite_ran_... and test_unmatchable_..., kept all three. tests/test_dispatch.py + tests/test_gate.py: 117 passed, 1 failed. The failure is test_a_merged_dispatcher_change_ends_the_daemon_loop_too, which fails identically on unmodified main -- it walks the registry and /home/chezzijr/proj/chezzilang is still registered. Not caused by this diff; TICKET-069's review recorded the same cause.

### 2026-08-28 01:37:35Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
md                      |  20 +
 .project/tickets/TICKET-069.md                     | 912 ++++++++++++++++++++-
 .project/tickets/TICKET-071.md                     | 583 ++++++++++++-
 .project/tickets/TICKET-078.md                     | 744 ++++++++++++++++-
 CLAUDE.md                                          |   9 +
 README.md                                          |  17 +
 pipeline/core/config.py                            |  44 +-
 pipeline/core/gate.py                              |  33 +-
 pipeline/core/machine.py                           |  24 +
 pipeline/daemon/supervisor.py                      |  51 +-
 pipeline/templates/pipeline.toml                   |  11 +
 pipeline/templates/skills/pipeline-config/SKILL.md |   8 +-
 tests/test_config.py                               | 123 ++-
 tests/test_dispatch.py                             | 114 ++-
 tests/test_gate.py                                 |  49 +-
 tests/test_machine.py                              |  13 +
 18 files changed, 2691 insertions(+), 113 deletions(-)
 create mode 100644 .project/decisions/DEC-069.md
 create mode 100644 .project/decisions/DEC-071.md
 create mode 100644 .project/decisions/DEC-078.md
Updating 16d0dab..d3994bc
Fast-forward
 pipeline/core/gate.py       | 44 ++++++++++++++++++++++++++++++++
 pipeline/stages/planning.md |  6 +++++
 tests/test_dispatch.py      | 11 ++++++++
 tests/test_gate.py          | 61 +++++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 122 insertions(+)

```

### 2026-08-28 01:37:35Z · merging · decision

decision recorded as `DEC-081`
