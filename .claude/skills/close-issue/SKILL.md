---
name: close-issue
description: Close an evaluated issue, or an epic whose descendants are all closed
model: sonnet
effort: medium
context: fork
argument-hint: issue-id
---

Close the issue.

```
prl close $0
```

prl refuses (exit 1) when:

- the issue is already closed;
- a non-epic issue has no evaluation (an issue that passes `prl eval` is closed automatically, so this command is rarely needed for it);
- an epic still has a descendant that is not closed (they are listed).

If it refuses, report the error and stop. Do not work around it.

Variant — closing an issue that was never evaluated (duplicate, won't-do, obsolete). This is a different command that the caller runs directly, with the reason as one quoted argument; the reason is recorded on the issue as `closed_unevaluated`:

```
prl close <issue-id> --unevaluated "<reason>"
```

Commit and push:

```
git add .pearls/issues.jsonl
git commit -m "pearls: close $0"
git push
```

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
