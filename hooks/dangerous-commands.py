#!/usr/bin/env python3
"""PreToolUse guard. Hooks decide with code -- this is the only layer in the
pipeline that can make a promise, so it holds the rules that must not depend on
a model's judgment.

Blocks unconditionally (exit 2). Two rule sets:
  * always      -- destructive or machine-wide, in any stage
  * read-only   -- mutation of any kind, when PIPELINE_READONLY=1

Registered per stage via `hooks:` in that stage's frontmatter.
"""
import json
import os
import re
import sys

# (pattern, why). Deliberately narrow: a guard that blocks ordinary work gets
# switched off, and a guard that is off protects nothing.
ALWAYS = [
    (r"\brm\s+(-[a-zA-Z]*\s+)*-?[a-zA-Z]*[rf][a-zA-Z]*\s+(/|~|\$HOME|/\*)(\s|$)",
     "recursive delete of a root or home path"),
    (r"\bgit\s+push\b.*(--force|-f)\b", "force push"),
    (r"\bgit\s+push\b.*\b(main|master)\b", "direct push to the default branch"),
    (r"\bgit\s+clean\b.*-[a-zA-Z]*f", "git clean discards untracked work"),
    (r"^\s*sudo\b|\s\|\s*sudo\b", "sudo: agents do not get root"),
    (r"\bmkfs(\.|\s)", "filesystem format"),
    (r"\bdd\b[^|]*\bof=/dev/", "raw write to a device"),
    (r">\s*/dev/(sd|nvme|disk)", "raw write to a device"),
    (r"\bchmod\s+(-[a-zA-Z]+\s+)*777\s+(/|~)", "world-writable root or home"),
    (r"\bcurl\b[^|]*\|\s*(sudo\s+)?(ba)?sh", "piping a download straight into a shell"),
    (r"\bwget\b[^|]*\|\s*(sudo\s+)?(ba)?sh", "piping a download straight into a shell"),
    (r":\(\)\s*\{.*\|.*&.*\}", "fork bomb"),
    (r"\bgit\s+worktree\s+remove\b", "worktrees are the dispatcher's to manage"),
    (r"\bhistory\s+-c\b|\brm\b.*\.bash_history", "erasing shell history"),
]

# A read-only stage gets Bash so it can run tests and read git. Everything that
# writes is off. The dispatcher's tree snapshot catches whatever slips past;
# this stops it happening in the first place.
READONLY = [
    (r"\bsed\b\s+(-[a-zA-Z]*\s+)*-i", "in-place edit"),
    (r"\b(tee|dd)\b", "writes files"),
    (r"(^|[^>\d])>{1,2}\s*[^&\s]", "shell redirection into a file"),
    (r"\bgit\s+(commit|add|checkout|merge|rebase|reset|stash|apply|restore)\b",
     "mutates the repository"),
    (r"\b(mv|cp|rm|mkdir|rmdir|touch|truncate|ln|install|chmod|chown)\b",
     "mutates the filesystem"),
    (r"\bpatch\b", "applies a patch"),
    (r"\b(pip|npm|yarn|pnpm|cargo|go|apt|brew)\s+(install|add|remove|uninstall)\b",
     "installs packages"),
]


def verdict(command: str, readonly: bool) -> str | None:
    for pattern, why in ALWAYS + (READONLY if readonly else []):
        if re.search(pattern, command):
            return why
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0  # never break the agent over a malformed event
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    readonly = os.environ.get("PIPELINE_READONLY") == "1"
    why = verdict(command, readonly)
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
