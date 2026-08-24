"""The socket server, and the select loop the whole daemon is built around.

The supervisor's tick used to end in `time.sleep()`. It now ends in
`Poller.poll()`, and everything that wants the daemon's attention -- a client
socket, a child's stdout, a PTY master -- is an fd registered with `watch()`.
No threads, no asyncio, no locks: one loop, one process, and adding a new
source of events is two lines at the call site instead of a rewrite here.

`watch(fd, callback)` / `unwatch(fd)` are the extension point. Callbacks take
the fd and must not block.
"""
import base64
import binascii
import errno
import fcntl
import json
import os
import selectors
import socket
import stat
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import __version__
from pipeline.core import PipelineError
from pipeline.core.machine import HUMAN_GATES, TERMINAL
from pipeline.core.ticket import Ticket, all_tickets, lease_expiry, now
# `lease_expiry()` is reused as this codebase's one total ISO parser: a
# hand-edited `waiting.since` must not raise inside `ls`.
from pipeline.daemon import registry
from pipeline.pty import host

OUTBOX = 1000    # events per connection before the oldest is dropped
MAX_CONNS = 64   # clients; past this, accept-and-refuse rather than run out of fds
MAX_SUBS = 8     # subscriptions per connection
OPS = ("ping", "ls", "projects", "subscribe", "kill",
       "attach", "input", "resize", "detach")
MAX_DIM = host.MAX_DIM   # one bound for the ioctl, the pyte allocation and the log marker
PTY_BACKLOG = 16  # outbox depth past which PTY frames are the ones dropped.
                  # NOT a pty-only queue: `conn.out` is shared with event and
                  # replay frames, and the pty is what yields, because OUTBOX
                  # was sized for small event objects while a pty frame is a
                  # 64 KiB read, base64'd. Our pyte screen is authoritative,
                  # so a dropped frame costs one re-attach; a dropped event is
                  # gone.
PTY_INPUT = 4096  # one write into a pty's input buffer. Larger short-writes,
                  # and a silently truncated paste into an approval prompt is
                  # worse than an error the client can chunk around
MAX_LINE = 1 << 20
STALE_HOURS = 4  # overlap ordering now reports itself in `waiting`; this bound
                 # still surfaces a ticket sitting still for any other reason
SENT = object()   # "this op already queued its own frames" -- see _op_subscribe

# sizeof(sockaddr_un.sun_path): 108 on Linux, 104 on macOS and the BSDs.
SUN_PATH_MAX = 104 if sys.platform != "linux" else 108


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


def _dim(req: dict, key: str) -> int:
    """Values off a socket reach `ioctl` and a pyte allocation. Bounded."""
    try:
        v = int(req[key])
    except (KeyError, TypeError, ValueError):
        raise PipelineError(f"resize needs an integer {key}") from None
    if not 1 <= v <= MAX_DIM:
        raise PipelineError(f"{key}={v} out of range (1..{MAX_DIM})")
    return v


