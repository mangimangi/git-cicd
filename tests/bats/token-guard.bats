#!/usr/bin/env bats
# No bats test reads a real token: helper.bash removes the five token names
# that ci/test.sh sets to sentinel values, so this fails when that guard is
# removed.

load helper

setup() {
    common_setup
}

@test "no token is in a test's environment" {
    for name in CICD_WRITE_TOKEN CICD_READ_TOKEN VENDOR_PAT GH_TOKEN GITHUB_TOKEN; do
        [ -z "${!name+set}" ] || { echo "$name is set"; false; }
    done
}
