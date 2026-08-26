"""The TUI, driven by Textual's own pilot. No daemon, no socket, no sleeps.

`asyncio.run` rather than an async pytest plugin: `run_test()` is the only
async thing in the repo and it is not worth a dependency.
"""
import asyncio
import base64

from textual.widgets import Tree

from helpers import project as make_project
from pipeline.core import PipelineError
from pipeline.core.ticket import Ticket
from pipeline.daemon.server import PTY_INPUT
from pipeline.pty.host import Screen
from pipeline.tui.app import (MAX_TAIL, PipelineApp, event_line, marker,
                              render_pty, tail_log)

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


async def select(app, pilot, project, tid):
    """Move the cursor straight to a ticket's node, by identity.

    `press("down", "down")` cannot select a row the cursor already sits on --
    re-selecting it must still fire a highlight, which a repeated key press
    cannot do once the tree opens on the first live ticket.
    """
    tree = app.query_one(Tree)
    node = next(c for n in tree.root.children for c in n.children
                if c.data == (str(project), tid))
    tree.move_cursor(None)
    tree.move_cursor(node)
    await pilot.pause()


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


def test_finished_tickets_do_not_bury_live_ones():
    """A project with many finished tickets and one live ticket should show
    the live ticket first, not last -- sorting by id alone buries it behind
    every earlier, finished ticket and forces a scroll to reach it."""
    async def go():
        rows = [row("/tmp/alpha", f"TICKET-{n:03d}", "done")
                for n in range(1, 51)]
        rows.append(row("/tmp/alpha", "TICKET-060", "implementing",
                        running=True))
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            got = labels(app)["alpha"]
            assert got[0].startswith("TICKET-060"), got[:3]
            await pilot.press("q")
        assert app.return_code == 0

    asyncio.run(go())


def test_the_cursor_opens_on_a_live_ticket():
    """The tree hides finished tickets by default, so the cursor must open on
    the first ticket that is not terminal, not on the root."""
    async def go():
        d = "/tmp/alpha"
        rows = [row(d, "TICKET-001", "done"), row(d, "TICKET-002", "done"),
                row(d, "TICKET-003", "awaiting-approval")]
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.selected == (d, "TICKET-003")

    asyncio.run(go())


def test_the_f_key_toggles_finished_tickets_back_into_the_tree():
    """`done` and `rejected` hide by default; `escalated` never hides. `f`
    brings them all back, and the status line says how many are hidden."""
    async def go():
        d = "/tmp/alpha"
        rows = [row(d, "TICKET-001", "done"), row(d, "TICKET-002", "rejected"),
                row(d, "TICKET-003", "escalated"),
                row(d, "TICKET-004", "implementing", running=True)]
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            assert labels(app)["alpha"] == ["TICKET-003 escalated",
                                            "TICKET-004 implementing *"]
            assert "2 finished hidden (f)" in status(app), status(app)

            await pilot.press("f")
            await pilot.pause()
            assert labels(app)["alpha"] == ["TICKET-001 done",
                                            "TICKET-002 rejected",
                                            "TICKET-003 escalated",
                                            "TICKET-004 implementing *"]
            assert "hidden" not in status(app), status(app)

            await pilot.press("f")
            await pilot.pause()
            assert labels(app)["alpha"] == ["TICKET-003 escalated",
                                            "TICKET-004 implementing *"]

    asyncio.run(go())


def test_the_down_key_moves_the_cursor_off_the_opening_row():
    """One `down` press still moves the cursor, over two live rows instead of
    a walk up from the root."""
    async def go():
        d = "/tmp/alpha"
        rows = [row(d, "TICKET-001", "implementing", running=True),
                row(d, "TICKET-002", "awaiting-approval")]
        app = PipelineApp(client=FakeClient(rows))
        async with app.run_test() as pilot:
            app.query_one(Tree).focus()
            await pilot.pause()
            assert app.selected == (d, "TICKET-001")

            await pilot.press("down")
            await pilot.pause()
            assert app.selected == (d, "TICKET-002")

    asyncio.run(go())


