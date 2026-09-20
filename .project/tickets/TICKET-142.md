---
id: TICKET-142
stage: done
class: feature
branch: ticket/142
test_file: tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision
files_declared:
- pipeline/cli/main.py
- pipeline/core/ticket.py
- pipeline/daemon/supervisor.py
- pipeline/stages/_common.md
- pipeline/stages/planning.md
- tests/test_cli.py
- tests/test_dispatch.py
- tests/test_ticket.py
counters:
  plan_validation_attempts: 0
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 4
  plan_files: 8
  no_result: 0
  api_errors: 1
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: holistic-review
  id: 2c613dba-199f-41b3-8310-85d2a0ae7907
  replay: claude --resume 2c613dba-199f-41b3-8310-85d2a0ae7907
  log: .project/logs/TICKET-142-holistic-review-2c613dba.log
  cost_usd: 0.6920229999999998
approved_by: chezzijr
approved_at: '2026-09-20T03:15:50.662601+00:00'
---

## Summary

A stage that finds a factually wrong decision record cannot correct it, so the error keeps steering tickets

Expected change files: `pipeline/core/ticket.py`, `pipeline/daemon/supervisor.py`, `pipeline/cli/main.py`, `pipeline/stages/_common.md`, `pipeline/stages/planning.md`, `tests/test_ticket.py`, `tests/test_dispatch.py`.

Observed in a real project: DEC-125's fifth bullet described code that does not exist (`join_eager_nursery` has no `spawn_replacement_worker` call) and sent two tickets toward a banned mechanism. The stage that found it could not fix it: `.project/decisions/` is outside every stage's writable paths (correctly), and the only correction channel is `supersedes: DEC-<n> -- reason` at the top of a ticket's `## Decisions` (`record_decision()`, `pipeline/core/ticket.py:453`, main at f09c5d6). That channel (a) replaces the whole record, not one wrong claim, (b) is taught only to `planning`, and (c) applies only when the superseding ticket lands (`supervisor.py:145`), so every ticket planned in the meantime still reads the wrong record.

Expected: any stage can report a correction to a named decision record, and the dispatcher -- not the agent -- appends it to that record when the stage finishes, append-only like the existing superseded-by footer (never rewriting the body). `active_decisions()` / `pipeline decisions` / what planning reads shows the correction with the record. The id is hostile input: it must match `SAFE_DEC_ID`, name an existing non-symlinked record, and the text must be validated before it reaches the file (CLAUDE.md invariant 5); a bad correction is a thread `finding`, not a crash. Tests: a stage result carrying a correction for DEC-N leaves DEC-N's original body byte-identical plus one appended correction footer naming the ticket; an id like `../x` or an absent DEC is rejected and the decisions directory is unchanged.

## Reproduction

Test: `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision`

Command: `uv run --group dev pytest -q tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision`

expect: assert '<!-- pipeline:correction -->' in

Output:

```text
E       AssertionError: # DEC-125
E         
E         join_eager_nursery has no replacement-worker call.
E         
E       assert '<!-- pipeline:correction -->' in '# DEC-125\n\njoin_eager_nursery has no replacement-worker call.\n'
```

Committed executable reproduction: `f077ce9` (`test(TICKET-142): reproduce decision correction loss`).

## Digest

- `pipeline/core/ticket.py` owns sidecar parsing, decision validation, atomic decision writes, and `Decision` metadata; add correction parsing and append-only persistence there.
- `pipeline/daemon/supervisor.py:_finish()` is the stage-result entry point; apply a validated correction before deleting the sidecar and advancing the ticket.
- `pipeline/cli/main.py:decision_row()` is the one-line decision listing; expose corrected state without parsing footer text in the CLI.
- `pipeline/stages/_common.md` teaches every stage the correction sidecar field; `pipeline/stages/planning.md` teaches planners to treat corrections as qualifications, not supersessions.
- `tests/test_ticket.py` covers parsing, validation, atomic append, replay idempotency, active status, and symlink refusal; `tests/test_dispatch.py` covers finish-time integration.
- `tests/test_cli.py` covers the corrected listing state while preserving DEC-101's record identifier, replacement identifier, and first-body-line fields.
- Gotcha: malformed YAML uses `loose_result()`, so `correction` must survive both parsers; a replay after the record write must not duplicate its footer.

