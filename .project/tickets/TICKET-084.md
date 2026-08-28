---
id: TICKET-084
stage: done
class: feature
branch: ticket/084
test_file: tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads
files_declared:
- pipeline/templates/pipeline.toml
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_stages.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 8
  plan_files: 3
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 9e397ccf-a80d-43be-badf-a3fc16d2316b
  log: .project/logs/TICKET-084-review-9e397ccf.log
approved_by: 'chezzijr (via Claude Code, while away; reviewer also filed this ticket
  -- audit in thread). Verified SKILL.md anchors: line 3 is the description, 112-113
  the git-ignored sentences, 118-122 the ''rest of the file'' section. The reproduction
  test is on the branch and asserts all five knobs. It answered the setup-vs-reference
  question by keeping one file with the setup path first and a reference half last,
  rather than splitting the skill.'
approved_at: '2026-08-28T09:10:57.508786+00:00'
---

## Summary

`pipeline/templates/skills/pipeline-config/SKILL.md` (122 lines) documents the
config's three test commands but names none of `max_usd`, `scale_usd`,
`worktree_setup`, `.project/stages/<name>.extra.md` or `pinned`. Triage
confirmed the gap and committed the failing test named in `## Reproduction`.

Planning answered the ticket's design question: one file, not a skill plus a
reference file, because `cmd_init()` copies exactly `<skill>/SKILL.md` per skill
directory, so a second file never reaches a scaffolded project. The setup path
stays first; a new `## Every other key` section goes last, and the frontmatter
`description` gains the budget-cap and cross-worktree-build triggers.

`## Plan` has 8 steps over three files:
`pipeline/templates/skills/pipeline-config/SKILL.md`,
`pipeline/templates/pipeline.toml` (which never mentioned `worktree_setup`) and
`tests/test_stages.py`.

Plan validation passed both tiers. Tier B verified every code claim the plan
rests on: `cmd_init()` at `pipeline/cli/main.py:60-66` copies only
`<skill>/SKILL.md`; the `max_usd` defaults quoted in step 4 match the stage
frontmatter; `worktree_setup` is read at `pipeline/core/worktree.py:61` and
`:92` and appears nowhere in `pipeline/templates/pipeline.toml`. The quoted line
ranges (`SKILL.md` 112-113 and 118-122, `pipeline.toml` 45) are the text the
plan says they are.

Implementing executed all 8 plan steps with no deviation and committed at
`79950b3`. The reproduction test and the new
`test_the_config_template_documents_worktree_setup` both pass;
`tests/test_stages.py tests/test_cli.py` is `64 passed`. Every acceptance
criterion checked directly: 5 distinct knobs in the skill, one
`# worktree_setup` comment line in `pipeline.toml`, the skill directory holds
only `SKILL.md`, the repo symlink unchanged.

Review passed with no blocking findings. It re-ran the acceptance criteria (`64
passed`) and checked each prose claim against the code: the seven `max_usd`
defaults, `budget_kills` and its escalation, `cap_for()`/`cap_config()`, both
`worktree_setup` call sites, the `.extra.md` append position, `FENCED`, and
`cmd_config`'s `source:  pinned` line. Three minor notes stand, none of them
work for this ticket: the pin path ignores `$XDG_CONFIG_HOME`; the closing
section claims the template's comments carry `effort`, `write`, `tools`,
`hooks` and `permission_mode`, which they do not (the pre-change text delegated
the same keys, so it is not a regression); and the `.extra.md` example uses
`git add` under a `# read from HEAD` comment.

Out of scope, unchanged: `init` copying a skill rather than updating a stale one.

## Reproduction

Test: `tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads`
Command: `uv run --group dev pytest -q tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads`
Committed on `ticket/084` at `162e007`.

Failure output:
```
AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-084/pipeline/templates/skills/pipeline-config/SKILL.md does not mention 'max_usd'
assert 'max_usd' in "---\nname: pipeline-config\ndescription: Set up or fix this project's .project/pipeline.toml for the agent pipeline. ...f `.project/pipeline.toml` itself. Read them there\nrather than inventing keys — an unknown key is silently ignored.\n"
```
expect: does not mention 'max_usd'