def test_a_selected_ticket_stays_in_the_tree_when_it_finishes():
    """The row under the cursor stays painted after it turns terminal, so the
    detail pane you are reading does not lose its row out from under you."""
    async def go():
        d = "/tmp/alpha"
        fake = FakeClient([row(d, "TICKET-001", "implementing", running=True)])
        app = PipelineApp(client=fake)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.selected == (d, "TICKET-001")

            fake.rows = [row(d, "TICKET-001", "done")]
            app.on_frame({"sub": 1, "event": {"project": d, "ticket": "TICKET-001",
                                              "kind": "transition", "data": {}}})
            await pilot.pause()
            assert labels(app)["alpha"] == ["TICKET-001 done"]
            assert app.selected == (d, "TICKET-001")

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
            await select(app, pilot, d, "TICKET-001")
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
            await select(app, pilot, d, "TICKET-001")
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


def test_marker_and_status_say_unknown_when_no_daemon_answered():
    assert marker({"running": None, "stage": "planning"}) == "~"
    assert marker({"running": None, "stage": "needs-input"}) == "!"
    assert marker({"stage": "unreadable"}) == ""
    assert marker({"running": True, "stage": "planning"}) == "*"


class FakeStream:
    """The subscription connection. `send` records and hands back the id the
    daemon will tag its frames with; frames come back through `on_frame`
    exactly as the reader thread delivers them."""

    def __init__(self):
        self.sent = []
        self._id = 0

    def send(self, op, **kw):
        self._id += 1
        self.sent.append((op, kw))
        return self._id

    def ops(self):
        return [op for op, _ in self.sent]


def pty_pane(app) -> str:
    return str(app.query_one("#pty").render())


def test_an_interactive_stage_attaches_and_a_dropped_frame_reattaches():
    """The seam TICKET-015 left and TICKET-013 filled the protocol for.

    A `dropped` marker means the daemon binned part of our pty backlog, so our
    emulator is now desynced from its authoritative pyte screen. Painting
    forward across that gap renders a corrupted terminal indefinitely; the fix
    is one round trip -- attach again and take the fresh snapshot.
    """
    async def go():
        d = "/tmp/alpha"
        fake = FakeClient([row(d, "TICKET-001", "planning", running=True,
                               mode="interactive")])
        app = PipelineApp(client=fake)
        async with app.run_test() as pilot:
            app.stream = FakeStream()          # the worker thread's socket
            app.query_one(Tree).focus()
            await select(app, pilot, d, "TICKET-001")
            await pilot.pause()

            assert app.attached == (d, "TICKET-001"), app.attached
            assert app.stream.ops() == ["attach"], app.stream.sent
            app.on_frame({"id": app.pty_id, "ok": True,
                          "data": {"screen": ["Allow Bash?", "> "], "rows": 4,
                                   "cols": 24, "writer": True}})
            await pilot.pause()
            assert "Allow Bash?" in pty_pane(app), pty_pane(app)

            # a live frame paints through our own emulator, not a re-request
            app.on_frame({"sub": app.pty_id,
                          "pty": base64.b64encode(b"\x1b[3;1Hyes").decode()})
            await pilot.pause()
            assert "yes" in pty_pane(app), pty_pane(app)
            assert "Allow Bash?" in pty_pane(app), \
                "the pre-attach screen was lost: the emulator started blank"
            assert app.stream.ops().count("attach") == 1, app.stream.sent

            app.on_frame({"sub": app.pty_id, "dropped": 3})
            await pilot.pause()
            assert app.stream.ops().count("attach") == 2, \
                "a dropped frame left a silent gap instead of re-attaching"
            assert app.dropped == 3

    asyncio.run(go())


