"""Interactive stages: a real PTY, a pyte screen, and four socket ops.

No `claude` anywhere in here -- the child is a shell one-liner, so the whole
file runs in well under a second. The property being defended is the one a
plausible-looking implementation breaks: **detaching must not kill the child.**
"""
import base64
import json
import os
import socket
import tempfile
import time
from pathlib import Path

# Before anything imports a path out of the environment: never touch the
# developer's real registry, event log or runtime socket.
for var in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
    os.environ.setdefault(var, tempfile.mkdtemp())

from pipeline.core.config import harness, render, stage_config
from pipeline.daemon import supervisor
from pipeline.daemon.server import Conn, Poller, Server
from pipeline.daemon.store import Store
from pipeline.pty import host

# `read` keeps the child alive after each line, which is what lets the test
# assert it is still there once every reader has gone away.
CMD = (r'printf "hello\r\n"; read x; printf "got:$x\r\n"; '
       r'read y; printf "y:$y\r\n"; read z')


def drive(poller: Poller, check, timeout: float = 5.0) -> bool:
    """Poll until `check()` holds. No sleeps: the fd is what wakes us."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return True
        poller.poll(0.05)
    return bool(check())


def child(tmp: Path, poller: Poller | None = None, cmd: str = CMD,
          session: str = "s1") -> dict:
    """A record shaped exactly like `spawn()`'s interactive one."""
    proc, pipe = host.start(cmd, tmp, dict(os.environ, TERM="xterm-256color"))
    screen = host.Screen()
    rec = {"proc": proc, "pipe": pipe, "reader": screen, "screen": screen,
           "writer": None, "fh": (tmp / "stage.log").open("wb"),
           "poller": poller, "sink": lambda ev: None, "mode": "interactive",
           "session": session, "tid": "TICKET-001", "stage": "planning",
           "log": tmp / "stage.log"}
    if poller:
        poller.watch(pipe.fileno(), lambda fd: supervisor.pump(rec))
    return rec


# --------------------------------------------------------------------------
# the one check that had to fail first
# --------------------------------------------------------------------------
def test_pty_screen_and_detach_does_not_kill():
    tmp = Path(tempfile.mkdtemp())
    poller = Poller()
    rec = child(tmp, poller)
    proc, screen = rec["proc"], rec["screen"]
    seen: list = []
    screen.subs.append(seen.append)        # what an attached client receives
    try:
        assert drive(poller, lambda: "hello" in screen.display[0]), \
            f"the child's output never reached the screen: {screen.display[:3]}"

        os.write(rec["pipe"].fileno(), b"abc\n")
        assert drive(poller, lambda: any("got:abc" in l for l in screen.display)), \
            f"input never reached the child: {screen.display[:5]}"
        assert seen, "an attached subscriber received nothing"

        # DETACH: every client drops its subscription and stops reading. The
        # daemon still owns the master fd, so nothing about the child changes.
        screen.subs.clear()
        poller.unwatch(rec["pipe"].fileno())
        assert proc.poll() is None, "detach killed the child"

        # and re-attaching later is just re-subscribing to the same session.
        # This is the load-bearing half: a `poll()` right after the detach can
        # win the race against a SIGHUP, but a session you can still type into
        # cannot have been hung up.
        poller.watch(rec["pipe"].fileno(), lambda fd: supervisor.pump(rec))
        try:
            os.write(rec["pipe"].fileno(), b"second\n")
        except (OSError, ValueError) as e:
            assert False, f"detach closed the session: {e.__class__.__name__}: {e}"
        assert drive(poller, lambda: any("y:second" in l for l in screen.display)), \
            "the session did not survive a detach/attach cycle"
        assert proc.poll() is None
    finally:
        proc.terminate()
        try:
            supervisor.close_child(rec)      # closing the master IS the hangup
        except Exception as e:               # never let teardown mask the assert
            print(f"teardown: {e.__class__.__name__}: {e}")
        poller.close()
    assert proc.wait(timeout=5) is not None
    # the raw stream is on disk, which is what covers replay past the screen
    assert b"hello" in (tmp / "stage.log").read_bytes()


