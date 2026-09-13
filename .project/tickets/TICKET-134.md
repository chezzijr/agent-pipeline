---
id: TICKET-134
stage: done
class: bugfix
branch: ticket/134
test_file: tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
files_declared:
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
  plan_steps: 2
  plan_files: 2
lease:
  holder: null
  expires: null
depends_on:
- TICKET-129
last_session:
  stage: review
  id: 01a09852-7f49-7bd2-874f-e7d06b6af743
  replay: codex exec resume 01a09852-7f49-7bd2-874f-e7d06b6af743
  log: .project/logs/TICKET-134-review-15d478c9.log
  cost_usd: null
approved_by: chezzijr
approved_at: '2026-09-13T00:52:27.453140+00:00'
---

## Summary

a stopped stage leaves its descendant processes running

`spawn()` starts a batch agent with no new session, so `stop_child()` signals
one pid and nothing under it -- `pipeline/daemon/supervisor.py:517`, on main at
3fd72b0:

    proc = retry_eagain(lambda: subprocess.Popen(
        cmd, shell=True, cwd=wt, stdout=subprocess.PIPE if poller else fh,
        stderr=subprocess.STDOUT, env=env))

`stop_child()` (`supervisor.py:1375`) then calls `proc.terminate()` and
`proc.kill()`. Both reach that pid only. An agent sitting inside a Bash tool
call -- a test run, a build, a `yes` in a pipeline -- leaves that grandchild
alive when the dispatcher stops, drains on a source change, or terminates a
child whose lease expired.

The interactive path does not have this problem: `pty.fork()` gives the child
its own session and `PtyProc._signal()` uses `os.killpg`
(`pipeline/pty/host.py:98`), so the whole group goes.

Observed on the chezzilang project, wave 12 (2026-09): triage left 24 `yes`
processes running, and they loaded the machine for every other ticket's gate
afterwards -- a load-sensitive test bound then bounced six tickets. The cost of
the orphans was paid by unrelated tickets as false gate failures.

`.project/known-issues.md` section 12 records a neighbouring case (a SIGKILLed
daemon orphaning agents) and names recording child pids as the upgrade. This
ticket is the narrower, always-reachable one: a CLEAN stop leaks descendants,
because the group was never created.

Expected: a batch child is started in its own process group
(`start_new_session=True`), and `stop_child()` signals the group rather than
the pid, matching what the PTY path already does. `spawn_command()`
(`supervisor.py:602`) starts dispatcher-owned children the same way and needs
the same treatment, since a gate child runs the project's whole suite.

The exact failure a test should show is a stopped batch child leaving a
descendant alive: spawn a shell that backgrounds a long-lived process, stop it
through `stop_child()`, and assert the descendant is gone. `tests/test_dispatch.py`
already builds fake children through `spawn()`.

## Reproduction

`tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant`

Command:

```
uv run --group dev pytest -q tests/test_dispatch.py -k stopping_a_batch_agent
```

Failure:

```
E   AssertionError: stopping the batch agent left background descendant 3982301 alive
```

expect: AssertionError: stopping the batch agent left background descendant

## Digest

Files: `pipeline/daemon/supervisor.py` owns both batch launches and shared teardown; `tests/test_dispatch.py` owns dispatcher lifecycle regressions.
Entry points: `spawn()` launches batch agents, and `spawn_command()` launches gate, verification, merge, and revalidation commands through `retry_eagain()`.
Teardown: `stop_child()` serves `shut_down()` and `drain_expired()`; it must keep partial-record cleanup and PTY behavior while signaling batch groups.
Test helper: `_assert_stop_kills_background_descendant(start_child, label)` accepts a two-argument launcher returning an inflight record.
Signal helper: `_signal_child(rec, sig)` uses `rec.get("mode")` to distinguish owned batch groups from PTY and partial records.
Gotcha: both `subprocess.Popen` calls retain DEC-086's `retry_eagain()` wrapper while adding `start_new_session=True`.
Reproduction: `uv run --group dev pytest -q tests/test_dispatch.py -k stopping_a_batch_agent` fails because the background `sleep` survives `stop_child()`.
Test coverage: commit `1cf740c` covers `spawn()`; planning adds equivalent behavioral coverage for `spawn_command()` because suites can also create descendants.
Revision: this plan names both helpers, their inputs, and the exact `mode` dispatch rejected by the previous validation.

