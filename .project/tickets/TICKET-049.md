---
id: TICKET-049
stage: done
class: feature
branch: ticket/049
test_file: tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference
files_declared:
- README.md
- pipeline/cli/main.py
- tests/test_cli.py
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
  id: a5ba0be5-f4f6-4a83-8096-aa4ed3c65497
  log: .project/logs/TICKET-049-review-a5ba0be5.log
approved_by: chezzijr
approved_at: '2026-08-24T09:19:45.841032+00:00'
---

## Summary
`review` passed the branch with no blocking findings. `implementing` executed
the approved plan in `b0ab370`, touching `pipeline/cli/main.py`, `README.md`
and `tests/test_cli.py`. `pipeline start --help` and `pipeline run --help` now
each carry a `description=` (`START_DESC` / `RUN_DESC`) naming `planning` as
the interactive stage, `pipeline tui` (start) or headless (run). `README.md`
lines 65 and 119 say the same, and a third sentence after line 190 points at
the drift test. `tests/test_cli.py` gained
`test_the_help_text_matches_the_code_it_describes`, next to triage's
`test_start_and_run_help_explain_the_interactive_stage_difference` (unedited).
`uv run --group dev pytest -q tests/test_cli.py tests/test_stages.py` ->
`28 passed in 2.68s`. `review` also proved the drift test non-vacuous: it fails
when `Poller.attachable` is true and when a second stage declares
`mode: interactive`. Two non-blocking nits are in the thread, both about the
test's README matchers being formatting-sensitive.

## Reproduction

`tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference`

Command: `uv run --group dev pytest -q tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference`

expect: AssertionError: usage: __main__.py start [-h] [--interval INTERVAL] [--harness HARNESS]

Failure output confirms `pipeline start --help` and `pipeline run --help` stdout contain no occurrence of "interactive" (case-insensitive). Verified directly at commit 80965a8 with `uv run pipeline start --help` and `uv run pipeline run --help`: neither mentions interactive stages, attaching, or permission prompts, matching the ticket's summary.

## Digest

Files touched: `pipeline/cli/main.py` (lines 475 and 477, the `start` and `run`
`add_parser` calls, each one dense line), `README.md` (lines 65, 119 and the
`## Interactive stages` section at 172-190), `tests/test_cli.py` (triage's
failing test at lines 39-48, committed at c651348 -- do not weaken it).

**The ticket's stated fix location is not sufficient.** `help=` never reaches
`pipeline start --help`. argparse's `add_parser` pops `help` into the parent's
subcommand listing and does not set `description`. Verified: `uv run python -m
pipeline start --help` prints `usage: __main__.py start ...` plus `options:`
and nothing else. The fix must pass `description=` too, or the reproduction
test stays red.

Entry point: `main()` at `pipeline/cli/main.py:454` builds the whole parser
inline. There is no `build_parser()` factory, so a test reads help text by
subprocess -- the pattern `tests/test_cli.py::cli` already uses.

The behaviour the help text asserts, each verified in code: `Server.attachable
is True` (`pipeline/daemon/server.py:213`), `Poller.attachable is False`
(`pipeline/daemon/server.py:138`), `run()` builds a bare `Poller`
(`pipeline/daemon/supervisor.py:1100`), `pipelined` builds a `Server`
(`pipeline/daemon/main.py:35`), and `spawn()` runs a `mode: interactive` stage
headless when `poller.attachable` is false (`pipeline/daemon/supervisor.py:350`).
`planning` is the only stage declaring `mode: interactive`; verified with
`[s for s in agent_stages() if stage_config(s).get('mode') == 'interactive']`
-> `['planning']`.

Gotchas:

- argparse wraps `description` at `$COLUMNS` (80 when stdout is not a tty), so a
  test asserting a two-word phrase must normalise whitespace first:
  `" ".join(stdout.split())`.
- `python -m pipeline` imports `pyte` eagerly. Run every command under `uv run`,
  or the import dies with `ModuleNotFoundError: No module named 'pyte'`.
- `.claude/skills/file-ticket/SKILL.md` lines 137-140 already state this
  difference correctly. No change is needed there, so the CLAUDE.md rule that a
  CLI change is unfinished until the skill agrees is already satisfied.
- `pipeline/cli/main.py` and `README.md` are not in `machine.FENCED`, so this
  diff does not park at `awaiting-merge` for that reason.

## Decisions checked