## Decisions checked

DEC-018 requires decision lookup in the project-root `.project/decisions/`, rejects symlinked records as absent, and resolves only `SAFE_DEC_ID` names.
DEC-101 keeps decision parsing in `Decision`, preserves one listing row per record, and requires superseded state to retain its replacement identifier.
Grep terms: `decision`, `record`, `append`, `footer`, `sidecar`, `claim`, `supersed`, `correct`, `symlink`.

## Plan

1. Extend `tests/test_ticket.py` and `tests/test_dispatch.py` with failing cases for YAML and loose sidecar parsing, byte-preserving append, active-record retention, replay idempotency, invalid ids, missing records, symlinks, multiline text, and finish-time persistence.
2. Add a strict single-line `DEC-<digits> -- <nonempty printable text>` parser and idempotent correction footer writer to `pipeline/core/ticket.py`, then call it from `pipeline/daemon/supervisor.py:_finish()` before sidecar deletion; append invalid corrections as stage `finding` entries and continue the verdict.
3. Add correction metadata to `pipeline/core/ticket.py:Decision`, render corrected state through `pipeline/cli/main.py:decision_row()`, and extend `tests/test_cli.py` so active and superseded rows retain DEC-101's existing fields.
4. Document `correction: DEC-<digits> -- <text>` for every stage in `pipeline/stages/_common.md`, and update `pipeline/stages/planning.md` so corrected records remain binding with their appended qualification.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` exits `0`.
- `uv run --group dev pytest -q tests/test_ticket.py -k correction` exits `0` and covers malformed ids, absent records, symlinks, unsafe text, and replay idempotency.
- `uv run --group dev pytest -q tests/test_cli.py -k decisions` exits `0` and corrected records retain one listing row.
- `uv run --group dev pytest -q` exits `0` with no regressions.
- `rg -n "correction: DEC-<digits>" pipeline/stages/_common.md pipeline/stages/planning.md` prints matches from both prompt files.

## Decisions

Decision corrections are append-only qualifications. They never rewrite a record body or make an active record superseded.

The dispatcher validates the decision id, target file, and single-line correction text before writing. Invalid corrections become thread findings and do not change the decisions directory.

Each correction footer names its source ticket and is idempotent under finish replay. `Decision` owns footer interpretation so CLI callers do not parse record text.

## Rollback

Revert the correction persistence, listing, prompt, and test commits together if corrected records mislead planners.

Riskiest step: step 2 writes shared project-root decision records during every stage finish. If its safety or replay tests fail, revert step 2 and leave corrections unsupported; do not add an unvalidated fallback writer.

## Thread

### 2026-09-18 16:19:00Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-18 16:41:28Z · triage · finding

Reproduced: a `review` sidecar carrying `correction: DEC-125 -- ...` leaves DEC-125 unchanged.

Root cause: `_finish()` validates and adopts only `CLAIMS` fields. `CLAIMS` contains `test_file` and `files_declared`, so it discards `correction` before `advance()`.

The existing `supersedes:` path differs: `record_decision()` runs only after a ticket reaches `done` and appends a replacement footer.

Expected fix files: `pipeline/core/ticket.py`, `pipeline/daemon/supervisor.py`, `pipeline/cli/main.py`, `pipeline/stages/_common.md`, `pipeline/stages/planning.md`, `tests/test_ticket.py`, `tests/test_dispatch.py`.

### 2026-09-18 16:42:22Z · triage · session · session=01a0b563-91d8-7341-b236-45b95a364be5

`triage` ran as session `01a0b563-91d8-7341-b236-45b95a364be5`
- replay: `codex exec resume 01a0b563-91d8-7341-b236-45b95a364be5`
- log: `.project/logs/TICKET-142-triage-e10c9327.log`
- cost: unknown (the harness reported none)
- tokens: 5,320 out (1,307 thinking) · 964,318 in · 902,400 cache read · 0 cache write

### 2026-09-18 16:42:22Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced ignored decision correction

### 2026-09-18 16:47:40Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails, but its output does not mention the expected string '`assert "<!-- pipeline:correction -->" in text, text`'
```
    rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
               "path": path, "tid": "TICKET-001", "stage": "review",
               "session": "s1", "log": log, "wt": d, "meta": snap, "before": None}
    
        assert supervisor._finish(d, rec) == "ok"
        text = record.read_text()
        assert text.startswith(original), text
