---
id: TICKET-144
stage: done
class: feature
branch: ticket/144
test_file: tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
files_declared:
- pipeline/cli/main.py
- pipeline/core/machine.py
- pipeline/core/ticket.py
- pipeline/daemon/supervisor.py
- tests/test_dispatch.py
- tests/test_machine.py
- tests/test_ticket.py
counters:
  plan_validation_attempts: 1
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 6
  plan_files: 7
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: holistic-review
  id: 4238ddf7-217e-489f-97c1-4523706fdd4e
  replay: claude --resume 4238ddf7-217e-489f-97c1-4523706fdd4e
  log: .project/logs/TICKET-144-holistic-review-4238ddf7.log
  cost_usd: 1.3895890000000002
approved_by: chezzijr
approved_at: '2026-09-20T04:58:01.859076+00:00'
---

## Summary

A rebase conflict discards the branch, the plan and the human's approval

Expected change files: `pipeline/core/machine.py`, `pipeline/daemon/supervisor.py`, `pipeline/core/ticket.py`, `tests/test_machine.py`, `tests/test_dispatch.py`.

`pipeline/core/machine.py:224`, on main at f9d1063:

    case ("revalidating", "conflict"):
        # the branch cannot be rebased onto base, so its commits are
        # discarded and the branch is recut from base. `triage` is the
        # only stage that can rebuild it
        return charge("rebase_conflicts", "triage")

So one conflict costs a triage run, a planning run and a second approval round. In a real project this hit five tickets (139, 141, 142, 143, 145); 142 took 24 stage transitions to land. Every conflict there was in an append-only ledger file, where both sides are wanted and neither is a real contradiction.

Two consequences, both to fix here:

1. The conflict is charged even when it is confined to files whose two sides could both be kept. The recut discards commits that had already passed review.
2. The approval does not survive the recut. `planning` writes a plan again, the ticket parks at `awaiting-approval` again, and the human re-approves text they already approved. `approved_by`/`approved_at` are in `CONTROL_FIELDS` but nothing compares the new plan with the approved one.

Expected: (a) a ticket returning from a recut with an unchanged `## Plan` does not ask for approval twice -- record what was approved (a hash of the plan section is enough) and let the dispatcher carry the approval forward when the section is byte-identical, charging nothing; a changed plan still parks at `awaiting-approval`. (b) `rebase_conflicts` remains bounded and a genuine code conflict still escalates: nothing here may auto-resolve a conflict in source. Tests: a ticket recut with an identical plan advances past `awaiting-approval` without a human; a ticket whose plan text changed still parks; the conflict counter still charges and still escalates at its bound.

## Reproduction

`uv run --group dev pytest -q tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan`

```
E       AssertionError: an unchanged approved plan asked for another human approval
E       assert 'awaiting-approval' == 'revalidating'
```

expect: AssertionError: an unchanged approved plan asked for another human approval

## Digest

`pipeline/cli/main.py::cmd_approve` (line 305) is the only approval writer: it sets `approved_by`, `approved_at` and `stage`, and the TUI calls that same function (`pipeline/tui/app.py:788`).
`pipeline/cli/main.py:215` holds `PLAN_SECTIONS = ("Plan", "Acceptance criteria", "Rollback")` -- the three sections `plan_text()` shows at the gate. DEC-073 requires exactly one such list.
`pipeline/core/ticket.py::sections()` is fence-aware and returns a section body stripped of its heading. `Ticket.extra` round-trips unknown frontmatter, and `cheap_route_head` is the precedent for a dispatcher-written `extra` key.
`Ticket` has no `replace_section` METHOD -- only the module function at `pipeline/core/ticket.py:188`. The reproduction test calls `carried.replace_section("Plan", ...)` at `tests/test_dispatch.py:642`, so the method is required.
`pipeline/daemon/supervisor.py::advance()` (line 108) computes `nxt` from `transition()` and then saves, so an `extra` key written there persists. `_finish()` (line 1285) restores frontmatter from the pre-spawn snapshot and escalates any `CONTROL_FIELDS` change an agent made.
`pipeline/core/machine.py:158` returns `awaiting-approval` for `("plan-validation", "ok")`, and `("implementing", "blocked")` charges `blocked_count` back to `plan-validation` (line 244). That second path is the DEC-029 hazard the last plan was rejected on.
Gotcha: a stage's sidecar `result` string reaches `advance()` unchecked, so a stage can write `result: approved`. `advance()` recomputes the verdict from the digest instead of trusting the word.
Gotcha: `transition` and `CONTROL_FIELDS` in `pipeline/core/machine.py` are in `machine.FENCED`, so this ticket parks at `awaiting-merge` for a human whatever the reviews say.
Gotcha: no step touches `regate_cmd()`, `start()`'s `revalidating` branch or `finish_regate()`, so DEC-061's single rebase-and-gate child and its exit 3 are unchanged.

## Decisions checked

DEC-029 (active) keeps the conflict repair -- abort, reset onto the recorded base, return through `triage` -- and also requires a gate on any route that carries implementation commits into that repair. This plan drops `approved_plan_hash` the moment a ticket enters `implementing`, so an `implementing -> blocked -> plan-validation` ticket has no approval to carry and still stops at the human gate.
DEC-073 (active, supersedes DEC-050) makes `pipeline plan` and the TUI gate print `Plan`, `Acceptance criteria` and `Rollback` through one `PLAN_SECTIONS` list, because two lists once showed two different plans. The digest covers those same three sections, and the list keeps one owner: it moves to `pipeline/core/ticket.py` and `pipeline/cli/main.py` imports it.
DEC-061 (active) keeps rebase and Tier A gate in one child with exit 3 reserved for a conflict. No step edits `regate_cmd()`, `finish_regate()` or `start()`.
DEC-011 is superseded by DEC-141, so it is history here, not a constraint; it is why `cmd_approve` refuses outside its two gates, which the code still does (`GATE_NEXT` at `pipeline/cli/main.py:300`). The hash is recorded for `awaiting-approval` only, never for `awaiting-merge`.
Search terms: `approv`, `plan hash`, `digest`, `rebase`, `conflict`, `recut`, `awaiting-approval`, `control field`, `blocked`.

## Plan

