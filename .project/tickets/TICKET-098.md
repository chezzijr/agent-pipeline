---
id: TICKET-098
stage: done
class: bugfix
branch: ticket/098
test_file: tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape
files_declared:
- pipeline/templates/skills/file-ticket/SKILL.md
- tests/test_stages.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 8
  plan_files: 2
  no_result: 0
  structural_gate_failures: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 1aca4ef6-029d-4a47-bae7-9ed66e516f32
  log: .project/logs/TICKET-098-review-1aca4ef6.log
  cost_usd: 1.2562750000000003
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified: tests/test_stages.py already imports re at
  line 3, so step 1''s regex assertion runs; the plan edits pipeline/templates/skills/file-ticket/SKILL.md,
  which is the symlink target and what pipeline init copies; step 4 rewrites the worked
  example to carry a real path:line anchor rather than only stating the rule; step
  6 makes the no-symptom push-back point at the docs-only shape instead of rejecting.
  Nothing fenced.'
approved_at: '2026-08-29T06:03:00.476749+00:00'
---

## Summary

the file-ticket skill omits code anchors and has no shape for a docs-only ticket

`pipeline/templates/skills/file-ticket/SKILL.md` (symlinked as
`.claude/skills/file-ticket/SKILL.md`) is what a session reads before filing work
into this pipeline. Its `## Summary` guidance -- "a one-line title, the mechanism,
a runnable reproduction, and the expected behaviour stated as something a test can
check" -- is missing two things that decide whether a ticket survives triage.

1. It never says to anchor the mechanism in code. A summary that names
`pipeline/core/gate.py:383` and quotes the three lines around it hands triage the
location; a summary that describes the same bug in prose makes triage re-find it
from scratch, on a stage that is charged per run. Every worked example in the
skill is prose-only, so nothing teaches the anchor.

2. It has no shape for a ticket whose symptom is in a document. The skill's own
push-back section says an agent that cannot write a failing test returns
`result: rejected` and the ticket dies at triage -- correct, and it makes a
docs-only ticket unfileable as written. The pattern that works already exists in
this repo: TICKET-084 fixed the `pipeline-config` skill and made it falsifiable
with `tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads`,
a test asserting the document's text, red before the edit. The skill never
mentions it, so the next documentation ticket either gets rejected or is forced
through by hand.

Expected: the skill gains (a) one line in the step-3 summary guidance requiring
`path:line` anchors and a short quote of the code the ticket is about, with the
worked example updated to carry one, and (b) a short section naming the docs-only
shape -- state the test file and the assertion that will hold the document to the
change, the way TICKET-084 did.

Falsifiable exactly as TICKET-084 was: a test in `tests/test_stages.py` asserting
the skill text names both, red before the edit. Note for planning: `pipeline init`
copies `pipeline/templates/skills/` into the projects it scaffolds, so the
template file is the one to edit -- not the symlink -- and CLAUDE.md's rule that
this skill is part of the interface applies.

**State: re-planned.** Two files change:
`pipeline/templates/skills/file-ticket/SKILL.md` (the anchor rule after the
"What makes that work" paragraph, an anchored worked example, a new
`## A docs-only ticket` section before `## Do not`, and one cross-reference
sentence in step 2's first push-back bullet) and `tests/test_stages.py` (two
assertions added to the repro test, for a worked anchor and for the cited
precedent). Triage's test at `tests/test_stages.py:407` already covers the two
substrings. Baseline on cf5a10e: `uv run --group dev pytest -q
tests/test_stages.py` prints `1 failed, 30 passed in 0.27s`, the failure being
the repro test. Neither file is in `machine.FENCED`.

**State: validated.** The Tier A gate failed the first plan on one acceptance
criterion, which pinned the absolute total `30 passed`. Planning rewrote every
criterion as an exit status re-measured against cf5a10e and left the eight
steps unchanged. The Tier A gate then passed, and Tier B passed all eight
judgment items with nothing unverified.

Two facts implementing should carry. First, steps 3 and 4 add roughly ten lines
above line 171, so step 5's cited lines 171 and 173 shift; edit by the text
anchor each step names (`## Do not`), not by the number. Second, no test
outside `tests/test_stages.py` reads the skill's text -- `tests/test_cli.py`
compares the installed copy to the source and overwrites it, both
content-agnostic -- so the two suite criteria cover the regression surface.

**State: implemented.** All eight plan steps done. Both files changed as
planned: `pipeline/templates/skills/file-ticket/SKILL.md` gained the anchor
rule, the anchored worked example, the `## A docs-only ticket` section, and
the push-back cross-reference; `tests/test_stages.py` gained the two
assertions. `uv run --group dev pytest -q tests/test_stages.py` prints
`31 passed in 0.18s`. `git diff --name-only fdcb228 HEAD` (the branch's actual
rebased base, not the stale cf5a10e) lists exactly the two declared files.
Committed as `d5618ec`, message
`docs(TICKET-098): require a path:line anchor and name the docs-only ticket shape`.

