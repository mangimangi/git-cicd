"""git-cicd's own jobs: the config declares test, version-check, release,
vendor-check and update-vendored, and their steps call the vendored tools the
way the workflows they replace did. The tools are replaced by fakes that log
their argv and environment: no test runs .vendored/install or the git-semver
release. The version check also runs the real `git-semver check-bump`, which
is read-only and local."""

import json
import os
import shutil

import pytest

from tests.conftest import ROOT, git_cicd


def test_this_repository_declares_its_own_jobs():
    config = git_cicd.load_config(str(ROOT))
    jobs = config["jobs"]
    assert list(jobs) == ["test", "version-check", "release", "vendor-check",
                          "update-vendored"]

    version = jobs["version-check"]
    assert version["title"] == "Version Check"
    assert version["on"] == ["open"] and version["branches"] == ["main"]
    assert version["paths"] is None and version["manual"] is False
    assert version["steps"] == [[".vendored/pkg/git-semver/git-semver",
                                 "check-bump"]]

    # release tags the landed commit with the version it carries: no
    # subcommand, no ci/ script and no inputs (git-semver refuses them when
    # bump_on is pull_request)
    release = jobs["release"]
    assert release["title"] == "Release"
    assert release["on"] == ["merge"] and release["branches"] == ["main"]
    assert release["paths"] is None and release["manual"] is True
    assert release["steps"] == [[".vendored/pkg/git-semver/release"]]
    assert release["inputs"] == {}
    assert not (ROOT / "ci" / "release.sh").exists()

    check = jobs["vendor-check"]
    assert check["title"] == "Check Vendor Files"
    assert check["on"] == ["open"] and check["branches"] == ["**"]
    assert check["paths"] is None
    assert check["steps"] == [["ci/vendor-check.sh"]]
    # the open jobs run on pull requests, never by hand
    assert check["manual"] is False and jobs["test"]["manual"] is False
    assert version["manual"] is False

    update = jobs["update-vendored"]
    assert update["title"] == "Install Vendored"
    assert update["on"] == ["cron"] and update["cron"] == "0 9 * * 1"
    assert update["branches"] == ["main"]
    assert update["steps"] == [["ci/update-vendored.sh"]]
    assert {k: (v["choices"], v["default"])
            for k, v in update["inputs"].items()} == {
        "vendor": (None, "all"), "version": (None, "latest"),
        "private": (["true", "false"], "false")}


def test_the_manual_form_lists_release_and_update_vendored():
    """The committed Manual workflow's form, as generate writes it from this
    repository's config: the job dropdown and update-vendored's three named
    fields (release takes none)."""
    from tests.test_workflow import form_fields
    text = (ROOT / ".github/workflows/git-cicd-manual.yml").read_text()
    config = git_cicd.load_config(str(ROOT))
    assert text == git_cicd.render_workflows(config, "git-cicd")[
        ".github/workflows/git-cicd-manual.yml"]
    fields = form_fields(text)
    assert fields == {
        "job": {"description": "The config job to run", "required": True,
                "type": "choice",
                "options": ["Release / git-cicd:release",
                            "Install Vendored / git-cicd:update-vendored"]},
        "vendor": {"description": "Vendor to update (or all) "
                                  "(Install Vendored / "
                                  "git-cicd:update-vendored)",
                   "required": False, "default": "all", "type": "string"},
        "version": {"description": "Version to install (default: latest) "
                                   "(Install Vendored / "
                                   "git-cicd:update-vendored)",
                    "required": False, "default": "latest",
                    "type": "string"},
        "private": {"description": "Vendor repo is private (only needed when "
                                   "adding a new vendor) (Install Vendored / "
                                   "git-cicd:update-vendored)",
                    "required": False, "default": "false", "type": "choice",
                    "options": ["true", "false"]},
    }


