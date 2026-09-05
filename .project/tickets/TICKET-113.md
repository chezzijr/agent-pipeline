---
id: TICKET-113
stage: done
class: bugfix
branch: ticket/113
test_file: tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot
files_declared:
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 1
  lease_expiries: 0
  plan_steps: 2
  plan_files: 2
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 01a071c5-a20a-72b2-84af-61af4e9c16eb
  replay: codex exec resume 01a071c5-a20a-72b2-84af-61af4e9c16eb
  log: .project/logs/TICKET-113-review-8371a75c.log
  cost_usd: null
cheap_route_head: d9081cfdb0119611ea56362965b096f0cced69a3
approved_by: chezzijr
approved_at: '2026-09-05T13:26:33.318354+00:00'
---

## Summary

Commit `f86de37` recovers delimiter-free agent ticket prose from the trusted
spawn snapshot. It rejects malformed metadata envelopes and preserves
control-field tamper detection. Review found no blocking defects. The focused
tests pass, and prior runs passed the dispatcher, full pytest, and guard suites.

## Reproduction

Test: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot`

Command:

```sh
/home/chezzijr/proj/agent-pipeline/.venv/bin/python -m pytest -q tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot
```

Output:

```
E pipeline.core.PipelineError: /tmp/tmphcno4pqt/.project/tickets/TICKET-001.md: /tmp/tmphcno4pqt/.project/tickets/TICKET-001.md: no frontmatter
1 failed in 0.41s
```

expect: no frontmatter

## Digest

- Files: modify `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py`; commit `d9081cf` already contains the failing regression.
- Entry point: `pipeline.daemon.supervisor._finish()` reads the sidecar, then currently calls `Ticket.load(path)` before consulting `rec["meta"]`.
- Regression evidence: running the committed node at `d9081cf` fails inside `Ticket.load(path)` with `PipelineError: ...: no frontmatter`, before its final assertion executes.
- Key behavior: `rec["meta"]` is the trusted pre-spawn `Ticket`; rebuild with `replace(snap, body=agent_body)` so agent prose survives and snapshot frontmatter wins.
- Boundary: recover only raw files without the opening `---\n`; re-raise delimiter-bearing malformed YAML instead of treating hostile metadata as prose.
- Tests: the recovery test currently fails with `PipelineError: ...: no frontmatter`; its post-fix summary assertion must use `Ticket.section("Summary").strip()`.
- Current branch: commit `11b55d5` implements the recovery and passes the focused, tamper, dispatcher, full pytest, and direct guard suites.
- Difference from the rejected plan: replace `sh ./pipeline/hooks/test_dangerous_commands.py` with `env ./pipeline/hooks/test_dangerous_commands.py`; the shell must honor the Python shebang.

## Decisions checked

- DEC-048 requires `_finish()` to rebuild from the pre-spawn snapshot while accepting only the agent body. This plan preserves that ownership boundary.
- DEC-110 requires the snapshot to win and valid control-field differences to escalate without accusing the stage. This plan leaves tamper detection unchanged.
- Searched `frontmatter`, `snapshot`, `_finish`, `agent body`, and `tamper` in the decisions directory.

## Plan

1. Complete `tests/test_dispatch.py` coverage by correcting the recovered-summary assertion, retaining snapshot-frontmatter assertions, and adding `test_a_malformed_frontmatter_envelope_is_not_recovered_as_prose`; run the two recovery nodes before and after the implementation.
2. Change `pipeline/daemon/supervisor.py::_finish()` to recover delimiter-free agent text with `replace(snap, body=agent_body)`, re-raise malformed envelopes, and preserve parsed control-field tamper detection; run the focused `tests/test_dispatch.py` nodes, the dispatcher file, the full pytest suite, and the executable guard suite.

## Acceptance criteria

- `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` passes and asserts snapshot frontmatter plus exact agent-written summary prose.
- `tests/test_dispatch.py::test_a_malformed_frontmatter_envelope_is_not_recovered_as_prose` passes and observes `PipelineError` from delimiter-bearing malformed YAML.
- `tests/test_dispatch.py::test_a_control_field_rewritten_mid_run_is_caught` passes and still proves tampering escalates before applying the sidecar verdict.
- `/home/chezzijr/proj/agent-pipeline/.venv/bin/python -m pytest -q tests/test_dispatch.py` exits `0`.
- `uv run --group dev pytest -q` exits `0`.
- `env ./pipeline/hooks/test_dangerous_commands.py` exits `0` after running every guard case as Python.

## Decisions

Recover an agent-written ticket without frontmatter as body text from the trusted pre-spawn snapshot. A file beginning with `---\n` remains a metadata envelope; any parse failure must propagate instead of converting hostile metadata into prose. Valid parsed control-field differences must still follow the existing tamper escalation.

## Rollback

Revert the TICKET-113 implementation and companion test amendments together. This restores fail-fast behavior for frontmatterless agent output while keeping ticket parsing rules unchanged.

## Thread

### 2026-09-05 13:01:00Z · implementing · todo

- [ ] Correct the recovery assertion and add malformed-envelope coverage.
- [ ] Run both tests red, then implement snapshot-body recovery.
- [ ] Run focused and repository suites, then commit the fix.

### 2026-09-05 12:05:00Z · implementing · todo

- [x] Restore the pre-spawn snapshot before reading agent frontmatter.
- [x] Run the focused regression test and commit the dispatcher fix.

### 2026-09-05 12:10:00Z · implementing · finding

Commit `e518ec1` recovers a ticket without frontmatter from `rec["meta"]`.
It preserves the agent's remaining prose and restores dispatcher-owned fields.
Malformed YAML with an opening delimiter still raises.
Valid control-field tampering still escalates.
The regression test had no `Ticket.summary()` API. It now reads `Summary` with
`Ticket.section()`.
`tests/test_dispatch.py` passed: `89 passed in 10.01s`.

### 2026-09-05 11:06:06Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-05 11:08:20Z · triage · rejected

The focused test reproduces the failure. `_finish()` loads body-only agent
bytes before reading `rec["meta"]`, so it raises `PipelineError: ...: no
frontmatter`. Valid-but-tampered frontmatter already takes the quarantine
path, which is the nearest working case. Git could not commit the test:
`fatal: Unable to create '/home/chezzijr/proj/agent-pipeline/.git/worktrees/TICKET-113/index.lock': Read-only file system`.
The test remains uncommitted in `tests/test_dispatch.py`.

### 2026-09-05 11:08:57Z · triage · session · session=01a0713f-73a5-7f30-b2ce-2e9359ba7891

`triage` ran as session `01a0713f-73a5-7f30-b2ce-2e9359ba7891`
- replay: `codex exec resume 01a0713f-73a5-7f30-b2ce-2e9359ba7891`
- log: `.project/logs/TICKET-113-triage-72e3f1b9.log`

### 2026-09-05 11:08:57Z · triage · transition · to=rejected · result=rejected · marker=yes

**triage -> rejected** (result: `rejected`)

✓ Reproduced the no-frontmatter crash, but Git cannot create this worktree's index lock to commit the test.

### 2026-09-05 11:43:50Z · human · note · by=chezzijr

**resumed** by chezzijr -> `triage`, reset []

### 2026-09-05 11:49:39Z · triage · finding

The committed regression test fails with `no frontmatter`.
`_finish()` loads the body-only ticket before it uses `rec["meta"]`.
The nearest working case restores valid tampered frontmatter from that snapshot.
Commit `d9081cf` adds `tests/test_dispatch.py` coverage.
The expected fix touches `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py`.

### 2026-09-05 12:00:00Z · triage · rejected

The focused test fails with `PipelineError: ...: no frontmatter`.
`_finish()` calls `Ticket.load(path)` before it restores `agent.body` from
`rec["meta"]`. The valid-frontmatter tamper test is the nearest working case.
The test is staged in `tests/test_dispatch.py` but is not committed.
Git reported: `fatal: unable to auto-detect email address (got 'chezzijr@chezzijr.(none)')`.

### 2026-09-05 11:45:49Z · triage · session · session=01a07161-d8b4-7d83-8f62-447a56c1b4a7

`triage` ran as session `01a07161-d8b4-7d83-8f62-447a56c1b4a7`
- replay: `codex exec resume 01a07161-d8b4-7d83-8f62-447a56c1b4a7`
- log: `.project/logs/TICKET-113-triage-fd2c9806.log`

### 2026-09-05 11:45:49Z · triage · transition · to=rejected · result=rejected · marker=yes

**triage -> rejected** (result: `rejected`)

✓ Reproduced the frontmatterless-ticket crash, but Git cannot commit without a configured author identity.

### 2026-09-05 11:48:02Z · human · note · by=chezzijr

**resumed** by chezzijr -> `triage`, reset []

### 2026-09-05 11:49:52Z · triage · session · session=01a07165-ac5c-7f81-b8fe-0f023d29f976

`triage` ran as session `01a07165-ac5c-7f81-b8fe-0f023d29f976`
- replay: `codex exec resume 01a07165-ac5c-7f81-b8fe-0f023d29f976`
- log: `.project/logs/TICKET-113-triage-18cc35e8.log`

### 2026-09-05 11:49:52Z · triage · transition · to=implementing · result=chore · marker=yes

**triage -> implementing** (result: `chore`)

✓ Reproduced and committed the frontmatterless agent-ticket regression.

### 2026-09-05 11:53:54Z · implementing · session · session=01a07167-57c5-7d50-8942-9d4f47e7d419

`implementing` ran as session `01a07167-57c5-7d50-8942-9d4f47e7d419`
- replay: `codex exec resume 01a07167-57c5-7d50-8942-9d4f47e7d419`
- log: `.project/logs/TICKET-113-implementing-428dbd9b.log`

### 2026-09-05 11:53:54Z · implementing · transition · to=quick-review · result=ok · marker=yes

**implementing -> quick-review** (result: `ok`)

✓ Restored frontmatterless agent tickets from the pre-spawn snapshot.

### 2026-09-05 12:15:00Z · quick-review · finding

1. No. Command: `git diff main...HEAD -- tests/test_dispatch.py`.
   Output adds
   `test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot`.
   The reproduction names that same test. Its recorded `no frontmatter` failure
   therefore does not prove it fails without this diff.
2. Yes. Command: `git diff --name-only main...HEAD`.
   Output:
   ```
   pipeline/daemon/supervisor.py
   tests/test_dispatch.py
   ```
   The triage finding states: `The expected fix touches
   pipeline/daemon/supervisor.py and tests/test_dispatch.py.`

### 2026-09-05 11:54:46Z · quick-review · session · session=01a0716b-0a2b-7ab3-88d0-edf7d2bf466d

`quick-review` ran as session `01a0716b-0a2b-7ab3-88d0-edf7d2bf466d`
- replay: `codex exec resume 01a0716b-0a2b-7ab3-88d0-edf7d2bf466d`
- log: `.project/logs/TICKET-113-quick-review-fc2c0c2c.log`

### 2026-09-05 11:54:46Z · quick-review · transition · to=unwinding · result=fail · marker=yes

**quick-review -> unwinding** (result: `fail`)

✓ The diff changes the committed regression test, so the recorded failure cannot prove it fails without this diff.

### 2026-09-05 11:54:48Z · unwinding · transition · to=planning · result=ok

**unwinding -> planning** (result: `ok`)

unwind exit 0
```
$ git merge-base --is-ancestor d9081cfdb0119611ea56362965b096f0cced69a3 HEAD || { echo "d9081cfdb0119611ea56362965b096f0cced69a3 is not an ancestor of HEAD -- refusing to unwind"; exit 1; }
git log --oneline d9081cfdb0119611ea56362965b096f0cced69a3..HEAD
git reset --hard d9081cfdb0119611ea56362965b096f0cced69a3 && git clean -fd


