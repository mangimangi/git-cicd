"""Tests for deciding which jobs a change needs on the open trigger."""

import json

import pytest

from tests.conftest import git_cicd


def setup_repo(repo, jobs=None, needs_nothing=None, **top):
    """A repo on main with job scripts and a config; a feature branch checked
    out. Return the base sha."""
    repo.script("ci/setup.sh")
    repo.script("ci/test.sh")
    repo.script("ci/lint.sh")
    repo.script("ci/bump.sh")
    repo.write("src/app.py", "x = 1\n")
    repo.write("docs/guide.md", "guide\n")
    repo.write("README.md", "readme\n")
    if jobs is None:
        jobs = {
            "test": {"on": ["open"], "branches": ["**"],
                     "paths": ["src/**", "tests/**"], "setup": "ci/setup.sh",
                     "steps": ["ci/test.sh"]},
            "lint": {"on": ["open"], "branches": ["main"],
                     "paths": ["src/*.py"], "steps": ["ci/lint.sh"]},
            "release": {"on": ["merge"], "branches": ["main"],
                        "steps": ["ci/bump.sh"]},
        }
    config = {"jobs": jobs,
              "needs_nothing": needs_nothing if needs_nothing is not None
              else ["docs/**", "*.md"]}
    config.update(top)
    repo.config(config)
    base = repo.commit("base")
    repo.git("checkout", "-q", "-b", "feature")
    return base


def decide(repo, base, head=None, target="main", source="feature",
           trigger="open"):
    head = head or repo.git("rev-parse", "HEAD")
    result = repo.run("decide", f"--trigger={trigger}", f"--target={target}",
                      f"--source={source}", f"--base={base}",
                      f"--head={head}", "--json")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    return data, {j["name"]: j for j in data["jobs"]}


def test_paths_match_needed(repo):
    base = setup_repo(repo)
    repo.write("src/app.py", "x = 2\n")
    repo.commit("change src")
    data, jobs = decide(repo, base)
    assert data["changed_files"] == ["src/app.py"]
    assert jobs["test"]["needed"] is True
    assert jobs["test"]["reason"] == "1 changed file match paths"
    assert jobs["lint"]["needed"] is True


def test_only_matching_job_needed(repo):
    base = setup_repo(repo)
    repo.write("src/deep/mod.py", "y\n")
    repo.commit("deep")
    _, jobs = decide(repo, base)
    assert jobs["test"]["needed"] is True
    # src/*.py does not cross '/'
    assert jobs["lint"]["needed"] is False
    assert jobs["lint"]["reason"] == "no changed file matches paths"


def test_target_not_matching_branches(repo):
    base = setup_repo(repo)
    repo.write("src/app.py", "x = 2\n")
    repo.commit("change")
    _, jobs = decide(repo, base, target="plan/x")
    assert jobs["test"]["needed"] is True
    assert jobs["lint"]["needed"] is False
    assert jobs["lint"]["reason"] == "target plan/x does not match branches"


def test_target_matches_no_job(repo):
    base = setup_repo(repo, jobs={
        "a": {"on": ["open"], "branches": ["main"], "steps": ["ci/test.sh"]},
        "b": {"on": ["open"], "branches": ["release/*"],
              "steps": ["ci/lint.sh"]},
    })
    repo.write(".vendored/configs/git-cicd.json",
               (repo.path / ".vendored/configs/git-cicd.json").read_text()
               + "\n")
    repo.commit("config change forces, but branches still bind")
    _, jobs = decide(repo, base, target="plan/x")
    for name in ("a", "b"):
        assert jobs[name]["needed"] is False
        assert "does not match branches" in jobs[name]["reason"]


def test_config_changed_forces_all(repo):
    base = setup_repo(repo)
    cfg = repo.path / ".vendored/configs/git-cicd.json"
    cfg.write_text(cfg.read_text() + "\n")
    repo.commit("touch config")
    _, jobs = decide(repo, base)
    for name in ("test", "lint"):
        assert jobs[name]["needed"] is True
        assert jobs[name]["reason"] == (
            "config or job script changed: .vendored/configs/git-cicd.json")
    assert jobs["release"]["needed"] is False


