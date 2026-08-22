---
id: TICKET-035
stage: new
class: feature
branch: ticket/035
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a project cannot override a stage, so customising one stage changes every registered project

`STAGES_DIR = PKG / "stages"` (`pipeline/core/config.py:16`), so every project
the daemon sweeps reads the same stage files. Frontmatter is what selects a
stage's model, effort, tools, hooks and `skills:`, so today there is no way to
customise any of those for one project without changing them for all.

    ~/.config/pipeline/projects   -> one line today, so nothing is broken yet
    pipeline/stages/implementing.md   shared by every project on the machine

Concretely: a project CAN ship its own skill in `<project>/.claude/skills/`,
and those survive `--setting-sources project` -- verified 2026-08-22, a spawn
in this repo reports 17 skills with `file-ticket` among them. But the
`skills: [...]` line that grants the `Skill` tool lives in the shared stage
file. Declare it for one repo and every other repo's stage is told to invoke a
skill it does not have -- the "prompt lying to the agent" failure
`compose_prompt()`'s docstring exists to prevent.

Expected: a project may place `<project>/.project/stages/<name>.md` and have it
shadow the packaged stage of the same name, with the packaged one used when
there is no override. The falsifiable check is two projects on one machine
whose `implementing` stages resolve to different files.

Suggestion, not a decision: the resolution looks like one path lookup in
whatever `stage_config()` and `compose_prompt()` use to find a stage file. Note
`agent_stages()` enumerates `STAGES_DIR` and a test asserts nothing else
enumerates the stages, so overrides have to be visible to that too, or the
override is invisible to `pipeline ls` and to `test_every_stage...`.

Related: TICKET-036 wants per-project MCP config and is the same missing seam.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
