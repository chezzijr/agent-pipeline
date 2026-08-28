---
id: TICKET-082
stage: done
class: bugfix
branch: ticket/082
test_file: tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget
files_declared:
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/core/machine.py
- tests/test_cli.py
- tests/test_machine.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 16
  plan_files: 6
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 5abe2640-452e-42a6-8c5f-9990a4e82578
  log: .project/logs/TICKET-082-review-5abe2640.log
approved_by: 'chezzijr (via Claude Code, on explicit instruction to approve this merge).
  FENCED review: transition() stays pure -- forgive() mutates the same local copy
  charge() already does; only the (''revalidating'',''ok'') row changes; the credit
  never exceeds the failures it forgives; charge()''s subtraction is a no-op for every
  counter that has no credit, so all other bounds are unchanged.'
approved_at: '2026-08-28T02:15:00.335080+00:00'
---

## Summary

`stale_regate` charged on lifetime fail count, so a regate failure that a
later regate did not reproduce still escalated a good ticket. Fixed: a pass
at `revalidating` now credits the failures before it into
`stale_regate_cleared`, and `charge()` subtracts that credit before
comparing against the bound, so the bound counts consecutive failures. The
raw count is unchanged for the thread and for metrics. `pipeline resume
--reset` and `--grant` clamp the credit with its counter.

Implemented in 3 commits on `ticket/082`: `529868e` (`pipeline/core/machine.py`
+ `tests/test_machine.py`), `f786b8c` (`pipeline/cli/main.py` +
`tests/test_cli.py`), `dc625b0` (`README.md` + `CLAUDE.md`).

Review passed on the first pass, no blocking findings. All 7 acceptance
criteria met. `uv run --group dev pytest -q`: `406 passed in 19.45s`.
`./pipeline/hooks/test_dangerous_commands.py`: `guard: all passed`. Two
minor findings stand unfixed, both in the thread: a `TypeError` on a non-int
credit in `cmd_resume()`, and an escalation reason that quotes the raw count
against the bound.

`transition()` is in `machine.FENCED`, so this diff parks at
`awaiting-merge` for a human, as expected -- not a failure.

## Reproduction

`tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget`

Command: `uv run --group dev pytest -q tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget`

`stale_regate` never resets on an intervening `ok`. Two `("revalidating",
"fail")` calls separated by a `("revalidating", "ok")` -- i.e. a failure
confirmed non-reproducing by the pass that followed it -- still escalate,
identically to two genuinely stale plans, because `MAX_ATTEMPTS` (2) is
charged on raw fail count with no re-run-before-charge step anywhere in
`transition()`, `finish_gate()`, or `finish_regate()` (`pipeline/core/machine.py`,
`pipeline/daemon/supervisor.py`).

expect: AssertionError: two non-reproducing regate failures, separated by a passing regate, exhausted the budget: got 'escalated'
assert 'escalated' != 'escalated'

## Digest

Files touched: `pipeline/core/machine.py` (the fix), `pipeline/cli/main.py`
(the counter edits a human makes), `tests/test_machine.py`,
`tests/test_cli.py`, `README.md`, `CLAUDE.md`.

Key functions:
- `transition()` (`pipeline/core/machine.py:81`) and its local `charge()`
  (`pipeline/core/machine.py:89`). `charge()` increments `c[key]`, then
  escalates when the raw count reaches `bound_for(klass, key, c)`. Nothing
  subtracts anything today.
- `("revalidating", "ok")` (`pipeline/core/machine.py:134`) returns
  `implementing` and touches no counter. `("revalidating", "fail")`
  (`pipeline/core/machine.py:136`) calls `charge("stale_regate", "planning")`.
- `_size()` (`pipeline/core/machine.py:62`) reads a counter as a non-negative
  int, or 0. It is the hostile-input clamp `transition()` already uses. Reuse
  it; do not write a second one.
- `cmd_resume()` (`pipeline/cli/main.py:225`) applies `--reset`
  (`pipeline/cli/main.py:246`) and `--grant` (`pipeline/cli/main.py:252`).

