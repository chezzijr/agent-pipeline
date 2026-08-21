"""The daemon: the event log, the line protocol, and the two-stores invariant.

No daemon process and no sleeps anywhere in here. The line handler takes a
`Conn` over a `socket.socketpair()`, and the Store takes a temp path, so every
assertion is against the real code rather than a timing window.
"""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

from helpers import ROOT, project

# Before anything imports a path out of the environment: these tests must never
# touch the developer's real registry, event log or runtime socket.
for var in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
    os.environ[var] = tempfile.mkdtemp()
from pipeline.core import PipelineError
from pipeline.core.ticket import Ticket
from pipeline.daemon import registry
from pipeline.daemon.server import (OUTBOX, Conn, Poller, Server,
                                    ticket_rows)
from pipeline.daemon.store import Store
from pipeline.daemon import supervisor
from pipeline.daemon.supervisor import holder_alive
from pipeline.stream import StreamReader


def store(tmp: Path) -> Store:
    return Store(tmp / "events.db")


def server_on(tmp: Path, st: Store) -> Server:
    return Server(st, tmp / "daemon.sock")


def talk(server: Server, req: dict) -> list[dict]:
    """Drive one request through the real line handler and read the frames it
    queued. A socketpair, so there is nothing to poll and nothing to wait for."""
    a, b = socket.socketpair()
    conn = Conn(a)
    server._handle_line(conn, json.dumps(req) + "\n")
    conn.flush()
    a.close()
    data = b.recv(1 << 20)
    b.close()
    return [json.loads(l) for l in data.decode().splitlines() if l.strip()]


# --------------------------------------------------------------------------
# the one check that had to fail first
# --------------------------------------------------------------------------
def test_event_log_is_append_only_and_ping_round_trips():
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    s.emit("/p", "daemon_start", pid=1)
    s.emit("/p", "stage_start", ticket="TICKET-001", stage="planning", pid=2)
    s.emit("/p", "stage_end", ticket="TICKET-001", stage="planning", result="ok")
    assert s.cursor() == 3

    for sql in ("UPDATE events SET kind='x'", "DELETE FROM events"):
        try:
            s.conn.execute(sql)
            assert False, f"{sql} must be refused by a trigger, not by convention"
        except sqlite3.IntegrityError as e:
            assert "append-only" in str(e), e
    assert s.cursor() == 3, "a refused write must leave the log intact"

    srv = server_on(tmp, s)
    try:
        reply = talk(srv, {"id": 1, "op": "ping"})[0]
        assert reply["ok"] and reply["id"] == 1, reply
        assert reply["data"]["pid"] == os.getpid()

        bad = talk(srv, {"id": 2, "op": "rm -rf"})[0]
        assert not bad["ok"] and "unknown op" in bad["error"], bad
        assert not talk(srv, {"id": None, "op": None})[0]["ok"]
        assert not talk(srv, {})[0]["ok"], "a request with no op must answer, not hang"
    finally:
        srv.close()


def test_deleting_the_event_db_leaves_every_ticket_stage_intact():
    """The two-stores invariant, and the whole design rests on it: ticket files
    are state, the database is history. Losing history must lose nothing else.

    So this drives a REAL state change through the writer that also emits --
    `advance()` -- and then asserts the ticket still reads the stage that
    transition put it in with the database deleted underneath it. Reading the
    stage back from a variable set moments earlier would pass no matter what
    `advance()` did."""
    d = project()
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    t = Ticket.find(d, "TICKET-001")
    assert t.stage == "plan-validation"
    supervisor.advance(d, t, "ok", "gate passed", s.emitter(d))
    # transition("plan-validation", "ok") -> awaiting-approval. Hard-coded, not
    # recomputed: a test that asks the code under test what to expect proves
    # nothing about the code under test.
    assert Ticket.find(d, "TICKET-001").stage == "awaiting-approval"
    assert [e["kind"] for e in s.since(0)] == ["transition"]

    s.close()
    for junk in ("events.db", "events.db-wal", "events.db-shm"):
        (tmp / junk).unlink(missing_ok=True)

    assert Ticket.find(d, "TICKET-001").stage == "awaiting-approval"
    s2 = store(tmp)          # reopens empty, no migration, no repair
    assert s2.cursor() == 0, "history is gone"
    assert Ticket.find(d, "TICKET-001").stage == "awaiting-approval", "state is not"
    # and the thread entry advance() wrote is still there to read
    assert any(e.kind == "transition" and "awaiting-approval" in e.text
               for e in Ticket.find(d, "TICKET-001").thread())


