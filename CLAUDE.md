# agent-pipeline

A ticket-driven agent pipeline. Agents never talk to each other; they talk
through a ticket file. A dumb dispatcher owns the state machine and spawns a
stateless `claude -p` per stage. See `README.md` for how to use it.

`AGENTS.md` is a symlink to this file so Codex, OpenCode, and other clients
that use the shared agent-instructions convention receive these same rules.
Keep one source of truth here rather than adding harness-specific copies.

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
   `cap_for()` scales a stage's `max_usd` the same way for the stages in
   `USD_SCALED`, capped at `USD_CEILING_FACTOR` times the stage's own number;
   a project's own `max_usd` is never scaled past unless it also sets
   `scale_usd = true`.
   A pass can credit failures back -- a passing `revalidating` writes
   `stale_regate_cleared` and `charge()` subtracts it, so `stale_regate`
   bounds CONSECUTIVE failures; the credit never exceeds the failures
   charged, so the loop stays bounded.
4. **Hooks decide with code.** `pipeline/hooks/dangerous-commands.py` is the only layer
   that makes a promise. Read-only stages get an *allowlist*, not a blocklist —
   do not "improve" it back into pattern matching.
5. **Values from ticket files are hostile.** `id`, `branch`, `test_file`,
   `deletes`, `files_declared` all reach a shell. Validate with `validate_meta()` on the
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
| `pipeline/templates/` | the ticket schema, the per-project config example, and the skills init installs: file-ticket and pipeline-config |
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
commands, no harness-specific skills, subagents, or slash commands. CLI
differences belong in `pipeline/harnesses/*.toml`.

As of 2026-08-22 **no stage declares `skills:`**. `triage`, `planning` and
`implementing` each invoked one superpowers skill, on 70 of 100 runs between
them — so the skill body was being paid on most runs anyway, and the `Skill`
tool plus a 46-skill listing rode on top of it. The three are inlined and
trimmed into the stage prompts (see `NOTICE`; they are MIT), which is both
cheaper and what the paragraph above asks for. The frontmatter key and every
branch behind it still work: declare `skills:` on a stage and it gets Claude's
tool and `/name`, or Codex's native `$name`, in the prompt. What the
stages must **not** do is depend on a plugin being installed on the operator's
machine — `--setting-sources project` means one is not.

## Commands

```sh
uv run --group dev pytest -q                # the dispatcher suite
./pipeline/hooks/test_dangerous_commands.py # 138 guard cases (table-driven)
```

`pytest` sees the allow/block tables through `test_the_allow_and_block_tables`,
which calls `tables()`. Until TICKET-057 the tables ran only under
`__main__`, and `pytest` missed all 80 of them — so the pipeline's own
`test_one` could report a red guard as green. Running the script directly is
still worth it: it prints one line per case, and the failure names the case.

## Gotchas, each found the hard way

- **The dispatcher runs under `uv`'s venv.** Left alone it shadows the target
  project's interpreter, so every project command runs against the wrong Python.
  `project_env()` strips it; use `run_cmd`, never bare `subprocess`.
- **A test that *errors* exits non-zero exactly like one that fails.** The gate
  requires the test's name in the output, or a missing dependency reads as a
  successful reproduction. The same trap hits `test_suite_without_new`: a shell
  syntax error also exits non-zero with no test ever run, so `suite_ran()` in
  `pipeline/core/gate.py` gates the pre-existing-breakage verdict on evidence
  of a run, not just the exit code (TICKET-074).
- **An exit-0 repro run in the worktree falls through to the base run.** A
  ticket resumed to `plan-validation` after `implementing` landed the fix has
  a worktree where `test_file` passes, and failing on that made Tier A
  permanently unsatisfiable. `gate()` reports the exit-0 finding only when
  the test does not also FAIL on base; failing on base is the durable proof
  the branch already carries the fix (TICKET-090).
- **The base SUITE run uses base's own test files; only the per-test base run
  copies the branch's.** `_base_findings()` copies the ticket's test file
  onto the base checkout, because the new node does not exist on base at all
  (DEC-017). `_base_suite()` must not: a defect the branch introduced in
  shared code in that same file rides along, base comes back red for a
  reason its own file never had, and `gate()` reports the branch's own bug as
  `ENVIRONMENT` -- "not this branch's doing" -- escalating and charging
  nothing (TICKET-104). The ticket's nodes are kept out of the base run by
  `test_suite_without_new`'s selector instead.