Confirmed by direct read: `grep -n "max_usd\|scale_usd\|worktree_setup\|extra.md\|pinned" pipeline/templates/skills/pipeline-config/SKILL.md` returns nothing, against a 122-line file.

## Digest

Files this change touches: `pipeline/templates/skills/pipeline-config/SKILL.md`
(122 lines, 6134 bytes), `pipeline/templates/pipeline.toml` (78 lines),
`tests/test_stages.py`.

Entry point that decides the split question: `cmd_init()` at
`pipeline/cli/main.py:60` loops `SKILLS_DIR` and copies exactly
`<skill>/SKILL.md` per directory. A second file beside `SKILL.md` never reaches
a scaffolded project, so a `reference.md` split would ship a skill pointing at
a path that is not there. One file it stays; see `## Decisions`.

`.claude/skills/pipeline-config/SKILL.md` is a relative symlink to the packaged
file (`../../../pipeline/templates/skills/pipeline-config/SKILL.md`, DEC-056),
so the packaged file is the only edit.

Code that reads each of the five knobs:

- `max_usd`: `stage_cap()` at `pipeline/core/config.py:479` reads
  `cfg.get("max_usd", hcfg.get("max_usd", 5))`. `cfg` is `stage_config()` --
  packaged frontmatter merged shallow with `[stages.<name>]`. Packaged values:
  `quick-review` 2, `triage` 3, `plan-validation` 3, `review` 4,
  `holistic-review` 4, `planning` 5, `implementing` 8; `claude-code.toml`
  carries 5.
- `scale_usd`: `cap_config()` at `pipeline/core/config.py:71-81` and `cap_for()`
  at `pipeline/core/machine.py:92`. `USD_SCALED = {"review", "quick-review",
  "holistic-review"}`, `USD_FILES_PER_DOLLAR = 4`, `USD_STEPS_PER_DOLLAR = 8`,
  `USD_CEILING_FACTOR = 2`.
- `worktree_setup`: `ensure_worktree()` at `pipeline/core/worktree.py:61` and
  `base_checkout()` at `pipeline/core/worktree.py:92`. The shared-cache hazard
  is `README.md:341-359`.
- `.project/stages/<name>.extra.md`: `stage_extra()` at
  `pipeline/core/config.py:408` (HEAD, then pin, then disk), appended by
  `compose_prompt()` at `pipeline/core/config.py:447`.
- `pinned`: `project_config()` at `pipeline/core/config.py:152-154`,
  `config_source()` at `:163`, `sync_pins()` at `:173`, and `cmd_config()` at
  `pipeline/cli/main.py:113-130`, which prints `source:  pinned` and warns when
  the working tree differs from the pin.

Gotchas:

- `max_usd` and `scale_usd` are read ONLY under `[stages.<name>]`; a top-level
  `max_usd` is ignored. `worktree_setup` is the opposite: top level, under no
  table.
- `pipeline/templates/pipeline.toml` never mentions `worktree_setup`, so the
  skill's closing line ("documented in the comments of `.project/pipeline.toml`
  itself") is false for that one knob today.
- `pipeline/templates/pipeline.toml` is NOT in `machine.FENCED`; this repo's own
  `.project/pipeline.toml` is. Neither file this ticket touches is fenced.
- The pipeline guard refuses any Bash command containing a backslash. Every
  command below is written without one.
- Tests already reading these two files:
  `test_the_config_docs_name_every_test_placeholder` (both must keep `{path}`
  and `{name}`), `test_the_repo_skill_is_the_packaged_file` (symlink, under
  128 KB), and `tests/test_cli.py::test_init_installs_every_packaged_skill`
  (byte equality after `init`).

## Decisions checked

Grepped `/home/chezzijr/proj/agent-pipeline/.project/decisions/` for
`pipeline-config`, `worktree_setup`, `scale_usd`, `max_usd`, `pinned`,
`extra.md`, `skill`, `SKILL`.

- DEC-056 -- the repo skill is a symlink to the packaged copy, and `init` never
  overwrites an existing skill file. This plan edits the packaged file only.
- DEC-078 -- a project's `max_usd` pins the cap unless the table also sets
  `scale_usd = true`; `scale_usd = false` opts a scaled stage out. The new skill
  text states exactly this.
