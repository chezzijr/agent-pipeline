---
id: TICKET-026
stage: done
class: feature
branch: ticket/026
test_file: tests/test_machine.py::test_a_small_fix_takes_the_cheap_route
files_declared:
- .claude/skills/file-ticket/SKILL.md
- README.md
- pipeline/core/machine.py
- pipeline/stages/implementing.md
- pipeline/stages/quick-review.md
- pipeline/stages/triage.md
- tests/test_machine.py
- tests/test_stages.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: holistic-review
  id: 4d5c4c0c-0cc1-4ee1-9593-caa2a7ffc043
  log: .project/logs/TICKET-026-holistic-review-4d5c4c0c.log
approved_by: chezzijr
approved_at: '2026-08-21T09:36:11.350747+00:00'
---

## Summary

a one-line ticket pays for planning, plan-validation and a full review

TICKET-025 changed one line in one file:

    --tools "{tools}" --strict-mcp-config \

It cost **$6.28** and ran nine stages. Measured across this session, from each
stage's final `result` event:

| stage | runs | $/run | share of $160.66 |
|---|---|---|---|
| planning | 16 | 3.60 | 36% |
| plan-validation | 18 | 2.11 | 24% |
| triage | 13 | 1.79 | 15% |
| review | 10 | 2.15 | 13% |
| implementing | 10 | 1.86 | 12% |

60% of the money decides what to do. For a ticket whose fix is one flag, that
work has no content: the plan restates the diff and the validator scores a plan
nobody needed.

Expected: a ticket whose fix is small skips `planning`, `plan-validation`, the
approval gate and the full `review`, and still leaves a failing test, a diff, a
green suite and an auditable thread behind.

    chore:  triage -> implementing -> quick-review -> verifying -> merging
    full:   triage -> planning -> plan-validation -> awaiting-approval
                   -> revalidating -> implementing -> review -> verifying -> merging

Three constraints the plan must respect. They are what separate this from a
hole in the design:

1. **The dispatcher decides the route, not the agent.** `triage` may report a
   new result value meaning "reproduced, and the fix is small" -- it must not
   write `class` or any other control field. CLAUDE.md invariant 1.
2. **A review still runs.** `review` bounced three tickets today
   (TICKET-016, TICKET-019, TICKET-022) and every one was a vacuous test that a
   green suite hid. A `quick-review` stage on sonnet with one question --
   *does the committed test fail without this diff, and does the diff touch a
   file the ticket did not name?* -- keeps that check at a fraction of $2.15.
3. **The cheap path can promote itself.** If `quick-review` finds anything
   outside its two questions, it returns `fail` and the ticket goes to
   `planning` with the finding in its thread. A fast path that cannot escalate
   into the slow one is how a vacuous test lands unattended.

Adding a stage is documented: one `pipeline/stages/quick-review.md`, one row in
`transition()`, one `BOUNDS` entry. `transition()` is a human-review-before-merge
file (CLAUDE.md), so expect that gate.

Triage confirmed the gap and committed a failing test for the whole route (see
`## Reproduction`). Today `transition("triage", "chore", ...)` falls through the
`match` and returns `escalated`: no cheap route exists, and no `chore` class,
`quick-review` stage or prompt file exists anywhere in the repo.

**Planning, 2026-08-21.** The plan is written; nothing above is edited, because
`quick-review`'s second question checks the diff against the files this section
names. Route: `counters["cheap_route"]`, set by `transition("triage", "chore")`
and consumed by `transition("implementing", ...)`, carries the ticket to the new
`quick-review` stage. No `chore` class and no `BOUNDS` entry are added -- the
ticket's sketch named one, and `## Decisions` says why a class cannot carry this
route. Eight files, seventeen steps, two commits.

**Planning, second pass.** The Tier A gate failed the first plan on two mechanical checks,
not on its content: plan step 15 named no declared file, and one acceptance criterion named
no test. Step 15 is now two steps and each names a declared path; the whole-suite criterion
names `tests/`. No row of the state machine, no stage prompt and no declared file changed.

**Plan-validation, 2026-08-21.** The plan passes all eight judgment items.
Execute `## Plan` steps 1-17 as written; nothing needs re-planning. Two findings
recorded, neither blocking: steps 11-14 edit prose files (`triage.md`,
`implementing.md`, `README.md`, `SKILL.md`) that no test can falsify, and the
cheap route has no `_base_findings()` substitute -- `## Decisions` already
states the second. Verified against the code: `advance()` writes the returned
counters back (`supervisor.py:125`), `validate_meta()` constrains no counter
key, `start()` spawns `quick-review` with no dispatcher change, and
`pipeline resume <id> --stage <s>` from `## Rollback` exists (`cli/main.py:452`).

**Implementing, 2026-08-21.** All 17 plan steps executed, two commits: `9b595bb`
(`feat: a small fix takes the cheap route`, `pipeline/core/machine.py` +
`tests/test_machine.py`) and `98747d4` (`feat: quick-review stage for the cheap
route`, `pipeline/stages/quick-review.md` new, `pipeline/stages/triage.md`,
`pipeline/stages/implementing.md`, `tests/test_stages.py`, `README.md`,
`.claude/skills/file-ticket/SKILL.md`). Whole suite: `195 passed in 8.67s`.
Guard script: `guard: all passed`. Details and command output in `## Thread`.

**Review, 2026-08-21.** The delta `4286a01..98747d4` passes: no blocking findings.
It matches `## Plan` steps 1-17 and touches exactly the eight files `## Digest`
names. Re-ran the suite: `195 passed in 8.57s`. Checked in the shipped code:
`transition()` still copies its input (`machine.py:30`), the route is one-way
(the flag is consumed at both `("implementing", ...)` rows and no row back to
`implementing` sets it), `chore` reaches `transition()` with no dispatcher
whitelist in the way (`supervisor.py:749`), and `quick-review` is reachable under
the new test's variants, so the prompt file is enforced. Two minor findings, both
follow-ups on text the approval gate already passed: `quick-review`'s question 1
uses a `<base>...HEAD` range that always contains triage's own test commit, and
the README diagram's cheap-route arrow ends at a column no `|` occupies. One check
is unreproduced: the guard's read-only allowlist refuses
`./pipeline/hooks/test_dangerous_commands.py`, and the delta touches no hook file.

**Holistic review, 2026-08-21.** The accumulated change is coherent: no drift,
nothing unasked, no partial undo. Three commits (`4286a01`, `9b595bb`,
`98747d4`), no fixups. The four machine rows close the route end to end and
one-way, `quick-review`'s promotion charges no counter and needs none, and no
list of stages or result values exists outside `machine.py` to fall out of sync.
Re-ran the whole suite: `195 passed in 8.48s`. One correction to the thread, not
to the code: `review`'s diffstat records `tests/test_machine.py | 23 ++` and
`133 insertions(+)`; the delta has `10` and `120`. Its file list is right.

## Reproduction

Test: `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route`
(commit `3770816`, branch `ticket/026`).

Command:

    uv run --group dev pytest -q "tests/test_machine.py::test_a_small_fix_takes_the_cheap_route"

