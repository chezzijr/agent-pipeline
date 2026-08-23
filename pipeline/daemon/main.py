"""`pipelined` -- one daemon, every registered project, one select loop.

Deliberately a raw foreground process: `systemd --user`, tmux or `pipeline
start` supervise it. It does not daemonise itself, write a pidfile, or restart
anything -- the socket is the liveness check and the pid comes back from
`ping`.
"""
import argparse
import sys

from pipeline.core import PipelineError, line_buffer_stdout
from pipeline.daemon import supervisor
from pipeline.daemon.server import Server
from pipeline.daemon.store import Store


def main() -> None:
    line_buffer_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=int, default=10)
    ap.add_argument("--harness", default="claude-code")
    ap.add_argument("-j", "--max-parallel", type=int, default=3,
                    help="agents in flight per project")
    ap.add_argument("--socket", help="override the daemon socket path (default: "
                         "$XDG_RUNTIME_DIR/pipeline/daemon.sock, or "
                         "/tmp/pipeline-$UID/daemon.sock when unset)")
    ap.add_argument("--db", help="override the event db (default: "
                         "$XDG_STATE_HOME/pipeline/events.db, or "
                         "~/.local/state/pipeline/events.db)")
    ap.add_argument("--once", action="store_true",
                    help="drain every project's queue and exit")
    args = ap.parse_args()
    try:
        store = Store(args.db)
        server = Server(store, args.socket)
        supervisor.serve(args.interval, args.harness, args.max_parallel,
                         store, server, args.once)
    except PipelineError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
