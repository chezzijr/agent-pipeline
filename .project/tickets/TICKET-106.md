---
id: TICKET-106
stage: done
class: bugfix
branch: ticket/106
test_file: pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
files_declared:
- CLAUDE.md
- pipeline/hooks/dangerous-commands.py
- pipeline/hooks/test_dangerous_commands.py
counters:
  plan_validation_attempts: 1
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 7
  plan_files: 3
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: e91b705b-44d6-427b-9860-8af3ebc1b763
  log: .project/logs/TICKET-106-review-e91b705b.log
  cost_usd: 1.9522000000000002
approved_by: 'chezzijr (via Claude Code, while away; reviewed the fenced guard diff
  and ran the branch''s guard over the full table). Verified against the branch, not
  by reading: ALLOW awk ''NR>=40 && NR<=70'', jq ''.a>1'', grep -c x f 2>&1, sed -n
  40,70p, sed -n $p; BLOCK echo hi>out.txt, cat a>>b, sed -n ''40,70p;s/a/b/w out.txt'',
  sed -n ''40,70p;w out.txt'', sed -i, wc -l >(tee out.txt), echo x >& out.txt, and
  git worktree remove foo -- the invariant-4 condition still holds. Two improvements
  over the plan: REDIRECT_CHARS includes ( and ) so process substitution >(tee out.txt)
  is caught, and a >& token clears only when the next token is all digits, so 2>&1
  passes while >& out.txt is blocked. SED_PRINT carries no anchors and says why in
  its comment -- the only call site is fullmatch -- so the start-only leak cannot
  return through a regex edit. Re-run the live spawn check when convenient; my check
  was the hook invoked directly, not through a real Claude Code session.'
approved_at: '2026-08-30T15:36:28.459650+00:00'
---

## Summary

Implemented in six commits on `ticket/106` (`12a61e2`, `123e7a3`, `59ce69a`,
`f59c700`, `dde3136`, `030d8dd`). The first four were rejected by review on
one blocking finding; the last two fix it.

The finding: process substitution wrote files in a read-only stage.
`redirection()` required `set(tok) <= REDIRECT_CHARS`, and shlex lexes `>(`
as one token, so the `(` disqualified it. `wc -l >(tee out.txt)` returned
`None` on the pre-fix branch and `shell redirection into a file` on `main`;
`wc` is in `READ_TOOLS`, so no later rule fired. Fix: `(` and `)` are now in
`REDIRECT_CHARS` at `pipeline/hooks/dangerous-commands.py:44`, and
`wc -l >(tee out.txt)` is a `BLOCKED_READONLY` row.

Review passed the fix on 2026-08-30 with no blocking findings. It re-measured
every acceptance criterion after the fix: `519 passed in 36.61s`, `guard: all
passed`, the count test green on `138`, `grep -c 'SED_PRINT.match'` -> `0`,
the `claude-code.toml` diff empty, and the invariant-4 check exits `2` with
`Blocked by the pipeline guard (review): worktrees are the dispatcher's to
manage.` Across 33 shapes only three verdicts differ from `main`, and all
three are acceptance criteria: `grep 'a > b' file.txt`, `awk 'NR>=40' f.rs`,
`sed -n 40,70p f.rs`. Descriptor duplication still passes (`ls 2>&1`,
`ls >&2`, `ls 1>&2`, `ls >& 2`).

Three pre-existing holes stay out of scope: `always_rules()` never inspects a
`>(...)` inner command; `<(cmd)` runs its inner command uninspected in every
stage (`cat <(rm -rf /tmp/x)` -> `None` on `main` too); and
`uv run <anything>` passes the read-only allowlist. One stale line: the
`## Decisions` section still says the redirection token's characters are all
in `<>&|`, while the code is `set("<>&|()")`.

The next gate is human: `pipeline/hooks/dangerous-commands.py` is in
`machine.FENCED`, so the ticket parks at `awaiting-merge` for a diff review.

Files touched: `pipeline/hooks/dangerous-commands.py` (in `machine.FENCED`,
parks at `awaiting-merge` for human diff review),
`pipeline/hooks/test_dangerous_commands.py`, `CLAUDE.md`.

## Reproduction

Test: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`
(table-driven; added `"grep 'a > b' file.txt"` to `ALLOWED_READONLY`).

Command: `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`

Failure output:

    AssertionError: readonly: "grep 'a > b' file.txt" -> 'shell redirection into a file' (expected allow)

expect: readonly: "grep 'a > b' file.txt" -> 'shell redirection into a file' (expected allow)

The blanket refusal of `sed` (even a pure read like `sed -n '10,20p' README.md`)
is confirmed but is intentional, not a bug: `pipeline/hooks/dangerous-commands.py`
lines 285-290 spell out the reason ("sed is not read-only: a sed script writes
with `w`, `s///w` and GNU `e`"), and
`test_sed_is_off_the_read_only_allowlist_by_name` plus the `BLOCKED_READONLY`
table already lock this in from TICKET-057. No test was added for it.

## Digest

What changed since the rejected plan (Tier B `result=fail`, 2026-08-30) and the human answer at 14:42:11Z:

- The rejected plan called `SED_PRINT` "anchored at both ends" and named no criterion that fails when it is not. Step 5 now names the API, not the property: `SED_PRINT.fullmatch(args[1])`, over a pattern carrying no `^` and no `$`. A reader checks the anchor by eye at one call site.
- Step 4 adds the human's two rows to `BLOCKED_READONLY`: `sed -n '40,70p;s/a/b/w out.txt' f.rs` and `sed -n '40,70p;w out.txt' f.rs`. Each begins with a valid line print and then writes.
- Measured, not reasoned. An in-memory prototype with a start-only pattern and `.match` fails the tables: `readonly: "sed -n '40,70p;s/a/b/w out.txt' f.rs" -> None (expected block)`. The same prototype with `.fullmatch` prints `tables: PASS`. The full match is now falsifiable by `test_the_allow_and_block_tables`.
- The guard case count moves twice: `123` on this branch today, `129` after step 1, `137` after step 4. The rejected plan said `135`, which predates the human's two rows.

Files this change touches:

- `pipeline/hooks/dangerous-commands.py` (in `machine.FENCED`): `readonly_rules()` at :258 holds the redirection rule at :260 and the `sed` refusal at :288; `split_segments()` at :68 turns shlex tokens into argv lists; `verdict()` at :307 flattens `sh -c` before it calls `readonly_rules()`, so an inner redirection arrives as tokens.
- `pipeline/hooks/test_dangerous_commands.py`: the eight tables at :11-:109, `tables()` at :168, `test_the_reason_strings_the_criteria_name` at :239, `test_sed_is_off_the_read_only_allowlist_by_name` at :254.
- `CLAUDE.md` line 103 carries the guard case count. `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` sums the eight tables and asserts `CLAUDE.md` names that number, so every added table row moves that line.

Why the first plan-validation gate failed, and what `planning` committed for it:

- The gate reported the reproduction "fails, but its output does not mention the expected string". The string was in the output. `run_cmd()` in `pipeline/core/worktree.py:51` returns `(p.stdout + p.stderr)[-4000:]`, pytest prints "Captured stdout call" AFTER the assertion, and `check()` printed one line per guard case. The run was 6275 characters and the `AssertionError` sat at line 29, outside that window: `tail -c 4000 /tmp/106out.txt | grep -c 'expected allow'` printed `0`.
- `planning` committed 8a0a4ea: a module-level `VERBOSE = False` in `pipeline/hooks/test_dangerous_commands.py`, guarding the per-case `print` in `check()` and `check_mcp()`, set to `True` in the `__main__` block. The direct script prints exactly as before. Under pytest the failing run is now 1906 characters and the expect string survives the window. The test is still red on `grep 'a > b' file.txt`, so the reproduction stands.
- Full suite after that commit: `1 failed, 515 passed in 37.27s`, the one failure being the reproduction.

Measured by calling `guard.segments()` on the ticket's own rows:

