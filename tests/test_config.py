"""Tests for loading and validating .vendored/configs/git-cicd.json."""

import json

import pytest

from tests.conftest import git_cicd


@pytest.fixture
def scripts(repo):
    for name in ("ci/setup.sh", "ci/test.sh", "ci/coverage.sh", "ci/bump.sh",
                 "ci/publish.sh"):
        repo.script(name)
    return repo


STRAWMAN = {
    "jobs": {
        "test": {"on": ["open"], "branches": ["**"],
                 "paths": ["medici/**", "tests/**"], "setup": "ci/setup.sh",
                 "steps": ["ci/test.sh", "ci/coverage.sh"]},
        "release": {"on": ["merge"], "branches": ["main"],
                    "steps": ["ci/bump.sh", "ci/publish.sh"]},
    }
}


def job(**fields):
    base = {"on": ["open"], "branches": ["**"], "steps": ["ci/test.sh"]}
    base.update(fields)
    return base


def refused(repo, config, *expected):
    """Assert the config is refused (exit 2) naming every expected text."""
    repo.config(config)
    result = repo.run("validate")
    assert result.returncode == 2, result.stdout + result.stderr
    for text in expected:
        assert text in result.stderr, result.stderr
    return result


def test_strawman_validates(scripts):
    scripts.config(STRAWMAN)
    result = scripts.run("validate")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "config ok: 2 jobs"


def test_strawman_normalized(scripts):
    scripts.config(STRAWMAN)
    config = git_cicd.load_config(str(scripts.path))
    test = config["jobs"]["test"]
    assert test["steps"] == [["ci/test.sh"], ["ci/coverage.sh"]]
    assert test["setup"] == "ci/setup.sh"
    assert test["manual"] is True and test["blocking"] is True
    assert config["jobs"]["release"]["paths"] is None
    assert config["max_parallel"] == 3
    assert config["needs_nothing"] == []
    assert list(config["jobs"]) == ["test", "release"]


def test_all_optional_fields_accepted(scripts):
    config = {
        "_vendor": {"repo": "mangimangi/git-cicd", "anything": [1, 2]},
        "jobs": {
            "test": job(paths=["src/**"], setup="ci/setup.sh",
                        steps=["ci/test.sh", ["ci/coverage.sh", "--min", "80",
                                              "$(x); `y` && z"]],
                        manual=False, blocking=False),
            "nightly": {"on": ["cron", "open", "merge"],
                        "branches": ["main", "plan/x"],
                        "cron": "0 3 * * 1", "steps": ["ci/test.sh"]},
            "manual-only": {"branches": ["main"], "steps": ["ci/test.sh"]},
            "empty_on": {"on": [], "branches": ["**"],
                         "steps": ["ci/test.sh"]},
        },
        "needs_nothing": [".pearls/**", "*.md"],
        "max_parallel": 5,
    }
    scripts.config(config)
    result = scripts.run("validate")
    assert result.returncode == 0, result.stderr
    loaded = git_cicd.load_config(str(scripts.path))
    assert loaded["max_parallel"] == 5
    assert loaded["needs_nothing"] == [".pearls/**", "*.md"]
    test = loaded["jobs"]["test"]
    assert test["manual"] is False and test["blocking"] is False
    assert test["steps"][1] == ["ci/coverage.sh", "--min", "80",
                                "$(x); `y` && z"]
    assert loaded["jobs"]["nightly"]["cron"] == "0 3 * * 1"
    assert loaded["jobs"]["manual-only"]["on"] == []


def test_vendor_key_ignored(scripts):
    scripts.config({"_vendor": "not even an object", "jobs": {}})
    assert scripts.run("validate").returncode == 0


def test_empty_jobs_valid(repo):
    repo.config({"jobs": {}, "needs_nothing": []})
    result = repo.run("validate")
    assert result.returncode == 0
    assert "config ok: 0 jobs" in result.stdout


