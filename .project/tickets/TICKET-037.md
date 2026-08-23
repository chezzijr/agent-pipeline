---
id: TICKET-037
stage: done
class: bugfix
branch: ticket/037
test_file: tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/config.py
- pipeline/core/fence.py
- pipeline/core/machine.py
- pipeline/core/worktree.py
- pipeline/templates/pipeline.toml
- tests/test_config.py
- tests/test_fence.py
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
  id: 79aa0641-57e8-4f0d-9fe7-42dd9f887109
  log: .project/logs/TICKET-037-review-79aa0641.log
approved_by: chezzijr
approved_at: '2026-08-23T16:34:22.536277+00:00'
---

## Summary

Implemented and reviewed; review pass 1 found nothing blocking.

`project_config()` (`pipeline/core/config.py`) now reads
`.project/pipeline.toml` via `head_file()` (new, `pipeline/core/worktree.py`)
-- `git show HEAD:./.project/pipeline.toml` in the main checkout -- and falls
back to disk only when git has no copy (fresh `pipeline init`, or
`.project/` excluded from git). `.project/pipeline.toml` is added to
`machine.FENCED` as a whole-file entry, so a committed edit parks at
`awaiting-merge`; `CLAUDE.md`'s fence sentence and gotcha bullet, `fence.py`'s
docstring and `tests/test_machine.py` are updated to match.

All 11 plan steps done, 4 commits (`9ef9ccc`, `5904adf`, `223cc16`, `e4277d1`).
The committed failing test now passes:
`tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config`.
Two new fallback tests and one new `head_file()` test and one new fence test
were added per the plan; TDD followed (RED verified before each GREEN).
Full suite: `uv run --group dev pytest -q` -- 232 passed, no collateral.
Guard: `./pipeline/hooks/test_dangerous_commands.py` exits 0.

**Deviation from the literal plan text, step 8 only:** between planning and
implementing, an unrelated already-merged ticket (`bdf24aa`) added
`pipeline/harnesses/claude-code.toml` to `machine.FENCED` and to the CLAUDE.md
fence sentence. The plan's step 8 quote for the new sentence, written before
that merge, omits `claude-code.toml`. Copying it verbatim would have silently
dropped that entry from the prose, breaking
`test_the_fenced_list_matches_the_rule_file` (prose must equal `FENCED`,
flattened). Kept `claude-code.toml` in the sentence alongside the new
`.project/pipeline.toml`; verified the test passes. No other step needed this
adjustment. Review accepted that deviation: `test_stages.py` compares the
CLAUDE.md prose to `FENCED` in both directions, so the literal plan text would
have failed.

**Review (pass 1, no blocking findings).** Re-ran the suite: `232 passed in
10.31s`. Two non-blocking findings are in `## Thread`: (1) `project_config()`
on a missing project directory now raises `FileNotFoundError` instead of
`PipelineError`, which only `pipeline gate --project <typo>` can reach; (2)
`head_file()` returns `""` for a committed empty file. Review could not run
`./pipeline/hooks/test_dangerous_commands.py` -- the guard blocks it from a
read-only stage -- and the delta touches no file in `pipeline/hooks/`.

## Reproduction

Test: `tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config`
Command: `uv run --group dev pytest -q tests/test_config.py`
Commit: 6b75188 on `ticket/037`.

Failure output:

    AssertionError: assert 'true' == 'pytest -x {test}'

      - pytest -x {test}
      + true

expect: assert 'true' == 'pytest -x {test}'

The test commits `.project/pipeline.toml` with `test_one="pytest -x {test}"`,
reads it once via `project_config()`, overwrites the file uncommitted with
`test_one="true"`, and reads again. `project_config()` returns the
uncommitted `'true'` where it must return the committed
`'pytest -x {test}'`, confirming the ticket's claim.

## Digest

Files touched (11): `pipeline/core/worktree.py` (new `head_file()`),
`pipeline/core/config.py` (`project_config()`), `pipeline/core/machine.py`
(`FENCED`), `pipeline/core/fence.py` (docstring count), `CLAUDE.md` (the fence
sentence and the `.project/` gotcha bullet), `README.md`,
`pipeline/templates/pipeline.toml`, `tests/test_config.py`,
`tests/test_worktree.py`, `tests/test_fence.py`, `tests/test_machine.py`.

Key functions: `project_config(project)` is the only reader of
`.project/pipeline.toml`. `fenced_touches(wt, base, fenced=FENCED)`
(`pipeline/core/fence.py:64`) is the fence check. `run_cmd()`
(`pipeline/core/worktree.py:25`) is unusable for this read: it returns
`(stdout + stderr)[-4000:]`, which merges git's stderr into the config text and
truncates a long file. `pipeline/core/fence.py` already takes that same
exception and calls `subprocess.run(..., env=project_env())` directly, so
`head_file()` follows it rather than inventing a pattern.

