---
id: TICKET-091
stage: done
class: feature
branch: ticket/091
test_file: tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown
files_declared:
- README.md
- pipeline/core/worktree.py
- pipeline/daemon/supervisor.py
- pipeline/templates/pipeline.toml
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_dispatch.py
- tests/test_stages.py
- tests/test_worktree.py
counters:
  plan_validation_attempts: 0
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
  id: 284a975c-5f3c-4a81-acf1-439b981c5a5a
  log: .project/logs/TICKET-091-review-284a975c.log
  cost_usd: 1.3430114999999998
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified: drop_worktree at worktree.py:92 gains an
  optional cfg so existing callers keep working; teardown runs from both removal paths
  including base_checkout''s finally; step 6 deliberately does not rebind the ''code''
  variable, which the removal branch depends on; step 7 pins that a failing teardown
  still removes the checkout and step 9 that a missing config still does. Nothing
  fenced. Noted: base_checkout''s dir is always named ''base'' (worktree.py:107),
  so a basename-keyed cache is shared across gate runs -- pre-existing, and step 10
  documents it.'
approved_at: '2026-08-29T05:25:51.990321+00:00'
---

## Summary

`worktree_teardown`: a project can reclaim what `worktree_setup` created

`worktree_setup` (`pipeline/core/worktree.py:61`) runs one project-supplied command
per new checkout, and the docs tell you to use it to key a build cache OUTSIDE the
worktree (`pipeline/templates/pipeline.toml:55`, `README.md:357`). Nothing ever
removes what it created. `drop_worktree()` (`pipeline/core/worktree.py:69`) runs
`git worktree remove` and stops there; `base_checkout()` runs `worktree_setup` for
the gate's throwaway checkout of base and removes only the checkout.

Measured on another project: 18 keyed target directories, 9.1G, against 2 live
worktrees -- 16 orphans. Plus 32 orphan directories, 19G, from
`/tmp/pipeline-base-*` gate checkouts whose keys are long gone. Nothing in the
system will ever collect either, and the pipeline is the only thing that knows
when a checkout dies.

Expected: a `worktree_teardown` key, run the same way `worktree_setup` is
(`run_cmd(cmd, wt)`, in the checkout, before it is removed), from BOTH removal
paths -- `drop_worktree()` and `base_checkout()`'s `finally`. The worktree
directory is `.worktrees/<id>`, so `$(basename $PWD)` is the ticket id in both
commands and the key matches by construction:

    worktree_setup    = "..."   # keys a cache at ~/.cache/x/$(basename $PWD)
    worktree_teardown = "rm -rf ~/.cache/x/$(basename $PWD)"

Falsifiable: after `drop_worktree()`, a file the teardown command was told to
remove must be gone; a project with no `worktree_teardown` behaves exactly as
today.

**State: reviewed, PASS, no blocking findings.** `drop_worktree()` and
`base_checkout()`'s `finally` both run `worktree_teardown` in the checkout
before removal; `start()`'s cleanup branch loads the config and falls back to
`{}` when `project_config()` raises. Documented in `pipeline.toml`,
`README.md` and the `pipeline-config` skill. `review` re-ran the full suite:
`uv run --group dev pytest -q` -> `465 passed in 36.46s`, and checked every
acceptance criterion: 5 named tests pass, `grep -l worktree_teardown README.md
pipeline/templates/pipeline.toml
pipeline/templates/skills/pipeline-config/SKILL.md | wc -l` prints `3`, and
`git diff main -- tests/test_worktree.py` shows no edit inside
`test_recreating_a_worktree_never_resets_the_branch`. Three non-blocking nits
are in the last `## Thread` entry. 4 commits: `4b51816`, `7c45c5f`,
`f893617`, `18eb2e6` (plus the pre-existing repro `5d54d88`).

Triage reproduced the bug (commit `a081379`,
`tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown` fails with
`TypeError: drop_worktree() takes 2 positional arguments but 3 were given`).
`## Plan` has 13 steps over 8 files. `drop_worktree()` gains
`cfg: dict | None = None` and runs the teardown in the checkout before
`git worktree remove --force`; `base_checkout()` does the same inside the
`if not code:` branch of its `finally`; `start()` in
`pipeline/daemon/supervisor.py` loads the config in its cleanup branch and
falls back to `{}` when `project_config()` raises. A failing teardown is
printed and the removal proceeds. DEC-084 requires the new key in the config
template and in the `pipeline-config` skill; steps 10 to 12 cover both and the
tests that keep them honest. In the gate checkout `$(basename $PWD)` is always
`base`, not a ticket id -- see `## Decisions`.

