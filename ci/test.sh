#!/bin/bash
# ci/test.sh - the step of git-cicd's own `test` job: run pytest with coverage.
#
# Uses the virtualenv ci/setup.sh creates for the Python floor. When setup was
# skipped (a local `git-cicd check` without --setup), falls back to a python3
# that already has pytest.
set -euo pipefail

FLOOR="$(sed -n 's/^requires-python *= *">= *\([0-9][0-9.]*\)".*/\1/p' pyproject.toml | head -n1)"
VENV="${XDG_CACHE_HOME:-$HOME/.cache}/git-cicd/venv-$FLOOR"

if [ -x "$VENV/bin/python" ]; then
    PYTHON="$VENV/bin/python"
elif python3 -c "import pytest" 2>/dev/null; then
    PYTHON=python3
else
    echo "ci/test.sh: pytest is not installed; run: ./git-cicd check --setup" >&2
    exit 1
fi

"$PYTHON" --version
COV=()
if "$PYTHON" -c "import pytest_cov" 2>/dev/null; then
    COV=(--cov --cov-report=term-missing --cov-config=pyproject.toml)
fi
exec "$PYTHON" -m pytest tests/ -v "${COV[@]}"
