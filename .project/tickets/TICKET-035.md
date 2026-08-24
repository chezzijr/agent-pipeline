---
id: TICKET-035
stage: escalated
class: feature
branch: ticket/035
test_file: tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage
files_declared:
- pipeline/core/config.py
- pipeline/daemon/supervisor.py
- tests/test_stages.py
- tests/test_dispatch.py
- README.md
- CLAUDE.md
- pipeline/templates/pipeline.toml
counters:
  plan_validation_attempts: 2
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: planning
  id: ee0c98d7-d6b5-40bf-9e4d-31160bd4dfa6
  log: .project/logs/TICKET-035-planning-ee0c98d7.log
---

## Summary

A project cannot override a stage, so customising one stage changes every registered project.

`stage_config()`, `agent_stages()` and `compose_prompt()`
(`pipeline/core/config.py`) all resolve exclusively against
`STAGES_DIR = PKG / "stages"`, the packaged directory. None of the three, nor
their only call sites (`pipeline/daemon/supervisor.py:320,365`), take a
project path. Frontmatter is what selects a stage's model, effort, tools,
hooks and `skills:`, so today there is no way to customise any of those for
one project without changing them for all.

Expected: a project may place `<project>/.project/stages/<name>.md` and have
it shadow the packaged stage of the same name, with the packaged one used
when there is no override. `agent_stages()` must also see the override, or it
is invisible to `pipeline ls` and to `test_every_stage...`.

Related: TICKET-036 wants per-project MCP config and is the same missing seam.

Planning rewrote the plan on 2026-08-23, after plan-validation rejected the
first one. Ten steps, eleven named tests, seven files. It adds `stage_file()`,
`_frontmatter()` and `_clamp()` to `pipeline/core/config.py`, a `project`
parameter to `stage_config()`, `is_readonly()`, `compose_prompt()` and
`agent_stages()`, and passes `project` at
`pipeline/daemon/supervisor.py:320,365,648`. An override shadows the packaged
file whole except two keys: `hooks` is unioned with the packaged stage's and
`write` is and-ed with it. A project can add a hook and narrow write access; it
can never drop the guard or grant write.

## Digest

Files touched: `pipeline/core/config.py` (the seam), `pipeline/daemon/supervisor.py`
(three call sites plus one `try:` boundary), `tests/test_stages.py`,
`tests/test_dispatch.py`, `README.md`, `CLAUDE.md`,
`pipeline/templates/pipeline.toml`.

Key functions, all in `pipeline/core/config.py`: `stage_config()` line 24,
`agent_stages()` line 31, `is_readonly()` line 35, `compose_prompt()` line 53,
`render()` line 80, `_tools()` line 140, `stage_settings()` line 151. The first
four read `STAGES_DIR = PKG / "stages"` (line 17) and take no project path.
`stage_settings(stage, cfg)` turns `cfg["hooks"]` into the `PreToolUse` settings
file, so frontmatter is what registers the guard.

Entry points: `spawn()` (`pipeline/daemon/supervisor.py:316`) already takes
`project` and calls `stage_config(stage)` at line 320 and
`compose_prompt(stage, hcfg, view)` at line 365. `start()` (line 508) also takes
`project` and calls `is_readonly(stage)` at line 648. No CLI command calls
`agent_stages()` -- `pipeline ls` lists tickets. Its callers are four test files:
`tests/test_stages.py`, `tests/test_machine.py`, `tests/test_harness.py`,
`tests/test_dispatch.py:105`.

### Changes since the rejected plan

plan-validation rejected the first plan with four findings. This plan differs
from it in exactly these places.

1. **`write:` is clamped, like `hooks`.** The first plan left it open, so an
   override declaring `write: true` gave every later `review` spawn
   `PIPELINE_READONLY=0` (`pipeline/daemon/supervisor.py:377`), the guard's
   blocklist instead of its read-only allowlist, and no tree snapshot. `_clamp()`
   now sets `meta["write"] = bool(base.get("write")) and bool(meta.get("write"))`.
   Step 4, with `test_a_project_override_cannot_grant_write` and, through the
   dispatcher, `test_a_project_override_cannot_turn_off_the_readonly_snapshot`.
2. **The `agent_stages` test can fail.** The old assertion
   `C.agent_stages(project=d) == C.agent_stages()` passed for a body that ignored
   `project`. The new test writes a project-only stem `audit.md` and asserts
   `"audit" in C.agent_stages(project=d)`, `stages.count("review") == 1` and
   `"audit" not in C.agent_stages()`. Step 5.
