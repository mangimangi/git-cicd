"""git-cicd's own jobs: the config declares test, release, vendor-check and
update-vendored, and their ci/ scripts call the vendored tools the way the
workflows they replace did. The tools are replaced by fakes that log their
argv and environment: no test runs .vendored/install or the git-semver
release."""

import json
import os
import shutil

import pytest

from tests.conftest import ROOT, git_cicd


def test_this_repository_declares_its_own_jobs():
    config = git_cicd.load_config(str(ROOT))
    jobs = config["jobs"]
    assert list(jobs) == ["test", "release", "vendor-check", "update-vendored"]

    release = jobs["release"]
    assert release["title"] == "Release"
    assert release["on"] == ["merge"] and release["branches"] == ["main"]
    assert release["paths"] is None and release["manual"] is True
    assert release["steps"] == [["ci/release.sh"]]
    assert {k: (v["choices"], v["default"], v["required"])
            for k, v in release["inputs"].items()} == {
        "bump_type": (["patch", "minor", "major"], "patch", False),
        "subdirectory": (None, "", False),
        "changelog_description": (None, "", False),
    }

    check = jobs["vendor-check"]
    assert check["title"] == "Check Vendor Files"
    assert check["on"] == ["open"] and check["branches"] == ["**"]
    assert check["paths"] is None
    assert check["steps"] == [["ci/vendor-check.sh"]]

    update = jobs["update-vendored"]
    assert update["title"] == "Install Vendored"
    assert update["on"] == ["cron"] and update["cron"] == "0 9 * * 1"
    assert update["branches"] == ["main"]
    assert update["steps"] == [["ci/update-vendored.sh"]]
    assert {k: (v["choices"], v["default"])
            for k, v in update["inputs"].items()} == {
        "vendor": (None, "all"), "version": (None, "latest"),
        "private": (["true", "false"], "false")}


def test_semver_files_list_every_template():
    files = json.loads((ROOT / ".vendored/configs/git-semver.json")
                       .read_text())["files"]
    for trigger in git_cicd.GENERATED_TRIGGERS:
        assert f"templates/workflows/{trigger}.yml" in files


FAKE = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["LOG"], "a") as f:
    f.write(json.dumps({"tool": sys.argv[0], "argv": sys.argv[1:],
                        "env": {k: v for k, v in os.environ.items()
                                if k.startswith(("GITHUB_", "INPUT_", "GH_"))}})
            + "\\n")
