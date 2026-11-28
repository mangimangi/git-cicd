# A config includes named jobs from a file

Unit 5 of plan `git-dev-0b7f` (record: `mangimangi/git-dev`, `.pearls/docs/epics/git-dev-0b7f.md`). Code references were read from `origin/main` (git-cicd 0.4.0) on 2026-11-28; re-check before relying on a line number.

## Problem

A check that several repositories should all run (an upgrade check owned by a workspace; a contract check across tools released separately) can be shared today only as scripts. Each repository vendors the scripts and then hand-writes the job in its own `.vendored/configs/git-cicd.json`: its triggers, branches, paths, secrets. The owner of the check owns half of it, and changing the job's shape takes a pull request in every repository that runs it.

Decided with the owner on 2026-11-28: a repository inherits a job by naming, in its own config, a file of job definitions and the jobs it takes from it. git-cicd reads that file from the working tree and does not know or care how it got there (vendored, committed by hand, a submodule). git-cicd learns nothing about vendoring. The repository stays in control: its include line names each job it takes and the most that job may ask for, so an update to the file cannot give a job a secret or a permission, or start a new job, without an edit to the repository's own config.

This is a git question only (a file at a path in the repository). Nothing platform-specific is added.

## What ships

- **`include` in the config, read and validated**
  - vehicle: issue **gcd-1dec.1**
  - target repo: git-cicd
  - affected surface: `git-cicd` (`load_config` line 793, `validate_config` line 646, `_validate_job` line 396, `_validate_permissions` line 573, `job_secrets` line 1138), `templates/config.schema`, `templates/config.json`, `tests/`
  - shape: the config accepts a top-level `include`: an array of objects, each with `path` (a file in the repository, relative to its root) and `jobs` (an object whose keys are the names of the jobs taken from that file and whose values state the most each may ask for: `secrets`, an array, default none; `permissions`, an object, default none). Example:

    ```json
    "include": [{
      "path": ".vendored/pkg/git-dev/jobs.json",
      "jobs": {"upgrade-check": {"secrets": ["CICD_READ_TOKEN"]}}
    }]
    ```

    The included file has the shape `{"jobs": {...}}`, each job written exactly as a job in the config is. Loading the config reads each included file from the working tree, takes the named jobs, validates each as a job, and merges them with the repository's own jobs into one set.
  - acceptance criteria: a job named on an include line is read from the file and is present in the loaded config; a job in the file that no include line names does not exist for this repository; each of the following is an invalid config, exits 2 as every other invalid config does, and names the config, the included file and the job involved: the file is missing, the file is not valid JSON or not of the stated shape, a named job is absent from the file, a named job has the same name as one of the repository's own jobs or as a job taken by another include, a job declares a secret not in its limit, a job declares a permission not in its limit or wider than it (write where the limit says read), a job's step or setup script does not exist in the repository; a `path` that leaves the repository (absolute, or with `..`) is refused; the schema documents `include`; git-cicd opens no network connection and runs no other tool to read the file.

- **Included jobs behave as the repository's own everywhere**
  - vehicle: issue **gcd-1dec.2** (blocked by gcd-1dec.1)
  - target repo: git-cicd
  - affected surface: `git-cicd` (`decide` line 1033, `run_job` line 1262, `permission_groups` line 618, `merge_branches` line 1402, `manual_form_fields` line 717, `job_scripts` line 865, the `generate` and `verify` commands), `tests/`
  - shape: after loading, nothing downstream distinguishes an included job from the repository's own: `decide`, `run`, `report`, `generate` and `verify` work on the merged set. A change to an included file affects the jobs taken from it the way a change to the config affects every job today (the job is needed). `verify` fails when the workflows no longer match the merged set, for example after an update changed an included job's triggers or secrets, and names the command to run.
  - acceptance criteria: with an included `open` job, a pull request that the job's `branches` and `paths` match needs it and the verdict counts it; an included job's declared secrets and permissions reach the generated workflows exactly as a repository job's do; an included `merge` job's branches appear in the Merge workflow's branches; an included manual job appears in the Manual form under its row name; changing the included file's content for a taken job makes `verify` fail until `generate` is run, with the existing message; a config with no `include` generates byte-identical workflows to the current release for every fixture in the tests; a local `git-cicd run <job>` works for an included job (refined: there is no `run` command; `run-job` and `check --job <name>`).

