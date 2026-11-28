#!/usr/bin/env bats
# ci/setup.sh: the Python floor, the test virtualenv and bats.

load helper

setup() {
    common_setup
    # A floor no host has, so the runner's tool cache never answers.
    sed -i 's/^requires-python = .*/requires-python = ">=3.99"/' pyproject.toml
    fake_python "$STUBS/python3"
    stub uv 1         # uv cannot install the floor
    stub curl 1       # no network
    cat > "$STUBS/bats" <<'SH'
#!/bin/bash
echo "Bats 9.9.9"
SH
    chmod +x "$STUBS/bats"
    VENV="$XDG_CACHE_HOME/git-cicd/venv-3.99"
}

@test "the floor comes from requires-python and is used when present" {
    fake_python "$STUBS/python3.99"
    run bash ci/setup.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"ci/setup.sh: using Python 3.99 at $STUBS/python3.99"* ]]
    [ -x "$VENV/bin/python" ]
    grep -qx "call python -m venv --clear $VENV" "$LOG"
    grep -qx "call python -m pip install --quiet pytest pytest-cov coverage>=7.10" "$LOG"
}

@test "an unreadable requires-python is an error" {
    sed -i '/^requires-python/d' pyproject.toml
    run bash ci/setup.sh
    [ "$status" -eq 1 ]
    [ "$output" = 'ci/setup.sh: cannot read requires-python (">=X.Y") from pyproject.toml' ]
    [ -z "$(logged)" ]
}

@test "locally, a missing floor falls back to python3" {
    run bash ci/setup.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"ci/setup.sh: Python 3.99 not found; using Python 3.99.9 locally (CI runs the floor)"* ]]
    [ -x "$VENV/bin/python" ]
    grep -qx "call python -m pip install --quiet pytest pytest-cov coverage>=7.10" "$LOG"
}

@test "in CI, a missing floor fails and installs nothing" {
    export CI=true
    run bash ci/setup.sh
    [ "$status" -eq 1 ]
    [[ "$output" == *"ci/setup.sh: Python 3.99 not found (looked for python3.99 and the runner tool cache; uv could not install it)"* ]]
    [ ! -e "$VENV" ]
    [ -z "$(grep -- "pytest" "$LOG")" ]
}

@test "bats on PATH is used, not downloaded" {
    run bash ci/setup.sh
    [ "$status" -eq 0 ]
    [[ "$output" == *"ci/setup.sh: using Bats 9.9.9 at $STUBS/bats"* ]]
    [ -z "$(grep -x "call curl" "$LOG")" ]
}

@test "without bats, a failed download fails setup" {
    rm "$STUBS/bats"
    only_tools bash sed head mkdir mktemp rm cat dirname sha256sum tar mv cp
    PATH="$ONLY_PATH" run bash ci/setup.sh
    [ "$status" -eq 1 ]
    [[ "$output" == *"ci/setup.sh: cannot download bats 1.11.1"* ]]
    grep -qx "arg https://registry.npmjs.org/bats/-/bats-1.11.1.tgz" "$LOG"
    [ ! -e "$XDG_CACHE_HOME/git-cicd/bats" ]
}

@test "without bats, a download that does not match the pin is refused" {
    rm "$STUBS/bats"
    mkdir -p "$BATS_TEST_TMPDIR/pkg/package/bin"
    echo fake > "$BATS_TEST_TMPDIR/pkg/package/bin/bats"
    tar -czf "$BATS_TEST_TMPDIR/bats.tgz" -C "$BATS_TEST_TMPDIR/pkg" package
    cat > "$STUBS/curl" <<SH
#!/bin/bash
while [ "\$1" != "-o" ]; do shift; done
cp "$BATS_TEST_TMPDIR/bats.tgz" "\$2"
SH
    chmod +x "$STUBS/curl"
    only_tools bash sed head mkdir mktemp rm cat dirname sha256sum tar mv cp
    PATH="$ONLY_PATH" run bash ci/setup.sh
    [ "$status" -eq 1 ]
    [[ "$output" == *"ci/setup.sh: bats 1.11.1 does not match its pinned sha256"* ]]
    [ ! -e "$XDG_CACHE_HOME/git-cicd/bats" ]
}
