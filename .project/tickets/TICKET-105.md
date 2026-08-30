---
id: TICKET-105
stage: done
class: bugfix
branch: ticket/105
test_file: tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim
files_declared:
- CLAUDE.md
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 14
  plan_files: 3
  no_result: 0
  structural_gate_failures: 1
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 44ac20c1-0358-41c9-8f93-c2dd216eb4b6
  log: .project/logs/TICKET-105-review-44ac20c1.log
  cost_usd: 1.9768590000000001
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). It takes the bounded shape the ticket preferred: merging
  waits behind a parked ticket whose files_declared overlap, rather than parked tickets
  holding claims for as long as a human is away, and it reports the wait through the
  existing waiting key. It also fixes a second failure triage found while reproducing,
  and a worse one: git rebase silently skips a branch commit whose patch is already
  on base, so the merge reported success with none of the ticket''s history landed
  -- steps 9-13 compare git rev-list --count before and after and restore the pre-rebase
  tip, and the guard no-ops when the rebase aborted on a conflict because the tip
  is already restored. Step 8 is the over-blocking guard: a parked ticket sharing
  no file must delay no merge, and it passes before and after, so its value is that
  a later widening of parked_meta breaks it. parked_meta reads every ticket off disk
  but only at merging. Nothing fenced.'
approved_at: '2026-08-30T13:47:22.727379+00:00'
---

## Summary

**Implemented and reviewed; no blocking finding.** All 14 plan steps done, four
commits: `db5367d` (parked-ticket merge hold in `start()` + `parked_meta()`),
`b5e2e31` (over-blocking guard test), `b359ecd` (`merge_cmd()`'s
`rev-list --count` rebase guard), `dafd42d` (CLAUDE.md).

Review re-ran every acceptance criterion on `dafd42d` and all pass:
`519 passed in 36.81s`, `2 passed, 39 deselected` for `-k files_conflict`, and
both `git grep` checks exit 0. The delta touches only
`pipeline/daemon/supervisor.py`, `tests/test_dispatch.py` and `CLAUDE.md`;
`pipeline/core/machine.py` is untouched and `conflict_holder()` keeps its
signature, as `## Digest` required.

Review appended three non-blocking findings and dropped three charges it could
refute. Nothing needs a fix before merge. Details in `## Thread`'s
`review · findings` entry; the full verification list is in the
`implementing · report` entry above it.

The original report follows.

`files_conflict` exists to stop two tickets editing one file at once. It sees
only the tickets currently running:

    # pipeline/core/machine.py:310-314
    def conflict_holder(meta: dict, inflight_meta: list[dict]) -> tuple[str, str] | None:
        """The first inflight ticket that overlaps `meta`'s `files_declared`..."""
        mine = set(meta.get("files_declared") or [])

and `start()` passes exactly the in-flight records:

    # pipeline/daemon/supervisor.py:807-808
    held = conflict_holder(t.frontmatter(),
                           [r["meta"].frontmatter() for r in inflight.values()])

A ticket parked at `needs-input`, `awaiting-approval` or `awaiting-merge` is
not in `inflight`, so its `files_declared` protects nothing while it waits for
a human. Another ticket declaring the same files runs and merges. The parked
branch can then no longer rebase, and `("revalidating", "conflict")` discards
its commits and sends it back to `triage`.

Observed on this repo, 2026-08-30, from TICKET-101's own thread:

    11:24  TICKET-101 parks at needs-input
           its branch carries cmd_decisions in pipeline/cli/main.py
    ~12:0x TICKET-100 runs and merges: "add pipeline new --depends-on"
           same file, and the same tests/test_cli.py
    12:29  TICKET-101 approved -> revalidating
    12:29  revalidating -> triage, result=conflict, rebase_conflicts: 1
           three commits discarded, branch recut from main
    12:47  back at awaiting-approval after a fresh triage and two planning runs

Both tickets declared `pipeline/cli/main.py` and `tests/test_cli.py`. Ordering
them was the whole job of `files_conflict`, and it was blind to the one that
was parked. The work survived only because the discarded commits stayed
reachable by SHA; nothing in the pipeline offered them back.

The cost is paid twice over: the human gate is where a ticket waits longest
(this one sat over an hour), so the window where its claim is ignored is the
widest window it has.

Expected: a ticket parked at a human gate keeps the ordering guarantee it had
while running. Two shapes, and the plan should say which and why:

- Include parked tickets in the conflict check, so a ticket whose files
  overlap a parked one waits instead of running. Simple, but a ticket parked
  for a week blocks its files for a week -- and `awaiting-merge` for a fenced
  diff can park indefinitely.
- Leave claiming alone and re-check at the point of damage: `merging` reads
  the parked tickets' `files_declared` before it lands, and waits behind them.
  A merge is short and already serialised (`start()` waits for one at a time),
  so the block is bounded by a merge rather than by a human.

Falsifiable: two tickets declaring one file, the first parked at
`awaiting-approval` with commits on its branch; the second must not be able to
land changes to that file while the first waits, and the first must still
rebase cleanly when a human approves it. And the existing behaviour must hold:
a ticket parked at a gate whose files overlap nothing must delay no one.

