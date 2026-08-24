---
id: TICKET-041
stage: done
class: bugfix
branch: ticket/041
test_file: tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
files_declared:
- CLAUDE.md
- pipeline/core/worktree.py
- pipeline/daemon/supervisor.py
- pipeline/harnesses/claude-code.toml
- pipeline/stages/_common.md
- tests/test_dispatch.py
- tests/test_harness.py
- tests/test_stages.py
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
  id: 7b099815-607b-40f6-99a9-45881ed40f94
  log: .project/logs/TICKET-041-review-7b099815.log
approved_by: chezzijr
approved_at: '2026-08-23T16:28:12.025184+00:00'
---

## Summary

`render()` grants `--add-dir {project}` (the whole main checkout) instead of
`--add-dir {project}/.project`, so every stage's file tools reach every other
ticket's file, every other ticket's worktree (`<project>/.worktrees/<id>`) and
the dispatcher's own source tree. TICKET-039 and TICKET-040 both wrote their
work into the main checkout on 2026-08-23. Reproduced by
`tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout`,
committed on `ticket/041` at fd47e01.

The fix landed in this ticket, four commits on `ticket/041`:

1. `7ea9f6c` -- rule 5 in `pipeline/stages/_common.md`: every edit except the
   ticket and the result file goes in the working directory.
2. `0114c89` -- narrow both `--add-dir {project}` grants in
   `pipeline/harnesses/claude-code.toml` (lines 166, 183) to
   `{project}/.project`, and rewrite the header comment.
3. `c13f6b3` -- `dirty_snapshot()` in `pipeline/core/worktree.py`: the
   main-checkout baseline, HEAD-free so `merging` moving base does not
   escalate a concurrent read-only stage.
4. `740517d` -- `pipeline/daemon/supervisor.py` escalates a read-only stage
   whose run left `dirty_snapshot(project)` changed, plus the `CLAUDE.md`
   gotcha bullet.

All 24 plan steps executed via TDD: each new test watched RED for the stated
reason, then GREEN. `uv run --group dev pytest -q` -> `232 passed`.
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`. Working
tree clean; no scope beyond the plan. Full trace is the last `## Thread`
entry under `implementing`.

`review` passed the delta `main...HEAD` with no blocking findings. It re-ran
`uv run --group dev pytest -q` -> `232 passed in 10.18s`, rendered both
templates against a project path with a space and got
`--add-dir '/my proj'/.project --`, and confirmed no bare `--add-dir {project}`
survives. It refuted the two false-escalation risks: `merge_cmd()` merges base
in the ticket's worktree and only fast-forwards the main checkout, so a
conflict never dirties it; the rule-5 renumbering breaks no citation, because
`CLAUDE.md:149` and `DEC-023.md:38` both cite rule 4. Three low-severity notes
are in the last `## Thread` entry, one of them that `review` could not run
`./pipeline/hooks/test_dangerous_commands.py` -- the read-only allowlist
refuses it, and the delta touches no file under `pipeline/hooks/`.

## Reproduction