# --------------------------------------------------------------------------
# the protocol
# --------------------------------------------------------------------------
def test_ls_reads_ticket_files_and_refuses_an_unregistered_project():
    d = project()
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    srv = server_on(tmp, s)
    try:
        bad = talk(srv, {"id": 1, "op": "ls", "project": str(d)})[0]
        assert not bad["ok"] and "not registered" in bad["error"], bad

        registry.register(d)
        rows = talk(srv, {"id": 2, "op": "ls", "project": str(d)})[0]["data"]
        assert [r["id"] for r in rows] == ["TICKET-001"], rows
        assert rows[0]["stage"] == "plan-validation" and rows[0]["running"] is False

        srv.states[str(d)] = {"TICKET-001": {"proc": None, "mode": "batch"}}
        rows = talk(srv, {"id": 3, "op": "ls"})[0]["data"]
        assert [r for r in rows if r["id"] == "TICKET-001"][0]["running"] is True
    finally:
        srv.close()
        registry.unregister(d)


def test_subscribe_replays_from_the_cursor_then_goes_live():
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    srv = server_on(tmp, s)
    try:
        s.emit("/a", "daemon_start", pid=1)
        mark = s.cursor()
        s.emit("/a", "transition", ticket="TICKET-002", **{"to": "planning"})

        a, b = socket.socketpair()
        conn = Conn(a)
        srv.conns[a.fileno()] = conn      # so _broadcast can see it
        srv._handle_line(conn, json.dumps({"id": 7, "op": "subscribe",
                                           "since": mark}) + "\n")
        s.emit("/a", "escalated", ticket="TICKET-002", reason="live one")
        conn.flush()
        a.close()
        msgs = [json.loads(l) for l in b.recv(1 << 20).decode().splitlines()]
        b.close()

        assert msgs[0] == {"id": 7, "ok": True, "data": {"cursor": mark + 1}}
        kinds = [m["event"]["kind"] for m in msgs[1:] if "event" in m]
        assert kinds == ["transition", "escalated"], msgs
        assert all(m["sub"] == 7 for m in msgs[1:])
        # nothing before the cursor replays: that is what makes it a cursor
        assert "daemon_start" not in kinds
    finally:
        srv.conns.clear()
        srv.close()


def test_a_wedged_client_is_dropped_from_not_the_supervisor():
    """Backpressure is a liveness boundary: a viewer that stops reading must
    lose its own oldest events, never stall the loop that emits them."""
    a, b = socket.socketpair()
    conn = Conn(a)
    for i in range(OUTBOX + 50):
        conn.send({"n": i})
    assert len(conn.out) == OUTBOX and conn.dropped == 50
    assert json.loads(conn.out[0])["n"] == 50, "drop-oldest, not drop-newest"
    a.close()
    b.close()


def test_a_second_daemon_on_a_live_socket_refuses_to_bind():
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    first = server_on(tmp, s)
    try:
        try:
            server_on(tmp, s)
            assert False, "two daemons on one socket is the one thing to prevent"
        except PipelineError as e:
            assert "already listening" in str(e), e
        assert oct(os.stat(tmp / "daemon.sock").st_mode)[-3:] in ("600", "700"), \
            "the socket can kill children; nobody else may connect"
    finally:
        first.close()

    # ...but the file left behind by a dead daemon is litter, not a claim
    (tmp / "daemon.sock").write_text("")
    second = server_on(tmp, s)
    second.close()


def test_a_lease_held_by_a_dead_pid_is_not_a_lease():
    """Without this a daemon restart parks every in-flight ticket for the full
    30-minute expiry."""
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    assert holder_alive(f"planning-{os.getpid()}") is True
    assert holder_alive(f"planning-{dead.pid}") is False
    # fail-safe, never fail-open: anything we cannot read as a pid is alive
    assert holder_alive("planning-someone") is True
    assert holder_alive(None) is True


