---
id: TICKET-043
stage: done
class: bugfix
branch: ticket/043
test_file: tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence
files_declared:
- CLAUDE.md
- pipeline/core/fence.py
- pipeline/core/machine.py
- tests/test_fence.py
- tests/test_machine.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: f429f595-3c45-4597-baad-1f13f20ed31a
  log: .project/logs/TICKET-043-review-f429f595.log
approved_by: chezzijr
approved_at: '2026-08-24T08:30:53.109903+00:00'
---

## Summary

Fixed and reviewed. `review` found nothing blocking in the delta, commits
792859d and f53e302 on branch `ticket/043`.
`machine.FENCED["pipeline/core/machine.py"]` now names `("transition",
"CONTROL_FIELDS", "FENCED")`, so a diff that edits only the `FENCED` dict
trips `fenced_touches()`.

Changed, five files: `pipeline/core/machine.py` (added `"FENCED"` to the
symbol tuple, a comment, "eight"->"nine"), `CLAUDE.md` (added backticked
`FENCED` to the fence sentence, line 216), `pipeline/core/fence.py`
("eight"->"nine", line 3), `tests/test_machine.py` ("eight"->"nine" plus
`FENCED` in the docstring, line 56), `tests/test_fence.py` (one new test:
`test_an_unfenced_symbol_in_machine_py_still_merges_unattended`).

`review` re-ran the evidence: `uv run --group dev pytest -q` -> `248 passed`,
the four acceptance-criteria nodes -> `4 passed`, the "eight things" grep ->
no output, and `fenced_touches(Path("."), "main")` ->
`['pipeline/core/machine.py:FENCED']`. `review` could not run
`./pipeline/hooks/test_dangerous_commands.py`; the guard blocks it for a
read-only stage. `implementing` reports exit 0 and the delta touches no file
under `pipeline/hooks/`.

Two non-blocking nits stand, both in `tests/test_fence.py`: the
`test_editing_the_fenced_dict_itself_trips_the_fence` docstring describes the
pre-fix tuple, and line 2 imports `Path` unused.

Ordering consequence, intended: once `FENCED` is fenced, every future ticket
that changes a fence entry parks at `awaiting-merge`. This ticket's own diff
touches `FENCED` too, so `verifying` is expected to park it there next, not
route it straight to `merging`.

Out of scope, for a new ticket: `pipeline/core/fence.py` is not in `FENCED`, so
a ticket can still edit `fenced_touches()` and merge unattended.

## Reproduction

`tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence`

Command: `uv run --group dev pytest -q tests/test_fence.py -k editing_the_fenced_dict_itself_trips_the_fence`

Output:

    AssertionError: assert [] != []
     +  where [] = fenced_touches(PosixPath('/tmp/tmplz6mqsmz'), 'main')

expect: assert [] != []

The test builds a minimal `pipeline/core/machine.py` with `CONTROL_FIELDS`,
`transition()` and `FENCED` (mapping `.project/pipeline.toml` to `None`),
commits it, then adds one key to `FENCED` and nothing else. `fenced_touches()`
with the real `FENCED` returns `[]` for that diff.

## Digest

Files touched: `pipeline/core/machine.py` (the `FENCED` dict, lines 18-33), `CLAUDE.md` (the fence sentence, lines 215-217), `pipeline/core/fence.py` (module docstring, line 3), `tests/test_machine.py` (docstring, lines 56-59), `tests/test_fence.py` (one new test).
Key functions: `fenced_touches()` at `pipeline/core/fence.py:64` reads `machine.FENCED`; `symbol_lines()` at `pipeline/core/fence.py:39` resolves a name to its `ast` span. `symbol_lines(machine_src, "FENCED")` returns `(18, 33)` today -- verified by running it -- so a hunk anywhere in the dict literal trips once the symbol is listed.
Entry point: `finish_suite()` at `pipeline/daemon/supervisor.py:712` calls `fenced_touches()`. A non-empty hit list yields `ok`, which parks the ticket at `awaiting-merge`; only `clean` reaches `merging`.
Gotcha 1: `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` compares the backticked tokens of the `CLAUDE.md` paragraph ending "requires human review before merge" against the `FENCED` names, in both directions. Adding `"FENCED"` to the dict without adding a backticked `FENCED` token to that sentence fails that test. A `machine.FENCED` token does not match: the test strips only `()`.
Gotcha 2: the fenced span is the assignment only. The comment at `pipeline/core/machine.py:14-17` sits above line 18, outside `(18, 33)`, so a diff touching only that comment still does not trip the fence.
Gotcha 3: the word "eight" counts the fenced things in three places: `pipeline/core/fence.py:3`, `pipeline/core/machine.py:14`, `tests/test_machine.py:56`. It becomes nine. Commit 783170c corrected the same count on 2026-08-23; no test enforces it.
Gotcha 4: this ticket's own diff edits `FENCED`, so `verifying` parks it at `awaiting-merge`. That is the intended new behaviour, not a failure.
Out of scope: `pipeline/core/fence.py` is not itself in `FENCED`, so a ticket can still edit `fenced_touches()` unattended. Reported in `## Thread`, not planned here.