## Reproduction

`tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown` sets
`cfg["worktree_teardown"]` to a command removing a marker file standing in
for a keyed cache, then calls `W.drop_worktree(d, meta, cfg)`.

Command: `uv run --group dev pytest -q tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown`

Failure:
```
>       W.drop_worktree(d, meta, cfg)
E       TypeError: drop_worktree() takes 2 positional arguments but 3 were given
```

expect: TypeError: drop_worktree() takes 2 positional arguments but 3 were given

## Digest

- Files touched: `pipeline/core/worktree.py` (both removal paths), `pipeline/daemon/supervisor.py` (the only `drop_worktree()` call site), `pipeline/templates/pipeline.toml`, `pipeline/templates/skills/pipeline-config/SKILL.md`, `README.md`, `tests/test_worktree.py`, `tests/test_dispatch.py`, `tests/test_stages.py`.
- Key functions: `drop_worktree(project, meta)` (`pipeline/core/worktree.py:69`) runs `git worktree remove --force` and nothing else. `base_checkout(project, cfg)` (`pipeline/core/worktree.py:76`) runs `worktree_setup` at line 93 and removes the checkout in its `finally` at line 97. `ensure_worktree()` (line 61) is the model for running a project command: `run_cmd(cfg["worktree_setup"], wt)`, output discarded.
- Entry point: `start()` in `pipeline/daemon/supervisor.py:735` is the only production caller of `drop_worktree()`, in the `stage in TERMINAL` branch. That branch returns before `cfg = project_config(project)` at line 766, so the cleanup path has no cfg and must load its own.
- Gotcha: `project_config()` (`pipeline/core/config.py:132`) raises `PipelineError` for a project with no `.project/pipeline.toml`, and `tomllib` raises `ValueError` for a malformed one. `tests/test_dispatch.py:61` deletes that file on purpose. An unwrapped call in the cleanup branch would leave the worktree behind, so the call is wrapped and falls back to `{}`.
- Gotcha: `machine.FENCED` fences `pipeline/core/worktree.py` at the symbol `strip_settings_sources` only (`pipeline/core/machine.py:56`), and `fenced_touches()` matches a hunk against that symbol's own line range. Editing `drop_worktree` and `base_checkout` does not park this ticket; editing `strip_settings_sources` would.
- Gotcha: in `base_checkout()` the checkout is `<tempdir>/base`, so `$(basename $PWD)` there is always the literal `base`, never a ticket id. The ticket summary claims it is the ticket id in both commands; that holds for `drop_worktree()` only. Setup and teardown still read the same string in the same checkout, so a key still matches by construction.
- Gotcha: `tests/test_worktree.py:54` calls `W.drop_worktree(d, meta)` with two arguments, so `cfg` takes a default rather than becoming required.
- Test helper: `git_project()` (`tests/helpers.py:52`) writes `.project/pipeline.toml` on disk and never commits it; `project_config()` falls back to disk, so a test can add `worktree_teardown` to that file and the dispatcher reads it.

## Decisions checked

Grepped `.project/decisions/` for `worktree_setup`, `drop_worktree`, `base_checkout`, `CLEANUP_STAGES`, `worktree remove`, `cache`, `teardown`.

- DEC-084 binds this change: a knob the code reads must appear in the comments of `pipeline/templates/pipeline.toml` and be named in `pipeline/templates/skills/pipeline-config/SKILL.md`, or a session has no route to it. Steps 10 and 11 document `worktree_teardown` in both, beside `worktree_setup`.
- DEC-034 and DEC-058 name `git worktree remove` only as a command the guard blocks for a read-only stage. Neither constrains library code. No conflict.
- No record covers reclaiming what `worktree_setup` creates.

## Plan

