"""`fenced_touches()` matches symbols, not whole files."""
from pathlib import Path

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


def test_a_directory_entry_trips_on_any_file_under_it():
    d, sh = git_project()
    (d / ".project" / "stages").mkdir(parents=True)
    (d / ".project" / "stages" / "review.extra.md").write_text("extra\n")
    sh("git add -A")
    assert fenced_touches(d, "main", {".project/stages/": None}) == \
        [".project/stages/review.extra.md"]
    assert fenced_touches(d, "main", {"other/": None}) == []


def test_a_change_to_the_committed_config_trips_the_fence():
    """`.project/pipeline.toml` names the commands Tier A and `verifying`
    trust, so a ticket that edits it stops for a human. This one calls
    `fenced_touches` with the real `FENCED`, not the module-level fake."""
    d, sh = git_project()
    sh("git add -A && git commit -qm commit-config")
    assert fenced_touches(d, "main") == []
    (d / ".project" / "pipeline.toml").write_text('test_one="true"\n')
    assert fenced_touches(d, "main") == [".project/pipeline.toml"]


def test_editing_the_fenced_dict_itself_trips_the_fence():
    """`FENCED` is what stops a guard change merging unattended, but
    `machine.FENCED` maps `pipeline/core/machine.py` to
    `("transition", "CONTROL_FIELDS")` -- not to `FENCED` itself. A ticket
    that adds an entry to `FENCED`, touching nothing else in the file,
    must trip the fence. Uses the real, module-level `FENCED` (like
    TICKET-037/038 did on main)."""
    d, sh = git_project()
    machine = d / "pipeline" / "core" / "machine.py"
    machine.parent.mkdir(parents=True)
    body = (
        "CONTROL_FIELDS = ('stage',)\n\n\n"
        "FENCED = {\n"
        '    ".project/pipeline.toml": None,\n'
        "}\n\n\n"
        "def transition(stage, result):\n"
        "    return stage\n"
    )
    machine.write_text(body)
    sh("git add -A && git commit -qm commit-machine")
    assert fenced_touches(d, "main") == []
    machine.write_text(body.replace(
        '".project/pipeline.toml": None,\n',
        '".project/pipeline.toml": None,\n    ".project/extra.toml": None,\n',
    ))
    sh("git add -A")
    assert fenced_touches(d, "main") != []


def test_an_unfenced_symbol_in_machine_py_still_merges_unattended():
    """The `pipeline/core/machine.py` entry in `FENCED` names symbols, not
    the whole file (DEC-031), so a ticket that edits only `BOUNDS` merges
    unattended. Fails if the entry is widened to `None`."""
    d, sh = git_project()
    machine = d / "pipeline" / "core" / "machine.py"
    machine.parent.mkdir(parents=True)
    body = (
        "CONTROL_FIELDS = ('stage',)\n\n\n"
        "BOUNDS = {'bugfix': 2}\n\n\n"
        "FENCED = {\n"
        '    ".project/pipeline.toml": None,\n'
        "}\n\n\n"
        "def transition(stage, result):\n"
        "    return stage\n"
    )
    machine.write_text(body)
    sh("git add -A && git commit -qm commit-machine")
    machine.write_text(body.replace("'bugfix': 2", "'bugfix': 3"))
    sh("git add -A")
    assert fenced_touches(d, "main") == []
