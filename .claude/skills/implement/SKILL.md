---
name: implement
description: Implement the open children of an epic
argument-hint: epic-id
---

Implement all open children of $0 — tasks, bugs, and defects alike. Leave the epic open when finished — eval and cleanup are separate modes.

**Carry forward all concrete details from input docs (issue bodies, planning docs, idea docs, headache docs).** You may add clarity but never drop or summarize away details — specific code references, paths, function names, line numbers, and implementation caveats called out upstream MUST be respected in the implementation. Re-validate concrete code references against current code before relying on them; if a reference is stale, fix it rather than working around it.

For each open child issue, in dependency order:
1. Read the issue body and acceptance criteria. Run `/start-issue <issue-id>` to mark it in progress.
2. Implement the changes
3. Commit with a descriptive message:
   ```
   git add -A && git commit -m "implement <issue-id>: <short description>"
   ```
4. Run the test suite and fix any failures before proceeding:
   ```
   # Run whatever test command is appropriate for the project
   ```
5. **MANDATORY: Mark implemented via `/mark-issue-implemented <issue-id> <commit-sha>`.** Both arguments are required. `<commit-sha>` is the full SHA of the commit from step 3 (`git rev-parse HEAD` immediately after that commit); the tracker rejects a commit that does not exist or is not on this branch. Never skip this step — not when low on context, not when the task felt trivial, not when batching multiple issues. An issue that isn't marked implemented leaves the child in an incomplete state and blocks the walker.

Implement **all** children of $0 in this session, in dependency order, in one pass. Implement in parallel when possible. Continue until every child is either implemented or explicitly blocked.

Do not batch all issues into one commit — one commit per child issue, traceable to the issue ID.

**This is an automated session.** Nobody will answer a question, and a turn that simply ends is a success (exit 0). Never end your turn on a question or waiting for input: where an issue leaves a choice open, take the option that best meets its acceptance criteria and this repository's rules, note the choice and the reason in the commit message, and go on. If a child is genuinely blocked (its issue contradicts itself or names code that does not exist), finish every other child first, then run `madp stop --mode implement "<child id>: <the blocking question>"` as your last action so the session ends as a failure with the question recorded.

If you hit friction during implementation, fire off a `/headache` inline and move on. If you spot an improvement opportunity, fire off an `/idea` inline. Do not list `.pearls/docs/headaches/` or `.pearls/docs/ideas/`, do not check for existing or similar entries, and do not deduplicate. Dedup happens later during triage.

## Calling the tracker skills

The tracker skills run in a separate context that cannot see this conversation. They receive only the arguments you pass, split on spaces, in order. Pass every argument, in the order shown, and put quotes around any argument that contains spaces. If a skill replies `MISSING ARGUMENT`, call it again with the full argument list; do not work around it by calling `prl` yourself.

## Completion criteria

You are done when all open children of $0 — tasks, bugs, and defects — are marked implemented via `/mark-issue-implemented`. An unmarked child is not complete — return and run `/mark-issue-implemented` for any child that is missing the mark before ending the session. Do not evaluate, score, estimate, or close the epic — those are separate modes.
