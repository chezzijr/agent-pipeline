---
id: TICKET-046
stage: done
class: refactor
branch: ticket/046
test_file: tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block
files_declared:
- CLAUDE.md
- pipeline/core/gate.py
- tests/test_gate.py
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
  stage: review
  id: c96fb44d-52d2-43b6-bf2a-e9c2f166cdc6
  log: .project/logs/TICKET-046-review-c96fb44d.log
approved_by: chezzijr
approved_at: '2026-08-24T09:03:46.299238+00:00'
---

## Summary
review passed the branch. No blocking findings, no drift from `## Plan`.

implementing executed all 14 plan steps in four commits. `pipeline/core/gate.py`
gained `_entry_ref()`, `_ref()`, `_blocks()` and `_dedupe()`, built on
`_fenced()` and `FENCE_RE` per DEC-016. `gate()` dedupes findings against the
ticket's own thread before appending, and dedupes the failures it returns
against the entry it just wrote. The first copy of a given output stays
verbatim; every later identical copy becomes one line naming the `## Thread`
entry that carries it. Nothing is truncated or summarised. `tests/test_gate.py`
gained four tests, `CLAUDE.md` one gotcha bullet.

review re-ran the suite: `257 passed in 10.49s`. The six tests named in
`## Acceptance criteria` report `6 passed`. Every criterion holds except the
literal count `249 passed`, which is `257 passed` -- a stale digest number, not
a defect. review did not run `./pipeline/hooks/test_dangerous_commands.py`; the
guard blocks it for a read-only stage and the delta touches no hook file.

review recorded three non-blocking findings, all in its `## Thread` note: an
adjacent-fence merge in `_blocks()` that `gate()` cannot reach, an `IndexError`
at `pipeline/core/gate.py:360` if `## Thread` opens with an unclosed fence, and
a dropped trailing newline in `_dedupe()` that changes nothing today.

## Reproduction

test: `tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block`
command: `uv run --group dev pytest -q tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block`

The test runs `gate()` twice on the same unchanged ticket and asserts every
fenced block in `## Thread` is unique. It fails with:

```
AssertionError: expected every fenced block to be unique, got 2 blocks, 1 unique
assert 2 == 1
 +  where 2 = len(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])
 +  and   1 = len({'```\ntest_broken\n\n```'})
```

expect: expected every fenced block to be unique, got 2 blocks, 1 unique

## Digest

Files touched: `pipeline/core/gate.py` (the fix), `tests/test_gate.py` (three new tests), `CLAUDE.md` (one gotcha bullet).
Key functions: `gate()` builds `findings: list[str]`, then `t.append("plan-validation", "gate", ...)` writes one entry per run and `t.save()` persists it. Six call sites inside `gate()` embed `out[-1200:]` in a fence; `_base_findings()` embeds four more.
Entry points: `pipeline/cli/main.py:83` (`pipeline gate`) and `pipeline/daemon/supervisor.py:629` / `:757` (plan-validation, and `finish_regate()`). Both take `(ok, failures)`; the supervisor copies `failures` into `advance()`'s own thread note, so a fenced failure lands in the thread twice per run.
Fence parsing: `_fenced(lines)` in `pipeline/core/ticket.py:110` marks every line inside a fence, delimiters included, with CommonMark's closing rule. `gate.py` already imports it; `FENCE_RE` sits beside it and is not imported yet.
Measured: one gate run on `_git_ticket_project("buggy", "buggy")` writes 2 fenced blocks, 1 unique -- the branch run and the base run produce the same tail, so duplication starts inside a single run, not only across runs. Two runs on `helpers.project()` write 2 blocks, 1 unique (the reproduction test).
Gate divergence, measured: the dispatcher runs the installed copy at `/home/chezzijr/.local/share/uv/tools/pipeline/lib/python3.13/site-packages/pipeline/core/gate.py`, whose criteria scan is `re.search(r"\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/", line, re.I)` -- it has no `\bpytest\b` arm. That is why the gate rejected the criterion whose only test token was `pytest`. `main` carries the `\bpytest\b` arm; this branch and the installed copy do not. Every criterion in this plan now names a `tests/` path.
Base divergence: `main` is 10 commits ahead of this branch. `pipeline/core/gate.py` on `main` carries `CRIT_ITEM_RE` at line 43 and the criteria scan at line 280; this branch's copy has neither. The new helpers go above `_base_findings()` (line 48) and the wiring above `failed = [...]` (line 285), so neither edit overlaps `main`'s two.
Gotchas: `t.thread()` must be read for the seed *before* `t.append()`, and read again after it to name the entry just written (`t.thread()[-1].raw`). `failed` is computed with `startswith("ok:")`, so a rewrite must never touch a finding's first line. `metrics.gate_failure_reasons()` groups by the whole finding string; findings already embed distinct output, so grouping does not get worse.

