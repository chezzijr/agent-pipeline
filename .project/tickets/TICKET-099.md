---
id: TICKET-099
stage: done
class: feature
branch: ticket/099
test_file: tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update
files_declared:
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/core/config.py
- tests/test_cli.py
- tests/test_config.py
counters:
  plan_validation_attempts: 2
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 21
  plan_files: 6
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: holistic-review
  id: 5289ee5b-2ca5-497b-a5ef-2b9d6a391531
  log: .project/logs/TICKET-099-holistic-review-5289ee5b.log
  cost_usd: 1.118196
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified every helper it claims exists: write_atomic
  at ticket.py:115 and already imported at config.py:19, hashlib and json at config.py:7-8,
  SKILLS_DIR used only in the loop being replaced. Respects both ticket constraints:
  a customised or unrecorded copy is never rewritten without --force, and init stays
  idempotent; it also refuses to write a symlinked copy at all, which is this repo''s
  own layout. Step 8 back-fills a record for an already-current copy so the next template
  edit reads stale rather than unknown. Step 18 proves the symlink test bites by reordering
  the branches and explicitly rules out the swap that would not falsify, because is_file
  follows the link. Nothing fenced -- .project/skills.json is not .project/pipeline.toml.'
approved_at: '2026-08-29T09:13:28.225164+00:00'
---

## Summary

Fixed: a scaffolded project's skill copies drifted and nothing detected it.

Added `skill_marks`/`mark_skill`/`skill_status`/`install_skill` to
`pipeline/core/config.py`: a per-project manifest
`<project>/.project/skills.json` maps skill name to the sha256 `init` wrote.
`skill_status()` names six states, `is_symlink()` checked first: `linked`,
`absent`, `current`, `stale` (matches the record, template moved on),
`customised` (differs from both), `unknown` (differs, no record).

`cmd_init` (`pipeline/cli/main.py`) now iterates `skill_status()` and prints
the state on every non-install branch, still never overwriting (DEC-056).
The new `pipeline --project P skills [--refresh] [--force]` does the
writing: `--refresh` rewrites a `stale` copy, `--refresh --force` also
rewrites `customised`/`unknown`, and a `linked` row is never written under
any flag. `--force` without `--refresh` is refused.

Committed as 28b8289 (manifest + helpers), 7f15d61 (`cmd_init` reporting),
94a5253 (`skills` command), f3751f1 (docs).

Review returned `fail` once, on `cmd_skills` installing an `absent` row with
no flags. 9136f54 fixed it: the branch reads `if args.refresh and state ==
"absent"`, so a no-flag `pipeline skills` reports `{name}: absent at {dst}`
instead. `tests/test_cli.py::test_skills_with_no_flags_never_installs_an_absent_copy`
holds it, confirmed RED first. The second review pass returned `ok` on the
delta `f3751f1..9136f54`.

holistic-review returned `ok` on the whole diff `main...9136f54`
(6 files, `262 insertions(+), 15 deletions(-)`). The sum matches the plan,
no fix undid an earlier one, error handling is consistent (`skill_marks` is
the one tolerant reader; `install_skill` and `skill_status` propagate an
OSError, as the loop they replaced did), and nothing landed outside the
acceptance criteria. Neither packaged `SKILL.md` names `pipeline skills` or
`init`'s copy states, so no skill drifted.

All 11 acceptance criteria pass. Re-measured at holistic-review: full suite
`493 passed in 34.96s`; guard `guard: all passed`; `skills --help` matched
`--refresh`/`--force` on 3 lines; both `grep -c` print `1`. Criterion 5
stands as checked on the first review pass: it mutates
`pipeline/core/config.py`, which has one commit on this branch (28b8289) and
which holistic-review may not edit.

Three non-blocking nits are in the review entries, none fixed: no test covers
the `--refresh` install of an `absent` row, `cmd_init` reads `skills.json`
once per row, and `skill_status` reads `dst` twice for the `stale` test.

## Reproduction

`tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update`, run
with `uv run --group dev pytest -q tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update`.

The test inits a throwaway project, appends a line to the packaged
`file-ticket` `SKILL.md`, re-runs `init`, and asserts the run reports the
drift. It fails instead:

    AssertionError: expected `init` to report the drift between
    /tmp/tmp6vt2nqmc/.claude/skills/file-ticket/SKILL.md and
    .../pipeline/templates/skills/file-ticket/SKILL.md, got:
    "initialised /tmp/tmp6vt2nqmc/.project -- edit
    /tmp/tmp6vt2nqmc/.project/pipeline.toml for this project's commands\n
      file-ticket skill already at
    /tmp/tmp6vt2nqmc/.claude/skills/file-ticket/SKILL.md -- kept\n
      pipeline-config skill already at
    /tmp/tmp6vt2nqmc/.claude/skills/pipeline-config/SKILL.md -- kept\n"

expect: expected `init` to report the drift between

Committed at 5762107 on `ticket/099`.

## Digest

Files touched: `pipeline/core/config.py` (the manifest and status helpers),
`pipeline/cli/main.py` (`cmd_init` reporting plus the new `cmd_skills`),
`tests/test_cli.py`, `tests/test_config.py`, `README.md`, `CLAUDE.md`.

Key functions: `cmd_init` at `pipeline/cli/main.py:40`, its skill loop at
`pipeline/cli/main.py:60-67`; `SKILLS_DIR` and `SKILL_TEMPLATE` at
`pipeline/core/config.py:32-33`; `write_atomic` at `pipeline/core/ticket.py:115`
(tmp sibling plus `os.replace`); `pin_dir` at `pipeline/core/config.py:99` is
the existing `hashlib.sha256` precedent. `json`, `hashlib` and `write_atomic`
are already imported in `pipeline/core/config.py`; `json` is already imported
in `pipeline/cli/main.py`. `cli(project, *args)` at `tests/test_cli.py:22` runs
`python -m pipeline --project <project> <args>` and returns the
`CompletedProcess`.

Entry points: `pipeline init [dir] [--private]` and the new
`pipeline --project P skills [--refresh] [--force]`. The subparser table is one
line per command at `pipeline/cli/main.py:637-667`.

Design chosen (the ticket left the shape to planning): a per-project manifest
`<project>/.project/skills.json`, name -> sha256 of the template text `init`
last wrote. It is the only way to tell an untouched-but-stale copy from a
customised one, which both ticket constraints need. Six states: `absent`,
`current`, `stale` (differs from the template, matches the recorded install),
`customised` (differs from both), `unknown` (differs, no record -- a project
scaffolded before this change), `linked` (a symlink).

What changed since the plan Tier B rejected: step 18 and the fifth acceptance
criterion, which named a mutation that does not bite. Both said to swap
`skill_status`'s first two branches. That swap yields `absent if not
is_file()` then `linked if is_symlink()`, and `Path.is_file()` follows the
symlink to `<project>/linked-elsewhere.md`, which exists -- so the row still
reads `linked`, no refresh path writes it, and the test still passes. Both now
prescribe the mutation that does bite: move the `linked` branch below the
`current`/`stale`/`customised`/`unknown` branches, so `is_symlink()` is tested
last. Under that order the symlinked `pipeline-config` copy reads `customised`,
because its text `# linked elsewhere` differs from the packaged template and
`init` recorded the template digest for it; step 11 writes the row under
`--force`, `write_atomic`'s `os.replace` replaces the link with a regular file,
and the assertion `--force rewrote a symlinked skill copy` fires. Step 18 also
tells the implementer not to substitute the first-two-branch swap. Step 16's
fixture, which plants the link at a file whose text differs from the template,
is what makes that order reachable; it is unchanged. Nothing else in the plan
changed; every other Tier B item passed.

