---
id: TICKET-145
stage: done
class: feature
branch: ticket/145
test_file: tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
files_declared:
- README.md
- pipeline/core/config.py
- pipeline/core/gate.py
- pipeline/templates/pipeline.toml
- pipeline/templates/skills/file-ticket/SKILL.md
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_config.py
- tests/test_gate.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 3
  plan_files: 8
  no_result: 0
  api_errors: 1
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: dbba8c99-7199-423a-ab3d-928f3a8a42d9
  replay: claude --resume dbba8c99-7199-423a-ab3d-928f3a8a42d9
  log: .project/logs/TICKET-145-review-dbba8c99.log
  cost_usd: 2.140522
approved_by: chezzijr
approved_at: '2026-09-20T02:33:45.148475+00:00'
---

## Summary

The Tier A gate has no way past a test that has stopped failing, and no way to quarantine a flaky test

Expected change files: `pipeline/core/gate.py`, `pipeline/core/config.py`, `pipeline/templates/pipeline.toml`, `README.md`, `tests/test_gate.py`, `tests/test_config.py`.

Two dead ends in the same gate, filed together because both live in `pipeline/core/gate.py` and both end in an escalation a human cannot clear from the stage that hit it.

1. A branch whose fix already landed has no way forward. `gate()` reports `LOAD-FLAKY` when the ticket's test exits 0 in the worktree AND on base -- `pipeline/core/gate.py:835`, on main at f9d1063: "It exited 0 on base `<base>` too ... no re-plan can make it fail. Only `triage` may write `test_file` (`CLAIMS`)". That verdict escalates and charges nothing (`gate_result()`), so a ticket whose implementation landed while it waited is stuck: `planning` cannot commit, and no stage it can be resumed to can satisfy Tier A. Observed on a ticket whose steps 1-7 had already landed; it escalated with the work done.
2. One flaky test blocks every unrelated ticket. `test_suite` is run whole, so a racy test from an unrelated ticket makes every later ticket's suite red, and nothing can exempt one node. A project can hand-edit `test_suite` to add `--deselect`, but then the exclusion is invisible to `pipeline ls`, unattributed, and permanent.

Expected: (a) the `LOAD-FLAKY` finding names a concrete recovery command that works, and a ticket resumed onto the stage it names passes Tier A rather than returning to the same verdict -- the gate must distinguish "this test never failed" from "this branch already carries the fix", which it already does at `gate.py:859` for the case where base still fails. (b) A project can quarantine named tests, e.g. `[gate] quarantine = ["tests/test_x.py::test_racy"]` in `.project/pipeline.toml`, applied to the SUITE run only, never to the ticket's own `test_file`, and each quarantined node is named in the gate's thread entry so it cannot rot unnoticed. Tests: a ticket whose test passes in the worktree and on base produces a finding naming a recovery stage, and the recovery passes; a quarantined node does not make `suite_ran()` report pre-existing breakage; a quarantine entry naming the ticket's own `test_file` is refused.

## Reproduction

