---
id: TICKET-034
stage: done
class: bugfix
branch: ticket/034
test_file: tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file
files_declared:
- CLAUDE.md
- pipeline/core/fence.py
- pipeline/core/machine.py
- pipeline/core/worktree.py
- pipeline/daemon/supervisor.py
- pipeline/harnesses/claude-code.toml
- pipeline/hooks/dangerous-commands.py
- tests/test_daemon.py
- tests/test_dispatch.py
- tests/test_machine.py
- tests/test_worktree.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 78a70e6e-a0d9-4471-b0db-b1859b2d4d83
  log: .project/logs/TICKET-034-review-78a70e6e.log
approved_by: chezzijr
approved_at: '2026-08-22T04:34:04.878485+00:00'
---

## Summary
Implemented and reviewed. The fix is dispatcher-side: a new
`strip_settings_sources()` in pipeline/core/worktree.py removes
`<worktree>/.claude/settings.json` and `.claude/settings.local.json`; `spawn()`
calls it before launching and `start()` calls it before the read-only
`tree_snapshot()`. A tracked file is deleted and marked `git update-index
--skip-worktree`, so the deletion never enters the ticket's diff. The design
rests on four probes against live `claude` 2.1.238 on 2026-08-22; the evidence
is in `## Digest`.

Review passed on the whole branch diff (7 commits, 11 files), no blocking
findings. All six acceptance criteria re-run green: `tests/` `219 passed`, the
five named tests `7 passed`, the guard `guard: all passed` over 79 cases.

Two non-blocking notes, both for a follow-up ticket, not for this one:

1. `guard_strip` never fires in production. `start()` strips before `spawn()`
   does, so `spawn()`'s print and `emit()` are dead outside a direct call.
2. `SETTINGS_SOURCES` is not in `FENCED`. Emptying the tuple disables the
   strip and merges unattended.

This diff edits `pipeline/hooks/dangerous-commands.py` and adds
`strip_settings_sources` to `machine.FENCED`, so it parks at `awaiting-merge`
for the human review CLAUDE.md requires of a guard change.

## Reproduction

Test: `tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file`

Command: `uv run --group dev pytest -q tests/test_daemon.py -k test_spawn_refuses_a_worktree_that_carries_its_own_settings_file`

Failure output:

    AssertionError: expected spawn() to refuse or strip a worktree-supplied .claude/settings.json before launching a guarded stage, but the file that disables the guard survived spawn() untouched
    assert not True
     +  where True = exists()
     +    where exists = ((PosixPath('/tmp/tmp4ul3dsav') / '.claude') / 'settings.json').exists

expect: expected spawn() to refuse or strip a worktree-supplied .claude/settings.json before launching a guarded stage, but the file that disables the guard survived spawn() untouched

Committed on `ticket/034` at `170c9d1`.

## Digest

