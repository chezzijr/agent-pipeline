---
id: TICKET-143
stage: done
class: feature
branch: ticket/143
test_file: tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
files_declared:
- README.md
- pipeline/core/config.py
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- pipeline/templates/pipeline.toml
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_config.py
- tests/test_dispatch.py
- tests/test_machine.py
- tests/test_stages.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 5
  plan_files: 10
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 97d496c2-1218-42da-9b58-cc8be6e1c46e
  replay: claude --resume 97d496c2-1218-42da-9b58-cc8be6e1c46e
  log: .project/logs/TICKET-143-review-97d496c2.log
  cost_usd: 1.5724984999999994
approved_by: chezzijr
approved_at: '2026-09-20T03:56:01.250809+00:00'
---

## Summary

Every ticket declaring a shared ledger file serializes the whole queue

Expected change files: `pipeline/core/machine.py`, `pipeline/core/config.py`, `pipeline/templates/pipeline.toml`, `README.md`, `tests/test_machine.py`, `tests/test_config.py`.

`conflict_holder()` intersects the two tickets' raw `files_declared` -- `pipeline/core/machine.py:335`, on main at f9d1063:

    mine = set(meta.get("files_declared") or [])
    for o in inflight_meta:
        overlap = mine & set(o.get("files_declared") or [])
        if overlap:
            return (str(o.get("id") or "?"), sorted(overlap)[0])

Every file counts the same, and there is no way to exempt one. In a real project every ticket appends to `PROGRESS.md` and `docs/gaps.md`, so every ticket overlapped every other ticket and exactly one could run at a time: 71.7 hours were spent in the `waiting` state against roughly 12 hours of stage work. `pipeline ls` reported `waiting on TICKET-NNN (PROGRESS.md)` throughout.

Expected: a project can declare files that do not order two tickets, e.g. `[conflict] ignore = ["PROGRESS.md", "docs/gaps.md"]` in `.project/pipeline.toml`, and two tickets whose only overlap is an ignored file both run. A shared code file still orders them: ignoring is per-path and opt-in, never a default, and a bad value is printed and ignored like `max_parallel`. `start()` keeps using the same `waiting` key for a real overlap. Tests: `conflict_holder()` with an ignore list returns `None` for a ledger-only overlap and still returns the holder when a declared code file overlaps; the config reader rejects a non-list value without raising.

## Reproduction

