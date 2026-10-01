---
id: TICKET-147
stage: done
class: bugfix
branch: ticket/147
test_file:
- tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree
- tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup
deletes: []
files_declared:
- README.md
- pipeline/cli/main.py
- pipeline/core/gate.py
- pipeline/core/worktree.py
- pipeline/templates/skills/file-ticket/SKILL.md
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_cli.py
- tests/test_gate.py
- tests/test_worktree.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 8
  plan_files: 9
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: 6a7b020f-7bf1-4d5a-9942-e88e3506e3e3
  replay: claude --resume 6a7b020f-7bf1-4d5a-9942-e88e3506e3e3
  log: .project/logs/TICKET-147-review-6a7b020f.log
  cost_usd: 0.5992906
approved_by: chezzijr
approved_at: '2026-10-01T12:25:54.970304+00:00'
---

## Summary

`worktree_setup` is neither checked nor prompted for, so stages can run in a worktree with no dependencies

Expected change files: `pipeline/core/worktree.py`, `pipeline/cli/main.py`, `pipeline/templates/skills/pipeline-config/SKILL.md`, `tests/test_worktree.py` and `tests/test_cli.py`.

Two halves of one gap, found on the first JavaScript project. Each needs its own failing test.

**1. A failing `worktree_setup` is ignored**

