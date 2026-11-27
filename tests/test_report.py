"""Tests for the report: one line per job with times, and one verdict."""

import io
import json

import pytest

from tests.conftest import git_cicd

MATCH = (True, "workflow matches config")
MISMATCH = (False, "diff")


@pytest.fixture
def config(repo):
    for name in ("ci/setup.sh", "ci/test.sh", "ci/cov.sh", "ci/lint.sh",
                 "ci/docs.sh"):
        repo.script(name)
    repo.config({"jobs": {
        "test": {"on": ["open"], "branches": ["**"], "paths": ["src/**"],
                 "setup": "ci/setup.sh", "steps": ["ci/test.sh", "ci/cov.sh"]},
        "lint": {"on": ["open"], "branches": ["**"], "paths": ["src/**"],
                 "steps": ["ci/lint.sh"], "blocking": False},
        "docs": {"on": ["open"], "branches": ["main"], "paths": ["docs/**"],
                 "steps": ["ci/docs.sh"]},
    }})
    return git_cicd.load_config(str(repo.path))


def decision(**needed):
    """needed: name -> (needed, reason)."""
    jobs = []
    for name in ("test", "lint", "docs"):
        n, reason = needed.get(name, (False, "no changed file matches paths"))
        jobs.append({"name": name, "needed": n, "reason": reason,
                     "blocking": name != "lint"})
    return {"moment": "open", "target": "main", "source": "f", "base": "b",
            "head": "h", "changed_files": [], "jobs": jobs, "max_parallel": 3}


def passed_result(name, steps=("ci/test.sh", "ci/cov.sh"), setup=True):
    return {
        "job": name, "state": "passed", "failed_step": None, "exit_code": 0,
        "error": None,
        "setup": {"script": "ci/setup.sh", "seconds": 1.25, "exit_code": 0,
                  "error": None} if setup else None,
        "setup_skipped": False,
        "steps": [{"step": s, "seconds": 2.5, "exit_code": 0, "error": None}
                  for s in steps],
        "seconds": 6.25,
    }


def run_report(config, repo, dec, results, workflow=MATCH, **kw):
    out = io.StringIO()
    ok, verdict = git_cicd.report(config, str(repo.path), dec, results,
                                  workflow=workflow, out=out, **kw)
    return ok, verdict, out.getvalue()


def line_for(text, name):
    return next(l for l in text.splitlines() if l.strip().startswith(name))


def test_all_passed(config, repo):
    dec = decision(test=(True, "1 changed file match paths"),
                   lint=(True, "1 changed file match paths"),
                   docs=(True, "x"))
    results = {"test": passed_result("test"),
               "lint": passed_result("lint", ("ci/lint.sh",), setup=False),
               "docs": passed_result("docs", ("ci/docs.sh",), setup=False)}
    ok, verdict, text = run_report(config, repo, dec, results)
    assert ok
    assert verdict == "PASSED - 3 of 3 jobs needed, 3 passed"
    assert text.splitlines()[-1] == verdict
    assert "workflow matches config" in text
    assert "passed  6.2s" in line_for(text, "test")


def test_times_present_for_every_job_and_step(config, repo):
    dec = decision(test=(True, "r"))
    ok, _, text = run_report(config, repo, dec, {"test": passed_result("test")})
    assert ok
    assert "setup ci/setup.sh  1.2s  (exit 0)" in text
    assert text.count("step ci/test.sh  2.5s") == 1
    assert text.count("step ci/cov.sh  2.5s") == 1


def test_one_line_per_declared_job_in_config_order(config, repo):
    dec = decision(test=(True, "r"))
    _, _, text = run_report(config, repo, dec, {"test": passed_result("test")})
    names = [l.split()[0] for l in text.splitlines()
             if l.startswith("  ") and l.split()[0] in ("test", "lint", "docs")]
    assert names == ["test", "lint", "docs"]
    assert "not needed (no changed file matches paths) (non-blocking)" in \
        line_for(text, "lint")


