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
