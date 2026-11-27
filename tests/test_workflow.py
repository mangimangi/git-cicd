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
    assert len(blocks) == 8
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
    assert "name: git-cicd report" in text
    assert "if: always()" in text
    assert "max-parallel: ${{ fromJSON(needs.decide.outputs.max_parallel) }}" \
        in text
    assert "job: ${{ fromJSON(needs.decide.outputs.jobs) }}" in text
    assert "fail-fast: false" in text
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert "VENDOR_PAT: ${{ secrets.VENDOR_PAT }}" in text
    assert "--setup --result=" in text
    assert "name: git-cicd-result-${{ matrix.job }}" in text
    uses = re.findall(r"(?m)^\s*(?:- )?uses:\s*(\S+)", text)
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


def job_blocks(text):
    """Each job's lines under `jobs:`, by job id."""
    body = text.split("\njobs:\n", 1)[1]
    jobs = {}
    for chunk in re.split(r"(?m)^(?=  [A-Za-z0-9_-]+:$)", body):
        m = re.match(r"  ([A-Za-z0-9_-]+):\n", chunk)
        if m:
            jobs[m.group(1)] = chunk
    return jobs


STATUS_PERMISSIONS = ("    permissions:\n      contents: read\n"
                      "      statuses: write\n")


def test_permissions_status_write_only(tool_repo):
    """On the pull request trigger the token may write commit statuses, and
    nothing else: contents stay read-only, and the jobs that run the config's
    scripts get no write at all."""
    text = generate(tool_repo, base_config())
    top = text.split("\njobs:\n", 1)[0]
    assert top.endswith("\npermissions:\n  contents: read\n")
    jobs = job_blocks(text)
    assert set(jobs) == {"decide", "run", "verdict"}
    assert STATUS_PERMISSIONS in jobs["decide"]
    assert STATUS_PERMISSIONS in jobs["verdict"]
    assert "permissions:" not in jobs["run"]
    writes = re.findall(r"^\s*([a-z-]+):\s*write\s*$", text, re.M)
    assert writes == ["statuses", "statuses"]
    assert "write-all" not in text
    assert text.count("permissions:") == 3


RUN_CONCURRENCY = (
    "    concurrency:\n"
    "      group: git-cicd-${{ github.workflow }}-${{ "
    "github.event.pull_request.number || github.ref }}-${{ matrix.job }}\n"
    "      cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n")


def test_concurrency_only_on_the_script_running_job(tool_repo):
    """The pending status never waits on a superseded run: no concurrency at
    the workflow level or on the status-posting jobs. A newer push still
    cancels the older run's script-running jobs, one group per pull request
    and job, so the jobs of one run do not cancel each other."""
    text = generate(tool_repo, base_config())
    top = text.split("\njobs:\n", 1)[0]
    assert not re.search(r"(?m)^concurrency:", top)
    jobs = job_blocks(text)
    assert "concurrency" not in jobs["decide"]
    assert "concurrency" not in jobs["verdict"]
    assert RUN_CONCURRENCY in jobs["run"]
    assert text.count("concurrency:") == 1


def test_superseded_run_stops_after_deciding(tool_repo):
    """A run whose head is no longer the pull request's head fails in decide,
    after the pending status and the decisions, so it queues no job that
    could cancel the newer run's and its report is not green for jobs that
    never ran."""
    text = generate(tool_repo, base_config())
    steps = job_blocks(text)["decide"].split("      - name: ")[1:]
    names = [s.split("\n", 1)[0] for s in steps]
    assert names.index("Stop if a newer push superseded this run") == \
        names.index("Decide which jobs the change needs") + 1
    guard = steps[names.index("Stop if a newer push superseded this run")]
    assert "if: github.event_name == 'pull_request'" in guard
    assert "PR_NUMBER: ${{ github.event.pull_request.number }}" in guard
    assert 'git ls-remote origin "refs/pull/$PR_NUMBER/head"' in guard
    assert '"$LATEST" != "$HEAD_SHA"' in guard and "exit 1" in guard


def test_verdict_status_pending_first_and_final_last(tool_repo):
    """The `git-cicd verdict` status is set to pending by the first step of
    the first job and to the verdict by the last step of the report job, which
    runs whatever happened before it; no job's check run carries the name."""
    text = generate(tool_repo, base_config())
    jobs = job_blocks(text)
    assert "needs:" not in jobs["decide"]
    decide_steps = jobs["decide"].split("      - name: ")[1:]
    assert decide_steps[0].startswith(
        "Set the git-cicd verdict status to pending\n")
    assert "if: github.event_name == 'pull_request'" in decide_steps[0]
    assert "-f state=pending" in decide_steps[0]
    assert '-f context="git-cicd verdict"' in decide_steps[0]
    report_steps = jobs["verdict"].split("      - name: ")[1:]
    last = report_steps[-1]
    assert last.startswith("Set the git-cicd verdict status\n")
    assert "if: always() && github.event_name == 'pull_request'" in last
    assert "STATE=failure" in last
    assert '-f context="git-cicd verdict"' in last
    assert "--verdict-out=" in report_steps[-2]
    assert "if: always()" in jobs["verdict"].split("    steps:")[0]
    assert not re.search(r"(?m)^    name: git-cicd verdict$", text)


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
