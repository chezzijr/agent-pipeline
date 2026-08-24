---
id: TICKET-051
stage: done
class: feature
branch: ticket/051
test_file: tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one
files_declared:
- README.md
- pipeline/cli/main.py
- tests/test_cli.py
counters:
  plan_validation_attempts: 0
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
  rebase_conflicts: 1
  plan_steps: 14
  plan_files: 3
lease:
  holder: null
  expires: null
last_session:
  stage: holistic-review
  id: bdd029e8-1854-4b64-a07d-2562cd2f0e1d
  log: .project/logs/TICKET-051-holistic-review-bdd029e8.log
approved_by: chezzijr
approved_at: '2026-08-24T10:16:07.456183+00:00'
---

## Summary
Implemented, reviewed twice, and holistic-reviewed. Neither the second review
nor the holistic review found anything blocking. The whole diff
`4708538..04e93b6` is coherent with `## Plan`: no commit undid an earlier one,
`die` is the single refusal path across the touched files, and nothing landed
that no criterion asked for. All seven acceptance criteria hold;
`uv run --group dev pytest -q tests/test_cli.py tests/test_machine.py
tests/test_dispatch.py` -> `77 passed in 6.21s`.

`pipeline resume` now accepts `--grant <counter>[=<n>]`, which subtracts `n`
(default 1) from a counter in `cmd_resume` (`pipeline/cli/main.py`). `--reset`
is unchanged: it still zeroes. A grant is refused, not clamped, when `n`
exceeds what the counter holds, when the counter does not exist, or when one
counter appears in both `--grant` and `--reset`. The thread note carries
`by=<user>` and, on a grant, a `` `key` before -> after `` clause.

The first review's one blocking finding is fixed and verified: `cmd_resume`
sums `n` per key into `grants: dict[str, int]` (`pipeline/cli/main.py:200-202`)
before validating or mutating, so `--grant plan_validation_attempts
plan_validation_attempts` on a counter of 1 is refused with `cannot grant 2`
instead of landing at `-1`. No counter can reach a negative value.

Three nits stand open, none blocking: `str.isdigit()` accepts `²`, a
hand-edited string counter raises `TypeError`, and a second `--grant`
occurrence overwrites the first (`nargs="*"`, same shape as `--reset`).

Three commits: `9e94e9d`, `77bb4cf`, `04e93b6`.

Reproduction test `test_resume_reset_only_zeroes_it_cannot_grant_back_one`
kept its name (`CLAIMS` gives `test_file` to `triage` alone); its body now
asserts the `--grant`/`--reset` contract.

## Reproduction

Test: `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one`

Command: `uv run --group dev pytest -q tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one`

Sets `plan_validation_attempts` to 2, runs `pipeline resume ... --reset
plan_validation_attempts`, then asserts the counter is 1 (one attempt handed
back). It is 0 instead: `--reset` only zeroes.

```
AssertionError: expected --reset to hand back exactly one wasted attempt (2 -> 1), got 0 (--reset always zeroes the counter)
assert 0 == 1
```

expect: got 0 (--reset always zeroes the counter)

## Digest
- Files touched: `pipeline/cli/main.py` (`cmd_resume`, lines 178-190; its `resume` subparser, line 490), `tests/test_cli.py` (the reproduction test, lines 39-57), `README.md` (lines 70-71 document `--reset`).
- Line numbers here were re-read on the recut branch at `761ceb5`. The earlier plan cited `main.py:177` and `main.py:467`; both moved when the branch was recut from `8b1a245`. The design is unchanged.
- `cmd_resume` today does five things: set `t.stage`, zero each `--reset` key, `t.release_lease()`, append one `human`/`note` entry, `t.save()`. It calls no `record()`, so `resume` emits no store event. This plan does not add one.
- `Ticket.append(stage, kind, text, **attrs)` (`pipeline/core/ticket.py:571`) renders the header `<ts> · <stage> · <kind> · k=v`. `cmd_approve` (`pipeline/cli/main.py:133`) is the precedent for `by=`.
- Bounds live in `pipeline/core/machine.py:6-11`. Class `feature` bounds `plan_validation_attempts` at 2. A decrement-only `--grant` never needs to read them.
- Gotcha: the reproduction test demands `--reset` return 1. This plan keeps `--reset` zeroing, so the test's body changes. Its **name must not change**: `CLAIMS` (`pipeline/core/machine.py:180`) gives `test_file` to `triage` only, so `implementing` cannot repoint the frontmatter at a new node.
- Gotcha: `gate()` runs at `plan-validation` and `revalidating` only (`pipeline/daemon/supervisor.py:657,785`), both before `implementing`. Rewriting the test body at `implementing` never faces the `expect:` string again.
- Gotcha: `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` (line 73) reads `README.md` and matches two lines: one containing `myproject run  ` and one starting `pipeline start `. The `resume --grant` lines step 13 adds match neither, so that test stays green.
- `pipeline/cli/main.py` is absent from `machine.FENCED`, so this diff merges unattended.
- `.claude/skills/file-ticket/SKILL.md` documents `ls`, `answer`, `reject` and `approve`, never `resume`; no skill change is due.
- Leave `cmd_reject`'s die message alone: it names `--reset plan_rejections` and `tests/test_cli.py:122` asserts that exact string.

## Decisions checked
Grepped `.project/decisions/` for `counter`, `--reset`, `resume`, `bound`, `BOUNDS`, `CONTROL_FIELDS`. Nine records matched: DEC-011, DEC-017, DEC-022, DEC-023, DEC-026, DEC-029, DEC-031, DEC-045, DEC-049. No record in that directory carries a `superseded-by:` line, so every one cited below is active.