- **Documentation**
  - vehicle: issue **gcd-1dec.3** (blocked by gcd-1dec.1 and gcd-1dec.2; also carries the version bump)
  - target repo: git-cicd
  - affected surface: `README.md`, `AGENTS.md`, `CHANGELOG.md`
  - shape: the README gains a section on inheriting a job: what the include line is, that the file is read from the repository and git-cicd does not fetch it, that the include line is the limit on what an inherited job may ask for and widening it is an edit to the repository's own config, and that an update which changes an included job needs `generate` run in the same pull request (a repository's own update script can do it; `verify` says so when it was not).
  - acceptance criteria: the section exists with the example above; it names no vendoring tool as required; the changelog entry states the new key in plain words; the version is raised in the pull request.

## Acceptance criteria

- A repository can take a job defined in a file it did not write by adding one include line, and that job runs, reports and is generated exactly like its own.
- An included file cannot start a job, or give a job a secret or permission, that the repository's config does not name.
- Every failure is an invalid config with the files and the job named.
- A config without `include` is unaffected, byte for byte.
- Line coverage stays at 99% or more per file and in total.

## Out of scope

- Fetching an included file from anywhere; knowing about git-vendored's layout or manifests.
- Including anything but jobs (no shared top-level settings such as `manual_role`).
- Running `generate` automatically after an install (the repository's update script does that; it is part of the adoption units).
- Moving the runner-specific parts of git-cicd behind one named place (an idea in git-dev, not in this plan).

## Issues

| Issue | Scope |
|---|---|
| gcd-1dec.1 | `include` key: parse, validate (limits, shape, paths, collisions), read files from the working tree, merge into `config["jobs"]`; schema entry; `tests/test_config.py` |
| gcd-1dec.2 | Included file paths join `decide`'s forcing set; tests that decide, run-job/check, permission groups, Merge branches, Manual form, generate and verify treat included jobs as own; no-`include` configs byte-identical |
| gcd-1dec.3 | README section (with the example), key table and Files row; AGENTS.md if it lists config keys; patch bump to 0.4.1 with changelog entry |

## Refinement decisions

- Three issues, as the doc lists them, chained: gcd-1dec.2 and gcd-1dec.3 are blocked by gcd-1dec.1, and gcd-1dec.3 is also blocked by gcd-1dec.2 (gcd-1dec.1, .2, .3). Reason: downstream behaviour needs the merged set, and the docs describe the shipped behaviour.
- Merge order is own jobs first, then included jobs in include-line order and in the order of each line's `jobs` keys (gcd-1dec.1). Reason: generated files and reports follow `config["jobs"]` order, so an update to the file must not reorder anything.
- The included file allows only the top-level key `jobs` (gcd-1dec.1). Reason: the doc states the shape `{"jobs": {...}}`, and including anything but jobs is out of scope.
- Errors are prefixed `<config relpath>: include <path>: job <name>:` (gcd-1dec.1). Reason: every failure must name the config, the file and the job.
- An include line with an empty `jobs` object is refused (gcd-1dec.1). Reason: it takes nothing and is a mistake.
- `templates/config.json` is not changed, although the doc lists it as affected (gcd-1dec.1). Reason: an absent `include` is the default, the schema documents the key, and installs stay identical.
- Only the absolute and `..` checks of `_check_file` apply to `path`, not the executable check (gcd-1dec.1). Reason: an included file is data, not a script.
- A change to an included file forces every job its trigger and branches allow, not only the jobs taken from it (gcd-1dec.2). Reason: it uses the forcing set that config and script changes already use, which is never less safe and keeps `decide` simple.
- The doc's `git-cicd run <job>` is read as `run-job` / `check --job` (gcd-1dec.2). Reason: no `run` command exists, so that reference was stale.
- The bump is a patch (0.4.1), done once in gcd-1dec.3 (gcd-1dec.3). Reason: AGENTS.md reserves minor and major for breaking changes, nothing breaks, and `version-check` only runs on the pull request into `main`.
- The README section goes under `## The config`, between `### Declared inputs` and `### Patterns` (gcd-1dec.3). Reason: it sits next to the other job-declaration sections.
