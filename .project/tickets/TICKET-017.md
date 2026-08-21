---
id: TICKET-017
stage: done
class: bugfix
branch: ticket/017
test_file: tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base
files_declared:
- pipeline/core/gate.py
- pipeline/core/worktree.py
- pipeline/templates/pipeline.toml
- tests/test_gate.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: review
  id: 90df32c8-600f-42a3-8560-613a2400ff05
  log: .project/logs/TICKET-017-review-90df32c8.log
approved_by: chezzijr
approved_at: '2026-08-21T05:11:32.985366+00:00'
---

## Summary

**Review (2026-08-21): PASS, no blocking findings.** Reviewed `git diff main...HEAD`
(`d52748d` + `612e43f`, four files = exactly `files_declared`). Re-ran everything rather
than trusting the thread: `tests/test_gate.py` 16 passed, whole suite `165 passed in
6.02s`, no leaked `/tmp/pipeline-base-*`, worktree clean. Killed three mutations of
`_base_findings` (no-op / always-fail / always-ok) against the real test bodies -- each
one turns a criterion red, so neither acceptance test is vacuous. Wiring is in the one
`else:` branch the plan named and the `code == 0` / `node not in out` / `expect` branches
are byte-unchanged, so a base failure can never satisfy `expect:`. Four non-blocking
notes in `## Thread`: stale `.git/worktrees` entry if `remove` fails (carried over from
plan-validation), the criterion's hardcoded `/tmp` vs `TMPDIR`, `worktree_setup`'s exit
code ignored in `base_checkout` exactly as `ensure_worktree` ignores it, and one thing
the review could not test because `git clone`/`git worktree` are off its allowlist --
whether this repo's own `uv run` `test_one` resolves deps in a `/tmp` base checkout
(low risk, first suspect if a post-merge ticket reports `errored rather than failed on
base`).

**Implemented (2026-08-21), plan executed exactly as approved.** Tier A now runs the
ticket's test a second time against a throwaway detached checkout of base (branch's test
file copied in, base's code), and requires fail-on-branch AND fail-on-base for a PASS.
`pipeline/core/worktree.py` gained `base_ref(cfg)` (the one default `ensure_worktree` and
the gate now share) and a `base_checkout` contextmanager. `pipeline/core/gate.py` gained
`_base_findings`, wired into the branch where the branch test already failed as required.
`tests/test_gate.py` gained a shared `_git_ticket_project` scaffold, the refactored
reproduction test (byte-identical assertions, still failed the same way after the
refactor, confirmed before touching `gate.py`), and the complement test
`test_gate_passes_a_test_that_fails_on_base_too`. `pipeline/templates/pipeline.toml`
documents the `base` key. All 16 tests in `tests/test_gate.py` and the whole suite (165
tests) pass; no leaked `/tmp/pipeline-base-*` checkout. Committed as `612e43f`.

Tier A previously ran the failing test on the ticket branch only, never on base, so a
test that fails on the branch and passes on base -- the bug already fixed upstream, or
the test red for a reason base does not have -- was accepted as a reproduction.

**Triage (2026-08-21): reproduced.** `pipeline/core/gate.py:69` is the only `test_one`
run and it uses `wd = workdir or project`, the ticket worktree; nothing in the file
reads `cfg["base"]`. Failing test committed as `1240d83`:
`tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base`. See
`## Reproduction` for the command and output.

**Planning (2026-08-21): plan written, and every claim in it re-verified against the
code.** The fix runs the ticket's test a second time against a throwaway detached
checkout of base, with the *branch's* test file copied into it -- the test does not
exist on base, and a naive checkout would exit non-zero for a missing file and read as
a successful reproduction. A reproduction then requires fail-on-branch AND fail-on-base.
The base run is skipped when no worktree was given (`wd == project`), which is what
keeps `pipeline gate` and 14 of the 15 gate tests working unchanged.

