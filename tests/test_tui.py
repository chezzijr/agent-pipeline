"""The TUI, driven by Textual's own pilot. No daemon, no socket, no sleeps.

`asyncio.run` rather than an async pytest plugin: `run_test()` is the only
async thing in the repo and it is not worth a dependency.
"""
import asyncio

from textual.widgets import Tree

from helpers import project as make_project
from pipeline.core import PipelineError
from pipeline.core.ticket import Ticket
from pipeline.tui.app import PipelineApp, event_line, marker

APPROVABLE = """---
id: TICKET-001
stage: awaiting-approval
class: bugfix
branch: ticket/001
test_file: test_thing.py::test_broken
files_declared: [thing.py]
counters: {}
lease: {holder: null, expires: null}
---

## Summary
x
## Plan
1. do it
## Thread
"""


class FakeClient:
    """The only reason `client` is a constructor argument.

    `ls` answers with whatever it was last handed, so a test can move the world
    and then make the app look again. `clone()` refuses, which is how the
    subscription worker stays out of the tests: the app treats a stream it
    cannot open as "no live events" and carries on.
    """

    def __init__(self, rows):
        self.rows = rows
        self.sent = []

    def request(self, op, **kw):
        self.sent.append(op)
        if op == "ls":
            return self.rows
        if op == "kill":
            return {"ticket": kw["ticket"], "project": kw["project"], "pid": 4242}
        raise PipelineError(f"fake client has no {op}")

    def clone(self, timeout=None):
        raise OSError("no stream in tests")

    def close(self):
        pass


def row(project, tid, stage, **kw):
    return {"project": str(project), "id": tid, "stage": stage, "class": "bugfix",
            "counters": {}, "lease": {}, "running": False, "leased": False,
            "stale": False, "last_session": None, "mode": "batch",
            "title": "a thing", **kw}


def labels(app):
    """{project label: [ticket labels]} -- what the tree actually shows."""
    root = app.query_one(Tree).root
    return {str(n.label): [str(c.label) for c in n.children] for n in root.children}


def test_tui_renders_tree_from_ls():
    async def go():
        app = PipelineApp(client=FakeClient([
            row("/tmp/alpha", "TICKET-001", "planning", running=True),
            row("/tmp/alpha", "TICKET-002", "awaiting-approval"),
            row("/tmp/beta", "TICKET-003", "implementing"),
        ]))
        async with app.run_test() as pilot:
            got = labels(app)
            assert list(got) == ["alpha", "beta"], got
            assert got["alpha"] == ["TICKET-001 planning *",
                                    "TICKET-002 awaiting-approval !"], got
            assert got["beta"] == ["TICKET-003 implementing"], got
            await pilot.press("q")
        assert app.return_code == 0

    asyncio.run(go())


def test_an_event_reseeds_the_tree_and_a_dropped_marker_says_so():
    """The two ways the tree stays in sync: a structural event refreshes it,
    and a `dropped` marker -- the daemon admitting it binned part of our
    backlog -- refreshes it *and* says so, because patching forward from events
    we know are missing is how a dashboard starts lying."""
    async def go():
        fake = FakeClient([row("/tmp/alpha", "TICKET-001", "planning")])
        app = PipelineApp(client=fake)
        async with app.run_test() as pilot:
            assert labels(app)["alpha"] == ["TICKET-001 planning"]

            fake.rows = [row("/tmp/alpha", "TICKET-001", "implementing",
                             running=True)]
            app.on_frame({"sub": 1, "event": {"project": "/tmp/alpha",
                                              "ticket": "TICKET-001",
                                              "kind": "transition", "data": {}}})
            await pilot.pause()
            assert labels(app)["alpha"] == ["TICKET-001 implementing *"]

            fake.rows = [row("/tmp/alpha", "TICKET-001", "escalated")]
            app.on_frame({"sub": 1, "dropped": 7})
            await pilot.pause()
            assert labels(app)["alpha"] == ["TICKET-001 escalated"]
            assert app.dropped == 7
            assert "7 events dropped" in str(app.query_one("#status").render())

            # chatter must not cost a rebuild
            before = fake.sent.count("ls")
            app.on_frame({"sub": 1, "event": {"kind": "assistant", "data": {}}})
            await pilot.pause()
            assert fake.sent.count("ls") == before

    asyncio.run(go())


def test_approve_rewrites_the_ticket_file_with_no_daemon_op():
    """`a` is four keybindings' worth of proof: it mutates the ticket file the
    daemon reads, and never touches the socket."""
    async def go():
        d = make_project(APPROVABLE)
        fake = FakeClient([row(d, "TICKET-001", "awaiting-approval")])
        app = PipelineApp(client=fake)
        async with app.run_test() as pilot:
            app.query_one(Tree).focus()
            await pilot.press("down", "down")     # root -> project -> the ticket
            assert app.selected == (str(d), "TICKET-001")
            fake.sent.clear()
            await pilot.press("a")
            await pilot.pause()
            assert Ticket.find(d, "TICKET-001").stage == "revalidating"
            assert fake.sent == ["ls"]            # the refresh, and nothing else

    asyncio.run(go())


def test_a_wrong_stage_refuses_without_taking_the_app_down():
    """`cmd_approve` calls `die()`, which is `sys.exit`. Reusing the CLI's
    precondition means catching its exit rather than copying its check."""
    async def go():
        d = make_project()                        # stage: plan-validation
        app = PipelineApp(client=FakeClient([row(d, "TICKET-001",
                                                 "plan-validation")]))
        async with app.run_test() as pilot:
            app.query_one(Tree).focus()
            await pilot.press("down", "down")
            await pilot.press("a")
            await pilot.pause()
            assert app.is_running
            assert Ticket.find(d, "TICKET-001").stage == "plan-validation"
            await pilot.press("q")
        assert app.return_code == 0

    asyncio.run(go())


def test_event_line_never_raises_on_a_kind_it_does_not_know():
    assert event_line({"kind": "stage_start", "data": {"model": "opus"}}) == \
        "[stage_start] model=opus"
    assert "hello" in event_line({"kind": "assistant",
                                  "data": {"text": "hello", "thinking": "",
                                           "tools": []}})
    # a stream kind with a payload that is missing half its keys
    assert event_line({"kind": "result", "data": {}}).startswith("[result]")
    assert event_line({}) == "[?] "


def test_marker_is_one_glyph():
    assert marker({"running": True, "stage": "planning"}) == "*"
    assert marker({"stage": "needs-input"}) == "!"
    assert marker({"stage": "planning", "stale": True}) == "?"
    assert marker({"stage": "planning"}) == ""