>       assert "<!-- pipeline:correction -->" in text, text
E       AssertionError: # DEC-125
E         
E         join_eager_nursery has no replacement-worker call.
E         
E       assert '<!-- pipeline:correction -->' in '# DEC-125\n\njoin_eager_nursery has no replacement-worker call.\n'

tests/test_dispatch.py:2359: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================

```
- `files_declared` is empty
- plan step names no declared file: '1. Extend `tests/test_ticket.py` and `tests/test_dispatch.py` with failing cases for YAML and loose sidecar parsing, byte-preserving append, active-record retention, replay idempotency, invalid ids, missing records, symlinks, multiline text, and finish-time persistence.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Add a strict single-line `DEC-<digits> -- <nonempty printable text>` parser and idempotent correction footer writer to `pipeline/core/ticket.py`, then call it from `pipeline/daemon/supervisor.py:_finish()` before sidecar deletion; append invalid corrections as stage `finding` entries and continue the verdict.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: "3. Add correction metadata to `pipeline/core/ticket.py:Decision`, render corrected state through `pipeline/cli/main.py:decision_row()`, and extend `tests/test_cli.py` so active and superseded rows retain DEC-101's existing fields." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '4. Document `correction: DEC-<digits> -- <text>` for every stage in `pipeline/stages/_common.md`, and update `pipeline/stages/planning.md` so corrected records remain binding with their appended qualification.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-18 16:49:22Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails, but its output does not mention the expected string "`assert '<!-- pipeline:correction -->' in '# DEC-125`"
```
    rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
               "path": path, "tid": "TICKET-001", "stage": "review",
               "session": "s1", "log": log, "wt": d, "meta": snap, "before": None}
    
        assert supervisor._finish(d, rec) == "ok"
        text = record.read_text()
        assert text.startswith(original), text
>       assert "<!-- pipeline:correction -->" in text, text
E       AssertionError: # DEC-125
E         
E         join_eager_nursery has no replacement-worker call.
E         
E       assert '<!-- pipeline:correction -->' in '# DEC-125\n\njoin_eager_nursery has no replacement-worker call.\n'

tests/test_dispatch.py:2359: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================

```
- `files_declared` is empty
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '1. Extend `tests/test_ticket.py` and `tests/test_dispatch.py` with failing cases for YAML and loose sidecar parsing, byte-preserving append, active-record retention, replay idempotency, invalid ids, missing records, symlinks, multiline text, and finish-time persistence.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '2. Add a strict single-line `DEC-<digits> -- <nonempty printable text>` parser and idempotent correction footer writer to `pipeline/core/ticket.py`, then call it from `pipeline/daemon/supervisor.py:_finish()` before sidecar deletion; append invalid corrections as stage `finding` entries and continue the verdict.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: "3. Add correction metadata to `pipeline/core/ticket.py:Decision`, render corrected state through `pipeline/cli/main.py:decision_row()`, and extend `tests/test_cli.py` so active and superseded rows retain DEC-101's existing fields." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '4. Document `correction: DEC-<digits> -- <text>` for every stage in `pipeline/stages/_common.md`, and update `pipeline/stages/planning.md` so corrected records remain binding with their appended qualification.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)

### 2026-09-18 16:50:45Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails as required
```
    rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
               "path": path, "tid": "TICKET-001", "stage": "review",
               "session": "s1", "log": log, "wt": d, "meta": snap, "before": None}
    
        assert supervisor._finish(d, rec) == "ok"
        text = record.read_text()
        assert text.startswith(original), text
>       assert "<!-- pipeline:correction -->" in text, text
E       AssertionError: # DEC-125
E         
E         join_eager_nursery has no replacement-worker call.
E         
E       assert '<!-- pipeline:correction -->' in '# DEC-125\n\njoin_eager_nursery has no replacement-worker call.\n'

tests/test_dispatch.py:2359: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================

```
- ok: `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails on base `main` too -- the bug is not already fixed upstream
```
     assert '<!-- pipeline:correction -->' in '# DEC-125\n\njoin_eager_nursery has no replacement-worker call.\n'

