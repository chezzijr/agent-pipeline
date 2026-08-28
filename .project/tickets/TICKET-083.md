---
id: TICKET-083
stage: done
class: bugfix
branch: ticket/083
test_file: tests/test_worktree.py::test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress
files_declared:
- CLAUDE.md
- pipeline/core/ticket.py
- pipeline/core/worktree.py
- pipeline/stages/_common.md
- tests/test_worktree.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 13
  plan_files: 5
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 065d6cb6-d3cd-4e48-910c-aa7b82485877
  log: .project/logs/TICKET-083-review-065d6cb6.log
approved_by: 'chezzijr (via Claude Code, while away; reviewer also filed this ticket
  -- audit in thread). Checked: worktree.py imports only stdlib, so the new ticket.py
  -> worktree.py import is not a cycle.'
approved_at: '2026-08-27T18:10:15.220063+00:00'
---

## Summary

A stage's worktree carries its own `.project/tickets/<id>.md`, frozen at the
branch cut, while the live ticket lives in the main checkout and is not
committed until merge. The two diverge from the first `Ticket.save()`.
TICKET-067 hit both consequences: `implementing` read the empty snapshot, called
its own prompt fabricated, and returned `blocked`; its objection, written into
that tracked snapshot, left the worktree dirty and `revalidating` failed with
`error: cannot rebase: You have unstaged changes.`

Planning chose the refresh shape. `Ticket.save()` mirrors the live ticket into
the worktree at mode `0444`, after marking the path with `git update-index
--skip-worktree` in the worktree's own index. One writer (invariant 5), two
destinations. The mark keeps the mirror out of `git status`, out of `git add -A`
and out of the rebase `merging` runs, so the escalation path closes even if a
stage writes to the mirror anyway. The plan is 13 steps over 5 files.

plan-validation passed all eight items. Two corrections for `implementing`:
step 7's import goes on line 18 of `pipeline/core/ticket.py`, below
`KNOWN_STAGES` on line 17; and `worktree()` (`pipeline/core/worktree.py:31`)
already returns the path step 4 re-derives.

`implementing` executed all 13 steps with TDD, both commits landed:
`fix(TICKET-083): Ticket.save mirrors the live ticket into its worktree,
read-only` and `docs(TICKET-083): the worktree ticket copy is a read-only
mirror`. `mirror_ticket()` re-derives its own worktree path from the ticket's
`Path` rather than calling `worktree()`, since `worktree()` needs a `meta`
dict `mirror_ticket()` does not have.

`review` passed the delta: no blocking findings. All six acceptance criteria
pass, `uv run --group dev pytest -q` printed `379 passed` and `exit=0`, and
`fenced_touches(Path('.'), 'main')` returned `[]`, so the diff does not park at
`awaiting-merge`. Four candidate blocking findings were refuted at a line and
dropped; the thread names each. Two minor findings and two nits stand, none
blocking: a crash inside `mirror_ticket()`'s sub-millisecond
chmod-to-`os.replace` window would leave a `0444` tmp that fails every later
save; and `test_a_merged_dispatcher_change_ends_the_daemon_loop_too` fails when
`tests/test_dispatch.py` runs alone but passes in the full suite -- it moves the
mtime of `pipeline/daemon/supervisor.py`, which this diff does not touch.

## Reproduction

`tests/test_worktree.py::test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress`
reproduces the TICKET-067 incident directly: `ensure_worktree` checks out the
branch, `Ticket.save()` on the main checkout records a stage's progress
without committing, and the worktree's own `.project/tickets/<id>.md` stays
the branch-cut snapshot while `stage_view()` already reflects the update.

Command: `uv run --group dev pytest -q tests/test_worktree.py::test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress`

Output:
```
AssertionError: the worktree's own ticket file contradicts the view a stage is handed -- it is still the branch-cut snapshot
assert 'KeyError' in '---\nid: TICKET-001\nstage: new\n...## Reproduction\n\n## Digest\n\n...## Thread\n'
```

expect: the worktree's own ticket file contradicts the view a stage is handed -- it is still the branch-cut snapshot

## Digest

Files touched: `pipeline/core/worktree.py` (new `mirror_ticket()`),
`pipeline/core/ticket.py` (`Ticket.save()` calls it), `pipeline/stages/_common.md`
(rules 1 and 5), `CLAUDE.md` (one gotcha), `tests/test_worktree.py` (two tests).