def waiting_text(w) -> str:
    """`ls`'s one-line rendering of a `waiting` reason, or `""` for none."""
    if not (isinstance(w, dict) and w.get("on") and w.get("file")):
        return ""
    text = f"waiting on {w['on']} ({w['file']})"
    since = lease_expiry(w.get("since"))
    if since is None:
        return text
    m = int((now() - since).total_seconds() // 60)
    return text + (f" {m}m" if m < 60 else f" {m // 60}h")


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
            rec = inflight.get(t.id)
            summary = t.section("Summary").strip().splitlines()
            leased = t.lease_active()   # NOT `lease.expires`: release_lease()
                                        # nulls it, an expiry does not, so a
                                        # dead lease still has one and would
                                        # read as held
            out.append({
                "project": str(project), "id": t.id, "stage": t.stage,
                "class": t.klass, "counters": t.counters, "lease": t.lease,
                "running": rec is not None, "leased": leased,
                "stale": (t.stage not in TERMINAL | HUMAN_GATES and not leased
                          and now() - datetime.fromtimestamp(path.stat().st_mtime,
                                                             timezone.utc)
                          > timedelta(hours=STALE_HOURS)),
                "last_session": t.extra.get("last_session"),
                # the dispatcher's last observation, advisory display only --
                # never read back as control flow
                "waiting": w if isinstance(w := t.extra.get("waiting"), dict) else None,
                "mode": (rec or {}).get("mode", "batch"),
                "title": summary[0] if summary else ""})
        except Exception as e:
            # Exception, not PipelineError, and around the WHOLE row: `_op_ls`
            # answers for every project at once, so anything one ticket raises
            # -- frontmatter nobody can parse, a lease nobody can read, a file
            # deleted mid-listing -- would otherwise blank the listing for all
            # of them, and `cmd_ls`'s file fallback would re-raise past the
            # CLI's handler. The row says so instead.
            out.append({"project": str(project), "id": path.stem,
                        "stage": "unreadable", "error": str(e)})
    return out


class Poller:
    """`watch`/`unwatch`/`poll` over one selector. The Server is this plus a
    listening socket; `pipeline run` standalone uses the bare Poller, which is
    what keeps the child-stdout pipe drained with no daemon in sight."""

    # Can a human reach a child hosted here? A bare Poller has no socket, so
    # nothing can ever `attach` to a PTY it drains -- which is exactly the
    # question `spawn()` has to answer before it starts a stage nobody could
    # steer. `poller is not None` was the wrong test: `run()` passes one.
    attachable = False

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
        self.attached: tuple | None = None   # (project, ticket, session)
        self.pty_sub = None                  # the id its `pty` frames carry
        self.pty_cb = None                   # this conn's entry in Screen.subs

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
    attachable = True   # there is a socket: `attach`/`input` can reach a PTY

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
        # AF_UNIX caps the path at `sizeof(sun_path)`, and the failure is an
        # opaque OSError from bind() rather than anything naming the cause.
        # Check it up front: a long $XDG_RUNTIME_DIR is a plausible thing to
        # have, and `--socket` is the way out. The cap is not the same
        # everywhere -- 108 on Linux, 104 on the BSDs and macOS -- so take the
        # smaller one rather than let a 105-byte path bind on one box and
        # raise a bare OSError on the next.
        if len(str(self.path).encode()) >= SUN_PATH_MAX:
            raise PipelineError(
                f"socket path is too long for AF_UNIX ({len(str(self.path).encode())} "
                f"bytes, limit {SUN_PATH_MAX - 1}): {self.path}\n"
                f"pass a shorter --socket, or set $XDG_RUNTIME_DIR")
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
    def poll(self, timeout: float) -> None:
        """Re-arm the listener, then poll.

        `_accept` steps off the listener on EMFILE/ENFILE -- a level-triggered
        listener with no free fd is a 100% spin -- and the only other re-arm
        is a client disconnecting. With the fds exhausted by children and no
        client connected, nothing ever re-armed it: `status`, `tui`, `attach`
        and `kill` stayed dead until a restart, long after the fds freed. One
        dict lookup per pass buys the recovery.
        """
        if self.sock.fileno() not in self.sel.get_map():
            self.watch(self.sock.fileno(), lambda fd: self._accept())
        super().poll(timeout)

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
            self._detach(conn)   # frees the writer slot; never touches the child
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

    def _running(self, req) -> tuple[str, dict]:
        """(project, in-flight record) for one ticket. `project` is a filter
        like everywhere else: absent means "whichever project it is in"."""
        want = self._project(req)
        tid = req.get("ticket")
        for proj, inflight in self.states.items():
            if want and proj != want:
                continue
            rec = inflight.get(tid)
            if rec:
                return proj, rec
        raise PipelineError(f"{tid} is not running")

    def _op_kill(self, conn, rid, req) -> dict:
        proj, rec = self._running(req)
        rec["proc"].terminate()
        return {"ticket": rec["tid"], "project": proj, "pid": rec["proc"].pid}

    # -- interactive stages ------------------------------------------------
    def _pty(self, conn: Conn) -> dict:
        """The record this connection is attached to. A stage that has since
        finished is an error on the next op, not a dangling subscription."""
        if conn.attached is None:
            raise PipelineError("not attached")
        proj, tid, session = conn.attached
        rec = self.states.get(proj, {}).get(tid)
        # the SESSION, not just the ticket: `planning` can finish and the next
        # interactive stage for the same ticket start before this client
        # notices. Matching on the name alone would silently rebind it -- input
        # into a terminal it cannot see, and the new session's writer slot held
        # by someone watching a dead screen.
        if (rec is None or rec.get("screen") is None or rec.get("pipe") is None
                or rec.get("session") != session):
            self._detach(conn)
            raise PipelineError(f"{tid} is no longer running")
        return rec

    def _writer(self, rec: dict, conn: Conn) -> bool:
        """One writer: one variable and one comparison, deliberately. The slot
        frees when its holder detaches or disconnects, and the next `input`
        from any attached client claims it -- no lease, no priorities."""
        w = rec.get("writer")
        if w is not None and w is not conn and self.conns.get(w.sock.fileno()) is w:
            return False
        rec["writer"] = conn
        return True

    def _detach(self, conn: Conn) -> None:
        """Detach touches nothing but this connection. The daemon owns the
        master fd, so a client going away cannot end a session -- which is the
        entire point of hosting the PTY here."""
        if conn.attached is None:
            return
        proj, tid, session = conn.attached
        conn.attached = None
        rec = self.states.get(proj, {}).get(tid) or {}
        if rec.get("session") != session:
            rec = {}          # a different session by now: nothing of ours in it
        screen = rec.get("screen")
        if screen is not None and conn.pty_cb in screen.subs:
            screen.subs.remove(conn.pty_cb)
        if rec.get("writer") is conn:
            rec["writer"] = None
        conn.pty_cb = conn.pty_sub = None

    def _op_attach(self, conn, rid, req) -> dict:
        proj, rec = self._running(req)
        if rec.get("screen") is None:
            raise PipelineError(f"{rec['tid']} is running `{rec['stage']}` "
                                f"headless -- only an interactive stage can be attached")
        self._detach(conn)                    # one PTY per connection
        screen = rec["screen"]
        conn.attached = (proj, rec["tid"], rec.get("session"))
        conn.pty_sub = rid
        conn.pty_cb = lambda chunk: self._pty_out(conn, rid, chunk)
        screen.subs.append(conn.pty_cb)
        return {"screen": list(screen.display), "writer": self._writer(rec, conn),
                "rows": screen.rows, "cols": screen.cols,
                "ticket": rec["tid"], "project": proj, "stage": rec["stage"]}

    def _pty_out(self, conn: Conn, sid, chunk: bytes) -> None:
        if len(conn.out) >= PTY_BACKLOG:
            # a client that stopped reading -- a suspended TUI, a stalled ssh
            # pane -- must not cost the daemon 1000 * 87 KiB. Drop the chunk
            # and charge the counter; the marker below tells it to re-attach,
            # and our pyte screen is authoritative anyway.
            conn.dropped += 1
            return
        if conn.dropped:
            # a wedged client lost frames, so its terminal emulation is now
            # desynced from ours. Zero FIRST (the marker goes through the same
            # full outbox), then say so: `attach` again for a fresh screen,
            # which is authoritative here and costs one round trip.
            n, conn.dropped = conn.dropped, 0
            conn.send({"sub": sid, "dropped": n})
        conn.send({"sub": sid, "pty": base64.b64encode(chunk).decode()})
        self._pump(conn)

    def _op_input(self, conn, rid, req) -> dict:
        rec = self._pty(conn)
        try:
            data = base64.b64decode(req.get("data") or "", validate=True)
        except (binascii.Error, ValueError) as e:
            # decode BEFORE claiming: a junk frame must not take the writer slot
            raise PipelineError(f"data must be base64: {e}") from None
        if len(data) > PTY_INPUT:
            # a pty's input buffer is a few KiB and the master is non-blocking,
            # so a larger write short-writes and truncates mid-keystroke
            raise PipelineError(f"input is {len(data)} bytes; send at most "
                                f"{PTY_INPUT} per op")
        if not self._writer(rec, conn):
            raise PipelineError("another client holds the writer")
        n = os.write(rec["pipe"].fileno(), data)
        # still possible on an already-full buffer: say so rather than let the
        # client assume every byte landed
        return {"written": n, "short": n < len(data)}

    def _op_resize(self, conn, rid, req) -> dict:
        """MUST-HAVE, not a nicety: a pane and a child that disagree about
        width render garbage. Writer-only, because it reshapes the terminal
        the writer is typing into."""
        rec = self._pty(conn)
        # bounds BEFORE claiming, exactly as `input` decodes first: a junk
        # frame must not take a free writer slot on its way to an error
        rows, cols = _dim(req, "rows"), _dim(req, "cols")
        if not self._writer(rec, conn):
            raise PipelineError("another client holds the writer")
        host.set_winsize(rec["pipe"].fileno(), rows, cols)
        rec["screen"].resize(rows, cols)
        # same point the live screen resizes, so a replay reproduces that
        # screen instead of reflowing bytes the daemon fed after the resize
        rec["fh"].write(host.geom_marker(rows, cols))
        rec["fh"].flush()
        return {"rows": rows, "cols": cols}

    def _op_detach(self, conn, rid, req) -> dict:
        was = conn.attached
        self._detach(conn)
        return {"detached": was[1] if was else None}

