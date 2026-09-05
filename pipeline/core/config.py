"""Where the data files live and what a stage or a project asks for.

The stage prompts, hooks, harnesses, templates and the file-ticket skill sit
INSIDE the package: located from the repo root they are simply gone after
`uv tool install .`.
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

from pipeline.core import PipelineError, notice_once
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
SKILL_TARGETS = {
    "claude": Path(".claude/skills"),
    "codex": Path(".agents/skills"),
}


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
        pinned = stage in USD_SCALED and "max_usd" in override
        if pinned:
            notice_once(
                f"{stage}: max_usd={override['max_usd']} is set without "
                f"scale_usd, so this stage will not scale its cap with plan "
                f"size. Add scale_usd = true if that was not the intent.",
                "cap-pin", str(project), stage,
            )
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


SKILL_MARKS = ".project/skills.json"


def project_skill(project: Path, name: str, target: str = "claude") -> Path:
    try:
        root = SKILL_TARGETS[target]
    except KeyError:
        raise PipelineError(f"unknown skill target {target!r}") from None
    return project / root / name / "SKILL.md"


def skill_mark_key(target: str, name: str) -> str:
    return f"{target}:{name}"


def installed_skill_mark(marks: dict, target: str, name: str) -> str | None:
    key = skill_mark_key(target, name)
    # Before Codex installation support, the manifest held bare names and every
    # one referred to the sole Claude destination.
    return marks.get(key, marks.get(name) if target == "claude" else None)


def skill_path_linked(project: Path, dst: Path) -> bool:
    path = dst
    while path != project and path.parent != path:
        if path.is_symlink():
            return True
        path = path.parent
    return False


def skill_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def skill_marks(project: Path) -> dict:
    """The digest `init` recorded for each skill it installed, or `{}` when
    there is no manifest, it is unreadable, or it is not a dict of strings --
    so an unrecorded copy always reads as unknown, never as pristine."""
    p = project / SKILL_MARKS
    try:
        marks = json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(marks, dict) or not all(isinstance(v, str) for v in marks.values()):
        return {}
    return marks


def mark_skill(project: Path, name: str, text: str, target: str = "claude") -> None:
    digest = skill_digest(text)
    marks = {**skill_marks(project), skill_mark_key(target, name): digest}
    if target == "claude":
        # Keep rollback compatibility with versions whose sole destination was
        # Claude and whose manifest reader knows only bare skill names.
        marks[name] = digest
    p = project / SKILL_MARKS
    p.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(p, json.dumps(marks, indent=2, sort_keys=True) + "\n")


def skill_status(project: Path) -> list[tuple[str, str, Path, str]]:
    """One `(target, name, dst, state)` per packaged skill and agent: `linked` (a symlink --
    never rewritten, checked FIRST so a symlinked copy is never mistaken for
    a content state), `absent` (not installed), `current` (matches the
    packaged template), `stale` (differs from the template but matches the
    recorded install), `customised` (differs from both), `unknown` (differs,
    no record)."""
    marks = skill_marks(project)
    out = []
    for target in SKILL_TARGETS:
        for src in sorted(SKILLS_DIR.iterdir()):
            name = src.name
            dst = project_skill(project, name, target)
            template = (src / "SKILL.md").read_text()
            mark = installed_skill_mark(marks, target, name)
            # Codex documents symlinked skill directories; Claude also permits
            # this repo's existing SKILL.md links. Neither may be replaced by a
            # refresh, because write_atomic() would destroy the chosen layout.
            if skill_path_linked(project, dst):
                state = "linked"
            elif not dst.is_file():
                state = "absent"
            elif dst.read_text() == template:
                state = "current"
            elif mark == skill_digest(dst.read_text()):
                state = "stale"
            elif mark is not None:
                state = "customised"
            else:
                state = "unknown"
            out.append((target, name, dst, state))
    return out


def install_skill(project: Path, name: str, target: str = "claude") -> Path:
    text = (SKILLS_DIR / name / "SKILL.md").read_text()
    dst = project_skill(project, name, target)
    if skill_path_linked(project, dst):
        raise PipelineError(f"refusing to replace symlinked skill path {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(dst, text)
    mark_skill(project, name, text, target)
    return dst


TEST_PLACEHOLDER_RE = re.compile(r"\{(test|path|name|rest)(?::([^{}]*))?\}")


def selector_parts(test: str) -> dict:
    """One `<path>::<name>` test id split into the four placeholder values.

    `rest` is everything after the FIRST `::`, falling back to the whole id
    when there is no `::` -- the module selector a Rust/Go/JVM runner wants,
    while `path` stays the file the gate copies.

    Not named `test_parts`: pytest collects any module-level `test*` name a
    test module imported and runs it as a test with a missing fixture."""
    return {
        "test": test,
        "path": test.split("::")[0],
        "name": test.split("::")[-1],
        "rest": test.split("::", 1)[-1],
    }


def format_tests_cmd(template: str, tests: list) -> str:
    """Substitute `{test}`, `{path}`, `{name}` and `{rest}` for a ticket's whole list.

    A bare `{test}` is every test, space-joined. `{test:<prefix>}` repeats
    `<prefix>` before each one: `pytest --deselect` takes a single value at
    a time, so excluding two tests in one run needs two flags. `{test:}` is
    the space-joined form written out, for a runner that does take several
    values after one flag.

    Values are `shlex.quote`d and de-duplicated first-seen-first, so two
    tests in one file yield one `{path}`. Every other brace passes through
    verbatim, which is DEC-067 and why this is a regex, not `str.format`.
    """
    def sub(m):
        prefix = m.group(2) or ""
        vals = dict.fromkeys(selector_parts(t)[m.group(1)] for t in tests)
        return " ".join(prefix + shlex.quote(v) for v in vals)
    return TEST_PLACEHOLDER_RE.sub(sub, template)


def format_test_cmd(template: str, test: str) -> str:
    """`format_tests_cmd()` for the call sites that hold exactly one test:
    `test_one`, which runs once per test, and `test_suite`. Behaviour is
    unchanged, `test=""` substituting `''` included."""
    return format_tests_cmd(template, [test])


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


HARNESS_NAME = re.compile(r"^[a-zA-Z0-9-]+$")


def project_harness(project: Path, override: str | None = None) -> str:
    """The explicit CLI harness, then this project's configured default."""
    name = override if override is not None else project_config(project).get(
        "harness", "claude-code")
    if not isinstance(name, str) or not HARNESS_NAME.fullmatch(name):
        raise PipelineError(
            f"{project}: harness must contain only letters, digits and hyphens, not {name!r}")
    path = HARNESSES_DIR / f"{name}.toml"
    if not path.is_file():
        raise PipelineError(f"no harness config {path}")
    return name