def test_job_script_changed_forces_all(repo):
    base = setup_repo(repo)
    repo.script("ci/bump.sh", "echo changed\n")  # named by a merge job only
    repo.commit("touch script")
    _, jobs = decide(repo, base)
    assert jobs["test"]["needed"] and jobs["lint"]["needed"]
    assert jobs["test"]["reason"] == "config or job script changed: ci/bump.sh"


def test_setup_script_changed_forces_all(repo):
    base = setup_repo(repo)
    repo.script("ci/setup.sh", "echo changed\n")
    repo.commit("touch setup")
    _, jobs = decide(repo, base)
    assert jobs["lint"]["needed"]
    assert "ci/setup.sh" in jobs["lint"]["reason"]


def test_script_in_needs_nothing_still_forces(repo):
    base = setup_repo(repo, needs_nothing=["ci/**"])
    repo.script("ci/test.sh", "echo changed\n")
    repo.commit("touch")
    _, jobs = decide(repo, base)
    assert jobs["test"]["needed"] and jobs["lint"]["needed"]


def test_file_in_no_paths_forces_all(repo):
    base = setup_repo(repo)
    repo.write("Makefile", "all:\n")
    repo.commit("makefile")
    _, jobs = decide(repo, base)
    for name in ("test", "lint"):
        assert jobs[name]["needed"] is True
        assert jobs[name]["reason"] == (
            "Makefile is in no job's paths and not in needs_nothing")


def test_several_files_in_no_paths(repo):
    base = setup_repo(repo)
    for i in range(7):
        repo.write(f"misc/{i}.txt", "x")
    repo.commit("misc")
    _, jobs = decide(repo, base)
    reason = jobs["test"]["reason"]
    assert reason.endswith("are in no job's paths and not in needs_nothing")
    assert "misc/0.txt" in reason and "(and 2 more)" in reason


def test_only_needs_nothing_files(repo):
    base = setup_repo(repo)
    repo.write("docs/guide.md", "new\n")
    repo.write("README.md", "new\n")
    repo.commit("docs")
    _, jobs = decide(repo, base)
    for name in ("test", "lint"):
        assert jobs[name]["needed"] is False
        assert jobs[name]["reason"] == "only needs_nothing files changed"


def test_needs_nothing_file_does_not_make_job_needed(repo):
    base = setup_repo(repo, jobs={
        "docs": {"on": ["open"], "branches": ["**"], "paths": ["docs/**"],
                 "steps": ["ci/test.sh"]},
        "test": {"on": ["open"], "branches": ["**"], "paths": ["src/**"],
                 "steps": ["ci/lint.sh"]},
    })
    repo.write("docs/guide.md", "new\n")
    repo.write("src/app.py", "x = 3\n")
    repo.commit("both")
    _, jobs = decide(repo, base)
    assert jobs["docs"]["needed"] is False
    assert jobs["test"]["needed"] is True


def test_bad_base_forces_all(repo):
    setup_repo(repo)
    repo.write("docs/guide.md", "new\n")
    repo.commit("docs only")
    _, jobs = decide(repo, "0" * 40)
    for name in ("test", "lint"):
        assert jobs[name]["needed"] is True
        assert jobs[name]["reason"].startswith("cannot compute the diff: base")


def test_bad_head_forces_all(repo):
    base = setup_repo(repo)
    _, jobs = decide(repo, base, head="nope")
    assert jobs["test"]["reason"].startswith("cannot compute the diff: head")


def test_option_like_base_is_not_an_option(repo):
    setup_repo(repo)
    _, jobs = decide(repo, "--output=/tmp/x")
    assert jobs["test"]["needed"]
    assert "cannot compute the diff" in jobs["test"]["reason"]


def test_empty_diff_forces_all(repo):
    base = setup_repo(repo)
    _, jobs = decide(repo, base)  # head == base
    for name in ("test", "lint"):
        assert jobs[name]["needed"] is True
        assert jobs[name]["reason"] == "no changed files found"