def test_explicit_config_path(scripts):
    scripts.write("other.json", json.dumps(STRAWMAN))
    result = scripts.run("validate", "--config", "other.json")
    assert result.returncode == 0, result.stderr


def test_runs_from_subdirectory(scripts):
    scripts.config(STRAWMAN)
    (scripts.path / "ci").mkdir(exist_ok=True)
    result = scripts.run("validate", cwd=scripts.path / "ci")
    assert result.returncode == 0, result.stderr


# ── refusals ────────────────────────────────────────────────────────────────

def test_job_without_branches(scripts):
    j = job()
    del j["branches"]
    refused(scripts, {"jobs": {"test": j}},
            "job test: missing required field branches")


def test_job_with_empty_branches(scripts):
    refused(scripts, {"jobs": {"test": job(branches=[])}},
            "job test: missing required field branches")


def test_step_not_a_file(scripts):
    refused(scripts, {"jobs": {"test": job(steps=["ci/missing.sh"])}},
            "job test: step 1: ci/missing.sh is not a file in the repository")


def test_step_is_a_directory(scripts):
    refused(scripts, {"jobs": {"test": job(steps=["ci"])}},
            "job test: step 1: ci is not a file")


def test_step_not_executable(scripts):
    scripts.write("ci/plain.sh", "echo hi\n")
    refused(scripts, {"jobs": {"test": job(steps=["ci/plain.sh"])}},
            "job test: step 1: ci/plain.sh is not executable")


def test_step_shell_string(scripts):
    refused(scripts, {"jobs": {"test": job(steps=["ci/test.sh --fast"])}},
            "job test: step 1:", "whitespace", "array form")


def test_step_absolute_path(scripts):
    refused(scripts, {"jobs": {"test": job(steps=["/bin/true"])}},
            "job test: step 1: /bin/true is an absolute path")


def test_step_dotdot(scripts):
    refused(scripts, {"jobs": {"test": job(steps=["ci/../ci/test.sh"])}},
            "job test: step 1:", "'..' segment")


def test_step_empty_array(scripts):
    refused(scripts, {"jobs": {"test": job(steps=[[]])}},
            "job test: step 1: empty array")


def test_step_array_with_non_string(scripts):
    refused(scripts, {"jobs": {"test": job(steps=[["ci/test.sh", 3]])}},
            "job test: step 1: every element of an array step must be a "
            "string")


def test_step_wrong_type(scripts):
    refused(scripts, {"jobs": {"test": job(steps=[{"run": "x"}])}},
            "job test: step 1: a step must be a file")


def test_step_array_file_missing(scripts):
    refused(scripts, {"jobs": {"test": job(steps=[["ci/nope.sh", "-x"]])}},
            "job test: step 1: ci/nope.sh is not a file")


def test_steps_missing_or_empty(scripts):
    j = job()
    del j["steps"]
    refused(scripts, {"jobs": {"a": j, "b": job(steps=[])}},
            "job a: missing required field steps",
            "job b: steps must be a non-empty array")


def test_setup_not_a_file(scripts):
    refused(scripts, {"jobs": {"test": job(setup="ci/nope.sh")}},
            "job test: setup: ci/nope.sh is not a file in the repository")


def test_setup_not_executable(scripts):
    scripts.write("ci/plain.sh", "echo hi\n")
    refused(scripts, {"jobs": {"test": job(setup="ci/plain.sh")}},
            "job test: setup: ci/plain.sh is not executable")


def test_setup_shell_string(scripts):
    refused(scripts, {"jobs": {"test": job(setup="ci/setup.sh && rm -rf")}},
            "job test: setup", "whitespace")


def test_setup_wrong_type(scripts):
    refused(scripts, {"jobs": {"test": job(setup=["ci/setup.sh"])}},
            "job test: setup must be one repository path")