1. Run `uv run --group dev pytest -q tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown` and confirm it fails with `TypeError: drop_worktree() takes 2 positional arguments but 3 were given`.
2. In `pipeline/core/worktree.py`, change the signature to `def drop_worktree(project: Path, meta: dict, cfg: dict | None = None) -> None:` and, inside the existing `if wt.is_dir():` block and BEFORE the `git worktree remove --force` line, add `if (cfg or {}).get("worktree_teardown"):` running `code, out = run_cmd(cfg["worktree_teardown"], wt)` and then `if code: print(f"  worktree_teardown failed for {meta['id']}: {out.strip()[:300]}")`; keep the removal unconditional after it.
3. Run `uv run --group dev pytest -q tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown`; expect `1 passed`. Commit `pipeline/core/worktree.py` as `feat(TICKET-091): run worktree_teardown before dropping a ticket checkout`.
4. Add `test_base_checkout_runs_worktree_teardown` to `tests/test_worktree.py`: `d, _ = git_project()`; `marker = Path(tempfile.mkdtemp()) / "base.marker"`; `marker.write_text("keyed cache")`; `cfg = {"base": "main", "worktree_teardown": f"rm -f {marker}"}`; inside `with W.base_checkout(d, cfg) as (wt, err):` assert `wt is not None` and `marker.exists()`; after the block assert `not marker.exists(), "worktree_teardown never ran in the gate base checkout"`; end with `shutil.rmtree(d, ignore_errors=True)`.
5. Run `uv run --group dev pytest -q tests/test_worktree.py::test_base_checkout_runs_worktree_teardown` and confirm it fails on `assert not marker.exists()`.
6. In `pipeline/core/worktree.py`, in the `finally` of `base_checkout()`, inside the existing `if not code:` branch and before the `git worktree remove --force` call, run `code2, out2 = run_cmd(cfg["worktree_teardown"], wt)` under `if cfg.get("worktree_teardown"):` and print `f"  worktree_teardown failed in the base checkout: {out2.strip()[:300]}"` when `code2` is non-zero; do not rebind `code`, which the `if not code:` branch depends on. Run the step 5 command; expect `1 passed`.
7. Add `test_a_failing_worktree_teardown_still_removes_the_checkout(capsys)` to `tests/test_worktree.py`: `d, _ = git_project()`; `meta = {"id": "TICKET-001", "branch": "ticket/001"}`; `cfg = {"base": "main", "worktree_teardown": "exit 3"}`; `W.ensure_worktree(d, meta, cfg)`; `W.drop_worktree(d, meta, cfg)`; assert `not W.worktree(d, meta).is_dir()` and `"worktree_teardown failed" in capsys.readouterr().out`. Run `uv run --group dev pytest -q tests/test_worktree.py`; expect no failures, then commit `pipeline/core/worktree.py` and `tests/test_worktree.py` as `feat(TICKET-091): run worktree_teardown in the gate base checkout too`.
8. Add `test_a_done_ticket_runs_worktree_teardown` to `tests/test_dispatch.py`, modelled on `test_a_done_ticket_does_release_its_worktree` at line 50: `d, _ = git_project()`; write a marker file under `tempfile.mkdtemp()`; append a `worktree_teardown = "rm -f <marker>"` line to `d / ".project/pipeline.toml"`; call `supervisor.ensure_worktree(d, meta, {"base": "main"})`; write the FIXTURE with `stage: plan-validation` replaced by `stage: done`; call `supervisor.start(d, d / ".project/tickets/TICKET-001.md", harness("fake"), {})`; assert the marker is gone. Run it and confirm it fails on the surviving marker.
9. In `pipeline/daemon/supervisor.py`, inside the `if stage in CLEANUP_STAGES and worktree(...).is_dir():` block of `start()` at line 734, load the config in a `try: cfg = project_config(project)` with an `except (PipelineError, ValueError) as e:` that prints `f"  {tid}: no worktree_teardown ({e})"` and sets `cfg = {}`, then call `drop_worktree(project, t.frontmatter(), cfg)`. Add `test_a_done_ticket_without_a_config_still_releases_its_worktree` to `tests/test_dispatch.py`: the step 8 setup but with `(d / ".project/pipeline.toml").unlink()` before `start()`, asserting `not wt.is_dir()`. Run `uv run --group dev pytest -q tests/test_dispatch.py`; expect no failures, then commit as `feat(TICKET-091): pass the project config to the dispatcher worktree cleanup`.
10. Document the key in `pipeline/templates/pipeline.toml` directly under the `worktree_setup` comment block that ends at line 55, as commented lines carrying `# worktree_teardown = "rm -rf ~/.cache/cargo/$(basename $PWD)"` and stating four things: it runs in the same checkout just before that checkout is removed; it runs from both removal paths, a ticket worktree and the gate throwaway checkout of base; `$(basename $PWD)` is the same string it was in `worktree_setup`, so a key matches by construction; in the gate checkout that string is always `base`.
11. Add the same key to `README.md` under the `worktree_setup` toml block at line 347, and to `pipeline/templates/skills/pipeline-config/SKILL.md` as a new `### worktree_teardown -- reclaiming what the setup created` section (heading formatted like its neighbour at line 161) placed after the `worktree_setup` section; each gets the toml line, the two removal paths, and the `base` caveat from step 10.
12. Extend the doc tests in `tests/test_stages.py`: add `"worktree_teardown"` to the knob tuple in `test_the_config_skill_names_every_knob_the_code_reads` at line 394, and add `assert "worktree_teardown" in text` to `test_the_config_template_documents_worktree_setup` at line 402. Run `uv run --group dev pytest -q tests/test_stages.py`; expect no failures.
13. Run `uv run --group dev pytest -q`, then commit `README.md`, `pipeline/templates/pipeline.toml`, `pipeline/templates/skills/pipeline-config/SKILL.md` and `tests/test_stages.py` as `docs(TICKET-091): document worktree_teardown beside worktree_setup`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown` exits 0.
- `uv run --group dev pytest -q tests/test_worktree.py::test_base_checkout_runs_worktree_teardown` exits 0: the gate base checkout runs the teardown.
- `uv run --group dev pytest -q tests/test_worktree.py::test_a_failing_worktree_teardown_still_removes_the_checkout` exits 0: a teardown exiting 3 is printed and the checkout is still removed.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_done_ticket_runs_worktree_teardown` exits 0: the dispatcher cleanup path passes the config through.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_done_ticket_without_a_config_still_releases_its_worktree` exits 0: an unreadable config does not strand a worktree.
- A project with no `worktree_teardown` behaves as before: `uv run --group dev pytest -q tests/test_dispatch.py::test_a_done_ticket_does_release_its_worktree tests/test_worktree.py::test_recreating_a_worktree_never_resets_the_branch` exits 0, and `git diff main -- tests/test_worktree.py` shows no edit inside `test_recreating_a_worktree_never_resets_the_branch`.
- `grep -l worktree_teardown README.md pipeline/templates/pipeline.toml pipeline/templates/skills/pipeline-config/SKILL.md | wc -l` prints `3`.
- `uv run --group dev pytest -q` exits 0. A failure unrelated to worktree teardown must be shown to fail at commit `a081379~1` too, and reported in the thread rather than fixed here.

## Decisions

**The teardown runs in the checkout, before `git worktree remove`, on both removal paths.** After the removal the cwd is gone and `run_cmd(cmd, wt)` has nowhere to run. Running it inside the checkout is what makes `$(basename $PWD)` the same string `worktree_setup` saw, so a keyed cache matches by construction and no key is ever stored. Both paths, because the gate throwaway checkout of base (`base_checkout()`) runs `worktree_setup` too, and its orphans measured larger than the ticket worktrees (19G against 9.1G).

**A failing teardown is printed and the removal proceeds.** `drop_worktree()` and the `finally` in `base_checkout()` must never leave a checkout behind: an orphan git worktree breaks the ticket resume path, while an unreclaimed cache directory only costs disk. The print exists because nothing downstream fails when a teardown fails -- unlike `worktree_setup`, whose failure surfaces as a red stage -- so a silent teardown would be indistinguishable from no teardown at all.

**`cfg` is optional on `drop_worktree()`, and the dispatcher cleanup path falls back to `{}`.** The `stage in TERMINAL` branch of `start()` returns before the config is loaded, and `project_config()` raises for a project whose `.project/pipeline.toml` is missing or malformed. Removing the checkout is the obligation there; reclaiming the cache is best effort. Do not make that config load unwrapped -- a broken config would then strand every finished ticket worktree.

**In the gate base checkout `$(basename $PWD)` is always `base`.** Two gate runs in parallel therefore share one cache key, and one teardown can delete a cache the other is still using. The shared key predates this ticket; the delete is new. A project that runs the gate concurrently should key its cache on more than the basename.

## Rollback

`git revert` the commits from steps 3, 7, 9 and 13, or drop the branch. The pre-change behaviour is exactly the behaviour of a project that sets no `worktree_teardown`: `drop_worktree()` and `base_checkout()` remove their checkout and nothing else. A revert strands nothing; it only stops reclaiming caches, which is today's state.

## Thread

### 2026-08-29 03:52:45Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 · triage · transition · to=? · result=ok

**triage** (result: `ok`)

Reproduced. `drop_worktree(project, meta)` takes no `cfg`, so it has no way
to run `worktree_teardown` even after the fix -- confirms the ticket's claim
that nothing removes what `worktree_setup` created.

Committed `tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown`
(commit `a081379`): sets `cfg["worktree_teardown"]` to remove a marker file
standing in for a keyed cache, calls `drop_worktree(d, meta, cfg)`, asserts
the marker is gone.

Not `chore`: fixing this needs a design decision on where in
`base_checkout()`'s `finally` the teardown call goes relative to
`git worktree remove`, and whether a failing teardown command should be
surfaced or swallowed. Leaving as `ok` for planning.

### 2026-08-29 04:16:14Z · triage · session · session=b6024641-f2a4-4204-b17f-bd5d0f5be9b3

`triage` ran as session `b6024641-f2a4-4204-b17f-bd5d0f5be9b3`
- replay: `claude --resume b6024641-f2a4-4204-b17f-bd5d0f5be9b3`
- log: `.project/logs/TICKET-091-triage-b6024641.log`
- cost: $0.26 of a $3 cap
- tokens: 2,932 out (48 thinking) · 26 in · 483,410 cache read · 32,660 cache write

### 2026-08-29 04:16:14Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: drop_worktree() has no cfg param, so it cannot run worktree_teardown; new test fails with TypeError.

### 2026-08-29 · planning · note · result=ok

Plan written: 13 steps, 8 files, 5 named tests. Scope stays on the two
removal paths the ticket names. It does not collect the orphans already on
disk -- that is a separate `pipeline` subcommand and it does not stand on
this change.

Two design questions triage left open, both settled from the code:

1. In `base_checkout()` the teardown runs inside the existing `if not code:`
   branch of the `finally`, before `git worktree remove --force`. After the
   removal the cwd is gone.
2. A failing teardown is printed and the removal proceeds. An orphan git
   worktree breaks the resume path; an unreclaimed cache costs disk.

One correction to the ticket summary: `$(basename $PWD)` is the ticket id in
`drop_worktree()` only. In the gate checkout the path is `<tempdir>/base`, so
that string is always `base`, for `worktree_setup` today and for the teardown
after this change. Setup and teardown still agree by construction, so the fix
holds; parallel gate runs share one cache key, which they already did before
this ticket. Recorded in `## Decisions`.