Constraints from the code: `conflict_holder()` and `files_conflict()` are pure
and take the list they compare against, so the shape of the fix is which list
is passed, not new logic in `machine.py`; `HUMAN_GATES` already names the
parked stages; and `note_wait()` (`pipeline/daemon/supervisor.py:687`) is how
a wait is reported to `ls`, which should say a parked ticket is what is
holding a file, or an operator sees a stall with no cause.

Not in scope: recovering commits a past conflict already discarded. That
happened here and is worth its own ticket if it recurs -- this one is about
not reaching that state.

## Reproduction

`tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim`

Run: `uv run --group dev pytest -q tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim`

TICKET-001 sits at `merging` (the tail of a human gate) with a committed
change to `thing.py` on its branch. A second, unrelated commit lands the
identical change directly on `main` first -- exactly what `files_conflict()`
misses, since a parked ticket is never in `inflight`. `start()` then runs
TICKET-001's `merging` stage: `merge_cmd()`'s `git rebase base` step finds
TICKET-001's patch is now a no-op and silently drops it (git's default
`--empty=drop`), and the following `git merge --ff-only` lands a branch with
none of TICKET-001's own commit on it.

expect: TICKET-001's own commit did not land on base -- the rebase step in merge_cmd() silently dropped it as an empty/no-op patch because an unrelated ticket landed the identical change while TICKET-001 sat at a human gate.

## Digest

- Files touched: `pipeline/daemon/supervisor.py` (the fix), `tests/test_dispatch.py` (two new tests), `CLAUDE.md` (two gotcha bullets). `pipeline/core/machine.py` is NOT touched: `conflict_holder()` stays pure and keeps its signature.
- Entry point: `start()` in `pipeline/daemon/supervisor.py:806-810` computes `held = conflict_holder(t.frontmatter(), [r["meta"].frontmatter() for r in inflight.values()])`, calls `note_wait()` exactly once, then returns `(False, None)` when `held` is set.
- Second entry point: `merge_cmd()` in `pipeline/daemon/supervisor.py:638-665` builds the merge script. Its first line today is `git rebase {base} || git rebase --abort 2>/dev/null`.
- `parked_meta()` is the one new function. It mirrors `dep_graph()` (`pipeline/daemon/supervisor.py:687`): iterate `all_tickets(project)`, `Ticket.load(p)` inside a `try/except PipelineError: continue`. Both names are already imported in that module.
- `HUMAN_GATES = {"awaiting-approval", "needs-input", "awaiting-merge"}` (`pipeline/core/machine.py:38`), already imported by `pipeline/daemon/supervisor.py:27`.
- `waiting_text()` (`pipeline/daemon/server.py:89`) already renders `{on, file}` as `waiting on TICKET-001 (thing.py)`. The parked hold reuses that shape, so no rendering change is needed.
- Gotcha: `tests/test_dispatch.py::test_a_ticket_held_at_merging_is_rebased_before_the_merge_is_attempted` asserts `"rebase" in log_text.splitlines()[0]`, and `spawn_command()` writes `$ {cmd}` as the log's first line. Any new first line in `merge_cmd()` must still contain the word `rebase`.
- Gotcha: `note_wait()` writes the ticket only when the reason changes, because `ticket_rows()` derives `stale` from the file's mtime. Two `note_wait()` calls in one tick -- one clearing, one setting -- would write every tick and hide a stuck ticket forever. The parked check must fold into the existing single call.
- Measured in a scratch git repo on 2026-08-30: branch commit `571e365` adds `thing.py`, base then gains an identical `thing.py`. `git rebase main` printed `warning: skipped previously applied commit 571e365` and `git rev-list --count main..HEAD` went from `1` to `0`. After `git reset --hard 571e365` and `git merge --no-edit main`, `git merge --ff-only ticket/001` on main left `571e365` in `git log main --format=%H`.
- Gotcha: the reproduction test holds only ONE ticket file. The conflicting change lands as a bare commit on `main`, which no `files_declared` covers. Ordering parked tickets cannot make that test pass; the rebase guard is what does.
- Baseline suite on `4676139`: `uv run --group dev pytest -q` printed `1 failed, 512 passed in 37.88s`, and the one failure is this ticket's own `test_a_ticket_parked_at_a_human_gate_holds_no_file_claim`.
- Fence check: `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py` and `CLAUDE.md` are not in `machine.FENCED`, so this ticket does not park at `awaiting-merge` for the fence.
- `pipeline/templates/skills/file-ticket/SKILL.md:79` says `files_conflict` orders tickets by the files they touch. That stays true and needs no edit: no CLI command, no human gate and no filing rule changes.

## Decisions checked

