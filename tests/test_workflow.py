"""Tests for generating and verifying the GitHub Actions workflows."""

import json
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


def bare(template, tool=TOOL, branches="['main']"):
    """A template as a config without permission groups renders it: the
    group placeholders empty, the Merge trigger's branches and the tool path
    filled in."""
    template = template.replace("__BRANCHES__", branches)
    for mark in ("__GROUP_OUTPUTS__\n", "__GROUP_JOBS__\n",
                 "__GROUP_NEEDS__"):
        template = template.replace(mark, "")
    return template.replace("__TOOL__", tool)


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
                                        (MANUAL, 9)])
def test_no_expressions_inside_run_blocks(tool_repo, path, count):
    generate(tool_repo, base_config())
    blocks = run_blocks((tool_repo.path / path).read_text())
    assert len(blocks) == count
    for block in blocks:
        assert "${{" not in block, block


def secret_lines(matrix_job):
    """The one env line per documented secret that every run step carries:
    the secret only for a matrix entry whose job declares it."""
    return [f"          {n}: ${{{{ contains(fromJSON(needs.decide.outputs."
            f"secrets)[{matrix_job}], '{n}') && secrets.{n} || '' }}}}"
            for n in git_cicd.DECLARABLE_SECRETS]


@pytest.mark.parametrize("trigger", git_cicd.GENERATED_TRIGGERS)
def test_run_step_selects_only_declared_secrets(trigger):
    """Every run job's step env carries exactly the selection lines for the
    documented set; no template reads `secrets.` anywhere else."""
    text = (TEMPLATES / f"{trigger}.yml").read_text()
    matrix_job = "matrix.entry.job" if trigger == "cron" else "matrix.job"
    lines = text.splitlines()
    expected = secret_lines(matrix_job)
    for line in expected:
        assert lines.count(line) == 1, line
    used = [line for line in lines if "secrets." in line]
    assert used and all(line in expected for line in used), used
    assert "secrets: ${{ steps.decide.outputs.secrets }}" in text
    # the step's env lines come right after GITHUB_TOKEN, in the set's order
    i = lines.index("          GITHUB_TOKEN: ${{ github.token }}")
    assert lines[i + 1:i + 1 + len(expected)] == expected


def test_secret_declarations_write_nothing_into_the_workflows(tool_repo):
    """A declaration changes no generated file: the names reach the workflow
    as decide's output, never as text from the config."""
    plain = {t: generate(tool_repo, base_config()) for t in ("open",)}
    texts = {}
    for path in (WORKFLOW, MERGE, MANUAL):
        texts[path] = (tool_repo.path / path).read_text()
    config = base_config()
    config["jobs"]["test"]["secrets"] = ["CICD_READ_TOKEN"]
    config["jobs"]["release"]["secrets"] = ["CICD_WRITE_TOKEN", "VENDOR_PAT"]
    assert generate(tool_repo, config) == plain["open"]
    for path in (MERGE, MANUAL):
        assert (tool_repo.path / path).read_text() == texts[path]


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
    # a secret reaches the step only through the selection lines
    for line in text.splitlines():
        if "secrets." in line:
            assert line in secret_lines("matrix.job"), line
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
        "other": {"on": ["open", "merge"], "branches": ["main"],
                  "paths": ["lib/**"], "steps": [["ci/other.sh", "-x"]],
                  "blocking": False, "name": "Something Else"},
        "release": {"on": [], "branches": ["main"], "steps": ["ci/bump.sh"]},
    }, "needs_nothing": [".pearls/**", "*.md"], "max_parallel": 7}
    generate(tool_repo, b_config)
    files_b = generated_files(tool_repo)
    assert sorted(files_a) == ["git-cicd-manual.yml", "git-cicd-merge.yml",
                               "git-cicd-open.yml"]
    assert files_b["git-cicd-open.yml"] == files_a["git-cicd-open.yml"]
    assert files_b["git-cicd-merge.yml"] == files_a["git-cicd-merge.yml"]
    # the Manual form lists the manual jobs: both configs have two
    assert files_b["git-cicd-manual.yml"] == files_a[
        "git-cicd-manual.yml"].replace('- "Test / repo:test"',
                                       '- "Something Else / repo:other"')


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
        bare(open_text)


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
    assert config["repository"] == "git-cicd"
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
    assert bare(TEMPLATE.read_text(), "git-cicd") == committed


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
    assert "\non:\n  push:\n    branches: ['main']\n\npermissions:" in text
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


