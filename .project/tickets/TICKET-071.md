---
id: TICKET-071
stage: done
class: bugfix
branch: ticket/071
test_file: tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector
files_declared:
- pipeline/core/gate.py
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_dispatch.py
- tests/test_gate.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 9
  plan_files: 4
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 67926c00-cc16-4a40-b76e-d88a7216c5de
  log: .project/logs/TICKET-071-review-67926c00.log
approved_by: chezzijr (via Claude Code, while away; reviewer also filed this ticket
  -- audit in thread)
approved_at: '2026-08-27T16:32:21.822090+00:00'
---

## Summary

`gate()` reports a genuinely passing repro test as a selector that matched
nothing. TICKET-064 (`ae3b53b`) split the exit-0 path on `node in out`, and
pytest names a node only when it FAILS, so the split inverts on every real
pass. `_base_findings()` carries the same split at
`pipeline/core/gate.py:176`. Both branches are already a gate failure, so this
is a wrong diagnosis, not a hole.

The plan merges each exit-0 pair into one finding that names both causes --
the test passes, or the runner matched no test -- and quotes the output.
Planning looked for a portable signal that separates them and found none.
Files: `pipeline/core/gate.py`, `tests/test_gate.py`, `tests/test_dispatch.py`,
`pipeline/templates/skills/pipeline-config/SKILL.md`.

plan-validation passed the plan on 2026-08-27, scoring all eight items. The
plan removes the `node in out` predicate, so it fixes the cause. Implementation
needs no further research: every step names a file, a line and its replacement
text, and I opened every cited line. Two cited ranges run one line long --
`249-256` and `176-185` each include the `node not in out` arm the same step
says to leave unchanged. Keep that arm. The merged finding matches no
`STRUCTURAL_MARKS` prefix, so it stays substantive.

Implemented 2026-08-27: all 9 plan steps done via TDD, all 6 acceptance-criteria
tests pass, `uv run --group dev pytest -q` is 352 passed, and
`./pipeline/hooks/test_dangerous_commands.py` is green. Three commits:
`270d9fb`, `705b503`, `1fbed09`.

Review passed on 2026-08-27 with no blocking findings. The diff `2691206..1fbed09`
touches the 4 planned files and nothing else. Both exit-0 splits collapse to the
same three-way partition as before, so no input changes verdict. I re-ran the
suite (`352 passed in 17.62s`), the guard (`guard: all passed`) and the 6
acceptance tests (`6 passed in 0.12s`). Two non-blocking nits are in the thread:
the repro test asserts only an absent phrase, and `test_one = "true"` renders an
empty fence.

## Reproduction

test: tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector
command: uv run --group dev pytest -x tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector
expect: the selector matched nothing

A `test_one` whose output mimics pytest's real success format -- a dot,
`[100%]`, `1 passed in 0.03s`, never the node name -- exits 0 with `node in
out` false, same as `test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`'s
`"true"` case. `gate()` cannot tell the two apart and reports the genuine
pass as "the selector matched nothing", exactly the wrong-diagnosis symptom
TICKET-064 introduced.

