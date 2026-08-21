"""Where the data files live and what a stage or a project asks for.

The stage prompts, hooks, harnesses and templates sit INSIDE the package:
located from the repo root they are simply gone after `uv tool install .`.
"""
import json
import shlex
import tempfile
import tomllib
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.core.ticket import split_frontmatter

PKG = Path(__file__).resolve().parent.parent
STAGES_DIR = PKG / "stages"
HOOKS_DIR = PKG / "hooks"
HARNESSES_DIR = PKG / "harnesses"
TICKET_TEMPLATE = PKG / "templates" / "ticket.md"
CONFIG_TEMPLATE = PKG / "templates" / "pipeline.toml"


def stage_config(stage: str) -> dict:
    """Model, effort and write access come from the stage prompt's own
    frontmatter, so a stage is one self-contained file."""
    meta, _ = split_frontmatter(STAGES_DIR / f"{stage}.md")
    return meta


def agent_stages() -> list[str]:
    return sorted(p.stem for p in STAGES_DIR.glob("*.md") if not p.stem.startswith("_"))


def is_readonly(stage: str) -> bool:
    return not stage_config(stage).get("write", False)


def project_config(project: Path) -> dict:
    cfg = project / ".project" / "pipeline.toml"
    if not cfg.is_file():
        raise PipelineError(f"no {cfg} -- run `pipeline init {project}` first")
    return tomllib.loads(cfg.read_text())


def harness(name: str = "claude-code") -> dict:
    p = HARNESSES_DIR / f"{name}.toml"
    if not p.is_file():
        raise PipelineError(f"no harness config {p}")
    return tomllib.loads(p.read_text())


def compose_prompt(stage: str, hcfg: dict | None = None) -> Path:
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
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
    f.write(text)
    f.close()
    return Path(f.name)


def render(hcfg: dict, cfg: dict, *, tid: str, project: Path, ticket: Path,
           result_file: Path, session: str, prompt: Path,
           settings: Path | None = None, key: str = "cmd") -> str:
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
    harness's interactive flags, not the terminal."""
    ticket_q, result_q = shlex.quote(str(ticket)), shlex.quote(str(result_file))
    work = f"Work ticket {tid}. Read {ticket_q} first. When finished write {result_q}"
    inline = (shlex.quote(prompt.read_text() + "\n\n" + work)
              if hcfg.get("prompt_mode", "system") == "inline" else "")
    return (hcfg.get(key) or hcfg["cmd"]).format(
        model=cfg.get("model", "sonnet"),
        effort_flag=(hcfg.get("effort_flag", "").format(effort=cfg["effort"])
                     if cfg.get("effort") else ""),
        session_flag=hcfg.get("session_flag", "").format(session=session),
        settings_flag=(hcfg.get("settings_flag", "").format(
            settings=shlex.quote(str(settings))) if settings else ""),
        # stage frontmatter wins, then the harness's default for THIS template
        # (headless and interactive want opposite answers -- see
        # `claude-code.toml`), then the pre-2026-08-21 value for a harness that
        # declares nothing.
        permission_mode=cfg.get("permission_mode", hcfg.get(
            "interactive_permission_mode" if key == "interactive_cmd"
            else "permission_mode", "acceptEdits")),
        stage_prompt=shlex.quote(str(prompt)),
        prompt=inline,
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
    entries = [{"type": "command", "command": str(HOOKS_DIR / f"{n}.py")}
               for n in names]
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": entries}]}}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(settings, f)
    f.close()
    return Path(f.name)
