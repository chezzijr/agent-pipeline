---
id: TICKET-097
stage: done
class: bugfix
branch: ticket/097
test_file: tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path
files_declared:
- README.md
- pipeline/templates/pipeline.toml
- pipeline/templates/skills/pipeline-config/SKILL.md
- tests/test_stages.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 7
  plan_files: 4
  no_result: 0
  structural_gate_failures: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 1da22c8a-dce3-4b93-acfc-5b889b625d66
  log: .project/logs/TICKET-097-review-1da22c8a.log
  cost_usd: 1.128566
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified: docs-only but red first via tests/test_stages.py,
  the pattern TICKET-098 exists to document. Step 6 resolves its RECLAIM_SENTENCE
  placeholder by grepping for worktree_teardown at implementation time, and files_conflict
  serialises 091 ahead of 097 on README.md, pipeline.toml and SKILL.md, so the grep
  sees the real answer rather than racing it. Content matches the measurement: sccache
  hashes the rustc command line, cargo puts the target dir in it, CARGO_INCREMENTAL=0
  costs rebuilds, ccache base_dir is the exception. Nothing fenced.'
approved_at: '2026-08-29T05:29:58.645033+00:00'
---

## Summary

Implemented, committed and reviewed. `README.md`,
`pipeline/templates/pipeline.toml` and
`pipeline/templates/skills/pipeline-config/SKILL.md` now state the cost of
keying a build cache, the shareability property (a key must exclude the
checkout path), the measured `sccache` table, and the three-build procedure.
`tests/test_stages.py` gained the second guard test from step 1. Two commits:
`aa03847` (red test) and `6570765` (docs).

Step 6 resolved `RECLAIM_SENTENCE` to "worktree_teardown runs before the
dispatcher removes a worktree, and is where to reclaim the keyed directory",
because the rebase merged TICKET-091 and `grep -c worktree_teardown
pipeline/core/worktree.py` prints `6`. Review confirmed that against the code:
`drop_worktree()` runs the hook at `pipeline/core/worktree.py:95` and removes
the worktree at line 100.

`implementing` reflowed one wrap point in all three files, same words, so
`excludes the checkout path` sits on one line for the step-1 guard test.

Review passed the delta with no blocking finding. All six acceptance criteria
hold, `uv run --group dev pytest -q tests/test_stages.py` prints
`32 passed in 0.18s`, and the full suite prints `471 passed in 33.51s`. Two
nits, both non-blocking: three added lines are 83 characters against the ~79
the surrounding prose wraps at, and `README.md` names `worktree_teardown`
three lines before the paragraph that introduces it.

## Reproduction

`tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path`

Command: `uv run --group dev pytest -q tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path`

Failure output:
```
AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-097/README.md does not say when a cache is shareable
assert 'shareable' in '# Ticket-driven agent pipeline\n...'
```

expect: does not say when a cache is shareable

## Digest

- Files touched: `README.md` (the build-cache paragraph, lines 350-358), `pipeline/templates/pipeline.toml` (the `worktree_setup` comment block, lines 51-60), `pipeline/templates/skills/pipeline-config/SKILL.md` (the `worktree_setup` section, lines 173-183), `tests/test_stages.py` (the guard tests).
- Key functions: none. Three of the four files are prose or data. The only code is the tests, which read `C.CONFIG_TEMPLATE`, `C.SKILLS_DIR / "pipeline-config" / "SKILL.md"` and `Path(__file__).resolve().parent.parent / "README.md"`. `tests/test_stages.py` already imports `Path` and `pipeline.core.config as C`.
- Entry point: `tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path`, at line 407, committed red in `c4cbb38`. Measured baseline: `uv run --group dev pytest -q tests/test_stages.py` prints `1 failed, 30 passed in 0.19s`, and that one failure is this ticket's repro test.
- Notation for this plan: a step's indented block is the literal text to insert, and `RECLAIM_SENTENCE` inside it is a placeholder step 6 replaces. No inserted block uses a numbered list, because the plan gate reads a line starting `N.` as a plan step.
- Gotcha: the previous plan failed the Tier A gate for exactly that. Its README block spelled the three-build procedure as a `1.` / `2.` / `3.` list, and the gate scored those three lines as plan steps naming no declared file. This plan writes the same procedure as a dash list.
- Gotcha: `worktree_teardown` does not exist in this tree. `grep -rn worktree_teardown pipeline` matches nothing, and `pipeline/core/worktree.py:84` reads `worktree_setup` only. TICKET-091 adds the key and sits at stage `plan-validation`, unmerged. Step 6 greps for the key and picks between two written sentences, so this ticket never names a key the code ignores.
- Gotcha: the existing keyed-per-checkout advice is correct and stays. Commit `40e44f9` added it to all three files. This ticket appends the cost, the property and the procedure; it rewrites nothing.
- Gotcha: the skill's `description` frontmatter already carries the trigger "when builds interfere across ticket worktrees". DEC-084 forbids trimming it and forbids a second file in the skill directory.
- Gotcha: `pipeline/templates/pipeline.toml` is a commented example. Every line added there starts with `#`, or `pipeline init` scaffolds a config that sets keys nobody asked for. Measured: `grep -c "^[^#]" pipeline/templates/pipeline.toml` prints `4` on `c4cbb38`.