**State: reviewed, no blocking findings.** Review read `fdcb228..HEAD` and
matched it against every acceptance criterion. All pass. The full suite prints
`466 passed in 34.48s`, so nothing outside `tests/test_stages.py` regressed.
The anchor grep exits 0 on the skill and 1 on `git show cf5a10e:...SKILL.md`.
`git merge-base HEAD main` is `fdcb228`; the diff against it lists exactly the
two declared files.

Two non-blocking notes are in the thread. First, the regex assertion is met by
the anchor rule's own `pipeline/core/gate.py:383`, so it holds the file, not
the worked example specifically -- weaker than `## Decisions` states. Second,
the criterion's literal `git diff --name-only cf5a10e` cannot be run: the
rebase orphaned cf5a10e.

## Reproduction

`tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape`

```
uv run --group dev pytest -q tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape
```

```
AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-098/pipeline/templates/skills/file-ticket/SKILL.md does not require a path:line anchor
assert 'path:line' in "---\nname: file-ticket\ndescription: File a ticket into this repo's pipeline (.project/tickets/). Use when the user r...h append to the\n  thread properly. To edit a running ticket by hand, interrupt the stage first\n  (`k` in the TUI).\n"
```

expect: does not require a path:line anchor

## Digest

Files touched: `pipeline/templates/skills/file-ticket/SKILL.md` (186 lines) and
`tests/test_stages.py`. The skill template is the only copy of the skill --
`.claude/skills/file-ticket/SKILL.md` is a symlink to it (DEC-056), so editing
the template edits both.

Entry points: `pipeline/core/config.py:33` is
`SKILL_TEMPLATE = SKILLS_DIR / "file-ticket" / "SKILL.md"`, which is what the
repro test reads. `cmd_init()` copies `<skill>/SKILL.md` per directory under
`SKILLS_DIR` into a scaffolded project, so the template is the file that ships.

Key locations in the skill, by line: step 2's push-back list at 69-81 (its
first bullet, "No observable symptom", is 74-76); step 3's worked `## Summary`
example fence at 95-110; the "What makes that work" paragraph at 112-117; step
4 ends at 171; `## Do not` starts at 173.

The pattern to cite for the docs-only shape:
`tests/test_stages.py:386 test_the_config_skill_names_every_knob_the_code_reads`
reads `SKILLS_DIR / "pipeline-config" / "SKILL.md"` and asserts five knob names
are in it. That is TICKET-084's test, red before that edit.

The repro test is `tests/test_stages.py:407-415`, committed by triage at
cf5a10e. It asserts two substrings, `path:line` and `docs-only`.

Baseline measured 2026-08-29 on cf5a10e:
`uv run --group dev pytest -q tests/test_stages.py` prints
`1 failed, 30 passed in 0.27s`, and the one failure is this ticket's repro test.

Gotchas:

1. Line 52 of the skill already reads `machine.py:BOUNDS`. It looks like an
   anchor and is not one, so a regex for a worked anchor must require digits
   after the colon. `grep -cE "[a-zA-Z0-9_/.-]+[.]py:[0-9]+"` on the skill
   prints `0` today.
2. Do not add a second file to the skill directory (DEC-084): `init` copies
   only `SKILL.md`, so a `reference.md` never reaches a scaffolded project.
3. Neither declared file is in `machine.FENCED` (which names
   `.project/pipeline.toml`, `pipeline/hooks/dangerous-commands.py`,
   `pipeline/harnesses/claude-code.toml`, `pipeline/core/machine.py`,
   `pipeline/core/ticket.py`, `pipeline/core/worktree.py`, `.project/stages/`),
   so this ticket does not park at `awaiting-merge` for the fence.
4. `tests/test_stages.py` already imports `re` at line 3; no new import.

Re-planned after the Tier A gate failed one acceptance criterion: it pinned the
absolute total `30 passed` copied from this section. The plan steps are
unchanged. `## Acceptance criteria` now states each check as an exit status plus
a re-measurement against cf5a10e, and carries no absolute count.

## Decisions checked

- DEC-056 -- `pipeline/templates/skills/file-ticket/SKILL.md` is the only copy;
  the repo's `.claude/` path is a symlink. Binding: this plan edits the
  template, and adds no second real file.
- DEC-084 -- one `SKILL.md` per skill directory, no sibling reference file, and
  the trigger path stays first with reference material last. Binding: the
  docs-only shape goes into this same file, as a section after the four filing
  steps.
- DEC-026 -- names `.claude/skills/file-ticket/SKILL.md` among its files and
  describes the cheap route the skill's step 4 documents. Consulted; it
  constrains nothing here, because this plan changes no routing text.