1. Add two tests to `tests/test_ticket.py`: `test_plan_digest_covers_the_sections_the_gate_shows` (same body gives the same digest twice; editing `## Rollback` or `## Acceptance criteria` changes it; a `## Plan` heading written inside a fenced block in `## Thread` does not) and `test_replace_section_method_rewrites_the_body` (`Ticket(path=Path("x"), id="TICKET-001", body="## Plan\n1. a\n\n## Thread\n").replace_section("Plan", "1. b\n")` leaves `t.section("Plan") == "1. b"` and keeps `## Thread`); run `uv run --group dev pytest -q tests/test_ticket.py`; expect both to fail on a missing `plan_digest` attribute and a missing method.
2. In `pipeline/core/ticket.py` add `import hashlib`, `SAFE_HASH = re.compile(r"^[0-9a-f]{64}$")`, `PLAN_SECTIONS = ("Plan", "Acceptance criteria", "Rollback")` moved from `pipeline/cli/main.py:215`, `def plan_digest(body: str) -> str` returning `hashlib.sha256("\n".join(f"## {n}\n" + sections(body).get(n, "") for n in PLAN_SECTIONS).encode()).hexdigest()`, the method `def replace_section(self, name: str, content: str) -> None: self.body = replace_section(self.body, name, content)` on `Ticket` beside `section()`, and in `validate_meta()` a check appending `f"approved_plan_hash {h!r} is not a sha256 hex digest"` when the key is present and does not match `SAFE_HASH`; import `PLAN_SECTIONS` from `pipeline.core.ticket` in `pipeline/cli/main.py` and delete its local assignment, leaving `plan_text()` unchanged; run `uv run --group dev pytest -q tests/test_ticket.py tests/test_cli.py`; expect exit 0; commit.
3. In `tests/test_machine.py` add `assert "approved_plan_hash" in M.CONTROL_FIELDS, "a stage that writes the approval hash must escalate, not be reverted"` to `test_control_fields_are_the_dispatchers_alone`, and add `test_an_identical_approved_plan_revalidates_without_a_human` asserting `t("plan-validation", "approved") == ("revalidating", {})`, that `t("plan-validation", "approved", {"rebase_conflicts": 1})[1] == {"rebase_conflicts": 1}` (the row charges nothing), and that `t("plan-validation", "ok")[0] == "awaiting-approval"` still holds; run `uv run --group dev pytest -q tests/test_machine.py`; expect the new test to fail with `('escalated', {})`.
4. In `pipeline/core/machine.py` add `"approved_plan_hash"` to `CONTROL_FIELDS` and, directly under the `("plan-validation", "ok")` row, the row `case ("plan-validation", "approved"): return "revalidating", c` with a comment saying the dispatcher -- not the agent -- issues this result, only when `## Plan`, `## Acceptance criteria` and `## Rollback` are byte-identical to what a human approved, and that it charges nothing because every exit from `revalidating` charges or leaves; run `uv run --group dev pytest -q tests/test_machine.py`; expect exit 0; commit.
5. Add two tests to `tests/test_dispatch.py`: `test_implementing_voids_a_carried_approval` (from `_ticket_awaiting_approval()`, assert `Ticket.load(path).extra["approved_plan_hash"]` is set, call `supervisor.advance(d, Ticket.load(path), "ok", "re-gated", agent=False)` and assert the ticket is at `implementing` with no `approved_plan_hash` in `extra`, then set `stage = "plan-validation"`, `save()`, advance `"ok"` again and assert `awaiting-approval`, quoting DEC-029's `git reset --hard` in the docstring) and `test_a_forged_approved_result_cannot_skip_the_human_gate` (same helper, set `stage = "plan-validation"`, `extra.pop("approved_plan_hash", None)`, `save()`, call `supervisor.advance(d, Ticket.load(path), "approved", "done")` and assert `awaiting-approval`); run `uv run --group dev pytest -q tests/test_dispatch.py -k "carried or forged or recut_carries"`; expect three failures; commit.
6. In `pipeline/cli/main.py` set `t.extra["approved_plan_hash"] = plan_digest(t.body)` in `cmd_approve` only when `gate == "awaiting-approval"` and add `t.extra.pop("approved_plan_hash", None)` to `cmd_reject` before its `t.save()`; in `pipeline/daemon/supervisor.py` add `def approval_carries(t: Ticket) -> bool` returning `bool(h) and h == plan_digest(t.body)` for `h = str(t.extra.get("approved_plan_hash") or "")`, and in `advance()` insert `if stage == "plan-validation" and result in ("ok", "approved"): result = "approved" if approval_carries(t) else "ok"` above the `transition()` call plus `if nxt == "implementing": t.extra.pop("approved_plan_hash", None)` above `t.counters = counters`; run `uv run --group dev pytest -q tests/test_ticket.py tests/test_cli.py tests/test_machine.py tests/test_dispatch.py`; expect exit 0; commit.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` exits 0: an unchanged approved plan reaches `revalidating` with no human, and changed plan text parks at `awaiting-approval`.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_implementing_voids_a_carried_approval tests/test_dispatch.py::test_a_forged_approved_result_cannot_skip_the_human_gate` exits 0: DEC-029's gate holds, and a sidecar word cannot buy an approval.
- `uv run --group dev pytest -q tests/test_machine.py::test_control_fields_are_the_dispatchers_alone tests/test_machine.py::test_an_identical_approved_plan_revalidates_without_a_human tests/test_machine.py::test_a_rebase_conflict_returns_to_triage_and_is_bounded` exits 0: the hash is dispatcher-owned, the new row charges nothing, and `rebase_conflicts` still escalates at its bound.
- `uv run --group dev pytest -q tests/test_ticket.py tests/test_cli.py tests/test_machine.py tests/test_dispatch.py` exits 0.
- `grep -c "^PLAN_SECTIONS = " pipeline/cli/main.py` prints `0`, and `grep -c "^PLAN_SECTIONS = " pipeline/core/ticket.py` prints `1`: DEC-073's one list, one owner.

## Decisions

**An approval is reusable only when the three sections the gate SHOWS are byte-identical.** `approved_plan_hash` is SHA-256 over `PLAN_SECTIONS` -- `## Plan`, `## Acceptance criteria`, `## Rollback` -- because DEC-073 says approving a plan approves its undo path. Hashing `## Plan` alone would reuse a human's approval for a rollback they never read.

**Entering `implementing` drops the hash, and that drop is DEC-029's gate.** `revalidating` repairs a conflict with `git reset --hard <base>`, so a branch that may carry implementation commits must never reach it without a human. The dispatcher pops `approved_plan_hash` in `advance()` whenever the next stage is `implementing`, so the `implementing -> blocked -> plan-validation -> ok` path parks at `awaiting-approval` exactly as it does today. Remove that pop and a blocked ticket's finished work is discarded with no human in the loop.

**`advance()` recomputes the verdict; it never trusts the word `approved`.** A `plan-validation` result of `ok` OR `approved` becomes `approved` only when the digest matches, so a stage writing `result: approved` into its sidecar cannot skip the gate. `approved_plan_hash` is in `CONTROL_FIELDS`, so a stage writing it into the frontmatter escalates the ticket instead of being silently reverted.

**`pipeline approve` is the only writer and `pipeline reject` clears it.** The hash is recorded at the `awaiting-approval` gate only, never at `awaiting-merge`. Without the clear in `cmd_reject`, a re-plan that reproduces an older approved text would carry forward an approval the human had just refused.

**The carry-forward row charges no counter, and it is bounded from the other side.** Every exit from `revalidating` either charges (`stale_regate`, `rebase_conflicts`) or leaves for `implementing`, so the uncharged row cannot loop for free.

**Conflict repair is unchanged.** A conflicting rebase still aborts, recuts onto the recorded base, charges `rebase_conflicts` and returns through `triage`. Nothing here resolves or merges conflicting source content.

## Rollback

Step 6 is the riskiest step: it is the one that lets a ticket past a human gate. Fallback if `test_implementing_voids_a_carried_approval`, `test_a_forged_approved_result_cannot_skip_the_human_gate` or the reproduction test goes red: delete `approval_carries()` and the two `advance()` inserts in `pipeline/daemon/supervisor.py`, which routes every `("plan-validation", "ok")` back to `awaiting-approval` and leaves the recorded hash inert, then re-run the suites of criterion 4 and report the red test.
To revert after a merge: revert the step 6, step 4 and step 2 commits, in that order, undoing `pipeline/daemon/supervisor.py`, `pipeline/cli/main.py`, `pipeline/core/machine.py` and `pipeline/core/ticket.py` together -- `plan_digest()` and `PLAN_SECTIONS` must not be removed from `pipeline/core/ticket.py` while `pipeline/cli/main.py` still imports them. Revert the assertions in `tests/test_ticket.py`, `tests/test_machine.py` and `tests/test_dispatch.py` with them. Keep the reproduction commit `89a4f84`.

## Thread

### 2026-09-20 01:53:55Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-20 02:10:00Z · triage · reproduction

Reproduced the lost approval after a rebase-conflict recut.

`89a4f84` adds `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan`.

The test creates a real rebase conflict, confirms the reset returns to `triage`, and renews plan validation unchanged.

The dispatcher then returns `awaiting-approval`, not `revalidating`.

Root cause: `cmd_approve()` stores approver metadata but no plan identity.

`advance()` always maps successful `plan-validation` to `awaiting-approval`, so it cannot carry an unchanged approval forward.

The test also requires changed plan text to remain at `awaiting-approval`.

Expected implementation files: `pipeline/core/machine.py`, `pipeline/daemon/supervisor.py`, `pipeline/core/ticket.py`, `tests/test_machine.py`, and `tests/test_dispatch.py`.

### 2026-09-20 02:03:50Z · triage · session · session=01a0bc8c-9f46-7341-aaa1-648aa06ccd03

`triage` ran as session `01a0bc8c-9f46-7341-aaa1-648aa06ccd03`
- replay: `codex exec resume 01a0bc8c-9f46-7341-aaa1-648aa06ccd03`
- log: `.project/logs/TICKET-144-triage-16174782.log`
- cost: unknown (the harness reported none)
- tokens: 3,974 out (1,425 thinking) · 514,143 in · 467,968 cache read · 0 cache write

### 2026-09-20 02:03:50Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced lost approval after a rebase-conflict recut

### 2026-09-20 02:08:56Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails as required
```
ed", agent=False)
        carried = Ticket.load(path)
>       assert carried.stage == "revalidating", \
            "an unchanged approved plan asked for another human approval"
E       AssertionError: an unchanged approved plan asked for another human approval
E       assert 'awaiting-approval' == 'revalidating'
E         
E         - revalidating
E         + awaiting-approval

tests/test_dispatch.py:637: AssertionError
----------------------------- Captured stdout call -----------------------------
TICKET-001: -> revalidating
  start TICKET-001: revalidating (script) pid 3780142 -> TICKET-001-revalidating-0f8ad199.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.30s ===============================

```
- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001: revalidating (script) pid 3780249 -> TICKET-001-revalidating-7978d99c.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.68s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-_m8tn5hu/base
      Built pipeline @ file:///tmp/pipeline-base-_m8tn5hu/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 58ms

```
- `files_declared` is empty
- plan step names no declared file: '1. Extend `tests/test_dispatch.py` and `tests/test_machine.py` so the recut test requires a persisted approved-plan hash, identical plans select an uncharged revalidation transition, changed plan bytes park at approval, the hash is dispatcher-controlled, and the existing conflict bound still escalates on its second charge; run the named tests before implementation and confirm the approval-reuse assertions fail.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Add a fence-aware SHA-256 section helper and approved-plan-hash validation in `pipeline/core/ticket.py`, hashing the exact `## Plan` heading and content through the byte before the next real level-two heading so whitespace changes cannot reuse approval.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Add `approved_plan_hash` to `CONTROL_FIELDS` and add a pure, uncharged `("plan-validation", "approved") -> "revalidating"` row in `pipeline/core/machine.py`; run the focused `tests/test_machine.py` transition, control-field, and conflict-bound tests.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '4. Update `pipeline/daemon/supervisor.py::start()` to persist the current plan hash whenever an approved ticket enters `revalidating`, and update `pipeline/daemon/supervisor.py::advance()` to select the `approved` result only when a successful plan validation exactly matches that hash; run the focused dispatch reproduction and both module suites.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-20 02:10:47Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails as required
```
ed", agent=False)
        carried = Ticket.load(path)
>       assert carried.stage == "revalidating", \
            "an unchanged approved plan asked for another human approval"
E       AssertionError: an unchanged approved plan asked for another human approval
E       assert 'awaiting-approval' == 'revalidating'
E         
E         - revalidating
E         + awaiting-approval

tests/test_dispatch.py:637: AssertionError
----------------------------- Captured stdout call -----------------------------
TICKET-001: -> revalidating
  start TICKET-001: revalidating (script) pid 3789279 -> TICKET-001-revalidating-7f256ecb.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.28s ===============================

```
- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001: revalidating (script) pid 3789376 -> TICKET-001-revalidating-053e84a8.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.71s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ttyiso61/base
      Built pipeline @ file:///tmp/pipeline-base-ttyiso61/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 51ms

```
- `files_declared` is empty
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '1. Extend `tests/test_dispatch.py` and `tests/test_machine.py` with approved-hash and pure-transition assertions. Preserve the second-conflict escalation assertion. Run the named tests; expect approval reuse to fail.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Add a fence-aware SHA-256 section helper and hash validation in `pipeline/core/ticket.py`. Hash from the `## Plan` heading through the byte before the next real level-two heading. Accept absent hashes or 64 lowercase hexadecimal characters.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Add `approved_plan_hash` to `CONTROL_FIELDS` in `pipeline/core/machine.py`. Map `("plan-validation", "approved")` to `revalidating` without charging. Run the focused machine tests; expect them to pass.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '4. Update `pipeline/daemon/supervisor.py::start()` to persist the plan hash before each approved revalidation. Update `pipeline/daemon/supervisor.py::advance()` to select `approved` only for an exact hash match. Run the focused reproduction and both module suites; expect them to pass.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-20 02:11:04Z · planning · plan

Planned dispatcher-owned approval identity without changing CLI behavior.

The dispatcher records the exact plan hash before approved revalidation.

Successful plan validation reuses approval only for an exact hash match.

Changed plan bytes still park at `awaiting-approval`.

DEC-029 and DEC-061 keep conflict repair unchanged: abort, recut to base, charge `rebase_conflicts`, and return through `triage`.

The repeated Tier A gate reported only the permitted pre-adoption findings: empty `files_declared` and plan paths absent from that empty list.

The result declares all five planned files.

### 2026-09-20 02:11:34Z · planning · session · session=01a0bc8e-355e-7a21-a7be-edfd7b8e5af7

`planning` ran as session `01a0bc8e-355e-7a21-a7be-edfd7b8e5af7`
- replay: `codex exec resume 01a0bc8e-355e-7a21-a7be-edfd7b8e5af7`
- log: `.project/logs/TICKET-144-planning-8c620e9b.log`
- cost: unknown (the harness reported none)
- tokens: 15,464 out (8,032 thinking) · 2,085,899 in · 1,997,312 cache read · 0 cache write

### 2026-09-20 02:11:34Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned byte-identical approval carry-forward while preserving bounded conflict recuts

### 2026-09-20 03:57:01Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails as required
```
ed", agent=False)
        carried = Ticket.load(path)
>       assert carried.stage == "revalidating", \
            "an unchanged approved plan asked for another human approval"
E       AssertionError: an unchanged approved plan asked for another human approval
E       assert 'awaiting-approval' == 'revalidating'
E         
E         - revalidating
E         + awaiting-approval

tests/test_dispatch.py:637: AssertionError
----------------------------- Captured stdout call -----------------------------
TICKET-001: -> revalidating
  start TICKET-001: revalidating (script) pid 3999915 -> TICKET-001-revalidating-cf4fd268.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.27s ===============================

```
- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001: revalidating (script) pid 4000017 -> TICKET-001-revalidating-cef42c8f.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.66s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-916q5ysv/base
      Built pipeline @ file:///tmp/pipeline-base-916q5ysv/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 82ms

```

### 2026-09-20 04:05:00Z · plan-validation · finding · severity=blocking

**Tier B: FAIL.** The plan adds an automatic route into `revalidating` from a stage whose branch can carry `implementing`'s commits, and DEC-029 requires that route to be gated.

long: the stage must score eight items and quote the evidence for the blocking one.

`("implementing", "blocked")` returns to `plan-validation` (`pipeline/core/machine.py:244`, `charge("blocked_count", "plan-validation")`). An approved ticket reaches it as approved -> `revalidating` (hash captured by step 4) -> `implementing` -> blocked -> `plan-validation`. Its `## Plan` bytes are unchanged, so step 4's comparison matches and step 3's new row sends it to `revalidating` with no human. A conflict there runs `git reset --hard {base}` (`pipeline/daemon/supervisor.py:1172`) and discards the implementation commits. DEC-029 names this exact case:

```
**The recut is safe only because `revalidating` runs before `implementing`.**
A future change that routes a stage holding implementation commits through
`finish_regate()` would discard real work. Gate such a change on the branch
carrying no commit but triage's, or give it a different repair.
```

The plan's `## Decisions checked` answers only DEC-029's repair ("abort, reset onto the recorded base, return through `triage`") and never this paragraph. Today the same destruction needs a human to press `pipeline approve`; the plan removes them. No test covers it: `grep -n blocked tests/test_dispatch.py` matches only lines 231 and 2008, neither about this path, so acceptance criterion 3 passes while the hazard ships.

Fix by gating the carry-forward, not by widening scope. One option: refuse the reuse unless the branch carries no commit past base but triage's. Another: have `advance()` ignore `approved_plan_hash` when `blocked_count` was just charged. Either one needs its own assertion in `tests/test_dispatch.py`.

Per-item scores:

1. Root cause -- **pass**. The dispatcher records THAT a human approved (`approved_by`/`approved_at`) and never WHAT they approved, so `("plan-validation", "ok")` returns `awaiting-approval` unconditionally (`pipeline/core/machine.py:158`) and cannot tell a re-planned identical plan from a new one. The plan supplies that missing identity; it does not merely make the test pass.
2. Decision conflict -- **fail**, DEC-029, above. DEC-061 is satisfied: step 4 captures the hash in `start()` before `regate_cmd()`, so rebase and gate stay one child and exit 3 still means conflict.
3. Scope discipline -- **pass**. Four steps, five files, all traceable: steps 2 and 4 to criterion 1, step 3 to criteria 2 and 3, step 1 to all three.
4. Falsifiable criteria -- **pass, with one dependency**. Criterion 1 asserts both directions, so always-park and always-carry each fail it. Criterion 2's `test_control_fields_are_the_dispatchers_alone` passes today unmodified and is vacuous for this ticket until step 1 adds the `approved_plan_hash` assertion step 1 promises.
5. No research left -- **pass**. Every step names the file and the symbol: `CONTROL_FIELDS`, `("plan-validation", "approved")`, `start()`, `advance()`. Step 2 names the byte range and the accepted hash shape instead of a function name; `sections()` and `_fenced()` in `pipeline/core/ticket.py` are the pattern it follows.
6. Riskiest step -- **pass**. The plan names step 4 and states the fallback: remove the comparison, route every successful plan validation to `awaiting-approval`.
7. Regression surface -- **pass**. `advance()` runs on every transition, so the surface is every `("plan-validation", "ok")`. `tests/test_dispatch.py::test_a_stale_plan_is_re_gated_on_approval` and `::test_a_still_good_plan_is_implemented_after_the_rebase` cover the revalidating paths, and criterion 3 runs both modules whole. The one uncovered path is finding 2's.
8. Blast radius -- **pass**. Three source files and two test files for a bugfix. No reclassification needed.

Two notes that are not findings:

- The new row cannot loop for free. Every exit from `revalidating` charges or leaves: `ok` goes to `implementing`, `fail` charges `stale_regate`, `conflict` charges `rebase_conflicts`. The uncharged row is bounded by the counter on the other side.
- `## Summary` consequence 1 ("the conflict is charged even when it is confined to files whose two sides could both be kept") is not implemented, and correctly so. The ticket's own Expected clause (b) says "nothing here may auto-resolve a conflict in source" and its Tests line requires "the conflict counter still charges". The plan matches the Expected clause, not the consequence's wider reading. Say so at the gate if more was meant.

**unverified:** I ran no test. A read-only stage cannot run `uv run pytest`, so every claim above rests on reading `pipeline/core/machine.py`, `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py` and `.project/decisions/DEC-029.md`. I would have run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_machine.py` to confirm the blocked path has no coverage.

### 2026-09-20 04:11:09Z · plan-validation · session · session=49593702-71ac-4d7b-8d3e-2e5b956bbd63

`plan-validation` ran as session `49593702-71ac-4d7b-8d3e-2e5b956bbd63`
- replay: `claude --resume 49593702-71ac-4d7b-8d3e-2e5b956bbd63`
- log: `.project/logs/TICKET-144-plan-validation-49593702.log`
- cost: $1.36 of a $3 cap
- tokens: 14,083 out (7,704 thinking) · 32 in · 784,562 cache read · 61,386 cache write

### 2026-09-20 04:11:09Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ the plan routes a branch carrying implementing's commits into revalidating's `git reset --hard`, which DEC-029 requires it to gate

### 2026-09-20 04:19:27Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails as required
```
ed", agent=False)
        carried = Ticket.load(path)
>       assert carried.stage == "revalidating", \
            "an unchanged approved plan asked for another human approval"
E       AssertionError: an unchanged approved plan asked for another human approval
E       assert 'awaiting-approval' == 'revalidating'
E         
E         - revalidating
E         + awaiting-approval

tests/test_dispatch.py:637: AssertionError
----------------------------- Captured stdout call -----------------------------
TICKET-001: -> revalidating
  start TICKET-001: revalidating (script) pid 4037090 -> TICKET-001-revalidating-f74428b2.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.27s ===============================

```
- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001: revalidating (script) pid 4037178 -> TICKET-001-revalidating-cb62c3ec.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.66s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-4izuj359/base
      Built pipeline @ file:///tmp/pipeline-base-4izuj359/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 69ms

```
- ok: DEC-011 is superseded -- history, not binding
- ok: DEC-050 is superseded -- history, not binding
- plan step names no declared file: '1. Add two tests to `tests/test_ticket.py`: `test_plan_digest_covers_the_sections_the_gate_shows` (same body gives the same digest twice; editing `## Rollback` or `## Acceptance criteria` changes it; a `## Plan` heading written inside a fenced block in `## Thread` does not) and `test_replace_section_method_rewrites_the_body` (`Ticket(path=Path("x"), id="TICKET-001", body="## Plan\\n1. a\\n\\n## Thread\\n").replace_section("Plan", "1. b\\n")` leaves `t.section("Plan") == "1. b"` and keeps `## Thread`); run `uv run --group dev pytest -q tests/test_ticket.py`; expect both to fail on a missing `plan_digest` attribute and a missing method.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-20 04:21:19Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails as required
```
ed", agent=False)
        carried = Ticket.load(path)
>       assert carried.stage == "revalidating", \
            "an unchanged approved plan asked for another human approval"
E       AssertionError: an unchanged approved plan asked for another human approval
E       assert 'awaiting-approval' == 'revalidating'
E         
E         - revalidating
E         + awaiting-approval

tests/test_dispatch.py:637: AssertionError
----------------------------- Captured stdout call -----------------------------
TICKET-001: -> revalidating
  start TICKET-001: revalidating (script) pid 4041615 -> TICKET-001-revalidating-9732ca73.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================

```
- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001: revalidating (script) pid 4041701 -> TICKET-001-revalidating-68977b5a.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.69s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-eeevk3be/base
      Built pipeline @ file:///tmp/pipeline-base-eeevk3be/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 96ms

```
- ok: DEC-011 is superseded -- history, not binding
- ok: DEC-050 is superseded -- history, not binding
- plan step names no declared file: '1. Add two tests to `tests/test_ticket.py`: `test_plan_digest_covers_the_sections_the_gate_shows` (same body gives the same digest twice; editing `## Rollback` or `## Acceptance criteria` changes it; a `## Plan` heading written inside a fenced block in `## Thread` does not) and `test_replace_section_method_rewrites_the_body` (`Ticket(path=Path("x"), id="TICKET-001", body="## Plan\\n1. a\\n\\n## Thread\\n").replace_section("Plan", "1. b\\n")` leaves `t.section("Plan") == "1. b"` and keeps `## Thread`); run `uv run --group dev pytest -q tests/test_ticket.py`; expect both to fail on a missing `plan_digest` attribute and a missing method.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)

### 2026-09-20 04:22:00Z · planning · plan

Re-planned around plan-validation's blocking DEC-029 finding.

The rejected plan compared the hash with no gate on the branch's commits. This plan adds the gate: `advance()` pops `approved_plan_hash` whenever the next stage is `implementing`, so an `implementing -> blocked -> plan-validation -> ok` ticket reaches `revalidating`'s `git reset --hard <base>` only after a human runs `pipeline approve`, exactly as today. `tests/test_dispatch.py::test_implementing_voids_a_carried_approval` asserts it.

Two further changes from the rejected plan:

1. The digest covers `PLAN_SECTIONS` -- `## Plan`, `## Acceptance criteria`, `## Rollback` -- not `## Plan` alone. DEC-073: approving a plan approves its undo path, and the gate shows all three sections.
2. `advance()` recomputes the verdict, so a stage writing `result: approved` into its sidecar cannot forge one (`test_a_forged_approved_result_cannot_skip_the_human_gate`).

`start()` and `regate_cmd()` are untouched, so DEC-061 holds. The reproduction test calls `Ticket.replace_section`, a method that does not exist; step 2 adds it.

The two `gate · verdict=FAIL` entries above are my own runs. Their one remaining finding is the expected pre-adoption `files_declared` one: the result declares `tests/test_ticket.py` and `pipeline/cli/main.py`.

`## Summary` consequence 1 -- keeping both sides of an append-only conflict -- is still not planned, per the Expected clause "nothing here may auto-resolve a conflict in source".

### 2026-09-20 04:22:32Z · planning · session · session=ade6b868-89f7-4ad6-9afd-2c2691bcbfeb

`planning` ran as session `ade6b868-89f7-4ad6-9afd-2c2691bcbfeb`
- replay: `claude --resume ade6b868-89f7-4ad6-9afd-2c2691bcbfeb`
- log: `.project/logs/TICKET-144-planning-ade6b868.log`
- cost: $4.71 of a $10 cap
- tokens: 43,905 out (24,403 thinking) · 106 in · 4,743,066 cache read · 124,267 cache write

### 2026-09-20 04:22:32Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-planned the approval carry-forward with DEC-029's gate: the digest covers all three sections the human sees, and entering `implementing` drops it

### 2026-09-20 04:23:41Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails as required
```
ed", agent=False)
        carried = Ticket.load(path)
>       assert carried.stage == "revalidating", \
            "an unchanged approved plan asked for another human approval"
E       AssertionError: an unchanged approved plan asked for another human approval
E       assert 'awaiting-approval' == 'revalidating'
E         
E         - revalidating
E         + awaiting-approval

tests/test_dispatch.py:637: AssertionError
----------------------------- Captured stdout call -----------------------------
TICKET-001: -> revalidating
  start TICKET-001: revalidating (script) pid 4046298 -> TICKET-001-revalidating-b4fa54b6.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.27s ===============================

```
- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001: revalidating (script) pid 4046382 -> TICKET-001-revalidating-1ce4b984.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.67s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-hyc8dfjx/base
      Built pipeline @ file:///tmp/pipeline-base-hyc8dfjx/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 64ms

```
- ok: DEC-011 is superseded -- history, not binding
- ok: DEC-050 is superseded -- history, not binding

### 2026-09-20 04:25:00Z · plan-validation · finding · severity=info

**Tier B: PASS.** All eight items pass. The blocking DEC-029 finding is answered.

long: the stage must score eight items and state the reasoning for each.

1. Root cause -- **pass**. The dispatcher records THAT a human approved (`approved_by`/`approved_at`) and never WHAT they approved, so `("plan-validation", "ok")` returns `awaiting-approval` unconditionally (`pipeline/core/machine.py:158`). The plan supplies the missing identity and compares it; it does not merely make the test pass.
2. Decision conflict -- **pass**. DEC-029's gate holds by construction. Step 6 pops `approved_plan_hash` whenever `nxt == "implementing"`, and every route into `implementing` runs through `advance()`: `transition()`'s only implementing targets are `("triage", "chore")`, `("revalidating", "ok")` and the three `charge("review_loops", "implementing")` rows, and `grep -n 'stage = "implementing"' pipeline/daemon/supervisor.py` matches nothing. A branch that ever ran `implementing` can regain a hash only from `cmd_approve` -- a human. `test_implementing_voids_a_carried_approval` asserts it (criterion 2). DEC-061: no step edits `regate_cmd()`, `finish_regate()` or `start()`.
3. Scope discipline -- **pass**. Six steps, three source files, three test files. Steps 2 and 6 trace to criterion 1, step 5 to criterion 2, steps 3 and 4 to criterion 3, step 1 to criterion 4, step 2's move to criterion 5.
4. Falsifiable criteria -- **pass**. Criterion 1 asserts both directions in one test, so always-carry and always-park each fail it. Criterion 3's `test_control_fields_are_the_dispatchers_alone` is vacuous for this ticket until step 3 adds its `approved_plan_hash` assertion, which step 3 does. Criterion 5 flips two real counts: today `grep -c "^PLAN_SECTIONS = "` prints `1` for `pipeline/cli/main.py` and `0` for `pipeline/core/ticket.py`.
5. No research left -- **pass**. Step 6's two anchors exist: `nxt, counters = transition(stage, result, t.counters, t.klass)` and `t.counters = counters` in `advance()`. Step 5's `_ticket_awaiting_approval()` is at `tests/test_dispatch.py:479` and leaves the ticket at `revalidating`, so an `advance(..., "ok")` from it lands on `implementing` as the step says.
6. Riskiest step -- **pass**. The plan names step 6 and states a fallback that restores today's behaviour: delete `approval_carries()` and the two `advance()` inserts, leaving the recorded hash inert.
7. Regression surface -- **pass**. The insert is guarded by `stage == "plan-validation"`, so the surface is every `("plan-validation", "ok")`, covered by `test_a_stale_plan_is_re_gated_on_approval` and `test_a_still_good_plan_is_implemented_after_the_rebase`. The `cmd_approve`/`cmd_reject` edits are covered by `tests/test_cli.py`, which steps 2 and 6 both run. The `CONTROL_FIELDS` check needs no further change: `_finish()` reads `agent.frontmatter()`, and `frontmatter()` merges `extra` (`pipeline/core/ticket.py:682`), so the new key is compared like the other nine.
8. Blast radius -- **pass**. A `bugfix` with three source files and three test files. No reclassification.

Three notes that are not findings:

- **DEC-073 goes stale at merge, in one sentence.** It says "`plan_text()` in `pipeline/cli/main.py` owns `PLAN_SECTIONS`"; step 2 moves the list to `pipeline/core/ticket.py`. That is not a conflict: DEC-073's rule is one list and one printed set of sections, and both hold -- `plan_text()` is unchanged, and `grep -n PLAN_SECTIONS pipeline/tui/app.py` matches nothing, so the TUI imports `plan_text`, not the list. The move is forced: `pipeline/cli/main.py` imports `pipeline/core/ticket.py`, so the reverse import would cycle. I filed no correction, because the record matches the code as it stands today. The merge gate should expect that sentence to age.
- **"Byte-identical" means identical after `sections()` strips.** `sections()` returns each body `.strip()`ed, so a trailing-blank-line edit inside the three sections still carries the approval forward. The compared text is what the gate printed, so the guarantee holds; the word "byte" is looser than it reads.
- **`## Summary` consequence 1 stays unplanned**, matching the Expected clause "nothing here may auto-resolve a conflict in source". Say so at the gate if more was meant.

**unverified:** I ran no test. A read-only stage cannot run `uv run pytest`, so every claim above rests on reading `pipeline/core/machine.py`, `pipeline/daemon/supervisor.py`, `pipeline/core/ticket.py`, `pipeline/cli/main.py`, `pipeline/tui/app.py`, `tests/test_dispatch.py`, `tests/test_machine.py`, `.project/decisions/DEC-029.md` and `.project/decisions/DEC-073.md`. I would have run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_machine.py tests/test_cli.py`.

### 2026-09-20 04:28:02Z · plan-validation · session · session=bdb2c39f-febd-4da6-8060-2ad1e7a96b01

`plan-validation` ran as session `bdb2c39f-febd-4da6-8060-2ad1e7a96b01`
- replay: `claude --resume bdb2c39f-febd-4da6-8060-2ad1e7a96b01`
- log: `.project/logs/TICKET-144-plan-validation-bdb2c39f.log`
- cost: $2.01 of a $3 cap
- tokens: 23,044 out (10,833 thinking) · 48 in · 1,377,054 cache read · 74,497 cache write

### 2026-09-20 04:28:02Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B PASS: the re-plan answers DEC-029 -- every route into `implementing` goes through `advance()`, which pops the hash, so no branch holding implementation commits carries an approval into `revalidating`

### 2026-09-20 04:28:41Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-20 04:30:03Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails as required
```
ed", agent=False)
        carried = Ticket.load(path)
>       assert carried.stage == "revalidating", \
            "an unchanged approved plan asked for another human approval"
E       AssertionError: an unchanged approved plan asked for another human approval
E       assert 'awaiting-approval' == 'revalidating'
E         
E         - revalidating
E         + awaiting-approval

tests/test_dispatch.py:637: AssertionError
----------------------------- Captured stdout call -----------------------------
TICKET-001: -> revalidating
  start TICKET-001: revalidating (script) pid 4054097 -> TICKET-001-revalidating-b12ba5a0.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.62s ===============================

```
- ok: `tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001: revalidating (script) pid 4054229 -> TICKET-001-revalidating-909b6763.log
  TICKET-001: -> triage {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
  TICKET-001: -> awaiting-approval {'plan_validation_attempts': 0, 'plan_steps': 1, 'plan_files': 1, 'rebase_conflicts': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_recut_carries_forward_only_an_identical_approved_plan
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.71s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-48ufrctx/base
      Built pipeline @ file:///tmp/pipeline-base-48ufrctx/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 83ms

```
- ok: DEC-011 is superseded -- history, not binding
- ok: DEC-050 is superseded -- history, not binding

### 2026-09-20 04:30:04Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-20 04:45:00Z · implementing · finding · severity=info

**Plan executed; all six steps done.** Commits: `f4f908c` (steps 1-2), `a620804` (steps 3-4), `6d2cccc` (step 5 tests), `1115917` (step 6).

Todo: [x] 1 ticket tests · [x] 2 `plan_digest`, `SAFE_HASH`, `PLAN_SECTIONS` moved, `replace_section` method · [x] 3 machine tests · [x] 4 row + `CONTROL_FIELDS` · [x] 5 dispatch tests · [x] 6 `cmd_approve`/`cmd_reject`/`advance()`.

Verified: `uv run --group dev pytest -q tests/test_ticket.py tests/test_cli.py tests/test_machine.py tests/test_dispatch.py` printed `291 passed`; `tests/test_stages.py tests/test_tui.py` printed `91 passed`. `grep -c "^PLAN_SECTIONS = "` prints 0 for `pipeline/cli/main.py`, 1 for `pipeline/core/ticket.py`.

Each new test was red first. Extra coverage beyond the plan: `test_a_malformed_approved_plan_hash_is_refused`, `test_a_rejection_clears_the_recorded_approval` (fails if `cmd_reject` stops popping the hash), `test_approving_at_the_merge_gate_records_no_plan_hash` (fails if the `gate == "awaiting-approval"` condition is dropped). I ran both mutations; both tests failed.

Not implemented, as the plan says: summary consequence 1 (skip the charge for append-only conflicts). A source conflict still charges `rebase_conflicts` and escalates at its bound.

Note: the guard refuses a shell command containing a backslash, so edits went through the Edit tool.

### 2026-09-20 04:34:03Z · implementing · session · session=8df052f1-ed41-4139-aff0-ba08fb6d8afe

`implementing` ran as session `8df052f1-ed41-4139-aff0-ba08fb6d8afe`
- replay: `claude --resume 8df052f1-ed41-4139-aff0-ba08fb6d8afe`
- log: `.project/logs/TICKET-144-implementing-8df052f1.log`
- cost: $0.69 of a $9 cap
- tokens: 16,108 out (1,296 thinking) · 48 in · 1,313,808 cache read · 66,627 cache write

### 2026-09-20 04:34:03Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ an unchanged approved plan now carries its approval across a recut; changed text still parks, and entering implementing drops the hash (DEC-029)

### 2026-09-20 05:05:00Z · review · finding · severity=blocking

**FAIL, one blocking finding.** Reviewed the delta `main...HEAD` (5 commits, 7 files, +192/-8).

1. **blocking. `pipeline resume --stage implementing` keeps `approved_plan_hash`, so DEC-029's gate has a second door.** `advance()` is not the only writer of `stage`: `cmd_resume` sets `t.stage = stage` for any `KNOWN_STAGES` value (`pipeline/cli/main.py:440`), and `KNOWN_STAGES` holds `"implementing"` (`pipeline/core/machine.py:66`). Nothing in `cmd_resume` pops the hash -- I read it whole (`pipeline/cli/main.py:399-478`); it touches `counters`, `lease`, `last_session` credits and the thread only. Call sequence: `pipeline approve` at `awaiting-approval` records the hash; `pipeline resume <id> --stage implementing` skips the `revalidating` hop that would have popped it; `implementing` commits WIP and reports `blocked`; `("implementing", "blocked")` returns to `plan-validation` (`pipeline/core/machine.py:251`); `## Plan` is unchanged, so `approval_carries()` is true and the new row sends the ticket to `revalidating`; a conflict there runs `git reset --hard {base}` (`pipeline/daemon/supervisor.py:1161`) on a branch holding implementation commits. On `main` that path parks at `awaiting-approval`, so a human sees it. This is what DEC-029 forbids and what `## Decisions` claims cannot happen: "every route into `implementing` goes through `advance()`". `test_implementing_voids_a_carried_approval` covers the `advance()` route only.

   Refutation attempted and failed: `cmd_resume` refuses only a live lease (`live_holder()`), not a forward jump; `implementing` never edits `## Plan`, so the digest still matches; the Tier A gate at `plan-validation` passes here because a `blocked` run leaves `test_file` red. The path needs three conditions (a resume straight to `implementing`, a `blocked` result, a conflicting rebase), which makes it rare, not impossible -- and it destroys committed work with no human.

   Fix options, both one line plus one assertion in `tests/test_dispatch.py`: pop the hash in `cmd_resume` when the target stage is `implementing`, or pop it in `start()`'s existing `if stage == "implementing"` block, which catches every spawn however the stage was set.

2. non-blocking. README's revalidation paragraph (`README.md:425-444`) still describes the recut as "hands the ticket back to `triage`" and says nothing about an approval surviving it. Nothing there is now false, so this is silence, not drift. The gate's behaviour changed for the human who reads that paragraph.

3. non-blocking. "byte-identical" is looser than it reads: `sections()` returns each body `.strip()`ed, so a trailing-newline edit inside the three sections still carries the approval. The compared text is what `plan_text()` prints, so the guarantee holds. The 04:25:00Z entry said the same.

Verified against the criteria I can check without running anything: `grep -c "^PLAN_SECTIONS = "` prints `0` for `pipeline/cli/main.py` and `1` for `pipeline/core/ticket.py` (criterion 5); the only other reference is `pipeline/cli/main.py:231` inside the unchanged `plan_text()`, so DEC-073 keeps one list and one owner. All three node ids named in criterion 3 exist (`tests/test_machine.py:295` is `test_a_rebase_conflict_returns_to_triage_and_is_bounded`). `finish_gate()` returns `GATE_PASS` before `advance()` for a Tier A PASS at `plan-validation` (`pipeline/daemon/supervisor.py:1134`), so the carry-forward cannot skip the Tier B agent. `tampered` compares the agent's frontmatter against the pre-spawn snapshot (`pipeline/daemon/supervisor.py:1273`), so a stage forging `approved_plan_hash` escalates; `advance()`'s pop runs after that comparison and before `t.save()`, so it persists. Each new test is non-vacuous: dropping the `if gate == "awaiting-approval"` guard reds `test_approving_at_the_merge_gate_records_no_plan_hash`, dropping the `advance()` rewrite reds `test_a_forged_approved_result_cannot_skip_the_human_gate`, and dropping the pop reds `test_implementing_voids_a_carried_approval`.

**unverified:** I ran no test. `uv run --group dev pytest` is not on this project's read-only allowlist (`[readonly] allow` in `.project/pipeline.toml`), so every claim above rests on reading the diff, `pipeline/cli/main.py`, `pipeline/core/machine.py`, `pipeline/core/ticket.py`, `pipeline/daemon/supervisor.py`, the three test files and `README.md`. I would have run the four suites of criterion 4.

long: eight quoted anchors plus the refutation each blocking finding owes.

### 2026-09-20 04:40:47Z · review · session · session=3c6428ec-9f99-4cf9-8540-460b12498d51

`review` ran as session `3c6428ec-9f99-4cf9-8540-460b12498d51`
- replay: `claude --resume 3c6428ec-9f99-4cf9-8540-460b12498d51`
- log: `.project/logs/TICKET-144-review-3c6428ec.log`
- cost: $2.50 of a $5 cap
- tokens: 28,596 out (19,995 thinking) · 54 in · 1,841,963 cache read · 86,674 cache write

### 2026-09-20 04:40:47Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ 1 blocking: `pipeline resume --stage implementing` keeps `approved_plan_hash`, so a resumed ticket that blocks carries its approval into `revalidating`'s `git reset --hard` (DEC-029)

### 2026-09-20 05:20:00Z · implementing · finding · severity=info

**Review's blocking finding fixed in `cdaabb1`.** `start()` now pops `approved_plan_hash` in a new `if stage == "implementing"` block above `t.take_lease()`, so every implementing spawn drops the approval however the stage was set, including `pipeline resume --stage implementing`. The `advance()` pop stays; both paths now hold.

Todo: [x] red test · [x] pop in `start()` · [x] suites green.

Red first: `test_spawning_implementing_voids_an_approval_however_the_stage_was_set` failed with `AssertionError: a resumed implementing ticket kept its approval`. It fails again if the `start()` pop is removed. Then it sets `plan-validation`, advances `ok`, and asserts `awaiting-approval`.

Verified: `uv run --group dev pytest -q tests/test_ticket.py tests/test_cli.py tests/test_machine.py tests/test_dispatch.py tests/test_stages.py` printed `336 passed`.

Not done: review finding 2 (README silence) and 3 (strip looseness) were non-blocking; I left both.

### 2026-09-20 04:42:18Z · implementing · session · session=30ecade6-a248-415c-9748-731e6c2446bd

`implementing` ran as session `30ecade6-a248-415c-9748-731e6c2446bd`
- replay: `claude --resume 30ecade6-a248-415c-9748-731e6c2446bd`
- log: `.project/logs/TICKET-144-implementing-30ecade6.log`
- cost: $0.28 of a $9 cap
- tokens: 4,001 out (452 thinking) · 18 in · 352,366 cache read · 43,468 cache write

### 2026-09-20 04:42:18Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ start() now drops approved_plan_hash on every implementing spawn, closing the pipeline resume door to DEC-029's reset; 336 tests pass

### 2026-09-20 05:45:00Z · review · finding · severity=info

**PASS, no blocking finding.** Reviewed the delta since the 05:05:00Z review: `cdaabb1` alone, 2 files, +33/-0.

The previous blocking finding is resolved. `start()` pops `approved_plan_hash` at `pipeline/daemon/supervisor.py:977-982`, above `t.take_lease()` and `t.save()`, so every `implementing` spawn drops it however `stage` was set. Two checks the fix depends on, both hold: `rec["meta"] = t` (line 1004) is that same popped object, so `_finish()`'s `t = replace(snap, body=agent_body)` (line 1281) cannot restore the hash; and `tampered` compares the agent's frontmatter against the same popped snapshot, so the pop raises no false escalation. The pop precedes any commit the agent makes, which is the moment DEC-029 needs.

`test_spawning_implementing_voids_an_approval_however_the_stage_was_set` is non-vacuous: remove the pop and both `assert "approved_plan_hash" not in t.extra` and the `awaiting-approval` assertion go red. No existing test asserts the hash survives an implementing spawn (`grep -rn approved_plan_hash`, 20 hits, none).

Criterion 5 still holds: `grep -c "^PLAN_SECTIONS = "` prints `0` for `pipeline/cli/main.py` and `1` for `pipeline/core/ticket.py`.

Three non-blocking notes:

1. non-blocking. A gap the chosen fix does not close, and neither option in the 05:05:00Z finding would have: a human runs `pipeline resume --stage implementing`, commits in the worktree by hand without the dispatcher ever spawning the stage, then runs `pipeline resume --stage plan-validation`. No spawn means no pop, so the approval carries and a conflict resets their commits. It needs a human hand-committing at both ends, so it is not the unattended destruction DEC-029 forbids.
2. non-blocking, carried. `README.md:425-444` still says nothing about an approval surviving the recut. The implementer left it deliberately.
3. non-blocking, carried. `sections()` strips each body, so a trailing-newline edit inside the three sections still carries the approval. The compared text is what `plan_text()` prints.

**unverified:** I ran no test. `uv run --group dev pytest` is not on `[readonly] allow` in `.project/pipeline.toml`, so the implementer's `336 passed` is unchecked here; every claim above rests on reading the diff, `pipeline/daemon/supervisor.py`, `pipeline/core/machine.py`, `pipeline/core/ticket.py` and `tests/test_dispatch.py`. I would have run the four suites of criterion 4.

long: a pass still owes the two snapshot checks the fix depends on, plus the gap it leaves.

### 2026-09-20 04:45:01Z · review · session · session=45ae8c7e-a27c-4933-9905-f066576eb5a4

`review` ran as session `45ae8c7e-a27c-4933-9905-f066576eb5a4`
- replay: `claude --resume 45ae8c7e-a27c-4933-9905-f066576eb5a4`
- log: `.project/logs/TICKET-144-review-45ae8c7e.log`
- cost: $1.48 of a $5 cap
- tokens: 12,567 out (7,407 thinking) · 46 in · 1,134,261 cache read · 60,342 cache write

### 2026-09-20 04:45:01Z · review · transition · to=holistic-review · result=ok · marker=yes

**review -> holistic-review** (result: `ok`)

✓ the resume door is closed: start() pops approved_plan_hash on every implementing spawn, and the pop lands in the pre-spawn snapshot so _finish() cannot restore it

### 2026-09-20 06:00:00Z · holistic-review · finding · severity=info

**PASS, coherent.** Reviewed `main...HEAD` whole: 6 commits, 7 files, +225/-8, against `## Plan`.

The sum is the plan. Each of the six steps landed in its own commit and nothing later removed an earlier one: `plan_digest`, `replace_section`, `SAFE_HASH` and the moved `PLAN_SECTIONS` (`f4f908c`), the `("plan-validation", "approved")` row and `CONTROL_FIELDS` (`a620804`), the dispatcher tests (`6d2cccc`), `approval_carries()` plus both `advance()` inserts (`1115917`), and the review fix (`cdaabb1`).

The two pops do not overlap. `advance()` pops at `if nxt == "implementing"` (`pipeline/daemon/supervisor.py:136`); `start()` pops at `if stage == "implementing"` (line 982), above `t.take_lease()` and `rec["meta"] = t`. The second covers the route the first cannot see (`pipeline resume --stage implementing`). Neither commit weakened the other.

One hash writer (`pipeline/cli/main.py:328`) and one clearer (`:356`). No third site writes the key.

Error handling is consistent across the four source files: `validate_meta()` appends to `bad` like every neighbouring field, `approval_carries()` is total on a hostile `extra` value (`str(...)` then compare), and `advance()` recomputes the verdict rather than trusting the sidecar word.

Nothing unasked landed. Three test functions exceed the plan's list -- `test_a_rejection_clears_the_recorded_approval`, `test_approving_at_the_merge_gate_records_no_plan_hash`, `test_a_malformed_approved_plan_hash_is_refused` -- and each asserts a claim `## Decisions` already makes. No production line lacks a criterion.

Two notes, neither a finding:

1. `("revalidating", "fail")` charges `stale_regate` back to `planning` (`pipeline/core/machine.py:228`) and no code clears the hash there. If `planning` reproduces the three sections byte-identically, the ticket revalidates without a human. The branch carries no implementation commit on that path, so DEC-029 holds, and `stale_regate` charges each lap, so the loop stays bounded. This is the design `## Decisions` states, not drift.
2. `## Summary` consequence 1 -- charging a conflict confined to files whose two sides could both be kept -- is still unimplemented, as `plan-validation` said at 04:05:00Z. The Expected clause and the criteria ask for the approval carry-forward only.

Criterion 5 verified: `grep -c "^PLAN_SECTIONS = "` prints `0` for `pipeline/cli/main.py` and `1` for `pipeline/core/ticket.py`. The only other use is `plan_text()` at `pipeline/cli/main.py:231`, so DEC-073 keeps one list.

**unverified:** I ran no test. `uv run --group dev pytest` is not on this project's read-only allowlist -- `[readonly] allow` in `.project/pipeline.toml` lists five `pipeline` subcommands and `./pipeline/hooks/test_dangerous_commands.py`. Every claim above rests on the diff and on reading `pipeline/cli/main.py`, `pipeline/core/machine.py`, `pipeline/core/ticket.py`, `pipeline/daemon/supervisor.py` and the three test files. I would have run the four suites of criterion 4.

long: a coherence verdict owes the per-step trace plus the two carried notes.

### 2026-09-20 04:47:19Z · holistic-review · session · session=4238ddf7-217e-489f-97c1-4523706fdd4e

`holistic-review` ran as session `4238ddf7-217e-489f-97c1-4523706fdd4e`
- replay: `claude --resume 4238ddf7-217e-489f-97c1-4523706fdd4e`
- log: `.project/logs/TICKET-144-holistic-review-4238ddf7.log`
- cost: $1.39 of a $5 cap
- tokens: 11,155 out (4,556 thinking) · 38 in · 935,188 cache read · 64,293 cache write

### 2026-09-20 04:47:19Z · holistic-review · transition · to=verifying · result=ok · marker=yes

**holistic-review -> verifying** (result: `ok`)

✓ the six plan steps and the review fix land as one coherent change: one hash writer, one clearer, two pops that do not overlap, no step undone

### 2026-09-20 04:48:36Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/core/machine.py:transition`
- `pipeline/core/machine.py:CONTROL_FIELDS`
- `pipeline/core/ticket.py:validate_meta`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-144` lands it; `pipeline resume TICKET-144 --stage planning` sends it back.

### 2026-09-20 04:58:01Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-20 04:58:08Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/144


Current branch ticket/144 is up to date.
Already up to date.
Updating 519a4e1..cdaabb1
Fast-forward
 pipeline/cli/main.py          |  13 ++---
 pipeline/core/machine.py      |   9 ++++
 pipeline/core/ticket.py       |  21 ++++++++
 pipeline/daemon/supervisor.py |  24 ++++++++-
 tests/test_dispatch.py        | 122 +++++++++++++++++++++++++++++++++++++++++-
 tests/test_machine.py         |  12 +++++
 tests/test_ticket.py          |  32 +++++++++++
 7 files changed, 225 insertions(+), 8 deletions(-)

```

### 2026-09-20 04:58:08Z · merging · decision

decision recorded as `DEC-144`
