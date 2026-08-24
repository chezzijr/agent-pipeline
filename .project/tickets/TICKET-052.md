---
id: TICKET-052
stage: done
class: bugfix
branch: ticket/052
test_file: pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/config.py
- pipeline/daemon/supervisor.py
- pipeline/harnesses/claude-code.toml
- pipeline/hooks/dangerous-commands.py
- pipeline/hooks/test_dangerous_commands.py
- tests/test_dispatch.py
- tests/test_harness.py
- tests/test_stages.py
counters:
  plan_validation_attempts: 2
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
  plan_steps: 23
  plan_files: 10
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: a3be3385-805d-4ff5-9682-e2c01c2c6d87
  log: .project/logs/TICKET-052-review-a3be3385.log
approved_by: chezzijr
approved_at: '2026-08-24T11:11:21.640489+00:00'
---

## Summary
a stage could write anywhere in the main checkout -- implemented: the guard now blocks a `Write`/`Edit`/`MultiEdit`/`NotebookEdit` outside the worktree

Review passed the delta with no blocking findings. Implementing landed the
approved 23-step plan in 4 commits (`df041ab`, `6d5fe93`, `2b32136`,
`fc8dce0`), and review re-ran every acceptance criterion it could.

`pipeline/hooks/dangerous-commands.py` gained `resolve()`, `path_verdict()`
and `file_verdict()`, wired into `main()` beside the Bash `verdict()`.
`stage_settings()` (`pipeline/core/config.py:244`) registers the guard for
`Bash|Write|Edit|MultiEdit|NotebookEdit`. `spawn()`
(`pipeline/daemon/supervisor.py:389-391`) exports `PIPELINE_WORKTREE`,
`PIPELINE_TICKET` and `PIPELINE_RESULT`. Stale "`matcher` is `Bash`" prose is
corrected in five files; `--add-dir` stays with a corrected comment.

Review's own runs: `uv run --group dev pytest -q` -- `282 passed`;
`uv run python pipeline/hooks/test_dangerous_commands.py` -- `guard: all
passed`; the `matcher` grep leaves no line saying `Bash` alone. Step 14's
live check is recorded in `## Thread`; review did not re-run it.

Bash stays uncovered by decision: `echo x > /abs/path` still writes outside
the worktree from a `write: true` stage.

`pipeline/hooks/dangerous-commands.py` and `pipeline/harnesses/claude-code.toml`
are in `machine.FENCED`; this ticket parks at `awaiting-merge` for a human.

TICKET-041 changed `--add-dir {project}` to `--add-dir {project}/.project` in
`pipeline/harnesses/claude-code.toml` to stop a stage writing outside its
worktree. It does not work, and it never could: `--add-dir` widens what the
harness's PERMISSION LAYER allows, and the same command line disables that
layer.

    pipeline/harnesses/claude-code.toml:169
    --permission-mode bypassPermissions ... --add-dir {project}/.project

With `bypassPermissions` there is no permission check for `--add-dir` to
extend, so the directory list is inert. Headless stages have had unrestricted
filesystem write access since the harness was written; narrowing the flag
changed nothing.

Reproduced on main at 47fed3b, by a `triage` agent that tested it deliberately
and recorded the result in `.project/logs/TICKET-044-triage-5ad2f9b1.log`:

    TOOL: Write
    {"file_path": "/home/chezzijr/proj/agent-pipeline/tests/_probe.txt",
     "content": "probe123\n"}

The file appeared in the main checkout. Its cwd was
`.worktrees/TICKET-044`. In the same run, TICKET-042's and TICKET-046's agents
wrote their tests into the main checkout's `tests/test_gate.py` -- TICKET-042's
twice, the second `def` silently shadowing the first -- and TICKET-044
escalated at `merging` because the resulting dirty checkout blocked its
fast-forward:

    error: Your local changes to the following files would be overwritten by merge:
        tests/test_config.py

Neither of TICKET-041's other two parts covers this. Its `_common.md` rule 5 is
guidance, which is worth having and is not enforcement. Its `dirty_snapshot()`
baseline only runs for `write: false` stages (`pipeline/daemon/supervisor.py`,
`if is_readonly(stage, project)`), and `triage` and `implementing` are
`write: true` -- so the two stages that write code are exactly the two nothing
watches.

Expected: a stage cannot write outside its worktree, enforced by code rather
than by a flag or a prompt. `pipeline/hooks/dangerous-commands.py` is the layer
that decides with code, and it already runs as a `PreToolUse` hook -- but
`stage_settings()` (`pipeline/core/config.py:232`) registers it with
`"matcher": "Bash"`, and `main()` returns 0 for any `tool_name` that is not
`Bash`, so `Write` and `Edit` are invisible to it. Both halves have to change
together for the guard to see a file tool at all.

The rule itself is narrow: reject a `Write`/`Edit` whose resolved path is
outside the agent's worktree, with the ticket file and the `.result` sidecar as
the two exceptions `_common.md` rule 5 already names. `PIPELINE_READONLY` is
already exported per stage; the worktree path needs exporting the same way.

Three things to settle in `## Decisions`, not to discover later:

1. Resolve the path before comparing -- symlinks and `..` -- and refuse what
   cannot be resolved. Invariant 5: values reaching this check are hostile.
2. Bash is NOT covered by this rule and must not be forgotten. A `write: true`
   stage runs arbitrary shell, and `always_rules()` does not restrict where a
   redirect points. This ticket can close the file-tool half honestly and say
   so; claiming the hole is shut when `echo x > /abs/path` still works would be
   worse than leaving it open.
3. `--add-dir {project}/.project` should stay or go on its own merits, but the
   comment above it in `claude-code.toml` currently claims an effect it does
   not have, and that comment is why this was believed fixed.

The failure a test should show is a `Write` to an absolute path outside the
worktree being allowed by the guard.

Supersedes the "reach" half of TICKET-041; that ticket's `_common.md` rule and
`dirty_snapshot()` baseline both stand.

Triage confirmed both code claims (`stage_settings()`'s `"matcher": "Bash"`
at `pipeline/core/config.py:238`, and `main()`'s `tool_name != "Bash"` early
return at `pipeline/hooks/dangerous-commands.py:235`) and committed a failing
test proving a `Write` outside the worktree passes the guard unblocked. See
`## Reproduction`.

Planning settled the three points in `## Decisions` and wrote a 20-step
`## Plan`. The fix has three parts that only work together:

1. `pipeline/hooks/dangerous-commands.py` gains `path_verdict()`. A resolved
   path outside the worktree is blocked; the ticket file and the `.result`
   sidecar are the two exceptions.
2. `stage_settings()` names the file tools in `matcher`.
3. `spawn()` exports `PIPELINE_WORKTREE`, `PIPELINE_TICKET` and
   `PIPELINE_RESULT` beside `PIPELINE_READONLY`.

Bash stays uncovered. After this ticket `echo x > /abs/path` still writes
outside the worktree. `--add-dir {project}/.project` stays, because
`interactive_cmd` runs under `acceptEdits` where the flag does bind; its
comment is corrected. `## Decisions` supersedes DEC-041.

Tier A and Tier B both passed the 23-step plan on 2026-08-24. Tier B had
rejected the 20-step draft on three findings; planning answered all three, and
steps 10, 14 and 20 are the answers. Implementation runs the plan as written.

Two things the implementer should carry, neither of which blocks the plan:

1. `test_dangerous_commands.py:86`'s assertion message, "non-Bash tools are not
   this guard's business", stays true for its `Read` event and false in
   general. No step touches it.