- **`git worktree add -B` resets the branch.** Never use `-B`: recreating a
  worktree after a resume would silently discard the ticket's commits.
- **`.project/` is excluded from the read-only tree snapshot**, because writing
  to the ticket is every stage's job. The guard's path rule blocks a file tool
  there, and Bash still reaches it, which is why `project_config()` reads HEAD
  (`git show HEAD:./.project/pipeline.toml`), so an
  uncommitted edit is inert; it falls back to disk only when git does not have
  the file YET (a fresh, uncommitted `pipeline init`). Where `.project/` is
  git-ignored (`init --private`) git will NEVER have the file, so
  `project_config()` pins a copy under `config_dir()/pinned/` on first read
  instead -- `pipeline config --sync` is the only way to adopt a later edit. A
  committed edit lands in the ticket's diff, and `.project/pipeline.toml` is in
  `machine.FENCED`, so it parks at `awaiting-merge`.
- **`-j` is the dispatcher's machine-wide budget, shared across projects.**
  `machine_watch()` and `machine_share()` in `pipeline/daemon/supervisor.py`
  hold every ticked project's `inflight` dict in one map; a project starts a
  child only while the total across projects is under `-j`, and never more
  than an equal share of `-j` among the projects that reported demand at
  their last tick. `serve()` rotates which project ticks first each pass.
  The budget is per dispatcher PROCESS, so a `pipeline run` beside a
  `pipeline start` gets its own `-j`. `max_parallel` in
  `.project/pipeline.toml` still only lowers one project's own number, and a
  bad value is printed and ignored.
- **`--add-dir` is inert under `bypassPermissions`** (headless spawns run under
  it) -- the guard's path rule is what confines a stage, not this flag. A
  read-only stage's baseline is two snapshots: `tree_snapshot(wt)` plus
  `dirty_snapshot(project)` — the second without HEAD, because `merging`
  moves the main checkout's HEAD mid-run.
- **`pty.fork`, never `openpty` + `Popen`.** Only fork gives the child a
  *controlling* terminal, and a TUI without one draws nothing. The winsize is
  set in the child before `exec` for the same reason: a child that reads 0x0
  renders an empty screen.
- **An interactive stage is only interactive while a client is attached.**
  `spawn()` asks two questions: `poller.attachable` (is there a socket --
  `Server` sets it, the bare `Poller` `pipeline run` builds does not) and
  `poller.watchers(project)` (is a client subscribed right now). Gating on
  `attachable` alone was wrong: a daemon with nobody on it still spawned a
  REPL, and it parked at a prompt nobody could see until the lease expired
  twice (TICKET-059). A TUI that attaches after the spawn gets a headless
  stage; that race is accepted.
- **`notice_once()` in `pipeline/core/__init__.py` holds a module-level set
  of keys.** `spawn()`'s headless line and `cap_config()`'s pinned-`max_usd`
  warning both go through it, keyed on the project and the stage; both fire
  from inside `spawn()`, so an un-deduped line repeats for every ticket
  forever and buries the per-ticket lines (TICKET-096). A new `spawn()`
  print that states a fact about the setup rather than about the ticket
  belongs there too. `reset_notices()` is the test seam.
- **A REPL does not exit when the agent writes `.result`.** `finish()` fires on
  `proc.poll()`, so `end_interactive()` SIGTERMs an interactive child once its
  sidecar appears. Without it the lease expires twice and the ticket escalates
  with its work already done.
- **`lease.expires` is hostile input like every other field.** Unquoted, YAML
  parses it as a `datetime`, not a `str`. `lease_expiry()` is total and
  `validate_meta()` escalates what it cannot read -- `lease_active()` runs in
  `ls`, before anything has validated anything.
- **A lease is renewed while its child lives, but not on every tick.** A stage
  outliving `LEASE_MINUTES` used to show an expired lease while working, and
  `drain_expired()` TERMINATED it on any source-change drain -- so a merged
  dispatcher change killed every stage older than 30 minutes. `tick()` now
  renews an inflight ticket's lease through `Ticket.renew_lease()`, and only
  once less than half the lease remains: each renewal rewrites the ticket file
  the agent is also writing, and a write every 10s races its `## Thread`
  append. Renewal is skipped while `stopping()`, so DEC-123's bounded drain
  still ends. Nothing renews a dead holder's lease, so `lease_expiries`
  recovery is untouched, and `ticket_rows()` requires `lease_active()` AND
  `holder_alive()` before it reports `leased` -- `ls` showing `LEASED` for a
  dead stage misled the operator twice (TICKET-141).