def test_unknown_trigger(scripts):
    refused(scripts, {"jobs": {"test": job(on=["open", "push"])}},
            "job test: unknown trigger 'push' in on")


def test_duplicate_trigger(scripts):
    refused(scripts, {"jobs": {"test": job(on=["open", "open"])}},
            "job test: trigger open listed more than once")


def test_on_wrong_type(scripts):
    refused(scripts, {"jobs": {"test": job(on="open")}},
            "job test: on must be an array")


def test_cron_without_expression(scripts):
    refused(scripts, {"jobs": {"nightly": job(on=["cron"], branches=["main"])}},
            "job nightly: on contains cron but no cron expression is given")


def test_cron_expression_without_cron_trigger(scripts):
    refused(scripts, {"jobs": {"test": job(cron="0 3 * * *")}},
            "job test: cron is set but on does not contain cron")


def test_cron_expression_malformed(scripts):
    refused(scripts, {"jobs": {"n": job(on=["cron"], branches=["main"],
                                         cron="0 3 * *")}},
            "job n: cron '0 3 * *' is not a cron expression")


def test_cron_expression_wrong_type(scripts):
    refused(scripts, {"jobs": {"n": job(on=["cron"], branches=["main"],
                                         cron=5)}},
            "job n: cron must be a string")


@pytest.mark.parametrize("branch", ["**", "plan/*", "v?", "rel[12]"])
def test_cron_job_with_pattern_branches(scripts, branch):
    refused(scripts, {"jobs": {"n": job(on=["cron"], branches=["main", branch],
                                         cron="0 3 * * *")}},
            f"job n: a cron job's branches are literal names; {branch!r} is "
            "a pattern")


def test_unknown_job_field(scripts):
    refused(scripts, {"jobs": {"test": job(runs_on="ubuntu")}},
            "job test: unknown field runs_on")


def test_unknown_top_level_field(scripts):
    refused(scripts, {"jobs": {}, "parallel": 2},
            "config: unknown field parallel")


def test_comment_keys_refused(scripts):
    refused(scripts, {"jobs": {}, "_comment_jobs": "hello"},
            "config: unknown field _comment_jobs")


def test_missing_jobs(scripts):
    refused(scripts, {"needs_nothing": []},
            "config: missing required field jobs")


def test_jobs_wrong_type(scripts):
    refused(scripts, {"jobs": []}, "config: jobs must be an object")


def test_job_wrong_type(scripts):
    refused(scripts, {"jobs": {"test": "ci/test.sh"}},
            "job test: a job must be an object")


def test_invalid_job_name(scripts):
    refused(scripts, {"jobs": {"my job": job()}},
            "job my job: invalid job name")


@pytest.mark.parametrize("value", [0, -1, "3", 1.5, True])
def test_max_parallel_wrong(scripts, value):
    refused(scripts, {"jobs": {}, "max_parallel": value},
            "config: max_parallel must be a positive integer")


def test_needs_nothing_wrong_type(scripts):
    refused(scripts, {"jobs": {}, "needs_nothing": "docs/**"},
            "config: needs_nothing must be an array")


@pytest.mark.parametrize("flag", ["manual", "blocking"])
def test_flags_must_be_boolean(scripts, flag):
    refused(scripts, {"jobs": {"test": job(**{flag: "false"})}},
            f"job test: {flag} must be a boolean")


def test_paths_wrong_type(scripts):
    refused(scripts, {"jobs": {"test": job(paths="src/**")}},
            "job test: paths must be an array")


def test_branches_wrong_type(scripts):
    refused(scripts, {"jobs": {"test": job(branches="main")}},
            "job test: branches must be an array")


def test_branches_empty_pattern(scripts):
    refused(scripts, {"jobs": {"test": job(branches=[""])}},
            "job test: branches contains an empty pattern")


def test_top_level_not_object(scripts):
    scripts.write(".vendored/configs/git-cicd.json", "[]")
    result = scripts.run("validate")
    assert result.returncode == 2
    assert "top level must be a JSON object" in result.stderr


