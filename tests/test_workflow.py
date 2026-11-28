"""Tests for generating and verifying the GitHub Actions workflows."""

import re

import pytest

from tests.conftest import ROOT, git_cicd

WORKFLOW = ".github/workflows/git-cicd-open.yml"
MERGE = ".github/workflows/git-cicd-merge.yml"
MANUAL = ".github/workflows/git-cicd-manual.yml"
CRON = ".github/workflows/git-cicd-cron.yml"
TEMPLATES = ROOT / "templates" / "workflows"
LEGACY = ".github/workflows/git-cicd.yml"
TEMPLATE = ROOT / "templates" / "workflows" / "open.yml"
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
    assert text.startswith(f"# {WORKFLOW} - GENERATED")
    assert "\nname: Open\n" in text
    assert f"python3 {TOOL} decide" in text
    assert "__TOOL__" not in text and "__SCHEDULE__" not in text
    assert "schedule:" not in text


@pytest.mark.parametrize("path,count", [(WORKFLOW, 8), (MERGE, 8),
                                        (MANUAL, 8)])
def test_no_expressions_inside_run_blocks(tool_repo, path, count):
    generate(tool_repo, base_config())
    blocks = run_blocks((tool_repo.path / path).read_text())
    assert len(blocks) == count
    for block in blocks:
        assert "${{" not in block, block


def test_template_run_blocks_have_no_expressions():
    templates = sorted(TEMPLATES.glob("*.yml"))
    assert len(templates) == len(git_cicd.GENERATED_TRIGGERS)
    for template in templates:
        blocks = run_blocks(template.read_text())
        assert blocks, template
        for block in blocks:
            assert "${{" not in block, (template, block)


def test_workflow_contract(tool_repo):
    text = generate(tool_repo, base_config())
    assert "  pull_request:\n    types: [opened, synchronize, reopened]\n" in text
    assert "permissions:\n  contents: read\n" in text
    assert "name: Report / git-cicd:report" in text
    assert "if: always()" in text
    assert "schedule" not in text.split("\nname: Open\n", 1)[1]
    assert "github.event_name" not in text
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
    """In the `open` workflow the token may write commit statuses, and
    nothing else: contents stay read-only, the two jobs that post the status
    get `statuses: write`, and the job that runs the config's scripts gets no
    permission of its own (only the read-only top level)."""
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
    "      group: git-cicd-open-${{ github.event.pull_request.number }}-"
    "${{ matrix.job }}\n"
    "      cancel-in-progress: true\n")


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
    assert "PR_NUMBER: ${{ github.event.pull_request.number }}" in guard
    assert 'git ls-remote origin "refs/pull/$PR_NUMBER/head"' in guard
    assert '"$LATEST" != "$HEAD_SHA"' in guard and "exit 1" in guard


def test_verdict_status_pending_first_and_final_last(tool_repo):
    """The `Verdict / git-cicd:verdict` status is set to pending by the first
    step of
    the first job and to the verdict by the last step of the report job, which
    runs whatever happened before it; no job's check run carries the name."""
    text = generate(tool_repo, base_config())
    jobs = job_blocks(text)
    assert "needs:" not in jobs["decide"]
    decide_steps = jobs["decide"].split("      - name: ")[1:]
    assert decide_steps[0].startswith(
        "Set the Verdict / git-cicd:verdict status to pending\n")
    assert "if:" not in decide_steps[0]
    assert "-f state=pending" in decide_steps[0]
    assert '-f context="Verdict / git-cicd:verdict"' in decide_steps[0]
    report_steps = jobs["verdict"].split("      - name: ")[1:]
    last = report_steps[-1]
    assert last.startswith("Set the Verdict / git-cicd:verdict status\n")
    assert "        if: always()\n" in last
    assert "STATE=failure" in last
    assert '-f context="Verdict / git-cicd:verdict"' in last
    assert "--verdict-out=" in report_steps[-2]
    assert "if: always()" in jobs["verdict"].split("    steps:")[0]
    assert not re.search(r"(?m)^    name: .*[Vv]erdict", text)
    assert text.count('context="Verdict / git-cicd:verdict"') == 2
    assert git_cicd.VERDICT_STATUS == "Verdict / git-cicd:verdict"
    # the old names are gone from the file
    for old in ("name: git-cicd\n", "name: git-cicd decide",
                "name: git-cicd report", "context=\"git-cicd", "git-cicd verdict",
                "`git-cicd decide`", "`git-cicd report`"):
        assert old not in text, old


