---
id: TICKET-100
stage: done
class: feature
branch: ticket/100
test_file: tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first
files_declared:
- CLAUDE.md
- pipeline/cli/main.py
- pipeline/core/machine.py
- pipeline/core/ticket.py
- pipeline/daemon/server.py
- pipeline/daemon/supervisor.py
- pipeline/templates/skills/file-ticket/SKILL.md
- pipeline/templates/ticket.md
- tests/test_cli.py
- tests/test_daemon.py
- tests/test_dispatch.py
- tests/test_machine.py
- tests/test_ticket.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 13
  plan_files: 13
  no_result: 0
  structural_gate_failures: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 22d90ac7-9eec-47a4-884d-121e7f23ffdd
  log: .project/logs/TICKET-100-review-22d90ac7.log
  cost_usd: 2.1166055
approved_by: 'chezzijr (via Claude Code, while away; reviewed the fenced diff). validate_meta
  gains three lines matching the files_declared loop, checking depends_on against
  SAFE_ID (^TICKET-\d{1,6}$, anchored), so nothing from a ticket file reaches a shell
  through the field; as_test_list keeps its name and docstring and delegates to the
  new as_list. CONTROL_FIELDS gains one entry with its reason -- accepted consequence:
  a stage writing depends_on now escalates the ticket instead of being silently reverted,
  and a hand-edit under a live lease does too, so edit it at a gate like test_file.
  transition() is untouched and the two new functions are pure, below files_conflict.
  Checked the classic cycle bug: seen is marked after the dep-in-path test, so a diamond
  cannot mask a cycle. 253 insertions, 113 of them tests.'
approved_at: '2026-08-30T11:07:39.574125+00:00'
---

## Summary

a ticket cannot declare that another ticket must land first

The only ordering the dispatcher knows is file overlap: `conflict_holder()`
(`pipeline/core/machine.py:305`), consulted once by `start()`
(`pipeline/daemon/supervisor.py:776`). It orders two tickets that touch the
same file and says nothing about two that are strictly ordered while touching
different files, so the ordering was written as English prose and nothing
enforced it.

triage confirmed no dependency field exists and committed a failing test,
`tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first`
(commit `3f54d3e`).

planning wrote a 13-step plan. `depends_on` is agent-visible frontmatter,
validated in `validate_meta()`, owned by the human (in no `CLAIMS` entry, added
to `CONTROL_FIELDS`), enforced by `dep_holder()` waiting and by
`dep_unsatisfiable()` escalating a missing, terminal or cyclic dependency,
reported by `ls` through the existing `waiting` key, and written by
`pipeline new --depends-on`.

The Tier A gate rejected that plan on one finding: "section `## Reproduction`
missing or empty". planning filled that section and the gate then passed. The
13 steps, the acceptance criteria, the decisions and `files_declared` are
unchanged from the rejected plan.

Tier B passed all eight items. The plan fixes the cause, not the assertion:
`start()` reads no dependency field, and the plan adds one, its reader and the
wait. DEC-029, DEC-048 and DEC-066 constrain this plan and it complies with
each; no decision names a dependency field. Every step names a file and a
function that exist. The riskiest step is 9, the wiring into `start()`, and it
is guarded by `if t.extra.get("depends_on"):` so a project declaring none runs
no new code.

Two observations for `implementing`, neither a defect in the plan. A `new`
ticket whose dependency lands keeps a stale `waiting` dict for one tick, and
clears it next tick at `triage`. `dep_unsatisfiable()` misses a cycle that is
reachable but off the walked path; the tickets in that cycle still escalate on
their own `start()` call, so nothing hangs. Full reasoning is in the
`plan-validation` thread entry.

The diff touches `validate_meta` and `CONTROL_FIELDS`, both in `machine.FENCED`,
so this parks at `awaiting-merge`.

implementing executed all 13 steps with TDD (each new test verified RED before
its code, verified GREEN after) and committed after each step. `depends_on` is
now validated (`as_list()`, `validate_meta()`), a control field, waited on by
`start()` via `dep_holder()`/`dep_unsatisfiable()`, rendered by `waiting_text()`,
and settable via `pipeline new --depends-on`. Full suite: 501 passed, 0 failed.
Every acceptance criterion re-checked and green. This still parks at
`awaiting-merge` for the fenced diff.

review found no blocking finding and passed the ticket. It read the delta
`3f54d3e..baf730f`, 13 files, and confirmed all 13 plan steps landed with no
drift. Re-run fresh: `uv run --group dev pytest -q` reports `501 passed in
35.28s`, all 9 acceptance criteria pass individually, and the guard suite
reports `guard: all passed`. Four minor findings are in the `review` thread
entry: `dep_unsatisfiable()` skips a cycle off the walked path (no hang -- the
cycle members escalate on their own `start()` call, measured), a dependent's
`waiting` rewrite resets the mtime `stale` is derived from, a `new` ticket
keeps a stale `waiting` dict for one tick, and `dep_holder()`'s `"?"` stage
fallback is unreachable from `start()`. The first and third were already known
from `plan-validation`. review dropped one candidate finding: an unsubstituted
`{{depends_on}}` cannot reach YAML, because `cmd_new` is the only reader of
`TICKET_TEMPLATE` and always substitutes.

The next gate is `awaiting-merge`, and a human must read the fenced diff --
`validate_meta()` and `CONTROL_FIELDS`.

## Reproduction

`tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first`,
run with `uv run --group dev pytest -q tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first`.

The test files TICKET-001 at `implementing` and TICKET-002 at `new` carrying
`depends_on: TICKET-001` in its frontmatter, calls
`supervisor.start(d, path, harness("fake"), {})` on TICKET-002, and asserts
`did is False`. `start()` claims TICKET-002 anyway:

    E       AssertionError: TICKET-002 declared depends_on: TICKET-001, which is still at `implementing`, but start() advanced it anyway -- nothing in start() reads a dependency field
    E       assert True is False

    tests/test_dispatch.py:2132: AssertionError
    ----------------------------- Captured stdout call -----------------------------
      TICKET-002: -> triage {'plan_steps': 1, 'plan_files': 1}

expect: assert True is False

Committed at `3f54d3e` on `ticket/100`. `start()` consults one ordering,
`conflict_holder()` on `files_declared`, and the two tickets declare
different files, so nothing holds TICKET-002 back.

## Digest