DEC-039 is the only record touching this behaviour, and it constrains nothing
here. It states that `tail_log()` tells a PTY dump from stream-json by the
bytes, and cites `spawn()` running an interactive stage headless when nothing
can attach (`pipeline/daemon/supervisor.py:348`) as the reason not to read
`mode:`. That is the same fact the new help text states, so this plan agrees
with it. DEC-025 constrains `claude-code.toml` flags only and is untouched here.
Neither record carries a `superseded-by:` line.

grep terms used over `.project/decisions/`: `interactive`, `help`, `--help`,
`README`, `attachable`, `acceptEdits`, `bypassPermissions`, `PTY`,
`permission`, `docs`, `documentation`. Nothing else is relevant.

## Plan

1. Run `uv run --group dev pytest -q tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference` and confirm it fails with `assert 'interactive' in '...'`; this test lives in `tests/test_cli.py` at lines 39-48 and must not be edited.
2. Add this drift test to `tests/test_cli.py`, immediately after `test_start_and_run_help_explain_the_interactive_stage_difference` (after line 48):

       def test_the_help_text_matches_the_code_it_describes():
           """A help string asserting a behaviour is a promise, and an untested one
           drifts. `start --help` says an interactive stage waits at `pipeline tui`;
           `run --help` says it runs headless. Both rest on `Server.attachable` being
           true and the bare `Poller`'s being false, and on which stages declare
           `mode: interactive`. Flip either, or add a second interactive stage, and
           this fails until the help text and the README say the new truth."""
           from pipeline.core import config as C
           from pipeline.daemon.server import Poller, Server

           assert Server.attachable is True and Poller.attachable is False

           interactive = [s for s in C.agent_stages()
                          if C.stage_config(s).get("mode") == "interactive"]
           assert interactive, "no stage declares `mode: interactive`"

           def help_of(cmd):
               r = subprocess.run([sys.executable, "-m", "pipeline", cmd, "--help"],
                                  cwd=ROOT, capture_output=True, text=True)
               assert r.returncode == 0, r.stderr
               return " ".join(r.stdout.split()).lower()   # argparse wraps at $COLUMNS

           start, run = help_of("start"), help_of("run")
           for stage in interactive:
               assert stage in start and stage in run, f"{stage} is unnamed: {start} {run}"
           assert "pipeline tui" in start and "headless" in start, start
           assert "headless" in run and "pipeline tui" in run, run

           readme = (Path(ROOT) / "README.md").read_text().splitlines()
           run_line = [ln for ln in readme if "myproject run  " in ln]
           start_line = [ln for ln in readme if ln.startswith("pipeline start ")]
           assert run_line and "headless" in run_line[0], run_line
           assert start_line and "tui" in start_line[0], start_line

3. Run `uv run --group dev pytest -q tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` and confirm it fails on `assert "pipeline tui" in start and "headless" in start`; the file it fails in is `tests/test_cli.py`.
4. In `pipeline/cli/main.py`, add these two constants directly above `def main() -> None:` (line 454), separated from it by two blank lines:

       # `add_parser(help=...)` reaches the top-level `pipeline --help` listing only:
       # argparse pops it for the parent and never sets `description`, so `pipeline
       # start --help` printed usage and options alone. `description=` is what a
       # subcommand's own --help prints. Both strings are bound by
       # tests/test_cli.py::test_the_help_text_matches_the_code_it_describes.
       START_DESC = (
           "Start the one daemon for every registered project. A stage whose "
           "frontmatter says `mode: interactive` -- `planning` -- runs on a PTY the "
           "daemon owns and blocks on its first permission prompt until a human "
           "attaches with `pipeline tui`. `pipeline run` executes that same stage "
           "headless instead."
       )
       RUN_DESC = (
           "Run one project's dispatcher loop, with no daemon and no socket. Nothing "
           "can attach, so a stage whose frontmatter says `mode: interactive` -- "
           "`planning` -- runs headless here and never waits for a human; its escape "
           "hatch is `result: needs-input`, which parks the ticket for `pipeline "
           "answer`. Under `pipeline start` that same stage waits at `pipeline tui`."
       )