Four files: `pipeline/core/gate.py` (new `_base_findings`, wired into the one branch
where the branch run already passed, so a red branch test never pays for a checkout),
`pipeline/core/worktree.py` (new `base_ref` and a `base_checkout` contextmanager),
`tests/test_gate.py` (a shared scaffold plus the complement test that an "always fail
the base check" implementation cannot satisfy), and `pipeline/templates/pipeline.toml`
(document the `base` key).

**Plan validation (2026-08-21): PASS on all eight items.** Root cause confirmed at
`pipeline/core/gate.py:69` (one `test_one` run, `wd = workdir or project`, no
`cfg["base"]` anywhere); the plan fixes that, not the assertion. The two acceptance
criteria are complementary -- the reproduction test kills a no-op, and
`test_gate_passes_a_test_that_fails_on_base_too` kills an "always report base failure"
implementation, so neither is vacuous. Skip path verified by reading every `gate()`
caller: exactly one test in the repo passes a `workdir` (`tests/test_gate.py:179`), the
other 14 plus `tests/test_ticket.py:269` pass none, so `wd == project` covers them.
DEC-011 is the only decision record, still active, and its frozen `gate` event row
`{verdict, findings:[...]}` is unchanged by adding list entries. Two observations
recorded in `## Thread`, neither blocking: step 13 is a template comment no criterion
covers, and `git worktree remove` failing before `rmtree` would leave a prunable stale
worktree entry.

## Reproduction

`tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` (committed on
`ticket/017` as `1240d83`).

Command:

```sh
uv run --group dev pytest -q tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base
```

The test builds a real git project: `main` has `f.py` = `fixed`, the ticket
worktree on `ticket/001` has `f.py` = `buggy`, and `test_one` is
`echo test_broken; grep -q fixed f.py` -- so the ticket's test FAILS on the
branch and PASSES on base. `gate()` returns `ok=True`: it never ran the test
against base.

Failure output:

```
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert not ok, "gate passed a test that does not fail on base"
E       AssertionError: gate passed a test that does not fail on base
E       assert not True

tests/test_gate.py:180: AssertionError
FAILED tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base - Asse...
1 failed in 0.08s
```

expect: gate passed a test that does not fail on base

## Digest

**The one hole.** `pipeline/core/gate.py:69` is the only `test_one` run and it passes
`wd = workdir or project` -- the ticket worktree. Nothing in the file mentions
`cfg["base"]`. A test that fails on the branch and passes on base is accepted.

**Call sites of `gate()`** (all three keep working unchanged):
- `pipeline/daemon/supervisor.py:518` -- stage `plan-validation`, always passes `wt`.
- `pipeline/daemon/supervisor.py:591` -- `finish_regate`, stage `revalidating`, passes
  `rec["wt"]`. This is the one the ticket cares about: it re-establishes stale facts
  after `git rebase base`.
- `pipeline/cli/main.py:73` -- `pipeline gate`, passes `wt` only `if wt.is_dir()`,
  otherwise `None`.

**The non-obvious part: the test does not exist on base.** The reproduction test is
written by `triage` and committed on the ticket branch. Checking out base and running
`test_one` there would hit a missing file, exit non-zero, and read as "fails on base" --
a false reproduction, the exact wrong direction. So the base run is: throwaway detached
checkout of base, **copy the branch's test file into it**, run `test_one` there. Branch's
test, base's code.

**Existing helpers to reuse, not reinvent:**
- `run_cmd(cmd, cwd)` in `pipeline/core/worktree.py:22` -- strips `uv`'s venv via
  `project_env()`. Never use bare `subprocess`.
- `ensure_worktree` (`pipeline/core/worktree.py:32`) already spells `cfg.get('base',
  'main')`; that literal is the default the gate must share, not re-invent.
- `cfg.get("worktree_setup")` (`pipeline/core/worktree.py:52`) -- a project that needs
  deps installed in a fresh checkout needs them in the base checkout too.
- The `"ok: "` prefix convention: `gate()` filters `failed = [f for f in findings if not
  f.startswith("ok:")]`, so a passing check still gets recorded in the thread.
- The `node not in out` guard at `pipeline/core/gate.py:73` -- an errored test exits
  non-zero exactly like a failing one. The base run needs the same guard for the same
  reason.

**Gotchas found while planning:**
- `tests/helpers.py::project()` builds a **non-git** directory (the `git init` in
  `tests/helpers.py` belongs to `git_project()`, a different function), and 14 of the 15
  tests in `tests/test_gate.py` gate it with `workdir=None`. The base check must skip when
  `wd.resolve() == project.resolve()`: there is no branch, so there is nothing to compare.
  That is also what makes `pipeline gate` from a project root keep working.
- **A test file the gate copies onto base must import nothing base does not have.**
  `gate()` copies `tests/test_gate.py` wholesale into the base checkout; if that file did
  `from helpers import git_ticket_project` and `helpers.py` on base had no such name, the
  copied module would fail to import, pytest would exit non-zero with a collection error,
  the node name would not appear in the output, and the gate would report "errored rather
  than failed on base" -- blocking a ticket at `revalidating`. (Not this ticket: the
  dispatcher imports `gate()` from the main checkout, so TICKET-017's own gate runs the
  pre-fix code until it merges. The rule binds every ticket after it.) Shared scaffolding
  for these tests therefore lives **inside `tests/test_gate.py`**, not in
  `tests/helpers.py`.
- `test_file` is validated by `SAFE_TEST` (`pipeline/core/ticket.py:29`), which permits
  `..` -- it only bans shell metacharacters. Today that is harmless because the gate only
  reads `wd / test`; the base run *writes* `base_wt / test`, so it needs its own
  `".." in rel` refusal.
- The `expect:` check stays bound to the branch run only. Triage flagged this: the base
  failure must never be the one that satisfies `expect:`.
- Cost: `git worktree add` + one `test_one` per gate, inside the select loop (see
  known-issue 14). Mitigated by only running the base check when the branch check already
  produced its `ok:`.
- The planning stage's guard blocks `git worktree` (`pipeline/hooks/dangerous-commands.py:190`),
  so the commands below were read from `ensure_worktree`, not executed. The implementer
  runs them only via `pytest`, whose command string contains no `git worktree`.

## Decisions checked

`.project/decisions/` holds exactly one record, **DEC-011** (daemon contract, still
active -- no `superseded-by:` line). Grepped it for `gate`, `base`, `worktree`,
`test_one`, `Tier A`, `reproduction`.

Relevant clause: the frozen event vocabulary lists
`| gate | gate() call sites | {verdict, findings:[...]} |`. This plan changes neither the
kind nor the shape -- it only adds entries to the existing `findings` list, and both
`emit("gate", ...)` call sites are untouched. Compliant, nothing superseded.

`git log --oneline -S "base" -- pipeline/core/gate.py` returns nothing: no prior commit
ever put a base run in the gate and removed it. This is an omission, not a reverted
workaround.

## Plan

