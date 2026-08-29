"""Tier A gate -- deterministic, no LLM judgment anywhere in the path."""
import re
import shutil
import tempfile
from pathlib import Path

from pipeline.core.config import (NO_TESTS_RE, format_test_cmd,
                                  format_tests_cmd, project_config,
                                  selector_parts)
from pipeline.core.ticket import (FENCE_RE, Ticket, _fenced, active_decisions,
                                  decisions_dir, ticket_path)
from pipeline.core.worktree import base_checkout, base_ref, run_cmd

# `## Thread` is deliberately absent: it starts empty on every ticket and the
# gate itself is what first writes to it.
REQUIRED_SECTIONS = [
    "Summary", "Reproduction", "Digest", "Decisions checked",
    "Plan", "Acceptance criteria", "Rollback",
]

# A digest exists so the next stage does not re-explore the codebase, and
# "non-empty" is satisfied by one word. Three lines is a floor, not a quality
# bar -- a digest that is genuinely shorter says so out loud in a line a human
# can see in review, rather than being padded to hit a number.
MIN_DIGEST_ENTRIES = 3
DIGEST_SHORT_RE = re.compile(r"^\s*digest-short:\s*\S", re.M)
# Only `DEC-<digits>` is resolvable: that is what `record_decision()` writes and
# all `SAFE_DEC_ID` allows. A `TICKET-012` in this section is prose, not a citation.
DEC_ID_RE = re.compile(r"\bDEC-\d{1,6}\b")

# A bare `{test}` in `test_suite_without_new` substitutes every listed test
# space-joined, and `pytest --deselect a b` deselects `a` and SELECTS `b`.
BARE_PLACEHOLDER_RE = re.compile(r"[{](test|path|name|rest)[}]")

# The next two constants paraphrase `## Plan` in `pipeline/stages/planning.md`
# and must be changed together.
PLAN_STEP_RULE = (
    "a step starts with `N.` or `N)`, and a line that continues a step must "
    "be indented under it -- an unindented line reads as prose")
PLAN_FILE_RULE = (
    "spell the path out in the step (e.g. `pipeline/core/machine.py`) and "
    "declare that same path in `files_declared`")
# The one regex `gate()` and `plan_steps()` both use for "what is a step" --
# PLAN_STEP_RULE in prose, this in code.
PLAN_STEP_RE = re.compile(r"^\s*\d+[.)]")

# A criterion is a criterion in any list form -- `-`, `*`, `1.` or `1)`. The
# numbered markers are the same `\d+[.)]` the `## Plan` scan below accepts.
# The bullet arm stays a prefix match, not a marker plus whitespace: requiring
# `\s` after `-`/`*` would stop checking `**bold prose**` and `--- ` lines the
# gate checks today.
CRIT_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])")

# A total any other ticket can move (a suite's pass count, a row count) is
# not a property of this change, so a criterion that pins one copied straight
# out of `## Digest` goes stale the moment the number moves. Two digits is
# the floor: a one-digit number in a criterion is an exit code, an ordinal or
# a count of 1 far more often than a measured total, so a single-digit total
# goes unflagged on purpose. The lookarounds reject `2.1.238`, `gate.py:411`,
# `DEC-065` and `10ms` -- a version, a line reference, a decision id or a
# duration, none of them a count.
COUNT_RE = re.compile(r"(?<![\w.:/-])(\d{2,})(?![\w.:/-])")
# The count noun must FOLLOW the number: `630 passed` is a count, but
# `step 12` and `README.md line 65` are references, where the noun precedes
# the number. Measured over the 83 tickets in `.project/tickets` on
# 2026-08-28: 469 criteria, 27 flagged by any shared bare integer, 3 by this
# noun-after form -- all 3 the defect.
CRIT_COUNT_RE = re.compile(
    COUNT_RE.pattern + r"[^A-Za-z0-9]{0,3}(?:pass(?:ed|es|ing)|"
    r"fail(?:ed|s|ing|ures?)|tests?|cases?|rows?|lines?|entries|files?|"
    r"criteria|steps?|ok)\b", re.I)