Test: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file`

Command: `uv run --group dev pytest -q tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file`

Failure:

```text
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'
```

expect: TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

## Digest

- `pipeline/core/machine.py:331`: `conflict_holder(meta, inflight_meta)` intersects raw `files_declared` and returns `(holder id, sorted(overlap)[0])`. `files_conflict()` at line 343 is its bool wrapper and has no caller under `pipeline/`.
- `pipeline/daemon/supervisor.py:895`: `start()` calls `conflict_holder()` on `inflight`; line 898 calls it a SECOND time on `parked_meta(project, tid)`, at `merging` only; line 899 is the single `note_wait()`. Both calls need the ignore set, and only a `merging`-versus-parked test can tell a one-call wiring from a two-call one.
- `pipeline/core/config.py:501` `readonly_allow()` and `:533` `project_max_parallel()` are the reader shape to copy. Both read `project_config()` (line 145), which serves HEAD. The file already imports `PipelineError` and `notice_once` at line 17.
- `notice_once(message, *key)` (`pipeline/core/__init__.py:28`) prints a setup fact once per key; `reset_notices()` is the test seam, used with `capsys` at `tests/test_config.py:132`.
- Fixtures: `project()` (no git repo) and `git_project()` in `tests/helpers.py`; `harness` is `pipeline.core.config.harness`, already imported at `tests/test_dispatch.py:19`. `FIXTURE` declares `files_declared: [thing.py]` and `stage: plan-validation`.
- Parked-gate fixtures to copy: `tests/test_dispatch.py:1710` `test_a_merge_waits_behind_a_ticket_parked_at_a_human_gate` and `:1735` `test_a_merge_is_not_held_by_a_parked_ticket_that_shares_no_file`. The inflight stand-in pattern is `tests/test_daemon.py:582`.
- `tests/test_stages.py:461` asserts a knob tuple against `pipeline/templates/skills/pipeline-config/SKILL.md:261`, the line listing the keys documented only in `pipeline/templates/pipeline.toml`.
- Gotcha: `start()` returns on a wait BEFORE `project_config()` and `ensure_worktree()`, so a wait test needs no git repo; a start test does.
- Gotcha: ignore entries are exact paths. No globs, no directory prefixes.
- Gotcha: subtracting the ignore set from `mine` alone is enough -- the intersection can then never contain an ignored path.
- Gotcha: `project_config()` raises `PipelineError` when a project has no config, and `tomllib` raises `ValueError` on malformed TOML. The reader catches both.

## Decisions checked

- DEC-037 and DEC-075: project config is read from HEAD, or from the pinned private copy, through `project_config()`. The new reader goes through it, so a ticket branch cannot grant itself an ignore list.
- DEC-048: `waiting` stays advisory, is recomputed each tick, and is written by the one `note_wait()` call. This plan adds no second call.
- DEC-105: the parked-ticket check stays inside the `merging` branch and folds into that same single `note_wait()`. This plan filters the existing call, it does not move it.
- DEC-029: refused to widen `files_conflict` to every non-terminal ticket. This plan narrows ordering, never widens it, so that refusal is untouched.
- DEC-047: a padded `files_declared` serialises a ticket against every other one. `[conflict] ignore` is the project's opt-in list of paths that must not carry that cost; it is never a default.
- DEC-094: the per-project cap is consulted inside `tick()`, not threaded through `serve()`. The ignore set is likewise read inside `start()`, not passed down from the daemon.
- DEC-069 is advisory history, superseded-by DEC-094. Its surviving ruling -- a bad `max_parallel` never raises out of `tick()`, it is printed and ignored -- is the model for a bad `[conflict] ignore`.

## Plan

1. Add `test_conflict_holder_still_orders_a_code_file_beside_an_ignored_ledger` to `tests/test_machine.py`, beside the committed repro at line 168, then implement the `ignored` parameter in `pipeline/core/machine.py` until both tests pass.
    - The new test in `tests/test_machine.py`: `mine = {"files_declared": ["PROGRESS.md", "thing.py"]}`; `inflight = [{"id": "TICKET-004", "files_declared": ["PROGRESS.md", "thing.py"]}]`; assert `M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) == ("TICKET-004", "thing.py")`; assert `M.conflict_holder(mine, inflight) == ("TICKET-004", "PROGRESS.md")` for the unignored default; assert `M.files_conflict(mine, inflight, ignored={"PROGRESS.md", "thing.py"}) is False`.
    - In `pipeline/core/machine.py`, `conflict_holder(meta: dict, inflight_meta: list[dict], ignored: set[str] = frozenset()) -> tuple[str, str] | None` computes `mine = set(meta.get("files_declared") or []) - set(ignored)` and is otherwise unchanged; `files_conflict(meta, inflight_meta, ignored=frozenset())` returns `conflict_holder(meta, inflight_meta, ignored) is not None`.
    - Docstring sentence to add to `conflict_holder()` in `pipeline/core/machine.py`: `ignored` holds the exact paths a project exempts through `[conflict] ignore`; an exempt path never orders two tickets, and any other shared path still does.
    - Run `uv run --group dev pytest -q tests/test_machine.py`, then commit `pipeline/core/machine.py` and `tests/test_machine.py` as `feat(TICKET-143): exempt configured paths from conflict ordering`.
2. Add two reader tests to `tests/test_config.py`, then add `project_conflict_ignore()` to `pipeline/core/config.py` until both pass.
    - `test_project_conflict_ignore_reads_the_committed_list` in `tests/test_config.py`: `d, sh = git_project()`; write `.project/pipeline.toml` holding `base="main"` and a `[conflict]` table whose `ignore = ["PROGRESS.md", "docs/gaps.md"]`; commit it with `sh("git add -A && git commit -qm 'ignore the ledgers'")`; assert `project_conflict_ignore(d) == {"PROGRESS.md", "docs/gaps.md"}`; then rewrite the file on disk with a third entry, leave it uncommitted, and assert the returned set is unchanged (HEAD wins, DEC-037).
    - `test_project_conflict_ignore_ignores_a_bad_value(capsys)` in `tests/test_config.py`: call `reset_notices()`; commit a `[conflict]` table whose `ignore = "PROGRESS.md"` is a string, not a list; assert `project_conflict_ignore(d) == set()` and that the call did not raise; assert `"ignoring [conflict] ignore"` appears in `capsys.readouterr().out`; repeat with `ignore = ["PROGRESS.md", 7]`, and with a top-level `conflict = "yes"`, each asserting `set()`.
    - In `pipeline/core/config.py`, place `project_conflict_ignore(project: Path) -> set[str]` directly after `project_max_parallel()`: wrap `project_config(project)` in `try` with `except (PipelineError, ValueError): return set()`; read `table = cfg.get("conflict") or {}`; when `table` is not a dict, or `table.get("ignore") or []` is not a list, or any entry is not a non-empty `str`, call `notice_once(f"  {project}: ignoring [conflict] ignore ({reason})", str(project), "conflict-ignore")` and return `set()`; otherwise return the set of entries.
    - Docstring for the new reader in `pipeline/core/config.py`: it never raises, because ordering must survive a bad value -- a fault returns the empty set, the behaviour from before the key existed, which is the DEC-069 model -- and `notice_once()` keeps one broken project from printing on every tick.
    - Run `uv run --group dev pytest -q tests/test_config.py`, then commit `pipeline/core/config.py` and `tests/test_config.py` as `feat(TICKET-143): read [conflict] ignore from the project config`.
3. Add five dispatcher tests to `tests/test_dispatch.py`, then pass the ignore set into BOTH `conflict_holder()` calls in `pipeline/daemon/supervisor.py` until all five pass.
    - Setup shared by the three wait cases, written inline in each test in `tests/test_dispatch.py`: `d = project()`, then append to `d / ".project/pipeline.toml"` a `[conflict]` table whose `ignore = ["PROGRESS.md"]`. That project is not a git repo, so `project_config()` reads the file off disk.
    - `test_conflict_ignore_lets_two_ledger_only_tickets_run_together` in `tests/test_dispatch.py`: `d, sh = git_project()`; append the same `[conflict]` table to `d / ".project/pipeline.toml"`; write `TICKET-001.md` from `FIXTURE` with `stage: merging` and `files_declared: [PROGRESS.md]`; build the inflight stand-in as `tests/test_daemon.py:582` does, with `t2 = Ticket.find(d, "TICKET-001")`, `t2.id = "TICKET-002"`, `t2.frontmatter()["files_declared"] = ["PROGRESS.md"]`, `inflight = {"TICKET-002": {"meta": t2}}`; create the worktree with `supervisor.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})` and commit a file inside it as the fixture at `tests/test_dispatch.py:1735` does; assert `did and rec["kind"] == "merge"`; then `rec["proc"].wait()`, `supervisor.finish(d, rec)`, `shutil.rmtree(d, ignore_errors=True)`.
    - `test_conflict_ignore_still_holds_a_ticket_on_a_declared_code_file` in `tests/test_dispatch.py`: `d = project()` with the `[conflict]` table; the on-disk ticket declares `["PROGRESS.md", "thing.py"]` and the inflight stand-in declares the same two; assert `(did, rec) == (False, None)`, then read `Ticket.find(d, "TICKET-001").extra["waiting"]` and assert its `["on"] == "TICKET-002"` and its `["file"] == "thing.py"`.
    - `test_conflict_ignore_frees_a_merge_from_a_parked_ledger_overlap` in `tests/test_dispatch.py`: copy the fixture at `tests/test_dispatch.py:1735`; TICKET-001 sits at `awaiting-approval` with `files_declared: [PROGRESS.md]`, TICKET-002 sits at `merging` with `files_declared: [PROGRESS.md]`, and the config carries the `[conflict]` table; assert `did and rec["kind"] == "merge"`; this is the case that fails when only the call at line 895 receives the ignore set and the `parked_meta()` call at line 898 does not.
    - `test_a_parked_code_file_overlap_still_holds_a_merge_under_an_ignore_list` in `tests/test_dispatch.py`: copy the fixture at `tests/test_dispatch.py:1710`; both tickets declare `[PROGRESS.md, thing.py]` and the config carries the `[conflict]` table; assert `(did, rec) == (False, None)`, `waiting["on"] == "TICKET-001"`, and `waiting["file"] == "thing.py"`.
    - `test_a_bad_conflict_ignore_preserves_file_ordering` in `tests/test_dispatch.py`: `d = project()` whose `[conflict]` table sets the string `ignore = "PROGRESS.md"`; call `reset_notices()`; the ticket and the inflight stand-in each declare only `PROGRESS.md`; assert `(did, rec) == (False, None)` and `waiting["file"] == "PROGRESS.md"`, so a bad value cannot weaken ordering.
    - In `pipeline/daemon/supervisor.py`, add `project_conflict_ignore` to the `pipeline.core.config` import list at line 30, insert `ignored = project_conflict_ignore(project)` above line 895, and pass `ignored` as the third argument to the `conflict_holder()` call at line 895 AND to the one at line 898. Add no second `note_wait()` (DEC-048, DEC-105).
    - Run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_daemon.py`, then commit `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py` as `feat(TICKET-143): honour [conflict] ignore in both overlap checks`.
