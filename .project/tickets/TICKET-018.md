---
id: TICKET-018
stage: plan-validation
class: bugfix
branch: ticket/018
test_file: tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
files_declared:
- pipeline/core/gate.py
- tests/helpers.py
- tests/test_gate.py
- tests/test_ticket.py
- pipeline/stages/planning.md
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
  stage: planning
  id: d1e42539-c068-4c28-93d7-4c16583269f9
  log: .project/logs/TICKET-018-planning-d1e42539.log
---

## Summary

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
`active_decisions(project)` in `pipeline/core/ticket.py:224` already returns the
active records (superseded ones drop out, carrying `SUPERSEDED_MARKER`), so the
lookup is available. Failing test committed on `ticket/018` as 2e908e9; see
`## Reproduction`.

**Plan (2026-08-21):** two checks added to `pipeline/core/gate.py`. (1) `## Digest`
must have at least `MIN_DIGEST_ENTRIES = 3` non-empty lines, waived by one
`digest-short: <why fewer>` line -- the escape hatch the design conversation asked
for. (2) Every `DEC-<n>` cited in `## Decisions checked` is resolved against
`.project/decisions/` via the existing `active_decisions()`: an id with no record
is a finding, a superseded one is an `ok:` note (informational, does not fail).
The count check forces `tests/helpers.py:FIXTURE` to grow a real three-entry
digest, which drags three string-matching call sites with it -- that coupling, and
the order that keeps the reproduction test honestly red until the fix lands, is the
main thing to get right. Nine steps, five files, one commit.

**Verified 2026-08-21:** every step was executed in the worktree and then
reverted, so the code in `## Digest` is transcribed from a run, not drafted.
Observed: step 4 leaves exactly the reproduction test red with the reported
`AssertionError`; step 9 gives `36 passed` and the whole suite `164 passed`; the
new test dies under three separate mutations. The worktree is clean again and
the reproduction test is red, which is what the plan-validation gate requires.

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

tests/test_gate.py:159: AssertionError
```

expect: one-word digest and unresolvable DEC-999 both passed the gate

## Digest

### Where the two weak checks live

`pipeline/core/gate.py` -- the whole Tier A gate, one function, ~150 lines.

- `REQUIRED_SECTIONS` (line 12) is the only thing that looks at `## Digest`:
  `if not secs.get(name)`. One word passes.
- The decisions check is lines 98-101: `re.search(r"\b[A-Z]+-\d+\b|DEC-", dec)`
  after an early-out on `"none relevant"`. A *shape* match -- `DEC-999` and even
  `TICKET-012` satisfy it. Nothing opens `.project/decisions/`.
- Findings whose text starts with `ok:` are informational: line 147 computes
  `failed = [f for f in findings if not f.startswith("ok:")]`, and only `failed`
  decides the verdict. That is the mechanism for "note it, do not fail it".
- `_cites()` (line 18) is the existing path-citation helper used by the `## Plan`
  check. Not used by this change -- see `## Decisions`.

### What already exists to resolve a decision id

`pipeline/core/ticket.py`:

- `decisions_dir(project) -> project/.project/decisions` (line 209).
- `active_decisions(project) -> list[Decision]` (line 224): every `DEC-*.md` in
  that directory that does not contain `SUPERSEDED_MARKER`, skipping symlinks.
  `Decision.id` is the file stem (`DEC-003`). Returns `[]` when the directory
  does not exist -- no exception, which is what the new test's fixture relies on.
- `SUPERSEDED_MARKER` (line 197) is the HTML comment `record_decision()` appends
  to a superseded record. Grep for the marker, never for `- superseded-by:`.
- `SAFE_DEC_ID = ^DEC-\d{1,6}$` (line 189) -- ids are always `DEC-<digits>`, so
  the new regex resolves only those.

Resolve against `project`, not `workdir`: `gate()` already reads the ticket from
`ticket_path(project, tid)`, and `record_decision()` writes records to the
project root. The worktree copy is a checkout of the base branch and can be
stale.

### The fixture coupling -- the one gotcha in this ticket

`tests/helpers.py:FIXTURE` is the canonical "complete ticket" and its `## Digest`
is a single line, `thing.py holds it`. A minimum-entry-count check fails it, so
`test_gate_passes_a_complete_ticket`, `test_an_acceptance_criterion_must_name_something_test_shaped`,
`test_gate_passes_a_failure_that_matches_the_reported_one` and
`tests/test_ticket.py::test_the_dispatcher_writes_typed_thread_entries` (line 269,
`assert gate(d, "TICKET-001")[0]`) all go red unless the fixture grows a real digest.

