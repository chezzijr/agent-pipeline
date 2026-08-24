"""Where the data files live and what a stage or a project asks for.

The stage prompts, hooks, harnesses and templates sit INSIDE the package:
located from the repo root they are simply gone after `uv tool install .`.
"""
import json
import re
import shlex
import sys
import tempfile
import tomllib
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.core.ticket import split_frontmatter
from pipeline.core.worktree import head_file

PKG = Path(__file__).resolve().parent.parent
STAGES_DIR = PKG / "stages"
HOOKS_DIR = PKG / "hooks"
HARNESSES_DIR = PKG / "harnesses"
TICKET_TEMPLATE = PKG / "templates" / "ticket.md"
CONFIG_TEMPLATE = PKG / "templates" / "pipeline.toml"


def project_stage_config(project: Path | None, stage: str) -> dict:
    """A project's `[stages.<stage>]` table, or `{}` when it has none.

    `project` of `None`, or a project with no `.project/pipeline.toml` at
    all, both yield `{}` -- the packaged stage is untouched. A `stages` or
    `[stages.<stage>]` value that is present but not a table is a config
    error, not a silent no-op, so it raises.
    """
    if project is None:
        return {}
    try:
        cfg = project_config(project)
    except PipelineError:
        return {}
    stages = cfg.get("stages", {})
    if not isinstance(stages, dict):
        raise PipelineError(f"{project}: [stages] must be a table")
    table = stages.get(stage, {})
    if not isinstance(table, dict):
        raise PipelineError(f"{project}: [stages.{stage}] must be a table")
    return table


def stage_config(stage: str, project: Path | None = None) -> dict:
    """Model, effort and write access come from the stage prompt's own
    frontmatter, so a stage is one self-contained file -- overlaid, when a
    project is given, with that project's `[stages.<stage>]` table.

    The merge is shallow: a project's `skills` list REPLACES the packaged
    list, it does not extend it.
    """
    meta, _ = split_frontmatter(STAGES_DIR / f"{stage}.md")
    return {**meta, **project_stage_config(project, stage)}


def agent_stages() -> list[str]:
    return sorted(p.stem for p in STAGES_DIR.glob("*.md") if not p.stem.startswith("_"))


def is_readonly(stage: str, project: Path | None = None) -> bool:
    return not stage_config(stage, project).get("write", False)


def project_config(project: Path) -> dict:
    """The project's config as HEAD has it, not as the working tree has it.

    Every stage can write the main checkout's `.project/` -- it is where the
    ticket file lives, and `tree_snapshot()` excludes it -- and the guard's
    path rule blocks a file tool there, but Bash still reaches the file.
    Reading off disk let any
    stage rewrite `test_one`, `test_suite` and `base`, the commands Tier A,
    `verifying` and `merging` trust. Read from HEAD, an uncommitted edit is
    inert, and a committed one is in the ticket's diff, where `review` sees
    it and `machine.FENCED` parks it at `awaiting-merge`.

    The disk fallback covers a project whose config git does not have:
    freshly `pipeline init`-ed and not yet committed, or `.project/` excluded
    from git (`pipeline init --private`). A ticket branch cannot reach it --
    only a commit on the main checkout can take the file out of HEAD.
    """
    text = head_file(project, ".project/pipeline.toml")
    if text is None:
        cfg = project / ".project" / "pipeline.toml"
        if not cfg.is_file():
            raise PipelineError(f"no {cfg} -- run `pipeline init {project}` first")
        text = cfg.read_text()
    return tomllib.loads(text)


def harness(name: str = "claude-code") -> dict:
    p = HARNESSES_DIR / f"{name}.toml"
    if not p.is_file():
        raise PipelineError(f"no harness config {p}")
    return tomllib.loads(p.read_text())


MCP_NAME = re.compile(r"^[a-zA-Z0-9-]+$")


def mcp_servers(project: Path, cfg: dict) -> dict:
    """The MCP servers this stage may use: `[mcp.<name>]` in the project's
    `.project/pipeline.toml`, intersected with the stage's `mcp:` frontmatter.

    A name containing `__` would be ambiguous to split back out of
    `mcp__<server>__<tool>` in the guard, so `mcp_verdict()`'s split assumes
    `[a-zA-Z0-9-]` only -- refused here rather than let through and mis-split.
    """
    wanted = cfg.get("mcp") or []
    if not wanted:
        return {}
    declared = project_config(project).get("mcp") or {}
    out = {}
    for n in wanted:
        if not isinstance(n, str) or not MCP_NAME.match(n):
            raise PipelineError(f"bad MCP server name {n!r} -- [a-zA-Z0-9-] only")
        if n not in declared:
            raise PipelineError(
                f"MCP server {n!r} is not declared in "
                f"{project}/.project/pipeline.toml")
        out[n] = dict(declared[n])
    return out


