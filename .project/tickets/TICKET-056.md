---
id: TICKET-056
stage: done
class: feature
branch: ticket/056
test_file: tests/test_cli.py::test_init_installs_the_file_ticket_skill
files_declared:
- .claude/skills/file-ticket/SKILL.md
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/core/config.py
- pipeline/templates/skills/file-ticket/SKILL.md
- tests/test_cli.py
- tests/test_stages.py
counters:
  plan_validation_attempts: 2
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 13
  plan_files: 8
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 0e00ef55-31c8-44cf-b934-32207bc70bd0
  log: .project/logs/TICKET-056-review-0e00ef55.log
approved_by: chezzijr
approved_at: '2026-08-24T16:27:25.937940+00:00'
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

Not in scope: any skill for editing `.project/pipeline.toml`. The commented
template covers it.

**Planning (2026-08-24, fourth pass): 13 steps over 8 files, no questions.** The
gate failed one line -- "acceptance criterion names no test", against criterion
6, which checked the `README.md` edit with `grep` alone. Step 9 now adds
`tests/test_stages.py::test_the_docs_name_the_skill_init_installs`, and
criterion 6 names it. Nothing else changed: steps 9-12 of the approved plan are
now steps 10-13.

The skill moves to `pipeline/templates/skills/file-ticket/SKILL.md`, where
`config.PKG` finds it after `uv tool install .`. This repo's
`.claude/skills/file-ticket/SKILL.md` becomes a relative symlink to it, so one
file serves both, and Claude Code 2.1.241's loader `stat`s a skill path, so it
still loads (`## Digest` gotcha 7). `cmd_init` (`pipeline/cli/main.py:38`)
copies the packaged file into `<project>/.claude/skills/file-ticket/SKILL.md`,
keeps an existing file, and prints the path either way -- the same shape it
already uses for `.project/pipeline.toml`. Steps 10 and 11 update the
`pipeline/templates/` row in `CLAUDE.md:62` and in `README.md:417`. No decision
record constrains this change.

**Plan-validation (2026-08-24): pass.** All eight judgment items pass, scored
against the code; the reasoning is in `## Thread`. The plan fixes the root
cause, not the test: `cmd_init` gains the copy step and the skill moves inside
`packages = ["pipeline"]`, so the wheel carries it. Nothing under `pipeline/`
reads `.claude/skills`, so the move breaks no code. One non-blocking note for
`implementing`: step 9's `CLAUDE.md` row check can be satisfied by step 10's
interface sentence, leaving the table row at `CLAUDE.md:62` unchanged; filter
to lines starting with `|`. The plan's `CLAUDE.md:250` is line 251.

**Implementing (2026-08-24): all 13 plan steps done, all 7 acceptance criteria
pass.** Three commits on `ticket/056`: `a11abed` (skill moved to
`pipeline/templates/skills/file-ticket/SKILL.md`, `.claude/skills/file-ticket/SKILL.md`
now a relative symlink), `569573d` (`config.SKILL_TEMPLATE` added, `cmd_init`
installs the skill and keeps a customised one, tests for both added and run
RED before GREEN), `463261b` (`CLAUDE.md` and `README.md` updated, docs test
added). `uv build --wheel` confirmed
`pipeline/templates/skills/file-ticket/SKILL.md` in the wheel; `dist/` removed
after. Full suite: `uv run --group dev pytest -q` -> `311 passed`. No test
removed or weakened.

