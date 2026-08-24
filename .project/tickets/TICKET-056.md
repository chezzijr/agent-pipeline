---
id: TICKET-056
stage: revalidating
class: feature
branch: ticket/056
test_file: tests/test_cli.py::test_init_installs_the_file_ticket_skill
files_declared:
- pipeline/cli/main.py
- pipeline/core/config.py
- pipeline/templates/skills/file-ticket/SKILL.md
- .claude/skills/file-ticket/SKILL.md
- tests/test_cli.py
- tests/test_stages.py
- CLAUDE.md
- README.md
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 12
  plan_files: 8
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: plan-validation
  id: fecb0e70-0f06-4984-98b7-53e83e1446fe
  log: .project/logs/TICKET-056-plan-validation-fecb0e70.log
approved_by: chezzijr
approved_at: '2026-08-24T15:07:03.749583+00:00'
waiting:
  'on': TICKET-055
  file: CLAUDE.md
  since: '2026-08-24T15:07:04.121578+00:00'
---

## Summary

the file-ticket skill is not installed into a project that pipeline init scaffolds

`pipeline init <project>` writes `.project/tickets/`, `.project/decisions/` and
`.project/pipeline.toml` (`cmd_init`, `pipeline/cli/main.py:38`), and that is
all. The one document that tells a session how to file a ticket ---
`.claude/skills/file-ticket/SKILL.md`, which `CLAUDE.md` calls part of the
interface --- lives outside the package, and `pyproject.toml` ships
`packages = ["pipeline"]`, so it is in neither the wheel nor the scaffolded
project:

    $ uv tool install . && pipeline init /tmp/demo && find /tmp/demo -name 'SKILL.md'
    initialised /tmp/demo/.project -- edit ... for this project's commands
    (nothing)

A session working in that project has a queue and no description of the
protocol, so it hand-writes frontmatter the dispatcher escalates, or fills
`## Plan` and skips plan-validation --- both of which the skill exists to
prevent.

Expected: after `pipeline init <project>`, the project carries the same
file-ticket skill this repo has, and `init` says where it put it. An existing
file is never overwritten --- a project that has customised it keeps its
version. The packaged copy has to be the source of truth for both, or this
repo's own copy and the shipped one drift the way `CLAUDE.md` warns about.

Suggestion only, planning decides: `pipeline/templates/` and
`pipeline/stages/` are already inside the package for exactly this reason
(`Path(__file__).parent`, so `uv tool install .` does not lose them). The
skill is Claude-specific and stage prompts must stay harness-neutral, but
this one is read by a human's session, not by a stage, so the rule may not
apply --- say which, either way.

Not in scope: any skill for editing `.project/pipeline.toml`. The commented
template covers it.

**Planning (2026-08-24): plan written**, 12 steps over 8 files, no questions
for the human. The skill moves to `pipeline/templates/skills/file-ticket/SKILL.md`,
where `config.PKG` finds it after `uv tool install .`. This repo's
`.claude/skills/file-ticket/SKILL.md` becomes a relative symlink to it, so one
file serves both and drift is impossible rather than merely detectable.
`cmd_init` (`pipeline/cli/main.py:38`) copies it into `<project>/.claude/skills/file-ticket/SKILL.md`,
keeps an existing file, and prints the path either way -- the same shape it
already uses for `.project/pipeline.toml`. The harness-neutrality rule does not
apply: it governs stage prompts the dispatcher composes into a spawn, and this
file is never composed into one. No decision record constrains this change.

**Planning (2026-08-24, second pass): the plan is unchanged; the `expect:` line
in `## Reproduction` is fixed.** The plan-validation gate failed on one finding
only, and it was not about the plan: the `expect:` value held a literal `\n` and
named two lines of pytest output, which `gate()` compares by substring against
raw output whose assertion lines each start `E       `. No run could match it.
The new value is one contiguous line of that failure, checked against a real run
of the test.

**Plan-validation (2026-08-24): PASS on all eight items, no finding.** The Tier A
gate passed, and the judgement pass raised nothing. The root cause is two facts
at once -- `cmd_init` has no skill step, and the skill sits outside
`packages = ["pipeline"]` -- and the plan fixes both. No decision record binds.
Every step traces to a criterion, every anchor the plan cites holds
(`pipeline/core/config.py:23`, `pipeline/cli/main.py:15`,
`tests/test_stages.py:184`, `tests/test_cli.py:296`, `tests/helpers.py:6`), and
the riskiest step, the symlink, has its fallback written in `## Decisions`.
One note for implementing, outside my scope: step 9 updates the
`pipeline/templates/` row at `CLAUDE.md:62` and nothing updates the same
description at `README.md:368`.