3. **A project-only stage is defined.** With no packaged file the clamp baseline
   is `GUARD_FLOOR = {"hooks": ["dangerous-commands"], "write": False}`, so
   `stage_config()` returns the override's own frontmatter with the guard hook
   added and `write` False. It does not raise. Step 3, with
   `test_a_project_only_stage_gets_the_guard_floor`.
4. **The `_frontmatter()` rationale is corrected and the line-648 path is
   fixed.** `tick()` catches `Exception` (`pipeline/daemon/supervisor.py:965`),
   so a `ValueError` does not end the loop. It aborts `start()` after
   `take_lease()` (line 642), so the ticket waits out two 30-minute leases
   (`LEASE_MINUTES = 30`, `MAX_ATTEMPTS = 2`) and escalates as "lease expired
   twice". `_frontmatter()` stays; step 9 moves `is_readonly()` inside `start()`'s
   `try:` at line 650 so its `PipelineError` reaches `bail()`.

### Gotchas

- `readonly_tools = "Read,Grep,Glob,Bash,Write,Edit"`
  (`pipeline/harnesses/claude-code.toml:29`) already includes `Write` and `Edit`,
  because a read-only stage has to write its `.result` sidecar. So `tools:` is
  *not* the read-only boundary, and this plan leaves it freely overridable. The
  boundary is `write:`: it picks the guard's allowlist over its blocklist
  (`pipeline/hooks/dangerous-commands.py:238`) and decides whether `start()`
  takes a tree snapshot. That is why exactly `write` and `hooks` are clamped.
- `KNOWN_STAGES` comes from `pipeline/core/machine.py:24`, and `validate_meta()`
  (`pipeline/core/ticket.py:63`) rejects a ticket whose `stage` is not in it. An
  override can therefore only shadow a stage `transition()` already names; a
  project-only file is listable but never reachable.
- `split_frontmatter()` (`pipeline/core/ticket.py:86`) raises `ValueError` on a
  file that does not start with `---\n`, and PyYAML raises `yaml.YAMLError` on a
  frontmatter block it cannot parse. Neither is a `PipelineError`, and `start()`
  catches only `PipelineError` (line 652).
- `.project/` is excluded from the read-only tree snapshot and is passed as
  `--add-dir {project}`, so `<project>/.project/stages/*.md` is writable by a
  `write: true` stage. DEC-034: "the absence of an agent-writable settings source
  is" the promise.
- `compose_prompt()`'s third positional parameter is `view`, and
  `tests/test_stages.py:57` passes it positionally. `project` must be the fourth
  parameter, not the second.
- `spawn()` writes `f"$ {cmd}\n\n"` as the first line of `rec["log"]`
  (`pipeline/daemon/supervisor.py:373`), and `pipeline/harnesses/fake.toml`'s
  `cmd` contains `{model}`. A `start()` test can therefore read back which stage
  config reached the child. That is what makes the step 8 dispatch test fail
  before the wiring lands.
- Packaged `pipeline/stages/review.md` declares `model: opus`,
  `hooks: [dangerous-commands]` and `write: false`; the committed reproduction
  overrides `review`.
- `tests/test_stages.py` uses plain `try`/`except`. No test file in this repo
  imports pytest, so `pytest.raises` is not the local idiom.

## Decisions checked

Grepped `/home/chezzijr/proj/agent-pipeline/.project/decisions/` for
`stage_config`, `agent_stages`, `compose_prompt`, `STAGES_DIR`, `override`,
`.project/stages`, `frontmatter`, `PKG`, `packaged`, `readonly_tools`,
`allowlist`, `read-only`, `write:`, `tools`, `superseded-by`.

- DEC-034 constrains this change. The guard is defended by the dispatcher, and
  "the absence of an agent-writable settings source is" the promise. A project
  stage file is agent-writable, so `hooks` is unioned and `write` is and-ed.
- DEC-026 constrains the `write` clamp: "The fix is to run the base check
  dispatcher-side before `quick-review`, not to give the stage write access."
  A read-only review stage stays read-only, whatever a project file declares.
- DEC-023 constrains `compose_prompt()`: the view rides in the composed system
  prompt. This plan adds a fourth parameter and leaves that assembly unchanged.
- DEC-021 (TUI raw mode) is not relevant. No record in the directory carries a
  `superseded-by:` line, and this plan supersedes none.

## Plan