- shlex already separates a real redirection from a quoted one. `grep 'a > b' file.txt` lexes to `['grep', 'a > b', 'file.txt']`; `awk 'NR>=40 && NR<=70' f.rs` to `['awk', 'NR>=40 && NR<=70', 'f.rs']`; `jq '.a>1' f` to `['jq', '.a>1', 'f']`. A real redirection is its own token: `echo hi>out.txt` gives `['echo', 'hi', '>', 'out.txt']`, `cat a>>b` gives `['cat', 'a', '>>', 'b']`, `echo x 1>f` gives `['echo', 'x', '1', '>', 'f']`.
- So the test is: a token whose characters are all in `<>&|` and which contains `>`. A quoted `>` never satisfies it, because the word around it carries other characters.
- Descriptor duplication lexes as `>&` plus a bare fd: `pytest -x 2>&1` gives `['pytest', '-x', '2', '>&', '1']`, `ls >&2` gives `['ls', '>&', '2']`. But `ls >& out.txt` gives `['ls', '>&', 'out.txt']`, which writes a file and which today's regex ALLOWS. Rule: a `>&` token is a duplication only when the next token is all digits.
- `split_segments()` drops a punctuation run carrying a newline (DEC-057), so `cat a >` + newline + `file` arrives as `[['cat', 'a'], ['file']]` with no `>` token at all, and `file` is in `READ_TOOLS`. Preserving the `>` is required, or that `BLOCKED_READONLY` row flips to allowed.
- sed shapes after lexing: `sed -n 40,70p f.rs` gives `['sed', '-n', '40,70p', 'f.rs']`, and quotes are stripped, so `sed -n '40,70p' f.rs` is the same argv. The human's two rows lex to `['sed', '-n', '40,70p;w out.txt', 'f.rs']` and `['sed', '-n', '40,70p;s/a/b/w out.txt', 'f.rs']`: the `;` sits inside the quoted script, so `split_segments()` does not split there and the whole script is `args[1]`.

Gotchas:

- An in-memory prototype of all three edits (token redirection, the `split_segments()` clause, the sed shape) was run against every existing table row plus the fourteen this plan adds. It printed `tables: PASS` and `reason strings: PASS`, `guard.verdict("sed -n '10,20p' README.md", True)` returned `None`, and `guard.segments("cat a >" + newline + "file")` returned `[['cat', 'a', '>'], ['file']]`.
- The test module loads its OWN copy of the guard, as `t.guard`. A prototype that patches a separately imported guard module changes nothing the tables see.
- `awk '{print > "f"}' x` becomes ALLOWED. The raw regex catches it today; a token scan cannot, because the ticket also requires `awk 'NR>=40 && NR<=70' f.rs` and posix shlex gives both the same shape. Reading awk script text would be invariant 4's blocklist mistake. The backstop is the read-only stage's `tree_snapshot()`/`dirty_snapshot()` baseline, which escalates `wrote-in-readonly` (DEC-011).
- `grep '>' f` stays BLOCKED. posix shlex strips the quotes, so a lone quoted `>` is byte-identical to a redirection token. Fail closed; no table row asserts it either way.
- The raw-string device-write rule in `always_rules()` at :230 is untouched. It is a blocklist backstop, it is not stage-scoped, and the quoted-`>` false positive it can produce is out of this ticket's scope.
- DEC-057 forbids adding an import to `pipeline/hooks/test_dangerous_commands.py` that base does not have, because `_base_findings()` copies that file onto base. 8a0a4ea adds none, and no step below adds one.
- DEC-057 says the count test sums "six tables"; it sums eight (`tests/test_stages.py:373-376`).

## Decisions checked

- DEC-057 (active) -- `sed` is off the read-only allowlist and the guard models no option grammar. This plan contradicts it narrowly; see the `supersedes:` line in `## Decisions`.
- DEC-058 (active) -- order is the safety property: `readonly_rules()` checks redirection and command substitution BEFORE its per-segment `[readonly] allow` prefix loop. Step 2 keeps the new token scan in that position, so a project prefix still cannot re-enable a redirection.
- DEC-075 (active) -- names the read-only allowlist's redirection refusal as part of the config-pin defence, and records that a `write: true` stage's Bash is deliberately not covered. Unchanged here: this ticket only narrows what counts as a redirection in a read-only stage.
- DEC-011 (active) -- `wrote-in-readonly` is a dispatcher verdict from the read-only baseline. It is the backstop named above for an awk script that writes.
- DEC-053 (active) -- `planning` must not repair the branch itself, because a branch whose fix is already committed makes Tier A unsatisfiable. Commit 8a0a4ea is not that repair: it changes no guard behaviour, and `test_the_allow_and_block_tables` is red before it and red after it.
- DEC-050 (active) -- the reproduction must fail before `implementing` runs. 8a0a4ea exists to make that failure legible to `gate()`, not to remove it.
- grep terms used against `.project/decisions/`: `sed`, `redirection`, `shlex`, `readonly`, `read-only`, `guard`, `allowlist`, `wrote-in-readonly`, `planning`, `fail before`.

## Plan

1. Add the redirection rows to the tables in `pipeline/hooks/test_dangerous_commands.py`: append `"awk 'NR>=40 && NR<=70' f.rs"` and `"jq '.a>1' f"` to `ALLOWED_READONLY`, append `"echo hi>out.txt"`, `"cat a>>b"`, `"echo x 1>f"` and `"ls >& out.txt"` to `BLOCKED_READONLY`, then set the count on line 103 of `CLAUDE.md` to the number `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (129 if the rows are exactly these six); run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`, watch it fail naming `awk 'NR>=40 && NR<=70' f.rs`, and commit.
2. Make the redirection rule read tokens in `pipeline/hooks/dangerous-commands.py`: add `REDIRECT_CHARS = set("<>&|")` beside `SEPARATORS` at :43, add the function `redirection(argv)` below `split_segments()` returning the first token where `">" in tok and set(tok) <= REDIRECT_CHARS`, skipping a token that ends in `&` whose next token `.isdigit()` (that is `2>&1` and `>&2`, a descriptor duplication), else `None`; replace both `re.search` calls at :260 with a loop over `segs` that returns `"shell redirection into a file"` for the first segment where `redirection(argv)` is truthy, keeping that loop above the command-substitution check and above the allow-prefix loop (DEC-058); in `split_segments()` at :75 add a first line to the separator branch that appends the one-character token `">"` to `current` when the separator token contains `>`, so `cat a >` + newline + `file` keeps its redirection while still splitting.
3. Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py` and `./pipeline/hooks/test_dangerous_commands.py`; both pass; commit `pipeline/hooks/dangerous-commands.py`.
4. Add the sed rows to `pipeline/hooks/test_dangerous_commands.py`: append `"sed -n 40,70p f.rs"`, `"sed -n 12p f.rs"` and `"sed -n '$p' f.rs"` to `ALLOWED_READONLY`, move the existing row `"sed -n '10,20p' README.md"` from `BLOCKED_READONLY` to `ALLOWED_READONLY`, append `"sed -n 's/a/b/w out.txt' f.rs"`, `"sed -i 's/a/b/' f.rs"`, `"sed -n 40,70p f.rs > out.txt"`, `"sed -n '40,70p;s/a/b/w out.txt' f.rs"` and `"sed -n '40,70p;w out.txt' f.rs"` to `BLOCKED_READONLY`, the last two being the rows the human's answer names because each begins with a valid line print and then writes; in the same file drop `"sed -n '10,20p' README.md"` from the loop in `test_the_reason_strings_the_criteria_name` and add `assert guard.verdict("sed -n '10,20p' README.md", True) is None` beneath that loop; set the count on line 103 of `CLAUDE.md` to what the count test reports (137 if steps 1 and 4 add exactly these rows); run the tables test, watch it fail naming `sed -n 40,70p f.rs`, and commit.
5. Add the one allowed sed shape to `pipeline/hooks/dangerous-commands.py`: define `SED_PRINT` beside `PY_MODULES_OK` at :65 as a compiled pattern matching a line number or `$`, optionally a comma and a second line number or `$`, then the letter `p` -- with no `^` and no `$` anchor in the pattern, because the only call site uses `SED_PRINT.fullmatch`, never `SED_PRINT.match`; add a function `sed_is_a_line_print(args)` returning True only when `len(args) >= 3`, `args[0] == "-n"`, `SED_PRINT.fullmatch(args[1])` is not None, and every element of `args[2:]` is non-empty and does not start with `-`; in `readonly_rules()` at :288 make the `sed` branch `continue` when `sed_is_a_line_print(args)` is True and otherwise return the unchanged reason string; rewrite the comment at :285-287 to say that one line-print shape is allowlisted, that `fullmatch` is what refuses a script continuing past the `p`, and that this is an allowlist of a known-safe form, not a blocklist of writing flags (invariant 4).
6. Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py` and `./pipeline/hooks/test_dangerous_commands.py`; both pass, including `test_sed_is_off_the_read_only_allowlist_by_name`, which still holds because no `SED_IN_PLACE` is defined and `sed` is not in `READ_TOOLS`; commit `pipeline/hooks/dangerous-commands.py`.
7. Verify the whole change against `pipeline/hooks/dangerous-commands.py`: run `uv run --group dev pytest -q`, then pipe the JSON event for `git worktree remove foo` into `PIPELINE_READONLY=1 python3 pipeline/hooks/dangerous-commands.py` and confirm exit status 2 with `Blocked by the pipeline guard`, then quote both outputs verbatim in the ticket's `## Thread` entry.

