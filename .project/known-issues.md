# Known issues — candidates for tickets

Everything here was found by the adversarial review, the conformance audit against
`~/.claude/plans/2026-08-20-pipeline-app-design.md` and `skydeckai-conversation-316269.md`,
or by running the app. Nothing here is speculative; each entry says how it was found and
what evidence exists.

**Already filed:** TICKET-017 (Tier A runs the failing test on the branch, not base),
TICKET-018 (`## Digest` / `## Decisions checked` are non-emptiness checks only).

Use the `file-ticket` skill. One ticket per entry — `files_conflict` orders tickets by the
files they touch, so a ticket spanning two areas blocks both.

---

## THE FIRST REAL RUN — three blockers, FIXED 2026-08-21

The daemon ran real `claude` agents against TICKET-016/017/018 for the first time and hit
three things, kept here as the record of what they were and what settled them. All three
are fixed in `a1e084c` + the branch merge; the section below is history, not a backlog.

### B1. Every non-read shell command was denied — nothing could pass triage  ★ was FATAL

`render()` passed `permission_mode = "acceptEdits"`, which auto-accepts *file edits* and
nothing else, so every Bash command fell through to an interactive approval prompt that
`-p` has nobody to answer:

```
→ Bash({"command": "uv run test_pipeline.py"})
← ERR This command requires approval
```

Triage's whole job is to write a failing test **and run it**, so every ticket escalated
there and the pipeline could not complete one.

**Settled by experiment before the fix was written**, because the open question was
whether the guard survives the fix. Two one-shot `claude -p --permission-mode
bypassPermissions --settings <the stage_settings() shape>` runs:

| probe | result |
|---|---|
| `sudo -n ls /` under `PIPELINE_READONLY=1` | `Blocked by the pipeline guard (triage): sudo: agents do not get root.` |
| `touch probe.txt && ls -l probe.txt` | ran, no approval error, file created |

So a `PreToolUse` hook **does** fire under `bypassPermissions`, and `--permission-mode`
**is** honoured under `-p` (the old comment in `claude-code.toml` said it was ignored —
corrected in the same commit). The guard stays the perimeter, which is what invariant 4
asks for; the settings-file allowlist route was not needed and was not taken.

Fix: `permission_mode = "bypassPermissions"` in `claude-code.toml`, and `render()` reads
stage frontmatter → the harness's default for *this template* → `acceptEdits`, so a
harness that declares nothing is unchanged.

**Headless only.** The first run after the fix cleared triage and then parked `planning`
(`mode: interactive`, on the PTY) at Claude Code's terminal modal:

```
running in Bypass Permissions mode.
❯ 1. No, exit
  2. Yes, I accept
```

A stage sitting on that dialog is a stage nobody is steering. `interactive_cmd` exists
precisely because an attended stage *can* answer a prompt, so it takes the opposite
default: `interactive_permission_mode = "acceptEdits"`. Consequence worth knowing before
starting an unattended run: an interactive `planning` still waits for a human on its first
Bash command — attach with `pipeline tui`, or use `pipeline run` (no socket, nothing can
attach, so `planning` runs headless with the guard as its only gate).

### B2. `base = "main"` while the app lived on `pipeline-app` — agents worked on dead code

Worktrees were cut from the pre-refactor single-file tree, so TICKET-017/018 — which name
`pipeline/core/gate.py` — were handed `pipeline.py`.

Fix: `main` was fast-forwarded to `pipeline-app` (`63e18fe..a1e084c`, 57 commits, clean
FF), so `base = "main"` is now correct as written. The stale `ticket/016` and `ticket/017`
worktrees and branches were removed so the next run re-cuts them from the new base; their
uncommitted work was one unrun test each against `test_pipeline.py`, which no longer
exists. The three tickets were reopened with `pipeline resume ... --stage triage`.

### B3. Stage prompts told agents to invoke a tool they were not given