def test_keystrokes_are_chunked_and_a_short_write_is_resent():
    """`input` is capped at 4096 bytes per op and reports what actually landed
    in the pty's buffer. A client that ignores either loses keystrokes in the
    middle of the prompt it attached to answer."""
    async def go():
        app = PipelineApp(client=FakeClient([]))
        async with app.run_test():
            app.stream = FakeStream()
            app.attached = ("/tmp/alpha", "TICKET-001")
            app.pty_screen = Screen(4, 24)

            app._send_keys(b"y" * 5000)
            op, kw = app.stream.sent[-1]
            first = base64.b64decode(kw["data"])
            assert op == "input" and len(first) == PTY_INPUT, len(first)

            # the daemon took only two bytes: the rest must not vanish
            app.on_frame({"id": app.stream._id, "ok": True,
                          "data": {"written": 2, "short": True}})
            assert app.stream.ops() == ["input"], "a full buffer was hammered"
            app.on_frame({"sub": 1, "pty": base64.b64encode(b".").decode()})
            resent = base64.b64decode(app.stream.sent[-1][1]["data"])
            assert resent.startswith(first[2:]), "the short write's tail was dropped"
            assert len(resent) == PTY_INPUT, "the refill is not capped"

            app.on_frame({"id": app.stream._id, "ok": True,
                          "data": {"written": len(resent), "short": False}})
            # 5000 sent, 2 + 4096 acknowledged: the rest, and nothing lost
            assert base64.b64decode(app.stream.sent[-1][1]["data"]) == b"y" * 902
            app.on_frame({"id": app.stream._id, "ok": True,
                          "data": {"written": 902, "short": False}})
            assert app.keys_out == b"" and app.keys_flight is None

    asyncio.run(go())


def test_the_pane_stops_claiming_to_be_live_when_the_stage_ends():
    """A frozen last screen that still looks live is the one way this pane can
    lie. `stage_end` for the attached ticket drops it back to the log."""
    async def go():
        d = "/tmp/alpha"
        fake = FakeClient([row(d, "TICKET-001", "planning", running=True,
                               mode="interactive")])
        app = PipelineApp(client=fake)
        async with app.run_test() as pilot:
            app.stream = FakeStream()
            app.query_one(Tree).focus()
            await select(app, pilot, d, "TICKET-001")
            await pilot.pause()
            assert app.attached == (d, "TICKET-001")

            fake.rows = [row(d, "TICKET-001", "review")]        # mode: batch
            app.on_frame({"sub": 1, "event": {"project": d, "ticket": "TICKET-001",
                                              "kind": "stage_end", "data": {}}})
            await pilot.pause()
            assert app.attached is None, "the pane kept a finished session"
            assert app.stream.ops()[-1] == "detach", app.stream.sent
            assert app.query_one("#pty").display is False

    asyncio.run(go())


def test_a_bracketed_path_on_the_attached_screen_does_not_crash_the_pane():
    """`Static` renders Rich markup by default and this pane is fed raw
    terminal output. `ls [/home/x]` on the attached screen raised MarkupError
    inside the frame handler -- the pane died on a perfectly ordinary line.
    The same class of text reaches `notify()`."""
    async def go():
        app = PipelineApp(client=FakeClient([]))
        async with app.run_test() as pilot:
            app.pty_screen = Screen(4, 40)
            app.pty_id = 1
            app.on_frame({"sub": 1, "pty": base64.b64encode(
                b"$ ls [/home/x] [bold]\r\n").decode()})
            await pilot.pause()
            assert "[/home/x]" in pty_pane(app), pty_pane(app)

            app.notify("attach: TICKET-001 is not running [/tmp/p]")
            await pilot.pause()
            assert app.is_running

    asyncio.run(go())


def test_edit_waits_for_the_stage_to_actually_stop():
    """`kill` is a SIGTERM, not a join: the daemon reaps on its next tick and
    `_finish` then writes the ticket from its pre-spawn snapshot -- over
    whatever the human saved meanwhile, silently. The docstring claimed the
    stage was stopped first; make it so."""
    async def go():
        d = make_project()
        running = row(d, "TICKET-001", "implementing", running=True)
        fake = FakeClient([running])
        app = PipelineApp(client=fake)
        opened = []
        app._sh = lambda cmd: opened.append(cmd)
        async with app.run_test() as pilot:
            app.query_one(Tree).focus()
            await select(app, pilot, d, "TICKET-001")
            assert app.selected == (str(d), "TICKET-001")

            app._stopped = lambda key, tries=20: False   # never reaped
            await pilot.press("e")
            await pilot.pause()
            assert "kill" in fake.sent, fake.sent
            assert opened == [], "the editor opened on a file the daemon owns"

            # the daemon has now reaped it: the real `_stopped` sees that
            fake.rows = [row(d, "TICKET-001", "implementing", running=False)]
            del app._stopped
            await pilot.press("e")
            await pilot.pause()
            assert len(opened) == 1, opened

    asyncio.run(go())