4. Document the knob in `pipeline/templates/pipeline.toml`, `README.md` and `pipeline/templates/skills/pipeline-config/SKILL.md`, and extend the knob tuple in `tests/test_stages.py`.
    - In `pipeline/templates/pipeline.toml`, after the `max_parallel` comment block, add commented lines saying: these are the paths that must not order two tickets; every ticket appends to a shared ledger such as PROGRESS.md or docs/gaps.md, and two tickets whose ONLY shared file is one of these run in parallel instead of queueing; entries are exact paths, not globs; any other shared file still orders them; a bad value is reported and ignored. Close the block with a commented example `[conflict]` table and `ignore = ["PROGRESS.md", "docs/gaps.md"]`.
    - In `README.md`, inside the `## Concurrency` section after the `max_parallel` paragraph near line 385, add one paragraph plus a fenced `toml` block showing the `[conflict]` table with `ignore = ["PROGRESS.md", "docs/gaps.md"]`, stating that paths are exact, that a shared code file still orders two tickets, and that the key is read from HEAD like the rest of the file.
    - In `pipeline/templates/skills/pipeline-config/SKILL.md` at line 261, extend the "Still in the file's own comments" sentence so it names `[conflict] ignore` beside `[readonly] allow` and `max_parallel`.
    - In `tests/test_stages.py` at line 469, add `"conflict"` to the knob tuple in `test_the_config_skill_names_every_knob_the_code_reads`.
    - Run `uv run --group dev pytest -q tests/test_stages.py`, then commit `pipeline/templates/pipeline.toml`, `README.md`, `pipeline/templates/skills/pipeline-config/SKILL.md` and `tests/test_stages.py` as `docs(TICKET-143): document [conflict] ignore`.
5. Run the whole suite and the guard from the worktree root, fix any regression in `pipeline/core/machine.py`, `pipeline/core/config.py` or `pipeline/daemon/supervisor.py`, and commit.
    - Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`; both are expected to exit 0.
    - Commit any fix to `pipeline/daemon/supervisor.py` or the other two code files as `fix(TICKET-143): <what broke>`; with nothing to fix, step 4's commit is the last one.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` exits 0.