5. In `pipeline/cli/main.py` line 475, replace `sub.add_parser("start", help="start the one daemon")` with `sub.add_parser("start", help="start the one daemon (interactive stages wait at `pipeline tui`)", description=START_DESC)`, and leave the rest of that line unchanged.
6. In `pipeline/cli/main.py` line 477, replace `sub.add_parser("run", help="one project, no daemon, no socket")` with `sub.add_parser("run", help="one project, no daemon, no socket (interactive stages run headless)", description=RUN_DESC)`, and leave the rest of that line unchanged.
7. Run `uv run --group dev pytest -q tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference tests/test_cli.py::test_the_help_text_matches_the_code_it_describes`; the first passes and the second still fails in `tests/test_cli.py` on `assert run_line and "headless" in run_line[0]`, its README assertion.
8. In `README.md` line 65, replace `pipeline --project ~/code/myproject run       # dispatcher loop, no daemon` with `pipeline --project ~/code/myproject run       # dispatcher loop, no daemon; interactive stages run headless`.
9. In `README.md` line 119, replace `pipeline start                       # spawns pipelined, detached` with ``pipeline start                       # spawns pipelined, detached; interactive stages wait for `pipeline tui` ``, keeping the backticks around `pipeline tui` inside the comment.
10. In `README.md`, append one sentence to the `## Interactive stages` paragraph that ends `which parks the ticket at a human gate for `pipeline answer`.` (line 190): ``pipeline start --help` and `pipeline run --help` each say which side they are on, and `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` fails if either stops saying it.``
11. Run `uv run --group dev pytest -q tests/test_cli.py tests/test_stages.py` and confirm every test passes, including the two tests in `tests/test_cli.py` named in steps 1 and 2.
12. Commit `pipeline/cli/main.py`, `README.md` and `tests/test_cli.py` with the message `docs: pipeline start/run --help say what each does with an interactive stage`.

## Acceptance criteria

1. `pipeline start --help` and `pipeline run --help` each print "interactive" -- `tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference` passes.
2. `start --help` names `pipeline tui`, `run --help` names headless, and both name every stage declaring `mode: interactive` -- `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` passes.
3. The drift test fails if `Poller.attachable` becomes true, if `Server.attachable` becomes false, or if a second stage declares `mode: interactive` without being named in both help strings -- the assertions in `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes`.
4. `README.md` line 65 says interactive stages run headless under `run`, and line 119 says they wait for `pipeline tui` under `start` -- the two README assertions in `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes`.
5. `uv run --group dev pytest -q tests/test_cli.py tests/test_stages.py` exits 0.

## Decisions

**A help string that asserts a behaviour is bound by a test, exactly as the
fenced list is.** `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes`
holds the `start`/`run` help text, `README.md` and the code to one story. It
reads the interactive stage set from `stage_config()` instead of hardcoding
`planning`, so adding a second interactive stage fails the test until both help
strings name it. It asserts `Server.attachable is True` and
`Poller.attachable is False`, the mechanism the whole claim rests on: `start`
builds a `Server` and can attach, `run` builds a bare `Poller` and cannot.
Delete that test and the strings become an unverified promise, which is what
this ticket was filed about.

**`help=` in `add_parser` does not reach `<cmd> --help`.** argparse pops it for
the parent parser's subcommand listing and never sets `description`. That is why
the `start` and `run` subparsers carry both `help=` (short, for `pipeline
--help`) and `description=` (`START_DESC` / `RUN_DESC`, for their own `--help`).
Do not fold the description back into `help=`: the reproduction test goes red
and nothing at `<cmd> --help` explains the difference again.

## Rollback

Revert the one commit touching `pipeline/cli/main.py`, `README.md` and
`tests/test_cli.py`. No runtime behaviour changes: `START_DESC` and `RUN_DESC`
are read by argparse only, and no code path branches on them. After the revert
`tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference`
is red again, which is the state triage recorded at c651348.

## Thread

### 2026-08-24 08:05:50Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

### 2026-08-24 · triage · result=ok

Reproduced. `pipeline start --help` and `pipeline run --help` stdout contain
no occurrence of "interactive" (case-insensitive), verified directly on
main at 80965a8 and via a committed test.

Added `tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference`,
committed at c651348. It asserts `"interactive" in stdout.lower()` for both
`pipeline start --help` and `pipeline run --help`. It fails now with:

    AssertionError: usage: __main__.py start [-h] [--interval INTERVAL] [--harness HARNESS]
                                 [-j MAX_PARALLEL]
    ...
    assert 'interactive' in '...'

Not filing as `chore`: the fix is two `help=` string edits in
`pipeline/cli/main.py` (`start` and `run` subparsers) plus a `README.md`
update, but the ticket also asks for a design decision on how the wording
stays true over time (a help string as a tested promise, like
`test_the_fenced_list_matches_the_rule_file`). That choice belongs to
planning, not triage.

Files I expect the fix to touch: `pipeline/cli/main.py`, `README.md`.

dispatcher pickup

### 2026-08-24 08:46:33Z · triage · session · session=f4e22bdd-3cfb-4103-9f3a-5f055ab4c542

`triage` ran as session `f4e22bdd-3cfb-4103-9f3a-5f055ab4c542`
- replay: `claude --resume f4e22bdd-3cfb-4103-9f3a-5f055ab4c542`
- log: `.project/logs/TICKET-049-triage-f4e22bdd.log`

### 2026-08-24 08:46:33Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- start/run --help mention no "interactive"; committed failing test at c651348

### 2026-08-24 · planning · result=ok

Plan written. Scope is one subsystem: the CLI parser's help text and the
README.

One correction to the ticket's stated fix. Editing only the `help=` strings
leaves the reproduction test red. argparse's `add_parser` pops `help` into the
parent parser's subcommand listing and never sets `description`, so `pipeline
start --help` prints usage and options alone. Verified:

    $ uv run python -m pipeline start --help
    usage: __main__.py start [-h] [--interval INTERVAL] [--harness HARNESS]
                             [-j MAX_PARALLEL]

    options:
      -h, --help            show this help message and exit

The plan passes `description=` to both subparsers as well as `help=`.

The wording stays true through one added test,
`tests/test_cli.py::test_the_help_text_matches_the_code_it_describes`. It reads
the interactive stage set from `stage_config()` (today `['planning']`), asserts
`Server.attachable is True` and `Poller.attachable is False`, and asserts the
two README lines. Triage's test at c651348 is untouched.

`.claude/skills/file-ticket/SKILL.md` lines 137-140 already state this
difference correctly, so the plan changes no skill file.

Noted, out of scope: `pipeline/cli/main.py` gives no `help=` to `init`, `new`,
`gate`, `approve`, `reject`, `answer`, `resume` or `logs`, so `pipeline --help`
lists them bare.

### 2026-08-24 09:00:12Z · planning · session · session=84cd980a-495f-4587-b6d3-610cce9d603a

`planning` ran as session `84cd980a-495f-4587-b6d3-610cce9d603a`
- replay: `claude --resume 84cd980a-495f-4587-b6d3-610cce9d603a`
- log: `.project/logs/TICKET-049-planning-84cd980a.log`

### 2026-08-24 09:00:12Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written -- start/run get description= plus help=, bound by a new drift test in tests/test_cli.py

### 2026-08-24 09:17:03Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference` fails as required
```
    where <built-in method lower of str object at 0x7ff2bac20c10> = 'usage: __main__.py start [-h] [--interval INTERVAL] [--harness HARNESS]\n                         [-j MAX_PARALLEL]\n...      show this help message and exit\n  --interval INTERVAL\n  --harness HARNESS\n  -j, --max-parallel MAX_PARALLEL\n'.lower
E        +      where 'usage: __main__.py start [-h] [--interval INTERVAL] [--harness HARNESS]\n                         [-j MAX_PARALLEL]\n...      show this help message and exit\n  --interval INTERVAL\n  --harness HARNESS\n  -j, --max-parallel MAX_PARALLEL\n' = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-049/.venv/bin/python', '-m', 'pipeline', ...his help message and exit\n  --interval INTERVAL\n  --harness HARNESS\n  -j, --max-parallel MAX_PARALLEL\n', stderr='').stdout

tests/test_cli.py:47: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.19s ===============================

```
- ok: `tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference` fails on base `main` too -- the bug is not already fixed upstream
```
-j, --max-parallel MAX_PARALLEL\n' = CompletedProcess(args=['/tmp/pipeline-base-6rt9y5z1/base/.venv/bin/python', '-m', 'pipeline', 'start', '--help'], retu...his help message and exit\n  --interval INTERVAL\n  --harness HARNESS\n  -j, --max-parallel MAX_PARALLEL\n', stderr='').stdout

tests/test_cli.py:47: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-6rt9y5z1/base
      Built pipeline @ file:///tmp/pipeline-base-6rt9y5z1/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-24 · plan-validation · result=ok

Plan passed. Eight items, each scored.

1. **Root cause.** The `start` and `run` subparsers pass only `help=`, which
   argparse routes to the parent's subcommand listing; neither sets
   `description`, so `<cmd> --help` prints usage and options alone. The plan
   adds `description=` (steps 5-6), which is the cause, not the symptom.
2. **Decision conflict.** DEC-039 states `tail_log()` reads bytes, not `mode:`,
   and cites the same `spawn()` gate the help text describes; it constrains no
   step here. DEC-025 covers `claude-code.toml` flags, untouched. Neither
   carries `superseded-by:`.
3. **Scope.** Steps 1-3 -> criteria 1-3, steps 4-7 -> criteria 1-2, steps 8-10
   -> criterion 4, step 11 -> criterion 5. Step 12 commits. Nothing is
   untraceable.
4. **Falsifiable.** Remove `description=` and step 3's assertion goes red. Flip
   either `attachable` and the drift test fails on its first assertion.
5. **No research left.** Every step names a file and a line, and quotes the
   replacement string.
6. **Riskiest step.** Step 2's README assertions are literal string matches.
   Both patterns are unique today: `^pipeline start ` matches line 119 only,
   `myproject run  ` matches line 65 only. Steps 8-9 keep both prefixes.
   Fallback: `## Rollback` reverts the one commit.
