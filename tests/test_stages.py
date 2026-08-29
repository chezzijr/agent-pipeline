"""A stage is one self-contained file -- and it has to survive being installed."""
import json
import re
import shlex
import sys
import tempfile
from pathlib import Path

from pipeline.core import config as C
from pipeline.core import machine as M
from pipeline.core import PipelineError


def test_every_stage_prompt_declares_its_config():
    """A stage is one self-contained file: prompt plus model/effort/write."""
    for stage in C.agent_stages():
        cfg = C.stage_config(stage)
        assert cfg.get("model"), f"{stage}: no model in frontmatter"
        assert isinstance(cfg.get("write"), bool), f"{stage}: no write flag"
    assert C.is_readonly("review") and C.is_readonly("plan-validation")
    assert not C.is_readonly("implementing")


def test_plan_validation_can_mark_an_item_unverified():
    """plan-validation is read-only: the guard blocks every `$(...)` probe it
    might try, so the prompt must give it a way to flag a finding it could
    not measure, distinct from a scored fail. It must also know about
    `[readonly] allow` in .project/pipeline.toml, the supported way to ask
    for a specific read-only command."""
    text = (C.STAGES_DIR / "plan-validation.md").read_text()
    assert "unverified" in text.lower(), \
        "plan-validation has no channel for an item it could not measure"
    assert "[readonly] allow" in text, \
        "plan-validation is never told about the per-project readonly allowlist"


def test_composed_prompt_has_common_rules_and_no_frontmatter():
    f = C.compose_prompt("review")
    text = f.read_text()
    f.unlink()
    assert "Failure protocol" in text, "shared rules missing"
    assert "Your stage: review" in text
    assert not text.startswith("---"), "frontmatter leaked into the system prompt"
    assert "model:" not in text.split("## Your stage")[0].split("```")[0]


def test_common_rules_say_where_a_code_edit_goes():
    f = C.compose_prompt("review")
    text = f.read_text()
    f.unlink()
    assert "Every file you edit goes in your working directory" in text
    assert "the ticket file and the result file" in text


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


def test_an_interactive_prompt_reverses_the_sidecar_ordering():
    default = C.compose_prompt("planning").read_text()
    assert "before you append your" in default
    assert "runs on a terminal" not in default

    inter = C.compose_prompt("planning", None, "", None, interactive=True).read_text()
    assert "Write the result file LAST" in inter


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
    assert entry["matcher"] == "Bash|Write|Edit|MultiEdit|NotebookEdit|mcp__.*"
    for tool in ("Bash", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        assert re.fullmatch(entry["matcher"], tool), tool
    # An interpreter + a script, not a bare path: a shebang would pick up the
    # operator's `python3`, and macOS ships a 3.9 that cannot import the guard.
    argv = shlex.split(entry["hooks"][0]["command"])
    assert argv[0] == sys.executable, argv
    assert argv[1].endswith("dangerous-commands.py")
    assert Path(argv[1]).is_file(), "hook path does not exist"


def test_guard_matcher_covers_mcp_tool_calls():
    """TICKET-036: an MCP tool is named `mcp__<server>__<tool>` and the
    guard is registered with a regex over the tool name, so an MCP tool call
    must match it or it never reaches `dangerous-commands.py` and is not
    refused either -- it just runs. The matcher must cover both or an MCP
    server is an unguarded path around invariant 4."""
    f = C.stage_settings("implementing", C.stage_config("implementing"))
    data = json.loads(f.read_text()); f.unlink()
    matcher = data["hooks"]["PreToolUse"][0]["matcher"]
    assert re.fullmatch(matcher, "mcp__github__create_pr"), \
        f"matcher {matcher!r} does not cover MCP tool calls"


def test_a_stage_only_gets_the_mcp_servers_it_declares():
    d = Path(tempfile.mkdtemp())
    (d / ".project").mkdir(parents=True)
    (d / ".project" / "pipeline.toml").write_text(
        '[mcp.docs]\ncommand = "docs-mcp"\nreadonly = true\n'
        '[mcp.github]\ncommand = "gh-mcp"\n')
    assert C.mcp_servers(d, {}) == {}
    got = C.mcp_servers(d, {"mcp": ["docs"]})
    assert set(got) == {"docs"}
    assert got["docs"]["readonly"] is True
    f = C.mcp_config(got)
    assert json.loads(f.read_text()) == {"mcpServers": {"docs": {"command": "docs-mcp"}}}
    f.unlink()
    assert C.mcp_config({}) is None


def test_a_project_names_the_commands_a_read_only_stage_may_run():
    d = Path(tempfile.mkdtemp())
    (d / ".project").mkdir(parents=True)
    cfg = d / ".project" / "pipeline.toml"
    cfg.write_text('[readonly]\nallow = ["pipeline ls", "./run tests"]\n')
    assert C.readonly_allow(d) == [["pipeline", "ls"], ["./run", "tests"]]

    cfg.write_text('test_one = "pytest"\n')
    assert C.readonly_allow(d) == []

    assert C.readonly_allow(Path(tempfile.mkdtemp())) == []

    for bad in ('allow = "pipeline ls"\n', 'allow = [""]\n', 'allow = [3]\n'):
        cfg.write_text("[readonly]\n" + bad)
        try:
            C.readonly_allow(d)
            assert False, f"{bad!r} must raise"
        except PipelineError:
            pass
    cfg.write_text("readonly = 3\n")
    try:
        C.readonly_allow(d)
        assert False, "readonly = 3 must raise"
    except PipelineError:
        pass


def test_an_mcp_server_a_stage_did_not_declare_is_refused():
    d = Path(tempfile.mkdtemp())
    (d / ".project").mkdir(parents=True)
    (d / ".project" / "pipeline.toml").write_text(
        '[mcp.docs]\ncommand = "docs-mcp"\n')
    try:
        C.mcp_servers(d, {"mcp": ["gitlab"]})
        assert False, "an undeclared server must raise"
    except PipelineError:
        pass
    try:
        C.mcp_servers(d, {"mcp": ["ev__il"]})
        assert False, "a server name with __ must raise"
    except PipelineError:
        pass


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
              C.CONFIG_TEMPLATE, C.SKILL_TEMPLATE):
        assert p.exists(), p
        assert C.PKG in p.parents, f"{p} is outside {C.PKG} -> lost on install"
    assert (C.HOOKS_DIR / "dangerous-commands.py").is_file()


