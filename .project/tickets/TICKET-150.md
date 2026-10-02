---
id: TICKET-150
stage: done
class: feature
branch: ticket/150
test_file:
- tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
- tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
deletes: []
files_declared:
- CLAUDE.md
- README.md
- pipeline/cli/main.py
- pipeline/core/config.py
- pipeline/core/machine.py
- pipeline/core/worktree.py
- pipeline/daemon/supervisor.py
- pipeline/templates/pipeline.toml
- pipeline/templates/skills/file-ticket/SKILL.md
- pipeline/tui/app.py
- tests/helpers.py
- tests/test_cli.py
- tests/test_config.py
- tests/test_dispatch.py
- tests/test_machine.py
- tests/test_tui.py
- tests/test_worktree.py
counters:
  plan_validation_attempts: 1
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  plan_steps: 15
  plan_files: 17
  no_result: 0
  stale_regate: 1
  stale_regate_cleared: 1
lease:
  holder: null
  expires: null
depends_on: []
last_session:
  stage: review
  id: d735c14f-52ac-43b2-b589-2087f48b93d5
  replay: claude --resume d735c14f-52ac-43b2-b589-2087f48b93d5
  log: .project/logs/TICKET-150-review-d735c14f.log
  cost_usd: 0.859718
approved_by: chezzijr
approved_at: '2026-10-02T07:13:07.128885+00:00'
---

## Summary

Ticket branches are cut from a possibly stale local base, and a team that lands through pull requests sees every finished ticket as escalated

Expected change files: `pipeline/core/worktree.py`, `pipeline/core/machine.py`, `pipeline/daemon/supervisor.py`, `pipeline/core/config.py`, `pipeline/cli/main.py`, `pipeline/templates/pipeline.toml`, `pipeline/templates/skills/file-ticket/SKILL.md`, `tests/test_worktree.py`, `tests/test_machine.py` and `tests/test_daemon.py`.

Found on the first JavaScript project, whose team merges through pull requests. Both parts are about how a ticket branch relates to the shared base. Each needs its own failing test.

**1. Branches are cut from local `<base>`, never fetched.** `pipeline/core/worktree.py:105`, on main at a2365c1: `git worktree add -b {branch} {wt} {base_ref(cfg)}`, where `base_ref` is `cfg.get("base", "main")`. Nothing runs `git fetch` or compares with the upstream. On the JS run the local base was 10 commits behind its remote; all 8 tickets were planned and verified against old code, and 3 of 8 conflicted when pushed. Expected: when `<base>` has an upstream, the dispatcher warns (thread note on the ticket and a `diagnostics` row) when local `<base>` is behind it at branch-cut time. Whether to also fetch and branch from the upstream is planning's call; a fetch must never move the main checkout's branch.

**2. No way to stop at "branch ready" without it reading as a failure.** The team stops at merge on purpose: with the main checkout off base, `merging` refuses ("main checkout is parked on ..., not the base branch -- refusing to land") and the ticket shows `escalated`, the same as a real failure. `depends_on` is satisfied only by `done` (`pipeline/core/machine.py:379`: `if stages.get(dep) != "done"`), so a dependent ticket in such a project waits forever. Expected: a project setting (e.g. `merge = "local"` default, `merge = "none"`) under which a verified ticket ends in its own terminal, non-failure state with its branch kept (no push, no PR creation -- the human does that); `ls` shows it distinctly from `escalated`, and `depends_on` accepts that state. The new transition row touches `transition()`, which is fenced -- this ticket will park at `awaiting-merge`.

Out of scope, recorded for later: a `branch_template` / `external_id` for branch names, squashing, and keeping `TICKET-NNN` ids out of code comments and test names.


## Reproduction

Two tests, both fail on base.

1. `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns`: local main is 1 commit behind origin/main; `ensure_worktree` prints nothing.
2. `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on`: `dep_holder` returns `('A', 'branch-ready')`. The state name `branch-ready` is a placeholder; planning may rename it and the test.

Command: `uv run --group dev pytest -q tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on`

expect: AssertionError: no warning that base is behind its upstream
expect: AssertionError: assert ('A', 'branch-ready') is None

## Digest

Scope: both parts plan as one ticket. They share `pipeline/daemon/supervisor.py:start()` and the docs, and each part is testable alone.

Part 1 -- stale base at branch-cut time:
- `pipeline/core/worktree.py:ensure_worktree()` (line 90) cuts with `git worktree add -b {branch} {wt} {base_ref(cfg)}` only when the branch does not exist yet (`branch_exists` is False). That branch is the only place a fetch and a lag check run. Its one caller is `pipeline/daemon/supervisor.py:start()` line 902, right after `drain_all(inflight)`, so a blocking call there is already accepted (worktree_setup blocks too).
- Upstream of base: `git rev-parse --abbrev-ref --symbolic-full-name main@{upstream}` prints `origin/main`; exit non-zero when base tracks nothing. Lag: `git rev-list --count main..main@{upstream}`. Remote name: `git config --get branch.main.remote`.
- `run_cmd()` returns `stdout + stderr` and has no timeout. Read the FIRST non-empty line of its output (DEC-115). The fetch needs a timeout, so it calls `subprocess.run` with list args, through `retry_eagain()` and `project_env()`, like `head_file()` does.
- `start()` holds the `Ticket` `t` and appends thread notes with `t.append(stage, "note", text)` then `t.save()`.
- `pipeline/cli/main.py:cmd_diagnostics()` (line 643) prints nine `label: value` rows. `tests/test_cli.py` parses them with `dict(l.split(": ", 1) ...)`. DEC-115 makes diagnostics read-only, so its new `base` row never fetches.

Part 2 -- `merge = "none"`:
- `transition()` in `pipeline/core/machine.py` is fenced. Add one row: `("merging", "kept") -> "branch-ready"`. The dispatcher issues `kept` itself, like `approved` and `clean`; no agent can.
- `start()` (supervisor line ~924) handles `stage == "merging"` by spawning `merge_cmd()`. `verifying` reaches `merging` on `clean`, or via `awaiting-merge` + `pipeline approve` on a fenced diff. Both routes pass through that one branch.
- `advance()` (supervisor line 89): `if nxt == "done": record_decision(...)`, and `if nxt in CLEANUP_STAGES:` commits the record onto base.
- `start()`'s `if stage in TERMINAL:` branch drops the worktree for stages in `CLEANUP_STAGES`. `git worktree remove` keeps the branch.
- `dep_holder()` (machine.py line 374) accepts only `done`.
- `FINISHED = TERMINAL - {"escalated"}` exists twice: `pipeline/cli/main.py:554` (bare `ls`) and `pipeline/tui/app.py:60` (tree). DEC-116 keeps the two equal.
- Config helpers in `pipeline/core/config.py` read `project_config()` (git HEAD, else disk). `tests/helpers.git_project()` leaves `.project/pipeline.toml` untracked, so appending to it on disk works in tests. A bad value is printed once through `notice_once(msg, *key)`; `reset_notices()` is the test seam.

Gotchas:
- A test helper that commits must `git add g.py`, never `git add -A`: `-A` sweeps the untracked `.project/` into the commit, and the following `git reset --hard HEAD~1` deletes the ticket files from disk.
- `tests/test_machine.py::test_escalated_tickets_keep_their_worktree` asserts `M.CLEANUP_STAGES == {"done", "rejected"}`; step 6 updates it.
- `tests/test_cli.py::test_diagnostics_documentation_explains_rows_and_force_boundary` reads README.md and the file-ticket SKILL.md; the "nine rows" text lives in both.
- Merging-stage tests in `tests/test_dispatch.py` (e.g. `test_a_ticket_held_at_merging_is_rebased_before_the_merge_is_attempted`) show the pattern: `FIXTURE.replace("stage: plan-validation", "stage: merging")`, `supervisor.start(d, path, harness("fake"), {})`.
- `advance()` skips `commit_record()` when HEAD is off base (`elif code or head.strip() != base:`, supervisor.py line 157). A test that parks the checkout off base therefore cannot catch a record commit; the `merge = "none"` no-commit test keeps the checkout on `main`. `commit_record()` always stages the ticket file itself, so `git ls-files .project/` is non-empty after any commit.
- `tests/test_daemon.py`, named in `## Summary`, holds no `start()` or merging test; the dispatcher tests go in `tests/test_dispatch.py` instead.

Baseline measured 2026-10-02 on ee4963d: `uv run --group dev pytest -q tests/test_worktree.py tests/test_machine.py tests/test_cli.py tests/test_dispatch.py tests/test_tui.py tests/test_config.py` printed `2 failed, 360 passed`; the 2 are this ticket's repro tests.

## Decisions checked