1. Run `uv run --group dev pytest -q tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage` and confirm the output contains `TypeError: stage_config() got an unexpected keyword argument 'project'`; this is the reproduction committed at `0c8c32d`, and `tests/test_stages.py` is not edited in this step.
2. Build the seam in `pipeline/core/config.py`: add `def stage_file(stage: str, project: Path | None = None) -> Path:` after `CONFIG_TEMPLATE`, returning `project / ".project" / "stages" / f"{stage}.md"` when `project is not None` and that path `.is_file()`, else `STAGES_DIR / f"{stage}.md"`; add `project: Path | None = None` to `stage_config(stage, project=None)` and `is_readonly(stage, project=None)`, and as the FOURTH parameter of `compose_prompt(stage, hcfg=None, view="", project=None)`; both readers replace `STAGES_DIR / f"{stage}.md"` with `stage_file(stage, project)`, `is_readonly` forwards `project` to `stage_config`, and `_common.md` still comes from `STAGES_DIR` until step 7; run the step 1 command and see it pass, run `uv run --group dev pytest -q tests/test_stages.py tests/test_harness.py`, commit.
3. Add `test_a_project_override_cannot_drop_the_guard_hook` and `test_a_project_only_stage_gets_the_guard_floor` to `tests/test_stages.py` -- the first builds a tempdir project with `.project/stages/review.md` holding `---\nmodel: OVERRIDE-MODEL\nwrite: false\n---\n\nOVERRIDE BODY\n` and asserts `C.stage_config("review", project=d)["hooks"] == ["dangerous-commands"]`, then a second project whose override declares `hooks: [extra-hook, dangerous-commands]` and asserts the result is exactly `["dangerous-commands", "extra-hook"]`, then a third whose override declares `hooks: nope` and asserts `PipelineError`; the second builds a project with `.project/stages/audit.md` (no packaged `audit`) and asserts `C.stage_config("audit", project=d)["hooks"] == ["dangerous-commands"]`; watch both fail, then in `pipeline/core/config.py` add `GUARD_FLOOR = {"hooks": ["dangerous-commands"], "write": False}` and `def _clamp(meta: dict, base: dict, path: Path) -> dict:` which raises `PipelineError(f"stage file {path}: hooks must be a list, got {own!r}")` when `meta["hooks"]` is neither `None` nor a `list` and otherwise sets `meta["hooks"] = list(dict.fromkeys((base.get("hooks") or []) + (own or [])))`, and have `stage_config()` call `_clamp(meta, base, path)` when `stage_file(stage, project) != STAGES_DIR / f"{stage}.md"`, with `base = split_frontmatter(STAGES_DIR / f"{stage}.md")[0]` when the packaged file exists and `GUARD_FLOOR` when it does not; run the two tests green, commit.
4. Add `test_a_project_override_cannot_grant_write` to `tests/test_stages.py`: a project whose `.project/stages/review.md` declares `write: true`, asserting `C.stage_config("review", project=d)["write"] is False` and `C.is_readonly("review", d) is True`, plus a `.project/stages/implementing.md` declaring `write: false`, asserting `C.stage_config("implementing", project=d)["write"] is False` while `C.stage_config("implementing")["write"] is True`; watch it fail with `assert True is False`; then add the single line `meta["write"] = bool(base.get("write")) and bool(meta.get("write"))` to `_clamp()` in `pipeline/core/config.py`; run it green, run `uv run --group dev pytest -q tests/test_stages.py`, commit.
5. Add `test_agent_stages_lists_a_project_only_stage_and_no_duplicate` to `tests/test_stages.py`: a project holding `.project/stages/review.md`, `.project/stages/audit.md` and `.project/stages/_common.md`, asserting for `stages = C.agent_stages(project=d)` that `stages.count("review") == 1`, `"audit" in stages`, `"_common" not in stages`, `stages == sorted(stages)`, and that `"audit" not in C.agent_stages()`; watch it fail with `agent_stages() got an unexpected keyword argument 'project'`; then in `pipeline/core/config.py` make `agent_stages(project: Path | None = None) -> list[str]` collect the stems of `STAGES_DIR.glob("*.md")`, add the stems of `(project / ".project" / "stages").glob("*.md")` when `project is not None`, drop every stem starting with `_`, and `return sorted(set(...))`; run it green, commit.
6. Add a module-level `_raises(fn)` helper to `tests/test_stages.py` returning the `PipelineError` message or `""`, and `test_a_malformed_override_raises_pipelineerror`: a project whose `.project/stages/review.md` is the single line `no frontmatter here`, asserting `"review.md" in _raises(lambda: C.stage_config("review", project=d))` and `"review.md" in _raises(lambda: C.compose_prompt("review", project=d))`, then rewriting that file as `---\nmodel: [oops\n---\n\nB\n` and asserting `_raises(lambda: C.stage_config("review", project=d))` is non-empty; watch it fail with an uncaught `ValueError: ...: no frontmatter`; then in `pipeline/core/config.py` add `import yaml` and `def _frontmatter(path: Path) -> tuple[dict, str]:` which wraps `return split_frontmatter(path)` in `except (OSError, ValueError, yaml.YAMLError) as e: raise PipelineError(f"stage file {path}: {e}") from e`, and route all three `split_frontmatter` calls in that file through it; run it green, commit.
7. Add `test_a_project_can_override_the_shared_rules` to `tests/test_stages.py`: a project holding `.project/stages/_common.md` with the text `COMMON-OVERRIDE-4471` and a `.project/stages/review.md`, asserting the text of `C.compose_prompt("review", project=d)` contains `COMMON-OVERRIDE-4471` and not `Failure protocol`, and that the text of `C.compose_prompt("review")` still contains `Failure protocol` and not `COMMON-OVERRIDE-4471`; watch it fail; then in `pipeline/core/config.py` change `compose_prompt()` to read `stage_file("_common", project).read_text()` in place of `(STAGES_DIR / "_common.md").read_text()`; run it green, commit.
8. Wire the seam into the dispatcher: add `test_spawn_uses_the_projects_stage_override` to `tests/test_dispatch.py` (`d = project()`, write `.project/stages/review.md` with `model: OVERRIDE-MODEL`, `write: false` and the body `OVERRIDE BODY`, set `hcfg = {**harness("fake"), "cmd": "echo {model} > {result_file}; cat {stage_prompt} >> {result_file}"}`, call `rec = supervisor.spawn(d, d, "TICKET-001", "review", hcfg)`, `rec["proc"].wait()`, `supervisor.close_child(rec)`, and assert the text of `d / ".project/tickets/TICKET-001.result"` contains `OVERRIDE-MODEL` and `OVERRIDE BODY`) and `test_a_project_override_cannot_turn_off_the_readonly_snapshot` to `tests/test_dispatch.py` (`d, sh = git_project()`, ticket rewritten to `stage: review`, override declaring `model: OVERRIDE-MODEL` and `write: true`, `did, rec = supervisor.start(d, path, harness("fake"), {})`, `rec["proc"].wait()`, `supervisor.close_child(rec)`, assert `"OVERRIDE-MODEL" in rec["log"].read_text()` and `rec["before"] is not None`); watch both fail on the packaged `opus`; then in `pipeline/daemon/supervisor.py` change line 320 to `cfg = stage_config(stage, project)`, line 365 to `prompt = compose_prompt(stage, hcfg, view, project)` and line 648 to `is_readonly(stage, project)`; run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_stages.py tests/test_daemon.py tests/test_harness.py tests/test_pty.py tests/test_machine.py`, commit.
9. Add `test_a_malformed_stage_override_escalates_one_ticket` to `tests/test_dispatch.py`: `d, _ = git_project()`, the ticket rewritten to `stage: review`, `.project/stages/review.md` holding the single line `no frontmatter here`, then `did, rec = supervisor.start(d, path, harness("fake"), {})` and assertions that `(did, rec) == (True, None)`, `Ticket.load(path).stage == "escalated"`, `not t.lease_active()` and `"review.md" in t.section("Thread")`; watch it fail with the `PipelineError` escaping `start()`; then in `pipeline/daemon/supervisor.py` move lines 648 and 649 (`before = tree_snapshot(wt) if is_readonly(stage, project) else None` then `drop_result(project, tid)`) inside the existing `try:` at line 650, keeping that order and putting them above the `spawn()` call, so `bail()` catches it; run `uv run --group dev pytest -q tests/test_dispatch.py`, commit.
10. Document the seam and pin the documentation: in `README.md` delete the two-line "Per-project stage overrides" bullet at lines 428-429 and add a `## Customising a stage for one project` section immediately before `## Interactive stages` (line 167) stating that `<project>/.project/stages/<name>.md` shadows the packaged stage whole, that `hooks:` is the union with the packaged stage's so `dangerous-commands` cannot be dropped, that `write:` is and-ed with the packaged stage's, that `_common.md` is shadowed the same way, and that only a stage `transition()` names is ever run; add a `<project>/.project/stages/<name>.md` row to the "Where things live" table in `CLAUDE.md`; add the two comment lines `# Per-project stage overrides live in .project/stages/<name>.md, not here: they` and `# shadow the packaged stage, except hooks: (unioned) and write: (and-ed).` to `pipeline/templates/pipeline.toml`; add `test_the_readme_documents_the_override_seam_and_its_clamp` to `tests/test_stages.py` asserting `"Per-project stage overrides" not in readme` and that the 1200 characters following the first `.project/stages/<name>.md` contain `union`, `dangerous-commands`, `write:` and `transition()`; run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, commit.