def test_failed_step_named(config, repo):
    r = passed_result("test")
    r.update(state="failed", failed_step="ci/cov.sh", exit_code=4)
    r["steps"][1]["exit_code"] = 4
    ok, verdict, text = run_report(config, repo, decision(test=(True, "r")),
                                   {"test": r})
    assert not ok
    assert "failed (step ci/cov.sh, exit 4)" in line_for(text, "test")
    assert verdict == "FAILED - 1 of 3 jobs needed, 1 failed"


def test_failed_step_with_error(config, repo):
    r = passed_result("test", ("ci/test.sh",))
    r.update(state="failed", failed_step="ci/test.sh", exit_code=None,
             error="cannot execute ci/test.sh: No such file")
    r["steps"][0].update(exit_code=None, error=r["error"])
    _, _, text = run_report(config, repo, decision(test=(True, "r")),
                            {"test": r})
    assert "failed (step ci/test.sh, error: cannot execute" in text


def test_setup_failed_is_could_not_run(config, repo):
    r = passed_result("test", ())
    r.update(state="could not run", exit_code=1)
    r["setup"]["exit_code"] = 1
    ok, verdict, text = run_report(config, repo, decision(test=(True, "r")),
                                   {"test": r})
    assert not ok
    assert "could not run (setup failed)" in line_for(text, "test")
    assert "failed (step" not in text
    assert verdict == "FAILED - 1 of 3 jobs needed, 1 could not run"


def test_non_blocking_failure_passes(config, repo):
    lint = passed_result("lint", ("ci/lint.sh",), setup=False)
    lint.update(state="failed", failed_step="ci/lint.sh", exit_code=1)
    dec = decision(test=(True, "r"), lint=(True, "r"))
    ok, verdict, text = run_report(config, repo, dec,
                                   {"test": passed_result("test"),
                                    "lint": lint})
    assert ok
    assert "failed (step ci/lint.sh, exit 1) (non-blocking)" in \
        line_for(text, "lint")
    assert verdict == ("PASSED - 2 of 3 jobs needed, 1 passed, 1 failed "
                       "(1 non-blocking)")


def test_non_blocking_could_not_run_passes(config, repo):
    dec = decision(lint=(True, "r"))
    ok, _, text = run_report(config, repo, dec, {})
    assert ok
    assert "could not run (no result) (non-blocking)" in line_for(text, "lint")


def test_none_needed(config, repo):
    reason = "only needs_nothing files changed"
    dec = decision(test=(False, reason), lint=(False, reason),
                   docs=(False, reason))
    ok, verdict, text = run_report(config, repo, dec, {})
    assert ok
    assert verdict == ("PASSED - 0 of 3 jobs needed: only needs_nothing files "
                       "changed")
    assert "not needed (only needs_nothing files changed)" in \
        line_for(text, "test")


def test_base_matches_no_branches(config, repo):
    dec = decision(**{n: (False, "target plan/x does not match branches")
                      for n in ("test", "lint", "docs")})
    ok, verdict, text = run_report(config, repo, dec, {})
    assert ok
    for name in ("test", "lint", "docs"):
        assert "does not match branches" in line_for(text, name)
    assert verdict == ("PASSED - 0 of 3 jobs needed: target plan/x does not "
                       "match branches")


def test_missing_result_is_could_not_run(config, repo):
    ok, verdict, text = run_report(config, repo, decision(test=(True, "r")),
                                   {})
    assert not ok
    assert "could not run (no result)" in line_for(text, "test")
    assert verdict.startswith("FAILED")


def test_workflow_mismatch_fails(config, repo):
    ok, verdict, text = run_report(config, repo, decision(), {},
                                   workflow=MISMATCH)
    assert not ok
    assert verdict.startswith("FAILED - 0 of 3 jobs needed")
    assert verdict.endswith("; the workflow does not match the config")
    assert "workflow does not match config: run git-cicd generate" in text


