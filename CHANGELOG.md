# Changelog

Releases of git-cicd. Each entry is written by `git-semver bump` in the pull request that raises the version; merging it into `main` tags and publishes that version.

## [0.1.0] - 2026-11-28

### Changed
- A manual run is started from a form that lists the jobs and their inputs; the free-text `inputs` field and CICD_MANUAL_INPUTS are removed (breaking: run `generate`, pass one `-f <name>=<value>` per input) (gcd-8f83); the Open workflow passes VENDOR_PAT to pull request jobs (gcd-9e80); git-cicd bumps its version in the pull request and tags on merge (gcd-c8e1)

## [0.0.4] - 2026-11-28

### Changed
- Every trigger executes; git-cicd runs its own release, vendor check and update (plan git-dev-883c) (#14)
- chore: ignore medici-written modes/ and .medici/ (#11)

## [0.0.3] - 2026-11-27

### Changed
- gcd-2809: moments are called triggers (CICD_TRIGGER, --trigger, docs) (#10)

## [0.0.2] - 2026-11-27

### Changed
- gcd-d9eb: pending git-cicd verdict no longer waits for a superseded run (#6) (#7)

## [0.0.1] - 2026-11-27

### Changed
- gcd-e74c: git-cicd reads a config, decides, runs and reports on open (#2)
- Bootstrap git-vendored 0.0.28 and install git-semver 0.0.15
- Scaffold the medici project files with medici init
- Initial commit

