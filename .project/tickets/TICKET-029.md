---
id: TICKET-029
stage: done
class: bugfix
branch: ticket/029
test_file: tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back
files_declared:
- README.md
- pipeline/cli/metrics.py
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
- tests/test_machine.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
  rebase_conflicts: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 0dfbb270-b248-427f-8d17-d520342e3eeb
  log: .project/logs/TICKET-029-review-0dfbb270.log
approved_by: chezzijr
approved_at: '2026-08-21T09:26:52.878394+00:00'
---

## Summary

a rebase conflict at `revalidating` escalates with no way back

**Reviewed (2026-08-21): PASS, no blocking finding.** The review read
`git diff main...HEAD` -- six files, `+93 -24`, commit `ea0b590` -- and ran
every test the acceptance criteria name: 6 passed. Full suite: `196 passed in
8.55s`. Confirmed: plan-validation's rc note is implemented, the bound is 2 by
`MAX_ATTEMPTS` fallback, `advance()` passes `agent=False`, `start()` and
`finish_regate()` name the same base, the new test fails if the
`git reset --hard` is dropped, and no other counter enumerator needed
`rebase_conflicts`. Four non-blocking notes are in the thread: two dead
guards (`if rec is not None`, `rec.get("base") or "main"`), one shared exit
code between the abort and its `git log`, and the guard script, which the
review stage's own allowlist blocks -- it was not run, and the delta touches
no file under `pipeline/hooks/`. This commit changes `transition()`, so
`CLAUDE.md` requires human review before merge.

**Implemented (2026-08-21).** All 13 plan steps done, commit `ea0b590`.
Steps 1-4 (the `("revalidating", "conflict")` machine row and its test) were
already committed to the worktree, uncommitted, when this stage started; they
were verified against the plan and kept rather than redone. Steps 5-13:
`pipeline/daemon/supervisor.py` imports `base_ref` and `run_cmd`; `start()`'s
`revalidating` branch computes `base = base_ref(cfg)` once and stores it on
the returned record; `finish_regate()` on a non-zero rebase exit runs
`git rebase --abort`, then `git reset --hard <base>`, escalates if either
command fails, otherwise calls `advance(..., "conflict", ..., agent=False)`.
`tests/test_dispatch.py::test_a_rebase_conflict_on_approval_escalates_and_keeps_the_worktree`
is rewritten to
`test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage`, asserting
`t.stage == "triage"`, `rebase_conflicts == 1`, no unmerged path, `f.py`
reads `base side`, and `ticket commit` is gone from the log. README and the
`metrics.py` view-1 comment updated as planned. Full suite: 196 passed. Guard
script: all passed.

**Planned (2026-08-21).** The plan routes the conflict through `transition()`
instead of `escalate()`. `finish_regate()` runs `git rebase --abort`, then
`git reset --hard <base>` in the ticket's worktree, then calls
`advance(..., "conflict", ..., agent=False)`. A new row
`("revalidating", "conflict")` charges `rebase_conflicts` and targets `triage`,
which rewrites its failing test on current base; the second conflict escalates
at the default bound of 2. Six files: `pipeline/core/machine.py`,
`pipeline/daemon/supervisor.py`, `tests/test_dispatch.py`,
`tests/test_machine.py`, `pipeline/cli/metrics.py`, `README.md`.
`tests/test_dispatch.py::test_a_rebase_conflict_on_approval_escalates_and_keeps_the_worktree`
is rewritten, as triage required. The ticket's other suggestion -- triage
declaring its test file so `files_conflict` orders earlier -- was checked and
rejected: `files_conflict` reads `inflight` only, and a ticket at
`awaiting-approval` holds no child.

**Plan validated (2026-08-21): PASS.** All eight items scored in the thread.
Every cited line, function and decision was opened and matches: DEC-011:10
("additive and fine"), DEC-017:37 (`base_ref(cfg)` is the single default) and
DEC-022:28 (`agent=False`) constrain the plan and it complies. Two notes for
implementing, neither blocking:

1. Step 7 must assign the `git reset --hard <base>` exit code back into the
   `rc` that step 8 tests. Otherwise a failed reset advances a ticket whose
   branch was never recut.
2. Step 12 edits a comment in `pipeline/cli/metrics.py` that no criterion
   covers. It stays as documentation of the new counter.

`revalidating` rebases the ticket branch onto base and re-runs the Tier A gate.
When the rebase conflicts it escalates, and the ticket stops there:

    $ git rebase main
    CONFLICT (content): Merge conflict in tests/test_gate.py
    error: could not apply 2e908e9... test: gate accepts a one-word digest and
           an unresolvable decision id

Both TICKET-018 and TICKET-021 hit this on 2026-08-21 within four minutes of
each other. In both cases the conflicting commit was the **triage test**, and in
both cases a sibling ticket had landed in the same test file while the first
waited at `awaiting-approval`.

