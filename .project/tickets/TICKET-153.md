---
id: TICKET-153
stage: done
class: bugfix
branch: ticket/153
test_file:
- tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence
- pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
deletes: []
files_declared:
- CLAUDE.md
- README.md
- pipeline/core/machine.py
- pipeline/hooks/dangerous-commands.py
- pipeline/hooks/test_dangerous_commands.py
counters:
  plan_validation_attempts: 2
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 10
  plan_files: 5
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: ebe5d6ca-503a-4cb2-a591-af74d7074e28
  replay: claude --resume ebe5d6ca-503a-4cb2-a591-af74d7074e28
  log: .project/logs/TICKET-153-review-ebe5d6ca.log
  cost_usd: 1.479394
approved_by: chezzijr
approved_at: '2026-10-02T09:04:08.734359+00:00'
---

## Summary

Two holes in what is supposed to keep a stage inside its limits: the fence misses the validator's own patterns, and the read-only guard lets `find` and `awk` write

Expected change files: `pipeline/core/machine.py`, `pipeline/hooks/dangerous-commands.py`, `pipeline/hooks/test_dangerous_commands.py`, `tests/test_fence.py` and `CLAUDE.md`.

Both were found while landing TICKET-151 and TICKET-152, and both weaken a promise `CLAUDE.md` makes. They are filed together at the operator's request; each needs its own failing test.

**1. `FENCED` watches `validate_meta` but not the patterns it applies.** `pipeline/core/machine.py:60`, on main at 9180b1b:

    "pipeline/core/ticket.py": ("validate_meta",),

`validate_meta()` (`pipeline/core/ticket.py:110`) checks hostile ticket values against module-level patterns -- `SAFE_ID`, `SAFE_BRANCH`, `SAFE_TEST`, `SAFE_FILE`, `SAFE_HASH` at `:29-36` and `SAFE_DEC_ID` at `:409`. TICKET-151 widened `SAFE_TEST` to accept spaces and `>`; its diff did not touch the `validate_meta` function body, so it went straight to `merging` and never stopped at `awaiting-merge`. A ticket could loosen any of these patterns -- the input side of invariant 5 -- with no human review. Expected: a diff that changes any `SAFE_*` pattern in `pipeline/core/ticket.py` is fenced exactly like a change to `validate_meta`. Test (in `tests/test_fence.py`, beside the existing fence tests): a diff that changes only the `SAFE_TEST` line currently reports as not fenced.

**2. The read-only allowlist admits `find` and `awk` with no argument check.** `READ_TOOLS` at `pipeline/hooks/dangerous-commands.py:57` includes both. Run through the hook with `PIPELINE_READONLY=1` on main at 9180b1b, every one of these exits 0 (allowed):

    find . -name x -delete
    find . -exec rm {} ;
    find . -fprint /tmp/out
    awk 'BEGIN{system("touch /tmp/x")}'

The tree snapshot catches a write inside the worktree after the fact, but not a write or delete outside it (`/tmp`, `$HOME`). Expected: in a read-only stage, `find` is refused when any argument is a write or exec action (`-delete`, `-exec`, `-execdir`, `-ok`, `-okdir`, `-fprint`, `-fprint0`, `-fprintf`, `-fls`); `awk` is refused when its program can run a command or write a file (`system(`, a `|` pipe, a `>` redirect, `getline` from a command). Plain `find . -name x` and `awk '{print $1}' f` stay allowed. Add each case to the guard's `BLOCKED_READONLY` / `ALLOWED_READONLY` tables. The allowlist stays an allowlist (invariant 4): narrow these two tools by argument the way `sed_is_a_line_print()` narrows `sed`, or move them to a guarded form -- planning decides.

Both files are fenced, so this ticket parks at `awaiting-merge`.


## Reproduction

Two tests, committed in 33be0fb. Both fail on main.

1. `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence`
2. `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage`

Command: `uv run --group dev pytest -q <id>`

Failure 1 (a diff changing only `SAFE_TEST` reports not fenced):

    >       assert fenced_touches(d, "main") != []
    E       AssertionError: assert [] != []

expect: AssertionError: assert [] != []

Failure 2 (the hook exits 0 for `find -delete` in a read-only stage):

    E       AssertionError: ('find . -name x -delete', 0, '')

expect: AssertionError: ('find . -name x -delete', 0, '')

## Digest

Files touched: `pipeline/core/machine.py` (FENCED), `pipeline/hooks/dangerous-commands.py` (read-only rules), `pipeline/hooks/test_dangerous_commands.py` (tables), `CLAUDE.md` (fence sentence at line 504, guard case count at line 107), `README.md` (read-only section, after the loop paragraph at line 879). `tests/test_fence.py` holds the repro and is not edited.

Scope, from the operator's 07:59:04Z answer: "Widen TICKET-153 to every readonly_rules() branch -- READ_TOOLS (find/awk), git, and GUARDED (uv/poetry run, npm/pnpm/yarn run). One root cause, one ticket". Every branch of `readonly_rules()` is narrowed by argument: `READ_TOOLS` (steps 2-4), git (step 5), `uv run`/`poetry run` (step 6), npm/pnpm/yarn (step 7), make/cargo/go (step 8), test runners and `python -m` (step 9). make, cargo, go and the test runners share those branches, and each has a measured hole below.

How this differs from the plan failed at 07:56:21Z: that plan narrowed `READ_TOOLS` only. Steps 5-10 are new. Steps 1-3 are unchanged. Step 4 now defines the shared `operands()` and `options_verdict()` that steps 5, 8 and 9 reuse.

How this differs from the plan escalated at 08:29:01Z (`bad-plan`): step 7 allowed `npm test -- <any args>`, which passes an unchecked argument to the test tool (jest `--outputFile`, pytest `--junit-xml`). The operator's 08:30:18Z note: "npm/pnpm/yarn test is allowed with NO arguments; refuse anything after test, including '--' and its args, like cargo test -- and tox --. Keep everything else in the plan as is." Step 7 now accepts exactly `test` or `run test`, and `"npm test -- --runInBand"` moves from `ALLOWED_READONLY` to `BLOCKED_READONLY`, so step 7 still adds 13 cases. Step 10 and `## Decisions` drop "with arguments only after `--`". Every other step is unchanged.

Fence, part 1:
- `fenced_touches()` (`pipeline/core/fence.py:64`) matches a FENCED symbol through `symbol_lines()` (`pipeline/core/fence.py:41`), which handles a module-level assignment such as `SAFE_TEST = re.compile(...)`. Adding the six names to the tuple is the whole fix.
- The six patterns in `pipeline/core/ticket.py`: `SAFE_ID` :29, `SAFE_BRANCH` :30, `SAFE_TEST` :34, `SAFE_FILE` :35, `SAFE_HASH` :36, `SAFE_DEC_ID` :409. `validate_meta()` applies the first five; `parse_correction()` (:551) and `correct_decision()` (:616) apply `SAFE_DEC_ID`.
- Gotcha: `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` (:407) compares the set of backticked tokens in the `CLAUDE.md` paragraph ending "requires human review before merge" with every FENCED path and symbol, both directions. Each `SAFE_*` name must appear backticked in that paragraph, in the same commit as the FENCED change.
- Gotcha (DEC-043): a comment above a FENCED entry but inside the dict literal is inside the fenced span; put the new comment there.

Guard, part 2:
- Entry point: `readonly_rules()` (`pipeline/hooks/dangerous-commands.py:444`). Branch order after this plan: `cd`, project prefix, `unwrap_run()`, project prefix on the unwrapped command, git, sed, find, awk, npm/pnpm/yarn, `OPTION_SPECS`, `READ_TOOLS`, `GUARDED`.
- Model: `sed_is_a_line_print()` (:81) narrows sed by shape. Every new helper goes after it, in step order.
- One parser serves every narrowed tool: `operands(args, spec)` reads GNU getopt syntax plus Go-style single-dash long names. A spec is a 5-tuple: short flags, short options taking a value, long flags, long options taking a value, most operands (`None` for any number).
- Holes measured on this machine at 33be0fb, each allowed by the unfixed guard, in a temp dir with a script that touches a marker file:
  1. coreutils 9.11 `sort -o out1 f` wrote `out1`; `uniq f out2` wrote `out2`; ripgrep 15.2.0 `rg --pre ./p.sh a f` ran p.sh; file-5.48 `file -C -m m` wrote `m.mgc`.
  2. git 2.55.0: `git diff --output=$T/o-full HEAD~1` wrote `o-full`. `git grep -O$T/b.sh SAFE_TEST` ran b.sh. `git grep --open-files=$T/a.sh SAFE_TEST` ran a.sh, an abbreviation parse-options accepts. `git log -1 --outp=$T/o-log` printed `fatal: unrecognized argument: --outp=...`.
  3. npm 12.0.2: `npm test --script-shell=./npm.sh` ran npm.sh. `npm test -- --script-shell=./npm2` exited 0 with the default shell; after `--` it is a script argument.
  4. GNU Make 4.4.1: `make test SHELL=./mk.sh` ran mk.sh; `make test --eval='$(shell touch $T/make-eval)'` created `make-eval`.
  5. cargo 1.98.1: `cargo check --config 'build.rustc-wrapper="$T/w.sh"'` ran w.sh; `cargo test -- --logfile $T/libtest.log` wrote it; `cargo build --target-dir $T/tdir` wrote `tdir`.
  6. go: `go test -exec $T/go.sh .` ran go.sh; `go test -o $T/out.test -c .` wrote `out.test`.
  7. pytest: `uv run --group dev pytest -q --junit-xml=$T/junit.xml tests/test_fence.py -k nothing_matches` wrote `junit.xml`.
  8. From the 07:56 research: `uv run rm /tmp/x`, `poetry run touch /tmp/x`, `npm run deploy`, `git branch -D foo`, `git remote add x u` and `git worktree add ../x list` are allowed.
- Not measured: `poetry`, `yarn`, `ag`, `tree`, `yq`, `tox` and `nox` print `command not found` here. `pnpm test --config.script-shell=./pnpm.sh` did not run pnpm.sh; step 7 refuses every argument after `test` anyway.
- uv 0.12.10 `uv run --help` lists `--with`, `--python` (uv runs the interpreter it names to probe it), `--directory`, `--project`, `--script`, `-m` and `--env-file`. None is in `RUN_WRAPPERS`.
- The `--help` text of every remaining `READ_TOOLS` member lists no file-writing or command-running option. `date -s` sets the clock; it writes no file and runs no command, so it is outside this ticket.
- GNU find consumes the token after a value-taking test: `find $T -name -delete` deleted nothing. gawk 5.4.1: `awk 'BEGIN{print 1 >= "x"}'` printed `0` and wrote no file; `awk 'BEGIN{x="system"; @x("echo indirect-ran")}'` printed `indirect-ran`.
- Prototype: every step applied to scratch copies of the guard and its test file in `/tmp/t153`. 131 candidate commands through `verdict(cmd, True)` printed `bad 0 of 131`. The scratch test file holding every table case below printed `guard: all passed` as a script and `16 passed in 1.51s` under pytest, the find/awk repro included. Cases added per step 2-9: 13, 11, 26, 35, 22, 13, 27, 21. Step 7's 08:30 change was not re-run in the prototype: this stage's guard refuses a write outside the worktree. The change is the one-line predicate `args in (["test"], ["run", "test"])`; the implementer's table run is its check.
- Gotcha: `guarded_options()` reads `GUARDED_SPECS[name]` and raises `KeyError` for a `GUARDED` tool with no entry. npm/pnpm/yarn leave `GUARDED` in step 7 so that step 8 meets no such tool. Keep the steps in order.
- Gotcha: `pytest -x 2>&1` lexes as `-x`, `2`, `>&`, `1`; pytest takes any number of operands, so the existing allowed case still passes. `uniq -c f 2>&1` is refused (two operands), an accepted cost.
- GNU getopt accepts an unambiguous long-option prefix (`sort --out=x`). `operands()` matches exact names only, so every abbreviation is refused, an accepted cost.
- `[readonly] allow` prefixes are matched above every branch (DEC-058), and again on the command `uv run`/`poetry run` runs. A `for` body reaches the branches once per word (DEC-152).
- This repo keeps working: `uv run --group dev pytest -x {test}` unwraps to pytest `-x`, and `./pipeline/hooks/test_dangerous_commands.py` matches this repo's `[readonly] allow`. No stage prompt or skill names a command these steps refuse (grep of backticked commands in `pipeline/stages/*.md` and both `SKILL.md` files).
- Baselines on this worktree at 33be0fb (unfixed): `uv run --group dev pytest -q` printed `2 failed, 761 passed in 80.51s`, the two being this ticket's repro tests. `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py tests/test_stages.py::test_the_rule_file_counts_the_guard_cases tests/test_stages.py::test_the_fenced_list_matches_the_rule_file tests/test_fence.py` printed `2 failed, 22 passed in 1.60s`, the same two. `./pipeline/hooks/test_dangerous_commands.py` printed `guard: all passed` and no `FAIL` line.