- DEC-038 -- `[stages.<name>]` is merged shallow and unclamped; the prose half
  (`.extra.md`) is append-only because it has no frontmatter to clamp.
- DEC-075 -- a config git will never have is pinned under
  `config_dir()/pinned/<hash>/`, and `pipeline config --sync` is the only way to
  adopt a later edit.
- DEC-069 -- `max_parallel` lowers `-j` and never raises it. Consulted for the
  key list; the skill keeps delegating this key to the template comments.

None of these five carries a `superseded-by:` line. The only superseded records
in that directory are DEC-041, DEC-042 and DEC-050, none of them cited here.
This plan contradicts no active record, so `## Decisions` opens no `supersedes:`
line.

## Plan

1. Run `uv run --group dev pytest -q tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads` and confirm the red from `tests/test_stages.py`: `AssertionError: ...SKILL.md does not mention 'max_usd'`.
2. In `pipeline/templates/skills/pipeline-config/SKILL.md`, line 3, extend the frontmatter `description` so the skill also loads on the reference triggers -- insert this immediately after `"the pipeline can't run my tests"` and before the closing period:

       , when a stage was killed at its budget cap, when builds interfere across ticket worktrees, or when the user asks which keys `.project/pipeline.toml` takes

3. In `pipeline/templates/skills/pipeline-config/SKILL.md`, replace the two sentences at lines 112-113 (from `If ` + backtick + `.project/` through `and say so to the operator.`) with this paragraph, which names the pin:

       If `.project/` is git-ignored here (`pipeline init --private`) there is
       nothing to commit. The dispatcher pinned a copy outside the repo on
       first read, under `~/.config/pipeline/pinned/<hash of the project
       path>/`, and every later edit stays inert until you run
       `pipeline config --sync`. `pipeline config` prints `source:  pinned`
       and warns when the working tree differs from the pin. Say both to the
       operator.

4. In `pipeline/templates/skills/pipeline-config/SKILL.md`, replace the whole final section (lines 118-122, `## The rest of the file` and its paragraph) with this reference half, kept last so the setup path stays first:

       ## Every other key

       `test_one`, `test_suite`, `test_suite_without_new` and `base` are the
       only keys this file needs. The rest are optional. These five are the
       ones an operator reaches for, and the file's own comments do not carry
       them all.

       ### `[stages.<name>] max_usd` -- the per-stage dollar cap

       Every stage spawns under a dollar cap. A stage killed at it escalates
       the ticket naming the cap, and nothing retries into the same spend.
       That is the lever for "the stage ran out of budget":

       ```toml
       [stages.planning]
       max_usd = 10
       ```

       Then `pipeline resume TICKET-066 --stage planning --reset budget_kills`.
       Defaults come from the stage's own file: `quick-review` 2, `triage` 3,
       `plan-validation` 3, `review` 4, `holistic-review` 4, `planning` 5,
       `implementing` 8. A `max_usd` here PINS the cap -- see `scale_usd`.
       Only `[stages.<name>] max_usd` is read; a top-level one is ignored.

       ### `[stages.<name>] scale_usd` -- opt in to size-scaled caps

       `review`, `quick-review` and `holistic-review` grow their cap by one
       dollar per 4 declared files or per 8 plan steps, whichever is larger,
       capped at twice the stage's own number. Your `max_usd` pins the cap and
       is never scaled past unless you also set `scale_usd = true`;
       `scale_usd = false` turns scaling off for a stage that scales by
       default.

       ```toml
       [stages.review]
       max_usd   = 6      # 6 flat; with the next line, 6 to 12 by plan size
       scale_usd = true
       ```

       ### `worktree_setup` -- one command per new checkout

       Top level, under no table. It runs in every worktree the dispatcher
       creates, after `git worktree add` and before the first stage, and in
       the throwaway checkout of `base` the gate re-runs `test_one` in. Copy
       an env file, install dependencies, key a build cache:

       ```toml
       worktree_setup = "cp ../../.env . && npm ci --prefer-offline"
       ```

       **Key any build cache per checkout.** Every ticket gets its own
       worktree. `ln -s ~/.cache/cargo-target target` points them all at one
       directory, and one ticket's stale artifact is then served into
       another's build: a test goes red for a reason that is not in that
       ticket's diff, and clears only when the source is touched. Use
       `CARGO_TARGET_DIR=~/.cache/cargo/$(basename $PWD)`, a `ccache` prefix
       per branch, or leave the cache unshared.

       ### `.project/stages/<name>.extra.md` -- prose for one stage

       A file, not a key. Its text is appended after the packaged stage prompt
       and before the ticket view, so it adds instructions and can never relax
       one: there is no frontmatter in it to override a setting with. Settings
       go in `[stages.<name>]`; wording goes here.

       ```sh
       mkdir -p .project/stages
       echo 'Run `make lint` before every commit.' > .project/stages/implementing.extra.md
       git add .project/stages/implementing.extra.md   # read from HEAD, like the config
       ```

       `.project/stages/` is fenced, so a committed change parks the ticket at
       `awaiting-merge` for a human to read.

       ### Still in the file's own comments

       The other `[stages.<name>]` keys (`model`, `effort`, `write`, `tools`,
       `hooks`, `permission_mode`, `skills`), `[mcp.<name>]`,
       `[readonly] allow` and `max_parallel` are documented in the comments of
       `.project/pipeline.toml` itself. Read them there rather than inventing
       keys -- an unknown key is silently ignored.