Gotchas:
1. `cmd_init` must keep printing the skill path and the word `kept` on every
   non-install branch: `tests/test_cli.py:487` asserts the path is in stdout
   and `tests/test_cli.py:492` asserts `kept` is in stdout.
2. This repo's own `.claude/skills/*/SKILL.md` are symlinks into `SKILLS_DIR`
   (DEC-056). `skill_status` must test `is_symlink()` FIRST, before every
   other branch, and no refresh path may write a `linked` row -- not even
   under `--force`. `Path.is_file()` follows a symlink, so the branch that
   actually steals a `linked` row is a content branch, not `absent`.
3. `SKILLS_DIR.iterdir()` at `pipeline/cli/main.py:60` is the only enumeration
   of skills; nothing else copies them (checked with
   `grep -rn SKILLS_DIR pipeline tests`).
4. `init` still never overwrites (DEC-056); only `pipeline skills --refresh`
   writes over an existing copy.
5. `.project/skills.json` is not in `machine.FENCED` and `.project/` is
   excluded from `tree_snapshot()`, so the new file changes no gate.
6. `write_atomic` writes a tmp sibling and `os.replace`s it, so a write to a
   symlinked path replaces the link and leaves its target untouched. That is
   why the assertion that bites in step 17 is `is_symlink()`, not the target
   text.
7. Baseline measured on `5762107`:
   `uv run --group dev pytest -q tests/test_cli.py -k skill` prints
   `1 failed, 3 passed, 34 deselected in 0.74s`, the one failure being
   `test_reinit_does_not_detect_a_packaged_skill_update`.

## Decisions checked

Grep terms used in `/home/chezzijr/proj/agent-pipeline/.project/decisions/`:
`skills`, `skill`, `symlink`, `pipeline init`, `scaffold`. Every id below is a
file in that directory, checked with `ls .project/decisions/`.

- DEC-056 (active) -- "`init` never overwrites an existing skill file", and
  this repo's `.claude/skills/file-ticket/SKILL.md` is a symlink to the
  packaged template. The plan complies: `init` keeps every existing copy, and
  `skills --refresh` is the deliberate re-install that record names as the
  cost of the rule. It does not supersede it.
- DEC-084 (active) -- `cmd_init` copies exactly `<skill>/SKILL.md` per
  directory under `SKILLS_DIR`; a second file in a skill directory never
  reaches a scaffolded project. The plan keeps that shape: the manifest
  hashes `SKILL.md` only and adds no file inside a skill directory.
- DEC-098 (active) -- restates DEC-084 for `file-ticket`. No conflict.
- DEC-018 (active) -- `active_decisions()` skips a symlinked `DEC-*.md`
  ("never follow a planted link"); the same rule is why `linked` is a
  terminal state here.
- DEC-037, DEC-075 (active) -- `pipeline init --private` and the pin
  directory. `.project/skills.json` lives in the project, so a `--private`
  project keeps its manifest git-ignored with the rest of `.project/`. No pin
  is involved.

## Plan

1. Add to `pipeline/core/config.py`, after `sync_pins`: `SKILL_MARKS = ".project/skills.json"`, `project_skill(project, name)` returning `project / ".claude" / "skills" / name / "SKILL.md"`, `skill_digest(text)` returning `hashlib.sha256(text.encode()).hexdigest()`, and `skill_marks(project) -> dict` which returns `{}` when `project / SKILL_MARKS` is missing, unreadable or not a dict of string values (catch `OSError` and `ValueError`), so an unrecorded copy reads as unknown and never as pristine.
2. Add `mark_skill(project, name, text)` to `pipeline/core/config.py`: merge `{name: skill_digest(text)}` into `skill_marks(project)`, run `(project / SKILL_MARKS).parent.mkdir(parents=True, exist_ok=True)`, and write `json.dumps(marks, indent=2, sort_keys=True)` plus a trailing newline through the existing `write_atomic`.
3. Add `skill_status(project) -> list[tuple[str, Path, str]]` to `pipeline/core/config.py`: read `skill_marks(project)` once, then for each `src` in `sorted(SKILLS_DIR.iterdir())` yield `(src.name, project_skill(project, src.name), state)` where state is `linked` if `dst.is_symlink()`, else `absent` if not `dst.is_file()`, else `current` if `dst.read_text()` equals `(src / "SKILL.md").read_text()`, else `stale` if `marks.get(src.name)` equals `skill_digest(dst.read_text())`, else `customised` if `src.name in marks`, else `unknown`.
4. Add `install_skill(project, name) -> Path` to `pipeline/core/config.py`: read `(SKILLS_DIR / name / "SKILL.md").read_text()`, run `dst.parent.mkdir(parents=True, exist_ok=True)`, call `write_atomic(dst, text)`, call `mark_skill(project, name, text)`, and return `dst`.
5. Add `tests/test_config.py::test_skill_status_reads_an_unrecorded_difference_as_unknown`: import `install_skill` and `skill_status` from `pipeline.core.config`, build a temp dir, write the text `# ours` into `.claude/skills/file-ticket/SKILL.md` with no manifest, assert the `file-ticket` state is `unknown`, then call `install_skill(d, "file-ticket")` and assert the state is `current`. Run `uv run --group dev pytest -q tests/test_config.py -k skill_status`, then commit steps 1-5 together.
6. Rewrite the skill loop at `pipeline/cli/main.py:60-67` to iterate `skill_status(project)` instead of `SKILLS_DIR.iterdir()`: on state `absent` call `install_skill(project, name)` and print the unchanged line `  installed the {name} skill at {dst}`, and on every other state print the line step 7 gives, which always contains the path and the word `kept`. Import `install_skill`, `mark_skill`, `skill_marks` and `skill_status` from `pipeline.core.config` in `pipeline/cli/main.py`, and drop `SKILLS_DIR` from that import if nothing else in the file uses it.
7. Use exactly these five `cmd_init` lines in `pipeline/cli/main.py`, keyed on state -- `current`: `  {name} skill already at {dst} -- kept`; `linked`: `  {name} skill already at {dst} -- kept (a symlink to the packaged template)`; `stale`: `  {name} skill at {dst} is stale -- kept; run pipeline --project {project} skills --refresh`; `customised`: `  {name} skill at {dst} differs from the packaged template -- kept (customised)`; `unknown`: `  {name} skill at {dst} differs from the packaged template -- kept (no install record; skills --refresh --force overwrites it)`.
8. In `cmd_init` (`pipeline/cli/main.py`), when a state is `current` and `name not in skill_marks(project)`, call `mark_skill(project, name, dst.read_text())` before printing, so a project scaffolded before this change adopts a record while its copy still matches the template, and the next template edit reads as `stale` rather than `unknown`.
9. Run `uv run --group dev pytest -q tests/test_cli.py -k skill`: `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update` now passes on the `is stale` line, and the other three still pass. Commit steps 6-9.
10. Add `cmd_skills(args)` to `pipeline/cli/main.py` above `cmd_config`: call `proj(args)`, call `die("--force applies to --refresh only")` when `args.force` is set and `args.refresh` is not, then walk `skill_status(project)` applying steps 11 and 12 to each row.
11. In `cmd_skills` (`pipeline/cli/main.py`) under `--refresh`: an `absent` row calls `install_skill(project, name)` and prints `{name}: installed at {dst}`; a `stale` row calls `install_skill(project, name)` and prints `{name}: refreshed at {dst}`; a `customised` or `unknown` row calls `install_skill(project, name)` and prints `{name}: overwritten at {dst}` only when `--force` is also set; a `linked` row is never written, with or without `--force`.
12. In `cmd_skills` (`pipeline/cli/main.py`) every row not written by step 11 prints `{name}: {state} at {dst}` plus a hint: `stale` adds ` -- run pipeline --project {project} skills --refresh`, `customised` and `unknown` add ` -- kept; add --force to overwrite it`, `linked` adds ` -- a symlink to the packaged template; never rewritten`, and `current` and `absent` add nothing.
13. Register the command in `pipeline/cli/main.py` beside the `config` row at `pipeline/cli/main.py:640`, one line in the same style: `sub.add_parser("skills", help="is this project's skill copy current with the packaged template")`, then `--refresh` (`action="store_true"`, help "rewrite a stale copy from the packaged template; a customised copy is kept"), then `--force` (`action="store_true"`, help "with --refresh, overwrite a customised copy too"), then `set_defaults(fn=cmd_skills)`.
14. Add `tests/test_cli.py::test_skills_refresh_updates_a_stale_copy_and_keeps_a_customised_one`: run `cli(d, "init")`, overwrite the project's `pipeline-config` copy with the text `# ours`, append an `<!-- upstream update -->` line to `SKILL_TEMPLATE` inside a `try` whose `finally` restores the original text, assert `cli(d, "skills").stdout` contains `file-ticket: stale` and `pipeline-config: customised`, assert that after `cli(d, "skills", "--refresh")` the project's `file-ticket` copy equals `SKILL_TEMPLATE.read_text()` and its `pipeline-config` copy is still `# ours`, and assert `cli(d, "skills").stdout` then contains `file-ticket: current`.
15. Run `uv run --group dev pytest -q tests/test_cli.py -k skill`; the run reports no failures. Commit steps 10-15.
16. Open `tests/test_cli.py::test_skills_force_overwrites_a_customised_copy_but_never_a_symlink` in `tests/test_cli.py`: run `cli(d, "init")`, overwrite the project's `file-ticket` copy with the text `# ours`, write the text `# linked elsewhere` to `d / "linked-elsewhere.md"`, then replace the project's `pipeline-config` copy with `unlink()` plus `symlink_to(d / "linked-elsewhere.md")` -- a target whose text differs from the packaged template, which is what makes step 17 falsify an order that tests `is_symlink()` after the content branches.
17. Finish that test in `tests/test_cli.py`: run `cli(d, "skills", "--refresh", "--force")`, assert the `file-ticket` copy equals `SKILL_TEMPLATE.read_text()`, assert the `pipeline-config` copy still satisfies `is_symlink()` with the assertion message `--force rewrote a symlinked skill copy`, assert `(d / "linked-elsewhere.md").read_text()` is still `# linked elsewhere`, and assert `cli(d, "skills", "--force")` exits non-zero with `--force applies to --refresh only` in stderr.
18. Prove step 17 bites, in `pipeline/core/config.py`: move `skill_status`'s `linked` branch below its `current`/`stale`/`customised`/`unknown` branches so `is_symlink()` is tested last, run `uv run --group dev pytest -q tests/test_cli.py::test_skills_force_overwrites_a_customised_copy_but_never_a_symlink` and confirm it fails on `--force rewrote a symlinked skill copy`, restore the `is_symlink()`-first order of step 3, re-run that test to green, then run `uv run --group dev pytest -q tests/test_cli.py -k skill` and commit steps 16-18.
    Do not substitute a swap of the first two branches of `skill_status` in `pipeline/core/config.py`: `Path.is_file()` follows the link to `<project>/linked-elsewhere.md`, which exists, so the chain reaches `is_symlink()` anyway, the row still reads `linked`, and the test still passes.