Entry points: `advance()` (`pipeline/daemon/supervisor.py:103`) is the only
caller of `transition()`. It seeds `plan_steps` and `plan_files` first, so its
escalation-reason scan sees exactly one changed key (DEC-047), then writes the
returned counters onto the ticket. `finish_regate()`
(`pipeline/daemon/supervisor.py:927`) produces the `revalidating` results
`ok`, `fail` and `conflict`.

Gotchas:
- The reproduction asserts `c["stale_regate"] == 1` after the intervening
  `ok`. Do not zero the raw counter. The credit is a second key.
- The frontmatter names the reproduction in `test_file`, and the Tier A gate
  re-runs it by that name. Do not rename it, even though after the fix the
  name reads inverted.
- `transition` is in `machine.FENCED`, so this diff parks at `awaiting-merge`
  for a human. Expected, not a failure.
- `tests/test_machine.py:186` already asserts two consecutive fails escalate,
  and `test_bounds_escalate_on_the_second_failure`
  (`tests/test_machine.py:38`) does not list `stale_regate`. Both stay green.
- `tests/test_stages.py:300` reads the FIRST `stale_regate` in `README.md` and
  requires a `planning` mention within the 300 characters before it. Add new
  prose after that occurrence, never before it.
- `validate_meta()` (`pipeline/core/ticket.py:54`) does not validate counter
  keys, so a new key needs no schema change.
- `pipeline/cli/metrics.py:117` already says `stale_regate` reaches
  `escalated` only when it exhausts its own bound. Still true. Leave it.

## Decisions checked

Grep terms in `.project/decisions/`: `stale_regate`, `revalidat`, `flak`,
`counter`, `max_parallel`, `review_loops`, `re-run`, `rerun`.

- DEC-029 -- the `("revalidating", "fail")` row: its own counter, target
  `planning`, dispatcher default bound. This plan keeps all three. It changes
  only what the bound is compared against.
- DEC-065 -- one Tier A failure split into two counters. The precedent for
  charging a second key rather than reusing an existing budget.
- DEC-047 -- `advance()` seeds the size keys before `transition()`, so the
  escalation-reason scan sees one changed key. The credit is written on an
  `ok` row, which never escalates, so that scan is unaffected.
- DEC-051 -- `--grant` subtracts, `--reset` zeroes, and no `BOUNDS` lookup
  lives in `pipeline/cli/main.py`. The clamp in step 10 adds none. DEC-051
  says a change that lets a human raise a budget makes a clamp mandatory; this
  change removes an unintended grant instead.
- DEC-061 -- `revalidating` rebases and gates in one child; exit 3 is the
  rebase conflict. Untouched: the fix is in `transition()`, not in the child.

None of these is superseded and none is contradicted, so no `supersedes:`
line is needed below.

## Plan

