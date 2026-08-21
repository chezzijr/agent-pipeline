---
id: TICKET-027
stage: escalated
class: refactor
branch: ticket/027
test_file: tests/test_stages.py::test_plan_validation_is_not_an_opus_stage
files_declared:
- pipeline/stages/plan-validation.md
- tests/test_stages.py
counters:
  plan_validation_attempts: 3
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: plan-validation
  id: 2a693866-5f7c-48b1-9b83-4ba50d839c04
  log: .project/logs/TICKET-027-plan-validation-2a693866.log
---

## Summary

`plan-validation` runs on opus to score a plan against a checklist

`pipeline/stages/plan-validation.md` declares `model: opus`, `effort: high`. It
cost **$37.90** across 18 runs this session -- 24% of the session's $160.66, the
second-largest line after `planning`.

Its job is to compare a written plan against eight fixed items and report which
fail. The two catches that earned its keep today were arithmetic and staleness,
not design judgment:

    TICKET-021: "14 tests vs 12 ... criterion 6's '13 passed' fails on a
                 correct implementation (post-merge count is 16)"
    TICKET-024: "criterion 7 is vacuous -- its grep returns 7 today, so
                 step 10 can be skipped"

Both look reachable by a cheaper model. Neither is proven to be.

Expected: the stage runs on the cheapest model that returns the same verdicts,
and the evidence for that choice sits in the ticket rather than in an opinion.

The experiment costs almost nothing and needs no live ticket, because every
plan this session is already on disk with its verdict:

1. Take the plans from TICKET-016 through TICKET-025 and the verdict each one
   received.
2. Re-run `plan-validation` over each plan on sonnet.
3. Compare verdict for verdict. A cheaper model that passes a plan opus
   rejected is a **regression**, not a saving -- 024's vacuous criterion would
   have reached implementing.

Change the frontmatter only if the verdicts match. If they diverge on even one
plan, record which one and leave the model alone: this is the stage that stops
a bad plan before anyone pays for the code, and one missed catch costs a review
loop ($2.15) plus an implementing re-run ($1.86).

Note for whoever plans this: the same question applies to `review` and would be
tempting to bundle. Do not. `review` is the stage that caught three vacuous
tests today, and it needs its own evidence.

**Triage (2026-08-21):** reproduced. `model: opus` confirmed in the frontmatter;
a failing test is committed on `ticket/027` (see `## Reproduction`). sonnet is
the only other model in use. Triage did not run the verdict comparison -- that
is planning's job, and the test does not cover it.

**Planning (2026-08-21):** the experiment is specified and costed, not run.
Planning had $1.75 of its $5 cap left after the research, and ten sonnet replays
cost about $5, so running them here would have crashed the stage. `implementing`
has `max_usd: 8` and runs them as steps 1--11.

Three things the research settled, all detailed in `## Digest`:

1. The baseline is **ten** agent verdicts, one per ticket -- eight `ok`, two
   `fail` (021 and 024). TICKET-024's 08:27:16Z `verdict=FAIL` was the
   deterministic gate, not an agent, and is excluded.
2. Every run is replayable. The ticket text each run read survives in its log
   (inline for six, spilled to `~/.claude/projects/.../tool-results/` for four),
   every ticket branch and `main`'s reflog still resolve by timestamp, and the
   log's first line is the exact spawn command.
3. The replay must omit `--effort`. Every baseline run rendered `{effort_flag}`
   empty, so passing `--effort high` would change two variables at once.

The plan replays 021 and 024 first because a sonnet `ok` on either settles the
ticket for about $1.10. `effort: high` stays either way -- DEC-024 fixes it, and
this ticket measures the model axis only.

**Plan-validation (2026-08-21): rejected.** Six of eight items passed. Two
failed, both because the plan rebuilt the baseline spawn command by hand from a
log header that does not carry every input: `--settings` named a dead per-spawn
`tempfile` (so the replay would run `bypassPermissions` with no
`dangerous-commands` hook), and `PIPELINE_READONLY` is not in the command at
all. The riskiest step was priced as bounded by `implementing`'s `max_usd: 8`,
which does not bound a nested session; the real ceiling is 10 x $3 = $30.
Full per-item scoring is in `## Thread`.

**Planning, second pass (2026-08-21).** The experiment design is unchanged --
baseline table, replay 021 and 024 first, `/tmp` clone, verdict from the
`.result` sidecar. What changed is how a replay is built, and that fixes both
`FAIL` items at their root rather than patching two steps:

1. **Nothing is transcribed from the log header.** The baseline commit is
   checked out into `/tmp/pv-main` and `render()` is called from *that* copy of
   the package. `stage_settings()` writes a live settings file, `compose_prompt()`
   rebuilds the baseline system prompt, `{effort_flag}` renders empty on its own,
   and the positional wording is the baseline's. A header cannot go stale if
   nobody reads it.
2. **`PIPELINE_READONLY=1` is set per replay** (`supervisor.py:339`), so the
   agent gets the guard's allowlist as every baseline run did, not
   `implementing`'s blocklist.
3. **The $30 ceiling is stated and stopped.** `/tmp/pv-replay.py` appends each
   run's `total_cost_usd` to a ledger and refuses to start past **$12**. Step 10
   also stops on any `subtype` other than `"success"`.
4. **DEC-025 is disambiguated and complied with.** The replay renders from the
   baseline harness, which predates `--strict-mcp-config`, then adds the flag
   back. Evidence it cannot move a verdict: **zero `mcp__*` tool calls in all ten
   baseline logs**, against 52--77 tools offered at `init`.

Two things were run rather than assumed this pass: all twenty baseline shas
resolve (`git rev-parse "<ref>@{<run-start>}"`), and the ticket-text extractor
recovered all ten tickets verbatim, 21211--38349 bytes each. `## Decisions
checked` now also lists DEC-023.

Still true: `effort: high` stays either way -- DEC-024 fixes it, and this ticket
measures the model axis only.

**Plan-validation, second pass (2026-08-21): rejected.** The two items the first
pass failed now pass: rendering from the baseline package regenerates
`--settings` and the composed prompt, `PIPELINE_READONLY=1` is set explicitly,
and the $30 ceiling is stated with a $12 ledger stop. Six of eight items pass.
Two fail, both new:

1. **The replay is not isolated from the live repo.** Baseline runs read the
   real checkout by absolute path -- `ls /home/chezzijr/proj/claude-setup/.project/decisions/`
   in the 021 log, `cat /home/chezzijr/proj/claude-setup/.project/tickets/TICKET-024.md`
   and `head -25 /home/chezzijr/proj/claude-setup/.worktrees/TICKET-024/pipeline/...`
   in the 024 log. Those paths still resolve, but to today's state:
   `.project/decisions/` now holds fourteen records including DEC-026, DEC-028
   and DEC-030, `.worktrees/TICKET-024` is gone, and
   `.project/tickets/TICKET-024.md` line 793 is
   `### 2026-08-21 08:34:24Z · plan-validation · transition · to=planning · result=fail`
   -- the opus verdict the replay is supposed to produce. No step, gotcha or
   criterion covers this. It is a second uncontrolled variable, the same defect
   the plan rejects for `--effort`.
2. **Criteria 5, 8 and 9 read artefacts criterion 6 requires deleted.** Step 17
   deletes `/tmp/pv-logs`; criterion 5 checks session ids against "the run's log
   header", criterion 8 greps `/tmp/pv-logs/*.log`, criterion 9 sums the `cost`
   values in `/tmp/pv-logs/results.jsonl`. After step 17 none of the three can
   be falsified.

Full per-item scoring is in `## Thread`.

**Planning, third pass (2026-08-21).** The design is unchanged -- baseline
table, replay 021 and 024 first, verdict from the `.result` sidecar. What
changed is where the replay runs. `plan-validation` rejected the second pass
because the agent reads the live checkout by absolute path and would have read
today's state, including TICKET-024's own opus verdict. This pass removes the
live checkout from the replay's view instead of asking the agent not to look:

1. **The clone is bind-mounted over `/home/chezzijr/proj/claude-setup`** in an
   unprivileged user namespace, for the replay process tree only. Every
   absolute path a baseline run used resolves to the clone. Verified on this
   box: `os.unshare(CLONE_NEWUSER|CLONE_NEWNS)` plus an `MS_BIND` mount keeps
   uid 1000, and the real checkout is untouched outside the namespace.
2. **`.project/decisions/` is rebuilt to the set each baseline run saw**, read
   out of that run's own log. The git tree does not carry it: at `4ed4307`
   `.project/decisions/` holds only `DEC-011.md`, while the 021 run read
   `DEC-019.md` -- most records are untracked working-tree files. The measured
   sets are in `## Digest`.
3. **Criteria 5, 8 and 9 now read the ticket, not `/tmp`.** Step 16 pastes the
   ledger verbatim into `## Decisions` before step 17 deletes the scratch, and
   each ledger row carries `effort_flag`, `strict_mcp`, `decisions` and `cost`.
   Every criterion stays falsifiable after cleanup.

Four things were run rather than assumed this pass: the bind mount, the clone's
checkout of the reflog-only sha `4ed4307`, the per-run decision sets, and a
content check of four `DEC-*.md` records quoted in baseline logs against today's
files (all four identical).

Still true: `effort: high` stays either way -- DEC-024 fixes it, and this ticket
measures the model axis only.

**Plan-validation, third pass (2026-08-21): rejected.** The two items the second
pass failed now pass: the bind mount removes the live checkout from the replay's
view, and step 16 pastes the ledger into `## Decisions` before step 17 deletes
the scratch, so criteria 5, 8, 9 and 10 stay falsifiable. Six of eight items
pass. Two fail, both new, and both have one root -- **two of the twenty baseline
shas in the `## Digest` table are reflog-edge fallbacks, not measurements**:

1. **`ticket/018` and `ticket/021` fall past their reflog.** `git rev-parse "ticket/021@{2026-08-21T05:34:04Z}"` prints `warning: log for 'ticket/021' only goes back to Fri, 21 Aug 2026 12:56:33 +0700` (= 05:56:33Z) and returns `4ed4307`; `ticket/018` at 05:06:10Z warns identically and returns the same sha. `git log -1 4ed4307` is `4ed4307 2026-08-21T12:30:36+07:00 Merge branch 'main' into ticket/019` -- a ticket/019 commit, made 24 minutes *after* the 018 run started. For 021 the table's main sha and branch sha are then equal, so `git merge-base --is-ancestor main HEAD` returns 0, while the 021 baseline log's FAIL item reads verbatim "`git merge-base --is-ancestor main HEAD` reports main is *not* an ancestor". The replay would invert the fact the verdict rests on. The other eighteen shas resolve silently and match the table.
2. **Step 2's own stop rule fires and has no fallback.** Step 2 halts the ticket on exactly that `warning: log for ... only goes back to` string. So the plan either stops at step 2 with no measurement -- the whole deliverable -- or ignores its own rule and pays to replay 021 against the wrong tree.

To clear: establish both branch shas from a source other than the reflog past
its edge and record how, then give step 2 a fallback for a warned row. If a sha
cannot be established, drop that row and state the loss -- 021 is one of the two
catches this ticket exists to reproduce. Full per-item scoring is in `## Thread`.

## Reproduction

Test: `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage`

Command:

    uv run --group dev pytest -q tests/test_stages.py::test_plan_validation_is_not_an_opus_stage