**Review (2026-08-24): pass, no blocking findings.** Reviewed the whole branch
delta, `43a986d..463261b`, 8 files, against the 7 acceptance criteria and the
13 plan steps. Re-ran the suite: `311 passed`. The skill's bytes moved
unchanged apart from plan step 3's install-line comment; the repo copy is mode
`120000`; `grep -c file-ticket README.md` prints `2`. Three non-blocking
findings are in `## Thread`, the first worth a one-line fix in a later ticket:
`test_the_docs_name_the_skill_init_installs` matches `CLAUDE.md:261` as well as
the row at `CLAUDE.md:62`, so reverting the row alone leaves it green. Criterion
5 is the one I could not re-run -- the guard blocks `uv build` for a read-only
stage -- so the thread records what supports `implementing`'s wheel line.

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
1. `pyproject.toml:23` ships `packages = ["pipeline"]`, so anything outside `pipeline/` is absent from the wheel. `pipeline/templates/` has no subdirectory today; hatchling includes the package tree recursively, and step 12 verifies that on a real wheel instead of assuming it.
2. `tests/test_stages.py::test_data_files_live_inside_the_package_so_they_survive_install` (line 178) already asserts every `config` data path sits under `PKG`, and its docstring says it cannot see inside the wheel. Extend that list; do not write a second test for the same rule.
3. `tests/test_cli.py` sandboxes `XDG_STATE_HOME` inside its `cli()` helper (line 22). Call `cli()`, never a bare `subprocess.run`.
4. The symlink is relative (`../../../pipeline/...`), so it resolves inside a worktree as well as in the main checkout. `tests/test_stages.py` does not import `ROOT` today; step 5's test adds `from helpers import ROOT` inside the function, because `C.PKG.parent` is `site-packages` after an install and would look for `.claude` there.
5. The skill's own body says `uv tool install --editable . --force     # from the repo root` (line 30). Once the file ships into other projects, `.` names the wrong directory there.
6. The Tier A gate compares `expect:` to raw pytest output with `expect not in out` (`pipeline/core/gate.py:226`), and pytest prefixes every assertion line with `E       `. An `expect:` value spanning two lines, or holding a literal `\n`, fails the gate however red the test is. The value in `## Reproduction` is one contiguous line for that reason.
7. Claude Code loads a symlinked `SKILL.md`. Verified against the installed binary, `/home/chezzijr/.local/share/claude/versions/2.1.241`, on 2026-08-24. Its project-skills loader (the function whose plugin filter reads `t==="projectSettings"&&e===ph.join(Bn(),".claude","skills")`) does three things in order: it keeps a directory entry that `isDirectory()||isSymbolicLink()`, then `let p=null;try{p=await o.stat(d)}catch{}` on `<dir>/SKILL.md`, then `if(p!==null&&!p.isFile())return E("[skills] skipping "+d+": not a regular file",{level:"warn"}),s="skill_load_read_failed",null;`. `stat` follows a symlink, so a link to a regular file passes. The same binary calls `lstat` on its Codex-import path and rejects what it finds -- `SKILL.md is a symlink -- copy the skill manually` -- so `stat` here is a deliberate choice, not an oversight. The loader also skips a `SKILL.md` over its byte limit; the file is 8470 bytes.
8. `tree_snapshot()` (`pipeline/core/worktree.py:143`) is `git rev-parse HEAD` plus `git status --porcelain`, so the symlink costs a read-only stage's baseline nothing: git reports mode `120000` like any other tracked content.
9. Two docs tests already read the rule files from `C.PKG.parent`: `test_the_docs_name_the_dependencies_and_the_targets_the_code_has` (`tests/test_stages.py:191`) and `test_the_fenced_list_matches_the_rule_file` (line 238). Step 9's test follows them and uses `C.PKG.parent`, not `helpers.ROOT`, which step 5's test needs only because it compares against `C.SKILL_TEMPLATE`.

## Decisions checked

None relevant. Grep terms over `/home/chezzijr/proj/agent-pipeline/.project/decisions/`: `skill`, `symlink`, `pipeline init`, `scaffold`, `template`, `packag`, `harness-neutral`, `uv tool install`, `inside the package`, `__file__`.

Read in full, none binding: DEC-031, DEC-026, DEC-047 and DEC-053 each list `.claude/skills/file-ticket/SKILL.md` among their files, but each records a state-machine decision and none says where that file lives. DEC-036 says "stage files ship inside the package"; this plan follows that rule for a template rather than a stage. DEC-032 uses `module.__file__` for the source watcher and does not touch data paths. No record governs `cmd_init`.

Two records name symlinks and neither reaches this change. DEC-052 resolves a file tool's path with `realpath` before the containment test, so the new symlink resolves inside the worktree and the guard allows a stage to write it. DEC-018 makes `active_decisions()` skip a symlinked `DEC-*.md`; that rule is about `.project/decisions/`, not `.claude/skills/`. Neither carries a `superseded-by:` line.

The binding rule sits in `CLAUDE.md`, not in a decision record: data directories live inside the package because they are found via `Path(__file__).parent`. This plan complies, so it needs no `supersedes:`.

## Plan