def test_watch_and_unwatch_are_the_extension_point():
    """Three tickets in the next wave register an fd with this loop. If this
    breaks, they all have to edit server.py instead."""
    p = Poller()
    r, w = os.pipe()
    seen = []
    p.watch(r, lambda fd: seen.append(os.read(fd, 64)))
    os.write(w, b"hello")
    p.poll(0.5)
    assert seen == [b"hello"], seen

    p.unwatch(r)
    os.write(w, b"ignored")
    p.poll(0)
    assert seen == [b"hello"], "unwatch must actually deregister"
    p.unwatch(r)                 # idempotent
    os.close(r); os.close(w)
    p.unwatch(r)                 # and safe on a closed fd
    p.close()


def test_a_child_on_a_pipe_is_drained_and_teed_to_its_log():
    """The pipe TICKET-012 needs: `stdout=PIPE` deadlocks a child at 64K unless
    something drains it, and a pipe nobody wrote down loses `pipeline logs`."""
    from pipeline.daemon import supervisor
    tmp = Path(tempfile.mkdtemp())
    log = tmp / "x.log"
    fh = log.open("wb")
    payload = json.dumps({"type": "system", "subtype": "init", "model": "m",
                          "tools": [], "session_id": "s"}) + "\n"
    big = "x" * 200_000                        # > the 64K pipe buffer
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import sys; sys.stdout.write(sys.argv[1] + 'x' * 200_000)", payload],
        stdout=subprocess.PIPE)
    os.set_blocking(proc.stdout.fileno(), False)
    p = Poller()
    seen = []
    rec = {"proc": proc, "fh": fh, "log": log, "poller": p, "pipe": proc.stdout,
           "reader": StreamReader(),
           "sink": seen.append}
    p.watch(proc.stdout.fileno(), lambda fd: supervisor.pump(rec))
    while proc.poll() is None:
        p.poll(0.1)
    supervisor.close_child(rec)                # drains the tail, then closes
    assert proc.returncode == 0, "an undrained pipe would have blocked the child"
    assert len(log.read_bytes()) == len(payload) + len(big), "the tee lost bytes"
    assert seen and seen[0]["kind"] == "init", seen[:1]
    # `finish()` closes in a finally as well as on the happy path: a second
    # call must not raise, and the fd must be gone from the loop -- otherwise
    # its callback fires every tick forever against a closed file
    assert not p.sel.get_map(), "close_child must deregister the child's fd"
    supervisor.close_child(rec)
    p.close()


def test_registry_is_a_text_file_and_one_flock_per_project():
    d = project()
    try:
        registry.register(d)
        assert d in registry.projects()
        assert str(d) in registry.registry_path().read_text()

        def refused() -> str:
            # a separate process: flock is per open-file-description, so a
            # second lock() in THIS process would succeed and prove nothing
            return subprocess.run(
                [sys.executable, "-c",
                 "import sys; from pipeline.daemon import registry;"
                 " print(registry.lock(sys.argv[1]) is None)", str(d)],
                capture_output=True, text=True, cwd=ROOT).stdout.strip()

        held = registry.lock(d)
        assert held is not None
        assert refused() == "True", "two supervisors on one project double-spawn"
        held.close()          # the kernel releases it on crash too: no stale file
        assert refused() == "False"
    finally:
        registry.unregister(d)
    assert d not in registry.projects()


