---
id: TICKET-058
stage: done
class: feature
branch: ticket/058
test_file: pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows
files_declared:
- .project/pipeline.toml
- CLAUDE.md
- README.md
- pipeline/core/config.py
- pipeline/daemon/supervisor.py
- pipeline/hooks/dangerous-commands.py
- pipeline/hooks/test_dangerous_commands.py
- pipeline/templates/pipeline.toml
- tests/test_harness.py
- tests/test_stages.py
counters:
  plan_validation_attempts: 2
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 27
  plan_files: 10
  no_result: 0
  rebase_conflicts: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 49632b57-48c5-494e-bcde-1de33441bd7c
  log: .project/logs/TICKET-058-review-49632b57.log
approved_by: chezzijr
approved_at: '2026-08-27T02:10:12.965322+00:00'
---

## Summary

Implemented and reviewed. 7 commits on `ticket/058`: `67ee105` reproduction,
`299160a` test, `e180550` guard, `a25e09c` config, `733d6f8` spawn,
`6ec9ae9` project declaration, `be6bd84` docs.

`readonly_prefixes()` in `pipeline/hooks/dangerous-commands.py` reads
`PIPELINE_READONLY_ALLOW`, fails closed to `[]` on anything malformed, and
matches as an argv prefix inside `readonly_rules()`'s per-segment loop, below
`always_rules()` and the redirection/command-substitution checks.
`readonly_allow()` in `pipeline/core/config.py` lexes `[readonly] allow` from
`project_config()` and returns `[]` when the project has no config. `spawn()`
in `pipeline/daemon/supervisor.py` exports it as JSON. This repo's own
`.project/pipeline.toml` declares `pipeline ls`, `status`, `plan`, `projects`,
`metrics` and the guard's own test file.

Review found nothing blocking; three nits are in `## Thread`.
`uv run --group dev pytest -q` -- 320 passed, including the reproduction test.
`./pipeline/hooks/test_dangerous_commands.py` prints `guard: all passed`.
`CLAUDE.md` carries exactly one `# 122 guard cases (table-driven)` line.

`.project/pipeline.toml` and `pipeline/hooks/dangerous-commands.py` are both
in `machine.FENCED`, so this ticket parks at `awaiting-merge` after the
regression suite runs clean.

## Reproduction

Test: `pipeline/hooks/test_dangerous_commands.py` -- the pytest-collected
`test_a_read_only_stage_runs_the_commands_its_project_allows`, which sets
`PIPELINE_READONLY_ALLOW` to `[["pipeline", "ls"], ["pipeline", "status"]]`
and asserts `guard.verdict("pipeline ls", True) is None`.

Command: `uv run --group dev pytest -x pipeline/hooks/test_dangerous_commands.py`

Output:
```
E               AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)
E               assert '`pipeline` is not on the read-only allowlist' is None

pipeline/hooks/test_dangerous_commands.py:158: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows
```

expect: `pipeline` is not on the read-only allowlist

Committed as `67ee105` on `ticket/058`. `readonly_rules()` in
`pipeline/hooks/dangerous-commands.py` has no entry for `pipeline` in
`READ_TOOLS`, `GUARDED`, or `TEST_RUNNERS`, so any `write: false` stage
invoking the project's own CLI is blocked outright. Re-run 2026-08-27 on
`67ee105`: same text, now at line 158.

## Digest

- Files touched: `pipeline/hooks/dangerous-commands.py` (`readonly_rules()`), `pipeline/core/config.py` (new `readonly_allow()`), `pipeline/daemon/supervisor.py` (`spawn()` env block), `pipeline/hooks/test_dangerous_commands.py`, `tests/test_stages.py`, `tests/test_harness.py`, `.project/pipeline.toml`, `pipeline/templates/pipeline.toml`, `README.md`, `CLAUDE.md`.
- Entry points: `verdict(command, readonly)` (`pipeline/hooks/dangerous-commands.py:275`) runs `always_rules()` first and `readonly_rules()` (line 231) only when `PIPELINE_READONLY=1`; `spawn()` (`pipeline/daemon/supervisor.py:329`) sets `PIPELINE_READONLY` at line 397 and the MCP env at lines 404-406.
- The MCP seam is the pattern to copy, end to end: `mcp_servers()` (`pipeline/core/config.py:107`) validates a `[mcp.<name>]` table, `spawn()` exports it, `mcp_verdict()` (`pipeline/hooks/dangerous-commands.py:335`) default-denies. Copy that shape; do not invent a second one.
- Gotcha, this is what rejected the second plan: `project_config()` raises `PipelineError(f"no {cfg} -- run `pipeline init {project}` first")` (`pipeline/core/config.py:92`) when a project has no `.project/pipeline.toml` on disk and none in HEAD. `tests/test_pty.py` calls `supervisor.spawn()` on a bare `tempfile.mkdtemp()` at lines 412, 419, 438 and 444. `spawn()` survives that today because `mcp_servers()` returns `{}` at line 117 before reading the config, and `project_stage_config()` catches `PipelineError` and returns `{}` (`pipeline/core/config.py:38-41`). `readonly_allow()` must catch it the same way and return `[]` -- no config means no widening, which fails closed.
- The recut changed this: `tables()` (`pipeline/hooks/test_dangerous_commands.py:130`) now holds the six `check` calls, and `test_the_allow_and_block_tables()` calls it, so pytest runs every table case. DEC-057 forbids moving those calls back into `__main__`.
- The recut changed this: `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` (line 305) sums six named tables and asserts `CLAUDE.md` carries `# <N> guard cases (table-driven)` with that exact N. Measured on `67ee105`: 33+17+32+21+4+2 = 109, and `CLAUDE.md:95` says 109. Adding a table case without updating both turns that test red.
- Gotcha, load-bearing: `tables()` must pop `PIPELINE_READONLY_ALLOW` for its own run. After step 23 this repo declares `pipeline status`, and `test_suite` runs inside a stage that exports the variable, so `check(BLOCKED_READONLY, True, True, "readonly")` would see `pipeline status` allowed and fail.
- Gotcha: `readonly_rules()` checks redirection and `$(`/backtick BEFORE its per-segment loop (lines 232-236), so a prefix match added inside the loop cannot smuggle either.
- Gotcha: `always_rules()` runs before `readonly_rules()`, so no project entry can re-enable `sudo`, `rm -rf /`, `git push --force` or `git worktree remove`. That ordering is the safety argument; keep it.
- Gotcha: `flatten()` unwraps `sh -c` before any rule sees it, so a prefix is compared against the real argv, not the wrapper.
- Gotcha, measured on `67ee105`: `verdict("uv run pipeline approve TICKET-058", True)` returns `None` -- `GUARDED["uv"] = {"run"}` checks `args[0]` only. DEC-057 records that hole and says closing it needs its own ticket. Out of scope here.
- Gotcha: DEC-057 forbids adding an import to `pipeline/hooks/test_dangerous_commands.py` that base does not have, because `_base_findings()` copies that file onto a checkout of base. This plan adds none: `json`, `os`, `subprocess` and `sys` are already imported at line 3.
- Gotcha: the guard's tables call `guard.verdict(c, readonly)` with no env, so a case needing `PIPELINE_READONLY_ALLOW` needs its own checker. `check_mcp()` (`pipeline/hooks/test_dangerous_commands.py:115`) is the save/restore pattern to copy.
- `tests/test_stages.py` asserts a raise with `try: ... assert False, "..." except PipelineError: pass` (lines 130-139), not `pytest.raises`. Match that style; `PipelineError` is imported at line 11 and `tempfile` at line 6.
- `pipeline/cli/main.py:532-550` is the command surface. Read-only: `ls`, `status`, `plan` (DEC-050; `cmd_plan` prints two sections and nothing else), `projects`, `metrics`. Mutating: `init`, `new`, `approve`, `reject`, `answer`, `resume`, `register`, `unregister`, `start`, `stop`, `run`. `gate` runs the project's test command; `logs -f` blocks; `tui` needs a terminal.
- `.project/pipeline.toml` and `pipeline/hooks/dangerous-commands.py` are both in `machine.FENCED`, so this ticket parks at `awaiting-merge`.

## Decisions checked

Grepped `.project/decisions/` for `readonly`, `read-only`, `allowlist`,
`project_config`, `pipeline.toml`; read DEC-011, DEC-017, DEC-019, DEC-021,
DEC-026, DEC-034, DEC-036, DEC-037, DEC-038, DEC-041, DEC-050, DEC-052,
DEC-056, DEC-057.

