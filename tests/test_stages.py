"""A stage is one self-contained file -- and it has to survive being installed."""
import json
import shlex
import sys
from pathlib import Path

from pipeline.core import config as C
from pipeline.core import machine as M


def test_every_stage_prompt_declares_its_config():
    """A stage is one self-contained file: prompt plus model/effort/write."""
    for stage in C.agent_stages():
        cfg = C.stage_config(stage)
        assert cfg.get("model"), f"{stage}: no model in frontmatter"
        assert isinstance(cfg.get("write"), bool), f"{stage}: no write flag"
    assert C.is_readonly("review") and C.is_readonly("plan-validation")
    assert not C.is_readonly("implementing")


def test_composed_prompt_has_common_rules_and_no_frontmatter():
    f = C.compose_prompt("review")
    text = f.read_text()
    f.unlink()
    assert "Failure protocol" in text, "shared rules missing"
    assert "Your stage: review" in text
    assert not text.startswith("---"), "frontmatter leaked into the system prompt"
    assert "model:" not in text.split("## Your stage")[0].split("```")[0]


def test_the_composed_prompt_carries_the_stage_view():
    """The view reaches the agent through the system prompt, not a file
    it has to open. A prompt built without one is the pre-TICKET-023
    behaviour and must stay buildable -- `spawn()` falls back to it."""
    f = C.compose_prompt("review", None, "VIEW-MARKER-9137")
    text = f.read_text()
    f.unlink()
    assert "VIEW-MARKER-9137" in text, "the view never reached the prompt"
    assert "Failure protocol" in text, "the shared rules were displaced"
    g = C.compose_prompt("review")
    plain = g.read_text()
    g.unlink()
    assert "VIEW-MARKER-9137" not in plain and "# The ticket" not in plain


def test_every_stage_named_by_the_state_machine_has_a_prompt():
    # `counters` and `klass` are part of the table, not decoration:
    # `holistic-review` needs a non-bugfix class AND `review_loops > 0` -- it
    # reviews an accumulated diff, so a review that passed first time routes
    # straight to `verifying`. `quick-review` needs `cheap_route` set. Varying
    # `result` alone left both prompts unenforced.
    variants = [({}, "bugfix"), ({}, "refactor"), ({"cheap_route": 1}, "bugfix"),
                ({"review_loops": 1}, "refactor")]
    reachable = {M.transition(s, r, c, k)[0] for s in C.agent_stages()
                 for r in ["ok", "fail", "blocked", "rejected", "chore"]
                 for c, k in variants}
    assert {"quick-review", "holistic-review"} <= reachable, \
        "a variant stopped covering the class- or route-dependent rows"
    for stage in reachable - M.TERMINAL - M.HUMAN_GATES - M.DISPATCHER_STAGES:
        assert (C.STAGES_DIR / f"{stage}.md").is_file(), f"no prompt for `{stage}`"


def test_dispatcher_stages_are_the_ones_with_no_prompt():
    assert M.DISPATCHER_STAGES, "the set is what test_every_stage... subtracts"
    for stage in M.DISPATCHER_STAGES:
        assert stage not in C.agent_stages(), f"{stage} has an agent prompt"
        assert not (C.STAGES_DIR / f"{stage}.md").is_file()