Grep terms used against `.project/decisions/`: `file-ticket`, `skill`,
`docs-only`, `documentation`, `anchor`, `path:line`, `templates/skills`,
`triage`, `rejected`, `failing test`, `reproduc`.

## Plan

1. Extend the repro test in `tests/test_stages.py` (function `test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape`, lines 407-415) with two assertions after the existing `docs-only` assertion, so the test also holds the worked example and the cited pattern:

        assert re.search(r"[A-Za-z0-9_/.-]+[.]py:[0-9]+", text), (
            f"{skill} states the anchor rule but carries no worked path:line anchor")
        assert "test_the_config_skill_names_every_knob_the_code_reads" in text, (
            f"{skill} does not name TICKET-084's test as the docs-only pattern")

2. Run `uv run --group dev pytest -q tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape` and confirm it still fails on the first assertion, `does not require a path:line anchor`; the two new assertions are red too, because `grep -cE "[a-zA-Z0-9_/.-]+[.]py:[0-9]+" pipeline/templates/skills/file-ticket/SKILL.md` prints `0` until step 4. Commit nothing here; `tests/test_stages.py` is committed in step 8 with the skill.

3. In `pipeline/templates/skills/file-ticket/SKILL.md`, insert this paragraph after the "What makes that work" paragraph, which ends at line 117 with "which the gate refuses because they cannot recur.", and before the "Do not touch the frontmatter" paragraph at line 119, with a blank line on each side:

        **Anchor the mechanism in code.** Name the location as `path:line` --
        `pipeline/core/gate.py:383` -- and quote the two or three lines it points at.
        Triage is charged per run, and a prose-only summary makes it re-find the
        location you already had open. Give the line number you saw and the commit
        you saw it on; a line that has since moved still lands triage within a few
        lines of the code.

4. In `pipeline/templates/skills/file-ticket/SKILL.md`, replace lines 96-109 -- the body of the worked `## Summary` example, inside the fence that opens at line 95 and closes at line 110 -- with this, which carries an anchor and moves the commit onto the anchor line:

        ## Summary

        evict() never drops the key when the cache is at capacity

        `Cache.evict()` is supposed to make room by removing the LRU entry. It picks
        the victim and never removes it -- `cache/lru.py:64`, on main at a1b2c3d:

            def evict(self):
                if len(self._d) > self.maxsize:
                    self._lru()        # picks the victim, never deletes it

        With `maxsize=2`, adding a third key leaves all three present, so the cache
        grows without bound.

            >>> c = Cache(maxsize=2); c.put("a",1); c.put("b",2); c.put("c",3)
            >>> len(c)
            3          # expected 2

        Expected: `len(c) == 2` after the third put, with "a" gone. The exact
        failure a test should show is `AssertionError: 3 != 2`.

5. In `pipeline/templates/skills/file-ticket/SKILL.md`, add this new top-level section between the end of step 4 at line 171 and the `## Do not` heading at line 173, with a blank line on each side:

        ## A docs-only ticket

        A ticket whose symptom is in a document -- a skill, a README, a stage prompt
        -- is filable, but not in the shape above. Triage's job is a *failing test*,
        and a wrong sentence has no runtime behaviour to fail on. The test asserts
        the document's own text instead.

        TICKET-084 is the worked precedent. The `pipeline-config` skill named none
        of five config knobs the code reads, and
        `tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads`
        reads that file and asserts each name is in it -- red before the edit, green
        after, exactly like a bug's test.

        So a docs-only `## Summary` carries two things a code ticket does not:

        - **The test file the assertion goes in**, by path. An existing file where
          this project already tests documents, not a new one.
        - **The assertion itself**, close to literal. "the skill must name
          `path:line`" is enough for triage to write `assert "path:line" in text`.

        Anchor the document the way you anchor code: `path:line` plus the lines that
        are wrong, or the section that should exist and does not.

        Without both, step 2's first push-back applies: there is no symptom a test
        can fail on, so triage returns `result: rejected` and the ticket dies there.

6. In `pipeline/templates/skills/file-ticket/SKILL.md`, extend step 2's first push-back bullet at lines 74-76 with one sentence, so the bullet ends: "Say so and ask for the symptom. A symptom that lives in a document is still filable -- see *A docs-only ticket* below for the shape it needs."

7. Run `uv run --group dev pytest -q tests/test_stages.py` and confirm it exits 0 with no failure reported: the repro test passes, and no other test in `tests/test_stages.py` regressed against the cf5a10e baseline recorded in `## Digest`.

