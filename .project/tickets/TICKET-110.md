---
id: TICKET-110
stage: done
class: bugfix
branch: ticket/110
test_file: tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active
files_declared:
- README.md
- pipeline/cli/main.py
- pipeline/daemon/supervisor.py
- tests/test_cli.py
- tests/test_dispatch.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 10
  plan_files: 5
  no_result: 0
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: df882e01-c376-4f1b-8a58-474e60b1c873
  replay: claude --resume df882e01-c376-4f1b-8a58-474e60b1c873
  log: .project/logs/TICKET-110-review-df882e01.log
  cost_usd: 1.3229965000000006
approved_by: claude-for-chezzijr
approved_at: '2026-09-03T16:45:15.602827+00:00'
---

## Summary

Fixed: `pipeline resume` rewrote `stage` under a live lease with no check;
the dispatcher then escalated the running stage for the change.

Implemented as planned, no deviation. Three commits: `5534da5` (`cmd_resume`
refuses when `t.lease_active() and holder_alive(holder)`, names the holder
on stderr, mutates nothing; `--force` takes the ticket anyway; a live lease
with a dead holder pid needs no flag, matching `start()`), `612a031`
(`README.md` documents `--force`), `a900757` (the tamper escalation in
`pipeline/daemon/supervisor.py:1230` now reads "frontmatter changed while
`<stage>` held the ticket" -- what the snapshot diff shows, not who wrote
it -- and the test asserting the old wording is renamed to
`test_a_control_field_rewritten_mid_run_is_caught`).

Five files touched: `pipeline/cli/main.py`, `pipeline/daemon/supervisor.py`,
`tests/test_cli.py`, `tests/test_dispatch.py`, `README.md`. Four new tests
plus the triage repro (`test_resume_refuses_a_ticket_whose_lease_is_active`)
all pass. Full suite: 536 passed, 0 failed (baseline was 531 passed + 1
failed). `./pipeline/hooks/test_dangerous_commands.py` exits 0. Both grep
criteria on `supervisor.py` hold: 0 occurrences of "edited dispatcher-owned
frontmatter", 1 of "frontmatter changed while".

Review pass 1: no blocking findings. The reviewer re-ran every acceptance
criterion (`536 passed in 62.53s`, the six named tests `6 passed`, guard
exit 0, greps `0` and `1`) and refuted both findings it raised: every path
that parks a ticket for a human releases the lease first, and
`cmd_approve` / `cmd_reject` refuse outside a gate stage. One non-blocking
nit stands: the README usage block (README.md:74-80) does not list
`--force`, which is documented at README.md:491-497 instead.

## Reproduction

Test: `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active`

Command: `uv run --group dev pytest -q tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active`

Output:

    AssertionError: resume rewrote `stage` while `planning` held the lease: stage='triage'
    assert 'triage' != 'triage'

expect: resume rewrote `stage` while `planning` held the lease: stage='triage'

`cmd_resume` (`pipeline/cli/main.py:380`) sets `t.stage = args.stage` and
calls `t.release_lease()` with no `lease_active()` check anywhere, unlike
`cmd_note`, which checks it (`pipeline/cli/main.py:331`) and reports the
holder instead of proceeding blind.

## Digest

- `cmd_resume` (`pipeline/cli/main.py:358`) rewrites `stage`, `counters` and the lease with no lease check anywhere. `cmd_note` (`pipeline/cli/main.py:322`) reads `t.lease_active()` and names the holder in stdout; that is the pattern to copy.
- `holder_alive(holder)` (`pipeline/daemon/supervisor.py:51`) parses the pid out of `f"{stage}-{os.getpid()}"` and returns False only for a pid that is gone. It is fail-safe: an unparseable holder and a `PermissionError` both read as alive.
- `start()` (`pipeline/daemon/supervisor.py:818`) parks a ticket only when `t.lease_active() and holder_alive(...)` -- "a live lease held by a dead pid is a daemon that was killed, not work in progress". `cmd_resume` uses the same pair, so a killed daemon does not park the operator for the 30-minute expiry.
- `pipeline/cli/main.py:29` already reads `from pipeline.daemon.supervisor import run`; add `holder_alive` to that import.
- The tamper escalation is `pipeline/daemon/supervisor.py:1230`. `grep -rn 'edited dispatcher-owned frontmatter'` returns exactly two lines: that one and `tests/test_dispatch.py:157`, inside `test_an_agent_that_rewrote_stage_is_still_caught` (line 135, spawn stage `plan-validation`). No code parses an escalation reason: `pipeline/tui/app.py:195` selects by `kind == "escalation"` and `pipeline/cli/metrics.py:446` counts rows.
- Entry points: the `resume` argparse row is `pipeline/cli/main.py:747`; README documents `resume` at README.md:74-78 (usage block) and README.md:477-489 (the recovery table and the `--note` paragraph).
- The `resume` row declares `id`, `--stage`, `--grant`, `--reset`, `--note` and no `--force`, and `main()` declares no top-level `--force`. So `args.force` does not exist until step 4 adds it: any earlier step that reads it raises `AttributeError: 'Namespace' object has no attribute 'force'`, and any earlier `pipeline resume --force` dies on argparse's `unrecognized arguments: --force`. Other subcommands (`skills`, `register`) carry their own `--force`; they share no namespace with `resume`.
- Difference from the rejected plan: step 4 now declares `p.add_argument("--force", ...)` on the `resume` row and inserts the refusal, in that order; step 7 documents the flag in `README.md` only. The gate rejected exactly one item -- steps 4 and 5 read `args.force` while step 7 declared it -- and nothing else moved. Step 5's expectation now holds, step 6 fails on its README assertion instead of on `--help`, and step 7 commits `README.md` with `tests/test_cli.py` rather than `pipeline/cli/main.py` too.
- Gotcha: the committed repro takes the lease as `planning-1`. `os.kill(1, 0)` raises `PermissionError` for a normal user and succeeds for root, so `holder_alive("planning-1")` is True either way and the refusal fires under both.
- Gotcha: a forced resume releases the lease while the child still runs, so that child's `_finish()` still escalates on the frontmatter diff. The reworded escalation is what makes that outcome readable instead of an accusation.
- Test helpers: `cli(project, *args)` (`tests/test_cli.py:22`) runs a real `python -m pipeline` process; `tests/test_daemon.py:255` is the existing dead-pid recipe (`subprocess.Popen([sys.executable, "-c", "pass"])` then `.wait()`); tests read the last thread entry as `t.thread()[-1].text`.
- `tests/test_cli.py` already imports `os`, `shutil`, `subprocess`, `sys`, `tempfile`, `Path`, `ROOT` and `Ticket`; the new tests need no new import.