def merge_trigger(text):
    return text.split("\non:\n  push:\n    branches: ", 1)[1].split("\n")[0]


def merge_config(*branch_lists, extra=None):
    jobs = {f"m{n}": {"on": ["merge"], "branches": list(b),
                      "steps": ["ci/bump.sh"]}
            for n, b in enumerate(branch_lists)}
    jobs.update(extra or {})
    return {"jobs": jobs}


def test_merge_trigger_is_the_branches_of_one_merge_job(tool_repo):
    tool_repo.config(base_config())
    result = tool_repo.run("generate")
    assert result.returncode == 0, result.stderr
    assert "note:" not in result.stdout
    assert merge_trigger((tool_repo.path / MERGE).read_text()) == "['main']"
    assert tool_repo.run("verify").returncode == 0


def test_merge_trigger_is_the_union_of_merge_jobs_in_config_order(tool_repo):
    """Two merge jobs on different branches: their branches in config order,
    each once; a job not on merge adds nothing."""
    config = merge_config(
        ["main", "release/*"], ["release/*", "dev", "main"],
        extra={"t": {"on": ["open"], "branches": ["feature/**"],
                     "steps": ["ci/test.sh"]}})
    tool_repo.config(config)
    result = tool_repo.run("generate")
    assert result.returncode == 0, result.stderr
    assert "note:" not in result.stdout
    assert merge_trigger((tool_repo.path / MERGE).read_text()) == \
        "['main', 'release/*', 'dev']"


def test_merge_trigger_change_fails_verify(tool_repo):
    generate(tool_repo, base_config())
    tool_repo.config(merge_config(["main", "dev"]))
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert "+    branches: ['main', 'dev']" in result.stdout


# Patterns a GitHub branch filter reads the same way as the config.
PASSED_THROUGH = ["main", "release/v1.2", "release/*", "*", "**", "plan/**",
                  "a**b", "x-*/y", "feature_*.final"]
# Patterns it reads differently, one per kind: the trigger falls back.
FALLS_BACK = ["release/v?", "c++", "rel[ab]", "x]", "!main", "a\\b",
              "**/main", "plan/**/x", "a***"]


@pytest.mark.parametrize("pattern", PASSED_THROUGH)
def test_a_pattern_a_branch_filter_reads_alike_is_passed_through(tool_repo,
                                                                  pattern):
    tool_repo.config(merge_config([pattern]))
    result = tool_repo.run("generate")
    assert result.returncode == 0, result.stderr
    assert "note:" not in result.stdout
    assert merge_trigger((tool_repo.path / MERGE).read_text()) == \
        f"['{pattern}']"


@pytest.mark.parametrize("pattern", FALLS_BACK)
def test_a_pattern_a_branch_filter_reads_otherwise_falls_back(tool_repo,
                                                               pattern):
    """The whole trigger becomes any branch, and generate says so in one
    line naming the pattern and its job."""
    tool_repo.config(merge_config(["main"], [pattern, "dev"]))
    result = tool_repo.run("generate")
    assert result.returncode == 0, result.stderr
    assert merge_trigger((tool_repo.path / MERGE).read_text()) == "['**']"
    notes = [ln for ln in result.stdout.splitlines() if "note:" in ln]
    assert notes == [
        "note: the Merge workflow starts on a push to any branch ('**'): "
        f"pattern {pattern!r} of job m1 means something else in a GitHub "
        "branch filter; the tool still decides each job against the branch"]
    assert tool_repo.run("verify").returncode == 0