def test_all_errors_reported_one_per_line(scripts):
    j = job(on=["push"])
    del j["branches"]
    result = refused(scripts, {"jobs": {"a": j, "b": job(bogus=1)},
                               "extra": 1},
                     "job a: missing required field branches",
                     "job a: unknown trigger 'push'",
                     "job b: unknown field bogus",
                     "config: unknown field extra")
    assert len(result.stderr.strip().splitlines()) == 4


def test_missing_config_file(repo):
    result = repo.run("validate")
    assert result.returncode == 2
    assert "cannot read" in result.stderr


def test_invalid_json(repo):
    repo.write(".vendored/configs/git-cicd.json", "{nope")
    result = repo.run("validate")
    assert result.returncode == 2
    assert "is not valid JSON" in result.stderr


def test_outside_git_repository(tmp_path):
    import subprocess
    import sys
    from tests.conftest import SCRIPT
    result = subprocess.run([sys.executable, str(SCRIPT), "validate"],
                            cwd=tmp_path, capture_output=True, text=True,
                            env={"PATH": "/usr/bin:/bin",
                                 "GIT_CEILING_DIRECTORIES": str(tmp_path)})
    assert result.returncode == 2
    assert "not inside a git repository" in result.stderr


def test_main_in_process(scripts, capsys):
    scripts.config(STRAWMAN)
    assert git_cicd.main(["validate"]) == 0
    assert "config ok: 2 jobs" in capsys.readouterr().out


# ── name (display name) ─────────────────────────────────────────────────────

def test_name_validates(scripts):
    scripts.config({"jobs": {"test": job(name="Unit Tests")}})
    result = scripts.run("validate")
    assert result.returncode == 0, result.stderr
    config = git_cicd.load_config(str(scripts.path))
    assert config["jobs"]["test"]["title"] == "Unit Tests"
    assert config["jobs"]["test"]["name"] == "test"


def test_name_defaults_to_job_name_in_title_case(scripts):
    scripts.config({"jobs": {"test": job(), "unit-tests": job(),
                             "build_docs-fast": job(), "e2e": job(),
                             "ci-PyPI": job()}})
    config = git_cicd.load_config(str(scripts.path))
    titles = {n: j["title"] for n, j in config["jobs"].items()}
    assert titles == {"test": "Test", "unit-tests": "Unit Tests",
                      "build_docs-fast": "Build Docs Fast", "e2e": "E2e",
                      "ci-PyPI": "Ci PyPI"}


@pytest.mark.parametrize("name", ["PyPI", "mypy", "unit tests",
                                  "Release to npm", "pre-COMMIT"])
def test_written_name_is_shown_exactly_as_written(scripts, name):
    """git-cicd never changes the case of a name the repository wrote."""
    scripts.config({"jobs": {"test": job(name=name)}})
    config = git_cicd.load_config(str(scripts.path))
    assert config["jobs"]["test"]["title"] == name


def test_default_title():
    assert git_cicd.default_title("unit-tests") == "Unit Tests"
    assert git_cicd.default_title("a__b--c") == "A B C"
    assert git_cicd.default_title("x") == "X"
    assert git_cicd.default_title("-") == "-"


def test_name_with_shell_metacharacters_is_data(scripts):
    name = "It's \"$(touch pwned)\" `id` $HOME; | &"
    scripts.config({"jobs": {"test": job(name=name)}})
    config = git_cicd.load_config(str(scripts.path))
    assert config["jobs"]["test"]["title"] == name


@pytest.mark.parametrize("value,reason", [
    (42, "name must be a string"),
    (None, "name must be a string"),
    (["a"], "name must be a string"),
    ("", "name is empty"),
    ("   ", "name is empty"),
    ("two\nlines", "must be a single line"),
    ("cr\rhere", "must be a single line"),
    ("tab\there", "must be a single line"),
])
def test_bad_name_refused(scripts, value, reason):
    refused(scripts, {"jobs": {"test": job(name=value)}},
            "job test: name", reason)