Test: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout`

Command: `uv run --group dev pytest -q tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout`

Failure output:
```
AssertionError: --add-dir must grant only the project's .project/ directory, not the whole main checkout:
claude -p ... --add-dir /proj -- "Work ticket TICKET-001. ..."
assert ('--add-dir /proj/.project ' in '...' or '--add-dir /proj/.project --' in '...')
```

expect: --add-dir must grant only the project's .project/ directory, not the whole main checkout

Committed on `ticket/041` at fd47e01.

## Digest

Files touched: `pipeline/harnesses/claude-code.toml`, `pipeline/stages/_common.md`,
`pipeline/core/worktree.py`, `pipeline/daemon/supervisor.py`, `CLAUDE.md`,
`tests/test_stages.py`, `tests/test_worktree.py`, `tests/test_dispatch.py`.

Key functions and entry points:

- `render()` (`pipeline/core/config.py:104`) fills `{project}` with
  `shlex.quote(str(project))`. The template appends the suffix, so
  `--add-dir {project}/.project` renders `'/my proj'/.project` for a path with
  a space -- the shell concatenates the quoted and unquoted halves. `config.py`
  needs no change.
- `--add-dir {project}` appears twice: `pipeline/harnesses/claude-code.toml:166`
  (`cmd`) and `:183` (`interactive_cmd`). The header comment at lines 6-7
  explains the grant and changes with them.
- `tree_snapshot()` (`pipeline/core/worktree.py:124`) returns
  `git rev-parse HEAD` + `git status --porcelain -- . ':(exclude).project'`.
- `start()` (`pipeline/daemon/supervisor.py:648`) takes
  `before = tree_snapshot(wt) if is_readonly(stage) else None`, after
  `strip_settings_sources(wt)` and before `Popen`.
- `_finish()` (`pipeline/daemon/supervisor.py:845`) compares that baseline and
  escalates `wrote-in-readonly`.
- `child()` (`pipeline/daemon/supervisor.py:592`) builds a dispatcher child's
  record with `rec["before"] = None`.

Gotchas:

- The main checkout's HEAD moves during a run: `merging` fast-forwards the base
  branch there while other tickets' stages run. A main-checkout baseline
  carrying HEAD would escalate every read-only stage that overlapped a merge.
  The new `dirty_snapshot()` omits HEAD and keeps only the status lines.
- `tests/test_dispatch.py:804` asserts `rec["before"] == tree_snapshot(wt)`.
  Keep `before` a string and add `before_main` as a second key; do not turn
  `before` into a tuple.
- `machine.FENCED` fences `pipeline/core/worktree.py` at symbol granularity and
  names only `strip_settings_sources` (`pipeline/core/machine.py:22`).
  `fenced_touches()` parks the ticket only when a diff hunk overlaps that
  symbol's line range. Put `dirty_snapshot()` BELOW `tree_snapshot()`, so no
  hunk reaches `strip_settings_sources`, which ends at
  `pipeline/core/worktree.py:121`.
- `--add-dir` is variadic and the `--` before the prompt is load-bearing
  (`pipeline/harnesses/claude-code.toml:9`). Keep the trailing `-- \`.
- `--add-dir` does not restrict Bash, so a stage that reads the main checkout
  with `cat` or `grep` keeps working. Only the file tools narrow.
- `_common.md` rules are numbered and `CLAUDE.md` cites "rule 4" (the bounded
  view). The new rule goes in as 5 and the result-file rule becomes 6, so the
  rule-4 citation stays correct.
- `pipeline/harnesses/fake.toml` has no `--add-dir`, so part 1 does not touch
  the end-to-end dispatcher tests.
- `git_project()` in `tests/helpers.py` builds a git checkout with `f.py`
  tracked and `.project/` present. `supervisor.start(d, path, harness("fake"),
  {})` is the existing way to drive one stage (`tests/test_dispatch.py:788`).

## Decisions checked

Grepped `.project/decisions/` for `add-dir`, `add_dir`, `main checkout`,
`snapshot`, `readonly`, `read-only`, `worktree`.

- DEC-034 (active) is the record that constrains this change. It states that a
  `.claude/settings.json` at the project root, "passed as `--add-dir
  {project}`, does not reach a spawn whose cwd is the worktree (measured)", and
  it forbids widening `strip_settings_sources()` to the project checkout. This
  plan narrows the grant and leaves the strip alone, so it complies. The
  measurement stays true: a narrower grant cannot make root settings reachable.
  Its second finding -- the guard keeps `matcher: "Bash"` because Claude Code
  resolves settings at session start -- is why part 3 adds detection instead of
  a Write/Edit hook matcher.
- DEC-018 (active) fixes where the Tier A gate resolves `DEC-<n>` and where
  `record_decision()` writes: `.project/decisions/` in the project root. Both
  sit inside the `{project}/.project` grant, so the narrower grant does not
  break the planning stage's own greps.
- DEC-011, DEC-017, DEC-019, DEC-021, DEC-026 and DEC-032 matched the grep
  terms and constrain nothing here.

## Plan

1. Write the failing test `test_common_rules_say_where_a_code_edit_goes` in `tests/test_stages.py`: build `f = C.compose_prompt("review")`, read `text = f.read_text()`, `f.unlink()`, then assert `"Every file you edit goes in your working directory" in text` and `"the ticket file and the result file" in text`.
2. Run `uv run --group dev pytest -q tests/test_stages.py::test_common_rules_say_where_a_code_edit_goes` and watch it fail with `AssertionError`, because `pipeline/stages/_common.md` carries no such rule.
3. Insert a new rule 5 in `pipeline/stages/_common.md` between rule 4 and the result-file rule, and renumber the result-file rule from `5.` to `6.`; the new rule reads: `5. Every file you edit goes in your working directory, with exactly two exceptions: the ticket file and the result file. Both are named by absolute path in your instructions. Your working directory is a git worktree for this ticket alone. An edit anywhere else is lost work -- it lands outside the ticket's branch, no review sees it, and it corrupts the checkout the dispatcher runs from. If a path you are about to edit is not under your working directory and is not one of those two files, stop: you are in the wrong tree.`
4. Run `uv run --group dev pytest -q tests/test_stages.py` and expect no failures, including `test_composed_prompt_has_common_rules_and_no_frontmatter`.
5. Commit `pipeline/stages/_common.md` and `tests/test_stages.py` as `fix(TICKET-041): tell every stage where its edits go`.
6. Narrow both grants in `pipeline/harnesses/claude-code.toml`: change `--add-dir {project} -- \` to `--add-dir {project}/.project -- \` at line 166 (`cmd`) and line 183 (`interactive_cmd`), keeping the trailing `-- \` on each line.
7. Rewrite the header comment at `pipeline/harnesses/claude-code.toml` lines 6-7 to say: the agent's cwd is the ticket's git worktree; the ticket file and the `.result` sidecar live under `<project>/.project/` in the main checkout, so that one directory is the extra allowed dir, not the whole checkout; `--add-dir {project}` also granted every other ticket's file, every other ticket's worktree (`<project>/.worktrees/<id>`) and the dispatcher's own source tree, and TICKET-039 and TICKET-040 each wrote their work into the main checkout on 2026-08-23 (TICKET-041).
8. Add `test_add_dir_narrows_the_interactive_template_too` to `tests/test_harness.py`, covering the `interactive_cmd` half of step 6 that no criterion reached: call `render()` exactly as `test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` does but with `key="interactive_cmd"`, assert `"--add-dir /proj/.project " in cmd`, and assert `"--add-dir /proj " not in cmd` so a fix that ADDS the narrow directory without removing the broad one fails; run it against the unnarrowed `pipeline/harnesses/claude-code.toml` first and watch it fail on the bare `--add-dir /proj`; then run `uv run --group dev pytest -q tests/test_harness.py` against the narrowed `pipeline/harnesses/claude-code.toml` and expect no failures, including `test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout`, `test_add_dir_narrows_the_interactive_template_too` and `test_the_prompt_survives_a_variadic_flag`.
9. Commit `pipeline/harnesses/claude-code.toml` as `fix(TICKET-041): grant --add-dir only the project's .project directory`.
10. Write the failing test `test_the_main_checkout_baseline_ignores_a_merge_moving_head` in `tests/test_worktree.py`: build `d, sh = git_project()`, record `base = W.dirty_snapshot(d)` and `tbase = W.tree_snapshot(d)`, run `sh("git commit -q --allow-empty -m moved")`, assert `W.dirty_snapshot(d) == base` and `W.tree_snapshot(d) != tbase`, record `tmid = W.tree_snapshot(d)`, then `(d / "stray.py").write_text("x\n")` and assert `W.dirty_snapshot(d) != base` and `W.tree_snapshot(d) != tmid`, then `shutil.rmtree(d, ignore_errors=True)`.
11. Run `uv run --group dev pytest -q tests/test_worktree.py::test_the_main_checkout_baseline_ignores_a_merge_moving_head` and watch it fail with `AttributeError: module 'pipeline.core.worktree' has no attribute 'dirty_snapshot'`.
12. Add `def dirty_snapshot(project: Path) -> str:` to `pipeline/core/worktree.py` directly BELOW `tree_snapshot()`, with the body `_, dirty = run_cmd("git status --porcelain -- . ':(exclude).project'", project)` then `return dirty`, and a docstring stating it omits HEAD because `merging` fast-forwards the base branch in the main checkout while other tickets' stages run.
13. Rewrite `tree_snapshot()`'s body in `pipeline/core/worktree.py` to `_, head = run_cmd("git rev-parse HEAD", project)` then `return head + dirty_snapshot(project)`, leaving its docstring and its callers unchanged.
14. Run `uv run --group dev pytest -q tests/test_worktree.py tests/test_dispatch.py` and expect no failures; `test_a_readonly_stage_snapshots_after_the_settings_strip` covers `tree_snapshot()`'s unchanged behaviour.
15. Commit `pipeline/core/worktree.py` and `tests/test_worktree.py` as `feat(TICKET-041): snapshot a checkout's dirty state without its HEAD`.
16. Write the failing test `test_a_readonly_stage_that_writes_the_main_checkout_escalates` in `tests/test_dispatch.py`: build `d, _ = git_project()`, set `path = d / ".project/tickets/TICKET-001.md"`, write `FIXTURE.replace("stage: plan-validation", "stage: review")` to it, call `did, rec = supervisor.start(d, path, harness("fake"), {})`, then `(d / "f.py").write_text("an edit the stage made in the wrong tree\n")`, then `rec["proc"].wait()` and `supervisor.finish(d, rec)`; assert `Ticket.load(path).stage == "escalated"` and `"main checkout" in path.read_text()`, then `shutil.rmtree(d, ignore_errors=True)`.
17. Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_readonly_stage_that_writes_the_main_checkout_escalates` and watch it fail: the ticket reaches `implementing`, not `escalated`, because no baseline covers the main checkout.
18. Add `dirty_snapshot` to the `from pipeline.core.worktree import (...)` list in `pipeline/daemon/supervisor.py` lines 30-32, keeping the names alphabetical: `base_ref, dirty_snapshot, drop_worktree, ensure_worktree, project_env, run_cmd, strip_settings_sources, tree_snapshot, worktree`.
19. In `start()` (`pipeline/daemon/supervisor.py:648`) add `before_main = dirty_snapshot(project) if is_readonly(stage) else None` on the line after the existing `before = tree_snapshot(wt) ...` line, and add `rec["before_main"] = before_main` on the line after `rec["before"] = before` (near `pipeline/daemon/supervisor.py:663`).
20. In `child()` (`pipeline/daemon/supervisor.py:592`) add `rec["before_main"] = None` on the line after `rec["path"], rec["tid"], rec["meta"], rec["before"] = path, tid, t, None`, so a dispatcher child's record carries the key too.
21. In `_finish()` (`pipeline/daemon/supervisor.py:845`) add, immediately after the existing `wrote-in-readonly` block, the three lines `if rec.get("before_main") is not None and dirty_snapshot(project) != rec["before_main"]:`, `escalate(t, f"read-only stage `{stage}` modified the main checkout outside `.project/`", emit)`, `return "wrote-in-readonly"`; read the key with `rec.get`, because `tests/test_dispatch.py:93` builds a record without it.
22. Run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_daemon.py` and expect no failures.
23. Add one bullet to the gotchas list in `CLAUDE.md`, next to the existing bullet about `.project/` being excluded from the snapshot: `--add-dir` grants `<project>/.project`, not the project root, and a read-only stage's baseline is two snapshots, `tree_snapshot(wt)` plus `dirty_snapshot(project)` -- the second without HEAD, because `merging` moves the main checkout's HEAD mid-run.
24. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect both to report no failures, then commit `pipeline/daemon/supervisor.py`, `tests/test_dispatch.py` and `CLAUDE.md` as `fix(TICKET-041): escalate a read-only stage that writes the main checkout`.

