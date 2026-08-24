---
id: TICKET-053
stage: done
class: bugfix
branch: ticket/053
test_file: tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass
files_declared:
- .claude/skills/file-ticket/SKILL.md
- README.md
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
- tests/test_gate.py
- tests/test_machine.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 9
  plan_files: 7
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 5bb52ccd-ad9d-4e3b-aa08-833b8f5ea618
  log: .project/logs/TICKET-053-review-5bb52ccd.log
approved_by: chezzijr
approved_at: '2026-08-24T12:58:09.037833+00:00'
---

## Summary
a ticket promoted from `quick-review` always fails Tier A, because its fix is already committed

**Review (2026-08-24): PASS**, no blocking findings. The delta is the whole branch,
`main...HEAD`, 7 commits (b27c668..d0a6335), 7 files, +265/-12. It matches the plan and
the acceptance criteria: `("quick-review", "fail")` returns `unwinding`,
`("unwinding", "ok")` returns `planning`, `("unwinding", "fail")` escalates, `start()`
records `cheap_route_head` and bails on a sha that fails `SAFE_SHA`, and `unwind_cmd()`
refuses a non-ancestor before it resets. Fresh runs: `uv run --group dev pytest -q` is
`287 passed in 12.78s`, and the five named tests alone are `5 passed, 40 deselected`.
`./pipeline/hooks/test_dangerous_commands.py` was NOT run -- the guard blocks it for a
read-only stage -- and no hook file is in the delta. Three minor findings, none
blocking: the README diagram's arrow columns do not line up, DEC-050 still reads active
with its by-hand revert, and `("implementing", "blocked")` with `cheap_route` still goes
straight to `planning`. Detail in `## Thread`.

**Implemented (2026-08-24).** All 9 plan steps done and committed (9bb7a5e, 247e217,
ea45b2b, e834c3e, 91c3db5, d0a6335): `unwind_cmd()` and `SAFE_SHA` in
`pipeline/daemon/supervisor.py`, `cheap_route_head` recorded at the cheap route's
`implementing` spawn, the `unwinding` stage added to `pipeline/core/machine.py` and wired
into `start()`/`_finish()`, `tests/test_gate.py`'s reproduction rewritten, `README.md` and
the file-ticket skill updated. `uv run --group dev pytest -q`: 287 passed.
`./pipeline/hooks/test_dangerous_commands.py`: all passed. Full detail in `## Thread`.

**Plan (2026-08-24).** `("quick-review", "fail")` returns a new dispatcher stage
`unwinding` instead of `planning`. `("unwinding", "ok")` returns `planning`;
`("unwinding", "fail")` escalates and charges no counter. `unwinding` runs
`unwind_cmd()` in the ticket worktree: `git merge-base --is-ancestor <sha> HEAD`,
then `git reset --hard <sha> && git clean -fd`, where `<sha>` is
`t.extra["cheap_route_head"]` -- the branch tip `start()` recorded when it spawned
the cheap route's `implementing`. Triage's test commit survives; only the route's
own commits go. No `counters` flag is added: the `("quick-review", "fail")` row is
itself the cheap-route marker, because `quick-review` is reachable only from
`("implementing", "ok")` with `cheap_route` set. Detail in `## Digest`, `## Plan`
and `## Decisions`.

**Plan review (2026-08-24): PASS**, all eight items. The plan fixes why the test
passes -- it removes the commit -- not the gate's verdict. Every anchor it names
exists at the line it names. Two carry-overs for `implementing`, neither a
blocker. First, the rewritten `tests/test_gate.py` reproduction runs
`git reset --hard` itself rather than calling `unwind_cmd()` (DEC-017 forbids the
import), so `tests/test_dispatch.py` is the only cover for the repair itself.
Second, DEC-050 carries no `superseded-by:` footer, so its "planning reverts the
cheap route's commit by hand" paragraph still reads as active. Per-item reasoning
is in `## Thread`.

`triage` can send a small ticket down the cheap route: `result: chore` sets
`counters["cheap_route"]` and routes straight to `implementing`, skipping
`planning`, `plan-validation` and the approval gate. `implementing` commits the
fix and the ticket goes to `quick-review`. When `quick-review` answers `fail`
the ticket is promoted to `planning` (`pipeline/core/machine.py`, the
`("quick-review", "fail")` row) and takes the full path.

It arrives there with the fix already committed on its branch, and nothing
removes it. `planning` writes a plan, `plan-validation` runs `gate()`, and
`gate()` runs the ticket's `test_file` in the worktree, where it now PASSES:

    pipeline/core/gate.py:219
    findings.append(f"`{test}` PASSES -- it must fail before implementation")

That is a Tier A failure, so the ticket is charged `plan_validation_attempts`
and sent back to `planning`, which cannot fix it: `implementing` is the only
stage that could change the tree, and it runs after the gate. The second pass
is identical and the ticket escalates with a correct plan and a working fix.

Not observed as an escalation, because the one ticket that took this path on
2026-08-24 was rescued by its `planning` stage, which recognised the trap and
repaired the branch itself. TICKET-050's `## Decisions` records what it did and
why:

    I reverted the `pipeline/cli/main.py` half of eea468d and kept the
    rewritten test, committed as ad4116e. Reason: `plan-validation` runs
    `gate()` next, and `gate()` fails a ticket whose `test_file` PASSES in the
    worktree. No plan step could have fixed that -- `implementing` runs after
    the gate.

That is a stage exceeding its job (`_common.md` rule 2: do only your stage's
job) to work around a hole in the state machine, and it is not something to
rely on. A reproduction has to construct the case rather than cite a log:
drive a ticket `triage -> implementing -> quick-review: fail -> planning`, then
run `gate()` and assert the `PASSES` finding.

