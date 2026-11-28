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
  - issue: gcd-cf98.1
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd` (`JOB_FIELDS` line 59, job validation around lines 371-499, `OPEN_WITHHELD_ENV` line 973 and the environment a script is given around line 983, `run_job` line 1023, decide, generate, verify), `templates/workflows/*.yml` (the `env:` of the job that runs the config's scripts), `templates/config.schema`, `tests/`
  - shape: A job may declare a list of secrets from a documented set: `CICD_WRITE_TOKEN`, `CICD_READ_TOKEN`, and `VENDOR_PAT` (deprecated). `validate` refuses any other name, a malformed declaration or a duplicate, naming the job and the reason. On every trigger, including `open` and a local `check`, a script's environment holds a secret if and only if its job declares it; a secret present in the caller's environment that the job does not declare is removed before the script runs. The trigger no longer decides: `VENDOR_PAT` is passed to no job that does not declare it. The generated workflows give each job only the secrets it declares; a job that declares none has no secret in its environment at all, not an empty one it could mistake for a value. A declared secret that is not set in the repository reaches the script as unset, and the report says which declared secrets were absent, by name only. No secret value is ever printed, in a log, a report or an error.

- A job declares the permissions its token needs
  - issue: gcd-cf98.2 (blocked by gcd-cf98.1)
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd` (validation, decide, generate, verify), `templates/workflows/*.yml` (the `permissions:` of the job that runs the config's scripts), `templates/config.schema`, `tests/`
  - shape: A job may declare permissions for the workflow's own token beyond its trigger's default, from a documented set that includes `packages: write`. `validate` refuses a permission outside the set, a level that is not allowed, and a write permission declared by a job that runs on `open` unless the documentation says why that one is allowed; each refusal names the job and the reason. A job that declares none keeps its trigger's default. In the generated workflows a job gets exactly its trigger's default plus what it declares, and no other job gains anything from it: two jobs on the same trigger with different declarations run with different permissions. `verify` fails when the generated files and the declarations disagree.

- git-cicd's own jobs declare what they need, and the docs say the rule
  - issue: gcd-cf98.3 (blocked by gcd-cf98.1, gcd-cf98.2)
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

## Issues

| Issue | Scope | Blocked by |
|---|---|---|
| gcd-cf98.1 | `secrets` job field, `script_env` strips undeclared secrets on every trigger, absent secrets reported by name, per-entry secret selection in the run step's `env`, token guard in pytest and bats | — |
| gcd-cf98.2 | `permissions` job field, a generated run job for each permission set, decide outputs for each group, generate/verify | gcd-cf98.1 |
| gcd-cf98.3 | this repo's config and `ci/update-vendored.sh`, regenerated workflows, README/AGENTS.md rule and upgrade steps, minor bump to 0.2.0 with a breaking changelog entry | gcd-cf98.1, gcd-cf98.2 |

The acceptance criteria above are split this way: the `open`/`CICD_READ_TOKEN`, the "declares nothing receives nothing" and the token-guard criteria go to gcd-cf98.1; `packages: write` vs sibling and `verify` after a declaration change go to gcd-cf98.2; the own-config `update-vendored`/`release` criterion, `check-bump`, the Verdict on the PR into `plan/git-dev-aef7` and the final vendor check go to gcd-cf98.3. Every issue also keeps the 99% coverage, `validate` refusal and vendor-check criteria.

## Refinement decisions

- **Three issues in the existing epic gcd-cf98, done in order** (gcd-cf98.1, gcd-cf98.2, gcd-cf98.3). Reason: the doc's three "What ships" items map one to one; .1 and .2 touch the same validation code, templates and decide outputs, so running them in order avoids conflicts, and .3 needs both declarations to exist.
- **Secrets are picked per matrix entry by an expression in the run step's `env`** (gcd-cf98.1): decide gets a `secrets` output (job → declared names); each documented name gets one line of the form `X: ${{ contains(fromJSON(needs.decide.outputs.secrets)[matrix.job], 'X') && secrets.X || '' }}`; `script_env` removes undeclared and empty names. Reason: the set of names is fixed, so the templates stay fixed text, no config value reaches the workflow, and an undeclared secret's value never reaches the step. The implementer checks this against GitHub's documentation and records any change.
- **A declared secret that is empty is treated as unset and removed** (gcd-cf98.1). Reason: the doc says a job must never see "an empty one it could mistake for a value".
- **The token guard is proved by sentinels** (gcd-cf98.1): an autouse conftest fixture and `tests/bats/helper.bash` remove the five names, `ci/test.sh` exports sentinel values before pytest and bats, and a pytest test and a bats test assert none of the five is set. Reason: without the sentinels, removing the guard would fail no test on a machine with no tokens set, so the acceptance criterion "a test fails if that guard is removed" could not be shown.
- **Permissions get a generated run job for each permission set** (gcd-cf98.2). For each trigger, every effective permission set that differs from the trigger's default gets its own generated run job (the default plus the set, written literally), with a matrix from its own decide output; the default `run` job keeps the other jobs. Reason: job-level `permissions` are expected to accept only literal values (the implementer checks this), and every matrix entry gets the job's permissions, so this is the only way two sibling jobs can run with different permissions. A config with no declarations generates exactly today's files. How a group job with nothing to run is shown (skipped by a job-level `if`, or a placeholder with its own documented title) is decided by the implementer after checking how GitHub renders it, so that no raw `${{ }}` row appears.
- **The permissions that can be declared are `contents`, `pull-requests`, `issues` and `packages`, each at `read` or `write`, in GitHub's own object syntax** (gcd-cf98.2). Reason: they cover `packages: write` and the scopes the triggers already use, and a small set can be documented in full.
- **No write permission is allowed on `open`** (gcd-cf98.2). Reason: `open` runs a pull request's own code. The one `open` job that must write (git-semver's version check, unit 2) does it with a declared `CICD_WRITE_TOKEN`, not with the workflow token.
- **A job's effective permissions are its trigger's default merged with what it declares, the higher level winning; a declaration that adds nothing is accepted** (gcd-cf98.2). Reason: a job on several triggers can then declare one set, and a declaration that adds nothing changes nothing.
- **`ci/update-vendored.sh` uses `CICD_WRITE_TOKEN`, else `VENDOR_PAT`, else `GITHUB_TOKEN`; the `private` input's description names the new token** (gcd-cf98.3). Reason: the doc says to "use the first that is set", and `GITHUB_TOKEN` stays as the last fallback the script already uses. Changing the description changes the Manual form, so the workflows are regenerated in the same issue.
- **The README documents fine-grained token permissions: read token = Contents read (plus Metadata); write token = Contents, Pull requests and Workflows read/write** (gcd-cf98.3). Reason: the doc asks for them. The implementer checks the names against GitHub's documentation.
- **The version is raised to 0.2.0 with `git-semver bump minor`** (gcd-cf98.3). Reason: the doc asks for a minor bump in the unit's own work, and below 1.0 a minor bump is how this repo marks a breaking change (0.1.0 did the same).


## Implementation notes

- **gcd-cf98.1, secret selection.** GitHub's documentation could not be fetched from the implementing session (no network). The mechanism relies on documented behaviour: the `secrets` context is available in a step's `env`; `&&` and `||` return an operand's value, with `''` falsy; `contains()` over an array tests membership, and over `null` (a key missing from `fromJSON(...)`) is false. An undeclared entry therefore gets `''`, never the value, and `script_env` removes the empty name. decide's `secrets` output lists every job (with `[]` for none) so the lookup never hits a missing key for a config job.
- **gcd-cf98.2, literal permissions.** From the workflow syntax and contexts references (as known to the implementer; not re-fetched, no network): `jobs.<job_id>.permissions` takes literal levels (`read`, `write`, `none`) and the contexts reference lists no context as available there, so it cannot vary per matrix entry. Hence one generated run job per distinct effective permission set, id `run-<scope>-<level>...` for each scope and level beyond the trigger's default (e.g. `run-packages-write`), in first-seen config order.
- **gcd-cf98.2, a group job with nothing to run.** It is not skipped with a job-level `if` (a matrix job skipped before its matrix is evaluated shows its raw `${{ }}` name, as README "Rows" explains for `run`). It runs a placeholder entry `(nothing:<group id>)`, titled `Nothing needed`, row `Nothing needed / <repo>:(nothing:<group id>)`, with its steps skipped; documented in README's Rows table.
- **gcd-cf98.2, rendering.** Templates hold `__GROUP_OUTPUTS__` (decide's `groups` output), `__GROUP_JOBS__` (after `run`) and `__GROUP_NEEDS__` (in the report's `needs`); all render empty without declarations, so such configs generate the same files as before. A group job is the template's own `run` job with its id, permissions, matrix source and placeholder changed. decide's existing outputs (`jobs`, `runs`) become the default `run` job's matrix; `any` keeps meaning "any job needed in this run".
