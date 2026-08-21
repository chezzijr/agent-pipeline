---
id: TICKET-020
stage: done
class: bugfix
branch: ticket/020
test_file: tests/test_daemon.py::test_the_daemon_log_is_readable_while_the_daemon_runs
files_declared:
- pipeline/cli/main.py
- pipeline/core/__init__.py
- pipeline/daemon/main.py
- tests/test_daemon.py
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
  id: 2239021a-bb17-4fa2-a694-bc1f7796f35c
  log: .project/logs/TICKET-020-review-2239021a.log
approved_by: chezzijr
approved_at: '2026-08-21T05:18:28.749979+00:00'
---

## Summary

**Reviewed, no blocking findings (2026-08-21).** First review pass over the
whole branch delta (3 commits, 4 files = exactly `files_declared`). All four
acceptance criteria re-verified here: `tests/test_daemon.py tests/test_cli.py
tests/test_dispatch.py` -> 56 passed. The fix reaches the real path, not only
the test's -- `cmd_start` spawns the same `-m pipeline.daemon.main` the daemon
test spawns, and both entry modules have a `__main__` guard. No test calls
either `main()` in-process, so the `reconfigure`-under-capture regression cannot
fire. No drift from the Plan (step 5's `python -m pipeline` is the Summary's own
correction). No invariant touched. Three nits in Thread, none blocking:
uncleaned `mkdtemp()` (house style), `reconfigure` on a `None`/`StringIO` stdout
would raise, and the two new tests are wall-clock polls on real children.

**Implemented and committed (2026-08-21).** `line_buffer_stdout()` added to
`pipeline/core/__init__.py` and called first in both `pipeline/daemon/main.py`
and `pipeline/cli/main.py`'s `main()`. Both tests pass:
`test_the_daemon_log_is_readable_while_the_daemon_runs` and the new
`test_pipeline_run_log_is_readable_while_it_runs` (verified non-vacuous --
failed pre-fix with the exact string the plan predicted). No regressions:
`tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py` -- 56 passed.
Two commits: `0b66bf7` (daemon half), `ead082f` (run half). See Thread for
full detail.

`pipelined` and `pipeline run` both block-buffer stdout, so their redirected log
is empty for the whole run and lands in one burst at exit. Python line-buffers
stdout only when it is a tty; `pipeline start` redirects it to
`~/.local/state/pipeline/daemon.log` and `pipeline run > run.log` redirects it to
a file, and the dispatcher prints a few hundred bytes an hour -- nowhere near the
8 KiB that triggers a flush.

Fix: a `line_buffer_stdout()` helper in `pipeline/core/__init__.py` calling
`sys.stdout.reconfigure(line_buffering=True)`, called as the first statement of
both entry points' `main()` -- `pipeline/daemon/main.py` and
`pipeline/cli/main.py`. Inside the process, not `-u` on the spawner, because
`pipeline run` has no spawner to pass a flag to. stderr needs nothing: it has
been unconditionally line-buffered since Python 3.9, and `pipeline start` merges
it into the same fd with `stderr=subprocess.STDOUT`.

Two tests, both in `tests/test_daemon.py`: the committed
`test_the_daemon_log_is_readable_while_the_daemon_runs` (daemon half, currently
failing) and a new `test_pipeline_run_log_is_readable_while_it_runs` (the `run`
half, which a `cmd_start`-only fix would leave broken).

**Plan validated (2026-08-21).** All eight items pass; the plan is ready to
implement as written. Every file, line and API it cites was checked against the
tree. Three corrections for whoever implements it, none of which change the fix:

1. The `PipelineError` import in `pipeline/cli/main.py` is at **line 14**, not
   the line 15 the plan cites.
2. **Use `python -m pipeline` in step 5's new test**, not the plan's
   `python -c "from pipeline.cli.main import main; main()"`. The Digest is right
   that `cli/main.py` has no `__main__` guard, but wrong that this leaves no way
   to spawn it: `pipeline/__main__.py` already exists and `tests/test_cli.py`
   uses `[sys.executable, "-m", "pipeline", ...]` throughout. Same `main()`, same
   argv, matches the suite. Drop the planning thread's "add the guard" note --
   nothing needs it.
3. Step 9's command is right, its reason is not: `tests/test_cli.py` does not
   import `pipeline.cli.main`, it spawns the CLI as a subprocess -- which
   exercises the edited `main()` for real and is a *better* check than an import.
   `tests/test_dispatch.py` imports `cmd_approve` only. Run it as written.

Regression surface is small and was checked: no test calls either `main()`
in-process, so `sys.stdout.reconfigure` never runs against pytest's capture
object. DEC-011 is the only decision on disk and does not constrain this
(schema/kinds/protocol only; none are touched). Keep step 5's hand-rolled
throwaway project rather than `helpers.project()` -- the helper writes a *valid*
ticket, which `tick()` would try to spawn an agent for.

