---
name: file-ticket
description: File a ticket into this repo's pipeline (.project/tickets/). Use when the user reports a bug, asks for a feature or refactor, or says "file a ticket", "add a ticket", "queue this up", "make a ticket for X". Interviews for the few things only a human knows, then hands the ticket to the dispatcher.
---

# Filing a ticket

A ticket is a work order for an agent pipeline, not a bug report for a person. The
dispatcher picks it up, a triage agent reproduces it, a planning agent plans it, and a
gate refuses to let any of that proceed on a vague ticket.

**You fill in only what a human knows and an agent cannot guess.** Everything else is
deliberately left empty — filling it in yourself is not helpfulness, it is guessing
inside a system built to stop agents guessing.

| Section | Who fills it |
|---|---|
| frontmatter `class` | you |
| `## Summary` | you |
| `## Reproduction` | **triage agent** — it writes a real failing test and records the exact error |
| `## Digest`, `## Decisions checked`, `## Plan`, `## Acceptance criteria`, `## Rollback` | **planning agent** |
| `## Decisions` | planning agent; copied to `.project/decisions/` when the ticket lands |
| `## Thread` | every stage, plus you via `pipeline answer` / `reject` |

## Before you start

The `pipeline` CLI must be on PATH (`~/.local/bin`). If it is not:

```sh
uv tool install --editable /home/chezzijr/proj/claude-setup --force
```

## Steps

### 1. Interview

Ask only what you cannot read out of the repo. Usually two or three questions, at most
one round — use `AskUserQuestion` when the answer is a choice.

- **What is the observable symptom?** A command and its wrong output, or the behaviour
  that is missing. "Cache grows forever" is a symptom; "refactor the cache" is not.
- **What should happen instead?** The gate later demands falsifiable acceptance
  criteria, and this is where they come from.
- **The class**, if it is not obvious from the answer:

  | class | means | bounds it buys |
  |---|---|---|
  | `bugfix` | something is wrong and you can point at it | 2 review loops, skips holistic review |
  | `feature` | something absent that should exist | 2 review loops, holistic review |
  | `refactor` | shape is wrong, behaviour stays | **3** review loops + 3 plan-validation attempts |

  Class is not cosmetic — it sets the loop budgets in `machine.py:BOUNDS` and decides
  whether a holistic review runs. Getting it wrong makes a ticket escalate early or
  churn late.

If the user already gave you a traceback or an exact error string, keep it verbatim for
step 3 — triage has to reproduce that exact failure, and the gate greps the test output
for it.

### 2. Push back before you file

Three things make a ticket that the pipeline will reject on its own, and it is cheaper
to say so now:

- **No observable symptom.** A triage agent's whole job is to write a *failing test*. If
  nothing fails, it will return `result: rejected` and the ticket dies at triage. Say so
  and ask for the symptom.
- **Two unrelated changes.** `files_conflict` orders tickets by the files they touch, so
  one ticket spanning two areas blocks both. File two.
- **A solution instead of a problem.** "Switch to a ring buffer" pre-empts the planning
  stage, whose job is to choose. Record the idea in `## Summary` as a suggestion, but
  lead with the symptom.

### 3. File it

```sh
cd /home/chezzijr/proj/claude-setup
pipeline new "cache leaks on evict" --class bugfix
```

That prints the path. Then rewrite `## Summary` — the template puts the bare title
there, which is not enough for an agent starting cold with no other context.

A good summary is three short paragraphs:

```markdown
## Summary

evict() never drops the key when the cache is at capacity

`Cache.evict()` is supposed to make room by removing the LRU entry. With
`maxsize=2`, adding a third key leaves all three present, so the cache grows
without bound.

    >>> c = Cache(maxsize=2); c.put("a",1); c.put("b",2); c.put("c",3)
    >>> len(c)
    3          # expected 2

Expected: `len(c) == 2` after the third put, with "a" gone. Seen on main at
a1b2c3d. The exact failure a test should show is `AssertionError: 3 != 2`.
```

What makes that work: a one-line title, the mechanism, a runnable reproduction, and the
expected behaviour stated as something a test can check. If the user gave an exact error
string, include it — triage records it as `expect: <text>` and the gate greps the real
test output for it, which is what stops a test that fails for an unrelated reason from
passing as a reproduction.

**Do not touch the frontmatter beyond `class`.** `stage`, `branch`, `counters` and
`lease` belong to the dispatcher, and a ticket whose control fields look edited is
escalated rather than trusted.

### 4. Hand it over

Nothing needs to be notified. The dispatcher globs `.project/tickets/*.md` every tick,
so a ticket in `stage: new` is picked up on the next pass — that is why the file *is*
the queue.

Check something is actually running:

```sh
pipeline status                  # is the daemon up
pipeline projects                # is this repo registered
```

`pipeline status` **exits 1 when no daemon is running** — that is its answer, not a
failure. Read the line it prints, not the exit code.

- Not registered → `pipeline register /home/chezzijr/proj/claude-setup`
- Daemon down → `pipeline start` (polls every 10s), or `pipeline run --once` to drain
  the queue in the foreground and watch it

Then tell the user what to expect and how to watch:

```sh
pipeline ls                      # stage of every ticket
pipeline tui                     # live view; a/r/A act on the human gates
pipeline logs TICKET-003 -f      # one stage's stream
```

The ticket will stop at `awaiting-approval` for the human — that gate is the point, so
do not describe filing as "it will be fixed automatically".

## Do not

- **Do not run `pipeline approve`.** Approval is the human gate. A session that files a
  ticket and approves its own plan has removed the only checkpoint in the system.
- **Do not fill `## Plan`.** The gate requires numbered steps citing declared files, and
  plan-validation scores the plan against eight judgment checks. A plan written here
  skips both.
- **Do not edit a ticket that is not in `new`.** A stage may hold its lease; use
  `pipeline answer <id> "..."` or `pipeline reject <id> "why"`, which append to the
  thread properly. To edit a running ticket by hand, interrupt the stage first
  (`k` in the TUI).