Output:

    >       assert C.stage_config("plan-validation")["model"] != "opus"
    E       AssertionError: assert 'opus' != 'opus'

expect: AssertionError: assert 'opus' != 'opus'

The test asserts the frontmatter fact only. It does not assert the sonnet/opus
verdicts match; the Summary asks for that experiment, and no test can stand in
for it.

## Digest

**Files this plan modifies:** `pipeline/stages/plan-validation.md` (the `model:`
line and the comment above it) and `tests/test_stages.py` (the triage test).
Nothing else. The experiment writes its evidence into this ticket.

**What changed since the rejected plan.** That plan ran the replay against
`/tmp/pv-main` while the agent's ticket text still named
`/home/chezzijr/proj/claude-setup`, so every absolute path in a baseline run
reached today's repo -- including `.project/tickets/TICKET-024.md`, which now
holds the opus verdict the replay must produce. This plan mounts the clone over
that path in a user namespace, so the live checkout is not reachable from the
replay at all. It also rebuilds `.project/decisions/`, which the git tree does
not carry, and it moves the evidence criteria 5, 8 and 9 read out of `/tmp` and
into this ticket before the scratch is deleted.

**Key functions**, all resolved from the baseline copy of the package, which
inside the namespace is `/home/chezzijr/proj/claude-setup/pipeline/`:

- `pipeline/core/config.py:23 stage_config()` -- reads the frontmatter the test asserts.
- `pipeline/core/config.py:52 compose_prompt(stage, hcfg)` -- `_common.md` + the stage body into one temp file. Two-argument at every baseline sha; today's takes a third `view` argument (DEC-023, `a97e7b7`). Calling the baseline copy is what keeps the agent's system prompt the baseline's.
- `pipeline/core/config.py:74 render(hcfg, cfg, *, tid, project, ticket, result_file, session, prompt, settings, key)` -- fills the harness `cmd` template. Signature verified identical at `cad2b6b` and `aeaa400` with `git show <sha>:pipeline/core/config.py`.
- `pipeline/core/config.py:131 stage_settings(stage, cfg)` -- writes a fresh `tempfile.NamedTemporaryFile(delete=False)` JSON registering `PreToolUse`/`Bash` -> `HOOKS_DIR/dangerous-commands.py`. Under the mount `HOOKS_DIR` renders as `/home/chezzijr/proj/claude-setup/pipeline/hooks`, the baseline string. Without this call the replay runs `bypassPermissions` with no guard.
- `pipeline/core/worktree.py:11 project_env()` -- strips `VIRTUAL_ENV`, `PYTHONHOME`, `PYTHONPATH` and the venv's `PATH` entries. `implementing` runs under `uv`, so a replay spawned without it runs against the wrong Python.
- `pipeline/daemon/supervisor.py:339` -- `env["PIPELINE_READONLY"] = "0" if cfg.get("write") else "1"`. Never in the command. `plan-validation` declares `write: false`, so every baseline run saw `1` and got the guard's allowlist; the script sets it explicitly.

**Entry point for the experiment:** `/tmp/pv-replay.py`, source at the end of
this section. One invocation is one replay: rebuild the clone and its worktree,
recover the ticket text and the decision set, mount, render, run, read the
verdict, append to a ledger.

**Baseline: the opus verdict this experiment must reproduce.** One agent run
per ticket -- the first `plan-validation` session that produced a `result=`.
Gate-only rejections (024 at 08:27:16Z) had no agent and are excluded.
Run-start is the `gate · verdict=` entry directly above each ticket's
`transition` entry. Both shas resolved in the real repo with
`git rev-parse "<ref>@{2026-08-21T<run-start>Z}"`; all twenty resolved.
`decisions` is the record set that run actually saw, recovered from its own log
(see below); `F7` abbreviates
`DEC-011,DEC-016,DEC-017,DEC-018,DEC-019,DEC-020,DEC-021`.

| ticket | run-start (Z) | session | main sha | branch sha | decisions | opus | log cost |
|---|---|---|---|---|---|---|---|
| 016 | 05:01:58 | a1bbd939-6f4e-4822-ae01-b7e9c48c4fd8 | cad2b6b | a234f18 | DEC-011 | ok | not logged |
| 017 | 05:02:04 | 9ccfbe4e-34a6-4897-a218-3c9b254137e6 | cad2b6b | 1240d83 | DEC-011 | ok | not logged |
| 018 | 05:06:10 | 83d75974-3658-44e9-8ddd-cff49532461c | cad2b6b | 4ed4307 | DEC-011 | ok | not logged |
| 019 | 05:09:28 | f2069b90-36b4-4aa9-9836-453c875afd38 | cad2b6b | ccc22c6 | DEC-011 | ok | not logged |
| 020 | 05:13:34 | a927a050-23f0-421d-a72d-54640217dbbe | cad2b6b | 185d1d7 | DEC-011 | ok | $1.65 |
| 021 | 05:34:04 | d5b37dd1-6049-4df9-aac1-dedd7b0c517b | 4ed4307 | 4ed4307 | DEC-011,DEC-016,DEC-017,DEC-019,DEC-020 | **fail** | $2.72 |
| 022 | 08:30:06 | c85e0be6-32d5-4e9d-8a11-ac35acbc00f6 | aeaa400 | 9ce9675 | F7 | ok | $2.30 |
| 023 | 08:41:00 | 36406001-7ca7-4fa0-80ec-d78c24be342f | aeaa400 | 8f6edac | F7 | ok | $2.51 |
| 024 | 08:30:34 | 0008d014-0909-4077-ac05-159fcd1e72b7 | aeaa400 | 20f6856 | F7 | **fail** | $2.04 |
| 025 | 08:44:43 | 52227449-1765-4e7b-a6c1-afe0fa8f6dd3 | aeaa400 | 8dcda2c | F7 | ok | $1.43 |

Each log is `.project/logs/TICKET-0NN-plan-validation-<first 8 of session>.log`;
all ten exist. Eight `ok`, two `fail` -- the two catches the Summary quotes.
Opus costs $1.43--$2.72 per run, so sonnet costs roughly $0.30--$0.55 and ten
replays cost about $5. That is an estimate, not a bound; the bound is gotcha 8.

The whole baseline window sits inside `[cad2b6b 2026-08-21T11:41:58+07:00,
bd83d0d 15:47:11+07:00)`, so only two versions of the package are in play and
both were checked.

**`.project/decisions/` cannot be recovered from git, so it is recovered from
the logs.** Most records are untracked working-tree files:
`git log --oneline -- .project/decisions/DEC-0NN.md` returns zero commits for
DEC-018 and DEC-021 through DEC-030, and one commit for DEC-016, DEC-017,
DEC-019 and DEC-020. So `git checkout 4ed4307` gives a `.project/decisions/`
holding only `DEC-011.md`, while the 021 run demonstrably read `DEC-019.md`.
The `decisions` column above was measured by replaying each baseline log's
`ls`, `cat` and `grep` tool results and collecting every `DEC-\d+` they
returned. Four of those records were quoted in full in a baseline log --
DEC-011 in the 019 and 021 logs, DEC-019 in the 021 log, DEC-018 in the 024 log
-- and all four are byte-identical to today's file, so copying today's file into
the clone reproduces what the run read. DEC-011 is the only record with a second
commit; it landed `2026-08-21T08:28:15+07:00`, which is 01:28:15Z, before the
05:01:58Z start of the baseline window.

**The ticket text each run read is recoverable, and this was run, not assumed.**
The agent's first tool call is `cat <ticket>` and its `tool_result` holds the
file verbatim. The extractor in `/tmp/pv-replay.py` returned all ten, each
starting `---\nid: TICKET-0NN\nsta`: 016 28827 bytes, 017 33014, 018 33909,
019 29120, 020 21211, 021 26005, 022 22618, 023 38349, 024 36124, 025 22400.
Four (017, 018, 023, 024) were spilled to
`~/.claude/projects/.../tool-results/*.txt`; the extractor follows the
`Full output saved to:` line. Line 1 of each log is a shell command, not JSON,
so parsing starts at line 3.

**Gotchas, each one load-bearing:**

1. **The replay must not see the live checkout.** Baseline runs address it by absolute path: `ls /home/chezzijr/proj/claude-setup/.project/decisions/` in the 021 log, `cat /home/chezzijr/proj/claude-setup/.project/tickets/TICKET-024.md` in the 024 log. Today that file holds the opus `fail` the replay is supposed to produce. The script therefore bind-mounts `/tmp/pv-main` over `/home/chezzijr/proj/claude-setup` in a fresh user namespace, so those exact paths resolve to the clone.
2. **The mount needs no root and no privileges, but the order is fixed.** `os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNS)`, then write `/proc/self/uid_map`, `/proc/self/setgroups`, `/proc/self/gid_map`, then `libc.mount(src, dst, b"none", MS_BIND=0x1000, None)`. Do the mount **before** any `exec`: capabilities are dropped on `execve` when euid is not 0, which is why `unshare --map-current-user --mount python3 -c ...` fails with `EPERM` and the in-process form succeeds. Verified on this box, uid stayed 1000 and the real checkout was unchanged outside the namespace.
3. **Read the real repo before the mount.** The baseline log under `.project/logs/` and the `DEC-*.md` records are read from `/home/chezzijr/proj/claude-setup`, which stops resolving to the real repo the moment the mount takes. The script reads both first and holds them in memory.
4. **`git clone` does not copy reflogs.** `main@{<date>}` resolves only in the real repo, so step 2 resolves every sha there, read-only, and passes them to the clone as literals.
5. **Never move `main` in `/home/chezzijr/proj/claude-setup`.** The dispatcher requires the main checkout parked on the base branch, and other tickets merge against it. `git branch -f main` happens only inside `/tmp/pv-main`.
6. **`ticket/021` was rebased** at 07:11Z. Its pre-rebase commits survive only in the reflog. `git clone --shared` reads the source object store through alternates, so a reflog-only sha still checks out in the clone -- verified: `git -C /tmp/pv-main worktree add --detach .worktrees/TICKET-021 4ed4307` succeeded. Do not drop `--shared`, do not add `--no-hardlinks`, and do not add `git fetch origin '+refs/heads/*:refs/heads/*'` -- it dies with `fatal: refusing to fetch into branch 'refs/heads/main' checked out at '/tmp/pv-main'` and the clone does not need it.
7. **`git rev-parse "<ref>@{<date>}"` is silent at the reflog edges.** Past the oldest entry it returns the oldest and warns on stderr. Run it without redirecting stderr; `warning: log for ... only goes back to` means stop.
8. **The worktree lives inside the clone, at the baseline's own relative path.** `/tmp/pv-main/.worktrees/TICKET-0NN` is `/home/chezzijr/proj/claude-setup/.worktrees/TICKET-0NN` under the mount, which is the cwd every baseline run had. `.worktrees/` is in `.gitignore` (line 3), so nothing in the clone objects.
9. **The baseline ran with no `--effort` flag.** `effort` reached the stage files at `bd83d0d` 15:47:11+07:00, after every baseline run, and `stage_config()` reads the main checkout, so `{effort_flag}` rendered empty. Rendering from the baseline package reproduces that on its own; the script asserts `"--effort" not in cmd` rather than trusting it.
10. **The replay tree has no `.venv` and no `.project/logs/`.** The 021 opus run read `textual`'s source from `.worktrees/TICKET-021/.venv/.../textual/app.py`; that path will not exist, and `.project/logs/` is gitignored so the clone has none. Both backed `PASS` items, not either `FAIL` item, so neither can flip the verdict this experiment compares; record them as known differences.
11. **Cost ordering matters.** A sonnet run that passes a plan opus rejected settles the ticket on its own. Replay 021 and 024 first and stop there if either diverges; that costs about $1.10 instead of $5.
12. **Each replay is its own session with its own meter, so `implementing`'s `max_usd: 8` does not bound them.** `pipeline/core/config.py:112` renders `--max-budget-usd {cap}` from the stage's `max_usd: 3`, and that meters one session. Ten replays therefore have a hard ceiling of 10 x $3 = **$30** charged to no counter. The stop rule is in the script: it appends each run's `total_cost_usd` to `/tmp/pv-logs/results.jsonl` and refuses to start a replay once the ledger totals $12 -- more than twice the $5 estimate, far under the $30 worst case. Step 10 stops the loop on that abort, and on any `subtype` other than `"success"`.
13. **The ledger is the only evidence that survives cleanup.** Step 17 deletes `/tmp/pv-logs`, so every acceptance criterion reads the ledger rows step 16 pastes into `## Decisions`, not the files. That is why each row carries `effort_flag`, `strict_mcp`, `decisions` and `cost` and not just the verdict.

