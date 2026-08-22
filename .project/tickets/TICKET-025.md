---
id: TICKET-025
stage: done
class: bugfix
branch: ticket/025
test_file: tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers
files_declared:
- pipeline/harnesses/claude-code.toml
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
  id: ad04b1ea-a615-46cd-999f-75566d7c6cbf
  log: .project/logs/TICKET-025-review-ad04b1ea.log
approved_by: chezzijr
approved_at: '2026-08-21T08:49:56.963605+00:00'
---

## Summary

Reviewed, no blocking findings. `pipeline/harnesses/claude-code.toml` carries
`--strict-mcp-config` in both `cmd` and `interactive_cmd`, committed as
`8a2b1fc`. Review re-ran the suite: `181 passed in 8.34s`, and
`tests/test_harness.py` alone `10 passed in 0.04s`, the named test among them.
Five non-blocking notes are in the last `## Thread` entry.

Review could not run `./pipeline/hooks/test_dangerous_commands.py`; the guard
blocks it for a read-only stage. The delta touches no guard code. Implementing
ran it and recorded `guard: all passed`.

The fix reaches a stage after the merge, and after a reinstall if `pipeline`
was installed with `uv tool install .`. `config.harness()` reads the file from
the installed package (`pipeline/core/config.py:46`), not from a worktree. This
review session still holds 9 `~/.claude` MCP servers, which is the pre-fix
behaviour and confirms the bug.

Prior context, for reference: a stage declared 7 tools and its session
granted 68, including Gmail.

plan-validation passed the plan on all eight items; the scoring is in
`## Thread`. One addition from that review, applied by implementing: step 4's
comment block sits above the `cmd` assignment, outside the `"""` string.

Fix: add `--strict-mcp-config` to both command templates in
`pipeline/harnesses/claude-code.toml`. Two words, one file, no Python.
Planning measured it on live sessions; `## Digest` carries the evidence and the
exact edit.

`config._tools()` (`pipeline/core/config.py:120`) builds `--tools` from the
stage's `write` flag, and `--tools` restricts the built-in set only. Every MCP
server in the developer's `~/.claude` loads anyway. TICKET-024's `planning`
asked for `Read,Grep,Glob,Bash,Edit,Write,Skill` and the `init` event of the
session it got granted 53 tools from 9 servers, among them
`mcp__claude_ai_Gmail__create_draft`. Two consequences, one of them a hole in
an invariant:

1. The guard registers `PreToolUse` with `matcher: "Bash"`
   (`pipeline/core/config.py:139`), so it has nothing to say about
   `mcp__claude_ai_Gmail__send_message`. CLAUDE.md invariant 4 says hooks are
   the layer that makes a promise; that promise covered one tool name out of 53.
2. The same ticket runs differently on two machines. The harness file describes
   the session; the developer's config decides it.

Planning ran the flag rather than trusting its name. With the pipeline's exact
flag set on `claude-haiku-4-5-20251001`, `init` reads `"tools":["Bash","Edit",
"Glob","Grep","Read","Skill","Write"]` and `"mcp":[]`; without the flag, 68
tools and 9 servers. The ticket's acceptance criterion -- `init.tools` contains
only the declared names -- is met, and the flag does not break the command.

Triage committed the failing test as `8dcda2c`. The count discrepancy in the
original report is settled: 68 on this machine today, 53 in the TICKET-024 log,
never 78. Same servers, same Gmail names.

Out of scope, unchanged, noted: slash commands (97 still load with the flag
on), `~/.claude/CLAUDE.md`, the plugin `SessionStart` hooks, `settings.json`,
and the guard's `matcher: "Bash"`.

The original report follows.

`render()` passes `--tools` built from the stage's `write` flag, so `planning`
asked for `Read,Grep,Glob,Bash,Edit,Write,Skill`. The `init` event of the
session it actually got, from `.project/logs/TICKET-024-planning-*.log`:

    tools: 78
    extra: 71
    sample: mcp__claude_ai_Gmail__create_draft, mcp__claude_ai_Gmail__forward,
            mcp__claude_ai_Gmail__trash_thread, ...
    mcp: github, context7, mermaid-mcp, godot, excalidraw, claude.ai Linear,
         claude.ai Gmail, claude.ai Google Calendar, claude.ai Google Drive
    slash commands: 98

`--tools` does not restrict MCP tools, and the developer's `~/.claude` MCP
servers load into every stage. Two consequences, one of them a hole in an
invariant:

1. The read-only allowlist in `pipeline/hooks/dangerous-commands.py` is
   registered as a `PreToolUse` hook with `matcher: "Bash"`. It has nothing to
   say about `mcp__claude_ai_Gmail__send_message`. CLAUDE.md invariant 4 says
   hooks are the layer that makes a promise; that promise currently covers one
   tool name out of 78.
