---
id: TICKET-094
stage: done
class: feature
branch: ticket/094
test_file: tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide
files_declared:
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/daemon/main.py
- pipeline/daemon/supervisor.py
- pipeline/templates/pipeline.toml
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 11
  plan_files: 7
  no_result: 0
  structural_gate_failures: 1
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: be46b420-e12d-423a-9a70-fd45a22c7f2a
  log: .project/logs/TICKET-094-review-be46b420.log
  cost_usd: 1.7636299999999998
approved_by: 'chezzijr (via Claude Code, while away; this session also filed the ticket
  -- not an independent gate). Verified the share arithmetic: with -j 3 and two busy
  projects, ceil(3/2)=2 but the second sees others=2 and takes min(3-2,2)=1, so the
  total is 3 and never 4; a quiet project is excluded from rivals so one busy project
  still reaches full -j; run() watches one project so rivals=1 and today''s behaviour
  is unchanged. Nothing fenced -- pipeline/templates/pipeline.toml is not .project/pipeline.toml.
  Design note accepted rather than re-planned: the budget lives in a module-level
  _MACHINE dict shared by the test process, where serve() could have owned it in states
  and passed the share as max_parallel with no global; step 11 acknowledges the shared-process
  risk and step 8 pins the two prunes. Expect a rebase against 086, which changed
  run() and the tick call site.'
approved_at: '2026-08-29T06:25:14.354804+00:00'
---

## Summary

worker budget is per project, so N projects multiply the machine's parallelism -- fixed

`-j` was not machine-wide: `serve()` passed the same `max_parallel` into every
project's `tick()` with that project's own inflight dict. `implementing`
landed the approved 11-step plan: `_MACHINE` in `pipeline/daemon/supervisor.py`
holds every ticked project's inflight dict by identity; `machine_share()`
gives each project the smaller of what `-j` has left and an equal share among
projects with demand; `tick()` takes the smaller of that share and
`_start_cap()`; `serve()` calls `machine_watch()` every pass and rotates which
project ticks first. Two prunes stop the budget leaking: an unwatched project
drops out, and one whose directory is gone drops out.

All four new tests pass (`machine_cap_is_shared`, `quiet_project`, `rotates`,
`unwatched_project`). Docs updated: `CLAUDE.md`, `README.md`,
`pipeline/templates/pipeline.toml`, `-j` help text in `pipeline/daemon/main.py`
and `pipeline/cli/main.py`. Five commits, one per plan phase.

`review` passed the delta with no blocking findings. It re-ran every
acceptance criterion: `483 passed in 34.44s`, `guard: all passed`, the repro
test `1 passed in 0.16s`, the four new tests `4 passed, 76 deselected`, and
all three greps. It recorded three minor findings and refuted three candidate
blocking ones; both lists are in the last `## Thread` entry.

Two known limits stand as documented, and neither blocks. A project `serve()`
lists in `wanted` but never locks keeps `want: True` forever, since only
`tick()` calls `machine_demand()`. Rotation does not hand over a freed slot,
because `reap()` runs inside the owning project's own `tick()`. Both only
lower parallelism.

## Reproduction

Test: `tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide`
Command: `uv run --group dev pytest -q tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide`

Two projects, each with 2 queued triage tickets, each ticked with `-j 1`
(`max_parallel=1`). Total inflight across both projects is 2, not 1.

Output:
```
AssertionError: machine cap is 1, but 2 children are inflight across 2 projects
assert 2 <= 1
```

expect: machine cap is 1, but 2 children are inflight across 2 projects

Confirms `pipeline/daemon/supervisor.py:1499` (`serve()`) passes the same
`max_parallel` into every project's `tick()` with that project's own
`inflight` dict, and `_start_cap()` (`pipeline/daemon/supervisor.py:1246`)
only ever lowers a project's own cap, never shares a machine-wide budget
across projects.

## Digest