def test_attaching_sends_the_pane_size():
    """TICKET-019: the child is forked at a fixed 40x120 and the TUI never
    tells the daemon how big its pane really is, so a wide terminal renders the
    agent in a 120-column box. `_op_resize` exists on the daemon and no client
    has ever called it."""
    async def go():
        d = "/tmp/alpha"
        fake = FakeClient([row(d, "TICKET-001", "planning", running=True,
                               mode="interactive")])
        app = PipelineApp(client=fake)
        async with app.run_test(size=(200, 50)) as pilot:
            app.stream = FakeStream()
            app.query_one(Tree).focus()
            await select(app, pilot, d, "TICKET-001")
            await pilot.pause()
            app.on_frame({"id": app.pty_id, "ok": True,
                          "data": {"screen": ["Allow Bash?"], "rows": 40,
                                   "cols": 120, "writer": True}})
            await pilot.pause()

            assert "resize" in app.stream.ops(), \
                f"attached without sending a size: {app.stream.ops()}"
            kw = dict(app.stream.sent[-1][1])
            assert kw["cols"] > 120, f"pane no wider than the child: {kw}"
            assert app.pty_screen.cols == kw["cols"], \
                f"local screen {app.pty_screen.cols} != sent {kw['cols']}"

    asyncio.run(go())


def test_resizing_the_terminal_resizes_the_child():
    async def go():
        d = "/tmp/alpha"
        fake = FakeClient([row(d, "TICKET-001", "planning", running=True,
                               mode="interactive")])
        app = PipelineApp(client=fake)
        async with app.run_test(size=(200, 50)) as pilot:
            app.stream = FakeStream()
            app.query_one(Tree).focus()
            await select(app, pilot, d, "TICKET-001")
            await pilot.pause()
            app.on_frame({"id": app.pty_id, "ok": True,
                          "data": {"screen": ["Allow Bash?"], "rows": 40,
                                   "cols": 120, "writer": True}})
            await pilot.pause()

            await pilot.resize_terminal(300, 60)
            await pilot.pause()
            assert app.stream.ops().count("resize") == 2, app.stream.sent
            assert app.pty_screen.cols == 266, app.pty_screen.cols
            assert app.pty_screen.rows == 58, app.pty_screen.rows

            await pilot.resize_terminal(300, 60)
            await pilot.pause()
            assert app.stream.ops().count("resize") == 2, \
                "the same size was re-sent"

            app.on_frame({"sub": app.pty_id, "dropped": 3})
            await pilot.pause()
            app.on_frame({"id": app.pty_id, "ok": True,
                          "data": {"screen": ["Allow Bash?"], "rows": 58,
                                   "cols": 266, "writer": True}})
            await pilot.pause()
            assert app.stream.ops().count("resize") == 2, \
                "re-attaching re-sent a size the daemon already has"

    asyncio.run(go())


def test_a_read_only_viewer_never_sends_a_resize():
    async def go():
        d = "/tmp/alpha"
        fake = FakeClient([row(d, "TICKET-001", "planning", running=True,
                               mode="interactive")])
        app = PipelineApp(client=fake)
        async with app.run_test(size=(200, 50)) as pilot:
            app.stream = FakeStream()
            app.query_one(Tree).focus()
            await select(app, pilot, d, "TICKET-001")
            await pilot.pause()
            app.on_frame({"id": app.pty_id, "ok": True,
                          "data": {"screen": ["Allow Bash?"], "rows": 40,
                                   "cols": 120, "writer": False}})
            await pilot.pause()

            await pilot.resize_terminal(300, 60)
            await pilot.pause()
            assert "resize" not in app.stream.ops(), \
                "resize claims the writer slot on the daemon"