Noticed outside this scope, not fixed: `ensure_worktree()` discards the exit
code of `worktree_setup`, so a failing setup is silent.

### 2026-08-29 04:23:57Z · planning · session · session=b89f74e6-da98-4d7e-a129-1f6f5c242c07

`planning` ran as session `b89f74e6-da98-4d7e-a129-1f6f5c242c07`
- replay: `claude --resume b89f74e6-da98-4d7e-a129-1f6f5c242c07`
- log: `.project/logs/TICKET-091-planning-b89f74e6.log`
- cost: $2.96 of a $10 cap
- tokens: 41,477 out (13,461 thinking) · 54 in · 1,742,270 cache read · 105,409 cache write

### 2026-08-29 04:23:57Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned worktree_teardown on both removal paths: 13 steps, 8 files, 5 named tests.

### 2026-08-29 05:20:03Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown` fails as required
```
________

    def test_drop_worktree_runs_worktree_teardown():
        """`worktree_setup` keys a cache outside the worktree; nothing today ever
        runs a matching teardown, so `drop_worktree()` must invoke `worktree_teardown`
        (in the checkout, before it is removed) to reclaim it."""
        d, sh = git_project()
        meta = {"id": "TICKET-001", "branch": "ticket/001"}
        marker = Path(tempfile.mkdtemp()) / "TICKET-001.marker"
        marker.write_text("keyed cache\n")
        cfg = {
            "base": "main",
            "worktree_setup": "true",
            "worktree_teardown": f"rm -f {marker}",
        }
        wt = W.ensure_worktree(d, meta, cfg)
        assert wt is not None
    
>       W.drop_worktree(d, meta, cfg)
E       TypeError: drop_worktree() takes 2 positional arguments but 3 were given

tests/test_worktree.py:79: TypeError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown - Ty...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown` fails on base `main` too -- the bug is not already fixed upstream
```
        "worktree_setup": "true",
            "worktree_teardown": f"rm -f {marker}",
        }
        wt = W.ensure_worktree(d, meta, cfg)
        assert wt is not None
    
>       W.drop_worktree(d, meta, cfg)
E       TypeError: drop_worktree() takes 2 positional arguments but 3 were given

tests/test_worktree.py:79: TypeError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown - Ty...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-kn9nmdg0/base
      Built pipeline @ file:///tmp/pipeline-base-kn9nmdg0/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 · plan-validation · note · result=ok

**Tier B: PASS.** All 8 items pass. Findings, one per item:

1. Root cause: `drop_worktree(project, meta)` and `base_checkout()`'s `finally`
   remove the checkout and run nothing else, and `drop_worktree()` has no `cfg`
   parameter, so no project command can reclaim what `worktree_setup` keyed
   outside the worktree. The plan fixes that, not the symptom.
2. Decisions: DEC-084 binds and steps 10 to 12 comply -- I read it and it
   requires the key in `pipeline/templates/pipeline.toml` comments and in
   `pipeline-config/SKILL.md`. DEC-034 and DEC-058 name `git worktree remove`
   only as a command the guard blocks; neither constrains library code.
3. Scope: every step traces to an acceptance criterion. Steps 10 to 12 trace to
   the `grep -l ... | wc -l` criterion, steps 4 to 7 to the two `test_worktree`
   criteria.
4. Criteria are falsifiable. Each names a test whose assertion is a removed
   marker file or a printed string, and the marker survives if the teardown
   never runs.
5. No research left. I verified every cited anchor: `worktree.py:61,69,76,93,97`,
   `supervisor.py:734-735` and its `cfg = project_config(project)` at 766,
   `tests/test_worktree.py:42,54`, `tests/test_dispatch.py:50,61`,
   `tests/test_stages.py:394,402`, `templates/pipeline.toml:50-56`,
   `README.md:347`, `SKILL.md:161`. All match.
6. Riskiest step: 9. Fallback stated in the step (`cfg = {}`) and tested.
7. Regression surface: the two existing `drop_worktree()` callers
   (`supervisor.py:735`, `tests/test_worktree.py:54`) -- `cfg` defaults, so both
   keep working; and the gate's `base_checkout()`, covered by
   `test_a_done_ticket_does_release_its_worktree` and
   `test_recreating_a_worktree_never_resets_the_branch`.
8. Blast radius matches `class: feature`: 8 files, of which 2 are code, 3 docs
   and 3 tests. `files_declared` matches the plan exactly.

Checked two claims the plan rests on, both hold:
`tomllib.TOMLDecodeError` subclasses `ValueError`, so step 9's
`except (PipelineError, ValueError)` catches a malformed config; and
`git_project()` (`tests/helpers.py:59`) writes `.project/pipeline.toml` without
committing it, so `project_config()` falls through HEAD and `git_ignored()` to
the disk copy step 8 appends to.

`machine.FENCED` fences `pipeline/core/worktree.py` at `strip_settings_sources`
only (`pipeline/core/machine.py:56`), so this diff does not park at
`awaiting-merge` on that account.

unverified: I ran no test. The stage is read-only and the Tier A gate already
recorded the reproduction failing at HEAD and at base `main`. I would have run
`uv run --group dev pytest -q tests/test_worktree.py`.

### 2026-08-29 05:22:07Z · plan-validation · session · session=eb5e585d-faa9-4efb-828b-384658f7cc5c

`plan-validation` ran as session `eb5e585d-faa9-4efb-828b-384658f7cc5c`
- replay: `claude --resume eb5e585d-faa9-4efb-828b-384658f7cc5c`
- log: `.project/logs/TICKET-091-plan-validation-eb5e585d.log`
- cost: $0.98 of a $3 cap
- tokens: 9,235 out (3,407 thinking) · 28 in · 539,476 cache read · 48,312 cache write

### 2026-08-29 05:22:07Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan validated: all 8 items pass; every cited line, decision and test name matches the code.

### 2026-08-29 05:25:51Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: drop_worktree at worktree.py:92 gains an optional cfg so existing callers keep working; teardown runs from both removal paths including base_checkout's finally; step 6 deliberately does not rebind the 'code' variable, which the removal branch depends on; step 7 pins that a failing teardown still removes the checkout and step 9 that a missing config still does. Nothing fenced. Noted: base_checkout's dir is always named 'base' (worktree.py:107), so a basename-keyed cache is shared across gate runs -- pre-existing, and step 10 documents it.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: drop_worktree at worktree.py:92 gains an optional cfg so existing callers keep working; teardown runs from both removal paths including base_checkout's finally; step 6 deliberately does not rebind the 'code' variable, which the removal branch depends on; step 7 pins that a failing teardown still removes the checkout and step 9 that a missing config still does. Nothing fenced. Noted: base_checkout's dir is always named 'base' (worktree.py:107), so a basename-keyed cache is shared across gate runs -- pre-existing, and step 10 documents it.**

### 2026-08-29 05:29:23Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown` fails as required
```
________

    def test_drop_worktree_runs_worktree_teardown():
        """`worktree_setup` keys a cache outside the worktree; nothing today ever
        runs a matching teardown, so `drop_worktree()` must invoke `worktree_teardown`
        (in the checkout, before it is removed) to reclaim it."""
        d, sh = git_project()
        meta = {"id": "TICKET-001", "branch": "ticket/001"}
        marker = Path(tempfile.mkdtemp()) / "TICKET-001.marker"
        marker.write_text("keyed cache\n")
        cfg = {
            "base": "main",
            "worktree_setup": "true",
            "worktree_teardown": f"rm -f {marker}",
        }
        wt = W.ensure_worktree(d, meta, cfg)
        assert wt is not None
    
>       W.drop_worktree(d, meta, cfg)
E       TypeError: drop_worktree() takes 2 positional arguments but 3 were given

tests/test_worktree.py:79: TypeError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown - Ty...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown` fails on base `main` too -- the bug is not already fixed upstream
```
        "worktree_setup": "true",
            "worktree_teardown": f"rm -f {marker}",
        }
        wt = W.ensure_worktree(d, meta, cfg)
        assert wt is not None
    
>       W.drop_worktree(d, meta, cfg)
E       TypeError: drop_worktree() takes 2 positional arguments but 3 were given

tests/test_worktree.py:79: TypeError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_drop_worktree_runs_worktree_teardown - Ty...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-czqrg3wk/base
      Built pipeline @ file:///tmp/pipeline-base-czqrg3wk/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 18ms

```

