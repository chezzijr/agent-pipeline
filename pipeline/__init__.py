"""Ticket-driven agent pipeline.

Deliberately dumb: the state machine lives in `pipeline.core.machine`, all
judgment lives in the agents. An agent never writes the `stage` field -- it
writes a `.result` sidecar and the dispatcher decides what happens next.
"""
from pipeline.core import PipelineError

__version__ = "0.1.0"
__all__ = ["PipelineError", "__version__"]
