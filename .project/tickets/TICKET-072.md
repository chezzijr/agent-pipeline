---
id: TICKET-072
stage: done
class: bugfix
branch: ticket/072
test_file: tests/test_registry_worktree.py::test_register_refuses_a_worktree_of_a_registered_project
files_declared:
- CLAUDE.md
- README.md
- pipeline/daemon/registry.py
- tests/conftest.py
- tests/test_registry_worktree.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 17
  plan_files: 5
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 6d2627a3-3489-4c97-92ab-66b6f4977f3c
  log: .project/logs/TICKET-072-review-6d2627a3.log
approved_by: chezzijr (via Claude Code, while away; reviewer also filed this ticket
  -- audit in thread)
approved_at: '2026-08-27T16:36:49.644760+00:00'
---

## Summary

Reviewed, no blocking findings. Every acceptance criterion re-run on this
worktree: `tests/test_registry_worktree.py` `4 passed`, full suite
`354 passed`, `./pipeline/hooks/test_dangerous_commands.py` `guard: all
passed`, and `git diff ec9017f HEAD --stat -- pipeline/hooks/
pipeline/harnesses/` is empty. Three non-blocking nits are in the review
thread entry.

Implemented, all steps 1-17 done, plan followed as written.

`is_worktree()` in `pipeline/daemon/registry.py` reads the `.git` file's
`gitdir:` pointer; a worktree's parent directory name is `worktrees`, a
submodule's is `modules`. `register()` raises `PipelineError` naming
`worktree` when it sees one; `projects()` skips one already in the file.
`register()`/`unregister()` also each raise `PipelineError` containing
`operator state` when `PIPELINE_STAGE` is set. `tests/conftest.py` pops that
variable so the suite's own `registry.register()` calls (test_daemon.py,
test_dispatch.py, test_harness.py) still run. `pipeline/hooks/
dangerous-commands.py` is untouched, its own suite green, diff empty.

All four named tests in `tests/test_registry_worktree.py` pass individually
and together (`4 passed`). Full suite: `354 passed`. Guard suite: `all
passed`.

One deviation from the plan, not a step: step 9's test registers a plain
`project()` fixture, which carries a real `TICKET-001` ticket and collided
with `tests/test_daemon.py`'s own `TICKET-001` project on the shared
registry when both files ran together (`XDG_CONFIG_HOME` is a process-wide
env var, last writer at import time wins for every test in the run). Added an
`unregister(p)` in a `finally` -- the convention `test_daemon.py` already
uses -- fixing `test_ls_reads_ticket_files_and_refuses_an_unregistered_project`
from failing under the combined run. No plan step named this file or this
fixture choice, so it counts as coverage hygiene, not a plan change.

Five commits, one per plan-designated stopping point: `ad779e2` (step 5),
`f0416ff` (step 8), `66ecf4e` (step 10), `8f7edb1` (step 14), `fac3e77`
(steps 15-17, docs).

The original report follows, for context only -- superseded by the above.

Observed live on 2026-08-27. `TICKET-068`'s `planning` stage ran
`pipeline register .` inside its own checkout while exploring the command the
ticket is about, and it took:

    $ pipeline projects
    /home/chezzijr/proj/agent-pipeline
    /home/chezzijr/proj/chezzilang
    /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068

The first visible symptom was `pipeline ls` printing every ticket twice --
once from the real project and once from the worktree's branch-time copy of
`.project/tickets/`, all at stage `new`. 154 rows for 82 tickets.

`register()` (`pipeline/daemon/registry.py:60`) validates three things: a
`.project/` exists, the path carries no newline or `#`, and it is not already
listed. A worktree of a registered project satisfies all three, because
`git worktree add` copies `.project/` along with everything else.

Why it escaped every containment the design has: the registry file lives at
`$XDG_CONFIG_HOME/pipeline/projects` (else `~/.config`), so the write is
outside the worktree, outside the ticket's diff, outside `tree_snapshot()`,
outside `machine.FENCED`, and outside review. Nothing recorded it. It was
found because `ls` looked wrong.

Nothing executed from the entry here: `pipeline run` serves one project. Under
`pipeline start`, which drains every registered project, the daemon would tick
a directory a stage registered, whose `.project/tickets/` that same stage can
write -- `.project/` is excluded from the read-only snapshot on purpose, and
Bash reaches it. That is the case this ticket is about, not the duplicate rows.

The guard is not at fault and must not be changed for this. `planning` is
`write: true`, so `pipeline/hooks/dangerous-commands.py` applies its blocklist,
and `pipeline register` is not a dangerous command by any pattern. A read-only
stage would have been stopped by the allowlist already.