# The waiver, spelled like DIGEST_SHORT_RE: some counts are legitimately
# pinned (e.g. a guard-case count a companion test asserts), and a hard
# reject would make that ticket unplannable.
COUNT_PINNED_RE = re.compile(r"^\s*count-pinned:\s*\S", re.M)
# Paraphrases `## Acceptance criteria` in `pipeline/stages/planning.md` and
# must be changed with it, like PLAN_STEP_RULE.
CRIT_COUNT_RULE = (
    "a total any other ticket can move is not a property of this change -- "
    "state it as a relation to a measured baseline, or re-measure at check "
    "time; one `count-pinned: <why it cannot move>` line in `## Acceptance "
    "criteria` waives this check")

# A criterion clears Tier A by naming a test, or by naming a command and the
# outcome running it must produce -- both halves are required, since a command
# with no stated result cannot be decided by running it. A one-token span
# (`` `10ms` ``, `` `gate.py` ``) is deliberately not a command: prose quotes an
# identifier or a metric constantly, so accepting a lone span would let an
# opinion like "the code is cleaner, see `gate.py`" through. The content class
# excludes a backtick, so a match never spans two separate code spans.
CRIT_CMD_RE = re.compile(r"`[A-Za-z_./][\w.+/-]*\s+\S[^`\n]*`")
CRIT_OUTCOME_RE = re.compile(
    r"\b(prints?|outputs?|reports?|returns?|exits?|shows?|lists?|finds?|"
    r"contains?|passes|fails|succeeds|empty|nothing|none|green|clean|zero|"
    r"no output|exit (?:code|status))\b", re.I)
CRIT_RULE = ("name a test, or name a command in backticks together with the "
             "output or exit status running it must produce")

# Each regex refuses one shape of token that cannot recur by construction --
# not every value that merely looks unstable. No bare-integer (pid) rule:
# TICKET-076's reported pid sits inside a temp path already caught below, and
# a standalone integer is as likely a count, a line number or an exit status.
_TMP_DIRS = ["/tmp", "/var/tmp", "/var/folders", "/private/var/folders",
             tempfile.gettempdir()]
TMP_PATH_RE = re.compile(
    r"(?:%s)/\S+" % "|".join(
        sorted({re.escape(d.rstrip("/")) for d in _TMP_DIRS}, key=len, reverse=True)))
# ` at 0x` is the CPython repr shape (`<Foo object at 0x7f...>`); anchoring on
# it keeps a literal constant like `0xdeadbeef` legal.
HEX_ADDR_RE = re.compile(r"\bat 0x[0-9a-fA-F]{4,}")
# Anchored at the end: an ellipsis is only the truncation marker a reporter
# added when it appears where the string stops, not wherever it appears.
ELLIPSIS_RE = re.compile(r"(?:\.\.\.|…)['\")\]}]*\s*$")
ESCAPE_RE = re.compile(r"\\[nrt]")

UNMATCHABLE_MARK = "`## Reproduction` `expect:` cannot recur"

# An allowlist, not a blocklist: a finding whose opener is not listed here
# reads as substantive, which is what every finding did before this ticket.
# `startswith`, never `in` -- a substantive finding can carry a fenced block
# of captured test output, and that output can quote a structural finding's
# text verbatim, so a substring match could be faked by a ticket's own test
# output into buying a free `plan-validation` attempt.
STRUCTURAL_MARKS = (
    "section `## ",
    "`## Digest` has ",
    "`## Reproduction` has no `expect:` line",
    "`## Decisions checked` cites",
    "`files_declared` is empty",
    "`## Plan` has zero numbered steps",
    "plan line is not a numbered step",
    "plan line names no declared file",
    "plan step names no declared file",
    "acceptance criterion names no test",
    "acceptance criterion pins an absolute count",
    UNMATCHABLE_MARK,  # DEC-065: a new structural finding needs its own mark
)


def unmatchable(expect: str) -> str | None:
    """Why `expect` can never match a second run's output, or `None` if it
    might. Only tokens that cannot recur by construction are listed here --
    see the comment above `_TMP_DIRS` for why there is no bare-integer rule."""
    m = TMP_PATH_RE.search(expect)
    if m:
        return (f"{m.group(0)!r} is a path under the system temp dir, and "
                 f"every one of those is minted fresh per run")
    m = HEX_ADDR_RE.search(expect)
    if m:
        return f"{m.group(0)!r} is an object address, and it changes every run"
    if ELLIPSIS_RE.search(expect):
        return ("it ends with an ellipsis, which is the truncation marker of "
                 "whatever printed the failure, not text the run emits")
    return None


