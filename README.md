# git-cicd

git platform hooks for managing cicd.

git-cicd defines an **interface between a repository's checks and the
platform that runs them**. It ships no checks. A repository declares *jobs* in
a config file, each job a setup script and ordered steps, every one a plain
script the repository owns. git-cicd decides from a change which jobs are
needed, runs them, and reports every decision, so that "nothing ran" is never
read as "passed".

It is one Python 3 file with no dependency beyond the standard library and the
git CLI, vendored by [git-vendored](https://github.com/mangimangi/git-vendored)
and versioned by [git-semver](https://github.com/mangimangi/git-semver).

What is built today: the whole interface is validated, and every trigger
executes: `open` (pull requests), `merge` (a change lands on a branch),
`cron` (a schedule fires), manual runs of one named job, and local runs. See
[Not built yet](#not-built-yet) for what remains.

## Files

| Path | Owner | What |
|---|---|---|
| `.vendored/configs/git-cicd.json` | the repository | the config: jobs, `needs_nothing`, `max_parallel` |
| `.github/workflows/git-cicd-<trigger>.yml` | generated | the GitHub Actions workflows, one per trigger (`git-cicd-open.yml`, `git-cicd-merge.yml`, `git-cicd-manual.yml` when a job allows manual runs, and `git-cicd-cron.yml` when a job has `cron` in `on`); generated, committed |
| your scripts (e.g. `ci/`) | the repository | setup and step scripts, wherever the repository keeps them; git-cicd installs none |
| `.vendored/pkg/git-cicd/` | git-cicd | the tool and its workflow template, installed by `install.sh` |

## The config

```json
{
  "jobs": {
    "test": {
      "on": ["open"],
      "branches": ["**"],
      "paths": ["src/**", "tests/**"],
      "setup": "ci/setup.sh",
      "steps": ["ci/test.sh", ["ci/coverage.sh", "--min", "80"]]
    },
    "release": {"on": ["merge"], "branches": ["main"], "steps": ["ci/bump.sh", "ci/publish.sh"]}
  },
  "needs_nothing": [".pearls/**", "*.md", "docs/**"],
  "max_parallel": 3
}
```

Top level:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `jobs` | object | required | job name → job. Names: letters, digits, `-`, `_` (they become runner and artifact names) |
| `needs_nothing` | array of patterns | `[]` | files that need no job: documents, tracker records |
| `max_parallel` | positive integer | `3` | how many job runners run at once |
| `_vendor` | anything | | git-vendored's registry key; ignored by git-cicd |

Any other key is refused, including `_comment_*` keys: comments belong here,
in the README.

### A job declares

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | non-empty single-line string | the job name in title case | a short human-readable display name (`"Unit Tests"`); it is data, shown in the job's row and the report, never part of a command |
| `on` | array of `open`, `merge`, `cron` | `[]` | the triggers the job runs at; several allowed, no duplicates; none means manual-only |
| `branches` | non-empty array of patterns | **required** | target branches the job runs for (`main`, `plan/**`, `**`). For a job with `cron` in `on`, literal branch names only (no `*`, `?`, `[`) |
| `paths` | array of patterns | none | the files that affect the job |
| `setup` | one repository path | none | the job's own setup script |
| `steps` | non-empty ordered array | **required** | each step is a file (`"ci/test.sh"`) or a file plus fixed arguments (`["ci/test.sh", "--fast"]`), run directly, never through a shell |
| `cron` | five-field cron expression | | required when `on` contains `cron`, refused otherwise |
| `manual` | boolean | `true` | the job can be run by hand: it is listed in the `Manual` workflow's `job` dropdown and its inputs are fields of that form |
| `blocking` | boolean | `true` | `false` makes the job non-blocking: its failure is reported and does not fail the verdict |
| `inputs` | object | `{}` | the inputs a manual run of the job takes, input name → declaration; see [Declared inputs](#declared-inputs) |

**Title case by convention and by default, never by rewriting.** A job
without `name` is shown under its job name with `-` and `_` as spaces and each
word capitalised: `unit-tests` shows as `Unit Tests`, `build_docs` as
`Build Docs`. A `name` you write is shown exactly as written; git-cicd never
changes its case (`"PyPI"`, `"mypy"`). Write names in title case
(`"Unit Tests"`, `"Release To PyPI"`) unless a word has its own spelling.

A `name` that is not a string, is empty (or only spaces), or holds a newline,
tab or other control character is refused naming the job and the reason.
Quotes, `$` and backticks are allowed and shown literally: the name reaches
the workflow only through the decide job's outputs, into a job's `name:`,
never a `run:` block.

A setup or step file must be a relative path to an **executable** regular file
in the repository, without `..` segments. A string step containing whitespace
is refused (it looks like a shell command line): use the array form.

There is no ordering between jobs. If order matters, it is steps in one job.
Steps share a machine, run in order and stop at the first failure.

`git-cicd validate` checks the config and prints every error, one per line,
naming the job and the reason (for example `job test: missing required field
branches`), and exits 2. Every other command refuses an invalid config the same
way.

### Declared inputs

A job may declare the inputs a manual run of it takes:

```json
"release": {
  "on": ["merge"], "branches": ["main"], "steps": ["ci/release.sh"],
  "inputs": {
    "bump_type": {"description": "Version bump type", "choices": ["patch", "minor", "major"], "default": "patch"},
    "changelog_description": {"description": "Changelog entry"},
    "repo": {"required": true}
  }
}
```

An input name is lowercase letters, digits and `_`, starting with a letter
(`^[a-z][a-z0-9_]*$`). A declaration has:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `description` | single-line string | `""` | what the input is for |
| `required` | boolean | `false` | a manual run must give a value |
| `default` | string | none | the value when none is given; not allowed with `"required": true` (a default would make `required` meaningless) |
| `choices` | non-empty array of distinct strings | none | the allowed values; a `default` must be one of them |

**Every value is a string**: values reach scripts as environment variables.
A boolean is a choice of `"true"` and `"false"`. An input that must be given
but has a usual value (like a bump type of `patch`) is declared not required
with that default.

**The naming rule.** Every declared input reaches every step and the setup as
`CICD_INPUT_<NAME upper-cased>` (`bump_type` becomes `CICD_INPUT_BUMP_TYPE`),
always set: to the manual run's value, else the default, else the empty
string. Inherited `CICD_INPUT_*` variables the job does not declare are
removed from the script's environment, so the declared inputs are the only
channel.

**Giving values.** The `Manual` workflow's form is generated from the config
(see [The generated workflows](#the-generated-workflows)): `job` is a dropdown
of the jobs that allow manual runs, and every declared input of those jobs is
a named field with its description, its default and, for an input with
`choices`, a dropdown of them. The owner picks the job and fills the fields;
from the command line, one `-f <name>=<value>` per input
(`gh workflow run git-cicd-manual.yml --ref main -f job=release -f bump_type=minor`).
The form reaches the tool only as one `env:` entry, `CICD_MANUAL_FORM`
(`${{ toJSON(inputs) }}`, a JSON object of strings), which the tool reads on a
manual run and removes from the scripts' environment. A value typed into a
field reaches the script exactly, quotes, `$`, backticks and newlines
included.

**One form for every job.** The form shows every manual job's fields at once,
so:

- an input declared under one name by several manual jobs is **one field**.
  Their declarations must be able to share it: the same `choices` and the
  same `default` (an absent default and `""` are the same). Their
  descriptions may differ; the field shows the first job's. A field not used
  by every manual job says which jobs use it, for example
  `Version bump type (job release)`;
- a run passes the chosen job **only the fields it declares**. Any other field
  is ignored, not an error; when its value is not the field's form default
  (its default, else the first choice, else empty) the report says so, for
  example `ignored input vendor (job release does not declare it)`;
- every input field is optional in the form, since the owner fills only the
  chosen job's; the tool enforces `required` for the chosen job, and an empty
  value counts as missing;
- `job` is the form's own field: a job that allows manual runs cannot declare
  an input named `job`;
- GitHub allows at most 25 inputs in a manually started workflow
  ([changelog, 2025-12-04](https://github.blog/changelog/2025-12-04-actions-workflow-dispatch-workflows-now-support-25-inputs/)),
  `job` included, so the manual jobs together have at most 24 distinct input
  names;
- GitHub evaluates `${{ ... }}` in every workflow string, and YAML has no
  escape for it, so a description, default or choice of a manual job cannot
  contain `${{`. Every other character is written safely (as a JSON string).

These rules apply only to jobs that allow manual runs: a job with
`"manual": false` is not in the form, and its inputs are not checked against
the others'.

**Changing inputs means regenerating.** Adding, changing or removing a
manual job's input, adding or removing a job that allows manual runs, or
changing a job's `manual` changes the `Manual` workflow: run `generate` and
commit `.github/workflows/git-cicd-manual.yml` in the same pull request;
`verify` (and with it the verdict) fails until you do.

**On every other trigger** (`open`, `merge`, `cron`, and local `check`) each
declared input is its default, or the empty string (a required input too).

**Locally**, `decide --trigger manual` and `run-job --trigger manual` read
the same `CICD_MANUAL_FORM` variable; without it every input is its default
(and a required input is missing).

**Failures.** A manual run is refused, with the reason in the report and the
status description, when `CICD_MANUAL_FORM` is not a JSON object of strings,
a required input of the chosen job is missing or empty, or a value is outside
the input's `choices`. `validate` refuses a malformed declaration naming the
job, the input and the reason (for example
`job release: input bump_type: default 'huge' is not one of the choices
(patch, minor, major)`): a bad name, an unknown field, a description or
default that is not a string, a default outside the choices, empty, duplicate
or non-string choices, a `required` that is not a boolean or comes with a
default, or `inputs` that is not an object. For the jobs that allow manual
runs it also refuses one input name declared with different choices or
defaults (`input bump_type is declared by jobs release and other with
different choices; ... give them the same choices and default, or rename
one`), an input named `job`, `${{` in a description, default or choice, and
a form of more than 25 fields (it gives the count and the limit); each
message says what to change, `"manual": false` on a job among the options.

### Patterns

`branches`, `paths` and `needs_nothing` use one matcher: `**` matches any
sequence including `/` (`dir/**` is everything under `dir`; a `**/` segment
may also match no directory, so `**/*.md` matches `README.md`), `*` matches
any sequence without `/` (so `*.md` is Markdown at the repository root only),
`?` matches one character other than `/`. Everything else is literal.

## When a job runs

- **`open`**: a pull request is opened or updated, its base (target) branch
  matches `branches`, and the change affects the job: a changed file outside
  `needs_nothing` matches its `paths` (a job without `paths` is affected by any
  change outside `needs_nothing`).
- **`merge`**: a change lands on a branch (a push), the branch matches
  `branches`, and the change affects the job under the same `paths` and
  `needs_nothing` rules as `open`. The changed files are what the push
  brought (`BEFORE...LANDED`, the commit before the push to the landed
  commit). A push that creates a branch has no commit before it (an all-zero
  `before`), so, like any base that does not resolve, the diff cannot be
  computed and every `merge` job whose `branches` match is needed. A push
  that deletes a branch runs nothing.
- **`cron`**: a schedule fires, and the job's `cron` is the expression that
  fired. The job then runs once on each of its literal `branches`, at that
  branch's head commit; `paths` and `needs_nothing` do not apply (a schedule
  has no change). A branch that does not exist fails the run with
  `branch <b> does not exist`, never silently.
- **manual**: someone runs one named job by hand (the `Manual` workflow).
  Every job may be run by hand unless it says `"manual": false`; `branches`
  still binds, against the branch the run is started on; `paths` and
  `needs_nothing` are ignored (a manual run has no change). An unknown job, a
  job with `"manual": false` or a branch that does not match is refused, and
  the run's verdict is FAILED with the reason in the report, never silently.
- A change affects **every** `open` or `merge` job whose `branches` match when it touches
  the git-cicd config or any script any job names (setup or step, whatever
  the job's triggers); when a changed file is in no job's `paths` and not in
  `needs_nothing`; or when the diff cannot be computed or is empty. So "not
  needed" only happens on purpose. `branches` always binds; forcing overrides
  `paths` only.
- The changed files are `git diff --name-only --no-renames BASE...HEAD`: what
  the branch changed since it left the base (both paths of a rename count).
- A file in `needs_nothing` never makes a job needed, unless it is the config
  or a job script.

Every decision carries a reason, and the report shows it.

## What a script is given

- The repository at the commit, as the working directory.
- The inherited environment plus:

| Variable | Value |
|---|---|
| `CICD_TRIGGER` | the trigger (`open`, `merge`, `cron`, `manual`) |
| `CICD_JOB` | the job name |
| `CICD_TARGET_BRANCH` | the target branch: on `open` the pull request's base; on `merge` the branch the change landed on; on `cron` the branch the job runs on; on manual the branch the run was started on |
| `CICD_SOURCE_BRANCH` | the source branch: on `open` the pull request's head (what `.vendored/check` needs to let install branches through); on `merge`, `cron` and manual the same branch as the target (there is no separate source, and the variable is never empty) |
| `CICD_BASE` | the base commit: on `open` the pull request's base; on `merge` the commit before the push (all zeros when the push created the branch); on `cron` the branch's head commit; on manual the run's commit |
| `CICD_HEAD` | the head commit: on `open` the pull request's head; on `merge` the landed commit; on `cron` the branch's head commit (the same as the base); on manual the run's commit (`github.sha`) |
| `CICD_CHANGED_FILES` | absolute path of a file listing the changed files, one per line (empty when the diff cannot be computed, and always on `cron` and manual) |
| `CICD_INPUT_<NAME>` | one per [declared input](#declared-inputs): the manual run's value, else the default, else empty; no other `CICD_INPUT_` variable is set |

- Secrets, by trigger. git-cicd itself never reads or logs them.

  | Trigger | `GITHUB_TOKEN` | `VENDOR_PAT` |
  |---|---|---|
  | `open` | passed through unchanged (read-only: `contents: read`) | **not passed**, and removed from the environment when set |
  | `merge`, `cron`, manual | passed through unchanged (the workflow's write permissions) | passed through unchanged |

  `VENDOR_PAT` is not only a read token for private vendor repositories: it
  is also the identity automation uses to propose changes, and may push
  branches, open pull requests and write workflow files. `open` runs a pull
  request's own code with a token that is read-only on purpose, and no `open`
  job writes anything, so a pull request's code never gets the write-capable
  secret. The `Open` workflow does not pass it, and `run-job --trigger=open`
  (which is what `check` runs) drops a `VENDOR_PAT` inherited from the
  caller, so a local check and CI give a script the same environment.

  **An `open` job that read a private vendor with `VENDOR_PAT`** (for example
  a setup that cloned a private repository) no longer can: move that step to
  a job on `merge`, `cron` or a manual run, which still get `VENDOR_PAT`, or
  make what the `open` job needs readable without it.
- Exit 0 passes. Anything else fails the job and stops its remaining steps.
- Setup runs first, on the same machine. What it installs on disk is its only
  channel to the steps; nothing else is passed between setup and steps or
  between steps. A failing setup is **could not run**, distinct from a failed
  step.

## No accidental injection

- A step is a file plus fixed arguments, run as a list argv, never a shell
  string; nothing is assembled into a command line.
- Facts about the change (branch names, commits, the changed files) and the
  values of declared inputs reach a script only as environment variables or
  a file; an input value never becomes part of a command line. The generated workflow
  follows the same rule: every fact is an `env:` entry, referenced in `run:`
  only as a quoted shell variable, never `${{ }}` inside `run:`. The Manual
  workflow's form passes every value in one `env:` entry,
  `CICD_MANUAL_FORM`; what the form writes from the config (job and input
  names, which are validated identifiers, and descriptions, defaults and
  choices, written as JSON strings, `${{` refused) sits only under
  `workflow_dispatch`, never in a `run:` block.
- A change to the config or to a job's scripts makes every job run, and the
  report says so.

## The report and the `Verdict / git-cicd:verdict` status

### Rows

Every row and the status are named `<name> / <owner>:<job>`. On a pull
request they are:

| Row | What | Kind |
|---|---|---|
| `Decide / git-cicd:decide` | decides which jobs the change needs; posts the pending status | check run (a job) |
| `<name> / <repo>:<job>` | one per needed job, for example `Unit Tests / medici:unit-tests` | check run (a job) |
| `Nothing needed / <repo>:(nothing)` | only when the run needs no job: a placeholder whose steps are all skipped | check run (a job) |
| `Report / git-cicd:report` | collects the results, writes the report, posts the final status | check run (a job) |
| `Verdict / git-cicd:verdict` | the verdict: **the one object a reader waits on** | commit status |

git-cicd owns its own three; a config job's row has the job's display name
(its job name in title case when it has none) and `<repo>`, the name of the
repository the workflow runs in. GitHub shows a check run after its
workflow's name, which is the trigger's (`Open / Unit Tests / medici:unit-tests`,
`Open / Decide / git-cicd:decide`, and on a push `Merge / Unit Tests /
medici:unit-tests`, `Merge / Decide / git-cicd:decide`,
`Merge / Report / git-cicd:report`, and `Cron / ...` or `Manual / ...` for a schedule or a manual run); a status has no workflow and shows as
`Verdict / git-cicd:verdict`. No row or status name carries a version: it is
what branch protection and anything else that waits on a check refers to, and
it does not change when a tool is upgraded.

**A run that needs no job** (on any trigger: a pull request that changes only
`needs_nothing` files, a push to a branch no `merge` job names, a schedule
with nothing to run) shows `Decide / git-cicd:decide`,
`Nothing needed / <repo>:(nothing)` and `Report / git-cicd:report`, all
green, and the `Verdict / git-cicd:verdict` status as always (for example
`PASSED - 0 of 3 jobs needed: only needs_nothing files changed`). The
placeholder row is the workflow's `run` job, run once for the placeholder
entry `(nothing)` with every step skipped (it takes a runner for a few
seconds). The `run` job is never skipped as a whole: GitHub does not expand
the name of a matrix job that is skipped before its matrix is evaluated, so a
skipped `run` job would show its raw `${{ ... }}` name expression as a row.
`(nothing)` is no valid job name, so no config job's row can look like it.
The placeholder uploads no result, so the report and the verdict are the
same as without it.

### The report

The header names the change under test: the repository and the short head
commit (`git-cicd report: medici at 1a2b3c4 ...`). A pull request tests a
change, not a release, so the versions in the step lines are their owners'
last releases, never the version of the change.

Then one line per declared job, in config order, named like its row:
`passed`, `failed (step <step>, exit <code>)`, `could not run (setup failed)`
(or `(no result)` when a runner was lost), or `not needed (<reason>)`;
non-blocking jobs are marked. Under each job that ran, one line for setup and
for every step that ran, with its result and its time, so cost is visible in
every pull request:

    <name> / <owner>@<version>:<job>:<step>  passed  2.5s

`<step>` is the step's (or setup's) file name. `<owner>` and `<version>`:

| The file is | `<owner>` | `<version>` |
|---|---|---|
| under `.vendored/pkg/<vendor>/` | the vendor | the first line of `.vendored/manifests/<vendor>.version` |
| anywhere else | the repository (`<repo>`) | the first line of the version file the repository's git-semver config names (`version_file` in `.vendored/configs/git-semver.json`, default `VERSION`) |

When that file does not exist (or is empty) the line has no `@<version>`; a
version is never guessed. Step lines are in the report only: there is no row
or status per step, and the `Verdict / git-cicd:verdict` description stays the verdict
line (at most 140 characters).

`<repo>` comes from the platform in Actions (the name part of
`GITHUB_REPOSITORY`, and `github.event.repository.name` in a row). Locally
(`git-cicd check`) it is the last path segment of the `origin` remote's URL
without `.git`; with no `origin` remote, the name of the checkout's top-level
directory.

After the jobs: whether the generated workflows match the config, then one
verdict:

- **FAILED** when a blocking job failed or could not run, or the generated
  workflows do not match the config (including while the old single
  `.github/workflows/git-cicd.yml` is still there);
- **PASSED** otherwise, e.g. `PASSED - 2 of 3 jobs needed, 2 passed`. A change
  that needs nothing is green with the explanation:
  `PASSED - 0 of 3 jobs needed: only needs_nothing files changed`.

In GitHub Actions the report is also written to the job summary of the
`Report / git-cicd:report` job, and the verdict is the one always-present
status with the fixed name **`Verdict / git-cicd:verdict`**.

**`Verdict / git-cicd:verdict` is pending from the start of the run.** It is
a *commit status* on the pull request's head commit, not a job: GitHub
creates a job's check run only when the job is queued, and the job that
reports is queued after every other job, so a job could not be present from
the start. The first step of the first job (`Decide / git-cicd:decide`) sets
the status to **pending**; the last step of `Report / git-cicd:report` sets it
to **success** or **failure** with the verdict line as its description (for
example `PASSED - 0 of 3 jobs needed: only needs_nothing files changed`), and
to failure when the report did not run to the end. One object carries the
name: no job's check run is called `Verdict / git-cicd:verdict`.

What a reader can rely on, and from when:

- From the moment GitHub creates the run for a push, the head commit has a
  `Decide / git-cicd:decide` check (queued, then in progress), and a few
  seconds later, when that job's first step runs, the pending
  `Verdict / git-cicd:verdict` status. This holds when the push supersedes an
  older run too: nothing in the workflow waits for another run, so the newer
  run's `decide` starts at once instead of after the older run has finished
  cancelling.
- Before GitHub has created the run (usually seconds after the push), the
  commit may have no git-cicd check or status at all; that gap is the
  platform's. A reader should treat an absent `Verdict / git-cicd:verdict`
  like a pending one.
- A run that is cancelled, superseded or dies leaves its commit's status
  pending or failed, never green without a verdict. A superseded run fails
  its `decide` job once it sees that the pull request's head has moved on,
  and its report is FAILED for every job it needed.

**The status when there is no pull request.** A `merge`, `cron` or manual
run's verdict is the same `Verdict / git-cicd:verdict` commit status, on the
commit the run is for (the landed commit, the head of each branch a schedule
runs on, or the commit a manual run was started on):
pending from the first step of decide, final from the last step of report,
and failure when the report did not run to the end. One exception keeps the
status the pull request's: a push to a branch with an open pull request
starts both `Open` and `Merge` on the same commit, and both would write the
same status (the last writer wins, so a `Merge` run that needs nothing could
turn a failed `Open` verdict green). So a run of any trigger but `open` posts
the status, pending and final, **only when no open pull request has that
commit as its head**. Otherwise the `Open` run owns the status, and the other
run's verdict is its `Report / git-cicd:report` check run, which fails on a
FAILED verdict, and its job summary.

**Wait on the `Verdict / git-cicd:verdict` status.** In branch protection,
require `Verdict / git-cicd:verdict` (a required check matches a status of
that name). A script should read the commit's statuses
(`GET /repos/{owner}/{repo}/commits/{ref}/status`, or `statusCheckRollup` in
`gh pr view --json statusCheckRollup`, where it is a `StatusContext` with that
`context`), and wait while it is pending or absent. The check runs are for
reading: `Report / git-cicd:report` holds the full report, and its state
follows the verdict. A repository that required the old name `git-cicd
verdict` changes its branch protection to the new name when it upgrades.

## The generated workflows

git-cicd generates **one workflow per trigger**, each its own file with its
own GitHub event, its own permissions (at the top level or per job) and its own
overlap rule, and each named for its trigger, so a row reads
`Open / Unit Tests / medici:unit-tests`:

| Trigger | Workflow name | File | Generated |
|---|---|---|---|
| `open` | `Open` | `.github/workflows/git-cicd-open.yml` | yes |
| `merge` | `Merge` | `.github/workflows/git-cicd-merge.yml` | yes |
| `cron` | `Cron` | `.github/workflows/git-cicd-cron.yml` | yes, when a job has `cron` in `on` |
| manual | `Manual` | `.github/workflows/git-cicd-manual.yml` | yes, when a job allows manual runs |

The names and file names are fixed for good: each trigger was built by
adding its own file, changing no other. The names are the trigger words
(not `CI`/`CD`): the config already says `"on": ["open"]`, and a trigger is
not a kind of job.

`git-cicd generate` writes every generated file. **Every generated file is
fixed text except the cron workflow's schedule block** (one entry per distinct
cron expression in the config) **and the Manual workflow's form** (which jobs
its `job` dropdown lists and which named input fields it has), and the tool
path, which follows where git-cicd is installed. Jobs are decided when a
workflow runs, so `Open` and `Merge` never change with the config, and two
configs that differ only in jobs that are neither `cron` nor manual (or only
in their `paths`, `branches`, `steps` or `name`) generate the same files.
(The comments at the top of the `open`, `merge` and `cron` templates still
read "fixed text except the cron workflow's schedule block": they are left as
they are so those files stay byte-identical; this section and the `manual`
template carry the rule.)

The `open` workflow (`Open`):

- Event: `pull_request` (opened, synchronize, reopened), every target
  branch; `branches` are decided by the tool.
- Token: `contents: read` at the top level. `Decide / git-cicd:decide` and
  `Report / git-cicd:report` also get `statuses: write`, the one write
  permission on `open`, and only to set the `Verdict / git-cicd:verdict`
  status (pending at the start, the verdict at the end); the job that runs the
  config's scripts has no permission of its own (only the read-only top level).
- Secrets: that job gets `GITHUB_TOKEN` (read-only) and **not**
  `VENDOR_PAT`, which may write (see
  [What a script is given](#what-a-script-is-given)); `Merge`, `Cron` and
  `Manual` pass both.
- Overlap: a newer push to the same pull request supersedes the older run.
  It cancels the older run's jobs that run the config's scripts (a
  `concurrency` group per pull request and job on the `run` job only; there is
  none on the workflow or on the status-posting jobs, so the newer run's
  pending status never waits for the older run).
- `decide` works out the needed jobs and their display names (its `jobs`
  and `names` outputs); `run` gives each needed job its own
  runner (`ubuntu-latest`), at most `max_parallel` at once, always with setup;
  `verdict` (`Report / git-cicd:report`) collects the results, verifies the
  workflows, reports and sets the `Verdict / git-cicd:verdict` status.
- Only GitHub's own `actions/checkout`, `actions/upload-artifact` and
  `actions/download-artifact`; no Python version is written anywhere: setup
  scripts install the Python they need (for example from `requires-python`).

The `merge` workflow (`Merge`):

- Event: `push` to every branch (`branches: ['**']`, no tags); `branches`
  are decided by the tool against the branch the push landed on. Every job
  skips a push that deletes a branch (`github.event.deleted`): there is no
  commit to run on or to put a status on.
- Token: `contents: read` at the top level. The job that runs the config's
  scripts gets `contents: write` and `pull-requests: write` (a release pushes
  a commit and tags, or opens a pull request), and checks out the landed
  commit on its branch with full history and tags (`fetch-depth: 0`,
  `fetch-tags: true`). `Decide / git-cicd:decide` and
  `Report / git-cicd:report` get `statuses: write` and `pull-requests: read`
  (to see whether an open pull request owns the status); decide also gets
  `actions: read` for the queue.
- Overlap: runs on one branch go **one at a time and are never cancelled**.
  The file has no `concurrency` key: a GitHub concurrency group keeps only
  one pending run, and cancels the pending one when a newer run joins, even
  with `cancel-in-progress: false`. Instead `decide`, right after posting
  pending, waits until no earlier run (a lower run id) of
  `git-cicd-merge.yml` or `git-cicd-manual.yml` on the same branch is queued
  or in progress (it polls `repos/{owner}/{repo}/actions/runs` for the
  branch's latest 100 runs), so a manual run of a release job shares the
  queue.
- Jobs as on `open`: `decide`, one `run` per needed job (at most
  `max_parallel` at once, always with setup), and `verdict`
  (`Report / git-cicd:report`); the verdict is the status on the landed
  commit under the rule above.

The manual workflow (`Manual`):

- Start one from the Actions tab: pick **Manual**, choose *Run workflow*,
  pick the branch to run on, pick the job in the `job` dropdown and fill the
  fields of that job (leave the other jobs' fields as they are). From the
  command line, one `-f` per field:
  `gh workflow run git-cicd-manual.yml --ref main -f job=release -f bump_type=minor`.
- Event: `workflow_dispatch` with the form generated from the config: `job`,
  a required dropdown of the jobs that allow manual runs, in config order,
  then one optional field per distinct [declared input](#declared-inputs) of
  those jobs, in first-seen order. For a config with a `release` job (inputs
  `bump_type` and `changelog_description`) and an `update-vendored` job
  (input `vendor`) the form is:

  ```yaml
  on:
    workflow_dispatch:
      inputs:
        job:
          description: "The config job to run"
          required: true
          type: choice
          options:
            - "release"
            - "update-vendored"
        bump_type:
          description: "Version bump type (job release)"
          required: false
          default: "patch"
          type: choice
          options:
            - "patch"
            - "minor"
            - "major"
        changelog_description:
          description: "Changelog entry (job release)"
          required: false
          type: string
        vendor:
          description: "Vendor to update (or all) (job update-vendored)"
          required: false
          default: "all"
          type: string
  ```

  Names are validated identifiers, written bare; descriptions, defaults and
  options are JSON strings, so no character in them can change the file
  (`${{` is refused by `validate`). The values reach the tool only as the
  one `env:` entry `CICD_MANUAL_FORM: ${{ toJSON(inputs) }}`, never
  `${{ }}` inside `run:`; the env lines are fixed text, only the form
  varies. `decide --trigger manual --job NAME` decides: the job is needed
  (`manual run`) when it exists, allows manual runs and its `branches` match
  the branch; every other job is `not needed (not the job asked for)`.
  Inputs that fail (see [Declared inputs](#declared-inputs)) are refused the
  same way. A refusal is recorded in the decisions (`refused`), needs no job,
  and the report is `FAILED - <reason>` in the report, the job summary and the
  status description. Fields the chosen job does not declare are recorded
  (`ignored`) and listed in the report when not at their form default.
- **No manual job, no file.** With no job that allows manual runs (every job
  says `"manual": false`, or there is none), `generate` writes no
  `git-cicd-manual.yml` and removes an existing one (saying so; commit the
  removal), and `verify` fails while it is still there: the `job` dropdown
  needs an option, and a workflow with nothing to run must not exist.
- `verify` covers the form like the schedule block: a change to a manual
  job's inputs, a new manual job or a changed `manual` without `generate`
  fails the verdict with the diff and `run: <tool> generate and commit ...`.
- Token, checkout, queue and verdict as on `Merge`: write permissions only on
  the job that runs the config's scripts, full history and tags, and manual
  and merge runs on one branch go one at a time, never cancelled.

**Upgrading from a version with the two free-text fields** (`job` and
`inputs`): run `generate` and commit the new `git-cicd-manual.yml` (`verify`
fails until you do). The `inputs` field, `-f inputs='{...}'` and
`CICD_MANUAL_INPUTS` no longer exist: anything that starts a run with
`gh workflow run git-cicd-manual.yml ... -f inputs='{"bump_type": "minor"}'`
switches to one `-f <name>=<value>` per input
(`-f job=release -f bump_type=minor`), and a script that read
`CICD_MANUAL_INPUTS` reads its `CICD_INPUT_<NAME>` variables. Every job is
in the `job` dropdown unless it says `"manual": false`: set that on jobs that
should not be started by hand (for example jobs that only check pull
requests). If `validate` now refuses the config, two manual jobs declare one
input name differently, or a job declares an input named `job`: rename one
or set `"manual": false`.

The cron workflow (`Cron`):

- Event: `schedule`, one entry per distinct `cron` expression among the
  config's jobs with `cron` in `on`, sorted and quoted
  (`    - cron: "0 9 * * 1"`). This schedule block and the Manual workflow's
  form are the only parts of any generated file that vary with the config;
  `verify` fails when either and the config disagree.
- **No cron job, no file.** With no job that has `cron` in `on`, `generate`
  writes no `git-cicd-cron.yml` and removes an existing one (saying so; commit
  the removal), and `verify` fails while it is still there: GitHub needs an
  event under `on:`, and a schedule must never fire with nothing to run. The
  template is installed either way.
- **GitHub runs schedules only from the default branch's copy of the file**,
  on the default branch's ref. A schedule added on another branch does
  nothing until it reaches the default branch, and decide reads the default
  branch's config.
- `decide --trigger cron --cron EXPR` gets the expression that fired
  (`github.event.schedule`, through `env:`) and needs every job whose `cron`
  is that expression, once for each of its literal `branches`; other cron
  jobs are `not needed (scheduled at <their expression>)`. It resolves each
  branch's head once, from `origin/<branch>` after a full checkout, so every
  job on a branch runs on the same commit, and a branch that does not exist
  is reported as failed. Its matrix output is the cron-only `runs`, a list of
  `{key, job, branch, sha}`.
- Token: write permissions (`contents: write`, `pull-requests: write`) only
  on the job that runs the config's scripts, which checks out its branch's
  head with full history and tags; decide and report get `statuses: write`
  and `pull-requests: read`.
- No queue: a schedule event carries the default branch's ref, not the job's
  branch, so cron runs do not join the `Merge`/`Manual` queue (the one cron
  job planned, a weekly update, only opens pull requests).
- Verdict: one `Verdict / git-cicd:verdict` status on the head commit of
  **each branch** the run is for, set to pending as soon as decide has
  resolved the heads and to the branch's verdict by the last step of report
  (failure when the report did not run to the end), under the no-open-pull-
  request rule. The report has one section and one verdict per branch, then
  the run's verdict (`PASSED - schedule 0 9 * * 1 on 1 branch`), which the
  `Report / git-cicd:report` check follows; a missing branch has no commit to
  carry a status and fails the run.

**The generate/verify rule.** The generated workflows are the repository's to
commit (see "Who owns what" under Installing). The platform's token cannot push
workflow files, so CI never regenerates. Whoever upgrades
git-cicd or changes the config runs `generate` and commits what it writes in
the same pull request, from any branch; the vendor check accepts it.
`git-cicd verify` regenerates every file in memory, compares each whole file,
and fails naming the command to run when one is missing or differs, or when
the old single file is still there; that catches a stale file and any hand
edit.

### Migrating from the single `git-cicd.yml`

git-cicd up to 0.0.2 generated one file, `.github/workflows/git-cicd.yml`, for
every trigger. In a repository that still has it, `generate` writes
`.github/workflows/git-cicd-open.yml` and **removes the old file**; commit
the new file and the deletion together. Until then `verify` fails (and so does
the verdict), naming the command to run. Every install runs `generate`, so the
install pull request of an upgrade does this for you when it may carry workflow
files; otherwise run `generate` and commit from any branch. Then point
branch protection and anything else that waited on `git-cicd verdict` at
`Verdict / git-cicd:verdict`.

## Installing

**Install and upgrade git-cicd by running the repository's Install Vendored
workflow, with `mangimangi/git-cicd` as the vendor.** Nothing else is the way
to install or upgrade it.

1. In the repository, open the Actions tab, pick **Install Vendored**
   (`.github/workflows/install-vendored.yml`), choose *Run workflow* and enter
   `mangimangi/git-cicd` as the vendor (the version defaults to the latest).
2. The workflow opens the install pull request from the branch
   `chore/install-git-cicd`. That pull request carries the tool, the
   templates, the schema and the config when it is missing. The install also
   regenerates the per-trigger workflows
   (`.github/workflows/git-cicd-open.yml`, `git-cicd-merge.yml`,
   `git-cicd-manual.yml` when a job allows manual runs, and
   `git-cicd-cron.yml` when a job has `cron` in `on`; on the first upgrade from the single file, also the deletion of
   `.github/workflows/git-cicd.yml`), but the pull request may arrive without
   them: one pushed with a token that may not write workflow files leaves
   them out. Review and merge it like any other.
3. Then, if the workflows are missing or stale (`git-cicd verify` fails),
   run `generate` and commit what it writes, from any branch (see below).
4. Upgrades are the same run (the workflow's weekly schedule also updates every
   vendor); each one opens a new install pull request.

**The one exception is git-vendored itself.** A repository with no `.vendored/`
yet gets git-vendored once from git-vendored's documented bootstrap (the
`curl ... install.sh | bash` in git-vendored's README), because that bootstrap
is what delivers the Install Vendored workflow. Everything after it, git-cicd
included, goes through the workflow.

**Do not run `.vendored/install` by hand in a checkout to install or upgrade.**
The workflow runs `python3 .vendored/install mangimangi/git-cicd --pr` for you;
run by hand and pushed from an ordinary branch, the same command produces a
pull request that `.vendored/check` (the Check Vendor Files job) rejects with
"Protected vendor files were modified": the check lets vendor-managed files
through only from the vendor's own install branch (`chore/install-git-cicd`).
An agent session never writes, copies or edits a vendor-protected file at all;
when a task needs a vendored tool installed or upgraded, that is a step for the
repository's owner (running the workflow), and the session stops and says so.

What lands where:

| Path | What | On upgrade |
|---|---|---|
| `.vendored/pkg/git-cicd/git-cicd` | the tool | replaced |
| `.vendored/pkg/git-cicd/templates/workflows/<trigger>.yml` | the templates `generate` fills, one per generated trigger | replaced |
| `.vendored/manifests/git-cicd.schema` | the config schema, for `.vendored/audit` | replaced |
| `.vendored/configs/git-cicd.json` | your config: the jobs | **created once**, only when missing; never overwritten |
| `.github/workflows/git-cicd-<trigger>.yml` | the generated workflows: **the repository's**, not in the install manifest | **regenerated on disk on every install**; you commit them (the install pull request may not carry them) |

The default config declares no jobs (`"jobs": {}`, `"needs_nothing": []`), so
a fresh install validates and needs nothing until you declare jobs.

**Who owns what.** The install manifest (`.vendored/manifests/git-cicd.files`)
lists only what git-cicd owns: the tool, its templates and the schema; those
are protected. The generated workflows are the repository's, allowed and never
protected: `install.sh`
writes them to disk but never lists them in the manifest, and the installed
config lists them as editable (`_vendor.allowed`, the pattern
`.github/workflows/git-cicd-*.yml`, which covers the files of triggers still
to come) along with the config itself. So the fix for a missing or stale
workflow is always the same: run `generate` and commit the result from any
branch, which the vendor check accepts. (A repository registered before this
pattern keeps the editable list it was registered with; add
`.github/workflows/git-cicd-*.yml` to `_vendor.allowed` in
`.vendored/configs/git-cicd.json`.)

**Whoever changes the config runs**

```bash
.vendored/pkg/git-cicd/git-cicd generate
```

**and commits the generated workflows (`.github/workflows/git-cicd-*.yml`) in
the same pull request.**

## Running the checks locally

The same jobs CI runs on a pull request run on your machine, or in a session
container, with one command and no GitHub (no network, no GitHub environment
variables):

```bash
.vendored/pkg/git-cicd/git-cicd check            # in a repository that installed git-cicd
./git-cicd check                                 # in git-cicd itself
```

`check` decides which jobs the change needs (the `open` trigger), runs the
needed jobs **one after another** (never in parallel locally), then prints the
same report and verdict as the `Verdict / git-cicd:verdict` status.

```
git-cicd check [--target BRANCH] [--source BRANCH] [--base REV] [--head REV]
               [--job NAME [--force]] [--setup]
```

Defaults, chosen so that a branch is checked against its target without
arguments:

| Option | Default |
|---|---|
| `--source` | the current branch (`git rev-parse --abbrev-ref HEAD`) |
| `--head` | `HEAD` |
| `--target` | the upstream's branch name if one is set (and it is not the branch's own remote copy), else the remote default branch (`origin/HEAD`), else `main` |
| `--base` | `origin/<target>` if it exists, else `<target>` |

Revisions are resolved to commits with `git rev-parse` before deciding. The
changed files are `git diff BASE...HEAD`: what the branch changed since it
left the target.

- `--setup` runs each job's `setup` script first. It is off by default because
  locally setup installs things for real; without it the report notes
  `setup skipped (pass --setup to run it)` for every job that declares one.
  Pass it the first time.
- `--job NAME` runs that single job. It stays bound by the job's `branches` and
  by the decision: a job the change does not need is reported as not needed.
  Add `--force` to run it regardless of its `paths` (`branches` still binds).
  An unknown job name exits 2.
- Scripts get the same environment as in CI: every `CICD_` variable, and
  `GITHUB_TOKEN` passed through unchanged when it is set. `check` runs on
  `open`, so a `VENDOR_PAT` in the caller's environment is removed, as the
  `Open` workflow does not pass it.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | verdict PASSED |
| 1 | verdict FAILED (a blocking job failed or could not run, or the generated workflows do not match the config) |
| 2 | config or usage error, or a refused manual `run-job` |

## Commands

| Command | What |
|---|---|
| `validate [--config PATH]` | load and validate the config: `config ok: N jobs` or every error |
| `decide --trigger open\|merge\|manual --target B --source B --base SHA --head SHA [--job NAME] [--json] [--changed-files-out PATH]`, or `decide --trigger cron --cron EXPR [--json]` | one decision per declared job, with the reason; `--job` names the job of a manual run (required with `--trigger manual`, refused with any other); `--cron` is the schedule that fired (required with `--trigger cron`, refused with any other); in Actions also writes `jobs`, `names`, `any`, `max_parallel` (and on cron `runs`) to `GITHUB_OUTPUT`, where `jobs` (and `runs`) is the placeholder `(nothing)` when no job is needed |
| `run-job JOB --trigger open\|merge\|cron\|manual --target … --head SHA [--setup] [--result PATH]` | setup when asked, then the steps; result JSON with the times |
| `generate` / `verify` | write / check the generated workflows (`.github/workflows/git-cicd-open.yml`, `.github/workflows/git-cicd-merge.yml`, `.github/workflows/git-cicd-manual.yml` when a job allows manual runs, and `.github/workflows/git-cicd-cron.yml` when a job has `cron` in `on`); `generate` removes, and `verify` fails on, the old `.github/workflows/git-cicd.yml` |
| `report --decisions FILE --results DIR [--trigger open\|merge\|cron\|manual] [--verdict-out PATH]` | the report and verdict from `decide --json` and `run-job --result` files; `--verdict-out` writes the status state (`success`/`failure`) and description, one per line (on cron one line per branch head: `<sha> TAB <state> TAB <description>`) |
| `check […]` | the local command above |

## Not built yet

- Secrets beyond `GITHUB_TOKEN` and `VENDOR_PAT` (which `open` does not
  get).
- An image or runtime per job.

## Developing git-cicd

git-cicd checks, releases and updates itself with itself. Its workflows run
the root `./git-cicd`, so CI tests the code in the pull request. Its own
config declares four jobs, one per trigger:

| Job | Row | Trigger | Script | What |
|---|---|---|---|---|
| `test` | `Open / Unit Tests / git-cicd:test` | `open`, every branch, `paths` the code; not by hand (`"manual": false`) | `ci/setup.sh`, `ci/test.sh` | setup installs pytest, pytest-cov and coverage (7.10 or later) for the Python floor (`>=3.11` in `pyproject.toml`), and bats-core when `bats` is not on PATH; the step runs the pytest suite, prints the line coverage of `git-cicd` with its missing lines and fails below 99%, then runs the bats tests of `install.sh` and the `ci/` scripts (`tests/bats/`) |
| `vendor-check` | `Open / Check Vendor Files / git-cicd:vendor-check` | `open`, every branch; not by hand (`"manual": false`) | `ci/vendor-check.sh` | `python3 .vendored/check --base "$CICD_BASE"`; it sets `GITHUB_HEAD_REF` from `CICD_SOURCE_BRANCH` when unset, so a local `check` lets `chore/install-*` branches through like Actions does |
| `release` | `Merge / Release / git-cicd:release` | `merge` on `main`; by hand with the inputs `bump_type` (patch, minor, major; default patch), `subdirectory`, `changelog_description` | `ci/release.sh` | git-semver's `release`: `publish` when the landed commit's subject starts with `chore: bump version`, nothing for `chore: install`, otherwise `bump` (and `bump` on a manual run); it gives `release` `GITHUB_EVENT_NAME`, `GITHUB_EVENT_BEFORE`, `INPUT_BUMP_TYPE`, `INPUT_SUBDIRECTORY`, `INPUT_CHANGELOG_DESCRIPTION` and `GH_TOKEN` |
| `update-vendored` | `Cron / Install Vendored / git-cicd:update-vendored` | `cron` `0 9 * * 1` on `main`; by hand with the inputs `vendor` (default all), `version` (default latest), `private` (true or false; default false) | `ci/update-vendored.sh` | `python3 .vendored/install <vendor> --version <version> --pr --deps=install` (plus `--private`), with `GH_TOKEN` set to `VENDOR_PAT` when set, else `GITHUB_TOKEN`; only CI runs it |

`release` has no `paths`, so a push that changes only `needs_nothing` files
does not release, while a `chore: bump version` commit still publishes
(`VERSION` is in no job's `paths` and not in `needs_nothing`). Start a
release or an update by hand from the Actions tab: **Manual**, *Run
workflow* on `main`, then pick the job in the `job` dropdown and fill its
named fields: `release` with `bump_type` (a dropdown of patch, minor, major),
`subdirectory` and `changelog_description`, or `update-vendored` with
`vendor` (for example `mangimangi/git-semver`), `version` and `private` (a
dropdown of true, false). Each field's description names the job that uses
it; the other job's fields are ignored. From the command line:
`gh workflow run git-cicd-manual.yml --ref main -f job=release -f bump_type=minor`.
`test` and `vendor-check` run on pull requests and are not in the dropdown
(`"manual": false`). A change to a job's inputs (or its `manual`) changes
the Manual workflow: run `./git-cicd generate` and commit it with the change.

The vendor-installed workflows these jobs replace (`version-bump.yml`,
`check-vendor.yml`, `install-vendored.yml`) are removed from this repository;
git-semver and git-vendored still install them into other repositories.

The `test` step measures line coverage of `git-cicd` in the pytest process
and in every `python3 git-cicd …` a test starts as a subprocess, including
the copies tests install into temporary repositories; `pyproject.toml`
(`[tool.coverage]`) maps them onto one `git-cicd` row. Each run writes its
data into a fresh temporary directory, so two runs give the same figure.
The step fails below 99% line coverage of `git-cicd` (`fail_under` in
`pyproject.toml`, so a local `coverage report` reads the same rule): a change
that lowers coverage below 99% fails the verdict and adds its tests in the
same pull request. A line is excluded (`# pragma: no cover`) only when no test
can reach it, with a comment on that line saying why. Without pytest-cov the
step fails in CI; locally (no `--setup`) it runs the suite and says coverage
was not checked.

The bats tests (`tests/bats/*.bats`, with `tests/bats/helper.bash`) run each
`ci/` script and `install.sh` in a temporary git repository with fake
vendored tools that log their arguments and environment, and use no network.
`ci/setup.sh` installs bats-core 1.11.1 (its npm tarball, checked against a
pinned sha256) into `${XDG_CACHE_HOME:-~/.cache}/git-cicd/bats` when `bats`
is not on PATH. The step runs pytest and then bats, and fails when either
fails; without bats it fails in CI and, locally, says to run
`./git-cicd check --setup`.

```bash
./git-cicd check --setup     # the first time
./git-cicd check
```