- DEC-115 (active): `pipeline diagnostics` is read-only and git probes read the first non-empty line. The new `base` row compares against the last-fetched ref and never fetches.
- DEC-147 (active): the lockfile row is informational, never a non-zero exit. The `base` row follows the same rule.
- DEC-116 and DEC-060 (active): bare `ls` and the TUI tree hide only stages nobody must act on, and stay equal. `branch-ready` needs a human (push, PR), so both keep it visible.
- DEC-139 (active, supersedes DEC-100): `escalated` stays in `TERMINAL`; dependency satisfiability is decided in `dep_holder()`/`dep_unsatisfiable()`. This plan adds `branch-ready` to what satisfies, and changes nothing else there.
- DEC-091 (active): the `TERMINAL` cleanup branch of `start()` loads config wrapped. Unchanged; `branch-ready` reuses that branch.
- DEC-105 (active): `merge_cmd()`'s rebase guard. Untouched; `merge = "none"` never calls `merge_cmd()`.
- DEC-029 (active): parked tickets hold no inflight record. Unchanged.
- Grep terms: `upstream`, `git fetch`, `depends_on`, `dep_holder`, `CLEANUP_STAGES`, `TERMINAL`, `diagnostics`, `FINISHED`, `merge_cmd`, `parked on`.

## Plan

1. Add `upstream_ahead(d, sh) -> Path` to `tests/helpers.py`: `git clone -q --bare {d} {remote}` into `tempfile.mkdtemp()`, then `git remote add origin {remote} && git fetch -q origin && git branch -u origin/main main`, write `g.py` = `later`, then `git add g.py && git commit -qm later && git push -q origin main && git reset -q --hard HEAD~1`; return `remote`. Never `git add -A` (see Digest).
2. Add two tests to `tests/test_worktree.py`, then run them and watch the first fail: (a) `test_a_branch_cut_fetches_the_upstream_and_leaves_base_alone(capsys)` -- `d, sh = git_project()`; bare remote via `git clone -q --bare`; `git remote add origin`, `git fetch -q origin`, `git branch -u origin/main main`; a second clone (`git clone -q {remote} {tmp2}`, set `user.email`/`user.name`, commit `h.py`, `git push -q origin main`); assert `sh("git rev-list --count main..origin/main").stdout.strip() == "0"`; save `old = sh("git rev-parse main").stdout`; call `W.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})`; assert `"behind" in capsys.readouterr().out`, `sh("git rev-parse main").stdout == old`, `sh("git rev-parse ticket/001").stdout == old`, and `git rev-list --count main..origin/main` prints `1`. (b) `test_a_base_with_no_upstream_cuts_without_a_warning(capsys)` -- `git_project()`, `ensure_worktree(...)` returns a dir, and the captured out contains neither `behind` nor `fetch`.
3. In `pipeline/core/worktree.py` add `FETCH_TIMEOUT = 20` and three functions below `base_ref()`, then extend `ensure_worktree()`:
    - `base_upstream(project, cfg) -> str | None`: runs `git rev-parse --abbrev-ref --symbolic-full-name {shlex.quote(base_ref(cfg) + "@{upstream}")}` through `run_cmd`; returns the first non-empty output line on exit 0, else None.
    - `base_lag(project, cfg) -> tuple[str, int] | None`: None when `base_upstream()` is None; else runs `git rev-list --count {shlex.quote(base + ".." + base + "@{upstream}")}` and returns `(upstream, int(first_line))`; None when the exit is non-zero or the line is not all digits. Read-only, no fetch.
    - `fetch_base(project, cfg, timeout=FETCH_TIMEOUT) -> str | None`: None (nothing to do) when `base_upstream()` is None; reads `git config --get {shlex.quote("branch." + base + ".remote")}`; returns None without fetching when the remote is empty, `.`, or starts with `-`. Else `retry_eagain(lambda: subprocess.run(["git", "fetch", "--quiet", remote], cwd=project, stdin=subprocess.DEVNULL, capture_output=True, text=True, env={**project_env(), "GIT_TERMINAL_PROMPT": "0"}, timeout=timeout))`; returns None on exit 0, `f"git fetch {remote} exited {rc}: {first stderr line}"` otherwise, `f"git fetch {remote} timed out after {timeout}s"` on `subprocess.TimeoutExpired`, and `f"git fetch {remote} failed: {e}"` on `OSError`. Docstring: a plain remote fetch only updates `refs/remotes/`, never a local branch, so the main checkout's branch cannot move.
    - `ensure_worktree(project, meta, cfg, notes: list[str] | None = None)`: inside the `not branch_exists` path only, before `git worktree add`, build a message list: if `fetch_base()` returns an error, add ``f"could not fetch `{base}`'s upstream ({err}); comparing against the last fetched copy"``; then if `base_lag()` gives `(up, n)` with `n > 0`, add ``f"`{meta['branch']}` is cut from local `{base}`, which is {n} commit(s) behind `{up}` -- every stage of this ticket sees the older code. `git pull --ff-only` on `{base}` in the main checkout catches it up for later tickets."``. For each message `print(f"  {meta['id']}: {msg}")` and, when `notes` is not None, `notes.append(msg)`. Run step 2's tests and `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns`; all pass.
