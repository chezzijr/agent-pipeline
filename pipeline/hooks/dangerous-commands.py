#!/usr/bin/env python3
"""PreToolUse guard. Hooks decide with code -- this is the only layer in the
pipeline that can make a promise, so it holds the rules that must not depend on
a model's judgment.

Three rule sets. `always` and `read-only` are applied per shell segment rather
than to the raw string, because `cd /tmp && sudo rm -rf /etc` is not a `sudo`
command until you split it:

  * always    -- destructive or machine-wide, in any stage. A blocklist, which
                 is leaky by nature; it is a backstop, not the perimeter.
  * read-only -- an ALLOWLIST, when PIPELINE_READONLY=1. A read-only stage needs
                 to run tests, read git, and grep. Everything else is denied by
                 default, so a bypass needs a hole in a short list of permitted
                 programs rather than a gap between blocked patterns.
  * paths     -- for a file tool, when PIPELINE_WORKTREE is set. A write
                 outside the worktree is refused, except the ticket file and
                 the `.result` sidecar. Bash is deliberately NOT covered:
                 `echo x > /abs/path` still writes anywhere.

Registered per stage via `hooks:` in that stage's frontmatter.

This file is registered through `--settings`, which Claude Code merges
*behind* a project settings source. `<worktree>/.claude/settings.json` =
`{"disableAllHooks": true}` therefore drops this hook entirely, so
`strip_settings_sources()` in `pipeline/core/worktree.py` removes that file
before every spawn. Do not remove it: without it a `write: true` stage
disables this guard for every later spawn in its worktree.
"""
import json
import os
import re
import shlex
import sys

PUNCTUATION = "();<>|&\n"            # what shlex emits as punctuation tokens
SEPARATORS = {"&", "|", ";", "\n"}   # a run of these separates two commands
SHELLS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "shell"}
HOME_ISH = re.compile(r"^(/|~|~/|\$HOME/?|\$\{HOME\}/?|/\*)$")
SED_IN_PLACE = re.compile(r"-[nrsuEz]*i.*|--in-place(=.*)?")

# read-only allowlist -----------------------------------------------------
GIT_READ = {"status", "log", "diff", "show", "blame", "grep", "ls-files",
            "rev-parse", "rev-list", "branch", "remote", "describe", "cat-file",
            "shortlog", "ls-tree", "merge-base", "name-rev", "worktree"}
GIT_WORKTREE_READ = {"list"}
READ_TOOLS = {"ls", "cat", "head", "tail", "wc", "grep", "rg", "ag", "find",
              "file", "stat", "du", "tree", "echo", "true", "false", "pwd",
              "which", "basename", "dirname", "sort", "uniq", "cut", "awk",
              "diff", "column", "jq", "yq", "date", "printf", "test", "[",
              "sed"}
TEST_RUNNERS = {"pytest", "py.test", "tox", "nox", "unittest"}
# programs allowed only with a vetted first argument
GUARDED = {
    "python": {"-m"}, "python3": {"-m"}, "uv": {"run"}, "poetry": {"run"},
    "cargo": {"test", "check", "clippy", "build", "fmt"},
    "go": {"test", "vet", "build"},
    "npm": {"test", "run"}, "pnpm": {"test", "run"}, "yarn": {"test", "run"},
    "make": {"test", "check", "lint"},
}
PY_MODULES_OK = {"pytest", "unittest", "tox", "nox"}


def split_segments(tokens: list[str]) -> list[list[str]]:
    """Token list to argv lists. A token that is a run of separator
    characters ends the segment it follows. A punctuation run carrying a
    newline separates too: shlex welds `>` to the newline after it, and
    `echo x ><newline>rm -rf /` must not hide the `rm` inside echo's argv."""
    out, current = [], []
    for tok in tokens:
        if tok and (set(tok) <= SEPARATORS
                    or "\n" in tok and set(tok) <= set(PUNCTUATION)):
            if current:
                out.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        out.append(current)
    return out


