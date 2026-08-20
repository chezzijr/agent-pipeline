# Ticket-driven agent pipeline

Agents do not talk to each other. They talk through a ticket file, one stage at
a time, each in a fresh stateless process. A dumb dispatcher owns the state
machine; no model ever decides what happens next.

This is a pipeline, not a session tree. Nothing forks a parent session, so no
process sits holding context while it waits, and nothing dies because its caller
did. Tickets are the queue; agents are stateless workers pulled off it.

    triage -> planning -> plan-validation -> [human] -> implementing
                                                            |
                        done <- merging <- verifying <- review

## Why

- **Less context per stage** -- less hallucination, and a stage that dies is
  respawned from the ticket rather than resumed from a transcript.
- **Enforceable gates** -- the mechanical checks are a script, so they cannot be
  talked out of. The agent supplies judgment; the dispatcher supplies promises.
- **Bounded loops** -- every retry is counted, and the second failure of any
  loop escalates to a human instead of ping-ponging.

## Use

```sh
uv tool install .                             # `pipeline` and `pipelined` on PATH

pipeline init ~/code/myproject                # scaffold .project/
$EDITOR ~/code/myproject/.project/pipeline.toml   # how to run this project's tests
pipeline --project ~/code/myproject new "cache leaks on evict"
pipeline --project ~/code/myproject run       # dispatcher loop
pipelined --project ~/code/myproject          # the same loop, as its own command

pipeline --project ~/code/myproject status
pipeline --project ~/code/myproject approve TICKET-001
pipeline --project ~/code/myproject reject  TICKET-001 "ignores cache invalidation"
pipeline --project ~/code/myproject resume  TICKET-001 \
    --stage planning --reset plan_validation_attempts
```

Without installing it, `uv run python -m pipeline …` runs the same CLI.

`run --once` drains the queue and exits -- what you want while you are still
watching it. Plain `run` keeps polling.

## Concurrency

    pipeline --project ~/code/myproject run -j 4

Each ticket gets its own git worktree under `.worktrees/<ID>`, created from
`base` and removed when the ticket reaches a terminal stage. Two tickets cannot
share one checkout, which is why worktrees and parallelism arrive together.

Ticket files stay in the **main** checkout, not the worktree. They are the queue,
and keeping them in one place is also what stops parallel agents from producing
merge conflicts on their own ticket threads.

`done` means landed. Once the suite passes, `merging` merges `base` into the
ticket's own worktree and then fast-forwards the **main** checkout onto the
ticket branch. Fast-forward only, and only while the main checkout is actually
on `base`, so a dirty, diverged or elsewhere-parked checkout escalates instead
of landing half of it -- and a conflict escalates with the conflicted worktree
left in place for you to open.

Two tickets whose `files_declared` intersect never run at the same time -- the
second one waits rather than failing. That ordering is silent, so `status` flags
anything sitting still for more than `STALE_HOURS`.

Per-project worktree setup (shared build cache, `.env`, dependency install) is
one config line, so it is never improvised by an agent:

```toml
worktree_setup = "ln -s ~/.cache/cargo-target target && cp ../../.env ."
```

## Watching a run

Every spawn gets a session id and a log:

```
$ pipeline --project ~/code/myproject status -v
TICKET-001   review    bugfix  {'review_loops': 1, ...}
             last: review log=.project/logs/TICKET-001-review-3582ef02.log
                   replay=`claude --resume 3582ef02-...`
```

`tail -f` the log while it runs; `claude --resume <id>` to open the session and
see what the agent actually did. There is no daemon manager here on purpose --
run the loop under systemd or tmux, which already solve supervision.

## The three invariants

0. **No agent waits on another agent.** The dispatcher launches and returns;
   `reap()` collects finished processes on the next tick. A stage that hangs
   burns its own lease and nothing else.
1. **An agent never writes `stage` — enforced, not requested.** It writes
   `.project/tickets/<ID>.result` with `result: ok|fail|blocked|rejected`;
   `transition()` maps that to the next stage. The agent *can* edit the ticket
   file, so the dispatcher restores every control field (`stage`, `counters`,
   `branch`, `lease`, …) from a snapshot taken before the spawn, and escalates
   the ticket if any of them changed. An unrecognised result escalates rather
   than guessing.
   It also cannot rewrite a field it does not own: only `triage` sets
   `test_file`, only `planning` sets `files_declared` (implementation may add to
   it, never shrink it). Otherwise a reviewer could shrink the declared set and
   unblock a ticket that overlaps one already in flight.
2. **Read-only stages are checked, not trusted.** The dispatcher snapshots the
   tree before starting the process and escalates if it changed. On top of that
   the guard hook gives read-only stages an *allowlist* — git read subcommands,
   test runners, grep and friends — so a bypass needs a hole in a short list of
   permitted programs, not a gap between blocked patterns.