tests/test_dispatch.py:2359: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.54s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-twshznl3/base
      Built pipeline @ file:///tmp/pipeline-base-twshznl3/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 68ms

```
- `files_declared` is empty
  -- this finding has now fired 3 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '1. Extend `tests/test_ticket.py` and `tests/test_dispatch.py` with failing cases for YAML and loose sidecar parsing, byte-preserving append, active-record retention, replay idempotency, invalid ids, missing records, symlinks, multiline text, and finish-time persistence.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 3 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '2. Add a strict single-line `DEC-<digits> -- <nonempty printable text>` parser and idempotent correction footer writer to `pipeline/core/ticket.py`, then call it from `pipeline/daemon/supervisor.py:_finish()` before sidecar deletion; append invalid corrections as stage `finding` entries and continue the verdict.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 3 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: "3. Add correction metadata to `pipeline/core/ticket.py:Decision`, render corrected state through `pipeline/cli/main.py:decision_row()`, and extend `tests/test_cli.py` so active and superseded rows retain DEC-101's existing fields." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 3 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '4. Document `correction: DEC-<digits> -- <text>` for every stage in `pipeline/stages/_common.md`, and update `pipeline/stages/planning.md` so corrected records remain binding with their appended qualification.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 3 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)

### 2026-09-18 16:51:04Z · planning · note

Plan maps correction parsing, atomic persistence, finish-time application, CLI visibility, prompt guidance, and safety tests.

The final gate reproduced the defect on this branch and `main`. Its only failures were the expected pre-adoption `files_declared` findings.

Corrected `expect:` to the stable pytest substring `assert '<!-- pipeline:correction -->' in`; the prior backticked string could not match real output.

### 2026-09-18 16:51:21Z · planning · session · session=01a0b565-d032-7b72-91f3-0680503f5e41

`planning` ran as session `01a0b565-d032-7b72-91f3-0680503f5e41`
- replay: `codex exec resume 01a0b565-d032-7b72-91f3-0680503f5e41`
- log: `.project/logs/TICKET-142-planning-05df5bc8.log`
- cost: unknown (the harness reported none)
- tokens: 13,569 out (7,375 thinking) · 2,565,861 in · 2,475,776 cache read · 0 cache write

### 2026-09-18 16:51:21Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned validated append-only decision corrections

### 2026-09-20 02:27:25Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-18 16:49:22Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails on base `main` too -- the bug is not already fixed upstream
```
     assert '<!-- pipeline:correction -->' in '# DEC-125\n\njoin_eager_nursery has no replacement-worker call.\n'

tests/test_dispatch.py:2359: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.54s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-7rtda741/base
      Built pipeline @ file:///tmp/pipeline-base-7rtda741/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 81ms

```

### 2026-09-20 02:37:54Z · plan-validation · session · session=01a0bcad-4af7-7512-9f6d-c51d5eced844

`plan-validation` ran as session `01a0bcad-4af7-7512-9f6d-c51d5eced844`
- replay: `codex exec resume 01a0bcad-4af7-7512-9f6d-c51d5eced844`
- log: `.project/logs/TICKET-142-plan-validation-ebc4c303.log`

### 2026-09-20 02:37:54Z · plan-validation · note

`plan-validation` was refused by the API (terminal_reason=api_error, attempt 1) -- waiting 30 seconds

### 2026-09-20 02:52:56Z · plan-validation · note

`plan-validation` API retry wait expired (attempt 1) -- respawning

### 2026-09-20 03:02:01Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-18 16:49:22Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails on base `main` too -- the bug is not already fixed upstream
```
     assert '<!-- pipeline:correction -->' in '# DEC-125\n\njoin_eager_nursery has no replacement-worker call.\n'

tests/test_dispatch.py:2359: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.55s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-3u74ix16/base
      Built pipeline @ file:///tmp/pipeline-base-3u74ix16/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 76ms