2. The same ticket runs differently on two machines. The harness file describes
   the session; the developer's config decides it.

Expected: a stage's toolset is what the stage and the harness declare. Nothing
else appears in `init`.

`claude --help` documents `--strict-mcp-config` ("Only use MCP servers from
--mcp-config, ignoring all other MCP configurations"), which looks like the
whole fix for the MCP half and is one line in
`pipeline/harnesses/claude-code.toml`. Check it against a real `init` event
rather than trusting the flag name: the acceptance criterion is that
`init.tools` contains only the declared names.

Do **not** reach for `--bare`. It skips hooks, and a stage that cannot register
`dangerous-commands.py` must be refused, not run unguarded -- `spawn()` already
refuses that case for a harness with `supports_hooks = false`.

Out of scope, note it and leave it: `~/.claude/CLAUDE.md`, the plugin
`SessionStart` hooks (3 fired in that same log) and `settings.json`
(`effortLevel`, `alwaysThinkingEnabled`) also reach every stage. Whether the
pipeline should inherit those is a design question, not a bug, and it needs a
human decision. This ticket is only about the toolset.

Triage reproduced it and committed a failing test, `8dcda2c`. The test asserts
that both claude-code command templates carry `--strict-mcp-config`; neither
does. The leak itself is confirmed from a recorded `init` event, which grants
53 tools from 9 MCP servers -- not 78. See `## Reproduction`.

## Reproduction

`tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers`

Command:

    uv run --group dev pytest -q tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers

Failure output:

    >           assert "--strict-mcp-config" in hcfg[key], \
                    f"claude-code {key} lets ~/.claude MCP servers into the session"
    E           AssertionError: claude-code cmd lets ~/.claude MCP servers into the session
    E           assert '--strict-mcp-config' in 'claude -p --model {model} ...'

    tests/test_harness.py:193: AssertionError
    1 failed, 9 passed in 0.13s

expect: AssertionError: claude-code cmd lets ~/.claude MCP servers into the session

The test asserts on the harness template, not on a live session, because a
session's real toolset needs an account, a network call and money. The leak
itself is confirmed from the recorded run named in `## Summary`,
`.project/logs/TICKET-024-planning-57906f4b.log`, whose `init` event reads:

    tools: 53
    mcp: ['github', 'context7', 'mermaid-mcp', 'godot', 'excalidraw',
          'claude.ai Linear', 'claude.ai Gmail', 'claude.ai Google Calendar',
          'claude.ai Google Drive']
    sample: ['mcp__claude_ai_Gmail__apply_sensitive_message_label',
             'mcp__claude_ai_Gmail__apply_sensitive_thread_label',
             'mcp__claude_ai_Gmail__create_draft',
             'mcp__claude_ai_Gmail__create_label']

The same log's command line asked for `--tools "Read,Grep,Glob,Bash,Edit,Write,Skill"`.

One correction to `## Summary`: that log grants 53 tools, not 78. The count is
the only figure that differs; the servers, the Gmail names and the leak are as
reported. 78 may come from a different run or a different machine.

`claude --help` confirms the flag: `--strict-mcp-config  Only use MCP servers
from --mcp-config, ignoring all other MCP configurations`. Nobody has yet run a
session with the flag to check `init.tools` against it -- that is the
acceptance criterion the ticket sets, and it belongs to a later stage.

## Digest

Files touched: `pipeline/harnesses/claude-code.toml` only. Both command
templates in it, `cmd` and `interactive_cmd`, need the same two words.

Key functions, none of which changes: `config.render()`
(`pipeline/core/config.py:74`) fills the template; `config._tools()`
(`pipeline/core/config.py:120`) builds `{tools}` from the stage's `write` flag;
`config.stage_settings()` (`pipeline/core/config.py:132`) writes the hooks
settings file. Entry point: `supervisor.spawn()` calls `render()` at
`pipeline/daemon/supervisor.py:302` with `key="interactive_cmd" if interactive
else "cmd"`. Nothing else in `pipeline/` builds a claude command line.

The exact edit. In `pipeline/harnesses/claude-code.toml`, the line

    --tools "{tools}" \

becomes

    --tools "{tools}" --strict-mcp-config \

in `cmd` and again in `interactive_cmd`.

Measured, not assumed. Planning ran three live sessions on
`claude-haiku-4-5-20251001` and read the `init` event. With the pipeline's own
flag set (`--tools "Read,Grep,Glob,Bash,Edit,Write,Skill" --strict-mcp-config
--permission-mode bypassPermissions --max-budget-usd 0.05 --add-dir /tmp --`):

    {"n":7,"tools":["Bash","Edit","Glob","Grep","Read","Skill","Write"],"mcp":[],"pm":"bypassPermissions"}

The same command without `--strict-mcp-config`:

    {"n":68,"mcp":["github","context7","mermaid-mcp","godot","excalidraw","claude.ai Linear","claude.ai Gmail","claude.ai Google Calendar","claude.ai Google Drive"],"sample":["mcp__claude_ai_Gmail__apply_sensitive_message_label","mcp__claude_ai_Gmail__apply_sensitive_thread_label","mcp__claude_ai_Gmail__create_draft"]}

That is the ticket's acceptance criterion already met, and it also proves the
flag does not break the command -- the failure mode this file's `--` comment
was written for. Implementing does not need to spend money repeating it.

Gotchas:

1. `--tools <tools...>` is variadic, like `--add-dir`. `--strict-mcp-config`
   starts with `-`, so it ends the list rather than joining it. The live run
   above used exactly this adjacency and `init.tools` held 7 names, not 8.
2. `--strict-mcp-config` needs no `--mcp-config` partner. With none passed the
   allowed set is empty, which is what `"mcp":[]` above shows.
3. `claude mcp list` ignores the flag -- it reads the config files directly and
   printed all 9 servers either way. Do not use it to check this; read an
   `init` event.
4. Do not reach for `--bare`. It skips hooks, and `spawn()` already refuses a
   stage that cannot register `dangerous-commands.py`.
5. The gate re-runs the named test and requires it to fail with the recorded
   `expect:` string. Do not touch `tests/test_harness.py` before the fix lands.
6. `slash commands: 97` still load with the flag on. Out of scope, see below.

## Decisions checked

None constrains this change. Grep terms over
`/home/chezzijr/proj/claude-setup/.project/decisions/`: `mcp`, `MCP`, `tools`,
`harness`, `toolset`, `claude-code`, `hook`, `guard`, `allowlist`,
`permission`, `prompt`, `strict`, `inherit`, `~/.claude`, `settings.json`.

Consulted: DEC-011, which freezes the event vocabulary and lists `init` as
`{model, tools, permission_mode, capabilities, ...}`. It is why the acceptance
criterion can be read off a log at all. It constrains the event schema, not the
command line, and this change adds no event. DEC-018, which sets the Tier A
gate's rules for this document. Neither carries a `superseded-by:` line.

## Plan

1. Run `uv run --group dev pytest -q tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers` and confirm it fails with `AssertionError: claude-code cmd lets ~/.claude MCP servers into the session`, which is the assertion that `pipeline/harnesses/claude-code.toml` carries no `--strict-mcp-config`.
2. In `pipeline/harnesses/claude-code.toml`, in the `cmd` template, replace the line `--tools "{tools}" \` with `--tools "{tools}" --strict-mcp-config \`.
3. In `pipeline/harnesses/claude-code.toml`, in the `interactive_cmd` template, replace the line `--tools "{tools}" \` with `--tools "{tools}" --strict-mcp-config \`.
4. Above the `cmd` assignment in `pipeline/harnesses/claude-code.toml`, add a comment block recording: `--tools` restricts the built-in set only; TICKET-024's planning asked for 7 tools and its `init` granted 53 from 9 `~/.claude` servers including Gmail; the guard's `matcher: "Bash"` covers none of them; the measured before/after from `## Digest` (68 tools and 9 servers without the flag, `["Bash","Edit","Glob","Grep","Read","Skill","Write"]` and `[]` with it, `claude-haiku-4-5-20251001`, 2026-08-21); and that `--bare` is not the alternative because it skips hooks.
5. Re-run `uv run --group dev pytest -q tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers` and confirm it passes, proving `pipeline/harnesses/claude-code.toml` now carries the flag in both templates.
6. Run `uv run --group dev pytest -q` and then `./pipeline/hooks/test_dangerous_commands.py`, and confirm both are green, since `pipeline/harnesses/claude-code.toml` is read by four other tests in `tests/test_harness.py`.
7. Commit `pipeline/harnesses/claude-code.toml` with the message `fix: a stage no longer inherits the developer's mcp servers`.

## Acceptance criteria

1. `tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers` passes. It asserts the flag is present in both `cmd` and `interactive_cmd`, so criterion 2 rides on the same test.
2. Both templates carry the flag, not just the headless one. Same test, which loops `for key in ("cmd", "interactive_cmd")`.
3. The rest of the suite stays green: `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`. The four other tests in `tests/test_harness.py` that read this harness (`test_the_prompt_survives_a_variadic_flag` in particular, which checks the `--` still ends the flags) are the ones that can break.
4. A live session started with the pipeline's flag set reports an `init` event whose `tools` list is exactly the declared names and whose `mcp_servers` is empty. Met in planning; the evidence is quoted verbatim in `## Digest`. To re-check, run `claude -p --model claude-haiku-4-5-20251001 --output-format stream-json --verbose --tools "Read,Grep" --strict-mcp-config --max-budget-usd 0.05 -- "reply with the single word ok"` and read the `subtype == "init"` line.

## Decisions

`--strict-mcp-config` in both `claude-code.toml` templates is the only thing
stopping the developer's `~/.claude` MCP servers from loading into every stage.
Remove it and a stage that declared 7 tools gets 68, including
`mcp__claude_ai_Gmail__send_message`, and the same ticket runs differently on
two machines. The guard registers `PreToolUse` with `matcher: "Bash"`, so it
promises nothing about an `mcp__*` tool name -- the flag is prevention, and
there is no detection behind it.

`--tools` does not do this job. It restricts the built-in set only; that is the
measurement in the ticket, not a reading of the help text.

`--bare` is not the cheaper version of this. It disables hooks too, and a stage
that cannot register `dangerous-commands.py` must be refused rather than run
unguarded -- `spawn()` already refuses exactly that case for a harness with
`supports_hooks = false`.

If a stage ever needs a real MCP server, pass `--mcp-config` with a file the
pipeline owns. Keep `--strict-mcp-config`: the point is that the harness names
the servers, not that there are none.

## Rollback

Revert the one commit that touches `pipeline/harnesses/claude-code.toml`, or
delete the two `--strict-mcp-config` occurrences. Nothing else changes: no
Python, no stage prompt, no event, no stored data. A stage then inherits the
developer's MCP servers again, which is the pre-fix behaviour, so the revert is
safe to do in a hurry.

## Thread

### 2026-08-21 08:33:54Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 · triage · result=ok

Reproduced. Test committed as `8dcda2c` on `ticket/025`:
`tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers`.
It fails with `AssertionError: claude-code cmd lets ~/.claude MCP servers into
the session`.

What I checked:

1. `pipeline/core/config.py:120` `_tools()` builds `--tools` from the stage's
   `write` flag. Nothing in `render()` or `spawn()` mentions MCP.
2. `pipeline/harnesses/claude-code.toml` passes `--tools` in both `cmd` and
   `interactive_cmd`, and no MCP flag in either.
3. `.project/logs/TICKET-024-planning-57906f4b.log` `init` event: 53 tools, 9
   MCP servers, Gmail among them. Verbatim output is in `## Reproduction`.
4. `claude --help` lists `--strict-mcp-config`.

Two notes for later stages:

- The count in the report is 78; the log I found says 53. Same servers, same
  Gmail tools. The discrepancy is in the number only.
- The test asserts on the harness template, not on a live `init` event. A live
  check needs an account and money, so the ticket's acceptance criterion --
  `init.tools` contains only the declared names -- stays unverified until a
  stage runs one. Say so rather than assuming the flag works.

Out of scope, noticed, not touched: the guard registers `PreToolUse` with
`matcher: "Bash"` only (`pipeline/core/config.py:139`), so even with MCP gone
it guards one tool name. Pyright reports `tests/test_harness.py:88: "prompt" is
not accessed` in pre-existing code.

### 2026-08-21 08:36:06Z · triage · session · session=e22c1472-c23e-40bc-8b16-0ce807ed03fe

`triage` ran as session `e22c1472-c23e-40bc-8b16-0ce807ed03fe`
- replay: `claude --resume e22c1472-c23e-40bc-8b16-0ce807ed03fe`
- log: `.project/logs/TICKET-025-triage-e22c1472.log`

### 2026-08-21 08:36:06Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

✓ reproduced: claude-code templates carry no --strict-mcp-config, so a stage inherits 53 tools from 9 ~/.claude MCP servers; failing test committed as 8dcda2c

### 2026-08-21 · planning · result=ok

Plan written. One file, `pipeline/harnesses/claude-code.toml`, two words in
each of its two command templates.

I did not stop at the flag name. Three live sessions on
`claude-haiku-4-5-20251001` settle the ticket's own acceptance criterion:

    with    --strict-mcp-config: {"n":7,"tools":["Bash","Edit","Glob","Grep","Read","Skill","Write"],"mcp":[],"pm":"bypassPermissions"}
    without --strict-mcp-config: {"n":68,"mcp":["github","context7","mermaid-mcp","godot","excalidraw","claude.ai Linear","claude.ai Gmail","claude.ai Google Calendar","claude.ai Google Drive"]}

The first used the pipeline's full flag set, including `--permission-mode
bypassPermissions`, `--add-dir` and the `--`. The flag does the job, and it
does not break the command -- the failure mode `claude-code.toml`'s own `--`
comment exists to warn about. Implementing does not need to spend money
repeating this.

Three notes for later stages:

1. The report's count of 78 is wrong on this machine. Today it is 68, and the
   TICKET-024 log says 53. The servers and the Gmail tool names match in all
   three. I rewrote `## Summary` to say 68 and to record the discrepancy.
2. `claude mcp list` prints all 9 servers with the flag on. That subcommand
   reads the config files, not the session. Check an `init` event instead.
3. Do not touch `tests/test_harness.py` before the fix lands. The gate re-runs
   the named test and requires it to fail with the recorded `expect:` string.

Out of scope, seen, untouched. `slash commands: 97` still load with the flag
on, and so do `~/.claude/CLAUDE.md`, the plugin `SessionStart` hooks and
`settings.json`. The ticket rules those a design question for a human. The
guard still registers `PreToolUse` with `matcher: "Bash"` only
(`pipeline/core/config.py:139`); with MCP gone that matcher is no longer a
hole, but it is still one matcher.

### 2026-08-21 08:42:38Z · planning · session · session=f03b03ad-899c-434d-a332-7ddc8e2a6e32

`planning` ran as session `f03b03ad-899c-434d-a332-7ddc8e2a6e32`
- replay: `claude --resume f03b03ad-899c-434d-a332-7ddc8e2a6e32`
- log: `.project/logs/TICKET-025-planning-f03b03ad.log`

### 2026-08-21 08:42:38Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

✓ plan written: add --strict-mcp-config to both claude-code.toml templates; verified live that init.tools then holds only the 7 declared names and mcp_servers is []

### 2026-08-21 08:44:43Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers` fails as required
```
 them, and the same ticket runs differently on two machines.
    
        `--strict-mcp-config` limits a session to the servers named by
        `--mcp-config`, i.e. none. Both templates carry `--tools`, so both need it."""
        hcfg = config.harness("claude-code")
        for key in ("cmd", "interactive_cmd"):
>           assert "--strict-mcp-config" in hcfg[key], \
                f"claude-code {key} lets ~/.claude MCP servers into the session"
E           AssertionError: claude-code cmd lets ~/.claude MCP servers into the session
E           assert '--strict-mcp-config' in 'claude -p --model {model} {effort_flag} {session_flag} {settings_flag} --output-format stream-json --verbose --append...ax-budget-usd {cap} --add-dir {project} -- "Work ticket {id}. Read {ticket} first. When finished write {result_file}" '

tests/test_harness.py:193: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers` fails on base `main` too -- the bug is not already fixed upstream
```
           assert '--strict-mcp-config' in 'claude -p --model {model} {effort_flag} {session_flag} {settings_flag} --output-format stream-json --verbose --append...ax-budget-usd {cap} --add-dir {project} -- "Work ticket {id}. Read {ticket} first. When finished write {result_file}" '

tests/test_harness.py:193: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.12s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-cl6y3ms7/base
      Built pipeline @ file:///tmp/pipeline-base-cl6y3ms7/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 · plan-validation · result=ok

Plan passes all eight items. Scoring, one line of reasoning each.

1. **Root cause, not symptom.** In my words: the claude-code command templates
   never restrict MCP configuration, so the CLI loads every server in the
   developer's `~/.claude` whatever `--tools` says -- `--tools` governs the
   built-in set only. The fix edits the command line, which is the single place
   a claude session is constructed: `render()` (`pipeline/core/config.py:74`)
   fills the template and `spawn()` (`pipeline/daemon/supervisor.py:302`) is its
   only caller. I confirmed the leak myself rather than taking the ticket's
   word. The `init` event of
   `.project/logs/TICKET-024-planning-57906f4b.log` reads:

       "tools":["Bash","Edit","Glob","Grep","Read","Skill","Write",
                "mcp__claude_ai_Gmail__apply_sensitive_message_label",
                "mcp__claude_ai_Gmail__apply_sensitive_thread_label",
                "mcp__claude_ai_Gmail__create_draft", ...

2. **Decision conflict: none.** I grepped `mcp|MCP|strict|harness|toolset` over
   `.project/decisions/` and no file matched. No decision's `files:` line names
   `pipeline/harnesses/claude-code.toml`. DEC-011 is cited correctly -- line 75
   is `| `init` | 012 | `{model, tools, permission_mode, capabilities, ...}` |`
   -- and it constrains the event schema, which this change does not touch.
   Neither DEC-011 nor DEC-018 carries a `superseded-by:` line.
3. **Scope discipline: one step is untraceable, and I accept it.** Steps 1-3
   and 5-7 map to criteria 1-3. Step 4 adds a comment block that no criterion
   names and no test can check. It changes no behaviour, it lands in the one
   declared file, and it records the measurement. Not grounds to bounce.
4. **Criteria are falsifiable.** The test loops
   `for key in ("cmd", "interactive_cmd")`, so an implementation that edits only
   the headless template fails on the second key. The test reads the parsed TOML
   value `hcfg[key]`, not the file text.
5. **No research left.** Step 2 and step 3 quote the line to replace, and
   `--tools "{tools}" \` is on `pipeline/harnesses/claude-code.toml:73` and
   `:89`, verbatim as written.
6. **Riskiest step: 2 and 3, the flag reaching a real session.** Two ways it
   could go wrong -- the variadic `--tools` swallowing the flag, and the flag
   breaking the command. `## Digest` gotcha 1 answers both from a live run at
   this exact adjacency: `init.tools` held 7 names, not 8. `## Rollback` states
   the fallback: revert the one commit, or delete the two occurrences.
7. **Regression surface: the four other tests that read this harness.**
   `test_the_prompt_survives_a_variadic_flag` is the one that can break, and the
   edit keeps `--` as the last token before the positional prompt.
   `test_claude_code_render_is_unchanged_by_the_extraction` asserts substrings,
   not string equality. Nothing outside `tests/test_harness.py` reads `--tools`;
   the end-to-end tests use `fake.toml`. Untested regression: a stage that
   legitimately needs an MCP server loses it. `## Decisions` answers that --
   pass `--mcp-config` with a file the pipeline owns.
8. **Blast radius matches `bugfix`.** One file, two words, plus a comment.

One hazard I add for step 4. Put the comment block above the `cmd` assignment,
outside the `"""` string. Inside the string it would break the command and
satisfy the test in the same edit, because the test asserts on `hcfg["cmd"]`.

Out of scope, seen, untouched: the guard still registers `PreToolUse` with
`matcher: "Bash"` only (`pipeline/core/config.py:139`).

One citation is off by one: `## Digest` gives `stage_settings()` as
`pipeline/core/config.py:132`; the `def` is on line 131.

The guard blocked three of my commands: `sed -n`, `cd`, and a `python3 -c`
heredoc-style pipeline ("command does not parse as a shell command"). I read
the files another way. No workaround, nothing missing from this analysis.

### 2026-08-21 08:47:21Z · plan-validation · session · session=52227449-1765-4e7b-a6c1-afe0fa8f6dd3

`plan-validation` ran as session `52227449-1765-4e7b-a6c1-afe0fa8f6dd3`
- replay: `claude --resume 52227449-1765-4e7b-a6c1-afe0fa8f6dd3`
- log: `.project/logs/TICKET-025-plan-validation-52227449.log`

### 2026-08-21 08:47:21Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items: root cause is the harness command line, no decision constrains it, criteria are falsifiable, blast radius is one file

### 2026-08-21 08:49:56Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 08:50:07Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers` fails as required
```
 them, and the same ticket runs differently on two machines.
    
        `--strict-mcp-config` limits a session to the servers named by
        `--mcp-config`, i.e. none. Both templates carry `--tools`, so both need it."""
        hcfg = config.harness("claude-code")
        for key in ("cmd", "interactive_cmd"):
>           assert "--strict-mcp-config" in hcfg[key], \
                f"claude-code {key} lets ~/.claude MCP servers into the session"
E           AssertionError: claude-code cmd lets ~/.claude MCP servers into the session
E           assert '--strict-mcp-config' in 'claude -p --model {model} {effort_flag} {session_flag} {settings_flag} --output-format stream-json --verbose --append...ax-budget-usd {cap} --add-dir {project} -- "Work ticket {id}. Read {ticket} first. When finished write {result_file}" '

tests/test_harness.py:193: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers` fails on base `main` too -- the bug is not already fixed upstream
```
E           assert '--strict-mcp-config' in 'claude -p --model {model} {effort_flag} {session_flag} {settings_flag} --output-format stream-json --verbose --append...ax-budget-usd {cap} --add-dir {project} -- "Work ticket {id}. Read {ticket} first. When finished write {result_file}" '

tests/test_harness.py:193: AssertionError
=========================== short test summary info ============================
FAILED tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.12s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-tpabj60y/base
      Built pipeline @ file:///tmp/pipeline-base-tpabj60y/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-21 08:50:07Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 · implementing · result=ok

Todo, one entry per plan step, all done:

1. [x] run named test, confirm it fails with the recorded `AssertionError`
2. [x] add `--strict-mcp-config` to `cmd` template
3. [x] add `--strict-mcp-config` to `interactive_cmd` template
4. [x] add comment block above `cmd`, outside the `"""` string
5. [x] re-run named test, confirm it passes
6. [x] run full suite + guard script, confirm both green
7. [x] commit

Step 1: ran `uv run --group dev pytest -q tests/test_harness.py::test_a_stage_does_not_inherit_the_developers_mcp_servers`,
failed with `AssertionError: claude-code cmd lets ~/.claude MCP servers into
the session`, matching `## Reproduction`'s `expect:` string.

Steps 2-3: in `pipeline/harnesses/claude-code.toml`, changed
`--tools "{tools}" \` to `--tools "{tools}" --strict-mcp-config \` in both
`cmd` and `interactive_cmd`. Same line text, two occurrences, verified by grep
before editing that each appeared once per template.

Step 4: added an 8-line `#` comment block directly above the `cmd = """`
line, above and outside the triple-quoted string, recording the root cause,
the measured before/after counts, and why `--bare` is not the alternative --
same content the plan specified from `## Digest`.

Step 5: re-ran the named test, passed, `1 passed in 0.03s`.

Step 6: `uv run --group dev pytest -q` -> `181 passed in 8.45s`.
`./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`, every
line `ok`.

Step 7: committed `pipeline/harnesses/claude-code.toml` as `8a2b1fc`,
message `fix: a stage no longer inherits the developer's mcp servers`,
`1 file changed, 11 insertions(+), 2 deletions(-)`.

Plan executed exactly as written. No deviation, no blocked step.

### 2026-08-21 08:51:12Z · implementing · session · session=5db022aa-9835-43ab-be56-8c32f10bc87a

`implementing` ran as session `5db022aa-9835-43ab-be56-8c32f10bc87a`
- replay: `claude --resume 5db022aa-9835-43ab-be56-8c32f10bc87a`
- log: `.project/logs/TICKET-025-implementing-5db022aa.log`

### 2026-08-21 08:51:12Z · implementing · transition · to=review · result=ok

**implementing -> review** (result: `ok`)

✓ added --strict-mcp-config to both claude-code.toml templates; named test, full suite (181), and guard script all pass; committed as 8a2b1fc

### 2026-08-21 · review · result=ok

Passed. The delta is `main...HEAD`: two commits, two files.
`pipeline/harnesses/claude-code.toml` (+11/-2) and `tests/test_harness.py`
(+17). No blocking finding.

What I verified against `## Acceptance criteria`:

1. Criteria 1 and 2. Both templates carry the flag, on
   `pipeline/harnesses/claude-code.toml:82` and `:98`, each as
   `--tools "{tools}" --strict-mcp-config \`. The named test passes.
2. Criterion 3. `uv run --group dev pytest -q` -> `181 passed in 8.34s`.
   `uv run --group dev pytest -q tests/test_harness.py -v` ->
   `10 passed in 0.04s`, so `test_the_prompt_survives_a_variadic_flag` and
   `test_claude_code_render_is_unchanged_by_the_extraction` both hold.
3. Criterion 4 stays as planning measured it. I did not run a live session; it
   costs money and the evidence is quoted in `## Digest`.
4. Plan step 4. The comment block is on lines 70-78, above `cmd = """` and
   outside the string. It records all five facts the step names: `--tools`
   covers built-ins only, 7 asked and 53 granted from 9 servers, the guard's
   `matcher: "Bash"`, the measured 68-vs-7 before/after, and why `--bare` is
   not the alternative.
5. Working tree clean. `git status --porcelain` printed nothing.

Non-blocking findings:

1. **minor.** `pipeline/harnesses/codex.toml:34` is
   `cmd = """codex exec --model {model} --sandbox {tools} {prompt}"""` and
   restricts no MCP configuration either. A codex stage still inherits the
   developer's servers. Out of this ticket's scope -- `files_declared` names
   `claude-code.toml` only. It needs its own ticket, and codex's flag is not
   `--strict-mcp-config`.
2. **minor.** Planning measured the flag under `-p` only. `interactive_cmd`
   drops `-p`, so its `init` is unmeasured. `--strict-mcp-config` is a global
   CLI flag, so the risk is low, and an interactive stage is the one a human
   watches.
3. **info.** This review session was granted 9 `~/.claude` MCP servers:
   `github`, `context7`, `mermaid-mcp`, `godot`, `excalidraw`, `claude.ai
   Linear`, `claude.ai Gmail`, `claude.ai Google Calendar`, `claude.ai Google
   Drive`. That is expected, not a regression. `config.harness()` reads
   `HARNESSES_DIR / "claude-code.toml"` from the package the dispatcher runs
   (`pipeline/core/config.py:46`), not from this worktree. The fix takes effect
   after the merge, and after `uv tool install .` if `pipeline` is installed
   that way. Worth telling the human at the merge gate.
4. **info.** I could not run `./pipeline/hooks/test_dangerous_commands.py`. The
   guard rejected it twice: "`test_dangerous_commands.py` is not on the
   read-only allowlist", then "python3: only `-m nox/pytest/tox/unittest` is
   allowed". The delta changes no guard code and no shell parsing.
   `implementing` reports `guard: all passed`.
5. **nit.** The new comment block starts on line 70 with no blank `#` line
   after line 69, "Both flags exist in `claude --help` ...", so it reads as a
   continuation of the "Deliberately NOT here" list above it. One `#` would
   separate them. Not worth a commit on its own.

The guard also blocked `cd`, `sed -n`, `claude --help` and a heredoc append for
me. I read and wrote the files with the file tools instead. Nothing is missing
from this review.

### 2026-08-21 08:54:22Z · review · session · session=ad04b1ea-a615-46cd-999f-75566d7c6cbf

`review` ran as session `ad04b1ea-a615-46cd-999f-75566d7c6cbf`
- replay: `claude --resume ad04b1ea-a615-46cd-999f-75566d7c6cbf`
- log: `.project/logs/TICKET-025-review-ad04b1ea.log`

### 2026-08-21 08:54:22Z · review · transition · to=verifying · result=ok

**review -> verifying** (result: `ok`)

✓ delta passes: both claude-code templates carry --strict-mcp-config, 181 tests green, no blocking finding; 5 non-blocking notes in the thread

### 2026-08-21 08:54:31Z · verifying · transition · to=merging · result=ok

**verifying -> merging** (result: `ok`)

regression suite exit 0
```
...HEAD
ok  allow [always] cargo build --release
ok  BLOCK [readonly] sed -i s/a/b/ x.py
ok  BLOCK [readonly] echo hi > file.txt
ok  BLOCK [readonly] git commit -am wip
ok  BLOCK [readonly] cp a b
ok  BLOCK [readonly] pip install requests
ok  BLOCK [readonly] mv a b
ok  BLOCK [readonly] python3 -c "open('/tmp/x','a').write(1)"
ok  BLOCK [readonly] git -C . commit -am wip
ok  BLOCK [readonly] pytest 2>out
ok  BLOCK [readonly] pytest >> log.txt
ok  BLOCK [readonly] git worktree add /tmp/x main
ok  BLOCK [readonly] python3 setup.py install
ok  BLOCK [readonly] tee /tmp/x
ok  BLOCK [readonly] curl https://example.com -o /tmp/x
ok  BLOCK [readonly] make install
ok  BLOCK [readonly] cargo run
ok  BLOCK [readonly] npm install
ok  BLOCK [readonly] echo $(whoami)
ok  allow [readonly] pytest -x
ok  allow [readonly] git diff main...HEAD
ok  allow [readonly] grep -rn foo .
ok  allow [readonly] git log --oneline
ok  allow [readonly] cat thing.py
ok  allow [readonly] python3 -m pytest --deselect x
ok  allow [readonly] ls -la
ok  allow [readonly] git show HEAD
ok  allow [readonly] git blame thing.py
ok  allow [readonly] rg evict src/
ok  allow [readonly] pytest -x 2>&1
ok  allow [readonly] find . -name '*.py'
ok  allow [readonly] cargo test
ok  allow [readonly] go test ./...
ok  allow [readonly] git status --porcelain
ok  allow [readonly] wc -l thing.py
ok  allow [readonly] python3 -m unittest
ok  allow [readonly] git diff main...HEAD | head -50
ok  end-to-end exit codes

guard: all passed

```

### 2026-08-21 08:54:32Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/025


Merge made by the 'ort' strategy.
 pipeline/stages/holistic-review.md |  3 +++
 pipeline/stages/implementing.md    |  3 +++
 pipeline/stages/plan-validation.md |  3 +++
 pipeline/stages/planning.md        |  3 +++
 pipeline/stages/review.md          |  3 +++
 pipeline/stages/triage.md          |  2 ++
 tests/test_stages.py               | 17 +++++++++++++++++
 7 files changed, 34 insertions(+)
Updating bd83d0d..e74dbaa
Fast-forward
 pipeline/harnesses/claude-code.toml | 13 +++++++++++--
 tests/test_harness.py               | 17 +++++++++++++++++
 2 files changed, 28 insertions(+), 2 deletions(-)

```

### 2026-08-21 08:54:32Z · merging · decision

decision recorded as `DEC-025`