## Decisions checked

DEC-031 (TICKET-031, active) binds this change. It records that the fence matches symbols, not whole files, because every ticket that adds a stage edits `pipeline/core/machine.py`, and whole-filing it would train the human to rubber-stamp. This plan complies: it adds one symbol to the existing tuple and does not set the entry to `None`. DEC-031 also requires the `CLAUDE.md` fence items to stay backticked in their own paragraph; step 6 keeps that shape.
DEC-038 (TICKET-038, active) records that a trailing `/` in a `FENCED` key means prefix. Untouched by this plan.
DEC-034 (TICKET-034, active) and DEC-037 (TICKET-037, active) record why `strip_settings_sources()` and `.project/pipeline.toml` are entries. Both stay.
Grep terms used in `.project/decisions/`: `FENCED`, `fence`, `awaiting-merge`, `machine.py`.

## Plan

1. Run `uv run --group dev pytest -q tests/test_fence.py -k editing_the_fenced_dict_itself_trips_the_fence` and confirm `tests/test_fence.py` fails with `AssertionError: assert [] != []`.
2. In `pipeline/core/machine.py`, change line 26 to `    "pipeline/core/machine.py": ("transition", "CONTROL_FIELDS", "FENCED"),`.
3. In `pipeline/core/machine.py`, insert three comment lines directly above that entry, indented four spaces: "FENCED itself: without it a ticket adds or removes an entry and the fence never sees it -- TICKET-037 and TICKET-038 both merged such a diff unattended on 2026-08-23."
4. In `pipeline/core/machine.py`, change the comment on line 14 from `# The eight things` to `# The nine things`.
5. Re-run the command from step 1 against `tests/test_fence.py` and expect `1 passed`.
6. Run `uv run --group dev pytest -q tests/test_stages.py -k fenced_list_matches_the_rule_file` and expect a failure reading `CLAUDE.md says {...}, machine.FENCED says {...}`, because `CLAUDE.md` does not yet name `FENCED`.
7. In `CLAUDE.md` line 216, insert a backticked `FENCED` and a comma between `CONTROL_FIELDS` and `strip_settings_sources()`, so the list reads `transition()`, `validate_meta()`, `CONTROL_FIELDS`, `FENCED`, `strip_settings_sources()`, each item backticked, with the blank line above the paragraph kept.
8. Re-run the command from step 6 and expect `1 passed`, proving `CLAUDE.md` and `machine.FENCED` agree again.
9. In `pipeline/core/fence.py` line 3, change `fences eight things off` to `fences nine things off`.
10. In `tests/test_machine.py`, edit the `test_a_fenced_file_is_gated_before_merge` docstring: `fences eight things` becomes `fences nine things`, and the list gains a backticked `FENCED` after `` `CONTROL_FIELDS`, ``.
11. Append to `tests/test_fence.py` a test `test_an_unfenced_symbol_in_machine_py_still_merges_unattended`, built on `git_project()`: create `d/pipeline/core/machine.py` holding `CONTROL_FIELDS`, `BOUNDS = {'bugfix': 2}`, a `FENCED` dict mapping `".project/pipeline.toml"` to `None`, and `def transition(stage, result)`; run `sh("git add -A && git commit -qm commit-machine")`; rewrite the file with `body.replace("'bugfix': 2", "'bugfix': 3")`; run `sh("git add -A")`; assert `fenced_touches(d, "main") == []`.
12. Give that new test in `tests/test_fence.py` a docstring saying the machine.py entry names symbols, not the whole file (DEC-031), so a ticket that edits only `BOUNDS` merges unattended, and the test fails if someone widens the entry to `None`.
13. Run `uv run --group dev pytest -q tests/test_fence.py tests/test_stages.py tests/test_machine.py` and expect no failures.
14. Run `uv run --group dev pytest -q`, which includes `tests/test_fence.py`, then run `./pipeline/hooks/test_dangerous_commands.py`; expect both green.
15. Commit `pipeline/core/machine.py`, `CLAUDE.md`, `pipeline/core/fence.py`, `tests/test_machine.py` and `tests/test_fence.py` as `fix(TICKET-043): the FENCED dict is itself fenced`.