def test_filter_pattern_ok_agrees_with_the_config_matcher():
    """Every passed-through pattern matches what the config's matcher says,
    read as GitHub reads it: `*` any characters but `/`, `**` any."""
    def github(pattern):
        out = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*",
                                                               "[^/]*")
        return re.compile(out + r"\Z")
    names = ["main", "release/v1.2", "release/x", "release/x/y", "plan/a/b",
             "ab", "a/b", "x-1/y", "feature_1.final", "", "dev"]
    for pattern in PASSED_THROUGH:
        assert git_cicd.filter_pattern_ok(pattern), pattern
        for name in names:
            assert git_cicd.match(pattern, name) == bool(
                github(pattern).match(name)), (pattern, name)
    for pattern in FALLS_BACK:
        assert not git_cicd.filter_pattern_ok(pattern), pattern


def test_merge_trigger_quotes_a_single_quote(tool_repo):
    tool_repo.config(merge_config(["it's"]))
    assert tool_repo.run("generate").returncode == 0
    assert merge_trigger((tool_repo.path / MERGE).read_text()) == \
        "['it''s']"


@pytest.mark.parametrize("pattern", ["rel-${{ github.actor }}", "a\tb"])
def test_a_merge_branch_that_cannot_be_written_is_refused(tool_repo,
                                                          pattern):
    tool_repo.config(merge_config([pattern]))
    result = tool_repo.run("validate")
    assert result.returncode != 0
    assert (f"job m0: branches pattern {pattern!r} contains ${{{{ or a "
            "control character") in result.stdout + result.stderr


def test_an_open_job_branch_is_not_written_so_not_refused(tool_repo):
    tool_repo.config({"jobs": {"t": {"on": ["open"], "branches": ["a${{b"],
                                     "steps": ["ci/test.sh"]}}})
    assert tool_repo.run("validate").returncode == 0


def test_no_merge_job_no_merge_file(tool_repo):
    """Without a job on merge no push could need anything, so the Merge
    workflow is not generated; a file left from before is removed and fails
    verify until then."""
    generate(tool_repo, base_config())
    assert (tool_repo.path / MERGE).is_file()
    config = base_config()
    config["jobs"]["release"]["on"] = ["open"]
    tool_repo.config(config)
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert f"{MERGE} is still there, but no job has merge in on" in \
        result.stdout
    result = tool_repo.run("generate")
    assert result.returncode == 0
    assert f"removed {MERGE} (no job has merge in on" in result.stdout
    assert not (tool_repo.path / MERGE).exists()
    assert tool_repo.run("verify").returncode == 0


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
    assert on.startswith(
        '  workflow_dispatch:\n    inputs:\n      job:\n'
        '        description: "The config job to run"\n'
        '        required: true\n        type: choice\n        options:\n'
        '          - "Test / repo:test"\n'
        '          - "Release / repo:release"\n')
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


def test_manual_file_carries_the_form_as_json_through_env(tool_repo):
    text = generate_manual(tool_repo)
    template = (TEMPLATES / "manual.yml").read_text()
    for t in (text, template):
        assert "CICD_MANUAL_INPUTS" not in t and "inputs.inputs" not in t
        assert "\n      inputs:\n" not in t  # no free-text inputs field
    jobs = job_blocks(text)
    entry = "          CICD_MANUAL_FORM: ${{ toJSON(inputs) }}\n"
    assert entry in steps_of(jobs["decide"])[3]
    assert entry in steps_of(jobs["run"])[1]
    header = text.split("\nname: Manual\n")[0]
    assert text.count("CICD_MANUAL_FORM") == 2 + header.count(
        "CICD_MANUAL_FORM")
    for block in run_blocks(text):
        assert "${{" not in block and "CICD_MANUAL_FORM" not in block


