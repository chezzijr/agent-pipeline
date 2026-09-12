---
id: TICKET-128
stage: done
class: bugfix
branch: ticket/128
test_file: tests/test_stages.py::test_common_rules_state_the_commit_message_format
files_declared:
- pipeline/stages/_common.md
- pipeline/templates/skills/file-ticket/SKILL.md
- tests/test_stages.py
counters:
  plan_validation_attempts: 0
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 4
  plan_files: 3
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 01a093dc-4fad-7003-bd53-086043790214
  replay: codex exec resume 01a093dc-4fad-7003-bd53-086043790214
  log: .project/logs/TICKET-128-review-3baa6687.log
  cost_usd: null
cheap_route_head: d79c51f1c2b5eb96dc7bf3b3114cecd5c7d671e9
approved_by: chezzijr
approved_at: '2026-09-12T04:07:09.441649+00:00'
---

## Summary

The post-review repair resolves the only blocking finding.

`tests/test_stages.py:81` now requires the literal commit syntax from `pipeline/stages/_common.md:36`. The implementing stage proved the assertion rejects the weakened syntax. It then recorded `42 passed in 0.29s`.

Review found no blocking issues in commit `57de30c test(TICKET-128): enforce commit format syntax`.

## Reproduction

Test: `tests/test_stages.py::test_common_rules_state_the_commit_message_format`

Command:

    uv run --group dev pytest -q tests/test_stages.py::test_common_rules_state_the_commit_message_format

Output:

    AssertionError: _common.md never tells a committing stage how to name its commit

expect: AssertionError: _common.md never tells a committing stage how to name its commit

## Digest

- `tests/test_stages.py` already contains `test_common_rules_state_the_commit_message_format`, which fails against the composed shared prompt.
- `tests/test_stages.py` uses `C.compose_prompt("review")` for shared rules and `C.SKILL_TEMPLATE.read_text()` for packaged skill assertions.
- `pipeline/stages/_common.md` is prepended to every stage prompt, so one commit rule reaches triage and implementing.
- `pipeline/templates/skills/file-ticket/SKILL.md` needs edits in the worked summary and the adjacent split guidance.
- `quick-review` checks changed paths against ticket prose, not `files_declared`; the skill must expose that cheap-route requirement.
- Repository copies under `.claude/skills/` and `.agents/skills/` are symlinks; edit only the packaged template.
- Keep all wording harness-neutral and language-neutral. The commit convention is a Git rule, not a runner or ecosystem rule.

## Decisions checked

DEC-056 requires `pipeline/templates/skills/file-ticket/SKILL.md` to remain the skill's single content source. Its repository installation is a symlink, so this plan leaves installed paths untouched.

Grep terms: `file-ticket`, `skill copies`, `commit message`, `conventional commit`, `files_conflict`, `quick-review`, `two unrelated`, `docs-only`.

## Plan

1. Extend `tests/test_stages.py` with `test_the_file_ticket_skill_requires_expected_change_files` and `test_the_file_ticket_skill_states_when_to_merge_findings`; assert the ticket phrases, run all three focused document tests to observe their missing-guidance failures, then commit as `test(TICKET-128): cover missing filing guidance`.
2. Update `pipeline/stages/_common.md` with one shared rule requiring single-line conventional `<type>(TICKET-nnn): <description>` commits, `test` for reproduction and `fix` or `feat` for implementation; run `tests/test_stages.py::test_common_rules_state_the_commit_message_format`, then commit as `fix(TICKET-128): state conventional commit format`.
3. Update `pipeline/templates/skills/file-ticket/SKILL.md` to require one `## Summary` line naming every expected change file, explain the `quick-review` cheap-route consequence, and add that line to the worked example; run `tests/test_stages.py::test_the_file_ticket_skill_requires_expected_change_files`, then commit as `fix(TICKET-128): require expected change files`.
4. Update `pipeline/templates/skills/file-ticket/SKILL.md` beside the split rule so findings merge only when they share both a file and a cause, while same-file different-cause findings stay separate; run `tests/test_stages.py::test_the_file_ticket_skill_states_when_to_merge_findings` and `uv run --group dev pytest -q tests/test_stages.py`, then commit as `fix(TICKET-128): state finding merge boundary`.