- **DEC-026 constrains this change.** `counters["cheap_route"]` is a route flag living in `counters`, never charged and deliberately absent from `BOUNDS`. `--grant cheap_route` would clear that flag exactly as `--reset cheap_route` already does. The plan neither widens nor special-cases this.
- **DEC-031 constrains it weakly.** `pipeline/core/machine.py` is fenced by symbol (`transition`, `CONTROL_FIELDS`, `FENCED`). This plan touches none of them and imports no new symbol from that module.
- **DEC-049 constrains steps 5 and 13.** It rules that a help string asserting a behaviour is bound by a test. The `--grant` help text says "a grant only subtracts", and criterion 3's test holds it. DEC-049 also binds `README.md` to the `start`/`run` help strings; step 13 adds `resume` lines, which that test does not read. DEC-049 landed in base after the earlier plan was written.
- DEC-011, DEC-017, DEC-022, DEC-023, DEC-029 and DEC-045 matched the grep terms but bind the store schema, the Tier A gate, the `✓` marker, `stage_view()`, the rebase-conflict repair and the `merging` rebase. None constrains `resume`.

No record covers the flag spelling or the clamp. `## Decisions` below records both choices.

## Plan
1. In `tests/test_cli.py`, rewrite the body of `test_resume_reset_only_zeroes_it_cannot_grant_back_one` (lines 39-57) and keep its name: set `plan_validation_attempts` to 2 via `Ticket.load`/`save`, run `cli(d, "resume", "TICKET-001", "--stage", "planning", "--grant", "plan_validation_attempts")`, assert the counter is 1; then run `cli(d, "resume", "TICKET-001", "--stage", "planning", "--reset", "plan_validation_attempts")` and assert it is 0; then assert the ticket body contains ``granted `plan_validation_attempts` 2 -> 1`` and a `by=` carrying `os.environ.get("USER", "human")`. Its docstring states the contract: `--grant` hands back exactly what was spent, `--reset` still zeroes.
2. Run `uv run --group dev pytest -q tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one` and watch it fail on the first assert: argparse rejects the unknown flag (`error: unrecognized arguments: --grant plan_validation_attempts`, exit 2), the counter stays 2, so pytest prints `assert 2 == 1`.
3. In `pipeline/cli/main.py`, add `parse_grant` directly above `cmd_resume` (line 178): `def parse_grant(spec: str) -> tuple[str, int]:`, docstring "`<counter>` or `<counter>=<n>`: which counter, and how many spent attempts to hand back. Bare means one."; body `key, eq, raw = spec.partition("=")`, then `if not key or (eq and not (raw.isdigit() and int(raw) >= 1)): die(f"`--grant {spec}`: want `<counter>` or `<counter>=<n>` with n >= 1")`, then `return key, int(raw) if eq else 1`.
4. In `pipeline/cli/main.py`, extend `cmd_resume` (lines 178-190): after `t = Ticket.find(project, args.id)` add `granted = []` and `for key, n in [parse_grant(s) for s in args.grant or []]:` whose body is `have = t.counters.get(key, 0)`, `t.counters[key] = have - n`, ``granted.append(f"`{key}` {have} -> {have - n}")``; replace the note with `who = os.environ.get("USER", "human")`, ``note = f"**resumed** by {who} -> `{args.stage}`, reset {args.reset or []}"``, `if granted: note += f", granted {', '.join(granted)}"`, `t.append("human", "note", note, by=who)`; end with `print(f"{args.id}: -> {args.stage}" + (f" ({', '.join(granted)})" if granted else ""))`.
5. In `pipeline/cli/main.py` line 490, add `p.add_argument("--grant", nargs="*", metavar="COUNTER[=N]", help="hand back N spent attempts (default 1) on a counter; a grant only subtracts")` to the one-line `resume` subparser, between its existing `--stage` and `--reset` arguments.
6. Run `uv run --group dev pytest -q tests/test_cli.py`, expect every test in the file to pass, then commit `pipeline/cli/main.py` and `tests/test_cli.py` as `fix(TICKET-051): resume --grant hands back n spent attempts instead of zeroing`.
7. In `tests/test_cli.py`, add `test_resume_grant_refuses_to_hand_back_more_than_was_spent`: set `plan_validation_attempts` to 2, run `cli(d, "resume", "TICKET-001", "--stage", "planning", "--grant", "plan_validation_attempts=3")`, assert `r.returncode != 0`, assert `"cannot grant 3" in r.stderr`, and assert the counter on disk is still 2.
8. In `tests/test_cli.py`, add `test_resume_grant_refuses_a_counter_the_ticket_does_not_have`: run `cli(d, "resume", "TICKET-001", "--stage", "planning", "--grant", "plan_validaton_attempts")` (that typo, spelled exactly so), assert `r.returncode != 0`, assert `"has no counter" in r.stderr`, and assert `"plan_validaton_attempts" not in t.counters` after reloading the ticket.
9. In `tests/test_cli.py`, add `test_resume_refuses_reset_and_grant_on_one_counter`: set `plan_validation_attempts` to 2 with the ticket at stage `planning`, run `cli(d, "resume", "TICKET-001", "--stage", "triage", "--reset", "plan_validation_attempts", "--grant", "plan_validation_attempts")`, assert `r.returncode != 0`, assert `"pick one" in r.stderr`, and assert the counter is still 2 and the stage is still `planning`.
10. Run `uv run --group dev pytest -q tests/test_cli.py -k "grant"` and watch the three new tests fail: with only step 4 in place `--grant plan_validation_attempts=3` exits 0 and writes `-1`, the typo'd key is created at `-1`, and the reset/grant pair exits 0.
11. In `pipeline/cli/main.py`, add three refusals to `cmd_resume` before the mutation loop of step 4: `grants = [parse_grant(s) for s in args.grant or []]`; `clash = {k for k, _ in grants} & set(args.reset or [])`; ``if clash: die(f"`--reset` and `--grant` both name {', '.join(sorted(clash))}: pick one")``; then a validation loop over `grants` with `have = t.counters.get(key)`, ``if have is None: die(f"{t.id} has no counter `{key}` (it has: {', '.join(sorted(t.counters)) or 'none'})")`` and ``if n > have: die(f"{t.id}: cannot grant {n} back to `{key}`, which is {have} -- a grant only returns attempts already spent; `--reset {key}` zeroes it if that is what you want")``; the mutation loop then iterates `grants` and reads `t.counters[key]` instead of `.get(key, 0)`.
12. Run `uv run --group dev pytest -q tests/test_cli.py` and expect every test in the file to pass, including the four named in `## Acceptance criteria`.
13. In `README.md`, insert two lines after line 71 (`    --stage planning --reset plan_validation_attempts`), inside the fenced block that closes on line 72: `pipeline --project ~/code/myproject resume  TICKET-001 \` on the first, then `    --stage planning --grant plan_validation_attempts   # hand back one spent attempt, not the whole budget` on the second.
14. Run `uv run --group dev pytest -q tests/test_cli.py tests/test_machine.py tests/test_dispatch.py`, expect no failures, then commit `pipeline/cli/main.py`, `tests/test_cli.py` and `README.md` as `fix(TICKET-051): refuse an over-grant rather than clamping it to zero`.

