"""`project_config()` must read the committed config, not the working tree:
a ticket branch cannot be allowed to rewrite the commands that judge it."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pipeline.core import PipelineError, reset_notices
from pipeline.core.config import (cap_config, format_test_cmd,
                                  format_tests_cmd, harness, install_skill,
                                   pin_dir, pin_path, project_config,
                                   project_harness, project_max_parallel,
                                   project_skill, render,
                                   selector_failure, selector_parts,
                                   skill_digest, skill_marks, skill_status,
                                   stage_config, stage_extra,
                                  suite_failure)
from pipeline.daemon.registry import config_dir
from tests.helpers import ROOT, git_project


def cmd(cfg):
    return render(harness("claude-code"), cfg, tid="TICKET-001", project=Path("/tmp"),
                  ticket=Path("/tmp/t.md"), result_file=Path("/tmp/t.result"),
                  session="s", prompt=Path("/tmp/t.md"))


def test_project_harness_uses_config_then_cli_override():
    d = Path(tempfile.mkdtemp())
    (d / ".project").mkdir()
    (d / ".project" / "pipeline.toml").write_text('harness = "codex"\n')
    assert project_harness(d) == "codex"
    assert project_harness(d, "fake") == "fake"


def test_project_harness_rejects_unknown_and_path_names():
    d = Path(tempfile.mkdtemp())
    (d / ".project").mkdir()
    cfg = d / ".project" / "pipeline.toml"
    for value in ("missing", "../codex"):
        cfg.write_text(f'harness = "{value}"\n')
        try:
            project_harness(d)
            assert False, value
        except PipelineError as e:
            assert "harness" in str(e)


def test_render_cap_does_not_scale_with_diff_size():
    """review's cap must grow with the plan it has to read the way
    bound_for() already grows plan_validation_attempts with plan size
    (DEC-047). Today it does not: render() computes the cap from static
    frontmatter/harness config alone, so a 15-file, 40-step plan gets the
    same cap as an empty one."""
    hcfg = harness("claude-code")
    cfg = stage_config("review")
    prompt = Path("/tmp/t.md")

    baseline = render(hcfg, cfg, tid="TICKET-001", project=Path("/tmp"),
                       ticket=Path("/tmp/t.md"), result_file=Path("/tmp/t.result"),
                       session="s", prompt=prompt)
    assert "--max-budget-usd 4" in baseline

    scaled_cfg = {**cfg, "counters": {"plan_files": 15, "plan_steps": 40}}
    scaled = render(hcfg, scaled_cfg, tid="TICKET-001", project=Path("/tmp"),
                     ticket=Path("/tmp/t.md"), result_file=Path("/tmp/t.result"),
                     session="s", prompt=prompt)
    assert "--max-budget-usd 4" not in scaled, (
        "expected the cap to grow with plan_files/plan_steps the way "
        "bound_for() scales plan_validation_attempts, but render() emitted "
        "the same --max-budget-usd 4 for a 15-file, 40-step plan as for "
        "one with no counters at all")


def test_a_project_max_usd_override_is_not_scaled_past():
    """A project's own `max_usd` pins the cap: TICKET-069's direction rule
    applies to money too, so a computed cap never exceeds what the operator
    asked for unless the operator also asks for scaling."""
    d, sh = git_project()
    with open(d / ".project" / "pipeline.toml", "a") as f:
        f.write("[stages.review]\nmax_usd = 2\n")
    sh("git add -A && git commit -qm config")
    cfg = cap_config("review", stage_config("review", d), d,
                      {"plan_files": 15, "plan_steps": 40})
    assert "counters" not in cfg, "an operator own max_usd was scaled past"
    assert "--max-budget-usd 2" in cmd(cfg)


def test_a_project_can_ask_for_scaling_on_top_of_its_own_cap():
    """`scale_usd = true` alongside a project's own `max_usd` asks for
    scaling on top of that number instead of pinning it."""
    d, sh = git_project()
    with open(d / ".project" / "pipeline.toml", "a") as f:
        f.write("[stages.review]\nmax_usd = 6\nscale_usd = true\n")
    sh("git add -A && git commit -qm config")
    cfg = cap_config("review", stage_config("review", d), d,
                      {"plan_files": 15, "plan_steps": 40})
    assert "--max-budget-usd 11" in cmd(cfg)


def test_pinning_max_usd_without_scale_usd_warns(capsys):
    """A project that sets `max_usd` on a USD_SCALED stage without also
    setting `scale_usd` silently opts that stage out of scaling
    (TICKET-095). cap_config() must print one line naming the pinned cap
    and the scaling it turned off, so the operator can add
    `scale_usd = true` if that was not the intent."""
    d, sh = git_project()
    with open(d / ".project" / "pipeline.toml", "a") as f:
        f.write("[stages.review]\nmax_usd = 9\n")
    sh("git add -A && git commit -qm config")
    cap_config("review", stage_config("review", d), d,
               {"plan_files": 15, "plan_steps": 40})
    out = capsys.readouterr().out
    assert "max_usd" in out and "9" in out, (
        f"expected a warning naming the pinned max_usd=9 and the scaling "
        f"it disabled, got: {out!r}")


def test_pinning_max_usd_with_scale_usd_does_not_warn(capsys):
    d, sh = git_project()
    with open(d / ".project" / "pipeline.toml", "a") as f:
        f.write("[stages.review]\nmax_usd = 9\nscale_usd = true\n")
    sh("git add -A && git commit -qm config")
    cap_config("review", stage_config("review", d), d,
               {"plan_files": 15, "plan_steps": 40})
    out = capsys.readouterr().out
    assert out == ""


def test_the_pinned_cap_warning_prints_once_per_process(capsys):
    """The pinned-cap warning is a fact about the project's config, not
    about one review, so a second `cap_config()` call for the same project
    and stage must not reprint it (TICKET-096)."""
    reset_notices()
    d, sh = git_project()
    with open(d / ".project" / "pipeline.toml", "a") as f:
        f.write("[stages.review]\nmax_usd = 9\n")
    sh("git add -A && git commit -qm config")
    cap_config("review", stage_config("review", d), d,
               {"plan_files": 15, "plan_steps": 40})
    cap_config("review", stage_config("review", d), d,
               {"plan_files": 15, "plan_steps": 40})
    out = capsys.readouterr().out
    assert out.count("max_usd") == 1, (
        f"expected the pinned-cap warning once per process, got: {out!r}")

    d2, sh2 = git_project()
    with open(d2 / ".project" / "pipeline.toml", "a") as f:
        f.write("[stages.quick-review]\nmax_usd = 9\n")
    sh2("git add -A && git commit -qm config")
    cap_config("quick-review", stage_config("quick-review", d2), d2,
               {"plan_files": 15, "plan_steps": 40})
    out2 = capsys.readouterr().out
    assert out2.count("max_usd") == 1, (
        f"expected a second project and stage to warn once too, got: "
        f"{out2!r}")


def test_the_project_decides_which_stages_scale_their_cap():
    """Only the stages in `USD_SCALED` scale by default, and a project can
    opt a scaled stage back out with `scale_usd = false`."""
    d, _ = git_project()
    counters = {"plan_files": 15, "plan_steps": 40}
    assert "counters" in cap_config("review", stage_config("review", d), d, counters)
    assert "counters" not in cap_config("implementing", stage_config("implementing", d), d, counters)
    assert "--max-budget-usd 8" in cmd(cap_config("implementing", stage_config("implementing", d), d, counters))

    d2, sh2 = git_project()
    with open(d2 / ".project" / "pipeline.toml", "a") as f:
        f.write("[stages.review]\nscale_usd = false\n")
    sh2("git add -A && git commit -qm config")
    assert "counters" not in cap_config("review", stage_config("review", d2), d2, counters)


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


def test_private_project_lets_a_stage_rewrite_test_one_with_no_diff():
    """`pipeline init --private` excludes `.project/` via
    `.git/info/exclude`, so the config is NEVER in HEAD -- not a transient
    state like a fresh `init`, but permanent for the life of the clone. The
    disk-fallback the HEAD read needs for that fresh-init case then also
    covers this one, silently, forever: an edit to `test_one` takes effect
    with no commit, no diff and no `machine.FENCED` stop at
    `awaiting-merge`."""
    d, sh = git_project()
    (d / ".git" / "info").mkdir(exist_ok=True)
    (d / ".git" / "info" / "exclude").write_text(".project/\n")

    committed = project_config(d)["test_one"]
    assert committed == "true"

    (d / ".project" / "pipeline.toml").write_text(
        'test_one="rm -rf /"\ntest_suite="true"\n'
        'test_suite_without_new="true"\nbase="main"\n')

    status = sh("git status --porcelain").stdout
    assert ".project" not in status

    assert project_config(d)["test_one"] == "true", (
        "a --private project must keep the HEAD-read guarantee, "
        f"but got {project_config(d)['test_one']!r}")


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


def test_project_max_parallel_reads_the_committed_value():
    d, sh = git_project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\n'
        'base="main"\nmax_parallel = 1\n')
    sh("git add -A && git commit -qm 'set max_parallel'")

    assert project_max_parallel(d) == 1

    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\n'
        'base="main"\nmax_parallel = 9\n')

    assert project_max_parallel(d) == 1


def test_project_max_parallel_is_none_without_a_key():
    d, _ = git_project()
    assert project_max_parallel(d) is None


def test_project_max_parallel_refuses_a_value_below_one():
    d, sh = git_project()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\n'
        'base="main"\nmax_parallel = 0\n')
    sh("git add -A && git commit -qm 'zero max_parallel'")
    try:
        project_max_parallel(d)
        assert False, "max_parallel = 0 must raise"
    except PipelineError as e:
        assert "must be an integer >= 1" in str(e)

    (d / ".project" / "pipeline.toml").write_text(
        'test_one="true"\ntest_suite="true"\ntest_suite_without_new="true"\n'
        'base="main"\nmax_parallel = true\n')
    sh("git add -A && git commit -qm 'bool max_parallel'")
    try:
        project_max_parallel(d)
        assert False, "max_parallel = true must raise"
    except PipelineError as e:
        assert "must be an integer >= 1" in str(e)


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


def test_format_tests_cmd_substitutes_one_test_or_many():
    """TICKET-066: `test_file` may hold a list. A bare placeholder joins
    the values with spaces; `{test:<prefix>}` repeats the prefix before
    each, which is the only way `pytest --deselect` excludes more than one
    test in a single run. `format_test_cmd` is unchanged for one test."""
    a, b = "a.py::t", "b.py::u"
    assert format_tests_cmd("pytest -x {test}", [a]) == "pytest -x a.py::t"
    assert format_tests_cmd("pytest -x {test}", [a, b]) == "pytest -x a.py::t b.py::u"
    assert format_tests_cmd("pytest {test:--deselect }", [a, b]) == (
        "pytest --deselect a.py::t --deselect b.py::u")
    assert format_tests_cmd("pytest {test:}", [a, b]) == "pytest a.py::t b.py::u"
    assert format_tests_cmd("pytest --ignore {path}", [a, "a.py::u"]) == (
        "pytest --ignore a.py")
    assert format_tests_cmd("pytest -x {test}", ["a.py::t[1]"]) == "pytest -x 'a.py::t[1]'"
    assert format_tests_cmd("""awk '{print $1}' {name}""", [a]) == """awk '{print $1}' t"""
    assert format_test_cmd("pytest -x {test}", a) == "pytest -x a.py::t"
    assert format_test_cmd("pytest {test}", "") == "pytest ''"


def _probe_project(test_one="false", test_suite="true"):
    """A throwaway project. It is not a git repo, so `project_config()`
    takes its disk fallback (DEC-037)."""
    d = Path(tempfile.mkdtemp())
    (d / ".project").mkdir()
    (d / ".project" / "pipeline.toml").write_text(
        'test_one = "%s"\ntest_suite = "%s"\n'
        'test_suite_without_new = "true"\n' % (test_one, test_suite))
    return d


def test_suite_failure_tells_a_broken_command_from_a_red_suite():
    """A suite that runs and fails is the normal state of a project with an
    open bug and must register. Only a suite that cannot run is refused."""
    missing = suite_failure(_probe_project(test_suite="pipeline-068-nonexistent-command-xyz"))
    assert missing and "pipeline-068-nonexistent-command-xyz" in missing
    assert "exit 127" in missing
    nothing = suite_failure(_probe_project(test_suite="echo no tests ran; exit 5"))
    assert nothing and "ran no tests" in nothing
    assert suite_failure(_probe_project(test_suite="echo 1 failed; exit 1")) is None
    assert suite_failure(_probe_project(test_suite="true")) is None
    # DEC-067: `test_suite` has never been `str.format`ed, so a literal
    # brace must reach the shell instead of raising
    assert suite_failure(_probe_project(test_suite="echo ${t##*::} ok")) is None


def test_selector_failure_wants_test_one_to_fail_when_it_matches_nothing():
    """`gate()` cannot tell `the test passed` from `the selector matched
    nothing` by reading output: a runner may name a test only when it
    fails. The project's own command knows its runner and can tell."""
    passes = selector_failure(_probe_project(test_one="true"))
    assert passes and "exited 0" in passes
    assert "pipeline_register_probe_no_such_test" in passes
    missing = selector_failure(_probe_project(test_one="pipeline-068-nonexistent-command-xyz"))
    assert missing and "exit 127" in missing
    assert selector_failure(_probe_project(test_one="false")) is None
    assert selector_failure(_probe_project(test_one="echo no test matched {test}; exit 1")) is None
    # DEC-067: `format_test_cmd()` leaves every other brace verbatim, so
    # this command is judged by its exit code. Under `str.format` it would
    # raise `KeyError: 't##*'` and this arm would error instead of pass.
    assert selector_failure(_probe_project(test_one="echo ${t##*::} matched nothing; exit 1")) is None