- DEC-036 binds the shape: an allowlist, default deny, declared per project, never pattern matching on arguments. This plan applies that shape to shell commands instead of MCP servers.
- DEC-037 binds where the list lives: `project_config()` reads HEAD, so `readonly_allow()` must go through it and never read the worktree.
- DEC-038 binds the safety argument: provenance, not a clamp. A stage cannot change the config of its own spawn, and a committed widening lands in the ticket's diff behind the fence.
- DEC-057 binds three things this plan obeys: the tables run under pytest via `tables()` and the calls stay there; no new import in the guard's test file; and `CLAUDE.md`'s case count is counted by a test, not claimed. It also forbids re-adding an option grammar or a backslash pre-pass, neither of which this plan touches, and it records the `uv run` hole as a separate ticket.
- DEC-026 is the backstop this seam leans on: a read-only stage's tree snapshot escalates `wrote-in-readonly`, so a prefix that turns out to write is caught after the fact.
- DEC-017 binds step 14 and step 19 indirectly: a test file the gate copies onto base may only import what base has. Both steps add tests to files whose imports are unchanged.
- DEC-034 is untouched: `strip_settings_sources()` and the `--settings` registration stay as they are.
- DEC-050 is the source for `pipeline plan <id>` being read-only, which is why it is in this repo's declared list.
- DEC-041 is history (`superseded-by: DEC-052`); cited only for the `--add-dir` reach it once described. DEC-052 is the active record and this plan does not touch it.
- DEC-011, DEC-019, DEC-021, DEC-056 were read and constrain nothing here.

This plan contradicts none of them.

## Plan