## Acceptance criteria

- `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence` passes. It fails today with `assert [] != []`.
- `tests/test_fence.py::test_an_unfenced_symbol_in_machine_py_still_merges_unattended` passes. It fails if the `pipeline/core/machine.py` entry is widened to `None`.
- `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` passes, proving `CLAUDE.md` and `machine.FENCED` both name `FENCED`.
- `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge` passes unchanged.
- `uv run --group dev pytest -q` reports no failures, and `./pipeline/hooks/test_dangerous_commands.py` exits 0.
- The count prose says nine: `grep -rn "eight things" pipeline/core/machine.py pipeline/core/fence.py tests/test_machine.py` prints nothing. No pytest node covers the count; this grep is the check.

## Decisions

**`FENCED` fences itself, and the ordering consequence is intended.** Once
`"FENCED"` is in the tuple for `pipeline/core/machine.py`, every future ticket
that adds or removes a fence entry parks at `awaiting-merge` for a human.
TICKET-037 and TICKET-038 each added an entry and merged unattended on
2026-08-23; the same gap let a ticket delete `pipeline/hooks/dangerous-commands.py`
from the dict unattended. Do not remove the symbol to make a later fence change
land on its own -- that is the failure mode `CLAUDE.md` refuses to automate.

**The entry stays a symbol tuple, not `None`.** DEC-031 records why: every
ticket that adds a stage edits `pipeline/core/machine.py`, and a whole-file
fence would park most of them and train the human to rubber-stamp.
`tests/test_fence.py::test_an_unfenced_symbol_in_machine_py_still_merges_unattended`
fails if someone widens it.

**The comment above `FENCED` is outside the fenced span.** `symbol_lines()`
returns the assignment's own `ast` range, so a diff touching only
`pipeline/core/machine.py:14-17` does not trip. Anything load-bearing goes
inside the dict literal, where the fence sees it.

## Rollback

Revert the implementation commit. The minimum revert is `pipeline/core/machine.py`
line 26 back to `("transition", "CONTROL_FIELDS")`; the fence then stops parking
`FENCED` edits and `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence`
goes red again. Revert `CLAUDE.md` in the same commit, or
`tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` fails on the
drift. Nothing else reads `FENCED`, so no state or data migrates.

## Thread

### 2026-08-24 08:05:50Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 · triage · reproduced

Reproduced. `machine.FENCED["pipeline/core/machine.py"]` names
`("transition", "CONTROL_FIELDS")`, not `FENCED` itself, so
`fenced_touches()` misses a diff that only edits the `FENCED` dict.

Added `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence`,
committed at 5bd7321. It builds a fake `machine.py` with real `CONTROL_FIELDS`,
`transition()` and `FENCED` symbols, edits only `FENCED`, and asserts
`fenced_touches` reports a hit. It fails now with `assert [] != []`.

Expected fix: add `"FENCED"` to the symbol tuple for
`pipeline/core/machine.py` in `machine.FENCED`. This touches the guard
definition itself, so it needs the human `awaiting-merge` gate per
`CLAUDE.md`, same as any other `FENCED` entry. Check whether
`tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` or the
`CLAUDE.md` fence prose need updating to match.

result: ok, test_file: `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence`

### 2026-08-24 08:07:54Z · triage · session · session=bba45d4b-e791-4b9b-921b-1d563a0339cd

`triage` ran as session `bba45d4b-e791-4b9b-921b-1d563a0339cd`
- replay: `claude --resume bba45d4b-e791-4b9b-921b-1d563a0339cd`
- log: `.project/logs/TICKET-043-triage-bba45d4b.log`

### 2026-08-24 08:07:54Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced with a failing test on FENCED entry for machine.py missing the FENCED symbol itself.

### 2026-08-24 · planning · plan written

Plan written: 15 steps over five files -- `pipeline/core/machine.py`,
`CLAUDE.md`, `pipeline/core/fence.py`, `tests/test_machine.py`,
`tests/test_fence.py`.