Three places string-match that digest text and must move with it:

| file:line | today |
|---|---|
| `tests/test_gate.py:18` | `.replace("## Digest\nthing.py holds it\n", "## Digest\n")` |
| `tests/test_gate.py:156` | `.replace("## Digest\nthing.py holds it\n", "## Digest\nx\n")` |
| `tests/test_ticket.py:22` | `t.section("Digest") == "thing.py holds it"` |

**A stale `.replace()` here is silent** -- it no-ops and the test then runs against
an unmodified fixture. Step 1 introduces a `DIGEST` constant in `tests/helpers.py`
so the replacement text has exactly one definition; steps 2 and 3 switch the call
sites to it. Do the fixture steps *before* the `gate.py` steps: after step 4 the
reproduction test must still be red for the reported reason, which proves the
replace strings still bite.

### Code for each step

Step 1 -- `tests/helpers.py`. Replace lines 6-35 (from `ROOT = ...` through the
closing `"""` of `FIXTURE`) with exactly this.

**The block below is indented by 4 spaces. De-indent every line by exactly 4
before writing the file.** The indent exists only so that this ticket's own
`sections()` parser -- `^##\s+(.+?)\s*$`, which does not respect markdown
fences -- does not read the fixture's `## Digest` as a section of *this* ticket.

```python
    ROOT = Path(__file__).resolve().parent.parent

    DIGEST = ("- thing.py holds it\n"
              "- cache() is the entry point\n"
              "- eviction runs on write, not read\n")

    FIXTURE = """---
    id: TICKET-001
    stage: plan-validation
    class: bugfix
    branch: ticket/001
    test_file: test_thing.py::test_broken
    files_declared: [thing.py]
    counters: {}
    lease: {holder: null, expires: null}
    ---

    ## Summary
    x
    ## Reproduction
    fails
    expect: test_broken
    ## Digest
    """ + DIGEST + """## Decisions checked
    none relevant (grepped: cache, evict)
    ## Plan
    1. fix thing.py
    ## Acceptance criteria
    - `test_broken` passes
    ## Rollback
    revert
    ## Thread
    """
```

Concatenation, not an f-string: the fixture contains
`lease: {holder: null, expires: null}`, whose braces an f-string would try to
interpolate. `DIGEST` already ends in a newline, so no blank line appears between
the three entries and the decisions header, and the reopened literal must keep
`## Decisions checked` hard against the closing `"""` on the same source line.

This exact splice was executed and diffed during planning: the resulting
`FIXTURE` differs from `git show HEAD:tests/helpers.py`'s in the digest body and
nowhere else (`-thing.py holds it` -> the three `- ` entries). To re-check after
editing, run from the repo root:

```sh
uv run --group dev python -c "import sys; sys.path.insert(0,'tests'); from helpers import FIXTURE; print(FIXTURE)"
```

Step 2 -- `tests/test_ticket.py:22`:

```python
    assert t.klass == "bugfix" and t.section("Digest").startswith("- thing.py holds it")
```

Step 3 -- `tests/test_gate.py`, import line 4 and the two call sites:

```python
from helpers import DIGEST, FIXTURE, project
...
    d = project(FIXTURE.replace(DIGEST, ""))                      # line 18
...
    d = project(FIXTURE.replace(DIGEST, "x\n")                    # line 156
                       .replace("none relevant (grepped: cache, evict)", "DEC-999"))
```

Step 5 -- `pipeline/core/gate.py`, module level, under `REQUIRED_SECTIONS`:

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