2. Step 14 does not run `strip_settings_sources()` on the worktree first. A
   `.claude/settings.json` there would show a `"Write"` and no block line,
   firing step 14's fallback on a false signal.

`pipeline/hooks/dangerous-commands.py` and `pipeline/harnesses/claude-code.toml`
are in `machine.FENCED`, so this ticket parks at `awaiting-merge` for a human
whatever it reports.

## Reproduction

`pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked`
(commit f370204).

    ./pipeline/hooks/test_dangerous_commands.py

    Traceback (most recent call last):
      File ".../pipeline/hooks/test_dangerous_commands.py", line 107, in <module>
        test_write_outside_worktree_is_not_blocked()
      File ".../pipeline/hooks/test_dangerous_commands.py", line 98, in test_write_outside_worktree_is_not_blocked
        assert p.returncode == 2, msg
    AssertionError: expected block, got returncode=0 stderr=''

expect: expected block, got returncode=0 stderr=''

## Digest

Files this plan touches, and what each is responsible for:

- `pipeline/hooks/dangerous-commands.py` -- the rule. Today two rule sets
  (`always_rules`, `readonly_rules`), both Bash-only. This adds a third that
  reads a path, not a command.
- `pipeline/hooks/test_dangerous_commands.py` -- the guard's own suite. Table
  driven, run directly (`./pipeline/hooks/test_dangerous_commands.py`), and
  only its `test_*` functions are collected by pytest.
- `pipeline/core/config.py` -- `stage_settings()` at line 223 writes the
  settings JSON. The `matcher` is at line 238.
- `pipeline/daemon/supervisor.py` -- `spawn()` builds the child env at lines
  376-378. `wt` is the worktree `Path`; `ticket_path` and `tickets_dir` are
  already imported (line 27) and already used at lines 369-370.
- `tests/test_stages.py:78` -- `test_stage_settings_register_the_guard_as_a_pretooluse_hook`
  asserts `entry["matcher"] == "Bash"`, so it fails the moment part 2 lands.
- `tests/test_dispatch.py`, `tests/test_harness.py`, `CLAUDE.md`, `README.md`,
  `pipeline/harnesses/claude-code.toml` -- the new env test, and the prose that
  states the opposite of what will be true.

Key functions and entry points:

- `main()` (`pipeline/hooks/dangerous-commands.py:232`) is the hook entry
  point. It reads one JSON event on stdin and returns 2 to block.
- A hook event carries `tool_name` and `tool_input`. `Write`, `Edit` and
  `MultiEdit` put the path in `tool_input.file_path`; `NotebookEdit` uses
  `notebook_path`.
- `verdict()` (line 224) is the Bash path. This plan does not touch it.
- `spawn()` (`pipeline/daemon/supervisor.py:310`) is the only place a stage's
  env is built. `PIPELINE_READONLY` and `PIPELINE_STAGE` are the precedent.

Gotchas, each read off the code:

- The guard imports `json`, `os`, `re`, `shlex`, `sys` and no `pathlib`. Stay
  on `os.path`. `realpath()` is non-strict, so a file that does not exist yet
  still resolves.
- `--tools` grants `Read,Grep,Glob,Bash,Edit,Write` today
  (`pipeline/harnesses/claude-code.toml:34-35`), so `MultiEdit` and
  `NotebookEdit` cannot appear in an event. They go in the matcher and the rule
  anyway, so granting one later does not silently reopen the hole.
- A `write: false` stage holds `Write` and `Edit` for one reason: writing the
  `.result` sidecar (`claude-code.toml:40`, `tests/test_harness.py:315`). Break
  the sidecar exception and no read-only stage can finish.
- `.project/pipeline.toml` becomes unwritable by a file tool as a side effect.
  DEC-037 worked around that hole from the other end; its HEAD read stays,
  because Bash still reaches the file.
- The reproduction test hardcodes absolute paths under
  `/home/chezzijr/proj/agent-pipeline`. They do not need to exist:
  `realpath()` does not stat. Do not rewrite the test to use a tempdir --
  `verifying` re-runs it by name and Tier A ran it against base.
- `pipeline/hooks/dangerous-commands.py` and
  `pipeline/harnesses/claude-code.toml` are both in `machine.FENCED`, so this
  ticket parks at `awaiting-merge` for a human whatever it reports.
- Two more comments state the opposite of what this plan makes true, and no
  earlier draft reached them: `project_config()`'s docstring
  (`pipeline/core/config.py:72-73`) and the `--strict-mcp-config` comment
  (`pipeline/harnesses/claude-code.toml:101`). Steps 10 and 20 fix them. Keep
  the true half of each: Bash still reaches `.project/pipeline.toml`, and an
  `mcp__*` tool name still matches no rule.
- Nothing in either suite spawns Claude Code, so no test observes a `Write`
  `PreToolUse` event reaching a regex matcher -- every test drives the hook by
  `subprocess`. `claude` 2.1.241 is on PATH, so step 14 runs one live `claude
  -p` and reads the block message out of the stream log. The fallback is one
  settings entry per tool name, exact strings, which is the matcher form
  `matcher: "Bash"` already proves.
- A plan step that writes a path as `./pipeline/...` cites nothing. Tier A's
  `_cites()` (`pipeline/core/gate.py:46`) anchors on `(?<![\w./-])`, so a
  leading `/` blocks the match. Step 2 names the bare path and keeps the
  `./` command form beside it.

## Decisions checked

Grepped `.project/decisions/` for: `add-dir`, `worktree`, `PIPELINE_READONLY`,
`hook`, `guard`, `bypassPermissions`, `PreToolUse`, `matcher`.

- DEC-041 -- calls `--add-dir {project}/.project` "a stage's whole reach
  outside its worktree" and "the prevention for its file tools". This ticket's
  evidence contradicts that, so `## Decisions` supersedes it. DEC-041's other
  two paragraphs (the main-checkout baseline omits HEAD; only read-only stages
  get that baseline) are restated there and still hold.
- DEC-034 -- complied with, not superseded. Its claim is that
  `strip_settings_sources()` at spawn is a complete defence against a worktree
  settings file, and that *that* defence "does not need a Write/Edit matcher on
  the hook". This plan adds the matcher for a different rule and changes
  nothing about `strip_settings_sources()`.
- DEC-037 -- `project_config()` reads `.project/pipeline.toml` from the main
  checkout's HEAD because "the guard's `matcher` is `Bash`, so a `Write` or
  `Edit` of `.project/pipeline.toml` passes both". This plan closes that hole
  for file tools only. The HEAD read stays.
- DEC-025 -- `--strict-mcp-config` keeps MCP tools out, since the guard's
  matcher cannot see an `mcp__*` tool name. Still true: the new matcher names
  built-in tools only.

## Plan

