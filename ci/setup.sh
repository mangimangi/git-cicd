#!/bin/bash
# ci/setup.sh - setup for git-cicd's own `test` job.
#
# Reads the Python floor from requires-python in pyproject.toml, uses (or
# installs) that Python, and installs the test-only dependencies into a
# virtualenv the test step finds on disk. No Python version is written in the
# workflow or the config: this script is the only place that decides it.
set -euo pipefail

FLOOR="$(sed -n 's/^requires-python *= *">= *\([0-9][0-9.]*\)".*/\1/p' pyproject.toml | head -n1)"
if [ -z "$FLOOR" ]; then
    echo "ci/setup.sh: cannot read requires-python (\">=X.Y\") from pyproject.toml" >&2
    exit 1
fi
VENV="${XDG_CACHE_HOME:-$HOME/.cache}/git-cicd/venv-$FLOOR"

find_floor() {
    local candidate
    for candidate in "python$FLOOR" /opt/hostedtoolcache/Python/"$FLOOR".*/x64/bin/python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done
    if command -v uv >/dev/null 2>&1; then
        uv python install "$FLOOR" >&2 && uv python find "$FLOOR" && return 0
    fi
    return 1
}

if PYTHON="$(find_floor)"; then
    echo "ci/setup.sh: using Python $FLOOR at $PYTHON"
elif [ -z "${CI:-}" ] && python3 -c "import sys; sys.exit(sys.version_info < tuple(map(int, '$FLOOR'.split('.'))))"; then
    PYTHON="$(command -v python3)"
    echo "ci/setup.sh: Python $FLOOR not found; using $("$PYTHON" --version) locally (CI runs the floor)"
else
    echo "ci/setup.sh: Python $FLOOR not found (looked for python$FLOOR, the runner tool cache and uv)" >&2
    exit 1
fi

"$PYTHON" -m venv --clear "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet pytest pytest-cov
"$VENV/bin/python" --version
