"""codex.toml is never run -- no codex account -- so it is exercised entirely
by asserting the rendered command string, same as fake.toml is exercised by
running it. This is also what proves the seam: a harness the data model
cannot express (no system-prompt flag, no hooks file) forces exactly the two
changes documented in codex.toml's header comment."""
import re
import tempfile
from pathlib import Path

from pipeline.core import PipelineError, config
from pipeline.daemon import registry, supervisor
from pipeline.daemon.server import Server
from pipeline.daemon.store import Store


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


def test_add_dir_grants_only_the_project_dir_not_the_whole_main_checkout():
    """A stage needs to write exactly two things outside its worktree: the
    ticket file and the `.result` sidecar, both under `<project>/.project/`.
    `--add-dir {project}` instead grants the whole main checkout -- every
    other ticket's file, every other ticket's worktree (worktrees live at
    `<project>/.worktrees/<id>`), and the dispatcher's own source tree."""
    hcfg = config.harness("claude-code")
    stage_cfg = config.stage_config("review")
    prompt = config.compose_prompt("review")
    cmd = config.render(hcfg, stage_cfg, tid="TICKET-001",
                        project=Path("/proj"), ticket=Path("/proj/.project/t.md"),
                        result_file=Path("/proj/.project/t.result"), session="s1",
                        prompt=prompt, settings=Path("/proj/settings.json"))
    prompt.unlink()

    assert "--add-dir /proj/.project " in cmd or "--add-dir /proj/.project --" in cmd, (
        f"--add-dir must grant only the project's .project/ directory, not "
        f"the whole main checkout:\n{cmd}")


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


# Both skill tests below take their stage as a cfg DICT, not a stage name.
# They used to read `implementing` off disk, which was honest only while some
# stage declared `skills:`. Since 2026-08-22 none does -- the three that did
# inlined their skill -- and a fixture read off disk would have made both tests
# assert the same branch twice and pass forever. The machinery is still live
# for a stage that declares a real skill later, so it is still tested; the
# input just no longer depends on what the shipped stages happen to want.
SKILLED = {"skills": ["demo:some-skill"], "write": True}
UNSKILLED = {"write": True}


def test_the_skill_tool_is_granted_only_where_skills_are_declared():
    """A stage's `skills:` used to reach the prompt while `Skill` never
    reached `--tools`, so triage/planning/implementing each opened with
    "No such tool available: Skill". Grant it exactly where it is declared."""
    hcfg = config.harness("claude-code")
    assert hcfg["skill_tool"] == "Skill"

    tools = config._tools(hcfg, SKILLED)
    assert tools.split(",")[-1] == "Skill"
    assert "Skill" not in config._tools(hcfg, UNSKILLED).split(","), \
        "a stage that declares no skills must not get the tool"
    quiet = dict(hcfg); quiet.pop("skill_tool")
    assert "Skill" not in config._tools(quiet, SKILLED).split(","), \
        "a harness that cannot supply the tool must not have it invented for it"


def test_a_stage_with_no_skills_is_spawned_without_the_skill_machinery():
    """The mirror of the test above. A stage that gets no `Skill` tool has no
    use for the 98 slash commands that ship with it either, and they cost
    2,628 tokens of opening context on EVERY turn -- 40 turns, 40 payments.

    The flag is `--disable-slash-commands`, never `--bare`: `--bare` skips
    hooks, and a stage that cannot register the guard is refused outright."""
    hcfg = config.harness("claude-code")
    assert hcfg["no_skills_flag"] == "--disable-slash-commands"

    def cmd(cfg, harness=hcfg):
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        f.write("stage body"); f.close()      # close: mkstemp's fd would leak
        prompt = Path(f.name)
        try:
            return config.render(harness, cfg,
                                 tid="TICKET-001", project=Path("/proj"),
                                 ticket=Path("/proj/t.md"),
                                 result_file=Path("/proj/t.result"),
                                 session="s1", prompt=prompt)
        finally:
            prompt.unlink()

    assert "--disable-slash-commands" in cmd(UNSKILLED), \
        "a stage declaring no skills should shed them"
    assert "--disable-slash-commands" not in cmd(SKILLED), \
        "a stage that USES a skill must keep the tool that invokes it"
    # a harness that declares no such flag must not have one invented for it
    quiet = dict(hcfg); quiet.pop("no_skills_flag")
    assert "--disable-slash-commands" not in cmd(UNSKILLED, quiet)

    # ...and every stage the repo actually ships is now on the shedding side.
    for stage in config.agent_stages():
        assert not config.stage_config(stage).get("skills"), \
            f"{stage} declares skills again -- intended, but see NOTICE first"