5. Run `uv run --group dev pytest -q "tests/test_stages.py" -k "config_skill or config_docs or repo_skill"` and expect exit 0 with `3 passed`: the reproduction in `tests/test_stages.py` is green and neither neighbouring skill test broke.
6. Append this test to `tests/test_stages.py`, directly after `test_the_config_skill_names_every_knob_the_code_reads`, then run `uv run --group dev pytest -q tests/test_stages.py::test_the_config_template_documents_worktree_setup` and expect `does not document worktree_setup`:

       def test_the_config_template_documents_worktree_setup():
           """TICKET-084: the skill delegates the keys it does not spell out
           to the comments of `.project/pipeline.toml`. `worktree_setup` was
           in neither file, so a session had no route to it at all."""
           text = C.CONFIG_TEMPLATE.read_text()
           assert "worktree_setup" in text, (
               f"{C.CONFIG_TEMPLATE} does not document worktree_setup")

7. Add this comment block to `pipeline/templates/pipeline.toml` between the `max_parallel` block (ends line 45) and the `[stages.<name>]` block (starts line 47), then re-run step 6's command and expect `1 passed`:

       # One command run in every worktree the dispatcher creates, after
       # `git worktree add` and before the first stage, and in the throwaway
       # checkout of `base` the gate re-runs a ticket's test in.
       # worktree_setup = "cp ../../.env . && npm ci --prefer-offline"
       #
       # A build cache shared across worktrees UNKEYED serves one ticket's
       # stale artifact into another ticket's build -- a test goes red for a
       # reason that is not in that ticket's diff. Key it per checkout
       # (CARGO_TARGET_DIR=~/.cache/cargo/$(basename $PWD), a ccache prefix
       # per branch) or leave it unshared.