def test_the_master_fd_does_not_reach_the_next_interactive_child():
    """PEP 446 does not cover `os.forkpty`: its master comes back
    *inheritable*, so without the explicit clear the second interactive stage
    inherits the first one's master and can type into another ticket's
    permission prompt. `subprocess` never had this hole -- it closes fds."""
    tmp = Path(tempfile.mkdtemp())
    rec = child(tmp, cmd="read x")
    try:
        assert os.get_inheritable(rec["pipe"].fileno()) is False, \
            "the pty master survives exec into every later child"
    finally:
        rec["proc"].terminate()
        supervisor.close_child(rec)


def test_a_pty_proc_is_shaped_like_popen():
    """`reap()` calls `rec["proc"].poll()` and `shut_down()` calls
    `.terminate()`/`.wait(timeout=)`/`.kill()`. A pty.fork pid is not a Popen,
    so the shim is what keeps all three call sites free of a PTY branch."""
    tmp = Path(tempfile.mkdtemp())
    rec = child(tmp, cmd="read x")
    proc = rec["proc"]
    assert proc.poll() is None and proc.pid > 0
    proc.terminate()
    assert proc.wait(timeout=5) is not None
    assert proc.poll() == proc.returncode, "returncode must latch"
    proc.kill()                              # a dead pid must not raise
    supervisor.close_child(rec)


# --------------------------------------------------------------------------
# the four ops
# --------------------------------------------------------------------------
def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def client(server: Server):
    """(Conn, peer socket). The peer is where fan-out lands: `_pty_out` pumps,
    which flushes the outbox onto the wire."""
    a, b = socket.socketpair()
    b.setblocking(False)
    conn = Conn(a)
    server.conns[a.fileno()] = conn
    return conn, b


def frames(peer) -> list:
    try:
        data = peer.recv(1 << 20)
    except BlockingIOError:
        return []
    return [json.loads(l) for l in data.decode().splitlines() if l.strip()]


def ask(server: Server, conn: Conn, **req) -> dict:
    """One request through the real line handler; its reply frame."""
    conn.out.clear()
    server._handle_line(conn, json.dumps(req))
    out = [json.loads(f) for f in conn.out]
    conn.out.clear()
    return next(f for f in out if "ok" in f)


def test_attach_gives_one_writer_and_detach_frees_the_slot():
    tmp = Path(tempfile.mkdtemp())
    st = Store(tmp / "events.db")
    server = Server(st, tmp / "d.sock")
    rec = child(tmp, server)
    server.states["/p"] = {"TICKET-001": rec}
    (a, a_peer), (b, b_peer) = client(server), client(server)
    try:
        r = ask(server, a, id=1, op="attach", ticket="TICKET-001")
        assert r["ok"], r
        assert r["data"]["writer"] is True, "the first attacher writes"
        assert len(r["data"]["screen"]) == host.ROWS, r["data"]["screen"]
        assert (r["data"]["rows"], r["data"]["cols"]) == (host.ROWS, host.COLS)

        r = ask(server, b, id=2, op="attach", ticket="TICKET-001")
        assert r["ok"] and r["data"]["writer"] is False, r

        r = ask(server, b, id=3, op="input", data=b64("x"))
        assert not r["ok"] and "another client holds the writer" in r["error"], r

        r = ask(server, a, id=4, op="input", data=b64("abc\n"))
        assert r["ok"] and r["data"]["written"] == 4, r
        assert drive(server, lambda: any("got:abc" in l
                                         for l in rec["screen"].display)), \
            "the writer's keystrokes never reached the child"

        # the second client saw the same bytes -- fan-out, not a takeover
        assert any(f.get("sub") == 2 and "pty" in f for f in frames(b_peer)), \
            "the read-only client saw none of the session's output"

        # detach frees the slot; the next input from anyone claims it
        assert ask(server, a, id=5, op="detach")["ok"]
        assert rec["writer"] is None, "detach left the writer slot held"
        r = ask(server, b, id=6, op="input", data=b64("q\n"))
        assert r["ok"], r
        assert rec["writer"] is b

        # and a dropped connection frees it exactly the same way
        server._drop(b.sock.fileno())
        assert rec["writer"] is None, "a disconnect left the writer slot held"
        assert rec["proc"].poll() is None, "a client disconnect killed the child"
    finally:
        rec["proc"].terminate()
        supervisor.close_child(rec)
        server.close()