def test_three_dot_diff_ignores_target_progress(repo):
    base = setup_repo(repo)
    repo.write("docs/guide.md", "feature docs\n")
    head = repo.commit("feature docs")
    repo.git("checkout", "-q", "main")
    repo.write("src/app.py", "main moved\n")
    main_tip = repo.commit("main moved")
    _, jobs = decide(repo, main_tip, head=head)
    assert jobs["test"]["needed"] is False


def test_rename_counts_both_paths(repo):
    base = setup_repo(repo)
    repo.git("mv", "src/app.py", "docs/app.py")
    repo.commit("move")
    data, jobs = decide(repo, base)
    assert sorted(data["changed_files"]) == ["docs/app.py", "src/app.py"]
    assert jobs["test"]["needed"]


def test_job_without_paths(repo):
    base = setup_repo(repo, jobs={
        "all": {"on": ["open"], "branches": ["**"], "steps": ["ci/test.sh"]},
        "src": {"on": ["open"], "branches": ["**"], "paths": ["src/**"],
                "steps": ["ci/lint.sh"]},
    })
    repo.write("src/app.py", "x = 9\n")
    repo.commit("src")
    _, jobs = decide(repo, base)
    assert jobs["all"]["needed"] is True
    assert "outside needs_nothing" in jobs["all"]["reason"]
    assert jobs["src"]["needed"] is True


def test_job_without_paths_not_needed_for_needs_nothing(repo):
    base = setup_repo(repo, jobs={
        "all": {"on": ["open"], "branches": ["**"], "steps": ["ci/test.sh"]},
    })
    repo.write("README.md", "x\n")
    repo.commit("readme")
    _, jobs = decide(repo, base)
    assert jobs["all"]["needed"] is False
    assert jobs["all"]["reason"] == "only needs_nothing files changed"


def test_job_without_paths_does_not_cover_files(repo):
    base = setup_repo(repo, jobs={
        "all": {"on": ["open"], "branches": ["**"], "steps": ["ci/test.sh"]},
        "src": {"on": ["open"], "branches": ["**"], "paths": ["src/**"],
                "steps": ["ci/lint.sh"]},
    })
    repo.write("other/file.txt", "x\n")
    repo.commit("other")
    _, jobs = decide(repo, base)
    assert jobs["src"]["needed"] is True
    assert "other/file.txt is in no job's paths" in jobs["src"]["reason"]


def test_not_open_jobs_reported(repo):
    base = setup_repo(repo)
    repo.write("src/app.py", "x = 2\n")
    repo.commit("src")
    data, jobs = decide(repo, base)
    assert [j["name"] for j in data["jobs"]] == ["test", "lint", "release"]
    assert jobs["release"]["needed"] is False
    assert jobs["release"]["reason"] == "not an open job"


@pytest.mark.parametrize("trigger", ["merge", "cron", "manual"])
def test_unbuilt_triggers_exit_2(repo, trigger):
    base = setup_repo(repo)
    result = repo.run("decide", "--trigger", trigger, "--target", "main",
                      "--source", "feature", "--base", base, "--head", base)
    assert result.returncode == 2
    assert (f"the {trigger} trigger is not built yet (git-cicd gcd-e74c builds "
            "open only)") in result.stderr
    assert result.stdout == ""


def test_unbuilt_trigger_lists_declaring_jobs(repo):
    base = setup_repo(repo)
    result = repo.run("decide", "--trigger", "merge", "--target", "main",
                      "--source", "feature", "--base", base, "--head", base)
    assert "jobs declaring it: release" in result.stderr


@pytest.mark.parametrize("paths,changed,needed", [
    (["src/*.py"], "src/a.py", True),
    (["src/*.py"], "src/x/a.py", False),
    (["src/**"], "src/x/y/a.py", True),
    (["src/v?.txt"], "src/v1.txt", True),
    (["src/v?.txt"], "src/v10.txt", False),
])
def test_patterns_in_paths(repo, paths, changed, needed):
    base = setup_repo(repo, jobs={
        "j": {"on": ["open"], "branches": ["**"], "paths": paths,
              "steps": ["ci/test.sh"]},
        "k": {"on": ["open"], "branches": ["**"], "paths": ["src/**"],
              "steps": ["ci/lint.sh"]},
    })
    repo.write(changed, "x\n")
    repo.commit("c")
    _, jobs = decide(repo, base)
    assert jobs["j"]["needed"] is needed