HOSTILE = [
    "it's \"quoted\": # not a comment",
    "  $HOME `id` $(id) {{ braces }} ${ x }  ",
    "- a: [b, {c: d}] & *anchor !tag | > %",
]
HOSTILE_LINES = ["two\nlines: x", "\n# leading newline", "back\\slash\t\r"]


def hostile_config():
    return {"jobs": {
        "zz-hostile_job": {
            "on": ["open"], "branches": ["main"], "steps": ["ci/test.sh"],
            "inputs": {
                "first": {"description": HOSTILE[0], "default": HOSTILE[1]},
                "second": {"description": HOSTILE[1],
                           "choices": HOSTILE + HOSTILE_LINES,
                           "default": HOSTILE_LINES[0]},
                "third": {"description": HOSTILE[2],
                          "default": HOSTILE_LINES[1]}}},
        "true": {"on": ["merge"], "branches": ["main"],
                 "steps": ["ci/bump.sh"],
                 "inputs": {"fourth": {"description": HOSTILE[2],
                                       "default": HOSTILE_LINES[2]}}},
        "nightly-hostile": {"on": ["cron"], "branches": ["main"],
                            "cron": "0 3 * * *", "steps": ["ci/test.sh"]},
    }}


def form_fields(text):
    """{field: {key: value}} of the Manual workflow's workflow_dispatch
    inputs, each scalar read with json.loads; asserts every line of the
    block has the shape the generator writes."""
    on = text.split("\non:\n  workflow_dispatch:\n    inputs:\n", 1)[1]
    block = on.split("\npermissions:")[0].rstrip("\n").split("\n")
    fields, field, key = {}, None, None
    for line in block:
        if not line:
            continue
        m = re.fullmatch(r"      ([a-z][a-z0-9_]*):", line)
        if m:
            field = fields.setdefault(m.group(1), {})
            continue
        m = re.fullmatch(r"        (description|default): (\".*\")", line)
        if m:
            field[m.group(1)] = json.loads(m.group(2))
            continue
        m = re.fullmatch(r"        (required): (true|false)", line)
        if m:
            field["required"] = m.group(2) == "true"
            continue
        m = re.fullmatch(r"        type: (choice|string)", line)
        if m:
            field["type"] = m.group(1)
            continue
        if line == "        options:":
            field["options"] = []
            continue
        m = re.fullmatch(r"          - (\".*\")", line)
        assert m, line
        field["options"].append(json.loads(m.group(1)))
    return fields


def test_hostile_declarations_cannot_change_the_files(tool_repo):
    config = hostile_config()
    generate(tool_repo, config)
    files = generated_files(tool_repo)
    fields = form_fields(files["git-cicd-manual.yml"])
    assert list(fields) == ["job", "first", "second", "third", "fourth"]
    assert fields["job"]["options"] == [
        "Zz Hostile Job / repo:zz-hostile_job", "True / repo:true",
        "Nightly Hostile / repo:nightly-hostile"]
    assert fields["first"]["description"] == \
        f"{HOSTILE[0]} (Zz Hostile Job / repo:zz-hostile_job)"
    assert fields["first"]["default"] == HOSTILE[1]
    assert fields["second"]["options"] == HOSTILE + HOSTILE_LINES
    assert fields["second"]["default"] == HOSTILE_LINES[0]
    assert fields["third"]["default"] == HOSTILE_LINES[1]
    assert fields["fourth"]["default"] == HOSTILE_LINES[2]
    # every value stays on its one line
    manual = files["git-cicd-manual.yml"]
    for value in HOSTILE_LINES:
        assert value not in manual
    # the rest of the file is the template's
    form = git_cicd.form_block(git_cicd.load_config(str(tool_repo.path)),
                               "repo")
    assert manual.replace(form, "__FORM__\n", 1) == \
        bare((TEMPLATES / "manual.yml").read_text())
    # no run: block of any generated file holds a value from the config
    values = set(HOSTILE + HOSTILE_LINES) | {"zz-hostile_job",
                                            "nightly-hostile"}
    values |= {v.strip() for v in values}
    assert sorted(files) == ["git-cicd-cron.yml", "git-cicd-manual.yml",
                             "git-cicd-merge.yml", "git-cicd-open.yml"]
    for name, text in files.items():
        for block in run_blocks(text):
            for value in values:
                assert value not in block, (name, value)
                for line in value.split("\n"):
                    assert not line.strip() or line not in block, (name, line)
    assert tool_repo.run("verify").returncode == 0