def test_resize_reaches_both_the_child_and_the_screen():
    tmp = Path(tempfile.mkdtemp())
    st = Store(tmp / "events.db")
    server = Server(st, tmp / "d.sock")
    rec = child(tmp, server, cmd=r'read x; stty size; read y')
    server.states["/p"] = {"TICKET-001": rec}
    a, _peer = client(server)
    try:
        ask(server, a, id=1, op="attach", ticket="TICKET-001")
        assert ask(server, a, id=2, op="resize", rows=50, cols=160)["ok"]
        assert (rec["screen"].rows, rec["screen"].cols) == (50, 160)
        ask(server, a, id=3, op="input", data=b64("\n"))
        assert drive(server, lambda: any("50 160" in l
                                         for l in rec["screen"].display)), \
            f"the child still sees the old winsize: {rec['screen'].display[:5]}"

        for bad in ({"rows": 0, "cols": 80}, {"rows": 5000, "cols": 80},
                    {"rows": "big", "cols": 80}, {"cols": 80}):
            r = ask(server, a, id=4, op="resize", **bad)
            assert not r["ok"], f"{bad} was accepted"

        # a refused op must not take a free writer slot on its way out
        b, _bpeer = client(server)
        ask(server, b, id=5, op="attach", ticket="TICKET-001")
        ask(server, a, id=6, op="detach")
        assert rec["writer"] is None
        assert not ask(server, b, id=7, op="resize", rows=0, cols=80)["ok"]
        assert not ask(server, b, id=8, op="input", data="not base64!!")["ok"]
        assert rec["writer"] is None, "a refused op claimed the writer"
    finally:
        rec["proc"].terminate()
        supervisor.close_child(rec)
        server.close()


def test_resize_records_the_width_in_the_log():
    """`_op_resize` writes the new geometry into the log, so a later replay
    knows the width the daemon actually resized to."""
    tmp = Path(tempfile.mkdtemp())
    st = Store(tmp / "events.db")
    server = Server(st, tmp / "d.sock")
    rec = child(tmp, server, cmd=r'read x')
    server.states["/p"] = {"TICKET-001": rec}
    a, _peer = client(server)
    try:
        ask(server, a, id=1, op="attach", ticket="TICKET-001")
        assert ask(server, a, id=2, op="resize", rows=50, cols=160)["ok"]
        assert host.geom_marker(50, 160) in (tmp / "stage.log").read_bytes()
    finally:
        rec["proc"].terminate()
        supervisor.close_child(rec)
        server.close()


def test_input_after_the_session_is_replaced_does_not_reach_the_new_one():
    """`conn.attached` is a name plus a session. Matching on the name alone
    would rebind a stale client to whatever runs for that ticket next: it
    would type into a terminal it cannot see, and hold that session's writer
    slot while watching a dead screen."""
    tmp = Path(tempfile.mkdtemp())
    st = Store(tmp / "events.db")
    server = Server(st, tmp / "d.sock")
    old_rec = child(tmp, server, cmd="read x", session="s1")
    server.states["/p"] = {"TICKET-001": old_rec}
    a, _peer = client(server)
    try:
        assert ask(server, a, id=1, op="attach", ticket="TICKET-001")["ok"]

        # the stage finished and the NEXT interactive stage for the same
        # ticket started, all before this client sent another frame
        new_rec = child(tmp, server, cmd="read x", session="s2")
        server.states["/p"]["TICKET-001"] = new_rec

        r = ask(server, a, id=2, op="input", data=b64("y\n"))
        assert not r["ok"] and "no longer running" in r["error"], r
        assert new_rec["writer"] is None, "a stale client took the new writer"
        assert a.attached is None, "the stale attachment was not dropped"
    finally:
        for rec in (old_rec, new_rec):
            rec["proc"].terminate()
            supervisor.close_child(rec)
        server.close()


