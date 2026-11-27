---
name: close-issue
description: Close an evaluated issue, or an epic whose descendants are all closed
parameters:
  issue_id:
    required: true
    description: Issue ID to close
    hint: "issue-id"
---

Close the issue.

```
prl close $issue_id
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
git commit -m "pearls: close $issue_id"
git push
```
