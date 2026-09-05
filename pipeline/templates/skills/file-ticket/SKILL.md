---
name: file-ticket
description: File a ticket into this repo's pipeline (.project/tickets/). Use when the user reports a bug, asks for a feature or refactor, or says "file a ticket", "add a ticket", "queue this up", "make a ticket for X". Interviews for the few things only a human knows, then hands the ticket to the dispatcher.
---

# Filing a ticket

This skill is installed for both supported clients. Invoke `/file-ticket` in
Claude Code or `$file-ticket` in Codex; the workflow below is identical.

A ticket is a work order for an agent pipeline, not a bug report for a person. The
dispatcher picks it up, a triage agent reproduces it, a planning agent plans it, and a
gate refuses to let any of that proceed on a vague ticket.

**You fill in only what a human knows and an agent cannot guess.** Everything else is
deliberately left empty — filling it in yourself is not helpfulness, it is guessing
inside a system built to stop agents guessing.

| Section | Who fills it |
|---|---|
| frontmatter `class` | you |
| frontmatter `depends_on` | you |
| `## Summary` | you |
| `## Reproduction` | **triage agent** — it writes a real failing test and records the exact error |
| `## Digest`, `## Decisions checked`, `## Plan`, `## Acceptance criteria`, `## Rollback` | **planning agent** |
| `## Decisions` | planning agent; copied to `.project/decisions/` when the ticket lands |
| `## Thread` | every stage, plus you via `pipeline answer` / `reject` |

## Before you start

The `pipeline` CLI must be on PATH (`~/.local/bin`). If it is not:

```sh
uv tool install --editable . --force     # from the agent-pipeline checkout
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
  | `bugfix` | something is wrong and you can point at it | 2 review loops, never a holistic review |
  | `feature` | something absent that should exist | 2 review loops, holistic review **if review bounced** |
  | `refactor` | shape is wrong, behaviour stays | **3** review loops + 3 plan-validation attempts, same holistic rule |

  Class is not cosmetic — it sets the loop budgets in `machine.py:BOUNDS`. Getting it
  wrong makes a ticket escalate early or churn late.

  Class sets the base budget; a large plan buys plan-validation attempts on
  top of it — one per 8 steps or 4 declared files, capped at 5 — so a class
  no longer has to be inflated to buy attempts.

  The holistic pass is not bought by class alone (DEC-034): it reviews an
  *accumulated* diff, so it runs only once `review_loops` has been charged at least
  once — by a failed review, a failed holistic pass, or a red regression suite. A
  `feature` whose review passed first time goes straight to `verifying`, exactly as a
  `bugfix` does.

If the user already gave you a traceback or an exact error string, keep it verbatim for
step 3 — triage has to reproduce that exact failure, and the gate greps the test output
for it.

### 2. Push back before you file

Three things make a ticket that the pipeline will reject on its own, and it is cheaper
to say so now:

- **No observable symptom.** A triage agent's whole job is to write a *failing test*. If
  nothing fails, it will return `result: rejected` and the ticket dies at triage. Say so
  and ask for the symptom. A symptom that lives in a document is still filable -- see
  *A docs-only ticket* below for the shape it needs.
- **Two unrelated changes.** `files_conflict` orders tickets by the files they touch, so
  one ticket spanning two areas blocks both. File two.
- **A solution instead of a problem.** "Switch to a ring buffer" pre-empts the planning
  stage, whose job is to choose. Record the idea in `## Summary` as a suggestion, but
  lead with the symptom.

### 3. File it

```sh
cd <the repo root>
pipeline new "cache leaks on evict" --class bugfix
```

That prints the path. Then rewrite `## Summary` — the template puts the bare title
there, which is not enough for an agent starting cold with no other context.

A good summary is three short paragraphs:

```markdown
## Summary

evict() never drops the key when the cache is at capacity

`Cache.evict()` is supposed to make room by removing the LRU entry. It picks
the victim and never removes it -- `cache/lru.py:64`, on main at a1b2c3d:

    def evict(self):
        if len(self._d) > self.maxsize:
            self._lru()        # picks the victim, never deletes it

With `maxsize=2`, adding a third key leaves all three present, so the cache
grows without bound.

    >>> c = Cache(maxsize=2); c.put("a",1); c.put("b",2); c.put("c",3)
    >>> len(c)
    3          # expected 2

Expected: `len(c) == 2` after the third put, with "a" gone. The exact
failure a test should show is `AssertionError: 3 != 2`.
```

What makes that work: a one-line title, the mechanism, a runnable reproduction, and the
expected behaviour stated as something a test can check. If the user gave an exact error
string, include it — triage records it as `expect: <text>` and the gate greps the real
test output for it, which is what stops a test that fails for an unrelated reason from
passing as a reproduction. Give the invariant part of that string -- not a `/tmp` path, a
pid, or a truncated tail, which the gate refuses because they cannot recur.