## Acceptance criteria

- `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout`
  passes: `render()` produces `--add-dir /proj/.project`, not `--add-dir /proj`.
- `tests/test_harness.py::test_the_prompt_survives_a_variadic_flag` still
  passes: `--` still separates the narrowed flag from the prompt in both
  templates.
- `tests/test_harness.py::test_add_dir_narrows_the_interactive_template_too`
  passes: `render()` with `key="interactive_cmd"` produces
  `--add-dir /proj/.project` and no bare `--add-dir /proj`, so the
  interactive template is narrowed and asserted, not only the headless one.
- `tests/test_stages.py::test_common_rules_say_where_a_code_edit_goes` passes:
  the composed prompt states that every edit except the ticket and the result
  file goes in the working directory.
- `tests/test_worktree.py::test_the_main_checkout_baseline_ignores_a_merge_moving_head`
  passes: `dirty_snapshot()` is unchanged by a new commit and changed by a new
  dirty file, while `tree_snapshot()` changes on both.
- `tests/test_dispatch.py::test_a_readonly_stage_that_writes_the_main_checkout_escalates`
  passes: a `review` stage whose run left `f.py` modified in the main checkout
  lands on `escalated`.
- `tests/test_dispatch.py::test_a_readonly_stage_snapshots_after_the_settings_strip`
  still passes: `rec["before"]` is a string equal to `tree_snapshot(wt)`.
- The whole `tests/` suite passes: `uv run --group dev pytest -q` reports
  no failures.
- `./pipeline/hooks/test_dangerous_commands.py` reports no failures: the
  guard's table-driven cases, which pytest does not collect.

## Decisions

**`--add-dir` grants `<project>/.project`, and that is a stage's whole reach
outside its worktree.** A stage writes exactly two files there: the ticket and
the `.result` sidecar. Widening the flag back to `{project}` re-opens write
access to every other ticket's file, every other ticket's worktree
(`<project>/.worktrees/<id>`, inside the project directory) and the
dispatcher's own source tree. That is not theoretical: TICKET-039 and
TICKET-040 both wrote their work into the main checkout on 2026-08-23, and
TICKET-040 then read its own dispatcher as a competing writer and returned
`result: rejected` on a ticket whose premise it had confirmed. `--add-dir` does
not restrict Bash, so a stage that reads the main checkout with `cat` still
works.

**The main-checkout baseline omits HEAD; `tree_snapshot()`'s does not.**
`merging` fast-forwards the base branch in the main checkout while other
tickets' stages are running. A baseline carrying `git rev-parse HEAD` there
would escalate every read-only stage whose run overlapped somebody else's
merge. `dirty_snapshot()` exists for that one reason. Do not fold it back into
`tree_snapshot()`, whose subject is a worktree nobody else commits to.

**Only read-only stages get the main-checkout baseline.** A `write: true` stage
can still reach the main checkout through Bash, and nothing detects that --
part 1 is the prevention for its file tools. Extending the baseline to write
stages is deliberately out of scope here, because this ticket scopes detection
to read-only stages. It is the next ticket if a write stage corrupts the tree
again.

## Rollback