8. Run `uv run --group dev pytest -q tests/test_stages.py tests/test_cli.py`, expect exit 0, then commit `pipeline/templates/skills/pipeline-config/SKILL.md`, `pipeline/templates/pipeline.toml` and `tests/test_stages.py` as `docs(TICKET-084): the pipeline-config skill names max_usd, scale_usd, worktree_setup, .extra.md and pinned`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads`
  exits 0 and prints `1 passed`.
- `uv run --group dev pytest -q tests/test_stages.py::test_the_config_template_documents_worktree_setup`
  exits 0 and prints `1 passed`.
- `grep -coE "max_usd|scale_usd|worktree_setup|extra[.]md|pinned" pipeline/templates/skills/pipeline-config/SKILL.md`
  prints a number of 5 or more, and
  `grep -oE "max_usd|scale_usd|worktree_setup|extra[.]md|pinned" pipeline/templates/skills/pipeline-config/SKILL.md | sort -u | wc -l`
  prints `5`.
- `grep -c "^# worktree_setup" pipeline/templates/pipeline.toml` prints `1`.
- `ls pipeline/templates/skills/pipeline-config/` prints `SKILL.md` and nothing
  else, so `cmd_init()` still ships the whole skill.
- `readlink .claude/skills/pipeline-config/SKILL.md` prints
  `../../../pipeline/templates/skills/pipeline-config/SKILL.md`.
- `uv run --group dev pytest -q tests/test_stages.py tests/test_cli.py` exits 0
  and its summary line contains no `failed`. Re-measure the same two files at
  `162e007` if the count is disputed: this change must move only the
  reproduction test from failing to passing and add one new passing test.

## Decisions

**One `SKILL.md`, not a skill plus a reference file.** The skill serves two jobs
-- set up a project's three test commands, and list every key the code reads --
and they stay in one file because `cmd_init()` (`pipeline/cli/main.py:60`)
copies exactly `<skill>/SKILL.md` per directory under `SKILLS_DIR`. A
`reference.md` beside it would never reach a scaffolded project, and the shipped
`SKILL.md` would point at a path that is not there. The two jobs are separated
by position instead: the trigger path (the three commands, the traps, the proof
script) stays first, the reference half is the last section. If `init` ever
copies a skill directory whole, the split becomes available; until then, do not
add a second file to a skill directory.

**The skill's `description` carries both jobs' triggers.** That frontmatter line
is the only thing deciding whether a session opens this file, so a reference
half nobody loads is not documentation. The budget-cap and cross-worktree-build
wording is in it deliberately -- do not trim the description back to
test-command setup while the reference half is in the file.

**A knob the template's comments do not carry must be spelled out in the
skill.** The skill's last section delegates the remaining keys to the comments
in `.project/pipeline.toml`, so a key in neither place is unreachable;
`worktree_setup` was exactly that.
`tests/test_stages.py::test_the_config_template_documents_worktree_setup` keeps
the delegation honest for that key.

**`max_usd` and `scale_usd` are documented under `[stages.<name>]` only.**
`stage_cap()` reads them off the merged stage config, never off the top level,
so a top-level `max_usd` is one of the silently ignored keys.

## Rollback

Revert the commit, or restore both files from `162e007`:
`git checkout 162e007 -- pipeline/templates/skills/pipeline-config/SKILL.md pipeline/templates/pipeline.toml`,
and delete `test_the_config_template_documents_worktree_setup` from
`tests/test_stages.py`. No executable path changes: the packaged skill and the
config template are data, read by `cmd_init()` and by humans. Projects already
scaffolded keep their own copies either way (DEC-056), so a revert cannot break
a running project; a project scaffolded after the revert gets the old skill
bytes back.

## Thread

### 2026-08-28 08:59:24Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-28 · triage · result=ok

Confirmed the gap by grep: `max_usd`, `scale_usd`, `worktree_setup`, `extra.md`,
`pinned` all absent from `pipeline/templates/skills/pipeline-config/SKILL.md`
(122 lines).

Added `tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads`,
which asserts each of the five knob names appears in the skill text. It fails
first on `max_usd` with:
`AssertionError: ...SKILL.md does not mention 'max_usd'`.
Committed on `ticket/084` at `162e007`.

result: ok. Not `chore`: the ticket itself raises an open design question
(split the skill into setup-trigger vs. reference, or justify one file) that
planning must answer before the fix is a few-line edit.

### 2026-08-28 09:01:01Z · triage · session · session=ad1d0cdb-9f5b-479d-89af-48e9785fdf4f

`triage` ran as session `ad1d0cdb-9f5b-479d-89af-48e9785fdf4f`
- replay: `claude --resume ad1d0cdb-9f5b-479d-89af-48e9785fdf4f`
- log: `.project/logs/TICKET-084-triage-ad1d0cdb.log`

### 2026-08-28 09:01:01Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced with tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads, failing on max_usd first


### 2026-08-28 · planning · result=ok

Plan written: 8 steps over three files
(`pipeline/templates/skills/pipeline-config/SKILL.md`,
`pipeline/templates/pipeline.toml`, `tests/test_stages.py`).

Answered the ticket's design question in `## Decisions`: one `SKILL.md`, not a
skill plus a reference file. `cmd_init()` (`pipeline/cli/main.py:60`) copies
exactly `<skill>/SKILL.md` per skill directory, so a `reference.md` beside it
would never reach a scaffolded project and the shipped skill would point at a
missing path. The two jobs are split by position instead: setup path first,
reference section last, `description` widened so the reference half loads at
all.