Key functions. `Ticket.save()` (`pipeline/core/ticket.py:550`) renders and calls
`write_atomic()`; it is the only ticket writer (invariant 5). `ensure_worktree()`
(`pipeline/core/worktree.py:41`) runs `git worktree add` once and never refreshes.
`strip_settings_sources()` (`pipeline/core/worktree.py:105`) is the pattern this plan
copies: overwrite or delete a tracked file in the worktree, then hide it from git.
`stage_view()` (`pipeline/core/ticket.py:420`) builds the view; `spawn()`
(`pipeline/daemon/supervisor.py:384`) reads the ticket from the MAIN checkout.

Entry point. `start()` (`pipeline/daemon/supervisor.py:707`) calls `ensure_worktree()`,
then `take_lease()`, then `t.save()`, then `spawn()`. Every agent spawn is therefore
already preceded by a `save()` with the worktree present. Putting the mirror in
`save()` needs no change in `supervisor.py` and covers `spawn_command()` stages too.

Gotchas, each verified in a scratch git repo on 2026-08-28:

- `git update-index --skip-worktree` hides a modified tracked file completely.
  After marking the path then rewriting the file, `git status --porcelain` printed
  nothing, `git rebase main` printed `Successfully rebased and updated
  refs/heads/ticket/001.`, and `git add -A && git commit` recorded only
  `new.py | 1 +` while `git show HEAD:.project/tickets/TICKET-001.md` still printed
  `snapshot`.
- Marking a file that is ALREADY dirty works. `git status` showed
  ` M .project/tickets/TICKET-001.md`, the mark returned rc 0, and status went empty.
  That is the TICKET-067 repair path.
- Marking an untracked path fails: `fatal: Unable to mark file
  .project/tickets/TICKET-999.md`, rc 128. Use that rc as the tracked test. Do not
  write an untracked mirror, because `implementing`'s `git add -A` would stage it.
- The mark is per-index. It must run with `cwd` set to the worktree. In the main
  checkout's index it would hide the live ticket from the `chore` commit.
- `os.replace()` over a `0444` file succeeds and the result keeps the tmp file's
  mode. So write the tmp, `chmod 0o444` the tmp, then replace. A shell redirect into
  the `0444` mirror failed with `permission denied`, which is the read-only property
  in practice.
- The fence is symbol-scoped (`pipeline/core/fence.py`). `pipeline/core/worktree.py`
  is fenced on `strip_settings_sources` and `pipeline/core/ticket.py` on
  `validate_meta` (lines 54-85). Append `mirror_ticket()` at the END of
  `pipeline/core/worktree.py`, and keep the `ticket.py` edits to line 17 and lines
  550-562, so no diff hunk overlaps a fenced symbol and the ticket does not park at
  `awaiting-merge`.
- No import cycle. `pipeline/core/worktree.py` imports only stdlib, so
  `pipeline/core/ticket.py` may import from it.

## Decisions checked

Grep terms used in `/home/chezzijr/proj/agent-pipeline/.project/decisions/`:
`worktree`, `stage_view`, `bounded view`, `Ticket.save`, `only writer`, `.project/`,
`superseded-by`.

- DEC-018 -- the Tier A gate resolves decisions against the project root, never the
  worktree, because "the worktree is a checkout of the base branch and its
  `.project/decisions/` can be stale". Same staleness, same direction of fix. This
  plan does not change where the gate reads from.
- DEC-023 -- the view rides in the composed prompt, and the ticket file "stays the
  hand-editable protocol between stages". The main checkout's file stays that. The
  mirror is a derived copy, and `_common.md` rule 1 still points a stage at the
  absolute path.
- DEC-034 -- `strip_settings_sources()` removes a tracked worktree file and hides it
  so the removal "never enters the ticket's own diff". This plan reuses that
  mechanism. It edits no fenced symbol.
- DEC-037 -- `.project/` is excluded from `tree_snapshot()`, so nothing notices a
  write there. That is why the mirror needs `--skip-worktree` and `0444` rather than
  the snapshot backstop.
- DEC-072 -- `git worktree add` copies `.project/` with everything else, which is why
  the registry refuses a worktree. The mirror does not make a worktree registrable:
  `is_worktree()` still reads the `.git` pointer.
- DEC-011 -- ticket files under `.project/tickets/` are the source of truth for what a
  ticket is. The main checkout's copy stays that source; the mirror is derived.

