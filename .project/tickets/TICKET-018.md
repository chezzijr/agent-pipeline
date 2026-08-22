---
id: TICKET-018
stage: done
class: bugfix
branch: ticket/018
test_file: tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
files_declared:
- pipeline/core/gate.py
- pipeline/stages/planning.md
- tests/helpers.py
- tests/test_gate.py
- tests/test_ticket.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 43edfb4d-37d5-4277-aff8-d833a615eedc
  log: .project/logs/TICKET-018-review-43edfb4d.log
approved_by: chezzijr
approved_at: '2026-08-21T07:11:00.078079+00:00'
---

## Summary

Fixed on `ticket/018` as commit `06089bf`. `pipeline/core/gate.py` now enforces
`MIN_DIGEST_ENTRIES = 3` non-empty `## Digest` lines (waived by a
`digest-short: <why fewer>` line) and resolves every `DEC-<n>` cited in
`## Decisions checked` against `.project/decisions/` in the project root via
`active_decisions()`/`decisions_dir()`: an unresolvable id is a finding, a
superseded one is an `ok:`-prefixed note that does not fail the gate.
`tests/helpers.py:FIXTURE` grew a real three-entry digest, which dragged three
call sites (`tests/test_gate.py:49,209` via a new file-local `_set_digest()`
helper, `tests/test_ticket.py:22`) and `pipeline/stages/planning.md` (two
documentation lines, no test reads that file) along with it. Verified:
`tests/test_gate.py tests/test_ticket.py` 43 passed, whole suite 177 passed,
`./pipeline/hooks/test_dangerous_commands.py` all passed.

**Review (2026-08-21, first pass): PASS, no blocking findings.** The delta
(`main...HEAD`, both commits) is the approved plan verbatim -- steps 1-8 landed
where `## Plan` said, in one commit touching exactly the five declared files,
tree clean. Re-run independently: `tests/test_gate.py tests/test_ticket.py` 43
passed, whole suite 177 passed, and all six tests the acceptance criteria name
pass by name. Four non-blocking notes are in `## Thread`; the only one worth
carrying forward is that the review stage's own allowlist blocks
`./pipeline/hooks/test_dangerous_commands.py`, so that AC is implementer-attested
rather than review-verified -- the delta touches no guard file.

Original report follows, superseded by the fix above:

`## Digest` and `## Decisions checked` are checked for non-emptiness only

The design conversation specifies two Tier A checks with real content requirements:

- "Context digest section exists: files touched, key functions, entry points, gotchas --
  minimum N entries or explicit justification for fewer"
- "Decisions file was read: plan cites which decision entries were checked (list of
  decision IDs, or explicit 'none relevant' with grep terms used)"

`gate()` implements both as "the section is a non-empty string". A digest of one word
passes. A `## Decisions checked` citing `DEC-999` passes even though no such record
exists -- the IDs are never resolved against `.project/decisions/`, though
`active_decisions()` now exists and would make that a one-line lookup.

This is the check that is supposed to stop a plan reverting a deliberate fix, so a
citation nobody verifies is the weakest possible version of it.

Expected: a minimum entry count for the digest (or an explicit justification line), and
cited decision IDs resolved against the decisions directory -- an unknown ID is a finding,
and a superseded one is noted rather than treated as binding.

**Triage (2026-08-21): reproduced.** Both symptoms confirmed in `pipeline/core/gate.py`:
the digest is only checked by `REQUIRED_SECTIONS` (non-empty string), and
`## Decisions checked` is only regex-matched for something ID-shaped
(`\b[A-Z]+-\d+\b|DEC-`) -- the ID is never resolved against `.project/decisions/`.
Failing test re-committed on `ticket/018` as `6738a26` (the earlier `2e908e9` was
lost when a rebase onto main conflicted and was aborted); see `## Reproduction`.

**Plan (2026-08-21, rewritten): two checks added to `pipeline/core/gate.py`.**
(1) `## Digest` must have at least `MIN_DIGEST_ENTRIES = 3` non-empty lines,
waived by one `digest-short: <why fewer>` line -- the escape hatch the design
conversation asked for. (2) Every `DEC-<n>` cited in `## Decisions checked` is
resolved against `.project/decisions/` via the existing `active_decisions()`: an
id with no record is a finding, a superseded one is an `ok:` note that does not
fail. The count check forces `tests/helpers.py:FIXTURE` to grow a real
three-entry digest, which drags three digest-matching call sites with it. Nine
steps, five files, one commit.

**This plan replaces an earlier one that DEC-017 forbids.** `main` moved while
this ticket sat at the human gate: the decisions directory went from one record
to five, and one of the new ones -- **DEC-017**, active -- says a test file the
gate copies onto base "may only import what base has". The earlier plan added
`from helpers import DIGEST, FIXTURE, project` to `tests/test_gate.py`, which is
precisely the banned move. It is replaced by a file-local `_set_digest()` helper
that derives the substitution from `FIXTURE` itself, needs no new import, and
asserts when it matches nothing -- which also kills the silent-stale-`.replace()`
hazard the earlier plan called its one gotcha. See `## Digest` for the measured
proof of both halves.

**Verified 2026-08-21 (this planning run):** every step below was executed in the
worktree and then reverted, so the code is transcribed from a run, not drafted.
Observed: step 4 leaves exactly the reproduction test red with the reported
`AssertionError`; step 9 gives `42 passed` on the two files and `176 passed` on
the whole suite; the guard script passes; the new test dies under three separate
mutations. The worktree is clean again and the reproduction test is red, which is
what the plan-validation gate requires.

**Plan-validation (2026-08-21, second run): PASS on all eight items.** Every
position claim in the rewritten plan was re-read against the worktree at
`6738a26` and holds: `gate.py` 13 / 89-91 / 141-144 / 190 / 8 / 19, `ticket.py`
223 / 231 / 235 / 243 / 258, the three digest call sites
(`tests/test_gate.py:49`, `:209`, `tests/test_ticket.py:22` -- grepped, exactly
three), `planning.md` bullets 22-23 and 24-38 with `- ## Plan` at 39. The
decisions directory in the **project root** holds five records, all with a
`pipeline:superseded-by` count of 0, so all five are active; DEC-017 was read in
full and does forbid the previous plan's `from helpers import DIGEST`, which the
file-local `_set_digest()` avoids. Step 8 (`pipeline/stages/planning.md`) has no
acceptance criterion and cannot have one -- no test reads that file (grepped,
zero hits) -- and is kept as the wiring half. Implementer notes: this ticket's
own `## Decisions checked` cites only resolvable active ids, so the new gate does
not lock the ticket out of a re-gate; and the guard blocks `python3 -c`, so the
`_set_digest` regex was verified by reading, not by running it in this stage.

## Reproduction

Test: `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id`

Command:

```sh
uv run --group dev pytest -q "tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id"
```

The test builds a ticket whose `## Digest` is the single word `x` and whose
`## Decisions checked` cites `DEC-999`, with no `.project/decisions/` at all,
then asserts the gate rejects it. It does not:

```
>       assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
E       AssertionError: one-word digest and unresolvable DEC-999 both passed the gate
E       assert not True

tests/test_gate.py:212: AssertionError
```

expect: one-word digest and unresolvable DEC-999 both passed the gate

## Digest

### Line numbers in this section were re-read on 2026-08-21 after main moved

The previous plan's line refs were stale (triage flagged this). Every number
below was re-read against `ticket/018` at `6738a26`. `pipeline/core/gate.py` grew
a base-check path (`_base_findings`) and `tests/test_gate.py` grew
`_git_ticket_project` plus two base-check tests, which is what moved everything.

### Where the two weak checks live

`pipeline/core/gate.py` -- the whole Tier A gate, ~196 lines.

- `REQUIRED_SECTIONS` (line 13) is the only thing that looks at `## Digest`. The
  loop is lines 89-91: `if not secs.get(name)`. One word passes.
- The decisions check is lines 141-144: `re.search(r"\b[A-Z]+-\d+\b|DEC-", dec)`
  after an early-out on `"none relevant"`. A *shape* match -- `DEC-999` and even
  `TICKET-012` satisfy it. Nothing opens `.project/decisions/`.
- Findings whose text starts with `ok:` are informational: **line 190** computes
  `failed = [f for f in findings if not f.startswith("ok:")]`, and only `failed`
  decides the verdict. That is the mechanism for "note it, do not fail it".
- The `pipeline.core.ticket` import is line 8.
- `_cites()` (line 19) is the existing path-citation helper used by the `## Plan`
  check. Not used by this change -- see `## Decisions`.

### What already exists to resolve a decision id

