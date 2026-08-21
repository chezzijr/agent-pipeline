"""The event log: one append-only SQLite table.

Two stores, and only one of them is state. Ticket files are the source of
truth for *what a ticket is*; this database is a record of *what happened*.
Deleting it loses history and never state -- which is why the append-only
triggers are triggers and not a comment, and why there is no pruning: `rm
events.db` is the supported reset.
"""
import json
import os
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id      INTEGER PRIMARY KEY,          -- rowid; monotonic, doubles as the subscribe cursor
  ts      REAL NOT NULL,
  project TEXT NOT NULL,                -- absolute path as registered
  ticket  TEXT,                         -- NULL for daemon-level events
  stage   TEXT,
  session TEXT,
  kind    TEXT NOT NULL,
  data    TEXT NOT NULL DEFAULT '{}'    -- JSON, kind-specific
);
CREATE INDEX IF NOT EXISTS events_proj_ts ON events(project, ts);
CREATE INDEX IF NOT EXISTS events_ticket  ON events(ticket, id);
CREATE INDEX IF NOT EXISTS events_kind_ts ON events(kind, ts);

CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;
"""

COLUMNS = ("id", "ts", "project", "ticket", "stage", "session", "kind", "data")


def state_dir() -> Path:
    root = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(root) / "pipeline"


def db_path() -> Path:
    return state_dir() / "events.db"


def _row(r: sqlite3.Row) -> dict:
    ev = dict(zip(COLUMNS, r))
    try:
        ev["data"] = json.loads(ev["data"])
    except ValueError:
        ev["data"] = {}
    return ev


class Store:
    """Opened once per process. `emit()` is the only writer."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else db_path()
        # 0700/0600: this database holds every project's ticket summaries and
        # gate findings. The socket in this same feature is careful about its
        # mode; the file behind it has no business being world-readable.
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        new = not self.path.exists()
        # isolation_level=None: every emit() is its own committed statement, so
        # a SIGKILLed daemon loses no event a reader had already been told about
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        if new:
            os.chmod(self.path, 0o600)
        self.conn.execute("PRAGMA journal_mode=WAL")     # readers never block emit()
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.execute("PRAGMA user_version=1")
        # live fan-out: the Server appends one callback here. A plain list keeps
        # the Store ignorant of sockets, which is what lets `pipeline run` use
        # the same store with no server at all.
        self.listeners: list = []

    # -- write -------------------------------------------------------------
    def emit(self, project, kind: str, ticket: str | None = None,
             stage: str | None = None, session: str | None = None,
             **data) -> dict:
        ts = time.time()
        blob = json.dumps(data, default=str)
        cur = self.conn.execute(
            "INSERT INTO events(ts,project,ticket,stage,session,kind,data)"
            " VALUES(?,?,?,?,?,?,?)",
            (ts, str(project), ticket, stage, session, kind, blob))
        ev = {"id": cur.lastrowid, "ts": ts, "project": str(project),
              "ticket": ticket, "stage": stage, "session": session,
              "kind": kind, "data": data}
        for fn in self.listeners:
            fn(ev)
        return ev

    def emitter(self, project):
        """`emit` with the project bound. Every supervisor call site already
        knows its project and nothing else does, so bind it once here rather
        than threading a Path through five signatures."""
        return lambda kind, **kw: self.emit(project, kind, **kw)

    # -- read --------------------------------------------------------------
    def cursor(self) -> int:
        return self.conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]

    def since(self, cursor: int = 0, project: str | None = None,
              ticket: str | None = None, limit: int = 1000) -> list[dict]:
        sql = "SELECT * FROM events WHERE id > ?"
        args: list = [int(cursor)]
        if project:
            sql += " AND project = ?"
            args.append(str(project))
        if ticket:
            sql += " AND ticket = ?"
            args.append(ticket)
        sql += " ORDER BY id LIMIT ?"
        args.append(int(limit))
        return [_row(r) for r in self.conn.execute(sql, args)]

    def close(self) -> None:
        self.conn.close()


def noop(kind: str, **kw) -> None:
    """The default `emit`. `pipeline run` with no store still runs."""
