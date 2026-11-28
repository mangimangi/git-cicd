"""The Manual form names each job as its row, `<name> / <repo>:<job>`, and
the tool maps the chosen option back to the job (gcd-ee6f)."""

import json

import pytest

from tests.conftest import git_cicd
from tests.test_workflow import form_fields

MANUAL = ".github/workflows/git-cicd-manual.yml"

# The checkout is `repo` (tests/conftest.py), with no origin remote, so its
# repository name is `repo`.
JOBS = {
    "release": {"name": "Release", "on": ["merge"], "branches": ["main"],
                "steps": ["ci/job.sh"],
                "inputs": {"bump_type": {"description": "Bump",
                                         "choices": ["patch", "minor"],
                                         "default": "patch"},
                           "note": {"description": "Shared"}}},
    # no `name`: its row uses the job name in title case
    "update-vendored": {"branches": ["main"], "steps": ["ci/job.sh"],
                        "inputs": {"note": {"description": "Shared"},
                                   "vendor": {"default": "all"}}},
    "test": {"name": "Unit Tests", "on": ["open"], "branches": ["**"],
             "steps": ["ci/job.sh"], "manual": False},
}
RELEASE = "Release / repo:release"
UPDATE = "Update Vendored / repo:update-vendored"


@pytest.fixture
def rows_repo(repo):
    repo.script("ci/job.sh", 'echo "job=$CICD_JOB note=$CICD_INPUT_NOTE"\n')
    repo.config({"jobs": JOBS})
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    repo.commit("base")
    return repo