## Acceptance criteria

- `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` passes, and it holds these rows: `awk 'NR>=40 && NR<=70' f.rs`, `jq '.a>1' f`, `sed -n 40,70p f.rs`, `sed -n 12p f.rs`, `sed -n '$p' f.rs` and `sed -n '10,20p' README.md` allowed; `echo hi>out.txt`, `cat a>>b`, `echo x 1>f`, `ls >& out.txt`,
  `sed -n 's/a/b/w out.txt' f.rs`, `sed -i 's/a/b/' f.rs`, `sed -n 40,70p f.rs > out.txt`,
  `sed -n '40,70p;s/a/b/w out.txt' f.rs` and `sed -n '40,70p;w out.txt' f.rs` blocked.
- The sed pattern is full-matched, and the last two rows above are what proves it: with `SED_PRINT.fullmatch(args[1])` replaced by `SED_PRINT.match(args[1])`,
  `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails with
  `readonly: "sed -n '40,70p;s/a/b/w out.txt' f.rs" -> None (expected block)`.
- `grep -c 'SED_PRINT.match' pipeline/hooks/dangerous-commands.py` prints `0`, so no call site matches the sed pattern from the start alone.
- `pipeline/hooks/test_dangerous_commands.py::test_the_reason_strings_the_criteria_name` passes: `sed -i s/a/b/ x.py`, `sed --in s/a/Z/ f.txt`, `sed -n 's/a/Z/w /tmp/out.txt' f.txt` and `sed -f /tmp/script.sed f.txt` still return the exact TICKET-057 reason string.
- `pipeline/hooks/test_dangerous_commands.py::test_sed_is_off_the_read_only_allowlist_by_name` passes unchanged: no `SED_IN_PLACE` attribute, and `sed` not in `READ_TOOLS`.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0 and its last line is `guard: all passed`.
- `uv run --group dev pytest -q tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` exits 0, which re-counts the tables against `CLAUDE.md` line 103.
- `uv run --group dev pytest -q` exits 0 and prints no line beginning `FAILED`.
- `PIPELINE_READONLY=1 python3 pipeline/hooks/dangerous-commands.py` fed the JSON event for `git worktree remove foo` on stdin exits 2 and prints `Blocked by the pipeline guard` together with `worktrees are the dispatcher's to manage`.
- `git diff main --stat -- pipeline/harnesses/claude-code.toml` prints nothing, so this change alters no spawn flag and the invariant-4 re-check named in `## Decisions` covers wiring the change did not touch.

## Decisions

supersedes: DEC-057 -- `sed` is no longer refused by name alone. One shape is allowlisted, `sed -n <line/range>p <file>...`, and DEC-057's "a read-only stage that needs a line range has `head -20 f | tail -11`" no longer holds. What DEC-057 forbids is kept: `sed` stays off `READ_TOOLS`, no `-i` or per-flag option grammar returns, and `test_sed_is_off_the_read_only_allowlist_by_name` still enforces both. DEC-057's statement that a `print` redirection inside an awk script is caught by the raw-string redirection rule also stops being true; see below.

**The redirection rule judges tokens, never the raw string.** `readonly_rules()` scans each segment's argv for a token whose characters are all in `<>&|` and which contains `>`. The raw regex could not tell `awk 'NR>=40 && NR<=70' f.rs` from `echo hi>out.txt`, because after quoting they are the same bytes to a regex and different tokens to shlex. Do not reintroduce a regex over the raw command: it re-opens TICKET-106.

**A `>&` token is a descriptor duplication only when the next token is all digits.** `2>&1` and `>&2` write no file; `ls >& out.txt` does, and the old regex allowed it. That hole is closed here, and `ls >& out.txt` is in `BLOCKED_READONLY` to keep it closed.

**`split_segments()` keeps a `>` that arrives welded to a newline.** shlex emits `>` and the newline after it as one punctuation token, and DEC-057 makes such a token a separator. The separator branch now appends a bare `">"` to the segment it closes, so `cat a >` + newline + `file` is still refused. Without it that command reads as two segments, the second being `file`, which is in `READ_TOOLS`, and the redirection disappears.

**The guard's tables print one line per case only under `__main__`.** `VERBOSE` in `pipeline/hooks/test_dangerous_commands.py` is `False` at import and `True` in the `__main__` block. It exists because `run_cmd()` keeps the last 4000 characters of a test run and pytest prints captured stdout AFTER the assertion: with the prints unconditional, every failure of `test_the_allow_and_block_tables` reached `gate()` with its `AssertionError` truncated away, and Tier A rejected TICKET-106's own reproduction for "does not mention the expected string". Do not make the prints unconditional again, and do not delete them either -- the direct script run is what names the failing case (CLAUDE.md). A new `check`-style helper in this file needs the same guard.

**An awk script that writes is no longer caught by the guard, knowingly.** `awk '{print > "f"}' x` was blocked only as a side effect of the raw regex, and the ticket requires `awk 'NR>=40 && NR<=70' f.rs` to be allowed. The two are indistinguishable without reading awk script text, which is the blocklist mistake invariant 4 exists to prevent. The backstop is the read-only stage's `tree_snapshot()`/`dirty_snapshot()` baseline, which escalates `wrote-in-readonly` (DEC-011). Removing `awk` from `READ_TOOLS` is a separate ticket against a fenced file.

**`grep '>' f` is refused, and that is the accepted cost.** posix shlex strips quotes, so a lone quoted `>` is byte-identical to a redirection token. The guard fails closed rather than reconstructing quoting.

**The sed rule is an allowlist of one shape, and the match is a full match.** `sed -n`, then a script that is a line number or `$`, optionally a comma and a second one, then `p`, then one or more operands that do not start with `-`. `SED_PRINT` carries no anchors and is read only through `fullmatch`, because a start-only match allows `sed -n '40,70p;s/a/b/w out.txt' f.rs`, which writes `out.txt` through `s///w` -- the route DEC-057 verified against real GNU sed. That command and `sed -n '40,70p;w out.txt' f.rs` are in `BLOCKED_READONLY` so a later edit cannot loosen the match silently. No second flag, no missing file operand, no `-e`, no `-f`, no `w`. Widening this to a second shape means proving that shape cannot write; adding a flag blocklist instead is the TICKET-057 mistake.

**The human merge gate re-runs the invariant-4 live check.** Type `git worktree remove foo` into a spawned stage under `--setting-sources project` and `--disable-slash-commands` together and confirm it answers `Blocked by the pipeline guard`. It is not an acceptance criterion because it needs a live billed spawn with a generated `--settings` file, which no deterministic command reproduces. `pipeline/harnesses/claude-code.toml` is unchanged by this ticket, so this re-checks wiring the change did not touch.

## Rollback

Revert the commits from steps 2 and 5 in `pipeline/hooks/dangerous-commands.py` with `git revert` on each, which restores the raw-string redirection regex and the by-name `sed` refusal, then revert the two table commits from steps 1 and 4 in `pipeline/hooks/test_dangerous_commands.py` and reset `CLAUDE.md` line 103 to the count `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` then reports. Leave 8a0a4ea in place: it changes no guard behaviour, and reverting it makes every future failure of this test file illegible to `gate()` again. A read-only stage returns to refusing every quoted `>` and every `sed`, which is the pre-TICKET-106 behaviour and is fail-closed; nothing else in the pipeline reads these functions.