# ── declared inputs ─────────────────────────────────────────────────────────

# What today's workflows take, as declarations (version-bump.yml,
# install-vendored.yml, git-vendored's validate).
TODAYS_INPUTS = {
    "release": {
        "bump_type": {"description": "Version bump type",
                      "choices": ["patch", "minor", "major"],
                      "default": "patch"},
        "subdirectory": {"description": "Subdirectory to bump (leave empty "
                                        "for root)", "default": ""},
        "changelog_description": {"description": "Changelog entry"},
    },
    "update": {
        "vendor": {"default": "all"},
        "version": {"default": "latest"},
        "private": {"choices": ["true", "false"], "default": "false"},
    },
    "validate": {
        "repo": {"required": True, "description": "owner/name"},
        "version": {"default": ""},
    },
}


def test_todays_workflow_inputs_validate(scripts):
    # validate's version (default "") cannot share update's form field
    # (default latest), so validate is not run by hand here
    scripts.config({"jobs": {name: job(inputs=inputs,
                                       manual=name != "validate")
                             for name, inputs in TODAYS_INPUTS.items()}})
    result = scripts.run("validate")
    assert result.returncode == 0, result.stderr
    config = git_cicd.load_config(str(scripts.path))
    bump = config["jobs"]["release"]["inputs"]["bump_type"]
    assert bump == {"description": "Version bump type", "required": False,
                    "default": "patch", "choices": ["patch", "minor", "major"]}
    assert config["jobs"]["validate"]["inputs"]["repo"]["required"] is True
    assert config["jobs"]["release"]["inputs"]["changelog_description"][
        "default"] is None


def test_no_inputs_normalizes_to_empty(scripts):
    scripts.config({"jobs": {"t": job()}})
    assert git_cicd.load_config(str(scripts.path))["jobs"]["t"]["inputs"] == {}


@pytest.mark.parametrize("inputs,expected", [
    (["x"], "job t: inputs must be an object (input name -> declaration)"),
    ({"Bump": {}}, "job t: input Bump: invalid input name"),
    ({"1x": {}}, "job t: input 1x: invalid input name"),
    ({"a-b": {}}, "job t: input a-b: invalid input name"),
    ({"x": "patch"}, "job t: input x: a declaration must be an object"),
    ({"x": {"type": "choice"}}, "job t: input x: unknown field type"),
    ({"x": {"default": 1}}, "job t: input x: default must be a string"),
    ({"x": {"default": True}}, "job t: input x: default must be a string"),
    ({"x": {"description": 5}},
     "job t: input x: description must be a single-line string"),
    ({"x": {"description": "two\nlines"}},
     "job t: input x: description must be a single-line string"),
    ({"x": {"choices": ["a"], "default": "b"}},
     "job t: input x: default 'b' is not one of the choices (a)"),
    ({"x": {"choices": []}},
     "job t: input x: choices must be a non-empty array of strings"),
    ({"x": {"choices": "a"}},
     "job t: input x: choices must be a non-empty array of strings"),
    ({"x": {"choices": ["a", "a"]}},
     "job t: input x: choice 'a' is listed more than once"),
    ({"x": {"choices": ["a", True]}},
     "job t: input x: every choice must be a string"),
    ({"x": {"required": "yes"}}, "job t: input x: required must be a boolean"),
    ({"x": {"required": True, "default": "a"}},
     "job t: input x: a required input cannot have a default"),
])
def test_malformed_inputs_refused(scripts, inputs, expected):
    refused(scripts, {"jobs": {"t": job(inputs=inputs)}}, expected)


def test_inputs_is_a_known_job_field():
    assert "inputs" in git_cicd.JOB_FIELDS


