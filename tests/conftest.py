"""Make the repo checkout importable so the suite runs without installing."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# macOS hides its temp root behind a symlink (`/var` -> `/private/var`) and
# `registry.register()` stores what `Path.resolve()` returns, so a test that
# compares a `mkdtemp()` path against what the registry hands back fails on the
# symlink rather than on the code. Resolve the root once, for every test and
# every subprocess they spawn.
os.environ["TMPDIR"] = tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())