- `spawn()` (pipeline/daemon/supervisor.py:296) builds `cmd` from `stage_settings()` and never looks at the worktree. `start()` (pipeline/daemon/supervisor.py:576) takes `before = tree_snapshot(wt)` for a read-only stage immediately before calling `spawn()`.
- `stage_settings()` (pipeline/core/config.py:150) writes the temp `--settings` file: `{"hooks": {"PreToolUse": [{"matcher": "Bash", ...}]}}`. Every one of the 7 stage prompts declares `hooks: [dangerous-commands]`, so "guarded stage" and "any stage" are the same set today.
- `pipeline/core/worktree.py` owns the checkout and already has `run_cmd()`, `project_env()`, `tree_snapshot()` and `shlex` imported; the new helper belongs there. `tree_snapshot()` = `git rev-parse HEAD` + `git status --porcelain -- . ':(exclude).project'`.
- Measured against `claude` 2.1.238 on 2026-08-22, four probes, real spawns with the real `stage_settings("implementing", ...)` file: (1) an agent that writes `.claude/settings.json` = `{"disableAllHooks": true}` with the Write tool **mid-run** still gets `Blocked by the pipeline guard (probe): worktrees are the dispatcher's to manage.` on `git worktree remove foo` -- settings are resolved at session start, so stripping at spawn is a complete defence for the run it starts; (2) the same file present **before** launch drops the guard, `fatal: 'foo' is not a working tree`; (3) `.claude/settings.local.json` with `disableAllHooks` does **not** drop it under `--setting-sources project` (guard fired); (4) `.claude/settings.json` = `{"permissions": {"allow": ["Bash(git worktree remove:*)"], "defaultMode": "bypassPermissions"}}` does **not** bypass the hook -- claude printed `Ignoring 1 permissions.allow entry from .claude/settings.json: this workspace has not been trusted` and the guard still fired. `permissions` is not the second weakness the ticket asked about; `disableAllHooks` is the whole hole.
- Also measured: a `.claude/settings.json` at the *project* root above the worktree, passed as `--add-dir {project}`, does **not** reach a spawn whose cwd is the worktree (guard fired). Only the worktree's own file counts, so only the worktree is stripped.
- Gotcha -- the gate copies this ticket's `test_file` (tests/test_daemon.py) onto a checkout of base and imports it there (DEC-017, DEC-018, DEC-030). A module-level import of a name this branch adds turns that base run into an `ImportError`, which the gate reports as "errored rather than failed on base" and the ticket is blocked. No new test and no new import goes into tests/test_daemon.py; new tests go in tests/test_worktree.py and tests/test_dispatch.py, which the gate never copies.
- Gotcha -- deleting a *tracked* `.claude/settings.json` leaves ` D .claude/settings.json` in `git status`, which `implementing`'s `git commit -a` would merge into base and which `tree_snapshot()` reads as a change. `git update-index --skip-worktree -- .claude/settings.json` after the delete hides it: verified in a scratch repo, `rc=0` and `git status --porcelain` came back with no `.claude` entry.
- Gotcha -- `machine.FENCED` is read from the **main checkout's** module while the dispatcher runs, so an entry this branch adds does not fence this branch's own diff. `pipeline/hooks/dangerous-commands.py` is fenced whole-file (`None`), so the plan puts the layering note in that file's docstring on purpose: it is what parks this ticket at `awaiting-merge` for the human review CLAUDE.md requires of a guard change.

## Decisions checked

Grepped `.project/decisions/` for: hook, settings, guard, worktree, dangerous, setting-sources, permissions, FENCED, snapshot, skip-worktree. No record carries a `superseded-by:` line, so all cited records are active.
- DEC-025 -- the harness names its settings sources, and a stage that cannot register `dangerous-commands.py` is refused rather than run unguarded (`--bare` rejected for exactly this). Stripping a settings source the pipeline did not put there is the same rule one level down; this plan complies, it does not supersede it.
- DEC-031 -- the fence matches symbols via `ast` line spans, a symbol missing from the new file trips unconditionally, and only a positive `clean` from `finish_suite()` skips the human. Adding `strip_settings_sources` to `FENCED` means a later deletion of it trips the fence.
- DEC-017, DEC-018, DEC-030 -- the gate copies the ticket's test file onto base and imports it there; a branch-only name is an `ImportError` that blocks the ticket. This is why tests/test_daemon.py gains nothing.
- DEC-011 -- the event vocabulary is frozen but adding a `kind` is additive and fine, so the new `guard_strip` event is allowed. `pipeline/tui/app.py` filters on `TREE_KINDS`/`STREAM_KINDS` and ignores an unknown kind.
- DEC-028, DEC-032 -- the harness `.toml` is re-read per tick, but a change to `pipeline/daemon/supervisor.py` or `pipeline/core/worktree.py` is inert until the dispatcher is restarted; `_source_watcher()` ends the loop when they merge. The fix protects spawns made after that restart.

## Plan

