---
id: TICKET-057
stage: planning
class: bugfix
branch: ticket/057
test_file: pipeline/hooks/test_dangerous_commands.py
files_declared: []
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 0
  plan_files: 0
  no_result: 0
lease:
  holder: planning-1115322
  expires: '2026-08-24T15:35:51.712053+00:00'
last_session:
  stage: triage
  id: 6b0a4a1d-4968-4f30-a680-49966836cd1e
  log: .project/logs/TICKET-057-triage-6b0a4a1d.log
---

## Summary

the guard blocks two things it means to allow: sed, and any multi-line command

Two defects in `pipeline/hooks/dangerous-commands.py`, filed as one ticket
because they are the same file and `files_conflict` would serialise two anyway.
Both are false blocks: the policy each defends is right, the mechanism refuses
work the policy allows. Counting block reasons across `.project/logs` (inflated
--- a stage pastes the block line back into its ticket --- so read it as a
ranking, not a count): `command does not parse` 540, `sed -n: not an allowed
subcommand` 314, then the three reasons that are the guard working correctly.

**1. `sed` is in `GUARDED` with an empty set, so every sed is blocked.**

    $ echo '{"tool_name":"Bash","tool_input":{"command":"sed -n '"'"'10,20p'"'"' README.md"}}' \
        | PIPELINE_READONLY=1 PIPELINE_STAGE=review ./pipeline/hooks/dangerous-commands.py
    Blocked by the pipeline guard (review): sed -n: not an allowed subcommand.

`awk` is in `READ_TOOLS`; `sed` is not. It is in `GUARDED` as `"sed": set()`,
and an empty set matches no first argument, so `sed -n '1,20p' f` --- a pure
read, and the ordinary way to read a line range --- is refused. The intent is
in the file twice, contradicting itself: the `GUARDED` entry is commented
`# only reaches here if -i was already rejected below`, and the branch it
refers to (`if name == "sed" and any(a.startswith("-i") ...)`) sits behind
`if name in READ_TOOLS or name in TEST_RUNNERS:`, which `sed` never enters.
That branch is unreachable today.

**2. `segments()` splits on `\n` before lexing, so a newline inside a quoted
string is treated as a command separator.** This one blocks write stages too:

    $ ... {"command":"uv run python -c \"\nfrom pipeline.core.machine import BOUNDS\nprint(BOUNDS)\n\""}
      PIPELINE_STAGE=implementing   # no PIPELINE_READONLY
    Blocked by the pipeline guard (implementing): command does not parse as a shell command.

`segments()` (`pipeline/hooks/dangerous-commands.py:65`) does
`command.split("\n")` and lexes each line separately, so the quote opens on one
line and never closes; `shlex` raises, `segments()` returns `None`, and
`verdict()` blocks. A heredoc (`python3 - <<PY ... PY`) is unaffected --- only
the quoted form dies. The behaviour is fail-closed, so this is friction and not
a hole, but the reason given is false: the command parses fine as shell.

Expected: `sed` with read-only arguments is allowed in a read-only stage and
`sed -i` is still refused, with the `-i` branch actually reached. A command
whose only newlines are inside a quoted string is judged on what it runs, in
both modes. Everything else blocked today stays blocked --- in particular
`python3 -c` in a read-only stage (arbitrary code is a write), redirection into
a file, and `cd`.

Prior art, checked 2026-08-24, for the second one specifically. Codex parses
with tree-sitter-bash (`codex-rs/shell-command/src/bash.rs`), permits only
`&& || ; |` between commands, refuses subshells, redirection and background,
and returns `None` on `tree.root_node().has_error()` --- the same fail-closed
posture this guard has. It accepts newlines inside a double-quoted string,
which is exactly the case that fails here. Suggestion only, planning decides:
`shlex` tracks `lex.lineno`, so reading tokens one at a time and starting a
segment when the line number advances keeps this stdlib-only. A parser
dependency is a fourth runtime dependency and `CLAUDE.md` puts the budget at
three.

Not in scope, recorded because it came up: Codex and Claude Code both answer
"uncertain" with a third outcome, `prompt`, and this guard has only allow and
block. A headless stage has nobody to ask, and `needs-input` is already the
stage-level form of it. No change wanted here.

This file is in `machine.FENCED` and `CLAUDE.md` requires human review of a
guard change whatever the pipeline says, so this ticket parks at
`awaiting-merge` by design.

`./pipeline/hooks/test_dangerous_commands.py` must be run directly --- pytest
collects only its two `test_*` functions and misses the allow/block tables,
which are what would catch a regression here.

## Reproduction

Test: `pipeline/hooks/test_dangerous_commands.py` (ALLOWED_READONLY table), added cases
`sed 's/a/b/' thing.py` and `pytest -x \` + newline + `tests/test_x.py`.
Command: `./pipeline/hooks/test_dangerous_commands.py`
Failure:
```
AssertionError: readonly: "sed 's/a/b/' thing.py" -> 'sed s/a/b/: not an allowed subcommand' (expected allow)
```
expect: sed s/a/b/: not an allowed subcommand

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-24 15:04:27Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

### 2026-08-24 · triage · reproduced · result=ok

Both defects confirmed by direct calls to `guard.verdict()`:

1. `sed` is unconditionally blocked in read-only mode, even with no `-i`. In
   `readonly_rules()`, `GUARDED["sed"] = set()` (empty). The `args[0] not in
   GUARDED[name]` check can never pass for `sed` since the allowed-subcommand
   set is empty, so every `sed` invocation falls through to "not an allowed
   subcommand". The `-i` rejection meant to gate this lives in the
   `READ_TOOLS`/`TEST_RUNNERS` branch above, but `sed` is not in `READ_TOOLS`,
   so that branch never runs for `sed`.
2. A backslash-continued multi-line command fails to parse. `segments()`
   splits the raw command on `\n` and lexes each line independently; a
   trailing `\` at end-of-line (shell line continuation) has no following
   character on that line, and `shlex` in posix mode raises `ValueError` on
   the dangling escape, so `segments()` returns `None` and `verdict()` reports
   "command does not parse as a shell command".

Added failing cases to `ALLOWED_READONLY` in
`pipeline/hooks/test_dangerous_commands.py`: `sed 's/a/b/' thing.py` and a
backslash-continued `pytest -x \` / `tests/test_x.py`. Ran
`./pipeline/hooks/test_dangerous_commands.py`; it fails on the `sed` case
first (the loop stops at the first assertion failure) with the text recorded
in `## Reproduction`. Committed on `ticket/057` as `ba02019`.

`pipeline/hooks/dangerous-commands.py` is on the FENCED list in
`CLAUDE.md` and requires human review before merge regardless of fix size, so
`result: ok` rather than `chore` even though the eventual fix is likely small
(fix `GUARDED["sed"]`/its allowlist branch, and make `segments()` rejoin a
`\`-continued line before lexing). Files this ticket will touch:
`pipeline/hooks/dangerous-commands.py`,
`pipeline/hooks/test_dangerous_commands.py`.

dispatcher pickup

### 2026-08-24 15:05:51Z · triage · session · session=6b0a4a1d-4968-4f30-a680-49966836cd1e

`triage` ran as session `6b0a4a1d-4968-4f30-a680-49966836cd1e`
- replay: `claude --resume 6b0a4a1d-4968-4f30-a680-49966836cd1e`
- log: `.project/logs/TICKET-057-triage-6b0a4a1d.log`

### 2026-08-24 15:05:51Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced both guard bugs (sed always blocked, backslash-continued multi-line commands fail to parse); committed failing test ba02019.