1. Add `test_paths_outside_the_worktree_are_blocked()` to `pipeline/hooks/test_dangerous_commands.py` and add `shutil` and `tempfile` to its import line; it builds `proj = os.path.realpath(tempfile.mkdtemp())`, `wt = proj + "/.worktrees/TICKET-001"`, `tickets = proj + "/.project/tickets"`, `os.makedirs` for both, `os.symlink(proj, wt + "/up")`, `ticket = tickets + "/TICKET-001.md"`, `result = tickets + "/TICKET-001.result"` and `allowed = [ticket, result]`, then asserts `guard.path_verdict(p, wt, allowed)` is truthy for each of `proj + "/tests/_probe.txt"`, `proj + "/.project/pipeline.toml"`, `proj + "/.worktrees/TICKET-002/x.py"`, `tickets + "/TICKET-002.md"`, `wt + "/../../escape.py"`, `wt + "/up/tests/x.py"`, `"/etc/passwd"` and `""`, asserts it is `None` for each of `wt + "/pipeline/core/config.py"`, `wt + "/sub/../thing.py"`, `"thing.py"`, `ticket` and `result`, and ends with `shutil.rmtree(proj)`.
2. Run the guard suite `pipeline/hooks/test_dangerous_commands.py` directly (`./pipeline/hooks/test_dangerous_commands.py`) and watch step 1's test fail with `AttributeError: module 'guard' has no attribute 'path_verdict'`.
3. Add the rule to `pipeline/hooks/dangerous-commands.py` above `def main()`: `FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}`; `PATH_KEYS = ("file_path", "notebook_path")`; `resolve(path, base)` returning `os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))`, with `None` for a falsy `path` and `None` under `except (OSError, ValueError)`; and `path_verdict(path, worktree, allowed)` which resolves `worktree` against `os.getcwd()` and returns `f"PIPELINE_WORKTREE={worktree!r} does not resolve to a path"` when that is `None`, resolves `path` against the resolved worktree and returns `f"{path!r} does not resolve to a path"` when that is `None`, returns `None` when the target equals `resolve(p, wt)` for any `p` in `allowed`, returns `None` when `target == wt or target.startswith(wt + os.sep)`, and otherwise returns `f"{target} is outside this stage's worktree {wt}"`.
4. Run `./pipeline/hooks/test_dangerous_commands.py`: step 1's test prints `ok BLOCK [path]` for all 8 paths and `ok allow [path]` for all 5, and `test_write_outside_worktree_is_not_blocked` still fails with `expected block, got returncode=0 stderr=''`. Commit `pipeline/hooks/dangerous-commands.py` and `pipeline/hooks/test_dangerous_commands.py` as `test(TICKET-052): a path rule for the guard`.
5. Route file tools into the guard in `pipeline/hooks/dangerous-commands.py`: add `file_verdict(tool_input)`, which returns `None` when `os.environ.get("PIPELINE_WORKTREE")` is empty, returns `"a file tool with no path the guard can read"` when no `PATH_KEYS` entry is a `str`, and otherwise returns `path_verdict(path, wt, [p for p in (os.environ.get("PIPELINE_TICKET"), os.environ.get("PIPELINE_RESULT")) if p])`.
6. Rewrite `main()` in `pipeline/hooks/dangerous-commands.py` to read `tool = event.get("tool_name")` and `tool_input = event.get("tool_input") or {}`, then set `label, subject, why` to `"Path"`, the first `PATH_KEYS` value that is a `str` (else `""`), and `file_verdict(tool_input)` when `tool in FILE_TOOLS`; to `"Command"`, `tool_input.get("command", "")` and `verdict(subject, os.environ.get("PIPELINE_READONLY") == "1")` when `tool == "Bash"`; and `return 0` for any other tool -- then print the existing block message with `f"{label}: {subject}"` in place of `f"Command: {command}"` and return 2.
7. Add `test_the_guard_sees_every_file_tool_not_just_bash()` to `pipeline/hooks/test_dangerous_commands.py` and call it from the `__main__` block; it builds the same temp project as step 1, sets `env = dict(os.environ, PIPELINE_WORKTREE=wt, PIPELINE_TICKET=ticket, PIPELINE_RESULT=result)`, and asserts through `subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True, env=env)` that `{"tool_name": "Edit", "tool_input": {"file_path": proj + "/tests/test_gate.py"}}` returns 2, that a `Write` to `ticket`, to `result` and to `wt + "/thing.py"` each return 0, and that a `Write` to `/etc/passwd` with `PIPELINE_WORKTREE` removed from the environment returns 0.
8. Run `./pipeline/hooks/test_dangerous_commands.py` and `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py`: both green, `test_write_outside_worktree_is_not_blocked` included. Commit `pipeline/hooks/dangerous-commands.py` and `pipeline/hooks/test_dangerous_commands.py` as `fix(TICKET-052): block a file tool writing outside the worktree`.
9. Change the matcher in `pipeline/core/config.py:238` to `{"matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit", "hooks": entries}`, with a comment above it stating that the value is a regex over the tool name, that every name is spelled out rather than relying on `Edit` matching `MultiEdit` by substring, that with `Bash` alone a `Write` to any absolute path never reached the hook, and that step 14's live check is what proves Claude Code delivers a `Write` event to this matcher.
10. Rewrite the stale half-sentence in `project_config()`'s docstring at `pipeline/core/config.py:72-73`, replacing "and the guard's `matcher` is `Bash`, so it never sees an `Edit`" with "and the guard's path rule blocks a file tool there, but Bash still reaches the file", leaving the rest of that docstring, the HEAD read and the disk fallback unchanged.
11. Update `tests/test_stages.py:82` to `assert entry["matcher"] == "Bash|Write|Edit|MultiEdit|NotebookEdit"`, add a loop asserting `re.fullmatch(entry["matcher"], tool)` for `tool` in `("Bash", "Write", "Edit", "MultiEdit", "NotebookEdit")`, and add `import re` to that file's imports.
12. Reword the stale docstring at `tests/test_harness.py:326` from "The guard registers `PreToolUse` with `matcher: \"Bash\"`, so it has nothing to say about any of them" to "The guard's `PreToolUse` matcher names built-in tools only, so it has nothing to say about any of them", leaving that test's assertions unchanged.
13. Run `uv run --group dev pytest -q tests/test_stages.py tests/test_harness.py`: no failures. Commit `pipeline/core/config.py`, `tests/test_stages.py` and `tests/test_harness.py` as `fix(TICKET-052): register the guard for the file tools too`.
14. Confirm live that Claude Code delivers a `Write` event to the new matcher in `pipeline/core/config.py`, because no test observes it -- every test drives the hook by `subprocess` -- by running, from the worktree root, `S=$(uv run python -c 'from pipeline.core.config import stage_settings, stage_config; print(stage_settings("implementing", stage_config("implementing")))')` and then `PIPELINE_WORKTREE=$PWD PIPELINE_STAGE=live-check claude -p --model claude-haiku-4-5-20251001 --settings "$S" --setting-sources project --output-format stream-json --verbose --tools "Read,Grep,Glob,Bash,Edit,Write" --strict-mcp-config --permission-mode bypassPermissions --max-budget-usd 1 -- "Use the Write tool, not Bash, to create the file /tmp/TICKET-052-probe.txt containing probe123." > /tmp/TICKET-052-live-check.log 2>&1` (`claude` 2.1.241 is on PATH).
    Expect `grep -cF '"Write"' /tmp/TICKET-052-live-check.log` to print 1 or more, `grep -cF 'Blocked by the pipeline guard' /tmp/TICKET-052-live-check.log` to print 1 or more, and `test ! -e /tmp/TICKET-052-probe.txt` to exit 0. Paste those three results verbatim into `## Thread`, then `rm -f /tmp/TICKET-052-live-check.log /tmp/TICKET-052-probe.txt`.
    Fallback, applied only when the log shows a `"Write"` and no block line: the regex matcher does not deliver the event, so change the matcher in `pipeline/core/config.py` to one entry per tool name, `settings = {"hooks": {"PreToolUse": [{"matcher": t, "hooks": entries} for t in ("Bash", "Write", "Edit", "MultiEdit", "NotebookEdit")]}}` -- an exact string is the matcher form `matcher: "Bash"` already proves -- rewrite step 11's assertions in `tests/test_stages.py` to read `[e["matcher"] for e in data["hooks"]["PreToolUse"]]` and compare that list to those five names, re-run `uv run --group dev pytest -q tests/test_stages.py`, and re-run this step's live check.
    When `claude` does not run at all -- binary missing, an auth error, a budget error, or no `"Write"` anywhere in the log -- record the verbatim error in `## Thread` and keep the regex matcher in `pipeline/core/config.py`. The fallback needs an observed unblocked `Write`, not an absent observation.