def test_one_write_into_a_pty_is_bounded():
    """A pty input buffer is a few KiB and the master is non-blocking, so an
    oversized write truncates mid-keystroke into a session that is being asked
    to approve commands. Refuse it; the client can chunk."""
    from pipeline.daemon.server import PTY_INPUT
    tmp = Path(tempfile.mkdtemp())
    st = Store(tmp / "events.db")
    server = Server(st, tmp / "d.sock")
    rec = child(tmp, server, cmd="read x")
    server.states["/p"] = {"TICKET-001": rec}
    a, _peer = client(server)
    try:
        ask(server, a, id=1, op="attach", ticket="TICKET-001")
        r = ask(server, a, id=2, op="input", data=b64("x" * (PTY_INPUT + 1)))
        assert not r["ok"] and "at most" in r["error"], r
        r = ask(server, a, id=3, op="input", data=b64("ok\n"))
        assert r["ok"] and r["data"]["short"] is False, r
    finally:
        rec["proc"].terminate()
        supervisor.close_child(rec)
        server.close()


def test_a_client_that_stops_reading_drops_frames_instead_of_hoarding_them():
    """A pty frame is a 64 KiB read, base64'd. `OUTBOX` was sized for small
    event objects, so 1000 of them is ~87 MB per stalled client and the daemon
    holds every project's flock and every lease."""
    from pipeline.daemon.server import PTY_BACKLOG
    tmp = Path(tempfile.mkdtemp())
    st = Store(tmp / "events.db")
    server = Server(st, tmp / "d.sock")
    rec = child(tmp, server, cmd="read x")
    server.states["/p"] = {"TICKET-001": rec}
    a, _peer = client(server)
    try:
        ask(server, a, id=1, op="attach", ticket="TICKET-001")
        a.out.clear()
        for _ in range(PTY_BACKLOG):          # a client that stopped reading
            a.out.append(b"{}\n")
        rec["screen"].feed(b"more output\r\n")
        assert len(a.out) == PTY_BACKLOG, "the backlog grew past its bound"
        assert a.dropped == 1, "a dropped chunk was not counted"
    finally:
        rec["proc"].terminate()
        supervisor.close_child(rec)
        server.close()


def test_attach_refuses_a_headless_stage_and_a_finished_one():
    tmp = Path(tempfile.mkdtemp())
    st = Store(tmp / "events.db")
    server = Server(st, tmp / "d.sock")
    server.states["/p"] = {"TICKET-002": {"screen": None, "tid": "TICKET-002",
                                          "stage": "implementing"}}
    a, _peer = client(server)
    try:
        r = ask(server, a, id=1, op="attach", ticket="TICKET-002")
        assert not r["ok"] and "headless" in r["error"], r
        r = ask(server, a, id=2, op="attach", ticket="TICKET-404")
        assert not r["ok"] and "not running" in r["error"], r
        for op in ("input", "resize", "detach"):
            r = ask(server, a, id=3, op=op, data="", rows=10, cols=10)
            assert r["ok"] if op == "detach" else "not attached" in r["error"], r
    finally:
        server.close()


# --------------------------------------------------------------------------
# the frontmatter -> harness wiring
# --------------------------------------------------------------------------
def rendered(hcfg, key):
    from pipeline.core.config import compose_prompt
    cfg = stage_config("planning")
    prompt = compose_prompt("planning")
    try:
        return render(hcfg, cfg, tid="TICKET-001", project=Path("/proj"),
                      ticket=Path("/proj/t.md"), result_file=Path("/proj/t.result"),
                      session="s1", prompt=prompt, settings=Path("/s.json"), key=key)
    finally:
        prompt.unlink()


def test_planning_is_interactive_and_never_rendered_under_print_mode():
    """`--permission-mode` is ignored under `-p` and AskUserQuestion is not in
    the headless toolset -- an interactive stage that still renders `-p` has
    lost the only thing the PTY was for."""
    assert stage_config("planning").get("mode") == "interactive"
    cmd = rendered(harness("claude-code"), "interactive_cmd")
    assert "claude -p" not in cmd and "--output-format stream-json" not in cmd
    assert "--permission-mode" in cmd, "the whole point of the PTY"
    assert "--max-budget-usd 5" in cmd, "the money guard works outside print mode"
    assert "--append-system-prompt" in cmd and "--settings /s.json" in cmd


class Attachable(Poller):
    """A poller a client could reach -- what `Server` is, without the socket."""
    attachable = True