## Reproduction

`tests/test_daemon.py::test_the_daemon_log_is_readable_while_the_daemon_runs`

Spawns a real `pipelined` child with stdout redirected to a file -- the only
place the buffering exists, a tty would not show it -- waits for the socket to
appear so the banner is provably already printed, then reads the file.

Command:

    uv run --group dev pytest -q tests/test_daemon.py::test_the_daemon_log_is_readable_while_the_daemon_runs

Output:

    >           assert b"pipelined" in log.read_bytes(), \
                    "the daemon printed its banner but the log is empty"
    E               AssertionError: the daemon printed its banner but the log is empty
    E               assert b'pipelined' in b''
    E                +  where b'' = read_bytes()
    E                +    where read_bytes = PosixPath('/tmp/tmph0zvkhfj/daemon.log').read_bytes

    tests/test_daemon.py:727: AssertionError
    1 failed in 0.66s

expect: AssertionError: the daemon printed its banner but the log is empty

Not a setup error: the daemon started (the socket assert above it passed, so the
child was up and had already printed), and the same bytes are in the file once
the process is killed -- the line was written, just not where anyone could read
it during the run.

## Digest

**The two entry points, and why both matter**

| entry point | file | how stdout is redirected |
|---|---|---|
| `pipelined` | `pipeline/daemon/main.py` `main()` | `cmd_start` passes `stdout=log` (`pipeline/cli/main.py:256-263`) |
| `pipeline run` | `pipeline/cli/main.py` `main()` -> `run(...)` at line 458-460 | the user's own `> run.log` |

Both are console scripts declared in `pyproject.toml:12-14`
(`pipeline = "pipeline.cli.main:main"`, `pipelined = "pipeline.daemon.main:main"`).
They share `supervisor.tick()` but **not** a spawner, which is why the fix cannot
live in `cmd_start`.

`pipeline/cli/main.py` has **no** `if __name__ == "__main__"` guard, so
`python -m pipeline.cli.main` imports and exits without running anything. To
spawn it as a child in a test, use
`[sys.executable, "-c", "from pipeline.cli.main import main; main()", "--project", P, "run", "--interval", "60"]`
-- `python -c CMD a b c` leaves `sys.argv == ["-c", "a", "b", "c"]`, so argparse
parses the trailing args exactly as it would from the console script. Verified.

**Where the prints are.** All of them are plain `print()` to stdout in
`pipeline/daemon/supervisor.py`: the banner at line 897
(`print(f"pipelined {__version__}: pid ...")`, printed *before* `server.bind`, so
the socket appearing proves it was already printed), stage starts at 347/370,
verdicts at 70/103, the SIGTERM notice at 832. Nothing uses `logging`; there is
no logger to reconfigure. `supervisor.run()` (line 838) prints **no** banner --
the cheapest line it prints every tick is `print(f"  skipping {path.name}: {e}")`
at line 796, reached when `Ticket.load()` raises on a malformed ticket file.

**Measured, not assumed** (2026-08-21, this worktree):

    without the fix, `pipeline run` on a project with one malformed ticket:
      while alive: b''
      after exit:  b'  skipping BAD.md: ... no frontmatter\n\n  signal 15: stopping\n'

    with `sys.stdout.reconfigure(line_buffering=True)` before `main()`:
      while alive: b'  skipping BAD.md: ... no frontmatter\n'

So the `run` half reproduces with exactly the shape the ticket reports, and
line buffering fixes it. Same probe on a trivial child confirmed the daemon half.

**Gotchas for the implementer**

- `sys.stdout.reconfigure` exists on `TextIOWrapper` but typeshed types
  `sys.stdout` as `TextIO`, so pyright (configured in `pyproject.toml:26`) emits
  `reportAttributeAccessIssue`. Add `# type: ignore[attr-defined]` on that line.
  The repo has no other `type: ignore`; this is the first.
- Do **not** reassign `sys.stdout` to a new `TextIOWrapper` -- `pipeline/pty/host.py`
  and the interactive stage machinery hold fds, and swapping the object is a
  bigger blast radius than reconfiguring the one that is already there.
- Do **not** add `-u` to `cmd_start`'s `Popen`: it fixes only the daemon, makes
  writes unbuffered rather than line-buffered, and the committed test spawns
  `pipeline.daemon.main` directly, so a `cmd_start`-only change does not even
  make it pass.