Output:

    >       assert t("triage", "chore")[0] == "implementing", \
                "a small fix still pays for planning, plan-validation and the approval gate"
    E       AssertionError: a small fix still pays for planning, plan-validation and the approval gate
    E       assert 'escalated' == 'implementing'
    E
    E         - implementing
    E         + escalated

    tests/test_machine.py:153: AssertionError
    1 failed in 0.07s

expect: assert 'escalated' == 'implementing'

The test pins the whole cheap route, so three later assertions still fail after
the first is fixed:

1. `t("quick-review", "ok")[0] == "verifying"`
2. `t("quick-review", "fail")[0] == "planning"` -- the promotion path
3. `"quick-review" in M.KNOWN_STAGES`

Names the test pins, because a test must pin something: the triage result value
is `chore` and the new stage is `quick-review`. Both come from the ticket's own
route sketch. Renaming either is a plan decision -- update the test with it.

## Digest

Files touched: `pipeline/core/machine.py` (the four new rows), `pipeline/stages/quick-review.md` (new), `pipeline/stages/triage.md` and `pipeline/stages/implementing.md` (the two prompts the new route changes), `tests/test_machine.py` and `tests/test_stages.py`, `README.md` and `.claude/skills/file-ticket/SKILL.md`.

Key functions: `transition()` at `pipeline/core/machine.py:24` is the only function this route lives in. `advance()` (`pipeline/daemon/supervisor.py:88`) calls it and writes `counters` back; `start()` (`pipeline/daemon/supervisor.py:429`) spawns any stage that is not in `TERMINAL`, `HUMAN_GATES` or one of the three hard-coded dispatcher branches, so `quick-review` needs no dispatcher change at all.

Entry point for the route carrier: `counters`. It is a `CONTROL_FIELDS` member, restored from the pre-spawn snapshot at `pipeline/daemon/supervisor.py:697`, so no agent can put a ticket on the cheap route. `class` is not read and not extended.

Gotcha 1 -- `quick-review` cannot re-run the test with the diff reverted. It is `write: false`, so `tree_snapshot()` escalates any tree change, and the read-only allowlist at `pipeline/hooks/dangerous-commands.py:28` permits `git diff|log|show|blame` but not `git stash`, `git checkout` or `git worktree add`. Its "does the test fail without this diff" question is answered from `## Reproduction` plus a `git diff` over the test file, not by running anything.

Gotcha 2 -- the Tier A gate never runs on the cheap route. `gate()` is called from `start()` only in the `plan-validation` branch (`pipeline/daemon/supervisor.py:544`), and it requires `## Plan`, `## Digest`, `## Acceptance criteria` and a non-empty `files_declared`, none of which a chore ticket has. The base check `_base_findings()` (`pipeline/core/gate.py:39`) -- the one that catches a test which passes on base -- therefore does not run either. `quick-review` is its only substitute.

Gotcha 3 -- `tests/test_stages.py:29` computes reachable stages with `M.transition(s, r, {})` and never varies `counters` or `klass`. `holistic-review` is already invisible to it today. Adding the `chore` result alone does not make `quick-review` visible; the variants have to vary too, or the new prompt file is unenforced.

Gotcha 4 -- a stage prompt must not declare a `tools:` key without `Write` or `Edit`. `tests/test_harness.py:167`, `test_every_stage_can_write_its_result_sidecar`, fails it: given Bash alone the guard refuses `>`, so the stage cannot write its own `.result`. The new prompt declares no `tools:` key and inherits `readonly_tools = "Read,Grep,Glob,Bash,Write,Edit"`.

Gotcha 5 -- `pipeline/stages/implementing.md:14` opens "The plan is already researched and approved. Execute it." On the cheap route there is no plan, so that prompt needs the no-plan branch in §8.

Verified before this plan was written: the four rows below satisfy every assertion in the committed test plus the one-way property. A scratch copy of the same `match` block printed `all ok`.

### §1 -- the `("triage", "chore")` row, after the `("triage", "rejected")` row

        case ("triage", "chore"):
            # the cheap route. TICKET-025 changed one line and paid $6.28 for
            # planning, plan-validation, an approval gate and a full review.
            # The flag lives in `counters` -- dispatcher-owned and restored
            # from the pre-spawn snapshot -- so no agent can put a ticket on
            # this route, and `class` keeps meaning what it meant: loop
            # budgets, and whether a holistic review runs.
            c["cheap_route"] = 1
            return "implementing", c

### §2 -- the two `implementing` rows, replacing the existing pair

        case ("implementing", "ok"):
            # CONSUMED here, not cleared later. `implementing` is the cheap
            # route's only exit, so a ticket bounced back by a red suite takes
            # the full `review` on its second pass. One-way by construction:
            # nothing routes back onto the cheap path.
            if c.pop("cheap_route", None):
                return "quick-review", c
            return "review", c
        case ("implementing", "blocked"):
            if c.pop("cheap_route", None):
                # there is no plan to re-gate, so the normal target would fail
                # its own Tier A gate on the missing sections and burn one of
                # the two plan attempts before landing here anyway
                return "planning", c
            return charge("blocked_count", "plan-validation")

### §3 -- the two `quick-review` rows, after the `implementing` rows

        case ("quick-review", "ok"):
            return "verifying", c
        case ("quick-review", "fail"):
            # promotion, not a retry, so it charges no counter: the cheap check
            # found something outside its two questions, and the ticket takes
            # the full path from `planning`. It cannot come back -- the flag
            # was consumed at `implementing`.
            return "planning", c

### §4 -- assertions appended to `test_a_small_fix_takes_the_cheap_route`

    nxt, c = t("triage", "chore")
    assert c["cheap_route"] == 1, "nothing carries the route as far as `implementing`"
    assert t("implementing", "ok", c) == ("quick-review", {}), \
        "the cheap route pays for the full review, or leaks its flag past the stage that consumes it"
    assert t("implementing", "ok", {})[0] == "review", "the full route changed"
    assert t("implementing", "blocked", {"cheap_route": 1})[0] == "planning", \
        "a blocked chore re-gates a plan that does not exist"
    assert t("quick-review", "fail", {"cheap_route": 1})[0] == "planning"
    assert "cheap_route" not in M.BOUNDS.get("bugfix", {}), \
        "a route flag is not a bounded loop counter"

### §5 -- `pipeline/stages/quick-review.md`, in full

    ---
    model: sonnet
    # medium: two questions against a diff of a few lines. `low` is triage's
    # tier -- run one command. This stage judges, and DEC-024's rule holds:
    # one extra bounce costs more than an effort downgrade saves.
    effort: medium
    write: false
    max_usd: 2
    hooks: [dangerous-commands]
    ---

    ## Your stage: quick-review

    This ticket took the cheap route: no plan, no plan-validation, no approval
    gate. You are the only review it gets. You are read-only -- do not modify
    any file except the ticket. The dispatcher snapshots the working tree
    before you start and escalates the ticket if anything changed.

    Answer exactly two questions. Do not review style, naming or design.

    1. **Does the committed test fail without this diff?** You cannot revert
       the diff: you are read-only, and `git stash` is not on your allowlist.
       Read `## Reproduction` for the failure triage recorded, then run
       `git diff <base>...HEAD -- <test file>` for the file named in
       `test_file`. If the diff changed the test triage committed, that
       recorded failure no longer proves anything: answer no.
    2. **Does the diff touch a file the ticket did not name?** Run
       `git diff --name-only <base>...HEAD`. For each file, quote the line in
       `## Summary` or `## Reproduction` that names it. A file no section names
       is an unnamed file, whatever `files_declared` says -- on this route
       `implementing` writes that field itself, so it cannot vet its own diff.

    Append your answers to `## Thread`: one numbered entry per question, each
    with the command you ran and its output.

    Anything you find outside those two questions -- a test that cannot fail, a
    diff that does more than the ticket asked, a claim you cannot check -- is
    `fail`. That is not an accusation: it promotes the ticket to `planning` for
    the full path, which is what the cheap route is allowed to cost when it is
    wrong. Guessing `ok` is not.

    `result`: `ok` (both questions answered yes) | `fail` (either answered no,
    or anything else found -- say which, and quote it)

