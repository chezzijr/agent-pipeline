# agent-pipeline

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
3. **Every bounded loop escalates at its class bound.** `BOUNDS[class][counter]`
   sets the budget, falling back to `MAX_ATTEMPTS` for an unknown class and for
   the dispatcher's own counters (`lease_expiries`, `no_result`), which are not
   class-scoped. Bounds live in the dispatcher; no stage prompt learns its
   budget. If you add a retry path, it charges a counter. An unbounded respawn
   is a bug, not a convenience.
   `BOUNDS[class][counter]` is the base; `bound_for()` adds one attempt per 8
   plan steps or 4 declared files for the counters in `SIZE_SCALED`, capped at
   `BOUND_CEILING`; `lease_expiries` and `no_result` stay on `MAX_ATTEMPTS`.
4. **Hooks decide with code.** `pipeline/hooks/dangerous-commands.py` is the only layer
   that makes a promise. Read-only stages get an *allowlist*, not a blocklist —
   do not "improve" it back into pattern matching.
5. **Values from ticket files are hostile.** `id`, `branch`, `test_file`,
   `files_declared` all reach a shell. Validate with `validate_meta()` on the
   way in and `shlex.quote` on the way out. Both, not either. `Ticket.save()`
   is the only writer and it validates on the way *out* too, so a hostile value
   cannot reach the file at all — a `.result` claim is validated before it is
   adopted, never after. The one `save(validate=False)` is `escalate()`, which
   quarantines a ticket whose frontmatter is what is wrong; it adds no value it
   did not read off disk. Do not add a second writer.
6. **The library never exits the process.** `PipelineError` is raised and the
   CLI turns it into `die()`. One broken project must not take the loop down.

## Where things live

| Path | Holds |
|---|---|
| `pipeline/core/` | `machine` (transition table), `ticket`, `config`, `gate`, `worktree` |
| `pipeline/daemon/supervisor.py` | the dispatcher loop: spawn, reap, apply the verdict |
| `pipeline/daemon/server.py` | the select loop. `watch(fd, cb)`/`unwatch(fd)` is how anything joins it; `Server` is `Poller` + AF_UNIX + NDJSON |
| `pipeline/daemon/store.py` | the append-only SQLite event log. `Store.emit()` is the only writer |
| `pipeline/daemon/registry.py` | the registry file (`$XDG_CONFIG_HOME`, else `~/.config`) `/pipeline/projects`, and the per-project `flock` |
| `pipeline/cli/main.py` | the `pipeline` command; `pipeline/daemon/main.py` is `pipelined` |
| `pipeline/cli/client.py` | connect/request/subscribe, and the file-based fallback for every one of them |
| `pipeline/stages/<name>.md` | one self-contained stage: frontmatter (`model`, `effort`, `write`, `tools`, `hooks`, `skills`, `max_usd`) + the prompt |
| `pipeline/stages/_common.md` | rules every stage shares, including the failure protocol |
| `pipeline/tui/app.py` | the Textual dashboard. One client argument, for the fake in `tests/test_tui.py` |
| `pipeline/stream/events.py` | `parse(line) -> dict`: one stream-json line to a normalised record. Never raises |
| `pipeline/harnesses/*.toml` | how to spawn an agent. Data, not code. A new harness is a new file |
| `pipeline/pty/host.py` | a `mode: interactive` stage on a real PTY: the fork, the `Popen` shim, the pyte screen |
| `pipeline/hooks/` | the guard and its tests |
| `pipeline/templates/` | the ticket schema and the per-project config example |
| `tests/` | one file per module, plain asserts; `tests/helpers.py` builds the throwaway projects |
| `.project/` | this repo's own tickets, decisions, logs |

Adding a stage = one `pipeline/stages/<name>.md` + one row in `transition()`.
A stage the dispatcher runs itself (`verifying`, `merging`) has no prompt file
at all: it goes in `DISPATCHER_STAGES` instead, spawns via `spawn_command()`
and is judged by an exit code. Nothing else enumerates the stages; a test
enforces that.

The data directories live **inside** the package on purpose: they are found via
`Path(__file__).parent`, so at the repo root they would be gone after
`uv tool install .`.

Stage prompts stay **harness-neutral** — plain instructions and shell/git
commands, no Claude Code skills, subagents, or slash commands. Anything
Claude-specific belongs in `pipeline/harnesses/claude-code.toml`.