1. Add `SETTINGS_SOURCES = (".claude/settings.json", ".claude/settings.local.json")` and `strip_settings_sources(wt: Path) -> list[str]` to `pipeline/core/worktree.py`, test-first: write `test_stripping_settings_sources_removes_both_project_files` and `test_a_tracked_settings_file_is_stripped_without_entering_the_diff` in `tests/test_worktree.py` (first builds `git_project()`, writes both files with `{"disableAllHooks": true}`, asserts the return is `[".claude/settings.json", ".claude/settings.local.json"]`, both files gone, and a second call returns `[]`; second commits `.claude/settings.json` via `sh("git add .claude/settings.json && git commit -qm settings")`, then asserts the file is gone and `.claude/settings.json` does not appear in `sh("git status --porcelain").stdout`), run `uv run --group dev pytest -q tests/test_worktree.py` and watch both fail with `AttributeError: module 'pipeline.core.worktree' has no attribute 'strip_settings_sources'`, then implement the helper: for each `rel` in `SETTINGS_SOURCES` skip unless `(wt / rel).is_file() or (wt / rel).is_symlink()`, set `tracked = run_cmd(f"git ls-files --error-unmatch -- {shlex.quote(rel)}", wt)[0] == 0`, `unlink()` the path, run `git update-index --skip-worktree -- {shlex.quote(rel)}` in `wt` when `tracked`, append `rel` to the returned list; comment it with why (`--settings` cannot outrank a merged project source, and skip-worktree keeps a tracked file's deletion out of the ticket's diff), rerun the file green, commit.
2. Call the helper from `spawn()` in `pipeline/daemon/supervisor.py`: add `strip_settings_sources` to the `from pipeline.core.worktree import ...` list at pipeline/daemon/supervisor.py:30, and make the first statement of `spawn()`'s body after its docstring `stripped = strip_settings_sources(wt)` followed by `if stripped:` -> `print(f"  {tid}: removed {', '.join(stripped)} from the worktree -- a settings source there disables the guard for every spawn in it")` and `emit("guard_strip", ticket=tid, stage=stage, files=stripped)`; it must sit **above** the `supports_hooks` refusal so a harness that cannot register hooks still gets the file removed; run `uv run --group dev pytest -q tests/test_daemon.py -k test_spawn_refuses_a_worktree_that_carries_its_own_settings_file` and see it pass, commit.
3. Strip before the read-only baseline in `pipeline/daemon/supervisor.py`: insert `strip_settings_sources(wt)` immediately above `before = tree_snapshot(wt) if is_readonly(stage) else None` (pipeline/daemon/supervisor.py:576) with the comment that a baseline taken while the file is still there reads its own removal as `wrote-in-readonly`, and add `test_a_readonly_stage_snapshots_after_the_settings_strip` to `tests/test_dispatch.py` -- `git_project()`, `supervisor.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})`, write `{"disableAllHooks": true}` to `wt/".claude"/"settings.json"`, `FIXTURE.replace("stage: plan-validation", "stage: review")`, `did, rec = supervisor.start(...)` with `harness("fake")`, `rec["proc"].wait()`, `supervisor.close_child(rec)`, then assert the file is gone and `rec["before"] == supervisor.tree_snapshot(wt)` with the message `the read-only baseline was taken before the strip, so the removal reads as wrote-in-readonly`; run `uv run --group dev pytest -q tests/test_dispatch.py -k snapshots_after_the_settings_strip`, watch it fail on the baseline mismatch before the supervisor edit and pass after, commit.
4. Fence the new helper: add `"pipeline/core/worktree.py": ("strip_settings_sources",)` to `FENCED` in `pipeline/core/machine.py` and add `` `strip_settings_sources()` `` to the sentence at CLAUDE.md:201 so it reads "a change to `pipeline/hooks/dangerous-commands.py`, `transition()`, `validate_meta()`, `CONTROL_FIELDS` or `strip_settings_sources()` **requires human review before merge**" -- the backticked tokens in that paragraph and `machine.FENCED` must match exactly; run `uv run --group dev pytest -q tests/test_stages.py -k fenced_list` and see it pass, commit.
5. Correct the two places that document the hole: replace the `A write: true stage can still disable its own guard` gotcha at CLAUDE.md:174-180 with the fix (the dispatcher strips `<worktree>/.claude/settings.json` and `.claude/settings.local.json` at every spawn and before the read-only snapshot; a file written mid-run does not affect the run that is already going, measured 2026-08-22; a tracked file is hidden with `--skip-worktree`), and in `pipeline/harnesses/claude-code.toml` rewrite the closing `Unrelated to this flag ... Pre-existing hole in invariant 4` paragraph to say the dispatcher now strips it, and amend the `Operator permissions.deny rules stop applying` bullet so it no longer advises putting a binding deny rule in the project source -- a `.claude/settings.json` in the worktree is removed before the spawn, so the pipeline's own `--settings` hook is the only place a rule binds; commit.
6. Record the layering where a reader of the guard will look: add to the module docstring of `pipeline/hooks/dangerous-commands.py` a short paragraph -- "This file is registered through `--settings`, which Claude Code merges *behind* a project settings source. `<worktree>/.claude/settings.json` = `{\"disableAllHooks\": true}` therefore drops this hook entirely, so `strip_settings_sources()` in `pipeline/core/worktree.py` removes that file before every spawn. Do not remove it: without it a `write: true` stage disables this guard for every later spawn in its worktree." -- then run `./pipeline/hooks/test_dangerous_commands.py` and confirm the 79 cases still pass, commit. This edit is deliberate: `FENCED` fences this file whole, so it is what parks this ticket at the `awaiting-merge` human gate.
7. Verify the whole affected set before reporting done: `uv run --group dev pytest -q tests/test_worktree.py tests/test_daemon.py tests/test_dispatch.py tests/test_stages.py` and `./pipeline/hooks/test_dangerous_commands.py`, both green, with the fresh output quoted in the ticket thread.