1. Add `"pipeline status"` to `BLOCKED_READONLY` in `pipeline/hooks/test_dangerous_commands.py`, with a comment that default deny stands even though this repo's own `[readonly] allow` names the command, because `tables()` pops `PIPELINE_READONLY_ALLOW`.
2. Add three tables to `pipeline/hooks/test_dangerous_commands.py`, directly below `ALLOWED_READONLY`: `PROJECT_PREFIXES = [["pipeline", "ls"], ["pipeline", "status"], ["./pipeline/hooks/test_dangerous_commands.py"]]`, `ALLOWED_PROJECT = ["pipeline ls", "pipeline ls -v", "pipeline status", "./pipeline/hooks/test_dangerous_commands.py", "pipeline ls | head -5"]` and `BLOCKED_PROJECT = ["pipeline approve TICKET-058", "pipeline resume TICKET-058 --stage planning", "pipeline", "pipelines ls", "pipeline ls > out.txt", "pipeline ls && git commit -am wip", "sudo pipeline ls"]`.
3. Add `check_readonly_allow(cmds, expect_block, label, prefixes=PROJECT_PREFIXES)` below `check_mcp()` in `pipeline/hooks/test_dangerous_commands.py`: it saves `os.environ.get("PIPELINE_READONLY_ALLOW")`, sets that variable to `json.dumps(prefixes)`, calls `check(cmds, True, expect_block, label)`, and in a `finally` restores the saved value or pops the variable when it was unset.
4. Rewrite `tables()` in `pipeline/hooks/test_dangerous_commands.py`: make `saved = os.environ.pop("PIPELINE_READONLY_ALLOW", None)` the first statement, keep the six existing `check` and `check_mcp` calls, add `check_readonly_allow(ALLOWED_PROJECT, False, "project-allow")` and `check_readonly_allow(BLOCKED_PROJECT, True, "project-allow")` after them, put all eight inside a `try` whose `finally` restores `saved` when it is not `None`, and extend the docstring to say the pop is what keeps `BLOCKED_READONLY` honest when the stage running the suite already exports this repo's allowlist.
5. Add `test_a_malformed_readonly_allowlist_fails_closed()` to `pipeline/hooks/test_dangerous_commands.py` directly after `test_a_read_only_stage_runs_the_commands_its_project_allows()`: for each of the five strings `{not json`, `"pipeline ls"`, `[["pipeline", 1]]`, `[[]]` and `[["", "ls"]]`, set `PIPELINE_READONLY_ALLOW` to it, then assert `guard.readonly_prefixes() == []` and that `guard.verdict("pipeline ls", True)` is truthy, restoring the environment in a `finally`.
6. Add `test_the_project_allowlist_reaches_the_real_hook()` to `pipeline/hooks/test_dangerous_commands.py` below `test_end_to_end_exit_code()`: build `env = dict(os.environ, PIPELINE_READONLY="1", PIPELINE_STAGE="review", PIPELINE_READONLY_ALLOW=json.dumps([["pipeline", "ls"]]))`, run `[sys.executable, str(GUARD)]` on the event `{"tool_name": "Bash", "tool_input": {"command": "pipeline ls"}}` and assert `returncode == 0`, then on the same event carrying `pipeline approve TICKET-058` and assert `returncode == 2` and that ``Blocked by the pipeline guard (review): `pipeline` is not on the read-only allowlist`` is in `p.stderr`.
7. In the `__main__` block of `pipeline/hooks/test_dangerous_commands.py`, call `test_a_malformed_readonly_allowlist_fails_closed()` and `test_the_project_allowlist_reaches_the_real_hook()` immediately after `test_end_to_end_exit_code()`.
8. Update `test_the_rule_file_counts_the_guard_cases` in `tests/test_stages.py` to sum eight tables -- add `mod.ALLOWED_PROJECT` and `mod.BLOCKED_PROJECT` to the tuple -- and change the `## Commands` line in `CLAUDE.md` from `# 109 guard cases (table-driven)` to `# 122 guard cases (table-driven)`, which is 109 + 1 + 5 + 7.
9. Run `./pipeline/hooks/test_dangerous_commands.py` and watch it fail with ``AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)``, run `uv run --group dev pytest -q tests/test_stages.py` and expect it to pass, then commit `pipeline/hooks/test_dangerous_commands.py`, `tests/test_stages.py` and `CLAUDE.md` as `test(TICKET-058): cover the per-project read-only allowlist`.
10. Add the reader to `pipeline/hooks/dangerous-commands.py` above `readonly_rules()`: `READONLY_ALLOW_ENV = "PIPELINE_READONLY_ALLOW"` and `def readonly_prefixes() -> list[list[str]]`, which passes that variable (default `[]`) through `json.loads`, returns `[]` on `ValueError` or on a non-list, and otherwise keeps only entries that are non-empty lists whose every element is a non-empty `str` -- fail closed, with a docstring saying an empty entry would match every argv.
11. Apply the prefix rule in `readonly_rules()` in `pipeline/hooks/dangerous-commands.py`: bind `allow = readonly_prefixes()` above the `for argv in segs` loop, and inside the loop, immediately after `if not argv: continue` and before `name = os.path.basename(argv[0])`, add `if any(argv[:len(p)] == p for p in allow): continue` with a comment that `argv[0]` is compared verbatim and not by basename, so `./pipeline/hooks/test_dangerous_commands.py` matches as written.
12. Extend the module docstring of `pipeline/hooks/dangerous-commands.py`: state that the read-only allowlist has one per-project extension, `PIPELINE_READONLY_ALLOW`, an argv-prefix list the dispatcher exports from `[readonly] allow` in `.project/pipeline.toml`, that it is applied per segment inside `readonly_rules()` only, and that it can never re-enable anything `always_rules()` or the redirection and command-substitution checks refuse.
13. Run `uv run --group dev pytest -x pipeline/hooks/test_dangerous_commands.py` and then `./pipeline/hooks/test_dangerous_commands.py`, expect pytest to pass and the script to end with `guard: all passed`, then commit `pipeline/hooks/dangerous-commands.py` as `feat(TICKET-058): let a project name the commands a read-only stage may run`.
14. Add the failing config test to `tests/test_stages.py` next to `test_a_stage_only_gets_the_mcp_servers_it_declares`: `test_a_project_names_the_commands_a_read_only_stage_may_run()` makes `d = Path(tempfile.mkdtemp())` holding `.project/pipeline.toml` = `[readonly]` plus `allow = ["pipeline ls", "./run tests"]`, asserts `C.readonly_allow(d) == [["pipeline", "ls"], ["./run", "tests"]]`, rewrites that file as `test_one = "pytest"` and asserts `C.readonly_allow(d) == []`, asserts `C.readonly_allow(Path(tempfile.mkdtemp())) == []` for a directory with no `.project/pipeline.toml` at all, and then for each of `allow = "pipeline ls"`, `allow = [""]`, `allow = [3]` and `readonly = 3` rewrites the file and asserts the raise with `try: C.readonly_allow(d); assert False, "<case> must raise" except PipelineError: pass`, the style already used at `tests/test_stages.py:130-139`.
15. Run `uv run --group dev pytest -q tests/test_stages.py` and watch it fail with `AttributeError: module 'pipeline.core.config' has no attribute 'readonly_allow'`.
16. Add `readonly_allow(project: Path) -> list[list[str]]` to `pipeline/core/config.py` below `mcp_servers()`: call `project_config(project)` inside `try`/`except PipelineError: return []` -- the same catch `project_stage_config()` makes at lines 38-41, so a project with no `.project/pipeline.toml` gets no prefixes instead of an exception -- then read `cfg.get("readonly") or {}`, raise `PipelineError(f"{project}: [readonly] must be a table")` when it is not a dict, read `table.get("allow") or []`, raise `PipelineError(f"{project}: [readonly] allow must be a list")` when it is not a list, and for each entry raise unless it is a `str` that `shlex.split` accepts and that lexes to at least one token -- an empty entry would match every argv, so it raises rather than being skipped.
17. Give `readonly_allow()` in `pipeline/core/config.py` a docstring recording three facts a reader needs: it is read through `project_config()`, so the list comes from HEAD of the main checkout and a stage cannot widen its own allowlist (DEC-037); a project with no config yields `[]`, because `spawn()` calls this for every stage and `tests/test_pty.py` spawns into a bare temp directory; and the prefixes never override `always_rules()` or the redirection and command-substitution rules in the guard.
18. Run `uv run --group dev pytest -q tests/test_stages.py`, expect it to pass, then commit `pipeline/core/config.py` and `tests/test_stages.py` as `feat(TICKET-058): read [readonly] allow from the project config`.
19. Add the failing spawn test to `tests/test_harness.py` after `test_a_spawned_stage_carries_its_mcp_allowlist_in_the_environment`: `test_a_spawned_stage_carries_its_readonly_allowlist_in_the_environment()` writes `config.STAGES_DIR / "_roprobe.md"` with frontmatter `model: sonnet`, `write: false` and `hooks: [dangerous-commands]`, appends `[readonly]` plus `allow = ["pipeline ls"]` to the `helpers.project()` config, calls `supervisor.spawn(d, d, "TICKET-001", "_roprobe", {"cmd": "env > env.txt", "supports_hooks": True, "readonly_tools": "", "write_tools": "", "settings_flag": ""})`, waits on `rec["proc"]`, asserts `'PIPELINE_READONLY_ALLOW=[["pipeline", "ls"]]' in (d / "env.txt").read_text()`, and in a `finally` unlinks the stage file, `rec["prompt"]` and `rec["settings"]` and removes the temp project.
20. Run `uv run --group dev pytest -q tests/test_harness.py` and watch the new test fail on the missing `PIPELINE_READONLY_ALLOW=` line in `env.txt`.
21. Wire the environment in `pipeline/daemon/supervisor.py`: add `readonly_allow` to the `from pipeline.core.config import` list at line 17, add `allow = readonly_allow(project)` beside `servers = mcp_servers(project, cfg)` in `spawn()`, and set `env["PIPELINE_READONLY_ALLOW"] = json.dumps(allow)` next to the `PIPELINE_MCP_READONLY` line, with a comment that a broken `[readonly]` table surfaces here exactly as a broken `[mcp.<name>]` one does, while a project with no config at all yields `[]` and spawns as before.
22. Run `uv run --group dev pytest -q tests/test_harness.py tests/test_pty.py`, expect both to pass -- `tests/test_pty.py` is the regression the second plan broke, because it spawns into a `tempfile.mkdtemp()` that has no `.project/pipeline.toml` -- then commit `pipeline/daemon/supervisor.py` and `tests/test_harness.py` as `feat(TICKET-058): export the project read-only allowlist to every stage`.
23. Declare this repo's own list in `.project/pipeline.toml`: a `[readonly]` table with `allow = ["pipeline ls", "pipeline status", "pipeline plan", "pipeline projects", "pipeline metrics", "./pipeline/hooks/test_dangerous_commands.py"]`, and above it a comment saying every entry is an argv prefix, that `approve`, `reject`, `resume`, `answer`, `init`, `new`, `start`, `stop` and `run` are left out because they mutate state a review must not change, that `gate` is left out because it runs the project's test command, that `tui` is left out because it needs a terminal, and that `logs` is left out because `-f` blocks (read `.project/logs/` with `cat` instead).
24. Document the seam in `pipeline/templates/pipeline.toml` as a commented block after the `[mcp.docs]` example: the two lines `# [readonly]` and `# allow = ["mytool status", "mytool show"]`, plus three comment lines saying entries are argv prefixes matched per shell segment, that they never override the always-blocked commands or the redirection and command-substitution rules, and that this file is read from git HEAD so a stage cannot widen its own allowlist.
25. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect the pytest suite to pass and the guard to print `guard: all passed`, then commit `.project/pipeline.toml` and `pipeline/templates/pipeline.toml` as `feat(TICKET-058): declare this project's read-only command allowlist`.
26. Document the seam in `README.md` as a `## Read-only stage commands` section placed immediately before the `## MCP servers` heading at line 515: the `[readonly] allow` toml block, that entries are argv prefixes matched per shell segment, that the always-blocked set and the redirection rule still win, and that the list is read from HEAD while `.project/pipeline.toml` is fenced, so widening it is a human's commit.
27. Add one bullet to `CLAUDE.md` under `## Gotchas, each found the hard way` stating that the read-only allowlist has a per-project extension in `[readonly] allow`, exported as `PIPELINE_READONLY_ALLOW`, which never overrides `always_rules()` or the redirection rule, and that `tables()` pops the variable so `BLOCKED_READONLY` still means default deny; then run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py` and commit `README.md` and `CLAUDE.md` as `docs(TICKET-058): document the per-project read-only allowlist`.

## Acceptance criteria

- `uv run --group dev pytest -x pipeline/hooks/test_dangerous_commands.py` passes, so `test_a_read_only_stage_runs_the_commands_its_project_allows` is green -- that is the reproduction and it is what the Tier A gate runs.
- The whole table run in `pipeline/hooks/test_dangerous_commands.py` exits 0 and prints `guard: all passed`.
- The table run of `pipeline/hooks/test_dangerous_commands.py` prints `ok  BLOCK [readonly] pipeline status` even when the calling environment exports `PIPELINE_READONLY_ALLOW` as `[["pipeline", "status"]]` -- the pop in `tables()` is what makes this hold.
- With the project prefixes set, the table run of `pipeline/hooks/test_dangerous_commands.py` prints `ok  allow [project-allow] pipeline ls` and `ok  allow [project-allow] ./pipeline/hooks/test_dangerous_commands.py` (cases in `ALLOWED_PROJECT`).
- With the same prefixes set, the table run of `pipeline/hooks/test_dangerous_commands.py` prints `ok  BLOCK [project-allow] pipeline approve TICKET-058` and `ok  BLOCK [project-allow] sudo pipeline ls` (cases in `BLOCKED_PROJECT`).
- `test_a_malformed_readonly_allowlist_fails_closed` in `pipeline/hooks/test_dangerous_commands.py` passes: a malformed `PIPELINE_READONLY_ALLOW` yields no prefixes and still blocks `pipeline ls`.
- `test_the_project_allowlist_reaches_the_real_hook` in `pipeline/hooks/test_dangerous_commands.py` passes: the hook process exits 0 on `pipeline ls` and 2 on `pipeline approve TICKET-058`, with the quoted refusal text on stderr.
- `uv run --group dev pytest -q tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` passes with `CLAUDE.md` reading `# 122 guard cases (table-driven)`.
- `uv run --group dev pytest -q tests/test_stages.py::test_a_project_names_the_commands_a_read_only_stage_may_run` passes, including its assertion that `C.readonly_allow(d) == []` for a directory holding no `.project/pipeline.toml`.
- `uv run --group dev pytest -q tests/test_harness.py::test_a_spawned_stage_carries_its_readonly_allowlist_in_the_environment` passes.
- `uv run --group dev pytest -q tests/test_pty.py` passes, with
  `test_an_interactive_stage_runs_headless_when_nothing_can_attach` and
  `test_an_interactive_log_opens_with_its_geometry` green -- both spawn into a
  bare `tempfile.mkdtemp()` and are the regression the second plan broke.
- `uv run --group dev pytest -q` passes with no new failures.

## Decisions

**A project names read-only commands as argv PREFIXES, in `[readonly] allow` in `.project/pipeline.toml`, and the guard matches `argv[:len(prefix)] == prefix` per shell segment.** Not a regex, not a program-name set: `pipeline ls` must be allowed while `pipeline approve` stays refused, and only a prefix separates them. `readonly_allow()` in `pipeline/core/config.py` lexes each entry once with `shlex.split`, and `spawn()` exports the result as JSON in `PIPELINE_READONLY_ALLOW`; the guard never lexes an allow entry itself.