Expected: a stage cannot add an entry to the operator's registry that the
daemon will then serve. A worktree of an already-registered project is the
concrete case to refuse, and `pipeline projects` should not list one.

Two suggestions, neither a decision -- the shape of the fix is planning's to
choose:

- Refuse at `register()`: a path under a registered project's `.worktrees/`,
  or any path whose `git rev-parse --git-common-dir` differs from its
  `--git-dir`, is a worktree and not a project.
- Refuse at the source: the registry is operator state, and no stage has a
  reason to write it. A spawned stage could be denied the verb outright.

The first is narrow and testable today. The second is the invariant, and needs
a mechanism that does not become pattern matching in the guard.

## Reproduction

`tests/test_registry_worktree.py::test_register_refuses_a_worktree_of_a_registered_project`

Command: `uv run --group dev pytest -q tests/test_registry_worktree.py`

Builds a git project with `.project/` committed, registers it, adds a
worktree under `.worktrees/TICKET-068` (mirrors the real layout), and calls
`registry.register(wt)`. It succeeds and the worktree lands in
`registry.projects()`.

expect: AssertionError: register() accepted a worktree of a registered project

Full failure:
```
E       AssertionError: register() accepted a worktree of a registered project: /tmp/tmpdaklea8m/.worktrees/TICKET-068 is in [PosixPath('/tmp/tmpdaklea8m'), PosixPath('/tmp/tmpdaklea8m/.worktrees/TICKET-068')]
E       assert PosixPath('/tmp/tmpdaklea8m/.worktrees/TICKET-068') not in [PosixPath('/tmp/tmpdaklea8m'), PosixPath('/tmp/tmpdaklea8m/.worktrees/TICKET-068')]
```

## Digest

