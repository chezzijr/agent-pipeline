# Ticket-driven agent pipeline

Agents do not talk to each other. They talk through a ticket file, one stage at
a time, each in a fresh stateless process. A dumb dispatcher owns the state
machine; no model ever decides what happens next.

    triage -> planning -> plan-validation -> [human] -> implementing
                                                            |
                                    done <- verifying <- review

## Why

- **Less context per stage** -- less hallucination, and a stage that dies is
  respawned from the ticket rather than resumed from a transcript.
- **Enforceable gates** -- the mechanical checks are a script, so they cannot be
  talked out of. The agent supplies judgment; the dispatcher supplies promises.
- **Bounded loops** -- every retry is counted, and the second failure of any
  loop escalates to a human instead of ping-ponging.

## Use

```sh
./pipeline.py init ~/code/myproject           # scaffold .project/
$EDITOR ~/code/myproject/.project/pipeline.toml   # how to run this project's tests
./pipeline.py --project ~/code/myproject new "cache leaks on evict"
./pipeline.py --project ~/code/myproject run      # dispatcher loop

./pipeline.py --project ~/code/myproject status
./pipeline.py --project ~/code/myproject approve TICKET-001
./pipeline.py --project ~/code/myproject resume  TICKET-001 \
    --stage planning --reset plan_validation_attempts
```

`run --once` does a single pass, which is what you want while you are still
watching it.

## Watching a run

Every spawn gets a session id and a log:

```
$ pipeline.py --project ~/code/myproject status -v
TICKET-001   review    bugfix  {'review_loops': 1, ...}
             last: review log=.project/logs/TICKET-001-review-3582ef02.log
                   replay=`claude --resume 3582ef02-...`
```

`tail -f` the log while it runs; `claude --resume <id>` to open the session and
see what the agent actually did. There is no daemon manager here on purpose --
run the loop under systemd or tmux, which already solve supervision.

## The three invariants

1. **An agent never writes `stage`.** It writes `.project/tickets/<ID>.result`
   with `result: ok|fail|blocked|rejected`; `transition()` maps that to the next
   stage. An agent cannot skip a gate or escape a bound because it has no way to
   name one. An unrecognised result escalates rather than guessing.
2. **Read-only stages are checked, not trusted.** The dispatcher snapshots the
   tree before a review stage and escalates if it changed. This catches an edit
   made through Bash, which a tool allowlist does not.
3. **The regression suite is run by the dispatcher.** `verifying` has no agent
   at all -- a test result should never pass through a model's mouth.

## Layout

    pipeline.py         dispatcher, gate, CLI
    stages/_common.md   rules every stage shares, incl. the failure protocol
    stages/*.md         one self-contained stage: frontmatter (model, effort,
                        write) plus the prompt. Harness-neutral.
    harnesses/*.toml    how to spawn an agent. A new harness is a new file here.
    ticket-template.md  the ticket schema

Adding a stage means adding `stages/<name>.md` and a row in `transition()`.
Nothing else knows the list.

Tickets live in the **target** project (`.project/tickets/`), not here, so they
branch, diff, and revert with the code they describe.

## Porting to another harness

Everything except `harnesses/claude-code.toml` is plain files and Python. A new
harness needs a `cmd` template that can (a) take a system prompt, (b) run in a
directory, and (c) write a file. Do not write one speculatively -- run real
tickets on one harness first; the second harness is what shows where the seam
actually belongs.

## Tests

    ./test_pipeline.py

Covers the transition table's bounds, gate rejections, and the two traps found
while building it: the dispatcher's own venv shadowing the project's, and a test
that *errors* (missing dependency) being indistinguishable from one that fails.

## Not built yet

Worktrees and parallelism, file-overlap detection between in-flight tickets,
per-class bounds, model tiering. Single-ticket flow first. Watch the escalation
rate per stage -- the frontmatter counters give it to you for free.
