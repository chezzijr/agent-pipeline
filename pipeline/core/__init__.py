"""Core library. Nothing here calls `sys.exit`: a library that kills the
process takes the whole dispatcher down with one bad project."""


class PipelineError(Exception):
    """Anything the library refuses to do. The CLI turns it into `die()`."""
