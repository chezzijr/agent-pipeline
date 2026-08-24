"""Tier A gate: the checks that must not be talkable-out-of."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from helpers import FIXTURE, project
from pipeline.core import ticket as T
from pipeline.core.gate import gate


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


def test_gate_passes_a_complete_ticket():
    d = project()
    ok, failures = gate(d, "TICKET-001")
    assert ok, failures
    assert "Tier A gate: PASS" in (d / ".project/tickets/TICKET-001.md").read_text()
    shutil.rmtree(d)


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


def test_gate_blocks_a_test_that_errors_instead_of_failing():
    """A missing dependency exits non-zero exactly like a real failure."""
    d = project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo ModuleNotFoundError: no module named pytest; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = gate(d, "TICKET-001")
    assert not ok and any("errored rather than failed" in f for f in failures), failures
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
    shutil.rmtree(d)


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


def test_gate_passes_a_test_that_fails_on_base_too():
    """The complement: a test that fails identically on base and on the
    branch IS the reproduction Tier A demands, and the base check must not
    reject it."""
    d, wt = _git_ticket_project("buggy\n", "buggy\n")
    ok, failures = gate(d, "TICKET-001", workdir=wt)
    assert ok, failures
    assert "fails on base" in (d / ".project/tickets/TICKET-001.md").read_text()
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