def test_declared_inputs_change_only_the_manual_form(tool_repo):
    generate(tool_repo, base_config())
    files_a = generated_files(tool_repo)
    config = base_config()
    config["jobs"]["release"]["inputs"] = {
        "bump_type": {"choices": ["patch", "minor"], "default": "patch"}}
    generate(tool_repo, config)
    files_b = generated_files(tool_repo)
    assert sorted(files_b) == sorted(files_a)
    for name in files_a:
        if name != "git-cicd-manual.yml":
            assert files_b[name] == files_a[name], name
    field = ('      bump_type:\n'
             '        description: "(Release / repo:release)"\n'
             '        required: false\n        default: "patch"\n'
             '        type: choice\n        options:\n'
             '          - "patch"\n          - "minor"\n')
    a, b = files_a["git-cicd-manual.yml"], files_b["git-cicd-manual.yml"]
    assert b.count(field) == 1
    assert b.replace(field, "", 1) == a


FORM_CONFIG = {"jobs": {
    "release": {"on": ["merge"], "branches": ["main"], "steps": ["ci/bump.sh"],
                "inputs": {
                    "bump_type": {"description": "Version bump type",
                                  "choices": ["patch", "minor", "major"],
                                  "default": "patch"},
                    "dry_run": {"description": "Only say what would happen",
                                "choices": ["true", "false"],
                                "default": "false"},
                    "note": {"description": "A note"}}},
    "test": {"on": ["open"], "branches": ["**"], "steps": ["ci/test.sh"],
             "manual": False,
             "inputs": {"only": {"description": "Not in the form"},
                        "job": {}}},
    "update": {"on": [], "branches": ["main"], "steps": ["ci/other.sh"],
               "inputs": {
                   "dry_run": {"description": "Ignored: release's is shown",
                               "choices": ["true", "false"],
                               "default": "false"},
                   "vendor": {"default": "all"},
                   "token": {"required": True}}},
}}

FORM = (
    '      job:\n'
    '        description: "The config job to run"\n'
    '        required: true\n'
    '        type: choice\n'
    '        options:\n'
    '          - "Release / repo:release"\n'
    '          - "Update / repo:update"\n'
    '      bump_type:\n'
    '        description: "Version bump type (Release / repo:release)"\n'
    '        required: false\n'
    '        default: "patch"\n'
    '        type: choice\n'
    '        options:\n'
    '          - "patch"\n'
    '          - "minor"\n'
    '          - "major"\n'
    '      dry_run:\n'
    '        description: "Only say what would happen"\n'
    '        required: false\n'
    '        default: "false"\n'
    '        type: choice\n'
    '        options:\n'
    '          - "true"\n'
    '          - "false"\n'
    '      note:\n'
    '        description: "A note (Release / repo:release)"\n'
    '        required: false\n'
    '        type: string\n'
    '      vendor:\n'
    '        description: "(Update / repo:update)"\n'
    '        required: false\n'
    '        default: "all"\n'
    '        type: string\n'
    '      token:\n'
    '        description: "(Update / repo:update)"\n'
    '        required: false\n'
    '        type: string\n')