Recovery took a human: abort the rebase, delete the worktree, delete the branch,
and `pipeline resume <id> --stage triage`. Nothing in the pipeline can do that,
so a conflict costs a full re-triage plus the planning that follows -- about $5
of work discarded, twice.

The deeper cause is ordering, not merging. `files_conflict` serialises tickets by
`files_declared`, but `files_declared` is written at **planning**. Triage commits
its test before any ticket has declared anything, so two tickets can both write
`tests/test_gate.py` before the ordering exists.

Expected: two tickets whose triage tests land in the same file do not both reach
`awaiting-approval` with branches that cannot both rebase; or a conflict at
`revalidating` returns the ticket to a stage that can fix it, rather than to a
human with a shell.

Do not "fix" this by dropping the rebase. `revalidating` exists because a plan's
facts go stale while a human is at the gate, and TICKET-017 landed changes that
made TICKET-018's plan wrong -- the rebase is what noticed.

Worth checking while planning this: `triage` could report the file it committed
into, which would give `files_conflict` something to order by one stage earlier.

**Triage found (2026-08-21):** the escalation is written by `finish_regate()`
at `pipeline/daemon/supervisor.py:619`, which calls `escalate()` directly on a
non-zero rebase exit. `transition()` never sees the conflict, so no counter is
charged and no row routes the ticket anywhere. Two constraints for planning:
`tests/test_dispatch.py::test_a_rebase_conflict_on_approval_escalates_and_keeps_the_worktree`
asserts today's behaviour and must be rewritten; and the worktree is left
mid-rebase, so any route back needs `git rebase --abort` first.
## Reproduction

`tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back`

    uv run --group dev pytest -q "tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back"

Fails:

    >       assert t.stage not in M.TERMINAL, \
    E       AssertionError: a rebase conflict parked the ticket at escalated with no way back
    E       assert 'escalated' not in {'done', 'escalated', 'rejected'}

expect: a rebase conflict parked the ticket at escalated with no way back

The test parks a ticket at `awaiting-approval`, writes `f.py` on both the ticket
branch and base, approves, and runs the `revalidating` child. The rebase
conflicts:

    CONFLICT (content): Merge conflict in f.py
    error: could not apply 220b78c... ticket commit

## Digest

Files touched: `pipeline/core/machine.py`, `pipeline/daemon/supervisor.py`,
`tests/test_dispatch.py`, `tests/test_machine.py`, `pipeline/cli/metrics.py`,
`README.md`.

Key functions: `transition()` (`pipeline/core/machine.py:24`), `finish_regate()`
(`pipeline/daemon/supervisor.py:613`), `start()`'s `revalidating` branch
(`pipeline/daemon/supervisor.py:539-543`), `advance()`
(`pipeline/daemon/supervisor.py:91`), `escalate()`
(`pipeline/daemon/supervisor.py:63`).

Entry points: the dispatcher reaps the `regate` child, `_finish()` routes
`kind == "regate"` to `finish_regate()`, which today calls `escalate()` on a
non-zero rebase exit. `transition()` never sees the conflict.

The repair, measured in a scratch repo before planning: `git rebase --abort`
restores the branch at the ticket commit, then `git reset --hard main` moves the
branch to base and leaves the worktree clean and still on the branch.

    $ git rebase --abort; git log --oneline -1
    642964b ticket commit
    $ git reset --hard main; git log --oneline -1; git status --porcelain
    ffddd3d base moved

Gotchas:

1. At `revalidating` the branch carries only triage's test commit. `approve` sets `revalidating`, and `transition("revalidating","ok")` returns `implementing`, so no implementation commit exists yet. The recut discards exactly one commit, and `triage` rewrites it.
2. `ensure_worktree` (`pipeline/core/worktree.py:41`) reuses an existing worktree directory. Resetting the branch in place needs no worktree deletion and no branch deletion.
3. The prevention the ticket suggests -- triage declaring its test file -- does not fix this case. `files_conflict` is called on `inflight` alone (`pipeline/daemon/supervisor.py:497`), and `inflight` holds children running in the current tick. A ticket parked at `awaiting-approval` has no child, so it orders nothing. TICKET-018 and TICKET-021 collided during exactly that wait.
4. `tests/test_stages.py:121-127` reads `README.md` and asserts the 300 characters before the word `stale_regate` contain `` `planning` ``. Edit the sentence after it, never before it.
5. `rebase_conflicts` stays out of `BOUNDS`, like `stale_regate`. `BOUNDS.get(klass, {}).get(key, MAX_ATTEMPTS)` then gives it a bound of 2.
6. `run_cmd` and `base_ref` live in `pipeline/core/worktree.py`. `pipeline/daemon/supervisor.py` does not import either one yet.