7. **Regression surface.** No test asserts the current `help=` strings; the
   only `--help` assertions in `tests/` are triage's test at lines 43-48. No
   code path branches on a description.
8. **Blast radius.** `class: feature`, three files, all in `files_declared`.

Re-verified in code: `pipeline/daemon/server.py:138` `attachable = False`,
line 213 `attachable = True`, `pipeline/daemon/supervisor.py:349-350`
`cfg.get("mode") == "interactive" and getattr(poller, "attachable", False)`.

Out of scope, verified: `.claude/skills/file-ticket/SKILL.md:137-140` already
states this difference, so the CLAUDE.md skill rule is satisfied.

### 2026-08-24 09:19:07Z · plan-validation · session · session=34c9a7df-8b2c-4af0-b81f-5c3547914827

`plan-validation` ran as session `34c9a7df-8b2c-4af0-b81f-5c3547914827`
- replay: `claude --resume 34c9a7df-8b2c-4af0-b81f-5c3547914827`
- log: `.project/logs/TICKET-049-plan-validation-34c9a7df.log`

### 2026-08-24 09:19:07Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passed all eight items; verified attachable flags, spawn() gate and the two unique README lines

### 2026-08-24 09:19:45Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-24 09:43:32Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference` fails as required
```
    where <built-in method lower of str object at 0x7f9e520a0c10> = 'usage: __main__.py start [-h] [--interval INTERVAL] [--harness HARNESS]\n                         [-j MAX_PARALLEL]\n...      show this help message and exit\n  --interval INTERVAL\n  --harness HARNESS\n  -j, --max-parallel MAX_PARALLEL\n'.lower
E        +      where 'usage: __main__.py start [-h] [--interval INTERVAL] [--harness HARNESS]\n                         [-j MAX_PARALLEL]\n...      show this help message and exit\n  --interval INTERVAL\n  --harness HARNESS\n  -j, --max-parallel MAX_PARALLEL\n' = CompletedProcess(args=['/home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-049/.venv/bin/python', '-m', 'pipeline', ...his help message and exit\n  --interval INTERVAL\n  --harness HARNESS\n  -j, --max-parallel MAX_PARALLEL\n', stderr='').stdout

tests/test_cli.py:47: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.19s ===============================

```
- ok: `tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference` fails on base `main` too -- the bug is not already fixed upstream
```
-j, --max-parallel MAX_PARALLEL\n' = CompletedProcess(args=['/tmp/pipeline-base-oy3w2iua/base/.venv/bin/python', '-m', 'pipeline', 'start', '--help'], retu...his help message and exit\n  --interval INTERVAL\n  --harness HARNESS\n  -j, --max-parallel MAX_PARALLEL\n', stderr='').stdout

tests/test_cli.py:47: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-oy3w2iua/base
      Built pipeline @ file:///tmp/pipeline-base-oy3w2iua/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### implementing · todo

1. Confirm triage's test fails RED -- done, `AssertionError` at `tests/test_cli.py:47`.
2. Add `test_the_help_text_matches_the_code_it_describes` -- done.
3. Confirm it fails RED -- done.
4. Add `START_DESC` / `RUN_DESC` in `pipeline/cli/main.py` -- done.
5. Wire `description=` into the `start` subparser -- done.
6. Wire `description=` into the `run` subparser -- done.
7. Re-run both new tests -- done, first passes, second still red on the README check.
8. Edit `README.md` line 65 -- done.
9. Edit `README.md` line 119 -- done.
10. Append the drift-test sentence to the `## Interactive stages` paragraph -- done.
11. Run `tests/test_cli.py tests/test_stages.py` -- done, 28 passed.
12. Commit -- done, `b0ab370`.