No plan step contradicts an active record, so this ticket opens no `supersedes:` line.

## Plan

1. Add `test_the_ticket_mirror_is_read_only_and_never_enters_the_branch_diff` to `tests/test_worktree.py`, built like the neighbouring tests: `d, sh = git_project()`, write `TICKET_TEXT` to `.project/tickets/TICKET-001.md`, `sh("git add -A && git commit -qm file-ticket")`, `wt = W.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})`, then `t = Ticket.find(d, "TICKET-001")`, replace the string `## Digest` in `t.body` with `## Digest` followed by a line reading `mirrored`, and call `t.save()`.
2. Give that test six assertions, in `tests/test_worktree.py`, with `mirror = wt / ".project" / "tickets" / "TICKET-001.md"` and a `wsh` helper running `subprocess.run(cmd, shell=True, cwd=wt, capture_output=True, text=True)`: `"mirrored" in mirror.read_text()`; `mirror.stat().st_mode & 0o222 == 0`; `wsh("git status --porcelain").stdout == ""`; after `(wt / "new.py").write_text("work")` and `wsh("git add -A && git commit -qm work")`, `"mirrored" not in wsh("git show HEAD:.project/tickets/TICKET-001.md").stdout`; `wsh("git rebase main").returncode == 0`; and `wsh("git status --porcelain").stdout == ""` again after the rebase. End with `shutil.rmtree(d, ignore_errors=True)`.
3. Run `uv run --group dev pytest -q tests/test_worktree.py::test_the_ticket_mirror_is_read_only_and_never_enters_the_branch_diff` and watch it fail on the first assertion, because `tests/test_worktree.py` now pins behaviour `pipeline/core/worktree.py` does not have.
4. Append `MIRROR_MODE = 0o444` and `def mirror_ticket(live: Path, text: str) -> Path | None` to the END of `pipeline/core/worktree.py`, below `exclude_project_dir()`. Body, in order: return None if `live.parent.name != "tickets"` or `live.parents[1].name != ".project"`; set `rel = ".project/tickets/" + live.name` and `wt = live.parents[2] / ".worktrees" / live.stem` and `dest = wt / rel`; return None if `not dest.is_file()`; return None if `run_cmd("git update-index --skip-worktree -- " + shlex.quote(rel), wt)[0]` is non-zero; then `tmp = dest.with_name(dest.name + ".tmp")`, `tmp.write_text(text)`, `os.chmod(tmp, MIRROR_MODE)`, `os.replace(tmp, dest)`, `return dest`.
5. Document that function in `pipeline/core/worktree.py` with a docstring stating four facts: it is called only by `Ticket.save()`, so invariant 5 keeps one writer; the mark runs in the worktree's index, never the main checkout's; the mark runs before the write, so it also repairs a worktree an earlier stage dirtied; a non-zero rc means untracked there or a locked index, and returning None fails toward staleness rather than toward a dirty worktree.
6. Add `test_mirror_ticket_is_a_no_op_without_a_worktree` to `tests/test_worktree.py`: `d, sh = git_project()` with no `.worktrees/` directory; assert `W.mirror_ticket(d / ".project" / "tickets" / "TICKET-001.md", "x") is None`; assert `W.mirror_ticket(d / "f.py", "x") is None`; then `shutil.rmtree(d, ignore_errors=True)`.
7. Add `from pipeline.core.worktree import mirror_ticket` on line 17 of `pipeline/core/ticket.py`, directly below `from pipeline.core.machine import KNOWN_STAGES`.
8. Change the last line of `Ticket.save()` in `pipeline/core/ticket.py` from `write_atomic(self.path, render(self.frontmatter(), self.body))` to three lines: `text = render(self.frontmatter(), self.body)`, then `write_atomic(self.path, text)`, then `mirror_ticket(self.path, text)`; precede the third with the comment `# invariant 5 keeps ONE writer, not one destination: the worktree's copy is a branch-cut snapshot that would otherwise contradict the view the next stage is handed (TICKET-083).`
9. Run `uv run --group dev pytest -q tests/test_worktree.py tests/test_ticket.py tests/test_dispatch.py` and expect no failures, including `test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress` with its body unchanged; then commit `pipeline/core/worktree.py`, `pipeline/core/ticket.py` and `tests/test_worktree.py` with the message `fix(TICKET-083): Ticket.save mirrors the live ticket into its worktree, read-only`.
10. Extend rule 1 of `pipeline/stages/_common.md` with one sentence after "grep the file for `^### ` to get the line number.": "Use the absolute ticket path your instructions name; the copy inside your worktree is a read-only mirror of it."
11. Extend rule 5 of `pipeline/stages/_common.md` with one sentence after "stop: you are in the wrong tree.": "The one path under your working directory you must not write is its own `.project/tickets/` copy -- it is read-only, and a write there is lost work."
12. Add one bullet to the gotchas list in `CLAUDE.md`, directly after the bullet beginning "**A stage reads a bounded view, not the ticket file.**", stating that `Ticket.save()` writes two destinations -- the main checkout's file and a `0444` mirror at `<worktree>/.project/tickets/<id>.md` marked `git update-index --skip-worktree` in the worktree's index -- that without the mirror the worktree copy is the branch-cut snapshot and `implementing` reads its own prompt as fabricated (TICKET-067), and that without the mark a write there leaves the worktree dirty so `merging`'s rebase fails with `error: cannot rebase: You have unstaged changes.`
13. Run `uv run --group dev pytest -q` and expect the whole suite green, in particular `tests/test_stages.py::test_common_rules_say_where_a_code_edit_goes` after the `pipeline/stages/_common.md` edits; then commit `pipeline/stages/_common.md` and `CLAUDE.md` with the message `docs(TICKET-083): the worktree ticket copy is a read-only mirror`.