def generated_files(repo):
    return {p.name: p.read_text()
            for p in (repo.path / ".github" / "workflows").glob("*.yml")}


def test_non_cron_differences_generate_identical_files(tool_repo):
    generate(tool_repo, base_config())
    files_a = generated_files(tool_repo)
    b_config = {"jobs": {
        "other": {"on": ["open", "merge"], "branches": ["plan/**", "main"],
                  "paths": ["lib/**"], "steps": [["ci/other.sh", "-x"]],
                  "blocking": False, "manual": False},
    }, "needs_nothing": [".pearls/**", "*.md"], "max_parallel": 7}
    generate(tool_repo, b_config)
    assert generated_files(tool_repo) == files_a
    assert sorted(files_a) == ["git-cicd-manual.yml", "git-cicd-merge.yml",
                               "git-cicd-open.yml"]


def test_cron_jobs_do_not_change_the_open_file(tool_repo):
    """Every generated file is fixed text except the cron workflow's
    schedule block: cron jobs leave the `open` file as it is."""
    a = generate(tool_repo, base_config())
    config = base_config()
    config["jobs"]["nightly"] = {"on": ["cron"], "branches": ["main"],
                                 "cron": "0 3 * * *", "steps": ["ci/test.sh"]}
    b = generate(tool_repo, config)
    assert a == b
    assert "schedule" not in b.split("\nname: Open\n", 1)[1]


def test_schedule_block_fills_only_a_cron_template(tool_repo):
    """The schedule block, one entry per distinct cron expression, is what
    the cron workflow's template will hold (`__SCHEDULE__`); a template
    without the marker, like `open`'s, is unchanged by the config."""
    tool_repo.config(base_config())
    config = base_config()
    config["jobs"]["nightly"] = {"on": ["cron"], "branches": ["main"],
                                 "cron": "0 3 * * *", "steps": ["ci/test.sh"]}
    config["jobs"]["weekly"] = {"on": ["cron", "open"], "branches": ["main"],
                                "cron": "0 9 * * 1", "steps": ["ci/test.sh"]}
    config["jobs"]["again"] = {"on": ["cron"], "branches": ["dev"],
                               "cron": "0 3 * * *", "steps": ["ci/test.sh"]}
    tool_repo.config(config)
    loaded = git_cicd.load_config(str(tool_repo.path))
    cron = "name: Cron\non:\n__SCHEDULE__\njobs: {}\n"
    assert git_cicd.render_workflow(loaded, TOOL, cron) == (
        'name: Cron\non:\n  schedule:\n    - cron: "0 3 * * *"\n'
        '    - cron: "0 9 * * 1"\njobs: {}\n')
    open_text = TEMPLATE.read_text()
    assert git_cicd.render_workflow(loaded, TOOL, open_text) == \
        open_text.replace("__TOOL__", TOOL)


def test_generate_is_deterministic(tool_repo):
    a = generate(tool_repo, base_config())
    b = generate(tool_repo, base_config())
    assert a == b


def test_verify_passes_after_generate(tool_repo):
    generate(tool_repo, base_config())
    result = tool_repo.run("verify")
    assert result.returncode == 0, result.stdout
    assert "workflows match config" in result.stdout