def test_no_decisions_fails(config, repo):
    ok, verdict, _ = run_report(config, repo, None, {})
    assert not ok
    assert "no decisions" in verdict


def test_summary_written_when_set(config, repo, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    r = passed_result("test")
    r.update(state="failed", failed_step="ci/cov.sh", exit_code=4)
    run_report(config, repo, decision(test=(True, "r")), {"test": r})
    md = summary.read_text()
    assert md.startswith("## git-cicd verdict: FAILED")
    assert "| Job | State | Time | Detail |" in md
    assert "| test | failed | 6.2s | step ci/cov.sh, exit 4 |" in md
    assert "↳ `setup ci/setup.sh` | exit 0 | 1.2s" in md
    assert "↳ `step ci/cov.sh`" in md
    assert "| lint | not needed (non-blocking) |" in md


def test_summary_not_written_when_unset(config, repo, tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.chdir(tmp_path)
    run_report(config, repo, decision(), {})
    assert list(tmp_path.glob("*.md")) == []


def test_setup_note(config, repo):
    r = passed_result("test", setup=False)
    r["setup_skipped"] = True
    _, _, text = run_report(config, repo, decision(test=(True, "r")),
                            {"test": r}, setup_note=True)
    assert "setup skipped (pass --setup to run it)" in text


# ── the command, against files as artifacts land ────────────────────────────

def test_report_command(config, repo, tmp_path):
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    artifacts = tmp_path / "artifacts"
    (artifacts / "git-cicd-decisions").mkdir(parents=True)
    (artifacts / "git-cicd-result-test").mkdir(parents=True)
    (artifacts / "git-cicd-decisions" / "decisions.json").write_text(
        json.dumps(decision(test=(True, "1 changed file match paths"))))
    (artifacts / "git-cicd-result-test" / "result.json").write_text(
        json.dumps(passed_result("test")))
    summary = tmp_path / "summary.md"
    result = repo.run("report", "--decisions",
                      str(artifacts / "git-cicd-decisions" / "decisions.json"),
                      "--results", str(artifacts),
                      env={"GITHUB_STEP_SUMMARY": str(summary)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == \
        "PASSED - 1 of 3 jobs needed, 1 passed"
    assert "workflow matches config" in result.stdout
    assert "PASSED" in summary.read_text()


def test_report_command_fails_on_stale_workflow(config, repo, tmp_path):
    repo.install_tool()
    (tmp_path / "d.json").write_text(json.dumps(decision()))
    result = repo.run("report", "--decisions", str(tmp_path / "d.json"),
                      "--results", str(tmp_path / "none"))
    assert result.returncode == 1
    assert ("workflow does not match config: run "
            ".vendored/pkg/git-cicd/git-cicd generate") in result.stdout


def test_report_command_missing_decisions(config, repo, tmp_path):
    repo.install_tool()
    repo.run("generate")
    result = repo.run("report", "--decisions", str(tmp_path / "missing.json"),
                      "--results", str(tmp_path))
    assert result.returncode == 1
    assert "no decisions" in result.stdout


def test_report_cron_moment_not_built(config, repo, tmp_path):
    repo.install_tool()
    summary = tmp_path / "summary.md"
    result = repo.run("report", "--moment", "cron", "--decisions", "x",
                      "--results", "y",
                      env={"GITHUB_STEP_SUMMARY": str(summary)})
    assert result.returncode == 2
    assert "the cron moment is not built yet" in result.stderr
    assert "FAILED" in summary.read_text()


def test_load_results_ignores_other_json(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "r.json").write_text(json.dumps(
        {"job": "x", "state": "passed"}))
    (tmp_path / "a" / "junk.json").write_text("{nope")
    (tmp_path / "a" / "other.json").write_text("[1]")
    (tmp_path / "a" / "notes.txt").write_text("hi")
    assert list(git_cicd.load_results(str(tmp_path))) == ["x"]
