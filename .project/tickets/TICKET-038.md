---
id: TICKET-038
stage: done
class: feature
branch: ticket/038
test_file: tests/test_stages.py::test_stage_config_can_take_a_per_project_override
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/config.py
- pipeline/core/fence.py
- pipeline/core/machine.py
- pipeline/core/worktree.py
- pipeline/daemon/supervisor.py
- pipeline/templates/pipeline.toml
- tests/test_dispatch.py
- tests/test_fence.py
- tests/test_stages.py
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
  id: 3c9ffbeb-f9ab-4366-bee4-417e7b9c3215
  log: .project/logs/TICKET-038-review-3c9ffbeb.log
approved_by: chezzijr
approved_at: '2026-08-23T16:34:22.606721+00:00'
---

## Summary

A stage's model, tools, skills and instructions were global: `stage_config()`,
`is_readonly()` and `compose_prompt()` resolved against `STAGES_DIR` and took no
project, so `stage_config("review", project=d)` raised `TypeError:
stage_config() got an unexpected keyword argument 'project'`.

**Shipped, in eight commits `e6b7295..f7a93be`.** The three functions take
`project: Path | None`. Structured settings come from `[stages.<name>]` in
`.project/pipeline.toml`, merged shallow over the packaged frontmatter (a
`skills` list replaces, it does not extend); prose comes from
`.project/stages/<name>.extra.md`, appended after the packaged prompt and
before the ticket view. `project_stage_config()` and `stage_extra()` are new.
`fenced_touches()` reads a trailing `/` key as a directory, and
`.project/stages/` joins `machine.FENCED` and the `CLAUDE.md` sentence.
`spawn()` and `start()` pass the project at `supervisor.py:320,365,648`.
Whole-file stage replacement (TICKET-035) stays out. Beyond the plan's text:
`head_file()` gained an `is_dir()` guard, because `subprocess.run(cwd=...)`
raised `FileNotFoundError` for a project path that does not exist; and the
`CLAUDE.md` sentence went to eight backticked tokens, not the "six" step 10
named, because the sentence already held seven.

