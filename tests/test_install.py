"""Tests for install.sh (run as git-vendored runs it)."""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
INSTALL_SH = ROOT / "install.sh"
SHIPPED = ["git-cicd", "templates/workflows/open.yml",
           "templates/workflows/merge.yml", "templates/workflows/manual.yml",
           "templates/config.json",
           "templates/config.schema"]
INSTALL_DIR = ".vendored/pkg/git-cicd"
CONFIG = ".vendored/configs/git-cicd.json"
WORKFLOW = ".github/workflows/git-cicd-open.yml"
MERGE = ".github/workflows/git-cicd-merge.yml"
MANUAL = ".github/workflows/git-cicd-manual.yml"
WORKFLOWS_ALLOWED = ".github/workflows/git-cicd-*.yml"
LEGACY = ".github/workflows/git-cicd.yml"


def _mirror(tmp_path):
    """A local copy of the files install.sh fetches."""
    repo_dir = tmp_path / "mirror"
    for rel in SHIPPED:
        dest = repo_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / rel).read_bytes())
    return repo_dir


def stub_install_sh(tmp_path):
    """install.sh with fetch_file replaced by a copy from the local mirror."""
    mirror = _mirror(tmp_path)
    stub_fetch = f'''fetch_file() {{
    local repo_path="$1"
    local dest="$2"
    cp "{mirror}/$repo_path" "$dest"
}}'''
    modified = re.sub(r"^fetch_file\(\) \{.*?^\}", stub_fetch,
                      INSTALL_SH.read_text(), flags=re.MULTILINE | re.DOTALL)
    assert modified != INSTALL_SH.read_text()
    script = tmp_path / "install.sh"
    script.write_text(modified)
    script.chmod(0o755)
    return script


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "project"
    p.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=p, check=True)
    return p


def run_install(project, script, version="1.2.3", env=None, unset=()):
    run_env = os.environ.copy()
    for key in list(run_env):
        if key.startswith(("GITHUB_", "CICD_", "VENDOR_")) or key == "GH_TOKEN":
            del run_env[key]
    run_env["VENDOR_INSTALL_DIR"] = INSTALL_DIR
    if env:
        run_env.update(env)
    for key in unset:
        run_env.pop(key, None)
    return subprocess.run(["bash", str(script), version], cwd=project,
                          capture_output=True, text=True, env=run_env)


