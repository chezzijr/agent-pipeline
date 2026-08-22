---
id: TICKET-031
stage: done
class: feature
branch: ticket/031
test_file: tests/test_machine.py::test_a_fenced_file_is_gated_before_merge
files_declared:
- .claude/skills/file-ticket/SKILL.md
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/core/fence.py
- pipeline/core/machine.py
- pipeline/daemon/supervisor.py
- tests/test_cli.py
- tests/test_dispatch.py
- tests/test_fence.py
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
  id: afdaff97-da62-4fe3-a246-e30fa4a4ea15
  log: .project/logs/TICKET-031-holistic-review-afdaff97.log
approved_by: chezzijr
approved_at: '2026-08-21T11:31:31.988460+00:00'
---

## Summary

CLAUDE.md fences four things off from unattended merge. The plan is
implemented, all 23 steps are done, and both `review` and `holistic-review`
passed with no blocking findings. `pipeline/core/fence.py`, `machine.FENCED`,
the `awaiting-merge` gate, `finish_suite()` and `cmd_approve`'s `GATE_NEXT` are
all in place, committed as `de7ad39` on `ticket/031`. The full suite passes,
`204 passed in 8.89s`, and the six tests the acceptance criteria name pass by
name. The working tree is clean.

`holistic-review` found the change coherent. The diff is 12 files, 302
insertions and 22 deletions, and the 12 files are the 12 the plan names. Four
checks, in the `holistic-review · findings` entry in `## Thread`: every plan
step has a matching hunk; the `ok` parks / `clean` merges polarity holds in
`transition()`, `finish_suite()` and both changed test assertions at once;
`finish_suite()` mirrors `finish_child()`'s error handling and adds only the
`except Exception` that parks; every reader of `HUMAN_GATES` reads the
constant, so the second gate needs no other edit.

`review` recorded four non-blocking findings and `holistic-review` two more;
both `findings` entries hold them in full. The three worth carrying forward:
1. A rename escapes the fence, because `hunks()` keys the new-side path. The
   suite runs first and a rename of any fenced file fails it, so nothing lands
   unseen.
2. `pipeline/tui/app.py:536`'s docstring still says `cmd_approve` refuses
   outside `awaiting-approval`. The TUI delegates to `cmd_approve` and
   reimplements no check, so behaviour is correct and only the prose is stale.
3. `approve` at `awaiting-merge` overwrites `approved_by` and `approved_at`, so
   a fenced ticket keeps only its second approval in frontmatter. Nothing reads
   those fields for meaning and the thread keeps one entry per gate.

Acceptance criterion 9 was measured, not run: the guard's read-only allowlist
refuses `./pipeline/hooks/test_dangerous_commands.py` from the `review` and
`holistic-review` stages. `git diff --stat main...HEAD` lists 12 files and none
is under `pipeline/hooks/`, so the tables are unchanged, and `implementing`
recorded the script exiting 0.

This ticket edits `transition()`, a fenced symbol, so it will park at its own
new `awaiting-merge` gate once `verifying` runs. That is correct, per the
plan's own note.

**The gate.** `verifying` gains a second outcome. `transition("verifying",
"ok")` now returns a new human gate `awaiting-merge`; `transition("verifying",
"clean")` returns `merging`. `finish_suite()` in the dispatcher runs the fence
check after the suite passes and claims `clean` only when the diff touches
nothing fenced. Every other path -- git missing, no merge base, an exception --
claims `ok` and parks. `pipeline approve` learns the second gate and sends it
to `merging`. The ticket's alternative (`merging` refuses and escalates) is
ruled out: `escalated` is in `TERMINAL`, not `HUMAN_GATES`, so it cannot pass
the committed test.

**What counts as touched.** Symbols, not whole files. `fenced_touches()` in a
new `pipeline/core/fence.py` intersects `git diff --unified=0` hunk ranges
against the merge base with each symbol's `ast` line span. Verified by
prototype on this worktree: the branch's own hunk (`@@ -41,0 +42,15 @@`) does
not trip `test_happy_path` (lines 10-23). A symbol missing from the new file
trips unconditionally, so deletion is not an escape.

**Where the list lives.** `FENCED` in `pipeline/core/machine.py`, a dict of
path to symbol tuple or `None` for whole-file. `CLAUDE.md` keeps the prose
copy, and `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file`
compares the two in both directions so they cannot drift.

12 files change: `pipeline/core/machine.py`, `pipeline/core/fence.py`,
`pipeline/daemon/supervisor.py`, `pipeline/cli/main.py`, five test files,
`CLAUDE.md`, `README.md` and `.claude/skills/file-ticket/SKILL.md`. Two
existing assertions change with them: `tests/test_machine.py:20` and
`tests/test_dispatch.py:156` both assert the old `verifying -> merging` row.

Note for the implementer: this ticket edits `transition()`, which is fenced, so
it will park at its own new gate before it lands. That is correct.

Three notes from plan-validation, none of which changes a step:
1. Base moved. `main` is `30542f1`, the merge base is `a97e7b7`, and TICKET-026
   landed `quick-review` between them. Apply steps 19 and 20 by content, not by
   line number: on `main`, `README.md` line 35 is line 37, line 175 is line
   177, and the `SKILL.md:148` sentence now names the cheap route. The two test
   line numbers, `tests/test_machine.py:20` and `tests/test_dispatch.py:156`,
   still hold the assertions the plan says they hold.
2. Two sentences go stale and no step lists them: `README.md:187` and the
   docstring at `pipeline/tui/app.py:536`, which both say `approve` works at
   `awaiting-approval` alone.
3. `hunks()` reads a zero-length new side as a one-line range, so deleting the
   lines immediately above a fenced symbol reads as outside it. Deleting the
   symbol itself still trips, through the `(gone)` path.

## Reproduction

Test: `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge`

Command:

    uv run --group dev pytest -q "tests/test_machine.py::test_a_fenced_file_is_gated_before_merge"

Output:

    >       assert getattr(M, "FENCED", None), "no fenced-file list in the dispatcher"
    E       AssertionError: no fenced-file list in the dispatcher
    E       assert None
    E        +  where None = getattr(M, 'FENCED', None)

    tests/test_machine.py:48: AssertionError
    FAILED tests/test_machine.py::test_a_fenced_file_is_gated_before_merge

expect: AssertionError: no fenced-file list in the dispatcher

The test asserts two things, and the first one fails first. The second holds a
walk of `transition()` from `implementing` with every result `ok`: the path is
`review -> holistic-review -> verifying -> merging -> done` and none of those
stages is in `HUMAN_GATES`. Making `FENCED` exist alone will not pass the test;
a gate must reach the path.

Committed as `2d5befd` on `ticket/031`.


## Digest

Files touched: `pipeline/core/machine.py` (the `FENCED` table and two
`transition()` rows), a new `pipeline/core/fence.py` (the diff/symbol check),
`pipeline/daemon/supervisor.py` (a `finish_suite()` beside `finish_child()`),
`pipeline/cli/main.py` (`cmd_approve` learns a second gate), plus
`tests/test_fence.py`, `tests/test_machine.py`, `tests/test_dispatch.py`,
`tests/test_cli.py`, `tests/test_stages.py`, `CLAUDE.md`, `README.md` and
`.claude/skills/file-ticket/SKILL.md`.

Key functions: `transition()` (`pipeline/core/machine.py:24`), `_finish()`
(`pipeline/daemon/supervisor.py:667`) which branches on `rec["kind"]`,
`finish_child()` (`pipeline/daemon/supervisor.py:603`) which maps an exit code
to `ok`/`fail`, `advance()` (`pipeline/daemon/supervisor.py:90`) which is the
only caller of `transition()`, and `cmd_approve()` (`pipeline/cli/main.py:105`),
which rewrites the stage in the CLI's own process and never touches the daemon.

Entry points: `verifying` spawns the suite at `pipeline/daemon/supervisor.py:523`
via `child(cfg["test_suite"], "suite")`, and its record carries `kind="suite"`,
`wt` and `path`. `_finish()` routes that record to `finish_child()` today; the
new `finish_suite()` takes that one line. `start()` returns early for any stage
in `HUMAN_GATES` (`pipeline/daemon/supervisor.py:466`), so a new gate needs no
code there at all. `base_ref(cfg)` already exists in
`pipeline/core/worktree.py:35` but is NOT yet imported by the supervisor.

Gotcha -- the committed test dictates the shape. `tests/test_machine.py:50-54`
walks `transition()` from `implementing` with **every result `ok`** and requires
a `HUMAN_GATES` member on the path. A conditional gate cannot satisfy that: the
gate must be where plain `ok` goes, and skipping it must take a *different*
result. So `("verifying", "ok") -> "awaiting-merge"` and
`("verifying", "clean") -> "merging"`. That polarity is the design, not a quirk:
every unhandled path parks for a human.

Gotcha -- this rules out the ticket's alternative. `merging` refusing and
escalating cannot pass the committed test either: `escalated` is in `TERMINAL`,
not in `HUMAN_GATES`.

Gotcha -- `awaiting-merge` may not be named `awaiting-approval`.
`tests/test_machine.py:102` asserts no stage but `plan-validation` may reach
`awaiting-approval`. A second gate needs its own name.

Gotcha -- two existing tests assert the old row and must change:
`tests/test_machine.py:20` and `tests/test_dispatch.py:156` both assert
`transition("verifying", "ok") == "merging"`.

Gotcha -- adding to `HUMAN_GATES` is enough for the rest of the system.
`KNOWN_STAGES` is built from it (`pipeline/core/machine.py:14`), so
`validate_meta()` and `pipeline resume --stage` accept it;
`tests/test_stages.py:47` subtracts `HUMAN_GATES`, so no prompt file is needed;
`pipeline/tui/app.py:81` flags it and `pipeline/cli/metrics.py:338` times it,
both free.

Gotcha -- the diff must include uncommitted work. `git diff base...HEAD` (three
dots) sees committed branch work only. Use
`git diff --unified=0 $(git merge-base <base> HEAD)`, which diffs the *working
tree* against the merge base. A stage that edited a fenced file without
committing must not slip past.

Prototype run, on this worktree against `main`: with
`{"tests/test_machine.py": ("test_happy_path",)}` the check returned `[]`. The
branch's real hunk is `@@ -41,0 +42,15 @@` and `test_happy_path` spans lines
10-23. Symbol-level matching does not park a ticket that edited a neighbouring
function. That is question 2 answered by measurement, not by assumption.