- `uv run --group dev pytest -q tests/test_machine.py::test_conflict_holder_still_orders_a_code_file_beside_an_ignored_ledger` exits 0.
- `uv run --group dev pytest -q tests/test_config.py::test_project_conflict_ignore_reads_the_committed_list` exits 0.
- `uv run --group dev pytest -q tests/test_config.py::test_project_conflict_ignore_ignores_a_bad_value` exits 0.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_conflict_ignore_lets_two_ledger_only_tickets_run_together` exits 0.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_conflict_ignore_still_holds_a_ticket_on_a_declared_code_file` exits 0.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_conflict_ignore_frees_a_merge_from_a_parked_ledger_overlap` exits 0.
    This criterion fails when only the `inflight` call at `pipeline/daemon/supervisor.py:895` receives the ignore set.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_parked_code_file_overlap_still_holds_a_merge_under_an_ignore_list` exits 0.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_bad_conflict_ignore_preserves_file_ordering` exits 0.
- `uv run --group dev pytest -q tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads` exits 0.
- `grep -n conflict pipeline/templates/pipeline.toml README.md pipeline/templates/skills/pipeline-config/SKILL.md` exits 0 and prints at least one line for each of the three files.
- `grep -c ignored pipeline/daemon/supervisor.py` prints a number three or higher: the read plus both `conflict_holder()` calls.
- `uv run --group dev pytest -q` exits 0, with no failure other than this ticket's own tests.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

- `[conflict] ignore` matches complete `files_declared` paths only. It interprets no globs and no directory prefixes, so `docs/` does not cover `docs/gaps.md`.
- An ignored path removes only itself from an overlap. Any remaining shared path still orders the two tickets and still supplies the file `note_wait()` displays.
- A bad `[conflict]` table, a non-list `ignore`, or a non-string entry prints once through `notice_once()` and yields an EMPTY ignore set, never a wide one. Ordering is the safe direction: bad configuration must not let two tickets collide.
- `project_conflict_ignore()` does not raise, unlike `project_max_parallel()` and `readonly_allow()` beside it. A raise would reach `start()` on the ordering path, where the safe answer is already known: keep ordering everything.
- The same ignore set governs both overlap checks in `start()` -- the `inflight` one and the `merging`-only `parked_meta()` one. Filtering only the first leaves a ledger file ordering every merge behind a parked ticket, which is this ticket's bug one code path later.
- The set is read inside `start()`, not threaded in from `run()` or `serve()` (DEC-094), and it is read through `project_config()`, so a ticket branch cannot exempt its own files (DEC-037).

## Rollback

Revert the TICKET-143 commits to restore all-path ordering; nothing else reads `[conflict] ignore`, and an absent key already means the empty set. Step 3 is the riskiest step: it changes live dispatcher ordering, and a wrong ignore set lets two tickets touching one code file run together. Fallback when any of step 3's five tests stays red: revert the `pipeline/daemon/supervisor.py` edit, leave `conflict_holder()`'s parameter defaulting to the empty set -- steps 1 and 2 stay landable and change no behaviour -- and drop step 4's documentation.

## Thread

### 2026-09-20 01:53:54Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-20 02:00:00Z · triage · reproduction

Reproduced and committed `ceb30b2`.

`conflict_holder()` intersects every declared path and accepts no ignore list.

`project_config()` already supplies project settings from committed configuration.
`readonly_allow()` and `project_max_parallel()` provide the nearest configuration-validation patterns.

The new test has only `PROGRESS.md` in both tickets.
It fails with the recorded `TypeError`, before the intended no-holder result.

### 2026-09-20 01:55:18Z · triage · session · session=01a0bc85-2537-7a72-8563-ddee57f6e1c9

`triage` ran as session `01a0bc85-2537-7a72-8563-ddee57f6e1c9`
- replay: `codex exec resume 01a0bc85-2537-7a72-8563-ddee57f6e1c9`
- log: `.project/logs/TICKET-143-triage-da5a715a.log`
- cost: unknown (the harness reported none)
- tokens: 2,568 out (743 thinking) · 399,806 in · 366,592 cache read · 0 cache write

### 2026-09-20 01:55:18Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Added and committed a failing ignored-ledger overlap regression.

### 2026-09-20 01:59:42Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails as required
```
9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-143
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
______________ test_conflict_holder_ignores_a_shared_ledger_file _______________

    def test_conflict_holder_ignores_a_shared_ledger_file():
        """An opt-in ledger ignore must not serialize otherwise independent tickets."""
        mine = {"files_declared": ["PROGRESS.md"]}
        inflight = [{"id": "TICKET-004", "files_declared": ["PROGRESS.md"]}]
    
>       assert M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) is None
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

tests/test_machine.py:173: TypeError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails on base `main` too -- the bug is not already fixed upstream
```
": "TICKET-004", "files_declared": ["PROGRESS.md"]}]
    
>       assert M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) is None
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

tests/test_machine.py:173: TypeError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-e4c8yma9/base
      Built pipeline @ file:///tmp/pipeline-base-e4c8yma9/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 76ms

```
- ok: DEC-069 is superseded -- history, not binding
- `files_declared` is empty
- plan step names no declared file: '1. Extend `tests/test_machine.py` with ignored-only and ignored-plus-code overlaps, expecting `None` then the deterministic code-file holder; run the focused tests and commit the failing cases.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Add `tests/test_config.py` validation cases and `tests/test_dispatch.py` end-to-end cases proving valid ignores permit parallel ledger work while invalid values warn and preserve ordering.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Implement exact-path filtering in `pipeline/core/machine.py`, add the fail-closed reader in `pipeline/core/config.py`, and pass its result through both `pipeline/daemon/supervisor.py` overlap checks.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '4. Document `[conflict] ignore` in `pipeline/templates/pipeline.toml`, `README.md`, and `pipeline/templates/skills/pipeline-config/SKILL.md`; extend `tests/test_stages.py` to keep the skill interface synchronized.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '5. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`; commit the passing implementation and documentation as `feat(TICKET-143): ignore configured conflict paths`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-20 02:01:21Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails as required
```
9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-143
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
______________ test_conflict_holder_ignores_a_shared_ledger_file _______________

    def test_conflict_holder_ignores_a_shared_ledger_file():
        """An opt-in ledger ignore must not serialize otherwise independent tickets."""
        mine = {"files_declared": ["PROGRESS.md"]}
        inflight = [{"id": "TICKET-004", "files_declared": ["PROGRESS.md"]}]
    
>       assert M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) is None
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

tests/test_machine.py:173: TypeError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails on base `main` too -- the bug is not already fixed upstream
```
": "TICKET-004", "files_declared": ["PROGRESS.md"]}]
    
