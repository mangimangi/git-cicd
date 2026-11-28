"""Tests for running a job: setup when asked, steps without a shell."""

import json
import os

import pytest

from tests.conftest import git_cicd

LOG_STEP = 'echo "$(basename "$0")${*:+ $*}" >> "$LOG"\n'


def setup_repo(repo, jobs, log):
    repo.config({"jobs": jobs})
    base = repo.commit("base")
    repo.git("checkout", "-q", "-b", "feature")
    repo.write("src/app.py", "x\n")
    head = repo.commit("change")
    return base, head


def run_job(repo, job, base, head, *extra, env=None, source="feature"):
    return repo.run("run-job", job, "--trigger=open", "--target=main",
                    f"--source={source}", f"--base={base}", f"--head={head}",
                    *extra, env=env)


@pytest.fixture
def log(tmp_path):
    return tmp_path / "log.txt"


def env_for(log, **more):
    env = {"LOG": str(log)}
    env.update(more)
    return env


def logged(log):
    return log.read_text().splitlines() if log.exists() else []


def test_setup_then_steps_in_order(repo, log, tmp_path):
    repo.script("ci/setup.sh", LOG_STEP)
    repo.script("ci/a.sh", LOG_STEP)
    repo.script("ci/b.sh", LOG_STEP)
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "setup": "ci/setup.sh",
        "steps": ["ci/a.sh", ["ci/b.sh", "x", "y"]]}}, log)
    out = tmp_path / "result.json"
    result = run_job(repo, "t", base, head, "--setup", "--result", str(out),
                     env=env_for(log))
    assert result.returncode == 0, result.stdout + result.stderr
    assert logged(log) == ["setup.sh", "a.sh", "b.sh x y"]
    assert "==> git-cicd: job t: setup ci/setup.sh" in result.stdout
    assert "==> git-cicd: job t: step 2/2 ci/b.sh x y" in result.stdout
    data = json.loads(out.read_text())
    assert data["state"] == "passed"
    assert data["setup"]["exit_code"] == 0
    assert isinstance(data["setup"]["seconds"], float)
    assert [s["step"] for s in data["steps"]] == ["ci/a.sh", "ci/b.sh x y"]
    assert all(isinstance(s["seconds"], float) for s in data["steps"])
    assert data["seconds"] >= sum(s["seconds"] for s in data["steps"])
    assert {"job", "state", "failed_step", "exit_code", "setup", "steps",
            "seconds"} <= set(data)


def test_stops_at_first_failing_step(repo, log, tmp_path):
    repo.script("ci/a.sh", LOG_STEP)
    repo.script("ci/fail.sh", LOG_STEP + "exit 3\n")
    repo.script("ci/later.sh", 'touch "$LOG.later"\n')
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"],
        "steps": ["ci/a.sh", "ci/fail.sh", "ci/later.sh"]}}, log)
    out = tmp_path / "result.json"
    result = run_job(repo, "t", base, head, "--result", str(out),
                     env=env_for(log))
    assert result.returncode == 1
    assert logged(log) == ["a.sh", "fail.sh"]
    assert not os.path.exists(str(log) + ".later")
    data = json.loads(out.read_text())
    assert data["state"] == "failed"
    assert data["failed_step"] == "ci/fail.sh"
    assert data["exit_code"] == 3
    assert len(data["steps"]) == 2
    assert "job t: failed (step ci/fail.sh, exit 3)" in result.stdout


def test_setup_failure_is_could_not_run(repo, log, tmp_path):
    repo.script("ci/setup.sh", "exit 7\n")
    repo.script("ci/a.sh", LOG_STEP)
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "setup": "ci/setup.sh",
        "steps": ["ci/a.sh"]}}, log)
    out = tmp_path / "result.json"
    result = run_job(repo, "t", base, head, "--setup", "--result", str(out),
                     env=env_for(log))
    assert result.returncode == 1
    assert logged(log) == []
    data = json.loads(out.read_text())
    assert data["state"] == "could not run"
    assert data["state"] != "failed"
    assert data["failed_step"] is None
    assert data["setup"]["exit_code"] == 7
    assert data["steps"] == []