8. Commit `pipeline/templates/skills/file-ticket/SKILL.md` and `tests/test_stages.py` together on branch `ticket/098`, with the message `docs(TICKET-098): require a path:line anchor and name the docs-only ticket shape`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape`
  exits 0. The same command exits non-zero on cf5a10e, which is the commit this
  branch starts from.
- `uv run --group dev pytest -q tests/test_stages.py` exits 0, so no test in the
  file fails. Re-measure the same command on cf5a10e: its only failure there is
  this ticket's repro test, so any failure that survives this change is a
  regression this ticket introduced.
- `uv run --group dev pytest -q tests/test_stages.py::test_the_repo_skill_is_the_packaged_file`
  exits 0: the edit went into the template, and
  `.claude/skills/file-ticket/SKILL.md` is still a symlink to it.
- `grep -q "^## A docs-only ticket" pipeline/templates/skills/file-ticket/SKILL.md`
  exits 0.
- `grep -qE "[a-zA-Z0-9_/.-]+[.]py:[0-9]+" pipeline/templates/skills/file-ticket/SKILL.md`
  exits 0, and the same grep reading
  `git show cf5a10e:pipeline/templates/skills/file-ticket/SKILL.md` exits 1, so
  the worked anchor is new in this change.
- `git diff --name-only cf5a10e` lists `pipeline/templates/skills/file-ticket/SKILL.md`
  and `tests/test_stages.py`, and no other path.

## Decisions

**The docs-only shape lives in `file-ticket/SKILL.md`, not in a sibling file.**
DEC-084 settled this for the `pipeline-config` skill: `cmd_init()` copies
exactly `<skill>/SKILL.md` per directory under `SKILLS_DIR`, so a `reference.md`
beside it never reaches a scaffolded project and the shipped skill would point
at a path that is not there. The section sits after the four filing steps and
before `## Do not` because it is a variant of the filing path, not a step every
ticket walks.

**The worked `## Summary` example must keep a `path:line`-shaped anchor.**
`tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape`
greps the skill for `[A-Za-z0-9_/.-]+[.]py:[0-9]+`, which is deliberately
stricter than the literal string `path:line`: the skill already contained
`machine.py:BOUNDS`, which reads like an anchor and is not one, so requiring
digits after the colon is what makes the example prove the rule. Reword the
example freely; keep a real line number in it.

**The docs-only section names TICKET-084's test by id, and the repro test
asserts that name.** Renaming
`tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads`
breaks the repro test on purpose: the cited precedent has to be a test that
exists, or the section teaches a pattern nobody can read.

## Rollback

`git revert` the single commit from step 8, or restore both files with
`git checkout cf5a10e -- pipeline/templates/skills/file-ticket/SKILL.md tests/test_stages.py`.
Nothing else reads either file at runtime: the skill is prose a session loads
before filing, and the test only reads it. Reverting the skill without the test
leaves the repro test red; revert both together.

## Thread

### 2026-08-29 04:25:14Z · human · note · by=chezzijr

**note from chezzijr**

From the operator: TICKET-092 landed `pipeline note` on 0f4dff2 -- when you write the docs-only shape, the two extra_md-style examples in this repo are .project/stages/planning.extra.md (written by hand 2026-08-29) and TICKET-084's test.

### 2026-08-29 05:14:33Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 05:30:00Z · triage · finding · by=triage

**triage confirms the gap**

Read `pipeline/templates/skills/file-ticket/SKILL.md` in full: the step-3
summary guidance names no `path:line` anchor, and no worked example carries
one. No section names a docs-only shape or points at
`tests/test_stages.py::test_the_config_skill_names_every_knob_the_code_reads`
as the pattern. Both matches the ticket's claim.

Wrote and committed a failing test,
`tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape`,
asserting the skill text contains `path:line` and `docs-only`. It fails now
with `AssertionError: ... does not require a path:line anchor`. Committed as
cf5a10e on branch `ticket/098`.

result: ok

### 2026-08-29 05:15:17Z · triage · session · session=0b5fe8a9-9fe0-48a5-be83-3715cbf46cda

`triage` ran as session `0b5fe8a9-9fe0-48a5-be83-3715cbf46cda`
- replay: `claude --resume 0b5fe8a9-9fe0-48a5-be83-3715cbf46cda`
- log: `.project/logs/TICKET-098-triage-0b5fe8a9.log`
- cost: $0.27 of a $3 cap
- tokens: 3,253 out · 28 in · 521,472 cache read · 32,167 cache write

### 2026-08-29 05:15:17Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced missing path:line anchor guidance and missing docs-only shape in file-ticket SKILL.md with a failing test, committed on ticket branch

### 2026-08-29 · planning · finding · by=planning

**plan written: one file of prose, one test extended**

The ticket stands on its own: one skill file, one test file, no second
subsystem. Both edits land in `pipeline/templates/skills/file-ticket/SKILL.md`,
the only copy of the skill (DEC-056).