**review passed with no blocking findings.** `uv run --group dev pytest -q` --
`240 passed in 10.30s`. `uv run --group dev python
pipeline/hooks/test_dangerous_commands.py` -- `guard: all passed`, `exit=0`.
Every acceptance criterion holds and all 11 changed files are in
`files_declared`. Four non-blocking findings are in the thread's `review` entry:
two stale "six things" comments, `is_readonly()` at `:648` sitting outside
`start()`'s `try`, no type check on override values, and `stage_extra()` reading
disk rather than `HEAD` (this ticket's own decision, deferred to TICKET-037),
plus one on the fence's scope. `fenced_touches(wt, "main")` on this branch
returns `[]`: the diff does not park at `awaiting-merge` on its own.

## Reproduction

`tests/test_stages.py::test_stage_config_can_take_a_per_project_override`

Command: `uv run --group dev pytest -q tests/test_stages.py::test_stage_config_can_take_a_per_project_override`

Output:
```
E       TypeError: stage_config() got an unexpected keyword argument 'project'
tests/test_stages.py:201: TypeError
1 failed in 0.06s
```

expect: TypeError: stage_config() got an unexpected keyword argument 'project'

## Digest

Files this change touches, and what each is responsible for:
- `pipeline/core/config.py` -- resolution: `stage_config()`, `is_readonly()`, `compose_prompt()`, plus two new helpers `project_stage_config()` and `stage_extra()`.
- `pipeline/core/fence.py` -- `fenced_touches()` gains a directory entry.
- `pipeline/core/machine.py` -- `FENCED` gains `.project/stages/`.
- `pipeline/daemon/supervisor.py` -- three call sites pass `project`: `stage_config` (line 320), `compose_prompt` (line 365), `is_readonly` (line 648).
- `pipeline/templates/pipeline.toml`, `README.md`, `CLAUDE.md` -- the documented shape.
- `tests/test_stages.py`, `tests/test_fence.py`, `tests/test_dispatch.py` -- one test per behaviour.

Entry points: `spawn()` (`pipeline/daemon/supervisor.py:316`) reads the stage
config and composes the prompt; `start()` (`pipeline/daemon/supervisor.py:508`)
takes the read-only baseline at line 648. `render()`
(`pipeline/core/config.py:76`) reads `model`, `permission_mode`, `tools`,
`max_usd` and `skills` out of the same dict `stage_config()` returns, so an
override reaches the spawned command with no change to `render()` and no change
to any harness `.toml`.

Gotchas, each read out of the tree:
- `tests/test_pty.py:393` calls `supervisor.spawn(tmp, tmp, ...)` on a bare temp dir with no `.project/pipeline.toml`. A missing config file must fall back to the packaged stage, not raise, or that test breaks.
- `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` compares the backticked tokens of one `CLAUDE.md` sentence with `machine.FENCED`. A new `FENCED` entry without the matching `CLAUDE.md` edit fails the suite.
- `fenced_touches()` looks up `changed.get(path)` by exact path, so a directory needs its own branch. `git diff` reports tracked files only, so the fence test must `git add -A` before it asserts.
- `project_config()` reads the **main checkout**, never the worktree, so an agent cannot change the config of its own spawn. It can only commit one and merge it.
- `tree_snapshot()` excludes all of `.project/`, so a read-only stage can write `.project/stages/review.extra.md` in its worktree undetected. The `FENCED` entry is what stops that file landing unread.
- `.claude/skills/file-ticket/SKILL.md` needs no edit. It says a diff parks at `awaiting-merge` when it touches anything `CLAUDE.md` fences off, and that stays true.
- `pipeline/harnesses/fake.toml` interpolates `{model}` into its `cmd`, so the spawn log's first line (`$ <cmd>`) is where a wiring test reads the effective model.

## Decisions checked

Grepped the decisions directory next to this ticket for: `stage_config`,
`pipeline.toml`, `FENCED`, `fenced`, `permission_mode`, `skills`,
`project_config`, `override`, `HEAD`. No record on disk carries a
`superseded-by:` line.

- DEC-031 -- a fenced diff parks at `awaiting-merge`, and the polarity of `verifying`'s results is the guard. This plan adds a `FENCED` entry and changes no result polarity, so it complies.
- DEC-034 -- `machine.FENCED` membership is how the dispatcher defends what an agent must not change unattended. Adding `.project/stages/` uses that mechanism rather than a new one, so it complies.

DEC-011, DEC-016, DEC-017, DEC-021, DEC-026, DEC-030 and DEC-032 matched a grep
term but constrain the daemon protocol, ticket parsing, the Tier A base run, the
TUI, the cheap route, gate findings and the source watcher. None of them
constrains stage resolution.

## Plan

1. Run `uv run --group dev pytest -q tests/test_stages.py::test_stage_config_can_take_a_per_project_override` and confirm the failure is `TypeError: stage_config() got an unexpected keyword argument 'project'`.
2. In `pipeline/core/config.py` add `project_stage_config(project: Path | None, stage: str) -> dict`: return `{}` when `project` is None; call `project_config(project)` and return `{}` when it raises `PipelineError`, so a project with no config file keeps the packaged stage; raise `PipelineError` naming the project when the `stages` value is present and is not a dict; raise the same shape when the `[stages.<stage>]` value is present and is not a dict; otherwise return that table.
3. In `pipeline/core/config.py` change `stage_config(stage: str, project: Path | None = None)` to return `{**meta, **project_stage_config(project, stage)}`, and state in its docstring that the merge is shallow: a project's `skills` list replaces the packaged list, it does not extend it. Run the step 1 command; it passes. Commit.
4. Add `test_a_project_override_merges_onto_the_packaged_frontmatter(tmp_path)` to `tests/test_stages.py`. It writes `.project/pipeline.toml` holding a `[stages.review]` table with `model = "haiku"` and `write = true`, then asserts four things: `C.stage_config("review", project=project)["effort"]` equals the packaged `effort`; the same for `["hooks"]`; `C.is_readonly("review")` is True while `C.is_readonly("review", project)` is False; `C.stage_config("review", project=tmp_path / "nothing")["model"]` equals the packaged model. Run it and watch it fail on `is_readonly()` taking one positional argument.
5. In `pipeline/core/config.py` change `is_readonly(stage: str, project: Path | None = None)` to return `not stage_config(stage, project).get("write", False)`. Run `uv run --group dev pytest -q tests/test_stages.py`; both tests pass. Commit.
6. Add `test_a_project_appends_prose_to_a_stage_prompt(tmp_path)` to `tests/test_stages.py`. It writes `.project/stages/review.extra.md` holding a heading line and a bullet carrying `EXTRA-MARKER-4471`, calls `C.compose_prompt("review", None, "VIEW-MARKER-9137", project)`, reads and unlinks the file, and asserts `text.index("Your stage: review") < text.index("EXTRA-MARKER-4471") < text.index("VIEW-MARKER-9137")`; it then calls `C.compose_prompt("review", None, "VIEW-MARKER-9137")` with no project and asserts `EXTRA-MARKER-4471` is absent. Run it and watch it fail with `TypeError: compose_prompt() takes from 1 to 3 positional arguments but 4 were given`.
7. In `pipeline/core/config.py` add `stage_extra(project: Path | None, stage: str) -> str`, returning the text of `<project>/.project/stages/<stage>.extra.md` when that file exists and the empty string otherwise, and give `compose_prompt()` a fourth parameter `project: Path | None = None`. When `stage_extra()` returns a non-empty string, append to `text` -- after the skills block and before the view block -- a horizontal rule, the heading `# This project's additions to this stage`, one sentence naming `.project/stages/<stage>.extra.md` as the source and saying these instructions add to the rules above and never relax them, then the file's text. Run `uv run --group dev pytest -q tests/test_stages.py`; it passes. Commit.
8. Add `test_a_directory_entry_trips_on_any_file_under_it()` to `tests/test_fence.py`. It does `d, sh = git_project()`, writes `.project/stages/review.extra.md`, runs `sh("git add -A")`, then asserts `fenced_touches(d, "main", {".project/stages/": None})` equals `[".project/stages/review.extra.md"]` and that a `{"other/": None}` fence returns `[]`. Run it and watch the first assertion fail with `[]`.
9. In `pipeline/core/fence.py`, as the first branch of `fenced_touches()`'s `for path, symbols in fenced.items()` loop, handle `path.endswith("/")` by extending `hits` with `sorted(p for p in changed if p.startswith(path))` and `continue`. Add one docstring line: a key ending in `/` is a directory, and any changed file under it trips. Run `uv run --group dev pytest -q tests/test_fence.py`; it passes. Commit.
10. Add the entry `".project/stages/": None` to `FENCED` in `pipeline/core/machine.py`, then edit the fenced sentence in `CLAUDE.md` (the one ending "requires human review before merge") so its backticked tokens are exactly six: pipeline/hooks/dangerous-commands.py, transition(), validate_meta(), CONTROL_FIELDS, strip_settings_sources() and .project/stages/. Run `uv run --group dev pytest -q tests/test_stages.py tests/test_machine.py`; `test_the_fenced_list_matches_the_rule_file` passes. Commit.
11. Add `test_a_project_override_reaches_the_spawned_command_and_prompt()` to `tests/test_dispatch.py`. It builds `d = project()`, appends a `[stages.review]` table with `model = "haiku"` to `d/".project"/"pipeline.toml"`, writes `.project/stages/review.extra.md` holding `EXTRA-MARKER-4471`, replaces `supervisor.compose_prompt` with a recorder that calls the real function and keeps the path it returns, calls `supervisor.spawn(d, d, "TICKET-001", "review", harness("fake"))`, then `rec["proc"].wait()` and `supervisor.close_child(rec)`, restores the attribute in a `finally`, and asserts `haiku` appears in the first line of the file matching `TICKET-001-review-*.log` under `d/".project"/"logs"` and `EXTRA-MARKER-4471` appears in the recorded prompt's text. Run it and watch both assertions fail.
12. In `pipeline/daemon/supervisor.py` pass the project at all three sites: `cfg = stage_config(stage, project)` at line 320, `prompt = compose_prompt(stage, hcfg, view, project)` at line 365, and `before = tree_snapshot(wt) if is_readonly(stage, project) else None` at line 648. Run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_pty.py`; they pass. Commit.
13. Document both halves: append to `pipeline/templates/pipeline.toml` a commented `[stages.review]` example setting `model` and `skills`, with a comment naming `.project/stages/<stage>.extra.md` as the prose half; in `README.md` delete the `Per-project stage overrides (TICKET-035)` bullet from `## Not built yet` and add a `## Per-project stage config` section before `## Porting to another harness` covering the two shapes, the shallow merge, and the fact that a committed change parks at `awaiting-merge`. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`; both pass. Commit.

## Acceptance criteria

- `tests/test_stages.py::test_stage_config_can_take_a_per_project_override` passes: `stage_config("review", project=p)["model"]` is `"haiku"`.
- `tests/test_stages.py::test_a_project_override_merges_onto_the_packaged_frontmatter` passes: packaged `effort` and `hooks` survive the merge, `is_readonly("review", p)` is False under `write = true`, and a project with no `.project/pipeline.toml` yields the packaged model.
- `tests/test_stages.py::test_a_project_appends_prose_to_a_stage_prompt` passes: the packaged body, then `EXTRA-MARKER-4471`, then `VIEW-MARKER-9137`, in that order, and the marker is absent when no project is passed.
- `tests/test_fence.py::test_a_directory_entry_trips_on_any_file_under_it` passes: `fenced_touches` returns `[".project/stages/review.extra.md"]`.
- `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` passes with `.project/stages/` named in both `CLAUDE.md` and `machine.FENCED`.
- `tests/test_dispatch.py::test_a_project_override_reaches_the_spawned_command_and_prompt` passes: the spawn log's first line carries `haiku` and the composed prompt carries `EXTRA-MARKER-4471`.
- `uv run --group dev pytest -q` reports no failures, and `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

**A project's `[stages.<name>]` table is merged shallow and is not clamped.**
Any key the packaged frontmatter carries can be replaced, `write`, `tools`,
`hooks` and `permission_mode` included. The defence is provenance, not a clamp:
the table lives in `.project/pipeline.toml`, which `project_config()` reads from
the main checkout, so an agent cannot change the config of its own spawn. It can
only commit one, and a committed one enters the ticket's diff. TICKET-037 moves
that read to `HEAD` and fences the file. Until TICKET-037 lands, a committed
`[stages.*]` change merges unattended -- the ordering this ticket declares its
dependency on.

**Do not reintroduce whole-file stage replacement.** TICKET-035 asked for it and
escalated: an override could set `write: true` and drop both the read-only
allowlist and the tree snapshot, and `tools` and `permission_mode` had the same
hole. The prose half is append-only for that reason -- an `.extra.md` has no
frontmatter, so there is nothing in it to clamp.

**`.project/stages/` is a directory entry in `machine.FENCED`, and a trailing
`/` in a `FENCED` key means prefix.** Remove either half and a project's stage
prose lands without a human reading it. `tree_snapshot()` excludes `.project/`,
so nothing else notices a read-only stage writing that file into its worktree.

**Prompt order is packaged rules, then the project's extra, then the ticket
view.** A project's additions must not precede the rules they add to.

**When TICKET-037 lands, route `stage_extra()` through the same `HEAD` read as
`project_config()`.** Prose cannot grant privilege, so reading it off disk is
not a hole today. Leaving the two halves resolved from different places is a
trap for whoever reads them next.

## Rollback

Revert the commits from step 3 onward. Nothing migrates: no schema, no state
file, no on-disk format. After the revert a project's `[stages.<name>]` table
and its `.project/stages/*.extra.md` are inert again, and every stage resolves
to the packaged file exactly as before. Revert `pipeline/core/machine.py` and
`CLAUDE.md` in the same step -- `machine.FENCED` and the `CLAUDE.md` sentence
must name the same set, or
`tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` fails.

## Thread

### 2026-08-23 14:21:54Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-23 14:22:11Z · triage · note

`triage` was interrupted; lease released

### 2026-08-23 14:22:11Z · triage · reproduced

Reproduced by calling `stage_config("review", project=project)`. Confirmed
`TypeError: stage_config() got an unexpected keyword argument 'project'`,
matching the ticket's quoted symptom exactly.

Added `tests/test_stages.py::test_stage_config_can_take_a_per_project_override`,
which asserts a `[stages.review]` override in `.project/pipeline.toml` reaches
`stage_config()`'s return value. It fails with the TypeError above because
`stage_config()`, `is_readonly()` and `compose_prompt()` take no `project`
argument today, and `project_config()` reads only test/base keys.

This is not a chore: it needs a new resolution shape across `stage_config()`,
`is_readonly()`, `compose_prompt()` and `project_config()` in
`pipeline/core/config.py`, plus new `.project/stages/*.extra.md` handling and
the `machine.FENCED` addition the ticket calls for. That is design work, not
a few-line fix -- result is `ok`, planning should pick this up.

Committed the test on `ticket/038` at `46115a1`.

### 2026-08-23 14:26:10Z · triage · session · session=ce400040-98ea-4480-8a07-4c52544918f7

`triage` ran as session `ce400040-98ea-4480-8a07-4c52544918f7`
- replay: `claude --resume ce400040-98ea-4480-8a07-4c52544918f7`
- log: `.project/logs/TICKET-038-triage-ce400040.log`

### 2026-08-23 14:26:10Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced with a failing test; stage_config() rejects project= exactly as reported.

### 2026-08-23 14:33:35Z · planning · note

Planned as one change, not two: the TOML half and the `.extra.md` half share
`stage_config()`'s call sites in `pipeline/daemon/supervisor.py`, so splitting
them would ship a project parameter nothing passes.

Two findings the implementer needs and cannot get from the ticket text:

1. `tests/test_pty.py:393` spawns against a directory with no
   `.project/pipeline.toml`. `project_stage_config()` therefore returns `{}`
   on `PipelineError` rather than propagating it.
2. `machine.FENCED` matches paths exactly, so `.project/stages/` does not work
   as an entry until `fenced_touches()` reads a trailing `/` as a prefix. That
   is step 9, and `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file`
   forces the matching `CLAUDE.md` edit in step 10.

Scope note for the human, not a blocker. This plan does not fence
`.project/pipeline.toml`; TICKET-037 owns that file and is still at `planning`.
Until TICKET-037 lands, a committed `[stages.*]` table can grant a stage
`write`, `tools` or `permission_mode` and merge unattended. Landing TICKET-037
first closes that window. The plan is written to be correct either way.

### 2026-08-23 14:34:07Z · planning · session · session=44d97465-43bd-44dd-837e-f1b6f85ab1fa

`planning` ran as session `44d97465-43bd-44dd-837e-f1b6f85ab1fa`
- replay: `claude --resume 44d97465-43bd-44dd-837e-f1b6f85ab1fa`
- log: `.project/logs/TICKET-038-planning-44d97465.log`

### 2026-08-23 14:34:07Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned 13 steps: project= on stage_config/is_readonly/compose_prompt, .project/stages/*.extra.md, and a directory entry in machine.FENCED.

### 2026-08-23 14:34:19Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_stage_config_can_take_a_per_project_override` fails as required
```
_project_override _______________

tmp_path = PosixPath('/tmp/pytest-of-chezzijr/pytest-1/test_stage_config_can_take_a_p0')

    def test_stage_config_can_take_a_per_project_override(tmp_path):
        """TICKET-038: `stage_config()` resolves against the packaged stage only,
        with no way for a project to add a model, tool or skill of its own. A
        project that wants `review` to run on a different model has nowhere to
        say so."""
        project = tmp_path / "proj"
        (project / ".project").mkdir(parents=True)
        (project / ".project" / "pipeline.toml").write_text(
            '[stages.review]\nmodel = "haiku"\n')
>       cfg = C.stage_config("review", project=project)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: stage_config() got an unexpected keyword argument 'project'

tests/test_stages.py:201: TypeError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_stage_config_can_take_a_per_project_override
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_stages.py::test_stage_config_can_take_a_per_project_override` fails on base `main` too -- the bug is not already fixed upstream
```
     (project / ".project" / "pipeline.toml").write_text(
            '[stages.review]\nmodel = "haiku"\n')
>       cfg = C.stage_config("review", project=project)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: stage_config() got an unexpected keyword argument 'project'

tests/test_stages.py:201: TypeError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_stage_config_can_take_a_per_project_override
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-a1gt0ama/base
      Built pipeline @ file:///tmp/pipeline-base-a1gt0ama/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-23 14:40:00Z · plan-validation · note

**PASS on all eight items**, scored against the tree.
long: eight judgment items, each needs its own evidence line.

1. Root cause: resolution is packaged-only. `stage_config()` (`config.py:24`),
   `is_readonly()` (`:35`) and `compose_prompt()` (`:53`) read
   `STAGES_DIR / f"{stage}.md"` and take no project, so no project can change a
   stage setting or add prose. The plan adds the layer there, not at the test.
2. Decisions: DEC-031 and DEC-034 constrain `FENCED` and the `awaiting-merge`
   park; the plan adds a `FENCED` entry and changes no result polarity, so it
   complies. DEC-023 also binds and is not cited: it fixes the view's place in
   the composed prompt. Order stays rules, extra, view, so it complies too.
3. Scope: 12 of 13 steps trace to a criterion. Step 13's `README.md` and
   `pipeline/templates/pipeline.toml` edits trace only to the suite-green
   criterion. Accepted: `README.md:428` lists this feature under
   `## Not built yet`, so skipping that edit ships a false statement.
4. Criteria are falsifiable. Packaged `review.md` carries `model: opus`,
   `effort: high`, `hooks: [dangerous-commands]`, so the merge assertions and
   the `haiku`-in-the-log assertion each fail on a wrong implementation.
5. No research left. The three call sites are exact: `stage_config` at
   `supervisor.py:320`, `compose_prompt` at `:365`, `is_readonly` at `:648`.
   Grep finds no fourth caller of the three functions.
6. Riskiest step: 10, the `FENCED` entry. `tests/test_stages.py:179` compares
   the backticked tokens of one `CLAUDE.md` sentence with `machine.FENCED`, and
   its `rstrip("()")` leaves `.project/stages/` intact, so the six-token
   sentence matches. `## Rollback` states the fallback: revert
   `pipeline/core/machine.py` and `CLAUDE.md` in one step.
7. Regression surface, each with its cover:
   - `tests/test_pty.py:393` spawns on a bare temp dir with no
     `.project/pipeline.toml`; step 2 returns `{}` on `PipelineError`. Covered
     by `tests/test_pty.py`.
   - Step 9's branch fires only on a key ending `/`, and no current `FENCED`
     key ends that way. Covered by `tests/test_fence.py`.
   - Every existing caller keeps its behaviour through `project=None`. Covered
     by `tests/test_stages.py` and `tests/test_dispatch.py`.
   - New failure mode: a `stages` value of the wrong type makes step 2 raise at
     `supervisor.py:648`, outside `start()`'s `except PipelineError` at `:575`.
     `tick()` catches every exception from `start()` at `:965` and continues, so
     invariant 6 holds and the lease expires on the charged path.
8. Blast radius: `class: feature`, 7 declared files plus 3 test files. In class.

`.project/stages/` is not in `.gitignore`, which lists only `.project/logs/`,
`.project/tickets/*.result` and `.project/.lock`. A committed `.extra.md`
therefore enters the diff and trips the fence. The plan's premise holds.

### 2026-08-23 14:38:05Z · plan-validation · session · session=5776fb3d-8a43-4c81-b0ab-8bfe70e0b9be

`plan-validation` ran as session `5776fb3d-8a43-4c81-b0ab-8bfe70e0b9be`
- replay: `claude --resume 5776fb3d-8a43-4c81-b0ab-8bfe70e0b9be`
- log: `.project/logs/TICKET-038-plan-validation-5776fb3d.log`

### 2026-08-23 14:38:05Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight judgment items; three call sites and the fence test verified in the tree.

### 2026-08-23 16:34:22Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-23 16:46:06Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_stage_config_can_take_a_per_project_override` fails as required
```
_project_override _______________

tmp_path = PosixPath('/tmp/pytest-of-chezzijr/pytest-3/test_stage_config_can_take_a_p0')

    def test_stage_config_can_take_a_per_project_override(tmp_path):
        """TICKET-038: `stage_config()` resolves against the packaged stage only,
        with no way for a project to add a model, tool or skill of its own. A
        project that wants `review` to run on a different model has nowhere to
        say so."""
        project = tmp_path / "proj"
        (project / ".project").mkdir(parents=True)
        (project / ".project" / "pipeline.toml").write_text(
            '[stages.review]\nmodel = "haiku"\n')
>       cfg = C.stage_config("review", project=project)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: stage_config() got an unexpected keyword argument 'project'

tests/test_stages.py:201: TypeError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_stage_config_can_take_a_per_project_override
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_stages.py::test_stage_config_can_take_a_per_project_override` fails on base `main` too -- the bug is not already fixed upstream
```
    (project / ".project" / "pipeline.toml").write_text(
            '[stages.review]\nmodel = "haiku"\n')
>       cfg = C.stage_config("review", project=project)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: stage_config() got an unexpected keyword argument 'project'

tests/test_stages.py:201: TypeError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_stage_config_can_take_a_per_project_override
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-t2cyuny5/base
      Built pipeline @ file:///tmp/pipeline-base-t2cyuny5/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-23 · implementing · note

**Todo, one entry per plan step:**

1. [x] Confirm the reproduction fails as stated.
2. [x] Add `project_stage_config()`.
3. [x] `stage_config()` takes `project`, merges shallow. Commit.
4. [x] Add `test_a_project_override_merges_onto_the_packaged_frontmatter`.
5. [x] `is_readonly()` takes `project`. Commit.
6. [x] Add `test_a_project_appends_prose_to_a_stage_prompt`.
7. [x] Add `stage_extra()`; `compose_prompt()` takes `project`, appends prose. Commit.
8. [x] Add `test_a_directory_entry_trips_on_any_file_under_it`.
9. [x] `fenced_touches()` reads a trailing `/` key as a directory. Commit.
10. [x] `.project/stages/` joins `machine.FENCED` and the `CLAUDE.md` sentence. Commit.
11. [x] Add `test_a_project_override_reaches_the_spawned_command_and_prompt`.
12. [x] Wire `project` through `spawn()`'s two call sites and `start()`'s. Commit.
13. [x] Document both halves in `pipeline/templates/pipeline.toml` and `README.md`. Commit.

All 13 steps done, one per commit from step 3 onward (steps 1-2 and 4-6-7 etc
land together where TDD red/green pairs share a commit). Two findings beyond
the plan's text, both detailed in `## Summary`:

1. `head_file()` needed an `is_dir()` guard -- the plan's own step-4 test
   (`project=tmp_path / "nothing"`) trips `subprocess.run`'s
   `FileNotFoundError` on a `cwd` that does not exist. Fixed in
   `pipeline/core/worktree.py`, inside `files_declared`.
2. Step 10 said "exactly six" backticked tokens for the `CLAUDE.md` sentence;
   the tree had seven before this ticket (two the plan's list omitted:
   `pipeline/harnesses/claude-code.toml`, `.project/pipeline.toml`) and needs
   eight after adding `.project/stages/`. Used the actual `machine.FENCED`
   set, not the plan's count; `test_the_fenced_list_matches_the_rule_file`
   confirms it.

`uv run --group dev pytest -q`: 240 passed.
`./pipeline/hooks/test_dangerous_commands.py`: exit 0.
Commits: `27d2fbd` `a37a34e` `9e40b4a` `63621f7` `2c76066` `1cc3216` `f7a93be`.

### 2026-08-23 16:46:06Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-23 16:51:06Z · implementing · session · session=c49bb6fd-89a6-441f-8dc2-108fc2123dfa

`implementing` ran as session `c49bb6fd-89a6-441f-8dc2-108fc2123dfa`
- replay: `claude --resume c49bb6fd-89a6-441f-8dc2-108fc2123dfa`
- log: `.project/logs/TICKET-038-implementing-c49bb6fd.log`

### 2026-08-23 16:51:06Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed all 13 plan steps; stage_config/is_readonly/compose_prompt take project, .project/stages/*.extra.md appends prose, fence gained a directory entry; full suite (240) and guard script pass.

### 2026-08-23 · review · note

**review: no blocking findings.** I reviewed the eight commits
`e6b7295..f7a93be` (`git diff main...HEAD`, 11 files, every one in
`files_declared`). Every acceptance criterion holds: `uv run --group dev pytest
-q` -- `240 passed in 10.30s`; `uv run --group dev python
pipeline/hooks/test_dangerous_commands.py` -- `guard: all passed`, `exit=0`.
Plan steps 2, 3, 5, 7, 9, 10, 12 and 13 match the tree.

Three charges I dropped:
- The guard and the snapshot could disagree under `write = true`. Refuted:
  `supervisor.py:377` sets `PIPELINE_READONLY` from the same merged `cfg`, and
  `:648` calls `is_readonly(stage, project)`.
- `head_file()`'s new `is_dir()` guard could mask a real git failure. Refuted:
  `config.py:84` is its only caller and falls back to disk, then raises.
- The dispatch test could pass vacuously. Refuted: the packaged model is
  `model: opus` (`pipeline/stages/review.md:2`), so `haiku` is a real
  assertion.

Non-blocking findings:

1. minor -- `pipeline/core/fence.py:3` and `pipeline/core/machine.py:14` still
   say "six things". `FENCED` now holds seven entries.
2. minor -- `is_readonly(stage, project)` at `supervisor.py:648` sits outside
   `start()`'s `try` at `:650`. A non-table `[stages]` raises there. `tick()`
   catches it at `:965`, so the loop survives, but the ticket holds the lease
   taken at `:643` and burns `lease_expiries` instead of `bail()`'s clean
   escalation.
3. minor -- override values are not type-checked. `write = "false"` is truthy
   in Python, so it grants write access. `project_stage_config()` validates
   table shape only.
4. note -- `stage_extra()` reads disk, so an uncommitted `.extra.md` in the
   main checkout reaches the next spawn with nothing in the ticket's diff. That
   is this ticket's own decision, deferred to TICKET-037. Not charged.
5. note -- this branch does not park itself. I ran `fenced_touches(Path('.'),
   'main')` in the worktree and it returned `[]`, although the diff edits the
   `CLAUDE.md` guard paragraph, `FENCED` and `fenced_touches()` itself.
   `CLAUDE.md` and `pipeline/core/fence.py` are not `FENCED` keys, and the
   `machine.py` key is symbol-scoped to `transition` and `CONTROL_FIELDS`. That
   scope predates this ticket, so it is out of scope here. Adding a `FENCED`
   entry only tightens the fence.

### 2026-08-23 16:56:45Z · review · session · session=3c9ffbeb-f9ab-4366-bee4-417e7b9c3215

`review` ran as session `3c9ffbeb-f9ab-4366-bee4-417e7b9c3215`
- replay: `claude --resume 3c9ffbeb-f9ab-4366-bee4-417e7b9c3215`
- log: `.project/logs/TICKET-038-review-3c9ffbeb.log`

### 2026-08-23 16:56:45Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed e6b7295..f7a93be: no blocking findings; 240 passed, guard exit 0, all acceptance criteria hold; five non-blocking notes appended.

### 2026-08-23 16:56:57Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-23 16:56:58Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/038


Already up to date.
Updating 5e2866c..f7a93be
Fast-forward
 CLAUDE.md                        |  4 +--
 README.md                        | 25 +++++++++++++++--
 pipeline/core/config.py          | 59 ++++++++++++++++++++++++++++++++++++----
 pipeline/core/fence.py           |  5 ++++
 pipeline/core/machine.py         |  4 +++
 pipeline/core/worktree.py        |  2 ++
 pipeline/daemon/supervisor.py    |  6 ++--
 pipeline/templates/pipeline.toml | 11 ++++++++
 tests/test_dispatch.py           | 35 ++++++++++++++++++++++++
 tests/test_fence.py              | 10 +++++++
 tests/test_stages.py             | 50 ++++++++++++++++++++++++++++++++++
 11 files changed, 198 insertions(+), 13 deletions(-)

```

### 2026-08-23 16:56:58Z · merging · decision

decision recorded as `DEC-038`