## Decisions checked

Grep terms over `.project/decisions/`: `rebase`, `revalidat`, `regate`,
`worktree`, `escalat`, `triage`. No record on disk carries a `superseded-by:`
line.

- DEC-011 -- the event vocabulary is frozen, but "adding a `kind` or a field inside `data` is additive and fine". A new `result` value inside the existing `transition` event's `data` is additive. View 1 counts `kind='escalated'`, so the new counter routes through a plain `transition` and does not inflate it, exactly like `stale_regate`.
- DEC-017 -- `base_ref(cfg)` is the single default for base. This plan uses it for the rebase and for the recut, so both name the same branch.
- DEC-022 -- a new dispatcher-owned `advance()` call site must pass `agent=False`. Step 8 does.
- DEC-018, DEC-023, DEC-024 read; nothing in them constrains this change. DEC-018's import rule binds `tests/test_gate.py`, which this plan does not touch.

## Plan

1. In `tests/test_machine.py`, add `test_a_rebase_conflict_returns_to_triage_and_is_bounded`: assert `t("revalidating", "conflict")[0] == "triage"`, that its counters give `c["rebase_conflicts"] == 1`, that `"stale_regate" not in c`, and that `t("revalidating", "conflict", c)[0] == "escalated"`.
2. Run `uv run --group dev pytest -q tests/test_machine.py -k rebase_conflict` and see it fail on the unknown-pair fallback: `assert 'escalated' == 'triage'`.
3. In `pipeline/core/machine.py`, add `case ("revalidating", "conflict"): return charge("rebase_conflicts", "triage")` directly below the `("revalidating", "fail")` row, with a comment saying the branch cannot be rebased, so its commits are discarded and `triage` rewrites its test on current base; `planning` is not the target because re-planning does not remove a conflicting commit.
4. Run `uv run --group dev pytest -q tests/test_machine.py` and see every test pass.
5. In `pipeline/daemon/supervisor.py`, extend the worktree import to `from pipeline.core.worktree import (base_ref, drop_worktree, ensure_worktree, project_env, run_cmd, tree_snapshot, worktree)`.
6. In `pipeline/daemon/supervisor.py`, change `start()`'s `revalidating` branch to compute `base = base_ref(cfg)` once, pass `shlex.quote(base)` to `git rebase`, set `rec["base"] = base` on the returned record, and return it, so the recut names the branch the rebase actually used.
7. In `pipeline/daemon/supervisor.py`, open the recut in `finish_regate()`'s `if code != 0:` body: `base = shlex.quote(rec.get("base") or "main")`, then `rc, repair = run_cmd(f"git rebase --abort && git log --oneline {base}..HEAD", rec["wt"])`, then when `rc == 0` run `git reset --hard {base}` in the same worktree and append its output to `repair`.
8. In `pipeline/daemon/supervisor.py`, finish that body: on a non-zero `rc` call `escalate(t, ...)` with a reason naming the failed recut and quoting `repair`, and return `"escalated"`; otherwise call `advance(project, t, "conflict", <note quoting log_tail(rec) and repair>, emit, agent=False)` and return `"conflict"`.
9. In `tests/test_dispatch.py`, rewrite `test_a_rebase_conflict_on_approval_escalates_and_keeps_the_worktree` as `test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage`, keeping its fixture and asserting `t.stage == "triage"`, `t.counters["rebase_conflicts"] == 1`, `t.counters.get("stale_regate", 0) == 0`, `not t.lease_active()`, `wt.is_dir()`, an empty `sh(f"git -C {wt} diff --name-only --diff-filter=U").stdout`, `(wt / "f.py").read_text() == "base side\n"`, and a `sh(f"git -C {wt} log --oneline").stdout` that contains `base moved` and not `ticket commit`.
10. Run `uv run --group dev pytest -q tests/test_dispatch.py -k rebase` and see the rebase tests in `tests/test_dispatch.py` pass.
11. In `README.md`, replace the sentence `A rebase conflict escalates and keeps the worktree, exactly like a merge conflict.` with two sentences: a rebase conflict aborts the rebase, recuts the branch from base against its own counter (`rebase_conflicts`), and hands the ticket back to `triage`, which rewrites its test on current base; nothing is auto-resolved, and a second conflict escalates. Leave every character before the word `stale_regate` untouched.
12. In `pipeline/cli/metrics.py`, extend the view 1 comment at line 117 so it names `rebase_conflicts` beside `stale_regate` as a counter that routes back through a plain `transition` and does not inflate the escalation rate.
13. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, then commit with `git add pipeline/core/machine.py pipeline/daemon/supervisor.py pipeline/cli/metrics.py tests/test_machine.py tests/test_dispatch.py README.md && git commit -m "fix: a rebase conflict at revalidating recuts the branch and returns to triage"`.

