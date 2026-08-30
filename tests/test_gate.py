"""Tier A gate: the checks that must not be talkable-out-of."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from helpers import FIXTURE, project
from pipeline.core import ticket as T
from pipeline.core.config import project_config
from pipeline.core.gate import _base_findings, _dedupe, gate, plan_steps
from pipeline.core.machine import transition
from pipeline.daemon.supervisor import gate_result


def _set_digest(body: str) -> str:
    """FIXTURE with its `## Digest` content replaced by `body`.

    Derived from the fixture rather than matched against a copy of its digest
    text: a `.replace()` of a literal that has drifted no-ops *silently* and
    leaves the test asserting against an unmodified fixture. The assert below
    is what makes that drift loud.

    Deliberately local to this file, and stdlib-only, rather than a constant
    imported from `helpers`: DEC-017 -- the gate copies THIS file onto a
    checkout of base and imports it there, so a name that exists only on the
    branch turns the base run into a collection error."""
    out, n = re.subn(r"(?<=^## Digest\n).*?(?=^## Decisions checked$)",
                     body, FIXTURE, flags=re.S | re.M)
    assert n == 1, "FIXTURE's `## Digest` section moved -- _set_digest is stale"
    return out


def _git_ticket_project(base_py: str, branch_py: str,
                        test_one: str = "echo test_broken; grep -q fixed f.py"):
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
        'test_one = "%s"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "true"\n'
        'base = "main"\n' % test_one)
    (d / ".project" / "tickets" / "TICKET-001.md").write_text(FIXTURE)
    sh("git add -A && git commit -qm init")
    wt = d / ".worktrees" / "TICKET-001"
    sh(f"git worktree add -q -b ticket/001 {wt} main")
    (wt / "f.py").write_text(branch_py)
    sh("git add -A && git commit -qm branch", cwd=wt)
    return d, wt


def _cheap_route_project():
    """A real git project whose ticket branch already carries the cheap
    route's fix as its own commit, on top of triage's failing-test commit.

    Deliberately local to this file, stdlib-only: DEC-017 -- the gate copies
    THIS file onto a checkout of base and imports it there."""
    d = Path(tempfile.mkdtemp())
    sh = lambda c, cwd=d: subprocess.run(c, shell=True, cwd=cwd,
                                         capture_output=True, text=True)
    sh("git init -qb main && git config user.email t@t && git config user.name t")
    (d / "f.py").write_text("buggy\n")
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
    (wt / "test_thing.py").write_text("")
    sh("git add -A && git commit -qm 'triage: the failing test'", cwd=wt)
    triage_sha = sh("git rev-parse HEAD", cwd=wt).stdout.strip()
    (wt / "f.py").write_text("fixed\n")
    sh("git add -A && git commit -qm 'implementing: the fix'", cwd=wt)
    return d, wt, triage_sha


def test_gate_passes_a_complete_ticket():
    d = project()
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    assert "Tier A gate: PASS" in (d / ".project/tickets/TICKET-001.md").read_text()
    shutil.rmtree(d)


def test_test_file_cannot_hold_a_second_reproduction_test():
    """A bug needing two failing tests -- one per code path -- has nowhere
    to record the second: `test_file` is one string. `test_suite_without_new`
    can only exclude the one it knows, so a second, equally-legitimate new
    test stays red and the gate reports it as pre-existing breakage instead
    of recognising it as an expected new-test failure (TICKET-066).

    `validate_meta` should accept a list of tests here; it instead
    stringifies the list and rejects it as containing shell metacharacters."""
    meta = {"id": "TICKET-001", "branch": "ticket/001",
            "test_file": ["test_thing.py::test_broken",
                           "test_thing2.py::test_broken2"]}
    bad = T.validate_meta(meta)
    assert not any("shell metacharacters" in b for b in bad), bad


def test_gate_blocks_an_empty_digest():
    d = project(_set_digest(""))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("Digest" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_blocks_a_plan_of_prose():
    """Today this PASSES -- prose paragraphs sail through Tier A untouched."""
    d = project(FIXTURE.replace(
        "## Plan\n1. fix thing.py\n",
        "## Plan\nWe will refactor the cache and then fix the eviction bug.\n"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("names no declared file" in f for f in failures), failures
    shutil.rmtree(d)


def test_a_repeated_finding_names_the_extra_md_file_and_the_repeat_count():
    """TICKET-102: a finding that fires again on the same ticket must point
    at `.project/stages/planning.extra.md` and say how many times it has now
    fired. `planning` and not the gate's own `plan-validation`: the finding
    fires where the plan is judged, but a rule pinned where the judge reads
    it cannot stop the plan repeating the mistake. Today the second run
    repeats the bare finding verbatim, with no mention of `.project/stages/`
    at all."""
    d = project(_set_digest(""))
    gate(d, "TICKET-001")
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any(".project/stages/planning.extra.md" in f for f in failures), failures
    assert any("2" in f for f in failures), failures
    shutil.rmtree(d)


def test_a_first_time_finding_does_not_mention_extra_md():
    d = project(_set_digest(""))
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert not any(".project/stages/" in f for f in failures), failures
    shutil.rmtree(d)


def test_the_repeat_note_names_planning_and_the_entry_keeps_its_own_stage():
    """The note points at the stage that WRITES the plan; the thread entry
    stays under the stage that judged it. One constant for each, so a later
    edit cannot collapse them back into one."""
    d = project(_set_digest(""))
    gate(d, "TICKET-001")
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any(".project/stages/planning.extra.md" in f for f in failures), failures
    assert not any("plan-validation.extra.md" in f for f in failures), failures
    thread = T.sections((d / ".project/tickets/TICKET-001.md").read_text())["Thread"]
    assert "· plan-validation · gate" in thread, thread
    shutil.rmtree(d)


def test_a_repeated_finding_with_output_keeps_its_deduped_reference():
    """The repeat note must not cost the ticket its evidence: a finding
    carrying a fence is deduped (DEC-046) AND annotated, which is only
    possible because the repeat is keyed on the finding's first line."""
    d = project(FIXTURE.replace("expect: test_broken", "expect: absent_marker"))
    gate(d, "TICKET-001")
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    noted = [f for f in failures if "fired 2 times" in f]
    assert noted, failures
    assert "identical output" in noted[0], noted[0]
    assert ".project/stages/planning.extra.md" in noted[0], noted[0]
    shutil.rmtree(d)