def test_manual_form_lists_manual_jobs_and_their_inputs(tool_repo):
    generate(tool_repo, FORM_CONFIG)
    text = (tool_repo.path / MANUAL).read_text()
    on = text.split("\non:\n", 1)[1].split("\npermissions:")[0]
    assert on.startswith("  workflow_dispatch:\n    inputs:\n" + FORM)
    assert "only" not in on and "repo:test" not in on
    assert tool_repo.run("verify").returncode == 0


def test_manual_form_names_every_job_of_a_shared_input(tool_repo):
    def job(inputs):
        return {"on": [], "branches": ["main"], "steps": ["ci/test.sh"],
                "inputs": inputs}
    config = {"jobs": {"a": job({"shared": {"description": "S"}, "a": {}}),
                       "b": job({"shared": {"description": "S"}, "b": {}}),
                       "c": job({})}}
    tool_repo.config(config)
    form = git_cicd.form_block(git_cicd.load_config(str(tool_repo.path)), "r")
    assert ('      shared:\n        description: "S (A / r:a, B / r:b)"\n'
            in form)
    assert '      a:\n        description: "(A / r:a)"\n' in form
    del config["jobs"]["c"]
    tool_repo.config(config)
    form = git_cicd.form_block(git_cicd.load_config(str(tool_repo.path)), "r")
    assert '      shared:\n        description: "S"\n' in form


def test_no_manual_job_no_manual_file(tool_repo):
    generate(tool_repo, base_config())
    assert (tool_repo.path / MANUAL).exists()
    config = base_config()
    for job in config["jobs"].values():
        job["manual"] = False
    tool_repo.config(config)
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert (f"{MANUAL} is still there, but no job allows manual runs "
            "(generate removes it)") in result.stdout
    assert f"run: {TOOL} generate and commit" in result.stdout
    assert f"and the removal of {MANUAL}" in result.stdout
    result = tool_repo.run("generate")
    assert result.returncode == 0
    assert f"removed {MANUAL} (no job allows manual runs" in result.stdout
    assert not (tool_repo.path / MANUAL).exists()
    assert tool_repo.run("verify").returncode == 0
    assert sorted(generated_files(tool_repo)) == ["git-cicd-merge.yml",
                                                  "git-cicd-open.yml"]


@pytest.mark.parametrize("change", ["add", "change", "new_job", "not_manual"])
def test_verify_fails_until_the_form_is_regenerated(tool_repo, change):
    generate(tool_repo, FORM_CONFIG)
    config = json.loads(json.dumps(FORM_CONFIG))
    if change == "add":
        config["jobs"]["release"]["inputs"]["extra"] = {}
    elif change == "change":
        config["jobs"]["release"]["inputs"]["bump_type"]["default"] = "minor"
    elif change == "new_job":
        config["jobs"]["another"] = {"on": [], "branches": ["main"],
                                     "steps": ["ci/test.sh"]}
    else:
        config["jobs"]["update"]["manual"] = False
    tool_repo.config(config)
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert f"{MANUAL} (committed)" in result.stdout
    assert f"run: {TOOL} generate and commit {WORKFLOW}" in result.stdout
    assert tool_repo.run("generate").returncode == 0
    assert tool_repo.run("verify").returncode == 0


def test_open_merge_cron_ignore_inputs_and_manual_flags(tool_repo):
    """Only the manual template holds the form: the open, merge and cron
    files are what their templates give, whatever the inputs and flags, and
    this repository's committed copies are what the templates give."""
    config = json.loads(json.dumps(FORM_CONFIG))
    config["jobs"]["nightly"] = {"on": ["cron"], "branches": ["main"],
                                 "cron": "0 3 * * *", "steps": ["ci/test.sh"]}
    tool_repo.config(config)
    loaded = git_cicd.load_config(str(tool_repo.path))
    bare = git_cicd.load_config(str(tool_repo.path))
    for job in bare["jobs"].values():
        job["inputs"] = {}
        job["manual"] = False
    own = git_cicd.load_config(str(ROOT))
    for trigger in ("open", "merge", "cron"):
        template = (TEMPLATES / f"{trigger}.yml").read_text()
        assert "__FORM__" not in template
        assert git_cicd.render_workflow(loaded, TOOL, template) == \
            git_cicd.render_workflow(bare, TOOL, template), trigger
        path = git_cicd.WORKFLOWS[trigger][1]
        assert git_cicd.render_workflow(own, "git-cicd", template) == \
            (ROOT / path).read_text(), path


