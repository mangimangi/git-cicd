---
name: create-issue-eval
description: Record evaluation scores the caller determined on an implemented issue
parameters:
  issue_id:
    required: true
    description: Issue ID that was evaluated
    hint: "issue-id"
  evaluator:
    required: true
    description: Full model ID of the model that did the evaluation
    hint: "evaluator-model-id"
  scores:
    required: true
    description: One quoted string of space-separated name=int pairs (0-100), one pair for every configured dimension — quote it
    hint: "\"name=score name=score ...\""
---

Record the scores the caller determined. Do not change, add or invent scores. This command only records: the evaluation itself (reading the diff, deciding the scores) is done by the caller before invoking it.

`scores` must contain exactly one `name=int` pair for every configured dimension (`prl eval --list-dimensions` prints them with their thresholds). prl rejects a missing dimension, an unknown dimension, a duplicate, or a placeholder evaluator.

Configured dimensions:
- correctness: Does it work as specified?
- completeness: Are all acceptance criteria met?
- quality: Is it clean, maintainable, well-structured?
- testing: Are changes adequately tested?
- documentation: Are changes documented where needed?
- hygiene: No build artifacts, generated files, secrets, credentials, or large binary blobs in the diff.

Run:

```
prl eval $issue_id --evaluator $evaluator --scores "$scores"
```

The last line of the output is the verdict — report it verbatim:

- `RESULT: PASS (closed)` — every dimension met its threshold; the issue was closed.
- `RESULT: FAIL (below threshold: <dim>=<score> < <threshold>, ...)` — recorded, issue left `implemented` (exit code is still 0).

If prl exits non-zero nothing was recorded: report the error and stop.

Commit and push:

```
git add .pearls/issues.jsonl
git commit -m "pearls: eval $issue_id"
git push
```
