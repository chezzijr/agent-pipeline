"""Tier A gate -- deterministic, no LLM judgment anywhere in the path."""
import re
import shlex
from pathlib import Path

from pipeline.core.config import project_config
from pipeline.core.ticket import (append_thread, load_ticket, save_ticket,
                                  sections, ticket_path)
from pipeline.core.worktree import run_cmd

# `## Thread` is deliberately absent: it starts empty on every ticket and the
# gate itself is what first writes to it.
REQUIRED_SECTIONS = [
    "Summary", "Reproduction", "Digest", "Decisions checked",
    "Plan", "Acceptance criteria", "Rollback",
]


def gate(project: Path, tid: str, workdir: Path | None = None) -> tuple[bool, list[str]]:
    """Tier A checks, run in the ticket's checkout. Returns (passed, findings)."""
    path = ticket_path(project, tid)
    wd = workdir or project
    cfg = project_config(project)
    findings: list[str] = []

    try:
        meta, body = load_ticket(path)
    except Exception as e:
        return False, [f"frontmatter does not parse: {e}"]

    secs = sections(body)
    for name in REQUIRED_SECTIONS:
        if not secs.get(name):
            findings.append(f"section `## {name}` missing or empty")

    test = meta.get("test_file")
    if not test:
        findings.append("no `test_file` recorded in frontmatter")
    else:
        test_path = wd / test.split("::")[0]
        if not test_path.is_file():
            findings.append(f"test file {test_path} does not exist")
        else:
            code, out = run_cmd(cfg["test_one"].format(test=shlex.quote(test)), wd)
            node = test.split("::")[-1]
            if code == 0:
                findings.append(f"`{test}` PASSES -- it must fail before implementation")
            elif node not in out:
                # a missing dependency or an import error exits non-zero too, and
                # looks exactly like a failing test unless you check for the name
                findings.append(
                    f"`{test}` exited non-zero but its name never appears in the "
                    f"output -- it errored rather than failed\n```\n{out[-1200:]}\n```")
            else:
                findings.append(f"ok: `{test}` fails as required\n```\n{out[-1200:]}\n```")
            code, out = run_cmd(cfg["test_suite_without_new"].format(test=shlex.quote(test)), wd)
            if code != 0:
                findings.append(
                    f"suite excluding `{test}` is RED -- pre-existing breakage, "
                    f"fix that first\n```\n{out[-1200:]}\n```"
                )

    dec = secs.get("Decisions checked", "")
    if dec and "none relevant" not in dec.lower() and not re.search(r"\b[A-Z]+-\d+\b|DEC-", dec):
        findings.append("`## Decisions checked` cites no decision IDs and no explicit "
                        "'none relevant' + grep terms")

    if not meta.get("files_declared"):
        findings.append("`files_declared` is empty")

    crit = secs.get("Acceptance criteria", "")
    for line in [l for l in crit.splitlines() if l.strip().startswith(("-", "*"))]:
        # a backticked token is not enough -- "`10ms`" is a metric, not a test
        if not re.search(r"\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/", line, re.I):
            findings.append(f"acceptance criterion names no test: {line.strip()}")

    failed = [f for f in findings if not f.startswith("ok:")]
    verdict = "PASS" if not failed else "FAIL"
    body = append_thread(body, "**Tier A gate: %s**\n\n%s" % (
        verdict, "\n".join(f"- {f}" for f in findings) or "- (no checks ran)"))
    save_ticket(path, meta, body)
    return not failed, failed