```
→ Skill({"command": "superpowers:systematic-debugging"})
← ERR Error: No such tool available: Skill. Skill is disabled for this session.
```

`compose_prompt()` appended the `skills:` block unconditionally while `Skill` never
reached `--tools`.

Fix (the option that resolves the harness-neutrality tension rather than entrenching it):
`claude-code.toml` declares `skill_tool = "Skill"`; `_tools()` grants it exactly when the
stage declares `skills:` **and** the harness can supply it; `compose_prompt(stage, hcfg)`
emits the block only in that same case. `codex.toml` and `fake.toml` declare no
`skill_tool`, so they now say nothing rather than lie. Tested both directions —
`tests/test_stages.py::test_declared_skills_reach_the_prompt_only_when_the_harness_grants_the_tool`.

### B4. A read-only stage could not write its `.result` at all — FIXED

Found on the run that followed: `plan-validation` produced a complete analysis for
TICKET-016 and TICKET-017, twice each, and escalated both with `no_result: 2`.

```
tools given:  Read,Grep,Glob,Bash                          # write: false
guard says:   Blocked by the pipeline guard (plan-validation): shell redirection into a file.
              Blocked ... : command does not parse as a shell command      (heredoc)
              Blocked ... : sed -n: not an allowed subcommand
verdict:      `plan-validation` wrote no .result sidecar 2 times
```

No `Write`, no `Edit`, and the guard correctly refuses `>` — so the one action every
stage must perform was the one it could not. It hit every read-only stage:
`plan-validation`, `review`, `holistic-review`.

The guard was not wrong; the tools list was. `write: false` names the **working tree**,
which is why `tree_snapshot()` excludes `.project/`: "writing to the ticket and the
.result sidecar is every stage's job, including the read-only ones."

Fix: `readonly_tools = "Read,Grep,Glob,Bash,Write,Edit"`. Prevention stays with the
guard for the shell; a file tool used outside `.project/` is caught by the snapshot at
reap and escalates as `wrote-in-readonly`. Regression test asserts every stage's
rendered toolset contains a file tool — `tests/test_harness.py::
test_every_stage_can_write_its_result_sidecar`.

### B5. A colon in a stage's summary destroyed its verdict — FIXED

TICKET-021 escalated twice in ten minutes with a correct `result: ok`, a committed
failing test, a written plan, and an empty reason in the thread. The sidecar it wrote:

```
result: ok
summary: reproduced; fails with "raw mode never reached the pty: b'\r'"
```

```
$ yaml.safe_load(sidecar)
ScannerError: mapping values are not allowed here
```

`read_result` caught `YAMLError`, set `data = {}`, and unlinked the file — so the
verdict read as `fail` and the evidence was deleted in the same breath. A stage's job
is to report what it saw, and what it saw is error text; error text has colons in it.

Fix: `loose_result()` — on a YAML failure, a line-based parse of `result`, `summary`,
`test_file` and the `files_declared` list. Nothing is trusted differently:
`apply_claims()` and `validate_meta()` check every value exactly as on the YAML path,
which is what makes a looser parser a fallback rather than a second front door.
Regression test feeds it that exact summary —
`tests/test_ticket.py::test_a_colon_in_the_summary_does_not_destroy_the_verdict`.

### What did work, and still does

The daemon supervised a real multi-ticket run; `--add-dir`'s `--` fix means stages spawn
and receive their prompt; stream-json parsing rendered live in the TUI; hook events showed
up as `[hook SessionStart:startup exit=0 success]`; the ticket thread recorded typed
entries throughout; and TICKET-016 escalated **with an accurate diagnosis of its own
failure**, which is the bounded-loop-plus-honest-reporting behaviour working as designed.

---

## 1. No log retention — the only thing here with a real growth curve

`.project/logs/` is gitignored, so it never bloats git, but nothing ever prunes it.
Measured on one ticket that ran four stages: **12 KB of logs against a 3.7 KB ticket**, so
logs grow ~3x faster than the thing they describe, forever. With stream-json every
assistant message is also written there.

