"""Tests for the report: one line per job with times, and one verdict."""

import io
import json

import pytest

from tests.conftest import git_cicd

MATCH = (True, "workflows match config")
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
    return {"trigger": "open", "target": "main", "source": "f", "base": "b",
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
    assert "workflows match config" in text
    assert "passed  6.2s" in line_for(text, "Test /")


def test_times_present_for_every_job_and_step(config, repo):
    dec = decision(test=(True, "r"))
    ok, _, text = run_report(config, repo, dec, {"test": passed_result("test")})
    assert ok
    assert "Test / repo:test:setup.sh  passed  1.2s" in text
    assert text.count("Test / repo:test:test.sh  passed  2.5s") == 1
    assert text.count("Test / repo:test:cov.sh  passed  2.5s") == 1


def test_one_line_per_declared_job_in_config_order(config, repo):
    dec = decision(test=(True, "r"))
    _, _, text = run_report(config, repo, dec, {"test": passed_result("test")})
    names = [l.split()[0] for l in text.splitlines()
             if l.startswith("  ") and not l.startswith("    ")
             and l.split()[0] in ("Test", "Lint", "Docs")]
    assert names == ["Test", "Lint", "Docs"]
    assert "  Test / repo:test  passed" in text
    assert "not needed (no changed file matches paths) (non-blocking)" in \
        line_for(text, "Lint /")


def test_failed_step_named(config, repo):
    r = passed_result("test")
    r.update(state="failed", failed_step="ci/cov.sh", exit_code=4)
    r["steps"][1]["exit_code"] = 4
    ok, verdict, text = run_report(config, repo, decision(test=(True, "r")),
                                   {"test": r})
    assert not ok
    assert "failed (step ci/cov.sh, exit 4)" in line_for(text, "Test /")
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
    assert "could not run (setup failed)" in line_for(text, "Test /")
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
        line_for(text, "Lint /")
    assert verdict == ("PASSED - 2 of 3 jobs needed, 1 passed, 1 failed "
                       "(1 non-blocking)")


def test_non_blocking_could_not_run_passes(config, repo):
    dec = decision(lint=(True, "r"))
    ok, _, text = run_report(config, repo, dec, {})
    assert ok
    assert "could not run (no result) (non-blocking)" in line_for(text, "Lint /")


def test_none_needed(config, repo):
    reason = "only needs_nothing files changed"
    dec = decision(test=(False, reason), lint=(False, reason),
                   docs=(False, reason))
    ok, verdict, text = run_report(config, repo, dec, {})
    assert ok
    assert verdict == ("PASSED - 0 of 3 jobs needed: only needs_nothing files "
                       "changed")
    assert "not needed (only needs_nothing files changed)" in \
        line_for(text, "Test /")


def test_base_matches_no_branches(config, repo):
    dec = decision(**{n: (False, "target plan/x does not match branches")
                      for n in ("test", "lint", "docs")})
    ok, verdict, text = run_report(config, repo, dec, {})
    assert ok
    for name in ("test", "lint", "docs"):
        assert "does not match branches" in line_for(text, name.capitalize() + " /")
    assert verdict == ("PASSED - 0 of 3 jobs needed: target plan/x does not "
                       "match branches")


def test_missing_result_is_could_not_run(config, repo):
    ok, verdict, text = run_report(config, repo, decision(test=(True, "r")),
                                   {})
    assert not ok
    assert "could not run (no result)" in line_for(text, "Test /")
    assert verdict.startswith("FAILED")


def test_workflow_mismatch_fails(config, repo):
    ok, verdict, text = run_report(config, repo, decision(), {},
                                   workflow=MISMATCH)
    assert not ok
    assert verdict.startswith("FAILED - 0 of 3 jobs needed")
    assert verdict.endswith("; the workflows do not match the config")
    assert "workflows do not match config: run git-cicd generate" in text


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
    assert md.startswith("## Verdict / git-cicd:verdict: FAILED")
    assert "| Job | State | Time | Detail |" in md
    assert "| `Test / repo:test` | failed | 6.2s | step ci/cov.sh, exit 4 |" \
        in md
    assert "↳ `Test / repo:test:setup.sh` | passed | 1.2s" in md
    assert "↳ `Test / repo:test:cov.sh`" in md
    assert "| `Lint / repo:lint` | not needed (non-blocking) |" in md
    assert "git-cicd report: repo at h" in md


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
    assert "workflows match config" in result.stdout
    assert "PASSED" in summary.read_text()


def test_report_command_fails_on_stale_workflow(config, repo, tmp_path):
    repo.install_tool()
    (tmp_path / "d.json").write_text(json.dumps(decision()))
    result = repo.run("report", "--decisions", str(tmp_path / "d.json"),
                      "--results", str(tmp_path / "none"))
    assert result.returncode == 1
    assert ("workflows do not match config: run "
            ".vendored/pkg/git-cicd/git-cicd generate") in result.stdout


def test_report_command_missing_decisions(config, repo, tmp_path):
    repo.install_tool()
    repo.run("generate")
    result = repo.run("report", "--decisions", str(tmp_path / "missing.json"),
                      "--results", str(tmp_path))
    assert result.returncode == 1
    assert "no decisions" in result.stdout


def test_report_cron_trigger_not_built(config, repo, tmp_path):
    repo.install_tool()
    summary = tmp_path / "summary.md"
    result = repo.run("report", "--trigger", "cron", "--decisions", "x",
                      "--results", "y",
                      env={"GITHUB_STEP_SUMMARY": str(summary)})
    assert result.returncode == 2
    assert "the cron trigger is not built yet" in result.stderr
    assert "FAILED" in summary.read_text()


def test_load_results_ignores_other_json(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "r.json").write_text(json.dumps(
        {"job": "x", "state": "passed"}))
    (tmp_path / "a" / "junk.json").write_text("{nope")
    (tmp_path / "a" / "other.json").write_text("[1]")
    (tmp_path / "a" / "notes.txt").write_text("hi")
    assert list(git_cicd.load_results(str(tmp_path))) == ["x"]


# ── --verdict-out: what the workflow sets the `Verdict / git-cicd:verdict`
# status to ──

def test_verdict_out_passed(config, repo, tmp_path):
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    (tmp_path / "d.json").write_text(json.dumps(decision()))
    out = tmp_path / "v" / "verdict.txt"
    result = repo.run("report", "--decisions", str(tmp_path / "d.json"),
                      "--results", str(tmp_path / "none"),
                      "--verdict-out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    state, description = out.read_text().splitlines()
    assert state == "success"
    assert description.startswith("PASSED - 0 of 3 jobs needed: ")
    assert description == result.stdout.splitlines()[-1]


def test_verdict_out_failed_job(config, repo, tmp_path):
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    (tmp_path / "d.json").write_text(json.dumps(
        decision(test=(True, "1 changed file match paths"))))
    res = passed_result("test")
    res.update(state="failed", failed_step="ci/cov.sh", exit_code=1)
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "result.json").write_text(json.dumps(res))
    out = tmp_path / "verdict.txt"
    result = repo.run("report", "--decisions", str(tmp_path / "d.json"),
                      "--results", str(tmp_path / "r"),
                      "--verdict-out", str(out))
    assert result.returncode == 1
    state, description = out.read_text().splitlines()
    assert state == "failure"
    assert description == "FAILED - 1 of 3 jobs needed, 1 failed"


def test_verdict_out_stale_workflow_fails(config, repo, tmp_path):
    repo.install_tool()
    (tmp_path / "d.json").write_text(json.dumps(decision()))
    out = tmp_path / "verdict.txt"
    result = repo.run("report", "--decisions", str(tmp_path / "d.json"),
                      "--results", str(tmp_path / "none"),
                      "--verdict-out", str(out))
    assert result.returncode == 1
    assert out.read_text().splitlines()[0] == "failure"


def test_verdict_out_trigger_not_built(config, repo, tmp_path):
    repo.install_tool()
    out = tmp_path / "verdict.txt"
    result = repo.run("report", "--trigger", "cron", "--decisions", "x",
                      "--results", "y", "--verdict-out", str(out))
    assert result.returncode == 2
    state, description = out.read_text().splitlines()
    assert state == "failure"
    assert "the cron trigger is not built yet" in description


def test_verdict_out_invalid_config(repo, tmp_path):
    repo.install_tool()
    repo.config({"jobs": {"x": {"steps": ["ci/missing.sh"]}}})
    out = tmp_path / "verdict.txt"
    result = repo.run("report", "--decisions", "x", "--results", "y",
                      "--verdict-out", str(out))
    assert result.returncode == 2
    state, description = out.read_text().splitlines()
    assert state == "failure"
    assert description.startswith("FAILED - the config is invalid: ")


def test_status_description_is_one_short_line():
    assert git_cicd.status_description("PASSED - a\nb") == "PASSED - a b"
    long = git_cicd.status_description("FAILED - " + "x" * 300)
    assert len(long) == git_cicd.STATUS_DESCRIPTION_MAX
    assert long.endswith("...")


# ── names, owners and versions ──────────────────────────────────────────────

@pytest.fixture
def owned(repo):
    """A job with a repository step and steps under .vendored/pkg/."""
    repo.script("ci/setup.sh")
    repo.script("ci/test.sh")
    repo.script(".vendored/pkg/tool/check.sh")
    repo.script(".vendored/pkg/bare/lint.sh")
    repo.config({"jobs": {
        "unit": {"name": "Unit Tests", "on": ["open"], "branches": ["**"],
                 "setup": "ci/setup.sh",
                 "steps": ["ci/test.sh", ".vendored/pkg/tool/check.sh",
                           [".vendored/pkg/bare/lint.sh", "--x"]]},
    }})
    return repo


def owned_result():
    return {"job": "unit", "state": "passed", "failed_step": None,
            "exit_code": 0, "error": None,
            "setup": {"script": "ci/setup.sh", "seconds": 1.0,
                      "exit_code": 0, "error": None},
            "setup_skipped": False,
            "steps": [
                {"step": "ci/test.sh", "file": "ci/test.sh", "seconds": 2.0,
                 "exit_code": 0, "error": None},
                {"step": ".vendored/pkg/tool/check.sh",
                 "file": ".vendored/pkg/tool/check.sh", "seconds": 3.0,
                 "exit_code": 0, "error": None},
                # an older result without "file": the label's first word
                {"step": ".vendored/pkg/bare/lint.sh --x", "seconds": 4.0,
                 "exit_code": 2, "error": None},
            ],
            "seconds": 10.0}


def owned_decision():
    return {"trigger": "open", "target": "main", "source": "f", "base": "b",
            "head": "0123456789abcdef0123", "changed_files": [],
            "jobs": [{"name": "unit", "title": "Unit Tests", "needed": True,
                      "reason": "r", "blocking": True}], "max_parallel": 3}


def owned_report(repo, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/medici")
    config = git_cicd.load_config(str(repo.path))
    return run_report(config, repo, owned_decision(),
                      {"unit": owned_result()})[2]


def test_step_lines_vendored_with_manifest_and_repo_with_version(
        owned, monkeypatch):
    owned.write(".vendored/manifests/tool.version", "1.4.2\n")
    owned.write("VERSION", "0.3.0\n")
    text = owned_report(owned, monkeypatch)
    assert "  Unit Tests / medici:unit  failed" not in text
    assert "  Unit Tests / medici:unit  passed  10.0s" in text
    assert "    Unit Tests / medici@0.3.0:unit:setup.sh  passed  1.0s" in text
    assert "    Unit Tests / medici@0.3.0:unit:test.sh  passed  2.0s" in text
    assert "    Unit Tests / tool@1.4.2:unit:check.sh  passed  3.0s" in text
    # a vendor with no manifest version: no @, never a guessed version
    assert "    Unit Tests / bare:unit:lint.sh  failed (exit 2)  4.0s" in text


def test_step_lines_repo_without_version(owned, monkeypatch):
    text = owned_report(owned, monkeypatch)
    assert "    Unit Tests / medici:unit:test.sh  passed" in text
    assert "    Unit Tests / tool:unit:check.sh  passed" in text
    assert "@" not in text


def test_repo_version_file_from_git_semver_config(owned, monkeypatch):
    owned.write(".vendored/configs/git-semver.json",
                '{"version_file": "meta/version.txt"}\n')
    owned.write("VERSION", "9.9.9\n")
    owned.write("meta/version.txt", "2.0.1\n")
    text = owned_report(owned, monkeypatch)
    assert "Unit Tests / medici@2.0.1:unit:test.sh" in text
    assert "9.9.9" not in text


def test_header_gives_the_short_head_commit(owned, monkeypatch):
    owned.write("VERSION", "0.3.0\n")
    text = owned_report(owned, monkeypatch)
    header = text.splitlines()[0]
    assert header.startswith("git-cicd report: medici at 0123456 ")
    assert "change under test" in header


def test_header_resolves_head_in_the_repository(owned, monkeypatch):
    sha = owned.commit("c")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/medici")
    config = git_cicd.load_config(str(owned.path))
    dec = owned_decision()
    dec["head"] = sha
    text = run_report(config, owned, dec, {"unit": owned_result()})[2]
    short = owned.git("rev-parse", "--short", sha)
    assert text.splitlines()[0].startswith(f"git-cicd report: medici at "
                                           f"{short} ")


def test_verdict_description_has_no_step_lines(owned, monkeypatch):
    owned.write("VERSION", "0.3.0\n")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/medici")
    config = git_cicd.load_config(str(owned.path))
    _, verdict, _ = run_report(config, owned, owned_decision(),
                               {"unit": owned_result()})
    assert verdict == "PASSED - 1 of 1 jobs needed, 1 passed"
    assert "@" not in git_cicd.status_description(verdict)


def test_repo_name_sources(repo, monkeypatch):
    root = str(repo.path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/from-actions")
    assert git_cicd.repo_name(root) == "from-actions"
    monkeypatch.delenv("GITHUB_REPOSITORY")
    # no origin remote: the checkout's top-level directory
    assert git_cicd.repo_name(root) == repo.path.name
    repo.git("remote", "add", "origin", "git@github.com:someone/medici.git")
    assert git_cicd.repo_name(root) == "medici"
    repo.git("remote", "set-url", "origin",
             "https://github.com/someone/other-repo")
    assert git_cicd.repo_name(root) == "other-repo"


def test_markdown_shows_names_literally(owned, monkeypatch, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    owned.config({"jobs": {"unit": {
        "name": "a `b` | c", "on": ["open"], "branches": ["**"],
        "setup": "ci/setup.sh",
        "steps": ["ci/test.sh", ".vendored/pkg/tool/check.sh",
                  [".vendored/pkg/bare/lint.sh", "--x"]]}}})
    owned_report(owned, monkeypatch)
    md = summary.read_text()
    assert "| ``a `b` \\| c / medici:unit`` | passed |" in md


# ── title case: by default, never by rewriting ──────────────────────────────

def test_rows_and_step_lines_title_case_default_and_written_name(
        repo, monkeypatch):
    """A job without `name` shows its job name in title case; a written
    `name` shows exactly as written, mixed case included."""
    repo.script("ci/test.sh")
    repo.script("ci/up.sh")
    repo.config({"jobs": {
        "unit-tests": {"on": ["open"], "branches": ["**"],
                       "steps": ["ci/test.sh"]},
        "pypi": {"name": "PyPI upload", "on": ["open"], "branches": ["**"],
                 "steps": ["ci/up.sh"]},
        "types": {"name": "mypy", "on": ["open"], "branches": ["**"],
                  "steps": ["ci/test.sh"]},
    }})
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/medici")
    config = git_cicd.load_config(str(repo.path))
    dec = {"trigger": "open", "target": "main", "source": "f", "base": "b",
           "head": "h", "changed_files": [], "max_parallel": 3,
           "jobs": [{"name": n, "needed": True, "reason": "r",
                     "blocking": True} for n in ("unit-tests", "pypi",
                                                 "types")]}
    results = {
        "unit-tests": passed_result("unit-tests", ("ci/test.sh",), False),
        "pypi": passed_result("pypi", ("ci/up.sh",), False),
        "types": passed_result("types", ("ci/test.sh",), False)}
    text = run_report(config, repo, dec, results)[2]
    assert "  Unit Tests / medici:unit-tests  passed" in text
    assert "    Unit Tests / medici:unit-tests:test.sh  passed" in text
    assert "  PyPI upload / medici:pypi " in text
    assert "    PyPI upload / medici:pypi:up.sh  passed" in text
    assert "  mypy / medici:types " in text
    assert "Mypy" not in text and "Pypi" not in text and "unit-tests /" \
        not in text