1. Move the skill into the package: run `mkdir -p pipeline/templates/skills/file-ticket`, then `git mv .claude/skills/file-ticket/SKILL.md pipeline/templates/skills/file-ticket/SKILL.md`, so the packaged copy holds the only copy of the file's bytes.
2. Point this repo's own copy at it: run `ln -s ../../../pipeline/templates/skills/file-ticket/SKILL.md .claude/skills/file-ticket/SKILL.md`, then `git add .claude/skills/file-ticket/SKILL.md`, and confirm `git ls-files -s .claude/skills/file-ticket/SKILL.md` prints mode `120000`.
3. In `pipeline/templates/skills/file-ticket/SKILL.md`, change the install line `uv tool install --editable . --force     # from the repo root` (line 30) to `uv tool install --editable . --force     # from the agent-pipeline checkout`, because `.` names the scaffolded project once the file ships; commit steps 1-3 together.
4. Add `SKILL_TEMPLATE = PKG / "templates" / "skills" / "file-ticket" / "SKILL.md"` below `CONFIG_TEMPLATE` in `pipeline/core/config.py` (line 23), and name the skill in that module docstring's list of what sits inside the package.
5. In `tests/test_stages.py`, add `C.SKILL_TEMPLATE` to the tuple in `test_data_files_live_inside_the_package_so_they_survive_install` (line 178) and add `test_the_repo_skill_is_the_packaged_file`, which asserts the four conditions Claude Code's skill loader applies (`## Digest` gotcha 7 quotes it); run `uv run --group dev pytest -q tests/test_stages.py` and expect `passed`. The test body is:

        def test_the_repo_skill_is_the_packaged_file():
            """One copy of the skill's bytes, and the harness still loads it.

            `.claude/skills/file-ticket/SKILL.md` is a symlink to the packaged
            copy, so the two cannot drift. Claude Code 2.1.241 loads a symlinked
            SKILL.md: its project-skills loader `stat`s the path -- not `lstat`,
            which it uses elsewhere -- and skips the skill only when the target
            is not a regular file, or is over its byte limit. These asserts are
            that loader's conditions. Replacing the link with a copy fails here.
            """
            from helpers import ROOT
            repo = ROOT / ".claude" / "skills" / "file-ticket" / "SKILL.md"
            assert repo.is_symlink(), \
                f"{repo} is a copy, not a symlink -- the two copies will drift"
            assert repo.is_file(), \
                f"{repo} is a broken symlink -- the skill would not load"
            assert repo.resolve() == C.SKILL_TEMPLATE.resolve(), \
                f"{repo} resolves to {repo.resolve()}, not to {C.SKILL_TEMPLATE}"
            assert repo.stat().st_size < 128 * 1024, \
                f"{repo} is {repo.stat().st_size} bytes -- too large to load"

6. Add the preserve-and-print test to `tests/test_cli.py` beside `test_init_installs_the_file_ticket_skill` (line 296): `test_init_keeps_a_customised_file_ticket_skill` runs `cli(d, "init")`, asserts `str(skill)` appears in `r.stdout`, writes `"# ours\n"` into the skill, runs `cli(d, "init")` a second time, asserts `skill.read_text() == "# ours\n"` with the message `"re-init overwrote a customised skill"`, and asserts `"kept" in r.stdout`; run `uv run --group dev pytest -q tests/test_cli.py -k file_ticket_skill` and expect `2 failed`.
7. Install the skill in `cmd_init` (`pipeline/cli/main.py:38`): import `SKILL_TEMPLATE` from `pipeline.core.config` (line 15); after the `initialised ...` print and before the `--private` block, set `skill = project / ".claude" / "skills" / "file-ticket" / "SKILL.md"`; when `skill.exists()`, print `f"  file-ticket skill already at {skill} -- kept"`; otherwise call `skill.parent.mkdir(parents=True, exist_ok=True)`, then `skill.write_text(SKILL_TEMPLATE.read_text())`, then print `f"  installed the file-ticket skill at {skill}"`.
8. Run `uv run --group dev pytest -q tests/test_cli.py -k file_ticket_skill`, expect `2 passed`, and commit `pipeline/cli/main.py`, `pipeline/core/config.py`, `tests/test_cli.py` and `tests/test_stages.py`.
9. Add `test_the_docs_name_the_skill_init_installs` to `tests/test_stages.py`, beside `test_the_docs_name_the_dependencies_and_the_targets_the_code_has` (line 191); run `uv run --group dev pytest -q tests/test_stages.py -k skill_init_installs` and expect `1 failed`. The test body is:

        def test_the_docs_name_the_skill_init_installs():
            """`init` installs the file-ticket skill, so both rule files say so.

            `CLAUDE.md`'s "Where things live" row for `pipeline/templates/` and
            the README's copy of that row describe one directory. A reader who
            finds only the schema and the config example there does not learn
            that the skill ships too, and `## Use` is where a human reads what
            `init` writes.
            """
            root = C.PKG.parent
            for name in ("CLAUDE.md", "README.md"):
                rows = [ln for ln in (root / name).read_text().splitlines()
                        if "pipeline/templates/" in ln and "file-ticket" in ln]
                assert rows, \
                    f"{name}: the pipeline/templates/ row does not name the file-ticket skill"
            readme = (root / "README.md").read_text()
            assert "installs `.claude/skills/file-ticket/SKILL.md`" in readme, \
                "README.md does not say `init` installs the file-ticket skill"

