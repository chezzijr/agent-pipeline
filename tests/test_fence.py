"""`fenced_touches()` matches symbols, not whole files."""
from pipeline.core.fence import fenced_touches
from tests.helpers import git_project

MODULE = "def func_a():\n    return 1\n\n\ndef func_b():\n    return 2\n"
FENCED = {"module.py": ("func_a",)}


def test_a_neighbouring_function_does_not_trip_the_fence():
    d, sh = git_project()
    (d / "module.py").write_text(MODULE)
    sh("git add -A && git commit -qm add-module")

    (d / "module.py").write_text(MODULE.replace("return 2", "return 22"))
    assert fenced_touches(d, "main", FENCED) == []

    (d / "module.py").write_text(MODULE.replace("return 1", "return 11"))
    assert fenced_touches(d, "main", FENCED) == ["module.py:func_a"]

    (d / "module.py").write_text("def func_b():\n    return 2\n")
    assert fenced_touches(d, "main", FENCED) == ["module.py:func_a (gone)"]


def test_a_change_to_the_committed_config_trips_the_fence():
    """`.project/pipeline.toml` names the commands Tier A and `verifying`
    trust, so a ticket that edits it stops for a human. This one calls
    `fenced_touches` with the real `FENCED`, not the module-level fake."""
    d, sh = git_project()
    sh("git add -A && git commit -qm commit-config")
    assert fenced_touches(d, "main") == []
    (d / ".project" / "pipeline.toml").write_text('test_one="true"\n')
    assert fenced_touches(d, "main") == [".project/pipeline.toml"]