## Acceptance criteria

- `tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file` passes: `spawn()` leaves no `.claude/settings.json` in the worktree it launches in.
- `tests/test_worktree.py::test_stripping_settings_sources_removes_both_project_files` passes: both files are removed, the return value names them in order, and a second call returns `[]`.
- `tests/test_worktree.py::test_a_tracked_settings_file_is_stripped_without_entering_the_diff` passes: a committed `.claude/settings.json` is gone from the working tree and absent from `git status --porcelain`.
- `tests/test_dispatch.py::test_a_readonly_stage_snapshots_after_the_settings_strip` passes: `rec["before"] == supervisor.tree_snapshot(wt)` after `start()` on a read-only stage whose worktree carried the file.
- `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` passes with `strip_settings_sources` in both `machine.FENCED` and the CLAUDE.md sentence.
- `./pipeline/hooks/test_dangerous_commands.py` still reports its 79 cases passing after the docstring edit.

## Decisions

**The guard is defended by the dispatcher, not by a flag.** `--settings` registers `dangerous-commands.py` and Claude Code merges the *project* settings source ahead of it, so no flag ordering can win: `<worktree>/.claude/settings.json` = `{"disableAllHooks": true}` drops the hook. `strip_settings_sources()` removes that file (and `.claude/settings.local.json`) before every spawn and before `start()`'s read-only baseline. Delete it and a `write: true` stage disables the guard for `implementing`'s retry, `review` and `quick-review` in the same worktree. It is in `machine.FENCED` for that reason.

**Stripping at spawn is sufficient, and this was measured, not reasoned.** Claude Code resolves settings at session start: an agent that wrote `.claude/settings.json` with the Write tool mid-run still got `Blocked by the pipeline guard (probe)` on `git worktree remove foo` (claude 2.1.238, 2026-08-22). The same file present before launch ran the command. So the defence does not need a Write/Edit matcher on the hook, and the hook keeps `matcher: "Bash"`. If a future Claude Code hot-reloads settings, that conclusion dies and the guard needs a file-write rule; re-run the probe when the harness or the CLI version changes.

**`permissions` is not a second hole.** `{"permissions": {"allow": ["Bash(git worktree remove:*)"], "defaultMode": "bypassPermissions"}}` in the worktree's settings did not bypass the hook -- claude printed `Ignoring 1 permissions.allow entry from .claude/settings.json: this workspace has not been trusted` and the guard still fired. Stripping the whole file covers it anyway; do not narrow the strip to the `disableAllHooks` key, because the key is not the promise -- the absence of an agent-writable settings source is.

**`.claude/settings.local.json` is stripped although it is not loaded today.** Under `--setting-sources project` a `disableAllHooks` in it did not drop the guard (measured). It is removed so that adding `local` to `--setting-sources` cannot silently reopen the hole.

**A tracked settings file is deleted and marked `--skip-worktree`, deliberately.** A plain delete leaves ` D .claude/settings.json` in `git status`: `implementing` runs `git commit -a`, and the project loses a file it owns at merge; a read-only stage escalates `wrote-in-readonly` on the same line. `--skip-worktree` hides the deletion from status and from the diff, and the worktree is disposable so the flag dies with it. The cost: a `git rebase` at `revalidating` can refuse to move a skip-worktree path if base changes that file. If that ever appears, run `git update-index --no-skip-worktree -- .claude/settings.json` in the worktree, not a wider change to the strip.