One thing found outside this stage's job: `pipeline/templates/pipeline.toml` has
no `worktree_setup` comment, so the skill's closing "documented in the comments
of `.project/pipeline.toml` itself" was false for that knob. Step 7 adds the
comment and step 6 adds the test that holds it, because the skill's own promise
depends on it.

Gotcha for implementing: the pipeline guard rejects any Bash command containing
a backslash ("it contains a backslash, which this guard refuses rather than
models"). Every command in `## Plan` and `## Acceptance criteria` is written
without one.

### 2026-08-28 09:07:31Z · planning · session · session=2637ad16-da0b-4fd8-a5b3-0b69dfd2c90d

`planning` ran as session `2637ad16-da0b-4fd8-a5b3-0b69dfd2c90d`
- replay: `claude --resume 2637ad16-da0b-4fd8-a5b3-0b69dfd2c90d`
- log: `.project/logs/TICKET-084-planning-2637ad16.log`

### 2026-08-28 09:07:31Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ 8-step plan: the pipeline-config skill gains a reference half naming max_usd, scale_usd, worktree_setup, .extra.md and pinned; stays one file because init copies only SKILL.md

### 2026-08-28 09:07:54Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads` fails as required
```
in[39;49;00m text, [33mf[39;49;00m[33m"[39;49;00m[33m{[39;49;00mskill[33m}[39;49;00m[33m does not mention [39;49;00m[33m{[39;49;00mknob[33m!r}[39;49;00m[33m"[39;49;00m[90m[39;49;00m
[1m[31mE           AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-084/pipeline/templates/skills/pipeline-config/SKILL.md does not mention 'max_usd'[0m
[1m[31mE           assert 'max_usd' in "---\nname: pipeline-config\ndescription: Set up or fix this project's .project/pipeline.toml for the agent pipeline. ...f `.project/pipeline.toml` itself. Read them there\nrather than inventing keys — an unknown key is silently ignored.\n"[0m

[1m[31mtests/test_stages.py[0m:395: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_stages.py::[1mtest_the_config_skill_names_every_knob_the_code_reads[0m - AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-084/pi...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.04s[0m[31m ===============================[0m

```
- ok: `tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads` fails on base `main` too -- the bug is not already fixed upstream
```
_stages.py[0m:395: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_stages.py::[1mtest_the_config_skill_names_every_knob_the_code_reads[0m - AssertionError: /tmp/pipeline-base-hqthunvk/base/pipeline/templates/skills/...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-hqthunvk/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-hqthunvk/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- ok: DEC-041 is superseded -- history, not binding
- ok: DEC-042 is superseded -- history, not binding
- ok: DEC-050 is superseded -- history, not binding

### 2026-08-28 · plan-validation · result=ok

Tier B PASS. Eight items, each verified against the code.

- Root cause: the skill's last section delegates every key it does not spell
  out to the comments of `.project/pipeline.toml`, so a key in neither file is
  unreachable. Steps 4 and 7 fix both halves; the plan does not just insert the
  five strings the test greps for.
- Decision conflict: none. DEC-078 matches `cap_config()` at
  `pipeline/core/config.py:73-79`; DEC-056 holds, `ls` shows `SKILL.md` alone.
- Scope: 8 steps, all traceable. Steps 6-7 trace to criterion 2 and 4.
- Falsifiable: criterion 3's `sort -u | wc -l` prints `5` only if all five knobs
  land; criterion 5 fails if a `reference.md` is added.
- No research left: every step names a file and line range. Verified lines
  112-113 and 118-122 of `SKILL.md` are the text quoted, and line 45 of
  `pipeline/templates/pipeline.toml` is `# max_parallel = 1`.
- Riskiest step: 4, the largest rewrite. Fallback is `## Rollback`.
- Regression surface: `test_the_config_docs_name_every_test_placeholder`,
  `test_the_repo_skill_is_the_packaged_file` (128 KB limit; the file is 6134
  bytes) and `tests/test_cli.py::test_init_installs_every_packaged_skill`.
  Step 5's `-k` selects exactly 3 tests, so `3 passed` is right.
- Blast radius: 3 files, class `feature`. Fits.

Checked the plan's numbers: `max_usd` defaults quoted in step 4 match the stage
frontmatter exactly (`quick-review` 2, `triage` 3, `plan-validation` 3, `review`
4, `holistic-review` 4, `planning` 5, `implementing` 8).

One nit for implementing, not a finding: step 3 writes the pin path as
`~/.config/pipeline/pinned/...`, but `config_dir()` honours `$XDG_CONFIG_HOME`
first. Say "your pipeline config directory" or keep it as the common case.

unverified: none. The guard blocked `sed`; `head`, `tail` and `grep` covered
every read.

### 2026-08-28 09:10:00Z · plan-validation · session · session=04628e41-740b-4bec-9257-db01967245d6

`plan-validation` ran as session `04628e41-740b-4bec-9257-db01967245d6`
- replay: `claude --resume 04628e41-740b-4bec-9257-db01967245d6`
- log: `.project/logs/TICKET-084-plan-validation-04628e41.log`

### 2026-08-28 09:10:00Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan-validation PASS: all 8 items pass; every code claim in the plan verified against main.py:60, config.py and worktree.py

### 2026-08-28 09:10:57Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Verified SKILL.md anchors: line 3 is the description, 112-113 the git-ignored sentences, 118-122 the 'rest of the file' section. The reproduction test is on the branch and asserts all five knobs. It answered the setup-vs-reference question by keeping one file with the setup path first and a reference half last, rather than splitting the skill.

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Verified SKILL.md anchors: line 3 is the description, 112-113 the git-ignored sentences, 118-122 the 'rest of the file' section. The reproduction test is on the branch and asserts all five knobs. It answered the setup-vs-reference question by keeping one file with the setup path first and a reference half last, rather than splitting the skill.**

### 2026-08-28 09:11:20Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads` fails as required
```
in[39;49;00m text, [33mf[39;49;00m[33m"[39;49;00m[33m{[39;49;00mskill[33m}[39;49;00m[33m does not mention [39;49;00m[33m{[39;49;00mknob[33m!r}[39;49;00m[33m"[39;49;00m[90m[39;49;00m
[1m[31mE           AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-084/pipeline/templates/skills/pipeline-config/SKILL.md does not mention 'max_usd'[0m
[1m[31mE           assert 'max_usd' in "---\nname: pipeline-config\ndescription: Set up or fix this project's .project/pipeline.toml for the agent pipeline. ...f `.project/pipeline.toml` itself. Read them there\nrather than inventing keys — an unknown key is silently ignored.\n"[0m

[1m[31mtests/test_stages.py[0m:395: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_stages.py::[1mtest_the_config_skill_names_every_knob_the_code_reads[0m - AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-084/pi...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.05s[0m[31m ===============================[0m

```
- ok: `tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads` fails on base `main` too -- the bug is not already fixed upstream
```
_stages.py[0m:395: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_stages.py::[1mtest_the_config_skill_names_every_knob_the_code_reads[0m - AssertionError: /tmp/pipeline-base-q34c590v/base/pipeline/templates/skills/...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.10s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-q34c590v/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-q34c590v/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- ok: DEC-041 is superseded -- history, not binding
- ok: DEC-042 is superseded -- history, not binding
- ok: DEC-050 is superseded -- history, not binding

### 2026-08-28 09:11:21Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-28 · implementing · result=ok

Todo (all done):
1. Confirm red on `test_the_config_skill_names_every_knob_the_code_reads` -- done.
2. Widen `description` in SKILL.md with the budget-cap and cross-worktree triggers -- done.
3. Rewrite the git-ignored sentences (lines 112-113) to name the pin path -- done.
4. Replace `## The rest of the file` with `## Every other key`, the five-knob reference section -- done.
5. Run the 3-test `-k config_skill or config_docs or repo_skill` check -- `3 passed`.
6. Add `test_the_config_template_documents_worktree_setup`, confirm it fails on `worktree_setup` -- done.
7. Add the `worktree_setup` comment block to `pipeline/templates/pipeline.toml` -- done, new test now `1 passed`.
8. Run `tests/test_stages.py tests/test_cli.py` full, commit -- `64 passed`, committed at `79950b3`.

All 8 plan steps executed as written, no deviation. Acceptance criteria checked directly:
`grep -coE` count is 18 (>=5 required); distinct-knob count is `5`; `grep -c "^# worktree_setup"` on `pipeline.toml` is `1`; `ls pipeline/templates/skills/pipeline-config/` prints only `SKILL.md`; `readlink .claude/skills/pipeline-config/SKILL.md` prints `../../../pipeline/templates/skills/pipeline-config/SKILL.md`.

No blockers, no deviation from the plan.

### 2026-08-28 09:13:39Z · implementing · session · session=9801957f-509c-4ff3-bcef-81755ad7e413

`implementing` ran as session `9801957f-509c-4ff3-bcef-81755ad7e413`
- replay: `claude --resume 9801957f-509c-4ff3-bcef-81755ad7e413`
- log: `.project/logs/TICKET-084-implementing-9801957f.log`

### 2026-08-28 09:13:39Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ plan executed; skill names all 5 knobs, pipeline.toml documents worktree_setup, new test passes, 64/64 pass

### 2026-08-28 · review · result=ok

Reviewed the delta `45af30b..79950b3`: `SKILL.md` +87/-7, `pipeline.toml` +11,
`tests/test_stages.py` +9. First review pass, no earlier findings to clear.

Checked every code claim the new prose makes. The seven `max_usd` defaults match
the stage files. `budget_kills` is written at `pipeline/daemon/supervisor.py:1093`
and that escalation names the cap; `cmd_resume` accepts `--reset budget_kills`.
`cap_for()` (`machine.py:100-102`) adds `max(steps//8, files//4)` capped at
`2 * base`, and `cap_config()` (`config.py:75-81`) pins on `max_usd` unless
`scale_usd = true`. `worktree_setup` runs after `git worktree add`
(`worktree.py:73`) and in the gate's base checkout (`worktree.py:126`,
`gate.py:284`). `.extra.md` is appended after the stage body and before the
ticket view (`config.py:445-451`). `.project/stages/` is in `FENCED`
(`machine.py:60`). `cmd_config` prints `source:  pinned` and the pin-differs
warning (`cli/main.py:120-126`).