Entry points: every `project_config()` call site passes the **main checkout**,
never a worktree -- `pipeline/core/gate.py:93` (`gate()` takes `workdir`
separately), `pipeline/daemon/supervisor.py:140` (the `done` record commit),
`pipeline/daemon/supervisor.py:574` (`start()`) and
`pipeline/daemon/supervisor.py:708` (`base_ref(project_config(project))`).
That answers the question triage left open.

Gotchas:
- `git show HEAD:./<rel>` resolves the path relative to cwd. Verified 2026-08-23 in a throwaway repo with the project in `sub/`: it printed the committed value while the working tree held a different one. A path absent from HEAD exits 128 with `fatal: path 'sub/nope.toml' does not exist in 'HEAD'`.
- `tests/helpers.py::git_project()` writes `.project/pipeline.toml` **after** its only commit, so the file is untracked there. `tests/test_dispatch.py:108`, `:281` and `:545` rewrite that config and depend on it being read. They keep working only through the disk fallback; a fallback narrowed to "no HEAD at all" breaks them.
- `tests/test_gate.py::_git_ticket_project` does commit the config (line 51), but the gate tests that rewrite it (lines 116, 154, 165, 177, 194) all use `tests/helpers.py::project()`, which is not a git repo. They are unaffected.
- `machine.FENCED` is read from the **main checkout's** module while the dispatcher runs, so the entry this ticket adds does not fence this ticket's own diff. Nothing else here touches a fenced symbol: the `machine.py` hunk lands on `FENCED` (lines 18-23), not on `transition` (line 34) or `CONTROL_FIELDS` (line 161). This diff needs the human review `CLAUDE.md` demands and the pipeline will not stop for it.
- `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` extracts the backticked tokens from the CLAUDE.md paragraph that ends at "requires human review before merge" and compares them to `FENCED`. Adding a `FENCED` entry without editing that sentence fails it.
- `.claude/skills/file-ticket/SKILL.md:156` and `README.md:255` defer to `CLAUDE.md` generically ("anything `CLAUDE.md` fences off"), so neither needs the new path spelled out.
- No test in this repo uses `pytest.raises`. The house style for an expected raise is `try:` / `assert False, "..."` / `except PipelineError`.

## Decisions checked

Grepped `/home/chezzijr/proj/agent-pipeline/.project/decisions/` for: pipeline.toml,
project_config, config, `git show`, HEAD, tree_snapshot, read-only, readonly,
allowlist, snapshot, FENCED, base, superseded-by. No record carries a
`superseded-by:` line, so all five cited below are active constraints.

- DEC-031 -- the fence parks on a positive-`clean`-only polarity, and "the fence matches symbols, not whole files" because every stage-adding ticket edits `machine.py`. A whole-file entry for `.project/pipeline.toml` does not contradict that reasoning: no ticket has a legitimate reason to edit the dispatcher's own config, so parking every one is the intent rather than collateral. DEC-031 also fixes how the CLAUDE.md fence sentence must be written (one paragraph, every item backticked); step 8 follows it.
- DEC-034 -- "the guard is defended by the dispatcher, not by a flag". The same shape applies here: the guard's `matcher` is `Bash` and cannot see an `Edit`, so the defence belongs where the value is read, not where the write happens.
- DEC-017 -- `base_ref(cfg)` is the single default for `base`, so the gate and the ticket's checkout cannot drift. This plan changes where `cfg` comes from, not that rule; `base_ref()` is untouched.
- DEC-029 -- `rec["base"]` is carried from the spawn to the reap so a config edited mid-run cannot move the recut's target. The HEAD read makes that case unreachable rather than merely defended; the plan does not remove the carry.
- DEC-011 -- per-project settings stay in `.project/pipeline.toml` (the registry holds only paths). Unchanged.

## Plan

1. Add this test to `tests/test_worktree.py` (that file already has `from pipeline.core import worktree as W`, `from helpers import git_project`, `import tempfile` and `from pathlib import Path`):

       def test_head_file_reads_the_commit_not_the_working_tree():
           """The dispatcher's own config is read through this. An uncommitted edit
           to a tracked file must be invisible, and a file git does not have must
           read as None so the caller can fall back to disk."""
           d, sh = git_project()
           (d / "f.py").write_text("dirty\n")
           assert W.head_file(d, "f.py") == "base\n"
           assert W.head_file(d, ".project/pipeline.toml") is None   # never committed
           sh("git add -A && git commit -qm commit-config")
           assert 'test_one="true"' in W.head_file(d, ".project/pipeline.toml")
           assert W.head_file(Path(tempfile.mkdtemp()), "f.py") is None  # not a repo

   Run `uv run --group dev pytest -q tests/test_worktree.py` and see it fail with `AttributeError: module 'pipeline.core.worktree' has no attribute 'head_file'`.
