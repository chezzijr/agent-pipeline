"""The socket server, and the select loop the whole daemon is built around.

The supervisor's tick used to end in `time.sleep()`. It now ends in
`Poller.poll()`, and everything that wants the daemon's attention -- a client
socket, a child's stdout, a PTY master -- is an fd registered with `watch()`.
No threads, no asyncio, no locks: one loop, one process, and adding a new
source of events is two lines at the call site instead of a rewrite here.

`watch(fd, callback)` / `unwatch(fd)` are the extension point. Callbacks take
the fd and must not block.
"""
import errno
import fcntl
import json
import os
import selectors
import socket
import stat
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import __version__
from pipeline.core import PipelineError
from pipeline.core.machine import HUMAN_GATES, TERMINAL
from pipeline.core.ticket import Ticket, all_tickets, now
from pipeline.daemon import registry

OUTBOX = 1000    # events per connection before the oldest is dropped
MAX_CONNS = 64   # clients; past this, accept-and-refuse rather than run out of fds
MAX_SUBS = 8     # subscriptions per connection
OPS = ("ping", "ls", "projects", "subscribe", "kill")
MAX_LINE = 1 << 20
STALE_HOURS = 4  # overlap ordering is silent; surface anything sitting still
SENT = object()   # "this op already queued its own frames" -- see _op_subscribe


def runtime_dir() -> Path:
    """`$XDG_RUNTIME_DIR/pipeline`, or a `0700` dir under /tmp that we check
    actually belongs to us and is not a symlink someone planted first."""
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    p = Path(xdg) / "pipeline" if xdg else Path(f"/tmp/pipeline-{os.getuid()}")
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = os.lstat(p)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise PipelineError(f"{p} is not a directory -- refusing to bind there")
    if st.st_uid != os.getuid():
        raise PipelineError(f"{p} is owned by uid {st.st_uid}, not {os.getuid()}")
    return p


def socket_path() -> Path:
    return runtime_dir() / "daemon.sock"


def ticket_rows(project: Path, inflight: dict | None = None) -> list[dict]:
    """One row per ticket in one project.

    The single source for `ls`, deliberately: the daemon serves these rows over
    the socket and the CLI builds the identical ones from the files when no
    daemon answers. Two implementations would let the same command give two
    different answers depending on whether a daemon happened to be up, which is
    exactly what "the daemon is an accelerator, never a dependency" forbids.
    """
    inflight = inflight or {}
    out = []
    for path in all_tickets(project):
        try:
            t = Ticket.load(path)
        except PipelineError as e:
            out.append({"project": str(project), "id": path.stem,
                        "stage": "unreadable", "error": str(e)})
            continue
        rec = inflight.get(t.id)
        summary = t.section("Summary").strip().splitlines()
        leased = t.lease_active()   # NOT `lease.expires`: release_lease() nulls
                                    # it, an expiry does not, so a dead lease
                                    # still has one and would read as held
        out.append({
            "project": str(project), "id": t.id, "stage": t.stage,
            "class": t.klass, "counters": t.counters, "lease": t.lease,
            "running": rec is not None, "leased": leased,
            "stale": (t.stage not in TERMINAL | HUMAN_GATES and not leased
                      and now() - datetime.fromtimestamp(path.stat().st_mtime,
                                                         timezone.utc)
                      > timedelta(hours=STALE_HOURS)),
            "last_session": t.extra.get("last_session"),
            "mode": (rec or {}).get("mode", "batch"),
            "title": summary[0] if summary else ""})
    return out


class Poller:
    """`watch`/`unwatch`/`poll` over one selector. The Server is this plus a
    listening socket; `pipeline run` standalone uses the bare Poller, which is
    what keeps the child-stdout pipe drained with no daemon in sight."""

    def __init__(self) -> None:
        self.sel = selectors.DefaultSelector()

    def watch(self, fd: int, callback) -> None:
        """Call `callback(fd)` whenever `fd` is readable. Re-registering an fd
        replaces its callback."""
        self.unwatch(fd)
        self.sel.register(fd, selectors.EVENT_READ, callback)

    def unwatch(self, fd: int) -> None:
        """Idempotent, and safe on an fd that has already been closed."""
        try:
            self.sel.unregister(fd)
        except (KeyError, ValueError, OSError):
            pass

    def poll(self, timeout: float) -> None:
        """Service whatever became readable. This replaces the loop's sleep."""
        for key, _ in self.sel.select(timeout):
            try:
                key.data(key.fd)
            except Exception as e:   # one wedged fd must not stop the loop
                print(f"  poll: {key.fd}: {e.__class__.__name__}: {e}")

    def close(self) -> None:
        self.sel.close()