### 2026-08-29 05:29:23Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-29 · implementing · todo

Todo (one per plan step):

1. [x] confirm red: `test_drop_worktree_runs_worktree_teardown` fails as stated
2. [x] `drop_worktree()` gains `cfg` param, runs teardown before removal
3. [x] green + commit worktree.py
4. [x] add `test_base_checkout_runs_worktree_teardown`, confirm red
5. [x] confirm red for step 4
6. [x] `base_checkout()` finally runs teardown before removal
7. [x] add `test_a_failing_worktree_teardown_still_removes_the_checkout`, green, commit
8. [x] add `test_a_done_ticket_runs_worktree_teardown` to test_dispatch.py, confirm red
9. [x] supervisor.py cleanup loads cfg with fallback `{}`; add `test_a_done_ticket_without_a_config_still_releases_its_worktree`; commit
10. [x] document key in pipeline.toml template
11. [x] document key in README.md and pipeline-config SKILL.md
12. [x] extend test_stages.py doc tests
13. [x] full suite, commit docs

### 2026-08-29 · implementing · done

Implemented all 13 plan steps. Confirmed RED then GREEN at every step: step 1
(`TypeError: drop_worktree() takes 2 positional arguments but 3 were given`),
step 5 (`assert not marker.exists()` failed inside `base_checkout`).

