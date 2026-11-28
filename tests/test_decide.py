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


def test_unknown_trigger_is_refused(repo):
    base = setup_repo(repo)
    result = repo.run("decide", "--trigger", "nightly", "--target", "main",
                      "--source", "feature", "--base", base, "--head", base)
    assert result.returncode == 2
    assert "invalid choice: 'nightly'" in result.stderr


@pytest.mark.parametrize("trigger", ["open", "merge", "cron", "manual"])
def test_no_trigger_is_not_built(repo, trigger):
    base = setup_repo(repo)
    extra = {"cron": ["--cron=0 3 * * *"], "manual": ["--job=test"]}
    result = repo.run("decide", f"--trigger={trigger}", "--target=main",
                      "--source=main", f"--base={base}", f"--head={base}",
                      *extra.get(trigger, []))
    assert "not built" not in result.stdout + result.stderr
    assert result.returncode == 0, result.stderr


# ── merge: a change landed on a branch ──────────────────────────────────────

MERGE_JOBS = {
    "test": {"on": ["open"], "branches": ["**"], "paths": ["src/**"],
             "steps": ["ci/test.sh"]},
    "release": {"on": ["merge"], "branches": ["main"], "steps": ["ci/bump.sh"]},
    "docs": {"on": ["merge", "open"], "branches": ["main", "plan/**"],
             "paths": ["docs/**"], "steps": ["ci/lint.sh"]},
}


def setup_merge(repo):
    """A repo on main with the merge jobs; return the commit before a push."""
    base = setup_repo(repo, jobs=MERGE_JOBS, needs_nothing=["*.md"])
    repo.git("checkout", "-q", "main")
    return base


def decide_merge(repo, before, branch="main"):
    return decide(repo, before, target=branch, source=branch,
                  trigger="merge")


def test_merge_paths_and_open_jobs(repo):
    before = setup_merge(repo)
    repo.write("docs/guide.md", "new\n")
    repo.commit("docs")
    data, jobs = decide_merge(repo, before)
    assert data["trigger"] == "merge"
    assert data["changed_files"] == ["docs/guide.md"]
    assert jobs["test"] == dict(jobs["test"], needed=False,
                                reason="not a merge job")
    assert jobs["release"]["needed"] is True
    assert jobs["release"]["reason"] == ("1 changed file outside needs_nothing "
                                         "(the job has no paths)")
    assert jobs["docs"]["needed"] is True
    assert jobs["docs"]["reason"] == "1 changed file match paths"


def test_merge_no_path_match(repo):
    before = setup_merge(repo)
    repo.write("src/app.py", "x = 3\n")
    repo.commit("src")
    _, jobs = decide_merge(repo, before)
    assert jobs["release"]["needed"] is True
    assert jobs["docs"]["needed"] is False
    assert jobs["docs"]["reason"] == "no changed file matches paths"


def test_merge_branches_bind(repo):
    before = setup_merge(repo)
    repo.write("docs/guide.md", "new\n")
    repo.commit("docs")
    _, jobs = decide_merge(repo, before, branch="plan/x")
    assert jobs["release"]["needed"] is False
    assert jobs["release"]["reason"] == "target plan/x does not match branches"
    assert jobs["docs"]["needed"] is True


def test_merge_only_needs_nothing(repo):
    before = setup_merge(repo)
    repo.write("README.md", "changed\n")
    repo.commit("readme")
    _, jobs = decide_merge(repo, before)
    for name in ("release", "docs"):
        assert jobs[name]["needed"] is False
        assert jobs[name]["reason"] == "only needs_nothing files changed"


def test_merge_job_script_forces(repo):
    before = setup_merge(repo)
    repo.script("ci/test.sh", "echo changed\n")  # an open job's script
    repo.commit("script")
    _, jobs = decide_merge(repo, before)
    assert jobs["release"]["needed"] and jobs["docs"]["needed"]
    assert jobs["docs"]["reason"] == "config or job script changed: ci/test.sh"