def validate_stage_overrides(project: Path, stage: str, hcfg: dict) -> None:
    """Refuse project stage keys this harness cannot honestly implement."""
    override = project_stage_config(project, stage)
    unsupported = set(hcfg.get("unsupported_stage_keys") or [])
    found = sorted(unsupported.intersection(override))
    if found:
        raise PipelineError(
            f"{project}: [stages.{stage}] {', '.join(found)} cannot be used "
            f"with the selected harness")
    if not hcfg.get("supports_usd_cap", True) and "max_usd" in override:
        notice_once(
            f"{stage}: max_usd={override['max_usd']} is ignored because the "
            f"selected harness cannot enforce a dollar cap.",
            "cap-unsupported", str(project), stage,
        )


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


def _toml_value(value) -> str:
    """The small TOML subset needed for command-line config overrides."""
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{json.dumps(str(k))}={_toml_value(v)}" for k, v in value.items()
        ) + "}"
    raise PipelineError(f"cannot encode {value!r} as a Codex TOML override")


CODEX_SKILL_NAME = re.compile(r"^[a-z0-9-]+$")


def native_skill_settings(hcfg: dict, cfg: dict, project: Path,
                          worktree: Path) -> str:
    """Bind Codex `$name` references to this worktree's declared skill bytes."""
    root = hcfg.get("skill_root")
    if not root:
        return ""
    if not cfg.get("skills"):
        return "-c skills.include_instructions=false"

    home = Path(os.environ.get("HOME", str(Path.home())))
    codex_home = Path(os.environ.get("CODEX_HOME", str(home / ".codex")))
    roots = (worktree / ".agents" / "skills",
             worktree / ".codex" / "skills",
             home / ".agents" / "skills",
             codex_home / "skills",
             Path("/etc/codex/skills"))
    disabled = set()
    for skills_dir in roots:
        try:
            entries = list(skills_dir.iterdir())
        except OSError:
            continue
        for entry in entries:
            doc = entry / "SKILL.md"
            if doc.is_file():
                disabled.add(str(doc.resolve()))
    rules = [{"path": path, "enabled": False} for path in sorted(disabled)]
    selected = []
    for name in cfg["skills"]:
        if not isinstance(name, str) or not CODEX_SKILL_NAME.fullmatch(name):
            raise PipelineError(f"bad Codex skill name {name!r} -- [a-z0-9-] only")
        path = worktree / root / name / "SKILL.md"
        if not path.is_file():
            raise PipelineError(f"Codex stage skill {name!r} is not installed at {path}")
        rel = f"{root}/{name}/SKILL.md"
        main = project / rel
        trusted = (main.read_text() if skill_path_linked(project, main)
                   else head_file(project, rel))
        if trusted is None and main.is_file():
            trusted = main.read_text()
        if trusted is None or path.read_text() != trusted:
            raise PipelineError(
                f"Codex stage skill {name!r} in the ticket worktree differs "
                f"from the trusted project copy {main}")
        # A name rule disables operator copies; the later path rule re-enables
        # exactly the repository copy the stage declared.
        selected.append(str(path.resolve()))
        # Disable same-name copies from any host root the installed Codex adds;
        # the later path rule wins for this worktree's exact document.
        rules.append({"name": name, "enabled": False})
    rules.extend({"path": path, "enabled": True} for path in selected)
    values = ("-c skills.include_instructions=true "
              "-c skills.bundled.enabled=false -c "
              + shlex.quote("skills.config=" + _toml_value(rules)))
    return values