I extended the scope of the repro test rather than adding a second test. Triage's
version asserts the two substrings `path:line` and `docs-only`, which the skill
could satisfy while the worked example stayed prose-only. Step 1 adds two
assertions: a regex `[A-Za-z0-9_/.-]+[.]py:[0-9]+` for a worked anchor, and the
literal `test_the_config_skill_names_every_knob_the_code_reads` for the cited
precedent. Both are red today --
`grep -cE "[a-zA-Z0-9_/.-]+[.]py:[0-9]+" pipeline/templates/skills/file-ticket/SKILL.md`
prints `0` -- so the test stays red on base, as the gate requires.

Baseline measured on cf5a10e: `uv run --group dev pytest -q tests/test_stages.py`
prints `1 failed, 30 passed in 0.27s`, the failure being this ticket's repro test.

Out of scope, noted not fixed: `.project/stages/planning.extra.md` is prose no
test reads, so nothing holds it to the gate it describes. That is a separate
ticket.

result: ok

### 2026-08-29 05:21:46Z · planning · session · session=08a3f069-25c5-4c03-9ad9-48ff14265e0f

`planning` ran as session `08a3f069-25c5-4c03-9ad9-48ff14265e0f`
- replay: `claude --resume 08a3f069-25c5-4c03-9ad9-48ff14265e0f`
- log: `.project/logs/TICKET-098-planning-08a3f069.log`
- cost: $2.20 of a $10 cap
- tokens: 31,806 out (12,009 thinking) · 44 in · 1,204,170 cache read · 80,480 cache write

### 2026-08-29 05:21:46Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned the path:line anchor rule, the anchored worked example, and a docs-only section for file-ticket/SKILL.md, held by two added assertions in the repro test

### 2026-08-29 05:45:16Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape` fails as required
```
mmary guidance never says to anchor the mechanism
        in code (a `path:line` plus a quoted snippet), and has no shape for a
        docs-only ticket like TICKET-084's, which asserted the skill's own text
        in a test."""
        skill = C.SKILL_TEMPLATE
        text = skill.read_text()
>       assert "path:line" in text, f"{skill} does not require a path:line anchor"
E       AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-098/pipeline/templates/skills/file-ticket/SKILL.md does not require a path:line anchor
E       assert 'path:line' in "---\nname: file-ticket\ndescription: File a ticket into this repo's pipeline (.project/tickets/). Use when the user r...h append to the\n  thread properly. To edit a running ticket by hand, interrupt the stage first\n  (`k` in the TUI).\n"

tests/test_stages.py:414: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape` fails on base `main` too -- the bug is not already fixed upstream
```
E       assert 'path:line' in "---\nname: file-ticket\ndescription: File a ticket into this repo's pipeline (.project/tickets/). Use when the user r...h append to the\n  thread properly. To edit a running ticket by hand, interrupt the stage first\n  (`k` in the TUI).\n"

tests/test_stages.py:414: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-3vaikzqw/base
      Built pipeline @ file:///tmp/pipeline-base-3vaikzqw/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```
- acceptance criterion pins an absolute count copied from `## Digest` (30): - `uv run --group dev pytest -q tests/test_stages.py` reports no failures. The baseline measured on cf5a10e was `1 failed, 30 passed`, the one failure being this ticket's repro test, so any other failure is a regression. -- a total any other ticket can move is not a property of this change -- state it as a relation to a measured baseline, or re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check

### 2026-08-29 05:45:16Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion pins an absolute count copied from `## Digest` (30): - `uv run --group dev pytest -q tests/test_stages.py` reports no failures. The baseline measured on cf5a10e was `1 failed, 30 passed`, the one failure being this ticket's repro test, so any other failure is a regression. -- a total any other ticket can move is not a property of this change -- state it as a relation to a measured baseline, or re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check

### 2026-08-29 · planning · finding · by=planning

**re-planned: the gate's one finding was an acceptance criterion, not the plan**

The Tier A gate passed both reproduction checks and failed exactly one
criterion: "The baseline measured on cf5a10e was `1 failed, 30 passed`" pins an
absolute total copied from `## Digest`, which any other ticket can move.

I left the eight plan steps, `## Decisions checked` and `## Decisions`
unchanged; the gate charged nothing against them. I rewrote every criterion as
an exit status re-measured at check time, and removed both absolute counts. The
suite criterion now says the command exits 0 and names cf5a10e as the baseline
to re-measure. The anchor criterion now pairs
`grep -qE "[a-zA-Z0-9_/.-]+[.]py:[0-9]+" pipeline/templates/skills/file-ticket/SKILL.md`
exiting 0 against the same grep reading
`git show cf5a10e:pipeline/templates/skills/file-ticket/SKILL.md`, which exits
1 -- I ran that and it printed `base grep exit=1`. Step 7 lost the same pinned
total and now says the command exits 0.