```

### 2026-09-20 03:14:56Z · plan-validation · review · verdict=PASS

**Tier B: PASS** -- eight items, each scored below.

1. Root cause: a stage can write only the ticket and its `.result`. The decisions directory is written by the dispatcher alone, through `record_decision()` (`pipeline/core/ticket.py:453`), which fires from a landed ticket's `## Decisions` and replaces a whole record. No sidecar field qualifies one claim, and `_finish()` (`supervisor.py:1219`) drops an unknown `correction:` key. The plan adds the field, the validated append-only writer and the finish-time call -- it fixes why, not the assertion.
2. Decisions: DEC-018 (root `.project/decisions/`, `SAFE_DEC_ID`, symlink = absent) and DEC-101 (parsing in `Decision`, one row per record, superseded row keeps its replacement id) both constrain this. Steps 2-3 and criteria 2-3 comply; nothing is superseded.
3. Scope: steps 1-4 map to criteria 1/2/4, 3 and 5. No untraceable step.
4. Criteria: falsifiable. The repro asserts the original bytes plus marker, `- corrected-by: TICKET-001` and the text; a writer that rewrote the body fails it.
5. No research left: `Decision`, `loose_result`, `_refuse_symlink`, `_finish()`, `decision_row()` all exist at the named paths.
6. Riskiest step named (step 2) with a revert-and-drop fallback.
7. Regression surface: `all_decisions()`/`active_decisions()` consumers, `decision_row()` (`tests/test_cli.py:1407,1416`), and the shared `_finish()` path. `SIDECAR_KEYS` is read only by `loose_result()` and `correction` is in no `CLAIMS` entry, so the new key cannot reach frontmatter. Criteria 3-4 cover it.
8. Blast radius: `class: feature`, 8 declared files, 4 steps. Matches.

long: eight scored items plus two notes.

Two notes, neither a finding:

- No test distinguishes the project root from the worktree, so an implementation reading `rec["wt"]` instead of `project` would pass while violating DEC-018. The test sets `wt == project`.
- `## Summary` lists 7 expected change files; `files_declared` holds 8, adding `tests/test_cli.py`, which step 3 and criterion 3 need. The frontmatter is right.

### 2026-09-20 03:15:16Z · plan-validation · session · session=6e121f0c-6b94-4e49-89a8-4a2d41a2fbe6

`plan-validation` ran as session `6e121f0c-6b94-4e49-89a8-4a2d41a2fbe6`
- replay: `claude --resume 6e121f0c-6b94-4e49-89a8-4a2d41a2fbe6`
- log: `.project/logs/TICKET-142-plan-validation-6e121f0c.log`
- cost: $0.97 of a $3 cap
- tokens: 9,585 out (5,427 thinking) · 24 in · 495,192 cache read · 48,267 cache write

### 2026-09-20 03:15:16Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan fixes the root cause; all eight items pass

### 2026-09-20 03:15:50Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-20 03:17:42Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails as required
```
    rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
               "path": path, "tid": "TICKET-001", "stage": "review",
               "session": "s1", "log": log, "wt": d, "meta": snap, "before": None}
    
        assert supervisor._finish(d, rec) == "ok"
        text = record.read_text()
        assert text.startswith(original), text
>       assert "<!-- pipeline:correction -->" in text, text
E       AssertionError: # DEC-125
E         
E         join_eager_nursery has no replacement-worker call.
E         
E       assert '<!-- pipeline:correction -->' in '# DEC-125\n\njoin_eager_nursery has no replacement-worker call.\n'

tests/test_dispatch.py:2359: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.46s ===============================

```
- ok: `tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision` fails on base `main` too -- the bug is not already fixed upstream
```
     assert '<!-- pipeline:correction -->' in '# DEC-125\n\njoin_eager_nursery has no replacement-worker call.\n'

tests/test_dispatch.py:2359: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-001: -> verifying {'no_result': 0, 'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_stage_result_appends_a_correction_to_an_existing_decision
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.56s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-4g0dx7wm/base
      Built pipeline @ file:///tmp/pipeline-base-4g0dx7wm/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 87ms

```