## Decisions checked

- DEC-106 (active): its paragraph "An awk script that writes is no longer caught by the guard, knowingly" says reading awk program text is invariant 4's blocklist mistake. Step 3 reads awk program text, as the ticket requires, so `## Decisions` supersedes DEC-106 and restates every other DEC-106 rule so it stays binding.
- DEC-057 (superseded by DEC-106): history only; the same awk stance and the `sed` removal.
- DEC-031 (active, with a TICKET-149 correction on `pipeline reject`): the fence matches symbols, not whole files. Complied with: `pipeline/core/ticket.py` stays a symbol tuple, not `None`.
- DEC-043 (active): FENCED fences itself, and a load-bearing comment goes inside the dict literal. Complied with.
- DEC-151 (active): `SAFE_TEST`'s current shape. Unchanged; step 1 only fences it.
- DEC-152 (active): a `for` body is judged verbatim and once per word. The new branches inherit that; steps 2, 4 and 5 each add a loop case.
- DEC-058 (active): project prefixes never re-enable the redirection or `always_rules()` checks. Unchanged; step 6 adds a second prefix match after `unwrap_run()`, still below both checks.
- DEC-072 (active): a stage's Bash runs `uv run --group dev pytest -q`. Complied with: it unwraps to pytest `-q`, which step 9 allows.

Grep terms: `READ_TOOLS`, `awk`, `find .`, `-delete`, `sort`, `uniq`, `rg`, `--pre`, `SAFE_TEST`, `SAFE_*`, `fenced_touches`, `symbol_lines`, `sed_is_a_line_print`, `allowlist`, `FENCED`, `uv run`, `GUARDED`, `GIT_READ`, `worktree list`, `npm`, `make test`, `TEST_RUNNERS`, `invariant 4`.

## Plan

1. Fence the six `SAFE_*` patterns: in `pipeline/core/machine.py` replace the FENCED line `"pipeline/core/ticket.py": ("validate_meta",),` with the block below, and in `CLAUDE.md` (line 504) extend the fence sentence; then run `tests/test_fence.py` and the drift test.
   ```python
       # The patterns that check a hostile ticket or sidecar value: SAFE_DEC_ID
       # in correct_decision(), the rest in validate_meta(). A ticket that
       # loosened one never touched a function body (TICKET-151 widened
       # SAFE_TEST and merged unattended).
       "pipeline/core/ticket.py": ("validate_meta", "SAFE_ID", "SAFE_BRANCH",
                                   "SAFE_TEST", "SAFE_FILE", "SAFE_HASH",
                                   "SAFE_DEC_ID"),
   ```
   In `CLAUDE.md` change `` `transition()`, `validate_meta()`, `CONTROL_FIELDS`, `` to `` `transition()`, `validate_meta()` and the patterns that check ticket values (`SAFE_ID`, `SAFE_BRANCH`, `SAFE_TEST`, `SAFE_FILE`, `SAFE_HASH`, `SAFE_DEC_ID`), `CONTROL_FIELDS`, `` and rewrap the paragraph so no backticked token splits across lines and no blank line enters it. Commit `fix(TICKET-153): fence the SAFE_* patterns that check ticket values`.
2. Narrow `find` by argument in `pipeline/hooks/dangerous-commands.py`: remove `"find"` from `READ_TOOLS`, add the constants and function below after `sed_is_a_line_print()`, add the branch below to `readonly_rules()` directly after the `if name == "sed":` block, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`.
   ```python
   # The tests, options and stdout actions of find. An allowlist (invariant 4):
   # -delete, -exec, -execdir, -ok, -okdir, -fprint, -fprint0, -fprintf and
   # -fls are on neither list, and neither is any primary added later.
   # FIND_ARG primaries consume exactly one following token, so a value such
   # as `-mtime -7` is never read as a primary.
   FIND_ARG = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename",
               "-regex", "-iregex", "-lname", "-ilname", "-type", "-xtype", "-size",
               "-newer", "-anewer", "-cnewer", "-mtime", "-mmin", "-atime", "-amin",
               "-ctime", "-cmin", "-used", "-perm", "-user", "-group", "-uid", "-gid",
               "-links", "-inum", "-samefile", "-fstype", "-maxdepth", "-mindepth",
               "-regextype", "-printf"}
   FIND_FLAG = {"-H", "-L", "-P", "-depth", "-xdev", "-mount", "-follow", "-noleaf",
                "-daystart", "-empty", "-readable", "-writable", "-executable",
                "-nouser", "-nogroup", "-true", "-false", "-not", "-and", "-or",
                "-a", "-o", "-print", "-print0", "-ls", "-prune", "-quit"}


   def find_only_reads(args: list[str]) -> bool:
       """True when every `-` argument of `find` is in FIND_FLAG, or is in
       FIND_ARG and has the value it consumes."""
       i = 0
       while i < len(args):
           if args[i] in FIND_ARG:
               if i + 1 >= len(args):
                   return False
               i += 2
               continue
           if args[i].startswith("-") and args[i] not in FIND_FLAG:
               return False
           i += 1
       return True
   ```
   Branch in `readonly_rules()`:
   ```python
           if name == "find":
               if find_only_reads(args):
                   continue
               return ("find: only tests and stdout actions are read-only -- "
                       "-delete, -exec, -ok and -fprint write or run a command; "
                       "use grep -r to search file contents")
   ```
   Append to `BLOCKED_READONLY`, under a `# TICKET-153: find writes or runs a command` comment: `"find . -name x -delete"`, `"find . -exec rm {} ;"`, `"find . -execdir rm {} +"`, `"find . -ok rm {} ;"`, `"find . -okdir rm {} ;"`, `"find . -fprint /tmp/out"`, `"find . -fprint0 /tmp/out"`, `"find . -fprintf /tmp/out %p"`, `"find . -fls /tmp/out"`, `"for f in -delete; do find . $f; done"`. Append to `ALLOWED_READONLY`, under `# TICKET-153`: `"find . -type f -mtime -7"`, `"find -L . -maxdepth 2 -size -10k -print"`, `"find . -path ./node_modules -prune -o -name '*.js' -print"`. Set the `# <N> guard cases (table-driven)` number in `CLAUDE.md` line 107 to the count `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (188 + 13 = 201 at plan time). Commit `fix(TICKET-153): refuse a find that writes or runs a command in a read-only stage`.
3. Narrow `awk` by argument in `pipeline/hooks/dangerous-commands.py`: remove `"awk"` from `READ_TOOLS`, add the constant and function below after `find_only_reads()`, add the branch below to `readonly_rules()` directly after the `find` branch, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`.
   ```python
   # The routes awk has to a file or a command: `>`/`>>` and `|`/`|&` after
   # print or getline, system(), and gawk `@` (`@load`, `@include`, and `@f()`,
   # an indirect call that reaches system -- measured on gawk 5.4.1). `>=` is a
   # comparison and never a redirection, so `NR>=40` stays readable.
   AWK_UNSAFE = re.compile(r"[|@]|>(?!=)|system")


   def awk_only_reads(args: list[str]) -> bool:
       """True for `awk [-F sep] [-v name=val]... program [file]...`: no other
       option (so no -f, -i, -l, -o, -p, -e, -E or --long), a program
       AWK_UNSAFE does not match, and no operand starting with `-`."""
       i = 0
       while i < len(args) and args[i].startswith("-"):
           if args[i] in ("-F", "-v"):
               i += 2
           elif args[i][:2] in ("-F", "-v"):
               i += 1
           else:
               return False
       if i >= len(args):
           return False
       return (AWK_UNSAFE.search(args[i]) is None
               and all(a and not a.startswith("-") for a in args[i + 1:]))
   ```
   Branch in `readonly_rules()`:
   ```python
           if name == "awk":
               if awk_only_reads(args):
                   continue
               return ("awk: a read-only awk takes only -F and -v, and its program "
                       "holds no |, @, system or > -- write NR>1 as NR>=2")
   ```
   Append to `BLOCKED_READONLY`, under `# TICKET-153: awk writes or runs a command`: `"awk 'BEGIN{system(\"touch /tmp/x\")}'"`, `"awk '{print $1 > \"out\"}' f"`, `"awk '{print $1 >> \"out\"}' f"`, `"awk '{print $1 | \"sh\"}' f"`, `"awk 'BEGIN{\"date\" | getline d}'"`, `"awk 'BEGIN{x=\"system\"; @x(\"touch /tmp/x\")}'"`, `"awk -f prog.awk f"`, `"awk -i inplace '{print}' f"`. Append to `ALLOWED_READONLY`: `"awk '{print $1}' f"`, `"awk -F: '{print $1}' /etc/passwd"`, `"awk -F , -v n=3 'NR==n{print $2}' f.csv"`. Keep the existing `"awk 'NR>=40 && NR<=70' f.rs"` case. Set the `CLAUDE.md` line 107 count to what `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (201 + 11 = 212 at plan time). Commit `fix(TICKET-153): refuse an awk program that writes or runs a command in a read-only stage`.