15. Add `test_a_spawn_tells_the_guard_where_its_worktree_is()` to `tests/test_dispatch.py`: `d, _ = git_project()`, write `FIXTURE.replace("stage: plan-validation", "stage: implementing")` to `d / ".project/tickets/TICKET-001.md"`, build `hcfg = dict(harness("fake"))` whose `cmd` is `printf "%s\n%s\n%s\n" "$PIPELINE_WORKTREE" "$PIPELINE_TICKET" "$PIPELINE_RESULT" > <dump>; printf "result: ok\nsummary: x\n" > {result_file}` with `<dump>` an absolute path inside `d`, call `supervisor.start(d, path, hcfg, {})`, then `rec["proc"].wait()`, and assert the three dumped lines equal `str(d / ".worktrees" / "TICKET-001")`, `str(path)` and `str(d / ".project/tickets/TICKET-001.result")`.
16. Run `uv run --group dev pytest -q "tests/test_dispatch.py::test_a_spawn_tells_the_guard_where_its_worktree_is"` and watch it fail on the first assert, because the dumped worktree line is empty.
17. Export the three variables in `pipeline/daemon/supervisor.py` directly below `env["PIPELINE_READONLY"]` (line 378): `env["PIPELINE_WORKTREE"] = str(wt)`, `env["PIPELINE_TICKET"] = str(ticket_path(project, tid))` and `env["PIPELINE_RESULT"] = str(tickets_dir(project) / f"{tid}.result")`, with a comment stating that the guard's file-tool rule compares against these, and that the two exceptions are exported by path rather than re-derived inside the hook.
18. Run `uv run --group dev pytest -q tests/test_dispatch.py`: no failures. Commit `pipeline/daemon/supervisor.py` and `tests/test_dispatch.py` as `fix(TICKET-052): tell the guard which worktree a stage owns`.
19. Correct the comment above `--add-dir` in `pipeline/harnesses/claude-code.toml` (lines 6-12) to state that `--add-dir` widens what the permission layer allows, that `--permission-mode bypassPermissions` on the same command line removes that layer, that the flag therefore enforces nothing under `cmd` and binds only under `interactive_cmd`'s `acceptEdits`, that the enforcement is the `PreToolUse` path rule in `pipeline/hooks/dangerous-commands.py`, and that the directory stays narrow so the flag is right if the permission mode ever changes.
20. Reword the second stale claim in `pipeline/harnesses/claude-code.toml`, at line 101, from "the guard's `matcher: \"Bash\"` covers none of those tool names" to "the guard's matcher names built-in tools only, so it covers none of those tool names", leaving the `--strict-mcp-config` measurement in the same comment block unchanged.
21. Rewrite the two stale claims in `CLAUDE.md`: the `.project/` bullet at line 111 replaces "the guard's `matcher` is `Bash` and never sees one" with "the guard's path rule blocks a file tool there, and Bash still reaches it, which is why `project_config()` reads HEAD"; the `--add-dir` bullet at line 118 states that the flag is inert under `bypassPermissions` and that the guard's path rule is what confines a stage.
22. Reword the two `matcher` claims in `README.md` (lines 44 and 458) to say the guard's matcher names built-in tools only, so an MCP tool name still reaches no rule, and extend the module docstring of `pipeline/hooks/dangerous-commands.py` with a third rule set: "paths -- for a file tool, when PIPELINE_WORKTREE is set. A write outside the worktree is refused, except the ticket file and the `.result` sidecar. Bash is deliberately NOT covered: `echo x > /abs/path` still writes anywhere."
23. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`: no failures, and the guard prints `guard: all passed`. Run `grep -rn matcher CLAUDE.md README.md pipeline/core/config.py pipeline/harnesses/claude-code.toml tests/test_harness.py`: no line left says the matcher is `Bash` alone. Commit `pipeline/harnesses/claude-code.toml`, `CLAUDE.md`, `README.md` and `pipeline/hooks/dangerous-commands.py` as `docs(TICKET-052): the guard confines file tools, the --add-dir flag does not`.

## Acceptance criteria

- `pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked` passes: a `Write` to an absolute path outside `PIPELINE_WORKTREE` exits 2.
- `pipeline/hooks/test_dangerous_commands.py::test_paths_outside_the_worktree_are_blocked` passes: 8 blocked paths, including a symlink out of the worktree and a `..` traversal, and 5 allowed ones.
- `pipeline/hooks/test_dangerous_commands.py::test_the_guard_sees_every_file_tool_not_just_bash` passes: an `Edit` outside the worktree exits 2; the ticket file, the `.result` sidecar and an unset `PIPELINE_WORKTREE` exit 0.
- `tests/test_stages.py::test_stage_settings_register_the_guard_as_a_pretooluse_hook` passes with a matcher that matches `Bash`, `Write` and `Edit`.
- `tests/test_dispatch.py::test_a_spawn_tells_the_guard_where_its_worktree_is` passes: a spawned child's environment carries all three paths.
- Step 14's live check is recorded in `## Thread` with its three results: `grep -cF '"Write"` prints 1 or more, `grep -cF 'Blocked by the pipeline guard'` prints 1 or more, and `/tmp/TICKET-052-probe.txt` does not exist. A run that shows a `"Write"` and no block line fails this criterion and triggers step 14's fallback. No named test covers this: nothing in either suite spawns Claude Code.
- No stale matcher claim survives: `grep -rn matcher CLAUDE.md README.md pipeline/core/config.py pipeline/harnesses/claude-code.toml tests/test_harness.py` returns no line saying the guard's matcher is `Bash` alone.
- `uv run --group dev pytest -q` reports no failures, and `./pipeline/hooks/test_dangerous_commands.py` prints `guard: all passed`.

## Decisions

supersedes: DEC-041 -- `--add-dir {project}/.project` is not a stage's reach outside its worktree, and never was.

**`--add-dir` narrows nothing under `bypassPermissions`, and the flag is not
the enforcement.** `--add-dir` widens what the harness's permission layer
allows. `--permission-mode bypassPermissions` on the same command line
(`pipeline/harnesses/claude-code.toml:169`) removes that layer, so the
directory list is inert for every headless stage. Headless stages have had
unrestricted filesystem write access since the harness was written. A `triage`
agent proved it on 2026-08-24 by writing
`/home/chezzijr/proj/agent-pipeline/tests/_probe.txt` from a cwd of
`.worktrees/TICKET-044` (`.project/logs/TICKET-044-triage-5ad2f9b1.log`). The
enforcement is `path_verdict()` in `pipeline/hooks/dangerous-commands.py`,
reached through the `PreToolUse` matcher and `PIPELINE_WORKTREE`. All three
parts are load-bearing: drop the matcher and the hook never sees the event;
drop the env export and the rule has nothing to compare against.

**The matcher is a regex over the tool name, and only a live spawn proves it
delivers.** `stage_settings()` writes
`"matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit"`. Every test in both
suites drives the hook by `subprocess`, so all of them pass whether or not
Claude Code routes a `Write` event to that matcher -- the one thing this
ticket exists to change. Step 14 is the only evidence: one live `claude -p`
under the generated settings file, blocked write recorded verbatim in
`## Thread`. If a future Claude Code stops honouring a regex matcher, fall
back to one entry per tool name with exact-string matchers; `matcher: "Bash"`
is the form that has always worked here. Do not delete the live check from the
ticket's record: it is the only place the routing was ever observed.