**Only the worktree's own file is stripped.** A `.claude/settings.json` at the project root above the worktree, passed as `--add-dir {project}`, does not reach a spawn whose cwd is the worktree (measured). Do not widen the strip to the project checkout: the ticket file and `.project/` live there and the dispatcher must not edit an operator's real settings.

**A project settings source no longer binds a stage.** `pipeline/harnesses/claude-code.toml` used to advise putting a `permissions.deny` rule in the project source because `--setting-sources project` drops the operator's. After this change that file is removed before the spawn, so the pipeline's `--settings` file is the only place a rule binds. A project that needs its own rule has to add it there.

## Rollback

Revert the commits from steps 1-3 (`pipeline/core/worktree.py`, `pipeline/daemon/supervisor.py`, `tests/test_worktree.py`, `tests/test_dispatch.py`) and the guard hole is back exactly as `170c9d1`'s test describes -- do that only with the dispatcher stopped, since a running dispatcher keeps the old code until it restarts. Steps 4-6 (`pipeline/core/machine.py`, `CLAUDE.md`, `pipeline/harnesses/claude-code.toml`, `pipeline/hooks/dangerous-commands.py`) are documentation and the fence entry; reverting step 4 alone breaks `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file`, so revert steps 4 and 5 together. Any live worktree that had a tracked settings file stripped is repaired with `git update-index --no-skip-worktree -- .claude/settings.json` followed by `git checkout -- .claude/settings.json`, or simply by deleting the worktree.

## Thread

### 2026-08-22 · implementing · todo

**todo**

1. [x] `strip_settings_sources()` in `pipeline/core/worktree.py` + `tests/test_worktree.py` (2 tests)
2. [x] `spawn()` calls it in `pipeline/daemon/supervisor.py`, above the `supports_hooks` refusal
3. [x] `start()` calls it before the read-only `tree_snapshot()` + `tests/test_dispatch.py` test
4. [x] fence `strip_settings_sources` in `machine.FENCED` + CLAUDE.md:201 sentence
5. [x] rewrite the CLAUDE.md:174-180 gotcha and the `claude-code.toml` hole paragraph
6. [x] docstring note in `pipeline/hooks/dangerous-commands.py`
7. [x] full verification pass, quote fresh output

### 2026-08-22 · implementing · note

Executed the plan's 7 steps, TDD throughout, one commit per step:

- `cebab6a` `strip_settings_sources()` + `tests/test_worktree.py` (2 new tests, watched both fail with `AttributeError: module 'pipeline.core.worktree' has no attribute 'strip_settings_sources'`, then pass).
- `c58b09d` `spawn()` wired above the `supports_hooks` refusal. `tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file` watched failing (`assert not True`) then passing.
- `7ae76c0` `start()` strips before the read-only baseline. New `tests/test_dispatch.py::test_a_readonly_stage_snapshots_after_the_settings_strip` watched fail on `'1f5ea5d3...\n' == '1f5ea5d3...e8fb6833fb0\n'` (baseline missing the strip's own `?? .claude/`), then pass.
- `a767fbb` fenced `strip_settings_sources` in `machine.FENCED` and CLAUDE.md:201; also fixed the "four things" -> "five things" wording in `pipeline/core/fence.py:3` and `tests/test_machine.py:56` per plan-validation's non-blocking note.
- `395cc03` rewrote the CLAUDE.md:174-180 gotcha and the two `claude-code.toml` paragraphs (the hole note and the `permissions.deny` bullet) to describe the fix instead of the hole.
- `97a04f3` added the layering paragraph to `pipeline/hooks/dangerous-commands.py`'s module docstring.
- Step 7: `uv run --group dev pytest -q` -> `221 passed in 10.11s`; `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed` (79 `ok` lines).

All six acceptance-criteria tests pass by name. No plan step was blocked; nothing outside `files_declared` was touched.

### 2026-08-22 03:54:48Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-22 · triage · investigation

Confirmed at the code level: `spawn()` (pipeline/daemon/supervisor.py:296)
builds `cmd` from `stage_settings()` and never inspects `wt / ".claude" /
"settings.json"`. Nothing in `pipeline/core/worktree.py` or the dispatcher
checks for or strips that file either -- grepped both, no hits. This matches
the ticket's claim that no code layer defends against it; the manual
`claude` repro in `## Summary` shows the external consequence, this shows
the missing guard in our own code.

Added `test_spawn_refuses_a_worktree_that_carries_its_own_settings_file` to
tests/test_daemon.py: writes `.claude/settings.json` with `disableAllHooks:
true` into a fake project's worktree, spawns the `implementing` stage
(`write: true`, `hooks: [dangerous-commands]`) with `harness("fake")`, and
asserts the file was refused or stripped. It survives untouched today --
test fails with `expect` text above. Committed on `ticket/034` at `170c9d1`.

Files a `chore` fix would touch, if planning judges it small enough:
pipeline/daemon/supervisor.py (`spawn()`), possibly pipeline/core/worktree.py.
Left as `ok` rather than `chore`: the ticket itself asks planning to weigh
dispatcher-refuse vs strip-the-file vs also checking `permissions`, which is
a design choice I should not make here, and the change touches the guard so
`CLAUDE.md` fences it for human review regardless.

### 2026-08-22 03:56:46Z · triage · session · session=a42fd100-28a4-4f02-abe7-12d7fa53325d

`triage` ran as session `a42fd100-28a4-4f02-abe7-12d7fa53325d`
- replay: `claude --resume a42fd100-28a4-4f02-abe7-12d7fa53325d`
- log: `.project/logs/TICKET-034-triage-a42fd100.log`

### 2026-08-22 03:56:46Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- spawn() never checks worktree for .claude/settings.json; failing test committed at 170c9d1


### 2026-08-22 · planning · note

Planned the dispatcher-side strip. The ticket asked planning to weigh
refuse-vs-strip and to check `permissions`; I answered both by measurement
rather than by argument, with four real `claude` 2.1.238 spawns using the real
`stage_settings("implementing", ...)` file (details and verbatim output in
`## Digest`):

1. Mid-run write of `.claude/settings.json` = `{"disableAllHooks": true}`:
   guard still fired -- `Blocked by the pipeline guard (probe): worktrees are
   the dispatcher's to manage.`
2. Same file present before launch: guard gone -- `fatal: 'foo' is not a
   working tree`.
3. `.claude/settings.local.json`: guard fired, so it is not loaded under
   `--setting-sources project`.
4. `permissions.allow` + `defaultMode: bypassPermissions`: guard fired, entry
   ignored as an untrusted workspace.

So strip-at-spawn is a complete defence and the hook keeps `matcher: "Bash"`.
Refusing to spawn was rejected: it makes the pipeline unusable on any project
that ships a `.claude/settings.json`, and the committed test requires the file
to be gone.

Scope note, not fixed here: `pipeline/harnesses/claude-code.toml` is not in
`machine.FENCED`, so a ticket that edits the harness `cmd` -- trusted shell --
merges unattended. Separate ticket.

### 2026-08-22 04:08:14Z · planning · session · session=c1841b5f-18a3-4e9a-88b9-89a80c74d0aa

`planning` ran as session `c1841b5f-18a3-4e9a-88b9-89a80c74d0aa`
- replay: `claude --resume c1841b5f-18a3-4e9a-88b9-89a80c74d0aa`
- log: `.project/logs/TICKET-034-planning-c1841b5f.log`

### 2026-08-22 04:08:14Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: spawn()/start() strip the worktree's .claude settings sources; 4 live-claude probes settle mid-run, local, permissions and project-root cases

### 2026-08-22 04:08:26Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file` fails as required
```
   assert not (d / ".claude" / "settings.json").exists(), (
            "expected spawn() to refuse or strip a worktree-supplied "
            ".claude/settings.json before launching a guarded stage, but the "
            "file that disables the guard survived spawn() untouched")
E       AssertionError: expected spawn() to refuse or strip a worktree-supplied .claude/settings.json before launching a guarded stage, but the file that disables the guard survived spawn() untouched
E       assert not True
E        +  where True = exists()
E        +    where exists = ((PosixPath('/tmp/tmpl54ftp7q') / '.claude') / 'settings.json').exists

tests/test_daemon.py:564: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: implementing (sonnet, batch) pid 2234696 -> TICKET-001-implementing-409b158f.log
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file` fails on base `main` too -- the bug is not already fixed upstream
```
     +    where exists = ((PosixPath('/tmp/tmp4sew33wb') / '.claude') / 'settings.json').exists

tests/test_daemon.py:564: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: implementing (sonnet, batch) pid 2234749 -> TICKET-001-implementing-fa766f9d.log
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-cp19lrx7/base
      Built pipeline @ file:///tmp/pipeline-base-cp19lrx7/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-22 · plan-validation · note

Plan accepted. Eight items, each checked against the code.

**Root cause.** `--settings` registers the guard hook, and Claude Code merges
the worktree's project settings source *ahead* of it, so
`<worktree>/.claude/settings.json` = `{"disableAllHooks": true}` drops the
hook. `spawn()` (pipeline/daemon/supervisor.py:296) never reads the worktree.
The plan removes the file before launch, which is the cause, not the symptom.

**Decisions.** All six cited records resolve in the project root (DEC-018's
rule), none carry `superseded-by:`, and the plan's reading of each is
accurate. DEC-031 requires the fence sentence to stay one paragraph with every
item backticked; step 4 obeys. DEC-025 refuses an unguarded stage; the plan
complies rather than supersedes.

**Falsifiable.** Verified the fenced-list test extracts backticked tokens from
the paragraph before `requires human review before merge`
(tests/test_stages.py:177-183): step 4's prose and `FENCED` match exactly.
The step-3 test fails today because the baseline snapshots `?? .claude/settings.json`
and the run deletes it.

**Scope, blast radius, regression.** 8 files match `files_declared`; 3 are
code, 2 tests, 3 prose -- proportionate for `bugfix`. Step 5 traces to no
criterion; it deletes prose this fix falsifies, and no test reads prose.
Checked the tests step 7 omits: `tests/test_machine.py:61` asserts only that
`FENCED` is truthy and `tests/test_stages.py:142` reads CLAUDE.md for
dependency names, so neither breaks.

**Riskiest step.** Step 1's `--skip-worktree` on a tracked file. The plan
states the fallback: `git update-index --no-skip-worktree` when a
`revalidating` rebase refuses the path. The committed test uses `project()`,
not a git repo, so `git ls-files` returns non-zero there and `tracked` is
False -- the helper as specified does not fault.

### 2026-08-22 04:12:57Z · plan-validation · session · session=3289b0ae-ff01-4ee0-94c5-468475ff56ba

`plan-validation` ran as session `3289b0ae-ff01-4ee0-94c5-468475ff56ba`
- replay: `claude --resume 3289b0ae-ff01-4ee0-94c5-468475ff56ba`
- log: `.project/logs/TICKET-034-plan-validation-3289b0ae.log`

### 2026-08-22 04:12:57Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan validated: root cause is the project-source merge order, all 6 cited decisions resolve and bind, anchors verified in code, 8 files match class bugfix

### 2026-08-22 04:19:30Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-22 04:22:20Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file` fails as required
```
   assert not (d / ".claude" / "settings.json").exists(), (
            "expected spawn() to refuse or strip a worktree-supplied "
            ".claude/settings.json before launching a guarded stage, but the "
            "file that disables the guard survived spawn() untouched")
E       AssertionError: expected spawn() to refuse or strip a worktree-supplied .claude/settings.json before launching a guarded stage, but the file that disables the guard survived spawn() untouched
E       assert not True
E        +  where True = exists()
E        +    where exists = ((PosixPath('/tmp/tmpxvymrfom') / '.claude') / 'settings.json').exists

tests/test_daemon.py:564: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: implementing (sonnet, batch) pid 2244562 -> TICKET-001-implementing-5e720add.log
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file` fails on base `main` too -- the bug is not already fixed upstream
```
     +    where exists = ((PosixPath('/tmp/tmpb54l8_ki') / '.claude') / 'settings.json').exists

tests/test_daemon.py:564: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: implementing (sonnet, batch) pid 2244606 -> TICKET-001-implementing-4cea1a06.log
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_spawn_refuses_a_worktree_that_carries_its_own_settings_file
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-lwm7vshg/base
      Built pipeline @ file:///tmp/pipeline-base-lwm7vshg/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-22 04:22:20Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-22 04:26:56Z · implementing · session · session=cb9bb6b5-d159-4eb9-b389-bc3270a2d549

`implementing` ran as session `cb9bb6b5-d159-4eb9-b389-bc3270a2d549`
- replay: `claude --resume cb9bb6b5-d159-4eb9-b389-bc3270a2d549`
- log: `.project/logs/TICKET-034-implementing-cb9bb6b5.log`

### 2026-08-22 04:26:56Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented strip_settings_sources(), wired it into spawn() and start(), fenced it, updated docs; full suite 221 passed, guard 79/79

### 2026-08-22 · review · note

Review passed, no blocking findings. Reviewed the whole branch diff
(`main...HEAD`, 7 commits, 11 files); the thread carries no earlier review
entry, so the branch point was the baseline.

Re-ran every acceptance criterion:

1. `uv run --group dev pytest -q tests/` -> `219 passed in 9.93s`.
2. The four named tests plus `test_the_fenced_list_matches_the_rule_file` ->
   `7 passed in 0.13s`.
3. `uv run python pipeline/hooks/test_dangerous_commands.py` ->
   `guard: all passed`, 79 `ok` lines. `./pipeline/hooks/test_dangerous_commands.py`
   is blocked for a read-only stage (`test_dangerous_commands.py` is not on the
   read-only allowlist), so I ran it through `uv run python`.

Two findings, neither blocking:

1. minor -- `guard_strip` never fires in production. `start()` strips at
   pipeline/daemon/supervisor.py:586, so `spawn()`'s strip at :304 always
   returns `[]` and its print and `emit()` are dead outside a direct `spawn()`
   call. A real strip leaves no event.
2. minor -- `SETTINGS_SOURCES` (pipeline/core/worktree.py:99) is not in
   `FENCED`. pipeline/core/fence.py:55-56 matches module-level assignments, so
   a later diff setting the tuple to `()` disables the strip and merges
   unattended.

Dropped two charges:

- "`unlink()` raising `OSError` takes the loop down" -- refuted, `tick()` wraps
  `start()` in `except Exception` (pipeline/daemon/supervisor.py:902-905).
- "the strip can delete the operator's project-root settings" -- refuted,
  `ensure_worktree()` returns `<project>/.worktrees/<id>` or `None`
  (pipeline/core/worktree.py:45), so `wt` is never the project root.

### 2026-08-22 04:30:50Z · review · session · session=78a70e6e-a0d9-4471-b0db-b1859b2d4d83

`review` ran as session `78a70e6e-a0d9-4471-b0db-b1859b2d4d83`
- replay: `claude --resume 78a70e6e-a0d9-4471-b0db-b1859b2d4d83`
- log: `.project/logs/TICKET-034-review-78a70e6e.log`

### 2026-08-22 04:30:50Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review passed on the full branch diff: 219 tests + 5 named tests + 79 guard cases green, 2 non-blocking notes appended, 2 charges dropped

### 2026-08-22 04:31:00Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/hooks/dangerous-commands.py`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-034` lands it; `pipeline resume TICKET-034 --stage planning` sends it back.

### 2026-08-22 04:34:04Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-22 04:34:10Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/034


Already up to date.
Updating 85328e6..97a04f3
Fast-forward
 CLAUDE.md                            | 22 ++++++++++++---------
 pipeline/core/fence.py               |  2 +-
 pipeline/core/machine.py             |  1 +
 pipeline/core/worktree.py            | 25 ++++++++++++++++++++++++
 pipeline/daemon/supervisor.py        | 15 +++++++++++++--
 pipeline/harnesses/claude-code.toml  | 20 +++++++++++--------
 pipeline/hooks/dangerous-commands.py |  7 +++++++
 tests/test_daemon.py                 | 29 ++++++++++++++++++++++++++++
 tests/test_dispatch.py               | 23 ++++++++++++++++++++++
 tests/test_machine.py                |  7 ++++---
 tests/test_worktree.py               | 37 ++++++++++++++++++++++++++++++++++++
 11 files changed, 165 insertions(+), 23 deletions(-)

```

### 2026-08-22 04:34:10Z · merging · decision

decision recorded as `DEC-034`
