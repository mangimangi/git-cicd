---
name: mark-issue-implemented
description: Mark an issue as implemented and record its commit SHA
model: sonnet
effort: medium
context: fork
argument-hint: issue-id commit-sha
---

Mark the issue as implemented and record the commit that implements it. Run after committing the implementation.

```
prl impl $0 --commit $1
```

`--commit` is required: prl never falls back to HEAD. The command fails if the commit does not exist or is not an ancestor of HEAD, or if the issue is not `in_progress`. If it fails, report the error and stop — do not retry with a different commit.

Commit and push the issue update:

```
git add .pearls/issues.jsonl
git commit -m "pearls: $0 implemented"
git push
```

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
