---
id: TICKET-129
stage: done
class: bugfix
branch: ticket/129
test_file: tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections
files_declared:
- pipeline/core/config.py
- pipeline/core/ticket.py
- pipeline/daemon/supervisor.py
- pipeline/stages/_common.md
- tests/test_dispatch.py
- tests/test_stages.py
- tests/test_ticket.py
counters:
  plan_validation_attempts: 0
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 3
  plan_files: 7
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 01a09553-6afa-79f0-a3f2-5146a845f395
  replay: codex exec resume 01a09553-6afa-79f0-a3f2-5146a845f395
  log: .project/logs/TICKET-129-review-9633209c.log
  cost_usd: null
approved_by: chezzijr
approved_at: '2026-09-12T04:07:09.605576+00:00'
---

## Summary

Review passed with no blocking findings. `_finish()` now rejects duplicate real Summary headings and restores one canonical filer-owned Summary before escalation.

The duplicate, changed, missing, unchanged, fenced, and frontmatterless focused cases pass. Implementation recorded the full suite at `620 passed in 65.83s (0:01:05)`.

## Reproduction

Test: `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections`
Command: `uv run --group dev pytest -q tests/test_dispatch.py -k finish_preserves_the_human_summary --tb=short`

Output:

    E   AssertionError: assert 'agent replacement' == 'human scope'
    E
    E     - human scope
    E     + agent replacement

expect: AssertionError: assert 'agent replacement' == 'human scope'

## Digest

- `pipeline/daemon/supervisor.py::_finish()` restores frontmatter from `rec["meta"]` but currently adopts `agent_body` wholesale before tamper checks.
- `pipeline/core/ticket.py::sections()` already compares fence-aware section contents; a matching replacement helper must reuse `_fenced()` and preserve unrelated body bytes.
- `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections` is the committed reproduction at `0a403ef`; it currently proves preservation only.
- `pipeline/stages/_common.md` rule 4 tells every stage to rewrite `## Summary`; `pipeline/core/config.py::compose_prompt()` repeats that instruction for interactive stages.
- `tests/test_stages.py` exercises both batch and interactive common prompts. `pipeline/templates/skills/file-ticket/SKILL.md` already assigns `## Summary` to the human.
- Gotcha: Summary tampering must restore the snapshot value, retain other agent sections, drop the sidecar, and preserve DEC-110's neutral snapshot-diff wording.

## Decisions checked

DEC-016 requires every ticket-heading scan to reuse `_fenced()` and preserve plain Markdown storage.
DEC-023 currently assigns `## Summary` to the last stage; this plan supersedes that ownership clause while retaining its bounded-view rules.
DEC-048 requires `_finish()` to restore snapshot frontmatter; selective Summary protection must not admit agent frontmatter.
DEC-110 requires tamper reports to name changed values without accusing the stage of authorship.
DEC-113 requires frontmatterless agent output to remain recoverable, while malformed YAML envelopes still raise.

## Plan

1. Add fence, duplicate, and missing-section cases in `tests/test_ticket.py`; implement `pipeline/core/ticket.py::replace_section()` to canonicalize one real heading while preserving unrelated bytes.
2. Extend `tests/test_dispatch.py` with changed, missing, and unchanged Summary outcomes; update `pipeline/daemon/supervisor.py::_finish()` to compare parsed sections, restore Summary, adopt other prose, and escalate mismatches as `tampered`.
3. Add batch and interactive ownership assertions in `tests/test_stages.py`; update `pipeline/stages/_common.md` and `pipeline/core/config.py` to forbid Summary edits while retaining assigned-section and Thread writes.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_ticket.py -k replace_section --tb=short` exits `0`; the named tests cover fenced headings, duplicates, and missing Summary insertion.
- `uv run --group dev pytest -q tests/test_dispatch.py -k 'finish_preserves_the_human_summary or frontmatterless_agent_ticket' --tb=short` exits `0`; changed Summary returns `tampered`, restores human text, and retains agent Reproduction.
- `uv run --group dev pytest -q tests/test_stages.py -k 'summary or interactive_prompt' --tb=short` exits `0`; no composed prompt tells a stage to rewrite Summary.
- `uv run --group dev pytest -q` exits `0` with no dispatcher-suite failures.

## Decisions

supersedes: DEC-023 -- `## Summary` is filer-owned, so stages no longer rewrite it.