def test_setup_skipped_without_flag(repo, log, tmp_path):
    repo.script("ci/setup.sh", LOG_STEP)
    repo.script("ci/a.sh", LOG_STEP)
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "setup": "ci/setup.sh",
        "steps": ["ci/a.sh"]}}, log)
    out = tmp_path / "result.json"
    result = run_job(repo, "t", base, head, "--result", str(out),
                     env=env_for(log))
    assert result.returncode == 0
    assert logged(log) == ["a.sh"]
    data = json.loads(out.read_text())
    assert data["setup"] is None
    assert data["setup_skipped"] is True


def test_step_that_cannot_execute_fails(repo, log, tmp_path):
    repo.write("ci/bad.sh", "#!/nonexistent/interpreter\n", executable=True)
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/bad.sh"]}}, log)
    out = tmp_path / "result.json"
    result = run_job(repo, "t", base, head, "--result", str(out))
    assert result.returncode == 1
    data = json.loads(out.read_text())
    assert data["state"] == "failed"
    assert data["failed_step"] == "ci/bad.sh"
    assert data["exit_code"] is None
    assert "cannot execute" in data["error"]


DUMP_ENV = """for v in CICD_TRIGGER CICD_JOB CICD_TARGET_BRANCH CICD_SOURCE_BRANCH \\
         CICD_BASE CICD_HEAD CICD_CHANGED_FILES GITHUB_TOKEN VENDOR_PAT; do
  printf '%s=' "$v" >> "$LOG"
  eval "printf '%s' \\"\\$$v\\"" >> "$LOG"
  printf '\\n' >> "$LOG"
done
cp "$CICD_CHANGED_FILES" "$LOG.changed"
pwd >> "$LOG"
"""


