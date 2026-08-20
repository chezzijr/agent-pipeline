"""Ticket-driven agent pipeline.

Deliberately dumb: the state machine lives in `core.machine`, all judgment
lives in the agents. An agent never writes the `stage` field -- it writes a
`.result` sidecar and the dispatcher decides what happens next.
"""
__version__ = "0.1.0"

from pipeline.core import PipelineError

# Temporary: `test_pipeline.py` still does `import pipeline as P`. These
# re-exports keep it green through the extraction and are deleted once the
# suite is split into `tests/` per module.
from pipeline.core.config import (STAGES_DIR, agent_stages, compose_prompt,
                                  harness, is_readonly, stage_config,
                                  stage_settings)
from pipeline.core.gate import gate
from pipeline.core.machine import (CLEANUP_STAGES, CONTROL_FIELDS,
                                   HUMAN_GATES, TERMINAL, apply_claims,
                                   files_conflict, transition)
from pipeline.core.ticket import (drop_result, load_ticket, read_result,
                                  record_decision, result_file, save_ticket,
                                  sections, validate_meta)
from pipeline.core.worktree import (drop_worktree, ensure_worktree,
                                    project_env)
from pipeline.daemon.supervisor import escalate, lease_active, start

__all__ = [n for n in dir() if not n.startswith("_")]