Test: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only`

Command: `uv run --group dev pytest -q tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only`

Failure:

```
AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
```

expect: suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first

## Digest

- `pipeline/core/config.py` will expose a validated `[gate].quarantine` selector list from the committed or pinned project config.
- `pipeline/core/gate.py` will combine quarantine selectors with ticket tests only for `test_suite_without_new`, including its base confirmation run.
- `pipeline/core/gate.py::gate()` can read `Ticket.stage`; normal revalidation follows a Tier A pass, while manual resume is an explicit human recovery.
- `tests/test_gate.py` already contains the failing quarantine reproduction; add recovery, overlap-refusal, and gate-thread visibility coverage beside the load-flaky tests.
- `tests/test_config.py` covers quarantine table, list, string, and safe-selector validation without importing the new helper into `tests/test_gate.py`.
- `pipeline/templates/pipeline.toml`, `README.md`, and `pipeline/templates/skills/pipeline-config/SKILL.md` document suite-only quarantine, visible gate entries, and the revalidating recovery command.
- `pipeline/templates/skills/file-ticket/SKILL.md` will tell filers how humans recover a `LOAD-FLAKY` escalation without letting the filing session resume it.
- Gotcha: quarantine selectors must remain `shlex.quote`d through `format_tests_cmd()` and must never reach `test_one` or `_copy_tests()`.

## Decisions checked

- DEC-017 -- keep base reproduction checks limited to ticket tests; quarantine selectors belong only to suite exclusion commands.
- DEC-029 -- `revalidating` rebases before Tier A and routes a passing gate to implementation, so it is the existing recovery stage.
- DEC-037 -- read `[gate].quarantine` through `project_config()` so committed or pinned config remains authoritative.
- DEC-067 -- reuse `format_tests_cmd()` for quoting and repeated selector prefixes; keep helper unit tests out of `tests/test_gate.py` imports.
- DEC-090 -- preserve the base-failure proof and the initial both-pass rejection; add only the explicit `revalidating` recovery exception.
- DEC-109 -- superseded below because its unconditional rule that `revalidating` keeps the load-flaky failure makes recovery impossible.
- DEC-137 -- retain confirmed-suite reruns and apply the same quarantine exclusions to worktree and base suite runs.

## Plan

1. Add `tests/test_config.py` cases for absent, malformed, unsafe, and valid quarantine values, then implement `pipeline/core/config.py::gate_quarantine()` to parse `[gate]`, require a list of safe test selectors, preserve order, and raise `PipelineError` with the offending key or entry.
2. Extend `tests/test_gate.py` with `test_gate_names_revalidating_recovery_and_accepts_it`, `test_gate_refuses_quarantining_its_own_test`, and gate-thread assertions, then update `pipeline/core/gate.py` to name `pipeline resume <id> --stage revalidating`, accept a worktree/base double-pass only while `Ticket.stage == "revalidating"`, reject quarantine overlap with `test_file`, append one visible `ok:` line naming every quarantined selector, and pass the de-duplicated ticket-plus-quarantine list only to worktree and base `test_suite_without_new` formatting.
3. Document `[gate] quarantine`, its suite-only scope, overlap refusal, visible gate entry, and load-flaky recovery in `pipeline/templates/pipeline.toml`, `README.md`, and `pipeline/templates/skills/pipeline-config/SKILL.md`; update `pipeline/templates/skills/file-ticket/SKILL.md` to identify `pipeline resume <id> --stage revalidating` as the human recovery command while retaining its ban on agent-initiated resume, and state that committed or pinned config remains authoritative.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` exits 0.
- `uv run --group dev pytest -q tests/test_gate.py::test_gate_names_revalidating_recovery_and_accepts_it tests/test_gate.py::test_gate_refuses_quarantining_its_own_test` exits 0; the first test observes `LOAD-FLAKY` at plan-validation and a Tier A pass at revalidating.
- `uv run --group dev pytest -q tests/test_config.py::test_gate_quarantine_validates_named_nodes` exits 0 for valid selectors and all malformed-shape or unsafe-selector cases.
- `grep -q "quarantine" pipeline/templates/pipeline.toml` exits 0, and README plus the packaged pipeline-config skill name the same suite-only behavior.
- `grep -q "LOAD-FLAKY" pipeline/templates/skills/file-ticket/SKILL.md` exits 0, and that skill names `pipeline resume <id> --stage revalidating` as a command only the human may run.
- `uv run --group dev pytest -q` exits 0 with no new failures relative to the current branch baseline.
- The `test_dangerous_commands` guard suite remains green when `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

supersedes: DEC-109 -- its unconditional rule that `revalidating` keeps load-flaky as a failure makes the advertised recovery return to the same verdict.

At `plan-validation`, a test passing in both trees remains `LOAD-FLAKY`, keeps its leading anti-forgery marker, and escalates without charging a counter. Its finding names `pipeline resume <id> --stage revalidating`.

At `revalidating`, the same double-pass is accepted. Normal entry follows a successful plan-validation; manual entry requires an explicit human resume. DEC-090's base-failure proof still governs first-time validation.

`[gate].quarantine` contains safe test selectors excluded only from `test_suite_without_new` in the worktree and base confirmation run. The gate refuses overlap with the ticket's `test_file` and records every active selector in its thread entry.

## Rollback

Step 2 is riskiest because its stage-aware exception changes Tier A acceptance. If `test_gate_names_revalidating_recovery_and_accepts_it` or the full suite goes red, remove the `revalidating` exception and restore the plan-validation `LOAD-FLAKY` behavior before reverting the quarantine integration in `pipeline/core/gate.py`; then revert `pipeline/core/config.py`, `tests/test_gate.py`, `tests/test_config.py`, `pipeline/templates/pipeline.toml`, `README.md`, `pipeline/templates/skills/pipeline-config/SKILL.md`, and `pipeline/templates/skills/file-ticket/SKILL.md` together so config and both human interfaces cannot advertise inactive recovery or quarantine behavior.

## Thread

### 2026-09-20 · implementing · todo

1. Add validated `[gate].quarantine` configuration coverage and parser.
2. Add gate recovery, overlap, and quarantine-visibility coverage and implementation.
3. Document suite-only quarantine and human `LOAD-FLAKY` recovery.
4. Run focused tests, the full suite, and the command guard; then commit.

### 2026-09-20 01:53:55Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-20 02:02:00Z · triage · reproduction

The gate ignores `[gate] quarantine` when it formats `test_suite_without_new`.

`gate()` passes only `test_file` to `format_tests_cmd()`. The configured racy node never reaches the suite selector.

Added and committed `fe3fdce` (`test(TICKET-145): reproduce ignored gate quarantine`).

The regression test fails with the recorded `expect:` text. It configures a quarantine node and requires the suite selector to contain it.

Expected implementation files: `pipeline/core/gate.py`, `pipeline/core/config.py`, `pipeline/templates/pipeline.toml`, `README.md`, `tests/test_gate.py`, and `tests/test_config.py`.

### 2026-09-20 02:13:32Z · triage · session · session=01a0bc95-4b8d-76e3-8fc5-c5a499c657a4

`triage` ran as session `01a0bc95-4b8d-76e3-8fc5-c5a499c657a4`
- replay: `codex exec resume 01a0bc95-4b8d-76e3-8fc5-c5a499c657a4`
- log: `.project/logs/TICKET-145-triage-19ae3ade.log`
- cost: unknown (the harness reported none)
- tokens: 4,751 out (1,956 thinking) · 578,363 in · 513,024 cache read · 0 cache write

### 2026-09-20 02:13:32Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Added a failing regression for ignored gate quarantine nodes.

### 2026-09-20 02:20:04Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails as required
```
eature.
        """
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "echo test_broken; exit 1"\n'
            'test_suite = "true"\n'
            'test_suite_without_new = "echo {test:--deselect } | '
            "grep -Fq -- '--deselect tests/test_racy.py::test_racy' || "
            '{ echo 1 failed; exit 1; }"\n'
            '[gate]\n'
            'quarantine = ["tests/test_racy.py::test_racy"]\n')
        ok, failures = gate(d, "TICKET-001")
>       assert ok, failures
E       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.38s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-lzuz5yq5/base
      Built pipeline @ file:///tmp/pipeline-base-lzuz5yq5/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 75ms

```
- `files_declared` is empty
- plan step names no declared file: '1. Add `tests/test_config.py` cases for absent, malformed, unsafe, and valid quarantine values, then implement `pipeline/core/config.py::gate_quarantine()` to parse `[gate]`, require a list of safe test selectors, preserve order, and raise `PipelineError` with the offending key or entry.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Extend `tests/test_gate.py` with `test_gate_names_revalidating_recovery_and_accepts_it`, `test_gate_refuses_quarantining_its_own_test`, and gate-thread assertions, then update `pipeline/core/gate.py` to name `pipeline resume <id> --stage revalidating`, accept a worktree/base double-pass only while `Ticket.stage == "revalidating"`, reject quarantine overlap with `test_file`, append one visible `ok:` line naming every quarantined selector, and pass the de-duplicated ticket-plus-quarantine list only to worktree and base `test_suite_without_new` formatting.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Document `[gate] quarantine`, its suite-only scope, overlap refusal, visible gate entry, and load-flaky recovery in `pipeline/templates/pipeline.toml`, `README.md`, and `pipeline/templates/skills/pipeline-config/SKILL.md`, including that committed or pinned config remains authoritative.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-20 02:21:47Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-20 02:20:04Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.37s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-c9971349/base
      Built pipeline @ file:///tmp/pipeline-base-c9971349/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 55ms

```

- `files_declared` is empty
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '1. Add `tests/test_config.py` cases for absent, malformed, unsafe, and valid quarantine values, then implement `pipeline/core/config.py::gate_quarantine()` to parse `[gate]`, require a list of safe test selectors, preserve order, and raise `PipelineError` with the offending key or entry.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '2. Extend `tests/test_gate.py` with `test_gate_names_revalidating_recovery_and_accepts_it`, `test_gate_refuses_quarantining_its_own_test`, and gate-thread assertions, then update `pipeline/core/gate.py` to name `pipeline resume <id> --stage revalidating`, accept a worktree/base double-pass only while `Ticket.stage == "revalidating"`, reject quarantine overlap with `test_file`, append one visible `ok:` line naming every quarantined selector, and pass the de-duplicated ticket-plus-quarantine list only to worktree and base `test_suite_without_new` formatting.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '3. Document `[gate] quarantine`, its suite-only scope, overlap refusal, visible gate entry, and load-flaky recovery in `pipeline/templates/pipeline.toml`, `README.md`, and `pipeline/templates/skills/pipeline-config/SKILL.md`, including that committed or pinned config remains authoritative.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)

### 2026-09-20 02:21:54Z · planning · plan

The plan uses `revalidating` as the explicit recovery boundary. Initial plan-validation still emits `LOAD-FLAKY`; normal revalidation follows a prior Tier A pass, and manual entry requires human resume.

The quarantine design validates `[gate].quarantine`, applies selectors only to worktree and base suite exclusions, refuses `test_file` overlap, and names every selector in the gate thread.

The plan supersedes DEC-109's unconditional revalidating failure rule. It preserves DEC-090's first-validation proof and DEC-137's confirmed-suite behavior.

Ran Tier A twice. Both runs reported only the expected pre-adoption `files_declared` findings; the reproduction failed with its recorded `expect:` text.

### 2026-09-20 02:22:31Z · planning · session · session=01a0bc97-1775-7ae2-87ab-3cccca309ea4

`planning` ran as session `01a0bc97-1775-7ae2-87ab-3cccca309ea4`
- replay: `codex exec resume 01a0bc97-1775-7ae2-87ab-3cccca309ea4`
- log: `.project/logs/TICKET-145-planning-d4fd9bd9.log`
- cost: unknown (the harness reported none)
- tokens: 19,731 out (9,336 thinking) · 3,648,673 in · 3,512,704 cache read · 0 cache write

### 2026-09-20 02:22:31Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned stage-aware load-flaky recovery and visible suite-only test quarantine.

### 2026-09-20 02:23:58Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails as required
```
eature.
        """
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "echo test_broken; exit 1"\n'
            'test_suite = "true"\n'
            'test_suite_without_new = "echo {test:--deselect } | '
            "grep -Fq -- '--deselect tests/test_racy.py::test_racy' || "
            '{ echo 1 failed; exit 1; }"\n'
            '[gate]\n'
            'quarantine = ["tests/test_racy.py::test_racy"]\n')
        ok, failures = gate(d, "TICKET-001")