**Verdict extraction.** Each replay writes
`/home/chezzijr/proj/claude-setup/.project/tickets/TICKET-0NN.result` under the
mount, which is `/tmp/pv-main/.project/tickets/TICKET-0NN.result` on real disk;
its `result:` key is the verdict. Read that file; do not infer the verdict from
prose. Cost comes from the final stream-json `result` event's `total_cost_usd`
(`{"subtype":"success","total_cost_usd":2.720417,"num_turns":42}` in the 021
baseline log), because the sidecar carries no cost field.

**`/tmp/pv-replay.py` -- the whole experiment, one ticket per invocation.**

```python
#!/usr/bin/env python3
"""TICKET-027: replay one plan-validation run on sonnet. Scratch; /tmp only.
usage: pv-replay.py <TICKET-0NN> <main-sha> <branch-sha> <baseline-log> <DEC-a,DEC-b,...>"""
import ctypes, json, os, subprocess, sys, uuid
from pathlib import Path

LIVE = Path("/home/chezzijr/proj/claude-setup")   # the path every baseline run used
MAIN, LOGS = Path("/tmp/pv-main"), Path("/tmp/pv-logs")
LEDGER, CEILING = LOGS / "results.jsonl", 12.0
LOGS.mkdir(exist_ok=True)

tid, main_sha, br_sha, baseline_log, decs = sys.argv[1:6]
decs = sorted(decs.split(","))
dry = os.environ.get("PV_DRYRUN") == "1"

spent = sum(json.loads(l).get("cost") or 0
            for l in LEDGER.read_text().splitlines() if l.strip()) if LEDGER.exists() else 0.0
assert dry or spent < CEILING, f"stop rule: ${spent:.2f} spent, ceiling ${CEILING:.2f}"

def ticket_text(path, tid):
    """The ticket verbatim as of the run: the first `cat` tool_result in the log."""
    for line in Path(path).read_text().splitlines()[2:]:
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") != "user":
            continue
        for c in (ev.get("message", {}).get("content") or []):
            if not isinstance(c, dict) or c.get("type") != "tool_result":
                continue
            txt = c.get("content")
            if not isinstance(txt, str):
                txt = "".join(b.get("text", "") for b in (txt or []) if isinstance(b, dict))
            if txt.startswith("<persisted-output>"):
                for l in txt.splitlines():
                    if "Full output saved to:" in l:
                        txt = Path(l.split("Full output saved to:")[1].strip()).read_text()
                        break
            if f"id: {tid}" in txt[:200]:
                return txt
    raise SystemExit(f"no ticket text for {tid} in {path}")

# --- everything that reads the REAL repo happens here, before the mount ---
text = ticket_text(baseline_log, tid)
records = {d: (LIVE / ".project" / "decisions" / f"{d}.md").read_text() for d in decs}

git = ["git", "-C", str(MAIN)]
wt = MAIN / ".worktrees" / tid
subprocess.run(git + ["worktree", "remove", "--force", str(wt)])
for c in (["checkout", "--detach", main_sha], ["branch", "-f", "main", main_sha],
          ["worktree", "add", "--detach", str(wt), br_sha]):
    subprocess.run(git + c, check=True)

dd = MAIN / ".project" / "decisions"                  # git does not carry this set
dd.mkdir(parents=True, exist_ok=True)
for p in dd.glob("DEC-*.md"):
    p.unlink()
for name, body in records.items():
    (dd / f"{name}.md").write_text(body)
(MAIN / "PV-CLONE").write_text(tid)                   # the sentinel the mount assert reads
tp = MAIN / ".project" / "tickets" / f"{tid}.md"
tp.write_text(text)
(MAIN / ".project" / "tickets" / f"{tid}.result").unlink(missing_ok=True)

# --- the live checkout is replaced by the clone, for this process tree only ---
u, g = os.getuid(), os.getgid()
os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNS)
Path("/proc/self/uid_map").write_text(f"{u} {u} 1")
Path("/proc/self/setgroups").write_text("deny")
Path("/proc/self/gid_map").write_text(f"{g} {g} 1")
libc = ctypes.CDLL("libc.so.6", use_errno=True)
if libc.mount(str(MAIN).encode(), str(LIVE).encode(), b"none", 0x1000, None):  # MS_BIND
    raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
assert (LIVE / "PV-CLONE").read_text() == tid, "bind mount did not take"

sys.path.insert(0, str(LIVE))
from pipeline.core import config as C
from pipeline.core.worktree import project_env
assert C.__file__.startswith(str(LIVE)), f"wrong package: {C.__file__}"

cfg = dict(C.stage_config("plan-validation"))
cfg["model"] = "sonnet"                       # the one variable under test
hcfg, session = C.harness(), str(uuid.uuid4())
lt = LIVE / ".project" / "tickets" / f"{tid}.md"
lr = LIVE / ".project" / "tickets" / f"{tid}.result"
cmd = C.render(hcfg, cfg, tid=tid, project=LIVE, ticket=lt, result_file=lr,
               session=session, prompt=C.compose_prompt("plan-validation", hcfg),
               settings=C.stage_settings("plan-validation", cfg))
# DEC-025: the baseline harness predates the flag. Restoring it is inert on the
# comparison -- zero mcp__* calls in all ten baseline logs -- and keeps the
# developer's MCP servers out of ten bypassPermissions sessions.
cmd = cmd.replace("--permission-mode", "--strict-mcp-config --permission-mode", 1)
assert "--effort" not in cmd, cmd            # gotcha 9
assert "--strict-mcp-config" in cmd, cmd
seen = sorted(p.stem for p in (LIVE / ".project" / "decisions").glob("DEC-*.md"))
assert seen == decs, f"decisions {seen} != {decs}"
if dry:
    print(cmd)
    print("decisions:", seen)
    raise SystemExit(0)

env = project_env()                           # implementing runs under uv; strip it
env["PIPELINE_STAGE"] = "plan-validation"
env["PIPELINE_READONLY"] = "0" if cfg.get("write") else "1"   # supervisor.py:339
log = LOGS / f"{tid}.log"
with log.open("wb") as fh:
    fh.write(f"$ {cmd}\n\n".encode())
    fh.flush()
    subprocess.run(cmd, shell=True, cwd=LIVE / ".worktrees" / tid, env=env,
                   stdout=fh, stderr=subprocess.STDOUT)

verdict = "no-result"
if lr.exists():
    verdict = next((l.split(":", 1)[1].strip() for l in lr.read_text().splitlines()
                    if l.startswith("result:")), "no-result")
res = next((json.loads(l) for l in log.read_text().splitlines()[2:]
            if l.startswith("{") and '"type":"result"' in l), {})
row = {"ticket": tid, "session": session, "verdict": verdict,
       "cost": res.get("total_cost_usd"), "subtype": res.get("subtype"),
       "effort_flag": "--effort" in cmd, "strict_mcp": "--strict-mcp-config" in cmd,
       "decisions": seen}
with LEDGER.open("a") as f:
    f.write(json.dumps(row) + "\n")
print(json.dumps(row))
```

## Decisions checked

Grepped `.project/decisions/` for
`model|opus|sonnet|max_usd|effort|plan-validation|PIPELINE_READONLY|settings|replay|cost`.
Fifteen records exist (DEC-011, DEC-016 through DEC-026, DEC-028, DEC-029,
DEC-030). `grep -ln superseded-by .project/decisions/*.md` returned nothing, so
all fifteen are active.

- **DEC-024 -- binding, and this plan complies.** It fixes `plan-validation:
  high` and says "a later cost-cutting pass must not flatten" the three `high`
  values. Its argument is about `effort`, not `model`: "one extra `review ->
  implementing` bounce costs more than an effort downgrade saves." This plan
  leaves `effort: high` untouched and changes only `model:`. Criterion 4
  enforces that by `git diff`.
- **DEC-025 -- binding, and this plan complies, as a stated deviation.** DEC-025
  keeps `--strict-mcp-config` in `pipeline/harnesses/claude-code.toml`, because
  without it a stage declaring 7 tools gets 68 including
  `mcp__claude_ai_Gmail__send_message`. The replay renders from the baseline
  harness file, which predates DEC-025 and has no `--strict-mcp-config`, and the
  script then adds the flag back. Evidence that adding it cannot move a verdict:
  all ten baseline logs contain zero `mcp__*` tool calls, against 52 to 77 tools
  offered at `init`. Recorded as a known deviation in `## Decisions`.
- **DEC-023 -- read, not constraining.** It governs `stage_view()` and thread
  trimming. It changed `compose_prompt()` to take a third `view` argument at
  `a97e7b7`, after every baseline run; the replay calls the baseline
  two-argument copy, so DEC-023's behaviour is correctly absent.
- **DEC-028 -- read, not constraining, but it explains the decisions gotcha.**
  It records that this pipeline edits its own harness while running, which is
  the same class of moving target as `.project/decisions/` gaining DEC-029
  during this planning stage. It constrains `_harness_reloader()` in
  `pipeline/daemon/supervisor.py`, which this plan does not touch.
- **DEC-026, DEC-029, DEC-030 -- read, not constraining.** DEC-026 governs the
  `cheap_route` counter, DEC-030 governs Tier A `## Plan` findings in
  `pipeline/core/gate.py`, and neither names a stage model. This plan changes no
  transition row and no gate rule.
- DEC-011, DEC-016 through DEC-022 -- no match beyond incidental mentions of the
  word "cost".

No record is superseded by this plan.

## Plan