## Decisions checked

DEC-016 -- fence state is parsed once, in `_fenced()`, and every scan over a ticket body consults it; a toggle scan on three backticks misses `~~~` and closes early on captured output. This plan complies: `_blocks()` is built on `_fenced()` and `FENCE_RE`, not on a local scan.
DEC-023 -- `stage_view()` trims only `## Thread`, and every omission is announced with a count and the ticket path. A reference may point at an entry the view omitted; the view already tells the reader to grep the file for `^### `, so the pointer stays resolvable. No change to `stage_view()`.
DEC-018 -- the gate resolves every cited `DEC-<n>`; unaffected, no citation code changes.
DEC-042 -- a wrapped acceptance criterion is checked on its first line only, and `CRIT_ITEM_RE` decides what a criterion line is. This plan complies: every criterion is one unwrapped line naming a `tests/` path. It also records that the criteria scan does not consult `_fenced()`; this plan changes no scan in `## Acceptance criteria`.
DEC-043 -- `machine.FENCED` fences itself and eight symbols; `pipeline/core/gate.py` is not one of them, so this change merges unattended. `CLAUDE.md` is not fenced either, but `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` reads the fenced-list paragraph, which step 13 does not touch.
Grep terms used against `.project/decisions/`: thread, fence, 1200, verbatim, `out[-`, stage_view, VIEW_, dedup, evidence, gate.

## Plan