1. Run `uv run --group dev pytest -q tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget` and confirm `tests/test_machine.py` reports `AssertionError: two non-reproducing regate failures, separated by a passing regate, exhausted the budget`.
2. Add `test_a_forgiveness_credit_is_bounded_and_never_invented` to `tests/test_machine.py`, after the reproduction, with this body: `assert "stale_regate_cleared" not in t("revalidating", "ok")[1]`; then `_, c = t("revalidating", "fail")`, `_, c = t("revalidating", "ok", c)`, `assert c["stale_regate_cleared"] == 1`, `_, c = t("revalidating", "ok", c)`, `assert c["stale_regate_cleared"] == 1`; then `_, c2 = t("revalidating", "fail", c)` and `assert t("revalidating", "fail", c2)[0] == "escalated"`; then `c3 = {"stale_regate": 1, "stale_regate_cleared": 5}`, `nxt, c3 = t("revalidating", "fail", c3)`, `assert nxt == "planning"`, the loop `while nxt != "escalated" and c3["stale_regate"] < 20: nxt, c3 = t("revalidating", "fail", c3)`, and `assert nxt == "escalated" and c3["stale_regate"] == 7, c3`.
3. Run `uv run --group dev pytest -q tests/test_machine.py -k forgiveness` and confirm `tests/test_machine.py` fails with `KeyError: stale_regate_cleared`.
4. Edit `pipeline/core/machine.py`: add `def cleared_key(key: str) -> str: return f"{key}_cleared"` above `transition()`, with a docstring saying `charge()` subtracts it so a bound counts consecutive failures.
5. Edit `charge()` in `pipeline/core/machine.py`: after `bound = bound_for(klass, key, c)`, compute `spent = c[key] - _size(c, cleared_key(key))` and `return ("escalated" if spent >= bound else target), c`.
6. Edit `transition()` in `pipeline/core/machine.py`: add a local `def forgive(key: str, target: str) -> tuple[str, dict]:` that runs `if _size(c, key): c[cleared_key(key)] = _size(c, key)` then `return target, c`, and change the `("revalidating", "ok")` row to `return forgive("stale_regate", "implementing")` with a comment saying a pass proves the failures before it did not reproduce and the credit never exceeds them.
7. Run `uv run --group dev pytest -q tests/test_machine.py tests/test_dispatch.py`, confirm 0 failures, and commit `pipeline/core/machine.py` with `tests/test_machine.py` as `fix(TICKET-082): a passing re-gate credits the failures before it`.
8. Add `test_resume_reset_drops_the_forgiveness_credit_too` to `tests/test_cli.py`, modelled on `test_resume_reset_only_zeroes_it_cannot_grant_back_one`: set `t.counters["stale_regate"] = 2` and `t.counters["stale_regate_cleared"] = 1`, run `cli(d, "resume", "TICKET-001", "--stage", "planning", "--reset", "stale_regate")`, and assert both counters are `0` with the message `the reset left a credit behind`; then set them to `2` and `2`, run the same command with `--grant stale_regate`, and assert `(t.counters["stale_regate"], t.counters["stale_regate_cleared"]) == (1, 1)`.
9. Run `uv run --group dev pytest -q tests/test_cli.py -k forgiveness` and confirm `tests/test_cli.py` fails with `the reset left a credit behind`.
10. Edit `pipeline/cli/main.py`: import `cleared_key` alongside `KNOWN_STAGES` from `pipeline.core.machine`, and after the `--grant` loop in `cmd_resume()` add `for key in (*(args.reset or []), *grants):` whose body is `cred = cleared_key(key)` and `if cred in t.counters: t.counters[cred] = min(t.counters[cred], t.counters.get(key, 0))`, commented: `charge()` subtracts this credit, so a counter a human lowered would keep a credit that outlives the failures it forgave.
11. Run `uv run --group dev pytest -q tests/test_cli.py`, confirm 0 failures, and commit `pipeline/cli/main.py` with `tests/test_cli.py` as `fix(TICKET-082): a human reset lowers the forgiveness credit with its counter`.
12. Append to the `stale_regate` paragraph in `README.md`, after the existing mention around line 302: a re-gate that passes credits the failures before it (`stale_regate_cleared`), so the bound counts consecutive failures; a red gate that the next re-gate does not reproduce -- a flaky suite, a machine under load -- costs a re-plan and not the ticket; two failures with no pass between them still escalate.
13. Append a paragraph to the counters section of `README.md`, after the `structural_gate_failures` paragraph around line 397: `stale_regate` is the one counter a later pass credits back; a passing `revalidating` writes `stale_regate_cleared`, capped at the failures already charged, and the bound is compared against the difference; `pipeline resume --reset` and `--grant` lower the credit with its counter, so a reset by a human cannot hand back an attempt twice.
14. Append to invariant 3 in `CLAUDE.md`: a pass can credit failures back -- a passing `revalidating` writes `stale_regate_cleared` and `charge()` subtracts it, so `stale_regate` bounds CONSECUTIVE failures; the credit never exceeds the failures charged, so the loop stays bounded.
15. Run `uv run --group dev pytest -q tests/test_stages.py`, confirm 0 failures, and commit `README.md` with `CLAUDE.md` as `docs(TICKET-082): a passing re-gate credits its failures back`.
16. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, and report both counts; the change to `pipeline/core/machine.py` may leave no failure behind.

