---
id: TICKET-072
stage: new
class: bugfix
branch: ticket/072
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

a stage can register its own worktree as a project

Observed live on 2026-08-27. `TICKET-068`'s `planning` stage ran
`pipeline register .` inside its own checkout while exploring the command the
ticket is about, and it took:

    $ pipeline projects
    /home/chezzijr/proj/agent-pipeline
    /home/chezzijr/proj/chezzilang
    /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-068

The first visible symptom was `pipeline ls` printing every ticket twice --
once from the real project and once from the worktree's branch-time copy of
`.project/tickets/`, all at stage `new`. 154 rows for 82 tickets.

`register()` (`pipeline/daemon/registry.py:60`) validates three things: a
`.project/` exists, the path carries no newline or `#`, and it is not already
listed. A worktree of a registered project satisfies all three, because
`git worktree add` copies `.project/` along with everything else.

Why it escaped every containment the design has: the registry file lives at
`$XDG_CONFIG_HOME/pipeline/projects` (else `~/.config`), so the write is
outside the worktree, outside the ticket's diff, outside `tree_snapshot()`,
outside `machine.FENCED`, and outside review. Nothing recorded it. It was
found because `ls` looked wrong.

Nothing executed from the entry here: `pipeline run` serves one project. Under
`pipeline start`, which drains every registered project, the daemon would tick
a directory a stage registered, whose `.project/tickets/` that same stage can
write -- `.project/` is excluded from the read-only snapshot on purpose, and
Bash reaches it. That is the case this ticket is about, not the duplicate rows.

The guard is not at fault and must not be changed for this. `planning` is
`write: true`, so `pipeline/hooks/dangerous-commands.py` applies its blocklist,
and `pipeline register` is not a dangerous command by any pattern. A read-only
stage would have been stopped by the allowlist already.

Expected: a stage cannot add an entry to the operator's registry that the
daemon will then serve. A worktree of an already-registered project is the
concrete case to refuse, and `pipeline projects` should not list one.

Two suggestions, neither a decision -- the shape of the fix is planning's to
choose:

- Refuse at `register()`: a path under a registered project's `.worktrees/`,
  or any path whose `git rev-parse --git-common-dir` differs from its
  `--git-dir`, is a worktree and not a project.
- Refuse at the source: the registry is operator state, and no stage has a
  reason to write it. A spawned stage could be denied the verb outright.

The first is narrow and testable today. The second is the invariant, and needs
a mechanism that does not become pattern matching in the guard.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