## Reproduction

`tests/test_cli.py::test_init_installs_the_file_ticket_skill`, committed on
`ticket/056` (6970aa8).

Command: `uv run --group dev pytest -q tests/test_cli.py::test_init_installs_the_file_ticket_skill`

Output:
```
AssertionError: expected /tmp/tmp8t7jisof/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
assert False
 +  where False = is_file()
 +    where is_file = PosixPath('/tmp/tmp8t7jisof/.claude/skills/file-ticket/SKILL.md').is_file
```

expect: .claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []

Planning rewrote the `expect:` line on 2026-08-24. The previous value,
`assert False\n +  where False = is_file()`, carried a literal `\n` and named
two output lines. `gate()` tests `expect not in out` against raw pytest output,
where each of those lines starts `E       `, so no run could ever match it. The
value above is one contiguous run of the same failure and drops the per-run
temp directory. Verified against a real run on 2026-08-24.

Confirmed directly too: `uv run python` a throwaway script that calls
`pipeline --project <tmp> init` then `list(<tmp>.rglob('SKILL.md'))` returns
`[]`. `cmd_init` (`pipeline/cli/main.py:38`) only creates
`.project/tickets/`, `.project/decisions/` and writes `pipeline.toml` --
no skill copy step exists anywhere in the CLI.

## Digest

Files touched: `pipeline/cli/main.py` (`cmd_init`, line 38), `pipeline/core/config.py` (the `PKG`-relative data paths, lines 19-23), `pipeline/templates/skills/file-ticket/SKILL.md` (new -- the moved skill), `.claude/skills/file-ticket/SKILL.md` (becomes a symlink), `tests/test_cli.py`, `tests/test_stages.py`, `CLAUDE.md`, `README.md`.

Key functions: `cmd_init` (`pipeline/cli/main.py:38`) creates `tickets_dir(project)` and `.project/decisions`, writes `pipeline.toml` from `CONFIG_TEMPLATE` only `if not cfg.exists()`, prints one `initialised ...` line, then runs the optional `--private` block. The skill install copies that shape. `config.PKG = Path(__file__).resolve().parent.parent`, and `TICKET_TEMPLATE`/`CONFIG_TEMPLATE` hang off it; `SKILL_TEMPLATE` joins them.

Entry points: `pipeline init <dir>` (CLI), and `tests/test_cli.py::cli()`, which runs `python -m pipeline --project <d> <args>` in a real subprocess.

Gotchas:
1. `pyproject.toml:23` ships `packages = ["pipeline"]`, so anything outside `pipeline/` is absent from the wheel. `pipeline/templates/` has no subdirectory today; hatchling includes the package tree recursively, and step 11 verifies that on a real wheel instead of assuming it.
2. `tests/test_stages.py::test_data_files_live_inside_the_package_so_they_survive_install` already asserts every `config` data path sits under `PKG`, and its docstring says it cannot see inside the wheel. Extend that list; do not write a second test for the same rule.
3. `tests/test_cli.py` sandboxes `XDG_STATE_HOME` inside its `cli()` helper. Call `cli()`, never a bare `subprocess.run`.
4. The symlink is relative (`../../../pipeline/...`), so it resolves inside a worktree as well as in the main checkout.
5. The skill's own body says `uv tool install --editable . --force     # from the repo root`. Once the file ships into other projects, `.` names the wrong directory there.
6. The Tier A gate compares `expect:` to raw pytest output with `expect not in out` (`pipeline/core/gate.py:226`), and pytest prefixes every assertion line with `E       `. An `expect:` value spanning two lines, or holding a literal `\n`, fails the gate however red the test is. That is why the plan-validation gate failed on 2026-08-24; the plan itself drew no finding and is unchanged.

## Decisions checked

None relevant. Grep terms over `/home/chezzijr/proj/agent-pipeline/.project/decisions/`: `skill`, `pipeline init`, `scaffold`, `template`, `packag`, `harness-neutral`, `uv tool install`, `inside the package`, `__file__`.

Read in full, none binding: DEC-031, DEC-026, DEC-047 and DEC-053 each list `.claude/skills/file-ticket/SKILL.md` among their files, but each records a state-machine decision and none says where that file lives. DEC-036 says "stage files ship inside the package"; this plan follows that rule for a template rather than a stage. DEC-032 uses `module.__file__` for the source watcher and does not touch data paths. No record governs `cmd_init`.

