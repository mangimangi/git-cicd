#!/usr/bin/env bats
# ci/update-vendored.sh: .vendored/install with the job's declared inputs.

load helper

setup() {
    common_setup
    fake_python_tool .vendored/install
}

@test "defaults update every vendor to latest with a pull request" {
    run bash ci/update-vendored.sh
    [ "$status" -eq 0 ]
    [ "$(args)" = "$(printf '%s\n' all --version latest --pr --deps=install)" ]
}

@test "the vendor and version inputs are passed" {
    export CICD_INPUT_VENDOR=mangimangi/git-semver CICD_INPUT_VERSION=v1.2.0
    run bash ci/update-vendored.sh
    [ "$status" -eq 0 ]
    [ "$(args)" = "$(printf '%s\n' mangimangi/git-semver --version v1.2.0 --pr --deps=install)" ]
}

@test "--private only when the private input is true" {
    export CICD_INPUT_PRIVATE=true
    run bash ci/update-vendored.sh
    [ "$status" -eq 0 ]
    [ "$(args | tail -n1)" = "--private" ]
    : > "$LOG"
    for value in false TRUE yes ""; do
        CICD_INPUT_PRIVATE="$value" run bash ci/update-vendored.sh
        [ "$status" -eq 0 ]
    done
    [ -z "$(args | grep -x -- --private)" ]
}

@test "GH_TOKEN is CICD_WRITE_TOKEN over VENDOR_PAT and GITHUB_TOKEN" {
    export CICD_WRITE_TOKEN=write_token VENDOR_PAT=pat_token GITHUB_TOKEN=ghs_token
    run bash ci/update-vendored.sh
    [ "$(env_of GH_TOKEN)" = "write_token" ]
}

@test "GH_TOKEN is VENDOR_PAT without CICD_WRITE_TOKEN" {
    export VENDOR_PAT=pat_token GITHUB_TOKEN=ghs_token
    run bash ci/update-vendored.sh
    [ "$(env_of GH_TOKEN)" = "pat_token" ]
}

@test "GH_TOKEN is GITHUB_TOKEN without CICD_WRITE_TOKEN or VENDOR_PAT" {
    export GITHUB_TOKEN=ghs_token
    run bash ci/update-vendored.sh
    [ "$(env_of GH_TOKEN)" = "ghs_token" ]
}

@test "inputs arrive verbatim as arguments, never through a shell" {
    export CICD_INPUT_VENDOR='$(touch pwned); x' CICD_INPUT_VERSION='`touch pwned2` y'
    run bash ci/update-vendored.sh
    [ "$status" -eq 0 ]
    [ "$(args | sed -n 1p)" = '$(touch pwned); x' ]
    [ "$(args | sed -n 3p)" = '`touch pwned2` y' ]
    [ "$(args | wc -l)" -eq 5 ]
    [ ! -e pwned ]
    [ ! -e pwned2 ]
}
