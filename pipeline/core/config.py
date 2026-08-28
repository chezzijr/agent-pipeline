"""Where the data files live and what a stage or a project asks for.

The stage prompts, hooks, harnesses, templates and the file-ticket skill sit
INSIDE the package: located from the repo root they are simply gone after
`uv tool install .`.
"""
import hashlib
import json
import re
import shlex
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.core.machine import USD_SCALED, cap_for
from pipeline.core.ticket import split_frontmatter, write_atomic
from pipeline.core.worktree import git_ignored, head_file, run_cmd
# pipeline/daemon/__init__.py is a docstring only, and registry imports only
# pipeline.core and pipeline.core.ticket, neither of which imports
# pipeline.core.config -- so this is not an import cycle.
from pipeline.daemon.registry import config_dir

PKG = Path(__file__).resolve().parent.parent
STAGES_DIR = PKG / "stages"
HOOKS_DIR = PKG / "hooks"
HARNESSES_DIR = PKG / "harnesses"
TICKET_TEMPLATE = PKG / "templates" / "ticket.md"
CONFIG_TEMPLATE = PKG / "templates" / "pipeline.toml"
SKILLS_DIR = PKG / "templates" / "skills"
SKILL_TEMPLATE = SKILLS_DIR / "file-ticket" / "SKILL.md"


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


def cap_config(stage: str, cfg: dict, project: Path | None, counters: dict) -> dict:
    """`cfg`, with `counters` attached when `stage` should scale its dollar
    cap. A computed cap never exceeds the operator's own `max_usd` unless the
    operator also sets `scale_usd = true` -- the same direction as the
    TICKET-069 rule."""
    override = project_stage_config(project, stage)
    want = override.get("scale_usd")
    if want is None:
        want = stage in USD_SCALED and "max_usd" not in override
    return {**cfg, "counters": counters} if want else cfg


def agent_stages() -> list[str]:
    return sorted(p.stem for p in STAGES_DIR.glob("*.md") if not p.stem.startswith("_"))


def is_readonly(stage: str, project: Path | None = None) -> bool:
    return not stage_config(stage, project).get("write", False)


def pin_dir(project: Path) -> Path:
    """Where a project's config is pinned when git will never have it
    (`pipeline init --private`) -- one directory per project, named by a hash
    of its path so the pin lives outside every repo and every ticket branch."""
    return config_dir() / "pinned" / hashlib.sha256(str(project).encode()).hexdigest()[:16]


def pin_path(project: Path, rel: str) -> Path:
    return pin_dir(project) / rel


def _pin_mkdir(pin: Path) -> None:
    """`mkdir(parents=True, mode=0o700)` applies the mode to the leaf only, so
    `pinned/` and the per-project hash directory would otherwise take the
    umask. The pin decides which commands the gate runs; a world-writable
    parent is a way to rewrite it without touching the file."""
    pin.parent.mkdir(parents=True, exist_ok=True)
    d = pin.parent
    while True:
        d.chmod(0o700)
        if d == config_dir():
            break
        d = d.parent


def pinned_text(project: Path, rel: str) -> str | None:
    """The pinned copy of `rel`, refreshed from disk on first read. `None`
    when `rel` does not exist on disk and nothing was pinned yet."""
    pin = pin_path(project, rel)
    if pin.is_file():
        return pin.read_text()
    src = project / rel
    if not src.is_file():
        return None
    _pin_mkdir(pin)
    write_atomic(pin, src.read_text())
    # names the project the hash stands for, for a human reading the directory
    write_atomic(pin_dir(project) / "project", str(project) + "\n")
    return pin.read_text()


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

    The disk fallback covers a project whose config git does not have yet:
    freshly `pipeline init`-ed and not yet committed. A config git will
    NEVER have -- `.project/` excluded from git (`pipeline init --private`) --
    is pinned outside the repo on first read instead, under
    `config_dir()/pinned/`; only `pipeline config --sync` adopts a later
    edit. A ticket branch cannot reach either -- only a commit, or a sync,
    on the main checkout can change what this returns.
    """
    text = head_file(project, ".project/pipeline.toml")
    if text is None and git_ignored(project, ".project/pipeline.toml"):
        text = pinned_text(project, ".project/pipeline.toml")
    if text is None:
        cfg = project / ".project" / "pipeline.toml"
        if not cfg.is_file():
            raise PipelineError(f"no {cfg} -- run `pipeline init {project}` first")
        text = cfg.read_text()
    return tomllib.loads(text)


def config_source(project: Path) -> str:
    """Where `project_config()` would read from: "head" (committed),
    "pinned" (git will never have it), or "disk" (not yet committed)."""
    if head_file(project, ".project/pipeline.toml") is not None:
        return "head"
    if git_ignored(project, ".project/pipeline.toml"):
        return "pinned"
    return "disk"


def sync_pins(project: Path) -> list[Path]:
    """Drop every pinned file for `project`, so the next `project_config()`
    or `stage_extra()` call re-pins from the current disk copy. This is the
    operator's only way to adopt an edit on a project git will never have."""
    d = pin_dir(project)
    if not d.exists():
        return []
    removed = sorted(p for p in d.rglob("*") if p.is_file() and p != d / "project")
    shutil.rmtree(d, ignore_errors=True)
    return removed