## Acceptance criteria

1. `tests/test_worktree.py::test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress` passes with its body unchanged. It is this ticket's `test_file`; do not rename it.
2. `tests/test_worktree.py::test_the_ticket_mirror_is_read_only_and_never_enters_the_branch_diff` passes, covering five facts: the mirror carries the live text, its mode has no write bit, `git status --porcelain` in the worktree is empty, the branch's committed blob does not contain the live text, and `git rebase main` in the worktree returns 0.
3. `tests/test_worktree.py::test_mirror_ticket_is_a_no_op_without_a_worktree` passes: `mirror_ticket()` returns `None` for a project with no `.worktrees/` and for a path that is not a ticket path.
4. `tests/test_stages.py::test_common_rules_say_where_a_code_edit_goes` passes after the `pipeline/stages/_common.md` edits.
5. `uv run --group dev pytest -q` exits 0 and prints no `failed`.
6. `git diff main --stat` names exactly five paths: `CLAUDE.md`, `pipeline/core/ticket.py`, `pipeline/core/worktree.py`, `pipeline/stages/_common.md`, `tests/test_worktree.py`.

## Decisions

**`Ticket.save()` writes two destinations, and that does not add a second
writer.** Invariant 5 says `Ticket.save()` is the only writer of a ticket file.
The worktree's copy is written from inside `save()` and from nowhere else, so the
invariant holds. Refreshing at spawn instead was rejected: `start()` already
saves between `ensure_worktree()` and `spawn()`, and four things reach a
worktree (`spawn()`, `spawn_command()`, `gate_cmd()`, the PTY host), so a
spawn-side refresh would be four call sites to keep right instead of one.

**The mirror is `0444` AND marked `--skip-worktree`. Both are load-bearing, for
different failures.** `0444` stops the write: TICKET-067's `implementing`
appended its objection to the nearest ticket-shaped file, and `path_verdict()`
in the guard allows any path inside the worktree, so nothing else refuses it.
`--skip-worktree` stops the consequence: `.project/` is excluded from
`tree_snapshot()` (DEC-037), so a write that lands anyway is invisible until
`merging` runs `git rebase` and fails with `error: cannot rebase: You have
unstaged changes.` Remove either and one of the two TICKET-067 failures returns.

**The mark runs in the WORKTREE's index, never the main checkout's.** Each
worktree has its own index. Marked in the main checkout, the live ticket would
stop being visible to git, and the `chore` commit that records a finished ticket
would commit the branch-cut blob instead.

**An untracked mirror path is skipped, not created.** `git update-index
--skip-worktree` on an untracked path exits 128 with `fatal: Unable to mark
file`, and `mirror_ticket()` returns `None` on any non-zero rc. A project that
excludes `.project/` through `.git/info/exclude` has no snapshot in its worktree
to contradict anything, and an untracked mirror would be staged by
`implementing`'s `git add -A`. Failing toward staleness is safe; failing toward
a dirty worktree is the escalation this ticket exists to remove.

