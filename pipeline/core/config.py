"""Where the data files live and what a stage or a project asks for.

The stage prompts, hooks, harnesses and templates sit INSIDE the package:
located from the repo root they are simply gone after `uv tool install .`.
"""
import json
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


def compose_prompt(stage: str) -> Path:
    """_common.md + this stage's body, frontmatter stripped, as one file."""
    cfg, body = split_frontmatter(STAGES_DIR / f"{stage}.md")
    text = (STAGES_DIR / "_common.md").read_text() + "\n" + body
    if cfg.get("skills"):
        text += ("\n\n## Skills for this stage\n\n"
                 "Invoke these before you start; they are here because this "
                 "stage's job depends on them.\n\n"
                 + "\n".join(f"- `/{sk}`" for sk in cfg["skills"]) + "\n")
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
    f.write(text)
    f.close()
    return Path(f.name)


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