Files touched: `pipeline/daemon/registry.py` (the fix),
`tests/test_registry_worktree.py` (triage's repro, extended),
`tests/conftest.py`, `README.md`, `CLAUDE.md`.

Key functions: `register()` (`pipeline/daemon/registry.py:60`) resolves the
path, requires `.project/`, refuses `\n` and `#`, dedupes against
`projects()`. `projects()` (line 45) is the filtered view -- it drops a line
that is not absolute or has no `.project/`, and its docstring says a line is
hand-editable and so is checked like any other input. `unregister()` drops the
raw line, not the filtered entry. `_raw()`/`_write()` own the file.

Entry points: `cmd_register` (`pipeline/cli/main.py:292`) is the only caller of
`register()`; `cmd_unregister` (line 296) of `unregister()`. `cmd_ls`,
`cmd_projects` and `serve()` (`pipeline/daemon/supervisor.py:1342`) all iterate
`registry.projects()`, so filtering there stops the daemon ticking a worktree
line that is already in the operator's file. `pipeline init` does not register.

Detection, verified on this checkout 2026-08-27: a linked worktree's `.git` is
a **file**, `gitdir: /home/chezzijr/proj/agent-pipeline/.git/worktrees/TICKET-072`;
`git rev-parse --git-dir` and `--git-common-dir` differ for it and match in the
main checkout. Reading the `.git` file needs no subprocess, which matters
because `projects()` runs on every tick; a submodule also has a `.git` file,
and its pointer's parent directory is `modules`, not `worktrees`. Ran:

    python3 -c '<is_worktree body>'   # worktree True, main checkout False, /tmp False

Gotchas:

1. `spawn()` sets `PIPELINE_STAGE` (`pipeline/daemon/supervisor.py:408`) for
   every agent stage. `spawn_command()` (line 499) does not, so `verifying` and
   the Tier A gate do not carry it.
2. A stage's Bash runs the suite with `PIPELINE_STAGE` set, and
   `tests/test_daemon.py` calls `registry.register()` in 8 tests. Refusing on
   that variable without clearing it in `tests/conftest.py` turns the whole
   suite red under `implementing`.
3. Triage's repro test calls `registry.register(wt)` unguarded, so a raise
   errors the test instead of passing it. Step 1 rewrites that call.
4. `registry.py` is not in `machine.FENCED`, so this diff does not park at
   `awaiting-merge` for the fence.
5. The operator's live registry still holds
   `/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068`. The
   `projects()` filter makes that line inert; nothing removes it.
6. `tests/helpers.py` gives `git_project()` (a git repo with `.project/`,
   `base=main`) and `project()` (no git at all). Both are used below.

## Decisions checked

- DEC-011 (active, frozen): the project registry is a text file and not a
  table, because deleting `events.db` must lose history and never state. This
  plan adds two refusals inside `registry.py` and no storage.
- DEC-034 (active) and DEC-052 (active): containment is enforced by the
  dispatcher and the guard's code, not by a flag. This plan changes neither
  `pipeline/hooks/dangerous-commands.py` nor
  `pipeline/harnesses/claude-code.toml`, as the ticket requires.
- DEC-041: superseded by DEC-052. History only, cited for the `--add-dir`
  reasoning; it binds nothing here.
- Grep terms over `.project/decisions/`: `registry`, `register`, `worktree`,
  `projects`, `registry.py`, `XDG_CONFIG_HOME`, `.worktrees`, `rev-parse`,
  `operator`. No record constrains `register()` itself.

## Plan

1. In `tests/test_registry_worktree.py`, rewrite the tail of `test_register_refuses_a_worktree_of_a_registered_project` so the bare `registry.register(wt)` becomes `try: registry.register(wt); assert False, "register() accepted a worktree of a registered project"` / `except PipelineError as e: assert "worktree" in str(e), e`, keep the existing `assert wt not in registry.projects()` with its message below it, and add `from pipeline.core import PipelineError` under the existing `from pipeline.daemon import registry` import.
2. Run `uv run --group dev pytest -q tests/test_registry_worktree.py` and expect it red with `AssertionError: register() accepted a worktree of a registered project` -- the same finding triage recorded, now raised by the `assert False`.
3. In `pipeline/daemon/registry.py`, add `def is_worktree(project: Path) -> bool` above `register()`: read `Path(project) / ".git"` with `read_text(encoding="utf-8", errors="replace")` inside `try/except OSError: return False` (a `.git` directory raises `IsADirectoryError`, a missing one `FileNotFoundError`), return `False` unless the stripped text starts with `gitdir:`, and otherwise return `Path(text.split(":", 1)[1].strip()).parent.name == "worktrees"`; document in its docstring that `git worktree add` copies `.project/` so a worktree passes every other check, and that a submodule's pointer names `modules` instead.
4. In `pipeline/daemon/registry.py`, inside `register()` and directly after the `.project/` check, raise `PipelineError(f"{project} is a git worktree, not a project -- register the main checkout instead")` when `is_worktree(project)`.
5. Run `uv run --group dev pytest -q tests/test_registry_worktree.py` and expect `1 passed`, then commit `pipeline/daemon/registry.py` and `tests/test_registry_worktree.py` as `fix(TICKET-072): register() refuses a linked git worktree`.
6. In `tests/test_registry_worktree.py`, add `test_projects_skips_a_worktree_line_already_in_the_registry`: build `git_project()`, `sh("git add -A .project && git commit -qm 'add .project'")`, `sh(f"git worktree add -b ticket/068 {wt} main")` with `wt = d / ".worktrees" / "TICKET-068"`, then `registry.registry_path().parent.mkdir(parents=True, exist_ok=True)`, `registry.registry_path().write_text(f"{d}\n{wt}\n")`, and assert `registry.projects() == [d], registry.projects()` -- the operator's file holds such a line today and no unregister runs.
7. In `pipeline/daemon/registry.py`, change the `projects()` filter line to `if q.is_absolute() and (q / ".project").is_dir() and not is_worktree(q) and q not in out:` (wrapped to fit), and extend that function's docstring with one sentence: a worktree line written before this check must go inert without an unregister.
8. Run `uv run --group dev pytest -q tests/test_registry_worktree.py` and expect `2 passed`, then commit both files as `fix(TICKET-072): projects() drops a worktree line`.
9. In `tests/test_registry_worktree.py`, add `test_register_still_accepts_a_main_checkout_and_a_plain_directory`: import `project` alongside `git_project` from `helpers`, register `git_project()`'s directory and `project()`'s directory, assert `registry.register(d) == d` and both appear in `registry.projects()`; this fails if the refusal is widened to any git repo or to any path under a `.worktrees/` directory.
10. Run `uv run --group dev pytest -q tests/test_registry_worktree.py` and expect `3 passed`, then commit `tests/test_registry_worktree.py` as `test(TICKET-072): register still accepts a main checkout`.
11. In `tests/conftest.py`, add `os.environ.pop("PIPELINE_STAGE", None)` below the `TMPDIR` line, with a comment: a stage's Bash runs this suite with `PIPELINE_STAGE` set, `registry.register()` refuses the operator's registry under that name, and a test process is not a stage.
12. In `tests/test_registry_worktree.py`, add `test_a_stage_cannot_register_or_unregister`: build `git_project()`, `registry.register(d)`, set `os.environ["PIPELINE_STAGE"] = "planning"`, then in a `try/finally` that ends with `del os.environ["PIPELINE_STAGE"]` call `registry.register(d)` and `registry.unregister(d)` and assert each raises `PipelineError` whose text contains `operator state`, and finally assert `d in registry.projects()`.
13. In `pipeline/daemon/registry.py`, add to `register()` and to `unregister()`, as the first statement of each, `stage = os.environ.get("PIPELINE_STAGE")` and `if stage: raise PipelineError(f"the registry is operator state: the {stage} stage cannot {verb} {project}")` with `verb` spelled literally `register` in one and `unregister` in the other; note in the docstring that this is a guardrail against an exploring stage, not a boundary, since the registry file is outside every containment the design has.
14. Run `uv run --group dev pytest -q tests/test_registry_worktree.py tests/test_daemon.py` and expect `4 passed` for the first file and no new failure in `tests/test_daemon.py`, then commit `pipeline/daemon/registry.py`, `tests/test_registry_worktree.py` and `tests/conftest.py` as `fix(TICKET-072): a spawned stage cannot write the registry`.
15. In `README.md`, below the `pipeline register ~/code/myproject` code block (line 129), add two sentences: `register` refuses a git worktree, because `git worktree add` copies `.project/` and the daemon would then tick a ticket's own checkout as a second project; and `register`/`unregister` refuse when `PIPELINE_STAGE` is set, because the registry is operator state.
16. In `CLAUDE.md`, add one bullet to *Gotchas, each found the hard way*: **The registry refuses a git worktree, and refuses a stage.** `is_worktree()` in `pipeline/daemon/registry.py` reads the `.git` *file*'s `gitdir:` pointer; `register()` raises and `projects()` skips, so a line written before the fix goes inert without an unregister. `register()`/`unregister()` also refuse when `PIPELINE_STAGE` is set -- a guardrail, not a boundary, since the registry lives outside the worktree, the ticket's diff and `machine.FENCED` (TICKET-072).
17. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect both green, then commit `README.md` and `CLAUDE.md` as `docs(TICKET-072): the registry refuses a worktree and a stage`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_registry_worktree.py::test_register_refuses_a_worktree_of_a_registered_project`
  passes: `register()` raises `PipelineError` naming `worktree`, and the
  worktree is absent from `registry.projects()`.
- `tests/test_registry_worktree.py::test_projects_skips_a_worktree_line_already_in_the_registry`
  passes: a hand-written registry holding `<project>` and
  `<project>/.worktrees/TICKET-068` yields `projects() == [<project>]`.
- `tests/test_registry_worktree.py::test_register_still_accepts_a_main_checkout_and_a_plain_directory`
  passes: a git main checkout and a non-git directory with `.project/` both
  register and both appear in `projects()`.
- `tests/test_registry_worktree.py::test_a_stage_cannot_register_or_unregister`
  passes: with `PIPELINE_STAGE=planning`, `register()` and `unregister()` each
  raise `PipelineError` containing `operator state`, and the project stays
  registered.
- `uv run --group dev pytest -q` is green, `tests/test_daemon.py` included --
  its 8 `registry.register()` calls still work because `tests/conftest.py`
  clears `PIPELINE_STAGE`.
- `./pipeline/hooks/test_dangerous_commands.py` is green and its diff is empty:
  the guard is not part of this fix.

## Decisions

**The registry refuses a linked git worktree, at `register()` and again in
`projects()`.** `git worktree add` copies `.project/` with everything else, so
a ticket's own checkout satisfies every other check `register()` makes, and the
daemon would then tick a directory a stage created and whose
`.project/tickets/` that stage can write. The second check is not redundant:
the operator's registry already holds such a line from 2026-08-27, `projects()`
is documented as where a hand-editable line is validated, and it is what
`serve()`, `cmd_ls` and `cmd_projects` all read. A worktree line therefore goes
inert without an unregister.

**The refusal is any linked worktree, not only one whose parent is
registered.** Registering the worktree *before* its parent would slip a
parent-scoped check, and a worktree shares its parent's object store and branch
namespace, so two dispatchers on the pair would fight over branches.

**`is_worktree()` reads the `.git` file, it does not shell out to `git
rev-parse`.** `projects()` runs on every tick, and its docstring justifies the
current cost as one stat plus a 200-byte read; two subprocesses per line per
tick would break that. The gitfile pointer is git's stable on-disk format:
`gitdir: <common>/worktrees/<name>` for a worktree, `<common>/modules/<name>`
for a submodule, which is why the check tests the pointer's parent directory
name and not merely that `.git` is a file. If a future git changes that layout,
the fallback is `git rev-parse --git-dir` versus `--git-common-dir`.

**`register()` and `unregister()` refuse when `PIPELINE_STAGE` is set, and that
is a guardrail, not a boundary.** It stops the exact incident -- a stage
running `pipeline register .` while exploring the command -- with a clear
error, and it covers a stage registering some other directory, which the
worktree check does not. It stops nothing deliberate: an agent can unset the
variable or write the file. Do not describe it as containment, and do not move
this check into `pipeline/hooks/dangerous-commands.py`, where it becomes the
pattern matching invariant 4 forbids.

**`tests/conftest.py` clears `PIPELINE_STAGE` for the whole suite.** A stage's
Bash runs `uv run --group dev pytest -q` with that variable set, and
`tests/test_daemon.py` registers projects in 8 tests. Without the pop, this
project's own `implementing` and `review` stages see a red suite that is green
for the operator. A test process is not a stage.

## Rollback

Revert the four commits from step 5, step 8, step 10 and step 14 (`git revert`
each, newest first); the doc commit from step 17 is text only. Each commit
stands alone: reverting step 14 restores `register()`/`unregister()` for a
spawned stage and leaves the worktree refusal in place, and reverting step 8
restores `projects()` while `register()` keeps refusing. If the worktree
refusal turns out to reject a checkout an operator wants registered, revert
step 5 too and the registry accepts anything with a `.project/`, as before.
Nothing here migrates the registry file, so no revert has to rewrite it.

## Thread

### 2026-08-27 16:15:56Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-27 · triage · reproduced · result=ok

Confirmed `register()` (`pipeline/daemon/registry.py:60`) has no worktree
check: it validates `.project/` exists, no `\n`/`#` in the path, and
dedup against the current list. Nothing distinguishes a worktree from a
real project. Added `tests/test_registry_worktree.py`, which builds a git
project with `.project/` committed, registers it, adds a worktree under
`.worktrees/TICKET-068`, and calls `register(wt)`. It succeeds and the
worktree lands in `registry.projects()` -- the exact bug the ticket
describes. Committed at `fdcd590`. This stage does not choose between the
ticket's two suggested fixes; that is planning's job.

### 2026-08-27 16:20:03Z · triage · session · session=b9f5c434-bed9-4793-836c-4342eae5f706

`triage` ran as session `b9f5c434-bed9-4793-836c-4342eae5f706`
- replay: `claude --resume b9f5c434-bed9-4793-836c-4342eae5f706`
- log: `.project/logs/TICKET-072-triage-b9f5c434.log`

### 2026-08-27 16:20:03Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- register() accepts a worktree of a registered project, test committed at fdcd590

### 2026-08-27 · planning · plan · result=ok

Plan written, 17 steps, 5 files. I took both fixes the ticket suggested,
because each covers a case the other misses: the worktree check catches a
registration the operator makes by hand, and the `PIPELINE_STAGE` check
catches a stage registering a directory that is not a worktree.

Two things a reviewer should look at deliberately.

1. Step 1 rewrites triage's reproduction test. `registry.register(wt)` is
   called unguarded there, so the new `PipelineError` would error the test
   rather than pass it. The rewrite keeps the original
   `assert wt not in registry.projects()` and its message.
2. The `PIPELINE_STAGE` refusal is a guardrail, not a boundary -- an agent
   can unset the variable. Recorded as such in `## Decisions`; reject step 13
   if a guardrail that cannot be enforced is not wanted.

Detection uses the `.git` file's `gitdir:` pointer, not `git rev-parse`,
because `projects()` runs on every tick. Evidence is in `## Digest`.

Two notes outside this ticket's scope, neither actioned:

- The operator's live registry still lists
  `/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068`. The
  `projects()` filter makes it inert; removing the line needs
  `pipeline unregister`.
- `pipeline register` reaches a stage because it is on `PATH`; no plan step
  changes that.

### 2026-08-27 16:26:57Z · planning · session · session=6c8c53e9-0913-40ed-9bb2-00b3055ead31

`planning` ran as session `6c8c53e9-0913-40ed-9bb2-00b3055ead31`
- replay: `claude --resume 6c8c53e9-0913-40ed-9bb2-00b3055ead31`
- log: `.project/logs/TICKET-072-planning-6c8c53e9.log`

### 2026-08-27 16:26:57Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: register() and projects() refuse a linked git worktree, and both verbs refuse when PIPELINE_STAGE is set

### 2026-08-27 16:33:17Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_registry_worktree.py::test_register_refuses_a_worktree_of_a_registered_project` fails as required
```
[31mE       AssertionError: register() accepted a worktree of a registered project: /tmp/tmptjitxh7u/.worktrees/TICKET-068 is in [PosixPath('/tmp/tmptjitxh7u'), PosixPath('/tmp/tmptjitxh7u/.worktrees/TICKET-068')][0m
[1m[31mE       assert PosixPath('/tmp/tmptjitxh7u/.worktrees/TICKET-068') not in [PosixPath('/tmp/tmptjitxh7u'), PosixPath('/tmp/tmptjitxh7u/.worktrees/TICKET-068')][0m
[1m[31mE        +  where [PosixPath('/tmp/tmptjitxh7u'), PosixPath('/tmp/tmptjitxh7u/.worktrees/TICKET-068')] = <function projects at 0x7fc1bba480e0>()[0m
[1m[31mE        +    where <function projects at 0x7fc1bba480e0> = registry.projects[0m

[1m[31mtests/test_registry_worktree.py[0m:35: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_registry_worktree.py::[1mtest_register_refuses_a_worktree_of_a_registered_project[0m - AssertionError: register() accepted a worktree of a registered project: /tm...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.06s[0m[31m ===============================[0m

```
- ok: `tests/test_registry_worktree.py::test_register_refuses_a_worktree_of_a_registered_project` fails on base `main` too -- the bug is not already fixed upstream
```
m:35: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_registry_worktree.py::[1mtest_register_refuses_a_worktree_of_a_registered_project[0m - AssertionError: register() accepted a worktree of a registered project: /tm...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.09s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-w5qdaddn/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-w5qdaddn/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- ok: DEC-041 is superseded -- history, not binding

### 2026-08-27 · plan-validation · judgment · result=ok

Tier B: PASS on all eight items.

1. **Root cause.** `register()` distinguishes a project by `.project/` alone,
   and `git worktree add` copies `.project/`, so a ticket's own checkout is
   indistinguishable from the project it was cut from. The plan adds the
   missing distinction in `registry.py`, the one place that decides. It does
   not target the test.
2. **Decisions.** DEC-011 (text file, no table) -- the plan adds two refusals
   and no storage. DEC-034/DEC-052 (containment is dispatcher and guard code,
   not a flag) -- the plan changes neither `dangerous-commands.py` nor
   `claude-code.toml`. The `PIPELINE_STAGE` check is env-read library code, the
   shape those decisions warn about; the plan complies by naming it a
   guardrail, not a boundary, in `## Decisions` and in step 16.
3. **Scope.** Every step traces to a criterion: 1-5 to the first, 6-8 to the
   second, 9-10 to the third, 11-14 to the fourth and fifth, 17 to the sixth.
   Steps 15-16 are docs for a user-visible CLI refusal.
4. **Falsifiable.** Step 9's test fails if the refusal widens to any git repo
   or any path under `.worktrees/`. Step 12's fails if either verb ignores
   `PIPELINE_STAGE`. Neither is vacuous.
5. **No research left.** Every step names the file, the function and the code.
6. **Riskiest step: 13.** A stage's Bash runs the suite with `PIPELINE_STAGE`
   set, so the refusal reddens the suite for this repo's own stages. Step 11
   clears it in `tests/conftest.py`, and `## Rollback` reverts step 14 alone.
7. **Regression surface.** `projects()` feeds `serve()`
   (`supervisor.py:1376`), `cmd_ls` (`main.py:272`), `cmd_projects` (311),
   `proj()` (487), `server.py:486` and `tui/app.py:250`; the full suite plus
   `tests/test_daemon.py` covers them. No existing test registers a worktree
   path -- I grepped `worktree add` and `ensure_worktree` across `tests/`.
8. **Blast radius.** `class: bugfix`, five files: one module, one test file,
   `conftest.py`, two docs. Proportionate.

Two counts in the plan are wrong; the fix is not. `tests/test_daemon.py` holds
**9** `registry.register()` calls in **7** tests (lines 137, 189, 190, 323,
437, 463, 665, 666, 1028), not "8 tests" (`## Digest` gotcha 2) or "8 calls"
(fifth acceptance criterion). Two more call sites live outside that file --
`tests/test_dispatch.py:855` and `tests/test_harness.py:479`. The step 11
`conftest.py` pop covers all 11 call sites, so no plan step changes. Read the
fifth criterion as "the suite is green", not as a count.

One follow-up outside this ticket: `pipeline/templates/skills/file-ticket/SKILL.md:138`
says "Not registered -> `pipeline register .` from the repo root". That stays
true after the refusal, so the plan's omission is not a gap.

### 2026-08-27 16:36:06Z · plan-validation · session · session=dbcf14c5-6c78-420c-9406-39afa2a35113

`plan-validation` ran as session `dbcf14c5-6c78-420c-9406-39afa2a35113`
- replay: `claude --resume dbcf14c5-6c78-420c-9406-39afa2a35113`
- log: `.project/logs/TICKET-072-plan-validation-dbcf14c5.log`

### 2026-08-27 16:36:06Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight judgment items; two call counts corrected in the thread, no step changes

### 2026-08-27 16:36:49Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread)

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread)**