Files touched: `pipeline/core/ticket.py` (`as_list()`, `validate_meta()`), `pipeline/core/machine.py` (`dep_holder()`, `dep_unsatisfiable()`, `CONTROL_FIELDS`), `pipeline/daemon/supervisor.py` (`dep_graph()`, `note_wait()`, `start()`), `pipeline/daemon/server.py` (`waiting_text()`), `pipeline/cli/main.py` (`cmd_new`, the `new` subparser), `pipeline/templates/ticket.md`, `pipeline/templates/skills/file-ticket/SKILL.md`, `CLAUDE.md`, and five test files.
Entry point: `start()` (`pipeline/daemon/supervisor.py:705`). Its ordering block is lines 776-780: `held = conflict_holder(t.frontmatter(), [...inflight...])`, then `note_wait(t, held)`, then `return False, None`. `start()` advances `stage == "new"` synchronously at line 772, ABOVE that block -- so a dependency check placed beside `conflict_holder` never runs for the repro ticket, which sits at `new`. The check goes above the `if stage == "new"` line.
Key functions: `conflict_holder()` (`pipeline/core/machine.py:305`) returns `(id, file)` or `None` and is the shape to copy. `note_wait()` (`pipeline/daemon/supervisor.py:687`) writes `t.extra["waiting"] = {"on", "file", "since"}` and only when the reason changes. `waiting_text()` (`pipeline/daemon/server.py:89`) renders it for `ls` and returns `""` unless BOTH `on` and `file` are set -- a `{on, stage}` dict renders as nothing until that function is widened. `ticket_rows()` (`pipeline/daemon/server.py:138`) copies `waiting` into the row only when it is a dict.
Gotcha -- the field arrives as a scalar, not a list. The repro test writes `depends_on: TICKET-001`, which YAML loads as `str`. DEC-066 records what a bare string in a list-shaped field costs: `validate_meta()` iterates it one character at a time and `conflict_holder()` builds a set of characters. `test_file` already solves this with `as_test_list()` (`pipeline/core/ticket.py:55`); `depends_on` reuses that helper, generalised as `as_list()`.
Gotcha -- an agent cannot set the field even if it tries. `_finish()` (`pipeline/daemon/supervisor.py:1128`) rebuilds the ticket as `replace(snap, body=agent.body)`, so every frontmatter key comes from the pre-spawn snapshot, and `apply_claims()` re-applies only the fields in `CLAIMS`. Leaving `depends_on` out of `CLAIMS` makes it human-only with no further code. Adding it to `CONTROL_FIELDS` upgrades an agent's write from a silent revert to an escalation.
Gotcha -- the dependency graph is not in `inflight`. `conflict_holder()` reads `inflight` alone, so a ticket parked at `awaiting-approval` holds no record there. A dependency must be readable at any stage, so the check reads the ticket files: `all_tickets(project)` is already imported in `pipeline/daemon/supervisor.py:30`.
Gotcha -- `pipeline/core/ticket.py`'s `validate_meta` and `pipeline/core/machine.py`'s `CONTROL_FIELDS` are both in `machine.FENCED`, so this ticket parks at `awaiting-merge` for a human diff review whatever the pipeline says. `FENCED` itself is not edited, so `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` is unaffected.
Baseline measured on `ticket/100` at `3f54d3e`: `uv run --group dev pytest -q` reports one failure, `tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first`, and no others.

## Decisions checked

- DEC-048 (active) -- binding, and this plan complies. It fixes the `waiting` contract: the reason is written by `start()` into frontmatter because `ticket_rows()` has no `inflight` in the file fallback; `waiting` is advisory display and is NEVER read back as control flow; `note_wait()` writes only when the reason changes, because an unconditional save resets the STALE clock forever; `waiting` is deliberately left out of `validate_meta()`. This plan adds a second reason shape to `waiting` and keeps all four properties: the dependency verdict is recomputed from the ticket files every tick, and `note_wait()` keeps its write-on-change guard.
- DEC-029 (active) -- context, not an obstacle. It records that `files_conflict` is consulted against `inflight` alone, and that making it read every non-terminal ticket "serialises tickets for as long as a human takes to approve. That is a different change". This plan does not touch `files_conflict`: it adds an opt-in field, so a ticket that declares nothing pays nothing and the serialisation DEC-029 refused is never introduced.
- DEC-066 (active) -- binding, and this plan complies. "Do not 'fix' that by storing it: as a string it reaches the frontmatter, where `validate_meta()` iterates it one character at a time". `depends_on` therefore goes through `as_list()` at every read, exactly as `test_file` goes through `as_test_list()`.
- DEC-087 and DEC-051 (active) -- context for the `CLAIMS` decision. Both record `CLAIMS` giving a field to exactly one stage and what a stage cannot then rewrite. Neither constrains a field that no stage owns.
- Grep terms used in `.project/decisions/`: `files_conflict`, `conflict_holder`, `note_wait`, `waiting`, `depends`, `CLAIMS`, `validate_meta`, `ordering`, `order`. No record names a dependency field.

## Plan

