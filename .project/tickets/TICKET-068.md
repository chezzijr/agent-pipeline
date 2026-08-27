---
id: TICKET-068
stage: done
class: feature
branch: ticket/068
test_file: tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run
files_declared:
- README.md
- pipeline/cli/main.py
- pipeline/core/config.py
- pipeline/daemon/registry.py
- pipeline/templates/skills/file-ticket/SKILL.md
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_cli.py
- tests/test_config.py
- tests/test_registry_worktree.py
counters:
  plan_validation_attempts: 3
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 16
  plan_files: 9
  no_result: 0
  plan_rejections: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 8c8a111c-69a2-4d81-b79f-46ff462fb8fa
  log: .project/logs/TICKET-068-review-8c8a111c.log
approved_by: chezzijr (via Claude Code, while away; reviewer also filed this ticket
  and rejected its earlier narrow scope -- audit in thread)
approved_at: '2026-08-27T17:58:50.678393+00:00'
---

## Summary

register accepts a project whose test commands do not work

`cmd_register()` is one line -- `registry.register(Path(args.path))`
(`pipeline/cli/main.py:305-306` on `main`). Nothing runs the project's test
commands, so a repo scaffolded with the packaged defaults registers clean and
every ticket filed against it dies at the gate.

This plan adds two checks to `register`, in this order, both skipped by
`--force`:

1. `test_suite` must be able to run. Refuse on exit 127, on exit 126, and on a
   non-zero exit whose output says nothing ran. A suite that runs and reports
   failures still registers.
2. `test_one` must exit non-zero when its selector matches no test. Probe it
   once with a bogus `<path>::<name>`.

Sixth plan (2026-08-28). Tier A passed it and Tier B passed it. The plan is
approved; `implementing` runs it as written, 16 steps and 9 files.

Both probes substitute with `format_test_cmd()`, never `str.format` (DEC-067).
`cmd_register()` calls a new `registry.check()` before it spawns anything, so
DEC-072's `PIPELINE_STAGE` refusal still fires first. Step 1 rebases onto
`main` (`c0e516d`); the branch is not a descendant of it today.

Two notes from Tier B, neither blocking. The digest's
`git diff --name-only main HEAD` claim needs the three-dot form to be true --
the rebase still replays one commit and one file, `tests/test_cli.py`, and
conflicts nowhere. And `suite_failure()` will refuse a multi-runner
`test_suite` that fails for real while one sub-run prints `collected 0 items`;
`--force` covers that case.

**Implemented.** All 16 plan steps done, TDD followed throughout, 6 commits
(`33e3a65`, `0d68de9`, `5572fd9`, `d61bbde`, `ad0c8bc`, `b1e2344`). All 9 named
acceptance-criterion tests pass, `git merge-base --is-ancestor main HEAD`
prints `0`, and `uv run --group dev pytest -q` reports `376 passed`, no
failures, no errors.

**Reviewed: PASS.** `review` re-ran every acceptance criterion on
`main...HEAD` (7 commits, 9 files) and reproduced all of them: `8 passed` for
the named node ids, `376 passed` for the full suite, `0` for the ancestry
check, and `--force` in `register --help`. Four minor findings, none blocking,
are in the `review` thread entry: a `<name>` -> `the name` doc drift in
`pipeline-config/SKILL.md:25`, a README sentence that claims one case more
than `suite_failure()` checks, no test pinning the `check()`-first order in
`cmd_register()`, and the note that `register` now runs the project's shell
commands.

## Reproduction

test: tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run
command: uv run --group dev pytest -q tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run

The test scaffolds a project whose `test_suite = "pipeline-068-nonexistent-command-xyz"`
(a shell cannot find it) and runs `pipeline register <dir>`. It asserts the
process exits non-zero and names the failing command in its output.

Actual output:

    AssertionError: registered /tmp/tmpn7w0imby

    assert 0 != 0
     +  where 0 = CompletedProcess(args=[..., 'register', '/tmp/tmpn7w0imby'],
         returncode=0, stdout='registered /tmp/tmpn7w0imby\n', stderr='').returncode

The `/tmp/tmpn7w0imby` above is one run's `tempfile.mkdtemp()` path, so it
cannot be the `expect:` string: Tier A checks `expect not in out` on every
later run, against a different path. The invariant part of the failure is that
`register` exited 0 after printing `registered`.

expect: returncode=0, stdout='registered

The test lives at `tests/test_cli.py:484-499` on the ticket branch (commit
`5db3b35`) and does not exist on `main`.

## Digest

Every line number below was taken against `main` at `c0e516d` on 2026-08-28,
which is what step 1 rebases onto. The ticket branch `ticket/068` (`5db3b35`)
is one commit, the reproduction test, and it is **not** a descendant of `main`.

- `git merge-tree --write-tree main HEAD` exits 0 and prints tree `6ed6930`, so the rebase in step 1 conflicts nowhere. `git diff --name-only main HEAD` lists only `tests/test_cli.py`.
- `pipeline/cli/main.py:305-306` -- `def cmd_register(args) -> None:` on line 305, and its whole body on line 306: `print(f"registered {registry.register(Path(args.path))}")`. Its parser row is `pipeline/cli/main.py:573`. Line 15 is `from pipeline.core.config import CONFIG_TEMPLATE, SKILLS_DIR, TICKET_TEMPLATE`. `PipelineError` is imported on line 13 and `main()` turns it into `die()`: exit 1, `error: <msg>` on stderr.
- `pipeline/core/config.py` -- `project_config(project)` is line 72 and reads `.project/pipeline.toml` from git HEAD, falling back to disk only when git has no copy (DEC-037). `re` (line 8) and `shlex` (line 9) are imported; line 17 is `from pipeline.core.worktree import head_file`. `format_test_cmd()` is line 101 and `def harness(` is line 114, so the new helpers go between them.
- `pipeline/core/config.py:101` -- `format_test_cmd(template, test)` substitutes `{test}`, `{path}` and `{name}` with a regex, each `shlex.quote`d, and leaves every other brace verbatim (DEC-067). It never raises. Measured 2026-08-28: `format_test_cmd("echo ${t##*::}", PROBE)` returns `echo ${t##*::}` unchanged, and `format_test_cmd("pytest -x {test}", PROBE)` returns `pytest -x pipeline_register_probe_no_such_file.py::pipeline_register_probe_no_such_test`.
- All four dispatcher call sites use it: `pipeline/core/gate.py:189`, `:261`, `:289`, and `pipeline/daemon/supervisor.py:725`, which is `child(format_test_cmd(cfg["test_suite"], t.test_file or ""), "suite")`. So `test_suite` is substituted too, with `""` when the ticket has no `test_file` -- which is what `suite_failure()` passes.
- `pipeline/core/worktree.py:25` -- `run_cmd(cmd, cwd) -> (returncode, (stdout + stderr)[-4000:])`, `shell=True`, `env=project_env()`. Every project command runs through it; never bare `subprocess`. `worktree.py` imports only stdlib, so `config.py` importing `run_cmd` adds no cycle.
- `pipeline/daemon/registry.py:83-108` -- `register()` makes four refusals before it writes: `PIPELINE_STAGE` set, no `.project/`, a linked git worktree, and a path holding a newline or `#` (DEC-072). Step 4 splits those four into `check()`, which `register()` then calls; no refusal changes.
- Exit codes measured on this machine 2026-08-28: a missing command exits 127 (`sh: line 1: pipeline-068-nonexistent-command-xyz: command not found`); a non-executable file exits 126 (`Permission denied`); `echo no tests ran; exit 5` exits 5; `exit 1` exits 1, which is a red suite and must still register.
- Measured 2026-08-28: `uv run --group dev pytest -x 'pipeline_register_probe_no_such_file.py::pipeline_register_probe_no_such_test'` exits **4** and prints `collected 0 items` and `no tests ran`. So the packaged default `test_one = "pytest -x {test}"` satisfies the new probe wherever pytest is installed, and exits 127 where it is not -- the case this ticket exists to catch.
- Gotcha, ordering: `cmd_register()` runs `suite_failure()` first and `selector_failure()` second. The reproduction test's project has `test_one = "true"` and a broken `test_suite`, and asserts the missing command name appears in the output. Reversed, the `test_one` message wins and the reproduction test fails.
- Gotcha, naming: the helpers are `suite_failure()` and `selector_failure()`, never `test_suite_failure()` or `test_one_failure()`; the config accessor is `project_test_cmd()`, never `test_command()`. pytest collects every module-level name matching `test*`, including one a test module imported. Probe run 2026-08-27 -- a module defining `def test_suite_failure(project)`, imported into a test file -- printed `ERROR test_x.py::test_suite_failure - fixture 'project' not found` and `1 passed, 1 error`.
- `tests/test_cli.py:22` -- `cli(project, *args, env=None)` runs `[sys.executable, "-m", "pipeline", "--project", str(project), *args]` with `cwd=ROOT` and `env={**os.environ, "XDG_STATE_HOME": ..., **(env or {})}`. `tests/conftest.py:19` is `os.environ.pop("PIPELINE_STAGE", None)`, so the spawned process never carries it (DEC-072). `--project` is read only by `proj(args)`, which `cmd_register()` never calls. `shutil` and `tempfile` are imported. The file is 486 lines on `main` and 499 with the reproduction test.
- `tests/test_config.py` is 77 lines on `main`; line 7 is `from pipeline.core.config import format_test_cmd, project_config, stage_extra`, and the two tests at lines 63-77 need `format_test_cmd`, so any rewrite of line 7 must keep it. Its existing projects come from `tests.helpers.git_project`; the new ones are plain `tempfile.mkdtemp()` directories, which are not git repos, so `project_config()` takes its disk fallback (DEC-037).
- `tests/test_registry_worktree.py` is 101 lines and sets `XDG_CONFIG_HOME` to a `mkdtemp()` before importing `registry` (lines 17-19), so its tests never touch the operator's registry.
- Gotcha: a CLI register test must pass `env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())}`, or it writes the operator's real `~/.config/pipeline/projects`.
- Gotcha: `.claude/skills/file-ticket/SKILL.md` and `.claude/skills/pipeline-config/SKILL.md` are symlinks into `pipeline/templates/skills/`. Edit the templates only.
- Doc anchors on `main`: `README.md:129` is the `pipeline register ~/code/myproject` line, its code fence ends at `README.md:136`, and lines 138-141 are the DEC-072 paragraph, so the new paragraph goes after line 141. `pipeline/templates/skills/file-ticket/SKILL.md:138` is the `- Not registered` bullet, and its arrow is the Unicode one, not `->`. `pipeline/templates/skills/pipeline-config/SKILL.md:25` is the `test_one` table row and reads "`<name>` appears in the output", line 29 reads `Two traps behind that table:`, the second trap bullet ends at line 35, and the expectations sentence is lines 68-70.
- `git rebase` is not in the guard's block rules (`pipeline/hooks/dangerous-commands.py:207-219` blocks only `push --force`, `push main`, `clean -f` and `worktree remove`), so step 1 runs from a write stage.
- No file in this plan is in `machine.FENCED`, so this ticket does not park at `awaiting-merge`.