Every acceptance criterion passes: `64 passed`, `grep -coE` 18, distinct knobs
`5`, `^# worktree_setup` 1, only `SKILL.md` in the skill directory, symlink
unchanged. Both new tests print `1 passed` run alone.

No blocking findings. Three non-blocking notes:

1. Minor. `SKILL.md:114` writes the pin as `~/.config/pipeline/pinned/...`;
   `config_dir()` honours `$XDG_CONFIG_HOME` first. Implementing noted this too.
2. Minor. `SKILL.md:197-201` says `effort`, `write`, `tools`, `hooks` and
   `permission_mode` are documented in the template's comments. That block
   (`pipeline/templates/pipeline.toml:58-64`) names only `model`, `skills` and
   `scale_usd`. The pre-change text delegated the same keys as a group, so this
   is not a regression.
3. Minor. `SKILL.md:190` comments `git add ...extra.md` with `# read from HEAD,
   like the config`. A staged file is not in HEAD; the prose still reaches the
   stage through the disk fallback at `config.py:425-426`.

### 2026-08-28 09:17:05Z · review · session · session=9e397ccf-a80d-43be-badf-a3fc16d2316b

`review` ran as session `9e397ccf-a80d-43be-badf-a3fc16d2316b`
- replay: `claude --resume 9e397ccf-a80d-43be-badf-a3fc16d2316b`
- log: `.project/logs/TICKET-084-review-9e397ccf.log`

### 2026-08-28 09:17:05Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review PASS: every prose claim checked against code; 64 passed; 3 non-blocking notes

### 2026-08-28 09:17:27Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-28 09:17:28Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/084


Current branch ticket/084 is up to date.
Already up to date.
Updating 45af30b..79950b3
Fast-forward
 pipeline/templates/pipeline.toml                   | 11 +++
 pipeline/templates/skills/pipeline-config/SKILL.md | 94 ++++++++++++++++++++--
 tests/test_stages.py                               | 21 +++++
 3 files changed, 119 insertions(+), 7 deletions(-)

```

### 2026-08-28 09:17:28Z · merging · decision

decision recorded as `DEC-084`