Failure output:
```
AssertionError: ['`test_thing.py::test_broken` exited 0 but its name never appears in the output -- the selector matched nothing, not ...al output, already quoted in the `## Thread` entry `2026-08-27 16:16:42Z · plan-validation · gate · verdict=FAIL` --*']
assert not True
```

## Digest

- `pipeline/core/gate.py:249-256` holds the branch run's exit-0 split, inside `gate()`; `pipeline/core/gate.py:176-185` holds the same split inside `_base_findings()`.
- `gate()` runs `cfg["test_one"]` in the ticket worktree, sets `node = test.split("::")[-1]`, and reaches `_base_findings()` only from the final `else` arm -- a test that failed with its name in the output.
- No portable signal separates a pass from a matched-nothing selector. pytest prints `.` and `1 passed`; cargo prints `test x ... ok`; TICKET-064's real case was `test_one = "true"`, which prints nothing at all. Both causes are already a FAIL, so one finding naming both loses nothing the output fence does not carry.
- Wording gotcha: `tests/test_gate.py::test_gate_blocks_a_test_that_already_passes` asserts `"PASSES" in f`, and this ticket's repro test asserts the phrase `selector matched nothing` is absent. The merged text must keep the word `PASSES` and drop that phrase.
- `STRUCTURAL_MARKS` needs no new entry. Neither old finding is listed there, so both read as substantive and charge `plan_validation_attempts` (DEC-065); the merged finding inherits that.
- One behaviour change beyond wording: the old `PASSES` finding carried no fenced output and the merged one does. `_dedupe()` already replaces a repeat of that fence with a thread reference.
- Verified before planning: `uv run --group dev pytest -q tests/test_gate.py -k "pytest_style_pass or already_passes or distinguishes or passes_on_base"` printed `1 failed, 3 passed, 38 deselected in 0.10s`.

## Decisions checked

Grepped `.project/decisions/` for: selector, matched nothing, node in out, exited 0, PASSES, gate.py, STRUCTURAL_MARKS.

- DEC-065 -- `structural_only()` is a `startswith` allowlist and a new structural finding needs a mark. The merged finding is substantive, not structural, so `STRUCTURAL_MARKS` stays as it is and the finding keeps charging `plan_validation_attempts`.
- DEC-017 -- the base run is load-bearing, and `tests/test_gate.py` is copied onto a checkout of base, so it may import only what base has. Step 4 adds a test that uses `subprocess`, already imported at `tests/test_gate.py:4`, and adds no import.
- DEC-046 -- `gate()` quotes each distinct output once and returns a reference. Both merged findings keep their fenced `out[-1200:]` block, so `_dedupe()` still sees a fence.
- DEC-061 -- findings reach the dispatcher as JSON from the gate child, byte-for-byte. Wording is data on that path; nothing parses it.
- DEC-050 and DEC-053 -- both quote "PASSES -- it must fail before implementation" as the reason a cheap-route branch cannot pass Tier A. They depend on exit 0 in the worktree being a gate failure, which this plan preserves; only the string changes. Neither is superseded, and neither binds the wording.

## Plan

1. Rewrite `tests/test_gate.py:164-175` (`test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`) as the test below, then run `uv run --group dev pytest -q tests/test_gate.py -k exit_zero_test_and_names` and watch it fail on `matched no test`.
   ```python
   def test_gate_fails_an_exit_zero_test_and_names_both_causes():
       """`test_one` exiting 0 without ever naming the test is either a
       passing reproduction or a runner whose filter matched zero tests
       (TICKET-064). No portable signal separates them -- a runner names a
       node only on failure (TICKET-071) -- so one finding names both."""
       d = project()
       (d / ".project" / "pipeline.toml").write_text(
           'test_one = "true"\ntest_suite = "true"\ntest_suite_without_new = "true"\n')
       ok, failures = gate(d, "TICKET-001")
       assert not ok
       zero = [f for f in failures if "exited 0" in f]
       assert len(zero) == 1, failures
       assert "PASSES" in zero[0] and "matched no test" in zero[0], zero
       shutil.rmtree(d)
   ```
2. Replace the two exit-0 branches in `gate()` at `pipeline/core/gate.py:249-256` with the single branch below, and leave the `elif node not in out:` arm after it unchanged.
   ```python
   if code == 0:
       # Exit 0 has two causes and no portable signal separates them: a
       # runner names a node only when the test FAILS (pytest prints a dot
       # and a count), so a real pass and a selector that matched no test
       # look identical -- TICKET-071, which inverted TICKET-064's split.
       # Both are a gate failure; the fence is what tells a human which.
       findings.append(
           f"`{test}` exited 0 -- it must fail before implementation. Either "
           f"it PASSES, or `test_one` matched no test at all; a runner that "
           f"names a node only on failure makes the two identical here. Read "
           f"the output to tell them apart\n```\n{out[-1200:]}\n```")
   ```
3. Run `uv run --group dev pytest -q tests/test_gate.py -k "pytest_style_pass or already_passes or exit_zero_test_and_names"`, expect `3 passed`, then commit `pipeline/core/gate.py` and `tests/test_gate.py` as `fix(TICKET-071): one exit-0 finding naming both causes`.
4. Add the test below to `tests/test_gate.py` directly after `test_gate_blocks_a_test_that_passes_on_base` (ends at `tests/test_gate.py:396`), then run `uv run --group dev pytest -q tests/test_gate.py -k exits_zero_on_base` and watch it fail on `matched no test`.
   ```python
   def test_gate_names_both_causes_when_the_test_exits_zero_on_base():
       """The base run carries the branch run's exit-0 ambiguity: `test_one`
       exits 0 on base without printing the node, which is a pass there or a
       selector that matched nothing, and nothing separates them. No literal
       brace in the command -- `str.format` raises KeyError on one."""
       d, wt = _git_ticket_project("fixed\n", "buggy\n")
       (d / ".project" / "pipeline.toml").write_text(
           'test_one = "grep -q fixed f.py && exit 0; echo test_broken; exit 1"\n'
           'test_suite = "true"\ntest_suite_without_new = "true"\nbase = "main"\n')
       subprocess.run("git add -A && git commit -qm cfg", shell=True, cwd=d,
                      capture_output=True, text=True)
       ok, failures = gate(d, "TICKET-001", workdir=wt)
       assert not ok
       zero = [f for f in failures if "exited 0 on base" in f]
       assert len(zero) == 1, failures
       assert "matched no test" in zero[0], zero
       shutil.rmtree(d, ignore_errors=True)
   ```
5. Replace the two exit-0 returns in `_base_findings()` at `pipeline/core/gate.py:176-185` with the single return below, and leave the `if node not in out:` arm after it unchanged.
   ```python
   if code == 0:
       # The branch run's ambiguity (TICKET-071), on base: the bug is already
       # fixed there, or the test is red for a reason base does not have, or
       # the selector matched no test. Base proves nothing either way.
       return [f"`{test}` exited 0 on base `{base}`, so base proves nothing. "
               f"Either it PASSES there -- the bug is already fixed on base, "
               f"or the test is red for a reason base does not have -- or "
               f"`test_one` matched no test at all; a runner that names a "
               f"node only on failure makes the two identical here"
               f"\n```\n{out[-1200:]}\n```"]
   ```
6. Run `uv run --group dev pytest -q tests/test_gate.py -k "on_base or exits_zero_on_base"`, expect `3 passed`, then commit `pipeline/core/gate.py` and `tests/test_gate.py` as `fix(TICKET-071): one exit-0-on-base finding naming both causes`.
7. In `tests/test_dispatch.py:1310`, change the `substantive` literal's first line from ``"`t.py::x` PASSES -- it must fail before implementation"`` to ``"`t.py::x` exited 0 -- it must fail before implementation"``, leave its fenced second line alone, then run `uv run --group dev pytest -q tests/test_dispatch.py -k structural_only` and expect `1 passed`.
8. In `pipeline/templates/skills/pipeline-config/SKILL.md` line 3, replace the quoted symptom `"PASSES -- it must fail"` with `"exited 0 -- it must fail before implementation"` inside the `description:` field, so the skill's trigger phrase matches the finding an operator now reads.
9. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect both green, then commit `tests/test_dispatch.py` and `pipeline/templates/skills/pipeline-config/SKILL.md` as `docs(TICKET-071): match the merged exit-0 finding`.

## Acceptance criteria

- `tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector` passes: a pytest-shaped pass no longer produces the phrase `selector matched nothing`.
- `tests/test_gate.py::test_gate_fails_an_exit_zero_test_and_names_both_causes` passes: `test_one = "true"` produces exactly one finding containing `exited 0`, and it names both `PASSES` and `matched no test`.
- `tests/test_gate.py::test_gate_names_both_causes_when_the_test_exits_zero_on_base` passes: an exit-0 base run produces exactly one `exited 0 on base` finding, and it names `matched no test`.
- `tests/test_gate.py::test_gate_blocks_a_test_that_already_passes` still passes: a test that exits 0 with its name in the output is still a gate failure carrying `PASSES`.
- `tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` still passes: base being green is still a gate failure.
- `tests/test_dispatch.py::test_structural_only_classifies_a_gate_finding` passes with the merged finding's opener as its substantive example, so the exit-0 finding still charges `plan_validation_attempts`.
- `uv run --group dev pytest -q` is green, and `./pipeline/hooks/test_dangerous_commands.py` is green.

## Decisions

**Exit 0 from `test_one` is one finding with two causes, and merging them is the fix.** A runner names a node only when the test FAILS -- pytest prints a dot, `[100%]` and `1 passed`, and `test_one = "true"` prints nothing -- so `code == 0 and node in out` is false for a genuine pass and for a selector that matched no test alike. TICKET-064 split those two on that predicate and got the diagnosis backwards for every real pass. No portable signal separates them, so `gate()` and `_base_findings()` each report one finding naming both causes and quote the output for a human. Both causes were already a gate failure and still are: nothing is let through, and the split that matters -- exit 0 against a red test -- is untouched. Do not re-split on `node in out`. The durable answer is a check on the project's own test commands, which is TICKET-068's question.

**The merged finding must contain the word `PASSES` and must not contain the phrase `selector matched nothing`.** Two tests pin the wording from opposite sides: `test_gate_blocks_a_test_that_already_passes` asserts the first, and this ticket's repro test asserts the absence of the second. Reword freely inside those two constraints.

**The finding stays out of `STRUCTURAL_MARKS`.** It is substantive, so a Tier A failure carrying it charges `plan_validation_attempts`, not `structural_gate_failures` (DEC-065). Listing it would buy a misconfigured `test_one` free plan-validation attempts.

## Rollback

Revert the commits from steps 3, 6 and 9, newest first, and the gate returns to TICKET-064's two-branch split in `pipeline/core/gate.py`. Nothing else reads these strings: findings travel as JSON to the dispatcher and as prose into `## Thread`. The only loss from a revert is the wrong diagnosis this ticket removes, so it is safe to sit on.