1. Add three helpers to `pipeline/core/gate.py` above `_base_findings()`: `_entry_ref(raw)` returns the string ``the `## Thread` entry `<raw>` ``; `_ref(where)` returns `*-- identical output, already quoted in <where> --*`; `_blocks(text)` returns `list[tuple[int, int, str]]` of `(first line index, one past the last, inner text)` for every fenced block, built by walking runs of `True` in `_fenced(text.splitlines())`, dropping the opener and -- when `FENCE_RE.match()` matches the run's last line -- the closer; import `FENCE_RE` from `pipeline.core.ticket` alongside `_fenced`.
2. Add `_dedupe(text, seen, where)` to `pipeline/core/gate.py`: it walks `_blocks(text)`, keeps a block whose inner text has no non-whitespace character, replaces a block whose inner text is already a key of `seen` with the single line `_ref(seen[body])`, and otherwise keeps the block and records `seen[body] = where`; it returns the rewritten text and mutates `seen` in place.
3. Add `test_dedupe_replaces_a_repeated_fence_and_keeps_the_first` to `tests/test_gate.py`: call `_dedupe` twice with one shared `seen` dict on two different prose lines carrying the same fenced body `boom`, assert the first result still contains the fenced `boom`, assert the second contains no fence and does contain `this entry, above`, and assert `_dedupe` on a `~~~`-delimited `boom` with a fresh dict leaves that dict equal to `{"boom": "x"}` (DEC-016: a `~~~` block is a fence).
4. Run `uv run --group dev pytest -q tests/test_gate.py -k dedupe` in the worktree, expect `1 passed`, then commit `pipeline/core/gate.py` and `tests/test_gate.py` as `fix(TICKET-046): a gate fence scanner that can spot a repeated block`.
5. Add `test_one_gate_run_quotes_the_branch_and_base_output_once` to `tests/test_gate.py`: build `d, wt = _git_ticket_project("buggy\n", "buggy\n")`, call `gate(d, "TICKET-001", workdir=wt)`, assert it passed, read the `Thread` section through `T.sections()`, assert it holds exactly 1 fenced block by the same `re.findall` the reproduction test uses, assert `identical output, already quoted in this entry, above` appears in it, then `shutil.rmtree(d, ignore_errors=True)`.
6. Run `uv run --group dev pytest -q tests/test_gate.py -k "regate_of_an_unchanged or branch_and_base_output_once"` and expect both to fail -- the new one on `1 != 2`, the reproduction one with `expected every fenced block to be unique, got 2 blocks, 1 unique`; this is the failing state that step 7 fixes in `pipeline/core/gate.py`.
7. Wire the dedupe into `gate()` in `pipeline/core/gate.py`, immediately above the `failed = [f for f in findings ...]` line at line 285: build `seen: dict[str, str] = {}`, then `for e in t.thread(): for _, _, body in _blocks(e.text): if body.strip(): seen.setdefault(body, _entry_ref(e.raw))` so the earliest entry that carries a body wins, then rebind `findings = [_dedupe(f, seen, "this entry, above") for f in findings]`, leaving the `failed`, `verdict`, `t.append(...)` and `t.save()` lines unchanged.
8. Run `uv run --group dev pytest -q tests/test_gate.py`, expect `28 passed` (26 today plus the tests from steps 3 and 5), then commit `pipeline/core/gate.py` and `tests/test_gate.py` as `fix(TICKET-046): the gate references a fence the thread already carries`.
9. Add `test_a_failed_gate_returns_a_reference_not_a_second_copy_of_the_output` to `tests/test_gate.py`: build `d = project()`, overwrite `d / ".project/pipeline.toml"` with `test_one = "echo nope; exit 1"` plus `test_suite = "true"` and `test_suite_without_new = "true"`, call `ok, failures = gate(d, "TICKET-001")`, assert `not ok`, assert one failure contains `never appears`, assert no failure contains a fence, assert one failure names a `## Thread` entry, and assert the `Thread` section contains `nope` exactly once.
10. Run `uv run --group dev pytest -q tests/test_gate.py -k returns_a_reference` and expect it to fail on the assertion that no failure carries a fence -- before step 11 `gate()` returns the fence verbatim; this is the failing state step 11 fixes in `pipeline/core/gate.py`.
11. Rewrite the return of `gate()` in `pipeline/core/gate.py`: after `t.save()`, set `here = _entry_ref(t.thread()[-1].raw)`, build `mine = {body: here for f in findings for _, _, body in _blocks(f) if body.strip()}`, and `return not failed, [_dedupe(f, mine, here) for f in failed]`; the fences left in `failed` were just written into that entry, and `supervisor.advance()` copies the returned findings into a note of its own.
12. Run `uv run --group dev pytest -q tests/test_gate.py tests/test_dispatch.py tests/test_cli.py`, expect `73 passed` (70 today plus the tests from steps 3, 5 and 9), then commit `pipeline/core/gate.py` and `tests/test_gate.py` as `fix(TICKET-046): a failed gate returns a reference to its own entry`.
13. Add one bullet to the `## Gotchas, each found the hard way` list in `CLAUDE.md`, after the `A stage reads a bounded view` bullet, saying: `gate()` quotes each distinct output once and references the rest; a re-gate re-runs the same test against the same code, so its fence is byte-identical to one the thread already holds, and `_dedupe()` replaces the copy with a pointer to the entry that carries it; never fix thread growth by truncating or summarising the fence, because `pipeline/stages/_common.md` rule 7 requires verbatim output.
14. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`, expect `249 passed` (246 today plus the three new tests) and `79 passed`, then commit `CLAUDE.md` as `docs(TICKET-046): the gate references a repeated fence rather than re-quoting it`.

## Acceptance criteria

- `tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block` passes: two `gate()` runs on one unchanged ticket leave every fenced block in `## Thread` unique.
- `tests/test_gate.py::test_one_gate_run_quotes_the_branch_and_base_output_once` passes: one `gate()` run on `_git_ticket_project("buggy\n", "buggy\n")` leaves exactly 1 fenced block, down from the 2 measured today.
- `tests/test_gate.py::test_dedupe_replaces_a_repeated_fence_and_keeps_the_first` passes: the first copy stays verbatim, the second becomes a reference, and a `~~~` block counts as a fence.
- `tests/test_gate.py::test_a_failed_gate_returns_a_reference_not_a_second_copy_of_the_output` passes: no returned failure carries a fence, and `nope` appears once in `## Thread`.
- `tests/test_gate.py::test_gate_passes_a_test_that_fails_on_base_too` still passes: the prose `fails on base` survives, so only the fence is replaced.
- `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` passes after the `CLAUDE.md` edit.
- `uv run --group dev pytest -q` reports `249 passed`: every test under `tests/` passes, including `tests/test_dispatch.py` and `tests/test_cli.py`.