## Decisions checked

Grep terms used in `/home/chezzijr/proj/agent-pipeline/.project/decisions/`: `cache`, `ccache`, `sccache`, `worktree_setup`, `teardown`, `README`, `SKILL.md`. Every id below is a file in that directory, checked with `ls`.

- DEC-084 (active) binds this change. It fixes the pipeline-config skill at one `SKILL.md` with the reference half last, and it requires a documented knob to reach both the template comments and the skill. This plan edits both files in place, adds no file, and leaves the `description` line alone.
- DEC-033, DEC-011 and DEC-059 matched the grep on `cache` and are unrelated: they cover the model `triage` runs on, the daemon's frozen event contract, and interactive-stage gating.
- No decision record covers build-cache advice, `sccache` or `worktree_teardown`.

## Plan

1. Add this test to `tests/test_stages.py`, directly below the repro test `test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path`, whose body ends at line 417:

       def test_the_build_cache_docs_carry_the_three_build_shareability_check():
           """TICKET-097: the word `shareable` is only actionable next to the
           measurement it came from and the procedure that decides it for
           another toolchain, so a later trim must not leave the word alone."""
           skill = C.SKILLS_DIR / "pipeline-config" / "SKILL.md"
           readme = Path(__file__).resolve().parent.parent / "README.md"
           for p in (readme, C.CONFIG_TEMPLATE, skill):
               text = p.read_text().lower()
               for marker in ("excludes the checkout path", "sccache", "wipe"):
                   assert marker in text, f"{p} does not carry {marker!r}"

2. Run `uv run --group dev pytest -q tests/test_stages.py::test_the_build_cache_docs_carry_the_three_build_shareability_check` and confirm it fails with `AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-097/README.md does not carry 'excludes the checkout path'`, then commit `tests/test_stages.py` as `test(TICKET-097): require the worked example and the three-build check in the cache docs`.
3. In `README.md`, keep lines 350-358 exactly as they are and insert after line 358 (the line `prefix) or leave it unshared.`) a blank line and then this text, verbatim:

       Keying is not free. Every ticket pays a cold build, and every keyed
       directory outlives the worktree it was named for -- 18 keys, 9.1G, 2 live
       worktrees, measured on one project. RECLAIM_SENTENCE

       **A cache is shareable across worktrees only if its key excludes the
       checkout path, and most keys do not.** A content-addressed compiler cache
       looks like the escape hatch. `sccache` is not one: it hashes the rustc
       command line, and cargo puts the target directory in it (`--out-dir`,
       `-L dependency=`), so the per-checkout target dirs that avoid the
       stale-artifact trap guarantee a miss across tickets. Measured:

       ```
       build | CARGO_TARGET_DIR              | sccache result
       ------+-------------------------------+------------------------
       1st   | .../t1                        | miss (compiles, stores)
       2nd   | .../t2, same source and flags | miss
       3rd   | .../t1 again, artifacts wiped | hit
       ```

       It also needs `CARGO_INCREMENTAL=0`, which slows repeated builds inside
       one ticket: net negative in both directions. `ccache` can normalise the
       path away (`base_dir`); most tools cannot.

       Three builds decide it for any toolchain:

       - Build in worktree A. Expect a miss.
       - Build in worktree B, same source and flags. A hit means the cache is
         shareable across checkouts; a miss means its key carries the checkout
         path.
       - Wipe A's artifacts and rebuild A. A hit confirms the cache works at
         all, which is what makes the second build's miss attributable to the
         key.