1. Write the failing test `test_depends_on_is_validated_like_every_other_agent_reachable_field` in `tests/test_ticket.py`: assert `T.validate_meta({"id": "TICKET-001", "branch": "ticket/001", "depends_on": "TICKET-002"}) == []`, assert `T.validate_meta({"id": "TICKET-001", "branch": "ticket/001", "depends_on": ["TICKET-002", "$(rm -rf /)"]}) == ["depends_on entry '$(rm -rf /)' is not TICKET-<digits>"]`, and assert `T.as_list("TICKET-002") == ["TICKET-002"] and T.as_list(None) == [] and T.as_list(["a"]) == ["a"]`. Run `uv run --group dev pytest -q tests/test_ticket.py::test_depends_on_is_validated_like_every_other_agent_reachable_field` and watch it fail with `AttributeError: module 'pipeline.core.ticket' has no attribute 'as_list'`.
2. Make step 1 pass in `pipeline/core/ticket.py`: insert `def as_list(v) -> list:` directly above `as_test_list()` with the body `if not v: return []` then `return list(v) if isinstance(v, list) else [v]` and the docstring `"""A scalar, a list, or nothing, as a list. A ticket file writes both `test_file` and `depends_on` either way."""`; replace `as_test_list()`'s two body lines with `return as_list(v)`, keeping its existing docstring (the name stays -- pytest collects a module-level `test*` name a test module imports); and append to `validate_meta()`, after the `files_declared` loop and before the `lease` block, the three lines `for dep in as_list(meta.get("depends_on")):` / `if not SAFE_ID.match(str(dep)):` / `bad.append(f"depends_on entry {dep!r} is not TICKET-<digits>")`. Re-run the same command, expect `1 passed`, then commit.
3. Write two failing tests in `tests/test_machine.py`: `test_dep_holder_names_the_first_dependency_short_of_done` asserts `M.dep_holder("TICKET-003", {"TICKET-003": ["TICKET-002", "TICKET-001"]}, {"TICKET-001": "implementing", "TICKET-002": "done", "TICKET-003": "new"}) == ("TICKET-001", "implementing")`, that the same call with `"TICKET-001": "done"` returns `None`, and that `M.dep_holder("TICKET-001", ...)` returns `None` because a ticket with no `depends_on` never waits; `test_a_dependency_that_can_never_land_escalates_instead_of_waiting` asserts `"escalated" in M.dep_unsatisfiable("TICKET-002", {"TICKET-002": ["TICKET-001"]}, {"TICKET-001": "escalated", "TICKET-002": "new"})`, `"not a ticket" in M.dep_unsatisfiable("TICKET-002", {"TICKET-002": ["TICKET-404"]}, {"TICKET-002": "new"})`, `"cycle" in M.dep_unsatisfiable("TICKET-002", {"TICKET-002": ["TICKET-001"], "TICKET-001": ["TICKET-002"]}, {"TICKET-001": "new", "TICKET-002": "new"})`, and that `M.dep_unsatisfiable("TICKET-002", {"TICKET-002": ["TICKET-001"]}, {"TICKET-001": "done", "TICKET-002": "new"}) is None`. Run `uv run --group dev pytest -q tests/test_machine.py -k dep` and watch both fail on the missing attributes.
4. Make step 3 pass in `pipeline/core/machine.py` by adding two pure functions directly below `files_conflict()`: `dep_holder(tid: str, deps: dict[str, list[str]], stages: dict[str, str]) -> tuple[str, str] | None` iterates `for dep in sorted(deps.get(tid, []))` and returns `(dep, str(stages.get(dep, "?")))` for the first whose `stages.get(dep) != "done"`, else `None`, docstring "The first dependency of `tid` short of `done`, and the stage it sits at. Sorted, so one blocked ticket always names the same holder. Only the direct dependencies: a transitive one blocks its own ticket, so the order holds one hop at a time."; `dep_unsatisfiable(tid: str, deps: dict[str, list[str]], stages: dict[str, str]) -> str | None` walks `stack = [(tid, [tid])]` with `seen: set[str] = set()`, popping `(cur, path)` and for each `dep in deps.get(cur, [])` returning `"depends_on is a cycle: " + " -> ".join(path[path.index(dep):] + [dep])` when `dep in path`, `f"{cur} depends_on {dep}, which is not a ticket in this project"` when `dep not in stages`, `f"{cur} depends_on {dep}, which is {stages[dep]} and can never reach done"` when `stages[dep] in TERMINAL and stages[dep] != "done"`, and otherwise pushing `(dep, path + [dep])` and adding `dep` to `seen` when `dep not in seen`; returns `None` when the walk drains. Re-run the step 3 command, expect `2 passed`, then commit.
5. Add `"depends_on"` to `CONTROL_FIELDS` in `pipeline/core/machine.py` with the comment "`depends_on` is the human's, not a stage's -- it is in no `CLAIMS` entry, so a stage's sidecar cannot set it, and listing it here turns an agent's frontmatter write from a silent revert into an escalation", and extend `test_control_fields_are_the_dispatchers_alone` in `tests/test_machine.py` with `assert "depends_on" in M.CONTROL_FIELDS, "a stage that edits the ordering must escalate, not be reverted"` and `assert "depends_on" not in M.CLAIMS, "the human who files the batch owns the ordering"`. Run `uv run --group dev pytest -q tests/test_machine.py`, expect no failures, then commit.
6. Widen `waiting_text()` in `pipeline/daemon/server.py` to render the dependency reason, and test it first: add `test_waiting_text_renders_a_declared_dependency` to `tests/test_daemon.py` asserting `waiting_text({"on": "TICKET-001", "stage": "implementing"}) == "waiting on TICKET-001 (depends_on, at implementing)"`, `waiting_text({"on": "TICKET-001", "file": "thing.py"}) == "waiting on TICKET-001 (thing.py)"` and `waiting_text({"on": "TICKET-001"}) == ""`; then change the guard to `if not (isinstance(w, dict) and w.get("on")): return ""`, followed by `if w.get("file"): text = f"waiting on {w['on']} ({w['file']})"`, `elif w.get("stage"): text = f"waiting on {w['on']} (depends_on, at {w['stage']})"`, `else: return ""`, leaving the `since` age block below unchanged, and extend the docstring with "Two reasons reach this: a file overlap, which names the file, and a declared `depends_on`, which names the stage the dependency sits at." Run `uv run --group dev pytest -q tests/test_daemon.py`, expect no failures, then commit.
7. Generalise `note_wait()` in `pipeline/daemon/supervisor.py` to carry either reason: change the signature to `def note_wait(t: Ticket, held: dict | None) -> None`, replace the previous-reason comparison with `if isinstance(prev, dict) and {k: v for k, v in prev.items() if k != "since"} == held: return`, write `t.extra["waiting"] = {**held, "since": now().isoformat()}`, keep the docstring's write-on-change paragraph (DEC-048) and re-title it "Record why `start()` is holding `t`, so `ls` can say so", and update the one existing caller in `start()` to `held = conflict_holder(...)` then `note_wait(t, {"on": held[0], "file": held[1]} if held else None)`. Run `uv run --group dev pytest -q tests/test_dispatch.py tests/test_daemon.py`, expect only `test_a_ticket_cannot_declare_that_another_must_land_first` to fail, then commit.
8. Add `dep_graph()` to `pipeline/daemon/supervisor.py`, directly above `note_wait()`: `def dep_graph(project: Path) -> tuple[dict[str, list[str]], dict[str, str]]` loops `for p in all_tickets(project)`, skips a ticket whose `Ticket.load(p)` raises `PipelineError`, and fills `stages[o.id] = o.stage` and `deps[o.id] = [str(x) for x in as_list(o.extra.get("depends_on"))]`, with the docstring "Every ticket's `depends_on` and `stage`, read off disk. `conflict_holder()` consults `inflight` alone, and a dependency parked at a human gate holds no record there (DEC-029). Called only for a ticket that declares `depends_on`, so a project that declares none pays nothing. An unreadable ticket is skipped: a dependency on one reads as missing, which escalates the dependent rather than parking it forever." Import `as_list` from `pipeline.core.ticket` and `dep_holder, dep_unsatisfiable` from `pipeline.core.machine` in the same file's import block. Commit.
9. Wire the check into `start()` in `pipeline/daemon/supervisor.py`, immediately above the `if stage == "new":` line and below the lease-expiry block: `if t.extra.get("depends_on"):` then `deps, stages = dep_graph(project)`, then `dead = dep_unsatisfiable(tid, deps, stages)` and `if dead: return bail(dead)`, then `dep = dep_holder(tid, deps, stages)` and `if dep is not None:` / `note_wait(t, {"on": dep[0], "stage": dep[1]})` / `return False, None`, with the comment "A declared dependency orders two tickets that share no file, which `conflict_holder()` cannot see. Checked above `new` so a blocked ticket is never even claimed, and waiting -- never failing -- exactly like the file overlap below." Run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first`, expect `1 passed`, then commit.
10. Add two tests to `tests/test_dispatch.py`, adding `from pipeline.daemon.server import ticket_rows, waiting_text` to its imports if absent: `test_a_dependency_that_cannot_land_escalates_rather_than_waiting_forever` writes `FIXTURE` to `TICKET-001.md` with `stage: plan-validation` replaced by `stage: new` and `depends_on: [TICKET-404]` inserted into the frontmatter, calls `supervisor.start(d, path, harness("fake"), {})` and asserts `did is True` and `Ticket.load(path).stage == "escalated"`; `test_ls_names_the_ticket_a_dependency_is_waiting_on` rebuilds the two-ticket setup of `test_a_ticket_cannot_declare_that_another_must_land_first`, calls `start()` on TICKET-002, and asserts `waiting_text([r for r in ticket_rows(d) if r["id"] == "TICKET-002"][0]["waiting"]).startswith("waiting on TICKET-001 (depends_on, at implementing)")` -- `startswith`, because `waiting_text()` appends the age `0m`. Run `uv run --group dev pytest -q tests/test_dispatch.py`, expect no failures, then commit.
11. Give the human a way to write the field without hand-editing frontmatter, test first: add `test_cli_new_records_a_declared_dependency` to `tests/test_cli.py` which runs `cli(d, "new", "first", "--class", "bugfix")`, then `cli(d, "new", "second", "--depends-on", "TICKET-001")` and asserts `returncode == 0` and `"depends_on: [TICKET-001]" in (d / ".project/tickets/TICKET-002.md").read_text()`, then asserts `cli(d, "new", "third", "--depends-on", "not-a-ticket").returncode != 0`. In `pipeline/cli/main.py` add `p.add_argument("--depends-on", dest="depends_on", default="", help="comma-separated ticket ids that must reach `done` before this one is claimed")` to the `new` subparser at line 681, import `SAFE_ID` alongside `Ticket` from `pipeline.core.ticket`, and in `cmd_new` build `deps = [x.strip() for x in (args.depends_on or "").split(",") if x.strip()]`, `die(f"--depends-on {one!r} is not TICKET-<digits>")` for any `one` in `deps` failing `SAFE_ID.match(one)`, and add `.replace("{{depends_on}}", "[" + ", ".join(deps) + "]")` to the template substitution chain. In `pipeline/templates/ticket.md` add the line `depends_on: {{depends_on}}` directly below `files_declared: []`. Run `uv run --group dev pytest -q tests/test_cli.py`, expect no failures, then commit.
12. Document the field where a filer reads, in `pipeline/templates/skills/file-ticket/SKILL.md` (`.claude/skills/file-ticket/SKILL.md` is a symlink to it, so one edit covers both): add a row to the "Who fills it" table directly below the `class` row, naming frontmatter `depends_on` in the first column and "you" in the second, change "**Do not touch the frontmatter beyond `class`.**" to "**Do not touch the frontmatter beyond `class` and `depends_on`.**", and add after that paragraph: "**Ordering: `depends_on` names the tickets that must reach `done` first.** Write it as `depends_on: [TICKET-023]` or pass `pipeline new --depends-on TICKET-023`, and only when the later ticket's work genuinely cannot be planned until the earlier one lands -- prose in `## Summary` saying 'land TICKET-023 first' enforces nothing. The dispatcher WAITS rather than failing, `pipeline ls` names what a ticket waits on, and a dependency that is missing, `escalated`, `rejected`, or part of a cycle escalates the dependent instead of hanging. Two tickets that touch the same file are already ordered by `files_declared`; do not restate that as a dependency." Commit.
13. Add one bullet to the "Gotchas" list in `CLAUDE.md`, beside the `files_conflict` and merge-wait entries: "**Ordering has two sources, and only one is a proxy.** `files_conflict` orders two tickets that declare the same file; `depends_on` in a ticket's frontmatter orders two that share no file at all. `start()` consults `dep_unsatisfiable()` then `dep_holder()` (`pipeline/core/machine.py`) above the `new` advance, waits exactly as it does for a file overlap, and reports the wait through the same `waiting` key -- {on, stage} for a dependency, {on, file} for an overlap. The field is the human's: it is in `CONTROL_FIELDS` and in no `CLAIMS` entry, so a stage that writes it escalates the ticket." Run `uv run --group dev pytest -q`, expect no failures, then commit.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first` exits `0`.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_a_dependency_that_cannot_land_escalates_rather_than_waiting_forever` exits `0`: a `depends_on` naming a ticket that does not exist escalates instead of waiting.
- `uv run --group dev pytest -q tests/test_dispatch.py::test_ls_names_the_ticket_a_dependency_is_waiting_on` exits `0`: `ls` names the ticket the wait is on and the stage it sits at.
- `uv run --group dev pytest -q tests/test_machine.py -k dep` exits `0`, covering the cycle, the missing id, the `escalated` dependency and the all-`done` case.
- `uv run --group dev pytest -q tests/test_ticket.py -k depends_on` exits `0`: a `depends_on` entry that is not `TICKET-<digits>` is refused by `validate_meta()`.
- `uv run --group dev pytest -q tests/test_cli.py::test_cli_new_records_a_declared_dependency` exits `0`.
- `uv run --group dev pytest -q` reports no failure other than ones already failing on `main` at the same commit; measured on `ticket/100` at `3f54d3e` the only failure was this ticket's repro test, which step 9 turns green.
- `grep -c 'depends_on' pipeline/templates/ticket.md` prints `1`.
- `grep -c 'depends_on' pipeline/templates/skills/file-ticket/SKILL.md` prints a number greater than `0`, and `git diff --stat main -- CLAUDE.md` names `CLAUDE.md`.