**Order is the safety property, not the matching.** `verdict()` runs `always_rules()` first, and `readonly_rules()` checks redirection and command substitution before its per-segment loop. The prefix check sits inside that loop, so a project entry can never re-enable `sudo`, `rm -rf /`, `git push --force`, `git worktree remove`, a redirection or a command substitution. Moving the prefix check above either of those turns this seam into a bypass.

**An empty allow entry raises; it is not skipped.** `argv[:0] == []` is true for every command, so `allow = [""]` would allow everything. `readonly_allow()` refuses it at config-read time and `readonly_prefixes()` in the guard drops it again -- both, because the guard must also be right about an environment it did not build.

**A project with no `.project/pipeline.toml` gets `[]`, not a `PipelineError`.** `readonly_allow()` catches the raise from `project_config()`, exactly as `project_stage_config()` does. `spawn()` calls it unconditionally, and a spawn into a directory that was never `pipeline init`-ed is a real case -- `tests/test_pty.py` does it four times. Failing closed here is also the safe direction: no config means no widening. Do not "harden" this into a raise; it would redden every such spawn.

**The guard fails closed on a malformed `PIPELINE_READONLY_ALLOW`.** Unparseable JSON, a non-list, or an entry that is not a non-empty list of non-empty strings yields no prefixes at all. The guard is the layer that makes a promise; it never widens on input it cannot read.

**`tables()` pops `PIPELINE_READONLY_ALLOW`, and that pop is load-bearing.** The guard's own suite runs inside stages that export this repo's allowlist, and `BLOCKED_READONLY` holds `pipeline status`, which `.project/pipeline.toml` allows. Without the pop the tables would assert against whatever environment happened to run them, so `readonly` would stop meaning default deny. Restore the saved value in the `finally`: `check_mcp()` snapshots the whole environment and would otherwise put the variable back mid-run.

**The list is project-scoped, not stage-scoped, unlike `mcp:`.** All four `write: false` stages want the same product commands, and a per-stage key would be a second place to look with no case behind it. Adding a `readonly:` frontmatter key later is additive and breaks no existing config.

**What makes it safe is provenance (DEC-037, DEC-038).** `project_config()` reads `.project/pipeline.toml` from HEAD of the main checkout, so a stage cannot widen its own allowlist even by committing one on its branch, and the file is in `machine.FENCED`, so such a commit parks at `awaiting-merge`. If the config ever starts being read off disk, this feature becomes a self-service bypass and must be removed with it.

**`pipeline logs`, `pipeline gate` and `pipeline tui` are deliberately absent from this repo's list.** `logs -f` blocks until the lease expires, `gate` runs the project's test command, and `tui` needs a terminal. A stage reads `.project/logs/` with `cat` and `grep`, which the built-in `READ_TOOLS` already allow.

**Adding a guard table means updating two more places, in the same commit.** `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` sums the tables by name and asserts `CLAUDE.md`'s `# <N> guard cases (table-driven)` line, so a new table that is not in that tuple is counted by nothing, and a new case that is not in `CLAUDE.md`'s number turns the test red (DEC-057). This ticket moved that number from 109 to 122.

## Rollback

Revert the six commits from steps 9, 13, 18, 22, 25 and 27, in reverse order; each is self-contained. Reverting steps 13 and 9 together restores the built-in-only read-only allowlist and is the fix if a read-only stage turns out to reach something it should not: `PIPELINE_READONLY_ALLOW` is then read by nothing, and a `[readonly]` table left in `.project/pipeline.toml` is an unread table `tomllib` ignores. Reverting step 13 alone leaves the guard's tables red, because they assert the prefix behaviour -- revert the pair. No state migrates and no ticket file changes shape. A running dispatcher picks the revert up only after a restart -- `_source_watcher()` stops the loop, then run `pipeline start` again.

## Thread

### 2026-08-26 15:27:52Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-26 · triage · reproduce

Reproduced: added `"pipeline status"` to `ALLOWED_READONLY` in
`pipeline/hooks/test_dangerous_commands.py`. Run fails with
`` `pipeline` is not on the read-only allowlist ``, matching the ticket.
Committed as `e19ee54`.

Root cause: `readonly_rules()` in `pipeline/hooks/dangerous-commands.py`
checks `READ_TOOLS`, `TEST_RUNNERS`, `GUARDED`, and `git`, but has no entry
for the project's own `pipeline` command, so every `write: false` stage is
blocked from running it.

Fix touches `pipeline/hooks/dangerous-commands.py`, which is in
`machine.FENCED` and requires human review before merge regardless of diff
size. Filing as `ok`, not `chore`.

test_file: `pipeline/hooks/test_dangerous_commands.py` (not pytest-collected;
run directly).

### 2026-08-26 15:29:00Z · triage · session · session=b8c4e235-6dc4-4ca7-91cf-97368d2aaf4a

`triage` ran as session `b8c4e235-6dc4-4ca7-91cf-97368d2aaf4a`
- replay: `claude --resume b8c4e235-6dc4-4ca7-91cf-97368d2aaf4a`
- log: `.project/logs/TICKET-058-triage-b8c4e235.log`

### 2026-08-26 15:29:00Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- readonly_rules() has no entry for `pipeline`, so a write:false stage cannot run the project's own CLI; failing case committed in test_dangerous_commands.py (e19ee54)

### 2026-08-26 · planning · plan

Scope: one subsystem -- the guard's read-only allowlist plus the config seam
that feeds it. Planned whole; no split needed.

Finding, out of scope, measured: `GUARDED` already allows `uv run <anything>`,
`poetry run <anything>` and `npm run <anything>` in a read-only stage. Probe
against `verdict(cmd, readonly=True)`:

    'uv run pipeline approve TICKET-058' -> None
    "uv run python -c 'print(1)'"        -> None
    'poetry run anything'                -> None

So a `write: false` stage can already reach the whole command surface, and
`python3 -c` with it, by prefixing `uv run`. The ticket scopes the built-in
entries out, so this plan does not touch them, and the new seam is still the
named, auditable route. File a separate ticket to narrow `uv run`,
`poetry run` and `npm run` to a vetted second argument; until then the
read-only promise is weaker than the allowlist reads.

Plan change to the reproduction case: `"pipeline status"` moves from
`ALLOWED_READONLY` to `BLOCKED_READONLY`. With no project list the guard must
still refuse it -- default deny is the property -- so the allow case moves to a
new env-scoped table.

### 2026-08-26 16:47:07Z · planning · session · session=b6f03c25-e69d-4dfd-a2de-707c50fa2542

`planning` ran as session `b6f03c25-e69d-4dfd-a2de-707c50fa2542`
- replay: `claude --resume b6f03c25-e69d-4dfd-a2de-707c50fa2542`
- log: `.project/logs/TICKET-058-planning-b6f03c25.log`

### 2026-08-26 16:47:07Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned the per-project read-only seam: [readonly] allow in .project/pipeline.toml -> readonly_allow() -> PIPELINE_READONLY_ALLOW -> argv-prefix match in readonly_rules(); 25 steps, 10 files

### 2026-08-26 16:47:23Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `pipeline/hooks/test_dangerous_commands.py` PASSES -- it must fail before implementation
- ok: DEC-041 is superseded -- history, not binding
- plan step names no declared file: "5. Run `./pipeline/hooks/test_dangerous_commands.py` and watch it fail at the first `ALLOWED_PROJECT` case with `AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)`." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- acceptance criterion names no test: - With `PIPELINE_READONLY_ALLOW` unset, `pipeline status` is refused: the guard run prints `ok  BLOCK [readonly] pipeline status` (case in `BLOCKED_READONLY`).
- acceptance criterion names no test: - With the same prefixes set, the guard run prints `ok  BLOCK [project-allow] pipeline approve TICKET-058` and `ok  BLOCK [project-allow] sudo pipeline ls` (cases in `BLOCKED_PROJECT`).
- acceptance criterion names no test: - Step 22's two hook invocations exit 0 and 2 respectively, the second printing the quoted refusal text.

### 2026-08-26 16:47:23Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- `pipeline/hooks/test_dangerous_commands.py` PASSES -- it must fail before implementation
- plan step names no declared file: "5. Run `./pipeline/hooks/test_dangerous_commands.py` and watch it fail at the first `ALLOWED_PROJECT` case with `AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)`." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- acceptance criterion names no test: - With `PIPELINE_READONLY_ALLOW` unset, `pipeline status` is refused: the guard run prints `ok  BLOCK [readonly] pipeline status` (case in `BLOCKED_READONLY`).
- acceptance criterion names no test: - With the same prefixes set, the guard run prints `ok  BLOCK [project-allow] pipeline approve TICKET-058` and `ok  BLOCK [project-allow] sudo pipeline ls` (cases in `BLOCKED_PROJECT`).
- acceptance criterion names no test: - Step 22's two hook invocations exit 0 and 2 respectively, the second printing the quoted refusal text.