## Decisions

**The evidence is quoted once and referenced afterwards; it is never truncated or summarised.** `pipeline/stages/_common.md` rule 7 requires verbatim output, and a summary of an error is not evidence. `_dedupe()` in `pipeline/core/gate.py` keeps the first copy of a given output byte-for-byte and replaces every later identical copy with a one-line reference to the entry that carries it. Do not shrink `out[-1200:]` to make a thread smaller.

**Fence identity is an exact match of the block's inner text.** Not the check's name, not the verdict: two runs of the same test on the same code produce the same bytes, and anything looser would collapse two different failures into one reference and lose evidence.

**`_blocks()` is built on `_fenced()` and `FENCE_RE`, per DEC-016.** A local scan for three backticks misses `~~~` and closes early on captured output that carries a fence of its own. A fourth scan over ticket bytes consults `_fenced()` too.

**A blank fence keeps its fence.** The reference line is longer than an empty block, so replacing one saves nothing and adds noise.

**`gate()` returns findings whose fences point at the entry it just wrote.** `supervisor.advance()` copies the returned failures into a thread note of its own, so returning the fence puts the same output in the thread twice in one tick. The cost is that `pipeline gate` prints the reference rather than the output; the entry it names is in the ticket the human is about to open. Accepted deliberately.

**The seed reads `t.thread()` before `t.append()`, and `t.thread()[-1].raw` after it.** Reversed, the run's own fences dedupe against themselves and no fence is ever written.

## Rollback

Revert the commits from steps 7 and 11 in `pipeline/core/gate.py`, newest first. The helpers from steps 1 and 2 are inert without those two call sites, so reverting the two wirings alone restores the old behaviour: every gate run re-quotes its output and the thread grows again. The four new tests in `tests/test_gate.py` fail after such a revert and must be reverted with them; `tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block` returns to the failing state recorded in `## Reproduction`. No data migration: tickets already carrying duplicate fences keep them.

## Thread

### 2026-08-24 08:05:50Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-24 08:14:35Z · triage · note

`triage` was interrupted; lease released

### 2026-08-24 · triage · note

Reproduced. Added
`tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block`,
committed at dd38215 on `ticket/046`. It runs `gate()` twice on an unchanged
ticket and asserts every fenced block in `## Thread` is unique.

Fails as expected:
```
AssertionError: expected every fenced block to be unique, got 2 blocks, 1 unique
```

This is `result: ok`, not `chore`. The fix touches `pipeline/core/gate.py`,
which embeds `out[-1200:]` at six call sites plus the `_base_findings()`
copies, and needs a design choice: what identifies "the same fence" across
runs (exact string match vs. same check + same verdict), and how a
duplicate should reference the earlier entry (timestamp? thread-entry id?).
That choice is planning's job, not mine.

### 2026-08-24 08:32:04Z · triage · session · session=c347c1bb-822a-4a63-8c7a-3bc011f90c21

`triage` ran as session `c347c1bb-822a-4a63-8c7a-3bc011f90c21`
- replay: `claude --resume c347c1bb-822a-4a63-8c7a-3bc011f90c21`
- log: `.project/logs/TICKET-046-triage-c347c1bb.log`

### 2026-08-24 08:32:04Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced gate's duplicate-fence bug with a failing test; committed dd38215 on ticket/046

### 2026-08-24 08:41:17Z · planning · note

Plan written. `gate()` will dedupe fenced blocks against the thread it is
about to append to, and the evidence stays verbatim.

