"""Tests for a job's `permissions`: validation, the run job of each
permission group in the generated workflows, decide's outputs, verify."""

import json
import re

import pytest

from tests.conftest import git_cicd
from tests.test_workflow import TOOL, bare

MERGE = ".github/workflows/git-cicd-merge.yml"
CRON = ".github/workflows/git-cicd-cron.yml"
MANUAL = ".github/workflows/git-cicd-manual.yml"
OPEN = ".github/workflows/git-cicd-open.yml"


@pytest.fixture
def tool_repo(repo):
    repo.script("ci/a.sh")
    repo.install_tool()
    return repo


def job(**fields):
    base = {"on": ["merge"], "branches": ["main"], "steps": ["ci/a.sh"]}
    base.update(fields)
    return base


def refused(repo, jobs, *expected):
    repo.config({"jobs": jobs})
    result = repo.run("validate")
    assert result.returncode == 2, result.stdout + result.stderr
    for text in expected:
        assert text in result.stderr, result.stderr


def load(repo, jobs):
    repo.config({"jobs": jobs})
    return git_cicd.load_config(str(repo.path))


def job_block(text, job_id):
    """The lines of one job of a workflow (from `  <id>:` to the next)."""
    m = re.search(rf"(?ms)^  {re.escape(job_id)}:\n(.*?)(?=^  \S|\Z)", text)
    assert m, job_id
    return m.group(1)


def permissions_of(block):
    m = re.search(r"(?m)^    permissions:\n((?:      .*\n)+)", block)
    if not m:
        return None
    return dict(line.strip().split(": ", 1)
                for line in m.group(1).splitlines())


# ── validate ────────────────────────────────────────────────────────────────

def test_permissions_accepted_and_normalized(tool_repo):
    config = load(tool_repo, {"r": job(permissions={
        "packages": "write", "issues": "read"})})
    # in the documented scope order
    assert list(config["jobs"]["r"]["permissions"].items()) == [
        ("issues", "read"), ("packages", "write")]


def test_permissions_default_empty(tool_repo):
    assert load(tool_repo, {"r": job()})["jobs"]["r"]["permissions"] == {}


def test_unknown_scope_refused(tool_repo):
    refused(tool_repo, {"r": job(permissions={"deployments": "write"})},
            "job r: unknown permission 'deployments' in permissions "
            "(allowed: contents, pull-requests, issues, packages)")


def test_unknown_level_refused(tool_repo):
    refused(tool_repo, {"r": job(permissions={"packages": "admin"})},
            "job r: permission packages: level 'admin' is not allowed "
            "(read or write)")


@pytest.mark.parametrize("value", [["packages"], "packages: write", None])
def test_non_object_refused(tool_repo, value):
    refused(tool_repo, {"r": job(permissions=value)},
            "job r: permissions must be an object (scope -> read or write; "
            "scopes: contents, pull-requests, issues, packages)")


def test_non_string_level_refused(tool_repo):
    refused(tool_repo, {"r": job(permissions={"packages": True})},
            "job r: permission packages: the level must be a string (read "
            "or write)")


def test_write_on_open_refused(tool_repo):
    refused(tool_repo, {"pr": job(on=["open", "merge"],
                                  permissions={"contents": "write"})},
            "job pr: permission contents: write is not allowed on a job "
            "with open in on (open runs a pull request's own code; a job "
            "that must write on open declares the CICD_WRITE_TOKEN secret)")


def test_read_on_open_accepted(tool_repo):
    config = load(tool_repo, {"pr": job(on=["open"],
                                        permissions={"packages": "read"})})
    assert config["jobs"]["pr"]["permissions"] == {"packages": "read"}


# ── effective permissions and groups ────────────────────────────────────────

def test_effective_permissions_higher_level_wins(tool_repo):
    config = load(tool_repo, {"r": job(permissions={
        "contents": "read", "packages": "write"})})
    r = config["jobs"]["r"]
    assert git_cicd.effective_permissions(r, "merge") == {
        "contents": "write", "pull-requests": "write", "packages": "write"}


def test_declaration_adding_nothing_stays_in_run(tool_repo):
    config = load(tool_repo, {"r": job(permissions={"contents": "read"})})
    assert git_cicd.permission_groups(config, "merge") == {}


def test_same_effective_set_shares_one_group(tool_repo):
    config = load(tool_repo, {
        "a": job(permissions={"packages": "write"}),
        "plain": job(),
        "b": job(permissions={"packages": "write", "contents": "read"}),
        "c": job(permissions={"issues": "write"}),
    })
    groups = git_cicd.permission_groups(config, "merge")
    assert list(groups) == ["run-packages-write", "run-issues-write"]
    assert groups["run-packages-write"]["jobs"] == ["a", "b"]
    assert groups["run-issues-write"]["jobs"] == ["c"]