## Acceptance criteria

- `tests/test_stages.py::test_common_rules_state_the_commit_message_format` passes and proves composed stage prompts state the conventional `TICKET-nnn` commit format.
- `tests/test_stages.py::test_the_file_ticket_skill_requires_expected_change_files` passes and proves the filing skill requires expected change files.
- `tests/test_stages.py::test_the_file_ticket_skill_states_when_to_merge_findings` passes and proves the filing skill states the shared-file and shared-cause boundary.
- `uv run --group dev pytest -q tests/test_stages.py` exits `0`.

## Decisions

The shared stage prompt owns the commit convention. Committing stages use single-line `<type>(TICKET-nnn): <description>` messages: `test` for reproduction and `fix` or `feat` for implementation.

A filer names every expected change file in `## Summary`. `quick-review` judges cheap-route scope from ticket prose, not `files_declared`.

Merge findings only when they share both a file and a cause. Findings with different causes remain separate even when they touch one file.

## Rollback

Revert the matching documentation and assertions in `pipeline/stages/_common.md`, `pipeline/templates/skills/file-ticket/SKILL.md`, and `tests/test_stages.py`; the repository skill symlinks need no rollback.

Step 4 is riskiest because it changes ticket grouping policy. If its focused test or review goes red, restore the split-only paragraph and keep findings separate until a replacement rule is approved.

## Thread

### 2026-09-10 02:03:19Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-10 02:04:57Z · triage · finding

The composed shared prompt omits `TICKET-nnn` and `conventional`.
`compose_prompt("review")` includes `_common.md`, so the omission affects every inheriting stage.
The focused test failed with `AssertionError: _common.md never tells a committing stage how to name its commit`.
I committed the reproduction as `d79c51f test(TICKET-128): reproduce missing commit format guidance`.
Expected fix files: `pipeline/stages/_common.md` and `tests/test_stages.py`.

### 2026-09-10 02:05:08Z · triage · session · session=01a0890e-55bc-7f11-b45c-6c61dd86c885

`triage` ran as session `01a0890e-55bc-7f11-b45c-6c61dd86c885`
- replay: `codex exec resume 01a0890e-55bc-7f11-b45c-6c61dd86c885`
- log: `.project/logs/TICKET-128-triage-6414e091.log`
- cost: unknown (the harness reported none)
- tokens: 3,453 out (635 thinking) · 379,317 in · 347,136 cache read · 0 cache write

### 2026-09-10 02:05:08Z · triage · transition · to=implementing · result=chore · marker=yes

**triage -> implementing** (result: `chore`)

✓ Added and committed a failing composed-prompt regression test.

### 2026-09-10 02:05:30Z · implementing · todo

1. [in progress] Add conventional commit guidance with the `TICKET-nnn` scope.
2. [pending] Run the focused composed-prompt regression test.
3. [pending] Commit the scoped prompt change.

### 2026-09-10 02:06:18Z · implementing · finding

Completed all todo items.
Added `type(TICKET-nnn): summary` to `pipeline/stages/_common.md`.
The focused regression passed: `1 passed in 0.05s`.
The related module passed: `40 passed in 0.33s`.
Committed `a0a0af9 fix(TICKET-128): state conventional commit format`.

### 2026-09-10 02:06:31Z · implementing · session · session=01a0890f-ccfb-7580-a332-b63a2f1d45ef

`implementing` ran as session `01a0890f-ccfb-7580-a332-b63a2f1d45ef`
- replay: `codex exec resume 01a0890f-ccfb-7580-a332-b63a2f1d45ef`
- log: `.project/logs/TICKET-128-implementing-c36340a2.log`
- cost: unknown (the harness reported none)
- tokens: 2,850 out (931 thinking) · 384,169 in · 356,096 cache read · 0 cache write

### 2026-09-10 02:06:31Z · implementing · transition · to=quick-review · result=ok · marker=yes

**implementing -> quick-review** (result: `ok`)

✓ Added conventional commit guidance and passed the focused regression plus tests/test_stages.py.