def structural_only(failures: list[str]) -> bool:
    """Are every one of `failures` a structural (formatting) finding?

    Empty is False: no findings is a PASS, not this function's question.
    """
    return bool(failures) and all(f.startswith(STRUCTURAL_MARKS) for f in failures)


# A second `startswith` allowlist, same shape as `STRUCTURAL_MARKS` and for
# the same reason (DEC-065): a substantive finding can quote this text in a
# captured-output fence, and a substring match would let a ticket forge its
# own escalation.
ENVIRONMENT_MARK = "ENVIRONMENT: "
ENVIRONMENT_MARKS = (ENVIRONMENT_MARK,)


def environment_only(failures: list[str]) -> bool:
    """Are every one of `failures` an environment finding -- the suite red on
    base too, not this branch's doing?

    Empty is False: no findings is a PASS, not this function's question.
    """
    return bool(failures) and all(f.startswith(ENVIRONMENT_MARKS) for f in failures)


def _cites(text: str, path: str) -> bool:
    """Does `text` name `path`? Substring match, but anchored at a
    non-path/non-word boundary on both sides -- a plain `path in text` lets a
    short declared file (`io.py`) be "cited" by an unrelated one that merely
    contains it (`ratio.py`, `delegate.py` for `gate.py`)."""
    pat = r"(?<![\w./-])" + re.escape(path) + r"(?![\w-])"
    return re.search(pat, text) is not None


def _entry_ref(raw: str) -> str:
    return f"the `## Thread` entry `{raw}`"


def _ref(where: str) -> str:
    return f"*-- identical output, already quoted in {where} --*"


def plan_steps(plan: str) -> int:
    """The counting half of `PLAN_STEP_RULE`: how many numbered steps `plan`
    has, ignoring anything inside a fenced block. This is the source of
    `counters["plan_steps"]`."""
    raws = plan.splitlines()
    fenced = _fenced(raws)
    return sum(1 for i, line in enumerate(raws)
               if not fenced[i] and PLAN_STEP_RE.match(line))


def _blocks(text: str) -> list[tuple[int, int, str]]:
    """Every fenced block in `text` as `(first line index, one past the
    last, inner text)`, built on `_fenced()` per DEC-016 rather than a local
    scan for three backticks, which misses `~~~` and closes early on
    captured output that carries a fence of its own."""
    lines = text.splitlines()
    fenced = _fenced(lines)
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(lines):
        if not fenced[i]:
            i += 1
            continue
        start = i
        while i < len(lines) and fenced[i]:
            i += 1
        end = i
        inner = lines[start + 1:end]
        if inner and FENCE_RE.match(lines[end - 1]):
            inner = inner[:-1]
        out.append((start, end, "\n".join(inner)))
    return out


def _dedupe(text: str, seen: dict[str, str], where: str) -> str:
    """Replace every fenced block whose inner text is already a key of
    `seen` with a one-line reference to the entry that carries it. The first
    copy of a given body stays verbatim; a blank body keeps its fence,
    because the reference line is longer than an empty block and would add
    noise, not save it."""
    lines = text.splitlines()
    out: list[str] = []
    last = 0
    for start, end, body in _blocks(text):
        out += lines[last:start]
        if not body.strip():
            out += lines[start:end]
        elif body in seen:
            out.append(_ref(seen[body]))
        else:
            out += lines[start:end]
            seen[body] = where
        last = end
    out += lines[last:]
    return "\n".join(out)


def _base_verdict(test: str, node: str, base: str, code: int, out: str) -> tuple[bool, str]:
    """One listed test's verdict on base. Split out of `_base_findings()`
    so a list of tests shares one checkout and one copy pass. The bool is
    True exactly when this test FAILS on base."""
    if code == 0:
        # The branch run's ambiguity (TICKET-071), on base: the bug is already
        # fixed there, or the test is red for a reason base does not have, or
        # the selector matched no test. Base proves nothing either way.
        return False, (f"`{test}` exited 0 on base `{base}`, so base proves nothing. "
                f"Either it PASSES there -- the bug is already fixed on base, "
                f"or the test is red for a reason base does not have -- or "
                f"`test_one` matched no test at all; a runner that names a "
                f"node only on failure makes the two identical here"
                f"\n```\n{out[-1200:]}\n```")
    if node not in out:
        # same trap as the branch run: an import error exits non-zero too,
        # and here that reads as a successful reproduction
        return False, (f"`{test}` exited non-zero on base `{base}` but its name "
                f"never appears in the output -- it errored rather than "
                f"failed, so base proves nothing\n```\n{out[-1200:]}\n```")
    return True, (f"ok: `{test}` fails on base `{base}` too -- the bug is not "
            f"already fixed upstream\n```\n{out[-1200:]}\n```")