## Decisions checked

- DEC-080 -- `resume`'s `--note ""` refusal "sits above `t.stage = args.stage`, so a refused resume leaves the stage where it was". This plan puts the lease refusal in the same place, for the same reason.
- DEC-051 -- `--grant` subtracts and `--reset` zeroes; it also records that `resume` emits no event to `events.db`. This plan adds a flag and changes neither.
- DEC-100 -- a `CONTROL_FIELDS` edit escalates the ticket instead of being silently reverted. That escalation is what step 9 rewords; it is not removed or weakened.
- DEC-047 -- counters are `CONTROL_FIELDS` restored from the pre-spawn snapshot. That snapshot diff is the evidence the escalation cites, and the reason it cannot name an author.
- grep terms used against `.project/decisions/`: `lease`, `lease_active`, `release_lease`, `holder_alive`, `dead pid`, `lease_expiries`, `resume`, `frontmatter`, `dispatcher-owned`, `CONTROL_FIELDS`, `tamper`. No record covers the dead-pid lease rule or the wording of the tamper escalation.

## Plan

1. Record the baseline: run `uv run --group dev pytest -q` from the worktree root and keep the summary line; today the only failure is the triage repro `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active`.
2. Add three tests to `tests/test_cli.py` immediately after line 226 (below `test_resume_refuses_a_ticket_whose_lease_is_active`), then run `uv run --group dev pytest -q tests/test_cli.py` and watch all three fail; the first fails on `assert r.returncode != 0`, because resume exits 0 today:

        def test_resume_names_the_lease_holder_when_it_refuses():
            """A refused resume mutates nothing and says who holds the ticket,
            the way `pipeline note` already reports a live lease."""
            d = Path(tempfile.mkdtemp())
            cli(d, "new", "t")
            path = d / ".project/tickets/TICKET-001.md"
            holder = f"planning-{os.getpid()}"          # this process: alive
            t = Ticket.load(path)
            t.take_lease(holder)
            t.save()

            r = cli(d, "resume", "TICKET-001", "--stage", "triage")

            assert r.returncode != 0, (r.returncode, r.stdout)
            assert holder in r.stderr, r.stderr
            after = Ticket.load(path)
            assert after.stage != "triage", after.stage
            assert after.lease.get("holder") == holder, after.lease
            shutil.rmtree(d)


        def test_resume_force_takes_a_ticket_whose_lease_is_active():
            """`--force` is the escape hatch for a stage the operator knows is
            stuck: it takes the ticket, releases the lease, and records in the
            thread that a human did it."""
            d = Path(tempfile.mkdtemp())
            cli(d, "new", "t")
            path = d / ".project/tickets/TICKET-001.md"
            holder = f"planning-{os.getpid()}"
            t = Ticket.load(path)
            t.take_lease(holder)
            t.save()

            r = cli(d, "resume", "TICKET-001", "--stage", "triage", "--force")

            assert r.returncode == 0, r.stderr
            after = Ticket.load(path)
            assert after.stage == "triage", after.stage
            assert after.lease == {"holder": None, "expires": None}, after.lease
            assert holder in after.thread()[-1].text, after.thread()[-1].text
            assert "forced" in after.thread()[-1].text, after.thread()[-1].text
            shutil.rmtree(d)


        def test_resume_treats_a_lease_held_by_a_dead_pid_as_free():
            """`start()` already reads a live lease with a dead holder as a
            killed daemon, not work in progress. Resume must not park the
            operator for the full 30-minute expiry over one, so this case
            needs no `--force`."""
            dead = subprocess.Popen([sys.executable, "-c", "pass"])
            dead.wait()
            d = Path(tempfile.mkdtemp())
            cli(d, "new", "t")
            path = d / ".project/tickets/TICKET-001.md"
            t = Ticket.load(path)
            t.take_lease(f"planning-{dead.pid}")
            t.save()

            r = cli(d, "resume", "TICKET-001", "--stage", "triage")

            assert r.returncode == 0, r.stderr
            assert Ticket.load(path).stage == "triage", "a dead holder parked the operator"
            shutil.rmtree(d)