4. In `pipeline/templates/pipeline.toml`, keep the comment at lines 55-60 as it is and insert after line 60 this block, verbatim, every line a comment:

       #
       # Keying is not free: a cold build per ticket, and each keyed
       # directory outlives its worktree (18 keys, 9.1G, 2 live worktrees,
       # measured on one project). RECLAIM_SENTENCE
       #
       # A cache is shareable across worktrees only if its key excludes the
       # checkout path, and most keys do not. sccache hashes the rustc
       # command line and cargo puts the target dir in it (--out-dir,
       # -L dependency=), so per-checkout target dirs miss on every ticket,
       # and the CARGO_INCREMENTAL=0 it needs slows rebuilds inside one
       # ticket. ccache normalises the path away with base_dir; most tools
       # cannot. Three builds decide it for any toolchain: build in worktree
       # A (expect a miss); build in B with the same source and flags (a hit
       # means shareable); wipe A and rebuild A (a hit confirms the cache
       # works at all, which is what makes the second build's miss
       # attributable to the key).

5. In `pipeline/templates/skills/pipeline-config/SKILL.md`, keep lines 177-183 as they are and insert after line 183 a blank line and then this text, verbatim, at the file's existing prose width:

       Keying is not free: a cold build per ticket, and each keyed directory
       outlives its worktree (18 keys, 9.1G, 2 live worktrees, measured on
       one project). RECLAIM_SENTENCE

       **A cache is shareable across worktrees only if its key excludes the
       checkout path, and most keys do not.** `sccache` hashes the rustc
       command line and cargo puts the target dir in it (`--out-dir`,
       `-L dependency=`), so per-checkout target dirs miss on every ticket:
       a build in `.../t1` compiles and stores, the same source in `.../t2`
       misses, and `.../t1` with its artifacts wiped hits. The
       `CARGO_INCREMENTAL=0` it needs also slows rebuilds inside one ticket.
       `ccache` normalises the path away with `base_dir`; most tools cannot.

       Three builds decide it for any toolchain: build in worktree A (expect
       a miss); build in B with the same source and flags (a hit means
       shareable); wipe A and rebuild A (a hit confirms the cache works at
       all, which is what makes the second build's miss attributable to the
       key).