def test_ls_falls_back_to_the_files_when_no_daemon_is_running():
    """The daemon is an accelerator, never a dependency."""
    d = project()
    r = subprocess.run([sys.executable, "-m", "pipeline", "--project", str(d), "ls"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "TICKET-001" in r.stdout and "plan-validation" in r.stdout, r.stdout
    r = subprocess.run([sys.executable, "-m", "pipeline", "status"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 1 and "not running" in r.stdout, r


# --------------------------------------------------------------------------
# regressions: each of these failed against an earlier version of this file
# --------------------------------------------------------------------------
def test_subscribe_refuses_a_junk_cursor_with_exactly_one_frame():
    """The reply is queued by the op itself, so anything that can fail has to
    fail before it: otherwise one id carries both `ok:true` and `ok:false` and
    a client that returns the first reads a failed subscribe as a success."""
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    srv = server_on(tmp, s)
    try:
        msgs = talk(srv, {"id": 4, "op": "subscribe", "since": "not-a-number"})
        assert len(msgs) == 1, msgs
        assert msgs[0]["ok"] is False and "integer" in msgs[0]["error"], msgs
    finally:
        srv.close()


def test_the_dropped_marker_reports_the_real_count():
    """The marker goes through the same full outbox it is reporting on, so
    clearing the counter after sending it loses every drop but one."""
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    srv = server_on(tmp, s)
    a, b = socket.socketpair()
    conn = Conn(a)
    srv.conns[a.fileno()] = conn
    conn.subs[1] = {"project": None}
    srv._pump = lambda c: None             # hold the frames where we can read them
    try:
        for i in range(OUTBOX + 5):
            conn.send({"filler": i})       # nothing is reading: the outbox fills
        assert conn.dropped == 5

        s.emit("/a", "daemon_start", pid=1)
        marker = next(json.loads(f) for f in conn.out if b'"dropped"' in f)
        assert marker == {"sub": 1, "dropped": 5}, marker
        # the marker and the event each displace one more frame from the full
        # outbox -- those are real losses and must still be counted, not
        # swallowed by the reset that reported the previous batch
        assert conn.dropped == 2, conn.dropped
    finally:
        srv.conns.clear()
        a.close()
        b.close()
        srv.close()


def test_closing_a_server_unhooks_it_from_the_store():
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    srv = server_on(tmp, s)
    assert len(s.listeners) == 1
    srv.close()
    assert s.listeners == [], "a closed server still fed events into dead sockets"
    s.emit("/a", "daemon_start", pid=1)     # must not raise


def test_the_daemon_lock_is_the_claim_not_the_socket_probe():
    """Two daemons starting in the same millisecond both probe, both see
    ECONNREFUSED, and the second unlinks the first's live socket. The flock is
    what actually makes `there is one daemon` true."""
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    first = server_on(tmp, s)
    try:
        (tmp / "daemon.sock").unlink()      # as if the probe had cleared it
        try:
            server_on(tmp, s)
            assert False, "the lock, not the socket file, is the claim"
        except PipelineError as e:
            assert "already listening" in str(e), e
    finally:
        first.close()
    server_on(tmp, s).close()               # released: the next one gets in


def test_the_registry_skips_junk_lines_and_can_drop_a_vanished_project():
    d = project()
    registry.register(d)
    gone = Path(tempfile.mkdtemp()) / "never-existed"
    registry.registry_path().write_text(
        f"# a comment\n\n{gone}\nrelative/path\n{d}\n")
    # `lock()` does mkdir(parents=True); an unchecked line would scaffold a
    # .project/ at whatever a typo named, and serve() would then tick it
    assert registry.projects() == [d], registry.projects()
    assert not gone.exists()
    # ...but a line the filter hides must still be removable
    assert registry.unregister(gone) is True
    assert registry.unregister(d) is True
    assert registry.projects() == []
    assert "# a comment" in registry.registry_path().read_text()


def test_ls_answers_the_same_with_and_without_a_daemon():
    """One `ticket_rows()` behind both, because a command that reports
    different columns depending on whether a daemon happens to be up is a
    dependency wearing an accelerator's clothes."""
    d = project()
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    srv = server_on(tmp, s)
    try:
        registry.register(d)
        served = talk(srv, {"id": 1, "op": "ls", "project": str(d)})[0]["data"]
        local = ticket_rows(d)
        assert served == local, (served, local)
        assert {"stale", "leased", "last_session"} <= set(local[0])
    finally:
        srv.close()
        registry.unregister(d)


def test_an_expired_lease_reads_as_stale_not_as_leased():
    """`release_lease()` nulls `expires`; an expiry does not. So a dead lease
    still HAS an `expires`, and anything testing that key instead of
    `lease_active()` hides exactly the crashed-dispatcher case `ls` exists to
    surface."""
    d = project()
    t = Ticket.find(d, "TICKET-001")
    t.lease = {"holder": f"planning-{os.getpid()}",
               "expires": "2020-01-01T00:00:00+00:00"}
    t.save()
    old = time.time() - 5 * 3600
    os.utime(d / ".project/tickets/TICKET-001.md", (old, old))

    row = ticket_rows(d)[0]
    assert row["lease"]["expires"], "the fixture must still carry a dead lease"
    assert row["leased"] is False and row["stale"] is True, row

    r = subprocess.run([sys.executable, "-m", "pipeline", "--project", str(d), "ls"],
                       cwd=ROOT, capture_output=True, text=True)
    assert "STALE" in r.stdout and "LEASED" not in r.stdout, r.stdout


def test_ls_with_no_project_covers_every_registered_project():
    """`--project` is a filter. Without one, the fallback must not silently
    narrow to the cwd -- that reports "nothing is running" for a machine that
    is busy."""
    a, b = project(), project()
    try:
        registry.register(a)
        registry.register(b)
        rows = [r for p in registry.projects() for r in ticket_rows(p)]
        assert {r["project"] for r in rows} == {str(a), str(b)}
        r = subprocess.run([sys.executable, "-m", "pipeline", "ls"],
                           cwd=tempfile.mkdtemp(), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert r.stdout.count("TICKET-001") == 2, r.stdout
    finally:
        registry.unregister(a)
        registry.unregister(b)


def test_a_too_long_socket_path_says_so_instead_of_raising_oserror():
    """AF_UNIX caps the path at ~108 bytes and bind() reports it as a bare
    OSError naming nothing. A long $XDG_RUNTIME_DIR is a plausible thing to
    have, so the limit is checked up front and the error names the way out."""
    d = Path(tempfile.mkdtemp())
    long_path = d / ("x" * 200) / "daemon.sock"
    store = Store(d / "events.db")
    try:
        Server(store, long_path)
        assert False, "bound a socket path AF_UNIX cannot hold"
    except PipelineError as e:
        assert "too long for AF_UNIX" in str(e), e
        assert "--socket" in str(e), "the error does not name the way out"
    except OSError as e:
        assert False, f"leaked a bare OSError instead of explaining: {e}"
    finally:
        store.close()
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------
# integration: the seams between 011, 012 and 013
# --------------------------------------------------------------------------
def _pump_fixture(sink) -> None:
    """Drive the real `pump()` over the stream fixture on a real pipe, with a
    spawn-shaped record. Not `reader.feed()` directly: the sink is only
    reachable through `pump`, which is the code path that was empty."""
    tmp = Path(tempfile.mkdtemp())
    r, w = os.pipe()
    os.write(w, (ROOT / "tests/fixtures/stream-planning.ndjson").read_bytes())
    os.close(w)
    os.set_blocking(r, False)
    rec = {"proc": None, "fh": (tmp / "x.log").open("wb"), "log": tmp / "x.log",
           "poller": None, "pipe": os.fdopen(r, "rb", 0),
           "reader": StreamReader(), "sink": sink}
    supervisor.pump(rec)
    supervisor.close_child(rec)


def test_parsed_stream_events_reach_the_event_log():
    """TICKET-012 parses stream-json, TICKET-011 stores events, and nothing
    connected them: `rec["sink"]` dropped every record, so `result` and
    `hook_response` never landed and metrics views 3 and 5 read "no data"
    against a live system."""
    tmp = Path(tempfile.mkdtemp())
    s = store(tmp)
    _pump_fixture(supervisor.event_sink("TICKET-001", "planning", "sess-1",
                                        s.emitter("/p")))
    rows = s.since(0)
    kinds = [r["kind"] for r in rows]
    assert "result" in kinds and "hook_response" in kinds, kinds
    assert "other" not in kinds, "an unparseable line must not become a row"

    hook = [r for r in rows if r["kind"] == "hook_response"][0]
    # the guard biting: the one event a human actually wants to watch live
    assert hook["data"]["exit_code"] == 2, hook
    assert "guard" in hook["data"]["stderr"], hook
    assert (hook["ticket"], hook["stage"], hook["session"]) == \
        ("TICKET-001", "planning", "sess-1"), hook
    assert [r for r in rows if r["kind"] == "result"][0]["data"]["total_cost_usd"] \
        == 0.3412

    # an emit that raises is history lost, never a stranded lease
    def boom(kind, **kw):
        raise sqlite3.OperationalError("disk I/O error")
    _pump_fixture(supervisor.event_sink("TICKET-001", "planning", "s", boom))
    s.close()


def test_spawn_wires_the_sink_to_the_store():
    """The gap was in `spawn()`, not in the sink: a record whose `sink` still
    defaults to dropping stores nothing however good the sink is."""
    from pipeline.core.config import harness
    d = project()
    s = store(Path(tempfile.mkdtemp()))
    rec = supervisor.spawn(d, d, "TICKET-001", "review", harness("fake"),
                           None, s.emitter(str(d)))
    rec["proc"].wait()
    supervisor.close_child(rec)
    rec["sink"]({"kind": "result", "total_cost_usd": 1.5})
    rec["sink"]({"kind": "other", "raw_type": None})
    got = [r for r in s.since(0) if r["kind"] == "result"]
    assert len(got) == 1 and got[0]["data"]["total_cost_usd"] == 1.5, s.since(0)
    assert got[0]["stage"] == "review" and got[0]["session"] == rec["session"]
    s.close()
    shutil.rmtree(d, ignore_errors=True)


TRANSCRIPT = """\
{"type":"assistant","message":{"model":"claude-opus-4-5","usage":{"input_tokens":10,\
"output_tokens":2,"cache_read_input_tokens":100,"cache_creation_input_tokens":7}}}
{"type":"user","message":{"role":"user","content":"no usage here"}}
{"type":"assistant","message":{"model":"claude-opus-4-5","usage":{"input_tokens":20,\
"output_tokens":3}}}
{"type":"assistant","message":{"model":"claude-haiku-4-5","usage":{"input_tokens":1,\
"output_tokens":1}}}
not json at all
"""


def _with_home(home: Path, fn):
    old = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        return fn()
    finally:
        os.environ["HOME"] = old or ""


def test_a_pty_stage_bills_from_its_session_transcript():
    """An interactive stage never gets a `result` event, so its cost is not in
    the stream at all. The transcript has no cost key at any depth either --
    but every assistant line has `message.model` and `message.usage`, and the
    file is found by globbing the session uuid rather than reimplementing the
    cwd-to-slug rule."""
    home = Path(tempfile.mkdtemp())
    sess = "6f1c0a2e-1111-4c5f-9a3d-0b2e4d6f8a10"
    # a worktree slug with the dots and `.worktrees` that make the rule
    # not worth reimplementing
    d = home / ".claude/projects/-home-u-proj-worktrees-t-001-v1.2"
    d.mkdir(parents=True)
    (d / f"{sess}.jsonl").write_text(TRANSCRIPT)

    got = {u["model"]: u for u in _with_home(home,
                                             lambda: supervisor.usage_events(sess))}
    assert got["claude-opus-4-5"] == {
        "model": "claude-opus-4-5", "input_tokens": 30, "output_tokens": 5,
        "cache_read": 100, "cache_creation": 7}, got
    assert got["claude-haiku-4-5"]["input_tokens"] == 1, got
    # a stage that died before writing one is not an error
    assert _with_home(home, lambda: supervisor.usage_events("no-such-session")) == []


def test_finish_emits_usage_for_an_interactive_stage_only():
    """The wiring, not the parser: `finish()` is where a PTY stage's cost has
    to be billed, because nothing else knows the stage is over."""
    home = Path(tempfile.mkdtemp())
    sess = "6f1c0a2e-1111-4c5f-9a3d-0b2e4d6f8a10"
    d = home / ".claude/projects/-p"
    d.mkdir(parents=True)
    (d / f"{sess}.jsonl").write_text(TRANSCRIPT)

    def run(mode):
        proj = project()
        s = store(Path(tempfile.mkdtemp()))
        path = proj / ".project/tickets/TICKET-001.md"
        log = proj / "x.log"
        rec = {"proc": types.SimpleNamespace(returncode=0, pid=1),
               "fh": log.open("wb"), "log": log, "poller": None, "pipe": None,
               "reader": None, "sink": lambda ev: None, "prompt": None,
               "settings": None, "path": path, "tid": "TICKET-001",
               "stage": "planning", "session": sess, "wt": proj,
               "meta": Ticket.load(path), "before": None, "mode": mode}
        supervisor.finish(proj, rec, s.emitter(str(proj)))
        out = [r for r in s.since(0) if r["kind"] == "usage"]
        s.close()
        shutil.rmtree(proj, ignore_errors=True)
        return out

    got = _with_home(home, lambda: run("interactive"))
    assert {u["data"]["model"] for u in got} == {"claude-opus-4-5",
                                                "claude-haiku-4-5"}, got
    assert got[0]["ticket"] == "TICKET-001" and got[0]["stage"] == "planning"
    # a headless stage's `result` event is authoritative -- billing it twice
    # from the transcript as well would double every merged ticket's cost
    assert _with_home(home, lambda: run("batch")) == []