## Acceptance criteria
1. `pipeline resume <id> --stage planning --grant plan_validation_attempts` takes a counter of 2 to 1, and `--reset` on the same counter still takes it to 0 -- `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one`.
2. The thread records the grant and the user: the ticket body contains ``granted `plan_validation_attempts` 2 -> 1`` and the entry header carries `by=<user>` -- same test.
3. `--grant plan_validation_attempts=3` on a counter of 2 exits non-zero, prints `cannot grant 3`, and leaves the counter at 2 -- `tests/test_cli.py::test_resume_grant_refuses_to_hand_back_more_than_was_spent`. No counter reaches a negative value, and because a grant only subtracts, none can exceed its `BOUNDS` entry.
4. `--grant` naming a counter the ticket does not carry exits non-zero, prints `has no counter`, and creates no key -- `tests/test_cli.py::test_resume_grant_refuses_a_counter_the_ticket_does_not_have`.
5. `--reset X --grant X` in one command exits non-zero, prints `pick one`, and changes neither the counter nor the stage -- `tests/test_cli.py::test_resume_refuses_reset_and_grant_on_one_counter`.
6. The `README.md` lines step 13 adds leave the README assertions green -- `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` still passes.
7. `uv run --group dev pytest -q tests/test_cli.py tests/test_machine.py tests/test_dispatch.py` reports no failures.

## Decisions
**`--grant <counter>[=<n>]` subtracts; `--reset` keeps its one meaning.** The rejected spelling was `--reset <counter>=<n>`, which sets a counter to an arbitrary value: it can *raise* one (0 -> 5), so it would have to read `BOUNDS[klass][counter]` and the ticket's class inside the CLI to clamp, and it would overload `--reset` -- a word that means "zero" in `README.md`, in `cmd_reject`'s refusal message and in every thread note written so far. A decrement-only flag cannot exceed a bound at all, which is why no `BOUNDS` lookup exists in `pipeline/cli/main.py`. If a future change lets `--grant` add attempts, that clamp becomes mandatory, and invariant 3 (`CLAUDE.md`: every bounded loop escalates at its class bound) is what it must answer to.

**An over-grant is refused, never clamped to 0.** `--grant plan_validation_attempts=3` on a counter of 2 exits non-zero instead of quietly yielding 0. Clamping would hand back the whole budget to a human who asked for three -- the exact over-grant this ticket exists to remove. `--reset` remains the explicit way to zero, and the refusal message says so.

**The test name `test_resume_reset_only_zeroes_it_cannot_grant_back_one` stays, though its body now drives `--grant`.** `CLAIMS` (`pipeline/core/machine.py:180`) gives `test_file` to `triage` alone, so `implementing` cannot repoint the frontmatter at a renamed node; a rename needs another `triage` pass or a `CLAIMS` change. The name still reads true: `--reset` only zeroes, by design.

**`resume` still emits no event to the store.** `cmd_resume` does not call `record()`, so a grant appears in the ticket thread and nowhere in `events.db`. That gap predates this ticket and is left alone: metrics view 6 measures human-gate spans, and `resume` is not one.

## Rollback
Revert the whole ticket branch, not one commit. Reverting the `pipeline/cli/main.py` commits alone would leave `tests/test_cli.py` driving a `--grant` flag that no longer exists, and its four tests would fail. Reverting everything restores `--reset` as the only operation and returns the reproduction test to its original failing form, which is the pre-ticket state. Nothing else reads `--grant`: no stage prompt, no dispatcher path and no store event depends on it.

## Thread

### 2026-08-24 08:05:50Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 · triage · triage · result=ok

Reproduced. Wrote `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one`.
It sets `plan_validation_attempts` to 2, runs `pipeline resume ... --reset
plan_validation_attempts`, and asserts the counter comes back as 1. It is 0:
`--reset` in `pipeline/cli/main.py:183` unconditionally zeroes the counter,
confirming the ticket's claim exactly.

Verdict: `ok`, not `chore`. The fix needs a design decision this stage must
not make: the flag's spelling (`--grant <counter>` vs `--reset
<counter>=<n>`) and how to clamp the result to `[0, bound]`. Both are named
as open in the ticket's "Expected" section. Send to planning.

Committed on `ticket/051` as `b73b450`.

### 2026-08-24 09:01:09Z · triage · session · session=63e6332e-faad-49be-ad25-05afe4a8ff63

`triage` ran as session `63e6332e-faad-49be-ad25-05afe4a8ff63`
- replay: `claude --resume 63e6332e-faad-49be-ad25-05afe4a8ff63`
- log: `.project/logs/TICKET-051-triage-63e6332e.log`

### 2026-08-24 09:01:09Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- `--reset` always zeroes the counter, failing test committed at b73b450

### 2026-08-24 · planning · note

Plan written. I settled the design question triage parked rather than asking
it: `--grant <counter>[=<n>]` subtracts, `--reset` keeps meaning "zero". The
reasons and the rejected `--reset <counter>=<n>` spelling are in
`## Decisions`. The code answered the clamping half -- a flag that only
subtracts can never exceed `BOUNDS`, so the CLI needs no bound lookup.