1. Build the scratch clone that stands in for the main checkout: `mkdir -p /tmp/pv-logs && git clone --shared /home/chezzijr/proj/claude-setup /tmp/pv-main` -- it must be a clone, never the real checkout, because step 6 forces `main` backwards (gotcha 5), and nothing in `pipeline/stages/plan-validation.md` is edited before step 12.
2. In the **real** repo only, re-resolve every row of the `## Digest` baseline table with `git rev-parse "main@{2026-08-21T<run-start>Z}"` and `git rev-parse "ticket/0NN@{2026-08-21T<run-start>Z}"`, without redirecting stderr; if any command prints `warning: log for ... only goes back to`, stop and report, leaving `pipeline/stages/plan-validation.md` on `model: opus` (gotchas 4 and 7).
3. Write `/tmp/pv-replay.py` verbatim from the source block at the end of `## Digest`; it is the only thing that spawns a replay of `pipeline/stages/plan-validation.md`, and it is what bind-mounts the clone over the live path, rebuilds `.project/decisions/`, regenerates `--settings` through `stage_settings()`, sets `PIPELINE_READONLY=1`, restores `--strict-mcp-config` for DEC-025, asserts `--effort` is absent, and refuses to start once the ledger passes $12.
4. Dry-run the renderer before spending anything: `PV_DRYRUN=1 python3 /tmp/pv-replay.py TICKET-021 4ed4307 4ed4307 /home/chezzijr/proj/claude-setup/.project/logs/TICKET-021-plan-validation-d5b37dd1.log DEC-011,DEC-016,DEC-017,DEC-019,DEC-020`, which prints the command and the decision set only after the mount assert and the two flag asserts have passed inside the namespace, so it also proves the replay of `pipeline/stages/plan-validation.md` is isolated.
5. Confirm step 4's printed command has `--model sonnet`, `--max-budget-usd 3`, `--strict-mcp-config`, `--add-dir /home/chezzijr/proj/claude-setup`, no `--effort`, and a `--settings` path that exists and names `/home/chezzijr/proj/claude-setup/pipeline/hooks/dangerous-commands.py`, and that the printed `decisions:` line reads `['DEC-011', 'DEC-016', 'DEC-017', 'DEC-019', 'DEC-020']`; if any of those seven is wrong, stop and report rather than editing the command by hand, because a replay of `pipeline/stages/plan-validation.md` under a guessed command measures nothing.
6. Replay TICKET-021 for real: `python3 /tmp/pv-replay.py TICKET-021 4ed4307 4ed4307 /home/chezzijr/proj/claude-setup/.project/logs/TICKET-021-plan-validation-d5b37dd1.log DEC-011,DEC-016,DEC-017,DEC-019,DEC-020`, whose printed `verdict` is the sonnet answer to the `fail` that `pipeline/stages/plan-validation.md` produced on opus.
7. Replay TICKET-024: `python3 /tmp/pv-replay.py TICKET-024 aeaa400 20f6856 /home/chezzijr/proj/claude-setup/.project/logs/TICKET-024-plan-validation-0008d014.log DEC-011,DEC-016,DEC-017,DEC-018,DEC-019,DEC-020,DEC-021`, the second of the two runs that can prove `pipeline/stages/plan-validation.md` must keep `model: opus`.
8. If either step 6 or step 7 printed `"verdict": "ok"` where the baseline table says `fail`, stop replaying and go to step 13, leaving `pipeline/stages/plan-validation.md` on `model: opus` (gotcha 11 -- this costs about $1.10 instead of $5).
9. Otherwise run the remaining eight replays one at a time, in the order 016, 017, 018, 019, 020, 022, 023, 025, each `python3 /tmp/pv-replay.py TICKET-0NN <main-sha> <branch-sha> <baseline log> <decisions>` with that row's values from the `## Digest` table, still comparing against the opus behaviour of `pipeline/stages/plan-validation.md`.
10. Stop the loop in step 9 and go to step 13 if any replay prints a `subtype` other than `"success"`, or if the script aborts on its own `$12` ledger assertion; record the partial table and leave `pipeline/stages/plan-validation.md` unchanged rather than reporting a verdict no agent produced.
11. Write the comparison into this ticket's `## Decisions` as one row per replayed ticket with columns `ticket | session | opus | sonnet | match | cost`, taken from `/tmp/pv-logs/results.jsonl`, plus one line recording gotcha 10's missing `.venv` and missing `.project/logs/` as known differences, so a later reader can price the model in `pipeline/stages/plan-validation.md` without re-running anything.
12. If every replayed row matched, edit `pipeline/stages/plan-validation.md` line 2 from `model: opus` to `model: sonnet` and insert above it the comment `# sonnet: replayed on TICKET-016..025, 10/10 verdicts identical to opus (TICKET-027)`, leaving `effort: high` and its two comment lines untouched because DEC-024 fixes them.
13. If any row diverged or the run stopped early, leave `pipeline/stages/plan-validation.md` on `model: opus` and insert above it the comment `# opus: sonnet replay diverged on TICKET-0NN (TICKET-027) -- it <verdict> a plan opus <verdict>`, naming the diverging ticket.
14. If step 12 applied, run `uv run --group dev pytest -q tests/test_stages.py::test_plan_validation_is_not_an_opus_stage` and confirm it passes; `tests/test_stages.py` needs no edit on that branch.
15. If step 13 applied, replace `test_plan_validation_is_not_an_opus_stage` in `tests/test_stages.py` with `test_plan_validation_stays_on_opus_for_a_recorded_reason`, asserting both `C.stage_config("plan-validation")["model"] == "opus"` and that `(C.STAGES_DIR / "plan-validation.md").read_text()` contains `TICKET-027`.
16. Paste `/tmp/pv-logs/results.jsonl` verbatim into this ticket's `## Decisions`, one fenced JSON line per replay, directly under the step 11 table, because step 17 deletes the file and criteria 5, 8 and 9 read those rows rather than `/tmp`; this is evidence for `pipeline/stages/plan-validation.md`, not scratch.
17. Delete every scratch artefact: `git -C /tmp/pv-main worktree list --porcelain` then `rm -rf /tmp/pv-main /tmp/pv-logs /tmp/pv-replay.py` -- the clone holds ten rewritten tickets and must not outlive the measurement that `pipeline/stages/plan-validation.md` records.
18. Run the whole stage suite with `uv run --group dev pytest -q tests/test_stages.py` and confirm it is green, since `tests/test_stages.py` also asserts every stage declares a model and an effort.
19. Commit with `git add pipeline/stages/plan-validation.md tests/test_stages.py` then `git commit -m "perf: plan-validation's model is a measured choice, not a default"`.

## Acceptance criteria

1. `uv run --group dev pytest -q tests/test_stages.py` is green. Under step 12 the passing test is `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage`; under step 13 it is `tests/test_stages.py::test_plan_validation_stays_on_opus_for_a_recorded_reason`. Exactly one of the two exists in the file.
2. This ticket's `## Decisions` holds a table with one row per ticket for 016, 017, 018, 019, 020, 021, 022, 023, 024 and 025, or fewer rows plus the step 8 or step 10 early exit naming the diverging ticket. Each row states the opus verdict, the sonnet verdict and whether they match. Falsified by a missing row or a row with no sonnet verdict.
3. The `model:` line in `pipeline/stages/plan-validation.md` carries a comment naming TICKET-027 and the measurement behind it. Asserted by `tests/test_stages.py::test_plan_validation_stays_on_opus_for_a_recorded_reason` under step 13, and read by criterion 2's table under step 12.
4. `effort: high` and its two comment lines in `pipeline/stages/plan-validation.md` are byte-for-byte unchanged. Falsified by `git diff pipeline/stages/plan-validation.md` showing any line but `model:` and the comment above it.
5. This ticket's `## Decisions` holds the pasted ledger from step 16, with one JSON row per row of criterion 2's table. Falsified by a criterion 2 row whose `session` or verdict differs from the ledger row for the same ticket, or by a ledger row whose `verdict` is `no-result` -- the script writes that key only from the `.result` sidecar's `result:` line.
6. None of `/tmp/pv-main`, `/tmp/pv-logs`, `/tmp/pv-replay.py` exists after step 17. Falsified by any of `test -e /tmp/pv-main`, `test -e /tmp/pv-logs`, `test -e /tmp/pv-replay.py` succeeding.
7. Every replay ran with a live guard and the read-only allowlist. Asserted by step 5's dry-run: the printed command's `--settings` path exists and its JSON names `/home/chezzijr/proj/claude-setup/pipeline/hooks/dangerous-commands.py`, and `/tmp/pv-replay.py` sets `PIPELINE_READONLY=1`. Falsified by a `--settings` path that does not exist, or by the string `PIPELINE_READONLY` being absent from step 5's transcript of `/tmp/pv-replay.py`.
8. No replay ran with `--effort` and every replay ran with `--strict-mcp-config`. Falsified by any pasted ledger row in `## Decisions` carrying `"effort_flag": true` or `"strict_mcp": false`. The script asserts both before spawning, so a violation aborts rather than spends.
9. Total replay spend stayed under $12. Falsified by the `cost` values in the pasted ledger rows summing to $12 or more. The ceiling without the stop rule is 10 x $3 = $30, and criterion 2's table records the actual total.
10. Every replay saw the baseline decision set and not today's. Falsified by any pasted ledger row whose `decisions` list differs from that ticket's `decisions` column in the `## Digest` baseline table, or by any row containing `DEC-026`, `DEC-028`, `DEC-029` or `DEC-030`. The script asserts the set inside the namespace, after the mount, so a mismatch aborts rather than spends.

## Decisions

**`plan-validation`'s model is whatever the replay measured, and the frontmatter
comment says which.** The comment above `model:` is the record; do not drop it
in a later tidy-up. A future cost pass that wants to move this stage to a
cheaper model must repeat the replay, not repeat the argument.

**The replay compares verdicts, not prose.** The opus baseline is the `result:`
key of the run's `.result` sidecar, recovered from each ticket's first
`plan-validation` agent session. A gate rejection is not an agent verdict:
TICKET-024's 08:27:16Z `verdict=FAIL` came from the deterministic gate with no
agent spawned, and counting it would invent an eleventh data point.

**The replay runs in a user namespace with the clone bind-mounted over
`/home/chezzijr/proj/claude-setup`.** Baseline agents address the repo by
absolute path, and today that path holds later tickets, later decisions and, for
TICKET-024, the very opus verdict the replay is meant to reproduce. Rewriting
paths or denying reads would have changed agent behaviour; replacing the
directory changes nothing the agent can observe except the date. The mount is
unprivileged and process-tree-local: `os.unshare(CLONE_NEWUSER|CLONE_NEWNS)`,
uid/gid maps, then `MS_BIND`, all in one process before any `exec`, because
`execve` drops capabilities when euid is not 0. Nothing outside that process
tree sees the mount, and the real checkout is never written.

**`.project/decisions/` is rebuilt from the logs because git does not carry it.**
Ten of the fifteen records have zero commits -- they are untracked working-tree
files -- so a checkout of the baseline sha gives `DEC-011.md` alone while the
021 run demonstrably read `DEC-019.md`. The set each run saw was recovered by
collecting every `DEC-\d+` its own log's `ls`, `cat` and `grep` results
returned. Anyone who later "simplifies" this to `git checkout <sha> --
.project/decisions/` will silently starve the replay of the records the stage
under test spends most of its reading on.

**The replay must not pass `--effort`.** Every baseline run rendered
`{effort_flag}` empty, because `effort` reached the stage files only at
`bd83d0d` and `stage_config()` reads the main checkout. Adding `--effort high`
to the replay would compare two configurations that differ in two ways and
attribute the difference to the model.

**`main` is rewritten in a `/tmp` clone, never in the real checkout.** Two
baseline verdicts depend on what `main` pointed at when they ran -- TICKET-021's
`fail` is literally `git merge-base --is-ancestor main HEAD`. Forcing `main`
backwards in `/home/chezzijr/proj/claude-setup` would break the dispatcher's
"main checkout is parked on the base branch" precondition and every pending
merge.

