Three rules this project's plan-validation gate has actually failed plans on.
They add to the rules above; none of them relaxes one.

**No prose in `## Plan`.** Every line of that section is either a step
starting `N.` / `N)` or a continuation line indented under one. Conventions,
notation and framing that apply to several steps go in `## Digest`, never
above step 1 -- an unindented line there is scored as a step, and then fails
for naming no declared file. Two findings, one habit.

**Cite only decisions that exist.** `## Decisions checked` may name a
`DEC-<n>` only if `.project/decisions/DEC-<n>.md` is a real file -- check
with `ls .project/decisions/` before you write the id. If nothing applies,
write `none relevant` together with the grep terms you searched. An id you
inferred from a ticket number or a thread mention is the single most common
way a plan here bounces.

**No absolute totals in `## Acceptance criteria`.** A criterion that pins a
number copied out of `## Digest` -- "87 passed", "122 cases", "3 call sites"
-- fails, because any other ticket can move that total. State it as a
relation to a measured baseline ("no failures other than this ticket's repro
test"), or re-measure at check time. If a total genuinely cannot move, one
`count-pinned: <why it cannot move>` line in that section waives the check.