19. Document the command in the `## Use` section of `README.md`: add the shell-block line `pipeline --project ~/code/myproject skills --refresh` with the comment "bring this project's skill copies up to the packaged templates", and after the existing sentence "An existing file is kept, so a project that customised one keeps its version." add two sentences saying that `init` now names a copy as stale (untouched since install, template changed since) or customised, that `pipeline skills` reports the same states, and that `--refresh` rewrites only a stale copy while `--refresh --force` is required to overwrite a customised one. Keep the existing literal phrase "installs `.claude/skills/file-ticket/SKILL.md`" -- `tests/test_stages.py::test_the_docs_name_the_skill_init_installs` greps for it.
20. Add one bullet to the "Gotchas, each found the hard way" list in `CLAUDE.md`: `init` records the sha256 of each skill it writes in `<project>/.project/skills.json`; that record is the only way `skill_status()` tells a stale copy from a customised one; a copy with no record reads as `unknown` and is never rewritten without `--force`; and a symlinked copy, which is this repo's own layout, is never written at all.
21. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py` from the worktree root; both report no failures. Commit steps 19-21, whose diff is `README.md` and `CLAUDE.md`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update`
  exits 0.
- `uv run --group dev pytest -q tests/test_cli.py -k skill` reports no
  failures; re-measure that run on `5762107` at check time rather than pinning
  a total.
- `uv run --group dev pytest -q tests/test_cli.py::test_skills_refresh_updates_a_stale_copy_and_keeps_a_customised_one`
  exits 0.
- `uv run --group dev pytest -q tests/test_cli.py::test_skills_force_overwrites_a_customised_copy_but_never_a_symlink`
  exits 0.
- Move the `linked` branch of `skill_status` in `pipeline/core/config.py` below
  its `current`/`stale`/`customised`/`unknown` branches, so `is_symlink()` is
  tested last, then run
  `uv run --group dev pytest -q tests/test_cli.py::test_skills_force_overwrites_a_customised_copy_but_never_a_symlink`:
  it exits non-zero with `--force rewrote a symlinked skill copy` in the
  output. Restore the `is_symlink()`-first order and the same command exits 0.
- `uv run --group dev pytest -q tests/test_config.py::test_skill_status_reads_an_unrecorded_difference_as_unknown`
  exits 0.
- `uv run python -m pipeline skills --help` exits 0, and its output contains
  both `--refresh` and `--force`.
- `grep -c "skills --refresh" README.md` prints a number greater than 0.
- `grep -c "skills.json" CLAUDE.md` prints a number greater than 0.
- `uv run --group dev pytest -q` reports no failure that does not also fail on
  `5762107`; re-measure the base run at check time rather than pinning a total.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

**A scaffolded project's skill copies are tracked in
`<project>/.project/skills.json`: skill name -> sha256 of the template text
`init` wrote.** Without that record a copy differing from the packaged template
is ambiguous -- it is either a project that customised the file or a project
scaffolded before the template changed -- and the two must not be treated
alike. `skill_status()` resolves it: a copy matching the record is `stale` and
`pipeline skills --refresh` rewrites it; a copy differing from the record is
`customised` and only `--refresh --force` touches it. Deleting `skills.json`
is safe but not free: every differing copy falls back to `unknown`, which a
plain `--refresh` refuses.

**`init` still never overwrites an existing skill copy (DEC-056); it only
names the state.** The write lives in `pipeline skills --refresh`, the
deliberate re-install DEC-056 said a project needs. Moving the refresh into
`init` would break its idempotence and silently discard a customisation, which
is what the `-- kept` branch exists to protect.

**A symlinked copy is state `linked` and is never written, under any flag, so
`skill_status()` tests `is_symlink()` first, before every other branch.** This repo's own
`.claude/skills/*/SKILL.md` are symlinks into `pipeline/templates/skills/`
(DEC-056), and a refresh there replaces a layout the repo chose deliberately.
The write is `write_atomic`, which `os.replace`s the path, so the packaged
template itself survives the wrong order -- the link does not. Any future
in-place write through that path would rewrite the packaged template as well.
`test_skills_force_overwrites_a_customised_copy_but_never_a_symlink` holds the
ordering: it links the copy at a file whose text differs from the template, so
an order testing `is_symlink()` after the content branches reads `customised`,
`--force` writes, and the `is_symlink()` assertion fails. Moving the
`is_symlink()` test after `is_file()` alone is not the hazard -- `is_file()`
follows the link, so the row still reads `linked`.

