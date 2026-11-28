#!/bin/bash
# ci/release.sh - the step of git-cicd's own `release` job: bump or publish
# with git-semver's release, the way version-bump.yml decided it.
#
#   manual run                       -> release bump (workflow_dispatch)
#   merge, head `chore: bump version` -> release publish
#   merge, head `chore: install`      -> nothing to release
#   merge, anything else              -> release bump (push)
#
# git-semver's release reads GITHUB_EVENT_NAME, GITHUB_EVENT_BEFORE,
# INPUT_BUMP_TYPE, INPUT_SUBDIRECTORY, INPUT_CHANGELOG_DESCRIPTION and
# GH_TOKEN (GITHUB_SHA, GITHUB_REF and GITHUB_REPOSITORY come from Actions);
# this script gives it them from the CICD_ variables and the job's declared
# inputs. The release is called through an argv, never an eval.
set -euo pipefail

RELEASE=(python3 .vendored/pkg/git-semver/release)

export GITHUB_EVENT_BEFORE="${CICD_BASE:-}"
export INPUT_BUMP_TYPE="${CICD_INPUT_BUMP_TYPE:-}"
export INPUT_SUBDIRECTORY="${CICD_INPUT_SUBDIRECTORY:-}"
export INPUT_CHANGELOG_DESCRIPTION="${CICD_INPUT_CHANGELOG_DESCRIPTION:-}"
export GH_TOKEN="${GITHUB_TOKEN:-}"

case "${CICD_TRIGGER:-}" in
    manual)
        export GITHUB_EVENT_NAME=workflow_dispatch
        exec "${RELEASE[@]}" bump
        ;;
    merge)
        SUBJECT="$(git log -1 --format=%s "$CICD_HEAD")"
        export GITHUB_EVENT_NAME=push
        case "$SUBJECT" in
            "chore: bump version"*)
                exec "${RELEASE[@]}" publish
                ;;
            "chore: install"*)
                echo "ci/release.sh: $CICD_HEAD is an install commit; nothing to release"
                exit 0
                ;;
            *)
                exec "${RELEASE[@]}" bump
                ;;
        esac
        ;;
    *)
        echo "ci/release.sh: the release runs on merge or by hand, not on ${CICD_TRIGGER:-no trigger}" >&2
        exit 1
        ;;
esac