def decide(repo, job, form=None, env=None):
    head = repo.git("rev-parse", "HEAD")
    run_env = dict(env or {})
    if form is not None:
        run_env["CICD_MANUAL_FORM"] = json.dumps(form)
    result = repo.run("decide", "--trigger=manual", f"--job={job}",
                      "--target=main", "--source=main", f"--base={head}",
                      f"--head={head}", "--json", env=run_env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def needed(data):
    return [j["name"] for j in data["jobs"] if j["needed"]]


def test_the_form_lists_each_manual_job_as_its_row(rows_repo):
    fields = form_fields((rows_repo.path / MANUAL).read_text())
    assert fields["job"]["options"] == [RELEASE, UPDATE]
    # a field of one job names it by its row, a shared field names both
    assert fields["bump_type"]["description"] == f"Bump ({RELEASE})"
    assert fields["note"]["description"] == "Shared"
    assert fields["vendor"]["description"] == f"({UPDATE})"
    # the rows are the report's
    config = git_cicd.load_config(str(rows_repo.path))
    rows = git_cicd.job_rows(config, None, {}, root=str(rows_repo.path))
    assert [r["display"] for r in rows][:2] == [RELEASE, UPDATE]


def test_a_shared_field_names_every_job_using_it(rows_repo):
    jobs = json.loads(json.dumps(JOBS))
    jobs["third"] = {"branches": ["main"], "steps": ["ci/job.sh"]}
    rows_repo.config({"jobs": jobs})
    fields = form_fields(git_cicd.render_workflows(
        git_cicd.load_config(str(rows_repo.path)), "git-cicd")[MANUAL])
    assert fields["note"]["description"] == f"Shared ({RELEASE}, {UPDATE})"


@pytest.mark.parametrize("option,job", [(RELEASE, "release"),
                                        (UPDATE, "update-vendored"),
                                        ("release", "release"),
                                        ("update-vendored", "update-vendored")])
def test_an_option_or_the_bare_job_name_runs_that_job(rows_repo, option, job):
    data = decide(rows_repo, option, form={"job": option, "note": "n"})
    assert data["refused"] is None
    assert data["job"] == job
    assert needed(data) == [job]


def test_mapping_both_ways(rows_repo):
    config = git_cicd.load_config(str(rows_repo.path))
    for name in git_cicd.manual_job_names(config):
        option = git_cicd.manual_option(config, name)
        assert git_cicd.manual_job_key(config, option) == name
        assert git_cicd.manual_job_key(config, name) == name
    assert git_cicd.manual_option(config, "update-vendored") == UPDATE


def test_the_chosen_option_runs_the_job_with_its_inputs(rows_repo, tmp_path):
    out = tmp_path / "out"
    form = {"job": UPDATE, "note": "hello", "vendor": "all",
            "bump_type": "patch"}
    data = decide(rows_repo, UPDATE, form=form,
                  env={"GITHUB_OUTPUT": str(out)})
    outputs = dict(line.split("=", 1)
                   for line in out.read_text().splitlines() if "=" in line)
    assert json.loads(outputs["jobs"]) == ["update-vendored"]
    head = data["head"]
    result = rows_repo.run(
        "run-job", "update-vendored", "--trigger=manual", "--target=main",
        "--source=main", f"--base={head}", f"--head={head}",
        env={"CICD_MANUAL_FORM": json.dumps(form)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "job=update-vendored note=hello" in result.stdout


@pytest.mark.parametrize("value", [
    "Unit Tests / repo:test",          # a job that is not in the form
    "Release / other:release",         # another repository's row
    "Release / repo:update-vendored",  # a name with another job
    "nope",
])
def test_anything_that_matches_no_job_is_refused(rows_repo, value):
    data = decide(rows_repo, value)
    assert data["refused"] == (f"unknown job {value!r} (declared: release, "
                               "update-vendored, test)")
    assert needed(data) == []


def test_the_stated_repository_names_the_rows(rows_repo):
    rows_repo.config({"jobs": JOBS, "repository": "medici"})
    assert rows_repo.run("generate").returncode == 0
    fields = form_fields((rows_repo.path / MANUAL).read_text())
    assert fields["job"]["options"] == ["Release / medici:release",
                                        "Update Vendored / medici:"
                                        "update-vendored"]
    # the same on a machine with another origin remote and in Actions
    rows_repo.git("remote", "add", "origin", "https://example.com/x/y.git")
    assert rows_repo.run("verify").returncode == 0
    assert rows_repo.run("verify", env={
        "GITHUB_REPOSITORY": "someone/elsewhere"}).returncode == 0
    data = decide(rows_repo, "Release / medici:release")
    assert needed(data) == ["release"]
    config = git_cicd.load_config(str(rows_repo.path))
    rows = git_cicd.job_rows(config, None, {}, root=str(rows_repo.path))
    assert rows[0]["display"] == "Release / medici:release"


@pytest.mark.parametrize("value", ["", "a/b", "has space", 3, "${{ x }}"])
def test_a_bad_repository_is_refused(rows_repo, value):
    rows_repo.config({"jobs": JOBS, "repository": value})
    result = rows_repo.run("validate")
    assert result.returncode == 2
    assert "config: repository must be the repository's name on GitHub" \
        in result.stderr


def test_a_derived_name_with_an_expression_is_refused(rows_repo):
    rows_repo.git("remote", "add", "origin",
                  "https://example.com/x/${{ github.token }}.git")
    result = rows_repo.run("validate")
    assert result.returncode == 2
    assert "config: the repository name '${{ github.token }}'" in result.stderr
    assert 'set "repository" in the config' in result.stderr
    # without a manual job the form does not exist, and nothing is refused
    jobs = {"test": JOBS["test"]}
    rows_repo.config({"jobs": jobs})
    assert rows_repo.run("validate").returncode == 0


def test_a_manual_job_name_with_an_expression_is_refused(rows_repo):
    jobs = json.loads(json.dumps(JOBS))
    jobs["release"]["name"] = "Release ${{ github.token }}"
    rows_repo.config({"jobs": jobs})
    result = rows_repo.run("validate")
    assert result.returncode == 2
    assert "job release: the name contains ${{" in result.stderr
    jobs["release"]["manual"] = False
    rows_repo.config({"jobs": jobs})
    assert rows_repo.run("validate").returncode == 0


# ── verify: when the name is the only difference ───────────────────────────

def test_verify_says_when_only_the_repository_name_differs(rows_repo):
    rows_repo.git("remote", "add", "origin",
                  "https://example.com/someone/other.git")
    result = rows_repo.run("verify")
    assert result.returncode == 1
    out = result.stdout
    assert (f"{MANUAL} differs only in the repository's name: its form names "
            "the jobs as in repo, but this checkout's repository is other "
            "(the origin remote's URL). If repo is the repository's name on "
            "GitHub, set \"repository\": \"repo\" in "
            ".vendored/configs/git-cicd.json; otherwise regenerate") in out
    assert "run: .vendored/pkg/git-cicd/git-cicd generate and commit" in out
    # stating the name the file has makes it match again
    rows_repo.config({"jobs": JOBS, "repository": "repo"})
    assert rows_repo.run("verify").returncode == 0


def test_verify_names_where_the_name_came_from(rows_repo):
    result = rows_repo.run("verify",
                           env={"GITHUB_REPOSITORY": "someone/actions"})
    assert result.returncode == 1
    assert ("this checkout's repository is actions (GITHUB_REPOSITORY)"
            in result.stdout)
    rows_repo.config({"jobs": JOBS, "repository": "stated"})
    result = rows_repo.run("verify")
    assert ("this checkout's repository is stated (the config's repository "
            "field)") in result.stdout
    # generated with an origin remote, verified without one
    rows_repo.git("remote", "add", "origin", "https://example.com/x/with.git")
    rows_repo.config({"jobs": JOBS})
    assert rows_repo.run("generate").returncode == 0
    rows_repo.git("remote", "remove", "origin")
    result = rows_repo.run("verify")
    assert ("but this checkout's repository is repo (the checkout's "
            "directory name, as there is no origin remote)") in result.stdout


def test_verify_shows_the_diff_when_more_than_the_name_differs(rows_repo):
    rows_repo.git("remote", "add", "origin", "https://example.com/x/other.git")
    jobs = json.loads(json.dumps(JOBS))
    jobs["release"]["inputs"]["bump_type"]["description"] = "Changed"
    rows_repo.config({"jobs": jobs})
    result = rows_repo.run("verify")
    assert result.returncode == 1
    assert "differs only in the repository's name" not in result.stdout
    assert f"{MANUAL} (committed)" in result.stdout


def test_form_repo_reads_the_committed_options(rows_repo):
    config = git_cicd.load_config(str(rows_repo.path))
    text = (rows_repo.path / MANUAL).read_text()
    assert git_cicd.form_repo(config, text) == "repo"
    assert git_cicd.form_repo(config, None) is None
    assert git_cicd.form_repo(config, (
        '          - "not \\json"\n'           # not a JSON string
        '          - "patch"\n'                # no job's row
        '          - "Release / a b:release"\n'  # no repository name
    )) is None