### 2026-08-27 16:37:23Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_registry_worktree.py::test_register_refuses_a_worktree_of_a_registered_project` fails as required
```
[31mE       AssertionError: register() accepted a worktree of a registered project: /tmp/tmpvh4co6mk/.worktrees/TICKET-068 is in [PosixPath('/tmp/tmpvh4co6mk'), PosixPath('/tmp/tmpvh4co6mk/.worktrees/TICKET-068')][0m
[1m[31mE       assert PosixPath('/tmp/tmpvh4co6mk/.worktrees/TICKET-068') not in [PosixPath('/tmp/tmpvh4co6mk'), PosixPath('/tmp/tmpvh4co6mk/.worktrees/TICKET-068')][0m
[1m[31mE        +  where [PosixPath('/tmp/tmpvh4co6mk'), PosixPath('/tmp/tmpvh4co6mk/.worktrees/TICKET-068')] = <function projects at 0x7f5e84650040>()[0m
[1m[31mE        +    where <function projects at 0x7f5e84650040> = registry.projects[0m

[1m[31mtests/test_registry_worktree.py[0m:35: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_registry_worktree.py::[1mtest_register_refuses_a_worktree_of_a_registered_project[0m - AssertionError: register() accepted a worktree of a registered project: /tm...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.06s[0m[31m ===============================[0m

```
- ok: `tests/test_registry_worktree.py::test_register_refuses_a_worktree_of_a_registered_project` fails on base `main` too -- the bug is not already fixed upstream
```
m:35: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_registry_worktree.py::[1mtest_register_refuses_a_worktree_of_a_registered_project[0m - AssertionError: register() accepted a worktree of a registered project: /tm...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.10s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ntoveqn3/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-ntoveqn3/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 11ms[0m[0m

```
- ok: DEC-041 is superseded -- history, not binding