10. Update `CLAUDE.md`: change the "Where things live" row for `pipeline/templates/` (line 62) to `the ticket schema, the per-project config example, and the file-ticket skill init installs`, and in the interface paragraph (line 250) state that `.claude/skills/file-ticket/SKILL.md` is a symlink to `pipeline/templates/skills/file-ticket/SKILL.md` and that `pipeline init` copies that file into every project it scaffolds.
11. Update `README.md` twice: change the `pipeline/templates/` row (line 417, moved by `e13dfed` -- grep for it rather than trusting the number) to `the ticket schema, the project config example, and the file-ticket skill`, and in `## Use`, directly above the paragraph that begins "Once `.project/` is committed" (line 78), add "`init` also installs `.claude/skills/file-ticket/SKILL.md` -- the protocol a session reads before filing a ticket -- and prints where it put it. An existing file is kept, so a project that customised it keeps its version."
12. Verify the wheel carries the file: run `uv build --wheel`, then `unzip -l dist/*.whl | grep SKILL.md`, and expect one line ending `pipeline/templates/skills/file-ticket/SKILL.md`; run `rm -rf dist` afterwards, so the build output stays out of the ticket's diff.
13. Run `uv run --group dev pytest -q`, expect every test to pass -- `test_the_docs_name_the_skill_init_installs` among them -- and commit `CLAUDE.md`, `README.md` and `tests/test_stages.py`.

## Acceptance criteria

1. `tests/test_cli.py::test_init_installs_the_file_ticket_skill` passes: after `pipeline init <tmp>`, `<tmp>/.claude/skills/file-ticket/SKILL.md` is a file.
2. `tests/test_cli.py::test_init_keeps_a_customised_file_ticket_skill` passes: a second `init` leaves a customised skill file byte-identical, and `init` prints the skill's path on both runs.
3. `tests/test_stages.py::test_the_repo_skill_is_the_packaged_file` passes: `.claude/skills/file-ticket/SKILL.md` is a symlink, resolves to `pipeline/templates/skills/file-ticket/SKILL.md`, stats as a regular file, and is under 128KB -- the four conditions Claude Code's skill loader applies, so the repo keeps one copy of the skill and still loads it.
4. `tests/test_stages.py::test_data_files_live_inside_the_package_so_they_survive_install` passes with `C.SKILL_TEMPLATE` in its list, so the skill sits under `config.PKG` and survives `uv tool install .`.
5. `unzip -l dist/*.whl | grep SKILL.md` prints one line for
   `pipeline/templates/skills/file-ticket/SKILL.md` -- the wheel check the test in criterion 4 cannot make.
6. `tests/test_stages.py::test_the_docs_name_the_skill_init_installs` passes: the `pipeline/templates/` row in `CLAUDE.md` and the same row in `README.md` both name the file-ticket skill, and `README.md` says `init` installs `.claude/skills/file-ticket/SKILL.md`; `grep -c file-ticket README.md` prints `2`, up from `0` today.
7. `uv run --group dev pytest -q` passes, with no existing test removed or weakened.

## Decisions

**`pipeline/templates/skills/file-ticket/SKILL.md` is the only copy of the skill; this repo's `.claude/skills/file-ticket/SKILL.md` is a symlink to it.** Two real files drift, and `CLAUDE.md` warns that a skill describing a pipeline that no longer exists sends every future ticket in wrong. A symlink makes drift impossible instead of detectable. The alternative -- two real files plus a byte-equality test -- was weighed and rejected: it catches drift only after someone edits one file, and it doubles the bytes a reviewer must read.

