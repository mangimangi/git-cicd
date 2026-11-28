"""Shared fixtures for git-cicd tests."""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "git-cicd"


def _import_extensionless(name, filename):
    """Import a script without .py extension as a Python module."""
    filepath = str(ROOT / filename)
    loader = importlib.machinery.SourceFileLoader(name, filepath)
    spec = importlib.util.spec_from_loader(name, loader, origin=filepath)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = filepath
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


git_cicd = _import_extensionless("git_cicd", "git-cicd")


def git(repo, *args):
    """Run git in repo, raise on failure, return stdout."""
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                            text=True)
    if result.returncode != 0:
        raise AssertionError(f"git {args} failed: {result.stderr}")
    return result.stdout.strip()


class Repo:
    """A temporary git repository with helpers to write files and commit."""

    def __init__(self, path):
        self.path = path
        git(path, "init", "-q", "-b", "main")
        git(path, "config", "user.email", "test@example.com")
        git(path, "config", "user.name", "Test")
        git(path, "config", "commit.gpgsign", "false")

    def write(self, rel, content="", executable=False):
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        if executable:
            p.chmod(0o755)
        return p

    def script(self, rel, body="exit 0\n"):
        """Write an executable shell script."""
        return self.write(rel, "#!/bin/sh\n" + body, executable=True)

    def config(self, data):
        return self.write(".vendored/configs/git-cicd.json",
                          json.dumps(data, indent=2) + "\n")

    def commit(self, message="commit"):
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.path, "rev-parse", "HEAD")

    def git(self, *args):
        return git(self.path, *args)

    def install_tool(self, rel=".vendored/pkg/git-cicd"):
        """Copy the script and its templates into the repository, as the
        installer does. Return the tool path relative to the root."""
        dest = self.path / rel
        shutil.copytree(ROOT / "templates" / "workflows",
                        dest / "templates" / "workflows", dirs_exist_ok=True)
        shutil.copy2(SCRIPT, dest / "git-cicd")
        self.tool = dest / "git-cicd"
        return f"{rel}/git-cicd"

    def run(self, *args, env=None, cwd=None):
        """Run the git-cicd script as a subprocess in the repository (the
        installed copy when install_tool was called)."""
        run_env = os.environ.copy()
        for key in list(run_env):
            if key.startswith(("GITHUB_", "CICD_")):
                del run_env[key]
        if env:
            run_env.update(env)
        script = getattr(self, "tool", SCRIPT)
        return subprocess.run([sys.executable, str(script), *args],
                              cwd=cwd or self.path, capture_output=True,
                              text=True, env=run_env)


# The token names no test may read from the caller's environment. ci/test.sh
# sets each to a sentinel value; the autouse fixture below removes them before
# every test, and tests/test_token_guard.py fails while one is set.
TOKEN_NAMES = ("CICD_WRITE_TOKEN", "CICD_READ_TOKEN", "VENDOR_PAT", "GH_TOKEN",
               "GITHUB_TOKEN")


@pytest.fixture(autouse=True)
def no_tokens(monkeypatch):
    """Before every test, remove the tokens and every GITHUB_* and CICD_*
    variable the caller's environment holds (a test sets its own with
    monkeypatch), so no test passes locally and fails in CI, where Actions
    sets GITHUB_REPOSITORY, GITHUB_ACTIONS and the rest, or the other way
    round."""
    for key in TOKEN_NAMES:
        monkeypatch.delenv(key, raising=False)
    for key in list(os.environ):
        if key.startswith(("GITHUB_", "CICD_")):
            monkeypatch.delenv(key)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    path = tmp_path / "repo"
    path.mkdir()
    for key in list(os.environ):
        if key.startswith(("GITHUB_", "CICD_")):
            monkeypatch.delenv(key)
    monkeypatch.chdir(path)
    return Repo(path)