## Acceptance criteria

1. `tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget` passes: a fail, then a pass, then a fail at `revalidating` returns `planning`, not `escalated`.
2. `tests/test_machine.py::test_a_forgiveness_credit_is_bounded_and_never_invented` passes: a pass with no failure behind it writes no credit key, and a corrupt credit of 5 still escalates at a raw count of 7.
3. `tests/test_machine.py::test_an_approved_plan_is_re_gated_before_it_is_implemented` still passes: two consecutive fails at `revalidating` escalate.
4. `tests/test_machine.py::test_bounds_escalate_on_the_second_failure` still passes: `review_loops`, `plan_validation_attempts`, `structural_gate_failures` and `blocked_count` each escalate on the second failure.
5. `tests/test_cli.py::test_resume_reset_drops_the_forgiveness_credit_too` passes: `--reset stale_regate` leaves `stale_regate_cleared` at 0, and `--grant stale_regate` on a 2 and 2 pair leaves 1 and 1.
6. `tests/test_stages.py` passes, so `README.md` still documents `stale_regate` within 300 characters after a `planning` mention.
7. `uv run --group dev pytest -q` reports 0 failures.

## Decisions

**A pass at `revalidating` credits its earlier failures instead of zeroing the
counter.** `("revalidating", "ok")` writes `stale_regate_cleared`, and
`charge()` compares the difference against the bound. The raw count stays,
because the thread, `pipeline ls` and the `counters` snapshot on every
`transition` event read it; zeroing it would erase the evidence that a re-gate
ever failed. The effect is that `stale_regate` bounds CONSECUTIVE failures. A
regate failure that the next regate does not reproduce -- a timing test
measuring a loaded machine -- costs one re-plan and not the ticket.

**The credit never exceeds the failures already charged, and that is what
keeps the loop bounded.** `forgive()` sets the credit to `_size(c, key)`, so
after any pass the effective count is 0 and `bound` further failures still
escalate. Raising the credit any other way, or granting it on a stage a ticket
can re-enter without a human, turns invariant 3 into a suggestion.

**Only `stale_regate` is forgiven. `review_loops` deliberately is not.**
`review_loops` is charged by `("review", "fail")`, `("holistic-review",
"fail")` and `("verifying", "fail")` together, so a passing suite would credit
back a review finding -- a different subject entirely. A pass at `verifying`
also ends the ticket (`clean` to `merging`, `ok` to `awaiting-merge`), so on
that path there is no intervening pass to forgive.

**The reproduction keeps its name though the name now reads inverted.** The
frontmatter names
`test_a_non_reproducing_regate_failure_still_exhausts_the_budget` in
`test_file`, and the Tier A gate resolves it by that name against base.
Renaming it makes the gate report that base proves nothing. Same precedent as
DEC-051.

**A human lowering a counter lowers its credit too.** `cmd_resume()` clamps
the cleared companion to its counter after `--reset` and `--grant`. Without
the clamp, `--reset stale_regate` on a counter of 2 with a credit of 1 leaves
a credit worth one attempt nobody granted -- the over-grant DEC-051 exists to
refuse.

## Rollback

Revert the three commits in reverse order: the docs commit, then
`pipeline/cli/main.py` with `tests/test_cli.py`, then
`pipeline/core/machine.py` with `tests/test_machine.py`. Reverting only the
docs commit, or only the CLI commit, is safe on its own. A
`stale_regate_cleared` key left in a live ticket counters map is inert once
`charge()` stops subtracting it, so no ticket needs editing after a revert.
The reproduction test goes red again, which is the pre-fix state.

## Thread

### 2026-08-27 16:15:56Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-28 · triage · ok