The binding rule sits in `CLAUDE.md`, not in a decision record: data directories live inside the package because they are found via `Path(__file__).parent`. This plan complies, so it needs no `supersedes:`.

## Plan

1. Move the skill into the package: run `mkdir -p pipeline/templates/skills/file-ticket`, then `git mv .claude/skills/file-ticket/SKILL.md pipeline/templates/skills/file-ticket/SKILL.md`, so the packaged copy holds the only copy of the file's bytes.
2. Point this repo's own copy at it: run `ln -s ../../../pipeline/templates/skills/file-ticket/SKILL.md .claude/skills/file-ticket/SKILL.md`, then `git add .claude/skills/file-ticket/SKILL.md`, and confirm `git ls-files -s .claude/skills/file-ticket/SKILL.md` prints mode `120000`.
3. In `pipeline/templates/skills/file-ticket/SKILL.md`, change the install line `uv tool install --editable . --force     # from the repo root` to `uv tool install --editable . --force     # from the agent-pipeline checkout`, because `.` names the scaffolded project once the file ships; commit steps 1-3 together.
4. Add `SKILL_TEMPLATE = PKG / "templates" / "skills" / "file-ticket" / "SKILL.md"` below `CONFIG_TEMPLATE` in `pipeline/core/config.py` (line 23), and name the skill in that module docstring's list of what sits inside the package.
5. In `tests/test_stages.py`, add `C.SKILL_TEMPLATE` to the tuple in `test_data_files_live_inside_the_package_so_they_survive_install` (line 184) and add `test_the_repo_skill_is_the_packaged_file`: it does `from helpers import ROOT`, builds `repo = ROOT / ".claude" / "skills" / "file-ticket" / "SKILL.md"`, asserts `repo.is_file()`, and asserts `repo.resolve() == C.SKILL_TEMPLATE.resolve()` with the message `f"{repo} is a copy, not the packaged file -- the two will drift"`; run `uv run --group dev pytest -q tests/test_stages.py` and expect `passed`.
6. Add the preserve-and-print test to `tests/test_cli.py` beside `test_init_installs_the_file_ticket_skill` (line 296): `test_init_keeps_a_customised_file_ticket_skill` runs `cli(d, "init")`, asserts `str(skill)` appears in `r.stdout`, writes `"# ours\n"` into the skill, runs `cli(d, "init")` a second time, asserts `skill.read_text() == "# ours\n"` with the message `"re-init overwrote a customised skill"`, and asserts `"kept" in r.stdout`; run `uv run --group dev pytest -q tests/test_cli.py -k file_ticket_skill` and expect `2 failed`.
7. Install the skill in `cmd_init` (`pipeline/cli/main.py:38`): import `SKILL_TEMPLATE` from `pipeline.core.config` (line 15); after the `initialised ...` print and before the `--private` block, set `skill = project / ".claude" / "skills" / "file-ticket" / "SKILL.md"`; when `skill.exists()`, print `f"  file-ticket skill already at {skill} -- kept"`; otherwise call `skill.parent.mkdir(parents=True, exist_ok=True)`, then `skill.write_text(SKILL_TEMPLATE.read_text())`, then print `f"  installed the file-ticket skill at {skill}"`.
8. Run `uv run --group dev pytest -q tests/test_cli.py -k file_ticket_skill`, expect `2 passed`, and commit `pipeline/cli/main.py`, `pipeline/core/config.py`, `tests/test_cli.py` and `tests/test_stages.py`.
9. Update `CLAUDE.md`: change the "Where things live" row for `pipeline/templates/` to `the ticket schema, the per-project config example, and the file-ticket skill init installs`, and in the interface paragraph (line 251) state that `.claude/skills/file-ticket/SKILL.md` is a symlink to `pipeline/templates/skills/file-ticket/SKILL.md` and that `pipeline init` copies that file into every project it scaffolds.
10. Update `README.md`: in `## Use`, directly above the paragraph that begins "Once `.project/` is committed", add "`init` also installs `.claude/skills/file-ticket/SKILL.md` -- the protocol a session reads before filing a ticket -- and prints where it put it. An existing file is kept, so a project that customised it keeps its version."
11. Verify the wheel carries the file: run `uv build --wheel`, then `unzip -l dist/*.whl | grep SKILL.md`, and expect one line ending `pipeline/templates/skills/file-ticket/SKILL.md`; run `rm -rf dist` afterwards, so the build output stays out of the ticket's diff.
12. Run `uv run --group dev pytest -q`, expect every test to pass, and commit `CLAUDE.md` and `README.md`.