Revert the four commits named in `## Plan` steps 5, 9, 15 and 24. The three
parts are independent:

1. If a stage loses access to something under `<project>` it genuinely needs,
   revert `pipeline/harnesses/claude-code.toml` alone to `--add-dir {project}`.
   The symptom is a stage reporting that it cannot read or write a path in the
   main checkout outside `.project/`.
2. If read-only stages escalate with "modified the main checkout outside
   `.project/`" on runs that did nothing wrong, revert the
   `pipeline/daemon/supervisor.py` change alone; `dirty_snapshot()` can stay.
3. `pipeline/stages/_common.md` is prose and carries no runtime risk.

## Thread

### 2026-08-23 15:38:59Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

### 2026-08-23 · triage · reproduced

Confirmed all three claims by reading the code directly:

1. `pipeline/harnesses/claude-code.toml` lines 166 and 183: both `cmd` and
   `interactive_cmd` pass `--add-dir {project}`, and `pipeline/core/config.py:132`
   fills `{project}` with the whole project root, not `.project/`.
2. `pipeline/daemon/supervisor.py:648`: `tree_snapshot(wt)` watches only the
   ticket's worktree, never the main checkout.
3. `pipeline/stages/_common.md` rule 5 only names the worktree parenthetically,
   while handing over an absolute path into the main checkout for the result
   file, as the ticket describes.

Wrote a test asserting `render()` on the `review` stage's `.project`-rooted
ticket/result paths still produces `--add-dir /proj` instead of
`--add-dir /proj/.project`. It fails with the reported symptom. Do not fix in
this stage -- three files across two modules, with a design choice (how the
readonly baseline learns the main-checkout root) left open, so this is `ok`,
not `chore`.

Caution to future stages: I first wrote this test into the MAIN checkout's
`tests/test_harness.py` by mistake (the harness's `--add-dir {project}` grant
made it possible), exactly reproducing the failure mode this ticket
describes. Caught it via `git status` in the main checkout, reverted there,
and wrote it in the worktree instead. No lasting effect; noted since it is
direct field evidence of the bug.

dispatcher pickup

### 2026-08-23 15:40:58Z · triage · session · session=6b91cb75-923f-4a16-b078-f3eacdab33c2

`triage` ran as session `6b91cb75-923f-4a16-b078-f3eacdab33c2`
- replay: `claude --resume 6b91cb75-923f-4a16-b078-f3eacdab33c2`
- log: `.project/logs/TICKET-041-triage-6b91cb75.log`

### 2026-08-23 15:40:58Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced --add-dir granting the whole main checkout; committed failing test on ticket/041.

### 2026-08-23 · planning · note

Planned all three parts as one ticket; they share one failure and one test
run, and part 1 without part 3 ships prevention with no detection.

Two facts settled by reading the code, both in `## Digest`:

1. `render()` needs no change. It fills `{project}` with
   `shlex.quote(str(project))`, and the shell concatenates `'/my proj'` with
   the literal `/.project` the template appends. The fix is two template
   lines in `pipeline/harnesses/claude-code.toml`.
2. The main-checkout baseline cannot reuse `tree_snapshot()`. That function
   includes `git rev-parse HEAD`, and `merging` fast-forwards the base branch
   in the main checkout while other tickets' stages run -- every read-only
   stage overlapping a merge would escalate. `dirty_snapshot()` drops HEAD and
   keeps the `git status --porcelain` lines.

Outside this ticket's scope, noted rather than fixed: a `write: true` stage can
still write the main checkout through Bash, which `--add-dir` does not
restrict. That is how TICKET-039 and TICKET-040 could still corrupt the tree
after this lands. `## Decisions` records it as the next ticket.

### 2026-08-23 15:47:13Z · planning · session · session=67dc12bb-44c3-4dc5-8250-04739b980ee0

`planning` ran as session `67dc12bb-44c3-4dc5-8250-04739b980ee0`
- replay: `claude --resume 67dc12bb-44c3-4dc5-8250-04739b980ee0`
- log: `.project/logs/TICKET-041-planning-67dc12bb.log`

### 2026-08-23 15:47:13Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned all three parts: narrow --add-dir to .project, add the edit-location rule, add a HEAD-free main-checkout baseline.

### 2026-08-23 15:47:24Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails as required
```
udget-usd 4 --add-dir /proj -- "Work ticket TICKET-001. Your prompt carries a bounded view of /proj/.project/t.md; open that file only for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" 
E       assert ('--add-dir /proj/.project ' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ' or '--add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails on base `main` too -- the bug is not already fixed upstream
```
-add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-so0verqp/base
      Built pipeline @ file:///tmp/pipeline-base-so0verqp/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- acceptance criterion names no test: - `uv run --group dev pytest -q` reports no failures.

### 2026-08-23 15:47:24Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion names no test: - `uv run --group dev pytest -q` reports no failures.

### 2026-08-23 · planning · note

The Tier A gate failed one check: "acceptance criterion names no test: -
`uv run --group dev pytest -q` reports no failures." The gate reads each
bullet of `## Acceptance criteria` alone and wants a test token on the
bullet's first line. Its regex is
`\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/`, and `pytest` carries no
word boundary before `test`, so that bullet named no test.

Changed `## Acceptance criteria` only, two bullets:

1. The full-suite bullet now opens "The whole `tests/` suite passes:" before
   the `uv run --group dev pytest -q` command.
2. The guard bullet now opens with `./pipeline/hooks/test_dangerous_commands.py`,
   so its test token is not stranded on a continuation line.

Re-ran the gate's structural checks offline against the edited ticket: 8 of 8
criteria carry a test token, 24 numbered steps, every step cites a declared
file, `## Digest` has 47 non-empty lines, and all 8 cited `DEC-` ids resolve
as active records.

The plan, the digest, the decisions and `files_declared` are unchanged. The
gate raised no finding against any of them.

### 2026-08-23 15:50:02Z · planning · session · session=aaf909f1-350e-4162-b4ab-b0f311848e98

`planning` ran as session `aaf909f1-350e-4162-b4ab-b0f311848e98`
- replay: `claude --resume aaf909f1-350e-4162-b4ab-b0f311848e98`
- log: `.project/logs/TICKET-041-planning-aaf909f1.log`

### 2026-08-23 15:50:02Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Fixed the two acceptance criteria the Tier A gate rejected for naming no test; plan, digest and files_declared unchanged.