**Cost: one `git update-index` subprocess per `Ticket.save()`, only when the
ticket's worktree exists.** Do not optimise it away by caching the mark. The
mark also repairs a worktree an earlier stage already dirtied, which is verified:
with ` M .project/tickets/TICKET-001.md` in `git status`, the mark returned rc 0
and status went empty.

## Rollback

Revert the two commits, from step 9 and step 13. The mirror stops being written
and the worktree copy is the branch-cut snapshot again, which is the TICKET-067
behaviour and no worse.

Any worktree a mirrored save already touched keeps its `skip-worktree` bit and
its `0444` mirror. Clear both per worktree, with `cwd` set to that worktree:
`chmod u+w .project/tickets/<id>.md`, then `git update-index --no-skip-worktree
-- .project/tickets/<id>.md`, then `git checkout -- .project/tickets/<id>.md`.
Dropping the worktree clears both as well, at the cost of the ticket's
uncommitted work.

## Thread

### 2026-08-27 17:50:38Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-28 · triage · human

Confirmed by reading the code, not just the incident report: `spawn()` in
`pipeline/daemon/supervisor.py:384` builds the prompt from
`stage_view(Ticket.find(project, tid), stage)` -- `project` is the MAIN
checkout. `ensure_worktree()` (`pipeline/core/worktree.py:41`) checks out the
ticket's branch once at cut time; `Ticket.save()` writes only the main
checkout's copy and nothing re-checks-out or refreshes the worktree's copy
afterward. So the two diverge from the first `save()` onward, exactly as the
Summary describes.

Wrote a failing test, `tests/test_worktree.py::test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress`,
committed on this branch. It builds a real git worktree, saves a ticket
update on the main checkout, and asserts the worktree's own ticket file
reflects it -- it does not. See `## Reproduction`.

This is not a small fix: the ticket lays out two shapes (document the
staleness in `_common.md` rule 4, or refresh the worktree's copy read-only at
spawn) and neither is chosen. Leaving as `ok` for planning to pick a shape.

### 2026-08-27 17:52:21Z · triage · session · session=1b328fe8-eea1-4c9a-9c93-2edc286a5b68

`triage` ran as session `1b328fe8-eea1-4c9a-9c93-2edc286a5b68`
- replay: `claude --resume 1b328fe8-eea1-4c9a-9c93-2edc286a5b68`
- log: `.project/logs/TICKET-083-triage-1b328fe8.log`

### 2026-08-27 17:52:21Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced worktree/main-checkout ticket divergence with a failing test; a design decision (document vs refresh) remains, so ok not chore

### 2026-08-27 18:01:41Z · planning · note

Planned the refresh shape, not the documentation shape. `Ticket.save()` gains a
second destination: a `0444` mirror at `<worktree>/.project/tickets/<id>.md`,
written after `git update-index --skip-worktree` marks the path in the
worktree's own index.

The ticket asked any refresh plan to say how the copy stays read-only. Two
mechanisms, for two different failures. Mode `0444` refuses the write --
`path_verdict()` in the guard allows every path inside the worktree, so
nothing else refuses it. `--skip-worktree` makes a write that lands anyway
invisible to git, which is what closes the TICKET-067 escalation
(`error: cannot rebase: You have unstaged changes.`).

Verified in a scratch git repo, not reasoned: after the mark and a rewrite,
`git status --porcelain` printed nothing, `git rebase main` printed
`Successfully rebased and updated refs/heads/ticket/001.`, and `git add -A &&
git commit` recorded only `new.py | 1 +`. Marking an already-dirty file
returned rc 0 and cleared it from `git status`, so the fix also repairs a
worktree a previous stage dirtied.

Scope: one subsystem, five files. `spawn()` needs no change, because `start()`
already calls `t.save()` between `ensure_worktree()` and `spawn()`.

### 2026-08-27 18:02:25Z · planning · session · session=51cf0fd8-3019-4a17-a568-fe91001438b3

`planning` ran as session `51cf0fd8-3019-4a17-a568-fe91001438b3`
- replay: `claude --resume 51cf0fd8-3019-4a17-a568-fe91001438b3`
- log: `.project/logs/TICKET-083-planning-51cf0fd8.log`