**Claude Code loads a symlinked `SKILL.md`; this was checked, not assumed.** Verified against the installed binary, version 2.1.241, on 2026-08-24. The project-skills loader keeps a directory entry that `isDirectory()||isSymbolicLink()`, then runs `stat` (which follows a symlink) on `<dir>/SKILL.md` and skips the skill only `if(p!==null&&!p.isFile())`, logging `[skills] skipping <path>: not a regular file`. The same binary calls `lstat` on its Codex-import path and refuses a symlink there, so `stat` in the loader is deliberate. `tests/test_stages.py::test_the_repo_skill_is_the_packaged_file` asserts those conditions from the Python side; it cannot see a future version switching to `lstat`. If this repo's file-ticket skill ever stops appearing in a session's skill list, that switch is the first thing to check: replace the link with a real file, and replace that test with a byte-equality assertion against `C.SKILL_TEMPLATE`. Do not leave a copy with no check on it.

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

### 2026-08-24 15:09:14Z · plan-validation · gate · verdict=PASS

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
E       AssertionError: expected /tmp/tmp1zq6u3_k/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmp1zq6u3_k/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.12s ===============================

```
- ok: `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails on base `main` too -- the bug is not already fixed upstream
```
    )
E       AssertionError: expected /tmp/tmpb2ofpoeo/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmpb2ofpoeo/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-9p4_o0wg/base
      Built pipeline @ file:///tmp/pipeline-base-9p4_o0wg/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-24 15:09:14Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 15:10:44Z · human · note · by=chezzijr

**sent back to planning by chezzijr** -- approved at the gate, then two things surfaced before `implementing` claimed it.

1. Step 9 updates the `pipeline/templates/` row in `CLAUDE.md` but not the same description in `README.md`, which `plan-validation` flagged and nothing acts on. That row is at `README.md:417` now, not `:368` -- `e13dfed` on `main` added a `## When a ticket escalates` section above it, so re-read the file rather than trusting the old line number.
2. Justify the symlink in step 2, or replace it. The risk is not git: it is whether the harness follows a symlink when it discovers a skill. If it does not, this repo silently loses its own `file-ticket` skill, and no acceptance criterion catches that -- criterion 3 asserts `repo.resolve() == SKILL_TEMPLATE.resolve()`, which holds for a symlink whether or not the skill still loads. The alternative to weigh is two real files plus a test asserting they are byte-identical.

The rest of the plan stood up; this is not a rewrite.

### 2026-08-24 · planning · plan

**Both items in the human's note are addressed; the rest of the plan is unchanged.**

1. `README.md:417` carries the same `pipeline/templates/` row as `CLAUDE.md:62`.
   I re-read the file: `grep -n templates README.md` gives `417:    pipeline/templates/          the ticket schema and the project config example`.
   Step 10 now updates that row and the `## Use` paragraph, in one step over one
   file. Criterion 6 checks it: `grep -c file-ticket README.md` prints `2`, up
   from `0` today.
2. The symlink stays, justified from the harness. Claude Code 2.1.241's
   project-skills loader keeps a directory entry that
   `isDirectory()||isSymbolicLink()`, runs `let p=null;try{p=await o.stat(d)}catch{}`
   on `<dir>/SKILL.md`, and skips the skill only
   `if(p!==null&&!p.isFile())return E("[skills] skipping "+d+": not a regular file",...)`.
   `stat` follows a symlink. The same binary calls `lstat` on its Codex-import
   path and refuses what it finds there -- `SKILL.md is a symlink -- copy the
   skill manually` -- so `stat` in the loader is a deliberate distinction, not
   an oversight. Verified against
   `/home/chezzijr/.local/share/claude/versions/2.1.241` on 2026-08-24.

Criterion 3 no longer stops at `resolve()`. Step 5's test asserts the loader's
four conditions: the path is a symlink, it stats as a regular file, it resolves
to `C.SKILL_TEMPLATE`, and it is under 128KB. A copy in place of the link now
fails it, and so does a broken link.

The Python test cannot see a future Claude Code switching to `lstat`.
`## Decisions` records that as the first thing to check if the skill ever stops
appearing, and names the fallback: a real file plus a byte-equality assertion.

Two decision records name symlinks, DEC-052 and DEC-018. I read both; neither
binds. Both are noted in `## Decisions checked`.

### 2026-08-24 15:26:57Z · planning · session · session=e51f7e15-473e-426c-b2d3-512ce26b528e

`planning` ran as session `e51f7e15-473e-426c-b2d3-512ce26b528e`
- replay: `claude --resume e51f7e15-473e-426c-b2d3-512ce26b528e`
- log: `.project/logs/TICKET-056-planning-e51f7e15.log`

### 2026-08-24 15:26:57Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan revised: README.md:417 row added to step 10, and the symlink justified against Claude Code 2.1.241's loader, which stats SKILL.md and follows it

