---
id: TICKET-061
stage: done
class: bugfix
branch: ticket/061
test_file: tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test
files_declared:
- .project/known-issues.md
- CLAUDE.md
- pipeline/cli/main.py
- pipeline/daemon/supervisor.py
- tests/test_cli.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 29
  plan_files: 6
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 780b8584-0656-437c-b19b-a3c8ee84a2d3
  log: .project/logs/TICKET-061-review-780b8584.log
approved_by: chezzijr
approved_at: '2026-08-26T19:29:20.432892+00:00'
---

## Summary

Implemented (2026-08-27): the Tier A gate now runs as a `spawn_command()` child
(`gate_cmd()`, `python -P -m pipeline gate --findings PATH`) instead of an inline
`gate()` call inside the select loop, so the daemon keeps answering clients and
draining other children's pipes while a project's `test_one` runs. `finish_gate()`
reads the child's findings file back and applies the verdict; a PASS at
`plan-validation` is a phase recorded in `counters["gate_ok"]` (consumed by the
next `start()`, no `stage_end`), a FAIL behaves exactly as the old inline path did.
`revalidating` chains the rebase and the gate in one child (`regate_cmd()`, exit 3
= rebase conflict). `pipeline/core/gate.py` is unchanged. Full suite green (327
tests) and the guard's 109 cases pass. See `## Thread` entry "implementing · done"
for the full breakdown.

Reviewed (2026-08-27): pass, no blocking finding on the delta 67c3872..59652b5.
`uv run --group dev pytest -q` -> `327 passed in 15.54s`, every named acceptance
test among them, and `pipeline/core/gate.py` is unchanged. The review raised two
findings and refuted both against the code. Four minor items are listed in the
thread entry "review · findings" and none of them block: an unused `gate` import,
a dead `if rec is not None`, an unswept findings JSON after a daemon crash, and
the `revalidating` rebase now running under the dispatcher's env.

the daemon stops answering while gate() runs the project's test, so the TUI toasts timeouts and no pipe is drained

`pipeline tui` shows `daemon: daemon: cannot read from timed out object`, in
bursts, repeatedly, while tickets are moving. Reported by the operator as
happening a lot; seen five times in one screenshot on 2026-08-26.

The message is the client's 5s socket timeout (`Client.__init__`,
`pipeline/cli/client.py:18-21`) surfacing through `_rows()`
(`pipeline/tui/app.py:262-264`), which catches it, toasts, and falls back to
reading the ticket files:

    try:
        return self.client.request("ls", project=self.project)
    except PipelineError as e:
        self.notify(f"daemon: {e}")

The daemon is not wedged; it is busy in its own loop. `gate()` runs the
project's `test_one` synchronously inside it, at
`pipeline/daemon/supervisor.py:712` (plan-validation) and `:851`
(`finish_regate`). For this project that is
`uv run --group dev pytest -x {test}`, and in a fresh worktree it builds a
venv first -- from TICKET-056's own gate output:

    Using CPython 3.13.11
    Creating virtual environment at: .venv
       Building pipeline @ file:///tmp/pipeline-base-2cyuna0f/base
    Installed 18 packages in 9ms

For that whole span the select loop serves nothing, so every `ls` the TUI
sends at its 5s refresh times out, which is why the toasts arrive in bursts
rather than singly.

Measured on 2026-08-26 to rule out the other per-tick work, so the fix does not
chase the wrong call:

    pipeline ls                     0.13s x8   loop idle
    git status --porcelain ...      0.00s x3   tree_snapshot is not the cost
    git worktree add --detach       0.01s      ensure_worktree is not the cost

The toast is cosmetic -- the tree still paints from files. The reason to fix it
is the other half, which `_widen()` already documents at
`pipeline/daemon/supervisor.py:174-177`: while the loop blocks, NOTHING drains
any child's stdout, so a chatty agent fills the 1M pipe and blocks in `write()`
holding its lease. `_widen()` calls itself "headroom, not a fix".

Expected: the daemon answers a client request while a gate runs, and a child's
pipe keeps draining. No behaviour change to what the gate decides.

Suggestion only, planning decides: the code names its own upgrade path in a
`ponytail:` comment directly above the blocking call --

    # ponytail: `gate()` runs the project's `test_one` synchronously, and
    # for its duration no pipe is drained -- a very chatty agent can still
    # fill 1M and block. Upgrade = run the gate as a spawned child like
    # `verifying` does, which is a `DISPATCHER_STAGES` change, not a
    # daemon one.

`spawn_command()` (`pipeline/daemon/supervisor.py:450`) already exists for
exactly this and says why it was written: "Run inline the suite stalled the
loop: no other ticket advanced and no finished agent was reaped while a real
project's suite took its minutes."

Two things the plan must not paper over:

1. `gate()` returns a verdict plus findings that the caller acts on
   immediately. A spawned gate answers later, so the state machine has to hold
   the ticket somewhere in between -- decide where, rather than blocking a
   different way.
2. Raising the client's 5s timeout would hide the toast and fix nothing: the
   pipe still is not drained. If the timeout is touched at all, say why it is
   not the fix.

Nothing here is in `machine.FENCED`.

Triage confirmed this with a real `pipelined` process: a client's `ls`
request times out with `daemon: timed out` while `gate()` runs a 3s
`test_one`. See `## Reproduction` and `## Thread` for the test and evidence.
This needs planning, not a `chore` fix: it is a design change to how
`gate()` runs and where the ticket waits meanwhile.

Planned (2026-08-27): `gate()` moves out of the loop and runs as a
`spawn_command()` child (`python -m pipeline gate --findings PATH`), the
upgrade path the `ponytail:` comment names. The ticket waits at its own stage
on the lease `child()` takes, exactly where `verifying` waits for its suite --
no new stage, no `transition()` row, nothing in `machine.FENCED`. A Tier A
pass at `plan-validation` is a phase, not an ended attempt: it is recorded in
`counters["gate_ok"]`, consumed by the next `start()`, and emits no
`stage_end`. `revalidating` rebases and gates in one child, exit code 3
meaning the rebase conflicted. The client's 5s timeout is untouched: raising
it hides the toast and leaves the pipe undrained. `## Plan` and
`## Decisions` carry the detail; the thread adds nothing a stage needs.

Plan-validation rejected the plan on 2026-08-27 on two items; the approach
itself passed the other seven. Both are fixed in `## Plan`, which is
re-submitted with the same approach.

1. The escalation test is named `test_a_bound_escalation_emits_an_escalated_event`
   (`tests/test_dispatch.py:454`). Step 20 and its acceptance criterion use that
   name, and step 20 drives the gate child through `wait()` and `finish()`.
2. The gate child runs `python -P -m pipeline`. Without `-P`, `spawn_command()`'s
   `cwd=wt` makes `-m` import the ticket worktree's own copy of `pipeline`. With
   `-P` the dispatcher's copy judges the gate: `PYTHONPATH` if set, else the
   venv's editable install. Step 7, digest gotchas 5 and 6, and `## Decisions`
   all say so.