3. Add `holder_alive` to the supervisor import in `pipeline/cli/main.py`, changing line 29 to `from pipeline.daemon.supervisor import holder_alive, run`.
4. Declare the flag and the refusal that reads it in one step, in `pipeline/cli/main.py`, so no later step runs a `resume` whose option argparse does not have: first append `p.add_argument("--force", action="store_true", help="resume even while a stage holds a live lease; the running stage keeps going and the dispatcher escalates the ticket when it finishes")` to the `resume` parser row (line 747, which today declares `id`, `--stage`, `--grant`, `--reset`, `--note` and no `--force`), then insert the block below directly under `t = Ticket.find(project, args.id)` in `cmd_resume` (line 363) -- above the `grants` loop and above every mutation, per DEC-080:

        holder = (t.lease or {}).get("holder")
        # A live lease whose holder pid is gone is a killed daemon, not work in
        # progress -- `start()` reads it the same way. Rewriting `stage` under a
        # LIVE one makes `_finish()` escalate the ticket for the human's edit.
        live = t.lease_active() and holder_alive(holder)
        if live and not args.force:
            die(f"{t.id}: `{t.stage}` holds a live lease (`{holder}`). "
                f"Resuming now rewrites `stage` under a running stage, and the "
                f"dispatcher escalates the ticket for that change when the "
                f"stage finishes. Wait for it, or `pipeline resume {t.id} "
                f"--stage {args.stage} --force` to take the ticket anyway.")

5. Record the override on the way out in `pipeline/cli/main.py`: below `note += f", granted {', '.join(granted)}"` in `cmd_resume`, add the two lines below, and add `+ (" (forced past a live lease)" if live else "")` to the final `print` of `cmd_resume`; then run `uv run --group dev pytest -q tests/test_cli.py`, expect step 2's three tests and the repro to pass, and commit `pipeline/cli/main.py` with `tests/test_cli.py` as `fix: refuse resume under a live lease, --force to override (TICKET-110)`:

        if live:
            note += f" (forced past a live lease held by `{holder}`)"

6. Add the flag test below to `tests/test_cli.py` beside `test_resume_help_and_readme_name_the_note_flag` (line 276), then run `uv run --group dev pytest -q tests/test_cli.py::test_resume_help_and_readme_name_the_force_flag` and watch it fail on the README assertion; its `--help` assertion already passes, because step 4 declared the flag:

        def test_resume_help_and_readme_name_the_force_flag():
            r = subprocess.run([sys.executable, "-m", "pipeline", "resume", "--help"],
                                cwd=ROOT, capture_output=True, text=True)
            assert "--force" in r.stdout, r.stdout
            readme = (Path(ROOT) / "README.md").read_text()
            assert "resume TICKET-017 --stage planning --force" in readme, readme

7. Document the flag in `README.md` by inserting the paragraph below after the `--note` paragraph that ends "which is why the note rides on `resume`." (line 489) -- keep the backticked command on one unwrapped line, since `test_resume_help_and_readme_name_the_force_flag` matches it as a substring -- then run `uv run --group dev pytest -q tests/test_cli.py`, expect every test in that file to pass, and commit `README.md` with `tests/test_cli.py` as `docs: document resume --force (TICKET-110)`:

        `resume` refuses a ticket whose lease is live and whose holder process is
        still running: rewriting `stage` under a running stage makes the dispatcher
        escalate the ticket for a change *you* made. It names the holder and stops.
        `pipeline resume TICKET-017 --stage planning --force` takes the ticket anyway
        -- for a stage you know is stuck. Expect that escalation when it finishes.
        A lease whose holder process is already gone is not a live lease: a daemon
        that was killed needs no `--force`.

8. Rewrite the wording assertion in `tests/test_dispatch.py`: rename `test_an_agent_that_rewrote_stage_is_still_caught` (line 135) to `test_a_control_field_rewritten_mid_run_is_caught`, add to its docstring that the snapshot diff proves the change and not its author, replace the assertion at line 157 with the two lines below, and run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_control_field_rewritten_mid_run_is_caught` to watch it fail on the old wording:

        assert ("frontmatter changed while `plan-validation` held the ticket"
                in t.thread()[-1].text), t.thread()[-1].text

9. Reword the escalation in `pipeline/daemon/supervisor.py`, replacing the `escalate(...)` call at line 1230 with the text below; then run `uv run --group dev pytest -q tests/test_dispatch.py::test_a_control_field_rewritten_mid_run_is_caught`, expect it to pass, and commit `pipeline/daemon/supervisor.py` with `tests/test_dispatch.py` as `fix: word the tamper escalation as what the snapshot diff shows (TICKET-110)`:

        escalate(t, f"frontmatter changed while `{stage}` held the ticket: "
                    + ", ".join(f"{k}={v!r}" for k, v in tampered.items())
                    + " -- the snapshot diff shows the change, not its author"
                      " (a `pipeline resume --force` during the run does this too)", emit)

10. Verify the whole change: run `uv run --group dev pytest -q` and `./pipeline/hooks/test_dangerous_commands.py`; the suite must report no failure that step 1's baseline did not, with the repro now passing, and the guard must exit 0. The five files this ticket changes are `pipeline/cli/main.py`, `pipeline/daemon/supervisor.py`, `tests/test_cli.py`, `tests/test_dispatch.py` and `README.md`.

## Acceptance criteria

- `uv run --group dev pytest -q tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active` exits 0 -- the triage repro, unmodified.
- `tests/test_cli.py::test_resume_names_the_lease_holder_when_it_refuses` passes: resume exits non-zero and its stderr names the holder.
- `tests/test_cli.py::test_resume_force_takes_a_ticket_whose_lease_is_active` passes: `--force` sets `stage` to `triage`, releases the lease, and the thread note names the holder.
- `tests/test_cli.py::test_resume_treats_a_lease_held_by_a_dead_pid_as_free` passes: a live lease with a dead holder needs no `--force`.
- `tests/test_cli.py::test_resume_help_and_readme_name_the_force_flag` passes: `resume --help` and `README.md` both carry `--force`.
- `tests/test_dispatch.py::test_a_control_field_rewritten_mid_run_is_caught` passes: a control field rewritten mid-run still escalates, with the new wording.
- `grep -c "edited dispatcher-owned frontmatter" pipeline/daemon/supervisor.py` prints `0`.
- `grep -c "frontmatter changed while" pipeline/daemon/supervisor.py` prints `1`.
- `uv run --group dev pytest -q` reports no failure that step 1's baseline run did not already report, and the baseline's one failure (the repro) is gone.
- `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions

**`pipeline resume` refuses a ticket whose lease is live AND whose holder pid is
alive; `--force` is the only way past it.** Both halves matter. Refusing on
`lease_active()` alone would park an operator for the full 30 minutes after a
daemon was killed -- the case `start()` (`pipeline/daemon/supervisor.py:818`)
already handles with `holder_alive()`. Resume calls the same pair, so the two
agree on what a lease means. Checking nothing is the bug this ticket fixed:
resume rewrote `stage` under a running stage, and the dispatcher then escalated
that stage for the human's edit. The refusal sits above every mutation in
`cmd_resume`, per DEC-080, so a refused resume leaves the ticket unchanged.

**`--force` releases the lease under a running child on purpose, and the
escalation that follows is expected, not a bug.** The child keeps running and
its `_finish()` still diffs frontmatter against the pre-spawn snapshot, so a
forced resume produces one escalation when that child ends. That is the honest
outcome: the dispatcher cannot cancel a running agent, and invariant 1 says the
snapshot wins. Do not "fix" it by making `_finish()` skip the diff after a
forced resume -- that would let an agent's own rewrite through whenever a human
had forced anything.

**The tamper escalation states what the snapshot diff shows, not who did it.**
The message is "frontmatter changed while `<stage>` held the ticket", never
"`<stage>` edited dispatcher-owned frontmatter". The diff is between a pre-spawn
snapshot and the file on disk; a human running `pipeline resume --force`, or any
other writer, lands in it identically. The old wording sent operators to read a
stage log that showed nothing: `chezzilang` TICKET-049 and TICKET-050 both
escalated this way. Keep the field names and values in the message -- they are
the evidence -- and keep the accusation out.

## Rollback

Three commits in two independent halves. The resume half is step 5's
`pipeline/cli/main.py` with `tests/test_cli.py` and step 7's `README.md` with
`tests/test_cli.py`; the wording half is step 9's `pipeline/daemon/supervisor.py`
with `tests/test_dispatch.py`. Reverting only the wording half restores the old
escalation text and keeps the resume refusal; reverting only the resume half
restores the silent rewrite and keeps the honest wording. Neither half depends
on the other at runtime. Revert the resume half's two commits together: the
README paragraph documents a flag the other commit declares. After a full
revert `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active`
fails again, which is the signal the fix is gone.

## Thread

### 2026-09-03 12:35:52Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-09-03 · triage · result=ok

Reproduced. `cmd_resume` (`pipeline/cli/main.py:380`) has no
`lease_active()` check anywhere, unlike `cmd_note`
(`pipeline/cli/main.py:331`), which checks it and names the holder.

Committed `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active`
on `d1162a2`: takes a `planning-1` lease, runs `pipeline resume ... --stage
triage`, and asserts `stage` did not change. It fails today with:

    AssertionError: resume rewrote `stage` while `planning` held the lease: stage='triage'

This needs a design choice (refuse outright vs warn and proceed, and what
the warning names) -- not a chore. Result: `ok`.

### 2026-09-03 12:37:05Z · triage · session · session=3eb9094e-fbc2-4538-8408-09d08a7f46c6

`triage` ran as session `3eb9094e-fbc2-4538-8408-09d08a7f46c6`
- replay: `claude --resume 3eb9094e-fbc2-4538-8408-09d08a7f46c6`
- log: `.project/logs/TICKET-110-triage-3eb9094e.log`
- cost: $0.33 of a $3 cap
- tokens: 3,282 out (25 thinking) · 32 in · 602,081 cache read · 44,984 cache write

### 2026-09-03 12:37:05Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced -- cmd_resume rewrites stage under an active lease with no lease check at all

### 2026-09-03 · planning · result=ok

Plan written, both halves of the ticket in one branch. They share no code and
each stands alone; rolling back one leaves the other working.

The design choice the ticket left open: `resume` REFUSES, it does not warn and
proceed. The committed repro asserts `stage` did not change, and a warning
would leave the escalation the ticket is about. `--force` is the escape hatch.