Reproduced in this repo, not just the other project the ticket describes.
`stale_regate` never resets on an intervening `ok`: two `("revalidating",
"fail")` calls separated by a `("revalidating", "ok")` still escalate,
identically to two genuinely stale plans. `MAX_ATTEMPTS` (2) charges on raw
fail count; no stage or `transition()` re-runs a failed suite/gate before
charging.

Added `tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget`,
committed on the ticket branch. It fails with:

    AssertionError: two non-reproducing regate failures, separated by a passing regate, exhausted the budget: got 'escalated'

This is `ok`, not `chore`: the fix is a design choice among the three options
the summary lists (re-run-before-charge, serialise suite-running stages, or a
new non-reproducing-failure counter), not a small, fully-specified edit.
Planning should also check whether `("verifying", "fail")` -> `review_loops`
has the same gap; I did not reproduce that one, only `revalidating`.

### 2026-08-27 17:38:19Z · triage · session · session=e6575ed3-49f8-40b1-8925-15951e0405b8

`triage` ran as session `e6575ed3-49f8-40b1-8925-15951e0405b8`
- replay: `claude --resume e6575ed3-49f8-40b1-8925-15951e0405b8`
- log: `.project/logs/TICKET-082-triage-e6575ed3.log`

### 2026-08-27 17:38:19Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Confirmed stale_regate never resets on an intervening ok; two non-reproducing regate failures still escalate. Added a failing test on the ticket branch.

### 2026-08-28 - planning - ok

Planned the third option in the summary: a pass at `revalidating` credits its
earlier failures, so `stale_regate` bounds consecutive failures. It is the
only option the committed reproduction can pass -- that test drives
`transition()` alone, and options 1 and 2 live in
`pipeline/daemon/supervisor.py`.

Left out deliberately:
- Re-running a failed gate once before charging. It doubles the cost of a
  genuine red gate and needs a second child in `finish_gate()`. Worth its own
  ticket if a flake survives this fix.
- Serialising the suite-running stages. That is `max_parallel` from
  TICKET-069, not this ticket.

Triage asked whether `("verifying", "fail")` has the same gap. It has the same
shape and no reach. `review_loops` is shared with `("review", "fail")` and
`("holistic-review", "fail")`, so forgiving it would credit back a review
finding. A passing suite at `verifying` also sends the ticket to `merging` or
`awaiting-merge` and never returns, so no intervening pass exists to forgive.
Left unchanged, on purpose.

The fourth answer in the summary stands: a test asserting a hard timing ratio
measures the machine, and the project should pin a floor instead. This fix
stops the pipeline turning that measurement into an escalation. It does not
make the test sound.

### 2026-08-27 17:50:38Z · planning · session · session=deadae6b-5726-4374-8c4e-652a92dc6e41

`planning` ran as session `deadae6b-5726-4374-8c4e-652a92dc6e41`
- replay: `claude --resume deadae6b-5726-4374-8c4e-652a92dc6e41`
- log: `.project/logs/TICKET-082-planning-deadae6b.log`

### 2026-08-27 17:50:38Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned the credit fix: a passing revalidating credits its earlier stale_regate failures, so the bound counts consecutive failures.

### 2026-08-28 - plan-validation - ok

(The Tier A gate entry below ran before this one. The file ends inside a fence
whose bytes I cannot reproduce, so I inserted here rather than rewrite it.)

Passed on all eight items.

1. Root cause: `charge()` (`pipeline/core/machine.py:89`) compares a lifetime
   counter against the bound, and no row credits or resets `stale_regate`. The
   plan changes that comparison, so it fixes the cause, not the test.
2. Decisions: DEC-029, DEC-047, DEC-051 and DEC-065 exist and say what the
   ticket claims. DEC-047's scan reads the first changed key; `forgive()`
   writes on the `ok` row, which returns `implementing`, so the scan is
   unaffected.
3. Scope: 6 files, 3 commits. Steps 12-14 document a semantics change
   `CLAUDE.md` invariant 3 states. No step is untraceable.