The design choice triage left open, settled here:
1. "The same fence" is a byte-identical inner text of the block. A looser key
   (check name, verdict) would collapse two different failures into one
   reference and lose evidence.
2. A duplicate names the entry that carries the original, by that entry's
   `### ` header line. Within one run it says "this entry, above".

Measured while planning: one gate run on `_git_ticket_project("buggy", "buggy")`
already writes 2 fenced blocks, 1 unique -- the branch run and the base run.
The duplication starts inside a single run, not only across re-gates, so the
fix dedupes within the run as well as against the thread.

Out of scope, noted rather than fixed: `pipeline/cli/metrics.py`
`gate_failure_reasons()` groups by the whole finding string, which embeds test
output, so it rarely groups two runs together.

Scope: one subsystem, `pipeline/core/gate.py`. No questions for the human.

### 2026-08-24 08:42:00Z · planning · session · session=916d4b44-a272-4822-b11a-191c40e2930b

`planning` ran as session `916d4b44-a272-4822-b11a-191c40e2930b`
- replay: `claude --resume 916d4b44-a272-4822-b11a-191c40e2930b`
- log: `.project/logs/TICKET-046-planning-916d4b44.log`

### 2026-08-24 08:42:00Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned the gate fence dedupe: quote each distinct output once, reference every later copy

### 2026-08-24 08:45:30Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block` fails as required
```
  d = project()
        ok1, _ = gate(d, "TICKET-001")
        assert ok1
        ok2, _ = gate(d, "TICKET-001")
        assert ok2
        thread = T.sections((d / ".project/tickets/TICKET-001.md").read_text())["Thread"]
        fences = re.findall(r"```\n.*?\n```", thread, re.S)
>       assert len(fences) == len(set(fences)), \
            f"expected every fenced block to be unique, got {len(fences)} blocks, " \
            f"{len(set(fences))} unique"
E       AssertionError: expected every fenced block to be unique, got 2 blocks, 1 unique
E       assert 2 == 1
E        +  where 2 = len(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])
E        +  and   1 = len({'```\ntest_broken\n\n```'})
E        +    where {'```\ntest_broken\n\n```'} = set(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])

tests/test_gate.py:403: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block` fails on base `main` too -- the bug is not already fixed upstream
```
ique
E       assert 2 == 1
E        +  where 2 = len(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])
E        +  and   1 = len({'```\ntest_broken\n\n```'})
E        +    where {'```\ntest_broken\n\n```'} = set(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])

tests/test_gate.py:403: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-01cms85t/base
      Built pipeline @ file:///tmp/pipeline-base-01cms85t/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- acceptance criterion names no test: - `uv run --group dev pytest -q` is green.

### 2026-08-24 08:45:30Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion names no test: - `uv run --group dev pytest -q` is green.

### 2026-08-24 08:49:14Z · planning · note

Re-planned after the Tier A fail. The design is unchanged; the plan is not.

The gate failed one line only:

    - acceptance criterion names no test: - `uv run --group dev pytest -q` is green.

Cause, measured: the dispatcher runs the installed copy at
`/home/chezzijr/.local/share/uv/tools/pipeline/lib/python3.13/site-packages/pipeline/core/gate.py`,
whose criteria scan is
`re.search(r"\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/", line, re.I)`
-- it has no `\bpytest\b` arm. `main` carries that arm (TICKET-041); this
branch and the installed copy do not. The criterion now names `tests/`.

Four other changes, all precision:
1. steps 8, 12 and 14 carry measured counts. 26, 70 and 246 tests collect
   today, so those steps expect 28, 73 and 249.
2. steps 7 and 11 spell out the loop over `_blocks()` rather than naming a
   `body` variable no step binds.
3. `## Decisions checked` adds DEC-042 (a wrapped criterion is checked on its
   first line only) and DEC-043 (`pipeline/core/gate.py` is not fenced).
4. `## Digest` records that `main` is 10 commits ahead and that
   `pipeline/core/gate.py` there carries `CRIT_ITEM_RE`, which this branch
   lacks.

Out of scope, noted rather than fixed: the installed `pipeline` tool is older
than `main`. Re-installing it is the operator decision, not this ticket.