## Acceptance criteria

1. A rebase conflict leaves the ticket at `triage`, outside `TERMINAL` -- `tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back` and `tests/test_dispatch.py::test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage`.
2. The worktree survives with no unmerged path, and the branch sits on base: `git diff --name-only --diff-filter=U` is empty, `f.py` reads `base side`, and `ticket commit` is gone from the log -- `tests/test_dispatch.py::test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage`.
3. The conflict charges `rebase_conflicts` once and never charges `stale_regate` -- `tests/test_dispatch.py::test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage`.
4. A second conflict escalates rather than looping -- `tests/test_machine.py::test_a_rebase_conflict_returns_to_triage_and_is_bounded`.
5. A clean rebase still reaches `implementing`, and a stale re-gate still bounces to `planning` charging `stale_regate` -- `tests/test_dispatch.py::test_a_still_good_plan_is_implemented_after_the_rebase` and `tests/test_dispatch.py::test_a_stale_plan_is_re_gated_on_approval`.
6. The README still documents the stale re-gate target -- `tests/test_stages.py::test_the_docs_name_the_dependencies_and_the_targets_the_code_has`.

## Decisions

**A rebase conflict at `revalidating` is repaired by discarding the branch's
commits, not by resolving them.** `git rebase --abort` followed by
`git reset --hard <base>` puts the branch back on current base, and the ticket
goes to `triage`, which rewrites its failing test against the tree that now
exists. Nothing merges the conflicting hunks. The rule that a conflict is never
auto-resolved holds, because no conflicting content survives.

**The recut is safe only because `revalidating` runs before `implementing`.**
`approve` sets `revalidating`, and `transition("revalidating","ok")` returns
`implementing`, so the branch carries triage's test commit and nothing else. A
future change that routes a stage holding implementation commits through
`finish_regate()` would discard real work. Gate such a change on the branch
carrying no commit but triage's, or give it a different repair.

**`planning` is the wrong target and `triage` is the right one.** Re-planning
does not remove a conflicting commit, so the next `revalidating` conflicts
identically and burns the counter -- the same argument the `stale_regate` row
already makes about re-validating a stale plan. `triage` writes and commits the
test, so it is the only stage that can rebuild the branch.

**Declaring triage's test file into `files_declared` would not have prevented
TICKET-018 and TICKET-021.** `files_conflict` is consulted against `inflight`
alone (`pipeline/daemon/supervisor.py:497`), and `inflight` holds children
running in the current tick. Both collisions happened while one ticket sat at
`awaiting-approval` holding no child. Ordering across a human gate would need
`files_conflict` to read every non-terminal ticket, which serialises tickets for
as long as a human takes to approve. That is a different change, and this plan
does not make it.

**`rec["base"]` carries the base from the spawn to the reap.** `start()` reads
`base_ref(cfg)` when it builds the rebase command, and `finish_regate()` reuses
that value rather than re-reading the config. A config edited mid-run therefore
cannot make the recut target a different branch from the one the rebase used.

## Rollback

Revert the single commit from step 13. Behaviour returns to
`escalate()`-on-conflict with the half-rebased worktree left in place, and
`tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back`
fails again exactly as it does today. No data migration and no state to unwind:
the only persisted trace is a `rebase_conflicts` counter on tickets that took
the path, and `transition()` ignores an unknown counter key.

## Thread

### 2026-08-21 09:06:59Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 · triage · reproduced

Reproduced. Committed `1eaa575`.