### §6 -- the replacement for `test_every_stage_named_by_the_state_machine_has_a_prompt`

    def test_every_stage_named_by_the_state_machine_has_a_prompt():
        # `counters` and `klass` are part of the table, not decoration:
        # `holistic-review` is reachable only for a non-bugfix class, and
        # `quick-review` only with `cheap_route` set. Varying `result` alone
        # left both prompts unenforced.
        variants = [({}, "bugfix"), ({}, "refactor"), ({"cheap_route": 1}, "bugfix")]
        reachable = {M.transition(s, r, c, k)[0] for s in C.agent_stages()
                     for r in ["ok", "fail", "blocked", "rejected", "chore"]
                     for c, k in variants}
        assert {"quick-review", "holistic-review"} <= reachable, \
            "a variant stopped covering the class- or route-dependent rows"
        for stage in reachable - M.TERMINAL - M.HUMAN_GATES - M.DISPATCHER_STAGES:
            assert (C.STAGES_DIR / f"{stage}.md").is_file(), f"no prompt for `{stage}`"

### §7 -- the `chore` result added to `pipeline/stages/triage.md`

Replace that prompt's two-entry `result:` list with these three entries, keeping the two existing ones verbatim:

    `result`:
    - `ok` -- reproduced, failing test committed
    - `chore` -- reproduced, failing test committed, AND the fix is small: you
      can name every file it touches, each edit is a few lines, and no design
      choice is left to make. The ticket then skips planning, plan-validation
      and the approval gate, so `ok` is the safe answer whenever you are
      unsure. Name the files you expect the fix to touch in `## Thread`;
      `quick-review` checks the diff against them.
    - `rejected` -- cannot reproduce, or the ticket is invalid. Append
      everything you tried to `## Thread` first; a rejection nobody can audit
      is worthless.

### §8 -- the no-plan branch added to `pipeline/stages/implementing.md`

Insert after that prompt's numbered steps, before the "If the plan turns out to be wrong" paragraph:

    A ticket on the cheap route has no `## Plan` and no `## Digest`: `triage`
    judged the fix small, and the dispatcher skipped planning. If `## Plan` is
    empty, work from `## Summary` and `## Reproduction` instead, keep the diff
    inside the files those two sections name, and report every file you touched
    in `files_declared`. If the fix needs a file the ticket never names, that
    is `blocked`, not a wider diff -- `blocked` sends it to `planning`, which
    is where a fix that size belonged.

### §9 -- `README.md`

The diagram at line 11 gains the cheap route, and the result list at line 226 becomes `result: ok|chore|fail|blocked|rejected`:

        triage -> planning -> plan-validation -> [human] -> revalidating
          |                                                       |
          |    done <- merging <- verifying <- review <- implementing
          |                          |
          +-- (chore) -> implementing -> quick-review --+

### §10 -- `.claude/skills/file-ticket/SKILL.md`

The sentence "The ticket will stop at `awaiting-approval` for the human -- that gate is the point" is now conditional. Say instead: the ticket stops at `awaiting-approval` unless `triage` judges the fix small enough for the cheap route (`triage -> implementing -> quick-review -> verifying -> merging`), which has no human gate; `quick-review` returns it to `planning`, and so to the approval gate, if the diff or the test does not hold up. The class table does not change: there is no `chore` class, and a human cannot request the cheap route.

## Decisions checked

Grep terms over `.project/decisions/`: `route`, `triage`, `review`, `class`, `counters`, `stage`, `effort`, `cheap`, `chore`, `gate`. Ten records exist; none carries a `superseded-by:` line.

- **DEC-024** constrains this change, and this plan complies rather than superseding it. It records that `review`, `plan-validation` and `planning` declare `effort: high` deliberately, and that "a later cost-cutting pass must not flatten them". No existing `effort` value changes here. The new stage has a narrower job and a promotion path: anything outside its two questions sends the ticket to `planning`. DEC-024's own rule -- one extra bounce costs more than an effort downgrade saves -- is why `quick-review` fails toward `planning` rather than toward `ok`.
- **DEC-018** records the Tier A gate's requirements on `## Plan`, `## Digest` and `files_declared`. It is why the cheap route cannot run `gate()` at all, and that consequence is recorded in `## Decisions` below rather than worked around.
- **DEC-017** records `base_checkout()` and the base re-run in `pipeline/core/gate.py`. Same reason: that check is dispatcher-side Python inside `gate()`, not something a read-only stage can invoke.
- **DEC-025** is the ticket that motivated this one. It constrains `pipeline/harnesses/claude-code.toml`, which this plan does not touch.
- **DEC-022** records the merge serialisation in `pipeline/daemon/supervisor.py`. Unaffected: this plan adds no dispatcher stage and no worktree operation.

## Plan

1. In `pipeline/core/machine.py`, add `"quick-review"` to the `KNOWN_STAGES` set literal, next to `"review"`.
2. In `pipeline/core/machine.py`, insert the `("triage", "chore")` row from `## Digest` §1 immediately after the existing `("triage", "rejected")` row.
3. In `pipeline/core/machine.py`, replace the existing `("implementing", "ok")` and `("implementing", "blocked")` rows with the pair in `## Digest` §2, comments included verbatim.
4. In `pipeline/core/machine.py`, insert the two `("quick-review", ...)` rows from `## Digest` §3 immediately after the `("implementing", "blocked")` row.
5. Append the six assertions in `## Digest` §4 to `test_a_small_fix_takes_the_cheap_route` in `tests/test_machine.py`, leaving the four assertions from commit `3770816` exactly as they are.
6. Run `uv run --group dev pytest -q tests/test_machine.py` and confirm every test passes, `test_happy_path` and `test_bounds_escalate_on_the_second_failure` included.
7. Commit `pipeline/core/machine.py` and `tests/test_machine.py` together as `feat: a small fix takes the cheap route`.
8. Create `pipeline/stages/quick-review.md` with the frontmatter and body in `## Digest` §5, verbatim, including `hooks: [dangerous-commands]` and no `tools:` key.
9. Replace `test_every_stage_named_by_the_state_machine_has_a_prompt` in `tests/test_stages.py` with the version in `## Digest` §6.
10. Run `uv run --group dev pytest -q tests/test_stages.py`, confirm it passes, then move `pipeline/stages/quick-review.md` aside, re-run, confirm the failure names `quick-review`, and move it back.
11. Replace the `result:` list in `pipeline/stages/triage.md` with the three entries in `## Digest` §7.
12. Add the no-plan branch from `## Digest` §8 to `pipeline/stages/implementing.md`, after its numbered steps and before the "If the plan turns out to be wrong" paragraph.
13. Update the route diagram at `README.md:11` and the result list at `README.md:226` as in `## Digest` §9.
14. Update the human-gate sentence in `.claude/skills/file-ticket/SKILL.md` as in `## Digest` §10, changing no row of its class table.
15. Run `uv run --group dev pytest -q` over the whole suite, which collects `tests/test_machine.py` and `tests/test_stages.py`, and quote its final line in `## Thread`.
16. Run `./pipeline/hooks/test_dangerous_commands.py` for the guard's 79 cases and quote its final line in `## Thread` -- this ticket edits no hook, and `pipeline/stages/quick-review.md` declares `hooks: [dangerous-commands]`, so a red run there is a pre-existing break, not this diff.
17. Commit `pipeline/stages/quick-review.md`, `pipeline/stages/triage.md`, `pipeline/stages/implementing.md`, `tests/test_stages.py`, `README.md` and `.claude/skills/file-ticket/SKILL.md` as `feat: quick-review stage for the cheap route`.