### 2026-08-24 08:50:38Z · planning · session · session=bfb8c635-c0b7-4177-923d-5bd5afb30482

`planning` ran as session `bfb8c635-c0b7-4177-923d-5bd5afb30482`
- replay: `claude --resume bfb8c635-c0b7-4177-923d-5bd5afb30482`
- log: `.project/logs/TICKET-046-planning-bfb8c635.log`

### 2026-08-24 08:50:38Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-planned TICKET-046: every acceptance criterion now names a tests/ path, and the step counts are measured

### 2026-08-24 08:59:03Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block` fails as required
```
  d = project()
        ok1, _ = gate(d, "TICKET-001")
        assert ok1
        ok2, _ = gate(d, "TICKET-001")
        assert ok2
        thread = T.sections((d / ".project/tickets/TICKET-001.md").read_text())["Thread"]
        fences = re.findall(r"```\n.*?\n```", thread, re.S)
>       assert len(fences) == len(set(fences)), \
            f"expected every fenced block to be unique, got {len(fences)} blocks, " \
            f"{len(set(fences))} unique"
E       AssertionError: expected every fenced block to be unique, got 2 blocks, 1 unique
E       assert 2 == 1
E        +  where 2 = len(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])
E        +  and   1 = len({'```\ntest_broken\n\n```'})
E        +    where {'```\ntest_broken\n\n```'} = set(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])

tests/test_gate.py:403: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block` fails on base `main` too -- the bug is not already fixed upstream
```
ique
E       assert 2 == 1
E        +  where 2 = len(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])
E        +  and   1 = len({'```\ntest_broken\n\n```'})
E        +    where {'```\ntest_broken\n\n```'} = set(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])

tests/test_gate.py:403: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-f162vxh7/base
      Built pipeline @ file:///tmp/pipeline-base-f162vxh7/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 09:02:02Z · plan-validation · note

**plan-validation review: PASS, 8 of 8 items.**

1. Root cause: `gate()` interpolates `out[-1200:]` into a fence at six sites and
   `_base_findings()` at four, and nothing compares a block against what the
   thread already carries. The plan fixes that, not the assertion.
2. Decisions: DEC-016 constrains the scan; `_fenced()` (`ticket.py:110`) and
   `FENCE_RE` (`:107`) exist and step 1 imports both. DEC-043 verified:
   `machine.FENCED` names neither `pipeline/core/gate.py` nor `CLAUDE.md`.
3. Scope: every step names a file in `files_declared`; class is `refactor`, 3
   files.
4. Criteria: falsifiable. Steps 6 and 10 record the failing state each fix
   clears.
5. No research left: anchors verified -- `_base_findings()` line 48,
   `failed = [f for f in findings ...]` line 285, `ThreadEntry.text` and `.raw`
   lines 478-479, and `advance()` copying `failures` at
   `pipeline/daemon/supervisor.py:635`.
6. Riskiest step: 11, which drops the output from what `pipeline gate` prints.
   `## Rollback` names steps 7 and 11 and calls the helpers inert without them.
7. Regression surface: step 12 runs `tests/test_dispatch.py` and
   `tests/test_cli.py`; `tests/test_gate.py:221` asserts `fails on base`
   survives.
8. Counts: 26, 35 and 9 `^def test_` in the three files (70), and 244 under
   `tests/` plus the 2 collected in `pipeline/hooks/test_dangerous_commands.py`
   (246). The plan matches.

Digest error, not plan-blocking: this branch carries the `\bpytest\b` arm at
`pipeline/core/gate.py:281`; only the installed copy (line 275) lacks it.

Implementation caution for `_blocks()`: `_fenced()` marks a closing delimiter
`True`, so two fences with no line between them read as one run.

### 2026-08-24 09:02:51Z · plan-validation · session · session=31ac4c23-8434-4c33-9de6-b628698c7cde

`plan-validation` ran as session `31ac4c23-8434-4c33-9de6-b628698c7cde`
- replay: `claude --resume 31ac4c23-8434-4c33-9de6-b628698c7cde`
- log: `.project/logs/TICKET-046-plan-validation-31ac4c23.log`

### 2026-08-24 09:02:51Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight judgment items; digest's claim that this branch lacks the pytest arm is wrong, gate.py:281 has it