6. Resolve the `RECLAIM_SENTENCE` placeholder now standing in `README.md`, `pipeline/templates/pipeline.toml` and `pipeline/templates/skills/pipeline-config/SKILL.md` by running `grep -c worktree_teardown pipeline/core/worktree.py`: if it prints `0`, replace each placeholder with `The dispatcher removes the worktree at "done"; the keyed directory it was named for is yours to reclaim.`, and if it prints anything else replace each placeholder with `worktree_teardown runs before the dispatcher removes a worktree, and is where to reclaim the keyed directory.`
7. Run `grep -rn RECLAIM_SENTENCE README.md pipeline/templates/pipeline.toml pipeline/templates/skills/pipeline-config/SKILL.md` and confirm it prints nothing, then run `uv run --group dev pytest -q tests/test_stages.py` and confirm no test fails, then commit `README.md`, `pipeline/templates/pipeline.toml` and `pipeline/templates/skills/pipeline-config/SKILL.md` as `docs(TICKET-097): say when a build cache is shareable across worktrees`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path` exits `0`.
- `uv run --group dev pytest -q tests/test_stages.py::test_the_build_cache_docs_carry_the_three_build_shareability_check` exits `0`.
- `uv run --group dev pytest -q tests/test_stages.py` reports no failing test. The baseline measured before this ticket was one failure, the repro test named above, and nothing else.
- `grep -rn RECLAIM_SENTENCE README.md pipeline/templates/pipeline.toml pipeline/templates/skills/pipeline-config/SKILL.md` prints nothing and exits `1`.
- `grep -c "^[^#]" pipeline/templates/pipeline.toml` prints the same number as
  `git show c4cbb38:pipeline/templates/pipeline.toml | grep -c "^[^#]"`, so every
  line this ticket adds to the template is a comment.
- `grep -n "sccache result" README.md` prints one line, the header of the measured build table.

## Decisions

**A build cache is shareable across worktrees only when its key excludes the
checkout path, and the docs state that property rather than a tool.** The
tool-shaped advice ("use sccache") is wrong here, and it was measured wrong:
sccache hashes the rustc command line, cargo puts the target directory in it
(`--out-dir`, `-L dependency=`), and the per-checkout target dirs that exist to
avoid the stale-artifact trap therefore guarantee a cross-ticket miss -- a build
in t1 stores, the same source in t2 misses, t1 with its artifacts wiped hits.
The `CARGO_INCREMENTAL=0` sccache requires also slows repeated builds inside one
ticket, so it loses in both directions. `ccache` escapes only because `base_dir`
normalises the path away. Keep the three-build procedure attached to the claim:
the third build is what makes the second build's miss attributable to the key
rather than to a cache that never worked. A later editor may replace the sccache
example with a better-measured one; do not replace the property with a tool
recommendation.

**The keyed directory outliving its worktree is stated on purpose.** 18 keys,
9.1G, 2 live worktrees is the measurement behind it. Cutting that sentence
leaves the docs recommending unbounded disk growth with no mention of it.

**The three-build procedure is written as a dash list in every document.** A
numbered list inside a plan's step block is scored by the Tier A plan gate as a
plan step, and it failed this ticket's first plan. Renumbering it back to `1.` /
`2.` / `3.` in the docs is harmless once merged, but it re-breaks any plan that
quotes the block.

## Rollback

Revert the two commits from step 2 and step 7. The docs return to the wording
`40e44f9` added, `tests/test_stages.py` loses both guard tests, and no code path
changes -- all four files are prose, data or tests, and the dispatcher reads
none of the added text.

## Thread

### 2026-08-29 03:52:45Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29T00:00:00Z · triage · result=ok

Confirmed. `README.md:350-357`, `pipeline/templates/pipeline.toml:52-55` and
`pipeline/templates/skills/pipeline-config/SKILL.md:172` all tell an agent to
key a build cache per checkout and none use the word "shareable" or state the
excludes-checkout-path property.

Committed `tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path`,
which asserts `"shareable"` appears in all three files. Ran red:

```
AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-097/README.md does not say when a cache is shareable
```

expect: does not say when a cache is shareable

Fix touches all three docs plus a design call on wording the worked example
and three-build procedure -- not a `chore`. `result: ok`.

files_declared: README.md, pipeline/templates/pipeline.toml,
pipeline/templates/skills/pipeline-config/SKILL.md

### 2026-08-29 05:08:57Z · triage · session · session=0f006b23-4164-4021-b080-36525cc82ba6

`triage` ran as session `0f006b23-4164-4021-b080-36525cc82ba6`
- replay: `claude --resume 0f006b23-4164-4021-b080-36525cc82ba6`
- log: `.project/logs/TICKET-097-triage-0f006b23.log`
- cost: $0.31 of a $3 cap
- tokens: 4,104 out (217 thinking) · 40 in · 726,702 cache read · 31,675 cache write

### 2026-08-29 05:08:57Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: README.md, pipeline.toml, and pipeline-config SKILL.md all tell an agent to key a build cache per checkout with no shareability warning; test committed red.

### 2026-08-29 · planning · result=ok

Plan written: 7 steps, 4 files, all text verbatim in the plan.

One finding contradicts the ticket. The ticket asks the three documents to
point at `worktree_teardown`; that key does not exist.
`grep -rn worktree_teardown pipeline` matches nothing, and
`pipeline/core/worktree.py:84` reads `worktree_setup` only. TICKET-091 adds the
key and is at stage `plan-validation`, unmerged. Step 6 decides the wording at
implementation time with `grep -c worktree_teardown pipeline/core/worktree.py`
and picks between two sentences the plan spells out, so this ticket ships no
pointer to a key the code ignores. If TICKET-091 lands first, the docs name it.

Measured baseline: `uv run --group dev pytest -q tests/test_stages.py` prints

```
1 failed, 30 passed in 0.26s
```

and the one failure is this ticket's repro test.

Noted outside this ticket's scope: TICKET-091 declares the same three
documents, so the two tickets will not run at the same time and the second one
to merge rebases onto the first.

### 2026-08-29 05:14:33Z · planning · session · session=5c8bf587-15e7-43cc-a01f-2f60a7c17e0b

`planning` ran as session `5c8bf587-15e7-43cc-a01f-2f60a7c17e0b`
- replay: `claude --resume 5c8bf587-15e7-43cc-a01f-2f60a7c17e0b`
- log: `.project/logs/TICKET-097-planning-5c8bf587.log`
- cost: $1.93 of a $10 cap
- tokens: 27,762 out (11,518 thinking) · 46 in · 1,080,367 cache read · 69,636 cache write

### 2026-08-29 05:14:33Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Planned the shareability warning for README.md, pipeline.toml and the pipeline-config skill: property, sccache table, three-build procedure, plus a second guard test.

### 2026-08-29 05:22:44Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path` fails as required
```
 content-addressed cache (sccache) that looks
        shareable silently misses on every ticket."""
        skill = C.SKILLS_DIR / "pipeline-config" / "SKILL.md"
        readme = Path(__file__).resolve().parent.parent / "README.md"
        for p in (readme, C.CONFIG_TEMPLATE, skill):
            text = p.read_text()
>           assert "shareable" in text, f"{p} does not say when a cache is shareable"
E           AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-097/README.md does not say when a cache is shareable
E           assert 'shareable' in '# Ticket-driven agent pipeline\n\nAgents do not talk to each other. They talk through a ticket file, one stage at\na ...ved from the\nMIT-licensed `superpowers` skills; `NOTICE` carries that attribution and has to\ntravel with the code.\n'

tests/test_stages.py:417: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path` fails on base `main` too -- the bug is not already fixed upstream
```
       assert 'shareable' in '# Ticket-driven agent pipeline\n\nAgents do not talk to each other. They talk through a ticket file, one stage at\na ...ved from the\nMIT-licensed `superpowers` skills; `NOTICE` carries that attribution and has to\ntravel with the code.\n'

tests/test_stages.py:417: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-4kd2j5gn/base
      Built pipeline @ file:///tmp/pipeline-base-4kd2j5gn/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```