def test_the_repeat_count_climbs_on_each_further_gate_run():
    """A third run says three, not two: the note is written as an indented
    continuation line, so `_count_findings()` never reads it back as a
    finding of its own."""
    d = project(_set_digest(""))
    gate(d, "TICKET-001")
    gate(d, "TICKET-001")
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("fired 3 times" in f for f in failures), failures
    shutil.rmtree(d)


def test_a_passing_gate_run_never_writes_the_repeat_note():
    """An `ok:` finding repeats on every re-gate by construction -- it is
    the evidence the gate passed, not a rule to pin."""
    d = project()
    assert gate(d, "TICKET-001")[0]
    assert gate(d, "TICKET-001")[0]
    thread = T.sections((d / ".project/tickets/TICKET-001.md").read_text())["Thread"]
    assert ".project/stages/" not in thread, thread
    shutil.rmtree(d)


def test_a_purely_structural_gate_failure_does_not_charge_a_plan_validation_attempt():
    """TICKET-065: a prose line above the numbered step fails Tier A on
    format alone -- the gate never judges the plan's content. `files_declared`
    is cited, so `_dedupe`'s only finding is the structural one; the gate never
    even reaches a substantive check. Charging `plan_validation_attempts` for
    this is charging the ticket for a typo, not a bad plan."""
    d = project(FIXTURE.replace(
        "## Plan\n1. fix thing.py\n",
        "## Plan\nDEC-003 sets the commit structure for thing.py: tests first.\n"
        "1. fix thing.py\n"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    real = [f for f in failures if not f.startswith("ok:")]
    assert all("is not a numbered step" in f for f in real), real
    nxt, counters = transition("plan-validation", "fail", {})
    assert counters.get("plan_validation_attempts", 0) == 0, (
        "a structural-only gate failure charged plan_validation_attempts: "
        f"{counters}")
    shutil.rmtree(d)


def test_a_nonexistent_test_file_does_not_charge_a_plan_validation_attempt():
    """TICKET-087: a `test_file` whose path half names no file on disk (e.g.
    a Rust module path `vm::tests::foo` with no `vm` file) is a typo triage
    should have caught, not a bad plan. `structural_only` must read the
    gate's "test file ... does not exist" finding as structural so
    `gate_result` returns `fail`, not `bad-plan`, and `plan_validation_attempts`
    is never charged for it."""
    d = project(FIXTURE.replace("test_thing.py::test_broken", "vm::tests::foo"))
    from pipeline.daemon.supervisor import gate_result
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("does not exist" in f for f in failures), failures
    result = gate_result(ok, failures, "plan-validation")
    nxt, counters = transition("plan-validation", result, {})
    assert counters.get("plan_validation_attempts", 0) == 0, (
        "a nonexistent test_file charged plan_validation_attempts: "
        f"{counters}")
    shutil.rmtree(d)


def test_gate_blocks_a_plan_step_citing_an_undeclared_path():
    d = project(FIXTURE.replace("1. fix thing.py", "1. fix other.py"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("names no declared file" in f for f in failures), failures
    assert any("files_declared" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_blocks_a_plan_step_whose_only_match_is_an_accidental_substring():
    """`io.py` must not be satisfied by a step that only mentions `ratio.py`
    -- a naive `path in step_text` lets an unrelated file "cite" a declared
    one just because its name happens to contain it."""
    d = project(FIXTURE.replace("files_declared: [thing.py]", "files_declared: [io.py]")
                        .replace("1. fix thing.py", "1. fix ratio.py"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("names no declared file" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_blocks_a_test_that_already_passes():
    d = project(test_passes=True)
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("PASSES" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_fails_an_exit_zero_test_and_names_both_causes():
    """`test_one` exiting 0 without ever naming the test is either a
    passing reproduction or a runner whose filter matched zero tests
    (TICKET-064). No portable signal separates them -- a runner names a
    node only on failure (TICKET-071) -- so one finding names both."""
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "true"\ntest_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    zero = [f for f in failures if "exited 0" in f]
    assert len(zero) == 1, failures
    assert "PASSES" in zero[0] and "matched no test" in zero[0], zero
    shutil.rmtree(d)


def test_gate_reports_a_pytest_style_pass_as_a_pass_not_a_bad_selector():
    """TICKET-071: pytest names a node only when it FAILS -- a genuine pass
    prints a dot and a count, never the node name. `code == 0 and node in out`
    is false for every real pass, so the gate falls into the TICKET-064
    branch and calls it a selector matching nothing, which is the wrong
    diagnosis for a project like this one."""
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo \'.                                    [100%]\'; '
        'echo \'1 passed in 0.03s\'; exit 0"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert not any("selector matched nothing" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_substitutes_the_name_placeholder_in_test_one():
    """`gate()` splits `test` into `path` and `name` for its own file check
    and output check (`test.split("::")`), but only ever formats the
    project's `test_one` with `test=...` -- TICKET-067. A project whose
    command wants `{name}` should get the substituted name, not a
    `KeyError`. Read the substituted output back from `## Thread`: `gate()`
    writes the entry, then `_dedupe()`s the copy it returns."""
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo GOT:{name}; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    gate(d, "TICKET-001")
    entry = T.Ticket.load(T.ticket_path(d, "TICKET-001")).thread()[-1].text
    assert "GOT:test_broken" in entry, entry
    shutil.rmtree(d)


def test_gate_substitutes_the_path_placeholder_in_test_suite_without_new():
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "echo GOT:{path}; exit 1"\n')
    ok, findings = gate(d, "TICKET-001")
    assert not ok and any("pre-existing breakage" in f for f in findings), findings
    entry = T.Ticket.load(T.ticket_path(d, "TICKET-001")).thread()[-1].text
    assert "GOT:test_thing.py" in entry, entry
    shutil.rmtree(d)


def test_gate_blocks_a_test_that_errors_instead_of_failing():
    """A missing dependency exits non-zero exactly like a real failure."""
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo ModuleNotFoundError: no module named pytest; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("errored rather than failed" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_distinguishes_a_suite_that_could_not_run_from_pre_existing_breakage():
    """A syntax error in the suite command exits non-zero without running any
    test -- TICKET-074. `gate()` must not report that as pre-existing
    breakage in the project's own tests."""
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "sh -c \'if ; then\'"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert not any("RED -- pre-existing breakage" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_reports_a_suite_that_ran_and_failed_as_pre_existing_breakage():
    """Exit 1 with NO output is a red suite, not a broken command -- it is
    what `! test -f broken` does in tests/test_dispatch.py."""
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "exit 1"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("RED -- pre-existing breakage" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_names_the_exit_code_when_the_suite_command_could_not_run():
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "echo boom >&2; exit 127"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    hits = [f for f in failures if "could not run the suite" in f]
    assert len(hits) == 1, failures
    assert "exited 127" in hits[0], hits[0]
    # the fence is deduped out of the returned finding, not out of the file
    entry = (d / ".project" / "tickets" / "TICKET-001.md").read_text()
    assert "boom" in entry, entry
    shutil.rmtree(d)


def test_gate_blocks_empty_files_declared():
    d = project(FIXTURE.replace("files_declared: [thing.py]", "files_declared: []"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("files_declared" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_blocks_a_vacuous_acceptance_criterion():
    d = project(FIXTURE.replace("- `test_broken` passes", "- code should be clean"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures
    shutil.rmtree(d)


def test_a_numbered_acceptance_criterion_naming_no_test_is_caught():
    """Numbered criteria must be checked exactly like bulleted ones."""
    d = project(FIXTURE.replace("- `test_broken` passes", "1. code should be clean"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures


def test_gate_base_suite_does_not_inherit_a_branch_defect_via_copied_test_file():
    """TICKET-104: `_copy_tests` copies the WHOLE test file the ticket
    names onto the base checkout, not just the new test node. When the
    branch itself broke something shared in that file, the base run
    inherits the branch's own defect and comes back RED too -- so `gate()`
    reports a branch defect as pre-existing/environment breakage that "is
    not this branch's doing", which is false: base's own original file
    never had the defect."""
    d = Path(tempfile.mkdtemp())
    sh = lambda c, cwd=d: subprocess.run(c, shell=True, cwd=cwd,
                                         capture_output=True, text=True)
    sh("git init -qb main && git config user.email t@t && git config user.name t")
    (d / "test_thing.py").write_text('SHARED = "good"\n')
    (d / ".project" / "tickets").mkdir(parents=True)
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; grep -q good test_thing.py"\n'
        'test_suite = "true"\n'
        "test_suite_without_new = \"echo '1 failed'; grep -q good test_thing.py\"\n"
        'base = "main"\n')
    (d / ".project" / "tickets" / "TICKET-001.md").write_text(FIXTURE)
    sh("git add -A && git commit -qm init")
    wt = d / ".worktrees" / "TICKET-001"
    sh(f"git worktree add -q -b ticket/001 {wt} main")
    # the branch's own defect: it broke SHARED, unrelated to the new test
    (wt / "test_thing.py").write_text('SHARED = "broken"\n')
    sh("git add -A && git commit -qm branch", cwd=wt)
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert not ok
    assert not any("is RED on base" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_still_reports_environment_when_base_lacks_the_branchs_test_file():
    """TICKET-104: the base suite run no longer copies the branch's test
    files, so a ticket whose test file is new leaves base without it. The
    TICKET-089 verdict must survive that -- a suite red on both for a reason
    neither branch introduced is still environment."""
    d = Path(tempfile.mkdtemp())
    sh = lambda c, cwd=d: subprocess.run(c, shell=True, cwd=cwd,
                                         capture_output=True, text=True)
    sh("git init -qb main && git config user.email t@t && git config user.name t")
    (d / ".project" / "tickets").mkdir(parents=True)
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "echo 1 failed; exit 1"\n'
        'base = "main"\n')
    (d / ".project" / "tickets" / "TICKET-001.md").write_text(FIXTURE)
    sh("git add -A && git commit -qm init")
    wt = d / ".worktrees" / "TICKET-001"
    sh(f"git worktree add -q -b ticket/001 {wt} main")
    (wt / "test_thing.py").write_text("def test_broken(): assert False")
    sh("git add -A && git commit -qm branch", cwd=wt)
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert not ok
    assert any(f.startswith("ENVIRONMENT: ") for f in failures), failures
    assert gate_result(ok, failures, "plan-validation") == "environment", failures
    shutil.rmtree(d, ignore_errors=True)


def test_numbered_criteria_are_checked_in_both_marker_forms():
    """Fails today: a `1)` criterion naming no test produces no finding.

    The second half guards against over-fixing: numbered criteria that do
    name a test must still pass.
    """
    d = project(FIXTURE.replace("- `test_broken` passes", "1) code should be clean"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures
    shutil.rmtree(d)

    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "1. `tests/test_cache.py::test_evicts` passes\n2) `test_broken` passes"))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_an_acceptance_criterion_must_name_something_test_shaped():
    d = project(FIXTURE.replace("- `test_broken` passes", "- latency drops below `10ms`"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures
    shutil.rmtree(d)

    d = project(FIXTURE.replace("- `test_broken` passes",
                                "- `tests/test_cache.py::test_evicts` passes"))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_wrapped_criterion_is_checked_whole_not_first_line_only():
    """DEC-042: the criteria scan does not join an indented continuation
    line onto the bullet above it, unlike the `## Plan` scan. A criterion
    whose test name falls on its second line draws a false `names no test`
    finding even though the whole criterion does name one.
    """
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- passes once the fix lands:\n  `test_broken` no longer errors"))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_wrapped_criterion_whose_continuation_starts_with_a_flag_passes():
    """TICKET-036 escalated on this exact shape: `CRIT_ITEM_RE` matches the
    leading `-` of `--porcelain`, so the continuation arm must run before the
    marker arm or the flag line is still read as a criterion of its own."""
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- `grep -rF probe tests/` prints nothing and `git status\n"
        "  --porcelain` prints nothing"))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_an_unindented_second_line_is_a_criterion_of_its_own():
    """Guards against over-fixing: only an indented line joins onto the
    criterion above it. An unindented second line is still checked alone and
    still fails if it names no test."""
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- `test_broken` passes and `git status\n"
        "--porcelain` prints nothing"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures
    shutil.rmtree(d)


def test_a_wrapped_criterion_naming_no_test_anywhere_still_fails():
    """Guards against over-fixing: joining the lines must not make a vacuous
    criterion pass just because it now spans two lines."""
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- the code is clean and\n"
        "  the latency drops below `10ms`"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_blocks_a_criterion_pinning_an_absolute_count_from_the_digest():
    """TICKET-081: a criterion that copies an absolute total out of `## Digest`
    goes stale the moment a sibling ticket or this ticket's own change moves
    that total. The gate has no check for this shape yet."""
    d = project(_set_digest("- thing.py holds it\n- 630 passed in tests/chz\n"
                             "- eviction runs on write, not read\n").replace(
        "- `test_broken` passes",
        "- `test_broken` passes\n- `tests/chz` suite: 630 passed"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("absolute count" in f for f in failures), failures
    shutil.rmtree(d)


def test_a_count_pinned_line_waives_the_absolute_count_check():
    """A bare `count-pinned:` line does not match `CRIT_ITEM_RE` and so
    raises no `names no test` finding of its own."""
    d = project(_set_digest("- thing.py holds it\n- 630 passed in tests/chz\n"
                             "- eviction runs on write, not read\n").replace(
        "- `test_broken` passes",
        "count-pinned: this ticket is what moves the number\n"
        "- `test_broken` passes\n- `tests/chz` suite: 630 passed"))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_number_a_criterion_refers_to_but_does_not_count_is_not_flagged():
    """The count noun follows the number in a count and precedes it in a
    reference, so a shared integer alone must not flag."""
    d = project(_set_digest("- thing.py holds it\n- README.md line 65 names it\n"
                             "- eviction runs on write, not read\n").replace(
        "- `test_broken` passes",
        "- `test_broken` passes, and `README.md` line 65 still names it"))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_count_a_criterion_measures_itself_is_not_flagged():
    """A count that appears in no `## Digest` line was not copied out of
    the digest."""
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- `test_broken` passes and `pytest -q` reports 630 passed"))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_test_shaped_criterion_pinning_a_count_is_still_flagged():
    """Pinning a total and naming a test are orthogonal, so this fails
    against any check placed inside `for c in crits:`."""
    d = project(_set_digest("- thing.py holds it\n- 630 passed in tests/chz\n"
                             "- eviction runs on write, not read\n").replace(
        "- `test_broken` passes",
        "- `tests/test_x.py::test_suite` passes and the suite reports 630 passed"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("absolute count" in f for f in failures), failures
    shutil.rmtree(d)


def test_a_top_level_fence_in_acceptance_criteria_is_not_read_as_criteria():
    """A fence at column 0 under `## Acceptance criteria` is quoted output,
    not a list of criteria -- its lines are skipped with no finding."""
    fence = "```"
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- `test_broken` passes\n\n%s\n- code should be clean\n%s" % (fence, fence)))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_fenced_block_indented_under_a_criterion_is_part_of_it():
    """An indented fence joins onto the criterion above it, so a criterion
    may quote the command that checks it."""
    fence = "```"
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- this prints nothing:\n\n  %s\n  pytest tests/test_thing.py\n  %s"
        % (fence, fence)))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_criterion_naming_a_command_and_its_expected_output_is_accepted():
    """TICKET-079: a criterion that names a command plus its observable
    result is falsifiable even though it names no test node id. The current
    regex only recognises a test-shaped token, so this reproduces the
    reported false rejection."""
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- `grep -c 'on an unreadable root' docs/stdlib.md` prints `0`"))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_criterion_naming_a_command_and_an_exit_status_is_accepted():
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- `uv run ruff check .` exits 0"))
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_command_criterion_with_no_stated_result_is_still_caught():
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- `cargo build --release` is nicer than before"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures
    shutil.rmtree(d)


def test_an_opinion_quoting_an_identifier_is_still_caught():
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- `pipeline/core/gate.py` is cleaner and the latency drops below `10ms`"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures
    shutil.rmtree(d)


def test_the_criterion_finding_states_the_rule_that_would_fix_it():
    d = project(FIXTURE.replace(
        "- `test_broken` passes",
        "- code should be clean"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any(
        "names no test" in f and "backticks" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_blocks_a_failure_that_is_not_the_reported_one():
    """A red test proves nothing if it is red for the wrong reason."""
    d = project(FIXTURE.replace("expect: test_broken", "expect: KeyError: 'evict'"))
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken: AssertionError: boom; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("does not mention" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_passes_a_failure_that_matches_the_reported_one():
    d = project(FIXTURE.replace("expect: test_broken", "expect: AssertionError: boom"))
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken: AssertionError: boom; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_expect_naming_a_temp_path_is_refused_as_unmatchable():
    """An `expect:` copied verbatim from triage's own run can carry a fresh
    `mkdtemp` path. That path cannot recur in any later run, so an expect
    that names one must be refused, not passed just because it happens to
    match on this one run (TICKET-076)."""
    tmp = tempfile.mkdtemp()
    d = project(FIXTURE.replace("expect: test_broken", f"expect: registered {tmp}"))
    (d / ".project" / "pipeline.toml").write_text(
        f'test_one = "echo test_broken: registered {tmp}; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok, (
        "gate passed an `expect:` string that names a temp path -- it "
        "cannot match a second run")
    assert any("cannot recur" in f for f in failures), failures
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)


def test_expect_ending_in_a_truncation_ellipsis_is_refused():
    """A trailing `...` is a reporter's truncation marker, not text any run
    emits (TICKET-076)."""
    d = project(FIXTURE.replace(
        "expect: test_broken",
        'expect: got: [CheckError { message: "no method", ...'))
    (d / ".project" / "pipeline.toml").write_text(
        "test_one = \"echo 'test_broken: got: [CheckError { message: no method, ...'; exit 1\"\n"
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("cannot recur" in f for f in failures), failures
    shutil.rmtree(d, ignore_errors=True)


def test_expect_holding_a_doubled_escape_is_reported_as_structural():
    """`expect` holds the two characters `\\` and `n` where the real output
    holds a newline, so the grep can never match (TICKET-076)."""
    d = project(FIXTURE.replace(
        "expect: test_broken",
        r"expect: AssertionError: a thing\n(no log yet)"))
    (d / ".project" / "pipeline.toml").write_text(
        "test_one = \"echo test_broken: AssertionError: a thing; echo '(no log yet)'; exit 1\"\n"
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any(f.startswith("`## Reproduction` `expect:` cannot recur") for f in failures), failures
    assert not any("does not mention" in f for f in failures), failures
    shutil.rmtree(d, ignore_errors=True)


def test_expect_naming_a_project_path_is_not_refused():
    """A path under the project, not the system temp dir, is stable and must
    still gate green (TICKET-076)."""
    d = project(FIXTURE.replace(
        "expect: test_broken",
        "expect: no such file: .project/pipeline.toml"))
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken: no such file: .project/pipeline.toml; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d, ignore_errors=True)


def test_expect_containing_a_backtick_does_not_corrupt_the_thread_entry():
    """`expect:` is unvalidated body text an agent wrote -- a backtick in it
    must not break out of the markdown fence the finding is written into."""
    d = project(FIXTURE.replace("expect: test_broken", "expect: `evict`"))
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken: nope; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any(repr("`evict`") in f for f in failures), failures
    shutil.rmtree(d)


def test_shell_injection_through_test_file_is_dead():
    """The gate runs the project's test command; test_file comes from an agent."""
    d = project()
    marker = d / "PWNED"
    path = d / ".project/tickets/TICKET-001.md"
    meta, body = T.split_frontmatter(path)
    meta["test_file"] = f"test_thing.py::test_x; touch {marker}"
    T.write_atomic(path, T.render(meta, body))   # Ticket.save() would refuse it
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo {test}"\ntest_suite = "true"\n'
        'test_suite_without_new = "echo {test}"\n')
    assert T.validate_meta(meta), "validation must reject it before anything runs"
    gate(d, "TICKET-001")
    assert not marker.exists(), "command substitution executed"
    shutil.rmtree(d)


def test_gate_blocks_a_test_that_passes_on_base():
    """Tier A must prove the bug exists on base, not only on the ticket branch.
    Here the branch's test fails but base is green -- someone already fixed it
    -- so this is not a reproduction and the gate must say so."""
    d, wt = _git_ticket_project("fixed\n", "buggy\n")
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert not ok, "gate passed a test that does not fail on base"
    assert any("base" in f for f in failures), failures
    shutil.rmtree(d, ignore_errors=True)


def test_gate_falls_through_to_base_when_the_worktree_test_already_passes():
    """TICKET-090: a ticket resumed to `plan-validation` after `implementing`
    has already landed the fix has a worktree where `test_file` now PASSES.
    Today that reads as an unresolvable exit-0 ambiguity and the gate can
    never pass again. It must instead fall through to the base check: base
    still has the bug, which is the durable proof the branch already fixed
    it, and the gate must PASS on that."""
    d, wt = _git_ticket_project("buggy\n", "fixed\n")
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert ok, failures
    shutil.rmtree(d, ignore_errors=True)


def test_gate_still_fails_when_the_worktree_and_base_both_pass():
    """The fall-through credits only a test that FAILS on base, so a branch
    whose test passes where base's passes too is still not a reproduction."""
    d, wt = _git_ticket_project("fixed\n", "fixed\n")
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert not ok, failures
    assert any("exited 0" in f and "PASSES" in f for f in failures), failures
    shutil.rmtree(d, ignore_errors=True)


def test_gate_names_both_causes_when_the_test_exits_zero_on_base():
    """The base run carries the branch run's exit-0 ambiguity: `test_one`
    exits 0 on base without printing the node, which is a pass there or a
    selector that matched nothing, and nothing separates them. No literal
    brace in the command -- `str.format` raises KeyError on one."""
    d, wt = _git_ticket_project("fixed\n", "buggy\n")
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "grep -q fixed f.py && exit 0; echo test_broken; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\nbase = "main"\n')
    subprocess.run("git add -A && git commit -qm cfg", shell=True, cwd=d,
                   capture_output=True, text=True)
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert not ok
    zero = [f for f in failures if "exited 0 on base" in f]
    assert len(zero) == 1, failures
    assert "matched no test" in zero[0], zero
    shutil.rmtree(d, ignore_errors=True)


def test_gate_passes_a_test_that_fails_on_base_too():
    """The complement: a test that fails identically on base and on the
    branch IS the reproduction Tier A demands, and the base check must not
    reject it."""
    d, wt = _git_ticket_project("buggy\n", "buggy\n")
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert ok, failures
    assert "fails on base" in (d / ".project/tickets/TICKET-001.md").read_text()
    shutil.rmtree(d, ignore_errors=True)


def test_the_base_run_covers_every_listed_test():
    """DEC-017 with two tests: both branch test files are copied onto ONE
    checkout of base and both are re-run there."""
    d, wt = _git_ticket_project("buggy\n", "buggy\n",
                                test_one="echo {name}; grep -q fixed f.py")
    (wt / "test_thing2.py").write_text("")
    subprocess.run("git add -A && git commit -qm second", shell=True, cwd=wt,
                   capture_output=True, text=True)
    out, on_base = _base_findings(d, project_config(d), wt,
                         ["test_thing.py::test_broken",
                          "test_thing2.py::test_broken2"])
    for one in ("test_thing.py::test_broken", "test_thing2.py::test_broken2"):
        assert any(f.startswith(f"ok: `{one}` fails on base") for f in out), out
    assert set(on_base) == {"test_thing.py::test_broken",
                            "test_thing2.py::test_broken2"}, on_base
    shutil.rmtree(d, ignore_errors=True)


def test_the_gate_runs_and_excludes_every_listed_test():
    """TICKET-066: with two reproduction tests the gate runs `test_one`
    for each and excludes BOTH from `test_suite_without_new` -- the second
    used to come back as pre-existing breakage."""
    d = project(FIXTURE.replace(
        "test_file: test_thing.py::test_broken",
        "test_file: [test_thing.py::test_broken, test_thing2.py::test_broken2]"))
    (d / "test_thing2.py").write_text("")
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo {name}; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "echo {test:--deselect } | '
        'grep -q -- \'--deselect test_thing2.py::test_broken2\'"\n')
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    # `gate()` returns only the findings that do NOT start with `ok:`, so
    # the `ok:` lines are read off the thread entry it wrote and saved --
    # the same way the substituted-command test reads it.
    text = (d / ".project/tickets/TICKET-001.md").read_text()
    for one in ("test_thing.py::test_broken", "test_thing2.py::test_broken2"):
        assert f"ok: `{one}` fails as required" in text, text
    shutil.rmtree(d, ignore_errors=True)


def test_a_bare_test_placeholder_is_refused_for_a_multi_test_ticket():
    """`pytest --deselect a b` deselects `a` and SELECTS `b`. With two
    tests a bare `{test}` runs the wrong suite, so the gate refuses it and
    names the fix. `{test:}` is the escape hatch for a runner that does
    take several values after one flag."""
    d = project(FIXTURE.replace(
        "test_file: test_thing.py::test_broken",
        "test_file: [test_thing.py::test_broken, test_thing2.py::test_broken2]"))
    (d / "test_thing2.py").write_text("")
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo {name}; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "true --deselect {test}"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("{test:" in f for f in failures), failures
    shutil.rmtree(d, ignore_errors=True)


def test_a_bare_rest_placeholder_is_refused_for_a_multi_test_ticket():
    """`{rest}` shares the same substitution regex as `{test}`, `{path}` and
    `{name}`, so it must share the same bare-placeholder refusal: a bare
    `{rest}` in `test_suite_without_new` skips one test's rest value and
    RUNS the other's when the ticket lists more than one test."""
    d = project(FIXTURE.replace(
        "test_file: test_thing.py::test_broken",
        "test_file: [test_thing.py::test_broken, test_thing2.py::test_broken2]"))
    (d / "test_thing2.py").write_text("")
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo {name}; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "true --skip {rest}"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("{rest:" in f for f in failures), failures
    shutil.rmtree(d, ignore_errors=True)


def test_a_ticket_promoted_from_quick_review_meets_a_gate_it_cannot_pass():
    """`triage` can route a small ticket onto the cheap route: `chore` sets
    `cheap_route` and sends it straight to `implementing`, skipping
    `planning` and `plan-validation`. `implementing` commits the fix and the
    ticket goes to `quick-review`. When `quick-review` answers `fail`, the
    ticket is promoted through a new dispatcher stage, `unwinding`, which
    discards the cheap route's own commit before handing the ticket to
    `planning` -- triage's failing-test commit survives. The repair must
    leave a tree where `test_file` still fails, so the promoted ticket's
    gate() passes Tier A."""
    stage, counters = "triage", {}
    stage, counters = transition(stage, "chore", counters)
    assert stage == "implementing" and counters.get("cheap_route") == 1
    stage, counters = transition(stage, "ok", counters)
    assert stage == "quick-review" and "cheap_route" not in counters
    stage, counters = transition(stage, "fail", counters)
    assert stage == "unwinding", \
        "planning is handed a branch that still carries the cheap route's fix"
    assert transition("unwinding", "ok", counters)[0] == "planning"

    d, wt, triage_sha = _cheap_route_project()
    subprocess.run(f"git reset --hard {triage_sha}", shell=True, cwd=wt,
                   capture_output=True, text=True)
    assert (wt / "test_thing.py").is_file(), "the repair discarded triage's test commit"

    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert ok, failures
    shutil.rmtree(d, ignore_errors=True)


def test_gate_blocks_a_one_word_digest_and_an_unresolvable_decision_id():
    """Both Tier A content checks are non-emptiness only: a digest of one word
    passes, and a cited `DEC-999` passes though no such record exists in
    `.project/decisions/`."""
    d = project(_set_digest("x\n")
                .replace("none relevant (grepped: cache, evict)", "DEC-999"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
    assert any("Digest" in f for f in failures), failures
    assert any("DEC-999" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_notes_a_superseded_decision_and_accepts_a_justified_short_digest():
    """A cited id that resolves must not fail; a superseded one is history, not
    a finding; and a short digest passes only when it says why it is short."""
    d = project(_set_digest("digest-short: one file, one line\n"
                            "- thing.py holds it\n")
                .replace("none relevant (grepped: cache, evict)",
                         "checked DEC-002 (superseded) and DEC-003"))
    dec = d / ".project" / "decisions"
    dec.mkdir()
    (dec / "DEC-002.md").write_text(
        "# DEC-002\n\nold\n\n%s\n- superseded-by: DEC-003 (2026-08-21)\n"
        % T.SUPERSEDED_MARKER)
    (dec / "DEC-003.md").write_text("# DEC-003\n\nstill binding\n")
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    text = (d / ".project/tickets/TICKET-001.md").read_text()
    assert "DEC-002 is superseded" in text, text
    shutil.rmtree(d)


def test_an_unindented_fence_is_reported_once_not_once_per_line():
    """TICKET-031's plan quoted its implementation and the gate reported every
    line of it twice -- 262 findings, all written into the thread that every
    later stage then reads through `stage_view()`. The block is still
    rejected; it is reported as one block."""
    fence = "```"
    d = project(FIXTURE.replace(
        "## Plan\n1. fix thing.py\n",
        "## Plan\n1. fix thing.py\n%spython\nimport re\nx = 1\nreturn None\n%s\n"
        % (fence, fence)))
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    plan_findings = [f for f in failures
                     if "not a numbered step" in f or "names no declared file" in f]
    assert len(plan_findings) == 1, plan_findings
    assert "indent" in plan_findings[0].lower(), plan_findings
    shutil.rmtree(d)


def test_a_numbered_step_cannot_hide_inside_a_fence():
    """The reason the block is reported rather than skipped. `implementing`
    reads `## Plan` whole, fence included, so a step hidden in one would be
    executed having never been checked against `files_declared` -- the
    declaration `files_conflict()` trusts to keep two tickets off one file.

    A silent skip made this exact plan return `(True, [])`, with steps
    rewriting the guard and deleting a test suite."""
    fence = "```"
    d = project(FIXTURE.replace(
        "## Plan\n1. fix thing.py\n",
        "## Plan\n1. fix thing.py\n%s\n"
        "2. also rewrite pipeline/hooks/dangerous-commands.py\n"
        "3. delete tests/test_gate.py\n%s\n" % (fence, fence)))
    ok, failures = gate(d, "TICKET-001")
    assert not ok, "a plan smuggling steps past the declared-file rule must fail"
    shutil.rmtree(d)


def test_a_step_keeps_its_indented_fence():
    """The legal form, and the one PLAN_STEP_RULE tells the writer to use.

    ANY indent, not four: `FENCE_RE` is `^ {0,3}`, so a three-space fence is
    still a real fence to `_fenced()` -- but to a plan's grammar it is a
    continuation of the step above. Gating on `_fenced()` alone failed such a
    plan with a finding telling it to indent the block, which it had done, and
    `plan_validation_attempts` ran out on the re-try."""
    fence = "```"
    for pad in (" ", "   ", "    "):
        d = project(FIXTURE.replace(
            "## Plan\n1. fix thing.py\n",
            "## Plan\n1. fix thing.py\n{p}{f}python\n{p}x = 1\n{p}{f}\n{p}then re-run it\n"
            .format(p=pad, f=fence)))
        ok, failures = gate(d, "TICKET-001")
        assert ok, (len(pad), failures)
        shutil.rmtree(d)


def test_the_line_after_a_rejected_fence_is_not_charged_again():
    """"Reported once" has to mean once. Clearing the step state after the
    block made the indented line following it read as fresh prose, so a single
    fence produced three findings -- the storm this branch exists to end."""
    fence = "```"
    d = project(FIXTURE.replace(
        "## Plan\n1. fix thing.py\n",
        "## Plan\n1. fix thing.py\n%spython\nx = 1\n%s\n    then re-run it\n"
        % (fence, fence)))
    ok, failures = gate(d, "TICKET-001")
    plan_findings = [f for f in failures if "not a numbered step" in f
                     or "names no declared file" in f]
    assert len(plan_findings) == 1, plan_findings
    shutil.rmtree(d)


def test_a_tilde_or_longer_fence_is_one_finding_too():
    """The gate must agree with `_fenced()` on what code is. A local
    `startswith("```")` scan missed `~~~` entirely -- eight findings for a
    four-line block -- and a nested 4-backtick block inverted its own parity,
    swallowing the real step that followed it."""
    for opener, closer in (("~~~python", "~~~"), ("````python", "````")):
        d = project(FIXTURE.replace(
            "## Plan\n1. fix thing.py\n",
            "## Plan\n1. fix thing.py\n%s\nimport re\nx = 1\nreturn None\n%s\n"
            % (opener, closer)))
        ok, failures = gate(d, "TICKET-001")
        plan_findings = [f for f in failures if "not a numbered step" in f
                         or "names no declared file" in f]
        assert len(plan_findings) == 1, (opener, plan_findings)
        shutil.rmtree(d)


def test_a_prose_finding_states_the_rule_that_would_fix_it():
    """`3f87848`: prose in `## Plan` was rejected with only the offending line
    quoted. The rule that would fix it -- indent the line under the step it
    belongs to -- lives in `planning.md` and never reached the agent that had
    to act on the failure. Unfenced prose still trips this; only fenced code
    stopped doing so."""
    d = project(FIXTURE.replace(
        "## Plan\n1. fix thing.py\n",
        "## Plan\n1. fix thing.py\nthis sentence is not a step\n"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    prose = [f for f in failures if "not a numbered step" in f]
    assert prose, failures
    assert any("indent" in f.lower() for f in prose), prose
    shutil.rmtree(d)


def test_a_whole_suite_criterion_naming_pytest_is_accepted():
    """`pytest` has no word boundary before `test`, so the criteria regex --
    `\\btest[_a-zA-Z0-9]*\\b|::|...` -- matched nothing in "run `pytest -q`".
    That is the whole-suite criterion `CLAUDE.md`'s own Commands section
    writes, and it cost TICKET-041 a plan-validation attempt on 2026-08-23
    against a plan the gate had no other finding on.

    Fails without the `\\bpytest\\b` alternative: the criterion is reported as
    naming no test. The second criterion is the guard against over-fixing --
    dropping the `\\b` instead would make `latest` a test name."""
    d = project(FIXTURE.replace(
        "## Acceptance criteria\n- `test_broken` passes\n",
        "## Acceptance criteria\n- `test_broken` passes\n"
        "- `uv run --group dev pytest -q` reports no failures\n"
        "- the latest build is the greatest\n"))
    ok, failures = gate(d, "TICKET-001")
    named = [f for f in failures if "names no test" in f]
    assert not any("pytest" in f for f in named), named
    assert any("latest build" in f for f in named), named
    shutil.rmtree(d)


def test_a_regate_of_an_unchanged_ticket_does_not_duplicate_the_fenced_block():
    """TICKET-046: `gate()` appends one `## Thread` entry per run, and each
    entry quotes `out[-1200:]` in full. A re-gate on an unchanged ticket
    re-runs the same test against the same code, so the branch fence and the
    base fence it produces are byte-identical to the ones the first gate run
    already wrote. Nothing dedupes them.

    Fails today: two runs put two copies of the same fenced block in
    `## Thread` instead of one."""
    d = project()
    ok1, _ = gate(d, "TICKET-001")
    assert ok1
    ok2, _ = gate(d, "TICKET-001")
    assert ok2
    thread = T.sections((d / ".project/tickets/TICKET-001.md").read_text())["Thread"]
    fences = re.findall(r"```\n.*?\n```", thread, re.S)
    assert len(fences) == len(set(fences)), \
        f"expected every fenced block to be unique, got {len(fences)} blocks, " \
        f"{len(set(fences))} unique"
    shutil.rmtree(d)


def test_dedupe_replaces_a_repeated_fence_and_keeps_the_first():
    """TICKET-046: the first copy of a body stays verbatim; a later copy of
    the same body becomes a one-line reference to the entry that carries it.
    Fails today: `_dedupe` does not exist."""
    seen: dict[str, str] = {}
    first = _dedupe("first prose\n```\nboom\n```\n", seen, "this entry, above")
    assert "```\nboom\n```" in first
    second = _dedupe("second prose\n```\nboom\n```\n", seen, "x")
    assert "```" not in second
    assert "this entry, above" in second

    fresh: dict[str, str] = {}
    _dedupe("prose\n~~~\nboom\n~~~\n", fresh, "x")
    assert fresh == {"boom": "x"}


def test_one_gate_run_quotes_the_branch_and_base_output_once():
    """TICKET-046: the branch run and the base run of the same test produce
    byte-identical output, so one `gate()` run should quote it once and
    reference it the second time. Fails today: 2 blocks, 1 unique."""
    d, wt = _git_ticket_project("buggy\n", "buggy\n")
    ok, _ = gate(d, "TICKET-001", workdir=wt)
    assert ok
    thread = T.sections((d / ".project/tickets/TICKET-001.md").read_text())["Thread"]
    fences = re.findall(r"```\n.*?\n```", thread, re.S)
    assert len(fences) == 1, fences
    assert "identical output, already quoted in this entry, above" in thread
    shutil.rmtree(d, ignore_errors=True)


def test_a_failed_gate_returns_a_reference_not_a_second_copy_of_the_output():
    """TICKET-046: `gate()` writes its findings into `## Thread` and then
    returns them; returning the fence verbatim puts the same output in the
    thread twice in one tick, once written by `gate()` and once by whatever
    copies the returned findings into a note of its own. Fails today: the
    returned failure still carries the fence."""
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo nope; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok
    assert any("never appears" in f for f in failures), failures
    assert not any("```" in f for f in failures), failures
    assert any("## Thread` entry" in f for f in failures), failures
    thread = T.sections((d / ".project/tickets/TICKET-001.md").read_text())["Thread"]
    assert thread.count("nope") == 1, thread
    shutil.rmtree(d, ignore_errors=True)


def test_plan_steps_counts_only_unfenced_numbered_steps():
    plan = (
        "1. fix thing.py\n"
        "   continue the fix\n"
        "2. fix other.py\n"
        "   ```\n"
        "   2. not a step\n"
        "   ```\n"
        "3. fix third.py\n"
    )
    assert plan_steps(plan) == 3


def test_a_suite_red_identically_on_base_does_not_charge_plan_validation_attempts():
    """TICKET-089: `test_suite_without_new` runs only in the ticket's worktree.
    A suite that is red for a reason base ALSO has -- an environment problem,
    not this ticket's doing -- must not be charged as a bad plan. Today
    `gate()` never re-runs the suite on base, so the finding is indistinguishable
    from a real pre-existing-breakage-caused-by-this-branch finding and
    `gate_result()` charges `plan_validation_attempts` for it."""
    d, wt = _git_ticket_project("buggy\n", "buggy\n")
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "echo 1 failed; exit 1"\n'
        'base = "main"\n')
    subprocess.run("git add -A && git commit -qm cfg", shell=True, cwd=d,
                   capture_output=True, text=True)
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert not ok
    breakage = [f for f in failures if "RED -- pre-existing breakage" in f]
    assert breakage, failures
    res = gate_result(ok, failures, "plan-validation")
    _, counters = transition("plan-validation", res, {})
    assert counters.get("plan_validation_attempts", 0) == 0, (
        f"suite failed identically on base too but still charged "
        f"plan_validation_attempts: {counters}")
    shutil.rmtree(d, ignore_errors=True)


def test_a_suite_red_only_in_the_worktree_still_charges_the_plan():
    """TICKET-089: base is green, so the environment verdict must not fire --
    today's verdict and today's charge both stand."""
    d, wt = _git_ticket_project("buggy\n", "buggy\n")
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; exit 1"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "! test -f broken"\n'
        'base = "main"\n')
    subprocess.run("git add -A && git commit -qm cfg", shell=True, cwd=d,
                   capture_output=True, text=True)
    (wt / "broken").write_text("")
    subprocess.run("git add -A && git commit -qm broken", shell=True, cwd=wt,
                   capture_output=True, text=True)
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert not ok
    assert any("RED -- pre-existing breakage" in f for f in failures), failures
    assert not any(f.startswith("ENVIRONMENT: ") for f in failures), failures
    res = gate_result(ok, failures, "plan-validation")
    assert res == "bad-plan"
    _, counters = transition("plan-validation", res, {})
    assert counters["plan_validation_attempts"] == 1
    shutil.rmtree(d, ignore_errors=True)