3. **Every value that reaches a shell is validated and quoted.** `id`, `branch`,
   `test_file` and `files_declared` all live in a file an agent can write and all
   end up in shell commands, so they are pattern-checked on the way in
   (`validate_meta`) and `shlex.quote`d on the way out. A ticket that fails
   validation is escalated, never executed.
4. **The regression suite and the merge are run by the dispatcher.**
   `verifying` and `merging` have no agent at all -- a test result should never
   pass through a model's mouth, and a merge conflict is never auto-resolved:
   `merging` escalates and keeps the conflicted worktree as the evidence.

## Layout

    pyproject.toml               `pipeline` + `pipelined` entry points
    pipeline/core/machine.py     the transition table. Pure, no I/O.
    pipeline/core/ticket.py      ticket files: load, validate, save, thread
    pipeline/core/config.py      stage/harness/project config and prompt assembly
    pipeline/core/gate.py        the Tier A gate
    pipeline/core/worktree.py    per-ticket checkouts and project commands
    pipeline/daemon/supervisor.py  the dispatcher loop
    pipeline/cli/main.py         the human-facing commands
    pipeline/stages/_common.md   rules every stage shares, incl. the failure protocol
    pipeline/stages/*.md         one self-contained stage: frontmatter (model,
                                 effort, write) plus the prompt. Harness-neutral.
    pipeline/harnesses/*.toml    how to spawn an agent. A new harness is a new file.
    pipeline/templates/          the ticket schema and the project config example
    tests/                       one file per module

Adding a stage means adding `pipeline/stages/<name>.md` and a row in
`transition()`. Nothing else knows the list.

The stages, hooks, harnesses and templates live inside the package because they
are located from `__file__` -- at the repo root they would not survive
`uv tool install .`.

Tickets live in the **target** project (`.project/tickets/`), not here, so they
branch, diff, and revert with the code they describe.

## Porting to another harness

`pipeline/harnesses/codex.toml` is a second harness written to find out where the
abstraction's seam actually sits -- untested against a real run (no codex account),
tested instead by asserting the rendered `cmd` string, the same way `fake.toml` is
exercised without a real agent (`tests/test_harness.py`).

Three of the five capability gaps between `claude` and `codex exec` were already
expressible with no code change: `effort_flag`, `session_flag` and `settings_flag`
are optional and default to `""` (`fake.toml` proved this first), and `max_usd`
maps to nothing simply by never appearing in the `cmd` template. `readonly_tools`/
`write_tools` also ported as-is -- codex has no per-tool allowlist, but it does
have a writability switch (`-s/--sandbox`), and both pairs express the same fact
("may this stage write?") in the harness's own vocabulary.

Two gaps forced the harness TOML format itself to grow a key:

- **No `--append-system-prompt`.** `prompt_mode = "system" | "inline"`. `"system"`
  (the default, what `claude-code.toml` declares) passes the composed prompt as a
  path the harness's own template reads. `"inline"` (what `codex.toml` declares)
  has `render()` read the composed prompt and prepend it to the work-ticket
  message as codex's one positional `PROMPT` argument.
- **No settings/hooks file.** `supports_hooks = true | false`. A stage that
  declares `hooks:` on a harness with `supports_hooks = false` makes `spawn()`
  raise instead of running the stage unguarded -- a hook is the only layer that
  decides with code (see `CLAUDE.md` invariant 4), and a harness that cannot
  register one gets refused, not silently downgraded to the tree-snapshot
  backstop alone. Every stage in this repo declares hooks, so every stage is
  refused on `codex.toml` today; that refusal, in code, is the honest answer for
  a harness with no hook mechanism.

`spawn()` used to build its command with one inline `.format()` call; that block
is now `config.render()`, a separable function a test can call without spawning
anything. The extraction is itself part of what porting to a second harness
found: the render step wasn't factored out until something needed to call it
without a subprocess.

Do not write a third harness speculatively -- this one only exists to answer
"does the seam hold," and it does, at the cost of exactly the two keys above.

## Tests

    uv run --group dev pytest -q
    ./pipeline/hooks/test_dangerous_commands.py   # NOT collected by pytest

Covers the transition table's bounds, gate rejections, worktree lifecycle,
frontmatter validation, the guard's allowlist, and every bypass an adversarial
review found — including the two traps from the build itself: the dispatcher's
own venv shadowing the project's, and a test that *errors* (missing dependency)
being indistinguishable from one that fails.

## Interrupting it

`Ctrl-C` / `SIGTERM` terminates every in-flight agent, releases its lease, notes
the interruption in the ticket, and cleans up temp files. Without that the
orphaned agent keeps writing while its lease expires, and the dispatcher spawns a
second agent onto the same stage in the same worktree.

## Not built yet

- **No real agent has run yet.** The stage prompts are the only unverified part;
  everything around them is tested against a fake harness.
- **`.project/decisions/` has no writer.** `planning.md` greps it; nothing ever
  appends to it, so the "do not revert this, it fixed a leak" case is still open.
- Per-class bounds, model tiering. Watch the escalation rate per stage -- the
  frontmatter counters give it to you for free.
