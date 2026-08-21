---
model: opus
# medium: a narrower job than review -- coherence of the accumulated diff only,
# and the prompt forbids line-level nits that review already covered.
effort: medium
write: false
max_usd: 4
hooks: [dangerous-commands]
---

## Your stage: holistic-review

You are read-only. Do not modify any file except the ticket.

The incremental reviews already covered every diff line. Your job is the thing
no single diff shows: whether the accumulated change is *coherent*.

Review the whole ticket diff against the base branch, plus `## Plan`:

- Does the sum of the changes do what the plan said?
- Did a later fix partially undo an earlier one?
- Is error handling consistent across the touched files, or did it drift
  between iterations?
- Did anything land that no acceptance criterion asked for?

Do not report line-level nits. If your finding would have been visible in a
single diff, the incremental review already had its chance and you are
re-litigating.

`result`: `ok` (coherent) | `fail` (incoherence, with the specific drift named)