4. Criteria: I re-ran the arithmetic against the code. `stale_regate` is
   outside `BOUNDS` and `SIZE_SCALED`, so `bound_for()` returns `MAX_ATTEMPTS`
   (2), and a credit of 5 escalates at a raw count of 7 -- criterion 2.
   Criterion 4 proves the subtraction leaves the other counters alone.
5. Every step names files and functions. No research is left.
6. Riskiest step is 6, editing `transition()` (`machine.FENCED`). `## Rollback`
   states the fallback and that an orphan credit key is inert.
7. Regressions: `tests/test_dispatch.py:433` reads `stale_regate == 1`, and the
   raw count is unchanged. Steps 7, 11 and 15 run the covering suites.

Note for `implementing`, not a finding: once a credit exists, `advance()`
renders the reason as `` `stale_regate` reached its bound (3/2) `` -- raw count
against bound. No test asserts that string.

### 2026-08-27 20:14:53Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget` fails as required
```
>       [94massert[39;49;00m nxt3 != [33m"[39;49;00m[33mescalated[39;49;00m[33m"[39;49;00m, ([90m[39;49;00m
            [33m"[39;49;00m[33mtwo non-reproducing regate failures, separated by a passing regate, [39;49;00m[33m"[39;49;00m[90m[39;49;00m
            [33mf[39;49;00m[33m"[39;49;00m[33mexhausted the budget: got [39;49;00m[33m{[39;49;00mnxt3[33m!r}[39;49;00m[33m"[39;49;00m[90m[39;49;00m
        )[90m[39;49;00m
[1m[31mE       AssertionError: two non-reproducing regate failures, separated by a passing regate, exhausted the budget: got 'escalated'[0m
[1m[31mE       assert 'escalated' != 'escalated'[0m

[1m[31mtests/test_machine.py[0m:204: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_machine.py::[1mtest_a_non_reproducing_regate_failure_still_exhausts_the_budget[0m - AssertionError: two non-reproducing regate failures, separated by a passing...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.04s[0m[31m ===============================[0m

```
- ok: `tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget` fails on base `main` too -- the bug is not already fixed upstream
```
[0m:204: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_machine.py::[1mtest_a_non_reproducing_regate_failure_still_exhausts_the_budget[0m - AssertionError: two non-reproducing regate failures, separated by a passing...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.10s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-tib26nc7/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-tib26nc7/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 20:20:00Z · plan-validation · session · session=195b86a0-0e2e-4157-9399-6f969b7561ba

`plan-validation` ran as session `195b86a0-0e2e-4157-9399-6f969b7561ba`
- replay: `claude --resume 195b86a0-0e2e-4157-9399-6f969b7561ba`
- log: `.project/logs/TICKET-082-plan-validation-195b86a0.log`

### 2026-08-27 20:20:00Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight judgment items: root cause is charge() comparing a lifetime counter against the bound, criteria are falsifiable, and the credit-5-escalates-at-7 arithmetic checks out against BOUNDS.

### 2026-08-27 20:20:56Z · human · approval · by=chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Verified anchors: charge() at machine.py:89, the ('revalidating','ok') row at :134, _size at :62. NOTE: this edits transition() in machine.py, which machine.FENCED covers -- it will park at awaiting-merge for a human, and it should.

**approved by chezzijr (via Claude Code, while away; reviewer also filed this ticket -- audit in thread). Verified anchors: charge() at machine.py:89, the ('revalidating','ok') row at :134, _size at :62. NOTE: this edits transition() in machine.py, which machine.FENCED covers -- it will park at awaiting-merge for a human, and it should.**

### 2026-08-27 20:28:30Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget` fails as required
```
>       [94massert[39;49;00m nxt3 != [33m"[39;49;00m[33mescalated[39;49;00m[33m"[39;49;00m, ([90m[39;49;00m
            [33m"[39;49;00m[33mtwo non-reproducing regate failures, separated by a passing regate, [39;49;00m[33m"[39;49;00m[90m[39;49;00m
            [33mf[39;49;00m[33m"[39;49;00m[33mexhausted the budget: got [39;49;00m[33m{[39;49;00mnxt3[33m!r}[39;49;00m[33m"[39;49;00m[90m[39;49;00m
        )[90m[39;49;00m
[1m[31mE       AssertionError: two non-reproducing regate failures, separated by a passing regate, exhausted the budget: got 'escalated'[0m
[1m[31mE       assert 'escalated' != 'escalated'[0m

[1m[31mtests/test_machine.py[0m:204: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_machine.py::[1mtest_a_non_reproducing_regate_failure_still_exhausts_the_budget[0m - AssertionError: two non-reproducing regate failures, separated by a passing...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.08s[0m[31m ===============================[0m

```
- ok: `tests/test_machine.py::test_a_non_reproducing_regate_failure_still_exhausts_the_budget` fails on base `main` too -- the bug is not already fixed upstream
```
[0m:204: AssertionError
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/test_machine.py::[1mtest_a_non_reproducing_regate_failure_still_exhausts_the_budget[0m - AssertionError: two non-reproducing regate failures, separated by a passing...
[31m!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!![0m
[31m============================== [31m[1m1 failed[0m[31m in 0.10s[0m[31m ===============================[0m
Using CPython [36m3.13.11[39m[36m[39m
Creating virtual environment at: [36m.venv[39m
   [36m[1mBuilding[0m[39m pipeline[2m @ file:///tmp/pipeline-base-z411zcvz/base[0m
      [32m[1mBuilt[0m[39m pipeline[2m @ file:///tmp/pipeline-base-z411zcvz/base[0m
[1m[33mwarning[39m[0m[1m:[0m [1mFailed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.[0m
[2mInstalled [1m18 packages[0m [2min 10ms[0m[0m

```