## Acceptance criteria

- `tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage` passes: the override's `model` and body reach `stage_config()` and `compose_prompt()`.
- `tests/test_stages.py::test_a_project_override_cannot_drop_the_guard_hook` passes: an override with no `hooks:` still yields `["dangerous-commands"]`, one declaring `hooks: [extra-hook, dangerous-commands]` yields `["dangerous-commands", "extra-hook"]`, and `hooks: nope` raises `PipelineError`.
- `tests/test_stages.py::test_a_project_only_stage_gets_the_guard_floor` passes: a stage with no packaged file returns `hooks: ["dangerous-commands"]` and does not raise.
- `tests/test_stages.py::test_a_project_override_cannot_grant_write` passes: `write: true` in an override yields `write` False and `is_readonly()` True, and `write: false` over `implementing` yields False.
- `tests/test_stages.py::test_agent_stages_lists_a_project_only_stage_and_no_duplicate` passes: `audit` is listed for that project, `review` appears once, `_common` never, and `audit` does not leak into `agent_stages()`.
- `tests/test_stages.py::test_a_malformed_override_raises_pipelineerror` passes: a file with no frontmatter, and one with unparseable YAML, both raise `PipelineError` naming the file.
- `tests/test_stages.py::test_a_project_can_override_the_shared_rules` passes: `.project/stages/_common.md` replaces the packaged shared rules in the composed prompt, for that project only.
- `tests/test_dispatch.py::test_spawn_uses_the_projects_stage_override` passes: the override's model reaches the rendered command and its body reaches the composed prompt through `spawn()`.
- `tests/test_dispatch.py::test_a_project_override_cannot_turn_off_the_readonly_snapshot` passes: with `write: true` in the override, `rec["log"]` names `OVERRIDE-MODEL` and `rec["before"]` is not `None`.
- `tests/test_dispatch.py::test_a_malformed_stage_override_escalates_one_ticket` passes: the ticket reaches `escalated`, its lease is released, and the thread names `review.md`.
- `tests/test_stages.py::test_the_readme_documents_the_override_seam_and_its_clamp` passes: the README documents the seam, the `hooks` union and the `write` clamp, and no longer lists the seam under "Not built yet".
- `uv run --group dev pytest -q` is green, and `./pipeline/hooks/test_dangerous_commands.py` still reports its 79 guard cases passing.