def test_groups_only_hold_jobs_of_the_trigger(tool_repo):
    config = load(tool_repo, {
        "m": job(permissions={"packages": "write"}, manual=False),
        "o": job(on=["open"], permissions={"packages": "read"}),
    })
    assert list(git_cicd.permission_groups(config, "merge")) == [
        "run-packages-write"]
    assert git_cicd.permission_groups(config, "manual") == {
        "run-packages-read": {"permissions": {
            "contents": "write", "pull-requests": "write",
            "packages": "read"}, "environment": None, "jobs": ["o"]}}
    assert git_cicd.permission_groups(config, "open") == {
        "run-packages-read": {"permissions": {
            "contents": "read", "packages": "read"}, "environment": None,
            "jobs": ["o"]}}
    assert git_cicd.permission_groups(config, "cron") == {}


# ── generate ────────────────────────────────────────────────────────────────

SIBLINGS = {
    "publish": job(on=["merge", "cron"], cron="0 3 * * *",
                   permissions={"packages": "write"}),
    "release": job(on=["merge", "cron"], cron="0 3 * * *"),
}


def generated(repo, jobs):
    repo.config({"jobs": jobs})
    result = repo.run("generate")
    assert result.returncode == 0, result.stderr
    return {p: (repo.path / p).read_text() for p in (OPEN, MERGE, CRON,
                                                     MANUAL)
            if (repo.path / p).exists()}


@pytest.mark.parametrize("path,source", [
    (MERGE, "job: ${{ fromJSON(needs.decide.outputs.groups)"
            "['run-packages-write'] }}"),
    (CRON, "entry: ${{ fromJSON(needs.decide.outputs.groups)"
           "['run-packages-write'] }}"),
    (MANUAL, "job: ${{ fromJSON(needs.decide.outputs.groups)"
             "['run-packages-write'] }}")])
def test_declared_packages_write_and_sibling_without(tool_repo, path,
                                                     source):
    text = generated(tool_repo, SIBLINGS)[path]
    group = job_block(text, "run-packages-write")
    assert permissions_of(group) == {"contents": "write",
                                     "pull-requests": "write",
                                     "packages": "write"}
    assert source in group
    run = job_block(text, "run")
    assert permissions_of(run) == {"contents": "write",
                                   "pull-requests": "write"}
    assert "packages" not in run
    assert "groups" not in run
    assert "      groups: ${{ steps.decide.outputs.groups }}\n" in text
    assert "    needs: [decide, run, run-packages-write]\n" in text
    # the group job is the run job with only those parts changed
    placeholder = "(nothing:run-packages-write)"
    assert f"!= '{placeholder}'" in group and "'(nothing)'" not in group
    assert group.replace(f"'{placeholder}'", "'(nothing)'").replace(
        source.split(": ", 1)[1],
        "${{ fromJSON(needs.decide.outputs."
        f"{'runs' if path == CRON else 'jobs'}) }}}}").replace(
        "      packages: write\n", "") == run
    # no config job's name is written outside the Manual form
    if path != MANUAL:
        assert "publish" not in text


def test_open_group_gets_the_read_level(tool_repo):
    text = generated(tool_repo, {
        "contract": job(on=["open"], branches=["**"],
                        permissions={"packages": "read"}),
        "unit": job(on=["open"], branches=["**"])})[OPEN]
    group = job_block(text, "run-packages-read")
    assert permissions_of(group) == {"contents": "read", "packages": "read"}
    assert permissions_of(job_block(text, "run")) is None
    # the group job keeps the run job's concurrency group
    assert "group: git-cicd-open-${{ github.event.pull_request.number }}-" \
        "${{ matrix.job }}" in group


def test_no_declarations_generate_the_template_unchanged(tool_repo):
    files = generated(tool_repo, {"release": job(manual=True),
                                  "plain": job(on=["open"])})
    from tests.test_workflow import TEMPLATES
    for path, text in files.items():
        trigger = re.search(r"git-cicd-(\w+)\.yml", path).group(1)
        template = (TEMPLATES / f"{trigger}.yml").read_text()
        if trigger == "manual":
            continue  # the form varies
        assert text == bare(template), path
    assert not re.search(r"(?m)^  run-", files[MERGE])


def test_two_groups_render_in_first_seen_order(tool_repo):
    text = generated(tool_repo, {
        "i": job(permissions={"issues": "write"}),
        "p": job(permissions={"packages": "write"}),
        "q": job(permissions={"packages": "write"})})[MERGE]
    assert text.index("\n  run-issues-write:\n") < \
        text.index("\n  run-packages-write:\n")
    assert "    needs: [decide, run, run-issues-write, run-packages-write]\n" \
        in text
    assert text.count("\n  run-packages-write:\n") == 1


