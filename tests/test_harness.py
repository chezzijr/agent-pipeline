"""codex.toml is never run -- no codex account -- so it is exercised entirely
by asserting the rendered command string, same as fake.toml is exercised by
running it. This is also what proves the seam: a harness the data model
cannot express (no system-prompt flag, no hooks file) forces exactly the two
changes documented in codex.toml's header comment."""
from pathlib import Path

from pipeline.core import PipelineError, config
from pipeline.daemon import supervisor


def test_codex_cannot_register_hooks_so_a_guarded_stage_is_refused():
    """Every stage file in this repo declares `hooks: [dangerous-commands]`.
    supports_hooks = false means spawn() must refuse rather than run the
    stage with only the tree-snapshot backstop -- detection, not prevention."""
    assert config.stage_config("implementing").get("hooks"), \
        "fixture assumption broken: `implementing` no longer declares hooks"
    cfg = config.harness("codex")
    try:
        supervisor.spawn(Path("/nonexistent-project"), Path("/nonexistent-wt"),
                         "TICKET-001", "implementing", cfg)
        assert False, "ran a guarded stage on a harness that cannot register hooks"
    except PipelineError as e:
        assert "hooks" in str(e)


def test_the_guard_is_per_harness_not_global():
    """claude-code registers hooks via --settings, so the same guarded stage
    that codex refuses must not be blocked for claude-code."""
    assert config.harness("claude-code")["supports_hooks"] is True
    assert config.harness("codex")["supports_hooks"] is False


def test_codex_renders_inline_prompt_with_no_system_prompt_or_settings_flag():
    """codex has no --append-system-prompt: prompt_mode = "inline" must fold
    the composed prompt into the positional PROMPT argument instead."""
    hcfg = config.harness("codex")
    stage_cfg = config.stage_config("review")   # write: false -- no hooks check here
    prompt = config.compose_prompt("review")
    cmd = config.render(hcfg, stage_cfg, tid="TICKET-001",
                        project=Path("/proj"), ticket=Path("/proj/t.md"),
                        result_file=Path("/proj/t.result"), session="s1",
                        prompt=prompt, settings=None)
    prompt.unlink()

    assert "--append-system-prompt" not in cmd
    assert "--settings" not in cmd
    assert "codex exec" in cmd
    assert "Your stage: review" in cmd, "composed prompt was not folded into the positional prompt"
    assert "Work ticket TICKET-001" in cmd, "the work-ticket message must survive inline mode too"


def test_claude_code_render_is_unchanged_by_the_extraction():
    """render() is a pure extraction of spawn()'s old inline .format() call --
    prompt_mode defaults to "system", so claude-code's command must look
    exactly as it did before the extraction."""
    hcfg = config.harness("claude-code")
    stage_cfg = config.stage_config("review")
    prompt = config.compose_prompt("review")
    cmd = config.render(hcfg, stage_cfg, tid="TICKET-001",
                        project=Path("/proj"), ticket=Path("/proj/t.md"),
                        result_file=Path("/proj/t.result"), session="s1",
                        prompt=prompt, settings=Path("/proj/settings.json"))
    prompt.unlink()

    assert "--append-system-prompt" in cmd
    assert "--settings /proj/settings.json" in cmd
    assert "claude -p" in cmd


def test_the_prompt_survives_a_variadic_flag():
    """`--add-dir` is variadic: `--add-dir /p "prompt"` eats the prompt as a
    second directory and claude exits with "Input must be provided either
    through stdin or as a prompt argument". Every stage this harness spawned
    died there. Nothing caught it because the end-to-end tests use `fake.toml`,
    whose command has no positional argument at all -- so the one harness that
    talks to a real agent was the one harness never exercised.

    The `--` is what ends option parsing. Assert it separates the last flag
    from the prompt in every command template that carries a positional.
    """
    hcfg = config.harness("claude-code")
    for key in ("cmd", "interactive_cmd"):
        tpl = hcfg.get(key)
        if not tpl:
            continue
        # the prompt is the trailing quoted positional
        head, sep, prompt = tpl.rpartition('"Work ticket')
        assert sep, f"{key}: no positional prompt found"
        assert head.rstrip().rstrip("\\").rstrip().endswith("--"), (
            f"{key}: the prompt is not separated from the flags by `--`, so a "
            f"variadic flag will swallow it:\n...{head[-60:]!r}")


def test_the_work_message_points_at_the_view_not_the_whole_ticket():
    """The saving is lost the moment the agent is told to read the file.
    Both claude-code templates and render()'s inline message carry their
    own copy of that sentence, so both are checked."""
    hcfg = config.harness("claude-code")
    for key in ("cmd", "interactive_cmd"):
        tpl = hcfg[key]
        assert "Read {ticket} first" not in tpl, f"{key}: orders a full read"
        assert "bounded view" in tpl, f"{key}: does not name the view"
        assert "{ticket}" in tpl, f"{key}: the agent must still write there"
    prompt = config.compose_prompt("review")
    cmd = config.render(config.harness("codex"),
                        config.stage_config("review"), tid="TICKET-001",
                        project=Path("/proj"), ticket=Path("/proj/t.md"),
                        result_file=Path("/proj/t.result"), session="s",
                        prompt=prompt)
    prompt.unlink()
    assert "Work ticket TICKET-001" in cmd
    assert "Read /proj/t.md first" not in cmd
    assert "bounded view" in cmd


