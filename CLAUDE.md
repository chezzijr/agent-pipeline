# claude-setup

A ticket-driven agent pipeline. Agents never talk to each other; they talk
through a ticket file. A dumb dispatcher owns the state machine and spawns a
stateless `claude -p` per stage. See `README.md` for how to use it.

**This repo runs its own pipeline** (`.project/tickets/`), so you may be an
agent working a ticket here. If so, your stage prompt governs; this file is
context, not instructions that override it.

## Invariants — break these and the design is pointless

1. **The dispatcher owns control flow.** An agent reports only `result:` in its
   `.result` sidecar. `stage`, `counters`, `branch`, `lease` are restored from a
   pre-spawn snapshot, and a ticket whose control fields changed mid-run is
   escalated. Never add a code path that reads `stage` back from an
   agent-writable file.
2. **`transition()` is pure and total.** No I/O, no mutation of its input, and
   an unknown `(stage, result)` escalates rather than guessing. It is the one
   piece the adversarial review could not land a charge on. Keep it that way.
3. **Every bounded loop escalates at `MAX_ATTEMPTS`.** If you add a retry path,
   it charges a counter. An unbounded respawn is a bug, not a convenience.
4. **Hooks decide with code.** `pipeline/hooks/dangerous-commands.py` is the only layer
   that makes a promise. Read-only stages get an *allowlist*, not a blocklist —
   do not "improve" it back into pattern matching.
5. **Values from ticket files are hostile.** `id`, `branch`, `test_file`,
   `files_declared` all reach a shell. Validate with `validate_meta()` on the
   way in and `shlex.quote` on the way out. Both, not either. `Ticket.save()`
   also validates on the way *out*, but the dispatcher still writes through
   `save_ticket()`, which does not -- so the way-in check is still the one
   holding. Do not weaken it on the strength of the model.
6. **The library never exits the process.** `PipelineError` is raised and the
   CLI turns it into `die()`. One broken project must not take the loop down.

## Where things live

| Path | Holds |
|---|---|
| `pipeline/core/` | `machine` (transition table), `ticket`, `config`, `gate`, `worktree` |
| `pipeline/daemon/supervisor.py` | the dispatcher loop: spawn, reap, apply the verdict |
| `pipeline/cli/main.py` | the `pipeline` command; `pipeline/daemon/main.py` is `pipelined` |
| `pipeline/stages/<name>.md` | one self-contained stage: frontmatter (`model`, `effort`, `write`, `tools`, `hooks`, `skills`, `max_usd`) + the prompt |
| `pipeline/stages/_common.md` | rules every stage shares, including the failure protocol |
| `pipeline/harnesses/*.toml` | how to spawn an agent. Data, not code. A new harness is a new file |
| `pipeline/hooks/` | the guard and its tests |
| `pipeline/templates/` | the ticket schema and the per-project config example |
| `tests/` | one file per module, plain asserts; `tests/helpers.py` builds the throwaway projects |
| `.project/` | this repo's own tickets, decisions, logs |

Adding a stage = one `pipeline/stages/<name>.md` + one row in `transition()`.
Nothing else enumerates the stages; a test enforces that.

The data directories live **inside** the package on purpose: they are found via
`Path(__file__).parent`, so at the repo root they would be gone after
`uv tool install .`.

Stage prompts stay **harness-neutral** — plain instructions and shell/git
commands, no Claude Code skills, subagents, or slash commands. Anything
Claude-specific belongs in `pipeline/harnesses/claude-code.toml`.

## Commands

```sh
uv run --group dev pytest -q                # the dispatcher suite
./pipeline/hooks/test_dangerous_commands.py # 79 guard cases (table-driven, NOT collected by pytest)
```

`pytest` collects only the two `test_*` functions in the guard file — it misses
the allow/block tables entirely. **Run the guard script directly** before
claiming the guard works.

## Gotchas, each found the hard way

- **The dispatcher runs under `uv`'s venv.** Left alone it shadows the target
  project's interpreter, so every project command runs against the wrong Python.
  `project_env()` strips it; use `run_cmd`, never bare `subprocess`.
- **A test that *errors* exits non-zero exactly like one that fails.** The gate
  requires the test's name in the output, or a missing dependency reads as a
  successful reproduction.
- **`git worktree add -B` resets the branch.** Never use `-B`: recreating a
  worktree after a resume would silently discard the ticket's commits.
- **`.project/` is excluded from the read-only tree snapshot**, because writing
  to the ticket is every stage's job. That means `.project/pipeline.toml` is
  reachable by a read-only stage — the guard's allowlist is what stops it.
- **Snapshot before `Popen`, not after.** A baseline taken while the agent is
  already running bakes in whatever it wrote first.
- **`--once` drains the queue**, it does not do one pass. A synchronous advance
  counts as work.

## Conventions

- Stdlib first. The only runtime dependency is PyYAML, via `uv` inline metadata.
  Adding a dependency needs a reason a few lines of stdlib cannot cover.
- Non-trivial logic leaves one runnable check behind. Both suites are plain
  asserts — no fixtures, no frameworks.
- A test must fail when the code breaks. Two tests in this repo once passed
  vacuously and an adversarial review caught both; if you cannot state the
  input that makes your new test fail, it is not a test.

## When changing this tool with this tool

The agent edits its worktree copy while the dispatcher runs from the main
checkout, so there is no mid-run self-modification hazard.

But a change to `pipeline/hooks/dangerous-commands.py`, `transition()`, `validate_meta()`
or `CONTROL_FIELDS` **requires human review before merge**, whatever the
pipeline says. A pipeline that can weaken its own guard unattended is the one
failure mode worth refusing to automate.