### 2026-08-23 15:50:14Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails as required
```
udget-usd 4 --add-dir /proj -- "Work ticket TICKET-001. Your prompt carries a bounded view of /proj/.project/t.md; open that file only for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" 
E       assert ('--add-dir /proj/.project ' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ' or '--add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails on base `main` too -- the bug is not already fixed upstream
```
-add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.13s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-dw90tr1c/base
      Built pipeline @ file:///tmp/pipeline-base-dw90tr1c/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-23 · plan-validation · note

**Tier B judgement: FAIL on one item of eight.** Step 10's second assertion is
vacuous, so acceptance criterion 4 is not tested. Fix that one assertion and
the plan passes.

1. Falsifiable criteria -- FAIL. Step 10 asserts `W.tree_snapshot(d) != base`
   where `base = W.dirty_snapshot(d)`. `tree_snapshot()` returns `head + dirty`
   and `dirty_snapshot()` returns `dirty`, so the two differ by the sha
   whatever the commit did. The assertion passes even if `tree_snapshot()`
   stopped tracking HEAD. Criterion 4 claims "`tree_snapshot()` changes on
   both" and nothing tests it. Fix: record `tbase = W.tree_snapshot(d)` before
   `sh("git commit -q --allow-empty -m moved")`, then assert
   `W.tree_snapshot(d) != tbase` after the commit and after `stray.py`.
2. Root cause -- pass. Both templates grant the file tools the whole main
   checkout, while a stage writes only two files, both under
   `<project>/.project/`. Step 6 narrows the grant; the test reads the
   rendered command, not a symptom.
3. Decision conflict -- pass. I read DEC-034: it forbids widening
   `strip_settings_sources()` to the project checkout, and the plan does not
   touch it. DEC-018 puts `.project/decisions/` in the project root, inside
   the narrowed grant.
4. No research left -- pass. I verified every cited site:
   `claude-code.toml:166` and `:183` both read `--add-dir {project} -- \`;
   `config.py:133` is `project=shlex.quote(str(project))`;
   `supervisor.py:592`, `:648`, `:663`, `:845` match the plan's quotes;
   the import list at `:29-31` is `base_ref, drop_worktree, ...`;
   `tests/test_dispatch.py:93` builds a record with no `before_main`, which
   is why step 21 uses `rec.get`; `_common.md` rule 4 is the bounded-view
   rule `CLAUDE.md:145` cites, and the result-file rule is 5.
5. Riskiest step -- pass. Step 6 changes every stage's reach at once.
   `## Rollback` item 1 reverts the toml alone and names the symptom.
6. Regression surface -- pass. `test_the_prompt_survives_a_variadic_flag`
   covers the `--`; `test_a_readonly_stage_snapshots_after_the_settings_strip`
   covers `tree_snapshot()`'s callers; `fake.toml` has no `--add-dir`, so the
   end-to-end tests are untouched. One risk the digest omits:
   `dirty_snapshot()` lists untracked files, so a project that does not ignore
   `.worktrees/` gets churn from other tickets' worktrees. This repo ignores
   it (`.gitignore` line 3, `.worktrees/`), and `## Rollback` item 2 covers
   the false escalation.
7. Scope discipline -- pass. Every step traces to a criterion except step 23,
   the `CLAUDE.md` bullet, which corrects the gotcha this change invalidates.
8. Blast radius -- pass. `class: bugfix`, 9 declared files: 4 source
   (one of them prose), 4 test, 1 doc.

### 2026-08-23 15:54:04Z · plan-validation · session · session=971dff76-15a2-4325-9f35-f01e149657a2

`plan-validation` ran as session `971dff76-15a2-4325-9f35-f01e149657a2`
- replay: `claude --resume 971dff76-15a2-4325-9f35-f01e149657a2`
- log: `.project/logs/TICKET-041-plan-validation-971dff76.log`

### 2026-08-23 15:54:04Z · plan-validation · transition · to=escalated · result=fail · marker=yes

**plan-validation -> escalated** (result: `fail`)

✓ Tier B failed 1 of 8 items: step 10's `tree_snapshot(d) != base` is vacuous, so acceptance criterion 4 tests nothing; the other seven pass.

### 2026-08-23 16:06:45Z · human · note

**resumed** by human -> `planning`, reset ['plan_validation_attempts']

### 2026-08-23 · planning · note

Rewrote step 10, the one item Tier B failed. Step 10 now records `tbase =
W.tree_snapshot(d)` before the empty commit and `tmid = W.tree_snapshot(d)`
after it. It asserts `W.tree_snapshot(d) != tbase` after the commit and
`W.tree_snapshot(d) != tmid` after `stray.py`. Tier B asked for both
comparisons against `tbase`; the second compares to `tmid` instead, because a
comparison to `tbase` differs by the sha alone and would not test the dirty
half. Acceptance criterion 4 -- "`tree_snapshot()` changes on both" -- is now
tested by both assertions.

The old assertion was vacuous: `base = W.dirty_snapshot(d)`, and
`tree_snapshot()` returns `head + dirty`, so `W.tree_snapshot(d) != base` held
whatever the commit did.

Checked the values the new assertions rest on. `git_project()`
(`tests/helpers.py:49`) commits `f.py` and leaves `.project/` untracked, and
`':(exclude).project'` drops the untracked directory. So `base` is the empty
string, and `dirty_snapshot(d) == base` after the commit is a real check: a
`dirty_snapshot()` that kept HEAD would fail it.

Steps 1-9 and 11-24, `## Digest`, `## Decisions checked`, `## Acceptance
criteria`, `## Decisions`, `## Rollback` and `files_declared` are unchanged.

### 2026-08-23 16:08:50Z · planning · session · session=b8b4ebeb-645f-4463-8806-310e537100f9

`planning` ran as session `b8b4ebeb-645f-4463-8806-310e537100f9`
- replay: `claude --resume b8b4ebeb-645f-4463-8806-310e537100f9`
- log: `.project/logs/TICKET-041-planning-b8b4ebeb.log`

### 2026-08-23 16:08:50Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Rewrote plan step 10 so tree_snapshot() is compared to its own earlier value twice; the rest of the plan is unchanged.

### 2026-08-23 16:09:02Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails as required
```
udget-usd 4 --add-dir /proj -- "Work ticket TICKET-001. Your prompt carries a bounded view of /proj/.project/t.md; open that file only for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" 
E       assert ('--add-dir /proj/.project ' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ' or '--add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails on base `main` too -- the bug is not already fixed upstream
```
--add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.13s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-q6i1a46c/base
      Built pipeline @ file:///tmp/pipeline-base-q6i1a46c/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```