def mcp_config(servers: dict, hcfg: dict | None = None) -> Path | None:
    """The harness-specific MCP configuration for this stage.

    Claude reads a JSON file via `--mcp-config`; Codex reads one inline TOML
    override. `readonly` belongs to the pipeline guard, and Claude's `type`
    discriminator is not part of Codex's server schema.
    """
    if not servers:
        return None
    mode = (hcfg or {}).get("mcp_mode", "claude-json")
    f = tempfile.NamedTemporaryFile("w", suffix=".toml" if mode == "inline" else ".json",
                                    delete=False)
    if mode == "inline":
        clean = {n: {k: v for k, v in s.items() if k not in {"readonly", "type"}}
                 for n, s in servers.items()}
        f.write("mcp_servers=" + _toml_value(clean))
    else:
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
    cfg = {**cfg, **project_stage_config(project, stage)}
    text = (STAGES_DIR / "_common.md").read_text() + "\n" + body
    skill_format = (hcfg or {}).get("skill_format")
    if cfg.get("skills") and ((hcfg or {}).get("skill_tool") or skill_format):
        skill_format = skill_format or "/{name}"
        text += ("\n\n## Skills for this stage\n\n"
                 "Invoke these before you start; they are here because this "
                 "stage's job depends on them.\n\n"
                 + "\n".join(f"- `{skill_format.format(name=sk)}`"
                              for sk in cfg["skills"]) + "\n")
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
    # Codex cannot enforce a dollar cap, so stage frontmatter must not make its
    # records claim one. This is explicit rather than inferred from max_usd=0:
    # fake.toml uses zero as its default while tests still exercise accounting.
    if not hcfg.get("supports_usd_cap", True):
        return 0
    return cap_for(cfg.get("max_usd", hcfg.get("max_usd", 5)), cfg.get("counters") or {})


def render(hcfg: dict, cfg: dict, *, tid: str, project: Path, ticket: Path,
           result_file: Path, session: str, prompt: Path,
           settings: Path | None = None, mcp: Path | None = None,
           key: str = "cmd", worktree: Path | None = None) -> str:
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
    logical_model = cfg.get("model", "sonnet")
    model = (hcfg.get("models") or {}).get(logical_model, logical_model)
    settings_value = (settings.read_text() if settings and
                      hcfg.get("settings_mode") == "inline" else str(settings or ""))
    mcp_value = (mcp.read_text() if mcp and hcfg.get("mcp_mode") == "inline"
                 else str(mcp or ""))
    wt = worktree or project
    return (hcfg.get(key) or hcfg["cmd"]).format(
        model=model,
        effort_flag=(hcfg.get("effort_flag", "").format(effort=cfg["effort"])
                     if cfg.get("effort") else ""),
        session_flag=hcfg.get("session_flag", "").format(session=session),
        settings_flag=(hcfg.get("settings_flag", "").format(
            settings=shlex.quote(settings_value)) if settings else ""),
        mcp_flag=(hcfg.get("mcp_flag", "").format(mcp=shlex.quote(mcp_value))
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
        skill_settings=native_skill_settings(hcfg, cfg, project, wt),
        tools=_tools(hcfg, cfg),
        cap=stage_cap(cfg, hcfg),
        project=shlex.quote(str(project)),
        worktree=shlex.quote(str(wt)),
        trust_config=shlex.quote(
            f'projects.{json.dumps(str(wt))}.trust_level="untrusted"'),
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


def stage_settings(stage: str, cfg: dict, hcfg: dict | None = None) -> Path | None:
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
    matcher = "Bash|Write|Edit|MultiEdit|NotebookEdit|apply_patch|mcp__.*"
    settings = {"hooks": {"PreToolUse": [
        {"matcher": matcher,
         "hooks": entries}]}}
    mode = (hcfg or {}).get("settings_mode", "path")
    f = tempfile.NamedTemporaryFile("w", suffix=".toml" if mode == "inline" else ".json",
                                    delete=False)
    if mode == "inline":
        f.write("hooks.PreToolUse=" + _toml_value(settings["hooks"]["PreToolUse"]))
    else:
        json.dump(settings, f)
    f.close()
    return Path(f.name)
