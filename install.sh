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
#   - Always updates: git-cicd (the tool) and the workflow templates
#     (templates/workflows/<trigger>.yml) under VENDOR_INSTALL_DIR, and the
#     config schema
#   - Preserves .vendored/configs/git-cicd.json (only creates if missing; a
#     new config lists .github/workflows/git-cicd-*.yml as allowed, so the
#     vendor check lets a pull request regenerate every per-trigger workflow,
#     the ones still to come included)
#   - Always (re)generates the per-trigger workflows
#     (.github/workflows/git-cicd-<trigger>.yml) from the config, so an upgrade
#     reaches them in the install pull request, and removes the single
#     .github/workflows/git-cicd.yml of earlier versions
#
set -euo pipefail

VERSION="${VENDOR_REF:-${1:?Usage: install.sh <version>}}"
VERSION="${VERSION#v}"  # strip v prefix if present (VENDOR_REF includes it)
REPO="${VENDOR_REPO:-mangimangi/git-cicd}"
INSTALL_DIR="${VENDOR_INSTALL_DIR:?VENDOR_INSTALL_DIR is required}"

CONFIG=".vendored/configs/git-cicd.json"
# The triggers whose workflow git-cicd generates (see WORKFLOWS in git-cicd).
TRIGGERS=(open merge)

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

mkdir -p "$INSTALL_DIR/templates/workflows" .vendored/configs .vendored/manifests .github/workflows

# Code - always updated
echo "Downloading git-cicd..."
fetch_file "git-cicd" "$INSTALL_DIR/git-cicd"
chmod +x "$INSTALL_DIR/git-cicd"
INSTALLED_FILES+=("$INSTALL_DIR/git-cicd")

# Templates of earlier versions, replaced by templates/workflows/
rm -f "$INSTALL_DIR/templates/workflow.yml"
for trigger in "${TRIGGERS[@]}"; do
    fetch_file "templates/workflows/$trigger.yml" \
        "$INSTALL_DIR/templates/workflows/$trigger.yml"
    INSTALLED_FILES+=("$INSTALL_DIR/templates/workflows/$trigger.yml")
done

# Config - only created if missing (user-owned; not listed in the manifest)
if [ ! -f "$CONFIG" ]; then
    fetch_file "templates/config.json" "$CONFIG"
    echo "Created $CONFIG (declare your jobs, then run $INSTALL_DIR/git-cicd generate)"
fi

# Config schema for vendor audit validation
fetch_file "templates/config.schema" ".vendored/manifests/git-cicd.schema"
INSTALLED_FILES+=(".vendored/manifests/git-cicd.schema")

# Workflows - regenerated on every install from the config (generate also
# removes the single workflow file of earlier versions)
python3 "$INSTALL_DIR/git-cicd" generate
for trigger in "${TRIGGERS[@]}"; do
    INSTALLED_FILES+=(".github/workflows/git-cicd-$trigger.yml")
done

# Write manifest when requested by the framework
if [ -n "${VENDOR_MANIFEST:-}" ]; then
    printf '%s\n' "${INSTALLED_FILES[@]}" > "$VENDOR_MANIFEST"
fi

echo ""
echo "Done! git-cicd v$VERSION installed."