Two findings the ticket did not carry.

1. `CLAUDE.md` must gain a backticked `FENCED` in the fence sentence.
`tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` compares
that paragraph's backticked tokens against the `FENCED` names in both
directions, so the code change alone turns that test red. Steps 6 to 8 cover it.

2. Out of scope, worth a new ticket: `pipeline/core/fence.py` is not itself in
`FENCED`. A ticket can still edit `fenced_touches()` or `symbol_lines()` -- the
code that runs the check -- and merge unattended. That needs its own
reproduction, so I did not widen this ticket to cover it.

Verified while planning: `symbol_lines(machine_src, "FENCED")` returns
`(18, 33)`, so the whole dict literal trips once the symbol is listed. The
comment above it (`pipeline/core/machine.py:14-17`) sits outside that span and
still does not trip.

result: ok

### 2026-08-24 08:12:36Z · planning · session · session=8fae454c-1713-421b-af2b-98b47e0f61a0

`planning` ran as session `8fae454c-1713-421b-af2b-98b47e0f61a0`
- replay: `claude --resume 8fae454c-1713-421b-af2b-98b47e0f61a0`
- log: `.project/logs/TICKET-043-planning-8fae454c.log`

### 2026-08-24 08:12:36Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: 15 steps over five files; adds "FENCED" to the machine.py symbol tuple and keeps CLAUDE.md in sync.

### 2026-08-24 08:12:48Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence` fails as required
```
e" / "core" / "machine.py"
        machine.parent.mkdir(parents=True)
        body = (
            "CONTROL_FIELDS = ('stage',)\n\n\n"
            "FENCED = {\n"
            '    ".project/pipeline.toml": None,\n'
            "}\n\n\n"
            "def transition(stage, result):\n"
            "    return stage\n"
        )
        machine.write_text(body)
        sh("git add -A && git commit -qm commit-machine")
        assert fenced_touches(d, "main") == []
        machine.write_text(body.replace(
            '".project/pipeline.toml": None,\n',
            '".project/pipeline.toml": None,\n    ".project/extra.toml": None,\n',
        ))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpb5s3co6d'), 'main')

tests/test_fence.py:73: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
 None,\n',
            '".project/pipeline.toml": None,\n    ".project/extra.toml": None,\n',
        ))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpgsxtx_0e'), 'main')

tests/test_fence.py:73: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ac7vq0xl/base
      Built pipeline @ file:///tmp/pipeline-base-ac7vq0xl/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 08:14:35Z · plan-validation · note

`plan-validation` was interrupted; lease released

### 2026-08-24 08:27:05Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence` fails as required
```
e" / "core" / "machine.py"
        machine.parent.mkdir(parents=True)
        body = (
            "CONTROL_FIELDS = ('stage',)\n\n\n"
            "FENCED = {\n"
            '    ".project/pipeline.toml": None,\n'
            "}\n\n\n"
            "def transition(stage, result):\n"
            "    return stage\n"
        )
        machine.write_text(body)
        sh("git add -A && git commit -qm commit-machine")
        assert fenced_touches(d, "main") == []
        machine.write_text(body.replace(
            '".project/pipeline.toml": None,\n',
            '".project/pipeline.toml": None,\n    ".project/extra.toml": None,\n',
        ))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpn4l1nmdc'), 'main')

tests/test_fence.py:73: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
 None,\n',
            '".project/pipeline.toml": None,\n    ".project/extra.toml": None,\n',
        ))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmp1f_8skix'), 'main')

tests/test_fence.py:73: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-nysomhvq/base
      Built pipeline @ file:///tmp/pipeline-base-nysomhvq/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 · plan-validation · judgment

**PASS on all eight items.** Scores below.

1. Root cause. `fenced_touches()` resolves a span per symbol named in the
tuple. `pipeline/core/machine.py` names only `transition` and
`CONTROL_FIELDS`, so a hunk inside the `FENCED` literal (lines 18-33) overlaps
neither span and the loop appends nothing. Step 2 adds the missing name; it
fixes the cause, not the assertion.
2. Decisions. Read `.project/decisions/DEC-031.md` in full. It requires
symbols, not whole files, and backticked items in their own paragraph. Steps 2
and 7 comply. No supersede needed.
3. Scope. Every step traces to a criterion except step 3, the three-line
comment. It sits inside the dict literal, matching the comments already on the
`claude-code.toml` and `.project/stages/` entries. Accepted.
4. Falsifiable. Criterion 2 fails if the entry is widened to `None`:
`symbols is None` appends the path, and the assert `== []` breaks.
5. No research left. Every step names a file and a line or a symbol.
6. Riskiest step: step 2. `## Rollback` states the minimum revert.
7. Regression surface. `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file`
is the one test the code change turns red; steps 6-8 cover it.
`tests/test_fence.py::test_a_change_to_the_committed_config_trips_the_fence`
builds no `machine.py`, so `ranges is None` skips the file.
8. Blast radius. `bugfix`, five files: one code line, one prose line, three
count words, one new test.