## Decisions checked

DEC-032 requires source-change drains to wait for live leases instead of terminating live work; group signaling changes only an already-authorized stop.
DEC-061 requires Tier A gates to remain `spawn_command()` children, so that launch path must receive the same process-group ownership.
DEC-086 requires every spawn primitive to remain inside `retry_eagain()`; adding `start_new_session=True` must not bypass that wrapper.
DEC-123 requires `stop_child()` to remain the single total teardown path for shutdown and expired drains; process-group signaling belongs there.

## Plan

1. Refactor the reproduction in `tests/test_dispatch.py` into `_assert_stop_kills_background_descendant(start_child, label)`. The callable accepts a project path and command, then returns an inflight record. Poll PID-file creation and descendant disappearance with five-second deadlines. Include `label` and the surviving PID in failures. Kill any surviving descendant during cleanup. Keep `test_stopping_a_batch_agent_also_stops_its_background_descendant`. Add `test_stopping_a_dispatcher_command_also_stops_its_background_descendant` using `spawn_command()`. Run the focused command and require both tests to fail before implementation.
2. Add `start_new_session=True` inside both `retry_eagain()`-wrapped Popen calls in `pipeline/daemon/supervisor.py`. Define `_signal_child(rec, sig)` beside `stop_child()`. For every present non-interactive `rec["mode"]`, call `os.killpg(rec["proc"].pid, sig)` and ignore `ProcessLookupError`. For `"interactive"` or missing mode, call the process's existing `terminate()` or `kill()` method for the requested signal. Make `stop_child()` call `_signal_child()` for SIGTERM and timeout SIGKILL. Preserve both waits, `close_child()`, temporary-file cleanup, and lease release. Run focused and full dispatcher tests. Commit the two-file fix.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py -k 'stopping_a_batch_agent or stopping_a_dispatcher_command'` exits `0`; both launch paths lose their background descendants after `stop_child()`.
- `uv run --group dev pytest -q tests/test_dispatch.py` exits `0`; existing shutdown, source-drain, retry, and PTY-compatible dispatcher behavior remains green.
- `uv run --group dev pytest -q` exits `0`; the full dispatcher suite has no regression.

## Decisions

Batch agents and dispatcher-owned commands must start as process-group leaders. `stop_child()` must signal each owned group, because PID-only teardown leaves tool and suite descendants running.

## Rollback

Step 2 is riskiest because an incorrect group identity can signal unrelated processes. If its focused checks fail, revert `_signal_child()` and both `start_new_session=True` additions together. Keep the failing tests. Do not ship new-session creation with PID-only teardown. After release, revert the implementation commit if shutdown regresses. Manually reap descendants until a corrected fix lands.

## Thread

### 2026-09-12 11:22:00Z · triage · reproduction

Reproduced and committed `1cf740c`.

`spawn()` starts `sleep 60` in the batch shell's process group.
`stop_child()` terminates only the recorded shell PID.
The background `sleep` survives.

The PTY path differs because `PtyProc._signal()` calls `os.killpg`.
The batch path needs a new process session and group signal handling.

Test command failed with:

```
E   AssertionError: stopping the batch agent left background descendant 3982301 alive
```

### 2026-09-12 05:01:13Z · new · escalation

TICKET-134 depends_on TICKET-129, which is escalated and can never reach done

### 2026-09-12 11:09:14Z · human · note · by=chezzijr

**resumed** by chezzijr -> `new`, reset ['no_result']

### 2026-09-12 11:18:48Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-12 11:30:14Z · triage · session · session=01a09560-70dd-7471-95ae-3ecf3aaa9d9b

`triage` ran as session `01a09560-70dd-7471-95ae-3ecf3aaa9d9b`
- replay: `codex exec resume 01a09560-70dd-7471-95ae-3ecf3aaa9d9b`
- log: `.project/logs/TICKET-134-triage-911bd7a2.log`
- cost: unknown (the harness reported none)
- tokens: 3,298 out (813 thinking) · 535,580 in · 496,896 cache read · 0 cache write

### 2026-09-12 11:30:14Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Added and committed a failing batch-descendant shutdown reproduction