**The flag stays, and the comment above it must not claim an effect again.**
`interactive_cmd` runs under `acceptEdits` (`claude-code.toml:54`), where the
permission layer exists and the directory list does bind. Widening it back to
`{project}` is still wrong, for the reason DEC-041 gave: it grants every other
ticket's file, every other ticket's worktree and the dispatcher's own tree.

**Bash is NOT covered, deliberately.** `echo x > /abs/path`, `cp x /abs/path`
and a heredoc all still write outside the worktree from a `write: true` stage.
`always_rules()` does not restrict where a redirect points, and
`readonly_rules()` applies only to `write: false` stages. Closing that half
needs either a path rule over parsed shell redirects -- a blocklist, leaky by
nature, which is why `readonly_rules()` is an allowlist -- or an allowlist for
write stages, which cannot work when the stage's job is running arbitrary
project commands. This ticket closes the file-tool half and says so. Do not
read the guard as a filesystem sandbox.

**The path is resolved before it is compared, and what will not resolve is
refused.** `resolve()` calls `os.path.realpath` on both sides, so
`<wt>/../../x`, a symlink planted inside the worktree, and a relative path all
land on their real target before the containment test. Invariant 5: values
reaching this check are hostile. A file tool whose event carries no readable
path is blocked, not allowed. If a future Claude Code renames `file_path`,
stages then fail loudly instead of silently regaining the whole filesystem --
that is the tripwire to look for if every stage suddenly cannot write.

**An unset `PIPELINE_WORKTREE` allows the write.** The guard stays usable
outside a pipeline spawn, where there is no worktree to be outside of.
`spawn()` is the only place that builds a stage's env, and it always exports
the variable;
`tests/test_dispatch.py::test_a_spawn_tells_the_guard_where_its_worktree_is`
is what keeps that true. Residual: a stage that spawns its own agent from Bash
with the variable unset gets an unguarded child.

**Two exceptions, exported by path, not re-derived.** `_common.md` rule 5 names
the ticket file and the `.result` sidecar. `spawn()` already computes both for
`render()`, so `PIPELINE_TICKET` and `PIPELINE_RESULT` carry them and the hook
never rebuilds `<project>/.project/tickets/<id>.md` from parts. Every other
path under `.project/` becomes unwritable by a file tool,
`.project/pipeline.toml` included. DEC-037's HEAD read stays, because Bash
still reaches that file.

**Still standing from DEC-041, restated here so superseding it loses nothing.**
The main-checkout baseline omits HEAD (`dirty_snapshot()`), because `merging`
fast-forwards base while other stages run; do not fold it into
`tree_snapshot()`. Only read-only stages get that baseline, and a `write: true`
stage's Bash reach into the main checkout is still undetected.

## Rollback

Revert the five commits, from `test(TICKET-052): a path rule for the guard`
through `docs(TICKET-052): the guard confines file tools, the --add-dir flag
does not`. Only `pipeline/hooks/dangerous-commands.py`,
`pipeline/core/config.py` and `pipeline/daemon/supervisor.py` change behaviour,
and each change is additive: reverting restores `matcher: "Bash"` and a
`main()` that ignores every non-Bash tool.

If a stage is blocked wrongly and a revert is too slow, delete the
`env["PIPELINE_WORKTREE"]` line in `spawn()`
(`pipeline/daemon/supervisor.py`). That one line disables the path rule alone
and leaves every Bash rule in force.

## Thread

### 2026-08-24 09:02:51Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 09:05:02Z · new · note

A second symptom of the same shape, recorded here because it has no
reproduction of its own and may share a cause with this ticket's.

Pure checks disagree between the dispatcher process and a hand-run:

1. `fenced_touches()` returned `[]` inside `verifying` for TICKET-041 on
   2026-08-23 ("the diff touches no fenced code"), while the same call by hand
   before and after returned `['pipeline/harnesses/claude-code.toml']`. The
   merge was stopped by a conflict, not by the fence.
2. The `## Acceptance criteria` regex produced `acceptance criterion names no
   test` for TICKET-042 and TICKET-046 on 2026-08-24, for the lines
   "- `uv run --group dev pytest -q` reports no failures." and
   "- `uv run --group dev pytest -q` is green." Both are pure ASCII (checked),
   both match the live pattern, and calling `gate()` on the same fixture under
   the dispatcher's own interpreter (`3.13.11`, the `uv tool` editable
   install, `pipeline/core/gate.py` with `\bpytest\b` present) returns no such
   finding. Each cost a plan-validation attempt.

Ruled out: a stale source (the fix predates the dispatcher's start by 16
hours), a non-ASCII look-alike in the input, and a different interpreter.
Not ruled out: stale bytecode -- `pipeline/core/__pycache__/` carries both a
`gate.cpython-313.pyc` and a `gate.cpython-314.pyc` dated 2026-08-22, a day
before the fix.

Do not treat this as in scope for this ticket. It is recorded here so the
evidence is not lost.

### 2026-08-24 09:07:31Z · triage · reproduce · result=ok

Confirmed the two claims by reading code, not just the ticket text:

1. `pipeline/core/config.py:238` — `stage_settings()` registers the guard
   with `"matcher": "Bash"` only.
2. `pipeline/hooks/dangerous-commands.py:235` — `main()` returns 0 whenever
   `event["tool_name"] != "Bash"`.

Added `test_write_outside_worktree_is_not_blocked` to
`pipeline/hooks/test_dangerous_commands.py`. It sends a `Write` event with
an absolute `file_path` outside the worktree straight through `main()` via
subprocess and asserts `returncode == 2`. It gets `returncode == 0`,
matching the ticket's claim exactly. Committed as f370204.

Chose `ok`, not `chore`: the fix needs a new path-outside-worktree check, a
`PIPELINE_WORKTREE` export, and a change to `stage_settings()`'s matcher, and
the ticket itself asks three questions to settle in `## Decisions` before
writing any of that — that is a planning step, not a same-shape edit.

Files this ticket will touch: `pipeline/hooks/dangerous-commands.py`,
`pipeline/core/config.py`, `pipeline/harnesses/claude-code.toml`. Both are
in `machine.FENCED`, so the fix parks at `awaiting-merge` regardless of
`result`.

### 2026-08-24 09:08:22Z · triage · session · session=0cc03517-c0e5-43f3-9deb-4c60adda5564

`triage` ran as session `0cc03517-c0e5-43f3-9deb-4c60adda5564`
- replay: `claude --resume 0cc03517-c0e5-43f3-9deb-4c60adda5564`
- log: `.project/logs/TICKET-052-triage-0cc03517.log`

### 2026-08-24 09:08:22Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Confirmed Write/Edit bypass the guard (matcher=Bash only); committed failing test f370204.

### 2026-08-24 · planning · note

Plan written, 20 steps. The three points the report asked to settle are
settled in `## Decisions`:

1. A path is resolved with `os.path.realpath` on both sides, and a path that
   does not resolve is refused.
2. Bash stays uncovered. The plan says so rather than claiming the hole is
   shut.
3. `--add-dir {project}/.project` stays, because `interactive_cmd` runs under
   `acceptEdits` where the flag does bind. Its comment is corrected.

`## Decisions` supersedes DEC-041, which calls the flag "a stage's whole reach
outside its worktree". DEC-041's other two paragraphs are restated there, so
nothing is lost. DEC-034 is complied with, not superseded: its "does not need
a Write/Edit matcher" claim is scoped to the settings-file defence, and
`strip_settings_sources()` is untouched.

