# git-cicd
git platform hooks for managing cicd

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
same report and verdict as the `git-cicd verdict` check.

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
| 1 | verdict FAILED (a blocking job failed or could not run, or the workflow does not match the config) |
| 2 | config or usage error, or a moment that is not built yet |