### 2026-08-27 16:37:23Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-27 · implementing · todo

1. Rewrite triage's repro test to expect `PipelineError` (step 1) -- done
2. Verify RED (step 2) -- done
3. Add `is_worktree()`, refuse in `register()` (steps 3-4) -- done
4. Verify GREEN, commit (step 5) -- done
5. Add/verify RED `test_projects_skips_...` (step 6) -- done
6. Fix `projects()` filter, verify GREEN, commit (steps 7-8) -- done
7. Add `test_register_still_accepts_...`, verify, commit (steps 9-10) -- done
8. Add/verify RED `test_a_stage_cannot_register_or_unregister` (step 12) -- done
9. `conftest.py` pops `PIPELINE_STAGE` (step 11) -- done
10. `register()`/`unregister()` refuse on `PIPELINE_STAGE` (step 13) -- done
11. Verify GREEN both test files, commit (step 14) -- done
12. README.md + CLAUDE.md updates (steps 15-16) -- done
13. Full suite + guard suite green, commit (step 17) -- done

### 2026-08-27 · implementing · report · result=ok

All 17 plan steps done, four commits plus one docs commit (`ad779e2`,
`f0416ff`, `66ecf4e`, `8f7edb1`, `fac3e77`).

`tests/test_registry_worktree.py`: 4 tests, all pass individually and as a
file (`4 passed`). `uv run --group dev pytest -q`: `354 passed`.
`./pipeline/hooks/test_dangerous_commands.py`: `all passed`, and
`pipeline/hooks/` has no diff -- confirmed with `git diff --stat
pipeline/hooks/`, empty.

