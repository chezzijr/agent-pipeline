---
id: TICKET-111
stage: new
class: bugfix
branch: ticket/111
test_file: null
files_declared: []
depends_on: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

the count check fires on the measured baseline `CRIT_COUNT_RULE` itself asks for

`CRIT_COUNT_RULE` (`pipeline/core/gate.py:79`, on main at 10b44e3) tells a
criterion to "state it as a relation to a measured baseline, or re-measure at
check time". A criterion that does BOTH is still rejected, because the scan
at `pipeline/core/gate.py:819` reads the whole criterion -- the baseline
clause included -- and cannot tell the pinned total it is hunting from the
evidence quoted beside it:

    dig_counts = set(COUNT_RE.findall(dig))
    if dig_counts and not COUNT_PINNED_RE.search(crit):
        for c in crits:
            shared = sorted(set(CRIT_COUNT_RE.findall(c)) & dig_counts, key=int)

Reproduced against the real functions:

    >>> from pipeline.core.gate import CRIT_COUNT_RE, COUNT_RE
    >>> c = ("- ... with a case count equal to `ls judge/problems/*/samples/*.in | wc -l` "
    ...      "re-measured at that moment. Measured on the prototype: "
    ...      "`done: 318 case(s), 0 failure(s)` in 40.9 s.")
    >>> dig = "the sweep takes 40.9 s on release for 318 cases"
    >>> sorted(set(CRIT_COUNT_RE.findall(c)) & set(COUNT_RE.findall(dig)))
    ['318']

That is TICKET-047 in the `chezzilang` project, verbatim:
`/home/chezzijr/proj/chezzilang/.project/tickets/TICKET-047.md:624`, repeated
at `:632`, which cost two `structural_gate_failures` on a criterion that
never pinned the count at all -- it says `wc -l` "re-measured at that
moment", and 318 appears only in the "Measured on the prototype:" clause.
The form is not unusual: every criterion in that ticket's final
`## Acceptance criteria` carries one ("Measured before the fix: ...",
"Measured on `9712c59a`: `0 passed; 1 failed`"), which is what the rule asks
for, so any such baseline quoting a two-digit number the digest also mentions
trips the check.

Expected: a criterion whose only shared number sits in its measured-baseline
clause, and which states a re-measure for the value under test, produces no
finding -- while a criterion that pins the total as the thing to check still
fails. The failing test belongs in `tests/test_gate.py` beside
`test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest`,
whose blocking case must keep passing; today the new case reports
"acceptance criterion pins an absolute count copied from `## Digest` (318)".

Suggestion only, for `planning` to choose: the count that matters is the one
being ASSERTED, so scanning only the assertion clause -- not a `Measured
on...`/`Measured before...` baseline, and not a backticked span quoting
captured output -- is one way; `COUNT_PINNED_RE`'s waiver is not, since it
waives the whole section for every criterion in it.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