- DEC-029 (active) -- "Ordering across a human gate would need `files_conflict` to read every non-terminal ticket, which serialises tickets for as long as a human takes to approve. That is a different change, and this plan does not make it." This plan complies rather than supersedes: `conflict_holder()`'s `inflight` argument is unchanged, and the parked list is read only in `start()`'s `merging` branch, so triage through verifying still run beside a parked overlap.
- DEC-100 (active) -- the dependency check reads ticket files, not `inflight`, and must NOT be folded into `conflict_holder()`. Complied with: `parked_meta()` is a separate reader in `pipeline/daemon/supervisor.py`, and `conflict_holder()` stays pure.
- DEC-048 (active) -- `waiting` is advisory, written by `start()` only when the reason changes. Complied with: one `note_wait()` call per tick, the parked holder folded into the existing `held` value.
- DEC-045 (active) -- the catch-up rebase belongs at `merging`, because merges are serialised there. Complied with: the rebase stays first, and the guard restores the pre-rebase tip only when the rebase dropped a commit.
- DEC-011 (active) -- the event vocabulary is frozen. This change emits no new event kind and adds no socket op.
- grep terms used against `.project/decisions/`: `files_conflict`, `conflict_holder`, `files_declared`, `merging`, `HUMAN_GATES`, `note_wait`, `waiting`.

## Plan