**A replay is rendered from the baseline package, never transcribed from a log
header.** The header is not a complete record of a spawn: `--settings` names a
per-spawn `tempfile` that no longer exists, the system prompt is
`$(cat <tempfile>)`, and `PIPELINE_READONLY` never appears in the command at
all. Importing the package from under the mount regenerates all of them, and
gets the empty `{effort_flag}` and the old positional wording for free.

**A replay runs with `PIPELINE_READONLY=1`, not the parent's value.**
`plan-validation` declares `write: false`, so every baseline run got the guard's
*allowlist*. `implementing` declares `write: true` and exports `0`. A nested
spawn inherits the parent env, so without the explicit set the replay would run
the same agent under the blocklist -- a second uncontrolled variable, and a
weaker guard, in an experiment whose discipline is one variable at a time.

**Nested agent spawns are not bounded by the spawning stage's `max_usd`.**
`--max-budget-usd` meters one session. Ten replays at `max_usd: 3` have a
ceiling of $30 charged to no counter, which is why `/tmp/pv-replay.py` keeps its
own ledger and refuses to start past $12. Any future ticket that spawns agents
from inside a stage needs its own ledger; the dispatcher will not supply one.

**The evidence lives in this ticket, not in `/tmp`.** Step 16 pastes the ledger
into `## Decisions` before step 17 deletes the scratch, and criteria 5, 8, 9 and
10 read those rows. A criterion that reads a path a later step deletes cannot be
falsified, which is the defect that rejected the second pass of this plan.

**The replay adds `--strict-mcp-config` even though the baseline lacked it.**
This is a deliberate, recorded deviation, not an oversight. DEC-025 exists
because without the flag a stage declaring 7 tools gets 68, Gmail among them.
The flag shipped at `8a2b1fc`, six minutes after the last baseline run. It is
inert on the comparison: all ten baseline logs contain zero `mcp__*` tool calls
against 52--77 tools offered at `init`. Running ten `bypassPermissions` sessions
with the developer's MCP servers loaded, to be faithful to an accident of
timing, is the wrong trade.

**Known differences: the replay tree has no `.venv` and no `.project/logs/`.**
The 021 opus run read `textual`'s source from
`.worktrees/TICKET-021/.venv/.../textual/app.py`; `.venv` is not in git, and
`.project/logs/` is gitignored, so neither exists in the clone. Both backed
`PASS` items, not either `FAIL` item, so neither can flip the compared verdict.
Recorded rather than fixed, because populating either would change the tree the
baseline saw in a second, unmeasured way.

## Rollback

Revert the single commit from step 19. It touches
`pipeline/stages/plan-validation.md` and `tests/test_stages.py` only, and the
revert restores `model: opus` with the triage test failing again -- the exact
state this ticket started from. No worktree, no branch and no other ticket
depends on it. The scratch artefacts (`/tmp/pv-main`, `/tmp/pv-logs`,
`/tmp/pv-replay.py`) are already gone after step 17; nothing else needs undoing.
Nothing outside `/tmp` was written by the experiment -- in particular `main` in
`/home/chezzijr/proj/claude-setup` never moved, and the bind mount lived and
died inside one process tree.

The `## Decisions` table and the ledger pasted under it survive the revert
because they live in this ticket, so a re-run starts from the measurement
instead of repeating it.

## Thread

### 2026-08-21 08:59:52Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 09:05Z · triage · reproduce · result=ok

Reproduced. `pipeline/stages/plan-validation.md` frontmatter reads `model: opus`,
`effort: high`. Every stage, for comparison:

| stage | model | effort |
|---|---|---|
| holistic-review | opus | medium |
| implementing | sonnet | medium |
| planning | opus | high |
| plan-validation | opus | high |
| review | opus | high |
| triage | opus | low |

sonnet is the only other model any stage uses.

Added one test to `tests/test_stages.py`, the file that already asserts stage
frontmatter (`test_every_stage_prompt_declares_its_config`). It fails with
`AssertionError: assert 'opus' != 'opus'`. Committed on `ticket/027`.

Two notes for planning, both outside triage scope:

1. The test locks the model, not the verdicts. The Summary's experiment -- re-run
   plan-validation on sonnet over TICKET-016..025 and compare verdict for verdict
   -- has to be run by hand, and its result belongs in `## Decisions`.