2. Add `head_file()` to `pipeline/core/worktree.py`, directly above `tree_snapshot()` (`shlex`, `subprocess` and `Path` are already imported there):

       def head_file(project: Path, rel: str) -> str | None:
           """The content of `rel` at `project`'s HEAD commit, or None if git has none.

           None means git could not answer -- not a repo, no commit yet, or the
           path is untracked -- and the caller falls back to the working tree.
           `HEAD:./<rel>` resolves relative to cwd, so a project inside a
           subdirectory of its repo reads its own copy.

           Not `run_cmd()`: that returns `(stdout + stderr)[-4000:]`, which would
           merge git's stderr into the file and truncate a long one.
           """
           p = subprocess.run(f"git show {shlex.quote('HEAD:./' + rel)}", shell=True,
                              cwd=project, capture_output=True, text=True,
                              errors="replace", env=project_env())
           return p.stdout if p.returncode == 0 else None

   Run `uv run --group dev pytest -q tests/test_worktree.py`, see it pass, and commit as `feat: read a file out of HEAD without run_cmd's truncation`.
3. Add both fallback tests to `tests/test_config.py`, which already has `from pipeline.core.config import project_config` and `from tests.helpers import git_project` (add `import tempfile`, `from pathlib import Path` and `from pipeline.core import PipelineError`):

       def test_project_config_falls_back_to_disk_when_git_has_no_copy():
           """A freshly `pipeline init`-ed project has not committed `.project/`,
           and `pipeline init --private` never will. Both must still run."""
           d, _ = git_project()          # writes the config AFTER its only commit
           assert project_config(d)["test_one"] == "true"
           plain = Path(tempfile.mkdtemp())
           (plain / ".project").mkdir()
           (plain / ".project" / "pipeline.toml").write_text('test_one="from-disk"\n')
           assert project_config(plain)["test_one"] == "from-disk"   # not a repo

       def test_project_config_still_raises_when_there_is_no_config_anywhere():
           d, _ = git_project()
           (d / ".project" / "pipeline.toml").unlink()
           try:
               project_config(d)
               assert False, "a project with no config must raise"
           except PipelineError as e:
               assert "run `pipeline init" in str(e)

   Run `uv run --group dev pytest -q tests/test_config.py` and expect `2 passed, 1 failed`: both new tests pass against the current disk read, while the committed test still fails with `assert 'true' == 'pytest -x {test}'`. They guard step 4's fallback; they are not a red-to-green pair.
4. Replace `project_config()` in `pipeline/core/config.py` with the body below, and add `from pipeline.core.worktree import head_file` to its imports (`pipeline/core/worktree.py` imports nothing from `pipeline`, so there is no cycle):

       def project_config(project: Path) -> dict:
           """The project's config as HEAD has it, not as the working tree has it.

           Every stage can write the main checkout's `.project/` -- it is where the
           ticket file lives, and `tree_snapshot()` excludes it -- and the guard's
           `matcher` is `Bash`, so it never sees an `Edit`. Reading off disk let any
           stage rewrite `test_one`, `test_suite` and `base`, the commands Tier A,
           `verifying` and `merging` trust. Read from HEAD, an uncommitted edit is
           inert, and a committed one is in the ticket's diff, where `review` sees
           it and `machine.FENCED` parks it at `awaiting-merge`.

           The disk fallback covers a project whose config git does not have:
           freshly `pipeline init`-ed and not yet committed, or `.project/` excluded
           from git (`pipeline init --private`). A ticket branch cannot reach it --
           only a commit on the main checkout can take the file out of HEAD.
           """
           text = head_file(project, ".project/pipeline.toml")
           if text is None:
               cfg = project / ".project" / "pipeline.toml"
               if not cfg.is_file():
                   raise PipelineError(f"no {cfg} -- run `pipeline init {project}` first")
               text = cfg.read_text()
           return tomllib.loads(text)

   Run `uv run --group dev pytest -q tests/test_config.py` and expect `3 passed`.