### 2026-08-24 15:27:12Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

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
E       AssertionError: expected /tmp/tmp12f15o91/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmp12f15o91/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails on base `main` too -- the bug is not already fixed upstream
```
    )
E       AssertionError: expected /tmp/tmpevbjoatp/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmpevbjoatp/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-sdl5291i/base
      Built pipeline @ file:///tmp/pipeline-base-sdl5291i/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```
- acceptance criterion names no test: 6. `grep -c file-ticket README.md` prints `2`, up from `0` today: the `pipeline/templates/` row names the skill and the `## Use` paragraph says `init` installs it, so `README.md` and `CLAUDE.md:62` describe the same directory.

### 2026-08-24 15:27:12Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion names no test: 6. `grep -c file-ticket README.md` prints `2`, up from `0` today: the `pipeline/templates/` row names the skill and the `## Use` paragraph says `init` installs it, so `README.md` and `CLAUDE.md:62` describe the same directory.

### 2026-08-24 · planning · plan

**The gate's one finding is fixed: criterion 6 now names a test.**

The gate said: `acceptance criterion names no test: 6. ...prints `2`, up from `0` today...`.
`gate()` requires a criterion to match
`\bpytest\b|\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/`
(`pipeline/core/gate.py:384`). Criterion 6 held only a `grep` command.

I did not reword the criterion to satisfy the regex. New step 9 adds
`test_the_docs_name_the_skill_init_installs` to `tests/test_stages.py`, beside
the two docs tests already there -- `test_the_docs_name_the_dependencies_and_the_targets_the_code_has`
(line 191) and `test_the_fenced_list_matches_the_rule_file` (line 238). It
asserts three things: the `pipeline/templates/` row in `CLAUDE.md` names the
file-ticket skill, the same row in `README.md` names it, and `README.md`
contains "installs `.claude/skills/file-ticket/SKILL.md`". Step 9 runs it and
expects `1 failed`; step 13 expects it green after the docs edits. Criterion 6
names the test and keeps the `grep -c file-ticket README.md` count.

The approved steps are unchanged: old 9-12 are now 10-13, and step 13 commits
`tests/test_stages.py` with the two docs files. `## Digest` gains gotcha 9 --
the new test reads the rule files from `C.PKG.parent`, like its neighbours, not
from `helpers.ROOT`.

### 2026-08-24 15:30:32Z · planning · session · session=0cfe80cf-8a1a-4398-97c8-4d5223a7b591

`planning` ran as session `0cfe80cf-8a1a-4398-97c8-4d5223a7b591`
- replay: `claude --resume 0cfe80cf-8a1a-4398-97c8-4d5223a7b591`
- log: `.project/logs/TICKET-056-planning-0cfe80cf.log`

### 2026-08-24 15:30:32Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ criterion 6 now names tests/test_stages.py::test_the_docs_name_the_skill_init_installs, added as step 9; plan is 13 steps over 8 files

### 2026-08-24 15:30:46Z · plan-validation · gate · verdict=PASS

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
E       AssertionError: expected /tmp/tmpux9t6wtl/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmpux9t6wtl/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails on base `main` too -- the bug is not already fixed upstream
```
   )
E       AssertionError: expected /tmp/tmpjsqmb1on/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmpjsqmb1on/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.21s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-0zus77yo/base
      Built pipeline @ file:///tmp/pipeline-base-0zus77yo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 12ms

```

### 2026-08-24 · plan-validation · judgment

**Pass. All eight items scored against the code.**

1. Root cause: `cmd_init` (`pipeline/cli/main.py:38`) writes `.project/` only,
   and `pyproject.toml:23` `packages = ["pipeline"]` leaves the skill out of the
   wheel. Steps 1, 4 and 7 fix both halves; step 12 checks the wheel.
2. Decisions: none bind. I re-read the `CLAUDE.md` rule the plan cites -- data
   dirs are found via `Path(__file__).parent` -- and the plan complies.
3. Scope: every step traces to a criterion. Step 3 (the install-line comment)
   traces to criterion 7 through the file it ships.
4. Criteria are falsifiable. One narrow gap, in the note below.
5. No research left: each step names a file, a line and a symbol.
6. Riskiest step: step 2, the symlink. `## Decisions` states the fallback --
   replace the link with a real file and a byte-equality test.
7. Regression surface: `grep` over `pipeline/` for `SKILL`, `.claude/skills` and
   `skills/file-ticket` returns `No matches found`, so no code reads the moved
   path. `test_the_fenced_list_matches_the_rule_file` reads the paragraph at
   `CLAUDE.md:241`; steps 10 and 11 edit lines 62 and 251, outside it.