e518ec1 fix(TICKET-113): recover frontmatterless agent tickets
HEAD is now at d9081cf test(TICKET-113): reproduce frontmatterless agent ticket crash

```

### 2026-09-05 11:56:44Z · planning · finding

The plan restores body-only agent output from the trusted pre-spawn snapshot.
It keeps delimiter-bearing malformed YAML fatal and preserves tamper escalation.
The implementer will correct the regression's nonexistent `Ticket.summary()`
call, add malformed-envelope coverage, and use `replace()` without mutating the
snapshot. DEC-048 and DEC-110 constrain the restore path.

### 2026-09-05 11:58:02Z · planning · note

`planning` was interrupted; lease released

### 2026-09-05 12:24:00Z · planning · finding

The plan uses regression commit `d9081cf` as the pre-fix evidence. Its focused
test fails inside `_finish()` with `PipelineError: ...: no frontmatter` before
the invalid `Ticket.summary()` assertion executes. The implementer will correct
that unreachable assertion, add malformed-envelope coverage, and recover only
delimiter-free body text through `replace(snap, body=agent_body)`. DEC-048 and
DEC-110 keep snapshot ownership and valid-frontmatter tamper escalation intact.

### 2026-09-05 12:43:17Z · planning · session · session=01a07195-d71e-75a3-a3ac-b4c922019543

`planning` ran as session `01a07195-d71e-75a3-a3ac-b4c922019543`
- replay: `codex exec resume 01a07195-d71e-75a3-a3ac-b4c922019543`
- log: `.project/logs/TICKET-113-planning-79cfad92.log`

### 2026-09-05 12:43:17Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned snapshot recovery with malformed-envelope and tamper boundaries preserved.

### 2026-09-05 12:44:10Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` fails as required
```
eline/daemon/supervisor.py:1146: in finish
    result = _finish(project, rec, emit)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^
pipeline/daemon/supervisor.py:1212: in _finish
    agent = Ticket.load(path)
            ^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cls = <class 'pipeline.core.ticket.Ticket'>
path = PosixPath('/tmp/tmpj622ucf1/.project/tickets/TICKET-001.md')

    @classmethod
    def load(cls, path) -> "Ticket":
        path = Path(path)
        try:
            meta, body = split_frontmatter(path)
        except Exception as e:
>           raise PipelineError(f"{path}: {e}") from e
E           pipeline.core.PipelineError: /tmp/tmpj622ucf1/.project/tickets/TICKET-001.md: /tmp/tmpj622ucf1/.project/tickets/TICKET-001.md: no frontmatter

pipeline/core/ticket.py:616: PipelineError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.20s ===============================

```
- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` fails on base `main` too -- the bug is not already fixed upstream
```
= split_frontmatter(path)
        except Exception as e:
