"""`pipeline tui` -- the pane that makes the pipeline watchable.

Left: a tree of the registered projects and their tickets. Right: the rendered
event stream for whatever the cursor is on. Ten keys along the bottom. `f`
shows the `done` and `rejected` tickets the tree hides by default; `escalated`
is never hidden.

Only one of those eight needs a daemon op. `a`/`r`/`A` mutate the ticket file,
which is the source of truth, and the daemon's next tick notices -- so they
call the very `cmd_approve`/`cmd_reject`/`cmd_answer` the CLI calls, including
their refusals. `e`/`l`/`m` suspend the app and hand the terminal to `$EDITOR`,
`less` and `pipeline metrics`. `k` is the only one that has to ask the daemon
anything, because only the daemon knows the child's pid.

The client is a constructor argument for exactly one reason: `tests/test_tui.py`
passes a fake one. It is not a plugin point, and there is no second one.
"""
import base64
import io
import os
import shlex
import socket
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from textual import events, work
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, RichLog, Static, Tree

from pipeline.cli.main import cmd_answer, cmd_approve, cmd_reject, render
from pipeline.core import PipelineError
from pipeline.core.machine import HUMAN_GATES, TERMINAL
from pipeline.core.ticket import ticket_path
from pipeline.daemon import registry
from pipeline.daemon.server import PTY_INPUT, ticket_rows
from pipeline.pty.host import COLS, GEOM_OSC, ROWS, Screen, last_geometry
from pipeline.stream import StreamReader

REFRESH_SECS = 5.0     # the safety net; events are what make it feel live
MAX_TAIL = 256 << 10   # of a stage log, before the live stream takes over

# The event kinds that can change a row. Everything else is stream chatter and
# belongs in the detail pane, not in a tree rebuild.
TREE_KINDS = {"stage_start", "stage_end", "transition", "escalated", "gate"}
# `escalated` is terminal, but it is the one terminal stage a human must open.
FINISHED = TERMINAL - {"escalated"}
# TICKET-012's passthrough kinds: `data` is the shape `cli.main.render` reads.
STREAM_KINDS = {"init", "assistant", "tool_result", "hook_started",
                "hook_response", "rate_limit", "result"}


# What a terminal sends for a key Textual hands us only the *name* of. Raw
# mode needs the bytes: `Key.character` is None for a cursor key, and wrong for
# backspace -- Textual says \x08, a terminal sends \x7f.
RAW_KEYS = {
    "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D",
    "home": b"\x1b[H", "end": b"\x1b[F", "insert": b"\x1b[2~",
    "delete": b"\x1b[3~", "pageup": b"\x1b[5~", "pagedown": b"\x1b[6~",
    "shift+tab": b"\x1b[Z", "tab": b"\t", "enter": b"\r", "escape": b"\x1b",
    "backspace": b"\x7f", "space": b" ",
}


def key_bytes(event) -> bytes:
    """One Textual key event -> the bytes the terminal would have sent. Total:
    a key with no sequence (f5, alt+x) is dropped, never guessed."""
    if event.key in RAW_KEYS:
        return RAW_KEYS[event.key]
    name = event.key.removeprefix("ctrl+")
    if name != event.key and len(name) == 1 and name.isalpha():
        return bytes([ord(name.upper()) ^ 0x40])
    return event.character.encode("utf-8") if event.is_printable else b""


def marker(row: dict) -> str:
    """The sketch's one-glyph status: running, waiting on a human, or sitting
    still long enough that somebody should look."""
    if row.get("running"):
        return "*"
    if row.get("stage") in HUMAN_GATES:
        return "!"
    if row.get("running", False) is None:
        return "~"
    return "?" if row.get("stale") else ""


def label(row: dict) -> str:
    return f"{row['id']} {row.get('stage', '?')} {marker(row)}".rstrip()


def event_line(ev: dict) -> str:
    """One stored event -> one line. Total: a kind nobody taught it about still
    prints, because a TUI that raises on an unknown event is worse than one
    that prints it raw."""
    kind, data = ev.get("kind", "?"), ev.get("data") or {}
    if kind in STREAM_KINDS:
        try:
            return render({"kind": kind, **data})
        except Exception:      # a partial payload; fall through to the raw form
            pass
    return f"[{kind}] " + " ".join(f"{k}={v}" for k, v in data.items())


