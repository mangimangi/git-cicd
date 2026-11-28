#!/bin/bash
# ci/test.sh - the step of git-cicd's own `test` job: run pytest with
# coverage, then the bats tests of install.sh and the ci/ scripts
# (tests/bats/). Both run; either failing fails the step.
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
# The step fails below 99% (pyproject.toml fail_under), after the report.
# In CI (CI set) a missing pytest-cov fails the step, so the gate is never
# skipped; locally the suite still runs and says coverage was not checked.
#
# The suite never reads a real token: tests/conftest.py (an autouse fixture)
# and tests/bats/helper.bash remove CICD_WRITE_TOKEN, CICD_READ_TOKEN,
# VENDOR_PAT, GH_TOKEN and GITHUB_TOKEN before every test. This script sets
# each of them to a sentinel value first, and a test in each suite fails
# while one is set, so removing the guard fails the step.
set -euo pipefail

for TOKEN in CICD_WRITE_TOKEN CICD_READ_TOKEN VENDOR_PAT GH_TOKEN GITHUB_TOKEN; do
    export "$TOKEN=git-cicd-test-sentinel"
done

FLOOR="$(sed -n 's/^requires-python *= *">= *\([0-9][0-9.]*\)".*/\1/p' pyproject.toml | head -n1)"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/git-cicd"
VENV="$CACHE/venv-$FLOOR"

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
elif [ -n "${CI:-}" ]; then
    echo "ci/test.sh: pytest-cov is not installed, so the 99% coverage gate cannot run; run: ./git-cicd check --setup" >&2
    exit 1
else
    echo "ci/test.sh: pytest-cov is not installed; coverage was not measured or checked (run: ./git-cicd check --setup)"
fi
STATUS=0
"$PYTHON" -m pytest tests/ -v "${COV[@]}" || STATUS=$?

# bats: on PATH, else the copy ci/setup.sh installs into the cache.
BATS="$(command -v bats 2>/dev/null || true)"
if [ -z "$BATS" ] && [ -x "$CACHE/bats/bin/bats" ]; then
    BATS="$CACHE/bats/bin/bats"
fi
if [ -n "$BATS" ]; then
    "$BATS" tests/bats/ || STATUS=$?
elif [ -n "${CI:-}" ]; then
    echo "ci/test.sh: bats is not installed, so the shell tests cannot run; run: ./git-cicd check --setup" >&2
    STATUS=1
else
    echo "ci/test.sh: bats is not installed; the shell tests (tests/bats/) did not run (install it with: ./git-cicd check --setup)"
fi
exit "$STATUS"