Verified while scoring. `FENCED` holds eight things today: three whole-file
entries, `transition`, `CONTROL_FIELDS`, `validate_meta`,
`strip_settings_sources`, `.project/stages/`. Nine is right. `grep -i eight`
finds the fence count in exactly the three files steps 4, 9 and 10 name; the
other hits are unrelated. `PKG.parent` is the worktree root, so step 7 edits
the `CLAUDE.md` that `test_the_fenced_list_matches_the_rule_file` reads.

Out of scope, noticed while scoring: `pipeline/harnesses/claude-code.toml:80`
says that file "is also NOT in `machine.FENCED`". It is, at
`pipeline/core/machine.py:25`. Stale comment, no code effect, not this plan's
to fix.

result: ok

### 2026-08-24 08:30:11Z · plan-validation · session · session=fe378122-5a36-4808-a5a3-10fc32d450f5

`plan-validation` ran as session `fe378122-5a36-4808-a5a3-10fc32d450f5`
- replay: `claude --resume fe378122-5a36-4808-a5a3-10fc32d450f5`
- log: `.project/logs/TICKET-043-plan-validation-fe378122.log`

### 2026-08-24 08:30:11Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan validation passed all eight items: root cause named, DEC-031 complied with, criteria falsifiable, rollback covers the riskiest step.

### 2026-08-24 08:30:53Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 08:31:52Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence` fails as required
```
e" / "core" / "machine.py"
        machine.parent.mkdir(parents=True)
        body = (
            "CONTROL_FIELDS = ('stage',)\n\n\n"
            "FENCED = {\n"
            '    ".project/pipeline.toml": None,\n'
            "}\n\n\n"
            "def transition(stage, result):\n"
            "    return stage\n"
        )
        machine.write_text(body)
        sh("git add -A && git commit -qm commit-machine")
        assert fenced_touches(d, "main") == []
        machine.write_text(body.replace(
            '".project/pipeline.toml": None,\n',
            '".project/pipeline.toml": None,\n    ".project/extra.toml": None,\n',
        ))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpa_3y6k1a'), 'main')

tests/test_fence.py:73: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
: None,\n',
            '".project/pipeline.toml": None,\n    ".project/extra.toml": None,\n',
        ))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpr5e_2ial'), 'main')

tests/test_fence.py:73: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_editing_the_fenced_dict_itself_trips_the_fence
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-2x6xqxfy/base
      Built pipeline @ file:///tmp/pipeline-base-2x6xqxfy/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 08:31:52Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 · implementing · todo

1. [x] Confirm `test_editing_the_fenced_dict_itself_trips_the_fence` RED.
2. [x] Add `"FENCED"` to the `pipeline/core/machine.py` symbol tuple.
3. [x] Add the three-line comment above the entry.
4. [x] "eight"->"nine" in `pipeline/core/machine.py:14`.
5. [x] Confirm the test GREEN.
6. [x] Confirm `test_the_fenced_list_matches_the_rule_file` RED.
7. [x] Add backticked `FENCED` to `CLAUDE.md` line 216.
8. [x] Confirm that test GREEN.
9. [x] "eight"->"nine" in `pipeline/core/fence.py:3`.
10. [x] "eight"->"nine" and add `FENCED` in `tests/test_machine.py:56`.
11. [x] Add `test_an_unfenced_symbol_in_machine_py_still_merges_unattended`.
12. [x] Docstring on that test states the DEC-031 rationale.
13. [x] Run `test_fence.py`, `test_stages.py`, `test_machine.py`: all pass.
14. [x] Run full `pytest -q` and the guard script: both green.
15. [x] Commit the five files as `fix(TICKET-043): the FENCED dict is itself fenced`.

### 2026-08-24 · implementing · report

Executed all 15 plan steps, TDD throughout. Verified RED for both new/changed
tests before each fix, verified GREEN after.

For step 11 I additionally proved RED for the new guard test
`test_an_unfenced_symbol_in_machine_py_still_merges_unattended`: temporarily
widened the real `machine.py` entry to `None`, ran the test, got
`AssertionError: assert ['pipeline/core/machine.py'] == []`, then reverted the
temporary edit before continuing. That edit was never committed.

Final: `uv run --group dev pytest -q` -> `248 passed`.
`./pipeline/hooks/test_dangerous_commands.py` -> exit 0.
`grep -rn "eight things" pipeline/core/machine.py pipeline/core/fence.py
tests/test_machine.py` -> no output.
Committed f53e302 on branch `ticket/043`, files:
`pipeline/core/machine.py`, `CLAUDE.md`, `pipeline/core/fence.py`,
`tests/test_machine.py`, `tests/test_fence.py`.

No deviation from `## Plan`. This diff itself touches `FENCED`, so
`verifying`/gating is expected to park it at `awaiting-merge` per
`## Digest` gotcha 4 -- not a failure.