One thing the implementer must not treat as a mistake: the plan does **not**
make the reproduction test pass as written. `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one`
asserts `--reset` returns a counter of 2 to 1, and this plan keeps `--reset`
zeroing. Step 1 rewrites that test's body to drive `--grant` and keeps its
name, because `CLAIMS` (`pipeline/core/machine.py:180`) gives `test_file` to
`triage` alone -- `implementing` cannot repoint the frontmatter at a renamed
node. `gate()` runs only at `plan-validation` and `revalidating`, both before
`implementing`, so the rewrite never faces the `expect:` string again.

Scope is one subsystem: `cmd_resume` and its flags. `transition()`,
`CONTROL_FIELDS` and `BOUNDS` are untouched, so nothing in this diff is
fenced and the ticket can merge unattended.

Verified the reproduction still fails on this branch: `assert 0 == 1`.

### 2026-08-24 09:07:48Z · planning · session · session=b342f525-684b-41d8-92f5-c29b4145e2dc

`planning` ran as session `b342f525-684b-41d8-92f5-c29b4145e2dc`
- replay: `claude --resume b342f525-684b-41d8-92f5-c29b4145e2dc`
- log: `.project/logs/TICKET-051-planning-b342f525.log`

### 2026-08-24 09:07:48Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned --grant <counter>[=<n>] on `pipeline resume`: subtract-only, refuses an over-grant, 14 steps

### 2026-08-24 09:48:44Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one` fails as required
```
.mkdtemp())
        cli(d, "new", "t")
        cli(d, "resume", "TICKET-001", "--stage", "planning")
        t = Ticket.load(d / ".project/tickets/TICKET-001.md")
        t.counters["plan_validation_attempts"] = 2
        t.save()
    
        cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--reset", "plan_validation_attempts")
    
        t = Ticket.load(d / ".project/tickets/TICKET-001.md")
>       assert t.counters["plan_validation_attempts"] == 1, (
            f"expected --reset to hand back exactly one wasted attempt "
            f"(2 -> 1), got {t.counters['plan_validation_attempts']} "
            f"(--reset always zeroes the counter)"
        )
E       AssertionError: expected --reset to hand back exactly one wasted attempt (2 -> 1), got 0 (--reset always zeroes the counter)
E       assert 0 == 1

tests/test_cli.py:54: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.22s ===============================

```
- ok: `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one` fails on base `main` too -- the bug is not already fixed upstream
```
tempt "
            f"(2 -> 1), got {t.counters['plan_validation_attempts']} "
            f"(--reset always zeroes the counter)"
        )
E       AssertionError: expected --reset to hand back exactly one wasted attempt (2 -> 1), got 0 (--reset always zeroes the counter)
E       assert 0 == 1

tests/test_cli.py:54: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.33s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-upkcb8y9/base
      Built pipeline @ file:///tmp/pipeline-base-upkcb8y9/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 · plan-validation · finding · verdict=pass

Plan passes all eight judgment items.

- **Root cause.** `cmd_resume` (`pipeline/cli/main.py:183-184`) runs
  `t.counters[key] = 0` for every `--reset` key. The CLI carries no decrement,
  so a human correcting one wasted attempt must zero the counter. The plan adds
  the missing operation; it does not bend `--reset` to pass a test.
- **Decisions.** DEC-026 holds: `--grant cheap_route` only subtracts, so it
  clears the route flag exactly as `--reset` already can, and cannot set it.
  DEC-031 holds: no symbol in `pipeline/core/machine.py` is touched.
- **Criteria falsifiable.** Each of 1-5 names a counter value, an exit code and
  a literal string (`cannot grant 3`, `has no counter`, `pick one`). The step-11
  messages contain those strings.
- **Riskiest step: 1**, rewriting the reproduction test body under its old
  name. `CLAIMS` (`machine.py:180`) and `gate()` (`supervisor.py:637,765`) are
  as the Digest states. Fallback: `## Rollback` reverts the branch.
- **Regression.** The note string changes from `by human` to `by $USER`; no
  test asserts the old one. `--reset` behaviour is unchanged and covered by
  `tests/test_cli.py:84,98,106`.
- **Blast radius.** 3 files, one new function, one flag. Fits `class: feature`.

Two findings, neither blocking:

1. Step 13 (`README.md`) traces to no acceptance criterion. Accepted:
   `README.md:70-71` is the only prose documenting `--reset`.
   `.claude/skills/file-ticket/SKILL.md` never names `resume`, so no skill
   change is due.
2. `## Reproduction` will describe a test body step 1 deletes. A human who
   resumes this ticket to `planning` after `implementing` re-runs `gate()`
   against a test that now passes, and the gate fails. Off this ticket's path:
   `plan-validation` and `revalidating` both precede `implementing`.

### 2026-08-24 09:51:37Z · plan-validation · session · session=270804f5-107b-42d3-89f4-15bb006ab986

`plan-validation` ran as session `270804f5-107b-42d3-89f4-15bb006ab986`
- replay: `claude --resume 270804f5-107b-42d3-89f4-15bb006ab986`
- log: `.project/logs/TICKET-051-plan-validation-270804f5.log`

### 2026-08-24 09:51:37Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan validated: root cause is cmd_resume zeroing counters, criteria are falsifiable, DEC-026/031 hold, 3 files fits class feature; two non-blocking findings recorded