### 2026-09-10 02:07:00Z · quick-review · finding

1. No. Command: `git diff main...HEAD -- tests/test_stages.py`.
   Output:

       +def test_common_rules_state_the_commit_message_format():
       +    f = C.compose_prompt("review")
       +    text = f.read_text()
       +    f.unlink()
       +    assert "TICKET-nnn" in text and "conventional" in text.lower(), \
       +        "_common.md never tells a committing stage how to name its commit"

   The diff adds the test named in Reproduction. Its recorded `AssertionError` cannot prove the added test fails without this diff.

2. Yes. Command: `git diff --name-only main...HEAD`.
   Output:

       pipeline/stages/_common.md
       tests/test_stages.py

   Reproduction names `_common.md` in `AssertionError: _common.md never tells a committing stage how to name its commit`.
   Reproduction names `tests/test_stages.py::test_common_rules_state_the_commit_message_format`.

### 2026-09-10 02:07:26Z · quick-review · session · session=01a08911-13d0-7db3-87cd-685c5f5d7dbd

`quick-review` ran as session `01a08911-13d0-7db3-87cd-685c5f5d7dbd`
- replay: `codex exec resume 01a08911-13d0-7db3-87cd-685c5f5d7dbd`
- log: `.project/logs/TICKET-128-quick-review-294a67d0.log`
- cost: unknown (the harness reported none)
- tokens: 2,019 out (846 thinking) · 161,988 in · 139,776 cache read · 0 cache write

### 2026-09-10 02:07:26Z · quick-review · transition · to=unwinding · result=fail · marker=yes

**quick-review -> unwinding** (result: `fail`)

✓ Review failed: the diff adds the cited reproduction test, so its recorded failure cannot prove it fails without this diff.

### 2026-09-12 03:48:25Z · unwinding · transition · to=planning · result=ok

**unwinding -> planning** (result: `ok`)

unwind exit 0
```
$ git merge-base --is-ancestor d79c51f1c2b5eb96dc7bf3b3114cecd5c7d671e9 HEAD || { echo "d79c51f1c2b5eb96dc7bf3b3114cecd5c7d671e9 is not an ancestor of HEAD -- refusing to unwind"; exit 1; }
git log --oneline d79c51f1c2b5eb96dc7bf3b3114cecd5c7d671e9..HEAD
git reset --hard d79c51f1c2b5eb96dc7bf3b3114cecd5c7d671e9 && git clean -fd


a0a0af9 fix(TICKET-128): state conventional commit format
HEAD is now at d79c51f test(TICKET-128): reproduce missing commit format guidance

```

### 2026-09-12 03:52:38Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_common_rules_state_the_commit_message_format` fails as required
```
ges.py F

=================================== FAILURES ===================================
______________ test_common_rules_state_the_commit_message_format _______________

    def test_common_rules_state_the_commit_message_format():
        f = C.compose_prompt("review")
        text = f.read_text()
        f.unlink()
>       assert "TICKET-nnn" in text and "conventional" in text.lower(), \
            "_common.md never tells a committing stage how to name its commit"
E       AssertionError: _common.md never tells a committing stage how to name its commit
E       assert ('TICKET-nnn' in '# Pipeline stage agent\n\nYou are one stage of a ticket pipeline. You have no memory of other stages and\nyou will no...umbered list with a severity on each.\n\n`result`: `ok` (no blocking findings) | `fail` (blocking findings appended)\n')

tests/test_stages.py:81: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_common_rules_state_the_commit_message_format
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_stages.py::test_common_rules_state_the_commit_message_format` fails on base `main` too -- the bug is not already fixed upstream
```
 to name its commit
E       assert ('TICKET-nnn' in '# Pipeline stage agent\n\nYou are one stage of a ticket pipeline. You have no memory of other stages and\nyou will no...umbered list with a severity on each.\n\n`result`: `ok` (no blocking findings) | `fail` (blocking findings appended)\n')

tests/test_stages.py:81: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_common_rules_state_the_commit_message_format
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-3jkpieds/base
      Built pipeline @ file:///tmp/pipeline-base-3jkpieds/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 94ms

```

### 2026-09-12 03:54:03Z · planning · finding