### 2026-08-24 08:34:12Z · implementing · session · session=12485410-253d-4969-b421-51f88927ffa8

`implementing` ran as session `12485410-253d-4969-b421-51f88927ffa8`
- replay: `claude --resume 12485410-253d-4969-b421-51f88927ffa8`
- log: `.project/logs/TICKET-043-implementing-12485410.log`

### 2026-08-24 08:34:12Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added FENCED to the machine.py symbol tuple, updated CLAUDE.md and the eight/nine count prose, added the guard test; 248 tests pass, guard script exits 0, committed f53e302.

### 2026-08-24 · review · report

**review: no blocking findings.** I reviewed the branch-point delta, commits
792859d and f53e302, five files.

Verified against the acceptance criteria, in this worktree:

- `uv run --group dev pytest -q` -> `248 passed in 10.46s`.
- The four named nodes run green by node id -> `4 passed in 0.06s`.
- `grep -rn "eight things" pipeline/core/machine.py pipeline/core/fence.py
  tests/test_machine.py` -> no output, exit 1.
- `fenced_touches(Path("."), "main")` -> `['pipeline/core/machine.py:FENCED']`,
  so the fix trips on this ticket's own diff. Gotcha 4 holds.
- `symbol_lines(machine_src, "FENCED")` -> `(18, 36)`. The three new comment
  lines sit at 26-28, inside the dict literal and inside the fenced span, as
  `## Decisions` requires.
- DEC-031 holds: the entry stays a symbol tuple, not `None`.

Non-blocking findings:

1. minor. The `test_editing_the_fenced_dict_itself_trips_the_fence` docstring
   in `tests/test_fence.py` still states `machine.FENCED` maps
   `pipeline/core/machine.py` to `("transition", "CONTROL_FIELDS")`. That was
   true at 792859d and is false after f53e302.
2. minor. `tests/test_fence.py:2` imports `Path` and no test uses it. No linter
   runs in this repo, so nothing fails.
3. evidence gap, not a defect. I could not run
   `./pipeline/hooks/test_dangerous_commands.py`: the guard blocked it --
   "`test_dangerous_commands.py` is not on the read-only allowlist". The delta
   touches no file under `pipeline/hooks/`. `implementing` reports exit 0.

### 2026-08-24 08:38:26Z · review · session · session=f429f595-3c45-4597-baad-1f13f20ed31a

`review` ran as session `f429f595-3c45-4597-baad-1f13f20ed31a`
- replay: `claude --resume f429f595-3c45-4597-baad-1f13f20ed31a`
- log: `.project/logs/TICKET-043-review-f429f595.log`

### 2026-08-24 08:38:26Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed 792859d..f53e302: no blocking findings; 248 passed, fence trips on this ticket's own diff, two minor nits recorded.

### 2026-08-24 08:42:07Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 08:42:07Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/043


Already up to date.
Updating 8a1597f..f53e302
Fast-forward
 CLAUDE.md                |  2 +-
 pipeline/core/fence.py   |  2 +-
 pipeline/core/machine.py |  7 +++++--
 tests/test_fence.py      | 54 ++++++++++++++++++++++++++++++++++++++++++++++++
 tests/test_machine.py    |  4 ++--
 5 files changed, 63 insertions(+), 6 deletions(-)

```

### 2026-08-24 08:42:07Z · merging · decision

decision recorded as `DEC-043`
