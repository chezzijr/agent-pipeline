---
id: TICKET-036
stage: new
class: feature
branch: ticket/036
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a stage cannot be given an MCP server, and the guard would not cover one if it could

The harness passes `--strict-mcp-config` with no `--mcp-config`, so every stage
runs with `mcp_servers: []` -- confirmed in the live TICKET-034 triage run. That
is deliberate: `pipeline/harnesses/claude-code.toml` records that without the
flag, TICKET-024's `planning` was granted 53 tools from 9 of the operator's MCP
servers, Gmail among them.

The blocker is not the flag, it is the guard. `stage_settings()`
(`pipeline/core/config.py:158`) registers the hook as:

    {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": entries}]}}

An MCP tool is named `mcp__<server>__<tool>` and never matches `Bash`, and
`--tools` does not restrict MCP either. So an MCP server today would be an
unguarded path around invariant 4, which is why it is off rather than
unconfigured.

Expected: a project can declare its own MCP servers and a stage can opt into
them, without any stage gaining a tool the guard cannot see. The falsifiable
check is a stage with a declared server whose MCP tool call reaches
`dangerous-commands.py` (or is refused), rather than executing unobserved.

Three things planning should weigh rather than have decided here: where the
config lives (`.project/pipeline.toml` is the only per-project seam today, and
TICKET-035 may add another); whether `matcher` becomes a regex like
`"Bash|mcp__.*"` -- note `dangerous-commands.py` parses shell commands and has
no idea what `mcp__github__create_pr` does, so a per-server allowlist may be
the honest shape; and whether read-only servers (docs lookup, search) are
worth separating from writing ones, since only the latter reintroduce the risk
the read-only allowlist exists to prevent.

Cost, not just safety: each server pays its tool schemas on every turn, which
is the same budget the 2026-08-22 harness change bought back.

This changes how the guard is registered, so it needs human review before merge
whatever the pipeline says.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