4. Add `test_a_branch_cut_behind_its_upstream_notes_the_ticket` to `tests/test_dispatch.py`: `d, sh = git_project()`; `upstream_ahead(d, sh)` (import it from `helpers`); `path.write_text(FIXTURE.replace("stage: plan-validation", "stage: verifying"))`; `did, rec = supervisor.start(d, path, harness("fake"), {})`; assert `did and rec`; `rec["proc"].wait()`; `supervisor.finish(d, rec)`; assert `"behind" in Ticket.load(path).section("Thread")`. Run it and watch it fail.
5. In `pipeline/daemon/supervisor.py:start()`, replace `wt = ensure_worktree(project, t.frontmatter(), cfg)` with `notes: list[str] = []` and `wt = ensure_worktree(project, t.frontmatter(), cfg, notes)`; after the `wt is None` bail, `for n in notes: t.append(stage, "note", n)` and `if notes: t.save()`. Run step 4's test; it passes. Commit `fix(TICKET-150): warn when a ticket branch is cut from a base behind its upstream`.
6. In `tests/test_machine.py` add `test_merging_kept_ends_at_branch_ready`: `assert M.transition("merging", "kept", {}) == ("branch-ready", {})`; `"branch-ready" in M.TERMINAL`, `in M.CLEANUP_STAGES`, `in M.KNOWN_STAGES`, and `M.VERIFIED == {"done", "branch-ready"}`. In `test_escalated_tickets_keep_their_worktree` change the last assertion to `M.CLEANUP_STAGES == {"done", "rejected", "branch-ready"}`. Run; watch it fail.
7. In `pipeline/core/machine.py`: set `TERMINAL = {"done", "rejected", "escalated", "branch-ready"}`; add below it `VERIFIED = {"done", "branch-ready"}` with a comment (the two stages a verified ticket ends in; both satisfy `depends_on` and both record `## Decisions`); set `CLEANUP_STAGES = {"done", "rejected", "branch-ready"}` with a comment that cleanup drops the worktree and keeps the branch; add `case ("merging", "kept"): return "branch-ready", c` after `("merging", "fail")`, commented: the dispatcher issues `kept` under `merge = "none"`, the branch is kept, nothing lands on base or is pushed, and no counter is charged; in `dep_holder()` change `!= "done"` to `not in VERIFIED` and say `done` or `branch-ready` in its docstring. Run `tests/test_machine.py`; step 6's test and `test_a_dependency_at_branch_ready_satisfies_depends_on` pass.
8. In `tests/test_config.py` add `test_merge_mode_defaults_to_local_and_ignores_a_bad_value(capsys)`: `reset_notices()`; `merge_mode(Path("/p"), {}) == "local"`; `merge_mode(Path("/p"), {"merge": "none"}) == "none"`; `merge_mode(Path("/p"), {"merge": "pr"}) == "local"` and `"merge" in capsys.readouterr().out`. Run; watch it fail on the import.
9. In `pipeline/core/config.py` add `MERGE_MODES = ("local", "none")` and `merge_mode(project: Path, cfg: dict) -> str` below `project_conflict_ignore()`: `v = cfg.get("merge", "local")`; return `v` when `isinstance(v, str) and v in MERGE_MODES`; otherwise `notice_once(f"  {project}: ignoring merge = {v!r} (want \"local\" or \"none\")", str(project), "merge-mode")` and return `"local"`. Docstring: `local` lands on base in the main checkout; `none` stops at `branch-ready`. Run step 8's test; it passes.
10. In `tests/test_dispatch.py` add two tests, then run both and watch them fail: (a) `test_merge_none_ends_a_verified_ticket_at_branch_ready_with_its_branch_kept`: `d, sh = git_project()`; append `merge = "none"` to `d/.project/pipeline.toml`; ticket at `stage: merging`; `wt = supervisor.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})`, commit `ticket.py` there with `_commit(wt, "'ticket commit'")`; `tip = rev-parse ticket/001`; `sh("git checkout -qb somewhere-else")`; `base = rev-parse main`; `did, rec = supervisor.start(d, path, harness("fake"), {})`; assert `did and rec is None`, stage `branch-ready`, thread contains `merge = "none"` and `no `## Decisions` section`, `rev-parse main` == `base`; then a second `supervisor.start(...)` returns `did` True, `wt.is_dir()` is False, and `rev-parse ticket/001` == `tip`. (b) `test_merge_none_never_commits_onto_base_from_a_checkout_on_base`: same setup as (a) except the checkout STAYS on `main` (no `git checkout -qb`), and the ticket text is `FIXTURE.replace("stage: plan-validation", "stage: merging").replace("## Thread", "## Decisions\nkeep the branch\n## Thread")`; `base = rev-parse main`; `did, rec = supervisor.start(d, path, harness("fake"), {})`; assert `did and rec is None`, stage `branch-ready`, `(d / ".project/decisions/DEC-001.md").is_file()`, `sh("git rev-parse main").stdout == base`, and `sh("git ls-files .project/").stdout == ""`. Without step 11's `nxt != "branch-ready"` guard, `commit_record()` commits the ticket file and `DEC-001.md` onto `main` and (b) fails on both git asserts; (a) cannot catch that, because `advance()` skips the commit whenever HEAD is off base (`supervisor.py:157`).
11. In `pipeline/daemon/supervisor.py`: import `merge_mode` from `pipeline.core.config` and `VERIFIED` from `pipeline.core.machine`. In `start()`, first inside `if stage == "merging":`, add: `if merge_mode(project, cfg) == "none":` call `advance(project, t, "kept", <note>, emit, agent=False)` and `return True, None`, where the note is ``f"`merge = \"none\"`: nothing landed on `{base_ref(cfg)}` and nothing pushed. Branch `{t.branch}` is kept -- push it and open the pull request, then `pipeline resume {tid} --stage done` once it merges."``. In `advance()` change `if nxt == "done":` to `if nxt in VERIFIED:`, and change `if nxt in CLEANUP_STAGES:` to `if nxt in CLEANUP_STAGES and nxt != "branch-ready":` with a comment that `merge = "none"` never writes base. Run step 10's two tests and `tests/test_dispatch.py`; all pass. Commit `feat(TICKET-150): merge = "none" ends a verified ticket at branch-ready`.
12. In `tests/test_cli.py`: add `test_diagnostics_reports_whether_base_is_behind_its_upstream` (`git_project()`; `rows["base"] == "no upstream for `main`"`; then `upstream_ahead(d, sh)` from `helpers`; `rows["base"].startswith("behind: ")` and exit 0); add `"base"` to the label tuple in `test_diagnostics_exits_nonzero_when_git_author_is_missing`; add `test_bare_ls_keeps_a_branch_ready_ticket`: `filter_ls_rows([{"id": "A", "stage": "branch-ready"}, {"id": "B", "stage": "done"}], None, False, None)` returns only the `A` row. Run; watch them fail.
13. In `pipeline/cli/main.py`: set `FINISHED = TERMINAL - {"escalated", "branch-ready"}` and extend its comment (a `branch-ready` ticket waits on a human to push it); add `base_state(path) -> str` beside `worktree_setup_state()`: `project_config()` wrapped like there (`unknown ({e})`), then `base_lag(path, cfg)` imported from `pipeline.core.worktree`; None -> ``f"no upstream for `{base}`"``; `n == 0` -> ``f"up to date with `{up}` (as of the last fetch)"``; else ``f"behind: `{base}` is {n} commit(s) behind `{up}` (as of the last fetch) -- new tickets branch from the older code"``. In `cmd_diagnostics()` print `base: not applicable (not a git checkout)` in the non-git branch and `base: {base_state(path)}` before `git author` in the git branch; never change the exit code for it; docstring says ten rows. Run step 12's tests; they pass.
14. In `tests/test_tui.py` add `test_the_tree_keeps_a_branch_ready_ticket`: `from pipeline.tui.app import FINISHED`; assert `"branch-ready" not in FINISHED` and `"done" in FINISHED`. Watch it fail, then set `FINISHED = TERMINAL - {"escalated", "branch-ready"}` in `pipeline/tui/app.py` with the same comment as step 13. Run `tests/test_tui.py`; all pass.
15. Update the docs in one commit: `pipeline/templates/pipeline.toml` -- under `base`, say a new ticket branch is cut from LOCAL base after a fetch of its upstream and warns when base is behind; then add a commented `# merge                   = "none"` block explaining `local` (default, lands on base, main checkout must sit on base) vs `none` (stops at `branch-ready`, branch kept, nothing merged or pushed, `depends_on` accepts it). `pipeline/templates/skills/file-ticket/SKILL.md` -- "nine rows" becomes "ten rows" and lists `base` (`no upstream`, `up to date`, or `behind: ...`); the `depends_on` paragraph says it waits for `done` or `branch-ready`; the hand-over section says under `merge = "none"` a verified ticket ends at `branch-ready` (push the branch, open the PR, then `pipeline resume <id> --stage done`). `README.md` -- "nine rows" becomes "ten rows" and gains a `base` bullet. `CLAUDE.md` -- append to the last paragraph: under `merge = "none"` in `.project/pipeline.toml` `merging` never touches the main checkout, so it need not sit on base. Run `uv run --group dev pytest -q tests/test_cli.py tests/test_stages.py`; exit 0. Commit `feat(TICKET-150): document merge = "none", branch-ready and the base row`.

## Acceptance criteria

- `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` passes (step 3).
- `tests/test_worktree.py::test_a_branch_cut_fetches_the_upstream_and_leaves_base_alone` passes (steps 2, 3).
- `tests/test_worktree.py::test_a_base_with_no_upstream_cuts_without_a_warning` passes (steps 2, 3).
- `tests/test_dispatch.py::test_a_branch_cut_behind_its_upstream_notes_the_ticket` passes (steps 1, 4, 5).
- `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` passes (step 7).
- `tests/test_machine.py::test_merging_kept_ends_at_branch_ready` passes (steps 6, 7).
- `tests/test_config.py::test_merge_mode_defaults_to_local_and_ignores_a_bad_value` passes (steps 8, 9).
- `tests/test_dispatch.py::test_merge_none_ends_a_verified_ticket_at_branch_ready_with_its_branch_kept` passes (steps 10, 11).
- `tests/test_dispatch.py::test_merge_none_never_commits_onto_base_from_a_checkout_on_base` passes (steps 10, 11).
- `tests/test_cli.py::test_diagnostics_reports_whether_base_is_behind_its_upstream` passes (steps 1, 12, 13).
- `tests/test_cli.py::test_bare_ls_keeps_a_branch_ready_ticket` passes (steps 12, 13).
- `tests/test_tui.py::test_the_tree_keeps_a_branch_ready_ticket` passes (step 14).
- `uv run --group dev pytest -q tests/test_worktree.py tests/test_machine.py tests/test_cli.py tests/test_dispatch.py tests/test_tui.py tests/test_config.py tests/test_stages.py` exits 0 (steps 1-15). Measured baseline on c8754f0 for all seven files: 2 failed, 412 passed; the 2 are this ticket's repro tests.
- `uv run --group dev pytest -q` exits 0, re-measured at check time (steps 1-15).
- `grep -q 'merge *= *"none"' pipeline/templates/pipeline.toml` exits 0 (step 15).
- `grep -q "branch-ready" pipeline/templates/skills/file-ticket/SKILL.md` exits 0 (step 15).
- `grep -q "nine rows" README.md` exits 1 (step 15).
- `grep -q "nine rows" pipeline/templates/skills/file-ticket/SKILL.md` exits 1 (step 15).

## Decisions

**A ticket branch is cut from LOCAL `<base>`, never from its upstream.** `base_checkout()`, `fenced_touches()`, `merge_cmd()` and `revalidating` all compare against local base. A branch cut from `origin/main` while local `main` lags would carry the upstream commits as the ticket's own diff: review reads them, the fence check flags them, and the merge lands them. The dispatcher fetches and warns instead; catching base up is the human's call.

**The branch-cut fetch never moves a local branch.** `fetch_base()` runs `git fetch --quiet <remote>` with list args and no refspec, so only `refs/remotes/` move. It runs on the dispatcher's loop, so it is bounded: `FETCH_TIMEOUT` (20s), `GIT_TERMINAL_PROMPT=0`, stdin from `/dev/null`. A failed or timed-out fetch is a thread note, never a bail. It runs only when a branch is cut, never on a resume that reuses the branch.

**`pipeline diagnostics` reports the lag as of the last fetch and never fetches** (DEC-115). Its `base` row is informational and never changes the exit code (DEC-147).

**`merge = "none"` never writes the base branch.** `start()` answers `merging` with a dispatcher-issued `kept`, and `transition()` maps `("merging", "kept")` to `branch-ready`. No `merge_cmd()`, no record commit (a local chore commit would diverge base from the upstream the team merges into). A fenced diff still parks at `awaiting-merge` first. The ticket's `## Decisions` is still written to `.project/decisions/`, because nothing else would ever record it. The worktree is dropped and the branch kept, so the human can check it out and push it.

**`branch-ready` satisfies `depends_on`** (`VERIFIED`). The dependent's branch is cut from local base and does NOT contain the dependency's code until the team merges it.

**`branch-ready` stays visible** in bare `ls` and the TUI tree: it is terminal but actionable (DEC-116). `pipeline resume <id> --stage done` clears it after the PR merges.