## Thread

### 2026-08-27 16:15:56Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-27 · triage

Reproduced. Added `tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector`,
committed at `c960f3f`.

It gives `test_one` output shaped like real pytest success -- a dot,
`[100%]`, `1 passed in 0.03s` -- with the node name absent, same shape as
`test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass`'s
`"true"` case. `gate()` cannot distinguish them and reports "the selector
matched nothing", confirming the ticket's diagnosis.

No prior commit addresses this: `ae3b53b` (TICKET-064) is the one that
introduced the split, and nothing has touched it since.

This is a design choice, not a mechanical fix: the ticket itself proposes
one option (merge the two findings into one that names both causes) but
defers to planning if a portable way to distinguish them exists. Filing
`ok`, not `chore`.

### 2026-08-27 16:17:12Z · triage · session · session=89bd58c2-93fb-42d3-819a-b465582b3c60

`triage` ran as session `89bd58c2-93fb-42d3-819a-b465582b3c60`
- replay: `claude --resume 89bd58c2-93fb-42d3-819a-b465582b3c60`
- log: `.project/logs/TICKET-071-triage-89bd58c2.log`

### 2026-08-27 16:17:12Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced with a pytest-style pass (dot, [100%], count, no node name); gate() misreports it as a matched-nothing selector.


