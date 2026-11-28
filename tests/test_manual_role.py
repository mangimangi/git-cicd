"""Tests for who may start a manual run (`manual_role`, CICD_ACTOR_ROLE) and
for a job's `environment` in the generated workflows."""

import json

import pytest

from tests.conftest import git_cicd
from tests.test_permissions import (CRON, MANUAL, MERGE, OPEN, job,
                                    job_block, load, refused)

JOBS = {
    "release": {"on": ["merge"], "branches": ["main"],
                "steps": ["ci/a.sh"]},
}


@pytest.fixture
def tool_repo(repo):
    repo.script("ci/a.sh")
    repo.install_tool()
    return repo


def decide(repo, env, config=None, job_name="release"):
    repo.config(config or {"jobs": JOBS})
    sha = repo.commit("base")
    result = repo.run("decide", "--trigger=manual", f"--job={job_name}",
                      "--target=main", "--source=main", f"--base={sha}",
                      f"--head={sha}", "--json", env=env)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    return data, {j["name"]: j for j in data["jobs"]}


NEEDS_ADMIN = ('a manual run needs the admin role ("manual_role" in the '
               'config)')


# ── the role ────────────────────────────────────────────────────────────────

def test_admin_runs(tool_repo):
    data, jobs = decide(tool_repo, {"CICD_ACTOR_ROLE": "admin",
                                    "CICD_ACTOR": "owner"})
    assert data["refused"] is None
    assert jobs["release"]["needed"] is True


def test_write_is_refused_by_default(tool_repo):
    data, jobs = decide(tool_repo, {"CICD_ACTOR_ROLE": "write",
                                    "CICD_ACTOR": "alice"})
    assert data["refused"] == f"alice has the write role; {NEEDS_ADMIN}"
    assert jobs["release"]["needed"] is False
    assert jobs["release"]["reason"] == data["refused"]


def test_write_runs_with_manual_role_write(tool_repo):
    data, jobs = decide(tool_repo, {"CICD_ACTOR_ROLE": "write",
                                    "CICD_ACTOR": "alice"},
                        {"jobs": JOBS, "manual_role": "write"})
    assert data["refused"] is None
    assert jobs["release"]["needed"] is True


def test_read_is_refused_with_manual_role_write(tool_repo):
    data, _ = decide(tool_repo, {"CICD_ACTOR_ROLE": "read",
                                 "CICD_ACTOR": "bob"},
                     {"jobs": JOBS, "manual_role": "write"})
    assert data["refused"] == ("bob has the read role; a manual run needs "
                               'the write role ("manual_role" in the config)')


@pytest.mark.parametrize("role", ["", "  "])
def test_empty_role_is_refused(tool_repo, role):
    data, jobs = decide(tool_repo, {"CICD_ACTOR_ROLE": role,
                                    "CICD_ACTOR": "alice"})
    assert data["refused"] == (f"the role of alice could not be read; "
                               f"{NEEDS_ADMIN}")
    assert jobs["release"]["needed"] is False


@pytest.mark.parametrize("role", ["maintain", "none", "ADMIN"])
def test_unknown_role_is_refused(tool_repo, role):
    data, _ = decide(tool_repo, {"CICD_ACTOR_ROLE": role,
                                 "CICD_ACTOR": "alice"})
    assert data["refused"] == (f"alice has the unknown role {role!r}; "
                               f"{NEEDS_ADMIN}")


def test_in_actions_a_missing_role_is_refused(tool_repo):
    # a stale workflow that passes no role is refused, not let through
    data, _ = decide(tool_repo, {"GITHUB_ACTIONS": "true"})
    assert data["refused"] == ("the role of whoever started the run could "
                               f"not be read; {NEEDS_ADMIN}")


def test_a_laptop_run_is_not_asked_for_a_role(tool_repo):
    data, jobs = decide(tool_repo, {})
    assert data["refused"] is None
    assert jobs["release"]["needed"] is True


def test_the_name_is_data_not_markup(tool_repo):
    data, _ = decide(tool_repo, {"CICD_ACTOR_ROLE": "write",
                                 "CICD_ACTOR": "eve\n$(id)"})
    assert data["refused"] == f"eve$(id) has the write role; {NEEDS_ADMIN}"


def test_the_refusal_fails_the_report(tool_repo, tmp_path):
    data, _ = decide(tool_repo, {"CICD_ACTOR_ROLE": "write",
                                 "CICD_ACTOR": "alice"})
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(data))
    results = tmp_path / "results"
    results.mkdir()
    result = tool_repo.run("report", "--trigger=manual",
                           f"--decisions={path}", f"--results={results}")
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"FAILED - alice has the write role; {NEEDS_ADMIN}" \
        in result.stdout


def test_run_job_refuses_a_lower_role(tool_repo):
    tool_repo.config({"jobs": JOBS})
    sha = tool_repo.commit("base")
    args = ("run-job", "release", "--trigger=manual", "--target=main",
            "--source=main", f"--base={sha}", f"--head={sha}")
    result = tool_repo.run(*args, env={"CICD_ACTOR_ROLE": "write",
                                       "CICD_ACTOR": "alice"})
    assert result.returncode == 2
    assert f"manual run refused: alice has the write role" in result.stderr
    ok = tool_repo.run(*args, env={"CICD_ACTOR_ROLE": "admin",
                                   "CICD_ACTOR": "owner"})
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_scripts_do_not_see_the_role(tool_repo, tmp_path):
    seen = tmp_path / "env"
    tool_repo.script("ci/a.sh", f'env > "{seen}"\n')
    tool_repo.config({"jobs": JOBS})
    sha = tool_repo.commit("base")
    result = tool_repo.run("run-job", "release", "--trigger=manual",
                           "--target=main", "--source=main", f"--base={sha}",
                           f"--head={sha}",
                           env={"CICD_ACTOR_ROLE": "admin",
                                "CICD_ACTOR": "owner"})
    assert result.returncode == 0, result.stdout + result.stderr
    text = seen.read_text()
    assert "CICD_ACTOR_ROLE" not in text and "CICD_ACTOR=" not in text