Planning fixed one more thing nobody flagged: step 1's fixture. `pipeline gate`
on a plain `helpers.project()` exits 0 `gate: PASS`, so the step now builds
`project(test_passes=True)`, which exits 1 with one finding. Step 26 also picks
up `bail()`'s stale docstring, the third stale comment the reviewer named.

Plan-validation accepted the plan on 2026-08-27: all nine items pass. Both
rejected items are fixed -- step 20 names
`test_a_bound_escalation_emits_an_escalated_event` and step 7 runs `-P`. Three
checks the reviewer ran against the code: `DISPATCHER_STAGES` stays untouched
and `tests/test_stages.py:70-79` does not forbid a prompt-bearing stage from
using `spawn_command()`; no metrics view reads `stage_start`, so the gate
child's new one skews nothing; `gate()` returns findings with every non-blank
fence already replaced (`pipeline/core/gate.py:402-403`), so step 1's
no-backticks assertion holds. Implementation can work from `## Plan` alone.

## Reproduction

`tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test`

Run: `uv run --group dev pytest -x tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test`

A real `pipelined` subprocess with a `plan-validation` ticket whose `test_one`
is `sleep 3; echo test_broken; exit 1`. A `Client` with a 1s timeout sends
`ls` 1s after the daemon comes up, while `gate()` is inside the `sleep 3`.
The request times out instead of getting a reply.

Failure output:

    AssertionError: daemon did not answer while the gate ran: daemon: timed out

expect: daemon: timed out

## Digest

Files this change touches, and what each is responsible for:
- `pipeline/daemon/supervisor.py` -- the loop. `start()` picks one branch per stage; the local `child(cmd, kind)` (line 661) takes the lease, saves, and calls `spawn_command()`; `_finish()` routes a dispatcher-owned child by `rec["kind"]`; `finish()` emits `stage_end`.
- `pipeline/cli/main.py` -- `cmd_gate()` (line 86) already runs the gate in the ticket's worktree and exits `0` on PASS, `1` on FAIL. It becomes the command the dispatcher spawns.
- `pipeline/core/gate.py` -- READ ONLY in this ticket. `gate()` decides nothing new; only where it runs changes.

Key functions:
- `gate(project, tid, workdir)` (`pipeline/core/gate.py:164`) runs three project commands: `test_one` in the worktree, `test_suite_without_new`, and `_base_findings()`, which cuts a base checkout and runs `test_one` again. That is the whole cost, and DEC-017 forbids removing the base run to make it cheaper.
- `spawn_command(project, wt, tid, stage, cmd, kind, emit)` (`pipeline/daemon/supervisor.py:450`) -- a tracked child shaped like `spawn()`'s record, collected by `reap()`. Its stdout goes straight to the log file, so it needs no pipe and no `pump()`.
- `finish_suite` / `finish_child` / `finish_regate` -- one finisher per `kind`, all called from `_finish()`.
- `child()` inside `start()` -- the lease is what holds a ticket at its own stage while a dispatcher-owned child runs. `verifying` already waits there for a whole regression suite.

Entry points: `start()` at `pipeline/daemon/supervisor.py:705` (`plan-validation`, the inline `gate()` call and its `ponytail:` comment) and `:689` (`revalidating`); `finish_regate()` at `:824` (the second inline `gate()` call); `pipeline/__main__.py`, which is what makes `python -m pipeline` the CLI.

