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

What is built today: the whole interface is validated, and the `open` moment
(pull requests) and local runs execute. The `merge` and `cron` moments and
manual runs validate in a config and are reported as **not built yet** when
asked to run (exit 2); they are never silently ignored. See
[Not built yet](#not-built-yet).

## Files

| Path | Owner | What |
|---|---|---|
| `.vendored/configs/git-cicd.json` | the repository | the config: jobs, `needs_nothing`, `max_parallel` |
| `.github/workflows/git-cicd-<moment>.yml` | generated | the GitHub Actions workflows, one per moment (`git-cicd-open.yml` today); generated, committed |
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
| `on` | array of `open`, `merge`, `cron` | `[]` | the moments the job runs at; several allowed, no duplicates; none means manual-only |
| `branches` | non-empty array of patterns | **required** | target branches the job runs for (`main`, `plan/**`, `**`). For a job with `cron` in `on`, literal branch names only (no `*`, `?`, `[`) |
| `paths` | array of patterns | none | the files that affect the job |
| `setup` | one repository path | none | the job's own setup script |
| `steps` | non-empty ordered array | **required** | each step is a file (`"ci/test.sh"`) or a file plus fixed arguments (`["ci/test.sh", "--fast"]`), run directly, never through a shell |
| `cron` | five-field cron expression | | required when `on` contains `cron`, refused otherwise |
| `manual` | boolean | `true` | the job can be run by hand |
| `blocking` | boolean | `true` | `false` makes the job non-blocking: its failure is reported and does not fail the verdict |

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
- A change affects **every** `open` job whose `branches` match when it touches
  the git-cicd config or any script any job names (setup or step, whatever
  the job's moments); when a changed file is in no job's `paths` and not in
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
| `CICD_MOMENT` | the moment (`open`) |
| `CICD_JOB` | the job name |
| `CICD_TARGET_BRANCH` | the target branch (the pull request's base) |
| `CICD_SOURCE_BRANCH` | the source branch (the pull request's head; what `.vendored/check` needs to let install branches through) |
| `CICD_BASE` | the base commit |
| `CICD_HEAD` | the head commit |
| `CICD_CHANGED_FILES` | absolute path of a file listing the changed files, one per line |

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
- Facts about the change (branch names, commits, the changed files) reach a
  script only as environment variables or a file. The generated workflow
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
| `Report / git-cicd:report` | collects the results, writes the report, posts the final status | check run (a job) |
| `Verdict / git-cicd:verdict` | the verdict: **the one object a reader waits on** | commit status |

git-cicd owns its own three; a config job's row has the job's display name
(its job name in title case when it has none) and `<repo>`, the name of the
repository the workflow runs in. GitHub shows a check run after its
workflow's name, which is the moment's (`Open / Unit Tests / medici:unit-tests`,
`Open / Decide / git-cicd:decide`); a status has no workflow and shows as
`Verdict / git-cicd:verdict`. No row or status name carries a version: it is
what branch protection and anything else that waits on a check refers to, and
it does not change when a tool is upgraded.

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

git-cicd generates **one workflow per moment**, each its own file with its
own trigger, its own permissions (at the top level or per job) and its own
overlap rule, and each named for its moment, so a row reads
`Open / Unit Tests / medici:unit-tests`:

| Moment | Workflow name | File | Generated |
|---|---|---|---|
| `open` | `Open` | `.github/workflows/git-cicd-open.yml` | yes |
| `merge` | `Merge` | `.github/workflows/git-cicd-merge.yml` | not yet |
| `cron` | `Cron` | `.github/workflows/git-cicd-cron.yml` | not yet |
| manual | `Manual` | `.github/workflows/git-cicd-manual.yml` | not yet |

The names and file names are fixed for good: when the other moments are
built, they add their files and change none. The names are the moment words
(not `CI`/`CD`): the config already says `"on": ["open"]`, and a moment is
not a kind of job.

`git-cicd generate` writes every generated file. **Every generated file is
fixed text except the cron workflow's schedule block** (one entry per distinct
cron expression in the config), and the tool path, which follows where
git-cicd is installed. Jobs are decided when a workflow runs, so two configs
that differ only in jobs that are not `cron` generate the same files.

The `open` workflow (`Open`):

- Trigger: `pull_request` (opened, synchronize, reopened), every target
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

**The generate/verify rule.** The platform's token cannot push workflow files,
so CI never regenerates. Whoever upgrades git-cicd or changes the config runs
`generate` and commits what it writes in the same pull request.
`git-cicd verify` regenerates every file in memory, compares each whole file,
and fails naming the command to run when one is missing or differs, or when
the old single file is still there; that catches a stale file and any hand
edit.

### Migrating from the single `git-cicd.yml`

git-cicd up to 0.0.2 generated one file, `.github/workflows/git-cicd.yml`, for
every moment. In a repository that still has it, `generate` writes
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
   the config when it is missing, and the regenerated per-moment workflows
   (`.github/workflows/git-cicd-open.yml`; on the first upgrade from the single
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
| `.vendored/pkg/git-cicd/templates/workflows/<moment>.yml` | the templates `generate` fills, one per generated moment | replaced |
| `.vendored/manifests/git-cicd.schema` | the config schema, for `.vendored/audit` | replaced |
| `.vendored/configs/git-cicd.json` | your config: the jobs | **created once**, only when missing; never overwritten |
| `.github/workflows/git-cicd-<moment>.yml` | the generated workflows | **regenerated on every install**, so an upgrade reaches them in the install pull request |

The default config declares no jobs (`"jobs": {}`, `"needs_nothing": []`), so
a fresh install validates and needs nothing until you declare jobs. The config
and the generated workflows are listed as editable (`_vendor.allowed`) for
git-vendored's check, the workflows as the pattern
`.github/workflows/git-cicd-*.yml`, which covers the files of moments still to
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

`check` decides which jobs the change needs (the `open` moment), runs the
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
| 2 | config or usage error, or a moment that is not built yet |

## Commands

| Command | What |
|---|---|
| `validate [--config PATH]` | load and validate the config: `config ok: N jobs` or every error |
| `decide --moment open --target B --source B --base SHA --head SHA [--json] [--changed-files-out PATH]` | one decision per declared job, with the reason; in Actions also writes `jobs`, `any`, `max_parallel` to `GITHUB_OUTPUT` |
| `run-job JOB --moment open --target … --head SHA [--setup] [--result PATH]` | setup when asked, then the steps; result JSON with the times |
| `generate` / `verify` | write / check the generated workflows (`.github/workflows/git-cicd-open.yml`); `generate` removes, and `verify` fails on, the old `.github/workflows/git-cicd.yml` |
| `report --decisions FILE --results DIR [--verdict-out PATH]` | the report and verdict from `decide --json` and `run-job --result` files; `--verdict-out` writes the status state (`success`/`failure`) and description, one per line |
| `check […]` | the local command above |

## Not built yet

- The `merge` and `cron` moments and manual runs: they validate, and
  `decide`/`run-job`/`report` exit 2 with `the <moment> moment is not built
  yet` when asked to run them. Their workflows (`Merge`, `Cron`, `Manual`) are
  not generated yet, so nothing triggers them; when they are built, each adds
  its own file under the name above, with its own trigger, permissions and
  overlap rule (`merge` queued, never cancelled), and changes no other file.
- Declared inputs for manual runs.
- Secrets beyond `GITHUB_TOKEN` and `VENDOR_PAT`.
- An image or runtime per job.

## Developing git-cicd

git-cicd checks itself with itself: its own config declares one job, `test`
(`ci/setup.sh` installs pytest for the Python floor, `>=3.11` in `pyproject.toml`;
`ci/test.sh` runs it), and its workflow runs the root `./git-cicd`, so CI
tests the code in the pull request.

```bash
./git-cicd check --setup     # the first time
./git-cicd check
```