- plan step names no declared file: '1. Build in worktree A. Expect a miss.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Build in worktree B, same source and flags. A hit means the cache is shareable across checkouts; a miss means its key carries the checkout path.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: "3. Wipe A's artifacts and rebuild A. A hit confirms the cache works at all, which is what makes step 2's miss attributable to the key." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-29 05:22:44Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- plan step names no declared file: '1. Build in worktree A. Expect a miss.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Build in worktree B, same source and flags. A hit means the cache is shareable across checkouts; a miss means its key carries the checkout path.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: "3. Wipe A's artifacts and rebuild A. A hit confirms the cache works at all, which is what makes step 2's miss attributable to the key." -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-29 · planning · result=ok

Replanned. One change from the plan the gate rejected: the three-build
procedure in step 3's README block is a dash list, not a numbered one.

The gate's three findings were all the same line class:

```
plan step names no declared file: '1. Build in worktree A. Expect a miss.'
```

Those lines were the document text to insert, indented inside step 3, but the
gate scores a line starting `N.` as a plan step. The steps, the files and the
inserted wording are otherwise unchanged; `## Decisions` now records that the
docs keep the dash list.

Re-measured: `uv run --group dev pytest -q tests/test_stages.py` prints

```
1 failed, 30 passed in 0.19s
```

and the one failure is this ticket's repro test. `grep -c "^[^#]"
pipeline/templates/pipeline.toml` prints `4` at `c4cbb38`; the step 4 block is
all comments, so an acceptance criterion compares the two.

`worktree_teardown` still does not exist: `grep -rn worktree_teardown pipeline`
matches nothing. TICKET-091 adds it and is at `plan-validation`, unmerged.

Noted outside this ticket's scope: TICKET-091 declares the same three
documents, so the second of the two to merge rebases onto the first.

### 2026-08-29 05:25:04Z · planning · session · session=4384918e-1a75-4631-8606-7394fe89f091

`planning` ran as session `4384918e-1a75-4631-8606-7394fe89f091`
- replay: `claude --resume 4384918e-1a75-4631-8606-7394fe89f091`
- log: `.project/logs/TICKET-097-planning-4384918e.log`
- cost: $0.97 of a $10 cap
- tokens: 11,438 out (2,630 thinking) · 22 in · 433,377 cache read · 46,769 cache write

### 2026-08-29 05:25:04Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Replanned: the three-build procedure is a dash list, not a numbered one, so the gate stops scoring it as plan steps.

### 2026-08-29 05:25:40Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-29 05:22:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path` fails on base `main` too -- the bug is not already fixed upstream
```
       assert 'shareable' in '# Ticket-driven agent pipeline\n\nAgents do not talk to each other. They talk through a ticket file, one stage at\na ...ved from the\nMIT-licensed `superpowers` skills; `NOTICE` carries that attribution and has to\ntravel with the code.\n'

tests/test_stages.py:417: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-s2bkwbwz/base
      Built pipeline @ file:///tmp/pipeline-base-s2bkwbwz/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 16ms

```

