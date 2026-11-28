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
  - issue: gcd-bbdd.1
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd` (decide, run-job, report, generate, verify), `templates/workflows/merge.yml` (new), `install.sh`, `tests/`, `README.md`
  - shape: `decide --trigger merge`, `run-job --trigger merge` and `report` work for a change that landed on a branch: the needed jobs are those with `merge` in `on`, whose `branches` match the branch, and that the change affects (the same `paths` and `needs_nothing` rules as `open`; the changed files are what the push brought). `generate` writes `.github/workflows/git-cicd-merge.yml`, named `Merge`, fixed text: its GitHub event is a push to any branch (branches are decided by the tool); `contents: write` and `pull-requests: write` for the job that runs the config's scripts; runs on one branch queue and are never cancelled; full history and tags are available to a step (git-semver's release needs them). The verdict is the commit status `Verdict / git-cicd:verdict` on the landed commit, pending from the first step of decide and final from the last step of report. Scripts get `CICD_TRIGGER=merge` and the other `CICD_` variables with documented meanings on `merge` (target is the branch landed on; base is the commit before the push). `verify` covers the new file.

- Manual runs execute
  - issue: gcd-bbdd.2
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd`, `templates/workflows/manual.yml` (new), `install.sh`, `tests/`, `README.md`
  - shape: A manual run of one named job executes: allowed unless the job says `"manual": false`; the job's `branches` still bind against the branch the run is started on; `paths` is ignored. `generate` writes `.github/workflows/git-cicd-manual.yml`, named `Manual`, with a `workflow_dispatch` and the `job` input, write permissions as on `merge`. An unknown job, a job with `"manual": false` or a branch that does not match fails the run with the reason in the report, never silently. The verdict is the same commit status on the commit the run is for.

- Declared inputs for manual runs
  - issue: gcd-bbdd.3
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd` (validate, run-job, generate), `templates/config.schema`, `templates/workflows/manual.yml`, `tests/`, `README.md`
  - shape: A job may declare the inputs a manual run of it takes (name, whether required, a default, and for a choice the allowed values). `validate` refuses a malformed declaration naming the job and the reason. A manual run passes the values to the job's steps only as environment variables with a documented naming rule; a value never becomes part of a command line and never appears as `${{ }}` inside a `run:` block. An undeclared input, a missing required one or a value outside a choice fails the run with the reason. The design must fit a workflow whose text does not vary with the config's jobs (the generated file stays fixed text) and must be able to carry what the three workflows above take today: `bump_type` (patch, minor, major), `subdirectory`, `changelog_description`; `vendor`, `version`, `private`; and git-vendored's `repo`, `version` for validate. Triggers other than manual give a step the declared defaults.

- The `cron` trigger executes
  - issue: gcd-bbdd.4
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd`, `templates/workflows/cron.yml` (new), `install.sh`, `tests/`, `README.md`
  - shape: `generate` writes `.github/workflows/git-cicd-cron.yml`, named `Cron`, whose schedule block has one entry per distinct cron expression among the config's jobs with `cron` in `on` and is the only part of any generated file that varies with the config; with no such job the file's handling is decided, documented and verified (no schedule that never has anything to run). At a scheduled time, the jobs whose expression is the one that fired run on each of their literal `branches`; `paths` does not apply. Write permissions as on `merge`. The verdict is the commit status on the head commit of the branch the run is for. The README says that GitHub runs schedules only from the default branch's copy of the file. `verify` fails when the schedule block and the config disagree.

- git-cicd's own release, vendor check and weekly update are git-cicd jobs
  - issue: gcd-bbdd.5
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

## Issues

Order: gcd-bbdd.1 first; gcd-bbdd.2 and gcd-bbdd.4 after it; gcd-bbdd.3 after gcd-bbdd.2; gcd-bbdd.5 last (blocked by all four).

- gcd-bbdd.1 — merge trigger: `decide`/`run-job`/`report --trigger merge`, `templates/workflows/merge.yml`, the run queue, the non-open verdict rule, install.sh, tests, README/AGENTS.md.
- gcd-bbdd.2 — manual runs: `decide --trigger manual --job`, refusals reported, `templates/workflows/manual.yml` with the `job` input, tests, docs.
- gcd-bbdd.3 — declared inputs: the job field `inputs`, validation, `CICD_INPUT_<NAME>`, the fixed `inputs` dispatch input carrying JSON, defaults on other triggers, schema, tests, docs.
- gcd-bbdd.4 — cron trigger: `templates/workflows/cron.yml` and its schedule block, `decide --trigger cron --cron`, per-branch heads and verdicts, the no-cron-job handling, tests, docs.
- gcd-bbdd.5 — this repository's own `release`, `vendor-check` and `update-vendored` jobs and their `ci/` scripts, git-semver.json `files`, the four committed workflows, README/AGENTS.md.

