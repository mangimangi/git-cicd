# Changelog

Releases of git-cicd. Each entry is written by `git-semver bump` in the pull request that raises the version; merging it into `main` tags and publishes that version.

## [0.3.0] - 2026-11-28

### Changed
- The Manual workflow's job dropdown lists each job by its row name, <name> / <repo>:<job>, as a pull request's checks show it, and input descriptions name their jobs the same way (gcd-cffa). Adopters run generate after upgrading and commit the Manual workflow: the form's job values changed (the bare config key is still accepted from the command line). <repo> no longer comes from GITHUB_REPOSITORY: it is the new config key repository, else the origin remote's last path segment, else the directory name.

## [0.2.0] - 2026-11-28

### Changed
- Breaking: a job gets only the secrets and permissions it declares (gcd-cf98.1, gcd-cf98.2, gcd-cf98.3). A job on merge, cron or a manual run that used VENDOR_PAT without declaring it no longer receives it: declare "secrets": ["VENDOR_PAT"], or rename the secret to CICD_WRITE_TOKEN and declare that, then run generate and commit the config and the workflows. Every documented secret (CICD_WRITE_TOKEN, CICD_READ_TOKEN, VENDOR_PAT) is removed from the environment of a job that does not declare it, on every trigger and in a local check. New: declared secrets CICD_READ_TOKEN (reads private repositories) and CICD_WRITE_TOKEN (proposes changes), VENDOR_PAT deprecated; declared permissions of the workflow token (contents, pull-requests, issues, packages; read or write; no write on open), each distinct set in a generated run job of its own; absent declared secrets named in the report.

## [0.1.0] - 2026-11-28

### Changed
- A manual run is started from a form that lists the manual jobs (a `job` dropdown) and their declared inputs; the free-text `inputs` field and `CICD_MANUAL_INPUTS` are removed (breaking: run `generate` and commit the Manual workflow, start runs with one `-f <name>=<value>` per input, and read `CICD_INPUT_<NAME>` in scripts) (gcd-8f83)
- The `Open` workflow no longer passes `VENDOR_PAT` to the job that runs a pull request's scripts, and `run-job --trigger open` (so `check`) removes an inherited one; `Merge`, `Cron` and `Manual` still pass it (breaking for an `open` job that read a private vendor with `VENDOR_PAT`: run `generate`, and move that step to a job on `merge`, `cron` or a manual run) (gcd-9e80)
- `install.sh` no longer lists the generated workflows in the install manifest: they are the repository's to commit and are never protected (every install still regenerates them on disk; commit them yourself) (gcd-364e)
- A run that needs no job shows a `Nothing needed / <repo>:(nothing)` placeholder row instead of a skipped row named with raw `${{ }}` text (run `generate` and commit the workflows) (gcd-69df)
- Line coverage of `git-cicd`, including the runs tests start as subprocesses, is measured and enforced at 99%, and `install.sh` and the `ci/` scripts have bats tests (no change for adopters) (gcd-1ee1)
- This repository raises its version in the pull request and tags the merged commit on `main` (its own release; no change for adopters) (gcd-c8e1)

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

