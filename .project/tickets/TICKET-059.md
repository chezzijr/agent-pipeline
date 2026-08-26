---
id: TICKET-059
stage: done
class: bugfix
branch: ticket/059
test_file: tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon
files_declared:
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/daemon/server.py
- pipeline/daemon/supervisor.py
- pipeline/templates/skills/file-ticket/SKILL.md
- tests/test_cli.py
- tests/test_daemon.py
- tests/test_pty.py
counters:
  plan_validation_attempts: 2
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 18
  plan_files: 9
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 98ef1335-c35e-4433-a9c2-9a9d8b5ae5d7
  log: .project/logs/TICKET-059-review-98ef1335.log
approved_by: chezzijr
approved_at: '2026-08-26T17:28:08.516779+00:00'
---

## Summary

The fix is the spawn gate, not the permission mode. `spawn()`
(`pipeline/daemon/supervisor.py:361`) will require an attached client, not just
a socket: `pipeline/daemon/server.py` gains `watchers(project)` -- `Poller`
returns 0, `Server` counts connections holding a subscription for this project
or for every project -- and `spawn()` takes the PTY path only when
`attachable` is true and `watchers() > 0`. Otherwise it prints why and runs
headless, which is what
`tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon`
asks for.

`pipeline/harnesses/claude-code.toml` is not touched. It keeps
`interactive_permission_mode = "acceptEdits"`, so the ticket does not park at
the `machine.FENCED` gate, and with a human attached a prompt in `acceptEdits`,
`auto` or `manual` is answerable either way.

The log's `auto mode on` is not set by the pipeline: `stage_settings()` writes
hooks only. `~/.claude/settings.json` carries `permissions.defaultMode = auto`.
See `## Digest` and `## Decisions`.

Implemented 2026-08-27, all 18 steps, no deviation. Four commits: `3aa8690`
(`watchers()` on `Poller`/`Server`), `c7a76bf` (the `spawn()` gate),
`20b9b08` (help text), `796192e` (README/CLAUDE.md/SKILL.md).

review passed the delta on 2026-08-27, first pass, no blocking findings.
`uv run --group dev pytest -q` -> `317 passed in 13.74s`, no skips. The diff
lists exactly the nine `files_declared` paths;
`pipeline/harnesses/claude-code.toml` is absent. All seven acceptance criteria
verified against the code. Two candidate findings were refuted and dropped; one
minor note stands, a stale comment at `pipeline/daemon/supervisor.py:353` that
the paragraph below it already corrects. Nothing needs changing before merge.

## Reproduction

`tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon`

Command: `uv run --group dev pytest -q tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon`

A real `Server` (no client ever attached) is passed to
`supervisor.spawn(..., "planning", ...)`. `rec["mode"]` comes back
`"interactive"`, so `spawn()` chose the PTY/`acceptEdits` path from
`srv.attachable` alone.

expect: AssertionError: nothing is attached, but spawn() ran a REPL anyway (mode='interactive')

## Digest

**Files touched.** `pipeline/daemon/server.py` (the new `watchers()`),
`pipeline/daemon/supervisor.py` (the gate), `pipeline/cli/main.py` (help text),
`README.md`, `CLAUDE.md`, `pipeline/templates/skills/file-ticket/SKILL.md`,
`tests/test_daemon.py`, `tests/test_pty.py`, `tests/test_cli.py`.

**Key functions.** `Poller.attachable = False` (`pipeline/daemon/server.py:156`)
and `Server.attachable = True` (`:231`). `Conn.subs` (`:201`) maps sub id ->
`{"project": str|None}`; `_op_subscribe` (`:480`) fills it, `_drop` (`:382`)
pops the connection, so a client that goes away stops counting. `_project()`
(`:455`) resolves a subscription's project to `str(Path(p).resolve())`, or
`None` for no filter. `spawn()` (`pipeline/daemon/supervisor.py:361`) reads
`getattr(poller, "attachable", False)` today; `run()`'s docstring repeats that
claim at `:1187`.

**Entry points.** `pipeline start` builds a `Server`, `pipeline run` builds a
bare `Poller`; both call `supervisor.spawn()`. `pipeline/tui/app.py:307`
`_subscribe()` opens a second connection with `client.clone()` and sends
`subscribe`, so a running `pipeline tui` is one connection carrying one
subscription. One-shot commands (`ls`, `kill`) use `Client.request()` and never
subscribe -- which is why a subscription, not a connection, is what counts.