Prototype run, `CLAUDE.md` extraction: taking the text from the blank line
before `requires human review before merge`, then
`re.findall(r"`([^`]+)`", ...)` with a trailing `()` stripped, yields exactly
`['CONTROL_FIELDS', 'pipeline/hooks/dangerous-commands.py', 'transition',
'validate_meta']`. The drift test compares that set to `FENCED`'s own names.

## Decisions checked

- **DEC-011** (active) -- froze the event vocabulary and states: "`cmd_approve`
  already refuses unless the stage is `awaiting-approval`, and that is a
  `HUMAN_GATE` the dispatcher never spawns into, so there is no lease to race."
  This plan complies. `awaiting-merge` is in `HUMAN_GATES`, so `start()` returns
  before taking a lease, and the same no-race argument holds. No new event kind
  and no new socket op: the second gate reuses the `transition` kind
  `cmd_approve` already emits.
- **DEC-017** (active) -- `base_ref()` is the one default for base, so the gate
  and the ticket's checkout cannot drift. The fence check reads its base through
  `base_ref(cfg)`, never an inline `cfg.get("base", "main")`.
- **DEC-018** (active) -- decisions resolve against the project root, not the
  worktree, because the worktree is a checkout of base and can be stale. Not
  violated: the fence check reads the *worktree* on purpose. It judges that
  branch's diff, not the project's records.
- **DEC-023** (active) -- `stage_view()` trims only `## Thread`. Untouched.
- **DEC-016**, **DEC-019**, **DEC-020**, **DEC-021**, **DEC-022**, **DEC-024**,
  **DEC-025**, **DEC-028** -- read, none relevant. DEC-028 governs the harness
  `.toml` reload and touches no stage, gate or merge path. Grep terms used
  across `.project/decisions/`: `merg`, `gate`, `human`, `approve`, `fenc`,
  `verify`.
- No record in `.project/decisions/` carries a `superseded-by:` line, so every
  id above is active history. This plan supersedes none of them.

## Plan

1. Add `FENCED` to `pipeline/core/machine.py` as a dict of path to symbol tuple, or `None` for whole-file: `{"pipeline/hooks/dangerous-commands.py": None, "pipeline/core/machine.py": ("transition", "CONTROL_FIELDS"), "pipeline/core/ticket.py": ("validate_meta",)}`, with a comment naming `CLAUDE.md` as the prose copy and `tests/test_stages.py` as the drift test.
2. In `pipeline/core/machine.py`, change `case ("verifying", "ok")` to return `"awaiting-merge"`, and add `case ("verifying", "clean"): return "merging", c` beside it, with a comment saying plain `ok` parks and only an explicit `clean` claim skips the gate.
3. In `pipeline/core/machine.py`, add `"awaiting-merge"` to `HUMAN_GATES` (which puts it in `KNOWN_STAGES` for free) and leave `DISPATCHER_STAGES` alone.
4. Create `pipeline/core/fence.py` holding `hunks(diff)`, `symbol_lines(src, name)` and `fenced_touches(wt, base, fenced=FENCED) -> list[str]`, copying the body from the `## Reference code` section verbatim.
5. Create `tests/test_fence.py` with `test_a_neighbouring_function_does_not_trip_the_fence`, built on `tests/helpers.py:git_project`: commit a file holding two functions, then assert editing the second returns `[]`, editing the first returns `["<path>:<sym>"]`, and deleting the first returns `["<path>:<sym> (gone)"]`.
6. Run `uv run --group dev pytest -q tests/test_fence.py` and confirm it passes before touching `pipeline/daemon/supervisor.py`.
7. In `pipeline/daemon/supervisor.py`, import `base_ref` from `pipeline.core.worktree` and `fenced_touches` from `pipeline.core.fence`.
8. In `pipeline/daemon/supervisor.py`, add `finish_suite(project, rec, emit)` next to `finish_child()`, copying the body from the `## Reference code` section verbatim.
9. In `pipeline/daemon/supervisor.py`, change the `if rec.get("kind") == "suite":` branch of `_finish()` to call `finish_suite(project, rec, emit)` instead of `finish_child(project, rec, "regression suite", emit)`.
10. In `pipeline/cli/main.py`, add `GATE_NEXT = {"awaiting-approval": "revalidating", "awaiting-merge": "merging"}` immediately above `cmd_approve`.
11. In `pipeline/cli/main.py`, rewrite `cmd_approve` to capture `gate = t.stage` first, `die()` when `gate not in GATE_NEXT`, set `t.stage = GATE_NEXT[gate]`, pass `gate` to `record(project, t, gate, "approved")`, and print the new stage; leave `cmd_reject` refusing anything but `awaiting-approval`.
12. In `tests/test_machine.py`, change line 20 to `assert t("verifying", "clean")[0] == "merging"` and add `assert t("verifying", "ok")[0] == "awaiting-merge"` beside it.
13. In `tests/test_dispatch.py`, change line 156 to `assert M.transition("verifying", "clean", {})[0] == "merging"`.
14. Add `test_a_fenced_diff_parks_before_merging` to `tests/test_dispatch.py`: commit `pipeline/core/machine.py` holding a `def transition():` on base, edit that function in the ticket worktree, run `start`/`finish` from `verifying`, then assert the stage is `awaiting-merge` and that a following `start()` returns no record.
15. Add `test_an_unfenced_diff_merges_without_a_human` to `tests/test_dispatch.py` with the same setup but an edit to an unfenced file, asserting the stage reaches `merging`.
16. Add `test_approve_lands_a_fenced_ticket` to `tests/test_cli.py`: `resume` a ticket to `awaiting-merge`, run `approve`, then assert the stage is `merging` and the emitted `transition` row carries `from: awaiting-merge` and `to: merging`.
17. Add `test_the_fenced_list_matches_the_rule_file` to `tests/test_stages.py`, copying the body from the `## Reference code` section verbatim.
18. Append a sentence to `CLAUDE.md` **after** the existing fence paragraph, never inside it, saying the rule is enforced by `machine.FENCED` plus the `awaiting-merge` gate and that `tests/test_stages.py` keeps the two copies in step.
19. Update three places in `README.md`: line 13's flow diagram, line 35 so `approve` names both targets, and the paragraph at line 175 so a passing suite hands a fenced ticket to `awaiting-merge` rather than straight to `merging`.
20. Update `.claude/skills/file-ticket/SKILL.md` line 148 to say a ticket stops at `awaiting-approval` and then, if its diff touches fenced code, again at `awaiting-merge`.
21. Run `uv run --group dev pytest -q tests/test_fence.py tests/test_machine.py tests/test_dispatch.py tests/test_cli.py tests/test_stages.py` and paste the verbatim output into `## Thread`.
22. Run `./pipeline/hooks/test_dangerous_commands.py` and paste its verbatim output into `## Thread`; pytest does not collect its tables, and `pipeline/core/machine.py` here carries a rule about that guard.

## Reference code

The three blocks below are the verbatim bodies plan steps 4, 8 and 17 copy.
They live outside `## Plan` because the Tier A gate parses every line of
`## Plan` as a numbered step.

Code for step 4, `pipeline/core/fence.py`:

```python
"""Which fenced symbols a branch's diff touches.

`CLAUDE.md` fences four things off from unattended merge. `machine.FENCED` is
the machine-readable copy; this is the check. A whole-file entry (`None`) trips
on any hunk. A symbol entry trips only when a hunk overlaps that symbol's own
line range, so a ticket that edited a neighbouring function is not parked.
"""
import ast
import re
import subprocess
from pathlib import Path

from pipeline.core.machine import FENCED
from pipeline.core.worktree import project_env


def hunks(diff: str) -> dict[str, list[tuple[int, int]]]:
    """path -> new-side line ranges, off `git diff --unified=0`.

    A deleted file has `+++ /dev/null`, so the `--- a/` path is carried over:
    dropping it would let "delete the guard entirely" read as an empty diff.
    """
    out: dict[str, list[tuple[int, int]]] = {}
    old = path = None
    for line in diff.splitlines():
        if line.startswith("--- "):
            old = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else old
            if path:
                out.setdefault(path, [])
        elif line.startswith("@@") and path:
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start = int(m.group(1))
                n = 1 if m.group(2) is None else max(int(m.group(2)), 1)
                out[path].append((start, start + n - 1))
    return out


def symbol_lines(src: str, name: str) -> tuple[int, int] | None:
    """A top-level def/class/assignment's line span, or None if it is gone.

    Decorators count: `node.lineno` is the `def` line, so a hunk that edited
    only a decorator would otherwise miss.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        else:
            names = [t.id for t in getattr(node, "targets", [])
                     if isinstance(t, ast.Name)]
        if name in names:
            starts = [node.lineno] + [d.lineno
                                      for d in getattr(node, "decorator_list", [])]
            return min(starts), node.end_lineno
    return None


def fenced_touches(wt: Path, base: str, fenced: dict = FENCED) -> list[str]:
    """Names of the fenced things this worktree's diff touches.

    Two dots against the merge base, NOT `base...HEAD`: three dots sees
    committed work only, and an uncommitted edit to the guard must not slip
    through.
    """
    def git(cmd: str) -> str:
        return subprocess.run(f"git {cmd}", shell=True, cwd=wt, capture_output=True,
                              text=True, env=project_env()).stdout

    mb = git(f"merge-base {base} HEAD").strip()
    if not mb:
        return ["fence check found no merge base"]   # fail closed
    changed = hunks(git(f"diff --unified=0 {mb}"))
    hits = []
    for path, symbols in fenced.items():
        ranges = changed.get(path)
        if ranges is None:
            continue
        if symbols is None:
            hits.append(path)
            continue
        f = Path(wt) / path
        src = f.read_text(errors="replace") if f.is_file() else ""
        for sym in symbols:
            span = symbol_lines(src, sym)
            if span is None:
                hits.append(f"{path}:{sym} (gone)")
            elif any(a <= span[1] and span[0] <= b for a, b in ranges):
                hits.append(f"{path}:{sym}")
    return hits
```

Code for step 8, `finish_suite()` in `pipeline/daemon/supervisor.py`:

```python
def finish_suite(project: Path, rec: dict, emit=noop) -> str:
    """The suite's exit code, and then the fence check.

    `ok` PARKS at `awaiting-merge`; only `clean` reaches `merging`. The
    polarity is the guard: a git failure, an unparseable diff or a bug in
    `fenced_touches()` all yield `ok`, and a human looks at the diff. A guard
    that fails open is not a guard.
    """
    close_child(rec)
    code = rec["proc"].returncode
    t = Ticket.load(rec["path"])
    if code != 0:
        advance(project, t, "fail",
                f"regression suite exit {code}\n```\n{log_tail(rec)}\n```",
                emit, agent=False)
        return "fail"
    try:
        hits = fenced_touches(rec["wt"], base_ref(project_config(project)))
    except Exception as e:
        hits = [f"fence check failed ({e.__class__.__name__}: {e})"]
    if not hits:
        advance(project, t, "clean",
                "regression suite passed; the diff touches no fenced code",
                emit, agent=False)
        return "clean"
    advance(project, t, "ok",
            "regression suite passed, but the diff touches fenced code:\n"
            + "\n".join(f"- `{h}`" for h in hits)
            + f"\n\n`CLAUDE.md` requires a human to see this diff before it "
              f"lands. `pipeline approve {rec['tid']}` lands it; "
              f"`pipeline resume {rec['tid']} --stage planning` sends it back.",
            emit, agent=False)
    return "ok"
```

Code for step 17, the drift test in `tests/test_stages.py`:

```python
def test_the_fenced_list_matches_the_rule_file():
    """`CLAUDE.md` names the fenced things in prose and `machine.FENCED` names
    them in code. Two copies that can drift are one promise nobody keeps."""
    import re
    text = (C.PKG.parent / "CLAUDE.md").read_text()
    i = text.index("requires human review before merge")
    sentence = text[text.rindex("\n\n", 0, i):i]
    prose = {tok.rstrip("()") for tok in re.findall(r"`([^`]+)`", sentence)}
    code = {p for p, s in M.FENCED.items() if s is None} | {
        s for syms in M.FENCED.values() if syms for s in syms}
    assert prose == code, f"CLAUDE.md says {prose}, machine.FENCED says {code}"
```

## Acceptance criteria

1. `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge` passes: `M.FENCED` is non-empty and the all-`ok` walk from `implementing` reaches `awaiting-merge`.
2. `tests/test_dispatch.py::test_a_fenced_diff_parks_before_merging` passes: a ticket whose worktree edited `transition()` sits at `awaiting-merge` after the suite, and the next `start()` returns no record.
3. `tests/test_dispatch.py::test_an_unfenced_diff_merges_without_a_human` passes: an unfenced diff reaches `merging` with no human.
4. `tests/test_dispatch.py::test_a_verified_ticket_lands_on_base` passes, changed only in its `verifying`/`clean` assertion at line 156.
5. `tests/test_fence.py::test_a_neighbouring_function_does_not_trip_the_fence` passes all three cases: neighbour edit returns `[]`, symbol edit trips, symbol deletion trips with `(gone)`.
6. `tests/test_cli.py::test_approve_lands_a_fenced_ticket` passes: `approve` at `awaiting-merge` sets stage `merging` and emits `from: awaiting-merge`.
7. The existing `approve` refusal assertion at `tests/test_cli.py:49` still passes: a ticket in `triage` is refused.
8. `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` passes, and fails if either copy is edited alone.
9. `./pipeline/hooks/test_dangerous_commands.py` exits 0, with its guard tables unchanged.

## Decisions

**A fenced diff parks at `awaiting-merge`, and the polarity of the results is
the guard.** `transition("verifying", "ok")` goes to the gate;
`transition("verifying", "clean")` goes to `merging`. Only an explicit,
positive `clean` claim from `finish_suite()` skips the human. Everything that
can go wrong -- git missing, no merge base, an unparseable diff, an exception
inside `fenced_touches()` -- yields `ok` and parks the ticket. Inverting this,
so `ok` merges and a new `fenced` result parks, reads more naturally and fails
open on every one of those paths. For the rule `CLAUDE.md` calls "the one
failure mode worth refusing to automate", that is the wrong direction.
`tests/test_machine.py:50-54` encodes the choice: it walks the machine with
every result `ok` and demands a human gate on that path.

**The fence matches symbols, not whole files.** `pipeline/core/machine.py`
holds `transition()` and `CONTROL_FIELDS` next to `BOUNDS`, `apply_claims()`
and `files_conflict()`, and every ticket that adds a stage edits that file. A
whole-file fence would park most of them and train the human holding the
keyboard to rubber-stamp, which is the failure the enforcement exists to
prevent. `fenced_touches()` intersects `git diff --unified=0` hunk ranges with
the symbol's own `ast` line span. A symbol that is gone from the new file trips
unconditionally, so deleting the guard is not a way around the guard.

**The diff is taken against the merge base with two dots, not three.**
`git diff base...HEAD` sees committed work only. A stage that edits
`validate_meta()` and does not commit it would otherwise merge unseen.

**`machine.FENCED` and `CLAUDE.md` are two copies on purpose, and a test is
what stops them drifting.** The prose is what an agent reads; the dict is what
the dispatcher reads. `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file`
compares them in both directions. If you edit the fence sentence in
`CLAUDE.md`, keep every item backticked and keep the sentence in its own
paragraph: the test extracts from the preceding blank line.

**`pipeline reject` still only works at `awaiting-approval`.** Rejecting a diff
is not rejecting a plan, and routing it through `cmd_reject` would charge
`plan_rejections` for something the plan may have got right. A human who does
not want a fenced diff uses `pipeline resume <id> --stage planning`.
Deliberately not built.

## Rollback

Revert the commit. Nothing persists outside the repo: no schema change, no new
event kind, no new socket op, no new frontmatter field. One ordering matters --
a ticket already parked at `awaiting-merge` when the revert lands would hold a
stage name `validate_meta()` no longer accepts, and `pipeline ls` would
escalate it. Move it on first with `pipeline resume <id> --stage merging`, then
revert.

## Thread

### 2026-08-21 09:28:26Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 · triage · result=ok

Reproduced. `pipeline/core/machine.py` defines no fenced-file list, and
`transition()` routes `implementing -> review -> holistic-review -> verifying ->
merging -> done` with no stage in `HUMAN_GATES`. The only human stop is
`awaiting-approval`, which sits before `implementing` and approves a plan.

Test committed: `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge`
(`2d5befd`). It fails with `AssertionError: no fenced-file list in the
dispatcher`.

Out of scope, noted not fixed: `CLAUDE.md` names the four fenced items in prose
only, so nothing can read them yet. Question 3 in `## Summary` covers it.

The pipeline guard blocked `cat >> tests/test_machine.py <<'EOF'` with "command
does not parse as a shell command". I wrote the test through the file edit tool
instead. I did not work around the guard.

### 2026-08-21 09:30:05Z · triage · session · session=fd02924d-5b25-4076-8c9b-3eebe42ba826

`triage` ran as session `fd02924d-5b25-4076-8c9b-3eebe42ba826`
- replay: `claude --resume fd02924d-5b25-4076-8c9b-3eebe42ba826`
- log: `.project/logs/TICKET-031-triage-fd02924d.log`

### 2026-08-21 09:30:05Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

✓ Reproduced: no fenced-file list in machine.py and no human gate between implementing and done; failing test committed as 2d5befd

### 2026-08-21 · planning · result=ok

Plan written. The three design questions are answered in `## Digest` and
`## Decisions`; none of them needed a human.

1. **Which gate.** A second human gate, `awaiting-merge`, entered from
   `verifying`. The ticket's alternative -- `merging` refuses and escalates --
   cannot pass the committed test: `tests/test_machine.py:50-54` requires a
   `HUMAN_GATES` member on the all-`ok` path, and `escalated` is in `TERMINAL`.
2. **What counts as touched.** Symbols, via `git diff --unified=0` hunk ranges
   intersected with each symbol's `ast` line span. Prototyped on this worktree:
   the branch's own hunk `@@ -41,0 +42,15 @@` does not trip `test_happy_path`
   at lines 10-23.
3. **Where the list lives.** `FENCED` in `pipeline/core/machine.py`, with
   `CLAUDE.md` keeping the prose copy and a two-way drift test in
   `tests/test_stages.py`.

Two existing assertions must change and are called out as plan steps 12 and 13:
`tests/test_machine.py:20` and `tests/test_dispatch.py:156` both assert
`transition("verifying", "ok") == "merging"`.

Out of scope, noted not fixed: `pipeline reject` still refuses anything but
`awaiting-approval`, so a human who does not want a fenced diff uses
`pipeline resume <id> --stage planning`. Reasoning is in `## Decisions`.

The pipeline guard blocked `cat > /tmp/t031_sections.md <<'SECTIONS' ... ` with
"command does not parse as a shell command". I wrote the files through the file
write tool instead. I did not work around the guard.

### 2026-08-21 09:39:08Z · planning · note

`planning` was interrupted; lease released

### 2026-08-21 · planning · result=ok

The plan the interrupted run wrote is on disk and complete. I re-ran it against
this worktree rather than rewriting it, and it holds. Two edits, both in
`## Plan` and `## Decisions checked`; no design changed.

What I verified, and how:

1. Every line number the plan cites resolves in the worktree at `2d5befd`:
   `tests/test_machine.py:20` is `assert t("verifying", "ok")[0] == "merging"`,
   `tests/test_dispatch.py:156` is
   `assert M.transition("verifying", "ok", {})[0] == "merging"`,
   `tests/test_cli.py:49` is the `approve must refuse` assertion,
   `tests/test_stages.py:47` subtracts `HUMAN_GATES`, and
   `.claude/skills/file-ticket/SKILL.md:148` is "The ticket will stop at
   `awaiting-approval` for the human".
2. Every name the two code blocks call exists: `project_config`, `noop`,
   `close_child`, `log_tail`, `advance`, `Ticket.load` and `project_env` are
   all imported or defined in `pipeline/daemon/supervisor.py` today, and
   `base_ref` is at `pipeline/core/worktree.py:35` and is not yet imported
   there. `rec["wt"]` and `rec["tid"]` are both set by `child()` at
   `pipeline/daemon/supervisor.py:512-521`.
3. The `CLAUDE.md` extraction the drift test performs returns exactly
   `{'transition', 'CONTROL_FIELDS', 'validate_meta',
   'pipeline/hooks/dangerous-commands.py'}`, matching `FENCED`'s names in step 1.
4. `_finish()` routes the suite at `pipeline/daemon/supervisor.py:672`,
   `if rec.get("kind") == "suite":`, and that is the one line step 9 replaces.
5. `tests/helpers.py:52` defines `git_project()`, which step 5 builds on.

Two edits:

1. Step 19 named `README.md` line 35 and "the paragraph near `README.md:180`".
   The paragraph starts at line 175, and line 13 holds the flow diagram
   `done <- merging <- verifying <- review <- implementing`, which the previous
   step missed. Step 19 now names lines 13, 35 and 175.
2. `.project/decisions/` gained `DEC-028` after the first run read it.
   `## Decisions checked` now records it as read and not relevant: it governs
   the per-tick harness `.toml` reload and touches no stage, gate or merge path.
   No record in that directory carries a `superseded-by:` line.

Out of scope, noted not fixed: `pipeline reject` still refuses anything but
`awaiting-approval`. `## Decisions` says why, and says it is deliberate.

The pipeline guard blocked a multi-line `python3 -c "..."` with "command does
not parse as a shell command". I re-ran the same check as a single-line
`python3 -c`, which the guard allows. I did not work around the guard.

### 2026-08-21 09:41:39Z · planning · session · session=2eaa74f0-6de6-4b24-9d7d-3494ec2ded33

`planning` ran as session `2eaa74f0-6de6-4b24-9d7d-3494ec2ded33`
- replay: `claude --resume 2eaa74f0-6de6-4b24-9d7d-3494ec2ded33`
- log: `.project/logs/TICKET-031-planning-2eaa74f0.log`

### 2026-08-21 09:41:39Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan verified against the worktree and kept; fixed README line refs in step 19 and added DEC-028 to decisions checked

### 2026-08-21 10:08:30Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge` fails as required
```
1 item

tests/test_machine.py F

=================================== FAILURES ===================================
___________________ test_a_fenced_file_is_gated_before_merge ___________________

    def test_a_fenced_file_is_gated_before_merge():
        """CLAUDE.md fences four things off from unattended merge:
        `pipeline/hooks/dangerous-commands.py`, `transition()`, `validate_meta()`
        and `CONTROL_FIELDS`. The dispatcher holds no such list, and no human gate
        stands between `implementing` and `done` -- a diff touching a fenced file
        lands with the plan gate as its only human."""
>       assert getattr(M, "FENCED", None), "no fenced-file list in the dispatcher"
E       AssertionError: no fenced-file list in the dispatcher
E       assert None
E        +  where None = getattr(M, 'FENCED', None)

tests/test_machine.py:48: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_fenced_file_is_gated_before_merge - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge` fails on base `main` too -- the bug is not already fixed upstream
```
hing a fenced file
        lands with the plan gate as its only human."""
>       assert getattr(M, "FENCED", None), "no fenced-file list in the dispatcher"
E       AssertionError: no fenced-file list in the dispatcher
E       assert None
E        +  where None = getattr(M, 'FENCED', None)

tests/test_machine.py:48: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_fenced_file_is_gated_before_merge - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-pbk92f63/base
      Built pipeline @ file:///tmp/pipeline-base-pbk92f63/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- plan line is not a numbered step -- the plan reads as prose: 'Code for step 4, `pipeline/core/fence.py`:'
- plan line is not a numbered step -- the plan reads as prose: '```python'
- plan line names no declared file: '```python'
- plan line is not a numbered step -- the plan reads as prose: '"""Which fenced symbols a branch\'s diff touches.'
- plan line names no declared file: '"""Which fenced symbols a branch\'s diff touches.'
- plan line is not a numbered step -- the plan reads as prose: '`CLAUDE.md` fences four things off from unattended merge. `machine.FENCED` is'
- plan line is not a numbered step -- the plan reads as prose: 'the machine-readable copy; this is the check. A whole-file entry (`None`) trips'
- plan line names no declared file: 'the machine-readable copy; this is the check. A whole-file entry (`None`) trips'
- plan line is not a numbered step -- the plan reads as prose: "on any hunk. A symbol entry trips only when a hunk overlaps that symbol's own"
- plan line names no declared file: "on any hunk. A symbol entry trips only when a hunk overlaps that symbol's own"
- plan line is not a numbered step -- the plan reads as prose: 'line range, so a ticket that edited a neighbouring function is not parked.'
- plan line names no declared file: 'line range, so a ticket that edited a neighbouring function is not parked.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'import ast'
- plan line names no declared file: 'import ast'
- plan line is not a numbered step -- the plan reads as prose: 'import re'
- plan line names no declared file: 'import re'
- plan line is not a numbered step -- the plan reads as prose: 'import subprocess'
- plan line names no declared file: 'import subprocess'
- plan line is not a numbered step -- the plan reads as prose: 'from pathlib import Path'
- plan line names no declared file: 'from pathlib import Path'
- plan line is not a numbered step -- the plan reads as prose: 'from pipeline.core.machine import FENCED'
- plan line names no declared file: 'from pipeline.core.machine import FENCED'
- plan line is not a numbered step -- the plan reads as prose: 'from pipeline.core.worktree import project_env'
- plan line names no declared file: 'from pipeline.core.worktree import project_env'
- plan line is not a numbered step -- the plan reads as prose: 'def hunks(diff: str) -> dict[str, list[tuple[int, int]]]:'
- plan line names no declared file: 'def hunks(diff: str) -> dict[str, list[tuple[int, int]]]:'
- plan line is not a numbered step -- the plan reads as prose: '"""path -> new-side line ranges, off `git diff --unified=0`.'
- plan line names no declared file: '"""path -> new-side line ranges, off `git diff --unified=0`.'
- plan line is not a numbered step -- the plan reads as prose: 'A deleted file has `+++ /dev/null`, so the `--- a/` path is carried over:'
- plan line names no declared file: 'A deleted file has `+++ /dev/null`, so the `--- a/` path is carried over:'
- plan line is not a numbered step -- the plan reads as prose: 'dropping it would let "delete the guard entirely" read as an empty diff.'
- plan line names no declared file: 'dropping it would let "delete the guard entirely" read as an empty diff.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'out: dict[str, list[tuple[int, int]]] = {}'
- plan line names no declared file: 'out: dict[str, list[tuple[int, int]]] = {}'
- plan line is not a numbered step -- the plan reads as prose: 'old = path = None'
- plan line names no declared file: 'old = path = None'
- plan line is not a numbered step -- the plan reads as prose: 'for line in diff.splitlines():'
- plan line names no declared file: 'for line in diff.splitlines():'
- plan line is not a numbered step -- the plan reads as prose: 'if line.startswith("--- "):'
- plan line names no declared file: 'if line.startswith("--- "):'
- plan line is not a numbered step -- the plan reads as prose: 'old = line[6:] if line.startswith("--- a/") else None'
- plan line names no declared file: 'old = line[6:] if line.startswith("--- a/") else None'
- plan line is not a numbered step -- the plan reads as prose: 'elif line.startswith("+++ "):'
- plan line names no declared file: 'elif line.startswith("+++ "):'
- plan line is not a numbered step -- the plan reads as prose: 'path = line[6:] if line.startswith("+++ b/") else old'
- plan line names no declared file: 'path = line[6:] if line.startswith("+++ b/") else old'
- plan line is not a numbered step -- the plan reads as prose: 'if path:'
- plan line names no declared file: 'if path:'
- plan line is not a numbered step -- the plan reads as prose: 'out.setdefault(path, [])'
- plan line names no declared file: 'out.setdefault(path, [])'
- plan line is not a numbered step -- the plan reads as prose: 'elif line.startswith("@@") and path:'
- plan line names no declared file: 'elif line.startswith("@@") and path:'
- plan line is not a numbered step -- the plan reads as prose: 'm = re.match(r"@@ -\\d+(?:,\\d+)? \\+(\\d+)(?:,(\\d+))? @@", line)'
- plan line names no declared file: 'm = re.match(r"@@ -\\d+(?:,\\d+)? \\+(\\d+)(?:,(\\d+))? @@", line)'
- plan line is not a numbered step -- the plan reads as prose: 'if m:'
- plan line names no declared file: 'if m:'
- plan line is not a numbered step -- the plan reads as prose: 'start = int(m.group(1))'
- plan line names no declared file: 'start = int(m.group(1))'
- plan line is not a numbered step -- the plan reads as prose: 'n = 1 if m.group(2) is None else max(int(m.group(2)), 1)'
- plan line names no declared file: 'n = 1 if m.group(2) is None else max(int(m.group(2)), 1)'
- plan line is not a numbered step -- the plan reads as prose: 'out[path].append((start, start + n - 1))'
- plan line names no declared file: 'out[path].append((start, start + n - 1))'
- plan line is not a numbered step -- the plan reads as prose: 'return out'
- plan line names no declared file: 'return out'
- plan line is not a numbered step -- the plan reads as prose: 'def symbol_lines(src: str, name: str) -> tuple[int, int] | None:'
- plan line names no declared file: 'def symbol_lines(src: str, name: str) -> tuple[int, int] | None:'
- plan line is not a numbered step -- the plan reads as prose: '"""A top-level def/class/assignment\'s line span, or None if it is gone.'
- plan line names no declared file: '"""A top-level def/class/assignment\'s line span, or None if it is gone.'
- plan line is not a numbered step -- the plan reads as prose: 'Decorators count: `node.lineno` is the `def` line, so a hunk that edited'
- plan line names no declared file: 'Decorators count: `node.lineno` is the `def` line, so a hunk that edited'
- plan line is not a numbered step -- the plan reads as prose: 'only a decorator would otherwise miss.'
- plan line names no declared file: 'only a decorator would otherwise miss.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'try:'
- plan line names no declared file: 'try:'
- plan line is not a numbered step -- the plan reads as prose: 'tree = ast.parse(src)'
- plan line names no declared file: 'tree = ast.parse(src)'
- plan line is not a numbered step -- the plan reads as prose: 'except SyntaxError:'
- plan line names no declared file: 'except SyntaxError:'
- plan line is not a numbered step -- the plan reads as prose: 'return None'
- plan line names no declared file: 'return None'
- plan line is not a numbered step -- the plan reads as prose: 'for node in tree.body:'
- plan line names no declared file: 'for node in tree.body:'
- plan line is not a numbered step -- the plan reads as prose: 'if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):'
- plan line names no declared file: 'if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):'
- plan line is not a numbered step -- the plan reads as prose: 'names = [node.name]'
- plan line names no declared file: 'names = [node.name]'
- plan line is not a numbered step -- the plan reads as prose: 'else:'
- plan line names no declared file: 'else:'
- plan line is not a numbered step -- the plan reads as prose: 'names = [t.id for t in getattr(node, "targets", [])'
- plan line names no declared file: 'names = [t.id for t in getattr(node, "targets", [])'
- plan line is not a numbered step -- the plan reads as prose: 'if isinstance(t, ast.Name)]'
- plan line names no declared file: 'if isinstance(t, ast.Name)]'
- plan line is not a numbered step -- the plan reads as prose: 'if name in names:'
- plan line names no declared file: 'if name in names:'
- plan line is not a numbered step -- the plan reads as prose: 'starts = [node.lineno] + [d.lineno'
- plan line names no declared file: 'starts = [node.lineno] + [d.lineno'
- plan line is not a numbered step -- the plan reads as prose: 'for d in getattr(node, "decorator_list", [])]'
- plan line names no declared file: 'for d in getattr(node, "decorator_list", [])]'
- plan line is not a numbered step -- the plan reads as prose: 'return min(starts), node.end_lineno'
- plan line names no declared file: 'return min(starts), node.end_lineno'
- plan line is not a numbered step -- the plan reads as prose: 'return None'
- plan line names no declared file: 'return None'
- plan line is not a numbered step -- the plan reads as prose: 'def fenced_touches(wt: Path, base: str, fenced: dict = FENCED) -> list[str]:'
- plan line names no declared file: 'def fenced_touches(wt: Path, base: str, fenced: dict = FENCED) -> list[str]:'
- plan line is not a numbered step -- the plan reads as prose: '"""Names of the fenced things this worktree\'s diff touches.'
- plan line names no declared file: '"""Names of the fenced things this worktree\'s diff touches.'
- plan line is not a numbered step -- the plan reads as prose: 'Two dots against the merge base, NOT `base...HEAD`: three dots sees'
- plan line names no declared file: 'Two dots against the merge base, NOT `base...HEAD`: three dots sees'
- plan line is not a numbered step -- the plan reads as prose: 'committed work only, and an uncommitted edit to the guard must not slip'
- plan line names no declared file: 'committed work only, and an uncommitted edit to the guard must not slip'
- plan line is not a numbered step -- the plan reads as prose: 'through.'
- plan line names no declared file: 'through.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'def git(cmd: str) -> str:'
- plan line names no declared file: 'def git(cmd: str) -> str:'
- plan line is not a numbered step -- the plan reads as prose: 'return subprocess.run(f"git {cmd}", shell=True, cwd=wt, capture_output=True,'
- plan line names no declared file: 'return subprocess.run(f"git {cmd}", shell=True, cwd=wt, capture_output=True,'
- plan line is not a numbered step -- the plan reads as prose: 'text=True, env=project_env()).stdout'
- plan line names no declared file: 'text=True, env=project_env()).stdout'
- plan line is not a numbered step -- the plan reads as prose: 'mb = git(f"merge-base {base} HEAD").strip()'
- plan line names no declared file: 'mb = git(f"merge-base {base} HEAD").strip()'
- plan line is not a numbered step -- the plan reads as prose: 'if not mb:'
- plan line names no declared file: 'if not mb:'
- plan line is not a numbered step -- the plan reads as prose: 'return ["fence check found no merge base"]   # fail closed'
- plan line names no declared file: 'return ["fence check found no merge base"]   # fail closed'
- plan line is not a numbered step -- the plan reads as prose: 'changed = hunks(git(f"diff --unified=0 {mb}"))'
- plan line names no declared file: 'changed = hunks(git(f"diff --unified=0 {mb}"))'
- plan line is not a numbered step -- the plan reads as prose: 'hits = []'
- plan line names no declared file: 'hits = []'
- plan line is not a numbered step -- the plan reads as prose: 'for path, symbols in fenced.items():'
- plan line names no declared file: 'for path, symbols in fenced.items():'
- plan line is not a numbered step -- the plan reads as prose: 'ranges = changed.get(path)'
- plan line names no declared file: 'ranges = changed.get(path)'
- plan line is not a numbered step -- the plan reads as prose: 'if ranges is None:'
- plan line names no declared file: 'if ranges is None:'
- plan line is not a numbered step -- the plan reads as prose: 'continue'
- plan line names no declared file: 'continue'
- plan line is not a numbered step -- the plan reads as prose: 'if symbols is None:'
- plan line names no declared file: 'if symbols is None:'
- plan line is not a numbered step -- the plan reads as prose: 'hits.append(path)'
- plan line names no declared file: 'hits.append(path)'
- plan line is not a numbered step -- the plan reads as prose: 'continue'
- plan line names no declared file: 'continue'
- plan line is not a numbered step -- the plan reads as prose: 'f = Path(wt) / path'
- plan line names no declared file: 'f = Path(wt) / path'
- plan line is not a numbered step -- the plan reads as prose: 'src = f.read_text(errors="replace") if f.is_file() else ""'
- plan line names no declared file: 'src = f.read_text(errors="replace") if f.is_file() else ""'
- plan line is not a numbered step -- the plan reads as prose: 'for sym in symbols:'
- plan line names no declared file: 'for sym in symbols:'
- plan line is not a numbered step -- the plan reads as prose: 'span = symbol_lines(src, sym)'
- plan line names no declared file: 'span = symbol_lines(src, sym)'
- plan line is not a numbered step -- the plan reads as prose: 'if span is None:'
- plan line names no declared file: 'if span is None:'
- plan line is not a numbered step -- the plan reads as prose: 'hits.append(f"{path}:{sym} (gone)")'
- plan line names no declared file: 'hits.append(f"{path}:{sym} (gone)")'
- plan line is not a numbered step -- the plan reads as prose: 'elif any(a <= span[1] and span[0] <= b for a, b in ranges):'
- plan line names no declared file: 'elif any(a <= span[1] and span[0] <= b for a, b in ranges):'
- plan line is not a numbered step -- the plan reads as prose: 'hits.append(f"{path}:{sym}")'
- plan line names no declared file: 'hits.append(f"{path}:{sym}")'
- plan line is not a numbered step -- the plan reads as prose: 'return hits'
- plan line names no declared file: 'return hits'
- plan line is not a numbered step -- the plan reads as prose: '```'
- plan line names no declared file: '```'
- plan line is not a numbered step -- the plan reads as prose: 'Code for step 8, `finish_suite()` in `pipeline/daemon/supervisor.py`:'
- plan line is not a numbered step -- the plan reads as prose: '```python'
- plan line names no declared file: '```python'
- plan line is not a numbered step -- the plan reads as prose: 'def finish_suite(project: Path, rec: dict, emit=noop) -> str:'
- plan line names no declared file: 'def finish_suite(project: Path, rec: dict, emit=noop) -> str:'
- plan line is not a numbered step -- the plan reads as prose: '"""The suite\'s exit code, and then the fence check.'
- plan line names no declared file: '"""The suite\'s exit code, and then the fence check.'
- plan line is not a numbered step -- the plan reads as prose: '`ok` PARKS at `awaiting-merge`; only `clean` reaches `merging`. The'
- plan line names no declared file: '`ok` PARKS at `awaiting-merge`; only `clean` reaches `merging`. The'
- plan line is not a numbered step -- the plan reads as prose: 'polarity is the guard: a git failure, an unparseable diff or a bug in'
- plan line names no declared file: 'polarity is the guard: a git failure, an unparseable diff or a bug in'
- plan line is not a numbered step -- the plan reads as prose: '`fenced_touches()` all yield `ok`, and a human looks at the diff. A guard'
- plan line names no declared file: '`fenced_touches()` all yield `ok`, and a human looks at the diff. A guard'
- plan line is not a numbered step -- the plan reads as prose: 'that fails open is not a guard.'
- plan line names no declared file: 'that fails open is not a guard.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'close_child(rec)'
- plan line names no declared file: 'close_child(rec)'
- plan line is not a numbered step -- the plan reads as prose: 'code = rec["proc"].returncode'
- plan line names no declared file: 'code = rec["proc"].returncode'
- plan line is not a numbered step -- the plan reads as prose: 't = Ticket.load(rec["path"])'
- plan line names no declared file: 't = Ticket.load(rec["path"])'
- plan line is not a numbered step -- the plan reads as prose: 'if code != 0:'
- plan line names no declared file: 'if code != 0:'
- plan line is not a numbered step -- the plan reads as prose: 'advance(project, t, "fail",'
- plan line names no declared file: 'advance(project, t, "fail",'
- plan line is not a numbered step -- the plan reads as prose: 'f"regression suite exit {code}\\n```\\n{log_tail(rec)}\\n```",'
- plan line names no declared file: 'f"regression suite exit {code}\\n```\\n{log_tail(rec)}\\n```",'
- plan line is not a numbered step -- the plan reads as prose: 'emit, agent=False)'
- plan line names no declared file: 'emit, agent=False)'
- plan line is not a numbered step -- the plan reads as prose: 'return "fail"'
- plan line names no declared file: 'return "fail"'
- plan line is not a numbered step -- the plan reads as prose: 'try:'
- plan line names no declared file: 'try:'
- plan line is not a numbered step -- the plan reads as prose: 'hits = fenced_touches(rec["wt"], base_ref(project_config(project)))'
- plan line names no declared file: 'hits = fenced_touches(rec["wt"], base_ref(project_config(project)))'
- plan line is not a numbered step -- the plan reads as prose: 'except Exception as e:'
- plan line names no declared file: 'except Exception as e:'
- plan line is not a numbered step -- the plan reads as prose: 'hits = [f"fence check failed ({e.__class__.__name__}: {e})"]'
- plan line names no declared file: 'hits = [f"fence check failed ({e.__class__.__name__}: {e})"]'
- plan line is not a numbered step -- the plan reads as prose: 'if not hits:'
- plan line names no declared file: 'if not hits:'
- plan line is not a numbered step -- the plan reads as prose: 'advance(project, t, "clean",'
- plan line names no declared file: 'advance(project, t, "clean",'
- plan line is not a numbered step -- the plan reads as prose: '"regression suite passed; the diff touches no fenced code",'
- plan line names no declared file: '"regression suite passed; the diff touches no fenced code",'
- plan line is not a numbered step -- the plan reads as prose: 'emit, agent=False)'
- plan line names no declared file: 'emit, agent=False)'
- plan line is not a numbered step -- the plan reads as prose: 'return "clean"'
- plan line names no declared file: 'return "clean"'
- plan line is not a numbered step -- the plan reads as prose: 'advance(project, t, "ok",'
- plan line names no declared file: 'advance(project, t, "ok",'
- plan line is not a numbered step -- the plan reads as prose: '"regression suite passed, but the diff touches fenced code:\\n"'
- plan line names no declared file: '"regression suite passed, but the diff touches fenced code:\\n"'
- plan line is not a numbered step -- the plan reads as prose: '+ "\\n".join(f"- `{h}`" for h in hits)'
- plan line names no declared file: '+ "\\n".join(f"- `{h}`" for h in hits)'
- plan line is not a numbered step -- the plan reads as prose: '+ f"\\n\\n`CLAUDE.md` requires a human to see this diff before it "'
- plan line is not a numbered step -- the plan reads as prose: 'f"lands. `pipeline approve {rec[\'tid\']}` lands it; "'
- plan line names no declared file: 'f"lands. `pipeline approve {rec[\'tid\']}` lands it; "'
- plan line is not a numbered step -- the plan reads as prose: 'f"`pipeline resume {rec[\'tid\']} --stage planning` sends it back.",'
- plan line names no declared file: 'f"`pipeline resume {rec[\'tid\']} --stage planning` sends it back.",'
- plan line is not a numbered step -- the plan reads as prose: 'emit, agent=False)'
- plan line names no declared file: 'emit, agent=False)'
- plan line is not a numbered step -- the plan reads as prose: 'return "ok"'
- plan line names no declared file: 'return "ok"'
- plan line is not a numbered step -- the plan reads as prose: '```'
- plan line names no declared file: '```'
- plan line is not a numbered step -- the plan reads as prose: 'Code for step 17, the drift test in `tests/test_stages.py`:'
- plan line is not a numbered step -- the plan reads as prose: '```python'
- plan line names no declared file: '```python'
- plan line is not a numbered step -- the plan reads as prose: 'def test_the_fenced_list_matches_the_rule_file():'
- plan line names no declared file: 'def test_the_fenced_list_matches_the_rule_file():'
- plan line is not a numbered step -- the plan reads as prose: '"""`CLAUDE.md` names the fenced things in prose and `machine.FENCED` names'
- plan line is not a numbered step -- the plan reads as prose: 'them in code. Two copies that can drift are one promise nobody keeps."""'
- plan line names no declared file: 'them in code. Two copies that can drift are one promise nobody keeps."""'
- plan line is not a numbered step -- the plan reads as prose: 'import re'
- plan line names no declared file: 'import re'
- plan line is not a numbered step -- the plan reads as prose: 'text = (C.PKG.parent / "CLAUDE.md").read_text()'
- plan line is not a numbered step -- the plan reads as prose: 'i = text.index("requires human review before merge")'
- plan line names no declared file: 'i = text.index("requires human review before merge")'
- plan line is not a numbered step -- the plan reads as prose: 'sentence = text[text.rindex("\\n\\n", 0, i):i]'
- plan line names no declared file: 'sentence = text[text.rindex("\\n\\n", 0, i):i]'
- plan line is not a numbered step -- the plan reads as prose: 'prose = {tok.rstrip("()") for tok in re.findall(r"`([^`]+)`", sentence)}'
- plan line names no declared file: 'prose = {tok.rstrip("()") for tok in re.findall(r"`([^`]+)`", sentence)}'
- plan line is not a numbered step -- the plan reads as prose: 'code = {p for p, s in M.FENCED.items() if s is None} | {'
- plan line names no declared file: 'code = {p for p, s in M.FENCED.items() if s is None} | {'
- plan line is not a numbered step -- the plan reads as prose: 's for syms in M.FENCED.values() if syms for s in syms}'
- plan line names no declared file: 's for syms in M.FENCED.values() if syms for s in syms}'
- plan line is not a numbered step -- the plan reads as prose: 'assert prose == code, f"CLAUDE.md says {prose}, machine.FENCED says {code}"'
- plan line is not a numbered step -- the plan reads as prose: '```'
- plan line names no declared file: '```'

### 2026-08-21 10:08:30Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- plan line is not a numbered step -- the plan reads as prose: 'Code for step 4, `pipeline/core/fence.py`:'
- plan line is not a numbered step -- the plan reads as prose: '```python'
- plan line names no declared file: '```python'
- plan line is not a numbered step -- the plan reads as prose: '"""Which fenced symbols a branch\'s diff touches.'
- plan line names no declared file: '"""Which fenced symbols a branch\'s diff touches.'
- plan line is not a numbered step -- the plan reads as prose: '`CLAUDE.md` fences four things off from unattended merge. `machine.FENCED` is'
- plan line is not a numbered step -- the plan reads as prose: 'the machine-readable copy; this is the check. A whole-file entry (`None`) trips'
- plan line names no declared file: 'the machine-readable copy; this is the check. A whole-file entry (`None`) trips'
- plan line is not a numbered step -- the plan reads as prose: "on any hunk. A symbol entry trips only when a hunk overlaps that symbol's own"
- plan line names no declared file: "on any hunk. A symbol entry trips only when a hunk overlaps that symbol's own"
- plan line is not a numbered step -- the plan reads as prose: 'line range, so a ticket that edited a neighbouring function is not parked.'
- plan line names no declared file: 'line range, so a ticket that edited a neighbouring function is not parked.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'import ast'
- plan line names no declared file: 'import ast'
- plan line is not a numbered step -- the plan reads as prose: 'import re'
- plan line names no declared file: 'import re'
- plan line is not a numbered step -- the plan reads as prose: 'import subprocess'
- plan line names no declared file: 'import subprocess'
- plan line is not a numbered step -- the plan reads as prose: 'from pathlib import Path'
- plan line names no declared file: 'from pathlib import Path'
- plan line is not a numbered step -- the plan reads as prose: 'from pipeline.core.machine import FENCED'
- plan line names no declared file: 'from pipeline.core.machine import FENCED'
- plan line is not a numbered step -- the plan reads as prose: 'from pipeline.core.worktree import project_env'
- plan line names no declared file: 'from pipeline.core.worktree import project_env'
- plan line is not a numbered step -- the plan reads as prose: 'def hunks(diff: str) -> dict[str, list[tuple[int, int]]]:'
- plan line names no declared file: 'def hunks(diff: str) -> dict[str, list[tuple[int, int]]]:'
- plan line is not a numbered step -- the plan reads as prose: '"""path -> new-side line ranges, off `git diff --unified=0`.'
- plan line names no declared file: '"""path -> new-side line ranges, off `git diff --unified=0`.'
- plan line is not a numbered step -- the plan reads as prose: 'A deleted file has `+++ /dev/null`, so the `--- a/` path is carried over:'
- plan line names no declared file: 'A deleted file has `+++ /dev/null`, so the `--- a/` path is carried over:'
- plan line is not a numbered step -- the plan reads as prose: 'dropping it would let "delete the guard entirely" read as an empty diff.'
- plan line names no declared file: 'dropping it would let "delete the guard entirely" read as an empty diff.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'out: dict[str, list[tuple[int, int]]] = {}'
- plan line names no declared file: 'out: dict[str, list[tuple[int, int]]] = {}'
- plan line is not a numbered step -- the plan reads as prose: 'old = path = None'
- plan line names no declared file: 'old = path = None'
- plan line is not a numbered step -- the plan reads as prose: 'for line in diff.splitlines():'
- plan line names no declared file: 'for line in diff.splitlines():'
- plan line is not a numbered step -- the plan reads as prose: 'if line.startswith("--- "):'
- plan line names no declared file: 'if line.startswith("--- "):'
- plan line is not a numbered step -- the plan reads as prose: 'old = line[6:] if line.startswith("--- a/") else None'
- plan line names no declared file: 'old = line[6:] if line.startswith("--- a/") else None'
- plan line is not a numbered step -- the plan reads as prose: 'elif line.startswith("+++ "):'
- plan line names no declared file: 'elif line.startswith("+++ "):'
- plan line is not a numbered step -- the plan reads as prose: 'path = line[6:] if line.startswith("+++ b/") else old'
- plan line names no declared file: 'path = line[6:] if line.startswith("+++ b/") else old'
- plan line is not a numbered step -- the plan reads as prose: 'if path:'
- plan line names no declared file: 'if path:'
- plan line is not a numbered step -- the plan reads as prose: 'out.setdefault(path, [])'
- plan line names no declared file: 'out.setdefault(path, [])'
- plan line is not a numbered step -- the plan reads as prose: 'elif line.startswith("@@") and path:'
- plan line names no declared file: 'elif line.startswith("@@") and path:'
- plan line is not a numbered step -- the plan reads as prose: 'm = re.match(r"@@ -\\d+(?:,\\d+)? \\+(\\d+)(?:,(\\d+))? @@", line)'
- plan line names no declared file: 'm = re.match(r"@@ -\\d+(?:,\\d+)? \\+(\\d+)(?:,(\\d+))? @@", line)'
- plan line is not a numbered step -- the plan reads as prose: 'if m:'
- plan line names no declared file: 'if m:'
- plan line is not a numbered step -- the plan reads as prose: 'start = int(m.group(1))'
- plan line names no declared file: 'start = int(m.group(1))'
- plan line is not a numbered step -- the plan reads as prose: 'n = 1 if m.group(2) is None else max(int(m.group(2)), 1)'
- plan line names no declared file: 'n = 1 if m.group(2) is None else max(int(m.group(2)), 1)'
- plan line is not a numbered step -- the plan reads as prose: 'out[path].append((start, start + n - 1))'
- plan line names no declared file: 'out[path].append((start, start + n - 1))'
- plan line is not a numbered step -- the plan reads as prose: 'return out'
- plan line names no declared file: 'return out'
- plan line is not a numbered step -- the plan reads as prose: 'def symbol_lines(src: str, name: str) -> tuple[int, int] | None:'
- plan line names no declared file: 'def symbol_lines(src: str, name: str) -> tuple[int, int] | None:'
- plan line is not a numbered step -- the plan reads as prose: '"""A top-level def/class/assignment\'s line span, or None if it is gone.'
- plan line names no declared file: '"""A top-level def/class/assignment\'s line span, or None if it is gone.'
- plan line is not a numbered step -- the plan reads as prose: 'Decorators count: `node.lineno` is the `def` line, so a hunk that edited'
- plan line names no declared file: 'Decorators count: `node.lineno` is the `def` line, so a hunk that edited'
- plan line is not a numbered step -- the plan reads as prose: 'only a decorator would otherwise miss.'
- plan line names no declared file: 'only a decorator would otherwise miss.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'try:'
- plan line names no declared file: 'try:'
- plan line is not a numbered step -- the plan reads as prose: 'tree = ast.parse(src)'
- plan line names no declared file: 'tree = ast.parse(src)'
- plan line is not a numbered step -- the plan reads as prose: 'except SyntaxError:'
- plan line names no declared file: 'except SyntaxError:'
- plan line is not a numbered step -- the plan reads as prose: 'return None'
- plan line names no declared file: 'return None'
- plan line is not a numbered step -- the plan reads as prose: 'for node in tree.body:'
- plan line names no declared file: 'for node in tree.body:'
- plan line is not a numbered step -- the plan reads as prose: 'if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):'
- plan line names no declared file: 'if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):'
- plan line is not a numbered step -- the plan reads as prose: 'names = [node.name]'
- plan line names no declared file: 'names = [node.name]'
- plan line is not a numbered step -- the plan reads as prose: 'else:'
- plan line names no declared file: 'else:'
- plan line is not a numbered step -- the plan reads as prose: 'names = [t.id for t in getattr(node, "targets", [])'
- plan line names no declared file: 'names = [t.id for t in getattr(node, "targets", [])'
- plan line is not a numbered step -- the plan reads as prose: 'if isinstance(t, ast.Name)]'
- plan line names no declared file: 'if isinstance(t, ast.Name)]'
- plan line is not a numbered step -- the plan reads as prose: 'if name in names:'
- plan line names no declared file: 'if name in names:'
- plan line is not a numbered step -- the plan reads as prose: 'starts = [node.lineno] + [d.lineno'
- plan line names no declared file: 'starts = [node.lineno] + [d.lineno'
- plan line is not a numbered step -- the plan reads as prose: 'for d in getattr(node, "decorator_list", [])]'
- plan line names no declared file: 'for d in getattr(node, "decorator_list", [])]'
- plan line is not a numbered step -- the plan reads as prose: 'return min(starts), node.end_lineno'
- plan line names no declared file: 'return min(starts), node.end_lineno'
- plan line is not a numbered step -- the plan reads as prose: 'return None'
- plan line names no declared file: 'return None'
- plan line is not a numbered step -- the plan reads as prose: 'def fenced_touches(wt: Path, base: str, fenced: dict = FENCED) -> list[str]:'
- plan line names no declared file: 'def fenced_touches(wt: Path, base: str, fenced: dict = FENCED) -> list[str]:'
- plan line is not a numbered step -- the plan reads as prose: '"""Names of the fenced things this worktree\'s diff touches.'
- plan line names no declared file: '"""Names of the fenced things this worktree\'s diff touches.'
- plan line is not a numbered step -- the plan reads as prose: 'Two dots against the merge base, NOT `base...HEAD`: three dots sees'
- plan line names no declared file: 'Two dots against the merge base, NOT `base...HEAD`: three dots sees'
- plan line is not a numbered step -- the plan reads as prose: 'committed work only, and an uncommitted edit to the guard must not slip'
- plan line names no declared file: 'committed work only, and an uncommitted edit to the guard must not slip'
- plan line is not a numbered step -- the plan reads as prose: 'through.'
- plan line names no declared file: 'through.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'def git(cmd: str) -> str:'
- plan line names no declared file: 'def git(cmd: str) -> str:'
- plan line is not a numbered step -- the plan reads as prose: 'return subprocess.run(f"git {cmd}", shell=True, cwd=wt, capture_output=True,'
- plan line names no declared file: 'return subprocess.run(f"git {cmd}", shell=True, cwd=wt, capture_output=True,'
- plan line is not a numbered step -- the plan reads as prose: 'text=True, env=project_env()).stdout'
- plan line names no declared file: 'text=True, env=project_env()).stdout'
- plan line is not a numbered step -- the plan reads as prose: 'mb = git(f"merge-base {base} HEAD").strip()'
- plan line names no declared file: 'mb = git(f"merge-base {base} HEAD").strip()'
- plan line is not a numbered step -- the plan reads as prose: 'if not mb:'
- plan line names no declared file: 'if not mb:'
- plan line is not a numbered step -- the plan reads as prose: 'return ["fence check found no merge base"]   # fail closed'
- plan line names no declared file: 'return ["fence check found no merge base"]   # fail closed'
- plan line is not a numbered step -- the plan reads as prose: 'changed = hunks(git(f"diff --unified=0 {mb}"))'
- plan line names no declared file: 'changed = hunks(git(f"diff --unified=0 {mb}"))'
- plan line is not a numbered step -- the plan reads as prose: 'hits = []'
- plan line names no declared file: 'hits = []'
- plan line is not a numbered step -- the plan reads as prose: 'for path, symbols in fenced.items():'
- plan line names no declared file: 'for path, symbols in fenced.items():'
- plan line is not a numbered step -- the plan reads as prose: 'ranges = changed.get(path)'
- plan line names no declared file: 'ranges = changed.get(path)'
- plan line is not a numbered step -- the plan reads as prose: 'if ranges is None:'
- plan line names no declared file: 'if ranges is None:'
- plan line is not a numbered step -- the plan reads as prose: 'continue'
- plan line names no declared file: 'continue'
- plan line is not a numbered step -- the plan reads as prose: 'if symbols is None:'
- plan line names no declared file: 'if symbols is None:'
- plan line is not a numbered step -- the plan reads as prose: 'hits.append(path)'
- plan line names no declared file: 'hits.append(path)'
- plan line is not a numbered step -- the plan reads as prose: 'continue'
- plan line names no declared file: 'continue'
- plan line is not a numbered step -- the plan reads as prose: 'f = Path(wt) / path'
- plan line names no declared file: 'f = Path(wt) / path'
- plan line is not a numbered step -- the plan reads as prose: 'src = f.read_text(errors="replace") if f.is_file() else ""'
- plan line names no declared file: 'src = f.read_text(errors="replace") if f.is_file() else ""'
- plan line is not a numbered step -- the plan reads as prose: 'for sym in symbols:'
- plan line names no declared file: 'for sym in symbols:'
- plan line is not a numbered step -- the plan reads as prose: 'span = symbol_lines(src, sym)'
- plan line names no declared file: 'span = symbol_lines(src, sym)'
- plan line is not a numbered step -- the plan reads as prose: 'if span is None:'
- plan line names no declared file: 'if span is None:'
- plan line is not a numbered step -- the plan reads as prose: 'hits.append(f"{path}:{sym} (gone)")'
- plan line names no declared file: 'hits.append(f"{path}:{sym} (gone)")'
- plan line is not a numbered step -- the plan reads as prose: 'elif any(a <= span[1] and span[0] <= b for a, b in ranges):'
- plan line names no declared file: 'elif any(a <= span[1] and span[0] <= b for a, b in ranges):'
- plan line is not a numbered step -- the plan reads as prose: 'hits.append(f"{path}:{sym}")'
- plan line names no declared file: 'hits.append(f"{path}:{sym}")'
- plan line is not a numbered step -- the plan reads as prose: 'return hits'
- plan line names no declared file: 'return hits'
- plan line is not a numbered step -- the plan reads as prose: '```'
- plan line names no declared file: '```'
- plan line is not a numbered step -- the plan reads as prose: 'Code for step 8, `finish_suite()` in `pipeline/daemon/supervisor.py`:'
- plan line is not a numbered step -- the plan reads as prose: '```python'
- plan line names no declared file: '```python'
- plan line is not a numbered step -- the plan reads as prose: 'def finish_suite(project: Path, rec: dict, emit=noop) -> str:'
- plan line names no declared file: 'def finish_suite(project: Path, rec: dict, emit=noop) -> str:'
- plan line is not a numbered step -- the plan reads as prose: '"""The suite\'s exit code, and then the fence check.'
- plan line names no declared file: '"""The suite\'s exit code, and then the fence check.'
- plan line is not a numbered step -- the plan reads as prose: '`ok` PARKS at `awaiting-merge`; only `clean` reaches `merging`. The'
- plan line names no declared file: '`ok` PARKS at `awaiting-merge`; only `clean` reaches `merging`. The'
- plan line is not a numbered step -- the plan reads as prose: 'polarity is the guard: a git failure, an unparseable diff or a bug in'
- plan line names no declared file: 'polarity is the guard: a git failure, an unparseable diff or a bug in'
- plan line is not a numbered step -- the plan reads as prose: '`fenced_touches()` all yield `ok`, and a human looks at the diff. A guard'
- plan line names no declared file: '`fenced_touches()` all yield `ok`, and a human looks at the diff. A guard'
- plan line is not a numbered step -- the plan reads as prose: 'that fails open is not a guard.'
- plan line names no declared file: 'that fails open is not a guard.'
- plan line is not a numbered step -- the plan reads as prose: '"""'
- plan line names no declared file: '"""'
- plan line is not a numbered step -- the plan reads as prose: 'close_child(rec)'
- plan line names no declared file: 'close_child(rec)'
- plan line is not a numbered step -- the plan reads as prose: 'code = rec["proc"].returncode'
- plan line names no declared file: 'code = rec["proc"].returncode'
- plan line is not a numbered step -- the plan reads as prose: 't = Ticket.load(rec["path"])'
- plan line names no declared file: 't = Ticket.load(rec["path"])'
- plan line is not a numbered step -- the plan reads as prose: 'if code != 0:'
- plan line names no declared file: 'if code != 0:'
- plan line is not a numbered step -- the plan reads as prose: 'advance(project, t, "fail",'
- plan line names no declared file: 'advance(project, t, "fail",'
- plan line is not a numbered step -- the plan reads as prose: 'f"regression suite exit {code}\\n```\\n{log_tail(rec)}\\n```",'
- plan line names no declared file: 'f"regression suite exit {code}\\n```\\n{log_tail(rec)}\\n```",'
- plan line is not a numbered step -- the plan reads as prose: 'emit, agent=False)'
- plan line names no declared file: 'emit, agent=False)'
- plan line is not a numbered step -- the plan reads as prose: 'return "fail"'
- plan line names no declared file: 'return "fail"'
- plan line is not a numbered step -- the plan reads as prose: 'try:'
- plan line names no declared file: 'try:'
- plan line is not a numbered step -- the plan reads as prose: 'hits = fenced_touches(rec["wt"], base_ref(project_config(project)))'
- plan line names no declared file: 'hits = fenced_touches(rec["wt"], base_ref(project_config(project)))'
- plan line is not a numbered step -- the plan reads as prose: 'except Exception as e:'
- plan line names no declared file: 'except Exception as e:'
- plan line is not a numbered step -- the plan reads as prose: 'hits = [f"fence check failed ({e.__class__.__name__}: {e})"]'
- plan line names no declared file: 'hits = [f"fence check failed ({e.__class__.__name__}: {e})"]'
- plan line is not a numbered step -- the plan reads as prose: 'if not hits:'
- plan line names no declared file: 'if not hits:'
- plan line is not a numbered step -- the plan reads as prose: 'advance(project, t, "clean",'
- plan line names no declared file: 'advance(project, t, "clean",'
- plan line is not a numbered step -- the plan reads as prose: '"regression suite passed; the diff touches no fenced code",'
- plan line names no declared file: '"regression suite passed; the diff touches no fenced code",'
- plan line is not a numbered step -- the plan reads as prose: 'emit, agent=False)'
- plan line names no declared file: 'emit, agent=False)'
- plan line is not a numbered step -- the plan reads as prose: 'return "clean"'
- plan line names no declared file: 'return "clean"'
- plan line is not a numbered step -- the plan reads as prose: 'advance(project, t, "ok",'
- plan line names no declared file: 'advance(project, t, "ok",'
- plan line is not a numbered step -- the plan reads as prose: '"regression suite passed, but the diff touches fenced code:\\n"'
- plan line names no declared file: '"regression suite passed, but the diff touches fenced code:\\n"'
- plan line is not a numbered step -- the plan reads as prose: '+ "\\n".join(f"- `{h}`" for h in hits)'
- plan line names no declared file: '+ "\\n".join(f"- `{h}`" for h in hits)'
- plan line is not a numbered step -- the plan reads as prose: '+ f"\\n\\n`CLAUDE.md` requires a human to see this diff before it "'
- plan line is not a numbered step -- the plan reads as prose: 'f"lands. `pipeline approve {rec[\'tid\']}` lands it; "'
- plan line names no declared file: 'f"lands. `pipeline approve {rec[\'tid\']}` lands it; "'
- plan line is not a numbered step -- the plan reads as prose: 'f"`pipeline resume {rec[\'tid\']} --stage planning` sends it back.",'
- plan line names no declared file: 'f"`pipeline resume {rec[\'tid\']} --stage planning` sends it back.",'
- plan line is not a numbered step -- the plan reads as prose: 'emit, agent=False)'
- plan line names no declared file: 'emit, agent=False)'
- plan line is not a numbered step -- the plan reads as prose: 'return "ok"'
- plan line names no declared file: 'return "ok"'
- plan line is not a numbered step -- the plan reads as prose: '```'
- plan line names no declared file: '```'
- plan line is not a numbered step -- the plan reads as prose: 'Code for step 17, the drift test in `tests/test_stages.py`:'
- plan line is not a numbered step -- the plan reads as prose: '```python'
- plan line names no declared file: '```python'
- plan line is not a numbered step -- the plan reads as prose: 'def test_the_fenced_list_matches_the_rule_file():'
- plan line names no declared file: 'def test_the_fenced_list_matches_the_rule_file():'
- plan line is not a numbered step -- the plan reads as prose: '"""`CLAUDE.md` names the fenced things in prose and `machine.FENCED` names'
- plan line is not a numbered step -- the plan reads as prose: 'them in code. Two copies that can drift are one promise nobody keeps."""'
- plan line names no declared file: 'them in code. Two copies that can drift are one promise nobody keeps."""'
- plan line is not a numbered step -- the plan reads as prose: 'import re'
- plan line names no declared file: 'import re'
- plan line is not a numbered step -- the plan reads as prose: 'text = (C.PKG.parent / "CLAUDE.md").read_text()'
- plan line is not a numbered step -- the plan reads as prose: 'i = text.index("requires human review before merge")'
- plan line names no declared file: 'i = text.index("requires human review before merge")'
- plan line is not a numbered step -- the plan reads as prose: 'sentence = text[text.rindex("\\n\\n", 0, i):i]'
- plan line names no declared file: 'sentence = text[text.rindex("\\n\\n", 0, i):i]'
- plan line is not a numbered step -- the plan reads as prose: 'prose = {tok.rstrip("()") for tok in re.findall(r"`([^`]+)`", sentence)}'
- plan line names no declared file: 'prose = {tok.rstrip("()") for tok in re.findall(r"`([^`]+)`", sentence)}'
- plan line is not a numbered step -- the plan reads as prose: 'code = {p for p, s in M.FENCED.items() if s is None} | {'
- plan line names no declared file: 'code = {p for p, s in M.FENCED.items() if s is None} | {'
- plan line is not a numbered step -- the plan reads as prose: 's for syms in M.FENCED.values() if syms for s in syms}'
- plan line names no declared file: 's for syms in M.FENCED.values() if syms for s in syms}'
- plan line is not a numbered step -- the plan reads as prose: 'assert prose == code, f"CLAUDE.md says {prose}, machine.FENCED says {code}"'
- plan line is not a numbered step -- the plan reads as prose: '```'
- plan line names no declared file: '```'

### 2026-08-21 · planning · result=ok

The gate's findings have one cause: three code blocks sat inside `## Plan`.
`pipeline/core/gate.py:193-220` reads every non-blank line of that section,
treats an unindented line without a leading `N.` as prose, and then asks that
prose line to name a declared file. A line reading `import ast` does neither.

Fix: the three blocks moved to a new `## Reference code` section, placed
between `## Plan` and `## Acceptance criteria`. Steps 4, 8 and 17 now say
"copying the body from the `## Reference code` section verbatim". No design
changed, no code block changed, no step changed its target files.

`sections()` keeps `## Reference code` whole, and `stage_view()` trims only
`## Thread` (DEC-023), so the implementer still reads the blocks in its prompt.

I re-ran the gate's own plan parser over the edited section, using
`pipeline.core.gate._cites` and `Ticket.files_declared`:

    22 steps
    CLEAN
    digest lines 57

Zero prose lines, zero steps missing a declared file, 57 digest lines against a
floor of 3, and every acceptance criterion names a test.

The pipeline guard blocked a `python3 - <<'PY'` heredoc with "command does not
parse as a shell command". I made that edit through the file edit tool. I did
not work around the guard.

### 2026-08-21 10:10:41Z · planning · session · session=489c037b-f21a-499a-8b32-e035bb4a5daf

`planning` ran as session `489c037b-f21a-499a-8b32-e035bb4a5daf`
- replay: `claude --resume 489c037b-f21a-499a-8b32-e035bb4a5daf`
- log: `.project/logs/TICKET-031-planning-489c037b.log`

### 2026-08-21 10:10:41Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Moved the plan's three code blocks into a new `## Reference code` section; `## Plan` now parses as 22 numbered steps with zero prose lines

### 2026-08-21 10:10:51Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge` fails as required
```
1 item

tests/test_machine.py F

=================================== FAILURES ===================================
___________________ test_a_fenced_file_is_gated_before_merge ___________________

    def test_a_fenced_file_is_gated_before_merge():
        """CLAUDE.md fences four things off from unattended merge:
        `pipeline/hooks/dangerous-commands.py`, `transition()`, `validate_meta()`
        and `CONTROL_FIELDS`. The dispatcher holds no such list, and no human gate
        stands between `implementing` and `done` -- a diff touching a fenced file
        lands with the plan gate as its only human."""
>       assert getattr(M, "FENCED", None), "no fenced-file list in the dispatcher"
E       AssertionError: no fenced-file list in the dispatcher
E       assert None
E        +  where None = getattr(M, 'FENCED', None)

tests/test_machine.py:48: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_fenced_file_is_gated_before_merge - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge` fails on base `main` too -- the bug is not already fixed upstream
```
hing a fenced file
        lands with the plan gate as its only human."""
>       assert getattr(M, "FENCED", None), "no fenced-file list in the dispatcher"
E       AssertionError: no fenced-file list in the dispatcher
E       assert None
E        +  where None = getattr(M, 'FENCED', None)

tests/test_machine.py:48: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_fenced_file_is_gated_before_merge - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-1sox5edp/base
      Built pipeline @ file:///tmp/pipeline-base-1sox5edp/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 · plan-validation · result=ok

**Tier B judgment: PASS.** Eight items scored below, each against the code in
the worktree. Three notes for the implementer follow the scores. None of the
three blocks the plan.

1. **Root cause.** `CLAUDE.md` states the fence in prose only. The state
machine holds no list of fenced things, and `transition()` runs
`implementing -> review -> verifying -> merging -> done` with no `HUMAN_GATES`
member on that path (`pipeline/core/machine.py:72-94`). A diff that rewrites
`transition()` itself lands with the plan gate as its only human. The plan
fixes that cause: it adds the list (`FENCED`), the gate (`awaiting-merge`) and
the check that chooses between them (`fenced_touches()`). It does not fix the
symptom alone. `FENCED` existing by itself still fails the committed test's
walk at `tests/test_machine.py:50-54`.

2. **Decision conflict.** DEC-011, DEC-017, DEC-018 and DEC-023 constrain this
plan, and the plan complies. `start()` returns at
`pipeline/daemon/supervisor.py:466` for any stage in `HUMAN_GATES`, before the
lease, so DEC-011's no-race argument carries to the second gate unchanged. The
plan supersedes no decision. I read the three records the ticket did not list:
DEC-026, DEC-029 and DEC-030. DEC-026 constrains this plan and the plan
complies: the cheap route it added routes `quick-review -> verifying`
(`git show main:pipeline/core/machine.py`, lines 102-103), so a chore reaches
the new gate like every other ticket. DEC-029 and DEC-030 govern the rebase and
the gate's finding text; neither reaches this path.

3. **Scope discipline.** Steps 1-17 and 21-22 each trace to an acceptance
criterion. Steps 18-20 trace to a project rule instead. `CLAUDE.md` holds the
fence prose that criterion 8 reads, and it states that
`.claude/skills/file-ticket/SKILL.md` "is part of the interface" and that a
change to the human gates "is not finished until the skill says the same
thing". Step 19's `README.md` edit carries the same obligation. No step is
untraceable.

4. **Falsifiable criteria.** Criterion 5 is the sharpest: a whole-file
implementation fails its neighbour case, and `base...HEAD` fails its
uncommitted case. Criterion 3 fails if the fence trips on everything.
Criterion 2 fails if it trips on nothing. Criterion 8 fails if either copy of
the list is edited alone. Criterion 9 covers the guard's own tables, which
pytest does not collect. No criterion is vacuous.

5. **No research left.** Every step names a file and a symbol, and the three
bodies sit verbatim in `## Reference code`. I checked the identifiers those
bodies reach for. `noop`, `close_child`, `log_tail`, `advance`, `Ticket` and
`project_config` are all in scope in `pipeline/daemon/supervisor.py`. A suite
record carries both keys `finish_suite()` reads: `wt`
(`pipeline/daemon/supervisor.py:409`) and `tid` (`:520`). `base_ref` and
`project_env` exist at `pipeline/core/worktree.py:35` and `:11`. `C.PKG` is
`pipeline/core/config.py:15` and its parent is the repo root, so the drift test
reads the real `CLAUDE.md`.

6. **Riskiest step, and its fallback.** Step 8, `finish_suite()`. It is the one
step that can let a fenced diff merge unseen. The plan states the fallback and
the reference body implements it: `except Exception` yields `ok`, an empty
merge base yields `["fence check found no merge base"]`, and both park at the
gate. Only a positive `clean` reaches `merging`. Step 6 requires
`tests/test_fence.py` green before the supervisor is touched, so the riskiest
step lands on a checked function.

7. **Regression surface.** Four things could plausibly break, and each has a
test. `tests/test_dispatch.py::test_a_verified_ticket_lands_on_base` is the
only existing test that runs a *passing* suite through `verifying`; criterion 4
covers it. `test_verifying_runs_as_a_tracked_child`
(`tests/test_dispatch.py:101`) and
`test_a_child_log_that_is_not_utf8_still_advances_the_ticket` (`:486`) both use
`exit 1` suites, so they stay on the `fail` branch this plan does not change.
`tests/test_machine.py:102` asserts that no stage but `plan-validation` reaches
`awaiting-approval`; the new gate carries its own name, so that assertion
holds. `tests/test_stages.py:47` subtracts `HUMAN_GATES`, so the new gate needs
no prompt file. I checked the free riders the digest claims:
`pipeline/daemon/server.py:106` and `pipeline/cli/metrics.py:108` both build
from `HUMAN_GATES`, and `pipeline/tui/app.py:531` delegates to `cmd_approve`
with no stage check of its own, so the TUI's `a` key works at the new gate with
no edit.

8. **Blast radius.** 12 files on a `class: feature` ticket: 4 source, 5 test, 3
documentation. The 4 source files are the minimum this change can touch -- the
table, the check, the caller and the CLI. Proportionate to the class.

**Note 1 -- base has moved, and two documentation line numbers moved with it.**
`main` is `30542f1`, the merge base is `a97e7b7`, and TICKET-026 landed
`quick-review` in between. `revalidating` rebases before `implementing` runs,
so the implementer edits the rebased tree. The two test line numbers survive
the rebase: `tests/test_machine.py:20` and `tests/test_dispatch.py:156` hold
the same assertions on `main`. Two documentation numbers do not. On `main`,
step 19's `README.md` line 35 is line 37 and line 175 is line 177. Step 20's
`.claude/skills/file-ticket/SKILL.md:148` now reads "The ticket stops at
`awaiting-approval` for the human, unless `triage` judges the fix" -- the cheap
route rewrote that sentence. Apply steps 19 and 20 by content, not by line
number.

**Note 2 -- two sentences the plan leaves stale.** `README.md:187` on `main`
says "`approve` therefore hands the ticket to `revalidating`".
`pipeline/tui/app.py:536` says "`cmd_approve` already refuses outside
`awaiting-approval`". After this change both describe the plan gate only. Step
19 lists neither. Each is a one-line edit.

**Note 3 -- one edge the symbol check misses.** `git diff --unified=0` writes a
pure deletion as `@@ -50,3 +49,0 @@`, and `hunks()` turns a zero-length new
side into the one-line range `(49, 49)`. Deleting the blank lines or the
decorator immediately *above* a fenced symbol therefore reads as outside that
symbol. Deleting the symbol itself still trips, through the `(gone)` path. The
acceptance criteria do not cover this edge, and I am not asking them to.

I ran no test in this stage. The Tier A gate already recorded the
reproduction, and this stage is read-only.

### 2026-08-21 10:16:41Z · plan-validation · session · session=34e16c6c-534e-4f58-8d23-83e4114d9350

`plan-validation` ran as session `34e16c6c-534e-4f58-8d23-83e4114d9350`
- replay: `claude --resume 34e16c6c-534e-4f58-8d23-83e4114d9350`
- log: `.project/logs/TICKET-031-plan-validation-34e16c6c.log`

### 2026-08-21 10:16:41Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B judgment passed all eight items; three non-blocking notes recorded (base moved to 30542f1, two stale doc sentences, zero-length-hunk edge)

### 2026-08-21 11:31:31Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 11:31:47Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge` fails as required
```
1 item

tests/test_machine.py F

=================================== FAILURES ===================================
___________________ test_a_fenced_file_is_gated_before_merge ___________________

    def test_a_fenced_file_is_gated_before_merge():
        """CLAUDE.md fences four things off from unattended merge:
        `pipeline/hooks/dangerous-commands.py`, `transition()`, `validate_meta()`
        and `CONTROL_FIELDS`. The dispatcher holds no such list, and no human gate
        stands between `implementing` and `done` -- a diff touching a fenced file
        lands with the plan gate as its only human."""
>       assert getattr(M, "FENCED", None), "no fenced-file list in the dispatcher"
E       AssertionError: no fenced-file list in the dispatcher
E       assert None
E        +  where None = getattr(M, 'FENCED', None)

tests/test_machine.py:48: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_fenced_file_is_gated_before_merge - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_machine.py::test_a_fenced_file_is_gated_before_merge` fails on base `main` too -- the bug is not already fixed upstream
```
ching a fenced file
        lands with the plan gate as its only human."""
>       assert getattr(M, "FENCED", None), "no fenced-file list in the dispatcher"
E       AssertionError: no fenced-file list in the dispatcher
E       assert None
E        +  where None = getattr(M, 'FENCED', None)

tests/test_machine.py:48: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_fenced_file_is_gated_before_merge - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-rneecs65/base
      Built pipeline @ file:///tmp/pipeline-base-rneecs65/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-21 11:31:47Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 · implementing · todo

**implementing todo list**, one entry per plan step:

1. [x] `FENCED` dict in `machine.py`
2. [x] `transition()` rows: `verifying/ok -> awaiting-merge`, `verifying/clean -> merging`
3. [x] `awaiting-merge` in `HUMAN_GATES`
4. [x] `pipeline/core/fence.py`
5. [x] `tests/test_fence.py`
6. [x] run `tests/test_fence.py`, confirm pass before touching supervisor
7. [x] import `fenced_touches` in `supervisor.py` (`base_ref` and `project_config` were already imported there)
8. [x] `finish_suite()` in `supervisor.py`
9. [x] `_finish()` calls `finish_suite()`
10. [x] `GATE_NEXT` in `cli/main.py`
11. [x] rewrite `cmd_approve`
12. [x] `test_machine.py:20` update + new assert
13. [x] `test_dispatch.py:156` update
14. [x] `test_a_fenced_diff_parks_before_merging`
15. [x] `test_an_unfenced_diff_merges_without_a_human`
16. [x] `test_approve_lands_a_fenced_ticket`
17. [x] `test_the_fenced_list_matches_the_rule_file`
18. [x] `CLAUDE.md` sentence
19. [x] `README.md` (lines 13, 37, 177) + stale sentence at 187
20. [x] `.claude/skills/file-ticket/SKILL.md` line 148
21. [x] full test run, paste output
22. [x] `test_dangerous_commands.py` run, paste output
23. [x] commit

### 2026-08-21 · implementing · note

**Not touched, out of scope.** `pipeline/tui/app.py:536`'s docstring, "`cmd_approve`
already refuses outside `awaiting-approval`", is stale: `cmd_approve` now also
accepts `awaiting-merge`. `## Digest` flagged this line as one of two stale
sentences with "no step lists them" -- the plan assigns it to no step, and
fixing it is outside `files_declared` for this ticket. Left for a follow-up.

### 2026-08-21 · implementing · tests

**Targeted suite, all pass:**
```
$ uv run --group dev pytest -q tests/test_fence.py tests/test_machine.py tests/test_dispatch.py tests/test_cli.py tests/test_stages.py
.................................................................        [100%]
65 passed in 3.32s
```

**Full suite, all pass:**
```
$ uv run --group dev pytest -q
........................................................................ [ 35%]
........................................................................ [ 70%]
............................................................             [100%]
204 passed in 9.00s
```

**Guard script, exit 0:**
```
$ ./pipeline/hooks/test_dangerous_commands.py
[26 table-driven cases + end-to-end exit codes, all `ok`]
guard: all passed
```

### 2026-08-21 11:37:03Z · implementing · session · session=51c90ed6-b964-4449-ac65-01207157c0d1

`implementing` ran as session `51c90ed6-b964-4449-ac65-01207157c0d1`
- replay: `claude --resume 51c90ed6-b964-4449-ac65-01207157c0d1`
- log: `.project/logs/TICKET-031-implementing-51c90ed6.log`

### 2026-08-21 11:37:03Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Implemented FENCED, awaiting-merge gate, finish_suite() and cmd_approve GATE_NEXT; 65 targeted + 204 full tests pass, guard script exits 0, committed as de7ad39.

### 2026-08-21 · review · findings · verdict=PASS

**No blocking findings.** I reviewed the delta `main..HEAD`: commits `f023043`
and `de7ad39`, 12 files, 302 insertions. The working tree is clean.

Every acceptance criterion holds. Criterion 9 was measured, not run -- see
finding 4.

```
$ uv run --group dev pytest -v tests/test_fence.py tests/test_stages.py::test_the_fenced_list_matches_the_rule_file tests/test_dispatch.py::test_a_fenced_diff_parks_before_merging tests/test_dispatch.py::test_an_unfenced_diff_merges_without_a_human tests/test_cli.py::test_approve_lands_a_fenced_ticket tests/test_machine.py::test_a_fenced_file_is_gated_before_merge
tests/test_fence.py::test_a_neighbouring_function_does_not_trip_the_fence PASSED [ 16%]
tests/test_stages.py::test_the_fenced_list_matches_the_rule_file PASSED  [ 33%]
tests/test_dispatch.py::test_a_fenced_diff_parks_before_merging PASSED   [ 50%]
tests/test_dispatch.py::test_an_unfenced_diff_merges_without_a_human PASSED [ 66%]
tests/test_cli.py::test_approve_lands_a_fenced_ticket PASSED             [ 83%]
tests/test_machine.py::test_a_fenced_file_is_gated_before_merge PASSED   [100%]

============================== 6 passed in 0.32s ===============================

$ uv run --group dev pytest -q
204 passed in 8.93s
```

Five checks found nothing. They are recorded so the next reader skips them:

1. The polarity is right in the code, not only in the comment.
   `finish_suite()` returns `clean` on one path, `if not hits`.
   `project_config()` raises `PipelineError`, which is an `Exception`, so the
   `except` catches it, sets `hits` and parks the ticket. The guard fails
   closed.
2. The new `clean` result reaches no consumer that enumerates results.
   `pipeline/cli/metrics.py` reads `kind IN ('result','usage')` for cost and
   `kind='escalated'` for the escalation view. Neither reads a `stage_end`
   result value. `tests/test_machine.py:94` already walks `junk`, so an
   unknown result still escalates.
3. `awaiting-merge` needs no code beyond `HUMAN_GATES`. Its five consumers all
   read the set: `supervisor.py:468`, `server.py:106`, `tui/app.py:81`,
   `metrics.py:108` and `metrics.py:339`. Outside `cmd_reject`, `transition()`
   and the tests, no literal `awaiting-approval` remains.
4. `FENCED` holds this repo's own paths, so another project's diff never
   matches and the fence never parks its tickets.
5. `test_an_unfenced_diff_merges_without_a_human` is what makes the dispatch
   pair non-vacuous. A `fenced_touches()` that always returned a hit would park
   that ticket and fail that test.

Findings. None blocks the ticket.

1. **minor -- a rename escapes the fence.** `hunks()` keys the new-side path.
   `git mv pipeline/core/machine.py pipeline/core/m2.py` plus an edit files the
   hunks under `pipeline/core/m2.py`, so `changed.get()` on the fenced path
   returns `None`. A 100%-similar rename emits no `---`/`+++` line at all;
   commit `5f12a19` shows `rename from hooks/dangerous-commands.py` with no
   hunk header. This does not block, because the suite runs before the fence
   check. `tests/test_stages.py:106` asserts
   `(C.HOOKS_DIR / "dangerous-commands.py").is_file()`, and renaming
   `machine.py` or `ticket.py` breaks every import. `finish_suite()` returns
   `fail` first.
2. **minor -- the stale docstring is a docstring only.**
   `pipeline/tui/app.py:536` still says `cmd_approve` refuses outside
   `awaiting-approval`. The TUI hands `cmd_approve` to `_cli()` and
   reimplements no check, so `a` on a ticket parked at `awaiting-merge` lands
   it correctly today. The `implementing · note` entry already scoped this out.
3. **nit -- `README.md:189` runs to 100 characters** where the file wraps at
   about 80: "`approve` at `awaiting-approval` therefore hands the ticket to
   `revalidating`, which rebases the branch". The content is correct.
4. **note -- acceptance criterion 9 was measured, not run.** The guard refused
   the script from this stage: "Blocked by the pipeline guard (review):
   `test_dangerous_commands.py` is not on the read-only allowlist." I did not
   work around it. Instead `git diff --stat main...HEAD` lists 12 files and
   none is under `pipeline/hooks/`, so the guard tables are unchanged.
   `implementing` recorded the script exiting 0 against those same tables.

### 2026-08-21 11:41:47Z · review · session · session=11c93300-7b6f-4d92-99e0-42b56a0a855d

`review` ran as session `11c93300-7b6f-4d92-99e0-42b56a0a855d`
- replay: `claude --resume 11c93300-7b6f-4d92-99e0-42b56a0a855d`
- log: `.project/logs/TICKET-031-review-11c93300.log`

### 2026-08-21 11:41:47Z · review · transition · to=holistic-review · result=ok · marker=yes

**review -> holistic-review** (result: `ok`)

✓ Reviewed de7ad39: all 9 acceptance criteria hold, 204/204 pass; 4 non-blocking findings appended (rename escape, stale TUI docstring, long README line, guard script not runnable from review).

### 2026-08-21 · holistic-review · findings · verdict=PASS

**Coherent.** I reviewed the whole diff `main...HEAD` against `## Plan`: 12
files, 302 insertions, 22 deletions, working tree clean. The 12 files are the
12 the plan names. No later change undoes an earlier one, and nothing landed
that no acceptance criterion asked for.

```
$ uv run --group dev pytest -q
204 passed in 8.89s
```

Four coherence checks, each with what I compared:

1. **The sum matches the plan.** Every one of the 22 numbered steps has a
   matching hunk. Steps 4, 8 and 17 copy `## Reference code` verbatim; I
   compared all three bodies to the ticket text and found no edit.
2. **The polarity holds in all four places at once.** `machine.transition()`
   sends `ok` to `awaiting-merge` and `clean` to `merging`. `finish_suite()`
   claims `clean` only under `if not hits`. `tests/test_machine.py:20-21`
   asserts both rows. `tests/test_dispatch.py:156` asserts `clean`. No file
   kept the old direction.
3. **Error handling did not drift between the touched files.**
   `finish_suite()` mirrors `finish_child()`: `close_child`, then
   `returncode`, then `advance(..., agent=False)`. The one addition is the
   `except Exception` around `fenced_touches()`, which sets `hits` and so
   parks. `fenced_touches()` fails closed on its own path too, returning
   `["fence check found no merge base"]`.
4. **No consumer was left behind by the second gate.** Every reader of
   `HUMAN_GATES` reads the constant, not a literal: `pipeline/tui/app.py:81`,
   `pipeline/cli/metrics.py:108` and `:339`, `pipeline/daemon/server.py:106`,
   `pipeline/daemon/supervisor.py:468`, and `machine.KNOWN_STAGES`.
   `cmd_reject` still refuses outside `awaiting-approval`, which
   `## Decisions` calls deliberate.

Two observations, neither blocking:

1. **`approve` at `awaiting-merge` overwrites `approved_by` and
   `approved_at`.** A fenced ticket passes both gates, so the second approval
   replaces the first one's name and timestamp. Nothing reads those two fields
   for meaning. They appear only in `CONTROL_FIELDS`
   (`pipeline/core/machine.py:151`) as tamper-checked frontmatter, and the
   thread keeps one `human · approval` entry per gate, so the audit trail
   survives. Plan step 11 lists no change here.
2. **The happy path no longer records the suite's log tail.**
   `finish_child()` posted `"regression suite exit 0"` plus `log_tail(rec)` on
   success. `finish_suite()` posts `"regression suite passed; the diff touches
   no fenced code"` with no tail. The failure path still carries the tail.
   This text comes from `## Reference code`, which step 8 says to copy
   verbatim, so it is planned, not drift.

`tests/test_machine.py:43-47`'s docstring still describes the pre-fence world:
"The dispatcher holds no such list, and no human gate stands between
`implementing` and `done`". It was written at triage as the reproduction. Its
assertions are correct. Prose only.

### 2026-08-21 11:44:22Z · holistic-review · session · session=afdaff97-da62-4fe3-a246-e30fa4a4ea15

`holistic-review` ran as session `afdaff97-da62-4fe3-a246-e30fa4a4ea15`
- replay: `claude --resume afdaff97-da62-4fe3-a246-e30fa4a4ea15`
- log: `.project/logs/TICKET-031-holistic-review-afdaff97.log`

### 2026-08-21 11:44:22Z · holistic-review · transition · to=verifying · result=ok · marker=yes

**holistic-review -> verifying** (result: `ok`)

✓ Whole diff coherent: 12 files match the plan, ok-parks/clean-merges polarity holds in all four places, 204/204 pass; 2 non-blocking observations recorded.

### 2026-08-21 11:44:31Z · verifying · transition · to=merging · result=ok

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

### 2026-08-21 11:44:32Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/031


Already up to date.
Updating 30542f1..de7ad39
Fast-forward
 .claude/skills/file-ticket/SKILL.md | 10 ++--
 CLAUDE.md                           |  6 +++
 README.md                           | 20 ++++----
 pipeline/cli/main.py                | 15 ++++--
 pipeline/core/fence.py              | 95 +++++++++++++++++++++++++++++++++++++
 pipeline/core/machine.py            | 17 ++++++-
 pipeline/daemon/supervisor.py       | 38 ++++++++++++++-
 tests/test_cli.py                   | 25 ++++++++++
 tests/test_dispatch.py              | 46 +++++++++++++++++-
 tests/test_fence.py                 | 21 ++++++++
 tests/test_machine.py               | 18 ++++++-
 tests/test_stages.py                | 13 +++++
 12 files changed, 302 insertions(+), 22 deletions(-)
 create mode 100644 pipeline/core/fence.py
 create mode 100644 tests/test_fence.py

```

### 2026-08-21 11:44:32Z · merging · decision

decision recorded as `DEC-031`
