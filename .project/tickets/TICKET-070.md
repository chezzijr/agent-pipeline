---
id: TICKET-070
stage: new
class: feature
branch: ticket/070
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

plan-validation cannot measure, and an unmeasured finding is scored as one

`plan-validation` is `write: false`, so the guard gives it an allowlist and
`readonly_rules()` (`pipeline/hooks/dangerous-commands.py:262`) rejects every
command substitution outright:

    if "$(" in raw or "`" in raw:
        return "command substitution the guard cannot inspect"

That is correct and must stay -- it is CLAUDE.md invariant 4. The consequence
is that the stage judging a plan cannot run anything to test its own
reasoning, and its prompt gives it no way to say so. Everything it emits is a
finding, scored the same, whether measured or reasoned from documented
semantics. A validator reporting "every probe I have was blocked, so this rests
on documented semantics alone" is being penalised for honesty, and its
plausible-but-unmeasured recommendation is indistinguishable from a checked
one.

Expected: two prompt-level changes, no guard change.

First, the stage can mark an item as unverified -- a distinct channel that is
visible to the human at the approval gate but is not counted as a finding
against the plan. What "not counted" means in the pass/fail decision is
`pipeline/stages/plan-validation.md`'s to define; today an unexplained pass is
a fail, and an unverifiable item should not silently become one either.

Second, the stage prompt does not mention `[readonly] allow` in
`.project/pipeline.toml`, the per-project argv-prefix extension that is the
supported way to give a read-only stage a specific command. The validator
cannot ask for what it does not know exists.

Do not weaken `readonly_rules()`, add a general escape hatch, or give this
stage `write: true`. The gate exists because a stage that can run arbitrary
shell is not a read-only stage.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