Step 5 -- `pipeline/core/gate.py`, immediately after the `REQUIRED_SECTIONS` loop
(after line 49's `findings.append(f"section `## {name}` missing or empty")` block):

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

Step 6 -- `pipeline/core/gate.py`, import on line 7 and the block replacing lines 98-101:

```python
from pipeline.core.ticket import Ticket, active_decisions, decisions_dir, ticket_path
...
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

Step 7 -- `tests/test_gate.py`, appended at the end of the file:

```python
def test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest():
    """A cited id that resolves must not fail; a superseded one is history, not
    a finding; and a short digest passes only when it says why it is short."""
    d = project(FIXTURE.replace(DIGEST, "digest-short: one file, one line\n"
                                        "- thing.py holds it\n")
                       .replace("none relevant (grepped: cache, evict)",
                                "checked DEC-002 (superseded) and DEC-003"))
    dec = d / ".project" / "decisions"
    dec.mkdir()
    (dec / "DEC-002.md").write_text(
        "# DEC-002\n\nold\n\n%s\n- superseded-by: DEC-003 (2026-08-21)\n" % T.SUPERSEDED_MARKER)
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
not work: changing only `elif cid not in active:` to `elif True:` leaves the
test **green**, since the extra finding still carries the `ok:` prefix that line
147 excludes from the verdict. Dropping the prefix is what makes a resolvable id
fail. Anyone re-deriving this list will hit the same trap.

Step 8 -- `pipeline/stages/planning.md`. Two continuation lines, each appended to
the **end** of a bullet, not after the bullet's first line. Indent both by 2
spaces so they stay part of the bullet:

- the `## Digest` bullet spans lines 22-23 and ends `...re-explores the
  codebase from scratch.` -- insert after line 23;
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

### Commands

```sh
uv run --group dev pytest -q tests/test_gate.py tests/test_ticket.py
./pipeline/hooks/test_dangerous_commands.py    # untouched here, but it is not collected by pytest
```

## Decisions checked

`.project/decisions/` holds exactly one record: **DEC-011** (the daemon's
cross-agent contract). Read in full.

- **DEC-011 -- consulted, complies.** It freezes the event vocabulary, and the
  `gate` kind carries `{verdict, findings:[...]}`. This change only adds new
  strings to `findings`, which DEC-011 calls out as additive and fine ("Adding a
  `kind` or a field inside `data` is additive and fine"). No column, kind name or
  field meaning changes, so no superseding record is needed.
- Not superseded (no `superseded-by:` footer), so it binds; nothing here
  contradicts it.

Grep terms used across `.project/decisions/`: `gate`, `digest`,
`Decisions checked`, `Tier A`, `DEC-`. Only the DEC-011 hits above, all about the
daemon's `gate` *event*, not the gate's checks.

## Plan

1. In `tests/helpers.py`, replace lines 6-35 with the de-indented block shown under "Step 1" in `## Digest`, adding the `DIGEST` constant and splicing it into `FIXTURE` so the fixture's digest is three entries with one definition.
2. In `tests/test_ticket.py`, change the exact-equality digest assertion on line 22 to the `startswith` form shown under "Step 2" in `## Digest`.
3. In `tests/test_gate.py`, import `DIGEST` from helpers and switch both digest `.replace(...)` call sites (lines 18 and 156) to it, per "Step 3" in `## Digest`.
4. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_ticket.py` and confirm the only red is `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id`, still failing with `AssertionError: one-word digest and unresolvable DEC-999 both passed the gate` -- a different message means a `.replace()` in `tests/test_gate.py` went stale and step 3 is wrong.
5. In `pipeline/core/gate.py`, add `MIN_DIGEST_ENTRIES`, `DIGEST_SHORT_RE` and `DEC_ID_RE` under `REQUIRED_SECTIONS`, and insert the digest entry-count check right after the `REQUIRED_SECTIONS` loop, both verbatim from "Step 5" in `## Digest`.
6. In `pipeline/core/gate.py`, widen the line-7 import to `active_decisions, decisions_dir` and replace the `## Decisions checked` block (lines 98-101) with the resolution block verbatim from "Step 6" in `## Digest`.
7. In `tests/test_gate.py`, append `test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest` verbatim from "Step 7" in `## Digest`.
8. In `pipeline/stages/planning.md`, insert the two 2-space-indented continuation lines from "Step 8" in `## Digest` after line 23 and after line 38 respectively, so the agent that must satisfy these checks is told the rule.
9. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_ticket.py` and confirm every test passes, including the reproduction test that was red at step 4, then commit `pipeline/core/gate.py`, `tests/helpers.py`, `tests/test_gate.py`, `tests/test_ticket.py` and `pipeline/stages/planning.md` in one commit.

## Acceptance criteria

- `tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id`
  passes: a one-word digest and an unresolvable `DEC-999` are both findings.
- `tests/test_gate.py::test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest`
  passes: a cited active id is silent, a cited superseded id lands in the ticket as
  `DEC-002 is superseded` without failing the gate, and a `digest-short:` line waives
  the entry count.
- `tests/test_gate.py::test_gate_passes_a_complete_ticket` still passes -- the
  three-entry fixture digest clears `MIN_DIGEST_ENTRIES`.
- `tests/test_gate.py::test_gate_blocks_an_empty_digest` still passes -- an empty
  digest is reported once, by `REQUIRED_SECTIONS`, not twice.
- `tests/test_ticket.py::test_unknown_frontmatter_survives_a_save` and
  `tests/test_ticket.py::test_the_dispatcher_writes_typed_thread_entries` still
  pass -- the fixture change did not break the round-trip or the `gate()` call at
  `tests/test_ticket.py:269`.
- Whole run of `uv run --group dev pytest -q tests/test_gate.py tests/test_ticket.py`
  is green at step 9 -- observed during planning as `36 passed`.
- The whole `tests/` suite, `uv run --group dev pytest -q`, is green -- observed
  during planning as `164 passed`. Seven files import `tests/helpers.py`, so the
  fixture change is not confined to `tests/test_gate.py` and `tests/test_ticket.py`
  even though only those three call sites string-match its digest.

## Decisions

The Tier A gate resolves every `DEC-<n>` cited in `## Decisions checked` against
`.project/decisions/` **in the project root**, never the worktree: the worktree is
a checkout of the base branch and its `.project/decisions/` can be stale, while
`record_decision()` writes to the root and `gate()` already reads the ticket from
there. Resolving against `workdir` would let a plan cite a record that was
superseded after the branch was cut.

Three rules that look arbitrary and are not:

- **A cited id with no record fails; a superseded one is a note, not a failure.**
  Superseded records stay on disk on purpose (they are still why something was
  once done that way), so citing one is legitimate; only treating it as *binding*
  is wrong, and that is Tier B judgment, not a deterministic check. The note is
  emitted with the `ok:` prefix, which line 147 of `pipeline/core/gate.py`
  excludes from the verdict. **Do not "fix" that prefix away** -- it is load
  bearing, and dropping it is exactly what turns a resolvable citation into a
  gate failure. Confirmed by mutation during planning: remove the prefix and
  `test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest`
  goes red, so the test does defend it.
- **A symlinked `DEC-*.md` counts as absent, not as superseded.** `active_decisions()`
  skips symlinks (invariant 5: never follow a planted link), so including them in
  the on-disk set would report a planted link as merely superseded -- the quietest
  possible outcome for the most hostile input.
- **`DEC_ID_RE` is `DEC-<digits>` only**, deliberately narrower than the old
  `\b[A-Z]+-\d+\b`, which accepted `TICKET-012` as a decision citation. Every id
  `record_decision()` can produce matches `SAFE_DEC_ID`; anything else in that
  section is prose.

`MIN_DIGEST_ENTRIES = 3` counts non-empty lines and is a floor, not a quality bar
-- three empty bullets still pass it. Its job is to kill the degenerate one-word
digest; judging whether a digest is *useful* is the plan-validation stage's.
`digest-short:` is the deliberate escape hatch from the design conversation
("minimum N entries or explicit justification for fewer"): an agent that needs
fewer says why in a line a human can grep, instead of padding to a number.

`tests/helpers.py:FIXTURE` now carries a three-entry digest, and `DIGEST` exists so
the replacement text has one definition. Every `.replace()` against the fixture's
digest must go through that constant: a stale literal no-ops silently and leaves a
test asserting against an unmodified fixture.

## Rollback

Revert the single commit from step 9. It is self-contained: `pipeline/core/gate.py`
returns to the two non-emptiness checks, `tests/helpers.py` to the one-line digest,
and the three test files to matching it. Nothing else imports `MIN_DIGEST_ENTRIES`,
`DIGEST_SHORT_RE` or `DEC_ID_RE`, no on-disk format changes, and no ticket already
merged becomes invalid -- the checks only run when a ticket passes the gate again.
Partial rollback is not safe: reverting `pipeline/core/gate.py` alone leaves
`tests/test_gate.py::test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest`
red, and reverting `tests/helpers.py` alone turns every fixture `.replace()` into
a no-op.

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

tests/test_gate.py:159: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```

### 2026-08-21 04:37:46Z · plan-validation · note

`plan-validation` was interrupted; lease released
