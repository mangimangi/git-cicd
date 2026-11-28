# git-cicd: every trigger executes

> Unit 1 of plan `git-dev-883c` (record: `mangimangi/git-dev`, `.pearls/docs/epics/git-dev-883c.md`). Agreed with the owner on 2026-11-28. Delivers into `plan/git-dev-883c`. Re-check every code reference against the code before using it.

## Problem

git-cicd's mission is "a vendored framework that decides which checks run on a change, runs them, and owns what happens after a merge". At v0.0.3 only the `open` trigger and local runs execute. The `merge` and `cron` triggers and manual runs validate in a config, and `decide`/`run-job`/`report` exit 2 with `the <trigger> trigger is not built yet`; only `.github/workflows/git-cicd-open.yml` is generated (README, "Not built yet" and "The generated workflows").

Because of that, git-cicd's own repository still runs three hand-written or vendor-installed workflows next to its generated one:

| Workflow | Trigger | What it runs |
|---|---|---|
| `version-bump.yml` ("Bump & Release") | push to `main`; manual with `bump_type`, `subdirectory`, `changelog_description` | job `bump`: `python3 .vendored/pkg/git-semver/release bump` (skipped when the head commit message starts with `chore: bump version` or `chore: install`); job `publish`: `python3 .vendored/pkg/git-semver/release publish` when the head commit message starts with `chore: bump version`; `contents: write`, `pull-requests: write`; concurrency group `push-to-main`, `cancel-in-progress: false`; checkout with `fetch-depth: 0`, `fetch-tags: true`; env `GH_TOKEN`, `GITHUB_EVENT_BEFORE`, `INPUT_BUMP_TYPE`, `INPUT_SUBDIRECTORY`, `INPUT_CHANGELOG_DESCRIPTION` |
| `check-vendor.yml` ("Check Vendor Files") | every pull request | `python3 .vendored/check`, checkout with `fetch-depth: 0` |
| `install-vendored.yml` ("Install Vendored") | cron `0 9 * * 1`; manual with `vendor`, `version`, `private` | `python3 .vendored/install "$VENDOR" --version "$VERSION" --pr --deps=install`; `contents: write`, `pull-requests: write`; env `GITHUB_TOKEN`, `VENDOR_PAT`, `GH_TOKEN` |

The same three workflows are in git-semver and git-vendored and wait for this unit before they can move.

## What already was decided (do not reopen)

From the interface agreed on 2026-11-27 (README; `mangimangi/git-dev`, `.pearls/docs/git-tools-implement-git-cicd.md`):

- One generated workflow per trigger: `Open`, `Merge`, `Cron`, `Manual`, in `.github/workflows/git-cicd-open.yml`, `git-cicd-merge.yml`, `git-cicd-cron.yml`, `git-cicd-manual.yml`. Names and file names are fixed. Adding a trigger adds a file and changes none.
- Every generated file is fixed text except the cron workflow's schedule block (one entry per distinct cron expression in the config) and the tool path.
- `merge`: a change lands on a branch matching `branches` and affects the job. `merge` runs on one branch go one at a time and are never cancelled.
- Token permissions are write on `merge`, `cron` and manual; `open` stays read-only plus `statuses: write` on decide and report.
- `cron`: the job carries its own expression; cron branches are literal names; GitHub runs schedules only from the default branch's copy of the file.
- Manual: on unless a job says `"manual": false`; `branches` still binds; only `paths` is ignored. The generated file carries a `workflow_dispatch` with one free-text `job` input, as fixed text.
- No ordering between jobs: bump then publish is steps in one job.
- Injection rules: every fact reaches a script as an environment variable or a file, never as part of a command line; never `${{ }}` inside `run:`.
- The verdict when there is no pull request (owner, 2026-11-27: "status is good"): the commit status `Verdict / git-cicd:verdict` on the commit the run is for.
- The Monday update is kept like-for-like as the first `cron` job (owner, 2026-11-27: "id say keep it just to test the cron trigger").
- Declared inputs for manual runs were reserved, not designed. This unit designs them, under the injection rules.

## What ships

- The `merge` trigger executes
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd` (decide, run-job, report, generate, verify), `templates/workflows/merge.yml` (new), `install.sh`, `tests/`, `README.md`
  - shape: `decide --trigger merge`, `run-job --trigger merge` and `report` work for a change that landed on a branch: the needed jobs are those with `merge` in `on`, whose `branches` match the branch, and that the change affects (the same `paths` and `needs_nothing` rules as `open`; the changed files are what the push brought). `generate` writes `.github/workflows/git-cicd-merge.yml`, named `Merge`, fixed text: its GitHub event is a push to any branch (branches are decided by the tool); `contents: write` and `pull-requests: write` for the job that runs the config's scripts; runs on one branch queue and are never cancelled; full history and tags are available to a step (git-semver's release needs them). The verdict is the commit status `Verdict / git-cicd:verdict` on the landed commit, pending from the first step of decide and final from the last step of report. Scripts get `CICD_TRIGGER=merge` and the other `CICD_` variables with documented meanings on `merge` (target is the branch landed on; base is the commit before the push). `verify` covers the new file.

- Manual runs execute
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd`, `templates/workflows/manual.yml` (new), `install.sh`, `tests/`, `README.md`
  - shape: A manual run of one named job executes: allowed unless the job says `"manual": false`; the job's `branches` still bind against the branch the run is started on; `paths` is ignored. `generate` writes `.github/workflows/git-cicd-manual.yml`, named `Manual`, with a `workflow_dispatch` and the `job` input, write permissions as on `merge`. An unknown job, a job with `"manual": false` or a branch that does not match fails the run with the reason in the report, never silently. The verdict is the same commit status on the commit the run is for.