>       assert ok, failures
E       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails on base `main` too -- the bug is not already fixed upstream
```
tionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.38s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ytw6nxbs/base
      Built pipeline @ file:///tmp/pipeline-base-ytw6nxbs/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 102ms

```

### 2026-09-20 02:26:16Z · plan-validation · finding · severity=blocking

- Root cause vs symptom — PASS. The plan separates an unproven initial reproduction from explicit human recovery after both trees pass.
- Decision conflict — PASS. It preserves DEC-017, DEC-029, DEC-037, DEC-067, DEC-090, and DEC-137, while explicitly superseding DEC-109.
- Scope discipline — PASS. Each planned code, test, and configuration document change supports recovery or suite-only quarantine.
- Falsifiable criteria — PASS. Named tests distinguish initial `LOAD-FLAKY`, revalidating success, overlap refusal, quarantine exclusion, and regressions.
- No research left — PASS. Steps name concrete files, functions, tests, validation rules, and command paths.
- Riskiest step — PASS. Step 2 owns the acceptance exception, and `## Rollback` restores the prior boundary before removing quarantine.
- Regression surface — FAIL. The plan omits `pipeline/templates/skills/file-ticket/SKILL.md`. Repository instructions require that interface to track human-gate behavior. Its current text names neither `LOAD-FLAKY` nor `revalidating` recovery. Add the file to step 3, `files_declared`, and an acceptance criterion. The pipeline-config skill does not replace this required interface.
- Blast radius matches class — PASS. Eight focused files are proportionate to this feature after adding the missing skill.

