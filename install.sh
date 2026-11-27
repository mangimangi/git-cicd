#!/bin/bash
# git-cicd/install.sh - Install or update git-cicd in a project
#
# Usage:
#   install.sh <version>
#
# Run by git-vendored: python3 .vendored/install mangimangi/git-cicd
#
# Environment:
#   VENDOR_REF         - Version to install (falls back to positional $1)
#   VENDOR_REPO        - Source repo (falls back to mangimangi/git-cicd)
#   VENDOR_INSTALL_DIR - Where to install code files (required;
#                        .vendored/pkg/git-cicd under git-vendored)
#   VENDOR_MANIFEST    - Path to write installed file manifest (optional)
#   GH_TOKEN           - Used for gh api downloads (required for private repos).
#                        Falls back to curl for public repos when not set.
#
# Behavior:
#   - Always updates: git-cicd (the tool) and templates/workflow.yml under
#     VENDOR_INSTALL_DIR, and the config schema
#   - Preserves .vendored/configs/git-cicd.json (only creates if missing)
#   - Always (re)generates .github/workflows/git-cicd.yml from the config, so
#     an upgrade reaches the workflow in the install pull request
#
set -euo pipefail

VERSION="${VENDOR_REF:-${1:?Usage: install.sh <version>}}"
VERSION="${VERSION#v}"  # strip v prefix if present (VENDOR_REF includes it)
REPO="${VENDOR_REPO:-mangimangi/git-cicd}"
INSTALL_DIR="${VENDOR_INSTALL_DIR:?VENDOR_INSTALL_DIR is required}"

CONFIG=".vendored/configs/git-cicd.json"
WORKFLOW=".github/workflows/git-cicd.yml"

# File download helper - uses gh api when GH_TOKEN is set, curl otherwise
fetch_file() {
    local repo_path="$1"
    local dest="$2"
    local ref="${3:-v$VERSION}"

    if [ -n "${GH_TOKEN:-}" ] && command -v gh &>/dev/null; then
        gh api "repos/$REPO/contents/$repo_path?ref=$ref" --jq '.content' | base64 -d > "$dest"
    else
        local base="https://raw.githubusercontent.com/$REPO"
        curl -fsSL "$base/$ref/$repo_path" -o "$dest"
    fi
}

echo "Installing git-cicd v$VERSION from $REPO"

INSTALLED_FILES=()

mkdir -p "$INSTALL_DIR/templates" .vendored/configs .vendored/manifests .github/workflows

# Code - always updated
echo "Downloading git-cicd..."
fetch_file "git-cicd" "$INSTALL_DIR/git-cicd"
chmod +x "$INSTALL_DIR/git-cicd"
INSTALLED_FILES+=("$INSTALL_DIR/git-cicd")

fetch_file "templates/workflow.yml" "$INSTALL_DIR/templates/workflow.yml"
INSTALLED_FILES+=("$INSTALL_DIR/templates/workflow.yml")

# Config - only created if missing (user-owned; not listed in the manifest)
if [ ! -f "$CONFIG" ]; then
    fetch_file "templates/config.json" "$CONFIG"
    echo "Created $CONFIG (declare your jobs, then run $INSTALL_DIR/git-cicd generate)"
fi

# Config schema for vendor audit validation
fetch_file "templates/config.schema" ".vendored/manifests/git-cicd.schema"
INSTALLED_FILES+=(".vendored/manifests/git-cicd.schema")

# Workflow - regenerated on every install from the config
python3 "$INSTALL_DIR/git-cicd" generate
INSTALLED_FILES+=("$WORKFLOW")

# Write manifest when requested by the framework
if [ -n "${VENDOR_MANIFEST:-}" ]; then
    printf '%s\n' "${INSTALLED_FILES[@]}" > "$VENDOR_MANIFEST"
fi

echo ""
echo "Done! git-cicd v$VERSION installed."