### 2026-08-24 09:52:13Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 09:57:26Z · revalidating · transition · to=triage · result=conflict

**revalidating -> triage** (result: `conflict`)

rebase onto base conflicted; branch recut from base:
```
$ git rebase main

Rebasing (1/1)
Auto-merging tests/test_cli.py
CONFLICT (content): Merge conflict in tests/test_cli.py
error: could not apply b73b450... test(TICKET-051): reproduce --reset zeroing when a human wants to grant one attempt back
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply b73b450... # test(TICKET-051): reproduce --reset zeroing when a human wants to grant one attempt back

b73b450 test(TICKET-051): reproduce --reset zeroing when a human wants to grant one attempt back
HEAD is now at 8b1a245 chore(TICKET-049): record the finished ticket

```

### 2026-08-24 · triage · triage · result=ok

**Re-triage after rebase recut.**

The `revalidating -> triage` conflict recut the branch from base
(`8b1a245`), which dropped commit `b73b450` -- the reproduction test -- along
with it. `tests/test_cli.py` on the recut branch had no
`test_resume_reset_only_zeroes_it_cannot_grant_back_one`.

Rewrote the test body verbatim from `## Reproduction` and recommitted it as
`761ceb5 test(TICKET-051): reproduce --reset zeroing when a human wants to
grant one attempt back`.

```
$ uv run --group dev pytest -q tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one
AssertionError: expected --reset to hand back exactly one wasted attempt (2 -> 1), got 0 (--reset always zeroes the counter)
assert 0 == 1
```

expect: got 0 (--reset always zeroes the counter)

The plan, decisions and acceptance criteria above are unaffected: nothing in
them referenced the dropped commit's sha, only the test's name, which is
unchanged.

### 2026-08-24 09:58:10Z · triage · session · session=286c6e55-5e7d-4cd3-a0a4-38408f95bf54

`triage` ran as session `286c6e55-5e7d-4cd3-a0a4-38408f95bf54`
- replay: `claude --resume 286c6e55-5e7d-4cd3-a0a4-38408f95bf54`
- log: `.project/logs/TICKET-051-triage-286c6e55.log`

### 2026-08-24 09:58:10Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ recut branch had dropped the reproduction test in the rebase conflict; rewrote it verbatim and recommitted (761ceb5), confirms same failure

### 2026-08-24 · planning · note

Replanned on the recut branch. The design is unchanged: `--grant` subtracts,
`--reset` still zeroes. Two things changed.

1. Line numbers. The recut from `8b1a245` moved every reference the validated
   plan carried: `cmd_resume` `pipeline/cli/main.py:177` -> `178-190`, the
   `resume` subparser `467` -> `490`, `gate()`
   `pipeline/daemon/supervisor.py:637,765` -> `657,785`, the reproduction test
   `tests/test_cli.py:39-58` -> `39-57`, and `cmd_reject`'s asserted string
   `tests/test_cli.py:98` -> `122`. Steps 3, 4, 5 and 13 name the new numbers.
2. DEC-049 landed in base with the recut and now applies: a help string that
   asserts a behaviour is bound by a test. It also binds `README.md` to the
   `start`/`run` help strings via
   `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes`, which
   matches one README line containing `myproject run  ` and one starting
   `pipeline start `. Step 13's `resume` lines match neither. That is now
   acceptance criterion 6, which closes the plan-validation finding that step
   13 traced to no criterion.

Verified the reproduction still fails on `761ceb5`:

```
AssertionError: expected --reset to hand back exactly one wasted attempt (2 -> 1), got 0 (--reset always zeroes the counter)
assert 0 == 1
```

The other plan-validation finding stands: `## Reproduction` describes a test
body step 1 deletes. Off this ticket's path, as recorded there.

### 2026-08-24 10:03:00Z · planning · session · session=a0cb09a9-6d4f-420c-9a2b-508b3b1df15e

`planning` ran as session `a0cb09a9-6d4f-420c-9a2b-508b3b1df15e`
- replay: `claude --resume a0cb09a9-6d4f-420c-9a2b-508b3b1df15e`
- log: `.project/logs/TICKET-051-planning-a0cb09a9.log`

### 2026-08-24 10:03:00Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned on the recut branch: same --grant design, every line reference refreshed against 761ceb5, DEC-049 cited, README criterion added

