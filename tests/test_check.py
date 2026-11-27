"""Tests for git-cicd check: decide, run and report locally."""

import pytest

from tests.conftest import git_cicd

LOG = 'echo "$CICD_JOB $(basename "$0")" >> "$LOG"\n'


@pytest.fixture
def project(repo, tmp_path):
    """main with two jobs; a feature branch that changes src/."""
    repo.script("ci/setup.sh", LOG)
    repo.script("ci/a.sh", LOG)
    repo.script("ci/b.sh", LOG)
    repo.script("ci/fail.sh", LOG + "exit 1\n")
    repo.write("src/app.py", "x\n")
    repo.write("docs/x.md", "x\n")
    repo.config({"jobs": {
        "first": {"on": ["open"], "branches": ["main"], "paths": ["src/**"],
                  "setup": "ci/setup.sh", "steps": ["ci/a.sh", "ci/b.sh"]},
        "second": {"on": ["open"], "branches": ["main"], "paths": ["src/**"],
                   "steps": ["ci/b.sh"]},
        "docs": {"on": ["open"], "branches": ["main"], "paths": ["docs/**"],
                 "steps": ["ci/a.sh"]},
        "release": {"on": ["merge"], "branches": ["main"],
                    "steps": ["ci/a.sh"]},
    }, "needs_nothing": ["*.md"]})
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    repo.commit("base")
    repo.git("checkout", "-q", "-b", "feature")
    repo.write("src/app.py", "y\n")
    repo.commit("feature change")
    repo.log = tmp_path / "log.txt"
    return repo


def check(repo, *args, **env):
    run_env = {"LOG": str(repo.log)}
    run_env.update(env)
    return repo.run("check", *args, env=run_env)


def logged(repo):
    return repo.log.read_text().splitlines() if repo.log.exists() else []


def test_defaults_decide_and_run_sequentially(project):
    result = check(project)
    assert result.returncode == 0, result.stdout + result.stderr
    # no upstream, no origin: target main, base main
    assert "target main, source feature" in result.stdout
    assert logged(project) == ["first a.sh", "first b.sh", "second b.sh"]
    out = result.stdout
    assert "git-cicd report" in out
    assert "docs: not needed (no changed file matches paths)" in out
    assert "release: not needed (not an open job)" in out
    assert out.strip().splitlines()[-1] == \
        "PASSED - 2 of 4 jobs needed, 2 passed"


def test_setup_not_run_without_flag(project):
    result = check(project)
    assert "first setup.sh" not in logged(project)
    assert "setup skipped (pass --setup to run it)" in result.stdout


def test_setup_run_with_flag(project):
    result = check(project, "--setup")
    assert result.returncode == 0
    assert logged(project)[:2] == ["first setup.sh", "first a.sh"]
    assert "setup skipped" not in result.stdout


def test_exit_1_when_blocking_job_fails(project):
    cfg = git_cicd.json.loads(
        (project.path / ".vendored/configs/git-cicd.json").read_text())
    cfg["jobs"]["second"]["steps"] = ["ci/fail.sh"]
    project.config(cfg)
    result = check(project)
    assert result.returncode == 1
    assert "failed (step ci/fail.sh, exit 1)" in result.stdout
    assert result.stdout.strip().splitlines()[-1].startswith("FAILED")


def test_non_blocking_failure_exit_0(project):
    cfg = git_cicd.json.loads(
        (project.path / ".vendored/configs/git-cicd.json").read_text())
    cfg["jobs"]["second"].update(steps=["ci/fail.sh"], blocking=False)
    project.config(cfg)
    result = check(project)
    assert result.returncode == 0, result.stdout


def test_single_job(project):
    result = check(project, "--job", "second")
    assert result.returncode == 0, result.stdout
    assert logged(project) == ["second b.sh"]
    assert "first: not needed (not selected (--job second))" in result.stdout


def test_single_job_not_needed_is_reported(project):
    result = check(project, "--job", "docs")
    assert result.returncode == 0
    assert logged(project) == []
    assert "docs: not needed (no changed file matches paths)" in result.stdout


def test_single_job_force_ignores_paths(project):
    result = check(project, "--job", "docs", "--force")
    assert result.returncode == 0
    assert logged(project) == ["docs a.sh"]
    assert "forced with --force (paths ignored)" in result.stdout