TDD followed for every new behaviour: steps 1-2, 6, 12 each verified RED with
the plan's expected failure message before the GREEN code was written. Step
9's test (main checkout / plain directory still accepted) was not RED-first,
per the plan's own step 9-10 pairing -- it asserts existing correct behaviour,
falsifiable by widening the refusal, not by a missing feature.

Deviation, not a plan change: step 9's `project()` fixture carries a real
`TICKET-001` ticket. Left registered, it collided with
`tests/test_daemon.py::test_ls_reads_ticket_files_and_refuses_an_unregistered_project`
when both files ran in one `pytest` process --
`os.environ["XDG_CONFIG_HOME"]` is set at each file's import time and read at
call time, so the last-imported file's registry directory is shared for the
whole run. Failure was `assert False is True` at `tests/test_daemon.py:144`.
Fixed by unregistering `p` in a `finally`, matching the `finally:
registry.unregister(d)` convention `test_daemon.py` already uses. No file
outside `## Digest`'s list was touched.

### 2026-08-27 16:41:57Z · implementing · session · session=3ece86bc-c452-4fe6-b6d2-dfdd01d24549

`implementing` ran as session `3ece86bc-c452-4fe6-b6d2-dfdd01d24549`
- replay: `claude --resume 3ece86bc-c452-4fe6-b6d2-dfdd01d24549`
- log: `.project/logs/TICKET-072-implementing-3ece86bc.log`