As of 2026-08-22 **no stage declares `skills:`**. `triage`, `planning` and
`implementing` each invoked one superpowers skill, on 70 of 100 runs between
them — so the skill body was being paid on most runs anyway, and the `Skill`
tool plus a 46-skill listing rode on top of it. The three are inlined and
trimmed into the stage prompts (see `NOTICE`; they are MIT), which is both
cheaper and what the paragraph above asks for. The frontmatter key and every
branch behind it still work: declare `skills:` on a stage and it gets the tool,
the prompt block and its slash commands back, with no code change. What the
stages must **not** do is depend on a plugin being installed on the operator's
machine — `--setting-sources project` means one is not.

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
  to the ticket is every stage's job. The guard's path rule blocks a file tool
  there, and Bash still reaches it, which is why `project_config()` reads HEAD
  (`git show HEAD:./.project/pipeline.toml`), so an
  uncommitted edit is inert; it falls back to disk only when git has no copy at
  all. A committed edit lands in the ticket's diff, and
  `.project/pipeline.toml` is in `machine.FENCED`, so it parks at
  `awaiting-merge`.
- **`--add-dir` is inert under `bypassPermissions`** (headless spawns run under
  it) -- the guard's path rule is what confines a stage, not this flag. A
  read-only stage's baseline is two snapshots: `tree_snapshot(wt)` plus
  `dirty_snapshot(project)` — the second without HEAD, because `merging`
  moves the main checkout's HEAD mid-run.
- **`pty.fork`, never `openpty` + `Popen`.** Only fork gives the child a
  *controlling* terminal, and a TUI without one draws nothing. The winsize is
  set in the child before `exec` for the same reason: a child that reads 0x0
  renders an empty screen.
- **An interactive stage is only interactive if something can attach.**
  `spawn()` asks `poller.attachable` -- `Server` sets it, the bare `Poller`
  `pipeline run` builds does not. Gating on `poller is not None` was wrong:
  `run()` passes one, and the stage parked at a REPL nobody could reach.
- **A REPL does not exit when the agent writes `.result`.** `finish()` fires on
  `proc.poll()`, so `end_interactive()` SIGTERMs an interactive child once its
  sidecar appears. Without it the lease expires twice and the ticket escalates
  with its work already done.
- **`lease.expires` is hostile input like every other field.** Unquoted, YAML
  parses it as a `datetime`, not a `str`. `lease_expiry()` is total and
  `validate_meta()` escalates what it cannot read -- `lease_active()` runs in
  `ls`, before anything has validated anything.
- **Only one merge runs at a time.** Two tickets merging in one tick both
  `git merge base`, and the first fast-forward moves base under the second.
  `start()` waits, exactly like `files_conflict` does.
- **`merging` rebases before it merges, and the rebase may not fail the
  child.** `merge_cmd()` runs `git rebase <base> || git rebase --abort` and
  then the `git merge --no-edit <base>` that was always there. The rebase
  keeps base's history linear. The merge decides, because `git rebase`
  refuses a worktree with unstaged changes that `git merge` lands. A conflict
  still escalates and nothing resolves one.
- **Snapshot before `Popen`, not after.** A baseline taken while the agent is
  already running bakes in whatever it wrote first.
- **`--once` drains the queue**, it does not do one pass. A synchronous advance
  counts as work.
- **The merge lives at `merging`, not in the `done` cleanup path.** `escalated`
  is not in `CLEANUP_STAGES`, so a conflict keeps its worktree -- moving the
  merge into `start()`'s cleanup would delete the evidence in the same pass
  that produced it.
- **A stage reads a bounded view, not the ticket file.** `stage_view()`
  (`pipeline/core/ticket.py`) keeps every section except `## Thread`
  whole and trims the thread to the human-written kinds plus the last
  `VIEW_RECENT` entries; `spawn()` puts it in the composed prompt. The
  file on disk is unchanged and stays the protocol. A stage that reads
  the whole file to make an edit undoes the saving -- `_common.md`
  rule 4 is what stops it.
- **`gate()` quotes each distinct output once and references the rest.** A
  re-gate re-runs the same test against the same code, so its fence is
  byte-identical to one the thread already holds, and `_dedupe()` replaces
  the copy with a pointer to the entry that carries it. Never fix thread
  growth by truncating or summarising the fence -- `pipeline/stages/_common.md`
  rule 7 requires verbatim output.
- **The harness `.toml` is re-read once per tick**, by `_harness_reloader()`
  in `pipeline/daemon/supervisor.py`. Before this, `run()` and `serve()` each
  read it once above their loop, so a harness change that merged mid-run
  reached nothing until the dispatcher restarted. A failed re-read keeps the
  last good dict instead of killing the loop.
