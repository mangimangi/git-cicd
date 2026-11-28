#!/usr/bin/env bats
# ci/release.sh: bump or publish with git-semver's release.

load helper

setup() {
    common_setup
    fake_python_tool .vendored/pkg/git-semver/release
    BASE="$(commit "base")"
}

run_release() {
    run bash ci/release.sh
}

@test "a manual run bumps as workflow_dispatch" {
    export CICD_TRIGGER=manual
    run_release
    [ "$status" -eq 0 ]
    [ "$(args)" = "bump" ]
    [ "$(env_of GITHUB_EVENT_NAME)" = "workflow_dispatch" ]
}

@test "a merge of a version bump commit publishes" {
    export CICD_TRIGGER=merge CICD_HEAD="$(commit "chore: bump version to 1.2.3")"
    run_release
    [ "$status" -eq 0 ]
    [ "$(args)" = "publish" ]
    [ "$(env_of GITHUB_EVENT_NAME)" = "push" ]
}

@test "a merge of an install commit releases nothing" {
    export CICD_TRIGGER=merge CICD_HEAD="$(commit "chore: install git-semver v1.0.0")"
    run_release
    [ "$status" -eq 0 ]
    [ "$output" = "ci/release.sh: $CICD_HEAD is an install commit; nothing to release" ]
    [ -z "$(logged)" ]
}

@test "any other merge bumps as push" {
    export CICD_TRIGGER=merge CICD_HEAD="$(commit "feat: something")"
    run_release
    [ "$status" -eq 0 ]
    [ "$(args)" = "bump" ]
    [ "$(env_of GITHUB_EVENT_NAME)" = "push" ]
}

@test "another trigger fails with the message" {
    export CICD_TRIGGER=open
    run_release
    [ "$status" -eq 1 ]
    [ "$output" = "ci/release.sh: the release runs on merge or by hand, not on open" ]
    [ -z "$(logged)" ]
}

@test "no trigger fails with the message" {
    run_release
    [ "$status" -eq 1 ]
    [ "$output" = "ci/release.sh: the release runs on merge or by hand, not on no trigger" ]
    [ -z "$(logged)" ]
}

@test "release gets its environment from the CICD_ variables" {
    export CICD_TRIGGER=manual CICD_BASE="$BASE" \
        CICD_INPUT_BUMP_TYPE=minor CICD_INPUT_SUBDIRECTORY=sub \
        CICD_INPUT_CHANGELOG_DESCRIPTION='a $(change); with "quotes"' \
        GITHUB_TOKEN=ghs_token
    run_release
    [ "$status" -eq 0 ]
    [ "$(env_of GITHUB_EVENT_BEFORE)" = "$BASE" ]
    [ "$(env_of INPUT_BUMP_TYPE)" = "minor" ]
    [ "$(env_of INPUT_SUBDIRECTORY)" = "sub" ]
    [ "$(env_of INPUT_CHANGELOG_DESCRIPTION)" = 'a $(change); with "quotes"' ]
    [ "$(env_of GH_TOKEN)" = "ghs_token" ]
}

@test "unset inputs reach release empty" {
    export CICD_TRIGGER=manual
    run_release
    [ "$status" -eq 0 ]
    for name in GITHUB_EVENT_BEFORE INPUT_BUMP_TYPE INPUT_SUBDIRECTORY \
            INPUT_CHANGELOG_DESCRIPTION GH_TOKEN; do
        has_env "$name"
        [ -z "$(env_of "$name")" ]
    done
}