def test_a_not_yet_committed_config_is_not_pinned():
    """A fresh, untracked-but-not-ignored project is the load-bearing
    fresh-`init` arm DEC-037 names. It must keep reading disk live, and must
    never create a pin."""
    d, sh = git_project()
    assert project_config(d)["test_one"] == "true"
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="pytest -x {test}"\ntest_suite="true"\n'
        'test_suite_without_new="true"\nbase="main"\n')
    assert project_config(d)["test_one"] == "pytest -x {test}"
    assert not pin_dir(d).exists()


def test_the_pin_is_a_file_so_a_spawned_child_reads_it_too():
    """An in-process cache would not protect the Tier A gate: it runs as a
    spawned child (`gate_cmd()`). The pin must be readable by a fresh
    process."""
    d, sh = git_project()
    (d / ".git" / "info").mkdir(exist_ok=True)
    (d / ".git" / "info" / "exclude").write_text(".project/\n")
    project_config(d)
    (d / ".project" / "pipeline.toml").write_text(
        'test_one="rm -rf /"\ntest_suite="true"\n'
        'test_suite_without_new="true"\nbase="main"\n')
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys;from pathlib import Path;"
         "from pipeline.core.config import project_config;"
         "print(project_config(Path(sys.argv[1]))['test_one'])",
         str(d)],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert r.stdout.strip() == "true", r.stdout + r.stderr