`## Summary` is protected prose. `_finish()` compares its parsed value with the pre-spawn snapshot, restores the snapshot, and reports mismatches as tampering.

The dispatcher still adopts every other agent prose section. The bounded view still trims only `## Thread`, keeps human and blocking entries, and announces every omission.

Stage prompts direct agents to their assigned sections and `## Thread`. They never direct an agent to rewrite `## Summary`.

## Rollback

Revert the commits touching `pipeline/core/ticket.py`, `pipeline/daemon/supervisor.py`, `pipeline/stages/_common.md`, `pipeline/core/config.py`, `tests/test_ticket.py`, `tests/test_dispatch.py`, and `tests/test_stages.py`.

Step 1's fence-aware body splice is riskiest. If its focused tests fail, retain full agent-body adoption and do not ship selective ownership.

## Thread

### 2026-09-12 03:16:59Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-12 03:25:00Z · triage · finding

Reproduced and committed `0a403ef`.

`_finish()` assigns `t = replace(snap, body=agent_body)`, so it restores metadata but adopts every prose section.

The focused test changes Summary and Reproduction in the agent body.
It fails because Summary becomes `agent replacement` instead of `human scope`.
Reproduction remains `agent evidence`, proving the failure is selective-section ownership, not a malformed ticket.

Root cause: `_finish()` does not compare or restore protected prose sections.
The nearest working behavior is frontmatter restoration from `snap` before saving.

Expected fix scope: `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py`.

### 2026-09-12 03:18:56Z · triage · session · session=01a0939e-5557-7722-8675-8fdca9adb159

`triage` ran as session `01a0939e-5557-7722-8675-8fdca9adb159`
- replay: `codex exec resume 01a0939e-5557-7722-8675-8fdca9adb159`
- log: `.project/logs/TICKET-129-triage-0953c60a.log`
- cost: unknown (the harness reported none)
- tokens: 3,911 out (541 thinking) · 453,718 in · 416,512 cache read · 0 cache write

### 2026-09-12 03:18:56Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced `_finish()` replacing the snapshot Summary with agent prose.

### 2026-09-12 03:26:29Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections` fails as required
```
e_text("result: ok\nsummary: ✓ reviewed\n")
        log = d / ".project" / "logs" / "TICKET-001.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
               "path": path, "tid": "TICKET-001", "stage": "quick-review",
               "session": "s1", "log": log, "wt": d, "meta": snap, "before": None}
    
        supervisor.finish(d, rec)
    
        t = Ticket.load(path)
>       assert t.section("Summary") == "human scope"
E       AssertionError: assert 'agent replacement' == 'human scope'
E         
E         - human scope
E         + agent replacement

tests/test_dispatch.py:2175: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================

```
- ok: `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections` fails on base `main` too -- the bug is not already fixed upstream
```
assert 'agent replacement' == 'human scope'
E         
E         - human scope
E         + agent replacement

tests/test_dispatch.py:2175: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.51s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-9f9co3mu/base
      Built pipeline @ file:///tmp/pipeline-base-9f9co3mu/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 68ms

```
- `files_declared` is empty
- plan step names no declared file: '1. Add fence, duplicate, and missing-section cases in `tests/test_ticket.py`; implement `pipeline/core/ticket.py::replace_section()` to canonicalize one real heading while preserving unrelated bytes.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Extend `tests/test_dispatch.py` with changed, missing, and unchanged Summary outcomes; update `pipeline/daemon/supervisor.py::_finish()` to compare parsed sections, restore Summary, adopt other prose, and escalate mismatches as `tampered`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Add batch and interactive ownership assertions in `tests/test_stages.py`; update `pipeline/stages/_common.md` and `pipeline/core/config.py` to forbid Summary edits while retaining assigned-section and Thread writes.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-12 03:28:09Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections` fails as required
```
e_text("result: ok\nsummary: ✓ reviewed\n")
        log = d / ".project" / "logs" / "TICKET-001.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
               "path": path, "tid": "TICKET-001", "stage": "quick-review",
               "session": "s1", "log": log, "wt": d, "meta": snap, "before": None}
    
        supervisor.finish(d, rec)
    
        t = Ticket.load(path)
>       assert t.section("Summary") == "human scope"
E       AssertionError: assert 'agent replacement' == 'human scope'
E         
E         - human scope
E         + agent replacement

tests/test_dispatch.py:2175: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================

```
- ok: `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections` fails on base `main` too -- the bug is not already fixed upstream
```
assert 'agent replacement' == 'human scope'
E         
E         - human scope
E         + agent replacement

tests/test_dispatch.py:2175: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-8felgnai/base
      Built pipeline @ file:///tmp/pipeline-base-8felgnai/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 78ms

```

