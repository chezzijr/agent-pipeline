"""TICKET-148: a running stage can be stopped cleanly."""
import os
import shutil
import types
from datetime import timedelta

import pyte

from helpers import project
from pipeline.core import ticket as T
from pipeline.core.ticket import Ticket
from pipeline.daemon import supervisor
from pipeline.daemon.server import Server


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