def test_verify_fails_after_hand_edit(tool_repo):
    generate(tool_repo, base_config())
    path = tool_repo.path / WORKFLOW
    path.write_text(path.read_text().replace("fail-fast: false",
                                             "fail-fast: true"))
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert "-      fail-fast: true" in result.stdout
    assert "+      fail-fast: false" in result.stdout
    assert (f"the workflows do not match the config; run: {TOOL} generate "
            f"and commit {WORKFLOW}") in result.stdout
    assert LEGACY not in result.stdout


def test_generate_removes_the_old_single_file(tool_repo):
    """A repository from before the per-trigger files: generate writes the
    new file and removes the old one."""
    tool_repo.config(base_config())
    (tool_repo.path / LEGACY).parent.mkdir(parents=True)
    (tool_repo.path / LEGACY).write_text("name: git-cicd\n")
    result = tool_repo.run("generate")
    assert result.returncode == 0, result.stderr
    assert f"wrote {WORKFLOW}" in result.stdout
    assert f"removed {LEGACY}" in result.stdout
    assert not (tool_repo.path / LEGACY).exists()
    assert (tool_repo.path / WORKFLOW).is_file()
    assert tool_repo.run("verify").returncode == 0
    # with nothing to remove, generate says nothing about it
    result = tool_repo.run("generate")
    assert "removed" not in result.stdout


def test_verify_fails_while_the_old_file_is_there(tool_repo):
    generate(tool_repo, base_config())
    (tool_repo.path / LEGACY).write_text("name: git-cicd\n")
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert f"{LEGACY} is still there" in result.stdout
    assert (f"run: {TOOL} generate and commit {WORKFLOW}, {MERGE}, {MANUAL} "
            f"and the removal of {LEGACY}") in result.stdout


def test_generated_files_are_named_for_their_triggers():
    """One workflow per trigger, its name the trigger's word and its file
    fixed for good; every trigger is generated (cron when a job has cron in
    on)."""
    assert git_cicd.WORKFLOWS == {
        "open": ("Open", ".github/workflows/git-cicd-open.yml"),
        "merge": ("Merge", ".github/workflows/git-cicd-merge.yml"),
        "cron": ("Cron", ".github/workflows/git-cicd-cron.yml"),
        "manual": ("Manual", ".github/workflows/git-cicd-manual.yml"),
    }
    assert git_cicd.GENERATED_TRIGGERS == ("open", "merge", "cron", "manual")
    templates = sorted(p.stem for p in (ROOT / "templates" / "workflows")
                       .glob("*.yml"))
    assert templates == sorted(git_cicd.GENERATED_TRIGGERS)
    for trigger in git_cicd.GENERATED_TRIGGERS:
        name, path = git_cicd.WORKFLOWS[trigger]
        text = (ROOT / "templates" / "workflows" / f"{trigger}.yml").read_text()
        assert text.startswith(f"# {path} - GENERATED")
        assert f"\nname: {name}\n" in text


def test_this_repository_is_migrated():
    assert not (ROOT / LEGACY).exists()
    config = git_cicd.load_config(str(ROOT))
    rendered = git_cicd.render_workflows(config, "git-cicd")
    assert list(rendered) == [WORKFLOW, MERGE, CRON, MANUAL]
    for path, text in rendered.items():
        assert (ROOT / path).read_text() == text, path


def test_open_file_is_unchanged_from_the_committed_copy(tool_repo):
    """The open workflow stays byte-identical as the other triggers are
    built: the committed copy in this repository is what the template
    renders, and the template is untouched."""
    committed = (ROOT / WORKFLOW).read_text()
    text = generate(tool_repo, base_config())
    assert text == committed.replace("python3 git-cicd ", f"python3 {TOOL} ") \
        .replace("#   git-cicd generate", f"#   {TOOL} generate")
    assert TEMPLATE.read_text().replace("__TOOL__", "git-cicd") == committed


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
    assert ok and message == "workflows match config"
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