Both call sites discard the exit code -- `pipeline/core/worktree.py:97` (ticket worktree) and `:134` (the gate's base checkout), on main at 7e7545a:

    if cfg.get("worktree_setup"):
        run_cmd(cfg["worktree_setup"], wt)
    return wt

`worktree_teardown` right below does check its code and prints a failure; setup does not. With `worktree_setup = "npm ci ..."` failing (offline, lockfile drift), the worktree is returned as ready, every stage runs without dependencies, and nothing in the ticket says why. On an npm-workspaces project that is worse than a crash: Node resolves the main checkout's `node_modules` by walking up the tree, so tests run against the main checkout's code and pass or fail with no error.

Expected: a non-zero `worktree_setup` exit is reported with its output (truncated as `worktree_teardown` does). For the ticket worktree, worktree creation fails (returns `None`, as a failed `git worktree add` already does) so the ticket does not proceed on a broken tree. For the base checkout, the gate does not trust a base run made in it. A test with `worktree_setup = "exit 3"` should show the worktree currently returned as ready.

**2. Nothing says `worktree_setup` is needed**

Ticket worktrees are fresh checkouts with no installed dependencies. A project that needs them (npm, pnpm, yarn, uv, poetry, bundler) must set `worktree_setup`, but nothing says so: `cmd_register` and `cmd_diagnostics` (`pipeline/cli/main.py:596-686`, on main at 7e7545a) never mention `worktree_setup`, and no code looks for a lockfile. On the first JavaScript project this went unnoticed until tests produced wrong results.

Expected: when the repo root contains a known lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock`, `Gemfile.lock`) and `worktree_setup` is unset, `pipeline register` prints a warning naming the lockfile and `worktree_setup`, and `pipeline diagnostics` shows it as a row. A test: a project with `package-lock.json` and no `worktree_setup` currently registers with no such warning.


## Reproduction

Two tests, both fail on the branch before the fix.

1. `tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree` -- `worktree_setup = "echo setup-broke; exit 3"`; `ensure_worktree()` returns the path (worktree.py:97 discards the code).
2. `tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup` -- `package-lock.json`, no `worktree_setup`; `register --force` prints no warning.

Command: `uv run --group dev pytest -q tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup`

```
AssertionError: worktree_setup exited 3 but the worktree was returned as ready
assert ('package-lock.json' in "--force: registering without checking this project's test commands ... registered /tmp/...")
```

expect: AssertionError: worktree_setup exited 3 but the worktree was returned as ready

The base-checkout half (`worktree.py:128`) and the `diagnostics` row have no test yet; the plan must cover them.

## Digest

Files and what each owns in this change:
- `pipeline/core/worktree.py` -- `ensure_worktree()` runs `worktree_setup` at line 97 and discards the code; `base_checkout()` does the same at line 129. `drop_worktree()` runs `worktree_teardown`, then `git worktree remove --force`, and keeps the branch. `run_cmd()` returns `(rc, bounded output)`. New here: `SETUP_FAILED`, `LOCKFILES`, `unset_setup_lockfile()`.
- `pipeline/core/gate.py` -- `_base_findings()` (line 634-637) turns `base_checkout()`'s `(None, err)` into `could not check out base ...`, an unlisted finding, so today it reads as substantive (`bad-plan`, charges `plan_validation_attempts`, respawns planning). `_base_suite()` (line 709-711) turns it into a non-empty `why` and fails closed; no change there. `environment_only()` is `any(f.startswith(ENVIRONMENT_MARKS))`, so one `ENVIRONMENT: ` finding escalates at `plan-validation` and charges nothing.
- `pipeline/daemon/supervisor.py:899-901` -- `start()` calls `ensure_worktree()`; `None` goes to `bail("could not create a worktree")`, which escalates. No change.
- `pipeline/cli/main.py` -- `cmd_diagnostics()` (line 596) and `cmd_register()` (line 650). Diagnostics already reads `project_config()` through `project_harness()`, so one more config read adds no mutation (DEC-115).
- Docs that count diagnostics rows: `README.md:197` and `pipeline/templates/skills/file-ticket/SKILL.md:188` both say "eight rows". `tests/test_cli.py::test_diagnostics_documentation_explains_rows_and_force_boundary` checks row labels in both files. `pipeline/templates/skills/pipeline-config/SKILL.md:202` documents `worktree_setup`.

Gotchas:
1. Remove the checkout when setup fails. `ensure_worktree()` returns early on `wt.is_dir()`, so a checkout left behind comes back as ready on the next `start()` (for example after `pipeline resume`) and setup never re-runs. `drop_worktree()` keeps the branch, so no commit is lost.
2. In `base_checkout()` do not rebind `code`. The `finally` reads it to decide cleanup, and cleanup must still run after a setup failure (DEC-091).
3. `project_config()` raises `PipelineError` for a missing config and `tomllib.TOMLDecodeError` (a `ValueError` subclass) for a malformed one. Catch both.
4. The lockfile check reads the registered project directory, not `git rev-parse --show-toplevel`. This repo has `uv.lock` and no `worktree_setup`, so `pipeline register` here will print the warning. It is a warning, never a refusal.
5. The escalation reason stays `could not create a worktree`. The setup output goes to the dispatcher's stdout, exactly as a failed `git worktree add` does today.
6. In `git_project()` (`tests/helpers.py`) `.project/pipeline.toml` is untracked, so `project_config()` reads it off disk and a test can edit it between two CLI runs.

Baseline, measured on ab9e041: `uv run --group dev pytest -q tests/test_worktree.py tests/test_cli.py tests/test_gate.py` printed `2 failed, 209 passed`. The 2 failures are this ticket's two reproduction tests.

## Decisions checked

Grep terms over `.project/decisions/`: `worktree_setup`, `base_checkout`, `ensure_worktree`, `lockfile`, `diagnostics`, `cmd_register`. None of the records below carries `superseded-by:`.
- DEC-091 (active): teardown runs on both removal paths, and a failed teardown is printed while removal proceeds. The plan reuses `drop_worktree()` for the ticket worktree, and `base_checkout()`'s `finally` still tears down and removes. DEC-091 also says a `worktree_setup` failure "surfaces as a red stage"; worktree.py:97 discarded the code. This change makes that claim true, so no correction is filed.
- DEC-017 (active): the base run is load-bearing and must fail closed. A setup failure on base now yields no base run at all.
- DEC-029 (active): `revalidating` gets `fail` whatever the findings say. The new `ENVIRONMENT: ` finding escalates only at `plan-validation`, the same as the existing one.
- DEC-115 (active): `diagnostics` is read-only, and informational rows do not fail it. The new row reads config only and never changes the exit code.
- DEC-068 (active): register refusals live in `cmd_register()`. The lockfile notice is a warning, printed with or without `--force`, never a refusal.
- DEC-084 (active): one `SKILL.md` per skill directory. The pipeline-config edit stays inside that file.
- DEC-083 (active): `mirror_ticket()` writes only when the mirror file exists, so `Ticket.save()` cannot recreate a removed worktree directory.

## Plan

1. Add two failing tests to `tests/test_worktree.py`, after `test_a_failing_worktree_setup_fails_the_ticket_worktree`, and run them to watch them fail.
   `test_a_failed_worktree_setup_leaves_no_checkout_behind`: `d, sh = git_project()`; `meta = {"id": "TICKET-001", "branch": "ticket/001"}`; assert `W.ensure_worktree(d, meta, {"base": "main", "worktree_setup": "exit 3"}) is None`; assert `not W.worktree(d, meta).exists()`; assert `sh("git rev-parse --verify --quiet ticket/001").returncode == 0` (branch kept); then `wt = W.ensure_worktree(d, meta, {"base": "main", "worktree_setup": "touch setup-ran"})` and assert `wt is not None and (wt / "setup-ran").is_file()`; `shutil.rmtree(d, ignore_errors=True)`.
   `test_a_failing_worktree_setup_fails_the_base_checkout(capsys)`: `d, sh = git_project()`; inside `with W.base_checkout(d, {"base": "main", "worktree_setup": "echo setup-broke; exit 3"}) as (wt, err):` assert `wt is None`, `err.startswith(W.SETUP_FAILED)` and `"setup-broke" in err`; after the block assert `"worktree_setup failed in the base checkout" in capsys.readouterr().out` and `len(sh("git worktree list").stdout.splitlines()) == 1`; rmtree.
   Run `uv run --group dev pytest -q tests/test_worktree.py`; expect these two plus the triage test to fail.
2. In `pipeline/core/worktree.py`, make a non-zero `worktree_setup` fail both checkouts.
   Below `OUTPUT_EDGE = 2000` add `SETUP_FAILED = "worktree_setup exited "` with a one-line comment: the prefix `gate._base_findings()` matches to tell a setup failure from a failed `git worktree add`.
   In `ensure_worktree()` replace `run_cmd(cfg["worktree_setup"], wt)` with `code, out = run_cmd(cfg["worktree_setup"], wt)` and, when `code` is non-zero: `print(f"  worktree_setup failed for {meta['id']} (exit {code}): {out.strip()[:300]}")`, then `drop_worktree(project, meta, cfg)`, then `return None`. Comment above the removal: a checkout left behind is returned as ready by the `wt.is_dir()` early return, and setup never re-runs; `drop_worktree()` keeps the branch.
   In `base_checkout()` replace `run_cmd(cfg["worktree_setup"], wt)` with `setup_code, setup_out = run_cmd(cfg["worktree_setup"], wt)`; when `setup_code` is non-zero: `print(f"  worktree_setup failed in the base checkout (exit {setup_code}): {setup_out.strip()[:300]}")`, `yield None, f"{SETUP_FAILED}{setup_code} in the base checkout\n{setup_out}"`, `return`. Keep `yield wt, ""` for the success path. Do not touch `code` or the `finally`. Update the docstring: it also yields `(None, ...)` when `worktree_setup` fails, because a base run without the project's dependencies proves nothing.
   Run `uv run --group dev pytest -q tests/test_worktree.py tests/test_dispatch.py`; expect no failures. Commit `fix(TICKET-147): a failing worktree_setup fails the ticket worktree and the base checkout`.
3. Add a failing test to `tests/test_gate.py` and run it to watch it fail.
   Extend the imports: `from helpers import FIXTURE, ROOT, git_project, project`, `ENVIRONMENT_MARK` in the `pipeline.core.gate` import, and `from pipeline.core import worktree as W`.
   `test_a_base_checkout_whose_setup_fails_is_an_environment_finding`: `d, _ = git_project()`; `wd = W.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})`; `findings, on_base, zero = _base_findings(d, {"base": "main", "test_one": "true", "worktree_setup": "echo setup-broke; exit 3"}, wd, ["tests/test_x.py::test_x"])`; assert `len(findings) == 1`, `findings[0].startswith(ENVIRONMENT_MARK)`, `"setup-broke" in findings[0]`, `on_base == {}` and `zero == {}`; `shutil.rmtree(d, ignore_errors=True)`.
   Run `uv run --group dev pytest -q tests/test_gate.py::test_a_base_checkout_whose_setup_fails_is_an_environment_finding`; expect it to fail on the `startswith(ENVIRONMENT_MARK)` assertion.
4. In `pipeline/core/gate.py`, route a base setup failure to the `ENVIRONMENT` verdict.
   Import `SETUP_FAILED` from `pipeline.core.worktree` beside `base_checkout`.
   In `_base_findings()`, inside `if base_wt is None:` and before the existing `could not check out base` return, add: if `err.startswith(SETUP_FAILED)`, return one finding, `f"{ENVIRONMENT_MARK}` + "`worktree_setup` failed in the throwaway checkout of base `{base}`, so {named} cannot be re-run there and base proves nothing. Fix `worktree_setup` or the environment, then resume the ticket" + the err fence the existing return uses (`\n```\n{err[-1200:]}\n```"`), with `{}, {}` as the other two values.
   Add a comment there: no plan can fix the environment, so this must not charge a planning respawn (TICKET-147). Leave `_base_suite()` unchanged; its non-empty `why` already fails closed.
   Run `uv run --group dev pytest -q tests/test_gate.py`; expect no failures. Commit `fix(TICKET-147): a failed worktree_setup on base is an environment finding`.
5. Add a failing diagnostics test to `tests/test_cli.py` and extend two existing diagnostics tests, then run them to watch them fail.
   `test_diagnostics_reports_a_lockfile_without_worktree_setup`: `d, _ = git_project()`; write `"{}"` to `d / "package-lock.json"`; `env = {"XDG_CONFIG_HOME": str(tempfile.mkdtemp())}`; `r = cli(d, "diagnostics", env=env)`; parse rows as `test_diagnostics_reports_runtime_harness_and_git_readiness` does; assert `r.returncode == 0` and `rows["worktree setup"].startswith("missing: package-lock.json")`. Then append the line `worktree_setup = "true"` to `d / ".project" / "pipeline.toml"`, run `cli(d, "diagnostics", env=env)` again, and assert `rows["worktree setup"] == "set"`; rmtree.
   Add `"worktree setup"` to `terms` in `test_diagnostics_documentation_explains_rows_and_force_boundary`, and to the label tuple in `test_diagnostics_exits_nonzero_when_git_author_is_missing`.
   Run `uv run --group dev pytest -q tests/test_cli.py`; expect the new test, the docs test, the git-author test and `test_register_warns_when_a_lockfile_has_no_worktree_setup` to fail.
6. Add the lockfile check to `pipeline/core/worktree.py` and wire it into `pipeline/cli/main.py`.
   In `pipeline/core/worktree.py`, after `base_ref()`: `LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock", "Gemfile.lock")`, and `def unset_setup_lockfile(project: Path, cfg: dict) -> str | None:` returning `None` when `cfg.get("worktree_setup")` is set, else `next((n for n in LOCKFILES if (project / n).is_file()), None)`. Docstring: a ticket worktree is a fresh checkout with no dependencies installed; a lockfile at the project root says the project needs some.
   In `pipeline/cli/main.py`, add `unset_setup_lockfile` to the `pipeline.core.worktree` import, and add `def worktree_setup_state(path: Path) -> str:` above `cmd_diagnostics()`, with this body:
   try `cfg = project_config(path)`; on `(PipelineError, ValueError) as e` return `f"unknown ({e})"`; `lock = unset_setup_lockfile(path, cfg)`; if `lock`, return `f"missing: {lock} found and worktree_setup is unset -- ticket worktrees are fresh checkouts with no dependencies installed"`; else return `"set"` if `cfg.get("worktree_setup")` else `"not needed (no known lockfile)"`.
   In `cmd_diagnostics()`, right after the `registration:` print, add `print(f"worktree setup: {worktree_setup_state(path)}")`; it never changes the exit code. Change the docstring's "exactly eight" to "exactly nine".
   In `cmd_register()`, right after `print(f"registered {registry.register(path)}")`, add `state = worktree_setup_state(path)` and, when `state.startswith("missing: ")`, print `f"  warning: {state.removeprefix('missing: ')}; set worktree_setup in .project/pipeline.toml (the pipeline-config skill shows how)"`. Comment: a warning, never a refusal, and `--force` does not skip it.
   Run `uv run --group dev pytest -q tests/test_cli.py tests/test_worktree.py`; expect only the docs test to fail (step 7 fixes it).