def test_the_pin_directories_are_private():
    """The pin decides which commands the gate runs; a world-writable parent
    is a way to rewrite it without touching the file."""
    d, sh = git_project()
    (d / ".git" / "info").mkdir(exist_ok=True)
    (d / ".git" / "info" / "exclude").write_text(".project/\n")
    project_config(d)
    for p in (config_dir(), config_dir() / "pinned", pin_dir(d),
              pin_path(d, ".project/pipeline.toml").parent):
        assert oct(p.stat().st_mode & 0o777) == "0o700", p


def test_a_private_projects_stage_extra_is_pinned_too():
    """`stage_extra()` shares `project_config()`'s bug: a git-ignored
    `.project/stages/<stage>.extra.md` must pin too, or a stage can inject
    prose into a later spawn's prompt with no commit."""
    d, sh = git_project()
    (d / ".git" / "info").mkdir(exist_ok=True)
    (d / ".git" / "info" / "exclude").write_text(".project/\n")
    (d / ".project" / "stages").mkdir(parents=True)
    (d / ".project" / "stages" / "implementing.extra.md").write_text("SAFE\n")
    assert stage_extra(d, "implementing").strip() == "SAFE"
    (d / ".project" / "stages" / "implementing.extra.md").write_text("INJECTED-9137\n")
    assert "INJECTED-9137" not in stage_extra(d, "implementing")