def test_template_documents_the_triggers():
    head = TEMPLATE.read_text().split("\nname: Open\n")[0]
    for trigger, (name, path) in git_cicd.WORKFLOWS.items():
        assert re.search(rf"(?m)^#   {trigger} +{name} +{re.escape(path)} ",
                         head), trigger
    prose = " ".join(line.lstrip("# ") for line in head.splitlines())
    assert ("Every generated file is fixed text except the cron workflow's "
            "schedule block") in " ".join(prose.split())
    assert "Overlap rule for `open`: a newer push supersedes" in head


ROW_NAME = ("    name: ${{ fromJSON(needs.decide.outputs.names)[matrix.job] }}"
            " / ${{ github.event.repository.name }}:${{ matrix.job }}\n")


def test_run_row_is_display_name_repo_and_job(tool_repo):
    """The row is `<name> / <repo>:<job>`, from the decide job's outputs and
    the event, never from the config text, and carries no version."""
    text = generate(tool_repo, base_config())
    jobs = job_blocks(text)
    assert ROW_NAME in jobs["run"]
    assert "      names: ${{ steps.decide.outputs.names }}\n" in jobs["decide"]
    assert "    name: Decide / git-cicd:decide\n" in jobs["decide"]
    assert "    name: Report / git-cicd:report\n" in jobs["verdict"]
    assert "version" not in ROW_NAME


def test_display_names_do_not_change_the_file(tool_repo):
    a = generate(tool_repo, base_config())
    config = base_config()
    config["jobs"]["test"]["name"] = "Unit Tests"
    config["jobs"]["release"]["name"] = "Release `$(x)` \"q\""
    b = generate(tool_repo, config)
    assert a == b
    assert "Unit Tests" not in b


# ── merge: the Merge workflow ───────────────────────────────────────────────

def generate_merge(repo):
    generate(repo, base_config())
    return (repo.path / MERGE).read_text()


def steps_of(job_text):
    return job_text.split("      - name: ")[1:]


def test_merge_file_is_written_with_the_push_event(tool_repo):
    text = generate_merge(tool_repo)
    assert text.startswith(f"# {MERGE} - GENERATED")
    assert "\nname: Merge\n" in text
    assert "\non:\n  push:\n    branches: ['**']\n\npermissions:" in text
    assert "tags" not in text.split("\non:\n", 1)[1].split("permissions:")[0]
    assert f"python3 {TOOL} decide --trigger=merge" in text
    assert f"python3 {TOOL} run-job \"$JOB\" --trigger=merge" in text
    assert f"python3 {TOOL} report --trigger=merge" in text
    assert "__TOOL__" not in text and "__SCHEDULE__" not in text
    # the facts of a push, through env: only
    assert "BASE: ${{ github.event.before }}" in text
    assert "HEAD_SHA: ${{ github.sha }}" in text
    assert "BRANCH: ${{ github.ref_name }}" in text
    assert '--target="$BRANCH"' in text and '--source="$BRANCH"' in text


def test_merge_skips_a_branch_deletion(tool_repo):
    jobs = job_blocks(generate_merge(tool_repo))
    assert "    if: ${{ !github.event.deleted }}\n" in jobs["decide"]
    assert "    if: always() && !github.event.deleted\n" in jobs["verdict"]
    assert "    needs: decide\n" in jobs["run"]


def test_merge_has_no_concurrency(tool_repo):
    text = generate_merge(tool_repo)
    assert "concurrency" not in text.split("\nname: Merge\n", 1)[1]
    assert "cancel-in-progress" not in text.split("\nname: Merge\n", 1)[1]