**A bad `merge` value reads as `local`**, printed once. `local` fails closed: a checkout off base escalates at `merging`, and nothing lands silently.

## Rollback

Revert the three commits from steps 5, 11 and 15 (`git revert`). No data migration: a ticket already at `branch-ready` is the only residue, and `pipeline resume <id> --stage done` (or `--stage merging` under `merge = "local"`) moves it to a stage the reverted code knows.

Riskiest step: step 3, the network fetch inside the dispatcher loop. If step 2's fetch test is flaky or `fetch_base()` cannot be bounded reliably, the fallback is to drop the `fetch_base()` call from `ensure_worktree()` and keep the compare-only warning against the last-fetched ref: delete test (a) of step 2, keep `base_lag()` and the triage repro test, and record the dropped fetch in `## Thread`.

## Thread

### 2026-10-02 02:07:34Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-10-02 · triage · finding

Reproduced both parts; tests committed on ticket/150. Root cause: `ensure_worktree` never compares base with its upstream; `dep_holder` accepts only `done`. Verdict `ok`, not `chore`: the fix needs a design choice (new terminal state, fenced `transition()`).

### 2026-10-02 02:08:24Z · triage · session · session=cee734cf-fac3-4664-a9c2-1606b3889d62

`triage` ran as session `cee734cf-fac3-4664-a9c2-1606b3889d62`
- replay: `claude --resume cee734cf-fac3-4664-a9c2-1606b3889d62`
- log: `.project/logs/TICKET-150-triage-cee734cf.log`
- cost: $0.24 of a $3 cap
- tokens: 4,659 out (365 thinking) · 20 in · 306,992 cache read · 34,034 cache write

### 2026-10-02 02:08:24Z · triage · transition · to=planning · result=ok · marker=yes

**triage -> planning** (result: `ok`)

✓ reproduced both parts with two failing tests

### 2026-10-02 02:17:39Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails as required
```
-cut time."""
        d, sh = git_project()
        remote = Path(tempfile.mkdtemp())
        subprocess.run(f"git clone -q --bare {d} {remote}", shell=True, check=True)
        sh(f"git remote add origin {remote} && git fetch -q origin "
           "&& git branch -u origin/main main")
        (d / "g.py").write_text("later")
        sh("git add -A && git commit -qm later && git push -q origin main"
           " && git reset -q --hard HEAD~1")
        assert "behind 1" in sh("git status -sb").stdout
        W.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.17s ===============================

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails as required
```
============= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-150
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7f320430bf60>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yj_duuja/base
      Built pipeline @ file:///tmp/pipeline-base-yj_duuja/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 57ms

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails on base `main` too -- the bug is not already fixed upstream
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/pipeline-base-yj_duuja/base
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7f82980c0ae0>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: DEC-100 is superseded -- history, not binding
- `files_declared` is empty
- plan step names no declared file: '1. Add `upstream_ahead(d, sh) -> Path` to `tests/helpers.py`: `git clone -q --bare {d} {remote}` into `tempfile.mkdtemp()`, then `git remote add origin {remote} && git fetch -q origin && git branch -u origin/main main`, write `g.py` = `later`, then `git add g.py && git commit -qm later && git push -q origin main && git reset -q --hard HEAD~1`; return `remote`. Never `git add -A` (see Digest).' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '2. Add two tests to `tests/test_worktree.py`, then run them and watch the first fail: (a) `test_a_branch_cut_fetches_the_upstream_and_leaves_base_alone(capsys)` -- `d, sh = git_project()`; bare remote via `git clone -q --bare`; `git remote add origin`, `git fetch -q origin`, `git branch -u origin/main main`; a second clone (`git clone -q {remote} {tmp2}`, set `user.email`/`user.name`, commit `h.py`, `git push -q origin main`); assert `sh("git rev-list --count main..origin/main").stdout.strip() == "0"`; save `old = sh("git rev-parse main").stdout`; call `W.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})`; assert `"behind" in capsys.readouterr().out`, `sh("git rev-parse main").stdout == old`, `sh("git rev-parse ticket/001").stdout == old`, and `git rev-list --count main..origin/main` prints `1`. (b) `test_a_base_with_no_upstream_cuts_without_a_warning(capsys)` -- `git_project()`, `ensure_worktree(...)` returns a dir, and the captured out contains neither `behind` nor `fetch`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '3. In `pipeline/core/worktree.py` add `FETCH_TIMEOUT = 20` and three functions below `base_ref()`, then extend `ensure_worktree()`: - `base_upstream(project, cfg) -> str | None`: runs `git rev-parse --abbrev-ref --symbolic-full-name {shlex.quote(base_ref(cfg) + "@{upstream}")}` through `run_cmd`; returns the first non-empty output line on exit 0, else None. - `base_lag(project, cfg) -> tuple[str, int] | None`: None when `base_upstream()` is None; else runs `git rev-list --count {shlex.quote(base + ".." + base + "@{upstream}")}` and returns `(upstream, int(first_line))`; None when the exit is non-zero or the line is not all digits. Read-only, no fetch. - `fetch_base(project, cfg, timeout=FETCH_TIMEOUT) -> str | None`: None (nothing to do) when `base_upstream()` is None; reads `git config --get {shlex.quote("branch." + base + ".remote")}`; returns None without fetching when the remote is empty, `.`, or starts with `-`. Else `retry_eagain(lambda: subprocess.run(["git", "fetch", "--quiet", remote], cwd=project, stdin=subprocess.DEVNULL, capture_output=True, text=True, env={**project_env(), "GIT_TERMINAL_PROMPT": "0"}, timeout=timeout))`; returns None on exit 0, `f"git fetch {remote} exited {rc}: {first stderr line}"` otherwise, `f"git fetch {remote} timed out after {timeout}s"` on `subprocess.TimeoutExpired`, and `f"git fetch {remote} failed: {e}"` on `OSError`. Docstring: a plain remote fetch only updates `refs/remotes/`, never a local branch, so the main checkout\'s branch cannot move. - `ensure_worktree(project, meta, cfg, notes: list[str] | None = None)`: inside the `not branch_exists` path only, before `git worktree add`, build a message list: if `fetch_base()` returns an error, add ``f"could not fetch `{base}`\'s upstream ({err}); comparing against the last fetched copy"``; then if `base_lag()` gives `(up, n)` with `n > 0`, add ``f"`{meta[\'branch\']}` is cut from local `{base}`, which is {n} commit(s) behind `{up}` -- every stage of this ticket sees the older code. `git pull --ff-only` on `{base}` in the main checkout catches it up for later tickets."``. For each message `print(f"  {meta[\'id\']}: {msg}")` and, when `notes` is not None, `notes.append(msg)`. Run step 2\'s tests and `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns`; all pass.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '4. Add `test_a_branch_cut_behind_its_upstream_notes_the_ticket` to `tests/test_dispatch.py`: `d, sh = git_project()`; `upstream_ahead(d, sh)` (import it from `helpers`); `path.write_text(FIXTURE.replace("stage: plan-validation", "stage: verifying"))`; `did, rec = supervisor.start(d, path, harness("fake"), {})`; assert `did and rec`; `rec["proc"].wait()`; `supervisor.finish(d, rec)`; assert `"behind" in Ticket.load(path).section("Thread")`. Run it and watch it fail.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '5. In `pipeline/daemon/supervisor.py:start()`, replace `wt = ensure_worktree(project, t.frontmatter(), cfg)` with `notes: list[str] = []` and `wt = ensure_worktree(project, t.frontmatter(), cfg, notes)`; after the `wt is None` bail, `for n in notes: t.append(stage, "note", n)` and `if notes: t.save()`. Run step 4\'s test; it passes. Commit `fix(TICKET-150): warn when a ticket branch is cut from a base behind its upstream`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '6. In `tests/test_machine.py` add `test_merging_kept_ends_at_branch_ready`: `assert M.transition("merging", "kept", {}) == ("branch-ready", {})`; `"branch-ready" in M.TERMINAL`, `in M.CLEANUP_STAGES`, `in M.KNOWN_STAGES`, and `M.VERIFIED == {"done", "branch-ready"}`. In `test_escalated_tickets_keep_their_worktree` change the last assertion to `M.CLEANUP_STAGES == {"done", "rejected", "branch-ready"}`. Run; watch it fail.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '7. In `pipeline/core/machine.py`: set `TERMINAL = {"done", "rejected", "escalated", "branch-ready"}`; add below it `VERIFIED = {"done", "branch-ready"}` with a comment (the two stages a verified ticket ends in; both satisfy `depends_on` and both record `## Decisions`); set `CLEANUP_STAGES = {"done", "rejected", "branch-ready"}` with a comment that cleanup drops the worktree and keeps the branch; add `case ("merging", "kept"): return "branch-ready", c` after `("merging", "fail")`, commented: the dispatcher issues `kept` under `merge = "none"`, the branch is kept, nothing lands on base or is pushed, and no counter is charged; in `dep_holder()` change `!= "done"` to `not in VERIFIED` and say `done` or `branch-ready` in its docstring. Run `tests/test_machine.py`; step 6\'s test and `test_a_dependency_at_branch_ready_satisfies_depends_on` pass.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '8. In `tests/test_config.py` add `test_merge_mode_defaults_to_local_and_ignores_a_bad_value(capsys)`: `reset_notices()`; `merge_mode(Path("/p"), {}) == "local"`; `merge_mode(Path("/p"), {"merge": "none"}) == "none"`; `merge_mode(Path("/p"), {"merge": "pr"}) == "local"` and `"merge" in capsys.readouterr().out`. Run; watch it fail on the import.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '9. In `pipeline/core/config.py` add `MERGE_MODES = ("local", "none")` and `merge_mode(project: Path, cfg: dict) -> str` below `project_conflict_ignore()`: `v = cfg.get("merge", "local")`; return `v` when `isinstance(v, str) and v in MERGE_MODES`; otherwise `notice_once(f"  {project}: ignoring merge = {v!r} (want \\"local\\" or \\"none\\")", str(project), "merge-mode")` and return `"local"`. Docstring: `local` lands on base in the main checkout; `none` stops at `branch-ready`. Run step 8\'s test; it passes.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '10. In `tests/test_dispatch.py` add `test_merge_none_ends_a_verified_ticket_at_branch_ready_with_its_branch_kept`: `d, sh = git_project()`; append `merge = "none"` to `d/.project/pipeline.toml`; ticket at `stage: merging`; `wt = supervisor.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})`, commit `ticket.py` there with `_commit(wt, "\'ticket commit\'")`; `tip = rev-parse ticket/001`; `sh("git checkout -qb somewhere-else")`; `base = rev-parse main`; `did, rec = supervisor.start(d, path, harness("fake"), {})`; assert `did and rec is None`, stage `branch-ready`, thread contains `merge = "none"` and `no `## Decisions` section`, `rev-parse main` == `base`, `git ls-files .project/` prints nothing; then a second `supervisor.start(...)` returns `did` True, `wt.is_dir()` is False, and `rev-parse ticket/001` == `tip`. Run; watch it fail.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '11. In `pipeline/daemon/supervisor.py`: import `merge_mode` from `pipeline.core.config` and `VERIFIED` from `pipeline.core.machine`. In `start()`, first inside `if stage == "merging":`, add: `if merge_mode(project, cfg) == "none":` call `advance(project, t, "kept", <note>, emit, agent=False)` and `return True, None`, where the note is ``f"`merge = \\"none\\"`: nothing landed on `{base_ref(cfg)}` and nothing pushed. Branch `{t.branch}` is kept -- push it and open the pull request, then `pipeline resume {tid} --stage done` once it merges."``. In `advance()` change `if nxt == "done":` to `if nxt in VERIFIED:`, and change `if nxt in CLEANUP_STAGES:` to `if nxt in CLEANUP_STAGES and nxt != "branch-ready":` with a comment that `merge = "none"` never writes base. Run step 10\'s test and `tests/test_dispatch.py`; all pass. Commit `feat(TICKET-150): merge = "none" ends a verified ticket at branch-ready`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '12. In `tests/test_cli.py`: add `test_diagnostics_reports_whether_base_is_behind_its_upstream` (`git_project()`; `rows["base"] == "no upstream for `main`"`; then `upstream_ahead(d, sh)` from `helpers`; `rows["base"].startswith("behind: ")` and exit 0); add `"base"` to the label tuple in `test_diagnostics_exits_nonzero_when_git_author_is_missing`; add `test_bare_ls_keeps_a_branch_ready_ticket`: `filter_ls_rows([{"id": "A", "stage": "branch-ready"}, {"id": "B", "stage": "done"}], None, False, None)` returns only the `A` row. Run; watch them fail.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '13. In `pipeline/cli/main.py`: set `FINISHED = TERMINAL - {"escalated", "branch-ready"}` and extend its comment (a `branch-ready` ticket waits on a human to push it); add `base_state(path) -> str` beside `worktree_setup_state()`: `project_config()` wrapped like there (`unknown ({e})`), then `base_lag(path, cfg)` imported from `pipeline.core.worktree`; None -> ``f"no upstream for `{base}`"``; `n == 0` -> ``f"up to date with `{up}` (as of the last fetch)"``; else ``f"behind: `{base}` is {n} commit(s) behind `{up}` (as of the last fetch) -- new tickets branch from the older code"``. In `cmd_diagnostics()` print `base: not applicable (not a git checkout)` in the non-git branch and `base: {base_state(path)}` before `git author` in the git branch; never change the exit code for it; docstring says ten rows. Run step 12\'s tests; they pass.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '14. In `tests/test_tui.py` add `test_the_tree_keeps_a_branch_ready_ticket`: `from pipeline.tui.app import FINISHED`; assert `"branch-ready" not in FINISHED` and `"done" in FINISHED`. Watch it fail, then set `FINISHED = TERMINAL - {"escalated", "branch-ready"}` in `pipeline/tui/app.py` with the same comment as step 13. Run `tests/test_tui.py`; all pass.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`
- plan step names no declared file: '15. Update the docs in one commit: `pipeline/templates/pipeline.toml` -- under `base`, say a new ticket branch is cut from LOCAL base after a fetch of its upstream and warns when base is behind; then add a commented `# merge                   = "none"` block explaining `local` (default, lands on base, main checkout must sit on base) vs `none` (stops at `branch-ready`, branch kept, nothing merged or pushed, `depends_on` accepts it). `pipeline/templates/skills/file-ticket/SKILL.md` -- "nine rows" becomes "ten rows" and lists `base` (`no upstream`, `up to date`, or `behind: ...`); the `depends_on` paragraph says it waits for `done` or `branch-ready`; the hand-over section says under `merge = "none"` a verified ticket ends at `branch-ready` (push the branch, open the PR, then `pipeline resume <id> --stage done`). `README.md` -- "nine rows" becomes "ten rows" and gains a `base` bullet. `CLAUDE.md` -- append to the last paragraph: under `merge = "none"` in `.project/pipeline.toml` `merging` never touches the main checkout, so it need not sit on base. Run `uv run --group dev pytest -q tests/test_cli.py tests/test_stages.py`; exit 0. Commit `feat(TICKET-150): document merge = "none", branch-ready and the base row`.' -- spell the path out in the step (e.g. `pipeline/core/machine.py`) and declare that same path in `files_declared`