The escalation is written by `finish_regate()`
(`pipeline/daemon/supervisor.py:619`):

    if code != 0:
        escalate(t, f"rebase onto base conflicted (exit {code})\n```\n"

`transition()` never sees the conflict, so no counter is charged and no row
routes it back. `escalated` is terminal and not in `CLEANUP_STAGES`, so the
half-rebased worktree stays.

Two facts for planning, not fixed here:

1. `tests/test_dispatch.py::test_a_rebase_conflict_on_approval_escalates_and_keeps_the_worktree`
   asserts the current behaviour (`t.stage == "escalated"`). Any fix must
   rewrite it; the two tests contradict each other on purpose.
2. The worktree is left mid-rebase. A route back to a working stage needs
   `git rebase --abort` first, or the next stage starts on a conflicted index.

### 2026-08-21 09:13:16Z · triage · session · session=98bb358b-5fe8-4e1f-ae82-2347ad09cb10

`triage` ran as session `98bb358b-5fe8-4e1f-ae82-2347ad09cb10`
- replay: `claude --resume 98bb358b-5fe8-4e1f-ae82-2347ad09cb10`
- log: `.project/logs/TICKET-029-triage-98bb358b.log`

### 2026-08-21 09:13:16Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

✓ reproduced: a rebase conflict at revalidating escalates terminally; failing test committed 1eaa575

### 2026-08-21 · planning · note

Plan written. The conflict is repaired, not resolved: `git rebase --abort`,
then `git reset --hard <base>`, then a new `("revalidating", "conflict")` row
charging `rebase_conflicts` and targeting `triage`.

Verified in a scratch repo before planning, not assumed:

    $ git rebase --abort; git log --oneline -1
    642964b ticket commit
    $ git reset --hard main; git log --oneline -1; git status --porcelain
    ffddd3d base moved

Two findings outside this stage's job, recorded rather than acted on:

1. The ticket's suggested prevention does not work. `files_conflict` is consulted against `inflight` alone (`pipeline/daemon/supervisor.py:497`), which holds only children running in the current tick. Both reported collisions happened while one ticket sat at `awaiting-approval` holding no child, so declaring triage's test file earlier orders nothing. Ordering across a human gate needs `files_conflict` to read every non-terminal ticket. That is a separate ticket.
2. `start()`'s `revalidating` branch reads `cfg.get('base', 'main')` directly (`pipeline/daemon/supervisor.py:542`) while DEC-017 names `base_ref(cfg)` as the single default. Step 6 replaces that one call site because the recut needs the same value; the other direct reads elsewhere are untouched.

### 2026-08-21 09:20:36Z · planning · session · session=ea130301-9949-4b48-88c3-c1daf24ebdc9

`planning` ran as session `ea130301-9949-4b48-88c3-c1daf24ebdc9`
- replay: `claude --resume ea130301-9949-4b48-88c3-c1daf24ebdc9`
- log: `.project/logs/TICKET-029-planning-ea130301.log`

### 2026-08-21 09:20:36Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

✓ plan written: a rebase conflict aborts, recuts the branch from base, and routes revalidating -> triage via a new transition row bounded by rebase_conflicts

### 2026-08-21 09:21:03Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back` fails as required
```
/test_dispatch.py:612: AssertionError
----------------------------- Captured stdout call -----------------------------
TICKET-001: -> revalidating
  start TICKET-001: revalidating (script) pid 1436647 -> TICKET-001-revalidating-378858a0.log
  TICKET-001: -> escalated (rebase onto base conflicted (exit 1)
```
$ git rebase main

Rebasing (1/1)
Auto-merging f.py
CONFLICT (content): Merge conflict in f.py
error: could not apply 33ef3ff... ticket commit
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply 33ef3ff... # ticket commit

```)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back` fails on base `main` too -- the bug is not already fixed upstream
```
icted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply 9500dac... # ticket commit

```)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.19s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-x_niozpo/base
      Built pipeline @ file:///tmp/pipeline-base-x_niozpo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-21 · plan-validation · validation

**PASS.** Eight items scored below. Every file, line number, function and
decision the plan cites was opened and matches.

1. **Root cause.** `finish_regate()` calls `escalate()` on a non-zero rebase
   exit (`pipeline/daemon/supervisor.py:619-624`), so `transition()` never sees
   the conflict. No counter is charged, no row routes the ticket, and
   `escalated` is terminal. The plan fixes that: the conflict becomes a
   `result` that reaches `transition()`, and the worktree is repaired first.
   It does not only make the test pass -- the rewritten test asserts the branch
   log lost `ticket commit` and `f.py` reads `base side`, which a stage change
   alone fails.
2. **Decision conflict.** Three cited decisions constrain this plan and the
   plan complies with each. DEC-011:10 -- "Adding a `kind` or a field inside
   `data` is additive and fine"; a new `result` value inside `transition` is
   additive. DEC-017:37 -- "**`base_ref(cfg)` is the single default.**"; step 6
   replaces the direct `cfg.get('base', 'main')` read at
   `pipeline/daemon/supervisor.py:542`. DEC-022:28 -- a dispatcher-owned
   `advance()` call site "must pass `agent=False`"; step 8 does. No record in
   `.project/decisions/` carries a `superseded-by:` line. DEC-025 exists and
   was not cited; it covers `--strict-mcp-config` in
   `pipeline/harnesses/claude-code.toml` and does not touch this change.
3. **Scope discipline.** Steps 1-11 and 13 each trace to a criterion. Step 12
   (`pipeline/cli/metrics.py:117`) does not: it edits a comment and no test can
   fail on it. It is one comment beside `stale_regate`, caused directly by the
   new counter, so it passes as documentation rather than scope creep.
4. **Falsifiable criteria.** Criterion 2 names three observable facts --
   `git diff --name-only --diff-filter=U` empty, `f.py` reads `base side`,
   `ticket commit` gone from the log. An implementation that aborted the rebase
   but skipped `git reset --hard` fails it. Criterion 4 fails if
   `rebase_conflicts` is put in `BOUNDS` with a bound above 2 or the row loops.
   Nothing here is vacuous.
