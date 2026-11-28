#!/bin/bash
# ci/update-vendored.sh - the step of git-cicd's own `update-vendored` job:
# install or update the vendored tools and open the install pull requests,
# like-for-like with install-vendored.yml.
#
# Only CI runs this script (the Monday schedule, or a manual run); a session
# never runs it or .vendored/install itself. The vendor, version and private
# flag are the job's declared inputs (defaults all, latest, false). GH_TOKEN
# is VENDOR_PAT when it is set, else GITHUB_TOKEN.
set -euo pipefail

export GH_TOKEN="${VENDOR_PAT:-${GITHUB_TOKEN:-}}"
ARGS=("${CICD_INPUT_VENDOR:-all}" --version "${CICD_INPUT_VERSION:-latest}"
      --pr --deps=install)
if [ "${CICD_INPUT_PRIVATE:-false}" = "true" ]; then
    ARGS+=(--private)
fi
exec python3 .vendored/install "${ARGS[@]}"
