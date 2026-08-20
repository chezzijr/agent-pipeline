"""`pipelined` -- the dispatcher loop behind its own entry point."""
import argparse
from pathlib import Path

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
    supervisor.run(Path(args.project).resolve(), args.once, args.interval,
                   args.harness, args.max_parallel)


if __name__ == "__main__":
    main()