### 2026-09-20 02:27:00Z · plan-validation · session · session=01a0bca0-a620-7e60-b151-0eb3f0ef2cef

`plan-validation` ran as session `01a0bca0-a620-7e60-b151-0eb3f0ef2cef`
- replay: `codex exec resume 01a0bca0-a620-7e60-b151-0eb3f0ef2cef`
- log: `.project/logs/TICKET-145-plan-validation-5d31c3f8.log`
- cost: unknown (the harness reported none)
- tokens: 5,114 out (2,763 thinking) · 638,210 in · 583,296 cache read · 0 cache write

### 2026-09-20 02:27:00Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ Plan omits the required file-ticket update for the changed human recovery contract.

### 2026-09-20 02:29:13Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails as required
```
eature.
        """
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "echo test_broken; exit 1"\n'
            'test_suite = "true"\n'
            'test_suite_without_new = "echo {test:--deselect } | '
            "grep -Fq -- '--deselect tests/test_racy.py::test_racy' || "
            '{ echo 1 failed; exit 1; }"\n'
            '[gate]\n'
            'quarantine = ["tests/test_racy.py::test_racy"]\n')
        ok, failures = gate(d, "TICKET-001")
>       assert ok, failures
E       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================

```
- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.38s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-fc00a6mb/base
      Built pipeline @ file:///tmp/pipeline-base-fc00a6mb/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 55ms