## Decisions

**A project stage file shadows the packaged one whole, not key by key.** The
docstring's promise is that a stage is one self-contained file; a key-level
merge would mean an override that sets `tools:` silently inherits `write:` from
a file the author never opened. `stage_file()` picks one file, and everything
but `hooks` and `write` comes from it.

**`hooks` and `write` are the two exceptions: an override may narrow a stage's
authority, never widen it.** `<project>/.project/stages/` is agent-writable --
`.project/` is excluded from the read-only tree snapshot and reaches a spawn
through `--add-dir {project}` -- so a `write: true` stage could otherwise write
`.project/stages/review.md` and change what every later spawn in that project is
allowed to do. Two keys carry that authority. `hooks:` registers the guard, so it
is the union with the packaged stage's: a project can add a hook, never remove
`dangerous-commands`. `write:` decides `PIPELINE_READONLY`
(`pipeline/daemon/supervisor.py:377`), which picks the guard's *allowlist* over
its blocklist, and decides whether `start()` takes a tree snapshot at all, so it
is and-ed: a project can make a write stage read-only, never the reverse. That is
DEC-034's threat model with a new door, and invariant 4 says a hook is the only
layer that promises. Do not "simplify" either clamp back into a plain override.

**`tools:` is deliberately NOT clamped.** `readonly_tools` already contains
`Write` and `Edit` (`pipeline/harnesses/claude-code.toml:29`), because a
read-only stage has to write its `.result` sidecar; the toolset is therefore not
the read-only boundary and never was. Prevention for the shell is the guard,
detection for the file tools is the snapshot, and both are keyed on `write:`,
which is clamped. Clamping `tools:` as well would buy nothing and would break the
customisation this ticket exists to allow.

**A project-only stage file gets `GUARD_FLOOR` as its clamp baseline.** With no
packaged file there is nothing to inherit, so the floor supplies
`hooks: [dangerous-commands]` and `write: false`. Such a file is listable and
unrunnable today -- `validate_meta()` rejects a ticket whose `stage` is not in
`KNOWN_STAGES`, which comes from `transition()` -- but the floor is what keeps it
safe if someone later adds the `transition()` row and forgets the guard. Adding a
stage is still a `transition()` row.

**`_common.md` resolves through the same lookup as a stage.** One rule, no
special case: a project that replaces the shared rules is making the same choice
as one that replaces a stage prompt. The failure protocol lives in that file, so
a project that shadows it owns the consequence.