Gotchas, each checked against the code today:
1. `plan-validation` is two checks, not one: the deterministic Tier A `gate()` and then a Tier B agent (`pipeline/stages/plan-validation.md`, spawned by the fall-through at `start()`'s end). Only the Tier A half moves. A Tier A pass must still spawn the agent.
2. Metrics view 1 is `escalated / stage_end` per stage (`pipeline/cli/metrics.py:135`, where `runs` counts `stage_end` rows). A passing gate child must emit no `stage_end`, or one `plan-validation` attempt puts two rows in the denominator and every escalation rate for that stage halves.
3. `spawn_command()` runs its child under `project_env()`, which pops `PYTHONPATH` and strips the venv from `PATH`. The gate child is the dispatcher's OWN code and needs the dispatcher's own environment; the project commands it runs re-apply `project_env()` inside `run_cmd()`. `tests/test_daemon.py` starts the daemon with `PYTHONPATH=ROOT`, so a stripped env there breaks the child's import.
4. `gate()` returns findings whose fenced output has already been replaced by a reference to the `## Thread` entry it just wrote (DEC-046). Pass the returned strings through unchanged; re-deriving findings from the child's log would put the same output in the thread twice.
5. A bare `python -m pipeline` would import the WORKTREE's copy of `pipeline`: `spawn_command()` runs its child with `cwd=wt` (`pipeline/daemon/supervisor.py:463`) and `-m` prepends the cwd to `sys.path`, and this project's worktree holds a `pipeline/` package. `-P` is the fix, verified today on this repo's CPython 3.13.11: `python -P -c ...` reports `sys.flags.safe_path` True and no cwd entry in `sys.path`. `-P` drops the cwd entry and keeps `PYTHONPATH`, so gotcha 3's `PYTHONPATH=ROOT` path still imports.
6. Which copy judges the gate, with `-P`: the DISPATCHER's copy, never the ticket's worktree. `PYTHONPATH` wins if set -- that is `tests/test_daemon.py`, which sets `PYTHONPATH=ROOT` -- otherwise the venv's `_editable_impl_pipeline.pth`, whose one line reads `/home/chezzijr/proj/agent-pipeline`, the checkout the daemon itself runs from. `sys.executable` is an absolute path into that venv, so nothing here depends on `PATH`.
7. The guard blocks a file tool under `.project/` unless the path is `PIPELINE_TICKET` or `PIPELINE_RESULT`, and a read-only stage's Bash allowlist refuses redirection. `.project/known-issues.md` is edited by `implementing`, which is a write stage, so Bash reaches it there.
8. `counters` is dispatcher-owned (`machine.CONTROL_FIELDS`) and restored from the pre-spawn snapshot, so a two-phase stage can carry its phase there and no agent can set it. `counters["cheap_route"]` is the existing precedent.

## Decisions checked

- DEC-017 (active) -- Tier A's base run is load-bearing, and its "Known cost, accepted" paragraph names this exact fix: "If the gate becomes the loop's bottleneck the fix is the one known-issue 14 already names (run the gate as a spawned child like `verifying`), not deleting the base run." This plan moves where `gate()` runs and changes no check inside it.
- DEC-046 (active) -- `gate()` returns findings whose fences already point at the thread entry it wrote, because `advance()` copies the returned failures into a note of its own. The findings file carries those returned strings verbatim, so the thread reads exactly as it does today.
- DEC-011 (active) -- the select loop is the extension point, its callbacks must not block, and `stage_start` / `stage_end` are `spawn()` / `spawn_command()`'s events. This plan adds no fd to the loop and no event kind.
- DEC-029 (active) -- the `revalidating` conflict repair (abort, `git reset --hard base`, back to `triage`) is safe only while the branch carries triage's test commit and nothing else. The plan keeps the repair at `revalidating` and keeps the rebase the only step that can trigger it.
- DEC-045 (active) -- the rebase at `merging` may not fail the merge child. `merging` is untouched here; the `revalidating` rebase keeps its own opposite rule, where a conflict IS the verdict.
- Grep terms used in `.project/decisions/`: `gate`, `spawn_command`, `drain`, `pipe`, `select loop`, `synchronous`, `blocking`, `stage_end`, `counters`, `plan-validation`, `revalidating`.
- Nothing in `machine.FENCED` is touched: `transition()` gains no row, no stage is added or removed, and `DISPATCHER_STAGES` is unchanged.

## Plan

1. Write the failing test `test_gate_writes_its_findings_where_the_dispatcher_asked` in `tests/test_cli.py`, whose import line becomes `from helpers import ROOT, project`: build `d = project(test_passes=True)` so Tier A fails with exactly one finding, put `out` under a `tempfile.mkdtemp()`, run `cli(d, "gate", "TICKET-001", "--findings", str(out))`, then assert `r.returncode == 1`, `json.loads(out.read_text())["ok"] is False`, `len(data["findings"]) == 1`, and that no finding contains three backticks (DEC-046 keeps the fence in the thread entry, not in the returned finding). Use `test_passes=True`, not the default: `pipeline gate TICKET-001` on a plain `project()` exits 0 `gate: PASS`, and on `project(test_passes=True)` it exits 1 and prints one finding, `` `test_thing.py::test_broken` PASSES -- it must fail before implementation ``. Both commands were run today.
2. Run `uv run --group dev pytest -x tests/test_cli.py::test_gate_writes_its_findings_where_the_dispatcher_asked` and watch it fail with `error: unrecognized arguments: --findings` -- `tests/test_cli.py` proves the flag does not exist yet.
3. Add the flag in `pipeline/cli/main.py`: on the `gate` subparser line add `p.add_argument("--findings", help="write {ok, findings} JSON here; the dispatcher's gate child reads it back")`, and in `cmd_gate()` insert, between the `gate()` call and the `for f in failures:` loop, `if args.findings: Path(args.findings).write_text(json.dumps({"ok": ok, "findings": failures}))` plus a comment saying the exit code is the verdict and this file is how the findings reach the thread note and the `gate` event. `json` and `Path` are already imported there.
4. Re-run the step-2 command on `tests/test_cli.py`, see it pass, and commit `pipeline/cli/main.py` with `tests/test_cli.py`.
5. Write the failing test `test_the_tier_a_gate_runs_as_a_spawned_child` in `tests/test_dispatch.py` (add `import time` to that file's imports): `git_project()`, commit `test_thing.py`, write `.project/pipeline.toml` with `test_one = "sleep 5; echo test_broken; exit 1"` plus `test_suite = "true"`, `test_suite_without_new = "true"` and `base = "main"`, write `FIXTURE` to the ticket, time one `supervisor.start(d, path, harness("fake"), {})`, then assert `rec["kind"] == "gate"`, `elapsed < 2`, `rec["proc"].poll() is None`, `Ticket.load(path).stage == "plan-validation"` and `Ticket.load(path).lease_active()`; end the test by killing the child and calling `supervisor.close_child(rec)`.
6. Run `uv run --group dev pytest -x tests/test_dispatch.py::test_the_tier_a_gate_runs_as_a_spawned_child` and watch it fail: `start()` blocks for the whole `sleep 5` and returns `(True, None)` with the ticket already at `planning`.
7. In `pipeline/daemon/supervisor.py`, add the constant `GATE_PASS = "gate-pass"` and the builder `gate_cmd(project, tid, findings)` returning `f"{shlex.quote(sys.executable)} -P -m pipeline --project {shlex.quote(str(project))} gate {shlex.quote(tid)} --findings {shlex.quote(str(findings))}"`, whose docstring states three things: it is a child because the loop served nothing for the length of `test_one`; it runs the dispatcher's own interpreter because this is the dispatcher's own code, and the project commands under it re-strip the venv in `run_cmd()`; and `-P` is load-bearing because `spawn_command()` runs with `cwd=wt` (`pipeline/daemon/supervisor.py:463`) and a bare `-m` prepends that cwd, so the WORKTREE's `pipeline/` would judge the gate and a branch cut before this change would run a `cmd_gate()` with no `--findings`.
8. In `pipeline/daemon/supervisor.py`, give `spawn_command()` a keyword argument `env: dict | None = None` and pass `env=env or project_env()` to its `subprocess.Popen`, so `suite`, `merge` and `unwind` children keep `project_env()` unchanged.
9. In `pipeline/daemon/supervisor.py`, add `read_findings(rec, code)` returning `(ok, failures)`: parse `json.loads(Path(rec["findings"]).read_text())`, unlink that file in a `finally`, return `(False, [one finding naming the exit code, the log file name and `log_tail(rec)`])` on any exception, and return `(False, [one finding saying the exit code and the file disagree])` when `ok != (code == 0)` -- fail closed, exactly like `finish_suite()`.
10. In `pipeline/daemon/supervisor.py`, add `finish_gate(project, rec, emit)`: `close_child(rec)`, `ok, failures = read_findings(rec, rec["proc"].returncode)`, `emit("gate", ticket=rec["tid"], stage=rec["stage"], verdict="pass" if ok else "fail", findings=failures)`, reload `t = Ticket.load(rec["path"])`; when `ok and t.stage == "plan-validation"` set `t.counters["gate_ok"] = 1`, `t.release_lease()`, `t.save()` and return `GATE_PASS`; otherwise call `advance(project, t, "ok" if ok else "fail", note, emit, agent=False)` and return `"ok"` or `"fail"`.
11. In `pipeline/daemon/supervisor.py`, build `finish_gate()`'s `note` from the failures: open it with `re-gated after rebasing onto base` when `rec.get("base")` is set and with `Tier A gate` otherwise, say `passed` when `ok`, and otherwise append one bullet (`- ` plus the finding) per entry of `failures`, joined by newlines -- the same shape `start()` writes today.
12. In `pipeline/daemon/supervisor.py`, replace the inline gate in `start()`'s `plan-validation` branch (the `ponytail:` comment, the `drain_all`, the `gate()` call, the `advance` and the manual `stage_end` emit) with a two-phase branch: when `not t.counters.get("gate_ok")`, build `out = project / ".project" / "logs" / f"{tid}-gate-{uuid.uuid4().hex[:8]}.json"`, call `ok, rec = child(gate_cmd(project, tid, out), "gate", env=dict(os.environ))`, set `rec["findings"] = out` and return; otherwise `t.counters.pop("gate_ok", None)` and fall through to the Tier B agent spawn, so a lease-expiry respawn re-gates instead of trusting a stale pass.
13. In `pipeline/daemon/supervisor.py`, give the local `child(cmd, kind)` inside `start()` an `env=None` parameter that it forwards to `spawn_command()`, so only the gate and regate children run under the dispatcher's environment.
14. In `pipeline/daemon/supervisor.py`, route the new kind in `_finish()` with `if rec.get("kind") == "gate": return finish_gate(project, rec, emit)`, placed beside the `regate` branch.
15. In `pipeline/daemon/supervisor.py`, stop `finish()` emitting `stage_end` for a passing gate: after its `finally: close_child(rec)` add `if result == GATE_PASS: return`, with a comment that a Tier A pass is a phase of `plan-validation` and that a row here would double view 1's denominator for one run.
16. Run the step-6 command on `tests/test_dispatch.py` and see it pass, then run `uv run --group dev pytest -x tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test` and see the reproduction pass, then commit `pipeline/daemon/supervisor.py` with `tests/test_dispatch.py`.
17. In `tests/test_dispatch.py`, extract the project setup of `_ticket_awaiting_approval()` (its `git_project()`, the committed `test_thing.py`, and the `pipeline.toml` whose `test_one` is `echo test_broken; exit 1` and whose `test_suite_without_new` is `! test -f broken`) into a helper `_gating_project()` returning `(d, sh)`, and call it from `_ticket_awaiting_approval()`.
18. Add `test_a_failing_gate_child_sends_the_ticket_back_to_planning` to `tests/test_dispatch.py`: a `git_project()` with no `test_thing.py` committed so Tier A fails on the missing test file, `start()` with a `Store` emitter, `rec["proc"].wait()`, `supervisor.finish(...)`, then assert `stage == "planning"`, `counters["plan_validation_attempts"] == 1`, `not lease_active()`, a `gate` thread entry whose text contains `Tier A gate: FAIL`, exactly one `gate` event and one `stage_end` event, and `not rec["findings"].exists()`.
19. Add `test_a_passing_gate_child_hands_the_ticket_to_the_plan_validation_agent` to `tests/test_dispatch.py`: from `_gating_project()` write `FIXTURE`, run `start()` then `wait()` then `finish()`, assert the ticket is still at `plan-validation` with `counters["gate_ok"] == 1`, no active lease and ZERO `stage_end` events; then run `start()` again and assert the record has no `kind` (a real agent spawn), `rec["stage"] == "plan-validation"` and `"gate_ok" not in Ticket.load(path).counters`; finish by waiting on the fake agent and calling `supervisor.close_child`.
20. Update `test_a_bound_escalation_emits_an_escalated_event` (`tests/test_dispatch.py:454`) to drive the child: keep its `git_project()` and its `counters: {plan_validation_attempts: 1}` fixture, turn the bare `supervisor.start(d, path, harness("fake"), {}, None, s.emitter(str(d)))` into `did, rec = supervisor.start(...)` followed by `rec["proc"].wait()` and `supervisor.finish(d, rec, s.emitter(str(d)))`, leave every existing assertion unchanged (`stage == "escalated"`, one `escalated` event whose reason names `plan_validation_attempts` and the bound `2`, `escalation_rate(conn, "plan-validation") == 1.0`, non-empty `gate_failure_reasons(conn)`), and rewrite its docstring's last paragraph -- the stage's `stage_end` now comes from `finish()` on the gate child, not from `start()`.
21. Run `uv run --group dev pytest -x tests/test_dispatch.py` and expect the three new tests plus the updated escalation test to pass.
22. In `pipeline/daemon/supervisor.py`, add `REBASE_FAILED = 3` and `regate_cmd(project, tid, base, findings)`, which returns the line `git rebase {shlex.quote(base)} || exit {REBASE_FAILED}` followed by a newline and then `gate_cmd(project, tid, findings)`, documented as one child for two steps because the gate has to judge the tree the rebase produced.
23. In `pipeline/daemon/supervisor.py`, change `start()`'s `revalidating` branch to `child(regate_cmd(project, tid, base, out), "regate", env=dict(os.environ))` with the same `out` path shape as step 12, and set both `rec["base"] = base` and `rec["findings"] = out`.
24. In `pipeline/daemon/supervisor.py`, cut the inline `gate()` out of `finish_regate()`: keep the conflict repair under `if code == REBASE_FAILED`, and end the function with `return finish_gate(project, rec, emit)` so one function decides every gate verdict.
25. Run `uv run --group dev pytest -x tests/test_dispatch.py -k "regate or revalidating or stale_plan or still_good or rebase_conflict"` and expect `test_a_stale_plan_is_re_gated_on_approval`, `test_a_still_good_plan_is_implemented_after_the_rebase`, `test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage` and `test_a_rebase_conflict_at_revalidating_leaves_a_way_back` to pass with their assertions unchanged.
26. Update the three stale comments in `pipeline/daemon/supervisor.py`: `_widen()`'s docstring must stop listing `gate()` among the loop's blocking calls (keep `ensure_worktree` and `worktree_setup`, and keep `_widen` itself as headroom); `reap()`'s `drain_all(inflight)` comment must stop saying "a `regate` finish runs the gate, which blocks"; and `bail()`'s docstring (`pipeline/daemon/supervisor.py:601-602`) must stop saying a failed Tier A gate "spawns nothing either" -- it spawns a gate child now, and `finish()` emits that child's `stage_end`.
27. Rewrite entry 14 of `.project/known-issues.md` as fixed by TICKET-061: the Tier A gate runs as a `spawn_command()` child, the ticket waits at its own stage on its lease, and the 1 MiB pipes and `drain_all()` remain only for the git calls.
28. Add one gotcha bullet to `CLAUDE.md` under "Gotchas, each found the hard way": the Tier A gate runs as a spawned child (`gate_cmd()`), a PASS is a phase of `plan-validation` carried in `counters["gate_ok"]` and emits no `stage_end`, and moving the gate back inline stalls the select loop for the length of the project's suite.
29. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, then commit `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py`, `.project/known-issues.md` and `CLAUDE.md`.

## Acceptance criteria

- `uv run --group dev pytest -x tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test` passes: a client's `ls` is answered while `gate()` runs a 3-second `test_one`. This is the ticket's reproduction and it fails today.
- `tests/test_dispatch.py::test_the_tier_a_gate_runs_as_a_spawned_child` passes: `start()` returns in under 2 seconds with `rec["kind"] == "gate"` while a 5-second `test_one` is still running. That returned-to-the-loop span is the same one in which nothing used to drain a child's pipe.
- `tests/test_dispatch.py::test_a_failing_gate_child_sends_the_ticket_back_to_planning` passes: a failed Tier A gate still charges `plan_validation_attempts` once, still lands the ticket at `planning`, still writes one `gate` event and exactly one `stage_end`, and leaves no findings file behind.
- `tests/test_dispatch.py::test_a_passing_gate_child_hands_the_ticket_to_the_plan_validation_agent` passes: a passed Tier A gate leaves the ticket at `plan-validation` with `counters["gate_ok"] == 1` and no `stage_end` event, and the next `start()` spawns the Tier B agent with `gate_ok` consumed.
- `tests/test_dispatch.py::test_a_bound_escalation_emits_an_escalated_event` still reports `metrics.escalation_rate(conn, "plan-validation") == 1.0` and a non-empty `metrics.gate_failure_reasons(conn)`, so views 1 and 4 read the same as before.
- `tests/test_cli.py::test_gate_writes_its_findings_where_the_dispatcher_asked` passes: `pipeline gate --findings PATH` exits 1 and writes `{"ok": false, "findings": [...]}` with no fenced output inside a finding.
- The four `revalidating` tests in `tests/test_dispatch.py` -- `test_a_stale_plan_is_re_gated_on_approval`, `test_a_still_good_plan_is_implemented_after_the_rebase`,
  `test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage` and `test_a_rebase_conflict_at_revalidating_leaves_a_way_back` -- pass with their assertions unchanged.
- `uv run --group dev pytest -q` is green and `./pipeline/hooks/test_dangerous_commands.py` reports no failing case.
- `uv run --group dev pytest -q tests/test_gate.py` is green and `git diff --stat` shows `pipeline/core/gate.py` unchanged: what the gate decides does not move with where it runs.

## Decisions

**The Tier A gate runs as a `spawn_command()` child, and the ticket waits at its own stage on its lease.** Run inline it stalled the select loop for the whole of the project's `test_one` -- three project commands, one of them a base checkout -- and for that span the daemon answered no client request (`daemon: timed out` in the TUI) and nothing drained any agent's stdout, so a chatty agent could fill a 1 MiB pipe and block in `write()` holding its lease. There is no new stage and no `transition()` row: the ticket stays at `plan-validation` (or `revalidating`) exactly as `verifying` stays put while its suite runs, held by the lease `child()` takes. Moving the gate back inline reintroduces both faults.

**A Tier A PASS at `plan-validation` is a phase, not an ended attempt.** `plan-validation` is the deterministic gate followed by a Tier B agent, so the pass is recorded in `counters["gate_ok"]` -- dispatcher-owned, restored from the pre-spawn snapshot, consumed by the next `start()` -- and emits NO `stage_end`. Metrics view 1 is `escalated / stage_end` per stage, so a `stage_end` for the gate child would put two rows in the denominator for one run and halve every `plan-validation` escalation rate. A FAILING gate does emit one, exactly as the old inline path did.

**The gate child runs under the dispatcher's own environment, not `project_env()`.** It is the dispatcher's own code (`python -m pipeline gate`), and the project commands it runs re-apply `project_env()` inside `run_cmd()`. Stripping `PYTHONPATH` for this child breaks its import of `pipeline` wherever the package is reached that way, which is how `tests/test_daemon.py` starts the daemon.

**The gate child runs `python -P -m pipeline`, and `-P` is load-bearing.** `spawn_command()` runs its child with `cwd=wt`, and `-m` prepends the cwd to `sys.path`, so a bare `-m pipeline` in this repo imports the TICKET WORKTREE's copy of the package -- the code under review judging itself. A branch cut before this change merges has no `--findings` flag: argparse exits 2, `read_findings()` fails closed, and a good plan bounces to `planning`. `-P` drops the cwd entry and keeps `PYTHONPATH`, so the gate is judged by the dispatcher's own copy (`PYTHONPATH` if set, else the venv's editable install). Dropping `-P` reintroduces a self-judging gate that misfires on every branch older than this one.

**Raising the client's 5-second socket timeout was rejected as the fix.** It hides the toast and drains nothing: the pipe stays unread for the length of the suite, which is the half of this bug that can wedge an agent. `pipeline/cli/client.py` is untouched.

**`revalidating` rebases and gates in ONE child, and exit code 3 means the rebase conflicted.** The gate must judge the tree the rebase produced, and running it in the dispatcher after the rebase child exited is the blocking call this ticket removes. `pipeline gate` exits 0 or 1, so `git rebase <base> || exit 3` keeps DEC-029's repair (abort, reset onto base, back to `triage`) reachable and distinct from a gate failure.

**A missing or contradictory findings file is a FAILED gate.** `read_findings()` fails closed like `finish_suite()`: a child that exited 0 without writing the file did not run the gate, and reporting that as a pass would send an ungated plan to a human. The findings themselves are passed through byte-for-byte from `gate()`'s return value, because DEC-046 already replaced their fences with references to the thread entry the gate wrote.

## Rollback

Revert the commits on `ticket/061`. The change is confined to `pipeline/daemon/supervisor.py` and one optional flag in `pipeline/cli/main.py`; nothing in `pipeline/core/gate.py`, `pipeline/core/machine.py` or the ticket schema moves, so a revert restores the inline gate with no data migration. A ticket sitting at `plan-validation` with `counters["gate_ok"]: 1` when the revert lands is re-gated inline on the next tick: the reverted `start()` ignores the unknown counter, and `gate()` is idempotent because `_dedupe()` replaces the repeated output with a reference. A ticket whose gate child is in flight when the daemon restarts onto the reverted code loses that child and recovers through the ordinary lease-expiry path.

## Thread

### 2026-08-26 16:47:23Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-26 · triage · reproduced

Reproduced with a real `pipelined` process, not a mock: a `plan-validation`
ticket with `test_one = "sleep 3; echo test_broken; exit 1"`, then an `ls`
request from a `Client(timeout=1.0)` 1s after the daemon starts, while
`gate()` is inside the `sleep 3`. The request times out with `daemon: timed
out` instead of getting a reply, confirming the daemon serves nothing while
`gate()`'s synchronous `test_one` runs, exactly as described.

Test committed: `tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test`
(commit `15b46f3`). It asserts the fixed behaviour -- the request must not
raise -- so it fails today and should pass once the gate stops blocking the
select loop.

This is a design change (the ticket's own two "must not paper over" points),
not a small fix, so `result: ok`, not `chore`.

### 2026-08-26 16:56:57Z · triage · session · session=4d60ceb4-0f28-4ad9-b90f-8bc25829757b

`triage` ran as session `4d60ceb4-0f28-4ad9-b90f-8bc25829757b`
- replay: `claude --resume 4d60ceb4-0f28-4ad9-b90f-8bc25829757b`
- log: `.project/logs/TICKET-061-triage-4d60ceb4.log`

### 2026-08-26 16:56:57Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced with a real pipelined process; ls times out (daemon: timed out) while gate() runs a 3s test_one

### 2026-08-27 · planning · note

Plan written. The gate runs as a `spawn_command()` child -- the upgrade path
the `ponytail:` comment names -- and the ticket waits at its own stage on the
lease `child()` takes, exactly where `verifying` waits for its suite. No new
stage, no `transition()` row, nothing in `machine.FENCED`.

The ticket's two "must not paper over" points, answered:

1. Where the ticket waits: at `plan-validation` itself. That stage is two
   checks -- Tier A `gate()`, then a Tier B agent -- so a Tier A pass is a
   phase, recorded in `counters["gate_ok"]` and consumed by the next `start()`.
   A pass emits no `stage_end`: metrics view 1 is `escalated / stage_end` per
   stage, and a second row per run would halve every escalation rate for
   `plan-validation`. `revalidating` needs no phase -- its rebase and its gate
   run in one child, with exit code 3 reserved for a conflicting rebase.
2. The client timeout is untouched. `pipeline/cli/client.py` does not appear in
   `files_declared`. Raising it hides the toast and drains nothing.

Scope: one subsystem, the dispatcher loop. Nothing else was folded in.

Two things noticed and deliberately left alone, since they are outside this
stage's job: `_widen()` stays (still headroom for the git calls), and the
`ponytail:` comment in `serve()` about orphaned children from a SIGKILLed
daemon is a separate ticket.

### 2026-08-26 17:49:53Z · planning · session · session=c34c1664-17d5-4409-9cc2-3120d87319ad

`planning` ran as session `c34c1664-17d5-4409-9cc2-3120d87319ad`
- replay: `claude --resume c34c1664-17d5-4409-9cc2-3120d87319ad`
- log: `.project/logs/TICKET-061-planning-c34c1664.log`

### 2026-08-26 17:49:53Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: gate() runs as a spawn_command() child, the ticket waits at plan-validation on its lease, counters[gate_ok] carries the Tier A pass

### 2026-08-26 19:10:39Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test` fails as required
```
NULL, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, env=env, cwd=ROOT)
        try:
            for _ in range(100):        # wait on the socket, not on a sleep
                if sock.exists():
                    break
                time.sleep(0.05)
            assert sock.exists(), "daemon never came up"
    
            # give the loop time to claim the ticket and enter the gate's sleep
            time.sleep(1.0)
    
            c = Client(sock, timeout=1.0)
            try:
                c.request("ls", project=str(d))     # must not raise
            except PipelineError as e:
>               assert False, f"daemon did not answer while the gate ran: {e}"
E               AssertionError: daemon did not answer while the gate ran: daemon: timed out
E               assert False

tests/test_daemon.py:983: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 6.21s ===============================

```
- ok: `tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test` fails on base `main` too -- the bug is not already fixed upstream
```
ect=str(d))     # must not raise
            except PipelineError as e:
>               assert False, f"daemon did not answer while the gate ran: {e}"
E               AssertionError: daemon did not answer while the gate ran: daemon: timed out
E               assert False

tests/test_daemon.py:983: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 6.33s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-s7jwcklh/base
      Built pipeline @ file:///tmp/pipeline-base-s7jwcklh/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-27 · plan-validation · rejected

**Tier B: FAIL.** Two items fail; the other seven pass.

long: two findings, each carrying its own evidence.

1. **Step 20 and one acceptance criterion name a test that does not exist.**
   `tests/test_dispatch.py::test_the_gate_s_own_escalation_is_recorded` is not
   in that file. The test step 20 describes -- fixture `counters:
   {plan_validation_attempts: 1}`, then `escalation_rate(conn,
   "plan-validation") == 1.0` and `gate_failure_reasons(conn)` -- is
   `test_a_bound_escalation_emits_an_escalated_event`, at
   `tests/test_dispatch.py:454`. Rename it in step 20 and in the criterion.

2. **The gate child imports the worktree's copy of `pipeline`, not the
   dispatcher's.** `spawn_command()` runs its child with `cwd=wt`
   (`pipeline/daemon/supervisor.py:463`), and `python -m` prepends the cwd to
   `sys.path`. This project's worktree holds a `pipeline/` package, so
   `{sys.executable} -m pipeline` (step 7) resolves there. Digest gotcha 5
   rules out `PATH` only. A branch cut before this change merges, and gated
   after it merges, runs a `pipeline/cli/main.py` that has no `--findings`:
   argparse exits 2, `read_findings()` fails closed, and the plan bounces to
   `planning`. Fix: run the child with `-P`, or set `PYTHONSAFEPATH=1` in its
   env, and say which copy of the package judges the gate. `-P` keeps
   `PYTHONPATH`, so gotcha 3's `tests/test_daemon.py` path still imports. I
   could not run the check -- the guard refuses `python -c` in a read-only
   stage -- so this rests on `-m`'s documented path rule plus `cwd=wt` at
   line 463.

The seven that pass:

- **Root cause.** `gate()` runs the project's `test_one` synchronously inside
  the select loop (`pipeline/daemon/supervisor.py:712` and `:851`), so for its
  whole duration the loop answers no client request and `pump()` drains no
  child's pipe. The plan moves that call into a `spawn_command()` child. That
  is the cause, not the toast.
- **Decisions.** DEC-011, DEC-017, DEC-029, DEC-045 and DEC-046 carry no
  `superseded` footer, so all five are active. DEC-017 names this fix
  verbatim: "run the gate as a spawned child like `verifying`". The plan
  complies with each and supersedes none.
- **Scope.** Every step traces to a criterion or records this change. Step 17
  (`_gating_project()`) is setup for step 19; steps 26-28 document what steps
  12-24 do.
- **Falsifiable criteria.** `elapsed < 2` against a 5-second `test_one`,
  `counters["gate_ok"] == 1`, exactly one `stage_end`, zero `stage_end`, and
  `not rec["findings"].exists()` each fail on a wrong implementation. The
  criterion in finding 1 is the exception: it names no runnable test.
- **Research.** Every other step names its file, its function and its line.
- **Riskiest step.** Step 15, the suppressed `stage_end`. The plan states its
  fallback: step 12 pops `gate_ok`, so a lease expiry re-gates, and
  `## Rollback` says a reverted `start()` ignores the counter.
- **Regression surface.** I read every `supervisor.start()` call site under
  `tests/`. Two touch the moved code: `test_a_bound_escalation_...` (:454) and
  the four `_ticket_awaiting_approval()` re-gate tests. The plan covers both;
  every other call rewrites the stage first. `stage_end` is read by
  `metrics.escalation_rates` (`pipeline/cli/metrics.py:135`) and by the TUI's
  PTY detach (`pipeline/tui/app.py:364`, interactive records only), so
  suppressing it for a passing gate moves view 1 alone. Nothing reads
  `stage_start`.
- **Blast radius.** `class: bugfix`, 6 declared files: two source, two test,
  two doc. One subsystem. It matches.

Not a fail, for whoever implements this: `bail()`'s docstring
(`pipeline/daemon/supervisor.py:601-602`) says a failed Tier A gate "spawns
nothing either". Step 26 updates two stale comments; this is a third.

### 2026-08-26 19:16:43Z · plan-validation · session · session=5925bd16-5708-41bf-bd78-555684116119

`plan-validation` ran as session `5925bd16-5708-41bf-bd78-555684116119`
- replay: `claude --resume 5925bd16-5708-41bf-bd78-555684116119`
- log: `.project/logs/TICKET-061-plan-validation-5925bd16.log`

### 2026-08-26 19:16:43Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ plan rejected on 2 items: step 20 names a test that does not exist, and the gate child's `python -m` imports the worktree's copy of pipeline (cwd=wt)

### 2026-08-27 · planning · note

Re-planned after the rejection. The approach is unchanged -- the reviewer
passed all seven items that judge it -- so only the two rejected items and one
fixture moved.

1. Step 20 and its acceptance criterion now name
   `test_a_bound_escalation_emits_an_escalated_event`
   (`tests/test_dispatch.py:454`), the test the reviewer identified. Step 20
   also drives the child: `did, rec = supervisor.start(...)`, then
   `rec["proc"].wait()`, then `supervisor.finish(d, rec, s.emitter(str(d)))`.
   The old step called `start()` alone, which no longer escalates by itself.
2. Step 7's command is now `{sys.executable} -P -m pipeline ...`. Verified on
   this repo's CPython 3.13.11: `python -P -c ...` reports `sys.flags.safe_path`
   True and no cwd entry in `sys.path`. Digest gotcha 6 answers "which copy
   judges the gate": the dispatcher's -- `PYTHONPATH` if set, else the venv's
   `_editable_impl_pipeline.pth`, whose one line reads
   `/home/chezzijr/proj/agent-pipeline`. Never the ticket's worktree.

One fixture nobody flagged: step 1 asserted `returncode == 1` on a plain
`helpers.project()`, but `pipeline gate TICKET-001` there exits 0 `gate: PASS`.
Ran both today; the step now uses `project(test_passes=True)`, which exits 1
with one finding and no fence. Step 26 also takes `bail()`'s stale docstring,
the third stale comment the reviewer named as not-a-fail.

One accident, disclosed: an editing script of mine deleted `## Reproduction`,
`## Digest`, `## Decisions checked` and `## Plan` from this file, and I wrote
all four back from the stage view before finishing. Verified after the
rewrite: `pipeline plan TICKET-061` prints 29 numbered steps, `grep '^## '`
lists the nine sections in their original order, and the frontmatter is
byte-identical (`plan_steps: 29`, `plan_files: 6`). No other section was
touched. If any prose here reads as changed beyond the four items above, that
is the cause.

### 2026-08-26 19:24:26Z · planning · session · session=06bb0534-b22f-4a56-938d-a996fc85c95b

`planning` ran as session `06bb0534-b22f-4a56-938d-a996fc85c95b`
- replay: `claude --resume 06bb0534-b22f-4a56-938d-a996fc85c95b`
- log: `.project/logs/TICKET-061-planning-06bb0534.log`

### 2026-08-26 19:24:26Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-planned: step 20 renamed to test_a_bound_escalation_emits_an_escalated_event and drives the child, step 7 adds -P so the dispatcher's copy judges the gate, step 1's fixture is project(test_passes=True)

### 2026-08-26 19:24:54Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-26 19:10:39Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test` fails on base `main` too -- the bug is not already fixed upstream
```
ect=str(d))     # must not raise
            except PipelineError as e:
>               assert False, f"daemon did not answer while the gate ran: {e}"
E               AssertionError: daemon did not answer while the gate ran: daemon: timed out
E               assert False

tests/test_daemon.py:983: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 6.33s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-_6du0ono/base
      Built pipeline @ file:///tmp/pipeline-base-_6du0ono/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-27 · plan-validation · accepted

**Tier B: PASS.** All nine items pass.

long: nine items, each with the evidence I read.

- **Root cause.** `gate()` runs the project's `test_one` inside the select
  loop (`pipeline/daemon/supervisor.py:711` and the second call in
  `finish_regate()`), so for its whole duration the loop answers no client
  and `pump()` drains no pipe. The plan moves that call into a
  `spawn_command()` child. It fixes the cause, not the toast.
- **Both rejected items are fixed.** Step 20 names
  `test_a_bound_escalation_emits_an_escalated_event`, which is at
  `tests/test_dispatch.py:454`, and drives the child through `wait()` and
  `finish()`. Step 7 runs `-P`, which drops the `cwd=wt` entry `-m` would
  prepend.
- **Decisions.** DEC-017, DEC-046, DEC-011, DEC-029 and DEC-045 constrain this
  plan and the plan complies. The `ponytail:` comment at `:709` calls the
  upgrade "a `DISPATCHER_STAGES` change"; the plan supersedes that with
  justification, and the code agrees: `DISPATCHER_STAGES` holds only stages
  with no prompt file (`tests/test_stages.py:74-79`), and `plan-validation`
  has `pipeline/stages/plan-validation.md`. It cannot go in the set.
- **Scope.** Every step traces to a criterion except 26, 27 and 28, which
  update three stale comments, known-issue 14 and `CLAUDE.md`. All three
  describe the behaviour this ticket changes and alter no code path.
  In scope, not creep.
- **Falsifiable.** `elapsed < 2` against `test_one = "sleep 5"` fails today by
  3 seconds. `escalation_rate(conn, "plan-validation") == 1.0` fails on one
  spurious `stage_end`. `git diff --stat` showing `pipeline/core/gate.py`
  unchanged fails on any edit there.
- **No research left.** Every step names a file and a function, and the two
  line numbers I spot-checked are right: `spawn_command()`'s `cwd=wt` is
  `pipeline/daemon/supervisor.py:463`, `bail()`'s stale sentence is at
  `:601-602`.
- **Riskiest step: 12**, replacing the inline gate in `start()`, because it
  changes where the ticket waits. `## Rollback` states the fallback and covers
  its two edge states: a ticket holding `counters["gate_ok"]: 1` when the
  revert lands is re-gated inline, and an in-flight gate child recovers
  through lease expiry.
- **Regression surface.** Metrics views 1 and 4 (step 20 plus its criterion),
  the four `revalidating` tests (step 25), `gate()`'s verdict
  (`tests/test_gate.py` plus the `git diff --stat` criterion), and the
  `suite` / `merge` / `unwind` children, which keep `project_env()` because
  step 8 defaults `env` to it. Checked one thing the plan does not mention: a
  passing gate child now emits a `stage_start` where the inline gate emitted
  none, and no metrics view reads that kind -- grep for `stage_start` in
  `pipeline/cli/metrics.py` returns nothing. It reaches only the TUI feed
  (`pipeline/tui/app.py:47`).
- **Blast radius.** Six files for a `bugfix`: two source files
  (`pipeline/daemon/supervisor.py`, one flag in `pipeline/cli/main.py`), two
  test files, two documents. Proportionate. Nothing in `machine.FENCED` is
  touched, so the ticket does not park at `awaiting-merge`.

One check I could not run: `pipeline gate` on `project(test_passes=True)`, so
step 1's "exactly one finding" rests on planning's run. I did confirm the
finding it names carries no fence (`pipeline/core/gate.py:219`) and that
`gate()` maps every non-blank fence body to a reference before returning
(`:402-403`), so the no-backticks assertion holds.

### 2026-08-26 19:28:49Z · plan-validation · session · session=f77a8ee0-411c-43cb-9090-ee068632e024

`plan-validation` ran as session `f77a8ee0-411c-43cb-9090-ee068632e024`
- replay: `claude --resume f77a8ee0-411c-43cb-9090-ee068632e024`
- log: `.project/logs/TICKET-061-plan-validation-f77a8ee0.log`

### 2026-08-26 19:28:49Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan accepted: all nine items pass; both rejected items fixed (step 20 names test_a_bound_escalation_emits_an_escalated_event, step 7 runs -P), DISPATCHER_STAGES stays out because plan-validation has a prompt file

### 2026-08-26 19:29:20Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-26 19:34:23Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test` fails as required
```
ULL, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, env=env, cwd=ROOT)
        try:
            for _ in range(100):        # wait on the socket, not on a sleep
                if sock.exists():
                    break
                time.sleep(0.05)
            assert sock.exists(), "daemon never came up"
    
            # give the loop time to claim the ticket and enter the gate's sleep
            time.sleep(1.0)
    
            c = Client(sock, timeout=1.0)
            try:
                c.request("ls", project=str(d))     # must not raise
            except PipelineError as e:
>               assert False, f"daemon did not answer while the gate ran: {e}"
E               AssertionError: daemon did not answer while the gate ran: daemon: timed out
E               assert False

tests/test_daemon.py:1020: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 6.27s ===============================

```
- ok: `tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test` fails on base `main` too -- the bug is not already fixed upstream
```
ct=str(d))     # must not raise
            except PipelineError as e:
>               assert False, f"daemon did not answer while the gate ran: {e}"
E               AssertionError: daemon did not answer while the gate ran: daemon: timed out
E               assert False

tests/test_daemon.py:1020: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_daemon_answers_a_client_while_the_gate_runs_the_project_s_test
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 6.34s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-5_fse2qs/base
      Built pipeline @ file:///tmp/pipeline-base-5_fse2qs/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-26 19:34:23Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-27 · implementing · todo

**implementing: 29-step plan, todo list**

- [x] 1-4: `--findings` flag on `pipeline gate`, test in tests/test_cli.py
- [x] 5-16: gate runs as spawn_command child in supervisor.py, test in tests/test_dispatch.py, reproduction passes
- [x] 17-21: _gating_project() helper, failing-gate test, passing-gate test, update escalation test
- [x] 22-25: revalidating regate_cmd, REBASE_FAILED=3, finish_regate uses finish_gate
- [x] 26-29: stale comments, known-issues.md, CLAUDE.md gotcha, full suite + commit

### 2026-08-27 · implementing · done

**All 29 plan steps done, full suite green.**

- `pipeline gate --findings PATH` writes `{ok, findings}` JSON (`pipeline/cli/main.py`).
- The Tier A gate runs as a `spawn_command()` child (`gate_cmd()`, `-P -m pipeline`,
  dispatcher's own env). `finish_gate()` reads the findings file back
  (`read_findings()`, fails closed) and routes the verdict; a PASS at
  `plan-validation` sets `counters["gate_ok"]` and returns `GATE_PASS`, which
  `finish()` uses to skip `stage_end`. A FAIL still emits one `gate` and one
  `stage_end`, unchanged from the inline path.
- `revalidating` chains `git rebase base || exit 3` with `gate_cmd()` in one child
  (`regate_cmd()`); `REBASE_FAILED = 3` marks a conflict, any other exit goes
  through `finish_gate()`.
- `tests/test_dispatch.py::test_a_bound_escalation_emits_an_escalated_event` now
  drives the gate child through `wait()`/`finish()` per the approved plan.
- `pipeline/core/gate.py` is untouched: `git diff --stat main...HEAD -- pipeline/core/gate.py` is empty.
- `uv run --group dev pytest -q`: 327 passed. `./pipeline/hooks/test_dangerous_commands.py`: all passed.
- Six commits on `ticket/061`: 31220de, 38c00df, 0bf5cbf, 329d442, 59652b5 (plus the
  pre-existing reproduction commit 67c3872).

### 2026-08-26 19:42:07Z · implementing · session · session=9721fe07-c1ca-430b-a278-6fa788e00d0e

`implementing` ran as session `9721fe07-c1ca-430b-a278-6fa788e00d0e`
- replay: `claude --resume 9721fe07-c1ca-430b-a278-6fa788e00d0e`
- log: `.project/logs/TICKET-061-implementing-9721fe07.log`

### 2026-08-26 19:42:07Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Tier A gate now runs as a spawn_command() child; all 29 plan steps done, full suite green (327 tests), guard passes.

### 2026-08-27 · review · findings

**review: pass. No blocking finding on the delta 67c3872..59652b5.**

`uv run --group dev pytest -q` -> `327 passed in 15.54s`. Every named
acceptance test passes: the reproduction, the CLI findings test, the three new
dispatch tests, the escalation test, the four `revalidating` tests.
`git diff --stat main...HEAD -- pipeline/core/gate.py` is empty.

Two findings I raised, then refuted:
1. "The findings JSON in `.project/logs/` trips another ticket's read-only
   tamper check." Refuted: `dirty_snapshot()` runs `git status --porcelain --
   . ':(exclude).project'` (`pipeline/core/worktree.py:156`).
2. "`read_findings()` fences a log tail into a thread bullet, against DEC-046."
   Refuted: `finish_suite()` already does (`pipeline/daemon/supervisor.py:840-842`).

Non-blocking:
1. minor: `gate` is an unused import now (`pipeline/daemon/supervisor.py:21`).
2. minor: `if rec is not None` after `child()` is dead in both new branches.
3. minor: nothing sweeps an orphaned `TICKET-*-gate-*.json` when the daemon
   dies between the child's write and `finish_gate()`.
4. minor: the `revalidating` rebase runs under the dispatcher's env now, not
   `project_env()`, since rebase and gate share one child.

The guard refused `./pipeline/hooks/test_dangerous_commands.py`: "`test_dangerous_commands.py`
is not on the read-only allowlist". I ran its 109 cases through pytest instead:
`-k allow_and_block_tables` -> `1 passed, 326 deselected`.

### 2026-08-26 19:48:41Z · review · session · session=780b8584-0656-437c-b19b-a3c8ee84a2d3

`review` ran as session `780b8584-0656-437c-b19b-a3c8ee84a2d3`
- replay: `claude --resume 780b8584-0656-437c-b19b-a3c8ee84a2d3`
- log: `.project/logs/TICKET-061-review-780b8584.log`

### 2026-08-26 19:48:41Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review pass: 327 passed, every acceptance test green, gate.py unchanged; two findings refuted, four minor items logged

### 2026-08-26 19:48:58Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-26 19:48:59Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/061


Current branch ticket/061 is up to date.
Already up to date.
Updating 9f4f55b..59652b5
Fast-forward
 .project/known-issues.md      |  12 ++--
 CLAUDE.md                     |   6 ++
 pipeline/cli/main.py          |   7 +-
 pipeline/daemon/supervisor.py | 163 +++++++++++++++++++++++++++++++-----------
 tests/test_cli.py             |  16 ++++-
 tests/test_daemon.py          |  58 ++++++++++++++-
 tests/test_dispatch.py        | 116 ++++++++++++++++++++++++++++--
 7 files changed, 320 insertions(+), 58 deletions(-)

```

### 2026-08-26 19:48:59Z · merging · decision

decision recorded as `DEC-061`