**Permission-mode finding (the ticket's second claim).** `claude --help` on
2.1.246 lists these `--permission-mode` choices: `"acceptEdits", "auto",
"bypassPermissions", "manual", "dontAsk", "plan"`. The pipeline is not the
source of `auto`: `stage_settings()` (`pipeline/core/config.py:275`) writes a
settings file holding hooks and nothing else. Two candidates remain on this
machine: `~/.claude/settings.json` has `permissions.defaultMode = auto`, and
`~/.claude.json` has `cachedGrowthBookFeatures.tengu_auto_mode_config.enabled =
enabled`. Either explains `auto mode on` in
`.project/logs/TICKET-035-planning-ee0c98d7.log`, whose first line spells
`--permission-mode acceptEdits`. I could not separate them: a live probe
(`claude --permission-mode acceptEdits` on a PTY) was refused with `Permission
for this action was denied by the Claude Code auto mode classifier.` The plan
therefore stops depending on which mode Claude Code picks.

**Gotchas.**

1. Ask `watchers()` only when `attachable` is true, so `poller=None` and the
   bare `Poller` short-circuit.
2. A subscription's project is a resolved path string; pass
   `str(project.resolve())` from `spawn()`.
3. `tests/test_pty.py:394` `class Attachable(Poller)` drives two tests that
   expect the interactive path -- it needs a `watchers()` of its own or both go
   red.
4. Do not edit `pipeline/harnesses/claude-code.toml`: it is in `machine.FENCED`
   and any diff there parks the ticket at `awaiting-merge`.
5. A `pipeline tui` started after the spawn gets a headless stage. That race is
   accepted, not closed.
6. `.claude/skills/file-ticket/SKILL.md` is a symlink to
   `pipeline/templates/skills/file-ticket/SKILL.md`. Edit the template; a
   second copy fails `tests/test_stages.py::test_the_repo_skill_is_the_packaged_file`.
7. No test asserts the text of the skill bullet at
   `pipeline/templates/skills/file-ticket/SKILL.md:141-144`.
   `test_the_docs_name_the_skill_init_installs` (`tests/test_stages.py:213`)
   reads `CLAUDE.md` and `README.md` only, so rewriting that bullet breaks
   nothing.
8. `pipeline/templates/skills/file-ticket/SKILL.md` is not in `machine.FENCED`
   (`pipeline/core/machine.py:32-50`), so editing it does not park the ticket.

## Decisions checked

Grepped `.project/decisions/` for `attachable`, `attach`, `interactive`, `pty`,
`permission_mode`, `acceptEdits`, `skill`, `file-ticket`.

- **DEC-049 (active).** Binds the `start`/`run` help text and two README lines
  to `Server.attachable is True` and `Poller.attachable is False`. The plan
  keeps both attributes and extends
  `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` rather
  than replacing it, so the record still holds.
- **DEC-052 (active, supersedes DEC-041).** `--add-dir` binds only under
  `interactive_cmd`'s `acceptEdits`. The plan keeps that mode and does not
  touch the harness, so nothing there changes.
- **DEC-055 (active).** The geometry marker goes in an interactive log only.
  The plan changes when a log is interactive, not the marker rule, which is why
  `test_an_interactive_log_opens_with_its_geometry` must keep seeing a watcher.
- **DEC-039 (active).** `tail_log()` sniffs a PTY dump by the raw ESC.
  Untouched.
- **DEC-011 (frozen).** The socket protocol, the schema and the event-kind
  vocabulary. The plan adds no op, no event kind and no column: `watchers()` is
  read server-side, never over the wire.
- **DEC-056 (active).** `pipeline/templates/skills/file-ticket/SKILL.md` is the
  only copy of the skill; `.claude/skills/file-ticket/SKILL.md` is a symlink to
  it. Step 16 edits the template and leaves the symlink, so the record holds.
- **DEC-041.** Superseded by DEC-052; cited as history, not as a constraint.

No active record constrains gating on an attached client. Nothing is
superseded.

## Plan

1. Add a failing test named `test_watchers_counts_a_subscribed_client_not_a_one_shot_request` to `tests/test_daemon.py`, below `test_subscribe_replays_from_the_cursor_then_goes_live`, with exactly this body:

    ```python
    def test_watchers_counts_a_subscribed_client_not_a_one_shot_request():
        """TICKET-059: `attachable` says a socket exists, `watchers()` says a
        client is on it. `pipeline ls` connects, is answered and goes away
        without subscribing, so it must not read as a human watching a PTY."""
        tmp = Path(tempfile.mkdtemp())
        a, b = Path(tempfile.mkdtemp()).resolve(), Path(tempfile.mkdtemp()).resolve()
        (a / ".project").mkdir()
        (b / ".project").mkdir()
        registry.register(a)
        registry.register(b)
        srv = server_on(tmp, store(tmp))
        socks = [socket.socketpair(), socket.socketpair()]
        try:
            assert srv.watchers() == 0
            one_shot = Conn(socks[0][0])
            srv.conns[one_shot.sock.fileno()] = one_shot
            srv._handle_line(one_shot, json.dumps({"id": 1, "op": "ping"}) + "\n")
            assert srv.watchers() == 0, "a request with no subscription is not a watcher"
            tui = Conn(socks[1][0])
            srv.conns[tui.sock.fileno()] = tui
            srv._handle_line(tui, json.dumps({"id": 2, "op": "subscribe",
                                              "project": str(a)}) + "\n")
            assert srv.watchers(str(a)) == 1
            assert srv.watchers(str(b)) == 0, "a filtered subscription watches one project"
            assert srv.watchers() == 1, "unfiltered means every project"
            srv._drop(tui.sock.fileno())
            assert srv.watchers(str(a)) == 0, "a client that went away is not a watcher"
        finally:
            srv.conns.clear()
            srv.close()
            registry.unregister(a)
            registry.unregister(b)
            for pair in socks:
                for s in pair:
                    s.close()
    ```

2. Run `uv run --group dev pytest -q tests/test_daemon.py::test_watchers_counts_a_subscribed_client_not_a_one_shot_request` and watch it fail with `AttributeError: 'Server' object has no attribute 'watchers'`; quote that line in `## Thread`. This step changes no file except `tests/test_daemon.py`, which step 1 already wrote.

3. Add `watchers()` to `pipeline/daemon/server.py` twice: on `Poller`, directly under `attachable = False` (line 156), and on `Server`, directly under `attachable = True` (line 231).

    ```python
    # on Poller
    def watchers(self, project: str | None = None) -> int:
        """How many clients could attach to a PTY hosted here right now.
        `attachable` says a socket exists; this says somebody is on it, which
        is the question `spawn()` actually has to answer. A bare `Poller` has
        neither, so this is 0 and stays 0."""
        return 0

    # on Server
    def watchers(self, project: str | None = None) -> int:
        """Connections holding a subscription for `project` (a resolved path
        string) or for every project. A one-shot `request` -- `ls`, `kill` --
        connects, is answered and goes away without subscribing, so only a
        subscription counts as a human watching: otherwise a `pipeline ls`
        landing in the same tick as a spawn would read as an attached TUI."""
        return sum(any(s.get("project") is None or project is None
                       or s.get("project") == project
                       for s in c.subs.values())
                   for c in self.conns.values())
    ```

4. Run `uv run --group dev pytest -q tests/test_daemon.py`, expect every test in `tests/test_daemon.py` to pass, then commit `pipeline/daemon/server.py` and `tests/test_daemon.py` as `feat(TICKET-059): count the clients subscribed to a server`.

5. Replace the gate and its message in `pipeline/daemon/supervisor.py:361` -- the two lines `interactive = cfg.get("mode") == "interactive" and getattr(poller, "attachable", False)` and the `if cfg.get("mode") == "interactive" and not interactive:` print under them -- with this, leaving the comment block above in place:

    ```python
    attached = (poller.watchers(str(project.resolve()))
                if getattr(poller, "attachable", False) else 0)
    interactive = cfg.get("mode") == "interactive" and attached > 0
    if cfg.get("mode") == "interactive" and not interactive:
        why = ("nothing can attach to it here"
               if not getattr(poller, "attachable", False)
               else "no client is attached")
        print(f"  {tid}: `{stage}` is interactive, but {why} -- running "
              f"headless (leave `pipeline tui` open before the stage starts "
              f"to steer it)")
    ```

6. Append this paragraph to the end of the comment block above that gate in `pipeline/daemon/supervisor.py`, immediately before the `attached =` assignment: `# A daemon is not a human: attachable only says a socket exists, so pipeline start with nobody on it spawned the REPL anyway and parked it at a permission prompt nobody could see (TICKET-059). watchers() is the second question -- a client subscribed right now. A TUI that attaches after the spawn gets a headless stage, deliberately: the alternative is holding a ticket for a human who may never arrive.`

7. Give `class Attachable(Poller)` in `tests/test_pty.py:394` a watcher, so the two tests that expect the interactive path keep it: add `def watchers(self, project: str | None = None) -> int: return 1` under `attachable = True`, and change its docstring to `"""A poller a client could reach, with one on it -- what `Server` is with a `pipeline tui` subscribed, minus the socket."""`

8. In the `run()` docstring at `pipeline/daemon/supervisor.py:1187`, replace `the bare `Poller` is not `attachable`, so `spawn()` runs those headless rather than parking a REPL nobody could reach (see `spawn()` and the README)` with `the bare `Poller` is not `attachable` and reports no `watchers()`, so `spawn()` runs those headless rather than parking a REPL nobody could reach. Under `serve()` the same happens whenever no client is subscribed (see `spawn()` and the README)`.

9. Run `uv run --group dev pytest -q tests/test_pty.py`, expect `test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon`, `test_an_interactive_stage_runs_headless_when_nothing_can_attach` and `test_an_interactive_log_opens_with_its_geometry` to pass, quote the summary line in `## Thread`, then commit `pipeline/daemon/supervisor.py` and `tests/test_pty.py` as `fix(TICKET-059): spawn a PTY only while a client is attached`.

10. Rewrite `START_DESC` and `RUN_DESC` in `pipeline/cli/main.py:509-522`: `START_DESC` becomes `"Start the one daemon for every registered project. A stage whose frontmatter says `mode: interactive` -- `planning` -- runs on a PTY the daemon owns only while a client is attached: leave `pipeline tui` open and it waits there at its first permission prompt. With no client subscribed it runs headless, exactly as `pipeline run` does."`, and `RUN_DESC` keeps its first two sentences (through `parks the ticket for `pipeline answer`.`) with its third and last sentence replaced by `"Under `pipeline start` that same stage waits at `pipeline tui`, and only if a tui is attached when it spawns."`

11. Extend `test_the_help_text_matches_the_code_it_describes` in `tests/test_cli.py` twice: after `assert Server.attachable is True and Poller.attachable is False` add `assert Poller().watchers() == 0, "a supervisor with no socket has no watchers"`, and after `start, run = help_of("start"), help_of("run")` add `assert "attached" in start and "attached" in run, (start, run)`.

12. Run `uv run --group dev pytest -q tests/test_cli.py`, expect every test in `tests/test_cli.py` to pass, then commit `pipeline/cli/main.py` and `tests/test_cli.py` as `docs(TICKET-059): help text says an interactive stage needs an attached client`.

13. In the *Interactive stages* section of `README.md`, replace the paragraph starting `` `mode: interactive` means "interactive when a human can reach it".`` with one saying: `mode: interactive` means "interactive while a human is attached"; `pipeline run` has no socket and `pipeline start` with no client subscribed is the same case; both run the stage headless and say so on stdout; a TUI that attaches after the spawn gets a headless stage. Keep its two closing sentences about `result: needs-input` and about `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` unchanged.

14. Change line 127 of `README.md` to `pipeline start                       # spawns pipelined, detached; interactive stages need `pipeline tui` attached`; the line must still begin `pipeline start ` and contain `tui`, because DEC-049's test reads it.

15. Rewrite the gotcha bullet in `CLAUDE.md` that begins `**An interactive stage is only interactive if something can attach.**` as: `**An interactive stage is only interactive while a client is attached.** `spawn()` asks two questions: `poller.attachable` (is there a socket -- `Server` sets it, the bare `Poller` `pipeline run` builds does not) and `poller.watchers(project)` (is a client subscribed right now). Gating on `attachable` alone was wrong: a daemon with nobody on it still spawned a REPL, and it parked at a prompt nobody could see until the lease expired twice (TICKET-059). A TUI that attaches after the spawn gets a headless stage; that race is accepted.`

16. Replace lines 141-144 of `pipeline/templates/skills/file-ticket/SKILL.md` (edit that path, never the `.claude/skills/file-ticket/SKILL.md` symlink pointing at it) with exactly this, keeping the two-space bullet indent:

    ```markdown
      **They differ where it matters:** `planning` is `mode: interactive`, so under the
      daemon it runs on a PTY and waits for a human -- but only when a client is already
      subscribed as the stage spawns: leave `pipeline tui` open first, then `i` for raw
      mode. With no client attached, and under `pipeline run` where nothing can attach,
      it runs headless and finishes on its own. Unattended = `pipeline run`.
    ```

17. Run `uv run --group dev pytest -q` (the whole dispatcher suite, because `tests/test_stages.py` and `tests/test_cli.py` read `CLAUDE.md`, `README.md` and the skill), quote the summary line in `## Thread`, then commit `README.md`, `CLAUDE.md` and `pipeline/templates/skills/file-ticket/SKILL.md` as `docs(TICKET-059): an interactive stage needs an attached client, not a daemon`.

18. Run `uv run --group dev pytest -q tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` (expect `1 passed`) and `git diff --name-only main...HEAD`, whose output must be exactly `CLAUDE.md`, `README.md`, `pipeline/cli/main.py`, `pipeline/daemon/server.py`, `pipeline/daemon/supervisor.py`, `pipeline/templates/skills/file-ticket/SKILL.md`, `tests/test_cli.py`, `tests/test_daemon.py`, `tests/test_pty.py` -- if `pipeline/harnesses/claude-code.toml` appears there, revert it, because a diff in a `machine.FENCED` path parks the ticket at `awaiting-merge`.

## Acceptance criteria

1. A `Server` with no subscribed client spawns `planning` headless:
   `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon`
   passes, with `rec["mode"] == "batch"`.
2. A poller with a watcher still gets the PTY:
   `tests/test_pty.py::test_an_interactive_stage_runs_headless_when_nothing_can_attach`
   passes both halves, and
   `tests/test_pty.py::test_an_interactive_log_opens_with_its_geometry` still
   finds the geometry marker in the interactive log.
3. `watchers()` counts a subscription and not a bare request, honours a project
   filter, and drops to 0 when the client goes away:
   `tests/test_daemon.py::test_watchers_counts_a_subscribed_client_not_a_one_shot_request`
   passes.
4. The help text and the README say the new rule and stay bound to the code:
   `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` passes
   with its two new assertions.
5. `uv run --group dev pytest -q` is green, with no test skipped or deleted.
6. `pipeline/harnesses/claude-code.toml` stays out of the diff: `git diff
   --name-only main...HEAD` lists only the nine paths in `files_declared`
   (`CLAUDE.md`, `README.md`, `pipeline/cli/main.py`,
   `pipeline/daemon/server.py`, `pipeline/daemon/supervisor.py`,
   `pipeline/templates/skills/file-ticket/SKILL.md`, `tests/test_cli.py`,
   `tests/test_daemon.py`, `tests/test_pty.py`), and
   `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` passes
   after the `CLAUDE.md` edit, so nothing in `machine.FENCED` moved and the
   ticket does not park at the `awaiting-merge` gate.
7. The file-ticket skill states the new rule and stays one file:
   `grep -c 'but only when a client is already'
   pipeline/templates/skills/file-ticket/SKILL.md` prints `1` (the phrase sits
   on one line of step 16's replacement text), and
   `tests/test_stages.py::test_the_repo_skill_is_the_packaged_file` passes, so
   `.claude/skills/file-ticket/SKILL.md` is still the symlink and carries the
   same bytes.

## Decisions

**An interactive stage is gated on an attached client, not on the existence of
a socket.** `spawn()` asks `poller.attachable` and then
`poller.watchers(project)`; both must hold. `attachable` stays exactly as it
is, because DEC-049's help-text test rests on it. A *subscription* is what
counts as a client, not a connection: `pipeline ls` and `pipeline kill`
connect, are answered and go away, and one landing in the same tick as a spawn
would otherwise read as an attached human. The accepted cost is a race the
other way -- a `pipeline tui` opened a second after the spawn gets a headless
stage. Holding a ticket for a human who may never attach is the failure this
gate exists to remove, so that race is not worth closing.

**The permission mode was not the fix, and `pipeline/harnesses/claude-code.toml`
was deliberately not touched.** `interactive_permission_mode = "acceptEdits"`
stays. Once a stage runs on a PTY only while a human is watching, every prompt
is answerable, so it stops mattering whether Claude Code offers `auto`,
`acceptEdits`, or falls back to `manual` -- which is what the ticket's first
question asked. Switching to `auto` would make the pipeline depend on an
account tier, a Claude Code version and an org toggle no dispatcher code can
check, and any diff in that file parks the ticket at `awaiting-merge`
(`machine.FENCED`). A future change that wants `auto` must answer first: what
does the stage do when the mode degrades to `manual` silently?

**The file-ticket skill states the gate, and it is edited through the
template.** `pipeline/templates/skills/file-ticket/SKILL.md` told a session that
under the daemon `planning` "runs on a PTY and waits for a human". That is true
only while a client is subscribed as the stage spawns, so this change rewrites
that bullet in the same commit as `README.md` and `CLAUDE.md`. Nothing tests the
bullet's text -- `CLAUDE.md`'s rule is the only thing keeping it honest. Edit the
template, never `.claude/skills/file-ticket/SKILL.md`, which is a symlink to it
(DEC-056).

**Where the log's `auto mode on` came from is narrowed, not settled.** The
pipeline does not set it: `stage_settings()` writes hooks and nothing else, and
the spawn line in `.project/logs/TICKET-035-planning-ee0c98d7.log` spells
`--permission-mode acceptEdits`. Two candidates remain on the operator's
machine: `permissions.defaultMode = auto` in `~/.claude/settings.json` (which
`--setting-sources project` is supposed to exclude), and
`cachedGrowthBookFeatures.tengu_auto_mode_config.enabled = enabled` in
`~/.claude.json`. Separating them takes one live `claude` session on a PTY with
`CLAUDE_CONFIG_DIR` pointed at an empty directory. If an interactive stage ever
starts prompting for what `acceptEdits` should auto-accept, run that check
first.

## Rollback

Revert the commits on `ticket/059` in reverse order. There is no migration, no
schema change and no protocol change to undo, and
`pipeline/harnesses/claude-code.toml` was never touched. Reverting restores the
old gate: an interactive stage spawns on a PTY under `pipeline start` whether
or not a client is attached.

If only the behaviour is wrong -- say a stage that should be steered runs
headless because the TUI subscribed a moment late -- the narrow revert is the
gate in `spawn()` (`pipeline/daemon/supervisor.py`): drop `attached` and
restore `interactive = cfg.get("mode") == "interactive" and getattr(poller,
"attachable", False)`. `watchers()` in `pipeline/daemon/server.py` is then
unused but harmless, and
`tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon`
goes red again, which is the signal that the ticket is back where it started.

## Thread

### 2026-08-26 15:27:52Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### triage

Reproduced the attachable-vs-attached defect directly: `supervisor.spawn()`
(`pipeline/daemon/supervisor.py:361`) reads `poller.attachable`, which is
`True` for any `Server`, including one with zero attached connections.
`tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon`
spawns `planning` against a bare `Server` and gets `rec["mode"] ==
"interactive"` back — a PTY in `acceptEdits`, unattended. Committed at
`40f2551`.

Also checked the ticket's second claim before trusting it:
`.project/logs/TICKET-035-planning-ee0c98d7.log` (2026-08-23, after `23ef892`
added `interactive_permission_mode = "acceptEdits"`) does contain `auto mode
on` and three lines of `Allowed by auto mode classifier`. That confirms the
discrepancy the ticket flags — the running session was in auto mode, not
`acceptEdits` — but I did not trace why; planning still has to decide whether
that is a rendering bug, a session resumed under stale settings, or a Claude
Code default overriding the flag.

Not a `chore`: the ticket names two design decisions the plan must settle
(auto-mode-unavailable fallback, and whether attach-tracking replaces the
attachable check entirely), so this goes through planning rather than a
direct fix.

### 2026-08-26 15:33:26Z · triage · session · session=b93fac35-f65d-4d9d-a9f8-9b1f435bfb7e

`triage` ran as session `b93fac35-f65d-4d9d-a9f8-9b1f435bfb7e`
- replay: `claude --resume b93fac35-f65d-4d9d-a9f8-9b1f435bfb7e`
- log: `.project/logs/TICKET-059-triage-b93fac35.log`

### 2026-08-26 15:33:26Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

### planning

Plan written. The fix is the spawn gate, not the permission mode.

`spawn()` will ask `poller.watchers(project)` as well as `poller.attachable`:
`Server` counts connections holding a subscription, `Poller` returns 0, so a
daemon with no `pipeline tui` on it runs `planning` headless. That is what
`tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon`
asks for.

`pipeline/harnesses/claude-code.toml` is absent from `files_declared`,
deliberately: it is in `machine.FENCED`, and with a human attached a prompt in
`acceptEdits`, `auto` or `manual` is answerable either way, so auto-mode
availability stops deciding anything. Both questions the ticket named are
settled in `## Decisions`.

On the log discrepancy: `~/.claude/settings.json` carries
`permissions.defaultMode = auto` and `~/.claude.json` carries
`cachedGrowthBookFeatures.tengu_auto_mode_config.enabled = enabled`. Either
explains `auto mode on` in `.project/logs/TICKET-035-planning-ee0c98d7.log`.
I could not separate them: my live probe was refused with `Permission for this
action was denied by the Claude Code auto mode classifier.` The pipeline is not
the source -- `stage_settings()` writes hooks only, no permission mode.

Scope: one subsystem, the spawn gate, plus the docs bound to it. Nothing
deferred.

✓ Reproduced: spawn() gates an interactive stage on poller.attachable, true for any Server with no client attached; committed a failing test proving it.

### 2026-08-26 16:55:46Z · planning · session · session=36c85b2b-0565-42a6-8709-c894d03f3741

`planning` ran as session `36c85b2b-0565-42a6-8709-c894d03f3741`
- replay: `claude --resume 36c85b2b-0565-42a6-8709-c894d03f3741`
- log: `.project/logs/TICKET-059-planning-36c85b2b.log`

### 2026-08-26 16:55:46Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Plan written: spawn() gates on an attached client via a new Server.watchers(); the permission mode and the FENCED harness file stay untouched.

### 2026-08-26 17:04:52Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon` fails as required
```
.mkdtemp())
        st = Store(tmp / "events.db")
        srv = Server(st, tmp / "daemon.sock")
        try:
            assert srv.attachable is True
            rec = supervisor.spawn(tmp, tmp, "TICKET-001", "planning",
                                   harness("fake"), srv)
>           assert rec["mode"] == "batch", \
                f"nothing is attached, but spawn() ran a REPL anyway (mode={rec['mode']!r})"
E               AssertionError: nothing is attached, but spawn() ran a REPL anyway (mode='interactive')
E               assert 'interactive' == 'batch'
E                 
E                 - batch
E                 + interactive

tests/test_pty.py:445: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: planning (opus, interactive) pid 566720 -> TICKET-001-planning-1088687d.log
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon` fails on base `main` too -- the bug is not already fixed upstream
```
 'interactive' == 'batch'
E                 
E                 - batch
E                 + interactive

tests/test_pty.py:445: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: planning (opus, interactive) pid 566764 -> TICKET-001-planning-55a783ac.log
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-4p502goe/base
      Built pipeline @ file:///tmp/pipeline-base-4p502goe/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- ok: DEC-041 is superseded -- history, not binding
- acceptance criterion names no test: 6. `pipeline/harnesses/claude-code.toml` is unchanged: `git diff --name-only main...HEAD` does not list it, so the ticket does not park at the `machine.FENCED` gate.

### 2026-08-26 17:04:52Z · plan-validation · transition · to=planning · result=fail

**plan-validation -> planning** (result: `fail`)

Tier A gate failed:
- acceptance criterion names no test: 6. `pipeline/harnesses/claude-code.toml` is unchanged: `git diff --name-only main...HEAD` does not list it, so the ticket does not park at the `machine.FENCED` gate.

### planning

Re-planned after the Tier A gate failed one finding: `acceptance criterion
names no test: 6.`. Two edits, nothing else.

1. Criterion 6 now names a test: `pipeline/harnesses/claude-code.toml` stays
   out of `git diff --name-only main...HEAD`, and
   `tests/test_stages.py::test_the_fenced_list_matches_the_rule_file` passes
   after the `CLAUDE.md` edit. That test is genuinely at risk here: step 15
   edits `CLAUDE.md`, and the test parses the paragraph before `requires human
   review before merge` (`tests/test_stages.py:284`) for backticked tokens. The
   gotcha bullet step 15 rewrites is not in that paragraph, so it should stay
   green.
2. Added step 17, which runs that test and that `git diff`, so an implementer
   can falsify criterion 6 instead of reading it.

Every other gate finding was `ok:`, including that
`tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon`
fails on this branch and on `main`. The design is unchanged: gate `spawn()` on
`poller.watchers(project)` as well as `poller.attachable`, and do not touch
`pipeline/harnesses/claude-code.toml`.

✓ Plan re-issued: criterion 6 names `test_the_fenced_list_matches_the_rule_file`, step 17 checks the diff; nothing else changed.

### 2026-08-26 17:11:01Z · planning · session · session=1e9ca974-a592-459b-a83d-a012800e7c13

`planning` ran as session `1e9ca974-a592-459b-a83d-a012800e7c13`
- replay: `claude --resume 1e9ca974-a592-459b-a83d-a012800e7c13`
- log: `.project/logs/TICKET-059-planning-1e9ca974.log`

### 2026-08-26 17:11:01Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Re-planned: criterion 6 now names test_the_fenced_list_matches_the_rule_file and step 17 checks the diff; design unchanged.

### 2026-08-26 17:11:16Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon` fails as required
```
.mkdtemp())
        st = Store(tmp / "events.db")
        srv = Server(st, tmp / "daemon.sock")
        try:
            assert srv.attachable is True
            rec = supervisor.spawn(tmp, tmp, "TICKET-001", "planning",
                                   harness("fake"), srv)
>           assert rec["mode"] == "batch", \
                f"nothing is attached, but spawn() ran a REPL anyway (mode={rec['mode']!r})"
E               AssertionError: nothing is attached, but spawn() ran a REPL anyway (mode='interactive')
E               assert 'interactive' == 'batch'
E                 
E                 - batch
E                 + interactive

tests/test_pty.py:445: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: planning (opus, interactive) pid 574534 -> TICKET-001-planning-04e8e000.log
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon` fails on base `main` too -- the bug is not already fixed upstream
```
 'interactive' == 'batch'
E                 
E                 - batch
E                 + interactive

tests/test_pty.py:445: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: planning (opus, interactive) pid 574590 -> TICKET-001-planning-fe51ed9e.log
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-t1ux9m5d/base
      Built pipeline @ file:///tmp/pipeline-base-t1ux9m5d/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```
- ok: DEC-041 is superseded -- history, not binding

### plan-validation

**Tier B judgment: FAIL on one item, scope discipline. Seven items pass.**

long: eight scored items, each carries its evidence.

- **Root cause.** Pass. `spawn()` asks "could a client attach?" and acts on the
  answer to "is a client attached?". `attachable` is a class attribute --
  `Server.attachable = True` (`pipeline/daemon/server.py:231`) whatever
  `self.conns` holds. The plan adds the second question rather than making the
  test pass.
- **Decision conflict.** Pass. I read DEC-049, DEC-052, DEC-055, DEC-011.
  DEC-049 binds `Server.attachable is True and Poller.attachable is False`
  (`tests/test_cli.py:162`); the plan keeps both and extends that test. DEC-011
  freezes the wire protocol; `watchers()` adds no op, so `OPS` is unchanged.
  DEC-055 keeps the geometry marker interactive-only; step 7 keeps `Attachable`
  on the interactive path. Nothing is superseded.
- **Falsifiable criteria.** Pass. Criterion 1's test fails on this branch and on
  `main` (`AssertionError: ... mode='interactive'`). The step-1 test asserts
  four distinct facts, including `srv.watchers(str(b)) == 0`.
- **No research left.** Pass. Every step names a file and a line. I read each:
  `server.py:156`, `:231`, `supervisor.py:361`, `:1189`, `test_pty.py:395`,
  `cli/main.py:509-522`, `README.md:127`.
- **Riskiest step.** Pass. Step 5, the gate. `## Rollback` names the fallback
  for that step: restore `interactive = cfg.get("mode") == "interactive" and
  getattr(poller, "attachable", False)`.
- **Regression surface.** Pass. Two tests expect the interactive path, both via
  `Attachable` (`tests/test_pty.py:420`, `:468`); step 7 covers both.
  `test_the_fenced_list_matches_the_rule_file` parses only the paragraph before
  `requires human review before merge` (`tests/test_stages.py:285`), and step
  15's bullet is not in it. `test_the_help_text_matches_the_code_it_describes`
  lowercases the help output, so step 11's `"attached" in start` holds.
- **Blast radius.** Pass. `bugfix`, 8 files: 2 source, 3 test, 3 doc. The
  behaviour change is 4 lines in `spawn()` plus one method on two classes.
- **Scope discipline. FAIL.** The plan omits a file the repo's own rule
  requires, and criterion 6 forbids adding it. `CLAUDE.md` says a change to a
  stage's behaviour "is not finished until the skill says the same thing".
  `pipeline/templates/skills/file-ticket/SKILL.md:141-144` says: "`planning` is
  `mode: interactive`, so under the daemon it runs on a PTY and waits for a
  human to answer its first approval prompt". After this change that holds only
  while a client is subscribed before the spawn. No step edits it, and
  criterion 6 pins `git diff --name-only main...HEAD` to eight paths -- so an
  implementer who corrects the skill fails a criterion. Fix: add
  `pipeline/templates/skills/file-ticket/SKILL.md` to `files_declared`, add a
  step that rewrites that bullet, and let criterion 6 list nine paths.

Two notes that do not block:

1. Step 1's test registers two projects and never unregisters them.
   `test_the_registry_skips_junk_lines_and_can_drop_a_vanished_project`
   (`tests/test_daemon.py:402`) overwrites the registry file wholesale, so the
   leak does not reach `assert registry.projects() == []` at `:411`. Add
   `registry.unregister(a)` and `registry.unregister(b)` to the `finally`.
2. Step 10 says "`RUN_DESC` keeps its first three sentences with the last one
   replaced". `RUN_DESC` has three sentences, not four. The replacement text is
   quoted verbatim, so the intent is clear: keep sentences 1 and 2.

### 2026-08-26 17:15:47Z · plan-validation · session · session=68bceec9-bc08-4181-8490-58af65905ff6

`plan-validation` ran as session `68bceec9-bc08-4181-8490-58af65905ff6`
- replay: `claude --resume 68bceec9-bc08-4181-8490-58af65905ff6`
- log: `.project/logs/TICKET-059-plan-validation-68bceec9.log`

### 2026-08-26 17:15:47Z · plan-validation · transition · to=planning · result=fail · marker=yes

**plan-validation -> planning** (result: `fail`)

✓ Seven items pass; scope discipline fails: no step updates file-ticket/SKILL.md, and criterion 6's eight-path diff forbids adding it.

### planning

Re-planned after plan-validation failed scope discipline. Four edits, design
unchanged.

1. Step 16 (new) rewrites the bullet at
   `pipeline/templates/skills/file-ticket/SKILL.md:141-144` and quotes the
   replacement text in full. The old steps 16 and 17 become 17 and 18. Step 17
   commits the skill with `README.md` and `CLAUDE.md`.
2. `files_declared` and criterion 6 list nine paths, adding
   `pipeline/templates/skills/file-ticket/SKILL.md`. Criterion 7 (new) checks
   the skill: `grep -c 'but only when a client is already'` prints `1`,
   and `tests/test_stages.py::test_the_repo_skill_is_the_packaged_file` passes.
3. Step 1's `finally` now calls `registry.unregister(a)` and
   `registry.unregister(b)`.
4. Step 10 now says `RUN_DESC` keeps its first two sentences and replaces the
   third. The quoted replacement text is unchanged.

Three facts I checked before writing step 16:

- `pipeline/templates/skills/file-ticket/SKILL.md` is not in `machine.FENCED`
  (`pipeline/core/machine.py:32-50`), so the edit does not park the ticket at
  `awaiting-merge`.
- No test reads that bullet. `test_the_docs_name_the_skill_init_installs`
  (`tests/test_stages.py:213`) reads `CLAUDE.md` and `README.md` only.
- DEC-056 (active) makes the template the only copy. `ls -l` prints
  `SKILL.md -> ../../../pipeline/templates/skills/file-ticket/SKILL.md`, so
  step 16 edits the template and
  `test_the_repo_skill_is_the_packaged_file` stays green.

### 2026-08-26 17:18:40Z · planning · session · session=75bc727e-c366-491f-8f7e-ff6f6c244058

`planning` ran as session `75bc727e-c366-491f-8f7e-ff6f6c244058`
- replay: `claude --resume 75bc727e-c366-491f-8f7e-ff6f6c244058`
- log: `.project/logs/TICKET-059-planning-75bc727e.log`

### 2026-08-26 17:18:40Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ Re-planned for scope discipline: step 16 rewrites file-ticket/SKILL.md, nine declared paths, criteria 6-7 updated.

### 2026-08-26 17:18:55Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon` fails as required
```
.mkdtemp())
        st = Store(tmp / "events.db")
        srv = Server(st, tmp / "daemon.sock")
        try:
            assert srv.attachable is True
            rec = supervisor.spawn(tmp, tmp, "TICKET-001", "planning",
                                   harness("fake"), srv)
>           assert rec["mode"] == "batch", \
                f"nothing is attached, but spawn() ran a REPL anyway (mode={rec['mode']!r})"
E               AssertionError: nothing is attached, but spawn() ran a REPL anyway (mode='interactive')
E               assert 'interactive' == 'batch'
E                 
E                 - batch
E                 + interactive

tests/test_pty.py:445: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: planning (opus, interactive) pid 581593 -> TICKET-001-planning-eed93850.log
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon` fails on base `main` too -- the bug is not already fixed upstream
```
t 'interactive' == 'batch'
E                 
E                 - batch
E                 + interactive

tests/test_pty.py:445: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: planning (opus, interactive) pid 581627 -> TICKET-001-planning-add19731.log
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-dbhm0xg9/base
      Built pipeline @ file:///tmp/pipeline-base-dbhm0xg9/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```
- ok: DEC-041 is superseded -- history, not binding

### plan-validation

**Tier B judgment: PASS. All eight items pass.**

long: eight scored items, each carries the evidence I checked in this tree.

- **Root cause.** Pass. `spawn()` asks "could a client attach?" and acts on the
  answer to "is a client attached?". `attachable` is a class attribute --
  `Server.attachable = True` (`pipeline/daemon/server.py:231`) whatever
  `self.conns` holds. The plan adds the second question; it does not make the
  test pass.
- **Decision conflict.** Pass. DEC-049 binds `Server.attachable is True and
  Poller.attachable is False` (`tests/test_cli.py:162`); step 11 extends that
  test and keeps both attributes. DEC-011 freezes the wire protocol;
  `watchers()` adds no op. DEC-055 keeps the geometry marker interactive-only;
  step 7 keeps `Attachable` on the interactive path. DEC-056 makes the template
  the only copy of the skill; step 16 edits the template. Nothing is superseded.
- **Scope discipline.** Pass -- the item that failed last round. Step 16 rewrites
  `pipeline/templates/skills/file-ticket/SKILL.md:141-144`, criterion 7 pins it,
  and criterion 6, `files_declared` and the frontmatter list the same nine paths.
  Every step traces to a criterion: 1-4 to 3, 5-9 to 1 and 2, 10-14 to 4, 15-16
  to 6 and 7, 17-18 to 5 and 6.
- **Falsifiable criteria.** Pass. Criterion 1's test fails on this branch and on
  `main` (`AssertionError: ... mode='interactive'`). The step-1 test asserts four
  distinct facts, including `srv.watchers(str(b)) == 0`. Criterion 7's phrase
  `but only when a client is already` appears nowhere in the repo today, so its
  `grep -c` prints `1` only after step 16 lands.
- **No research left.** Pass. Every step names a file and a line, and each one
  resolves: `server.py:156`, `:231`, `supervisor.py:361-366`, `:1188-1190`,
  `test_pty.py:395-397`, `cli/main.py:509-522`, `README.md:127`, `:191`,
  `SKILL.md:141-144`. Step 1's test uses only names `tests/test_daemon.py`
  already imports (`json`, `socket`, `tempfile`, `Path`, `Conn`, `Server`,
  `registry`, `store`, `server_on`). `Server.__init__` sets `self.states`
  (`server.py:240`), so `_op_ping` does not raise on a server `serve()` never
  touched, and `registry.register()` needs a `.project/` directory
  (`registry.py:62`), which the test makes for both projects.
- **Riskiest step.** Pass. Step 5, the gate. `## Rollback` names its fallback:
  restore `interactive = cfg.get("mode") == "interactive" and getattr(poller,
  "attachable", False)`.
- **Regression surface.** Pass. Two tests expect the interactive path, both
  through `Attachable` (`tests/test_pty.py:420`, `:468`); step 7 covers both.
  `poller=None` short-circuits, because `getattr(None, "attachable", False)` is
  false and the plan asks `watchers()` second.
  `test_the_fenced_list_matches_the_rule_file` parses only the paragraph before
  `requires human review before merge` (`tests/test_stages.py:285`), and step
  15's bullet is in the gotcha list, not that paragraph.
  `test_the_help_text_matches_the_code_it_describes` lowercases the help output
  (`tests/test_cli.py:172`), so step 11's `"attached" in start` holds; both new
  descriptions keep `planning`, `pipeline tui` and `headless`. Step 14's README
  line still starts `pipeline start ` and contains `tui`
  (`tests/test_cli.py:182-184`). `test_the_repo_skill_is_the_packaged_file`
  compares the symlink to `C.SKILL_TEMPLATE` (`tests/test_stages.py:207`), which
  is the file step 16 edits.
- **Blast radius.** Pass. `bugfix`, nine files: three source (`server.py`,
  `supervisor.py`, `cli/main.py`), three tests, three prose (`README.md`,
  `CLAUDE.md`, `SKILL.md`). Each prose file is bound by a test or by the rule
  file, and the behaviour change is two lines in `spawn()`.

### 2026-08-26 17:23:01Z · plan-validation · session · session=3fde3827-bef6-4d84-b978-32ec4e5425d4

`plan-validation` ran as session `3fde3827-bef6-4d84-b978-32ec4e5425d4`
- replay: `claude --resume 3fde3827-bef6-4d84-b978-32ec4e5425d4`
- log: `.project/logs/TICKET-059-plan-validation-3fde3827.log`

### 2026-08-26 17:23:01Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Tier B judgment: all eight items pass; scope discipline closed by step 16 and criterion 7.

### 2026-08-26 17:28:08Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-26 18:50:55Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon` fails as required
```
.mkdtemp())
        st = Store(tmp / "events.db")
        srv = Server(st, tmp / "daemon.sock")
        try:
            assert srv.attachable is True
            rec = supervisor.spawn(tmp, tmp, "TICKET-001", "planning",
                                   harness("fake"), srv)
>           assert rec["mode"] == "batch", \
                f"nothing is attached, but spawn() ran a REPL anyway (mode={rec['mode']!r})"
E               AssertionError: nothing is attached, but spawn() ran a REPL anyway (mode='interactive')
E               assert 'interactive' == 'batch'
E                 
E                 - batch
E                 + interactive

tests/test_pty.py:445: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: planning (opus, interactive) pid 650465 -> TICKET-001-planning-ca568ed5.log
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.10s ===============================

```
- ok: `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon` fails on base `main` too -- the bug is not already fixed upstream
```
t 'interactive' == 'batch'
E                 
E                 - batch
E                 + interactive

tests/test_pty.py:445: AssertionError
----------------------------- Captured stdout call -----------------------------
  start TICKET-001: planning (opus, interactive) pid 650501 -> TICKET-001-planning-28ddc5e0.log
=========================== short test summary info ============================
FAILED tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-1bufyynh/base
      Built pipeline @ file:///tmp/pipeline-base-1bufyynh/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 9ms

```
- ok: DEC-041 is superseded -- history, not binding

### 2026-08-26 18:50:55Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### implementing

Todo, one entry per plan step:

1. [x] add failing `test_watchers_counts_a_subscribed_client_not_a_one_shot_request`
2. [x] run it, confirm `AttributeError`
3. [x] add `watchers()` to `Poller` and `Server`
4. [x] run `tests/test_daemon.py`, commit
5. [x] replace the gate in `supervisor.py:361`
6. [x] append the comment paragraph
7. [x] give `Attachable` in `test_pty.py` a `watchers()`
8. [x] rewrite `run()` docstring
9. [x] run `tests/test_pty.py`, commit
10. [x] rewrite `START_DESC`/`RUN_DESC`
11. [x] extend `test_the_help_text_matches_the_code_it_describes`
12. [x] run `tests/test_cli.py`, commit
13. [x] rewrite README interactive-stages paragraph
14. [x] rewrite README line 127
15. [x] rewrite CLAUDE.md gotcha bullet
16. [x] rewrite file-ticket SKILL.md bullet
17. [x] run full suite, commit docs
18. [x] final diff check against files_declared

All 18 steps done, four commits: `3aa8690` (watchers()), `c7a76bf` (the gate),
`20b9b08` (help text), `796192e` (README/CLAUDE.md/SKILL.md).

Verified each acceptance criterion:

1. `tests/test_pty.py::test_an_interactive_stage_needs_an_attached_client_not_just_a_daemon` passes.
2. Both interactive-path tests in `tests/test_pty.py` pass (17 passed).
3. `tests/test_daemon.py::test_watchers_counts_a_subscribed_client_not_a_one_shot_request` passes (37 passed).
4. `tests/test_cli.py::test_the_help_text_matches_the_code_it_describes` passes with its two new assertions (20 passed).
5. `uv run --group dev pytest -q` -- `317 passed`, no skips.
6. `git diff --name-only main...HEAD` lists exactly the nine `files_declared` paths; `pipeline/harnesses/claude-code.toml` absent. `test_the_fenced_list_matches_the_rule_file` passes.
7. `grep -c 'but only when a client is already' pipeline/templates/skills/file-ticket/SKILL.md` prints `1`; `test_the_repo_skill_is_the_packaged_file` passes.

No deviation from the plan. `pipeline/harnesses/claude-code.toml` was never touched.

✓ Plan executed as written across 18 steps, four commits; full suite green (317 passed); all seven acceptance criteria verified directly.

### 2026-08-26 18:54:45Z · implementing · session · session=57226f37-6317-4887-811c-1b3e45340564

`implementing` ran as session `57226f37-6317-4887-811c-1b3e45340564`
- replay: `claude --resume 57226f37-6317-4887-811c-1b3e45340564`
- log: `.project/logs/TICKET-059-implementing-57226f37.log`

### 2026-08-26 18:54:45Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ Executed all 18 plan steps via TDD; spawn() now gates on watchers() plus attachable; full suite 317 passed, diff matches the nine declared paths.

### review

Reviewed the whole branch delta (no earlier review entry): `main...HEAD`, five
commits, nine files, `128 insertions(+), 28 deletions(-)`.

No blocking findings. `uv run --group dev pytest -q` -> `317 passed in 13.74s`,
no skips. `git status --porcelain` is empty; I changed no file but this ticket.

Verified each acceptance criterion against the code, not the thread:

1. The gate reads `attached = poller.watchers(str(project.resolve())) if
   getattr(poller, "attachable", False) else 0`
   (`pipeline/daemon/supervisor.py:367`), and `interactive` requires
   `attached > 0`. `interactive` still selects `interactive_cmd` and the
   geometry marker (`:396`, `:399`).
2. `Attachable` returns `watchers() == 1` (`tests/test_pty.py:400`), so both
   interactive-path tests keep the PTY.
3. `Server.watchers()` counts connections, not subscriptions:
   `any(...) for c in self.conns.values()`. `_drop()` pops the connection
   (`pipeline/daemon/server.py:401`) and `_read()` calls `_drop` on EOF
   (`:390`), so a dead TUI stops counting on the next poll.
4. Path forms match: `_project()` stores `str(Path(p).resolve())` (`:479`) and
   `spawn()` passes `str(project.resolve())`.
5. The diff lists exactly the nine `files_declared` paths;
   `pipeline/harnesses/claude-code.toml` is absent.
6. `grep -c 'but only when a client is already'` prints `1`;
   `.claude/skills/file-ticket/SKILL.md` is still the symlink.

Two findings I dropped. An unfiltered `pipeline tui` counts as a watcher for
every project -- refuted by `pipeline/tui/app.py:415`, where `attach` takes the
row's project, so that human can reach any PTY. `rec` is unbound in the new
test's `finally` if `spawn()` raises -- refuted as new by the identical pattern
at `tests/test_pty.py:427`.

Non-blocking note (severity: minor). `pipeline/daemon/supervisor.py:353` still
reads `interactive WHEN a human can reach it`, which the paragraph below it at
`:361` and `README.md` now correct to "while a human is attached". One comment,
no behaviour.

✓ Delta reviewed, seven criteria verified, 317 passed; no blocking findings.

### 2026-08-26 19:09:24Z · review · session · session=98ef1335-c35e-4433-a9c2-9a9d8b5ae5d7

`review` ran as session `98ef1335-c35e-4433-a9c2-9a9d8b5ae5d7`
- replay: `claude --resume 98ef1335-c35e-4433-a9c2-9a9d8b5ae5d7`
- log: `.project/logs/TICKET-059-review-98ef1335.log`

### 2026-08-26 19:09:24Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ Delta reviewed: gate, watchers(), tests and docs match the plan and all seven criteria; 317 passed; no blocking findings.

### 2026-08-26 19:09:39Z · verifying · transition · to=merging · result=clean

**verifying -> merging** (result: `clean`)

regression suite passed; the diff touches no fenced code

### 2026-08-26 19:09:40Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git rebase main || git rebase --abort 2>/dev/null
git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/059


Current branch ticket/059 is up to date.
Already up to date.
Updating fe2ae93..796192e
Fast-forward
 CLAUDE.md                                      | 12 ++++++---
 README.md                                      | 17 ++++++------
 pipeline/cli/main.py                           |  9 ++++---
 pipeline/daemon/server.py                      | 18 +++++++++++++
 pipeline/daemon/supervisor.py                  | 25 ++++++++++++-----
 pipeline/templates/skills/file-ticket/SKILL.md |  7 ++---
 tests/test_cli.py                              |  2 ++
 tests/test_daemon.py                           | 37 ++++++++++++++++++++++++++
 tests/test_pty.py                              | 29 +++++++++++++++++++-
 9 files changed, 128 insertions(+), 28 deletions(-)

```

### 2026-08-26 19:09:40Z · merging · decision

decision recorded as `DEC-059`
