# A local check commits a version bump

> Captured: 2026-11-28

## What was happening

Solo session for gcd-63f3, which changes `git-cicd` and the templates. The first `./git-cicd check --setup` failed on Version Check (`.vendored/pkg/git-semver/git-semver check-bump`). That run also left a new commit on the branch, `chore: bump version (root 0.3.0 -> 0.3.1)`. The change needed a minor bump (0.4.0), so the commit had to be dropped with `git rebase --onto` before running `git-semver bump minor --no-push`.

## Headache

Running `./git-cicd check` locally made the version-check job (git-semver `check-bump`) commit a patch bump to the working branch without being asked. A local check should report a missing bump and leave committing to the developer.