"""


@pytest.fixture
def own(repo, tmp_path):
    """A repository with this repository's ci/ scripts and config, and fake
    vendored tools."""
    for name in ("release.sh", "vendor-check.sh", "update-vendored.sh",
                 "setup.sh", "test.sh"):
        dest = repo.path / "ci" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "ci" / name, dest)
    repo.write(".vendored/configs/git-cicd.json",
               (ROOT / ".vendored/configs/git-cicd.json").read_text())
    for fake in (".vendored/pkg/git-semver/release", ".vendored/install",
                 ".vendored/check"):
        repo.write(fake, FAKE, executable=True)
    repo.log = tmp_path / "calls.jsonl"
    return repo


def calls(repo):
    if not repo.log.exists():
        return []
    return [json.loads(line) for line in repo.log.read_text().splitlines()]


def run_job(repo, job, trigger, head, base=None, branch="main", inputs=None,
            **env):
    run_env = {"LOG": str(repo.log), "GITHUB_TOKEN": "ghs_token"}
    run_env.update(env)
    if inputs is not None:
        run_env["CICD_MANUAL_INPUTS"] = json.dumps(inputs)
    result = repo.run("run-job", job, f"--trigger={trigger}",
                      f"--target={branch}", f"--source={branch}",
                      f"--base={base or head}", f"--head={head}", env=run_env)
    return result


def test_release_bumps_on_a_merge(own):
    before = own.commit("before")
    landed = own.commit("feat: something")
    result = run_job(own, "release", "merge", landed, base=before)
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    assert call["tool"].endswith(".vendored/pkg/git-semver/release")
    assert call["argv"] == ["bump"]
    env = call["env"]
    assert env["GITHUB_EVENT_NAME"] == "push"
    assert env["GITHUB_EVENT_BEFORE"] == before
    assert env["GH_TOKEN"] == "ghs_token"
    assert env["INPUT_BUMP_TYPE"] == "patch"
    assert env["INPUT_SUBDIRECTORY"] == "" and \
        env["INPUT_CHANGELOG_DESCRIPTION"] == ""


def test_release_publishes_a_bump_commit(own):
    before = own.commit("before")
    landed = own.commit("chore: bump version to 1.2.3")
    result = run_job(own, "release", "merge", landed, base=before)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [c["argv"] for c in calls(own)] == [["publish"]]


def test_release_skips_an_install_commit(own):
    before = own.commit("before")
    landed = own.commit("chore: install git-semver v1.0.0")
    result = run_job(own, "release", "merge", landed, base=before)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(own) == []
    assert "nothing to release" in result.stdout


def test_release_by_hand_with_inputs(own):
    sha = own.commit("chore: bump version to 1.2.3")  # the subject is ignored
    note = "it's \"new\" $HOME `id`\nline two"
    result = run_job(own, "release", "manual", sha,
                     inputs={"bump_type": "minor", "changelog_description":
                             note})
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    assert call["argv"] == ["bump"]
    assert call["env"]["GITHUB_EVENT_NAME"] == "workflow_dispatch"
    assert call["env"]["INPUT_BUMP_TYPE"] == "minor"
    assert call["env"]["INPUT_CHANGELOG_DESCRIPTION"] == note


def test_vendor_check_uses_the_base_and_the_source_branch(own):
    base = own.commit("base")
    own.git("checkout", "-q", "-b", "chore/install-git-semver")
    head = own.commit("install")
    result = own.run("run-job", "vendor-check", "--trigger=open",
                     "--target=main", "--source=chore/install-git-semver",
                     f"--base={base}", f"--head={head}",
                     env={"LOG": str(own.log)})
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    assert call["tool"].endswith(".vendored/check")
    assert call["argv"] == ["--base", base]
    assert call["env"]["GITHUB_HEAD_REF"] == "chore/install-git-semver"


def test_vendor_check_keeps_the_platform_head_ref(own):
    base = own.commit("base")
    result = own.run("run-job", "vendor-check", "--trigger=open",
                     "--target=main", "--source=feature", f"--base={base}",
                     f"--head={base}",
                     env={"LOG": str(own.log), "GITHUB_HEAD_REF": "from-pr"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(own)[0]["env"]["GITHUB_HEAD_REF"] == "from-pr"


def test_update_vendored_on_the_schedule(own):
    sha = own.commit("head")
    result = run_job(own, "update-vendored", "cron", sha, VENDOR_PAT="")
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    assert call["tool"].endswith(".vendored/install")
    assert call["argv"] == ["all", "--version", "latest", "--pr",
                            "--deps=install"]
    assert call["env"]["GH_TOKEN"] == "ghs_token"


def test_update_vendored_by_hand_private(own):
    sha = own.commit("head")
    result = run_job(own, "update-vendored", "manual", sha,
                     inputs={"vendor": "mangimangi/git-semver",
                             "version": "1.2.0", "private": "true"},
                     VENDOR_PAT="pat_token")
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    assert call["argv"] == ["mangimangi/git-semver", "--version", "1.2.0",
                            "--pr", "--deps=install", "--private"]
    assert call["env"]["GH_TOKEN"] == "pat_token"


def test_scripts_are_executable_and_named_by_the_config():
    for name in ("release.sh", "vendor-check.sh", "update-vendored.sh"):
        assert os.access(ROOT / "ci" / name, os.X_OK), name