### 2026-10-02 · planning · finding

Plan written: 15 steps, 17 files. The gate entry above is my own `pipeline gate` run; its findings are only `files_declared` empty and `names no declared file`, which clear once the dispatcher adopts `files_declared`.

Design calls the ticket left to planning:
1. Branch cut stays on LOCAL base. `base_checkout()`, `fenced_touches()`, `merge_cmd()` and `revalidating` all compare against local base, so cutting from the upstream would put upstream commits in the ticket's diff.
2. The dispatcher fetches the upstream's remote once per branch cut. The fetch is bounded (20s, `GIT_TERMINAL_PROMPT=0`) and never moves a local branch. A failed fetch is a note, not a bail.
3. "`diagnostics` row" is read as a `base:` row in `pipeline diagnostics`. Per DEC-115 it never fetches.
4. The new state is named `branch-ready`. `merge = "none"` reaches it through a dispatcher-issued `("merging", "kept")` row. The worktree is dropped and the branch kept. No record commit lands on base.
5. `branch-ready` stays visible in bare `ls` and the TUI (DEC-116).

Scope notes: the dispatcher tests go in `tests/test_dispatch.py`, not `tests/test_daemon.py`, because the `start()` merging tests live there. README.md, CLAUDE.md, `pipeline/tui/app.py` and `tests/helpers.py` are added to the expected list. The `transition()` row is fenced, so this ticket parks at `awaiting-merge`.

### 2026-10-02 02:18:03Z · planning · session · session=ffe11cf6-bc61-4bcd-8df9-5aebbd0a8448

`planning` ran as session `ffe11cf6-bc61-4bcd-8df9-5aebbd0a8448`
- replay: `claude --resume ffe11cf6-bc61-4bcd-8df9-5aebbd0a8448`
- log: `.project/logs/TICKET-150-planning-ffe11cf6.log`
- cost: $2.52 of a $10 cap
- tokens: 43,618 out (25,475 thinking) · 62 in · 2,734,861 cache read · 137,820 cache write

### 2026-10-02 02:18:03Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ 15-step plan: fetch + warn at branch cut (local base kept as cut point), merge = none ends at terminal branch-ready, depends_on accepts it, diagnostics gains a base row

### 2026-10-02 02:19:24Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:17:39Z · plan-validation · gate · verdict=FAIL` --*
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails as required
```
============= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-150
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7ff0a2ccff60>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.07s ===============================

```
- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-83szrx96/base
      Built pipeline @ file:///tmp/pipeline-base-83szrx96/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 85ms

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails on base `main` too -- the bug is not already fixed upstream
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/pipeline-base-83szrx96/base
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7f1fe2b8cae0>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: DEC-100 is superseded -- history, not binding