def test_merge_queue_waits_for_earlier_runs_on_the_branch(tool_repo):
    jobs = job_blocks(generate_merge(tool_repo))
    steps = steps_of(jobs["decide"])
    names = [s.split("\n", 1)[0] for s in steps]
    assert names[:4] == [
        "Set the Verdict / git-cicd:verdict status to pending",
        "Wait for earlier Merge and Manual runs on this branch",
        "Checkout repository", "Decide which jobs the change needs"]
    queue = steps[1]
    assert '"repos/$GITHUB_REPOSITORY/actions/runs"' in queue
    assert '-f branch="$BRANCH"' in queue
    assert 'select(.status != "completed")' in queue
    assert '.github/workflows/git-cicd-merge.yml' in queue
    assert '.github/workflows/git-cicd-manual.yml' in queue
    assert "select(.id < (env.GITHUB_RUN_ID | tonumber))" in queue
    assert "actions: read" in jobs["decide"]


def test_merge_write_permissions_only_on_the_run_job(tool_repo):
    text = generate_merge(tool_repo)
    top = text.split("\njobs:\n", 1)[0]
    assert top.endswith("\npermissions:\n  contents: read\n")
    jobs = job_blocks(text)
    assert set(jobs) == {"decide", "run", "verdict"}
    assert ("    permissions:\n      contents: write\n"
            "      pull-requests: write\n") in jobs["run"]
    for name in ("decide", "verdict"):
        perms = re.findall(r"^      ([a-z-]+): (read|write)$",
                           jobs[name].split("    steps:")[0], re.M)
        assert ("statuses", "write") in perms
        assert [p for p, level in perms if level == "write"] == ["statuses"]
        assert ("pull-requests", "read") in perms
    writes = re.findall(r"^\s*([a-z-]+):\s*write\s*$", text, re.M)
    assert sorted(writes) == ["contents", "pull-requests", "statuses",
                              "statuses"]
    assert "write-all" not in text


def test_merge_run_job_has_full_history_and_tags(tool_repo):
    run = job_blocks(generate_merge(tool_repo))["run"]
    checkout = steps_of(run)[0]
    assert "fetch-depth: 0" in checkout and "fetch-tags: true" in checkout
    # the landed commit (github.sha) on its branch, so a release can push
    assert "ref:" not in checkout
    assert "--setup --result=" in run


def test_merge_verdict_status_pending_first_and_final_last(tool_repo):
    text = generate_merge(tool_repo)
    jobs = job_blocks(text)
    first = steps_of(jobs["decide"])[0]
    assert first.startswith(
        "Set the Verdict / git-cicd:verdict status to pending\n")
    assert "-f state=pending" in first
    assert 'statuses/$HEAD_SHA"' in first
    last = steps_of(jobs["verdict"])[-1]
    assert last.startswith("Set the Verdict / git-cicd:verdict status\n")
    assert "        if: always()\n" in last
    assert "STATE=failure" in last
    assert "--verdict-out=" in steps_of(jobs["verdict"])[-2]
    assert text.count('context="Verdict / git-cicd:verdict"') == 2
    assert text.count("HEAD_SHA: ${{ github.sha }}") >= 3


def test_merge_status_only_without_an_open_pull_request(tool_repo):
    """A pull request's Open run owns the status on its head commit: the
    Merge run posts neither pending nor final when an open pull request has
    the landed commit as its head."""
    jobs = job_blocks(generate_merge(tool_repo))
    for step in (steps_of(jobs["decide"])[0], steps_of(jobs["verdict"])[-1]):
        guard, post = step.split("--method POST", 1)
        assert '"repos/$GITHUB_REPOSITORY/commits/$HEAD_SHA/pulls"' in guard
        assert 'select(.state == "open" and .head.sha == env.HEAD_SHA)' \
            in guard
        assert 'if [ "$OPEN_PRS" != "0" ]; then' in guard
        assert "exit 0" in guard


def test_merge_rows_and_actions(tool_repo):
    text = generate_merge(tool_repo)
    jobs = job_blocks(text)
    assert ROW_NAME in jobs["run"]
    assert "    name: Decide / git-cicd:decide\n" in jobs["decide"]
    assert "    name: Report / git-cicd:report\n" in jobs["verdict"]
    uses = re.findall(r"(?m)^\s*(?:- )?uses:\s*(\S+)", text)
    assert uses and all(re.fullmatch(
        r"actions/(checkout|upload-artifact|download-artifact)@v4", u)
        for u in uses), uses


