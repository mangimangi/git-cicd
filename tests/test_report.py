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


def test_report_command_merge(config, repo, tmp_path):
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    dec = decision(test=(True, "1 changed file match paths"))
    dec["trigger"] = "merge"
    (tmp_path / "d.json").write_text(json.dumps(dec))
    (tmp_path / "r").mkdir()
    res = passed_result("test")
    res.update(state="failed", failed_step="ci/cov.sh", exit_code=1)
    (tmp_path / "r" / "result.json").write_text(json.dumps(res))
    out = tmp_path / "verdict.txt"
    result = repo.run("report", "--trigger", "merge", "--decisions",
                      str(tmp_path / "d.json"), "--results",
                      str(tmp_path / "r"), "--verdict-out", str(out))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not built yet" not in result.stdout + result.stderr
    assert out.read_text().splitlines() == [
        "failure", "FAILED - 1 of 3 jobs needed, 1 failed"]


def test_report_manual_refusal_fails_with_the_reason(config, repo, tmp_path):
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    reason = 'job docs cannot be run by hand ("manual": false)'
    dec = decision(docs=(False, reason))
    dec.update(trigger="manual", job="docs", refused=reason)
    for j in dec["jobs"]:
        if j["name"] != "docs":
            j["reason"] = "not the job asked for"
    (tmp_path / "d.json").write_text(json.dumps(dec))
    out = tmp_path / "verdict.txt"
    summary = tmp_path / "summary.md"
    result = repo.run("report", "--trigger", "manual", "--decisions",
                      str(tmp_path / "d.json"), "--results",
                      str(tmp_path / "none"), "--verdict-out", str(out),
                      env={"GITHUB_STEP_SUMMARY": str(summary)})
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == f"FAILED - {reason}"
    assert out.read_text().splitlines() == ["failure", f"FAILED - {reason}"]
    assert "FAILED - job docs cannot be run by hand" in summary.read_text()
    assert f"not needed ({reason})" in result.stdout