7. Update `README.md` and `pipeline/templates/skills/file-ticket/SKILL.md` for the ninth diagnostics row.
   `README.md:197`: "prints eight rows" becomes "prints nine rows". After the `registration` bullet add: "- `worktree setup` -- `set`, `not needed (no known lockfile)`, or `missing: <lockfile> found and worktree_setup is unset ...` when the project root has `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock` or `Gemfile.lock` and no `worktree_setup`. Informational: it never changes the exit code."
   `pipeline/templates/skills/file-ticket/SKILL.md:188`: "prints eight rows" becomes "prints nine rows". In the row list, add `worktree setup` (`missing: <lockfile> ...` when a lockfile has no `worktree_setup`) after `registration`.
   Run `uv run --group dev pytest -q tests/test_cli.py`; expect no failures.
8. Document the new behaviour in `pipeline/templates/skills/pipeline-config/SKILL.md`, in the `worktree_setup` section, right after its `toml` example.
   Add this paragraph: "**A non-zero exit fails the checkout.** In a ticket worktree the dispatcher prints the output, removes the checkout (the branch stays) and escalates the ticket with `could not create a worktree`; fix the command, then `pipeline resume`. In the gate's checkout of base it is an `ENVIRONMENT:` finding, and the ticket escalates without a charge. A project with `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock` or `Gemfile.lock` at its root and no `worktree_setup` gets a warning from `pipeline register` and a `worktree setup: missing: ...` row from `pipeline diagnostics`."
   Run `uv run --group dev pytest -q tests/test_stages.py tests/test_cli.py tests/test_worktree.py tests/test_gate.py tests/test_dispatch.py`; expect no failures. Commit `feat(TICKET-147): warn when a lockfile has no worktree_setup`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup` exits 0.
- `tests/test_worktree.py::test_a_failed_worktree_setup_leaves_no_checkout_behind` passes.
- `tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_base_checkout` passes.
- `tests/test_gate.py::test_a_base_checkout_whose_setup_fails_is_an_environment_finding` passes.
- `tests/test_cli.py::test_diagnostics_reports_a_lockfile_without_worktree_setup` passes.
- `tests/test_cli.py::test_diagnostics_documentation_explains_rows_and_force_boundary` passes.
- `uv run --group dev pytest -q tests/test_worktree.py tests/test_cli.py tests/test_gate.py tests/test_dispatch.py tests/test_stages.py` exits 0. Measured baseline on ab9e041 for the first three files: `2 failed, 209 passed`, both failures this ticket's reproduction tests.
- `grep -l 'eight rows' README.md pipeline/templates/skills/file-ticket/SKILL.md` prints nothing and exits 1.

## Decisions

- A non-zero `worktree_setup` fails the checkout it ran in. Dropping that check brings back the original bug: on an npm-workspaces project Node resolves the main checkout's `node_modules` by walking up the tree, so every stage tests the main checkout's code with no error anywhere.
- `ensure_worktree()` removes the checkout when setup fails, through `drop_worktree()`, and keeps the branch. Without the removal, the `wt.is_dir()` early return hands the broken checkout back as ready on the next `start()`, and setup never re-runs.
- A setup failure in `base_checkout()` yields `(None, err)` with `err` starting with `SETUP_FAILED`. `_base_findings()` turns that prefix into an `ENVIRONMENT: ` finding, so the ticket escalates without charging `plan_validation_attempts`; no plan can fix a broken environment. A failed `git worktree add` of base keeps its old substantive finding.
- The lockfile check is a warning in `register` and an informational `diagnostics` row, never a refusal or a non-zero exit. A project that installs dependencies on demand (`uv run` syncs before it runs) needs no `worktree_setup`, and a refusal would block it.

## Rollback

Revert the three commits from steps 2, 4 and 8. The tests from steps 1, 3 and 5 go red again; nothing else depends on the change, and no data or config migrates.

Riskiest step: step 2's `drop_worktree()` call on a just-created checkout, because every `start()` goes through `ensure_worktree()`. Fallback when step 2's own check (`tests/test_worktree.py tests/test_dispatch.py`) goes red because of that call:
1. Replace the call with `run_cmd(f"git worktree remove --force {shlex.quote(str(wt))}", project)`. It skips `worktree_teardown` but keeps the removal.
2. If that is still red, stop and return `blocked` with the failing output. Do not leave the checkout in place: that returns the broken tree as ready.

## Thread

### 2026-10-01 12:07:29Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-10-01 triage · finding

Reproduced both halves with the two tests in `## Reproduction` (commit ab9e041). Root cause 1: `run_cmd(cfg["worktree_setup"], wt)` at worktree.py:97 and :129 drops the exit code. Root cause 2: no lockfile check exists in `cmd_register` or `cmd_diagnostics`. Result `ok`, not `chore`: base-checkout semantics and the diagnostics row are design choices.