### 2026-09-12 11:34:51Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails as required
```
d time.monotonic() < deadline:
                time.sleep(.01)
            assert child_pid.exists(), "the batch agent did not start its background child"
            pid = int(child_pid.read_text())
    
            supervisor.stop_child("TICKET-001", rec)
    
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
>               raise AssertionError(
                    f"stopping the batch agent left background descendant {pid} alive")
E                   AssertionError: stopping the batch agent left background descendant 4054328 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 4054326 -> TICKET-001-review-77867ac7.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.23s ===============================

```
- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails on base `main` too -- the bug is not already fixed upstream
```
onError: stopping the batch agent left background descendant 4054777 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 4054776 -> TICKET-001-review-518dd1cd.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.64s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-7m7bdo30/base
      Built pipeline @ file:///tmp/pipeline-base-7m7bdo30/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 83ms

```
- `files_declared` is empty
- plan step names no declared file: '1. Extend `tests/test_dispatch.py` with a shared background-descendant lifecycle check for `spawn()` and `spawn_command()`, including bounded startup and shutdown polling, failure messages naming the surviving PID, and cleanup that kills leftovers; run the focused tests before implementation to prove both launch paths leak.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Update `pipeline/daemon/supervisor.py` so both retry-wrapped `subprocess.Popen` calls use `start_new_session=True`, add one process-group signal helper that tolerates vanished groups, and make `stop_child()` send SIGTERM then SIGKILL to non-interactive groups while preserving `PtyProc` signaling, waits, resource cleanup, and lease release; run focused and full dispatcher tests, then commit the two-file fix.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-12 11:38:32Z · planning · plan

Planned session ownership and group teardown for both batch launch paths.

The focused reproduction failed with:

```
E   AssertionError: stopping the batch agent left background descendant 4015862 alive
```

Consulted DEC-032, DEC-061, DEC-086, and DEC-123. The plan preserves live-lease drains, spawned gates, fork retries, and the shared total teardown path.

The direct gate reported only the dispatcher-owned `files_declared` claim as missing. Running the same gate with the result's two claims supplied in memory printed `gate: PASS`.

### 2026-09-12 11:41:03Z · planning · session · session=01a09561-e4b2-7650-a006-76700c0eca2e

`planning` ran as session `01a09561-e4b2-7650-a006-76700c0eca2e`
- replay: `codex exec resume 01a09561-e4b2-7650-a006-76700c0eca2e`
- log: `.project/logs/TICKET-134-planning-805349db.log`
- cost: unknown (the harness reported none)
- tokens: 13,295 out (7,143 thinking) · 2,004,799 in · 1,934,080 cache read · 0 cache write

### 2026-09-12 11:41:03Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned process-group teardown for both batch launch paths

### 2026-09-12 11:44:25Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails as required
```
) and time.monotonic() < deadline:
                time.sleep(.01)
            assert child_pid.exists(), "the batch agent did not start its background child"
            pid = int(child_pid.read_text())
    
            supervisor.stop_child("TICKET-001", rec)
    
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
>               raise AssertionError(
                    f"stopping the batch agent left background descendant {pid} alive")
E                   AssertionError: stopping the batch agent left background descendant 22709 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 22708 -> TICKET-001-review-588faf27.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.22s ===============================

```
- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails on base `main` too -- the bug is not already fixed upstream
```
ertionError: stopping the batch agent left background descendant 22852 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 22851 -> TICKET-001-review-40fe697a.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.65s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-xmv7qpx5/base
      Built pipeline @ file:///tmp/pipeline-base-xmv7qpx5/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 65ms

```

### 2026-09-12 11:45:53Z · plan-validation · validation

Result: `fail`.

- Root cause vs symptom — pass. Batch `Popen` children lack owned sessions, while `stop_child()` signals only the leader PID.
- Decision conflict — pass. The plan preserves DEC-032 lease waits, DEC-061 child gates, DEC-086 retries, and DEC-123 shared teardown.
- Scope discipline — pass. Both files and both launch paths trace to descendant cleanup and regression criteria.
- Falsifiable criteria — pass. Two behavioral tests require descendant disappearance, while dispatcher and full suites detect regressions.
- No research left — fail. Steps name files and existing entry points, but neither new shared helper has a function name. The signaling helper's inputs and the `stop_child()` dispatch condition also remain unspecified. Name both helpers and state whether dispatch uses `mode`, process type, or another concrete record field.
- Riskiest step — pass. Group identity is the stated risk. Reverting both group changes while retaining failing tests is a safe fallback.
- Regression surface — pass. Shutdown, source drains, EAGAIN retries, dispatcher commands, and PTY behavior have named suite coverage.
- Blast radius matches class — pass. A two-file change to shared launch and teardown code matches this bugfix.