# ── cron: the Cron workflow ─────────────────────────────────────────────────

def cron_config():
    # not run by hand, so the Manual form is base_config()'s
    config = base_config()
    config["jobs"]["nightly"] = {"on": ["cron"], "branches": ["main", "dev"],
                                 "cron": "0 3 * * *", "steps": ["ci/test.sh"],
                                 "manual": False}
    config["jobs"]["weekly"] = {"on": ["cron", "open"], "branches": ["main"],
                                "cron": "0 9 * * 1", "steps": ["ci/test.sh"],
                                "manual": False}
    config["jobs"]["again"] = {"on": ["cron"], "branches": ["dev"],
                               "cron": "0 3 * * *", "steps": ["ci/other.sh"],
                               "manual": False}
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


# ── a run that needs no job ─────────────────────────────────────────────────

@pytest.mark.parametrize("path,entry", [
    (WORKFLOW, "matrix.job"), (MERGE, "matrix.job"),
    (MANUAL, "matrix.job"), (CRON, "matrix.entry.job")])
def test_run_job_is_never_skipped_and_skips_the_placeholder(tool_repo, path,
                                                            entry):
    """GitHub shows a matrix job skipped by a job-level `if` under its raw
    `name:` expression, so `run` has none: a run that needs no job runs the
    placeholder entry (`decide` never writes an empty matrix), and every
    step of `run` is skipped for it."""
    generate(tool_repo, cron_config())
    text = (tool_repo.path / path).read_text()
    run = job_blocks(text)["run"]
    header = run.split("\n    steps:\n", 1)[0]
    assert not re.search(r"(?m)^    if:", header)
    assert "    needs: decide\n" in header
    skip = f"{entry} != '{git_cicd.NOTHING_JOB}'"
    steps = steps_of(run)
    assert [s.split("\n", 1)[0] for s in steps] == [
        "Checkout repository", "Run job", "Upload result"]
    for step in steps[:2]:
        assert step.split("\n")[1] == f"        if: {skip}"
    assert steps[2].split("\n")[1] == f"        if: always() && {skip}"
    head = text.split("\njobs:\n", 1)[0]
    prose = " ".join(" ".join(
        line.lstrip("# ") for line in head.splitlines()).split())
    assert ("A run that needs no job still runs the `run` job, once, as the "
            "placeholder entry `(nothing)`, whose row is "
            "`Nothing needed / <repo>:(nothing)`") in prose
    # every other row keeps its name
    assert "    name: Decide / git-cicd:decide\n" in text
    assert "    name: Report / git-cicd:report\n" in text
    assert (f"    name: ${{{{ fromJSON(needs.decide.outputs.names)[{entry}] }}}}"
            f" / ${{{{ github.event.repository.name }}}}:${{{{ {entry} }}}}\n") \
        in run


def test_form_block_is_empty_without_manual_jobs():
    config = {"jobs": {"t": {"manual": False, "inputs": {}, "on": ["open"],
                             "cron": None}}}
    assert git_cicd.form_block(config, "r") == ""
    assert git_cicd.rendered_triggers(config) == ["open"]
    assert git_cicd.stale_triggers(config) == ["merge", "cron", "manual"]


# ── the repository's name in the Manual form ────────────────────────────────