### 2026-09-20 03:17:43Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-20 03:20:00Z · implementing · note

Todo (plan steps):
- [ ] 1. failing tests: `tests/test_ticket.py`, `tests/test_dispatch.py`, `tests/test_cli.py`
- [ ] 2. parser + idempotent footer writer in `pipeline/core/ticket.py`; call from `_finish()` in `pipeline/daemon/supervisor.py`
- [ ] 3. `Decision` correction metadata; `decision_row()` in `pipeline/cli/main.py`
- [ ] 4. prompts: `pipeline/stages/_common.md`, `pipeline/stages/planning.md`

### 2026-09-20 03:35:00Z · implementing · note

Implemented in `e2553aa`. All four plan steps done; full suite `674 passed`.

- [x] 1. tests: 8 in `tests/test_ticket.py`, 1 in `tests/test_dispatch.py`, 1 in `tests/test_cli.py`. Each failed first (`AttributeError`, `KeyError: 'correction'`, missing marker).
- [x] 2. `parse_correction()` and `correct_decision()` in `pipeline/core/ticket.py`; `_finish()` calls it before `drop_result()`, with `project` (DEC-018), not `wt`.
- [x] 3. `Decision.corrections`; `decision_row()` shows `(corrected)`; superseded rows keep the replacement id.
- [x] 4. `correction: DEC-<digits>` documented in `_common.md` and `planning.md`.

Decisions in the code: text is capped at 500 characters (`CORRECTION_MAX`) and rejects `<!--`/`-->`, so it cannot forge a footer marker. A replay skips a footer with the same ticket and text.

Not tested: `wt != project`. `_finish()` reads only `project`, but no test separates the two (the note from `plan-validation` stands).

### 2026-09-20 03:23:46Z · implementing · session · session=96e46833-3dce-429b-8f25-4b18ab027e66

`implementing` ran as session `96e46833-3dce-429b-8f25-4b18ab027e66`
- replay: `claude --resume 96e46833-3dce-429b-8f25-4b18ab027e66`
- log: `.project/logs/TICKET-142-implementing-96e46833.log`
- cost: $0.90 of a $10 cap
- tokens: 26,487 out (6,322 thinking) · 48 in · 1,530,790 cache read · 83,436 cache write

### 2026-09-20 03:23:46Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ a sidecar `correction: DEC-<n> -- <text>` is validated and appended to the decision record by _finish(); full suite 674 passed

### 2026-09-20 03:29:00Z · review · finding · severity=blocking

Reviewed `e2553aa` against `main`. One blocking finding.

1. **blocking** -- `correction: null` appends a false `finding` to every ticket. `_common.md:47` now tells every stage to write that line in its sidecar. `_finish()` gates on the KEY, not the value: `if "correction" in res` (`supervisor.py:1354`). YAML reads `correction: null` as `None`, so `correct_decision()` raises `want \`DEC-<digits> -- <text>\`, got None` and appends `` `correction` was not applied: ... ; nothing written`` to the thread of every stage finish. `tests/test_ticket.py:421` lists `None` among the bad inputs and asserts one finding, so the behaviour is deliberate -- and it contradicts the template the same diff ships. `apply_claims()` skips a falsy value for exactly this reason (`machine.py:322`), which is why `test_file: null` in the same block is inert. Fix by testing truthiness in `_finish()`, or by dropping `correction: null` from `_common.md`.

Not blocking, no action required:

2. **minor** -- `decision_row()` pads `state` to 22 (`cli/main.py:259`); `superseded by DEC-011 (corrected)` is 32 characters and shifts the ticket and title columns.
3. **minor** -- a correction lands uncommitted in the main checkout. `commit_record()` sweeps every dirty file under `.project/decisions`, so an unrelated ticket's `chore(...)` commit adopts it at the next `done`. Readers see it immediately; `active_decisions()` reads disk.

Verified: full suite `674 passed in 72.26s`; `rg -n "correction: DEC-<digits>"` matches `_common.md:52` and `planning.md:64`.

### 2026-09-20 03:29:09Z · review · session · session=641c4f97-6b59-4fb4-bfd3-cdc350fb5906