### 2026-08-27 · planning

Planned the merge the ticket proposed. I looked for a portable signal that
separates a passing test from a selector that matched nothing and found none:
pytest prints `.` and `1 passed`, cargo prints `test x ... ok`, and
TICKET-064's own case was `test_one = "true"`, which prints nothing. Both are
already a FAIL, so `gate()` and `_base_findings()` each get one finding that
names both causes and keeps the output fence.

Two constraints come from the existing tests and are recorded in
`## Decisions`: the merged text must keep the word `PASSES`
(`test_gate_blocks_a_test_that_already_passes`) and must drop the phrase
`selector matched nothing` (this ticket's repro test).

Scope is one subsystem, `pipeline/core/gate.py`. A register-time check on a
project's test commands stays TICKET-068's question, and no step touches it.

Noticed, and step 7 is the whole of what I do about it:
`tests/test_dispatch.py:1310` hand-writes the old `PASSES -- it must fail
before implementation` string as an example finding. The classifier it tests
does not change.

### 2026-08-27 16:24:41Z · planning · session · session=cbb52a27-ce48-4346-a736-861905ef1251

`planning` ran as session `cbb52a27-ce48-4346-a736-861905ef1251`
- replay: `claude --resume cbb52a27-ce48-4346-a736-861905ef1251`
- log: `.project/logs/TICKET-071-planning-cbb52a27.log`

### 2026-08-27 16:24:41Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: merge each exit-0 pair in gate() and _base_findings() into one finding naming both causes; 9 steps, 4 files.

### 2026-08-27 16:25:01Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector` fails as required
```
[33m"[39;49;00m[33mselector matched nothing[39;49;00m[33m"[39;49;00m [95min[39;49;00m f [94mfor[39;49;00m f [95min[39;49;00m failures), failures[90m[39;49;00m
[1m[31mE       AssertionError: ['`test_thing.py::test_broken` exited 0 but its name never appears in the output -- the selector matched nothing, not ...al output, already quoted in the `## Thread` entry `2026-08-27 16:24:42Z · plan-validation · gate · verdict=FAIL` --*'][0m
[1m[31mE       assert not True[0m
[1m[31mE        +  where True = any(<generator object test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector.<locals>.<genexpr> at 0x7f4f28138ee0>)[0m

[1m[31mtests/test_gate.py[0m:190: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector[0m - AssertionError: ['`test_thing.py::test_broken` exited 0 but its name never ...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.05s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector` fails on base `main` too -- the bug is not already fixed upstream
```
[0m:190: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector[0m - AssertionError: ['`test_thing.py::test_broken` exited 0 but its name never ...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.10s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ml930m7m/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ml930m7m/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 · plan-validation

Tier B: PASS. I scored each item against the code.

Root cause: `gate()` and `_base_findings()` split exit 0 on `node in out`, but
a runner prints the node only when the test FAILS. The predicate is false for
every genuine pass, so the gate names the wrong cause. The plan deletes the
predicate; it does not just make the repro test pass.

Decisions: DEC-065, DEC-017, DEC-046, DEC-061, DEC-050 and DEC-053 all hold.
The merged finding starts with a backtick and matches no `STRUCTURAL_MARKS`
prefix (`pipeline/core/gate.py:54-65`), so it stays substantive, as
`## Decisions` claims. DEC-050:15 and DEC-053 still quote the old string in
prose; they are records, and the plan states the wording does not bind them.

Every step names a file, a line and its replacement text. I opened every cited
line. Two ranges run one line long: `249-256` and `176-185` each include the
`node not in out` arm the same step says to leave unchanged. The intent is
unambiguous.

The riskiest step is 5, the base-run merge, and `## Rollback` covers its
commit.

Regression surface: `test_gate_blocks_a_test_that_already_passes` at
`tests/test_gate.py:160` asserts `PASSES`, which the merged text keeps. Grep
found no consumer of these strings outside the four declared files.

Step 8 (SKILL.md) is a one-line doc sync that no test can pin.

### 2026-08-27 16:31:36Z · plan-validation · session · session=f13dfcd8-5ddb-41ea-b5c5-9cf28f8135b0

`plan-validation` ran as session `f13dfcd8-5ddb-41ea-b5c5-9cf28f8135b0`
- replay: `claude --resume f13dfcd8-5ddb-41ea-b5c5-9cf28f8135b0`
- log: `.project/logs/TICKET-071-plan-validation-f13dfcd8.log`

### 2026-08-27 16:31:36Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight judgment items: it deletes the `node in out` predicate, complies with the six cited decisions, and every step names a file, a line and its replacement text.

### 2026-08-27 16:32:21Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread)

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread)**

### 2026-08-27 16:44:04Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector` fails as required
```
[33m"[39;49;00m[33mselector matched nothing[39;49;00m[33m"[39;49;00m [95min[39;49;00m f [94mfor[39;49;00m f [95min[39;49;00m failures), failures[90m[39;49;00m
[1m[31mE       AssertionError: ['`test_thing.py::test_broken` exited 0 but its name never appears in the output -- the selector matched nothing, not ...al output, already quoted in the `## Thread` entry `2026-08-27 16:43:46Z · plan-validation · gate · verdict=FAIL` --*'][0m
[1m[31mE       assert not True[0m
[1m[31mE        +  where True = any(<generator object test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector.<locals>.<genexpr> at 0x7ffa9cb54fb0>)[0m

[1m[31mtests/test_gate.py[0m:190: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector[0m - AssertionError: ['`test_thing.py::test_broken` exited 0 but its name never ...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m

```
- ok: `tests/test_gate.py::test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector` fails on base `main` too -- the bug is not already fixed upstream
```
[0m:190: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_gate.py::[1mtest_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector[0m - AssertionError: ['`test_thing.py::test_broken` exited 0 but its name never ...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-taugi4lo/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-taugi4lo/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 12ms[0m[0m

```

### 2026-08-27 16:44:05Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-27 · implementing

**implementing** (result: `ok`)

Todo list (all done):
1. Rewrite `test_gate_distinguishes_a_selector_matching_nothing_from_a_real_pass` -> `test_gate_fails_an_exit_zero_test_and_names_both_causes`. Done, verified RED then GREEN.
2. Merge the two exit-0 branches in `gate()` at `pipeline/core/gate.py:249-256`. Done.
3. Run the three named tests, `3 passed`, commit `270d9fb`. Done.
4. Add `test_gate_names_both_causes_when_the_test_exits_zero_on_base`. Done, verified RED then GREEN.
5. Merge the two exit-0 returns in `_base_findings()` at `pipeline/core/gate.py:176-185`. Done.
6. Run the three named tests, `3 passed`, commit `705b503`. Done.
7. Reword the `substantive` literal in `tests/test_dispatch.py:1310`. Done, `1 passed`.
8. Reword the SKILL.md trigger phrase. Done.
9. Full suite + guard, both green, commit `1fbed09`. Done.

Verified RED for both new/rewritten tests before writing the fix: each failed
on the exact string the plan predicted (`matched no test` / `PASSES` absent).
`uv run --group dev pytest -q` -> `352 passed in 17.55s`.
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`.
All 6 acceptance-criteria tests pass individually, confirmed together:
`6 passed in 0.13s`.

No deviation from the plan. Every cited line range matched the file exactly.

### 2026-08-27 16:46:13Z · implementing · session · session=97570a16-5935-45ca-890c-46b3ee25355d

`implementing` ran as session `97570a16-5935-45ca-890c-46b3ee25355d`
- replay: `claude --resume 97570a16-5935-45ca-890c-46b3ee25355d`
- log: `.project/logs/TICKET-071-implementing-97570a16.log`

### 2026-08-27 16:46:13Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed all 9 plan steps via TDD, merged both exit-0 splits into one finding each; full suite 352 passed, guard green.

### 2026-08-27 · review

**review** (result: `ok`)

Reviewed `2691206..1fbed09`. No blocking findings. The delta touches the 4
planned files and nothing else.

Correctness: both merged branches keep the same three-way partition. `gate()`
was `code == 0 and node in out` / `elif code == 0` / `elif node not in out`;
it is now `code == 0` / `elif node not in out`. `_base_findings()` changed the
same way at `pipeline/core/gate.py:176`. No input reaches a different verdict.

I checked that the two new tests are RED against the pre-change gate. With
`test_one = "true"` the old code emits "the selector matched nothing", which
holds neither `PASSES` nor `matched no test`, so both assertions fail.

Wording constraints hold: `tests/test_gate.py:160` (`"PASSES" in f`) passes,
and the repro test finds no `selector matched nothing`. Neither finding starts
with a `STRUCTURAL_MARKS` prefix (`pipeline/core/gate.py:54-65`), so both stay
substantive. Grep found no other reader of the old strings in `pipeline/` or
`tests/`.

Verified: `uv run --group dev pytest -q` -> `352 passed in 17.62s`;
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`; the 6
acceptance tests together -> `6 passed in 0.12s`.

Non-blocking nits:
1. Nit: `test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector`
   asserts only that a phrase is absent. Deleting the exit-0 branch outright
   would leave it green, because the flow falls to `elif node not in out` and
   `ok` stays False. `test_gate_fails_an_exit_zero_test_and_names_both_causes`
   pins the text, so the pair covers the change.
2. Nit: `test_one = "true"` prints nothing, so the merged finding ends in an
   empty fence. `_dedupe()` keeps a blank fence on purpose
   (`pipeline/core/gate.py:138`). TICKET-064's finding had the same shape.

### 2026-08-27 16:49:19Z · review · session · session=67926c00-cc16-4a40-b76e-d88a7216c5de

`review` ran as session `67926c00-cc16-4a40-b76e-d88a7216c5de`
- replay: `claude --resume 67926c00-cc16-4a40-b76e-d88a7216c5de`
- log: `.project/logs/TICKET-071-review-67926c00.log`

### 2026-08-27 16:49:19Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed 2691206..1fbed09: both exit-0 merges keep the same partition, 352 passed, guard green, 6 acceptance tests pass; two non-blocking nits filed.

### 2026-08-27 16:59:24Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 16:59:25Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/071


Rebasing (1/4)
Auto-merging tests/test_gate.py
CONFLICT (content): Merge conflict in tests/test_gate.py
error: could not apply 21a5640... test(TICKET-071): repro a pytest-style pass reported as a matched-nothing selector
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply 21a5640... # test(TICKET-071): repro a pytest-style pass reported as a matched-nothing selector
Auto-merging pipeline/core/gate.py
CONFLICT (content): Merge conflict in pipeline/core/gate.py
Auto-merging pipeline/templates/skills/pipeline-config/SKILL.md
Auto-merging tests/test_dispatch.py
Auto-merging tests/test_gate.py
Automatic merge failed; fix conflicts and then commit the result.

```

### 2026-08-28 01:34:08Z · human · note · by=chezzijr

**resumed** by chezzijr -> `merging`, reset []

### 2026-08-28 01:34:08Z · human · answer · by=chezzijr

**note from chezzijr**

Merge conflict in pipeline/core/gate.py resolved by hand (chezzijr, via Claude Code, on explicit instruction). TICKET-067 had rewritten the same call site to format_test_cmd(); kept that and dropped main's 'if code == 0 and node in out' PASSES block, which is exactly what this ticket replaces. tests/test_gate.py: 45 passed.

### 2026-08-28 01:35:27Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
   |   20 +-
 tests/test_cli.py                                  |  131 +-
 tests/test_config.py                               |  119 +-
 tests/test_dispatch.py                             |  139 ++
 tests/test_gate.py                                 |  160 +++
 tests/test_machine.py                              |   13 +
 tests/test_registry_worktree.py                    |   21 +
 tests/test_stages.py                               |    9 +
 tests/test_stream.py                               |   12 +
 tests/test_tui.py                                  |  101 ++
 tests/test_worktree.py                             |   99 ++
 48 files changed, 8547 insertions(+), 362 deletions(-)
 create mode 100644 .project/decisions/DEC-068.md
 create mode 100644 .project/decisions/DEC-073.md
 create mode 100644 .project/decisions/DEC-074.md
 create mode 100644 .project/decisions/DEC-076.md
 create mode 100644 .project/decisions/DEC-077.md
 create mode 100644 .project/decisions/DEC-078.md
 create mode 100644 .project/decisions/DEC-079.md
 create mode 100644 .project/decisions/DEC-080.md
 create mode 100644 .project/decisions/DEC-083.md
Updating 1f5ae0d..21a0110
Fast-forward
 pipeline/core/gate.py                              | 33 ++++++++-------
 pipeline/templates/skills/pipeline-config/SKILL.md |  2 +-
 tests/test_dispatch.py                             |  2 +-
 tests/test_gate.py                                 | 49 +++++++++++++++++++---
 4 files changed, 65 insertions(+), 21 deletions(-)

```

### 2026-08-28 01:35:27Z · merging · decision

decision recorded as `DEC-071`
