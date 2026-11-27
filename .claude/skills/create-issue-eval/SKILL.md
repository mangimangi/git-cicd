---
name: create-issue-eval
description: Record evaluation scores the caller determined on an implemented issue
model: sonnet
effort: medium
context: fork
argument-hint: issue-id evaluator-model-id "name=score name=score ..."
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
prl eval $0 --evaluator $1 --scores "$2"
```

The last line of the output is the verdict — report it verbatim:

- `RESULT: PASS (closed)` — every dimension met its threshold; the issue was closed.
- `RESULT: FAIL (below threshold: <dim>=<score> < <threshold>, ...)` — recorded, issue left `implemented` (exit code is still 0).

If prl exits non-zero nothing was recorded: report the error and stop.

Commit and push:

```
git add .pearls/issues.jsonl
git commit -m "pearls: eval $0"
git push
```

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