def test_selector_parts_has_a_rest_placeholder_for_non_pytest_selectors():
    """A Rust/Go/JVM selector needs `{path}` to stay a real file the gate
    can stat and copy, and a module selector for the runner -- the two
    differ when the test id has more than one `::`. `{rest}` is everything
    after the FIRST `::`, so `test_one = "cargo test {rest}"` runs the
    right test while `{path}` still names `src/vm.rs`."""
    parts = selector_parts("src/vm.rs::vm::tests::foo")
    assert parts["path"] == "src/vm.rs"
    assert parts["rest"] == "vm::tests::foo"

    cmd = format_test_cmd("cargo test {rest}", "src/vm.rs::vm::tests::foo")
    assert cmd == "cargo test vm::tests::foo"


def test_selector_parts_rest_falls_back_to_the_whole_value_without_a_separator():
    """A pytest selector has no `::` to split on the first occurrence of, so
    `rest` must degrade to the whole id like `path` and `name` already do --
    an empty `{rest}` would make `cargo test ''` match every test."""
    assert selector_parts("tests/t.py")["rest"] == "tests/t.py"
    assert format_test_cmd("cargo test {rest}", "tests/t.py") == "cargo test tests/t.py"


def test_skill_status_reads_an_unrecorded_difference_as_unknown():
    """A copy that differs from the packaged template with no install record
    (a project scaffolded before `skills.json` existed) must not read as
    `stale` -- `stale` implies a known-good install that drifted, and nothing
    here knows that. Installing it records the digest, so the same copy then
    reads `current`."""
    d = Path(tempfile.mkdtemp())
    skill = d / ".claude" / "skills" / "file-ticket" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# ours\n")
    states = {(target, name): state for target, name, _, state in skill_status(d)}
    assert states[("claude", "file-ticket")] == "unknown", states
    assert states[("codex", "file-ticket")] == "absent", states

    install_skill(d, "file-ticket")
    states = {(target, name): state for target, name, _, state in skill_status(d)}
    assert states[("claude", "file-ticket")] == "current", states
    marks = skill_marks(d)
    assert marks["file-ticket"] == marks["claude:file-ticket"], marks


