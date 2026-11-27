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
