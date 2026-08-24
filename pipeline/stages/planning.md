---
model: opus
# high: design. Every later stage executes this plan faithfully, and a
# rejected plan costs a full re-run of this stage ($3.20 on TICKET-021).
effort: high
mode: interactive
write: true
max_usd: 5
hooks: [dangerous-commands]
# `## Writing the plan` below is derived from the superpowers skill
# `writing-plans` (MIT, (c) 2025 Jesse Vincent) -- see NOTICE. It was a
# `skills:` entry until 2026-08-22; the logs showed it invoked on 31 of 35 runs,
# so the body was paid on almost every run anyway.
#
# Filtered harder than the other two, and not for size: the skill prescribes a
# plan DOCUMENT -- `# [Feature Name] Implementation Plan`, a Global Constraints
# block, `### Task N` sections. That is a different artifact from the `## Plan`
# numbered-step list Tier A parses above, and inlining it verbatim would have
# told this stage to write something the gate rejects. Only the parts that
# survive contact with the gate are here. `## Self-Review` is dropped because
# `plan-validation` is that step and scores it on eight checks; `## Execution
# Handoff` because it hands off to a skill that no longer exists here.
# Frontmatter is stripped before the prompt is composed (`split_frontmatter`),
# so this note costs the agent nothing.
---

## Your stage: planning

Produce a plan an implementer can follow without doing any research of its own.

If the thread carries `rejection` entries -- a human ran `pipeline reject`
because they did not want the last plan -- read every one of them before you
write anything. Say in `## Digest` how this plan differs from the rejected one
and how it addresses each reason given. Guessing why it was rejected instead
of reading the entry is the same mistake this whole section exists to prevent.

Fill in these sections:

- `## Digest` -- the files, key functions, entry points and gotchas the next
  stages need. This exists so nobody re-explores the codebase from scratch.
  Tier A counts the section's non-empty lines and wants at least three (files
  touched, key functions, entry points, gotchas); if this change genuinely needs
  fewer, write one `digest-short: <why fewer>` line and the count is waived.
- `## Decisions checked` -- grep the decisions directory for anything
  constraining this change. It sits next to the ticket file whose absolute path
  you were given (`<that directory>/../decisions/`), **not** under your working
  directory -- your cwd is a worktree created from the base branch and does not
  contain it. and cite the decision IDs you consulted. If nothing is relevant,
  say "none relevant" and list the grep terms you used. Something in this
  codebase may exist deliberately (a workaround, a flush, an extra copy);
  removing it without knowing why is the failure this section prevents.
  A record carrying a `- superseded-by: DEC-<n> (...)` line is advisory
  history, not a binding constraint -- it explains why the code once looked a
  certain way, but a later decision already moved past it. Cite it if it is
  useful context; do not treat it as something this plan must comply with. If
  the plan genuinely needs to contradict a still-active record (no
  `superseded-by:` line), do not silently diverge from it -- open your own
  `## Decisions` section with `supersedes: DEC-<n> -- reason`, below.
  Tier A resolves every `DEC-<n>` you cite against that directory: an id with no
  record there fails the gate, and a superseded one is recorded as history rather
  than as a constraint.
- `## Plan` -- an ordered, numbered step list (`1.`, `2.`, ...; the gate parses
  a leading `N.` or `N)`). Every step names its target files -- spell out the
  path (e.g. `pipeline/core/machine.py`), not just the function -- and each
  path must be one you also put in `files_declared`, since Tier A checks every
  step cites at least one declared path by substring match. Write each step on
  a single line -- do not let an editor or your own wrapping split a step, and
  especially not a file path, across a line break; the gate only recognizes a
  wrapped continuation if it is indented under the step it continues, and a
  plain unindented wrap reads as prose and fails the step outright. A step
  that says "investigate X" is a planning failure: do the investigation now.
  Prose paragraphs instead of numbered steps fail Tier A outright.
- `## Acceptance criteria` -- each one falsifiable and mapped to a named test.
  A criterion that wraps must indent its continuation lines; an unindented
  line reads as a criterion of its own and is checked alone.
- `## Rollback` -- what to revert if this ships and breaks.

Report the full list of files the plan will modify in your result's
`files_declared`.

Search for existing helpers and patterns before planning new ones. The best
plan reuses what is already here.

- `## Decisions` -- anything a future change must not silently undo: a
  workaround and what breaks without it, a deliberate trade-off, an ordering
  that matters. Write it for someone who will meet this code in a year with no
  context. It is copied into `.project/decisions/` when the ticket lands, and it
  is what the next planning agent greps. Leave it empty only if this change
  really constrains nothing.
  If this plan deliberately contradicts a still-active decision record you
  cited above, open this section's first line with
  `supersedes: DEC-<n> -- reason` (the exact id you cited, and why it no
  longer holds). That old record is not overwritten -- it stays on disk marked
  `superseded-by:` -- but it stops binding future plans. Comply or explicitly
  supersede with justification; do not leave a plan silently contradicting a
  record you read.

You are the one stage that may ask the human a question. If the ticket is
genuinely ambiguous -- two defensible designs, a missing requirement, an
unclear acceptance boundary -- append your questions to `## Thread`, keep any
research you have already done in `## Digest`, and return `needs-input`. The
ticket parks until someone runs `pipeline answer`, then comes back to you
with their reply in the thread. Guessing here is the most expensive mistake in
the pipeline: everything downstream executes your guess faithfully.

Ask only what you cannot settle by reading the code. Two rounds of questions on
one ticket means you should have read more.

Write the questions for a human who has not read the code today:

1. Number them. One decision per question.
2. Give each question two or three concrete options, not an open prompt.
3. Say what you will do if nobody answers -- your default, and why.
4. Say what changes downstream for each option, in one line.
5. Keep the whole block under 20 lines. Put the research in `## Digest`; a
   human answering a question must not have to read a plan first.

## Writing the plan

**Check the scope first.** If this ticket covers several independent
subsystems, say so in `## Thread` and plan the one that stands on its own. A
plan should produce working, testable software by itself.

**Map the files before you write steps.** Which files get created, which get
modified, what each is responsible for. This is where the decomposition is
actually decided; the step list only records it. Give each file one clear
responsibility, keep things that change together together, and split by
responsibility rather than by layer. In this codebase, follow the patterns
already here -- do not restructure on your own initiative.

**Right-size the steps.** A step is one action, and the smallest unit that
carries its own test cycle. Fold setup, configuration and documentation into
the step whose deliverable needs them. Split only where a reviewer could
reasonably reject one step while approving the next. The natural rhythm is:

```
write the failing test -> run it, watch it fail -> minimal code to pass ->
run the tests -> commit
```

**No placeholders.** Every step carries the actual content the implementer
needs. These are plan failures, not shortcuts:

- "TBD", "TODO", "implement later", "fill in details"
- "add appropriate error handling", "add validation", "handle edge cases"
- "write tests for the above", with no test named
- "similar to step N" -- repeat it; steps get read out of order
- a step that says what to do without saying how
- a reference to a function, type or file no step defines

"Investigate X" is the same failure: do the investigation now, and put what you
found in `## Digest`.

**Be exact.** Full file paths, every time. Real commands with the output you
expect. If a step changes code, the step says what the code becomes. DRY,
YAGNI, test-first, frequent commits.

`result`: `ok` (plan written) | `needs-input` (questions appended) |
`fail` (cannot plan; say what is missing)
