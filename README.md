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
| `.github/workflows/git-cicd-<trigger>.yml` | generated | the GitHub Actions workflows, one per trigger (`git-cicd-open.yml`, `git-cicd-merge.yml`, `git-cicd-manual.yml`, and `git-cicd-cron.yml` when a job has `cron` in `on`); generated, committed |
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
| `manual` | boolean | `true` | the job can be run by hand |
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

**Giving values.** The `Manual` workflow is fixed text, so it cannot list a
job's inputs. It has one second free-text field, `inputs`, holding a JSON
object of string values, for example `{"bump_type": "minor"}` (empty means
`{}`). JSON carries quotes, `$`, backticks and newlines exactly. The field
reaches the tool only as the `env:` entry `CICD_MANUAL_INPUTS`, which the tool
reads on a manual run and removes from the scripts' environment.

**On every other trigger** (`open`, `merge`, `cron`, and local `check`) each
declared input is its default, or the empty string (a required input too).

**Failures.** A manual run is refused, with the reason in the report and the
status description, when the `inputs` field is not a JSON object of strings,
names an input the job does not declare, leaves out a required input or gives
a value outside the input's `choices`. `validate` refuses a malformed
declaration naming the job, the input and the reason (for example
`job release: input bump_type: default 'huge' is not one of the choices
(patch, minor, major)`): a bad name, an unknown field, a description or
default that is not a string, a default outside the choices, empty, duplicate
or non-string choices, a `required` that is not a boolean or comes with a
default, or `inputs` that is not an object.

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

- `GITHUB_TOKEN` and `VENDOR_PAT`, passed through unchanged. git-cicd itself
  never reads or logs them.
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
  only as a quoted shell variable, never `${{ }}` inside `run:`.
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
| manual | `Manual` | `.github/workflows/git-cicd-manual.yml` | yes |

The names and file names are fixed for good: each trigger was built by
adding its own file, changing no other. The names are the trigger words
(not `CI`/`CD`): the config already says `"on": ["open"]`, and a trigger is
not a kind of job.

`git-cicd generate` writes every generated file. **Every generated file is
fixed text except the cron workflow's schedule block** (one entry per distinct
cron expression in the config), and the tool path, which follows where
git-cicd is installed. Jobs are decided when a workflow runs, so two configs
that differ only in jobs that are not `cron` generate the same files.

The `open` workflow (`Open`):

- Event: `pull_request` (opened, synchronize, reopened), every target
  branch; `branches` are decided by the tool.
- Token: `contents: read` at the top level. `Decide / git-cicd:decide` and
  `Report / git-cicd:report` also get `statuses: write`, the one write
  permission on `open`, and only to set the `Verdict / git-cicd:verdict`
  status (pending at the start, the verdict at the end); the job that runs the
  config's scripts has no permission of its own (only the read-only top level).
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
  pick the branch to run on and type the job name (a key under `jobs` in the
  config) into the `job` field. From the command line:
  `gh workflow run git-cicd-manual.yml --ref main -f job=release`.
