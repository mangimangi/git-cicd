---
name: manage-deps
description: Add or remove a dependency between two issues
argument-hint: add|remove issue-id other-issue-id dep-type
---

Add or remove a dependency between two issues. All four arguments are required. With `dep_type` `blocked_by` the command reads "issue is blocked by target".

```
prl dep $0 $1 $2 --type $3
```

Commit and push:

```
git add .pearls/issues.jsonl
git commit -m "pearls: dep $0 $1"
git push
```

Variant — listing dependencies changes nothing and takes only the issue ID. It is a different command that the caller runs directly:

```
prl dep list <issue-id>
```
