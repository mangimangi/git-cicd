"""Tests for generating and verifying the GitHub Actions workflow."""

import re

import pytest

from tests.conftest import ROOT, git_cicd

WORKFLOW = ".github/workflows/git-cicd.yml"
TOOL = ".vendored/pkg/git-cicd/git-cicd"


def base_config(**top):
    config = {"jobs": {
        "test": {"on": ["open"], "branches": ["**"], "paths": ["src/**"],
                 "setup": "ci/setup.sh", "steps": ["ci/test.sh"]},
        "release": {"on": ["merge"], "branches": ["main"],
                    "steps": ["ci/bump.sh"]},
    }, "needs_nothing": ["docs/**"]}
    config.update(top)
    return config


@pytest.fixture
def tool_repo(repo):
    for name in ("ci/setup.sh", "ci/test.sh", "ci/bump.sh", "ci/other.sh"):
        repo.script(name)
    repo.install_tool()
    return repo


def generate(repo, config):
    repo.config(config)
    result = repo.run("generate")
    assert result.returncode == 0, result.stderr
    return (repo.path / WORKFLOW).read_text()


def run_blocks(text):
    """The lines of every `run:` block (inline or literal block)."""
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", lines[i])
        if m:
            indent = len(m.group(1))
            rest = m.group(2)
            if rest in ("|", ">", "|-", ">-"):
                body = []
                i += 1
                while i < len(lines) and (not lines[i].strip() or
                                          len(lines[i]) - len(lines[i].lstrip())
                                          > indent):
                    body.append(lines[i])
                    i += 1
                blocks.append("\n".join(body))
                continue
            blocks.append(rest)
        i += 1
    return blocks


def test_generate_writes_file(tool_repo):
    text = generate(tool_repo, base_config())
    assert text.startswith("# .github/workflows/git-cicd.yml - GENERATED")
    assert "name: git-cicd\n" in text
    assert f"python3 {TOOL} decide" in text
    assert "__TOOL__" not in text and "__SCHEDULE__" not in text
    assert "schedule:" not in text


def test_no_expressions_inside_run_blocks(tool_repo):
    text = generate(tool_repo, base_config())
    blocks = run_blocks(text)
    assert len(blocks) == 5
    for block in blocks:
        assert "${{" not in block, block


def test_template_run_blocks_have_no_expressions():
    text = (ROOT / "templates" / "workflow.yml").read_text()
    for block in run_blocks(text):
        assert "${{" not in block


def test_workflow_contract(tool_repo):
    text = generate(tool_repo, base_config())
    assert "  pull_request:\n    types: [opened, synchronize, reopened]\n" in text
    assert "permissions:\n  contents: read\n" in text
    assert ("group: git-cicd-${{ github.workflow }}-${{ "
            "github.event.pull_request.number || github.ref }}") in text
    assert ("cancel-in-progress: ${{ github.event_name == 'pull_request' }}"
            in text)
    assert "name: git-cicd verdict" in text
    assert "if: always()" in text
    assert "max-parallel: ${{ fromJSON(needs.decide.outputs.max_parallel) }}" \
        in text
    assert "job: ${{ fromJSON(needs.decide.outputs.jobs) }}" in text
    assert "fail-fast: false" in text
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert "VENDOR_PAT: ${{ secrets.VENDOR_PAT }}" in text
    assert "--setup --result=" in text
    assert "name: git-cicd-result-${{ matrix.job }}" in text
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses and all(re.fullmatch(
        r"actions/(checkout|upload-artifact|download-artifact)@v\d+", u)
        for u in uses), uses
    assert "python-version" not in text and "setup-python" not in text
    # facts reach run: only as quoted shell variables
    assert 'TARGET: ${{ github.base_ref }}' in text
    assert 'SOURCE: ${{ github.head_ref }}' in text
    assert 'BASE: ${{ github.event.pull_request.base.sha }}' in text
    assert 'HEAD_SHA: ${{ github.event.pull_request.head.sha }}' in text
    assert '--target="$TARGET"' in text and '--source="$SOURCE"' in text


def test_non_cron_differences_generate_identical_file(tool_repo):
    a = generate(tool_repo, base_config())
    b_config = {"jobs": {
        "other": {"on": ["open", "merge"], "branches": ["plan/**", "main"],
                  "paths": ["lib/**"], "steps": [["ci/other.sh", "-x"]],
                  "blocking": False, "manual": False},
    }, "needs_nothing": [".pearls/**", "*.md"], "max_parallel": 7}
    b = generate(tool_repo, b_config)
    assert a == b