def test_raw_mode_routes_every_keystroke_to_the_pty_until_esc_esc():
    """TICKET-021: `i` must hand the keyboard to the attached pty, not suspend
    the app to read one line. Arrows and Tab belong to the child while raw mode
    is on; `Esc Esc` gives them back to the tree."""
    async def go():
        app = PipelineApp(client=FakeClient([]))
        async with app.run_test() as pilot:
            app.stream = FakeStream()
            app.attached = ("/tmp/alpha", "TICKET-001")
            app.pty_screen = Screen(4, 24)

            await pilot.press("i")
            await pilot.pause()
            for key in ("down", "tab"):
                await pilot.press(key)
                await pilot.pause()
                # one op is in flight at a time and the daemon ack is what
                # releases the next keystroke; the fake stream never acks
                app.on_frame({"id": app.stream._id, "ok": True,
                              "data": {"written": PTY_INPUT}})
            sent = b"".join(base64.b64decode(kw["data"])
                            for op, kw in app.stream.sent if op == "input")
            assert sent == b"\x1b[B\t", f"raw mode never reached the pty: {sent!r}"

            await pilot.press("escape", "escape")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            after = b"".join(base64.b64decode(kw["data"])
                             for op, kw in app.stream.sent if op == "input")
            assert after == sent, f"esc esc did not leave raw mode: {after!r}"

    asyncio.run(go())


def status(app) -> str:
    return str(app.query_one("#status").render())


def test_raw_mode_is_visible_and_does_not_outlive_the_attachment():
    """A keyboard that silently belongs to the child is worse than no raw mode,
    and raw mode pointed at a detached pane types into nothing."""
    async def go():
        app = PipelineApp(client=FakeClient([]))
        async with app.run_test() as pilot:
            app.stream = FakeStream()
            app.pty_screen = Screen(4, 24)
            await pilot.press("i")
            await pilot.pause()
            assert app.raw is False, "raw mode with nothing to type into"

            app.attached = ("/tmp/alpha", "TICKET-001")
            await pilot.press("i")
            await pilot.pause()
            assert app.raw is True
            assert "RAW" in status(app), status(app)

            app._detach()
            await pilot.pause()
            assert app.raw is False, "raw mode outlived the attachment"
            assert "RAW" not in status(app), status(app)

    asyncio.run(go())


def test_tail_log_never_returns_a_raw_escape_byte_for_a_pty_dump():
    """A finished `mode: interactive` stage leaves a raw PTY dump, not
    stream-json. `tail_log()` must render it through the pyte `Screen`, the
    same one the live pane uses, not hand escape bytes to a `RichLog`."""
    d = make_project()
    logs = d / ".project" / "logs"
    logs.mkdir(parents=True)
    (logs / "TICKET-001-planning.log").write_bytes(
        b"\x1b[2C\x1b[3A\x1b[?25h\x1b[?25l\x1b[2D\x1b[3B hello\x1b[7A\x1b[38;5;174m*\x1b[39m\n")

    lines = tail_log(str(d), "TICKET-001")

    for line in lines:
        assert "\x1b" not in line, f"raw escape byte reached the log line: {line!r}"


def test_tail_log_renders_a_pty_dump_as_the_final_screen():
    """Escape-free is not enough: the pyte screen is the point. A dump
    whose second frame clears and overwrites the first must come back
    as the last screen, once."""
    d = make_project()
    logs = d / ".project" / "logs"
    logs.mkdir(parents=True)
    (logs / "TICKET-001-planning.log").write_bytes(
        b"\x1b[H\x1b[2Jfirst frame\x1b[H\x1b[2Jsecond frame\x1b[K\n")

    assert tail_log(str(d), "TICKET-001") == ["second frame"]