def test_force_still_bound_by_branches(project):
    result = check(project, "--job", "docs", "--force", "--target", "dev",
                   "--base", "main")
    assert logged(project) == []
    assert "target dev does not match branches" in result.stdout


def test_force_needs_job(project):
    result = check(project, "--force")
    assert result.returncode == 2
    assert "--force needs --job" in result.stderr


def test_unknown_job(project):
    result = check(project, "--job", "nope")
    assert result.returncode == 2
    assert "unknown job 'nope'" in result.stderr


def test_explicit_base_and_head(project):
    first = project.git("rev-parse", "HEAD")
    project.write("docs/x.md", "changed\n")
    project.commit("docs")
    # Only the docs commit: base = first feature commit, head = HEAD
    result = check(project, "--base", first, "--head", "HEAD")
    assert result.returncode == 0
    assert logged(project) == ["docs a.sh"]
    # Only the src commit
    project.log.unlink()
    result = check(project, "--base", "main", "--head", first)
    assert logged(project) == ["first a.sh", "first b.sh", "second b.sh"]


def test_target_from_origin_head(project, tmp_path):
    remote = tmp_path / "remote.git"
    project.git("init", "-q", "--bare", str(remote))
    project.git("remote", "add", "origin", str(remote))
    project.git("push", "-q", "origin", "main")
    project.git("checkout", "-q", "main")
    project.write("src/app.py", "main moved\n")
    project.commit("main moved locally only")
    project.git("checkout", "-q", "feature")
    project.git("remote", "set-head", "origin", "main")
    project.git("push", "-q", "-u", "origin", "feature")  # own upstream
    assert git_cicd.default_target(str(project.path), "feature") == "main"
    assert git_cicd.default_base(str(project.path), "main") == "origin/main"
    result = check(project)
    assert result.returncode == 0
    assert "target main, source feature" in result.stdout


def test_target_from_upstream(project):
    project.git("checkout", "-q", "-b", "plan/x", "main")
    project.git("checkout", "-q", "-b", "unit", "--track", "plan/x")
    assert git_cicd.default_target(str(project.path), "unit") == "plan/x"
    assert git_cicd.default_base(str(project.path), "plan/x") == "plan/x"


def test_works_without_github_env(project):
    # Repo.run strips every GITHUB_* variable from the environment.
    result = check(project)
    assert result.returncode == 0
    assert not list(project.path.glob("*summary*"))


def test_token_passthrough(project):
    project.script("ci/a.sh", 'echo "$GITHUB_TOKEN/$VENDOR_PAT" >> "$LOG"\n')
    project.commit("script")
    check(project, "--job", "docs", "--force", GITHUB_TOKEN="t",
          VENDOR_PAT="p")
    assert logged(project) == ["t/p"]


def test_stale_workflow_fails_verdict(project):
    (project.path / ".github/workflows/git-cicd-open.yml").write_text("stale\n")
    result = check(project)
    assert result.returncode == 1
    assert "workflows do not match config: run " \
        ".vendored/pkg/git-cicd/git-cicd generate" in result.stdout


def test_display_name_with_metacharacters_reaches_report_and_runs_nothing(
        repo, tmp_path):
    """A display name is data: shown literally, never run."""
    marker = tmp_path / "pwned"
    name = (f"It's \"$(touch {marker})\" `touch {marker}` $HOME; "
            f"touch {marker} | &")
    repo.script("ci/a.sh")
    repo.config({"jobs": {"unit": {"name": name, "on": ["open"],
                                   "branches": ["main"],
                                   "steps": ["ci/a.sh"]}}})
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    repo.commit("base")
    repo.git("checkout", "-q", "-b", "feature")
    repo.write("src/x", "y\n")
    repo.commit("change")
    summary = tmp_path / "summary.md"
    result = repo.run("check", env={"GITHUB_STEP_SUMMARY": str(summary)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"  {name} / {repo.path.name}:unit  passed" in result.stdout
    assert f"    {name} / {repo.path.name}:unit:a.sh  passed" in result.stdout
    assert not marker.exists()
    assert "$HOME" in summary.read_text()