def test_the_repo_skill_is_the_packaged_file():
    """One copy of the skill's bytes, and the harness still loads it.

    `.claude/skills/file-ticket/SKILL.md` is a symlink to the packaged
    copy, so the two cannot drift. Claude Code 2.1.241 loads a symlinked
    SKILL.md: its project-skills loader `stat`s the path -- not `lstat`,
    which it uses elsewhere -- and skips the skill only when the target
    is not a regular file, or is over its byte limit. These asserts are
    that loader's conditions. Replacing the link with a copy fails here.
    """
    from helpers import ROOT
    packaged = sorted(p.name for p in C.SKILLS_DIR.iterdir())
    assert "file-ticket" in packaged and "pipeline-config" in packaged, packaged
    for name in packaged:
        repo = ROOT / ".claude" / "skills" / name / "SKILL.md"
        assert repo.is_symlink(), \
            f"{repo} is a copy, not a symlink -- the two copies will drift"
        assert repo.is_file(), \
            f"{repo} is a broken symlink -- the skill would not load"
        assert repo.resolve() == (C.SKILLS_DIR / name / "SKILL.md").resolve(), \
            f"{repo} resolves to {repo.resolve()}, not to the packaged copy"
        assert repo.stat().st_size < 128 * 1024, \
            f"{repo} is {repo.stat().st_size} bytes -- too large to load"


def test_the_docs_name_the_skill_init_installs():
    """`init` installs the file-ticket skill, so both rule files say so.

    `CLAUDE.md`'s "Where things live" row for `pipeline/templates/` and
    the README's copy of that row describe one directory. A reader who
    finds only the schema and the config example there does not learn
    that the skill ships too, and `## Use` is where a human reads what
    `init` writes.
    """
    root = C.PKG.parent
    for name in ("CLAUDE.md", "README.md"):
        rows = [ln for ln in (root / name).read_text().splitlines()
                if "pipeline/templates/" in ln and "file-ticket" in ln]
        assert rows, \
            f"{name}: the pipeline/templates/ row does not name the file-ticket skill"
    readme = (root / "README.md").read_text()
    assert "installs `.claude/skills/file-ticket/SKILL.md`" in readme, \
        "README.md does not say `init` installs the file-ticket skill"


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


def test_the_rule_file_documents_the_pty_log_geometry_marker():
    """The marker number comes from `geom_marker()`, so the rule file
    cannot drift from the bytes it names."""
    from pipeline.pty import host
    num = host.geom_marker(40, 120).decode("latin-1").split(";")[0].lstrip("\x1b]")
    text = (C.PKG.parent / "CLAUDE.md").read_text()
    hits = [" ".join(b.split()) for b in text.split("\n- ") if num in b]
    assert len(hits) == 1, f"no CLAUDE.md bullet names the {num} geometry marker"
    for claim in ("resize", "batch log", "render_pty"):
        assert claim in hits[0], claim