4. Narrow `sort`, `uniq`, `rg` and `file` by option, and drop `ag`, `tree` and `yq`, in `pipeline/hooks/dangerous-commands.py`: set `READ_TOOLS` to the literal below, add `OPTION_SPECS`, `operands()` and `options_verdict()` below after `awk_only_reads()`, add the branch below to `readonly_rules()` directly after the `awk` branch, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`.
   ```python
   READ_TOOLS = {"ls", "cat", "head", "tail", "wc", "grep", "stat", "du", "echo",
                 "true", "false", "pwd", "which", "basename", "dirname", "cut",
                 "diff", "column", "jq", "date", "printf", "test", "[", "nl"}
   ```
   ```python
   # The options a program may take in a read-only stage: (short flags, short
   # options taking a value, long flags, long options taking a value, most
   # operands or None for any number). An allowlist (invariant 4): every write
   # or exec option -- sort -o/-T/--compress-program, rg --pre/--hostname-bin/-z,
   # file -C/-m -- is on no list and is refused, and so is a GNU long-option
   # abbreviation. uniq takes one operand, because its second is an output file.
   OPTION_SPECS = {
       "sort": ("bcCdfghiMmnRrsuVz", "kSt",
                {"--ignore-leading-blanks", "--dictionary-order", "--ignore-case",
                 "--general-numeric-sort", "--ignore-nonprinting", "--month-sort",
                 "--human-numeric-sort", "--numeric-sort", "--random-sort",
                 "--reverse", "--version-sort", "--stable", "--unique",
                 "--zero-terminated", "--merge"},
                {"--key", "--field-separator", "--buffer-size", "--sort", "--parallel"},
                None),
       "uniq": ("cdDiuz", "fsw",
                {"--count", "--repeated", "--ignore-case", "--unique",
                 "--zero-terminated"},
                {"--skip-fields", "--skip-chars", "--check-chars"}, 1),
       "rg": ("abcFHhIiLlNnoPpqSsUuvVwx0", "ABCdEefgjMmrTt",
              {"--hidden", "--no-ignore", "--no-ignore-vcs", "--files",
               "--files-with-matches", "--files-without-match", "--count",
               "--count-matches", "--fixed-strings", "--ignore-case", "--smart-case",
               "--case-sensitive", "--word-regexp", "--line-regexp", "--line-number",
               "--no-line-number", "--heading", "--no-heading", "--with-filename",
               "--no-filename", "--only-matching", "--invert-match", "--multiline",
               "--multiline-dotall", "--pcre2", "--follow", "--json", "--vimgrep",
               "--column", "--null", "--quiet", "--type-list", "--no-messages",
               "--unrestricted", "--text", "--trim", "--stats", "--passthru"},
              {"--glob", "--iglob", "--type", "--type-not", "--max-depth",
               "--max-count", "--context", "--after-context", "--before-context",
               "--regexp", "--file", "--replace", "--sort", "--sortr",
               "--max-columns", "--max-filesize", "--threads", "--color",
               "--encoding"}, None),
       "file": ("bhikLN", "",
                {"--brief", "--mime", "--mime-type", "--mime-encoding",
                 "--dereference", "--no-dereference", "--keep-going", "--no-pad"},
                set(), None),
   }


   def operands(args: list[str], spec: tuple) -> list[str] | None:
       """`args` without its options, or None when an option is not in `spec`.
       Reads GNU getopt syntax -- a short cluster (`-nr`, `-k2,2`, `-t,`),
       `--long` and `--long=value`, a value in the next token, and `--` -- and
       the single-dash long names of Go (`-run=x`, `-count 1`) when the spec
       lists them among its long options."""
       short, short_valued, long_flags, long_valued, _ = spec
       out, i = [], 0
       while i < len(args):
           a = args[i]
           i += 1
           if a == "--":
               return out + args[i:]
           name, eq, _ = a.partition("=")
           if name in long_flags and not eq:
               continue
           if name in long_valued:
               if not eq and i >= len(args):
                   return None
               i += 0 if eq else 1
               continue
           if a.startswith("--"):
               return None
           if a.startswith("-") and a != "-":
               for j, c in enumerate(a[1:], 1):
                   if c in short_valued:
                       if j == len(a) - 1:
                           if i >= len(args):
                               return None
                           i += 1
                       break
                   if c not in short:
                       return None
               continue
           out.append(a)
       return out


   def options_verdict(label: str, args: list[str], spec: tuple) -> str | None:
       """None when every option in `args` is in `spec` and the operands number
       at most spec[4]; otherwise the reason, naming `label`."""
       ops = operands(args, spec)
       if ops is not None and (spec[4] is None or len(ops) <= spec[4]):
           return None
       return (f"{label}: an option outside its read-only set, or one operand too "
               "many -- that set, in pipeline/hooks/dangerous-commands.py, leaves "
               "out every option that writes a file or runs a command")
   ```
   Branch in `readonly_rules()`:
   ```python
           if name in OPTION_SPECS:
               why = options_verdict(name, args, OPTION_SPECS[name])
               if why:
                   return why
               continue
   ```
   Append to `BLOCKED_READONLY`, under `# TICKET-153: sort, uniq, rg and file write or run a command; ag, tree and yq left READ_TOOLS`: `"sort -o /tmp/out f"`, `"sort -no /tmp/out f"`, `"sort --output=/tmp/out f"`, `"sort --out=/tmp/out f"`, `"sort --compress-program=./p.sh f"`, `"sort -T /tmp f"`, `"uniq f /tmp/out"`, `"uniq -c f /tmp/out"`, `"rg --pre ./p.sh a ."`, `"rg --pre=./p.sh a ."`, `"rg --hostname-bin=./p.sh a ."`, `"rg -z a ."`, `"file -C -m m"`, `"for o in -o; do sort $o /tmp/out f; done"`, `"tree -o /tmp/out"`, `"yq -i '.a=1' f.yaml"`, `"ag --pager ./p.sh a"`. Append to `ALLOWED_READONLY`, under `# TICKET-153`: `"rg -n --hidden -g '*.py' 'def foo' pipeline/"`, `"rg -l -t py -e '-foo' ."`, `"rg --files"`, `"sort -nr f"`, `"sort -t, -k2,2 f.csv"`, `"sort -u --key=1,1 f"`, `"git log --oneline | sort | uniq -c | sort -rn | head"`, `"uniq -c f"`, `"file -b --mime-type x.py"`. Keep the existing `"rg evict src/"` case. Set the `CLAUDE.md` line 107 count to what `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (212 + 26 = 238 at plan time). Commit `fix(TICKET-153): narrow sort, uniq, rg and file by option in a read-only stage`.
5. Narrow git by option and by listing form in `pipeline/hooks/dangerous-commands.py`: delete the line `GIT_WORKTREE_READ = {"list"}`, add the constants and function below after `options_verdict()`, replace the whole `if name == "git":` block in `readonly_rules()` with the branch below, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`.
   ```python
   # git options that write a file or run a command, refused on every git call
   # and in every prefix: `git grep --open-files=./p.sh` ran p.sh as
   # --open-files-in-pager (git 2.55.0). Refusing options inside an allowlisted
   # subcommand is the written exception to invariant 4 in TICKET-153.
   GIT_REFUSED = ("--output", "--open-files-in-pager", "--ext-diff", "--exec-path",
                  "--config-env")
   # the options `git branch` lists with; a name operand creates a branch unless
   # -l/--list makes it a pattern
   GIT_BRANCH_LIST = ("alrvi", "",
                      {"--all", "--remotes", "--list", "--verbose", "--show-current",
                       "--ignore-case", "--color", "--no-color"},
                      {"--contains", "--no-contains", "--merged", "--no-merged",
                       "--points-at", "--sort", "--format", "--color"}, None)


   def git_verdict(args: list[str]) -> str | None:
       """None when `git <args>` only reads: a GIT_READ subcommand, no global
       `-c`, no GIT_REFUSED option or prefix of one, no `git grep -O`, and the
       listing forms only of `branch`, `remote` and `worktree`."""
       at = next((i for i, a in enumerate(args)
                  if not a.startswith("-") and (i == 0 or args[i - 1] != "-C")), None)
       sub = None if at is None else args[at]
       if sub not in GIT_READ:
           return f"git {sub or ''}: not a read-only git subcommand"
       if "-c" in args[:at]:
           return "git -c: a config value can name a command for git to run"
       for a in args:
           opt = a.partition("=")[0]
           if opt.startswith("--") and len(opt) > 2 and any(r.startswith(opt) for r in GIT_REFUSED):
               return f"git {opt}: writes a file or runs a command"
       rest = args[at + 1:]
       if sub == "grep" and any(a[:1] == "-" and a[:2] != "--" and "O" in a for a in rest):
           return "git grep -O: opens the matches in a pager, which runs a command"
       if sub == "branch":
           ops = operands(rest, GIT_BRANCH_LIST)
           if ops is None or ops and not {"-l", "--list"} & set(rest):
               return ("git branch: only listing is read-only -- a name operand "
                       "creates a branch, and -d, -m, -c, -f and -u write refs")
       if sub == "remote":
           while rest[:1] in (["-v"], ["--verbose"]):
               rest = rest[1:]
           if rest[:1] not in ([], ["show"], ["get-url"]):
               return "git remote: only listing, `show` and `get-url` are read-only"
       if sub == "worktree" and rest[:1] != ["list"]:
           return "git worktree: only `list` is read-only"
       return None
   ```
   Branch in `readonly_rules()`, replacing the old `if name == "git":` block:
   ```python
           if name == "git":
               why = git_verdict(args)
               if why:
                   return why
               continue
   ```
   Append to `BLOCKED_READONLY`, under `# TICKET-153: git options and forms that write or run a command`: `"git diff --output=/tmp/o HEAD"`, `"git log --output /tmp/o -1"`, `"git show --output=/tmp/o HEAD"`, `"git grep -O./p.sh x"`, `"git grep -nO./p.sh x"`, `"git grep --open-files-in-pager=./p.sh x"`, `"git grep --open-files=./p.sh x"`, `"git -c core.pager=./p.sh log"`, `"git --config-env=core.pager=P log"`, `"git --exec-path=/tmp log"`, `"git diff --ext-diff HEAD"`, `"git branch -D foo"`, `"git branch newref"`, `"git branch -m a b"`, `"git branch -f main HEAD"`, `"git branch --set-upstream-to=origin/x"`, `"git remote add x u"`, `"git remote -v remove origin"`, `"git remote set-url origin u"`, `"git worktree add ../x list"`, `"for o in --output=/tmp/o; do git diff $o; done"`. Append to `ALLOWED_READONLY`, under `# TICKET-153`: `"git branch"`, `"git branch -a"`, `"git branch -vv"`, `"git branch --list 'ticket/*'"`, `"git branch --show-current"`, `"git branch --contains HEAD"`, `"git remote -v"`, `"git remote get-url origin"`, `"git remote show origin"`, `"git worktree list --porcelain"`, `"git log -c -1"`, `"git grep -n foo"`, `"git log --oneline --output-indicator-new=+ -1"`, `"git diff --no-ext-diff HEAD"`. Set the `CLAUDE.md` line 107 count to what `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (238 + 35 = 273 at plan time). Commit `fix(TICKET-153): refuse git options and forms that write or run a command in a read-only stage`.
6. Judge `uv run` and `poetry run` by the command they run, in `pipeline/hooks/dangerous-commands.py`: change the first `GUARDED` line from `"python": {"-m"}, "python3": {"-m"}, "uv": {"run"}, "poetry": {"run"},` to `"python": {"-m"}, "python3": {"-m"},`, add the constant and function below after `git_verdict()`, replace the four lines in `readonly_rules()` shown below, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`.
   ```python
   # The `uv run` and `poetry run` options a read-only stage may pass before the
   # command: (flags, options taking a value). An allowlist: --with installs a
   # package, --python runs the interpreter it names, and --directory, --project,
   # --script, -m and --env-file are refused with them.
   RUN_WRAPPERS = {
       "uv": ({"--frozen", "--locked", "--offline", "--no-sync", "--all-extras",
               "--all-groups", "--no-dev", "--quiet", "-q"},
              {"--group", "--extra", "--only-group", "--no-group", "--package"}),
       "poetry": (set(), set()),
   }


   def unwrap_run(argv: list[str]) -> tuple[list[str] | None, str | None]:
       """`(command, None)`: the command a chain of `uv run`/`poetry run`
       wrappers runs, with their allowlisted options stripped -- `argv` itself
       when it is not one. `(None, reason)` when a wrapper option is not in
       RUN_WRAPPERS or no command follows."""
       while os.path.basename(argv[0]) in RUN_WRAPPERS and argv[1:2] == ["run"]:
           name = os.path.basename(argv[0])
           flags, valued = RUN_WRAPPERS[name]
           rest, i = argv[2:], 0
           while i < len(rest) and rest[i].startswith("-"):
               opt, eq, _ = rest[i].partition("=")
               if rest[i] in flags:
                   i += 1
               elif opt in valued:
                   i += 1 if eq else 2
               else:
                   return None, (f"{name} run {opt}: not a read-only {name} run option "
                                 "-- --with installs a package and --python runs the "
                                 "interpreter it names")
           if i >= len(rest):
               return None, f"{name} run: names no command to run"
           argv = rest[i:]
       return argv, None
   ```
   In `readonly_rules()` these four lines:
   ```python
           if any(argv[:len(p)] == p for p in allow):
               continue
           name = os.path.basename(argv[0])
           args = argv[1:]
   ```
   become:
   ```python
           if any(argv[:len(p)] == p for p in allow):
               continue
           # `uv run` and `poetry run` are judged by the command they run, so
           # `uv run find . -delete` meets the rules bare `find` meets, and a
           # project prefix matches that command too (TICKET-153)
           inner, why = unwrap_run(argv)
           if why:
               return why
           if inner is not argv and any(inner[:len(p)] == p for p in allow):
               continue
           name = os.path.basename(inner[0])
           args = inner[1:]
   ```
   Append to `BLOCKED_READONLY`, under `# TICKET-153: uv run and poetry run meet the rules of the command they run`: `"uv run rm /tmp/x"`, `"uv run python -c 1"`, `"uv run find . -name x -delete"`, `"uv run --with x pytest"`, `"uv run --python ./p.sh pytest"`, `"uv run --directory /tmp pytest"`, `"uv run uv run rm x"`, `"uv run"`, `"uv run --group dev"`, `"poetry run touch /tmp/x"`, `"poetry run -C /tmp pytest"`, `"uv sync"`, `"uv run -m pytest"`. Append to `ALLOWED_READONLY`, under `# TICKET-153`: `"uv run --group dev pytest -x tests/test_fence.py"`, `"uv run --group=dev --frozen pytest -q"`, `"uv run rg x"`, `"uv run python -m pytest -q"`, `"poetry run pytest -x"`, `"uv run --no-sync git log --oneline"`, `"uv run uv run pytest"`. Append `"uv run pipeline ls"` to `ALLOWED_PROJECT` and `"uv run --with x pipeline ls"` to `BLOCKED_PROJECT`. Set the `CLAUDE.md` line 107 count to what `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (273 + 22 = 295 at plan time). Commit `fix(TICKET-153): judge uv run and poetry run by the command they run in a read-only stage`.
