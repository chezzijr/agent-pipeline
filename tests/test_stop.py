"""TICKET-148: a running stage can be stopped cleanly."""
import os
import shutil
import argparse
import tempfile
import types
from datetime import timedelta
from pathlib import Path

import pyte

from helpers import project
from pipeline.core import ticket as T
from pipeline.core.config import harness
from pipeline.core.ticket import Ticket
from pipeline.daemon import supervisor
from pipeline.daemon.server import Poller, Server
from pipeline.pty import host


def test_an_operator_kill_does_not_respawn_or_charge_no_result():
    """`kill` stops a stage and the ticket waits for the human: no respawn
    note, no `no_result` charge."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    snap = Ticket.load(path)
    log = d / ".project" / "logs" / "TICKET-001.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    child = types.SimpleNamespace(terminate=lambda: None, pid=1, returncode=-15, poll=lambda: -15)
    rec = {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
           "path": path, "tid": "TICKET-001", "stage": "plan-validation",
           "session": "s1", "log": log, "wt": d, "meta": snap,
           "before": None, "proc": child}
    me = types.SimpleNamespace(_running=lambda req: (str(d), rec))
    Server._op_kill(me, None, 1, {"ticket": "TICKET-001"})

    supervisor.finish(d, rec)
    t = Ticket.load(path)
    assert t.counters.get("no_result", 0) == 0, t.counters
    assert "will respawn" not in "".join(e.text for e in t.thread())
    shutil.rmtree(d, ignore_errors=True)


def test_an_interactive_stage_with_a_frozen_screen_does_not_keep_its_lease():
    """A REPL parked at a permission prompt for hours is detected: its lease
    is not renewed forever."""
    d = project()
    path = d / ".project/tickets/TICKET-001.md"
    t = Ticket.load(path)
    holder = f"planning-{os.getpid()}"
    t.lease = {"holder": holder,
               "expires": (T.now() + timedelta(minutes=1)).isoformat()}
    t.save()
    screen = pyte.Screen(80, 24)
    pyte.Stream(screen).feed("This command requires approval")
    child = types.SimpleNamespace(poll=lambda: None)
    inflight = {t.id: {"proc": child, "stage": "planning", "meta": t,
                       "screen": screen, "pipe": object()}}
    real = supervisor.now
    try:
        supervisor.renew_leases(d, inflight)
        later = real() + timedelta(hours=2)
        supervisor.now = lambda: later
        t2 = Ticket.load(path)
        t2.lease = {"holder": holder,
                    "expires": (later + timedelta(minutes=1)).isoformat()}
        t2.save()
        inflight[t.id]["meta"].lease = t2.lease
        before = dict(t2.lease)
        supervisor.renew_leases(d, inflight)
    finally:
        supervisor.now = real
    after = Ticket.load(path)
    assert after.stage == "escalated" or after.lease == before, \
        "a screen frozen for 2 hours still had its lease renewed"
    shutil.rmtree(d, ignore_errors=True)


def _killed_rec(d):
    path = d / ".project/tickets/TICKET-001.md"
    log = d / ".project" / "logs" / "TICKET-001.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    child = types.SimpleNamespace(terminate=lambda: None, pid=1, returncode=-15, poll=lambda: -15)
    return {"fh": log.open("w"), "prompt": d / "gone.md", "settings": None,
            "path": path, "tid": "TICKET-001", "stage": "plan-validation",
            "session": "s1", "log": log, "wt": d, "meta": Ticket.load(path),
            "before": None, "proc": child}


def test_an_idle_interactive_session_is_ended():
    tmp = Path(tempfile.mkdtemp())
    proc, pipe = host.start("read x", tmp, dict(os.environ))
    rec = {"proc": proc, "mode": "interactive", "stage": "planning", "idle": "x"}
    try:
        supervisor.end_interactive(tmp, {"TICKET-001": rec})
        assert rec["proc"].wait(5) is not None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_session_that_is_not_idle_is_left_running():
    tmp = Path(tempfile.mkdtemp())
    proc, pipe = host.start("read x", tmp, dict(os.environ))
    rec = {"proc": proc, "mode": "interactive", "stage": "planning", "idle": None}
    try:
        supervisor.end_interactive(tmp, {"TICKET-001": rec})
        assert rec["proc"].poll() is None
    finally:
        proc.terminate()
        proc.wait(5)
        shutil.rmtree(tmp, ignore_errors=True)


def test_an_idle_kill_charges_idle_kills_and_quotes_the_screen():
    d = project()
    rec = _killed_rec(d)
    rec["idle"] = "This command requires approval"
    supervisor.finish(d, rec)
    t = Ticket.load(rec["path"])
    assert t.counters.get("idle_kills") == 1, t.counters
    assert t.counters.get("no_result", 0) == 0
    assert t.stage == "plan-validation"
    assert not (t.lease or {}).get("holder")
    assert "This command requires approval" in "".join(e.text for e in t.thread())
    shutil.rmtree(d, ignore_errors=True)


def test_a_ticket_with_an_idle_kill_spawns_headless():
    class Attachable(Poller):
        attachable = True

        def watchers(self, project=None):
            return 1

    d = project()
    t = Ticket.load(d / ".project/tickets/TICKET-001.md")
    t.counters["idle_kills"] = 1
    t.save()
    poller = Attachable()
    rec = supervisor.spawn(d, d, "TICKET-001", "planning", harness("fake"), poller)
    try:
        assert rec["mode"] == "batch"
    finally:
        rec["proc"].wait()
        supervisor.close_child(rec)
        poller.close()
        shutil.rmtree(d, ignore_errors=True)


def test_a_killed_stage_resumes_without_force():
    from pipeline.cli.main import cmd_resume
    d = project()
    rec = _killed_rec(d)
    me = types.SimpleNamespace(_running=lambda req: (str(d), rec))
    Server._op_kill(me, None, 1, {"ticket": "TICKET-001"})
    supervisor.finish(d, rec)
    cmd_resume(argparse.Namespace(project=str(d), id="TICKET-001", stage="planning",
                                  note="redirect", grant=None, reset=None, force=False))
    t = Ticket.load(rec["path"])
    assert t.stage == "planning"
    assert t.counters.get("no_result", 0) == 0
    shutil.rmtree(d, ignore_errors=True)