def _unsafe_rel(tests: list[str]) -> str | None:
    """The first of `tests` whose file half is not a plain relative path, or
    `None`. SAFE_TEST bans shell metacharacters, not traversal -- and unlike
    the branch run, which only reads, copying onto a base checkout WRITES
    the path."""
    for test in tests:
        rel = test.split("::")[0]
        if ".." in rel or rel.startswith("/"):
            return test
    return None


def _copy_tests(wd: Path, base_wt: Path, tests: list[str]) -> None:
    """Copy each test file `tests` names, from `wd` onto `base_wt`, once per
    distinct file even when several node ids share it."""
    for rel in dict.fromkeys(x.split("::")[0] for x in tests):
        dst = base_wt / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(wd / rel, dst)


def _base_findings(project: Path, cfg: dict, wd: Path,
                   tests: list[str]) -> tuple[list[str], dict[str, str]]:
    """A test that fails in the ticket's worktree proves the bug is HERE.
    Tier A wants more: that it fails on BASE, which is what makes it a
    reproduction rather than a branch that broke itself. The test itself
    only exists on the branch, so the branch's test file is copied onto a
    throwaway checkout of base: the branch's test, base's code. Every test
    the ticket lists shares that one checkout, and each is re-run on its
    own -- one run of two tests could not say which of them failed.

    Returns the findings list, plus a dict mapping each test that FAILS on
    base to that base run's output. Membership of the dict is the durable
    proof the bug is upstream, and the output is what `expect:` is matched
    against for a test that already passes in the ticket's worktree."""
    if wd.resolve() == project.resolve():
        return (["ok: base check skipped -- no ticket worktree was given, so "
                "there is no branch to compare against base"], {})
    unsafe = _unsafe_rel(tests)
    if unsafe:
        # SAFE_TEST bans shell metacharacters, not traversal -- and unlike
        # the branch run, which only reads, this one WRITES the path.
        return ([f"`{unsafe}` is not a plain relative path -- refusing to copy "
                f"it into a checkout of base"], {})
    base = base_ref(cfg)
    named = " ".join(f"`{x}`" for x in tests)
    verdicts = []
    on_base: dict[str, str] = {}
    with base_checkout(project, cfg) as (base_wt, err):
        if base_wt is None:
            return ([f"could not check out base `{base}` to re-run {named}"
                    f"\n```\n{err[-1200:]}\n```"], {})
        _copy_tests(wd, base_wt, tests)
        for test in tests:
            code, out = run_cmd(format_test_cmd(cfg["test_one"], test), base_wt)
            hit, verdict = _base_verdict(test, test.split("::")[-1], base, code, out)
            verdicts.append(verdict)
            if hit:
                on_base[test] = out
    return verdicts, on_base


# `test_suite_without_new` exiting non-zero is pre-existing breakage only when
# the run produced evidence it ran. A shell syntax error exits 2 with no test
# result and used to read as breakage in the project's own tests (TICKET-074).
# pytest, go test, jest, unittest and rspec exit 1 on a failing test; cargo
# exits 101. The regex is the fallback for a runner that exits with its own
# failure count -- mocha exits 3 on three failures.
SUITE_FAILED_CODES = (1, 101)
SUITE_RAN_RE = re.compile(
    r"\b\d+\s+(?:failed|failing|passed|passing|errors?|skipped)\b"
    r"|\bran\s+\d+\s+tests?\b"
    r"|\btest result:"
    r"|^(?:---\s+)?FAIL\b", re.M | re.I)


def suite_ran(code: int, out: str) -> bool:
    """True when a non-zero suite run produced evidence it ran tests.

    False is the safe answer: it makes `gate()` report "could not run"
    instead of asserting breakage nobody observed.

    `NO_TESTS_RE` (DEC-068) vetoes first. `pytest`'s collection error exits 2
    printing `collected 0 items / 1 error`, and `1 error` matches the count
    regex, so without the veto a suite that collected nothing reads as red.
    """
    if NO_TESTS_RE.search(out):
        return False
    return code in SUITE_FAILED_CODES or bool(SUITE_RAN_RE.search(out))