@pytest.mark.parametrize("value", ["maintain", "", True, ["admin"]])
def test_invalid_manual_role_fails_validation(tool_repo, value):
    tool_repo.config({"jobs": JOBS, "manual_role": value})
    result = tool_repo.run("validate")
    assert result.returncode == 2
    assert "config: manual_role must be \"admin\"" in result.stderr


def test_manual_role_defaults_to_admin(tool_repo):
    config = load(tool_repo, JOBS)
    assert config["manual_role"] == "admin"


# ── the generated Manual workflow passes the role ───────────────────────────

def test_manual_workflow_reads_the_role_with_its_own_token(tool_repo):
    tool_repo.config({"jobs": JOBS})
    assert tool_repo.run("generate").returncode == 0
    text = (tool_repo.path / MANUAL).read_text()
    decide_job = job_block(text, "decide")
    assert "actor_role: ${{ steps.actor.outputs.role }}" in decide_job
    step = decide_job.split("- name: Read the role")[1].split("- name:")[0]
    assert "GH_TOKEN: ${{ github.token }}" in step
    assert "ACTOR: ${{ github.triggering_actor }}" in step
    assert "collaborators/$ACTOR/permission" in step
    assert "${{" not in step.split("run: |")[1]
    decide_step = decide_job.split("- name: Decide")[1]
    assert "CICD_ACTOR_ROLE: ${{ steps.actor.outputs.role }}" in decide_step
    assert "CICD_ACTOR: ${{ github.triggering_actor }}" in decide_step
    run_job = job_block(text, "run")
    assert ("CICD_ACTOR_ROLE: ${{ needs.decide.outputs.actor_role }}"
            in run_job)


# ── environment ─────────────────────────────────────────────────────────────

def generated(repo, jobs):
    repo.config({"jobs": jobs})
    result = repo.run("generate")
    assert result.returncode == 0, result.stdout + result.stderr
    return {p: (repo.path / p).read_text() for p in (OPEN, MERGE, CRON, MANUAL)
            if (repo.path / p).exists()}


def test_environment_is_in_every_workflow_the_job_appears_in(tool_repo):
    files = generated(tool_repo, {
        "deploy": job(on=["open", "merge", "cron"], cron="0 9 * * 1",
                      environment="production")})
    assert set(files) == {OPEN, MERGE, CRON, MANUAL}
    for path, text in files.items():
        block = job_block(text, "run-env-production")
        assert '    environment: "production"\n' in block, path
        assert "fromJSON(needs.decide.outputs.groups)['run-env-production']" \
            in block
        assert "environment:" not in job_block(text, "run"), path
        assert "run, run-env-production]" in text, path


def test_environment_and_permissions_share_one_run_job(tool_repo):
    files = generated(tool_repo, {
        "publish": job(permissions={"packages": "write"},
                       environment="release")})
    block = job_block(files[MERGE], "run-packages-write-env-release")
    assert "      packages: write\n" in block
    assert '    environment: "release"\n' in block


def test_different_environments_do_not_share_a_run_job(tool_repo):
    config = load(tool_repo, {"a": job(environment="staging"),
                              "b": job(environment="production"),
                              "c": job(environment="staging"),
                              "d": job()})
    groups = git_cicd.permission_groups(config, "merge")
    assert {g: v["jobs"] for g, v in groups.items()} == {
        "run-env-staging": ["a", "c"], "run-env-production": ["b"]}
    files = generated(tool_repo, {"a": job(environment="staging"),
                                  "b": job(environment="production")})
    text = files[MERGE]
    assert '"staging"' in job_block(text, "run-env-staging")
    assert '"production"' not in job_block(text, "run-env-staging")
    assert '"production"' in job_block(text, "run-env-production")


def test_a_job_without_environment_is_unchanged(tool_repo):
    plain = generated(tool_repo, {"release": job(), "other": job()})
    with_env = generated(tool_repo, {"release": job(),
                                     "other": job(environment="x")})
    for path in plain:
        assert "environment:" not in job_block(plain[path], "run")
        assert job_block(plain[path], "run") == \
            job_block(with_env[path], "run")
    # no environment anywhere: no group run job at all
    assert "run-env" not in "".join(plain.values())


def test_decide_puts_an_environment_job_in_its_group(tool_repo, tmp_path):
    tool_repo.config({"jobs": {"release": job(environment="production"),
                               "other": job()}})
    sha = tool_repo.commit("base")
    out = tmp_path / "out"
    result = tool_repo.run("decide", "--trigger=merge", "--target=main",
                           "--source=main", f"--base={sha}", f"--head={sha}",
                           env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0, result.stderr
    values = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert json.loads(values["jobs"]) == ["other"]
    assert json.loads(values["groups"]) == {"run-env-production":
                                            ["release"]}


@pytest.mark.parametrize("value", ["has space", "${{ x }}", "a.b", "",
                                   "x" * 256, 3, ["prod"]])
def test_invalid_environment_is_refused(tool_repo, value):
    refused(tool_repo, {"release": job(environment=value)},
            "job release: environment must be the name of a GitHub "
            "environment")