### 2026-10-01 12:08:16Z · triage · session · session=bb6a9066-9968-4f16-a8a4-1c8daee8b783

`triage` ran as session `bb6a9066-9968-4f16-a8a4-1c8daee8b783`
- replay: `claude --resume bb6a9066-9968-4f16-a8a4-1c8daee8b783`
- log: `.project/logs/TICKET-147-triage-bb6a9066.log`
- cost: $0.24 of a $3 cap
- tokens: 4,310 out (105 thinking) · 16 in · 247,965 cache read · 35,924 cache write

### 2026-10-01 12:08:16Z · triage · finding · severity=minor

`correction` was not applied: want `DEC-<digits> -- <text>` on one line, got 'null'; nothing written

### 2026-10-01 12:08:16Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ two failing tests committed: ignored worktree_setup exit code, and no lockfile warning at register

### 2026-10-01 12:15:25Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree` fails as required
```
___ test_a_failing_worktree_setup_fails_the_ticket_worktree ____________

capsys = <_pytest.capture.CaptureFixture object at 0x7f0549183410>

    def test_a_failing_worktree_setup_fails_the_ticket_worktree(capsys):
        """A non-zero `worktree_setup` used to be discarded: the worktree came
        back as ready with no dependencies installed."""
        d, _ = git_project()
        meta = {"id": "TICKET-001", "branch": "ticket/001"}
        cfg = {"base": "main", "worktree_setup": "echo setup-broke; exit 3"}
    
        wt = W.ensure_worktree(d, meta, cfg)
    
>       assert wt is None, "worktree_setup exited 3 but the worktree was returned as ready"
E       AssertionError: worktree_setup exited 3 but the worktree was returned as ready
E       assert PosixPath('/tmp/tmp583sq039/.worktrees/TICKET-001') is None

tests/test_worktree.py:380: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup` fails as required
```
ree_setup ___________

    def test_register_warns_when_a_lockfile_has_no_worktree_setup():
        """A fresh worktree has no installed dependencies; a project with a
        lockfile and no `worktree_setup` registered with no word about it."""
        d = register_project()
        (d / "package-lock.json").write_text("{}")
        r = cli(d, "register", str(d), "--force",
                env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
        out = r.stdout + r.stderr
>       assert "package-lock.json" in out and "worktree_setup" in out, out
E       AssertionError: --force: registering without checking this project's test commands
E         registered /tmp/tmpl31d703p
E         
E       assert ('package-lock.json' in "--force: registering without checking this project's test commands\nregistered /tmp/tmpl31d703p\n")

tests/test_cli.py:1751: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.27s ===============================

```
- ok: `tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree` fails on base `main` too -- the bug is not already fixed upstream
```
worktree(d, meta, cfg)
    
>       assert wt is None, "worktree_setup exited 3 but the worktree was returned as ready"
E       AssertionError: worktree_setup exited 3 but the worktree was returned as ready
E       assert PosixPath('/tmp/tmp2mi7g4l7/.worktrees/TICKET-001') is None

tests/test_worktree.py:380: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-0zwxhmxo/base
      Built pipeline @ file:///tmp/pipeline-base-0zwxhmxo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 832ms

```
- ok: `tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup` fails on base `main` too -- the bug is not already fixed upstream
```
ree_setup ___________

    def test_register_warns_when_a_lockfile_has_no_worktree_setup():
        """A fresh worktree has no installed dependencies; a project with a
        lockfile and no `worktree_setup` registered with no word about it."""
        d = register_project()
        (d / "package-lock.json").write_text("{}")
        r = cli(d, "register", str(d), "--force",
                env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
        out = r.stdout + r.stderr
>       assert "package-lock.json" in out and "worktree_setup" in out, out
E       AssertionError: --force: registering without checking this project's test commands
E         registered /tmp/tmpg6_9u8y2
E         
E       assert ('package-lock.json' in "--force: registering without checking this project's test commands\nregistered /tmp/tmpg6_9u8y2\n")

tests/test_cli.py:1751: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.59s ===============================

```
- `files_declared` is empty
- plan step names no declared file: '1. Add two failing tests to `tests/test_worktree.py`, after `test_a_failing_worktree_setup_fails_the_ticket_worktree`, and run them to watch them fail. `test_a_failed_worktree_setup_leaves_no_checkout_behind`: `d, sh = git_project()`; `meta = {"id": "TICKET-001", "branch": "ticket/001"}`; assert `W.ensure_worktree(d, meta, {"base": "main", "worktree_setup": "exit 3"}) is None`; assert `not W.worktree(d, meta).exists()`; assert `sh("git rev-parse --verify --quiet ticket/001").returncode == 0` (branch kept); then `wt = W.ensure_worktree(d, meta, {"base": "main", "worktree_setup": "touch setup-ran"})` and assert `wt is not None and (wt / "setup-ran").is_file()`; `shutil.rmtree(d, ignore_errors=True)`. `test_a_failing_worktree_setup_fails_the_base_checkout(capsys)`: `d, sh = git_project()`; inside `with W.base_checkout(d, {"base": "main", "worktree_setup": "echo setup-broke; exit 3"}) as (wt, err):` assert `wt is None`, `err.startswith(W.SETUP_FAILED)` and `"setup-broke" in err`; after the block assert `"worktree_setup failed in the base checkout" in capsys.readouterr().out` and `len(sh("git worktree list").stdout.splitlines()) == 1`; rmtree. Run `uv run --group dev pytest -q tests/test_worktree.py`; expect these two plus the triage test to fail.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. In `pipeline/core/worktree.py`, make a non-zero `worktree_setup` fail both checkouts. Below `OUTPUT_EDGE = 2000` add `SETUP_FAILED = "worktree_setup exited "` with a one-line comment: the prefix `gate._base_findings()` matches to tell a setup failure from a failed `git worktree add`. In `ensure_worktree()` replace `run_cmd(cfg["worktree_setup"], wt)` with `code, out = run_cmd(cfg["worktree_setup"], wt)` and, when `code` is non-zero: `print(f"  worktree_setup failed for {meta[\'id\']} (exit {code}): {out.strip()[:300]}")`, then `drop_worktree(project, meta, cfg)`, then `return None`. Comment above the removal: a checkout left behind is returned as ready by the `wt.is_dir()` early return, and setup never re-runs; `drop_worktree()` keeps the branch. In `base_checkout()` replace `run_cmd(cfg["worktree_setup"], wt)` with `setup_code, setup_out = run_cmd(cfg["worktree_setup"], wt)`; when `setup_code` is non-zero: `print(f"  worktree_setup failed in the base checkout (exit {setup_code}): {setup_out.strip()[:300]}")`, `yield None, f"{SETUP_FAILED}{setup_code} in the base checkout\\n{setup_out}"`, `return`. Keep `yield wt, ""` for the success path. Do not touch `code` or the `finally`. Update the docstring: it also yields `(None, ...)` when `worktree_setup` fails, because a base run without the project\'s dependencies proves nothing. Run `uv run --group dev pytest -q tests/test_worktree.py tests/test_dispatch.py`; expect no failures. Commit `fix(TICKET-147): a failing worktree_setup fails the ticket worktree and the base checkout`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Add a failing test to `tests/test_gate.py` and run it to watch it fail. Extend the imports: `from helpers import FIXTURE, ROOT, git_project, project`, `ENVIRONMENT_MARK` in the `pipeline.core.gate` import, and `from pipeline.core import worktree as W`. `test_a_base_checkout_whose_setup_fails_is_an_environment_finding`: `d, _ = git_project()`; `wd = W.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})`; `findings, on_base, zero = _base_findings(d, {"base": "main", "test_one": "true", "worktree_setup": "echo setup-broke; exit 3"}, wd, ["tests/test_x.py::test_x"])`; assert `len(findings) == 1`, `findings[0].startswith(ENVIRONMENT_MARK)`, `"setup-broke" in findings[0]`, `on_base == {}` and `zero == {}`; `shutil.rmtree(d, ignore_errors=True)`. Run `uv run --group dev pytest -q tests/test_gate.py::test_a_base_checkout_whose_setup_fails_is_an_environment_finding`; expect it to fail on the `startswith(ENVIRONMENT_MARK)` assertion.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '4. In `pipeline/core/gate.py`, route a base setup failure to the `ENVIRONMENT` verdict. Import `SETUP_FAILED` from `pipeline.core.worktree` beside `base_checkout`. In `_base_findings()`, inside `if base_wt is None:` and before the existing `could not check out base` return, add: if `err.startswith(SETUP_FAILED)`, return one finding, `f"{ENVIRONMENT_MARK}` + "`worktree_setup` failed in the throwaway checkout of base `{base}`, so {named} cannot be re-run there and base proves nothing. Fix `worktree_setup` or the environment, then resume the ticket" + the err fence the existing return uses (`\\n```\\n{err[-1200:]}\\n```"`), with `{}, {}` as the other two values. Add a comment there: no plan can fix the environment, so this must not charge a planning respawn (TICKET-147). Leave `_base_suite()` unchanged; its non-empty `why` already fails closed. Run `uv run --group dev pytest -q tests/test_gate.py`; expect no failures. Commit `fix(TICKET-147): a failed worktree_setup on base is an environment finding`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '5. Add a failing diagnostics test to `tests/test_cli.py` and extend two existing diagnostics tests, then run them to watch them fail. `test_diagnostics_reports_a_lockfile_without_worktree_setup`: `d, _ = git_project()`; write `"{}"` to `d / "package-lock.json"`; `env = {"XDG_CONFIG_HOME": str(tempfile.mkdtemp())}`; `r = cli(d, "diagnostics", env=env)`; parse rows as `test_diagnostics_reports_runtime_harness_and_git_readiness` does; assert `r.returncode == 0` and `rows["worktree setup"].startswith("missing: package-lock.json")`. Then append the line `worktree_setup = "true"` to `d / ".project" / "pipeline.toml"`, run `cli(d, "diagnostics", env=env)` again, and assert `rows["worktree setup"] == "set"`; rmtree. Add `"worktree setup"` to `terms` in `test_diagnostics_documentation_explains_rows_and_force_boundary`, and to the label tuple in `test_diagnostics_exits_nonzero_when_git_author_is_missing`. Run `uv run --group dev pytest -q tests/test_cli.py`; expect the new test, the docs test, the git-author test and `test_register_warns_when_a_lockfile_has_no_worktree_setup` to fail.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '6. Add the lockfile check to `pipeline/core/worktree.py` and wire it into `pipeline/cli/main.py`. In `pipeline/core/worktree.py`, after `base_ref()`: `LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock", "Gemfile.lock")`, and `def unset_setup_lockfile(project: Path, cfg: dict) -> str | None:` returning `None` when `cfg.get("worktree_setup")` is set, else `next((n for n in LOCKFILES if (project / n).is_file()), None)`. Docstring: a ticket worktree is a fresh checkout with no dependencies installed; a lockfile at the project root says the project needs some. In `pipeline/cli/main.py`, add `unset_setup_lockfile` to the `pipeline.core.worktree` import, and add `def worktree_setup_state(path: Path) -> str:` above `cmd_diagnostics()`, with this body: try `cfg = project_config(path)`; on `(PipelineError, ValueError) as e` return `f"unknown ({e})"`; `lock = unset_setup_lockfile(path, cfg)`; if `lock`, return `f"missing: {lock} found and worktree_setup is unset -- ticket worktrees are fresh checkouts with no dependencies installed"`; else return `"set"` if `cfg.get("worktree_setup")` else `"not needed (no known lockfile)"`. In `cmd_diagnostics()`, right after the `registration:` print, add `print(f"worktree setup: {worktree_setup_state(path)}")`; it never changes the exit code. Change the docstring\'s "exactly eight" to "exactly nine". In `cmd_register()`, right after `print(f"registered {registry.register(path)}")`, add `state = worktree_setup_state(path)` and, when `state.startswith("missing: ")`, print `f"  warning: {state.removeprefix(\'missing: \')}; set worktree_setup in .project/pipeline.toml (the pipeline-config skill shows how)"`. Comment: a warning, never a refusal, and `--force` does not skip it. Run `uv run --group dev pytest -q tests/test_cli.py tests/test_worktree.py`; expect only the docs test to fail (step 7 fixes it).' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '7. Update `README.md` and `pipeline/templates/skills/file-ticket/SKILL.md` for the ninth diagnostics row. `README.md:197`: "prints eight rows" becomes "prints nine rows". After the `registration` bullet add: "- `worktree setup` -- `set`, `not needed (no known lockfile)`, or `missing: <lockfile> found and worktree_setup is unset ...` when the project root has `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock` or `Gemfile.lock` and no `worktree_setup`. Informational: it never changes the exit code." `pipeline/templates/skills/file-ticket/SKILL.md:188`: "prints eight rows" becomes "prints nine rows". In the row list, add `worktree setup` (`missing: <lockfile> ...` when a lockfile has no `worktree_setup`) after `registration`. Run `uv run --group dev pytest -q tests/test_cli.py`; expect no failures.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '8. Document the new behaviour in `pipeline/templates/skills/pipeline-config/SKILL.md`, in the `worktree_setup` section, right after its `toml` example. Add this paragraph: "**A non-zero exit fails the checkout.** In a ticket worktree the dispatcher prints the output, removes the checkout (the branch stays) and escalates the ticket with `could not create a worktree`; fix the command, then `pipeline resume`. In the gate\'s checkout of base it is an `ENVIRONMENT:` finding, and the ticket escalates without a charge. A project with `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock` or `Gemfile.lock` at its root and no `worktree_setup` gets a warning from `pipeline register` and a `worktree setup: missing: ...` row from `pipeline diagnostics`." Run `uv run --group dev pytest -q tests/test_stages.py tests/test_cli.py tests/test_worktree.py tests/test_gate.py tests/test_dispatch.py`; expect no failures. Commit `feat(TICKET-147): warn when a lockfile has no worktree_setup`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-10-01 planning · finding