## Acceptance criteria

- `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` passes, the six appended assertions included.
- `tests/test_machine.py::test_happy_path` and `tests/test_machine.py::test_bounds_escalate_on_the_second_failure` still pass: the full route and every existing bound are unchanged.
- `tests/test_stages.py::test_every_stage_named_by_the_state_machine_has_a_prompt` fails, naming `quick-review`, when `pipeline/stages/quick-review.md` is moved aside; step 10 runs exactly that.
- `tests/test_stages.py::test_every_stage_declares_the_effort_its_job_needs` and `tests/test_stages.py::test_every_stage_that_can_run_bash_has_the_guard` pass with the new stage file present.
- `tests/test_harness.py::test_every_stage_can_write_its_result_sidecar` passes: `quick-review` inherits `readonly_tools`, so it can write its own `.result`.
- `uv run --group dev pytest -q` reports no failures across `tests/` -- the whole suite, not only the files this ticket edits.
- `./pipeline/hooks/test_dangerous_commands.py` prints its own pass line for all 79 guard cases; pytest collects only its two `test_*` functions, never those tables.

## Decisions

**The cheap route is carried in `counters`, not in `class`.** The route spans two hops -- `triage -> implementing`, then `implementing -> quick-review` -- and `transition()` returns only `(next_stage, counters)`. `counters["cheap_route"]` is the one dispatcher-owned value that already round-trips: it is a `CONTROL_FIELDS` member restored from the pre-spawn snapshot, so no agent can put a ticket on the cheap route, and `transition()` stays pure and total with no supervisor change. The cost is that `pipeline ls` prints a flag among the real counters. It is never passed to `charge()`, it is deliberately absent from `BOUNDS`, and a test asserts that absence.

Using `class` was rejected for a concrete reason. Promoting a ticket to `class: chore` overwrites whatever class it had, and the promotion back to `planning` then has no original to restore: a `feature` would return as a `bugfix` and silently lose its holistic review.

**The flag is consumed at `implementing`, not cleared on the way out.** `c.pop("cheap_route", None)` in the two `("implementing", ...)` rows makes the route one-way by construction instead of by a rule someone has to remember. A ticket bounced back by `verifying`, or promoted by a failed `quick-review`, reaches `implementing` a second time with no flag and takes the full `review`. That is the fail-safe direction: a chore whose suite went red is exactly the case that deserves the expensive look. Do not "fix" this by re-setting the flag to keep the second pass cheap.

**No Tier A gate runs on the cheap route, and that is not an oversight.** `gate()` requires `## Plan`, `## Digest`, `## Acceptance criteria` and a non-empty `files_declared`; a chore ticket has none of them, so calling it would fail on missing sections rather than on anything real. The consequence worth knowing: `_base_findings()` -- the check that catches a test which passes on base -- does not run either. `quick-review`'s first question is its only substitute, and that question is answered by reading, because a read-only stage cannot revert a diff. If a vacuous test ever lands through this route, that gap is where it came from. The fix is to run the base check dispatcher-side before `quick-review`, not to give the stage write access.

**`quick-review` is read-only on purpose.** The allowlist in `pipeline/hooks/dangerous-commands.py` has no `git stash`, no `git checkout` and no `git worktree add`, and `tree_snapshot()` escalates any tree change. Both are what stop a review stage from "just checking" by mutating the branch it is judging.

**On the cheap route `files_declared` is written by `implementing` itself.** `CLAIMS` gives that field to `planning` and `implementing`, and planning is skipped, so the union starts empty and ends as exactly the set of files the implementer touched. It cannot be used to vet that same diff, which is why `quick-review`'s second question checks the diff against the files `## Summary` and `## Reproduction` name. It also means a chore ticket does not participate in `files_conflict` ordering until `implementing` reports, so two chore tickets touching one file can run at once.

## Rollback

Revert the two commits from steps 7 and 17. Before reverting, move any ticket parked at `quick-review` with `pipeline resume <id> --stage review`: `quick-review` leaves `KNOWN_STAGES`, and `validate_meta()` then escalates that ticket as an unknown stage. A leftover `cheap_route: 1` in a ticket's `counters` is inert once the machine is reverted -- nothing reads the key -- so no ticket file needs hand-editing. Reverting step 16 alone is also safe: with the prompt files gone and the machine still routing, `tests/test_stages.py` fails immediately on the missing `pipeline/stages/quick-review.md`, which is the intended alarm rather than a silent hole.

## Thread

### 2026-08-21 08:59:52Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 · triage

Reproduced. Committed `3770816` on `ticket/026` with
`tests/test_machine.py::test_a_small_fix_takes_the_cheap_route`, which fails
with `assert 'escalated' == 'implementing'`.

What I searched, and found nothing:

1. `grep -rn "trivial\|chore"` over `*.py`, `*.md`, `*.toml` -- no `chore`
   class, no cheap route, no `quick-review`.
2. `pipeline/core/machine.py` -- `BOUNDS` holds `bugfix`, `feature`,
   `refactor` only. `transition()` has no `triage -> implementing` row.
3. `.claude/skills/file-ticket/SKILL.md:48` -- the class table a human reads
   lists the same three classes.

Two notes for planning, outside my stage:

1. `tests/test_stages.py:29` enumerates results `["ok", "fail", "blocked",
   "rejected"]` to decide which stages need a prompt file. A new `chore`
   result is not in that list, so `quick-review.md` would go unchecked. Add
   the new result value there.
2. This ticket's own `class` is `feature`, so it takes the slow path itself.
   That is correct: it edits `transition()`, which CLAUDE.md requires a human
   to review before merge.

### 2026-08-21 09:01:39Z · triage · session · session=18e58aa9-4d32-4837-bc0c-08fd01d43e83

`triage` ran as session `18e58aa9-4d32-4837-bc0c-08fd01d43e83`
- replay: `claude --resume 18e58aa9-4d32-4837-bc0c-08fd01d43e83`
- log: `.project/logs/TICKET-026-triage-18e58aa9.log`

