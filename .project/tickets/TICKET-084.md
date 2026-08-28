---
id: TICKET-084
stage: new
class: feature
branch: ticket/084
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

the pipeline-config skill omits half the knobs the config now has

`pipeline/templates/skills/pipeline-config/SKILL.md` is what a session reads
before writing a project's `.project/pipeline.toml`, and `pipeline init`
copies it into every project it scaffolds. Twenty tickets landed on
2026-08-27; seven of them updated this file as they went, and four knobs
still have no mention in it at all.

Measured on 2026-08-28 against the 122-line skill:

    max_usd          MISSING     the per-stage dollar cap
    scale_usd        MISSING     opt in to size-scaled caps (TICKET-078)
    worktree_setup   MISSING     per-worktree setup command
    <name>.extra.md  MISSING     .project/stages/ prose appended to a stage
    pinned           MISSING     why a --private project needs `config --sync`

Already covered, and to be left alone: `test_one`, `test_suite`,
`test_suite_without_new`, `base`, `{test}`/`{path}`/`{name}`, `max_parallel`,
`[readonly] allow`, `[mcp.<name>]`, `[stages.<name>]`, and `config --sync`
itself.

Two of the five are not merely undocumented, they are the ones an operator
reaches for under pressure:

- `max_usd` is what unblocked TICKET-066. Its `planning` stage was killed at
  the $5 default having spent $5.30 over 46 turns; the cap was raised to $10
  in `.project/pipeline.toml` and the next run finished at $6.09. Nothing in
  the skill says that lever exists.
- `worktree_setup` carries a hazard the README documents and the skill does
  not: a build cache shared across worktrees unkeyed serves one ticket's
  artifact into another's build, which reads as a red test in a diff that
  did not cause it.

Expected: a session that reads this skill can write every key the code
actually reads, and knows which of them is the answer to "the stage ran out
of budget" and "my builds interfere across tickets". The five above are named
with what they do and one example each.

A second question this raises, and planning should answer it in the plan
rather than in code: the skill now serves two jobs -- "set up test commands
for a project the pipeline has never seen", which is its trigger, and "here
is every knob the tool has", which is a reference. If those want separate
shapes, say so and propose the split; if one file still serves both, say why.

OUT of scope, and NOT to be fixed here: `pipeline init` COPIES this file
rather than linking it, so a project scaffolded before a skill change keeps
the old bytes forever, and a re-run of `init` prints "already at ... -- kept"
rather than updating. Measured: `/home/chezzijr/proj/chezzilang` holds an
8484-byte `file-ticket/SKILL.md` from 2026-08-26 against the packaged
8566-byte copy, and has no `pipeline-config` skill at all because that skill
did not exist when it was scaffolded. That is a distribution problem needing
its own ticket -- a version marker, an `init --update-skills`, or a way to
tell a stale copy from a customised one. Do not widen into it.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
