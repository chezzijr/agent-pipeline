"""Core library. Nothing here calls `sys.exit`: a library that kills the
process takes the whole dispatcher down with one bad project."""
import sys


class PipelineError(Exception):
    """Anything the library refuses to do. The CLI turns it into `die()`."""


def line_buffer_stdout() -> None:
    """Every entry point whose stdout can be redirected calls this first.

    Python block-buffers stdout when it is not a tty. The dispatcher prints
    a few hundred bytes an hour, so `pipeline start`'s redirect into
    daemon.log -- and any `pipeline run > run.log` -- holds every line until
    8 KiB accumulate or the process exits, and watching that file is how a
    human or a `tail -f` finds out what the pipeline is doing. It goes
    inside the process rather than as `-u` on the spawner because
    `pipeline run` has no spawner to pass a flag to. stderr needs nothing:
    line-buffered unconditionally since 3.9.
    """
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]


_NOTICED: set[tuple[str, ...]] = set()


def notice_once(message: str, *key: str) -> bool:
    """Print `message` the first time this `key` is seen, and stay silent
    after. A caller uses this for a fact about the operator's whole setup
    (a project, a stage) rather than about one ticket, so reprinting it per
    ticket would bury the lines that ARE per-ticket. Key on the project and
    the stage (and any other fact that varies) so a second project or stage
    still prints once. Returns whether it printed."""
    if key in _NOTICED:
        return False
    _NOTICED.add(key)
    print(message)
    return True


def reset_notices() -> None:
    """Test seam: the suite runs every test in one process, so a test that
    asserts a `notice_once()` print must clear the keys first."""
    _NOTICED.clear()