>           raise PipelineError(f"{path}: {e}") from e
E           pipeline.core.PipelineError: /tmp/tmpr0c2ph37/.project/tickets/TICKET-001.md: /tmp/tmpr0c2ph37/.project/tickets/TICKET-001.md: no frontmatter

pipeline/core/ticket.py:616: PipelineError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-8dwzam0b/base
      Built pipeline @ file:///tmp/pipeline-base-8dwzam0b/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 32ms

```

### 2026-09-05 12:45:45Z · plan-validation · finding

Plan validation passed all scored items.

1. **Root cause: pass.** `_finish()` parses agent-controlled frontmatter before using `rec["meta"]`; the plan restores body text from that trusted snapshot.
2. **Decision conflict: pass.** `replace(snap, body=agent_body)` complies with DEC-048. Parsed-frontmatter tamper detection remains intact under DEC-110.
3. **Scope discipline: pass.** Both planned files support recovery or its acceptance criteria. The assertion correction makes the committed regression reachable after recovery.
4. **Falsifiable criteria: pass.** Exact frontmatter, exact prose, malformed-envelope exceptions, and tamper escalation each distinguish incorrect implementations.
5. **No research left: pass.** Both steps name `tests/test_dispatch.py`, `pipeline/daemon/supervisor.py::_finish()`, concrete test nodes, and commands.
6. **Riskiest step: pass.** The delimiter test protects the recovery boundary. Joint reversion restores fail-fast behavior if recovery proves unsafe.
7. **Regression surface: pass.** Malformed YAML and control-field tampering could regress. Focused tests cover both, while dispatcher and full suites cover callers.
8. **Blast radius: pass.** This bugfix changes two files around one dispatcher restore path, matching its class.

Unverified: none. The rejected `2>/dev/null` probe was unnecessary and did not limit any score.

### 2026-09-05 12:46:20Z · plan-validation · session · session=01a07199-1177-72b1-b95c-95f7ff4232d9

`plan-validation` ran as session `01a07199-1177-72b1-b95c-95f7ff4232d9`
- replay: `codex exec resume 01a07199-1177-72b1-b95c-95f7ff4232d9`
- log: `.project/logs/TICKET-113-plan-validation-52f8b191.log`

### 2026-09-05 12:46:20Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan preserves snapshot ownership, malformed-envelope failure, and tamper escalation with focused regression coverage.

### 2026-09-05 12:59:16Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-05 13:00:17Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` fails as required
```
eline/daemon/supervisor.py:1146: in finish
    result = _finish(project, rec, emit)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^
pipeline/daemon/supervisor.py:1212: in _finish
    agent = Ticket.load(path)
            ^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cls = <class 'pipeline.core.ticket.Ticket'>
path = PosixPath('/tmp/tmpeqy3bsfx/.project/tickets/TICKET-001.md')

    @classmethod
    def load(cls, path) -> "Ticket":
        path = Path(path)
        try:
            meta, body = split_frontmatter(path)
        except Exception as e:
>           raise PipelineError(f"{path}: {e}") from e
E           pipeline.core.PipelineError: /tmp/tmpeqy3bsfx/.project/tickets/TICKET-001.md: /tmp/tmpeqy3bsfx/.project/tickets/TICKET-001.md: no frontmatter

pipeline/core/ticket.py:616: PipelineError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.20s ===============================

```
- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` fails on base `main` too -- the bug is not already fixed upstream
```
= split_frontmatter(path)
        except Exception as e:
