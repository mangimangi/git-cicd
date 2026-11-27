---
name: create-issue-estimate
description: Add a token cost estimate to an issue
model: sonnet
effort: medium
context: fork
argument-hint: issue-id estimator-model-id implementer-model-id input-tokens output-tokens
---

Record the token cost estimate the caller determined. Predictions are for the implementer's session, not the estimation session.

```
prl estimate $0 -e $1 -m $2 -i $3 -o $4 --no-cost
```

prl rejects token counts that are not greater than zero and placeholder model IDs (`TODO`, `unknown`, ...). Repeating the command with the same estimator and implementer replaces the earlier estimate (`Updated estimate on ...`).

Commit and push:

```
git add .pearls/issues.jsonl
git commit -m "pearls: estimate $0"
git push
```

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