`drop_worktree()` (`pipeline/core/worktree.py`) gains `cfg: dict | None = None`
and runs `cfg["worktree_teardown"]` in the checkout before
`git worktree remove --force`, printing `worktree_teardown failed for
<id>: <out>` on non-zero and removing anyway. `base_checkout()`'s `finally`
does the same inside `if not code:`, without rebinding `code`. `start()` in
`pipeline/daemon/supervisor.py` wraps `project_config(project)` in
`try/except (PipelineError, ValueError)`, falling back to `cfg = {}` and
printing `<tid>: no worktree_teardown (<e>)`.

Documented the key in `pipeline/templates/pipeline.toml`, `README.md` and
`pipeline-config/SKILL.md`, each with the two removal paths and the `base`
basename caveat. Extended `test_the_config_skill_names_every_knob_the_code_reads`
and `test_the_config_template_documents_worktree_setup` in `tests/test_stages.py`.

5 named tests added, all pass: `test_drop_worktree_runs_worktree_teardown`,
`test_base_checkout_runs_worktree_teardown`,
`test_a_failing_worktree_teardown_still_removes_the_checkout`,
`test_a_done_ticket_runs_worktree_teardown`,
`test_a_done_ticket_without_a_config_still_releases_its_worktree`.

Full suite: `uv run --group dev pytest -q` -> `465 passed`, no failure to
report against `a081379~1`. `grep -l worktree_teardown README.md
pipeline/templates/pipeline.toml
pipeline/templates/skills/pipeline-config/SKILL.md | wc -l` -> `3`.
`git diff main -- tests/test_worktree.py` touches no line inside
`test_recreating_a_worktree_never_resets_the_branch`.