## Acceptance criteria

1. `tests/test_cli.py::test_init_installs_the_file_ticket_skill` passes: after `pipeline init <tmp>`, `<tmp>/.claude/skills/file-ticket/SKILL.md` is a file.
2. `tests/test_cli.py::test_init_keeps_a_customised_file_ticket_skill` passes: a second `init` leaves a customised skill file byte-identical, and `init` prints the skill's path on both runs.
3. `tests/test_stages.py::test_the_repo_skill_is_the_packaged_file` passes: `.claude/skills/file-ticket/SKILL.md` resolves to `pipeline/templates/skills/file-ticket/SKILL.md`, so this repo holds one copy of the skill, not two.
4. `tests/test_stages.py::test_data_files_live_inside_the_package_so_they_survive_install` passes with `C.SKILL_TEMPLATE` in its list, so the skill sits under `config.PKG` and survives `uv tool install .`.
5. `unzip -l dist/*.whl | grep SKILL.md` prints one line for
   `pipeline/templates/skills/file-ticket/SKILL.md` -- the wheel check the test in criterion 4 cannot make.
6. `uv run --group dev pytest -q` passes, with no existing test removed or weakened.

## Decisions

**`pipeline/templates/skills/file-ticket/SKILL.md` is the only copy of the skill; this repo's `.claude/skills/file-ticket/SKILL.md` is a symlink to it.** Two real files drift, and `CLAUDE.md` warns that a skill describing a pipeline that no longer exists sends every future ticket in wrong. A symlink makes drift impossible instead of detectable. `tests/test_stages.py::test_the_repo_skill_is_the_packaged_file` fails if someone replaces the link with a copy. If a checkout ever needs a real file there (a git without symlink support), replace the link **and** that test with a byte-equality assertion -- do not leave a copy with no check on it.

**The skill lives in `pipeline/templates/`, not `pipeline/stages/`, and the harness-neutrality rule does not apply to it.** That rule governs stage prompts, which the dispatcher composes into a spawn. This file is never composed into anything: a human's Claude Code session reads it before the ticket exists, so being Claude-specific is what it is for. Keeping it out of `pipeline/stages/` is what keeps the rule true -- no stage prompt gained a Claude-specific dependency.

**`init` never overwrites an existing skill file.** It mirrors `.project/pipeline.toml`: a project that customised its copy keeps it, and `init` stays idempotent, which `README.md` documents and `pipeline init . --private` relies on. The cost is that a project pinned to an old skill does not pick up a new one; re-installing means deleting the file first, deliberately.

## Rollback

Revert the commits on `ticket/056`. The move is the only step that looks irreversible: `git revert` restores `.claude/skills/file-ticket/SKILL.md` as a real file and deletes `pipeline/templates/skills/file-ticket/SKILL.md`, which is the pre-ticket state exactly. Nothing reads `SKILL_TEMPLATE` except `cmd_init`, and a scaffolded project keeps the skill file it already received -- reverting this ticket does not reach into an initialised project.

## Thread

### 2026-08-24 14:44:07Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 · triage · investigation

Reproduced. `cmd_init` (`pipeline/cli/main.py:38`) creates
`.project/tickets/`, `.project/decisions/` and `pipeline.toml` only; no code
path copies `.claude/skills/file-ticket/SKILL.md` into the scaffolded
project. Confirmed with a real `pipeline --project <tmp> init` run: `find
<tmp> -name SKILL.md` returns nothing.

Not a chore: the ticket leaves open where the packaged skill should live so
`uv tool install .` keeps it (`pyproject.toml:23` ships `packages =
["pipeline"]`, so anything outside `pipeline/` is lost), whether an existing
project file must be preserved on re-init, and what `init` should print.
These are design choices, not a few-line fix -- send to planning.

Failing test: `tests/test_cli.py::test_init_installs_the_file_ticket_skill`,
committed on `ticket/056` (6970aa8).

### 2026-08-24 14:45:24Z · triage · session · session=7ef3e42f-49f3-4d55-9c22-c98bd9e3a48c

`triage` ran as session `7ef3e42f-49f3-4d55-9c22-c98bd9e3a48c`
- replay: `claude --resume 7ef3e42f-49f3-4d55-9c22-c98bd9e3a48c`
- log: `.project/logs/TICKET-056-triage-7ef3e42f.log`