def render_pty(data: bytes, rows: int = ROWS, cols: int = COLS) -> list[str]:
    """A raw PTY dump -> the final screen, as plain text lines.

    An interactive stage that ran attached leaves terminal bytes, not
    stream-json. Replay them through the same pyte `Screen` the live
    pane uses: 40 lines of what the stage last showed, instead of
    2852 spinner frames with their cursor codes intact.

    `rows`/`cols` are the geometry the dump opens at. A marker inside it
    (`\\x1b]9999;<rows>;<cols>\\x07`) resizes the screen at the same point
    the daemon resized the live one, so the replay reproduces that screen
    instead of one final width. Replaying at the wrong width re-wraps every
    frame, so a later redraw lands on a leftover row instead of clearing it.
    """
    screen = Screen(rows, cols)
    pos = 0
    for m in GEOM_OSC.finditer(data):
        screen.feed(data[pos:m.start()])
        screen.resize(*last_geometry(m.group(0)))
        pos = m.end()
    screen.feed(data[pos:])
    lines = [ln.rstrip() for ln in screen.display]
    while lines and not lines[-1]:
        lines.pop()
    return lines or ["(blank screen)"]


def tail_log(project: str, tid: str) -> list[str]:
    """The tail of the ticket's most recent stage log, rendered.

    A subscription only carries what happens after you subscribe; this is what
    happened before. Same `StreamReader` and same `render` as `pipeline logs`.
    A log carrying a raw ESC is a PTY dump instead, and goes through render_pty().
    """
    try:
        logs = sorted((Path(project) / ".project" / "logs").glob(f"{tid}-*.log"),
                      key=lambda p: p.stat().st_mtime)
        if not logs:
            return ["(no log yet)"]
        raw = logs[-1].read_bytes()
        # drop the first line when we cut into the middle of one; keep the
        # head (spawn()'s marker can sit before the cut) to recover the
        # geometry the cut tail lost
        cut = max(0, len(raw) - MAX_TAIL)
        head, data = raw[:cut], raw[cut:]
        if cut:
            first, sep, rest = data.partition(b"\n")
            if sep:
                head, data = head + first + sep, rest
        # A stage that ran attached leaves a PTY dump, and valid stream-json
        # never carries a raw ESC (JSON escapes it), so the byte is the test.
        # The stage's name is not: `planning` runs headless whenever nothing
        # can attach to it, and then its log IS stream-json.
        if b"\x1b" in data:
            return render_pty(data, *last_geometry(head))
        return [ln for ev in StreamReader().feed(data) if (ln := render(ev))]
    except OSError as e:
        return [f"(log unreadable: {e})"]


class PtyPane(Static):
    """The attached terminal. A widget and not a bare `Static` for one reason:
    `events.Resize` does NOT bubble, so the only place that learns this pane
    real size is the pane itself."""

    def on_resize(self, event) -> None:
        self.app._resize()