## Thread

### 2026-08-30 13:59:56Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-30 · triage · result=ok

Reproduced the redirection false positive. `readonly_rules()` in
`pipeline/hooks/dangerous-commands.py:260` regexes the raw command string, so
a `>` inside a quoted argument (e.g. `grep 'a > b' file.txt`) is
indistinguishable from a real redirection and is blocked. Added
`"grep 'a > b' file.txt"` to `ALLOWED_READONLY` in
`pipeline/hooks/test_dangerous_commands.py` and confirmed it fails:

    AssertionError: readonly: "grep 'a > b' file.txt" -> 'shell redirection into a file' (expected allow)

Committed on `ticket/106` (e359efd).

Checked the sed half against `git log -S "sed is not read-only"`: it is
TICKET-057's deliberate design, documented in code comments and already
covered by `test_sed_is_off_the_read_only_allowlist_by_name` and the
`BLOCKED_READONLY` table. Not a bug — no test added for it. If the ticket
means to relax that policy, it needs a decision, not a fix.

files expected to change: `pipeline/hooks/dangerous-commands.py` (fix the
redirection regex to skip quoted spans).

### 2026-08-30 14:01:59Z · triage · session · session=6addaefa-8fc4-4cb6-bdbf-ba50c82b6db8

`triage` ran as session `6addaefa-8fc4-4cb6-bdbf-ba50c82b6db8`
- replay: `claude --resume 6addaefa-8fc4-4cb6-bdbf-ba50c82b6db8`
- log: `.project/logs/TICKET-106-triage-6addaefa.log`
- cost: $0.52 of a $3 cap
- tokens: 10,240 out (1,741 thinking) · 58 in · 1,209,474 cache read · 43,961 cache write

### 2026-08-30 14:01:59Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ Reproduced: readonly redirection regex fires on a quoted `>`, not just a real one; sed's blanket refusal is intentional (TICKET-057) and not a bug.

### 2026-08-30 · planning · result=ok

Plan written. Both halves are one change to `readonly_rules()`, so they ship
together rather than as two tickets.

The redirection rule moves from a regex over the raw string to a scan of the
lexed tokens. shlex already tells the two apart: `grep 'a > b' file.txt` lexes
to `['grep', 'a > b', 'file.txt']`, `echo hi>out.txt` to
`['echo', 'hi', '>', 'out.txt']`. A prototype of both rules was run in memory
against every existing table row and the twelve new ones: all pass.

Two findings the plan acts on:

1. `ls >& out.txt` writes a file and today's regex ALLOWS it. The token rule
   closes that hole, and a `BLOCKED_READONLY` row keeps it closed.
2. `awk '{print > "f"}' x` becomes ALLOWED. The ticket requires
   `awk 'NR>=40 && NR<=70' f.rs`, and posix shlex gives both the same shape.
   Recorded in `## Decisions`; the backstop is `wrote-in-readonly`.

The sed half contradicts DEC-057, which is active. `## Decisions` opens with
`supersedes: DEC-057` and states what of it is kept.

`planning` committed 3e5e75d, a one-line `CLAUDE.md` count fix. triage's
e359efd added a table row without moving that number, so the suite excluding
`test_file` was `1 failed, 514 passed, 1 deselected` and Tier A would have read
it as pre-existing breakage. `test_the_allow_and_block_tables` is still red.

Out of scope, untouched: the raw-string device-write rule in `always_rules()`
at :230, and the command-substitution check, which has the same
quoted-argument false positive this ticket fixes for `>`.

### 2026-08-30 14:12:55Z · planning · session · session=cc21066b-d174-4b67-8b00-f07c0ff49e43

`planning` ran as session `cc21066b-d174-4b67-8b00-f07c0ff49e43`
- replay: `claude --resume cc21066b-d174-4b67-8b00-f07c0ff49e43`
- log: `.project/logs/TICKET-106-planning-cc21066b.log`
- cost: $3.65 of a $10 cap
- tokens: 46,555 out (25,252 thinking) · 74 in · 2,755,776 cache read · 110,896 cache write

### 2026-08-30 14:12:55Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: redirection judged on shlex tokens, plus one allowlisted `sed -n <range>p` shape; supersedes DEC-057 narrowly

### 2026-08-30 14:13:33Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails, but its output does not mention the expected string 'readonly: "grep \'a > b\' file.txt" -> \'shell redirection into a file\' (expected allow)'
```
'10,20p' README.md
ok  BLOCK [readonly] sed -E 's/a+/b/' thing.py
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
ok  allow [readonly] grep -rn "a
b" .
ok  allow [readonly] cat a.py
cat b.py
ok  allow [readonly] grep -rn 'a\.b' src/
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- acceptance criterion pins an absolute count copied from `## Digest` (514): - `uv run --group dev pytest -q` reports no failures at all; the baseline this branch starts from is `1 failed, 514 passed, 1 deselected` for the same command excluding `test_file`, and commit 3e5e75d already cleared that one failure. -- a total any other ticket can move is not a property of this change -- state it as a relation to a measured baseline, or re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check
- acceptance criterion names no test: - At the human merge gate, `git worktree remove foo` typed into a spawned stage under `--setting-sources project` and `--disable-slash-commands` together still answers `Blocked by the pipeline guard` (the invariant-4 condition the ticket names). -- name a test, or name a command in backticks together with the output or exit status running it must produce

### 2026-08-30 14:13:33Z · plan-validation · transition · to=planning · result=bad-plan

**plan-validation -> planning** (result: `bad-plan`)

Tier A gate failed:
- `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails, but its output does not mention the expected string 'readonly: "grep \'a > b\' file.txt" -> \'shell redirection into a file\' (expected allow)'
*-- identical output, already quoted in the `## Thread` entry `2026-08-30 14:13:33Z · plan-validation · gate · verdict=FAIL` --*
- acceptance criterion pins an absolute count copied from `## Digest` (514): - `uv run --group dev pytest -q` reports no failures at all; the baseline this branch starts from is `1 failed, 514 passed, 1 deselected` for the same command excluding `test_file`, and commit 3e5e75d already cleared that one failure. -- a total any other ticket can move is not a property of this change -- state it as a relation to a measured baseline, or re-measure at check time; one `count-pinned: <why it cannot move>` line in `## Acceptance criteria` waives this check
- acceptance criterion names no test: - At the human merge gate, `git worktree remove foo` typed into a spawned stage under `--setting-sources project` and `--disable-slash-commands` together still answers `Blocked by the pipeline guard` (the invariant-4 condition the ticket names). -- name a test, or name a command in backticks together with the output or exit status running it must produce


### 2026-08-30 · planning · result=ok

Plan rewritten. The gate's three findings, each addressed.

Finding 1, the one that was not a wording problem: the reproduction's failure
message never reached `gate()`. `run_cmd()` in `pipeline/core/worktree.py:51`
returns `(p.stdout + p.stderr)[-4000:]`, pytest prints "Captured stdout call"
AFTER the assertion, and `check()` printed one line per guard case. The run was
6275 characters with the `AssertionError` at line 29:

    tail -c 4000 /tmp/106out.txt | grep -c 'expected allow'
    0

Committed 8a0a4ea: `VERBOSE = False` at module level in
`pipeline/hooks/test_dangerous_commands.py`, guarding the per-case `print` in
`check()` and `check_mcp()`, set `True` in `__main__`. The direct script prints
as before. The pytest run is now 1906 characters and carries the expect string.
It is not the branch repair DEC-053 forbids: the test is red before and after,
and no guard behaviour moved. Suite after it: `1 failed, 515 passed in 37.27s`.

Finding 2: the criterion pinning `514` is now `exits 0 and prints no line
beginning FAILED`.

Finding 3: the invariant-4 live check needs a billed spawn, so it moves out of
`## Acceptance criteria` into `## Decisions` as a merge-gate step. The
criterion in its place is `git diff main --stat -- pipeline/harnesses/claude-code.toml`
prints nothing.