def test_render_workflow_infers_the_trigger(tool_repo):
    config = load(tool_repo, SIBLINGS)
    from tests.test_workflow import TEMPLATES
    template = (TEMPLATES / "merge.yml").read_text()
    assert git_cicd.render_workflow(config, TOOL, template) == \
        git_cicd.render_workflow(config, TOOL, template, "merge")
    # a template without a trigger or a run job gets no group job
    assert git_cicd.render_workflow(config, TOOL, "x\n__GROUP_JOBS__\n") \
        == "x\n"


# ── decide ──────────────────────────────────────────────────────────────────

def outputs(path):
    return dict(line.split("=", 1) for line in
                path.read_text().splitlines())


def test_decide_lists_each_job_in_exactly_one_group(tool_repo, tmp_path):
    tool_repo.config({"jobs": {
        "publish": job(permissions={"packages": "write"}),
        "release": job(),
        "idle": job(permissions={"issues": "write"}, branches=["dev"]),
    }})
    base = tool_repo.commit("base")
    tool_repo.write("src/x", "x\n")
    head = tool_repo.commit("change")
    out = tmp_path / "out"
    result = tool_repo.run("decide", "--trigger=merge", "--target=main",
                           "--source=main", f"--base={base}",
                           f"--head={head}",
                           env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0, result.stderr
    values = outputs(out)
    assert json.loads(values["jobs"]) == ["release"]
    groups = json.loads(values["groups"])
    assert groups == {"run-packages-write": ["publish"],
                      "run-issues-write": ["(nothing:run-issues-write)"]}
    names = json.loads(values["names"])
    assert names["(nothing:run-issues-write)"] == "Nothing needed"
    assert names["(nothing:run-packages-write)"] == "Nothing needed"


def test_decide_without_groups_writes_no_groups_output(tool_repo, tmp_path):
    tool_repo.config({"jobs": {"release": job()}})
    sha = tool_repo.commit("base")
    out = tmp_path / "out"
    result = tool_repo.run("decide", "--trigger=merge", "--target=main",
                           "--source=main", f"--base={sha}", f"--head={sha}",
                           env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0, result.stderr
    assert "groups" not in outputs(out)


def test_cron_decide_splits_runs_by_group(tool_repo, tmp_path):
    tool_repo.config({"jobs": SIBLINGS})
    tool_repo.commit("base")
    tool_repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
    out = tmp_path / "out"
    result = tool_repo.run("decide", "--trigger=cron", "--cron=0 3 * * *",
                           env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0, result.stderr
    values = outputs(out)
    assert [r["job"] for r in json.loads(values["runs"])] == ["release"]
    groups = json.loads(values["groups"])
    assert [r["job"] for r in groups["run-packages-write"]] == ["publish"]
    # a schedule where the group has nothing gets its placeholder entry
    tool_repo.config({"jobs": dict(SIBLINGS, publish=job(
        on=["merge", "cron"], cron="0 4 * * *",
        permissions={"packages": "write"}))})
    out.unlink()
    result = tool_repo.run("decide", "--trigger=cron", "--cron=0 3 * * *",
                           env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0, result.stderr
    assert json.loads(outputs(out)["groups"]) == {"run-packages-write": [
        {"job": "(nothing:run-packages-write)", "branch": "", "sha": "",
         "key": "(nothing:run-packages-write)"}]}


def test_manual_decide_puts_the_chosen_job_in_its_group(tool_repo, tmp_path):
    tool_repo.config({"jobs": SIBLINGS})
    sha = tool_repo.commit("base")
    out = tmp_path / "out"
    result = tool_repo.run("decide", "--trigger=manual", "--job=publish",
                           "--target=main", "--source=main",
                           f"--base={sha}", f"--head={sha}",
                           env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0, result.stderr
    values = outputs(out)
    assert json.loads(values["jobs"]) == ["(nothing)"]
    assert json.loads(values["groups"]) == {"run-packages-write": ["publish"]}


# ── verify ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("change", ["add", "change", "remove"])
def test_verify_fails_until_a_declaration_is_regenerated(tool_repo, change):
    before = {"publish": job(permissions={"packages": "write"}),
              "release": job()}
    if change == "add":
        before = {"publish": job(), "release": job()}
    generated(tool_repo, before)
    assert tool_repo.run("verify").returncode == 0
    after = json.loads(json.dumps(before))
    if change == "add":
        after["publish"]["permissions"] = {"packages": "write"}
    elif change == "change":
        after["publish"]["permissions"] = {"issues": "write"}
    else:
        del after["publish"]["permissions"]
    tool_repo.config({"jobs": after})
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert f"run: {TOOL} generate" in result.stdout
    assert tool_repo.run("generate").returncode == 0
    assert tool_repo.run("verify").returncode == 0