7. Allow npm, pnpm and yarn only a bare `test` or `run test`, with no argument, in `pipeline/hooks/dangerous-commands.py`: delete the `GUARDED` line `"npm": {"test", "run"}, "pnpm": {"test", "run"}, "yarn": {"test", "run"},`, add the function below after `unwrap_run()`, add the branch below to `readonly_rules()` directly before the `if name in OPTION_SPECS:` branch, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`.
   ```python
   def runs_the_test_script(args: list[str]) -> bool:
       """True for exactly npm/pnpm/yarn `test` or `run test`, with no argument.
       An option is npm config (`npm test --script-shell=./p.sh` ran p.sh, npm
       12.0.2), and an argument after `--` reaches the test tool unchecked
       (jest --outputFile, pytest --junit-xml), as `cargo test --` would."""
       return args in (["test"], ["run", "test"])
   ```
   Branch in `readonly_rules()`:
   ```python
           if name in ("npm", "pnpm", "yarn"):
               if runs_the_test_script(args):
                   continue
               return (f"{name}: only a bare `{name} test` or `{name} run test` is "
                       "read-only -- another script is package.json text the guard "
                       "cannot judge, an option is npm config such as --script-shell, "
                       "which runs a command, and an argument after `--` reaches the "
                       "test tool unchecked")
   ```
   Append to `BLOCKED_READONLY`, under `# TICKET-153: npm, pnpm and yarn run only the test script`: `"npm run deploy"`, `"pnpm run build"`, `"yarn run eslint --fix"`, `"npm test --script-shell=./p.sh"`, `"npm run test --script-shell ./p.sh"`, `"npm run-script test"`, `"yarn eslint"`, `"npm test -- --runInBand"`. Append to `ALLOWED_READONLY`, under `# TICKET-153`: `"npm test"`, `"npm run test"`, `"pnpm test"`, `"yarn test"`, `"yarn run test"`. Set the `CLAUDE.md` line 107 count to what `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (295 + 13 = 308 at plan time). Commit `fix(TICKET-153): allow npm, pnpm and yarn only the test script in a read-only stage`.
8. Narrow make, cargo and go by option in `pipeline/hooks/dangerous-commands.py`: add the constants and function below after `runs_the_test_script()`, replace the `continue` that ends the `if name in GUARDED:` block in `readonly_rules()` (the line after `return f"{name} {args[0] if args else ''}: not an allowed subcommand"`) with the lines below, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`.
   ```python
   # What may follow `<tool> <subcommand>` for a GUARDED build tool, in the
   # OPTION_SPECS shape; a `"<tool> <subcommand>"` key wins over `"<tool>"`.
   # Left out on purpose, each measured or documented to write outside the
   # worktree or run a command: make VAR=value, --eval, -f and -C; cargo
   # --config, --target-dir, --manifest-path and -Z; go -exec, -toolexec,
   # -vettool, -o, -c, -args, -ldflags, -gcflags and every -*profile.
   GUARDED_SPECS = {
       "make": ("ks", "j", {"--keep-going", "--silent", "--quiet"}, {"--jobs"}, 0),
       "cargo": ("qvr", "pjF",
                 {"--workspace", "--all", "--lib", "--bins", "--tests", "--examples",
                  "--benches", "--all-targets", "--doc", "--release", "--no-run",
                  "--no-fail-fast", "--all-features", "--no-default-features",
                  "--locked", "--frozen", "--offline", "--quiet", "--verbose",
                  "--keep-going"},
                 {"--package", "--exclude", "--bin", "--test", "--example", "--bench",
                  "--features", "--jobs", "--target", "--profile", "--message-format",
                  "--color"}, None),
       "cargo fmt": ("", "p", {"--check", "--all"}, {"--package"}, 0),
       "go": ("", "",
              {"-v", "-short", "-race", "-failfast", "-cover", "-json", "-benchmem",
               "-trimpath", "-fullpath"},
              {"-run", "-skip", "-count", "-timeout", "-bench", "-benchtime", "-cpu",
               "-parallel", "-p", "-tags", "-shuffle", "-covermode", "-coverpkg",
               "-list"}, None),
   }
   # What may follow `--`: the libtest flags after `cargo test` (--logfile wrote
   # a file, cargo 1.98.1), lint levels after `cargo clippy`. Nothing else may.
   CARGO_TAIL = {
       "test": ("q", "",
                {"--nocapture", "--no-capture", "--exact", "--ignored",
                 "--include-ignored", "--show-output", "--quiet", "--list"},
                {"--test-threads", "--skip", "--color", "--format"}, None),
       "clippy": ("", "DWAF", set(), {"--deny", "--warn", "--allow", "--forbid"}, 0),
   }


   def guarded_options(name: str, sub: str, args: list[str]) -> str | None:
       """None when every argument after `<name> <sub>` is in GUARDED_SPECS, and
       after `cargo test --`/`cargo clippy --` in CARGO_TAIL. `cargo fmt` must
       carry `--check`, or it rewrites source files."""
       key = f"{name} {sub}"
       spec = GUARDED_SPECS.get(key, GUARDED_SPECS[name])
       tail_spec = CARGO_TAIL.get(sub) if name == "cargo" else None
       head, tail = args, []
       if "--" in args:
           if tail_spec is None:
               return f"{key} --: passes arguments the guard cannot judge"
           head, tail = args[:args.index("--")], args[args.index("--") + 1:]
       why = (options_verdict(key, head, spec)
              or tail and options_verdict(f"{key} --", tail, tail_spec))
       if why:
           return why
       if key == "cargo fmt" and "--check" not in head:
           return "cargo fmt: only `cargo fmt --check` is read-only; without it cargo fmt rewrites source files"
       return None
   ```
   The `continue` that ends the `GUARDED` block becomes:
   ```python
               why = guarded_options(name, args[0], args[1:])
               if why:
                   return why
               continue
   ```
   Append to `BLOCKED_READONLY`, under `# TICKET-153: make, cargo and go options that write outside the worktree or run a command`: `"make test SHELL=./p.sh"`, `"make test --eval=x"`, `"make -C /tmp test"`, `"make test install"`, `"cargo test --config build.rustc-wrapper=./p.sh"`, `"cargo build --target-dir /tmp/t"`, `"cargo test -- --logfile /tmp/l"`, `"cargo fmt"`, `"cargo clippy --fix"`, `"cargo clippy -- -C linker=./p.sh"`, `"go test -exec ./p.sh ./..."`, `"go vet -vettool=./p.sh ./..."`, `"go test -c -o /tmp/x ."`, `"go test -coverprofile=/tmp/c ./..."`, `"go build -ldflags=-extld=./p.sh ."`, `"go test ./... -args -test.coverprofile=/tmp/c"`, `"uv run cargo build --target-dir /tmp/t"`. Append to `ALLOWED_READONLY`, under `# TICKET-153`: `"make check -k"`, `"make lint -j4"`, `"make test -j 4"`, `"cargo test -p foo --release"`, `"cargo test my_test -- --nocapture --test-threads 1"`, `"cargo clippy --all-targets -- -D warnings"`, `"cargo fmt --check"`, `"go test -run TestX -count=1 ./..."`, `"go test ./... -v -race"`, `"go vet ./..."`. Keep the existing `"cargo test"` and `"go test ./..."` cases. Set the `CLAUDE.md` line 107 count to what `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (308 + 27 = 335 at plan time). Commit `fix(TICKET-153): narrow make, cargo and go by option in a read-only stage`.
9. Narrow the test runners and `python -m` by option in `pipeline/hooks/dangerous-commands.py`: add the four entries below to the `OPTION_SPECS` literal and the `py.test` line directly after it, add `pytest --junit-xml/--basetemp/--log-file/--debug/-o/-p/--rootdir` to the write-or-exec list in the comment above `OPTION_SPECS`, delete the line `TEST_RUNNERS = {"pytest", "py.test", "tox", "nox", "unittest"}`, change `if name in READ_TOOLS or name in TEST_RUNNERS:` in `readonly_rules()` to `if name in READ_TOOLS:`, replace the `continue` after the `python`/`python3` check with the lines below, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`.
   ```python
       "pytest": ("xqvsl", "kmr",
                  {"--exitfirst", "--quiet", "--verbose", "--showlocals",
                   "--no-showlocals", "--lf", "--last-failed", "--ff", "--failed-first",
                   "--nf", "--new-first", "--sw", "--stepwise", "--co", "--collect-only",
                   "--no-header", "--no-summary", "--strict-markers", "--runxfail",
                   "--full-trace", "--setup-show", "--fixtures", "--markers",
                   "--disable-warnings", "--version", "--help"},
                  {"--maxfail", "--deselect", "--durations", "--tb", "--capture",
                   "--color", "--ignore", "--ignore-glob", "--import-mode",
                   "--report-chars", "--verbosity"}, None),
       "unittest": ("vqfcb", "kspt",
                    {"--verbose", "--quiet", "--failfast", "--catch", "--buffer",
                     "--locals"},
                    {"--start-directory", "--pattern", "--top-level-directory"}, None),
       "tox": ("qv", "e", {"--quiet", "--verbose"}, set(), 0),
       "nox": ("", "se", set(), {"--session", "--sessions"}, 0),
   ```
   Directly after the closing `}` of `OPTION_SPECS`:
   ```python
   OPTION_SPECS["py.test"] = OPTION_SPECS["pytest"]
   ```
   In the `if name in ("python", "python3"):` block, the `continue` directly after the `PY_MODULES_OK` refusal becomes:
   ```python
                   why = options_verdict(f"{name} -m {args[1]}", args[2:], OPTION_SPECS[args[1]])
                   if why:
                       return why
                   continue
   ```
   Append to `BLOCKED_READONLY`, under `# TICKET-153: test runner options that write outside the worktree or load code`: `"pytest --junit-xml=/tmp/x"`, `"pytest --basetemp=/tmp/b"`, `"pytest -p evil"`, `"pytest -o cache_dir=/tmp/c"`, `"pytest --log-file=/tmp/l"`, `"pytest --debug=/tmp/d"`, `"pytest --rootdir=/tmp"`, `"pytest --junit=/tmp/x"`, `"python3 -m pytest --junit-xml=/tmp/x"`, `"py.test --junitxml=/tmp/x"`, `"uv run --group dev pytest --junit-xml=/tmp/x"`, `"tox -e py -- --junit-xml=/tmp/x"`, `"tox --workdir /tmp"`, `"nox -f /tmp/n.py"`, `"python3 -m unittest --junk"`. Append to `ALLOWED_READONLY`, under `# TICKET-153`: `"pytest -q tests/test_fence.py::t -k foo --tb=short"`, `"pytest --lf -rA"`, `"python3 -m unittest -v tests.test_x"`, `"tox -e py"`, `"nox -s tests"`, `"py.test -x"`. Keep the existing `"pytest -x"`, `"pytest -x 2>&1"`, `"python3 -m pytest --deselect x"` and `"python3 -m unittest"` cases. Set the `CLAUDE.md` line 107 count to what `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (335 + 21 = 356 at plan time). Commit `fix(TICKET-153): narrow pytest, unittest, tox and nox by option in a read-only stage`.