Files touched: `pipeline/daemon/supervisor.py` (the budget and both loops), `tests/test_dispatch.py` (4 new tests), `CLAUDE.md`, `README.md`, `pipeline/templates/pipeline.toml`, `pipeline/daemon/main.py` and `pipeline/cli/main.py` (the `-j` help text).
Key functions: `_start_cap()` (`pipeline/daemon/supervisor.py:1246`, a project's own `max_parallel` lowering `-j`), `tick()` (`:1269`, the loop that breaks on `len(inflight) >= cap`), `serve()` (`:1445`, one `tick()` per registered project with `states[key]`), `run()` (`:1397`, one project), `reap()` (`:1196`, pops finished records out of the same `inflight` dict).
Entry points: `pipeline start -j N` -> `pipelined` -> `serve()`; `pipeline run -j N` -> `run()`. Both pass one `-j` int down to `tick()`, and `tick()` is the only place a cap is applied (DEC-069).
Gotcha -- the repro test calls `supervisor.tick()` twice with two separate `inflight` dicts and no shared object, so the machine budget must be module state inside `pipeline/daemon/supervisor.py` that `tick()` consults by itself. A budget threaded through `serve()` cannot make that test pass.
Gotcha -- fair share must count only projects with demand. Dividing `-j` by the number of registered projects starves a busy project when the others are idle: `-j 3` over 5 registered projects would run 1 agent.
Gotcha -- the budget stores each project's `inflight` dict BY IDENTITY, because `reap()` and `tick()` mutate that same dict in place. A stored count would freeze the moment a child finished.
Gotcha -- tests that call `supervisor.tick()` directly never tear the budget down, so a stale entry from an earlier test would starve every later one. Two prunes handle it: `machine_watch()` drops projects the dispatcher no longer watches, and `machine_share()` drops an entry whose project directory is gone (every such test ends in `shutil.rmtree`).
Gotcha -- `main` is 13 commits ahead of this branch (TICKET-086), and `merging` rebases onto it. TICKET-086 rewrote `_start_cap()`'s DOCSTRING and wrapped `run()`'s `tick()` call in `try/except Exception`; it did not touch `tick()`'s body or `serve()`. Leave the `_start_cap()` docstring alone and the rebase stays clean.
Gotcha -- a test that stops a fake `tick()` from inside `serve()` or `run()` must raise a `BaseException` subclass, because both loops catch `Exception` (DEC-086).
`pipeline/templates/skills/pipeline-config/SKILL.md:205` only says `max_parallel` is documented in `.project/pipeline.toml`'s own comments, which stays true, so it needs no edit. Nothing this plan touches is in `machine.FENCED`.
Gotcha -- `PLAN_STEP_RE` in `pipeline/core/gate.py:45` matches an INDENTED number too, so a line starting `1.` inside step 2's pasted code reads as its own plan step. That is exactly what the first Tier A run rejected: `machine_share()`'s docstring listed its two limits as `1.` / `2.`. The docstring now states them as prose. When the implementer pastes that code into `pipeline/daemon/supervisor.py` the numbering may come back as a real list, but the ticket's `## Plan` must never carry one.

## Decisions checked

DEC-069 -- `max_parallel` lowers `-j` and never raises it; the cap is applied in `tick()`, not threaded through `run()` and `serve()`; and "`-j` was already a per-project cap, and this key does not make it a machine-wide one". This plan keeps the first two rulings and contradicts the third, so `## Decisions` opens with `supersedes: DEC-069`.
DEC-086 -- every spawn primitive goes through `retry_eagain()`, and a loop detector raised from a fake `tick()` must subclass `BaseException`. Binding on the rotation test in step 6.
DEC-028 -- the harness `.toml` is re-read once per tick and `_harness_reloader()` keeps the last good dict. Untouched: the rotation in step 7 must not move `hcfg = reload()` out of the pass.
Grep terms used against `.project/decisions/`: `max_parallel`, `parallel`, `inflight`, `concurren`, `starv`, `fair`, `round-robin`, `serve()`, `registry.projects`, `-j`.

## Plan

1. Add `test_the_machine_cap_is_shared_when_both_projects_have_work` to `tests/test_dispatch.py`, directly below `test_the_daemons_max_parallel_is_not_machine_wide`: build two `git_project()`s with the same 2-queued-triage-ticket loop that test uses, call `supervisor.machine_watch([p1, p2])`, then call `supervisor.tick(d, harness("fake"), inflight, 2)` once per project, `shutil.rmtree` both projects, and assert `[len(i) for i in inflights] == [1, 1]` with the message `f"a machine cap of 2 over two busy projects must be 1 each, got {[len(i) for i in inflights]}"`. Run `uv run --group dev pytest -q tests/test_dispatch.py -k machine_cap_is_shared` and watch it fail with `AttributeError: module 'pipeline.daemon.supervisor' has no attribute 'machine_watch'`.
2. Add the machine budget to `pipeline/daemon/supervisor.py`, inserted between `_start_cap()` and `tick()`; do not edit `_start_cap()` itself, whose docstring changed on `main`. The code is exactly:

        # Every inflight dict this dispatcher is ticking, by project key:
        #   {"<project path>": {"inflight": <the dict tick() mutates>, "want": bool}}
        # `-j` is ONE budget for the whole dispatcher process. `serve()` hands every
        # project its own `inflight` dict, so nothing but this map sees the total.
        _MACHINE: dict[str, dict] = {}


        def machine_watch(projects) -> None:
            """Declare the projects this dispatcher watches, before it ticks them.

            Seeds one entry per project with `want: True`, so the FIRST pass already
            shares `-j` instead of letting whichever project ticks first take all of
            it, and drops the entry of any project not named -- an unregistered
            project must stop holding machine slots.
            """
            keys = {str(p) for p in projects}
            for key in [k for k in _MACHINE if k not in keys]:
                del _MACHINE[key]
            for key in keys:
                _MACHINE.setdefault(key, {"inflight": {}, "want": True})


        def machine_share(project: Path, inflight: dict, max_parallel: int) -> int:
            """The most children `project` may hold out of the machine-wide `-j`.

            The smaller of two limits: what `-j` has left after the OTHER
            projects' inflight children, and an equal share of `-j` among the
            projects with demand -- this one, plus every other whose last tick
            left a ticket it had no slot for. A quiet project is not counted,
            so one busy project still reaches `-j`.

            `inflight` is stored by identity: `reap()` and `tick()` mutate that same
            dict, so the count read here is always current. An entry whose project
            directory is gone is dropped -- nothing will ever tick it again.
            """
            key = str(project)
            entry = _MACHINE.setdefault(key, {"inflight": inflight, "want": True})
            entry["inflight"] = inflight
            for k in [k for k in _MACHINE if k != key and not Path(k).is_dir()]:
                del _MACHINE[k]
            others = sum(len(e["inflight"]) for k, e in _MACHINE.items() if k != key)
            rivals = 1 + sum(1 for k, e in _MACHINE.items() if k != key and e["want"])
            share = -(-max_parallel // rivals)      # ceil, so a share is never 0
            return max(0, min(max_parallel - others, share))


        def machine_demand(project: Path, want: bool) -> None:
            """Record whether `project` had a ticket the machine cap gave no slot."""
            entry = _MACHINE.get(str(project))
            if entry is not None:
                entry["want"] = want

3. Wire the budget into `tick()` in `pipeline/daemon/supervisor.py`. Keep `worked = reap(project, inflight, emit)` and `tickets = all_tickets(project)`; replace `cap = _start_cap(project, max_parallel) if tickets else max_parallel` with `share = machine_share(project, inflight, max_parallel)` then `cap = min(_start_cap(project, max_parallel), share) if tickets else share` then `want = False`; replace `if stopping() or len(inflight) >= cap:` and its `break` with `if stopping():` / `break` / `if len(inflight) >= cap:` / `want = len(inflight) >= share   # the machine cap stopped it, not this project's own key` / `break`; add `machine_demand(project, want)` immediately above the closing `return worked`; and end the docstring with "The start cap is the smallest of the `-j` argument, this project's share of it, and the project's own `max_parallel` key."
4. Call `machine_watch()` from both loops in `pipeline/daemon/supervisor.py`: in `run()` add `machine_watch([project])   # -j is this dispatcher's budget; one project has all of it` directly below `inflight: dict[str, dict] = {}`, and in `serve()` add `machine_watch(wanted)   # -j is one budget for all of them` below the `for key in [k for k in states if k not in wanted]:` release loop and above `worked = False`. Run `uv run --group dev pytest -q tests/test_dispatch.py -k "machine_cap or max_parallel"`, expect every selected test to pass including `test_the_daemons_max_parallel_is_not_machine_wide`, and commit steps 1-4 as `fix(TICKET-094): share -j across projects as one machine-wide budget`.
5. Add `test_a_quiet_project_does_not_shrink_a_busy_ones_share` to `tests/test_dispatch.py` below the step 1 test: `busy` is a `git_project()` with 2 queued triage tickets, `quiet` is a `git_project()` with none; call `supervisor.machine_watch([busy, quiet])`, tick `quiet` first with `supervisor.tick(quiet, harness("fake"), {}, 2)`, then `supervisor.tick(busy, harness("fake"), inflight, 2)`, `shutil.rmtree` both, and assert `len(inflight) == 2` with the message `f"a quiet project takes no share of -j 2, expected 2 children, got {len(inflight)}"`. Run `uv run --group dev pytest -q tests/test_dispatch.py -k quiet_project`, expect it to pass, and commit as `test(TICKET-094): pin that a quiet project takes no share of -j`.
6. Add `test_serve_rotates_which_project_ticks_first` to `tests/test_dispatch.py` next to `test_a_merged_dispatcher_change_ends_the_daemon_loop_too`, built from that test's shape: one `tempfile.mkdtemp()` holding `Store(tmp / "events.db")` and `Server(store, tmp / "daemon.sock")`, two `project()` dirs passed to `registry.register`, `class Stop(BaseException)` because `serve()` catches `Exception` (DEC-086), a `def fake_tick(proj, hcfg, *a, **kw)` that appends `str(proj)` to `seen` and raises `Stop` once `len(seen) >= 4`, `supervisor.serve(0, "fake", 1, store, server, once=False)` inside `try/except Stop`, and a `finally` that restores `supervisor.tick`, calls `registry.unregister` on both projects and `shutil.rmtree`s all three dirs; then assert `seen[0] != seen[2]` with the message `f"pass 2 must not tick the same project first: {seen}"` and assert `set(seen[:2]) == set(seen[2:])`. Run `uv run --group dev pytest -q tests/test_dispatch.py -k rotates` and watch it fail on `pass 2 must not tick the same project first`.
7. Rotate the project order in `serve()` in `pipeline/daemon/supervisor.py`: initialise `turn = 0` on the line after `stale, moved = _source_watcher(), None`, and replace `for key, proj in wanted.items():` with `keys = list(wanted)` then `keys = keys[turn % len(keys):] + keys[:turn % len(keys)] if keys else keys` then `turn += 1` then `for key in keys:` whose first body line is `proj = wanted[key]`. Run `uv run --group dev pytest -q tests/test_dispatch.py -k "rotates or machine_cap or max_parallel"`, expect all selected tests to pass, and commit as `fix(TICKET-094): rotate which project serve() ticks first`.
8. Add `test_an_unwatched_project_stops_holding_machine_slots` to `tests/test_dispatch.py` below the step 6 test: two `tempfile.mkdtemp()` paths `p1` and `p2`; call `supervisor.machine_watch([p1, p2])` and `supervisor.machine_share(p1, {"TICKET-001": {}, "TICKET-002": {}}, 2)`, assert `supervisor.machine_share(p2, {}, 2) == 0` with the message `"p1 holds both slots"`, call `supervisor.machine_watch([p2])` and assert `supervisor.machine_share(p2, {}, 2) == 2` with the message `"an unwatched project must stop holding machine slots"`; then call `supervisor.machine_watch([p1, p2])` and `supervisor.machine_share(p1, {"TICKET-001": {}, "TICKET-002": {}}, 2)` again, `shutil.rmtree(p1)`, and assert `supervisor.machine_share(p2, {}, 2) == 2` with the message `"a project directory that is gone must stop holding machine slots"`; finish with `supervisor.machine_watch([])` and `shutil.rmtree` on both paths. Run `uv run --group dev pytest -q tests/test_dispatch.py -k unwatched_project`, expect it to pass, and commit as `test(TICKET-094): pin the machine budget's two prunes`.
9. Update the docs in one commit. In `CLAUDE.md`, replace the whole gotcha bullet that starts "**`-j` is already per project, not machine-wide.**" with one titled "**`-j` is the dispatcher's machine-wide budget, shared across projects.**" that states: `machine_watch()` and `machine_share()` in `pipeline/daemon/supervisor.py` hold every ticked project's `inflight` dict in one map; a project starts a child only while the total across projects is under `-j`, and never more than an equal share of `-j` among the projects that reported demand at their last tick; `serve()` rotates which project ticks first each pass; the budget is per dispatcher PROCESS, so a `pipeline run` beside a `pipeline start` gets its own `-j`; `max_parallel` in `.project/pipeline.toml` still only lowers one project's own number, and a bad value is printed and ignored.
10. Finish the doc commit from step 9 in the remaining files. In `README.md`, rewrite the `## Concurrency` paragraph that today begins "A project can lower that number further" so it says `-j` is the dispatcher's whole budget across every registered project rather than `-j` each, that each project with work gets an equal share when the cap binds, that the tick order rotates, that a quiet project takes no share, and that two dispatchers each get their own `-j`, keeping the existing `max_parallel = 1` toml block and the sentence about the key being read from HEAD. In `pipeline/templates/pipeline.toml`, replace the three comment lines above `# max_parallel = 1` with these four: `# Lowers this project's share of the daemon's -j; it never raises it. -j is a`, `# machine-wide budget shared across every registered project, and this key`, `# lowers this project alone. A project with no key takes its share. A value`, `# below 1 is reported and ignored.`. In `pipeline/daemon/main.py`, change the `-j` help string from `"agents in flight per project"` to `"agents in flight across every registered project"`. In `pipeline/cli/main.py`, add `help="agents in flight across every registered project"` to the `start` parser's `-j` argument and `help="agents in flight for this project"` to the `run` parser's `-j` argument. Commit as `docs(TICKET-094): document -j as a machine-wide budget`.
11. Run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py` from the worktree root, confirm neither reports a failure, and quote the last line of each in the thread entry. `tests/test_dispatch.py`, `tests/test_harness.py` and `tests/test_daemon.py` share one process with the module-level budget in `pipeline/daemon/supervisor.py`, so a stale-budget regression shows up there as an unrelated test starting no children.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide` exits 0 and its output names the test.
- `uv run --group dev pytest -q tests/test_dispatch.py -k "machine_cap_is_shared or quiet_project or rotates or unwatched_project"` exits 0 and selects the tests added in steps 1, 5, 6 and 8.
- `uv run --group dev pytest -q` exits 0 and prints no `failed`, so no test outside this ticket regressed against the branch point.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0; this ticket touches no hook.
- `grep -c "already per project" CLAUDE.md` prints `0`.
- `grep -c "per project" pipeline/daemon/main.py` prints `0`.
- `grep -n "machine_watch(wanted)" pipeline/daemon/supervisor.py` prints one line, so `serve()` declares its projects to the budget on every pass.

## Decisions

supersedes: DEC-069 -- its third ruling ("`-j` was already a per-project cap, and this key does not make it a machine-wide one") is the bug TICKET-094 reports. DEC-069's other rulings stand: a project's `max_parallel` still only LOWERS its own number, and the cap is still applied inside `tick()` rather than threaded through `run()` and `serve()` as a per-project argument.

**`-j` is one budget per dispatcher PROCESS, not per host.** The state is `_MACHINE` in `pipeline/daemon/supervisor.py`, so a `pipeline run` started beside a `pipeline start` gets its own `-j` and the two add up. A true host-wide cap needs shared state outside the process (a lock file, or the registry) and was not built. Do not describe `-j` to users as a host guarantee.

**The budget is consulted inside `tick()`, from module state, not passed in.** The reproduction `tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide` calls `tick()` once per project with two separate `inflight` dicts and no shared object. A budget threaded through `serve()` cannot see the total that test measures, and it would be the per-project argument DEC-069 refuses.

**A project's `inflight` dict is held by identity, never copied.** `reap()` and `tick()` mutate that dict in place; a stored count would go stale the moment a child finished, and the budget would keep charging for it until that project ticked again.

**Fair share divides `-j` among the projects with demand, not among the registered ones.** A project counts only if its last tick left a ticket the machine cap gave it no slot for, or it has been watched but not yet ticked. Dividing by the registered count would run 1 agent under `-j 3` with 5 registered projects, 4 of them idle. The cost is one pass of latency: a newly watched project is assumed to want work until its first tick says otherwise.

**Two prunes keep the budget from leaking, and both are load-bearing.** `machine_watch()` drops a project the dispatcher no longer watches; `serve()` calls it every pass and `run()` once. `machine_share()` drops an entry whose project directory no longer exists. Without the second, every test that calls `tick()` directly and then `shutil.rmtree`s its project leaves inflight records charged against the budget forever, and the next test in that process starts no children.

**`serve()` rotates which project ticks first each pass.** The share stops one project taking the whole cap, but whoever ticks first still gets first refusal on a slot that just freed. `turn` is a plain counter on `serve()`'s frame; nothing reads it back and no state file records it.

## Rollback

Revert the two commits from steps 4 and 7 (`fix(TICKET-094): share -j across projects as one machine-wide budget` and `fix(TICKET-094): rotate which project serve() ticks first`). That restores `tick()` and `serve()` to the per-project `-j` this ticket reports, and no stage's behaviour depends on the budget. The doc and test commits are inert on their own; revert them only to keep the tree honest. The symptom that warrants a rollback: a project stops starting tickets while the machine is idle, which means `machine_share()` is charging for children that no longer exist -- compare the `_MACHINE` entries against the live `states` in `serve()`.

## Thread

### 2026-08-29 03:52:45Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-29 · triage · result=ok

Reproduced. Added `tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide`:
two projects, each with 2 queued triage tickets, each ticked with `-j 1`. Total
inflight across both is 2, not 1.

```
AssertionError: machine cap is 1, but 2 children are inflight across 2 projects
```

Root cause: `serve()` (`pipeline/daemon/supervisor.py:1499`) calls `tick()`
once per registered project, passing the same `max_parallel` and that
project's own `inflight` dict each time. `_start_cap()`
(`pipeline/daemon/supervisor.py:1246`) only ever lowers one project's cap
against a project-local `max_parallel` key; nothing tracks or shares a
budget across projects. Not a regression -- this is `_start_cap`'s
documented behavior, just never checked against more than one project.

Fix needs a machine-wide cap held in `serve()`'s own state (shared across
the per-project `inflight` dicts) plus a fair-share policy (round-robin per
the ticket's suggestion) when it binds. This is a design change to the
daemon loop, not a small patch -- sending to planning rather than `chore`.

Committed on `ticket/094` as `9b63b3a`.

### 2026-08-29 04:39:59Z · triage · session · session=90c8456d-fc84-4702-bc06-0e78091048f1

`triage` ran as session `90c8456d-fc84-4702-bc06-0e78091048f1`
- replay: `claude --resume 90c8456d-fc84-4702-bc06-0e78091048f1`
- log: `.project/logs/TICKET-094-triage-90c8456d.log`
- cost: $0.41 of a $3 cap
- tokens: 5,784 out (841 thinking) · 46 in · 965,087 cache read · 40,637 cache write

### 2026-08-29 04:39:59Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- two projects each ticked with -j 1 run 2 inflight children, not 1

### 2026-08-29 · planning · result=ok

Planned. 11 steps over 7 files, ordered test-first.

The shape: `-j` becomes one budget held in `_MACHINE`, a module dict in
`pipeline/daemon/supervisor.py` that maps a project key to that project's own
`inflight` dict. `tick()` reads it through `machine_share()` and takes the
smaller of that share and `_start_cap()`. `serve()` declares its projects with
`machine_watch()` each pass and rotates which one ticks first.

Two findings shaped the design.

1. The repro test calls `tick()` twice with two separate `inflight` dicts and
   no shared object, so the budget must be module state that `tick()` consults
   by itself. An argument threaded through `serve()` cannot make that test
   pass, and DEC-069 refuses it anyway.
2. The share divides `-j` among projects with DEMAND, not among registered
   ones. A flat division would run 1 agent under `-j 3` with 5 registered
   projects, 4 of them idle.

This supersedes DEC-069's third ruling ("`-j` was already a per-project cap").
Its other two rulings hold and the plan complies with them.

Scope note for the implementer: `main` is 13 commits ahead (TICKET-086) and
`merging` rebases onto it. TICKET-086 rewrote `_start_cap()`'s docstring, so
the plan adds new functions below it and leaves that docstring alone.

### 2026-08-29 04:56:48Z · planning · session · session=2962c60b-478e-4380-8f43-d834744fa072

`planning` ran as session `2962c60b-478e-4380-8f43-d834744fa072`
- replay: `claude --resume 2962c60b-478e-4380-8f43-d834744fa072`
- log: `.project/logs/TICKET-094-planning-2962c60b.log`
- cost: $4.25 of a $10 cap
- tokens: 62,205 out (37,462 thinking) · 70 in · 2,824,171 cache read · 127,748 cache write

### 2026-08-29 04:56:48Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ planned a per-process machine budget in tick() plus demand-based share and serve() rotation

### 2026-08-29 06:01:40Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide` fails as required
```
     inflights = [{} for _ in projects]
        for d, inflight in zip(projects, inflights):
            supervisor.tick(d, harness("fake"), inflight, max_parallel)
    
        total = sum(len(i) for i in inflights)
        for d in projects:
            shutil.rmtree(d, ignore_errors=True)
>       assert total <= max_parallel, \
            f"machine cap is {max_parallel}, but {total} children are inflight " \
            f"across {len(projects)} projects"
E       AssertionError: machine cap is 1, but 2 children are inflight across 2 projects
E       assert 2 <= 1

tests/test_dispatch.py:712: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: triage (sonnet, batch) pid 2121618 -> TICKET-001-triage-97af4b3d.log
  start TICKET-001: triage (sonnet, batch) pid 2121640 -> TICKET-001-triage-3c351181.log
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================

```
- ok: `tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide` fails on base `main` too -- the bug is not already fixed upstream
```
rojects
E       assert 2 <= 1

tests/test_dispatch.py:712: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: triage (sonnet, batch) pid 2121736 -> TICKET-001-triage-91b2a827.log
  start TICKET-001: triage (sonnet, batch) pid 2121758 -> TICKET-001-triage-1c2f4e79.log
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.53s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-pc9ltwz8/base
      Built pipeline @ file:///tmp/pipeline-base-pc9ltwz8/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```
- plan step names no declared file: "1. what `-j` has left after the OTHER projects' inflight children;" -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. an equal share of `-j` among the projects with demand -- this one, plus every other whose last tick left a ticket it had no slot for. A quiet project is not counted, so one busy project still reaches `-j`. `inflight` is stored by identity: `reap()` and `tick()` mutate that same dict, so the count read here is always current. An entry whose project directory is gone is dropped -- nothing will ever tick it again. """ key = str(project) entry = _MACHINE.setdefault(key, {"inflight": inflight, "want": True}) entry["inflight"] = inflight for k in [k for k in _MACHINE if k != key and not Path(k).is_dir()]: del _MACHINE[k] others = sum(len(e["inflight"]) for k, e in _MACHINE.items() if k != key) rivals = 1 + sum(1 for k, e in _MACHINE.items() if k != key and e["want"]) share = -(-max_parallel // rivals)      # ceil, so a share is never 0 return max(0, min(max_parallel - others, share)) def machine_demand(project: Path, want: bool) -> None: """Record whether `project` had a ticket the machine cap gave no slot.""" entry = _MACHINE.get(str(project)) if entry is not None: entry["want"] = want' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-29 06:01:41Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- plan step names no declared file: "1. what `-j` has left after the OTHER projects' inflight children;" -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. an equal share of `-j` among the projects with demand -- this one, plus every other whose last tick left a ticket it had no slot for. A quiet project is not counted, so one busy project still reaches `-j`. `inflight` is stored by identity: `reap()` and `tick()` mutate that same dict, so the count read here is always current. An entry whose project directory is gone is dropped -- nothing will ever tick it again. """ key = str(project) entry = _MACHINE.setdefault(key, {"inflight": inflight, "want": True}) entry["inflight"] = inflight for k in [k for k in _MACHINE if k != key and not Path(k).is_dir()]: del _MACHINE[k] others = sum(len(e["inflight"]) for k, e in _MACHINE.items() if k != key) rivals = 1 + sum(1 for k, e in _MACHINE.items() if k != key and e["want"]) share = -(-max_parallel // rivals)      # ceil, so a share is never 0 return max(0, min(max_parallel - others, share)) def machine_demand(project: Path, want: bool) -> None: """Record whether `project` had a ticket the machine cap gave no slot.""" entry = _MACHINE.get(str(project)) if entry is not None: entry["want"] = want' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-08-29 · planning · result=ok

Re-planned after the Tier A structural failure. One edit to `## Plan`.

Both gate findings came from the code pasted into step 2:

```
plan step names no declared file: "1. what `-j` has left after the OTHER projects' inflight children;"
```

`PLAN_STEP_RE` in `pipeline/core/gate.py:45` matches a number at any
indentation, so the two numbered lines inside `machine_share()`'s docstring
parsed as plan steps, each naming no declared file. Those two limits now read
as prose in the same docstring. Nothing else moved: 11 steps, the same 7
files, the same acceptance criteria, the same `supersedes: DEC-069`.

I re-ran the gate's own plan scan over the edited section, using
`gate.PLAN_STEP_RE`, `ticket._fenced()` and `gate._cites()`:

```
steps: 11
findings: []
```

`## Digest` gains one line naming that rule, so a later re-plan does not paste
the numbering back in.

### 2026-08-29 06:04:16Z · planning · session · session=47d6cbfe-f62f-44f4-a421-6319bf804536

`planning` ran as session `47d6cbfe-f62f-44f4-a421-6319bf804536`
- replay: `claude --resume 47d6cbfe-f62f-44f4-a421-6319bf804536`
- log: `.project/logs/TICKET-094-planning-47d6cbfe.log`
- cost: $1.42 of a $10 cap
- tokens: 10,653 out (4,718 thinking) · 40 in · 1,018,407 cache read · 63,988 cache write

### 2026-08-29 06:04:16Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-planned: removed the numbered list inside step 2's code block that Tier A read as two fileless steps; plan is unchanged otherwise

### 2026-08-29 06:17:33Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide` fails as required
```
     inflights = [{} for _ in projects]
        for d, inflight in zip(projects, inflights):
            supervisor.tick(d, harness("fake"), inflight, max_parallel)
    
        total = sum(len(i) for i in inflights)
        for d in projects:
            shutil.rmtree(d, ignore_errors=True)
>       assert total <= max_parallel, \
            f"machine cap is {max_parallel}, but {total} children are inflight " \
            f"across {len(projects)} projects"
E       AssertionError: machine cap is 1, but 2 children are inflight across 2 projects
E       assert 2 <= 1

tests/test_dispatch.py:712: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: triage (sonnet, batch) pid 2267572 -> TICKET-001-triage-ba85104e.log
  start TICKET-001: triage (sonnet, batch) pid 2267594 -> TICKET-001-triage-d9db4eba.log
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================

```
- ok: `tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide` fails on base `main` too -- the bug is not already fixed upstream
```
rojects
E       assert 2 <= 1

tests/test_dispatch.py:712: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: triage (sonnet, batch) pid 2267818 -> TICKET-001-triage-8d0cf740.log
  start TICKET-001: triage (sonnet, batch) pid 2267845 -> TICKET-001-triage-d621861f.log
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.54s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-8yu7xjr6/base
      Built pipeline @ file:///tmp/pipeline-base-8yu7xjr6/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 15ms

```

### 2026-08-29 · plan-validation · result=ok

**Tier B: PASS.** Eight items, each scored against the code.

long: the stage owes one verdict per item, and the risk it found needs its
evidence quoted.

1. Root cause -- pass. `serve()` (`pipeline/daemon/supervisor.py:1499`) gives
   each project `states[key]`, its own inflight dict, and `tick()` compares
   `len(inflight) >= cap` (`:1279`) against that one dict. Nothing sums
   children across projects, so `-j` bounds a project, not the dispatcher. The
   plan makes `tick()` measure the cap against a process-wide total. It fixes
   the cause, not the test.
2. Decision conflict -- pass. DEC-069's first two rulings hold: `machine_share()`
   is consulted inside `tick()`, and `run()`/`serve()` gain no per-project
   number (`machine_watch()` passes projects, no cap). The third ruling is
   superseded, and `## Decisions` line 1 matches `SUPERSEDES_RE`
   (`pipeline/core/ticket.py:298`). DEC-086 binds step 6 and the plan complies
   (`class Stop(BaseException)`; `serve()` catches `Exception` at `:1502`).
   DEC-086 is not on this branch -- it arrives with the rebase onto `main`; its
   ruling is verified directly in the code instead.
3. Scope -- pass. Steps 1-8 map to criteria 1, 2 and 7; steps 9-10 to criteria
   5 and 6. Two doc edits carry no criterion of their own: `README.md`'s
   `## Concurrency` and `pipeline/templates/pipeline.toml`. Minor.
4. Falsifiable criteria -- pass. Criterion 1 fails today with
   `AssertionError: machine cap is 1, but 2 children are inflight across 2 projects`.
   Criterion 2 exits 5, not 0, if the four tests are absent. Criterion 5 prints
   `1` today and `0` after step 9. Criterion 7 prints nothing if `serve()` is
   unwired.
5. No research left -- pass. Every anchor the plan names exists at the line it
   implies: `cap = _start_cap(project, max_parallel) if tickets else max_parallel`
   (`:1277`), `if stopping() or len(inflight) >= cap:` (`:1279`),
   `inflight: dict[str, dict] = {}` (`:1412`), the release loop (`:1482`),
   `worked = False` (`:1490`), `for key, proj in wanted.items():` (`:1491`),
   `stale, moved = _source_watcher(), None` (`:1465`), and
   `test_a_merged_dispatcher_change_ends_the_daemon_loop_too`
   (`tests/test_dispatch.py:970`), whose shape step 6 reuses.
6. Riskiest step -- pass. Step 3: every project's start path runs through the
   new cap, and a stale budget entry starves a project with no error.
   `## Rollback` names the two commits to revert, the symptom ("a project stops
   starting tickets while the machine is idle") and the diagnostic (`_MACHINE`
   against `states`). The rebase hazard has its own fallback: step 2 forbids
   touching `_start_cap()`'s docstring. I confirmed `git diff HEAD...main`
   touches that docstring and `run()`'s `tick()` call, and neither `tick()`'s
   body nor `serve()`.
7. Regression surface -- pass. Five existing tests call `supervisor.tick()`
   directly (`tests/test_dispatch.py:587,611,633,656,680,737`) and every one
   ends in `shutil.rmtree`, so `machine_share()`'s gone-directory prune clears
   the entry before the next test sums `others`. The prune runs before that sum
   in the plan's code, which is what makes it hold. Criterion 3 covers it.
8. Blast radius -- pass. `class: feature`, 11 steps over 7 files, of which 4
   are one-line doc or help-string edits. None of the 7 is in `machine.FENCED`
   (`pipeline/core/machine.py:43`): `pipeline/templates/pipeline.toml` is not
   `.project/pipeline.toml`.

**Risk, not a finding against the plan.** A project `serve()` lists in `wanted`
but never ticks keeps its share forever. `machine_watch(wanted)` seeds
`want: True` for every wanted key, and only `machine_demand()` -- called from
`tick()` -- clears it; a project whose `registry.lock()` returns None hits
`continue` at `:1495` and is never ticked. With `-j 4`, four registered
projects and three locked by another dispatcher, the one project this
dispatcher runs is capped at 1 forever. No plan step or test covers it. It only
lowers parallelism, so no acceptance criterion breaks. Worth a
`machine_demand(proj, False)` on that `continue`, or a note in `## Decisions`.

**unverified:** the full suite under the new module-level `_MACHINE`. I read
every direct `tick()` call site instead of running it. I would have run
`uv run --group dev pytest -q`; step 11 and criterion 3 run it.

### 2026-08-29 06:22:32Z · plan-validation · session · session=b39472af-b62a-4291-a96b-073723e8f270

`plan-validation` ran as session `b39472af-b62a-4291-a96b-073723e8f270`
- replay: `claude --resume b39472af-b62a-4291-a96b-073723e8f270`
- log: `.project/logs/TICKET-094-plan-validation-b39472af.log`
- cost: $1.81 of a $3 cap
- tokens: 23,403 out (13,663 thinking) · 34 in · 939,514 cache read · 75,115 cache write

### 2026-08-29 06:22:32Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B pass: root cause, decisions, scope, criteria, riskiest step and blast radius all check out; one noted risk (a project serve() lists but never locks holds its share forever)

### 2026-08-29 06:25:14Z · human · approval · by=chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified the share arithmetic: with -j 3 and two busy projects, ceil(3/2)=2 but the second sees others=2 and takes min(3-2,2)=1, so the total is 3 and never 4; a quiet project is excluded from rivals so one busy project still reaches full -j; run() watches one project so rivals=1 and today's behaviour is unchanged. Nothing fenced -- pipeline/templates/pipeline.toml is not .project/pipeline.toml. Design note accepted rather than re-planned: the budget lives in a module-level _MACHINE dict shared by the test process, where serve() could have owned it in states and passed the share as max_parallel with no global; step 11 acknowledges the shared-process risk and step 8 pins the two prunes. Expect a rebase against 086, which changed run() and the tick call site.

**approved by chezzijr (via Claude Code, while away; this session also filed the ticket -- not an independent gate). Verified the share arithmetic: with -j 3 and two busy projects, ceil(3/2)=2 but the second sees others=2 and takes min(3-2,2)=1, so the total is 3 and never 4; a quiet project is excluded from rivals so one busy project still reaches full -j; run() watches one project so rivals=1 and today's behaviour is unchanged. Nothing fenced -- pipeline/templates/pipeline.toml is not .project/pipeline.toml. Design note accepted rather than re-planned: the budget lives in a module-level _MACHINE dict shared by the test process, where serve() could have owned it in states and passed the share as max_parallel with no global; step 11 acknowledges the shared-process risk and step 8 pins the two prunes. Expect a rebase against 086, which changed run() and the tick call site.**

### 2026-08-29 06:26:05Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide` fails as required
```
     inflights = [{} for _ in projects]
        for d, inflight in zip(projects, inflights):
            supervisor.tick(d, harness("fake"), inflight, max_parallel)
    
        total = sum(len(i) for i in inflights)
        for d in projects:
            shutil.rmtree(d, ignore_errors=True)
>       assert total <= max_parallel, \
            f"machine cap is {max_parallel}, but {total} children are inflight " \
            f"across {len(projects)} projects"
E       AssertionError: machine cap is 1, but 2 children are inflight across 2 projects
E       assert 2 <= 1

tests/test_dispatch.py:748: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: triage (sonnet, batch) pid 2409289 -> TICKET-001-triage-69861a2b.log
  start TICKET-001: triage (sonnet, batch) pid 2409312 -> TICKET-001-triage-0b617126.log
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.44s ===============================

```
- ok: `tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide` fails on base `main` too -- the bug is not already fixed upstream
```
rojects
E       assert 2 <= 1

tests/test_dispatch.py:748: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: triage (sonnet, batch) pid 2409459 -> TICKET-001-triage-6386696e.log
  start TICKET-001: triage (sonnet, batch) pid 2409483 -> TICKET-001-triage-d8312945.log
=========================== short test summary info ============================
FAILED tests/test_dispatch.py::test_the_daemons_max_parallel_is_not_machine_wide
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.55s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-rf5xse23/base
      Built pipeline @ file:///tmp/pipeline-base-rf5xse23/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 16ms

```

### 2026-08-29 06:26:05Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-08-29 · implementing · todo

**implementing: todo list**

1. [ ] step 1: add `test_the_machine_cap_is_shared_when_both_projects_have_work`, watch it fail on `AttributeError`
2. [ ] step 2: add `_MACHINE`/`machine_watch()`/`machine_share()`/`machine_demand()` to supervisor.py
3. [ ] step 3: wire the budget into `tick()`
4. [ ] step 4: call `machine_watch()` from `run()` and `serve()`; run tests; commit
5. [ ] step 5: add `test_a_quiet_project_does_not_shrink_a_busy_ones_share`; commit
6. [ ] step 6: add `test_serve_rotates_which_project_ticks_first`, watch it fail
7. [ ] step 7: rotate project order in `serve()`; run tests; commit
8. [ ] step 8: add `test_an_unwatched_project_stops_holding_machine_slots`; commit
9. [ ] step 9: update CLAUDE.md gotcha
10. [ ] step 10: update README.md, pipeline.toml, main.py, cli/main.py help text; commit
11. [ ] step 11: run full test suite + dangerous-commands hook, quote last lines

### 2026-08-29 · implementing · result=ok

**implementing: done, all 11 plan steps landed**

Todo, updated:
1. [x] step 1: `test_the_machine_cap_is_shared_when_both_projects_have_work` added, failed RED on `AttributeError: module 'pipeline.daemon.supervisor' has no attribute 'machine_watch'`
2. [x] step 2: `_MACHINE`/`machine_watch()`/`machine_share()`/`machine_demand()` added to `pipeline/daemon/supervisor.py`, code pasted exactly as planned
3. [x] step 3: `tick()` wired to `machine_share()`/`machine_demand()`
4. [x] step 4: `machine_watch()` called from `run()` and `serve()`; committed `ed76c0b`
5. [x] step 5: `test_a_quiet_project_does_not_shrink_a_busy_ones_share` added, passed first run (behaviour from step 2-4); committed `41a5658`
6. [x] step 6: `test_serve_rotates_which_project_ticks_first` added, failed RED: `pass 2 must not tick the same project first: [..p1, p2, p1, p2]`
7. [x] step 7: rotation added to `serve()`; all selected tests pass; committed `70da57a`
8. [x] step 8: `test_an_unwatched_project_stops_holding_machine_slots` added, passed first run; committed `7b7fc5a`
9. [x] step 9: `CLAUDE.md` gotcha rewritten
10. [x] step 10: `README.md`, `pipeline/templates/pipeline.toml`, `pipeline/daemon/main.py`, `pipeline/cli/main.py` help text updated; committed `92daa43`
11. [x] step 11: full suite and hook run

`uv run --group dev pytest -q` last line: `483 passed in 37.93s`.
`./pipeline/hooks/test_dangerous_commands.py` last line: `guard: all passed`.

Acceptance criteria verified: `grep -c "already per project" CLAUDE.md` -> `0`; `grep -c "per project" pipeline/daemon/main.py` -> `0`; `grep -n "machine_watch(wanted)" pipeline/daemon/supervisor.py` -> one line.

No deviation from the plan.

### 2026-08-29 06:31:28Z · implementing · session · session=7a920ee5-dfbe-4e2a-9f93-866708eb49ac

`implementing` ran as session `7a920ee5-dfbe-4e2a-9f93-866708eb49ac`
- replay: `claude --resume 7a920ee5-dfbe-4e2a-9f93-866708eb49ac`
- log: `.project/logs/TICKET-094-implementing-7a920ee5.log`
- cost: $1.49 of a $8 cap
- tokens: 20,844 out (1,489 thinking) · 130 in · 4,741,037 cache read · 82,202 cache write

### 2026-08-29 06:31:28Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented the machine-wide -j budget per the 11-step plan; all tests and the guard pass

### 2026-08-29 · review · result=ok

**review: PASS, no blocking findings**

Reviewed the delta `main..HEAD`: 6 commits, 251 insertions. Re-ran every
acceptance criterion: `483 passed in 34.44s`, `guard: all passed`, the repro
test `1 passed in 0.16s`, the four new tests `4 passed, 76 deselected`,
`grep -c "already per project" CLAUDE.md` -> `0`, `grep -c "per project"
pipeline/daemon/main.py` -> `0`, and `grep -n "machine_watch(wanted)"` -> one
line at `:1585`. The code matches `## Plan` steps 1-10. The tree stayed clean.

Non-blocking findings:

1. minor -- rotation does not hand over a freed slot. `reap()` runs inside the
   owning project's own `tick()` (`pipeline/daemon/supervisor.py:1350`), so a
   rival ticking first still counts the finished-but-unreaped child in
   `others` (`:1352`). Under `-j 1` with two busy projects, p1 reaps and
   refills in the same tick, and p2 keeps share 0.
2. minor -- `want` overstates demand. `tick()` sets `want` at `:1359` before it
   knows any ticket is startable, so a project whose tickets are all parked
   claims a rival share for one pass. The next tick clears it.
3. minor -- the Tier B gap already in `## Summary` stands: `serve()` seeds
   `want: True` for a project it fails to lock, and nothing clears it.

Findings I dropped after refuting them:

- `ZeroDivisionError` on the rotation line: the conditional expression binds
  looser than `+`, so `len(keys)` runs only when `keys` is truthy (`:1588`).
- `_MACHINE` leaking across tests: `machine_share()` drops entries whose
  directory is gone (`:1328`), and `machine_watch()` drops unwatched keys.
- key mismatch between `machine_watch(wanted)` and `machine_share()`:
  `wanted = {str(p): p ...}` at `:1576`, and `tick()` receives that same Path.

### 2026-08-29 06:36:18Z · review · session · session=be46b420-e12d-423a-9a70-fd45a22c7f2a

`review` ran as session `be46b420-e12d-423a-9a70-fd45a22c7f2a`
- replay: `claude --resume be46b420-e12d-423a-9a70-fd45a22c7f2a`
- log: `.project/logs/TICKET-094-review-be46b420.log`
- cost: $1.76 of a $5 cap
- tokens: 17,974 out (11,549 thinking) · 52 in · 1,351,062 cache read · 63,745 cache write

### 2026-08-29 06:36:18Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed the 6-commit delta: no blocking findings; 483 passed, guard all passed, every acceptance criterion re-run

### 2026-08-29 06:36:54Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-29 06:36:55Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/094


Current branch ticket/094 is up to date.
Already up to date.
Updating ea58ca9..92daa43
Fast-forward
 CLAUDE.md                        |  15 ++--
 README.md                        |  14 ++--
 pipeline/cli/main.py             |   4 +-
 pipeline/daemon/main.py          |   2 +-
 pipeline/daemon/supervisor.py    |  77 ++++++++++++++++++--
 pipeline/templates/pipeline.toml |   7 +-
 tests/test_dispatch.py           | 152 +++++++++++++++++++++++++++++++++++++++
 7 files changed, 251 insertions(+), 20 deletions(-)

```

### 2026-08-29 06:36:55Z · merging · decision

decision recorded as `DEC-094`