class Conn:
    """One client. Non-blocking both ways, with a bounded outbox: a TUI that
    stops reading gets its oldest events dropped, it does not stall the
    supervisor. Liveness boundary, not a nicety."""

    # ponytail: single select loop, bounded outbox; per-client threads if a
    # viewer ever needs guaranteed delivery

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        sock.setblocking(False)
        self.inbuf = b""
        self.out: deque[bytes] = deque(maxlen=OUTBOX)
        self.pending = b""      # a partially-sent frame
        self.dropped = 0
        self.subs: dict[int, dict] = {}   # sub id -> {"project": str|None}

    def send(self, obj: dict) -> None:
        if len(self.out) == self.out.maxlen:
            self.dropped += 1
        self.out.append((json.dumps(obj, default=str) + "\n").encode())

    def flush(self) -> bool:
        """True while there is more to write. Never blocks."""
        while self.pending or self.out:
            if not self.pending:
                self.pending = self.out.popleft()
            try:
                n = self.sock.send(self.pending)
            except (BlockingIOError, InterruptedError):
                return True
            except OSError:
                self.out.clear()
                self.pending = b""
                return False
            self.pending = self.pending[n:]
            if self.pending:
                return True
        return False


class Server(Poller):
    def __init__(self, store, path: Path | None = None) -> None:
        super().__init__()
        self.store = store
        self.path = Path(path) if path else socket_path()
        self.conns: dict[int, Conn] = {}
        # set by serve(): project str -> its in-flight record dict. `ls` reads
        # `running` off it and `kill` reaches the child through it.
        self.states: dict[str, dict] = {}
        self.lock = self._claim()
        self.sock = self._bind()
        self.watch(self.sock.fileno(), lambda fd: self._accept())
        store.listeners.append(self._broadcast)

    # -- lifecycle ---------------------------------------------------------
    def _claim(self):
        """The exclusive claim on being *the* daemon.

        A probe ("can I connect to the existing socket?") is evidence, never a
        claim: two daemons starting in the same millisecond both probe, both
        see refused, and the second unlinks the first's live socket out from
        under it. `flock` is the claim -- the same primitive the per-project
        lock uses, kernel-released on crash, so there is no stale lockfile to
        reason about. Everything below runs while we hold it.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fh = self.path.with_name(self.path.name + ".lock").open("w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            raise PipelineError(
                f"a daemon is already listening on {self.path}") from None
        return fh

    def _bind(self) -> socket.socket:
        """Under `_claim()`, a socket file left on disk can only be litter from
        a daemon that is already gone -- so it is safe to unlink. The connect
        probe stays as a belt-and-braces check for a daemon predating the lock
        file."""
        if self.path.exists():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.connect(str(self.path))
            except OSError as e:
                if e.errno not in (errno.ECONNREFUSED, errno.ENOENT):
                    raise PipelineError(f"{self.path}: {e}") from e
                self.path.unlink(missing_ok=True)
            else:
                raise PipelineError(f"a daemon is already listening on {self.path}")
            finally:
                probe.close()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # umask around bind(), not chmod after: chmod leaves a window in which
        # the socket is world-connectable, and this socket can kill children.
        old = os.umask(0o077)
        try:
            s.bind(str(self.path))
        finally:
            os.umask(old)
        s.listen(64)
        s.setblocking(False)
        return s

    def close(self) -> None:
        # first: a closed server left on the store's listener list keeps
        # receiving events and writing into dead sockets
        if self._broadcast in self.store.listeners:
            self.store.listeners.remove(self._broadcast)
        for c in list(self.conns.values()):
            c.sock.close()
        self.conns.clear()
        self.sock.close()
        self.path.unlink(missing_ok=True)
        super().close()
        self.lock.close()

    # -- plumbing ----------------------------------------------------------
    def _accept(self) -> None:
        while True:
            try:
                sock, _ = self.sock.accept()
            except (BlockingIOError, InterruptedError):
                return
            except OSError as e:
                # EMFILE/ENFILE with a level-triggered listener is a live-lock:
                # select() returns readable immediately, forever, and the loop
                # spins at 100% without ever polling a child's pipe. Step off
                # the listener; a closing client re-arms it.
                print(f"  accept: {e}")
                self.unwatch(self.sock.fileno())
                return
            if len(self.conns) >= MAX_CONNS:
                # refuse politely rather than run the daemon out of the fds its
                # children need. The client sees a closed connection and falls
                # back to reading ticket files.
                sock.close()
                continue
            conn = Conn(sock)
            self.conns[sock.fileno()] = conn
            self.watch(sock.fileno(), self._readable)

    def _readable(self, fd: int) -> None:
        conn = self.conns.get(fd)
        if conn is None:
            self.unwatch(fd)
            return
        try:
            chunk = conn.sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            chunk = b""
        if not chunk:
            return self._drop(fd)
        conn.inbuf += chunk
        if len(conn.inbuf) > MAX_LINE:
            return self._drop(fd)
        *lines, conn.inbuf = conn.inbuf.split(b"\n")
        for line in lines:
            if line.strip():
                self._handle_line(conn, line.decode("utf-8", "replace"))
        self._pump(conn)

    def _drop(self, fd: int) -> None:
        conn = self.conns.pop(fd, None)
        self.unwatch(fd)
        if conn is not None:
            conn.sock.close()
        self.watch(self.sock.fileno(), lambda _fd: self._accept())  # re-arm

    def _pump(self, conn: Conn) -> None:
        """Write what we can. Anything left waits for the next poll rather than
        blocking the loop -- worst case it ages out of the bounded outbox."""
        self._arm(conn, conn.flush())

    def _arm(self, conn: Conn, write: bool) -> None:
        fd = conn.sock.fileno()
        if fd not in self.conns:
            return
        events = selectors.EVENT_READ | (selectors.EVENT_WRITE if write else 0)
        cb = self._writable if write else self._readable
        try:
            self.sel.modify(fd, events, cb)
        except KeyError:
            self.sel.register(fd, events, cb)

    def _writable(self, fd: int) -> None:
        """Registered for READ|WRITE, so this also has to serve reads."""
        conn = self.conns.get(fd)
        if conn is None:
            return self.unwatch(fd)
        self._arm(conn, conn.flush())
        self._readable(fd)

    def _broadcast(self, ev: dict) -> None:
        """Store listener: fan one committed event out to every subscription
        that asked for its project."""
        for conn in list(self.conns.values()):
            for sid, sub in conn.subs.items():
                if sub["project"] and sub["project"] != ev["project"]:
                    continue
                if conn.dropped:
                    # zero it FIRST: the marker itself goes through a full
                    # outbox and would otherwise re-charge the counter we are
                    # about to clear, so the client would be told "1" forever
                    n, conn.dropped = conn.dropped, 0
                    conn.send({"sub": sid, "dropped": n})
                conn.send({"sub": sid, "event": ev})
            self._pump(conn)

    # -- ops ---------------------------------------------------------------
    def _handle_line(self, conn: Conn, line: str) -> None:
        """One request line -> one reply queued. Total: every path answers,
        because a client blocked on a reply that never comes is worse than an
        error it can print."""
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("request is not an object")
        except ValueError as e:
            return conn.send({"id": None, "ok": False, "error": f"bad json: {e}"})
        rid, op = req.get("id"), req.get("op")
        if op not in OPS:
            return conn.send({"id": rid, "ok": False,
                              "error": f"unknown op {op!r}; want one of {', '.join(OPS)}"})
        try:
            data = getattr(self, f"_op_{op}")(conn, rid, req)
            if data is not SENT:
                conn.send({"id": rid, "ok": True, "data": data})
        except PipelineError as e:
            conn.send({"id": rid, "ok": False, "error": str(e)})
        except Exception as e:
            conn.send({"id": rid, "ok": False,
                       "error": f"{e.__class__.__name__}: {e}"})

    def _project(self, req: dict) -> str | None:
        """`--project` is a filter, not a target. Unregistered is an error, not
        an empty list -- a typo must not read as "nothing is running"."""
        p = req.get("project")
        if p in (None, ""):
            return None
        p = str(Path(p).resolve())
        if Path(p) not in registry.projects():
            raise PipelineError(f"project not registered: {p}")
        return p

    def _op_ping(self, conn, rid, req) -> dict:
        return {"pid": os.getpid(), "version": __version__,
                "socket": str(self.path), "projects": len(self.states)}

    def _op_projects(self, conn, rid, req) -> list:
        return [{"project": str(p), "watched": str(p) in self.states}
                for p in registry.projects()]

    def _op_ls(self, conn, rid, req) -> list:
        want = self._project(req)
        return [row for p in registry.projects()
                if not want or str(p) == want
                for row in ticket_rows(p, self.states.get(str(p), {}))]

    def _op_subscribe(self, conn, rid, req) -> dict:
        if not isinstance(rid, int):
            raise PipelineError("subscribe needs an integer id to tag its events")
        want = self._project(req)
        # everything that can fail is resolved BEFORE the success frame is
        # queued: this op sends its own reply, so a later raise would put an
        # `ok:true` and an `ok:false` on the wire under the same id
        since = req.get("since")
        if since is not None:
            try:
                since = int(since)
            except (TypeError, ValueError):
                raise PipelineError(f"since must be an integer id, got {since!r}")
        if len(conn.subs) >= MAX_SUBS and rid not in conn.subs:
            raise PipelineError(f"at most {MAX_SUBS} subscriptions per connection")
        conn.subs[rid] = {"project": want}
        # The reply first, then the replay, then live events -- so this op
        # queues its own frames rather than letting `_handle_line` append the
        # reply after them. One thread, so nothing can be emitted in between
        # and nothing arrives twice: a reconnecting client passes its last-seen
        # id and misses none.
        conn.send({"id": rid, "ok": True, "data": {"cursor": self.store.cursor()}})
        if since is not None:
            for ev in self.store.since(since, project=want):
                conn.send({"sub": rid, "event": ev})
        return SENT

    def _op_kill(self, conn, rid, req) -> dict:
        want = self._project(req)
        tid = req.get("ticket")
        for proj, inflight in self.states.items():
            if want and proj != want:
                continue
            rec = inflight.get(tid)
            if rec:
                rec["proc"].terminate()
                return {"ticket": tid, "project": proj, "pid": rec["proc"].pid}
        raise PipelineError(f"{tid} is not running")
