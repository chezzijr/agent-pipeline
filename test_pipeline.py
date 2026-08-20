#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Checks for the parts that silently rot: the transition table's bounds and
the Tier A gate. Run: ./test_pipeline.py"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pipeline as P

HERE = Path(__file__).parent


def t(stage, result, counters=None, klass="bugfix"):
    return P.transition(stage, result, counters or {}, klass)


def test_happy_path():
    assert t("new", "-")[0] == "triage"
    assert t("triage", "ok")[0] == "planning"
    assert t("planning", "ok")[0] == "plan-validation"
    assert t("plan-validation", "ok")[0] == "awaiting-approval"
    assert t("implementing", "ok")[0] == "review"
    assert t("review", "ok", klass="bugfix")[0] == "verifying", "bugfix skips holistic"
    assert t("review", "ok", klass="refactor")[0] == "holistic-review"
    assert t("holistic-review", "ok")[0] == "verifying"
    assert t("verifying", "ok")[0] == "done"
    assert t("triage", "rejected")[0] == "rejected"


def test_bounds_escalate_on_the_second_failure():
    for stage, result, key in [
        ("plan-validation", "fail", "plan_validation_attempts"),
        ("review", "fail", "review_loops"),
        ("holistic-review", "fail", "review_loops"),
        ("verifying", "fail", "review_loops"),
        ("implementing", "blocked", "blocked_count"),
    ]:
        nxt, c = t(stage, result)
        assert nxt != "escalated", f"{stage}: first {result} must retry, got {nxt}"
        assert c[key] == 1, f"{stage}: counter not charged"
        nxt, c = t(stage, result, c)
        assert nxt == "escalated", f"{stage}: second {result} must escalate, got {nxt}"
        assert c[key] == 2


def test_review_loops_are_a_shared_budget():
    """A review fail then a holistic fail must escalate -- not reset per stage."""
    _, c = t("review", "fail")
    assert t("holistic-review", "fail", c)[0] == "escalated"


def test_transition_is_pure():
    c = {"review_loops": 0}
    t("review", "fail", c)
    assert c == {"review_loops": 0}, "transition mutated its input"


def test_unknown_result_escalates_rather_than_guesses():
    assert t("review", "lgtm!")[0] == "escalated"
    assert t("implementing", "")[0] == "escalated"


def test_no_agent_can_reach_a_human_gate_or_a_terminal_state():
    reachable = {t(s, r)[0] for s in P.agent_stages() for r in
                 ["ok", "fail", "blocked", "rejected", "junk"]}
    assert "awaiting-approval" not in {t(s, r)[0] for s in P.agent_stages() if s != "plan-validation"
                                       for r in ["ok", "fail", "blocked", "rejected"]}
    assert "done" not in reachable, "an agent stage must never reach `done`"


# --- gate ------------------------------------------------------------------

FIXTURE = """---
id: TICKET-001
stage: plan-validation
class: bugfix
branch: ticket/001
test_file: test_thing.py::test_broken
files_declared: [thing.py]
counters: {}
lease: {holder: null, expires: null}
---

## Summary
x
## Reproduction
fails
## Digest
thing.py holds it
## Decisions checked
none relevant (grepped: cache, evict)
## Plan
1. fix thing.py
## Acceptance criteria
- `test_broken` passes
## Rollback
revert
## Thread
"""


def _project(ticket_text=FIXTURE, test_passes=False):
    d = Path(tempfile.mkdtemp())
    (d / ".project" / "tickets").mkdir(parents=True)
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo test_broken; exit %d"\n'
        'test_suite = "true"\n'
        'test_suite_without_new = "true"\n' % (0 if test_passes else 1))
    (d / ".project" / "tickets" / "TICKET-001.md").write_text(ticket_text)
    (d / "test_thing.py").write_text("")
    return d


def test_gate_passes_a_complete_ticket():
    d = _project()
    ok, failures = P.gate(d, "TICKET-001")
    assert ok, failures
    assert "Tier A gate: PASS" in (d / ".project/tickets/TICKET-001.md").read_text()
    shutil.rmtree(d)


