"""Run one stage under a real PTY the daemon owns.

Why a PTY at all: `--permission-mode` is *ignored* under `-p` (init reports
`default` and Bash runs unprompted) and `AskUserQuestion` is not in the
headless toolset. An option picker and a permission prompt only exist in a
real interactive session, so this is not a nicer view of a headless stage --
it is the only mode in which a human can steer one.

Why `pty.fork` and not `openpty` + `Popen`: fork gives the child a
CONTROLLING terminal (setsid + TIOCSCTTY in one call). A `Popen` handed a
slave fd on stdin/stdout has a tty but no session, and a TUI that checks for
a controlling terminal draws nothing.

The daemon owns the master fd, which is what makes detach free: closing a
client socket touches neither the fd nor the child.
"""
import fcntl
import os
import pty
import signal
import struct
import subprocess
import termios
import time

import pyte

ROWS, COLS = 40, 120


def set_winsize(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class PtyProc:
    """The five bits of `Popen` that `reap`, `finish` and `shut_down` use,
    over a bare pid from `pty.fork`. A shim on purpose: none of those call
    sites should grow a PTY branch to learn that a child is a child."""

    def __init__(self, pid: int) -> None:
        self.pid, self.returncode = pid, None

    def poll(self):
        if self.returncode is None:
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:      # already reaped: gone either way
                self.returncode = -1
            else:
                if pid:
                    self.returncode = os.waitstatus_to_exitcode(status)
        return self.returncode

    def wait(self, timeout: float | None = None):
        """Blocking, with `Popen`'s exception -- `shut_down` catches exactly
        `subprocess.TimeoutExpired` before it escalates to `kill()`."""
        deadline = time.monotonic() + (timeout or 0)
        while self.poll() is None:
            if timeout is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(f"pty {self.pid}", timeout)
            time.sleep(0.02)
        return self.returncode

    def _signal(self, sig: int) -> None:
        # the child is a session leader, so its pid is also its process group:
        # signal the group, or claude's own children outlive the stage
        try:
            os.killpg(self.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def terminate(self) -> None:
        self._signal(signal.SIGTERM)

    def kill(self) -> None:
        self._signal(signal.SIGKILL)


class Screen:
    """A pyte screen plus the clients watching it.

    pyte's entire justification: a client attaching at minute three must see
    the CURRENT screen, not three minutes of replayed ANSI. `display` is 40
    plain-text lines, instantly. Nothing else in the app needs it.

    Deliberately shaped like `StreamReader` -- `feed(chunk) -> events` -- so
    `supervisor.pump()` needs no PTY branch at all. It returns nothing,
    because a PTY carries no stream-json events: the raw bytes go to the
    subscribers here, and the log tee is pump's own doing.
    """

    def __init__(self, rows: int = ROWS, cols: int = COLS) -> None:
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        self.subs: list = []      # callables taking one raw chunk

    @property
    def rows(self) -> int:
        return self.screen.lines

    @property
    def cols(self) -> int:
        return self.screen.columns

    @property
    def display(self) -> list:
        return self.screen.display

    def feed(self, chunk: bytes) -> tuple:
        self.stream.feed(chunk)
        for sub in list(self.subs):
            sub(chunk)
        return ()

    def resize(self, rows: int, cols: int) -> None:
        self.screen.resize(rows, cols)


def start(cmd: str, cwd, env: dict, rows: int = ROWS, cols: int = COLS):
    """Fork `sh -c cmd` on a new PTY. Returns (PtyProc, master file object).

    The master is non-blocking because the poller's callback does one read and
    returns; on Linux it reports `EIO` rather than EOF once the child is gone,
    which `supervisor.pump` already treats as end-of-stream.

    Every fd this process holds -- the socket, the flocks, the event DB, the
    other children's masters -- is CLOEXEC (Python's default since PEP 446),
    so `execvpe` is the fd hygiene; there is nothing to close by hand.
    """
    pid, fd = pty.fork()
    if pid == 0:                      # child: nothing here may return
        try:
            os.chdir(str(cwd))
            # The winsize goes on the slave, HERE, before exec: a child that
            # reads 0x0 at startup draws nothing, and setting it from the
            # parent races the child's first draw. In the child `pty.fork`
            # has already dup'd the slave onto 0/1/2.
            set_winsize(0, rows, cols)
            os.execvpe("sh", ["sh", "-c", cmd], env)
        except BaseException:
            pass
        os._exit(127)
    os.set_blocking(fd, False)
    return PtyProc(pid), os.fdopen(fd, "rb", buffering=0)