### 2026-09-12 03:29:00Z · planning · finding

Planned Summary ownership enforcement across dispatcher, ticket parsing, and stage prompts.

The plan supersedes DEC-023's stage-owned Summary clause. It retains DEC-023's bounded-view rules.

Tier A passed after injecting the sidecar's seven `files_declared` paths in memory. The direct pre-adoption run found only the expected empty-declaration errors.

### 2026-09-12 03:29:17Z · planning · session · session=01a093a0-1563-75f0-8f01-f1a3a0fc73f0

`planning` ran as session `01a093a0-1563-75f0-8f01-f1a3a0fc73f0`
- replay: `codex exec resume 01a093a0-1563-75f0-8f01-f1a3a0fc73f0`
- log: `.project/logs/TICKET-129-planning-1cc27099.log`
- cost: unknown (the harness reported none)
- tokens: 16,707 out (10,286 thinking) · 1,698,470 in · 1,616,128 cache read · 0 cache write

### 2026-09-12 03:29:17Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned protected Summary merging, tamper reporting, and aligned stage prompts.

### 2026-09-12 03:59:04Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections` fails as required
```
e_text("result: ok\nsummary: ✓ reviewed\n")
        log = d / ".project" / "logs" / "TICKET-001.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
               "path": path, "tid": "TICKET-001", "stage": "quick-review",
               "session": "s1", "log": log, "wt": d, "meta": snap, "before": None}
    
        supervisor.finish(d, rec)
    
        t = Ticket.load(path)
>       assert t.section("Summary") == "human scope"
E       AssertionError: assert 'agent replacement' == 'human scope'
E         
E         - human scope
E         + agent replacement

tests/test_dispatch.py:2175: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections` fails on base `main` too -- the bug is not already fixed upstream
```
assert 'agent replacement' == 'human scope'
E         
E         - human scope
E         + agent replacement

tests/test_dispatch.py:2175: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.49s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-n2gzz6jh/base
      Built pipeline @ file:///tmp/pipeline-base-n2gzz6jh/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 82ms

```

### 2026-09-12 04:00:06Z · plan-validation · finding

Plan validation passed all eight scored items.

- **Root cause — pass:** `_finish()` adopts `agent_body` wholesale after restoring only frontmatter. The plan protects snapshot Summary while retaining other prose.
- **Decision conflict — pass:** DEC-016, DEC-048, DEC-110, and DEC-113 constrain the implementation. The plan complies and explicitly supersedes DEC-023's ownership clause.
- **Scope discipline — pass:** All seven files implement protected ownership, prompt alignment, or regression coverage required by the criteria.
- **Falsifiable criteria — pass:** Wrong parsing, merging, or prompt wording makes a named command fail. The criteria state exit `0` and behavioral assertions.
- **No research left — pass:** Every step names concrete files and functions. Each behavior maps to focused tests.
- **Riskiest step — pass:** Fence-aware replacement risks corrupting unrelated Markdown. The rollback retains wholesale adoption and blocks selective ownership if focused tests fail.
- **Regression surface — pass:** Tests cover fences, duplicates, missing sections, changed and unchanged Summary, other prose, frontmatterless recovery, prompts, and the full suite.
- **Blast radius — pass:** Seven files form one dispatcher ownership fix plus tests. This fits the bugfix class.

Unverified: None.

### 2026-09-12 04:00:55Z · plan-validation · session · session=01a093c4-d631-7481-946f-51af8f2fa0a4

`plan-validation` ran as session `01a093c4-d631-7481-946f-51af8f2fa0a4`
- replay: `codex exec resume 01a093c4-d631-7481-946f-51af8f2fa0a4`
- log: `.project/logs/TICKET-129-plan-validation-7d52e685.log`
- cost: unknown (the harness reported none)
- tokens: 3,984 out (2,015 thinking) · 393,221 in · 349,824 cache read · 0 cache write

