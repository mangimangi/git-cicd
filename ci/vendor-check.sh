#!/bin/bash
# ci/vendor-check.sh - the step of git-cicd's own `vendor-check` job: the
# vendor file protection check (.vendored/check) against the change's base.
#
# .vendored/check lets a vendor's install branch (chore/install-<vendor>)
# through by its name, read from GITHUB_HEAD_REF in a pull request. When that
# is unset (a local `git-cicd check`), it is the change's source branch, so a
# local run and Actions decide the same way.
set -euo pipefail

if [ -z "${GITHUB_HEAD_REF:-}" ]; then
    export GITHUB_HEAD_REF="${CICD_SOURCE_BRANCH:-}"
fi
exec python3 .vendored/check --base "$CICD_BASE"