class PipelineApp(App):
    CSS = """
    #tree { width: 34; }
    #log { height: 1fr; }
    #pty { height: 1fr; }
    #status { height: 1; background: $panel; color: $text; }
    """

    BINDINGS = [
        ("q", "quit", "quit"),
        ("a", "approve", "approve"),
        ("r", "reject", "reject"),
        ("A", "answer", "answer"),
        ("e", "edit", "edit"),
        ("l", "logs", "logs"),
        ("m", "metrics", "metrics"),
        ("k", "kill", "kill"),
        ("i", "raw", "type"),
        ("f", "finished", "finished"),
    ]

    def __init__(self, client=None, project: str | None = None) -> None:
        super().__init__()
        self.client = client          # None == no daemon: the files still answer
        self.stream = None            # the subscription's own connection
        self.project = project        # a filter, never a target
        self.projects: list[str] = []
        self.rows: dict[tuple[str, str], dict] = {}
        self.selected: tuple[str, str] | None = None
        self.dropped = 0
        self.sig = None               # last painted tree, to skip no-op repaints
        self.show_finished = False    # `f` toggles `done`/`rejected` back in
        self.attached = None          # (project, ticket) the PTY pane is showing
        self.pty_id = None            # the request id its `attach` frames carry
        self.pty_screen = None        # our own emulator, fed by those frames
        self.pty_writer = False       # resize is writer-only
        self.resize_id = None         # the resize awaiting its reply
        self.keys_out = b""           # keystrokes the daemon has not taken yet
        self.keys_flight = None       # (request id, chunk) currently with it
        self.raw = False              # raw mode: every keystroke goes to the pty
        self.esc = 0                  # escapes held back, waiting for the second

    def notify(self, message: str, **kw) -> None:
        """Everything this app notifies with is text it did not write -- an
        exception string, a daemon error, a path with brackets in it. Rich
        markup is the wrong reading of all of them, and a bad one raises."""
        kw.setdefault("markup", False)
        super().notify(str(message), **kw)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Tree("pipelines", id="tree")
            with Vertical():
                yield RichLog(id="log", wrap=True, max_lines=2000)
                # markup=False: `Static` renders Rich markup by default and
                # this pane is fed raw terminal output. One bracketed path on
                # the attached screen (`ls [/home/x]`) raises MarkupError
                # inside the frame handler and takes the pane down.
                yield PtyPane(id="pty", markup=False)
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#pty", PtyPane).display = False
        self.query_one(Tree).root.expand()
        rows = self._rows()
        self.projects = sorted({r["project"] for r in rows}) or (
            [self.project] if self.project else [str(p) for p in registry.projects()])
        self._paint(rows)
        self.set_interval(REFRESH_SECS, self.refresh_tree)
        self._subscribe()

    def on_unmount(self) -> None:
        """Shut the sockets down, not just close them: the reader thread parks
        in `recv` with no timeout, and a bare `close()` does not reliably wake
        it -- a live worker thread would then hold the process open long after
        `run()` returned."""
        for c in (self.stream, self.client):
            for call in (lambda: c.sock.shutdown(socket.SHUT_RDWR), lambda: c.close()):
                try:
                    call()
                except (OSError, AttributeError):
                    pass

    # -- rows ---------------------------------------------------------------
    def _rows(self) -> list[dict]:
        """The daemon if there is one -- only it knows which stages are
        actually running -- and the files if there is not. Both answers are
        built by the same `ticket_rows()`, which is the whole point of it being
        one function."""
        if self.client is not None:
            try:
                return self.client.request("ls", project=self.project)
            except PipelineError as e:
                self.notify(f"daemon: {e}")
        targets = self.projects or ([self.project] if self.project
                                    else [str(p) for p in registry.projects()])
        return [self._carry(r) for p in targets for r in ticket_rows(Path(p))]

    def _carry(self, row: dict) -> dict:
        """A file row cannot know `running`/`mode` and says `None`. The last
        daemon answer is a better guess than `not running`: a live
        interactive stage stays attachable across one timed-out `ls`. It can
        be stale for as long as the daemon is silent, and the next answered
        `ls` corrects it -- erring toward reachable, because the failure this
        fixes is a human locked out of a prompt already on screen."""
        for k in ("running", "mode"):
            if row.get(k, False) is None:
                last = self.rows.get((row.get("project"), row.get("id")))
                if last and last.get(k) is not None:
                    row[k] = last[k]
        return row

    def refresh_tree(self) -> None:
        self._paint(self._rows())

    def _visible(self, rows: list[dict]) -> list[dict]:
        """Which rows the tree paints. `done` and `rejected` hide by default;
        the selected row stays painted whatever its stage, so a ticket that
        finishes while its pane is open does not take its own row away."""
        if self.show_finished:
            return rows
        return [r for r in rows if r.get("stage") not in FINISHED
                or (r["project"], r["id"]) == self.selected]

    def _paint(self, rows: list[dict]) -> None:
        """Rebuild the tree -- but only when a label actually changed. The 5s
        refresh would otherwise yank the cursor back to the root twice a
        keystroke, which is the difference between a dashboard and a toy."""
        self.rows = {(r["project"], r["id"]): r for r in rows}
        grouped: dict[str, list[dict]] = {r["project"]: [] for r in rows}
        for r in self._visible(rows):
            grouped[r["project"]].append(r)
        sig = [(p, [label(r) for r in sorted(rs, key=lambda r: r["id"])])
               for p, rs in sorted(grouped.items())]
        self._status()
        if sig == self.sig:
            return
        self.sig = sig
        tree = self.query_one(Tree)
        keep, restored, first = self.selected, False, None
        tree.root.remove_children()
        for p, labels in sig:
            node = tree.root.add(Path(p).name or p, data=p, expand=True)
            for text in labels:
                leaf = node.add_leaf(text, data=(p, text.split()[0]))
                if leaf.data == keep:
                    restored, first = True, leaf
                elif (not restored and first is None
                      and self.rows.get(leaf.data, {}).get("stage") not in TERMINAL):
                    first = leaf
        if first is not None:
            # a leaf added this tick has `_line == -1`, and `move_cursor` would
            # clamp that to the root; reading `last_line` forces the line build
            tree.last_line
            tree.move_cursor(first)

    def _status(self) -> None:
        rows = list(self.rows.values())
        running = sum(1 for r in rows if r.get("running"))
        unknown = sum(1 for r in rows if r.get("running", False) is None)
        hidden = len(rows) - len(self._visible(rows))
        finished = f" - {hidden} finished hidden (f)" if hidden else ""
        drops = f" - {self.dropped} events dropped" if self.dropped else ""
        mode = "RAW (esc esc to exit) - " if self.raw else ""
        unk = f" - {unknown} unknown (no daemon)" if unknown else ""
        # the sketch's `$2.14 today` lives behind `m`: cost is TICKET-014's
        self.query_one("#status", Static).update(
            f"{mode}{len(rows)} tickets - {running} running{unk}{finished}{drops}")

    # -- the event stream ---------------------------------------------------
    @work(thread=True, exclusive=True)
    def _subscribe(self) -> None:
        """One thread, one connection, no requests on it.

        `Client.lines()` blocks, so a subscription owns its socket: a `request`
        on the same one from the UI thread would eat the subscription's frames.
        That is what `clone()` is for.
        """
        if self.client is None:
            return
        try:
            self.stream = self.client.clone()       # timeout None: park, do not expire
            self.stream.send("subscribe", project=self.project)
            for msg in self.stream.lines():
                self.call_from_thread(self.on_frame, msg)
        except (OSError, ValueError, PipelineError, RuntimeError):
            pass    # the daemon went away, or the app did (`call_from_thread`
                    # raises once it stops). Either way the 5s refresh carries on.

    def on_frame(self, msg: dict) -> None:
        """One socket frame. Three shapes reach here: the `subscribe` reply
        (ignored -- we asked for live events, not a replay), an event, and the
        `dropped` marker.

        `dropped` means the daemon binned part of our backlog to avoid stalling
        the supervisor, so the tree may be describing a world that has moved:
        say so, and reseed from scratch rather than patching forward from
        events we know are missing.
        """
        if "pty" in msg:
            return self._pty_frame(msg["pty"])
        if self.pty_id is not None and msg.get("id") == self.pty_id:
            return self._attached(msg)
        if self.resize_id is not None and msg.get("id") == self.resize_id:
            self.resize_id = None
            if not msg.get("ok"):
                self.notify("resize: %s" % msg.get("error"))
            return
        if self.keys_flight and msg.get("id") == self.keys_flight[0]:
            return self._keys_acked(msg)
        if "dropped" in msg:
            self.dropped += int(msg.get("dropped") or 0)
            self._write(f"-- {msg.get('dropped')} events dropped; reseeding")
            self.sig = None                  # force the repaint, not just the read
            if self.attached is not None:
                # the daemon binned part of our backlog, so our emulation is
                # desynced from its pyte screen -- which is authoritative.
                # Painting forward across the gap renders a corrupted terminal
                # indefinitely; re-attaching costs one round trip.
                proj, tid = self.attached
                self.attached = None         # force it, do not no-op
                self._pty({"mode": "interactive", "project": proj, "id": tid})
            return self.refresh_tree()
        ev = msg.get("event")
        if not isinstance(ev, dict):
            return
        if ev.get("kind") in TREE_KINDS:
            self.refresh_tree()
        if (ev.get("kind") == "stage_end"
                and self.attached == (ev.get("project"), ev.get("ticket"))):
            # the session this pane is showing is over. Without this the pane
            # sits on its last screen forever, looking live.
            self._detach()
            if self.selected:
                return self._show(self.selected)
        if self.selected == (ev.get("project"), ev.get("ticket")):
            self._write(event_line(ev))

    def _write(self, text: str) -> None:
        self.query_one("#log", RichLog).write(text)

    # -- selection ----------------------------------------------------------
    def on_tree_node_highlighted(self, event) -> None:
        if not isinstance(event.node.data, tuple):
            return                            # a project node
        self.selected = event.node.data
        self._show(self.selected)

    def _show(self, key: tuple[str, str]) -> None:
        log = self.query_one("#log", RichLog)
        log.clear()
        row = self.rows.get(key, {})
        log.write(f"== {row.get('id', key[1])} {row.get('stage', '?')} "
                  f"{row.get('class', '')} {row.get('title', '')}".rstrip())
        if self._pty(row):
            return
        self._detach()
        self.query_one("#pty", PtyPane).display = False
        log.display = True
        for line in tail_log(key[0], key[1]):
            log.write(line)

    # -- the PTY pane -------------------------------------------------------
    def _pty(self, row: dict) -> bool:
        """TICKET-013's `attach`, in the pane TICKET-015 left for it. Returns
        "the PTY pane is showing this".

        The attach goes out on the SUBSCRIPTION's connection, not the request
        one. `pty` frames are pushed to whichever connection attached, and
        nothing reads the request socket between `request()` calls -- an
        attach there would paint one screen and then go deaf. `on_frame`
        already sees every frame from this connection, reply included, so the
        screen arrives there.
        """
        if row.get("mode") != "interactive" or self.stream is None:
            return False
        if self.attached != (row["project"], row["id"]):
            self._detach()
            try:
                self.pty_id = self.stream.send("attach", project=row["project"],
                                               ticket=row["id"])
            except (OSError, ValueError) as e:
                self.notify(f"attach: {e}")
                return False
            self.attached = (row["project"], row["id"])
        self.query_one("#log", RichLog).display = False
        self.query_one("#pty", PtyPane).display = True
        return True

    def _detach(self) -> None:
        """Leaving the pane ends nothing: the daemon owns the master fd."""
        if self.attached is not None and self.stream is not None:
            try:
                self.stream.send("detach")
            except (OSError, ValueError):
                pass
        self.attached = self.pty_id = self.pty_screen = None
        self.pty_writer, self.resize_id = False, None
        self.keys_out, self.keys_flight = b"", None
        self.raw, self.esc = False, 0
        self._status()

    def _attached(self, msg: dict) -> None:
        """The `attach` reply: a snapshot of the daemon's pyte screen."""
        if not msg.get("ok"):
            self.attached = self.pty_id = None
            return self.notify(f"attach: {msg.get('error')}")
        d = msg.get("data") or {}
        self.pty_screen = Screen(d.get("rows") or ROWS, d.get("cols") or COLS)
        # seed our emulator with the snapshot: it starts blank, so the first
        # live frame would otherwise paint onto nothing and lose every line
        # written before we attached. `rstrip` because pyte pads its display
        # to the full width and a full-width line would wrap on the newline.
        lines = [str(x) for x in (d.get("screen") or [])]
        self.pty_screen.feed(b"\x1b[H" + "\r\n".join(
            l.rstrip() for l in lines).encode("utf-8", "replace"))
        self.pty_writer = bool(d.get("writer"))
        self._paint_pty()
        self._resize()
        if not self.pty_writer:
            self.notify("another client holds the writer: read-only")

    def _paint_pty(self) -> None:
        pane = self.query_one("#pty", PtyPane)
        pane.update("\n".join(self.pty_screen.display))
        pane.display = True

    def _resize(self) -> None:
        """Tell the daemon how big this pane is, and keep our own emulator the
        same size."""
        if self.pty_screen is None or self.stream is None or not self.pty_writer:
            return
        size = self.query_one("#pty", PtyPane).size
        rows, cols = size.height, size.width
        if rows < 1 or cols < 1 or (rows, cols) == (self.pty_screen.rows,
                                                    self.pty_screen.cols):
            return
        try:
            self.resize_id = self.stream.send("resize", rows=rows, cols=cols)
        except (OSError, ValueError) as e:
            return self.notify("resize: %s" % e)
        self.pty_screen.resize(rows, cols)
        self._paint_pty()

    def _pty_frame(self, blob: str) -> None:
        if self.pty_screen is None:
            return
        try:
            self.pty_screen.feed(base64.b64decode(blob))
        except ValueError:              # binascii.Error is one: remote data
            return
        self._paint_pty()
        self._flush_keys()   # the child read something, so its buffer moved

    # -- typing into it -----------------------------------------------------
    def _send_keys(self, data: bytes) -> None:
        self.keys_out += data
        self._flush_keys()

    def _flush_keys(self) -> None:
        """`input` takes at most PTY_INPUT bytes per op and reports what
        actually reached the pty's buffer. Ignoring either loses keystrokes in
        the middle of the prompt you attached to answer.
        """
        # ponytail: one op in flight, and a short write waits for the next pty
        # frame rather than hammering a full buffer. Upgrade = a timer, if a
        # child that never echoes what it reads ever turns up.
        if self.keys_flight or not self.keys_out or self.stream is None:
            return
        chunk, self.keys_out = self.keys_out[:PTY_INPUT], self.keys_out[PTY_INPUT:]
        try:
            rid = self.stream.send("input",
                                   data=base64.b64encode(chunk).decode())
        except (OSError, ValueError) as e:
            self.keys_out = b""
            return self.notify(f"input: {e}")
        self.keys_flight = (rid, chunk)

    def _keys_acked(self, msg: dict) -> None:
        _rid, chunk = self.keys_flight
        self.keys_flight = None
        if not msg.get("ok"):
            self.keys_out = b""
            return self.notify(f"input: {msg.get('error')}")
        try:
            n = int((msg.get("data") or {}).get("written") or 0)
        except (TypeError, ValueError):
            n = len(chunk)        # total, like every other frame handler here
        if n < len(chunk):        # short write: the pty's buffer was full
            self.keys_out = chunk[n:] + self.keys_out
            return
        self._flush_keys()

    async def on_event(self, event) -> None:
        """Raw mode has to catch a key HERE, before Textual checks the bindings
        and before it forwards to the focused Tree -- anywhere later and `down`
        moves the ticket cursor instead of reaching the child. It is also the
        only point at which ctrl+c is still ours to pass on. The guard stays
        narrowed to `events.Key`: DEC-019's pane sizing needs `Resize` through."""
        if self.raw and isinstance(event, events.Key) and not event.is_forwarded:
            return self._raw_key(event)
        await super().on_event(event)

    def _raw_key(self, event) -> None:
        """Every keystroke goes to the child except `Esc Esc`, the way back out.
        A lone Esc is held rather than sent: an agent prompt reads Esc as
        cancel, so a stray one on the way out of raw mode would answer the
        question you attached to read."""
        if event.key == "escape":
            self.esc += 1
            if self.esc > 1:
                self.raw, self.esc = False, 0
                self._status()
            return
        # ponytail: a held Esc is flushed by the next key, never by a timer.
        # Upgrade = a timeout, if "Esc alone does nothing" ever bites.
        pending, self.esc = b"\x1b" * self.esc, 0
        data = pending + key_bytes(event)
        if data:
            self._send_keys(data)

    def action_raw(self) -> None:
        """Hand the keyboard to the attached terminal until `Esc Esc`. The old
        `i` suspended the whole app to read one line through `input()`, which
        took the tree, the pane and the prompt off screen to answer it."""
        if self.attached is None:
            return self.notify("select an interactive stage first")
        self.raw, self.esc = True, 0
        self._status()

    # -- the keys that only touch the ticket file ---------------------------
    def _target(self) -> tuple[str, str] | None:
        if self.selected is None:
            self.notify("select a ticket first")
        return self.selected

    def _cli(self, fn, **kw) -> None:
        """Run one CLI command in-process against the selected ticket.

        These keys need no protocol surface: they rewrite the ticket file,
        which is the source of truth, and the daemon's next tick notices.
        `cmd_approve` already refuses outside `awaiting-approval` and
        `cmd_reject` already refuses past its bound -- reimplementing those
        checks here is how the two copies would drift apart. `die()` ends the
        process, though, so catch its `SystemExit` and put the message on
        screen instead of taking the app down with it.
        """
        key = self._target()
        if key is None:
            return
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                fn(SimpleNamespace(project=key[0], id=key[1], **kw))
        except SystemExit:
            pass
        except PipelineError as e:
            buf.write(str(e))
        self.notify(buf.getvalue().strip() or "done")
        self.refresh_tree()

    def action_approve(self) -> None:
        self._cli(cmd_approve, by=None)

    def action_reject(self) -> None:
        reason = self._ask("reason for rejecting: ")
        if reason:
            self._cli(cmd_reject, reason=reason)

    def action_answer(self) -> None:
        text = self._ask("answer: ")
        if text:
            self._cli(cmd_answer, text=text)

    # -- the keys that hand the terminal to something else ------------------
    def _ask(self, prompt: str) -> str:
        """Typing happens on the terminal, not in a modal. Three keys already
        suspend the app; a dialog widget for the other two would be the only
        thing in here that needed one."""
        try:
            with self.suspend():
                return input(prompt).strip()
        except (EOFError, KeyboardInterrupt, SuspendNotSupported, OSError):
            return ""

    def _sh(self, cmd: str) -> None:
        try:
            with self.suspend():
                subprocess.run(cmd, shell=True)
        except SuspendNotSupported:
            self.notify("this terminal cannot be suspended")

    def _pipeline(self, project: str) -> str:
        """`python -m pipeline`, not `pipeline`: the console script may not be
        on `$PATH`, but the interpreter running this app imports it by
        definition."""
        return (f"{shlex.quote(sys.executable)} -m pipeline "
                f"--project {shlex.quote(project)}")

    def action_logs(self) -> None:
        key = self._target()
        if key:
            self._sh(f"{self._pipeline(key[0])} logs {shlex.quote(key[1])} "
                     f"2>&1 | less -R")

    def action_metrics(self) -> None:
        # TICKET-014 owns this subcommand; `2>&1` is what shows you its absence
        p = self.selected[0] if self.selected else (self.projects or ["."])[0]
        self._sh(f"{self._pipeline(p)} metrics 2>&1 | less -R")

    def _stopped(self, key: tuple[str, str], tries: int = 20) -> bool:
        """Has the stage actually stopped? `kill` is a SIGTERM, not a join.

        The daemon reaps on its next tick and `_finish` then writes the ticket
        from its PRE-SPAWN snapshot -- over whatever the human saved in the
        meantime, silently, last writer wins. `running` goes false when the
        daemon has dropped the record, which is after that write.
        """
        # ponytail: a 5s blocking poll on the UI thread, like the three keys
        # that suspend the app. Upgrade = an async worker, if anyone ever
        # notices the pause.
        for _ in range(tries):
            self.refresh_tree()
            if not self.rows.get(key, {}).get("running"):
                return True
            time.sleep(0.25)
        return False

    def action_edit(self) -> None:
        """Interrupt the stage, then open the editor.

        The dispatcher escalates a ticket whose control fields changed during a
        stage. A human editing one mid-run would trip that, so the stage is
        stopped first -- which narrows tamper detection back to the case it
        exists for: an *agent* rewriting its own control fields.

        "Stopped" means reaped, not signalled: opening the editor on a ticket
        the daemon is still going to rewrite loses one of the two edits with
        no sign of which.
        """
        key = self._target()
        if key is None:
            return
        if self.rows.get(key, {}).get("running"):
            self._kill(key)
            if not self._stopped(key):
                return self.notify("the stage has not stopped yet -- the daemon "
                                   "would overwrite your edit. Try again.")
        self._sh(f"{os.environ.get('EDITOR') or os.environ.get('VISUAL') or 'vi'} "
                 f"{shlex.quote(str(ticket_path(Path(key[0]), key[1])))}")
        self.refresh_tree()

    # -- the one key that needs the daemon ----------------------------------
    def _kill(self, key: tuple[str, str]) -> None:
        """Only the daemon holds the child's pid, so this is the one action
        that has to be a protocol op."""
        if self.client is None:
            return self.notify("no daemon running: nothing to kill")
        try:
            d = self.client.request("kill", project=key[0], ticket=key[1])
        except PipelineError as e:
            return self.notify(f"kill: {e}")
        self.notify(f"killed {d['ticket']} (pid {d['pid']})")

    def action_kill(self) -> None:
        key = self._target()
        if key:
            self._kill(key)
            self.refresh_tree()

    def action_finished(self) -> None:
        """`f` toggles `done`/`rejected` in and out of the tree. Hidden is the
        default; `self.sig = None` forces the rebuild even when the visible
        labels did not change."""
        self.show_finished = not self.show_finished
        self.sig = None
        self.refresh_tree()