8. Blast radius: `class: feature`, 13 steps, 8 files, matching `files_declared`.

Two line numbers drifted. The interface paragraph the plan calls `CLAUDE.md:250`
is at line 251, and step 9's test is step 9 of 13 while `## Digest` gotcha 1
still calls the wheel check "step 11" (it is step 12). Both quote their anchor
text, so neither blocks.

Note for `implementing`, non-blocking: step 9's `CLAUDE.md` row check keeps any
line holding both `pipeline/templates/` and `file-ticket`. Step 10's interface
sentence names `pipeline/templates/skills/file-ticket/SKILL.md`, so that
sentence alone can satisfy the check while the table row at `CLAUDE.md:62` stays
unchanged. Filtering to lines that start with `|` closes it.

### 2026-08-24 15:33:17Z · plan-validation · session · session=bc893855-b1ea-4d71-8916-49e2bff41e17

`plan-validation` ran as session `bc893855-b1ea-4d71-8916-49e2bff41e17`
- replay: `claude --resume bc893855-b1ea-4d71-8916-49e2bff41e17`
- log: `.project/logs/TICKET-056-plan-validation-bc893855.log`

### 2026-08-24 15:33:17Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan-validation pass: all eight items scored against the code; one non-blocking note on step 9's CLAUDE.md row check

### 2026-08-24 16:27:25Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 16:39:25Z · plan-validation · gate · verdict=PASS

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
E       AssertionError: expected /tmp/tmp5qwnhkxz/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmp5qwnhkxz/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: `tests/test_cli.py::test_init_installs_the_file_ticket_skill` fails on base `main` too -- the bug is not already fixed upstream
```
   )
E       AssertionError: expected /tmp/tmpwqhgj9je/.claude/skills/file-ticket/SKILL.md to exist after `pipeline init`, found: []
E       assert False
E        +  where False = is_file()
E        +    where is_file = PosixPath('/tmp/tmpwqhgj9je/.claude/skills/file-ticket/SKILL.md').is_file

tests/test_cli.py:305: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_init_installs_the_file_ticket_skill - Assertio...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.23s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-l7posckw/base
      Built pipeline @ file:///tmp/pipeline-base-l7posckw/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 16:39:25Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 · implementing · todo

**All 13 plan steps done.**

1. Move skill to `pipeline/templates/skills/file-ticket/SKILL.md` -- done
2. Symlink `.claude/skills/file-ticket/SKILL.md` -- done, mode `120000`
3. Fix install-line comment -- done
4. Add `config.SKILL_TEMPLATE` -- done
5. Add `test_the_repo_skill_is_the_packaged_file` -- done
6. Add `test_init_keeps_a_customised_file_ticket_skill` -- done
7. Install skill in `cmd_init` -- done
8. Verify GREEN, commit -- done (`569573d`)
9. Add `test_the_docs_name_the_skill_init_installs` -- done
10. Update `CLAUDE.md` row + interface paragraph -- done
11. Update `README.md` row + `## Use` paragraph -- done
12. `uv build --wheel` + `unzip -l` check -- done, `dist/` removed after
13. Full suite, commit -- done (`463261b`)

### 2026-08-24 · implementing · report

**All 7 acceptance criteria pass.** `uv run --group dev pytest -q` -> `311 passed`.

1. `test_init_installs_the_file_ticket_skill` passes.
2. `test_init_keeps_a_customised_file_ticket_skill` passes.
3. `test_the_repo_skill_is_the_packaged_file` passes.
4. `test_data_files_live_inside_the_package_so_they_survive_install` passes with `C.SKILL_TEMPLATE` added.
5. `unzip -l dist/*.whl | grep SKILL.md` printed one line:
   `8484  2020-02-02 00:00   pipeline/templates/skills/file-ticket/SKILL.md`
6. `test_the_docs_name_the_skill_init_installs` passes; `grep -c file-ticket README.md` prints `2`.
7. Full suite passes, no test removed or weakened.

Three commits on `ticket/056`: `a11abed` (move + symlink), `569573d` (install
in `cmd_init` + tests), `463261b` (docs + docs test). TDD followed throughout:
each new test run RED before the code, then GREEN after.

### 2026-08-24 16:42:23Z · implementing · session · session=73f00287-b26f-483d-bd67-24c86ed27196