## Decisions

**`depends_on` is the human's field, not a stage's.** It is in no `CLAIMS`
entry, so no stage can set it through its `.result` sidecar, and it IS in
`CONTROL_FIELDS`, so a stage that edits it in the ticket's frontmatter
escalates the ticket instead of having the write silently reverted. The
person who files a batch is the one who knows the ordering; a stage sees one
ticket and cannot. Giving the field to `triage` would let a stage park its own
ticket behind an arbitrary other one, which the dispatcher would then have to
escalate anyway.

**The dispatcher WAITS on a dependency; it never fails one.** Same shape as
`files_conflict`: `start()` returns `(False, None)` and the ticket is
retried next tick. Failing would burn a counter for the crime of being
second.

**Waiting on something that can never arrive is the one case that
escalates.** `dep_unsatisfiable()` returns a reason for three of them -- an id
no ticket file carries, a dependency that reached `escalated` or `rejected`,
and a cycle reachable from this ticket -- and `start()` calls `bail()` on it.
It runs BEFORE `dep_holder()`, or a cycle would park both tickets forever
instead of reporting itself. `bail()` escalates and charges no counter,
because no retry can differ.

**`dep_holder()` consults only the direct dependencies.** A transitive
dependency blocks its own ticket, which blocks this one, so the ordering
holds one hop at a time. Do not "fix" this into a transitive walk;
`dep_unsatisfiable()` is the only function here that walks the graph, and it
walks it to find a cycle.