5. **No research left.** Every step names a file and a function or a line:
   `transition()` (`pipeline/core/machine.py:37`), `finish_regate()`
   (`:613`), `start()`'s `revalidating` branch (`:539-543`), the import at
   `:27-28`, `README.md:190`, `pipeline/cli/metrics.py:117`. I confirmed each.
6. **Riskiest step and its fallback.** Step 7: `git rebase --abort` then
   `git reset --hard <base>` discards commits in a live worktree. The plan
   states the fallback -- a non-zero `rc` calls `escalate()` quoting `repair`,
   which is exactly today's behaviour. One reading requirement for
   implementing: the `git reset --hard` exit code must be assigned back into
   the `rc` that step 8 tests. A reset that fails while `rc` still holds the
   abort's 0 would advance a ticket whose branch was never recut.
7. **Regression surface.** A clean rebase and a stale re-gate both run through
   the same `finish_regate()` and the same changed `start()` branch; criterion 5
   names `test_a_still_good_plan_is_implemented_after_the_rebase` and
   `test_a_stale_plan_is_re_gated_on_approval`, which assert `implementing` and
   the `stale_regate` bounce. `README.md` is covered by criterion 6. Nothing in
   `pipeline/` enumerates the legal `result` strings -- I grepped -- so the new
   `"conflict"` value breaks no consumer. `merging`'s conflict path is
   untouched.
8. **Blast radius matches class.** `bugfix`, six files: two logic hunks
   (`machine.py`, `supervisor.py`), one comment (`metrics.py`), two tests, one
   doc sentence. Proportionate.

One defensive detail, not a blocker: step 7's `rec.get("base") or "main"`
default is unreachable once step 6 sets `rec["base"]`. If it ever fired in a
project whose base is not `main`, it would reset the branch onto the wrong
branch rather than fail.

### 2026-08-21 09:24:01Z · plan-validation · session · session=a727ce9a-70dc-4e28-a059-d5c9fb0e049c

`plan-validation` ran as session `a727ce9a-70dc-4e28-a059-d5c9fb0e049c`
- replay: `claude --resume a727ce9a-70dc-4e28-a059-d5c9fb0e049c`
- log: `.project/logs/TICKET-029-plan-validation-a727ce9a.log`

### 2026-08-21 09:24:01Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan validated: all eight items pass; root cause is finish_regate() escalating without transition(); two non-blocking notes recorded

### 2026-08-21 09:26:52Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 09:37:44Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back` fails as required
```
/test_dispatch.py:612: AssertionError
----------------------------- Captured stdout call -----------------------------
TICKET-001: -> revalidating
  start TICKET-001: revalidating (script) pid 1471201 -> TICKET-001-revalidating-3517c00d.log
  TICKET-001: -> escalated (rebase onto base conflicted (exit 1)
```
$ git rebase main

Rebasing (1/1)
Auto-merging f.py
CONFLICT (content): Merge conflict in f.py
error: could not apply fa1eeab... ticket commit
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply fa1eeab... # ticket commit

```)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: `tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back` fails on base `main` too -- the bug is not already fixed upstream
```
cted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply fa1eeab... # ticket commit