def test_tail_log_renders_a_pty_dump_at_its_own_width_not_120():
    """The width now rides in the log, as an OSC marker `spawn()` and
    `_op_resize` write (`\\x1b]9999;<rows>;<cols>\\x07`). It is spelled out
    literally here, not imported from `pipeline.pty.host`, so this file
    still imports cleanly on base (DEC-017). Without it `render_pty()`
    always replays on a `Screen()`, 40x120 by default: a log written at a
    different width -- as every resized attach produces -- re-wraps at the
    wrong column count, and a later frame's redraw lands on top of a
    leftover row instead of clearing it."""
    d = make_project()
    logs = d / ".project" / "logs"
    logs.mkdir(parents=True)
    geom = b"\x1b]9999;40;150\x07"
    frame1 = b"B" * 140
    redraw = b"\x1b[1A\r\x1b[KSHORT\n"
    (logs / "TICKET-001-planning.log").write_bytes(geom + frame1 + redraw)

    lines = tail_log(str(d), "TICKET-001")

    assert lines == ["SHORT"], (
        f"replaying at the log's own width (150) should be clean, got {lines!r}"
    )


def test_render_pty_matches_the_screen_the_dump_was_written_on():
    """A dump written at width 150 comes back equal to that screen's own
    `display`."""
    frames = b"\x1b[H\x1b[2J" + b"B" * 140 + b"\x1b[1A\r\x1b[KSHORT\n"
    want_screen = Screen(40, 150)
    want_screen.feed(frames)
    want = [ln.rstrip() for ln in want_screen.display]
    while want and not want[-1]:
        want.pop()

    assert render_pty(b"\x1b]9999;40;150\x07" + frames) == want


def test_render_pty_resizes_where_the_log_says_the_screen_did():
    """`render_pty()` resizes mid-replay where the log says the daemon
    resized, so it reproduces the daemon's screen. Replaying the identical
    bytes wholly at 150 gives `['tail']` instead -- a different screen."""
    want_screen = Screen(40, 120)
    want_screen.feed(b"A" * 130)
    want_screen.resize(40, 150)
    want_screen.feed(b"\r\x1b[Ktail\n")
    want = [ln.rstrip() for ln in want_screen.display]
    while want and not want[-1]:
        want.pop()

    got = render_pty(b"\x1b]9999;40;120\x07" + b"A" * 130 +
                     b"\x1b]9999;40;150\x07" + b"\r\x1b[Ktail\n")

    assert got == want
    assert want == ["A" * 120, "tail"]


def test_render_pty_ignores_a_hostile_width_marker():
    """A five-digit marker does not match `GEOM_OSC` at all, so the default
    40x120 stands. A four-digit one is clamped to `MAX_DIM` (1000) columns."""
    assert render_pty(b"\x1b]9999;99999;99999\x07hello") == ["hello"]
    assert [len(l) for l in render_pty(b"\x1b]9999;9999;9999\x07" + b"x" * 1500)] == \
        [1000, 500]


def test_tail_log_keeps_a_width_marker_the_tail_cut_dropped():
    """`spawn()`'s opening marker sits in the head `MAX_TAIL` cuts off; the
    geometry must survive the cut. `\\x1b[H\\x1b[2J` is load-bearing: `pad\\n`
    is a bare line feed that fills the screen, so without the clear
    `\\x1b[1A` lands on a pad row instead of clamping at row 0, and the B
    row of the frame survives below SHORT at every width."""
    d = make_project()
    logs = d / ".project" / "logs"
    logs.mkdir(parents=True)
    geom = b"\x1b]9999;40;150\x07"
    pad = b"pad\n" * (MAX_TAIL // 4 + 1)
    frames = b"\x1b[H\x1b[2J" + b"B" * 140 + b"\x1b[1A\r\x1b[KSHORT\n"
    (logs / "TICKET-001-planning.log").write_bytes(geom + pad + frames)

    lines = tail_log(str(d), "TICKET-001")

    assert lines == ["SHORT"]


def test_tail_log_still_renders_a_stream_json_log():
    """The sniff must not divert a headless stage's log into pyte: 35
    of the 43 `planning` logs in this repo are stream-json, from runs
    where nothing could attach."""
    d = make_project()
    logs = d / ".project" / "logs"
    logs.mkdir(parents=True)
    (logs / "TICKET-001-planning.log").write_bytes(
        b'{"type":"assistant","message":{"content":'
        b'[{"type":"text","text":"planning done"}]}}\n')

    assert tail_log(str(d), "TICKET-001") == ["planning done"]