**Every stage-file read goes through `_frontmatter()`, and `is_readonly()` is
called inside `start()`'s `try:`.** `split_frontmatter()` raises `ValueError` and
PyYAML raises `YAMLError`. `tick()` catches `Exception`, so neither ends the
dispatcher loop, but both abort `start()` after `take_lease()`: a project file
with a typo in its frontmatter costs that ticket two 30-minute lease expiries
before it escalates as "lease expired twice". Routing the read through
`PipelineError` and calling `is_readonly()` below the `try:` sends it to `bail()`
instead, which escalates at once with the file named. Moving that call back above
the `try:` reopens it.

## Rollback

Revert the commits from steps 2 to 10. Every `project` parameter defaults to
`None` and every existing caller omits it, so reverting
`pipeline/daemon/supervisor.py` alone (lines 320, 365, 648 and the `try:`
boundary from step 9) restores the packaged-stage behaviour while leaving
`pipeline/core/config.py` importable and every existing test green. A project
that has already written `<project>/.project/stages/` keeps the files; they
simply stop being read.

## Thread

### 2026-08-23 11:25:41Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-23 · triage · reproduction

Confirmed. `stage_config()`, `agent_stages()`, `compose_prompt()`
(`pipeline/core/config.py`) and their only callers
(`pipeline/daemon/supervisor.py:320,365`) take no project path -- verified by
reading every call site, not just the three functions.

Added `tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage`.
It builds a project with `.project/stages/review.md` and calls
`C.stage_config("review", project=project)`; fails with
`TypeError: stage_config() got an unexpected keyword argument 'project'`.
Committed at `0c8c32d`.

Suggested fix files, not yet designed: `pipeline/core/config.py` (add
`project` param to the three functions and an override lookup),
`pipeline/daemon/supervisor.py` (pass `project` through at the two call
sites). This is a design decision (list-and-merge for `agent_stages()`,
override precedence), so leaving it to planning rather than calling it a
chore.

### 2026-08-23 11:29:47Z · triage · session · session=120033ff-f81f-4ed6-a6de-905896973c15

`triage` ran as session `120033ff-f81f-4ed6-a6de-905896973c15`
- replay: `claude --resume 120033ff-f81f-4ed6-a6de-905896973c15`
- log: `.project/logs/TICKET-035-triage-120033ff.log`

### 2026-08-23 11:29:47Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: stage_config()/compose_prompt() take no project path, so an override can't even be looked up. Failing test committed at 0c8c32d.

### 2026-08-23 · planning · note

Plan written. Nine steps, seven named tests, `files_declared` lists six files.

Scope: the ticket is one subsystem, so the plan covers all of it. TICKET-036
(per-project MCP config) is named as "the same missing seam" but touches
`pipeline/harnesses/claude-code.toml` and `--strict-mcp-config`, not
`pipeline/core/config.py`. It is left alone.

One finding the ticket did not state. `<project>/.project/stages/` is
agent-writable: `.project/` is excluded from the read-only tree snapshot and
reaches a spawn through `--add-dir {project}`. A `write: true` stage could
write `.project/stages/review.md` with no `hooks:` key and disable the guard
for every later spawn in that project, which is DEC-034's threat model with a
new door. The plan therefore unions `hooks` with the packaged stage's instead
of replacing it: a project can add a hook, never remove `dangerous-commands`.
`tests/test_stages.py::test_a_project_override_cannot_drop_the_guard_hook` is
the check, and `## Decisions` records why.

Second finding: `split_frontmatter()` raises `ValueError`, `stage_config()`
runs inside `spawn()`, and `start()` catches only `PipelineError`. A project
override with a typo in its frontmatter would end the dispatcher loop for every
other project too. Step 6 wraps every stage-file read in `_frontmatter()`.

The plan does not touch `machine.FENCED` code, so it is not a fenced diff.

No questions for the human.

### 2026-08-23 12:04:33Z · planning · session · session=5e269ba2-a4ea-410a-a109-ada18f5d08fc

`planning` ran as session `5e269ba2-a4ea-410a-a109-ada18f5d08fc`
- replay: `claude --resume 5e269ba2-a4ea-410a-a109-ada18f5d08fc`
- log: `.project/logs/TICKET-035-planning-5e269ba2.log`

### 2026-08-23 12:04:33Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: stage_file() + a project param on four config functions, wired at three supervisor call sites; hooks unioned so an override cannot drop the guard.