### 2026-08-29 · plan-validation · result=ok

Tier B: pass on all eight items.

- Root cause: the three documents state the rule "key a build cache per
  checkout" without the two facts that make it actionable -- keying costs a
  cold build per ticket plus unbounded disk, and a cache is shareable only
  when its key excludes the checkout path. Steps 3-5 write both facts.
- Decisions: DEC-084 binds and the plan complies. It edits `SKILL.md` in place
  at line 183, adds no second file, and leaves the `description` line alone.
- Scope: every step traces to a criterion. No orphan step.
- Falsifiable: I ran `uv run --group dev pytest -q tests/test_stages.py`. It
  prints `1 failed, 30 passed in 0.19s`, this ticket's repro test. A
  case-insensitive grep for `shareable`, `sccache` and `wipe` prints `0` for
  each of the three documents, so both guard tests fail today.
- No research left: the line numbers hold at `c4cbb38`. README 350 and 358,
  template 56-60, `SKILL.md` 177-183, repro test at 407 with the next `def` at
  420.
- Riskiest step: step 6, the `RECLAIM_SENTENCE` placeholder. The plan spells
  out both branches, and step 7 greps for a survivor.
- Regression surface: four tests read these files, at lines 234, 261, 374 and
  386 of `tests/test_stages.py`. None matches the added text. The 128K size
  guard at line 261 reads the file-ticket skill, not pipeline-config.
- Blast radius: `bugfix`, 4 files, 7 steps. Three files are prose or data.

Criterion 5 holds on both sides: `grep -c "^[^#]"` prints `4` in the worktree
and `4` from `git show c4cbb38:pipeline/templates/pipeline.toml`.

Stale fact, no effect on the plan: the ticket says TICKET-091 sits at
`plan-validation`. Its frontmatter now reads `stage: revalidating`. Step 6
greps this worktree at implementation time, so either state resolves.

### 2026-08-29 05:28:47Z · plan-validation · session · session=1082f04e-22dd-4365-bba5-f8428cd072c2

`plan-validation` ran as session `1082f04e-22dd-4365-bba5-f8428cd072c2`
- replay: `claude --resume 1082f04e-22dd-4365-bba5-f8428cd072c2`
- log: `.project/logs/TICKET-097-plan-validation-1082f04e.log`
- cost: $1.20 of a $3 cap
- tokens: 13,451 out (5,248 thinking) · 38 in · 758,083 cache read · 48,522 cache write

### 2026-08-29 05:28:47Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan passes all eight items: root cause named, DEC-084 complied with, criteria falsifiable, regression surface covered by four existing tests that read the same files.

### 2026-08-29 05:29:58Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: docs-only but red first via tests/test_stages.py, the pattern TICKET-098 exists to document. Step 6 resolves its RECLAIM_SENTENCE placeholder by grepping for worktree_teardown at implementation time, and files_conflict serialises 091 ahead of 097 on README.md, pipeline.toml and SKILL.md, so the grep sees the real answer rather than racing it. Content matches the measurement: sccache hashes the rustc command line, cargo puts the target dir in it, CARGO_INCREMENTAL=0 costs rebuilds, ccache base_dir is the exception. Nothing fenced.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified: docs-only but red first via tests/test_stages.py, the pattern TICKET-098 exists to document. Step 6 resolves its RECLAIM_SENTENCE placeholder by grepping for worktree_teardown at implementation time, and files_conflict serialises 091 ahead of 097 on README.md, pipeline.toml and SKILL.md, so the grep sees the real answer rather than racing it. Content matches the measurement: sccache hashes the rustc command line, cargo puts the target dir in it, CARGO_INCREMENTAL=0 costs rebuilds, ccache base_dir is the exception. Nothing fenced.**