### 2026-08-21 09:01:39Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

✓ Reproduced: transition('triage','chore') returns 'escalated'; failing test committed as 3770816

### 2026-08-21 · planning

Plan written. Sixteen steps, eight files, two commits.

Three findings the ticket did not have:

1. `("implementing", "ok")` is what routes to `quick-review`, and `transition()`
   has no memory of how the ticket reached `implementing`. The route is carried
   in `counters["cheap_route"]` -- dispatcher-owned, snapshot-restored -- and
   consumed at `implementing`, which makes the path one-way by construction.
   `class` cannot carry it: promoting to `class: chore` overwrites the original
   class, and the promotion back to `planning` has nothing to restore.
2. `("implementing", "blocked")` needed its own cheap-route row. Without it a
   blocked chore goes to `plan-validation`, whose Tier A gate fails on the
   missing `## Plan`, and lands at `planning` having burnt one of its two
   `plan_validation_attempts`.
3. `pipeline/stages/implementing.md:14` says "The plan is already researched and
   approved." A chore ticket has no plan, so that prompt gets a no-plan branch.

Triage's note about `tests/test_stages.py:29` is correct but not sufficient:
adding `chore` to the result list does not make `quick-review` reachable, since
reachability also depends on `counters`. `holistic-review` is invisible to that
test today for the same reason. Step 9 varies both.

Out of my stage, for whoever meets it later: the Tier A gate does not run at all
on the cheap route, so `_base_findings()` -- the check that catches a test which
passes on base -- does not run either. Recorded in `## Decisions`.

### 2026-08-21 09:11:34Z · planning · session · session=1f0f737a-0286-4021-879b-f616cda48f0e

`planning` ran as session `1f0f737a-0286-4021-879b-f616cda48f0e`
- replay: `claude --resume 1f0f737a-0286-4021-879b-f616cda48f0e`
- log: `.project/logs/TICKET-026-planning-1f0f737a.log`

### 2026-08-21 09:11:34Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

✓ Plan written: cheap route carried in counters[cheap_route], consumed at implementing; new quick-review stage; 16 steps, 8 files

### 2026-08-21 09:14:30Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` fails as required
```
LURES ===================================
____________________ test_a_small_fix_takes_the_cheap_route ____________________

    def test_a_small_fix_takes_the_cheap_route():
        """TICKET-025 changed one line and paid for planning, plan-validation and a
        full review. A triage that reports the fix is small must route
        `triage -> implementing -> quick-review -> verifying`, and `quick-review`
        must be able to promote the ticket back onto the slow path."""
>       assert t("triage", "chore")[0] == "implementing", \
            "a small fix still pays for planning, plan-validation and the approval gate"
E       AssertionError: a small fix still pays for planning, plan-validation and the approval gate
E       assert 'escalated' == 'implementing'
E         
E         - implementing
E         + escalated

tests/test_machine.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_small_fix_takes_the_cheap_route - Assert...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` fails on base `main` too -- the bug is not already fixed upstream
```
           "a small fix still pays for planning, plan-validation and the approval gate"
E       AssertionError: a small fix still pays for planning, plan-validation and the approval gate
E       assert 'escalated' == 'implementing'
E         
E         - implementing
E         + escalated

tests/test_machine.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_small_fix_takes_the_cheap_route - Assert...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-k8w2o5_g/base
      Built pipeline @ file:///tmp/pipeline-base-k8w2o5_g/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- plan step names no declared file: "15. Run `uv run --group dev pytest -q` over the whole suite, run `./pipeline/hooks/test_dangerous_commands.py` for the guard's 79 cases, and quote both final lines in `## Thread` -- the guard is unchanged by this ticket, so a red run there is a pre-existing break, not this diff."
- acceptance criterion names no test: - `uv run --group dev pytest -q` reports no failures for the whole suite.

### 2026-08-21 09:14:30Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- plan step names no declared file: "15. Run `uv run --group dev pytest -q` over the whole suite, run `./pipeline/hooks/test_dangerous_commands.py` for the guard's 79 cases, and quote both final lines in `## Thread` -- the guard is unchanged by this ticket, so a red run there is a pre-existing break, not this diff."
- acceptance criterion names no test: - `uv run --group dev pytest -q` reports no failures for the whole suite.

### 2026-08-21 · planning

Second planning pass. The Tier A gate failed the first plan on two mechanical
checks. Its verdict, verbatim:

- `plan step names no declared file: "15. Run ..."`
- `acceptance criterion names no test: - uv run --group dev pytest -q reports no failures for the whole suite.`

Neither finding touched the plan's content, so the route, the four `transition()`
rows, the new stage prompt and `files_declared` are unchanged. Two edits:

1. Step 15 is now two steps. Step 15 runs the suite and names
   `tests/test_machine.py` and `tests/test_stages.py`; step 16 runs the guard
   script and names `pipeline/stages/quick-review.md`, which is what declares
   `hooks: [dangerous-commands]`. The old step 16 is now step 17, and
   `## Rollback` names steps 7 and 17.
2. The whole-suite acceptance criterion now names `tests/`. A second criterion
   covers the guard script, because `pytest` collects only its two `test_*`
   functions and never its 79-case tables (CLAUDE.md).

I replayed the gate's two failing checks against the edited ticket: `_cites()`
from `pipeline/core/gate.py` over all 17 steps, and the criterion regex over
every bullet. Output: `steps: 17` / `FINDINGS: none`. The test run and the base
re-run are dispatcher-side; I did not run them.

Nothing above `## Reproduction` was rewritten beyond one appended paragraph.
`quick-review`'s second question checks the diff against the files `## Summary`
names, so editing that section would move the target the next stages are judged
against.

One content fix beyond the gate findings: an acceptance criterion named
`tests/test_harness.py::test_every_stage_has_a_file_tool`, which does not exist.
The real test is `test_every_stage_can_write_its_result_sidecar` at
`tests/test_harness.py:167`. Criterion and `## Digest` gotcha 4 now name it.

### 2026-08-21 09:30:06Z · planning · session · session=5328980b-4243-4bdd-af97-a250730dc83d

`planning` ran as session `5328980b-4243-4bdd-af97-a250730dc83d`
- replay: `claude --resume 5328980b-4243-4bdd-af97-a250730dc83d`
- log: `.project/logs/TICKET-026-planning-5328980b.log`

### 2026-08-21 09:30:06Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

✓ Fixed the two Tier A findings: step 15 split so both halves name a declared file, whole-suite criterion now names tests/; also corrected a criterion that named a nonexistent harness test