### 2026-10-02 · plan-validation · finding

long: eight scored items plus one concrete fix.

**Verdict: fail -- one item (falsifiability).** No test catches a record commit onto base under `merge = "none"`.

1. **Root cause -- pass.** `ensure_worktree()` never compares base with its upstream. `dep_holder()` accepts only `done` (`machine.py:379`), and the only way to stop before merging is an escalation. The plan fixes both causes.
2. **Decision conflict -- pass.** DEC-115/147: the `base` row never fetches and never changes the exit code. DEC-116/060: both `FINISHED` copies change together. DEC-139: `dep_unsatisfiable()` (`machine.py:401`) rejects only `rejected`, so it is unchanged.
3. **Scope -- pass.** Every step maps to a criterion or to the docs obligation in `CLAUDE.md`.
4. **Falsifiability -- FAIL.** In step 10 the test runs `git checkout -qb somewhere-else` before `start()`. `advance()` skips `commit_record()` whenever HEAD is off base: `elif code or head.strip() != base:` (`supervisor.py:157`). Drop step 11's `nxt != "branch-ready"` guard and every listed test still passes. On `main`, that commit lands on base, which breaks the plan's own Decision "`merge = "none"` never writes the base branch". Fix: add a second `start()` case with the checkout left on `main`. Assert that `rev-parse main` is unchanged and that `git ls-files .project/` prints nothing.
5. **No research left -- pass.**
6. **Riskiest step -- pass.** The riskiest step is the fetch in step 3, and the plan states a fallback.
7. **Regression surface -- pass.** `ensure_worktree()` has 30+ test callers, none with an upstream. `test_machine.py:242` changes in step 6. `cmd_resume` accepts `--stage done` from any stage (`main.py:402`).
8. **Blast radius -- pass.** The class is `ok`, not `bugfix`.

Not scored: the uncommitted decision record from `branch-ready` is picked up by the next `commit_record()` (`git status --porcelain -- .project/decisions`, `supervisor.py:651`). That is acceptable.

### 2026-10-02 02:22:00Z · plan-validation · session · session=c1436cb2-ff98-4382-a629-9ab3d9f04eb9

`plan-validation` ran as session `c1436cb2-ff98-4382-a629-9ab3d9f04eb9`
- replay: `claude --resume c1436cb2-ff98-4382-a629-9ab3d9f04eb9`
- log: `.project/logs/TICKET-150-plan-validation-c1436cb2.log`
- cost: $1.06 of a $3 cap
- tokens: 15,692 out (7,978 thinking) · 32 in · 928,524 cache read · 70,390 cache write

### 2026-10-02 02:22:00Z · plan-validation · transition · to=planning · result=bad-plan · marker=yes

**plan-validation -> planning** (result: `bad-plan`)

✓ plan sound on 7 of 8 items; fails falsifiability -- step 10 parks the checkout off base, so no test catches a record commit onto base under merge = none

### 2026-10-02 02:38:07Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails as required
```
-cut time."""
        d, sh = git_project()
        remote = Path(tempfile.mkdtemp())
        subprocess.run(f"git clone -q --bare {d} {remote}", shell=True, check=True)
        sh(f"git remote add origin {remote} && git fetch -q origin "
           "&& git branch -u origin/main main")
        (d / "g.py").write_text("later")
        sh("git add -A && git commit -qm later && git push -q origin main"
           " && git reset -q --hard HEAD~1")
        assert "behind 1" in sh("git status -sb").stdout
        W.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails as required
```
============= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-150
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7f4465c1ff60>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.26s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-yusxwtj_/base
      Built pipeline @ file:///tmp/pipeline-base-yusxwtj_/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 85ms

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails on base `main` too -- the bug is not already fixed upstream
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/pipeline-base-yusxwtj_/base
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7fa3936b8ae0>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: DEC-100 is superseded -- history, not binding

### 2026-10-02 · planning · finding

Re-plan for the plan-validation falsifiability failure. Only step 10, one criterion and one Digest gotcha changed.

1. Step 10 now adds two tests. (a) is the old test, with the checkout parked off base. (b) `test_merge_none_never_commits_onto_base_from_a_checkout_on_base` keeps the checkout on `main` and gives the ticket a `## Decisions` section.
2. (b) asserts `DEC-001.md` exists on disk, `git rev-parse main` is unchanged, and `git ls-files .project/` prints nothing.
3. Without step 11's `nxt != "branch-ready"` guard, (b) fails. `commit_record()` always stages the ticket file (`files = [str(t.path.relative_to(project))]`, supervisor.py line 648), so a commit onto `main` turns both git asserts red.
4. `## Acceptance criteria` names the new test. The new `## Digest` gotcha says why an off-base test cannot catch a record commit (`elif code or head.strip() != base:`, line 157).

`pipeline gate TICKET-150` printed `gate: PASS`.

### 2026-10-02 02:38:52Z · planning · session · session=7c35dade-0dc6-4188-afc0-ae983585af80

`planning` ran as session `7c35dade-0dc6-4188-afc0-ae983585af80`
- replay: `claude --resume 7c35dade-0dc6-4188-afc0-ae983585af80`
- log: `.project/logs/TICKET-150-planning-7c35dade.log`
- cost: $0.86 of a $10 cap
- tokens: 8,894 out (2,005 thinking) · 38 in · 1,025,271 cache read · 59,672 cache write

### 2026-10-02 02:38:52Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-plan: step 10 adds a merge = none test with the checkout on main, so a record commit onto base fails it; gate PASS

