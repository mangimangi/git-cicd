# tests/bats/helper.bash - shared setup for the bats tests of install.sh and
# the ci/ scripts.
#
# Each test gets a temporary git repository ($REPO, the working directory)
# holding copies of this repository's ci/ scripts and pyproject.toml, an
# empty cache (XDG_CACHE_HOME) and a stub directory ($STUBS) first on PATH.
# Fake tools log their argv (one `arg` line per element) and the environment
# they were given (`env` lines) to $LOG. Nothing touches the network.

ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

common_setup() {
    # Nothing from the caller's environment decides a test.
    local var
    for var in $(compgen -e); do
        case "$var" in
            GITHUB_*|CICD_*|INPUT_*|VENDOR_*) unset "$var" ;;
        esac
    done
    unset GH_TOKEN CI

    REPO="$BATS_TEST_TMPDIR/repo"
    STUBS="$BATS_TEST_TMPDIR/stubs"
    LOG="$BATS_TEST_TMPDIR/calls.log"
    export LOG
    export XDG_CACHE_HOME="$BATS_TEST_TMPDIR/cache"
    mkdir -p "$REPO" "$STUBS" "$XDG_CACHE_HOME"
    PATH="$STUBS:$PATH"

    git init -q -b main "$REPO"
    git -C "$REPO" config user.email test@example.com
    git -C "$REPO" config user.name Test
    git -C "$REPO" config commit.gpgsign false
    mkdir -p "$REPO/ci"
    cp "$ROOT"/ci/*.sh "$REPO/ci/"
    cp "$ROOT/pyproject.toml" "$REPO/"
    cd "$REPO"
}

# commit <subject>: an empty commit; prints its sha.
commit() {
    git commit -q --allow-empty -m "$1"
    git rev-parse HEAD
}

# fake_python_tool <path>: a Python script under the repository that logs its
# argv and the GITHUB_/INPUT_/GH_ environment to $LOG (run as python3 <path>).
fake_python_tool() {
    mkdir -p "$(dirname "$1")"
    cat > "$1" <<'PY'
#!/usr/bin/env python3
import os, sys
with open(os.environ["LOG"], "a") as f:
    f.write("call %s\n" % sys.argv[0])
    for arg in sys.argv[1:]:
        f.write("arg %s\n" % arg)
    for key in sorted(os.environ):
        if key.startswith(("GITHUB_", "INPUT_", "GH_")):
            f.write("env %s=%s\n" % (key, os.environ[key]))
PY
    chmod +x "$1"
}

# stub <name> [exit code]: a command on PATH that logs its argv to $LOG.
stub() {
    cat > "$STUBS/$1" <<SH
#!/bin/bash
echo "call $1" >> "\$LOG"
for arg in "\$@"; do echo "arg \$arg" >> "\$LOG"; done
exit ${2:-0}
SH
    chmod +x "$STUBS/$1"
}

# logged: the log (empty when nothing ran).
logged() {
    cat "$LOG" 2>/dev/null || true
}

# args: the argv lines of the log, without the prefix.
args() {
    sed -n 's/^arg //p' "$LOG" 2>/dev/null || true
}

# env_of <NAME>: the value a fake tool was given (empty line when unset).
env_of() {
    sed -n "s/^env $1=//p" "$LOG"
}

# has_env <NAME>: the fake tool was given NAME.
has_env() {
    grep -q "^env $1=" "$LOG"
}

# only_tools <name>...: sets ONLY_PATH to $STUBS plus a directory holding just
# the named system tools, so a command the host happens to have (bats, uv,
# python3.X) is not found. Use it for the script only:
# PATH="$ONLY_PATH" run bash ci/<script>.
only_tools() {
    local bin="$BATS_TEST_TMPDIR/bin" tool
    mkdir -p "$bin"
    for tool in "$@"; do
        # the system binary, not a wrapper an environment puts on PATH
        if [ -x "/usr/bin/$tool" ]; then
            ln -sf "/usr/bin/$tool" "$bin/$tool"
        elif [ -x "/bin/$tool" ]; then
            ln -sf "/bin/$tool" "$bin/$tool"
        else
            ln -sf "$(command -v "$tool")" "$bin/$tool"
        fi
    done
    ONLY_PATH="$STUBS:$bin"
}

# fake_python <path>: a python3 stand-in that logs `call python <args>` and
# acts out what the ci/ scripts ask of it: `-m venv DIR` creates DIR/bin/python
# (a copy of itself), `-m pip install` succeeds unless it installs uv,
# `--version` prints Python 3.99.9, `-m pytest` exits $FAKE_PYTEST_EXIT (0)
# and `-c "import M"` fails for each module in $FAKE_MISSING.
fake_python() {
    mkdir -p "$(dirname "$1")"
    cat > "$1" <<'SH'
#!/bin/bash
echo "call python $*" >> "$LOG"
case "$1" in
    --version) echo "Python 3.99.9"; exit 0 ;;
    -c)
        for module in ${FAKE_MISSING:-}; do
            [ "$2" = "import $module" ] && exit 1
        done
        exit 0 ;;
    -m)
        case "$2" in
            venv)
                dir="${!#}"; mkdir -p "$dir/bin"; cp "$0" "$dir/bin/python"
                exit 0 ;;
            pip)
                for arg in "$@"; do [ "$arg" = uv ] && exit 1; done
                exit 0 ;;
            pytest)
                [ -n "${COVERAGE_FILE:-}" ] && echo "coverage-file $COVERAGE_FILE" >> "$LOG"
                exit "${FAKE_PYTEST_EXIT:-0}" ;;
        esac ;;
esac
exit 0
SH
    chmod +x "$1"
}