def test_stage_settings_register_the_guard_as_a_pretooluse_hook():
    f = C.stage_settings("implementing", C.stage_config("implementing"))
    data = json.loads(f.read_text()); f.unlink()
    entry = data["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Bash"
    # An interpreter + a script, not a bare path: a shebang would pick up the
    # operator's `python3`, and macOS ships a 3.9 that cannot import the guard.
    argv = shlex.split(entry["hooks"][0]["command"])
    assert argv[0] == sys.executable, argv
    assert argv[1].endswith("dangerous-commands.py")
    assert Path(argv[1]).is_file(), "hook path does not exist"


def test_every_stage_that_can_run_bash_has_the_guard():
    for stage in C.agent_stages():
        assert "dangerous-commands" in (C.stage_config(stage).get("hooks") or []), \
            f"{stage} runs Bash with no guard"


def test_declared_skills_reach_the_prompt_only_when_the_harness_grants_the_tool():
    """Both directions, because the block is only honest in one of them: the
    2026-08-21 run appended it for every harness, and the agent's first turn
    was always `Skill(...)` -> "No such tool available: Skill".

    `compose_prompt()` takes a stage NAME and reads it off disk, so unlike the
    two tests in test_harness.py this one cannot be handed a cfg dict. Since
    2026-08-22 no shipped stage declares `skills:` -- the three that did inlined
    their skill -- so it writes its own stage instead. The leading underscore is
    what keeps it out of `agent_stages()`, which globs `*.md` and skips `_`
    (the same convention that hides `_common.md`); without it, every test that
    enumerates the stages would pick this file up mid-run."""
    fixture = C.STAGES_DIR / "_skillfixture.md"
    fixture.write_text("---\nskills: [demo:some-skill]\n---\n\nfixture body\n")
    try:
        granted = C.compose_prompt("_skillfixture", {"skill_tool": "Skill"})
        text = granted.read_text(); granted.unlink()
        assert "/demo:some-skill" in text

        for hcfg in ({}, None, C.harness("codex")):
            f = C.compose_prompt("_skillfixture", hcfg)
            text = f.read_text(); f.unlink()
            assert "demo:some-skill" not in text, \
                f"{hcfg}: told the agent to invoke a tool the harness cannot give it"
        assert "_skillfixture" not in C.agent_stages(), \
            "the fixture leaked into the stage list"
    finally:
        fixture.unlink()


def test_data_files_live_inside_the_package_so_they_survive_install():
    """Every data path is resolved from `config.PKG`, so it has to live under
    it. This catches a data dir added at the repo root -- which works in a
    checkout and is gone after `uv tool install .`. It does NOT see inside the
    built wheel: an `exclude` in [tool.hatch.build.targets.wheel] would pass
    here and still ship a broken install."""
    for p in (C.STAGES_DIR, C.HOOKS_DIR, C.HARNESSES_DIR, C.TICKET_TEMPLATE,
              C.CONFIG_TEMPLATE):
        assert p.exists(), p
        assert C.PKG in p.parents, f"{p} is outside {C.PKG} -> lost on install"
    assert (C.HOOKS_DIR / "dangerous-commands.py").is_file()


def test_the_docs_name_the_dependencies_and_the_targets_the_code_has():
    """Two rules the review caught asserting something false.

    `CLAUDE.md` claimed two runtime dependencies with `textual` lazy; three are
    declared and `pyte` is imported eagerly (`cli/main` -> `daemon/supervisor`
    -> `pty/host`), so `pipeline approve` fails at import without it. The
    README claimed a stale re-gate bounces to `plan-validation`; `machine.py`
    returns `planning`, with a comment arguing why. A rule file that is wrong
    is worse than no rule file.
    """
    import re
    import tomllib

    root = C.PKG.parent
    deps = tomllib.loads((root / "pyproject.toml").read_text())["project"]["dependencies"]
    names = [re.split(r"[<>=!~ \[]", d)[0] for d in deps]
    claude_md = (root / "CLAUDE.md").read_text().lower()
    for name in names:
        assert name.lower() in claude_md, \
            f"{name} is a runtime dependency no rule mentions"

    readme = (root / "README.md").read_text()
    target = M.transition("revalidating", "fail", {})[0]
    assert target == "planning"
    stale = [ln for ln in readme.splitlines() if "stale_regate" in ln]
    assert stale, "the README stopped documenting the stale re-gate"
    around = readme[readme.index("stale_regate") - 300:readme.index("stale_regate")]
    assert f"`{target}`" in around, around


def test_every_stage_declares_the_effort_its_job_needs():
    """`effort` is per-stage. A stage that declares none drops the flag from the
    spawn command entirely and runs at whatever the harness defaults to."""
    missing = [s for s in C.agent_stages() if not C.stage_config(s).get("effort")]
    assert not missing, f"stages with no effort in frontmatter: {missing}"


def test_effort_values_are_ones_the_harness_accepts():
    """`claude --help`: `--effort <level>  (low, medium, high, xhigh, max)`.
    A typo here is not caught by the declaration test above -- it renders into
    the spawn command verbatim and kills the stage at startup."""
    allowed = {"low", "medium", "high", "xhigh", "max"}
    for stage in C.agent_stages():
        effort = C.stage_config(stage).get("effort")
        assert effort in allowed, f"{stage}: effort {effort!r} not in {sorted(allowed)}"


def test_the_fenced_list_matches_the_rule_file():
    """`CLAUDE.md` names the fenced things in prose and `machine.FENCED` names
    them in code. Two copies that can drift are one promise nobody keeps."""
    import re
    text = (C.PKG.parent / "CLAUDE.md").read_text()
    i = text.index("requires human review before merge")
    sentence = text[text.rindex("\n\n", 0, i):i]
    prose = {tok.rstrip("()") for tok in re.findall(r"`([^`]+)`", sentence)}
    code = {p for p, s in M.FENCED.items() if s is None} | {
        s for syms in M.FENCED.values() if syms for s in syms}
    assert prose == code, f"CLAUDE.md says {prose}, machine.FENCED says {code}"