5. Run the whole suite for collateral -- `uv run --group dev pytest -q` -- and expect no new failures: the tests at risk are the ones that rewrite a config `pipeline/core/config.py` now reads through HEAD, namely `tests/test_dispatch.py:108`, `:281`, `:545` and `tests/test_gate.py`, and all of them stay green through the disk fallback (see `## Digest`). Commit steps 3-5 as `fix: read pipeline.toml from HEAD, not the working tree`.
6. Add this test to `tests/test_fence.py`, which already has `from pipeline.core.fence import fenced_touches` and `from tests.helpers import git_project`:

       def test_a_change_to_the_committed_config_trips_the_fence():
           """`.project/pipeline.toml` names the commands Tier A and `verifying`
           trust, so a ticket that edits it stops for a human. This one calls
           `fenced_touches` with the real `FENCED`, not the module-level fake."""
           d, sh = git_project()
           sh("git add -A && git commit -qm commit-config")
           assert fenced_touches(d, "main") == []
           (d / ".project" / "pipeline.toml").write_text('test_one="true"\n')
           assert fenced_touches(d, "main") == [".project/pipeline.toml"]

   Run `uv run --group dev pytest -q tests/test_fence.py` and see it fail with `assert [] == ['.project/pipeline.toml']`.
7. Add `".project/pipeline.toml": None,` as the first entry of `FENCED` in `pipeline/core/machine.py`, and change the comment above it from "The four things" to "The six things" (the count was already stale at five); run `uv run --group dev pytest -q tests/test_fence.py tests/test_stages.py` and expect `tests/test_fence.py` green with `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` failing on `CLAUDE.md says {...}, machine.FENCED says {...}`.
8. Edit the fence sentence in `CLAUDE.md` (line 205) to read "But a change to `pipeline/hooks/dangerous-commands.py`, `transition()`, `validate_meta()`, `CONTROL_FIELDS`, `strip_settings_sources()` or `.project/pipeline.toml` **requires human review before merge**, whatever the pipeline says." -- one paragraph, every item backticked, per DEC-031 -- then run `uv run --group dev pytest -q tests/test_stages.py -k fenced_list` and expect `1 passed`.
9. Change "fences five things" to "fences six things" in the module docstring of `pipeline/core/fence.py` (line 3), and in `tests/test_machine.py` (line 55) change "fences five things" to "fences six things" and add `` `.project/pipeline.toml` `` to the list that docstring spells out; run `uv run --group dev pytest -q tests/test_machine.py tests/test_fence.py tests/test_stages.py` and expect all passed. Commit steps 6-9 as `fix: fence .project/pipeline.toml against unattended merge`.
10. Rewrite the `.project/` gotcha bullet in `CLAUDE.md` (the one that today ends "the guard's allowlist is what stops it") to read: "**`.project/` is excluded from the read-only tree snapshot**, because writing to the ticket is every stage's job. That leaves `.project/pipeline.toml` writable by every stage, `Write` and `Edit` included -- the guard's `matcher` is `Bash` and never sees one. `project_config()` therefore reads it from the main checkout's HEAD (`git show HEAD:./.project/pipeline.toml`), so an uncommitted edit is inert; it falls back to disk only when git has no copy at all. A committed edit lands in the ticket's diff, and `.project/pipeline.toml` is in `machine.FENCED`, so it parks at `awaiting-merge`." -- the bullet sits far above the fence paragraph, so `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` still reads the right sentence; re-run `uv run --group dev pytest -q tests/test_stages.py` and expect all passed.
11. Document the operator-visible change in `pipeline/templates/pipeline.toml` and `README.md`: append to the template's header comment the three lines "# The dispatcher reads this file from git HEAD, so an edit to a committed", "# config takes effect once it is committed. A config git does not have --" and "# not yet committed, or excluded by `init --private` -- is read from disk."; then add one sentence to `README.md` immediately after the `## Use` code block: "Once `.project/` is committed, `pipeline.toml` is read from git `HEAD`, so an edit takes effect at the next commit -- a ticket working on a branch must not be able to change the commands that judge it. Until it is committed (and under `--private`, which never commits it) the file on disk is read as-is." Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect the suite green and the guard script to exit 0, and commit as `docs: pipeline.toml is read from HEAD`.

## Acceptance criteria