def test_verify_fails_on_a_hand_edit_of_the_merge_file(tool_repo):
    text = generate_merge(tool_repo)
    (tool_repo.path / MERGE).write_text(text.replace("fetch-tags: true",
                                                     "fetch-tags: false"))
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert "+          fetch-tags: true" in result.stdout
    assert f"{MERGE} (committed)" in result.stdout


def test_verify_fails_when_the_merge_file_is_missing(tool_repo):
    generate_merge(tool_repo)
    (tool_repo.path / MERGE).unlink()
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert f"{MERGE} is missing" in result.stdout


# ── manual: the Manual workflow ─────────────────────────────────────────────

def generate_manual(repo):
    generate(repo, base_config())
    return (repo.path / MANUAL).read_text()


def test_manual_file_is_written_with_the_dispatch_and_job_input(tool_repo):
    text = generate_manual(tool_repo)
    assert text.startswith(f"# {MANUAL} - GENERATED")
    assert "\nname: Manual\n" in text
    on = text.split("\non:\n", 1)[1].split("\npermissions:")[0]
    assert on.startswith("  workflow_dispatch:\n    inputs:\n      job:\n")
    assert "        required: true\n        type: string\n" in on
    assert "config job to run" in on
    assert "push" not in on and "schedule" not in on
    assert "JOB: ${{ inputs.job }}" in text
    assert (f'python3 {TOOL} decide --trigger=manual --job="$JOB"') in text
    assert f"python3 {TOOL} run-job \"$JOB\" --trigger=manual" in text
    assert f"python3 {TOOL} report --trigger=manual" in text
    assert "__TOOL__" not in text
    # the input appears only in env: entries
    for block in run_blocks(text):
        assert "inputs." not in block


def test_manual_permissions_queue_and_checkout(tool_repo):
    text = generate_manual(tool_repo)
    jobs = job_blocks(text)
    assert set(jobs) == {"decide", "run", "verdict"}
    assert text.split("\njobs:\n", 1)[0].endswith(
        "\npermissions:\n  contents: read\n")
    assert ("    permissions:\n      contents: write\n"
            "      pull-requests: write\n") in jobs["run"]
    writes = re.findall(r"^\s*([a-z-]+):\s*write\s*$", text, re.M)
    assert sorted(writes) == ["contents", "pull-requests", "statuses",
                              "statuses"]
    assert "concurrency" not in text.split("\nname: Manual\n", 1)[1]
    merge = job_blocks(generate_merge(tool_repo))
    queue = steps_of(jobs["decide"])[1]
    assert queue.startswith("Wait for earlier Merge and Manual runs")
    assert queue == steps_of(merge["decide"])[1]
    checkout = steps_of(jobs["run"])[0]
    assert "fetch-depth: 0" in checkout and "fetch-tags: true" in checkout


def test_manual_verdict_pending_first_and_final_last(tool_repo):
    jobs = job_blocks(generate_manual(tool_repo))
    merge = job_blocks(generate_merge(tool_repo))
    first = steps_of(jobs["decide"])[0]
    last = steps_of(jobs["verdict"])[-1]
    assert first.startswith(
        "Set the Verdict / git-cicd:verdict status to pending\n")
    assert last.startswith("Set the Verdict / git-cicd:verdict status\n")
    assert "        if: always()\n" in last
    # the same no-open-pull-request rule as Merge
    assert first == steps_of(merge["decide"])[0]
    assert last == steps_of(merge["verdict"])[-1]
    assert "    if: always()\n" in jobs["verdict"]


def test_verify_fails_on_a_hand_edit_of_the_manual_file(tool_repo):
    text = generate_manual(tool_repo)
    (tool_repo.path / MANUAL).write_text(text.replace("required: true",
                                                      "required: false"))
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert f"{MANUAL} (committed)" in result.stdout