- plan step names no declared file: '8. Run `uv run --group dev pytest -q tests/test_harness.py` and expect no failures, including `test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` and `test_the_prompt_survives_a_variadic_flag`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-23 16:09:02Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- plan step names no declared file: '8. Run `uv run --group dev pytest -q tests/test_harness.py` and expect no failures, including `test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` and `test_the_prompt_survives_a_variadic_flag`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-23 · planning · note

Rewrote step 8, the one item the Tier A gate failed. The gate reported: "plan
step names no declared file: '8. Run `uv run --group dev pytest -q
tests/test_harness.py` and expect no failures, ...'". Step 8 now runs that
same command "against the narrowed `pipeline/harnesses/claude-code.toml`".
That path is declared, and it is the file step 8 verifies.

I did not add `tests/test_harness.py` to `files_declared`. No step edits it:
the reproduction test is committed at fd47e01 and the plan only runs it.
Declaring a file the plan does not modify would widen the blast radius Tier B
passed at 8 declared paths.

Checked every other step for the same failure before writing. All 24 steps
contain at least one of the 8 declared paths as a substring.

Resolved the ids cited in `## Decisions checked` against
`.project/decisions/`: DEC-011, DEC-017, DEC-018, DEC-019, DEC-021, DEC-026,
DEC-032 and DEC-034 all exist as files, and none carries a `superseded-by:`
line.

Steps 1-7 and 9-24, `## Digest`, `## Decisions checked`, `## Acceptance
criteria`, `## Decisions`, `## Rollback` and `files_declared` are unchanged.

### 2026-08-23 16:11:13Z · planning · session · session=d0cde6f6-a046-42cf-818b-e71dd09d22e1

`planning` ran as session `d0cde6f6-a046-42cf-818b-e71dd09d22e1`
- replay: `claude --resume d0cde6f6-a046-42cf-818b-e71dd09d22e1`
- log: `.project/logs/TICKET-041-planning-d0cde6f6.log`

### 2026-08-23 16:11:13Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Rewrote plan step 8 to cite pipeline/harnesses/claude-code.toml; all 24 steps now name a declared file.

### 2026-08-23 16:11:25Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails as required
```
udget-usd 4 --add-dir /proj -- "Work ticket TICKET-001. Your prompt carries a bounded view of /proj/.project/t.md; open that file only for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" 
E       assert ('--add-dir /proj/.project ' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ' or '--add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails on base `main` too -- the bug is not already fixed upstream
```
--add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-n6wt6fee/base
      Built pipeline @ file:///tmp/pipeline-base-n6wt6fee/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-23 · plan-validation · note

Tier B: FAIL on one item, falsifiable criteria. The other seven items pass.

long: eight scored items, each carrying its evidence.

**FAIL -- falsifiable criteria.** Step 6 narrows two lines and only one is
tested. `test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout`
renders `cmd`, never `interactive_cmd`.
`test_the_prompt_survives_a_variadic_flag` loops both templates, but asserts
only that the text before `"Work ticket` ends with `--` -- which
`--add-dir {project} -- \` already satisfies. So an implementer who narrows
`pipeline/harnesses/claude-code.toml:166` and leaves `:183` at
`--add-dir {project}` passes all 8 acceptance criteria, with an interactive
stage still granted the whole main checkout. No criterion covers `:183`.
Fix: assert the narrowed grant in both templates, declare
`tests/test_harness.py`, and add the criterion.

**Pass -- root cause.** The root cause is the grant's breadth in the harness
template; `render()` only fills `{project}`. Step 6 changes the template.

**Pass -- decisions.** DEC-034 forbids widening `strip_settings_sources()` to
the project checkout; the plan leaves it alone. DEC-018 puts
`.project/decisions/` inside the narrowed grant.

**Pass -- scope.** Steps 1-5 serve criterion 3, steps 6-9 criteria 1-2, steps
10-15 criterion 4, steps 16-22 criteria 5-6. Step 23 is one `CLAUDE.md`
gotcha bullet with no criterion; `CLAUDE.md` is this repo's gotcha file, so I
accept it.

**Pass -- no research left.** Every step names a file plus a function or a
line: `dirty_snapshot()`, `tree_snapshot()`, `start()`, `child()`,
`_finish()`, `pipeline/daemon/supervisor.py` lines 30-32, 592, 648, 663, 845.

**Pass -- riskiest step.** Step 6. `## Rollback` item 1 reverts the grant
alone and names the symptom. Step 21 ranks second; item 2 reverts it alone.

**Pass -- regression surface.** Step 13 rewrites `tree_snapshot()`'s body;
`test_a_readonly_stage_snapshots_after_the_settings_strip`
(`tests/test_dispatch.py:804`) covers it. `tests/test_dispatch.py:93` builds a
record with no `before_main`, and step 21 reads it with `rec.get`. Step 3
renumbers the result-file rule to 6 and keeps rule 4, which `CLAUDE.md:145`
cites.

**Pass -- blast radius.** 8 declared paths and 4 commits for one root cause,
with prevention, guidance and detection. DEC-034 is also `class: bugfix` at 11
declared paths.

Verified two `## Digest` claims. `fenced_touches()` diffs with `--unified=0`
(`pipeline/core/fence.py:78`), so a hunk on lines 128-130 cannot reach
`strip_settings_sources`, which ends at `pipeline/core/worktree.py:121`.
`render()` fills `project=shlex.quote(str(project))`
(`pipeline/core/config.py:133`), so `{project}/.project` renders
`'/my proj'/.project`.

One `## Digest` wording error, harmless. It calls the `CLAUDE.md` "rule 4"
citation the bounded view. Rule 4 is the thread-and-summary rule; rule 1 is
the bounded view. The plan's action holds either way: the new rule enters as
5, so rule 4 keeps its number.

### 2026-08-23 16:15:23Z · plan-validation · session · session=34fe3b8a-fc2b-45bc-8096-7620ecf746a6

`plan-validation` ran as session `34fe3b8a-fc2b-45bc-8096-7620ecf746a6`
- replay: `claude --resume 34fe3b8a-fc2b-45bc-8096-7620ecf746a6`
- log: `.project/logs/TICKET-041-plan-validation-34fe3b8a.log`