**The check reads the ticket files, not `inflight`.** A dependency parked at
`awaiting-approval` holds no `inflight` record (DEC-029), so `inflight` cannot
answer the question. `dep_graph()` is called only for a ticket that declares
`depends_on`, so this costs nothing for a project that declares none -- and it
is why the check must NOT be folded into `conflict_holder()`, which DEC-029
deliberately keeps on `inflight`.

**The dependency verdict is recomputed every tick; `waiting` stays advisory.**
DEC-048 still holds in full. `waiting` gained a second shape,
`{on, stage, since}` beside `{on, file, since}`, and nothing reads either back
as control flow.

## Rollback

Revert the commits from steps 2 through 13 (`git revert` them, or reset to
`3f54d3e`). `depends_on` then becomes an inert frontmatter key: unknown keys
round-trip through `Ticket.extra`, so an existing ticket file still loads and
saves unchanged, and a `waiting: {on, stage}` dict left behind renders as the
empty string in `ls` rather than raising. What is lost is the ordering itself:
a ticket declaring `depends_on` is claimed immediately again, and a
dependency naming a missing ticket stops escalating. Reverting step 13 or
step 12 alone is safe and only removes documentation. Reverting step 5 alone
downgrades a stage's write to the field from an escalation to a silent
revert.

## Thread

### 2026-08-30 · implementing · todo

**implementing todo** (one per plan step, updated as I go)

1. [x] `as_list()` + `validate_meta()` depends_on check, `tests/test_ticket.py`
2. [x] wire step 1 into `pipeline/core/ticket.py`
3. [x] `dep_holder()`/`dep_unsatisfiable()` tests, `tests/test_machine.py`
4. [x] implement `dep_holder()`/`dep_unsatisfiable()` in `pipeline/core/machine.py`
5. [x] add `depends_on` to `CONTROL_FIELDS` + test
6. [x] `waiting_text()` widened + test, `pipeline/daemon/server.py`
7. [x] `note_wait()` generalised, `pipeline/daemon/supervisor.py`
8. [x] `dep_graph()` added
9. [x] wire check into `start()`
10. [x] two more `tests/test_dispatch.py` tests
11. [x] `pipeline new --depends-on` + test
12. [x] SKILL.md doc update
13. [x] CLAUDE.md gotcha bullet + full suite run

All 13 done. 501 passed, 0 failed.

### 2026-08-30 01:49:14Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-30 · triage · result=ok

Confirmed by reading the code, not just the ticket: `validate_meta()`
(`pipeline/core/ticket.py:69`), `CONTROL_FIELDS`/`FENCED`
(`pipeline/core/machine.py:285`) and `start()`
(`pipeline/daemon/supervisor.py:705`) hold no dependency field or check.
`conflict_holder()` is the only ordering `start()` consults, and it is
file-overlap only, confirming the ticket's own reading.

Wrote a failing test on branch `ticket/100`:
`tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first`.
It files TICKET-001 at `implementing` and TICKET-002 with
`depends_on: TICKET-001` at `new`, then calls `start()` on TICKET-002 and
asserts it does not advance.

Command: `uv run --group dev pytest -q tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first`

Output:
```
E       AssertionError: TICKET-002 declared depends_on: TICKET-001, which is still at `implementing`, but start() advanced it anyway -- nothing in start() reads a dependency field
E       assert True is False
```
expect: assert True is False

Committed as `3f54d3e`. `depends_on` is my probe field for the test, not a
proposed schema -- planning still owns the four decisions the ticket lists.

### 2026-08-30 01:51:03Z · triage · session · session=2c348c23-4b9c-4d72-bc8f-605339ba2d19

`triage` ran as session `2c348c23-4b9c-4d72-bc8f-605339ba2d19`
- replay: `claude --resume 2c348c23-4b9c-4d72-bc8f-605339ba2d19`
- log: `.project/logs/TICKET-100-triage-2c348c23.log`
- cost: $0.49 of a $3 cap
- tokens: 7,002 out (2,816 thinking) · 52 in · 1,154,488 cache read · 46,135 cache write

### 2026-08-30 01:51:03Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ confirmed no dependency field exists; committed a failing test proving start() ignores depends_on

### 2026-08-30 · planning · result=ok

Planned. `depends_on` is a list, or one scalar id, of tickets that must reach
`done`; `start()` waits on it exactly as it waits on `files_conflict`.

The four decisions the ticket asked for:
1. Validation: `validate_meta()` checks every entry against `SAFE_ID`, and
   every read goes through a new `as_list()` -- `depends_on: TICKET-001` loads
   as a `str`, and DEC-066 records what a bare string costs a list-shaped field.
2. Unsatisfiable dependency: `dep_unsatisfiable()` escalates on a missing id,
   on `escalated` or `rejected`, and on a cycle. It runs before the wait check,
   so a cycle reports itself instead of deadlocking.
3. Cycle: one DFS from the ticket over the graph, reported as the path.
4. Who writes it: the human. `depends_on` is in no `CLAIMS` entry, so no
   sidecar can set it, and step 5 adds it to `CONTROL_FIELDS`, so a stage that
   edits it escalates rather than having the write silently reverted.
   `pipeline new --depends-on TICKET-023` is how a human writes it.