`implementing` ran as session `73f00287-b26f-483d-bd67-24c86ed27196`
- replay: `claude --resume 73f00287-b26f-483d-bd67-24c86ed27196`
- log: `.project/logs/TICKET-056-implementing-73f00287.log`

### 2026-08-24 16:42:23Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ executed all 13 plan steps, all 7 acceptance criteria pass, 311 tests pass, 3 commits (a11abed, 569573d, 463261b)

### 2026-08-24 · review · finding · severity=none

**No blocking findings.** Reviewed the whole branch delta, `43a986d..463261b`,
8 files. `uv run --group dev pytest -q` -> `311 passed`. The move is
byte-identical apart from plan step 3: `git diff main:.claude/... HEAD:pipeline/templates/...`
prints one hunk, `-uv tool install --editable . --force     # from the repo root`
/ `+... # from the agent-pipeline checkout`. `git ls-files -s` prints mode
`120000` for the repo copy. `grep -c file-ticket README.md` prints `2`.
`git status --porcelain` is empty and no `dist/` remains.

Three non-blocking findings:

1. severity=minor. `test_the_docs_name_the_skill_init_installs` does not pin
   the `CLAUDE.md` row. Two lines match its filter -- the row at `CLAUDE.md:62`
   and the interface sentence at `CLAUDE.md:261`, which also holds
   `pipeline/templates/` and `file-ticket`. Reverting the row alone leaves the
   test green. Plan-validation raised this and named the fix: add
   `ln.startswith("|")` to the comprehension at `tests/test_stages.py:225`.
   `README.md` is unaffected -- only its row matches.
2. severity=minor. `cmd_init` writes through a broken symlink.
   `skill.exists()` (`pipeline/cli/main.py:54`) is False for a dangling link,
   so `skill.write_text()` (line 58) follows it and writes the link's target,
   or raises `FileNotFoundError` past `main()`'s handler. Reaching it needs a
   hand-made broken link at that path.
3. severity=none. `--private` excludes `.project/` only, so the installed
   `.claude/skills/file-ticket/SKILL.md` shows up untracked in a shared repo.
   The comment's promise at `pipeline/cli/main.py:60` still holds: an untracked
   file reaches no teammate's diff.

Two findings I dropped. A scaffolded project's `.claude/skills/` costs stage
spawns nothing: no stage declares `skills:`, so `render()` passes
`no_skills_flag = "--disable-slash-commands"` (`pipeline/core/config.py:253`,
`pipeline/harnesses/claude-code.toml:98`), which drops the Skill tool. The docs
tests reading `C.PKG.parent` break after `uv tool install .`, but
`test_the_docs_name_the_dependencies_and_the_targets_the_code_has`
(`tests/test_stages.py:191`) already does exactly that.

I could not re-run criterion 5: the guard blocks `uv build` for a read-only
stage. Two facts support `implementing`'s wheel line instead.
`[tool.hatch.build.targets.wheel]` declares `packages = ["pipeline"]` and no
`exclude`, and the file is tracked. The quoted size, `8484`, is the digest's
`8470` plus the 14 bytes step 3 added.

### 2026-08-24 16:46:18Z · review · session · session=0e00ef55-31c8-44cf-b934-32207bc70bd0

`review` ran as session `0e00ef55-31c8-44cf-b934-32207bc70bd0`
- replay: `claude --resume 0e00ef55-31c8-44cf-b934-32207bc70bd0`
- log: `.project/logs/TICKET-056-review-0e00ef55.log`

### 2026-08-24 16:46:18Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review pass: delta 43a986d..463261b reviewed, 311 tests pass, 3 non-blocking findings appended

### 2026-08-24 16:46:34Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 16:46:35Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/056


Current branch ticket/056 is up to date.
Already up to date.
Updating 43a986d..463261b
Fast-forward
 .claude/skills/file-ticket/SKILL.md            | 181 +------------------------
 CLAUDE.md                                      |   6 +-
 README.md                                      |   6 +-
 pipeline/cli/main.py                           |   9 +-
 pipeline/core/config.py                        |   6 +-
 pipeline/templates/skills/file-ticket/SKILL.md | 180 ++++++++++++++++++++++++
 tests/test_cli.py                              |  33 +++++
 tests/test_stages.py                           |  44 +++++-
 8 files changed, 278 insertions(+), 187 deletions(-)
 mode change 100644 => 120000 .claude/skills/file-ticket/SKILL.md
 create mode 100644 pipeline/templates/skills/file-ticket/SKILL.md

```

### 2026-08-24 16:46:35Z · merging · decision

decision recorded as `DEC-056`