10. Document the narrowed allowlist in `README.md`: insert the paragraph below directly after the paragraph whose first words are "The built-in rules also accept a" (line 879), before `## MCP servers`, as one line. Commit `docs(TICKET-153): document the argument checks of the read-only allowlist`.
   ```markdown
   In a read-only stage the built-in allowlist checks arguments, not only the program name. `find`, `awk`, `sort`, `uniq`, `rg`, `file`, `pytest`, `python -m unittest`, `tox`, `nox`, `make`, `cargo` and `go` accept only the options listed for them in `pipeline/hooks/dangerous-commands.py`, and that list leaves out every option that writes a file or runs a command. `git` runs its read subcommands without `--output`, `--open-files-in-pager` (or `git grep -O`), `--ext-diff`, `--exec-path`, `--config-env` or a global `-c`, and `git branch`, `git remote` and `git worktree` only in their listing forms. `uv run` and `poetry run` are judged by the command they run, after a short list of their own options (`--group`, `--extra`, `--frozen`, `--locked`, `--offline`, `--no-sync`). `npm`, `pnpm` and `yarn` run only the `test` script, as a bare `npm test` or `npm run test` with no argument: any other `run <script>` is refused, because a package.json script is text the guard cannot judge, and so is an argument after `--`, because it reaches the test tool unchecked. `ag`, `tree` and `yq` are not allowed. An `[readonly] allow` entry matches the command as written and also the command a `uv run` or `poetry run` runs; add the exact argv prefix of a refused form there when a stage needs it.
   ```

## Acceptance criteria

- `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` passes: `uv run --group dev pytest -q tests/test_fence.py` exits 0 (step 1)
- `uv run --group dev pytest -q tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` exits 0 (step 1)
- `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` passes: `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py` exits 0 (steps 2, 3)
- `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` passes with every case steps 2-9 add in the tables: `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` exits 0 (steps 2-9)
- `python3 -c "import importlib.util as u; s=u.spec_from_file_location('g','pipeline/hooks/dangerous-commands.py'); m=u.module_from_spec(s); s.loader.exec_module(m); print(sorted({'ag','tree','yq','sort','uniq','rg','file','find','awk'} & m.READ_TOOLS))"` prints `[]` (step 4)
- `python3 -c "import importlib.util as u; s=u.spec_from_file_location('g','pipeline/hooks/dangerous-commands.py'); m=u.module_from_spec(s); s.loader.exec_module(m); print(sorted(set(m.GUARDED) - {'python','python3'} - set(m.GUARDED_SPECS)), hasattr(m, 'TEST_RUNNERS'), hasattr(m, 'GIT_WORKTREE_READ'))"` prints `[] False False` (steps 5, 6, 7, 8, 9)
- `uv run --group dev pytest -q tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` exits 0 (steps 2-9)
- `./pipeline/hooks/test_dangerous_commands.py` prints `guard: all passed` and no `FAIL` line (steps 2-9)
- `grep -c "a package.json script is text the guard cannot judge" README.md` prints `1` (step 10)
- `uv run --group dev pytest -q` reports no failures. Measured baseline on 33be0fb: `2 failed, 761 passed`, the two being this ticket's repro tests (steps 1-10)

## Decisions

supersedes: DEC-106 -- its awk paragraph says the guard must not read awk program text; TICKET-153 narrows awk by its program, with an allowlisted option set and a closed list of awk's write and exec routes. Every other DEC-106 rule is restated below and still binds.

- **Every branch of `readonly_rules()` judges arguments, not only the program name.** The operator chose this scope on 2026-10-02 07:59:04Z: "every readonly_rules() branch". A new allowlisted program gets an argument check in the same change, or stays off the allowlist.
- **A `READ_TOOLS` member must have no argument that writes a file or runs a command.** TICKET-153 audited every member with `--help`. A tool with such an option leaves the set and gets an argument allowlist (`find_only_reads()`, `awk_only_reads()`, `OPTION_SPECS`), or leaves the allowlist entirely (`ag`, `tree`, `yq`). Run the new tool's `--help` before adding it.
- **`OPTION_SPECS` and `GUARDED_SPECS` are allowlists of options, never lists of dangerous ones.** `operands()` refuses any option not named, including GNU long-option abbreviations (`sort --out=x`). Add an option only after reading its `--help` line. Never add `sort -o/-T/--compress-program`, `rg --pre/--hostname-bin/-z`, `file -C/-m`, `pytest --junit-xml/--basetemp/--log-file/--debug/-o/-p/--rootdir`, `make -f/-C/--eval/-E` or a `VAR=value` operand, `cargo --config/--target-dir/--manifest-path/-Z`, or `go -exec/-toolexec/-vettool/-o/-c/-args/-ldflags/-gcflags/-*profile`. `uniq` takes at most one operand, because its second is an output file. `make` takes no operand after its target. `cargo fmt` needs `--check`. Only `cargo test` and `cargo clippy` accept `--`, judged by `CARGO_TAIL`; libtest `--logfile` stays out. `sort` may still spill temporary files to `$TMPDIR` on large input; that is accepted.
- **git is the one written exception to invariant 4, approved by the operator on 2026-10-02.** The subcommand stays an allowlist (`GIT_READ`). Inside it, `git_verdict()` refuses only the options known to write or run a command: `GIT_REFUSED` in any prefix (git grep accepted `--open-files=` for `--open-files-in-pager`), a global `-c`, and `git grep -O`. A full per-subcommand option allowlist was rejected because it refuses reads agents use in `git log`. `branch`, `remote` and `worktree` are allowlisted by form: listing, `remote show`/`get-url`, and `worktree list` as the first word. Extend `GIT_REFUSED` when a new git option writes or runs a command; do not extend the exception to another tool without a human's decision.
- **`uv run` and `poetry run` are judged by the command they run.** `unwrap_run()` strips a chain of wrappers and their `RUN_WRAPPERS` options, then the inner command meets every rule a bare command meets. Never add `--with`, `--python`, `--directory`, `--project`, `--script`, `-m` or `--env-file`: each installs, runs or relocates code. A `[readonly] allow` prefix matches the outer command and the inner one.
- **npm, pnpm and yarn run only a bare `test` or `run test`, with no argument.** A package.json script is text the guard cannot judge. An option is npm config: `--script-shell` ran a command (npm 12.0.2). An argument after `--` reaches the test tool unchecked (jest `--outputFile`, pytest `--junit-xml`), the same route refused for `cargo test --`, `go test -args` and `tox --`; the operator chose no arguments on 2026-10-02 08:30:18Z. Do not re-admit `--` without a per-tool spec like `CARGO_TAIL`.
- **`awk` is narrowed by argument, not trusted by name.** `awk_only_reads()` accepts only `-F` and `-v` options, a program that `AWK_UNSAFE` does not match, and operands not starting with `-`. awk's routes to a file or command are a closed set in the language: `>`/`>>`, `|`/`|&`, `system()`, and gawk's `@` (`@load`, `@include`, indirect `@f()` reaching `system`, measured on gawk 5.4.1). `>=` is a comparison (gawk 5.4.1 printed `0` and wrote no file for `print 1 >= "x"`), so `NR>=40` stays allowed. The cost is accepted: `awk 'NR>1'`, `||` and `"->"` are refused; the reason string says `write NR>1 as NR>=2`. Do not widen `AWK_UNSAFE` to tell a `>` comparison from a redirect by parsing awk.
- **`find` is an allowlist of primaries.** `find_only_reads()` admits only `FIND_FLAG` and `FIND_ARG` primaries; each `FIND_ARG` primary consumes one token, so `-mtime -7` works and `-name -delete` is a harmless pattern (GNU find measured). `find -exec grep ...` is refused; use `grep -r`. Never add `-exec`, `-ok` or any `-f*` output primary to either set.
- **Carried from DEC-106, unchanged:** the redirection rule judges shlex tokens, never the raw string; a `>&` token is a duplication only before an all-digit token; `split_segments()` keeps a `>` welded to a newline, so `cat a >` + newline + `file` stays refused (`file` is no longer in `READ_TOOLS`, but the appended `>` is what refuses it); `VERBOSE` in the guard's test file is `True` only under `__main__`; `grep '>' f` is refused as the accepted cost; the `sed` rule is one shape, `sed -n <line/range>p <file>...`, read through `SED_PRINT.fullmatch`; the human merge gate re-runs the invariant-4 live check (`git worktree remove foo` answers `Blocked by the pipeline guard` under `--setting-sources project` and `--disable-slash-commands`).
- **FENCED names every `SAFE_*` pattern that checks a ticket or sidecar value.** A new module-level pattern in `pipeline/core/ticket.py` that checks hostile input needs its own FENCED entry and its backticked `CLAUDE.md` mention; editing `validate_meta()` to use it trips the fence once, but later edits to the pattern alone do not.

## Rollback

Revert the step commits on main with `git revert`, newest first. Step 1 is independent of the rest. Steps 2-9 share the `CLAUDE.md` guard case count and the `READ_TOOLS`/`GUARDED` literals; steps 5, 8 and 9 call `operands()` from step 4, and step 8 depends on step 7 having removed npm/pnpm/yarn from `GUARDED`. Step 10 is prose only.

Riskiest step: step 9, because it narrows `pytest`, the command read-only stages in this repo run most, and an option missing from `OPTION_SPECS["pytest"]` refuses a test run a stage needs today. Steps 4 (`rg`, `sort`, `uniq`) and 6 (`uv run`) carry the same risk. Fallback when a step's check goes red: narrow, never widen.
1. A BLOCKED case passes: remove the option from its spec, or tighten `operands()`, `git_verdict()` or `unwrap_run()`, until it blocks.
2. An ALLOWED case fails: add only that exact option, after its `--help` line shows it neither writes a file nor runs a command.
3. The option does write or run a command: the result is `blocked`; report the case in `## Thread`.
Never loosen `AWK_UNSAFE`, `GIT_REFUSED` or `RUN_WRAPPERS` to make a case pass. If a step ships and refuses a command a stage needs, a project adds an exact `[readonly] allow` prefix for it; reverting step 9 restores unchecked test runners, and reverting step 6 restores the unchecked `uv run`.

## Thread

### 2026-10-02 07:28:27Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-10-02 triage · finding

Reproduced both holes. Verdict `ok`, not `chore`: the fix needs a design choice (narrow `find`/`awk` by argument, or a guarded form), so planning decides. Expected files: `pipeline/core/machine.py` (FENCED entry for the `SAFE_*` patterns), `pipeline/hooks/dangerous-commands.py`, `pipeline/hooks/test_dangerous_commands.py`, `tests/test_fence.py`, `CLAUDE.md`.
My guard test drives the real hook. The implementer still adds the `BLOCKED_READONLY` and `ALLOWED_READONLY` table cases.

### 2026-10-02 07:29:25Z · triage · session · session=df7ec816-bb15-457d-8155-949eef895e88

`triage` ran as session `df7ec816-bb15-457d-8155-949eef895e88`
- replay: `claude --resume df7ec816-bb15-457d-8155-949eef895e88`
- log: `.project/logs/TICKET-153-triage-df7ec816.log`
- cost: $0.30 of a $3 cap
- tokens: 5,890 out (216 thinking) · 28 in · 467,494 cache read · 37,122 cache write

### 2026-10-02 07:29:25Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced both holes with two failing tests, committed 33be0fb