def test_report_manual_run_passes(config, repo, tmp_path):
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    dec = decision(docs=(True, "manual run"))
    dec.update(trigger="manual", job="docs", refused=None)
    (tmp_path / "d.json").write_text(json.dumps(dec))
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "result.json").write_text(
        json.dumps(passed_result("docs", steps=("ci/docs.sh",), setup=False)))
    result = repo.run("report", "--trigger", "manual", "--decisions",
                      str(tmp_path / "d.json"), "--results", str(tmp_path / "r"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == \
        "PASSED - 1 of 3 jobs needed, 1 passed"


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


def as_medici(repo):
    """Name the repository medici the way every machine sees it: its origin
    remote (repo_name reads no environment variable)."""
    repo.git("remote", "add", "origin", "git@github.com:someone/medici.git")


def owned_report(repo, monkeypatch):
    as_medici(repo)
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
    as_medici(owned)
    config = git_cicd.load_config(str(owned.path))
    dec = owned_decision()
    dec["head"] = sha
    text = run_report(config, owned, dec, {"unit": owned_result()})[2]
    short = owned.git("rev-parse", "--short", sha)
    assert text.splitlines()[0].startswith(f"git-cicd report: medici at "
                                           f"{short} ")


def test_verdict_description_has_no_step_lines(owned, monkeypatch):
    owned.write("VERSION", "0.3.0\n")
    as_medici(owned)
    config = git_cicd.load_config(str(owned.path))
    _, verdict, _ = run_report(config, owned, owned_decision(),
                               {"unit": owned_result()})
    assert verdict == "PASSED - 1 of 1 jobs needed, 1 passed"
    assert "@" not in git_cicd.status_description(verdict)


def test_repo_name_sources(repo, monkeypatch):
    root = str(repo.path)
    # no environment variable decides the name, not even in Actions
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/from-actions")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    # no origin remote: the checkout's top-level directory
    assert git_cicd.repo_identity(root) == (
        repo.path.name, "the checkout's directory name")
    repo.git("remote", "add", "origin", "git@github.com:someone/medici.git")
    assert git_cicd.repo_identity(root) == ("medici",
                                            "the origin remote's URL")
    repo.git("remote", "set-url", "origin",
             "https://github.com/someone/other-repo")
    assert git_cicd.repo_name(root) == "other-repo"
    # the config's repository wins over both
    config = {"jobs": {}, "repository": "chosen"}
    assert git_cicd.repo_identity(root, config) == (
        "chosen", "the config's repository")
    assert git_cicd.repo_name(root, {"jobs": {}, "repository": None}) == \
        "other-repo"


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
    as_medici(repo)
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


# ── cron: one verdict per branch head ───────────────────────────────────────

@pytest.fixture
def cron_config(repo):
    for name in ("ci/a.sh", "ci/b.sh"):
        repo.script(name)
    repo.config({"jobs": {
        "nightly": {"on": ["cron"], "branches": ["main", "dev"],
                    "cron": "0 3 * * *", "steps": ["ci/a.sh"]},
        "test": {"on": ["open"], "branches": ["**"], "steps": ["ci/b.sh"]},
    }})
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    return git_cicd.load_config(str(repo.path))


MAIN_SHA = "a" * 40
DEV_SHA = "b" * 40


def cron_decision(heads=None):
    heads = heads if heads is not None else {"main": MAIN_SHA, "dev": DEV_SHA}
    runs, missing = [], []
    for n, (branch, sha) in enumerate(heads.items(), 1):
        if sha:
            runs.append({"key": f"nightly-{n}", "job": "nightly",
                         "branch": branch, "sha": sha})
        else:
            missing.append({"job": "nightly", "branch": branch,
                            "reason": f"branch {branch} does not exist"})
    return {"trigger": "cron", "cron": "0 3 * * *", "target": None,
            "source": None, "base": None, "head": None, "changed_files": [],
            "heads": heads, "runs": runs, "missing": missing,
            "jobs": [{"name": "nightly", "title": "Nightly", "needed": True,
                      "reason": "scheduled 0 3 * * *", "blocking": True},
                     {"name": "test", "title": "Test", "needed": False,
                      "reason": "not a cron job", "blocking": True}],
            "max_parallel": 3}


def cron_result(branch, sha, state="passed"):
    res = passed_result("nightly", steps=("ci/a.sh",), setup=False)
    res.update(target=branch, head=sha, state=state)
    if state == "failed":
        res.update(failed_step="ci/a.sh", exit_code=1)
    return res


def run_cron_report(repo, tmp_path, dec, results):
    (tmp_path / "d.json").write_text(json.dumps(dec))
    for i, res in enumerate(results):
        d = tmp_path / "r" / f"git-cicd-result-{i}"
        d.mkdir(parents=True)
        (d / "result.json").write_text(json.dumps(res))
    (tmp_path / "r").mkdir(exist_ok=True)
    out = tmp_path / "verdict.txt"
    result = repo.run("report", "--trigger=cron", "--decisions",
                      str(tmp_path / "d.json"), "--results",
                      str(tmp_path / "r"), "--verdict-out", str(out))
    lines = [l.split("\t") for l in out.read_text().splitlines()] \
        if out.exists() else None
    return result, lines


def test_cron_one_verdict_per_branch(cron_config, repo, tmp_path):
    result, lines = run_cron_report(repo, tmp_path, cron_decision(), [
        cron_result("main", MAIN_SHA),
        cron_result("dev", DEV_SHA, state="failed")])
    assert result.returncode == 1, result.stdout + result.stderr
    assert lines == [
        [MAIN_SHA, "success", "PASSED - 1 of 2 jobs needed, 1 passed"],
        [DEV_SHA, "failure", "FAILED - 1 of 2 jobs needed, 1 failed"]]
    assert "git-cicd report: repository on main at aaaaaaa" in result.stdout \
        or " on main at aaaaaaa" in result.stdout
    assert " on dev at bbbbbbb" in result.stdout
    assert result.stdout.splitlines()[-1] == (
        "FAILED - schedule 0 3 * * * on 2 branches, failed on dev")


def test_cron_all_passed(cron_config, repo, tmp_path):
    result, lines = run_cron_report(repo, tmp_path, cron_decision(), [
        cron_result("main", MAIN_SHA), cron_result("dev", DEV_SHA)])
    assert result.returncode == 0, result.stdout + result.stderr
    assert [l[1] for l in lines] == ["success", "success"]
    assert result.stdout.splitlines()[-1] == \
        "PASSED - schedule 0 3 * * * on 2 branches"


def test_cron_missing_result_fails_its_branch(cron_config, repo, tmp_path):
    result, lines = run_cron_report(repo, tmp_path, cron_decision(), [
        cron_result("main", MAIN_SHA)])
    assert result.returncode == 1
    assert lines[1] == [DEV_SHA, "failure",
                        "FAILED - 1 of 2 jobs needed, 1 could not run"]


def test_cron_missing_branch_fails(cron_config, repo, tmp_path):
    result, lines = run_cron_report(
        repo, tmp_path, cron_decision({"main": MAIN_SHA, "dev": None}),
        [cron_result("main", MAIN_SHA)])
    assert result.returncode == 1
    assert lines == [[MAIN_SHA, "success",
                      "PASSED - 1 of 2 jobs needed, 1 passed"]]
    assert "could not run (branch dev does not exist)" in result.stdout
    assert "FAILED - branch dev does not exist" in result.stdout
    assert result.stdout.splitlines()[-1].endswith("failed on dev")


def test_cron_branches_at_one_commit_share_a_failed_status(cron_config, repo,
                                                           tmp_path):
    dec = cron_decision({"main": MAIN_SHA, "dev": MAIN_SHA})
    result, lines = run_cron_report(repo, tmp_path, dec, [
        cron_result("main", MAIN_SHA, state="failed"),
        cron_result("dev", MAIN_SHA)])
    assert lines == [[MAIN_SHA, "failure",
                      "FAILED - 1 of 2 jobs needed, 1 failed"]]


def test_cron_nothing_scheduled_passes_without_statuses(cron_config, repo,
                                                        tmp_path):
    dec = cron_decision({})
    dec["jobs"][0].update(needed=False, reason="scheduled at 0 4 * * *")
    result, lines = run_cron_report(repo, tmp_path, dec, [])
    assert result.returncode == 0, result.stdout
    assert lines == []
    assert result.stdout.splitlines()[-1].startswith("PASSED - 0 of 2 jobs")


def test_cron_invalid_config_fails_every_head(repo, tmp_path):
    repo.install_tool()
    repo.config({"jobs": {"x": {"steps": ["ci/missing.sh"]}}})
    (tmp_path / "d.json").write_text(json.dumps(cron_decision()))
    out = tmp_path / "verdict.txt"
    result = repo.run("report", "--trigger=cron", "--decisions",
                      str(tmp_path / "d.json"), "--results", "y",
                      "--verdict-out", str(out))
    assert result.returncode == 2
    lines = [l.split("\t") for l in out.read_text().splitlines()]
    assert [l[:2] for l in lines] == [[MAIN_SHA, "failure"],
                                      [DEV_SHA, "failure"]]
    assert lines[0][2].startswith("FAILED - the config is invalid")


@pytest.mark.parametrize("version_file", ["../VERSION", "/etc/hostname", ""])
def test_version_file_outside_the_repository_is_never_read(owned, monkeypatch,
                                                           version_file):
    owned.write(".vendored/configs/git-semver.json",
                json.dumps({"version_file": version_file}) + "\n")
    owned.write("VERSION", "9.9.9\n")
    text = owned_report(owned, monkeypatch)
    assert "Unit Tests / medici:unit:test.sh  passed" in text
    assert "@" not in text


@pytest.mark.parametrize("content", ["\n", "1.0\x07\n"])
def test_blank_or_unprintable_version_is_no_version(owned, monkeypatch,
                                                    content):
    owned.write("VERSION", content)
    text = owned_report(owned, monkeypatch)
    assert "Unit Tests / medici:unit:test.sh  passed" in text
    assert "@" not in text


def test_old_result_step_label_that_does_not_split_names_itself(
        owned, monkeypatch):
    config = git_cicd.load_config(str(owned.path))
    result = owned_result()
    result["steps"] = [{"step": "ci/test.sh 'unbalanced", "seconds": 2.0,
                        "exit_code": 0, "error": None}]
    as_medici(owned)
    text = run_report(config, owned, owned_decision(), {"unit": result})[2]
    assert "Unit Tests / medici:unit:test.sh 'unbalanced  passed" in text


def test_job_rows_without_a_root_name_the_repository_without_a_version(owned):
    owned.write("VERSION", "0.3.0\n")
    config = git_cicd.load_config(str(owned.path))
    rows = git_cicd.job_rows(config, owned_decision(),
                             {"unit": owned_result()}, repo="medici")
    names = [child[0] for child in rows[0]["children"]]
    assert names[0] == "Unit Tests / medici:unit:setup.sh"
    assert "Unit Tests / medici:unit:test.sh" in names
    assert "Unit Tests / tool:unit:check.sh" in names
    assert not any("@" in n for n in names)


def test_refusal_with_stale_workflows_names_both(config, repo):
    reason = 'job docs cannot be run by hand ("manual": false)'
    dec = decision(docs=(False, reason))
    dec.update(trigger="manual", job="docs", refused=reason)
    ok, verdict, _ = run_report(config, repo, dec, {}, workflow=MISMATCH)
    assert not ok
    assert verdict == (f"FAILED - {reason}; the workflows do not match the "
                       "config")


def test_cron_branch_without_a_run_of_a_needed_job_is_not_needed(
        cron_config, repo, tmp_path):
    dec = cron_decision()
    dec["runs"] = [r for r in dec["runs"] if r["branch"] == "main"]
    result, lines = run_cron_report(repo, tmp_path, dec, [
        cron_result("main", MAIN_SHA)])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "not needed (not scheduled on dev)" in result.stdout
    assert lines[0] == [MAIN_SHA, "success",
                        "PASSED - 1 of 2 jobs needed, 1 passed"]
    assert lines[1][:2] == [DEV_SHA, "success"]
    assert lines[1][2].startswith("PASSED - 0 of 2 jobs needed")


def test_cron_report_without_verdict_out_writes_nothing(cron_config, repo,
                                                        tmp_path):
    (tmp_path / "d.json").write_text(json.dumps(cron_decision()))
    (tmp_path / "r").mkdir()
    result = repo.run("report", "--trigger=cron", "--decisions",
                      str(tmp_path / "d.json"), "--results",
                      str(tmp_path / "r"))
    assert result.returncode == 1
    assert result.stdout.splitlines()[-1].startswith("FAILED - schedule")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["d.json", "r",
                                                          "repo"]


def test_cron_report_without_decisions_writes_no_statuses(cron_config, repo,
                                                          tmp_path):
    out = tmp_path / "verdict.txt"
    result = repo.run("report", "--trigger=cron", "--decisions",
                      str(tmp_path / "missing.json"), "--results",
                      str(tmp_path), "--verdict-out", str(out))
    assert result.returncode == 1
    assert result.stdout.splitlines()[-1].startswith(
        "FAILED - no decisions: the decide step failed or did not run")
    assert out.read_text() == ""


@pytest.mark.parametrize("content", ["[]", '{"jobs": {}}', "not json"])
def test_decisions_that_are_not_a_decision_record_fail(config, repo, tmp_path,
                                                       content):
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    (tmp_path / "d.json").write_text(content)
    out = tmp_path / "verdict.txt"
    result = repo.run("report", "--decisions", str(tmp_path / "d.json"),
                      "--results", str(tmp_path), "--verdict-out", str(out))
    assert result.returncode == 1
    assert out.read_text().splitlines() == [
        "failure", "FAILED - no decisions: the decide step failed or did "
        "not run (see its log)"]


def test_report_names_ignored_form_fields(config, repo, tmp_path,
                                          monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    note = "ignored input vendor (job docs does not declare it)"
    dec = decision(docs=(True, "manual run"))
    dec.update(trigger="manual", job="docs", refused=None, ignored=[note])
    results = {"docs": passed_result("docs", steps=("ci/docs.sh",),
                                     setup=False)}
    ok, verdict, text = run_report(config, repo, dec, results)
    assert ok
    assert f"\n  {note}\nworkflows match config\n" in text
    assert f"\n- {note}\n" in summary.read_text()


@pytest.mark.parametrize("ignored", [None, "not a list", []])
def test_report_without_ignored_fields_has_no_notes(config, repo, ignored):
    dec = decision(docs=(True, "manual run"))
    dec.update(trigger="manual", job="docs", refused=None, ignored=ignored)
    results = {"docs": passed_result("docs", steps=("ci/docs.sh",),
                                     setup=False)}
    _, _, text = run_report(config, repo, dec, results)
    assert "ignored" not in text and "not a list" not in text


# ── absent declared secrets ─────────────────────────────────────────────────

def test_absent_secrets_named_on_the_row(config, repo, tmp_path,
                                         monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    r = passed_result("test")
    r["absent_secrets"] = ["CICD_WRITE_TOKEN", "not-a-secret-name"]
    _, _, text = run_report(config, repo, decision(test=(True, "r")),
                            {"test": r})
    lines = text.splitlines()
    i = lines.index(next(l for l in lines if l.startswith("  Test /")))
    assert "    declared secret CICD_WRITE_TOKEN is not set" in lines[i + 1:]
    # only documented names are shown, whatever a result file holds
    assert "not-a-secret-name" not in text
    assert "| &nbsp;&nbsp;↳ secrets | declared secret CICD_WRITE_TOKEN is " \
        "not set | | |" in summary.read_text()


def test_result_without_absent_secrets_reports_as_before(config, repo):
    r = passed_result("test")
    assert "absent_secrets" not in r
    _, _, text = run_report(config, repo, decision(test=(True, "r")),
                            {"test": r})
    assert "declared secret" not in text


def test_secret_value_never_printed(repo, tmp_path):
    """run-job, its result file and the report never hold a secret's
    value, set or not."""
    repo.script("ci/t.sh", "exit 0\n")
    repo.config({"jobs": {"t": {"on": ["open"], "branches": ["**"],
                                "steps": ["ci/t.sh"],
                                "secrets": ["CICD_WRITE_TOKEN",
                                            "CICD_READ_TOKEN"]}}})
    repo.install_tool()
    assert repo.run("generate").returncode == 0
    base = repo.commit("base")
    artifacts = tmp_path / "artifacts"
    (artifacts / "r").mkdir(parents=True)
    result_file = artifacts / "r" / "result.json"
    env = {"CICD_WRITE_TOKEN": "s3cret-write", "VENDOR_PAT": "s3cret-pat",
           "GITHUB_TOKEN": "s3cret-gh"}
    run = repo.run("run-job", "t", "--trigger=open", "--target=main",
                   "--source=f", f"--base={base}", f"--head={base}",
                   f"--result={result_file}", env=env)
    assert run.returncode == 0, run.stdout + run.stderr
    dec = tmp_path / "d.json"
    dec.write_text(json.dumps({
        "trigger": "open", "target": "main", "source": "f", "base": base,
        "head": base, "changed_files": [], "max_parallel": 3,
        "jobs": [{"name": "t", "needed": True, "reason": "r",
                  "blocking": True}]}))
    summary = tmp_path / "summary.md"
    rep = repo.run("report", "--decisions", str(dec), "--results",
                   str(artifacts),
                   env=dict(env, GITHUB_STEP_SUMMARY=str(summary)))
    assert rep.returncode == 0, rep.stdout + rep.stderr
    assert "declared secret CICD_READ_TOKEN is not set" in rep.stdout
    everything = (run.stdout + run.stderr + result_file.read_text()
                  + rep.stdout + rep.stderr + summary.read_text())
    assert "s3cret" not in everything