```)
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.19s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-7p7qmgsv/base
      Built pipeline @ file:///tmp/pipeline-base-7p7qmgsv/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 09:37:44Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 · implementing · todo

Todo list, one entry per plan step:

1. [x] `tests/test_machine.py`: add `test_a_rebase_conflict_returns_to_triage_and_is_bounded`
2. [x] run it, see it fail on unknown-pair fallback
3. [x] `pipeline/core/machine.py`: add `("revalidating", "conflict")` row
4. [x] run `tests/test_machine.py`, all pass
5. [x] `pipeline/daemon/supervisor.py`: extend worktree import
6. [x] `pipeline/daemon/supervisor.py`: `start()`'s `revalidating` branch uses `base_ref(cfg)`, quotes it, sets `rec["base"]`
7. [x] `pipeline/daemon/supervisor.py`: `finish_regate()` recut on conflict -- abort, reset --hard, assign rc
8. [x] `pipeline/daemon/supervisor.py`: finish recut body -- escalate on failed rc, else `advance(..., "conflict", ..., agent=False)`
9. [x] `tests/test_dispatch.py`: rewrite `test_a_rebase_conflict_on_approval_escalates_and_keeps_the_worktree` -> `test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage`
10. [x] run `tests/test_dispatch.py -k rebase`, pass
11. [x] `README.md`: replace escalation sentence with recut description
12. [x] `pipeline/cli/metrics.py`: extend view 1 comment
13. [x] run full suite + guard script, commit

### 2026-08-21 09:39:09Z · implementing · note

`implementing` was interrupted; lease released

### 2026-08-21 · implementing · note

Resumed. Steps 1-4 were already committed to the working tree, uncommitted,
from the interrupted run: `("revalidating", "conflict")` row in
`pipeline/core/machine.py` and `test_a_rebase_conflict_returns_to_triage_and_is_bounded`
in `tests/test_machine.py`. Verified both against the plan and kept them
rather than redo the work.

`uv run --group dev pytest -q tests/test_machine.py -k rebase_conflict`:

```
.                                                                        [100%]
1 passed, 13 deselected in 0.02s
```

Ran steps 5-13. `uv run --group dev pytest -q tests/test_dispatch.py -k rebase`:

```
...                                                                      [100%]
3 passed, 21 deselected in 0.20s
```

`uv run --group dev pytest -q`:

```
........................................................................ [ 36%]
........................................................................ [ 73%]
....................................................                     [100%]
196 passed in 8.56s
```

`./pipeline/hooks/test_dangerous_commands.py`: `guard: all passed`.

Committed `ea0b590` "fix: a rebase conflict at revalidating recuts the branch
and returns to triage", touching the six files the plan named.

### 2026-08-21 09:51:03Z · implementing · session · session=7723fd33-983f-482f-80d0-f977d45a47f7

`implementing` ran as session `7723fd33-983f-482f-80d0-f977d45a47f7`
- replay: `claude --resume 7723fd33-983f-482f-80d0-f977d45a47f7`
- log: `.project/logs/TICKET-029-implementing-7723fd33.log`

### 2026-08-21 09:51:03Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ plan executed, all 13 steps done; rebase conflict at revalidating now recuts the branch and returns to triage; full suite 196 passed, guard passed, committed ea0b590

### 2026-08-21 · review · review · verdict=PASS

**Review of commit `ea0b590`: PASS. No blocking finding.**

Delta reviewed: `git diff main...HEAD`, six files, `+93 -24`. `262fd32` (the
reproduction test) is triage's commit and is reviewed here only as the
criterion it serves. This is the first review pass; `## Thread` holds no
earlier review entry to verify resolved.

Every acceptance criterion runs green:

```
uv run --group dev pytest -q \
  tests/test_dispatch.py::test_a_rebase_conflict_at_revalidating_leaves_a_way_back \
  tests/test_dispatch.py::test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage \
  tests/test_dispatch.py::test_a_still_good_plan_is_implemented_after_the_rebase \
  tests/test_dispatch.py::test_a_stale_plan_is_re_gated_on_approval \
  tests/test_machine.py::test_a_rebase_conflict_returns_to_triage_and_is_bounded \
  tests/test_stages.py::test_the_docs_name_the_dependencies_and_the_targets_the_code_has
......                                                                   [100%]
6 passed in 0.20s
```

Full suite reproduces the implementer's number: `196 passed in 8.55s`.

Checked against the plan and the decisions:

1. Plan step 7's rc assignment, which plan-validation flagged, is present:
   `rc, reset_out = run_cmd(f"git reset --hard {base}", rec["wt"])` reassigns
   the `rc` that the next `if rc != 0:` tests. A failed reset escalates and
   cannot advance the ticket.
2. The bound holds. `charge()` escalates on `c[key] >= bound`,
   `BOUNDS["bugfix"]` carries no `rebase_conflicts` key, so the fallback is
   `MAX_ATTEMPTS = 2`: first conflict charges 1 and returns `triage`, second
   charges 2 and returns `escalated`.
3. `advance()` passes `agent=False`, as DEC-022 requires, and emits a plain
   `transition`. `emit("escalated", ...)` fires only on the `nxt ==
   "escalated"` branch, so the `metrics.py` view-1 comment's claim -- the
   counter does not inflate the escalation rate unless it exhausts its bound
   -- is accurate.
4. `start()` and `finish_regate()` name the same branch. `start()` computes
   `base = base_ref(cfg)` once, quotes it into `git rebase`, and stores the
   unquoted value on `rec["base"]`; `finish_regate()` quotes that same value.
   DEC-017 satisfied.
5. The new test is not vacuous. `git rebase --abort` alone would leave `f.py`
   at `branch side` and `ticket commit` in the log, and the test asserts
   `(wt / "f.py").read_text() == "base side\n"` and `"ticket commit" not in
   log` -- so dropping the `git reset --hard` fails it.
6. Grep for `stale_regate` across the repo finds no counter enumeration
   outside `machine.py`, `metrics.py`'s comment, README and the tests, so no
   view, `ls` column or TUI panel had to learn `rebase_conflicts`.
7. The README edit sits after the word `stale_regate`, as gotcha 4 requires;
   `tests/test_stages.py::test_the_docs_name_the_dependencies_and_the_targets_the_code_has`
   passes.

Non-blocking notes, recorded and not fixed:

1. **nit** -- `if rec is not None:` in `start()`'s `revalidating` branch is
   dead. The local `child()` returns `(True, rec)` with `rec` always a dict.