The check reads the ticket files, not `inflight`: a dependency parked at
`awaiting-approval` holds no `inflight` record (DEC-029). `dep_graph()` runs
only for a ticket that declares the field, so nothing else pays for it.

`ls` reports the wait through the existing `waiting` key, which gains a second
shape, on/stage/since, beside on/file/since. DEC-048 still holds in full.

Out of scope, noted not fixed: the merge wait in `start()` still returns
False with no `waiting` reason. DEC-048 records that as a separate ticket.

### 2026-08-30 02:00:26Z · planning · session · session=abcfe23f-9fb7-4632-9de0-1211d6b407c3

`planning` ran as session `abcfe23f-9fb7-4632-9de0-1211d6b407c3`
- replay: `claude --resume abcfe23f-9fb7-4632-9de0-1211d6b407c3`
- log: `.project/logs/TICKET-100-planning-abcfe23f.log`
- cost: $3.27 of a $10 cap
- tokens: 46,170 out (24,478 thinking) · 66 in · 2,224,328 cache read · 100,118 cache write

### 2026-08-30 02:00:26Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned depends_on: human-owned frontmatter, start() waits like files_conflict, unsatisfiable or cyclic deps escalate

### 2026-08-30 02:07:33Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- section `## Reproduction` missing or empty
- ok: `tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first` fails as required
```
      .replace("---\n\n## Summary", "depends_on: TICKET-001\n---\n\n## Summary")
        path = d / ".project/tickets/TICKET-002.md"
        path.write_text(dependent)
    
        did, _ = supervisor.start(d, path, harness("fake"), {})
    
>       assert did is False, (
            "TICKET-002 declared depends_on: TICKET-001, which is still at "
            "`implementing`, but start() advanced it anyway -- nothing in "
            "start() reads a dependency field")
E       AssertionError: TICKET-002 declared depends_on: TICKET-001, which is still at `implementing`, but start() advanced it anyway -- nothing in start() reads a dependency field
E       assert True is False

tests/test_dispatch.py:2132: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-002: -> triage {'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.13s ===============================

```
- ok: `tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first` fails on base `main` too -- the bug is not already fixed upstream
```
hich is still at `implementing`, but start() advanced it anyway -- nothing in start() reads a dependency field
E       assert True is False

tests/test_dispatch.py:2132: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-002: -> triage {'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.43s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-dwfdy55c/base
      Built pipeline @ file:///tmp/pipeline-base-dwfdy55c/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 16ms

```

### 2026-08-30 02:07:33Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- section `## Reproduction` missing or empty

### 2026-08-30 · planning · result=ok

Fixed the one thing the gate named: `## Reproduction` was empty. It now
carries the test path, the command, the verbatim failure and the
`expect:` line the gate parses.

The gate's other checks passed, so I changed nothing else. The 13 steps,
the acceptance criteria, `## Decisions checked`, `## Decisions`,
`## Rollback` and `files_declared` are byte-identical to the rejected plan.
`## Summary` gained one paragraph recording this round.

`expect:` is `assert True is False`. It is a substring of the failing
output and carries no temp path, no object address and no ellipsis, so
`unmatchable()` (`pipeline/core/gate.py:143`) returns `None` for it.

Re-measured the baseline on `ticket/100` at `3f54d3e` before writing:

Command: `uv run --group dev pytest -q`

Output:
```
FAILED tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first
1 failed, 493 passed in 35.21s
```

The one failure is this ticket's repro test, which the `## Digest` baseline
line already records.

Out of scope, noted not fixed: the merge wait in `start()` still returns
False with no `waiting` reason. DEC-048 records that as a separate ticket.

### 2026-08-30 02:10:00Z · planning · session · session=db6f032d-26a2-44f8-80ca-76ebfe37539c

`planning` ran as session `db6f032d-26a2-44f8-80ca-76ebfe37539c`
- replay: `claude --resume db6f032d-26a2-44f8-80ca-76ebfe37539c`
- log: `.project/logs/TICKET-100-planning-db6f032d.log`
- cost: $1.15 of a $10 cap
- tokens: 7,958 out (2,420 thinking) · 38 in · 838,561 cache read · 52,801 cache write

### 2026-08-30 02:10:00Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ filled the empty ## Reproduction the gate rejected; plan unchanged, baseline re-measured

### 2026-08-30 02:10:37Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-30 02:07:33Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first` fails on base `main` too -- the bug is not already fixed upstream
```
hich is still at `implementing`, but start() advanced it anyway -- nothing in start() reads a dependency field
E       assert True is False

tests/test_dispatch.py:2132: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-002: -> triage {'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.43s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-giqmk7aw/base
      Built pipeline @ file:///tmp/pipeline-base-giqmk7aw/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 18ms

```

### 2026-08-30 · plan-validation · result=ok

**Tier B: PASS.** Eight items, each checked against the code the plan names.

- Root cause: `start()` consults one ordering, `conflict_holder()`
  (`pipeline/core/machine.py:305`) on `files_declared` against `inflight`. No
  frontmatter field states "TICKET-A first" and no code reads one. The plan
  adds the field, the reader and the wait. It fixes the cause.
- Decisions: verified in `.project/decisions/`. DEC-029 line 33 refuses
  serialising `files_conflict`; the plan leaves `files_conflict` untouched.
  DEC-048 line 24 requires write-on-change; step 7 keeps that guard. DEC-066
  requires one normaliser; step 2 adds `as_list()`. `grep -rln 'depends'` over
  `.project/decisions/` matched no file.
- Scope: 13 steps trace to the 9 criteria. No step is untraceable.
- Criteria: falsifiable. `pytest -k dep` exits `5` on no collection, so it is
  not vacuous. `git diff --stat main -- CLAUDE.md` is the weakest: it proves
  the file changed, not what it says.
- Research: verified `note_wait` (`supervisor.py:687`), `waiting_text`
  (`server.py:89`), `as_test_list` (`ticket.py:55`), the `new` subparser
  (`cli/main.py:681`), the replace chain (`cli/main.py:105`), `files_declared:
  []` in `templates/ticket.md`, the "Who fills it" table (`SKILL.md:16`).
- Riskiest step: 9, wiring into `start()` above the `new` advance. Guarded by
  `if t.extra.get("depends_on"):`, so a project declaring none runs no new
  code; `## Rollback` names the revert and its cost.
- Regression surface: `note_wait()` has one caller (`supervisor.py:774`).
  `waiting_text()`'s existing asserts (`tests/test_daemon.py:529,539-541`)
  survive the new guard. `CONTROL_FIELDS` has one consumer, `_finish`'s tamper
  check (`supervisor.py:1130`). `TICKET_TEMPLATE` has one reader plus an
  existence check (`tests/test_stages.py:241`); no test compares its text.