- Event: `workflow_dispatch` with two free-text inputs, as fixed text: `job`
  and `inputs` (the job's [declared inputs](#declared-inputs) as a JSON
  object of strings, for example `{"bump_type": "minor"}`; leave it empty for
  none or for the defaults). They reach the tool only through `env:` entries
  (`inputs` as `CICD_MANUAL_INPUTS`), never `${{ }}` inside `run:`. From the
  command line: `gh workflow run git-cicd-manual.yml --ref main -f job=release
  -f inputs='{"bump_type": "minor"}'`. `decide --trigger manual --job NAME` decides: the job is
  needed (`manual run`) when it exists, allows manual runs and its
  `branches` match the branch; every other job is `not needed (not the job
  asked for)`. Inputs that fail (see [Declared inputs](#declared-inputs)) are
  refused the same way. A refusal is recorded in the decisions (`refused`), needs no
  job, and the report is `FAILED - <reason>` in the report, the job summary
  and the status description.
- Token, checkout, queue and verdict as on `Merge`: write permissions only on
  the job that runs the config's scripts, full history and tags, and manual
  and merge runs on one branch go one at a time, never cancelled.

The cron workflow (`Cron`):

- Event: `schedule`, one entry per distinct `cron` expression among the
  config's jobs with `cron` in `on`, sorted and quoted
  (`    - cron: "0 9 * * 1"`). This schedule block is the only part of any
  generated file that varies with the config; `verify` fails when it and the
  config disagree.
- **No cron job, no file.** With no job that has `cron` in `on`, `generate`
  writes no `git-cicd-cron.yml` and removes an existing one (saying so; commit
  the removal), and `verify` fails while it is still there: GitHub needs an
  event under `on:`, and a schedule must never fire with nothing to run. The
  template is installed either way, and the install manifest lists only the
  workflows `generate` wrote.
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

**The generate/verify rule.** The platform's token cannot push workflow files,
so CI never regenerates. Whoever upgrades git-cicd or changes the config runs
`generate` and commits what it writes in the same pull request.
`git-cicd verify` regenerates every file in memory, compares each whole file,
and fails naming the command to run when one is missing or differs, or when
the old single file is still there; that catches a stale file and any hand
edit.

### Migrating from the single `git-cicd.yml`

git-cicd up to 0.0.2 generated one file, `.github/workflows/git-cicd.yml`, for
every trigger. In a repository that still has it, `generate` writes
`.github/workflows/git-cicd-open.yml` and **removes the old file**; commit
the new file and the deletion together. Until then `verify` fails (and so does
the verdict), naming the command to run. The install pull request of an
upgrade does this for you, since every install runs `generate`. Then point
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
   `chore/install-git-cicd`. That pull request carries the tool, the schema,
   the config when it is missing, and the regenerated per-trigger workflows
   (`.github/workflows/git-cicd-open.yml`, `git-cicd-merge.yml`,
   `git-cicd-manual.yml`, and `git-cicd-cron.yml` when a job has `cron` in
   `on`; on the first upgrade from the single
   file, also the deletion of `.github/workflows/git-cicd.yml`). Review and
   merge it like any other.
3. Upgrades are the same run (the workflow's weekly schedule also updates every
   vendor); each one opens a new install pull request with the regenerated
   workflow.

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
| `.github/workflows/git-cicd-<trigger>.yml` | the generated workflows | **regenerated on every install**, so an upgrade reaches them in the install pull request |

The default config declares no jobs (`"jobs": {}`, `"needs_nothing": []`), so
a fresh install validates and needs nothing until you declare jobs. The config
and the generated workflows are listed as editable (`_vendor.allowed`) for
git-vendored's check, the workflows as the pattern
`.github/workflows/git-cicd-*.yml`, which covers the files of triggers still to
come; the tool's own files are protected. (A repository first installed before
this pattern keeps the editable list it was registered with; its install pull
requests regenerate the workflows from the install branch, which the check
lets through.)

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
  `GITHUB_TOKEN` and `VENDOR_PAT` passed through unchanged when they are set.

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
| `generate` / `verify` | write / check the generated workflows (`.github/workflows/git-cicd-open.yml`, `.github/workflows/git-cicd-merge.yml`, `.github/workflows/git-cicd-manual.yml`, and `.github/workflows/git-cicd-cron.yml` when a job has `cron` in `on`); `generate` removes, and `verify` fails on, the old `.github/workflows/git-cicd.yml` |
| `report --decisions FILE --results DIR [--trigger open\|merge\|cron\|manual] [--verdict-out PATH]` | the report and verdict from `decide --json` and `run-job --result` files; `--verdict-out` writes the status state (`success`/`failure`) and description, one per line (on cron one line per branch head: `<sha> TAB <state> TAB <description>`) |
| `check […]` | the local command above |

## Not built yet

- Secrets beyond `GITHUB_TOKEN` and `VENDOR_PAT`.
- An image or runtime per job.

## Developing git-cicd

git-cicd checks, releases and updates itself with itself. Its workflows run
the root `./git-cicd`, so CI tests the code in the pull request. Its own
config declares four jobs, one per trigger:

| Job | Row | Trigger | Script | What |
|---|---|---|---|---|
| `test` | `Open / Unit Tests / git-cicd:test` | `open`, every branch, `paths` the code | `ci/setup.sh`, `ci/test.sh` | setup installs pytest, pytest-cov and coverage (7.10 or later) for the Python floor (`>=3.11` in `pyproject.toml`), and bats-core when `bats` is not on PATH; the step runs the pytest suite, prints the line coverage of `git-cicd` with its missing lines and fails below 99%, then runs the bats tests of `install.sh` and the `ci/` scripts (`tests/bats/`) |
| `vendor-check` | `Open / Check Vendor Files / git-cicd:vendor-check` | `open`, every branch | `ci/vendor-check.sh` | `python3 .vendored/check --base "$CICD_BASE"`; it sets `GITHUB_HEAD_REF` from `CICD_SOURCE_BRANCH` when unset, so a local `check` lets `chore/install-*` branches through like Actions does |
| `release` | `Merge / Release / git-cicd:release` | `merge` on `main`; by hand with the inputs `bump_type` (patch, minor, major; default patch), `subdirectory`, `changelog_description` | `ci/release.sh` | git-semver's `release`: `publish` when the landed commit's subject starts with `chore: bump version`, nothing for `chore: install`, otherwise `bump` (and `bump` on a manual run); it gives `release` `GITHUB_EVENT_NAME`, `GITHUB_EVENT_BEFORE`, `INPUT_BUMP_TYPE`, `INPUT_SUBDIRECTORY`, `INPUT_CHANGELOG_DESCRIPTION` and `GH_TOKEN` |
| `update-vendored` | `Cron / Install Vendored / git-cicd:update-vendored` | `cron` `0 9 * * 1` on `main`; by hand with the inputs `vendor` (default all), `version` (default latest), `private` (true or false; default false) | `ci/update-vendored.sh` | `python3 .vendored/install <vendor> --version <version> --pr --deps=install` (plus `--private`), with `GH_TOKEN` set to `VENDOR_PAT` when set, else `GITHUB_TOKEN`; only CI runs it |

`release` has no `paths`, so a push that changes only `needs_nothing` files
does not release, while a `chore: bump version` commit still publishes
(`VERSION` is in no job's `paths` and not in `needs_nothing`). Start a
release or an update by hand from the Actions tab: **Manual**, *Run
workflow* on `main`, job `release` (inputs for example
`{"bump_type": "minor"}`) or `update-vendored` (for example
`{"vendor": "mangimangi/git-semver"}`).

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