### 2026-08-24 10:11:34Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one` fails as required
```
.mkdtemp())
        cli(d, "new", "t")
        cli(d, "resume", "TICKET-001", "--stage", "planning")
        t = Ticket.load(d / ".project/tickets/TICKET-001.md")
        t.counters["plan_validation_attempts"] = 2
        t.save()
    
        cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--reset", "plan_validation_attempts")
    
        t = Ticket.load(d / ".project/tickets/TICKET-001.md")
>       assert t.counters["plan_validation_attempts"] == 1, (
            f"expected --reset to hand back exactly one wasted attempt "
            f"(2 -> 1), got {t.counters['plan_validation_attempts']} "
            f"(--reset always zeroes the counter)"
        )
E       AssertionError: expected --reset to hand back exactly one wasted attempt (2 -> 1), got 0 (--reset always zeroes the counter)
E       assert 0 == 1

tests/test_cli.py:53: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.24s ===============================

```
- ok: `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one` fails on base `main` too -- the bug is not already fixed upstream
```
tempt "
            f"(2 -> 1), got {t.counters['plan_validation_attempts']} "
            f"(--reset always zeroes the counter)"
        )
E       AssertionError: expected --reset to hand back exactly one wasted attempt (2 -> 1), got 0 (--reset always zeroes the counter)
E       assert 0 == 1

tests/test_cli.py:53: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.34s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yw3r84tk/base
      Built pipeline @ file:///tmp/pipeline-base-yw3r84tk/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 · plan-validation · note

**Judgment review: PASS on all eight items.** Every claim below was read off
the worktree at `761ceb5`.

long: eight scored items plus two residuals, each carrying its evidence.

1. **Root cause.** `cmd_resume` offers one counter operation, `t.counters[key] = 0`
   (`pipeline/cli/main.py:184-185`). A human who wants back the one wasted
   attempt must forfeit the whole budget. The plan adds the missing partial
   decrement; it does not tune the counter accounting.
2. **Decisions.** DEC-026, DEC-031 and DEC-049 constrain the plan and it
   complies. `FENCED` (`pipeline/core/machine.py:18-36`) names neither
   `pipeline/cli/main.py`, `tests/test_cli.py` nor `README.md`. The `--grant`
   help string asserts "a grant only subtracts"; criterion 3's test holds it,
   which is what DEC-049 requires. No record carries `superseded-by:`.
3. **Scope.** Every step traces to a criterion: 1-6 to 1 and 2, 7-12 to 3, 4
   and 5, 13 to 6, 14 to 7.
4. **Falsifiable.** Criterion 4's test fails against step 4 alone: `.get(key, 0)`
   creates the typo'd key at `-1` and `t.save()` writes it. Step 10 predicts
   that failure.
5. **No research left.** Four line references verified: `cmd_resume` 178-190,
   the `resume` subparser 490, the reproduction test 39-57, README 71 inside
   the block closing at 72.
6. **Riskiest step: 1**, rewriting the reproduction test body under a name that
   must not change. `gate()` runs at `plan-validation` and `revalidating` only
   (`pipeline/daemon/supervisor.py:650,785`), both before `implementing`, so
   the `expect:` string never meets the rewritten body. Fallback stated: a
   rename needs another `triage` pass or a `CLAIMS` change, and `## Rollback`
   reverts the whole branch.
7. **Regression surface.** `--reset` semantics do not change. Step 4 rewrites
   the thread note from `by human` to `by {who}`; no test asserts that string
   -- `grep -rn "resumed" tests/` matches nothing. `cmd_reject`'s die message is
   untouched, and `tests/test_cli.py:144` asserts `"--reset plan_rejections"`.
   The digest cites line 122 for it, which is the enclosing test's `def`.
8. **Blast radius.** Class `feature`, three files, one new function, one flag,
   three new tests. Proportionate.

Two residuals, neither blocking:

- Step 14 runs three test files; `verifying` runs `test_suite`, the whole suite
  plus the guard script. One README-reading test sits outside those three:
  `tests/test_stages.py:161-167`, which windows 300 chars before `stale_regate`
  at `README.md:274`. Step 13 inserts at line 71, 200 lines above it, so that
  window holds the same characters. Verified, not assumed.
- `## Reproduction` will describe a test body step 1 deletes. The earlier
  plan-validation raised this and `planning` recorded it as off-path. `gate()`
  reads `expect:` only before `implementing`, so nothing mechanical breaks. It
  leaves stale prose in the ticket.

### 2026-08-24 10:15:40Z · plan-validation · session · session=75dc3abe-5f2b-4ddb-ad40-ff6c804f963a

`plan-validation` ran as session `75dc3abe-5f2b-4ddb-ad40-ff6c804f963a`
- replay: `claude --resume 75dc3abe-5f2b-4ddb-ad40-ff6c804f963a`
- log: `.project/logs/TICKET-051-plan-validation-75dc3abe.log`

### 2026-08-24 10:15:40Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ all eight judgment items pass; line references verified on 761ceb5, two non-blocking residuals recorded