2. **nit** -- `rec.get("base") or "main"` in `finish_regate()` is dead for the
   same reason: `finish_regate()` runs only for `kind == "regate"`, and the
   only producer of that record sets `rec["base"]`. If a future caller ever
   omits it, the fallback recuts onto `main` silently rather than escalating.
3. **nit** -- `git rebase --abort && git log --oneline {base}..HEAD` shares one
   exit code, so a failing `git log` escalates a ticket whose abort succeeded.
   The `git log` is evidence, not repair.
4. **out of scope** -- the review stage's guard allowlist blocks
   `./pipeline/hooks/test_dangerous_commands.py`: "`test_dangerous_commands.py`
   is not on the read-only allowlist". I did not run the guard script. The
   delta touches no file under `pipeline/hooks/`.

Reminder for merge, from `CLAUDE.md`: this commit changes `transition()`, so
it **requires human review before merge** whatever the pipeline says.

### 2026-08-21 09:54:01Z · review · session · session=0dfbb270-b248-427f-8d17-d520342e3eeb

`review` ran as session `0dfbb270-b248-427f-8d17-d520342e3eeb`
- replay: `claude --resume 0dfbb270-b248-427f-8d17-d520342e3eeb`
- log: `.project/logs/TICKET-029-review-0dfbb270.log`

### 2026-08-21 09:54:01Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed ea0b590 (6 files, +93 -24): all 6 acceptance-criteria tests pass, full suite 196 passed; 4 non-blocking nits in the thread

### 2026-08-21 09:54:10Z · verifying · transition · to=merging · result=ok

**verifying -> merging** (result: `ok`)

regression suite exit 0
```
...HEAD
ok  allow [always] cargo build --release
ok  BLOCK [readonly] sed -i s/a/b/ x.py
ok  BLOCK [readonly] echo hi > file.txt
ok  BLOCK [readonly] git commit -am wip
ok  BLOCK [readonly] cp a b
ok  BLOCK [readonly] pip install requests
ok  BLOCK [readonly] mv a b
ok  BLOCK [readonly] python3 -c "open('/tmp/x','a').write(1)"
ok  BLOCK [readonly] git -C . commit -am wip
ok  BLOCK [readonly] pytest 2>out
ok  BLOCK [readonly] pytest >> log.txt
ok  BLOCK [readonly] git worktree add /tmp/x main
ok  BLOCK [readonly] python3 setup.py install
ok  BLOCK [readonly] tee /tmp/x
ok  BLOCK [readonly] curl https://example.com -o /tmp/x
ok  BLOCK [readonly] make install
ok  BLOCK [readonly] cargo run
ok  BLOCK [readonly] npm install
ok  BLOCK [readonly] echo $(whoami)
ok  allow [readonly] pytest -x
ok  allow [readonly] git diff main...HEAD
ok  allow [readonly] grep -rn foo .
ok  allow [readonly] git log --oneline
ok  allow [readonly] cat thing.py
ok  allow [readonly] python3 -m pytest --deselect x
ok  allow [readonly] ls -la
ok  allow [readonly] git show HEAD
ok  allow [readonly] git blame thing.py
ok  allow [readonly] rg evict src/
ok  allow [readonly] pytest -x 2>&1
ok  allow [readonly] find . -name '*.py'
ok  allow [readonly] cargo test
ok  allow [readonly] go test ./...
ok  allow [readonly] git status --porcelain
ok  allow [readonly] wc -l thing.py
ok  allow [readonly] python3 -m unittest
ok  allow [readonly] git diff main...HEAD | head -50
ok  end-to-end exit codes

guard: all passed

```

### 2026-08-21 09:54:11Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/029


Auto-merging README.md
Auto-merging pipeline/core/machine.py
Auto-merging tests/test_machine.py
CONFLICT (content): Merge conflict in tests/test_machine.py
Automatic merge failed; fix conflicts and then commit the result.

```

### 2026-08-21 09:55:21Z · human · note

**resumed** by human -> `merging`, reset ['rebase_conflicts', 'blocked_count', 'no_result', 'lease_expiries']

### 2026-08-21 09:55:21Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/029


Already up to date.
Updating 5cb7d26..30542f1
Fast-forward
 README.md                     |  7 +++++--
 pipeline/cli/metrics.py       | 11 ++++++-----
 pipeline/core/machine.py      |  6 ++++++
 pipeline/daemon/supervisor.py | 37 ++++++++++++++++++++++++++---------
 tests/test_dispatch.py        | 45 +++++++++++++++++++++++++++++++++++--------
 tests/test_machine.py         | 11 +++++++++++
 6 files changed, 93 insertions(+), 24 deletions(-)

```

### 2026-08-21 09:55:21Z · merging · decision

decision recorded as `DEC-029`