def test_headless_stages_get_the_harness_permission_mode_not_a_prompt():
    """`acceptEdits` auto-accepts file edits and nothing else, so under `-p`
    every Bash command fell through to an approval prompt with nobody to
    answer it -- `This command requires approval` on `uv run pytest`, on
    `git add`, on everything triage exists to do. The harness now carries the
    default, so the fallback chain is: stage frontmatter, then harness, then
    the old value for a harness that says nothing."""
    hcfg = config.harness("claude-code")
    assert hcfg["permission_mode"] == "bypassPermissions"

    def rendered(stage_cfg, h=hcfg, key="cmd"):
        prompt = config.compose_prompt("review", h)
        cmd = config.render(h, stage_cfg, tid="TICKET-001", project=Path("/proj"),
                            ticket=Path("/proj/t.md"),
                            result_file=Path("/proj/t.result"), session="s1",
                            prompt=prompt, settings=Path("/proj/s.json"), key=key)
        prompt.unlink()
        return cmd

    assert "--permission-mode bypassPermissions" in rendered(
        config.stage_config("review")), "the harness default did not reach the command"
    assert "--permission-mode plan" in rendered({"model": "opus", "permission_mode": "plan"}), \
        "a stage can no longer override the harness"
    quiet = dict(hcfg); quiet.pop("permission_mode")
    assert "--permission-mode acceptEdits" in rendered({"model": "opus"}, quiet), \
        "a harness that declares nothing must keep the pre-fix value"


def test_the_skill_tool_is_granted_only_where_skills_are_declared():
    """A stage's `skills:` used to reach the prompt while `Skill` never
    reached `--tools`, so triage/planning/implementing each opened with
    "No such tool available: Skill". Grant it exactly where it is declared."""
    hcfg = config.harness("claude-code")
    assert hcfg["skill_tool"] == "Skill"
    assert config.stage_config("implementing").get("skills"), \
        "fixture assumption broken: `implementing` no longer declares skills"
    assert not config.stage_config("review").get("skills")

    tools = config._tools(hcfg, config.stage_config("implementing"))
    assert tools.split(",")[-1] == "Skill"
    assert "Skill" not in config._tools(hcfg, config.stage_config("review")).split(","), \
        "a stage that declares no skills must not get the tool"
    quiet = dict(hcfg); quiet.pop("skill_tool")
    assert "Skill" not in config._tools(quiet, config.stage_config("implementing")).split(","), \
        "a harness that cannot supply the tool must not have it invented for it"


def test_an_interactive_stage_keeps_the_mode_that_can_ask():
    """`bypassPermissions` on a real terminal opens a modal before the session
    starts, and a stage parked on "Yes, I accept" is a stage nobody is
    steering -- TICKET-016's planning run sat there until it was killed. The
    interactive template is the one place a prompt CAN be answered, so it takes
    the opposite default from the headless one."""
    hcfg = config.harness("claude-code")
    stage_cfg = config.stage_config("planning")
    assert stage_cfg.get("mode") == "interactive", \
        "fixture assumption broken: `planning` is no longer interactive"

    def rendered(key):
        prompt = config.compose_prompt("planning", hcfg)
        cmd = config.render(hcfg, stage_cfg, tid="TICKET-001", project=Path("/proj"),
                            ticket=Path("/proj/t.md"),
                            result_file=Path("/proj/t.result"), session="s1",
                            prompt=prompt, settings=Path("/proj/s.json"), key=key)
        prompt.unlink()
        return cmd

    assert "--permission-mode acceptEdits" in rendered("interactive_cmd")
    assert "--permission-mode bypassPermissions" in rendered("cmd"), \
        "the same stage run headless still must not wait for an approval"


def test_every_stage_can_write_its_result_sidecar():
    """`write: false` names the working tree, not the ticket: `tree_snapshot()`
    excludes `.project/` precisely so a read-only stage can write its `.result`.
    Given only Bash it cannot -- the guard refuses `>`, heredocs and `sed -i` --
    so two `plan-validation` runs produced complete analyses, had nowhere to put
    them, and escalated with `no_result: 2`. Every stage needs a file tool."""
    hcfg = config.harness("claude-code")
    for stage in config.agent_stages():
        tools = config._tools(hcfg, config.stage_config(stage)).split(",")
        assert {"Write", "Edit"} & set(tools), \
            f"{stage} has no file tool, so it cannot write its .result: {tools}"


def test_a_stage_does_not_inherit_the_developers_mcp_servers():
    """`--tools` restricts built-in tools only. Every MCP server configured in
    the developer's `~/.claude` still loads, so TICKET-024's `planning` asked
    for `Read,Grep,Glob,Bash,Edit,Write,Skill` and the `init` event of the
    session it got granted 53 tools from 9 servers, among them
    `mcp__claude_ai_Gmail__apply_sensitive_message_label`. The guard registers
    `PreToolUse` with `matcher: "Bash"`, so it has nothing to say about any of
    them, and the same ticket runs differently on two machines.

    `--strict-mcp-config` limits a session to the servers named by
    `--mcp-config`, i.e. none. Both templates carry `--tools`, so both need it."""
    hcfg = config.harness("claude-code")
    for key in ("cmd", "interactive_cmd"):
        assert "--strict-mcp-config" in hcfg[key], \
            f"claude-code {key} lets ~/.claude MCP servers into the session"
