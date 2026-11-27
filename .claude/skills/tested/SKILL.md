---
name: tested
description: Bootstrap test coverage up to a target threshold and enforce it in CI
model: opus
effort: high
argument-hint: percentage
---

Bootstrap test coverage up to `$0`% and wire a CI workflow to enforce it on PRs to main.

Steps:

1. Read AGENTS.md README.md docs/ for repo orientation. Detect the language(s) in use and any existing test setup (test runner, coverage tool, existing workflows).
2. If multiple languages are present, suggest a coverage tool and methodology for each, then pick one language to drive the `$0` threshold (the one holding the most lines of code or the primary application language).
3. Measure current coverage. Write tests until measured coverage ≥ `$0`%. The percentage is a floor, not the goal: the goal is tests that fail when the code is wrong. Prioritize by risk first (gates, validators, anything that decides pass/fail, writes or merges records, or exits non-zero), then by size.
   Every test you add must:
   - Assert an outcome a user or caller depends on: return value, file or record contents, exit code, or the exact output line another tool parses. A test that only checks "a mock was called", "no exception", or "result is not None" does not count.
   - For an error path, assert the exit code and the message, not just that it exited.
   - Mock only what leaves the process (network, Docker, the clock). Use a real temp directory and a real git repo instead of mocking the filesystem or git.
   Never raise the number by excluding code: no `# pragma: no cover`, no `omit`, no narrowing of the measured source. If something truly cannot be tested, leave it uncovered and say so in the final report.
   Never edit vendored or generated files (`.vendored/`, generated command files).
4. Check the tests, not just the number. Pick at least 15 lines your new tests cover, spread across the modules you touched, and favouring conditions, returns and error exits. For each: break the line (flip the condition, change the returned value or exit code, delete the call), run the suite, confirm a test fails, restore the line. If nothing fails, fix the test and try again. Leave the source exactly as you found it (`git diff` on non-test files must be empty apart from intended changes). Report the tally as `MUTATION CHECK: <caught>/<tried>` with any line you could not get a test to catch.
5. Add (or extend) a GitHub Actions workflow at `.github/workflows/coverage.yml` that:
   - Runs on PRs targeting `main`.
   - Runs the test suite with coverage.
   - Fails the job if coverage drops below `$0`%.
6. One commit per logical batch — per module or area you added tests for, plus the GHA workflow as its own commit. Do not bundle unrelated test additions and the workflow change into one commit.
7. Push when done.

## Completion criteria

You are done when measured coverage is ≥ `$0`%, the mutation check has been run and reported, a PR-gating GHA workflow enforcing that threshold is committed, and all changes are pushed. Do not ask what to do. Do not survey coverage and wait. Write the tests and wire the workflow.