### 2026-08-23 16:15:23Z · plan-validation · transition · to=escalated · result=fail · marker=yes

**plan-validation -> escalated** (result: `fail`)

✓ Tier B failed one item: no criterion covers the interactive_cmd half of step 6's --add-dir narrowing.

### 2026-08-23 16:18:13Z · human · note

**resumed** by human -> `plan-validation`, reset ['plan_validation_attempts']

### 2026-08-23 16:18:25Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails as required
```
udget-usd 4 --add-dir /proj -- "Work ticket TICKET-001. Your prompt carries a bounded view of /proj/.project/t.md; open that file only for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" 
E       assert ('--add-dir /proj/.project ' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ' or '--add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails on base `main` too -- the bug is not already fixed upstream
```
-add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-9owtsebi/base
      Built pipeline @ file:///tmp/pipeline-base-9owtsebi/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 12ms

```

### 2026-08-23 · plan-validation · note

Tier B: PASS on all eight items. The item that failed the previous run,
falsifiable criteria, is fixed.

long: eight scored items, each carrying its evidence.

**Pass -- falsifiable criteria.** New criterion 3 and step 8 cover
`pipeline/harnesses/claude-code.toml:183` (`interactive_cmd`), the half no
criterion reached before. Step 8 asserts `"--add-dir /proj/.project " in cmd`
and `"--add-dir /proj " not in cmd`, so narrowing `:166` alone now fails:
`:183` still renders `--add-dir {project} -- \`. Frontmatter `files_declared`
line 9 lists `tests/test_harness.py`.

**Pass -- root cause.** The root cause is the grant's breadth in the harness
template, not in code: `--add-dir {project}` is written twice
(`pipeline/harnesses/claude-code.toml:166`, `:183`) and `render()` only
substitutes `{project}`. Step 6 changes both template lines.

**Pass -- decisions.** DEC-034 forbids widening `strip_settings_sources()`
(`pipeline/core/worktree.py:102-121`); the plan does not touch it. DEC-018
puts `.project/decisions/` inside the narrowed grant.

**Pass -- scope.** Steps 1-5 serve criterion 4, steps 6-9 criteria 1-3, steps
10-15 criterion 5, steps 16-22 criteria 6-7, step 24 criteria 8-9. Step 23 is
one `CLAUDE.md` gotcha bullet with no criterion; `CLAUDE.md` is this repo's
gotcha file, so I accept it.

**Pass -- no research left.** I opened every cited location and all hold:
`tree_snapshot()` at `pipeline/core/worktree.py:124-130`,
`strip_settings_sources()` ending at `:121`, `child()` at
`pipeline/daemon/supervisor.py:592`, the baseline at `:648`, `rec["before"]`
at `:663`, the `wrote-in-readonly` block at `:845`, `tests/test_dispatch.py:93`
(a record built without the key, so step 21's `rec.get` is required) and
`:804`. One off-by-one: the `worktree` import block is lines 29-31, not 30-32;
step 18 gives the final list verbatim, so nothing is ambiguous.

**Pass -- riskiest step.** Step 6. `## Rollback` item 1 reverts
`pipeline/harnesses/claude-code.toml` alone and names the symptom. Step 21
ranks second; item 2 reverts it alone and keeps `dirty_snapshot()`.

**Pass -- regression surface.** Step 13 rewrites `tree_snapshot()`'s body;
`test_a_readonly_stage_snapshots_after_the_settings_strip`
(`tests/test_dispatch.py:804`) asserts `rec["before"] == tree_snapshot(wt)`
and covers it. I checked the false-escalation path step 21 opens: `merge_cmd()`
runs `git merge --no-edit {base}` in the ticket's own worktree and only
`git -C {proj} merge --ff-only` in the main checkout
(`pipeline/daemon/supervisor.py:501,505`), so another ticket's merge leaves
neither a conflict nor a dirty file there. A human editing the main checkout
mid-run still escalates a read-only stage; `## Rollback` item 2 is the exit.

**Pass -- blast radius.** `class: bugfix`, 9 declared files: 3 code
(`pipeline/harnesses/claude-code.toml`, `pipeline/core/worktree.py`,
`pipeline/daemon/supervisor.py`), 1 stage prompt, 1 doc, 4 test files. Four
commits, one root cause plus its prevention and its detection.

**Two notes for `implementing`, neither a gate failure.** Step 8 says to run
the new test "against the unnarrowed `pipeline/harnesses/claude-code.toml`
first", but step 6 already narrowed both lines. Add the test before applying
step 6, or restore `--add-dir {project}` on `:183` to watch it fail, then
reapply. Second: `## Digest`'s "Files touched" list omits
`tests/test_harness.py` while frontmatter `files_declared` includes it.
`files_conflict` reads the frontmatter, so nothing is blocked.

### 2026-08-23 16:22:09Z · plan-validation · session · session=21797336-f418-4aa6-8161-f89fc6c58b66

`plan-validation` ran as session `21797336-f418-4aa6-8161-f89fc6c58b66`
- replay: `claude --resume 21797336-f418-4aa6-8161-f89fc6c58b66`
- log: `.project/logs/TICKET-041-plan-validation-21797336.log`

### 2026-08-23 16:22:09Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B passed all eight items; the interactive_cmd criterion gap from the previous run is closed.