### 2026-10-02 02:40:11Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:38:07Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails as required
```
============= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-150
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7ff970ccff60>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.24s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-qtn9a8f0/base
      Built pipeline @ file:///tmp/pipeline-base-qtn9a8f0/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 81ms

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails on base `main` too -- the bug is not already fixed upstream
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/pipeline-base-qtn9a8f0/base
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7ffabd33cae0>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: DEC-100 is superseded -- history, not binding

### 2026-10-02 · plan-validation · finding

long: eight scored items plus one suggested ticket.

**Verdict: ok.** The re-plan fixes the falsifiability gap, and no gap shares the ticket's root cause.

1. **Root cause -- pass.** `ensure_worktree()` cuts from local base and never compares it with its upstream. Only `done` counts as verified (`machine.py:379`), so stopping before a merge means escalating. The plan fixes both causes.
2. **Decision conflict -- pass.** DEC-115/147: the `base` row reads the last fetch and never sets the exit code. DEC-116/060: both `FINISHED` copies change together (`main.py:554`, `app.py:60`). DEC-139: `dep_unsatisfiable()` still rejects only `rejected`.
3. **Scope -- pass.** Every step maps to a criterion or to the docs obligation in `CLAUDE.md`.
4. **Falsifiability -- pass.** Step 10(b) keeps HEAD on `main`, so `advance()`'s `elif code or head.strip() != base:` (`supervisor.py:157`) no longer hides a `commit_record()`. Step 2(a) asserts lag `0` before the cut and `1` after it, so it fails without the fetch.
5. **No research left -- pass.**
6. **Riskiest step -- pass.** The riskiest step is the fetch in step 3. The plan's fallback keeps a compare-only warning.
7. **Regression surface -- pass.** `test_stages.py:145` subtracts `M.TERMINAL`, so the new terminal stage needs no prompt. Fenced diffs still route `verifying` -> `awaiting-merge` -> `merging` (`machine.py:283-289`), ahead of the new `kept` check.
8. **Blast radius -- pass.** The class is not `bugfix`.

Suggested new ticket: `merged_tickets()` (`metrics.py:202-206`) counts only `merging -> done`. A `branch-ready` ticket later resumed to `done` never counts as merged.

### 2026-10-02 02:52:56Z · plan-validation · session · session=4c4008c0-e799-4931-abe7-a9f957bf32b1

`plan-validation` ran as session `4c4008c0-e799-4931-abe7-a9f957bf32b1`
- replay: `claude --resume 4c4008c0-e799-4931-abe7-a9f957bf32b1`
- log: `.project/logs/TICKET-150-plan-validation-4c4008c0.log`
- cost: $0.77 of a $3 cap
- tokens: 9,901 out (4,419 thinking) · 24 in · 584,730 cache read · 56,893 cache write

### 2026-10-02 02:52:56Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ plan passes all 8 items; the re-plan's on-base merge = none test catches a record commit, and no same-root-cause gap found

### 2026-10-02 03:44:19Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-02 03:46:26Z · plan-validation · gate · verdict=FAIL

**Tier A gate: FAIL**

- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails as required
```
-cut time."""
        d, sh = git_project()
        remote = Path(tempfile.mkdtemp())
        subprocess.run(f"git clone -q --bare {d} {remote}", shell=True, check=True)
        sh(f"git remote add origin {remote} && git fetch -q origin "
           "&& git branch -u origin/main main")
        (d / "g.py").write_text("later")
        sh("git add -A && git commit -qm later && git push -q origin main"
           " && git reset -q --hard HEAD~1")
        assert "behind 1" in sh("git status -sb").stdout
        W.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.20s ===============================

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails as required
```
============= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-150
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7fa47c320400>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-kycm0d6y/base
      Built pipeline @ file:///tmp/pipeline-base-kycm0d6y/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 68ms

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails on base `main` too -- the bug is not already fixed upstream
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/pipeline-base-kycm0d6y/base
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7fa8830c0ae0>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================

```
- ok: DEC-100 is superseded -- history, not binding
- plan step has no acceptance criterion: step 1 '1. Add `upstream_ahead(d, sh) -> Path` to `tests/helpers.py`: `git clone -q --ba' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 2 '2. Add two tests to `tests/test_worktree.py`, then run them and watch the first ' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 3 '3. In `pipeline/core/worktree.py` add `FETCH_TIMEOUT = 20` and three functions b' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 4 '4. Add `test_a_branch_cut_behind_its_upstream_notes_the_ticket` to `tests/test_d' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 5 '5. In `pipeline/daemon/supervisor.py:start()`, replace `wt = ensure_worktree(pro' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 6 '6. In `tests/test_machine.py` add `test_merging_kept_ends_at_branch_ready`: `ass' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 7 '7. In `pipeline/core/machine.py`: set `TERMINAL = {"done", "rejected", "escalate' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 8 '8. In `tests/test_config.py` add `test_merge_mode_defaults_to_local_and_ignores_' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 9 '9. In `pipeline/core/config.py` add `MERGE_MODES = ("local", "none")` and `merge' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 10 '10. In `tests/test_dispatch.py` add two tests, then run both and watch them fail' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 11 '11. In `pipeline/daemon/supervisor.py`: import `merge_mode` from `pipeline.core.' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 12 '12. In `tests/test_cli.py`: add `test_diagnostics_reports_whether_base_is_behind' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 13 '13. In `pipeline/cli/main.py`: set `FINISHED = TERMINAL - {"escalated", "branch-' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 14 '14. In `tests/test_tui.py` add `test_the_tree_keeps_a_branch_ready_ticket`: `fro' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 15 '15. Update the docs in one commit: `pipeline/templates/pipeline.toml` -- under `' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt

### 2026-10-02 03:46:27Z · revalidating · transition · to=planning · result=fail

**revalidating -> planning** (result: `fail`)

re-gated after rebasing onto base failed:
- plan step has no acceptance criterion: step 1 '1. Add `upstream_ahead(d, sh) -> Path` to `tests/helpers.py`: `git clone -q --ba' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 2 '2. Add two tests to `tests/test_worktree.py`, then run them and watch the first ' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 3 '3. In `pipeline/core/worktree.py` add `FETCH_TIMEOUT = 20` and three functions b' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 4 '4. Add `test_a_branch_cut_behind_its_upstream_notes_the_ticket` to `tests/test_d' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 5 '5. In `pipeline/daemon/supervisor.py:start()`, replace `wt = ensure_worktree(pro' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 6 '6. In `tests/test_machine.py` add `test_merging_kept_ends_at_branch_ready`: `ass' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 7 '7. In `pipeline/core/machine.py`: set `TERMINAL = {"done", "rejected", "escalate' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 8 '8. In `tests/test_config.py` add `test_merge_mode_defaults_to_local_and_ignores_' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 9 '9. In `pipeline/core/config.py` add `MERGE_MODES = ("local", "none")` and `merge' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 10 '10. In `tests/test_dispatch.py` add two tests, then run both and watch them fail' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 11 '11. In `pipeline/daemon/supervisor.py`: import `merge_mode` from `pipeline.core.' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 12 '12. In `tests/test_cli.py`: add `test_diagnostics_reports_whether_base_is_behind' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 13 '13. In `pipeline/cli/main.py`: set `FINISHED = TERMINAL - {"escalated", "branch-' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 14 '14. In `tests/test_tui.py` add `test_the_tree_keeps_a_branch_ready_ticket`: `fro' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt
- plan step has no acceptance criterion: step 15 '15. Update the docs in one commit: `pipeline/templates/pipeline.toml` -- under `' -- name the step in the criterion that checks it, as `(step 2)`, `(steps 1, 3)`, `(steps 1 and 3)` or `(steps 2-4)`; a plan of one step is exempt

### 2026-10-02 03:49:47Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails as required
```
-cut time."""
        d, sh = git_project()
        remote = Path(tempfile.mkdtemp())
        subprocess.run(f"git clone -q --bare {d} {remote}", shell=True, check=True)
        sh(f"git remote add origin {remote} && git fetch -q origin "
           "&& git branch -u origin/main main")
        (d / "g.py").write_text("later")
        sh("git add -A && git commit -qm later && git push -q origin main"
           " && git reset -q --hard HEAD~1")
        assert "behind 1" in sh("git status -sb").stdout
        W.ensure_worktree(d, {"id": "TICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.18s ===============================

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails as required
```
============= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-150
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7fb3a9a1ff60>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.24s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-wr0jstvo/base
      Built pipeline @ file:///tmp/pipeline-base-wr0jstvo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 64ms

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails on base `main` too -- the bug is not already fixed upstream
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/pipeline-base-wr0jstvo/base
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7f9af48c0ae0>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: DEC-100 is superseded -- history, not binding

### 2026-10-02 · planning · finding

**Re-plan after `revalidating` failed: only `## Acceptance criteria` changed.**

1. Cause: TICKET-149 (813e4fe) added a Tier A rule: a criterion must name each plan step. The approved plan's criteria named no steps, so all 15 steps failed `plan step has no acceptance criterion`.
2. Fix: each criterion now carries a step tag, e.g. `(steps 10, 11)`. `## Plan`, `## Digest`, `## Decisions` and `## Rollback` are unchanged.
3. Baseline re-measured on c8754f0 (rebased onto b6a88e9): the seven-file suite printed `2 failed, 412 passed`; the 2 are this ticket's repro tests.
4. The rebase moved no plan target: `git diff ee4963d main` touches `pipeline/cli/main.py` only in `cmd_reject()`. `FINISHED` is now at `main.py:564`, `cmd_diagnostics()` at `main.py:653`.
5. `pipeline gate TICKET-150` printed `gate: PASS`.

The criteria edit changes the `approved_plan_hash` digest, so the approval does not carry. A human must approve again.

### 2026-10-02 03:50:30Z · planning · session · session=4e44cc4b-9493-493d-9ecf-17765d0ee5a7

`planning` ran as session `4e44cc4b-9493-493d-9ecf-17765d0ee5a7`
- replay: `claude --resume 4e44cc4b-9493-493d-9ecf-17765d0ee5a7`
- log: `.project/logs/TICKET-150-planning-4e44cc4b.log`
- cost: $0.89 of a $10 cap
- tokens: 8,913 out (1,434 thinking) · 34 in · 942,649 cache read · 65,624 cache write

### 2026-10-02 03:50:30Z · planning · transition · to=plan-validation · result=ok · marker=yes

**planning -> plan-validation** (result: `ok`)

✓ re-plan: every acceptance criterion now names its plan step (TICKET-149 rule); plan steps unchanged; gate PASS

### 2026-10-02 03:51:51Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:38:07Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails as required
```
============= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-150
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7f5cde21ff60>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-t4i944ws/base
      Built pipeline @ file:///tmp/pipeline-base-t4i944ws/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 97ms

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails on base `main` too -- the bug is not already fixed upstream
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/pipeline-base-t4i944ws/base
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7f5d5ec38ae0>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: DEC-100 is superseded -- history, not binding

### 2026-10-02 · plan-validation · finding

long: eight scored items, each with its evidence.

**Verdict: ok.** Since the last `ok`, only the criteria's step tags changed. I re-checked every claim against c8754f0.

1. **Root cause -- pass.** `ensure_worktree()` (`worktree.py:103-105`) cuts from local base and never compares it with an upstream. `dep_holder()` accepts only `done` (`machine.py:379`). Stopping before a merge therefore means escalating. The plan fixes both causes.
2. **Decision conflict -- pass.** DEC-115/147: the `base` row reads the last fetch and never sets the exit code. DEC-116/060: both `FINISHED` copies change (`main.py:564`, `app.py:60`). DEC-139: `dep_unsatisfiable()` still rejects only `rejected`.
3. **Scope -- pass.** Every step carries a criterion tag. The docs edits answer `CLAUDE.md`'s file-ticket obligation.
4. **Falsifiability -- pass.** Step 2(a) asserts lag `0` before the cut, and it warns only after a fetch. Step 10(b) keeps HEAD on `main`, so dropping the `nxt != "branch-ready"` guard fails it.
5. **No research left -- pass.** Every step names its file and function.
6. **Riskiest step -- pass.** The riskiest step is the fetch in step 3. Its fallback is a compare-only warning.
7. **Regression surface -- pass.** No existing test configures an upstream, so `fetch_base()` stays a no-op there. `test_machine.py:69` and `test_stages.py:145` treat the new stage through `M.TERMINAL`. The off-base refusal lives only in `merge_cmd()` (`supervisor.py:701`).
8. **Blast radius -- pass.** The class is `feature`.

No sibling gap: `ensure_worktree()` is the only branch cut (`supervisor.py:902`). `worktree.py:147` is the gate's detached base checkout.

### 2026-10-02 03:54:14Z · plan-validation · session · session=0f6e3ebc-0513-4d35-8961-2a4ba9977729

`plan-validation` ran as session `0f6e3ebc-0513-4d35-8961-2a4ba9977729`
- replay: `claude --resume 0f6e3ebc-0513-4d35-8961-2a4ba9977729`
- log: `.project/logs/TICKET-150-plan-validation-0f6e3ebc.log`
- cost: $1.03 of a $3 cap
- tokens: 12,975 out (6,371 thinking) · 36 in · 1,045,604 cache read · 70,630 cache write

### 2026-10-02 03:54:14Z · plan-validation · transition · to=awaiting-approval · result=ok · marker=yes

**plan-validation -> awaiting-approval** (result: `ok`)

✓ all eight items pass on the re-plan; only the step tags in the criteria changed, and no gap shares the ticket's root cause

### 2026-10-02 04:31:50Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-02 04:33:20Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails as required
*-- identical output, already quoted in the `## Thread` entry `2026-10-02 02:38:07Z · plan-validation · gate · verdict=PASS` --*
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails as required
```
============= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/chezzijr/proj/agent-pipeline/.worktrees/TICKET-150
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7f68a341ff60>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.06s ===============================

```
- ok: `tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns` fails on base `main` too -- the bug is not already fixed upstream
```
ICKET-001", "branch": "ticket/001"}, {"base": "main"})
        out = capsys.readouterr().out
>       assert "behind" in out, f"no warning that base is behind its upstream: {out!r}"
E       AssertionError: no warning that base is behind its upstream: ''
E       assert 'behind' in ''

tests/test_worktree.py:427: AssertionError
=========================== short test summary info ============================
FAILED tests/test_worktree.py::test_a_branch_cut_from_a_base_behind_its_upstream_warns
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.25s ===============================
Using CPython 3.12.10
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-k5aicx2w/base
      Built pipeline @ file:///tmp/pipeline-base-k5aicx2w/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 82ms

```
- ok: `tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on` fails on base `main` too -- the bug is not already fixed upstream
```
============================= test session starts ==============================
platform linux -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/pipeline-base-k5aicx2w/base
configfile: pyproject.toml
collected 1 item

tests/test_machine.py F

=================================== FAILURES ===================================
____________ test_a_dependency_at_branch_ready_satisfies_depends_on ____________

    def test_a_dependency_at_branch_ready_satisfies_depends_on():
        from pipeline.core.machine import dep_holder
>       assert dep_holder("B", {"B": ["A"]}, {"A": "branch-ready", "B": "new"}) is None
E       AssertionError: assert ('A', 'branch-ready') is None
E        +  where ('A', 'branch-ready') = <function dep_holder at 0x7fb2229b8ae0>('B', {'B': ['A']}, {'A': 'branch-ready', 'B': 'new'})

tests/test_machine.py:438: AssertionError
=========================== short test summary info ============================
FAILED tests/test_machine.py::test_a_dependency_at_branch_ready_satisfies_depends_on
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.14s ===============================

```
- ok: DEC-100 is superseded -- history, not binding

### 2026-10-02 04:33:21Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base: passed

### 2026-10-02 · implementing · note

**implementing: done.** All 15 plan steps executed, in order, test first; each new test was seen red for the expected reason before its code.

- [x] 1-5 `upstream_ahead` helper, fetch/lag warning, thread note -- `8d0b220`
- [x] 6-11 `branch-ready`, `VERIFIED`, `merge_mode`, `merge = "none"` in `start()` -- `0539700`
- [x] 12-14 diagnostics `base` row, `FINISHED` in `ls` and TUI -- `2b844ce`
- [x] 15 README, SKILL.md, pipeline.toml, CLAUDE.md -- `9db0f5f`

Plan step 6 changed `test_escalated_tickets_keep_their_worktree` (the `CLEANUP_STAGES` set), as the plan says.

Result: `pytest -q` on the seven named test files printed `424 passed`. `grep -c "nine rows"` prints 0 for README.md and SKILL.md. The full suite was not run.

### 2026-10-02 04:38:32Z · implementing · session · session=cc66c0b8-fd1f-4e75-afb9-c19a6a4b2b99

`implementing` ran as session `cc66c0b8-fd1f-4e75-afb9-c19a6a4b2b99`
- replay: `claude --resume cc66c0b8-fd1f-4e75-afb9-c19a6a4b2b99`
- log: `.project/logs/TICKET-150-implementing-cc66c0b8.log`
- cost: $1.06 of a $12 cap
- tokens: 22,462 out (1,054 thinking) · 74 in · 2,429,615 cache read · 87,419 cache write

### 2026-10-02 04:38:32Z · implementing · transition · to=review · result=ok · marker=yes

**implementing -> review** (result: `ok`)

✓ plan executed in 4 commits; the 7 named test files pass (424 passed), docs updated, no "nine rows" left

### 2026-10-02 · review · note

**review: pass, no blocking findings.** Delta: `main...9db0f5f` (5 commits, first pass). The code matches `## Plan` steps 1-15.

Evidence:
- 7 named files: `424 passed in 67.31s`. Full suite: `749 passed in 78.69s`. `git status --short` stayed empty.
- Grep criteria: `pipeline.toml` exits 0, SKILL.md `branch-ready` exits 0, `nine rows` exits 1 in README.md and SKILL.md.
- `("merging", "kept")` is the only `merging` row that matches `kept` (`machine.py:297-305`); no earlier wildcard catches it.
- `pipeline resume <id> --stage done` works: `cmd_resume` accepts any `KNOWN_STAGES` (`cli/main.py:412`).

Non-blocking:
1. (nit, docs) README.md:222 and SKILL.md:194 still say a non-git project reports "both Git rows" as `not applicable`. Three rows say it now: `base`, `git author`, `worktree commit`.
2. (nit, test) The triage test `test_a_branch_cut_from_a_base_behind_its_upstream_warns` uses `git add -A`, which the Digest warns against. It passes because the `reset --hard` deletes only the untracked `.project/` files and the test passes `cfg` directly. `upstream_ahead()` uses `git add g.py` correctly.
3. (observation) `pipeline close` accepts a `branch-ready` ticket and moves it to `rejected` (`cli/main.py:542`). This fits an abandoned PR, so it is not a defect.

### 2026-10-02 04:42:33Z · review · session · session=d735c14f-52ac-43b2-b589-2087f48b93d5

`review` ran as session `d735c14f-52ac-43b2-b589-2087f48b93d5`
- replay: `claude --resume d735c14f-52ac-43b2-b589-2087f48b93d5`
- log: `.project/logs/TICKET-150-review-d735c14f.log`
- cost: $0.86 of a $8 cap
- tokens: 8,209 out (3,113 thinking) · 32 in · 852,250 cache read · 65,620 cache write

### 2026-10-02 04:42:33Z · review · transition · to=verifying · result=ok · marker=yes

**review -> verifying** (result: `ok`)

✓ no blocking findings; delta main...9db0f5f matches the plan, full suite 749 passed, 4 grep criteria hold; 2 doc nits noted

### 2026-10-02 04:43:53Z · verifying · transition · to=awaiting-merge · result=ok

**verifying -> awaiting-merge** (result: `ok`)

regression suite passed, but the diff touches fenced code:
- `pipeline/core/machine.py:transition`

`CLAUDE.md` requires a human to see this diff before it lands. `pipeline approve TICKET-150` lands it; `pipeline resume TICKET-150 --stage planning` sends it back.

### 2026-10-02 07:13:07Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-10-02 07:13:50Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
ain || exit 1
head=$(git -C /home/chezzijr/proj/agent-pipeline rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/agent-pipeline merge --ff-only ticket/150


Current branch ticket/150 is up to date.
Already up to date.
Updating b6a88e9..9db0f5f
Fast-forward
 CLAUDE.md                                      |  2 +
 README.md                                      |  5 +-
 pipeline/cli/main.py                           | 26 ++++++++--
 pipeline/core/config.py                        | 15 ++++++
 pipeline/core/machine.py                       | 18 +++++--
 pipeline/core/worktree.py                      | 67 +++++++++++++++++++++++++-
 pipeline/daemon/supervisor.py                  | 24 +++++++--
 pipeline/templates/pipeline.toml               |  7 +++
 pipeline/templates/skills/file-ticket/SKILL.md | 13 +++--
 pipeline/tui/app.py                            |  3 +-
 tests/helpers.py                               | 12 +++++
 tests/test_cli.py                              | 24 ++++++++-
 tests/test_config.py                           |  9 ++++
 tests/test_dispatch.py                         | 60 +++++++++++++++++++++++
 tests/test_machine.py                          | 15 +++++-
 tests/test_tui.py                              |  6 +++
 tests/test_worktree.py                         | 48 ++++++++++++++++++
 17 files changed, 332 insertions(+), 22 deletions(-)

```

### 2026-10-02 07:13:50Z · merging · decision

decision recorded as `DEC-150`