@pytest.mark.parametrize("before,why", [
    ("0" * 40, "is the all-zero commit (the push created the branch)"),
    ("1" * 40, "is not a commit in this repository"),
])
def test_merge_without_a_diff_needs_every_matching_job(repo, before, why):
    setup_merge(repo)
    repo.write("README.md", "changed\n")  # needs_nothing only
    repo.commit("readme")
    data, jobs = decide_merge(repo, before)
    assert data["changed_files"] == []
    for name in ("release", "docs"):
        assert jobs[name]["needed"] is True
        assert jobs[name]["reason"] == (
            f"cannot compute the diff: base {before!r} {why}")
    assert jobs["test"]["needed"] is False
    _, jobs = decide_merge(repo, before, branch="other")
    assert not jobs["release"]["needed"] and not jobs["docs"]["needed"]


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
                     'names={"test": "Test", "lint": "Lint", "release": "Release", '
                     '"(nothing)": "Nothing needed"}',
                     'secrets={"test": [], "lint": [], "release": []}',
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
        'jobs=["(nothing)"]',
        'names={"test": "Test", "lint": "Lint", "release": "Release", '
        '"(nothing)": "Nothing needed"}',
        'secrets={"test": [], "lint": [], "release": []}',
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
    assert ('names={"unit-tests": "Unit Tests", "pypi": "PyPI", '
            '"(nothing)": "Nothing needed"}') in \
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


# ── manual: one named job, run by hand ──────────────────────────────────────

MANUAL_JOBS = {
    "test": {"on": ["open"], "branches": ["**"], "paths": ["src/**"],
             "steps": ["ci/test.sh"]},
    "release": {"on": ["merge"], "branches": ["main"], "steps": ["ci/bump.sh"]},
    "lint": {"on": ["open"], "branches": ["**"], "steps": ["ci/lint.sh"],
             "manual": False},
}


def decide_manual(repo, job, branch="main"):
    head = repo.git("rev-parse", "HEAD")
    result = repo.run("decide", "--trigger=manual", f"--job={job}",
                      f"--target={branch}", f"--source={branch}",
                      f"--base={head}", f"--head={head}", "--json")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    return data, {j["name"]: j for j in data["jobs"]}


def test_manual_run_of_a_job(repo):
    setup_repo(repo, jobs=MANUAL_JOBS)
    data, jobs = decide_manual(repo, "release")
    assert data["trigger"] == "manual" and data["job"] == "release"
    assert data["refused"] is None
    assert data["changed_files"] == []
    assert jobs["release"]["needed"] is True
    assert jobs["release"]["reason"] == "manual run"
    for name in ("test", "lint"):
        assert jobs[name]["needed"] is False
        assert jobs[name]["reason"] == "not the job asked for"


def test_manual_ignores_paths_and_triggers(repo):
    """paths and needs_nothing do not apply: a job with paths runs though
    nothing changed, and a job need not list a trigger in on."""
    setup_repo(repo, jobs=MANUAL_JOBS)
    _, jobs = decide_manual(repo, "test", branch="feature")
    assert jobs["test"]["needed"] is True
    assert jobs["test"]["reason"] == "manual run"


@pytest.mark.parametrize("job,branch,reason", [
    ("nope", "main", "unknown job 'nope' (declared: test, release, lint)"),
    ("lint", "main", 'job lint cannot be run by hand ("manual": false)'),
    ("release", "feature",
     "branch feature does not match the branches of job release (main)"),
])
def test_manual_refusals_are_recorded(repo, job, branch, reason):
    setup_repo(repo, jobs=MANUAL_JOBS)
    data, jobs = decide_manual(repo, job, branch=branch)
    assert data["refused"] == reason
    assert not any(j["needed"] for j in data["jobs"])
    if job in jobs:
        assert jobs[job]["reason"] == reason