### 2026-08-27 20:28:31Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-28 - implementing - ok

Todo (all done):
1. Confirm reproduction fails as described -- done.
2. Add `test_a_forgiveness_credit_is_bounded_and_never_invented` -- done.
3. Confirm it fails with `KeyError: stale_regate_cleared` -- done.
4. Add `cleared_key()` -- done.
5. Edit `charge()` to subtract the credit -- done.
6. Edit `transition()`'s `("revalidating", "ok")` row to call `forgive()` -- done.
7. Run `test_machine.py`/`test_dispatch.py`, commit -- done.
8. Add `test_resume_reset_drops_the_forgiveness_credit_too` -- done.
9. Confirm it fails with "the reset left a credit behind" -- done.
10. Clamp the credit in `cmd_resume()` after `--reset`/`--grant` -- done.
11. Run `test_cli.py`, commit -- done.
12-13. README.md: `stale_regate` paragraph and counters section -- done.
14. CLAUDE.md invariant 3 -- done.
15. Run `test_stages.py`, commit -- done.
16. Full suite + guard -- done.

Executed the plan as written, all 16 steps, 3 commits (`529868e`,
`f786b8c`, `dc625b0`). Each new test went RED for the stated reason before
GREEN, per TDD.

`tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
failed intermittently during my run (`expected serve() to exit after tick 1,
got 2`), unrelated to `stage`, `revalidating` or `machine.py`. I verified it
fails the same way with my changes stashed out, so it predates this ticket --
not fixing it, out of scope. It passed in the final full-suite run (406
passed).

`uv run --group dev pytest -q`: 406 passed.
`./pipeline/hooks/test_dangerous_commands.py`: guard: all passed (122 cases).

All 7 acceptance criteria met. No plan deviation.

### 2026-08-27 20:32:02Z · implementing · session · session=9579d65c-d69c-4c09-b6d9-cacadf00b08b

`implementing` ran as session `9579d65c-d69c-4c09-b6d9-cacadf00b08b`
- replay: `claude --resume 9579d65c-d69c-4c09-b6d9-cacadf00b08b`
- log: `.project/logs/TICKET-082-implementing-9579d65c.log`

### 2026-08-27 20:32:02Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Implemented the stale_regate forgiveness credit (steps 1-16): machine.py charge()/forgive(), cli/main.py reset/grant clamp, README.md/CLAUDE.md docs, all three planned tests RED then GREEN. Full suite 406 passed, guard 122 passed.

### 2026-08-28 - review - ok

Reviewed `git diff main...HEAD`: 6 files, +108/-4. No blocking findings.

Verified all 7 acceptance criteria. The 5 named tests pass (`5 passed in
0.30s`). `uv run --group dev pytest -q`: `406 passed in 19.45s`.
`./pipeline/hooks/test_dangerous_commands.py`: `guard: all passed`.

Refuted before writing: `charge()` cannot loop forever on a forged credit.
`forgive()` writes the credit only on an `ok` row, so `c[key]` grows while
the credit stays fixed (`pipeline/core/machine.py:126`); the credit-5 case
escalates at raw 7. DEC-047 holds: the `charged` scan runs only when
`nxt == "escalated"` (`pipeline/daemon/supervisor.py:126`), and `forgive()`
never escalates.

Non-blocking findings:

1. minor -- `min(t.counters[cred], ...)` (`pipeline/cli/main.py:258`) raises
   `TypeError` on a non-int credit read from a ticket file. Before this diff,
   `--reset` on such a ticket succeeded. Counter values are not
   type-validated (`pipeline/core/ticket.py:532`). `_size()` is the existing
   clamp for this.
2. minor -- the escalation reason quotes the raw count against the bound
   (`pipeline/daemon/supervisor.py:135`), so a forgiven `stale_regate`
   escalates reading "`stale_regate` reached its bound (3/2)".

Observation, not a finding:
`tests/test_dispatch.py::test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
fails when `tests/test_dispatch.py` runs alone (`expected serve() to exit
after tick 1, got 2`) and passes in the full suite. It reads the operator's
real registry, which lists two projects, so `tick` fires twice per loop pass.
The diff touches no file under `pipeline/daemon/`.