def test_setup_empty_path(scripts):
    refused(scripts, {"jobs": {"test": job(setup="")}},
            "job test: setup: empty path")


def test_outside_a_git_repository_is_a_usage_error(repo, tmp_path):
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    result = repo.run("validate", cwd=outside,
                      env={"GIT_CEILING_DIRECTORIES": str(tmp_path)})
    assert result.returncode == 2
    assert result.stderr.startswith(
        "git-cicd: not inside a git repository: fatal:")


# ── The Manual workflow's form ──────────────────────────────────────────────

def test_shared_identical_inputs_validate(scripts):
    decl = {"choices": ["a", "b"], "default": "b", "description": "one"}
    scripts.config({"jobs": {
        "x": job(inputs={"mode": decl}),
        "y": job(inputs={"mode": dict(decl, description="another")}),
        "z": job(inputs={"note": {"default": ""}}),
        "w": job(inputs={"note": {}}),
    }})
    result = scripts.run("validate")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("a,b,what", [
    ({"choices": ["a", "b"]}, {"choices": ["a", "c"]}, "choices"),
    ({"choices": ["a", "b"]}, {}, "choices"),
    ({"default": "x"}, {"default": "y"}, "defaults"),
    ({"default": "x"}, {}, "defaults"),
    ({"choices": ["a", "b"], "default": "a"}, {"default": "b"},
     "choices and defaults"),
])
def test_shared_incompatible_inputs_are_refused(scripts, a, b, what):
    refused(scripts, {"jobs": {"first": job(inputs={"mode": a}),
                               "second": job(inputs={"mode": b})}},
            f"input mode is declared by jobs first and second with "
            f"different {what}",
            "give them the same choices and default, or rename one")


def test_incompatible_inputs_of_a_job_not_run_by_hand_validate(scripts):
    scripts.config({"jobs": {
        "first": job(inputs={"mode": {"default": "x"}}),
        "second": job(inputs={"mode": {"default": "y"}}, manual=False),
    }})
    assert scripts.run("validate").returncode == 0


@pytest.mark.parametrize("name", ["job"])
def test_form_field_names_are_reserved_on_manual_jobs(scripts, name):
    refused(scripts, {"jobs": {"t": job(inputs={name: {}})}},
            f"job t: input {name}: the name {name} is reserved for the "
            "Manual workflow's own field",
            '"manual": false')
    scripts.config({"jobs": {"t": job(inputs={name: {}}, manual=False)}})
    assert scripts.run("validate").returncode == 0


def test_form_limit(scripts):
    inputs = {f"in{i}": {} for i in range(24)}
    scripts.config({"jobs": {"a": job(inputs=dict(list(inputs.items())[:12])),
                             "b": job(inputs=dict(list(inputs.items())[12:]))}})
    assert scripts.run("validate").returncode == 0, "24 inputs fit"
    inputs["in24"] = {}
    refused(scripts, {"jobs": {"a": job(inputs=inputs)}},
            "the Manual workflow's form would have 26 fields (job and 25 "
            "distinct input names)",
            "at most 25 inputs", "at most 24 distinct input names",
            "use fewer distinct input names, or set \"manual\": false")
    scripts.config({"jobs": {"a": job(inputs=inputs, manual=False)}})
    assert scripts.run("validate").returncode == 0


@pytest.mark.parametrize("decl,what", [
    ({"description": "say ${{ github.token }}"}, "description"),
    ({"default": "${{ secrets.X }}"}, "default"),
    ({"choices": ["a", "b${{ x }}"]}, "choice"),
])
def test_expressions_are_refused_in_manual_jobs_form_values(scripts, decl,
                                                            what):
    refused(scripts, {"jobs": {"t": job(inputs={"x": decl})}},
            f"job t: input x: the {what} contains ${{{{, which GitHub would "
            "evaluate in the Manual workflow's form",
            '"manual": false')
    scripts.config({"jobs": {"t": job(inputs={"x": decl}, manual=False)}})
    assert scripts.run("validate").returncode == 0