Expected: the promotion undoes the cheap route's commit before `planning` sees
the branch, so Tier A meets the red test `triage` committed. The neighbouring
row already reasons about a promoted ticket meeting a gate it cannot satisfy --

    case ("implementing", "blocked"):
        if c.pop("cheap_route", None):
            # there is no plan to re-gate, so the normal target would fail
            # its own Tier A gate on the missing sections and burn one of
            # the two plan attempts before landing here anyway
            return "planning", c

-- so the shape of the answer is established; this row needs the same care for
a different reason, a commit rather than missing sections.

Three constraints for planning to settle, not to discover:

1. `transition()` is pure and total and must stay so. It cannot run git. If the
   repair is a dispatcher step, it needs a stage name in `KNOWN_STAGES` and
   `DISPATCHER_STAGES`, and `revalidating`'s conflict repair (abort, then
   `git reset --hard <base>`) is the closest existing model.
2. Only the cheap route's own commit may be discarded. `triage` commits the
   failing test on the same branch, and that commit must survive -- losing it
   destroys the reproduction the whole ticket rests on.
3. `cheap_route` is consumed at `implementing` (`c.pop`), so by the time
   `quick-review` fails, the flag that would identify the route is gone.
   Whatever carries the information has to be decided explicitly; do not
   reintroduce a flag that lets a ticket route back onto the cheap path.

The failure a test should show is `gate()` returning
"`<test>` PASSES -- it must fail before implementation" for a ticket promoted
out of `quick-review`.

## Reproduction

`tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass`
drives `transition()` through `triage(chore) -> implementing(ok) -> quick-review(fail)`,
lands on `planning`, then builds a git ticket project whose branch already has
the cheap route's fix committed and runs `gate()` against it.

Command: `uv run --group dev pytest -q tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass`

Failure:
```
AssertionError: ['`test_thing.py::test_broken` PASSES -- it must fail before implementation']
assert False
```

expect: `test_thing.py::test_broken` PASSES -- it must fail before implementation

## Digest