def test_gate_blocks_an_empty_digest():
    d = _project(FIXTURE.replace("## Digest\nthing.py holds it\n", "## Digest\n"))
    ok, failures = P.gate(d, "TICKET-001")
    assert not ok and any("Digest" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_blocks_a_test_that_already_passes():
    d = _project(test_passes=True)
    ok, failures = P.gate(d, "TICKET-001")
    assert not ok and any("PASSES" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_blocks_a_test_that_errors_instead_of_failing():
    """A missing dependency exits non-zero exactly like a real failure."""
    d = _project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo ModuleNotFoundError: no module named pytest; exit 1"\n'
        'test_suite = "true"\ntest_suite_without_new = "true"\n')
    ok, failures = P.gate(d, "TICKET-001")
    assert not ok and any("errored rather than failed" in f for f in failures), failures
    shutil.rmtree(d)


def test_project_commands_do_not_inherit_the_dispatchers_venv():
    env = P.project_env()
    assert "VIRTUAL_ENV" not in env
    assert not any("uv/environments" in d for d in env["PATH"].split(":")), env["PATH"]


def test_gate_blocks_empty_files_declared():
    d = _project(FIXTURE.replace("files_declared: [thing.py]", "files_declared: []"))
    ok, failures = P.gate(d, "TICKET-001")
    assert not ok and any("files_declared" in f for f in failures), failures
    shutil.rmtree(d)


def test_gate_blocks_a_vacuous_acceptance_criterion():
    d = _project(FIXTURE.replace("- `test_broken` passes", "- code should be clean"))
    ok, failures = P.gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures
    shutil.rmtree(d)


def test_escalation_clears_the_lease_so_a_human_can_resume():
    d = _project()
    path = d / ".project/tickets/TICKET-001.md"
    meta, body = P.load_ticket(path)
    meta["lease"] = {"holder": "x", "expires": "2999-01-01T00:00:00+00:00"}
    P.save_ticket(path, meta, body)
    meta, body = P.load_ticket(path)
    P.escalate(path, meta, body, "test")
    meta, _ = P.load_ticket(path)
    assert meta["stage"] == "escalated"
    assert not P.lease_active(meta), "a leased escalated ticket cannot be resumed"
    shutil.rmtree(d)


def test_every_stage_prompt_declares_its_config():
    """A stage is one self-contained file: prompt plus model/effort/write."""
    for stage in P.agent_stages():
        cfg = P.stage_config(stage)
        assert cfg.get("model"), f"{stage}: no model in frontmatter"
        assert isinstance(cfg.get("write"), bool), f"{stage}: no write flag"
    assert P.is_readonly("review") and P.is_readonly("plan-validation")
    assert not P.is_readonly("implementing")


def test_composed_prompt_has_common_rules_and_no_frontmatter():
    f = P.compose_prompt("review")
    text = f.read_text()
    f.unlink()
    assert "Failure protocol" in text, "shared rules missing"
    assert "Your stage: review" in text
    assert not text.startswith("---"), "frontmatter leaked into the system prompt"
    assert "model:" not in text.split("## Your stage")[0].split("```")[0]


def test_every_stage_named_by_the_state_machine_has_a_prompt():
    reachable = {t(s, r)[0] for s in P.agent_stages()
                 for r in ["ok", "fail", "blocked", "rejected"]}
    for stage in reachable - P.TERMINAL - {"awaiting-approval", "verifying"}:
        assert (P.STAGES_DIR / f"{stage}.md").is_file(), f"no prompt for `{stage}`"


def test_ticket_roundtrips():
    d = _project()
    p = d / ".project/tickets/TICKET-001.md"
    meta, body = P.load_ticket(p)
    P.save_ticket(p, meta, body)
    assert P.load_ticket(p)[0] == meta
    assert P.sections(body)["Digest"] == "thing.py holds it"
    shutil.rmtree(d)


def test_cli_new_then_status():
    d = Path(tempfile.mkdtemp())
    run = lambda *a: subprocess.run([sys.executable, str(HERE / "pipeline.py"),
                                     "--project", str(d), *a],
                                    capture_output=True, text=True)
    r = run("new", "cache leaks", "--class", "bugfix")
    assert r.returncode == 0, r.stderr
    assert (d / ".project/tickets/TICKET-001.md").is_file()
    r = run("status")
    assert "TICKET-001" in r.stdout and "new" in r.stdout, r.stdout
    r = run("approve", "TICKET-001")
    assert r.returncode != 0, "approve must refuse a ticket that is not awaiting-approval"
    shutil.rmtree(d)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