4 commits: `4b51816`, `7c45c5f`, `f893617`, `18eb2e6`.

### 2026-08-29 05:33:46Z · implementing · session · session=b5545f4c-f537-4b56-88dc-81971b7e9282

`implementing` ran as session `b5545f4c-f537-4b56-88dc-81971b7e9282`
- replay: `claude --resume b5545f4c-f537-4b56-88dc-81971b7e9282`
- log: `.project/logs/TICKET-091-implementing-b5545f4c.log`
- cost: $1.07 of a $8 cap
- tokens: 15,025 out (489 thinking) · 112 in · 3,262,578 cache read · 66,907 cache write

### 2026-08-29 05:33:46Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Implemented worktree_teardown on both removal paths; all 13 plan steps done, full suite 465 passed.

### 2026-08-29 · review · findings

**Review PASS. No blocking findings.** Reviewed the whole delta,
`git diff main...HEAD` over 8 files: base `d5050ce`, commits `4b51816`,
`7c45c5f`, `f893617`, `18eb2e6`.

Acceptance criteria, re-run here: `uv run --group dev pytest -q` ->
`465 passed in 36.46s`; `grep -l worktree_teardown README.md
pipeline/templates/pipeline.toml
pipeline/templates/skills/pipeline-config/SKILL.md | wc -l` -> `3`;
`git diff main -- tests/test_worktree.py` touches no line inside
`test_recreating_a_worktree_never_resets_the_branch` -- its one match is the
hunk header `@@ -60,6 +60,57 @@`.