Plan written: 8 steps over 9 files. `pipeline gate TICKET-147` printed only the two findings expected before dispatch: `files_declared` is empty, and each step `names no declared file`.

Design choices the ticket left open:
1. Ticket worktree: on a non-zero setup, `ensure_worktree()` prints the output, removes the checkout through `drop_worktree()` (branch kept) and returns `None`. Without the removal, the `wt.is_dir()` early return hands the broken checkout back as ready on the next `start()`.
2. Base checkout: `base_checkout()` yields `(None, err)`, and `_base_findings()` emits an `ENVIRONMENT: ` finding. The ticket escalates with no charge instead of respawning planning, which cannot fix an environment. This adds `pipeline/core/gate.py` to the ticket's expected files.
3. The diagnostics row `worktree setup` is informational; it never changes the exit code (DEC-115). The row count moves from eight to nine, so `README.md` and the file-ticket `SKILL.md` change too.

Out of scope, noted only: `start()` escalates with the generic `could not create a worktree`, so the setup output reaches dispatcher stdout, not the ticket. This repo has `uv.lock` and no `worktree_setup`, so `pipeline register` here will print the new warning.

### 2026-10-01 12:16:10Z · planning · session · session=3da5e865-cd97-4443-9234-996931afdcbf

`planning` ran as session `3da5e865-cd97-4443-9234-996931afdcbf`
- replay: `claude --resume 3da5e865-cd97-4443-9234-996931afdcbf`
- log: `.project/logs/TICKET-147-planning-3da5e865.log`
- cost: $2.11 of a $10 cap
- tokens: 38,288 out (15,046 thinking) · 56 in · 2,038,793 cache read · 116,618 cache write