## Decisions checked

Grepped `.project/decisions/` for: register, registry, test_one, test_suite,
config, validate, selector, matched nothing, zero-match, 127, exit code,
command not found, expect, format, substitut.

- DEC-067 (active) -- one substitution function, `format_test_cmd()`, for all four test-command call sites; only `{test}`, `{path}` and `{name}` are touched and every other brace passes through verbatim, because `str.format` raised `KeyError: 't##*'` on a literal `${t##*::}`. This plan complies: both probes substitute with `format_test_cmd()` and neither uses `str.format`. Step 9 pins it with an arm asserting `test_one = "echo ${t##*::} matched nothing; exit 1"` is judged, not rejected.
- DEC-072 (active) -- `register()` refuses a linked git worktree and refuses when `PIPELINE_STAGE` is set, and that guardrail must give a clear error. This plan complies: step 4 splits those refusals into `registry.check()` without changing one of them, and `cmd_register()` calls `check()` **before** it spawns a test command, so a stage running `pipeline register .` still gets `the registry is operator state` and no suite runs.
- DEC-037 (active) -- the dispatcher reads `.project/pipeline.toml` from HEAD, and from disk only when git has no copy. Both new checks call `project_config()` and inherit that; neither reads the working tree itself.
- DEC-011 (active) -- the registry file contract: one absolute path per line, rewritten with `write_atomic`, filtered by `projects()`. This plan changes no registry format and adds no socket op.
- DEC-061 (active) -- a dispatcher child is judged by its exit code, not by parsing its prose. Cited as precedent for the 126/127 rule and for the `test_one` probe, which reads only an exit code; `suite_failure()` departs from it by matching `NO_TESTS_RE`, and `## Decisions` says why.
- DEC-065 (active) -- Tier A verdicts and counters. Read and not relevant: this plan adds no stage and no `transition()` row.
- DEC-017 (active) -- `tests/test_gate.py` is copied onto a checkout of base, so it must not import a helper that does not exist there. Read and not relevant: this plan adds no import to `tests/test_gate.py` and does not touch `pipeline/core/gate.py`.
- TICKET-064 landed the gate half of the zero-match problem (commit `ae3b53b`, `gate()` refuses a base run that exits 0 without naming the node) and wrote **no** decision record, so this plan cites no id for it. TICKET-071 owns what remains there.

No record constrains what `register` checks before it writes its line.

## Plan

1. Rebase this worktree onto `main`: run `git fetch --all` then `git rebase main` in `/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068`, expect `Successfully rebased and updated refs/heads/ticket/068.`, then run `git merge-base --is-ancestor main HEAD; echo $?` and expect `0`; the only file this replays is `tests/test_cli.py` and `git merge-tree --write-tree main HEAD` already exited 0, so no conflict is expected -- if one appears, stop and report it in `## Thread` rather than resolving it.
2. Append this test to the end of `tests/test_registry_worktree.py`:

        def test_check_refuses_before_the_caller_spawns_anything():
            """`cmd_register()` calls `check()` before it runs the project's test
            commands, so a stage's `pipeline register .` gets the DEC-072 error
            instead of a suite run first."""
            d, sh = git_project()
            r = sh("git add -A .project && git commit -qm 'add .project'")
            assert r.returncode == 0, r.stderr

            os.environ["PIPELINE_STAGE"] = "implementing"
            try:
                registry.check(d)
                assert False, "check() ran under PIPELINE_STAGE"
            except PipelineError as e:
                assert "operator state" in str(e), e
            finally:
                del os.environ["PIPELINE_STAGE"]

            assert d not in registry.projects()
            assert registry.check(d) == d

3. Run `uv run --group dev pytest -q tests/test_registry_worktree.py` and watch it fail with `AttributeError: module 'pipeline.daemon.registry' has no attribute 'check'`.
4. Split `register()` in `pipeline/daemon/registry.py:83-108` into `check()` and `register()`, changing no refusal: put `check()` directly above `register()`, move lines 91-104 into it verbatim (the `PIPELINE_STAGE` raise, the `.project/` raise, the `is_worktree()` raise and the newline/`#` raise, in that order) with `return project` at the end, and make `register()`'s body `project = check(project)` followed by the three surviving lines (`if project in projects(): return project`, `_write(_raw() + [str(project)])`, `return project`); `check()` gets the docstring "The resolved path, or `PipelineError`: every refusal `register()` makes before it writes. Split out so `cmd_register()` can refuse before it spawns the project's test commands -- a stage running `pipeline register .` must still get the `PIPELINE_STAGE` error (DEC-072), not a suite run first.", and `register()` keeps its existing docstring unchanged. Then run `uv run --group dev pytest -q tests/test_registry_worktree.py tests/test_daemon.py`, expect no failures, and commit `pipeline/daemon/registry.py` and `tests/test_registry_worktree.py` as `refactor(TICKET-068): split register()'s refusals into registry.check()`.
5. Add this helper and this test at the end of `tests/test_config.py`, and make line 7 of `tests/test_config.py` read `from pipeline.core.config import format_test_cmd, project_config, stage_extra, suite_failure`:

        def _probe_project(test_one="false", test_suite="true"):
            """A throwaway project. It is not a git repo, so `project_config()`
            takes its disk fallback (DEC-037)."""
            d = Path(tempfile.mkdtemp())
            (d / ".project").mkdir()
            (d / ".project" / "pipeline.toml").write_text(
                'test_one = "%s"\ntest_suite = "%s"\n'
                'test_suite_without_new = "true"\n' % (test_one, test_suite))
            return d


        def test_suite_failure_tells_a_broken_command_from_a_red_suite():
            """A suite that runs and fails is the normal state of a project with an
            open bug and must register. Only a suite that cannot run is refused."""
            missing = suite_failure(_probe_project(test_suite="pipeline-068-nonexistent-command-xyz"))
            assert missing and "pipeline-068-nonexistent-command-xyz" in missing
            assert "exit 127" in missing
            nothing = suite_failure(_probe_project(test_suite="echo no tests ran; exit 5"))
            assert nothing and "ran no tests" in nothing
            assert suite_failure(_probe_project(test_suite="echo 1 failed; exit 1")) is None
            assert suite_failure(_probe_project(test_suite="true")) is None
            # DEC-067: `test_suite` has never been `str.format`ed, so a literal
            # brace must reach the shell instead of raising
            assert suite_failure(_probe_project(test_suite="echo ${t##*::} ok")) is None

6. Run `uv run --group dev pytest -q tests/test_config.py` and watch it fail with `ImportError: cannot import name 'suite_failure' from 'pipeline.core.config'`.
7. Implement `suite_failure()` in `pipeline/core/config.py`: make line 17 read `from pipeline.core.worktree import head_file, run_cmd`, and put this directly below `format_test_cmd()` (which ends at line 111), above `def harness(`:

        # `suite_failure`, not `test_suite_failure`, and `project_test_cmd`, not
        # `test_command`: pytest collects every module-level name matching
        # `test*`, including one a test module imported, and would run these as
        # tests it cannot supply `project` for -- `fixture 'project' not found`.
        SHELL_CANNOT_RUN = {126: "the shell found it but could not execute it",
                            127: "the shell could not find it"}
        # `pytest` exits 5 and prints this when it collected nothing -- what the
        # packaged default `test_suite = "pytest"` does in a repo that is not a
        # Python one. A collection error prints it too, and exits 2.
        NO_TESTS_RE = re.compile(r"no tests ran|no tests were run|collected 0 items")


        def project_test_cmd(project: Path, key: str) -> str:
            """The project's `key` command. Raises `PipelineError` when the config
            has no usable one; `project_config()` raises before that for a project
            with no config at all, naming `pipeline init`."""
            cmd = project_config(project).get(key)
            if not isinstance(cmd, str) or not cmd.strip():
                raise PipelineError(f"{project}: `.project/pipeline.toml` has no `{key}` -- "
                                    f"the dispatcher would have no command to run")
            return cmd


        def suite_failure(project: Path) -> str | None:
            """`None` when the project's `test_suite` can run; the refusal message
            when it cannot run at all.

            A suite that ran and reported failures returns `None`: that is the
            normal state of a project with an open bug, and it is what a ticket is
            filed against. Only two things count as cannot-run -- the shell's own
            126 and 127, and a non-zero exit whose output says nothing ran.

            Substituted with `format_test_cmd(cmd, "")`, matching
            `supervisor.py`'s `t.test_file or ""` for a ticket with no test file.
            """
            cmd = format_test_cmd(project_test_cmd(project, "test_suite"), "")
            code, out = run_cmd(cmd, project)
            reason = SHELL_CANNOT_RUN.get(code)
            if reason is None and code != 0 and NO_TESTS_RE.search(out):
                reason = "it ran no tests"
            if reason is None:
                return None
            return (f"{project}: `test_suite` cannot run -- `{cmd}`: {reason} "
                    f"(exit {code})\n{out.strip()[-1200:]}\n"
                    f"fix `test_suite` in {project}/.project/pipeline.toml, or "
                    f"`pipeline register --force {project}` to register anyway")

8. Run `uv run --group dev pytest -q tests/test_config.py`, expect `5 passed` (the 4 existing tests plus the new one) and no line reading `ERROR`, then commit `pipeline/core/config.py` and `tests/test_config.py` as `feat(TICKET-068): tell a test_suite that cannot run from one that fails`.
9. Add this test at the end of `tests/test_config.py`, and make line 7 of `tests/test_config.py` read `from pipeline.core.config import format_test_cmd, project_config, selector_failure, stage_extra, suite_failure`:

        def test_selector_failure_wants_test_one_to_fail_when_it_matches_nothing():
            """`gate()` cannot tell `the test passed` from `the selector matched
            nothing` by reading output: a runner may name a test only when it
            fails. The project's own command knows its runner and can tell."""
            passes = selector_failure(_probe_project(test_one="true"))
            assert passes and "exited 0" in passes
            assert "pipeline_register_probe_no_such_test" in passes
            missing = selector_failure(_probe_project(test_one="pipeline-068-nonexistent-command-xyz"))
            assert missing and "exit 127" in missing
            assert selector_failure(_probe_project(test_one="false")) is None
            assert selector_failure(_probe_project(test_one="echo no test matched {test}; exit 1")) is None
            # DEC-067: `format_test_cmd()` leaves every other brace verbatim, so
            # this command is judged by its exit code. Under `str.format` it would
            # raise `KeyError: 't##*'` and this arm would error instead of pass.
            assert selector_failure(_probe_project(test_one="echo ${t##*::} matched nothing; exit 1")) is None