`pipeline/core/ticket.py` (all re-read, all moved from the old plan's numbers):

- `SAFE_DEC_ID = ^DEC-\d{1,6}$` (line 223) -- ids are always `DEC-<digits>`.
- `SUPERSEDED_MARKER` (line 231) is the HTML comment `record_decision()` appends
  to a superseded record. Grep for the marker, never for `- superseded-by:`;
  `tests/test_ticket.py::test_active_decisions_ignores_a_coincidental_superseded_by_line_in_body_text`
  exists because a loose scan drops an active record on a coincidence.
- `Decision` dataclass (line 235): `id`, `path`, `text`. `id` is the file stem.
- `decisions_dir(project) -> project/.project/decisions` (line 243).
- `active_decisions(project) -> list[Decision]` (line 256): every `DEC-*.md` in
  that directory that does not contain `SUPERSEDED_MARKER`, **skipping
  symlinks**. Returns `[]` when the directory does not exist -- no exception,
  which is what the reproduction test's fixture relies on (it has no
  `.project/decisions/` at all).

Resolve against `project`, not `workdir`: `gate()` already reads the ticket from
`ticket_path(project, tid)` (line 71), and `record_decision()` writes records to
the project root. The worktree copy is a checkout of the base branch and can be
stale.

### The DEC-017 constraint -- the thing that changed this plan

`pipeline/core/gate.py:_base_findings` (lines 28-66) copies **only the test
file** onto a throwaway checkout of base and runs it there:

```python
rel = test.split("::")[0]          # "tests/test_gate.py"
dst = base_wt / rel
shutil.copy2(wd / rel, dst)        # the branch's test, base's everything-else
```

`tests/helpers.py` is **not** copied. So a `from helpers import <new name>` added
to `tests/test_gate.py` on the branch raises `ImportError` on base, pytest exits
non-zero with a collection error, the node name never appears in the output, and
the `node not in out` guard (line 59) reports "errored rather than failed on
base". DEC-017 states this rule and names it as the reason `_git_ticket_project`
lives inside `tests/test_gate.py` rather than in `tests/helpers.py`.

Measured both ways during planning, by writing base's `tests/helpers.py` next to
the branch's `tests/test_gate.py` and importing:

| form | result |
|---|---|
| `_set_digest()` local to `tests/test_gate.py`, imports only `re` | `IMPORT OK`, and it works on base's one-line `FIXTURE` too |
| `from helpers import DIGEST, FIXTURE, project` | `ImportError: cannot import name 'DIGEST' from 'helpers'` |

The gate does not run again after `implementing` (`transition()` reaches the gate
only at `plan-validation` and `revalidating`), so the banned form would probably
not have bitten *this* ticket -- except via `("implementing", "blocked")`, which
routes back to `plan-validation` and re-gates a branch that already has the new
import. Either way DEC-017 is active and binding, so the plan complies rather
than gambling on the path not being taken.

### The fixture coupling

`tests/helpers.py:FIXTURE` is the canonical "complete ticket" and its `## Digest`
is a single line, `thing.py holds it` (line 25). A minimum-entry-count check
fails it, so `test_gate_passes_a_complete_ticket`,
`test_an_acceptance_criterion_must_name_something_test_shaped`,
`test_gate_passes_a_failure_that_matches_the_reported_one` and
`tests/test_ticket.py::test_the_dispatcher_writes_typed_thread_entries` (line
269, `assert gate(d, "TICKET-001")[0]`) all go red unless the fixture grows a
real digest.

Three places match that digest text and must move with it (re-grepped; these
three are the only ones):

| file:line | today |
|---|---|
| `tests/test_gate.py:49` | `.replace("## Digest\nthing.py holds it\n", "## Digest\n")` |
| `tests/test_gate.py:209` | `.replace("## Digest\nthing.py holds it\n", "## Digest\nx\n")` |
| `tests/test_ticket.py:22` | `t.section("Digest") == "thing.py holds it"` |

A stale `.replace()` here is **silent** -- it no-ops and the test then runs
against an unmodified fixture. `_set_digest()` (step 3) removes the hazard rather
than documenting it: it derives the span from `FIXTURE` and asserts `n == 1`, so
drift is loud. Do the fixture steps *before* the `gate.py` steps -- after step 4
the reproduction test must still be red for the reported reason, which proves the
substitution still bites.

### Code for each step

**Step 1** -- `tests/helpers.py`, line 25. Replace the single digest line with
three entries. This is the only edit to this file; no new export, so DEC-017 is
not engaged.

```python
## Digest
- thing.py holds it
- cache() is the entry point
- eviction runs on write, not read
## Decisions checked
```

(the `## Digest` and `## Decisions checked` lines already exist and are unchanged;
only `thing.py holds it` becomes the three `- ` entries)

**Step 2** -- `tests/test_ticket.py:22`:

```python
    assert t.klass == "bugfix" and t.section("Digest").startswith("- thing.py holds it")
```

**Step 3** -- `tests/test_gate.py`. Add `import re` above `import shutil` (line 2),
and insert this helper after the `from pipeline.core.gate import gate` import,
above `_git_ticket_project`:

```python
def _set_digest(body: str) -> str:
    """FIXTURE with its `## Digest` content replaced by `body`.

    Derived from the fixture rather than matched against a copy of its digest
    text: a `.replace()` of a literal that has drifted no-ops *silently* and
    leaves the test asserting against an unmodified fixture. The assert below
    is what makes that drift loud.

    Deliberately local to this file, and stdlib-only, rather than a constant
    imported from `helpers`: DEC-017 -- the gate copies THIS file onto a
    checkout of base and imports it there, so a name that exists only on the
    branch turns the base run into a collection error."""
    out, n = re.subn(r"(?<=^## Digest\n).*?(?=^## Decisions checked$)",
                     body, FIXTURE, flags=re.S | re.M)
    assert n == 1, "FIXTURE's `## Digest` section moved -- _set_digest is stale"
    return out
```

Then the two call sites. `tests/test_gate.py:49` becomes:

```python
    d = project(_set_digest(""))
```

and `tests/test_gate.py:209` becomes:

```python
    d = project(_set_digest("x\n")
                .replace("none relevant (grepped: cache, evict)", "DEC-999"))
```

**Step 5** -- `pipeline/core/gate.py`, module level, appended under the
`REQUIRED_SECTIONS` list (after line 16):

```python
# A digest exists so the next stage does not re-explore the codebase, and
# "non-empty" is satisfied by one word. Three lines is a floor, not a quality
# bar -- a digest that is genuinely shorter says so out loud in a line a human
# can see in review, rather than being padded to hit a number.
MIN_DIGEST_ENTRIES = 3
DIGEST_SHORT_RE = re.compile(r"^\s*digest-short:\s*\S", re.M)
# Only `DEC-<digits>` is resolvable: that is what `record_decision()` writes and
# all `SAFE_DEC_ID` allows. A `TICKET-012` in this section is prose, not a citation.
DEC_ID_RE = re.compile(r"\bDEC-\d{1,6}\b")
```

and, in `gate()`, immediately after the `REQUIRED_SECTIONS` loop (after line 91):

```python
    # An empty `## Digest` is already reported above; skip rather than double-report.
    dig = secs.get("Digest", "")
    if dig.strip() and not DIGEST_SHORT_RE.search(dig):
        entries = [l for l in dig.splitlines() if l.strip()]
        if len(entries) < MIN_DIGEST_ENTRIES:
            findings.append(
                f"`## Digest` has {len(entries)} non-empty line(s); want at least "
                f"{MIN_DIGEST_ENTRIES} (files touched, key functions, entry points, "
                f"gotchas) or one `digest-short: <why fewer>` line")
```

**Step 6** -- `pipeline/core/gate.py`, the import on line 8 becomes:

```python
from pipeline.core.ticket import (Ticket, active_decisions, decisions_dir,
                                  ticket_path)
```

and lines 141-144 are replaced by:

```python
    dec = secs.get("Decisions checked", "")
    cited = sorted(set(DEC_ID_RE.findall(dec)))
    if dec and "none relevant" not in dec.lower() and not cited:
        findings.append("`## Decisions checked` cites no decision IDs and no explicit "
                        "'none relevant' + grep terms")
    if cited:
        ddir = decisions_dir(project)
        # A symlinked record is not a record -- active_decisions() skips it, so
        # counting it as on-disk would report a planted link as merely superseded.
        on_disk = ({p.stem for p in ddir.glob("DEC-*.md") if not p.is_symlink()}
                   if ddir.is_dir() else set())
        active = {d.id for d in active_decisions(project)}
        for cid in cited:
            if cid not in on_disk:
                findings.append(
                    f"`## Decisions checked` cites {cid}, which is not a record in "
                    f"{ddir} -- a citation nobody can resolve is not a check")
            elif cid not in active:
                # a superseded record stays on disk as history; citing one is fine,
                # treating it as binding is the thing the plan must not do
                findings.append(f"ok: {cid} is superseded -- history, not binding")
```

**Step 7** -- `tests/test_gate.py`, appended at the end of the file (after
`test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id`, which is
currently last). `shutil` and `T` are already imported at lines 2 and 8:

```python
def test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest():
    """A cited id that resolves must not fail; a superseded one is history, not
    a finding; and a short digest passes only when it says why it is short."""
    d = project(_set_digest("digest-short: one file, one line\n"
                            "- thing.py holds it\n")
                .replace("none relevant (grepped: cache, evict)",
                         "checked DEC-002 (superseded) and DEC-003"))
    dec = d / ".project" / "decisions"
    dec.mkdir()
    (dec / "DEC-002.md").write_text(
        "# DEC-002\n\nold\n\n%s\n- superseded-by: DEC-003 (2026-08-21)\n"
        % T.SUPERSEDED_MARKER)
    (dec / "DEC-003.md").write_text("# DEC-003\n\nstill binding\n")
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    text = (d / ".project/tickets/TICKET-001.md").read_text()
    assert "DEC-002 is superseded" in text, text
    shutil.rmtree(d)
```

It is not vacuous. Three mutations were run against it during planning and each
turned it red:

| mutation | result |
|---|---|
| rename the `ok: {cid} is superseded` string | FAIL -- the note never reaches the ticket |
| point `DIGEST_SHORT_RE` at something unmatchable | FAIL -- the two-line digest fails the count |
| `elif cid not in active:` -> `elif True:` **and** drop the `ok:` prefix | FAIL -- `ok` goes false |

The third mutation is stated precisely because the obvious version of it does
not work: changing only `elif cid not in active:` to `elif True:` leaves the test
**green**, since the extra finding still carries the `ok:` prefix that line 190
excludes from the verdict. Dropping the prefix is what makes a resolvable id
fail. Anyone re-deriving this list will hit the same trap.

**Step 8** -- `pipeline/stages/planning.md`. Two continuation lines, each appended
to the **end** of a bullet, not after the bullet's first line, indented by 2
spaces so they stay part of the bullet. Line numbers re-read and still current:

- the `## Digest` bullet spans lines 22-23 and ends `...re-explores the codebase
  from scratch.` -- insert after line 23;
- the `## Decisions checked` bullet spans lines 24-38 and ends ``...with
  `supersedes: DEC-<n> -- reason`, below.`` -- insert after line 38, before the
  `- ## Plan` bullet that starts on line 39.

```
  Tier A counts the section's non-empty lines and wants at least three (files
  touched, key functions, entry points, gotchas); if this change genuinely needs
  fewer, write one `digest-short: <why fewer>` line and the count is waived.
```

```
  Tier A resolves every `DEC-<n>` you cite against that directory: an id with no
  record there fails the gate, and a superseded one is recorded as history rather
  than as a constraint.
```

### Gotchas the implementer will otherwise hit

- **The dangerous-commands guard blocks heredocs and `python -c` with complex
  quoting** from a stage prompt ("command does not parse as a shell command").
  Both triage and this stage hit it. Use the file-edit tool for every edit below.
- **`pytest` does not collect the guard's tables.** Run
  `./pipeline/hooks/test_dangerous_commands.py` directly. This change does not
  touch the guard, but the repo's rule stands; it passed during planning.
- **`tests/test_ticket.py` has four pre-existing Pyright complaints** at lines
  367-383 (`Argument of type "None" ... parameter "path"`). They are not from
  this change and are out of scope -- do not "fix" them in this commit.

### Commands

```sh
uv run --group dev pytest -q tests/test_gate.py tests/test_ticket.py
uv run --group dev pytest -q
./pipeline/hooks/test_dangerous_commands.py
```

## Decisions checked

`.project/decisions/` now holds **five** records: DEC-011, DEC-016, DEC-017,
DEC-019, DEC-020. None carries the `<!-- pipeline:superseded-by -->` marker
(`grep -c` returns 0 for all five), so all five are active and binding. The
previous plan's claim that this directory held only DEC-011 was written before
main moved and was stale; all five were re-read for this plan.

- **DEC-017 -- consulted, and it changed this plan.** "Test files that the gate
  copies onto base may only import what base has." The previous plan added
  `from helpers import DIGEST, ...` to `tests/test_gate.py`, which is exactly the
  banned move; measured, it raises `ImportError` against base's `tests/helpers.py`.
  Replaced with the file-local `_set_digest()` (stdlib `re` only). DEC-017 also
  requires the base run and the `node not in out` guard to stay -- this change
  touches neither `_base_findings` nor `base_ref`. **Complies; nothing superseded.**
- **DEC-016 -- consulted, complies, and it simplifies the plan.** Fence state is
  parsed once in `_fenced()` and every heading scan consults it, so
  `sections()` (`pipeline/core/ticket.py:139`) does not read a `##` line inside a
  fenced block as a heading. That is why this ticket's `## Digest` can show the
  fixture's own `## Digest` line verbatim inside a ```` ```python ```` fence with
  no indent dodge. This change adds no fourth heading scan and keeps storage as
  plain markdown.
- **DEC-011 -- consulted, complies.** It freezes the event vocabulary; the `gate`
  kind carries `{verdict, findings:[...]}`. This change only adds new strings to
  `findings`, which DEC-011 calls out as additive and fine. No column, kind name
  or field meaning changes.
- **DEC-019 -- read, not relevant.** TUI resize/writer semantics
  (`pipeline/tui/app.py`); no overlap.
- **DEC-020 -- read, not relevant.** Stdout line buffering in the two entry
  points; no overlap.

Grep terms used across `.project/decisions/`: `gate`, `digest`,
`Decisions checked`, `Tier A`, `DEC-`, `decision`, `helpers`, `import`,
`superseded`, `symlink`.

## Plan

1. In `tests/helpers.py`, replace the single digest line `thing.py holds it` (line 25) with the three `- ` entries shown under "Step 1" in `## Digest`, leaving the surrounding `## Digest` and `## Decisions checked` header lines untouched and adding no new module-level name.
2. In `tests/test_ticket.py`, change the exact-equality digest assertion on line 22 to the `startswith("- thing.py holds it")` form shown under "Step 2" in `## Digest`.
3. In `tests/test_gate.py`, add `import re` at line 2 and insert the `_set_digest()` helper verbatim from "Step 3" in `## Digest` after the `gate` import, then switch the two digest call sites (lines 49 and 209) to it; do NOT add any new name to the `from helpers import` line, per DEC-017.
4. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_ticket.py` and confirm the only red is `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id`, still failing with `AssertionError: one-word digest and unresolvable DEC-999 both passed the gate` -- any other message means step 3's helper in `tests/test_gate.py` is wrong, and its own `assert n == 1` should have said so.
5. In `pipeline/core/gate.py`, add `MIN_DIGEST_ENTRIES`, `DIGEST_SHORT_RE` and `DEC_ID_RE` after the `REQUIRED_SECTIONS` list (line 16), and insert the digest entry-count check right after the `REQUIRED_SECTIONS` loop (line 91), both verbatim from "Step 5" in `## Digest`.
6. In `pipeline/core/gate.py`, widen the line-8 import to bring in `active_decisions` and `decisions_dir`, and replace the `## Decisions checked` block at lines 141-144 with the resolution block verbatim from "Step 6" in `## Digest`.
7. In `tests/test_gate.py`, append `test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest` verbatim from "Step 7" in `## Digest` to the end of the file.
8. In `pipeline/stages/planning.md`, insert the two 2-space-indented continuation lines from "Step 8" in `## Digest` after line 23 and after line 38 respectively, so the agent that must satisfy these checks is told the rule.
9. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_ticket.py`, then `uv run --group dev pytest -q`, then `./pipeline/hooks/test_dangerous_commands.py`, confirm all three are green, and commit `pipeline/core/gate.py`, `tests/helpers.py`, `tests/test_gate.py`, `tests/test_ticket.py` and `pipeline/stages/planning.md` in one commit.

## Acceptance criteria

- `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id`
  passes: a one-word digest and an unresolvable `DEC-999` are both findings.
- `tests/test_gate.py::test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest`
  passes: a cited active id is silent, a cited superseded id lands in the ticket as
  `DEC-002 is superseded` without failing the gate, and a `digest-short:` line waives
  the entry count.
- `tests/test_gate.py::test_gate_passes_a_complete_ticket` still passes -- the
  three-entry fixture digest clears `MIN_DIGEST_ENTRIES`.
- `tests/test_gate.py::test_gate_blocks_an_empty_digest` still passes via the
  rewritten `_set_digest("")` call site -- the `assert n == 1` inside
  `_set_digest` is what fails loudly if the fixture's digest span ever moves,
  which is the check no test previously had.
- `tests/test_ticket.py::test_unknown_frontmatter_survives_a_save` and
  `tests/test_ticket.py::test_the_dispatcher_writes_typed_thread_entries` still
  pass -- the fixture change did not break the round-trip or the `gate()` call at
  `tests/test_ticket.py:269`.
- Whole run of `uv run --group dev pytest -q tests/test_gate.py tests/test_ticket.py`
  is green at step 9 -- observed during planning as `42 passed`.
- The whole `tests/` suite, `uv run --group dev pytest -q`, is green -- observed
  during planning as `176 passed`. Seven files import `tests/helpers.py`, so the
  fixture change is not confined to the two files that match its digest.
- `./pipeline/hooks/test_dangerous_commands.py` still exits 0 -- observed during
  planning as `guard: all passed`. Not collected by pytest, so the suite run
  above does not cover it.

## Decisions

The Tier A gate resolves every `DEC-<n>` cited in `## Decisions checked` against
`.project/decisions/` **in the project root**, never the worktree: the worktree is
a checkout of the base branch and its `.project/decisions/` can be stale, while
`record_decision()` writes to the root and `gate()` already reads the ticket from
there. Resolving against `workdir` would let a plan cite a record that was
superseded after the branch was cut.

**`tests/test_gate.py` must never grow a new `from helpers import` name.** This is
DEC-017's rule and it is why `_set_digest()` is a file-local function rather than
a `DIGEST` constant in `tests/helpers.py`, which is the obvious and wrong
refactor. The gate copies only the test file onto a checkout of base
(`pipeline/core/gate.py:_base_findings`, `shutil.copy2(wd / rel, dst)`);
`tests/helpers.py` stays at base's version, so a branch-only name is an
`ImportError` there, which the gate reports as "errored rather than failed on
base" -- blocking the very ticket that added it. Measured, not assumed: the
banned form raises `ImportError: cannot import name 'DIGEST' from 'helpers'`
against base's helpers, and `_set_digest()` imports clean. If a later change
wants to share digest-editing with another test file, copy the function; do not
hoist it into `tests/helpers.py`.

`_set_digest()` asserts `n == 1` on its own `re.subn`, and that assert is the
point of the function, not decoration. The pattern it replaces -- a
`.replace("## Digest\nthing.py holds it\n", ...)` literal -- fails *silently*
when the fixture drifts: the replace no-ops and the test then asserts against an
unmodified fixture, passing vacuously. Do not simplify the assert away.

Three rules that look arbitrary and are not:

- **A cited id with no record fails; a superseded one is a note, not a failure.**
  Superseded records stay on disk on purpose (they are still why something was
  once done that way), so citing one is legitimate; only treating it as *binding*
  is wrong, and that is Tier B judgment, not a deterministic check. The note is
  emitted with the `ok:` prefix, which `pipeline/core/gate.py:190` excludes from
  the verdict. **Do not "fix" that prefix away** -- it is load bearing, and
  dropping it is exactly what turns a resolvable citation into a gate failure.
  Confirmed by mutation during planning: remove the prefix and
  `test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest`
  goes red, so the test does defend it.
- **A symlinked `DEC-*.md` counts as absent, not as superseded.** `active_decisions()`
  skips symlinks (invariant 5: never follow a planted link), so including them in
  the on-disk set would report a planted link as merely superseded -- the quietest
  possible outcome for the most hostile input.
- **`DEC_ID_RE` is `DEC-<digits>` only**, deliberately narrower than the old
  `\b[A-Z]+-\d+\b`, which accepted `TICKET-012` as a decision citation. Every id
  `record_decision()` can produce matches `SAFE_DEC_ID`; anything else in that
  section is prose. Consequence, intended: a `## Decisions checked` whose only
  citation is `TICKET-<n>`-shaped now fails where it used to pass.

`MIN_DIGEST_ENTRIES = 3` counts non-empty lines and is a floor, not a quality bar
-- three empty bullets still pass it. Its job is to kill the degenerate one-word
digest; judging whether a digest is *useful* is the plan-validation stage's.
`digest-short:` is the deliberate escape hatch from the design conversation
("minimum N entries or explicit justification for fewer"): an agent that needs
fewer says why in a line a human can grep, instead of padding to a number.

## Rollback

Revert the single commit from step 9. It is self-contained: `pipeline/core/gate.py`
returns to the two non-emptiness checks, `tests/helpers.py` to the one-line digest,
`tests/test_gate.py` loses `_set_digest` and the new test, and
`tests/test_ticket.py` returns to exact equality. Nothing else imports
`MIN_DIGEST_ENTRIES`, `DIGEST_SHORT_RE` or `DEC_ID_RE`, no on-disk format
changes, and no ticket already merged becomes invalid -- the checks only run when
a ticket passes the gate again. Partial rollback is not safe: reverting
`pipeline/core/gate.py` alone leaves
`tests/test_gate.py::test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest`
red, and reverting `tests/helpers.py` alone trips `_set_digest`'s own
`assert n == 1` only if the headers move -- otherwise it silently restores the
one-line digest that `MIN_DIGEST_ENTRIES` rejects, turning four tests red.

## Thread

### 2026-08-21 03:13:42Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 03:33:42Z · human · note

**resumed** by human -> `triage`, reset ['blocked_count', 'lease_expiries', 'no_result']

### 2026-08-21 · triage · reproduced

Read `pipeline/core/gate.py`. Confirmed both halves of the report:

- `## Digest` appears only in `REQUIRED_SECTIONS`; the sole check is
  `if not secs.get(name)`. No entry count, no justification line.
- `## Decisions checked` is checked by
  `re.search(r"\b[A-Z]+-\d+\b|DEC-", dec)` after an early-out on
  `"none relevant"`. A shape match, not a lookup -- `DEC-999` satisfies it.

Wrote `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id`
in the file's existing style (plain asserts, `project()`/`FIXTURE` from
`tests/helpers.py`, `shutil.rmtree` at the end). It fails with
`AssertionError: one-word digest and unresolvable DEC-999 both passed the gate`
-- i.e. `gate()` returned `ok=True` for a ticket that is exactly the reported
symptom, not a setup error. Committed as 2e908e9 on `ticket/018`.

One test covers both symptoms deliberately: the gate only runs the single
`test_file` it is given, so splitting them would leave one half unproven at the
plan-validation gate.

Note for the next stage, out of scope here: the guard blocked a `cat >> file
<<'EOF'` heredoc with "command does not parse as a shell command". Not a
finding against this ticket, just a thing to know when editing files from a
stage prompt -- use the file-edit tool.

### 2026-08-21 03:49:47Z · triage · session · session=ba10840a-e7c2-4130-ab56-3a71743de6dc

`triage` ran as session `ba10840a-e7c2-4130-ab56-3a71743de6dc`
- replay: `claude --resume ba10840a-e7c2-4130-ab56-3a71743de6dc`
- log: `.project/logs/TICKET-018-triage-ba10840a.log`

### 2026-08-21 03:49:47Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

reproduced -- gate() passes a one-word digest and an unresolvable DEC-999; failing test committed as 2e908e9

### 2026-08-21 · planning · note

Plan written. Read `pipeline/core/gate.py`, `pipeline/core/ticket.py`,
`tests/test_gate.py`, `tests/helpers.py`, `pipeline/stages/planning.md` and the
design conversation the ticket quotes (`skydeckai-conversation-316269.md:282`).

Three judgment calls the next stages should know about, so nobody re-litigates
them:

1. **`N` was never chosen by the design.** The checklist says "minimum N entries"
   literally. Picked 3, counted as non-empty lines, with the `digest-short:`
   hatch the same line asks for. It is a floor against the degenerate case, not a
   quality bar -- that is Tier B's job.
2. **Considered and skipped: requiring `## Digest` to name a declared file** (it
   would reuse `_cites()`, already in `gate.py`, and is arguably harder to game
   than any line count). Skipped because the ticket asks for an entry count, and
   stacking a second, un-asked-for check risks bouncing legitimate plans whose
   digest describes files they only read. Worth filing separately if the count
   turns out to be gameable in practice.
3. **The fixture had to change.** `tests/helpers.py:FIXTURE` has a one-line
   digest, so any count `>= 2` fails four currently-green tests. The alternative
   was a rule tuned to pass a three-word fixture, which is not a rule. The plan
   orders the fixture edits first so step 4 proves the reproduction test is still
   red for the reported reason before `gate.py` is touched.

Also checked, no change needed: `.project/known-issues.md:9` already lists this
ticket under "already filed", not as an open issue; `README.md` does not enumerate
the Tier A checks, so only `pipeline/stages/planning.md` needs the new rules
documented.

Noted the triage warning about the guard and heredocs -- this stage wrote the
ticket with the file-edit tool, no `cat >>`.

### 2026-08-21 04:23:15Z · planning · note

`planning` was interrupted; lease released

### 2026-08-21 · planning · note

Resumed after the interrupt. The previous run had already written a complete
plan; this run did not rewrite it from scratch. It **executed** all nine steps
in the worktree, kept what survived, corrected what did not, then reverted the
worktree to clean. No rejection entries in the thread, so nothing to answer.

What changed against the interrupted run's plan:

1. **Step 1 now gives exact source, not splice prose.** The old step described
   the `FIXTURE` edit in words ("close the triple-quoted string, reopen it on
   the decisions header line") because printing the fixture would put `## Digest`
   at column 0 and `sections()` would eat it as a section of this ticket. The
   indent-by-4 dodge solves that -- `^##` does not match `    ##` -- so the
   implementer now gets the literal block to write. Executed and diffed: the new
   `FIXTURE` differs from HEAD's only in the digest body.
2. **The new test's non-vacuity claim was wrong and is fixed.** The old plan
   claimed "flag resolvable ids and `ok` goes false". It does not: changing
   `elif cid not in active:` to `elif True:` leaves the test green, because the
   extra finding still carries the `ok:` prefix that line 147 filters out of the
   verdict. The prefix must also be dropped. All three mutations are now in a
   table in `## Digest`, each one run.
3. **Step 8's line numbers pointed at bullet starts, not insertion points.**
   The `## Decisions checked` bullet runs lines 24-38; appending "to line 24"
   would have landed the sentence mid-bullet. Both insertion points are now
   spelled out, with the 2-space indent that keeps them inside the bullet.
4. **Added a whole-suite acceptance criterion.** Seven test files import
   `tests/helpers.py`; the old criteria only covered the two that string-match
   its digest. `164 passed` observed.

Confirmed unchanged from the interrupted run, by reading the code: `gate.py`
lines 12-15, 47-49, 98-101 and 147; `ticket.py` `active_decisions`,
`decisions_dir`, `SUPERSEDED_MARKER`, `SAFE_DEC_ID`; the three digest call sites
at `tests/test_gate.py:18`, `tests/test_gate.py:156`, `tests/test_ticket.py:22`;
DEC-011 is the only decision record and is not superseded. No test reads
`pipeline/stages/planning.md`, so step 8 is documentation-only.

Left the worktree clean and the reproduction test red on purpose -- if the
verification edits had been left in place, `test_one` would PASS at the
plan-validation gate and the gate would reject the plan for it.

Hit the guard gotcha triage flagged: `python3 - <<'PY'` was blocked with
"command does not parse as a shell command". Used the file-edit tool. Worth
knowing for the implementation stage -- heredocs are not available to it either.

### 2026-08-21 04:29:43Z · planning · session · session=d1e42539-c068-4c28-93d7-4c16583269f9

`planning` ran as session `d1e42539-c068-4c28-93d7-4c16583269f9`
- replay: `claude --resume d1e42539-c068-4c28-93d7-4c16583269f9`
- log: `.project/logs/TICKET-018-planning-d1e42539.log`

### 2026-08-21 04:29:43Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

plan written and verified by executing all nine steps in the worktree then reverting; corrected the interrupted run's fixture-splice prose, a wrong non-vacuity claim, and step 8's line numbers

### 2026-08-21 04:37:05Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id` fails as required
```
==== FAILURES ===================================
______ test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id ______

    def test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id():
        """Both Tier A content checks are non-emptiness only: a digest of one word
        passes, and a cited `DEC-999` passes though no such record exists in
        `.project/decisions/`."""
        d = project(FIXTURE.replace("## Digest\nthing.py holds it\n", "## Digest\nx\n")
                           .replace("none relevant (grepped: cache, evict)", "DEC-999"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
E       AssertionError: one-word digest and unresolvable DEC-999 both passed the gate
E       assert not True

tests/test_gate.py:212: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```

### 2026-08-21 04:37:46Z · plan-validation · note

`plan-validation` was interrupted; lease released

### 2026-08-21 05:06:10Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id` fails as required
```
==== FAILURES ===================================
______ test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id ______

    def test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id():
        """Both Tier A content checks are non-emptiness only: a digest of one word
        passes, and a cited `DEC-999` passes though no such record exists in
        `.project/decisions/`."""
        d = project(FIXTURE.replace("## Digest\nthing.py holds it\n", "## Digest\nx\n")
                           .replace("none relevant (grepped: cache, evict)", "DEC-999"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
E       AssertionError: one-word digest and unresolvable DEC-999 both passed the gate
E       assert not True

tests/test_gate.py:212: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```

### 2026-08-21 · plan-validation · note

**Tier B: PASS.** Every claim of position and content in the plan was re-read
against the worktree, not taken on trust. Item by item:

- **Root cause, stated independently.** `gate()` never inspects the *content* of
  the two sections it names. `## Digest` is reached only by the `REQUIRED_SECTIONS`
  loop (`gate.py:47-49`, `if not secs.get(name)`), so any single character passes;
  `## Decisions checked` is a shape match (`gate.py:99`,
  `re.search(r"\b[A-Z]+-\d+\b|DEC-", dec)`) that never opens
  `.project/decisions/`. Both checks answer "is there text here", and the design
  asked "is there a check here". The plan changes the two checks in `gate.py`,
  which is where the wrong question is asked -- it does not special-case the
  reproduction ticket, and the new checks bite on any ticket, so this is the root
  cause and not the symptom.
- **Decision conflict: none.** `.project/decisions/` holds exactly one record and
  it is `DEC-011` (verified by `ls`; `pipeline:superseded-by` marker count is 0,
  so it is active and binding). Read it: it freezes the SQLite schema, the event
  kind vocabulary and the socket protocol, and states in the record itself that
  "Adding a `kind` or a field inside `data` is additive and fine". This change
  adds only new strings to the existing `gate` event's `findings` list -- no
  column, no kind, no changed field meaning. Complies; no superseding record
  needed. The plan's citation is accurate, not decorative.
- **Scope: one step is not covered by a criterion, and it should not be dropped.**
  Steps 1-3 (the `DIGEST` constant and the three call sites) are forced by the
  count check and are covered by the "still passes" criteria; steps 5-7 map to the
  two behavioural criteria; steps 4 and 9 are the two verification runs. Step 8
  (`pipeline/stages/planning.md`) has no acceptance criterion and cannot have one
  -- no test in `tests/` reads that file (grepped: zero hits). It is the wiring
  half of the change: a gate rule the planning stage is never told about would
  bounce every future plan for a rule it was never given. Documentation-only, two
  continuation lines, no code path. Kept.
- **Criteria are falsifiable.** The reproduction test fails today with the quoted
  `AssertionError`, and the new
  `test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest`
  carries three executed mutations, including the trap that the obvious mutation
  (`elif cid not in active:` -> `elif True:`) leaves it *green* because the `ok:`
  prefix is filtered at `gate.py:147`. That is the opposite of a vacuous test.
  One criterion overstates slightly: `test_gate_blocks_an_empty_digest` asserts
  `any("Digest" in f ...)` and so would still pass if an empty digest were
  reported twice -- the `if dig.strip()` guard is what prevents the double report,
  and no test pins it. Not worth a bounce; noted for review.
- **No research left.** Every step names a file, a line range and verbatim code.
  Spot-checked every position: `REQUIRED_SECTIONS` is `gate.py:12`, the decisions
  block is `gate.py:98-101`, the `ok:` filter is `gate.py:147`, the import is
  `gate.py:7`; `decisions_dir` `ticket.py:209`, `active_decisions` `ticket.py:224`,
  `SUPERSEDED_MARKER` `ticket.py:197`, `SAFE_DEC_ID` `ticket.py:189`;
  `helpers.py` lines 6-35 are exactly `ROOT` through the close of `FIXTURE`;
  `planning.md`'s `## Digest` bullet is lines 22-23 and the `## Decisions checked`
  bullet is 24-38 with `- ## Plan` starting at 39. All correct.
- **Riskiest step: the fixture splice (step 1), and its tripwire is step 4.**
  A stale `.replace()` no-ops silently, leaving a test asserting against an
  unmodified fixture -- the failure mode that looks green. The plan names it,
  routes all three call sites through one `DIGEST` constant, orders the fixture
  edits before `gate.py`, and states the fallback: at step 4 the reproduction test
  must still be red with the *reported* message, and any other message means step 3
  is wrong. A print-the-fixture command is given as the second check. Adequate.
- **Regression surface, independently enumerated.** Grepped for the digest text:
  exactly three string-match sites exist (`test_gate.py:18`, `test_gate.py:156`,
  `test_ticket.py:22`), matching the plan's table -- no fourth. `test_ticket.py:269`
  calls `gate()` on the default fixture, whose `## Decisions checked` says "none
  relevant", so it never reaches the new lookup and only needs the three-entry
  digest. Seven test files import `helpers`; the whole-suite criterion covers them.
  One behaviour change is wider than the tests: `DEC_ID_RE` is narrower than the old
  `\b[A-Z]+-\d+\b`, so a `## Decisions checked` whose only citation is
  `TICKET-012`-shaped now fails where it passed. No existing test covers that
  branch, and the plan argues the narrowing deliberately in `## Decisions`. It is
  a tightening of a gate, applied to tickets that re-enter the gate -- intended,
  not collateral.
- **Blast radius matches `bugfix`.** Five files, one commit: one production file
  (`pipeline/core/gate.py`), three test files dragged in by the fixture coupling,
  one prompt file for the rule text. No new module, no dependency, no format change.

Verdict: pass. Nothing here needs the plan reworked.

### 2026-08-21 05:10:07Z · plan-validation · session · session=83d75974-3658-44e9-8ddd-cff49532461c

`plan-validation` ran as session `83d75974-3658-44e9-8ddd-cff49532461c`
- replay: `claude --resume 83d75974-3658-44e9-8ddd-cff49532461c`
- log: `.project/logs/TICKET-018-plan-validation-83d75974.log`

### 2026-08-21 05:10:07Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

plan validated on all eight items -- root cause is gate.py's content-blind checks, DEC-011 complies, line refs and the three digest call sites verified against the worktree; step 8 (planning.md) has no criterion by design and is kept as wiring

### 2026-08-21 05:11:33Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 05:24:24Z · revalidating · escalation

rebase onto base conflicted (exit 1)
```
$ git rebase main

Rebasing (1/1)
Auto-merging tests/test_gate.py
CONFLICT (content): Merge conflict in tests/test_gate.py
error: could not apply 2e908e9... test: gate accepts a one-word digest and an unresolvable decision id
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply 2e908e9... # test: gate accepts a one-word digest and an unresolvable decision id

```

### 2026-08-21 05:56:30Z · human · note

**resumed** by human -> `triage`, reset ['plan_validation_attempts', 'review_loops', 'blocked_count', 'no_result', 'lease_expiries']

### 2026-08-21 · triage · re-reproduced

The test from the first triage (2e908e9) was not on `ticket/018` any more -- the
aborted rebase left the branch at the ticket/019 merge (4ed4307). Cherry-picked
it back; the conflict was a pure append collision with main's two new base-check
tests, resolved by keeping both. Committed as `6738a26`.

Still red for the reported reason:
`AssertionError: one-word digest and unresolvable DEC-999 both passed the gate`
(now at `tests/test_gate.py:212`).

Outside this stage, for whoever implements: `main` has moved since `## Digest`
was written (a base-check path was added to `gate.py`, and `tests/test_gate.py`
grew `_git_ticket_project` plus two base-check tests). The digest's *line
numbers* for `gate.py` are stale; the named symbols and the three fixture call
sites still hold -- re-grep before trusting a line ref.

### 2026-08-21 05:57:49Z · triage · session · session=f25e5b92-08ff-4c45-827f-14371241d5a5

`triage` ran as session `f25e5b92-08ff-4c45-827f-14371241d5a5`
- replay: `claude --resume f25e5b92-08ff-4c45-827f-14371241d5a5`
- log: `.project/logs/TICKET-018-triage-f25e5b92.log`

### 2026-08-21 05:57:49Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

reproduction test restored on ticket/018 as 6738a26 (lost to an aborted rebase) and confirmed red with the reported AssertionError

### 2026-08-21 · planning · note

Re-planned after triage restored the reproduction test (`6738a26`). No
`rejection` entries in the thread, so nothing to answer; this run existed because
the ticket came back to `planning` from the aborted rebase, and triage warned
that main had moved under the previous plan's line references.

**The previous plan was not merely stale -- one step is forbidden by an active
decision record.** Re-grepping `.project/decisions/` found five records, not the
one the old plan cited. **DEC-017** (added by TICKET-017 while this ticket waited
at the human gate) says a test file the gate copies onto base "may only import
what base has". The old step 3 added `from helpers import DIGEST, FIXTURE,
project` to `tests/test_gate.py`. Measured against base's `tests/helpers.py`:
`ImportError: cannot import name 'DIGEST' from 'helpers'` -- which the gate
reports as "errored rather than failed on base". Replaced with a file-local
`_set_digest()` using stdlib `re` only, which imports clean against base and, as
a bonus, `assert`s when its substitution matches nothing -- removing the silent
stale-`.replace()` hazard the old plan called its one gotcha rather than just
documenting it.

Other corrections to the previous plan:

1. **Every line number was stale.** `gate.py`'s `REQUIRED_SECTIONS` is line 13
   not 12, its loop 89-91 not 47-49, the decisions block 141-144 not 98-101, the
   `ok:` filter **190** not 147, the import 8 not 7. `ticket.py`'s helpers moved
   too: `decisions_dir` 243, `active_decisions` 256, `SUPERSEDED_MARKER` 231,
   `SAFE_DEC_ID` 223. The digest call sites are `tests/test_gate.py:49` and
   `:209`, not 18 and 156. `tests/test_ticket.py:22`, `tests/test_ticket.py:269`
   and `pipeline/stages/planning.md`'s bullets (22-23, 24-38, 39) were the only
   references that still held.
2. **The old step 1's "indent by 4, de-indent before writing" dodge is obsolete.**
   DEC-016 made `sections()` consult `_fenced()`, so a `##` line inside a fenced
   block is no longer read as a heading. The plan now shows the fixture hunk
   plainly inside a fence. That also let step 1 shrink from a 30-line block
   replacement to a one-line-to-three-lines edit, which is a smaller thing to get
   wrong.
3. **The decisions citation was wrong on its face.** The old `## Decisions
   checked` asserted the directory held "exactly one record: DEC-011". It holds
   five. All five re-read; DEC-017 and DEC-016 are the two that bite, DEC-011
   still complies, DEC-019 and DEC-020 are unrelated.

Verified by executing all nine steps in the worktree and then reverting:

- step 4 leaves exactly one red, the reproduction test, with the reported
  `AssertionError: one-word digest and unresolvable DEC-999 both passed the gate`;
- step 9 gives `42 passed` on the two files, `176 passed` on the whole suite, and
  `guard: all passed` on `./pipeline/hooks/test_dangerous_commands.py`;
- the new test dies under all three mutations tabulated in `## Digest`,
  including the trap one (`elif True:` alone leaves it **green** -- the `ok:`
  prefix must also be dropped).

The worktree is clean again and the reproduction test is red on purpose: leaving
the verification edits in place would make it PASS at the plan-validation gate
and the gate would reject the plan for it.

Out of scope, noted not fixed: `tests/test_ticket.py` lines 367-383 carry four
pre-existing Pyright `Argument of type "None" ... parameter "path"` complaints,
untouched by this ticket. Also re-hit the guard gotcha triage flagged -- a
`python -c` with nested quoting was blocked as "command does not parse as a shell
command"; used the file-edit tool throughout, and the implementer will need to as
well.

### 2026-08-21 06:06:15Z · planning · session · session=75b23189-48a0-4b93-bc71-bb6fdaa60e76

`planning` ran as session `75b23189-48a0-4b93-bc71-bb6fdaa60e76`
- replay: `claude --resume 75b23189-48a0-4b93-bc71-bb6fdaa60e76`
- log: `.project/logs/TICKET-018-planning-75b23189.log`

### 2026-08-21 06:06:15Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

plan rewritten after re-reading the decisions dir (now 5 records, not 1) -- the previous plan's step 3 is forbidden by active DEC-017 (a test file the gate copies onto base may only import what base has); replaced the helpers `DIGEST` constant with a file-local `_set_digest()` and refreshed every stale line ref; all 9 steps executed in the worktree then reverted (176 passed, guard passed, new test dies under 3 mutations)

### 2026-08-21 06:06:24Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id` fails as required
```
==== FAILURES ===================================
______ test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id ______

    def test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id():
        """Both Tier A content checks are non-emptiness only: a digest of one word
        passes, and a cited `DEC-999` passes though no such record exists in
        `.project/decisions/`."""
        d = project(FIXTURE.replace("## Digest\nthing.py holds it\n", "## Digest\nx\n")
                           .replace("none relevant (grepped: cache, evict)", "DEC-999"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
E       AssertionError: one-word digest and unresolvable DEC-999 both passed the gate
E       assert not True

tests/test_gate.py:212: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```

### 2026-08-21 06:06:32Z · plan-validation · note

`plan-validation` was interrupted; lease released

### 2026-08-21 07:05:12Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id` fails as required
```
==== FAILURES ===================================
______ test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id ______

    def test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id():
        """Both Tier A content checks are non-emptiness only: a digest of one word
        passes, and a cited `DEC-999` passes though no such record exists in
        `.project/decisions/`."""
        d = project(FIXTURE.replace("## Digest\nthing.py holds it\n", "## Digest\nx\n")
                           .replace("none relevant (grepped: cache, evict)", "DEC-999"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
E       AssertionError: one-word digest and unresolvable DEC-999 both passed the gate
E       assert not True

tests/test_gate.py:212: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id` fails on base `main` too -- the bug is not already fixed upstream
```
(grepped: cache, evict)", "DEC-999"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
E       AssertionError: one-word digest and unresolvable DEC-999 both passed the gate
E       assert not True

tests/test_gate.py:212: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-hhpskby7/base
      Built pipeline @ file:///tmp/pipeline-base-hhpskby7/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 · plan-validation · note

**Tier B: PASS.** This is a re-validation of a *rewritten* plan (the previous
Tier B note in this thread validated the plan DEC-017 later forbade -- its line
refs and its "exactly one decision record" claim are both stale, do not read it
as current). Every position claim below was re-read against the worktree at
`6738a26`, not taken on trust.

- **Root cause, stated independently.** `gate()` asks "is there text here" where
  the design asked "is there a check here". `## Digest` is reached only by the
  `REQUIRED_SECTIONS` loop (`gate.py:89-91`, `if not secs.get(name)`), so one
  character passes; `## Decisions checked` is a shape match (`gate.py:142`,
  `re.search(r"\b[A-Z]+-\d+\b|DEC-", dec)`) that never opens
  `.project/decisions/`, so a citation is never resolved against a referent. The
  plan changes those two checks in `gate.py` -- where the wrong question is asked
  -- and the new checks bite on every ticket, not on the reproduction fixture.
  Root cause, not symptom.
- **Decision conflict: five records, all active, two bite, plan complies.**
  `grep -c "pipeline:superseded-by"` returns 0 for DEC-011, DEC-016, DEC-017,
  DEC-019 and DEC-020 in the **project root** (the worktree's copy still holds
  only DEC-011, which is exactly why the plan resolves against the root -- its
  `## Decisions` says so and that reasoning is correct). DEC-017 read in full: it
  does say "Test files that the gate copies onto base may only import what base
  has", and names `_git_ticket_project` living in `tests/test_gate.py` for that
  reason. The plan's file-local `_set_digest()` adds no name to the existing
  `from helpers import FIXTURE, project` (line 7), so it complies rather than
  supersedes; it also touches neither `_base_findings` nor `base_ref`, which
  DEC-017 requires kept. DEC-016 read: `sections()` consults `_fenced()`
  (`ticket.py:143`), which is what lets this ticket print `## Digest` at column 0
  inside a fence -- the plan's claim is accurate and the ticket's own sections
  parse correctly, as the Tier A PASS above shows. DEC-011 (event vocabulary
  frozen; new `findings` strings are additive) complies. DEC-019 and DEC-020 are
  TUI resize and stdout buffering -- correctly called irrelevant.
- **Scope: one step has no criterion, deliberately, and is kept.** Steps 1-3 are
  forced by the count check (the fixture's digest is one line, `helpers.py:25`)
  and are covered by the four "still passes" criteria; step 4 and step 9 are the
  two verification runs; steps 5-6 are the fix and map to the two behavioural
  criteria; step 7 is the new test. Step 8 (`pipeline/stages/planning.md`) has no
  criterion because no test reads that file -- grepped `tests/` for
  `planning.md`, zero hits. It is the wiring half: a gate rule the planning stage
  is never told about would bounce every future plan for a rule it was never
  given. Nothing else is untraceable.
- **Criteria are falsifiable.** The reproduction test fails today with the quoted
  `AssertionError` and the Tier A gate confirms it fails on base too. The new
  `test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest`
  carries three executed mutations, including the trap that `elif True:` alone
  leaves it **green** because the `ok:` prefix is filtered at `gate.py:190` --
  the `ok:` filter is at 190, verified. That is the opposite of vacuous. Traced
  the new test by hand against the fixture: `digest-short:` waives the count,
  `DEC-002` resolves as superseded to an `ok:` note, `DEC-003` is silent, and the
  base-check skip (`wd.resolve() == project.resolve()`) keeps it green -- so
  `assert ok` is reachable. One weakness carried over and still not worth a
  bounce: `test_gate_blocks_an_empty_digest` asserts `any("Digest" in f ...)` and
  would still pass if an empty digest were reported twice; the `if dig.strip()`
  guard prevents that and no test pins it. Noted for review.
- **No research left.** Every step names a file and verbatim code. Spot-checked
  every position: `gate.py` `REQUIRED_SECTIONS` 13, loop 89-91, decisions block
  141-144, `ok:` filter 190, `ticket` import 8, `_cites` 19; `ticket.py`
  `SAFE_DEC_ID` 223, `SUPERSEDED_MARKER` 231, `Decision` 235, `decisions_dir`
  243, `active_decisions` 258 (returns `[]` when the directory is missing, skips
  symlinks -- both as the plan states, and both load-bearing for the reproduction
  fixture and for the symlink rule); `tests/test_gate.py` `shutil` 2, `T` 8,
  `gate` 9, call sites 49 and 209, and the reproduction test is last in the file
  (ends 216) so step 7's append is unambiguous; `helpers.py:25`;
  `planning.md` 22-23 / 24-38 / 39. All correct. One nit, not a finding: step 3's
  "lines 49 and 209" go stale within its own step once `import re` and the helper
  are inserted -- both sites are given verbatim, so text-matching them is
  unambiguous.
- **Riskiest step: the fixture splice (step 1); fallback stated and adequate.**
  A stale `.replace()` no-ops *silently* and leaves a test asserting against an
  unmodified fixture -- the failure that looks green. The plan does not merely
  document it: `_set_digest()` derives the span from `FIXTURE` and asserts
  `n == 1`, and step 4 is the checkpoint -- the reproduction test must still be
  red with the *reported* message, and any other message means step 3 is wrong.
  Checked the regex by reading (fixed-width lookbehind `^## Digest\n`, `re.S|re.M`,
  one match in `FIXTURE`, and `""` yields the empty digest `test_gate_blocks_an_empty_digest`
  needs); could not execute it here because the guard blocks `python3 -c` --
  reported, not worked around. The plan states it was executed during planning.
- **Regression surface, independently enumerated.** Grepped the whole repo for
  the digest text: exactly three source sites, matching the plan's table -- no
  fourth. `tests/test_ticket.py:269` calls `gate()` on the default fixture whose
  `## Decisions checked` is "none relevant", so it never reaches the new lookup
  and only needs the three-entry digest. Seven test files import `helpers`
  (`test_cli`, `test_daemon`, `test_dispatch`, `test_gate`, `test_ticket`,
  `test_tui`, `test_worktree`) -- the whole-suite criterion covers them, and
  `176 passed` was observed. One behaviour change is wider than any test:
  `DEC_ID_RE` is narrower than the old `\b[A-Z]+-\d+\b|DEC-`, so a
  `## Decisions checked` citing only `TICKET-012` (or a bare `DEC-`) now fails
  where it passed. Argued deliberately in `## Decisions`; it is a gate
  tightening applied to tickets that re-enter the gate. Checked the obvious
  self-lockout: this ticket's own `## Decisions checked` cites only DEC-011,
  DEC-016, DEC-017, DEC-019, DEC-020, all resolvable and active, and the bare
  `DEC-` in its grep-terms line does not match `DEC-\d{1,6}`.
- **Blast radius matches `bugfix`.** Five files, one commit: one production file
  (`pipeline/core/gate.py`), three test files dragged in by the fixture coupling,
  one prompt file for the rule text. No new module, no dependency, no on-disk
  format change.

Verdict: pass. Nothing here needs the plan reworked.

### 2026-08-21 07:10:08Z · plan-validation · session · session=ba44fdf2-fede-4193-871c-c017276632b5

`plan-validation` ran as session `ba44fdf2-fede-4193-871c-c017276632b5`
- replay: `claude --resume ba44fdf2-fede-4193-871c-c017276632b5`
- log: `.project/logs/TICKET-018-plan-validation-ba44fdf2.log`

### 2026-08-21 07:10:08Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

plan validated on all eight items -- root cause is gate.py's content-blind checks (89-91, 142), DEC-017 read in full and the file-local _set_digest() complies, all five decisions active and correctly characterised, every line ref and the three digest call sites re-verified at 6738a26; step 8 (planning.md) has no criterion by design and is kept as wiring

### 2026-08-21 07:11:00Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 07:11:14Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id` fails as required
```
==== FAILURES ===================================
______ test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id ______

    def test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id():
        """Both Tier A content checks are non-emptiness only: a digest of one word
        passes, and a cited `DEC-999` passes though no such record exists in
        `.project/decisions/`."""
        d = project(FIXTURE.replace("## Digest\nthing.py holds it\n", "## Digest\nx\n")
                           .replace("none relevant (grepped: cache, evict)", "DEC-999"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
E       AssertionError: one-word digest and unresolvable DEC-999 both passed the gate
E       assert not True

tests/test_gate.py:212: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id` fails on base `main` too -- the bug is not already fixed upstream
```
(grepped: cache, evict)", "DEC-999"))
        ok, failures = gate(d, "TICKET-001")
>       assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
E       AssertionError: one-word digest and unresolvable DEC-999 both passed the gate
E       assert not True

tests/test_gate.py:212: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-n5fgrd4u/base
      Built pipeline @ file:///tmp/pipeline-base-n5fgrd4u/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 12ms

```

### 2026-08-21 07:11:14Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 · implementing · note

Todo list from the approved plan's nine steps:

1. [x] `tests/helpers.py` -- three-entry digest
2. [x] `tests/test_ticket.py:22` -- `startswith` digest assertion
3. [x] `tests/test_gate.py` -- `import re`, `_set_digest()` helper, both call sites switched
4. [x] confirm only the reproduction test red, reported `AssertionError`
5. [x] `pipeline/core/gate.py` -- `MIN_DIGEST_ENTRIES`/`DIGEST_SHORT_RE`/`DEC_ID_RE` + entry-count check
6. [x] `pipeline/core/gate.py` -- widened import + decision-ID resolution block
7. [x] `tests/test_gate.py` -- appended the new superseded/short-digest test
8. [x] `pipeline/stages/planning.md` -- two documentation lines
9. [x] verification runs + single commit

Before touching any file, re-read every position the plan cited against the
current worktree (HEAD `0ac36f2`, the reproduction test already on branch) --
all held exactly: `gate.py` lines 13 / 89-91 / 141-144 / 190 / 8 / 19;
`ticket.py`'s `SAFE_DEC_ID`, `SUPERSEDED_MARKER`, `Decision`, `decisions_dir`,
`active_decisions` had drifted to lines 263/271/275/283/298 (the file grew ~40
lines since plan-validation) but the symbols, signatures and behaviour matched
verbatim -- no re-plan needed; `tests/helpers.py:25`; `tests/test_gate.py`
call sites 49/209 and imports at lines 7-8; `tests/test_ticket.py:22`;
`planning.md` bullets 22-23/24-38/39. Step 4 confirmed exactly one red
(`test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id`) with the
reported `AssertionError` and 41 other tests passing.

Executed steps 1-8 verbatim from `## Digest`/`## Plan`. Step 9 verification:
`tests/test_gate.py tests/test_ticket.py` -- 43 passed (one more than the
planning run's 42; an unrelated test landed on `main` between plan-validation
and this run, not from this change). Whole suite -- 177 passed (one more than
planning's 176, same reason). `./pipeline/hooks/test_dangerous_commands.py` --
`guard: all passed`. `git status --porcelain` showed exactly the five declared
files before staging. Pre-commit history check
(`git log --oneline -S "REQUIRED_SECTIONS" -- pipeline/core/gate.py`) found no
prior commit addressing this exact gap. Committed as `06089bf` on `ticket/018`.

Confirmed the acceptance criteria: both new/changed gate tests pass, the
still-passing criteria all hold, both suite runs and the guard script are
green as specified.

Noted, out of scope (per triage/planning): `tests/test_ticket.py` carries
pre-existing Pyright `reportOptionalSubscript`/`reportArgumentType` complaints
(now at different line numbers than the ticket's note since the file has
grown) -- untouched by this change, not fixed here.

### 2026-08-21 07:14:18Z · implementing · session · session=f1166682-270d-4ffd-9acf-8e4157583b61

`implementing` ran as session `f1166682-270d-4ffd-9acf-8e4157583b61`
- replay: `claude --resume f1166682-270d-4ffd-9acf-8e4157583b61`
- log: `.project/logs/TICKET-018-implementing-f1166682.log`

### 2026-08-21 07:14:18Z · implementing · transition · to=review · result=ok

**implementing -> review** (result: `ok`)

executed all nine plan steps verbatim, committed 06089bf; reproduction test and new test pass, whole suite 177 passed, guard passed

### 2026-08-21 · review · note

First review pass. Delta reviewed: `git diff main...HEAD` (commits `0ac36f2`
test-only, `06089bf` the fix) -- no prior review entry in `## Thread`, so the
branch point is the baseline. **No blocking findings.**

Verified independently, not taken from the implementing note:

- `git show --stat 06089bf` -- one commit, exactly the five `files_declared`
  files, nothing extra; `git status --porcelain` empty.
- `uv run --group dev pytest -q tests/test_gate.py tests/test_ticket.py` -- `43
  passed`; `uv run --group dev pytest -q` -- `177 passed`. Both match the
  implementing note, including the +1 over planning's 42/176.
- All six tests the `## Acceptance criteria` name, run by node id in one
  invocation -- `6 passed`.
- Drift check against `## Plan`: steps 1-8 are the plan's code blocks verbatim
  and land where the plan said (`gate.py` constants after `REQUIRED_SECTIONS`,
  entry-count check right after the loop, widened line-8 import, resolution
  block replacing the shape-match). `planning.md`'s two continuation lines are
  2-space indented inside their bullets (lines 24-26 and 42-44), so they stay
  part of the `## Digest` / `## Decisions checked` bullets rather than starting
  new ones. DEC-017 complied with: `tests/test_gate.py` gained `import re` and
  the file-local `_set_digest()`, and no new name on its `from helpers import`
  line.
- The new test is not vacuous on three independent axes, each traced through
  `gate()`: break the `digest-short:` waiver and the two-line digest trips
  `MIN_DIGEST_ENTRIES` (`assert ok` fails); drop the `ok:` prefix and line 228's
  `failed = [...]` picks the superseded note up (`assert ok` fails); rename the
  note string and `assert "DEC-002 is superseded" in text` fails. Confirmed by
  reading, not by mutating -- this stage is read-only.
- Whitespace-only-digest gap I went looking for does not exist: `sections()`
  (`pipeline/core/ticket.py:147,152`) `.strip()`s each section, so a blank-ish
  `## Digest` is `""` and `REQUIRED_SECTIONS` catches it. The `dig.strip()`
  guard is belt-and-braces, and the "skip rather than double-report" comment is
  accurate.

Non-blocking, in descending order of how much they matter:

1. **[minor] One acceptance criterion could not be verified in this stage.**
   `./pipeline/hooks/test_dangerous_commands.py` is blocked by the read-only
   allowlist (`test_dangerous_commands.py is not on the read-only allowlist`),
   as is running it via a `python` invocation. The delta touches no file under
   `pipeline/hooks/`, so the guard's behaviour cannot have changed; the AC rests
   on the implementing stage's `guard: all passed`. Reported rather than worked
   around, per the guard's own instruction.
2. **[minor] `gate()` is now the first production caller of
   `active_decisions()`** -- before this change only tests called it. It does
   `p.read_text()` on every `DEC-*.md` glob hit, and `glob` matches a
   *directory* named e.g. `DEC-1.md`, which raises `IsADirectoryError` out of
   `gate()` rather than a `PipelineError`. Pre-existing in `active_decisions()`,
   newly reachable from the gate path, and only by a hostile
   `.project/decisions/`. Worth a `DEC-*.md` `is_file()` filter in
   `active_decisions()` some day; out of scope here.
3. **[nit] `"none relevant"` no longer fully early-outs.** A section reading
   `none relevant (grepped: DEC-017, gate)` now resolves `DEC-017` because the
   grep-term list itself contains a well-formed id. Harmless in this repo (all
   five records exist) and arguably correct, but in a project without that
   record a genuine "none relevant" would fail the gate. A bare `DEC-` as a grep
   term -- which is what this ticket's own section uses -- does not match
   `DEC_ID_RE`, so the common form is safe.
4. **[nit] Two spots where a plausible input is silently not what the author
   meant.** `DIGEST_SHORT_RE` is case-sensitive, so `Digest-short:` fails the
   count with no hint why; and `DEC_ID_RE`/`DIGEST_SHORT_RE` both scan fenced
   code blocks inside their section, so a `digest-short:` shown as an example
   inside a fence waives the count for real. Both are consistent with how the
   rest of the gate reads sections, and `planning.md` documents the exact
   lowercase spelling.
5. **[nit, already known] The new test does not defend "an active cited id
   produces no finding at all"** -- `elif cid not in active:` -> `elif True:`
   leaves it green, because the `ok:` prefix keeps the extra finding out of the
   verdict. `## Decisions` states this trap explicitly and the third mutation in
   `## Digest` is written to route around it, so this is documented, not missed.

### 2026-08-21 07:18:11Z · review · session · session=43edfb4d-37d5-4277-aff8-d833a615eedc

`review` ran as session `43edfb4d-37d5-4277-aff8-d833a615eedc`
- replay: `claude --resume 43edfb4d-37d5-4277-aff8-d833a615eedc`
- log: `.project/logs/TICKET-018-review-43edfb4d.log`

### 2026-08-21 07:18:11Z · review · transition · to=verifying · result=ok

**review -> verifying** (result: `ok`)

reviewed main...HEAD; plan followed verbatim, 5 declared files in one commit, 43/177 tests and all 6 named acceptance tests pass; 5 non-blocking notes appended

### 2026-08-21 07:18:20Z · verifying · transition · to=merging · result=ok

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

### 2026-08-21 07:18:20Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/018


Already up to date.
Updating 40b8fe3..06089bf
Fast-forward
 pipeline/core/gate.py       | 42 +++++++++++++++++++++++++++++++++--
 pipeline/stages/planning.md |  6 +++++
 tests/helpers.py            |  4 +++-
 tests/test_gate.py          | 54 ++++++++++++++++++++++++++++++++++++++++++++-
 tests/test_ticket.py        |  2 +-
 5 files changed, 103 insertions(+), 5 deletions(-)

```

### 2026-08-21 07:18:20Z · merging · decision

decision recorded as `DEC-018`