## Rollback

Revert the commits from steps 5, 9, 15, 18 and 21 on `ticket/099`. `init`
returns to the `skill.exists()` check at `pipeline/cli/main.py:60-67`, the
`skills` command disappears, and a project keeps whatever copy it has.
`<project>/.project/skills.json` stays behind in any project that ran the new
`init`; it is inert once the code reading it is gone, and deleting it is
optional.

## Thread

### 2026-08-29 08:14:07Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 · triage · reproduced · result=ok

Reproduced. `pipeline init`'s skill copy loop (`pipeline/cli/main.py:60-67`)
checks only `skill.exists()`, never diffs content against `SKILLS_DIR`. So a
packaged skill edit never reaches an already-scaffolded project, and `init`
reports "kept" identically whether the copy is untouched-but-stale or
deliberately customised.

Added `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update`:
inits a throwaway project, appends a line to the real `file-ticket` `SKILL.md`
template (restored in `finally`), re-runs `init`, and asserts the run's stdout
names the drift. It fails with `AssertionError: expected \`init\` to report
the drift between ...`, confirming no detection exists today. See
`## Reproduction` for the full command and output.

This is a feature gap, not a regression: no fix files are obvious yet since
`planning` owns the shape (refresh command, version stamp, or symlink).
Leaving `test_file` as the one new test above.

### 2026-08-29 08:16:18Z · triage · session · session=bec53062-04e0-42d7-b121-4d52e7f890e8

`triage` ran as session `bec53062-04e0-42d7-b121-4d52e7f890e8`
- replay: `claude --resume bec53062-04e0-42d7-b121-4d52e7f890e8`
- log: `.project/logs/TICKET-099-triage-bec53062.log`
- cost: $0.48 of a $3 cap
- tokens: 7,810 out (2,743 thinking) · 46 in · 955,838 cache read · 53,487 cache write

### 2026-08-29 08:16:18Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- `init` only checks a scaffolded skill file exists, never diffs it against the packaged template, so an upstream skill edit never reaches an already-scaffolded project and nothing reports the drift

### 2026-08-29 · planning · plan written · result=ok

Plan written: 19 steps over 6 files. Shape chosen: a per-project manifest
`<project>/.project/skills.json`, skill name -> sha256 of the template text
`init` wrote. That record is what separates the ticket's two cases -- a copy
matching it is `stale` and safe to rewrite, a copy differing from it is
`customised` and is kept. `init` gains the report and keeps its `-- kept`
branch, so it stays idempotent and never overwrites (DEC-056). The write lives
in a new `pipeline --project P skills [--refresh] [--force]`.

Two findings the steps rest on. A copy with no record reads as `unknown`, not
as stale: a project scaffolded before this change must not have a
customisation refreshed out from under it. A symlinked copy reads as `linked`
and is never written under any flag -- this repo's own
`.claude/skills/*/SKILL.md` are symlinks into `pipeline/templates/skills/`, and
a write through one writes the packaged template itself.

Baseline measured on `5762107`:
`uv run --group dev pytest -q tests/test_cli.py -k skill` prints
`1 failed, 3 passed, 34 deselected in 0.74s`.

Scope note, outside this ticket: no test asserts the two shipped skills stay in
sync with the CLI they describe.

### 2026-08-29 08:22:41Z · planning · session · session=affbc68e-81c8-4f1f-a098-2c175bf96b89

`planning` ran as session `affbc68e-81c8-4f1f-a098-2c175bf96b89`
- replay: `claude --resume affbc68e-81c8-4f1f-a098-2c175bf96b89`
- log: `.project/logs/TICKET-099-planning-affbc68e.log`
- cost: $2.53 of a $10 cap
- tokens: 32,319 out (12,679 thinking) · 50 in · 1,521,773 cache read · 95,570 cache write

### 2026-08-29 08:22:41Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned a per-project skills.json digest manifest: init names each copy stale/customised/linked, and a new `pipeline skills --refresh` rewrites only a stale one

### 2026-08-29 08:23:18Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update` fails as required
```
y at /tmp/tmp2yxq6ah4/.claude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-099/.venv/bin/python', '-m', 'pipeline', ...ept\n  pipeline-config skill already at /tmp/tmp2yxq6ah4/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout
E                +  and   "initialised /tmp/tmp2yxq6ah4/.project -- edit /tmp/tmp2yxq6ah4/.project/pipeline.toml for this project's commands\n  ...KILL.md -- kept\n  pipeline-config skill already at /tmp/tmp2yxq6ah4/.claude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-099/.venv/bin/python', '-m', 'pipeline', ...ept\n  pipeline-config skill already at /tmp/tmp2yxq6ah4/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout

tests/test_cli.py:514: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.28s ===============================

```
- ok: `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update` fails on base `main` too -- the bug is not already fixed upstream
```
ude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/tmp/pipeline-base-ieb5_6b9/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpg3...ept\n  pipeline-config skill already at /tmp/tmpg3se1twr/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout

tests/test_cli.py:514: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.51s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ieb5_6b9/base
      Built pipeline @ file:///tmp/pipeline-base-ieb5_6b9/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 · plan-validation · Tier B · result=fail

**Tier B: fail.** One scored finding.

- **Falsifiable criteria: fail.** Step 16's
  `test_skills_force_overwrites_a_customised_copy_but_never_a_symlink` passes
  even when `skill_status` tests `is_file()` before `is_symlink()` -- the swap
  `## Decisions` calls "reopens exactly that". The test symlinks the project's
  `pipeline-config` copy at `SKILLS_DIR/pipeline-config/SKILL.md`, whose text
  that copy already matches, so the wrong order yields `current`; step 11
  writes no `current` row, and `is_symlink()` still holds. Fix: point the
  symlink at a file whose text differs from the packaged template. The wrong
  order then reads `unknown`, `--force` writes, and the link is gone.

Every other item passes. Root cause: `cmd_init`
(`pipeline/cli/main.py:60-67`) tests `skill.exists()` and never compares
content, and no record separates a customised copy from a stale one; the
manifest fixes that cause. DEC-056, DEC-084 and DEC-098 read as cited and the
plan complies. Every step names files and functions. Riskiest step is 6-7, the
`cmd_init` rewrite; `tests/test_cli.py:487` and `:492` pin the path and the
word `kept`, and `## Rollback` names the revert. Regression surface is `init`
stdout, covered by `tests/test_cli.py:464-493`; no test enumerates
`.project/`. 19 steps over 6 files fits `class: feature`.

Rationale correction, not a scored finding: `install_skill` writes through
`write_atomic`, which `os.replace`s the path, so a refresh would replace a
symlink rather than rewrite the packaged template. `linked` stays sound; the
stated mechanism does not.

### 2026-08-29 08:27:03Z · plan-validation · session · session=4c81e76c-3268-4740-a13e-693557d1dfd7

`plan-validation` ran as session `4c81e76c-3268-4740-a13e-693557d1dfd7`
- replay: `claude --resume 4c81e76c-3268-4740-a13e-693557d1dfd7`
- log: `.project/logs/TICKET-099-plan-validation-4c81e76c.log`
- cost: $1.58 of a $3 cap
- tokens: 16,996 out (8,339 thinking) · 42 in · 1,042,257 cache read · 63,749 cache write

### 2026-08-29 08:27:03Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ one scored finding: the symlink test in step 16 passes even if skill_status tests is_file() before is_symlink(), so no criterion falsifies the ordering the plan calls its own hazard

### 2026-08-29 · planning · plan rewritten after Tier B · result=ok