### 2026-08-21 09:30:16Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` fails as required
```
LURES ===================================
____________________ test_a_small_fix_takes_the_cheap_route ____________________

    def test_a_small_fix_takes_the_cheap_route():
        """TICKET-025 changed one line and paid for planning, plan-validation and a
        full review. A triage that reports the fix is small must route
        `triage -> implementing -> quick-review -> verifying`, and `quick-review`
        must be able to promote the ticket back onto the slow path."""
>       assert t("triage", "chore")[0] == "implementing", \
            "a small fix still pays for planning, plan-validation and the approval gate"
E       AssertionError: a small fix still pays for planning, plan-validation and the approval gate
E       assert 'escalated' == 'implementing'
E         
E         - implementing
E         + escalated

tests/test_machine.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_small_fix_takes_the_cheap_route - Assert...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` fails on base `main` too -- the bug is not already fixed upstream
```
           "a small fix still pays for planning, plan-validation and the approval gate"
E       AssertionError: a small fix still pays for planning, plan-validation and the approval gate
E       assert 'escalated' == 'implementing'
E         
E         - implementing
E         + escalated

tests/test_machine.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_small_fix_takes_the_cheap_route - Assert...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-srzum4qm/base
      Built pipeline @ file:///tmp/pipeline-base-srzum4qm/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 · plan-validation

**Verdict: pass.** Eight items, each scored against the code.

1. **Root cause.** `transition()` has one route out of `triage` on success:
   `case ("triage", "ok"): return "planning"` (`pipeline/core/machine.py:40`).
   Every ticket therefore pays `planning`, `plan-validation`, the approval gate
   and `review`, whatever its size. The plan adds a second route rather than a
   row that only satisfies the assertion: §1-§3 add the four machine rows, §5
   adds the reviewer the route needs, and §7-§8 change the two prompts without
   which `triage` cannot report `chore` and `implementing` finds no `## Plan`.
2. **Decisions.** DEC-024 is the one that constrains this plan. Quoted verbatim
   from `.project/decisions/DEC-024.md`: "The three `high` values are not
   oversights and a later cost-cutting pass must not flatten them". No existing
   `effort` value changes; `quick-review` is a new stage at `medium`. The plan
   complies rather than supersedes. DEC-017 and DEC-018 are cited as reasons the
   cheap route cannot call `gate()`, which matches `start()`: `gate()` runs only
   in the `plan-validation` branch (`pipeline/daemon/supervisor.py:544`).
3. **Scope.** Steps 1-10 trace to acceptance criteria 1-5. Steps 11-14 trace to
   the ticket's route, not to a criterion: they edit prose. Recorded as finding
   A below, not as a defect.
4. **Falsifiable criteria.** Criterion 3 is the strongest: move
   `pipeline/stages/quick-review.md` aside and
   `test_every_stage_named_by_the_state_machine_has_a_prompt` must name
   `quick-review`. It genuinely fails, because §6 computes `reachable` from
   `M.transition`, and `quick-review` stays a target of `("implementing","ok")`
   after the file leaves `C.agent_stages()`. §4's six assertions fail today on
   every one of the four new rows.
5. **No research left.** Every step names a file and a §. Line references check
   out: `pipeline/stages/implementing.md:14` is "The plan is already researched
   and approved. Execute it."; `README.md:11` is the route diagram;
   `README.md:226` is "`result: ok|fail|blocked|rejected`";
   `pipeline/stages/triage.md:34-36` is the two-entry `result:` list §7 replaces.
6. **Riskiest step: 3**, replacing the two `implementing` rows -- the only rows
   on the existing route this plan rewrites. Fallback stated: `## Rollback`
   reverts both commits and moves a parked ticket with
   `pipeline resume <id> --stage review`, a command that exists
   (`pipeline/cli/main.py:452`, `--stage` is `required=True`).
7. **Regression surface.** The full route through `implementing` is covered by
   `test_happy_path` (`t("implementing","ok")[0] == "review"`) and by
   `test_bounds_escalate_on_the_second_failure`, whose table already carries
   `("implementing", "blocked", "blocked_count")` (`tests/test_machine.py:32`);
   with empty counters `c.pop("cheap_route", None)` returns `None` and the row
   still charges. §4 pins both directions explicitly. `advance()` attributes an
   escalation to the counter that changed (`pipeline/daemon/supervisor.py:112`),
   and no new row sets `cheap_route` on a path that returns `escalated`, so the
   flag cannot be misreported as the charged counter. `validate_meta()` places
   no constraint on counter keys, so `cheap_route: 1` in a ticket file is not an
   escalation.
8. **Blast radius.** `class: feature`, 8 files, 17 steps, 2 commits, one new
   stage plus four state-machine rows. The class fits.

Finding A, non-blocking: steps 11-14 change `pipeline/stages/triage.md`,
`pipeline/stages/implementing.md`, `README.md` and
`.claude/skills/file-ticket/SKILL.md`. No test falsifies their content -- the
whole-suite criterion passes whatever those four files say. They are required
anyway: without §7 no `triage` agent knows `chore` exists, and CLAUDE.md makes
the SKILL.md update part of the change. `review` reads them.

Finding B, non-blocking and already recorded in `## Decisions`: the cheap route
runs no `_base_findings()`, so nothing re-runs the committed test on base.
`quick-review`'s first question is answered by reading `## Reproduction`, not by
running anything. That is the gap through which a vacuous test could land. The
plan states it, states why a read-only stage cannot close it, and states the fix
(run the base check dispatcher-side).

### 2026-08-21 09:35:05Z · plan-validation · session · session=6c24e911-8656-4065-9c93-1dcc7f892b05

`plan-validation` ran as session `6c24e911-8656-4065-9c93-1dcc7f892b05`
- replay: `claude --resume 6c24e911-8656-4065-9c93-1dcc7f892b05`
- log: `.project/logs/TICKET-026-plan-validation-6c24e911.log`

### 2026-08-21 09:35:05Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight judgment items; two non-blocking findings recorded in the thread (prose steps 11-14 have no falsifiable test; the cheap route runs no _base_findings())

### 2026-08-21 09:36:11Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 09:39:30Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` fails as required
```
LURES ===================================
____________________ test_a_small_fix_takes_the_cheap_route ____________________

    def test_a_small_fix_takes_the_cheap_route():
        """TICKET-025 changed one line and paid for planning, plan-validation and a
        full review. A triage that reports the fix is small must route
        `triage -> implementing -> quick-review -> verifying`, and `quick-review`
        must be able to promote the ticket back onto the slow path."""
>       assert t("triage", "chore")[0] == "implementing", \
            "a small fix still pays for planning, plan-validation and the approval gate"
E       AssertionError: a small fix still pays for planning, plan-validation and the approval gate
E       assert 'escalated' == 'implementing'
E         
E         - implementing
E         + escalated

tests/test_machine.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_small_fix_takes_the_cheap_route - Assert...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `tests/test_machine.py::test_a_small_fix_takes_the_cheap_route` fails on base `main` too -- the bug is not already fixed upstream
```
           "a small fix still pays for planning, plan-validation and the approval gate"
E       AssertionError: a small fix still pays for planning, plan-validation and the approval gate
E       assert 'escalated' == 'implementing'
E         
E         - implementing
E         + escalated

tests/test_machine.py:153: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_small_fix_takes_the_cheap_route - Assert...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-a2sunbam/base
      Built pipeline @ file:///tmp/pipeline-base-a2sunbam/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 09:39:30Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 · implementing · todo

Todo list, one entry per `## Plan` step, 1-17:

1. [x] add `"quick-review"` to `KNOWN_STAGES`
2. [x] insert the `("triage", "chore")` row
3. [x] replace the `("implementing", "ok")` / `("implementing", "blocked")` rows
4. [x] insert the two `("quick-review", ...)` rows
5. [x] append the six assertions to `test_a_small_fix_takes_the_cheap_route`
6. [x] run `tests/test_machine.py`, confirm all pass
7. [x] commit `pipeline/core/machine.py` + `tests/test_machine.py`
8. [x] create `pipeline/stages/quick-review.md`
9. [x] replace `test_every_stage_named_by_the_state_machine_has_a_prompt`
10. [x] run `tests/test_stages.py`, move the prompt aside, confirm it names `quick-review`, restore
11. [x] add `chore` to `triage.md`'s `result:` list
12. [x] add the no-plan branch to `implementing.md`
13. [x] update `README.md` diagram and result list
14. [x] update `.claude/skills/file-ticket/SKILL.md`'s human-gate sentence
15. [x] run the whole suite
16. [x] run the guard script
17. [x] commit the remaining six files

### 2026-08-21 · implementing · report

**Plan executed as written, steps 1-17. Two commits, as planned.**

Step 6 -- `uv run --group dev pytest -q tests/test_machine.py`: `14 passed in 0.04s`.

Step 7 commit `9b595bb`: `feat: a small fix takes the cheap route` -- `pipeline/core/machine.py`, `tests/test_machine.py`.

Step 10 -- `tests/test_stages.py` passed with the prompt present (`12 passed in 0.04s`); moved `pipeline/stages/quick-review.md` aside and re-ran the single test, which failed:
```
AssertionError: no prompt for `quick-review`
```
Moved the file back and re-ran; green again.

Step 15 -- `uv run --group dev pytest -q` over the whole suite: `195 passed in 8.67s`.

Step 16 -- `./pipeline/hooks/test_dangerous_commands.py`: `guard: all passed`.

Step 17 commit `98747d4`: `feat: quick-review stage for the cheap route` -- `pipeline/stages/quick-review.md` (new), `pipeline/stages/triage.md`, `pipeline/stages/implementing.md`, `tests/test_stages.py`, `README.md`, `.claude/skills/file-ticket/SKILL.md`.

No plan step was impossible and no file outside `files_declared` was touched. `## Plan`, `## Digest`, `## Decisions` and `## Rollback` are unchanged.

### 2026-08-21 09:42:16Z · implementing · session · session=4bc66dcc-adbb-4bbb-91f6-88c30eeaf740

`implementing` ran as session `4bc66dcc-adbb-4bbb-91f6-88c30eeaf740`
- replay: `claude --resume 4bc66dcc-adbb-4bbb-91f6-88c30eeaf740`
- log: `.project/logs/TICKET-026-implementing-4bc66dcc.log`

### 2026-08-21 09:42:16Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed all 17 plan steps, two commits (9b595bb, 98747d4); whole suite 195 passed, guard script all passed.

### 2026-08-21 · review · findings

**Review of the delta `4286a01..98747d4`: no blocking findings.** Two non-blocking
findings below. The diff matches `## Plan` steps 1-17 and touches exactly the eight
files `## Digest` names:

```
 .claude/skills/file-ticket/SKILL.md |  8 +++++--
 README.md                           |  8 ++++---
 pipeline/core/machine.py            | 30 +++++++++++++++++++++++++-
 pipeline/stages/implementing.md     |  8 +++++++
 pipeline/stages/quick-review.md     | 43 +++++++++++++++++++++++++++++++++++++
 pipeline/stages/triage.md           | 11 ++++++++--
 tests/test_machine.py               | 23 ++++++++++++++++++++
 tests/test_stages.py                | 12 +++++++++--
 8 files changed, 133 insertions(+), 10 deletions(-)
```

Verified against `## Acceptance criteria`:

1. `uv run --group dev pytest -q` over `tests/`: `195 passed in 8.57s`. That run
   collects `test_a_small_fix_takes_the_cheap_route`, `test_happy_path`,
   `test_bounds_escalate_on_the_second_failure`, the three `tests/test_stages.py`
   criteria and `test_harness.py::test_every_stage_can_write_its_result_sidecar`.
2. `transition()` stays pure. `c = dict(counters)` at `pipeline/core/machine.py:30`,
   and both new mutations (`c["cheap_route"] = 1`, `c.pop("cheap_route", None)`) run
   on the copy. Invariant 2 holds.
3. `quick-review` is reachable under the new test's variants, so the prompt file is
   enforced, not merely present. Computed from the shipped code:
   `needs prompt: ['holistic-review', 'implementing', 'plan-validation', 'planning', 'quick-review', 'review']`.
   Gotcha 3 is closed.
4. The dispatcher needs no change and got none. `start()` branches on
   `stage == "new"`, `"verifying"`, `"merging"`, `"revalidating"` and
   `"plan-validation"` only (`pipeline/daemon/supervisor.py:493-545`), and `finish()`
   reads `res.get("result", "fail")` (`supervisor.py:749`) against no whitelist, so
   `chore` reaches `transition()` untouched.
5. `BOUNDS` is unchanged and no `chore` class exists, as `## Summary` promised.
6. The route is one-way. The flag is consumed at both `("implementing", ...)` rows,
   and the only paths back to `implementing` are `charge("review_loops", ...)` from
   `review`, `holistic-review` and `verifying`. None of the three sets the flag.
7. `pipeline resume --reset cheap_route` sets the key to `0`
   (`pipeline/cli/main.py:169`), which `c.pop(...)` reads as falsy: the ticket then
   takes the full `review`. That is the fail-safe direction `## Decisions` asks for.
8. The flag does not corrupt an escalation reason. `advance()` computes `charged`
   from `v != t.counters.get(k, 0)` (`supervisor.py:113`) only when
   `nxt == "escalated"`, and no row both escalates and changes `cheap_route`.

Non-blocking findings:

1. **minor -- `quick-review`'s question 1 can read as always "no".** The prompt says
   to run `git diff <base>...HEAD -- <test file>`, but on the cheap route that range
   contains triage's own test commit, so the test file always appears in it. The next
   sentence -- "If the diff changed the test triage committed, that recorded failure
   no longer proves anything: answer no" -- asks the agent to tell "the commit that
   added the test" apart from "a later edit to it". A literal reading fails every
   chore to `planning`, and the cheap route never lands. A range anchored on triage's
   commit removes the ambiguity: `git log --format=%H --diff-filter=A -- <test file>`,
   then `git diff <that sha>..HEAD -- <test file>`. The wording is verbatim from
   `## Digest` §5, which the approval gate passed, so this is a follow-up, not drift.
2. **minor -- the README diagram's cheap-route arrow does not connect.** Line 15 ends
   `quick-review --+` at column 51; the `|` it joins on line 14 sits at column 31,
   under `verifying`. A reader gets the route from the labels, not from the rules.
   Verbatim from `## Digest` §9.

Not verified by me: `./pipeline/hooks/test_dangerous_commands.py`. The guard refused
it -- "`test_dangerous_commands.py` is not on the read-only allowlist" -- so
`implementing`'s `guard: all passed` stands unreproduced. The diffstat above shows the
delta touches no file under `pipeline/hooks/`.

### 2026-08-21 09:46:15Z · review · session · session=79fbbf4f-1736-484b-9a76-f6eab4e387f7