- `tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config` passes: the committed `'pytest -x {test}'` survives an uncommitted overwrite with `'true'`.
- `tests/test_config.py::test_project_config_falls_back_to_disk_when_git_has_no_copy` passes: an untracked config and a non-git directory each still configure a project.
- `tests/test_config.py::test_project_config_still_raises_when_there_is_no_config_anywhere` passes: nothing on disk and nothing in HEAD still raises `PipelineError`.
- `tests/test_worktree.py::test_head_file_reads_the_commit_not_the_working_tree` passes: HEAD content for a tracked file, `None` for an untracked one and for a non-repo.
- `tests/test_fence.py::test_a_change_to_the_committed_config_trips_the_fence` passes: an edit to a committed `.project/pipeline.toml` returns `[".project/pipeline.toml"]`.
- `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` passes: `CLAUDE.md` and `machine.FENCED` name the same six things.
- `uv run --group dev pytest -q` reports no failures, and `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

**The dispatcher reads its own config from HEAD, and the working tree is not
consulted when HEAD has a copy.** `.project/` is excluded from
`tree_snapshot()` because writing the ticket is every stage's job, and the
guard's `matcher` is `Bash`, so a `Write` or `Edit` of `.project/pipeline.toml`
passes both. Reading off disk therefore let any stage -- read-only ones
included -- rewrite `test_one`, `test_suite` and `base`, the commands Tier A,
`verifying` and `merging` trust. A ticket works on a branch, so it must not be
able to change the config that judges it. Do not answer a stale-config
complaint by reading the working tree again; the answer is to commit the
config.

**The disk fallback is scoped to "git has no copy", and that is deliberate.**
`head_file()` returns `None` for a non-repo, for a repo with no commit, and for
an untracked path; `project_config()` then reads disk. A narrower fallback --
only when HEAD does not exist -- breaks every test built on
`tests/helpers.py::git_project()`, which writes the config after its only
commit, and breaks `pipeline init --private`. The fallback is not reachable
from a ticket branch: taking the file out of the main checkout's HEAD needs a
commit on the main checkout, which is what `machine.FENCED` and the
`awaiting-merge` gate cover.

**Residual: a project that keeps `.project/` out of git is not protected.**
`pipeline init --private` writes `.git/info/exclude`, so the config is never in
HEAD and the disk read is permanent there. Hardening that case needs a copy of
the config the ticket cannot reach -- outside the repo, or in the registry --
and this ticket does not build one.

**`.project/pipeline.toml` is fenced whole-file, not by symbol.** DEC-031 chose
symbol matching so an ordinary stage-adding ticket does not park on
`machine.py`. The reasoning inverts here: no ticket has a legitimate reason to
edit the dispatcher's own config, so every such diff should stop for a human.
It is also not Python, so `symbol_lines()` has nothing to match.

**`head_file()` does not use `run_cmd()`.** `run_cmd()` returns
`(stdout + stderr)[-4000:]`. Both halves are wrong for reading a file: git's
stderr would be parsed as TOML, and a config over 4000 bytes would be truncated
into a different config. `pipeline/core/fence.py` already calls
`subprocess.run(..., env=project_env())` for the same reason. `project_env()`
still applies, so the dispatcher's venv cannot shadow the project's git.

## Rollback

Revert in one piece: `git revert` the four commits, or reset the branch to its
merge base. Nothing outside `pipeline/core/`, `tests/` and the docs changes.

The load-bearing commit is step 4's `pipeline/core/config.py`. Reverting that
one function to `tomllib.loads(cfg.read_text())` restores the old behaviour
completely; `head_file()` is then unused and inert, and the `FENCED` entry only
costs an extra human gate.

What is not a reason to roll back: an operator reporting that an edit to
`.project/pipeline.toml` "did nothing". That is the fix working -- tell them to
commit it. Roll back only if a project reads a stale config **after**
committing the change, which would mean `head_file()` read the wrong checkout.

Removing the `.project/pipeline.toml` entry from `machine.FENCED` on its own
restores unattended merge for a config change. Do not do that without also
reverting `pipeline/core/config.py`; the two are one defence.

## Thread

### 2026-08-23 14:21:54Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-23 14:22:10Z · triage · note

`triage` was interrupted; lease released

### 2026-08-23 · triage · note

Reproduced. Added a failing test, see `## Reproduction`. Result: `ok`, not
`chore` -- the fix touches `machine.FENCED` and `pipeline/core/config.py`'s
`HEAD`-read/fallback logic, both of which need a design decision, and
`machine.FENCED` changes require human review per this repo's own CLAUDE.md.
Likely touches: `pipeline/core/config.py` (`project_config()`),
`pipeline/core/machine.py` (`FENCED`), and possibly
`tests/test_stages.py::test_the_fenced_list_matches_the_rule_file`'s
counterpart doc paragraph. Not investigated further: how `HEAD` is read when
`project` is a worktree vs. the main checkout -- planning should confirm
which checkout `project_config()` receives at each call site.

### 2026-08-23 14:25:56Z · triage · session · session=b4edec72-970d-42c8-85dc-e9abd91468b1

`triage` ran as session `b4edec72-970d-42c8-85dc-e9abd91468b1`
- replay: `claude --resume b4edec72-970d-42c8-85dc-e9abd91468b1`
- log: `.project/logs/TICKET-037-triage-b4edec72.log`