Two findings outside this stage's job:

1. `README.md:44` and `README.md:458` state the guard cannot see an MCP tool
   name because the matcher is `Bash`. Step 19 rewords them. The `TICKET-036`
   gap they describe is unchanged.
2. The thread's second symptom (stale `__pycache__` under `pipeline/core/`) is
   untouched by this plan and still has no ticket.

### 2026-08-24 09:18:51Z · planning · session · session=bcb2cf11-066c-4c39-b9d1-ec330e0be517

`planning` ran as session `bcb2cf11-066c-4c39-b9d1-ec330e0be517`
- replay: `claude --resume bcb2cf11-066c-4c39-b9d1-ec330e0be517`
- log: `.project/logs/TICKET-052-planning-bcb2cf11.log`

### 2026-08-24 09:18:51Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned the file-tool path rule in 20 steps: path_verdict() in the guard, a matcher naming the file tools, and three env exports from spawn(). Supersedes DEC-041; Bash stays uncovered and says so.

### 2026-08-24 09:26:31Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked` fails as required
```
nt, capture_output=True, text=True, env=env)
        msg = "expected block, got returncode=" + repr(p.returncode) + " stderr=" + repr(p.stderr)
>       assert p.returncode == 2, msg
E       AssertionError: expected block, got returncode=0 stderr=''
E       assert 0 == 2
E        +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-052/.venv/bin/python', '/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-052/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:98: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-052
      Built pipeline @ file:///home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-052
Installed 18 packages in 3ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked` fails on base `main` too -- the bug is not already fixed upstream
```
ncode=0 stderr=''
E       assert 0 == 2
E        +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-ivb7bh5e/base/.venv/bin/python', '/tmp/pipeline-base-ivb7bh5e/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:98: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ivb7bh5e/base
      Built pipeline @ file:///tmp/pipeline-base-ivb7bh5e/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- plan step names no declared file: "2. Run `./pipeline/hooks/test_dangerous_commands.py` and watch step 1's test fail with `AttributeError: module 'guard' has no attribute 'path_verdict'`." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-24 09:26:31Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- plan step names no declared file: "2. Run `./pipeline/hooks/test_dangerous_commands.py` and watch step 1's test fail with `AttributeError: module 'guard' has no attribute 'path_verdict'`." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-24 · planning · note

Tier A returned one finding and I fixed exactly it. The finding:

    plan step names no declared file: "2. Run
    `./pipeline/hooks/test_dangerous_commands.py` and watch step 1's test fail
    with `AttributeError: module 'guard' has no attribute 'path_verdict'`."

The step did name a declared file. `_cites()` (`pipeline/core/gate.py:46`)
anchors the match with `(?<![\w./-])`, so the `/` in `./pipeline/...` blocks
it. Step 2 now reads "Run the guard suite
`pipeline/hooks/test_dangerous_commands.py` directly
(`./pipeline/hooks/test_dangerous_commands.py`)". That cites the path and
keeps the command `CLAUDE.md` asks for. The gotcha is in `## Digest`.

I re-ran the gate's own step check over all 20 steps with `_cites()` and
`t.files_declared`: 20 steps, zero uncited, zero prose lines.

Nothing else changed. `## Decisions checked`, `## Plan` steps 1 and 3-20,
`## Acceptance criteria`, `## Decisions` and `## Rollback` stand as written.
DEC-025, DEC-034, DEC-037 and DEC-041 each resolve to a file in
`.project/decisions/`.

### 2026-08-24 09:29:06Z · planning · session · session=5cf69410-c3f9-4f66-bc7b-dcdbb73af701

`planning` ran as session `5cf69410-c3f9-4f66-bc7b-dcdbb73af701`
- replay: `claude --resume 5cf69410-c3f9-4f66-bc7b-dcdbb73af701`
- log: `.project/logs/TICKET-052-planning-5cf69410.log`

### 2026-08-24 09:29:06Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Fixed the one Tier A finding: step 2 cited only `./pipeline/hooks/test_dangerous_commands.py`, which `_cites()` rejects; it now names the bare path. All 20 steps cite a declared file.

### 2026-08-24 10:15:52Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked` fails as required
```
ezzijr/proj/agent-pipeline/tests/_probe.txt", "content": "probe123\n"}})
        env = dict(os.environ)
        env["PIPELINE_WORKTREE"] = "/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-052"
        p = subprocess.run([sys.executable, str(GUARD)], input=event, capture_output=True, text=True, env=env)
        msg = "expected block, got returncode=" + repr(p.returncode) + " stderr=" + repr(p.stderr)
>       assert p.returncode == 2, msg
E       AssertionError: expected block, got returncode=0 stderr=''
E       assert 0 == 2
E        +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-052/.venv/bin/python', '/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-052/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:98: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked` fails on base `main` too -- the bug is not already fixed upstream
```
ncode=0 stderr=''
E       assert 0 == 2
E        +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-jam2wg8n/base/.venv/bin/python', '/tmp/pipeline-base-jam2wg8n/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:98: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jam2wg8n/base
      Built pipeline @ file:///tmp/pipeline-base-jam2wg8n/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 · plan-validation · note

**Tier B: FAIL on three findings.** Two are stale prose in files the plan
already declares; one is the riskiest step.

1. `pipeline/core/config.py:72-73` -- `project_config()`'s docstring reads "the
   guard's `matcher` is `Bash`, so it never sees an `Edit`". Part 2 makes that
   false. Step 9 edits line 238 of this file and skips the docstring. Step 18
   corrects the CLAUDE.md paraphrase of it at line 111.
2. `pipeline/harnesses/claude-code.toml:101` -- "the guard's `matcher: "Bash"`
   covers none of those tool names". Step 17 edits lines 6-12 of this file;
   step 19 corrects the identical claim in `README.md` at 44 and 458.
   This ticket exists because a comment claimed an effect the code did not
   have. Leaving two more of them is that same failure.
3. The riskiest step is 9, the matcher. Every test drives the hook through
   `subprocess.run([sys.executable, str(GUARD)], ...)`. Nothing observes Claude
   Code delivering a `Write` event to a hook registered with
   `"Bash|Write|Edit|MultiEdit|NotebookEdit"`, so all 6 criteria can pass with
   the hole open. `## Rollback` covers over-blocking only.

