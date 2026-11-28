# git-cicd: a manual run is started from a form that lists the jobs and their inputs

> Unit 15 of plan `git-dev-883c` (record: `mangimangi/git-dev`, `.pearls/docs/epics/git-dev-883c.md`; the friction is in `mangimangi/git-dev`, `.pearls/docs/headaches/manual-runs-of-a-git-cicd-job-are-awkward-to-start.md`). Added to the plan by the owner on 2026-11-28. Delivers into `plan/git-dev-883c`. Re-check every code reference against the code before using it.

## Problem

The owner, 2026-11-28, after starting a job by hand for the first time: "that ux for manual cicd jobs is not good lol".

The generated Manual workflow (`templates/workflows/manual.yml`, `workflow_dispatch` at lines 68-78) asks for two free-text fields: `job`, a job name typed from memory of `.vendored/configs/git-cicd.json`, and `inputs`, "the job's declared inputs as a JSON object of strings, for example {"bump_type": "minor"}". Nothing lists the jobs or their inputs, and a mistyped name or a malformed object is reported only after the run has started. The workflows these jobs replaced (`install-vendored.yml`, `version-bump.yml`) had one named field per input, with a description, a default and a dropdown for a choice.

It is like this because of a rule of the interface: every generated workflow is fixed text except the cron workflow's schedule block, so the Manual workflow "cannot list a job's inputs, since it does not vary with the config" (the template's own comment, lines 27-28).

## The decision (agreed; do not reopen)

The owner chose the first of three directions: the Manual workflow varies with the config, as the cron workflow's schedule block does. `job` becomes a choice among the jobs that allow a manual run, and their declared inputs become named fields with their descriptions, defaults and choices.

What stays:

- The rule changes only for the Manual workflow: the generated files are fixed text except the cron workflow's schedule block and the Manual workflow's form. `Open` and `Merge` do not change, and no existing row or status name changes.
- The injection rules: a value from the form reaches the tool and the scripts only as environment variables, never as part of a command line and never as `${{ }}` inside a `run:` block. Job names and input names that reach the generated file are validated identifiers; descriptions are data and must be written into the file so that they cannot break out of their place in it.
- Declared inputs still reach a step as `CICD_INPUT_<NAME>`; a run is still refused, with the reason in the report, for a job that does not allow manual runs, a branch that does not match, a missing required input or a value outside its choices.
- `generate` writes the file and `verify` fails when the file and the config disagree, naming the command to run; whoever changes a job's inputs or adds a job regenerates and commits in the same pull request.
- Coverage: the `test` job fails below 99%; every change comes with its tests, shell with bats.
- No vendor-protected file is added, changed or deleted. Run `python3 .vendored/check --base origin/plan/git-dev-883c` before finishing.

## What ships

- The Manual workflow's form is generated from the config
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd` (generate, verify, the manual decision and how inputs are read), `templates/workflows/manual.yml`, `templates/config.schema`, `tests/`
  - shape: `generate` writes `.github/workflows/git-cicd-manual.yml` with `job` as a choice listing, in config order, the jobs that allow a manual run, and one named field for each declared input of those jobs, carrying its description, its default and, for a choice, its allowed values as a dropdown. Inputs of different jobs share one form: an input declared by more than one job under the same name appears once, and `validate` refuses declarations of one name that cannot share a field (different choices or different defaults), naming the jobs and the input; a field's description says which jobs use it when it is not used by all. The platform's limit on the number of inputs of a manually started workflow is respected: `validate` refuses a config whose manual form would exceed it, with the count and the limit (look the current limit up in the platform's documentation; do not assume it). A run passes only the fields of the chosen job to it; a value given for a field the chosen job does not declare is ignored and said so in the report, not an error, since the form shows every job's fields. With no job that allows a manual run, what is generated is decided, documented and verified. `verify` covers the form like the schedule block.

- The form is safe and the old way of passing inputs has one clear fate
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `git-cicd`, `templates/workflows/manual.yml`, `tests/`
  - shape: Names written into the generated file are validated identifiers; descriptions, defaults and choice values are written so that quotes, colons, `#`, `$`, backticks, `${{` and newlines in them cannot change the file's structure or reach a shell, with tests that generate a file from hostile declarations and show it is still one well-formed workflow whose `run:` blocks contain no value from the config. The single free-text `inputs` JSON field is removed from the form; the tool's reading of manual inputs is changed to match and has one path, with tests. A value typed into a field still reaches a script literally, shown for quotes, `$`, backticks and a newline.

- git-cicd's own form, and the docs
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `.github/workflows/git-cicd-manual.yml` (regenerated), `README.md` ("The generated workflows", "The config", the manual-run sections, "Developing git-cicd"), `AGENTS.md`, the comments at the top of the templates
  - shape: This repository's Manual workflow is regenerated from its own config (`release` and `update-vendored` with their inputs) and committed. The README states the changed rule (which generated files vary with the config and how), shows the form an adopter gets, says that changing a job's inputs or adding a manual job means `generate` and a commit, and tells an adopter upgrading from a version with the two free-text fields what changes for them. `AGENTS.md` says how a job is started by hand here.

## Acceptance criteria

- For this repository's config, the generated form has a `job` dropdown with `release` and `update-vendored` and the named fields `bump_type` (a dropdown of `patch`, `minor`, `major`), `subdirectory`, `changelog_description`, `vendor`, `version` and `private`, each with its description and default.
- `./git-cicd verify` fails after a job's input is added or changed without regenerating, naming the command; and passes after `generate`.
- `validate` refuses two jobs declaring one input name incompatibly, and a config over the platform's input limit, each with a message naming what to change.
- The hostile-declaration tests pass; no `run:` block in any generated file contains a value taken from the config.
- A manual run started with fields set gives the chosen job its inputs as `CICD_INPUT_<NAME>`; shown by the tests for `decide` and `run-job` on the manual trigger.
- `git-cicd-open.yml`, `git-cicd-merge.yml` and `git-cicd-cron.yml` are byte-identical to before the unit.
- `./git-cicd check` passes with coverage at 99% or more; the pull request into `plan/git-dev-883c` has a passing `Verdict / git-cicd:verdict`.
- `python3 .vendored/check --base origin/plan/git-dev-883c` reports nothing.

## Out of scope

- One workflow per job; `key=value` input; any change to the `open`, `merge` or `cron` triggers.
- Changing how git-semver or git-vendored declare their jobs (they regenerate when they upgrade).
- Raising this repository's version or changing how it releases (unit 12).