>           raise PipelineError(f"{path}: {e}") from e
E           pipeline.core.PipelineError: /tmp/tmpxsq_spuj/.project/tickets/TICKET-001.md: /tmp/tmpxsq_spuj/.project/tickets/TICKET-001.md: no frontmatter

pipeline/core/ticket.py:616: PipelineError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.53s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-e1pmz6dk/base
      Built pipeline @ file:///tmp/pipeline-base-e1pmz6dk/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 27ms

```

### 2026-09-05 13:00:17Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-05 13:03:00Z · implementing · todo

- [x] Corrected the recovery assertion and added malformed-envelope coverage.
- [x] Ran tests red, then implemented snapshot-body recovery.
- [x] Ran focused and repository suites and committed `11b55d5`.

### 2026-09-05 13:03:00Z · implementing · finding

Blocked by an acceptance-command contradiction outside the approved scope.

1. Commit `11b55d5` recovers delimiter-free prose with `replace(snap, body=agent_body)`.
2. The recovery, malformed-envelope, and tamper tests passed: `3 passed in 0.31s`.
3. `tests/test_dispatch.py` passed: `90 passed in 9.87s`.
4. `uv run --group dev pytest -q` passed: `559 passed in 50.02s`.
5. `./pipeline/hooks/test_dangerous_commands.py` passed all 138 cases.
6. `sh ./pipeline/hooks/test_dangerous_commands.py` exits 2 because shell parses Python:
   `./pipeline/hooks/test_dangerous_commands.py: line 2: Run: ./hooks/test_dangerous_commands.py: No such file or directory`

The plan names only `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py`.
Changing the guard invocation or hook is outside that plan.

### 2026-09-05 13:04:32Z · implementing · session · session=01a071a7-d7f1-76f2-a62f-9f4ffae8af60

`implementing` ran as session `01a071a7-d7f1-76f2-a62f-9f4ffae8af60`
- replay: `codex exec resume 01a071a7-d7f1-76f2-a62f-9f4ffae8af60`
- log: `.project/logs/TICKET-113-implementing-ff665be3.log`

### 2026-09-05 13:04:32Z · implementing · transition · to=plan-validation · result=blocked · marker=yes

**implementing -> plan-validation** (result: `blocked`)

✓ Blocked: the required `sh` guard command parses a Python script as shell and exits 2.

### 2026-09-05 13:05:25Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` exited 0 here and fails on base `main` -- the branch already carries the fix, and base is where the reproduction still holds
- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` fails on base `main` too -- the bug is not already fixed upstream
```
= split_frontmatter(path)
        except Exception as e:
>           raise PipelineError(f"{path}: {e}") from e
E           pipeline.core.PipelineError: /tmp/tmp1p4nlruz/.project/tickets/TICKET-001.md: /tmp/tmp1p4nlruz/.project/tickets/TICKET-001.md: no frontmatter

pipeline/core/ticket.py:616: PipelineError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.53s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-tcmwu2ck/base
      Built pipeline @ file:///tmp/pipeline-base-tcmwu2ck/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 40ms

```

### 2026-09-05 13:06:39Z · plan-validation · finding

Plan validation failed because the required guard criterion cannot test the implementation.

1. **Root cause: pass.** `_finish()` parses the agent file before rebuilding from `rec["meta"]`; delimiter-free output fails before trusted snapshot recovery.
2. **Decision conflict: pass.** Snapshot reconstruction complies with DEC-048. Preserved parsed-frontmatter comparison complies with DEC-110.
3. **Scope discipline: pass.** Both code files and every implementation step trace to recovery or regression criteria.
4. **Falsifiable criteria: fail.** `sh ./pipeline/hooks/test_dangerous_commands.py` exits 2 while parsing Python, regardless of implementation correctness.
5. **No research left: fail.** The plan does not replace the disproven command with `./pipeline/hooks/test_dangerous_commands.py` or another concrete valid criterion.
6. **Riskiest step: pass.** Broad parse-failure recovery risks accepting malformed metadata. The prefix check re-raises envelopes, and joint reversion restores fail-fast behavior.
7. **Regression surface: pass.** Malformed YAML and control-field tampering could regress. Focused tests cover both; dispatcher and full suites cover callers.
8. **Blast radius: pass.** The two-file change remains limited to one dispatcher restore path and its tests.

Unverified: none.

### 2026-09-05 13:07:21Z · plan-validation · session · session=01a071ac-8739-7362-a859-2da294df505a

`plan-validation` ran as session `01a071ac-8739-7362-a859-2da294df505a`
- replay: `codex exec resume 01a071ac-8739-7362-a859-2da294df505a`
- log: `.project/logs/TICKET-113-plan-validation-ede2ab3f.log`

### 2026-09-05 13:07:21Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ Replace the invalid `sh` guard criterion; it fails before guard cases run.

### 2026-09-05 13:12:00Z · planning · finding

Revised the rejected acceptance command without changing implementation scope.

1. `sh ./pipeline/hooks/test_dangerous_commands.py` parses Python as shell and exits 2.
2. `pipeline/hooks/test_dangerous_commands.py` is executable and declares `#!/usr/bin/env python3`.
3. `env ./pipeline/hooks/test_dangerous_commands.py` ran every guard case and exited 0.
4. Commit `11b55d5` already contains the approved two-file implementation and passing regression coverage.