### 2026-08-27 · planning · plan

long: four gate findings, each needing its root cause and the measured output that shows it fixed.

Replanned after the Tier A FAIL at 16:47:23Z. Four findings, four fixes.

1. "`pipeline/hooks/test_dangerous_commands.py` PASSES". Root cause: `test_one`
   is `uv run --group dev pytest -x {test}`, and pytest collects only the
   `test_*` functions in that file. Triage filed the reproduction as an entry
   in the `ALLOWED_READONLY` table, which only `__main__` reads, so the gate
   ran a green file. Fixed in commit `9a5cacc`: `"pipeline status"` moved to
   `BLOCKED_READONLY` (default deny), and the reproduction is now the
   pytest-collected `test_a_read_only_stage_runs_the_commands_its_project_allows`,
   placed first in the file so `-x` reaches it. Measured:

       uv run --group dev pytest -x pipeline/hooks/test_dangerous_commands.py
       E  AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)
       1 failed in 0.02s

       uv run --group dev pytest --deselect pipeline/hooks/test_dangerous_commands.py -q
       306 passed, 6 deselected in 13.83s

2. "plan step names no declared file" on step 5. The step named the script only
   as `./pipeline/hooks/test_dangerous_commands.py`; `_cites()` refuses a match
   preceded by `/`. Step 5 now names the bare path too. Steps 9, 21 and 25 got
   the same treatment.

3, 4. Three acceptance criteria named no test. Each now names
   `pipeline/hooks/test_dangerous_commands.py` or a `test_*` function, and every
   criterion is one unwrapped line.

Design unchanged: `[readonly] allow` -> `readonly_allow()` ->
`PIPELINE_READONLY_ALLOW` -> argv-prefix match inside `readonly_rules()`. Still
25 steps, 10 files. The `uv run <anything>` finding in the earlier planning
entry stands and is still out of scope.

### 2026-08-26 17:01:06Z · planning · session · session=428413a4-2054-4b83-b941-786cf27bb37c

`planning` ran as session `428413a4-2054-4b83-b941-786cf27bb37c`
- replay: `claude --resume 428413a4-2054-4b83-b941-786cf27bb37c`
- log: `.project/logs/TICKET-058-planning-428413a4.log`

### 2026-08-26 17:01:06Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned after the Tier A FAIL: reproduction refiled as a pytest-collected test (9a5cacc), step 5 spells out a declared path, every acceptance criterion names a test; design unchanged, 25 steps, 10 files

### 2026-08-26 17:01:21Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py` fails as required
```
ot defeat the redirection rule.
    
        This is the pytest-collected reproduction: `test_one` runs this file
        through pytest, which never reaches the tables under `__main__`.
        """
        saved = os.environ.get("PIPELINE_READONLY_ALLOW")
        os.environ["PIPELINE_READONLY_ALLOW"] = json.dumps(
            [["pipeline", "ls"], ["pipeline", "status"]])
        try:
            for c in ("pipeline ls", "pipeline status"):
                got = guard.verdict(c, True)
>               assert got is None, f"project-allow: {c!r} -> {got!r} (expected allow)"
E               AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)
E               assert '`pipeline` is not on the read-only allowlist' is None

pipeline/hooks/test_dangerous_commands.py:120: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.01s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py` fails on base `main` too -- the bug is not already fixed upstream
```
 {c!r} -> {got!r} (expected allow)"
E               AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)
E               assert '`pipeline` is not on the read-only allowlist' is None

pipeline/hooks/test_dangerous_commands.py:120: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-h8384trh/base
      Built pipeline @ file:///tmp/pipeline-base-h8384trh/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```
- ok: DEC-041 is superseded -- history, not binding

### 2026-08-27 · plan-validation · judgement

**Judgement: PASS.** Eight items, each with its evidence.

1. Root cause. `readonly_rules()` default-denies: line 220 returns
   ``f"`{name}` is not on the read-only allowlist"`` for any name outside
   `READ_TOOLS`, `TEST_RUNNERS` and `GUARDED`. `pipeline` is in none, and the
   guard has no per-project extension point. The plan adds that extension
   point. Adding `pipeline` to a built-in table would fix the symptom and
   allow `pipeline approve` with it.
2. Decisions. DEC-036, DEC-037, DEC-038 and DEC-050 constrain this plan and it
   complies. Verified: `project_config()` reads HEAD (`config.py:88`), and
   `machine.FENCED` holds `.project/pipeline.toml` (`machine.py:33`).
3. Scope. Steps 20, 23 and 24 are documentation, required by `CLAUDE.md`. Step
   19 declares this repo's own table and no criterion covers it -- see the gap
   below.
4. Falsifiable. Step 3's `"[[]]"` case fails a reader that keeps an empty
   entry, because `argv[:0] == []` matches every command. `BLOCKED_PROJECT`
   holds `pipeline approve TICKET-058`, which a program-name fix would allow.
5. No research left. Every anchor exists: `check_mcp()` line 88 and
   `ALLOWED_READONLY` line 59 in `pipeline/hooks/test_dangerous_commands.py`,
   `mcp_servers()` at `config.py:107`, the env block at `supervisor.py:395-406`
   with `json` imported at line 4, `shlex` at `config.py:9`,
   `test_a_stage_only_gets_the_mcp_servers_it_declares` at `test_stages.py:109`,
   `test_a_spawned_stage_carries_its_mcp_allowlist_in_the_environment` at
   `test_harness.py:357`.
6. Riskiest step: 7, the prefix check inside `readonly_rules()`. Placement is
   correct: redirection at line 186, `$(`/backtick at 188, loop at 191,
   `if not argv: continue` at 192. Fallback stated: revert step 9's commit
   alone.
7. Regression surface. The guard tables inherit the environment, and
   `BLOCKED_READONLY` holds `"pipeline status"` (line 57), which step 19's
   table allows -- a table run inside a stage would fail. Step 4's
   `os.environ.pop("PIPELINE_READONLY_ALLOW", None)` covers it. Nothing under
   `tests/` runs the guard tables (grepped). `spawn()` gains a raise path for a
   broken `[readonly]` table; the spawn tests use `helpers.project()`, whose
   config has no such table.
8. Blast radius. `class: feature`, 10 files: 3 source, 3 test, 2 config,
   2 docs. Matches the class.

Two facts for `implementing` and `review`, neither blocking.

- No criterion checks step 19's own table. A malformed entry there raises
  `PipelineError` in every `spawn()` for this repo. `.project/pipeline.toml`
  is fenced, so a human reads it before merge; that is the only check.
- The prefix check sits above the `git` branch of the loop, so an entry like
  `git push` would skip `GIT_READ`. `always_rules()` still refuses `--force`
  and a push to `main`. This repo declares no `git` prefix.

### 2026-08-26 17:04:36Z · plan-validation · session · session=f0e3f82c-a53b-4be3-8875-50dcfa6261b0

`plan-validation` ran as session `f0e3f82c-a53b-4be3-8875-50dcfa6261b0`
- replay: `claude --resume f0e3f82c-a53b-4be3-8875-50dcfa6261b0`
- log: `.project/logs/TICKET-058-plan-validation-f0e3f82c.log`

### 2026-08-26 17:04:36Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight judgement items; noted two non-blocking facts: step 4's env pop is load-bearing, and no criterion checks step 19's own [readonly] table

### 2026-08-26 17:28:08Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-26 17:46:08Z · revalidating · transition · to=triage · result=conflict

**revalidating -> triage** (result: `conflict`)

rebase onto base conflicted; branch recut from base:
```
$ git rebase main

Rebasing (1/2)
Auto-merging pipeline/hooks/test_dangerous_commands.py
CONFLICT (content): Merge conflict in pipeline/hooks/test_dangerous_commands.py
error: could not apply e19ee54... test(TICKET-058): reproduce read-only guard blocking the pipeline CLI
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply e19ee54... # test(TICKET-058): reproduce read-only guard blocking the pipeline CLI

9a5cacc test(TICKET-058): make the read-only reproduction pytest-collected
e19ee54 test(TICKET-058): reproduce read-only guard blocking the pipeline CLI
HEAD is now at fe2ae93 chore(TICKET-057): record the finished ticket

```

### 2026-08-27 · triage · reproduce