def test_environment_reaches_step(repo, log):
    repo.script("ci/env.sh", DUMP_ENV)
    base, head = setup_repo(repo, {"envjob": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/env.sh"]}}, log)
    result = run_job(repo, "envjob", base, head,
                     env=env_for(log, GITHUB_TOKEN="ghs_tok",
                                 VENDOR_PAT="pat value $x"))
    assert result.returncode == 0, result.stdout + result.stderr
    lines = logged(log)
    values = dict(line.split("=", 1) for line in lines[:9])
    assert values == {
        "CICD_TRIGGER": "open", "CICD_JOB": "envjob",
        "CICD_TARGET_BRANCH": "main", "CICD_SOURCE_BRANCH": "feature",
        "CICD_BASE": base, "CICD_HEAD": head,
        "CICD_CHANGED_FILES": values["CICD_CHANGED_FILES"],
        # open runs a pull request's code: VENDOR_PAT (which may write) is
        # dropped even when the caller has it
        "GITHUB_TOKEN": "ghs_tok", "VENDOR_PAT": "",
    }
    assert os.path.isabs(values["CICD_CHANGED_FILES"])
    assert (log.parent / "log.txt.changed").read_text() == "src/app.py\n"
    assert os.path.realpath(lines[9]) == os.path.realpath(repo.path)
    # the changed-files file is cleaned up after the job
    assert not os.path.exists(values["CICD_CHANGED_FILES"])
    assert "ghs_tok" not in result.stdout + result.stderr
    assert "pat value" not in result.stdout + result.stderr


def test_open_step_has_no_vendor_pat_variable(repo, log):
    """VENDOR_PAT is removed on open, not set empty."""
    repo.script("ci/env.sh", 'echo "${VENDOR_PAT-unset}" >> "$LOG"\n')
    base, head = setup_repo(repo, {"envjob": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/env.sh"]}}, log)
    result = run_job(repo, "envjob", base, head,
                     env=env_for(log, VENDOR_PAT="pat_token"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert logged(log) == ["unset"]


def test_merge_environment_reaches_step(repo, log):
    """On merge the target is the branch landed on, the source the same
    branch, the base the commit before the push and the head the landed
    commit; the changed files are what the push brought."""
    repo.script("ci/env.sh", DUMP_ENV)
    repo.config({"jobs": {"envjob": {
        "on": ["merge"], "branches": ["main"], "steps": ["ci/env.sh"],
        "secrets": ["VENDOR_PAT"]}}})
    before = repo.commit("base")
    repo.write("src/app.py", "x\n")
    landed = repo.commit("landed")
    result = repo.run("run-job", "envjob", "--trigger=merge", "--target=main",
                      "--source=main", f"--base={before}", f"--head={landed}",
                      env=env_for(log, GITHUB_TOKEN="ghs_tok",
                                  VENDOR_PAT="pat_token"))
    assert result.returncode == 0, result.stdout + result.stderr
    values = dict(line.split("=", 1) for line in logged(log)[:9])
    assert values == {
        "GITHUB_TOKEN": "ghs_tok", "VENDOR_PAT": "pat_token",
        "CICD_TRIGGER": "merge", "CICD_JOB": "envjob",
        "CICD_TARGET_BRANCH": "main", "CICD_SOURCE_BRANCH": "main",
        "CICD_BASE": before, "CICD_HEAD": landed,
        "CICD_CHANGED_FILES": values["CICD_CHANGED_FILES"],
    }
    assert (log.parent / "log.txt.changed").read_text() == "src/app.py\n"


def test_manual_environment_reaches_step(repo, log):
    """On manual, target and source are the branch the run was started on,
    base and head the run's commit, and the changed files are empty."""
    repo.script("ci/env.sh", DUMP_ENV)
    repo.config({"jobs": {"envjob": {
        "on": [], "branches": ["main"], "paths": ["src/**"],
        "steps": ["ci/env.sh"]}}})
    repo.commit("base")
    repo.write("src/app.py", "x\n")
    sha = repo.commit("run here")
    result = repo.run("run-job", "envjob", "--trigger=manual", "--target=main",
                      "--source=main", f"--base={sha}", f"--head={sha}",
                      env=env_for(log))
    assert result.returncode == 0, result.stdout + result.stderr
    values = dict(line.split("=", 1) for line in logged(log)[:7])
    assert values == {
        "CICD_TRIGGER": "manual", "CICD_JOB": "envjob",
        "CICD_TARGET_BRANCH": "main", "CICD_SOURCE_BRANCH": "main",
        "CICD_BASE": sha, "CICD_HEAD": sha,
        "CICD_CHANGED_FILES": values["CICD_CHANGED_FILES"],
    }
    assert (log.parent / "log.txt.changed").read_text() == ""


@pytest.mark.parametrize("job,branch,reason", [
    ("nope", "main", "unknown job 'nope'"),
    ("off", "main", 'job off cannot be run by hand ("manual": false)'),
    ("t", "dev", "branch dev does not match the branches of job t (main)"),
])
def test_manual_run_job_refusals(repo, log, job, branch, reason):
    repo.script("ci/a.sh", LOG_STEP)
    repo.config({"jobs": {
        "t": {"branches": ["main"], "steps": ["ci/a.sh"]},
        "off": {"branches": ["**"], "steps": ["ci/a.sh"], "manual": False}}})
    sha = repo.commit("base")
    result = repo.run("run-job", job, "--trigger=manual", f"--target={branch}",
                      f"--source={branch}", f"--base={sha}", f"--head={sha}",
                      env=env_for(log))
    assert result.returncode == 2
    assert reason in result.stderr
    assert logged(log) == []


# ── declared inputs ─────────────────────────────────────────────────────────

DUMP_INPUTS = """env | grep '^CICD_INPUT_\\|^CICD_MANUAL_FORM=' | sort > "$LOG"
printf '%s' "$CICD_INPUT_TEXT" > "$LOG.text"
"""

INPUT_JOB = {"on": ["open", "merge"], "branches": ["**"],
             "steps": ["ci/inputs.sh"],
             "inputs": {"text": {"default": "the default"},
                        "kind": {"choices": ["a", "b"], "default": "a"},
                        "empty": {}}}


def setup_inputs(repo, job=None):
    repo.script("ci/inputs.sh", DUMP_INPUTS)
    repo.config({"jobs": {"j": job or INPUT_JOB}})
    return repo.commit("base")


def run_inputs(repo, sha, log, trigger="manual", inputs=None, **more):
    env = env_for(log, **more)
    if inputs is not None:
        env["CICD_MANUAL_FORM"] = inputs
    return repo.run("run-job", "j", f"--trigger={trigger}", "--target=main",
                    "--source=main", f"--base={sha}", f"--head={sha}", env=env)


def test_manual_value_reaches_the_step_literally(repo, log):
    sha = setup_inputs(repo)
    value = "it's \"q\" $HOME `id` $(id)\nsecond line\\n"
    result = run_inputs(repo, sha, log, inputs=json.dumps({"text": value,
                                                           "kind": "b"}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (log.parent / "log.txt.text").read_bytes() == value.encode()
    lines = logged(log)
    assert "CICD_INPUT_KIND=b" in lines
    assert "CICD_INPUT_EMPTY=" in lines
    assert not any(l.startswith("CICD_MANUAL_FORM=") for l in lines)


@pytest.mark.parametrize("trigger", ["open", "merge"])
def test_other_triggers_get_the_defaults(repo, log, trigger):
    sha = setup_inputs(repo)
    result = run_inputs(repo, sha, log, trigger=trigger,
                        inputs=json.dumps({"kind": "b"}),
                        CICD_INPUT_STRAY="inherited",
                        CICD_INPUT_KIND="inherited")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (log.parent / "log.txt.text").read_text() == "the default"
    lines = logged(log)
    assert sorted(l for l in lines if not l.startswith("CICD_INPUT_TEXT")) \
        == ["CICD_INPUT_EMPTY=", "CICD_INPUT_KIND=a"]


def test_undeclared_inherited_inputs_are_dropped(repo, log):
    sha = setup_inputs(repo)
    result = run_inputs(repo, sha, log, inputs="",
                        CICD_INPUT_STRAY="inherited")
    assert result.returncode == 0, result.stdout + result.stderr
    names = [l.split("=", 1)[0] for l in logged(log)]
    assert "CICD_INPUT_STRAY" not in names
    assert sorted(set(names)) == ["CICD_INPUT_EMPTY", "CICD_INPUT_KIND",
                                  "CICD_INPUT_TEXT"]


@pytest.mark.parametrize("inputs,reason", [
    ("{nope", "the manual run's form values are not valid JSON"),
    ('["a"]', "the manual run's form values must be a JSON object of "
              "string values"),
    ('{"text": 1}', "the manual run's form values must be a JSON object of "
                    "string values"),
    ('{"kind": "c"}', "job j: input kind: 'c' is not one of the choices (a, b)"),
])
def test_manual_input_failures_refuse_the_run(repo, log, inputs, reason):
    sha = setup_inputs(repo)
    result = run_inputs(repo, sha, log, inputs=inputs)
    assert result.returncode == 2
    assert f"manual run refused: {reason}" in result.stderr
    assert logged(log) == []


def test_missing_required_input_refuses_the_run(repo, log):
    job = dict(INPUT_JOB, inputs={"repo": {"required": True}})
    sha = setup_inputs(repo, job)
    result = run_inputs(repo, sha, log, inputs="{}")
    assert result.returncode == 2
    assert "job j: input repo is required" in result.stderr
    # an empty field of the form is missing
    result = run_inputs(repo, sha, log, inputs='{"job": "j", "repo": ""}')
    assert result.returncode == 2
    assert "job j: input repo is required" in result.stderr
    # without the form every input is its default: a required one is missing
    result = run_inputs(repo, sha, log)
    assert result.returncode == 2
    assert "job j: input repo is required" in result.stderr
    # on another trigger a required input is the empty string
    result = run_inputs(repo, sha, log, trigger="open")
    assert result.returncode == 0, result.stderr
    assert logged(log) == ["CICD_INPUT_REPO="]


def test_step_receives_trigger_not_moment(repo, log):
    """The step sees CICD_TRIGGER=open; the old name CICD_MOMENT is not set."""
    repo.script("ci/env.sh", 'env >> "$LOG"\n')
    base, head = setup_repo(repo, {"envjob": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/env.sh"]}}, log)
    result = run_job(repo, "envjob", base, head, env=env_for(log))
    assert result.returncode == 0, result.stdout + result.stderr
    names = {line.split("=", 1)[0]: line.split("=", 1)[1]
             for line in logged(log) if "=" in line}
    assert names["CICD_TRIGGER"] == "open"
    assert "CICD_MOMENT" not in names


@pytest.mark.parametrize("command", [
    ["decide"], ["run-job", "t"], ["report", "--decisions", "x",
                                   "--results", "y"]])
def test_moment_option_is_rejected(repo, command):
    """--moment is gone with no alias: argparse rejects it on every command
    that took it."""
    repo.config({"jobs": {"t": {"on": ["open"], "branches": ["**"],
                                "steps": ["ci/t.sh"]}}})
    # every other argument is valid, so the unknown option is the only error
    change = [] if command[0] == "report" else [
        "--trigger=open", "--target=main", "--source=f", "--base=b",
        "--head=h"]
    result = repo.run(*command, "--moment=open", *change)
    assert result.returncode == 2
    assert "unrecognized arguments: --moment=open" in result.stderr


def test_setup_receives_environment(repo, log):
    repo.script("ci/setup.sh", 'echo "$CICD_JOB $CICD_TRIGGER" >> "$LOG"\n'
                'test -f "$CICD_CHANGED_FILES"\n')
    repo.script("ci/a.sh")
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "setup": "ci/setup.sh",
        "steps": ["ci/a.sh"]}}, log)
    result = run_job(repo, "t", base, head, "--setup", env=env_for(log))
    assert result.returncode == 0
    assert logged(log) == ["t open"]


INJECTION = ("x$(touch${IFS}pwned)`touch${IFS}pwned2`;touch${IFS}pwned3"
             "&&touch${IFS}pwned4")


def test_branch_with_shell_metacharacters_reaches_step_unaltered(repo, log):
    # A real branch whose name git accepts, carrying shell metacharacters.
    repo.git("check-ref-format", "--branch", INJECTION)
    repo.script("ci/show.sh",
                'printf "%s" "$CICD_SOURCE_BRANCH" > "$LOG"\n'
                'printf "%s" "$CICD_TARGET_BRANCH" > "$LOG.target"\n')
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/show.sh"]}}, log)
    repo.git("branch", INJECTION)
    result = repo.run("run-job", "t", "--trigger=open",
                      f"--target={INJECTION}", f"--source={INJECTION}",
                      f"--base={base}", f"--head={head}", env=env_for(log))
    assert result.returncode == 0, result.stderr
    assert log.read_bytes() == INJECTION.encode()
    assert (log.parent / "log.txt.target").read_bytes() == INJECTION.encode()
    for name in ("pwned", "pwned2", "pwned3", "pwned4"):
        assert not (repo.path / name).exists()
        assert not (log.parent / name).exists()


def test_fixed_arguments_with_metacharacters_unaltered(repo, log):
    args = ["$(touch pwned)", "`touch pwned2`", "a;touch pwned3", "&& b",
            "two words", "'q'\"", "*"]
    repo.script("ci/args.sh",
                'for a in "$@"; do printf "%s\\n" "$a" >> "$LOG"; done\n')
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"],
        "steps": [["ci/args.sh", *args]]}}, log)
    result = run_job(repo, "t", base, head, env=env_for(log))
    assert result.returncode == 0, result.stderr
    assert logged(log) == args
    for name in ("pwned", "pwned2", "pwned3"):
        assert not (repo.path / name).exists()


def test_unknown_job(repo, log):
    repo.script("ci/a.sh")
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/a.sh"]}}, log)
    result = run_job(repo, "nope", base, head)
    assert result.returncode == 2
    assert "unknown job 'nope'" in result.stderr


def test_cron_environment_reaches_step(repo, log):
    """On cron, target and source are the branch, base and head its head
    commit, the changed files are empty and inputs are their defaults."""
    repo.script("ci/env.sh", DUMP_ENV + 'echo "$CICD_INPUT_VENDOR" >> "$LOG"\n')
    repo.config({"jobs": {"envjob": {
        "on": ["cron"], "cron": "0 9 * * 1", "branches": ["main"],
        "inputs": {"vendor": {"default": "all"}}, "steps": ["ci/env.sh"]}}})
    repo.commit("base")
    repo.write("src/app.py", "x\n")
    sha = repo.commit("head")
    result = repo.run("run-job", "envjob", "--trigger=cron", "--target=main",
                      "--source=main", f"--base={sha}", f"--head={sha}",
                      env=env_for(log, CICD_MANUAL_FORM='{"vendor": "x"}'))
    assert result.returncode == 0, result.stdout + result.stderr
    lines = logged(log)
    values = dict(line.split("=", 1) for line in lines[:7])
    assert values == {
        "CICD_TRIGGER": "cron", "CICD_JOB": "envjob",
        "CICD_TARGET_BRANCH": "main", "CICD_SOURCE_BRANCH": "main",
        "CICD_BASE": sha, "CICD_HEAD": sha,
        "CICD_CHANGED_FILES": values["CICD_CHANGED_FILES"],
    }
    assert (log.parent / "log.txt.changed").read_text() == ""
    assert lines[-1] == "all"


def test_result_names_branch_and_head(repo, log, tmp_path):
    repo.script("ci/a.sh")
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/a.sh"]}}, log)
    out = tmp_path / "result.json"
    assert run_job(repo, "t", base, head, "--result", str(out)).returncode == 0
    data = json.loads(out.read_text())
    assert data["target"] == "main" and data["head"] == head


def test_changed_files_when_diff_fails_is_empty_file(repo, log):
    repo.script("ci/a.sh", 'wc -l < "$CICD_CHANGED_FILES" > "$LOG"\n')
    _, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/a.sh"]}}, log)
    result = run_job(repo, "t", "nope", head, env=env_for(log))
    assert result.returncode == 0
    assert logged(log)[0].strip() == "0"


def test_run_job_function(repo, log):
    repo.script("ci/a.sh")
    setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/a.sh"]}}, log)
    config = git_cicd.load_config(str(repo.path))
    facts = {"trigger": "open", "target": "main", "source": "f",
             "base": "HEAD~1", "head": "HEAD"}
    result = git_cicd.run_job(config, str(repo.path), "t", facts)
    assert result["state"] == "passed"


def test_a_step_that_removes_the_changed_files_list_still_passes(repo, log,
                                                                  tmp_path):
    repo.script("ci/a.sh", 'rm "$CICD_CHANGED_FILES"\n' + LOG_STEP)
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/a.sh"]}}, log)
    out = tmp_path / "result.json"
    result = run_job(repo, "t", base, head, "--result", str(out),
                     env=env_for(log))
    assert result.returncode == 0, result.stdout + result.stderr
    assert logged(log) == ["a.sh"]
    assert json.loads(out.read_text())["state"] == "passed"


def test_manual_run_gets_only_its_own_fields(repo, log):
    """The form holds every manual job's fields: run-job passes the chosen
    job only those it declares, says which others it ignored (those not at
    their form default) and never passes the form on."""
    repo.script("ci/inputs.sh", DUMP_INPUTS)
    repo.config({"jobs": {
        "j": INPUT_JOB,
        "other": {"branches": ["**"], "steps": ["ci/inputs.sh"],
                  "inputs": {"vendor": {"default": "all"},
                             "private": {"choices": ["false", "true"]}}}}})
    sha = repo.commit("base")
    form = {"job": "j", "text": "mine", "kind": "b", "empty": "",
            "vendor": "someone", "private": "false"}
    result = run_inputs(repo, sha, log, inputs=json.dumps(form))
    assert result.returncode == 0, result.stdout + result.stderr
    assert ("==> git-cicd: ignored input vendor (job j does not declare it)"
            in result.stdout)
    assert "private" not in result.stdout
    assert sorted(logged(log)) == ["CICD_INPUT_EMPTY=", "CICD_INPUT_KIND=b",
                                   "CICD_INPUT_TEXT=mine"]


# ── secrets ─────────────────────────────────────────────────────────────────

SECRET_NAMES = git_cicd.DECLARABLE_SECRETS
ECHO_SECRETS = "".join(
    f'echo "{n}=${{{n}-unset}}" >> "$LOG"\n'
    for n in ("GITHUB_TOKEN",) + SECRET_NAMES)
ALL_SET = {"GITHUB_TOKEN": "gh-value", "CICD_WRITE_TOKEN": "write-value",
           "CICD_READ_TOKEN": "read-value", "VENDOR_PAT": "pat-value"}


def run_on(repo, trigger, base, head, *extra, env=None):
    branch = "main" if trigger in ("merge", "cron", "manual") else None
    return repo.run("run-job", "j", f"--trigger={trigger}", "--target=main",
                    f"--source={branch or 'feature'}", f"--base={base}",
                    f"--head={head}", *extra, env=env)


def secret_job(repo, log, secrets=None):
    repo.script("ci/echo.sh", ECHO_SECRETS)
    job = {"on": ["open", "merge"], "branches": ["**"],
           "steps": ["ci/echo.sh"]}
    if secrets is not None:
        job["secrets"] = secrets
    return setup_repo(repo, {"j": job}, log)


def seen(log):
    return dict(line.split("=", 1) for line in logged(log))


@pytest.mark.parametrize("trigger", git_cicd.ALL_TRIGGERS)
def test_undeclared_secrets_never_reach_a_script(repo, log, trigger):
    base, head = secret_job(repo, log)
    result = run_on(repo, trigger, base, head, env=env_for(log, **ALL_SET))
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen(log) == {"GITHUB_TOKEN": "gh-value",
                         "CICD_WRITE_TOKEN": "unset",
                         "CICD_READ_TOKEN": "unset", "VENDOR_PAT": "unset"}


@pytest.mark.parametrize("trigger", git_cicd.ALL_TRIGGERS)
def test_a_declared_secret_and_nothing_else(repo, log, trigger):
    base, head = secret_job(repo, log, ["CICD_READ_TOKEN"])
    result = run_on(repo, trigger, base, head, env=env_for(log, **ALL_SET))
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen(log) == {"GITHUB_TOKEN": "gh-value",
                         "CICD_WRITE_TOKEN": "unset",
                         "CICD_READ_TOKEN": "read-value",
                         "VENDOR_PAT": "unset"}
    assert "declared secret" not in result.stdout


@pytest.mark.parametrize("trigger", git_cicd.ALL_TRIGGERS)
def test_every_declared_secret_reaches_the_script(repo, log, trigger):
    base, head = secret_job(repo, log, list(SECRET_NAMES))
    result = run_on(repo, trigger, base, head, env=env_for(log, **ALL_SET))
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen(log) == ALL_SET


@pytest.mark.parametrize("trigger", git_cicd.ALL_TRIGGERS)
def test_declared_secret_empty_or_unset_reaches_the_script_unset(
        repo, log, tmp_path, trigger):
    base, head = secret_job(repo, log, ["CICD_WRITE_TOKEN",
                                        "CICD_READ_TOKEN", "VENDOR_PAT"])
    out = tmp_path / "result.json"
    # CICD_WRITE_TOKEN empty (as the workflow gives an unset secret),
    # CICD_READ_TOKEN unset, VENDOR_PAT set
    result = run_on(repo, trigger, base, head, "--result", str(out),
                    env=env_for(log, CICD_WRITE_TOKEN="",
                                VENDOR_PAT="pat-value"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen(log)["CICD_WRITE_TOKEN"] == "unset"
    assert seen(log)["CICD_READ_TOKEN"] == "unset"
    assert seen(log)["VENDOR_PAT"] == "pat-value"
    data = json.loads(out.read_text())
    assert data["absent_secrets"] == ["CICD_WRITE_TOKEN", "CICD_READ_TOKEN"]
    out_text = result.stdout
    assert "==> git-cicd: job j: declared secret CICD_WRITE_TOKEN is not " \
        "set" in out_text
    assert "==> git-cicd: job j: declared secret CICD_READ_TOKEN is not " \
        "set" in out_text
    # the note comes before the steps
    assert out_text.index("declared secret") < out_text.index("step 1/1")
    assert "pat-value" not in out_text + result.stderr + out.read_text()


def test_script_env_removes_undeclared_secrets(monkeypatch):
    for name, value in ALL_SET.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CICD_READ_TOKEN", "")
    facts = {"trigger": "merge", "target": "main", "source": "main",
             "base": "b", "head": "h"}
    env = git_cicd.script_env("j", facts, "/tmp/x", {}, ["CICD_READ_TOKEN",
                                                         "VENDOR_PAT"])
    assert env["GITHUB_TOKEN"] == "gh-value"
    assert env["VENDOR_PAT"] == "pat-value"
    assert "CICD_READ_TOKEN" not in env and "CICD_WRITE_TOKEN" not in env
    assert git_cicd.absent_secrets(["CICD_READ_TOKEN", "VENDOR_PAT"]) == [
        "CICD_READ_TOKEN"]