Re-verified in the worktree: the skill is 186 lines, `## Do not` is at line 173,
the worked summary fence spans 95-110, step 2's first push-back bullet is 74-76,
and the repro test is `tests/test_stages.py:407-415`. Every line number the plan
cites still holds. DEC-056, DEC-084 and DEC-026 all exist under
`.project/decisions/`.

result: ok

### 2026-08-29 05:47:32Z · planning · session · session=670b9f6f-91ca-4b83-8c99-d718b7b42482

`planning` ran as session `670b9f6f-91ca-4b83-8c99-d718b7b42482`
- replay: `claude --resume 670b9f6f-91ca-4b83-8c99-d718b7b42482`
- log: `.project/logs/TICKET-098-planning-670b9f6f.log`
- cost: $1.07 of a $10 cap
- tokens: 10,623 out (3,906 thinking) · 32 in · 656,922 cache read · 47,480 cache write

### 2026-08-29 05:47:32Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-planned after the Tier A gate: acceptance criteria now state exit statuses and a re-measurement against cf5a10e, with no absolute count; plan steps unchanged

### 2026-08-29 05:48:07Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-29 05:45:16Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape` fails on base `main` too -- the bug is not already fixed upstream
```
E       assert 'path:line' in "---\nname: file-ticket\ndescription: File a ticket into this repo's pipeline (.project/tickets/). Use when the user r...h append to the\n  thread properly. To edit a running ticket by hand, interrupt the stage first\n  (`k` in the TUI).\n"

tests/test_stages.py:414: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-d0x4_rq8/base
      Built pipeline @ file:///tmp/pipeline-base-d0x4_rq8/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```

### 2026-08-29 · plan-validation · finding · by=plan-validation

**Tier B: PASS. All eight items pass; nothing unverified.**

- **Root cause.** The shipped skill template teaches only prose summaries and
  names no route for a symptom that lives in a document. `grep -cE
  "[a-zA-Z0-9_/.-]+[.]py:[0-9]+"` on the skill returns 0 matches, and the file
  holds neither `path:line` nor `docs-only`. Steps 3-6 change the guidance the
  template ships, not just the four substrings the test greps.
- **Decision conflict.** DEC-056 and DEC-084 both bind and the plan complies:
  it edits `pipeline/templates/skills/file-ticket/SKILL.md`, adds no sibling
  file, and puts the new section after the four filing steps. DEC-026 changes
  no routing text. All three exist under `.project/decisions/`.
- **Scope.** Eight steps, two files. Every step traces to a criterion or to the
  ticket's Expected (a), "with the worked example updated to carry one".
- **Falsifiable criteria.** Criterion 5 pairs the anchor grep on the worktree
  (exits 0) against `git show cf5a10e:` (exits 1), so a no-op edit fails it.
  Criterion 6 pins the diff to exactly two paths.
- **No research left.** Every line number the plan cites holds: fence 95-110,
  "What makes that work" at 112, "Do not touch the frontmatter" at 119,
  `## Do not` at 173, file 186 lines, repro test at 407-415.
- **Riskiest step.** Step 5. It cites lines 171 and 173, measured before steps
  3 and 4 add roughly ten lines above them. Each step also names its text
  anchor (`## Do not`), so an edit by content survives the shift. `## Rollback`
  states the fallback for both files.
- **Regression surface.** Three tests read the skill:
  `test_the_repo_skill_is_the_packaged_file` (symlink and size only),
  `test_data_files_live_inside_the_package_so_they_survive_install` (existence
  only), and the repro test. `tests/test_cli.py:475` compares the installed
  copy to the source, and the re-init test overwrites it; both are
  content-agnostic. Criteria 2 and 3 cover that surface. No test outside
  `tests/test_stages.py` reads the skill's text.
- **Blast radius.** Two files, one commit. It matches the class.

Note, not a scored finding: the criteria are substring greps, so they cannot
prove the added prose is useful. That is the limit of the docs-only pattern the
ticket cites from TICKET-084; the review stage reads the diff.

result: ok

### 2026-08-29 05:50:27Z · plan-validation · session · session=6ebb6422-1a5c-4436-a1a9-f154ef253afc

`plan-validation` ran as session `6ebb6422-1a5c-4436-a1a9-f154ef253afc`
- replay: `claude --resume 6ebb6422-1a5c-4436-a1a9-f154ef253afc`
- log: `.project/logs/TICKET-098-plan-validation-6ebb6422.log`
- cost: $1.05 of a $3 cap
- tokens: 10,572 out (3,517 thinking) · 32 in · 638,743 cache read · 46,316 cache write

### 2026-08-29 05:50:27Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight judgment items: root cause is the shipped template's missing anchor rule and docs-only shape, criteria are exit statuses re-measured against cf5a10e, two files, no test outside tests/test_stages.py reads the skill text

