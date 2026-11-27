---
name: manage-deps
description: Add or remove a dependency between two issues
parameters:
  action:
    required: true
    description: "Action to perform: add or remove"
    hint: "add|remove"
  issue_id:
    required: true
    description: Issue ID the dependency is recorded on
    hint: "issue-id"
  target_id:
    required: true
    description: Other issue ID (the blocker for blocked_by, or the target for other types)
    hint: "other-issue-id"
  dep_type:
    required: true
    description: "Dependency type, one of: blocked_by, blocks, precedes, follows, relates_to, duplicates, duplicated_by, implements, implemented_by, causes, caused_by"
    hint: "dep-type"
---

Add or remove a dependency between two issues. All four arguments are required. With `dep_type` `blocked_by` the command reads "issue is blocked by target".

```
prl dep $action $issue_id $target_id --type $dep_type
```

Commit and push:

```
git add .pearls/issues.jsonl
git commit -m "pearls: dep $action $issue_id"
git push
```

Variant — listing dependencies changes nothing and takes only the issue ID. It is a different command that the caller runs directly:

```
prl dep list <issue-id>
```