```

### 2026-09-20 02:29:43Z · planning · plan

The revised plan adds `pipeline/templates/skills/file-ticket/SKILL.md` to step 3, `files_declared`, acceptance criteria, and rollback.

The skill will name `pipeline resume <id> --stage revalidating` as the human recovery for `LOAD-FLAKY`. It retains the ban on agent-initiated resume.

Tier A passed after the revision with no plan findings. The reproduction still failed with its recorded `expect:` text.

### 2026-09-20 02:30:43Z · planning · session · session=01a0bca3-6a09-7230-913e-3d8b6b34b85c

`planning` ran as session `01a0bca3-6a09-7230-913e-3d8b6b34b85c`
- replay: `codex exec resume 01a0bca3-6a09-7230-913e-3d8b6b34b85c`
- log: `.project/logs/TICKET-145-planning-fb4aea74.log`
- cost: unknown (the harness reported none)
- tokens: 7,679 out (3,278 thinking) · 1,111,973 in · 1,053,952 cache read · 0 cache write

### 2026-09-20 02:30:43Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Added the required file-ticket recovery contract to the validated plan.

### 2026-09-20 02:31:56Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-20 02:20:04Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.39s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-rt6g94nf/base
      Built pipeline @ file:///tmp/pipeline-base-rt6g94nf/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 68ms

```

### 2026-09-20 02:32:36Z · plan-validation · finding · severity=clear

- Root cause vs symptom — PASS. The gate conflates an already-fixed branch with an invalid nonfailing reproduction and lacks selector-level suite quarantine. The plan fixes both causes.
- Decision conflict — PASS. The plan preserves DEC-017, DEC-029, DEC-037, DEC-067, DEC-090, and DEC-137. It explicitly supersedes DEC-109 with a narrower human recovery.
- Scope discipline — PASS. Every changed file implements, tests, or documents recovery and suite-only quarantine.
- Falsifiable criteria — PASS. Named tests distinguish initial rejection, revalidating acceptance, overlap refusal, quarantine exclusion, malformed configuration, and suite regressions.
- No research left — PASS. Steps name concrete files, functions, validation rules, selectors, stages, and commands.
- Riskiest step — PASS. Step 2 identifies the stage-aware exception. Rollback removes it first and restores all related interfaces together.
- Regression surface — PASS. Tests cover ticket-test isolation, worktree and base suite exclusions, overlap refusal, config validation, full dispatcher behavior, and the guard suite.
- Blast radius matches class — PASS. Eight cohesive files match the two gate dead ends and their required user interfaces.

