"""`pipelined` -- the dispatcher loop behind its own entry point."""
import argparse
import sys
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.daemon import supervisor


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=".", help="target project dir")
    ap.add_argument("--interval", type=int, default=10)
    ap.add_argument("--harness", default="claude-code")
    ap.add_argument("-j", "--max-parallel", type=int, default=3)
    ap.add_argument("--once", action="store_true",
                    help="drain the queue and exit")
    args = ap.parse_args()
    try:
        supervisor.run(Path(args.project).resolve(), args.once, args.interval,
                       args.harness, args.max_parallel)
    except PipelineError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