- Blast radius: `class: feature`, 13 files, 5 tests and 3 docs among them.

long: two observations that do not fail the plan, and one digest correction.

Digest correction: the digest puts the `new` advance at line 772 and the
ordering block at 776-780. They are at 768-770 and 772-776. The fact step 9
rests on holds -- the advance is ABOVE the ordering block.

Observation 1: a `new` ticket whose dependency lands keeps a stale `waiting`
dict for one tick. Step 9 returns above line 774's `note_wait(t, held)`, and
the `new` advance returns too. It clears next tick at `triage`. Display only,
per DEC-048.

Observation 2: `dep_unsatisfiable()` misses a cycle that is reachable but off
the walked path, because `seen` blocks re-entry. Given A->B, A->C, B->D, C->D,
D->B, the walk from A never reports the B/D cycle. It is not a hang: B and D
escalate on their own `start()` call, and A then reads a terminal dependency
and escalates too.

Unverified: I ran no test. The guard allows read-only commands only, and I did
not execute `uv run --group dev pytest -q`. Every finding above rests on
reading the code the plan names. The Tier A gate's own run is quoted in the
entry `2026-08-30 02:10:37Z · plan-validation · gate · verdict=PASS`.

### 2026-08-30 02:14:56Z · plan-validation · session · session=5b4ae2ff-1c95-48a9-8bfb-1c7626d6b34c

`plan-validation` ran as session `5b4ae2ff-1c95-48a9-8bfb-1c7626d6b34c`
- replay: `claude --resume 5b4ae2ff-1c95-48a9-8bfb-1c7626d6b34c`
- log: `.project/logs/TICKET-100-plan-validation-5b4ae2ff.log`
- cost: $1.79 of a $3 cap
- tokens: 20,640 out (9,460 thinking) · 40 in · 1,118,884 cache read · 71,124 cache write

### 2026-08-30 02:14:56Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B pass: every step names verified code, DEC-048/029/066 cited correctly, blast radius fits class feature

### 2026-08-30 10:35:03Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: SAFE_ID at ticket.py:28, CONTROL_FIELDS at machine.py:285, waiting_text's current file-only guard at server.py:91, as_test_list at ticket.py:55. Both ticket constraints honoured: a dependency that is missing, escalated, rejected or cyclic calls bail() with a named reason instead of parking forever, and the dispatcher WAITS like files_conflict rather than failing. Ownership is right -- depends_on is in CONTROL_FIELDS and in no CLAIMS entry, so a stage writing it escalates rather than being silently reverted, and the human filing the batch is who knows the order. The waiting key stays one shape, {on,file} for an overlap and {on,stage} for a dependency, so existing on-disk entries still render. dep_graph reads every ticket but only for a ticket that declares depends_on. FENCED: validate_meta and CONTROL_FIELDS -- this must park at awaiting-merge for a human diff, and I will not approve that gate.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: SAFE_ID at ticket.py:28, CONTROL_FIELDS at machine.py:285, waiting_text's current file-only guard at server.py:91, as_test_list at ticket.py:55. Both ticket constraints honoured: a dependency that is missing, escalated, rejected or cyclic calls bail() with a named reason instead of parking forever, and the dispatcher WAITS like files_conflict rather than failing. Ownership is right -- depends_on is in CONTROL_FIELDS and in no CLAIMS entry, so a stage writing it escalates rather than being silently reverted, and the human filing the batch is who knows the order. The waiting key stays one shape, {on,file} for an overlap and {on,stage} for a dependency, so existing on-disk entries still render. dep_graph reads every ticket but only for a ticket that declares depends_on. FENCED: validate_meta and CONTROL_FIELDS -- this must park at awaiting-merge for a human diff, and I will not approve that gate.**

### 2026-08-30 10:43:08Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-30 02:07:33Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first` fails on base `main` too -- the bug is not already fixed upstream
```
hich is still at `implementing`, but start() advanced it anyway -- nothing in start() reads a dependency field
E       assert True is False

tests/test_dispatch.py:2132: AssertionError
----------------------------- Captured stdout call -----------------------------
  TICKET-002: -> triage {'plan_steps': 1, 'plan_files': 1}
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_a_ticket_cannot_declare_that_another_must_land_first
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.45s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-srr_7hf5/base
      Built pipeline @ file:///tmp/pipeline-base-srr_7hf5/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```

### 2026-08-30 10:43:09Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-30 · implementing · result=ok

Executed all 13 plan steps with TDD: each new test verified RED for the
expected reason, then GREEN, one commit per step. `depends_on` is validated
(`as_list()`, `validate_meta()`), a control field (in `CONTROL_FIELDS`, no
`CLAIMS` entry), waited on by `start()` via `dep_holder()`, escalated by
`dep_unsatisfiable()` for a missing/terminal/cyclic dependency, rendered by
`waiting_text()`, and settable via `pipeline new --depends-on`.

Verified by temporarily disabling the `if t.extra.get("depends_on"):` block
in `start()`: `test_a_dependency_that_cannot_land_escalates_rather_than_waiting_forever`
and `test_ls_names_the_ticket_a_dependency_is_waiting_on` both failed for the
expected reason, then passed once restored.

All 9 acceptance criteria re-run individually and green. Full suite:
`uv run --group dev pytest -q` -> 501 passed, 0 failed. No refactor beyond
the plan's 13 steps. Diff touches `validate_meta()` and `CONTROL_FIELDS`, both
`FENCED` -- parks at `awaiting-merge` per the plan.

### 2026-08-30 10:52:37Z · implementing · session · session=cc645308-4ab9-46e2-8e99-5e7309c94357

`implementing` ran as session `cc645308-4ab9-46e2-8e99-5e7309c94357`
- replay: `claude --resume cc645308-4ab9-46e2-8e99-5e7309c94357`
- log: `.project/logs/TICKET-100-implementing-cc645308.log`
- cost: $2.72 of a $8 cap
- tokens: 28,082 out (1,584 thinking) · 228 in · 10,025,241 cache read · 108,037 cache write

### 2026-08-30 10:52:37Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented all 13 plan steps: depends_on validated, dep_holder/dep_unsatisfiable added, waiting/ls widened, start() waits/escalates on a declared dependency, pipeline new --depends-on, docs updated; full suite 501 passed.

### 2026-08-30 · review · result=ok