def test_manual_refusal_outputs_need_no_job(repo, tmp_path):
    setup_repo(repo, jobs=MANUAL_JOBS)
    head = repo.git("rev-parse", "HEAD")
    out = tmp_path / "out"
    result = repo.run("decide", "--trigger=manual", "--job=lint",
                      "--target=main", "--source=main", f"--base={head}",
                      f"--head={head}", env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0
    assert "refused: job lint cannot be run by hand" in result.stdout
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert outputs["jobs"] == '["(nothing)"]' and outputs["any"] == "false"


def test_manual_needs_job(repo):
    base = setup_repo(repo, jobs=MANUAL_JOBS)
    result = repo.run("decide", "--trigger=manual", "--target=main",
                      "--source=main", f"--base={base}", f"--head={base}")
    assert result.returncode == 2
    assert "--trigger manual needs --job NAME" in result.stderr


@pytest.mark.parametrize("trigger", ["open", "merge", "cron"])
def test_job_refused_for_other_triggers(repo, trigger):
    base = setup_repo(repo, jobs=MANUAL_JOBS)
    result = repo.run("decide", f"--trigger={trigger}", "--job=test",
                      "--target=main", "--source=main", f"--base={base}",
                      f"--head={base}")
    assert result.returncode == 2
    assert (f"--job is for --trigger manual only, not --trigger {trigger}"
            in result.stderr)


# ── manual: declared inputs ─────────────────────────────────────────────────

INPUT_JOBS = {
    "release": {"branches": ["main"], "steps": ["ci/bump.sh"],
                "inputs": {
                    "bump_type": {"choices": ["patch", "minor", "major"],
                                  "default": "patch"},
                    "note": {"required": True}}},
    "update": {"branches": ["main"], "steps": ["ci/bump.sh"],
               "inputs": {"vendor": {"default": "all"},
                          "private": {"choices": ["false", "true"]},
                          "free": {}}},
    "hidden": {"branches": ["main"], "steps": ["ci/bump.sh"],
               "manual": False, "inputs": {"secret": {"default": "s"}}},
}


def decide_inputs(repo, form, job="release"):
    head = repo.git("rev-parse", "HEAD")
    env = {} if form is None else {"CICD_MANUAL_FORM": form}
    result = repo.run("decide", "--trigger=manual", f"--job={job}",
                      "--target=main", "--source=main", f"--base={head}",
                      f"--head={head}", "--json", env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_manual_inputs_accepted(repo):
    setup_repo(repo, jobs=INPUT_JOBS)
    data = decide_inputs(repo, json.dumps({
        "job": "release", "bump_type": "minor", "note": "x",
        "vendor": "all", "private": "false", "free": ""}))
    assert data["refused"] is None
    assert data["ignored"] == []
    assert data["jobs"][0]["needed"] is True


def test_manual_fields_of_other_jobs_are_ignored_and_noted(repo):
    setup_repo(repo, jobs=INPUT_JOBS)
    data = decide_inputs(repo, json.dumps({
        "job": "release", "bump_type": "major", "note": "x",
        "vendor": "mangimangi/git-semver", "private": "true", "free": "",
        "unknown": "u", "blank": ""}))
    assert data["refused"] is None
    assert data["ignored"] == [
        "ignored input vendor (job release does not declare it)",
        "ignored input private (job release does not declare it)",
        "ignored input unknown (job release does not declare it)"]
    assert data["jobs"][0]["needed"] is True
    head = repo.git("rev-parse", "HEAD")
    text = repo.run("decide", "--trigger=manual", "--job=release",
                    "--target=main", "--source=main", f"--base={head}",
                    f"--head={head}", env={"CICD_MANUAL_FORM": json.dumps(
                        {"note": "x", "vendor": "v"})}).stdout
    assert "  ignored input vendor (job release does not declare it)\n" in text


def test_manual_without_the_form_takes_the_defaults(repo):
    setup_repo(repo, jobs=INPUT_JOBS)
    data = decide_inputs(repo, None, job="update")
    assert data["refused"] is None and data["ignored"] == []
    data = decide_inputs(repo, None)
    assert data["refused"] == "job release: input note is required"


@pytest.mark.parametrize("form,reason", [
    ("", "job release: input note is required"),
    ('{"note": ""}', "job release: input note is required"),
    ('{"note": "x", "bump_type": "huge"}',
     "job release: input bump_type: 'huge' is not one of the choices "
     "(patch, minor, major)"),
    ("not json", "the manual run's form values are not valid JSON"),
    ('["x"]', "the manual run's form values must be a JSON object of "
              "string values"),
    ('{"note": ["x"]}', "the manual run's form values must be a JSON object "
                        "of string values"),
])
def test_manual_input_failures_are_refusals(repo, form, reason):
    setup_repo(repo, jobs=INPUT_JOBS)
    data = decide_inputs(repo, form)
    assert data["refused"].startswith(reason), data["refused"]
    assert not data["jobs"][0]["needed"]


# ── cron: a schedule fired ──────────────────────────────────────────────────

CRON_JOBS = {
    "test": {"on": ["open"], "branches": ["**"], "steps": ["ci/test.sh"]},
    "nightly": {"on": ["cron"], "branches": ["main", "dev"],
                "cron": "0 3 * * *", "paths": ["src/**"],
                "steps": ["ci/lint.sh"]},
    "weekly": {"on": ["cron", "open"], "branches": ["main"],
               "cron": "0 9 * * 1", "steps": ["ci/bump.sh"]},
    "again": {"on": ["cron"], "branches": ["dev"], "cron": "0 3 * * *",
              "steps": ["ci/test.sh"]},
}


def setup_cron(repo, branches=("main", "dev")):
    """Remote-tracking heads for the cron branches, as after a full
    checkout. Return {branch: sha}."""
    setup_repo(repo, jobs=CRON_JOBS)
    heads = {}
    for branch in branches:
        repo.write(f"{branch}.txt", branch)
        heads[branch] = repo.commit(f"on {branch}")
        repo.git("update-ref", f"refs/remotes/origin/{branch}", heads[branch])
    return heads


def decide_cron(repo, expr, env=None):
    result = repo.run("decide", "--trigger=cron", f"--cron={expr}", "--json",
                      env=env)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    return data, {j["name"]: j for j in data["jobs"]}


def test_cron_needs_the_jobs_of_the_fired_expression_on_each_branch(repo):
    heads = setup_cron(repo)
    data, jobs = decide_cron(repo, "0 3 * * *")
    assert data["trigger"] == "cron" and data["cron"] == "0 3 * * *"
    assert data["changed_files"] == []
    assert jobs["nightly"] == dict(jobs["nightly"], needed=True,
                                   reason="scheduled 0 3 * * *")
    assert jobs["again"]["needed"] is True
    assert jobs["weekly"]["needed"] is False
    assert jobs["weekly"]["reason"] == "scheduled at 0 9 * * 1"
    assert jobs["test"]["reason"] == "not a cron job"
    assert data["runs"] == [
        {"key": "nightly-1", "job": "nightly", "branch": "main",
         "sha": heads["main"]},
        {"key": "nightly-2", "job": "nightly", "branch": "dev",
         "sha": heads["dev"]},
        {"key": "again-1", "job": "again", "branch": "dev",
         "sha": heads["dev"]},
    ]
    assert data["heads"] == {"main": heads["main"], "dev": heads["dev"]}
    assert data["missing"] == []


def test_cron_other_expression(repo):
    heads = setup_cron(repo)
    data, jobs = decide_cron(repo, "0 9 * * 1")
    assert [r["job"] for r in data["runs"]] == ["weekly"]
    assert data["heads"] == {"main": heads["main"]}
    assert jobs["nightly"]["reason"] == "scheduled at 0 3 * * *"


def test_cron_missing_branch_is_recorded(repo):
    heads = setup_cron(repo, branches=("main",))
    data, _ = decide_cron(repo, "0 3 * * *")
    assert data["heads"] == {"main": heads["main"], "dev": None}
    assert [(r["job"], r["branch"]) for r in data["runs"]] == [
        ("nightly", "main")]
    assert data["missing"] == [
        {"job": "nightly", "branch": "dev",
         "reason": "branch dev does not exist"},
        {"job": "again", "branch": "dev",
         "reason": "branch dev does not exist"}]


def test_cron_outputs(repo, tmp_path):
    setup_cron(repo)
    out = tmp_path / "out"
    data, _ = decide_cron(repo, "0 3 * * *", env={"GITHUB_OUTPUT": str(out)})
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert json.loads(outputs["runs"]) == data["runs"]
    assert outputs["any"] == "true"
    assert json.loads(outputs["names"])["nightly"] == "Nightly"
    # the other triggers' outputs carry no runs
    base = repo.git("rev-parse", "HEAD")
    out.write_text("")
    repo.run("decide", "--trigger=open", "--target=main", "--source=f",
             f"--base={base}", f"--head={base}", env={"GITHUB_OUTPUT": str(out)})
    assert "runs=" not in out.read_text()


def test_cron_outputs_nothing_to_run_is_the_placeholder(repo, tmp_path):
    """A schedule with no run gives the matrix the one placeholder entry, so
    the workflow's `run` job is never skipped (a skipped matrix job shows its
    `name:` expression unexpanded)."""
    setup_cron(repo)
    out = tmp_path / "out"
    data, _ = decide_cron(repo, "0 4 * * *", env={"GITHUB_OUTPUT": str(out)})
    assert data["runs"] == []
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert outputs["any"] == "false"
    assert json.loads(outputs["runs"]) == [
        {"job": "(nothing)", "branch": "", "sha": "", "key": "(nothing)"}]
    assert json.loads(outputs["names"])["(nothing)"] == "Nothing needed"


def test_placeholder_is_no_valid_job_name():
    assert not git_cicd.JOB_NAME_RE.match(git_cicd.NOTHING_JOB)


def test_cron_needs_cron(repo):
    setup_cron(repo)
    result = repo.run("decide", "--trigger=cron")
    assert result.returncode == 2
    assert "--trigger cron needs --cron EXPR" in result.stderr
    result = repo.run("decide", "--trigger=open", "--cron=0 3 * * *",
                      "--target=main", "--source=f", "--base=HEAD",
                      "--head=HEAD")
    assert result.returncode == 2
    assert "--cron is for --trigger cron only" in result.stderr
    result = repo.run("decide", "--trigger=open", "--target=main")
    assert result.returncode == 2
    assert "--trigger open needs --source, --base, --head" in result.stderr


def test_unknown_trigger_is_refused_by_the_module_api(repo):
    setup_repo(repo)
    config = git_cicd.load_config(str(repo.path))
    message = "unknown trigger 'push' (allowed: open, merge, cron, manual)"
    with pytest.raises(git_cicd.UsageError, match=r"unknown trigger 'push'") \
            as e:
        git_cicd.decide(config, str(repo.path), "push", "main", "f", "HEAD",
                        "HEAD")
    assert str(e.value) == message
    with pytest.raises(git_cicd.UsageError) as e:
        git_cicd.run_job(config, str(repo.path), "test", {"trigger": "push"})
    assert str(e.value) == message


def test_empty_base_is_not_a_commit(repo):
    setup_repo(repo)
    result = repo.run("decide", "--trigger=open", "--target=main",
                      "--source=feature", "--base=", "--head=HEAD", "--json")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    jobs = {j["name"]: j for j in data["jobs"]}
    assert "base '' is not a commit in this repository" \
        in jobs["test"]["reason"]


def test_unrelated_histories_report_the_diff_failure(repo):
    setup_repo(repo)
    repo.git("checkout", "-q", "--orphan", "other")
    repo.write("src/other.py", "y\n")
    other = repo.commit("unrelated")
    base = repo.git("rev-parse", "main")
    result = repo.run("decide", "--trigger=open", "--target=main",
                      "--source=other", f"--base={base}", f"--head={other}",
                      "--json")
    assert result.returncode == 0, result.stderr
    jobs = {j["name"]: j for j in json.loads(result.stdout)["jobs"]}
    assert "git diff failed: fatal:" in jobs["test"]["reason"]
    assert jobs["test"]["needed"] is True


def test_cron_text_lists_each_branch_and_run(repo):
    heads = setup_cron(repo, branches=("main",))
    result = repo.run("decide", "--trigger=cron", "--cron=0 3 * * *")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "git-cicd decide: trigger cron, schedule 0 3 * * *"
    assert f"  branch main: {heads['main']}" in lines
    assert "  branch dev: does not exist" in lines
    assert f"  run nightly on main at {heads['main']}" in lines