- **Only one merge runs at a time.** Two tickets merging in one tick both
  `git merge base`, and the first fast-forward moves base under the second.
  `start()` waits, exactly like `files_conflict` does. `start()` also holds a
  `merging` ticket behind any ticket parked at a `HUMAN_GATES` stage whose
  `files_declared` overlap -- `conflict_holder()`'s `inflight` list never sees
  a parked ticket, so `parked_meta()` reads those tickets off disk and the
  wait is reported through the same `waiting` key (TICKET-105).
- **Ordering has two sources, and only one is a proxy.** `files_conflict`
  orders two tickets that declare the same file; `depends_on` in a ticket's
  frontmatter orders two that share no file at all. `start()` consults
  `dep_unsatisfiable()` then `dep_holder()` (`pipeline/core/machine.py`)
  above the `new` advance, waits exactly as it does for a file overlap, and
  reports the wait through the same `waiting` key -- {on, stage} for a
  dependency, {on, file} for an overlap. The field is the human's: it is in
  `CONTROL_FIELDS` and in no `CLAIMS` entry, so a stage that writes it
  escalates the ticket.
  A project exempts a path from the FILE half with `[conflict] ignore` in
  `.project/pipeline.toml`, read by `project_conflict_ignore()`. It exists
  because a repo where every ticket appends to one ledger (`PROGRESS.md`) runs
  one ticket at a time -- 71.7 hours of waiting against 12 hours of work in the
  project it was found in. Entries are exact paths, never globs; a shared code
  file still orders two tickets; a bad value is printed once and ignored. Both
  `conflict_holder()` calls in `start()` take the set -- the inflight one and
  the `parked_meta()` one -- or a `merging` ticket still waits on a parked
  ledger overlap (TICKET-143).
- **A human approval survives a recut, and only a recut.** `cmd_approve`
  records `approved_plan_hash`, a digest of `PLAN_SECTIONS` (`## Plan`,
  `## Acceptance criteria`, `## Rollback`); `advance()` recomputes the verdict
  through `approval_carries()` and rewrites `ok` to `approved`, so a sidecar
  word can never buy an approval. The hash is dropped on EVERY route into
  `implementing` -- `advance()`'s own, and `start()`'s, which is what
  `pipeline resume --stage implementing` takes. That second pop is the whole
  safety argument: `revalidating` may `git reset --hard`, so a branch carrying
  implementation commits must never reach it on a carried approval (DEC-029,
  TICKET-144). `approved_plan_hash` is in `CONTROL_FIELDS` and validated by
  `validate_meta()` as a sha256 hex digest.
- **A stage corrects a decision record through the dispatcher, never by hand.**
  `.project/decisions/` is outside every stage's writable paths, so a stage
  that finds a false claim writes `correction: DEC-<digits> -- <text>` in its
  sidecar and `_finish()` appends it through `correct_decision()`. Append-only
  and idempotent on replay: the body is never rewritten, the record stays
  ACTIVE, and the correction qualifies one claim where `supersedes:` replaces
  the whole record. `_finish()` gates on the VALUE, not the key -- `_common.md`
  ships `correction: null` in the sidecar template, and gating on the key put a
  false finding in every ticket's thread (TICKET-142). A bad id is a `finding`,
  never a crash.
- **The gate's two dead ends both have a way out now.** `[gate] quarantine` in
  `.project/pipeline.toml` excludes named nodes from the SUITE run only, never
  from the ticket's own `test_file`, and the gate names every active entry in
  its thread entry so a quarantine cannot rot unnoticed. And a `LOAD-FLAKY`
  verdict (the test exits 0 in the worktree AND on base) names
  `pipeline resume <id> --stage revalidating`, which accepts that double pass
  -- the recovery for a ticket whose fix landed while it waited. At
  `plan-validation` the same double pass still escalates (TICKET-145).