**No blocking finding.** Reviewed the delta `3f54d3e..baf730f`, 13 files. All
13 plan steps landed with no drift; every step's named file and function
matches the plan.

Verified fresh:
1. `uv run --group dev pytest -q` reports `501 passed in 35.28s`.
2. All 9 acceptance criteria run individually and pass: the 4 named node ids
   report `4 passed in 0.47s`, `tests/test_machine.py -k dep` reports
   `2 passed, 26 deselected`, `tests/test_ticket.py -k depends_on` reports
   `1 passed, 29 deselected`, `grep -c depends_on pipeline/templates/ticket.md`
   prints `1`, the SKILL.md grep prints `4`, and
   `git diff --stat main -- CLAUDE.md` prints `CLAUDE.md | 9 +++++++++`.
3. `./pipeline/hooks/test_dangerous_commands.py` reports `guard: all passed`.

Minor findings, none blocking:
1. minor -- `dep_unsatisfiable()`'s `seen` set skips a cycle off the walked
   path. Measured: `dep_unsatisfiable("A", {"A": ["B", "C"], "C": ["B"], "B":
   ["C"]}, ...)` returns `None`. Nothing hangs: `A` waits on `B`, `B`'s own
   `start()` returns `depends_on is a cycle: B -> C -> B` and escalates, then
   `A` escalates next tick because `B` is terminal and not `done`.
   `plan-validation` recorded this already.
2. minor -- a dependent's `waiting` is rewritten each time the dependency
   changes stage, which resets the file mtime `ticket_rows()` derives `stale`
   from (`pipeline/daemon/server.py:139`). A ticket blocked behind an
   advancing dependency never reads STALE. Bounded, because the dependency's
   own loops are bounded, and DEC-048's per-tick write is still avoided.
3. minor -- a `new` ticket keeps a stale `waiting` dict for one tick after its
   dependency lands: `advance()` (`pipeline/daemon/supervisor.py:804`) saves
   before any `note_wait(t, None)` clears it. It clears next tick at `triage`.
   `plan-validation` recorded this already.
4. nit -- `dep_holder()`'s `stages.get(dep, "?")` fallback is unreachable from
   `start()`: `dep_unsatisfiable()` returns `not a ticket in this project`
   first (`pipeline/daemon/supervisor.py:795`).

Dropped one candidate finding. An unsubstituted `{{depends_on}}` reaching YAML
is impossible: `TICKET_TEMPLATE` has one reader, `cmd_new`
(`pipeline/cli/main.py:109`), and it always substitutes.

This still parks at `awaiting-merge`. The diff touches `validate_meta()` and
`CONTROL_FIELDS`, both in `machine.FENCED`.

### 2026-08-30 10:58:07Z · review · session · session=22d90ac7-9eec-47a4-884d-121e7f23ffdd

`review` ran as session `22d90ac7-9eec-47a4-884d-121e7f23ffdd`
- replay: `claude --resume 22d90ac7-9eec-47a4-884d-121e7f23ffdd`
- log: `.project/logs/TICKET-100-review-22d90ac7.log`
- cost: $2.12 of a $7 cap
- tokens: 21,414 out (12,221 thinking) · 58 in · 1,659,553 cache read · 75,015 cache write

### 2026-08-30 10:58:07Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ review of 3f54d3e..baf730f found no blocking finding; 501 passed, all 9 acceptance criteria green, 4 minor notes appended

### 2026-08-30 10:58:45Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/core/machine.py:CONTROL_FIELDS`
- `pipeline/core/ticket.py:validate_meta`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-100` lands it; `pipeline resume TICKET-100 --stage planning` sends it back.

### 2026-08-30 11:07:39Z · human · approval · by=chezzijr (via Claude Code, while away; reviewed the fenced diff). validate_meta gains three lines matching the files_declared loop, checking depends_on against SAFE_ID (^TICKET-\d{1,6}$, anchored), so nothing from a ticket file reaches a shell through the field; as_test_list keeps its name and docstring and delegates to the new as_list. CONTROL_FIELDS gains one entry with its reason -- accepted consequence: a stage writing depends_on now escalates the ticket instead of being silently reverted, and a hand-edit under a live lease does too, so edit it at a gate like test_file. transition() is untouched and the two new functions are pure, below files_conflict. Checked the classic cycle bug: seen is marked after the dep-in-path test, so a diamond cannot mask a cycle. 253 insertions, 113 of them tests.

**approved by chezzijr (via Claude Code, while away; reviewed the fenced diff). validate_meta gains three lines matching the files_declared loop, checking depends_on against SAFE_ID (^TICKET-\d{1,6}$, anchored), so nothing from a ticket file reaches a shell through the field; as_test_list keeps its name and docstring and delegates to the new as_list. CONTROL_FIELDS gains one entry with its reason -- accepted consequence: a stage writing depends_on now escalates the ticket instead of being silently reverted, and a hand-edit under a live lease does too, so edit it at a gate like test_file. transition() is untouched and the two new functions are pure, below files_conflict. Checked the classic cycle bug: seen is marked after the dep-in-path test, so a diamond cannot mask a cycle. 253 insertions, 113 of them tests.**

### 2026-08-30 11:08:53Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
it merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/100


Rebasing (1/12)Rebasing (2/12)Rebasing (3/12)Rebasing (4/12)Rebasing (5/12)Rebasing (6/12)Rebasing (7/12)Rebasing (8/12)Rebasing (9/12)Rebasing (10/12)Rebasing (11/12)Rebasing (12/12)Successfully rebased and updated refs/heads/ticket/100.
Already up to date.
Updating c0c32b2..c590de6
Fast-forward
 CLAUDE.md                                      |  9 ++++
 pipeline/cli/main.py                           | 14 +++++--
 pipeline/core/machine.py                       | 42 ++++++++++++++++++-
 pipeline/core/ticket.py                        | 15 +++++--
 pipeline/daemon/server.py                      | 14 +++++--
 pipeline/daemon/supervisor.py                  | 49 ++++++++++++++++++----
 pipeline/templates/skills/file-ticket/SKILL.md | 16 +++++--
 pipeline/templates/ticket.md                   |  1 +
 tests/test_cli.py                              | 11 +++++
 tests/test_daemon.py                           |  8 ++++
 tests/test_dispatch.py                         | 58 ++++++++++++++++++++++++++
 tests/test_machine.py                          | 25 +++++++++++
 tests/test_ticket.py                           | 11 +++++
 13 files changed, 253 insertions(+), 20 deletions(-)

```

### 2026-08-30 11:08:53Z · merging · decision

decision recorded as `DEC-100`
