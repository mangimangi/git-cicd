#!/bin/bash
# ci/setup.sh - setup for git-cicd's own `test` job.
#
# Reads the Python floor from requires-python in pyproject.toml, uses that
# Python if present (python3.X, the runner tool cache) or installs it with uv
# (itself installed into a small venv when missing), and installs the test-only dependencies into a
# virtualenv the test step finds on disk. No Python version is written in the
# workflow or the config: this script is the only place that decides it.
#
# It also installs bats-core (the shell tests under tests/bats/) into the
# cache when `bats` is not on PATH: the pinned release's npm tarball (bats-core
# publishes itself to npm as `bats`), checked against its sha256. Setup may
# download; the tests themselves use no network.
set -euo pipefail

FLOOR="$(sed -n 's/^requires-python *= *">= *\([0-9][0-9.]*\)".*/\1/p' pyproject.toml | head -n1)"
if [ -z "$FLOOR" ]; then
    echo "ci/setup.sh: cannot read requires-python (\">=X.Y\") from pyproject.toml" >&2
    exit 1
fi
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/git-cicd"
VENV="$CACHE/venv-$FLOOR"
TOOLS="$CACHE/tools"   # holds uv when it has to be installed
BATS_VERSION=1.11.1
BATS_SHA256=1d8a88fc70bc5a518c7cf17e5201b80b24e9475be95abe6508b3197a64b73365
BATS_DIR="$CACHE/bats"  # ci/test.sh runs $BATS_DIR/bin/bats when bats is not on PATH

find_floor() {
    local candidate
    for candidate in "python$FLOOR" /opt/hostedtoolcache/Python/"$FLOOR".*/x64/bin/python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done
    local uv
    uv="$(command -v uv 2>/dev/null || true)"
    if [ -z "$uv" ] && python3 -m venv "$TOOLS" >&2 \
            && "$TOOLS/bin/python" -m pip install --quiet uv >&2; then
        uv="$TOOLS/bin/uv"
    fi
    if [ -n "$uv" ]; then
        "$uv" python install "$FLOOR" >&2 && "$uv" python find "$FLOOR" && return 0
    fi
    return 1
}

if PYTHON="$(find_floor)"; then
    echo "ci/setup.sh: using Python $FLOOR at $PYTHON"
elif [ -z "${CI:-}" ] && python3 -c "import sys; sys.exit(sys.version_info < tuple(map(int, '$FLOOR'.split('.'))))"; then
    PYTHON="$(command -v python3)"
    echo "ci/setup.sh: Python $FLOOR not found; using $("$PYTHON" --version) locally (CI runs the floor)"
else
    echo "ci/setup.sh: Python $FLOOR not found (looked for python$FLOOR and the runner tool cache; uv could not install it)" >&2
    exit 1
fi

"$PYTHON" -m venv --clear "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
# coverage >= 7.10 measures subprocesses (pyproject.toml patch = ["subprocess"]).
"$VENV/bin/python" -m pip install --quiet pytest pytest-cov "coverage>=7.10"
"$VENV/bin/python" --version

install_bats() {
    if command -v bats >/dev/null 2>&1; then
        echo "ci/setup.sh: using $(bats --version) at $(command -v bats)"
        return 0
    fi
    if [ "$(cat "$BATS_DIR/VERSION" 2>/dev/null)" = "$BATS_VERSION" ] \
            && [ -x "$BATS_DIR/bin/bats" ]; then
        echo "ci/setup.sh: using bats $BATS_VERSION at $BATS_DIR/bin/bats"
        return 0
    fi
    local tmp
    tmp="$(mktemp -d)"
    if ! curl -fsSL -o "$tmp/bats.tgz" \
            "https://registry.npmjs.org/bats/-/bats-$BATS_VERSION.tgz"; then
        echo "ci/setup.sh: cannot download bats $BATS_VERSION" >&2
        rm -rf "$tmp"
        return 1
    fi
    if ! echo "$BATS_SHA256  $tmp/bats.tgz" | sha256sum -c --quiet - >/dev/null 2>&1; then
        echo "ci/setup.sh: bats $BATS_VERSION does not match its pinned sha256" >&2
        rm -rf "$tmp"
        return 1
    fi
    tar -xzf "$tmp/bats.tgz" -C "$tmp"
    rm -rf "$BATS_DIR"
    mkdir -p "$(dirname "$BATS_DIR")"
    mv "$tmp/package" "$BATS_DIR"
    echo "$BATS_VERSION" > "$BATS_DIR/VERSION"
    rm -rf "$tmp"
    echo "ci/setup.sh: installed bats $BATS_VERSION at $BATS_DIR/bin/bats"
}

install_bats