- Declared inputs for manual runs
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd` (validate, run-job, generate), `templates/config.schema`, `templates/workflows/manual.yml`, `tests/`, `README.md`
  - shape: A job may declare the inputs a manual run of it takes (name, whether required, a default, and for a choice the allowed values). `validate` refuses a malformed declaration naming the job and the reason. A manual run passes the values to the job's steps only as environment variables with a documented naming rule; a value never becomes part of a command line and never appears as `${{ }}` inside a `run:` block. An undeclared input, a missing required one or a value outside a choice fails the run with the reason. The design must fit a workflow whose text does not vary with the config's jobs (the generated file stays fixed text) and must be able to carry what the three workflows above take today: `bump_type` (patch, minor, major), `subdirectory`, `changelog_description`; `vendor`, `version`, `private`; and git-vendored's `repo`, `version` for validate. Triggers other than manual give a step the declared defaults.

- The `cron` trigger executes
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd`, `templates/workflows/cron.yml` (new), `install.sh`, `tests/`, `README.md`
  - shape: `generate` writes `.github/workflows/git-cicd-cron.yml`, named `Cron`, whose schedule block has one entry per distinct cron expression among the config's jobs with `cron` in `on` and is the only part of any generated file that varies with the config; with no such job the file's handling is decided, documented and verified (no schedule that never has anything to run). At a scheduled time, the jobs whose expression is the one that fired run on each of their literal `branches`; `paths` does not apply. Write permissions as on `merge`. The verdict is the commit status on the head commit of the branch the run is for. The README says that GitHub runs schedules only from the default branch's copy of the file. `verify` fails when the schedule block and the config disagree.

- git-cicd's own release, vendor check and weekly update are git-cicd jobs
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `.vendored/configs/git-cicd.json`, `ci/` (new scripts), `.vendored/configs/git-semver.json` (`files` gains the new templates), generated `.github/workflows/git-cicd-*.yml`, `README.md`, `AGENTS.md`
  - shape: The repository's own config declares, beside `test`: (1) `release`, on `merge` for `main`, plus a manual run with the bump type, subdirectory and changelog text as declared inputs; its step is a script under `ci/` that calls `.vendored/pkg/git-semver/release` and decides between `bump` and `publish` the way `version-bump.yml` does today (publish when the landed commit's message starts with `chore: bump version`; nothing for `chore: install`; otherwise bump), giving `release` the environment it reads (`GITHUB_EVENT_NAME`, `GITHUB_EVENT_BEFORE`, `INPUT_BUMP_TYPE`, `INPUT_SUBDIRECTORY`, `INPUT_CHANGELOG_DESCRIPTION`, `GH_TOKEN`); (2) a vendor check job on `open` for every branch whose step runs `.vendored/check`; (3) an update job on `cron` `0 9 * * 1` for `main`, plus a manual run with `vendor` (default `all`), `version` (default `latest`) and `private` as declared inputs, whose step runs `.vendored/install <vendor> --version <version> --pr --deps=install` from a script under `ci/`. All four generated workflows are committed and `verify` passes. `README.md` ("Not built yet", the trigger table, "Developing git-cicd") and `AGENTS.md` say what is true. The sessions do **not** add, change or delete `version-bump.yml`, `check-vendor.yml` or `install-vendored.yml`: they are vendor-protected, and the planning session removes them from the integration branch after this unit, before it reaches `main`. Until then both the old workflow and the new job exist on the integration branch only; nothing on `main` changes.

## Acceptance criteria

- `./git-cicd decide`, `run-job` and `report` run for `merge`, `cron` and a manual run; none answers "not built yet" for a built trigger. Local `check` is unchanged for `open`.
- `./git-cicd generate` writes four files; `git-cicd-open.yml` is byte-identical to before the unit; `./git-cicd verify` passes and fails on a hand edit or a stale schedule block in any of them.
- Runs of `merge` on one branch never overlap and are never cancelled; `open` is unchanged, including its permissions.
- Every run on every trigger ends with exactly one `Verdict / git-cicd:verdict` commit status on its commit; a run that dies leaves it pending or failed, never green.
- A declared input reaches a step only as an environment variable; the tests show a value with quotes, `$`, backticks and a newline arriving literally.
- The repository's config declares `test`, `release`, the vendor check and the update job; the pull request into `plan/git-dev-883c` shows the vendor check row from git-cicd and a passing verdict.
- The test suite passes on the Python floor (`>=3.11`); `./git-cicd check` passes.
- `python3 .vendored/check --base origin/plan/git-dev-883c` reports nothing.

## Out of scope

- Deleting `version-bump.yml`, `check-vendor.yml`, `install-vendored.yml` (vendor-protected; done by the planning session).
- Any change in git-semver or git-vendored (units 2 to 5 of the plan), including a `release` that decides bump or publish itself.
- Secrets beyond `GITHUB_TOKEN` and `VENDOR_PAT`; an image or runtime per job.
- A trigger for "something outside this repository changed"; anything about how versions move.
- How an install pull request carries workflow files.