### 2026-09-12 04:00:55Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Validated all eight plan-quality items; the plan is implementation-ready.

### 2026-09-12 04:07:09Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-12 04:28:35Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-12 03:26:29Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections` fails on base `main` too -- the bug is not already fixed upstream
```
assert 'agent replacement' == 'human scope'
E         
E         - human scope
E         + agent replacement

tests/test_dispatch.py:2175: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_finish_preserves_the_human_summary_while_adopting_agent_sections
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.49s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-metp29kg/base
      Built pipeline @ file:///tmp/pipeline-base-metp29kg/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 47ms

```

### 2026-09-12 04:28:37Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-12 04:31:00Z · implementing · finding

Todo:

1. Add `replace_section()` tests for fences, duplicates, and missing headings.
2. Protect Summary in `_finish()` and test changed, missing, and unchanged outcomes.
3. Remove Summary rewrite instructions and test batch and interactive prompts.

### 2026-09-12 04:39:30Z · implementing · finding

Completed all three plan steps and committed `0027300` (`Protect filer-owned ticket summaries`).

1. Added fence-aware `replace_section()` coverage for duplicate and missing Summary headings.
2. Restored changed or missing Summary values, retained other prose, dropped the sidecar, and escalated as `tampered`.
3. Removed Summary rewrite instructions from batch and interactive prompts.

DEC-113 recovery remains intact for frontmatterless agent bodies.

Checks passed:

- `uv run --group dev pytest -q tests/test_ticket.py tests/test_dispatch.py tests/test_stages.py` — `175 passed in 16.12s`
- `uv run --group dev pytest -q` — `619 passed in 65.85s (0:01:05)`

### 2026-09-12 04:39:51Z · implementing · session · session=01a093df-e4ad-73c1-b2b4-978d41269ad6

`implementing` ran as session `01a093df-e4ad-73c1-b2b4-978d41269ad6`
- replay: `codex exec resume 01a093df-e4ad-73c1-b2b4-978d41269ad6`
- log: `.project/logs/TICKET-129-implementing-4a51fb06.log`
- cost: unknown (the harness reported none)
- tokens: 12,843 out (4,153 thinking) · 2,453,751 in · 2,362,112 cache read · 0 cache write

### 2026-09-12 04:39:51Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Protected filer-owned Summary prose and committed the dispatcher, prompt, and regression updates.

### 2026-09-12 04:52:31Z · review · finding · severity=blocking

1. **Blocking** — Duplicate headings bypass Summary protection. `sections()` overwrites earlier values at `pipeline/core/ticket.py:172` and `:177`. `_finish()` compares only the last value at `pipeline/daemon/supervisor.py:1243-1248`. Change the first Summary to `agent replacement`, then append a second Summary matching `human scope`. The comparison matches, `_finish()` advances, and the changed protected prose persists. No validator rejects duplicates. `replace_section()` supports duplicates but runs only after a mismatch. Add a dispatcher regression and restore one canonical Summary before applying the verdict.

Focused ticket, dispatcher, and prompt acceptance tests passed. The restricted full-suite run produced unrelated failures and stopped progressing; the implementing stage recorded `619 passed in 65.85s`.

### 2026-09-12 04:53:14Z · review · session · session=01a093ea-2e77-7131-a688-a35335198617

`review` ran as session `01a093ea-2e77-7131-a688-a35335198617`
- replay: `codex exec resume 01a093ea-2e77-7131-a688-a35335198617`
- log: `.project/logs/TICKET-129-review-c0b8d735.log`
- cost: unknown (the harness reported none)
- tokens: 13,784 out (7,704 thinking) · 2,367,641 in · 2,301,952 cache read · 0 cache write

### 2026-09-12 04:53:14Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ Duplicate Summary headings bypass protected-prose tamper detection.

### 2026-09-12 05:01:02Z · implementing · session · session=01a093fd-6c4d-77a0-a745-262b690cfd24

`implementing` ran as session `01a093fd-6c4d-77a0-a745-262b690cfd24`
- replay: `codex exec resume 01a093fd-6c4d-77a0-a745-262b690cfd24`
- log: `.project/logs/TICKET-129-implementing-89b31dbf.log`

### 2026-09-12 05:01:02Z · implementing · note