The refusal is `t.lease_active() and holder_alive(holder)`, not `lease_active()`
alone. `start()` (`pipeline/daemon/supervisor.py:818`) already reads a live
lease with a dead holder pid as a killed daemon; refusing on `lease_active()`
alone would park an operator 30 minutes after every daemon kill, which is the
case `resume` exists for. `cmd_note` keeps its current wording -- it writes no
control field, so it has nothing to refuse.

Second half taken as planned: the escalation becomes "frontmatter changed while
`<stage>` held the ticket", and `tests/test_dispatch.py:157` is rewritten with
it. `grep -rn 'edited dispatcher-owned frontmatter'` returns only that line and
`pipeline/daemon/supervisor.py:1230`, so nothing else reads the old wording.

Out of scope, noted not fixed: `pipeline resume` still emits no event to
`events.db` (DEC-051 left that gap deliberately).

### 2026-09-03 12:44:16Z · planning · session · session=b08d61d0-4d98-487d-abdc-25e2be58d6a4

`planning` ran as session `b08d61d0-4d98-487d-abdc-25e2be58d6a4`
- replay: `claude --resume b08d61d0-4d98-487d-abdc-25e2be58d6a4`
- log: `.project/logs/TICKET-110-planning-b08d61d0.log`
- cost: $2.81 of a $10 cap
- tokens: 34,896 out (14,326 thinking) · 68 in · 2,054,488 cache read · 90,956 cache write

### 2026-09-03 12:44:16Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan written: resume refuses a live lease held by a live pid, --force takes it, escalation reworded

### 2026-09-03 12:45:04Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active` fails as required
```
le.mkdtemp())
        cli(d, "new", "t")
        path = d / ".project/tickets/TICKET-001.md"
        t = Ticket.load(path)
        t.take_lease("planning-1")
        t.save()
    
        r = cli(d, "resume", "TICKET-001", "--stage", "triage")
    
        after = Ticket.load(path)
>       assert after.stage != "triage", (
            "resume rewrote `stage` while `planning` held the lease: "
            f"stage={after.stage!r}")
E       AssertionError: resume rewrote `stage` while `planning` held the lease: stage='triage'
E       assert 'triage' != 'triage'
E        +  where 'triage' = Ticket(path=PosixPath('/tmp/tmpjm26hv3w/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='triage', klass='bugf...## Thread\n\n### 2026-09-03 12:44:18Z · human · note · by=chezzijr\n\n**resumed** by chezzijr -> `triage`, reset []\n').stage

tests/test_cli.py:223: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.38s ===============================

```
- ok: `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active` fails on base `main` too -- the bug is not already fixed upstream
```
 'triage' != 'triage'
E        +  where 'triage' = Ticket(path=PosixPath('/tmp/tmpqz22urd1/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='triage', klass='bugf...## Thread\n\n### 2026-09-03 12:44:19Z · human · note · by=chezzijr\n\n**resumed** by chezzijr -> `triage`, reset []\n').stage

tests/test_cli.py:223: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.60s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jw28j36_/base
      Built pipeline @ file:///tmp/pipeline-base-jw28j36_/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 22ms

```

### 2026-09-03 · plan-validation · result=fail

Rejected on one item: step ordering. Steps 4 and 5 read `args.force`, and step
2's `test_resume_force_takes_a_ticket_whose_lease_is_active` passes `--force`,
but step 7 is where the plan adds the flag to the `resume` parser
(`pipeline/cli/main.py:747`). That row today declares `id`, `--stage`,
`--grant`, `--reset`, `--note` and no `--force`, and no top-level `--force`
exists. So step 5's "expect the three new tests and the repro to pass" cannot
hold: the refusal test gets `AttributeError: 'Namespace' object has no
attribute 'force'` in stderr instead of the holder, and the force test gets
argparse's `unrecognized arguments: --force`. Step 5 also commits a
`pipeline resume` that crashes on every live lease. Fix: move
`p.add_argument("--force", ...)` from step 7 into step 4.

Passed, each verified against the code:

1. Root cause. `cmd_resume` writes `stage` with no lease check; `_finish()`
   diffs the pre-spawn snapshot and escalates. The plan fixes both.
2. Decisions. DEC-080 says the refusal "sits above `t.stage = args.stage`";
   step 4 puts it above every mutation. DEC-100, DEC-051, DEC-047 unaffected.
3. Scope. Every step traces to a criterion. Blast radius: 5 files, bugfix.
4. Criteria. `grep -c "edited dispatcher-owned frontmatter"
   pipeline/daemon/supervisor.py` prints `1` today and
   `grep -c "frontmatter changed while"` prints `0`; both flip only if
   step 9 lands.
5. Concreteness. `holder_alive` (supervisor.py:51), `release_lease()`
   (ticket.py:711) returning `{"holder": None, "expires": None}`, and
   `die()` (main.py:36) writing stderr and exiting 1 all match the plan.
6. Riskiest step: step 9, the escalation wording. Only
   `tests/test_dispatch.py:157` reads it; `pipeline/tui/app.py` selects by
   `kind == "escalation"`. Rollback reverts it independently.
7. Regression surface. `take_lease` appears twice in tests: line 217 (the
   repro) and line 268 (a `note` test). No existing test resumes a leased
   ticket, so the refusal breaks none.

Unverified: I ran no test. The guard blocks `pytest` for this stage, so items
4 and 7 rest on the greps and reads above, not on a run.

long: the rejected item needs its evidence and the six passing items each need
their reasoning, per this stage's "an unexplained pass is a fail".