`review` ran as session `641c4f97-6b59-4fb4-bfd3-cdc350fb5906`
- replay: `claude --resume 641c4f97-6b59-4fb4-bfd3-cdc350fb5906`
- log: `.project/logs/TICKET-142-review-641c4f97.log`
- cost: $1.88 of a $6 cap
- tokens: 18,422 out (11,690 thinking) · 50 in · 1,415,070 cache read · 71,201 cache write

### 2026-09-20 03:29:09Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ blocking: `correction: null` -- the line `_common.md` now tells every stage to write -- appends a false `finding` to every ticket

### 2026-09-20 03:40:00Z · implementing · note

Fixed the review's blocking finding in `aa0de4c`.

- [x] `_finish()` now gates on `res.get("correction")`, not the key (`supervisor.py:1354`). `correction: null`, an empty value and `''` report nothing and add no `finding`.
- [x] New test `test_a_null_correction_in_a_stage_result_is_no_correction_and_no_finding` in `tests/test_dispatch.py`. It failed first with `` `DEC-<digits> -- <text>`, got None; nothing written `` and passes now.
- `correct_decision()` still rejects `None` when called directly; `tests/test_ticket.py` is unchanged.
- `tests/test_dispatch.py`, `tests/test_ticket.py`, `tests/test_cli.py`: `244 passed`.

Not changed, per the review's non-blocking list: `decision_row()` state column width (minor 2) and the uncommitted correction file in the main checkout (minor 3).

### 2026-09-20 03:30:35Z · implementing · session · session=f6bffd0f-8301-4231-98c7-259aba1081c8

`implementing` ran as session `f6bffd0f-8301-4231-98c7-259aba1081c8`
- replay: `claude --resume f6bffd0f-8301-4231-98c7-259aba1081c8`
- log: `.project/logs/TICKET-142-implementing-f6bffd0f.log`
- cost: $0.23 of a $10 cap
- tokens: 3,718 out (265 thinking) · 20 in · 303,841 cache read · 32,073 cache write

### 2026-09-20 03:30:35Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ review blocker fixed: _finish() skips a falsy correction, so `correction: null` adds no finding; affected files 244 passed

### 2026-09-20 03:50:00Z · review · note

Reviewed `aa0de4c` against `e2553aa`. No blocking findings. The delta is
`supervisor.py:1355` (`if res.get("correction")`) and one new test.

The previous review's blocking finding is resolved on the YAML path.
`test_a_null_correction_in_a_stage_result_is_no_correction_and_no_finding`
covers `correction: null`, `correction:` and `correction: ''`, and it is not
vacuous: the old key gate passes `None` and `''` to `correct_decision()`, which
appends the finding the test asserts absent. Minors 2 and 3 stand unfixed, as
that review said they may.

1. **minor** -- the same false finding survives on the loose path.
`loose_result()` is line-based, so `correction: null` becomes the STRING
`'null'`, which is truthy. Verified: for a sidecar whose summary carries a
colon, `yaml.safe_load` raises `mapping values are not allowed here` and
`loose_result()` returns `{'result': 'ok', 'summary': 'fixed: the parser',
'correction': 'null'}`. `_finish()` then calls `correct_decision(..., 'null')`,
which appends `` `correction` was not applied: want `DEC-<digits> -- <text>` on
one line, got 'null'; nothing written``. Impact is one `severity=minor` thread
line: the verdict stands, `.project/decisions/` is untouched, and `_view_keep()`
keeps only BLOCKING findings past the last 8 entries. The Digest asked for both
parsers, so record it. The same string reaches `test_file` -- `validate_meta`
returns `[]` for `test_file: 'null'` -- so the fix belongs in `loose_result()`,
which is outside this ticket.

Verified: `uv run --group dev pytest -q` -> `675 passed in 71.36s`;
`rg -n "correction: DEC-<digits>"` matches `_common.md:52` and `planning.md:64`;
worktree clean, no file modified by this stage.

### 2026-09-20 03:34:05Z · review · session · session=8b74958b-d60f-4f9e-b908-08ece0f67d8e