### 2026-08-23 14:25:56Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced with a failing test showing project_config() returns the uncommitted value instead of HEAD's.

### 2026-08-23 · planning · note

Plan written: 11 steps, 11 files.

Design: `head_file()` in `pipeline/core/worktree.py` runs
`git show HEAD:./.project/pipeline.toml` in the main checkout, and
`project_config()` falls back to disk only when git returns nothing.
`.project/pipeline.toml` joins `machine.FENCED` whole-file.

Answered triage's open question: every `project_config()` call site passes the
main checkout, never a worktree -- `pipeline/core/gate.py:93`,
`pipeline/daemon/supervisor.py:140`, `:574` and `:708`.

Two findings outside this ticket's scope, not fixed here:
1. `FENCED` itself is not a fenced symbol in `pipeline/core/machine.py`, so a ticket that deletes an entry from it does not park at `awaiting-merge`.
2. `pipeline/harnesses/claude-code.toml` holds the trusted `cmd` template and is not fenced either. TICKET-034's thread already recorded that one.

Residual recorded in `## Decisions`: a project that excludes `.project/` from
git (`pipeline init --private`) has no committed config, keeps the disk read,
and is not protected by this fix.

### 2026-08-23 14:36:47Z · planning · session · session=ed8a0c26-8439-43cd-b7e8-e1c80de8054b

`planning` ran as session `ed8a0c26-8439-43cd-b7e8-e1c80de8054b`
- replay: `claude --resume ed8a0c26-8439-43cd-b7e8-e1c80de8054b`
- log: `.project/logs/TICKET-037-planning-ed8a0c26.log`

### 2026-08-23 14:36:47Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned the HEAD read (head_file + project_config fallback) and the .project/pipeline.toml FENCED entry: 11 steps, 11 files, 6 named tests.

### 2026-08-23 14:38:17Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config` fails as required
```
t_change_project_config ___

    def test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config():
        d, sh = git_project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one="pytest -x {test}"\ntest_suite="true"\n'
            'test_suite_without_new="true"\nbase="main"\n')
        sh("git add -A && git commit -qm init-config")
    
        committed = project_config(d)["test_one"]
        assert committed == "pytest -x {test}"
    
        (d / ".project" / "pipeline.toml").write_text(
            'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\nbase="main"\n')
    
>       assert project_config(d)["test_one"] == committed
E       AssertionError: assert 'true' == 'pytest -x {test}'
E         
E         - pytest -x {test}
E         + true

tests/test_config.py:20: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config` fails on base `main` too -- the bug is not already fixed upstream
```
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\nbase="main"\n')
    
>       assert project_config(d)["test_one"] == committed
E       AssertionError: assert 'true' == 'pytest -x {test}'
E         
E         - pytest -x {test}
E         + true

tests/test_config.py:20: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-co57sxmy/base
      Built pipeline @ file:///tmp/pipeline-base-co57sxmy/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-23 · plan-validation · note

Plan validated: pass on all eight items.

- Root cause: `project_config()` reads the file a stage can write. `.project/`
  is outside `tree_snapshot()` and the guard's `matcher` is `Bash`, so a
  `Write` or `Edit` of `test_one` is invisible to both. The plan moves the read
  to the main checkout's HEAD, which a ticket branch cannot reach. It fixes the
  trust boundary, not the assertion.
- Decisions: DEC-031 scopes symbol matching to `machine.py`'s stage-adding
  churn, so a whole-file entry for a non-Python config does not conflict. Its
  "one paragraph, every item backticked" rule binds step 8, which follows it.
  DEC-034, DEC-017, DEC-029 and DEC-011 are unaffected.
- Scope: steps 9-11 (the "five things" counts, the `.project/` gotcha bullet,
  `README.md`, the template) trace to no single criterion. They stop rule files
  this repo tests from stating a behaviour that no longer exists. Kept.
- Criteria: six named tests with stated inputs. Each fails on a wrong
  implementation.
- Riskiest step: 4. `## Rollback` names it and gives the one-function revert.
- Regression surface: checked `tests/test_dispatch.py:108`, `:281`, `:545`,
  `tests/test_gate.py:116`, `:154`, `:165`, `:177`, `:194` and
  `tests/test_daemon.py:775`. Each project is non-git or has an untracked
  config, so each reads the disk fallback.
- Blast radius: 3 source files, 4 test files, 4 docs. Proportionate to `bugfix`.

Verified in this checkout: `git show HEAD:./.project/pipeline.toml` prints the
committed config, and `git show HEAD:./nope.toml` exits 128 with
`fatal: path 'nope.toml' does not exist in 'HEAD'`. This repo tracks
`.project/pipeline.toml`, so the HEAD read is live here after merge.