### 2026-10-01 12:16:10Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ 8-step plan: a failing worktree_setup fails the ticket worktree (removed, branch kept) and yields an ENVIRONMENT finding on base; register warns and diagnostics adds a row for a lockfile with no worktree_setup

### 2026-10-01 12:17:30Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree` fails as required
```
___ test_a_failing_worktree_setup_fails_the_ticket_worktree ____________

capsys = <_pytest.capture.CaptureFixture object at 0x7fc0779ef3e0>

    def test_a_failing_worktree_setup_fails_the_ticket_worktree(capsys):
        """A non-zero `worktree_setup` used to be discarded: the worktree came
        back as ready with no dependencies installed."""
        d, _ = git_project()
        meta = {"id": "TICKET-001", "branch": "ticket/001"}
        cfg = {"base": "main", "worktree_setup": "echo setup-broke; exit 3"}
    
        wt = W.ensure_worktree(d, meta, cfg)
    
>       assert wt is None, "worktree_setup exited 3 but the worktree was returned as ready"
E       AssertionError: worktree_setup exited 3 but the worktree was returned as ready
E       assert PosixPath('/tmp/tmpvzlb61rt/.worktrees/TICKET-001') is None

tests/test_worktree.py:380: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup` fails as required
```
ree_setup ___________

    def test_register_warns_when_a_lockfile_has_no_worktree_setup():
        """A fresh worktree has no installed dependencies; a project with a
        lockfile and no `worktree_setup` registered with no word about it."""
        d = register_project()
        (d / "package-lock.json").write_text("{}")
        r = cli(d, "register", str(d), "--force",
                env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
        out = r.stdout + r.stderr
>       assert "package-lock.json" in out and "worktree_setup" in out, out
E       AssertionError: --force: registering without checking this project's test commands
E         registered /tmp/tmpajexrpvm
E         
E       assert ('package-lock.json' in "--force: registering without checking this project's test commands\nregistered /tmp/tmpajexrpvm\n")

tests/test_cli.py:1751: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.29s ===============================

```
- ok: `tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree` fails on base `main` too -- the bug is not already fixed upstream
```
_worktree(d, meta, cfg)
    
>       assert wt is None, "worktree_setup exited 3 but the worktree was returned as ready"
E       AssertionError: worktree_setup exited 3 but the worktree was returned as ready
E       assert PosixPath('/tmp/tmpg7u7d8vf/.worktrees/TICKET-001') is None

tests/test_worktree.py:380: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-pfcaqx8x/base
      Built pipeline @ file:///tmp/pipeline-base-pfcaqx8x/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 71ms

```
- ok: `tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup` fails on base `main` too -- the bug is not already fixed upstream
```
ree_setup ___________

    def test_register_warns_when_a_lockfile_has_no_worktree_setup():
        """A fresh worktree has no installed dependencies; a project with a
        lockfile and no `worktree_setup` registered with no word about it."""
        d = register_project()
        (d / "package-lock.json").write_text("{}")
        r = cli(d, "register", str(d), "--force",
                env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
        out = r.stdout + r.stderr
>       assert "package-lock.json" in out and "worktree_setup" in out, out
E       AssertionError: --force: registering without checking this project's test commands
E         registered /tmp/tmp2aizoa4x
E         
E       assert ('package-lock.json' in "--force: registering without checking this project's test commands\nregistered /tmp/tmp2aizoa4x\n")

tests/test_cli.py:1751: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.61s ===============================

```

