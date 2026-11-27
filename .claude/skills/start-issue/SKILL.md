---
name: start-issue
description: Mark an open issue as in progress
model: sonnet
effort: medium
context: fork
argument-hint: issue-id
---

Mark the issue as in progress before beginning implementation.

```
prl start $0
```

This only works on an `open` issue. prl refuses (exit 1) if the issue is already `in_progress`, `implemented` or `closed`; report the error and stop.

Variant — restarting an issue that was already started, implemented or closed. This is a different command that the caller runs directly; it moves any recorded evaluation into `evaluation_history` so the old score cannot be reused:

```
prl start <issue-id> --reopen
```

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