## Refinement decisions

- **A branch-creating push (all-zero before sha) or an unresolvable base counts as "cannot compute the diff", so every matching merge job is needed** (gcd-bbdd.1). Reason: "not needed" must only happen on purpose, which is the existing forcing rule.
- **On merge, `CICD_SOURCE_BRANCH` equals the branch landed on** (gcd-bbdd.1). Reason: a push has no separate source, and the variable is never empty.
- **Merge skips a push that deletes a branch** (gcd-bbdd.1). Reason: there is no commit to run on or to put a status on.
- **merge.yml has no `concurrency` key; decide waits until earlier Merge/Manual runs on the same branch finish** (gcd-bbdd.1, gcd-bbdd.2). Reason: a GitHub concurrency group with `cancel-in-progress: false` still cancels a pending run when a newer one joins, which would break "never cancelled". Manual runs share the queue, as version-bump.yml's push-to-main group does today.
- **A non-open run posts `Verdict / git-cicd:verdict` only when no open pull request has the commit as its head; otherwise its Report check run carries the verdict** (gcd-bbdd.1, gcd-bbdd.2, gcd-bbdd.4). Reason: Open and Merge runs on the same commit would overwrite each other's status, and a Merge run that needs nothing could turn a failed Open verdict green. The owner's rule makes the status the verdict "when there is no pull request".
- **templates/workflows/open.yml is not touched, though its header says the other triggers are "not built yet"** (gcd-bbdd.1). Reason: the acceptance criterion requires git-cicd-open.yml to stay byte-identical.
- **`decide --trigger manual --job NAME`; a refusal (unknown job, `"manual": false`, branch mismatch) is recorded in the decision record, decide exits 0, and report gives FAILED with the reason** (gcd-bbdd.2). Reason: the reason must reach the report, never silently.
- **On manual, target = source = the branch the run was started on, base = head = github.sha, and the changed files are empty** (gcd-bbdd.2). Reason: there is no change, and paths are ignored.
- **The `inputs` field: name `^[a-z][a-z0-9_]*$`, with `description`, `required`, `default` and `choices`; every value is a string (booleans are a true/false choice)** (gcd-bbdd.3). Reason: environment variables are strings.
- **A required input may not have a default; bump_type is declared not required with default patch** (gcd-bbdd.3). Reason: a default would make `required` meaningless, and not-required-with-default carries today's behaviour.
- **Env naming: `CICD_INPUT_<NAME upper-cased>`, always set (value, else default, else empty); undeclared inherited `CICD_INPUT_*` are removed** (gcd-bbdd.3). Reason: a predictable, documented channel and nothing stray.
- **Manual values travel in one fixed second dispatch input `inputs` (a JSON object of strings), passed to the tool only as the env entry `CICD_MANUAL_INPUTS` and stripped from the scripts' environment** (gcd-bbdd.3). Reason: the generated file cannot list per-job inputs, GitHub caps the number of dispatch inputs, and JSON carries quotes and newlines exactly.
- **With no cron job, no git-cicd-cron.yml is generated; generate removes a stale one, verify fails while it exists, and the install manifest lists only the files generate wrote** (gcd-bbdd.4). Reason: GitHub needs an event under `on:`, and the doc forbids a schedule with nothing to run.
- **Cron: decide takes `--cron` (from `github.event.schedule` through env), resolves each literal branch's head once from `origin/<branch>`, fails a missing branch with its reason, uses a cron-only matrix output, and gives one verdict per branch head** (gcd-bbdd.4). Reason: every job on a branch runs on one commit, nothing fails silently, and the open outputs and file stay unchanged.
- **On cron, target = source = the branch, base = head = its head commit, and the changed files are empty** (gcd-bbdd.4). Reason: a schedule has no change.
- **Cron runs do not join the Merge/Manual queue** (gcd-bbdd.4). Reason: schedule runs carry the default branch's ref, and the only planned cron job opens pull requests.
- **`release` has no `paths`, so a needs_nothing-only push to main does not release** (gcd-bbdd.5). Reason: a bump commit still publishes, because VERSION is in no paths and not in needs_nothing.
- **ci/vendor-check.sh passes `--base "$CICD_BASE"` and sets GITHUB_HEAD_REF from CICD_SOURCE_BRANCH when unset** (gcd-bbdd.5). Reason: it works the same locally and in Actions, and install branches pass.
- **ci/update-vendored.sh sets GH_TOKEN to VENDOR_PAT, else GITHUB_TOKEN** (gcd-bbdd.5). Reason: like-for-like with install-vendored.yml.
- **Adding the new templates to git-semver.json `files` stays in gcd-bbdd.5, as the doc assigns it** (gcd-bbdd.5). Reason: follow the doc.