The three code edits were prototyped in memory against every table row plus the
thirteen this plan adds: `tables()` passes and the four pinned `sed` reason
strings are unchanged.

Out of scope, untouched: the raw-string device-write rule in `always_rules()`
at :230, and the command-substitution check, which has the same
quoted-argument false positive this ticket fixes for `>`.

### 2026-08-30 14:24:31Z · planning · session · session=53b712b3-4309-44a9-beb1-3c3861432168

`planning` ran as session `53b712b3-4309-44a9-beb1-3c3861432168`
- replay: `claude --resume 53b712b3-4309-44a9-beb1-3c3861432168`
- log: `.project/logs/TICKET-106-planning-53b712b3.log`
- cost: $4.72 of a $10 cap
- tokens: 50,067 out (17,454 thinking) · 108 in · 4,384,627 cache read · 127,564 cache write

### 2026-08-30 14:24:31Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan rewritten for the gate's 3 findings; committed 8a0a4ea so the repro's failure message survives run_cmd's 4000-char window

### 2026-08-30 14:25:11Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
```
s
    check(ALLOWED_READONLY, True, False, "readonly")
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cmds = ['pytest -x', 'git diff main...HEAD', 'grep -rn foo .', 'git log --oneline', 'cat thing.py', 'python3 -m pytest --deselect x', ...]
readonly = True, expect_block = False, label = 'readonly'

    def check(cmds, readonly, expect_block, label):
        for c in cmds:
            got = guard.verdict(c, readonly)
>           assert bool(got) == expect_block, \
                f"{label}: {c!r} -> {got!r} (expected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: "grep 'a > b' file.txt" -> 'shell redirection into a file' (expected allow)
E           assert True == False
E            +  where True = bool('shell redirection into a file')

pipeline/hooks/test_dangerous_commands.py:123: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.03s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
!r} (expected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: "grep 'a > b' file.txt" -> 'shell redirection into a file' (expected allow)
E           assert True == False
E            +  where True = bool('shell redirection into a file')

pipeline/hooks/test_dangerous_commands.py:123: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-lrp5fxsc/base
      Built pipeline @ file:///tmp/pipeline-base-lrp5fxsc/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 19ms

```
- ok: DEC-050 is superseded -- history, not binding

### 2026-08-30 · plan-validation · result=fail

Tier B: one item fails, seven pass.

**Falsifiable criteria -- FAIL.** No criterion fails if `SED_PRINT` is anchored
only at the start. Step 5 says "anchored at both ends", and every block row
fails on args[0] or on args[1]'s FIRST character: `sed -n 's/a/b/w out.txt' f.rs`
and `sed -i 's/a/b/' f.rs` are rejected before the tail matters, and
`sed -n 40,70p f.rs > out.txt` is rejected by the redirection rule, not the sed
rule. So `^(\d+|\$)(,(\d+|\$))?p` with no `$` passes all thirteen rows and
allows `sed -n '40,70p;s/a/b/w out.txt' f.rs`, which writes `out.txt` --
`s///w`, the route DEC-057 verified against real GNU sed. Add
`"sed -n '40,70p;s/a/b/w out.txt' f.rs"` to `BLOCKED_READONLY` (count 136, not
135) and the anchor becomes falsifiable.

Passes: root cause (the rule decides on `raw`, where quoting is already
resolved; tokens are where the distinction survives), decision conflict
(DEC-058's order kept, DEC-057 superseded with justification), scope (7 steps,
all traced), no research left (`:43`, `:65`, `:68`, `:75`, `:260`, `:285-290`,
`:307`, `CLAUDE.md:103` all verified), riskiest step (5, rollback covers it),
regression surface, blast radius (bugfix, 3 files).

Checked by reading: `pytest -x 2>&1` survives on the digit skip; `pytest 2>out`,
`pytest >> log.txt`, `pipeline ls > out.txt` stay blocked; `python3 - <<PY`
stays blocked by `GUARDED`, not by redirection. `presplit_segments()` routes
through `split_segments()` too, so the backslash path needs no second edit.

