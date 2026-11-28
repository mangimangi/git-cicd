#!/usr/bin/env bats
# ci/vendor-check.sh: .vendored/check against the change's base.

load helper

setup() {
    common_setup
    fake_python_tool .vendored/check
    export CICD_BASE=0123abc
}

@test "GITHUB_HEAD_REF comes from CICD_SOURCE_BRANCH when unset" {
    export CICD_SOURCE_BRANCH=chore/install-git-semver
    run bash ci/vendor-check.sh
    [ "$status" -eq 0 ]
    [ "$(env_of GITHUB_HEAD_REF)" = "chore/install-git-semver" ]
}

@test "a set GITHUB_HEAD_REF is kept" {
    export GITHUB_HEAD_REF=feature CICD_SOURCE_BRANCH=chore/install-git-semver
    run bash ci/vendor-check.sh
    [ "$(env_of GITHUB_HEAD_REF)" = "feature" ]
}

@test "the base is passed to the check" {
    run bash ci/vendor-check.sh
    [ "$status" -eq 0 ]
    [ "$(args)" = "$(printf '%s\n' --base 0123abc)" ]
}

@test "the check's failure fails the step" {
    printf '#!/usr/bin/env python3\nimport sys\nsys.exit(3)\n' > .vendored/check
    run bash ci/vendor-check.sh
    [ "$status" -eq 3 ]
}