2. The frontmatter comment justifies `effort: high` ("a false pass costs
   implementing + review + revalidating"). Lowering the model does not answer it.
   Say whether it still holds, or leave `effort` alone.

### 2026-08-21 09:00:58Z · triage · session · session=7ef563f9-cdfb-4611-aa11-be18c257078f

`triage` ran as session `7ef563f9-cdfb-4611-aa11-be18c257078f`
- replay: `claude --resume 7ef563f9-cdfb-4611-aa11-be18c257078f`
- log: `.project/logs/TICKET-027-triage-7ef563f9.log`

### 2026-08-21 09:00:58Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

✓ Reproduced: plan-validation.md declares model: opus. Failing test committed as 6d05f29.

### 2026-08-21 · planning · result=ok

Plan written. The experiment is specified as steps 1--11 and runs in
`implementing`, not here.

**Why planning did not run it.** Ten sonnet replays cost about $5. Planning had
$1.75 of its `max_usd: 5` left after the research. Starting the replays would
have exhausted the cap mid-experiment and cost a full planning re-run. Every
input the replays need is now in `## Digest`, so `implementing` runs commands
rather than research.

**What the research found that the ticket's Summary did not assume.** The
Summary says the experiment "needs no live ticket, because every plan this
session is already on disk with its verdict". Two corrections:

1. The plans that earned the two catches are **not** on disk in the form opus
   rejected. TICKET-021 and TICKET-024 were replanned after their `fail`, and
   `## Plan` was rewritten in place. The rejected text survives only in the
   run's log, which is why steps 2--4 reconstruct it.
2. Both catches are relative to a repo state, not to the plan text alone.
   TICKET-021's `fail` is `git merge-base --is-ancestor main HEAD` reporting
   main is not an ancestor, and `main` has moved eleven times since. A replay in
   today's repo would score a different question, so step 3 rewrites `main` in a
   `/tmp` clone.

**Two notes outside this stage's scope.**

1. Triage asked whether DEC-024's `effort: high` justification still holds. It
   does. `## Decisions checked` records the reading, and no step touches
   `effort`.
2. The Summary says the same question applies to `review` and says not to bundle
   it. This plan does not. The replay recipe in `## Digest` transfers to `review`
   unchanged -- same logs, same reflogs, same spawn command -- so that ticket is
   measurement, not research.

**One thing a human may want to redirect at the gate.** Steps 13 and 15 cover
the outcome where sonnet diverges: keep `model: opus`, record the divergence in
the frontmatter comment, and replace the triage test with one asserting the
recorded reason. That path ships a decision record and no behaviour change, and
it rewrites the test triage committed. The precedent is DEC-024, which recorded
`effort` as a comment plus a test in the same file. Reject the plan if you would
rather the ticket close with no code change at all.

### 2026-08-21 09:10:35Z · planning · session · session=16c27147-ad8b-48a7-a085-59208c402bad

`planning` ran as session `16c27147-ad8b-48a7-a085-59208c402bad`
- replay: `claude --resume 16c27147-ad8b-48a7-a085-59208c402bad`
- log: `.project/logs/TICKET-027-planning-16c27147.log`

### 2026-08-21 09:10:35Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

✓ Plan written: replay 10 opus plan-validation verdicts on sonnet, 021 and 024 first; frontmatter changes only if all match

### 2026-08-21 09:10:45Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage` fails as required
```
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/claude-setup/.worktrees/TICKET-027
configfile: pyproject.toml
collected 1 item

tests/test_stages.py F

=================================== FAILURES ===================================
__________________ test_plan_validation_is_not_an_opus_stage ___________________

    def test_plan_validation_is_not_an_opus_stage():
        """plan-validation reads a plan against a checklist -- sonnet's job."""
>       assert C.stage_config("plan-validation")["model"] != "opus"
E       AssertionError: assert 'opus' != 'opus'

tests/test_stages.py:135: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_plan_validation_is_not_an_opus_stage - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage` fails on base `main` too -- the bug is not already fixed upstream
```
is_not_an_opus_stage ___________________

    def test_plan_validation_is_not_an_opus_stage():
        """plan-validation reads a plan against a checklist -- sonnet's job."""
>       assert C.stage_config("plan-validation")["model"] != "opus"
E       AssertionError: assert 'opus' != 'opus'

tests/test_stages.py:135: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_plan_validation_is_not_an_opus_stage - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-_9o5crzd/base
      Built pipeline @ file:///tmp/pipeline-base-_9o5crzd/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 · plan-validation · finding · result=fail · severity=blocking

**Rejected. Two items fail: "no research left" and "riskiest step has a
fallback". Six items pass.** Both failures are the same omission seen twice: the
plan reconstructs the baseline spawn command from a log header, and two of that
command's inputs are not recoverable from the header.

**Item 1 -- Root cause vs symptom: PASS.** Root cause in my words: nobody
measured which model this stage needs. `pipeline/stages/plan-validation.md` line
2 reads `model: opus` because opus was the default choice for a judgment stage,
not because a cheaper model was tried and found worse. The test fails on that
line, but flipping the line alone would be the symptom fix. Steps 12 and 13 both
write a comment recording the measurement, so either outcome leaves the *reason*
on disk. The plan fixes the why.

**Item 2 -- Decision conflict: PASS with one correction.** DEC-024 binds and the
plan complies: it fixes `effort: high` for this stage and forbids a cost pass
from flattening it, and no step touches `effort`. Criterion 4 enforces that by
`git diff`. DEC-023 exists and `## Decisions checked` does not list it. Its
grep terms match -- DEC-023 cites
`.project/logs/TICKET-016-plan-validation-a1bbd939.log`. I read DEC-023: it
governs `stage_view()` and thread trimming, and it does not constrain a model
change. The enumeration is incomplete; the conclusion is unaffected.

**Item 3 -- Scope discipline: PASS.** Every step traces to a criterion. Steps
1--11 to criteria 2 and 5, steps 12--13 to criteria 3 and 4, steps 14--16 to
criterion 1, step 17 to criterion 6. Step 18 is the commit. No step is orphaned.

**Item 4 -- Falsifiable criteria: PASS.** Criteria 1, 2, 4, 5 and 6 each name a
command or a row whose absence falsifies them. One weakness, not blocking:
under step 12 no test asserts criterion 3's comment, because step 15's test only
exists on the step 13 branch. Criterion 4's `git diff` shows the comment line, so
a human at the gate can still falsify it.

**Item 5 -- No research left: FAIL.** Step 6 says to run "the `## Digest`
command, substituting `--model sonnet`, a fresh `--session-id`,
`--max-budget-usd 3`, `--add-dir /tmp/pv-replay`, the scratch ticket path, and
**no** `--effort` flag". That leaves two inputs of the baseline command
unresolved.

1. **`--settings` is a dead path.** The Digest header carries `--settings
   /tmp/tmptrdz5ehv.json`. `pipeline/core/config.py:131 stage_settings()` writes
   that file with `tempfile.NamedTemporaryFile(delete=False)` on every spawn, so
   the baseline's copy is a stale `/tmp` path, and the plan never names the
   function that regenerates it. Step 5 regenerates the prompt via
   `compose_prompt()` and stops there. An implementing agent following step 6
   literally passes a path that no longer exists, and the replay then runs
   `--permission-mode bypassPermissions` with **no `dangerous-commands` hook
   registered** -- the guard is the only layer that decides with code.
2. **`PIPELINE_READONLY` is not in the command at all.**
   `pipeline/daemon/supervisor.py:338` sets it in the child's environment:
   `env["PIPELINE_READONLY"] = "0" if cfg.get("write") else "1"`.
   `plan-validation` declares `write: false`, so every baseline run saw `1` and
   got the guard's allowlist. A replay spawned from `implementing` (`write:
   true`) inherits `0` and gets the blocklist instead. The plan does not mention
   the variable.

Together these are two uncontrolled variables in an experiment whose stated
discipline is one variable at a time (gotcha 1 omits `--effort` for exactly this
reason). A sonnet run with a different guard is not the comparison the ticket
asked for.

**Item 6 -- Riskiest step has a fallback: FAIL.** The riskiest step is 10: eight
more nested `claude` spawns. The plan prices it as bounded -- "Ten replays cost
about $5, inside `implementing`'s `max_usd: 8`". That is wrong on mechanism.
`pipeline/core/config.py:112` renders `cap=cfg.get("max_usd", ...)` into
`--max-budget-usd {cap}`, which meters **one session**. Each replay is a
separate `claude` process with its own `--max-budget-usd 3`; its spend never
reaches the parent's meter, and `pipeline/daemon/supervisor.py` reads a stage's
cost from that stage's own `result` event. So `implementing`'s `max_usd: 8`
does not bound the replays at all. The real ceiling is 10 x $3 = $30, charged to
no counter and no bound. Step 9's early exit fires only when 021 or 024
diverges; the all-match path is the expensive one and has no stop. The plan
needs a stated ceiling and a fallback for a replay that hits its cap mid-run.

**Item 7 -- Regression surface: PASS.** Two files change. `tests/test_stages.py`
also asserts every stage declares a model and an effort, and step 16 runs the
whole file. Under step 12 the behaviour change is to every future
`plan-validation` run, which no test covers -- the replay table is the evidence,
and the plan says so rather than claiming a test.

**Item 8 -- Blast radius matches class: PASS.** `class: refactor`, two declared
files, one commit, one revert in `## Rollback`. The diff matches the class. The
*cost* does not -- see item 6 -- but that is a bound problem, not a
classification problem.

**One more, non-blocking, for whoever revises.** `## Decisions checked` says of
DEC-025 that "the replay copies the harness flags verbatim, so it neither relies
on nor weakens that flag". "Verbatim" is ambiguous between two commands that
differ: the Digest header has no `--strict-mcp-config`, and
`pipeline/harnesses/claude-code.toml:79` has it today. Copying the header is
faithful to the baseline and is probably right, but it means the replay runs
with MCP servers loaded -- the harness records 68 tools from 9 servers without
that flag. Say which command "verbatim" names.

**What would make this pass.** Name `stage_settings()` in a step, set
`PIPELINE_READONLY=1` for each replay, state the $30 ceiling with a stop rule,
and disambiguate the DEC-025 sentence. The experiment design itself -- baseline
table, replay order, `/tmp` clone, `.result` extraction -- is sound and needs no
rework.

### 2026-08-21 09:14:19Z · plan-validation · session · session=b229a67f-6c39-4827-8e9a-630f61ba2cf6

`plan-validation` ran as session `b229a67f-6c39-4827-8e9a-630f61ba2cf6`
- replay: `claude --resume b229a67f-6c39-4827-8e9a-630f61ba2cf6`
- log: `.project/logs/TICKET-027-plan-validation-b229a67f.log`

### 2026-08-21 09:14:19Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

✓ Plan rejected: 6/8 items pass; replay omits stage_settings() and PIPELINE_READONLY, and 10 nested spawns cost up to $30 outside implementing's max_usd

### 2026-08-21 · planning · result=ok

**Replanned. Both `FAIL` items fixed at one root: the replay is no longer built
from the log header.** The rejection's own words -- "the plan reconstructs the
baseline spawn command from a log header, and two of that command's inputs are
not recoverable from the header" -- name the root cause. Patching step 6 to add
two flags would leave the same method in place. Instead the baseline commit is
checked out into `/tmp/pv-main` and `render()` is called from that copy of the
package, so every input is regenerated by the code that produced the baseline.

Point by point against the four things the review asked for:

1. **"Name `stage_settings()` in a step."** Step 3 names it, and
   `/tmp/pv-replay.py` calls `C.stage_settings("plan-validation", cfg)` with
   `HOOKS_DIR` resolving to `/tmp/pv-main/pipeline/hooks/dangerous-commands.py`
   -- the baseline guard, freshly registered. Step 4 is a `PV_DRYRUN=1` pass
   that verifies the `--settings` path exists before any money is spent, and
   step 5 stops the ticket if it does not. Criterion 7 falsifies it.
2. **"Set `PIPELINE_READONLY=1` for each replay."** The script sets
   `env["PIPELINE_READONLY"] = "0" if cfg.get("write") else "1"`, copied from
   `pipeline/daemon/supervisor.py:339`, and `plan-validation` declares
   `write: false`. It also calls `project_env()`, which the rejected plan also
   missed: `implementing` runs under `uv` and would otherwise hand the replay
   the wrong Python. Verified the guard reads the variable at both baseline
   shas: `git show cad2b6b:pipeline/hooks/dangerous-commands.py` line 231 is
   `why = verdict(command, os.environ.get("PIPELINE_READONLY") == "1")`, and
   `aeaa400` is identical.
3. **"State the $30 ceiling with a stop rule."** Gotcha 8 states it with the
   mechanism (`config.py:112` meters one session; the parent's `max_usd: 8`
   never sees a child's spend). The script appends `total_cost_usd` to
   `/tmp/pv-logs/results.jsonl` and asserts the total is under **$12** before
   starting. Step 10 also stops on any `subtype` other than `"success"`, which
   is what a budget-exhausted replay looks like. Criterion 9 falsifies it.
4. **"Disambiguate the DEC-025 sentence."** Resolved in `## Decisions checked`
   and `## Decisions`: the replay renders from the *baseline* harness, which has
   no `--strict-mcp-config`, and then adds the flag back. This is a deliberate
   deviation, and the evidence that it cannot move a verdict was measured, not
   argued -- zero `mcp__*` tool calls across all ten baseline logs, against
   `init` reporting 77, 77, 77, 72, 77, 72, 77, 52, 77, 77 tools.

Also fixed, unprompted: `## Decisions checked` now lists DEC-023 (read, not
constraining -- it is why today's `compose_prompt()` takes a third `view`
argument the baseline copy does not).

Two claims the rejected plan asserted are now measured:

- All twenty baseline shas resolve. `main` was `cad2b6b` for 016--020,
  `4ed4307` for 021, `aeaa400` for 022--025; branch shas are in the
  `## Digest` table. `git rev-parse` at the reflog edge warns on stderr rather
  than failing, so gotcha 4 tells the implementer not to redirect it.
- The ticket-text extractor was run against all ten baseline logs and returned
  all ten, each starting `---\nid: TICKET-0NN\nsta`: 21211 to 38349 bytes. Four
  came from spilled `tool-results/*.txt` files. The rejected plan left this as a
  `jq` incantation for the implementer to get right.

One review remark is acknowledged and not acted on. Item 4 noted that under
step 12 no test asserts criterion 3's frontmatter comment, because step 15's
test exists only on the divergence branch. That is still true. Adding a test
that asserts a comment string on the match branch would mean `tests/test_stages.py`
asserting the *provenance* of a value rather than the value, and criterion 4's
`git diff` already exposes the comment at the human gate. Flagged here so the
next reader sees it was a choice.

No question for the human: nothing in the rejection needed a decision only a
human could make.

### 2026-08-21 09:25:30Z · planning · session · session=f0e6ac02-c7f4-40c4-85bf-bd68ae274746

`planning` ran as session `f0e6ac02-c7f4-40c4-85bf-bd68ae274746`
- replay: `claude --resume f0e6ac02-c7f4-40c4-85bf-bd68ae274746`
- log: `.project/logs/TICKET-027-planning-f0e6ac02.log`

### 2026-08-21 09:25:30Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

✓ Replanned: replay renders from the baseline package (stage_settings, PIPELINE_READONLY=1, project_env), $12 ledger stop under the $30 ceiling, DEC-025 flag restored on measured evidence

### 2026-08-21 09:35:14Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage` fails as required
```
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/claude-setup/.worktrees/TICKET-027
configfile: pyproject.toml
collected 1 item

tests/test_stages.py F

=================================== FAILURES ===================================
__________________ test_plan_validation_is_not_an_opus_stage ___________________

    def test_plan_validation_is_not_an_opus_stage():
        """plan-validation reads a plan against a checklist -- sonnet's job."""
>       assert C.stage_config("plan-validation")["model"] != "opus"
E       AssertionError: assert 'opus' != 'opus'

tests/test_stages.py:135: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_plan_validation_is_not_an_opus_stage - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage` fails on base `main` too -- the bug is not already fixed upstream
```
_is_not_an_opus_stage ___________________

    def test_plan_validation_is_not_an_opus_stage():
        """plan-validation reads a plan against a checklist -- sonnet's job."""
>       assert C.stage_config("plan-validation")["model"] != "opus"
E       AssertionError: assert 'opus' != 'opus'

tests/test_stages.py:135: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_plan_validation_is_not_an_opus_stage - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-u_q3gc58/base
      Built pipeline @ file:///tmp/pipeline-base-u_q3gc58/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```

### 2026-08-21 09:39:08Z · plan-validation · note

`plan-validation` was interrupted; lease released

### 2026-08-21 09:48:45Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage` fails as required
```
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/claude-setup/.worktrees/TICKET-027
configfile: pyproject.toml
collected 1 item

tests/test_stages.py F

=================================== FAILURES ===================================
__________________ test_plan_validation_is_not_an_opus_stage ___________________

    def test_plan_validation_is_not_an_opus_stage():
        """plan-validation reads a plan against a checklist -- sonnet's job."""
>       assert C.stage_config("plan-validation")["model"] != "opus"
E       AssertionError: assert 'opus' != 'opus'

tests/test_stages.py:135: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_plan_validation_is_not_an_opus_stage - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage` fails on base `main` too -- the bug is not already fixed upstream
```
is_not_an_opus_stage ___________________

    def test_plan_validation_is_not_an_opus_stage():
        """plan-validation reads a plan against a checklist -- sonnet's job."""
>       assert C.stage_config("plan-validation")["model"] != "opus"
E       AssertionError: assert 'opus' != 'opus'

tests/test_stages.py:135: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_plan_validation_is_not_an_opus_stage - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-kvp7doga/base
      Built pipeline @ file:///tmp/pipeline-base-kvp7doga/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 · plan-validation · result=fail

**Plan rejected: 6 of 8 items pass, 2 fail.** Both failures are new. The two
items the first pass failed -- `stage_settings()` and `PIPELINE_READONLY` -- now
pass, and I verified the mechanism rather than the prose.

**1. Root cause vs symptom -- PASS.** Root cause: `pipeline/stages/plan-validation.md`
line 2 reads `model: opus` and nothing measured it; the test asserts that
frontmatter fact. The plan measures first and sets the line from the result,
including the branch where the measurement says keep opus (step 13). It does not
flip the line to pass the test.

**2. Decision conflict -- PASS.** DEC-024 fixes `effort: high`; the plan leaves
it and criterion 4 falsifies any other changed line. DEC-025 is a stated
deviation with evidence (zero `mcp__*` calls in ten baseline logs) and the
script restores `--strict-mcp-config`. DEC-023 is correctly absent: I ran
`git show cad2b6b:pipeline/core/config.py` and line 52 is
`def compose_prompt(stage: str, hcfg: dict | None = None) -> Path:`, against
today's `def compose_prompt(stage: str, hcfg: dict | None = None, view: str = "") -> Path:`.

**3. Scope discipline -- PASS.** Every step traces to a criterion: 1--10 to
criteria 2 and 9, 11 to 2, 12--13 to 3 and 4, 14--16 to 1, 17 to 6, 18 to
`## Rollback`.

**4. Falsifiable criteria -- FAIL.** Criteria 5, 8 and 9 depend on files
criterion 6 requires deleted. Step 17 runs
`rm -rf /tmp/pv-main /tmp/pv-wt /tmp/pv-logs /tmp/pv-replay.py`. Criterion 5 is
"Falsified by a row whose session id does not appear in the run's log header",
criterion 8 is "Falsified by `grep -c '\-\-effort' /tmp/pv-logs/*.log`", and
criterion 9 is "Falsified by the `cost` values in `/tmp/pv-logs/results.jsonl`".
After step 17 all three read a deleted path, so none can fail. Fix: copy the
ledger and each log's line 1 into the `## Decisions` table before step 17, and
point criteria 5, 8 and 9 at the ticket. Criterion 8's wording also needs one
word: `grep -c` exits non-zero when the count is **zero**, so "returning
non-zero" inverts the intended check -- say "a count above 0".

**5. No research left -- PASS.** Every cited symbol resolves at the baseline
sha, checked with `git show cad2b6b:pipeline/core/config.py`: `stage_config` 23,
`compose_prompt` 52, `render` 74, `stage_settings` 131 -- the Digest's numbers
exactly. `render`'s baseline signature accepts the script's call. The baseline
`cmd` in `pipeline/harnesses/claude-code.toml` contains `--permission-mode
{permission_mode}` and `--add-dir {project}`, so step 3's `.replace()` and step
4's checks have something to match. `git diff cad2b6b aeaa400 --stat` over
`config.py`, `claude-code.toml`, `plan-validation.md` and
`dangerous-commands.py` printed nothing -- the two baseline versions are
identical on every file this plan renders from.

**6. Riskiest step -- FAIL.** The riskiest step is the replay itself (steps 6,
7, 9): ten nested `bypassPermissions` sessions charged to no counter. The plan
has a fallback for the two ways it can cost too much (the $12 ledger assertion,
the `subtype != "success"` stop) and for divergence (steps 8 and 13). It has no
fallback for the way the measurement can be wrong: **a replay is not isolated
from the live repo, so a divergence cannot be attributed to the model.** Both
decisive baseline runs read outside their worktree by absolute path:

    021 log: "command":"ls /home/chezzijr/proj/claude-setup/.project/decisions/; echo
    024 log: "command":"cat /home/chezzijr/proj/claude-setup/.project/tickets/TICKET-024.md
    024 log: "command":"head -25 /home/chezzijr/proj/claude-setup/.worktrees/TICKET-024/pipeli

Those paths resolve in a replay, to today's state, not the baseline's. Three
concrete differences, all checked just now:

1. `ls .project/decisions/` returns fourteen records (DEC-011, DEC-016 through
   DEC-026, DEC-028, DEC-030). The plan's own grep found eleven, and the
   baseline runs saw fewer still. A replay can invent a decision conflict the
   opus run could not see.
2. `ls .worktrees/` returns `TICKET-027 TICKET-029 TICKET-031`. Every absolute
   `.worktrees/TICKET-0NN/...` read in a baseline log now fails.
3. `.project/tickets/TICKET-024.md` line 793 is
   `### 2026-08-21 08:34:24Z · plan-validation · transition · to=planning · result=fail`.
   The replay agent can read the verdict it is being measured against, at the
   same absolute path the baseline agent used. That is answer leakage on one of
   the two runs the plan replays first.

The plan writes the baseline ticket text to `/tmp/pv-main/.project/tickets/` and
stops there. Nothing blocks or detects a read of
`/home/chezzijr/proj/claude-setup`. Gotcha 6 records the missing `.venv` as a
known difference and this is the same class of problem, larger and unrecorded.
Cheapest fix that keeps the experiment honest: after each replay, grep its log
for `/home/chezzijr/proj/claude-setup` and treat a hit as a contaminated run --
one more stop condition in step 10, one more column in criterion 2's table. A
stronger fix is to make the replay's guard refuse those paths, but detection is
enough to keep a divergence attributable.

**7. Regression surface -- PASS.** The experiment writes nothing outside `/tmp`
and never moves `main` in the real checkout (gotcha 2, and the `git -C
/tmp/pv-main` prefix on every mutating command in `/tmp/pv-replay.py`). The
shipped change is two lines of frontmatter plus a test. What could break is the
stage suite, and `tests/test_stages.py` covers it: criterion 1 runs the whole
file, which also asserts every stage declares a model and an effort. Criterion 4
covers the one regression that would be invisible -- a tidy-up that drops
`effort: high` while editing `model:`.

**8. Blast radius matches class -- PASS.** Two files:
`pipeline/stages/plan-validation.md` and `tests/test_stages.py`. The eighteen
steps are the measurement, not the diff.

**What to fix.** Item 4 is a wording and ordering change: record the evidence in
the ticket before step 17 deletes it. Item 6 needs a real addition: a
contamination check per replay, with a stop condition and a table column. Do not
re-derive the replay method -- it is now sound, and `git show
cad2b6b:pipeline/core/config.py` backs every line number the Digest cites.

### 2026-08-21 09:52:35Z · plan-validation · session · session=619570e3-60bb-4232-afab-cc8531bb0940

`plan-validation` ran as session `619570e3-60bb-4232-afab-cc8531bb0940`
- replay: `claude --resume 619570e3-60bb-4232-afab-cc8531bb0940`
- log: `.project/logs/TICKET-027-plan-validation-619570e3.log`

### 2026-08-21 09:52:35Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ Plan rejected: 6/8 pass; replay reads the live repo by absolute path (024's ticket now holds its own opus verdict), and criteria 5/8/9 read /tmp artefacts criterion 6 deletes

### 2026-08-21 · planning · replan (third pass)

Replanned after `plan-validation` rejected the second pass on two items. Both
are fixed at the root, not patched at the step that failed.

**1. "The replay is not isolated from the live repo."** Correct, and the fix is
not to rewrite paths or deny reads -- either changes what the agent does. The
replay now bind-mounts `/tmp/pv-main` over `/home/chezzijr/proj/claude-setup`
in an unprivileged user namespace, so
`cat /home/chezzijr/proj/claude-setup/.project/tickets/TICKET-024.md` returns
the 08:30:34Z ticket text, not today's file with its own opus verdict at line
793. Verified on this box before planning it:

```
$ python3 /tmp/nsbind.py /tmp/nstest/fake /home/chezzijr/proj/claude-setup sh -c 'id -u; cat /home/chezzijr/proj/claude-setup/marker.txt'
1000
FAKE
--- outside ---
CLAUDE.md
hooks
pipeline
```

uid stays 1000, and the real checkout is unchanged outside the namespace. The
mount must happen in-process before any `exec`: `unshare --map-current-user
--mount python3 ...` fails with
`PermissionError: [Errno 1] bind ...: Operation not permitted`, because
`execve` drops capabilities when euid is not 0. Gotcha 2 records this.

**A second contamination the rejection did not name, found while fixing the
first.** `.project/decisions/` is not reproduced by checking out the baseline
sha. Ten of the fifteen records are untracked working-tree files:

```
$ for f in .project/decisions/DEC-*.md; do printf "%s %s\n" "$(git log --oneline -- $f | wc -l)" "$f"; done
2 .project/decisions/DEC-011.md
1 .project/decisions/DEC-016.md
...
0 .project/decisions/DEC-018.md
0 .project/decisions/DEC-021.md
```

`git checkout 4ed4307` gives a `.project/decisions/` holding `DEC-011.md`
alone, while the 021 baseline log shows the agent running
`cat /home/chezzijr/proj/claude-setup/.project/decisions/DEC-019.md`. The set
each run saw is now recovered from its own log and rebuilt in the clone; the
measured sets are the `decisions` column of the `## Digest` table. Four records
quoted in full in a baseline log (DEC-011 in the 019 and 021 logs, DEC-019 in
the 021 log, DEC-018 in the 024 log) are byte-identical to today's file, so
copying today's file reproduces what the run read.

**2. "Criteria 5, 8 and 9 read artefacts criterion 6 requires deleted."**
Correct. New step 16 pastes `/tmp/pv-logs/results.jsonl` verbatim into
`## Decisions` before step 17 deletes the scratch, and each ledger row now
carries `effort_flag`, `strict_mcp`, `decisions` and `cost` as well as
`session`, `verdict` and `subtype`. Criteria 5, 8, 9 and the new criterion 10
read those pasted rows. Nothing in `## Acceptance criteria` now reads a `/tmp`
path except criterion 6, which asserts the path is gone, and criterion 7, which
reads step 5's dry-run transcript.

**One step from the old plan was wrong and is deleted.** Old step 1 ran
`git -C /tmp/pv-main fetch origin '+refs/heads/*:refs/heads/*'`, which dies:

```
fatal: refusing to fetch into branch 'refs/heads/main' checked out at '/tmp/pv-main'
```

The clone does not need it. `git clone --shared` reads the source object store
through alternates, so the reflog-only sha survives:
`git -C /tmp/pvchk worktree add -q --detach /tmp/pvchk/.worktrees/TICKET-021 4ed4307`
returned `OK`.

The experiment design is otherwise unchanged: replay 021 and 024 first, stop on
the first divergence, verdict from the `.result` sidecar, `$12` ledger stop
under the $30 nested-session ceiling, `effort: high` untouched per DEC-024.

Not run here: the ten replays. `implementing` has `max_usd: 8` and runs them as
steps 1--10.

### 2026-08-21 10:03:48Z · planning · session · session=b1b48a81-2f8d-4696-a5e8-2a0d44415a7a

`planning` ran as session `b1b48a81-2f8d-4696-a5e8-2a0d44415a7a`
- replay: `claude --resume b1b48a81-2f8d-4696-a5e8-2a0d44415a7a`
- log: `.project/logs/TICKET-027-planning-b1b48a81.log`

### 2026-08-21 10:03:48Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Replanned: replay bind-mounts the clone over /home/chezzijr/proj/claude-setup in a user namespace, rebuilds .project/decisions from each baseline log, and pastes the ledger into the ticket so criteria 5/8/9/10 survive cleanup

### 2026-08-21 10:03:58Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage` fails as required
```
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/claude-setup/.worktrees/TICKET-027
configfile: pyproject.toml
collected 1 item

tests/test_stages.py F

=================================== FAILURES ===================================
__________________ test_plan_validation_is_not_an_opus_stage ___________________

    def test_plan_validation_is_not_an_opus_stage():
        """plan-validation reads a plan against a checklist -- sonnet's job."""
>       assert C.stage_config("plan-validation")["model"] != "opus"
E       AssertionError: assert 'opus' != 'opus'

tests/test_stages.py:135: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_plan_validation_is_not_an_opus_stage - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.02s ===============================

```
- ok: `tests/test_stages.py::test_plan_validation_is_not_an_opus_stage` fails on base `main` too -- the bug is not already fixed upstream
```
is_not_an_opus_stage ___________________

    def test_plan_validation_is_not_an_opus_stage():
        """plan-validation reads a plan against a checklist -- sonnet's job."""
>       assert C.stage_config("plan-validation")["model"] != "opus"
E       AssertionError: assert 'opus' != 'opus'

tests/test_stages.py:135: AssertionError
=========================== short test summary info ============================
FAILED tests/test_stages.py::test_plan_validation_is_not_an_opus_stage - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-4pm8x6jv/base
      Built pipeline @ file:///tmp/pipeline-base-4pm8x6jv/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 · plan-validation · result=fail

**Plan rejected: 6 of 8 items pass, 2 fail.** Both failures are new and both
have one root: the `## Digest` baseline table's `branch sha` column is a
measurement for eight rows and a reflog-edge fallback for two. The two items
the second pass failed now pass, and I verified each mechanism rather than the
prose.

**1. Root cause vs symptom -- PASS.** Root cause: `pipeline/stages/plan-validation.md`
line 2 reads `model: opus` and no measurement chose it; the test asserts that
frontmatter fact. I read the file: line 2 is `model: opus`, line 5 is
`effort: high`. The plan measures first and writes the line from the result,
including the branch where the measurement says keep opus (step 13). It does not
flip the line to pass the test.

**2. Decision conflict -- PASS.** Three claims checked against the shas, not the
prose.

- DEC-024 fixes `effort: high`. The plan leaves it and criterion 4 falsifies any
  other changed line. Lines 3--4 of the stage file are the two comment lines
  criterion 4 protects.
- DEC-025 is a stated deviation with evidence. `git show cad2b6b:pipeline/harnesses/claude-code.toml`
  and `git show aeaa400:...` both return **zero** matches for `strict-mcp-config`;
  today's file has it. The flag landed at
  `8a2b1fc 2026-08-21T15:50:50+07:00`, after the last baseline run
  (08:44:43Z = 15:44:43+07:00). Both baseline `cmd` templates carry
  `--permission-mode {permission_mode}` at line 74, so the script's
  `cmd.replace("--permission-mode", "--strict-mcp-config --permission-mode", 1)`
  has an anchor.
- DEC-023 is correctly absent. At both `cad2b6b` and `aeaa400`,
  `pipeline/core/config.py:52` is
  `def compose_prompt(stage: str, hcfg: dict | None = None) -> Path:`, against
  today's `def compose_prompt(stage: str, hcfg: dict | None = None, view: str = "") -> Path:`.
  The script calls the two-argument form.

**3. Scope discipline -- PASS.** Every step traces to a criterion: 1--10 to
criteria 2, 7, 8, 9 and 10; 11 to 2; 12--13 to 3 and 4; 14--15 to 1; 16 to 5;
17 to 6; 18 to 1; 19 to `## Rollback`.

**4. Falsifiable criteria -- PASS.** The second pass failed this item because
criteria 5, 8 and 9 read `/tmp` paths step 17 deletes. Fixed: step 16 pastes the
ledger into `## Decisions` before step 17 runs, and criteria 5, 8, 9 and 10 now
read the pasted rows. Each row carries `verdict`, `session`, `cost`,
`effort_flag`, `strict_mcp` and `decisions`, which is what those four criteria
test. All four can still fail after cleanup.

**5. No research left -- FAIL. Two of the twenty baseline shas are not
measurements.** `## Digest` states "all twenty baseline shas resolve
(`git rev-parse "<ref>@{<run-start>}"`)". Run today, two of twenty warn:

```
$ git rev-parse "ticket/021@{2026-08-21T05:34:04Z}"
warning: log for 'ticket/021' only goes back to Fri, 21 Aug 2026 12:56:33 +0700
4ed43077e976805cb0bf12934e55579ba059f2ba

$ git rev-parse "ticket/018@{2026-08-21T05:06:10Z}"
warning: log for 'ticket/018' only goes back to Fri, 21 Aug 2026 12:56:33 +0700
4ed43077e976805cb0bf12934e55579ba059f2ba
```

`12:56:33 +0700` is `05:56:33Z`, after both run starts. This is gotcha 7's own
case: past the oldest entry `git rev-parse` returns the oldest and warns. Both
rows therefore carry the same fallback value, and the table records it as the
branch sha for both. The remaining eighteen resolve silently, and all eighteen
match the table.

The fallback is demonstrably not either run's tree:

```
$ git log --format='%h %cI %s' -1 4ed4307
4ed4307 2026-08-21T12:30:36+07:00 Merge branch 'main' into ticket/019
```

Three consequences.

1. `4ed4307` is a **ticket/019** merge commit. TICKET-018's worktree was not checked out at it.
2. `4ed4307` was committed `12:30:36+07:00` = `05:30:36Z`, **24 minutes after** TICKET-018's run started at `05:06:10Z`. A branch sha that postdates the run cannot be what the run saw.
3. For TICKET-021 the table gives main sha `4ed4307` and branch sha `4ed4307` -- identical. `git merge-base --is-ancestor main HEAD` then returns 0. The 021 baseline log records the opposite, verbatim: **"FAIL -- blast radius / regression surface / criterion 6 is wrong.\n`git merge-base --is-ancestor main HEAD` reports main is *not* an ancestor."** That sentence is one of the two FAIL items the replay of 021 must reproduce. The plan would hand the sonnet agent a tree where the fact is inverted.

Step 6 replays TICKET-021 first. So the first real spend runs against a tree
that contradicts the verdict it is measuring, and a sonnet `ok` there would be
read as "sonnet missed the catch" when the tree, not the model, changed. That is
a third uncontrolled variable, the same defect the plan rejects for `--effort`
and for the live checkout.

The plan already recovers two things git does not carry -- the ticket text and
`.project/decisions/` -- from each run's own log. The branch sha needs the same
treatment or an explicit recorded exception. I did not find ticket/021's HEAD in
its log: the only `4ed4307` occurrences there are `git log --oneline main -8`
output and the agent's prose about TICKET-019, not a `git rev-parse HEAD`. So
whether the log carries it is open, and that is research this stage should not
be doing.

Two citation slips found while checking, neither load-bearing and neither the
reason for this FAIL: `## Digest` cites `pipeline/daemon/supervisor.py:339` for
`env["PIPELINE_READONLY"] = "0" if cfg.get("write") else "1"`, which is line
**347** today (339 is `ticket=ticket_path(project, tid),`); the mechanism is
right and the script sets the variable itself. The four `config.py` line numbers
(23, 52, 74, 131) are correct for the baseline copies, which is what the Digest
says they are -- I confirmed all four with `git show <sha>:pipeline/core/config.py`.

**6. Riskiest step -- FAIL. The plan's own stop rule fires at step 2 and there
is no fallback.** Step 2 reads: "if any command prints `warning: log for ... only
goes back to`, stop and report, leaving `pipeline/stages/plan-validation.md` on
`model: opus`". Item 5 shows that warning appears today, for two rows. Executed
literally, the plan halts at step 2, spends $0, and produces no verdict
comparison -- which is the whole deliverable. Executed loosely, the agent
ignores its own stop rule and replays against the wrong tree. Neither branch
reaches the measurement.

The riskiest step is correctly identified elsewhere in the plan (step 6, the
first paid replay) and correctly bounded: gotcha 12's $12 ledger, gotcha 11's
order, step 10's `subtype` check. The missing fallback is for step 2, and step 2
is what gates step 6.

**7. Regression surface -- PASS.** The diff is two files. `pipeline/stages/plan-validation.md`
changes one line plus a comment; anything else is falsified by criterion 4's
`git diff`. `tests/test_stages.py` changes only on the step 13 branch, and
criterion 1 pins exactly one of the two test names. Step 18 runs the whole
`tests/test_stages.py`, which the plan notes also asserts every stage declares a
model and an effort -- that is the test covering the frontmatter this ticket
edits. The experiment writes nothing outside `/tmp` and the ticket: `main` in
`/home/chezzijr/proj/claude-setup` never moves (gotcha 5), and the bind mount is
process-tree-local.

**8. Blast radius matches class -- PASS.** `class: refactor`, two files, one
`model:` line and one test. The nineteen steps are the measurement, not the
change.

**What would clear this.** Both FAIL items close together:

1. Establish TICKET-018's and TICKET-021's branch sha from a source that is not the reflog past its edge, and record how it was established.
2. Give step 2 a fallback for the reflog-edge warning, so a warned row is resolved that way instead of halting the ticket.

If neither sha can be established, say so and drop those two rows from the
experiment with the loss stated -- 021 is one of the two catches the Summary
quotes, so dropping it changes what the result can claim.

### 2026-08-21 10:08:20Z · plan-validation · session · session=2a693866-5f7c-48b1-9b83-4ba50d839c04

`plan-validation` ran as session `2a693866-5f7c-48b1-9b83-4ba50d839c04`
- replay: `claude --resume 2a693866-5f7c-48b1-9b83-4ba50d839c04`
- log: `.project/logs/TICKET-027-plan-validation-2a693866.log`

### 2026-08-21 10:08:20Z · plan-validation · transition · to=escalated · result=fail · marker=yes

**plan-validation -> escalated** (result: `fail`)

✓ Plan rejected: 6/8 pass; ticket/018 and ticket/021 fall past their reflog so both branch shas are the 4ed4307 fallback (a ticket/019 commit made 24min after the 018 run), and step 2's own stop rule fires on that warning with no fallback

### 2026-08-21 12:24:26Z · human · note

**Closed: keep `model: opus`.** The experiment ran by hand, outside the pipeline.

The three planning attempts all failed on the same thing: replaying historical plans
needs branches that were deleted (`ticket/018`, `ticket/021`), ticket files that now
contain the opus verdict the replay must not see, and nested `claude` spawns past
`implementing`'s `max_usd`. That plan cannot be written safely, which is why this
ticket escalated at `plan_validation_attempts: 3`.

The question it asked was still worth answering, so it was answered directly:

1. **Agreement on a good plan.** TICKET-032's real plan, scored by both models on the
   same prompt and the same `stage_view()`. Both returned `ok`. Sonnet hand-traced the
   loop to check a criterion was reachable and flagged step 12's missing criterion,
   which opus did not mention.
2. **The decisive case — a planted vacuous criterion.** The same plan with one extra
   acceptance criterion: `grep -c "def " pipeline/daemon/supervisor.py returns at
   least 1`. It already returns 39, so it passes on unmodified code. This is exactly
   the failure opus caught on TICKET-024 (`criterion 7 is vacuous -- its grep returns
   7 today`).

```
opus   -> result: fail -- seven items pass; acceptance criterion 6 is vacuous --
          base returns 36, so it passes on unmodified code and cannot detect a
          wrong implementation
sonnet -> result: ok -- all eight items pass
```

Opus ran the grep to get the base count. Sonnet marked item 4 (falsifiable criteria)
`pass` with the vacuous line in the list.

**Decision: no change.** The saving was ~24% of a session's stage spend; the cost is a
false accept in the stage whose whole job is catching a plan that cannot fail. A missed
vacuous criterion is paid for later by a `review` bounce plus an `implementing` re-run,
and `review` caught three vacuous tests in this session alone.

Not evidence against sonnet elsewhere: this tests one stage on one adversarial plan,
n=1 per model. `triage` and `implementing` already run sonnet and have shipped 15
tickets. If this is revisited, plant the flaw and compare -- agreement on a plan both
models accept proves nothing.