### 2026-08-23 14:42:35Z · plan-validation · session · session=211c7d26-8c45-4fb1-a33c-c02489ee1734

`plan-validation` ran as session `211c7d26-8c45-4fb1-a33c-c02489ee1734`
- replay: `claude --resume 211c7d26-8c45-4fb1-a33c-c02489ee1734`
- log: `.project/logs/TICKET-037-plan-validation-211c7d26.log`

### 2026-08-23 14:42:35Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight items: HEAD read fixes the trust boundary, disk fallback keeps every config-rewriting test green, 11 files proportionate to bugfix.

### 2026-08-23 16:34:22Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-23 16:37:13Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config` fails as required
```
t_change_project_config ___

    def test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config():
        d, sh = git_project()
        (d / ".project" / "pipeline.toml").write_text(
            'test_one="pytest -x {test}"\ntest_suite="true"\n'
            'test_suite_without_new="true"\nbase="main"\n')
        sh("git add -A && git commit -qm init-config")
    
        committed = project_config(d)["test_one"]
        assert committed == "pytest -x {test}"
    
        (d / ".project" / "pipeline.toml").write_text(
            'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\nbase="main"\n')
    
>       assert project_config(d)["test_one"] == committed
E       AssertionError: assert 'true' == 'pytest -x {test}'
E         
E         - pytest -x {test}
E         + true

tests/test_config.py:20: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config` fails on base `main` too -- the bug is not already fixed upstream
```
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\nbase="main"\n')
    
>       assert project_config(d)["test_one"] == committed
E       AssertionError: assert 'true' == 'pytest -x {test}'
E         
E         - pytest -x {test}
E         + true

tests/test_config.py:20: AssertionError
=========================== short test summary info ============================
FAILED tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-xp80bv96/base
      Built pipeline @ file:///tmp/pipeline-base-xp80bv96/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-23 16:37:13Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-23 · implementing · todo

**implementing todo** (11 plan steps)

1. [x] `tests/test_worktree.py::test_head_file_reads_the_commit_not_the_working_tree` (RED)
2. [x] `head_file()` in `pipeline/core/worktree.py`; commit
3. [x] fallback tests in `tests/test_config.py`
4. [x] `project_config()` reads HEAD via `head_file()`; commit steps 3-5
5. [x] full suite for collateral
6. [x] `tests/test_fence.py::test_a_change_to_the_committed_config_trips_the_fence` (RED)
7. [x] add `.project/pipeline.toml` to `machine.FENCED`
8. [x] `CLAUDE.md` fence sentence (kept `claude-code.toml` too, see note below)
9. [x] "five things" -> "six things" in `fence.py` docstring and `tests/test_machine.py`; commit steps 6-9
10. [x] `.project/` gotcha bullet in `CLAUDE.md`
11. [x] `pipeline/templates/pipeline.toml` header + `README.md` sentence; commit

### 2026-08-23 · implementing · note

All 11 steps done, TDD followed throughout (RED verified before each GREEN).
4 commits: `9ef9ccc` (`head_file()`), `5904adf` (`project_config()` HEAD read),
`223cc16` (FENCED entry + docs), `e4277d1` (template + README).

Step 8 deviated from the plan's literal sentence text: an unrelated
already-merged commit (`bdf24aa`, landed before this branch's `revalidating`
rebase) had added `pipeline/harnesses/claude-code.toml` to both
`machine.FENCED` and the CLAUDE.md fence sentence. The plan's step 8 quote,
written before that merge, omits `claude-code.toml`. Writing it verbatim would
have dropped that entry from the prose and failed
`test_the_fenced_list_matches_the_rule_file` (prose must equal `FENCED`,
flattened, in both directions). Kept `claude-code.toml` in the sentence
alongside the new `.project/pipeline.toml`. Verified:
`uv run --group dev pytest -q tests/test_stages.py -k fenced_list` -> 1 passed.

All acceptance criteria verified:
- `tests/test_config.py::test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config` passes.
- `tests/test_config.py::test_project_config_falls_back_to_disk_when_git_has_no_copy` passes.
- `tests/test_config.py::test_project_config_still_raises_when_there_is_no_config_anywhere` passes.
- `tests/test_worktree.py::test_head_file_reads_the_commit_not_the_working_tree` passes.
- `tests/test_fence.py::test_a_change_to_the_committed_config_trips_the_fence` passes.
- `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` passes.
- `uv run --group dev pytest -q` -> `232 passed`, no collateral failures.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.

Result: `ok`.

### 2026-08-23 16:42:02Z · implementing · session · session=59bb06a3-3de0-4ec9-ae09-6a4dadd3cdff

`implementing` ran as session `59bb06a3-3de0-4ec9-ae09-6a4dadd3cdff`
- replay: `claude --resume 59bb06a3-3de0-4ec9-ae09-6a4dadd3cdff`
- log: `.project/logs/TICKET-037-implementing-59bb06a3.log`

### 2026-08-23 16:42:02Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented all 11 plan steps (HEAD-read config, fence entry, docs); test passes, 232-test suite and guard clean; step 8 kept claude-code.toml in the fence sentence to match FENCED after an intervening merge

### 2026-08-23 · review · note

**review pass 1: no blocking findings.** Reviewed the delta since the branch
point (`main...HEAD`, 11 files, +135/-15). Every acceptance criterion holds:
`uv run --group dev pytest -q` -- `232 passed in 10.31s`; the five named tests
plus `test_the_fenced_list_matches_the_rule_file` pass. The code matches the
plan; the step 8 deviation is correct, since `test_stages.py` compares the
CLAUDE.md prose to `FENCED` in both directions.

Refuted before writing: an import cycle (`pipeline/core/worktree.py:1-8`
imports stdlib only); a vacuous fence test (`fenced_touches` diffs two dots
against the merge base, `pipeline/core/fence.py:67-78`, so it sees the
uncommitted rewrite); a stale config reaching the gate from a worktree
(`pipeline/core/gate.py:93` passes `project`, not `wd`).

Non-blocking findings:

1. **minor** -- `project_config()` on a missing project directory now raises
   `FileNotFoundError`, not `PipelineError`. `subprocess.run(cwd=project)` in
   `head_file()` fails before the `cfg.is_file()` check. `pipeline/cli/main.py:497`
   catches only `PipelineError`, so `pipeline gate --project <typo>` prints a
   traceback instead of "no .../pipeline.toml -- run `pipeline init` first".
   Verified: `FileNotFoundError: [Errno 2] No such file or directory:
   PosixPath('/nonexistent-proj-xyz')`. Not reachable from the dispatcher:
   `supervisor.py:140`, `:574` and `:708` all need a ticket file under
   `project/.project/tickets/`, so the directory exists there.
2. **nit** -- `head_file()` returns `""`, not `None`, for a committed empty
   file, and exits 0 with a tree listing for a directory path. Neither reaches
   its one caller, which passes a fixed file path.

Not run: `./pipeline/hooks/test_dangerous_commands.py` -- the guard blocks it
from a read-only stage ("`test_dangerous_commands.py` is not on the read-only
allowlist"). The delta touches no file in `pipeline/hooks/`.

### 2026-08-23 16:45:40Z · review · session · session=79aa0641-57e8-4f0d-9fe7-42dd9f887109

`review` ran as session `79aa0641-57e8-4f0d-9fe7-42dd9f887109`
- replay: `claude --resume 79aa0641-57e8-4f0d-9fe7-42dd9f887109`
- log: `.project/logs/TICKET-037-review-79aa0641.log`

### 2026-08-23 16:45:40Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review pass 1: no blocking findings; 232 passed, all six named tests green, plan followed; two non-blocking findings appended

### 2026-08-23 16:45:52Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-23 16:45:53Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/037


Merge made by the 'ort' strategy.
 .project/decisions/DEC-039.md  |  28 ++
 .project/tickets/TICKET-039.md | 618 +++++++++++++++++++++++++++++++++++++++++
 pipeline/tui/app.py            |  23 ++
 tests/test_tui.py              |  45 ++-
 4 files changed, 713 insertions(+), 1 deletion(-)
 create mode 100644 .project/decisions/DEC-039.md
 create mode 100644 .project/tickets/TICKET-039.md
Updating a7b5f03..a71925e
Fast-forward
 CLAUDE.md                        | 18 ++++++++++------
 README.md                        |  5 +++++
 pipeline/core/config.py          | 27 ++++++++++++++++++++----
 pipeline/core/fence.py           |  2 +-
 pipeline/core/machine.py         |  3 ++-
 pipeline/core/worktree.py        | 17 +++++++++++++++
 pipeline/templates/pipeline.toml |  3 +++
 tests/test_config.py             | 45 ++++++++++++++++++++++++++++++++++++++++
 tests/test_fence.py              | 11 ++++++++++
 tests/test_machine.py            |  6 +++---
 tests/test_worktree.py           | 13 ++++++++++++
 11 files changed, 135 insertions(+), 15 deletions(-)
 create mode 100644 tests/test_config.py

```

### 2026-08-23 16:45:53Z · merging · decision

decision recorded as `DEC-037`
