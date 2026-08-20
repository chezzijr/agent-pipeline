"""Tier A gate: the checks that must not be talkable-out-of."""
import shutil

from helpers import FIXTURE, project
from pipeline.core import ticket as T
from pipeline.core.gate import gate


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


def test_shell_injection_through_test_file_is_dead():
    """The gate runs the project's test command; test_file comes from an agent."""
    d = project()
    marker = d / "PWNED"
    path = d / ".project/tickets/TICKET-001.md"
    meta, body = T.load_ticket(path)
    meta["test_file"] = f"test_thing.py::test_x; touch {marker}"
    T.save_ticket(path, meta, body)
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo {test}"\ntest_suite = "true"\n'
        'test_suite_without_new = "echo {test}"\n')
    assert T.validate_meta(meta), "validation must reject it before anything runs"
    gate(d, "TICKET-001")
    assert not marker.exists(), "command substitution executed"
    shutil.rmtree(d)