### 2026-08-24 10:16:07Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 10:20:09Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one` fails as required
```
.mkdtemp())
        cli(d, "new", "t")
        cli(d, "resume", "TICKET-001", "--stage", "planning")
        t = Ticket.load(d / ".project/tickets/TICKET-001.md")
        t.counters["plan_validation_attempts"] = 2
        t.save()
    
        cli(d, "resume", "TICKET-001", "--stage", "planning",
            "--reset", "plan_validation_attempts")
    
        t = Ticket.load(d / ".project/tickets/TICKET-001.md")
>       assert t.counters["plan_validation_attempts"] == 1, (
            f"expected --reset to hand back exactly one wasted attempt "
            f"(2 -> 1), got {t.counters['plan_validation_attempts']} "
            f"(--reset always zeroes the counter)"
        )
E       AssertionError: expected --reset to hand back exactly one wasted attempt (2 -> 1), got 0 (--reset always zeroes the counter)
E       assert 0 == 1

tests/test_cli.py:53: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================

```
- ok: `tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one` fails on base `main` too -- the bug is not already fixed upstream
```
tempt "
            f"(2 -> 1), got {t.counters['plan_validation_attempts']} "
            f"(--reset always zeroes the counter)"
        )
E       AssertionError: expected --reset to hand back exactly one wasted attempt (2 -> 1), got 0 (--reset always zeroes the counter)
E       assert 0 == 1

tests/test_cli.py:53: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_reset_only_zeroes_it_cannot_grant_back_one
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.33s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-stuy730c/base
      Built pipeline @ file:///tmp/pipeline-base-stuy730c/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 10:20:09Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24T10:20:29Z · implementing · note

**todo**

1. [ ] rewrite reproduction test body to drive `--grant`, keep its name
2. [ ] run test, confirm it fails on unknown flag
3. [ ] add `parse_grant` above `cmd_resume`
4. [ ] extend `cmd_resume` with the grant loop and note
5. [ ] add `--grant` to the `resume` subparser
6. [ ] run `tests/test_cli.py`, commit
7. [ ] add over-grant refusal test
8. [ ] add unknown-counter refusal test
9. [ ] add reset+grant clash refusal test
10. [ ] run the three new tests, confirm they fail
11. [ ] add the three refusals to `cmd_resume`
12. [ ] run `tests/test_cli.py`, confirm all pass
13. [ ] add README lines
14. [ ] run cli/machine/dispatch tests, commit

### 2026-08-24T10:22:08Z · implementing · note

**implemented; all 14 plan steps done**

- Steps 1-6: rewrote `test_resume_reset_only_zeroes_it_cannot_grant_back_one` (name unchanged) to drive `--grant`, confirmed RED (`unrecognized arguments: --grant`), added `parse_grant` and the grant loop to `cmd_resume`, added `--grant` to the `resume` subparser, `tests/test_cli.py` green (14 passed), committed `9e94e9d`.
- Steps 7-12: added the three refusal tests, confirmed each RED for the predicted reason (`assert 0 != 0` with counters landing at `-1`), added the clash/unknown-counter/over-grant refusals to `cmd_resume`, `tests/test_cli.py` green (17 passed).
- Step 13: added the two README lines after the existing `--reset` example.
- Step 14: `uv run --group dev pytest -q tests/test_cli.py tests/test_machine.py tests/test_dispatch.py` -> `76 passed`. Committed `77bb4cf`.
- All five acceptance-criteria tests pass individually; `test_the_help_text_matches_the_code_it_describes` still passes.

### 2026-08-24 10:22:43Z · implementing · session · session=7e2e7943-7b2c-40c3-874a-357f2f5506b2

`implementing` ran as session `7e2e7943-7b2c-40c3-874a-357f2f5506b2`
- replay: `claude --resume 7e2e7943-7b2c-40c3-874a-357f2f5506b2`
- log: `.project/logs/TICKET-051-implementing-7e2e7943.log`

### 2026-08-24 10:22:43Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented pipeline resume --grant with over-grant/unknown-counter/clash refusals; tests/test_cli.py (17) and the wider suite (76) pass

### 2026-08-24 10:25:42Z · review · finding · severity=blocking

**1 blocking finding. Delta reviewed: `4708538...77bb4cf` (README.md, pipeline/cli/main.py, tests/test_cli.py).**

1. **blocking** -- a repeated `--grant` key drives the counter negative, which
   criterion 3 forbids. `--grant` takes `nargs="*"`, so
   `pipeline resume TICKET-001 --stage planning --grant plan_validation_attempts plan_validation_attempts`
   on a counter of 1 passes validation and lands at `-1`. The validation loop
   (`pipeline/cli/main.py:204-213`) reads `t.counters.get(key)` before any
   mutation, so both entries see `1` and neither trips `n > have`. The mutation
   loop (`pipeline/cli/main.py:217-220`) then subtracts twice: `1 -> 0 -> -1`.
   Simulated both loops: `final {'pva': -1}`. `validate_meta`
   (`pipeline/core/ticket.py:54-83`) does not read `counters`, so `-1` reaches
   disk. `charge()` (`pipeline/core/machine.py:89-91`) is
   `c[key] = c.get(key, 0) + 1` with no clamp, so `-1` buys one attempt past
   the class bound. This is the over-grant the refusal exists to stop:
   `--grant plan_validation_attempts=2` on 1 is refused, the repeated spelling
   is not. Sum `n` per key before validating, or refuse a repeated key.
2. **nit** -- `parse_grant` (`pipeline/cli/main.py:186-192`) uses
   `raw.isdigit()`, which is true for `²`. `--grant k=²` raises
   `ValueError: invalid literal for int()` instead of calling `die`.
3. **nit** -- `--grant k` on a hand-edited ticket whose `counters[k]` is a
   string raises `TypeError` at `n > have`. `--reset` has no such exposure; it
   assigns `0`.

Verified: `uv run --group dev pytest -q tests/test_cli.py tests/test_machine.py tests/test_dispatch.py` -> `76 passed in 6.00s`. Criteria 1, 2, 4, 5, 6, 7 hold. Criterion 3 holds for `=3` and fails for the repeated key.

long: three findings, each needing its own file:line evidence.

### 2026-08-24 10:26:27Z · review · session · session=f7c61f87-6941-4e00-a6b7-55c8951121f3

`review` ran as session `f7c61f87-6941-4e00-a6b7-55c8951121f3`
- replay: `claude --resume f7c61f87-6941-4e00-a6b7-55c8951121f3`
- log: `.project/logs/TICKET-051-review-f7c61f87.log`

### 2026-08-24 10:26:27Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ blocking: a repeated --grant key drives a counter to -1, which criterion 3 forbids; other 6 criteria hold, 76 tests pass

### 2026-08-24T10:27:25Z · implementing · note

**todo**

1. [x] add RED test for a repeated `--grant` key summing past `have`
2. [x] confirm RED for the expected reason
3. [x] sum `n` per key in `cmd_resume` before validating and mutating
4. [x] confirm GREEN, run wider suite, commit

### 2026-08-24T10:29:02Z · implementing · note

**fixed the blocking finding; all 4 steps done**

Added `test_resume_grant_refuses_a_repeated_key_that_would_sum_past_have`
(`tests/test_cli.py`): `--grant plan_validation_attempts
plan_validation_attempts` on a counter of 1. Confirmed RED for the reviewer's
predicted reason: `assert 0 != 0`, `TICKET-001: -> planning
(\`plan_validation_attempts\` 1 -> 0, \`plan_validation_attempts\` 0 -> -1)`.

`cmd_resume` (`pipeline/cli/main.py`) now builds `grants: dict[str, int]` by
summing `n` per key while parsing `args.grant`, before the clash check, the
validation loop and the mutation loop -- all three now iterate `grants.items()`
instead of the original list, so a repeated key sees its total against `have`
once. The same input now dies with `cannot grant 2`.

`uv run --group dev pytest -q tests/test_cli.py` -> `18 passed`.
`uv run --group dev pytest -q tests/test_cli.py tests/test_machine.py
tests/test_dispatch.py` -> `77 passed in 6.21s`. Committed `04e93b6`.

The two nits from review (`str.isdigit()` on non-ASCII digits, a hand-edited
string counter raising `TypeError`) are untouched: the review marked them
non-blocking and no plan step covers them.

### 2026-08-24 10:27:38Z · implementing · session · session=77c1d358-dc2a-4663-9d99-28c6d40ba1ab

`implementing` ran as session `77c1d358-dc2a-4663-9d99-28c6d40ba1ab`
- replay: `claude --resume 77c1d358-dc2a-4663-9d99-28c6d40ba1ab`
- log: `.project/logs/TICKET-051-implementing-77c1d358.log`

### 2026-08-24 10:27:38Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ fixed the blocking finding (repeated --grant key sums before validating); 77 passed in 6.21s

### 2026-08-24 10:33:11Z · review · finding · severity=none

**No blocking findings. Delta reviewed: `77bb4cf...04e93b6` (pipeline/cli/main.py, tests/test_cli.py).**

The previous blocking finding is fixed. `cmd_resume` sums `n` per key into
`grants: dict[str, int]` (`pipeline/cli/main.py:200-202`) before the clash
check, the validation loop and the mutation loop, so a repeated key is
validated once against `have`. `--grant plan_validation_attempts
plan_validation_attempts` on a counter of 1 now exits non-zero with
`cannot grant 2`, asserted by
`test_resume_grant_refuses_a_repeated_key_that_would_sum_past_have`
(`tests/test_cli.py:104-119`).

No counter can reach a negative value now. The validation loop reads
`t.counters.get(key)` before the `--reset` zeroing (`pipeline/cli/main.py:216`),
and the mutation loop reads `t.counters[key]` after it; the two differ only for
a key named in both lists, and lines 203-205 refuse that. `parse_grant` enforces
`n >= 1`, and `die` is `sys.exit(1)` (`pipeline/cli/main.py:31-35`), so no
refusal falls through to a mutation.

1. **nit** -- `--grant a --grant b` keeps only `b`: `nargs="*"` with the default
   store action overwrites. Confirmed: `Namespace(grant=['b'])`. `--reset` has
   the same shape, and a dropped grant cannot over-grant.

Nits 2 and 3 from the previous review (`str.isdigit()` on `²`, a string counter)
are unchanged and stay non-blocking.

Verified: `uv run --group dev pytest -q tests/test_cli.py tests/test_machine.py tests/test_dispatch.py` -> `77 passed in 6.19s`. All seven acceptance criteria hold.

### 2026-08-24 10:29:45Z · review · session · session=27b4dacf-3b1a-43fc-95e5-92939ce31684

`review` ran as session `27b4dacf-3b1a-43fc-95e5-92939ce31684`
- replay: `claude --resume 27b4dacf-3b1a-43fc-95e5-92939ce31684`
- log: `.project/logs/TICKET-051-review-27b4dacf.log`

### 2026-08-24 10:29:45Z · review · transition · to=holistic-review · result=ok · marker=yes

**review -> holistic-review** (result: `ok`)

✓ no blocking findings in 77bb4cf...04e93b6; the repeated --grant key is refused with `cannot grant 2`, all 7 criteria hold, 77 passed

### 2026-08-24 10:36:00Z · holistic-review · finding · severity=none

**Coherent. Reviewed the whole ticket diff `4708538..04e93b6`: `README.md` (+2), `pipeline/cli/main.py` (+37/-4), `tests/test_cli.py` (+101).**

The three commits sum to what `## Plan` describes. Plan steps 3, 4, 5, 11 and
13 all landed. Step 4's mutation loop reads `t.counters[key]`, which is step
11's amendment, not a leftover. No later commit undid an earlier one: `04e93b6`
replaces the `grants` list with a per-key sum, and the clash check, the
validation loop and the mutation loop all moved to `grants.items()` together.

Error handling is uniform. Every refusal is `die(...)` and every one runs
before `t.stage = args.stage`, so a refused command changes neither the
counters nor the stage. `parse_grant` uses the same `die`. Nothing raises
`PipelineError`, and `cmd_resume` never did.

Nothing landed outside the acceptance criteria. The one addition beyond the
plan is `test_resume_grant_refuses_a_repeated_key_that_would_sum_past_have`
(`tests/test_cli.py`), which criterion 3's "no counter reaches a negative
value" requires.

`--reset` on an absent counter still creates it at `0` while `--grant` refuses
it. That asymmetry predates the ticket and `## Decisions` keeps `--reset`
unchanged on purpose.

Verified: `uv run --group dev pytest -q tests/test_cli.py tests/test_machine.py tests/test_dispatch.py` -> `77 passed in 6.21s`.

### 2026-08-24 10:30:58Z · holistic-review · session · session=bdd029e8-1854-4b64-a07d-2562cd2f0e1d

`holistic-review` ran as session `bdd029e8-1854-4b64-a07d-2562cd2f0e1d`
- replay: `claude --resume bdd029e8-1854-4b64-a07d-2562cd2f0e1d`
- log: `.project/logs/TICKET-051-holistic-review-bdd029e8.log`

### 2026-08-24 10:30:58Z · holistic-review · transition · to=verifying · result=ok · marker=yes

**holistic-review -> verifying** (result: `ok`)

✓ coherent: 4708538..04e93b6 matches the plan, no fix undid another, die is the one refusal path, 77 passed in 6.21s

### 2026-08-24 10:31:11Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 10:31:12Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/051


Current branch ticket/051 is up to date.
Already up to date.
Updating 4708538..04e93b6
Fast-forward
 README.md            |   2 +
 pipeline/cli/main.py |  41 +++++++++++++++++++--
 tests/test_cli.py    | 101 +++++++++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 140 insertions(+), 4 deletions(-)

```

### 2026-08-24 10:31:12Z · merging · decision

decision recorded as `DEC-051`