The four-step plan covers all three documentation rules across three declared files.

`d79c51f` retains the first failing contract. The plan adds two skill contracts before changing either document.

DEC-056 requires editing `pipeline/templates/skills/file-ticket/SKILL.md` while leaving repository symlinks untouched.

Tier A passed. Its gate entry records `**Tier A gate: PASS**` and confirms the reproduction fails on this branch and base `main`.

### 2026-09-12 03:54:40Z · planning · session · session=01a093bb-170a-7a02-a559-fe38bb1f11b7

`planning` ran as session `01a093bb-170a-7a02-a559-fe38bb1f11b7`
- replay: `codex exec resume 01a093bb-170a-7a02-a559-fe38bb1f11b7`
- log: `.project/logs/TICKET-128-planning-d28ea6ac.log`
- cost: unknown (the harness reported none)
- tokens: 11,715 out (5,889 thinking) · 1,542,082 in · 1,465,984 cache read · 0 cache write

### 2026-09-12 03:54:40Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned the three documentation rules, their focused tests, and rollback; Tier A passed.

### 2026-09-12 03:55:48Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_common_rules_state_the_commit_message_format` fails as required
```
ges.py F

=================================== FAILURES ===================================
______________ test_common_rules_state_the_commit_message_format _______________

    def test_common_rules_state_the_commit_message_format():
        f = C.compose_prompt("review")
        text = f.read_text()
        f.unlink()
>       assert "TICKET-nnn" in text and "conventional" in text.lower(), \
            "_common.md never tells a committing stage how to name its commit"
E       AssertionError: _common.md never tells a committing stage how to name its commit
E       assert ('TICKET-nnn' in '# Pipeline stage agent\n\nYou are one stage of a ticket pipeline. You have no memory of other stages and\nyou will no...umbered list with a severity on each.\n\n`result`: `ok` (no blocking findings) | `fail` (blocking findings appended)\n')

tests/test_stages.py:81: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_common_rules_state_the_commit_message_format
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_stages.py::test_common_rules_state_the_commit_message_format` fails on base `main` too -- the bug is not already fixed upstream
```
 to name its commit
E       assert ('TICKET-nnn' in '# Pipeline stage agent\n\nYou are one stage of a ticket pipeline. You have no memory of other stages and\nyou will no...umbered list with a severity on each.\n\n`result`: `ok` (no blocking findings) | `fail` (blocking findings appended)\n')

tests/test_stages.py:81: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_common_rules_state_the_commit_message_format
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-1uhuxvqc/base
      Built pipeline @ file:///tmp/pipeline-base-1uhuxvqc/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 54ms

```

### 2026-09-12 03:57:25Z · plan-validation · finding

1. **Root cause — pass.** Missing authoring rules let stages commit inconsistently and let filers omit scope and grouping boundaries.
2. **Decision conflict — pass.** DEC-056 assigns skill content to `pipeline/templates/skills/file-ticket/SKILL.md`; the plan edits that source only.
3. **Scope discipline — pass.** Every step implements one of the three acceptance criteria or its regression check.
4. **Falsifiable criteria — pass.** Each focused contract fails when its required format, file list, or two-condition boundary is absent.
5. **No research left — pass.** Every step names the file, test function, document location, command, and expected outcome.
6. **Riskiest step — pass.** Step 4 names the grouping-policy risk and restores the split-only paragraph if review rejects it.
7. **Regression surface — pass.** Shared prompts and filing guidance could regress; three focused contracts plus `tests/test_stages.py` cover them.
8. **Blast radius — pass.** This bugfix changes three declared documentation-contract files without runtime code changes.

**Unverified:** Repository symlink targets. The guard reported: “`readlink` is not on the read-only allowlist.” I would run `readlink` on both installed skill paths.

### 2026-09-12 03:57:56Z · plan-validation · session · session=01a093c1-dcb4-72e0-98b8-161aa229d287

`plan-validation` ran as session `01a093c1-dcb4-72e0-98b8-161aa229d287`
- replay: `codex exec resume 01a093c1-dcb4-72e0-98b8-161aa229d287`
- log: `.project/logs/TICKET-128-plan-validation-1453bc85.log`
- cost: unknown (the harness reported none)
- tokens: 4,706 out (2,500 thinking) · 545,283 in · 502,656 cache read · 0 cache write