`implementing` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-12 05:01:12Z · implementing · session · session=01a093fd-9208-7a52-92fa-5aad98e9898e

`implementing` ran as session `01a093fd-9208-7a52-92fa-5aad98e9898e`
- replay: `codex exec resume 01a093fd-9208-7a52-92fa-5aad98e9898e`
- log: `.project/logs/TICKET-129-implementing-ec546d20.log`

### 2026-09-12 05:01:12Z · implementing · escalation

`implementing` wrote no .result sidecar 2 times

### 2026-09-12 11:09:13Z · human · note · by=chezzijr

**resumed** by chezzijr -> `implementing`, reset ['no_result']

### 2026-09-12 11:10:00Z · implementing · todo

1. Add a duplicate Summary dispatcher regression and verify RED.
2. Canonicalize protected Summary headings before the dispatcher advances.
3. Run focused and full tests, then commit the fix.

### 2026-09-12 11:14:08Z · implementing · finding

✓ Duplicate Summary headings now escalate as `tampered` and collapse to one filer-owned Summary.

1. Added `test_finish_rejects_duplicate_summary_that_hides_an_earlier_change`.
   It failed first: `assert 'ok' == 'tampered'`.
2. Added fence-aware `section_count()` and reject any agent ticket without exactly one real Summary heading.
   `replace_section()` restores one canonical snapshot Summary before escalation.
3. Committed `72b75b9 fix(TICKET-129): reject duplicate summaries`.
   Focused tests passed: 3 dispatcher, 1 ticket, 2 prompt tests.
   Full suite passed: `620 passed in 65.83s (0:01:05)`.

### 2026-09-12 11:14:25Z · implementing · session · session=01a0954e-d269-7dd1-8776-92734823724c

`implementing` ran as session `01a0954e-d269-7dd1-8776-92734823724c`
- replay: `codex exec resume 01a0954e-d269-7dd1-8776-92734823724c`
- log: `.project/logs/TICKET-129-implementing-3d12501b.log`
- cost: unknown (the harness reported none)
- tokens: 6,519 out (2,882 thinking) · 1,058,057 in · 999,680 cache read · 0 cache write

### 2026-09-12 11:14:25Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Rejected duplicate Summary headings and passed all tests.

### 2026-09-12 11:16:40Z · review · finding

No blocking findings.

The prior duplicate-heading bypass is resolved. `section_count()` ignores fenced headings and requires exactly one real Summary. `_finish()` restores one canonical snapshot Summary before returning `tampered`.

Focused review tests passed:

- `tests/test_ticket.py -k replace_section`: `1 passed, 31 deselected in 0.08s`
- Summary dispatcher outcomes: `4 passed, 100 deselected in 0.12s`
- `git diff --check 72b75b9^ 72b75b9` exited `0`.

### 2026-09-12 11:17:06Z · review · session · session=01a09553-6afa-79f0-a3f2-5146a845f395

`review` ran as session `01a09553-6afa-79f0-a3f2-5146a845f395`
- replay: `codex exec resume 01a09553-6afa-79f0-a3f2-5146a845f395`
- log: `.project/logs/TICKET-129-review-9633209c.log`
- cost: unknown (the harness reported none)
- tokens: 4,544 out (2,084 thinking) · 584,470 in · 550,912 cache read · 0 cache write

### 2026-09-12 11:17:06Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Duplicate Summary bypass is closed; focused review tests pass

### 2026-09-12 11:18:16Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-12 11:18:20Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/129


Rebasing (1/3)Rebasing (2/3)Rebasing (3/3)Successfully rebased and updated refs/heads/ticket/129.
Already up to date.
Updating d5854e9..97b30af
Fast-forward
 pipeline/core/config.py       |   3 +-
 pipeline/core/ticket.py       |  42 +++++++++++++++++
 pipeline/daemon/supervisor.py |  18 +++++++
 pipeline/stages/_common.md    |   6 +--
 tests/test_dispatch.py        | 107 ++++++++++++++++++++++++++++++++++++++++++
 tests/test_stages.py          |  12 +++++
 tests/test_ticket.py          |  14 ++++++
 7 files changed, 198 insertions(+), 4 deletions(-)

```

### 2026-09-12 11:18:20Z · merging · decision

decision recorded as `DEC-129`