### 2026-09-03 12:48:25Z · plan-validation · session · session=4e1c9fa3-9a75-4b4c-aa02-7eea92d454d1

`plan-validation` ran as session `4e1c9fa3-9a75-4b4c-aa02-7eea92d454d1`
- replay: `claude --resume 4e1c9fa3-9a75-4b4c-aa02-7eea92d454d1`
- log: `.project/logs/TICKET-110-plan-validation-4e1c9fa3.log`
- cost: $1.28 of a $3 cap
- tokens: 14,338 out (8,062 thinking) · 30 in · 706,425 cache read · 56,539 cache write

### 2026-09-03 12:48:25Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ step ordering: steps 4-5 read `args.force` and pass `--force`, but step 7 declares the flag, so step 5's stated expectation cannot hold

### 2026-09-03 · planning · result=ok

Plan rewritten for the one item the gate rejected: step ordering.

Step 4 now does two things in order -- append
`p.add_argument("--force", action="store_true", help=...)` to the `resume`
parser row (`pipeline/cli/main.py:747`), then insert the refusal that reads
`args.force` under `t = Ticket.find(project, args.id)`. The flag and its only
reader land in one commit, so no step runs a `resume` that argparse cannot
parse.

Step 7 is now `README.md` only; it commits `README.md` with `tests/test_cli.py`
as `docs: document resume --force (TICKET-110)`. Step 6 states what it fails
on: the README assertion, since step 4 already put `--force` in
`resume --help`. Step 5 now says "step 2's three tests", not "the three new
tests" -- step 6 adds a fourth.

Verified against the code before rewriting: the `resume` parser row at line 747
declares `id`, `--stage`, `--grant`, `--reset`, `--note` and no `--force`, and
`main()` declares no top-level `--force`. That fact is now in `## Digest`.

`## Rollback` said "the two commits"; the plan makes three. It now names three
in two independent halves, and says the resume half's two revert together.

The design, the decisions (DEC-080, DEC-051, DEC-100, DEC-047), the scope, the
criteria and the tests are unchanged from the plan the gate passed on those
items. Still out of scope, noted not fixed: `pipeline resume` emits no event to
`events.db` (DEC-051 left that gap deliberately).

### 2026-09-03 12:51:42Z · planning · session · session=18546d70-d1ab-4589-915d-ead7c6bebc6b

`planning` ran as session `18546d70-d1ab-4589-915d-ead7c6bebc6b`
- replay: `claude --resume 18546d70-d1ab-4589-915d-ead7c6bebc6b`
- log: `.project/logs/TICKET-110-planning-18546d70.log`
- cost: $1.64 of a $10 cap
- tokens: 14,241 out (3,948 thinking) · 50 in · 1,319,213 cache read · 62,555 cache write

### 2026-09-03 12:51:42Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ plan rewritten: step 4 declares --force on the resume parser before the refusal reads it; step 7 is README only

### 2026-09-03 12:56:57Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active` fails as required
```
le.mkdtemp())
        cli(d, "new", "t")
        path = d / ".project/tickets/TICKET-001.md"
        t = Ticket.load(path)
        t.take_lease("planning-1")
        t.save()
    
        r = cli(d, "resume", "TICKET-001", "--stage", "triage")
    
        after = Ticket.load(path)
>       assert after.stage != "triage", (
            "resume rewrote `stage` while `planning` held the lease: "
            f"stage={after.stage!r}")
E       AssertionError: resume rewrote `stage` while `planning` held the lease: stage='triage'
E       assert 'triage' != 'triage'
E        +  where 'triage' = Ticket(path=PosixPath('/tmp/tmpwp7sa7dn/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='triage', klass='bugf...## Thread\n\n### 2026-09-03 12:56:16Z · human · note · by=chezzijr\n\n**resumed** by chezzijr -> `triage`, reset []\n').stage

tests/test_cli.py:223: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.29s ===============================

```
- ok: `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active` fails on base `main` too -- the bug is not already fixed upstream
```
 'triage' != 'triage'
E        +  where 'triage' = Ticket(path=PosixPath('/tmp/tmpvjsh07l8/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='triage', klass='bugf...## Thread\n\n### 2026-09-03 12:56:17Z · human · note · by=chezzijr\n\n**resumed** by chezzijr -> `triage`, reset []\n').stage

tests/test_cli.py:223: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.57s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-g93u3sat/base
      Built pipeline @ file:///tmp/pipeline-base-g93u3sat/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 18ms

```

### 2026-09-03 · plan-validation · result=ok

Tier B: all eight items pass. The item the last run rejected is fixed.

Step ordering. The `resume` parser row is `pipeline/cli/main.py:747` and today
declares `id`, `--stage`, `--grant`, `--reset`, `--note`. Step 4 appends
`p.add_argument("--force", ...)` there and then inserts the refusal that reads
`args.force`, in one step. No earlier step runs `resume --force`.

1. Root cause. `cmd_resume` writes `stage`, `counters` and the lease with no
   lease read; `_finish()` diffs the pre-spawn snapshot and escalates the stage
   that held it. The plan fixes the write and the wording, not just the repro.
2. Decisions. DEC-080: the refusal goes above every mutation. DEC-086 states
   `lease_active() and holder_alive(...)` for `start()`; the plan reuses that
   pair. DEC-100, DEC-051, DEC-047 unaffected.