def mcp_config(servers: dict) -> Path | None:
    """The `--mcp-config` file Claude Code wants: `mcpServers` keyed by name,
    with `readonly` stripped -- that key is the pipeline's own, read by
    `spawn()` to build `PIPELINE_MCP_READONLY`, and the CLI has no use for it.
    """
    if not servers:
        return None
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"mcpServers": {n: {k: v for k, v in s.items() if k != "readonly"}
                              for n, s in servers.items()}}, f)
    f.close()
    return Path(f.name)


def stage_extra(project: Path | None, stage: str) -> str:
    """A project's own prose for this stage, or `""` when it has none.

    Read the way `project_config()` reads `.project/pipeline.toml`: from
    HEAD, falling back to disk only when git has no copy at all. A read-only
    stage can write this file with no commit, no diff, no snapshot and no
    gate, so reading it off disk let uncommitted prose reach the next
    spawn's composed prompt unreviewed.
    """
    if project is None:
        return ""
    rel = f".project/stages/{stage}.extra.md"
    text = head_file(project, rel)
    if text is not None:
        return text
    f = project / rel
    return f.read_text() if f.is_file() else ""


def compose_prompt(stage: str, hcfg: dict | None = None, view: str = "",
                   project: Path | None = None) -> Path:
    """_common.md + this stage's body, frontmatter stripped, as one file.

    A stage's `skills:` only reaches the prompt when the harness declares the
    tool that can invoke them (`skill_tool`). Otherwise the block is dropped:
    the 2026-08-21 run appended it unconditionally, so every triage, planning
    and implementing stage opened by calling a tool it had not been given
    ("No such tool available: Skill") -- the prompt lying to the agent, which
    is the one thing this design exists to stop."""
    cfg, body = split_frontmatter(STAGES_DIR / f"{stage}.md")
    text = (STAGES_DIR / "_common.md").read_text() + "\n" + body
    if cfg.get("skills") and (hcfg or {}).get("skill_tool"):
        text += ("\n\n## Skills for this stage\n\n"
                 "Invoke these before you start; they are here because this "
                 "stage's job depends on them.\n\n"
                 + "\n".join(f"- `/{sk}`" for sk in cfg["skills"]) + "\n")
    extra = stage_extra(project, stage)
    if extra:
        text += ("\n\n---\n\n# This project's additions to this stage\n\n"
                 f"From `.project/stages/{stage}.extra.md`. These instructions "
                 "add to the rules above, and never relax them.\n\n" + extra)
    if view:
        text += ("\n\n---\n\n# The ticket\n\nThis is a bounded view of "
                 "the ticket named in your instructions -- the ticket's "
                 "own text, trimmed. Read it here; open the file only "
                 "for what the view says it omitted.\n\n" + view)
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
    f.write(text)
    f.close()
    return Path(f.name)