### 2026-10-01 plan-validation · finding · verdict=ok

long: eight scored items plus one unverified note.

1. Root cause -- pass. `ensure_worktree()` (worktree.py:97) and `base_checkout()` (:129) call `run_cmd(cfg["worktree_setup"], wt)` and drop the `(rc, out)` it returns. No code reads the project root for a lockfile. Steps 2 and 6 fix both causes, not only the assertions.
2. Decisions -- pass. The `finally` in `base_checkout()` gates on `code` (git's rc), so `yield None, ...; return` still tears down and removes (DEC-091). `_base_suite()`'s non-empty `why` fails closed (DEC-017). `environment_only()` escalates at `plan-validation` only (DEC-029). Diagnostics already calls `project_config()` through `project_harness()`, so the new read adds no new mutation (DEC-115).
3. Scope -- pass. `gate.py`, `README.md` and the file-ticket `SKILL.md` each trace to a named criterion.
4. Criteria -- pass. Each new test fails without its step: without the removal, `W.worktree(d, meta)` stays on disk; an unchanged `_base_findings()` returns `could not check out base`.
5. No research left -- pass. Every line anchor matches ab9e041.
6. Riskiest step -- pass. Step 2's `drop_worktree()` call; the plan states a two-step fallback.
7. Regression -- pass. `test_drop_worktree_runs_worktree_teardown` and `test_base_checkout_runs_worktree_teardown` cover the success paths. In `gate()`, a resumed ticket with a passing test also gets a substantive `exited 0` finding; `environment_only()` is `any()`, so it still escalates.
8. Blast radius -- pass. `bugfix`, 9 files: 3 code, 3 docs, 3 tests.

Unverified: I did not run pytest (read-only stage). The `2 failed, 209 passed` baseline rests on the planning entry.

### 2026-10-01 12:23:34Z · plan-validation · session · session=71f44179-eaa3-47ff-bc4f-c43a18eadd00

`plan-validation` ran as session `71f44179-eaa3-47ff-bc4f-c43a18eadd00`
- replay: `claude --resume 71f44179-eaa3-47ff-bc4f-c43a18eadd00`
- log: `.project/logs/TICKET-147-plan-validation-71f44179.log`
- cost: $0.90 of a $3 cap
- tokens: 10,362 out (4,047 thinking) · 34 in · 889,115 cache read · 64,943 cache write

### 2026-10-01 12:23:34Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items; root cause, decisions, line anchors and the ENVIRONMENT route checked against the code on ab9e041

### 2026-10-01 12:25:54Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-01 12:34:14Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree` fails as required
```
___ test_a_failing_worktree_setup_fails_the_ticket_worktree ____________

capsys = <_pytest.capture.CaptureFixture object at 0x7fb70e19f3e0>

    def test_a_failing_worktree_setup_fails_the_ticket_worktree(capsys):
        """A non-zero `worktree_setup` used to be discarded: the worktree came
        back as ready with no dependencies installed."""
        d, _ = git_project()
        meta = {"id": "TICKET-001", "branch": "ticket/001"}
        cfg = {"base": "main", "worktree_setup": "echo setup-broke; exit 3"}
    
        wt = W.ensure_worktree(d, meta, cfg)
    
>       assert wt is None, "worktree_setup exited 3 but the worktree was returned as ready"
E       AssertionError: worktree_setup exited 3 but the worktree was returned as ready
E       assert PosixPath('/tmp/tmp2d0vswck/.worktrees/TICKET-001') is None

tests/test_worktree.py:380: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup` fails as required
```
ree_setup ___________

    def test_register_warns_when_a_lockfile_has_no_worktree_setup():
        """A fresh worktree has no installed dependencies; a project with a
        lockfile and no `worktree_setup` registered with no word about it."""
        d = register_project()
        (d / "package-lock.json").write_text("{}")
        r = cli(d, "register", str(d), "--force",
                env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
        out = r.stdout + r.stderr
>       assert "package-lock.json" in out and "worktree_setup" in out, out
E       AssertionError: --force: registering without checking this project's test commands
E         registered /tmp/tmpmjye5t07
E         
E       assert ('package-lock.json' in "--force: registering without checking this project's test commands\nregistered /tmp/tmpmjye5t07\n")

tests/test_cli.py:1751: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.29s ===============================

```
- ok: `tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree` fails on base `main` too -- the bug is not already fixed upstream
```
_worktree(d, meta, cfg)
    
>       assert wt is None, "worktree_setup exited 3 but the worktree was returned as ready"
E       AssertionError: worktree_setup exited 3 but the worktree was returned as ready
E       assert PosixPath('/tmp/tmpa1fi9t1n/.worktrees/TICKET-001') is None

tests/test_worktree.py:380: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_failing_worktree_setup_fails_the_ticket_worktree
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-6vvq2uk6/base
      Built pipeline @ file:///tmp/pipeline-base-6vvq2uk6/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 89ms

```
- ok: `tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup` fails on base `main` too -- the bug is not already fixed upstream
```
ree_setup ___________

    def test_register_warns_when_a_lockfile_has_no_worktree_setup():
        """A fresh worktree has no installed dependencies; a project with a
        lockfile and no `worktree_setup` registered with no word about it."""
        d = register_project()
        (d / "package-lock.json").write_text("{}")
        r = cli(d, "register", str(d), "--force",
                env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
        out = r.stdout + r.stderr
>       assert "package-lock.json" in out and "worktree_setup" in out, out
E       AssertionError: --force: registering without checking this project's test commands
E         registered /tmp/tmp45vbzgtk
E         
E       assert ('package-lock.json' in "--force: registering without checking this project's test commands\nregistered /tmp/tmp45vbzgtk\n")

tests/test_cli.py:1751: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_register_warns_when_a_lockfile_has_no_worktree_setup
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.60s ===============================

```

### 2026-10-01 12:34:15Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-10-01 · implementing · finding · verdict=ok

All 8 plan steps done, in order, each test seen red before its code.

- [x] 1-2 worktree tests, then `worktree.py`: setup failure drops the ticket checkout (branch kept) and yields `(None, SETUP_FAILED...)` on base
- [x] 3-4 gate test, then `_base_findings()` returns one `ENVIRONMENT: ` finding
- [x] 5-6 cli tests, then `unset_setup_lockfile()`, `worktree_setup_state()`, register warning, diagnostics row
- [x] 7-8 README, file-ticket and pipeline-config docs

Result: `pytest -q tests/test_stages.py tests/test_cli.py tests/test_worktree.py tests/test_gate.py tests/test_dispatch.py` -> `393 passed`. `grep -l 'eight rows'` prints nothing.
Edited existing tests: the two diagnostics tests only gained the `worktree setup` label, as step 5 says.

### 2026-10-01 12:37:18Z · implementing · session · session=de0d5d98-bd07-40c8-ab51-abf268a59738

`implementing` ran as session `de0d5d98-bd07-40c8-ab51-abf268a59738`
- replay: `claude --resume de0d5d98-bd07-40c8-ab51-abf268a59738`
- log: `.project/logs/TICKET-147-implementing-de0d5d98.log`
- cost: $0.54 of a $10 cap
- tokens: 11,554 out (78 thinking) · 36 in · 892,971 cache read · 61,479 cache write

### 2026-10-01 12:37:18Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ failing worktree_setup now fails ticket worktree and base checkout; register warns and diagnostics shows lockfile row; 393 tests pass

### 2026-10-01 · review · finding · verdict=ok

No blocking findings. I reviewed the delta `ab9e041..cf6e012` (commits 15fbcc8, d07cc8f, cf6e012) against all 8 plan steps, and it matches them.

Evidence:
- `uv run --group dev pytest -q tests/test_worktree.py tests/test_cli.py tests/test_gate.py tests/test_dispatch.py tests/test_stages.py` -> `393 passed in 53.26s`.
- `grep -l 'eight rows' README.md pipeline/templates/skills/file-ticket/SKILL.md` printed nothing, exit 1.
- `base_checkout()` does not rebind `code`. Its `finally` still tears down and removes after a setup failure (worktree.py:149-168).
- The new finding reaches the `environment` verdict. `gate_result()` checks `environment_only()` first (supervisor.py:1109), and both `_base_findings()` call sites (gate.py:841, :931) add it to `findings`.
- `ensure_worktree()` has one caller, supervisor.py:899. `None` still goes to `bail("could not create a worktree")`.
- The diagnostics row adds no mutation. `project_harness(path)` at main.py:623 already calls `project_config()` (config.py:465).

Non-blocking notes:
1. Minor: if `git worktree remove --force` fails inside `drop_worktree()`, the checkout stays. The next `start()` then returns it as ready. The return code goes unchecked here, as it did before this change.
2. Nit: the `cmd_diagnostics()` docstring's first sentence lists the rows' subjects and leaves out worktree setup.

### 2026-10-01 12:39:13Z · review · session · session=6a7b020f-7bf1-4d5a-9942-e88e3506e3e3

`review` ran as session `6a7b020f-7bf1-4d5a-9942-e88e3506e3e3`
- replay: `claude --resume 6a7b020f-7bf1-4d5a-9942-e88e3506e3e3`
- log: `.project/logs/TICKET-147-review-6a7b020f.log`
- cost: $0.60 of a $6 cap
- tokens: 5,055 out (1,585 thinking) · 22 in · 479,353 cache read · 50,279 cache write

### 2026-10-01 12:39:13Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ no blocking findings; diff matches all 8 plan steps, 393 passed on the five affected test files, two non-blocking notes in Thread

### 2026-10-01 12:40:30Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-10-01 13:57:22Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
.HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/147


Rebasing (1/4)
Rebasing (2/4)
Rebasing (3/4)
Auto-merging pipeline/core/gate.py
Auto-merging tests/test_gate.py
CONFLICT (content): Merge conflict in tests/test_gate.py
error: could not apply d07cc8f... fix(TICKET-147): a failed worktree_setup on base is an environment finding
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply d07cc8f... # fix(TICKET-147): a failed worktree_setup on base is an environment finding
Auto-merging README.md
Auto-merging pipeline/core/gate.py
Auto-merging tests/test_gate.py
CONFLICT (content): Merge conflict in tests/test_gate.py
Automatic merge failed; fix conflicts and then commit the result.

```

### 2026-10-01 14:14:40Z · human · note · by=chezzijr

**resumed** by chezzijr -> `merging`, reset []

### 2026-10-01 14:14:49Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
e --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/147


Rebasing (1/4)
Auto-merging tests/test_cli.py
CONFLICT (content): Merge conflict in tests/test_cli.py
error: could not apply ab9e041... test(TICKET-147): worktree_setup failure is ignored and a lockfile without it is not warned about
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply ab9e041... # test(TICKET-147): worktree_setup failure is ignored and a lockfile without it is not warned about
Auto-merging README.md
Auto-merging pipeline/cli/main.py
Auto-merging pipeline/templates/skills/file-ticket/SKILL.md
Auto-merging tests/test_cli.py
CONFLICT (content): Merge conflict in tests/test_cli.py
Automatic merge failed; fix conflicts and then commit the result.

```

### 2026-10-01 14:16:42Z · human · note · by=chezzijr

**resumed** by chezzijr -> `merging`, reset []

### 2026-10-01 14:16:44Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
eline merge --ff-only ticket/147


Rebasing (1/4)Auto-merging tests/test_cli.py
CONFLICT (content): Merge conflict in tests/test_cli.py
error: could not apply ab9e041... test(TICKET-147): worktree_setup failure is ignored and a lockfile without it is not warned about
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply ab9e041... # test(TICKET-147): worktree_setup failure is ignored and a lockfile without it is not warned about
Already up to date.
Updating 709bc2e..8016c05
Fast-forward
 README.md                                          |  7 +++-
 pipeline/cli/main.py                               | 22 ++++++++++--
 pipeline/core/gate.py                              | 10 +++++-
 pipeline/core/worktree.py                          | 36 +++++++++++++++++--
 pipeline/templates/skills/file-ticket/SKILL.md     |  5 +--
 pipeline/templates/skills/pipeline-config/SKILL.md | 10 ++++++
 tests/test_cli.py                                  | 39 ++++++++++++++++++--
 tests/test_gate.py                                 | 20 +++++++++--
 tests/test_worktree.py                             | 42 ++++++++++++++++++++++
 9 files changed, 177 insertions(+), 14 deletions(-)

```

### 2026-10-01 14:16:44Z · merging · decision

decision recorded as `DEC-147`