`grep -rn "rmtree|prune|archive|retention" pipeline/*.py` returns nothing outside worktree
cleanup. `events.db` is deliberately append-only with `rm events.db` as the supported
reset, and that is fine. Logs have no equivalent story.

Expected: a retention policy the dispatcher applies — age or total size — and a decision
recorded about whether a landed ticket's logs are evidence worth keeping.

## 2. `init` does not register, and `new` does not warn

Reproduced end to end:

```
$ pipeline init          # scaffolds .project/
$ pipeline projects      # ...registered nowhere
$ pipeline new "some bug"
/tmp/autoreg/.project/tickets/TICKET-001.md
$ pipeline ls
TICKET-001   new   bugfix   {...}      # sits here forever, nothing watches it
```

Three commands, no warning, and `ls` shows a ticket no daemon will ever pick up.

Expected: `init` registers the project and says so (it already means "set this project up
for the pipeline"), with `--no-register` for CI; `new` warns when the project is not
registered. Read-only commands (`ls`, `status`, `logs`, `metrics`) must stay pure — do
**not** auto-register on any command, because registering enlists a directory into a
background process that spawns agents and writes code, and a side effect that depends on
`cd` is the kind that bites.

## 3. `sections()` splits on a `## ` line inside a fenced code block

Already filed as TICKET-016, listed here because it is easy to underestimate: the gate and
`verifying` embed up to 1500 chars of raw test output in ``` fences, so a diff hunk of a
markdown file inside one splits the entry and truncates `Ticket.thread()`. That silently
disables the typed-thread feature TICKET-010 exists to provide.

## 4. Three transition guards from the spec are not enforced at the transition

The design conversation's table gives every row a dispatcher-enforced guard. Three are
missing (conformance audit section A):

| transition | guard the spec demands |
|---|---|
| `triage -> planning` | failing test exists on the branch |
| `triage -> rejected` | repro attempt log appended |
| `implementing -> review` | the new test passes |

Each is caught later — by the Tier A gate or the scripted suite — so nothing escapes
today. But the guard-per-row property is what makes the table a contract rather than a
diagram, and "caught later" means caught after a wasted stage.

## 5. `pipelined --db` and the CLI's `Store()` can write to different databases

Found by the integration pass. `pipelined` takes `--db`; `cmd_approve`/`reject`/`answer`
open the default path directly. Point the daemon at a non-default DB and a ticket's parked
span is split across two event logs, so metrics view 6 measures nothing useful.

Needs a decision, not wiring: either the CLI learns the daemon's DB, or `--db` goes.

## 6. `DEC-011.md` no longer describes what emits `stage_end`

The frozen contract says `stage_end` is emitted by `finish()`. Since the review fixes,
`start()` emits one too, for an attempt that ends before a child exists. If that table is
meant to be exhaustive it needs a one-line update or a superseding record — and TICKET-008
built the superseding mechanism, so this is a chance to use it.

## 7. `metrics.PRICE_PER_MTOK` silently defaults unknown models to sonnet-tier

It is now load-bearing for every interactive stage, since PTY cost is tokens x price (no
cost field exists in transcripts — verified across 40 files, ~14.5k assistant lines). An
unknown model id gets a sonnet-tier guess with no marker, so a wrong number renders
identically to a right one. Estimates already render with `~`; an unknown model deserves
its own marker, or a loud one.

## 8. `tail_log()` renders a finished interactive stage's ANSI log as junk

`cmd_logs` detects the case; `tail_log()` does not. A PTY stage's `.raw` log is terminal
escape sequences, not text.

## 9. `cmd_resume` accepts any known stage, including a terminal one

Confirmed by the adversarial review (B7). `pipeline resume <id> --stage triage` on an
escalated ticket lets it reach a terminal stage a second time, so `metrics.py`'s "a ticket
has at most one terminal row" guarantee fails and the ticket is double-counted.

## 10. `PTY_BACKLOG` is checked against the wrong queue

Confirmed (B6), low. Documented as "queued pty frames per client" but measures `conn.out`,
the shared outbox that also holds subscription event frames. No shipped client sends
`since`, so it is protocol-only today — file it before a client does.

## 11. Two `worktree.py` weaknesses the Tier A gate depends on

Raised by TICKET-004's review, out of scope there because they live in another file:

- `run_cmd` keeps only the last 4000 chars of output, so a real `expect:` match can fall
  outside the retained tail on a verbose suite. The same weakness applies to the existing
  `node not in out` check.
- `project_env()` does not pin `PYTHONHASHSEED`, so a hash-order-dependent repr (a set in
  an assertion) can differ between triage's run and the gate's rerun of the same test.

## 12. Orphaned agents after a SIGKILLed daemon

Marked with a `ponytail:` comment, not solved. A SIGKILLed daemon leaves `claude` children
that can still write `.result`. The respawn uses a new session id and `drop_result()` runs
pre-spawn, so the worst case today is a stale thread summary. The named upgrade is
recording child pids and reaping them on startup.

## 13. An interactive stage does not survive a daemon restart

Deferred deliberately in TICKET-013, with a `ponytail:` comment naming the upgrade path
(an abduco/dtach-style per-session helper). The master fd dies with the daemon and the
child gets SIGHUP; lease expiry recovers the ticket. Worth a ticket only if restarts
during planning turn out to be common.

## 14. `gate()` runs the project's test command synchronously inside the select loop

Marked with a `ponytail:` comment by TICKET-011. The loop is now the only pipe reader, so
a slow `test_one` stalls every other project's children. Mitigated (1 MiB pipes,
`drain_all()` before every blocking call) but not removed. The real fix is running the
Tier A gate as a spawned child like `verifying` — the mechanism already exists
(`spawn_command`).

---

## Not bugs — deliberate, recorded here so nobody "fixes" them

- **`blocked` is not a stage.** The spec's two `blocked` rows collapse into
  `implementing -> plan-validation` charging `blocked_count`. Nothing references a
  `blocked` stage.
- **A stale re-gate returns to `planning`, not `plan-validation`.** The ticket said
  `plan-validation`; that reran the identical gate a tick later and charged
  `plan_validation_attempts`, the exact cost the row exists to avoid. `machine.py:71`
  carries the reasoning.
- **`plan_rejections` is not in `BOUNDS`.** `transition()` never charges it; the CLI does.
  A `BOUNDS` key `charge()` never reads would falsely imply dispatcher enforcement.
- **`mode: interactive` falls back to headless when nothing can attach.** `planning` is on
  every ticket's happy path, so refusing it without a daemon would delete the `pipeline
  run` escape hatch rather than keep it honest.
- **`save(validate=False)` has exactly one caller, `escalate()`.** A ticket whose
  frontmatter *is* what is wrong cannot be quarantined by a validating save.

---

## The big one: no real agent has ever completed a stage

The `claude-code` harness ended with `--add-dir {project} "<prompt>"`, and `--add-dir` is
variadic — it ate the prompt:

```
$ claude -p --add-dir /tmp "say hi in three words"
Error: Input must be provided either through stdin or as a prompt argument
$ claude -p --add-dir /tmp -- "say hi in three words"
Hi. Ready. Go.
```

All 21 dogfood triage logs died there. Fixed (`e01947d`) with a regression test, but
**unexercised**: the end-to-end tests use `fake.toml`, whose command has no positional
argument, so the one harness that talks to a real agent was the one never exercised.

Consequences: the design's falsifiable predictions 2, 3 and 4 have no data, and the first
real ticket is also the first real test of the harness. Run it with `pipeline run --once`
in the foreground before trusting the daemon with it.