- **`merging` rebases before it merges, and the rebase may not fail the
  child.** `merge_cmd()` runs `git rebase <base> || git rebase --abort` and
  then the `git merge --no-edit <base>` that was always there. The rebase
  keeps base's history linear. The merge decides, because `git rebase`
  refuses a worktree with unstaged changes that `git merge` lands. A conflict
  still escalates and nothing resolves one. A `git rev-list --count`
  comparison guards the rebase: `git rebase` silently skips or empties a
  branch commit whose patch already landed on base, and the guard restores
  the pre-rebase tip rather than let a dropped commit vanish, so the merge
  below lands it as a merge commit instead (TICKET-105).
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
- **`Ticket.save()` writes two destinations.** The main checkout's file, and a
  `0444` mirror at `<worktree>/.project/tickets/<id>.md`, marked
  `git update-index --skip-worktree` in the worktree's own index. Without the
  mirror, the worktree copy is the branch-cut snapshot, and `implementing`
  reads its own prompt as fabricated (TICKET-067). Without the mark, a write
  there leaves the worktree dirty, and `merging`'s rebase fails with
  `error: cannot rebase: You have unstaged changes.`
- **`gate()` quotes each distinct output once and references the rest.** A
  re-gate re-runs the same test against the same code, so its fence is
  byte-identical to one the thread already holds, and `_dedupe()` replaces
  the copy with a pointer to the entry that carries it. Never fix thread
  growth by truncating or summarising the fence -- `pipeline/stages/_common.md`
  rule 7 requires verbatim output. A finding that fires again on the SAME
  ticket also gains one indented line naming
  `.project/stages/planning.extra.md` and the count so far. It names
  `planning`, not the gate's own `plan-validation`, because the stage that
  WRITES a plan is the one a repeated finding is a missing rule for;
  `GATE_STAGE` and `RULE_STAGE` in `pipeline/core/gate.py` keep the two apart.
  `_count_findings()` keys the count on the finding's FIRST line, because
  `_dedupe()` has already rewritten the fence by then, and it counts
  `kind == "gate"` entries only, because `advance()` copies the same findings
  into a `transition` entry.
- **The harness `.toml` is re-read once per tick**, by `_harness_reloader()`
  in `pipeline/daemon/supervisor.py`. Before this, `run()` and `serve()` each
  read it once above their loop, so a harness change that merged mid-run
  reached nothing until the dispatcher restarted. A failed re-read keeps the
  last good dict instead of killing the loop.
- **A merged change to the dispatcher's own Python is inert until restart.**
  `_source_watcher()` in `pipeline/daemon/supervisor.py` snapshots the mtimes of
  the loaded `pipeline` modules. When one moves, `run()` and `serve()` stop
  claiming tickets, reap what is inflight and return `reason="source_changed"` --
  so whatever started them runs the merged code. `serve()`'s `finally` emits
  `daemon_stop` carrying that reason and the module that moved; `pipeline
  status` and the TUI status bar read it back through `daemon_notice()`.
  `pipeline start --restart-on-upgrade` re-execs the daemon into the merged
  code, at most 3 times in 60s; without that flag nothing restarts it. Never
  `importlib.reload()`; live child records, an open SQLite handle and signal
  handlers outlive the modules. The drain is bounded by the lease: `drain_expired()` terminates an inflight child that outlives its lease during that drain, through the same `stop_child()` path `shut_down()` uses, so one stage that never exits cannot park the dispatcher while it still answers its socket (TICKET-123). A child whose lease is still live is waited for, exactly as DEC-032 requires.
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
- **An MCP tool is guarded by server, not by command.** The `PreToolUse`
  matcher is `Bash|Write|Edit|MultiEdit|NotebookEdit|mcp__.*`.
  `dangerous-commands.py` parses shell and cannot judge
  `mcp__github__create_pr`, so it allows a call only when the server is in
  `PIPELINE_MCP_ALLOW`, and in a read-only stage only when it is also in
  `PIPELINE_MCP_READONLY`. `spawn()` sets both from `[mcp.<name>]` in
  `.project/pipeline.toml` intersected with the stage's `mcp:` frontmatter. A
  server declared without `readonly = true` is unusable from every
  `write: false` stage.