### 2026-08-27 16:41:57Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented all 17 plan steps, registry refuses a linked worktree and a spawned stage's write, full suite green (354 passed), guard suite green with empty diff

### 2026-08-27 · review · report · result=ok

Reviewed the delta `ec9017f..fac3e77`: 5 files, +164/-2, exactly the files
`## Digest` names. No blocking findings. Working tree clean before and after.

Re-ran every acceptance criterion here:
1. `uv run --group dev pytest -q tests/test_registry_worktree.py` -> `4 passed`
2. `uv run --group dev pytest -q` -> `354 passed in 17.39s`
3. `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`
4. `git diff ec9017f HEAD --stat -- pipeline/hooks/ pipeline/harnesses/` -> empty

Two charges I dropped after checking the code:
- "the refusal on `PIPELINE_STAGE` breaks the dispatcher". Refuted:
  `supervisor.py:407` builds `env = project_env()`, a `dict(os.environ)` copy
  (`pipeline/core/worktree.py:15`), so `env["PIPELINE_STAGE"] = stage` never
  touches the parent process.
- "a reader bypasses the `projects()` filter". Refuted: every consumer goes
  through `registry.projects()` -- `cli/main.py:272,311,487`,
  `daemon/server.py:486,496,500`, `supervisor.py:1376`, `tui/app.py:250,279`.
  `_raw()` is called only inside `registry.py`.

