# git-cicd — Agent Context

git-cicd is a vendored tool that decides which of a repository's jobs a change
needs, runs them and reports one verdict. It is a single Python 3 file,
`git-cicd`, at the repository root (standard library and git only), plus
`install.sh` and `templates/` for installing it through git-vendored. The
interface it implements is described in `README.md`.

## Running the checks

The checks run with the tool itself, the same way CI runs them:

```bash
./git-cicd check --setup   # the first time: ci/setup.sh installs pytest for the Python floor (3.11)
./git-cicd check           # afterwards
```

`check` compares the current branch against its target (upstream, else
`origin/HEAD`, else `main`), runs the needed jobs one after another and exits
non-zero on a failed verdict. Run a single job with `--job test`.

After changing `.vendored/configs/git-cicd.json` or `templates/workflow.yml`,
run `./git-cicd generate` and commit `.github/workflows/git-cicd.yml`; the
verdict fails while they disagree.

## Vendored tools

This repository's own vendored tools (git-vendored and git-semver, under
`.vendored/` with their workflows in `.github/workflows/`) are updated only by
the owner running the **Install Vendored** workflow from the Actions tab (its
weekly schedule updates them too); each update arrives as a pull request from
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
- `templates/workflow.yml` — the workflow template; `templates/config.json`, `templates/config.schema` — installed config and schema
- `install.sh` — the git-vendored installer
- `ci/` — this repository's own job scripts; `.vendored/configs/git-cicd.json` — its own config
- `tests/` — pytest suite

## Planning and issues

Planning lives in `.pearls/docs/` (`epics/`, `ideas/`, `headaches/`,
`overview.md`). Issues live in `.pearls/issues.jsonl`; use the `prl` CLI
(`prl list`, `prl show <id>`).