**Anchor the mechanism in code.** Name the location as `path:line` --
`pipeline/core/gate.py:383` -- and quote the two or three lines it points at.
Triage is charged per run, and a prose-only summary makes it re-find the
location you already had open. Give the line number you saw and the commit
you saw it on; a line that has since moved still lands triage within a few
lines of the code.

**Do not touch the frontmatter beyond `class` and `depends_on`.** `stage`, `branch`,
`counters` and `lease` belong to the dispatcher, and a ticket whose control fields look
edited is escalated rather than trusted.

**Ordering: `depends_on` names the tickets that must reach `done` first.** Write it as
`depends_on: [TICKET-023]` or pass `pipeline new --depends-on TICKET-023`, and only when
the later ticket's work genuinely cannot be planned until the earlier one lands — prose
in `## Summary` saying "land TICKET-023 first" enforces nothing. The dispatcher WAITS
rather than failing, `pipeline ls` names what a ticket waits on, and a dependency that
is missing, `escalated`, `rejected`, or part of a cycle escalates the dependent instead
of hanging. Two tickets that touch the same file are already ordered by
`files_declared`; do not restate that as a dependency.

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

- Not registered → `pipeline register .` from the repo root. It runs this
  project's `test_suite` once and probes `test_one` with a selector that
  matches nothing, then refuses when the suite cannot run at all or when
  `test_one` exits 0 on that probe; fix `.project/pipeline.toml` (the
  `pipeline-config` skill teaches how) or pass `--force` for a slow suite.
- Daemon down → `pipeline run` (this project, in your terminal; `--once` drains the
  queue and exits) or `pipeline start` (detached, every registered project).
  **They differ where it matters:** `planning` is `mode: interactive`, so under the
  daemon it runs on a PTY and waits for a human -- but only when a client is already
  subscribed as the stage spawns: leave `pipeline tui` open first, then `i` for raw
  mode. With no client attached, and under `pipeline run` where nothing can attach,
  it runs headless and finishes on its own. Unattended = `pipeline run`.
- Whichever you use, the main checkout has to be sitting on the base branch, or
  `merging` refuses to land the ticket and escalates it with the work already done.

Then tell the user what to expect and how to watch:

```sh
pipeline ls                      # stage of every ticket
pipeline decisions               # what earlier tickets already decided
pipeline tui                     # live view; a/r/A act on the human gates
pipeline logs TICKET-003 -f      # one stage's stream
```

The ticket stops at `awaiting-approval` for the human, unless `triage` judges the fix
small enough for the cheap route (`triage -> implementing -> quick-review -> verifying
-> merging`), which has no plan-approval gate; `quick-review` returns it to `planning`, and
so to the approval gate, if the diff or the test does not hold up; the dispatcher undoes
the cheap route's commit on the way, so the ticket re-plans against the failing test
`triage` committed. Either route stops
again at `awaiting-merge`, a second human gate, if its diff touches anything `CLAUDE.md`
fences off from unattended merge. The class table below does not change: there is no
`chore` class, and a human cannot request the cheap route. That gate is the point, so
do not describe filing as "it will be fixed automatically".

## A docs-only ticket

A ticket whose symptom is in a document -- a skill, a README, a stage prompt
-- is filable, but not in the shape above. Triage's job is a *failing test*,
and a wrong sentence has no runtime behaviour to fail on. The test asserts
the document's own text instead.

TICKET-084 is the worked precedent. The `pipeline-config` skill named none
of five config knobs the code reads, and
`tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads`
reads that file and asserts each name is in it -- red before the edit, green
after, exactly like a bug's test.

So a docs-only `## Summary` carries two things a code ticket does not:

- **The test file the assertion goes in**, by path. An existing file where
  this project already tests documents, not a new one.
- **The assertion itself**, close to literal. "the skill must name
  `path:line`" is enough for triage to write `assert "path:line" in text`.

Anchor the document the way you anchor code: `path:line` plus the lines that
are wrong, or the section that should exist and does not.

Without both, step 2's first push-back applies: there is no symptom a test
can fail on, so triage returns `result: rejected` and the ticket dies there.

## Do not

- **Do not run `pipeline approve`.** Approval is the human gate. A session that files a
  ticket and approves its own plan has removed the only checkpoint in the system.
- **Do not fill `## Plan`.** The gate requires numbered steps citing declared files, and
  plan-validation scores the plan against eight judgment checks. A plan written here
  skips both.
- **Do not resume or reject an escalated ticket on the user's behalf.** The bound it
  hit is the checkpoint, the same as approval is. Read it -- README's *When a ticket
  escalates* is the procedure -- and hand the user the command.
- **Do not edit a ticket that is not in `new`.** A stage may hold its lease; use
  `pipeline answer <id> "..."` or `pipeline reject <id> "why"`, which append to the
  thread properly. To edit a running ticket by hand, interrupt the stage first
  (`k` in the TUI).