Re-triaged after the rebase conflict recut `ticket/058` from `main` (`fe2ae93`),
which dropped both prior reproduction commits (`e19ee54`, `9a5cacc`). Refiled
the pytest-collected reproduction directly, since the code under test is
unchanged from the second planning pass: added
`test_a_read_only_stage_runs_the_commands_its_project_allows` to
`pipeline/hooks/test_dangerous_commands.py`, ran it, confirmed the failure
text matches the ticket's recorded reproduction verbatim, and committed as
`67ee105` on `ticket/058`.

Command: `uv run --group dev pytest -x pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows`

Output:
```
E               AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)
E               assert '`pipeline` is not on the read-only allowlist' is None
```

expect: `pipeline` is not on the read-only allowlist

No code change was needed beyond the test: `readonly_rules()` in
`pipeline/hooks/dangerous-commands.py` still has no `pipeline` entry and no
`PIPELINE_READONLY_ALLOW` reader, matching the plan's premise unchanged.

### 2026-08-26 17:47:09Z · triage · session · session=b6831c4e-ab77-4e0a-846e-a237b627e797

`triage` ran as session `b6831c4e-ab77-4e0a-846e-a237b627e797`
- replay: `claude --resume b6831c4e-ab77-4e0a-846e-a237b627e797`
- log: `.project/logs/TICKET-058-triage-b6831c4e.log`

### 2026-08-26 17:47:09Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Recut branch dropped the reproduction; refiled it as commit 67ee105, same failure text as before.

### 2026-08-26 18:27:47Z · planning · note

`planning` was interrupted; lease released

### 2026-08-27 · planning · plan

Replanned on `67ee105`. The 17:46:08Z rebase conflict recut `ticket/058` from
`main` at `fe2ae93`, which brought TICKET-057 and DEC-057 onto the branch. Two
premises of the approved plan are now false, so this is a rewrite, not a
re-approval of the same steps.

1. `tables()` exists and `test_the_allow_and_block_tables()` calls it, so
   pytest runs every table case. The approved plan put its new
   `check_readonly_allow()` calls in `__main__`; DEC-057 forbids that. They
   move into `tables()`.
2. `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` asserts
   `CLAUDE.md` names the exact table-case count. Measured: 109 today. This
   plan adds 13 cases and moves the number to 122 in the same commit, and adds
   the two new tables to that test's sum.
3. The approved plan's criterion cited `pipeline status` as an existing
   `BLOCKED_READONLY` case. It is not in that table on `67ee105`. Step 1 adds
   it, and step 4's pop is what keeps it blocked once this repo declares the
   same command.
4. The approved plan's step 22 was a manual two-command check. It is now
   `test_the_project_allowlist_reaches_the_real_hook`, a pytest test.

Scope: one subsystem, the read-only guard seam. The `uv run <anything>` hole
DEC-057 records is measured again here and left alone -- it needs its own
ticket against the same fenced file.

Guard note for the next stage: this stage could not write the ticket through a
Bash heredoc. `verdict()` refuses a command carrying a backslash, and refuses
prose containing an apostrophe as unlexable. The plan text was written with
the `Write` tool into the worktree and assembled with quote-free `head`,
`cat` and `tail`.

### 2026-08-26 18:38:10Z · planning · session · session=f460f148-c90a-458a-aa18-0409b7d8f894

`planning` ran as session `f460f148-c90a-458a-aa18-0409b7d8f894`
- replay: `claude --resume f460f148-c90a-458a-aa18-0409b7d8f894`
- log: `.project/logs/TICKET-058-planning-f460f148.log`

### 2026-08-26 18:38:10Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned on 67ee105: 27 steps, 10 files; the recut brought DEC-057, so the new guard cases go in tables() and CLAUDE.md's count moves 109 to 122

### 2026-08-26 18:38:25Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows` fails as required
```
ot defeat the redirection rule.
    
        This is the pytest-collected reproduction: `test_one` runs this file
        through pytest, which never reaches the tables under `__main__`.
        """
        saved = os.environ.get("PIPELINE_READONLY_ALLOW")
        os.environ["PIPELINE_READONLY_ALLOW"] = json.dumps(
            [["pipeline", "ls"], ["pipeline", "status"]])
        try:
            for c in ("pipeline ls", "pipeline status"):
                got = guard.verdict(c, True)
>               assert got is None, f"project-allow: {c!r} -> {got!r} (expected allow)"
E               AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)
E               assert '`pipeline` is not on the read-only allowlist' is None

pipeline/hooks/test_dangerous_commands.py:158: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.01s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows` fails on base `main` too -- the bug is not already fixed upstream
```
{c!r} -> {got!r} (expected allow)"
E               AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)
E               assert '`pipeline` is not on the read-only allowlist' is None

pipeline/hooks/test_dangerous_commands.py:158: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-vhwjshje/base
      Built pipeline @ file:///tmp/pipeline-base-vhwjshje/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- ok: DEC-041 is superseded -- history, not binding

### 2026-08-27 · plan-validation · review

**Verdict: fail.** One item fails: regression surface. Nine pass.

Root cause: `readonly_rules()` in `pipeline/hooks/dangerous-commands.py` holds
one fixed allowlist compiled into the guard, so a project cannot name its own
read-only commands. The plan adds the missing seam, not a `pipeline` entry.
That fixes why the test fails.

FAIL -- regression surface. Step 21 puts `allow = readonly_allow(project)` in
`spawn()` beside `servers = mcp_servers(project, cfg)`
(`pipeline/daemon/supervisor.py:380`). Step 16 makes `readonly_allow()` call
`project_config()`, which raises when a project has no
`.project/pipeline.toml`:

```
raise PipelineError(f"no {cfg} -- run `pipeline init {project}` first")
```

`pipeline/core/config.py:92`. Today `spawn()` never reads the config for a
project that has none: `mcp_servers()` returns `{}` at line 117 before
`project_config()`, and `project_stage_config()` catches `PipelineError`.
Four spawns in `tests/test_pty.py` pass a bare `tempfile.mkdtemp()` -- lines
412, 419, 438 and 444, in
`test_an_interactive_stage_runs_headless_when_nothing_can_attach` and
`test_an_interactive_log_opens_with_its_geometry`. `head_file()` returns
`None` there (not a repo) and the disk fallback finds no file, so step 21
turns both tests red. No plan step covers this and no criterion names it.

Pass, with reasoning:

1. Decision conflict: none. DEC-036 (allowlist, default deny), DEC-037 (read
   from HEAD), DEC-038 (provenance), DEC-050 and DEC-057 all constrain this
   plan and it complies. DEC-057 forbids a new import in
   `pipeline/hooks/test_dangerous_commands.py`; steps 3, 5 and 6 use `json`,
   `os`, `subprocess` and `sys`, all on line 3 already.
2. Scope discipline: every step traces to a criterion except step 23, which
   declares this repo's own list. See the note below.
3. Falsifiable criteria: yes. Drop the prefix check and
   `test_a_read_only_stage_runs_the_commands_its_project_allows` stays red.
   Place it above the redirection check and `pipeline ls > out.txt` in
   `BLOCKED_PROJECT` goes red. Drop the pop in `tables()` and
   `pipeline status` in `BLOCKED_READONLY` goes red.
4. No research left: every step names a file and a function.
5. Blast radius: 10 files, 27 steps, class `feature`. Proportionate.
6. Arithmetic: the six tables hold 33+17+32+21+4+2 = 109 and `CLAUDE.md:95`
   says 109. The plan adds 1 + 5 + 7 = 13 cases and two tables, so 122 and an
   eight-table sum in `tests/test_stages.py:313` are both right.
7. Riskiest step: 11, the prefix check inside the loop in `readonly_rules()`.
   The plan states the fallback -- revert steps 13 and 9 as a pair (Rollback).
   The placement is safe: lines 233-236 check redirection and command
   substitution before the loop, and `always_rules()` runs first in
   `verdict()` at line 284.

Note, not blocking: no criterion covers step 23. Nothing asserts
`.project/pipeline.toml` gains `[readonly] allow`, which is the change that
makes `pipeline ls` work in this repo. A criterion that greps the committed
file for `pipeline ls` would close it. `project_config()` reads the main
checkout HEAD, so a test through `readonly_allow()` cannot see the branch.

Anchor for the fix: give `readonly_allow()` the `project_stage_config()`
shape -- catch `PipelineError` from `project_config()` and return `[]` -- or
skip the call in `spawn()` when the config is missing. Either is one step.

### 2026-08-26 18:42:07Z · plan-validation · session · session=56701e94-6d3e-41c7-ba02-de52589f4baa

`plan-validation` ran as session `56701e94-6d3e-41c7-ba02-de52589f4baa`
- replay: `claude --resume 56701e94-6d3e-41c7-ba02-de52589f4baa`
- log: `.project/logs/TICKET-058-plan-validation-56701e94.log`

### 2026-08-26 18:42:07Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ plan fails on regression surface: step 21 calls readonly_allow() unconditionally in spawn(), which raises for a project with no .project/pipeline.toml and reddens four tests/test_pty.py spawns; nine items pass

### 2026-08-27 · planning · plan

Replanned on `67ee105`. Plan-validation rejected the previous plan on one item,
regression surface. This rewrite addresses that item; the nine items that passed
keep their steps unchanged.

The finding: step 21 calls `readonly_allow(project)` unconditionally in
`spawn()`, `readonly_allow()` reads `project_config()`, and that raises
`PipelineError` for a project with no `.project/pipeline.toml`.
`tests/test_pty.py` spawns into a bare `tempfile.mkdtemp()` at lines 412, 419,
438 and 444.

Three changes:

1. Step 16: `readonly_allow()` catches `PipelineError` from `project_config()`
   and returns `[]` -- the same catch `project_stage_config()` makes at
   `pipeline/core/config.py:38-41`. No config means no widening, so this fails
   closed rather than open.
2. Step 14 asserts `C.readonly_allow(Path(tempfile.mkdtemp())) == []` and step
   17 puts the reason in the docstring. A new `## Decisions` paragraph records
   it, so a later change does not turn it back into a raise.
