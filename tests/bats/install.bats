#!/usr/bin/env bats
# install.sh: what it writes where, on a first install and on an upgrade.
# fetch_file is replaced by a copy from this checkout (a local mirror), as
# tests/test_install.py's stub_install_sh does; nothing is downloaded.

load helper

INSTALL_DIR=.vendored/pkg/git-cicd

setup() {
    common_setup
    python3 - "$ROOT/install.sh" "$BATS_TEST_TMPDIR/install.sh" "$ROOT" <<'PY'
import re, sys
source, dest, mirror = sys.argv[1:]
text = open(source).read()
stub = ('fetch_file() {\n    local repo_path="$1"\n    local dest="$2"\n'
        f'    cp "{mirror}/$repo_path" "$dest"\n}}')
modified = re.sub(r"^fetch_file\(\) \{.*?^\}", lambda m: stub, text,
                  flags=re.MULTILINE | re.DOTALL)
assert modified != text
open(dest, "w").write(modified)
PY
    INSTALL="$BATS_TEST_TMPDIR/install.sh"
    MANIFEST="$BATS_TEST_TMPDIR/manifest"
    export VENDOR_INSTALL_DIR="$INSTALL_DIR" VENDOR_MANIFEST="$MANIFEST"
}

install() {
    run bash "$INSTALL" "$@"
}

@test "a first install writes the tool, templates, config, schema and workflows" {
    install v1.2.3
    [ "$status" -eq 0 ]
    [[ "$output" == "Installing git-cicd v1.2.3 from mangimangi/git-cicd"* ]]
    [[ "$output" == *"Created .vendored/configs/git-cicd.json (declare your jobs, then run $INSTALL_DIR/git-cicd generate)"* ]]
    [[ "$output" == *"Done! git-cicd v1.2.3 installed." ]]
    [ -x "$INSTALL_DIR/git-cicd" ]
    cmp "$ROOT/git-cicd" "$INSTALL_DIR/git-cicd"
    for trigger in open merge cron manual; do
        cmp "$ROOT/templates/workflows/$trigger.yml" \
            "$INSTALL_DIR/templates/workflows/$trigger.yml"
    done
    cmp "$ROOT/templates/config.json" .vendored/configs/git-cicd.json
    cmp "$ROOT/templates/config.schema" .vendored/manifests/git-cicd.schema
    for trigger in open merge manual; do
        [ -f ".github/workflows/git-cicd-$trigger.yml" ]
    done
    [ ! -e .github/workflows/git-cicd-cron.yml ]   # no job has cron
    [ "$(cat "$MANIFEST")" = "$(printf '%s\n' \
        "$INSTALL_DIR/git-cicd" \
        "$INSTALL_DIR/templates/workflows/open.yml" \
        "$INSTALL_DIR/templates/workflows/merge.yml" \
        "$INSTALL_DIR/templates/workflows/cron.yml" \
        "$INSTALL_DIR/templates/workflows/manual.yml" \
        .vendored/manifests/git-cicd.schema)" ]
    # the generated workflows are the repository's to commit, never protected
    ! grep -q '^\.github/workflows/' "$MANIFEST"
}

@test "VENDOR_REF names the version over the argument" {
    VENDOR_REF=v2.0.0 install 1.0.0
    [ "$status" -eq 0 ]
    [[ "$output" == "Installing git-cicd v2.0.0 from mangimangi/git-cicd"* ]]
}

@test "an upgrade replaces the code, keeps the config and regenerates" {
    mkdir -p "$INSTALL_DIR/templates" .github/workflows .vendored/configs
    echo "old tool" > "$INSTALL_DIR/git-cicd"
    echo "old template" > "$INSTALL_DIR/templates/workflow.yml"
    echo "old workflow" > .github/workflows/git-cicd.yml
    mkdir -p ci
    printf '#!/bin/sh\nexit 0\n' > ci/nightly.sh
    chmod +x ci/nightly.sh
    cat > .vendored/configs/git-cicd.json <<'JSON'
{"jobs": {"nightly": {"on": ["cron"], "cron": "0 3 * * *",
                      "branches": ["main"], "steps": ["ci/nightly.sh"]}}}
JSON
    cp .vendored/configs/git-cicd.json "$BATS_TEST_TMPDIR/config.before"
    # the manifest of a version that listed the generated workflows
    printf '%s\n' "$INSTALL_DIR/git-cicd" .github/workflows/git-cicd-open.yml \
        .github/workflows/git-cicd-merge.yml \
        .github/workflows/git-cicd-manual.yml > "$MANIFEST"
    install v1.3.0
    [ "$status" -eq 0 ]
    [[ "$output" != *"Created .vendored/configs/git-cicd.json"* ]]
    cmp "$ROOT/git-cicd" "$INSTALL_DIR/git-cicd"
    cmp "$BATS_TEST_TMPDIR/config.before" .vendored/configs/git-cicd.json
    [ ! -e "$INSTALL_DIR/templates/workflow.yml" ]
    [ ! -e .github/workflows/git-cicd.yml ]
    grep -q "0 3 \* \* \*" .github/workflows/git-cicd-cron.yml
    for trigger in open merge cron manual; do
        [ -f ".github/workflows/git-cicd-$trigger.yml" ]
    done
    grep -qx "$INSTALL_DIR/git-cicd" "$MANIFEST"
    ! grep -q '^\.github/workflows/' "$MANIFEST"
}

@test "without VENDOR_INSTALL_DIR the install refuses" {
    unset VENDOR_INSTALL_DIR
    install v1.2.3
    [ "$status" -ne 0 ]
    [[ "$output" == *"VENDOR_INSTALL_DIR is required"* ]]
    [ ! -e .vendored ]
}
