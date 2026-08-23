"""`project_config()` must read the committed config, not the working tree:
a ticket branch cannot be allowed to rewrite the commands that judge it."""
from pipeline.core.config import project_config
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
