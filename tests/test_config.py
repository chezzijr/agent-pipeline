"""`project_config()` must read the committed config, not the working tree:
a ticket branch cannot be allowed to rewrite the commands that judge it."""
import tempfile
from pathlib import Path

from pipeline.core import PipelineError
from pipeline.core.config import format_test_cmd, project_config, stage_extra
from tests.helpers import git_project


def test_an_uncommitted_edit_to_pipeline_toml_does_not_change_project_config():
    d, sh = git_project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="pytest -x {test}"\ntest_suite="true"\n'
        'test_suite_without_new="true"\nbase="main"\n')
    sh("git add -A && git commit -qm init-config")

    committed = project_config(d)["test_one"]
    assert committed == "pytest -x {test}"

    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\nbase="main"\n')

    assert project_config(d)["test_one"] == committed


def test_project_config_falls_back_to_disk_when_git_has_no_copy():
    """A freshly `pipeline init`-ed project has not committed `.project/`,
    and `pipeline init --private` never will. Both must still run."""
    d, _ = git_project()          # writes the config AFTER its only commit
    assert project_config(d)["test_one"] == "true"
    plain = Path(tempfile.mkdtemp())
    (plain / ".project").mkdir()
    (plain / ".project" / "pipeline.toml").write_text('test_one="from-disk"\n')
    assert project_config(plain)["test_one"] == "from-disk"   # not a repo


def test_project_config_still_raises_when_there_is_no_config_anywhere():
    d, _ = git_project()
    (d / ".project" / "pipeline.toml").unlink()
    try:
        project_config(d)
        assert False, "a project with no config must raise"
    except PipelineError as e:
        assert "run `pipeline init" in str(e)


def test_an_uncommitted_stage_extra_must_not_reach_stage_extra():
    """A read-only stage can write `.project/stages/<stage>.extra.md` with no
    commit, no diff, no snapshot and no gate. `stage_extra()` must read it the
    way `project_config()` reads its own file: from HEAD, falling back to disk
    only when git has no copy at all."""
    d, sh = git_project()
    (d / ".project" / "stages").mkdir(parents=True)
    (d / ".project" / "stages" / "implementing.extra.md").write_text("SAFE\n")
    sh("git add -A && git commit -qm init-extra")

    (d / ".project" / "stages" / "implementing.extra.md").write_text("INJECTED-9137\n")

    assert "INJECTED-9137" not in stage_extra(d, "implementing")


def test_format_test_cmd_substitutes_test_path_and_name():
    test = "tests/test_gate.py::test_broken"
    assert format_test_cmd("pytest -x {test}", test) == "pytest -x tests/test_gate.py::test_broken"
    assert format_test_cmd("cargo test {name}", test) == "cargo test test_broken"
    assert format_test_cmd("jest {path}", test) == "jest tests/test_gate.py"
    assert format_test_cmd("pytest {path} -k {name}", "tests/a b.py::t x") == (
        "pytest 'tests/a b.py' -k 't x'")


def test_format_test_cmd_leaves_other_braces_untouched():
    """`test_suite` was never `.format()`ed, and `str.format` raised
    `KeyError: 't##*'` on `${t##*::}` -- both must keep working."""
    cmd = """awk '{print $1}' && cargo test -- --skip "${t##*::}" {name}"""
    assert format_test_cmd(cmd, "tests/f.rs::t_a") == (
        """awk '{print $1}' && cargo test -- --skip "${t##*::}" t_a""")