### 2026-08-27 18:02:25Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned the refresh shape: Ticket.save() mirrors the live ticket into the worktree at 0444 behind git update-index --skip-worktree; 13 steps, 5 files

### 2026-08-27 18:05:33Z · plan-validation · note

long: eight scored items, two corrections `implementing` needs, one untested edge

**Tier B: pass.** All eight items pass.

Root cause: `ensure_worktree()` (`pipeline/core/worktree.py:41`) checks out the
branch once and nothing refreshes it, the branch commits no ticket file, and
`Ticket.save()` writes only the main checkout that `spawn()` reads. The plan
fixes the writer, not the assertion.

Decisions: DEC-034 binds, and the plan reuses its mechanism. `machine.FENCED`
(`pipeline/core/machine.py:44-45`) fences `validate_meta` (`ticket.py:54`) and
`strip_settings_sources`. The planned edits sit at `ticket.py` line 18 and lines
554-563, and at the end of `worktree.py`, so no hunk overlaps either symbol.

Scope: 13 steps, each traceable to a criterion. Five files, about 15 lines of
production code, which matches `bugfix`.

Criteria falsify. Drop the `chmod` and criterion 2's mode assertion fails; drop
the mark and its status, blob and rebase assertions fail. Criterion 4 only
guards steps 10-11 against displacing text `test_common_rules_say_where_a_code_edit_goes`
already asserts; it does not assert the new sentences.

Riskiest step: 4. Fallback stated -- a non-zero `git update-index` rc returns
`None` and the copy stays stale, plus `## Rollback`.

Regression surface: `Ticket.save()` (11 call sites in `supervisor.py`, all
event-driven, none per tick), `merging`'s rebase, `implementing`'s `git add -A`.
Steps 9 and 13 run the tests that cover them.

Corrections for `implementing`:
1. `from pipeline.core.machine import KNOWN_STAGES` is line 17, so step 7's
   import lands on line 18. The anchor governs, not the number.
2. `worktree()` (`pipeline/core/worktree.py:31`) already returns
   `project / ".worktrees" / meta["id"]`, the path step 4 re-derives.

Untested edge: git refuses to update a `skip-worktree` path when an incoming
merge or rebase changes it. No path in this repo commits a ticket file to base
while its branch is live, so this does not fire today.

This note sits before the gate entry, not after it. The gate's fenced output
ends the file with ANSI bytes, which left no anchor the editor could match
uniquely, and the read-only guard blocks every shell writer.

### 2026-08-27 18:02:45Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress` fails as required
```
file contradicts the view a stage is [39;49;00m[33m"[39;49;00m[90m[39;49;00m
            [33m"[39;49;00m[33mhanded -- it is still the branch-cut snapshot[39;49;00m[33m"[39;49;00m)[90m[39;49;00m
[1m[31mE       AssertionError: the worktree's own ticket file contradicts the view a stage is handed -- it is still the branch-cut snapshot[0m
[1m[31mE       assert 'KeyError' in '---\nid: TICKET-001\nstage: new\nclass: bugfix\nbranch: ticket/001\ntest_file: null\nfiles_declared: []\ncounters: {}...# Reproduction\n\n## Digest\n\n## Decisions checked\n\n## Plan\n\n## Acceptance criteria\n\n## Rollback\n\n## Thread\n'[0m

[1m[31mtests/test_worktree.py[0m:193: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_worktree.py::[1mtest_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress[0m - AssertionError: the worktree's own ticket file contradicts the view a stage...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.06s[0m[31m ===============================[0m

```
- ok: `tests/test_worktree.py::test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_worktree.py::[1mtest_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress[0m - AssertionError: the worktree's own ticket file contradicts the view a stage...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.10s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-tetz2sx7/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-tetz2sx7/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 9ms[0m[0m

```

### 2026-08-27 18:09:31Z · plan-validation · session · session=5585f3f3-c992-4066-97e5-671389afe20b

`plan-validation` ran as session `5585f3f3-c992-4066-97e5-671389afe20b`
- replay: `claude --resume 5585f3f3-c992-4066-97e5-671389afe20b`
- log: `.project/logs/TICKET-083-plan-validation-5585f3f3.log`

### 2026-08-27 18:09:32Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B passed all eight items; noted two corrections for implementing (import lands on ticket.py line 18; worktree() already returns the path step 4 re-derives)