### 2026-08-27 20:35:34Z · review · session · session=5abe2640-452e-42a6-8c5f-9990a4e82578

`review` ran as session `5abe2640-452e-42a6-8c5f-9990a4e82578`
- replay: `claude --resume 5abe2640-452e-42a6-8c5f-9990a4e82578`
- log: `.project/logs/TICKET-082-review-5abe2640.log`

### 2026-08-27 20:35:34Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the 6-file delta: no blocking findings, 7/7 acceptance criteria met, 406 passed, guard all passed; two minor findings in the thread.

### 2026-08-27 20:35:55Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/core/machine.py:transition`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-082` lands it; `pipeline resume TICKET-082 --stage planning` sends it back.

### 2026-08-28 02:15:00Z · human · approval · by=chezzijr (via Claude Code, on explicit instruction to approve this merge). FENCED review: transition() stays pure -- forgive() mutates the same local copy charge() already does; only the ('revalidating','ok') row changes; the credit never exceeds the failures it forgives; charge()'s subtraction is a no-op for every counter that has no credit, so all other bounds are unchanged.

**approved by chezzijr (via Claude Code, on explicit instruction to approve this merge). FENCED review: transition() stays pure -- forgive() mutates the same local copy charge() already does; only the ('revalidating','ok') row changes; the credit never exceeds the failures it forgives; charge()'s subtraction is a no-op for every counter that has no credit, so all other bounds are unchanged.**

### 2026-08-28 03:43:57Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/082


Rebasing (1/4)Rebasing (2/4)Rebasing (3/4)Rebasing (4/4)Successfully rebased and updated refs/heads/ticket/082.
Already up to date.
Updating abd37b3..adab498
Fast-forward
 CLAUDE.md                |  4 ++++
 README.md                | 12 +++++++++++-
 pipeline/cli/main.py     |  8 +++++++-
 pipeline/core/machine.py | 19 +++++++++++++++++--
 tests/test_cli.py        | 30 ++++++++++++++++++++++++++++++
 tests/test_machine.py    | 39 +++++++++++++++++++++++++++++++++++++++
 6 files changed, 108 insertions(+), 4 deletions(-)

```

### 2026-08-28 03:43:57Z · merging · decision

decision recorded as `DEC-082`