### 2026-09-05 13:09:56Z · planning · session · session=01a071ae-48c8-7190-ad82-7db7a3a04e0c

`planning` ran as session `01a071ae-48c8-7190-ad82-7db7a3a04e0c`
- replay: `codex exec resume 01a071ae-48c8-7190-ad82-7db7a3a04e0c`
- log: `.project/logs/TICKET-113-planning-66cb7325.log`

### 2026-09-05 13:09:56Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Replaced the invalid shell criterion with an executable Python guard-suite command while preserving the approved two-file plan.

### 2026-09-05 13:10:50Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` exited 0 here and fails on base `main` -- the branch already carries the fix, and base is where the reproduction still holds
- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` fails on base `main` too -- the bug is not already fixed upstream
```
= split_frontmatter(path)
        except Exception as e:
>           raise PipelineError(f"{path}: {e}") from e
E           pipeline.core.PipelineError: /tmp/tmpdbol_qis/.project/tickets/TICKET-001.md: /tmp/tmpdbol_qis/.project/tickets/TICKET-001.md: no frontmatter

pipeline/core/ticket.py:616: PipelineError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-shs7hx3g/base
      Built pipeline @ file:///tmp/pipeline-base-shs7hx3g/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 31ms

```

### 2026-09-05 13:11:51Z · plan-validation · finding

Plan validation passed after the guard command correction.

1. **Root cause: pass.** `_finish()` loads agent output before using the trusted snapshot. Snapshot reconstruction fixes that cause, not only the failing assertion.
2. **Decision conflict: pass.** Snapshot-owned metadata complies with DEC-048. Preserved tamper escalation complies with DEC-110.
3. **Scope discipline: pass.** Both files and both steps trace to recovery, boundary, or regression criteria.
4. **Falsifiable criteria: pass.** Recovery, malformed-envelope, and tamper tests distinguish incorrect behavior. Dispatcher and full suites test regressions. The guard command now executes Python cases.
5. **No research left: pass.** Steps name `tests/test_dispatch.py`, `pipeline/daemon/supervisor.py::_finish()`, assertions, recovery construction, and the envelope boundary.
6. **Riskiest step: pass.** Recovery could accept hostile metadata. The delimiter check preserves rejection, and joint reversion restores fail-fast behavior.
7. **Regression surface: pass.** Malformed YAML, control-field ownership, dispatcher callers, and guard behavior have named tests or suites.
8. **Blast radius: pass.** This bugfix changes one restore path and its tests across two files.

Unverified: none.

### 2026-09-05 13:12:32Z · plan-validation · session · session=01a071b1-7ac9-7f13-b311-3313dbd39ba9

`plan-validation` ran as session `01a071b1-7ac9-7f13-b311-3313dbd39ba9`
- replay: `codex exec resume 01a071b1-7ac9-7f13-b311-3313dbd39ba9`
- log: `.project/logs/TICKET-113-plan-validation-f32033c8.log`

### 2026-09-05 13:12:32Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Revised plan passes all eight judgment checks; the executable guard criterion resolves the prior rejection.

### 2026-09-05 13:26:33Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-05 13:27:27Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` exited 0 here and fails on base `main` -- the branch already carries the fix, and base is where the reproduction still holds
- ok: `tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot` fails on base `main` too -- the bug is not already fixed upstream
```
= split_frontmatter(path)
        except Exception as e:
>           raise PipelineError(f"{path}: {e}") from e
E           pipeline.core.PipelineError: /tmp/tmpbcu34yc0/.project/tickets/TICKET-001.md: /tmp/tmpbcu34yc0/.project/tickets/TICKET-001.md: no frontmatter

pipeline/core/ticket.py:616: PipelineError
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_frontmatterless_agent_ticket_is_recovered_from_the_spawn_snapshot
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-mr4i9p4t/base
      Built pipeline @ file:///tmp/pipeline-base-mr4i9p4t/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 45ms

```