### 2026-08-23 12:04:45Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage` fails as required
```
e ______________

    def test_a_project_override_shadows_the_packaged_stage():
        """A project's own `.project/stages/<name>.md` must shadow the packaged
        stage of the same name -- today `stage_config`/`compose_prompt` take no
        project path at all, so the override is silently ignored and every
        project on the machine reads the same shared file."""
        project = Path(tempfile.mkdtemp())
        override_dir = project / ".project" / "stages"
        override_dir.mkdir(parents=True)
        (override_dir / "review.md").write_text(
            "---\nmodel: OVERRIDE-MODEL\nwrite: false\n---\n\nOVERRIDE BODY\n")
    
>       cfg = C.stage_config("review", project=project)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: stage_config() got an unexpected keyword argument 'project'

tests/test_stages.py:23: TypeError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage` fails on base `main` too -- the bug is not already fixed upstream
```
view.md").write_text(
            "---\nmodel: OVERRIDE-MODEL\nwrite: false\n---\n\nOVERRIDE BODY\n")
    
>       cfg = C.stage_config("review", project=project)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: stage_config() got an unexpected keyword argument 'project'

tests/test_stages.py:23: TypeError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-61_c9zsb/base
      Built pipeline @ file:///tmp/pipeline-base-61_c9zsb/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 48ms

```

### 2026-08-23 · plan-validation · note

Plan rejected. Four findings; the first two need a plan change.

1. **The plan closes `hooks:` and leaves `write:` open.** `spawn()` sets
   `env["PIPELINE_READONLY"] = "0" if cfg.get("write") else "1"`
   (`pipeline/daemon/supervisor.py:377`), and `cfg` becomes
   `stage_config(stage, project)` at step 8. So `.project/stages/review.md` with
   `write: true` gives every later `review` spawn the write toolset, the guard's
   blocklist instead of its read-only allowlist, and no tree snapshot
   (`is_readonly` returns False, so `before` is `None` at line 648). That is the
   agent-writable door the plan names, one key over. State whether `write:` may
   be overridden and why, or clamp it like `hooks`.
2. **`test_agent_stages_lists_a_project_override_once` cannot fail.** It asserts
   `C.agent_stages(project=d) == C.agent_stages()` for an override of `review`,
   a stage that is already packaged. A body that ignores `project` returns the
   packaged list and passes. Add a project-only stem and assert it appears once.
3. **Step 5 is undefined for a project-only stage.** It reads the packaged
   frontmatter to union hooks; no packaged file exists, so `stage_config()`
   raises. `## Decisions` says such a file is listable. Say what it returns.
4. **Step 6's rationale is wrong and its fix has a hole.** `tick()` catches
   `Exception` (`pipeline/daemon/supervisor.py:965`), so a `ValueError` never
   ends the loop -- it costs the ticket two lease expiries. And
   `is_readonly(stage, project)` at line 648 sits above the `try:` at line 650,
   so its `PipelineError` bypasses `bail()` too. Keep `_frontmatter()`; fix the
   reason and the line-648 path.

Verified and passing: root cause (the four functions resolve only against
`STAGES_DIR`, none takes a project path -- the plan builds the missing seam,
not a test-shaped patch); DEC-034 constrains and the `hooks` union complies
(DEC-034 line 12: "the absence of an agent-writable settings source is" the
promise); DEC-023 untouched; `project` as `compose_prompt()`'s fourth parameter
matches `tests/test_stages.py:57`; `{stage_prompt}` and `{result_file}` are real
`render()` placeholders (`pipeline/core/config.py:118`), so step 8 is runnable;
riskiest step is 8, and `## Rollback` names its three lines; every existing
caller omits `project` and defaults keep them green; class `feature`, seven
files -- proportionate. Step 9 (docs) traces to no acceptance criterion; the
README bullet it deletes spans two lines (README.md:428-429).

### 2026-08-23 12:08:13Z · plan-validation · session · session=437cab1a-1df2-416c-8fa5-56bf88b1ed16

`plan-validation` ran as session `437cab1a-1df2-416c-8fa5-56bf88b1ed16`
- replay: `claude --resume 437cab1a-1df2-416c-8fa5-56bf88b1ed16`
- log: `.project/logs/TICKET-035-plan-validation-437cab1a.log`

### 2026-08-23 12:08:13Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ Plan rejected: it clamps `hooks:` but an override's `write: true` still drops the read-only allowlist (supervisor.py:377), and the agent_stages test passes even if `project` is ignored.

### 2026-08-23 · planning · note

Plan rewritten against plan-validation's four findings. `## Digest` carries the
per-finding diff; the two that changed the design:

1. **`write:` is clamped, not just `hooks:`.** `_clamp()` now sets
   `meta["write"] = bool(base.get("write")) and bool(meta.get("write"))`. An
   override can make a write stage read-only; it cannot give a read-only stage
   `PIPELINE_READONLY=0`, the guard's blocklist, or a `None` tree snapshot.
   One rule covers both keys: an override may narrow a stage's authority, never
   widen it.