- **A PTY log carries the width it was written at.** An interactive stage's log
  opens with `\x1b]9999;<rows>;<cols>\x07` and gains one more marker per
  resize; `render_pty()` replays the dump at that geometry instead of a fixed
  40x120. A batch log must never get one -- `tail_log()` sniffs a PTY dump by
  the raw ESC (DEC-039), so a marker there sends stream-json through pyte.
  `#log` writes those lines with `RichLog.write(line, width=cols)`, so a pane
  narrower than the dump clips and scrolls horizontally instead of re-flowing
  a screen; stream-json lines pass `width=None` and still wrap.
- **The Tier A gate runs as a spawned child (`gate_cmd()`), not inline.** A
  PASS at `plan-validation` is a phase of the stage, carried in
  `counters["gate_ok"]` and consumed by the next `start()`, which spawns the
  Tier B agent -- it emits no `stage_end`, or one run would put two rows in
  view 1's denominator. Moving the gate back inline stalls the select loop
  for the length of the project's suite, exactly the bug TICKET-061 fixed.
- **`gate_result()` splits a Tier A failure at `plan-validation` into six
  verdicts: `fail` (structural), `bad-plan` (substantive), `no-test-file`
  (the `test_file` names no file), `load-flaky` (the `test_file` exits 0 in
  the worktree and on base), `invalid-test` (the selected test hides
  statically unreachable statements) and `environment` (the suite is red on
  base too) -- the last four escalate and charge nothing.** `structural_only()`
  in `pipeline/core/gate.py` classifies the findings against `STRUCTURAL_MARKS`, a
  `startswith` prefix allowlist: an unlisted finding reads as substantive on
  purpose, so a new structural finding in `gate()` needs its own mark or it
  silently charges `plan_validation_attempts` instead of
  `structural_gate_failures` like a bad plan. `MISSING_TEST_MARK`,
  `LOAD_FLAKY_MARKS`, `INVALID_TEST_MARKS` and `ENVIRONMENT_MARKS` are four more
  `startswith` allowlists beside it, checked by `missing_test_file()`,
  `load_flaky()`, `invalid_test()` and `environment_only()` in that order, all
  before `structural_only()`. Each escalates through an enumerated
  `transition()` row that charges no counter, and all four apply at
  `plan-validation` only: `revalidating` still gets `fail`, whatever the
  findings say (DEC-029).
- **The read-only allowlist has a per-project extension.** `[readonly] allow`
  in `.project/pipeline.toml` is exported as `PIPELINE_READONLY_ALLOW`, an
  argv-prefix list matched per shell segment. It never overrides
  `always_rules()` or the redirection rule, and `tables()` in the guard's own
  test file pops the variable so `BLOCKED_READONLY` still means default deny.
- **The registry refuses a git worktree, and refuses a stage.**
  `is_worktree()` in `pipeline/daemon/registry.py` reads the `.git` *file*'s
  `gitdir:` pointer; `register()` raises and `projects()` skips, so a line
  written before the fix goes inert without an unregister. `register()`/
  `unregister()` also refuse when `PIPELINE_STAGE` is set -- a guardrail, not
  a boundary, since the registry lives outside the worktree, the ticket's
  diff and `machine.FENCED` (TICKET-072).
- **A budget kill is not a crash, and the stream says which it was.** Claude
  Code's final `result` event carries `terminal_reason`, which
  `--max-budget-usd` sets to `budget_exhausted`. `terminal_sink()` keeps it on
  the child's record and `_finish()` escalates on the FIRST one, naming the
  cap, instead of charging `no_result` and respawning into the identical
  spend. An interactive stage emits no `result` event, so it is never
  classified this way -- and it writes its `.result` LAST, because
  `end_interactive()` SIGTERMs on the sidecar.
- **A run's cost and tokens are reported once, in its session thread entry.**
  `terminal_sink()` keeps `total_cost_usd` and `usage` off the same `result`
  event it already reads `terminal_reason` from, and `cost_report()` renders
  the two lines `_finish()` appends next to the replay command. The two lines
  are independent: a Codex `turn.completed` has tokens and no dollar amount,
  so the cost reads `unknown` and the tokens still show (TICKET-120). An
  interactive stage emits no `result` event at all, so its `usage` stays
  empty and it gets neither line; its tokens reach the event log through
  `usage_events()` instead.
