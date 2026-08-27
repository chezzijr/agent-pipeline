---
id: TICKET-079
stage: done
class: feature
branch: ticket/079
test_file: tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted
files_declared:
- pipeline/core/gate.py
- pipeline/stages/plan-validation.md
- pipeline/stages/planning.md
- tests/test_gate.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 13
  plan_files: 4
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 666ba6ca-e272-41fe-999d-05148bd0bd8f
  log: .project/logs/TICKET-079-review-666ba6ca.log
approved_by: chezzijr (via Claude Code, while away; reviewer also filed this ticket
  -- audit in thread)
approved_at: '2026-08-27T17:27:59.315470+00:00'
---

## Summary

Implemented as `a645816` and reviewed: pass 1, no blocking findings.

`gate()` rejected an acceptance criterion naming a command and its expected
output, because the only shape it accepted was a test-shaped token. The fix ORs
a second arm onto that check at `pipeline/core/gate.py:426-439`. A criterion
clears it when it holds both a command in backticks (`CRIT_CMD_RE` -- a code
span carrying a word and at least one argument) and an outcome word
(`CRIT_OUTCOME_RE` -- `prints`, `exits`, `empty`, and the rest). A one-token
span such as `10ms` or `gate.py` is not a command, so an opinion quoting an
identifier still fails. The finding keeps its `STRUCTURAL_MARKS` prefix
(`gate.py:78`) and gains `CRIT_RULE` after the criterion, per DEC-030 and
DEC-065. Both prose copies of the rule changed in the same commit.

The diff is four files, `+81 -6`: `pipeline/core/gate.py`,
`tests/test_gate.py`, `pipeline/stages/planning.md` and
`pipeline/stages/plan-validation.md` -- exactly `files_declared`.

Review re-ran the evidence: `uv run --group dev pytest -q` -> `368 passed`,
`tests/test_gate.py` -> `48 passed`, `./pipeline/hooks/test_dangerous_commands.py`
-> `guard: all passed`. Every acceptance criterion holds.

Two minor findings stand, neither blocking and neither needing an edit: a
multi-word code span that is not a command can clear `CRIT_CMD_RE`, which
`## Decisions` accepts and Tier B now judges; and
`pipeline/templates/skills/file-ticket/SKILL.md` never named the old rule, so
it did not go stale.

## Reproduction

`tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted`

Command: `uv run --group dev pytest -q tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted`

Failure output:

```
AssertionError: ["acceptance criterion names no test: - `grep -c 'on an unreadable root' docs/stdlib.md` prints `0`"]
assert False
```

expect: acceptance criterion names no test: - `grep -c 'on an unreadable root' docs/stdlib.md` prints `0`

## Digest

Files touched: `pipeline/core/gate.py` (the rule), `tests/test_gate.py` (the
tests), `pipeline/stages/planning.md` and `pipeline/stages/plan-validation.md`
(the two prose copies of the rule).

Key function: `gate()` in `pipeline/core/gate.py`. Its `## Acceptance criteria`
scan runs at lines 382-421. Lines 383-410 build `crits` -- one string per
criterion, with continuation lines already joined (DEC-054). Lines 411-421 test
each `c` against
`re.search(r"\bpytest\b|\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/", c, re.I)`
and append `f"acceptance criterion names no test: {c}"`. Only that loop body
changes; the `crits` builder is untouched.

Entry points: `gate()` is called by `pipeline gate` (`pipeline/cli/main.py`) and
spawned by `gate_cmd()` at `plan-validation` and `revalidating`.

Gotchas:

1. The finding's prefix `acceptance criterion names no test` is in
   `STRUCTURAL_MARKS` (`pipeline/core/gate.py:63`), matched with `startswith`.
   Keep that prefix byte-identical, or the finding starts charging
   `plan_validation_attempts` instead of `structural_gate_failures` (DEC-065).
2. `tests/test_gate.py` is copied onto a checkout of base and imported there
   (DEC-017, DEC-018). The new tests import no new name -- not from `helpers`,
   and not `CRIT_CMD_RE` from `pipeline.core.gate`. They assert on the literal
   substring `names no test`, as every neighbouring test does.
