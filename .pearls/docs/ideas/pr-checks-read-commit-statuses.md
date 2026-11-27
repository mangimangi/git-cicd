# PR checks readers should also read commit statuses

> Captured: 2026-11-27

## Context

Solo on gcd-f8eb (git-cicd PR #5). `git-cicd verdict` became a commit status, set to pending by the first step of the first job and to the verdict by the last step of `git-cicd report`, so it is present and pending from the start of the run. While gathering the platform evidence I saw that `madp pr checks 5` listed only check runs (`git-cicd decide`, `test`, `check`) and never the `git-cicd verdict` status.

## Idea

madp pr checks lists only check runs, not commit statuses, so it never shows the git-cicd verdict status (now a commit status, gcd-f8eb). madp pr checks and medici's walker should also read GET /commits/{sha}/status or statusCheckRollup and treat an absent or pending git-cicd verdict as pending.
