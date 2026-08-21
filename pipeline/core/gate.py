"""Tier A gate -- deterministic, no LLM judgment anywhere in the path."""
import re
import shlex
import shutil
from pathlib import Path

from pipeline.core.config import project_config
from pipeline.core.ticket import Ticket, ticket_path
from pipeline.core.worktree import base_checkout, base_ref, run_cmd

# `## Thread` is deliberately absent: it starts empty on every ticket and the
# gate itself is what first writes to it.
REQUIRED_SECTIONS = [
    "Summary", "Reproduction", "Digest", "Decisions checked",
    "Plan", "Acceptance criteria", "Rollback",
]


def _cites(text: str, path: str) -> bool:
    """Does `text` name `path`? Substring match, but anchored at a
    non-path/non-word boundary on both sides -- a plain `path in text` lets a
    short declared file (`io.py`) be "cited" by an unrelated one that merely
    contains it (`ratio.py`, `delegate.py` for `gate.py`)."""
    pat = r"(?<![\w./-])" + re.escape(path) + r"(?![\w-])"
    return re.search(pat, text) is not None


def _base_findings(project: Path, cfg: dict, wd: Path, test: str,
                   node: str) -> list[str]:
    """A test that fails in the ticket's worktree proves the bug is HERE.
    Tier A wants more: that it fails on BASE, which is what makes it a
    reproduction rather than a branch that broke itself. The test itself
    only exists on the branch, so the branch's test file is copied onto a
    throwaway checkout of base: the branch's test, base's code."""
    if wd.resolve() == project.resolve():
        return ["ok: base check skipped -- no ticket worktree was given, so "
                "there is no branch to compare against base"]
    rel = test.split("::")[0]
    if ".." in rel or rel.startswith("/"):
        # SAFE_TEST bans shell metacharacters, not traversal -- and unlike
        # the branch run, which only reads, this one WRITES the path.
        return [f"`{test}` is not a plain relative path -- refusing to copy "
                f"it into a checkout of base"]
    base = base_ref(cfg)
    with base_checkout(project, cfg) as (base_wt, err):
        if base_wt is None:
            return [f"could not check out base `{base}` to re-run `{test}`"
                    f"\n```\n{err[-1200:]}\n```"]
        dst = base_wt / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(wd / rel, dst)
        code, out = run_cmd(
            cfg["test_one"].format(test=shlex.quote(test)), base_wt)
    if code == 0:
        return [f"`{test}` PASSES on base `{base}` -- it fails only on this "
                f"branch, so it is not a reproduction: either the bug is "
                f"already fixed on base, or the test is red for a reason "
                f"base does not have\n```\n{out[-1200:]}\n```"]
    if node not in out:
        # same trap as the branch run: an import error exits non-zero too,
        # and here that reads as a successful reproduction
        return [f"`{test}` exited non-zero on base `{base}` but its name "
                f"never appears in the output -- it errored rather than "
                f"failed, so base proves nothing\n```\n{out[-1200:]}\n```"]
    return [f"ok: `{test}` fails on base `{base}` too -- the bug is not "
            f"already fixed upstream\n```\n{out[-1200:]}\n```"]


def gate(project: Path, tid: str, workdir: Path | None = None) -> tuple[bool, list[str]]:
    """Tier A checks, run in the ticket's checkout. Returns (passed, findings)."""
    path = ticket_path(project, tid)
    wd = workdir or project
    cfg = project_config(project)
    findings: list[str] = []

    try:
        t = Ticket.load(path)
    except Exception as e:
        return False, [f"frontmatter does not parse: {e}"]

    # `pipeline gate` is a human entry point, so unlike the dispatcher's own
    # path nothing has validated this ticket yet. Refuse before `test_file`
    # reaches the project's test command at all.
    bad = t.errors()
    if bad:
        return False, [f"unusable frontmatter: {b}" for b in bad]

    secs = t.sections()
    for name in REQUIRED_SECTIONS:
        if not secs.get(name):
            findings.append(f"section `## {name}` missing or empty")

    # The gate proves a bug exists by running a test that fails; it must also
    # prove that failure is the *reported* one, or a test failing for an
    # unrelated reason sails through looking like evidence.
    repro = secs.get("Reproduction", "")
    expect_m = re.search(r"^expect:\s*(.*)$", repro, re.M)
    expect = expect_m.group(1).strip() if expect_m else ""
    if repro.strip() and not expect:
        findings.append(
            "`## Reproduction` has no `expect:` line recording the expected failure string")

    test = t.test_file
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
            elif expect and expect not in out:
                # a red test proves nothing if it is red for a different reason
                # than the one reported -- that looks like evidence but isn't.
                # `expect` is body text an agent wrote, not frontmatter -- it
                # never passes validate_meta -- so it is shown via repr(), not
                # backtick-quoted, or a backtick/newline in it would corrupt the
                # markdown fence this finding gets written into.
                findings.append(
                    f"`{test}` fails, but its output does not mention the expected "
                    f"string {expect!r}\n```\n{out[-1200:]}\n```")
            else:
                findings.append(f"ok: `{test}` fails as required\n```\n{out[-1200:]}\n```")
                findings += _base_findings(project, cfg, wd, test, node)
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

    if not t.files_declared:
        findings.append("`files_declared` is empty")

    # `## Plan` must be an ordered step list, not judgment-graded prose --
    # `files_conflict()` trusts `files_declared`, and a plan that never says
    # which file each step touches is the plan that produced an untrustworthy
    # declaration in the first place. An empty `## Plan` is already caught by
    # REQUIRED_SECTIONS above; skip this check rather than double-report it.
    plan = secs.get("Plan", "")
    if plan.strip():
        steps: list[str] = []
        in_step = False
        for raw in plan.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if re.match(r"^\s*\d+[.)]", line):
                steps.append(line.strip())
                in_step = True
            elif in_step and re.match(r"^\s+\S", line):
                # a continuation of the previous step, not a step of its own
                steps[-1] += " " + line.strip()
            else:
                # body text an agent wrote -- repr(), not backtick-quoted, so a
                # backtick or newline in it cannot corrupt the finding's fence
                findings.append(
                    "plan line is not a numbered step -- the plan reads as "
                    f"prose: {line.strip()!r}")
                if not any(_cites(line, p) for p in t.files_declared):
                    findings.append(
                        f"plan line names no declared file: {line.strip()!r}")
                in_step = False
        if not steps:
            findings.append("`## Plan` has zero numbered steps")
        for s in steps:
            if not any(_cites(s, p) for p in t.files_declared):
                findings.append(f"plan step names no declared file: {s!r}")

    crit = secs.get("Acceptance criteria", "")
    for line in [l for l in crit.splitlines() if l.strip().startswith(("-", "*"))]:
        # a backticked token is not enough -- "`10ms`" is a metric, not a test
        if not re.search(r"\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/", line, re.I):
            findings.append(f"acceptance criterion names no test: {line.strip()}")

    failed = [f for f in findings if not f.startswith("ok:")]
    verdict = "PASS" if not failed else "FAIL"
    t.append("plan-validation", "gate", "**Tier A gate: %s**\n\n%s" % (
        verdict, "\n".join(f"- {f}" for f in findings) or "- (no checks ran)"),
        verdict=verdict)
    t.save()
    return not failed, failed