>       assert M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) is None
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

tests/test_machine.py:173: TypeError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-vvknd1jf/base
      Built pipeline @ file:///tmp/pipeline-base-vvknd1jf/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 49ms

```
- ok: DEC-069 is superseded -- history, not binding
- `files_declared` is empty
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '1. Extend `tests/test_machine.py` with ignored-only and ignored-plus-code overlaps, expecting `None` then the deterministic code-file holder; run the focused tests and commit the failing cases.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '2. Add `tests/test_config.py` validation cases and `tests/test_dispatch.py` end-to-end cases proving valid ignores permit parallel ledger work while invalid values warn and preserve ordering.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '3. Implement exact-path filtering in `pipeline/core/machine.py`, add the fail-closed reader in `pipeline/core/config.py`, and pass its result through both `pipeline/daemon/supervisor.py` overlap checks.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '4. Document `[conflict] ignore` in `pipeline/templates/pipeline.toml`, `README.md`, and `pipeline/templates/skills/pipeline-config/SKILL.md`; extend `tests/test_stages.py` to keep the skill interface synchronized.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '5. Validate `pipeline/core/machine.py` and `README.md` with `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`; commit as `feat(TICKET-143): ignore configured conflict paths`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-09-20 02:01:46Z · planning · plan

Planned an exact-path `[conflict] ignore` setting with fail-closed validation.

The implementation passes one ignore set to active and merge-only parked overlap checks. A remaining code-file overlap still reports its deterministic holder through the existing `waiting` path.

The file map adds `pipeline/daemon/supervisor.py` for runtime wiring. It adds the packaged configuration skill and its contract test for interface consistency.

Consulted DEC-037, DEC-048, DEC-075, DEC-105, and DEC-094. DEC-069 supplies advisory history for invalid-setting fallback.

Tier A reproduced the committed test on the branch and base. Its only findings were the allowed pre-sidecar `files_declared` findings.

### 2026-09-20 02:02:06Z · planning · session · session=01a0bc86-6616-7fe2-889a-bd120a44a879

`planning` ran as session `01a0bc86-6616-7fe2-889a-bd120a44a879`
- replay: `codex exec resume 01a0bc86-6616-7fe2-889a-bd120a44a879`
- log: `.project/logs/TICKET-143-planning-7602bbcc.log`
- cost: unknown (the harness reported none)
- tokens: 11,061 out (6,802 thinking) · 1,591,093 in · 1,511,424 cache read · 0 cache write

### 2026-09-20 02:02:06Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned exact-path conflict ignores with fail-closed configuration and dispatcher coverage.

### 2026-09-20 02:38:14Z · plan-validation · note

`plan-validation` was interrupted; lease released

### 2026-09-20 03:16:25Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-20 02:01:21Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails on base `main` too -- the bug is not already fixed upstream
```
": "TICKET-004", "files_declared": ["PROGRESS.md"]}]
    
>       assert M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) is None
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

tests/test_machine.py:173: TypeError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-5m5e79ke/base
      Built pipeline @ file:///tmp/pipeline-base-5m5e79ke/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 74ms

```
- ok: DEC-069 is superseded -- history, not binding

### 2026-09-20 03:41:06Z · plan-validation · note

**Tier B: FAIL** -- one item fails: falsifiable criteria.

- fail: **falsifiable criteria.** No criterion distinguishes a one-call wiring from a two-call wiring. The Digest requires "both checks must receive the same ignore set", and `## Decisions` item 4 repeats it. An implementation that passes the ignore set to `pipeline/daemon/supervisor.py:895` and leaves `pipeline/daemon/supervisor.py:898` (`parked_meta()`) unfiltered still satisfies criteria 1-7: the default set is empty, so every existing test is unchanged. Remedy: add one `tests/test_dispatch.py` case in step 2 -- a `merging` ticket against a ticket parked at `awaiting-merge` whose only overlap is an ignored path -- plus a code-file case that still waits. `test_a_ticket_parked_at_a_human_gate_holds_no_file_claim` (`tests/test_dispatch.py:1664`) is the working fixture.
- ok: **root cause.** `conflict_holder()` (`pipeline/core/machine.py:335`) intersects raw `files_declared` and has no exemption, so a ledger every ticket appends to orders every pair. Step 3 plus criteria 3-4 fix that, not only the keyword the repro test calls.
- ok: **decision conflict.** DEC-037/DEC-075 (config from `project_config()`), DEC-048 (one advisory `note_wait()`), DEC-105 (the parked check stays `merging`-only) all constrain this plan, and the plan complies. DEC-069 is history; its print-and-ignore model matches `_start_cap()`.
- ok: **scope discipline.** 5 steps, 10 files, class `feature`. Steps 1-3 trace to criteria 1-4, step 4 to criterion 5, step 5 to criteria 6-7. No criterion asserts the `README.md` and `pipeline/templates/pipeline.toml` edits; `## Summary` names both files, so they stay in scope.
- ok: **no research left.** Every step names files; the Digest names `project_conflict_ignore()` and both `supervisor.py` call sites.
- ok: **riskiest step.** The plan names step 3 and states the fallback: keep the empty set, do not document the knob.
- ok: **regression surface.** Existing ordering is covered by `test_overlapping_tickets_do_not_run_together`, `test_conflict_holder_names_the_first_holder_and_its_file` and `tests/test_dispatch.py:1664`. An empty default ignore set leaves all three unchanged. `files_conflict()` has no caller under `pipeline/`, so its signature is safe.
- ok: **blast radius.** 3 code files, 4 test files, 3 doc files for a `feature`.