def test_legacy_skill_marks_apply_only_to_the_claude_copy():
    """The old manifest schema predates Codex installation. Treating its bare
    name as both destinations would call an unrelated Codex copy stale and let
    a plain refresh overwrite it."""
    d = Path(tempfile.mkdtemp())
    old = "# previously installed\n"
    for target in ("claude", "codex"):
        skill = project_skill(d, "file-ticket", target)
        skill.parent.mkdir(parents=True)
        skill.write_text(old)
    marks = d / ".project" / "skills.json"
    marks.parent.mkdir()
    marks.write_text(json.dumps({"file-ticket": skill_digest(old)}))

    states = {(target, name): state for target, name, _, state in skill_status(d)}
    assert states[("claude", "file-ticket")] == "stale", states
    assert states[("codex", "file-ticket")] == "unknown", states


def test_skill_install_refuses_every_symlinked_destination_ancestor():
    d = Path(tempfile.mkdtemp())
    outside = Path(tempfile.mkdtemp())
    (d / ".agents").mkdir()
    (d / ".agents" / "skills").symlink_to(outside, target_is_directory=True)
    states = {(target, name): state for target, name, _, state in skill_status(d)}
    assert states[("codex", "file-ticket")] == "linked", states
    try:
        install_skill(d, "file-ticket", "codex")
        assert False, "install_skill followed a destination ancestor symlink"
    except PipelineError as e:
        assert "symlinked skill path" in str(e)
    assert not (outside / "file-ticket" / "SKILL.md").exists()