### 2026-09-12 11:46:16Z · plan-validation · session · session=01a0956e-e308-7cb1-b40d-929b1e3f1394

`plan-validation` ran as session `01a0956e-e308-7cb1-b40d-929b1e3f1394`
- replay: `codex exec resume 01a0956e-e308-7cb1-b40d-929b1e3f1394`
- log: `.project/logs/TICKET-134-plan-validation-a02a6fe7.log`
- cost: unknown (the harness reported none)
- tokens: 3,503 out (1,871 thinking) · 358,194 in · 322,048 cache read · 0 cache write

### 2026-09-12 11:46:16Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ Plan leaves shared helper functions unnamed, so implementation research remains

### 2026-09-12 11:46:59Z · planning · session · session=01a09570-9248-7090-a515-8d9633d3f4e1

`planning` ran as session `01a09570-9248-7090-a515-8d9633d3f4e1`
- replay: `codex exec resume 01a09570-9248-7090-a515-8d9633d3f4e1`
- log: `.project/logs/TICKET-134-planning-6c84315b.log`

### 2026-09-12 11:46:59Z · planning · note

`planning` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-09-12 11:47:06Z · planning · session · session=01a09571-3905-7392-9539-67f1b222176e

`planning` ran as session `01a09571-3905-7392-9539-67f1b222176e`
- replay: `codex exec resume 01a09571-3905-7392-9539-67f1b222176e`
- log: `.project/logs/TICKET-134-planning-1e6f4481.log`

### 2026-09-12 11:47:06Z · planning · escalation

`planning` wrote no .result sidecar 2 times

### 2026-09-12 18:06:40Z · human · note · by=chezzijr

**resumed** by chezzijr -> `planning`, reset ['no_result']

### 2026-09-12 22:23:48Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails as required
```
d time.monotonic() < deadline:
                time.sleep(.01)
            assert child_pid.exists(), "the batch agent did not start its background child"
            pid = int(child_pid.read_text())
    
            supervisor.stop_child("TICKET-001", rec)
    
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
>               raise AssertionError(
                    f"stopping the batch agent left background descendant {pid} alive")
E                   AssertionError: stopping the batch agent left background descendant 1366767 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 1366766 -> TICKET-001-review-4219e386.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================

```
- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails on base `main` too -- the bug is not already fixed upstream
```
onError: stopping the batch agent left background descendant 1366841 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 1366840 -> TICKET-001-review-6fa167cd.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.58s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yg4p4knp/base
      Built pipeline @ file:///tmp/pipeline-base-yg4p4knp/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 46ms

```

### 2026-09-12 22:25:02Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails as required
```
d time.monotonic() < deadline:
                time.sleep(.01)
            assert child_pid.exists(), "the batch agent did not start its background child"
            pid = int(child_pid.read_text())
    
            supervisor.stop_child("TICKET-001", rec)
    
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
>               raise AssertionError(
                    f"stopping the batch agent left background descendant {pid} alive")
E                   AssertionError: stopping the batch agent left background descendant 1370913 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 1370912 -> TICKET-001-review-1f4df56c.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.22s ===============================

```
- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails on base `main` too -- the bug is not already fixed upstream
```
onError: stopping the batch agent left background descendant 1370975 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 1370974 -> TICKET-001-review-db87f622.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.58s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-_tj6kznm/base
      Built pipeline @ file:///tmp/pipeline-base-_tj6kznm/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 85ms

```

### 2026-09-12 22:25:25Z · planning · plan

Revised the plan after Tier B rejected unnamed helpers and an unspecified teardown branch.

The plan now defines `_assert_stop_kills_background_descendant(start_child, label)` for both launch-path tests. It defines `_signal_child(rec, sig)` for shared teardown.

`_signal_child()` uses `rec.get("mode")`. Present non-interactive modes signal the owned process group. Interactive and missing modes retain process methods, preserving PTY behavior and partial-record totality.