3. Scope. Every step traces to a criterion. 5 files for a `bugfix`.
4. Criteria. `grep -c "edited dispatcher-owned frontmatter"
   pipeline/daemon/supervisor.py` prints `1` today, `grep -c "frontmatter
   changed while"` prints `0`; both flip only if step 9 lands.
5. Concreteness. `holder_alive` returns True on `PermissionError`
   (supervisor.py:63), `release_lease()` sets `{"holder": None, "expires":
   None}` (ticket.py:711), `die()` writes stderr and exits 1 (main.py:36).
6. Riskiest step: step 9. Only `tests/test_dispatch.py:157` reads that string;
   `pipeline/tui/app.py:195` selects by `kind == "escalation"`. `## Rollback`
   reverts it alone.
7. Regression surface. `take_lease` appears at `tests/test_cli.py:217` (the
   repro), `tests/test_cli.py:268` (a `note` test, after its resume) and
   `tests/test_dispatch.py:27` (an `escalate` test). No existing test resumes a
   leased ticket.

Two line numbers are one off; the prose anchors are exact, so neither needs
research. `t = Ticket.find(project, args.id)` in `cmd_resume` is line 364, not
363. Step 2's insertion point is after line 227 (`shutil.rmtree(d)`), not 226 --
line 226 is inside the repro's assert.

Unverified: the step 1 baseline. I did not run `uv run --group dev pytest -q`;
a read-only stage cannot. The gate's PASS entry records the repro failing on
the branch and on base.

### 2026-09-03 12:59:43Z · plan-validation · session · session=68391925-3d44-442a-be11-a68a0fa34060

`plan-validation` ran as session `68391925-3d44-442a-be11-a68a0fa34060`
- replay: `claude --resume 68391925-3d44-442a-be11-a68a0fa34060`
- log: `.project/logs/TICKET-110-plan-validation-68391925.log`
- cost: $1.31 of a $3 cap
- tokens: 12,911 out (5,473 thinking) · 32 in · 809,436 cache read · 58,270 cache write

### 2026-09-03 12:59:43Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all eight items; step 4 declares --force on the resume parser (main.py:747) before the refusal reads it

### 2026-09-03 16:45:15Z · human · note · by=chezzijr

**note from chezzijr**

Plan gate reviewed by Claude on chezzijr's instruction (they are asleep). Checked: the refusal sits above every mutation in cmd_resume, --force is the escape hatch and records the override in the thread, a lease whose holder pid is dead needs no --force (matches start()'s reading), and the reworded escalation asserts only what the snapshot diff proves. tests/test_dispatch.py's wording assertion is renamed and updated in the same commit, so nothing is left asserting the old text. Both halves revert independently. Approving.

### 2026-09-03 16:45:15Z · human · approval · by=claude-for-chezzijr

**approved by claude-for-chezzijr**

### 2026-09-03 16:46:21Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active` fails as required
```
le.mkdtemp())
        cli(d, "new", "t")
        path = d / ".project/tickets/TICKET-001.md"
        t = Ticket.load(path)
        t.take_lease("planning-1")
        t.save()
    
        r = cli(d, "resume", "TICKET-001", "--stage", "triage")
    
        after = Ticket.load(path)
>       assert after.stage != "triage", (
            "resume rewrote `stage` while `planning` held the lease: "
            f"stage={after.stage!r}")
E       AssertionError: resume rewrote `stage` while `planning` held the lease: stage='triage'
E       assert 'triage' != 'triage'
E        +  where 'triage' = Ticket(path=PosixPath('/tmp/tmph5rpmd3w/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='triage', klass='bugf...## Thread\n\n### 2026-09-03 16:45:16Z · human · note · by=chezzijr\n\n**resumed** by chezzijr -> `triage`, reset []\n').stage

tests/test_cli.py:223: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.50s ===============================

```
- ok: `tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active` fails on base `main` too -- the bug is not already fixed upstream
```
 'triage' != 'triage'
E        +  where 'triage' = Ticket(path=PosixPath('/tmp/tmp75s0pxd0/.project/tickets/TICKET-001.md'), id='TICKET-001', stage='triage', klass='bugf...## Thread\n\n### 2026-09-03 16:45:19Z · human · note · by=chezzijr\n\n**resumed** by chezzijr -> `triage`, reset []\n').stage

tests/test_cli.py:223: AssertionError
=========================== short test summary info ============================
FAILED tests/test_cli.py::test_resume_refuses_a_ticket_whose_lease_is_active
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 1.10s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-jl2oweio/base
      Built pipeline @ file:///tmp/pipeline-base-jl2oweio/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 41ms

```

### 2026-09-03 16:46:22Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-09-03T16:47:52Z · implementing · todo

**todo list**

1. [ ] baseline: run full suite, record summary (1 failed, 531 passed today)
2. [ ] add 3 tests to tests/test_cli.py after line 227, watch fail
3. [ ] import holder_alive in pipeline/cli/main.py:29
4. [ ] declare --force on resume parser + insert refusal in cmd_resume
5. [ ] record forced-override note + print suffix; commit main.py + test_cli.py
6. [ ] add test_resume_help_and_readme_name_the_force_flag, watch fail on README
7. [ ] document --force in README.md; commit README.md + test_cli.py
8. [ ] rename/reword test_an_agent_that_rewrote_stage_is_still_caught in test_dispatch.py
9. [ ] reword tamper escalation in supervisor.py:1230; commit supervisor.py + test_dispatch.py
10. [ ] verify: full suite + dangerous_commands guard