def test_code_lands_under_install_dir(tmp_path, project):
    result = run_install(project, stub_install_sh(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    tool = project / INSTALL_DIR / "git-cicd"
    assert tool.read_bytes() == (ROOT / "git-cicd").read_bytes()
    assert tool.stat().st_mode & 0o111
    assert (project / INSTALL_DIR / "templates" / "workflows" / "open.yml") \
        .read_bytes() == (ROOT / "templates" / "workflows" / "open.yml") \
        .read_bytes()
    for trigger in ("open", "merge", "manual"):
        assert (project / INSTALL_DIR / "templates" / "workflows"
                / f"{trigger}.yml").read_bytes() == \
            (ROOT / "templates" / "workflows" / f"{trigger}.yml").read_bytes()
    assert (project / MERGE).is_file() and (project / MANUAL).is_file()
    assert "Installing git-cicd v1.2.3 from mangimangi/git-cicd" in result.stdout


def test_v_prefix_and_vendor_ref(tmp_path, project):
    result = run_install(project, stub_install_sh(tmp_path), version="x",
                         env={"VENDOR_REF": "v2.0.0"})
    assert result.returncode == 0
    assert "git-cicd v2.0.0" in result.stdout


def test_config_created_when_missing_and_valid(tmp_path, project):
    result = run_install(project, stub_install_sh(tmp_path))
    assert result.returncode == 0
    config = json.loads((project / CONFIG).read_text())
    assert config["jobs"] == {}
    assert config["needs_nothing"] == []
    assert config["_vendor"]["repo"] == "mangimangi/git-cicd"
    assert config["_vendor"]["install_branch"] == "chore/install-git-cicd"
    assert config["_vendor"]["protected"] == [".vendored/pkg/git-cicd/**"]
    assert config["_vendor"]["allowed"] == [CONFIG, WORKFLOWS_ALLOWED]
    validate = subprocess.run(
        ["python3", f"{INSTALL_DIR}/git-cicd", "validate"], cwd=project,
        capture_output=True, text=True)
    assert validate.returncode == 0, validate.stderr
    assert "config ok: 0 jobs" in validate.stdout


def test_config_preserved_on_reinstall(tmp_path, project):
    script = stub_install_sh(tmp_path)
    assert run_install(project, script).returncode == 0
    ci = project / "ci" / "test.sh"
    ci.parent.mkdir()
    ci.write_text("#!/bin/sh\n")
    ci.chmod(0o755)
    custom = {"jobs": {"test": {"on": ["open"], "branches": ["**"],
                                "steps": ["ci/test.sh"]},
                       "nightly": {"on": ["cron"], "branches": ["main"],
                                   "cron": "0 4 * * *",
                                   "steps": ["ci/test.sh"]}}}
    (project / CONFIG).write_text(json.dumps(custom))
    result = run_install(project, script, version="1.2.4")
    assert result.returncode == 0, result.stderr
    assert json.loads((project / CONFIG).read_text()) == custom


def test_schema_installed(tmp_path, project):
    run_install(project, stub_install_sh(tmp_path))
    schema = json.loads(
        (project / ".vendored/manifests/git-cicd.schema").read_text())
    fields = schema["fields"]
    assert fields["jobs"]["type"] == "object" and fields["jobs"]["required"]
    assert fields["needs_nothing"]["type"] == "array"
    assert fields["max_parallel"]["type"] == "integer"
    for field in fields.values():
        assert set(field) == {"type", "required", "description"}


def test_workflow_generated_and_regenerated(tmp_path, project):
    script = stub_install_sh(tmp_path)
    assert run_install(project, script).returncode == 0
    workflow = project / WORKFLOW
    text = workflow.read_text()
    assert f"python3 {INSTALL_DIR}/git-cicd decide" in text
    assert "schedule:" not in text
    # a hand edit (or an older version's file) is replaced on reinstall
    workflow.write_text("stale\n")
    ci = project / "ci" / "n.sh"
    ci.parent.mkdir()
    ci.write_text("#!/bin/sh\n")
    ci.chmod(0o755)
    (project / CONFIG).write_text(json.dumps({"jobs": {"n": {
        "on": ["cron"], "branches": ["main"], "cron": "0 4 * * *",
        "steps": ["ci/n.sh"]}}}))
    assert run_install(project, script).returncode == 0
    assert workflow.read_text() == text
    verify = subprocess.run(["python3", f"{INSTALL_DIR}/git-cicd", "verify"],
                            cwd=project, capture_output=True, text=True)
    assert verify.returncode == 0, verify.stdout


def test_manifest_lists_installed_files(tmp_path, project):
    manifest = tmp_path / "manifest.txt"
    result = run_install(project, stub_install_sh(tmp_path),
                         env={"VENDOR_MANIFEST": str(manifest)})
    assert result.returncode == 0
    files = manifest.read_text().splitlines()
    assert files == [f"{INSTALL_DIR}/git-cicd",
                     f"{INSTALL_DIR}/templates/workflows/open.yml",
                     f"{INSTALL_DIR}/templates/workflows/merge.yml",
                     f"{INSTALL_DIR}/templates/workflows/manual.yml",
                     ".vendored/manifests/git-cicd.schema", WORKFLOW, MERGE,
                     MANUAL]
    assert CONFIG not in files
    for f in files:
        assert (project / f).is_file()


def _vendor_check_allows(path, allowed):
    """The vendor check's own matching (.vendored/check)."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(
        "vendored_check", str(ROOT / ".vendored" / "check"))
    spec = importlib.util.spec_from_loader("vendored_check", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.matches_any_pattern(path, allowed)


def test_allowed_covers_every_per_trigger_workflow():
    """The editable list covers the generated files, those still to come
    included, and nothing else under .github/workflows."""
    allowed = json.loads((ROOT / "templates" / "config.json").read_text())[
        "_vendor"]["allowed"]
    for trigger in ("open", "merge", "cron", "manual"):
        assert _vendor_check_allows(f".github/workflows/git-cicd-{trigger}.yml",
                                    allowed), trigger
    for other in (".github/workflows/version-bump.yml",
                  ".github/workflows/check-vendor.yml",
                  ".github/workflows/sub/git-cicd-open.yml"):
        assert not _vendor_check_allows(other, allowed), other


def test_upgrade_from_the_single_workflow_file(tmp_path, project):
    """An install over an earlier version: the old single file and the old
    template go, the per-trigger file is written, verify passes."""
    script = stub_install_sh(tmp_path)
    (project / LEGACY).parent.mkdir(parents=True)
    (project / LEGACY).write_text("name: git-cicd\n")
    old_template = project / INSTALL_DIR / "templates" / "workflow.yml"
    old_template.parent.mkdir(parents=True)
    old_template.write_text("old\n")
    result = run_install(project, script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (project / LEGACY).exists()
    assert not old_template.exists()
    assert f"removed {LEGACY}" in result.stdout
    assert (project / WORKFLOW).is_file()
    verify = subprocess.run(["python3", f"{INSTALL_DIR}/git-cicd", "verify"],
                            cwd=project, capture_output=True, text=True)
    assert verify.returncode == 0, verify.stdout


def test_no_manifest_without_env(tmp_path, project):
    result = run_install(project, stub_install_sh(tmp_path))
    assert result.returncode == 0
    assert not list(tmp_path.glob("*.manifest"))


def test_install_dir_required(tmp_path, project):
    result = run_install(project, stub_install_sh(tmp_path),
                         unset=("VENDOR_INSTALL_DIR",))
    assert result.returncode != 0
    assert "VENDOR_INSTALL_DIR is required" in result.stderr
    assert not (project / ".vendored").exists()


def test_version_required(tmp_path, project):
    script = stub_install_sh(tmp_path)
    run_env = {k: v for k, v in os.environ.items()
               if not k.startswith("VENDOR_")}
    run_env["VENDOR_INSTALL_DIR"] = INSTALL_DIR
    result = subprocess.run(["bash", str(script)], cwd=project,
                            capture_output=True, text=True, env=run_env)
    assert result.returncode != 0
    assert "Usage: install.sh <version>" in result.stderr


def test_invalid_config_fails_install(tmp_path, project):
    (project / ".vendored/configs").mkdir(parents=True)
    (project / CONFIG).write_text(json.dumps({"jobs": {"x": {
        "steps": ["ci/missing.sh"]}}}))
    result = run_install(project, stub_install_sh(tmp_path))
    assert result.returncode != 0
    assert "job x: missing required field branches" in result.stderr


def test_real_fetch_file_with_curl(tmp_path, project):
    """The unmodified install.sh, with curl on PATH served from the mirror."""
    mirror = _mirror(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(f"""#!/bin/bash
# curl -fsSL <url> -o <dest>
url="$2"; dest="$4"
prefix="https://raw.githubusercontent.com/owner/fork/v9.9.9/"
case "$url" in "$prefix"*) ;; *) echo "unexpected $url" >&2; exit 22;; esac
cp "{mirror}/${{url#$prefix}}" "$dest"
""")
    curl.chmod(0o755)
    result = run_install(project, INSTALL_SH, version="v9.9.9",
                         env={"PATH": f"{bin_dir}:{os.environ['PATH']}",
                              "VENDOR_REPO": "owner/fork"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / INSTALL_DIR / "git-cicd").is_file()
    assert (project / WORKFLOW).is_file()


def test_real_fetch_file_with_gh(tmp_path, project):
    """With GH_TOKEN set, install.sh downloads through gh api."""
    mirror = _mirror(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    gh = bin_dir / "gh"
    gh.write_text(f"""#!/bin/bash
# gh api repos/<repo>/contents/<path>?ref=<ref> --jq .content
echo "$2" >> "{log}"
path="${{2#repos/mangimangi/git-cicd/contents/}}"
path="${{path%%\\?ref=*}}"
base64 -w0 "{mirror}/$path"
""")
    gh.chmod(0o755)
    result = run_install(project, INSTALL_SH,
                         env={"PATH": f"{bin_dir}:{os.environ['PATH']}",
                              "GH_TOKEN": "t"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "repos/mangimangi/git-cicd/contents/git-cicd?ref=v1.2.3" in \
        log.read_text()
    assert (project / INSTALL_DIR / "git-cicd").read_bytes() == \
        (ROOT / "git-cicd").read_bytes()