Consulted DEC-032, DEC-061, DEC-086, and DEC-123. The direct Tier A command printed `gate: PASS`.

### 2026-09-12 22:25:45Z · planning · session · session=01a097b4-bd51-7dc3-a9d9-5b52482f83c4

`planning` ran as session `01a097b4-bd51-7dc3-a9d9-5b52482f83c4`
- replay: `codex exec resume 01a097b4-bd51-7dc3-a9d9-5b52482f83c4`
- log: `.project/logs/TICKET-134-planning-667d3183.log`
- cost: unknown (the harness reported none)
- tokens: 8,415 out (4,805 thinking) · 1,129,891 in · 1,070,976 cache read · 0 cache write

### 2026-09-12 22:25:45Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Named both lifecycle helpers and specified mode-based process-group signaling

### 2026-09-12 22:26:52Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails as required
```
d time.monotonic() < deadline:
                time.sleep(.01)
            assert child_pid.exists(), "the batch agent did not start its background child"
            pid = int(child_pid.read_text())
    
            supervisor.stop_child("TICKET-001", rec)
    
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
>               raise AssertionError(
                    f"stopping the batch agent left background descendant {pid} alive")
E                   AssertionError: stopping the batch agent left background descendant 1375261 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 1375260 -> TICKET-001-review-5b59c7a5.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================

```
- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails on base `main` too -- the bug is not already fixed upstream
```
onError: stopping the batch agent left background descendant 1375336 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 1375335 -> TICKET-001-review-ae1b2b86.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.57s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-f7n4cwc7/base
      Built pipeline @ file:///tmp/pipeline-base-f7n4cwc7/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 77ms

```

### 2026-09-12 22:27:59Z · plan-validation · validation

Result: `ok`.

- Root cause vs symptom — pass. Batch children lack owned sessions, so PID-only teardown cannot reach descendants. The plan creates and signals owned groups.
- Decision conflict — pass. It preserves DEC-032 lease waits, DEC-061 child gates, DEC-086 retry wrappers, and DEC-123 shared teardown.
- Scope discipline — pass. Both files and launch paths trace directly to descendant cleanup and its regression tests.
- Falsifiable criteria — pass. Incorrect group teardown leaves a descendant alive; focused tests detect that outcome. Broader suites detect lifecycle regressions.
- No research left — pass. The plan names both files, both launch functions, `_signal_child(rec, sig)`, the test helper, its launcher contract, and mode dispatch.
- Riskiest step — pass. Group identity is the stated risk. The fallback reverts signaling and session creation together while retaining failing tests.
- Regression surface — pass. Dispatcher tests cover shutdown, source drains, retries, dispatcher commands, and PTY-compatible teardown. The full suite covers wider regressions.
- Blast radius matches class — pass. A two-file launch-and-teardown change matches this bugfix.

Unverified: I did not reinspect current implementations. The combined `rg`, status, and diff probe was blocked for shell redirection. I would run separate read-only searches over `supervisor.py`, `host.py`, and `test_dispatch.py` after allowlisting them.

### 2026-09-12 22:28:25Z · plan-validation · session · session=01a097bb-1113-7272-a9d8-8137a981cb98

`plan-validation` ran as session `01a097bb-1113-7272-a9d8-8137a981cb98`
- replay: `codex exec resume 01a097bb-1113-7272-a9d8-8137a981cb98`
- log: `.project/logs/TICKET-134-plan-validation-2519bfba.log`
- cost: unknown (the harness reported none)
- tokens: 3,685 out (2,121 thinking) · 315,140 in · 290,560 cache read · 0 cache write

### 2026-09-12 22:28:25Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Revised plan passes all eight judgment checks and resolves the prior helper and dispatch ambiguity

### 2026-09-13 00:52:27Z · human · note · by=chezzijr

**note from chezzijr**

Approved by Claude on the operator's behalf. Checked: two files, neither fenced; start_new_session=True on both retry_eagain()-wrapped Popen calls, and _signal_child() uses os.killpg only for non-interactive records while interactive keeps PtyProc's own terminate()/kill() -- so the PTY path, which already had killpg, is untouched. stop_child()'s two waits, close_child(), temp-file cleanup and lease release are all preserved, which is the part a naive group-signal rewrite would drop. Both tests required to fail before implementation. No concern raised.