`review` ran as session `8b74958b-d60f-4f9e-b908-08ece0f67d8e`
- replay: `claude --resume 8b74958b-d60f-4f9e-b908-08ece0f67d8e`
- log: `.project/logs/TICKET-142-review-8b74958b.log`
- cost: $1.09 of a $6 cap
- tokens: 9,424 out (4,510 thinking) · 40 in · 782,416 cache read · 45,977 cache write

### 2026-09-20 03:34:06Z · review · transition · to=holistic-review · result=ok · marker=yes

**review -> holistic-review** (result: `ok`)

✓ aa0de4c fixes the blocking `correction: null` finding on the YAML path; 675 passed; one minor left on the loose_result path

### 2026-09-20 03:58:00Z · holistic-review · note

Reviewed `main...aa0de4c` (8 files, +375/-2) against `## Plan`. Coherent. No
blocking finding.

1. The four plan steps each land, and nothing landed beyond them. Step 2's
   writer (`ticket.py:parse_correction`, `correct_decision`) is the only path
   that writes `.project/decisions/`, and `supervisor.py:1354` is its only
   caller. Step 3 adds `Decision.corrections` and one `(corrected)` suffix in
   `decision_row()`; DEC-101's row count, replacement id and title fields are
   unchanged. Steps 1 and 4 match the criteria.
2. The later fix did not undo the earlier one. `aa0de4c` narrowed `_finish()`
   from a key gate to `res.get("correction")`; `e2553aa`'s append, validation
   and idempotency are untouched.
3. Error handling is consistent across the touched files: every failure inside
   `correct_decision()` becomes one `severity=minor` thread `finding` and
   returns None, and the verdict stands. The CLI and the prompts add no second
   failure path.

Residual drift, recorded not fixed: the Digest asked that `correction` survive
both parsers. It survives one. `loose_result()` is line-based, so the shipped
`_common.md:47` template line `correction: null` becomes the truthy STRING
`'null'` and produces the false finding `` want `DEC-<digits> -- <text>` on one
line, got 'null'; nothing written``. The same string reaches `test_file`, so
the defect is `loose_result()`'s, outside this ticket's files. The review at
03:50 found it and called it minor; I agree. Impact is one minor thread line;
`.project/decisions/` is untouched.

Verified: `uv run --group dev pytest -q` -> `675 passed in 72.37s`;
`rg -n "correction: DEC-<digits>"` matches `_common.md:52` and
`planning.md:64`; worktree clean, no file modified by this stage.

### 2026-09-20 03:36:23Z · holistic-review · session · session=2c613dba-199f-41b3-8310-85d2a0ae7907

`holistic-review` ran as session `2c613dba-199f-41b3-8310-85d2a0ae7907`
- replay: `claude --resume 2c613dba-199f-41b3-8310-85d2a0ae7907`
- log: `.project/logs/TICKET-142-holistic-review-2c613dba.log`
- cost: $0.69 of a $6 cap
- tokens: 4,496 out (1,847 thinking) · 20 in · 328,346 cache read · 41,535 cache write

### 2026-09-20 03:36:23Z · holistic-review · transition · to=verifying · result=ok · marker=yes

**holistic-review -> verifying** (result: `ok`)

✓ coherent: the four plan steps all land, 675 passed; residual `correction: null` finding on the loose_result path is recorded, not fixed

### 2026-09-20 03:37:37Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-20 03:37:38Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/142


Current branch ticket/142 is up to date.
Already up to date.
Updating abd11c9..aa0de4c
Fast-forward
 pipeline/cli/main.py          |   2 +
 pipeline/core/ticket.py       |  87 ++++++++++++++++++++++++-
 pipeline/daemon/supervisor.py |   9 ++-
 pipeline/stages/_common.md    |  10 +++
 pipeline/stages/planning.md   |   7 +++
 tests/test_cli.py             |  31 +++++++++
 tests/test_dispatch.py        |  88 ++++++++++++++++++++++++++
 tests/test_ticket.py          | 143 ++++++++++++++++++++++++++++++++++++++++++
 8 files changed, 375 insertions(+), 2 deletions(-)

```

### 2026-09-20 03:37:38Z · merging · decision

decision recorded as `DEC-142`
