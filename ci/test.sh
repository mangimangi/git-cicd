#!/bin/bash
# ci/test.sh - the step of git-cicd's own `test` job: run pytest with coverage.
#
# Uses the virtualenv ci/setup.sh creates for the Python floor. When setup was
# skipped (a local `git-cicd check` without --setup), falls back to a python3
# that already has pytest.
#
# Coverage measures git-cicd's lines in the pytest process and in every
# `python3 git-cicd ...` a test starts (pyproject.toml [tool.coverage]): each
# process writes its own data file into a fresh temporary directory, pytest-cov
# combines them (mapping installed copies onto the root git-cicd) and prints
# one row with the missing lines. The directory is removed afterwards, so no
# data carries over from one run to the next and nothing lands in the checkout.
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
    DATA="$(mktemp -d)"
    trap 'rm -rf "$DATA"' EXIT
    export COVERAGE_FILE="$DATA/.coverage"
    COV=(--cov --cov-report=term-missing --cov-config=pyproject.toml)
else
    echo "ci/test.sh: pytest-cov is not installed; coverage was not measured (run: ./git-cicd check --setup)"
fi
"$PYTHON" -m pytest tests/ -v "${COV[@]}"