- **`test_file` holds one test or a list.** `test_one` runs once per listed
  test, so the name-in-output check stays meaningful for each; only
  `test_suite_without_new` runs once for all of them, and `{test:--deselect }`
  is how a flag that takes one value at a time (like pytest's `--deselect`)
  excludes them all in that single run.
- **`deletes` is planning-owned exact test data.** Every selector must already
  be in `test_file`; an empty list clears stale exclusions. The gate skips only
  declared selectors for reproduction checks, while suite formatting still sees
  every selector and never infers deletion from plan prose.
- **A transient `fork` EAGAIN must not end a stage or the loop.**
  `retry_eagain()` in `pipeline/core/worktree.py` retries a `BlockingIOError`
  3 times with 0.25/0.5/1.0 s backoff, and every spawn primitive goes through
  it -- both `subprocess.Popen` calls in `pipeline/daemon/supervisor.py`,
  `subprocess.run` in `run_cmd()`, and `pty.fork()` in `pipeline/pty/host.py`.
  `run()` catches per tick like `serve()` does, so an error that outlives the
  retries escalates one ticket through `bail()` and never reaches `finally:
  shut_down(project, inflight)`. Two consequences: a new spawn primitive that
  skips the helper reopens TICKET-086, and a test that detects a runaway loop
  by raising from a fake `tick()` must raise a `BaseException` subclass, or
  either catch eats it and the test hangs instead of failing.
- **`init` installs every packaged skill for Claude under `.claude/skills/`
  and for Codex under `.agents/skills/`, and records each target's sha256 in
  `<project>/.project/skills.json`.** That record is the only way
  `skill_status()` tells a stale copy from a customised one; a copy with no
  record reads as `unknown` and is never rewritten without `--force`. A
  symlinked copy, which is this repo's own layout, is never written at all.
- **A Codex stage sees no ambient skill catalog.** `native_skill_settings()`
  disables discovered host and repo paths. When a stage declares `skills:`, it
  re-enables only those worktree paths after their bytes match the main
  checkout's trusted copies; Codex needs `skills.include_instructions=true` for
  `$name` to resolve at all. This was checked with `codex debug prompt-input`
  0.153.4, which listed only the selected skill.
- **A Codex write stage cannot use `workspace-write`.** A linked worktree's
  index and ticket-branch ref live in the main checkout's `.git/worktrees/`
  and `.git/refs/`, outside the worktree sandbox, so `git commit` fails creating
  `index.lock`. `codex.toml` uses `danger-full-access` for write stages and the
  blocking pipeline hook as the boundary, matching Claude's
  `bypassPermissions`; read-only stages retain `workspace-write`. Replacing
  this with `--add-dir <project>/.git` is not safer: it grants arbitrary writes
  to all repository metadata while making the sandbox look narrower.

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
`pipeline/harnesses/codex.toml`,
`transition()`, `validate_meta()`, `CONTROL_FIELDS`, `FENCED`, `strip_settings_sources()`,
`.project/pipeline.toml` or `.project/stages/` **requires human review before merge**, whatever the pipeline says.
A pipeline that can weaken its own guard unattended is the one failure mode worth
refusing to automate.

This is enforced, not just written down: `machine.FENCED` names the same
things in code, a diff touching any of them parks at the `awaiting-merge`
gate instead of landing on its own, and
`tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` keeps this
paragraph and `machine.FENCED` from drifting apart.

**The installed `file-ticket` skill is part of the interface.** Claude reads it
at `.claude/skills/file-ticket/SKILL.md`; Codex reads the same packaged skill at
`.agents/skills/file-ticket/SKILL.md`. A session uses it before filing work into
this pipeline, so a change to a CLI command, a stage's behaviour, or the human
gates is not finished until the skill says the same thing. A skill describing a pipeline that no longer exists sends
every future ticket in wrong, and nothing tests it. This repo's installed copies
are symlinks to `pipeline/templates/skills/file-ticket/SKILL.md`, and `pipeline init`
copies every directory under `pipeline/templates/skills/` into the projects it
scaffolds -- `pipeline-config`, which teaches a session to write and *verify*
this file's three test commands for a non-pytest project, ships the same way and
carries the same obligation.

**The main checkout must be parked on the base branch while the dispatcher
runs.** `merging` refuses to land otherwise -- "main checkout is parked on
`<branch>`, not the base branch" -- and the ticket escalates with its work done.
Read that message as "check out `main`", not as a merge conflict.