### 2026-08-24 14:45:24Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced init not scaffolding the file-ticket skill; failing test committed on ticket/056

### 2026-08-24 · planning · plan

Plan written: 12 steps, 8 files. Scope is one subsystem -- `cmd_init` and where
the skill file lives -- so nothing is deferred.

Three design questions the triage entry left open, all settled by reading the
code rather than by asking:
1. The packaged skill goes to `pipeline/templates/skills/file-ticket/SKILL.md`,
   because `config.PKG` finds it there after `uv tool install .`.
2. This repo's `.claude/skills/file-ticket/SKILL.md` becomes a symlink to that
   file, so the two cannot drift.
3. `init` keeps an existing skill file and prints one line either way, mirroring
   how it already treats `.project/pipeline.toml`.

The ticket asked whether the harness-neutrality rule blocks a Claude-specific
file in the package. It does not: that rule governs stage prompts the dispatcher
composes into a spawn, and this file is never composed into one. `## Decisions`
records that verdict.

Noted outside this ticket's scope, not fixed: `tests/test_stages.py::test_data_files_live_inside_the_package_so_they_survive_install`
cannot see inside the built wheel, which its own docstring states. Step 11 runs
`uv build --wheel` once by hand to cover this ticket's file; nothing tests it
on every run.

### 2026-08-24 14:50:08Z · planning · session · session=d1137bb4-c81b-4ff0-a301-6b7ccb926866

`planning` ran as session `d1137bb4-c81b-4ff0-a301-6b7ccb926866`
- replay: `claude --resume d1137bb4-c81b-4ff0-a301-6b7ccb926866`
- log: `.project/logs/TICKET-056-planning-d1137bb4.log`

### 2026-08-24 14:50:08Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned: skill moves to pipeline/templates/skills/file-ticket/SKILL.md, repo copy becomes a symlink, cmd_init installs it without overwriting

### 2026-08-24 14:50:22Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails, but its output does not mention the expected string 'assert False\\n +  where False = is_file()'
```
 it is what a session reads before filing a ticket into this
        pipeline. `init` scaffolds `.project/` but never copies it, so a project
        it creates has a queue and no description of the protocol."""
        d = Path(tempfile.mkdtemp())
        r = cli(d, "init")
        assert r.returncode == 0, r.stderr
        skill = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"
>       assert skill.is_file(), (
            f"expected {skill} to exist after `pipeline init`, "
            f"found: {list(d.rglob('SKILL.md'))}"
        )
E       AssertionError: expected /tmp/tmp4fwprvtq/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmp4fwprvtq/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```

### 2026-08-24 14:50:22Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails, but its output does not mention the expected string 'assert False\\n +  where False = is_file()'
*-- identical output, already quoted in the `## Thread` entry `2026-08-24 14:50:22Z · plan-validation · gate · verdict=FAIL` --*

### 2026-08-24 · planning · plan

The gate's one finding was the `expect:` line, not the plan. I fixed that line
and left the 12 steps, the 8 files and `## Decisions` as they were.

The old value was `assert False\n +  where False = is_file()`. It holds a
literal `\n` and names two lines of pytest output. `gate()`
(`pipeline/core/gate.py:226`) runs `expect not in out` against raw output, and
pytest prefixes each assertion line with `E       `, so no run could match it.
The new value is one contiguous line of the same failure:

    .claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []

I re-ran the test and checked both values against the captured output in
Python: the new one prints `MATCH True`, the old one `OLD MATCH False`. The
test still fails as required:

```
E       AssertionError: expected /tmp/tmpgyql37k8/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
1 failed in 0.09s
```

I re-checked every anchor the plan cites: `CONFIG_TEMPLATE` at
`pipeline/core/config.py:23`, the config import at `pipeline/cli/main.py:15`,
the tuple at `tests/test_stages.py:184`, the test at `tests/test_cli.py:296`,
`ROOT` at `tests/helpers.py:6`, `packages = ["pipeline"]` at `pyproject.toml:23`,
the `pipeline/templates/` row at `CLAUDE.md:62`, and `README.md:78`. All hold.
`## Digest` gotcha 6 records the gate rule so this does not recur.

