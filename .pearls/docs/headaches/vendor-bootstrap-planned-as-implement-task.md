# Vendor bootstrap planned as an implement-mode task

> Captured: 2026-11-27

## What was happening

Implementing gcd-e74c.8 ("git-cicd uses itself and is set up to release") in an automated implement session on branch `gcd-e74c/impl`. Scope item 1 asks for git-vendored and git-semver to be installed into this repository (`.vendored/install`, `check`, `audit`, `feedback`, `remove`, `.vendored/pkg/git-semver/`, `install-vendored.yml`, `check-vendor.yml`, `version-bump.yml`). The session's protected-paths rule forbids adding vendor-protected files under `.vendored/` in-session, and `.vendored/check` would flag them on a non-install branch. Everything else in .8 was built (own config, `ci/` scripts, generated workflow, `VERSION`, `.vendored/configs/git-semver.json`, README, AGENTS.md, PR #2 into `plan/mdci-dev-6692`), but the vendoring part, and with it the first-release acceptance criterion, could not be done.

## Headache

gcd-e74c.8 asks the implement session to install git-vendored and git-semver into .vendored/, but the session's protected-paths rule forbids adding vendor-protected files in-session (they belong to the install-vendored workflow, and .vendored/check would reject them on a non-install branch). A repository with no .vendored/ yet has no workflow to bootstrap from, so refine should plan vendor bootstrap as an owner step or an install-branch PR, not as an implement-mode task.