def _base_suite(project: Path, cfg: dict, wd: Path,
                 tests: list[str]) -> tuple[str | None, str]:
    """Re-run `test_suite_without_new` on a throwaway checkout of base.
    Returns `(output, "")` when the suite RAN and FAILED there too --
    evidence the breakage is not this branch's doing. Returns `(None, why)`
    otherwise, where `why` is empty when the suite is simply not red on base
    and non-empty when the question is unproven (no worktree, an unsafe test
    path, a base checkout that fails, or a run with no evidence it happened)
    -- callers fail closed on a non-empty `why`."""
    if wd.resolve() == project.resolve():
        return None, ("no ticket worktree was given, so there is no branch "
                       "to compare against base")
    bad = _unsafe_rel(tests)
    if bad:
        return None, f"`{bad}` is not a plain relative path"
    base = base_ref(cfg)
    with base_checkout(project, cfg) as (base_wt, err):
        if base_wt is None:
            return None, f"base `{base}` could not be checked out: {err[-200:]}"
        _copy_tests(wd, base_wt, tests)
        code, out = run_cmd(format_tests_cmd(cfg["test_suite_without_new"], tests), base_wt)
    if code != 0 and suite_ran(code, out):
        return out, ""
    if code == 0:
        return None, ""
    return None, f"the suite exited {code} on base `{base}` and reported no test result"


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

    # An empty `## Digest` is already reported above; skip rather than double-report.
    dig = secs.get("Digest", "")
    if dig.strip() and not DIGEST_SHORT_RE.search(dig):
        entries = [l for l in dig.splitlines() if l.strip()]
        if len(entries) < MIN_DIGEST_ENTRIES:
            findings.append(
                f"`## Digest` has {len(entries)} non-empty line(s); want at least "
                f"{MIN_DIGEST_ENTRIES} (files touched, key functions, entry points, "
                f"gotchas) or one `digest-short: <why fewer>` line")

    # The gate proves a bug exists by running a test that fails; it must also
    # prove that failure is the *reported* one, or a test failing for an
    # unrelated reason sails through looking like evidence.
    repro = secs.get("Reproduction", "")
    expect_m = re.search(r"^expect:\s*(.*)$", repro, re.M)
    expect = expect_m.group(1).strip() if expect_m else ""
    if repro.strip() and not expect:
        findings.append(
            "`## Reproduction` has no `expect:` line recording the expected failure string")
    bad = unmatchable(expect) if expect else None
    if bad:
        findings.append(
            f"{UNMATCHABLE_MARK}: {bad} -- trim it to the part of the failure "
            f"that is the same on every run. Got: {expect!r}")

    tests = t.tests
    if not tests:
        findings.append("no `test_file` recorded in frontmatter")
    else:
        runnable = []
        for test in tests:
            test_path = wd / test.split("::")[0]
            if not test_path.is_file():
                findings.append(f"test file {test_path} does not exist")
            else:
                runnable.append(test)
        # `reproduced`, not `failed`: `gate()` binds that name below for
        # the findings that decide the verdict.
        reproduced: list[tuple[str, str]] = []
        # exit 0 in the worktree carries no evidence of its own; the base run
        # below decides it
        passing: list[tuple[str, str]] = []
        for test in runnable:
            code, out = run_cmd(format_test_cmd(cfg["test_one"], test), wd)
            node = test.split("::")[-1]
            if code == 0:
                passing.append((test, out))
            elif node not in out:
                # a missing dependency or an import error exits non-zero too, and
                # looks exactly like a failing test unless you check for the name
                findings.append(
                    f"`{test}` exited non-zero but its name never appears in the "
                    f"output -- it errored rather than failed\n```\n{out[-1200:]}\n```")
            else:
                reproduced.append((test, out))
        # base does not carry the branch's fix, so its verdict does not depend
        # on the branch's current state; a ticket resumed to `plan-validation`
        # after `implementing` landed the fix has a worktree where `test_file`
        # now PASSES, and the run must reach base before `expect:` is judged,
        # because base's output is the only failing output such a test has
        # (TICKET-090).
        base: list[str] = []
        on_base: dict[str, str] = {}
        candidates = [x for x, _ in reproduced + passing]
        if passing:
            base, on_base = _base_findings(project, cfg, wd, candidates)
        # `expect:` is ONE line of the ticket, and two tests covering two code
        # paths fail with two different strings, so it must appear in at least
        # one of them -- see `## Decisions`. The per-test guarantee above is
        # the strong one and is unchanged: every listed test exits non-zero
        # AND prints its own node name. For a test that already passes here,
        # the failing output `expect:` is checked against is base's.
        matched = (not expect or any(expect in o for _, o in reproduced)
                   or any(expect in on_base.get(t, "") for t, _ in passing))
        for test, out in passing:
            if test not in on_base:
                # Exit 0 has two causes and no portable signal separates them: a
                # runner names a node only when the test FAILS (pytest prints a dot
                # and a count), so a real pass and a selector that matched no test
                # look identical -- TICKET-071, which inverted TICKET-064's split.
                # Both are a gate failure; the fence is what tells a human which.
                findings.append(
                    f"`{test}` exited 0 -- it must fail before implementation. Either "
                    f"it PASSES, or `test_one` matched no test at all; a runner that "
                    f"names a node only on failure makes the two identical here. Read "
                    f"the output to tell them apart\n```\n{out[-1200:]}\n```")
            elif matched or bad:
                findings.append(
                    f"ok: `{test}` exited 0 here and fails on base `{base_ref(cfg)}` "
                    f"-- the branch already carries the fix, and base is where the "
                    f"reproduction still holds")
            else:
                findings.append(
                    f"`{test}` exited 0 here and fails on base `{base_ref(cfg)}`, "
                    f"but base's output does not mention the expected string "
                    f"{expect!r}\n```\n{on_base[test][-1200:]}\n```")
        for test, out in reproduced:
            if matched:
                findings.append(f"ok: `{test}` fails as required\n```\n{out[-1200:]}\n```")
            elif bad:
                # step 4 already reported why `expect` cannot recur -- a second,
                # substantive finding here would make the list read as mixed and
                # charge `plan_validation_attempts` instead of the structural
                # counter (DEC-065).
                findings.append(
                    f"ok: `{test}` fails; its output is not checked against an "
                    f"`expect:` that cannot recur\n```\n{out[-1200:]}\n```")
            elif ESCAPE_RE.search(expect):
                # a literal backslash-`n` in `expect` is undecidable on its own:
                # pytest reprs a string holding a real newline the same way, so
                # this fires only once the grep has already missed -- see
                # `## Decisions`.
                findings.append(
                    f"{UNMATCHABLE_MARK}: it holds a literal backslash escape "
                    f"where the run's output holds a control character, and "
                    f"`{test}`'s output does not contain it either way -- trim "
                    f"it to the part before the escape. Got: {expect!r}")
            else:
                # a red test proves nothing if it is red for a different reason
                # than the one reported -- that looks like evidence but isn't.
                # `expect` is body text an agent wrote, not frontmatter -- it
                # never passes validate_meta -- so it is shown via repr(), not
                # backtick-quoted, or a backtick/newline in it would corrupt the
                # markdown fence this finding gets written into.
                findings.append(
                    f"`{test}` fails, but its output does not mention the expected "
                    f"string {expect!r}\n```\n{out[-1200:]}\n```")
        if not passing and matched and reproduced:
            # a non-empty `passing` already paid for the one checkout above,
            # so this arm covers only the ordinary case where every listed
            # test failed in the worktree.
            base, _ = _base_findings(project, cfg, wd, candidates)
        findings += base
        if runnable:
            names = " ".join(f"`{x}`" for x in runnable)
            bare = next((m for m in BARE_PLACEHOLDER_RE.finditer(
                cfg["test_suite_without_new"])
                if len({selector_parts(x)[m.group(1)] for x in runnable}) > 1), None)
            if bare:
                findings.append(
                    f"`test_suite_without_new` substitutes a bare `{bare.group(0)}` "
                    f"and this ticket names {len(runnable)} tests -- a flag that "
                    f"takes one value at a time excludes only the first, and the "
                    f"rest come back as pre-existing breakage. Write "
                    f"`{{{bare.group(1)}:<flag> }}` (pytest: "
                    f"`pytest {{test:--deselect }}`) in `.project/pipeline.toml`, "
                    f"or `{{{bare.group(1)}:}}` if the runner takes them all "
                    f"after one flag")
            else:
                suite_cmd = format_tests_cmd(cfg["test_suite_without_new"], runnable)
                code, out = run_cmd(suite_cmd, wd)
                if code != 0 and suite_ran(code, out):
                    base_out, why = _base_suite(project, cfg, wd, runnable)
                    if base_out is not None:
                        findings.append(
                            f"{ENVIRONMENT_MARK}suite excluding {names} is RED -- "
                            f"pre-existing breakage, and it is RED on base "
                            f"`{base_ref(cfg)}` too, so it is not this branch's "
                            f"doing and no plan can fix it. Fix the environment "
                            f"or base itself, then `pipeline resume {tid}`"
                            f"\n```on base\n{base_out[-1200:]}\n```"
                            f"\n```in the ticket's worktree\n{out[-1200:]}\n```"
                        )
                    elif not why:
                        findings.append(
                            f"suite excluding {names} is RED -- pre-existing breakage, "
                            f"fix that first\n```\n{out[-1200:]}\n```"
                        )
                    else:
                        findings.append(
                            f"suite excluding {names} is RED -- pre-existing breakage, "
                            f"fix that first\n```\n{out[-1200:]}\n```"
                            f"\n(base was not consulted: {why})"
                        )
                elif code != 0:
                    findings.append(
                        f"could not run the suite excluding {names}: {suite_cmd!r} "
                        f"exited {code} and reported no test result, so pre-existing "
                        f"breakage is neither proven nor ruled out -- fix "
                        f"`test_suite_without_new` in `.project/pipeline.toml`"
                        f"\n```\n{out[-1200:]}\n```")

    dec = secs.get("Decisions checked", "")
    cited = sorted(set(DEC_ID_RE.findall(dec)))
    if dec and "none relevant" not in dec.lower() and not cited:
        findings.append("`## Decisions checked` cites no decision IDs and no explicit "
                        "'none relevant' + grep terms")
    if cited:
        ddir = decisions_dir(project)
        # A symlinked record is not a record -- active_decisions() skips it, so
        # counting it as on-disk would report a planted link as merely superseded.
        on_disk = ({p.stem for p in ddir.glob("DEC-*.md") if not p.is_symlink()}
                   if ddir.is_dir() else set())
        active = {d.id for d in active_decisions(project)}
        for cid in cited:
            if cid not in on_disk:
                findings.append(
                    f"`## Decisions checked` cites {cid}, which is not a record in "
                    f"{ddir} -- a citation nobody can resolve is not a check")
            elif cid not in active:
                # a superseded record stays on disk as history; citing one is fine,
                # treating it as binding is the thing the plan must not do
                findings.append(f"ok: {cid} is superseded -- history, not binding")

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
        raws = plan.splitlines()
        # `_fenced()` and not a local scan: it is what `sections()` already
        # uses to split THIS file, so a second opinion on what counts as code
        # would let the gate and the section splitter disagree. It carries
        # CommonMark's rules -- `~~~` as well as backticks, a closing fence at
        # least as long as its opener, and `^ {0,3}`, so a fence indented four
        # spaces is not a fence at all but a continuation of the step above,
        # which is the form PLAN_STEP_RULE tells the writer to use.
        fenced = _fenced(raws)
        i = 0
        while i < len(raws):
            line = raws[i].rstrip()
            if fenced[i]:
                opener = raws[i]
                while i < len(raws) and fenced[i]:
                    i += 1
                # Indented under a step, at ANY depth, is the continuation form
                # PLAN_STEP_RULE asks for -- absorb it silently. `FENCE_RE` is
                # `^ {0,3}`, so three spaces still opens a real fence: without
                # this branch a plan that took the rule's advice failed with a
                # finding telling it to do what it had already done, and
                # `plan_validation_attempts` ran out on the re-try.
                #
                # At column 0 it is a violation, reported ONCE for the block.
                # Reporting per line put 262 findings in TICKET-031's thread,
                # which every later stage reads through `stage_view()`. Never
                # skip it SILENTLY, which was tried: a numbered step hidden in
                # a fence reaches `implementing` -- which reads the section
                # whole -- unchecked against `files_declared`, the declaration
                # `files_conflict()` trusts to keep two tickets off one file.
                #
                # `in_step` survives either way. Clearing it made the line
                # AFTER the block read as fresh prose, so one fence produced
                # three findings rather than the one this branch promises.
                if not (in_step and opener[:1].isspace()):
                    findings.append(
                        "plan line is not a numbered step -- the plan reads as "
                        f"prose: {opener.strip()!r} -- {PLAN_STEP_RULE}")
                continue
            i += 1
            if not line.strip():
                continue
            if PLAN_STEP_RE.match(line):
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
                    f"prose: {line.strip()!r} -- {PLAN_STEP_RULE}")
                if not any(_cites(line, p) for p in t.files_declared):
                    findings.append(
                        f"plan line names no declared file: {line.strip()!r} "
                        f"-- {PLAN_FILE_RULE}")
                in_step = False
        if not steps:
            findings.append(
                f"`## Plan` has zero numbered steps -- {PLAN_STEP_RULE}")
        for s in steps:
            if not any(_cites(s, p) for p in t.files_declared):
                findings.append(
                    f"plan step names no declared file: {s!r} -- {PLAN_FILE_RULE}")

    crit = secs.get("Acceptance criteria", "")
    crit_lines = crit.splitlines()
    crit_fenced = _fenced(crit_lines)
    crits: list[str] = []
    in_crit = False
    for i, raw in enumerate(crit_lines):
        if not raw.strip():
            continue
        # A fenced block indented under a criterion joins onto it, per
        # DEC-016 (`_fenced()` is the one parse of fence state). A fence at
        # column 0 is quoted output, not a criterion -- skip it with no
        # finding, unlike the `## Plan` scan, because a hidden bullet here
        # evades nothing the way a hidden numbered step would.
        if crit_fenced[i]:
            if in_crit and raw[:1].isspace():
                crits[-1] += " " + raw.strip()
            continue
        # The continuation arm runs BEFORE the marker arm, the opposite order
        # to the `## Plan` scan above: `CRIT_ITEM_RE` matches a bare leading
        # `-`, so an indented continuation beginning `--porcelain` would still
        # read as a criterion of its own if the marker arm ran first. That
        # exact shape escalated TICKET-036.
        if in_crit and re.match(r"^\s+\S", raw):
            crits[-1] += " " + raw.strip()
        elif CRIT_ITEM_RE.match(raw):
            crits.append(raw.strip())
            in_crit = True
        else:
            in_crit = False
    # A separate loop, never folded into the one below: both accept arms of
    # that loop `continue` on a criterion that names a test or a command, so
    # a check appended there would only ever see criteria that already fail
    # the names-no-test rule. Pinning a stale total and naming a test are
    # orthogonal properties -- a criterion can do both.
    dig_counts = set(COUNT_RE.findall(dig))
    if dig_counts and not COUNT_PINNED_RE.search(crit):
        for c in crits:
            shared = sorted(set(CRIT_COUNT_RE.findall(c)) & dig_counts, key=int)
            if shared:
                findings.append(
                    "acceptance criterion pins an absolute count copied "
                    f"from `## Digest` ({', '.join(shared)}): {c} -- {CRIT_COUNT_RULE}")
    for c in crits:
        # a backticked token is not enough -- "`10ms`" is a metric, not a test.
        # `pytest` is named explicitly: `\btest` needs a word boundary before
        # `test`, and `py` is a word character, so "run `pytest -q`" -- the
        # whole-suite criterion `CLAUDE.md` itself writes -- matched nothing.
        # It cost TICKET-041 a plan-validation attempt on a plan the gate had
        # no other complaint about. Not `\btest` without the boundary: that
        # matches `latest`, `greatest`, `contest`.
        if re.search(r"\bpytest\b|\btest[_a-zA-Z0-9]*\b|::|\b\w+_test\b|\btests?/",
                     c, re.I):
            continue
        if CRIT_CMD_RE.search(c) and CRIT_OUTCOME_RE.search(c):
            continue
        findings.append(f"acceptance criterion names no test: {c} -- {CRIT_RULE}")

    seen: dict[str, str] = {}
    for e in t.thread():
        for _, _, body in _blocks(e.text):
            if body.strip():
                seen.setdefault(body, _entry_ref(e.raw))
    findings = [_dedupe(f, seen, "this entry, above") for f in findings]

    failed = [f for f in findings if not f.startswith("ok:")]
    verdict = "PASS" if not failed else "FAIL"
    t.append("plan-validation", "gate", "**Tier A gate: %s**\n\n%s" % (
        verdict, "\n".join(f"- {f}" for f in findings) or "- (no checks ran)"),
        verdict=verdict)
    t.save()
    here = _entry_ref(t.thread()[-1].raw)
    mine = {body: here for f in findings for _, _, body in _blocks(f) if body.strip()}
    return not failed, [_dedupe(f, mine, here) for f in failed]
