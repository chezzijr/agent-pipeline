"""Talking to the daemon, and doing without it.

Every client call has a file-based fallback, because the ticket files are the
source of truth and the daemon only ever knew what it read from them. A
daemon that is not running must cost you liveness, never an answer.
"""
import json
import socket
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.daemon.server import socket_path


class Client:
    """One request/reply connection. NDJSON, one object per line."""

    def __init__(self, path: Path | None = None, timeout: float = 5.0) -> None:
        self.path = Path(path) if path else socket_path()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(str(self.path))
        self.fh = self.sock.makefile("rwb")
        self._id = 0

    def send(self, op: str, **kw) -> int:
        self._id += 1
        self.fh.write((json.dumps({"id": self._id, "op": op, **kw}) + "\n").encode())
        self.fh.flush()
        return self._id

    def lines(self):
        """Every frame the daemon sends, forever. Subscriptions live here."""
        for raw in self.fh:
            if raw.strip():
                yield json.loads(raw)

    def request(self, op: str, **kw):
        """One round trip. A daemon that hangs, dies mid-reply or answers
        garbage becomes a `PipelineError` -- the CLI has a fallback for that
        and no fallback for a traceback."""
        try:
            rid = self.send(op, **kw)
            for msg in self.lines():
                if msg.get("id") != rid:
                    continue        # an event for an earlier subscription
                if not msg.get("ok"):
                    raise PipelineError(msg.get("error", "daemon refused"))
                return msg.get("data")
        except (OSError, ValueError) as e:   # timeout, reset, unparseable frame
            raise PipelineError(f"daemon: {e}") from e
        raise PipelineError("daemon closed the connection without replying")

    def clone(self, timeout: float | None = None) -> "Client":
        """A second connection to the same daemon.

        A subscription owns its connection: `lines()` blocks until the daemon
        speaks, so a `request()` on the same socket would consume the
        subscription's frames. The default `timeout=None` is what a subscriber
        wants -- an idle pipeline is not a dead one, and a 5s deadline would
        end the stream every time nothing happened.
        """
        return Client(self.path, timeout)

    def close(self) -> None:
        self.fh.close()
        self.sock.close()


def connect(path: Path | None = None, timeout: float = 5.0) -> Client | None:
    """The daemon, or None if there isn't one. Callers fall back; they do not
    fail. `ENOENT` is "never started", `ECONNREFUSED` is "died and left its
    socket file behind" -- both mean the same thing to a client."""
    try:
        return Client(path, timeout)
    except (FileNotFoundError, ConnectionRefusedError, PermissionError, OSError):
        return None
