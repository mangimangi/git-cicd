---
name: create-issue-estimate
description: Add a token cost estimate to an issue
parameters:
  issue_id:
    required: true
    description: Issue ID to estimate
    hint: "issue-id"
  estimator:
    required: true
    description: Full model ID of the model that produced the estimate
    hint: "estimator-model-id"
  implementer:
    required: true
    description: Full model ID of the model that will implement
    hint: "implementer-model-id"
  input_cost:
    required: true
    description: Predicted input tokens for the implementer (integer > 0)
    hint: "input-tokens"
  output_cost:
    required: true
    description: Predicted output tokens for the implementer (integer > 0)
    hint: "output-tokens"
---

Record the token cost estimate the caller determined. Predictions are for the implementer's session, not the estimation session.

```
prl estimate $issue_id -e $estimator -m $implementer -i $input_cost -o $output_cost --no-cost
```

prl rejects token counts that are not greater than zero and placeholder model IDs (`TODO`, `unknown`, ...). Repeating the command with the same estimator and implementer replaces the earlier estimate (`Updated estimate on ...`).

Commit and push:

```
git add .pearls/issues.jsonl
git commit -m "pearls: estimate $issue_id"
git push
```
