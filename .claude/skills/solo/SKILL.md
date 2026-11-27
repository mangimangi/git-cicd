---
name: solo
description: Implement and evaluate a single issue end-to-end
argument-hint: issue-id
---

You have a single issue to complete end-to-end in this session. Read the issue, estimate it, implement the work, verify it meets acceptance criteria, then score it.

Steps:
1. Review the issue using `/review-issue $0`
2. Understand the scope and acceptance criteria
3. Estimate the issue using `/create-issue-estimate $0 <estimator-model-id> <implementer-model-id> <input-tokens> <output-tokens>`. All five arguments are required; both model ids are your own model id, and the token counts are positive integers
4. Run `/start-issue $0` to mark it in progress
5. Implement the changes
6. Commit your implementation:
   ```
   git add -A && git commit -m "implement $0: <short description>"
   ```
7. **MANDATORY: Run the repo's test suite and fix any failures before proceeding.** Discover the test command (bats, pytest, unittest, npm test, etc.) and run it. If tests fail, fix the code first and re-run — do not proceed to `/mark-issue-implemented` with failing tests.
   ```
   # Run whatever test command is appropriate for the project
   ```
8. Verify against acceptance criteria
9. Mark implemented via `/mark-issue-implemented $0 <commit-sha>`, where `<commit-sha>` is the full SHA of the implementation commit from step 6 (use the latest implementation commit if you committed fixes afterwards). Both arguments are required. This is mandatory — do not skip this step.
10. Score your work honestly against the acceptance criteria and the diff, then record the scores via `/create-issue-eval $0 <evaluator-model-id> "<name>=<score> <name>=<score> ..."`. Run `/list-eval-dimensions` first: the third argument is ONE quoted string with a `name=score` pair (integer 0-100) for every configured dimension. The skill only records what you pass; it does not evaluate

The issue auto-closes when all scores meet configured thresholds. If not auto-closed, fix and re-score.

11. Create a PR for the implementation branch via `madp pr create`. Push the branch first if needed (`git push -u origin <branch>`), then run `madp pr create --base "${MEDICI_PR_TARGET:-main}" --title "<title>" --body "<body>"` with a title that references the issue ID and short description, and a body that links to the issue and summarises the acceptance criteria. `MEDICI_PR_TARGET` is set by the dispatcher when this session is running under a workspace orchestrator; falling back to `main` makes the same command work in standalone runs. The PR is the deliverable — solo is not complete until it exists.

If you hit friction during solo, fire off a `/headache` inline and move on. If you spot an improvement opportunity, fire off an `/idea` inline. Do not list `.pearls/docs/headaches/` or `.pearls/docs/ideas/`, do not check for existing or similar entries, and do not deduplicate. Dedup happens later during triage.

**This is an automated session.** Nobody will answer a question, and a turn that simply ends is a success (exit 0). Never end your turn on a question or waiting for input: where the issue leaves a choice open, take the option that best meets its acceptance criteria and this repository's rules, state the choice and the reason in the PR body, and go on. If the issue cannot be completed at all (it contradicts itself or names code that does not exist), run `madp stop --mode solo "$0: <the blocking question>"` as your last action so the session ends as a failure with the question recorded.

## Calling the tracker skills

The tracker skills run in a separate context that cannot see this conversation. They receive only the arguments you pass, split on spaces, in order. Pass every argument, in the order shown, and put quotes around any argument that contains spaces. If a skill replies `MISSING ARGUMENT`, call it again with the full argument list; do not work around it by calling `prl` yourself.

## Completion criteria

You are done when the issue is estimated, implemented, verified against acceptance criteria, scored, committed, pushed, and a PR has been created via `madp pr create`. Do not ask what to do. Do not summarize the issue and wait. Implement it.