Tier B's one finding is fixed, and only that. The symlink test was vacuous
because it linked the project's `pipeline-config` copy at the packaged
template, whose text that copy already matched: an `is_file()`-before-
`is_symlink()` `skill_status` read `current`, no refresh path writes a
`current` row, and the link survived the wrong order.

The test now plants the link at `<project>/linked-elsewhere.md`, holding
`# linked elsewhere`. That text differs from the packaged template, so the
wrong order reads `customised`, `skills --refresh --force` writes the row,
`write_atomic`'s `os.replace` replaces the link with a regular file, and the
assertion `--force rewrote a symlinked skill copy` fires. The test is now
steps 16-18: 16 sets it up, 17 asserts, and 18 makes the implementer perform
the branch swap once, watch the test fail, and restore the order. One
acceptance criterion states that swap and its expected failure output.

The plan is 21 steps over the same 6 files; steps 1-15 are unchanged except
for renumbering after 18. `## Decisions` keeps `linked` terminal but states
the mechanism correctly: `write_atomic` replaces the path, so the packaged
template survives a wrong-order refresh and the project's deliberate symlink
does not. Tier B raised that as a rationale correction, not a scored finding.

Baseline unchanged on `5762107`:
`uv run --group dev pytest -q tests/test_cli.py -k skill` prints
`1 failed, 3 passed, 34 deselected in 0.74s`.

### 2026-08-29 08:32:44Z · planning · session · session=ceff6541-d0bd-4ab6-918d-b8a3c9433b77

`planning` ran as session `ceff6541-d0bd-4ab6-918d-b8a3c9433b77`
- replay: `claude --resume ceff6541-d0bd-4ab6-918d-b8a3c9433b77`
- log: `.project/logs/TICKET-099-planning-ceff6541.log`
- cost: $2.18 of a $10 cap
- tokens: 32,651 out (5,067 thinking) · 30 in · 972,026 cache read · 87,547 cache write

### 2026-08-29 08:32:44Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned: the symlink test now links the copy at a file differing from the template, so the is_file()-before-is_symlink() order fails it; 21 steps over 6 files

### 2026-08-29 08:33:21Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update` fails as required
```
y at /tmp/tmp5x66ujb4/.claude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-099/.venv/bin/python', '-m', 'pipeline', ...ept\n  pipeline-config skill already at /tmp/tmp5x66ujb4/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout
E                +  and   "initialised /tmp/tmp5x66ujb4/.project -- edit /tmp/tmp5x66ujb4/.project/pipeline.toml for this project's commands\n  ...KILL.md -- kept\n  pipeline-config skill already at /tmp/tmp5x66ujb4/.claude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-099/.venv/bin/python', '-m', 'pipeline', ...ept\n  pipeline-config skill already at /tmp/tmp5x66ujb4/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout

tests/test_cli.py:514: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.28s ===============================

```
- ok: `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update` fails on base `main` too -- the bug is not already fixed upstream
```
ude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/tmp/pipeline-base-78z9f29v/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmp69...ept\n  pipeline-config skill already at /tmp/tmp69xqz4u1/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout

tests/test_cli.py:514: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.51s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-78z9f29v/base
      Built pipeline @ file:///tmp/pipeline-base-78z9f29v/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 · plan-validation · Tier B · result=fail

**Tier B: fail.** One scored finding.
long: the stage requires reasoning for each of the eight items.

- **Falsifiable criteria: fail.** The mutation step 18 and the fifth
  acceptance criterion prescribe does not change the test's outcome. Step 3
  orders the chain `linked if dst.is_symlink()`, else `absent if not
  dst.is_file()`. Swapping those two branches gives `absent if not
  is_file()`, then `linked if is_symlink()`. `Path.is_file()` follows a
  symlink, and step 16 points the link at `<project>/linked-elsewhere.md`,
  which exists. So `is_file()` is true, the chain falls through to
  `is_symlink()`, and the row still reads `linked`. Step 11 writes no
  `linked` row and the `is_symlink()` assertion holds, so the test passes
  under the swap. Fix: state the mutation as moving the `is_symlink()`
  branch after `current`/`stale`/`customised`/`unknown`, or deleting it.
  That order reads the link as `customised`, `--force` writes it,
  `os.replace` replaces the link, and `--force rewrote a symlinked skill
  copy` fires. Step 16's fixture change is correct and necessary for that
  order. Only the named mutation is wrong.

Every other item passes.

- **Root cause: pass.** `cmd_init` (`pipeline/cli/main.py:60-67`) tests
  `skill.exists()` and never compares content, and no record separates a
  customised copy from a stale one. The manifest fixes that cause.
- **Decision conflict: pass.** DEC-056 reads as cited: "`init` never
  overwrites an existing skill file", and this repo's skill is a symlink.
  DEC-084 reads as cited: "do not add a second file to a skill directory".
  The manifest lives at `.project/skills.json`, outside every skill
  directory. DEC-018, DEC-037, DEC-075 and DEC-098 are files in
  `.project/decisions/`.
- **Scope discipline: pass.** Steps 19-20 trace to the two `grep -c`
  criteria. Step 8 is one branch inside a step the criteria exercise.
- **No research left: pass.** Every step names a file and a function.
- **Riskiest step: pass.** Steps 6-7, the `cmd_init` rewrite.
  `tests/test_cli.py:487` and `:492` pin the path and the word `kept`, and
  `## Rollback` names the revert for each commit group.
- **Regression surface: pass.** `init` stdout, covered by
  `tests/test_cli.py:464-493`. `machine.FENCED` holds only
  `.project/pipeline.toml` and `.project/stages/` under `.project/`, and no
  test enumerates `.project/`.
- **Blast radius: pass.** 21 steps over 6 files fits `class: feature`.

Verified while scoring: `write_atomic` (`pipeline/core/ticket.py:115-120`)
is `tmp.write_text` plus `os.replace`, so a write to a symlinked path
replaces the link and leaves its target untouched. `pipeline/cli/main.py:60`
is the only `SKILLS_DIR` enumeration outside tests. `hashlib`, `json` and
`write_atomic` are imported in `pipeline/core/config.py`. The README phrase
step 19 must keep is at `README.md:79`.

Unverified, and not a finding: I did not execute the swap. I am read-only.
I would have applied the swapped chain to `skill_status` and run
`uv run --group dev pytest -q tests/test_cli.py::test_skills_force_overwrites_a_customised_copy_but_never_a_symlink`.
The finding rests on `Path.is_file()` following symlinks, which the plan's
own digest assumes too when it says the wrong order "read `current`" for the
old fixture.

### 2026-08-29 08:37:11Z · plan-validation · session · session=57d3c0d8-3379-4922-b4af-b7e33351c7c0

`plan-validation` ran as session `57d3c0d8-3379-4922-b4af-b7e33351c7c0`
- replay: `claude --resume 57d3c0d8-3379-4922-b4af-b7e33351c7c0`
- log: `.project/logs/TICKET-099-plan-validation-57d3c0d8.log`
- cost: $1.48 of a $3 cap
- tokens: 17,829 out (8,004 thinking) · 36 in · 877,369 cache read · 59,877 cache write

### 2026-08-29 08:37:11Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ one scored finding: the branch swap step 18 and one acceptance criterion prescribe is a no-op under step 3's own chain, so the symlink test still passes under it

### 2026-08-29 · planning · plan rewritten after the second Tier B · result=ok

Tier B's one finding is fixed, and only that. Step 18 and the fifth acceptance
criterion named a mutation that does not bite. Swapping `skill_status`'s first
two branches gives `absent if not is_file()` then `linked if is_symlink()`;
`Path.is_file()` follows the link to `<project>/linked-elsewhere.md`, which
exists, so the row still reads `linked`, no refresh path writes it, and
`test_skills_force_overwrites_a_customised_copy_but_never_a_symlink` still
passes.

