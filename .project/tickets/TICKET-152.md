---
id: TICKET-152
stage: done
class: feature
branch: ticket/152
test_file: pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
deletes: []
files_declared:
- CLAUDE.md
- README.md
- pipeline/hooks/dangerous-commands.py
- pipeline/hooks/test_dangerous_commands.py
counters:
  plan_validation_attempts: 2
  review_loops: 1
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 6
  plan_files: 4
  no_result: 0
  structural_gate_failures: 1
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: holistic-review
  id: 9e4ad459-435b-4d2f-87dd-b7d58d733e98
  replay: claude --resume 9e4ad459-435b-4d2f-87dd-b7d58d733e98
  log: .project/logs/TICKET-152-holistic-review-9e4ad459.log
  cost_usd: 0.5176782
approved_by: chezzijr
approved_at: '2026-10-02T07:23:42.019865+00:00'
---

## Summary

The read-only guard blocks `nl`, shell `for` loops and `cd`, wasting turns in every read-only stage

Expected change files: `pipeline/hooks/dangerous-commands.py` and `pipeline/hooks/test_dangerous_commands.py`.

Two projects reported the same thing: 18 blocked commands on a Rust project, each a wasted turn, and a JS plan-validation that "ran no tests -- the guard blocks cd" and had to trust the planner's numbers. Run through the hook with `PIPELINE_READONLY=1` on main at a2365c1:

| command | exit | message |
|---|---|---|
| `nl foo.py` | 2 | `nl` is not on the read-only allowlist |
| `for f in a b; do cat $f; done` | 2 | `for` is not on the read-only allowlist |
| `cd packages/x && npx vitest run` | 2 | `cd` is not on the read-only allowlist |
| `sed -n 1,20p foo.py` | 0 | (already allowed) |

`READ_TOOLS` is at `pipeline/hooks/dangerous-commands.py:53`; the default deny at `:350`. The per-project `[readonly] allow` cannot fix `for`: entries are argv prefixes per segment, so the shell splitter hands it `for`, `do`, `done` as separate commands, and allowing `do` would allow `do <anything>`.

Expected, each with guard table cases:
- `nl` is allowed with plain file operands.
- A `for NAME in WORDS; do BODY; done` loop is allowed when every command in BODY is itself allowed; the loop keywords never become allowable on their own.
- `cd` is allowed when its target resolves inside `PIPELINE_WORKTREE`, and every later segment is still judged on its own. `cd` outside the worktree, `cd` with no argument, and `cd -` stay blocked.

This is the guard, which is fenced: it parks at `awaiting-merge` for human review. The allowlist stays an allowlist (invariant 4).


## Reproduction

Test: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`
Command: `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`

```
AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
```

expect: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)

The table also holds the `for` loop allow case and block cases (`rm` in a body, redirect in a body, bare `do`/`done`). The `cd` cases need `PIPELINE_WORKTREE`, so the table does not cover them. Add a dedicated test at implementation.

## Digest

Files: `pipeline/hooks/dangerous-commands.py` (the guard), `pipeline/hooks/test_dangerous_commands.py` (its tables and tests), `CLAUDE.md` (the `# <N> guard cases (table-driven)` line), `README.md` (`## Read-only stage commands`, line 861).
Pipeline today: `verdict()` (line 354) -> `segments()` -> `flatten()` -> `always_rules()` -> `readonly_rules()` (line 294). `readonly_rules()` checks `redirection()` per segment and `$(`/backtick in the raw string, then loops per argv: project prefix (`readonly_prefixes()`), `git`, `sed`, `READ_TOOLS` (line 53), `GUARDED`, default deny at line 350.
Splitter output, measured: `for f in a b; do cat $f; done` -> `[['for','f','in','a','b'], ['do','cat','$f'], ['done']]`; with newlines, `do` alone is its own segment `['do']`. `for f in <(rm x); do ...` -> `['for','f','in','<(','rm','x',');','do','cat','$f']`.
Loop design: `loop_bodies()` turns each loop into its body commands judged twice: once verbatim (`$f` literal) and once per word with `$f`/`${f}` replaced by that word. Loops do not nest: a `for` inside an open loop is refused. Sequential loops are fine.
The loop variable is the one channel this ticket opens, and each hole below was measured in a temp dir (`x` truncated to `a` each time, so `sed -i` ran):
    1. `bash -c 'for f in -i; do true; done; sed -n 1p $f x'` -- the variable outlives the loop.
    2. `zsh -fc 'for f in xi; do sed -n 1p $f:s/x/-/ x; done'` -- a zsh modifier rewrites the value.
    3. `zsh -fc 'for f in xi; do sed -n 1p ${f/x/-} x; done'` -- parameter expansion rewrites it.
  Hence: the name is one lowercase letter (no bash or zsh special parameter is one; `zsh -fc` listed the one-char ones as `! # $ * - 0 ? @ _`); words are a plain charset with no space, quote, glob (`*`, `?`), `$`, `{`, `<(` or leading `=`; and in a command holding a loop every `$` must be a plain `$x`/`${x}` naming the loop that encloses it, followed by end or one of `/._,=@+-`. A `$` outside every loop, or naming another loop's variable, is refused.
