# Ticket-driven agent pipeline

Agents do not talk to each other. They talk through a ticket file, one stage at
a time, each in a fresh stateless process. A dumb dispatcher owns the state
machine; no model ever decides what happens next.

This is a pipeline, not a session tree. Nothing forks a parent session, so no
process sits holding context while it waits, and nothing dies because its caller
did. Tickets are the queue; agents are stateless workers pulled off it.

    triage -> planning -> plan-validation -> [human] -> revalidating
      |                                                       |
      |    done <- merging <- [human?] <- verifying <- review <- implementing
      |                          |
      +-- (chore) -> implementing -> quick-review --+
                                                      |
      planning <- unwinding <-------------+   (fail: the cheap route's commit is undone first)

## What you need

- **Python 3.11+** and [uv](https://docs.astral.sh/uv/). Three runtime
  dependencies and that is the budget: PyYAML, `pyte`, `textual`.
- **An agent CLI.** [Claude Code](https://claude.com/claude-code) is the one
  harness that is exercised against real runs. Stage prompts are
  harness-neutral; everything CLI-specific lives in one TOML file, and
  `pipeline/harnesses/codex.toml` exists to prove that seam holds.
- **Linux or macOS.** POSIX only -- `fork`, a PTY, `flock`, a Unix socket and
  `selectors` -- with no Linux-only syscall on any path, so both are supported.
  Not Windows: WSL is the way there.
- **A git repo to point it at** -- the pipeline works on *your* project, not on
  itself. Each ticket gets its own worktree.

## Status

Working, and used on itself. This repo runs its own pipeline: 32 tickets landed
across 216 stage runs. The most recent is a fair example of the loop closing --
an adversarial review of a hand-written change found a hole in the guard, that
became `TICKET-034`, and the pipeline planned and implemented its own fix,
stopping twice at a human gate on the way. `.project/` is the real record --
tickets, decisions, threads and all -- so you can read what the agents actually
did rather than take this page's word for it.

Not a product. There is one registered project (this one), and one known gap:
stage prompts and hooks live inside the package, so customising them is global
rather than per-project (`TICKET-035`).

## Why

- **Less context per stage** -- less hallucination, and a stage that dies is
  respawned from the ticket rather than resumed from a transcript.
- **Enforceable gates** -- the mechanical checks are a script, so they cannot be
  talked out of. The agent supplies judgment; the dispatcher supplies promises.
- **Bounded loops** -- every retry is counted, and a loop escalates to a
  human at its bound -- two failures for most, more for plan-validation on a
  large plan, never more than five.

## Use

```sh
uv tool install .                             # `pipeline` and `pipelined` on PATH

pipeline init ~/code/myproject                # scaffold .project/
pipeline init ~/code/myproject --private      # ...and hide it from git, this clone only
$EDITOR ~/code/myproject/.project/pipeline.toml   # how to run this project's tests
pipeline --project ~/code/myproject new "cache leaks on evict"
pipeline --project ~/code/myproject run       # dispatcher loop, no daemon; interactive stages run headless

pipeline --project ~/code/myproject ls
pipeline --project ~/code/myproject plan TICKET-001    # the plan and its acceptance criteria, nothing else
pipeline --project ~/code/myproject approve TICKET-001   # -> revalidating, or -> merging from awaiting-merge
pipeline --project ~/code/myproject reject  TICKET-001 "ignores cache invalidation"
pipeline --project ~/code/myproject resume  TICKET-001 \
    --stage planning --reset plan_validation_attempts
pipeline --project ~/code/myproject resume  TICKET-001 \
    --stage planning --grant plan_validation_attempts   # hand back one spent attempt, not the whole budget
```

`init` also installs `.claude/skills/file-ticket/SKILL.md` -- the protocol a
session reads before filing a ticket -- and prints where it put it. An
existing file is kept, so a project that customised it keeps its version.

Once `.project/` is committed, `pipeline.toml` is read from git `HEAD`, so an
edit takes effect at the next commit -- a ticket working on a branch must not
be able to change the commands that judge it. Until it is committed (and under
`--private`, which never commits it) the file on disk is read as-is.

Without installing it, `uv run python -m pipeline …` runs the same CLI.

`run --once` drains the queue and exits -- what you want while you are still
watching it. Plain `run` keeps polling.

## Sharing a repo with people who do not use this

`.project/` is committed by default: the tickets and especially
`.project/decisions/` are a record, and `planning` greps the decisions so it
does not re-litigate a choice somebody already made.

That is wrong for a repo where you are the only one running the pipeline.
`pipeline init --private` writes `.project/` into `.git/info/exclude`, which is
**per-clone and never committed** -- no line about a tool your teammates do not
use lands in their diffs. Everything still works; the tickets are simply a
local queue, and the dispatcher says so when it skips recording one:

    TICKET-001: not recording -- `.project` is git-ignored here

`init` is idempotent, so this also retrofits a project that already has a
`.project/`: `pipeline init . --private` scaffolds nothing new and just adds the
exclude. It does not un-commit anything already in history -- for that,
`git rm -r --cached .project` once, then commit.

A team that *all* runs the pipeline and still wants tickets out of history
wants the tracked file instead -- one line in `.gitignore`. That is a shared
decision, so it is deliberately not automated by a flag.

The trade-off is the decisions, not the tickets: excluded, they are local to
your machine, so two people running the pipeline on one repo would each build a
private decision set and re-argue each other's conclusions.

## The daemon

`pipelined` is **one process for many projects**, not one per project. It keeps
working after you close the terminal, and it records what happened to an event
database under your state directory (see *Where it keeps things*).

```sh
pipeline register ~/code/myproject   # one path per line in the registry file
pipeline start                       # spawns pipelined, detached; interactive stages need `pipeline tui` attached
pipeline status                      # is it running, and how many projects
pipeline ls                          # every registered project's tickets
pipeline ls --project ~/code/myproject     # --project is a FILTER here
pipeline stop
pipeline unregister ~/code/myproject
```

`pipelined` itself stays a raw foreground process, so `systemd --user`, `launchd`
or tmux can supervise it; `pipeline start` is just a convenience wrapper. There is
no pidfile: the daemon socket is the liveness check and `ping` returns the pid.

### Where it keeps things

Nothing here is a hardcoded path. Each one reads the matching XDG variable if
your session sets it and falls back to a plain `$HOME` path if it does not, so
this works the same on a systemd desktop, a bare login shell and macOS.

| What | Set by | Unset (the fallback) |
|---|---|---|
| registry | `$XDG_CONFIG_HOME/pipeline/projects` | `~/.config/pipeline/projects` |
| event log | `$XDG_STATE_HOME/pipeline/events.db` | `~/.local/state/pipeline/events.db` |
| daemon socket | `$XDG_RUNTIME_DIR/pipeline/daemon.sock` | `/tmp/pipeline-$UID/daemon.sock`, created `0700` and checked to be yours |

`$XDG_RUNTIME_DIR` is the one that is usually **absent** outside systemd -- macOS
never sets it -- which is why the socket has a real fallback rather than an error.
`--socket` and `--db` override the last two; the registry follows
`$XDG_CONFIG_HOME`. AF_UNIX caps a socket path at 104 bytes on macOS and the BSDs
and 108 on Linux, so `pipeline` checks the shorter limit and says so instead of
letting `bind()` fail with an unexplained `OSError`.

**The daemon is an accelerator, never a dependency.** `pipeline run --project X`
is the same supervisor minus the socket, and every client command falls back to
reading the ticket files when nothing answers the socket. It runs every stage,
including the interactive ones -- headless, since nothing can attach to a
supervisor with no socket (see *Interactive stages*). Ticket files stay the
source of truth; the database holds the event log only, so `rm events.db` loses
history and nothing else.

Two supervisors on one project would double-spawn, so each holds an
`fcntl.flock` on `<project>/.project/.lock` while it watches it, and the daemon
itself holds one on `daemon.sock.lock`. The kernel releases both on crash. A
daemon restart also treats a lease whose holder pid is gone as expired, instead
of parking the ticket for the full 30 minutes.

The socket is `0600` in a `0700` directory and the event database is `0600`, but
the boundary is the uid and nothing more: anything running as you can `ls`,
`subscribe` and `kill`. It is not a privilege boundary and nothing should treat
it as one.

The protocol, the schema and the event-kind vocabulary are frozen in
`.project/decisions/DEC-011.md`.

## Interactive stages

A stage whose frontmatter says `mode: interactive` is spawned on a real PTY the
daemon owns, using the harness's `interactive_cmd` template. `planning` is the
one that does today.

This is not a nicer view of a headless stage. Under `-p` the harness *ignores*
`--permission-mode` and `AskUserQuestion` is not in the toolset, so a permission
prompt and an option picker simply do not exist there. A PTY is the only mode in
which a human can steer a stage.

`mode: interactive` means "interactive while a human is attached". `pipeline
run` has no socket, and `pipeline start` with no client subscribed is the same
case: both run the stage **headless** instead, and say so on stdout. A TUI
that attaches after the spawn gets a headless stage. Nothing is lost but the
steering: `planning`'s own escape hatch is `result: needs-input`, which parks
the ticket at a human gate for `pipeline answer`. `pipeline start --help` and
`pipeline run --help` each say
which side they are on, and `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes`
fails if either stops saying it.

An interactive session also ends on its `.result` sidecar, not on `/exit`: a
REPL does not exit when the agent reports a verdict, so the supervisor sends it
SIGTERM once the sidecar lands and reaps it like any other child.

```
-> {"id":7,"op":"attach","ticket":"TICKET-003"}      # "project" optional, a filter
<- {"id":7,"ok":true,"data":{"screen":[...40 lines...],"writer":true,"rows":40,"cols":120}}
<- {"sub":7,"pty":"<base64 chunk>"}                  # live, until you detach
-> {"id":8,"op":"input","data":"<base64 keystrokes>"}
-> {"id":9,"op":"resize","rows":50,"cols":160}
-> {"id":10,"op":"detach"}
```

`screen` is the *current* 40 lines, not a replay -- that is the whole reason
`pyte` is a dependency. The full raw stream is in the stage log, so
`cat .project/logs/<id>-<stage>-<session>.log` covers scrollback.

**Detach never kills the session**, and neither does closing the socket: the
daemon holds the master fd, so a client is only ever a subscriber. Any number
may watch; the first to attach holds the writer, others get `writer:false` and
their `input` is refused until the holder detaches or disconnects.

An interactive stage does **not** survive a daemon restart -- the master fd dies
with the daemon and the child gets SIGHUP. The lease expiry recovers the ticket
like any other crash.

## The TUI

```sh
pipeline tui                              # every registered project
pipeline --project ~/code/myproject tui   # the same filter `ls` takes
```

Left pane a tree of projects and their tickets (`*` running, `!` waiting on
you, `~` running unknown -- no daemon answered, `?` untouched for hours),
right pane the ticket's stage log rendered the way `pipeline logs` renders it,
then live events as they arrive. It seeds from `ls` and stays current from a
`subscribe` on its own connection; with no daemon running it reads the ticket
files instead and simply does not update itself. A ticket file cannot say
whether a stage is running, so those rows report `running`/`mode` as unknown
rather than idle, and the pane keeps the last answer the daemon gave for
them; `pipeline ls` prints `-- no daemon: running/mode unknown for these
rows` once above such a listing.

Select a ticket running an **interactive** stage and the right pane becomes
that stage's live terminal instead: it `attach`es on the subscription's
connection, seeds from the daemon's `screen` snapshot and paints the `pty`
frames after it. A `dropped` marker means the daemon binned part of the
backlog, so it re-attaches for a fresh snapshot rather than paint across the
gap. `i` types a line into it -- chunked at 4096 bytes an op, with a short
write's remainder re-sent, so a long answer cannot be half-swallowed.

`a` approve, `r` reject, `A` answer, `e` edit, `l` logs, `m` metrics, `k` kill,
`i` type, `f` finished, `q` quit. Only `k` and `i` are daemon ops -- approve, reject and answer rewrite the
ticket file, which is the source of truth, and the daemon's next tick notices;
`e`/`l`/`m` suspend the app and hand you the real terminal. `e` interrupts the
running stage before opening `$EDITOR`, so your edit cannot trip the
dispatcher's tamper detection.

The tree hides `done` and `rejected` tickets and opens the cursor on the first
ticket that is not terminal; `f` brings the hidden ones back, and `escalated`
is never hidden.

## Concurrency

    pipeline --project ~/code/myproject run -j 4

Each ticket gets its own git worktree under `.worktrees/<ID>`, created from
`base` and removed when the ticket reaches a terminal stage. Two tickets cannot
share one checkout, which is why worktrees and parallelism arrive together.

Ticket files stay in the **main** checkout, not the worktree. They are the queue,
and keeping them in one place is also what stops parallel agents from producing
merge conflicts on their own ticket threads.

`done` means landed. Once the suite passes, a diff that touches nothing
`CLAUDE.md` fences off from unattended merge reaches `merging` on its own; one
that does parks first at `awaiting-merge`, a human gate, and `approve` sends
it on. `merging` merges `base` into the ticket's own worktree and then
fast-forwards the **main** checkout onto the ticket branch. Fast-forward only,
and only while the main checkout is actually on `base`, so a dirty, diverged
or elsewhere-parked checkout escalates instead of landing half of it -- and a
conflict escalates with the conflicted worktree left in place for you to open.

Approval does not mean "start typing". A ticket can sit at the human gate for
days while other tickets land on base, so the Tier A facts behind its plan --
suite green, the new test the only red -- describe a tree that no longer exists.
`approve` at `awaiting-approval` therefore hands the ticket to `revalidating`, which rebases the branch
onto current `base` and re-runs the gate before any implementation. A gate that
now fails bounces back to `planning` against its own counter (`stale_regate`),
never `plan_validation_attempts`: the plan was fine, the world moved -- and
re-validating the same stale plan would rerun the identical gate and fail
identically, so re-planning is the only thing that can fix it. A rebase
conflict aborts the rebase, recuts the branch from base against its own
counter (`rebase_conflicts`), and hands the ticket back to `triage`, which
rewrites its test on current base; nothing is auto-resolved, and a second
conflict escalates.

Two tickets whose `files_declared` intersect never run at the same time -- the
second one waits rather than failing. That ordering is silent, so `ls` flags
anything sitting still for more than `STALE_HOURS`.

Per-project worktree setup (shared build cache, `.env`, dependency install) is
one config line, so it is never improvised by an agent:

```toml
worktree_setup = "ln -s ~/.cache/cargo-target target && cp ../../.env ."
```

## Watching a run

Every spawn gets a session id and a log:

```
$ pipeline --project ~/code/myproject ls -v
TICKET-001   review    bugfix  {'review_loops': 1, ...}
             last: review log=.project/logs/TICKET-001-review-3582ef02.log
                   replay=`claude --resume 3582ef02-...`
```

`tail -f` the log while it runs, or `pipeline logs <id> -f` to pretty-print it;
`claude --resume <id>` to open the session and see what the agent actually did.
Under the daemon the child's stdout comes back over a pipe, but it is *teed* to
the same log file -- otherwise both of those stop working.

## When a ticket escalates

`escalated` means a bounded loop hit its bound, or the dispatcher saw a thing it
refuses to guess about. Nothing retries it and no stage can un-escalate it: a
human decides.

```
$ pipeline ls
TICKET-017   escalated   bugfix   {'review_loops': 0, ..., 'no_result': 2}
```

The reason is the last entry in the ticket's thread, written by the dispatcher
itself:

```
### 2026-08-21 04:36:36Z · plan-validation · escalation

`plan-validation` wrote no .result sidecar 2 times
```

So: `tail -n 30 .project/tickets/TICKET-017.md` for the reason and the stage
that hit it, `pipeline logs TICKET-017` for that stage's log. The worktree is
still there -- `escalated` is not in `CLEANUP_STAGES`, so whatever failed is
left where it happened, `git -C .worktrees/TICKET-017 status` and all.

Then one of three:

| The reason is | Do |
|---|---|
| a flake -- crashed harness, expired lease, no sidecar | `pipeline resume TICKET-017 --stage plan-validation --reset no_result` |
| real, but the stage deserves another go with the thread it has now | `pipeline resume TICKET-017 --stage planning --grant plan_validation_attempts` |
| the ticket itself is wrong | `pipeline reject TICKET-017 "why"` |

`--reset` zeroes a counter; `--grant` hands back one spent attempt (`N` with
`--grant counter=N`) and cannot return more than was spent. Naming the same
counter in both is an error, not a merge.

The bound that was hit lives in the dispatcher, never in a stage prompt:
`BOUNDS[class][counter]` in `pipeline/core/machine.py`, which is 2 for `bugfix`
and `feature` and 3 for `refactor` on `review_loops` and
`plan_validation_attempts`. `plan_validation_attempts` is the only one that
grows with the plan -- one more attempt per 8 steps or 4 declared files, never
past 5. `lease_expiries` and `no_result` are the dispatcher's own counters and
stay at 2 whatever the class.

Resetting a counter because the loop is tiresome is how an unbounded loop gets
back in. A stage that escalates twice for the same reason is telling you the
ticket is wrong, not that the budget is small.

## The invariants

0. **No agent waits on another agent.** The dispatcher launches and returns;
   `reap()` collects finished processes on the next tick. A stage that hangs
   burns its own lease and nothing else.
1. **An agent never writes `stage` — enforced, not requested.** It writes
   `.project/tickets/<ID>.result` with `result: ok|chore|fail|blocked|rejected`;
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
4. **The regression suite, the re-gate and the merge are run by the dispatcher.**
   `verifying`, `revalidating`, `unwinding` and `merging` have no agent at all --
   a test result should never pass through a model's mouth, and neither a rebase
   nor a merge conflict is ever auto-resolved: both escalate and keep the
   conflicted worktree as the evidence. Putting a promoted cheap-route branch
   back where `triage` left it is a `git reset --hard` no prompt should be
   trusted to aim.

## Layout

    pyproject.toml               `pipeline` + `pipelined` entry points
    pipeline/core/machine.py     the transition table. Pure, no I/O.
    pipeline/core/ticket.py      ticket files: load, validate, save, thread
    pipeline/core/config.py      stage/harness/project config and prompt assembly
    pipeline/core/gate.py        the Tier A gate
    pipeline/core/worktree.py    per-ticket checkouts and project commands
    pipeline/daemon/supervisor.py  the dispatcher loop
    pipeline/daemon/server.py    the select loop: watch(fd, cb)/unwatch(fd), AF_UNIX, NDJSON
    pipeline/daemon/store.py     the append-only SQLite event log
    pipeline/daemon/registry.py  the project list and the per-project flock
    pipeline/pty/host.py         a stage on a real PTY: pty.fork, a Popen shim,
                                 a pyte screen, and the clients watching it
    pipeline/cli/main.py         the human-facing commands
    pipeline/cli/client.py       the socket client, and its file-based fallback
    pipeline/stages/_common.md   rules every stage shares, incl. the failure protocol
    pipeline/stages/*.md         one self-contained stage: frontmatter (model,
                                 effort, write) plus the prompt. Harness-neutral.
    pipeline/harnesses/*.toml    how to spawn an agent. A new harness is a new file.
    pipeline/templates/          the ticket schema, the project config example, and the file-ticket skill
    tests/                       one file per module

Adding a stage means adding `pipeline/stages/<name>.md` and a row in
`transition()`. Nothing else knows the list.

The stages, hooks, harnesses and templates live inside the package because they
are located from `__file__` -- at the repo root they would not survive
`uv tool install .`.

Tickets live in the **target** project (`.project/tickets/`), not here, so they
branch, diff, and revert with the code they describe.

## Per-project stage config

`pipeline/stages/<name>.md` is packaged, so every registered project reads
the same stage files by default. A project can override one in two ways:

- **Settings**, in `.project/pipeline.toml`, under `[stages.<name>]` --
  `model`, `effort`, `write`, `tools`, `hooks`, `permission_mode`, `skills`,
  `max_usd`, anything the packaged frontmatter carries. This table is merged
  **shallow** onto the packaged frontmatter: a key you set replaces the
  packaged one outright, it does not extend it -- a `skills` list you give
  replaces the packaged list, not appends to it.
- **Prose**, in `.project/stages/<name>.extra.md` -- free text appended after
  the packaged prompt and before the ticket view. It can only add
  instructions, never remove or relax one: there is no frontmatter in an
  `.extra.md` file, so there is nothing to clamp there either.

Both are read the same way the rest of a project's config is: the settings
table comes from `.project/pipeline.toml` at `HEAD`, so an uncommitted edit
is inert and a committed one lands in the ticket's diff, where
`.project/pipeline.toml` being fenced parks it at `awaiting-merge` for a
human to read before it merges. `.project/stages/` is fenced the same way,
so a committed `.extra.md` change parks there too.

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
    ./pipeline/hooks/test_dangerous_commands.py   # the same cases, one line each

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

## MCP servers

A project declares one in `[mcp.<name>]` in `.project/pipeline.toml`:

```toml
[mcp.docs]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]
readonly = true
```

A stage opts in with `mcp: [docs]` in its frontmatter -- a server nobody
declares is never spawned and costs no tokens. `readonly = true` is what lets
a `write: false` stage call it at all; a server declared without it is
unusable from a read-only stage. The guard's `PreToolUse` matcher covers
`mcp__.*`, and `dangerous-commands.py` allows a call only for a server the
stage declared, default deny. `--strict-mcp-config` still excludes every
server the project did not name, so a stage never inherits the operator's
`~/.claude` servers.

## Not built yet

- **A second harness that actually runs.** `codex.toml` is asserted, not
  executed -- every stage declares `hooks:`, and it cannot register one.

## Licence

MIT -- see `LICENSE`. Three stage prompts embed text derived from the
MIT-licensed `superpowers` skills; `NOTICE` carries that attribution and has to
travel with the code.
