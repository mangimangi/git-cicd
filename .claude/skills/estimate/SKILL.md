---
name: estimate
description: Estimate token cost for issues in an epic
argument-hint: epic-id
---

Estimate the open children of $0. For each issue, predict the input/output token cost the implementer will incur. Disregard any existing estimates — they are likely stale.

For each open child issue:
1. Read the issue body, acceptance criteria, and any referenced files
2. Predict input tokens (context the implementer will need to load) and output tokens (code, commits, issue updates the implementer will generate)
3. Add the estimate using `/create-issue-estimate <issue-id> <estimator-model-id> <implementer-model-id> <input-tokens> <output-tokens>`. All five arguments are required. `<estimator-model-id>` is your own model id; `<implementer-model-id>` is the model that will implement (use your own model id unless the issue or planning doc names another); the token counts are positive integers

**DO NOT commit code. DO NOT modify source files.** Your only writes should be estimates added via `/create-issue-estimate`. If the planning doc contains implementation guidance, that is context for the implement session — not for you.

## Calling the tracker skills

The tracker skills run in a separate context that cannot see this conversation. They receive only the arguments you pass, split on spaces, in order. Pass every argument, in the order shown, and put quotes around any argument that contains spaces. If a skill replies `MISSING ARGUMENT`, call it again with the full argument list; do not work around it by calling `prl` yourself.

## Completion criteria

You are done when all open children of $0 have estimates. Do not implement, evaluate, or modify any code — those are separate modes.