`review` ran as session `79fbbf4f-1736-484b-9a76-f6eab4e387f7`
- replay: `claude --resume 79fbbf4f-1736-484b-9a76-f6eab4e387f7`
- log: `.project/logs/TICKET-026-review-79fbbf4f.log`

### 2026-08-21 09:46:15Z · review · transition · to=holistic-review · result=ok · marker=yes

**review -> holistic-review** (result: `ok`)

✓ Delta 4286a01..98747d4 matches the plan and the acceptance criteria; 195 passed in 8.57s; two minor findings, none blocking

### 2026-08-21 · holistic-review · findings

**The accumulated change is coherent.** The ticket is three commits -- `4286a01`
(triage's failing test), `9b595bb`, `98747d4` -- with no fixup commit, so no
later change undoes an earlier one.

1. The sum matches `## Plan` steps 1-17 and touches exactly the eight files
   `## Digest` names. `git diff 4286a01..98747d4 --stat`:
```
 .claude/skills/file-ticket/SKILL.md |  8 +++++--
 README.md                           |  8 ++++---
 pipeline/core/machine.py            | 30 +++++++++++++++++++++++++-
 pipeline/stages/implementing.md     |  8 +++++++
 pipeline/stages/quick-review.md     | 43 +++++++++++++++++++++++++++++++++++++
 pipeline/stages/triage.md           | 11 ++++++++--
 tests/test_machine.py               | 10 +++++++++
 tests/test_stages.py                | 12 +++++++++--
 8 files changed, 120 insertions(+), 10 deletions(-)
```
2. The route is closed end to end, and one-way. `("triage", "chore")` sets
   `cheap_route`, both `("implementing", ...)` rows consume it,
   `("quick-review", "ok")` goes to `verifying`, `("quick-review", "fail")` to
   `planning`. `("verifying", "fail")` charges back to `implementing` with no
   flag, so a bounced chore takes the full `review`. That is what `## Decisions`
   says the route does.
3. No unbounded loop entered the machine. `("quick-review", "fail")` charges no
   counter and needs none: the flag was consumed at `implementing`, so the
   ticket cannot re-enter `quick-review`. Invariant 3 holds.
4. Nothing enumerates stages or result values outside `machine.py`, so no second
   list drifted. Grepped `pipeline/` `*.py` and `*.toml` for `rejected`,
   `"review"` and `holistic`: the only hits are a comment
   (`hooks/dangerous-commands.py:45`), a metrics label (`cli/metrics.py:420`)
   and the approval gate's own record (`cli/main.py:145`).
5. Nothing landed that no acceptance criterion asked for. Every hunk maps to a
   plan step; the two prose files carry `## Digest` §9 and §10 and no more.
6. Error handling did not drift between the two commits. The one new failure
   path (`quick-review` -> `planning`) states its verdict values in the prompt
   like every other stage and follows `_common.md`'s failure protocol.

Re-ran the whole suite from the worktree, `uv run --group dev pytest -q`:
`195 passed in 8.48s`.

One number to correct in the thread, not in the code: `review`'s diffstat above
records `tests/test_machine.py | 23 ++` and `133 insertions(+)`. The delta it
names has `10` and `120`, as quoted in item 1. The file list is right; only the
two counts are wrong.

Not re-litigated: `review`'s two minor findings (question 1's `<base>...HEAD`
range, the README arrow column). Both are line-level and the incremental review
already ruled on them.

### 2026-08-21 09:48:25Z · holistic-review · session · session=4d5c4c0c-0cc1-4ee1-9593-caa2a7ffc043

`holistic-review` ran as session `4d5c4c0c-0cc1-4ee1-9593-caa2a7ffc043`
- replay: `claude --resume 4d5c4c0c-0cc1-4ee1-9593-caa2a7ffc043`
- log: `.project/logs/TICKET-026-holistic-review-4d5c4c0c.log`

### 2026-08-21 09:48:25Z · holistic-review · transition · to=verifying · result=ok · marker=yes

**holistic-review -> verifying** (result: `ok`)

✓ Coherent: 8 files, plan steps 1-17, route closed and one-way, no unasked change; 195 passed in 8.48s

### 2026-08-21 09:48:35Z · verifying · transition · to=merging · result=ok

**verifying -> merging** (result: `ok`)

regression suite exit 0
```
...HEAD
ok  allow [always] cargo build --release
ok  BLOCK [readonly] sed -i s/a/b/ x.py
ok  BLOCK [readonly] echo hi > file.txt
ok  BLOCK [readonly] git commit -am wip
ok  BLOCK [readonly] cp a b
ok  BLOCK [readonly] pip install requests
ok  BLOCK [readonly] mv a b
ok  BLOCK [readonly] python3 -c "open('/tmp/x','a').write(1)"
ok  BLOCK [readonly] git -C . commit -am wip
ok  BLOCK [readonly] pytest 2>out
ok  BLOCK [readonly] pytest >> log.txt
ok  BLOCK [readonly] git worktree add /tmp/x main
ok  BLOCK [readonly] python3 setup.py install
ok  BLOCK [readonly] tee /tmp/x
ok  BLOCK [readonly] curl https://example.com -o /tmp/x
ok  BLOCK [readonly] make install
ok  BLOCK [readonly] cargo run
ok  BLOCK [readonly] npm install
ok  BLOCK [readonly] echo $(whoami)
ok  allow [readonly] pytest -x
ok  allow [readonly] git diff main...HEAD
ok  allow [readonly] grep -rn foo .
ok  allow [readonly] git log --oneline
ok  allow [readonly] cat thing.py
ok  allow [readonly] python3 -m pytest --deselect x
ok  allow [readonly] ls -la
ok  allow [readonly] git show HEAD
ok  allow [readonly] git blame thing.py
ok  allow [readonly] rg evict src/
ok  allow [readonly] pytest -x 2>&1
ok  allow [readonly] find . -name '*.py'
ok  allow [readonly] cargo test
ok  allow [readonly] go test ./...
ok  allow [readonly] git status --porcelain
ok  allow [readonly] wc -l thing.py
ok  allow [readonly] python3 -m unittest
ok  allow [readonly] git diff main...HEAD | head -50
ok  end-to-end exit codes

guard: all passed

```

### 2026-08-21 09:48:36Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/026


Merge made by the 'ort' strategy.
 pipeline/core/gate.py | 20 ++++++++++++++++----
 tests/test_gate.py    | 18 ++++++++++++++++++
 2 files changed, 34 insertions(+), 4 deletions(-)
Updating 3f87848..5cb7d26
Fast-forward
 .claude/skills/file-ticket/SKILL.md |  8 +++++--
 README.md                           |  8 ++++---
 pipeline/core/machine.py            | 30 +++++++++++++++++++++++++-
 pipeline/stages/implementing.md     |  8 +++++++
 pipeline/stages/quick-review.md     | 43 +++++++++++++++++++++++++++++++++++++
 pipeline/stages/triage.md           | 11 ++++++++--
 tests/test_machine.py               | 23 ++++++++++++++++++++
 tests/test_stages.py                | 12 +++++++++--
 8 files changed, 133 insertions(+), 10 deletions(-)
 create mode 100644 pipeline/stages/quick-review.md

```

### 2026-08-21 09:48:36Z · merging · decision

decision recorded as `DEC-026`