### 2026-09-20 02:33:08Z · plan-validation · session · session=01a0bca7-ee5a-73a0-ba53-490a5b2fcb54

`plan-validation` ran as session `01a0bca7-ee5a-73a0-ba53-490a5b2fcb54`
- replay: `codex exec resume 01a0bca7-ee5a-73a0-ba53-490a5b2fcb54`
- log: `.project/logs/TICKET-145-plan-validation-13c3e59f.log`
- cost: unknown (the harness reported none)
- tokens: 2,218 out (674 thinking) · 240,159 in · 217,856 cache read · 0 cache write

### 2026-09-20 02:33:08Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Revised plan covers the recovery contract, quarantine boundary, regression surface, and rollback.

### 2026-09-20 02:33:45Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-20 02:34:59Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails as required
```
eature.
        """
        d = project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "echo test_broken; exit 1"\n'
            'test_suite = "true"\n'
            'test_suite_without_new = "echo {test:--deselect } | '
            "grep -Fq -- '--deselect tests/test_racy.py::test_racy' || "
            '{ echo 1 failed; exit 1; }"\n'
            '[gate]\n'
            'quarantine = ["tests/test_racy.py::test_racy"]\n')
        ok, failures = gate(d, "TICKET-001")
>       assert ok, failures
E       AssertionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.24s ===============================

```
- ok: `tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError: ['suite excluding `test_thing.py::test_broken` is RED -- pre-existing breakage, fix that first
E         *-- identical output, ...dict=FAIL` --*
E         (base was not consulted: no ticket worktree was given, so there is no branch to compare against base)']
E       assert False

tests/test_gate.py:1110: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_quarantines_named_nodes_from_the_suite_only
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.37s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-nm4_o98s/base
      Built pipeline @ file:///tmp/pipeline-base-nm4_o98s/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 81ms

```

### 2026-09-20 02:34:59Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-20 02:37:44Z · implementing · session · session=01a0bcaa-ba22-7cc1-a260-72b0807b5880

`implementing` ran as session `01a0bcaa-ba22-7cc1-a260-72b0807b5880`
- replay: `codex exec resume 01a0bcaa-ba22-7cc1-a260-72b0807b5880`
- log: `.project/logs/TICKET-145-implementing-506b3630.log`

### 2026-09-20 02:37:44Z · implementing · note

`implementing` was refused by the API (terminal_reason=api_error, attempt 1) -- waiting 30 seconds

### 2026-09-20 02:52:56Z · implementing · note

`implementing` API retry wait expired (attempt 1) -- respawning

### 2026-09-20 03:10:00Z · implementing · note

Implemented in commit a6ef869. A prior attempt had left uncommitted edits; I kept them, found one gap, and fixed it.

- [x] 1. `gate_quarantine()` in `pipeline/core/config.py`; `test_gate_quarantine_validates_named_nodes` covers absent, non-list, non-string, `..` and valid values.
- [x] 2. `gate()`: `LOAD-FLAKY` names `pipeline resume <id> --stage revalidating`; the double-pass is accepted only when `Ticket.stage == "revalidating"`; quarantine overlap with `test_file` is a finding; one `ok:` line per quarantined selector; selectors reach only worktree and base `test_suite_without_new`.
- [x] 3. Docs: `pipeline.toml`, `README.md`, both skills.

Gap fixed: at `revalidating`, `_base_findings()` still emitted "exited 0 on base ... base proves nothing", so the recovery failed. `gate()` now drops that verdict for accepted tests.

Evidence:
- `tests/test_gate.py` + `tests/test_config.py`: 133 passed.
- Full suite: 658 passed. `./pipeline/hooks/test_dangerous_commands.py` exits 0.
- Tests fail if: the `revalidating` exception is removed (recovery test), the overlap check is removed (`test_gate_refuses_quarantining_its_own_test`), or `ok:` lines are dropped (quarantine test asserts the thread text).

### 2026-09-20 02:55:41Z · implementing · session · session=138e677c-8826-448e-8acd-420c1420bf75

`implementing` ran as session `138e677c-8826-448e-8acd-420c1420bf75`
- replay: `claude --resume 138e677c-8826-448e-8acd-420c1420bf75`
- log: `.project/logs/TICKET-145-implementing-138e677c.log`
- cost: $0.41 of a $10 cap
- tokens: 8,164 out (1,138 thinking) · 30 in · 622,808 cache read · 51,002 cache write

### 2026-09-20 02:55:41Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added [gate].quarantine (suite-only, overlap refused, named in gate entry) and revalidating recovery for LOAD-FLAKY; 658 tests + guard pass

### 2026-09-20 03:20:00Z · review · finding · severity=clear

**Review of the delta 222067d..a6ef869: PASS.** No blocking findings.

Acceptance criteria, all re-run here:
- the four named tests -> `4 passed in 0.30s`
- `uv run --group dev pytest -q` -> `658 passed in 72.56s (0:01:12)`
- `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`, exit 0
- `grep -c quarantine` -> `pipeline/templates/pipeline.toml:2`, `README.md:2`, `pipeline-config/SKILL.md:4`; `grep -c LOAD-FLAKY file-ticket/SKILL.md` -> `1`

Wiring checked, not assumed:
- The recovery command is real. `--stage` is a `resume` flag (`pipeline/cli/main.py:963`) and `revalidating` is in `KNOWN_STAGES` (`pipeline/core/machine.py:65`).
- The gate child reads `stage: revalidating` off disk: `start()` spawns `regate_cmd()` while the ticket sits at that stage (`pipeline/daemon/supervisor.py:945`).
- `FIXTURE` carries `stage: plan-validation` (`tests/helpers.py:10`), so the recovery test observes LOAD-FLAKY at plan-validation and the pass at revalidating.
- Quarantine reaches only `test_suite_without_new` in the worktree and `_base_suite()`. `_base_findings()` and `_copy_tests()` still take `candidates` alone, so DEC-017 holds, and `format_tests_cmd()` quotes each value (`pipeline/core/config.py:359`).

Findings I dropped: the base filter at `gate.py:847` keys on the specific test string, so it cannot swallow another test's verdict; the `t.stage` read is the approved `## Digest` line, not drift.

