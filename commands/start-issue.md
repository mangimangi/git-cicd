---
name: start-issue
description: Mark an open issue as in progress
parameters:
  issue_id:
    required: true
    description: Issue ID to start
    hint: "issue-id"
---

Mark the issue as in progress before beginning implementation.

```
prl start $issue_id
```

This only works on an `open` issue. prl refuses (exit 1) if the issue is already `in_progress`, `implemented` or `closed`; report the error and stop.

Variant — restarting an issue that was already started, implemented or closed. This is a different command that the caller runs directly; it moves any recorded evaluation into `evaluation_history` so the old score cannot be reused:

```
prl start <issue-id> --reopen
```