def test_a_stage_does_not_inherit_the_operators_plugins():
    """`--setting-sources project` in BOTH templates. Without it a spawn loads
    the operator's whole `~/.claude`: on the machine this was found on, 6
    plugins and two `SessionStart` hooks that put every stage into a persona
    ("You are a lazy senior developer... shortest working diff wins"), which
    `implementing` was then writing merged code under.

    `interactive_cmd` is listed separately because `planning` is the stage that
    uses it, and it is the expensive one to get wrong."""
    hcfg = config.harness("claude-code")
    for key in ("cmd", "interactive_cmd"):
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        f.write("stage body"); f.close()      # close: mkstemp's fd would leak
        prompt = Path(f.name)
        try:
            rendered = config.render(hcfg, UNSKILLED, tid="TICKET-001",
                                     project=Path("/proj"),
                                     ticket=Path("/proj/t.md"),
                                     result_file=Path("/proj/t.result"),
                                     session="s1", prompt=prompt, key=key)
        finally:
            prompt.unlink()
        # the VALUE, not just the prefix: `--setting-sources project,user`
        # contains the substring and reinstates everything the flag exists to
        # drop, so a widening would otherwise pass this test unchanged.
        assert re.search(r"--setting-sources\s+project(\s|$)", rendered), \
            f"{key} inherits the operator's plugins, hooks and skills"


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


def test_a_harness_edit_mid_run_reaches_the_next_spawn():
    """TICKET-028: `run()` reads the harness once, before its loop, so every
    spawn for the life of the process reuses that dict. A stage prompt is
    re-read per spawn; the harness must not be the odd file out."""
    import shutil
    import tempfile

    from helpers import project
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(config.HARNESSES_DIR / "fake.toml", tmp / "fake.toml")
    d = project()
    seen, orig_dir, orig_tick = [], config.HARNESSES_DIR, supervisor.tick

    def fake_tick(proj, hcfg, *a, **kw):
        seen.append(hcfg)
        if len(seen) == 1:      # a harness change lands between two ticks
            p = tmp / "fake.toml"
            p.write_text(p.read_text() + '\nmarker = "TICKET-028"\n')
            return True         # worked -- --once keeps draining
        return False

    config.HARNESSES_DIR = tmp
    supervisor.tick = fake_tick
    try:
        supervisor.run(d, once=True, interval=0, harness_name="fake")
    finally:
        supervisor.tick, config.HARNESSES_DIR = orig_tick, orig_dir

    assert len(seen) == 2, f"expected two ticks, got {len(seen)}"
    assert seen[1].get("marker") == "TICKET-028", \
        "dispatcher spawned with a stale harness: the edit never reached tick 2"


def test_a_harness_edit_mid_run_reaches_the_daemon_loop_too():
    """TICKET-028: `serve()` (the daemon's `run_daemon()`) has the same bug
    as `run()` -- one `hcfg` bound above its loop, reused for every project
    it serves."""
    import shutil
    import tempfile

    from helpers import project
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(config.HARNESSES_DIR / "fake.toml", tmp / "fake.toml")
    d = project()
    seen, orig_dir, orig_tick = [], config.HARNESSES_DIR, supervisor.tick
    store = Store(tmp / "events.db")
    server = Server(store, tmp / "daemon.sock")

    def fake_tick(proj, hcfg, *a, **kw):
        seen.append(hcfg)
        if len(seen) == 1:      # a harness change lands between two ticks
            p = tmp / "fake.toml"
            p.write_text(p.read_text() + '\nmarker = "TICKET-028"\n')
            return True         # worked -- --once keeps draining
        return False

    config.HARNESSES_DIR = tmp
    supervisor.tick = fake_tick
    registry.register(d)
    try:
        supervisor.serve(0, "fake", 1, store, server, once=True)
    finally:
        supervisor.tick, config.HARNESSES_DIR = orig_tick, orig_dir
        registry.unregister(d)

    assert len(seen) == 2, f"expected two ticks, got {len(seen)}"
    assert seen[1].get("marker") == "TICKET-028", \
        "daemon spawned with a stale harness: the edit never reached tick 2"


def test_a_broken_harness_mid_run_keeps_the_last_good_config():
    """A per-tick re-read turns a half-written `.toml` into a runtime fault.
    `run()` calls `tick()` with no `try/except`, so a `_harness_reloader()`
    that re-raises would strand every lease. It must keep the last good
    dict instead."""
    import shutil
    import tempfile

    from helpers import project
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(config.HARNESSES_DIR / "fake.toml", tmp / "fake.toml")
    d = project()
    seen, orig_dir, orig_tick = [], config.HARNESSES_DIR, supervisor.tick

    def fake_tick(proj, hcfg, *a, **kw):
        seen.append(hcfg)
        if len(seen) == 1:
            (tmp / "fake.toml").write_text("not toml = [[[")
            return True
        return False

    config.HARNESSES_DIR = tmp
    supervisor.tick = fake_tick
    try:
        supervisor.run(d, once=True, interval=0, harness_name="fake")
    finally:
        supervisor.tick, config.HARNESSES_DIR = orig_tick, orig_dir

    assert len(seen) == 2, f"expected two ticks, got {len(seen)}"
    assert seen[1] == seen[0], \
        "a broken harness reload must keep the last good config, not " \
        "propagate the parse error"


def test_an_unknown_harness_still_fails_before_the_loop_starts():
    """The first read stays unguarded: `pipeline run --harness nope` must
    still die with `no harness config ...`, not hang or silently no-op."""
    from helpers import project
    d = project()
    try:
        supervisor.run(d, once=True, interval=0, harness_name="nope")
        assert False, "an unknown harness should have raised before the loop"
    except PipelineError as e:
        assert "no harness config" in str(e)