### 2026-08-24 09:03:46Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 09:07:44Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block` fails as required
```
  d = project()
        ok1, _ = gate(d, "TICKET-001")
        assert ok1
        ok2, _ = gate(d, "TICKET-001")
        assert ok2
        thread = T.sections((d / ".project/tickets/TICKET-001.md").read_text())["Thread"]
        fences = re.findall(r"```\n.*?\n```", thread, re.S)
>       assert len(fences) == len(set(fences)), \
            f"expected every fenced block to be unique, got {len(fences)} blocks, " \
            f"{len(set(fences))} unique"
E       AssertionError: expected every fenced block to be unique, got 2 blocks, 1 unique
E       assert 2 == 1
E        +  where 2 = len(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])
E        +  and   1 = len({'```\ntest_broken\n\n```'})
E        +    where {'```\ntest_broken\n\n```'} = set(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])

tests/test_gate.py:430: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block` fails on base `main` too -- the bug is not already fixed upstream
```
ique
E       assert 2 == 1
E        +  where 2 = len(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])
E        +  and   1 = len({'```\ntest_broken\n\n```'})
E        +    where {'```\ntest_broken\n\n```'} = set(['```\ntest_broken\n\n```', '```\ntest_broken\n\n```'])

tests/test_gate.py:430: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-e6e886k0/base
      Built pipeline @ file:///tmp/pipeline-base-e6e886k0/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 09:07:44Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 09:10:00Z · implementing · note

**implementing: todo list**

1. [x] Add `_entry_ref`, `_ref`, `_blocks` to `pipeline/core/gate.py`, import `FENCE_RE`.
2. [x] Add `_dedupe(text, seen, where)` to `pipeline/core/gate.py`.
3. [x] RED (then GREEN, already implemented): `test_dedupe_replaces_a_repeated_fence_and_keeps_the_first`.
4. [x] Ran `-k dedupe`, 1 passed; committed steps 1-4 (`233021e`).
5. [x] Wrote `test_one_gate_run_quotes_the_branch_and_base_output_once`.
6. [x] Confirmed step 5 and the reproduction test both fail as expected.
7. [x] Wired dedupe into `gate()` before `failed = [...]`.
8. [x] Ran `tests/test_gate.py`, 30 passed (digest's `28` was stale, see `## Summary`); committed steps 5-8 (`c11d5ae`).
9. [x] Wrote `test_a_failed_gate_returns_a_reference_not_a_second_copy_of_the_output`.
10. [x] Confirmed it fails on the no-fence assertion.
11. [x] Rewrote `gate()`'s return to dedupe `failed` against its own entry.
12. [x] Ran `test_gate.py test_dispatch.py test_cli.py`, 78 passed (digest's `73` was stale); committed steps 9-12 (`5fcbc6e`).
13. [x] Added `CLAUDE.md` gotcha bullet.
14. [x] Ran full suite (`257 passed`, digest's `249` was stale) and guard script (all passed); committed step 13-14 (`d941269`).

### 2026-08-24 09:20:00Z · implementing · note

**implementing: done**

All 14 plan steps executed, 4 commits (`233021e`, `c11d5ae`, `5fcbc6e`, `d941269`).
The ticket's own failing test,
`tests/test_gate.py::test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block`,
passes. Every test named in `## Acceptance criteria` passes individually and
in the full suite (`257 passed`); the guard script passes all cases.

The plan's step 1-2 order writes the helpers before their test in step 3 --
followed as approved, since `_dedupe` needs `_blocks` to exist to be
exercised at all. Steps 5-6, 9-10 kept RED-then-GREEN: each new test was
confirmed failing for the stated reason before its wiring step made it pass.

### 2026-08-24 09:11:32Z · implementing · session · session=5e47ac8f-a1bd-42ed-9c5c-fe01a05364d2

`implementing` ran as session `5e47ac8f-a1bd-42ed-9c5c-fe01a05364d2`
- replay: `claude --resume 5e47ac8f-a1bd-42ed-9c5c-fe01a05364d2`
- log: `.project/logs/TICKET-046-implementing-5e47ac8f.log`

### 2026-08-24 09:11:32Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ executed all 14 plan steps in pipeline/core/gate.py; gate() now dedupes repeated fences, 4 commits, 257 tests pass

### 2026-08-24 09:35:00Z · review · note

**review: PASS -- no blocking findings**

Reviewed the whole branch delta (`main...HEAD`, 5 commits, 3 files,
+146/-3); no earlier `review` entry exists. `uv run --group dev pytest -q`
reports `257 passed in 10.49s`. The six tests named in
`## Acceptance criteria` report `6 passed`. Every criterion holds except the
literal count `249 passed`, which is `257 passed` -- a stale digest number
`## Summary` already records.

Non-blocking findings:

1. minor -- `_blocks()` merges two fenced blocks that abut with no line
   between them. Measured: `_blocks("p\n```\nA\n```\n```\nB\n```\n")` returns
   `[(1, 7, 'A\n```\n```\nB')]`. Unreachable from `gate()`: every finding
   opens with prose and `t.append()` joins them as `- ` bullets, so two
   fences never abut. The effect if reached is a dedupe miss, not lost
   evidence.
2. minor -- `pipeline/core/gate.py:360` reads `t.thread()[-1].raw`. It raises
   `IndexError` if `## Thread` opens with an unclosed fence, because
   `thread()` then sees no `### ` header. New path: `gate()` did not call
   `t.thread()` before this change.
3. nit -- `_dedupe()` drops a trailing newline (`splitlines()` then
   `"\n".join`). No finding ends with one and `Ticket.append()` strips, so it
   changes nothing today.

Refuted and dropped:

- "dedupe can flip a verdict": `_ref()` returns `*-- identical output ...`,
  never `ok:`, and `failed` is computed after the rebind
  (`pipeline/core/gate.py:352-354`).
- "`t.thread()[-1]` may not be the entry just written":
  `pipeline/core/ticket.py:161-171` appends at the end of the `## Thread`
  section.
- "`metrics.gate_failure_reasons()` grouping gets worse":
  `pipeline/cli/metrics.py:310` groups by the whole finding string, and the
  reference carries the entry timestamp, so each run stays as distinct as the
  output tail made it before.

I did not run `./pipeline/hooks/test_dangerous_commands.py`: the guard blocked
it -- "`test_dangerous_commands.py` is not on the read-only allowlist". The
delta touches no hook file.

### 2026-08-24 09:16:46Z · review · session · session=c96fb44d-52d2-43b6-bf2a-e9c2f166cdc6

`review` ran as session `c96fb44d-52d2-43b6-bf2a-e9c2f166cdc6`
- replay: `claude --resume c96fb44d-52d2-43b6-bf2a-e9c2f166cdc6`
- log: `.project/logs/TICKET-046-review-c96fb44d.log`

### 2026-08-24 09:16:46Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed the 5-commit delta; 257 passed, all 6 acceptance tests pass, 3 non-blocking findings

### 2026-08-24 09:17:04Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 09:17:05Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/046


Merge made by the 'ort' strategy.
 .project/decisions/DEC-048.md  |  44 +++
 .project/tickets/TICKET-048.md | 615 +++++++++++++++++++++++++++++++++++++++++
 pipeline/cli/main.py           |   4 +-
 pipeline/core/machine.py       |  20 +-
 pipeline/daemon/server.py      |  22 +-
 pipeline/daemon/supervisor.py  |  32 ++-
 tests/test_daemon.py           | 140 +++++++++-
 tests/test_machine.py          |  13 +
 8 files changed, 876 insertions(+), 14 deletions(-)
 create mode 100644 .project/decisions/DEC-048.md
 create mode 100644 .project/tickets/TICKET-048.md
Updating a4ce031..b7e65ee
Fast-forward
 CLAUDE.md             |  6 +++++
 pipeline/core/gate.py | 68 ++++++++++++++++++++++++++++++++++++++++++++--
 tests/test_gate.py    | 75 ++++++++++++++++++++++++++++++++++++++++++++++++++-
 3 files changed, 146 insertions(+), 3 deletions(-)

```

### 2026-08-24 09:17:05Z · merging · decision

decision recorded as `DEC-046`