### implementing · result=ok

Plan executed as written, no deviation. `uv run --group dev pytest -q
tests/test_cli.py::test_start_and_run_help_explain_the_interactive_stage_difference`
failed first on `assert "interactive" in r_start.stdout.lower()` (RED,
confirmed against the unmodified tree). Added the drift test; it failed next
on `assert stage in start and stage in run` (`planning is unnamed`), since
neither subparser had a `description=` yet. After steps 4-6 it failed once
more on the README check (`assert run_line and "headless" in run_line[0]`),
exactly where the plan predicted. After the `README.md` edits, `uv run
--group dev pytest -q tests/test_cli.py tests/test_stages.py` -> `28 passed`,
clean output. Committed `pipeline/cli/main.py`, `README.md`,
`tests/test_cli.py` as `b0ab370`
(`docs: pipeline start/run --help say what each does with an interactive
stage`). No file outside `files_declared` touched. Triage's test at line
39-48 is unedited.

### 2026-08-24 09:43:32Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-24 09:45:15Z · implementing · session · session=3abcec1c-78e2-436b-a4be-60bdff22631b

`implementing` ran as session `3abcec1c-78e2-436b-a4be-60bdff22631b`
- replay: `claude --resume 3abcec1c-78e2-436b-a4be-60bdff22631b`
- log: `.project/logs/TICKET-049-implementing-3abcec1c.log`