Checked against `## Plan` and `## Decisions`: both removal paths run the
teardown in the checkout before `git worktree remove --force`
(`pipeline/core/worktree.py:92`, `:121`); `base_checkout()` binds `code2` and
leaves `code` alone, so the `if not code:` branch still removes the checkout;
`start()` (`pipeline/daemon/supervisor.py:736`) returns at `:743`, so its new
local `cfg` cannot reach the load at `:772`. `drop_worktree()` has one
production caller, `base_checkout()` one (`pipeline/core/gate.py:284`), both
passed the full project config.

Non-blocking nits, recorded not sent back:

1. minor: `except (PipelineError, ValueError)` (`supervisor.py:738`) does not
   cover `OSError` from `cfg.read_text()` (`pipeline/core/config.py:166`), so
   a present-but-unreadable config would strand the worktree. The same gap
   exists at `supervisor.py:773` today.
2. minor: `run_cmd()` has no timeout, so a hanging `worktree_teardown` blocks
   the tick. `worktree_setup` carries the same exposure already.
3. trivial: `wt` is assigned and never used in `tests/test_dispatch.py:70`.

### 2026-08-29 06:00:18Z · review · session · session=284a975c-5f3c-4a81-acf1-439b981c5a5a

`review` ran as session `284a975c-5f3c-4a81-acf1-439b981c5a5a`
- replay: `claude --resume 284a975c-5f3c-4a81-acf1-439b981c5a5a`
- log: `.project/logs/TICKET-091-review-284a975c.log`
- cost: $1.34 of a $6 cap
- tokens: 10,416 out (3,532 thinking) · 50 in · 1,088,965 cache read · 53,684 cache write

### 2026-08-29 06:00:18Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Review passed: worktree_teardown runs on both removal paths, full suite 465 passed, 3 non-blocking nits

### 2026-08-29 06:00:54Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 06:00:55Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/091


Current branch ticket/091 is up to date.
Already up to date.
Updating d5050ce..18eb2e6
Fast-forward
 README.md                                          | 13 ++++++
 pipeline/core/worktree.py                          | 10 ++++-
 pipeline/daemon/supervisor.py                      |  7 ++-
 pipeline/templates/pipeline.toml                   |  9 ++++
 pipeline/templates/skills/pipeline-config/SKILL.md | 15 +++++++
 tests/test_dispatch.py                             | 31 +++++++++++++
 tests/test_stages.py                               |  5 ++-
 tests/test_worktree.py                             | 51 ++++++++++++++++++++++
 8 files changed, 138 insertions(+), 3 deletions(-)

```

### 2026-08-29 06:00:55Z · merging · decision

decision recorded as `DEC-091`