TEST_PLACEHOLDER_RE = re.compile(r"\{(test|path|name)\}")


def format_test_cmd(template: str, test: str) -> str:
    """Substitute `{test}`, `{path}` and `{name}` in a project test command.

    `test` is the ticket's whole `test_file` value (`<path>::<name>`), and
    every substitution is `shlex.quote`d, exactly as the single `{test}`
    was. Only these three names are touched: `str.format` raised
    `KeyError: 't##*'` on a literal `${t##*::}`, and `test_suite` was never
    formatted at all, so any other brace must reach the shell as written.
    """
    parts = {"test": test, "path": test.split("::")[0], "name": test.split("::")[-1]}
    return TEST_PLACEHOLDER_RE.sub(lambda m: shlex.quote(parts[m.group(1)]), template)


# `suite_failure`, not `test_suite_failure`, and `project_test_cmd`, not
# `test_command`: pytest collects every module-level name matching
# `test*`, including one a test module imported, and would run these as
# tests it cannot supply `project` for -- `fixture 'project' not found`.
SHELL_CANNOT_RUN = {126: "the shell found it but could not execute it",
                    127: "the shell could not find it"}
# `pytest` exits 5 and prints this when it collected nothing -- what the
# packaged default `test_suite = "pytest"` does in a repo that is not a
# Python one. A collection error prints it too, and exits 2.
NO_TESTS_RE = re.compile(r"no tests ran|no tests were run|collected 0 items")


def project_test_cmd(project: Path, key: str) -> str:
    """The project's `key` command. Raises `PipelineError` when the config
    has no usable one; `project_config()` raises before that for a project
    with no config at all, naming `pipeline init`."""
    cmd = project_config(project).get(key)
    if not isinstance(cmd, str) or not cmd.strip():
        raise PipelineError(f"{project}: `.project/pipeline.toml` has no `{key}` -- "
                            f"the dispatcher would have no command to run")
    return cmd


def suite_failure(project: Path) -> str | None:
    """`None` when the project's `test_suite` can run; the refusal message
    when it cannot run at all.

    A suite that ran and reported failures returns `None`: that is the
    normal state of a project with an open bug, and it is what a ticket is
    filed against. Only two things count as cannot-run -- the shell's own
    126 and 127, and a non-zero exit whose output says nothing ran.

    Substituted with `format_test_cmd(cmd, "")`, matching
    `supervisor.py`'s `t.test_file or ""` for a ticket with no test file.
    """
    cmd = format_test_cmd(project_test_cmd(project, "test_suite"), "")
    code, out = run_cmd(cmd, project)
    reason = SHELL_CANNOT_RUN.get(code)
    if reason is None and code != 0 and NO_TESTS_RE.search(out):
        reason = "it ran no tests"
    if reason is None:
        return None
    return (f"{project}: `test_suite` cannot run -- `{cmd}`: {reason} "
            f"(exit {code})\n{out.strip()[-1200:]}\n"
            f"fix `test_suite` in {project}/.project/pipeline.toml, or "
            f"`pipeline register --force {project}` to register anyway")


# The selector `selector_failure()` probes `test_one` with: a path and a
# name no project has. A runner that reports success for this cannot tell
# `gate()` that a real selector matched nothing either.
PROBE_TEST = ("pipeline_register_probe_no_such_file.py"
              "::pipeline_register_probe_no_such_test")


