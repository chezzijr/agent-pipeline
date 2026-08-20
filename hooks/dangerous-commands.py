#!/usr/bin/env python3
"""PreToolUse guard. Hooks decide with code -- this is the only layer in the
pipeline that can make a promise, so it holds the rules that must not depend on
a model's judgment.

Two rule sets, both applied per shell segment rather than to the raw string,
because `cd /tmp && sudo rm -rf /etc` is not a `sudo` command until you split it:

  * always    -- destructive or machine-wide, in any stage. A blocklist, which
                 is leaky by nature; it is a backstop, not the perimeter.
  * read-only -- an ALLOWLIST, when PIPELINE_READONLY=1. A read-only stage needs
                 to run tests, read git, and grep. Everything else is denied by
                 default, so a bypass needs a hole in a short list of permitted
                 programs rather than a gap between blocked patterns.

Registered per stage via `hooks:` in that stage's frontmatter.
"""
import json
import os
import re
import shlex
import sys

OPERATORS = {";", "&&", "||", "|", "&", "\n"}
SHELLS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "shell"}
HOME_ISH = re.compile(r"^(/|~|~/|\$HOME/?|\$\{HOME\}/?|/\*)$")

# read-only allowlist -----------------------------------------------------
GIT_READ = {"status", "log", "diff", "show", "blame", "grep", "ls-files",
            "rev-parse", "rev-list", "branch", "remote", "describe", "cat-file",
            "shortlog", "ls-tree", "merge-base", "name-rev", "worktree"}
GIT_WORKTREE_READ = {"list"}
READ_TOOLS = {"ls", "cat", "head", "tail", "wc", "grep", "rg", "ag", "find",
              "file", "stat", "du", "tree", "echo", "true", "false", "pwd",
              "which", "basename", "dirname", "sort", "uniq", "cut", "awk",
              "diff", "column", "jq", "yq", "date", "printf", "test", "["}
TEST_RUNNERS = {"pytest", "py.test", "tox", "nox", "unittest"}
# programs allowed only with a vetted first argument
GUARDED = {
    "python": {"-m"}, "python3": {"-m"}, "uv": {"run"}, "poetry": {"run"},
    "cargo": {"test", "check", "clippy", "build", "fmt"},
    "go": {"test", "vet", "build"},
    "npm": {"test", "run"}, "pnpm": {"test", "run"}, "yarn": {"test", "run"},
    "make": {"test", "check", "lint"},
    "sed": set(),  # only reaches here if -i was already rejected below
}
PY_MODULES_OK = {"pytest", "unittest", "tox", "nox"}


def segments(command: str) -> list[list[str]] | None:
    """Split a shell command into argv lists, one per segment. None if the
    string will not lex -- which is itself a reason to refuse."""
    if "\n" in command:
        # shlex treats a newline as plain whitespace, which would weld two
        # separate commands into one argv and hide the second from every rule
        out = []
        for line in command.split("\n"):
            if not line.strip():
                continue
            part = segments(line)
            if part is None:
                return None
            out.extend(part)
        return out
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:
        return None
    out, current = [], []
    for tok in tokens:
        if tok in OPERATORS or set(tok) <= {"&", "|", ";"} and tok:
            if current:
                out.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        out.append(current)
    return out


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
            if name == "sed" and any(a.startswith("-i") for a in args):
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
        return "command does not parse as a shell command"
    segs = [a for seg in segs for a in flatten(seg)]
    why = always_rules(segs, command)
    if why or not readonly:
        return why
    return readonly_rules(segs, command)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0  # never break the agent over a malformed event
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    why = verdict(command, os.environ.get("PIPELINE_READONLY") == "1")
    if why is None:
        return 0
    stage = os.environ.get("PIPELINE_STAGE", "this stage")
    print(f"Blocked by the pipeline guard ({stage}): {why}.\n"
          f"Command: {command}\n"
          f"If your stage genuinely needs this, stop and report it in the ticket "
          f"rather than working around the guard.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