### 2026-08-29 06:03:00Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: tests/test_stages.py already imports re at line 3, so step 1's regex assertion runs; the plan edits pipeline/templates/skills/file-ticket/SKILL.md, which is the symlink target and what pipeline init copies; step 4 rewrites the worked example to carry a real path:line anchor rather than only stating the rule; step 6 makes the no-symptom push-back point at the docs-only shape instead of rejecting. Nothing fenced.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: tests/test_stages.py already imports re at line 3, so step 1's regex assertion runs; the plan edits pipeline/templates/skills/file-ticket/SKILL.md, which is the symlink target and what pipeline init copies; step 4 rewrites the worked example to carry a real path:line anchor rather than only stating the rule; step 6 makes the no-symptom push-back point at the docs-only shape instead of rejecting. Nothing fenced.**

### 2026-08-29 06:03:36Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape` fails as required
```
mmary guidance never says to anchor the mechanism
        in code (a `path:line` plus a quoted snippet), and has no shape for a
        docs-only ticket like TICKET-084's, which asserted the skill's own text
        in a test."""
        skill = C.SKILL_TEMPLATE
        text = skill.read_text()
>       assert "path:line" in text, f"{skill} does not require a path:line anchor"
E       AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-098/pipeline/templates/skills/file-ticket/SKILL.md does not require a path:line anchor
E       assert 'path:line' in "---\nname: file-ticket\ndescription: File a ticket into this repo's pipeline (.project/tickets/). Use when the user r...h append to the\n  thread properly. To edit a running ticket by hand, interrupt the stage first\n  (`k` in the TUI).\n"

tests/test_stages.py:417: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================

```
- ok: `tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape` fails on base `main` too -- the bug is not already fixed upstream
```
E       assert 'path:line' in "---\nname: file-ticket\ndescription: File a ticket into this repo's pipeline (.project/tickets/). Use when the user r...h append to the\n  thread properly. To edit a running ticket by hand, interrupt the stage first\n  (`k` in the TUI).\n"

tests/test_stages.py:417: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-wh5d4_w8/base
      Built pipeline @ file:///tmp/pipeline-base-wh5d4_w8/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```

### 2026-08-29 06:03:37Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-29 · implementing · todo

**Todo list**

1. [x] Extend the repro test with two new assertions (worked anchor, cited test name).
2. [x] Confirm RED on the extended repro test.
3. [x] Add the "Anchor the mechanism in code" paragraph.
4. [x] Rewrite the worked `## Summary` example to carry a real `path:line` anchor.
5. [x] Add `## A docs-only ticket` section before `## Do not`.
6. [x] Extend step 2's "No observable symptom" bullet with the cross-reference.
7. [x] Run the full `tests/test_stages.py` suite and confirm GREEN, no regressions.
8. [x] Commit both files on `ticket/098`.

### 2026-08-29 · implementing · finding

**Implemented all eight plan steps. `d5618ec`.**

RED confirmed first: `tests/test_stages.py::test_the_file_ticket_skill_requires_a_code_anchor_and_a_docs_only_shape`
failed on the first assertion, `does not require a path:line anchor`, before any
skill edit -- the expected failure. After editing the skill (anchor rule,
anchored worked example, `## A docs-only ticket` section, push-back
cross-reference), `uv run --group dev pytest -q tests/test_stages.py` prints
`31 passed in 0.18s`, up from the recorded baseline `1 failed, 30 passed`.

`grep -q "^## A docs-only ticket"` and
`grep -qE "[a-zA-Z0-9_/.-]+[.]py:[0-9]+"` both exit 0 on the worktree copy;
the same anchor grep against `git show cf5a10e:...SKILL.md` exits 1, so the
anchor is new. `test_the_repo_skill_is_the_packaged_file` passes, confirming
the symlink still points at the edited template.