### 2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpouwquf4z'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
```
ind . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-153/.venv/bin/python', '/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-153/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpue37g_mh'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-3gqllc_7/base
      Built pipeline @ file:///tmp/pipeline-base-3gqllc_7/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 99ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-3gqllc_7/base/.venv/bin/python', '/tmp/pipeline-base-3gqllc_7/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding
- `files_declared` is empty
- plan step names no declared file: '1. Fence the six `SAFE_*` patterns: in `pipeline/core/machine.py` replace the FENCED line `"pipeline/core/ticket.py": ("validate_meta",),` with the block below, and in `CLAUDE.md` (line 504) extend the fence sentence; then run `tests/test_fence.py` and the drift test. In `CLAUDE.md` change `` `transition()`, `validate_meta()`, `CONTROL_FIELDS`, `` to `` `transition()`, `validate_meta()` and the patterns it applies (`SAFE_ID`, `SAFE_BRANCH`, `SAFE_TEST`, `SAFE_FILE`, `SAFE_HASH`, `SAFE_DEC_ID`), `CONTROL_FIELDS`, `` and rewrap the paragraph so no backticked token splits across lines. Commit `fix(TICKET-153): fence the SAFE_* patterns validate_meta applies`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Narrow `find` by argument in `pipeline/hooks/dangerous-commands.py`: remove `"find"` from `READ_TOOLS`, add the constants and function below after `sed_is_a_line_print()`, add the branch below to `readonly_rules()` directly after the `if name == "sed":` block, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`. Branch in `readonly_rules()`: Append to `BLOCKED_READONLY`, under a `# TICKET-153: find writes or runs a command` comment: `"find . -name x -delete"`, `"find . -exec rm {} ;"`, `"find . -execdir rm {} +"`, `"find . -ok rm {} ;"`, `"find . -okdir rm {} ;"`, `"find . -fprint /tmp/out"`, `"find . -fprint0 /tmp/out"`, `"find . -fprintf /tmp/out %p"`, `"find . -fls /tmp/out"`, `"for f in -delete; do find . $f; done"`. Append to `ALLOWED_READONLY`, under `# TICKET-153`: `"find . -type f -mtime -7"`, `"find -L . -maxdepth 2 -size -10k -print"`, `"find . -path ./node_modules -prune -o -name \'*.js\' -print"`. Set the `# <N> guard cases (table-driven)` number in `CLAUDE.md` line 107 to the count `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (188 + 13 = 201 at plan time). Commit `fix(TICKET-153): refuse a find that writes or runs a command in a read-only stage`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. Narrow `awk` by argument in `pipeline/hooks/dangerous-commands.py`: remove `"awk"` from `READ_TOOLS`, add the constant and function below after `find_only_reads()`, add the branch below to `readonly_rules()` directly after the `find` branch, and add the table cases below to `pipeline/hooks/test_dangerous_commands.py`. Branch in `readonly_rules()`: Append to `BLOCKED_READONLY`, under `# TICKET-153: awk writes or runs a command`: `"awk \'BEGIN{system(\\"touch /tmp/x\\")}\'"`, `"awk \'{print $1 > \\"out\\"}\' f"`, `"awk \'{print $1 >> \\"out\\"}\' f"`, `"awk \'{print $1 | \\"sh\\"}\' f"`, `"awk \'BEGIN{\\"date\\" | getline d}\'"`, `"awk \'BEGIN{x=\\"system\\"; @x(\\"touch /tmp/x\\")}\'"`, `"awk -f prog.awk f"`, `"awk -i inplace \'{print}\' f"`. Append to `ALLOWED_READONLY`: `"awk \'{print $1}\' f"`, `"awk -F: \'{print $1}\' /etc/passwd"`, `"awk -F , -v n=3 \'NR==n{print $2}\' f.csv"`. Keep the existing `"awk \'NR>=40 && NR<=70\' f.rs"` case. Set the `CLAUDE.md` line 107 count to what `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports (201 + 11 = 212 at plan time). Commit `fix(TICKET-153): refuse an awk program that writes or runs a command in a read-only stage`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-10-02 planning · finding

Plan written: three steps. Step 1 adds the six `SAFE_*` names to the `pipeline/core/ticket.py` FENCED tuple and the `CLAUDE.md` fence sentence. Steps 2 and 3 take `find` and `awk` off `READ_TOOLS` and allow each only in an allowlisted argument shape, modelled on `sed_is_a_line_print()`.

The plan supersedes DEC-106. Its awk paragraph forbids reading awk program text; the ticket requires it. `## Decisions` restates every other DEC-106 rule.