unverified: I did not run `uv run --group dev pytest -q`. I am read-only; my criteria judgment rests on reading `pipeline/core/machine.py`, `pipeline/core/config.py`, `pipeline/daemon/supervisor.py` and the existing tests.

long: eight scored items plus one unverified item, each with its evidence.

### 2026-09-20 03:41:57Z · plan-validation · session · session=a9d757bd-e3d0-490e-92ee-35125f34b924

`plan-validation` ran as session `a9d757bd-e3d0-490e-92ee-35125f34b924`
- replay: `claude --resume a9d757bd-e3d0-490e-92ee-35125f34b924`
- log: `.project/logs/TICKET-143-plan-validation-a9d757bd.log`
- cost: $1.29 of a $3 cap
- tokens: 13,887 out (6,362 thinking) · 32 in · 736,477 cache read · 56,944 cache write

### 2026-09-20 03:41:57Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ No criterion fails if only one of the two supervisor overlap checks gets the ignore set.

### 2026-09-20 03:50:21Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-20 02:01:21Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails on base `main` too -- the bug is not already fixed upstream
```
": "TICKET-004", "files_declared": ["PROGRESS.md"]}]
    
>       assert M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) is None
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

tests/test_machine.py:173: TypeError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jgqyo1wg/base
      Built pipeline @ file:///tmp/pipeline-base-jgqyo1wg/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 70ms

```
- ok: DEC-069 is superseded -- history, not binding

### 2026-09-20 04:00:00Z · planning · plan

Replanned after the Tier B rejection at 03:41:06Z. That review passed every item but one: "No criterion distinguishes a one-call wiring from a two-call wiring."

The fix is step 3 and its criteria. `tests/test_dispatch.py` now carries five named cases, and two of them exercise the `merging`-versus-parked path the old plan never asserted: `test_conflict_ignore_frees_a_merge_from_a_parked_ledger_overlap` fails when only `pipeline/daemon/supervisor.py:895` receives the ignore set, and `test_a_parked_code_file_overlap_still_holds_a_merge_under_an_ignore_list` fails when the parked check drops a real code overlap. Each of the five has its own acceptance criterion; the old plan named two dispatcher tests and neither touched `parked_meta()`.

Two further changes. Steps are now one test-and-code cycle each, so the implementer never writes code with no run between it and the next commit. `## Digest` carries the line numbers and fixtures the tests copy, including `tests/test_daemon.py:582` for the inflight stand-in and the fact that a wait case needs no git repo.

`## Decisions` records why `project_conflict_ignore()` does not raise where `project_max_parallel()` does.

I ran `pipeline --project /home/chezzijr/proj/agent-pipeline gate TICKET-143`: `gate: PASS`, no findings.

### 2026-09-20 03:51:08Z · planning · session · session=22ceed46-30b5-4b87-859c-3fc9feb6e775

`planning` ran as session `22ceed46-30b5-4b87-859c-3fc9feb6e775`
- replay: `claude --resume 22ceed46-30b5-4b87-859c-3fc9feb6e775`
- log: `.project/logs/TICKET-143-planning-22ceed46.log`
- cost: $3.31 of a $10 cap
- tokens: 40,614 out (10,772 thinking) · 58 in · 2,190,250 cache read · 120,341 cache write

### 2026-09-20 03:51:08Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Replanned: five dispatcher tests now fail a one-call wiring, the parked merge case included.

### 2026-09-20 03:52:15Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-09-20 02:01:21Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails on base `main` too -- the bug is not already fixed upstream
```
": "TICKET-004", "files_declared": ["PROGRESS.md"]}]
    
>       assert M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) is None
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

tests/test_machine.py:173: TypeError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jp5lf58u/base
      Built pipeline @ file:///tmp/pipeline-base-jp5lf58u/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 75ms

```
- ok: DEC-069 is superseded -- history, not binding

### 2026-09-20 04:20:00Z · plan-validation · note

**Tier B: PASS** -- eight items pass. One acceptance criterion is vacuous; I report it as a caveat, not as a scored finding.

long: eight scored items, each with its evidence.

