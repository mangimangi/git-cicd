# git-cicd — Agent Context

git-cicd is a vendored tool that decides which of a repository's jobs a change
needs, runs them and reports one verdict. It is a single Python 3 file,
`git-cicd`, at the repository root (standard library and git only), plus
`install.sh` and `templates/` for installing it through git-vendored. The
interface it implements is described in `README.md`.

## Running the checks

The checks run with the tool itself, the same way CI runs them:

```bash
./git-cicd check --setup   # the first time: ci/setup.sh installs pytest and coverage for the Python floor (3.11), and bats
./git-cicd check           # afterwards
```

`check` compares the current branch against its target (upstream, else
`origin/HEAD`, else `main`), runs the needed jobs one after another and exits
non-zero on a failed verdict. Run a single job with `--job test`.
The `test` job measures line coverage of `git-cicd`, including the runs tests
start as subprocesses (`pyproject.toml` `[tool.coverage]`), and prints one
`git-cicd` row with the missing lines. It fails below 99% line coverage of
`git-cicd` (`fail_under` in `pyproject.toml`): a change that lowers coverage
below 99% fails the verdict and adds its tests in the same pull request. A
line is excluded (`# pragma: no cover`) only when no test can reach it, with a
comment on that line saying why. In CI the step fails when pytest-cov is
missing; locally without `--setup` it runs and says coverage was not checked.
After pytest the job runs the bats tests of `install.sh` and the `ci/`
scripts (`tests/bats/`); either failing fails the step. Setup installs
bats-core (pinned, into `${XDG_CACHE_HOME:-~/.cache}/git-cicd/bats`) when
`bats` is not on PATH; without it the step fails in CI and, locally, says how
to install it.

After changing `.vendored/configs/git-cicd.json` or a template under
`templates/workflows/`, run `./git-cicd generate` and commit the generated
workflows (`.github/workflows/git-cicd-<trigger>.yml`, one per trigger;
`git-cicd-open.yml`, `git-cicd-merge.yml`, `git-cicd-cron.yml` and `git-cicd-manual.yml`; the cron file exists only while a job has `cron` in `on`); the verdict fails while they disagree.

## This repository's jobs

`.vendored/configs/git-cicd.json` declares four jobs: `test` (`open`; the
pytest suite), `vendor-check` (`open`; `ci/vendor-check.sh` runs
`.vendored/check`), `release` (`merge` on `main`; `ci/release.sh` bumps or
publishes with git-semver's `release`) and `update-vendored` (`cron`
`0 9 * * 1` on `main`; `ci/update-vendored.sh` runs `.vendored/install`).
Only CI runs `release` and `update-vendored`. The owner starts either by hand
from the Actions tab: **Manual**, *Run workflow* on `main`, job `release` or
`update-vendored`, and the `inputs` field as JSON (for example
`{"bump_type": "minor"}` or `{"vendor": "mangimangi/git-semver"}`; empty for
the defaults).

The old vendor workflows (`version-bump.yml`, `check-vendor.yml`,
`install-vendored.yml`) are removed from this repository; these jobs replace
them.

## Vendored tools

This repository's own vendored tools (git-vendored and git-semver, under
`.vendored/`) are updated only by the `update-vendored` job: the owner runs it
from the Actions tab (**Manual**, job `update-vendored`), and its weekly
schedule updates them too; each update arrives as a pull request from
`chore/install-<vendor>`. git-vendored itself came once from its documented
bootstrap. Adopting repositories install and upgrade git-cicd the same way
(`README.md`, "Installing").

A session never adds, changes, copies or deletes a vendor-protected file
(anything under `.vendored/` that a vendor protects, and the workflows the
vendors install), and never runs `.vendored/install` by hand: the Check Vendor
Files job rejects such changes from any branch but the vendor's install
branch. When a task needs a vendored tool installed or upgraded, the session
finishes everything else, then stops and says so (`madp stop "<question>"`),
leaving the workflow run to the owner. The editable vendor configs under
`.vendored/configs/` (each vendor's `_vendor.allowed`) may be changed.
Before finishing, run `python3 .vendored/check --base origin/<pr-target>` and
undo anything it reports.

## Layout

- `git-cicd` — the tool (validate, decide, run-job, generate, verify, report, check)
- `templates/workflows/<trigger>.yml` — the workflow templates, one per generated trigger (`open.yml`); `templates/config.json`, `templates/config.schema` — installed config and schema
- `install.sh` — the git-vendored installer
- `ci/` — this repository's own job scripts (`setup.sh`, `test.sh`, `vendor-check.sh`, `release.sh`, `update-vendored.sh`); `.vendored/configs/git-cicd.json` — its own config
- `tests/` — pytest suite; `tests/bats/` — bats tests of `install.sh` and the `ci/` scripts (shared `helper.bash`)

## Planning and issues

Planning lives in `.pearls/docs/` (`epics/`, `ideas/`, `headaches/`,
`overview.md`). Issues live in `.pearls/issues.jsonl`; use the `prl` CLI
(`prl list`, `prl show <id>`).