- `pipeline/core/machine.py` -- `transition()` row `("quick-review", "fail")` returns `planning` today (line 160). `KNOWN_STAGES` (line 51) and `DISPATCHER_STAGES` (line 60) are the two sets a dispatcher-run stage must join. `FENCED` names `("transition", ...)` in this file, so this ticket parks at `awaiting-merge` before it merges.
- `pipeline/daemon/supervisor.py` -- `start()` holds one `if stage == ...` branch per dispatcher stage (`verifying`, `merging`, `revalidating`, lines 640-661); each calls the local `child(cmd, kind)`, which takes the lease and calls `spawn_command()`. `_finish()` routes on `rec["kind"]` (lines 845-856). `merge_cmd()` (line 501) is the model for a command builder. `finish_child()` (line 726) turns a child's exit code into `advance(..., "ok"|"fail", ...)` with `log_tail(rec)` quoted. `bail(reason)` inside `start()` escalates before any child exists.
- Entry points: `supervisor.start(project, path, hcfg, inflight)` spawns; `supervisor.finish(project, rec)` reaps. `tests/test_dispatch.py::test_a_rebase_conflict_recuts_the_branch_and_returns_to_triage` is the call shape to copy.
- The route's identity needs no new flag. `quick-review` is reachable only from `("implementing", "ok")` with `cheap_route` set, so the `("quick-review", "fail")` row **is** the cheap-route marker. `counters["cheap_route"]` stays popped at `implementing` (DEC-026), so nothing routes back onto the cheap path.
- What has to be carried is the *boundary*, not the route: which commits are the cheap route's own. Nothing in git distinguishes them -- same author, same committer, and a commit-message prefix is a convention no code enforces. So `start()` records the worktree's `git rev-parse HEAD` into `t.extra["cheap_route_head"]` when it spawns the cheap route's `implementing`, the last moment `counters["cheap_route"]` is still set.
- `t.extra` is dispatcher-owned in practice: `_finish()` rebuilds the ticket as `replace(snap, body=agent.body)`, so every frontmatter key comes back from the pre-spawn snapshot and only the body is the agent's. `note_wait()` (`t.extra["waiting"]`) and `t.extra["last_session"]` already use it this way. It is still pattern-checked and `shlex.quote`d at the point of use, per invariant 5 -- both, not either.
- Gotcha: `git reset --hard` leaves untracked files. An untracked file `implementing` left behind can complete the fix and make `test_file` pass at the very gate this repair exists to satisfy, so the repair also runs `git clean -fd` (no `-x`: ignored build artefacts are not the cheap route's work).
- Gotcha (DEC-017): `tests/test_gate.py` is copied wholesale onto a checkout of base and imported there, and it is also collected on the branch *before* `implementing` runs. A new module-level import of a name this ticket adds (`unwind_cmd`) turns both runs into a collection error and blocks the ticket. The rewritten reproduction therefore adds no import: it uses `transition`, `gate`, `subprocess` and `shutil`, all already imported at the top of that file.
- Gotcha: `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` asserts `t("quick-review", "fail")[0] == "planning"` in two places (lines 210 and 220). Both change in the same step as `transition()`.
- Gotcha: `tests/test_stages.py::test_dispatcher_stages_are_the_ones_with_no_prompt` fails if `pipeline/stages/unwinding.md` is created. Do not create one.

## Decisions checked

Grepped `.project/decisions/` for `cheap route`, `cheap_route`, `quick-review`, `promoted`, `reset --hard`, `revalidating`, `DISPATCHER_STAGES`, `untracked`, `git clean`.

- **DEC-050** (active) is the direct precedent. It records `planning` reverting the cheap route's fix by hand on TICKET-050 and says: "If a future change stops `planning` from writing to the branch, this promotion path needs a dispatcher-side revert instead, or it escalates every time." This plan builds that dispatcher-side revert, so it follows the record's own named successor rather than contradicting it. No `supersedes:` line is needed. Its `pipeline plan` paragraph is untouched.
- **DEC-029** (active) constrains the repair directly: "A future change that routes a stage holding implementation commits through `finish_regate()` would discard real work. Gate such a change on the branch carrying no commit but triage's, or give it a different repair." This plan gives it a different repair -- a new `unwind` child kind with its own `_finish()` branch. `finish_regate()` is not reached and its `git reset --hard <base>` is not reused; `unwinding` resets to triage's recorded tip, not to base.
- **DEC-026** (active) fixes what may carry the route: `counters["cheap_route"]` is consumed at `implementing` to make the route one-way by construction, and "Do not 'fix' this by re-setting the flag to keep the second pass cheap." This plan adds no flag to `counters`; the boundary sha lives in `t.extra` and never reaches `transition()`.
- **DEC-017** (active) forbids new imports in a test file the gate copies onto base. It is why the rewritten `tests/test_gate.py` reproduction calls no new function, and why the dispatcher-side coverage lives in `tests/test_dispatch.py`.
- **DEC-045** (active): "A conflict at `merging` is never repaired by a recut... at `merging` the branch holds every implementation commit." Consistent -- `unwinding` runs before `planning`, never at or after `verifying`.
- **DEC-024** was grepped (effort tiers) and is not relevant: no stage prompt and no model tier changes here.

## Plan

1. Add `SAFE_SHA = re.compile(r"^[0-9a-f]{7,40}$")` beside the other module constants in `pipeline/daemon/supervisor.py`, and add `test_the_unwind_refuses_a_sha_that_is_not_on_the_branch` to `tests/test_dispatch.py`: build `git_project()`, cut a worktree with `supervisor.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})`, commit `test_thing.py` as `'triage: the failing test'`, capture `triage_sha` from `git rev-parse HEAD`, commit `f.py` holding the fix as `'implementing: the fix'`, write an untracked `scratch.py`, commit `'base moved'` on `d`'s `main`, then assert `subprocess.run(supervisor.unwind_cmd(<that main sha>), shell=True, cwd=wt, capture_output=True, text=True)` exits non-zero, prints `is not an ancestor of HEAD`, and leaves `git -C <wt> rev-parse HEAD` unchanged; then assert `supervisor.unwind_cmd(triage_sha)` exits 0, leaves HEAD at `triage_sha`, keeps `test_thing.py`, restores `f.py` to base's content and removes `scratch.py`. Run `uv run --group dev pytest -q tests/test_dispatch.py -k unwind` and watch it fail with `AttributeError: module 'pipeline.daemon.supervisor' has no attribute 'unwind_cmd'`.
2. Add `unwind_cmd(sha: str) -> str` to `pipeline/daemon/supervisor.py` directly below `merge_cmd()`. With `q = shlex.quote(sha)` it returns three lines: `git merge-base --is-ancestor {q} HEAD || { echo "{q} is not an ancestor of HEAD -- refusing to unwind"; exit 1; }`, then `git log --oneline {q}..HEAD`, then `git reset --hard {q} && git clean -fd`. Its docstring states: `sha` is the branch tip recorded when the cheap route's `implementing` was spawned, so everything after it is that stage's work; the ancestor guard is what stops a stale value from resetting the branch onto an unrelated commit; `git clean -fd` runs because an untracked file `implementing` left behind survives `git reset --hard` and can make `test_file` pass at the gate this repair exists to satisfy; `-x` is left off so ignored build artefacts survive. Re-run the step 1 command, expect the `-k unwind` selection to pass, and commit.
3. Record the boundary in `pipeline/daemon/supervisor.py`. First add `test_the_cheap_routes_branch_tip_is_recorded_before_the_fix_is_written` to `tests/test_dispatch.py`: write `FIXTURE.replace("stage: plan-validation", "stage: implementing").replace("counters: {}", "counters: {cheap_route: 1}")`, call `supervisor.start(d, path, harness("fake"), {})`, `rec["proc"].wait()`, and assert `Ticket.load(path).extra["cheap_route_head"]` equals the worktree's `git rev-parse HEAD`; assert a second ticket with `counters: {}` records no such key. Watch it fail with `KeyError: 'cheap_route_head'`. Then in `start()`, immediately above the `t.take_lease(f"{stage}-{os.getpid()}")` that precedes `strip_settings_sources(wt)`, add `if stage == "implementing" and t.counters.get("cheap_route") and not t.extra.get("cheap_route_head"):` which calls `run_cmd("git rev-parse HEAD", wt)` and, when the exit code is 0 and `SAFE_SHA` matches the stripped output, sets `t.extra["cheap_route_head"]` to it; the `not t.extra.get(...)` guard is what keeps a lease-expiry respawn from re-recording a tip that already carries the route's own commits. Run `uv run --group dev pytest -q tests/test_dispatch.py -k cheap_routes_branch_tip` green and commit.
4. Add the `unwinding` stage to `pipeline/core/machine.py`: put `"unwinding"` in `KNOWN_STAGES` and in `DISPATCHER_STAGES`, change the `case ("quick-review", "fail")` body to `return "unwinding", c` (keep its comment and add that the row is itself the cheap-route marker, since `quick-review` is reachable only from `("implementing", "ok")` with the flag set), and add `case ("unwinding", "ok"): return "planning", c` and `case ("unwinding", "fail"): return "escalated", c`, the latter commented that a repair which already refused is never guessed at, the same rule as `("merging", "fail")`. In `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` change line 210 to `assert t("quick-review", "fail")[0] == "unwinding"` with the message `"the promoted ticket reaches planning with the cheap route's fix still committed"`, change line 220 to `assert t("quick-review", "fail", {"cheap_route": 1})[0] == "unwinding"`, and add `assert t("unwinding", "ok")[0] == "planning"`, `assert t("unwinding", "fail")[0] == "escalated"`, `assert "unwinding" in M.KNOWN_STAGES` and `assert "unwinding" in M.DISPATCHER_STAGES`. Create no `pipeline/stages/unwinding.md`. Run `uv run --group dev pytest -q tests/test_machine.py tests/test_stages.py` and expect 0 failed.
5. Wire the stage into `pipeline/daemon/supervisor.py`: in `start()`, directly after the `if stage == "revalidating":` block, add `if stage == "unwinding":` which reads `head = str(t.extra.get("cheap_route_head") or "")`, returns `bail(f"cannot unwind the cheap route: cheap_route_head is {head!r}, not a commit sha")` when `SAFE_SHA` does not match, and otherwise `return child(unwind_cmd(head), "unwind")`; in `_finish()`, directly after the `if rec.get("kind") == "regate":` branch, add `if rec.get("kind") == "unwind": return finish_child(project, rec, "unwind", emit)`, commented that the reset's exit code is the whole verdict, like the merge. Run `uv run --group dev pytest -q tests/test_dispatch.py` and expect no new failure.
6. Add `test_a_promoted_cheap_route_ticket_reaches_planning_with_its_fix_unwound` to `tests/test_dispatch.py`: build the same two-commit worktree as step 1, set `t.extra["cheap_route_head"] = triage_sha` and `t.stage = "quick-review"` then `t.save()`, call `supervisor.advance(d, Ticket.load(path), "fail", "quick-review failed", agent=False)` and assert the stage is `unwinding`, then `did, rec = supervisor.start(d, path, harness("fake"), {})`, assert `rec["kind"] == "unwind"`, `rec["proc"].wait()`, `supervisor.finish(d, rec)`, and assert `Ticket.load(path).stage == "planning"`, that `git -C <wt> log --oneline` contains `triage: the failing test` and not `implementing: the fix`, that `(wt / "test_thing.py").is_file()`, that `(wt / "f.py").read_text()` is base's content, and `not Ticket.load(path).lease_active()`. Add `test_an_unwind_with_no_recorded_head_escalates_instead_of_guessing` to `tests/test_dispatch.py`: the same project with `stage: unwinding` and no `cheap_route_head`, asserting `supervisor.start(...)` returns `(True, None)` and `Ticket.load(path).stage == "escalated"`. Run `uv run --group dev pytest -q tests/test_dispatch.py` green and commit.
7. Rewrite the ticket's reproduction in `tests/test_gate.py`. Add a local helper `_cheap_route_project()` beside `_git_ticket_project` -- stdlib only, no new import (DEC-017) -- that `git init -qb main`s a temp dir, writes a buggy `f.py`, `.project/tickets/TICKET-001.md` = `FIXTURE` and `.project/pipeline.toml` with `test_one = "echo test_broken; grep -q fixed f.py"`, `test_suite = "true"`, `test_suite_without_new = "true"` and `base = "main"`, commits, adds worktree `ticket/001`, commits `test_thing.py` as triage's failing test, captures that sha, commits the fixed `f.py` as the cheap route's fix, and returns `(d, wt, triage_sha)`. Then change `test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass` so that after `transition(stage, "fail", counters)` it asserts `stage == "unwinding"` with the message `"planning is handed a branch that still carries the cheap route's fix"` and asserts `transition("unwinding", "ok", counters)[0] == "planning"`; then it calls `_cheap_route_project()`, runs `subprocess.run(f"git reset --hard {triage_sha}", shell=True, cwd=wt, capture_output=True, text=True)`, asserts `(wt / "test_thing.py").is_file()` with the message `"the repair discarded triage's test commit"`, and ends with `ok, failures = gate(d, "TICKET-001", workdir=wt)`, `assert ok, failures` and `shutil.rmtree(d, ignore_errors=True)`. Rewrite its docstring to state what the repair must leave behind. Run `uv run --group dev pytest -q tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass` and expect `1 passed`.
8. Update `README.md`: keep the diagram line `      +-- (chore) -> implementing -> quick-review --+` and add below it a line carrying a `|` under `quick-review` and a line reading `      planning <- unwinding <-------------+   (fail: the cheap route's commit is undone first)`; and in numbered point 4 change "`verifying`, `revalidating` and `merging` have no agent at all" to "`verifying`, `revalidating`, `unwinding` and `merging` have no agent at all", appending to that sentence "and putting a promoted cheap-route branch back where `triage` left it is a `git reset --hard` no prompt should be trusted to aim". Update `.claude/skills/file-ticket/SKILL.md` so the sentence "`quick-review` returns it to `planning`, and so to the approval gate, if the diff or the test does not hold up" continues "; the dispatcher undoes the cheap route's commit on the way, so the ticket re-plans against the failing test `triage` committed".
9. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`. Expect pytest to report 0 failed and the guard script to report every case passing. Commit `pipeline/core/machine.py`, `pipeline/daemon/supervisor.py`, `tests/test_machine.py`, `tests/test_gate.py`, `tests/test_dispatch.py`, `README.md` and `.claude/skills/file-ticket/SKILL.md`.

## Acceptance criteria

- `tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass` passes: a ticket driven `triage(chore) -> implementing(ok) -> quick-review(fail)` lands on `unwinding`, `unwinding(ok)` lands on `planning`, and a branch reset to triage's commit passes `gate()`.
- `tests/test_dispatch.py::test_a_promoted_cheap_route_ticket_reaches_planning_with_its_fix_unwound` passes: after `start()` and `finish()` the ticket is at `planning`, and `git log --oneline` in the worktree still contains `triage: the failing test` and no longer contains `implementing: the fix`.
- `tests/test_dispatch.py::test_the_unwind_refuses_a_sha_that_is_not_on_the_branch` passes: `unwind_cmd()` with a sha that is not an ancestor of HEAD exits non-zero, prints `is not an ancestor of HEAD` and leaves HEAD where it was; with triage's sha it exits 0, keeps `test_thing.py` and removes the untracked `scratch.py`.
- `tests/test_dispatch.py::test_an_unwind_with_no_recorded_head_escalates_instead_of_guessing` passes: `start()` returns `(True, None)` and the ticket is `escalated`.
- `tests/test_dispatch.py::test_the_cheap_routes_branch_tip_is_recorded_before_the_fix_is_written` passes: a cheap-route `implementing` spawn records `extra["cheap_route_head"]` equal to the worktree's HEAD, and a non-cheap-route spawn records no such key.
- `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` passes with `("quick-review", "fail") -> "unwinding"`, `("unwinding", "ok") -> "planning"`, `("unwinding", "fail") -> "escalated"`, and `"unwinding"` in both `KNOWN_STAGES` and `DISPATCHER_STAGES`.
- `tests/test_stages.py::test_dispatcher_stages_are_the_ones_with_no_prompt` and `tests/test_stages.py::test_every_stage_named_by_the_state_machine_has_a_prompt` both pass with no `pipeline/stages/unwinding.md` on disk.
- `uv run --group dev pytest -q` reports 0 failed, and `./pipeline/hooks/test_dangerous_commands.py` reports every case passing.

## Decisions

**A ticket promoted out of `quick-review` is repaired by the dispatcher, at a stage of its own.** `("quick-review", "fail")` returns `unwinding`, a `DISPATCHER_STAGES` member with no prompt file, and `("unwinding", "ok")` returns `planning`. Before this, the row returned `planning` directly and the cheap route's fix was still committed on the branch, so `gate()` at `plan-validation` failed the ticket with "`<test>` PASSES -- it must fail before implementation". No plan step could fix that: `implementing` runs after the gate. This is the dispatcher-side revert DEC-050 named as the successor to `planning` repairing the branch by hand, so `planning` must not repair the branch itself any more.

**The `("quick-review", "fail")` row is the cheap-route marker; no flag was reintroduced.** `quick-review` is reachable only from `("implementing", "ok")` with `counters["cheap_route"]` set, so reaching that row already proves the route. DEC-026's rule that the flag is consumed at `implementing` is untouched, and nothing routes back onto the cheap path.

**`t.extra["cheap_route_head"]` carries the boundary, not the route.** It is the worktree's HEAD at the moment `start()` spawned the cheap route's `implementing` -- the last point at which `counters["cheap_route"]` is still set, and the last point at which anything knows which commits are the route's own. Git cannot tell them apart otherwise: same author, same committer, and a commit-message prefix is a convention no code enforces. It is written only when absent, so a lease-expiry respawn cannot re-record a tip that already carries the route's commits. It is pattern-checked against `^[0-9a-f]{7,40}$` and `shlex.quote`d before it reaches a shell -- invariant 5 wants both, and `t.extra` is dispatcher-owned only in practice (`_finish()` rebuilds the ticket as `replace(snap, body=agent.body)`), not by `CONTROL_FIELDS`.

**`unwinding` resets to triage's tip, not to base, and does not reuse `finish_regate()`.** DEC-029 permits the recut at `revalidating` only because that branch carries triage's test commit and nothing else, and warns that routing a stage holding implementation commits through `finish_regate()` would discard real work. `unwinding` is exactly such a stage, so it has its own `unwind` child kind and its own `git reset --hard <triage tip>`. Resetting to base here would destroy the reproduction the whole ticket rests on.

**The unwind refuses rather than guesses.** `git merge-base --is-ancestor <sha> HEAD` runs first, so a stale or hand-edited sha fails the child instead of moving the branch somewhere unrelated. A missing or malformed `cheap_route_head` escalates in `start()` before any child exists. `("unwinding", "fail")` escalates and charges no counter: a repair that already refused is never retried, the same rule as `("merging", "fail")`.

**`git clean -fd` is part of the repair, and `-x` is deliberately absent.** `git reset --hard` leaves untracked files behind, and an untracked file `implementing` left in the worktree can complete the fix and make `test_file` pass at the very gate this repair exists to satisfy. `-x` is left off so ignored build artefacts, which are not the cheap route's work, survive.

**The reproduction in `tests/test_gate.py` adds no import.** DEC-017: that file is copied wholesale onto a checkout of base and imported there, and it is also collected on the branch before `implementing` runs. Importing `unwind_cmd` would make both runs a collection error and block the ticket that adds it. The dispatcher-side coverage lives in `tests/test_dispatch.py` for that reason, and `_cheap_route_project()` is local to `tests/test_gate.py` for the same reason `_git_ticket_project` is.

## Rollback

Revert the commits from steps 2 through 8 in one `git revert`. That restores `("quick-review", "fail") -> "planning"`, removes `unwinding` from `KNOWN_STAGES` and `DISPATCHER_STAGES`, removes `unwind_cmd()`, the `cheap_route_head` recording and both the `start()` and `_finish()` branches, and restores the previous `tests/test_gate.py` reproduction, the `tests/test_machine.py` asserts, `README.md` and `.claude/skills/file-ticket/SKILL.md`. A ticket parked at `unwinding` when the revert lands has no row for its stage and escalates on the next tick; move it on by hand with `pipeline resume <id> --stage planning` after running `git reset --hard <its cheap_route_head>` in its worktree. Nothing else reads `t.extra["cheap_route_head"]`, so a leftover key in a ticket file is inert.

## Thread

### 2026-08-24 11:31:58Z · new · transition · to=triage · result=new

### 2026-08-24 · triage

Reproduced. Committed `b27c668`, test
`tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass`.
It drives `transition()` through `("triage","chore") -> ("implementing","ok")
-> ("quick-review","fail")`, confirms the target is `planning` with
`cheap_route` gone from counters, then runs `gate()` on a git ticket project
whose branch already carries the cheap route's fix. The gate returns
`` `test_thing.py::test_broken` PASSES -- it must fail before implementation
`` -- the exact finding the ticket reports.

`result: ok`, not `chore`: the fix needs a design choice this stage must not
make. It has to add a dispatcher-run repair step (name, position in
`KNOWN_STAGES`/`DISPATCHER_STAGES`, and how it tells the cheap route's commit
apart from `triage`'s test commit on the same branch, since `cheap_route` is
already popped by the time `quick-review` fails). Leaving that to planning.

Ran `uv run --group dev pytest -q tests/test_gate.py tests/test_machine.py`:
52 passed, 1 failed (the new test, for the reported reason). No other test
regressed.

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 11:33:45Z · triage · session · session=742bb915-cfed-469b-ae9e-66909d69f4ee

`triage` ran as session `742bb915-cfed-469b-ae9e-66909d69f4ee`
- replay: `claude --resume 742bb915-cfed-469b-ae9e-66909d69f4ee`
- log: `.project/logs/TICKET-053-triage-742bb915.log`

### 2026-08-24 11:33:45Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: transition() promotes quick-review-fail to planning with the cheap-route fix still committed, and gate() rejects it with the exact PASSES finding; failing test committed as b27c668.

### 2026-08-24 11:48:43Z · planning · session · session=3ef64687-60f5-435e-816c-8f43491ef283

`planning` ran as session `3ef64687-60f5-435e-816c-8f43491ef283`
- replay: `claude --resume 3ef64687-60f5-435e-816c-8f43491ef283`
- log: `.project/logs/TICKET-053-planning-3ef64687.log`

### 2026-08-24 11:48:43Z · planning · note

`planning` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-08-24 · planning

Plan written. 9 steps, 7 files.

The three constraints resolve as follows.

1. `transition()` stays pure: the repair is a new `DISPATCHER_STAGES` member
   `unwinding`, with no prompt file, spawned by `start()` like `revalidating`.
2. Only the cheap route's commits are discarded. `unwind_cmd()` resets to
   `t.extra["cheap_route_head"]`, the worktree HEAD recorded when `start()`
   spawned the cheap route's `implementing`, so triage's test commit survives.
   `git merge-base --is-ancestor` refuses a sha that is not on the branch.
3. Nothing carries the route. `quick-review` is reachable only from
   `("implementing", "ok")` with `cheap_route` set, so the
   `("quick-review", "fail")` row is itself the marker. No flag is added to
   `counters`, and DEC-026's one-way rule is untouched.

Two things outside this stage's job, noted rather than fixed:

- `CLAUDE.md` names only `verifying` and `merging` as dispatcher-run stages;
  `revalidating` was already missing before this ticket. Step 8 updates
  `README.md`, which enumerates all three, but leaves `CLAUDE.md` alone.
- The diff touches `transition()`, which `machine.FENCED` covers, so this
  ticket parks at `awaiting-merge` for a human before it lands.

### 2026-08-24 12:00:54Z · planning · session · session=0b25bfe2-c342-4d6a-8a48-e6dc88c302a6

`planning` ran as session `0b25bfe2-c342-4d6a-8a48-e6dc88c302a6`
- replay: `claude --resume 0b25bfe2-c342-4d6a-8a48-e6dc88c302a6`
- log: `.project/logs/TICKET-053-planning-0b25bfe2.log`

### 2026-08-24 12:00:54Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: (quick-review, fail) routes to a new dispatcher stage `unwinding` that resets the branch to the tip recorded before the cheap route's `implementing`, so triage's test commit survives and Tier A meets a red test.

### 2026-08-24 12:01:08Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass` fails as required
```
}
        stage, counters = transition(stage, "chore", counters)
        assert stage == "implementing" and counters.get("cheap_route") == 1
        stage, counters = transition(stage, "ok", counters)
        assert stage == "quick-review" and "cheap_route" not in counters
        stage, counters = transition(stage, "fail", counters)
        assert stage == "planning"
    
        # the cheap route's fix is still committed on the branch by the time
        # `planning` -> `plan-validation` runs gate() against it -- nothing has
        # repaired it
        d, wt = _git_ticket_project("buggy\n", "fixed\n")
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert ok, failures
E       AssertionError: ['`test_thing.py::test_broken` PASSES -- it must fail before implementation']
E       assert False

tests/test_gate.py:277: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass` fails on base `main` too -- the bug is not already fixed upstream
```
 repaired it
        d, wt = _git_ticket_project("buggy\n", "fixed\n")
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert ok, failures
E       AssertionError: ['`test_thing.py::test_broken` PASSES -- it must fail before implementation']
E       assert False

tests/test_gate.py:277: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yq7o6s0v/base
      Built pipeline @ file:///tmp/pipeline-base-yq7o6s0v/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 · plan-validation · review · verdict=PASS

**Plan review: PASS.** Eight items, each checked against the code.

- **Root cause.** `("quick-review", "fail")` hands `planning` a branch that still
  carries `implementing`'s commit, so `gate()` at `plan-validation` runs `test_one`
  in a tree where the bug is fixed. No stage between the promotion and the gate can
  change the tree. The plan removes the commit, not the finding.
- **Decisions.** DEC-029 forbids routing a stage holding implementation commits
  through `finish_regate()`; the plan adds an `unwind` kind with its own `_finish()`
  branch and resets to triage's tip, not base -- compliant. DEC-026's `c.pop` at
  `pipeline/core/machine.py:148` stays; no counter is added. DEC-050 named this
  dispatcher-side revert as its own successor. Residual: DEC-050 carries no
  `superseded-by:` footer, so its "planning reverts by hand" paragraph still reads
  active.
- **Scope.** 7 files, all traceable. `README.md:341` and
  `.claude/skills/file-ticket/SKILL.md:158` trace to CLAUDE.md's interface rule, not
  to a criterion; both name a stage list this change falsifies.
- **Criteria.** Falsifiable. Drop the ancestor guard and
  `test_the_unwind_refuses_a_sha_that_is_not_on_the_branch` fails on a moved HEAD;
  drop `git clean -fd` and its `scratch.py` assert fails.
- **Research.** Every named anchor exists: `merge_cmd()` line 500, the
  `revalidating` block lines 654-661, `t.take_lease` line 685, `rec["meta"] = t`
  line 706, the `regate` branch in `_finish()` line 854, `re` and `shlex` imported.
  `SAFE_SHA` is new; `pipeline/daemon/supervisor.py` has no `SAFE_*` today.
- **Riskiest step.** Step 5, the `git reset --hard` on a live branch. Fallbacks
  stated: `git merge-base --is-ancestor` fails the child, a malformed
  `cheap_route_head` calls `bail()` before any child, and `## Rollback` moves a
  ticket parked at `unwinding` by hand.
- **Regressions.** `tests/test_machine.py:210,220` and `tests/test_gate.py:268`
  assert the old target; steps 4 and 7 change both. `tests/test_stages.py:68`
  subtracts `DISPATCHER_STAGES`, so no prompt is required. No other module
  enumerates stage names -- grepped `pipeline/**/*.py` for `"verifying"`, which
  matched only `pipeline/core/machine.py` and `pipeline/daemon/supervisor.py:638`.
- **Blast radius.** `class: bugfix`, 2 source files, 3 test files, 2 docs. A
  transition row plus its dispatcher branch is the minimum for this fix.

Two notes, not objections. The rewritten `tests/test_gate.py` reproduction runs
`git reset --hard` itself instead of calling `unwind_cmd()`, so it covers the
routing and the gate, not the repair; DEC-017 forbids the import, and
`tests/test_dispatch.py` covers the repair. `commit_record()` commits in the main
checkout, not the worktree, so the unwind discards no ticket record.

### 2026-08-24 12:05:26Z · plan-validation · session · session=c34760ba-87de-438e-9c56-740c12b60237

`plan-validation` ran as session `c34760ba-87de-438e-9c56-740c12b60237`
- replay: `claude --resume c34760ba-87de-438e-9c56-740c12b60237`
- log: `.project/logs/TICKET-053-plan-validation-c34760ba.log`

### 2026-08-24 12:05:26Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan review PASS on all eight items: root cause removed not masked, DEC-029/026/050/017 complied with, every named anchor verified in machine.py and supervisor.py, 7 files traceable.

### 2026-08-24 12:05:58Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 12:09:33Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-24 12:01:08Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass` fails on base `main` too -- the bug is not already fixed upstream
```
 repaired it
        d, wt = _git_ticket_project("buggy\n", "fixed\n")
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert ok, failures
E       AssertionError: ['`test_thing.py::test_broken` PASSES -- it must fail before implementation']
E       assert False

tests/test_gate.py:277: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-55ki5zlx/base
      Built pipeline @ file:///tmp/pipeline-base-55ki5zlx/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 12:09:33Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24T12:10:12Z · implementing · todo

**implementing: todo list**

- [ ] 1. `unwind_cmd()` refuses a non-ancestor sha (test_dispatch.py)
- [ ] 2. add `unwind_cmd()` to supervisor.py
- [ ] 3. record `cheap_route_head` at `implementing` spawn
- [ ] 4. `("quick-review", "fail") -> "unwinding"`, add `unwinding` rows/sets in machine.py
- [ ] 5. wire `unwinding` into `start()`/`_finish()`
- [ ] 6. dispatch-level test: promoted ticket reaches planning with fix unwound; no-head escalates
- [ ] 7. rewrite `tests/test_gate.py` reproduction
- [ ] 8. update README.md and SKILL.md
- [ ] 9. full suite + guard script, commit

### 2026-08-24T12:19:00Z · implementing · report

**implementing: all 9 plan steps done, 6 commits.**

- Added `SAFE_SHA` and `unwind_cmd()` to `pipeline/daemon/supervisor.py`: refuses a sha
  that is not an ancestor of HEAD, else `git reset --hard <sha> && git clean -fd`.
  Covered by `test_the_unwind_refuses_a_sha_that_is_not_on_the_branch`.
- `start()` records `t.extra["cheap_route_head"]` at the cheap route's `implementing`
  spawn, guarded by `not t.extra.get(...)`. Covered by
  `test_the_cheap_routes_branch_tip_is_recorded_before_the_fix_is_written`.
- `pipeline/core/machine.py`: `("quick-review", "fail") -> "unwinding"`,
  `("unwinding", "ok") -> "planning"`, `("unwinding", "fail") -> "escalated"`.
  `"unwinding"` added to `KNOWN_STAGES` and `DISPATCHER_STAGES`. No
  `pipeline/stages/unwinding.md` created.
- `start()`/`_finish()` wired: `stage == "unwinding"` bails if `cheap_route_head` fails
  `SAFE_SHA`, else spawns `unwind_cmd()` as kind `"unwind"`; `_finish()` routes
  `"unwind"` through `finish_child()`. Covered by
  `test_a_promoted_cheap_route_ticket_reaches_planning_with_its_fix_unwound` and
  `test_an_unwind_with_no_recorded_head_escalates_instead_of_guessing`.
- Rewrote `tests/test_gate.py::test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass`
  with a local `_cheap_route_project()` helper (no new import, DEC-017); it asserts the
  `transition()` path through `unwinding` and that `gate()` passes once the branch is
  reset to triage's commit.
- Updated `README.md` (diagram + point 4) and `.claude/skills/file-ticket/SKILL.md`.
- `uv run --group dev pytest -q`: 287 passed. `./pipeline/hooks/test_dangerous_commands.py`:
  all passed.

Every new function's test was verified RED for the expected reason (AttributeError,
KeyError, or the stage falling through to `pipeline/stages/unwinding.md` not existing)
before the implementing edit, then GREEN. Commits: 9bb7a5e, 247e217, ea45b2b, e834c3e,
91c3db5, d0a6335.

### 2026-08-24 12:16:18Z · implementing · session · session=d1ece555-e86a-461d-9be9-123bf97ba09c

`implementing` ran as session `d1ece555-e86a-461d-9be9-123bf97ba09c`
- replay: `claude --resume d1ece555-e86a-461d-9be9-123bf97ba09c`
- log: `.project/logs/TICKET-053-implementing-d1ece555.log`

### 2026-08-24 12:16:18Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added the unwinding dispatcher stage: unwind_cmd() resets a promoted cheap-route branch to its recorded triage tip, machine.py routes (quick-review, fail) through it to planning, start()/_finish() wire it, and the ticket's reproduction now passes. Full suite (287) and the guard script pass.

### 2026-08-24 · review · verdict=PASS

**Code review: PASS.** No blocking findings. Delta reviewed: `main...HEAD`, 7 commits
(b27c668..d0a6335), 7 files, +265/-12. This is the first review pass, so the delta is
the whole branch.

Verified against the acceptance criteria, fresh output:
- `uv run --group dev pytest -q`: `287 passed in 12.78s`.
- The five named tests, run alone: `5 passed, 40 deselected in 0.22s`.
- `./pipeline/hooks/test_dangerous_commands.py`: not run. The guard blocked it --
  "`test_dangerous_commands.py` is not on the read-only allowlist". No hook file is
  in the delta.

Two candidate findings were refuted and dropped. `t.extra["cheap_route_head"]` survives
`_finish()`: `rec["meta"]` is the same `t` the recording block mutated
(`pipeline/daemon/supervisor.py:716-728`) and `Ticket.save()` writes `extra` into
frontmatter (`pipeline/core/ticket.py:544`). The new
`from pipeline.core.machine import transition` in `tests/test_gate.py` does not break
DEC-017: `transition` exists on base (`git show main:pipeline/core/machine.py`, line 80),
so the copy the gate imports on base collects.

Findings, none blocking:

1. minor: the README diagram does not line up. `README.md:15` ends its `+` at column 53,
   `README.md:16` puts `|` at column 55, and `README.md:17`'s `<-------------+` ends at
   column 43, so the arrow points at nothing.
2. minor: `.project/decisions/DEC-050.md` still reads active and still says `planning`
   reverts the cheap route's commit by hand. The plan review named this carry-over; the
   delta touches no decisions file.
3. minor, out of scope: `("implementing", "blocked")` with `cheap_route` still returns
   `planning` directly (`pipeline/core/machine.py:152-157`), so a blocked chore that
   committed partial work reaches `planning` with commits on the branch. This ticket did
   not change that row.

### 2026-08-24 12:45:24Z · review · session · session=5bb52ccd-ad9d-4e3b-aa08-833b8f5ea618

`review` ran as session `5bb52ccd-ad9d-4e3b-aa08-833b8f5ea618`
- replay: `claude --resume 5bb52ccd-ad9d-4e3b-aa08-833b8f5ea618`
- log: `.project/logs/TICKET-053-review-5bb52ccd.log`

### 2026-08-24 12:45:24Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Review PASS: the unwinding stage matches the plan and the acceptance criteria; 287 passed, 5 named tests passed; 3 minor findings, none blocking

### 2026-08-24 12:46:03Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/core/machine.py:transition`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-053` lands it; `pipeline resume TICKET-053 --stage planning` sends it back.

### 2026-08-24 12:58:09Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 12:58:10Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/053


Rebasing (1/7)Rebasing (2/7)Rebasing (3/7)Rebasing (4/7)Rebasing (5/7)Rebasing (6/7)Rebasing (7/7)Successfully rebased and updated refs/heads/ticket/053.
Already up to date.
Updating eaff6ae..053bdbd
Fast-forward
 .claude/skills/file-ticket/SKILL.md |   4 +-
 README.md                           |  12 ++--
 pipeline/core/machine.py            |  21 ++++--
 pipeline/daemon/supervisor.py       |  45 +++++++++++++
 tests/test_dispatch.py              | 125 ++++++++++++++++++++++++++++++++++++
 tests/test_gate.py                  |  60 +++++++++++++++++
 tests/test_machine.py               |  10 ++-
 7 files changed, 265 insertions(+), 12 deletions(-)

```

### 2026-08-24 12:58:10Z · merging · decision

decision recorded as `DEC-053`