- ok: **root cause.** `conflict_holder()` (`pipeline/core/machine.py:335`) intersects raw `files_declared` and offers no exemption, so one path every ticket declares orders every pair. Steps 1-3 subtract a project-owned set from that intersection. They do not special-case the repro's keyword.
- ok: **falsifiable criteria.** Criterion 7's test fails on a one-call wiring. With `inflight` empty the first call returns `None`, `start()` reaches `pipeline/daemon/supervisor.py:898`, an unfiltered `parked_meta()` call returns `("TICKET-001", "PROGRESS.md")`, and `assert did and rec["kind"] == "merge"` fails. Criteria 8 and 9 hold the two reverse directions: a parked code-file overlap still waits, and a bad value still orders.
- ok: **decision conflict.** DEC-037/DEC-075 (HEAD through `project_config()`), DEC-048 (one advisory `note_wait()`), DEC-105 ("Do not move this check up beside the `inflight` one"), DEC-094 (read inside the caller), DEC-069 (print and ignore). The plan complies with each; it filters both existing calls and adds none. DEC-047 names a padded `files_declared` as a deterrent -- "a padded `files_declared` serialises the ticket against every other ticket touching those files" -- and an ignored path drops that deterrent for itself. The plan states the compensating limit: the list is project-owned, read from HEAD, opt-in, never a default. No agent can exempt its own files.
- ok: **scope discipline.** class `feature`, `plan_steps: 5`, `plan_files: 10`, three of them code. Steps 1-3 trace to criteria 1-9, step 4 to criteria 10-11, step 5 to criteria 13-14.
- ok: **no research left.** Every step names the file, the function and the assertion. I checked the four fixtures the plan copies: `tests/test_dispatch.py:1710` and `:1735` exist as described, `tests/test_daemon.py:582` is the inflight stand-in, `tests/helpers.py` `git_project()` writes `.project/pipeline.toml` AFTER its only commit, so an appended `[conflict]` table is read off disk by `project_config()`'s fallback and the three git-backed step-3 tests need no extra commit.
- ok: **riskiest step.** The plan names step 3 and states the fallback: revert the `pipeline/daemon/supervisor.py` edit, keep the parameter defaulting to the empty set, drop step 4.
- ok: **regression surface.** The default `frozenset()` leaves every existing path byte-identical, and `tests/test_machine.py`'s conflict tests, `tests/test_daemon.py:582` and `tests/test_dispatch.py:1710`/`:1735` cover it; step 5 runs the whole suite. One new surface the plan does not name: `project_conflict_ignore()` sits above the wait decision, so `start()` now runs `project_config()` -- a `git show` subprocess -- for every ticket it considers, on a path that previously returned before any config read. It swallows `PipelineError`, so an unconfigured project still waits correctly.
- ok: **blast radius.** 10 files for a `feature` that changes one ordering rule, adds one reader, wires two call sites and documents one knob. Proportionate.

caveat, not a scored finding: acceptance criterion 12 is vacuous. `grep -c ignored pipeline/daemon/supervisor.py` prints `9` on `ceb30b2` today, before any implementation, because `git_ignored`, `ignore_errors` prose and `--permission-mode` comments already match. "three or higher" therefore passes on a one-call wiring and on no wiring at all. It costs nothing, since criterion 7 asserts the same property with a test that fails when only `pipeline/daemon/supervisor.py:895` receives the ignore set. The implementer must not read criterion 12 as evidence that both calls are wired.

Also noted, for the filer not for the plan: `## Summary`'s "Expected change files" line names six files; frontmatter `files_declared` names ten. The frontmatter list is the one that orders tickets, and it is the complete one.

### 2026-09-20 03:55:50Z · plan-validation · session · session=c52212d9-9ae6-4bd6-a295-778ac7d34231

`plan-validation` ran as session `c52212d9-9ae6-4bd6-a295-778ac7d34231`
- replay: `claude --resume c52212d9-9ae6-4bd6-a295-778ac7d34231`
- log: `.project/logs/TICKET-143-plan-validation-c52212d9.log`
- cost: $1.52 of a $3 cap
- tokens: 17,514 out (11,068 thinking) · 32 in · 849,132 cache read · 65,435 cache write

### 2026-09-20 03:55:50Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B PASS: the parked-merge test now fails a one-call wiring; one grep criterion is vacuous and is noted, not scored.

### 2026-09-20 03:56:01Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-09-20 03:58:18Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails as required
```
9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-143
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
______________ test_conflict_holder_ignores_a_shared_ledger_file _______________

    def test_conflict_holder_ignores_a_shared_ledger_file():
        """An opt-in ledger ignore must not serialize otherwise independent tickets."""
        mine = {"files_declared": ["PROGRESS.md"]}
        inflight = [{"id": "TICKET-004", "files_declared": ["PROGRESS.md"]}]
    
>       assert M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) is None
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

tests/test_machine.py:173: TypeError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: `tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file` fails on base `main` too -- the bug is not already fixed upstream
```
": "TICKET-004", "files_declared": ["PROGRESS.md"]}]
    
>       assert M.conflict_holder(mine, inflight, ignored={"PROGRESS.md"}) is None
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: conflict_holder() got an unexpected keyword argument 'ignored'

tests/test_machine.py:173: TypeError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_conflict_holder_ignores_a_shared_ledger_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yfkq_222/base
      Built pipeline @ file:///tmp/pipeline-base-yfkq_222/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 74ms