10. Run `uv run --group dev pytest -q tests/test_config.py` and watch it fail with `ImportError: cannot import name 'selector_failure' from 'pipeline.core.config'`.
11. Implement `selector_failure()` in `pipeline/core/config.py`, directly below `suite_failure()` and above `def harness(`:

        # The selector `selector_failure()` probes `test_one` with: a path and a
        # name no project has. A runner that reports success for this cannot tell
        # `gate()` that a real selector matched nothing either.
        PROBE_TEST = ("pipeline_register_probe_no_such_file.py"
                      "::pipeline_register_probe_no_such_test")


        def selector_failure(project: Path) -> str | None:
            """`None` when the project's `test_one` exits non-zero for a selector
            that matches no test; the refusal message when it does not.

            `gate()` cannot tell `the test passed` from `the selector matched
            nothing` by reading output -- `pytest` prints `1 passed` and never the
            node name. The project's command knows its own runner and can tell, so
            the requirement is checked here, once, at `register`.

            Substituted with `format_test_cmd()`, the one substitution the four
            dispatcher call sites use (DEC-067). It quotes `{test}`, `{path}` and
            `{name}` itself and never raises on any other brace.
            """
            probe = format_test_cmd(project_test_cmd(project, "test_one"), PROBE_TEST)
            code, out = run_cmd(probe, project)
            reason = SHELL_CANNOT_RUN.get(code)
            if reason is None and code == 0:
                reason = "it exited 0 -- `gate()` would read that as `the test PASSES`"
            if reason is None:
                return None
            return (f"{project}: `test_one` must exit non-zero when its selector "
                    f"matches no test -- probed with `{PROBE_TEST}`, ran `{probe}`: "
                    f"{reason} (exit {code})\n{out.strip()[-1200:]}\n"
                    f"make `test_one` fail when its filter matches nothing (the "
                    f"`pipeline-config` skill shows how), or "
                    f"`pipeline register --force {project}` to register anyway")

12. Run `uv run --group dev pytest -q tests/test_config.py`, expect `6 passed` and no line reading `ERROR`, then commit `pipeline/core/config.py` and `tests/test_config.py` as `feat(TICKET-068): require test_one to fail on a selector that matches nothing`.
13. Wire both checks into `pipeline/cli/main.py`: make line 15 read `from pipeline.core.config import CONFIG_TEMPLATE, SKILLS_DIR, TICKET_TEMPLATE, selector_failure, suite_failure`, make the `register` parser row at `pipeline/cli/main.py:573` read `p = sub.add_parser("register"); p.add_argument("path", nargs="?", default="."); p.add_argument("--force", action="store_true", help="register without running the project's test commands"); p.set_defaults(fn=cmd_register)`, and replace `cmd_register()` at `pipeline/cli/main.py:305-306` with the body below; then run `uv run --group dev pytest -q tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run`, expect `1 passed`, and commit `pipeline/cli/main.py` as `fix(TICKET-068): check the project's test commands before registering it`:

        def cmd_register(args) -> None:
            # a project whose test commands are wrong registers clean otherwise,
            # and every ticket filed against it then dies at the gate reporting a
            # different symptom of the one broken config
            #
            # `check()` first: it holds DEC-072's `PIPELINE_STAGE` and worktree
            # refusals, and a stage running `pipeline register .` must get that
            # error rather than a run of the project's suite
            path = registry.check(Path(args.path))
            if args.force:
                print("--force: registering without checking this project's test commands")
            else:
                print("checking this project's test commands (--force skips this)")
                # `test_suite` first: the reproduction test asserts its message
                # wins over `test_one`'s, and `or` skips the second command once
                # the first has already refused
                problem = suite_failure(path) or selector_failure(path)
                if problem:
                    raise PipelineError(problem)
            print(f"registered {registry.register(path)}")