### 2026-08-29 06:06:19Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path` fails as required
```
 content-addressed cache (sccache) that looks
        shareable silently misses on every ticket."""
        skill = C.SKILLS_DIR / "pipeline-config" / "SKILL.md"
        readme = Path(__file__).resolve().parent.parent / "README.md"
        for p in (readme, C.CONFIG_TEMPLATE, skill):
            text = p.read_text()
>           assert "shareable" in text, f"{p} does not say when a cache is shareable"
E           AssertionError: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-097/README.md does not say when a cache is shareable
E           assert 'shareable' in '# Ticket-driven agent pipeline\n\nAgents do not talk to each other. They talk through a ticket file, one stage at\na ...ved from the\nMIT-licensed `superpowers` skills; `NOTICE` carries that attribution and has to\ntravel with the code.\n'

tests/test_stages.py:420: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path` fails on base `main` too -- the bug is not already fixed upstream
```
       assert 'shareable' in '# Ticket-driven agent pipeline\n\nAgents do not talk to each other. They talk through a ticket file, one stage at\na ...ved from the\nMIT-licensed `superpowers` skills; `NOTICE` carries that attribution and has to\ntravel with the code.\n'

tests/test_stages.py:420: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_build_cache_docs_warn_that_a_key_must_exclude_the_checkout_path
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-a32t7afm/base
      Built pipeline @ file:///tmp/pipeline-base-a32t7afm/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 18ms

```

### 2026-08-29 06:06:20Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-29 · implementing · todo

Todo list, one entry per plan step:

1. [ ] Add guard test to `tests/test_stages.py`, run it red, commit.
2. [ ] Verify RED with expected assertion message.
3. [ ] Insert cost/shareability/measurement/procedure text into `README.md`.
4. [ ] Insert comment block into `pipeline/templates/pipeline.toml`.
5. [ ] Insert text into `pipeline/templates/skills/pipeline-config/SKILL.md`.
6. [ ] Resolve `RECLAIM_SENTENCE` by grepping `worktree_teardown` in `pipeline/core/worktree.py`.
7. [ ] Confirm no `RECLAIM_SENTENCE` survives, full suite green, commit docs.

Note: rebasing onto base (TICKET-091 merged) means `worktree_teardown` now
exists in this tree -- `grep -c worktree_teardown pipeline/core/worktree.py`
prints `6`, not `0` as the digest recorded. Step 6 picks the second sentence.
Also, README.md and SKILL.md already carry a `worktree_teardown` section from
that merge, so insertion points are matched by content, not the digest's
stale line numbers (README insertion point unchanged at line 358; SKILL's
paragraph now ends at line 186, not 183).

### 2026-08-29 · implementing · result=ok

Todo, updated:

1. [x] Added guard test, ran red (`AssertionError: ... does not carry
   'excludes the checkout path'`), committed `aa03847`.
2. [x] Verified RED with the expected message.
3. [x] Inserted cost/shareability/measurement/procedure text into
   `README.md`, after line 358.
4. [x] Inserted the same, as `#`-prefixed comments, into
   `pipeline/templates/pipeline.toml`, after line 60.