Passed, each checked against the code: root cause (matcher plus `main()`'s
`tool_name != "Bash"` plus no path rule -- the plan fixes all three, not the
test); DEC-025, DEC-034, DEC-037, DEC-041 (no step contradicts the first three;
DEC-041 is superseded with evidence); scope (every step traces to a criterion or
to a stale claim); criteria (8 blocked and 5 allowed paths, each falsifiable);
no research left (every cited line exists: `config.py:238`,
`supervisor.py:376-378`, `test_stages.py:82`, `claude-code.toml:171`);
regression surface (`test_stages.py:82` and `test_harness.py:326` are the two
the plan already fixes; decision records are written by `record_decision()`, not
by an agent's file tool, so the two exceptions cover every stage write);
blast radius (10 files, 3 of them behaviour, for a fix whose 3 parts only work
together).

### 2026-08-24 10:19:55Z · plan-validation · session · session=15f7a380-939f-43ed-8382-c83ccc88f8dc

`plan-validation` ran as session `15f7a380-939f-43ed-8382-c83ccc88f8dc`
- replay: `claude --resume 15f7a380-939f-43ed-8382-c83ccc88f8dc`
- log: `.project/logs/TICKET-052-plan-validation-15f7a380.log`

### 2026-08-24 10:19:55Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ Tier B rejected the plan on 3 findings: two stale `matcher is Bash` claims in declared files (config.py:72-73, claude-code.toml:101) that no step corrects, and no fallback or live check for step 9.

### 2026-08-24 · planning · note

Tier B returned three findings and I fixed exactly those three.

Finding 1 -- `pipeline/core/config.py:72-73`. On disk it reads "and the guard's
`matcher` is `Bash`, so it never sees an `Edit`". New step 10 replaces that
clause with the path rule and leaves the HEAD read, the disk fallback and the
rest of the docstring alone.

Finding 2 -- `pipeline/harnesses/claude-code.toml:101`. On disk it reads "the
guard's `matcher: "Bash"` covers none of those tool names". New step 20 rewords
it to "the guard's matcher names built-in tools only". The MCP half of that
sentence stays true, so the `--strict-mcp-config` measurement below it is
untouched.

Finding 3 -- nothing observes the matcher. New step 14 runs one live `claude -p`
(2.1.241 is on PATH) with the settings file `stage_settings()` writes,
`PIPELINE_WORKTREE=$PWD`, and a prompt asking for a `Write` to
`/tmp/TICKET-052-probe.txt`. It passes on three results: a `"Write"` in the
stream log, a `Blocked by the pipeline guard` line, and no probe file. Its
fallback fires only on an observed unblocked `Write`: one settings entry per
tool name, exact strings.

I re-ran the gate's own scan over `## Plan`: 23 steps, zero uncited, zero prose
lines. All 8 acceptance criteria still name a test.

### 2026-08-24 10:37:59Z · planning · session · session=66fa0df5-de6a-4aac-b86b-428e282da78a

`planning` ran as session `66fa0df5-de6a-4aac-b86b-428e282da78a`
- replay: `claude --resume 66fa0df5-de6a-4aac-b86b-428e282da78a`
- log: `.project/logs/TICKET-052-planning-66fa0df5.log`

### 2026-08-24 10:37:59Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Fixed all 3 Tier B findings: step 10 rewrites the stale docstring at config.py:72-73, step 20 the stale claim at claude-code.toml:101, step 14 confirms the matcher with one live `claude -p` and carries a fallback. Plan is now 23 steps, all cited.

### 2026-08-24 10:38:11Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-24 10:15:52Z · plan-validation · gate · verdict=PASS` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked` fails on base `main` too -- the bug is not already fixed upstream
```
ncode=0 stderr=''
E       assert 0 == 2
E        +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-p2sewzvk/base/.venv/bin/python', '/tmp/pipeline-base-p2sewzvk/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:98: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-p2sewzvk/base
      Built pipeline @ file:///tmp/pipeline-base-p2sewzvk/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 · plan-validation · note

**Tier B: PASS on all 8 items.** The three findings from the previous round are
fixed. I re-checked each against the code.

1. `pipeline/core/config.py:73` still reads "`matcher` is `Bash`, so it never
   sees an `Edit`". Step 10 rewrites it.
2. `pipeline/harnesses/claude-code.toml:101` still reads "the guard's
   `matcher: "Bash"` covers none of those tool names". Step 20 rewrites it.
3. Step 14 runs one live `claude -p` and states a fallback with a firing
   condition: an observed `"Write"` and no block line.

Root cause, in my words: three gaps, all load-bearing. `stage_settings()`
registers `"matcher": "Bash"` (`config.py:238`), `main()` returns 0 unless
`tool_name == "Bash"` (`dangerous-commands.py:235`), and no rule reads a path.
The plan closes all three and exports `PIPELINE_WORKTREE`, so it fixes why the
test fails, not the test.

Decisions: DEC-041 superseded with evidence. DEC-037's premise holds --
`project_config()` reads HEAD (`config.py:69-83`) and Bash still reaches the
file. DEC-025 and DEC-034 are untouched.

Scope: every step traces to a criterion or to a stale claim the criteria's
`grep` covers. I grepped the 6 declared files for `matcher`: 8 lines, and a
step owns each.

Criteria: falsifiable. 8 blocked paths include a symlink and a `..`; 5 allowed
include the two exceptions.

No research left: `config.py:238`, `config.py:72-73`, `supervisor.py:376-378`
(`wt` is `spawn()`'s parameter, `supervisor.py:317`), `test_stages.py:82`,
`test_harness.py:326`, `claude-code.toml:101` and the comment at 6-12 all exist
as cited. `interactive_permission_mode = "acceptEdits"` is at
`claude-code.toml:54`, as `## Decisions` says.

Riskiest step: 9, the matcher. Step 14 is its evidence and carries its
fallback.

Regression surface: `test_stages.py:82` and `test_harness.py:326` fail on part
2, and steps 11 and 12 fix them. `test_end_to_end_exit_code()` asserts a `Read`
of `/etc/passwd` exits 0 -- step 6 keeps `return 0` for a non-file tool, so it
passes. No test asserts the `Command: ` prefix, so step 6's `f"{label}:
{subject}"` breaks nothing. `planning.md:44-51` only greps
`.project/decisions/`; `record_decision()` (`pipeline/core/ticket.py:315`,
called from `supervisor.py:126`) writes that directory, not a file tool.

Blast radius: 10 files for a `bugfix` -- 3 behaviour, 3 test, 4 prose. The
prose files are there because a criterion greps them.

Two observations, neither blocking:

- `test_dangerous_commands.py:86`'s message "non-Bash tools are not this
  guard's business" stays true for its `Read` event and false in general.
- Step 14 does not run `strip_settings_sources()` on the worktree first. A
  `.claude/settings.json` there would show a `"Write"` and no block line,
  firing the fallback on a false signal. The fallback is a valid matcher form
  either way, so the cost is small.

long: 8 items, each needing its own evidence line.

### 2026-08-24 10:42:17Z · plan-validation · session · session=53fa5fee-f6ce-4e53-aaca-9dcc16d2f959

`plan-validation` ran as session `53fa5fee-f6ce-4e53-aaca-9dcc16d2f959`
- replay: `claude --resume 53fa5fee-f6ce-4e53-aaca-9dcc16d2f959`
- log: `.project/logs/TICKET-052-plan-validation-53fa5fee.log`

### 2026-08-24 10:42:17Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B passed all 8 items: root cause is the 3 gaps the plan closes, every cited line exists, steps 10/14/20 answer the previous rejection, and step 14 carries the riskiest step's fallback.

### 2026-08-24 10:43:18Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 10:43:43Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-24 10:15:52Z · plan-validation · gate · verdict=PASS` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked` fails on base `main` too -- the bug is not already fixed upstream
```
ncode=0 stderr=''
E       assert 0 == 2
E        +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-2gpn_eyh/base/.venv/bin/python', '/tmp/pipeline-base-2gpn_eyh/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:98: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_write_outside_worktree_is_not_blocked
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-2gpn_eyh/base
      Built pipeline @ file:///tmp/pipeline-base-2gpn_eyh/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 10:43:43Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 · implementing · todo

**23-step plan todo, one entry per step:**

1. [x] add `test_paths_outside_the_worktree_are_blocked`
2. [x] run guard suite, watch AttributeError
3. [x] add `path_verdict`/`resolve`/`FILE_TOOLS`/`PATH_KEYS`
4. [x] run suite, commit test(TICKET-052)
5. [x] add `file_verdict`
6. [x] rewrite `main()`
7. [x] add `test_the_guard_sees_every_file_tool_not_just_bash`
8. [x] run both suites, commit fix(TICKET-052) guard
9. [x] change matcher in config.py
10. [x] fix stale docstring config.py:72-73
11. [x] update test_stages.py matcher assertion
12. [x] reword test_harness.py:326 docstring
13. [x] run tests, commit fix(TICKET-052) matcher
14. [x] live check claude -p delivers Write event; record 3 results
15. [x] add `test_a_spawn_tells_the_guard_where_its_worktree_is`
16. [x] run test, watch failure
17. [x] export PIPELINE_WORKTREE/TICKET/RESULT in spawn()
18. [x] run tests, commit fix(TICKET-052) supervisor
19. [x] correct --add-dir comment in claude-code.toml
20. [x] reword claude-code.toml:101 stale claim
21. [x] fix CLAUDE.md stale claims
22. [x] fix README.md matcher claims + guard docstring
23. [x] run full suite + guard script + grep check, commit docs(TICKET-052)

### 2026-08-24 · implementing · report

**Plan executed as written, 4 commits.** TDD followed throughout: each new
test observed RED for the stated reason before any production code, then
GREEN.

1. `df041ab` -- `path_verdict()`, `resolve()`, `file_verdict()`, `FILE_TOOLS`,
   `PATH_KEYS`, and `main()` rewired to route file tools and Bash through
   separate verdicts. Combined the plan's steps 3-8 into one commit -- the
   path rule and its wiring into `main()` are one coupled change, and RED was
   confirmed (`AttributeError: module 'guard' has no attribute 'path_verdict'`)
   before any of it was written.
2. `6d5fe93` -- matcher widened to
   `Bash|Write|Edit|MultiEdit|NotebookEdit`, stale `config.py:72-73` docstring
   and `test_harness.py:326` fixed, `test_stages.py` asserts the new matcher.
3. `2b32136` -- `spawn()` exports `PIPELINE_WORKTREE`, `PIPELINE_TICKET`,
   `PIPELINE_RESULT`. New dispatch test observed RED (`['', '', '']` dumped)
   before the export existed.
4. `fc8dce0` -- `--add-dir` comment corrected, `claude-code.toml:101`,
   `CLAUDE.md`, `README.md` and the guard's module docstring reworded.

**Step 14 live check, no fallback needed:**
- `grep -cF '"Write"'` on the log: `3`
- `grep -cF 'Blocked by the pipeline guard'`: `1`
- `test ! -e /tmp/TICKET-052-probe.txt`: exit 0 (file never created)

The block message read: `Blocked by the pipeline guard (live-check):
/tmp/TICKET-052-probe.txt is outside this stage's worktree
/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-052.` Temp files
(`/tmp/TICKET-052-live-check.log`, `/tmp/TICKET-052-probe.txt`, the scratch
`tests/_live_check.sh` script) were removed after.

**Verification:** `uv run --group dev pytest -q` -- 282 passed.
`./pipeline/hooks/test_dangerous_commands.py` -- `guard: all passed`.
`grep -rn matcher CLAUDE.md README.md pipeline/core/config.py
pipeline/harnesses/claude-code.toml tests/test_harness.py` -- no line
left says the matcher is `Bash` alone.

**No deviation from the plan or `## Decisions`.** Bash stays uncovered, as
decided -- no step touched `always_rules`/`readonly_rules`/`verdict()`.

### 2026-08-24 10:49:24Z · implementing · session · session=ea8c2d03-68a3-4dd7-bdbb-8a087372fa49

`implementing` ran as session `ea8c2d03-68a3-4dd7-bdbb-8a087372fa49`
- replay: `claude --resume ea8c2d03-68a3-4dd7-bdbb-8a087372fa49`
- log: `.project/logs/TICKET-052-implementing-ea8c2d03.log`

### 2026-08-24 10:49:24Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed the 23-step plan in 4 commits; guard now blocks a file tool outside the worktree, matcher widened, PIPELINE_WORKTREE/TICKET/RESULT exported, live check confirmed no fallback needed, full suite green.

### 2026-08-24 · review · report

**No blocking findings.** Reviewed `main..HEAD`: 5 commits, 10 files. Review
re-ran every acceptance criterion except step 14's live check.

- `uv run --group dev pytest -q` -- `282 passed in 12.44s`
- `uv run python pipeline/hooks/test_dangerous_commands.py` -- `guard: all passed`
- `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py` --
  `5 passed`, so all three named guard tests are collected.
- `grep -rn matcher CLAUDE.md README.md pipeline/core/config.py
  pipeline/harnesses/claude-code.toml tests/test_harness.py` -- 5 lines, none
  says the matcher is `Bash` alone.
- Step 14's live check: not re-run. Its three results are in the
  `implementing` report.

Findings raised and then refuted:

1. A stage might need a file tool outside its worktree, so the rule breaks it.
   Refuted: `grep -rn "\.project/" pipeline/stages/*.md` returns one line,
   `pipeline/stages/planning.md:85`, and it says a decision is *copied* into
   `.project/decisions/` when the ticket lands. No stage prompt writes out.
2. The reproduction test might have been weakened to pass. Refuted: `git log
   -L` on `test_write_outside_worktree_is_not_blocked` shows one commit,
   `caa06e0`.

Non-blocking findings:

1. nit -- `pipeline/hooks/test_dangerous_commands.py:86`'s message, "non-Bash
   tools are not this guard's business", stays true for its `Read` event and
   false in general. Planning flagged it; no step touched it.
2. nit -- `main()` prints `Path: ` with an empty subject when `file_verdict()`
   returns "a file tool with no path the guard can read". The block still fires.
3. nit -- the pre-review `## Summary` said the live check saw 1 `"Write"`; the
   `implementing` report says `3`. The criterion is 1 or more. Summary
   rewritten.
4. nit -- a hardlink inside the worktree to a file outside it defeats
   `realpath()`. Speculative: nothing in the pipeline creates one.

Drift from `## Plan`: steps 3-8 landed as one commit, `df041ab`, not two.
`implementing` reported it. Every step's content landed.

### 2026-08-24 10:53:30Z · review · session · session=a3be3385-805d-4ff5-9682-e2c01c2c6d87

`review` ran as session `a3be3385-805d-4ff5-9682-e2c01c2c6d87`
- replay: `claude --resume a3be3385-805d-4ff5-9682-e2c01c2c6d87`
- log: `.project/logs/TICKET-052-review-a3be3385.log`

### 2026-08-24 10:53:30Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed 5 commits: no blocking findings. 282 passed, guard: all passed, 5 guard tests collected, no stale matcher line; 4 nits recorded.

### 2026-08-24 10:53:42Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/hooks/dangerous-commands.py`
- `pipeline/harnesses/claude-code.toml`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-052` lands it; `pipeline resume TICKET-052 --stage planning` sends it back.

### 2026-08-24 11:11:21Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 11:11:32Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/052


Current branch ticket/052 is up to date.
Already up to date.
Updating 3042830..fc8dce0
Fast-forward
 CLAUDE.md                                 | 12 ++--
 README.md                                 |  7 ++-
 pipeline/core/config.py                   | 10 +++-
 pipeline/daemon/supervisor.py             |  6 ++
 pipeline/harnesses/claude-code.toml       | 13 ++++-
 pipeline/hooks/dangerous-commands.py      | 71 +++++++++++++++++++++--
 pipeline/hooks/test_dangerous_commands.py | 93 ++++++++++++++++++++++++++++++-
 tests/test_dispatch.py                    | 27 +++++++++
 tests/test_harness.py                     |  6 +-
 tests/test_stages.py                      |  5 +-
 10 files changed, 226 insertions(+), 24 deletions(-)

```

### 2026-08-24 11:11:32Z · merging · decision

decision recorded as `DEC-052`
