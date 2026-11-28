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

## Issues

- **gcd-8f83.1** — Generate the Manual workflow's form from the config: `job` dropdown of the manual jobs in config order, one field per distinct declared input (description, default, dropdown for choices), sharing by name with `validate` refusing incompatible declarations, the `job` reserved name, the platform input limit, no Manual workflow when no job is manual, `verify` covering the form, `templates/config.schema`. First "What ships" item.
- **gcd-8f83.2** (blocked by .1) — The form is safe and the old way of passing inputs has one fate: free-text `inputs` field and `CICD_MANUAL_INPUTS` removed, one reading path (`CICD_MANUAL_FORM: ${{ toJSON(inputs) }}`), only the chosen job's fields passed, others ignored and reported, `${{` refused, hostile-declaration tests, literal values reaching scripts. Second "What ships" item.
- **gcd-8f83.3** (blocked by .2) — git-cicd's own form regenerated (with `"manual": false` on `test` and `vendor-check`), `tests/test_own_jobs.py`, README sections, upgrade note, AGENTS.md. Third "What ships" item.

## Refinement decisions

- **Form fields are `required: false`; the tool enforces `required` for the chosen job** (gcd-8f83.1, gcd-8f83.2) — the form shows every job's fields, so a required field would force inputs of jobs not chosen; an empty value of a required input counts as missing.
- **Absent default and `""` are the same default when two jobs share an input** (gcd-8f83.1) — both give the script the empty string (`input_values`).
- **Differing descriptions of a shared input are allowed; the first job's is used** (gcd-8f83.1) — a description does not change the value a script gets; only different choices or defaults cannot share a field.
- **An input named `job` is refused on a job that allows manual runs** (gcd-8f83.1) — it would collide with the form's `job` field.
- **The platform limit is 25 `workflow_dispatch` inputs, `job` included (24 input fields)** (gcd-8f83.1) — GitHub changelog 2025-12-04 raised it from 10 to 25; the implementer re-checks the docs and cites the source in a code comment.
- **With no manual job, no Manual workflow is generated; `generate` removes a stale one and `verify` fails while it exists** (gcd-8f83.1) — a `choice` input needs at least one option and a workflow with nothing to run should not exist; mirrors the cron workflow.
- **Values are written with `json.dumps`, names bare** (gcd-8f83.1, gcd-8f83.2) — a JSON string is a valid YAML double-quoted scalar, as `schedule_block` already does for cron; names are validated identifiers.
- **One env variable `CICD_MANUAL_FORM: ${{ toJSON(inputs) }}` replaces `CICD_MANUAL_INPUTS`** (gcd-8f83.2) — keeps the step env blocks fixed text, gives one reading path, and keeps values in an env var only.
- **The reading of manual values (and the ignored-field report) is in gcd-8f83.2, not .1** (gcd-8f83.1, gcd-8f83.2) — .1 keeps the old free-text field and env lines so a run still works between the two issues; .2 switches the read path in one place.
- **An ignored field is reported only when its value differs from the field's form default** (gcd-8f83.2) — GitHub prefills defaults, so reporting every other job's field would report on every run.
- **`${{` is refused in descriptions, defaults and choices of manual jobs** (gcd-8f83.2) — GitHub evaluates `${{ }}` in workflow strings and YAML has no escape for it.
- **`test` and `vendor-check` get `"manual": false` in this repo's config** (gcd-8f83.3) — the acceptance criterion's dropdown is exactly `release` and `update-vendored`, and AGENTS.md has the owner start only those by hand.
- **The header comments of `open.yml`, `merge.yml`, `cron.yml` are not changed** (gcd-8f83.1, gcd-8f83.3) — those generated files must stay byte-identical; the README and the manual template carry the changed rule (headache filed).
- **Three issues, one per "What ships" item, chained by dependencies** (all) — each item touches the same Manual template and reading code in sequence.