def test_manual_file_carries_inputs_as_json_through_env(tool_repo):
    text = generate_manual(tool_repo)
    on = text.split("\non:\n", 1)[1].split("\npermissions:")[0]
    assert ("      inputs:\n        description: 'The job''s declared inputs as "
            "a JSON object of strings") in on
    assert "        required: false\n        default: ''\n        type: string\n" \
        in on
    jobs = job_blocks(text)
    entry = "          CICD_MANUAL_INPUTS: ${{ inputs.inputs }}\n"
    assert entry in steps_of(jobs["decide"])[3]
    assert entry in steps_of(jobs["run"])[1]
    assert text.count("CICD_MANUAL_INPUTS") == text.count(entry) + \
        text.split("\nname: Manual\n")[0].count("CICD_MANUAL_INPUTS")
    for block in run_blocks(text):
        assert "${{" not in block and "CICD_MANUAL_INPUTS" not in block


def test_declared_inputs_do_not_change_the_files(tool_repo):
    generate(tool_repo, base_config())
    files_a = generated_files(tool_repo)
    config = base_config()
    config["jobs"]["release"]["inputs"] = {
        "bump_type": {"choices": ["patch", "minor"], "default": "patch"}}
    generate(tool_repo, config)
    assert generated_files(tool_repo) == files_a


# ── cron: the Cron workflow ─────────────────────────────────────────────────

def cron_config():
    config = base_config()
    config["jobs"]["nightly"] = {"on": ["cron"], "branches": ["main", "dev"],
                                 "cron": "0 3 * * *", "steps": ["ci/test.sh"]}
    config["jobs"]["weekly"] = {"on": ["cron", "open"], "branches": ["main"],
                                "cron": "0 9 * * 1", "steps": ["ci/test.sh"]}
    config["jobs"]["again"] = {"on": ["cron"], "branches": ["dev"],
                               "cron": "0 3 * * *", "steps": ["ci/other.sh"]}
    return config


def generate_cron(repo, config=None):
    generate(repo, config or cron_config())
    return (repo.path / CRON).read_text()


def test_cron_file_has_one_schedule_entry_per_distinct_expression(tool_repo):
    text = generate_cron(tool_repo)
    assert text.startswith(f"# {CRON} - GENERATED")
    assert "\nname: Cron\n" in text
    assert ('\non:\n  schedule:\n    - cron: "0 3 * * *"\n'
            '    - cron: "0 9 * * 1"\n\npermissions:') in text
    assert "__SCHEDULE__" not in text and "__TOOL__" not in text
    assert "CRON: ${{ github.event.schedule }}" in text
    assert f'python3 {TOOL} decide --trigger=cron --cron="$CRON"' in text
    assert f"python3 {TOOL} report --trigger=cron" in text


def test_cron_file_no_expressions_in_run_blocks(tool_repo):
    blocks = run_blocks(generate_cron(tool_repo))
    assert len(blocks) == 7
    for block in blocks:
        assert "${{" not in block, block


def test_cron_permissions_and_no_queue(tool_repo):
    text = generate_cron(tool_repo)
    jobs = job_blocks(text)
    assert set(jobs) == {"decide", "run", "verdict"}
    assert text.split("\njobs:\n", 1)[0].endswith(
        "\npermissions:\n  contents: read\n")
    assert ("    permissions:\n      contents: write\n"
            "      pull-requests: write\n") in jobs["run"]
    for name in ("decide", "verdict"):
        assert ("    permissions:\n      contents: read\n      statuses: write\n"
                "      pull-requests: read\n") in jobs[name]
    writes = re.findall(r"^\s*([a-z-]+):\s*write\s*$", text, re.M)
    assert sorted(writes) == ["contents", "pull-requests", "statuses",
                              "statuses"]
    body = text.split("\nname: Cron\n", 1)[1]
    assert "concurrency" not in body and "actions/runs\"" not in body
    checkout = steps_of(jobs["run"])[0]
    assert "fetch-depth: 0" in checkout and "fetch-tags: true" in checkout
    assert "ref: ${{ matrix.entry.sha }}" in checkout
    assert "entry: ${{ fromJSON(needs.decide.outputs.runs) }}" in jobs["run"]
    assert "name: git-cicd-result-${{ matrix.entry.key }}" in jobs["run"]