def test_form_uses_the_configured_repository_over_origin(tool_repo):
    tool_repo.git("remote", "add", "origin",
                  "https://example.invalid/someone/from-origin.git")
    generate(tool_repo, base_config())
    text = (tool_repo.path / MANUAL).read_text()
    assert '          - "Test / from-origin:test"\n' in text
    generate(tool_repo, base_config(repository="chosen"))
    text = (tool_repo.path / MANUAL).read_text()
    assert '          - "Test / chosen:test"\n' in text
    assert "from-origin" not in text


def test_no_environment_variable_names_the_repository(tool_repo):
    """generate and verify resolve the name the same way with or without
    the platform's variables: a file generated outside CI verifies inside."""
    generate(tool_repo, base_config())
    before = (tool_repo.path / MANUAL).read_text()
    env = {"GITHUB_REPOSITORY": "someone/else", "GITHUB_ACTIONS": "true",
           "CI": "true"}
    result = tool_repo.run("verify", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert tool_repo.run("generate", env=env).returncode == 0
    assert (tool_repo.path / MANUAL).read_text() == before
    assert "/ else:" not in before and "/ repo:test" in before


def test_verify_says_when_only_the_repository_name_differs(tool_repo):
    generate(tool_repo, base_config())
    tool_repo.git("remote", "add", "origin", "git@example.invalid:o/moved.git")
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert (f"{MANUAL} differs only in the repository's name: it was "
            "generated for 'repo', and this checkout's name is 'moved' (the "
            "origin remote's URL). The name never comes from the "
            "environment; when the file is right, set \"repository\": "
            "\"repo\" in the config, otherwise run "
            f"{TOOL} generate and commit {MANUAL}") in result.stdout
    # following the advice makes verify pass
    tool_repo.config(base_config(repository="repo"))
    assert tool_repo.run("verify").returncode == 0


def test_verify_gives_a_diff_when_more_than_the_name_differs(tool_repo):
    generate(tool_repo, base_config())
    path = tool_repo.path / MANUAL
    path.write_text(path.read_text().replace("name: Manual", "name: Other"))
    tool_repo.git("remote", "add", "origin", "git@example.invalid:o/moved.git")
    result = tool_repo.run("verify")
    assert result.returncode == 1
    assert "differs only in the repository's name" not in result.stdout
    assert "-name: Other" in result.stdout


def test_committed_repo_reads_the_first_option():
    config = {"jobs": {
        "a": {"title": "A", "manual": True},
        "b": {"title": "B", "manual": True}}}
    text = ('          - "not \\q json"\n'
            '          - "Other / x:a"\n'
            '          - 7\n'
            '          - "B / old:b"\n'
            '          - "A / old:a"\n')
    assert git_cicd._committed_repo(config, text, "new") == "old"
    assert git_cicd._committed_repo(config, text, "old") is None
    assert git_cicd._committed_repo(config, '          - "A / :a"\n',
                                    "new") is None
    assert git_cicd._committed_repo(config, "", "new") is None
    assert git_cicd._committed_repo(
        {"jobs": {"a": {"title": "A", "manual": False}}}, text, "n") is None


@pytest.mark.parametrize("name", ["${{ github.token }}", "a\nb"])
def test_a_repository_name_that_cannot_be_written_is_refused(name):
    config = {"jobs": {"t": {"title": "T", "manual": True, "inputs": {},
                             "on": [], "cron": None, "permissions": {}}},
              "repository": None}
    with pytest.raises(git_cicd.UsageError,
                       match="cannot be written into a workflow"):
        git_cicd.render_workflows(config, "git-cicd", repo=name)


def test_render_without_a_repo_uses_the_config_or_a_placeholder():
    config = {"jobs": {"t": {"title": "T", "manual": True, "inputs": {},
                             "on": [], "cron": None, "permissions": {}}}}
    text = git_cicd.render_workflows(config, "git-cicd")[MANUAL]
    assert '- "T / repository:t"' in text
    config["repository"] = "named"
    text = git_cicd.render_workflows(config, "git-cicd")[MANUAL]
    assert '- "T / named:t"' in text