Notes, not scored findings: `triage` parked the sed half ("If the ticket means
to relax that policy, it needs a decision, not a fix"); the plan's
`supersedes: DEC-057` is that decision, and the file is fenced, so the human
gate sees it. `DEC-057` says the count test sums "six tables"; it sums eight
(`tests/test_stages.py:373-376`).

unverified: I ran no test and no `sed` -- the guard blocks `sed` for a
read-only stage (that block fired on my own `sed -n '36,80p'`), and I am
read-only. I would have run `uv run --group dev pytest -q
pipeline/hooks/test_dangerous_commands.py`. Every row above is judged by
reading the tables and the guard, not by executing them.

### 2026-08-30 14:30:17Z · plan-validation · session · session=239dc269-a9bd-4bcb-8983-6d74218521b7

`plan-validation` ran as session `239dc269-a9bd-4bcb-8983-6d74218521b7`
- replay: `claude --resume 239dc269-a9bd-4bcb-8983-6d74218521b7`
- log: `.project/logs/TICKET-106-plan-validation-239dc269.log`
- cost: $1.77 of a $3 cap
- tokens: 22,243 out (15,437 thinking) · 38 in · 1,018,157 cache read · 70,654 cache write

### 2026-08-30 14:30:17Z · plan-validation · transition · to=escalated · result=bad-plan · marker=yes

**plan-validation -> escalated** (result: `bad-plan`)

✓ fail: no criterion fails if SED_PRINT is anchored only at the start, and then sed -n '40,70p;s/a/b/w out.txt' f.rs is allowed and writes out.txt

### 2026-08-30 14:42:11Z · human · note · by=chezzijr

**resumed** by chezzijr -> `planning`, reset [], granted `plan_validation_attempts` 2 -> 1

### 2026-08-30 14:42:11Z · human · answer · by=chezzijr

**note from chezzijr**

The Tier B finding is correct and the ticket's own table was incomplete -- my fault, not the plan's alone. Two changes: (1) SED_PRINT must be full-matched, not .match()ed: either compile it with a trailing $ and keep .match, or use .fullmatch, and say which in the step so a reader can check it by eye. (2) Add these rows to BLOCKED_READONLY in pipeline/hooks/test_dangerous_commands.py, because no current criterion fails when the anchor is wrong: sed -n '40,70p;s/a/b/w out.txt' f.rs and sed -n '40,70p;w out.txt' f.rs -- both begin with a valid line print and then write. Also add ALLOWED_READONLY sed -n '$p' f.rs, since the shape claims to accept $. Everything else in the plan stands, including supersedes: DEC-057 and the note that the count test sums eight tables rather than six. If a full-match cannot be stated checkably, drop the sed half and ship the redirection fix alone -- that half is 438 of the 892 blocks and is not in question.

### 2026-08-30 · planning · result=ok

Plan rewritten. Both changes the human's answer names are in it.

1. Step 5 specifies `SED_PRINT.fullmatch(args[1])` and a pattern with no `^` and no `$`. The step names the API, so a reader checks the full match at one call site.
2. Step 4 appends `"sed -n '40,70p;s/a/b/w out.txt' f.rs"` and `"sed -n '40,70p;w out.txt' f.rs"` to `BLOCKED_READONLY`.

Measured, not reasoned. I ran an in-memory prototype of all three edits against every existing table row plus the fourteen this plan adds:

```
tables: PASS
reason strings: PASS
START-ONLY ANCHOR: tables FAIL -> readonly: "sed -n '40,70p;s/a/b/w out.txt' f.rs" -> None (expected block)
case count after both steps: 137
case count after step 1 only: 129
```

So the full match is falsifiable by `test_the_allow_and_block_tables`. The sed half stays; the answer's fallback, ship the redirection fix alone, is not needed.

Two acceptance criteria are new: the `.match` substitution above, and `grep -c 'SED_PRINT.match' pipeline/hooks/dangerous-commands.py` prints `0`.

`CLAUDE.md` line 103 says `123` today, so the count moves twice: `129` at step 1, `137` at step 4. The rejected plan said `135`.

I committed nothing. `git status --porcelain` in the worktree prints nothing.

### 2026-08-30 14:48:38Z · planning · session · session=3458537d-6aab-4fb4-a8ac-6ec8b2a43cde

`planning` ran as session `3458537d-6aab-4fb4-a8ac-6ec8b2a43cde`
- replay: `claude --resume 3458537d-6aab-4fb4-a8ac-6ec8b2a43cde`
- log: `.project/logs/TICKET-106-planning-3458537d.log`
- cost: $2.20 of a $10 cap
- tokens: 34,794 out (10,269 thinking) · 30 in · 933,277 cache read · 85,952 cache write

### 2026-08-30 14:48:38Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan rewritten for the human answer: SED_PRINT is read through fullmatch, and two BLOCKED_READONLY rows make that anchor falsifiable

### 2026-08-30 14:49:17Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-08-30 14:25:11Z · plan-validation · gate · verdict=PASS` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
!r} (expected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: "grep 'a > b' file.txt" -> 'shell redirection into a file' (expected allow)
E           assert True == False
E            +  where True = bool('shell redirection into a file')

pipeline/hooks/test_dangerous_commands.py:123: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-q7ttzcu8/base
      Built pipeline @ file:///tmp/pipeline-base-q7ttzcu8/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 17ms

```
- ok: DEC-050 is superseded -- history, not binding

### 2026-08-30 · plan-validation · result=ok

Tier B passes. Eight items, each scored.

1. Root cause. `readonly_rules()` decides redirection with two `re.search` calls over the RAW string (`pipeline/hooks/dangerous-commands.py:260-261`), so quoted argument bytes and a real operator are the same bytes to a regex. Step 2 moves the decision to shlex tokens, which already separate them. That is the cause, not the symptom.
2. Decisions. DEC-058's order property binds, and step 2 keeps the token scan above the prefix loop. DEC-057 binds and is superseded narrowly in `## Decisions`, including its line 42 claim that an awk `print` redirection is caught by the raw-string rule. DEC-075 and DEC-011 are unaffected.
3. Scope. Every step traces to a criterion; 3 files, 7 steps. The sed half exceeds the reproduction, and the human answer of 14:42:11Z endorsed it with a fallback.
4. Falsifiable. The `.match` substitution and `grep -c 'SED_PRINT.match'` are mutation criteria. The string `SED_PRINT.fullmatch` does not match that grep pattern, so the expected `0` is real.
5. No research left. Every step names files, functions and line numbers.
6. Riskiest step is 5, the sed allowlist. Fallback stated: revert steps 4-5 and ship the redirection fix alone (`## Rollback`, human answer).
7. Regression. I read every `BLOCKED_READONLY` redirection row against the proposed token rule. `echo hi > file.txt`, `pytest 2>out`, `pytest >> log.txt`, `cat a >` + newline + `file` and `pipeline ls > out.txt` each still hold a token that is all `<>&|` and contains `>`. `pytest -x 2>&1` skips on the digit rule. `python3 - <<PY` keeps its own separate refusal. Covered by `test_the_allow_and_block_tables` and `test_the_rule_file_counts_the_guard_cases`.
8. Blast radius matches `bugfix`.

Verified verbatim in the tree: `guard: all passed` (`pipeline/hooks/test_dangerous_commands.py:397`), `worktrees are the dispatcher's to manage` (`pipeline/hooks/dangerous-commands.py:219`), `Blocked by the pipeline guard` (`:409`), and `CLAUDE.md` line 103 reads `# 123 guard cases (table-driven)`.

unverified: planning's prototype numbers (`tables: PASS`, `case count after both steps: 137`). The guard refuses `python3 -c`, so I could not re-run the prototype. I checked the token shapes and the row arithmetic (+6 at step 1, +8 at step 4) by reading the tables instead.

Note for `implementing`, not a finding: `redirection()` must not index past the end when a `>&` token is the last token.

long: eight scored items plus the row-by-row regression evidence.

### 2026-08-30 14:53:33Z · plan-validation · session · session=0be1bd80-83af-403e-b6f9-a2a69b5bcd43

`plan-validation` ran as session `0be1bd80-83af-403e-b6f9-a2a69b5bcd43`
- replay: `claude --resume 0be1bd80-83af-403e-b6f9-a2a69b5bcd43`
- log: `.project/logs/TICKET-106-plan-validation-0be1bd80.log`
- cost: $1.71 of a $3 cap
- tokens: 19,088 out (9,243 thinking) · 44 in · 1,160,527 cache read · 65,296 cache write

### 2026-08-30 14:53:33Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ all eight items pass: the root cause is the raw-string regex at :260, the fullmatch criterion is falsifiable by two BLOCKED_READONLY rows, and every existing redirection row stays blocked under the token scan

### 2026-08-30 15:04:50Z · human · approval · by=chezzijr (via Claude Code, while away; this session filed the ticket and answered its escalation -- not an independent gate). The Tier B finding is answered structurally: SED_PRINT carries no anchors precisely because the only call site uses fullmatch, so the regex and the method cannot drift back into the leak, and both adversarial rows are in BLOCKED_READONLY -- sed -n '40,70p;s/a/b/w out.txt' and sed -n '40,70p;w out.txt', each beginning as a valid print and then writing. Two things the plan found that the ticket did not: an existing table row sed -n '10,20p' README.md sat in BLOCKED_READONLY and moves, with a direct verdict-is-None assertion replacing its loop entry; and split_segments() must keep a > token across a newline separator or cat a > \n file loses its redirection, a fail-open case. Step 7 runs the invariant-4 check inline. Fenced: dangerous-commands.py -- this must park at awaiting-merge for a human diff, and I will not approve that gate.

**approved by chezzijr (via Claude Code, while away; this session filed the ticket and answered its escalation -- not an independent gate). The Tier B finding is answered structurally: SED_PRINT carries no anchors precisely because the only call site uses fullmatch, so the regex and the method cannot drift back into the leak, and both adversarial rows are in BLOCKED_READONLY -- sed -n '40,70p;s/a/b/w out.txt' and sed -n '40,70p;w out.txt', each beginning as a valid print and then writing. Two things the plan found that the ticket did not: an existing table row sed -n '10,20p' README.md sat in BLOCKED_READONLY and moves, with a direct verdict-is-None assertion replacing its loop entry; and split_segments() must keep a > token across a newline separator or cat a > \n file loses its redirection, a fail-open case. Step 7 runs the invariant-4 check inline. Fenced: dangerous-commands.py -- this must park at awaiting-merge for a human diff, and I will not approve that gate.**

### 2026-08-30 15:05:33Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
```
s
    check(ALLOWED_READONLY, True, False, "readonly")
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cmds = ['pytest -x', 'git diff main...HEAD', 'grep -rn foo .', 'git log --oneline', 'cat thing.py', 'python3 -m pytest --deselect x', ...]
readonly = True, expect_block = False, label = 'readonly'

    def check(cmds, readonly, expect_block, label):
        for c in cmds:
            got = guard.verdict(c, readonly)
>           assert bool(got) == expect_block, \
                f"{label}: {c!r} -> {got!r} (expected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: "grep 'a > b' file.txt" -> 'shell redirection into a file' (expected allow)
E           assert True == False
E            +  where True = bool('shell redirection into a file')

pipeline/hooks/test_dangerous_commands.py:123: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
!r} (expected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: "grep 'a > b' file.txt" -> 'shell redirection into a file' (expected allow)
E           assert True == False
E            +  where True = bool('shell redirection into a file')

pipeline/hooks/test_dangerous_commands.py:123: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jxl1a2ps/base
      Built pipeline @ file:///tmp/pipeline-base-jxl1a2ps/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 14ms

```
- ok: DEC-050 is superseded -- history, not binding

### 2026-08-30 15:05:34Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-30 15:06:00Z · implementing · todo

**implementing: todo list**

1. [x] Step 1: add redirection rows to tables, bump CLAUDE.md count, watch red, commit.
2. [x] Step 2: token-based `redirection()` in dangerous-commands.py, `split_segments()` keeps welded `>`.
3. [x] Step 3: run both suites green, commit.
4. [x] Step 4: add sed rows to tables (including human's two adversarial rows), move `sed -n '10,20p' README.md` to allowed, bump count, watch red, commit.
5. [x] Step 5: add `SED_PRINT` (fullmatch, no anchors) and `sed_is_a_line_print()`, wire into `readonly_rules()`.
6. [x] Step 6: run both suites green, commit.
7. [x] Step 7: full suite + invariant-4 live check, quote both outputs verbatim.

### 2026-08-30 15:20:00Z · implementing · result=ok

**implementing: plan executed, all 7 steps done**

Four commits on `ticket/106`, in plan order:
- `12a61e2` test: add redirection rows to tables (129 cases), CLAUDE.md bumped, watched red on `ls >& out.txt`.
- `123e7a3` fix: `redirection(argv)` scans shlex tokens for a `<>&|`-only token containing `>`, skipping `>&<digits>`; `split_segments()` appends a bare `>` when the separator token welds one to a newline.
- `59ce69a` test: add sed rows (137 cases), move `sed -n '10,20p' README.md` to `ALLOWED_READONLY`, watched red on `sed -n 40,70p f.rs`.
- `f59c700` fix: `SED_PRINT` (no anchors) + `sed_is_a_line_print()`, read only via `.fullmatch`; wired into the `sed` branch of `readonly_rules()`.

Verified after step 7:
- `uv run --group dev pytest -q` -> `519 passed in 37.29s`, no `FAILED` line.
- `grep -c 'SED_PRINT.match' pipeline/hooks/dangerous-commands.py` -> `0`.
- Mutation check: replacing `.fullmatch` with `.match` makes `test_the_allow_and_block_tables` fail with exactly `readonly: "sed -n '40,70p;s/a/b/w out.txt' f.rs" -> None (expected block)`, matching the acceptance criterion verbatim.
- `echo '{"tool_name": "Bash", "tool_input": {"command": "git worktree remove foo"}}' | PIPELINE_READONLY=1 python3 pipeline/hooks/dangerous-commands.py` exits `2` and prints `Blocked by the pipeline guard (implementing): worktrees are the dispatcher's to manage.`
- `git diff main --stat -- pipeline/harnesses/claude-code.toml` prints nothing.

`pipeline/hooks/dangerous-commands.py` is in `machine.FENCED`: this parks at `awaiting-merge` for human diff review, per `## Decisions`.

### 2026-08-30 15:09:27Z · implementing · session · session=b7f1c598-1bca-49fd-8b0e-4b0f7723461b

`implementing` ran as session `b7f1c598-1bca-49fd-8b0e-4b0f7723461b`
- replay: `claude --resume b7f1c598-1bca-49fd-8b0e-4b0f7723461b`
- log: `.project/logs/TICKET-106-implementing-b7f1c598.log`
- cost: $1.21 of a $8 cap
- tokens: 16,837 out (1,078 thinking) · 96 in · 3,610,914 cache read · 80,362 cache write

### 2026-08-30 15:09:27Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Implemented the 7-step plan: token-based redirection rule, welded-`>` preservation, and a full-matched sed line-print allowlist. All 519 tests pass.

### 2026-08-30 15:30:00Z · review · result=fail

**review: one blocking finding on the delta `main...HEAD` (first review pass)**

1. **blocking -- process substitution `>(cmd)` writes files in a read-only
   stage; `main` blocks it.** `redirection()` requires
   `set(tok) <= REDIRECT_CHARS`, and shlex lexes `>(` as ONE token, so the
   `(` disqualifies it. Measured, both guards loaded in one process:
   `wc -l >(tee out.txt)` -> `new= None old= 'shell redirection into a file'`,
   segments `[['wc', '-l', '>(', 'tee', 'out.txt', ')']]`. Same for
   `grep foo f >(tee out.txt)` and `head -1 f >>(tee o)`. bash and zsh both
   start `tee out.txt`, which truncates it. `wc` and `grep` are in
   `READ_TOOLS`, so `readonly_rules()` returns `None`
   (`pipeline/hooks/dangerous-commands.py:336`). Refutation attempts, all
   failed: no earlier rule fires (the verdict is `None`); `## Decisions` names
   only the awk-script loss as knowing, not this one; the DEC-011 backstop
   detects a write after it lands, it does not prevent one. Adding `(` and `)`
   to `REDIRECT_CHARS` at :44 blocks it at the same fail-closed cost
   `## Decisions` already accepts for `grep '>' f`, and needs a
   `BLOCKED_READONLY` row.

Not blocking, no action asked:

- `always_rules()` never sees the inner command of `>(...)`:
  `echo hi >(rm -rf ~)` returns `None` in a WRITE stage on `main` too.
  Pre-existing, out of scope.
- `uv run <anything>` passes the read-only allowlist, so `uv run python3 -c`
  runs arbitrary Python (`GUARDED["uv"] == {"run"}`, :60). Pre-existing.
  This review used it, because `python3 -c` is refused.
- `echo hi >;ls` lexes `>;` and is allowed. bash rejects it as a syntax
  error, so it is not reachable.

What I verified as correct on this delta:

- `uv run --group dev pytest -q` -> `519 passed in 36.65s`, no `FAILED` line.
- `./pipeline/hooks/test_dangerous_commands.py` -> last line `guard: all passed`.
- `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` -> `1 passed`,
  so `CLAUDE.md` line 103 (`137`) matches the tables.
- `grep -c 'SED_PRINT.match' pipeline/hooks/dangerous-commands.py` -> `0`.
- `git diff main --stat -- pipeline/harnesses/claude-code.toml` prints nothing.
- The fullmatch criterion: with `SED_PRINT.fullmatch` delegated to `.match`
  in memory, `sed -n '40,70p;s/a/b/w out.txt' f.rs` and
  `sed -n '40,70p;w out.txt' f.rs` both return `None`, the exact acceptance
  criterion.
- 27 redirection shapes through the new guard: every real write blocked
  (`ls &>>out.txt`, `ls >|out.txt`, `ls >& out.txt`, `ls 3>f`, `ls >&2foo`,
  `cat a >` + newline + `file`, `sh -c 'cat a > b'`), every duplication
  allowed (`ls 2>&1`, `ls >&2`, `ls 1>&2`, `ls >& 2`).
- I did not re-run the invariant-4 live check for `git worktree remove foo`:
  `PIPELINE_READONLY=1 python3 ...` is itself refused in this stage. It
  tests `always_rules()`, which the delta does not touch.

### 2026-08-30 15:16:09Z · review · session · session=5075b223-1b43-4eb9-a060-eaed8c46262f

`review` ran as session `5075b223-1b43-4eb9-a060-eaed8c46262f`
- replay: `claude --resume 5075b223-1b43-4eb9-a060-eaed8c46262f`
- log: `.project/logs/TICKET-106-review-5075b223.log`
- cost: $2.08 of a $4 cap
- tokens: 26,187 out (15,051 thinking) · 44 in · 1,302,353 cache read · 76,838 cache write

### 2026-08-30 15:16:09Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ one blocking finding: the token scan lets process substitution `wc -l >(tee out.txt)` through in a read-only stage; main blocks it

### 2026-08-30 15:35:00Z · implementing · todo

**implementing: todo list (fix pass, review finding)**

1. [ ] Add `wc -l >(tee out.txt)` to `BLOCKED_READONLY`, watch `test_the_allow_and_block_tables` fail naming it, bump CLAUDE.md count.
2. [ ] Add `(` and `)` to `REDIRECT_CHARS` in `pipeline/hooks/dangerous-commands.py:44`.
3. [ ] Run both suites green, commit.
4. [ ] Full suite + invariant-4 live check, quote outputs verbatim.

### 2026-08-30 15:40:00Z · implementing · result=ok

**implementing: fixed the review's blocking finding**

Two commits on `ticket/106`:
- `dde3136` test: add `wc -l >(tee out.txt)` to `BLOCKED_READONLY` (138 cases), CLAUDE.md bumped to `138`, watched red: `AssertionError: readonly: 'wc -l >(tee out.txt)' -> None (expected block)`.
- `030d8dd` fix: `REDIRECT_CHARS` now `set("<>&|()")` at `pipeline/hooks/dangerous-commands.py:44`. shlex lexes `>(` as one token; adding `(`/`)` lets `redirection()` catch it the same way it catches `>`.

Verified:
- `uv run --group dev pytest -q` -> `519 passed in 36.68s`, no `FAILED` line.
- `./pipeline/hooks/test_dangerous_commands.py` -> last line `guard: all passed`.
- `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` -> `1 passed`.
- `grep -c 'SED_PRINT.match' pipeline/hooks/dangerous-commands.py` -> `0`.
- `git diff main --stat -- pipeline/harnesses/claude-code.toml` prints nothing.
- Invariant-4 recheck: `git worktree remove foo` piped in under `PIPELINE_READONLY=1` exits `2`, prints `Blocked by the pipeline guard (implementing): worktrees are the dispatcher's to manage.`

No regression checked: a bare grouping `(cmd)` has no `>` in its parens tokens, so `redirection()` still returns `None` for it -- `redirection()` only fires when a token contains `>` AND is built entirely from `<>&|()`.

`pipeline/hooks/dangerous-commands.py` is in `machine.FENCED`: parks at `awaiting-merge` again.

### 2026-08-30 15:18:19Z · implementing · session · session=91eb721c-d570-4441-900c-22eaebe6d447

`implementing` ran as session `91eb721c-d570-4441-900c-22eaebe6d447`
- replay: `claude --resume 91eb721c-d570-4441-900c-22eaebe6d447`
- log: `.project/logs/TICKET-106-implementing-91eb721c.log`
- cost: $0.59 of a $8 cap
- tokens: 7,286 out (737 thinking) · 54 in · 1,493,857 cache read · 53,620 cache write

### 2026-08-30 15:18:19Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ fixed the review's blocking finding: process substitution's write is now blocked in a read-only stage

### 2026-08-30 15:50:00Z · review · result=ok

**review: no blocking findings on the delta `f59c700..030d8dd` (second pass)**

The previous pass's one blocking finding is resolved. Measured with both
guards loaded in one process: `wc -l >(tee out.txt)` ->
`new= 'shell redirection into a file' old= 'shell redirection into a file'`.
Same for `grep foo f >(tee out.txt)`, `head -1 f >>(tee o)`,
`wc -l 2>(tee o)`, `wc -l >( tee out.txt )`, `bash -c 'wc -l >(tee out.txt)'`
and `wc -l >(tee out.txt) ; ls`.

Three findings I raised and dropped:

1. **Dropped -- the `(`/`)` widening is not a fail-open.** `REDIRECT_CHARS`
   is read at one site, `pipeline/hooks/dangerous-commands.py:116`, and
   `redirection()` is called at one site, :300. Widening the set only adds
   tokens to the loop; the `>&`-duplication branch at :117-118 does
   `continue`, not `return None`. Across 33 shapes, exactly three verdicts
   differ from `main`, and all three are acceptance criteria:
   `grep 'a > b' file.txt`, `awk 'NR>=40' f.rs`, `sed -n 40,70p f.rs`.
2. **Dropped -- no over-block regression.** Descriptor duplication still
   passes: `ls 2>&1`, `ls >&2`, `ls 1>&2`, `ls >& 2`, `pytest -x 2>&1` ->
   `None`. `ls 2>/dev/null` is blocked on this branch AND on `main`.
3. **Dropped -- input process substitution is not this delta's doing.**
   `cat <(rm -rf /tmp/x)` returns `None` on `main` too, in a read-only and a
   write stage.

Verified on the delta:

- `uv run --group dev pytest -q` -> `519 passed in 36.61s`, no `FAILED` line.
- `./pipeline/hooks/test_dangerous_commands.py` -> last line `guard: all passed`.
- `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` -> `1 passed`;
  `CLAUDE.md` line 103 reads `138 guard cases (table-driven)`.
- `grep -c 'SED_PRINT.match' pipeline/hooks/dangerous-commands.py` -> `0`.
- `git diff main --stat -- pipeline/harnesses/claude-code.toml` prints nothing.
- Invariant-4 check, run with `PIPELINE_READONLY=1` in the child env: exit
  `2`, stderr `Blocked by the pipeline guard (review): worktrees are the
  dispatcher's to manage.`
- `git diff main --stat` touches three files only:
  `CLAUDE.md`, `pipeline/hooks/dangerous-commands.py`,
  `pipeline/hooks/test_dangerous_commands.py`.

Not blocking, no action asked:

- `## Decisions` still says the redirection token's characters are "all in
  `<>&|`". The code is `set("<>&|()")` at :44. The docstring at :107-114 is
  current; only the ticket prose is stale.
- `<(cmd)` runs its inner command uninspected in a read-only AND a write
  stage: `cat <(rm -rf /tmp/x)` -> `None`. This is the mirror of the
  `>(...)` note the first pass filed, it predates this ticket, and closing it
  needs its own ticket against a fenced file.
- `PIPELINE_RESULT` is `.project/tickets/TICKET-106.result`; my instructions
  named `.project/TICKET-106.result`, which the guard's path rule refuses. I
  wrote the env var's path, which is what `tickets_dir()` reads
  (`pipeline/daemon/supervisor.py:465`).

### 2026-08-30 15:23:57Z · review · session · session=e91b705b-44d6-427b-9860-8af3ebc1b763

`review` ran as session `e91b705b-44d6-427b-9860-8af3ebc1b763`
- replay: `claude --resume e91b705b-44d6-427b-9860-8af3ebc1b763`
- log: `.project/logs/TICKET-106-review-e91b705b.log`
- cost: $1.95 of a $4 cap
- tokens: 21,988 out (9,468 thinking) · 50 in · 1,412,942 cache read · 69,474 cache write

### 2026-08-30 15:23:57Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ second review pass: the process-substitution finding is fixed; no blocking findings on the delta f59c700..030d8dd

### 2026-08-30 15:24:35Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/hooks/dangerous-commands.py`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-106` lands it; `pipeline resume TICKET-106 --stage planning` sends it back.

### 2026-08-30 15:36:28Z · human · approval · by=chezzijr (via Claude Code, while away; reviewed the fenced guard diff and ran the branch's guard over the full table). Verified against the branch, not by reading: ALLOW awk 'NR>=40 && NR<=70', jq '.a>1', grep -c x f 2>&1, sed -n 40,70p, sed -n $p; BLOCK echo hi>out.txt, cat a>>b, sed -n '40,70p;s/a/b/w out.txt', sed -n '40,70p;w out.txt', sed -i, wc -l >(tee out.txt), echo x >& out.txt, and git worktree remove foo -- the invariant-4 condition still holds. Two improvements over the plan: REDIRECT_CHARS includes ( and ) so process substitution >(tee out.txt) is caught, and a >& token clears only when the next token is all digits, so 2>&1 passes while >& out.txt is blocked. SED_PRINT carries no anchors and says why in its comment -- the only call site is fullmatch -- so the start-only leak cannot return through a regex edit. Re-run the live spawn check when convenient; my check was the hook invoked directly, not through a real Claude Code session.

**approved by chezzijr (via Claude Code, while away; reviewed the fenced guard diff and ran the branch's guard over the full table). Verified against the branch, not by reading: ALLOW awk 'NR>=40 && NR<=70', jq '.a>1', grep -c x f 2>&1, sed -n 40,70p, sed -n $p; BLOCK echo hi>out.txt, cat a>>b, sed -n '40,70p;s/a/b/w out.txt', sed -n '40,70p;w out.txt', sed -i, wc -l >(tee out.txt), echo x >& out.txt, and git worktree remove foo -- the invariant-4 condition still holds. Two improvements over the plan: REDIRECT_CHARS includes ( and ) so process substitution >(tee out.txt) is caught, and a >& token clears only when the next token is all digits, so 2>&1 passes while >& out.txt is blocked. SED_PRINT carries no anchors and says why in its comment -- the only call site is fullmatch -- so the start-only leak cannot return through a regex edit. Re-run the live spawn check when convenient; my check was the hook invoked directly, not through a real Claude Code session.**

### 2026-08-30 15:36:38Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/106


Current branch ticket/106 is up to date.
Already up to date.
Updating be65875..030d8dd
Fast-forward
 CLAUDE.md                                 |  2 +-
 pipeline/hooks/dangerous-commands.py      | 59 +++++++++++++++++++++++++++----
 pipeline/hooks/test_dangerous_commands.py | 36 ++++++++++++++++---
 3 files changed, 86 insertions(+), 11 deletions(-)

```

### 2026-08-30 15:36:38Z · merging · decision

decision recorded as `DEC-106`