### 2026-08-23 16:28:12Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-23 16:28:44Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails as required
```
udget-usd 4 --add-dir /proj -- "Work ticket TICKET-001. Your prompt carries a bounded view of /proj/.project/t.md; open that file only for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" 
E       assert ('--add-dir /proj/.project ' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ' or '--add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout` fails on base `main` too -- the bug is not already fixed upstream
```
--add-dir /proj/.project --' in 'claude -p --model opus --effort high --session-id s1 --settings /proj/settings.json --output-format stream-json --ver...nly for what the view says it omitted, and read only the lines you need. When finished write /proj/.project/t.result" ')

tests/test_harness.py:90: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yaf325nj/base
      Built pipeline @ file:///tmp/pipeline-base-yaf325nj/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-23 16:28:44Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-23 · implementing · todo

Todo list, one entry per plan step:

1. [x] _common.md rule + test (steps 1-5)
2. [x] narrow --add-dir in claude-code.toml + interactive test (steps 6-9)
3. [x] dirty_snapshot() in worktree.py + test (steps 10-15)
4. [x] escalate on main-checkout write in supervisor.py + test (steps 16-22)
5. [x] CLAUDE.md gotcha bullet + full suite + guard script (steps 23-24)

### 2026-08-23 · implementing · note

Executed the plan as written, TDD per step, four commits:

1. `7ea9f6c` -- rule 5 in `pipeline/stages/_common.md`, result-file rule
   renumbered 5->6. `test_common_rules_say_where_a_code_edit_goes` RED then
   GREEN.
2. `0114c89` -- narrowed `--add-dir {project}` to `--add-dir {project}/.project`
   at `pipeline/harnesses/claude-code.toml:166` and `:183`, rewrote the header
   comment. Added `test_add_dir_narrows_the_interactive_template_too` before
   narrowing, watched it fail on the bare `--add-dir /proj`, then narrowed and
   watched it pass alongside the existing two harness tests.
3. `c13f6b3` -- added `dirty_snapshot()` below `tree_snapshot()` in
   `pipeline/core/worktree.py`, rewrote `tree_snapshot()` to call it.
   `test_the_main_checkout_baseline_ignores_a_merge_moving_head` RED
   (`AttributeError: no attribute 'dirty_snapshot'`) then GREEN.
4. `740517d` -- `dirty_snapshot` import, `before_main` in `start()`/`child()`,
   a second escalate block in `_finish()` guarded by `rec.get`, plus the
   `CLAUDE.md` gotcha bullet. `test_a_readonly_stage_that_writes_the_main_checkout_escalates`
   RED (`assert 'verifying' == 'escalated'`) then GREEN.

Full suite: `uv run --group dev pytest -q` -> `232 passed`.
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`. Working
tree clean, no scope beyond the plan's 24 steps.

### 2026-08-23 16:32:31Z · implementing · session · session=fc4140b2-7d35-4373-b9f1-509566ee00df

`implementing` ran as session `fc4140b2-7d35-4373-b9f1-509566ee00df`
- replay: `claude --resume fc4140b2-7d35-4373-b9f1-509566ee00df`
- log: `.project/logs/TICKET-041-implementing-fc4140b2.log`

### 2026-08-23 16:32:31Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed all 24 plan steps via TDD across 4 commits; full suite (232 tests) and guard script pass.

### 2026-08-23 · review · note

Reviewed the delta `main...HEAD`, five commits, 129 insertions across 9 files.
No blocking findings.

Verified:

1. `uv run --group dev pytest -q` -> `232 passed in 10.18s`.
2. Both templates render `--add-dir '/my proj'/.project --` for a project path
   with a space. `Popen(cmd, shell=True)`
   (`pipeline/daemon/supervisor.py:391`) makes that one argument,
   `/my proj/.project`.
3. No `--add-dir {project}` remains: the only two are
   `pipeline/harnesses/claude-code.toml:171` and `:188`, both narrowed.
4. `merge_cmd()` (`pipeline/daemon/supervisor.py:502`) merges base in the
   ticket's worktree and only fast-forwards the main checkout, so a conflict
   never dirties the main checkout and cannot escalate a concurrent read-only
   stage. HEAD moving is what `dirty_snapshot()` omits.
5. The rule-5 renumbering breaks no citation. `CLAUDE.md:149` and
   `.project/decisions/DEC-023.md:38` both cite rule 4, which is unchanged.
6. Rule 5's "exactly two exceptions" holds: no stage prompt writes a third
   file outside its worktree. `record_decision()` is the dispatcher's writer
   (`pipeline/daemon/supervisor.py:126`); `planning` only reads
   `.project/decisions/`, which stays inside the narrowed grant.

Non-blocking:

1. severity=low. I did not run `./pipeline/hooks/test_dangerous_commands.py`.
   The guard refused it: "`test_dangerous_commands.py` is not on the
   read-only allowlist". The delta touches no file under `pipeline/hooks/`.
2. severity=low. `## Reproduction` cites the repro commit as `fd47e01`;
   `git merge-base --is-ancestor fd47e01 HEAD` reports it is not on the
   branch. `revalidating` rebased it to `d1e2454`.
3. severity=low. `pipeline/harnesses/claude-code.toml:9` reads "`--add-dir
   {project}` used to grant that"; "that" has no antecedent.

### 2026-08-23 16:37:01Z · review · session · session=7b099815-607b-40f6-99a9-45881ed40f94

`review` ran as session `7b099815-607b-40f6-99a9-45881ed40f94`
- replay: `claude --resume 7b099815-607b-40f6-99a9-45881ed40f94`
- log: `.project/logs/TICKET-041-review-7b099815.log`

### 2026-08-23 16:37:01Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the delta main...HEAD (5 commits, 9 files); no blocking findings, 3 low-severity notes appended.

### 2026-08-23 16:57:10Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-23 16:57:11Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/041


Auto-merging CLAUDE.md
CONFLICT (content): Merge conflict in CLAUDE.md
Auto-merging pipeline/core/worktree.py
Auto-merging pipeline/daemon/supervisor.py
CONFLICT (content): Merge conflict in pipeline/daemon/supervisor.py
Auto-merging tests/test_dispatch.py
Auto-merging tests/test_stages.py
Auto-merging tests/test_worktree.py
Automatic merge failed; fix conflicts and then commit the result.

```

### 2026-08-24 00:45:44Z · human · note

**resumed** by human -> `merging`, reset []

### 2026-08-24 00:45:47Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/041


Merge made by the 'ort' strategy.
 pipeline/core/fence.py   | 2 +-
 pipeline/core/machine.py | 2 +-
 tests/test_machine.py    | 7 ++++---
 3 files changed, 6 insertions(+), 5 deletions(-)
Updating 783170c..a79e777
Fast-forward
 CLAUDE.md                           |  4 ++++
 pipeline/core/worktree.py           | 10 +++++++++-
 pipeline/daemon/supervisor.py       | 14 ++++++++++---
 pipeline/harnesses/claude-code.toml | 13 ++++++++----
 pipeline/stages/_common.md          | 10 +++++++++-
 tests/test_dispatch.py              | 18 +++++++++++++++++
 tests/test_harness.py               | 40 +++++++++++++++++++++++++++++++++++++
 tests/test_stages.py                |  8 ++++++++
 tests/test_worktree.py              | 21 +++++++++++++++++++
 9 files changed, 129 insertions(+), 9 deletions(-)

```

### 2026-08-24 00:45:47Z · merging · decision

decision recorded as `DEC-041`