def test_cron_job_changes_only_schedule_block(tool_repo):
    a = generate(tool_repo, base_config())
    config = base_config()
    config["jobs"]["nightly"] = {"on": ["cron"], "branches": ["main"],
                                 "cron": "0 3 * * *", "steps": ["ci/test.sh"]}
    config["jobs"]["weekly"] = {"on": ["cron", "open"], "branches": ["main"],
                                "cron": "0 9 * * 1", "steps": ["ci/test.sh"]}
    config["jobs"]["again"] = {"on": ["cron"], "branches": ["dev"],
                               "cron": "0 3 * * *", "steps": ["ci/test.sh"]}
    b = generate(tool_repo, config)
    block = ('  schedule:\n    - cron: "0 3 * * *"\n'
             '    - cron: "0 9 * * 1"\n')
    assert block in b
    assert b.replace(block, "") == a


def test_generate_is_deterministic(tool_repo):
    a = generate(tool_repo, base_config())
    b = generate(tool_repo, base_config())
    assert a == b


def test_verify_passes_after_generate(tool_repo):
    generate(tool_repo, base_config())
    result = tool_repo.run("verify")
    assert result.returncode == 0, result.stdout
    assert "workflow matches config" in result.stdout


def test_verify_fails_after_hand_edit(tool_repo):
    generate(tool_repo, base_config())
    path = tool_repo.path / WORKFLOW
    path.write_text(path.read_text().replace("fail-fast: false",
                                             "fail-fast: true"))
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert "-      fail-fast: true" in result.stdout
    assert "+      fail-fast: false" in result.stdout
    assert (f"the workflow does not match the config; run: {TOOL} generate "
            f"and commit {WORKFLOW}") in result.stdout


def test_verify_fails_after_config_cron_change(tool_repo):
    generate(tool_repo, base_config())
    config = base_config()
    config["jobs"]["nightly"] = {"on": ["cron"], "branches": ["main"],
                                 "cron": "0 3 * * *", "steps": ["ci/test.sh"]}
    tool_repo.config(config)
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert '+    - cron: "0 3 * * *"' in result.stdout
    assert f"run: {TOOL} generate" in result.stdout


def test_verify_missing_file(tool_repo):
    tool_repo.config(base_config())
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert f"{WORKFLOW} is missing" in result.stdout
    assert f"run: {TOOL} generate" in result.stdout


def test_verify_function(tool_repo):
    generate(tool_repo, base_config())
    config = git_cicd.load_config(str(tool_repo.path))
    ok, message = git_cicd.verify_workflow(config, str(tool_repo.path),
                                           tool=TOOL)
    assert ok and message == "workflow matches config"
    ok, message = git_cicd.verify_workflow(config, str(tool_repo.path),
                                           tool="elsewhere/git-cicd")
    assert not ok and "run: elsewhere/git-cicd generate" in message


def test_tool_path_follows_install_location(repo):
    repo.script("ci/test.sh")
    tool = repo.install_tool("tools/cicd")
    assert tool == "tools/cicd/git-cicd"
    text = generate(repo, {"jobs": {}})
    assert "python3 tools/cicd/git-cicd decide" in text


def test_root_script_tool_path():
    assert git_cicd.tool_path(str(ROOT)) == "git-cicd"


def test_generate_refuses_tool_outside_repo(repo):
    repo.config({"jobs": {}})
    result = repo.run("generate")  # the root script, outside this temp repo
    assert result.returncode == 2
    assert "outside the repository" in result.stderr


def test_generate_refuses_invalid_config(tool_repo):
    tool_repo.config({"jobs": {"x": {"steps": ["ci/test.sh"]}}})
    result = tool_repo.run("generate")
    assert result.returncode == 2
    assert not (tool_repo.path / WORKFLOW).exists()


def test_template_documents_reserved_triggers():
    text = (ROOT / "templates" / "workflow.yml").read_text()
    head = text.split("\nname: git-cicd\n")[0]
    assert "Reserved for later moments" in head
    assert "`push` with NO branch filter" in head
    assert "`workflow_dispatch` with one free-text `job` input" in head
    assert "`permissions` cannot be expressions" in head
    assert "cron moment is not built yet" in head