Why no nesting (the 03:23:48Z Tier B rejection): the previous plan's `names` set read only segments whose `argv[0]` is `for`, so `do for g in -i` escaped the scope check; a shadowing inner `for f` left `f=-i` for the outer body; and each `done` multiplied the body by (words + 1), so nine nested loops of nine words build 10^9 argv lists and a `MemoryError` exits 1, which runs the command. Refusing nesting closes all three; the expansion becomes body x (words + 1) for each loop, linear in the command's length. The "own enclosing loop" rule replaces `names`/`scope`, so no name set exists to miss.
Why `always_rules()` runs twice (the 03:36:00Z Tier B rejection and the human answer at 03:50:42Z): `verdict()` runs `always_rules()` and `flatten()` on the raw segments, where a loop body is `['do','git','-C','vendor','push','--force','origin','main']`; both key on `argv[0]`, see `do`, and skip it. With `[readonly] allow = ["git -C vendor"]` the previous plan returned `None` for that body. This plan differs in one place: step 3 re-runs `flatten()` and then `always_rules()` over `loop_bodies()`' output, above the prefix loop, so DEC-058's "a project entry can never re-enable `git push --force`" holds for loop bodies, per-word values included. The `flatten()` pass makes `do sh -c '...'` unwrap exactly as a top-level `sh -c '...'` does; without it a project prefix starting with a shell name would see the wrapper, not the program. Step 1 adds `["git", "-C", "vendor"]` to `PROJECT_PREFIXES` with three allow and four block cases that pin it.
Why no glob: `for f in *` assigns real filenames, and bash splits an unquoted `$f`, so a file named `x -i` becomes two arguments in `sed -n 1p $f` -- the judged word `*` is not the value assigned. A leading `=` is zsh's `=cmd` path expansion.
`cd` design: `cd` is judged against a SET of possible cwds. A `cd` can fail or be skipped (`||`, `&&`), so each approved `cd` adds its landing paths and removes nothing. Every target must land inside the worktree from every member, logically (`os.path.normpath`, bash's default `cd -L`) and physically (`os.path.realpath`), and be an existing directory (`os.path.isdir`), which also defeats zsh `CDABLE_VARS`.
`cd` targets must be `.`, `..`, absolute, or start `./`/`../`: measured, `CDPATH=$d/c bash -c 'cd $d/p; cd q; pwd'` printed `.../c/q`, so bash prefers a CDPATH hit over the cwd, and the guard cannot see a CDPATH set only in the agent's shell profile. `./`, `../` and `/` skip CDPATH in bash and zsh. A `cd` inside a loop body is refused: it runs once per word.
Start cwd: the hook event's `cwd` field (Claude Code sends it on every PreToolUse event) when it is an absolute `str`, else `os.getcwd()`. The e2e test runs the hook from the project root to prove the event value wins.
Existing helpers to reuse: `PUNCTUATION`, `redirection()`. `path_verdict()` line 398 holds the inside-the-worktree comparison; step 5 extracts it as `within()`.
Gotcha: a Python exception in the hook exits 1, which Claude Code treats as a non-blocking error, so the command RUNS. Every new path returns a reason, never raises; `cd_places()` catches `(OSError, ValueError)`, and `cd_verdict()` refuses a non-absolute `PIPELINE_WORKTREE` instead of calling `os.path.abspath()`.
Gotcha: `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` sums every guard table and compares `CLAUDE.md:107`; it passes at fc7290a. Step 6 sets the number that test's assertion message prints.
Gotcha: `tables()` must pop `PIPELINE_WORKTREE` like it pops `PIPELINE_READONLY_ALLOW`: a stage running this suite exports it (this planning stage has it set), and the tables mean "no worktree known".
Gotcha: the guard refuses any Bash command containing a backslash, so write regexes and multi-line Python with the file tools, not heredocs.
Prototype (this round): every case in steps 1 and 4 was run against a scratch copy of the guard built from steps 2, 3 and 5, then deleted. Every case matched its expected verdict, and every existing test in `pipeline/hooks/test_dangerous_commands.py` passed against it. The four new `BLOCKED_PROJECT` cases returned `'force push'`, `'force push'`, `'direct push to the default branch'`, `'force push'`; with the second `always_rules()` call stubbed out, all four returned `None`. `for f in a; do sh -c 'pipeline ls'; done` returned `None` (allowed) only because the body is flattened. The extended tables on the unmodified guard still fail first on `readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)`, because `tables()` checks the readonly tables before the project ones.
Known, pre-existing, out of scope: `printf -v f %s -i; sed -n 1p $f x` -- the unmodified guard returns `None`, and in a temp dir `sed -i` ran (`x` went from 4 to 2 bytes). `printf` is in `READ_TOOLS`, and bash's `printf -v` assigns a variable. The same command inside a loop body passes too; the loop adds nothing to it. See `## Thread`.
Baseline at fc7290a: `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py tests/test_stages.py` -> `1 failed, 56 passed` (the failure is the repro test).
Out of scope: the JS report's `cd packages/x && npx vitest run` stays blocked on `npx` and on the bare `packages/x`; that project writes `cd ./packages/x` and adds `npx vitest` to its own `[readonly] allow`.

## Decisions checked

- DEC-058 (active): `always_rules()` first, then redirection and command substitution, then the per-segment loop with the project prefix inside it. This plan keeps that order and extends it to loop bodies: `loop_bodies()` runs after the redirection/substitution checks, its output is flattened and judged by `always_rules()` again before the prefix loop (step 3), and the `cd` rule sits inside the loop above the prefix match, so a project prefix cannot widen `cd` or re-enable an always-refused command inside a loop. DEC-058 also requires the `CLAUDE.md` guard-case count to move in the same commit as new table cases (step 6 moves it; steps 1 and 6 land on one branch before merge).
- DEC-106 (active, supersedes DEC-057): redirection judged on tokens, `VERBOSE` prints only under `__main__`, `sed` stays one allowlisted shape. This plan adds no raw-string regex and no unconditional print. The per-word substitution in step 3 is what keeps the `sed` shape from being bypassed through `$f`.
- DEC-057: superseded by DEC-106; cited as history only (`sed` stays off `READ_TOOLS`).
- DEC-052 (active): `path_verdict()` plus `PIPELINE_WORKTREE` is the confinement for file tools. Step 5 extracts its inside-the-worktree comparison into `within()` with unchanged behaviour; `test_paths_outside_the_worktree_are_blocked` keeps it pinned.
- DEC-034, DEC-036: the guard's registration and MCP rule; untouched.
- Grep terms over `.project/decisions/`: `dangerous-commands`, `readonly_rules`, `READ_TOOLS`, `allowlist`, `split_segments`, `PIPELINE_WORKTREE`, `segments(`, `for loop`, `CDPATH`, `loop_bodies`, `cd_verdict`, `event cwd`.

## Plan

1. In `pipeline/hooks/test_dangerous_commands.py`, extend the tables and `tables()`; run the tables and watch them fail on `nl foo.py`.
    - `tables()`: next to `saved = os.environ.pop("PIPELINE_READONLY_ALLOW", None)` add `saved_wt = os.environ.pop("PIPELINE_WORKTREE", None)`, and in its `finally` restore it when not `None`. Extend the docstring by one sentence: the tables mean "no worktree known", so every `cd` in them is blocked.
    - `BLOCKED_READONLY`, under the existing `# TICKET-152` block, append these 16 Python literals: `"for f in <(rm x); do cat $f; done"`, `"for f in a; do cat $f"`, `"for f in a b; cat $f; done"`, `"for ((i=0; i<2; i++)); do cat a; done"`, `"for a in x; do for b in y; do rm $b; done; done"`, `"for PATH in /tmp; do true; done; ls"`, `"for CDPATH in /; do cat a; done"`, `"for path in /tmp; do ls; done"`, `"for f in -i; do sed -n 1p $f x; done"`, `"for f in -i; do true; done; sed -n 1p $f x"`, `"for f in xi; do sed -n 1p $f:s/x/-/ x; done"`, `"for f in xi; do sed -n 1p ${f/x/-} x; done"`, `"for f in 'x -i'; do sed -n 1p $f; done"`, `"for f in {-i,x}; do sed -n 1p $f; done"`, `"cd"`, `"cd -"`. Put one comment line above the loop-variable group: `# the loop variable is a value the guard must judge, not a name (TICKET-152)`.
    - `BLOCKED_READONLY`, directly after those 16, append these 9 Python literals under the comment `# loops do not nest, and only the enclosing loop's own variable expands (TICKET-152)`: `"for f in x; do for g in -i; do true; done; sed -n 1p $g x; done"`, `"for f in x; do for f in -i; do true; done; sed -n 1p $f x; done"`, `"for a in x; do for b in y; do cat $a $b; done; done"`, `"for a in 1 2; do for b in 1 2; do for c in 1 2; do true; done; done; done"`, `"for f in -i; do true; done; for g in x; do sed -n 1p $f x; done"`, `"for f in a; do cat $HOME; done"`, `"ls $HOME; for f in a; do cat $f; done"`, `"for f in *; do sed -n 1p $f; done"`, `"for f in =ls; do cat $f; done"`.
    - `ALLOWED_READONLY`, under the existing `# TICKET-152` block, append these 5 Python literals: `"for f in a b\ndo\n  cat $f\ndone | head -5"`, `"for f in a.py b.py; do nl $f | head -3; done"`, `"for f in a; do cat $f.bak ${f}; done; for f in b; do cat $f; done"`, `"for f in -i; do true; done; for f in x; do sed -n 1p $f x; done"`, `"ls; for f in a b; do cat $f; done; ls"`.
    - `PROJECT_PREFIXES`: append `["git", "-C", "vendor"]`. `ALLOWED_PROJECT`: append under the comment `# a prefix admits a loop body, never past always_rules() (TICKET-152)` these 3 literals: `"git -C vendor push origin x"`, `"for f in a; do pipeline ls $f; done"`, `"for f in a; do sh -c 'pipeline ls'; done"`. The first proves the prefix alone admits a push, so the blocks below come from `always_rules()`.
    - `BLOCKED_PROJECT`: append these 4 literals: `"for f in a; do git -C vendor push --force origin x; done"`, `"for f in --force; do git -C vendor push $f origin x; done"`, `"for f in a; do git -C vendor push origin main; done"`, `"for f in a; do sh -c 'git -C vendor push --force origin x'; done"`.
    - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`; expect the failure `readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)`. Every new BLOCKED case is default-denied today, so `nl foo.py` stays the first failure.
2. In `pipeline/hooks/dangerous-commands.py`, add `"nl"` to the `READ_TOOLS` set (line 53). GNU and BSD `nl` have no option that writes a file or runs a program.
3. In `pipeline/hooks/dangerous-commands.py`, add `LOOP_NAME`, `LOOP_WORD`, `VAR_REF`, `substitute()` and `loop_bodies()` directly below `redirection()`, wire `loop_bodies()` into `readonly_rules()`, and run the tables green.
    - Constants: `LOOP_NAME = re.compile(r"[a-z]")`, `LOOP_WORD = re.compile(r"[\w./@+,:-][\w./@+,:=-]*")`, `VAR_REF = re.compile(r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})(?=\Z|[/._,=@+-])")`. One comment above each says why: `LOOP_NAME` -- no bash or zsh special parameter is one lowercase letter, so the loop cannot assign `PATH`, `CDPATH`, `IFS` or zsh's `path`/`cdpath`; `LOOP_WORD` -- no space, quote, glob, `$`, `{`, `<(` or leading `=` (zsh `=cmd`), so a word is exactly the value the shell assigns; `VAR_REF` -- the lookahead refuses `$f:s/x/-/` and `$f[1]`, zsh's modifier and subscript.
    - `def substitute(tok: str, name: str, word: str) -> str:` with the body `return VAR_REF.sub(lambda m: word if (m.group(1) or m.group(2)) == name else m.group(0), tok)`.
    - `def loop_bodies(segs: list[list[str]]) -> tuple[list[list[str]] | None, str | None]:` with exactly this body (it is the prototype every step-1 case passed against):
      ```
      if not any(a and a[0] == "for" for a in segs):
          return segs, None
      out = []
      loop = None  # (name, words, body) of the open loop; loops do not nest
      want_do = False
      for argv in segs:
          if not argv:
              continue
          if want_do:
              if argv[0] != "do":
                  return None, "a `for` loop needs `do` after its word list"
              want_do = False
              argv = argv[1:]
              if not argv:
                  continue
          if argv[0] == "for":
              if loop is not None:
                  return None, "a `for` loop inside another `for` loop is not a read-only loop"
              if (len(argv) < 3 or not LOOP_NAME.fullmatch(argv[1]) or argv[2] != "in"
                      or not all(LOOP_WORD.fullmatch(w) for w in argv[3:])):
                  return None, ("only `for x in WORDS; do ...; done` is a read-only loop: "
                                "a one-letter lowercase name, and words with no space, "
                                "quote, glob, `$`, `{`, `<(` or leading `=`")
              loop = (argv[1], argv[3:], [])
              want_do = True
              continue
          if argv == ["done"]:
              if loop is None:
                  return None, "`done` closes no `for` loop"
              name, words, body = loop
              if any(c[0] == "cd" for c in body):
                  return None, ("`cd` inside a `for` loop runs once per word but is "
                                "judged once -- move it before the loop")
              out.extend(body + [[substitute(t, name, w) for t in c]
                                 for w in words for c in body])
              loop = None
              continue
          for tok in argv:
              for i, ch in enumerate(tok):
                  if ch != "$":
                      continue
                  m = VAR_REF.match(tok, i)
                  if not m or loop is None or (m.group(1) or m.group(2)) != loop[0]:
                      return None, (f"`{tok}`: a command with a `for` loop may expand only "
                                    "the loop's own variable, as a plain $x or ${x}, "
                                    "inside that loop")
          (loop[2] if loop else out).append(argv)
      if want_do or loop is not None:
          return None, "a `for` loop with no `done`"
      return out, None
      ```
    - `loop_bodies()` docstring states: (1) each body command is judged verbatim AND once per word with the variable replaced, because the variable is a value a rule like `sed_is_a_line_print()` must see; (2) a `do`/`done` outside the shape stays a command with that keyword as `argv[0]`, so default deny refuses it and the keywords never become allowable; (3) loops do not nest, because nesting let an inner name escape the scope check, let a shadowing inner loop rewrite the outer variable, and multiplied the expansion to (words + 1)^depth, whose `MemoryError` exits 1 and runs the command; (4) a `$` may name only the loop enclosing it, because the variable outlives the loop; (5) the three measured holes from `## Digest`.
    - `readonly_rules()`: directly after the `$(`/backtick check and above `allow = readonly_prefixes()`, insert, in this order: `segs, why = loop_bodies(segs)`; `if why: return why`; `segs = [a for seg in segs for a in flatten(seg)]`; `why = always_rules(segs, raw)`; `if why: return why` (each `if` on two lines, as the surrounding code writes it). One comment above the last three lines: `# verdict() ran flatten() and always_rules() on segments whose argv[0] was "do", so run both again on the bodies -- DEC-058: a project prefix never re-enables what always_rules() refuses (TICKET-152)`.
    - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`; expect `1 passed`. Commit `fix(TICKET-152): allow nl and for loops in read-only stages`.
4. In `pipeline/hooks/test_dangerous_commands.py`, add two tests above the `if __name__` block, add both calls to that block, run them and watch them fail.
    - `test_cd_is_allowed_only_inside_the_worktree()`: `proj = os.path.realpath(tempfile.mkdtemp())`, `wt = proj + "/wt"`, `os.makedirs(wt + "/packages/x")`, `os.makedirs(wt + "/a/b")`, `os.symlink(proj, wt + "/up")`, `os.symlink(wt + "/a/b", wt + "/inner")`. Save `PIPELINE_WORKTREE` and `PIPELINE_READONLY_ALLOW` (pop the second), set `PIPELINE_WORKTREE=wt`; restore both and `shutil.rmtree(proj)` in `finally`.
    - Allowed (`guard.verdict(c, True, cwd=wt) is None`): `"cd ./packages/x && ls"`, `f"cd {wt}/packages && ls"`, `"cd . && pwd"`, `"cd ./packages/x\nnl a.py"`, `f"cd {wt}/packages/x && cd {wt}"`; and `guard.verdict("cd ../.. && ls", True, cwd=wt + "/packages/x") is None`.
    - Blocked (truthy with `cwd=wt`): `"cd"`, `"cd -"`, `"cd .."`, `"cd /"`, `"cd ./up"`, `"cd ./inner/../.."`, `"cd ~"`, `"cd $HOME"`, `"cd -P ./packages"`, `"cd ./packages/x && rm a"`, `"cd ./packages && cd ../.."`, `"cd packages/x"`, `"cd +1"`, `"cd ./nosuch"`, `"cd ./packages && cd ./x"`, `"for d in a; do cd ./packages; done"`; and truthy with `cwd=wt + "/packages/x"`: `"for i in 1 2 3; do cd ..; done && ls"`.
    - Then pop `PIPELINE_WORKTREE` and assert `guard.verdict("cd ./packages/x", True, cwd=wt)` is truthy.
    - Each assert message follows `check()`'s form, e.g. `f"cd: {c!r} -> {got!r} (expected allow)"`. Print one `ok` line only when `VERBOSE`, per DEC-106.
    - `test_cd_reaches_the_real_hook_through_the_event_cwd()`: same temp layout; run `[sys.executable, str(GUARD)]` with `cwd=proj` (the project root, NOT the worktree) and `env=dict(os.environ, PIPELINE_READONLY="1", PIPELINE_WORKTREE=wt, PIPELINE_STAGE="review")` minus `PIPELINE_READONLY_ALLOW`. Event `{"tool_name": "Bash", "cwd": wt, "tool_input": {"command": "cd ./packages && ls"}}` exits 0; the same event with command `"cd .. && ls"` exits 2 with `"leaves this stage's worktree"` in stderr. The first case proves the event `cwd` is used, since from `proj` the target `proj/packages` lies outside.
    - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py -k cd_`; both tests are new, so this run is their first: expect both to fail (`TypeError` on the `cwd` keyword, and exit 2 for `cd ./packages && ls`).
5. In `pipeline/hooks/dangerous-commands.py`, implement the `cd` rule and thread `cwd` from the event to it.
    - `def within(path: str, root: str) -> bool: return path == root or path.startswith(root + os.sep)`, placed above `path_verdict()`; replace line 398's comparison with `if within(target, wt):`.
    - `CD_TARGET = re.compile(r"\.\.?|(/|\.\.?/)[\w./@+,:=-]*")`, beside `SED_PRINT`, with a comment: `.`, `..`, absolute, or `./`/`../`-led, because those forms skip CDPATH in bash and zsh and none can be an option, `~`, `$`, `+N` or `=cmd`.
    - `def cd_places(cwd: str | None) -> set[str]:` body: `try:` `here = cwd if isinstance(cwd, str) and os.path.isabs(cwd) else os.getcwd()`, `return {os.path.normpath(here), os.path.realpath(here)}`, `except (OSError, ValueError): return set()`.
    - `def cd_verdict(argv: list[str], places: set[str], worktree: str | None) -> tuple[str | None, set[str]]:` with exactly this body:
      ```
      if len(argv) != 2 or not CD_TARGET.fullmatch(argv[1]):
          return ("`cd` takes one directory operand that is `.`, `..`, absolute, or "
                  "starts with `./` or `../` -- no options, `-`, `~`, `$`, or a bare "
                  "name that CDPATH may redirect", places)
      if not worktree or not os.path.isabs(worktree):
          return "`cd` is judged against PIPELINE_WORKTREE, which is not an absolute path", places
      if not places:
          return "`cd` cannot tell which directory this command starts in", places
      t = argv[1]
      roots = {os.path.normpath(worktree), os.path.realpath(worktree)}
      landed = set()
      for here in places:
          for p in (os.path.normpath(os.path.join(here, t)),
                    os.path.realpath(os.path.join(here, t))):
              if not any(within(p, root) for root in roots):
                  return f"`cd {t}` leaves this stage's worktree {worktree}", places
              landed.add(p)
          if not os.path.isdir(os.path.realpath(os.path.join(here, t))):
              return f"`cd {t}` is not a directory from {here}", places
      return None, places | landed
      ```
    - `cd_verdict()` docstring: the set-of-cwds reason from `## Digest`; why both the logical and the physical check (physical alone passes `cd ./inner/../..`, logical alone passes `cd ./up`); and that `cd ./packages && cd ./x` is refused on purpose.
    - `readonly_rules(segs, raw, cwd=None)` (keep the type hints: `cwd: str | None = None`): before the per-argv loop set `places = None`; as the loop's first check after `if not argv: continue`, when `argv[0] == "cd"`: `if places is None: places = cd_places(cwd)`, then `why, places = cd_verdict(argv, places, os.environ.get("PIPELINE_WORKTREE"))`, `return why` when set, else `continue`. It sits above the prefix match so `[readonly] allow` cannot widen `cd`.
    - `verdict(command, readonly, cwd=None)` (typed `cwd: str | None = None`) passes `cwd` to `readonly_rules(segs, command, cwd)`. In `main()`, the Bash branch reads `cwd = event.get("cwd")` and calls `verdict(subject, os.environ.get("PIPELINE_READONLY") == "1", cwd if isinstance(cwd, str) else None)`.
    - Module docstring: one paragraph after the `PIPELINE_READONLY_ALLOW` paragraph stating that a `for` loop's body is judged command by command, verbatim and once per word, and that `cd` must land inside `PIPELINE_WORKTREE` from the cwd the hook event reports.
    - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py`; expect no failures. Commit `fix(TICKET-152): allow cd inside the worktree in read-only stages`.
6. Update the number in `CLAUDE.md` line 107's `# <N> guard cases (table-driven)` to the count `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports, and add to `README.md` `## Read-only stage commands`, after the paragraph ending "widening it is a human's commit.", the paragraph below.
    - README paragraph: "The built-in rules also accept a `for x in WORDS; do ...; done` loop with a one-letter lowercase variable, whose body commands are each allowed both as written and with each word in place of `$x`, and `cd` into an existing directory inside the stage's worktree, written as `.`, `..`, an absolute path, or a path starting `./` or `../`. Loop words carry no glob, quote or `$`, and a command with a loop may expand only that loop's `$x`, inside it. A loop inside a loop and a `cd` inside a loop are refused, a loop's keywords are never allowed on their own, and an `[readonly] allow` entry does not widen `cd`."
    - Run `uv run --group dev pytest -q tests/test_stages.py::test_the_rule_file_counts_the_guard_cases`; its message `CLAUDE.md says ['145'], tables hold N` names N. Write N, re-run, expect `1 passed`.
    - Run `./pipeline/hooks/test_dangerous_commands.py`; expect last line `guard: all passed`. Commit `docs(TICKET-152): count the new guard cases and document loops and cd`.

## Acceptance criteria

- `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` passes (steps 1-3); it holds the `nl`, `for` loop, loop-variable, nested-loop and bare `cd` cases, and the `git -C vendor` project-prefix cases that wrap a force push and a push to `main` in a loop.
- `pipeline/hooks/test_dangerous_commands.py::test_cd_is_allowed_only_inside_the_worktree` passes (steps 4, 5).
- `pipeline/hooks/test_dangerous_commands.py::test_cd_reaches_the_real_hook_through_the_event_cwd` passes (steps 4, 5).
- `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` passes (step 6).
- `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py tests/test_stages.py` exits 0 (steps 1-6). Measured baseline at fc7290a: `1 failed, 56 passed`.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0 and its last line is `guard: all passed` (steps 1-6).
- `uv run --group dev pytest -q tests/` exits 0, or every failure it lists also fails on base `main` when re-measured at check time (steps 1-6).
- `pipeline/hooks/test_dangerous_commands.py::test_sed_is_off_the_read_only_allowlist_by_name` passes (step 2); DEC-106 keeps `sed` off `READ_TOOLS`.

## Decisions

- A read-only `for` loop is accepted only as `for x in WORDS; do BODY; done`, and `loop_bodies()` hands only BODY's commands to the allowlist. `for`/`do`/`done` are never allowlist entries: a bare `do X` reaches default deny with `do` as its program. Do not add `do` or `done` to `READ_TOOLS` or the project prefix list; `do <anything>` would then pass.
- The loop variable is a value the guard judges, not a name it ignores. Each body command is judged verbatim AND once per word with `$x`/`${x}` replaced. Without the per-word pass, `for f in -i; do sed -n 1p $f x; done` passes `sed_is_a_line_print()` and runs `sed -i`. Three rules keep the substitution honest, and each closes a measured hole:
    1. The name is one lowercase letter, so a loop cannot assign `PATH`, `CDPATH`, `IFS` or zsh's tied `path`/`cdpath`.
    2. In a command with a loop, every `$` is a plain `$x`/`${x}` followed by end or `/._,=@+-`, so zsh modifiers (`$f:s/x/-/`), subscripts and `${f/x/-}` cannot rewrite the value.
    3. That `$x` must name the loop enclosing it. A `$` outside every loop, or naming another loop's variable, is refused, because the shell keeps the last word after `done`.
  Words exclude space, quotes, globs (`*`, `?`), `$`, `{`, `<(` and a leading `=`, so a word is exactly the value assigned (no word splitting, filename generation, brace expansion, process substitution or zsh `=cmd`). Loosening any of these needs a new measured counter-example.
- Loops do not nest. Nesting broke the scope check twice (an inner `do for g` name escaped it; a shadowing inner `for f` rewrote the outer value) and made the expansion (words + 1)^depth. A `MemoryError` in the hook exits 1, and Claude Code then RUNS the command. If nesting is ever allowed, it needs shadow refusal, a scope check over the parsed names, and a hard cap on the expanded size that returns a reason.
- The per-word pass assumes no body command reassigns the variable. Bash's `printf -v f` does, and `printf` is in `READ_TOOLS`; that hole is on main without any loop (measured, see `## Thread`) and is not closed here.
- `loop_bodies()` runs AFTER the redirection and command-substitution checks (DEC-058's order), so the redirection scan sees every original segment, `done > out` included.
- `readonly_rules()` runs `flatten()` and then `always_rules()` a second time, over `loop_bodies()`' output and above the `[readonly] allow` prefix loop. `verdict()`'s first pass sees a loop body as a segment whose `argv[0]` is `do`, so it never reaches the body's program. Without the second pass, `[readonly] allow = ["git -C vendor"]` admits `for f in a; do git -C vendor push --force origin main; done`. Do not remove the second call as a duplicate; the `git -C vendor` cases in `BLOCKED_PROJECT` go red without it.
- `cd` is judged against a set of possible cwds that only grows, never a single tracked cwd. A `cd` that fails or is skipped by `||`/`&&` leaves the shell where it was. The accepted cost: `cd ./packages && cd ./x` is refused; write one `cd` with the full path. A `cd` inside a loop body is refused because it runs once per word.
- Each `cd` target must land inside the worktree both logically (`normpath`, bash's default `cd -L`) and physically (`realpath`), and be an existing directory. Physical alone passes `cd ./inner/../..` through an in-tree symlink; logical alone passes `cd ./up` through a symlink to outside; the `isdir` check stops zsh `CDABLE_VARS` from reinterpreting a missing directory.
- `cd` targets are `.`, `..`, absolute, or `./`/`../`-led, never a bare name. Bash prefers a CDPATH hit over the cwd, and a CDPATH set in the agent's shell profile never reaches the hook's environment. Do not relax this to "bare names when CDPATH is unset".
- The `cd` rule sits above the `[readonly] allow` prefix match, so a project entry cannot widen it.
- The start cwd is the hook event's `cwd`. The guard trusts Claude Code to report the shell's current directory there. If a harness reports a stale directory, relative `cd` judgments use the wrong base; absolute targets are unaffected.

## Rollback

Revert the ticket's three commits on `main` (`git revert` of each, newest first). That restores `nl`, `for` and `cd` to default deny, the shipped behaviour at a2365c1; nothing outside the guard, its tests and two doc lines depends on them.
Riskiest step: step 5, the `cd` rule, because it is new path logic inside the one layer that makes a promise. Fallback when step 5's tests stay red and the cause is not a typo: drop the `cd` half. Run `git checkout HEAD -- pipeline/hooks/dangerous-commands.py pipeline/hooks/test_dangerous_commands.py` after step 3's commit, which reverts step 5's code and step 4's two tests. Ship `nl` and `for` alone, set `CLAUDE.md` from the count test, and return `blocked` naming the failing case so `cd` is replanned as its own ticket.
Fallback when the step-3 table run stays red: report the exact failing case and return `blocked`. Do not loosen `LOOP_NAME`, `LOOP_WORD`, `VAR_REF`, the nesting refusal, the enclosing-loop check or the second `always_rules()` pass to make a case pass; each guards a measured bypass.

## Thread

### 2026-10-02 02:07:34Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### triage

Reproduced at 0286b05. Verdict `ok`, not `chore`: the `for` loop needs a design choice in the splitter. Expected files: `pipeline/hooks/dangerous-commands.py`, `pipeline/hooks/test_dangerous_commands.py`.

### 2026-10-02 02:20:26Z · triage · session · session=68f74e5c-97f5-4db7-8b9f-653f91f835b1

`triage` ran as session `68f74e5c-97f5-4db7-8b9f-653f91f835b1`
- replay: `claude --resume 68f74e5c-97f5-4db7-8b9f-653f91f835b1`
- log: `.project/logs/TICKET-152-triage-68f74e5c.log`
- cost: $0.25 of a $3 cap
- tokens: 4,304 out (226 thinking) · 26 in · 402,339 cache read · 32,624 cache write

### 2026-10-02 02:20:26Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced - guard table rejects nl and for loops in read-only stages; test committed

### 2026-10-02 02:30:06Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
```
check(ALLOWED_READONLY, True, False, "readonly")
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cmds = ['pytest -x', 'git diff main...HEAD', 'grep -rn foo .', 'git log --oneline', 'cat thing.py', 'python3 -m pytest --deselect x', ...]
readonly = True, expect_block = False, label = 'readonly'

    def check(cmds, readonly, expect_block, label):
        for c in cmds:
            got = guard.verdict(c, readonly)
>           assert bool(got) == expect_block, \
                f"{label}: {c!r} -> {got!r} (expected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ixq69etj/base
      Built pipeline @ file:///tmp/pipeline-base-ixq69etj/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 90ms

```
- suite excluding `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` is RED -- pre-existing breakage, fix that first
```
 / "hooks" / "test_dangerous_commands.py"
        spec = importlib.util.spec_from_file_location("guard_tables", path)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        cases = sum(len(t) for t in (mod.BLOCKED_ALWAYS, mod.ALLOWED_ALWAYS,
                                     mod.BLOCKED_READONLY, mod.ALLOWED_READONLY,
                                     mod.MCP_BLOCKED, mod.MCP_ALLOWED,
                                     mod.ALLOWED_PROJECT, mod.BLOCKED_PROJECT))
        text = (C.PKG.parent / "CLAUDE.md").read_text()
        claimed = re.findall(r"# (\d+) guard cases \(table-driven\)", text)
>       assert claimed == [str(cases)], f"CLAUDE.md says {claimed}, tables hold {cases}"
E       AssertionError: CLAUDE.md says ['138'], tables hold 145
E       assert ['138'] == ['145']
E         
E         At index 0 diff: '138' != '145'
E         Use -v to get more diff

tests/test_stages.py:446: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_the_rule_file_counts_the_guard_cases - Asse...
============ 1 failed, 724 passed, 1 deselected in 77.35s (0:01:17) ============

```
- ok: DEC-057 is superseded -- history, not binding
- `files_declared` is empty
- plan step names no declared file: '1. In `pipeline/hooks/test_dangerous_commands.py`, extend the tables and `tables()`; run the tables and watch them fail on `nl foo.py`. - `tables()`: next to `saved = os.environ.pop("PIPELINE_READONLY_ALLOW", None)` add `saved_wt = os.environ.pop("PIPELINE_WORKTREE", None)`, and in its `finally` restore it when not `None`. Extend the docstring by one sentence: the tables mean "no worktree known", so every `cd` in them is blocked. - `BLOCKED_READONLY`, under the existing `# TICKET-152` block, append: `"for f in <(rm x); do cat $f; done"`, `"for f in a; do cat $f"`, `"for f in a b; cat $f; done"`, `"for ((i=0; i<2; i++)); do cat a; done"`, `"for a in x; do for b in y; do rm $b; done; done"`, `"cd"`, `"cd -"`. - `ALLOWED_READONLY`, under the existing `# TICKET-152` block, append: `"for f in a b\\ndo\\n  cat $f\\ndone | head -5"`, `"for f in a.py b.py; do nl $f | head -3; done"`, `"for a in x; do for b in y; do cat $a $b; done; done"`. - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`; expect the failure `readonly: \'nl foo.py\' -> \'`nl` is not on the read-only allowlist\' (expected allow)`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. In `pipeline/hooks/dangerous-commands.py`, add `"nl"` to the `READ_TOOLS` set (line 53). GNU and BSD `nl` have no option that writes a file or runs a program.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. In `pipeline/hooks/dangerous-commands.py`, add `LOOP_NAME` and `loop_bodies()` below `redirection()`, wire it into `readonly_rules()`, and run the tables green. - `LOOP_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")`. - `def loop_bodies(segs: list[list[str]]) -> tuple[list[list[str]] | None, str | None]:` returns `(commands, None)` or `(None, reason)`. Body: `out, depth, want_do = [], 0, False`; for each `argv` in `segs`: a. if `want_do`: when `argv[0] != "do"` return `(None, "a `for` loop needs `do` after its word list")`; else set `want_do = False`, `argv = argv[1:]`, and `continue` when `argv` is now empty; b. if `argv[0] == "for"`: when `len(argv) < 3`, or `not LOOP_NAME.fullmatch(argv[1])`, or `argv[2] != "in"`, or `any(set(w) & set(PUNCTUATION) for w in argv[3:])`, return `(None, "only `for NAME in WORDS; do ...; done` is a read-only loop")`; else `depth += 1`, `want_do = True`, `continue`; c. if `argv == ["done"]`: when `depth == 0` return `(None, "`done` closes no `for` loop")`; else `depth -= 1`, `continue`; d. otherwise `out.append(argv)`. After the loop, when `depth or want_do` return `(None, "a `for` loop with no `done`")`; else `(out, None)`. - Docstring: a `do` that does not directly follow a `for` header stays in `out` with `do` as `argv[0]`, so default deny refuses it; the keywords never become allowable on their own. A WORD carrying a `PUNCTUATION` char is refused because `<(` runs a command. - `readonly_rules()`: directly after the `$(`/backtick check, insert `segs, why = loop_bodies(segs)` and `if why: return why`. - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`; expect `1 passed`. Commit `fix(TICKET-152): allow nl and for loops in read-only stages`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '4. In `pipeline/hooks/test_dangerous_commands.py`, add two tests above the `if __name__` block, add both calls to that block, run them and watch them fail. - `test_cd_is_allowed_only_inside_the_worktree()`: `proj = os.path.realpath(tempfile.mkdtemp())`, `wt = proj + "/wt"`, make `wt/packages/x` and `wt/a/b`, `os.symlink(proj, wt + "/up")`, `os.symlink(wt + "/a/b", wt + "/inner")`. Save `PIPELINE_WORKTREE` and pop `CDPATH` (save it); set `PIPELINE_WORKTREE=wt`; restore both and `shutil.rmtree(proj)` in `finally`. - Allowed (`guard.verdict(c, True, cwd=wt) is None`): `"cd packages/x && ls"`, `f"cd {wt}/packages && ls"`, `"cd . && pwd"`, `"cd packages/x\\nnl a.py"`, `"for f in a; do cd packages; done"`; and `guard.verdict("cd ../.. && ls", True, cwd=wt + "/packages/x") is None`. - Blocked (truthy with `cwd=wt`): `"cd"`, `"cd -"`, `"cd .."`, `"cd /"`, `"cd up"`, `"cd inner/../.."`, `"cd ~"`, `"cd $HOME"`, `"cd -P packages"`, `"cd packages/x && rm a"`, `"cd packages && cd ../.."`, `"for d in a; do cd /; done"`. - CDPATH: set `os.environ["CDPATH"] = proj`; assert `"cd packages/x"` is blocked and `"cd ./packages/x"` is allowed; pop `CDPATH`. Then pop `PIPELINE_WORKTREE` and assert `"cd packages/x"` is blocked. - Each assert message follows `check()`\'s form, e.g. `f"cd: {c!r} -> {got!r} (expected allow)"`. Print one `ok` line only when `VERBOSE`, per DEC-106. - `test_cd_reaches_the_real_hook_through_the_event_cwd()`: same temp layout; run `[sys.executable, str(GUARD)]` with `cwd=proj` (the project root, NOT the worktree) and `env=dict(os.environ, PIPELINE_READONLY="1", PIPELINE_WORKTREE=wt, PIPELINE_STAGE="review")` minus `CDPATH`. Event `{"tool_name": "Bash", "cwd": wt, "tool_input": {"command": "cd packages && ls"}}` exits 0; the same event with command `"cd .. && ls"` exits 2 with `"leaves this stage\'s worktree"` in stderr. The first case proves the event `cwd` is used, since from `proj` the target `proj/packages` lies outside. - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py -k cd_`; expect both to fail (`TypeError` on the `cwd` keyword, and exit 2 for `cd packages && ls`).' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '5. In `pipeline/hooks/dangerous-commands.py`, implement the `cd` rule and thread `cwd` from the event to it. - `def within(path: str, root: str) -> bool: return path == root or path.startswith(root + os.sep)`, placed above `path_verdict()`; replace line 398\'s comparison with `if within(target, wt):`. - `CD_TARGET = re.compile(r"[\\w./@+,:=-]+")`, beside `SED_PRINT`. - `def cd_places(cwd: str | None) -> set[str]:` uses `cwd` when it is a `str` and `os.path.isabs(cwd)`, else `os.getcwd()` inside `try/except OSError: return set()`; returns `{os.path.normpath(here), os.path.realpath(here)}`. - `def cd_verdict(argv: list[str], places: set[str], worktree: str | None) -> tuple[str | None, set[str]]:` in this order: a. `len(argv) != 2` or `argv[1].startswith("-")` or not `CD_TARGET.fullmatch(argv[1])` -> `"`cd` takes exactly one plain directory operand: no options, `-`, `~` or `$`"`; b. no `worktree` -> `"`cd` is judged against PIPELINE_WORKTREE, which is not set"`; c. `os.environ.get("CDPATH")` and the target is relative, not `.`/`..`, and does not start with `./` or `../` -> `f"`cd {t}` may search CDPATH; write ./{t} or an absolute path"`; d. empty `places` -> `"`cd` cannot tell which directory this command starts in"`; e. `roots = {os.path.normpath(os.path.abspath(worktree)), os.path.realpath(worktree)}`; for each `here` in `places` and each of `os.path.normpath(os.path.join(here, t))` and `os.path.realpath(os.path.join(here, t))`: if no root has `within(p, root)`, return `f"`cd {t}` leaves this stage\'s worktree {worktree}"`; else collect `p`. Return `(None, places | collected)`. Every refusal returns `places` unchanged. Docstring: the set-of-cwds reason from `## Digest`, and that `cd packages && cd x` is refused on purpose. - `readonly_rules(segs, raw, cwd=None)`: before the per-argv loop set `places = None`; as the loop\'s first check after `if not argv`, when `argv[0] == "cd"`: `if places is None: places = cd_places(cwd)`, then `why, places = cd_verdict(argv, places, os.environ.get("PIPELINE_WORKTREE"))`, `return why` when set, else `continue`. It sits above the prefix match so `[readonly] allow` cannot widen `cd`. - `verdict(command, readonly, cwd=None)` passes `cwd` to `readonly_rules()`. In `main()`, the Bash branch reads `cwd = event.get("cwd")` and calls `verdict(subject, ..., cwd if isinstance(cwd, str) else None)`. - Module docstring: one paragraph after the `PIPELINE_READONLY_ALLOW` paragraph stating that a `for` loop\'s body is judged command by command and `cd` must land inside `PIPELINE_WORKTREE`. - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py`; expect no failures. Commit `fix(TICKET-152): allow cd inside the worktree in read-only stages`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '6. Update `CLAUDE.md` line 107\'s `# 138 guard cases (table-driven)` to the count `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports, and add to `README.md` `## Read-only stage commands`, after the paragraph ending "widening it is a human\'s commit.", the paragraph below. - README paragraph: "The built-in rules also accept a `for NAME in WORDS; do ...; done` loop whose body commands are each allowed, and `cd` into a directory inside the stage\'s worktree. A `for` loop\'s keywords are never allowed on their own, and an `[readonly] allow` entry does not widen `cd`." - Run `uv run --group dev pytest -q tests/test_stages.py::test_the_rule_file_counts_the_guard_cases`; its message `CLAUDE.md says [\'138\'], tables hold N` names N. Write N, re-run, expect `1 passed`. - Run `./pipeline/hooks/test_dangerous_commands.py`; expect last line `guard: all passed`. Commit `docs(TICKET-152): count the new guard cases and document loops and cd`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
```
check(ALLOWED_READONLY, True, False, "readonly")
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cmds = ['pytest -x', 'git diff main...HEAD', 'grep -rn foo .', 'git log --oneline', 'cat thing.py', 'python3 -m pytest --deselect x', ...]
readonly = True, expect_block = False, label = 'readonly'

    def check(cmds, readonly, expect_block, label):
        for c in cmds:
            got = guard.verdict(c, readonly)
>           assert bool(got) == expect_block, \
                f"{label}: {c!r} -> {got!r} (expected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-2hiwz99k/base
      Built pipeline @ file:///tmp/pipeline-base-2hiwz99k/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 80ms

```
- ok: DEC-057 is superseded -- history, not binding
- `files_declared` is empty
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '1. In `pipeline/hooks/test_dangerous_commands.py`, extend the tables and `tables()`; run the tables and watch them fail on `nl foo.py`. - `tables()`: next to `saved = os.environ.pop("PIPELINE_READONLY_ALLOW", None)` add `saved_wt = os.environ.pop("PIPELINE_WORKTREE", None)`, and in its `finally` restore it when not `None`. Extend the docstring by one sentence: the tables mean "no worktree known", so every `cd` in them is blocked. - `BLOCKED_READONLY`, under the existing `# TICKET-152` block, append: `"for f in <(rm x); do cat $f; done"`, `"for f in a; do cat $f"`, `"for f in a b; cat $f; done"`, `"for ((i=0; i<2; i++)); do cat a; done"`, `"for a in x; do for b in y; do rm $b; done; done"`, `"cd"`, `"cd -"`. - `ALLOWED_READONLY`, under the existing `# TICKET-152` block, append: `"for f in a b\\ndo\\n  cat $f\\ndone | head -5"`, `"for f in a.py b.py; do nl $f | head -3; done"`, `"for a in x; do for b in y; do cat $a $b; done; done"`. - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`; expect the failure `readonly: \'nl foo.py\' -> \'`nl` is not on the read-only allowlist\' (expected allow)`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '2. In `pipeline/hooks/dangerous-commands.py`, add `"nl"` to the `READ_TOOLS` set (line 53). GNU and BSD `nl` have no option that writes a file or runs a program.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '3. In `pipeline/hooks/dangerous-commands.py`, add `LOOP_NAME` and `loop_bodies()` below `redirection()`, wire it into `readonly_rules()`, and run the tables green. - `LOOP_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")`. - `def loop_bodies(segs: list[list[str]]) -> tuple[list[list[str]] | None, str | None]:` returns `(commands, None)` or `(None, reason)`. Body: `out, depth, want_do = [], 0, False`; for each `argv` in `segs`: a. if `want_do`: when `argv[0] != "do"` return `(None, "a `for` loop needs `do` after its word list")`; else set `want_do = False`, `argv = argv[1:]`, and `continue` when `argv` is now empty; b. if `argv[0] == "for"`: when `len(argv) < 3`, or `not LOOP_NAME.fullmatch(argv[1])`, or `argv[2] != "in"`, or `any(set(w) & set(PUNCTUATION) for w in argv[3:])`, return `(None, "only `for NAME in WORDS; do ...; done` is a read-only loop")`; else `depth += 1`, `want_do = True`, `continue`; c. if `argv == ["done"]`: when `depth == 0` return `(None, "`done` closes no `for` loop")`; else `depth -= 1`, `continue`; d. otherwise `out.append(argv)`. After the loop, when `depth or want_do` return `(None, "a `for` loop with no `done`")`; else `(out, None)`. - Docstring: a `do` that does not directly follow a `for` header stays in `out` with `do` as `argv[0]`, so default deny refuses it; the keywords never become allowable on their own. A WORD carrying a `PUNCTUATION` char is refused because `<(` runs a command. - `readonly_rules()`: directly after the `$(`/backtick check, insert `segs, why = loop_bodies(segs)` and `if why: return why`. - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables`; expect `1 passed`. Commit `fix(TICKET-152): allow nl and for loops in read-only stages`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '4. In `pipeline/hooks/test_dangerous_commands.py`, add two tests above the `if __name__` block, add both calls to that block, run them and watch them fail. - `test_cd_is_allowed_only_inside_the_worktree()`: `proj = os.path.realpath(tempfile.mkdtemp())`, `wt = proj + "/wt"`, make `wt/packages/x` and `wt/a/b`, `os.symlink(proj, wt + "/up")`, `os.symlink(wt + "/a/b", wt + "/inner")`. Save `PIPELINE_WORKTREE` and pop `CDPATH` (save it); set `PIPELINE_WORKTREE=wt`; restore both and `shutil.rmtree(proj)` in `finally`. - Allowed (`guard.verdict(c, True, cwd=wt) is None`): `"cd packages/x && ls"`, `f"cd {wt}/packages && ls"`, `"cd . && pwd"`, `"cd packages/x\\nnl a.py"`, `"for f in a; do cd packages; done"`; and `guard.verdict("cd ../.. && ls", True, cwd=wt + "/packages/x") is None`. - Blocked (truthy with `cwd=wt`): `"cd"`, `"cd -"`, `"cd .."`, `"cd /"`, `"cd up"`, `"cd inner/../.."`, `"cd ~"`, `"cd $HOME"`, `"cd -P packages"`, `"cd packages/x && rm a"`, `"cd packages && cd ../.."`, `"for d in a; do cd /; done"`. - CDPATH: set `os.environ["CDPATH"] = proj`; assert `"cd packages/x"` is blocked and `"cd ./packages/x"` is allowed; pop `CDPATH`. Then pop `PIPELINE_WORKTREE` and assert `"cd packages/x"` is blocked. - Each assert message follows `check()`\'s form, e.g. `f"cd: {c!r} -> {got!r} (expected allow)"`. Print one `ok` line only when `VERBOSE`, per DEC-106. - `test_cd_reaches_the_real_hook_through_the_event_cwd()`: same temp layout; run `[sys.executable, str(GUARD)]` with `cwd=proj` (the project root, NOT the worktree) and `env=dict(os.environ, PIPELINE_READONLY="1", PIPELINE_WORKTREE=wt, PIPELINE_STAGE="review")` minus `CDPATH`. Event `{"tool_name": "Bash", "cwd": wt, "tool_input": {"command": "cd packages && ls"}}` exits 0; the same event with command `"cd .. && ls"` exits 2 with `"leaves this stage\'s worktree"` in stderr. The first case proves the event `cwd` is used, since from `proj` the target `proj/packages` lies outside. - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py -k cd_`; expect both to fail (`TypeError` on the `cwd` keyword, and exit 2 for `cd packages && ls`).' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '5. In `pipeline/hooks/dangerous-commands.py`, implement the `cd` rule and thread `cwd` from the event to it. - `def within(path: str, root: str) -> bool: return path == root or path.startswith(root + os.sep)`, placed above `path_verdict()`; replace line 398\'s comparison with `if within(target, wt):`. - `CD_TARGET = re.compile(r"[\\w./@+,:=-]+")`, beside `SED_PRINT`. - `def cd_places(cwd: str | None) -> set[str]:` uses `cwd` when it is a `str` and `os.path.isabs(cwd)`, else `os.getcwd()` inside `try/except OSError: return set()`; returns `{os.path.normpath(here), os.path.realpath(here)}`. - `def cd_verdict(argv: list[str], places: set[str], worktree: str | None) -> tuple[str | None, set[str]]:` in this order: a. `len(argv) != 2` or `argv[1].startswith("-")` or not `CD_TARGET.fullmatch(argv[1])` -> `"`cd` takes exactly one plain directory operand: no options, `-`, `~` or `$`"`; b. no `worktree` -> `"`cd` is judged against PIPELINE_WORKTREE, which is not set"`; c. `os.environ.get("CDPATH")` and the target is relative, not `.`/`..`, and does not start with `./` or `../` -> `f"`cd {t}` may search CDPATH; write ./{t} or an absolute path"`; d. empty `places` -> `"`cd` cannot tell which directory this command starts in"`; e. `roots = {os.path.normpath(os.path.abspath(worktree)), os.path.realpath(worktree)}`; for each `here` in `places` and each of `os.path.normpath(os.path.join(here, t))` and `os.path.realpath(os.path.join(here, t))`: if no root has `within(p, root)`, return `f"`cd {t}` leaves this stage\'s worktree {worktree}"`; else collect `p`. Return `(None, places | collected)`. Every refusal returns `places` unchanged. Docstring: the set-of-cwds reason from `## Digest`, and that `cd packages && cd x` is refused on purpose. - `readonly_rules(segs, raw, cwd=None)`: before the per-argv loop set `places = None`; as the loop\'s first check after `if not argv`, when `argv[0] == "cd"`: `if places is None: places = cd_places(cwd)`, then `why, places = cd_verdict(argv, places, os.environ.get("PIPELINE_WORKTREE"))`, `return why` when set, else `continue`. It sits above the prefix match so `[readonly] allow` cannot widen `cd`. - `verdict(command, readonly, cwd=None)` passes `cwd` to `readonly_rules()`. In `main()`, the Bash branch reads `cwd = event.get("cwd")` and calls `verdict(subject, ..., cwd if isinstance(cwd, str) else None)`. - Module docstring: one paragraph after the `PIPELINE_READONLY_ALLOW` paragraph stating that a `for` loop\'s body is judged command by command and `cd` must land inside `PIPELINE_WORKTREE`. - Run `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py`; expect no failures. Commit `fix(TICKET-152): allow cd inside the worktree in read-only stages`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
  -- this finding has now fired 2 times on this ticket. A finding that repeats is a missing project rule: pin it in `.project/stages/planning.extra.md` (read from HEAD -- commit it)
- plan step names no declared file: '6. Update the number in `CLAUDE.md` line 107\'s `# <N> guard cases (table-driven)` to the count `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases` reports, and add to `README.md` `## Read-only stage commands`, after the paragraph ending "widening it is a human\'s commit.", the paragraph below. - README paragraph: "The built-in rules also accept a `for NAME in WORDS; do ...; done` loop whose body commands are each allowed, and `cd` into a directory inside the stage\'s worktree. A `for` loop\'s keywords are never allowed on their own, and an `[readonly] allow` entry does not widen `cd`." - Run `uv run --group dev pytest -q tests/test_stages.py::test_the_rule_file_counts_the_guard_cases`; its message `CLAUDE.md says [\'145\'], tables hold N` names N. Write N, re-run, expect `1 passed`. - Run `./pipeline/hooks/test_dangerous_commands.py`; expect last line `guard: all passed`. Commit `docs(TICKET-152): count the new guard cases and document loops and cd`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### planning

Plan written: six steps across `pipeline/hooks/dangerous-commands.py`, its test file, `CLAUDE.md` and `README.md`. `pipeline gate TICKET-152` now prints only the two expected pre-`files_declared` findings.

Committed fc7290a: `CLAUDE.md` guard-case count `138` -> `145`. Triage's 0286b05 added 7 table cases without it, and the gate reported `suite excluding ... is RED -- pre-existing breakage, fix that first` from `tests/test_stages.py::test_the_rule_file_counts_the_guard_cases`.

I prototyped `loop_bodies()` and the `cd` rule before writing the plan, and every case in steps 1 and 4 matched its expected verdict.

Out of scope, found while planning. Each needs its own ticket against the fenced guard:
1. Read-only bypass: `cat <(rm x)` returns `None` from `verdict(c, True)`. `redirection()` only flags tokens containing `>`, and `<(` runs a command.
2. `always_rules()` misses commands behind a shell keyword: `for f in a; do rm -rf /; done` and `if true; then sudo rm -rf /etc; fi` both return `None` from `verdict(c, False)`, because `argv[0]` is `do`/`then`.
3. `uv run <anything>` is allowed read-only (`GUARDED["uv"] = {"run"}`).

The JS report's `cd packages/x && npx vitest run` stays blocked on `npx` after this ticket. That project adds `npx vitest` to its `[readonly] allow`.

### 2026-10-02 02:32:24Z · planning · session · session=92f83eab-b33c-44d8-b508-27760123668a

`planning` ran as session `92f83eab-b33c-44d8-b508-27760123668a`
- replay: `claude --resume 92f83eab-b33c-44d8-b508-27760123668a`
- log: `.project/logs/TICKET-152-planning-92f83eab.log`
- cost: $2.02 of a $10 cap
- tokens: 39,796 out (22,679 thinking) · 44 in · 1,780,927 cache read · 108,090 cache write

### 2026-10-02 02:32:24Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written - nl on READ_TOOLS, loop_bodies() unwraps for loops, cd judged against a set of cwds inside PIPELINE_WORKTREE; CLAUDE.md count fixed at fc7290a

### 2026-10-02 03:02:38Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yg603htv/base
      Built pipeline @ file:///tmp/pipeline-base-yg603htv/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 42ms

```
- ok: DEC-057 is superseded -- history, not binding
- plan step has no acceptance criterion: step 1 '1. In `pipeline/hooks/test_dangerous_commands.py`, extend the tables and `tables' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 2 '2. In `pipeline/hooks/dangerous-commands.py`, add `"nl"` to the `READ_TOOLS` set' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 3 '3. In `pipeline/hooks/dangerous-commands.py`, add `LOOP_NAME` and `loop_bodies()' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 4 '4. In `pipeline/hooks/test_dangerous_commands.py`, add two tests above the `if _' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 5 '5. In `pipeline/hooks/dangerous-commands.py`, implement the `cd` rule and thread' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 6 "6. Update the number in `CLAUDE.md` line 107's `# <N> guard cases (table-driven)" -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt

### 2026-10-02 03:02:38Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- plan step has no acceptance criterion: step 1 '1. In `pipeline/hooks/test_dangerous_commands.py`, extend the tables and `tables' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 2 '2. In `pipeline/hooks/dangerous-commands.py`, add `"nl"` to the `READ_TOOLS` set' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 3 '3. In `pipeline/hooks/dangerous-commands.py`, add `LOOP_NAME` and `loop_bodies()' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 4 '4. In `pipeline/hooks/test_dangerous_commands.py`, add two tests above the `if _' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 5 '5. In `pipeline/hooks/dangerous-commands.py`, implement the `cd` rule and thread' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 6 "6. Update the number in `CLAUDE.md` line 107's `# <N> guard cases (table-driven)" -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt

### 2026-10-02 03:04:40Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-mzr3q5ar/base
      Built pipeline @ file:///tmp/pipeline-base-mzr3q5ar/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 68ms

```
- ok: DEC-057 is superseded -- history, not binding

### planning

Re-plan after the 03:02:38Z Tier A FAIL. All six findings were `plan step has no acceptance criterion`.

Fix: each `## Acceptance criteria` line now names its steps -- tables test `(steps 1-3)`, both `cd` tests `(steps 4, 5)`, count test `(step 6)`, `sed` test `(step 2)`, and the three suite and script runs `(steps 1-6)`. `## Plan`, `## Digest`, `## Decisions` and `## Rollback` are unchanged.

Baseline re-measured at fc7290a: `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py tests/test_stages.py` printed `1 failed, 56 passed in 0.90s`; the failure is the repro test.

`pipeline gate TICKET-152`, run from the project root, exits 0 with no non-ok finding. Run from the worktree, it fails with `[Errno 2] No such file or directory` on the worktree ticket mirror.

### 2026-10-02 03:05:03Z · planning · session · session=11401535-a7b6-47d2-a2a4-b66acb4cbc70

`planning` ran as session `11401535-a7b6-47d2-a2a4-b66acb4cbc70`
- replay: `claude --resume 11401535-a7b6-47d2-a2a4-b66acb4cbc70`
- log: `.project/logs/TICKET-152-planning-11401535.log`
- cost: $0.61 of a $10 cap
- tokens: 5,741 out (822 thinking) · 26 in · 585,819 cache read · 47,476 cache write

### 2026-10-02 03:05:03Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan unchanged except each acceptance criterion now names the plan steps it checks; pipeline gate TICKET-152 exits 0

### 2026-10-02 03:06:21Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-y6cr2b0m/base
      Built pipeline @ file:///tmp/pipeline-base-y6cr2b0m/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 70ms

```
- ok: DEC-057 is superseded -- history, not binding

### plan-validation

**Tier B: FAIL.** The `cd` rule has two gaps with the ticket's root cause: the guard judges `cd` against a cwd model that does not match what the shell executes.
long: two same-root-cause gaps, each needing a quoted counter-example.

Gaps (same root cause):
1. A loop body `cd` runs once per word but is judged once. `loop_bodies()` flattens the body, so `cd_verdict()` adds landing paths once. Command 1, `cd packages/x`, is allowed, and Claude Code keeps the cwd. Command 2, `for i in 1 2 3; do cd ..; done && ls`, then starts at `wt/packages/x`. The guard judges `..` as landing on `wt/packages` and allows it. The shell runs it three times and lands in `proj`. The plan's own allow case `"for f in a; do cd packages; done"` confirms that it judges a body `cd` once.
2. `LOOP_NAME` accepts any name, so a loop can assign variables the `cd` rule depends on. In `for CDPATH in /; do cd etc; done`, step 5c reads only `os.environ["CDPATH"]`, judges `etc` as `wt/etc`, and allows it. Bash searches CDPATH first and lands in `/etc`. In zsh, `cdpath` is tied to `CDPATH`. Today `CDPATH=/ cd etc` is blocked: `CDPATH=/` is argv[0].

Per item:
- Root cause: pass. The allowlist judges argv[0] of each segment. That sends loop keywords and `cd` to default deny, and `nl` is not on the allowlist.
- Decision conflict: pass. The plan keeps DEC-058's order, adds no print (DEC-106), and keeps DEC-052's comparison as `within()`.
- Scope: pass. The README and `CLAUDE.md` edits trace to step 6 and DEC-058.
- Falsifiable: fail for `cd`. No case repeats a body `cd`, and no case assigns the loop variable `CDPATH`.
- No research left: pass.
- Riskiest step: step 5 is the riskiest. The plan names it and states a fallback, but the gaps are in step 5.
- Regression surface: pass. The surface is the existing tables, `test_paths_outside_the_worktree_are_blocked` and the sed test.
- Blast radius: pass. The plan changes 4 files.

The same assignment hole affects the loop half: `for PATH in DIR; do true; done; ls` runs `DIR/ls`. Fixes for the replan:
1. Refuse `cd` inside a loop body.
2. Allowlist the loop name, and refuse `PATH`, `CDPATH`, `HOME`, `IFS` and zsh's tied arrays (`path`, `cdpath`, `fpath`).

Unverified: `CD_TARGET` admits `+`, and zsh's `cd +1` reads the directory stack. The guard blocked my probe `bash -c 'cd /usr/share/doc; for i in 1 2 3; do cd ..; done; pwd'` and its CDPATH, PATH and `zsh -fc 'cd +1'` siblings with "`cd` is not on the read-only allowlist". Gaps 1 and 2 therefore rest on documented bash semantics.

Suggested new ticket: some read-only allowlist entries already write or run programs. `uv run <anything>` passes because `GUARDED` checks only `args[0]`. `find -delete`/`-exec` and `awk 'BEGIN{system(...)}'` pass `READ_TOOLS`.

### 2026-10-02 03:09:07Z · plan-validation · session · session=b280128d-520d-40eb-9907-5de26f1266a0

`plan-validation` ran as session `b280128d-520d-40eb-9907-5de26f1266a0`
- replay: `claude --resume b280128d-520d-40eb-9907-5de26f1266a0`
- log: `.project/logs/TICKET-152-plan-validation-b280128d.log`
- cost: $0.90 of a $3 cap
- tokens: 15,820 out (10,809 thinking) · 18 in · 457,163 cache read · 61,329 cache write

### 2026-10-02 03:09:07Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ cd rule has same-root-cause gaps: a loop body cd runs once per word but is judged once, and a for loop can assign CDPATH/PATH, which the guard never sees

### 2026-10-02 03:19:04Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-62yhs2n2/base
      Built pipeline @ file:///tmp/pipeline-base-62yhs2n2/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 60ms

```
- ok: DEC-057 is superseded -- history, not binding

### planning

Re-plan after the 03:09:07Z Tier B `bad-plan`. Both gaps are closed in steps 3 and 5.

1. Gap 1, a body `cd` judged once: `loop_bodies()` refuses any `cd` in a loop body. Test case: `for i in 1 2 3; do cd ..; done && ls` from `wt/packages/x` is blocked.
2. Gap 2, the loop assigns variables: `LOOP_NAME` is now `[a-z]`. `zsh -fc` lists its one-char specials as `! # $ * - 0 ? @ _`, and bash has no one-letter special. Table cases cover `PATH`, `CDPATH` and `path`.
3. Same root cause, found while replanning: the variable's value bypassed `sed_is_a_line_print()`. Each probe truncated `x`, so `sed -i` ran: `for f in -i; do true; done; sed -n 1p $f x` (bash), plus zsh's `$f:s/x/-/` and `${f/x/-}`. The fix judges bodies verbatim and once per word, allows only plain `$name` expansions, and scopes each name to its loop.
4. `cd` targets must be `.`, `..`, absolute, or `./`/`../`-led, and must already exist. Bash took a CDPATH hit over the cwd (`.../c/q`), and the hook cannot see a profile-only CDPATH. The previous `CDPATH` env check is gone.

A scratch prototype passed every case in steps 1 and 4, plus all 12 existing guard tests. `pipeline gate TICKET-152` printed `gate: PASS`.

Out of scope, pre-existing on main: `verdict("sed -n 1p ${PWD/*/-i} x", True)` returns `None`.

### 2026-10-02 03:19:35Z · planning · session · session=1e3c5a6d-3103-43ed-ae70-a250df8849a4

`planning` ran as session `1e3c5a6d-3103-43ed-ae70-a250df8849a4`
- replay: `claude --resume 1e3c5a6d-3103-43ed-ae70-a250df8849a4`
- log: `.project/logs/TICKET-152-planning-1e3c5a6d.log`
- cost: $2.24 of a $10 cap
- tokens: 48,974 out (25,600 thinking) · 46 in · 1,884,699 cache read · 110,062 cache write

### 2026-10-02 03:19:35Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replan closes both Tier B gaps: cd in a loop body is refused, and the loop variable is a one-letter name judged per word and scoped to its loop; pipeline gate TICKET-152 prints gate: PASS

### 2026-10-02 03:20:53Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-pnvbv03g/base
      Built pipeline @ file:///tmp/pipeline-base-pnvbv03g/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 61ms

```
- ok: DEC-057 is superseded -- history, not binding

### plan-validation

**Tier B: FAIL.** Step 3's scope check misses nested loops. That reopens measured hole 1 (the variable outlives its loop).
long: two same-root-cause gaps, each with a traced counter-example, plus one fail-open.

Gaps (same root cause), traced through step 3's exact body:
1. `for f in x; do for g in -i; do true; done; sed -n 1p $g x; done` is allowed. `names = {a[1] for a in segs if a and a[0] == "for" ...}` reads segments before `do` is stripped. The inner segment is `['do','for','g','in','-i']`, so `g` never enters `names` and `$g` skips the scope check. Verbatim `sed -n 1p $g x` passes `sed_is_a_line_print()`; the shell runs `sed -n 1p -i x`.
2. `for f in x; do for f in -i; do true; done; sed -n 1p $f x; done` is allowed. The outer `f` is in `scope`, but the inner loop left `f=-i`. The outer pass substitutes only `x`.
3. Fail-open, plan's own code: each `done` multiplies the body by (words + 1). Nine nested loops of nine words build 10^9 argv lists. A `MemoryError` exits 1, which the Digest says lets the command run. Default deny for a body `rm` runs only after `loop_bodies()`.

Fix shape: collect names after stripping `do`, refuse a `for` whose name is on the stack, and cap the expanded size with a reason.

Per item:
- Root cause: pass. The allowlist judges each segment's argv[0], so `nl`, the loop keywords and `cd` reach default deny. The plan fixes that.
- Decision conflict: pass. DEC-058 order kept; `cd` sits above the prefix match. DEC-106: `sed` stays off `READ_TOOLS`. DEC-052: `within()` keeps the comparison.
- Scope: pass. Every step traces to a criterion or DEC-058.
- Falsifiable: fail. No case nests a loop under `do for`, shadows a name, or nests deeply.
- No research left: pass.
- Riskiest step: pass on form. Step 5 is named with a fallback. The gaps are in step 3, whose fallback is `blocked`.
- Regression surface: pass. The `$` check applies only to commands with a loop. The existing tables, `test_paths_outside_the_worktree_are_blocked` and the sed test cover the rest.
- Blast radius: pass. 4 files.

Unverified: I ran no shell or Python (read-only). Gaps 1-2 are traced by hand. The 10^9 size is arithmetic, not a timing.

Suggested new ticket (different root cause, pre-existing on main):
- `echo -i; sed -n 1p $_ x` passes the `sed` shape; bash expands `$_` to `-i`.
- `find -delete`, `awk 'BEGIN{system(...)}'`, `sort -o` write through `READ_TOOLS` entries.

### 2026-10-02 03:23:48Z · plan-validation · session · session=8565644b-f22a-47b5-8b5f-296faddf77de

`plan-validation` ran as session `8565644b-f22a-47b5-8b5f-296faddf77de`
- replay: `claude --resume 8565644b-f22a-47b5-8b5f-296faddf77de`
- log: `.project/logs/TICKET-152-plan-validation-8565644b.log`
- cost: $0.89 of a $3 cap
- tokens: 16,221 out (12,956 thinking) · 16 in · 386,755 cache read · 61,373 cache write

### 2026-10-02 03:23:48Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ loop scope check misses nested loops: names collects only segments whose argv[0] is for, so `do for g in -i` escapes it, and a shadowed name passes; both let sed -n 1p $g x run sed -i. Body expansion is also unbounded, (w+1)^depth, so the hook can crash open

### 2026-10-02 03:31:07Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-fpkwslej/base
      Built pipeline @ file:///tmp/pipeline-base-fpkwslej/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 70ms

```
- ok: DEC-057 is superseded -- history, not binding

### planning

Re-plan after the 03:23:48Z Tier B `bad-plan`. Step 3 now refuses nested loops, and a `$` may name only the loop enclosing it. No `rejection` entries exist.

1. Gap 1 (`do for g in -i` escaped `names`) and gap 2 (shadowing `for f`): both are nested loops. Each now returns `a `for` loop inside another `for` loop is not a read-only loop`. The `names`/`scope` sets are gone.
2. Gap 3, (words + 1)^depth: without nesting the expansion is linear in command length. The 9-deep case returns the same reason.
3. Also found: `for f in *` assigns real filenames, and bash splits an unquoted `$f`. `LOOP_WORD` now refuses globs and a leading `=` (zsh `=cmd`).
4. Step 1 adds 9 BLOCKED and 2 ALLOWED cases. The nested `cat $a $b` case moves from ALLOWED to BLOCKED.

A scratch prototype matched every step-1 and step-4 case and passed all 12 existing guard tests. On the unmodified guard the tables still fail first on `nl foo.py`. `pipeline gate TICKET-152` printed `gate: PASS`.

Suggested new ticket (pre-existing on main, different root cause): `printf -v f %s -i; sed -n 1p $f x`. The unmodified guard returns `None`, and in a temp dir `x` went from 4 to 2 bytes, so `sed -i` ran. Same class as `$_` and `${PWD/*/-i}`: an unknown `$` value reaches the `sed` shape.

### 2026-10-02 03:31:37Z · planning · session · session=a0f42788-02a4-44b0-9570-a419a50c580a

`planning` ran as session `a0f42788-02a4-44b0-9570-a419a50c580a`
- replay: `claude --resume a0f42788-02a4-44b0-9570-a419a50c580a`
- log: `.project/logs/TICKET-152-planning-a0f42788.log`
- cost: $2.15 of a $10 cap
- tokens: 36,206 out (14,549 thinking) · 66 in · 2,762,229 cache read · 109,203 cache write

### 2026-10-02 03:31:37Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replan refuses nested for loops and lets a $ name only its enclosing loop, closing the do-for scope escape, the shadowing rewrite and the (w+1)^depth crash-open; loop words also drop globs and leading =; pipeline gate TICKET-152 prints gate: PASS

### 2026-10-02 03:32:55Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-78nv8l_p/base
      Built pipeline @ file:///tmp/pipeline-base-78nv8l_p/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 78ms

```
- ok: DEC-057 is superseded -- history, not binding

### plan-validation

**Tier B: FAIL.** A loop hides its body's program from `always_rules()`, and a project prefix then allows it. This breaks DEC-058, and its root cause matches the ticket's: a rule keyed on `argv[0]` sees a shell keyword, not the program.
long: one same-root-cause gap with a traced counter-example, plus nine per-item scores.

Gap, traced through the current `verdict()` plus step 3:
1. `verdict()` calls `always_rules(segs, command)` before `readonly_rules()`. The body segment is `['do','git','-C','vendor','push','--force','origin','main']`, so `name` is `do` and the `git` push branch never runs.
2. `loop_bodies()` strips `do` and returns `['git','-C','vendor','push','--force','origin','main']`.
3. With `[readonly] allow = ["git -C vendor"]`, the prefix match `continue`s. The result is `None`, so the force push runs.
Without the loop, `always_rules()` returns `force push` first. DEC-058 line 10: "a project entry can never re-enable `sudo`, `rm -rf /`, `git push --force`, `git worktree remove`". The plan claims "This plan keeps that order". A per-word value hides a flag the same way: `for f in --force; do git -C vendor push $f origin main; done`.
Fix shape: run `always_rules()` over `loop_bodies()`' output inside `readonly_rules()`. Add a project-prefix table case that wraps an always-refused command in a loop.

Per item:
- Root cause: pass. Rules judge each segment's `argv[0]`, so `nl`, `for`/`do`/`done` and `cd` reach default deny.
- Decision conflict: fail (above). DEC-106 and DEC-052 comply.
- Scope: pass. Every step traces to a criterion or to DEC-058's count rule.
- Falsifiable: fail. No case pins prefix-vs-always through a loop. The other cases are concrete and would flip.
- No research left: pass. Exact bodies, files and line numbers are given.
- Riskiest step: pass. Step 5 has a fallback, and step 3's is `blocked`.
- Regression surface: pass. The existing tables, `test_paths_outside_the_worktree_are_blocked` (`within()`), `test_end_to_end_exit_code` and the default `cwd=None` cover it.
- Blast radius: pass. 4 files: the guard, its tests, and 2 doc lines.

Unverified: I traced the gap by reading the code. The guard blocked `cd` and a pipe into `python3`. I would have piped the event into the hook with `PIPELINE_READONLY=1 PIPELINE_READONLY_ALLOW='[["git","-C","vendor"]]'`.

Suggested new ticket (different root cause, pre-existing on main): `find` and `awk` are in `READ_TOOLS` with no argument check. By reading, `find . -delete` and `awk 'BEGIN{system("rm x")}'` pass the read-only rules.

### 2026-10-02 03:36:00Z · plan-validation · session · session=9600bd2a-866b-4792-bb6a-3912ebde7400

`plan-validation` ran as session `9600bd2a-866b-4792-bb6a-3912ebde7400`
- replay: `claude --resume 9600bd2a-866b-4792-bb6a-3912ebde7400`
- log: `.project/logs/TICKET-152-plan-validation-9600bd2a.log`
- cost: $1.06 of a $3 cap
- tokens: 17,337 out (12,871 thinking) · 26 in · 758,735 cache read · 70,270 cache write

### 2026-10-02 03:36:00Z · plan-validation · transition · to=escalated · result=bad-plan · marker=yes

**plan-validation -> escalated** (result: `bad-plan`)

✓ always_rules() judges the do-prefixed segment before loop_bodies() strips do, so a loop hides the body program from it and a project prefix then allows it: with allow git -C vendor, for f in a; do git -C vendor push --force origin main; done passes. Breaks DEC-058, same argv[0]-is-a-keyword root cause

### 2026-10-02 03:50:42Z · human · note · by=chezzijr

**resumed** by chezzijr -> `planning`, reset [], granted `plan_validation_attempts` 3 -> 2

### 2026-10-02 03:50:42Z · human · answer · by=chezzijr

**note from chezzijr**

Run always_rules() on loop_bodies() output; add a table case wrapping an always-refused command in a loop under a project allow prefix.

### 2026-10-02 04:26:41Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-if1mzlhs/base
      Built pipeline @ file:///tmp/pipeline-base-if1mzlhs/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 74ms

```
- ok: DEC-057 is superseded -- history, not binding

### planning

Replanned per the 03:50:42Z answer. `readonly_rules()` now re-runs `flatten()` and `always_rules()` over `loop_bodies()` output, above the prefix loop (step 3). Step 1 adds `["git", "-C", "vendor"]` to `PROJECT_PREFIXES`, 3 `ALLOWED_PROJECT` cases and 4 `BLOCKED_PROJECT` cases.

Evidence, from a scratch prototype (deleted afterwards):
1. The four block cases returned `'force push'`, `'force push'`, `'direct push to the default branch'`, `'force push'`.
2. With the second `always_rules()` call stubbed out, all four returned `None`.
3. Every step-1 and step-4 case and every existing guard test passed.

Baseline is unchanged: `1 failed, 56 passed`. `pipeline gate` printed `gate: PASS`.

Findings outside this stage's scope:
1. In write stages (`readonly=False`), `always_rules()` still sees a loop body as `do ...`. So `for f in a; do git push --force origin x; done` skips the force-push rule. Measured on the unmodified guard: `verdict(..., False)` returned `None` for the loop and `'force push'` for `git push --force origin x`. This is pre-existing on main, and step 3 changes only the read-only path. It may need its own ticket.
2. The worktree mirror `.project/tickets/TICKET-152.md` is missing. `pipeline gate TICKET-152` run from the worktree failed with `[Errno 2] No such file or directory`, so I ran `pipeline --project /home/chezzijr/proj/agent-pipeline gate TICKET-152`.

### 2026-10-02 04:27:27Z · planning · session · session=4b8eb2cf-bfac-4ec4-9fdb-a000b3707a39

`planning` ran as session `4b8eb2cf-bfac-4ec4-9fdb-a000b3707a39`
- replay: `claude --resume 4b8eb2cf-bfac-4ec4-9fdb-a000b3707a39`
- log: `.project/logs/TICKET-152-planning-4b8eb2cf.log`
- cost: $1.62 of a $10 cap
- tokens: 24,766 out (7,418 thinking) · 54 in · 2,004,631 cache read · 90,828 cache write

### 2026-10-02 04:27:27Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ replan re-runs flatten() and always_rules() over loop_bodies() output above the prefix loop, and adds git -C vendor project-prefix cases wrapping a force push and a push to main in a loop; prototype blocked all four, and each flips to allowed without the second pass; pipeline gate prints gate: PASS

### 2026-10-02 04:28:45Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:32:02Z · plan-validation · gate · verdict=FAIL` --*
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-aj0cxoru/base
      Built pipeline @ file:///tmp/pipeline-base-aj0cxoru/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 64ms

```
- ok: DEC-057 is superseded -- history, not binding

### plan-validation

**Tier B: ok.** All eight items pass.

1. Root cause: pass. The read-only allowlist has no rule for `nl`, `for` loop syntax or `cd`. The splitter emits the loop keywords as `argv[0]`, so default deny at `dangerous-commands.py:350` refuses them. Steps 2, 3 and 5 add a rule for each. None of them only silences a test.
2. Decisions: pass. Step 3 keeps DEC-058's order: redirection and substitution first, then `loop_bodies()`, then `flatten()` and `always_rules()`, then the prefix loop. The `cd` rule sits above the prefix match. DEC-106: `sed` stays off `READ_TOOLS`, and nothing new prints. DEC-052: `within()` is extracted from line 398 unchanged.
3. Scope: pass. Each step maps to a criterion. The `git -C vendor` prefix pins the 03:50:42Z answer.
4. Falsifiable: pass. The planner's prototype returned `None` for all four `BLOCKED_PROJECT` loop cases once the second `always_rules()` call was stubbed out. The e2e `cd` test runs from `proj`, so a guard that ignores the event `cwd` blocks `cd ./packages`.
5. No research left: pass. Every anchor exists: `READ_TOOLS` at line 53, `tables()` at line 188, `CLAUDE.md:107` (`145`), `README.md:861`/`:873`, and `tests/test_stages.py:432`.
6. Riskiest step: step 5, the `cd` rule. `## Rollback` names its fallback.
7. Regression surface: `test_paths_outside_the_worktree_are_blocked` covers `path_verdict()` through `within()`. The new `cwd` keyword defaults to `None`. The existing tables cover the rest.
8. Blast radius: pass. This `feature` ticket touches 2 code files and 2 doc lines.

Suggested new ticket: in write stages (`readonly=False`), `always_rules()` still receives a loop body as `do ...`. The planner measured `verdict(..., False)` returning `None` for `for f in a; do git push --force origin x; done`. That gap exists on main without this ticket. Its cause is in `always_rules()`, not in the read-only allowlist. So it is not this ticket's root cause, and it does not fail this plan.

### 2026-10-02 04:31:06Z · plan-validation · session · session=5445a83f-de0f-4e79-b246-56f1cabb0979

`plan-validation` ran as session `5445a83f-de0f-4e79-b246-56f1cabb0979`
- replay: `claude --resume 5445a83f-de0f-4e79-b246-56f1cabb0979`
- log: `.project/logs/TICKET-152-plan-validation-5445a83f.log`
- cost: $0.89 of a $3 cap
- tokens: 13,177 out (8,800 thinking) · 20 in · 484,239 cache read · 65,633 cache write

### 2026-10-02 04:31:06Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ all eight items pass; the plan extends the allowlist to nl, flat for loops and in-worktree cd, re-runs flatten() and always_rules() on loop bodies per the 03:50:42Z answer, and names a fallback for step 5; write-stage loop gap filed as a suggested new ticket

### 2026-10-02 04:31:41Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-02 04:53:17Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails as required
```
check(ALLOWED_READONLY, True, False, "readonly")
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cmds = ['pytest -x', 'git diff main...HEAD', 'grep -rn foo .', 'git log --oneline', 'cat thing.py', 'python3 -m pytest --deselect x', ...]
readonly = True, expect_block = False, label = 'readonly'

    def check(cmds, readonly, expect_block, label):
        for c in cmds:
            got = guard.verdict(c, readonly)
>           assert bool(got) == expect_block, \
                f"{label}: {c!r} -> {got!r} (expected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables` fails on base `main` too -- the bug is not already fixed upstream
```
xpected {'block' if expect_block else 'allow'})"
E           AssertionError: readonly: 'nl foo.py' -> '`nl` is not on the read-only allowlist' (expected allow)
E           assert True == False
E            +  where True = bool('`nl` is not on the read-only allowlist')

pipeline/hooks/test_dangerous_commands.py:143: AssertionError
=========================== short test summary info ============================
FAILED pipeline/hooks/test_dangerous_commands.py::test_the_allow_and_block_tables
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-lop_h8m0/base
      Built pipeline @ file:///tmp/pipeline-base-lop_h8m0/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 73ms

```
- ok: DEC-057 is superseded -- history, not binding

### 2026-10-02 04:53:18Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-10-02 · implementing · note

Plan steps 1-6 done, in order, TDD.
- [x] 1 tables extended; RED on `nl foo.py` (`1 failed`)
- [x] 2-3 `nl`, `loop_bodies()`, second `always_rules()` pass; tables `1 passed`; commit 65e7e9c
- [x] 4 two `cd` tests; RED: `TypeError: verdict() got an unexpected keyword argument 'cwd'`, and exit 2 for `cd ./packages && ls`
- [x] 5 `cd_verdict()`, `within()`, event `cwd`; `14 passed`
- [x] 6 CLAUDE.md count 145 -> 182, README paragraph

Results: `pytest pipeline/hooks/test_dangerous_commands.py tests/test_stages.py` -> `62 passed`; `./pipeline/hooks/test_dangerous_commands.py` ends `guard: all passed`; `pytest tests/` -> `725 passed`.
Guard is fenced: parks at `awaiting-merge`.

### 2026-10-02 04:56:23Z · implementing · session · session=d51dce72-6eaf-4f37-896c-539b076ac547

`implementing` ran as session `d51dce72-6eaf-4f37-896c-539b076ac547`
- replay: `claude --resume d51dce72-6eaf-4f37-896c-539b076ac547`
- log: `.project/logs/TICKET-152-implementing-d51dce72.log`
- cost: $0.63 of a $9 cap
- tokens: 14,049 out (409 thinking) · 40 in · 1,152,245 cache read · 65,671 cache write

### 2026-10-02 04:56:23Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ nl, flat for loops and in-worktree cd allowed in read-only stages; 725 tests and guard script pass

### 2026-10-02 · review · findings

long: the blocking finding needs its input, the arithmetic and the refutation attempt.

First pass, delta `main...HEAD` (5a503b1..d90e31b). The code matches `## Plan` step for step. Every acceptance criterion passes: two files `62 passed`; script ends `guard: all passed`; `pytest tests/` `725 passed in 76.56s`.

1. **Blocking.** One flat loop can make the guard fail open. `loop_bodies()` at `done` runs `out.extend(body + [... for w in words for c in body])`, which builds B x (W + 1) argv lists before any rule judges them. B and W both grow with command length, so the cost is quadratic, not "linear in the command's length" as `## Digest` states. Input: `for f in ` + `a ` x 10000 + `; do ` + `true; ` x 10000 + `rm -rf x; done` is about 80KB and builds about 10^8 lists, at least 6.4GB at 64 bytes each. `main()` wraps only the event parse in `try` (line 625), so a `MemoryError` exits 1, and Claude Code then runs the command. That is the failure `## Decisions` refused nesting for. I did not measure it: a read-only stage cannot run an ad-hoc script. Refutation tried: no length cap exists (`grep -n 'len(command\|MAX_\|limit'` finds none in the guard), and the hook registration at `pipeline/core/config.py:904` sets no timeout. Fix: cap B x (W + 1) and return a reason before `extend`, with a table case.
2. Nit, not blocking: the step-3 comment in `readonly_rules()` is one line of about 200 characters, exactly as the plan wrote it.

### 2026-10-02 05:00:42Z · review · session · session=c9ed8033-7f14-46bd-a5e7-d7355e16b82c

`review` ran as session `c9ed8033-7f14-46bd-a5e7-d7355e16b82c`
- replay: `claude --resume c9ed8033-7f14-46bd-a5e7-d7355e16b82c`
- log: `.project/logs/TICKET-152-review-c9ed8033.log`
- cost: $0.94 of a $5 cap
- tokens: 14,319 out (10,753 thinking) · 22 in · 589,850 cache read · 67,392 cache write

### 2026-10-02 05:00:42Z · review · transition · to=implementing · result=fail · marker=yes

**review -> implementing** (result: `fail`)

✓ one blocking finding: loop_bodies() expands a single loop to B x (W + 1) argv lists, quadratic in command length, so an ~80KB loop can exhaust memory and the hook exits 1, which runs the command; all acceptance tests pass

### 2026-10-02 · implementing · note

Fixed the review's blocking finding in d8e0462. `loop_bodies()` returns a reason when `len(out) + len(body) * (len(words) + 1)` exceeds `MAX_LOOP_COMMANDS` (2000), before `extend`.
- RED: new table case (50 words, 51 body commands) expected block, got allow.
- Added 3 `BLOCKED_READONLY` cases: 50 x 51 loop, 3000-command body, 3000 sequential loops. `CLAUDE.md` count 182 -> 185.
- GREEN: `62 passed` on the two files; the script ends `guard: all passed`.

### 2026-10-02 05:01:26Z · implementing · session · session=7e1c7e08-ea27-466e-a3af-c1f979f89df3

`implementing` ran as session `7e1c7e08-ea27-466e-a3af-c1f979f89df3`
- replay: `claude --resume 7e1c7e08-ea27-466e-a3af-c1f979f89df3`
- log: `.project/logs/TICKET-152-implementing-7e1c7e08.log`
- cost: $0.33 of a $9 cap
- tokens: 4,391 out (517 thinking) · 22 in · 479,060 cache read · 46,432 cache write

### 2026-10-02 05:01:26Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ capped for-loop expansion at 2000 commands so the guard cannot MemoryError; 3 new table cases, tests pass

### 2026-10-02 · review · findings

long: the finding needs its input, the arithmetic and the refutation attempt.

Second pass, delta `d90e31b..d8e0462`. The first review's finding is only partly fixed. Acceptance criteria pass: two files `62 passed in 1.08s`; script `guard: all passed`; `pytest tests/` `725 passed in 77.22s`.

1. **Blocking.** `MAX_LOOP_COMMANDS` caps the number of argv lists, but the cost is their tokens. `dangerous-commands.py:200` checks `len(body) * (len(words) + 1)`. Line 203 then calls `substitute()` once per token per word. Total work is (W + 1) x body tokens, still quadratic in command length.
   Input: `for f in ` + `a ` x 1999 + `; do cat` + ` x` x 250000 + `; done`, about 504KB. The check sees 1 x 2000 = 2000, which is not `> 2000`. The expansion then builds 2000 lists of 250001 tokens: about 5 x 10^8 `substitute()` calls and 4GB of list pointers alone. A `MemoryError` exits 1 and the command runs. I did not measure it: the guard refuses ad-hoc Python in this stage.
   Refutation tried: `main()` and `segments()` have no size cap (grep for `len(command`, `MAX_` finds only line 132). The body has no `$`, and `a` matches `LOOP_WORD`, so no earlier check returns.
   Fix: cap `sum(len(c) for c in body) * (len(words) + 1)` plus the tokens already in `out`. Add a table case with few words and one long body command, e.g. 100 words x a 1000-token `cat`.
2. Nit, carried over: the step-3 comment at line 456 is one 200-character line.

### 2026-10-02 05:04:45Z · review · session · session=783e1f9f-2c05-470b-b939-f5e42d8148f6

`review` ran as session `783e1f9f-2c05-470b-b939-f5e42d8148f6`
- replay: `claude --resume 783e1f9f-2c05-470b-b939-f5e42d8148f6`
- log: `.project/logs/TICKET-152-review-783e1f9f.log`
- cost: $0.79 of a $5 cap
- tokens: 10,353 out (6,412 thinking) · 26 in · 643,937 cache read · 56,547 cache write

### 2026-10-02 05:04:45Z · review · transition · to=escalated · result=fail · marker=yes

**review -> escalated** (result: `fail`)

✓ one blocking finding: MAX_LOOP_COMMANDS caps argv lists, not tokens, so one 2000-word loop over a 250000-token body still builds about 5x10^8 tokens; acceptance tests pass

### 2026-10-02 07:13:48Z · human · note · by=chezzijr

**resumed** by chezzijr -> `implementing`, reset [], granted `review_loops` 2 -> 1

### 2026-10-02 07:13:48Z · human · answer · by=chezzijr

**note from chezzijr**

Cap total expanded tokens, not argv count. Make main() fail closed: catch any exception and exit 2.

### 2026-10-02 · implementing · note

Addressed the review's blocking finding.
- `MAX_LOOP_COMMANDS` is now `MAX_LOOP_TOKENS` (5000): `loop_bodies()` sums body tokens x (words + 1) across loops and refuses past the cap before any expansion.
- `main()` wraps `decide()` and exits 2 on any exception (`BaseException`); a malformed JSON event still exits 0, as before.
- New table cases: 60 words x 51 commands, 100 words x 1000-token `cat`, one 250000-token body, 1500 sequential loops. New test `test_an_exception_in_the_guard_blocks_instead_of_exiting_1` (a list `tool_input` raises).
- `CLAUDE.md` count 185 -> 188. `63 passed`; script ends `guard: all passed`.
- Not shown RED first for the two code changes; the old 2000-command check let the 250000-token body through per the review's arithmetic.

### 2026-10-02 07:15:08Z · implementing · session · session=69348fed-feab-4eb3-8800-5c451508ac2d

`implementing` ran as session `69348fed-feab-4eb3-8800-5c451508ac2d`
- replay: `claude --resume 69348fed-feab-4eb3-8800-5c451508ac2d`
- log: `.project/logs/TICKET-152-implementing-69348fed.log`
- cost: $0.36 of a $9 cap
- tokens: 5,771 out (1,001 thinking) · 24 in · 543,626 cache read · 49,147 cache write

### 2026-10-02 07:15:08Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ capped loop expansion by total tokens (5000) and made main() exit 2 on any exception; 63 tests pass

### 2026-10-02 · review · findings

Third pass, delta `d8e0462..dc643de`. No blocking findings. The prior blocking finding is resolved.

- `dangerous-commands.py:201` adds `sum(len(c) + 1 for c in body) * (len(words) + 1)` to `spent` and refuses past 5000 before line 205 expands. The review's input (2000 words x 250000-token body) now refuses before any expansion. Table cases at `test_dangerous_commands.py:108-110` pin it.
- `main()` (line 637) catches `BaseException` from `decide()` and returns 2. `decide()` has no `sys.exit` (grep: the only one is line 679), so no allow path turns into a block. The new test fails if the `try` is removed: an `AttributeError` exits 1.
- `CLAUDE.md` 185 -> 188 matches +3 table cases (one existing case changed 50 -> 60 words).

Measured: two files `63 passed in 1.51s`; script last line `guard: all passed`. I did not re-run `pytest tests/`; the delta touches only the guard, its tests and the `CLAUDE.md` count.

1. Note, not blocking. The cap counts tokens, not characters. A body token of L characters that holds `$f` is copied once per word, up to about 1600 x L. A model-sized command (about 500KB) gives about 800MB of copies. A `MemoryError` now exits 2. Only an OOM kill or a hook timeout would still run the command. I could not measure it: the guard refuses ad-hoc Python here.
2. Nit, carried over: line 458 is one 203-character comment line.

### 2026-10-02 07:16:38Z · review · session · session=d51c42d1-f974-434f-a76e-ad4113f900fa

`review` ran as session `d51c42d1-f974-434f-a76e-ad4113f900fa`
- replay: `claude --resume d51c42d1-f974-434f-a76e-ad4113f900fa`
- log: `.project/logs/TICKET-152-review-d51c42d1.log`
- cost: $0.64 of a $5 cap
- tokens: 7,578 out (4,328 thinking) · 18 in · 401,432 cache read · 50,526 cache write

### 2026-10-02 07:16:38Z · review · transition · to=holistic-review · result=ok · marker=yes

**review -> holistic-review** (result: `ok`)

✓ token cap and fail-closed main() resolve the prior blocking finding; 63 passed, guard: all passed; two non-blocking notes

### 2026-10-02 · holistic-review · findings

Coherent. The diff `main...HEAD` (5 commits, 4 files) does what plan steps 1-6 say. The two extras are `MAX_LOOP_TOKENS` and fail-closed `main()`/`decide()`. The human asked for both at 07:13:48Z.

- Order holds across iterations: redirection/substitution, `loop_bodies()`, `flatten()` + second `always_rules()`, then `cd` above the prefix match (DEC-058).
- The token cap sits inside `loop_bodies()` before expansion, so a later fix did not bypass the nesting refusal or the scope checks.
- `within()` is shared by `path_verdict()` and `cd_verdict()`. Error handling is consistent: each new path returns a reason, and `main()` now backs that with exit 2.
- Measured: `uv run --group dev pytest -q pipeline/hooks/test_dangerous_commands.py tests/test_stages.py` -> `63 passed in 1.50s`.

Note, not blocking: dc643de made three rationale comments stale. Each says an exception "exits 1" and runs the command, which `main()` now prevents:
1. `dangerous-commands.py:131`
2. `dangerous-commands.py:159`
3. `dangerous-commands.py:420`

The `## Decisions` nesting bullet says the same. The cap and the never-raise rule stay worth keeping as defence in depth, but those lines no longer describe the reason correctly.

### 2026-10-02 07:17:26Z · holistic-review · session · session=9e4ad459-435b-4d2f-87dd-b7d58d733e98

`holistic-review` ran as session `9e4ad459-435b-4d2f-87dd-b7d58d733e98`
- replay: `claude --resume 9e4ad459-435b-4d2f-87dd-b7d58d733e98`
- log: `.project/logs/TICKET-152-holistic-review-9e4ad459.log`
- cost: $0.52 of a $5 cap
- tokens: 3,761 out (1,094 thinking) · 14 in · 298,251 cache read · 47,844 cache write

### 2026-10-02 07:17:26Z · holistic-review · transition · to=verifying · result=ok · marker=yes

**holistic-review -> verifying** (result: `ok`)

✓ accumulated diff matches the plan plus the two human-requested additions; 63 passed; one non-blocking note on comments made stale by fail-closed main()

### 2026-10-02 07:18:45Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/hooks/dangerous-commands.py`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-152` lands it; `pipeline resume TICKET-152 --stage planning` sends it back.

### 2026-10-02 07:23:42Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-02 07:25:18Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/152


Rebasing (1/7)Rebasing (2/7)Rebasing (3/7)Rebasing (4/7)Rebasing (5/7)Rebasing (6/7)Rebasing (7/7)Successfully rebased and updated refs/heads/ticket/152.
Already up to date.
Updating fbb27de..9971c10
Fast-forward
 CLAUDE.md                                 |   2 +-
 README.md                                 |   2 +
 pipeline/hooks/dangerous-commands.py      | 191 +++++++++++++++++++++++++++++-
 pipeline/hooks/test_dangerous_commands.py | 149 ++++++++++++++++++++++-
 4 files changed, 335 insertions(+), 9 deletions(-)

```

### 2026-10-02 07:25:18Z · merging · decision

decision recorded as `DEC-152`