3. `tests/test_gate.py:606` (`test_a_whole_suite_criterion_naming_pytest_is_accepted`)
   asserts that no emitted finding contains `pytest`. The rule text appended to
   the finding must not use that word.
4. The dispatcher runs the *installed* `pipeline` copy of `gate.py`, not this
   worktree's, so this ticket's own acceptance criteria are judged by the old
   rule. Every one of them names a `tests/...::...` node for that reason.
5. Measured 2026-08-28, both regexes run against all fifteen criterion strings
   the existing tests use. The command half
   `` `[A-Za-z_./][\w.+/-]*\s+\S[^`\n]*` `` matches
   `` `grep -c 'on an unreadable root' docs/stdlib.md` `` and does not match
   `` `10ms` ``, `` `test_broken` `` or `` `pipeline/core/gate.py` `` -- a
   one-token span is a metric or an identifier. Its content class excludes a
   backtick, so a match never spans two separate code spans: the criterion
   "the review agent is happy with `gate.py` and `machine.py`" produces no
   match and still fails.
6. `pipeline/stages/planning.md` is not in `machine.FENCED`, so this diff does
   not park at `awaiting-merge` for the fence.

## Decisions checked

Grep terms in `/home/chezzijr/proj/agent-pipeline/.project/decisions/`:
`criterion`, `criteria`, `names no test`, `acceptance`, `STRUCTURAL_MARKS`,
`Tier A`, `gate.py`, `backtick`.

Binding, all active:

- DEC-054 (supersedes DEC-042): `CRIT_ITEM_RE` matches four markers, the
  continuation arm runs before the marker arm, the scan consults `_fenced()`.
  This plan changes none of that. It edits only what happens to a built `c`.
- DEC-030: a Tier A finding states the rule that would fix it; the rule text is
  duplicated between `pipeline/core/gate.py` and `pipeline/stages/planning.md`
  on purpose; `tests/test_gate.py` asserts literal substrings rather than
  importing the constant. This plan follows all three -- it adds `CRIT_RULE` to
  the finding and changes both prose copies in the same commit.
- DEC-065: add a `STRUCTURAL_MARKS` entry for a new structural finding. This
  plan adds no new finding and leaves the existing prefix unchanged, so the
  existing mark still matches.
- DEC-017, DEC-018: `tests/test_gate.py` gains no new import.

History, not binding: DEC-042 (superseded by DEC-054) records why the check
reads numbered criteria at all.

## Plan

1. Run `uv run --group dev pytest -q tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted` and watch it fail with ``AssertionError: ["acceptance criterion names no test: - `grep -c 'on an unreadable root' docs/stdlib.md` prints `0`"]`` -- the test triage committed at 3b98842 in `tests/test_gate.py`.
2. In `pipeline/core/gate.py`, add three module constants directly below `CRIT_ITEM_RE` (line 45) and above `STRUCTURAL_MARKS`: `CRIT_CMD_RE = re.compile(r"`[A-Za-z_./][\w.+/-]*\s+\S[^`\n]*`")`; `CRIT_OUTCOME_RE = re.compile(r"\b(prints?|outputs?|reports?|returns?|exits?|shows?|lists?|finds?|contains?|passes|fails|succeeds|empty|nothing|none|green|clean|zero|no output|exit (?:code|status))\b", re.I)`; and `CRIT_RULE = ("name a test, or name a command in backticks together with the output or exit status running it must produce")`.
3. Comment those three constants in `pipeline/core/gate.py` with three facts: both halves are required, a one-token span is a metric or an identifier and so is not a command, and the command half's content class excludes a backtick so one match never spans two code spans.
4. In `pipeline/core/gate.py`, rewrite the body of `for c in crits:` (lines 411-421) as three statements, keeping the existing comment about `10ms` and `pytest` above the first: `if re.search(r"\bpytest\b|\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/", c, re.I): continue`, then `if CRIT_CMD_RE.search(c) and CRIT_OUTCOME_RE.search(c): continue`, then `findings.append(f"acceptance criterion names no test: {c} -- {CRIT_RULE}")`.
5. Run `uv run --group dev pytest -q tests/test_gate.py` and expect every test in the file to pass, including `test_a_criterion_naming_a_command_and_its_expected_output_is_accepted`.
6. Add `test_a_criterion_naming_a_command_and_an_exit_status_is_accepted` to `tests/test_gate.py`, below the reproduction test at line 349: `d = project(FIXTURE.replace("- `test_broken` passes", "- `uv run ruff check .` exits 0"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert ok, failures`, then `shutil.rmtree(d)`.
7. Add `test_a_command_criterion_with_no_stated_result_is_still_caught` to `tests/test_gate.py`: `d = project(FIXTURE.replace("- `test_broken` passes", "- `cargo build --release` is nicer than before"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert not ok and any("names no test" in f for f in failures), failures`, then `shutil.rmtree(d)`.
8. Add `test_an_opinion_quoting_an_identifier_is_still_caught` to `tests/test_gate.py`: `d = project(FIXTURE.replace("- `test_broken` passes", "- `pipeline/core/gate.py` is cleaner and the latency drops below `10ms`"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert not ok and any("names no test" in f for f in failures), failures`, then `shutil.rmtree(d)`.
9. Add `test_the_criterion_finding_states_the_rule_that_would_fix_it` to `tests/test_gate.py`: `d = project(FIXTURE.replace("- `test_broken` passes", "- code should be clean"))`, then `ok, failures = gate(d, "TICKET-001")`, then `assert not ok and any("names no test" in f and "backticks" in f for f in failures), failures`, then `shutil.rmtree(d)`.
10. Run `uv run --group dev pytest -q tests/test_gate.py` and expect the four new tests and every existing one to pass; the over-fixing guards in that file are `test_a_command_criterion_with_no_stated_result_is_still_caught`, `test_an_opinion_quoting_an_identifier_is_still_caught`, `test_gate_blocks_a_vacuous_acceptance_criterion`, `test_an_acceptance_criterion_must_name_something_test_shaped`, `test_an_unindented_second_line_is_a_criterion_of_its_own` and `test_a_wrapped_criterion_naming_no_test_anywhere_still_fails`.
11. In `pipeline/stages/planning.md` (line 73), replace `- `## Acceptance criteria` -- each one falsifiable and mapped to a named test.` with `- `## Acceptance criteria` -- each one falsifiable: mapped to a named test, or` plus an indented continuation line reading `naming a command in backticks together with the output or exit status running it must produce, as in ``- `grep -c foo docs/x.md` prints `0` ``. A backticked identifier alone is not a command: the span needs a word and at least one argument.` -- the two sentences go above the existing `A criterion that wraps must indent its continuation lines` sentence, which stays.
12. In `pipeline/stages/plan-validation.md`, change line 16 from `present, test fails, suite green, criteria name tests). Your job is judgment.` to `present, test fails, suite green, criteria name a test or a command and its expected output). Your job is judgment.`, and add to the `**Falsifiable criteria**` bullet (lines 26-27) the sentence `A criterion naming a command clears Tier A on its shape alone -- judge whether the result it states would actually differ if the implementation were wrong.`
13. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect both green, then commit `pipeline/core/gate.py`, `tests/test_gate.py`, `pipeline/stages/planning.md` and `pipeline/stages/plan-validation.md` in one commit titled `fix(TICKET-079): a criterion naming a command and its result satisfies the gate`.

## Acceptance criteria

- `tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted` passes: the criterion `` `grep -c 'on an unreadable root' docs/stdlib.md` prints `0` `` draws no finding.
- `tests/test_gate.py::test_a_criterion_naming_a_command_and_an_exit_status_is_accepted` passes: the criterion `` `uv run ruff check .` exits 0 `` draws no finding.
- `tests/test_gate.py::test_a_command_criterion_with_no_stated_result_is_still_caught` passes: `` `cargo build --release` is nicer than before `` still draws a `names no test` finding.
- `tests/test_gate.py::test_an_opinion_quoting_an_identifier_is_still_caught` passes: `` `pipeline/core/gate.py` is cleaner and the latency drops below `10ms` `` still draws a `names no test` finding.
- `tests/test_gate.py::test_the_criterion_finding_states_the_rule_that_would_fix_it` passes: the finding text contains the word `backticks`.
- `tests/test_gate.py::test_gate_blocks_a_vacuous_acceptance_criterion`, `tests/test_gate.py::test_an_acceptance_criterion_must_name_something_test_shaped`, `tests/test_gate.py::test_an_unindented_second_line_is_a_criterion_of_its_own` and `tests/test_gate.py::test_a_wrapped_criterion_naming_no_test_anywhere_still_fails` all still pass, unedited: the widening rejects nothing less than it did before.
- `tests/test_gate.py::test_a_whole_suite_criterion_naming_pytest_is_accepted` still passes: no emitted finding contains the word `pytest`.
- `uv run --group dev pytest -q` reports no failures for the whole suite, and `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

**A Tier A acceptance criterion may name a test, or a command plus the result of
running it. The two arms are OR'd; neither replaces the other.** The command arm
is two regexes in `pipeline/core/gate.py` and both must match: `CRIT_CMD_RE`, an
inline code span holding a word and at least one argument, and `CRIT_OUTCOME_RE`,
an outcome vocabulary (`prints`, `exits`, `empty`, `clean`, and the rest).
`CRIT_CMD_RE` carries the discrimination. A one-token span is deliberately not a
command: prose quotes `10ms`, `gate.py` and `test_broken` constantly, so
accepting a lone span would let "the code is cleaner, see `gate.py`" through --
the exact opinion this check exists to reject. Do not relax `CRIT_CMD_RE` to
"mentions backticks".

**Requiring both halves is what keeps the check falsifiable.** A command with no
stated result (`` `cargo build --release` is nicer ``) cannot be decided by
running it, so it still fails. `CRIT_OUTCOME_RE` is loose on purpose and is not
the guard; widening it costs little, widening `CRIT_CMD_RE` costs the rule.

**The finding's prefix `acceptance criterion names no test` stays unchanged; the
rule text is appended after the criterion.** That prefix is a `STRUCTURAL_MARKS`
entry matched with `startswith` (DEC-065), so editing it would move this failure
onto the `plan_validation_attempts` budget. `CRIT_RULE` must never contain the
word `pytest` --
`tests/test_gate.py::test_a_whole_suite_criterion_naming_pytest_is_accepted`
asserts that no finding does.

## Rollback

Revert the single commit from step 13 on `ticket/079`. It touches
`pipeline/core/gate.py`, `tests/test_gate.py`, `pipeline/stages/planning.md` and
`pipeline/stages/plan-validation.md` only, and no state or data, so the revert
restores the previous rule exactly. The visible effect of a revert: a criterion
naming a command and its output is rejected again, and every plan carrying one
pays a re-plan.

If instead the fix over-accepts -- an opinion criterion clears Tier A -- the
narrower repair is to drop `CRIT_OUTCOME_RE`'s noun-shaped alternatives
(`clean`, `green`, `none`, `nothing`) rather than to revert, which keeps the
`prints` and `exits` shapes the ticket reports.

## Thread

### 2026-08-27 16:15:56Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-28 · triage · result=ok

Reproduced. `pipeline/core/gate.py:419` checks each acceptance criterion with
`re.search(r"\bpytest\b|\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/", c, re.I)`.
A criterion naming a command and its expected output but no test-shaped word
(e.g. `` `grep -c 'on an unreadable root' docs/stdlib.md` prints `0` ``) fails
this regex and is rejected.

Added `tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted`,
committed on this branch (`3b98842`). It fails with exactly the reported
finding text; see `## Reproduction`.

Not a chore: the fix needs a rule that distinguishes a checkable
"command + expected output/exit status" shape from an unfalsifiable opinion
that happens to use backticks (the ticket itself flags this as the hard
part). That is a design choice for planning, not a mechanical edit to
`gate.py:419`.

### 2026-08-27 17:14:58Z · triage · session · session=f72d41f1-8f89-4f00-ad3e-a54a70158251

`triage` ran as session `f72d41f1-8f89-4f00-ad3e-a54a70158251`
- replay: `claude --resume f72d41f1-8f89-4f00-ad3e-a54a70158251`
- log: `.project/logs/TICKET-079-triage-f72d41f1.log`

### 2026-08-27 17:14:58Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced: gate() rejects a command+output criterion because its regex only matches test-shaped tokens

### 2026-08-28 · planning · note

Plan written: 13 steps over `pipeline/core/gate.py`, `tests/test_gate.py`,
`pipeline/stages/planning.md` and `pipeline/stages/plan-validation.md`.

The rule the ticket asked planning to settle: a criterion clears the check when
it names a test (the existing arm, unchanged), or when it holds BOTH a
backticked command and a word for what running it produces. The command half is
the discriminator -- an inline code span must carry a word and at least one
argument, so `10ms`, `test_broken` and `pipeline/core/gate.py` are not commands.
That is what keeps "mentions backticks" from being the rule.

Measured 2026-08-28, both regexes against the fifteen criterion strings the
existing tests use: all four shapes the ticket names are accepted, and every
criterion the current tests require to fail still fails, including the
unindented `--porcelain` continuation from TICKET-036 (one unbalanced backtick,
so no command match).

The finding text gains `CRIT_RULE` after the criterion (DEC-030) and keeps its
`STRUCTURAL_MARKS` prefix byte-identical (DEC-065). `CRIT_RULE` must not contain
the word `pytest`: `test_a_whole_suite_criterion_naming_pytest_is_accepted`
asserts no finding does.

Scope check: one function, one rule. No split needed. No questions for the human.

### 2026-08-27 17:22:06Z · planning · session · session=306956aa-f14c-4e02-a43d-57d45d177aad

`planning` ran as session `306956aa-f14c-4e02-a43d-57d45d177aad`
- replay: `claude --resume 306956aa-f14c-4e02-a43d-57d45d177aad`
- log: `.project/logs/TICKET-079-planning-306956aa.log`

### 2026-08-27 17:22:06Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: gate() accepts a criterion holding both a backticked command and an outcome word, test arm unchanged

### 2026-08-27 17:22:27Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted` fails as required
```

            [33m"[39;49;00m[33m- `test_broken` passes[39;49;00m[33m"[39;49;00m,[90m[39;49;00m
            [33m"[39;49;00m[33m- `grep -c [39;49;00m[33m'[39;49;00m[33mon an unreadable root[39;49;00m[33m'[39;49;00m[33m docs/stdlib.md` prints `0`[39;49;00m[33m"[39;49;00m))[90m[39;49;00m
        ok, failures = gate(d, [33m"[39;49;00m[33mTICKET-001[39;49;00m[33m"[39;49;00m)[90m[39;49;00m
>       [94massert[39;49;00m ok, failures[90m[39;49;00m
[1m[31mE       AssertionError: ["acceptance criterion names no test: - `grep -c 'on an unreadable root' docs/stdlib.md` prints `0`"][0m
[1m[31mE       assert False[0m

[1m[31mtests/test_gate.py[0m:358: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_a_criterion_naming_a_command_and_its_expected_output_is_accepted[0m - AssertionError: ["acceptance criterion names no test: - `grep -c 'on an unr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.05s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted` fails on base `main` too -- the bug is not already fixed upstream
```
m:358: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_a_criterion_naming_a_command_and_its_expected_output_is_accepted[0m - AssertionError: ["acceptance criterion names no test: - `grep -c 'on an unr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ayy5yyw3/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ayy5yyw3/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 9ms[0m[0m

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-08-28 · plan-validation · result=ok

Tier B: all eight items pass.

long: the stage requires a scored reasoning line per item, and there are eight.

**Root cause.** `gate()` decides "is this criterion falsifiable?" by looking for
a test-shaped token, so it rejects the other falsifiable shape -- a command plus
the result running it must produce. The plan fixes that, not the test: it ORs a
second arm onto `pipeline/core/gate.py:411-421` and leaves the `crits` builder
alone.

**Decisions.** DEC-030's scope note ("`acceptance criterion names no test` ...
is not touched") was closed by DEC-042, which keeps the rest of DEC-030 active.
Applying DEC-030's rule-text requirement to this finding therefore complies, and
needs no supersede. DEC-065: the prefix stays byte-identical, so
`STRUCTURAL_MARKS` (`pipeline/core/gate.py:63`) still matches. DEC-054 governs
the builder the plan does not touch.

**Both regexes, re-run independently against 21 criterion strings** -- the 15 the
existing tests use plus the 6 the plan adds. Zero mismatches. The three that
decide the design:

```
12 --porcelain` prints nothing         cmd=None  -> still rejected
18 `cargo build --release` is nicer     out=None  -> still rejected
19 `pipeline/core/gate.py` is cleaner   cmd=None  -> still rejected
```

**Scope.** Steps 11-12 trace to DEC-030, not to a criterion; that is the
decision's duplication requirement, not creep. Class `feature`, 4 files, one
function -- proportionate. **No research left:** every step names the file and
the literal text.

**Riskiest step:** step 2, `CRIT_CMD_RE`. `## Rollback` states the fallback --
drop `CRIT_OUTCOME_RE`'s noun alternatives rather than revert.

**Regression surface.** Over-acceptance, covered by
`test_gate_blocks_a_vacuous_acceptance_criterion`,
`test_an_acceptance_criterion_must_name_something_test_shaped`,
`test_an_unindented_second_line_is_a_criterion_of_its_own` and
`test_a_wrapped_criterion_naming_no_test_anywhere_still_fails`. Finding text:
`CRIT_RULE` carries no `pytest`, so `tests/test_gate.py:623` holds. Prose:
`tests/test_stages.py:30-34` asserts `unverified` and `[readonly] allow` in
`plan-validation.md`; both sit at lines 40-50, below the lines step 12 edits. No
test asserts `planning.md` prose.

**Criteria are falsifiable.** Each names a test node and the input that decides
it. Step 9's test fails if `CRIT_RULE` is not appended.

### 2026-08-27 17:27:07Z · plan-validation · session · session=0815dce5-6c3d-48ee-84c4-7e6fb198185a

`plan-validation` ran as session `0815dce5-6c3d-48ee-84c4-7e6fb198185a`
- replay: `claude --resume 0815dce5-6c3d-48ee-84c4-7e6fb198185a`
- log: `.project/logs/TICKET-079-plan-validation-0815dce5.log`

### 2026-08-27 17:27:07Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan validated: all eight items pass; both regexes re-run over 21 criterion strings with zero mismatches

### 2026-08-27 17:27:59Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread)

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread)**

### 2026-08-27 17:29:15Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-27 17:22:27Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_gate.py::test_a_criterion_naming_a_command_and_its_expected_output_is_accepted` fails on base `main` too -- the bug is not already fixed upstream
```
m:358: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_a_criterion_naming_a_command_and_its_expected_output_is_accepted[0m - AssertionError: ["acceptance criterion names no test: - `grep -c 'on an unr...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ke7ns6yw/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ke7ns6yw/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 9ms[0m[0m

```
- ok: DEC-042 is superseded -- history, not binding

### 2026-08-27 17:29:16Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-28 · implementing · todo

**implementing todo** (steps 1-13 from `## Plan`)

- [x] 1. run reproduction test, confirm RED
- [x] 2. add `CRIT_CMD_RE`, `CRIT_OUTCOME_RE`, `CRIT_RULE` constants
- [x] 3. comment the three constants
- [x] 4. rewrite the `for c in crits:` body with the OR'd check
- [x] 5. run `tests/test_gate.py`, expect all pass
- [x] 6. add `test_a_criterion_naming_a_command_and_an_exit_status_is_accepted`
- [x] 7. add `test_a_command_criterion_with_no_stated_result_is_still_caught`
- [x] 8. add `test_an_opinion_quoting_an_identifier_is_still_caught`
- [x] 9. add `test_the_criterion_finding_states_the_rule_that_would_fix_it`
- [x] 10. run `tests/test_gate.py`, expect all pass including 4 new + guards
- [x] 11. edit `pipeline/stages/planning.md` line 73
- [x] 12. edit `pipeline/stages/plan-validation.md` lines 16, 26-27
- [x] 13. run full suite + dangerous-commands test, commit

### 2026-08-28 · implementing · result=ok

**implementing done.** Executed all 13 plan steps.

RED confirmed for the reproduction test, then for two of the four new tests
(`test_a_criterion_naming_a_command_and_an_exit_status_is_accepted` and
`test_the_criterion_finding_states_the_rule_that_would_fix_it`) by
temporarily stashing the `gate.py` change and re-running them -- both failed
with `acceptance criterion names no test: ...` on old code, then passed on
restore. The other two new tests (`test_a_command_criterion_with_no_stated_result_is_still_caught`,
`test_an_opinion_quoting_an_identifier_is_still_caught`) assert the rejection
that already existed, so they passed on old code too -- correct, they guard
against over-acceptance.

`tests/test_gate.py`: 48 passed (44 existing + 4 new).
`uv run --group dev pytest -q`: 368 passed.
`./pipeline/hooks/test_dangerous_commands.py`: `guard: all passed`.

Committed `a645816` "fix(TICKET-079): a criterion naming a command and its
result satisfies the gate", touching exactly `pipeline/core/gate.py`,
`tests/test_gate.py`, `pipeline/stages/planning.md`,
`pipeline/stages/plan-validation.md` -- matches `files_declared`.

### 2026-08-27 17:31:45Z · implementing · session · session=f7244d73-29c1-487b-a679-a80483d02732

`implementing` ran as session `f7244d73-29c1-487b-a679-a80483d02732`
- replay: `claude --resume f7244d73-29c1-487b-a679-a80483d02732`
- log: `.project/logs/TICKET-079-implementing-f7244d73.log`

### 2026-08-27 17:31:45Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented plan (13 steps): gate() ORs CRIT_CMD_RE/CRIT_OUTCOME_RE onto the test-shaped check; 368 suite + 48 test_gate.py + guard all green, committed a645816

### 2026-08-28 · review · result=ok

**review pass 1: no blocking findings.** Reviewed `git diff main...HEAD` --
commits `3b98842` (test) and `a645816` (fix), four files, `+81 -6`, exactly
`files_declared`.

Re-ran the evidence: `uv run --group dev pytest -q` -> `368 passed`,
`uv run --group dev pytest -q tests/test_gate.py` -> `48 passed`,
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`.
`git status --porcelain` is empty.

Every acceptance criterion holds. All 13 plan steps landed as written.

Findings raised, then refuted:

1. The `continue` rewrite skips later loop work. Refuted: `gate.py:426-439` is
   the whole `for c in crits:` body; line 441 `seen: dict[str, str] = {}` sits
   at function scope.
2. The finding text breaks `STRUCTURAL_MARKS`. Refuted: `gate.py:439` keeps the
   prefix `acceptance criterion names no test: `, and `gate.py:87` matches with
   `startswith`.
3. `CRIT_RULE` carries `pytest`. Refuted: the constant reads `output or exit
   status`, and `tests/test_gate.py:656` passes.

Surviving findings:

1. minor -- `CRIT_CMD_RE` accepts any multi-word code span, so
   "- the `Tier A gate` passes" clears Tier A while naming no command.
   `## Decisions` chooses this looseness, and `plan-validation.md:26-30` now
   tells the Tier B judge to catch it. Not blocking.
2. minor -- `pipeline/templates/skills/file-ticket/SKILL.md:42` says only
   "falsifiable acceptance criteria". It never named the test-shaped rule, so
   nothing there went stale. No edit needed.

### 2026-08-27 17:35:08Z · review · session · session=666ba6ca-e272-41fe-999d-05148bd0bd8f

`review` ran as session `666ba6ca-e272-41fe-999d-05148bd0bd8f`
- replay: `claude --resume 666ba6ca-e272-41fe-999d-05148bd0bd8f`
- log: `.project/logs/TICKET-079-review-666ba6ca.log`

### 2026-08-27 17:35:08Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review pass 1: no blocking findings; 368 suite + 48 test_gate.py + guard green, 4 files match files_declared, 2 minor notes

### 2026-08-27 17:35:27Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 17:35:28Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/079


Current branch ticket/079 is up to date.
Already up to date.
Updating c56fe24..a645816
Fast-forward
 pipeline/core/gate.py              | 24 +++++++++++++++---
 pipeline/stages/plan-validation.md |  7 ++++--
 pipeline/stages/planning.md        |  6 ++++-
 tests/test_gate.py                 | 50 ++++++++++++++++++++++++++++++++++++++
 4 files changed, 81 insertions(+), 6 deletions(-)

```

### 2026-08-27 17:35:28Z · merging · decision

decision recorded as `DEC-079`