Nits, none blocking:
1. minor: `tests/test_registry_worktree.py:11,13` import `subprocess` and
   `Path`; neither is used.
2. minor: `registry.py:59,93,121` run 96-105 chars. Plan step 7 said "wrapped
   to fit"; `supervisor.py` has 2 such lines in 1400.
3. minor: tests 1, 2 and 4 leave their `git_project()` registered. Harmless --
   `git_project()` writes no ticket, so `test_ls_with_no_project_covers_every_registered_project`
   (`tests/test_daemon.py:663`) counts no extra row, and it runs first anyway.

### 2026-08-27 16:45:42Z · review · session · session=6d2627a3-3489-4c97-92ab-66b6f4977f3c

`review` ran as session `6d2627a3-3489-4c97-92ab-66b6f4977f3c`
- replay: `claude --resume 6d2627a3-3489-4c97-92ab-66b6f4977f3c`
- log: `.project/logs/TICKET-072-review-6d2627a3.log`

### 2026-08-27 16:45:42Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed ec9017f..fac3e77, no blocking findings: all 6 acceptance criteria re-run green (4 passed, 354 passed, guard all passed, hooks diff empty), 3 minor nits in thread

### 2026-08-27 16:46:00Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 16:46:00Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/072


Rebasing (1/6)Rebasing (2/6)Rebasing (3/6)Rebasing (4/6)Rebasing (5/6)Rebasing (6/6)Successfully rebased and updated refs/heads/ticket/072.
Already up to date.
Updating 2691206..f44666e
Fast-forward
 CLAUDE.md                       |   7 +++
 README.md                       |   5 ++
 pipeline/daemon/registry.py     |  48 ++++++++++++++++++-
 tests/conftest.py               |   5 ++
 tests/test_registry_worktree.py | 101 ++++++++++++++++++++++++++++++++++++++++
 5 files changed, 164 insertions(+), 2 deletions(-)
 create mode 100644 tests/test_registry_worktree.py

```

### 2026-08-27 16:46:00Z · merging · decision

decision recorded as `DEC-072`
