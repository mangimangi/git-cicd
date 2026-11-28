#!/usr/bin/env bats
# ci/test.sh: pytest (with coverage) and the bats tests, either failing fails.

load helper

setup() {
    common_setup
    VENV="$XDG_CACHE_HOME/git-cicd/venv-3.11"
    stub bats
}

pytest_call() {
    grep "^call python -m pytest" "$LOG"
}

@test "the setup virtualenv's python runs pytest with coverage, then bats" {
    fake_python "$VENV/bin/python"
    run bash ci/test.sh
    [ "$status" -eq 0 ]
    [ "$(pytest_call)" = "call python -m pytest tests/ -v --cov --cov-report=term-missing --cov-config=pyproject.toml" ]
    grep -qx "call bats" "$LOG"
    grep -qx "arg tests/bats/" "$LOG"
}

@test "coverage data goes to a fresh directory that is removed afterwards" {
    fake_python "$VENV/bin/python"
    run bash ci/test.sh
    [ "$status" -eq 0 ]
    data="$(sed -n 's/^coverage-file //p' "$LOG")"
    [ -n "$data" ]
    [ "$(basename "$data")" = ".coverage" ]
    [ ! -e "$(dirname "$data")" ]
    [ -z "$(ls -A | grep '^\.coverage')" ]
}

@test "without the virtualenv, a python3 with pytest runs the suite" {
    fake_python "$STUBS/python3"
    run bash ci/test.sh
    [ "$status" -eq 0 ]
    [ -n "$(pytest_call)" ]
}

@test "without pytest, the step fails and names setup" {
    export FAKE_MISSING="pytest pytest_cov"
    fake_python "$STUBS/python3"
    run bash ci/test.sh
    [ "$status" -eq 1 ]
    [ "$output" = "ci/test.sh: pytest is not installed; run: ./git-cicd check --setup" ]
}

@test "locally without pytest-cov, the suite runs and says coverage was not checked" {
    export FAKE_MISSING=pytest_cov
    fake_python "$STUBS/python3"
    run bash ci/test.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"ci/test.sh: pytest-cov is not installed; coverage was not measured or checked (run: ./git-cicd check --setup)"* ]]
    [ "$(pytest_call)" = "call python -m pytest tests/ -v" ]
}

@test "in CI without pytest-cov, the step fails before the suite" {
    export FAKE_MISSING=pytest_cov CI=true
    fake_python "$STUBS/python3"
    run bash ci/test.sh
    [ "$status" -eq 1 ]
    [[ "$output" == *"the 99% coverage gate cannot run; run: ./git-cicd check --setup"* ]]
    [ -z "$(pytest_call)" ]
}

@test "a failing pytest fails the step, and bats still runs" {
    export FAKE_PYTEST_EXIT=1
    fake_python "$VENV/bin/python"
    run bash ci/test.sh
    [ "$status" -eq 1 ]
    grep -qx "call bats" "$LOG"
}

@test "a failing bats test fails the step" {
    stub bats 1
    fake_python "$VENV/bin/python"
    run bash ci/test.sh
    [ "$status" -eq 1 ]
    [ -n "$(pytest_call)" ]
}

@test "bats from the setup cache is used when not on PATH" {
    fake_python "$VENV/bin/python"
    rm "$STUBS/bats"
    mkdir -p "$XDG_CACHE_HOME/git-cicd/bats/bin"
    cat > "$XDG_CACHE_HOME/git-cicd/bats/bin/bats" <<'SH'
#!/bin/bash
echo "call cached-bats $*" >> "$LOG"
SH
    chmod +x "$XDG_CACHE_HOME/git-cicd/bats/bin/bats"
    only_tools bash sed head mktemp rm mkdir cp dirname
    PATH="$ONLY_PATH" run bash ci/test.sh
    [ "$status" -eq 0 ]
    grep -qx "call cached-bats tests/bats/" "$LOG"
}

@test "locally without bats, the step says how to install it" {
    fake_python "$VENV/bin/python"
    rm "$STUBS/bats"
    only_tools bash sed head mktemp rm mkdir cp dirname
    PATH="$ONLY_PATH" run bash ci/test.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"ci/test.sh: bats is not installed; the shell tests (tests/bats/) did not run (install it with: ./git-cicd check --setup)"* ]]
}

@test "in CI without bats, the step fails" {
    export CI=true
    fake_python "$VENV/bin/python"
    rm "$STUBS/bats"
    only_tools bash sed head mktemp rm mkdir cp dirname
    PATH="$ONLY_PATH" run bash ci/test.sh
    [ "$status" -eq 1 ]
    [[ "$output" == *"ci/test.sh: bats is not installed, so the shell tests cannot run; run: ./git-cicd check --setup"* ]]
    [ -n "$(pytest_call)" ]
}

@test "pytest and bats run with a sentinel for every token name" {
    fake_python "$VENV/bin/python"
    cat > "$STUBS/bats" <<'SH'
#!/bin/bash
for name in CICD_WRITE_TOKEN CICD_READ_TOKEN VENDOR_PAT GH_TOKEN GITHUB_TOKEN; do
    echo "token $name=${!name-unset}" >> "$LOG"
done
SH
    chmod +x "$STUBS/bats"
    run bash ci/test.sh
    [ "$status" -eq 0 ]
    for name in CICD_WRITE_TOKEN CICD_READ_TOKEN VENDOR_PAT GH_TOKEN GITHUB_TOKEN; do
        grep -qx "token $name=git-cicd-test-sentinel" "$LOG"
    done
}