### 2026-08-24 14:53:24Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails as required
```
 it is what a session reads before filing a ticket into this
        pipeline. `init` scaffolds `.project/` but never copies it, so a project
        it creates has a queue and no description of the protocol."""
        d = Path(tempfile.mkdtemp())
        r = cli(d, "init")
        assert r.returncode == 0, r.stderr
        skill = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"
>       assert skill.is_file(), (
            f"expected {skill} to exist after `pipeline init`, "
            f"found: {list(d.rglob('SKILL.md'))}"
        )
E       AssertionError: expected /tmp/tmp2r1q0sdi/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmp2r1q0sdi/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails on base `main` too -- the bug is not already fixed upstream
```
    )
E       AssertionError: expected /tmp/tmp57_bm_84/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmp57_bm_84/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.20s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ldvz43k_/base
      Built pipeline @ file:///tmp/pipeline-base-ldvz43k_/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 14:53:40Z · planning · session · session=f0aa2032-165c-4f69-9dcf-2fba6667abf9

`planning` ran as session `f0aa2032-165c-4f69-9dcf-2fba6667abf9`
- replay: `claude --resume f0aa2032-165c-4f69-9dcf-2fba6667abf9`
- log: `.project/logs/TICKET-056-planning-f0aa2032.log`

### 2026-08-24 14:53:40Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned: plan unchanged, `## Reproduction` expect: rewritten to a one-line string the real pytest output contains; local gate() now returns PASSED: True

### 2026-08-24 14:53:54Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails as required
```
 it is what a session reads before filing a ticket into this
        pipeline. `init` scaffolds `.project/` but never copies it, so a project
        it creates has a queue and no description of the protocol."""
        d = Path(tempfile.mkdtemp())
        r = cli(d, "init")
        assert r.returncode == 0, r.stderr
        skill = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"
>       assert skill.is_file(), (
            f"expected {skill} to exist after `pipeline init`, "
            f"found: {list(d.rglob('SKILL.md'))}"
        )
E       AssertionError: expected /tmp/tmpl48rjzkt/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmpl48rjzkt/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails on base `main` too -- the bug is not already fixed upstream
```
    )
E       AssertionError: expected /tmp/tmps3lmunph/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmps3lmunph/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-f69_6ixq/base
      Built pipeline @ file:///tmp/pipeline-base-f69_6ixq/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 · plan-validation · judgement

**PASS on all eight items.** I re-read every anchor the plan cites.

1. Root cause: `cmd_init` (`pipeline/cli/main.py:38-62`) creates
   `.project/tickets/`, `.project/decisions` and `pipeline.toml`, and the skill
   sits at the repo root, outside `packages = ["pipeline"]` (`pyproject.toml:23`).
   The plan fixes both halves -- the file moves under `PKG`, and `cmd_init`
   copies it. It is not a test-shaped patch.
2. Decisions: no record binds. `CLAUDE.md`'s `Path(__file__).parent` rule binds,
   and the plan complies, so no `supersedes:` is owed.
3. Scope: 12 steps, 8 files, `class: feature`. Every step traces to a criterion;
   steps 9-10 trace to `CLAUDE.md:251`, which makes the skill interface.
4. Criteria are falsifiable. Criteria 1, 2 and 3 each fail on a real wrong
   implementation: no copy, an overwrite, a copy where the symlink belongs.
5. No research left: `config.py:23`, `main.py:15`, `test_stages.py:184`,
   `test_cli.py:296` and `helpers.py:6` all hold as the plan writes them.
6. Riskiest step is 2, the symlink. `## Decisions` states the fallback.
7. Regression surface: nothing globs `pipeline/templates/`, and no test asserts
   `init`'s stdout shape.
   `tests/test_cli.py::test_init_honours_project_like_every_other_command`
   covers `init`.
8. Blast radius matches `feature`.

Out of my scope, for implementing: step 9 updates the `pipeline/templates/`
row at `CLAUDE.md:62`, and nothing updates the same description at
`README.md:368`. I checked step 11's `rm -rf dist` against the guard --
`dist` is not `HOME_ISH`, so the step runs.

### 2026-08-24 14:56:20Z · plan-validation · session · session=fecb0e70-0f06-4984-98b7-53e83e1446fe

`plan-validation` ran as session `fecb0e70-0f06-4984-98b7-53e83e1446fe`
- replay: `claude --resume fecb0e70-0f06-4984-98b7-53e83e1446fe`
- log: `.project/logs/TICKET-056-plan-validation-fecb0e70.log`

### 2026-08-24 14:56:20Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan-validation: PASS on all eight items -- root cause covers both halves, every anchor holds, symlink step has a fallback

### 2026-08-24 15:07:03Z · human · approval · by=chezzijr

**approved by chezzijr**