def presplit_segments(command: str) -> list[list[str]] | None:
    """The pre-TICKET-057 splitter: split on newlines, lex each line alone.

    Reached only for a command containing a backslash. A line ending in one
    does not lex ("No escaped character"), so a line continuation is refused
    rather than joined, and a newline inside a quoted string is refused
    rather than kept. Both are fail-closed, which is why this is the route.
    """
    out = []
    for line in command.split("\n"):
        if not line.strip():
            continue
        lex = shlex.shlex(line, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        try:
            out.extend(split_segments(list(lex)))
        except ValueError:
            return None
    return out


def lexed_segments(command: str) -> list[list[str]] | None:
    """The newline-aware splitter, for a command with no backslash in it.

    A newline is a punctuation char here rather than whitespace, so shlex
    emits it as its own token outside quotes and keeps it inside a quoted
    string. Splitting the raw string on newlines instead refuses every
    quoted multi-line command as "does not parse", which is the defect
    TICKET-057 opened on.

    `commenters` is off deliberately. shlex eats the newline that ends a
    comment, so with comments on, `echo hi # note<newline>sudo rm -rf /etc`
    lexes as one argv and the `sudo` rule never sees it.
    """
    lex = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
    lex.whitespace = " \t\r"
    lex.commenters = ""
    lex.whitespace_split = True
    try:
        return split_segments(list(lex))
    except ValueError:
        return None


def segments(command: str) -> list[list[str]] | None:
    """Split a shell command into argv lists, one per segment. None if the
    string will not lex -- which is itself a reason to refuse.

    A command containing a backslash goes down `presplit_segments()`, which
    refuses more than it parses. This guard does not model shell backslash
    grammar: TICKET-057 hand-rolled that pre-pass three times and every
    pass was found allowing a command the old splitter blocked -- last an
    apostrophe inside double quotes, and a doubled backslash before a
    newline. Refusing what the old splitter cannot parse costs the line
    continuation and buys a grammar with no known escape. Do not add a
    backslash pre-pass.
    """
    if "\\" in command:
        return presplit_segments(command)
    return lexed_segments(command)


def flatten(argv: list[str]) -> list[list[str]]:
    """`sh -c '<cmd>'` hides a whole command inside one argument. Unwrap it so
    the rules below see what actually runs."""
    if not argv:
        return []
    name = os.path.basename(argv[0])
    if name in SHELLS and "-c" in argv:
        i = argv.index("-c")
        if i + 1 < len(argv):
            inner = segments(argv[i + 1])
            return [a for seg in (inner or []) for a in flatten(seg)] or [argv]
    return [argv]


def downloaded_paths(segs: list[list[str]]) -> set[str]:
    """Paths curl/wget wrote, so `curl -o /tmp/x u && bash /tmp/x` is caught."""
    paths = set()
    for argv in segs:
        if not argv or os.path.basename(argv[0]) not in {"curl", "wget"}:
            continue
        for flag in ("-o", "--output", "-O", "--output-document"):
            if flag in argv:
                i = argv.index(flag)
                if i + 1 < len(argv):
                    paths.add(argv[i + 1])
    return paths


def always_rules(segs: list[list[str]], raw: str) -> str | None:
    downloads = downloaded_paths(segs)
    piped_into_shell = re.search(r"\|\s*(sudo\s+)?[\w/]*(" + "|".join(SHELLS) + r")\b", raw)
    fetches = any(argv and os.path.basename(argv[0]) in {"curl", "wget"} for argv in segs)
    if fetches and piped_into_shell:
        return "piping a download straight into a shell"

    for argv in segs:
        if not argv:
            continue
        name = os.path.basename(argv[0])
        args = argv[1:]

        if name == "sudo" or name == "doas":
            return "sudo: agents do not get root"
        if name == "eval":
            return "eval: indirection the guard cannot inspect"
        if name in SHELLS and any(a in downloads for a in args):
            return "running a file that was just downloaded"

        if name == "rm":
            flags = [a for a in args if a.startswith("-")]
            recursive = any("r" in f.lstrip("-") or f in ("--recursive",) for f in flags)
            force = any("f" in f.lstrip("-") or f in ("--force",) for f in flags)
            targets = [a for a in args if not a.startswith("-")]
            if recursive and force and any(HOME_ISH.match(t) for t in targets):
                return "recursive delete of a root or home path"
            if any(re.search(r"bash_history|zsh_history", t) for t in targets):
                return "erasing shell history"

        if name == "git":
            sub = next((a for i, a in enumerate(args)
                        if not a.startswith("-") and (i == 0 or args[i - 1] != "-C")), None)
            rest = args
            if sub == "push":
                if any(f in rest for f in ("--force", "-f", "--force-with-lease")):
                    return "force push"
                if any(b in rest for b in ("main", "master")):
                    return "direct push to the default branch"
            if sub == "clean" and any("f" in a.lstrip("-") for a in rest if a.startswith("-")):
                return "git clean discards untracked work"
            if sub == "worktree" and "remove" in rest:
                return "worktrees are the dispatcher's to manage"

        if name == "mkfs" or name.startswith("mkfs."):
            return "filesystem format"
        if name == "dd" and any(a.startswith("of=/dev/") for a in args):
            return "raw write to a device"
        if name == "chmod" and "777" in args and any(HOME_ISH.match(a) for a in args):
            return "world-writable root or home"
        if name == "history" and "-c" in args:
            return "erasing shell history"

    if re.search(r">\s*/dev/(sd|nvme|disk)", raw):
        return "raw write to a device"
    if re.search(r":\(\)\s*\{.*\|.*&.*\}", raw):
        return "fork bomb"
    return None


def readonly_rules(segs: list[list[str]], raw: str) -> str | None:
    # any redirection that lands in a file; `2>&1` and `>&2` are not writes
    if re.search(r"(?<![0-9&>])>{1,2}(?!\s*&)", raw) or re.search(r"\d>{1,2}(?!\s*&)", raw):
        return "shell redirection into a file"
    if "$(" in raw or "`" in raw:
        return "command substitution the guard cannot inspect"

    for argv in segs:
        if not argv:
            continue
        name = os.path.basename(argv[0])
        args = argv[1:]

        if name == "git":
            sub = next((a for i, a in enumerate(args)
                        if not a.startswith("-") and (i == 0 or args[i - 1] != "-C")), None)
            if sub not in GIT_READ:
                return f"git {sub or ''}: not a read-only git subcommand"
            if sub == "worktree" and not (set(args) & GIT_WORKTREE_READ):
                return "git worktree: only `list` is read-only"
            continue

        if name in READ_TOOLS or name in TEST_RUNNERS:
            if name == "sed" and any(SED_IN_PLACE.fullmatch(a) for a in args):
                return "sed -i is an in-place edit"
            continue

        if name in GUARDED:
            if name in ("python", "python3"):
                if len(args) < 2 or args[0] != "-m" or args[1] not in PY_MODULES_OK:
                    return f"{name}: only `-m {'/'.join(sorted(PY_MODULES_OK))}` is allowed"
                continue
            if not args or args[0] not in GUARDED[name]:
                return f"{name} {args[0] if args else ''}: not an allowed subcommand"
            continue

        return f"`{name}` is not on the read-only allowlist"
    return None


def verdict(command: str, readonly: bool) -> str | None:
    segs = segments(command)
    if segs is None:
        if "\\" in command:
            return ("command does not parse as a shell command: it contains a "
                    "backslash, which this guard refuses rather than models -- "
                    "put the command on one line without one")
        return "command does not parse as a shell command"
    segs = [a for seg in segs for a in flatten(seg)]
    why = always_rules(segs, command)
    if why or not readonly:
        return why
    return readonly_rules(segs, command)


FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
PATH_KEYS = ("file_path", "notebook_path")


def resolve(path: str, base: str) -> str | None:
    """A path, resolved against `base` when it is relative. `None` for
    anything that will not resolve -- invariant 5: this reads hostile input."""
    if not path:
        return None
    try:
        full = path if os.path.isabs(path) else os.path.join(base, path)
        return os.path.realpath(full)
    except (OSError, ValueError):
        return None


def path_verdict(path: str, worktree: str, allowed: list[str]) -> str | None:
    """None if `path` resolves inside `worktree` or matches an entry of
    `allowed`; otherwise the reason it is blocked."""
    wt = resolve(worktree, os.getcwd())
    if wt is None:
        return f"PIPELINE_WORKTREE={worktree!r} does not resolve to a path"
    target = resolve(path, wt)
    if target is None:
        return f"{path!r} does not resolve to a path"
    if any(target == resolve(p, wt) for p in allowed):
        return None
    if target == wt or target.startswith(wt + os.sep):
        return None
    return f"{target} is outside this stage's worktree {wt}"


def file_verdict(tool_input: dict) -> str | None:
    wt = os.environ.get("PIPELINE_WORKTREE")
    if not wt:
        return None
    path = next((tool_input.get(k) for k in PATH_KEYS
                 if isinstance(tool_input.get(k), str)), None)
    if path is None:
        return "a file tool with no path the guard can read"
    allowed = [p for p in (os.environ.get("PIPELINE_TICKET"),
                            os.environ.get("PIPELINE_RESULT")) if p]
    return path_verdict(path, wt, allowed)


def mcp_verdict(tool: str) -> str | None:
    """An MCP tool is named `mcp__<server>__<tool>`. The guard parses shell and
    cannot judge `mcp__github__create_pr`, so the rule is a per-server
    allowlist, default deny -- the same shape as the read-only rules."""
    parts = tool.split("__")
    if len(parts) < 3 or not parts[1]:
        return f"{tool} is not a recognisable MCP tool name"
    server = parts[1]
    allow = {s for s in os.environ.get("PIPELINE_MCP_ALLOW", "").split(",") if s}
    if server not in allow:
        return f"MCP server {server} is not declared for this stage"
    if os.environ.get("PIPELINE_READONLY") == "1":
        ro = {s for s in os.environ.get("PIPELINE_MCP_READONLY", "").split(",") if s}
        if server not in ro:
            return f"MCP server {server} is not marked readonly and this stage is read-only"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0  # never break the agent over a malformed event
    tool = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input") or {}
    if tool in FILE_TOOLS:
        label = "Path"
        subject = next((tool_input.get(k) for k in PATH_KEYS
                         if isinstance(tool_input.get(k), str)), "")
        why = file_verdict(tool_input)
    elif tool == "Bash":
        label = "Command"
        subject = tool_input.get("command", "")
        why = verdict(subject, os.environ.get("PIPELINE_READONLY") == "1")
    elif tool.startswith("mcp__"):
        label, subject = "Tool", tool
        why = mcp_verdict(tool)
    else:
        return 0
    if why is None:
        return 0
    stage = os.environ.get("PIPELINE_STAGE", "this stage")
    print(f"Blocked by the pipeline guard ({stage}): {why}.\n"
          f"{label}: {subject}\n"
          f"If your stage genuinely needs this, stop and report it in the ticket "
          f"rather than working around the guard.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