- A test child needs the dev interpreter: `pipeline/pty/host.py` imports `pyte`
  eagerly at module import (`cli/main.py` -> `daemon/server.py` -> `pty/host.py`),
  so a bare `python3` outside the uv venv dies with `ModuleNotFoundError: pyte`
  before argparse runs. Under pytest `sys.executable` is already the right one --
  the existing test relies on this.
- `tests/test_daemon.py` sets `XDG_CONFIG_HOME`, `XDG_STATE_HOME` and
  `XDG_RUNTIME_DIR` to a temp dir at module import (lines 22-24) *before* any
  pipeline import, and each subprocess test re-sets them in the child's `env`
  plus `PYTHONPATH=str(ROOT)`. A `run` child needs the same: it constructs
  `Store()` with no path, which resolves under `XDG_STATE_HOME`.
- `pipeline run` takes an exclusive `flock` on `<project>/.project/.lock` for its
  whole life (`registry.lock`), so the test must `terminate()` it in a `finally`.
- `pipeline/core/__init__.py` currently has zero imports. Adding `import sys` is
  the first one.

## Decisions checked

- **DEC-011** (the daemon's cross-agent contract) -- read in full, **not
  constraining**. It freezes the SQLite schema, the event-kind vocabulary and
  the socket protocol; this change touches none of them. Its "two stores"
  section is about `events.db` versus the ticket files, not about the human-
  facing stdout log, and nothing in it depends on when bytes reach `daemon.log`.
  Not superseded (no `superseded-by:` line).

`grep -rn "stdout|buffer|daemon.log|flush|tty" .project/decisions/` returns
nothing -- DEC-011 is the only record on disk and it never mentions buffering.
No decision explains the absence of a flush, so there is no deliberate
workaround being removed here.

## Plan

1. Add the helper to `pipeline/core/__init__.py`: `import sys` at the top (the file currently has none), then a module-level `def line_buffer_stdout() -> None:` whose body is `sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]`, with a docstring stating why it exists -- Python block-buffers stdout when it is not a tty, `pipeline start` redirects it into `daemon.log` and `pipeline run` is redirected by the user, the dispatcher prints far less than 8 KiB an hour, and stderr needs nothing because it has been line-buffered unconditionally since Python 3.9. Exact content:

    ```python
    """Core library. Nothing here calls `sys.exit`: a library that kills the
    process takes the whole dispatcher down with one bad project."""
    import sys


    class PipelineError(Exception):
        """Anything the library refuses to do. The CLI turns it into `die()`."""


    def line_buffer_stdout() -> None:
        """Every entry point whose stdout can be redirected calls this first.

        Python block-buffers stdout when it is not a tty. The dispatcher prints
        a few hundred bytes an hour, so `pipeline start`'s redirect into
        daemon.log -- and any `pipeline run > run.log` -- holds every line until
        8 KiB accumulate or the process exits, and watching that file is how a
        human or a `tail -f` finds out what the pipeline is doing. It goes
        inside the process rather than as `-u` on the spawner because
        `pipeline run` has no spawner to pass a flag to. stderr needs nothing:
        line-buffered unconditionally since 3.9.
        """
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    ```

2. Wire the daemon entry point in `pipeline/daemon/main.py`: change `from pipeline.core import PipelineError` to `from pipeline.core import PipelineError, line_buffer_stdout`, and make `line_buffer_stdout()` the first statement inside `def main() -> None:`, before `ap = argparse.ArgumentParser(...)`.

3. Run the committed daemon test against the change -- `uv run --group dev pytest -q tests/test_daemon.py::test_the_daemon_log_is_readable_while_the_daemon_runs` -- and expect it to go from the recorded `AssertionError: the daemon printed its banner but the log is empty` to `1 passed`. This proves step 2 fixed the `pipeline/daemon/main.py` half.

4. Commit the daemon half: `git add pipeline/core/__init__.py pipeline/daemon/main.py && git commit -m "fix: line-buffer the daemon's stdout so its redirected log is readable live"`.

5. Write the failing test for the `run` half at the end of `tests/test_daemon.py`, directly after `test_the_daemon_log_is_readable_while_the_daemon_runs` (currently the last function, file ends at line 735). It spawns `pipeline run` as a real child with stdout redirected to a file, on a throwaway project holding one malformed ticket so `supervisor.tick()` prints `  skipping BAD.md: ...` on its first pass, then polls the file for up to 5s. Exact content:

    ```python
    def test_pipeline_run_log_is_readable_while_it_runs():
        """The daemon is not the only entry point with a redirectable stdout:
        `pipeline run > run.log` block-buffers identically, so a fix confined to
        `pipeline start`'s redirect would leave `run` blank. A malformed ticket
        is the cheapest line the loop prints on its very first tick."""
        tmp = Path(tempfile.mkdtemp())
        proj = tmp / "proj"
        (proj / ".project" / "tickets").mkdir(parents=True)
        (proj / ".project" / "pipeline.toml").write_text('test_one = "true"\n')
        (proj / ".project" / "tickets" / "BAD.md").write_text("no frontmatter\n")
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        for var in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
            env[var] = str(tmp)
        log = tmp / "run.log"
        fh = log.open("wb")
        proc = subprocess.Popen(
            [sys.executable, "-c", "from pipeline.cli.main import main; main()",
             "--project", str(proj), "run", "--interval", "60"],
            stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env=env, cwd=ROOT)
        try:
            for _ in range(100):        # 5s, and it lands in well under one
                if b"skipping BAD.md" in log.read_bytes():
                    break
                time.sleep(0.05)
            assert b"skipping BAD.md" in log.read_bytes(), \
                "`pipeline run` printed a line but its redirected log is empty"
        finally:
            proc.terminate()            # it holds a flock on the project
            proc.wait(10)
            fh.close()
    ```

6. Run the new test in `tests/test_daemon.py` before touching `pipeline/cli/main.py` -- `uv run --group dev pytest -q tests/test_daemon.py::test_pipeline_run_log_is_readable_while_it_runs` -- and expect `AssertionError: `pipeline run` printed a line but its redirected log is empty` with `assert b'skipping BAD.md' in b''`. If it passes here the test is vacuous and the rest of the plan is worthless; stop and report that instead.

7. Wire the CLI entry point in `pipeline/cli/main.py`: change `from pipeline.core import PipelineError` (line 15) to `from pipeline.core import PipelineError, line_buffer_stdout`, and make `line_buffer_stdout()` the first statement inside `def main() -> None:` (line 423), before `ap = argparse.ArgumentParser(...)`. It runs for every subcommand, not only `run`, because reconfiguring a tty that is already line-buffered is a no-op and one call site cannot drift from the other.

8. Re-run the new test in `tests/test_daemon.py` -- `uv run --group dev pytest -q tests/test_daemon.py::test_pipeline_run_log_is_readable_while_it_runs` -- and expect `1 passed`.

9. Run the modules this touches -- `uv run --group dev pytest -q tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py` -- and expect no failures; `tests/test_cli.py` and `tests/test_dispatch.py` import `pipeline/cli/main.py`, so they are what a bad import line in step 7 would break.

10. Commit the `run` half: `git add pipeline/cli/main.py tests/test_daemon.py && git commit -m "fix: line-buffer pipeline run's stdout too"`.

## Acceptance criteria

- `tests/test_daemon.py::test_the_daemon_log_is_readable_while_the_daemon_runs` passes: `pipelined`'s banner is in the redirected log within 0.5s of the socket appearing, while the process is still alive.
- `tests/test_daemon.py::test_pipeline_run_log_is_readable_while_it_runs` passes: `pipeline run`'s `skipping BAD.md` line is in the redirected log within 5s, while the process is still alive.
- That new test is not vacuous: with step 7's edit to `pipeline/cli/main.py` reverted, `tests/test_daemon.py::test_pipeline_run_log_is_readable_while_it_runs` fails with `assert b'skipping BAD.md' in b''` (this is step 6, run before the fix).
- No regression in the modules that import the two changed entry points: `uv run --group dev pytest -q tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py` reports no failures.

## Decisions

**Stdout line buffering is set inside each entry point, never by the spawner.**

`pipeline/core/__init__.py:line_buffer_stdout()` is called first thing in both
`pipeline/daemon/main.py:main()` and `pipeline/cli/main.py:main()`. The obvious
"simplification" is to delete both calls and add `-u` (or `PYTHONUNBUFFERED=1`)
to the `Popen` in `cmd_start` that spawns `pipelined`. Do not: `pipeline run` is
an in-process loop with no spawner at all, and the user's own `> run.log`
redirect is the thing being fixed there. A spawner-side flag fixes one of the two
entry points and cannot reach the other. The committed test spawns
`pipeline.daemon.main` directly for the same reason -- it is deliberately blind
to anything `cmd_start` does.

Line buffering, not unbuffered. The dispatcher prints whole lines; flushing per
`write()` call buys nothing and costs a syscall per fragment.

stderr is deliberately left alone: CPython has line-buffered it unconditionally
since 3.9, and `cmd_start` merges it into the same fd (`stderr=subprocess.STDOUT`),
so both streams interleave correctly with no second call.

## Rollback

Revert the three production edits -- the `line_buffer_stdout()` definition and
`import sys` in `pipeline/core/__init__.py`, and the import + first-statement
call in `pipeline/daemon/main.py` and `pipeline/cli/main.py`. Nothing else reads
the helper, there is no state, no schema, no on-disk format and no protocol
change; reverting restores the old block-buffered behaviour exactly. The two
tests in `tests/test_daemon.py` then fail again, which is the correct signal, so
revert them only if the whole ticket is being abandoned.

## Thread

### 2026-08-21 04:29:43Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 04:37:45Z · triage · note

`triage` was interrupted; lease released

### 2026-08-21 · triage · reproduced

The interrupted run had already committed the test at `185d1d7`; nothing else was
left behind (`git status` clean, no ticket sections written). Ran that test: it
fails with `AssertionError: the daemon printed its banner but the log is empty`,
which is the reported symptom, not a setup failure -- the socket assert above it
passes, so the child was up and had already printed the banner. After
`terminate()` the same bytes are in the file, which is the "burst on exit" half
of the report.

Out of scope for triage, for whoever plans the fix: `pipeline run` with its
output redirected has the same shape (the ticket's `wc -c run.log` = 0), so a fix
confined to `cmd_start`'s redirect would leave `run` broken.

### 2026-08-21 05:07:03Z · triage · session · session=93a9d103-4899-4767-91dd-b471618c45f2

`triage` ran as session `93a9d103-4899-4767-91dd-b471618c45f2`
- replay: `claude --resume 93a9d103-4899-4767-91dd-b471618c45f2`
- log: `.project/logs/TICKET-020-triage-93a9d103.log`

### 2026-08-21 05:07:03Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

reproduced - daemon.log is empty while pipelined runs; failing test committed at 185d1d7

### 2026-08-21 · planning · plan

Root cause is Python's default stdout buffering, not any pipeline code: stdout is
line-buffered only when it is a tty, and both entry points have theirs redirected
to a file. Verified in this worktree that `sys.stdout.reconfigure(line_buffering=True)`
before `main()` turns an empty-while-alive log into one that has the line the
instant it is printed -- for a trivial child *and* for a real `pipeline run` on a
project with one malformed ticket.

Confirmed the ticket's own warning: `pipeline run` reproduces the same shape
(`while alive: b''`, the burst at exit), and it has no spawner, so a `-u` on
`cmd_start`'s `Popen` cannot reach it. Hence the helper in
`pipeline/core/__init__.py` called from both `main()`s rather than a flag.

Two things found while reading, out of scope, noted rather than fixed:
- `pipeline/cli/main.py` has no `if __name__ == "__main__"` guard, so
  `python -m pipeline.cli.main` silently does nothing. The new test works around
  it with `python -c "from pipeline.cli.main import main; main()"`. Adding the
  guard would be two lines if anyone wants it.
- `sys.stdout.reconfigure` needs a `# type: ignore[attr-defined]` for pyright
  (typeshed types `sys.stdout` as `TextIO`). It is the repo's first `type: ignore`.

### 2026-08-21 05:13:26Z · planning · session · session=c9b4a196-dfa1-4c30-9cb0-0faf7b1c158f

`planning` ran as session `c9b4a196-dfa1-4c30-9cb0-0faf7b1c158f`
- replay: `claude --resume c9b4a196-dfa1-4c30-9cb0-0faf7b1c158f`
- log: `.project/logs/TICKET-020-planning-c9b4a196.log`

### 2026-08-21 05:13:26Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

plan written - line_buffer_stdout() helper in pipeline/core called from both entry points' main(), plus a second test for the pipeline-run half

### 2026-08-21 05:13:34Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_the_daemon_log_is_readable_while_the_daemon_runs` fails as required
```
          stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env=env, cwd=ROOT)
        try:
            for _ in range(100):        # wait on the socket, not on a sleep
                if sock.exists():
                    break
                time.sleep(0.05)
            assert sock.exists(), f"daemon never came up: {log.read_text()}"
            time.sleep(0.5)             # the banner is printed BEFORE the bind
>           assert b"pipelined" in log.read_bytes(), \
                "the daemon printed its banner but the log is empty"
E               AssertionError: the daemon printed its banner but the log is empty
E               assert b'pipelined' in b''
E                +  where b'' = read_bytes()
E                +    where read_bytes = PosixPath('/tmp/tmpg1u04qj3/daemon.log').read_bytes

tests/test_daemon.py:727: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_daemon_log_is_readable_while_the_daemon_runs
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.66s ===============================

```

### 2026-08-21 · plan-validation · validated

Every claim below was checked against the tree, not taken from the plan.

**Root cause.** CPython line-buffers `sys.stdout` only when `isatty()`; otherwise
it is block-buffered at 8 KiB. Both entry points have stdout pointed at a file
(`cmd_start`'s `stdout=log`, and the user's own `> run.log`), and the dispatcher
prints far less than 8 KiB between exits, so every line sits in the process
buffer until it dies. No pipeline code causes it and none can be blamed; the
process never asks for a different buffering mode. The plan fixes exactly that
-- it changes the mode of the stream, it does not add a `flush()` on the one path
the test happens to watch. Passes: root cause, not symptom.

**Decisions.** `.project/decisions/` holds one record, DEC-011, no
`superseded-by:`. Read it: it freezes the `events` schema, the event-kind
vocabulary and the socket protocol; its "two stores" section is `events.db`
versus the ticket files. This change touches no column, no kind, no protocol
frame and no on-disk format. Not constraining, and nothing to supersede. Passes.

**Scope.** Four files, and `files_declared` is exactly those four. Steps 1/2/7
are the fix, 3/6/8/9 are the runs the criteria name, 4/10 are commits, 5 is the
second test the third criterion requires. No step is untraceable. Blast radius
matches `bugfix`. Passes both items.

**Falsifiable.** Criterion 3 is the one that matters and it is real: step 6 runs
the new test with `pipeline/cli/main.py` still unmodified and requires
`assert b'skipping BAD.md' in b''`, with an explicit instruction to stop and
report if it passes there. The criteria pin two named tests and one named
failure string, not "the log should work". Passes.

**No research left.** Verified each concrete reference:
- `pipeline/core/__init__.py` is 7 lines, zero imports -- as stated.
- `pipeline/daemon/main.py:11` is `from pipeline.core import PipelineError`, and
  `main()` at line 17 opens with `ap = argparse.ArgumentParser`. As stated.
- `pipeline/cli/main.py`: the `PipelineError` import is at **line 14**, not 15
  (line 15 is `from pipeline.core.config import ...`). `main()` at 423 opens with
  `ap = ...` as stated. Off-by-one in a citation, the string is unambiguous.
- `pyproject.toml`: `requires-python = ">=3.11"` (so `reconfigure` exists and the
  stderr-since-3.9 claim holds), console scripts at 12-14, `[tool.pyright]`
  present -- so the `# type: ignore[attr-defined]` note is warranted.
- `supervisor.py:796` is `print(f"  skipping {path.name}: {e}")` inside `tick()`,
  reached from `run()` (838) on the first pass. Banner at 897 in `serve()`,
  before `server.bind`. As stated.
- `registry.lock()` takes `LOCK_EX|LOCK_NB` on `<project>/.project/.lock` and
  `run()` holds it in a `try/finally` for its whole life -- the plan's
  `terminate()`-in-`finally` is required, not decorative.
- `tests/test_daemon.py` already imports `os`, `subprocess`, `sys`, `tempfile`,
  `time`, `Path` and `ROOT`; the new test needs no new import. File is 735 lines,
  the committed test is last. As stated.
Passes.

**Riskiest step.** Step 5, the new test: it is the only step that spawns a real
child on a real project and can hang or flake, and it is the one thing the
committed test does not already cover. It has a fallback -- step 6 is a
mandatory pre-fix run with a named expected failure and an explicit
stop-and-report if it passes. The `Rollback` section covers the three production
edits. Passes.

**Regression surface.** The reachable risk is `line_buffer_stdout()` raising
where `sys.stdout` is not a `TextIOWrapper` -- i.e. under pytest's capture.
Checked: no test calls either `main()` in-process. `tests/test_dispatch.py:14`
imports `cmd_approve`, not `main`; `tests/test_cli.py` does not import
`pipeline.cli.main` at all, it spawns `[sys.executable, "-m", "pipeline", ...]`
as a subprocess. So step 9's *reason* is wrong for `test_cli.py` (it subprocesses
rather than imports) but its *coverage claim is stronger than stated*: those runs
actually execute the edited `main()` end to end for many subcommands, which is
precisely what a bad import or a raising `reconfigure` would break. The command
in step 9 is right; keep it. Passes.

**One finding for the implementer, non-blocking.** The Digest asserts that
because `pipeline/cli/main.py` has no `__main__` guard, spawning it as a child
requires `python -c "from pipeline.cli.main import main; main()"`. The premise is
true, the conclusion is not: `pipeline/__main__.py` exists and is exactly
`from pipeline.cli.main import main` under a guard, and `python -m pipeline` is
what `tests/test_cli.py` uses in at least three places. The step-5 test can and
should be `[sys.executable, "-m", "pipeline", "--project", str(proj), "run",
"--interval", "60"]` -- same `main()`, same argv shape, matches the suite. The
`-c` form was measured working, so this is not a correctness defect and does not
block; it is a reuse point for implement/review. The planning thread's related
suggestion to "add the guard, two lines" should be dropped: nothing needs it.

Also noted, not acted on: the plan's hand-rolled throwaway project in step 5
deliberately does *not* use `helpers.project()`, and that is correct --
`helpers.project()` writes a **valid** `TICKET-001.md`, which `tick()` would try
to spawn an agent for. A project holding only a malformed ticket spawns nothing.

Verdict: all eight items pass.

### 2026-08-21 05:16:55Z · plan-validation · session · session=a927a050-23f0-421d-a72d-54640217dbbe

`plan-validation` ran as session `a927a050-23f0-421d-a72d-54640217dbbe`
- replay: `claude --resume a927a050-23f0-421d-a72d-54640217dbbe`
- log: `.project/logs/TICKET-020-plan-validation-a927a050.log`

### 2026-08-21 05:16:55Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

plan validated - all eight items pass; three non-blocking corrections written into Summary (use `python -m pipeline` in the new test, cli import is line 14, step 9's rationale)

### 2026-08-21 05:18:28Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 05:20:32Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_daemon.py::test_the_daemon_log_is_readable_while_the_daemon_runs` fails as required
```
          stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env=env, cwd=ROOT)
        try:
            for _ in range(100):        # wait on the socket, not on a sleep
                if sock.exists():
                    break
                time.sleep(0.05)
            assert sock.exists(), f"daemon never came up: {log.read_text()}"
            time.sleep(0.5)             # the banner is printed BEFORE the bind
>           assert b"pipelined" in log.read_bytes(), \
                "the daemon printed its banner but the log is empty"
E               AssertionError: the daemon printed its banner but the log is empty
E               assert b'pipelined' in b''
E                +  where b'' = read_bytes()
E                +    where read_bytes = PosixPath('/tmp/tmpdy0vp7y9/daemon.log').read_bytes

tests/test_daemon.py:727: AssertionError
=========================== short test summary info ============================
FAILED tests/test_daemon.py::test_the_daemon_log_is_readable_while_the_daemon_runs
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.70s ===============================

```

### 2026-08-21 05:20:32Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 · implementing · todo

1. [x] Add `line_buffer_stdout()` to `pipeline/core/__init__.py`
2. [x] Wire it into `pipeline/daemon/main.py:main()`
3. [x] Run committed daemon test, expect 1 passed
4. [x] Commit daemon half
5. [x] Write `test_pipeline_run_log_is_readable_while_it_runs` in `tests/test_daemon.py`
6. [x] Run new test pre-fix, expect named failure (or stop if it passes)
7. [x] Wire `line_buffer_stdout()` into `pipeline/cli/main.py:main()`
8. [x] Re-run new test, expect 1 passed
9. [x] Run full module set: test_daemon.py test_cli.py test_dispatch.py
10. [x] Commit run half

### 2026-08-21 · implementing · done

All ten steps executed exactly as planned, no deviations. Used `python -m
pipeline` (not `-c`) in the new test per the Summary's step-5 correction.

- Step 3: `test_the_daemon_log_is_readable_while_the_daemon_runs` -> 1 passed.
- Step 4: committed `0b66bf7` (daemon half).
- Step 6: new test pre-fix failed exactly as required --
  `AssertionError: \`pipeline run\` printed a line but its redirected log is
  empty` / `assert b'skipping BAD.md' in b''`. Not vacuous.
- Step 8: new test post-fix -> 1 passed.
- Step 9: `tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py` ->
  56 passed, no regressions.
- Step 10: committed `ead082f` (run half).

Pyright flagged some new-diagnostics after each edit, but every flagged line
(261/267/348/658 in test_daemon.py; 282/284/404/221/236/277 in cli/main.py)
is pre-existing code untouched by this ticket's edits (core/__init__.py:1-19,
daemon/main.py:11+17-18, cli/main.py:14+423-424, tests/test_daemon.py's
appended function) -- not a regression from this change.

All four acceptance criteria met.

### 2026-08-21 05:22:25Z · implementing · session · session=3a4de3af-6f18-430b-92ed-cc80ffcfea47

`implementing` ran as session `3a4de3af-6f18-430b-92ed-cc80ffcfea47`
- replay: `claude --resume 3a4de3af-6f18-430b-92ed-cc80ffcfea47`
- log: `.project/logs/TICKET-020-implementing-3a4de3af.log`

### 2026-08-21 05:22:25Z · implementing · transition · to=review · result=ok

**implementing -> review** (result: `ok`)

implemented line_buffer_stdout() plan as written; both tests pass, no regressions (56 passed), 2 commits (0b66bf7, ead082f)

### 2026-08-21 · review · reviewed

Reviewed the whole branch delta (`git diff main...HEAD`, first review pass):
three commits, four files, exactly the four in `files_declared`. No blocking
findings.

Verified here, not taken from the thread:

- **All four acceptance criteria hold.** `uv run --group dev pytest -q
  tests/test_daemon.py tests/test_cli.py tests/test_dispatch.py` -> `56 passed
  in 4.00s` in this worktree, both named tests included.
- **The fix reaches the real path, not only the test's.** `cmd_start` spawns
  `[sys.executable, "-m", "pipeline.daemon.main", ...]` with `stdout=log`
  (`pipeline/cli/main.py:259-264`) -- the same module the daemon test spawns.
  `pipeline/daemon/main.py` and `pipeline/__main__.py` both carry a `__main__`
  guard, so both `-m` spawns really enter `main()` and hit the new first
  statement.
- **Non-vacuity of the `run` half stands.** `grep -n "flush|reconfigure|
  PYTHONUNBUFFERED"` over `pipeline/` shows the only stdout flush near the
  dispatcher's prints is `cli/main.py:372` (the log-follow path, unrelated);
  with `line_buffer_stdout()` gone there is no other mechanism that could make
  `skipping BAD.md` land mid-run. That matches the pre-fix failure recorded at
  implement time and by the Tier A gate. Not re-run directly: the review stage's
  guard blocks the multi-line `python -c` probe, and reverting the edit is not
  allowed in a read-only stage.
- **The regression the plan worried about cannot fire.** `reconfigure` exists
  only on `TextIOWrapper`, so an in-process `main()` under pytest capture would
  raise. `grep` over `tests/` finds only `cmd_approve` (`test_dispatch.py:14`,
  `test_ticket.py:8`) and `render` (`test_stream.py:124`) imported from
  `pipeline/cli/main.py`; no test calls either `main()` in-process, still true
  after this change.
- **No drift from the Plan.** Steps 1/2/7 match the plan's exact content;
  step 5 used `python -m pipeline` rather than `python -c`, which is the
  correction the Summary ordered, not a deviation. Commits `0b66bf7` and
  `ead082f` are the two the plan names. Working tree clean.
- **No invariant touched.** Nothing in `pipeline/hooks/dangerous-commands.py`,
  `transition()`, `validate_meta()` or `CONTROL_FIELDS`; no schema, no protocol,
  no on-disk format. `pipeline/core/__init__.py` still calls no `sys.exit`.

Non-blocking findings:

1. **(nit)** Both new tests `tempfile.mkdtemp()` with no cleanup. House style --
   `tests/test_daemon.py` has 25 `mkdtemp()` calls against 3 `rmtree`s -- so it
   is consistent, not new debt.
2. **(nit)** `line_buffer_stdout()` raises `AttributeError` if `sys.stdout` is
   `None` (stdout closed, e.g. `pipeline ls >&-`) or a `StringIO`. Pre-fix the
   first `print()` failed on the same input, and no caller does either today.
   Worth `getattr(sys.stdout, "reconfigure", ...)` only if someone ever calls
   `main()` in-process.
3. **(nit, out of scope)** The two new tests are wall-clock polls on real
   children (0.5s / 5s budgets) -- the module's two slowest candidates if CI
   ever runs loaded.

### 2026-08-21 05:25:16Z · review · session · session=2239021a-bb17-4fa2-a694-bc1f7796f35c

`review` ran as session `2239021a-bb17-4fa2-a694-bc1f7796f35c`
- replay: `claude --resume 2239021a-bb17-4fa2-a694-bc1f7796f35c`
- log: `.project/logs/TICKET-020-review-2239021a.log`

### 2026-08-21 05:25:16Z · review · transition · to=verifying · result=ok

**review -> verifying** (result: `ok`)

reviewed branch delta - all four acceptance criteria verified (56 passed), fix reaches cmd_start's real spawn path, no drift, three non-blocking nits in Thread

### 2026-08-21 05:25:23Z · verifying · transition · to=merging · result=ok

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

### 2026-08-21 05:25:24Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/020


Merge made by the 'ort' strategy.
 pipeline/core/gate.py            | 45 +++++++++++++++++++++++++-
 pipeline/core/ticket.py          | 47 +++++++++++++++++++++++----
 pipeline/core/worktree.py        | 37 +++++++++++++++++++++-
 pipeline/templates/pipeline.toml |  1 +
 tests/test_gate.py               | 53 +++++++++++++++++++++++++++++++
 tests/test_ticket.py             | 68 ++++++++++++++++++++++++++++++++++++++++
 6 files changed, 243 insertions(+), 8 deletions(-)
Updating a163a1b..f7377cf
Fast-forward
 pipeline/cli/main.py      |  3 +-
 pipeline/core/__init__.py | 16 +++++++++++
 pipeline/daemon/main.py   |  3 +-
 tests/test_daemon.py      | 70 +++++++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 90 insertions(+), 2 deletions(-)

```

### 2026-08-21 05:25:24Z · merging · decision

decision recorded as `DEC-020`