def test_an_interactive_stage_runs_headless_when_nothing_can_attach():
    """`pipeline run` builds a bare `Poller`: no socket, so no client can ever
    `attach`, and a REPL nobody attaches to sits at its prompt until its lease
    expires twice and the ticket escalates. Gating on `poller is not None` did
    not see that -- `run()` passes one.

    Headless is what the stage did before it grew a PTY, and `planning`'s own
    `needs-input` result is the escape hatch that keeps the human in the loop.
    """
    tmp = Path(tempfile.mkdtemp())
    plain, attachable = Poller(), Attachable()
    try:
        rec = supervisor.spawn(tmp, tmp, "TICKET-001", "planning",
                               harness("fake"), plain)
        assert rec["mode"] == "batch", "a stage nobody can attach to still ran a REPL"
        assert rec["screen"] is None
        rec["proc"].wait()
        supervisor.close_child(rec)

        rec = supervisor.spawn(tmp, tmp, "TICKET-001", "planning",
                               harness("fake"), attachable)
        assert rec["mode"] == "interactive", "a daemon-hosted stage lost its PTY"
        assert rec["screen"] is not None
    finally:
        rec["proc"].terminate()
        rec["proc"].wait()
        supervisor.close_child(rec)
        plain.close()
        attachable.close()


def test_an_interactive_log_opens_with_its_geometry():
    """Only an interactive log gets the opening marker: an ESC in a batch
    log would send stream-json through pyte instead of rendering it
    (DEC-039)."""
    tmp = Path(tempfile.mkdtemp())
    plain, attachable = Poller(), Attachable()
    try:
        rec = supervisor.spawn(tmp, tmp, "TICKET-001", "planning",
                               harness("fake"), plain)
        rec["proc"].wait()
        assert b"\x1b]9999;" not in rec["log"].read_bytes()
        supervisor.close_child(rec)

        rec = supervisor.spawn(tmp, tmp, "TICKET-001", "planning",
                               harness("fake"), attachable)
        assert host.geom_marker(host.ROWS, host.COLS) in rec["log"].read_bytes()
    finally:
        rec["proc"].terminate()
        rec["proc"].wait()
        supervisor.close_child(rec)
        plain.close()
        attachable.close()


def test_an_interactive_stage_ends_when_its_result_lands():
    """A REPL does not exit because the agent wrote its verdict, and `finish()`
    fires on `proc.poll()`. Without this the session sat at its prompt, the
    lease expired twice, and the ticket escalated with its plan already
    written."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / ".project" / "tickets").mkdir(parents=True)
    rec = child(tmp, cmd="read x; read y; read z")
    inflight = {"TICKET-001": rec}
    try:
        supervisor.end_interactive(tmp, inflight)
        assert rec["proc"].poll() is None, "ended a session that reported nothing"

        (tmp / ".project" / "tickets" / "TICKET-001.result").write_text(
            "result: ok\nsummary: planned\n")
        supervisor.end_interactive(tmp, inflight)
        assert rec["proc"].wait(5) is not None, "the REPL was left holding its lease"
    finally:
        rec["proc"].kill()
        rec["fh"].close()


def test_a_harness_with_no_interactive_template_falls_back_to_its_command():
    fake = harness("fake")
    assert "interactive_cmd" not in fake
    assert rendered(fake, "interactive_cmd") == rendered(fake, "cmd")


def test_the_geometry_marker_round_trips_and_clamps():
    """`geom_marker()`/`last_geometry()` are the only place that knows the OSC
    bytes. Hostile cases: five digits do not match the pattern, and a value
    that does match is clamped to `1..MAX_DIM`."""
    assert host.geom_marker(40, 124) == b"\x1b]9999;40;124\x07"
    assert host.last_geometry(b"") == (host.ROWS, host.COLS)
    assert host.last_geometry(b"no marker here") == (host.ROWS, host.COLS)
    assert host.last_geometry(host.geom_marker(40, 124)) == (40, 124)
    assert host.last_geometry(
        host.geom_marker(40, 124) + host.geom_marker(50, 160)) == (50, 160)
    assert host.last_geometry(b"\x1b]9999;99999;99999\x07") == (host.ROWS, host.COLS)
    assert host.last_geometry(b"\x1b]9999;0;0\x07") == (1, 1)
    assert host.last_geometry(b"\x1b]9999;40;9999\x07") == (40, host.MAX_DIM)

    s = host.Screen(4, 20)
    s.feed(host.geom_marker(40, 124) + b"hi")
    assert s.display[0].strip() == "hi"