Both now prescribe the mutation Tier B named: move the `linked` branch below
the `current`/`stale`/`customised`/`unknown` branches, so `is_symlink()` is
tested last. That order reads the symlinked `pipeline-config` copy as
`customised`, step 11 writes it under `--force`, `write_atomic`'s `os.replace`
replaces the link with a regular file, and `--force rewrote a symlinked skill
copy` fires. Step 18 carries an indented line telling the implementer not to
substitute the first-two-branch swap, and says why.

Three sentences elsewhere stated the same wrong order and now state the right
one: `## Digest` gotcha 2, the `## Digest` paragraph on what changed, and the
third `## Decisions` paragraph.

The plan is still 21 steps over the same 6 files. Steps 1-17 and 19-21 are
unchanged, as is step 16's fixture, which is what makes the new order
reachable. Baseline unchanged on `5762107`:
`uv run --group dev pytest -q tests/test_cli.py -k skill` prints
`1 failed, 3 passed, 34 deselected in 0.74s`.

### 2026-08-29 08:39:44Z · planning · session · session=7d6da9ca-4e58-4452-b6af-f77a4f69290a

`planning` ran as session `7d6da9ca-4e58-4452-b6af-f77a4f69290a`
- replay: `claude --resume 7d6da9ca-4e58-4452-b6af-f77a4f69290a`
- log: `.project/logs/TICKET-099-planning-7d6da9ca.log`
- cost: $1.43 of a $10 cap
- tokens: 12,540 out (2,795 thinking) · 38 in · 979,521 cache read · 62,841 cache write

### 2026-08-29 08:39:44Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned: step 18 and criterion 5 now prescribe moving the linked branch below the content branches, the mutation that fails the symlink test; 21 steps over 6 files

### 2026-08-29 08:40:21Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update` fails as required
```
y at /tmp/tmp4th0eep0/.claude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-099/.venv/bin/python', '-m', 'pipeline', ...ept\n  pipeline-config skill already at /tmp/tmp4th0eep0/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout
E                +  and   "initialised /tmp/tmp4th0eep0/.project -- edit /tmp/tmp4th0eep0/.project/pipeline.toml for this project's commands\n  ...KILL.md -- kept\n  pipeline-config skill already at /tmp/tmp4th0eep0/.claude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-099/.venv/bin/python', '-m', 'pipeline', ...ept\n  pipeline-config skill already at /tmp/tmp4th0eep0/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout

tests/test_cli.py:514: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.28s ===============================

```
- ok: `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update` fails on base `main` too -- the bug is not already fixed upstream
```
ude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/tmp/pipeline-base-b1e4bbi1/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpta...ept\n  pipeline-config skill already at /tmp/tmptazsnwdw/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout

tests/test_cli.py:514: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.51s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-b1e4bbi1/base
      Built pipeline @ file:///tmp/pipeline-base-b1e4bbi1/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 · plan-validation · Tier B · result=ok

**Tier B: pass.** No scored finding.
long: the stage requires reasoning for each of the eight items.

- **Root cause: pass.** `cmd_init` tests `skill.exists()` at
  `pipeline/cli/main.py:62` and never compares text, and no record separates a
  customised copy from a stale one. The manifest plus `skill_status` fixes
  that cause, not the assertion.
- **Falsifiable criteria: pass.** The mutation step 18 and criterion 5
  prescribe bites. With `linked` below the content branches, the symlinked
  `pipeline-config` copy runs: `is_file()` is true (it follows the link to
  `<project>/linked-elsewhere.md`), the text `# linked elsewhere` differs from
  the template so not `current`, its digest differs from the recorded template
  digest so not `stale`, the name is in marks so `customised`. Step 11 writes
  a `customised` row under `--force`, `os.replace`
  (`pipeline/core/ticket.py:118-120`) replaces the link, and `--force rewrote
  a symlinked skill copy` fires. The two `grep -c` criteria fail today:
  `grep -c "skills --refresh" README.md` prints `0`, and
  `grep -c "skills.json" CLAUDE.md` prints `0`.
- **Decision conflict: pass.** DEC-056 reads verbatim "**`init` never
  overwrites an existing skill file.**" The plan keeps every copy in `init`
  and puts the write in `skills --refresh`, the deliberate re-install that
  record names. DEC-084 requires one `SKILL.md` per skill directory; the
  manifest lives at `.project/skills.json`, outside every skill directory.
  DEC-018, DEC-037, DEC-075 and DEC-098 are files in `.project/decisions/`.
- **Scope discipline: pass.** Steps 19-20 trace to the two `grep -c`
  criteria; steps 1-18 and 21 trace to the pytest criteria.
- **No research left: pass.** Every step names a file and a function, and
  each anchor holds: `SKILLS_DIR` at `pipeline/core/config.py:32`,
  `sync_pins` at `pipeline/core/config.py:181`, `cmd_config` at
  `pipeline/cli/main.py:115`, the `config` subparser row at
  `pipeline/cli/main.py:640`, `cli()` at `tests/test_cli.py:22`. `json` and
  `hashlib` are imported at `pipeline/core/config.py:7-8`, `json` at
  `pipeline/cli/main.py:3`.
- **Riskiest step: pass.** Steps 6-7, which replace `cmd_init`'s output on
  every non-install branch. `tests/test_cli.py:487` asserts the path is in
  stdout and `tests/test_cli.py:492` asserts `kept` is in stdout; all five
  lines in step 7 carry both, gotcha 1 states the constraint, step 9 runs
  `-k skill` before the commit, and `## Rollback` reverts that commit alone.
- **Regression surface: pass.** Three existing tests read this code.
  `test_init_installs_every_packaged_skill` (`tests/test_cli.py:465`): an
  absent copy still installs the template text.
  `test_init_keeps_a_customised_file_ticket_skill` (`tests/test_cli.py:479`):
  `# ours` reads `customised`, and that step 7 line carries the path and
  `kept`. `test_the_docs_name_the_skill_init_installs`
  (`tests/test_stages.py:273`) greps `README.md` for
  "installs `.claude/skills/file-ticket/SKILL.md`" at `README.md:79`, which
  step 19 preserves. No test compares `init` stdout for equality
  (`grep -rn "stdout ==" tests/*.py` finds only git-porcelain compares).
  Gotcha 5 holds: `FENCED` (`pipeline/core/machine.py:43-61`) names
  `.project/pipeline.toml` and `.project/stages/` only, and
  `dirty_snapshot()` excludes `.project` via `':(exclude).project'`.
- **Blast radius: pass.** `class: feature`, 21 steps, 6 files, one new CLI
  command. Proportionate.

Two observations, not findings. Step 8's `current` and `name not in marks`
branch -- the adoption path for a project scaffolded before this change -- is
the one branch no acceptance criterion exercises; every planned test starts
from a fresh `init` that records both skills. Under the step 18 mutation the
`linked` branch sits after `unknown`, which is the terminal `else`, so
`linked` becomes unreachable rather than merely last; the test fails either
way.

`unverified`: I did not execute the step 18 mutation. `skill_status` does not
exist yet, so there was nothing to mutate. The finding above rests on reading
step 3's branch chain against documented `Path.is_file()` symlink semantics
and on `write_atomic` at `pipeline/core/ticket.py:115-120`.

### 2026-08-29 08:43:39Z · plan-validation · session · session=148a24e8-c637-4059-a932-308b93934e4b

`plan-validation` ran as session `148a24e8-c637-4059-a932-308b93934e4b`
- replay: `claude --resume 148a24e8-c637-4059-a932-308b93934e4b`
- log: `.project/logs/TICKET-099-plan-validation-148a24e8.log`
- cost: $1.47 of a $3 cap
- tokens: 15,306 out (5,428 thinking) · 36 in · 902,950 cache read · 63,478 cache write