One deviation from the criterion's literal command: `git diff --name-only
cf5a10e` lists 11 files, not 2, because the branch was rebased onto a later
base (TICKET-091's commits landed on `main` after cf5a10e and are now
ancestors of this branch, per the `revalidating -> implementing` re-gate
entry above). `git diff --name-only fdcb228 HEAD` -- the branch's actual
merge-base -- lists exactly the two declared files, matching the criterion's
intent. Committed as `d5618ec docs(TICKET-098): require a path:line anchor
and name the docs-only ticket shape`.

### 2026-08-29 06:05:31Z · implementing · session · session=13eb8fb7-86d1-4318-aca5-d8f144852548

`implementing` ran as session `13eb8fb7-86d1-4318-aca5-d8f144852548`
- replay: `claude --resume 13eb8fb7-86d1-4318-aca5-d8f144852548`
- log: `.project/logs/TICKET-098-implementing-13eb8fb7.log`
- cost: $0.52 of a $8 cap
- tokens: 8,504 out (600 thinking) · 46 in · 1,150,688 cache read · 49,886 cache write

### 2026-08-29 06:05:31Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added anchor rule, anchored worked example, and docs-only section to file-ticket/SKILL.md; extended the repro test with two assertions; all 31 tests pass; committed d5618ec.

### 2026-08-29 · review · finding

**Review of `fdcb228..HEAD` (`811d59c`, `d5618ec`): no blocking findings.**

The delta is the two declared files and nothing else: `git diff --name-only
fdcb228 HEAD` prints `pipeline/templates/skills/file-ticket/SKILL.md` and
`tests/test_stages.py`. Every plan step landed as written -- the anchor
paragraph after "What makes that work", the worked example carrying
`cache/lru.py:64`, the `## A docs-only ticket` section before `## Do not`, the
push-back cross-reference, and the two test assertions.

Measured: `uv run --group dev pytest -q` prints `466 passed in 34.48s`, so
nothing regressed outside the ticket's own file. `grep -q "^## A docs-only
ticket"` and `grep -qE "[a-zA-Z0-9_/.-]+[.]py:[0-9]+"` exit 0 on the skill; the
same anchor grep on `git show cf5a10e:...SKILL.md` exits 1.
`pipeline/core/gate.py:383`, cited in the anchor rule, is real code in a
656-line file.

Non-blocking notes:

1. **low.** The regex assertion is satisfied by the rule paragraph's own
   `pipeline/core/gate.py:383`, so deleting the anchor from the worked example
   alone leaves the test green. `## Decisions` claims the regex pins the
   example; it pins the file.
2. **info.** The criterion's literal `git diff --name-only cf5a10e` is
   unmeasurable: the rebase orphaned cf5a10e, so it is not an ancestor of
   `main` or `HEAD`. `git merge-base HEAD main` is `fdcb228`, which is what I
   measured.

### 2026-08-29 06:16:38Z · review · session · session=1aca4ef6-029d-4a47-bae7-9ed66e516f32

`review` ran as session `1aca4ef6-029d-4a47-bae7-9ed66e516f32`
- replay: `claude --resume 1aca4ef6-029d-4a47-bae7-9ed66e516f32`
- log: `.project/logs/TICKET-098-review-1aca4ef6.log`
- cost: $1.26 of a $5 cap
- tokens: 11,297 out (4,484 thinking) · 50 in · 1,003,262 cache read · 47,093 cache write

### 2026-08-29 06:16:38Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ delta d5618ec meets every acceptance criterion; full suite 466 passed in 34.48s; two non-blocking notes appended

### 2026-08-29 06:17:35Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 06:17:36Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/098


Rebasing (1/2)
Auto-merging tests/test_stages.py
CONFLICT (content): Merge conflict in tests/test_stages.py
error: could not apply 811d59c... test(TICKET-098): reproduce missing code anchor and docs-only guidance in file-ticket skill
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply 811d59c... # test(TICKET-098): reproduce missing code anchor and docs-only guidance in file-ticket skill
Auto-merging tests/test_stages.py
CONFLICT (content): Merge conflict in tests/test_stages.py
Automatic merge failed; fix conflicts and then commit the result.

```

### 2026-08-29 06:25:10Z · human · note · by=chezzijr

**resumed** by chezzijr -> `merging`, reset []

### 2026-08-29 06:25:10Z · human · answer · by=chezzijr

**note from chezzijr**

conflict with TICKET-097 in tests/test_stages.py resolved by hand: all three tests kept, they assert different files and nothing overlaps. 478 passed in the worktree.

### 2026-08-29 06:25:11Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/098


Rebasing (1/2)Auto-merging tests/test_stages.py
CONFLICT (content): Merge conflict in tests/test_stages.py
error: could not apply 811d59c... test(TICKET-098): reproduce missing code anchor and docs-only guidance in file-ticket skill
hint: Resolve all conflicts manually, mark them as resolved with
hint: "git add/rm <conflicted_files>", then run "git rebase --continue".
hint: You can instead skip this commit: run "git rebase --skip".
hint: To abort and get back to the state before "git rebase", run "git rebase --abort".
hint: Disable this message with "git config set advice.mergeConflict false"
Could not apply 811d59c... # test(TICKET-098): reproduce missing code anchor and docs-only guidance in file-ticket skill
Already up to date.
Updating f801f9c..8ec6cab
Fast-forward
 pipeline/templates/skills/file-ticket/SKILL.md | 52 +++++++++++++++++++++++---
 tests/test_stages.py                           | 15 ++++++++
 2 files changed, 61 insertions(+), 6 deletions(-)

```

### 2026-08-29 06:25:11Z · merging · decision

decision recorded as `DEC-098`