### 2026-09-12 03:57:56Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Validated all eight plan criteria; the plan is complete, scoped, falsifiable, and decision-compliant.

### 2026-09-12 04:07:09Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-12 04:18:09Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_common_rules_state_the_commit_message_format` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-12 03:55:48Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_stages.py::test_common_rules_state_the_commit_message_format` fails on base `main` too -- the bug is not already fixed upstream
```
 to name its commit
E       assert ('TICKET-nnn' in '# Pipeline stage agent\n\nYou are one stage of a ticket pipeline. You have no memory of other stages and\nyou will no...umbered list with a severity on each.\n\n`result`: `ok` (no blocking findings) | `fail` (blocking findings appended)\n')

tests/test_stages.py:81: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_common_rules_state_the_commit_message_format
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-vbajvtjd/base
      Built pipeline @ file:///tmp/pipeline-base-vbajvtjd/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 48ms

```

### 2026-09-12 04:18:10Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-12 04:19:00Z · implementing · todo

1. [in progress] Add the two filing-skill contract tests and observe each fail.
2. [pending] Add the shared conventional commit rule and pass its focused test.
3. [pending] Add expected-change-file guidance and pass its focused test.
4. [pending] Add the shared-file and shared-cause merge boundary and run the module suite.
5. [pending] Commit each completed plan step.

### 2026-09-12 04:21:00Z · implementing · finding

Completed all todo items.

1. Added two filing-skill contracts in `tests/test_stages.py` and observed all three focused contracts fail.
2. Added the shared conventional commit rule. Its focused test passed: `1 passed in 0.04s`.
3. Added expected-change-file and quick-review guidance, including the worked summary. Its focused test passed: `1 passed in 0.04s`.
4. Added the shared-file and shared-cause merge boundary. Its focused test passed: `1 passed in 0.04s`.
5. The regression module passed: `42 passed in 0.26s`.

Commits: `199e288 test(TICKET-128): cover missing filing guidance`; `e2ae780 fix(TICKET-128): state conventional commit format`; `4619d76 fix(TICKET-128): require expected change files`; `4afb959 fix(TICKET-128): state finding merge boundary`.

### 2026-09-12 04:20:43Z · implementing · session · session=01a093d6-5178-7473-8f96-3dffe9602690

`implementing` ran as session `01a093d6-5178-7473-8f96-3dffe9602690`
- replay: `codex exec resume 01a093d6-5178-7473-8f96-3dffe9602690`
- log: `.project/logs/TICKET-128-implementing-d09cbd6c.log`
- cost: unknown (the harness reported none)
- tokens: 5,102 out (1,088 thinking) · 855,253 in · 807,424 cache read · 0 cache write

### 2026-09-12 04:20:43Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added all three documentation rules, committed four scoped changes, and passed tests/test_stages.py.

### 2026-09-12 04:22:03Z · review · finding

No blocking findings survived review.

1. **Non-blocking:** The five-commit delta matches the approved plan and touches only the three declared files.
2. **Non-blocking:** The new rules match quick-review behavior and preserve the existing filing guidance.
3. **Non-blocking:** `git diff --check` passed. The implementing stage recorded `42 passed in 0.26s` for `tests/test_stages.py`.
4. **Non-blocking:** Review could not rerun the suite. The sandbox returned `Could not create temporary file` under `/home/chezzijr/.cache/uv`.

### 2026-09-12 04:22:03Z · review · finding correction

The refutation audit found one blocking acceptance gap after the preliminary entry above.

1. **Blocking:** `tests/test_stages.py:81` asserts only `TICKET-nnn` and `conventional`. Replacing `<type>(TICKET-nnn): <description>` with `TICKET-nnn: <description>` still passes. The test therefore does not prove the required format or type placement.

Refutation failed. `pipeline/stages/_common.md:36` contains the correct syntax today, but no other assertion constrains that syntax.

### 2026-09-12 04:23:20Z · review · session · session=01a093d8-a756-7871-9761-cc5202df65f1