### 2026-09-13 00:52:27Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-13 01:08:31Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails as required
```
d time.monotonic() < deadline:
                time.sleep(.01)
            assert child_pid.exists(), "the batch agent did not start its background child"
            pid = int(child_pid.read_text())
    
            supervisor.stop_child("TICKET-001", rec)
    
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
>               raise AssertionError(
                    f"stopping the batch agent left background descendant {pid} alive")
E                   AssertionError: stopping the batch agent left background descendant 1431359 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 1431358 -> TICKET-001-review-9368a56b.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.46s ===============================

```
- ok: `tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant` fails on base `main` too -- the bug is not already fixed upstream
```
onError: stopping the batch agent left background descendant 1431424 alive

tests/test_dispatch.py:2688: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: review (opus, batch) pid 1431423 -> TICKET-001-review-f389d751.log
  stopped TICKET-001 (review)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_stopping_a_batch_agent_also_stops_its_background_descendant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.58s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jkn62vzc/base
      Built pipeline @ file:///tmp/pipeline-base-jkn62vzc/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 65ms

```

### 2026-09-13 01:08:31Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-13 · implementing · todo

1. Refactor both descendant-stop regressions and verify they fail.
2. Create sessions and signal owned batch process groups.
3. Run focused and full suites, then commit the two-file fix.

### 2026-09-13 · implementing · result

Completed all three todo items.

Both regressions failed before production changes. Each reported its surviving background descendant.

Added `start_new_session=True` to both batch `Popen` calls. Added `_signal_child()` to signal non-interactive process groups. Interactive and partial records retain process-method signaling.

Tests passed:

1. `uv run --group dev pytest -q tests/test_dispatch.py -k 'stopping_a_batch_agent or stopping_a_dispatcher_command'` — 2 passed.
2. `uv run --group dev pytest -q tests/test_dispatch.py` — 109 passed.
3. `uv run --group dev pytest -q` — passed with no recorded failures.

Committed `57be51a` as `fix(TICKET-134): stop batch process groups`.

### 2026-09-13 01:12:17Z · implementing · session · session=01a0984f-0f5f-7973-a112-2d82f654dcef

`implementing` ran as session `01a0984f-0f5f-7973-a112-2d82f654dcef`
- replay: `codex exec resume 01a0984f-0f5f-7973-a112-2d82f654dcef`
- log: `.project/logs/TICKET-134-implementing-06273721.log`
- cost: unknown (the harness reported none)
- tokens: 5,577 out (1,959 thinking) · 865,488 in · 816,128 cache read · 0 cache write

### 2026-09-13 01:12:17Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added owned batch process groups and descendant-stop coverage

### 2026-09-13 · review · result

No blocking findings survived review.

The two batch launchers retain `retry_eagain()` and add `start_new_session=True`. `_signal_child()` sends both teardown signals to owned non-interactive groups.

Interactive and partial records retain process-method signaling. `stop_child()` preserves both waits, cleanup, and lease release.

The focused regressions passed: `2 passed, 107 deselected`.

The dispatcher run reached `104 passed`. Five untouched server tests failed because this review sandbox denied AF_UNIX `bind()` at `pipeline/daemon/server.py:333`.

### 2026-09-13 01:16:44Z · review · session · session=01a09852-7f49-7bd2-874f-e7d06b6af743

`review` ran as session `01a09852-7f49-7bd2-874f-e7d06b6af743`
- replay: `codex exec resume 01a09852-7f49-7bd2-874f-e7d06b6af743`
- log: `.project/logs/TICKET-134-review-15d478c9.log`
- cost: unknown (the harness reported none)
- tokens: 8,665 out (5,530 thinking) · 642,661 in · 592,768 cache read · 0 cache write

### 2026-09-13 01:16:44Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Review found no blocking findings in the process-group teardown delta

### 2026-09-13 01:17:52Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-13 01:34:51Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/134


Rebasing (1/2)Rebasing (2/2)Successfully rebased and updated refs/heads/ticket/134.
Already up to date.
Updating 560d735..e8c8618
Fast-forward
 pipeline/daemon/supervisor.py | 26 ++++++++++++++++----
 tests/test_dispatch.py        | 56 +++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 78 insertions(+), 4 deletions(-)

```

### 2026-09-13 01:34:51Z · merging · decision

decision recorded as `DEC-134`
