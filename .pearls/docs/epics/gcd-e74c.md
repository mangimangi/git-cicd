# git-cicd reads a config, decides, runs and reports on `open`

> Unit 1 of plan `mdci-dev-6692` (the plan's record: `.pearls/docs/epics/mdci-dev-6692.md` in `mangimangi/medici-dev`). Agreed with the owner on 2026-11-27.
> This repository holds only `README.md`, `LICENSE` and the medici scaffold (`medici.yaml`, `pearls.yaml`, `madreperla.yaml`, `AGENTS.md`). Everything else is built by this epic.
> The epic delivers into `plan/mdci-dev-6692`. Only the owner merges that into `main`.

## Problem

Nothing sits between a repository's checks and the platform that runs them. Each repository in the toolchain (pearls, madreperla, medici) hand-writes GitHub workflows that each decide where and when to run. The same check differs across repositories; a pull request into a plan's integration branch (`plan/<plan-id>`) in medici runs only the vendor-file check, so "checks pass" there says almost nothing, and units merge there unattended on it; the same suite runs more than once per pull request; and no check can be run the same way in a session container or on a person's machine.

git-cicd closes this by defining an **interface**, not checks. The owner: "the repo defines the checks via the interface ... git-cicd shouldn't have any clue what the checks are tbh and shouldn't need access". A repository declares jobs (a setup script and ordered steps, each a plain script it owns) in a config file; git-cicd decides from a change which jobs are needed, runs them, and reports every decision, so that "nothing ran" is never read as "passed".

It is delivered the way git-semver is: vendored into a repository by git-vendored (`install.sh` at the repository root, code under `.vendored/pkg/git-cicd/`, config at `.vendored/configs/git-cicd.json`, a schema at `templates/config.schema`), versioned by git-semver, Python 3 and git with no other dependency. Read both before building: `mangimangi/git-semver` (`install.sh`, `git-semver`, `release`, `templates/`, `README.md`) and `mangimangi/git-vendored` (`README.md` "Vendor Contract", `docs/vendor-install-dir-guide.md`, `docs/adoption.md`, `templates/check`).

This epic builds the first slice: the whole interface is what a config is validated against, and the `open` moment and local runs execute. The `merge` and `cron` moments and manual runs are accepted in a config and reported plainly as not built yet; they are never silently ignored.

**If the interface below cannot be built as written, stop and say so (`madp stop "<question>"`); do not reinterpret it.** The owner locked it item by item: "that's the whole game...don't make assumptions". Names marked *(name open)* are for this epic to choose and record under `## Refinement decisions`; nothing else is open.

## The interface (locked with the owner; build against it as written)

This is what was locked. Unit 1 builds against it; a session that finds it cannot be built as written stops and asks, it does not reinterpret. Items marked *(session)* were proposed by the planning session and accepted by the owner as part of "it all looks good to me"; every other item is the owner's own decision. Field and variable names are as written here unless marked *(name open)*.

### Files

- Config: `.vendored/configs/git-cicd.json`, following the git-vendored precedent (`.vendored/configs/<vendor>.json`, with the `_vendor` registry key ignored by the tool).
- Workflow: one generated file under `.github/workflows/` *(name open; the session's working name is `git-cicd.yml`)*. Everything in it is fixed text except the cron block.
- Scripts: wherever the repository keeps them. git-cicd installs none.
- Code: `.vendored/pkg/git-cicd/`, installed by git-cicd's `install.sh` through git-vendored (`VENDOR_INSTALL_DIR`, `VENDOR_MANIFEST`, `templates/config.schema`), versioned by git-semver.

### A job declares

- `on`: any combination of `open`, `merge`, `cron`. A job may list several. A job with none is manual-only.
- `branches`: **required on every job**. Patterns such as `main`, `plan/**`, `**`. A job without `branches` is a config error. For `cron`, the branches are literal names, not patterns *(session)*.
- `paths`: the files that affect the job.
- `setup`: the job's own setup script. Optional.
- `steps`: ordered. Each step is a file in the repository plus fixed arguments, run directly, without a shell.
- `cron`: the expression, when `on` includes `cron`.
- `manual`: on unless set to `false`.
- A job may be marked non-blocking *(field name open)*: its failure is reported and does not fail the verdict.

There is no ordering between jobs. If order matters, it is steps in one job. Steps share a machine, run in order and stop at the first failure.

The repository also declares a list of paths that need nothing (documents, tracker records) *(field name open)*, and may change the parallel limit from its default of three *(session)*.

The strawman shown to the owner, names still as above:

```json
"jobs": {
  "test":    {"on": ["open"],  "branches": ["**"],   "paths": ["medici/**", "tests/**"], "setup": "ci/setup.sh", "steps": ["ci/test.sh", "ci/coverage.sh"]},
  "release": {"on": ["merge"], "branches": ["main"], "steps": ["ci/bump.sh", "ci/publish.sh"]}
}
```

### When a job runs

- `open`: a pull request is opened or updated, its base matches `branches`, and the change affects the job.
- `merge`: a change lands on a branch matching `branches` and affects the job.
- `cron`: at its expression, on its branches, always. `paths` do not apply.
- Manual: by name, on a branch matching `branches`, always. `branches` still binds, because the platform lets whoever starts a manual run pick any branch; only `paths` is ignored.
- A change affects **every** job when it touches the git-cicd config or any script a job names; when a changed file is neither in any job's `paths` nor in the "needs nothing" list; or when the diff cannot be computed *(session)*. So "not needed" can only happen on purpose. medici-dev's `.github/scripts/tests-needed.sh` already works this way.

### What a script is given

- The repository at the commit, as the working directory.
- Environment variables, prefix `CICD_` *(session)*: the moment, the job name, the target branch, the source branch, the base and head commits, and the path of a file listing the changed files. The source branch is needed by `.vendored/check`, which reads `GITHUB_HEAD_REF` today (git-vendored `templates/check`, lines 129-131) to let install branches through.
- `GITHUB_TOKEN` and `VENDOR_PAT`, passed through and never used by git-cicd. This is the precedent: git-vendored's `templates/github/workflows/install-vendored.yml` names `github.token` and `secrets.VENDOR_PAT` and hands them to its script as environment variables.
- Exit 0 passes. Anything else fails the job and stops its remaining steps.
- Setup runs first, on the same machine. What it installs on disk is its only channel to the steps; there is no variable passing *(session)*.

### No accidental injection

- A step is a file plus fixed arguments, never a shell string; nothing is assembled into a command line.
- Facts about the change (branch names, commits, the changed files) reach a script only as environment variables or a file. The generated workflow follows the same rule. (git-vendored's `install-vendored.yml` does not today: it writes `${{ inputs.vendor }}` straight into its script.)
- A change to the config or to a job's scripts makes every job run, and the report says so.

### Where it runs

- GitHub Actions is the first platform. One runner per job, three at once by default.
- Token permissions go by moment: read-only on `open`; write on `merge`, `cron` and manual.
- `open` runs are superseded by a newer push to the same pull request. `merge` runs on one branch go one at a time and are never cancelled.
- Locally and in a session: the same command, jobs one after another. Setup runs only when asked, because there it installs things for real.

### The report

- One line per job for the moment: passed, failed (naming the step), could not run (setup failed), or not needed (with the reason).
- The time each job and step took, so cost is visible in every pull request.
- One always-present check with a fixed name *(name open)*. It is green only when no blocking job failed or could not run, and the workflow matches the config. A change that needs nothing shows that check green, with the explanation in its text (for example "0 of 3 jobs needed"). The owner accepted green with the explanation over a separate "neutral" state.

### The generated workflow

- Generated from the config. Only the cron block varies; jobs are decided when the workflow runs, not written into the file.
- The platform's own token cannot push workflow files, so CI verifies and does not regenerate: whoever changes the config runs the generate command and commits the workflow in the same pull request. CI regenerates, compares the whole file, and fails with the command to run when they differ. That catches a stale file and any hand edit outside the cron block.
- The verification lives in git-cicd. git-vendored's check knows a file as frozen or as free to edit; the workflow is listed as editable there. If a second vendored tool generates files, that is when git-vendored gets a general "ask the vendor to verify its generated files" feature.
- A git-cicd upgrade regenerates the file in the install pull request. (git-semver's `install.sh` installs `version-bump.yml` on first install only, so a change to that workflow never reaches a repository that already has it.)
- GitHub runs schedules only from the default branch's copy of the file.

### Room reserved, not built

- Declared inputs for manual runs. Five of today's workflows take values when run by hand (version bump, both image publishes, vendor install, vendor validate); they cannot fully move until this is built. The owner: "leave them til needed".
- Secrets beyond `GITHUB_TOKEN` and `VENDOR_PAT` (a PyPI token, cloud credentials for `tf apply`).
- An image or runtime per job.

### Python versions

No version is written in any workflow or config. Blocking checks run on the floor the tool declares (`requires-python` in `pyproject.toml`: `>=3.11` pearls, `>=3.10` madreperla and medici); setup reads it and installs it. A non-blocking `cron` job runs the same steps on the newest Python. Sessions run the same setup script. Python 3.10 reached end of life in October 2026; watching for floors that are too low is the shared tool of `.pearls/docs/ideas/shared-eol-and-known-issue-watch.md`, not part of this plan.

### Checked against every existing workflow (2026-11-27)

32 workflow files in eight repositories (medici-fixture and git-cicd have none), 16 distinct kinds. What fits as the interface stands: unit tests, coverage and type check; the vendor file check; the cross-tool contract (its script clones the other repositories with `VENDOR_PAT`); madreperla's tests on pull request and on push; medici-dev's cross-tool tests, pinned and latest (two jobs, one script, a different fixed argument); version bump and release (a `merge` job whose step calls git-semver's `release`); the base image publish; the weekly vendor update; dogfood (a later step in the release job).

Consequences that are not gaps: no marketplace actions, so checking out other repositories, Docker login and multi-platform build setup become commands in the repository's scripts; no value passing between steps, so bats is installed where the path already looks (medici's `test.yml` uses `$GITHUB_PATH` today); the pin bump in medici-dev after a tool release has no moment ("another repository released") and would be a step that starts a manual job in medici-dev, or a `cron` job there; the "Rebuilt for" line lives in the environment's settings and cannot be owned by git-cicd. medici's `version-bump.yml` differs from the template in passing `secrets.VENDOR_PAT` as `GH_TOKEN`.

## What ships

- The config is loaded and validated against the interface
  - vehicle: type: issue
  - source repo: git-cicd
  - affected surface: the tool script (new, at the repository root, installed to `.vendored/pkg/git-cicd/`); `templates/config.schema`; `templates/` default config; tests
  - target repo: git-cicd
  - shape: Read `.vendored/configs/git-cicd.json`, ignoring the `_vendor` key. Accept every field of "A job declares", the "needs nothing" list and the parallel limit. Refuse, with the job and the reason: a job without `branches`; a step that is not a file plus fixed arguments; an unknown moment in `on`; `on` containing `cron` without a `cron` expression; a `cron` job whose branches are patterns; an unknown field. A job naming `merge` or `cron`, and `manual`, validate; the tool states that those moments are not built yet when asked to run them.

- The tool decides which jobs a change needs on `open`
  - vehicle: type: issue
  - source repo: git-cicd
  - affected surface: the tool script; tests
  - target repo: git-cicd
  - shape: Given the target branch, the source branch, a base commit and a head commit, list the changed files (what the branch changed since it left the base) and decide each `open` job as needed or not needed, with the reason, exactly as "When a job runs" says: base matches `branches` and a changed file matches `paths`; every job when the config or any script a job names changed; every job when a changed file is in no job's `paths` and not in the "needs nothing" list; every job when the diff cannot be computed. Patterns support `*`, `**` and `?`.

- The tool runs a job: setup, then steps, with the change's facts as environment variables
  - vehicle: type: issue
  - source repo: git-cicd
  - affected surface: the tool script; tests
  - target repo: git-cicd
  - shape: Run the job's setup when asked, then each step in order, each as a file plus fixed arguments executed directly without a shell, from the repository root. Stop at the first failing step. Give every script the `CICD_`-prefixed variables of "What a script is given" (moment, job name, target branch, source branch, base commit, head commit, path of the changed-files file) and pass `GITHUB_TOKEN` and `VENDOR_PAT` through unchanged; git-cicd itself never reads them. A setup that fails is "could not run", distinct from a failed step. Record the time each setup and step took.

- The report: one line per job, the times, and one verdict
  - vehicle: type: issue
  - source repo: git-cicd
  - affected surface: the tool script; tests
  - target repo: git-cicd
  - shape: For the moment, one line per declared job: passed, failed (naming the step), could not run, or not needed (with the reason), with the time of each job and step. One verdict: failed when a blocking job failed or could not run, or when the workflow does not match the config; otherwise passed, and when no job was needed its text says so and why (for example "0 of 3 jobs needed"). A failing non-blocking job is reported and does not fail the verdict. The report is readable in a terminal and is written to the platform's summary when one exists.

- The same jobs run locally and in a session with one command
  - vehicle: type: issue
  - source repo: git-cicd
  - affected surface: the tool script (its command line); `README.md`; tests
  - target repo: git-cicd
  - shape: One command, given a base and a head (with sensible defaults for a branch against its target), decides, runs the needed jobs one after another and prints the report, exiting non-zero on a failed verdict. Setup runs only when asked. A single job can be named. This is what a pipeline session and a person use; it must not need GitHub.

- The GitHub Actions workflow is generated from the config and verified
  - vehicle: type: issue
  - source repo: git-cicd
  - affected surface: the tool script (generate and verify commands); the workflow template under `templates/`; tests
  - target repo: git-cicd
  - shape: Generate one workflow file whose only varying part is the cron block. It turns a pull request event into moment, target branch, source branch, base and head and calls the tool; jobs are decided when it runs, each needed job on its own runner, at most three at once by default (the config can change the number); one always-present check with a fixed name carries the verdict. Token permissions are read-only on `open`. A newer push to the same pull request supersedes a running `open` run. Every fact about the change reaches the tool as an environment variable, never spliced into a command. The verify step regenerates, compares the whole file, and fails naming the generate command when they differ. Two configs that differ only in jobs that are not `cron` generate the same file. `merge`, `cron` and manual triggers are not executed in this epic; where the generated file must already carry something for them to keep "only the cron block varies" true later, say so under `## Refinement decisions`.

- git-cicd installs through git-vendored
  - vehicle: type: issue
  - source repo: git-cicd
  - affected surface: `install.sh`; `templates/config.schema`; the default config template; tests
  - target repo: git-cicd
  - shape: `install.sh` follows the vendor contract as git-semver's does: `VENDOR_REF` (or `$1`), `VENDOR_REPO`, `VENDOR_INSTALL_DIR`, `VENDOR_MANIFEST`, `GH_TOKEN` when set. It always updates the code under `VENDOR_INSTALL_DIR`; creates `.vendored/configs/git-cicd.json` only when missing, with a `_vendor` block that lists the config and the generated workflow as editable; installs the schema to `.vendored/manifests/git-cicd.schema`; generates the workflow; writes the manifest. `python3 .vendored/install mangimangi/git-cicd` in a scratch repository that has git-vendored works.

- git-cicd uses itself, and can release
  - vehicle: type: issue
  - source repo: git-cicd
  - affected surface: `.vendored/` (git-vendored and git-semver installed, `configs/git-semver.json`, `configs/git-cicd.json`); `VERSION`; `.github/workflows/`; `README.md`; `AGENTS.md`; `pyproject.toml` for the tests
  - target repo: git-cicd
  - shape: The repository installs git-vendored and git-semver as the other git- tools do, so a merge to `main` produces a version tag and a release. Its own tests run as a git-cicd job declared in its own config, through the generated workflow, on pull requests into every branch (`"branches": ["**"]`). `README.md` describes the tool and the interface for a repository adopting it; `AGENTS.md` says how to run the checks with the one local command.

## Acceptance criteria

- A config that breaks the interface is refused with the reason: a job without `branches`, a step that is not a file, an unknown moment, `on` with `cron` and no expression.
- On a pull request into a branch matching a job's `branches`, a change under the job's `paths` runs the job: setup, then each step in order, stopping at the first failing step.
- A change whose every file is in the "needs nothing" list runs no job; the verdict check is present and green, and its text says how many jobs were needed and why none were.
- A change with a file in no job's `paths` and not in the "needs nothing" list runs every `open` job, and the report says why.
- A change to the config or to any script a job names runs every `open` job, and the report says why.
- A pull request whose base matches no job's `branches` reports that, and the verdict check is still present.
- A failing setup reports "could not run", distinct from a failing step, and fails the verdict.
- A failing non-blocking job is reported and does not fail the verdict.
- The report has one line per job with its state and the time each job and step took.
- Each job runs on its own runner, at most three at once by default.
- A step receives the moment, job name, target branch, source branch, base and head commits and the changed-files file as environment variables, and `GITHUB_TOKEN` and `VENDOR_PAT` unchanged; a test shows a branch name containing shell metacharacters reaches a step unaltered and runs nothing.
- The generate command writes the workflow; the verify step fails when the file differs from what the config generates, naming the command to run; two configs that differ only in jobs that are not `cron` generate the same file.
- The same jobs run locally with one command, given a base and a head, one after another; setup runs only when asked.
- `python3 .vendored/install mangimangi/git-cicd` in a scratch repository installs it under `.vendored/pkg/git-cicd/`, creates the config only if missing, writes a manifest, and installs the schema.
- git-cicd's own tests run as a git-cicd job on this epic's own pull request into `plan/mdci-dev-6692`, and the verdict check is seen there before the work is called done.
- The repository is set up so that a first release (tag and `VERSION`) is produced when the owner merges the integration branch into `main`.
- Python 3 and git only; no other runtime dependency.

## Out of scope

- Executing the `merge` and `cron` moments and manual runs. They validate in a config and are reported as not built.
- Declared inputs for manual runs; secrets beyond `GITHUB_TOKEN` and `VENDOR_PAT`; an image or runtime per job.
- Any check of its own: git-cicd ships no test, build or publish logic for other repositories.
- Any change to git-vendored or git-semver. If one turns out to be needed, stop and say so.
- Installing git-cicd into medici, madreperla, pearls or any other repository (unit 2 of the plan does medici).
- Fixing the generated `AGENTS.md` scaffold's errors beyond rewriting `AGENTS.md` for this repository as the last entry asks.