Evidence measured in this worktree:
1. gawk 5.4.1: `print 1 >= "x"` printed `0` and wrote no file; `@x("echo indirect-ran")` with `x="system"` printed `indirect-ran`.
2. GNU find: `-name -delete` deleted nothing.
3. Baseline at 33be0fb: `2 failed, 761 passed` (this ticket's two repro tests).

The 07:38:44Z gate FAIL above holds only the two findings expected before dispatch: `files_declared` empty, and steps naming files the result declares.

Outside scope: the `pipeline/core/fence.py` docstring and `tests/test_machine.py:59` say FENCED holds "nine things"; it holds ten before this ticket. Accepted cost: `awk 'NR>1'` and `find -exec grep` become refused in read-only stages.

### 2026-10-02 07:39:20Z · planning · session · session=ff59a8b0-ce05-445f-a1ee-0ea6c3a56a5b

`planning` ran as session `ff59a8b0-ce05-445f-a1ee-0ea6c3a56a5b`
- replay: `claude --resume ff59a8b0-ce05-445f-a1ee-0ea6c3a56a5b`
- log: `.project/logs/TICKET-153-planning-ff59a8b0.log`
- cost: $2.06 of a $10 cap
- tokens: 41,263 out (24,883 thinking) · 56 in · 2,061,679 cache read · 102,398 cache write

### 2026-10-02 07:39:20Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ 3-step plan: fence the six SAFE_* patterns, and narrow find and awk by argument; supersedes DEC-106's awk paragraph

### 2026-10-02 07:40:44Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpfey12pth'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmptferx1f1'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-gvxcj8oa/base
      Built pipeline @ file:///tmp/pipeline-base-gvxcj8oa/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 64ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-gvxcj8oa/base/.venv/bin/python', '/tmp/pipeline-base-gvxcj8oa/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding

### 2026-10-02 plan-validation · finding

**FAIL: same-root-cause gap in part 2.** `readonly_rules()` runs `if name in READ_TOOLS or name in TEST_RUNNERS: continue` (`pipeline/hooks/dangerous-commands.py:506`), with no argument check. After the plan, `READ_TOOLS` still holds three tools that write a file or run a command by argument. Measured on this machine:
1. `sort` (GNU coreutils 9.11): `--help` lists `-o, --output=FILE` and `--compress-program=PROG`.
2. `uniq`: `Usage: uniq [OPTION]... [INPUT [OUTPUT]]` -- "writing to OUTPUT".
3. `rg` (ripgrep 15.2.0): `--pre=COMMAND`.

None is a shell redirection token, so `sort -o /tmp/out f`, `uniq f /tmp/out` and `rg --pre ./x pat .` pass the guard. They hit the hole the ticket names: a write or exec outside the worktree.

long: per-item scores
- Root cause: pass. Part 1 -- FENCED fences the function body, not the module-level patterns it reads. Part 2 -- the gap above.
- Decisions: pass. Supersedes DEC-106 with reasons and restates its other rules.
- Scope: pass. Every step traces to a criterion.
- Falsifiable: pass. Each BLOCKED case returns exit 0 on 33be0fb.
- No research left: pass.
- Riskiest step: pass. Step 3, with a fallback stated.
- Regression: pass. `find . -name '*.py'` (:142) and `awk 'NR>=40 && NR<=70' f.rs` (:150) still fit the new shapes.
- Blast radius: pass.

Note: `SAFE_DEC_ID` is not read by `validate_meta()` (it guards `supersedes:`), so the step 1 comment overstates. Fencing it is harmless.

Suggested new ticket: `GIT_READ` admits `git diff --output=<file>`/`git log --output=<file>` (a write) and `git branch <name>` (creates a ref), checking only the subcommand.

### 2026-10-02 07:42:46Z · plan-validation · session · session=d3465aee-5c2b-4399-b77a-a1660fb723f8

`plan-validation` ran as session `d3465aee-5c2b-4399-b77a-a1660fb723f8`
- replay: `claude --resume d3465aee-5c2b-4399-b77a-a1660fb723f8`
- log: `.project/logs/TICKET-153-plan-validation-d3465aee.log`
- cost: $0.83 of a $3 cap
- tokens: 11,394 out (4,424 thinking) · 28 in · 704,267 cache read · 57,796 cache write

### 2026-10-02 07:42:46Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ same-root-cause gap: READ_TOOLS still admits sort (-o, --compress-program), uniq (OUTPUT operand) and rg (--pre) with no argument check; the plan narrows only find and awk

### 2026-10-02 07:51:27Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpu1hzhq2r'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpy_7yhmgo'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-am8emgpi/base
      Built pipeline @ file:///tmp/pipeline-base-am8emgpi/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 86ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-am8emgpi/base/.venv/bin/python', '/tmp/pipeline-base-am8emgpi/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding

### 2026-10-02 planning · finding

Re-plan after the 07:42:46Z `bad-plan`: step 4 closes the `READ_TOOLS` gap. It narrows `sort`, `uniq`, `rg` and `file` through `OPTION_SPECS` and `operands()`, an option allowlist, and drops `ag`, `tree` and `yq`. Steps 1-3 are unchanged except the step 1 comment, which now says `SAFE_DEC_ID` is applied by `correct_decision()`, not `validate_meta()`.

Evidence, measured in a temp dir on this machine:
1. `sort -o out1 f` wrote `out1`; `uniq f out2` wrote `out2`; `rg --pre ./p.sh a f` ran `p.sh`; `file -C -m m` wrote `m.mgc`.
2. `ag`, `tree` and `yq` are not installed, so they leave `READ_TOOLS` rather than get an unmeasured allowlist.
3. A scratch copy of the guard with all four branches printed `bad 0 of 59` on the candidate cases and `existing readonly cases broken: [] of 113`.
4. `pipeline gate TICKET-153` printed `gate: PASS`.

Outside scope, for new tickets:
1. `date -s` sets the system clock from a read-only stage (needs root; no file, no command).
2. `GIT_READ` admits `git diff --output=<file>` and `git branch <name>`, as plan-validation noted.
3. The `pipeline/core/fence.py` docstring and `tests/test_machine.py:59` count FENCED entries as "nine".

### 2026-10-02 07:51:54Z · planning · session · session=80e47c89-b305-4824-927b-389c8c8bfcdd

`planning` ran as session `80e47c89-b305-4824-927b-389c8c8bfcdd`
- replay: `claude --resume 80e47c89-b305-4824-927b-389c8c8bfcdd`
- log: `.project/logs/TICKET-153-planning-80e47c89.log`
- cost: $2.08 of a $10 cap
- tokens: 40,047 out (11,981 thinking) · 64 in · 2,452,365 cache read · 98,019 cache write

### 2026-10-02 07:51:54Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ 4-step plan: fence the six SAFE_* patterns, narrow find and awk, and narrow sort/uniq/rg/file by option allowlist while dropping ag/tree/yq; closes the READ_TOOLS gap plan-validation found; supersedes DEC-106's awk paragraph

### 2026-10-02 07:53:19Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpekoek1ps'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpprsl7ho2'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-a7nm54t4/base
      Built pipeline @ file:///tmp/pipeline-base-a7nm54t4/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 87ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-a7nm54t4/base/.venv/bin/python', '/tmp/pipeline-base-a7nm54t4/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding

### 2026-10-02 plan-validation · finding

**FAIL: same-root-cause gap in part 2.** Root cause: `readonly_rules()` admits a command once its name or first word is allowlisted and never checks the rest of argv. The plan fixes this for `READ_TOOLS` only. Two sibling branches in the same function keep the defect:
1. `if name == "git":` (`pipeline/hooks/dangerous-commands.py:484`) checks only the subcommand. `git diff/log/show --output=<file>` writes a file; `git branch -D/-f/-m` and `git remote add/remove` write the main checkout's `.git`; `git grep --open-files-in-pager=<cmd>` and `git -c core.pager=<cmd> log` run a command.
2. `if name in GUARDED:` (:509) checks only `args[0]`, so `uv run <any command>` passes, as do `poetry`, `npm`, `pnpm` and `yarn` `run`.

Measured live in this read-only stage: `git diff --output=/dev/null HEAD` printed `git-exit=0`; `poetry run true` printed `(eval):1: command not found: poetry` (exit 127), so the guard admitted it. No decision record accepts either.

long: per-item scores
- Root cause: part 1 pass (`symbol_lines()` matches an `Assign`, `fence.py:41`); part 2 fail, above.
- Decisions: pass. DEC-106 superseded with reasons.
- Scope: pass. Falsifiable: pass. No research left: pass.
- Riskiest step: pass. Step 4, fallback stated.
- Regression: pass. Kept cases at test file :142-150.
- Blast radius: pass.

Note: the Digest says "Do not write a backticked `SAFE_*` there", but step 1 does. Step 1 is right: `tests/test_stages.py:414-417` compares against the new FENCED.
Not a gap: `as_test_list()` feeds both validation and the shell (`Ticket.tests`, `gate.py:854`).

### 2026-10-02 07:56:21Z · plan-validation · session · session=e86eff4b-796c-47fc-9098-7ab616a98931

`plan-validation` ran as session `e86eff4b-796c-47fc-9098-7ab616a98931`
- replay: `claude --resume e86eff4b-796c-47fc-9098-7ab616a98931`
- log: `.project/logs/TICKET-153-plan-validation-e86eff4b.log`
- cost: $1.14 of a $3 cap
- tokens: 16,885 out (9,087 thinking) · 38 in · 1,140,744 cache read · 72,374 cache write

### 2026-10-02 07:56:21Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ same-root-cause gap: readonly_rules() admits git by subcommand and uv/poetry/npm/pnpm/yarn by first word with no further argument check; git diff --output=/dev/null HEAD and poetry run true both passed the guard in this read-only stage. The plan narrows READ_TOOLS only

### 2026-10-02 planning · question

Plan-validation's last two runs disagree on scope. At 07:42 it suggested a new ticket for git; at 07:56 it failed the plan for leaving git and `GUARDED` out. `uv run find . -name x -delete` passes today, so `uv run` bypasses the find/awk fix. Research is in `## Digest`.

1. Scope. (a) Widen TICKET-153 to every `readonly_rules()` branch: git, `uv`/`poetry run`, and `npm`/`pnpm`/`yarn run`. (b) Keep TICKET-153 at `READ_TOOLS`, add `uv`/`poetry run`, and file git plus `npm`/`yarn` as a new ticket. (c) Keep the current plan; everything else goes in a new ticket.
   Default: (b). It closes the bypass that voids this ticket and keeps the fenced diff reviewable. (a) roughly doubles the guard diff. (b) and (c) need your answer quoted in the thread so plan-validation accepts the boundary.
2. `uv run` / `poetry run` design. (a) Allowlist the wrapper's options (`--group`, `--extra`, `--with`, `--frozen`, ...), then judge the inner argv through the same read-only rules. (b) Allow only a `TEST_RUNNERS` member or `python -m <PY_MODULES_OK>` after `run`.
   Default: (a). `uv run --group dev pytest` keeps working, and `uv run rg x` stays a read. (b) is smaller but refuses `uv run` for every non-test tool.
3. If git is in scope: (a) `branch`, `remote` and `worktree` accept listing forms only, and `diff`/`log`/`show`/`grep` refuse `--output`, `-O` and `--open-files-in-pager`. (b) A full option allowlist per subcommand.
   Default: (a). A full allowlist for `git log` would refuse many reads agents use. (a) needs a written exception to invariant 4 in `## Decisions`.

### 2026-10-02 07:58:25Z · planning · session · session=54af330e-76e3-4fb1-974a-a8eb422f714f

`planning` ran as session `54af330e-76e3-4fb1-974a-a8eb422f714f`
- replay: `claude --resume 54af330e-76e3-4fb1-974a-a8eb422f714f`
- log: `.project/logs/TICKET-153-planning-54af330e.log`
- cost: $0.84 of a $10 cap
- tokens: 10,840 out (6,063 thinking) · 22 in · 598,794 cache read · 62,665 cache write

### 2026-10-02 07:58:25Z · planning · transition · to=needs-input · result=needs-input · marker=yes

**planning -> needs-input** (result: `needs-input`)

✓ scope question: plan-validation now wants git and GUARDED (uv/poetry/npm run) narrowed too; an earlier validator called git a new ticket, so the operator decides scope and the uv-run and git designs

### 2026-10-02 07:59:04Z · human · answer

**answer from chezzijr**

Operator answers (quote these in the plan so plan-validation accepts the boundary):

1. Scope: (a). Widen TICKET-153 to every readonly_rules() branch -- READ_TOOLS (find/awk), git, and GUARDED (uv/poetry run, npm/pnpm/yarn run). One root cause, one ticket; the operator prefers one larger fenced diff over a follow-up ticket.

2. uv run / poetry run: (a). Allowlist the wrapper's own options, then judge the inner argv through the same read-only rules, so `uv run --group dev pytest` and `uv run rg x` keep working and `uv run find . -delete` is refused exactly like bare `find . -delete`. npm/pnpm/yarn `run <script>` runs arbitrary package.json script text the guard cannot judge: refuse `run <script>` in read-only stages except the `test` script (keep `npm test` / `npm run test`), and say so in the README.

3. git: (a). branch/remote/worktree accept listing forms only; diff/log/show/grep refuse --output, -O and --open-files-in-pager. Also refuse a global `-c` (and `--config-env`), `--ext-diff` and `--exec-path` on any git call, since each can run a command. Record the per-option refusals as a written exception to invariant 4 in ## Decisions: the subcommand is still allowlisted; only options known to write or exec are refused within it.

### 2026-10-02 08:21:03Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpib1d_z_p'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpg_hmwlkq'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-08l59rf7/base
      Built pipeline @ file:///tmp/pipeline-base-08l59rf7/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 77ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-08l59rf7/base/.venv/bin/python', '/tmp/pipeline-base-08l59rf7/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding
- plan step names no declared file: '10. Document the narrowed allowlist in `README.md`: insert the paragraph below directly after the paragraph that starts `The built-in rules also accept a `for x in WORDS; do ...; done` loop` (line 879), before `## MCP servers`, as one line. Commit `docs(TICKET-153): document the argument checks of the read-only allowlist`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-10-02 08:23:00Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpq39my8hx'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpkk393nda'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-iwxgpavv/base
      Built pipeline @ file:///tmp/pipeline-base-iwxgpavv/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 84ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-iwxgpavv/base/.venv/bin/python', '/tmp/pipeline-base-iwxgpavv/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding
- plan step names no declared file: '10. Document the narrowed allowlist in `README.md`: insert the paragraph below directly after the paragraph whose first words are "The built-in rules also accept a" (line 879), before `## MCP servers`, as one line. Commit `docs(TICKET-153): document the argument checks of the read-only allowlist`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-10-02 planning · finding

**Plan rewritten to the operator's 07:59:04Z scope: every `readonly_rules()` branch narrowed by argument.** Ten steps replace four. Steps 5-9 are new: git, `uv run`/`poetry run`, npm/pnpm/yarn, make/cargo/go, and the test runners plus `python -m`. Step 10 adds the README text the operator asked for.

make, cargo, go and pytest are in scope because "every readonly_rules() branch" covers them, and each has a measured hole: `make test SHELL=./mk.sh`, `go test -exec`, `cargo test -- --logfile` and `pytest --junit-xml` each ran a command or wrote outside the worktree (`## Digest` lists the evidence). They get option allowlists. Only git gets the refuse-known-options exception, as the operator approved. If the human wants the narrower reading, drop steps 8 and 9 and remove make, cargo, go, pytest, unittest, tox and nox from step 10's paragraph. No other step depends on steps 8 or 9.

Evidence: a scratch prototype of all ten steps printed `bad 0 of 131`, `guard: all passed`, and `16 passed in 1.51s` under pytest.

The gate's only remaining finding is `plan step names no declared file` for step 10 (`README.md`). It is the expected pre-adoption finding: `README.md` is in this run's `files_declared`.

### 2026-10-02 08:23:54Z · planning · session · session=b8a2d4cc-6dbd-46cb-9212-ad0d316467d3

`planning` ran as session `b8a2d4cc-6dbd-46cb-9212-ad0d316467d3`
- replay: `claude --resume b8a2d4cc-6dbd-46cb-9212-ad0d316467d3`
- log: `.project/logs/TICKET-153-planning-b8a2d4cc.log`
- cost: $5.94 of a $10 cap
- tokens: 126,880 out (63,871 thinking) · 108 in · 8,393,057 cache read · 215,767 cache write

### 2026-10-02 08:23:54Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned to the operator's scope: every readonly_rules() branch narrowed by argument -- find/awk/sort/uniq/rg/file, git (operator-approved option exception), uv/poetry run unwrapped, npm test only, make/cargo/go and pytest/unittest/tox/nox by option allowlist; prototype bad 0 of 131, scratch guard tests 16 passed

### 2026-10-02 08:25:17Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmps3cfr8rj'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmp53ykltwl'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-2fkpzuky/base
      Built pipeline @ file:///tmp/pipeline-base-2fkpzuky/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 69ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-2fkpzuky/base/.venv/bin/python', '/tmp/pipeline-base-2fkpzuky/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding

### 2026-10-02 · plan-validation · finding · verdict=FAIL

long: eight scored items plus one same-root-cause gap with its evidence.

**FAIL: step 7 lets an unchecked argument reach the test tool.** `runs_the_test_script()` returns True when `rest[:1] in ([], ["--"])`, so `npm test -- --outputFile=/tmp/x` (jest) and `npm test -- --junit-xml=/tmp/x` (a pytest test script) are allowed. `## Digest` measured that arguments after `--` reach the script. This is hole 7 (`pytest --junit-xml`) through another call site. The plan refuses the same form elsewhere: `cargo test -- --logfile`, `go test ./... -args ...`, `tox -e py -- --junit-xml=/tmp/x`, and `guarded_options()` returns "passes arguments the guard cannot judge". The operator's answer kept `npm test` / `npm run test`. It did not ask for script arguments. Fix: require `rest == []`, move `"npm test -- --runInBand"` to `BLOCKED_READONLY`, and drop "with arguments only after `--`" from step 10 and `## Decisions`.

Other items:
1. Root cause: pass. Part 1: FENCED names `validate_meta` but not the module-level patterns it applies; `symbol_lines()` handles assignments. Part 2: `readonly_rules()` trusts a program or subcommand by name.
2. Decisions: pass. DEC-106 superseded with reasons, its other rules restated; DEC-058/031/043 complied with.
3. Scope: pass. Steps 4-10 trace to the 07:59:04Z answer.
4. Criteria: pass. Tables and the `READ_TOOLS`/`GUARDED_SPECS` prints differ on a wrong implementation.
5. Research: pass.
6. Riskiest step: pass (step 9, fallback stated).
7. Regression: pass; `uv run --group dev pytest -x {test}` stays allowed.
8. Blast radius: pass; 5 files.

Unverified: I did not run npm; the jest/pytest writes rest on their documented options.

### 2026-10-02 08:29:01Z · plan-validation · session · session=89c534c6-91cb-4eee-aaea-113bbae624dd

`plan-validation` ran as session `89c534c6-91cb-4eee-aaea-113bbae624dd`
- replay: `claude --resume 89c534c6-91cb-4eee-aaea-113bbae624dd`
- log: `.project/logs/TICKET-153-plan-validation-89c534c6.log`
- cost: $1.23 of a $3 cap
- tokens: 20,819 out (15,737 thinking) · 26 in · 878,530 cache read · 79,346 cache write

### 2026-10-02 08:29:01Z · plan-validation · transition · to=escalated · result=bad-plan · marker=yes

**plan-validation -> escalated** (result: `bad-plan`)

✓ step 7 allows `npm test -- <any args>`, an unchecked argument route to the test tool (jest --outputFile, pytest --junit-xml) -- the same root cause the plan refuses for cargo test --, go -args and tox --; every other item passes

### 2026-10-02 08:30:18Z · human · note · by=chezzijr

**resumed** by chezzijr -> `planning`, reset [], granted `plan_validation_attempts` 3 -> 2

### 2026-10-02 08:30:18Z · human · answer · by=chezzijr

**note from chezzijr**

Only change: npm/pnpm/yarn test is allowed with NO arguments; refuse anything after test, including '--' and its args, like cargo test -- and tox --. Keep everything else in the plan as is.

### 2026-10-02 08:33:07Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpmmohaxrs'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpejn8ca2s'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-nf8xmrg4/base
      Built pipeline @ file:///tmp/pipeline-base-nf8xmrg4/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 78ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-nf8xmrg4/base/.venv/bin/python', '/tmp/pipeline-base-nf8xmrg4/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding

### 2026-10-02 · planning · replan

**Replanned step 7 only, per the operator's 08:30:18Z note.** npm, pnpm and yarn now accept exactly `test` or `run test`, with no argument.

1. Step 7: `runs_the_test_script()` becomes `return args in (["test"], ["run", "test"])`. Its refusal string names the `--` route. `"npm test -- --runInBand"` moves from `ALLOWED_READONLY` to `BLOCKED_READONLY`, so step 7 still adds 13 cases and every later count is unchanged.
2. Step 10's README paragraph and the npm bullet in `## Decisions` drop "with arguments only after `--`" and say why an argument after `--` is refused.
3. `## Digest` records the 08:29:01Z rejection and this difference.
4. Steps 1-6 and 8-10 are unchanged otherwise.

Not re-run: the `/tmp/t153` prototype. The guard refused the edit: "/tmp/t153/dangerous-commands.py is outside this stage's worktree". The implementer's table run is the check.

`pipeline gate TICKET-153` printed `gate: PASS` (the entry above).

### 2026-10-02 08:33:55Z · planning · session · session=e44f6351-5bf0-4458-b737-11689057c21d

`planning` ran as session `e44f6351-5bf0-4458-b737-11689057c21d`
- replay: `claude --resume e44f6351-5bf0-4458-b737-11689057c21d`
- log: `.project/logs/TICKET-153-planning-e44f6351.log`
- cost: $1.20 of a $10 cap
- tokens: 12,772 out (1,952 thinking) · 48 in · 1,649,380 cache read · 76,926 cache write

### 2026-10-02 08:33:55Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replanned step 7 per the operator's 08:30:18Z note: npm/pnpm/yarn accept only a bare `test` or `run test`, `npm test -- --runInBand` moves to BLOCKED_READONLY, step 10 and Decisions updated; every other step unchanged; pipeline gate prints PASS

### 2026-10-02 08:35:19Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpwue_gza8'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpq6t1ag1j'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ll3x1uqu/base
      Built pipeline @ file:///tmp/pipeline-base-ll3x1uqu/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 94ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-ll3x1uqu/base/.venv/bin/python', '/tmp/pipeline-base-ll3x1uqu/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding

### 2026-10-02 · plan-validation · review

**Tier B: ok. Every item passes.** Step 7 now admits exactly `["test"]` / `["run", "test"]`, which closes the 08:29:01Z gap.
long: eight scored items plus two suggested tickets need their evidence.

1. **Root cause: pass.** Part 1: `fenced_touches()` matches symbol spans, and `FENCED` names `validate_meta` but not the module-level patterns it applies. Part 2: `readonly_rules()` admits `READ_TOOLS`, `TEST_RUNNERS`, `GUARDED` and git by name or first word, never by the arguments that write or execute. Steps 1-9 fix both causes, not the two tests.
2. **Decisions: pass.** DEC-106 superseded with every other rule restated. The git invariant-4 exception quotes the 07:59:04Z answer. Step 6's second prefix match sits below the redirection and `always_rules()` checks (DEC-058).
3. **Scope: pass.** Every step traces to a criterion; step 10 to the README grep.
4. **Falsifiable: pass.** Each BLOCKED case is allowed by the unfixed guard, so the tables test fails without the code.
5. **No research left: pass.** Each step names file, function, branch position and cases. I traced every new case and every existing `ALLOWED_READONLY`/`BLOCKED_READONLY` case through the planned code; none flips. `PY_MODULES_OK` ⊆ `OPTION_SPECS` and `GUARDED` ⊆ `GUARDED_SPECS` ∪ python, so no `KeyError`.
6. **Riskiest step: pass.** Step 9 (pytest), with a narrow-never-widen fallback.
7. **Regression surface: pass.** No test outside the guard's own file and the two `tests/test_stages.py` checks feeds commands to `verdict()`. `tests/test_machine.py:60` quotes the fence paragraph in a docstring only.
8. **Blast radius: pass.** 5 files; the operator widened scope.

Suggested new ticket: `name = os.path.basename(argv[0])` (`dangerous-commands.py:503`) reads an env assignment as the program. `X=/cat touch /tmp/x` names `cat`, and `PYTEST_ADDOPTS=--junit-xml=/tmp/pytest pytest -q` passes step 9. The cause is program misidentification, not argument checking. Unverified: my guard refuses `python3 -c`, so I could not run `verdict()`.

Suggested new ticket: `parse_correction()`/`correct_decision()` (apply `SAFE_DEC_ID`) and `lease_expiry()` stay unfenced. These are unfenced functions, not patterns of a fenced one.

### 2026-10-02 08:40:44Z · plan-validation · session · session=b1c6953d-9f47-4c29-8730-059223eaedfd

`plan-validation` ran as session `b1c6953d-9f47-4c29-8730-059223eaedfd`
- replay: `claude --resume b1c6953d-9f47-4c29-8730-059223eaedfd`
- log: `.project/logs/TICKET-153-plan-validation-b1c6953d.log`
- cost: $1.65 of a $3 cap
- tokens: 31,081 out (23,519 thinking) · 36 in · 1,387,986 cache read · 93,557 cache write

### 2026-10-02 08:40:44Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ all eight items pass; step 7 now admits only bare npm/pnpm/yarn test or run test; traced every new and existing table case against the planned code; two different-root-cause gaps filed as suggested tickets

### 2026-10-02 08:41:43Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-02 08:43:09Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails as required
```
ns. A diff
        that changes only `SAFE_TEST` must trip the fence like one that edits
        `validate_meta` itself (TICKET-153)."""
        d, sh = git_project()
        ticket = d / "pipeline" / "core" / "ticket.py"
        ticket.parent.mkdir(parents=True)
        body = (
            "import re\n\n"
            "SAFE_TEST = re.compile(r'^[a-z]+$')\n\n\n"
            "def validate_meta(meta):\n"
            "    return meta\n"
        )
        ticket.write_text(body)
        sh("git add -A && git commit -qm commit-ticket")
        assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmp6n4_agq9'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 07:38:44Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence` fails on base `main` too -- the bug is not already fixed upstream
```
  assert fenced_touches(d, "main") == []
        ticket.write_text(body.replace("[a-z]+", "[a-z >]+"))
        sh("git add -A")
>       assert fenced_touches(d, "main") != []
E       AssertionError: assert [] != []
E        +  where [] = fenced_touches(PosixPath('/tmp/tmpgcrj6vhj'), 'main')

tests/test_fence.py:117: AssertionError
=========================== short test summary info ============================
FAILED tests/test_fence.py::test_loosening_a_safe_pattern_trips_the_fence - A...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.09s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-hdaj99iz/base
      Built pipeline @ file:///tmp/pipeline-base-hdaj99iz/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 69ms

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage` fails on base `main` too -- the bug is not already fixed upstream
```
PELINE_READONLY_ALLOW", None)
        cmds = ["find . -name x -delete", "find . -fprint /tmp/out",
                "awk 'BEGIN{system(\"touch /tmp/x\")}'"]
        for cmd in cmds:
            event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            p = subprocess.run([sys.executable, str(GUARD)], input=event,
                               capture_output=True, text=True, env=env)
>           assert p.returncode == 2, (cmd, p.returncode, p.stderr)
E           AssertionError: ('find . -name x -delete', 0, '')
E           assert 0 == 2
E            +  where 0 = CompletedProcess(args=['/tmp/pipeline-base-hdaj99iz/base/.venv/bin/python', '/tmp/pipeline-base-hdaj99iz/base/pipeline/hooks/dangerous-commands.py'], returncode=0, stdout='', stderr='').returncode

pipeline/hooks/test_dangerous_commands.py:588: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_find_and_awk_cannot_write_in_a_read_only_stage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.11s ===============================

```
- ok: DEC-057 is superseded -- history, not binding

### 2026-10-02 08:43:09Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-10-02 · implementing · report

**Plan steps 1-10 done. Full suite: `763 passed` (baseline `2 failed, 761 passed`).**

- [x] 1 fence: `0592211` -- six `SAFE_*` in FENCED and CLAUDE.md; `tests/test_fence.py` and the drift test pass.
- [x] tables: `test(TICKET-153)` commit -- all 168 new cases, written first. Red: `AssertionError: readonly: 'find . -name x -delete' -> None (expected block)`. CLAUDE.md count 188 -> 356.
- [x] 2-9 code: `44cf145` -- find, awk, `OPTION_SPECS`, `operands()`, `git_verdict()`, `unwrap_run()`, npm/pnpm/yarn bare `test`, `GUARDED_SPECS`, pytest/unittest/tox/nox. Plan code used verbatim. `./pipeline/hooks/test_dangerous_commands.py` prints `guard: all passed`.
- [x] 10 README paragraph: same commit.

Deviation: steps 2-10 are one commit, not one per step, because the tables were added up front. No test was edited or weakened.
Acceptance checks run: `READ_TOOLS` lacks the nine named tools; the GUARDED/TEST_RUNNERS/GIT_WORKTREE_READ check prints `[] False False`; the README grep prints `1`.
Not run: the invariant-4 live check under `--setting-sources project`; the human merge gate re-runs it.

### 2026-10-02 08:46:42Z · implementing · session · session=a5412979-e57f-4263-a11f-cc58798ed9d1

`implementing` ran as session `a5412979-e57f-4263-a11f-cc58798ed9d1`
- replay: `claude --resume a5412979-e57f-4263-a11f-cc58798ed9d1`
- log: `.project/logs/TICKET-153-implementing-a5412979.log`
- cost: $0.79 of a $9 cap
- tokens: 19,661 out (1,334 thinking) · 40 in · 1,331,337 cache read · 80,639 cache write

### 2026-10-02 08:46:42Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ fenced the six SAFE_* patterns; every readonly_rules() branch now checks arguments; full suite 763 passed

### 2026-10-02 · review · report

**Pass: no blocking findings.** First review. Delta `9180b1b..44cf145`, 4 commits.

The code and table cases match plan steps 1-10 as written. That covers FENCED, `find_only_reads()`, `awk_only_reads()`, `OPTION_SPECS`, `operands()`, `git_verdict()`, `unwrap_run()`, `runs_the_test_script()`, `GUARDED_SPECS`/`guarded_options()`, the CLAUDE.md fence sentence and the README paragraph.

Checks run on `44cf145`:
- `uv run --group dev pytest -q`: `763 passed in 80.33s`.
- Guard, stages and fence tests: `70 passed in 1.95s`.
- `./pipeline/hooks/test_dangerous_commands.py`: `guard: all passed`.
- README grep: `1`.
- No `TEST_RUNNERS` or `GIT_WORKTREE_READ` reference remains in any `*.py`.
- No stage prompt or packaged skill names a command that is now refused.

Not run: the two `python3 -c` acceptance checks. The review guard refuses `python3 -c`. I checked their claims against the diff: the `READ_TOOLS` literal lacks all nine tools. `GUARDED` keys are python, python3, cargo, go and make, and the last three are in `GUARDED_SPECS`.

Non-blocking:
1. (minor) Steps 2-10 landed as one `fix` commit (`44cf145`), README included. `## Rollback` assumes a revert per step, so a partial revert now needs a hand edit.
2. (accepted cost) `OPTION_SPECS["pytest"]` refuses `-W`, `-n` and `-p no:cacheprovider`. A project that needs one adds a `[readonly] allow` prefix.

### 2026-10-02 08:53:32Z · review · session · session=ebe5d6ca-503a-4cb2-a591-af74d7074e28

`review` ran as session `ebe5d6ca-503a-4cb2-a591-af74d7074e28`
- replay: `claude --resume ebe5d6ca-503a-4cb2-a591-af74d7074e28`
- log: `.project/logs/TICKET-153-review-ebe5d6ca.log`
- cost: $1.48 of a $5 cap
- tokens: 31,126 out (26,919 thinking) · 28 in · 981,010 cache read · 82,570 cache write

### 2026-10-02 08:53:32Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ no blocking findings; code matches plan steps 1-10; full suite 763 passed, guard script all passed, 70 guard/stages/fence tests passed

### 2026-10-02 08:54:56Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/hooks/dangerous-commands.py`
- `pipeline/core/machine.py:FENCED`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-153` lands it; `pipeline resume TICKET-153 --stage planning` sends it back.

### 2026-10-02 09:04:08Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-02 09:30:10Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/153


Current branch ticket/153 is up to date.
Already up to date.
Updating 9180b1b..44cf145
Fast-forward
 CLAUDE.md                                 |   6 +-
 README.md                                 |   2 +
 pipeline/core/machine.py                  |   8 +-
 pipeline/hooks/dangerous-commands.py      | 381 ++++++++++++++++++++++++++++--
 pipeline/hooks/test_dangerous_commands.py |  97 ++++++++
 tests/test_fence.py                       |  21 ++
 6 files changed, 495 insertions(+), 20 deletions(-)

```

### 2026-10-02 09:30:10Z · merging · decision

decision recorded as `DEC-153`