2. **`tools:` is left overridable, deliberately, and `## Decisions` says why.**
   `readonly_tools = "Read,Grep,Glob,Bash,Write,Edit"`
   (`pipeline/harnesses/claude-code.toml:29`) already grants a read-only stage
   `Write` and `Edit`, because it has to write its `.result` sidecar. The
   toolset is not the read-only boundary; `write:` is, and `write:` is clamped.

The other two findings are fixes, not design changes: the `agent_stages` test
now writes a project-only stem `audit.md` so it fails when `project` is ignored,
and a project-only stage gets `GUARD_FLOOR` as its clamp baseline instead of
raising. Step 9 moves `is_readonly()` inside `start()`'s `try:` so a malformed
override reaches `bail()` rather than costing two 30-minute lease expiries.

Ten steps, eleven named tests, seven files. Scope unchanged: TICKET-036
(per-project MCP config) touches `pipeline/harnesses/claude-code.toml` and
`--strict-mcp-config`, not `pipeline/core/config.py`, and is left alone. The
plan does not touch `machine.FENCED` code, so it is not a fenced diff.

No questions for the human.

### 2026-08-23 12:50:28Z · planning · session · session=ee0c98d7-d6b5-40bf-9e4d-31160bd4dfa6

`planning` ran as session `ee0c98d7-d6b5-40bf-9e4d-31160bd4dfa6`
- replay: `claude --resume ee0c98d7-d6b5-40bf-9e4d-31160bd4dfa6`
- log: `.project/logs/TICKET-035-planning-ee0c98d7.log`

### 2026-08-23 12:50:28Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan rewritten against plan-validation's four findings: `write:` is now clamped like `hooks:`, the agent_stages test uses a project-only stem, a project-only stage gets GUARD_FLOOR, and is_readonly() moves inside start()'s try.

### 2026-08-23 12:50:39Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- section `## Reproduction` missing or empty
- ok: `tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage` fails as required
```
e ______________

    def test_a_project_override_shadows_the_packaged_stage():
        """A project's own `.project/stages/<name>.md` must shadow the packaged
        stage of the same name -- today `stage_config`/`compose_prompt` take no
        project path at all, so the override is silently ignored and every
        project on the machine reads the same shared file."""
        project = Path(tempfile.mkdtemp())
        override_dir = project / ".project" / "stages"
        override_dir.mkdir(parents=True)
        (override_dir / "review.md").write_text(
            "---\nmodel: OVERRIDE-MODEL\nwrite: false\n---\n\nOVERRIDE BODY\n")
    
>       cfg = C.stage_config("review", project=project)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: stage_config() got an unexpected keyword argument 'project'

tests/test_stages.py:23: TypeError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage` fails on base `main` too -- the bug is not already fixed upstream
```
view.md").write_text(
            "---\nmodel: OVERRIDE-MODEL\nwrite: false\n---\n\nOVERRIDE BODY\n")
    
>       cfg = C.stage_config("review", project=project)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: stage_config() got an unexpected keyword argument 'project'

tests/test_stages.py:23: TypeError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jnfcbu2i/base
      Built pipeline @ file:///tmp/pipeline-base-jnfcbu2i/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-23 12:50:39Z · plan-validation · transition · to=escalated · result=fail

**plan-validation -> escalated** (result: `fail`)

Tier A gate failed:
- section `## Reproduction` missing or empty

### 2026-08-24 13:07:55Z · human · note · by=chezzijr

**Closed as superseded by TICKET-038**, which landed on 2026-08-24.

This ticket asked for `<project>/.project/stages/<name>.md` to shadow the
packaged stage whole. That design was abandoned, not deferred. TICKET-038
shipped the same capability append-only instead: `[stages.<name>]` in
`.project/pipeline.toml` for structured settings, and
`.project/stages/<name>.extra.md` appended to the packaged prompt for prose.

The two plan-validation rejections recorded above are why. A whole-file
override needs a clamp on every frontmatter key that grants privilege --
`hooks` (planned), `write` (this ticket's blocking finding), and `tools` and
`permission_mode`, which nobody had noticed. An `.extra.md` carries no
frontmatter at all, so there is nothing to clamp, and `[stages.*]` is reached
through `project_config()`, which TICKET-037 moved to read from HEAD. Three
clamps became one trust boundary.

Do not reopen this as written. If whole-file stage replacement is ever wanted
again, it needs those four clamps and an argument for why the append-only form
is insufficient.

Its reproduction, `tests/test_stages.py::test_a_project_override_shadows_the_packaged_stage`,
asserted the rejected API and was discarded; TICKET-038 committed its own.
Superseded by: TICKET-038, TICKET-037, TICKET-044.