### 2026-08-24 09:45:15Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ added description= to start/run subparsers, updated README, added drift test; 28 passed, committed b0ab370

### review · result=ok

Reviewed the branch diff `main...HEAD` (`4037104`, `b0ab370`): three files,
`pipeline/cli/main.py`, `README.md`, `tests/test_cli.py`. No blocking findings.

Verified:

1. `uv run --group dev pytest -q tests/test_cli.py tests/test_stages.py` ->
   `28 passed in 2.68s`, clean.
2. The drift test is not vacuous. With `Poller.attachable` set true it fails at
   `assert Server.attachable is True and Poller.attachable is False`. With a
   second stage stubbed to `mode: interactive` it fails at
   `AssertionError: triage is unnamed: ...`. Both ran in memory; no file changed.
3. `start --help` prints `pipeline tui`, `headless` and `planning`; `run --help`
   prints the same three. Criteria 1, 2 and 3 hold.
4. `README.md:65` and `README.md:119` each match their test pattern exactly
   once, so the `[0]` index reads the intended line.
5. Triage's test is unedited: `git diff 4037104 b0ab370 -- tests/test_cli.py` is
   one added block after line 48.
6. `pipeline --help` still lists both subcommands, wrapped, exit 0.
7. `machine.FENCED` names neither `pipeline/cli/main.py` nor `README.md`.
   `.claude/skills/file-ticket/SKILL.md:137-140` already states this difference.
8. `git status --porcelain` is empty; I changed no file but this ticket.

Non-blocking nits:

1. (nit) `run_line` matches `"myproject run  "` on two literal spaces. Realign
   the README comment column and the test fails on formatting, not on drift.
2. (nit) `run --help` passes `"pipeline tui" in run` only through RUN_DESC's
   last sentence. Trim that sentence and the test fails though `run`'s own
   claim stands.

### 2026-08-24 09:48:06Z · review · session · session=a5ba0be5-f4f6-4a83-8096-aa4ed3c65497

`review` ran as session `a5ba0be5-f4f6-4a83-8096-aa4ed3c65497`
- replay: `claude --resume a5ba0be5-f4f6-4a83-8096-aa4ed3c65497`
- log: `.project/logs/TICKET-049-review-a5ba0be5.log`

### 2026-08-24 09:48:06Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed b0ab370: 28 passed, drift test proven non-vacuous on both flips; no blocking findings, two nits

### 2026-08-24 09:48:18Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-24 09:48:19Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/049


Already up to date.
Updating b06ed44..b0ab370
Fast-forward
 README.md            |  8 +++++---
 pipeline/cli/main.py | 25 +++++++++++++++++++++++--
 tests/test_cli.py    | 47 +++++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 75 insertions(+), 5 deletions(-)

```

### 2026-08-24 09:48:19Z · merging · decision

decision recorded as `DEC-049`