def test_the_rule_file_counts_the_guard_cases():
    """`CLAUDE.md`'s Commands block names how many cases the guard's tables
    hold. TICKET-057 moved that number twice, so count them instead of
    trusting a hand count."""
    import importlib.util
    path = C.PKG / "hooks" / "test_dangerous_commands.py"
    spec = importlib.util.spec_from_file_location("guard_tables", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cases = sum(len(t) for t in (mod.BLOCKED_ALWAYS, mod.ALLOWED_ALWAYS,
                                 mod.BLOCKED_READONLY, mod.ALLOWED_READONLY,
                                 mod.MCP_BLOCKED, mod.MCP_ALLOWED,
                                 mod.ALLOWED_PROJECT, mod.BLOCKED_PROJECT))
    text = (C.PKG.parent / "CLAUDE.md").read_text()
    claimed = re.findall(r"# (\d+) guard cases \(table-driven\)", text)
    assert claimed == [str(cases)], f"CLAUDE.md says {claimed}, tables hold {cases}"


def test_the_config_docs_name_every_test_placeholder():
    """`{path}` and `{name}` are part of the config interface (TICKET-067).
    These two files are what a project reads before writing its three
    commands; one that still documents `{test}` alone sends every non-pytest
    project back to re-deriving the split in shell."""
    skill = C.SKILLS_DIR / "pipeline-config" / "SKILL.md"
    for p in (C.CONFIG_TEMPLATE, skill):
        text = p.read_text()
        assert "{path}" in text and "{name}" in text, p
        assert "sed 's/.*:://'" not in text, f"{p} still splits the test id in shell"


def test_the_config_skill_names_every_knob_the_code_reads():
    """TICKET-084: `max_usd`, `scale_usd`, `worktree_setup`, the
    `.project/stages/<name>.extra.md` prose append, and `pinned` are all
    knobs the pipeline reads, but landed in the code across 2026-08-27
    without a matching update to the skill a session reads before writing
    `.project/pipeline.toml`."""
    skill = C.SKILLS_DIR / "pipeline-config" / "SKILL.md"
    text = skill.read_text()
    for knob in ("max_usd", "scale_usd", "worktree_setup", "worktree_teardown",
                 "extra.md", "pinned"):
        assert knob in text, f"{skill} does not mention {knob!r}"


def test_the_config_template_documents_worktree_setup():
    """TICKET-084: the skill delegates the keys it does not spell out
    to the comments of `.project/pipeline.toml`. `worktree_setup` was
    in neither file, so a session had no route to it at all."""
    text = C.CONFIG_TEMPLATE.read_text()
    assert "worktree_setup" in text, (
        f"{C.CONFIG_TEMPLATE} does not document worktree_setup")
    assert "worktree_teardown" in text, (
        f"{C.CONFIG_TEMPLATE} does not document worktree_teardown")


def test_stage_config_can_take_a_per_project_override(tmp_path):
    """TICKET-038: `stage_config()` resolves against the packaged stage only,
    with no way for a project to add a model, tool or skill of its own. A
    project that wants `review` to run on a different model has nowhere to
    say so."""
    project = tmp_path / "proj"
    (project / ".project").mkdir(parents=True)
    (project / ".project" / "pipeline.toml").write_text(
        '[stages.review]\nmodel = "haiku"\n')
    cfg = C.stage_config("review", project=project)
    assert cfg["model"] == "haiku"


def test_a_project_override_merges_onto_the_packaged_frontmatter(tmp_path):
    """The merge is shallow and additive per key: a project that sets `model`
    and `write` does not lose the packaged `effort` or `hooks`, and a project
    with no config file at all yields the packaged stage untouched."""
    project = tmp_path / "proj"
    (project / ".project").mkdir(parents=True)
    (project / ".project" / "pipeline.toml").write_text(
        '[stages.review]\nmodel = "haiku"\nwrite = true\n')
    packaged = C.stage_config("review")
    cfg = C.stage_config("review", project=project)
    assert cfg["effort"] == packaged["effort"]
    assert cfg["hooks"] == packaged["hooks"]
    assert C.is_readonly("review") is True
    assert C.is_readonly("review", project) is False
    assert C.stage_config("review", project=tmp_path / "nothing")["model"] == packaged["model"]


def test_a_project_appends_prose_to_a_stage_prompt(tmp_path):
    """A project's `.project/stages/<stage>.extra.md` lands after the packaged
    prompt and before the ticket view -- an addition, never a replacement."""
    project = tmp_path / "proj"
    stages_dir = project / ".project" / "stages"
    stages_dir.mkdir(parents=True)
    extra = stages_dir / "review.extra.md"
    extra.write_text("## This project's rule\n\n- EXTRA-MARKER-4471\n")
    try:
        path = C.compose_prompt("review", None, "VIEW-MARKER-9137", project)
        text = path.read_text()
        assert text.index("Your stage: review") < text.index("EXTRA-MARKER-4471") \
            < text.index("VIEW-MARKER-9137")

        path = C.compose_prompt("review", None, "VIEW-MARKER-9137")
        assert "EXTRA-MARKER-4471" not in path.read_text()
    finally:
        extra.unlink()