3. Step 22 runs `tests/test_pty.py` next to `tests/test_harness.py`, and a new
   criterion names both `tests/test_pty.py` tests by name.

Still 27 steps, 10 files, 109 -> 122 guard cases.

### 2026-08-26 18:46:40Z · planning · session · session=65b39eb5-d3d0-47eb-9d4f-8a3d6f197c59

`planning` ran as session `65b39eb5-d3d0-47eb-9d4f-8a3d6f197c59`
- replay: `claude --resume 65b39eb5-d3d0-47eb-9d4f-8a3d6f197c59`
- log: `.project/logs/TICKET-058-planning-65b39eb5.log`

### 2026-08-26 18:46:40Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned on 67ee105: readonly_allow() now catches PipelineError from project_config() and returns [], so spawn() into a project with no .project/pipeline.toml keeps tests/test_pty.py green; 27 steps, 10 files

### 2026-08-26 18:46:55Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-26 18:38:25Z · plan-validation · gate · verdict=PASS` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows` fails on base `main` too -- the bug is not already fixed upstream
```
{c!r} -> {got!r} (expected allow)"
E               AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)
E               assert '`pipeline` is not on the read-only allowlist' is None

pipeline/hooks/test_dangerous_commands.py:158: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-tho_cx_9/base
      Built pipeline @ file:///tmp/pipeline-base-tho_cx_9/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- ok: DEC-041 is superseded -- history, not binding

### 2026-08-27 · plan-validation · review

**Verdict: pass.** All ten items pass. The regression finding that rejected the
second plan is fixed and covered.

long: ten items, each carries its own evidence.

Root cause: `readonly_rules()` (`pipeline/hooks/dangerous-commands.py:231`)
holds one allowlist compiled into the guard -- `READ_TOOLS`, `GUARDED`,
`TEST_RUNNERS`, `GIT_READ`. A project cannot name its own read-only commands,
so the fall-through at line 271 returns "`pipeline` is not on the read-only
allowlist". The plan adds the missing seam; it does not add a `pipeline` entry.

1. Regression surface, the item that failed last time: fixed. Step 16 catches
   `PipelineError` from `project_config()` and returns `[]`, the catch
   `project_stage_config()` makes at `pipeline/core/config.py:38-41`. Step 14
   asserts it, step 22 runs `tests/test_pty.py`, and a criterion names both
   affected tests. I confirmed the four bare-`mkdtemp` spawns at
   `tests/test_pty.py:412`, `419`, `438` and `444`.
2. Decision conflict: none. DEC-036, DEC-037, DEC-038, DEC-050 and DEC-057
   constrain this plan and it complies. DEC-057 forbids a new import in
   `pipeline/hooks/test_dangerous_commands.py`; steps 3, 5 and 6 use `json`,
   `os`, `subprocess` and `sys`, all on line 3 already.
3. Falsifiable criteria: yes. Drop the prefix check and
   `test_a_read_only_stage_runs_the_commands_its_project_allows` stays red.
   Drop the pop in `tables()` and `ok  BLOCK [readonly] pipeline status` fails
   once a stage exports this repo's list. Widen `readonly_prefixes()` to accept
   `[[]]` and `test_a_malformed_readonly_allowlist_fails_closed` fails.
4. No research left: every step names a file and a symbol. I checked each
   anchor: `spawn()` at `pipeline/daemon/supervisor.py:329`,
   `mcp_servers(project, cfg)` at line 380, `PIPELINE_MCP_ALLOW` at line 404,
   the config import list at line 17; `check_mcp()` at
   `pipeline/hooks/test_dangerous_commands.py:115`, `tables()` at line 130,
   `test_end_to_end_exit_code()` at line 198, `__main__` at line 307;
   `## MCP servers` at `README.md:515`; the raise style at
   `tests/test_stages.py:128-139`, with `PipelineError` imported at line 11 and
   `tempfile` at line 6.
5. Counts: I ran the six tables and got `total 109`, matching `CLAUDE.md:95`
   `# 109 guard cases (table-driven)`. The plan adds 1 + 5 + 7 = 13, so 122 is
   right. `test_the_rule_file_counts_the_guard_cases`
   (`tests/test_stages.py:313-318`) asserts `claimed == [str(cases)]`, so the
   file must hold exactly one `# <N> guard cases (table-driven)` line. Step
   27's gotcha bullet must not add a second one.
6. Blast radius matches class: `feature`, 27 steps, 10 files -- 4 source, 3
   test, 3 docs and config. Proportionate for a seam crossing config,
   supervisor and guard.
7. Riskiest step: step 11, the prefix check inside `readonly_rules()`. It is
   the only step that can widen the guard. The fallback is stated: `## Rollback`
   names reverting steps 13 and 9 as a pair, and says why reverting 13 alone
   leaves the tables red. Placement is safe -- lines 232-236 run the redirection
   and command-substitution checks before the `for argv in segs` loop, and
   `verdict()` (line 284) runs `always_rules()` first.
8. Scope discipline: steps 1-22 trace to criteria. Steps 23-27 have no criteria
   of their own; they declare this repo's list and document the seam. Step 23 is
   what makes the feature reach this repo, and step 27's `CLAUDE.md` edit is
   covered by criterion 8. I pass this as a documentation tail, the call the
   second review also made.
9. Prefix semantics: I traced every `BLOCKED_PROJECT` case against step 11.
   `pipeline` alone and `pipelines ls` match no prefix; `pipeline ls > out.txt`
   hits the redirection check at line 233; `sudo pipeline ls` hits
   `always_rules()`; `pipeline ls && git commit -am wip` hits the `git` branch
   at line 244. Each blocks for the reason the plan claims.
10. Config validation: `readonly = 3`, `allow = "pipeline ls"`, `allow = [""]`
    and `allow = [3]` each hit a distinct raise in step 16. `shlex.split("")`
    returns `[]`, so the empty entry raises rather than matching every argv.

No item to fix. This plan is ready to implement.

### 2026-08-26 18:50:39Z · plan-validation · session · session=89445122-fa6b-4197-8991-85e00515d7ed

`plan-validation` ran as session `89445122-fa6b-4197-8991-85e00515d7ed`
- replay: `claude --resume 89445122-fa6b-4197-8991-85e00515d7ed`
- log: `.project/logs/TICKET-058-plan-validation-89445122.log`

### 2026-08-26 18:50:39Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all ten items: root cause is the guard's compiled-in allowlist, the regression that failed the second plan is fixed by step 16's PipelineError catch, and the 109 -> 122 case count is measured

### 2026-08-26 18:51:12Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-26 18:55:01Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-26 18:38:25Z · plan-validation · gate · verdict=PASS` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows` fails on base `main` too -- the bug is not already fixed upstream
```
 {c!r} -> {got!r} (expected allow)"
E               AssertionError: project-allow: 'pipeline ls' -> '`pipeline` is not on the read-only allowlist' (expected allow)
E               assert '`pipeline` is not on the read-only allowlist' is None

pipeline/hooks/test_dangerous_commands.py:158: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-e2ggbhqy/base
      Built pipeline @ file:///tmp/pipeline-base-e2ggbhqy/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```
- ok: DEC-041 is superseded -- history, not binding

### 2026-08-26 18:55:01Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-27 · implementing · todo

**Todo list, one entry per plan step.**