```
- ok: DEC-069 is superseded -- history, not binding

### 2026-09-20 03:58:19Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-20 04:20:00Z · implementing · note

**Implemented; all plan steps done, no deviation.**

Todo: [x] 1 `ignored` param in `machine.py` · [x] 2 `project_conflict_ignore()` · [x] 3 wire both `start()` calls · [x] 4 docs + knob tuple · [x] 5 full suite and guard.

- Commits: `e4b4c2c`, `d426945`, `b39de8a`, `b8366ea`.
- `pytest -q`: `685 passed`. `./pipeline/hooks/test_dangerous_commands.py`: exit 0, `guard: all passed`.
- Each new test failed first on an assertion (`TypeError` on `ignored`; the reader stub returned `set()`; the dispatcher tests named `PROGRESS.md` or ran no merge).
- Mutation check: dropping `ignored` from the `parked_meta()` call fails `test_conflict_ignore_frees_a_merge_from_a_parked_ledger_overlap` and `test_a_parked_code_file_overlap_still_holds_a_merge_under_an_ignore_list`. I restored the call.
- `test_a_bad_conflict_ignore_preserves_file_ordering` passed before the wiring. It guards against a fix that turns a bad value into a wide ignore set.
- Extra test beyond the plan: `test_project_conflict_ignore_is_empty_without_a_key_or_a_config`.
- Line numbers in the plan for `supervisor.py` were stale (calls at 868 and 871, not 895 and 898); I edited by content.

### 2026-09-20 04:02:17Z · implementing · session · session=adca21e4-40ad-41f4-b954-56144ae3ea95

`implementing` ran as session `adca21e4-40ad-41f4-b954-56144ae3ea95`
- replay: `claude --resume adca21e4-40ad-41f4-b954-56144ae3ea95`
- log: `.project/logs/TICKET-143-implementing-adca21e4.log`
- cost: $0.68 of a $10 cap
- tokens: 15,476 out (1,325 thinking) · 50 in · 1,312,532 cache read · 65,532 cache write

### 2026-09-20 04:02:17Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added [conflict] ignore; both start() overlap checks honour it; full suite 685 passed, guard exit 0.

### 2026-09-20 05:00:00Z · review · note

**Review of the delta `main...b8366ea`: PASS. No blocking findings.**

I re-ran the evidence from the worktree: `uv run --group dev pytest -q` prints `685 passed in 72.68s (0:01:12)`; the ten acceptance-criteria nodes run together print `10 passed in 0.56s`; `./pipeline/hooks/test_dangerous_commands.py` prints `guard: all passed`; `git status --porcelain` is empty.

Both `conflict_holder()` calls receive `ignored` (`pipeline/daemon/supervisor.py:869`, `:872`), and `parked_meta()` has no other caller. Subtracting `ignored` from `mine` alone is sound: the intersection is a subset of `mine`. I checked the two parked tests discriminate a one-call wiring: with `inflight` empty an unfiltered `parked_meta()` call returns `("TICKET-001", "PROGRESS.md")`, failing `assert did and rec["kind"] == "merge"` and the `waiting["file"] == "thing.py"` assertion.

Non-blocking, in severity order:

1. **low** -- `start()` now reads the project config once per ticket considered, not once per tick. `_start_cap()` already ran one `project_config()` per tick (`pipeline/daemon/supervisor.py:1620`); line 868 adds one `git show` per ticket past the `new` advance. DEC-094 chose this placement.
2. **low** -- `conflict = false` or `ignore = false` returns the empty set with no notice: `or {}` and `or []` (`pipeline/core/config.py:591`, `:595`) swallow a falsy non-table before the type check. Ordering is preserved, only the report is missing.
3. **low** -- `ignored: set[str] = frozenset()` (`pipeline/core/machine.py:332`) annotates `set[str]` and defaults to a `frozenset`. The plan specified this literal.

Confirming plan-validation's caveat: `grep -c ignored pipeline/daemon/supervisor.py` prints `12`, up from 9 on base, so criterion 12 stays vacuous. Criterion 7 carries the property instead.

### 2026-09-20 04:06:41Z · review · session · session=97d496c2-1218-42da-9b58-cc8be6e1c46e

`review` ran as session `97d496c2-1218-42da-9b58-cc8be6e1c46e`
- replay: `claude --resume 97d496c2-1218-42da-9b58-cc8be6e1c46e`
- log: `.project/logs/TICKET-143-review-97d496c2.log`
- cost: $1.57 of a $6 cap
- tokens: 16,219 out (9,402 thinking) · 38 in · 1,015,427 cache read · 65,912 cache write

### 2026-09-20 04:06:41Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ No blocking findings: both start() overlap checks honour the ignore set, 685 passed, guard exit 0; three low-severity notes appended.

### 2026-09-20 04:07:56Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-20 04:07:58Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/143


Current branch ticket/143 is up to date.
Already up to date.
Updating 0ef4273..b8366ea
Fast-forward
 README.md                                          |  14 +++
 pipeline/core/config.py                            |  32 ++++++
 pipeline/core/machine.py                           |  16 ++-
 pipeline/daemon/supervisor.py                      |   9 +-
 pipeline/templates/pipeline.toml                   |   9 ++
 pipeline/templates/skills/pipeline-config/SKILL.md |   2 +-
 tests/test_config.py                               |  39 ++++++-
 tests/test_dispatch.py                             | 113 +++++++++++++++++++++
 tests/test_machine.py                              |  17 ++++
 tests/test_stages.py                               |   2 +-
 10 files changed, 241 insertions(+), 12 deletions(-)

```

### 2026-09-20 04:07:58Z · merging · decision

decision recorded as `DEC-143`