### 2026-09-03T16:51:34Z · implementing · result=ok

**todo (all done)**

1. [x] baseline: 531 passed, 1 failed (the repro)
2. [x] 3 tests added to tests/test_cli.py after line 227, all failed as expected
3. [x] holder_alive imported at pipeline/cli/main.py:29
4. [x] --force declared on resume parser, refusal inserted above every mutation in cmd_resume
5. [x] forced-override recorded in thread note and print; committed 5534da5
6. [x] force-flag README test added, failed on README assertion as expected
7. [x] README.md documents --force; committed 612a031
8. [x] test_dispatch.py test renamed to test_a_control_field_rewritten_mid_run_is_caught, wording updated
9. [x] escalation reworded in supervisor.py:1230; committed a900757
10. [x] verify: full suite 536 passed (531 base + 1 repro fixed + 4 new); guard exits 0

**verification**

- 0 -> 0
- 1 -> 1
- `uv run --group dev pytest -q` -> 536 passed, no failures
- `./pipeline/hooks/test_dangerous_commands.py` -> guard: all passed, exit 0

Three commits, as the rollback section describes: d1162a2 (repro, pre-existing),
5534da5 (resume refusal + tests), 612a031 (README), a900757 (escalation wording
+ test rename). No deviation from the plan.

### 2026-09-03 16:51:53Z · implementing · session · session=01b1c6f5-4494-4534-bce2-a29f5a7f8780

`implementing` ran as session `01b1c6f5-4494-4534-bce2-a29f5a7f8780`
- replay: `claude --resume 01b1c6f5-4494-4534-bce2-a29f5a7f8780`
- log: `.project/logs/TICKET-110-implementing-01b1c6f5.log`
- cost: $0.83 of a $8 cap
- tokens: 11,480 out (57 thinking) · 80 in · 2,346,738 cache read · 60,327 cache write

### 2026-09-03 16:51:53Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ implemented the plan as written; resume refuses a live lease, --force overrides, escalation reworded; all criteria pass

### 2026-09-03 17:03:00Z · review · note

**review pass 1: no blocking findings**

Reviewed `git diff 3c6643f..HEAD` -- 5 files, 130 insertions. The delta
matches the plan step for step. No drift.

Re-ran every acceptance criterion here:

1. `uv run --group dev pytest -q` -> `536 passed in 62.53s`, 0 failed.
2. The six named tests -> `6 passed in 1.75s`.
3. `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`, exit 0.
4. `grep -c "edited dispatcher-owned frontmatter" pipeline/daemon/supervisor.py`
   -> `0`; `grep -c "frontmatter changed while" ...` -> `1`. A repo-wide grep
   for the old wording returns nothing.

Two findings I raised and then refuted:

1. "The refusal parks a human resuming a parked or escalated ticket." Refuted:
   every path that leaves a ticket for a human releases the lease first --
   `escalate()` (`pipeline/daemon/supervisor.py:76`), `advance()` (line 148),
   the gate pass (line 1089), `shut_down()` (line 1352).
2. "`cmd_approve` and `cmd_reject` rewrite `stage` with the same missing
   check." Refuted: both refuse outside a gate stage
   (`pipeline/cli/main.py:280`, `pipeline/cli/main.py:308`), and a ticket
   reaches a gate stage through `advance()`, which released the lease.

Non-blocking nit: the README usage block (README.md:74-80) lists `--reset`,
`--grant` and `--note` on `resume` but not `--force`. The flag is documented
in the recovery paragraph at README.md:491-497 instead.

### 2026-09-03 16:55:33Z · review · session · session=df882e01-c376-4f1b-8a58-474e60b1c873

`review` ran as session `df882e01-c376-4f1b-8a58-474e60b1c873`
- replay: `claude --resume df882e01-c376-4f1b-8a58-474e60b1c873`
- log: `.project/logs/TICKET-110-review-df882e01.log`
- cost: $1.32 of a $5 cap
- tokens: 10,150 out (2,998 thinking) · 44 in · 1,034,415 cache read · 55,078 cache write

### 2026-09-03 16:55:33Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ reviewed the 5-file delta against 3c6643f: no blocking findings; 536 passed, guard exit 0, both grep criteria hold

### 2026-09-03 17:12:49Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-09-04 01:48:25Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ pre=$(git rev-parse HEAD); n=$(git rev-list --count main..HEAD); git rebase main || git rebase --abort 2>/dev/null
[ "$(git rev-list --count main..HEAD)" -ge "$n" ] || { echo "rebase dropped a commit already on main -- restoring $pre so the merge lands it"; git reset --hard "$pre"; }
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/110


Rebasing (1/4)Rebasing (2/4)Rebasing (3/4)Rebasing (4/4)Successfully rebased and updated refs/heads/ticket/110.
Already up to date.
Updating e311543..631210f
Fast-forward
 README.md                     |  8 ++++
 pipeline/cli/main.py          | 20 +++++++--
 pipeline/daemon/supervisor.py |  6 ++-
 tests/test_cli.py             | 94 +++++++++++++++++++++++++++++++++++++++++++
 tests/test_dispatch.py        | 10 +++--
 5 files changed, 130 insertions(+), 8 deletions(-)

```

### 2026-09-04 01:48:25Z · merging · decision

decision recorded as `DEC-110`
