"""A stage is one self-contained file -- and it has to survive being installed."""
import json
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


def test_every_stage_named_by_the_state_machine_has_a_prompt():
    reachable = {M.transition(s, r, {})[0] for s in C.agent_stages()
                 for r in ["ok", "fail", "blocked", "rejected"]}
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
    assert entry["hooks"][0]["command"].endswith("dangerous-commands.py")
    assert Path(entry["hooks"][0]["command"]).is_file(), "hook path does not exist"


def test_every_stage_that_can_run_bash_has_the_guard():
    for stage in C.agent_stages():
        assert "dangerous-commands" in (C.stage_config(stage).get("hooks") or []), \
            f"{stage} runs Bash with no guard"


def test_declared_skills_reach_the_prompt_only_when_the_harness_grants_the_tool():
    """Both directions, because the block is only honest in one of them: the
    2026-08-21 run appended it for every harness, and the agent's first turn
    was always `Skill(...)` -> "No such tool available: Skill"."""
    granted = C.compose_prompt("implementing", {"skill_tool": "Skill"})
    text = granted.read_text(); granted.unlink()
    assert "/superpowers:test-driven-development" in text

    for hcfg in ({}, None, C.harness("codex")):
        f = C.compose_prompt("implementing", hcfg)
        text = f.read_text(); f.unlink()
        assert "superpowers:test-driven-development" not in text, \
            f"{hcfg}: told the agent to invoke a tool the harness cannot give it"


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