- [ ] 1. `BLOCKED_READONLY` += `pipeline status`
- [ ] 2. add `PROJECT_PREFIXES`, `ALLOWED_PROJECT`, `BLOCKED_PROJECT`
- [ ] 3. add `check_readonly_allow()`
- [ ] 4. rewrite `tables()` to pop/restore env and call the new checks
- [ ] 5. add `test_a_malformed_readonly_allowlist_fails_closed`
- [ ] 6. add `test_the_project_allowlist_reaches_the_real_hook`
- [ ] 7. wire both new tests into `__main__`
- [ ] 8. `test_the_rule_file_counts_the_guard_cases` += 2 tables; `CLAUDE.md` 109->122
- [ ] 9. verify RED, run `tests/test_stages.py`, commit test file
- [ ] 10. add `readonly_prefixes()` + `READONLY_ALLOW_ENV` to guard
- [ ] 11. apply prefix rule in `readonly_rules()`
- [ ] 12. extend guard module docstring
- [ ] 13. verify GREEN, commit guard
- [ ] 14. add `test_a_project_names_the_commands_a_read_only_stage_may_run`
- [ ] 15. verify RED (AttributeError)
- [ ] 16. add `readonly_allow()` to `pipeline/core/config.py`
- [ ] 17. docstring for `readonly_allow()`
- [ ] 18. verify GREEN, commit config.py + test_stages.py
- [ ] 19. add `test_a_spawned_stage_carries_its_readonly_allowlist_in_the_environment`
- [ ] 20. verify RED
- [ ] 21. wire `PIPELINE_READONLY_ALLOW` into `spawn()`
- [ ] 22. verify GREEN incl. `tests/test_pty.py`, commit supervisor.py + test_harness.py
- [ ] 23. declare this repo's own `[readonly] allow` in `.project/pipeline.toml`
- [ ] 24. document seam in `pipeline/templates/pipeline.toml`
- [ ] 25. verify, commit both config files
- [ ] 26. document seam in `README.md`
- [ ] 27. add `CLAUDE.md` gotcha bullet, verify, commit docs

### 2026-08-27 · implementing · report

**All 27 steps done, TDD throughout, 6 commits.**

Reproduction test passes:
`pipeline/hooks/test_dangerous_commands.py::test_a_read_only_stage_runs_the_commands_its_project_allows`.
`uv run --group dev pytest -q` -- 320 passed. `./pipeline/hooks/test_dangerous_commands.py`
prints `guard: all passed`. `tests/test_pty.py` passes -- the regression that
failed the second plan. `CLAUDE.md` carries exactly one
`# 122 guard cases (table-driven)` line, confirmed by grep before commit.

Every new function (`readonly_prefixes()`, `readonly_allow()`) had its test
written and run RED before the implementation, then GREEN after. No test was
edited for behaviour reasons; `BLOCKED_READONLY` gained one case
(`pipeline status`) and `tables()` was rewritten to pop/restore
`PIPELINE_READONLY_ALLOW`, both named in the plan.

Commits: `299160a` test, `e180550` guard, `a25e09c` config, `733d6f8` spawn,
`6ec9ae9` project declaration, `be6bd84` docs.

### 2026-08-26 19:00:39Z · implementing · session · session=19af9224-4267-47ec-b712-a9f98d8be9d8

`implementing` ran as session `19af9224-4267-47ec-b712-a9f98d8be9d8`
- replay: `claude --resume 19af9224-4267-47ec-b712-a9f98d8be9d8`
- log: `.project/logs/TICKET-058-implementing-19af9224.log`

### 2026-08-26 19:00:39Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ executed all 27 plan steps via TDD, 6 commits; reproduction test and full suite (320) pass, guard prints all passed

### 2026-08-27 · review · findings

**No blocking findings.** Reviewed `main...HEAD` -- 7 commits, 10 files.

long: the acceptance criteria name eleven checks; each needs its own evidence.

Verified:
- `uv run --group dev pytest -q` -- `320 passed in 13.61s`. `tests/test_pty.py` -- `16 passed`.
- The guard script prints `guard: all passed` and all five required lines: `ok  BLOCK [readonly] pipeline status`, `ok  allow [project-allow] pipeline ls`, `ok  allow [project-allow] ./pipeline/hooks/test_dangerous_commands.py`, `ok  BLOCK [project-allow] pipeline approve TICKET-058`, `ok  BLOCK [project-allow] sudo pipeline ls`.
- The pop in `tables()` is load-bearing and holds. With `PIPELINE_READONLY_ALLOW=[["pipeline", "status"]]` exported, `tables()` still printed `ok  BLOCK [readonly] pipeline status`, and the `finally` restored `ENV AFTER: [["pipeline", "status"]]`.
- Every command in this repo's `[readonly] allow` is read-only. `cmd_plan` prints two sections (`pipeline/cli/main.py:98`); `metrics.connect()` refuses a missing db instead of creating it (`pipeline/cli/metrics.py:75`).

Dropped one candidate finding. Running `./pipeline/hooks/test_dangerous_commands.py` from a read-only stage writes nothing in the repo: its only writes are `os.makedirs` under `tempfile.mkdtemp()` (lines 301, 302, 343, 344), and the Write-tool cases feed JSON to the guard subprocess, which only decides (line 288).

Nits, not blocking:
1. Nit: the docstring of `test_a_read_only_stage_runs_the_commands_its_project_allows` still reads `Not yet implemented`; the test is green.
2. Nit: `cfg.get("readonly") or {}` and `table.get("allow") or []` in `pipeline/core/config.py` read a falsy value as absent, so `readonly = 0` returns `[]` while `readonly = 3` raises. Both fail closed.
3. Nit: `spawn()` calls `readonly_allow()` for every stage, one `git show` per spawn even when `write: true`.

### 2026-08-26 19:05:35Z · review · session · session=49632b57-48c5-494e-bcde-1de33441bd7c

`review` ran as session `49632b57-48c5-494e-bcde-1de33441bd7c`
- replay: `claude --resume 49632b57-48c5-494e-bcde-1de33441bd7c`
- log: `.project/logs/TICKET-058-review-49632b57.log`

### 2026-08-26 19:05:35Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed 7 commits, 10 files: no blocking findings; 320 pytest pass, guard prints all passed, three nits recorded

### 2026-08-26 19:05:50Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `.project/pipeline.toml`
- `pipeline/hooks/dangerous-commands.py`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-058` lands it; `pipeline resume TICKET-058 --stage planning` sends it back.

### 2026-08-27 02:10:12Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-27 02:10:19Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/058


Rebasing (1/7)
Rebasing (2/7)
Rebasing (3/7)
Rebasing (4/7)
Rebasing (5/7)
Rebasing (6/7)
Rebasing (7/7)
Auto-merging CLAUDE.md
CONFLICT (content): Merge conflict in CLAUDE.md
Auto-merging README.md
error: could not apply be6bd84... docs(TICKET-058): document the per-project read-only allowlist
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply be6bd84... # docs(TICKET-058): document the per-project read-only allowlist
Auto-merging CLAUDE.md
CONFLICT (content): Merge conflict in CLAUDE.md
Auto-merging README.md
Auto-merging pipeline/daemon/supervisor.py
Automatic merge failed; fix conflicts and then commit the result.

```

### 2026-08-27 02:11:43Z · human · note · by=chezzijr

**resumed** by chezzijr -> `merging`, reset []

### 2026-08-27 02:11:44Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
jr/proj/agent-pipeline merge --ff-only ticket/058


Rebasing (1/7)Rebasing (2/7)Rebasing (3/7)Rebasing (4/7)Rebasing (5/7)Rebasing (6/7)Rebasing (7/7)Auto-merging CLAUDE.md
CONFLICT (content): Merge conflict in CLAUDE.md
Auto-merging README.md
error: could not apply be6bd84... docs(TICKET-058): document the per-project read-only allowlist
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply be6bd84... # docs(TICKET-058): document the per-project read-only allowlist
Already up to date.
Updating 444285a..82bc1a3
Fast-forward
 .project/pipeline.toml                    |  10 +++
 CLAUDE.md                                 |   7 +-
 README.md                                 |  15 +++++
 pipeline/core/config.py                   |  32 +++++++++
 pipeline/daemon/supervisor.py             |   7 +-
 pipeline/hooks/dangerous-commands.py      |  32 +++++++++
 pipeline/hooks/test_dangerous_commands.py | 107 ++++++++++++++++++++++++++++--
 pipeline/templates/pipeline.toml          |   8 +++
 tests/test_harness.py                     |  29 ++++++++
 tests/test_stages.py                      |  30 ++++++++-
 10 files changed, 267 insertions(+), 10 deletions(-)

```

### 2026-08-27 02:11:44Z · merging · decision

decision recorded as `DEC-058`