def test_github_output_written(repo, tmp_path):
    base = setup_repo(repo, max_parallel=2)
    repo.write("src/deep/a.py", "x\n")
    head = repo.commit("deep")
    out = tmp_path / "github_output"
    out.write_text("previous=1\n")
    result = repo.run("decide", "--trigger", "open", "--target", "main",
                      "--source", "feature", "--base", base, "--head", head,
                      env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0, result.stderr
    lines = out.read_text().splitlines()
    assert lines == ["previous=1", 'jobs=["test"]',
                     'names={"test": "Test", "lint": "Lint", "release": "Release"}',
                     "any=true", "max_parallel=2"]


def test_github_output_none_needed(repo, tmp_path):
    base = setup_repo(repo)
    repo.write("README.md", "x\n")
    head = repo.commit("readme")
    out = tmp_path / "github_output"
    result = repo.run("decide", "--trigger", "open", "--target", "main",
                      "--source", "feature", "--base", base, "--head", head,
                      env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0
    assert out.read_text().splitlines() == [
        "jobs=[]", 'names={"test": "Test", "lint": "Lint", "release": "Release"}',
        "any=false", "max_parallel=3"]


def test_github_output_names_title_case_default_and_written(repo, tmp_path):
    """The row names the workflow reads: the job name in title case without
    `name`, a written `name` exactly as written."""
    repo.script("ci/t.sh")
    repo.config({"jobs": {
        "unit-tests": {"on": ["open"], "branches": ["**"],
                       "steps": ["ci/t.sh"]},
        "pypi": {"name": "PyPI", "on": ["open"], "branches": ["**"],
                 "steps": ["ci/t.sh"]}}})
    base = repo.commit("base")
    repo.write("x", "1\n")
    head = repo.commit("x")
    out = tmp_path / "github_output"
    result = repo.run("decide", "--trigger", "open", "--target", "main",
                      "--source", "feature", "--base", base, "--head", head,
                      env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0, result.stderr
    assert 'names={"unit-tests": "Unit Tests", "pypi": "PyPI"}' in \
        out.read_text().splitlines()


def test_changed_files_out_and_human_output(repo, tmp_path):
    base = setup_repo(repo)
    repo.write("src/app.py", "x = 2\n")
    repo.write("README.md", "x\n")
    head = repo.commit("two")
    out = tmp_path / "changed.txt"
    result = repo.run("decide", "--trigger", "open", "--target", "main",
                      "--source", "feature", "--base", base, "--head", head,
                      "--changed-files-out", str(out))
    assert result.returncode == 0
    assert out.read_text() == "README.md\nsrc/app.py\n"
    assert "test: needed (1 changed file match paths)" in result.stdout
    assert "release: not needed (not an open job)" in result.stdout
    assert "2 changed files" in result.stdout


def test_json_shape(repo):
    base = setup_repo(repo)
    data, _ = decide(repo, base)
    assert set(data) == {"trigger", "target", "source", "base", "head",
                         "changed_files", "jobs", "max_parallel"}
    assert set(data["jobs"][0]) == {"name", "title", "needed", "reason",
                                    "blocking"}
    assert data["jobs"][0]["title"] == \
        git_cicd.default_title(data["jobs"][0]["name"])


def test_invalid_config_refused(repo):
    base = setup_repo(repo)
    repo.config({"jobs": {"x": {"steps": ["ci/test.sh"]}}})
    result = repo.run("decide", "--trigger", "open", "--target", "main",
                      "--source", "f", "--base", base, "--head", base)
    assert result.returncode == 2
    assert "job x: missing required field branches" in result.stderr


def test_decide_function_with_given_files(repo):
    setup_repo(repo)
    config = git_cicd.load_config(str(repo.path))
    d = git_cicd.decide(config, str(repo.path), "open", "main", "f", "b", "h",
                        files=["src/sub/x.py"])
    assert git_cicd.needed_jobs(d) == ["test"]