def selector_failure(project: Path) -> str | None:
    """`None` when the project's `test_one` exits non-zero for a selector
    that matches no test; the refusal message when it does not.

    `gate()` cannot tell `the test passed` from `the selector matched
    nothing` by reading output -- `pytest` prints `1 passed` and never the
    node name. The project's command knows its own runner and can tell, so
    the requirement is checked here, once, at `register`.

    Substituted with `format_test_cmd()`, the one substitution the four
    dispatcher call sites use (DEC-067). It quotes `{test}`, `{path}` and
    `{name}` itself and never raises on any other brace.
    """
    probe = format_test_cmd(project_test_cmd(project, "test_one"), PROBE_TEST)
    code, out = run_cmd(probe, project)
    reason = SHELL_CANNOT_RUN.get(code)
    if reason is None and code == 0:
        reason = "it exited 0 -- `gate()` would read that as `the test PASSES`"
    if reason is None:
        return None
    return (f"{project}: `test_one` must exit non-zero when its selector "
            f"matches no test -- probed with `{PROBE_TEST}`, ran `{probe}`: "
            f"{reason} (exit {code})\n{out.strip()[-1200:]}\n"
            f"make `test_one` fail when its filter matches nothing (the "
            f"`pipeline-config` skill shows how), or "
            f"`pipeline register --force {project}` to register anyway")


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


def readonly_allow(project: Path) -> list[list[str]]:
    """A project's own read-only argv prefixes: `[readonly] allow` in
    `.project/pipeline.toml`, each entry lexed once with `shlex.split`.

    Read through `project_config()`, so the list comes from HEAD of the main
    checkout and a stage cannot widen its own allowlist (DEC-037). A project
    with no config yields `[]` -- `spawn()` calls this for every stage, and
    `tests/test_pty.py` spawns into a bare temp directory with none.  The
    prefixes never override `always_rules()` or the redirection and
    command-substitution rules in the guard.
    """
    try:
        cfg = project_config(project)
    except PipelineError:
        return []
    table = cfg.get("readonly") or {}
    if not isinstance(table, dict):
        raise PipelineError(f"{project}: [readonly] must be a table")
    allow = table.get("allow") or []
    if not isinstance(allow, list):
        raise PipelineError(f"{project}: [readonly] allow must be a list")
    out = []
    for entry in allow:
        if not isinstance(entry, str):
            raise PipelineError(f"{project}: [readonly] allow entry {entry!r} must be a string")
        tokens = shlex.split(entry)
        if not tokens:
            raise PipelineError(f"{project}: [readonly] allow entry {entry!r} is empty")
        out.append(tokens)
    return out


def project_max_parallel(project: Path) -> int | None:
    """A project's own concurrency ceiling: `max_parallel` in
    `.project/pipeline.toml`, or `None` when the project has no config or the
    key is absent -- the daemon `-j` argument stands alone.

    Read through `project_config()`, so the value comes from HEAD of the main
    checkout (DEC-037): a stage cannot widen its own project's concurrency
    from its worktree. The raise here is caught by `_start_cap()` in
    `pipeline/daemon/supervisor.py`, never left to reach `tick()`'s caller.
    """
    try:
        cfg = project_config(project)
    except PipelineError:
        return None
    v = cfg.get("max_parallel")
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise PipelineError(f"{project}: max_parallel must be an integer >= 1, not {v!r}")
    return v


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
    if text is None and git_ignored(project, rel):
        text = pinned_text(project, rel)
    if text is not None:
        return text
    f = project / rel
    return f.read_text() if f.is_file() else ""


def compose_prompt(stage: str, hcfg: dict | None = None, view: str = "",
                   project: Path | None = None, interactive: bool = False) -> Path:
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
    if interactive:
        text += ("\n\n---\n\n# This session runs on a terminal\n\n"
                 "Write the result file LAST: after your `## Thread` entry "
                 "and your `## Summary` rewrite. The dispatcher ends an "
                 "interactive session as soon as the sidecar appears, so "
                 "anything you have not written by then is lost. This "
                 "reverses rule 6's ordering and nothing else.")
    if view:
        text += ("\n\n---\n\n# The ticket\n\nThis is a bounded view of "
                 "the ticket named in your instructions -- the ticket's "
                 "own text, trimmed. Read it here; open the file only "
                 "for what the view says it omitted.\n\n" + view)
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
    f.write(text)
    f.close()
    return Path(f.name)


def stage_cap(cfg: dict, hcfg: dict):
    """The dollar cap a stage spawns under: its own frontmatter, then the
    harness default, then 5. One definition, because `_finish()` names the
    cap a budget-killed stage hit and it must be the number `render()`
    passed.

    `cfg["counters"]` is the plan size the cap scales by. Its absence means
    no scaling. The scaling lives here, rather than at the `render()` call
    site, so `rec["cap"]` in `pipeline/daemon/supervisor.py` names the same
    number the rendered flag does (DEC-077)."""
    return cap_for(cfg.get("max_usd", hcfg.get("max_usd", 5)), cfg.get("counters") or {})


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
        cap=stage_cap(cfg, hcfg),
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