1. severity=minor -- `pipeline/core/gate.py:934` still reads `this ticket names {len(runnable)} tests`, while the bare-placeholder check above it now counts `suite_tests` (runnable plus quarantine). One ticket test plus one quarantine entry prints `this ticket names 1 tests`. The check and its remedy are correct; the count is stale.
2. severity=minor -- the overlap refusal is exact-match (`set(tests) & set(quarantine)`, `gate.py:784`), so a file-level entry `tests/test_x.py` that subsumes `tests/test_x.py::test_thing` is not refused and drops that whole file from the suite run. `README.md:620` and `pipeline/templates/pipeline.toml:54` state "the gate refuses a ticket whose `test_file` is quarantined" without that qualifier.

### 2026-09-20 03:00:53Z · review · session · session=dbba8c99-7199-423a-ab3d-928f3a8a42d9

`review` ran as session `dbba8c99-7199-423a-ab3d-928f3a8a42d9`
- replay: `claude --resume dbba8c99-7199-423a-ab3d-928f3a8a42d9`
- log: `.project/logs/TICKET-145-review-dbba8c99.log`
- cost: $2.14 of a $6 cap
- tokens: 18,126 out (9,051 thinking) · 62 in · 1,846,304 cache read · 76,391 cache write

### 2026-09-20 03:00:53Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed a6ef869 + 222067d: every acceptance criterion verified green (658 passed, guard exits 0); two minor findings, none blocking

### 2026-09-20 03:02:07Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-20 03:02:09Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/145


Current branch ticket/145 is up to date.
Already up to date.
Updating 7de7ed3..a6ef869
Fast-forward
 README.md                                          | 17 ++++++--
 pipeline/core/config.py                            | 21 ++++++++-
 pipeline/core/gate.py                              | 38 ++++++++++++----
 pipeline/templates/pipeline.toml                   |  9 ++++
 pipeline/templates/skills/file-ticket/SKILL.md     |  4 ++
 pipeline/templates/skills/pipeline-config/SKILL.md | 15 +++++++
 tests/test_config.py                               | 27 ++++++++++++
 tests/test_gate.py                                 | 51 ++++++++++++++++++++++
 8 files changed, 170 insertions(+), 12 deletions(-)

```

### 2026-09-20 03:02:09Z · merging · decision

decision recorded as `DEC-145`