`review` ran as session `01a093d8-a756-7871-9761-cc5202df65f1`
- replay: `codex exec resume 01a093d8-a756-7871-9761-cc5202df65f1`
- log: `.project/logs/TICKET-128-review-40206f61.log`
- cost: unknown (the harness reported none)
- tokens: 6,383 out (3,820 thinking) · 460,755 in · 426,624 cache read · 0 cache write

### 2026-09-12 04:23:20Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ Found one blocking acceptance gap: the commit-format test does not assert the required syntax.

### 2026-09-12 04:24:00Z · implementing · todo

1. [in progress] Strengthen the commit-format contract with the required literal syntax.
2. [pending] Prove the contract rejects a prompt without that syntax.
3. [pending] Run the focused contract and module suite, then commit the repair.

### 2026-09-12 04:25:00Z · implementing · finding

Completed all todo items.

1. Strengthened `test_common_rules_state_the_commit_message_format` with the required literal syntax.
2. Replaced the rule temporarily with `TICKET-nnn: <description>`. The test failed with `AssertionError: _common.md never tells a committing stage how to name its commit`.
3. Restored the rule. The focused test passed: `1 passed in 0.04s`.
4. The module suite passed: `42 passed in 0.29s`.
5. Committed the repair: `57de30c test(TICKET-128): enforce commit format syntax`.

### 2026-09-12 04:24:43Z · implementing · session · session=01a093db-0dfe-7521-a501-99344c5e5e3d

`implementing` ran as session `01a093db-0dfe-7521-a501-99344c5e5e3d`
- replay: `codex exec resume 01a093db-0dfe-7521-a501-99344c5e5e3d`
- log: `.project/logs/TICKET-128-implementing-9bb2ffe8.log`
- cost: unknown (the harness reported none)
- tokens: 2,736 out (573 thinking) · 392,325 in · 364,288 cache read · 0 cache write

### 2026-09-12 04:24:43Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Enforced the literal conventional commit syntax and passed the focused and module tests.

### 2026-09-12 04:25:40Z · review · finding

No blocking findings survived review.

1. **Non-blocking:** Commit `57de30c` changes only the assertion identified by the prior review.
2. **Non-blocking:** `tests/test_stages.py:81` now matches the required syntax at `pipeline/stages/_common.md:36`.
3. **Non-blocking:** The literal assertion cannot accept the prior weakened `TICKET-nnn: <description>` rule. This refutes the earlier acceptance gap.
4. **Non-blocking:** `git diff --check HEAD^..HEAD` passed. The implementing stage recorded `42 passed in 0.29s`.
5. **Non-blocking:** Review could not rerun tests. The guard returned: "Blocked by the pipeline guard (review): `PYTHONDONTWRITEBYTECODE=1` is not on the read-only allowlist."

### 2026-09-12 04:26:18Z · review · session · session=01a093dc-4fad-7003-bd53-086043790214

`review` ran as session `01a093dc-4fad-7003-bd53-086043790214`
- replay: `codex exec resume 01a093dc-4fad-7003-bd53-086043790214`
- log: `.project/logs/TICKET-128-review-3baa6687.log`
- cost: unknown (the harness reported none)
- tokens: 3,373 out (1,454 thinking) · 348,507 in · 323,200 cache read · 0 cache write

### 2026-09-12 04:26:18Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ The literal syntax assertion resolves the prior blocking finding; no blocking findings survived review.

### 2026-09-12 04:27:28Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-12 05:00:53Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/128


Rebasing (1/6)Rebasing (2/6)Rebasing (3/6)Rebasing (4/6)Rebasing (5/6)Rebasing (6/6)Successfully rebased and updated refs/heads/ticket/128.
Already up to date.
Updating 145faa6..2f08e3f
Fast-forward
 pipeline/stages/_common.md                     |  4 +++-
 pipeline/templates/skills/file-ticket/SKILL.md |  5 +++++
 tests/test_stages.py                           | 29 ++++++++++++++++++++++++++
 3 files changed, 37 insertions(+), 1 deletion(-)

```

### 2026-09-12 05:00:53Z · merging · decision

decision recorded as `DEC-128`
