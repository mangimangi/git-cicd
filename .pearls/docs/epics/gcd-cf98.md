# git-cicd: a job declares its permissions and its secrets

> Unit 1 of plan `git-dev-aef7` (record: `mangimangi/git-dev`, `.pearls/docs/epics/git-dev-aef7.md`). Agreed with the owner on 2026-11-28. Delivers into `plan/git-dev-aef7`. Re-check every code reference against the code before using it.

## Problem

Which token permissions and which secret a job gets is decided by its trigger, not by the job. The job that runs a repository's scripts gets, on `merge`, `cron` and manual runs, `contents: write` and `pull-requests: write` (`templates/workflows/merge.yml` lines 156-157, `cron.yml` 134-135, `manual.yml` 172-173) and the secret `VENDOR_PAT` (`merge.yml` line 179, `cron.yml` 157, `manual.yml` 195); on `open` a read-only token and no secret (`OPEN_WITHHELD_ENV`, `git-cicd` line 973; the README's trigger/secret table at line 275). That fixed rule is in the way three times, each found while preparing the migration of pearls, madreperla and medici (`mangimangi/git-dev`, `.pearls/docs/adopting-git-cicd-jobs-and-tag-on-merge-releases.md`):

- **A job cannot publish packages.** medici's image workflows push to the container registry and need `packages: write`. It cannot stay a separate workflow chained off the release: a tag or release made with a workflow's own token starts no workflow. It has to be a later step of the `release` job, and that job cannot get the permission.
- **A pull request job cannot read a private repository.** pearls' and madreperla's toolchain-contract check does, with `VENDOR_PAT`; since 0.1.0 an `open` job gets none, on purpose, because that token can write.
- **One pull request job needs to write.** git-semver's version check is to push the version bump to the pull request's branch (unit 2 of the plan); that needs a write token in exactly one `open` job.

And the rule hands a write token to jobs that never use it: this repository's `release` job receives `VENDOR_PAT`.

## What already was decided (do not reopen)

- **A job declares what it needs** (owner: "yeah job declares it"). `packages: write` is a permission of the workflow's own token; no personal token is involved.
- **Two tokens, named for what they can do:** `CICD_WRITE_TOKEN` replaces `VENDOR_PAT` (pushes branches, opens pull requests, writes workflow files); `CICD_READ_TOKEN` is new (reads private repositories; cannot write).
- **Nothing is passed undeclared, on any trigger, from this release.** A script receives a secret only if its job declares it. This is a breaking release; only three jobs anywhere depend on the old rule (`update-vendored` in git-cicd, git-semver and git-vendored).
- A job may still declare the old name `VENDOR_PAT`, documented as deprecated, so a repository can upgrade before it renames its secret.
- `GITHUB_TOKEN` is still given to every job; an `open` job that declares nothing gets exactly what it gets today.
- The injection rules hold: a declared name is a validated identifier; a value from the config never reaches a `run:` block; a secret reaches a script only as an environment variable.
- Generated files are checked: where a file must vary with the config, `generate` writes it and `verify` fails when file and config disagree, as for the cron schedule and the Manual form. No existing row or status name changes.
- Coverage: the `test` job fails below 99%; every change comes with its tests, shell with bats. The suite must not read a real token from the environment.
- No vendor-protected file is added, changed or deleted. Run `python3 .vendored/check --base origin/plan/git-dev-aef7` before finishing.
- The version is raised in the unit's own work (a minor bump), with the changelog entry, as the `version-check` job requires.

How a declared permission and a declared secret reach one job among several that share a workflow is for this unit to work out against the platform's documentation (whether a job's `permissions` can depend on a value computed at run time; how a secret is selected by name). Look it up; do not assume.

## What ships

