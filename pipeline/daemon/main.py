"""`pipelined` -- one daemon, every registered project, one select loop.

Deliberately a raw foreground process: `systemd --user`, tmux or `pipeline
start` supervise it. It does not daemonise itself, write a pidfile, or restart
anything -- the socket is the liveness check and the pid comes back from
`ping`.
"""
import argparse
import os
import sys
import time

from pipeline.core import PipelineError, line_buffer_stdout
from pipeline.daemon import supervisor
from pipeline.daemon.server import Server
from pipeline.daemon.store import SOURCE_CHANGED, Store

RESTART_MAX = 3
RESTART_WINDOW = 60.0
COUNT_VAR = "PIPELINE_UPGRADE_RESTARTS"
SINCE_VAR = "PIPELINE_UPGRADE_SINCE"


def restart_budget(env, now: float) -> tuple[int, float] | None:
    """`None` refuses a restart; otherwise the (count, since) pair the exec
    passes on. The env is operator-writable, so a bad value reads as no
    restarts spent rather than raising."""
    try:
        count = int(env.get(COUNT_VAR, 0))
        since = float(env.get(SINCE_VAR, 0.0))
    except (TypeError, ValueError):
        count, since = 0, 0.0
    if now - since > RESTART_WINDOW:
        count, since = 0, now
    if count >= RESTART_MAX:
        return None
    return (count + 1, since)


def main() -> None:
    """`--restart-on-upgrade`'s `os.execve` is safe and bounded:

    1. `serve()`'s `finally` releases the socket, the flocks and every lease
       before it returns, so the new image never contends with the old one.
    2. `os.execve` keeps the pid, the log fd and the session -- a clean
       handoff, not a second daemon.
    3. The new image re-snapshots the module mtimes, so one merged change
       cannot fire the restart twice.
    4. A restart never runs for `signal`, `drained` or `error` -- only for
       `source_changed`.
    5. `restart_budget()`'s refusal exits 1, so a `Restart=on-success`
       systemd unit stops with it instead of spinning.
    """
    line_buffer_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=int, default=10)
    ap.add_argument("--harness", help="override every project's configured harness")
    ap.add_argument("-j", "--max-parallel", type=int, default=3,
                    help="agents in flight across every registered project")
    ap.add_argument("--socket", help="override the daemon socket path (default: "
                         "$XDG_RUNTIME_DIR/pipeline/daemon.sock, or "
                         "/tmp/pipeline-$UID/daemon.sock when unset)")
    ap.add_argument("--db", help="override the event db (default: "
                         "$XDG_STATE_HOME/pipeline/events.db, or "
                         "~/.local/state/pipeline/events.db)")
    ap.add_argument("--once", action="store_true",
                    help="drain every project's queue and exit")
    ap.add_argument("--restart-on-upgrade", action="store_true",
                    help="after a source change, re-exec this process into the "
                         "merged code (at most 3 times in 60s)")
    args = ap.parse_args()
    try:
        store = Store(args.db)
        server = Server(store, args.socket)
        reason = supervisor.serve(args.interval, args.harness, args.max_parallel,
                                  store, server, args.once)
    except PipelineError as e:
        sys.exit(f"error: {e}")

    if args.restart_on_upgrade and reason == SOURCE_CHANGED:
        budget = restart_budget(os.environ, time.time())
        if budget is None:
            print("pipelined: 3 upgrade restarts inside 60s -- not restarting; "
                  "run pipeline start when the source settles")
            sys.exit(1)
        count, since = budget
        print(f"pipelined: restarting into the merged code "
              f"(restart {count} of {RESTART_MAX})")
        store.close()
        os.execve(sys.executable,
                  [sys.executable, "-m", "pipeline.daemon.main", *sys.argv[1:]],
                  {**os.environ, COUNT_VAR: str(count), SINCE_VAR: str(since)})


if __name__ == "__main__":
    main()