### 2026-08-29 08:43:39Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B pass: the reordered mutation in step 18 and criterion 5 now bites -- the symlinked copy reads customised, --force writes it, and the is_symlink assertion fires

### 2026-08-29 09:13:28Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified every helper it claims exists: write_atomic at ticket.py:115 and already imported at config.py:19, hashlib and json at config.py:7-8, SKILLS_DIR used only in the loop being replaced. Respects both ticket constraints: a customised or unrecorded copy is never rewritten without --force, and init stays idempotent; it also refuses to write a symlinked copy at all, which is this repo's own layout. Step 8 back-fills a record for an already-current copy so the next template edit reads stale rather than unknown. Step 18 proves the symlink test bites by reordering the branches and explicitly rules out the swap that would not falsify, because is_file follows the link. Nothing fenced -- .project/skills.json is not .project/pipeline.toml.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified every helper it claims exists: write_atomic at ticket.py:115 and already imported at config.py:19, hashlib and json at config.py:7-8, SKILLS_DIR used only in the loop being replaced. Respects both ticket constraints: a customised or unrecorded copy is never rewritten without --force, and init stays idempotent; it also refuses to write a symlinked copy at all, which is this repo's own layout. Step 8 back-fills a record for an already-current copy so the next template edit reads stale rather than unknown. Step 18 proves the symlink test bites by reordering the branches and explicitly rules out the swap that would not falsify, because is_file follows the link. Nothing fenced -- .project/skills.json is not .project/pipeline.toml.**

### 2026-08-29 09:14:05Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update` fails as required
```
y at /tmp/tmptc8c87we/.claude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-099/.venv/bin/python', '-m', 'pipeline', ...ept\n  pipeline-config skill already at /tmp/tmptc8c87we/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout
E                +  and   "initialised /tmp/tmptc8c87we/.project -- edit /tmp/tmptc8c87we/.project/pipeline.toml for this project's commands\n  ...KILL.md -- kept\n  pipeline-config skill already at /tmp/tmptc8c87we/.claude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-099/.venv/bin/python', '-m', 'pipeline', ...ept\n  pipeline-config skill already at /tmp/tmptc8c87we/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout

tests/test_cli.py:514: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.29s ===============================

```
- ok: `tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update` fails on base `main` too -- the bug is not already fixed upstream
```
ude/skills/pipeline-config/SKILL.md -- kept\n" = CompletedProcess(args=['/tmp/pipeline-base-re0f74sx/base/.venv/bin/python', '-m', 'pipeline', '--project', '/tmp/tmpbc...ept\n  pipeline-config skill already at /tmp/tmpbcldaxr5/.claude/skills/pipeline-config/SKILL.md -- kept\n", stderr='').stdout

tests/test_cli.py:514: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.52s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-re0f74sx/base
      Built pipeline @ file:///tmp/pipeline-base-re0f74sx/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```

### 2026-08-29 09:14:06Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-29 · implementing · todo

Working the 21-step plan in order:

1. [x] steps 1-5: manifest helpers in `config.py` + `test_config.py` test, commit 28b8289
2. [x] steps 6-9: rewrite `cmd_init` skill loop to use `skill_status`, commit 7f15d61
3. [x] steps 10-15: `cmd_skills` + subparser + two new cli tests, commit 94a5253
4. [x] steps 16-18: symlink test (in step 3's commit) + branch-order mutation proof (reverted, not committed -- no code change)
5. [x] steps 19-21: README.md + CLAUDE.md + full suite, commit f3751f1

### 2026-08-29 · implementing · done

All 21 steps executed and committed across four commits: 28b8289, 7f15d61,
94a5253, f3751f1. Every pytest acceptance criterion passes, including
`tests/test_cli.py::test_reinit_does_not_detect_a_packaged_skill_update`.
Both `grep -c` criteria print `1`. Full suite: `492 passed`. Guard:
`./pipeline/hooks/test_dangerous_commands.py` exits 0, `guard: all passed`.
Step 18's mutation was verified live by editing, running, and reverting --
no separate commit, since the final code is step 3's original order.

### 2026-08-29 09:19:29Z · implementing · session · session=c9948f5c-40b5-4d18-ad94-5740a9901b3c

`implementing` ran as session `c9948f5c-40b5-4d18-ad94-5740a9901b3c`
- replay: `claude --resume c9948f5c-40b5-4d18-ad94-5740a9901b3c`
- log: `.project/logs/TICKET-099-implementing-c9948f5c.log`
- cost: $1.46 of a $8 cap
- tokens: 19,593 out (1,754 thinking) · 112 in · 4,524,896 cache read · 88,966 cache write

### 2026-08-29 09:19:29Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented all 21 steps; skill manifest, cmd_init reporting, pipeline skills --refresh/--force, docs; full suite and guard pass

### 2026-08-29 · review · findings

**review: fail** -- one blocking finding on the delta `5762107..f3751f1`.

1. **blocking** -- `cmd_skills` installs an `absent` row with no flags, so a
   report command writes. `pipeline/cli/main.py:144` branches on
   `state == "absent"` before it tests `args.refresh`. Plan step 11 scopes
   every write to `--refresh`; step 12 sends every other row to the
   `{name}: {state} at {dst}` print and lists `absent` among the states that
   add no hint. `SKILLS_HINT["absent"]` at `pipeline/cli/main.py:135` is
   unreachable under the shipped order. README (step 19) says `pipeline
   skills` "reports the same states without re-running `init`". Run against
   an empty directory it created four files:
   ```
   $ python -m pipeline --project /tmp/tmpn28_1_mk skills
   file-ticket: installed at /tmp/tmpn28_1_mk/.claude/skills/file-ticket/SKILL.md
   pipeline-config: installed at /tmp/tmpn28_1_mk/.claude/skills/pipeline-config/SKILL.md
   ['.claude/skills/file-ticket/SKILL.md', '.claude/skills/pipeline-config/SKILL.md', '.project/skills.json']
   ```
   Nothing refutes it: `grep -n absent tests/test_cli.py` matches no line, so
   no test asserts the install-without-`--refresh` behaviour.
2. **nit** -- `cmd_init` calls `skill_marks(project)` once per row
   (`pipeline/cli/main.py:79`), re-reading `skills.json` per skill, and
   `skill_status` reads `dst` twice for the `stale` test
   (`pipeline/core/config.py:244`). Neither is wrong.

All 11 acceptance criteria pass. `pytest -q tests/test_cli.py -k skill` plus
the config test print `7 passed, 34 deselected in 1.53s`; full suite
`492 passed in 34.62s`; guard `guard: all passed`; `skills --help` exits 0
with both flags; both `grep -c` print `1`. Criterion 5 checked without
editing the tree, since this stage is read-only: a `skill_status` copy
testing `is_symlink()` last reads the symlinked row `customised`, and
`--refresh --force` through `cmd_skills` left `is_symlink() == False`; the
shipped order reads `linked` and keeps the link.

### 2026-08-29 09:23:25Z · review · session · session=4ad275da-3a0b-4c5b-a0f0-58fc1eb8a0c8

`review` ran as session `4ad275da-3a0b-4c5b-a0f0-58fc1eb8a0c8`
- replay: `claude --resume 4ad275da-3a0b-4c5b-a0f0-58fc1eb8a0c8`
- log: `.project/logs/TICKET-099-review-4ad275da.log`
- cost: $1.42 of a $6 cap
- tokens: 14,919 out (6,686 thinking) · 40 in · 955,443 cache read · 57,265 cache write

### 2026-08-29 09:23:25Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ one blocking finding: `pipeline skills` with no flags installs an absent copy, drift from plan steps 11-12; all 11 acceptance criteria pass

### 2026-08-29 · implementing · fix

Fixed the blocking finding: `pipeline/cli/main.py:143-146` now reads
`if args.refresh and state == "absent":` instead of `if state == "absent":`,
so a no-flag `pipeline skills` falls to the report branch for an `absent`
row and prints `{name}: absent at {dst}` -- `SKILLS_HINT["absent"]` is `""`,
matching plan step 12.

Added `tests/test_cli.py::test_skills_with_no_flags_never_installs_an_absent_copy`.
RED confirmed first: against the unfixed code it printed `file-ticket:
installed at .../SKILL.md` and failed the assertion `'file-ticket: absent'
in stdout`. GREEN after the fix: `uv run --group dev pytest -q
tests/test_cli.py -k skill` -> `7 passed, 34 deselected in 1.64s`. Full
suite `uv run --group dev pytest -q` -> `493 passed in 34.84s` (one more
than review's 492, the new test). Guard `./pipeline/hooks/test_dangerous_commands.py`
-> `guard: all passed`.

Committed as 9136f54 (`pipeline/cli/main.py`, `tests/test_cli.py`). The
review's non-blocking nit (per-row `skill_marks` read, double `dst.read_text()`
in the `stale` branch) is unchanged -- out of scope for a blocking-finding
fix pass.

### 2026-08-29 09:25:07Z · implementing · session · session=0a25b8ca-fd5e-4a9c-bf76-880f5729b573

`implementing` ran as session `0a25b8ca-fd5e-4a9c-bf76-880f5729b573`
- replay: `claude --resume 0a25b8ca-fd5e-4a9c-bf76-880f5729b573`
- log: `.project/logs/TICKET-099-implementing-0a25b8ca.log`
- cost: $0.43 of a $8 cap
- tokens: 4,797 out (42 thinking) · 40 in · 974,797 cache read · 45,953 cache write

### 2026-08-29 09:25:07Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ fixed cmd_skills to only install an absent row under --refresh, added a no-flags-on-empty-project test, full suite and guard pass

### 2026-08-29 · review · findings

**review: ok** -- no blocking findings on the delta `f3751f1..9136f54`
(`pipeline/cli/main.py | 2 +-`, `tests/test_cli.py | 17 +++`).

The previous blocking finding is resolved. `pipeline/cli/main.py:144` now
reads `if args.refresh and state == "absent":`, so a no-flag row falls to the
report branch and `SKILLS_HINT["absent"]` at `pipeline/cli/main.py:135` is
reachable. Verified both paths against `/tmp/t099rev`, an empty directory:
`skills --refresh` printed `file-ticket: installed at
/tmp/t099rev/.claude/skills/file-ticket/SKILL.md` and created three files;
the following no-flag `skills` printed `file-ticket: current at ...` and
exited 0.

`pipeline/core/config.py` is unchanged in this delta, so `skill_status`'s
`is_symlink()`-first order and criterion 5 stand as checked last pass.

Non-blocking:

1. **nit** -- no test covers the `--refresh` install of an `absent` row, the
   branch this delta edited. I exercised it by hand (above); the suite does
   not.
2. **nit** -- the previous entry's nit is unchanged: `cmd_init` reads
   `skills.json` once per row (`pipeline/cli/main.py:79`) and `skill_status`
   reads `dst` twice for the `stale` test (`pipeline/core/config.py:244`).

All 11 acceptance criteria pass: `pytest -q tests/test_cli.py -k skill` with
`tests/test_config.py` prints `8 passed, 60 deselected in 1.64s`; full suite
`493 passed in 34.94s`; guard `guard: all passed`; `skills --help` exits 0
with both flags; both `grep -c` print `1`. The guard blocked my `rm`, so the
scratch directory `/tmp/t099rev` is left behind; it is outside the worktree.

### 2026-08-29 09:27:36Z · review · session · session=8b879f06-6054-4b3e-9316-1db84534dc66

`review` ran as session `8b879f06-6054-4b3e-9316-1db84534dc66`
- replay: `claude --resume 8b879f06-6054-4b3e-9316-1db84534dc66`
- log: `.project/logs/TICKET-099-review-8b879f06.log`
- cost: $1.01 of a $6 cap
- tokens: 7,850 out (2,560 thinking) · 38 in · 756,331 cache read · 43,221 cache write

### 2026-08-29 09:27:36Z · review · transition · to=holistic-review · result=ok · marker=yes

**review -> holistic-review** (result: `ok`)

✓ delta f3751f1..9136f54 clean: the absent-install finding is fixed and tested; full suite 493 passed, guard all passed

### 2026-08-29 · holistic-review · findings

**holistic-review: ok** -- the whole diff `main...9136f54` is coherent
(6 files, `262 insertions(+), 15 deletions(-)`).

The sum matches the plan. Every plan step landed in one place: the manifest
and the six states in `pipeline/core/config.py`, the reporting loop and
`cmd_skills` in `pipeline/cli/main.py`, the four tests, and the two doc
edits. Nothing landed that no acceptance criterion asked for.

No fix undid an earlier one. 9136f54 changed one line inside `cmd_skills`
(`if args.refresh and state == "absent":`); `cmd_init`'s own `absent` install
is untouched, so `init` still scaffolds and `skills` with no flags still
reports. `pipeline/core/config.py` has one commit on this branch (28b8289),
so the `is_symlink()`-first order the decisions require is the order the
first review checked.

Error handling did not drift across iterations. `skill_marks` is the one
tolerant reader (`except (OSError, ValueError): return {}`); `install_skill`
and `skill_status` let an OSError propagate, exactly as the loop they
replaced did with `skill.write_text`. `cmd_skills` refuses a bad flag pair
through `die()`, like every other command in the file.

Docs match the code: `pipeline skills` is not named in either packaged
`SKILL.md`, and neither documents `init`'s copy states, so no skill drifted.

Re-ran here: `uv run --group dev pytest -q` -> `493 passed in 34.96s`;
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`;
`skills --help` matched `--refresh`/`--force` on 3 lines; both `grep -c`
print `1`. I did not re-run criterion 5's mutation: it edits
`pipeline/core/config.py`, and this stage is read-only.

### 2026-08-29 09:30:15Z · holistic-review · session · session=5289ee5b-2ca5-497b-a5ef-2b9d6a391531

`holistic-review` ran as session `5289ee5b-2ca5-497b-a5ef-2b9d6a391531`
- replay: `claude --resume 5289ee5b-2ca5-497b-a5ef-2b9d6a391531`
- log: `.project/logs/TICKET-099-holistic-review-5289ee5b.log`
- cost: $1.12 of a $6 cap
- tokens: 8,203 out (2,923 thinking) · 34 in · 734,184 cache read · 54,482 cache write

### 2026-08-29 09:30:15Z · holistic-review · transition · to=verifying · result=ok · marker=yes

**holistic-review -> verifying** (result: `ok`)

✓ whole diff main...9136f54 is coherent: one manifest-backed state model, the fix undid nothing, docs match the code

### 2026-08-29 09:30:52Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 09:30:53Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/099


Current branch ticket/099 is up to date.
Already up to date.
Updating aaeb09b..9136f54
Fast-forward
 CLAUDE.md               |   5 +++
 README.md               |   7 ++++
 pipeline/cli/main.py    |  68 ++++++++++++++++++++++++++------
 pipeline/core/config.py |  70 ++++++++++++++++++++++++++++++++
 tests/test_cli.py       | 103 ++++++++++++++++++++++++++++++++++++++++++++++++
 tests/test_config.py    |  24 +++++++++--
 6 files changed, 262 insertions(+), 15 deletions(-)

```

### 2026-08-29 09:30:53Z · merging · decision

decision recorded as `DEC-099`
