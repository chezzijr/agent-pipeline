"""Tier A gate: the checks that must not be talkable-out-of."""
import shutil
import subprocess
import tempfile
from pathlib import Path

from helpers import FIXTURE, project
from pipeline.core import ticket as T
from pipeline.core.gate import gate


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
    d = project(FIXTURE.replace("## Digest\nthing.py holds it\n", "## Digest\n"))
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
    d = project(FIXTURE.replace("## Digest\nthing.py holds it\n", "## Digest\nx\n")
                       .replace("none relevant (grepped: cache, evict)", "DEC-999"))
    ok, failures = gate(d, "TICKET-001")
    assert not ok, "one-word digest and unresolvable DEC-999 both passed the gate"
    assert any("Digest" in f for f in failures), failures
    assert any("DEC-999" in f for f in failures), failures
    shutil.rmtree(d)
