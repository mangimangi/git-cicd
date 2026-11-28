# git-cicd: test coverage is measured for the tool and enforced at 99%

> Unit 7 of plan `git-dev-883c` (record: `mangimangi/git-dev`, `.pearls/docs/epics/git-dev-883c.md`). Added to the plan by the owner on 2026-11-28. Delivers into `plan/git-dev-883c`. Re-check every figure and code reference against the code before using it.

## Problem

The owner, 2026-11-28: "we need 99 test coverage for all of these tool repos using bats or pytest right? these are core tooling and they need to be safe and not regress".

git-cicd decides which of a repository's jobs run and reports the one verdict every consumer waits on. Today nothing fails when its tests stop reaching part of it:

- `ci/test.sh` runs pytest with `--cov --cov-report=term-missing --cov-config=pyproject.toml` when pytest-cov is present; `pyproject.toml` has `[tool.coverage.run] include = ["git-cicd"]` and no threshold.
- Measured by the planning session on `main` at v0.0.4 (2026-11-28, 373 tests passing): `git-cicd` 63% of 1,136 statements. That run counts only code executed in the test process; a test that starts `./git-cicd` as a subprocess is not counted, so the figure understates what the tests reach, and nothing says by how much.
- The shell scripts are not measured and have no bats tests: `install.sh` and the job scripts under `ci/` (`setup.sh`, `test.sh`, `release.sh`, `vendor-check.sh`, `update-vendored.sh`). `ci/release.sh` decides between bump and publish for this repository's own release.
- The generated workflows (`templates/workflows/*.yml`) hold shell in their `run:` blocks; the existing tests check them as text.

## What already was decided (do not reopen)

- The threshold is 99% line coverage of `git-cicd`, enforced: the `test` job fails below it.
- Shell scripts get bats tests for each behaviour, run by the `test` job, with no numeric threshold (agreed 2026-11-28).
- Gaps are closed with real tests. A line is excluded only when no test can reach it, with a comment on the line saying why.
- The checks run with the tool itself (`./git-cicd check`), on the Python floor (`>=3.11`); no Python version is written in a workflow.
- No vendor-protected file is added, changed or deleted. Run `python3 .vendored/check --base origin/plan/git-dev-883c` before finishing.
- The interface (README) does not change in this unit.

## What ships

- Coverage is measured honestly, including subprocess runs
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `pyproject.toml` (`[tool.coverage.run]`, `[tool.coverage.report]`), `ci/setup.sh`, `ci/test.sh`, `tests/conftest.py`, `AGENTS.md`, `README.md` ("Developing git-cicd")
  - shape: The `test` job measures line coverage of `git-cicd` and counts runs that a test starts as a subprocess, so the figure is what the tests really execute; it prints the report with the missing lines. A local `./git-cicd check` gives the same figure as CI. This issue ends with the true figure in the pull request description; no threshold yet if it is below 99%.

- The gaps are closed to 99%
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `tests/` (new and extended test files), and `git-cicd` only where a line is provably unreachable or a defect is found
  - shape: Tests are added until `git-cicd` is at 99% or more. They exercise behaviour a consumer relies on: every validation error with its message, every decision and its reason on each trigger (`open`, `merge`, `cron`, manual), declared inputs, `run-job` results including a failing setup and a failing step, `generate` and `verify` for each generated file, `report` and the verdict line for every outcome, `check` and its defaults, and every exit code. A defect a new test exposes is fixed with the test that shows it and named in the pull request; any other behaviour change is out of scope.

- The threshold is enforced
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `pyproject.toml` (`fail_under`), `ci/test.sh`, `AGENTS.md`, `README.md`
  - shape: The `test` job fails when coverage of `git-cicd` is below 99%, with the report showing the lines. The docs state the rule: a change that lowers coverage below 99% fails the verdict and adds its tests in the same pull request.

- The shell scripts have bats tests
  - vehicle: type: issue
  - source repo: git-cicd
  - target repo: git-cicd
  - affected surface: `tests/` (bats files), `ci/setup.sh`, `ci/test.sh`, `.vendored/configs/git-cicd.json` (`paths` of the `test` job), `AGENTS.md`
  - shape: `install.sh` and each script under `ci/` have bats tests covering every behaviour: for `ci/release.sh` each case of its decision (manual run, bump commit, install commit, any other merge, any other trigger) and the environment it hands to git-semver's `release`; for `ci/update-vendored.sh` that inputs reach `.vendored/install` as arguments and never through a shell; for `ci/vendor-check.sh` the source branch it passes on; for `install.sh` what is written where on a first install and on an upgrade. They run in the `test` job (setup installs bats; no network) and locally through `./git-cicd check`. A failing bats test fails the job.

## Acceptance criteria

- `./git-cicd check --setup` passes in a clean checkout and prints a coverage report with `git-cicd` at 99% or more.
- Removing a test file makes the `test` job and the verdict fail; shown once in the pull request description.
- Subprocess runs are counted, shown by the figure before and after the measurement change in the first issue's pull request description.
- Every exclusion carries a comment with its reason; the pull request lists them.
- The bats tests run in the `test` job and cover `install.sh` and each `ci/` script.
- `./git-cicd verify` passes; the generated workflows are unchanged.
- The pull request into `plan/git-dev-883c` has a passing `Verdict / git-cicd:verdict`.
- `python3 .vendored/check --base origin/plan/git-dev-883c` reports nothing.

## Out of scope

- Any change to the interface, the generated workflows or the tool's behaviour beyond fixing a defect a new test exposes (`gcd-4674` and the generated-workflows manifest issue follow this unit).
- A coverage figure for shell scripts.
- Anything in git-semver or git-vendored.