- **A merged change to the dispatcher's own Python is inert until restart.**
  `_source_watcher()` in `pipeline/daemon/supervisor.py` snapshots the mtimes of
  the loaded `pipeline` modules. When one moves, `run()` and `serve()` stop
  claiming tickets, reap what is inflight and return -- so whatever started them
  runs the merged code. Nothing restarts them: after that message, run
  `pipeline start` (or `pipeline run`) again. Never `importlib.reload()`; live
  child records, an open SQLite handle and signal handlers outlive the modules.
- **A stage inherits the operator's `~/.claude` unless told not to.** Without
  `--setting-sources project` a spawn loads every installed plugin, its skills,
  and its `SessionStart` hooks. On the machine this was found on that meant
  every stage — `implementing` included — opened in two personas nobody wrote
  for it: *"You are a lazy senior developer… shortest working diff wins"* and
  *"Respond terse like smart caveman."* It cost 5,392 tokens of opening context
  per turn, which was the smaller half of the problem. It keeps the guard —
  `--settings` is explicit and unaffected — verified 2026-08-22 under
  `--setting-sources project` *and* `--disable-slash-commands` together:
  `git worktree remove foo` came back "Blocked by the pipeline guard". Re-run
  that check if either flag changes; it is the invariant-4 condition. It does
  **not** keep the operator's `~/.claude/CLAUDE.md` or their
  `permissions.deny` rules — both stop reaching stages, and the deny rules did
  bind before (they survive `bypassPermissions`). The full list of what the
  flag costs is in `claude-code.toml`; every line of it was A/B'd against a
  live spawn, because a first draft asserted the opposite and was wrong.
- **A worktree-supplied settings file used to be able to disable its own
  guard.** Writing `<worktree>/.claude/settings.json` =
  `{"disableAllHooks": true}` drops the `--settings` PreToolUse hook with it,
  so every later spawn in that worktree would run unguarded.
  `strip_settings_sources()` in `pipeline/core/worktree.py` removes that file
  and `.claude/settings.local.json` before every spawn and before `start()`'s
  read-only baseline. A file written *mid-run* does not affect the run
  already going — settings are resolved at session start, verified against
  `claude` 2.1.238 on 2026-08-22 — so stripping at spawn is a complete
  defence. A tracked settings file is hidden with `--skip-worktree` so its
  deletion never enters the ticket's own diff.

## Conventions

- Stdlib first. Three runtime dependencies, and that is the budget: PyYAML;
  `pyte`, for the screen an interactive stage is attached to, imported
  *eagerly* (`cli/main.py` -> `daemon/supervisor.py` -> `pty/host.py`) because
  the supervisor hosts the PTY; and `textual` for `pipeline tui`, imported
  inside `cmd_tui` so nothing else pays for it. Adding a fourth needs a reason
  a few lines of stdlib cannot cover.
- Non-trivial logic leaves one runnable check behind. Both suites are plain
  asserts — no fixtures, no frameworks.
- A test must fail when the code breaks. Two tests in this repo once passed
  vacuously and an adversarial review caught both; if you cannot state the
  input that makes your new test fail, it is not a test.

## When changing this tool with this tool

The agent edits its worktree copy while the dispatcher runs from the main
checkout, so there is no mid-run self-modification hazard.

But a change to `pipeline/hooks/dangerous-commands.py`, `pipeline/harnesses/claude-code.toml`,
`transition()`, `validate_meta()`, `CONTROL_FIELDS`, `FENCED`, `strip_settings_sources()`,
`.project/pipeline.toml` or `.project/stages/` **requires human review before merge**, whatever the pipeline says.
A pipeline that can weaken its own guard unattended is the one failure mode worth
refusing to automate.

This is enforced, not just written down: `machine.FENCED` names the same
things in code, a diff touching any of them parks at the `awaiting-merge`
gate instead of landing on its own, and
`tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` keeps this
paragraph and `machine.FENCED` from drifting apart.

**`.claude/skills/file-ticket/SKILL.md` is part of the interface.** It is what a
session reads before filing work into this pipeline, so a change to a CLI
command, a stage's behaviour, or the human gates is not finished until the skill
says the same thing. A skill describing a pipeline that no longer exists sends
every future ticket in wrong, and nothing tests it.

**The main checkout must be parked on the base branch while the dispatcher
runs.** `merging` refuses to land otherwise -- "main checkout is parked on
`<branch>`, not the base branch" -- and the ticket escalates with its work done.
Read that message as "check out `main`", not as a merge conflict.