14. Append this helper and these four tests to the end of `tests/test_cli.py`, run `uv run --group dev pytest -q tests/test_cli.py`, expect every test to pass, and commit `tests/test_cli.py` as `test(TICKET-068): register keeps a red suite, refuses a blind test_one, honours --force`:

        def register_project(test_one="false", test_suite="true", config=True):
            """A throwaway project for `pipeline register`. Not named `test_*`:
            pytest would collect it."""
            d = Path(tempfile.mkdtemp()).resolve()
            (d / ".project").mkdir()
            if config:
                (d / ".project" / "pipeline.toml").write_text(
                    'test_one = "%s"\ntest_suite = "%s"\n'
                    'test_suite_without_new = "true"\n' % (test_one, test_suite))
            return d


        def test_register_accepts_a_project_whose_test_suite_runs_and_fails():
            """A red suite is the normal state of a project with an open bug."""
            d = register_project(test_suite="echo 1 failed; exit 1")
            r = cli(d, "register", str(d), env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
            assert r.returncode == 0, r.stdout + r.stderr
            assert f"registered {d}" in r.stdout
            shutil.rmtree(d, ignore_errors=True)


        def test_register_refuses_a_test_one_that_exits_0_on_a_selector_matching_nothing():
            """`gate()` would read that exit 0 as `the reproduction PASSES`."""
            d = register_project(test_one="true")
            r = cli(d, "register", str(d), env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
            assert r.returncode != 0, r.stdout + r.stderr
            assert "test_one" in r.stdout + r.stderr
            assert "pipeline_register_probe_no_such_test" in r.stdout + r.stderr
            shutil.rmtree(d, ignore_errors=True)


        def test_register_refuses_a_project_directory_with_no_pipeline_toml():
            """`register` accepted a bare `.project/` before this ticket. Both
            checks read the config, so it refuses one now -- intended, pinned here,
            and `--force` still registers it."""
            d = register_project(config=False)
            r = cli(d, "register", str(d), env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
            assert r.returncode != 0, r.stdout + r.stderr
            assert "pipeline init" in r.stdout + r.stderr
            forced = cli(d, "register", "--force", str(d),
                         env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
            assert forced.returncode == 0, forced.stdout + forced.stderr
            shutil.rmtree(d, ignore_errors=True)


        def test_register_force_skips_both_test_command_checks():
            """`--force` is what a slow suite wants: register without running it."""
            d = register_project(test_one="true",
                                 test_suite="pipeline-068-nonexistent-command-xyz")
            r = cli(d, "register", "--force", str(d),
                    env={"XDG_CONFIG_HOME": str(tempfile.mkdtemp())})
            assert r.returncode == 0, r.stdout + r.stderr
            assert f"registered {d}" in r.stdout
            shutil.rmtree(d, ignore_errors=True)

15. Document the two checks in three files, keeping each file's existing arrow characters and table pipes: (a) `README.md` line 129 becomes `pipeline register ~/code/myproject   # runs its test_suite and probes test_one first`, and a new paragraph goes after the DEC-072 paragraph that ends at `README.md:141`, reading "`register` also refuses a project whose test commands are wrong, because every ticket filed against it would die at the gate instead. `test_suite` must run at all: the shell must find the command, and the runner must run something. `test_one` must exit non-zero when its selector matches no test, which is the one thing `gate()` cannot tell from a runner's output. A suite that runs and reports failures still registers. `pipeline register --force <path>` skips both checks, which is what a slow suite wants."; (b) `pipeline/templates/skills/file-ticket/SKILL.md` line 138 gains the sentence "It runs this project's `test_suite` once and probes `test_one` with a selector that matches nothing, then refuses when the suite cannot run at all or when `test_one` exits 0 on that probe; fix `.project/pipeline.toml` (the `pipeline-config` skill teaches how) or pass `--force` for a slow suite."; (c) in `pipeline/templates/skills/pipeline-config/SKILL.md` line 25 becomes the table row `| test_one | run **only** that one test | exits non-zero **and** the name appears in the output; exits non-zero when the selector matches NO test |` with each of `test_one` and the name in backticks as they are today, line 29 becomes `Three traps behind that table:`, a third bullet goes in after line 35 reading "- A selector that matches **no** test must still exit non-zero. A runner that treats the selector as a filter may exit 0 and print `0 filtered out`, and the gate would read that as `the reproduction PASSES`. Wrap the runner when it cannot -- a `run-test.sh` that prints `FILTER MATCHED NO TEST -- refusing to report success` and exits 1. `pipeline register` probes exactly this and refuses a config that fails it.", and the expectations sentence ending at line 70 gains "Then run `test_one` once more with a name no test has: it must be non-zero there too."
16. Run `uv run --group dev pytest -q` and expect no failures and no errors, then commit `README.md`, `pipeline/templates/skills/file-ticket/SKILL.md` and `pipeline/templates/skills/pipeline-config/SKILL.md` as `docs(TICKET-068): register checks test_suite and test_one, and --force skips both`.

## Acceptance criteria

- `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` passes: the process exits non-zero and its output names `pipeline-068-nonexistent-command-xyz`.
- `tests/test_cli.py::test_register_refuses_a_test_one_that_exits_0_on_a_selector_matching_nothing` passes: a project whose `test_suite` is `true` and whose `test_one` is `true` is refused, and the output names `pipeline_register_probe_no_such_test`.
- `tests/test_cli.py::test_register_accepts_a_project_whose_test_suite_runs_and_fails` passes: a project whose `test_suite` is `echo 1 failed; exit 1` registers, exit 0, printing `registered <dir>`.
- `tests/test_cli.py::test_register_refuses_a_project_directory_with_no_pipeline_toml` passes: a bare `.project/` is refused with `pipeline init` in the message, and registers under `--force`.
- `tests/test_cli.py::test_register_force_skips_both_test_command_checks` passes: a project with an unfindable `test_suite` and a `test_one` of `true` registers under `--force`.
- `tests/test_config.py::test_suite_failure_tells_a_broken_command_from_a_red_suite` passes all five arms: the unfindable command and `echo no tests ran; exit 5` return a message; `echo 1 failed; exit 1`, `true` and `echo ${t##*::} ok` return `None`.
- `tests/test_config.py::test_selector_failure_wants_test_one_to_fail_when_it_matches_nothing` passes all five arms: `true` (exit 0) and the unfindable command (exit 127) return a message; `false`, `echo no test matched {test}; exit 1` and `echo ${t##*::} matched nothing; exit 1` return `None`. The last arm errors with `KeyError: 't##*'` if `str.format` is used instead of `format_test_cmd()` (DEC-067).
- `tests/test_registry_worktree.py::test_check_refuses_before_the_caller_spawns_anything` passes: `registry.check()` raises `PipelineError` naming `operator state` under `PIPELINE_STAGE`, registers nothing, and returns the resolved path once the variable is gone (DEC-072).
- `git merge-base --is-ancestor main HEAD; echo $?` prints `0`, so the branch carries `format_test_cmd()` and the DEC-072 refusals that `tests/test_registry_worktree.py::test_check_refuses_before_the_caller_spawns_anything` and `tests/test_config.py::test_selector_failure_wants_test_one_to_fail_when_it_matches_nothing` need.
- `uv run --group dev pytest -q` reports no failures and no errors. In particular it reports no `ERROR ...::suite_failure`, no `ERROR ...::selector_failure` and no `ERROR ...::project_test_cmd`, which is what a helper named `test*` would produce.

## Decisions

**`register` refuses only a `test_suite` that cannot run, never one that
fails.** Three cases refuse: shell exit 127 (command not found), 126 (found,
not executable), and a non-zero exit whose output matches `NO_TESTS_RE` (`no
tests ran`, `no tests were run`, `collected 0 items` -- `pytest`'s exit 5 and
its collection error). Every other non-zero exit registers. Widening this to
"any non-zero exit" would refuse exactly the projects this tool exists for: one
with an open bug has a red suite.

**`test_one` must exit non-zero when its selector matches no test, and that is
checked at `register`, not inferred in `gate()`.** `gate()` cannot tell "the
test passed" from "the selector matched nothing" by reading output: a runner
may name a test only when it fails -- `pytest` prints `1 passed` and never the
node name. The project's command knows its own runner and can tell, so the
durable contract is a requirement on `test_one`, checked once. The fix a
project makes is a wrapper: `run-test.sh: FILTER MATCHED NO TEST -- refusing to
report success`, exit 1. TICKET-071 owns the gate half; this ticket does not
touch `pipeline/core/gate.py`.

**Both probes substitute with `format_test_cmd()`, never `str.format`
(DEC-067).** `selector_failure()` runs `format_test_cmd(cmd, PROBE_TEST)` and
`suite_failure()` runs `format_test_cmd(cmd, "")`, which is exactly what
`pipeline/daemon/supervisor.py:725` does for a ticket with no `test_file`. A
probe that substituted differently from the dispatcher would judge a command
the dispatcher never runs. `format_test_cmd()` quotes `{test}`, `{path}` and
`{name}` itself and never raises, so neither helper catches an exception and
neither refuses a command for holding a literal brace -- `${t##*::}` is a valid
`test_one`, and an arm of each unit test pins that.

**The probe selector is bogus in both halves --
`pipeline_register_probe_no_such_file.py::pipeline_register_probe_no_such_test`.**
`register` knows no real test in the project, so it cannot probe a real path
with a bogus name. The limit that follows is real and accepted: a runner that
exits non-zero only because the *file* is missing passes this probe and could
still exit 0 for a real file with zero matches. Measured 2026-08-28 -- `pytest`
exits 4 on the probe and 5 on a real file with no matching name, so both are
caught for pytest. Tightening this needs a real test path, which `register`
does not have.

**Order: `registry.check()`, then `suite_failure()`, then
`selector_failure()`.** `check()` first because it holds DEC-072's
`PIPELINE_STAGE` and worktree refusals, and a stage exploring
`pipeline register .` must get that error rather than a run of the project's
whole suite before it. `suite_failure()` before `selector_failure()` because
the reproduction test's project has a broken `test_suite` and
`test_one = "true"`, and asserts the missing command's name reaches the output;
reversed, the `test_one` message wins and that test fails. The `or` also keeps
`register` from spawning the second command once the first has refused.

**`registry.check()` exists so those two orderings can both hold, and it
changes no refusal.** It is `register()`'s four pre-write refusals, moved
verbatim; `register()` calls it and behaves as before, so the tests that call
`registry.register()` in-process are untouched. Do not inline it back into
`register()`: `cmd_register()` would then have to duplicate the DEC-072 checks
or spawn the project's suite before making them.

**`register` refusing a `.project/` that holds no `pipeline.toml` is
intended.** Both checks read the config through `project_config()`, which
raises `PipelineError` when git has no copy and disk has no file: `no
<path>/.project/pipeline.toml -- run pipeline init <path> first`. Before this
ticket `register` accepted that directory, and every ticket filed there failed
later with the same message. `--force` still registers it.

**A helper that a test module imports must not be named `test*`.**
`suite_failure()` judges `test_suite`, `selector_failure()` judges `test_one`,
and `project_test_cmd()` reads either, so the obvious names are
`test_suite_failure()`, `test_one_failure()` and `test_command()`. pytest
collects every module-level name matching `test*`, an imported one included, so
those names turn the helpers into tests whose `project` argument pytest tries
to resolve as a fixture: `ERROR tests/test_config.py::test_suite_failure -
fixture 'project' not found`. Renaming them back reddens the suite without
touching a line of logic.

**The checks live in `cmd_register()`, not in `registry.register()`.**
`registry.register()` is the library function DEC-011 froze, ten tests call it
in-process, and the daemon never calls it. Moving the checks down there makes
every one of those tests spawn a shell.

**They read the config through `project_config()`, so they judge the HEAD copy
(DEC-037).** An uncommitted fix to `test_suite` is inert at `register` exactly
as it is at `verifying`. That is the point: `register` must check the commands
the dispatcher will actually run.

**No timeout on either check.** A slow suite blocks `register`, and `--force`
is the answer, named in both refusal messages. Adding a timeout to `run_cmd()`
would change every project command in the repo for one caller's benefit.

**An `expect:` line must survive a second run.** Tier A checks `expect not in
out` every time it gates, so a `tempfile.mkdtemp()` path captured once can
never match again. Record the invariant part of the failure -- here
`returncode=0, stdout='registered` -- not the run.

## Rollback

Revert the commits from steps 4, 8, 12, 13, 14 and 16 with `git revert`.
`register` returns to appending the path unconditionally, `registry.check()`
folds back into `registry.register()`, and `pipeline register --force` becomes
an argparse error (exit 2). Nothing persists across the revert: no registry
format change, no schema change, and a project registered under `--force` is
indistinguishable from one registered before this ticket.

## Thread

### 2026-08-27 08:59:34Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-27 · triage

Confirmed: `cmd_register()` (`pipeline/cli/main.py:292-293`) is one line,
`registry.register(Path(args.path))`. No test command runs before
registering, so any project registers regardless of whether `test_suite` can
run at all.

Added a failing test,
`tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run`,
committed on this branch (`5db3b35`). It scaffolds a project whose
`test_suite` names a command the shell cannot find, runs `pipeline register`,
and asserts non-zero exit naming the command. It fails today with exit 0 and
`registered <dir>`. See `## Reproduction`.

This needs a design decision (how to detect "cannot run at all" vs. "ran and
failed", the `--force` escape hatch, and the message format), so it is not a
`chore`.

### 2026-08-27 09:25:48Z · triage · session · session=4d6c4753-1ada-4d5c-9238-41db2149f1dc

`triage` ran as session `4d6c4753-1ada-4d5c-9238-41db2149f1dc`
- replay: `claude --resume 4d6c4753-1ada-4d5c-9238-41db2149f1dc`
- log: `.project/logs/TICKET-068-triage-4d6c4753.log`

### 2026-08-27 09:25:48Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Confirmed cmd_register() never runs test_suite; added failing test tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run, committed 5db3b35.

### 2026-08-27 09:30:12Z · planning · note

`planning` was interrupted; lease released

### 2026-08-27 · planning

Plan written: 12 steps, 6 files. `register` runs `test_suite` once through a
new `test_suite_failure()` in `pipeline/core/config.py` and refuses on three
cases only. Measured on `/bin/sh` today, quoted verbatim:

    'pipeline-068-nonexistent-command-xyz' 127 '/bin/sh: line 1: pipeline-068-nonexistent-command-xyz: command not found'
    '/etc/hostname' 126 '/bin/sh: line 1: /etc/hostname: Permission denied'
    'exit 1' 1 ''

and `pytest` in an empty directory printed `no tests ran` and exited 5. So 127,
126, and a non-zero exit whose output says nothing ran are the refusals; every
other non-zero exit registers, which keeps the ticket's "a red suite must still
register" rule.

Scope: `test_suite` only. The ticket names it, and `test_suite_without_new`
takes a `{test}` substitution `register` has no ticket to supply.

Two questions I settled by reading rather than asking. The check goes in
`cmd_register()`, not `registry.register()`, because 10 tests call the library
function in-process (`tests/test_daemon.py`, `tests/test_dispatch.py`). It
reads the config through `project_config()`, so it judges the HEAD copy the
dispatcher runs (DEC-037).

### 2026-08-27 15:42:58Z · planning · session · session=ec033e0b-4655-46b3-91ca-27fc7f63710e

`planning` ran as session `ec033e0b-4655-46b3-91ca-27fc7f63710e`
- replay: `claude --resume ec033e0b-4655-46b3-91ca-27fc7f63710e`
- log: `.project/logs/TICKET-068-planning-ec033e0b.log`

### 2026-08-27 15:42:58Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: register runs test_suite via a new test_suite_failure() in pipeline/core/config.py, refuses on exit 127/126 or a non-zero exit that ran nothing, and --force skips the check. 12 steps, 6 files.

### 2026-08-27 15:43:17Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails, but its output does not mention the expected string 'registered /tmp/tmpn7w0imby'
```
r[39;49;00m[33m"[39;49;00m, [96mstr[39;49;00m(d), env={[33m"[39;49;00m[33mXDG_CONFIG_HOME[39;49;00m[33m"[39;49;00m: [96mstr[39;49;00m(tempfile.mkdtemp())})[90m[39;49;00m
>       [94massert[39;49;00m r.returncode != [94m0[39;49;00m, r.stdout + r.stderr[90m[39;49;00m
[1m[31mE       AssertionError: registered /tmp/tmp_7d0j2x0[0m
[1m[31mE         [0m
[1m[31mE       assert 0 != 0[0m
[1m[31mE        +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068/.venv/bin/python', '-m', 'pipeline', ..., '/tmp/tmp_7d0j2x0', 'register', '/tmp/tmp_7d0j2x0'], returncode=0, stdout='registered /tmp/tmp_7d0j2x0\n', stderr='').returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmp_7d0j2x0
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m

```

### 2026-08-27 15:43:17Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails, but its output does not mention the expected string 'registered /tmp/tmpn7w0imby'
*-- identical output, already quoted in the `## Thread` entry `2026-08-27 15:43:17Z · plan-validation · gate · verdict=FAIL` --*

### 2026-08-27 · planning

Second plan. The gate rejected the first one for the ticket's `expect:` line,
not for a step. `## Reproduction` recorded `expect: registered /tmp/tmpn7w0imby`,
a `tempfile.mkdtemp()` path from the triage run; today the same test prints
`/tmp/tmpqxjvy40b`. Tier A checks `expect not in out`, so that line could never
match again. This stage rewrote it to `expect: returncode=0, stdout='registered`,
which occurs once in today's raw output and still says register exited 0 after
printing `registered`. No plan step covers this: the gate reads the ticket
before any step runs, so the fix had to be on disk now.

Second defect, found re-reading the rejected plan: it named the helper
`test_suite_failure()` and had `tests/test_config.py` import it. pytest collects
an imported `test*` name. Probe:

    ERROR test_x.py::test_suite_failure - fixture 'project' not found
    1 passed, 1 error

Step 4 would have reported `4 passed, 1 error`, not `5 passed`. The helper is
`suite_failure()` everywhere now, and `## Decisions` records why.

The rest stands: 12 steps, 6 files, `test_suite` only, refuse on exit 127, 126,
or a non-zero exit that ran nothing.

### 2026-08-27 15:51:50Z · planning · session · session=deecbb49-804b-467d-9abc-983ba2f650ac

`planning` ran as session `deecbb49-804b-467d-9abc-983ba2f650ac`
- replay: `claude --resume deecbb49-804b-467d-9abc-983ba2f650ac`
- log: `.project/logs/TICKET-068-planning-deecbb49.log`

### 2026-08-27 15:51:50Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Second plan: fixed the unmatchable expect: line (a mkdtemp path) that failed the gate, renamed the helper to suite_failure() because pytest collects an imported test* name, 12 steps, 6 files.

### 2026-08-27 · plan-validation

**Tier B: PASS.** Eight items, each verified against the code. This entry sits
above the Tier A gate entry that precedes it in time, not at the end of the
thread: the last entry ends with a fence of raw terminal escapes I cannot
reproduce as an edit anchor, and the guard blocks every Bash write path from a
read-only stage -- `>>` is "shell redirection into a file", `tee` is "not on
the read-only allowlist".

1. Root cause: `cmd_register()` writes the registry line without ever running
   the project's `test_suite`, so a config naming a command the shell cannot
   find registers as valid, and every ticket filed against it then dies at the
   gate. The plan runs that command at register time, through the same
   `project_config()` and `run_cmd()` the dispatcher uses. It fixes the cause,
   not the assertion.
2. Decisions: DEC-037 holds -- `project_config()` reads `head_file()` and falls
   back to disk (`pipeline/core/config.py:89-95`), so the check judges HEAD.
   DEC-011 holds -- `registry.register()` (`pipeline/daemon/registry.py:60`)
   is untouched. DEC-061 does not bind. The plan departs from exit-code-only
   by matching `NO_TESTS_RE`, and `## Decisions` states why.
3. Scope: steps 1-9 trace to criteria. Steps 10-12 (README, SKILL.md) trace to
   the `CLAUDE.md` rule that a CLI change is unfinished until the skill agrees.
4. Criteria falsifiable: an implementation that refuses every non-zero exit
   fails the `echo 1 failed; exit 1` arm and the accept test. An unwired
   `--force` exits 2.
5. No research left: verified `cmd_register` at `pipeline/cli/main.py:292`, the
   `register` parser row at 560, the config import at line 15, line 7 of
   `tests/test_config.py`, and `shutil` plus `tempfile` already imported in
   `tests/test_cli.py`.
6. Riskiest step is 5: `register` spawns an arbitrary project command with no
   timeout. Fallback stated -- `--force`, named in the refusal message itself.
7. Regression surface: 12 in-process `registry.register()` calls
   (`tests/test_daemon.py`, `test_dispatch.py:855`, `test_harness.py:479`,
   `tests/conftest.py`) keep their path. `tests/test_cli.py:496` is the only
   CLI register test, so no existing test starts spawning a project suite.
8. Blast radius: class `feature`, 6 files, 2 of them source. Proportionate.

One observation, not a defect. `suite_failure()` returns `None` for a missing
`.project/` directory, but it calls `project_config()`, which raises
`PipelineError` when `.project/pipeline.toml` is absent. `register` then dies
where it used to register. No test pins that, and `pipeline init` always writes
the file.

I could not measure exit 127 myself. The guard refused the command --
"`pipeline-068-nonexistent-command-xyz` is not on the read-only allowlist" --
and refused `python3 -c`. Step 7 proves it end-to-end.

### 2026-08-27 15:52:09Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails as required
```
r[39;49;00m[33m"[39;49;00m, [96mstr[39;49;00m(d), env={[33m"[39;49;00m[33mXDG_CONFIG_HOME[39;49;00m[33m"[39;49;00m: [96mstr[39;49;00m(tempfile.mkdtemp())})[90m[39;49;00m
>       [94massert[39;49;00m r.returncode != [94m0[39;49;00m, r.stdout + r.stderr[90m[39;49;00m
[1m[31mE       AssertionError: registered /tmp/tmpperslbjm[0m
[1m[31mE         [0m
[1m[31mE       assert 0 != 0[0m
[1m[31mE        +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068/.venv/bin/python', '-m', 'pipeline', ..., '/tmp/tmpperslbjm', 'register', '/tmp/tmpperslbjm'], returncode=0, stdout='registered /tmp/tmpperslbjm\n', stderr='').returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmpperslbjm
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m

```
- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails on base `main` too -- the bug is not already fixed upstream
```
returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmprczl6gsa
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.23s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-37knzk0k/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-37knzk0k/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 15:59:17Z · plan-validation · session · session=1f9f8b7a-09a9-407e-950e-ebbb9314380b

`plan-validation` ran as session `1f9f8b7a-09a9-407e-950e-ebbb9314380b`
- replay: `claude --resume 1f9f8b7a-09a9-407e-950e-ebbb9314380b`
- log: `.project/logs/TICKET-068-plan-validation-1f9f8b7a.log`

### 2026-08-27 15:59:17Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B PASS: all eight items verified against the code; one noted side effect (project_config() raises when .project/pipeline.toml is absent, so register now refuses that case)

### 2026-08-27 16:05:34Z · human · rejection

[chezzijr's decision, entered via Claude Code] Widen the scope by one assertion. Also assert that test_one exits non-zero when its selector matches NO test -- run it once at register with a deliberately bogus name and require a non-zero exit.

Why: gate() cannot distinguish 'the test passed' from 'the selector matched nothing' by reading output, because a runner may name a test only when it fails (pytest prints '1 passed' and never the node name; measured on tests/test_gate.py::test_gate_passes_a_complete_ticket, 0 occurrences). The project's own command CAN tell, because it knows its runner. So the durable contract is a requirement on test_one, checked once at register, rather than an inference in the gate. A real wrapper doing exactly this: 'run-test.sh: FILTER MATCHED NO TEST -- refusing to report success', exit 1, where the same input previously exited 0 and a gate read it as 'the repro PASSES'.

Everything else in the plan stands and needs no rework. Keep the test_suite smoke run, keep the --force escape hatch, and keep the noted side effect (project_config() raising when .project/pipeline.toml is absent) -- but say in the plan whether refusing that case is intended, because register currently only checks that .project/ exists.

This does not widen into gate() -- TICKET-071 owns that half.

### 2026-08-27 · planning

Third plan. The human rejected the second one to widen the scope by one check:
`test_one` must exit non-zero when its selector matches no test. That check is
`selector_failure()` in `pipeline/core/config.py`, probed once at `register`
with `pipeline_register_probe_no_such_file.py::pipeline_register_probe_no_such_test`
and substituted the way `gate()` substitutes -- `cmd.format(test=shlex.quote(...))`.
Its limit is recorded in `## Decisions`: `register` knows no real test path, so
the probe path is bogus too.

Ordering is load-bearing, and step 9 comments it in the code. `suite_failure()`
runs first, `selector_failure()` second. The reproduction test's project has
`test_one = "true"` and a broken `test_suite`, and asserts the missing command's
name reaches the output. Reversed, the `test_one` message wins and that test
fails.

The human asked whether refusing a `.project/` holding no `pipeline.toml` is
intended. It is, and `## Decisions` says so. Step 11 pins both arms in
`test_register_refuses_a_project_directory_with_no_pipeline_toml`: refused
without `--force`, registered with it.

Measured today: `pytest -x` on that probe selector exits 4 (`collected 0
items`), so the packaged default config satisfies the new check.

The rest of the second plan stands. 14 steps, 7 files -- `--force` skips both
checks, and `pipeline/templates/skills/pipeline-config/SKILL.md` is the seventh
file, because it is what teaches a project to write `test_one`.

### 2026-08-27 16:32:48Z · planning · session · session=fa6d611c-17e2-43b7-8e4f-eb8ead0c68ec

`planning` ran as session `fa6d611c-17e2-43b7-8e4f-eb8ead0c68ec`
- replay: `claude --resume fa6d611c-17e2-43b7-8e4f-eb8ead0c68ec`
- log: `.project/logs/TICKET-068-planning-fa6d611c.log`

### 2026-08-27 16:32:48Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Third plan: adds the rejection's test_one zero-match probe (selector_failure) beside the test_suite smoke run, 14 steps, 7 files; states that refusing a .project/ with no pipeline.toml is intended and pins it.

### 2026-08-27 17:06:39Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails as required
```
r[39;49;00m[33m"[39;49;00m, [96mstr[39;49;00m(d), env={[33m"[39;49;00m[33mXDG_CONFIG_HOME[39;49;00m[33m"[39;49;00m: [96mstr[39;49;00m(tempfile.mkdtemp())})[90m[39;49;00m
>       [94massert[39;49;00m r.returncode != [94m0[39;49;00m, r.stdout + r.stderr[90m[39;49;00m
[1m[31mE       AssertionError: registered /tmp/tmp4x82yjll[0m
[1m[31mE         [0m
[1m[31mE       assert 0 != 0[0m
[1m[31mE        +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068/.venv/bin/python', '-m', 'pipeline', ..., '/tmp/tmp4x82yjll', 'register', '/tmp/tmp4x82yjll'], returncode=0, stdout='registered /tmp/tmp4x82yjll\n', stderr='').returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmp4x82yjll
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m

```
- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails on base `main` too -- the bug is not already fixed upstream
```
returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmpa3nz06yo
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.23s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-uht8zzyb/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-uht8zzyb/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- `## Decisions checked` cites DEC-064, which is not a record in /home/chezzijr/proj/agent-pipeline/.project/decisions -- a citation nobody can resolve is not a check

### 2026-08-27 17:06:39Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- `## Decisions checked` cites DEC-064, which is not a record in /home/chezzijr/proj/agent-pipeline/.project/decisions -- a citation nobody can resolve is not a check

### 2026-08-28 · planning

Fourth plan. The Tier A gate failed the third one on one item, quoted verbatim:
"`## Decisions checked` cites DEC-064, which is not a record in
/home/chezzijr/proj/agent-pipeline/.project/decisions -- a citation nobody can
resolve is not a check". The bullet meant to say that TICKET-064 wrote no
record, but it named the id to say so, and the gate resolves every id it finds.

That bullet now states it without naming an id. The ids this plan cites are
DEC-011, DEC-037, DEC-061 and DEC-065. All four have records in
`.project/decisions/`, and none carries a `superseded-by:` line.

The gate reported the other items ok, and no step changed. Re-checked every
anchor today against commit `5db3b35` -- `pipeline/cli/main.py` 15, 291-292 and
560; `pipeline/core/config.py` 8, 9, 17, 72 and 98; `tests/test_config.py` line
7 and 60 lines; `README.md` 129 and 136; both SKILL.md anchors. Two were off by
a word and are now exact: `cmd_register()` spans lines 291-292, not 292, and
`pipeline/templates/skills/pipeline-config/SKILL.md:25` reads "`<name>` appears
in the output", so step 13's replacement line keeps "appears".

### 2026-08-27 17:09:26Z · planning · session · session=e6fa1089-8ba0-4130-bd1b-6b36e48f0fc7

`planning` ran as session `e6fa1089-8ba0-4130-bd1b-6b36e48f0fc7`
- replay: `claude --resume e6fa1089-8ba0-4130-bd1b-6b36e48f0fc7`
- log: `.project/logs/TICKET-068-planning-e6fa1089.log`

### 2026-08-27 17:09:26Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Fourth plan: fixed the one Tier A failure -- the decisions bullet no longer cites an unresolvable id; 14 steps and 7 files unchanged, anchors re-verified

### 2026-08-28 · plan-validation

(Appended above the Tier A entry below, not at the end of the file: the
`plan-validation` guard blocks every shell writer, and the file ends inside a
fence whose ANSI bytes an editor anchor cannot match.)

**FAIL on one item of eight: decision conflict.** The branch is not a
descendant of `main`:

    $ git merge-base --is-ancestor main HEAD; echo $?
    1
    $ git rev-parse HEAD main
    5db3b352b1d10cd5ebd47f028df630d82d97a77c
    c56fe24b90194c514ff2bef1e6989ce1df864120

`main` holds TICKET-067, TICKET-072 and TICKET-073. Two of their decisions
constrain this plan. The plan cites neither, and neither carries a
`superseded-by:` line.

long: eight scored items, each with the evidence its verdict rests on.

**DEC-067.** `main` has one substitution function for all four test-command
call sites, and it is not `str.format`:

    pipeline/core/config.py:101:def format_test_cmd(template: str, test: str) -> str:
    pipeline/core/gate.py:174:            format_test_cmd(cfg["test_one"], test), base_wt)
    pipeline/core/gate.py:246:            code, out = run_cmd(format_test_cmd(cfg["test_one"], test), wd)
    pipeline/daemon/supervisor.py:725:        return child(format_test_cmd(cfg["test_suite"], t.test_file or ""), "suite")

DEC-067 states why: "This is a regex, deliberately not `str.format`. [...]
`str.format` raised `KeyError: 't##*'` on a literal `${t##*::}`, which is what
pushed projects into `$(echo {test} | sed ...)` in the first place."

Three consequences:

1. Step 7 reintroduces `cmd.format(test=shlex.quote(PROBE_TEST))`. The plan's
   own rule -- substitute "exactly as `gate()` does" -- now names
   `format_test_cmd(cfg["test_one"], PROBE_TEST)`.
2. Step 5 probes `test_one="echo ${t##*::}"` and asserts `"format string" in
   braces`. Under `format_test_cmd()` that brace reaches the shell, `echo`
   runs, it exits 0, and the message reads "it exited 0". The arm fails. It
   pins an error DEC-067 removed on purpose.
3. The digest bullet "`pipeline/daemon/supervisor.py:724` runs
   `cfg["test_suite"]` raw -- no `{test}` -- so `register` runs it raw too" is
   false on `main`: `test_suite` is substituted there now.

**DEC-072.** `registry.register()` gained two refusals -- a linked git
worktree, and `PIPELINE_STAGE` set -- and sits at
`pipeline/daemon/registry.py:83`. The digest says `:60` and "It stays
unchanged". The four new CLI tests still pass under it: `main`'s
`tests/conftest.py:19` is `os.environ.pop("PIPELINE_STAGE", None)`, and a
`mkdtemp()` directory is not a worktree. README already carries a DEC-072
paragraph directly below the code fence step 13(a) appends to.

**Anchors that moved on `main`.** `cmd_register()` 292 -> 305; the `register`
parser row 560 -> 573; `def harness(` 98 -> 114; `gate()`'s two `test_one`
sites 148/220 -> 174/246; `tests/test_config.py` 60 -> 77 lines, and its line 7
is now `from pipeline.core.config import format_test_cmd, project_config,
stage_extra`, so steps 1 and 5 rewriting that line verbatim drop
`format_test_cmd` and break `main`'s two new tests. `tests/test_cli.py` is 486
lines. In `pipeline/templates/skills/pipeline-config/SKILL.md` lines 25 and 29
still read as the plan says, but the brace paragraph the plan works around is
replaced by "`{test}` is the whole `<path>::<name>` value; `{path}` and
`{name}` are its two halves."

The other seven items pass.

- **Root cause, pass.** `cmd_register()` writes the registry line without ever
  executing the project's commands, so a config the dispatcher cannot run is
  found one ticket at a time at the gate. The plan runs both commands at
  register, through the same `run_cmd()` the dispatcher uses. It fixes the
  cause, not the assertion.
- **Scope discipline, pass.** 13 of 14 steps trace to an acceptance criterion.
  Step 13 (docs) traces to `CLAUDE.md`: a change to a CLI command "is not
  finished until the skill says the same thing". No step is untraceable.
- **Falsifiable criteria, pass.** Each criterion names an input and an exit
  code. `test_suite = "echo 1 failed; exit 1"` must register;
  `test_one = "true"` must be refused. An implementation refusing every
  non-zero suite fails the first; one reading exit codes only fails the
  `NO_TESTS_RE` arm.
- **No research left, pass.** Every step names its file, its line and its
  function, and both helper bodies are written out.
- **Riskiest step, pass.** Step 9: every `pipeline register` starts spawning
  two project commands. The plan states two fallbacks -- `--force`, and
  `## Rollback`, which reverts the five commits and says what survives
  (nothing).
- **Regression surface, pass.** `cmd_init()` never calls `register`, so
  `pipeline init` is unaffected. `tests/test_cli.py:484` is the only test that
  runs `pipeline register` through the CLI. `tests/test_daemon.py` calls
  `registry.register()` in-process, which the plan leaves alone.
- **Blast radius, pass.** 7 files: 2 source, 2 test, 3 doc. No file is in
  `machine.FENCED`.

**To fix.** Rebase on `main` (`c56fe24`), then re-anchor:

1. Substitute the probe with `format_test_cmd(cfg["test_one"], PROBE_TEST)`.
2. Drop the `echo ${t##*::}` arm, or invert it to assert the brace passes
   through untouched.
3. Cite DEC-067 and DEC-072 in `## Decisions checked`.
4. Re-take every line number against `main`.

The two checks, their order, `--force` and the acceptance criteria stand.

### 2026-08-27 17:09:45Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails as required
```
r[39;49;00m[33m"[39;49;00m, [96mstr[39;49;00m(d), env={[33m"[39;49;00m[33mXDG_CONFIG_HOME[39;49;00m[33m"[39;49;00m: [96mstr[39;49;00m(tempfile.mkdtemp())})[90m[39;49;00m
>       [94massert[39;49;00m r.returncode != [94m0[39;49;00m, r.stdout + r.stderr[90m[39;49;00m
[1m[31mE       AssertionError: registered /tmp/tmpogcwdz9h[0m
[1m[31mE         [0m
[1m[31mE       assert 0 != 0[0m
[1m[31mE        +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068/.venv/bin/python', '-m', 'pipeline', ..., '/tmp/tmpogcwdz9h', 'register', '/tmp/tmpogcwdz9h'], returncode=0, stdout='registered /tmp/tmpogcwdz9h\n', stderr='').returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmpogcwdz9h
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m

```
- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails on base `main` too -- the bug is not already fixed upstream
```
returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmp75of8nod
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.23s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-d60kglz8/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-d60kglz8/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 17:17:29Z · plan-validation · session · session=3d533259-5b93-4c79-8403-e3a0c06011c6

`plan-validation` ran as session `3d533259-5b93-4c79-8403-e3a0c06011c6`
- replay: `claude --resume 3d533259-5b93-4c79-8403-e3a0c06011c6`
- log: `.project/logs/TICKET-068-plan-validation-3d533259.log`

### 2026-08-27 17:17:29Z · plan-validation · transition · to=escalated · result=fail · marker=yes

**plan-validation -> escalated** (result: `fail`)

✓ Tier B FAIL on decision conflict: branch 5db3b35 is not a descendant of main c56fe24; DEC-067 (format_test_cmd, not str.format) and DEC-072 (register refusals) are uncited and step 5's brace arm fails after a rebase. Seven other items pass.

### 2026-08-27 17:18:19Z · human · note · by=chezzijr

**resumed** by chezzijr -> `planning`, reset [], granted `plan_validation_attempts` 3 -> 2

### 2026-08-28 · planning

Fifth plan. Tier B failed the fourth on decision conflict, and this plan
re-anchors on `main` rather than redesigning. Three changes:

1. Step 1 rebases the branch onto `main`. `main` moved past the `c56fe24` Tier B
   measured: it is `c0e516d` today, and TICKET-079 moved `pipeline/core/gate.py`
   again, so the `test_one` call sites are `:189` and `:261`, not `:174`/`:246`.
   `git merge-tree --write-tree main HEAD` exits 0 and prints tree `6ed6930`, so
   the rebase conflicts nowhere; `git diff --name-only main HEAD` lists only
   `tests/test_cli.py`.
2. DEC-067. Both probes now call `format_test_cmd()`. `suite_failure()` passes
   `""`, matching `supervisor.py:725`'s `t.test_file or ""`. The `"format
   string"` arm is gone; each unit test instead pins that a literal `${t##*::}`
   is judged by its exit code and returns `None`.
3. DEC-072. Step 4 splits `register()`'s four pre-write refusals into
   `registry.check()`, changing none of them, and `cmd_register()` calls
   `check()` first. Without it a stage running `pipeline register .` would run
   the project's whole suite before getting `the registry is operator state`.

Two steps and one file are new: `pipeline/daemon/registry.py` and
`tests/test_registry_worktree.py`. Nine files declared, 16 steps.

Out of scope, noted not fixed: `pipeline/templates/skills/pipeline-config/SKILL.md:18-19`
still reads "The gate substitutes it with `str.format` after `shlex.quote`",
which DEC-067 made false; lines 37-39 of the same file are correct.

### 2026-08-27 17:45:23Z · planning · session · session=1e2bbfaa-bd34-4fb8-b6d0-aacbd364b582

`planning` ran as session `1e2bbfaa-bd34-4fb8-b6d0-aacbd364b582`
- replay: `claude --resume 1e2bbfaa-bd34-4fb8-b6d0-aacbd364b582`
- log: `.project/logs/TICKET-068-planning-1e2bbfaa.log`

### 2026-08-27 17:45:23Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Fifth plan, re-anchored on main c0e516d: step 1 rebases, both probes use format_test_cmd() per DEC-067, and new registry.check() keeps DEC-072's refusals first; 16 steps, 9 files

### 2026-08-27 17:45:42Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails as required
```
r[39;49;00m[33m"[39;49;00m, [96mstr[39;49;00m(d), env={[33m"[39;49;00m[33mXDG_CONFIG_HOME[39;49;00m[33m"[39;49;00m: [96mstr[39;49;00m(tempfile.mkdtemp())})[90m[39;49;00m
>       [94massert[39;49;00m r.returncode != [94m0[39;49;00m, r.stdout + r.stderr[90m[39;49;00m
[1m[31mE       AssertionError: registered /tmp/tmpv03rv_p3[0m
[1m[31mE         [0m
[1m[31mE       assert 0 != 0[0m
[1m[31mE        +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068/.venv/bin/python', '-m', 'pipeline', ..., '/tmp/tmpv03rv_p3', 'register', '/tmp/tmpv03rv_p3'], returncode=0, stdout='registered /tmp/tmpv03rv_p3\n', stderr='').returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmpv03rv_p3
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m

```
- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails on base `main` too -- the bug is not already fixed upstream
```
returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmpnhd2zl_t
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.23s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-f5xduc2k/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-f5xduc2k/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```
- acceptance criterion names no test: - `git merge-base --is-ancestor main HEAD; echo $?` prints `0`, so the branch carries `format_test_cmd()` and the DEC-072 refusals.

### 2026-08-27 17:45:42Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion names no test: - `git merge-base --is-ancestor main HEAD; echo $?` prints `0`, so the branch carries `format_test_cmd()` and the DEC-072 refusals.

### 2026-08-28 · planning

Sixth plan. Tier A failed the fifth on one finding, and this plan changes only
what that finding named:

    acceptance criterion names no test: - `git merge-base --is-ancestor main HEAD; echo $?` prints `0`, so the branch carries `format_test_cmd()` and the DEC-072 refusals.

`gate()` requires every acceptance criterion to name a test (`pipeline/core/gate.py:426-439`
on `main`, `c0e516d`): a criterion must match `pytest`, a `test`-prefixed word,
`::`, `*_test` or `tests/`. The rebase criterion matched none -- `format_test_cmd`
does not, because the regex wants a word boundary before `test` and `_` is a word
character. The criterion now names the two tests the rebase carries:
`tests/test_registry_worktree.py::test_check_refuses_before_the_caller_spawns_anything`
and `tests/test_config.py::test_selector_failure_wants_test_one_to_fail_when_it_matches_nothing`.

Nothing else moved: the same 16 steps, the same 9 declared files, the same nine
other criteria. Re-checked against `main` at `c0e516d` today: `main` has not
moved since the fifth plan measured it, the branch is still `5db3b35` and still
not a descendant of `main` (`git merge-base --is-ancestor main HEAD; echo $?`
prints `1`), and `pipeline/cli/main.py:305-306` is still the one-line
`cmd_register()`. Every cited decision resolves in `.project/decisions/` and
none carries a `superseded-by:` line.

Note, not fixed here: `pipeline/core/gate.py` moved on `main` since the fifth
plan was gated, so the criterion check now sits at `:426-439`, not `:385-395`.
No plan step touches that file.

### 2026-08-27 17:48:29Z · planning · session · session=ab49c126-f0ea-496d-91fa-5188a61b1a81

`planning` ran as session `ab49c126-f0ea-496d-91fa-5188a61b1a81`
- replay: `claude --resume ab49c126-f0ea-496d-91fa-5188a61b1a81`
- log: `.project/logs/TICKET-068-planning-ab49c126.log`

### 2026-08-27 17:48:29Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Sixth plan: the rebase acceptance criterion now names the two tests it carries, the one Tier A finding; 16 steps and 9 files unchanged

### 2026-08-28 · plan-validation · Tier B

long: eight scored items plus two findings; rule 9 keeps every anchor and count.

Placement note: this entry sits above the gate entry that follows it, not below.
Appending at the end of the file needs a unique anchor there, and the last five
gate fences end in byte-identical uv output. It ran after that gate.

**Tier B: PASS.** Eight items, each checked against `main` at `c0e516d`.

1. **Root cause.** `register` writes the path after checking only that
   `.project/` exists and that no `PIPELINE_STAGE` is set. It never runs the
   project's commands, so a config the dispatcher cannot use is accepted at the
   one moment an operator is present to fix it. The plan runs both commands at
   `register`. It fixes the cause, not the test: `--force` and the
   accept-a-red-suite arm cover the class, not the one repro.
2. **Decisions.** All seven cited ids resolve in `.project/decisions/` and none
   carries `superseded-by:`. I read DEC-067 and DEC-072 in full. DEC-067 is the
   regex rule; both probes call `format_test_cmd()`. DEC-072's four refusals
   move verbatim into `check()`. DEC-061 is the one departure -- `suite_failure()`
   matches `NO_TESTS_RE` against output -- and `## Decisions` states it.
3. **Scope.** Steps 1-14 and 16 each trace to a criterion. Step 15 (3 doc files)
   traces to none. `CLAUDE.md` makes the file-ticket and pipeline-config skills
   part of the interface, so it stands.
4. **Criteria falsifiable.** The `${t##*::}` arm errors with `KeyError: 't##*'`
   under `str.format`. The red-suite arm fails if the refusal widens to any
   non-zero exit. The `--force` arm fails if the flag is ignored. None vacuous.
5. **No research left.** Every anchor confirmed on `main`: `cli/main.py:15`,
   `:305-306`, `:573`; `registry.py:83-108`; `config.py:17`, `:101-111`,
   `:114`; `test_config.py:7` (77 lines); `test_registry_worktree.py`
   (101 lines, imports `os`, `PipelineError`, `git_project`);
   `README.md:129,136,141`; `file-ticket/SKILL.md:138`;
   `pipeline-config/SKILL.md:25,29,35,68-70`. `tests/conftest.py:14` resolves
   `TMPDIR`, so step 2's `registry.check(d) == d` holds.
6. **Riskiest step: 13**, wiring `cmd_register()`. It changes what every
   operator's `register` does, and no unit test proves it alone. The plan states
   a fallback twice: `--force`, named in both refusal messages, and
   `## Rollback`'s `git revert`, which returns `register` to an unconditional
   append. Step 1 carries its own -- stop and report a conflict, do not resolve it.
7. **Regression surface, measured.** `registry.register()` has exactly one
   caller in the package, `pipeline/cli/main.py:293`; `cmd_init` does not
   auto-register, so nothing else gains a shell spawn. In-process callers are
   `tests/test_daemon.py:137,189,190,323,437,463,665` and
   `tests/test_registry_worktree.py`, and step 4 runs both files. `pipeline
   register` appears in one existing CLI test, the reproduction itself, so no
   existing CLI test regresses. The packaged defaults survive the probe: I ran
   `uv run --group dev pytest -q -x 'pipeline_register_probe_no_such_file.py::pipeline_register_probe_no_such_test'`
   and it exited `4`, printing `no tests ran`.
8. **Blast radius.** `class: feature`, 16 steps, 9 files: 3 source, 3 test, 3
   doc. `files_declared` matches the files the steps name. Appropriate.

**Correction to the digest, not a plan defect.** The digest says
`git diff --name-only main HEAD` lists only `tests/test_cli.py`. Run today it
lists 43 files, because `HEAD` is not a descendant of `main`. The claim holds
in the three-dot form: `git diff --name-only main...HEAD` prints
`tests/test_cli.py`, and `git log --oneline main..HEAD` is the single commit
`5db3b35`. The rebase is still clean. I could not run `git merge-tree` -- the
guard refused it, `git merge-tree: not a read-only git subcommand` -- so I
compared the two hunks instead: `main` has changed `tests/test_cli.py` only at
lines 435-460 since the merge-base `571680f`, and `5db3b35` appends at EOF.

**Accepted false-refusal, for `review` to keep in view.** `suite_failure()`
refuses any non-zero exit whose output matches `NO_TESTS_RE`. A `test_suite`
chaining two runners, exiting non-zero for a real failure while one sub-run
prints `collected 0 items`, is refused as cannot-run. `--force` covers it.

### 2026-08-27 17:48:48Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails as required
```
r[39;49;00m[33m"[39;49;00m, [96mstr[39;49;00m(d), env={[33m"[39;49;00m[33mXDG_CONFIG_HOME[39;49;00m[33m"[39;49;00m: [96mstr[39;49;00m(tempfile.mkdtemp())})[90m[39;49;00m
>       [94massert[39;49;00m r.returncode != [94m0[39;49;00m, r.stdout + r.stderr[90m[39;49;00m
[1m[31mE       AssertionError: registered /tmp/tmpje2jv2fx[0m
[1m[31mE         [0m
[1m[31mE       assert 0 != 0[0m
[1m[31mE        +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068/.venv/bin/python', '-m', 'pipeline', ..., '/tmp/tmpje2jv2fx', 'register', '/tmp/tmpje2jv2fx'], returncode=0, stdout='registered /tmp/tmpje2jv2fx\n', stderr='').returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmpje2jv2fx
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.11s[0m[31m ===============================[0m

```
- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails on base `main` too -- the bug is not already fixed upstream
```
returncode[0m

[1m[31mtests/test_cli.py[0m:497: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmp0mhyu8r0
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.23s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-v9i254_n/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-v9i254_n/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 17:56:38Z · plan-validation · session · session=bded5d69-0bc7-4fcd-812f-d329dacf8582

`plan-validation` ran as session `bded5d69-0bc7-4fcd-812f-d329dacf8582`
- replay: `claude --resume bded5d69-0bc7-4fcd-812f-d329dacf8582`
- log: `.project/logs/TICKET-068-plan-validation-bded5d69.log`

### 2026-08-27 17:56:38Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B PASS: all eight items scored against main c0e516d; every plan anchor confirmed, one digest wording correction and one accepted false-refusal noted in the thread

### 2026-08-27 17:58:50Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket and rejected its earlier narrow scope -- audit in thread)

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket and rejected its earlier narrow scope -- audit in thread)**

### 2026-08-27 18:00:51Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails as required
```
r[39;49;00m[33m"[39;49;00m, [96mstr[39;49;00m(d), env={[33m"[39;49;00m[33mXDG_CONFIG_HOME[39;49;00m[33m"[39;49;00m: [96mstr[39;49;00m(tempfile.mkdtemp())})[90m[39;49;00m
>       [94massert[39;49;00m r.returncode != [94m0[39;49;00m, r.stdout + r.stderr[90m[39;49;00m
[1m[31mE       AssertionError: registered /tmp/tmpifsd4a16[0m
[1m[31mE         [0m
[1m[31mE       assert 0 != 0[0m
[1m[31mE        +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068/.venv/bin/python', '-m', 'pipeline', ..., '/tmp/tmpifsd4a16', 'register', '/tmp/tmpifsd4a16'], returncode=0, stdout='registered /tmp/tmpifsd4a16\n', stderr='').returncode[0m

[1m[31mtests/test_cli.py[0m:502: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmpifsd4a16
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.19s[0m[31m ===============================[0m

```
- ok: `tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run` fails on base `main` too -- the bug is not already fixed upstream
```
.returncode[0m

[1m[31mtests/test_cli.py[0m:502: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_cli.py::[1mtest_register_refuses_a_project_whose_test_suite_cannot_run[0m - AssertionError: registered /tmp/tmpu7cvqdxi
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.24s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-d3_d70hb/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-d3_d70hb/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 9ms[0m[0m

```

### 2026-08-27 18:00:52Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-28 · implementing · todo list

1. Rebase onto main -- done, branch already an ancestor of `main`, no conflict.
2. Add `test_check_refuses_before_the_caller_spawns_anything` to `tests/test_registry_worktree.py` -- done.
3. Confirm RED (`AttributeError: no attribute 'check'`) -- done.
4. Split `register()` into `check()`/`register()` in `registry.py`, commit `33e3a65` -- done.
5. Add `_probe_project`/`test_suite_failure_...` to `tests/test_config.py` -- done.
6. Confirm RED (`ImportError: cannot import name 'suite_failure'`) -- done.
7. Implement `suite_failure()` in `config.py` -- done.
8. Confirm GREEN, commit `0d68de9` -- done.
9. Add `test_selector_failure_...` -- done.
10. Confirm RED (`ImportError: cannot import name 'selector_failure'`) -- done.
11. Implement `selector_failure()` in `config.py` -- done.
12. Confirm GREEN, commit `5572fd9` -- done.
13. Wire both checks into `cmd_register()` in `pipeline/cli/main.py`, add `--force`, commit `d61bbde` -- done.
14. Add the four `pipeline register` CLI tests, commit `ad0c8bc` -- done.
15. Update `README.md` and both skill templates -- done.
16. Full suite green, commit `b1e2344` -- done.

### 2026-08-28 · implementing · result

All 16 steps done as written, no plan deviation. TDD followed for every new
function: each RED confirmed for the stated reason (`AttributeError` /
`ImportError`) before the implementation, each GREEN confirmed after.

`uv run --group dev pytest -q` -- `376 passed`, no failures, no errors, no
`ERROR ...::suite_failure` / `::selector_failure` / `::project_test_cmd`.

The nine acceptance-criterion tests pass individually:
`tests/test_cli.py::test_register_refuses_a_project_whose_test_suite_cannot_run`,
`::test_register_refuses_a_test_one_that_exits_0_on_a_selector_matching_nothing`,
`::test_register_accepts_a_project_whose_test_suite_runs_and_fails`,
`::test_register_refuses_a_project_directory_with_no_pipeline_toml`,
`::test_register_force_skips_both_test_command_checks`,
`tests/test_config.py::test_suite_failure_tells_a_broken_command_from_a_red_suite`,
`::test_selector_failure_wants_test_one_to_fail_when_it_matches_nothing`,
`tests/test_registry_worktree.py::test_check_refuses_before_the_caller_spawns_anything`.

`git merge-base --is-ancestor main HEAD; echo $?` prints `0`.

One note, not blocking: the plan's expected pytest counts at steps 8/12
("5 passed" / "6 passed") undercounted `tests/test_config.py`'s pre-existing
tests -- actual counts were 7 and 8. Every arm named in the plan passed; the
mismatch is only in the plan's stated total, not a missing or extra test.

Six commits: `33e3a65`, `0d68de9`, `5572fd9`, `d61bbde`, `ad0c8bc`, `b1e2344`.

### 2026-08-27 18:05:41Z · implementing · session · session=0e57bae7-dd04-4b51-b8ef-318bdb1ccfeb

`implementing` ran as session `0e57bae7-dd04-4b51-b8ef-318bdb1ccfeb`
- replay: `claude --resume 0e57bae7-dd04-4b51-b8ef-318bdb1ccfeb`
- log: `.project/logs/TICKET-068-implementing-0e57bae7.log`

### 2026-08-27 18:05:41Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Ran all 16 plan steps with TDD; register now refuses a test_suite that cannot run or a test_one that misses a zero-match probe, --force skips both; 376 passed, no failures/errors.

### 2026-08-28 · review

**PASS. No blocking findings.** Reviewed the whole branch delta, `main...HEAD`:
7 commits, 9 files.

Verified against the acceptance criteria, re-run in this worktree:

- The 8 named tests pass by node id: `8 passed in 0.51s`.
- `uv run --group dev pytest -q` reports `376 passed`, no failures, no errors.
- `git merge-base --is-ancestor main HEAD; echo $?` prints `0`.
- `python -m pipeline register --help` prints `[--force]` and
  `register without running the project's test commands`.
- Order holds: `cmd_register()` calls `registry.check()` at
  `pipeline/cli/main.py:313`, above the `--force` branch and both probes, so
  DEC-072's `PIPELINE_STAGE` refusal fires before any spawn.

Minor findings, none blocking:

1. minor -- `pipeline/templates/skills/pipeline-config/SKILL.md:25` now reads
   "`the name` appears in the output". On `main` it read "`<name>`", and the
   trap bullet below it still says "`<name>` must reach the output". Plan step
   15(c) asked to keep the name in backticks as it was.
2. minor -- `README.md:145` says "the runner must run something", but
   `pipeline/core/config.py:152` requires `code != 0` before `NO_TESTS_RE`. A
   suite that runs nothing and exits 0 registers. That matches DEC-061; the
   README claims one case more than the code checks.
3. minor -- no test pins the `check()`-before-`suite_failure()` order in
   `cmd_register()`. `test_check_refuses_before_the_caller_spawns_anything`
   calls `registry.check()` in isolation, so reordering `cmd_register()` keeps
   the suite green. This matches plan step 2 as written.
4. minor -- `pipeline register` now runs the project's `test_suite` and
   `test_one` from HEAD's config, so registering a repo executes its shell
   commands. Intended and documented; `--force` skips both.

Checked and dropped: the double `check()` call (`cmd_register()` then
`register()`) is idempotent -- `pipeline/daemon/registry.py:83-104` writes
nothing.

### 2026-08-27 18:09:48Z · review · session · session=8c8a111c-69a2-4d81-b79f-46ff462fb8fa

`review` ran as session `8c8a111c-69a2-4d81-b79f-46ff462fb8fa`
- replay: `claude --resume 8c8a111c-69a2-4d81-b79f-46ff462fb8fa`
- log: `.project/logs/TICKET-068-review-8c8a111c.log`

### 2026-08-27 18:09:48Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed main...HEAD (7 commits, 9 files): no blocking findings; 8 named tests pass, full suite 376 passed, ancestry check prints 0; 4 minor findings appended

### 2026-08-27 18:10:07Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-27 18:10:09Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/068


Current branch ticket/068 is up to date.
Already up to date.
Updating c0e516d..b1e2344
Fast-forward
 README.md                                          | 10 ++-
 pipeline/cli/main.py                               | 24 +++++-
 pipeline/core/config.py                            | 85 +++++++++++++++++++++-
 pipeline/daemon/registry.py                        | 25 +++++--
 pipeline/templates/skills/file-ticket/SKILL.md     |  6 +-
 pipeline/templates/skills/pipeline-config/SKILL.md | 13 +++-
 tests/test_cli.py                                  | 74 +++++++++++++++++++
 tests/test_config.py                               | 45 +++++++++++-
 tests/test_registry_worktree.py                    | 21 ++++++
 9 files changed, 286 insertions(+), 17 deletions(-)

```

### 2026-08-27 18:10:09Z · merging · decision

decision recorded as `DEC-068`
