"""`pipeline tui` -- the pane that makes the pipeline watchable.

Left: a tree of the registered projects and their tickets. Right: the rendered
event stream for whatever the cursor is on. Eight keys along the bottom.

Only one of those eight needs a daemon op. `a`/`r`/`A` mutate the ticket file,
which is the source of truth, and the daemon's next tick notices -- so they
call the very `cmd_approve`/`cmd_reject`/`cmd_answer` the CLI calls, including
their refusals. `e`/`l`/`m` suspend the app and hand the terminal to `$EDITOR`,
`less` and `pipeline metrics`. `k` is the only one that has to ask the daemon
anything, because only the daemon knows the child's pid.

The client is a constructor argument for exactly one reason: `tests/test_tui.py`
passes a fake one. It is not a plugin point, and there is no second one.
"""
import io
import os
import shlex
import socket
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from textual import work
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, RichLog, Static, Tree

from pipeline.cli.main import cmd_answer, cmd_approve, cmd_reject, render
from pipeline.core import PipelineError
from pipeline.core.machine import HUMAN_GATES
from pipeline.core.ticket import ticket_path
from pipeline.daemon import registry
from pipeline.daemon.server import ticket_rows
from pipeline.stream import StreamReader

REFRESH_SECS = 5.0     # the safety net; events are what make it feel live
MAX_TAIL = 256 << 10   # of a stage log, before the live stream takes over

# The event kinds that can change a row. Everything else is stream chatter and
# belongs in the detail pane, not in a tree rebuild.
TREE_KINDS = {"stage_start", "stage_end", "transition", "escalated", "gate"}
# TICKET-012's passthrough kinds: `data` is the shape `cli.main.render` reads.
STREAM_KINDS = {"init", "assistant", "tool_result", "hook_started",
                "hook_response", "rate_limit", "result"}


def marker(row: dict) -> str:
    """The sketch's one-glyph status: running, waiting on a human, or sitting
    still long enough that somebody should look."""
    if row.get("running"):
        return "*"
    if row.get("stage") in HUMAN_GATES:
        return "!"
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


def tail_log(project: str, tid: str) -> list[str]:
    """The tail of the ticket's most recent stage log, rendered.

    A subscription only carries what happens after you subscribe; this is what
    happened before. Same `StreamReader` and same `render` as `pipeline logs`.
    """
    try:
        logs = sorted((Path(project) / ".project" / "logs").glob(f"{tid}-*.log"),
                      key=lambda p: p.stat().st_mtime)
        if not logs:
            return ["(no log yet)"]
        raw = logs[-1].read_bytes()
        # drop the first line when we cut into the middle of one
        data = raw[-MAX_TAIL:].split(b"\n", 1)[-1] if len(raw) > MAX_TAIL else raw
        return [ln for ev in StreamReader().feed(data) if (ln := render(ev))]
    except OSError as e:
        return [f"(log unreadable: {e})"]


class PipelineApp(App):
    CSS = """
    #tree { width: 34; }
    #log { height: 1fr; }
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

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Tree("pipelines", id="tree")
            with Vertical():
                yield RichLog(id="log", wrap=True, max_lines=2000)
                yield Static(id="pty")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#pty", Static).display = False
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
        return [r for p in targets for r in ticket_rows(Path(p))]

    def refresh_tree(self) -> None:
        self._paint(self._rows())

    def _paint(self, rows: list[dict]) -> None:
        """Rebuild the tree -- but only when a label actually changed. The 5s
        refresh would otherwise yank the cursor back to the root twice a
        keystroke, which is the difference between a dashboard and a toy."""
        self.rows = {(r["project"], r["id"]): r for r in rows}
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            grouped.setdefault(r["project"], []).append(r)
        sig = [(p, [label(r) for r in sorted(rs, key=lambda r: r["id"])])
               for p, rs in sorted(grouped.items())]
        self._status(rows)
        if sig == self.sig:
            return
        self.sig = sig
        tree = self.query_one(Tree)
        keep = self.selected
        tree.root.remove_children()
        for p, labels in sig:
            node = tree.root.add(Path(p).name or p, data=p, expand=True)
            for text in labels:
                leaf = node.add_leaf(text, data=(p, text.split()[0]))
                if leaf.data == keep:
                    tree.move_cursor(leaf)

    def _status(self, rows: list[dict]) -> None:
        running = sum(1 for r in rows if r.get("running"))
        drops = f" - {self.dropped} events dropped" if self.dropped else ""
        # the sketch's `$2.14 today` lives behind `m`: cost is TICKET-014's
        self.query_one("#status", Static).update(
            f"{len(rows)} tickets - {running} running{drops}")

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
        if "dropped" in msg:
            self.dropped += int(msg.get("dropped") or 0)
            self._write(f"-- {msg.get('dropped')} events dropped; reseeding")
            self.sig = None                  # force the repaint, not just the read
            return self.refresh_tree()
        ev = msg.get("event")
        if not isinstance(ev, dict):
            return
        if ev.get("kind") in TREE_KINDS:
            self.refresh_tree()
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
        for line in tail_log(key[0], key[1]):
            log.write(line)

    def _pty(self, row: dict) -> bool:
        """The seam TICKET-013 fills. Returns "the PTY pane is showing this".

        A PTY-hosted stage is `row["mode"] == "interactive"` -- that value is
        already on every `ls` row, and nothing but this reads it yet. 013 adds
        the `attach` op, whose reply carries the rendered `screen.display`.
        Wiring it up is three lines here and one branch in `on_frame`:

            if row.get("mode") != "interactive": return False
            d = self.client.request("attach", project=..., ticket=...)
            pty = self.query_one("#pty", Static)
            pty.update(d["display"]); pty.display = True
            self.query_one("#log", RichLog).display = False
            return True

        plus `on_frame` updating `#pty` from 013's screen frames instead of
        appending to the log. Until then every stage renders headless, which
        today is every stage.
        """
        # TODO(TICKET-013): `attach` op -> screen.display into #pty
        return False

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

    def action_edit(self) -> None:
        """Interrupt the stage, then open the editor.

        The dispatcher escalates a ticket whose control fields changed during a
        stage. A human editing one mid-run would trip that, so the stage is
        stopped first -- which narrows tamper detection back to the case it
        exists for: an *agent* rewriting its own control fields.
        """
        key = self._target()
        if key is None:
            return
        if self.rows.get(key, {}).get("running"):
            self._kill(key)
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