1. Add `test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate` to `tests/test_dispatch.py`: build `d = project()`, set TICKET-001 to `awaiting-approval` with `t1 = Ticket.find(d, "TICKET-001"); t1.stage = "awaiting-approval"; t1.save()`, write `d / ".project/tickets/TICKET-002.md"` as `FIXTURE.replace("id: TICKET-001", "id: TICKET-002").replace("branch: ticket/001", "branch: ticket/002").replace("stage: plan-validation", "stage: merging")`, call `supervisor.start(d, d / ".project/tickets/TICKET-002.md", harness("fake"), {})`, and assert it returns `(False, None)` and that `Ticket.find(d, "TICKET-002").extra["waiting"]` has `on == "TICKET-001"` and `file == "thing.py"`.
2. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate` and watch it fail: `start()` spawns a merge child instead of returning `(False, None)`, so the assert on the return value fires first.
3. Add `parked_meta(project: Path, tid: str) -> list[dict]` to `pipeline/daemon/supervisor.py` immediately below `dep_graph()`, returning `o.frontmatter()` for every `Ticket.load(p)` over `all_tickets(project)` where `o.id != tid and o.stage in HUMAN_GATES`, skipping a `PipelineError` with `continue`; its docstring states that a parked ticket holds no `inflight` record (DEC-029) and that this list is read only at `merging`.
4. In `start()` in `pipeline/daemon/supervisor.py`, insert `if held is None and stage == "merging": held = conflict_holder(t.frontmatter(), parked_meta(project, tid))` between the existing `held = conflict_holder(...)` assignment and the existing `note_wait(t, {"on": held[0], "file": held[1]} if held else None)` line, leaving that `note_wait()` call and the `return False, None` below it unchanged.
5. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate` and confirm it passes, then run `uv run --group dev pytest -q tests/test_daemon.py -k files_conflict` and confirm it reports no failure.
6. Commit steps 1, 3 and 4 in `tests/test_dispatch.py` and `pipeline/daemon/supervisor.py` as `fix(TICKET-105): a merge waits behind a ticket parked at a human gate`.
7. Add `test_a_merge_is_not_held_by_a_parked_ticket_that_shares_no_file` to `tests/test_dispatch.py`: `d, sh = git_project()`, write `d / ".project/tickets/TICKET-001.md"` as `FIXTURE` with `stage: awaiting-approval` and `files_declared: [other.py]`, write `d / ".project/tickets/TICKET-002.md"` as `FIXTURE` with `id: TICKET-002`, `branch: ticket/002`, `stage: merging` and `files_declared: [thing.py]`, build its worktree with `supervisor.ensure_worktree(d, {"id": "TICKET-002", "branch": "ticket/002"}, {"base": "main"})`, write a `thing.py` there and `_commit(wt, "'TICKET-002: the fix'")`, then assert `supervisor.start(d, d / ".project/tickets/TICKET-002.md", harness("fake"), {})` returns `did` true with `rec["kind"] == "merge"`, and close with `rec["proc"].wait()`, `supervisor.finish(d, rec)` and `shutil.rmtree(d, ignore_errors=True)`.
8. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_merge_is_not_held_by_a_parked_ticket_that_shares_no_file` and confirm it passes on its first run -- it guards against over-blocking, so it passes both before and after step 4, and its value is that a later widening of `parked_meta()` breaks it; commit it in `tests/test_dispatch.py` as `test(TICKET-105): a parked ticket sharing no file delays no merge`.
9. Change the first two lines of the string `merge_cmd()` returns in `pipeline/daemon/supervisor.py` to `pre=$(git rev-parse HEAD); n=$(git rev-list --count {base}..HEAD); git rebase {base} || git rebase --abort 2>/dev/null` followed by `[ "$(git rev-list --count {base}..HEAD)" -ge "$n" ] || {{ echo "rebase dropped a commit already on {base} -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }}`, leaving the `git merge --no-edit {base} || exit 1` line and the three lines after it byte-identical.
10. Extend `merge_cmd()`'s docstring in `pipeline/daemon/supervisor.py` with three facts: `git rebase` skips a branch commit whose patch is already on base and prints `warning: skipped previously applied commit <sha>`; that is what a ticket parked at a human gate gets when another change lands the same content, and the merge then reports success with none of the ticket's own history landed; the count guard restores the pre-rebase tip so `git merge --no-edit <base>` lands the original commit as a merge commit instead.
11. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` and confirm it now passes.
12. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_ticket_held_at_merging_is_rebased_before_the_merge_is_attempted` and confirm it still passes, which proves the new first line of `merge_cmd()` still runs a rebase.
13. Run `uv run --group dev pytest -q` and confirm it reports no failure at all, against the measured baseline of one failure on `4676139`; then commit steps 9 and 10 in `pipeline/daemon/supervisor.py` as `fix(TICKET-105): the merge rebase never drops the branch's own commit`.
14. Extend two bullets in `CLAUDE.md`: the `Only one merge runs at a time` bullet gains that `start()` also holds a `merging` ticket behind any ticket parked at a `HUMAN_GATES` stage whose `files_declared` overlap, reported through the same `waiting` key; the `merging` rebases before it merges bullet gains that a `git rev-list --count` comparison guards the rebase and restores the pre-rebase tip rather than let a skipped commit vanish. Commit as `docs(TICKET-105): record the parked-ticket merge hold and the rebase guard`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` exits 0.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate` exits 0.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_merge_is_not_held_by_a_parked_ticket_that_shares_no_file` exits 0, which is the
  existing behaviour the ticket asks to keep: a parked ticket overlapping nothing delays no one.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_ticket_held_at_merging_is_rebased_before_the_merge_is_attempted` exits 0, proving
  `merge_cmd()`'s first line still runs a rebase.
- `uv run --group dev pytest -q tests/test_daemon.py -k files_conflict` exits 0, proving the `inflight` overlap path and its `waiting` row are unchanged.
- `uv run --group dev pytest -q 2>&1 | tail -1` prints a summary line containing no `failed`. Re-measure the baseline by running the same
  command on `4676139`: it names this ticket's reproduction test as the only failure, so this change must leave no failure at all.
- `git grep -n parked_meta -- pipeline/daemon/supervisor.py` exits 0 and prints both the definition and the call inside `start()`.
- `git grep -n 'rev-list --count' -- pipeline/daemon/supervisor.py` exits 0, showing the rebase guard is in `merge_cmd()`.

## Decisions

**A ticket at `merging` waits behind a ticket parked at a human gate; `conflict_holder()`'s `inflight` list is unchanged.** DEC-029 refused to widen `files_conflict` to every non-terminal ticket, because that serialises work for as long as a human takes. This does not widen it: `start()` reads `parked_meta()` only in the `merging` branch, so an overlapping ticket still runs triage through verifying in parallel and only its landing is ordered. The cost is real and accepted: a ticket at `merging` can now wait on a human, and a fenced diff parked at `awaiting-merge` can hold an overlapping merge indefinitely. `note_wait()` names the holder, so `ls` shows `waiting on TICKET-xxx (file.py)` instead of a silent stall. Do not move this check up beside the `inflight` one -- that is the change DEC-029 declined.

**The parked check folds into `start()`'s existing single `note_wait()` call.** A second call would clear `waiting` and re-set it in the same tick. `ticket_rows()` computes `stale` from the ticket file's mtime (DEC-048), so a write every tick hides a stuck ticket forever.

**`merge_cmd()`'s rebase must never reduce the branch's own commit count.** `git rebase` skips a commit whose patch is already upstream (`warning: skipped previously applied commit <sha>`) and drops one that replays empty. Either discards the ticket's work while the merge still reports success and the ticket reaches `done`. The `git rev-list --count` guard restores the pre-rebase tip and lets `git merge --no-edit <base>` land the original commit as a merge commit. Linear history (DEC-045) is the goal, not a rule that outranks keeping the commit: do not delete the guard to get a linear merge back.

**Ordering parked tickets alone cannot satisfy the reproduction, and that is why both halves ship.** The identical change can land as a bare commit on base that no ticket declares, so `files_declared` cannot see it. `files_declared` orders only what the pipeline itself lands; the rebase guard covers everything else.

## Rollback

Revert the four commits from steps 6, 8, 13 and 14, newest first. The two halves are independent. Reverting only the `merge_cmd()` commit restores `git rebase {base} || git rebase --abort 2>/dev/null` as the first line and returns `test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` to failing, while the parked hold keeps working. Reverting only the `start()` and `parked_meta()` commit removes the hold and leaves every merge unordered against parked tickets again. Nothing here writes frontmatter, changes an event kind or migrates a file, so a revert needs no cleanup on tickets that ran under it: a stale `waiting` key is advisory and the next tick overwrites it.

## Thread

### 2026-08-30 13:29:04Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-30 · triage · transition · to=triage · result=ok

**triage -> triage** (result: `ok`)

Reproduced via `merging`'s rebase step, a second path to the same symptom
alongside the `revalidating`-conflict path the summary describes: a ticket
parked at a human gate has no entry in `inflight`, so `conflict_holder()`
never sees it, and a same-content commit landed on base first turns the
parked ticket's own commit into a no-op that `git rebase` drops silently.
Committed `tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim`
on `ticket/105` (commit 4676139). This needs a design decision between the
two fix shapes the summary lists, so it is not a `chore`.

### 2026-08-30 13:31:26Z · triage · session · session=dcc8669d-ab86-4a9d-8fcb-6dab91ab2f50

`triage` ran as session `dcc8669d-ab86-4a9d-8fcb-6dab91ab2f50`
- replay: `claude --resume dcc8669d-ab86-4a9d-8fcb-6dab91ab2f50`
- log: `.project/logs/TICKET-105-triage-dcc8669d.log`
- cost: $0.54 of a $3 cap
- tokens: 10,013 out (3,890 thinking) · 52 in · 1,220,211 cache read · 49,142 cache write

### 2026-08-30 13:31:26Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- rebase in merge_cmd() drops a parked ticket's commit as a no-op patch when a same-change ticket lands first

### 2026-08-30 · planning · note

Chose the second fix shape: `merging` reads the parked tickets' `files_declared` and waits behind them. `conflict_holder()` keeps its `inflight` argument, which is what DEC-029 declined to widen, and a ticket still runs triage through verifying beside a parked overlap.

The plan ships a second change the ticket did not name, because neither fix shape satisfies the reproduction on its own. `tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` holds ONE ticket file; the conflicting change lands as a bare commit on `main`, which no `files_declared` covers. So `merge_cmd()` also guards its rebase with a commit count. Verified in a scratch repo: `git rebase main` printed `warning: skipped previously applied commit 571e365` and `git rev-list --count main..HEAD` went `1` to `0`; after `git reset --hard 571e365` and `git merge --no-edit main`, `git merge --ff-only ticket/001` left `571e365` in `git log main --format=%H`.

Baseline `uv run --group dev pytest -q` on `4676139`: `1 failed, 512 passed in 37.88s`, the failure being the reproduction test.

Out of scope, noted not fixed: `start()`'s merge serialisation returns without calling `note_wait()`, so a ticket held by another ticket's merge shows no reason in `ls`.

### 2026-08-30 13:40:23Z · planning · session · session=381eddc7-db2f-4e52-98e7-3969e2c44741

`planning` ran as session `381eddc7-db2f-4e52-98e7-3969e2c44741`
- replay: `claude --resume 381eddc7-db2f-4e52-98e7-3969e2c44741`
- log: `.project/logs/TICKET-105-planning-381eddc7.log`
- cost: $3.09 of a $10 cap
- tokens: 39,786 out (20,449 thinking) · 60 in · 2,112,704 cache read · 103,483 cache write

### 2026-08-30 13:40:23Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: `merging` waits behind parked tickets, and merge_cmd()'s rebase never drops the branch's own commit

### 2026-08-30 13:41:15Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` fails as required
```
t did not land on base -- the rebase step in merge_cmd() silently dropped it as an empty/no-op patch because an unrelated ticket landed the identical change while TICKET-001 sat at a human gate. git log main --format=%H returned: 'e2244aebef0a60c97600b31d9ea5f2cbe781a949\nd9b7bab336a76bc71bd6a7ded373b517d7722ebf\nd1c81e4fa87b486e8810ff2049512fba0f12727d\n'
E       assert '8c16af71ca46b86e15df9e79e3326e985d835999' in 'e2244aebef0a60c97600b31d9ea5f2cbe781a949\nd9b7bab336a76bc71bd6a7ded373b517d7722ebf\nd1c81e4fa87b486e8810ff2049512fba0f12727d\n'

tests/test_dispatch.py:1479: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: merging (script) pid 1394108 -> TICKET-001-merging-54a44052.log
  TICKET-001: -> done {'plan_steps': 1, 'plan_files': 1}
  TICKET-001: recorded the finished ticket on `main`
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================

```
- ok: `tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` fails on base `main` too -- the bug is not already fixed upstream
```
96\n'

tests/test_dispatch.py:1479: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: merging (script) pid 1395048 -> TICKET-001-merging-ae2c0f83.log
  TICKET-001: -> done {'plan_steps': 1, 'plan_files': 1}
  TICKET-001: recorded the finished ticket on `main`
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.79s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-08ptzg65/base
      Built pipeline @ file:///tmp/pipeline-base-08ptzg65/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 27ms

```
- acceptance criterion pins an absolute count copied from `## Digest` (512): - `uv run --group dev pytest -q` reports no failure. The baseline measured on `4676139` was `1 failed, 512 passed`, and that one failure is this ticket's own reproduction test. -- a total any other ticket can move is not a property of this change -- state it as a relation to a measured baseline, or re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check

### 2026-08-30 13:41:15Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion pins an absolute count copied from `## Digest` (512): - `uv run --group dev pytest -q` reports no failure. The baseline measured on `4676139` was `1 failed, 512 passed`, and that one failure is this ticket's own reproduction test. -- a total any other ticket can move is not a property of this change -- state it as a relation to a measured baseline, or re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check

### 2026-08-30 · planning · note

The Tier A gate failed on one finding: an acceptance criterion pinned `1 failed, 512 passed`, a total any other ticket can move. That criterion is the only thing this run changed. It now reads: `uv run --group dev pytest -q 2>&1 | tail -1` prints a summary line containing no `failed`, and the baseline is re-measured on `4676139` at check time instead of copied out of `## Digest`.

`## Digest`, `## Decisions checked`, the 14 plan steps, `## Decisions` and `## Rollback` are unchanged, and so are the other seven criteria. The gate's other two checks passed: `tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` fails on the branch and on base `main`.

Verified `.project/decisions/` holds every id this plan cites: DEC-011, DEC-029, DEC-045, DEC-048, DEC-100.

The 512 count stays in `## Digest`, where it is a measurement carrying its commit sha, not a criterion.

### 2026-08-30 13:43:12Z · planning · session · session=2e7b23da-d90f-4214-bb41-bb1357465aed

`planning` ran as session `2e7b23da-d90f-4214-bb41-bb1357465aed`
- replay: `claude --resume 2e7b23da-d90f-4214-bb41-bb1357465aed`
- log: `.project/logs/TICKET-105-planning-2e7b23da.log`
- cost: $0.99 of a $10 cap
- tokens: 8,285 out (3,540 thinking) · 28 in · 593,289 cache read · 48,213 cache write

### 2026-08-30 13:43:12Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan kept; the suite acceptance criterion now re-measures the baseline instead of pinning 512 passed

### 2026-08-30 13:43:50Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` fails as required
```
t did not land on base -- the rebase step in merge_cmd() silently dropped it as an empty/no-op patch because an unrelated ticket landed the identical change while TICKET-001 sat at a human gate. git log main --format=%H returned: 'e037948c933611f6a5111be1f92891c7e944172b\nebdff0ad23352c0811489fe65401468f6fe06c72\n531b3957613f66176784922f1787ba3ab5e213f2\n'
E       assert '9e65638a7d01ecd8ce555a6ddb1d5a28361b17b7' in 'e037948c933611f6a5111be1f92891c7e944172b\nebdff0ad23352c0811489fe65401468f6fe06c72\n531b3957613f66176784922f1787ba3ab5e213f2\n'

tests/test_dispatch.py:1479: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: merging (script) pid 1442158 -> TICKET-001-merging-710a74f6.log
  TICKET-001: -> done {'plan_steps': 1, 'plan_files': 1}
  TICKET-001: recorded the finished ticket on `main`
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.19s ===============================

```
- ok: `tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` fails on base `main` too -- the bug is not already fixed upstream
```
b2\n'

tests/test_dispatch.py:1479: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: merging (script) pid 1442250 -> TICKET-001-merging-bf4d6ae2.log
  TICKET-001: -> done {'plan_steps': 1, 'plan_files': 1}
  TICKET-001: recorded the finished ticket on `main`
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.50s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-1depohw7/base
      Built pipeline @ file:///tmp/pipeline-base-1depohw7/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 13ms

```

### 2026-08-30 · plan-validation · note

**Tier B: PASS.** Every item scored against the code at `4676139`.

- root cause: two defects. `conflict_holder()` reads `inflight` only (`pipeline/daemon/supervisor.py:807-808`), so a parked ticket's `files_declared` claim binds nothing. `merge_cmd()`'s `git rebase {base}` (line 660) drops the branch's own commit when its patch is already on base, and the merge still reports success. The plan fixes both causes, not the assertion.
- decision conflict: none. `conflict_holder()` keeps its signature, so DEC-100 and DEC-029's refusal to widen `files_conflict` both hold; step 4 reads parked tickets in the `merging` branch alone. Step 4 inserts above the single `note_wait()` at line 809, so DEC-048 holds. The guard makes a dropped-commit merge non-linear, and `## Decisions` states that DEC-045 supersession with its reason.
- scope: 3 files, one new function, one two-line branch, two shell lines. Every step traces to a criterion. Fits `bugfix`.
- falsifiable: criterion 2's test fails without step 4 -- `start()` spawns a merge child instead of returning `(False, None)`. Criterion 3 passes before and after; step 8 says so and states its value.
- no research left: `git_project`, `_commit`, `harness`, `Ticket.find` and `FIXTURE` (`files_declared: [thing.py]`) all exist as cited.
- riskiest step: 9, the `merge_cmd()` shell. Fallback: `## Rollback` reverts that commit alone; step 12 guards the first-line `rebase` assertion.
- regression surface: `tests/test_daemon.py:552-582` covers the `inflight` path, `test_a_ticket_held_at_merging_is_rebased_before_the_merge_is_attempted` covers the log's first line, criterion 6 covers the rest.

unverified: I ran no command. Every finding rests on reading `pipeline/daemon/supervisor.py`, `pipeline/core/machine.py` and `tests/`. I would have run the two new pytest node ids from criteria 2 and 3.

### 2026-08-30 13:46:25Z · plan-validation · session · session=a44dec49-bbc5-42f8-915d-acd5b7e275ef

`plan-validation` ran as session `a44dec49-bbc5-42f8-915d-acd5b7e275ef`
- replay: `claude --resume a44dec49-bbc5-42f8-915d-acd5b7e275ef`
- log: `.project/logs/TICKET-105-plan-validation-a44dec49.log`
- cost: $1.21 of a $3 cap
- tokens: 11,772 out (5,011 thinking) · 32 in · 726,409 cache read · 55,062 cache write

### 2026-08-30 13:46:25Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes every judgment item: both halves trace to criteria, DEC-029/045/048/100 complied with, 3-file blast radius fits bugfix

### 2026-08-30 13:47:22Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). It takes the bounded shape the ticket preferred: merging waits behind a parked ticket whose files_declared overlap, rather than parked tickets holding claims for as long as a human is away, and it reports the wait through the existing waiting key. It also fixes a second failure triage found while reproducing, and a worse one: git rebase silently skips a branch commit whose patch is already on base, so the merge reported success with none of the ticket's history landed -- steps 9-13 compare git rev-list --count before and after and restore the pre-rebase tip, and the guard no-ops when the rebase aborted on a conflict because the tip is already restored. Step 8 is the over-blocking guard: a parked ticket sharing no file must delay no merge, and it passes before and after, so its value is that a later widening of parked_meta breaks it. parked_meta reads every ticket off disk but only at merging. Nothing fenced.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). It takes the bounded shape the ticket preferred: merging waits behind a parked ticket whose files_declared overlap, rather than parked tickets holding claims for as long as a human is away, and it reports the wait through the existing waiting key. It also fixes a second failure triage found while reproducing, and a worse one: git rebase silently skips a branch commit whose patch is already on base, so the merge reported success with none of the ticket's history landed -- steps 9-13 compare git rev-list --count before and after and restore the pre-rebase tip, and the guard no-ops when the rebase aborted on a conflict because the tip is already restored. Step 8 is the over-blocking guard: a parked ticket sharing no file must delay no merge, and it passes before and after, so its value is that a later widening of parked_meta breaks it. parked_meta reads every ticket off disk but only at merging. Nothing fenced.**

### 2026-08-30 13:48:08Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` fails as required
```
t did not land on base -- the rebase step in merge_cmd() silently dropped it as an empty/no-op patch because an unrelated ticket landed the identical change while TICKET-001 sat at a human gate. git log main --format=%H returned: '517095b419229bb7d15f436fd451a15516ccda4b\nea2b93f22d7b5734a14ecc9508dd4f5f7f995a04\nc80b27ef2e990e01a2ad161aa213400f22a6a914\n'
E       assert '8c65f205ee491863b65b4ce5aa6370bff9a06d94' in '517095b419229bb7d15f436fd451a15516ccda4b\nea2b93f22d7b5734a14ecc9508dd4f5f7f995a04\nc80b27ef2e990e01a2ad161aa213400f22a6a914\n'

tests/test_dispatch.py:1479: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: merging (script) pid 1450179 -> TICKET-001-merging-a15b7b5a.log
  TICKET-001: -> done {'plan_steps': 1, 'plan_files': 1}
  TICKET-001: recorded the finished ticket on `main`
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.37s ===============================

```
- ok: `tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` fails on base `main` too -- the bug is not already fixed upstream
```
3e\n'

tests/test_dispatch.py:1479: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: merging (script) pid 1450258 -> TICKET-001-merging-e6f1de13.log
  TICKET-001: -> done {'plan_steps': 1, 'plan_files': 1}
  TICKET-001: recorded the finished ticket on `main`
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_parked_at_a_human_gate_holds_no_file_claim
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.50s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-0y85p3rk/base
      Built pipeline @ file:///tmp/pipeline-base-0y85p3rk/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-30 13:48:08Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

### 2026-08-30 · implementing · todo

**Todo, one per plan step:**

1. [x] test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate (RED)
2. [x] confirm RED
3. [x] `parked_meta()` in supervisor.py
4. [x] wire `parked_meta()` into `start()`'s `held` check
5. [x] confirm GREEN + files_conflict tests still pass
6. [x] commit steps 1/3/4 (`db5367d`)
7. [x] test_a_merge_is_not_held_by_a_parked_ticket_that_shares_no_file
8. [x] confirm it passes, commit (`b5e2e31`)
9. [x] rev-list --count rebase guard in `merge_cmd()`
10. [x] extend `merge_cmd()` docstring
11. [x] confirm reproduction test passes
12. [x] confirm rebase-first-line test still passes
13. [x] full suite green, commit steps 9/10 (`b359ecd`)
14. [x] extend two CLAUDE.md bullets, commit (`dafd42d`)

### 2026-08-30 · implementing · report

**Plan executed as written, all 14 steps.** Four commits: `db5367d` (parked-ticket
merge hold), `b5e2e31` (over-blocking guard test), `b359ecd` (rebase
count guard), `dafd42d` (CLAUDE.md). `pipeline/core/machine.py` untouched, as
`## Digest` required.

TDD followed for both new production changes:
- `test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate` failed RED
  because `start()` returned `(True, None)` (escalated on worktree creation,
  a non-git temp dir) instead of `(False, None)` -- proof the parked check
  never ran before reaching worktree code. `parked_meta()` + the `held`
  branch in `start()` turned it GREEN.
- `test_a_merge_is_not_held_by_a_parked_ticket_that_shares_no_file` passed on
  first run, by design (`## Plan` step 8): it guards the over-blocking case
  before and after the fix.
- The ticket's own reproduction test stayed RED until the `merge_cmd()`
  `rev-list --count` guard landed.

All acceptance criteria verified:
- `test_a_ticket_parked_at_a_human_gate_holds_no_file_claim`: pass
- `test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate`: pass
- `test_a_merge_is_not_held_by_a_parked_ticket_that_shares_no_file`: pass
- `test_a_ticket_held_at_merging_is_rebased_before_the_merge_is_attempted`: pass
- `tests/test_daemon.py -k files_conflict`: 2 passed, 39 deselected
- full suite: `519 passed in 36.54s`, no failure (baseline on `4676139` was
  `1 failed, 512 passed`)
- `git grep -n parked_meta -- pipeline/daemon/supervisor.py`: definition at
  line 723, call at line 845
- `git grep -n 'rev-list --count' -- pipeline/daemon/supervisor.py`: two hits
  in `merge_cmd()`

No deviation from `## Plan`. No file touched outside `## Digest`'s three.

re-gated after rebasing onto base: passed

### 2026-08-30 13:54:33Z · implementing · session · session=4db3f2e6-e5ee-455e-9d1e-d3e54c93920f

`implementing` ran as session `4db3f2e6-e5ee-455e-9d1e-d3e54c93920f`
- replay: `claude --resume 4db3f2e6-e5ee-455e-9d1e-d3e54c93920f`
- log: `.project/logs/TICKET-105-implementing-4db3f2e6.log`
- cost: $1.33 of a $8 cap
- tokens: 18,542 out (2,692 thinking) · 124 in · 4,133,169 cache read · 78,555 cache write

### 2026-08-30 13:54:33Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented all 14 plan steps, 4 commits; full suite 519 passed, no failure

### 2026-08-30 · review · findings · result=ok

**No blocking finding.** I reviewed the delta `a180858..dafd42d` against
`## Plan` and `## Acceptance criteria`. Every criterion passes here:
`519 passed in 36.81s`, `2 passed, 39 deselected` for `-k files_conflict`, and
both `git grep` checks exit 0. No drift: the delta touches only
`pipeline/daemon/supervisor.py`, `tests/test_dispatch.py` and `CLAUDE.md`, and
`conflict_holder()` keeps its signature.

Non-blocking findings:

1. **minor** -- `merge_cmd()` (`pipeline/daemon/supervisor.py:675`) runs
   `git reset --hard "$pre"`, which discards uncommitted worktree changes when
   the operator sets `rebase.autoStash = true`: the rebase then succeeds on a
   dirty worktree instead of refusing. Git's default is `false`.
2. **minor** -- `parked_meta()` (`pipeline/daemon/supervisor.py:723`) does not
   call `o.errors()`, so a hand-edited `files_declared: 5` raises `TypeError`
   in `conflict_holder()`'s `set(...)`. `Ticket.save()` validates on the way
   out, so the pipeline cannot write that value itself. `dep_graph()` reads
   ticket files the same way.
3. **nit** -- `test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate`
   (`tests/test_dispatch.py:1488`) leaves its temp dir; 21 of the 23
   `project()` tests in that file call `shutil.rmtree`.

Three charges dropped:

- "The reset discards changes the merge was meant to land" -- `git rebase`
  refuses a dirty worktree (`pipeline/daemon/supervisor.py:650-651`), so the
  reset path and unstaged changes cannot co-occur under git's default config.
- "An empty `$n` breaks the `[ -ge ]` test and forces a reset" -- every path
  where `git rev-list --count` fails is one where the rebase also fails and
  aborts, so `$pre` is the current HEAD and the reset is a no-op.
- "A ticket parked at `needs-input` blocks an overlapping merge forever" --
  `## Decisions` states and accepts that cost, and `note_wait()` names the
  holder for `ls`.

### 2026-08-30 14:00:01Z · review · session · session=44ac20c1-0358-41c9-8f93-c2dd216eb4b6

`review` ran as session `44ac20c1-0358-41c9-8f93-c2dd216eb4b6`
- replay: `claude --resume 44ac20c1-0358-41c9-8f93-c2dd216eb4b6`
- log: `.project/logs/TICKET-105-review-44ac20c1.log`
- cost: $1.98 of a $5 cap
- tokens: 21,535 out (12,942 thinking) · 52 in · 1,478,310 cache read · 69,803 cache write

### 2026-08-30 14:00:01Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review passed: no blocking finding, 3 non-blocking appended; full suite 519 passed in 36.81s

### 2026-08-30 14:00:40Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-30 14:00:41Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/105


Current branch ticket/105 is up to date.
Already up to date.
Updating 19594f8..dafd42d
Fast-forward
 CLAUDE.md                     | 12 +++++-
 pipeline/daemon/supervisor.py | 39 ++++++++++++++++-
 tests/test_dispatch.py        | 97 +++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 145 insertions(+), 3 deletions(-)

```

### 2026-08-30 14:00:41Z · merging · decision

decision recorded as `DEC-105`