def test_cron_verdict_per_branch_pending_then_final_last(tool_repo):
    jobs = job_blocks(generate_cron(tool_repo))
    names = [s.split("\n", 1)[0] for s in steps_of(jobs["decide"])]
    assert names[:3] == ["Checkout repository",
                         "Decide which jobs the schedule needs",
                         "Set the Verdict / git-cicd:verdict status to pending"]
    pending = steps_of(jobs["decide"])[2]
    assert "jq -r '.heads[] | select(. != null)'" in pending
    assert "-f state=pending" in pending
    last = steps_of(jobs["verdict"])[-1]
    assert last.startswith("Set the Verdict / git-cicd:verdict status\n")
    assert "        if: always()\n" in last
    assert "read -r HEAD_SHA STATE DESCRIPTION" in last
    assert "tfailure\\tFAILED - the report did not run to the end" in last
    for step in (pending, last):
        assert 'select(.state == "open" and .head.sha == env.HEAD_SHA)' in step
        assert "continue" in step


def test_no_cron_job_no_cron_file(tool_repo):
    generate(tool_repo, base_config())
    assert not (tool_repo.path / CRON).exists()
    assert tool_repo.run("verify").returncode == 0


def test_generate_removes_a_cron_file_without_cron_jobs(tool_repo):
    generate_cron(tool_repo)
    tool_repo.config(base_config())
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert f"{CRON} is still there, but no job has cron in on" in result.stdout
    assert f"and the removal of {CRON}" in result.stdout
    result = tool_repo.run("generate")
    assert result.returncode == 0
    assert f"removed {CRON} (no job has cron in on" in result.stdout
    assert not (tool_repo.path / CRON).exists()
    assert tool_repo.run("verify").returncode == 0


def test_stale_schedule_block_fails_verify(tool_repo):
    generate_cron(tool_repo)
    config = cron_config()
    config["jobs"]["weekly"]["cron"] = "0 10 * * 1"
    tool_repo.config(config)
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert '-    - cron: "0 9 * * 1"' in result.stdout
    assert '+    - cron: "0 10 * * 1"' in result.stdout


def test_verify_fails_on_a_hand_edit_of_the_cron_file(tool_repo):
    text = generate_cron(tool_repo)
    (tool_repo.path / CRON).write_text(text.replace("fetch-tags: true", ""))
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert f"{CRON} (committed)" in result.stdout


def test_cron_jobs_change_only_the_cron_file(tool_repo):
    generate(tool_repo, base_config())
    before = generated_files(tool_repo)
    generate_cron(tool_repo)
    after = generated_files(tool_repo)
    assert sorted(after) == sorted(list(before) + ["git-cicd-cron.yml"])
    for name, text in before.items():
        assert after[name] == text


def test_generate_refuses_a_tool_path_the_workflow_cannot_hold(repo):
    repo.config({"jobs": {}})
    repo.install_tool("tools/my cicd")
    result = repo.run("generate")
    assert result.returncode == 2
    assert result.stderr.strip() == (
        "git-cicd: the tool path 'tools/my cicd/git-cicd' contains characters "
        "the generated workflow does not accept")


def test_generate_without_templates_names_the_missing_template(repo):
    repo.config({"jobs": {}})
    repo.install_tool()
    template = repo.tool.parent / "templates" / "workflows" / "open.yml"
    template.unlink()
    result = repo.run("generate")
    assert result.returncode == 2
    assert result.stderr.strip().startswith(
        f"git-cicd: cannot read the workflow template {template}: ")
    assert "No such file or directory" in result.stderr
