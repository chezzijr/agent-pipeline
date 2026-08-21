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
