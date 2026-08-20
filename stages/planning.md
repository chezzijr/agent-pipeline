## Your stage: planning

Produce a plan an implementer can follow without doing any research of its own.

Fill in these sections:

- `## Digest` -- the files, key functions, entry points and gotchas the next
  stages need. This exists so nobody re-explores the codebase from scratch.
- `## Decisions checked` -- grep `.project/decisions/` for anything constraining
  this change and cite the decision IDs you consulted. If nothing is relevant,
  say "none relevant" and list the grep terms you used. Something in this
  codebase may exist deliberately (a workaround, a flush, an extra copy);
  removing it without knowing why is the failure this section prevents.
- `## Plan` -- ordered steps. Every step names its target files and concrete
  functions. A step that says "investigate X" is a planning failure: do the
  investigation now.
- `## Acceptance criteria` -- each one falsifiable and mapped to a named test.
- `## Rollback` -- what to revert if this ships and breaks.

Report the full list of files the plan will modify in your result's
`files_declared`.

Search for existing helpers and patterns before planning new ones. The best
plan reuses what is already here.

`result`: `ok` (plan written) | `fail` (cannot plan; say what is missing)