### 2026-09-05 13:27:28Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-05 13:28:00Z · implementing · todo

- [x] Confirmed the committed recovery tests and implementation match the approved plan.
- [x] Ran the focused recovery and tamper tests.
- [x] Ran dispatcher and guard suites; amended the implementation commit.

### 2026-09-05 13:31:00Z · implementing · finding

Implemented and committed the approved recovery boundary as `f86de37`.

1. `_finish()` rebuilds delimiter-free agent text with `replace(snap, body=agent_body)`.
2. Files beginning `---\n` re-raise `PipelineError` from malformed YAML.
3. Parsed agent frontmatter still compares control fields before applying the sidecar verdict.
4. Focused recovery, malformed-envelope, and tamper tests passed: `3 passed in 0.11s`.
5. Dispatcher tests passed: `90 passed in 9.83s`.
6. `env ./pipeline/hooks/test_dangerous_commands.py` passed all 138 guard cases.
7. Earlier implementation evidence recorded `uv run --group dev pytest -q`: `559 passed in 50.02s`.

### 2026-09-05 13:32:51Z · implementing · session · session=01a071c0-b77f-7200-8f78-40ff4b7c955f

`implementing` ran as session `01a071c0-b77f-7200-8f78-40ff4b7c955f`
- replay: `codex exec resume 01a071c0-b77f-7200-8f78-40ff4b7c955f`
- log: `.project/logs/TICKET-113-implementing-4f65cc3f.log`

### 2026-09-05 13:32:51Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Recovered delimiter-free agent ticket prose from the spawn snapshot and verified the focused, dispatcher, and guard suites.

### 2026-09-05 13:34:49Z · review · finding

No blocking findings.

The delta matches the approved plan and preserves parsed control-field tamper
detection. The three focused recovery, malformed-envelope, and tamper tests
passed: `3 passed in 0.11s`.

The local dispatcher run reached `88 passed` before two unrelated AF_UNIX tests
failed with `PermissionError: [Errno 1] Operation not permitted`. The earlier
implementation run passed all 90 dispatcher tests in an unrestricted environment.

### 2026-09-05 13:35:22Z · review · session · session=01a071c5-a20a-72b2-84af-61af4e9c16eb

`review` ran as session `01a071c5-a20a-72b2-84af-61af4e9c16eb`
- replay: `codex exec resume 01a071c5-a20a-72b2-84af-61af4e9c16eb`
- log: `.project/logs/TICKET-113-review-8371a75c.log`

### 2026-09-05 13:35:22Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Review found no blocking defects in the snapshot recovery boundary.

### 2026-09-05 13:36:12Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-05 13:36:14Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/113


Current branch ticket/113 is up to date.
Already up to date.
Updating 07b379e..f86de37
Fast-forward
 pipeline/daemon/supervisor.py | 17 ++++++++++++----
 tests/test_dispatch.py        | 45 +++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 58 insertions(+), 4 deletions(-)

```

### 2026-09-05 13:36:14Z · merging · decision

decision recorded as `DEC-113`