1. In `pipeline/core/worktree.py`, add `def base_ref(cfg: dict) -> str: return str(cfg.get("base", "main"))` above `ensure_worktree`, with the docstring `"""One default for base, so the gate and the ticket's own checkout can never drift apart."""`, and replace the literal in `ensure_worktree`'s `add` string so it reads `f"{shlex.quote(base_ref(cfg))}"` instead of `f"{shlex.quote(str(cfg.get('base', 'main')))}"`.
2. In `pipeline/core/worktree.py`, add `import shutil`, `import tempfile` and `from contextlib import contextmanager` to the imports, then append this contextmanager after `drop_worktree`:

    ```python
    @contextmanager
    def base_checkout(project: Path, cfg: dict):
        """A throwaway detached checkout of base, outside the repo, for running a
        ticket's test against the code the ticket branched from. Yields
        `(path, "")`, or `(None, git's output)` when base cannot be checked out.

        Always removed. It is not a ticket's checkout: nothing resumes in it and
        nothing may be left behind for a human to look at."""
        tmp = Path(tempfile.mkdtemp(prefix="pipeline-base-"))
        wt = tmp / "base"
        code, out = run_cmd(
            f"git worktree add --detach {shlex.quote(str(wt))} "
            f"{shlex.quote(base_ref(cfg))}", project)
        try:
            if code:
                yield None, out
            else:
                if cfg.get("worktree_setup"):
                    run_cmd(cfg["worktree_setup"], wt)
                yield wt, ""
        finally:
            if not code:
                run_cmd(f"git worktree remove --force {shlex.quote(str(wt))}", project)
            shutil.rmtree(tmp, ignore_errors=True)
    ```

3. In `tests/test_gate.py`, add this scaffold immediately below the imports -- inside this file on purpose, see step 4:

    ```python
    def _git_ticket_project(base_py: str, branch_py: str):
        """A real git project: `main` holds `base_py`, the ticket worktree on
        `ticket/001` holds `branch_py`. Returns (project, worktree).

        Deliberately local to this file rather than in `helpers.py`: the gate
        copies THIS file onto a checkout of base, where only what base already
        has can be imported."""
        d = Path(tempfile.mkdtemp())
        sh = lambda c, cwd=d: subprocess.run(c, shell=True, cwd=cwd,
                                             capture_output=True, text=True)
        sh("git init -qb main && git config user.email t@t && git config user.name t")
        (d / "f.py").write_text(base_py)
        (d / "test_thing.py").write_text("")
        (d / ".project" / "tickets").mkdir(parents=True)
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "echo test_broken; grep -q fixed f.py"\n'
            'test_suite = "true"\n'
            'test_suite_without_new = "true"\n'
            'base = "main"\n')
        (d / ".project" / "tickets" / "TICKET-001.md").write_text(FIXTURE)
        sh("git add -A && git commit -qm init")
        wt = d / ".worktrees" / "TICKET-001"
        sh(f"git worktree add -q -b ticket/001 {wt} main")
        (wt / "f.py").write_text(branch_py)
        sh("git add -A && git commit -qm branch", cwd=wt)
        return d, wt
    ```

4. In `tests/test_gate.py`, replace the body of the existing `test_gate_blocks_a_test_that_passes_on_base` (its `git init` block through the `git commit -qm break`) with `d, wt = _git_ticket_project("fixed\n", "buggy\n")`, leaving its docstring and its four trailing lines (`gate(...)`, both asserts, `shutil.rmtree`) byte-identical -- this is the ticket's `test_file` and its evidence must not move.
5. Run `uv run --group dev pytest -q tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` and confirm it STILL fails with `AssertionError: gate passed a test that does not fail on base` -- the same assertion as before the refactor, proving step 4 did not defuse the reproduction; if it errors instead, stop and fix the scaffold in `tests/test_gate.py` before touching `pipeline/core/gate.py`.
6. In `tests/test_gate.py`, append the other half of the check, which must fail if the fix is "always report base":

    ```python
    def test_gate_passes_a_test_that_fails_on_base_too():
        """The complement: a test that fails identically on base and on the
        branch IS the reproduction Tier A demands, and the base check must not
        reject it."""
        d, wt = _git_ticket_project("buggy\n", "buggy\n")
        ok, failures = gate(d, "TICKET-001", workdir=wt)
        assert ok, failures
        assert "fails on base" in (d / ".project/tickets/TICKET-001.md").read_text()
        shutil.rmtree(d, ignore_errors=True)
    ```

7. Run `uv run --group dev pytest -q tests/test_gate.py::test_gate_passes_a_test_that_fails_on_base_too` and confirm it fails on the `"fails on base" in ...` assertion (the gate records no such finding yet), not on `assert ok` -- if `assert ok` fails, the scaffold in `tests/test_gate.py` is wrong, not the gate.
8. In `pipeline/core/gate.py`, add `import shutil` and change the worktree import to `from pipeline.core.worktree import base_checkout, base_ref, run_cmd`.
9. In `pipeline/core/gate.py`, add this function between `_cites` and `gate`:

    ```python
    def _base_findings(project: Path, cfg: dict, wd: Path, test: str,
                       node: str) -> list[str]:
        """A test that fails in the ticket's worktree proves the bug is HERE.
        Tier A wants more: that it fails on BASE, which is what makes it a
        reproduction rather than a branch that broke itself. The test itself
        only exists on the branch, so the branch's test file is copied onto a
        throwaway checkout of base: the branch's test, base's code."""
        if wd.resolve() == project.resolve():
            return ["ok: base check skipped -- no ticket worktree was given, so "
                    "there is no branch to compare against base"]
        rel = test.split("::")[0]
        if ".." in rel or rel.startswith("/"):
            # SAFE_TEST bans shell metacharacters, not traversal -- and unlike
            # the branch run, which only reads, this one WRITES the path.
            return [f"`{test}` is not a plain relative path -- refusing to copy "
                    f"it into a checkout of base"]
        base = base_ref(cfg)
        with base_checkout(project, cfg) as (base_wt, err):
            if base_wt is None:
                return [f"could not check out base `{base}` to re-run `{test}`"
                        f"\n```\n{err[-1200:]}\n```"]
            dst = base_wt / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wd / rel, dst)
            code, out = run_cmd(
                cfg["test_one"].format(test=shlex.quote(test)), base_wt)
        if code == 0:
            return [f"`{test}` PASSES on base `{base}` -- it fails only on this "
                    f"branch, so it is not a reproduction: either the bug is "
                    f"already fixed on base, or the test is red for a reason "
                    f"base does not have\n```\n{out[-1200:]}\n```"]
        if node not in out:
            # same trap as the branch run: an import error exits non-zero too,
            # and here that reads as a successful reproduction
            return [f"`{test}` exited non-zero on base `{base}` but its name "
                    f"never appears in the output -- it errored rather than "
                    f"failed, so base proves nothing\n```\n{out[-1200:]}\n```"]
        return [f"ok: `{test}` fails on base `{base}` too -- the bug is not "
                f"already fixed upstream\n```\n{out[-1200:]}\n```"]
    ```

10. In `pipeline/core/gate.py`, wire it into the one branch where the branch run succeeded, so the `else:` at line 89 becomes two lines -- the existing `findings.append(f"ok: \`{test}\` fails as required\n\`\`\`\n{out[-1200:]}\n\`\`\`")` followed by `findings += _base_findings(project, cfg, wd, test, node)` -- and leave the `code == 0`, `node not in out` and `expect` branches untouched so a base failure can never satisfy `expect:`.
11. Run `uv run --group dev pytest -q tests/test_gate.py` and confirm every test passes, including both `test_gate_blocks_a_test_that_passes_on_base` and `test_gate_passes_a_test_that_fails_on_base_too`.
12. Run `uv run --group dev pytest -q` and confirm the whole suite is green, not just `tests/test_gate.py` -- in particular `tests/test_ticket.py`, which calls `gate()` on the non-git project built by `tests/helpers.py` and must take the skip path rather than error.
13. In `pipeline/templates/pipeline.toml`, change the `base` line's documentation by adding the comment `# The branch tickets are cut from, and the one Tier A re-runs {test} against.` directly above `base                    = "main"`.
14. Commit with `git add pipeline/core/gate.py pipeline/core/worktree.py tests/test_gate.py pipeline/templates/pipeline.toml && git commit -m "fix: Tier A never ran the failing test against base"`.

## Acceptance criteria

- `tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` passes: a test that
  fails on `ticket/001` but passes on `main` is rejected, with `base` named in a finding.
- `tests/test_gate.py::test_gate_passes_a_test_that_fails_on_base_too` passes: a test that
  fails on both is accepted, and the ticket thread records `fails on base`. This is the
  criterion an "always fail the base check" implementation cannot satisfy.
- `tests/test_gate.py::test_gate_passes_a_complete_ticket` and the whole of
  `uv run --group dev pytest -q` still report zero failures -- that test and
  `tests/test_ticket.py` both gate a non-git project with no worktree, so both exercise
  the skip path.
- No leaked checkout: after `uv run --group dev pytest -q tests/test_gate.py`,
  `ls /tmp/pipeline-base-*` finds nothing.

## Decisions

**The Tier A reproduction is a two-run fact, and the base run is the load-bearing one.**
A test that fails in the ticket's worktree proves only that the branch is red. The gate
runs it a second time against base and requires the same failure there; that is what makes
it a *reproduction*. If a future change drops the base run to make the gate faster, the
gate is back to accepting a bug someone else already fixed -- which is exactly what
`revalidating` exists to catch, since base moved while the ticket sat at the human gate.

**The branch's test file is copied onto base; base is never asked for its own copy.** The
failing test is written by `triage` on the ticket branch and does not exist on base. A
naive "check out base and run `test_one`" exits non-zero for a missing file, which reads
as a successful reproduction -- failing open, in the one direction that matters. The
`node not in out` guard on the base run is the second line of defence and must stay.

**The base check is skipped when no ticket worktree was given, and this is not a hole.**
`wd.resolve() == project.resolve()` means the caller handed the gate the project checkout
itself: there is no branch, so there is nothing to compare. Both dispatcher call sites
always pass a worktree; only `pipeline gate` run by a human without one takes the skip,
and it records an `ok:` finding saying so. Do not "harden" this into a failure -- it would
break `pipeline gate` from a project root and every gate test built on
`tests/helpers.py::project()`.

**Test files that the gate copies onto base may only import what base has.**
`tests/test_gate.py` is copied wholesale into a base checkout and imported there. Adding
`from helpers import <something new>` to it makes that import fail on base, pytest exits
non-zero with a collection error, the node name never appears, and the gate reports
"errored rather than failed on base" -- blocking the very ticket that added the helper.
That is why `_git_ticket_project` lives inside `tests/test_gate.py` and not in
`tests/helpers.py`. The rule applies to any test file a ticket names in `test_file`.

**`base_ref(cfg)` is the single default.** `ensure_worktree` cuts the ticket branch from
it and the gate re-runs the test against it; two copies of `cfg.get("base", "main")` that
drift would have the gate proving a fact about a different branch than the one the ticket
was cut from.

**Known cost, accepted:** this adds a `git worktree add` plus a full `test_one` to every
gate run, synchronously inside the select loop (known-issue 14). It is bounded by running
only when the branch test already passed its checks -- a failing branch test never pays
for a base checkout. If the gate becomes the loop's bottleneck the fix is the one
known-issue 14 already names (run the gate as a spawned child like `verifying`), not
deleting the base run.

## Rollback

Revert the one commit from step 14 (`git revert <sha>`). It touches
`pipeline/core/gate.py`, `pipeline/core/worktree.py`, `tests/test_gate.py` and
`pipeline/templates/pipeline.toml` and nothing else; no schema, no frontmatter field, no
event kind and no stage changes, so nothing in flight needs migrating. Reverting restores
the pre-fix behaviour exactly: `gate()` runs `test_one` once, in the ticket's worktree,
and `tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` goes red again.

If only the cost is the problem and the check itself is wanted, the smaller rollback is to
make `_base_findings` return its skip finding unconditionally in `pipeline/core/gate.py` --
one line, the gate stays green, and the missing coverage is loud in every ticket thread
rather than silent.

## Thread

### 2026-08-21 03:13:42Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 03:18:14Z · triage · note

`triage` was interrupted; lease released

### 2026-08-21 03:33:42Z · human · note

**resumed** by human -> `triage`, reset ['blocked_count', 'lease_expiries', 'no_result']

### 2026-08-21 · triage · note

Confirmed by reading `pipeline/core/gate.py`: the only `run_cmd(cfg["test_one"] ...)`
call passes `wd`, which is `workdir or project` -- the ticket worktree in the
dispatcher's path. There is no second run and no reference to `cfg["base"]` anywhere
in the file. Ticket is valid.

Wrote `tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base`, committed as
`1240d83`. It fails with `AssertionError: gate passed a test that does not fail on
base`, i.e. because of the reported symptom, not a setup error (the gate ran, returned
`ok=True`).

Out of scope, noticed while here:
- The `.project/pipeline.toml` template has no documented `base` key contract for the
  gate; `ensure_worktree` defaults it to `main`. Whatever the fix does should reuse
  the same default rather than invent a second one.
- Running the test on base needs a checkout of base that is not the ticket worktree.
  `project` itself is the obvious one but it may be dirty; the planner should decide
  (worth considering `git worktree add --detach` for a throwaway, or running in
  `project` and accepting its state).
- The `## Reproduction` `expect:` line the gate checks is body text, so the fix must
  not make the base-run failure the one that satisfies `expect:`.

Also note the guard blocked a `cat >> file <<'EOF'` heredoc during this stage
("command does not parse as a shell command"); wrote the test with the file-edit tool
instead. No workaround attempted.

### 2026-08-21 03:49:37Z · triage · session · session=1be0c4f5-4acc-4302-9ccc-93d125f348c3

`triage` ran as session `1be0c4f5-4acc-4302-9ccc-93d125f348c3`
- replay: `claude --resume 1be0c4f5-4acc-4302-9ccc-93d125f348c3`
- log: `.project/logs/TICKET-017-triage-1be0c4f5.log`

### 2026-08-21 03:49:37Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

reproduced -- gate() runs test_one only in the ticket worktree, so a test that passes on base still passes Tier A; failing test committed as 1240d83

### 2026-08-21 04:23:14Z · planning · note

`planning` was interrupted; lease released

### 2026-08-21 · planning · note

The plan was already on the ticket from the interrupted `planning` run. This run
re-verified every claim in it against the code rather than trusting it, and corrected
three. No `rejection` entries in this thread, so nothing to answer for.

Verified true:
- `pipeline/core/gate.py:69` is the only `test_one` run; line 91 is
  `test_suite_without_new`. The file never mentions base.
- All three `gate()` call sites are where the Digest says they are:
  `pipeline/daemon/supervisor.py:518`, `pipeline/daemon/supervisor.py:591`,
  `pipeline/cli/main.py:73`.
- `SAFE_TEST` (`pipeline/core/ticket.py:29`) does permit `..`, so the base run needs its
  own traversal refusal: it writes the path, whereas the branch run only reads it.
- `git log --oneline -S "base" -- pipeline/core/gate.py` is empty. This is an omission,
  not a workaround someone removed on purpose.
- DEC-011 is the only decision record and is still active. Its frozen row is
  `| gate | gate() call sites | {verdict, findings:[...]} |`; the plan only adds entries
  to the existing `findings` list, changing no kind, column or field meaning.
- `pipeline/templates/pipeline.toml:6` already carries `base = "main"`, undocumented.
- Baseline: `uv run --group dev pytest -q tests/test_gate.py` gives `1 failed, 14
  passed`, the failure being this ticket's own test with the expected assertion.
- The `## Plan` section parses clean under `gate()`'s own step parser: every non-blank
  line is either a numbered step or an indented continuation, no prose lines.

Corrected in `## Digest`:
- "14 of the 16 tests" -- there are 15 tests in `tests/test_gate.py`, 14 of which gate
  without a worktree. Also recorded why `tests/helpers.py::project()` looks git-backed
  at a glance but is not: the `git init` in that file belongs to `git_project()`.
- "blocking this very ticket at `revalidating`" was an overstatement. The dispatcher
  imports `gate()` from the main checkout, so TICKET-017 is gated by the pre-fix code
  until it merges. The import rule still binds every ticket after it.
- Step 4 said "three trailing lines" where there are four.

Left as written, deliberately: a single `git worktree remove --force` is correct.
Doubling `--force` is only for a locked worktree, and `drop_worktree`
(`pipeline/core/worktree.py:61`) already uses one `--force` on ticket worktrees that
always carry untracked files.

Not verified by execution: the guard permits only `git worktree list`, so no
`git worktree add` or `remove` was run in this stage; those commands were read off
`ensure_worktree`. The implementer reaches them only through `pytest`. The guard also
blocked a `python3 - <<EOF` heredoc here, same as it did in triage -- the apostrophes in
the prose made it unparseable as a shell command. Used the file-edit tool. No workaround
attempted.

### 2026-08-21 04:28:04Z · planning · session · session=a4b76ca5-15e0-483f-b744-b9ecbe1597b4

`planning` ran as session `a4b76ca5-15e0-483f-b744-b9ecbe1597b4`
- replay: `claude --resume a4b76ca5-15e0-483f-b744-b9ecbe1597b4`
- log: `.project/logs/TICKET-017-planning-a4b76ca5.log`

### 2026-08-21 04:28:04Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

plan verified against the code and written -- gate re-runs the ticket test on a throwaway detached checkout of base with the branch's test file copied in; three factual errors in the inherited digest corrected

### 2026-08-21 04:28:11Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` fails as required
```
oject" / "tickets").mkdir(parents=True)
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "echo test_broken; grep -q fixed f.py"\n'
            'test_suite = "true"\n'
            'test_suite_without_new = "true"\n'
            'base = "main"\n')
        (d / ".project" / "tickets" / "TICKET-001.md").write_text(FIXTURE)
        sh("git add -A && git commit -qm init")
    
        wt = d / ".worktrees" / "TICKET-001"
        sh(f"git worktree add -q -b ticket/001 {wt} main")
        (wt / "f.py").write_text("buggy\n")
        sh("git add -A && git commit -qm break", cwd=wt)
    
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert not ok, "gate passed a test that does not fail on base"
E       AssertionError: gate passed a test that does not fail on base
E       assert not True

tests/test_gate.py:180: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```

### 2026-08-21 04:31:59Z · plan-validation · session · session=5436fb29-6eb6-41ad-893d-0226662bf899

`plan-validation` ran as session `5436fb29-6eb6-41ad-893d-0226662bf899`
- replay: `claude --resume 5436fb29-6eb6-41ad-893d-0226662bf899`
- log: `.project/logs/TICKET-017-plan-validation-5436fb29.log`

### 2026-08-21 04:31:59Z · plan-validation · note

`plan-validation` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-08-21 04:32:06Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` fails as required
```
oject" / "tickets").mkdir(parents=True)
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "echo test_broken; grep -q fixed f.py"\n'
            'test_suite = "true"\n'
            'test_suite_without_new = "true"\n'
            'base = "main"\n')
        (d / ".project" / "tickets" / "TICKET-001.md").write_text(FIXTURE)
        sh("git add -A && git commit -qm init")
    
        wt = d / ".worktrees" / "TICKET-001"
        sh(f"git worktree add -q -b ticket/001 {wt} main")
        (wt / "f.py").write_text("buggy\n")
        sh("git add -A && git commit -qm break", cwd=wt)
    
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert not ok, "gate passed a test that does not fail on base"
E       AssertionError: gate passed a test that does not fail on base
E       assert not True

tests/test_gate.py:180: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```

### 2026-08-21 04:36:36Z · plan-validation · session · session=72aac80c-cc36-4134-8bbf-18026908c1ae

`plan-validation` ran as session `72aac80c-cc36-4134-8bbf-18026908c1ae`
- replay: `claude --resume 72aac80c-cc36-4134-8bbf-18026908c1ae`
- log: `.project/logs/TICKET-017-plan-validation-72aac80c.log`

### 2026-08-21 04:36:36Z · plan-validation · escalation

`plan-validation` wrote no .result sidecar 2 times

### 2026-08-21 04:42:03Z · human · note

**resumed** by human -> `plan-validation`, reset ['no_result', 'blocked_count', 'lease_expiries']

### 2026-08-21 05:02:04Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` fails as required
```
oject" / "tickets").mkdir(parents=True)
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "echo test_broken; grep -q fixed f.py"\n'
            'test_suite = "true"\n'
            'test_suite_without_new = "true"\n'
            'base = "main"\n')
        (d / ".project" / "tickets" / "TICKET-001.md").write_text(FIXTURE)
        sh("git add -A && git commit -qm init")
    
        wt = d / ".worktrees" / "TICKET-001"
        sh(f"git worktree add -q -b ticket/001 {wt} main")
        (wt / "f.py").write_text("buggy\n")
        sh("git add -A && git commit -qm break", cwd=wt)
    
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert not ok, "gate passed a test that does not fail on base"
E       AssertionError: gate passed a test that does not fail on base
E       assert not True

tests/test_gate.py:180: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```

### 2026-08-21 · plan-validation · note

Judged the plan item by item. Every claim below was re-read off the code in this
worktree, not taken from `## Digest`.

**1. Root cause vs symptom — PASS.** In my own words: `gate()` runs the ticket's test
exactly once, in `wd = workdir or project`, which for both dispatcher call sites is the
ticket's worktree (`pipeline/core/gate.py:30`, the single `run_cmd(cfg["test_one"] ...)`
at line 69). "Red" is therefore a property of the branch alone; the gate never asks
whether base is red too, so a bug already fixed upstream — or a test red for a
branch-only reason — reads as a reproduction. `cfg["base"]` appears nowhere in the file.
The plan adds the missing second observation (same test, base's code) rather than
adjusting what the assertion accepts.

**2. Decision conflict — PASS.** `.project/decisions/` holds one record, DEC-011, with
no `superseded-by:`. Its only relevant clause is the frozen event row
`| gate | gate() call sites | {verdict, findings:[...]} |` (`DEC-011.md:74`). The plan
touches neither `emit("gate", ...)` call site (`supervisor.py:519`, `:592`) and only
appends strings to the existing `findings` list, so the kind and shape are unchanged.
Nothing to comply with beyond that, nothing superseded.

**3. Scope discipline — PASS, with one note.** Steps 1–12 and 14 trace to a criterion.
Step 13 (a `#` comment above `base` in `pipeline/templates/pipeline.toml:6`) traces to no
acceptance criterion. Not bounced: it is one comment line on the very key the fix makes
load-bearing for the gate, and the file is in `files_declared`. Flagging rather than
failing, since the cost of a planning retry exceeds the cost of the line.

**4. Falsifiable criteria — PASS, and this is the plan's strongest part.** The two
criteria are complements and no single cheat satisfies both: a no-op leaves
`test_gate_blocks_a_test_that_passes_on_base` red; an implementation that always emits a
base failure passes it but fails `test_gate_passes_a_test_that_fails_on_base_too`, whose
project is `_git_ticket_project("buggy\n", "buggy\n")` — red on branch and on base, the
reproduction Tier A must accept. Traced both by hand through `test_one =
"echo test_broken; grep -q fixed f.py"`: on base `f.py == "fixed"` gives exit 0 → the
`PASSES on base` finding (no `ok:` prefix → `failed` non-empty → `ok=False`); with
`f.py == "buggy"` it gives exit 1 with `test_broken` in the output → the `ok: ... fails
on base` finding, which is also the string the second test greps out of the thread. The
suite criterion is falsifiable too: it is what catches a skip path that errors instead.
The no-leak criterion is a real check, though it hardcodes `/tmp` where `mkdtemp` honours
`TMPDIR`.

**5. No research left — PASS.** Every step names a file and a symbol, and steps 2, 3, 6
and 9 give the code verbatim. Verified the anchors exist: `ensure_worktree` does spell
`cfg.get('base', 'main')` at `pipeline/core/worktree.py:47`, `drop_worktree` is at `:58`,
`_cites` and the `else:` branch the wiring targets are at `pipeline/core/gate.py:18` and
`:89-90`, and `pipeline/templates/pipeline.toml:6` is the undocumented `base` line. The
traversal refusal in step 9 is justified: `SAFE_TEST` (`pipeline/core/ticket.py:29`)
permits `.` and `/` freely — only `SAFE_FILE` at `:68` bans `..` and a leading `/` — and
the base run *writes* the path where the branch run only reads it.

**6. Riskiest step — PASS.** The riskiest step is 9/2: the base run is the one that can
fail *closed*, blocking a legitimate ticket, because a non-zero exit on base is
indistinguishable from an import error. The plan states the fallback twice: the `node not
in out` guard as the in-code second line of defence, and in `## Rollback` a one-line
degrade (`_base_findings` returns its skip finding unconditionally) that keeps the gate
green and makes the missing coverage loud in every thread, short of a full revert.

**7. Regression surface — PASS.** What could break is the 14 gate tests plus
`tests/test_ticket.py:269` that gate `tests/helpers.py::project()`, a **non-git**
directory: a base checkout there would fail and turn every one of them red. Confirmed by
grepping every `gate(` call in `tests/`: only `tests/test_gate.py:179` passes a
`workdir`, so all of them take the `wd.resolve() == project.resolve()` skip. Same for
`pipeline gate` from a project root (`pipeline/cli/main.py:73` passes `None` unless the
worktree exists). No test asserts on the length or exact content of `findings`, so the
new `ok:` entry breaks nothing (`tests/test_metrics.py` builds its own findings lists and
never calls `gate()`). Step 12 covers the whole suite. The accepted behaviour change —
a reproduction test that imports something base lacks now blocks at `revalidating` — is
documented in `## Decisions` and is self-consistent here: the step 3 scaffold uses only
`shutil`, `subprocess`, `tempfile`, `Path` and `FIXTURE`, all already imported at
`tests/test_gate.py:1-9` on base.

**8. Blast radius matches class — PASS.** `bugfix`, four files, one new function in each
of `gate.py` and `worktree.py` plus a contextmanager, one new test and one refactored
one. `files_declared` matches the set the plan touches exactly.

Also confirmed the sequencing the plan depends on: `revalidating` runs *before*
`implementing` (`pipeline/core/machine.py:54-55`), so the test is still red when
`finish_regate` re-gates — the base run is checking exactly the case the ticket names
(base moved under an approved plan).

Out of scope, noticed while here: if `git worktree remove --force` fails in
`base_checkout`'s `finally`, `shutil.rmtree` still deletes the directory, leaving a stale
prunable entry in the project's `.git/worktrees`. Harmless to `ensure_worktree`, which
addresses `.worktrees/<id>` by path, but a `git worktree prune` there would be tidier.

Read-only stage: nothing but this ticket was modified. The guard blocked `cd`, `sed -n`
and two commands containing `2>/dev/null` (read as shell redirection); re-issued them as
plain `cat`/`grep`/`ls` and used the file-read tool for line ranges. No workaround
attempted.

### 2026-08-21 05:06:03Z · plan-validation · session · session=9ccfbe4e-34a6-4897-a218-3c9b254137e6

`plan-validation` ran as session `9ccfbe4e-34a6-4897-a218-3c9b254137e6`
- replay: `claude --resume 9ccfbe4e-34a6-4897-a218-3c9b254137e6`
- log: `.project/logs/TICKET-017-plan-validation-9ccfbe4e.log`

### 2026-08-21 05:06:03Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

plan passes all eight judgment items -- fixes the root cause (gate() runs test_one only in the ticket worktree, never against base), complies with DEC-011, and its two criteria are complements no cheap implementation satisfies

### 2026-08-21 05:11:32Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 05:12:38Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base` fails as required
```
oject" / "tickets").mkdir(parents=True)
        (d / ".project" / "pipeline.toml").write_text(
            'test_one = "echo test_broken; grep -q fixed f.py"\n'
            'test_suite = "true"\n'
            'test_suite_without_new = "true"\n'
            'base = "main"\n')
        (d / ".project" / "tickets" / "TICKET-001.md").write_text(FIXTURE)
        sh("git add -A && git commit -qm init")
    
        wt = d / ".worktrees" / "TICKET-001"
        sh(f"git worktree add -q -b ticket/001 {wt} main")
        (wt / "f.py").write_text("buggy\n")
        sh("git add -A && git commit -qm break", cwd=wt)
    
        ok, failures = gate(d, "TICKET-001", workdir=wt)
>       assert not ok, "gate passed a test that does not fail on base"
E       AssertionError: gate passed a test that does not fail on base
E       assert not True

tests/test_gate.py:180: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate.py::test_gate_blocks_a_test_that_passes_on_base - Asse...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.05s ===============================

```

### 2026-08-21 05:12:38Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 05:12:59Z · implementing · todo

Working the 14-step plan in order:

1. [x] `base_ref(cfg)` in `worktree.py`, wire into `ensure_worktree`
2. [x] `base_checkout` contextmanager in `worktree.py`
3. [x] `_git_ticket_project` scaffold in `tests/test_gate.py`
4. [x] refactor `test_gate_blocks_a_test_that_passes_on_base` to use scaffold
5. [x] confirm step 4 still fails with same assertion
6. [x] add `test_gate_passes_a_test_that_fails_on_base_too`
7. [x] confirm it fails on the `"fails on base"` assertion, not `assert ok`
8. [x] import `base_checkout`, `base_ref` in `gate.py`
9. [x] `_base_findings` function in `gate.py`
10. [x] wire `_base_findings` into the `else:` branch
11. [x] `tests/test_gate.py` full run green (16 passed)
12. [x] whole suite green (165 passed); no leaked `/tmp/pipeline-base-*`
13. [x] doc comment on `base` in `pipeline/templates/pipeline.toml`
14. [x] commit

### 2026-08-21 · implementing · note

Executed the approved plan verbatim, no deviations. Verified at step 5 that the
refactored `test_gate_blocks_a_test_that_passes_on_base` still failed with the exact
same `AssertionError: gate passed a test that does not fail on base` before touching
`gate.py` -- the scaffold refactor did not defuse the reproduction. Verified at step 7
that the new complement test failed on the `"fails on base" in ...` assertion, not on
`assert ok`, confirming the scaffold itself was correct before the gate learned to
satisfy it. `tests/test_gate.py` (16 passed) and the whole suite (165 passed) are green;
`ls /tmp/pipeline-base-*` finds nothing after the run. Committed as `612e43f`, touching
exactly the four `files_declared` and nothing else.

No plan deviation to report: every claim in `## Plan` held against the code as written.

### 2026-08-21 05:15:20Z · implementing · session · session=8f78f43c-fd48-4c3f-9766-446687e9ac45

`implementing` ran as session `8f78f43c-fd48-4c3f-9766-446687e9ac45`
- replay: `claude --resume 8f78f43c-fd48-4c3f-9766-446687e9ac45`
- log: `.project/logs/TICKET-017-implementing-8f78f43c.log`

### 2026-08-21 05:15:20Z · implementing · transition · to=review · result=ok

**implementing -> review** (result: `ok`)

Plan executed exactly as written; Tier A now re-runs the ticket's test against a throwaway base checkout, both new tests and the whole 165-test suite pass, committed as 612e43f

### 2026-08-21 · review · note

First review pass. Delta reviewed: `git diff main...HEAD` (two commits, `d52748d` +
`612e43f`; `main` confirmed an ancestor of `HEAD`), four files, exactly the
`files_declared` set and nothing else. **No blocking findings.**

Verified rather than trusted:

1. **Both acceptance tests are non-vacuous — severity: none, this is the check that
   mattered.** Ran three in-memory mutations of `_base_findings` against the real test
   bodies (no file was modified; the fakes were installed on the imported module):

   | mutation | test | outcome |
   |---|---|---|
   | returns `[]` (fix removed) | `..._blocks_a_test_that_passes_on_base` | fails: `gate passed a test that does not fail on base` |
   | always reports a base failure | `..._passes_a_test_that_fails_on_base_too` | fails: `['fake PASSES on base']` |
   | always reports `ok: fails on base` | `..._blocks_a_test_that_passes_on_base` | fails: `gate passed a test that does not fail on base` |

   All three killed. No single cheap implementation satisfies both criteria.

2. **Acceptance criteria — all four met.** `tests/test_gate.py`: 16 passed. Whole suite:
   `165 passed in 6.02s`. `ls -d /tmp/pipeline-base-*` after both runs: `no matches
   found`. Fresh output, run in this worktree, not copied from `## Thread`.

3. **Wiring is where the plan said — severity: none.** `pipeline/core/gate.py:133` adds
   `findings += _base_findings(...)` inside the `else:` that already appended
   `ok: ... fails as required`; the `code == 0`, `node not in out` and `expect` branches
   at `:113-130` are byte-unchanged, so a base failure can never satisfy `expect:`, and a
   branch test that is red for the wrong reason never pays for a checkout. The
   `test_suite_without_new` run at `:134` still happens unconditionally.

4. **The skip path is real — severity: none.** `wd.resolve() == project.resolve()`
   returns an `ok:`-prefixed finding, so `failed` stays empty. The 165-test suite green
   is the evidence: 14 gate tests plus `tests/test_ticket.py` gate the non-git
   `helpers.py::project()` and would all error if the base checkout ran there.

5. **`git worktree remove --force` covers the copied test file — severity: none.**
   `_base_findings` writes an untracked/modified file into the base checkout; `remove`
   refuses on a dirty worktree without `--force`, and `--force` (single) is what
   `base_checkout`'s `finally` uses, matching `drop_worktree`. `--detach` is also what
   keeps the base checkout legal while `main` is checked out elsewhere.

6. **Stale worktree registration if `git worktree remove` fails — severity: low, not
   blocking, carried forward unchanged from `plan-validation`.** `shutil.rmtree` deletes
   the directory regardless, so a failed `remove` leaves a prunable entry in the
   project's `.git/worktrees`. Harmless (`ensure_worktree` addresses `.worktrees/<id>`
   by path) and self-clearing on any later `git worktree prune`; a `prune` in the
   `finally` would be tidier. Not worth a review loop.

7. **`ls /tmp/pipeline-base-*` ignores `TMPDIR` — severity: low, criterion wording
   only, also carried forward.** `tempfile.mkdtemp` honours `TMPDIR`; the criterion
   hardcodes `/tmp`. The check passed here because `TMPDIR` is unset.

8. **`base_checkout` ignores `worktree_setup`'s exit code — severity: nit.** A failed
   setup surfaces as `errored rather than failed on base`, which misnames the cause.
   `ensure_worktree:63` ignores it identically, so this matches the existing convention;
   changing one without the other would be the worse diff.

9. **Behaviour change worth knowing about, not a defect — severity: informational.**
   After this merges, a `test_file` that imports anything base lacks blocks its own
   ticket at the gate ("errored rather than failed on base"). It is documented in
   `## Decisions`, it is why `_git_ticket_project` lives in `tests/test_gate.py` rather
   than `tests/helpers.py` (confirmed: the scaffold uses only `shutil`, `subprocess`,
   `tempfile`, `Path` and `helpers.FIXTURE`, all present on base), and `## Rollback`
   gives a one-line degrade. Fails closed and loudly, which is the right direction.

Not verified, and I did not work around the guard to try: whether this repo's own
`test_one` (`uv run --group dev pytest -x {test}`, no `worktree_setup`) resolves its
deps in a `/tmp` checkout. `git clone` and `git worktree` are both off the review
allowlist. The same command already runs green in a fresh `.worktrees/<id>` checkout
(this ticket's own gate at 05:12:38Z), and the uv cache is global, so the risk is
low — but it is the first thing to look at if a post-merge ticket reports
`errored rather than failed on base` in this repo.

Read-only stage: only this ticket was modified; `git status --porcelain -- . ':(exclude).project'`
is empty after the test runs. The guard blocked `cd`, `sed -n`, `timeout`, `git clone`
and two multi-line `python -c` scripts; each was re-issued as an allowed form (the
file-read tool for line ranges, a scratch script under `/tmp` for the mutation run) and
`git clone` was dropped rather than worked around.

### 2026-08-21 05:20:18Z · review · session · session=90df32c8-600f-42a3-8560-613a2400ff05

`review` ran as session `90df32c8-600f-42a3-8560-613a2400ff05`
- replay: `claude --resume 90df32c8-600f-42a3-8560-613a2400ff05`
- log: `.project/logs/TICKET-017-review-90df32c8.log`

### 2026-08-21 05:20:18Z · review · transition · to=verifying · result=ok

**review -> verifying** (result: `ok`)

reviewed the two-commit delta; both acceptance tests survive three mutations of _base_findings, 16 gate tests and the 165-test suite green with no leaked base checkout, four non-blocking notes recorded

### 2026-08-21 05:20:24Z · verifying · transition · to=merging · result=ok

**verifying -> merging** (result: `ok`)

regression suite exit 0
```
...HEAD
ok  allow [always] cargo build --release
ok  BLOCK [readonly] sed -i s/a/b/ x.py
ok  BLOCK [readonly] echo hi > file.txt
ok  BLOCK [readonly] git commit -am wip
ok  BLOCK [readonly] cp a b
ok  BLOCK [readonly] pip install requests
ok  BLOCK [readonly] mv a b
ok  BLOCK [readonly] python3 -c "open('/tmp/x','a').write(1)"
ok  BLOCK [readonly] git -C . commit -am wip
ok  BLOCK [readonly] pytest 2>out
ok  BLOCK [readonly] pytest >> log.txt
ok  BLOCK [readonly] git worktree add /tmp/x main
ok  BLOCK [readonly] python3 setup.py install
ok  BLOCK [readonly] tee /tmp/x
ok  BLOCK [readonly] curl https://example.com -o /tmp/x
ok  BLOCK [readonly] make install
ok  BLOCK [readonly] cargo run
ok  BLOCK [readonly] npm install
ok  BLOCK [readonly] echo $(whoami)
ok  allow [readonly] pytest -x
ok  allow [readonly] git diff main...HEAD
ok  allow [readonly] grep -rn foo .
ok  allow [readonly] git log --oneline
ok  allow [readonly] cat thing.py
ok  allow [readonly] python3 -m pytest --deselect x
ok  allow [readonly] ls -la
ok  allow [readonly] git show HEAD
ok  allow [readonly] git blame thing.py
ok  allow [readonly] rg evict src/
ok  allow [readonly] pytest -x 2>&1
ok  allow [readonly] find . -name '*.py'
ok  allow [readonly] cargo test
ok  allow [readonly] go test ./...
ok  allow [readonly] git status --porcelain
ok  allow [readonly] wc -l thing.py
ok  allow [readonly] python3 -m unittest
ok  allow [readonly] git diff main...HEAD | head -50
ok  end-to-end exit codes

guard: all passed

```

### 2026-08-21 05:20:24Z · merging · transition · to=escalated · result=fail

**merging -> escalated** (result: `fail`)

merge exit 1
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/017


Already up to date.
main checkout is parked on pipeline-app, not the base branch -- refusing to land

```

### 2026-08-21 05:20:50Z · human · note

**resumed** by human -> `merging`, reset ['blocked_count', 'no_result', 'lease_expiries']

### 2026-08-21 05:22:26Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/017


Already up to date.
Updating cad2b6b..612e43f
Fast-forward
 pipeline/core/gate.py            | 45 +++++++++++++++++++++++++++++++++-
 pipeline/core/worktree.py        | 37 +++++++++++++++++++++++++++-
 pipeline/templates/pipeline.toml |  1 +
 tests/test_gate.py               | 53 ++++++++++++++++++++++++++++++++++++++++
 4 files changed, 134 insertions(+), 2 deletions(-)

```

### 2026-08-21 05:22:26Z · merging · decision

decision recorded as `DEC-017`
