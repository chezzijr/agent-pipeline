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
