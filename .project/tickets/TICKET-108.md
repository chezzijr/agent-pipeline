---
id: TICKET-108
stage: new
class: bugfix
branch: ticket/108
test_file: null
files_declared: []
depends_on: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

`gate()` reports a `DEC-` id as an unresolvable citation even when the plan says it has no record

`## Decisions checked` is matched with a bare token regex, so the gate cannot
tell a mention from a use -- `pipeline/core/gate.py:685`, on main at 10b44e3:

    cited = sorted(set(DEC_ID_RE.findall(dec)))   # DEC_ID_RE = r"\bDEC-\d{1,6}\b"
    ...
    if cid not in on_disk:
        findings.append(
            f"`## Decisions checked` cites {cid}, which is not a record in "
            f"{ddir} -- a citation nobody can resolve is not a check")

A plan that documents a gap in the decision sequence has to name the id it
could not find, and that sentence is read as a citation:

    >>> from pipeline.core.gate import DEC_ID_RE
    >>> DEC_ID_RE.findall('DEC-031 has no record -- the sequence skips it')
    ['DEC-031']

The finding is in `STRUCTURAL_MARKS` (`pipeline/core/gate.py:133`), so it
charges `structural_gate_failures` and sends the ticket back to `planning`,
which writes the same true sentence again. The `"none relevant"` escape at
`gate.py:686` does not reach it -- that arm only runs when NO id matched --
and unlike the count check there is no per-id waiver (`COUNT_PINNED_RE`,
`gate.py:75`).

Observed on two tickets in the `chezzilang` project, both plans defect-free:
`/home/chezzijr/proj/chezzilang/.project/tickets/TICKET-043.md:786` and
`.../TICKET-045.md:392`, each firing twice. The plan text that triggered it
documented the gap the records themselves have -- that project's
`.project/decisions/` holds DEC-001..DEC-030 and DEC-032..DEC-042, so
DEC-031 has no record, and saying so is what the gate read as a citation.
The workaround the human had to hand back (TICKET-043.md:804) was "do not
write a bare `DEC-NNN` token for the missing record" -- a phrasing rule the
gate should not need.

Expected: a `## Decisions checked` section whose only `DEC-031` is in a
clause saying it does not exist produces no finding. The failing test belongs
in `tests/test_gate.py`, beside
`test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`; it
fails today because the gate's findings contain the string
"`## Decisions checked` cites DEC-031".

Suggestions only, for `planning` to choose between: skip an id inside a
negating clause, scan only lines that read as assertions, or give this check
a waiver line the way `count-pinned:` waives the count check.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