# ── secrets ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", git_cicd.DECLARABLE_SECRETS)
def test_each_documented_secret_accepted(scripts, name):
    scripts.config({"jobs": {"t": job(secrets=[name])}})
    config = git_cicd.load_config(str(scripts.path))
    assert config["jobs"]["t"]["secrets"] == [name]


def test_secrets_default_empty(scripts):
    scripts.config({"jobs": {"t": job()}})
    config = git_cicd.load_config(str(scripts.path))
    assert config["jobs"]["t"]["secrets"] == []


def test_unknown_secret_refused(scripts):
    refused(scripts, {"jobs": {"t": job(secrets=["NPM_TOKEN"])}},
            "job t: unknown secret 'NPM_TOKEN' in secrets (allowed: "
            "CICD_WRITE_TOKEN, CICD_READ_TOKEN, VENDOR_PAT)")


@pytest.mark.parametrize("value", ["CICD_READ_TOKEN", {"a": 1}, None,
                                   ["CICD_READ_TOKEN", 3]])
def test_malformed_secrets_refused(scripts, value):
    refused(scripts, {"jobs": {"t": job(secrets=value)}},
            "job t: secrets must be an array of secret names "
            "(CICD_WRITE_TOKEN, CICD_READ_TOKEN, VENDOR_PAT)")


def test_duplicate_secret_refused(scripts):
    refused(scripts, {"jobs": {"t": job(
        secrets=["CICD_READ_TOKEN", "CICD_READ_TOKEN"])}},
        "job t: secret CICD_READ_TOKEN listed more than once in secrets")


def test_expressions_are_refused_in_a_manual_jobs_name(scripts):
    refused(scripts, {"jobs": {"t": job(name="Run ${{ github.token }}")}},
            "job t: the name contains ${{, which GitHub would evaluate in "
            "the Manual workflow's job dropdown", '"manual": false')
    scripts.config({"jobs": {"t": job(name="Run ${{ x }}", manual=False)}})
    assert scripts.run("validate").returncode == 0


# ── repository ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["git-cicd", "a.b_c-9", "X"])
def test_repository_names_are_accepted(scripts, value):
    scripts.config({"jobs": {"t": job()}, "repository": value})
    assert scripts.run("validate").returncode == 0
    config = git_cicd.load_config(str(scripts.path))
    assert config["repository"] == value


def test_repository_defaults_to_none(scripts):
    scripts.config({"jobs": {"t": job()}})
    assert git_cicd.load_config(str(scripts.path))["repository"] is None


@pytest.mark.parametrize("value", ["", "owner/name", "a b", "${{ x }}", ".",
                                   "..", 7, None, ["x"], "ü"])
def test_repository_must_be_a_name(scripts, value):
    refused(scripts, {"jobs": {"t": job()}, "repository": value},
            "config: repository must be the repository's name")


# ── manual_role ─────────────────────────────────────────────────────────────

def test_manual_role_defaults_to_admin(scripts):
    scripts.config({"jobs": {"t": job()}})
    assert git_cicd.load_config(str(scripts.path))["manual_role"] == "admin"


@pytest.mark.parametrize("value", ["admin", "write"])
def test_manual_roles_are_accepted(scripts, value):
    scripts.config({"jobs": {"t": job()}, "manual_role": value})
    assert scripts.run("validate").returncode == 0
    assert git_cicd.load_config(str(scripts.path))["manual_role"] == value


@pytest.mark.parametrize("value", ["read", "Admin", "", "maintain", None, 1,
                                   ["admin"], True])
def test_manual_role_must_be_admin_or_write(scripts, value):
    refused(scripts, {"jobs": {"t": job()}, "manual_role": value},
            "config: manual_role must be one of write, admin")
