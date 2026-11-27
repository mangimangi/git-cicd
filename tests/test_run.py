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
        "GITHUB_TOKEN": "ghs_tok", "VENDOR_PAT": "pat value $x",
    }
    assert os.path.isabs(values["CICD_CHANGED_FILES"])
    assert (log.parent / "log.txt.changed").read_text() == "src/app.py\n"
    assert os.path.realpath(lines[9]) == os.path.realpath(repo.path)
    # the changed-files file is cleaned up after the job
    assert not os.path.exists(values["CICD_CHANGED_FILES"])
    assert "ghs_tok" not in result.stdout + result.stderr


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


@pytest.mark.parametrize("trigger", ["merge", "cron", "manual"])
def test_unbuilt_trigger(repo, log, trigger):
    repo.script("ci/a.sh")
    base, head = setup_repo(repo, {"t": {
        "on": ["open"], "branches": ["**"], "steps": ["ci/a.sh"]}}, log)
    result = repo.run("run-job", "t", f"--trigger={trigger}", "--target=main",
                      "--source=f", f"--base={base}", f"--head={head}")
    assert result.returncode == 2
    assert f"the {trigger} trigger is not built yet" in result.stderr


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
