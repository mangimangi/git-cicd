---
name: mark-issue-implemented
description: Mark an issue as implemented and record its commit SHA
parameters:
  issue_id:
    required: true
    description: Issue ID
    hint: "issue-id"
  commit:
    required: true
    description: SHA of the commit that implements the issue (must already exist on the current branch)
    hint: "commit-sha"
---

Mark the issue as implemented and record the commit that implements it. Run after committing the implementation.

```
prl impl $issue_id --commit $commit
```

`--commit` is required: prl never falls back to HEAD. The command fails if the commit does not exist or is not an ancestor of HEAD, or if the issue is not `in_progress`. If it fails, report the error and stop — do not retry with a different commit.

Commit and push the issue update:

```
git add .pearls/issues.jsonl
git commit -m "pearls: $issue_id implemented"
git push
```