def test_semver_bumps_in_the_pull_request():
    config = json.loads((ROOT / ".vendored/configs/git-semver.json")
                        .read_text())
    assert config["bump_on"] == "pull_request"


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
                                if k.startswith(("GITHUB_", "INPUT_", "GH_",
                                                 "CICD_", "VENDOR_"))}})
            + "\\n")
"""


@pytest.fixture
def own(repo, tmp_path):
    """A repository with this repository's ci/ scripts and config, and fake
    vendored tools."""
    for name in ("vendor-check.sh", "update-vendored.sh", "setup.sh",
                 "test.sh"):
        dest = repo.path / "ci" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "ci" / name, dest)
    repo.write(".vendored/configs/git-cicd.json",
               (ROOT / ".vendored/configs/git-cicd.json").read_text())
    for fake in (".vendored/pkg/git-semver/release",
                 ".vendored/pkg/git-semver/git-semver", ".vendored/install",
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
        run_env["CICD_MANUAL_FORM"] = json.dumps(inputs)
    result = repo.run("run-job", job, f"--trigger={trigger}",
                      f"--target={branch}", f"--source={branch}",
                      f"--base={base or head}", f"--head={head}", env=run_env)
    return result


def test_release_tags_the_landed_commit_on_a_merge(own):
    before = own.commit("before")
    landed = own.commit("feat: something")
    result = run_job(own, "release", "merge", landed, base=before)
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    assert call["tool"].endswith(".vendored/pkg/git-semver/release")
    # no subcommand: release reads bump_on and tags what landed
    assert call["argv"] == []
    env = call["env"]
    assert env["CICD_TRIGGER"] == "merge"
    assert env["CICD_BASE"] == before and env["CICD_HEAD"] == landed
    assert env["GITHUB_TOKEN"] == "ghs_token"
    assert not any(k.startswith(("CICD_INPUT_", "INPUT_")) for k in env)


def test_release_by_hand_takes_no_inputs(own):
    sha = own.commit("feat: something")
    result = run_job(own, "release", "manual", sha, inputs={})
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    assert call["argv"] == []
    assert call["env"]["CICD_TRIGGER"] == "manual"


def test_version_check_runs_check_bump_on_a_pull_request(own):
    base = own.commit("base")
    own.git("checkout", "-q", "-b", "feature")
    head = own.commit("change")
    result = own.run("run-job", "version-check", "--trigger=open",
                     "--target=main", "--source=feature", f"--base={base}",
                     f"--head={head}", env={"LOG": str(own.log)})
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    assert call["tool"].endswith(".vendored/pkg/git-semver/git-semver")
    assert call["argv"] == ["check-bump"]
    assert call["env"]["CICD_BASE"] == base
    assert call["env"]["CICD_HEAD"] == head


@pytest.fixture
def semver(own):
    """The `own` repository with this repository's git-semver config and the
    real vendored git-semver, at version 1.0.0."""
    repo = own
    repo.write(".vendored/configs/git-semver.json",
               (ROOT / ".vendored/configs/git-semver.json").read_text())
    tool = repo.path / ".vendored/pkg/git-semver/git-semver"
    shutil.copy2(ROOT / ".vendored/pkg/git-semver/git-semver", tool)
    repo.write("VERSION", "1.0.0\n")
    repo.write("git-cicd", "old\n")
    repo.base = repo.commit("base")
    repo.git("checkout", "-q", "-b", "feature")
    return repo


def version_check(repo):
    head = repo.commit("change")
    return repo.run("run-job", "version-check", "--trigger=open",
                    "--target=main", "--source=feature",
                    f"--base={repo.base}", f"--head={head}")


def test_version_check_fails_a_change_that_keeps_the_version(semver):
    semver.write("git-cicd", "new\n")
    result = version_check(semver)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "the version was not raised: VERSION is still 1.0.0" in \
        result.stdout


def test_version_check_passes_a_change_that_raises_the_version(semver):
    semver.write("git-cicd", "new\n")
    semver.write("VERSION", "1.0.1\n")
    result = version_check(semver)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout


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


def test_update_vendored_prefers_cicd_write_token(own):
    sha = own.commit("head")
    result = run_job(own, "update-vendored", "manual", sha,
                     inputs={"private": "true"},
                     CICD_WRITE_TOKEN="write_token", VENDOR_PAT="pat_token")
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    assert call["env"]["GH_TOKEN"] == "write_token"


ALL_TOKENS = {"CICD_WRITE_TOKEN": "write_token",
              "CICD_READ_TOKEN": "read_token", "VENDOR_PAT": "pat_token"}


@pytest.mark.parametrize("job,trigger,expected", [
    ("update-vendored", "cron", {"CICD_WRITE_TOKEN", "VENDOR_PAT"}),
    ("update-vendored", "manual", {"CICD_WRITE_TOKEN", "VENDOR_PAT"}),
    ("release", "merge", set()),
    ("release", "manual", set()),
])
def test_own_jobs_get_only_what_they_declare(own, job, trigger, expected):
    """With all three secrets in the caller's environment, update-vendored
    sees CICD_WRITE_TOKEN and VENDOR_PAT, release none of them."""
    before = own.commit("before")
    sha = own.commit("head")
    result = run_job(own, job, trigger, sha, base=before,
                     inputs={} if trigger == "manual" else None,
                     **ALL_TOKENS)
    assert result.returncode == 0, result.stdout + result.stderr
    (call,) = calls(own)
    seen = {k for k in ALL_TOKENS if k in call["env"]}
    assert seen == expected
    assert call["env"]["GITHUB_TOKEN"] == "ghs_token"


def test_own_declarations():
    config = git_cicd.load_config(str(ROOT))
    declared = {n: (j["secrets"], j["permissions"])
                for n, j in config["jobs"].items()}
    assert declared == {
        "test": ([], {}), "version-check": ([], {}), "release": ([], {}),
        "vendor-check": ([], {}),
        "update-vendored": (["CICD_WRITE_TOKEN", "VENDOR_PAT"], {}),
    }


@pytest.mark.parametrize("trigger,job", [("cron", None),
                                         ("manual", "update-vendored"),
                                         ("merge", None),
                                         ("manual", "release")])
def test_generated_workflows_give_update_vendored_its_two_secrets(
        own, tmp_path, trigger, job):
    """The committed workflows select each secret by decide's `secrets`
    output, which (from this repository's config) gives update-vendored's
    matrix entry CICD_WRITE_TOKEN and VENDOR_PAT and release none."""
    from tests.test_workflow import secret_lines
    path = git_cicd.WORKFLOWS[trigger][1]
    text = (ROOT / path).read_text()
    matrix = "matrix.entry.job" if trigger == "cron" else "matrix.job"
    for line in secret_lines(matrix):
        assert line in text.splitlines(), line
    sha = own.commit("head")
    own.git("update-ref", "refs/remotes/origin/main", sha)
    out = tmp_path / "out"
    args = {"cron": ["--trigger=cron", "--cron=0 9 * * 1"],
            "merge": ["--trigger=merge", "--target=main", "--source=main",
                      f"--base={sha}", f"--head={sha}"],
            "manual": ["--trigger=manual", f"--job={job}", "--target=main",
                       "--source=main", f"--base={sha}", f"--head={sha}"]}
    result = own.run("decide", *args[trigger],
                     env={"GITHUB_OUTPUT": str(out)})
    assert result.returncode == 0, result.stderr
    values = dict(l.split("=", 1) for l in out.read_text().splitlines())
    secrets = json.loads(values["secrets"])
    assert secrets["update-vendored"] == ["CICD_WRITE_TOKEN", "VENDOR_PAT"]
    assert secrets["release"] == []
    assert all(v == [] for k, v in secrets.items() if k != "update-vendored")


def test_scripts_are_executable_and_named_by_the_config():
    for name in ("vendor-check.sh", "update-vendored.sh"):
        assert os.access(ROOT / "ci" / name, os.X_OK), name