def render(hcfg: dict, cfg: dict, *, tid: str, project: Path, ticket: Path,
           result_file: Path, session: str, prompt: Path,
           settings: Path | None = None, mcp: Path | None = None,
           key: str = "cmd") -> str:
    """Fill a harness's `cmd` template. Pulled out of `spawn()` so a harness
    can be exercised -- rendered command asserted -- without ever running an
    agent, which is how `codex.toml` is tested.

    `prompt_mode`: "system" (default) passes `stage_prompt` as a path the
    harness's own template reads (`claude-code.toml`'s `$(cat {stage_prompt})`
    via `--append-system-prompt`). "inline" is for a harness with no system
    prompt flag: the composed prompt is read here and prepended to the
    work-ticket message as one positional `{prompt}` argument.

    `key` picks the template: "cmd" headless, "interactive_cmd" for a stage
    with `mode: interactive`. A harness with no interactive template falls
    back to its normal command under the PTY -- what you lose is the
    harness's interactive flags, not the terminal.

    `mcp`, like `settings`, is a path to a file the dispatcher already wrote --
    here the `--mcp-config` file `mcp_config()` built. `None` renders no flag,
    which is what a harness with no `{mcp_flag}` in its template already gets."""
    ticket_q, result_q = shlex.quote(str(ticket)), shlex.quote(str(result_file))
    work = (f"Work ticket {tid}. Your prompt carries a bounded view of "
            f"{ticket_q}; open that file only for what the view says it "
            f"omitted, and read only the lines you need. When finished "
            f"write {result_q}")
    inline = (shlex.quote(prompt.read_text() + "\n\n" + work)
              if hcfg.get("prompt_mode", "system") == "inline" else "")
    return (hcfg.get(key) or hcfg["cmd"]).format(
        model=cfg.get("model", "sonnet"),
        effort_flag=(hcfg.get("effort_flag", "").format(effort=cfg["effort"])
                     if cfg.get("effort") else ""),
        session_flag=hcfg.get("session_flag", "").format(session=session),
        settings_flag=(hcfg.get("settings_flag", "").format(
            settings=shlex.quote(str(settings))) if settings else ""),
        mcp_flag=(hcfg.get("mcp_flag", "").format(mcp=shlex.quote(str(mcp)))
                  if mcp else ""),
        # stage frontmatter wins, then the harness's default for THIS template
        # (headless and interactive want opposite answers -- see
        # `claude-code.toml`), then the pre-2026-08-21 value for a harness that
        # declares nothing.
        permission_mode=cfg.get("permission_mode", hcfg.get(
            "interactive_permission_mode" if key == "interactive_cmd"
            else "permission_mode", "acceptEdits")),
        stage_prompt=shlex.quote(str(prompt)),
        prompt=inline,
        # The mirror of `_tools()`, gated on the same pair it is: a stage that
        # ends up with no skill tool -- because it declares no `skills:`, or
        # because the harness supplies none -- can also be spawned with the
        # flag that drops the skill machinery entirely. Measured on
        # `claude-haiku-4-5-20251001`: 98 slash commands and 22,574 tokens of
        # opening context become 0 and 19,946 -- 2,628 tokens back on EVERY
        # turn, and a stage pays its opening context once per turn. Verified
        # 2026-08-21 that a `PreToolUse` guard still fires under the flag;
        # that is the condition of using it at all (invariant 4).
        skills_flag=("" if (cfg.get("skills") and hcfg.get("skill_tool"))
                     else hcfg.get("no_skills_flag", "")),
        tools=_tools(hcfg, cfg),
        cap=cfg.get("max_usd", hcfg.get("max_usd", 5)),
        project=shlex.quote(str(project)),
        ticket=ticket_q,
        result_file=result_q,
        id=tid,
    )


def _tools(hcfg: dict, cfg: dict) -> str:
    """The stage's toolset, plus the harness's skill tool when -- and only when
    -- the stage declares `skills:` and the harness can supply one."""
    tools = cfg.get("tools") or (hcfg["write_tools"] if cfg.get("write")
                                 else hcfg["readonly_tools"])
    skill_tool = hcfg.get("skill_tool")
    if cfg.get("skills") and skill_tool and skill_tool not in tools.split(","):
        tools += f",{skill_tool}"
    return tools


def stage_settings(stage: str, cfg: dict) -> Path | None:
    """Per-stage hooks, as a settings file the harness loads. A hook is the only
    layer that decides with code, so this is where a stage's non-negotiables go."""
    names = cfg.get("hooks") or []
    if not names:
        return None
    # The interpreter is named, not left to the shebang: `#!/usr/bin/env
    # python3` resolves to whatever `python3` the operator has first on PATH,
    # which on macOS is the 3.9 the system ships and cannot parse the guard's
    # `str | None` annotations. A guard that fails to import is a guard that
    # does not run, so it runs under the same interpreter as the dispatcher.
    entries = [{"type": "command",
                "command": f"{shlex.quote(sys.executable)} "
                           f"{shlex.quote(str(HOOKS_DIR / f'{n}.py'))}"}
               for n in names]
    # A regex over the tool name, spelled out rather than relying on `Edit`
    # matching `MultiEdit` by substring. With `Bash` alone a `Write` to any
    # absolute path never reached this hook -- step 14 of TICKET-052's plan
    # is the live check that Claude Code delivers a `Write` event here.
    # `mcp__.*` covers every MCP tool name, unconditionally -- even for a stage
    # with no `mcp:` -- because `mcp_verdict()` in the guard default-denies any
    # server not in `PIPELINE_MCP_ALLOW`, so a server arriving by another route
    # is refused rather than unobserved. `--tools` restricts built-in tools
    # only (DEC-025); this matcher is what makes an MCP call visible at all.
    settings = {"hooks": {"PreToolUse": [
        {"matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit|mcp__.*",
         "hooks": entries}]}}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(settings, f)
    f.close()
    return Path(f.name)