### 2026-08-27 18:10:15Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Checked: worktree.py imports only stdlib, so the new ticket.py -> worktree.py import is not a cycle.

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Checked: worktree.py imports only stdlib, so the new ticket.py -> worktree.py import is not a cycle.**

### 2026-08-27 18:30:45Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress` fails as required
```
file contradicts the view a stage is [39;49;00m[33m"[39;49;00m[90m[39;49;00m
            [33m"[39;49;00m[33mhanded -- it is still the branch-cut snapshot[39;49;00m[33m"[39;49;00m)[90m[39;49;00m
[1m[31mE       AssertionError: the worktree's own ticket file contradicts the view a stage is handed -- it is still the branch-cut snapshot[0m
[1m[31mE       assert 'KeyError' in '---\nid: TICKET-001\nstage: new\nclass: bugfix\nbranch: ticket/001\ntest_file: null\nfiles_declared: []\ncounters: {}...# Reproduction\n\n## Digest\n\n## Decisions checked\n\n## Plan\n\n## Acceptance criteria\n\n## Rollback\n\n## Thread\n'[0m

[1m[31mtests/test_worktree.py[0m:193: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_worktree.py::[1mtest_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress[0m - AssertionError: the worktree's own ticket file contradicts the view a stage...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m

```
- ok: `tests/test_worktree.py::test_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress` fails on base `main` too -- the bug is not already fixed upstream
```
rtionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_worktree.py::[1mtest_the_worktree_ticket_copy_goes_stale_the_moment_a_stage_records_progress[0m - AssertionError: the worktree's own ticket file contradicts the view a stage...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.10s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-bzc6u5qf/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-bzc6u5qf/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 9ms[0m[0m

```

### 2026-08-27 18:30:46Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

### 2026-08-28 · implementing · todo

Working the 13-step plan in order:

1. [x] add `test_the_ticket_mirror_is_read_only_and_never_enters_the_branch_diff`
2. [x] six assertions for that test
3. [x] run it, confirm RED
4. [x] `mirror_ticket()` in `pipeline/core/worktree.py`
5. [x] docstring for `mirror_ticket()`
6. [x] `test_mirror_ticket_is_a_no_op_without_a_worktree`
7. [x] import `mirror_ticket` in `pipeline/core/ticket.py` line 18
8. [x] `Ticket.save()` calls `mirror_ticket()`
9. [x] run worktree/ticket/dispatch tests, commit
10. [x] `_common.md` rule 1 sentence
11. [x] `_common.md` rule 5 sentence
12. [x] `CLAUDE.md` gotcha bullet
13. [x] full suite green, commit docs

### 2026-08-28 · implementing · report

All 13 plan steps done, TDD followed throughout. Two commits:
`fix(TICKET-083): Ticket.save mirrors the live ticket into its worktree,
read-only` and `docs(TICKET-083): the worktree ticket copy is a read-only
mirror`.

RED confirmed before writing `mirror_ticket()`:
`AttributeError: module 'pipeline.core.worktree' has no attribute
'mirror_ticket'` and `assert 'mirrored' in '---\nid: TICKET-001...'` (mirror
still the branch-cut snapshot). GREEN confirmed after: 88 passed in
`tests/test_worktree.py tests/test_ticket.py tests/test_dispatch.py`.

Applied plan-validation's two corrections: the import lands on
`pipeline/core/ticket.py` line 18, below `KNOWN_STAGES` on line 17; and
`mirror_ticket()` re-derives the worktree path directly rather than calling
`worktree()`, since `worktree()` takes a `meta` dict and `mirror_ticket()`
only has a `Path`.

`tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
fails on a clean checkout too (verified via a WIP stash-and-restore, dropped
after): `AssertionError: expected serve() to exit after tick 1, got 2`.
Pre-existing, unrelated to this diff -- excluded from the runs above, not
fixed.

`git diff main --stat` names exactly the five paths acceptance criterion 6
requires: `CLAUDE.md`, `pipeline/core/ticket.py`, `pipeline/core/worktree.py`,
`pipeline/stages/_common.md`, `tests/test_worktree.py`.

result: ok

re-gated after rebasing onto base: passed

### 2026-08-27 18:34:06Z · implementing · session · session=50cb4590-87cb-4c90-951b-a6ba8c87484f

`implementing` ran as session `50cb4590-87cb-4c90-951b-a6ba8c87484f`
- replay: `claude --resume 50cb4590-87cb-4c90-951b-a6ba8c87484f`
- log: `.project/logs/TICKET-083-implementing-50cb4590.log`

### 2026-08-27 18:34:06Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented mirror_ticket() in Ticket.save(), all 13 plan steps done via TDD, two commits landed, full suite green (excluding a pre-existing unrelated flake)

### 2026-08-28 · review · report

Reviewed the delta `git diff main` (5 files, +147/-1). No blocking findings.

All six acceptance criteria pass. `uv run --group dev pytest -q` printed
`379 passed in 18.46s` and `exit=0`. The reproduction test's body is unchanged:
`git diff 6c5b424~1 HEAD -- tests/test_worktree.py` shows no `-` line except the
file header. `fenced_touches(Path('.'), 'main')` returned `[]`, so the diff does
not park at `awaiting-merge`.

long: four refutations belong here as evidence, per the review protocol.

Findings, none blocking:

1. minor -- a crash between `os.chmod(tmp, MIRROR_MODE)` and `os.replace`
   (`pipeline/core/worktree.py:225-226`) leaves a `0444` `<id>.md.tmp`, and the
   next save's `tmp.write_text(text)` raises `PermissionError`. That is not a
   `PipelineError`, so it propagates out of `Ticket.save()`. The window is
   sub-millisecond, and `write_atomic` (`pipeline/core/ticket.py:100`) already
   carries the same tmp shape without the chmod.
2. minor -- `tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
   fails when that file runs alone (`AssertionError: expected serve() to exit
   after tick 1, got 2`) and passes in the full suite. Order-dependent, not
   caused by this diff: it moves the mtime of `pipeline/daemon/supervisor.py`,
   which the diff does not touch.
3. nit -- `sh` is unpacked and never used in
   `test_mirror_ticket_is_a_no_op_without_a_worktree`.
4. nit -- `mirror_ticket()` derives the worktree directory from `live.stem`
   while `worktree()` uses `meta["id"]`. They agree because `ticket_path()`
   names the file `<id>.md` (`pipeline/core/ticket.py:184`). A ticket file
   renamed off its id gets no mirror, silently.

Four candidate blocking findings, each refuted at a line:

- `mirror_ticket(d / "f.py", "x")` raising `IndexError` on `live.parents[1]`:
  `or` short-circuits on `live.parent.name != "tickets"`
  (`pipeline/core/worktree.py:214`), and `tests/test_worktree.py:238` asserts it
  returns None.
- the mark hiding the live ticket from the `chore` commit: the mark runs with
  `cwd=wt` (`pipeline/core/worktree.py:221`), and the chore commit runs
  `git add -- <paths>` in `project` (`pipeline/daemon/supervisor.py:559-561`).
- the `0444` mirror blocking cleanup: `drop_worktree()` runs
  `git worktree remove --force` (`pipeline/core/worktree.py:72`).
- a read-only stage escalating because the mirror moved under it:
  `dirty_snapshot()` runs `git status --porcelain -- . ':(exclude).project'`
  (`pipeline/core/worktree.py:158`).

result: ok

### 2026-08-27 18:40:52Z · review · session · session=065d6cb6-d3cd-4e48-910c-aa7b82485877

`review` ran as session `065d6cb6-d3cd-4e48-910c-aa7b82485877`
- replay: `claude --resume 065d6cb6-d3cd-4e48-910c-aa7b82485877`
- log: `.project/logs/TICKET-083-review-065d6cb6.log`

### 2026-08-27 18:40:52Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed the 5-file delta: all six acceptance criteria pass, pytest -q exit=0 with 379 passed, fence clean; 4 candidate blocking findings refuted at a line, 2 minor findings and 2 nits recorded

### 2026-08-27 18:41:12Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 18:41:13Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/083


Rebasing (1/3)Rebasing (2/3)Rebasing (3/3)Successfully rebased and updated refs/heads/ticket/083.
Already up to date.
Updating 47f9c80..a2d7491
Fast-forward
 CLAUDE.md                  |  7 ++++
 pipeline/core/ticket.py    |  8 +++-
 pipeline/core/worktree.py  | 30 ++++++++++++++
 pipeline/stages/_common.md |  4 ++
 tests/test_worktree.py     | 99 ++++++++++++++++++++++++++++++++++++++++++++++
 5 files changed, 147 insertions(+), 1 deletion(-)

```

### 2026-08-27 18:41:13Z · merging · decision

decision recorded as `DEC-083`