5. [x] Inserted the same into `SKILL.md`, after its paragraph (now ending
   line 186, not the digest's stale 183 -- content matched, not counted).
6. [x] `grep -c worktree_teardown pipeline/core/worktree.py` printed `6`
   (TICKET-091 merged onto base during the rebase). Resolved
   `RECLAIM_SENTENCE` to the second sentence the plan spells out for that
   branch.
7. [x] `grep -rn RECLAIM_SENTENCE` on the three files: no match, exit `1`.
   `grep -c "^[^#]" pipeline/templates/pipeline.toml` prints `4`, matching
   `git show c4cbb38:...`. `grep -n "sccache result" README.md` prints one
   line. Committed `6570765`.

Found mid-implementation: the plan's verbatim blocks wrap "excludes the /
checkout path" across a line break in all three files. `str.lower()` keeps
newlines, so the guard test from step 1 checks for the literal substring
`"excludes the checkout path"` with a space, and the wrapped text failed it
on first run. This is a word-wrap artifact in the plan's own copy, not a
content or scope change: I reflowed the wrap point in all three files so the
phrase sits on one line, same words, same order, nothing added or removed.
Did not treat this as a plan contradiction requiring `blocked` -- no file
outside `files_declared`, no step skipped, no test weakened.

`uv run --group dev pytest -q tests/test_stages.py` -> `32 passed in 0.18s`.
Both target tests pass individually. Two commits: `aa03847` (red test),
`6570765` (docs).

### 2026-08-29 06:09:43Z · implementing · session · session=55056e33-61d4-445c-9876-af75870a0c44

`implementing` ran as session `55056e33-61d4-445c-9876-af75870a0c44`
- replay: `claude --resume 55056e33-61d4-445c-9876-af75870a0c44`
- log: `.project/logs/TICKET-097-implementing-55056e33.log`
- cost: $0.99 of a $8 cap
- tokens: 17,131 out (4,255 thinking) · 102 in · 2,854,817 cache read · 60,467 cache write

### 2026-08-29 06:09:43Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Added the shareability property, sccache measurement and three-build check to README.md, pipeline.toml and SKILL.md; both guard tests and the full suite (32 passed) are green.

### 2026-08-29 · review · result=ok

Reviewed the delta `main...HEAD`: 97 added lines across `README.md`,
`pipeline/templates/pipeline.toml`,
`pipeline/templates/skills/pipeline-config/SKILL.md` and
`tests/test_stages.py`. The thread holds no earlier review entry, so this pass
covers the whole branch. No blocking findings.

Verified:

1. Every acceptance criterion holds. `grep -c "^[^#]" pipeline/templates/pipeline.toml`
   prints `4`, and `git show c4cbb38:pipeline/templates/pipeline.toml | grep -c "^[^#]"`
   prints `4`. `grep -rn RECLAIM_SENTENCE` on the three files prints nothing and
   exits `1`. `grep -n "sccache result" README.md` prints one line, `373`.
2. `uv run --group dev pytest -q tests/test_stages.py` prints `32 passed in 0.18s`.
   `uv run --group dev pytest -q` prints `471 passed in 33.51s`.
3. The resolved `RECLAIM_SENTENCE` matches the code. `drop_worktree()` runs
   `worktree_teardown` at `pipeline/core/worktree.py:95` and `git worktree remove`
   at line 100, so teardown does run before removal.
4. No fenced path is touched: `pipeline/templates/pipeline.toml` is not
   `.project/pipeline.toml`, the entry in `machine.FENCED`.
5. DEC-084 holds: one `SKILL.md`, no added file, `description` untouched.
6. The template block extends the `worktree_setup` comment and orphans no key;
   the commented `worktree_setup =` line stays above it.

Non-blocking findings:

1. nit: three added lines are 83 characters, past the ~79 the surrounding prose
   wraps at. That is the reflow that puts `excludes the checkout path` on one
   line for the guard test.
2. nit: `README.md` names `worktree_teardown` three lines before the paragraph
   that introduces it. Not a contradiction -- that paragraph reads "Nothing ever
   reclaims what `worktree_setup` created, unless the project also sets
   `worktree_teardown`".

### 2026-08-29 06:12:36Z · review · session · session=1da22c8a-dce3-4b93-acfc-5b889b625d66

`review` ran as session `1da22c8a-dce3-4b93-acfc-5b889b625d66`
- replay: `claude --resume 1da22c8a-dce3-4b93-acfc-5b889b625d66`
- log: `.project/logs/TICKET-097-review-1da22c8a.log`
- cost: $1.13 of a $5 cap
- tokens: 10,292 out (3,240 thinking) · 40 in · 804,534 cache read · 46,776 cache write

### 2026-08-29 06:12:36Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Reviewed the four-file docs delta: both guard tests pass, all six acceptance criteria hold, full suite 471 passed; two non-blocking nits.

### 2026-08-29 06:13:11Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 06:13:12Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/097


Current branch ticket/097 is up to date.
Already up to date.
Updating 159d570..6570765
Fast-forward
 README.md                                          | 34 ++++++++++++++++++++++
 pipeline/templates/pipeline.toml                   | 18 ++++++++++++
 pipeline/templates/skills/pipeline-config/SKILL.md | 20 +++++++++++++
 tests/test_stages.py                               | 25 ++++++++++++++++
 4 files changed, 97 insertions(+)

```

### 2026-08-29 06:13:12Z · merging · decision

decision recorded as `DEC-097`