- A job declares the secrets it receives; nothing is passed undeclared
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd` (`JOB_FIELDS` line 59, job validation around lines 371-499, `OPEN_WITHHELD_ENV` line 973 and the environment a script is given around line 983, `run_job` line 1023, decide, generate, verify), `templates/workflows/*.yml` (the `env:` of the job that runs the config's scripts), `templates/config.schema`, `tests/`
  - shape: A job may declare a list of secrets from a documented set: `CICD_WRITE_TOKEN`, `CICD_READ_TOKEN`, and `VENDOR_PAT` (deprecated). `validate` refuses any other name, a malformed declaration or a duplicate, naming the job and the reason. On every trigger, including `open` and a local `check`, a script's environment holds a secret if and only if its job declares it; a secret present in the caller's environment that the job does not declare is removed before the script runs. The trigger no longer decides: `VENDOR_PAT` is passed to no job that does not declare it. The generated workflows give each job only the secrets it declares; a job that declares none has no secret in its environment at all, not an empty one it could mistake for a value. A declared secret that is not set in the repository reaches the script as unset, and the report says which declared secrets were absent, by name only. No secret value is ever printed, in a log, a report or an error.

- A job declares the permissions its token needs
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd` (validation, decide, generate, verify), `templates/workflows/*.yml` (the `permissions:` of the job that runs the config's scripts), `templates/config.schema`, `tests/`
  - shape: A job may declare permissions for the workflow's own token beyond its trigger's default, from a documented set that includes `packages: write`. `validate` refuses a permission outside the set, a level that is not allowed, and a write permission declared by a job that runs on `open` unless the documentation says why that one is allowed; each refusal names the job and the reason. A job that declares none keeps its trigger's default. In the generated workflows a job gets exactly its trigger's default plus what it declares, and no other job gains anything from it: two jobs on the same trigger with different declarations run with different permissions. `verify` fails when the generated files and the declarations disagree.

- git-cicd's own jobs declare what they need, and the docs say the rule
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `.vendored/configs/git-cicd.json`, `ci/update-vendored.sh`, generated `.github/workflows/git-cicd-*.yml`, `README.md` ("The config", "What a script is given", the trigger/secret table at line 275, "The generated workflows", "Not built yet" line 836, "Developing git-cicd"), `AGENTS.md`, `CHANGELOG.md`, `VERSION`
  - shape: This repository's `update-vendored` job declares `CICD_WRITE_TOKEN` and `VENDOR_PAT` (so it keeps working until the owner has renamed the secret), and `ci/update-vendored.sh` uses the first that is set; `release`, `test`, `vendor-check` and `version-check` declare nothing. The generated workflows are regenerated and committed. The README replaces the trigger/secret table with the rule (a job gets what it declares), documents both declarations with an example for each of the three needs above (a release job that publishes packages; a pull request job that reads a private repository with `CICD_READ_TOKEN`; a job that proposes changes with `CICD_WRITE_TOKEN`), says what each token is for and what permissions a fine-grained token needs for it, and gives an adopter's upgrade steps in order (declare, add the renamed secret, `generate`, commit). The changelog entry marks the release breaking and says what breaks for whom. `VERSION` is raised (minor).

## Acceptance criteria

- With this repository's config, the `update-vendored` job's script sees `CICD_WRITE_TOKEN` (and `VENDOR_PAT`) and the `release` job's script sees neither, on `merge`, `cron` and manual runs; shown by tests on `run-job` and on the generated files.
- An `open` job that declares `CICD_READ_TOKEN` receives it and nothing else; one that declares nothing receives no secret even when the caller's environment has all three.
- A job that declares `packages: write` runs with it and a sibling job on the same trigger does not; shown on the generated workflow.
- `validate` refuses an unknown secret name, an unknown permission, and a malformed declaration, each with a message naming the job.
- `./git-cicd verify` fails after a declaration is added or changed without regenerating, and passes after `generate`.
- No test reads a token from the environment: the suite removes `CICD_WRITE_TOKEN`, `CICD_READ_TOKEN`, `VENDOR_PAT`, `GH_TOKEN` and `GITHUB_TOKEN` before every test, and a test fails if that guard is removed.
- `./git-cicd check` passes with coverage at 99% or more; `.vendored/pkg/git-semver/git-semver check-bump` passes against `origin/main`.
- The pull request into `plan/git-dev-aef7` has a passing `Verdict / git-cicd:verdict`.
- `python3 .vendored/check --base origin/plan/git-dev-aef7` reports nothing.

## Out of scope

- Any change in git-semver or git-vendored (units 2 and 3 of the plan), and pushing a version bump.
- A GitHub App as the identity behind a token; secrets outside the documented set; an image or runtime per job.
- Migrating a consumer.
