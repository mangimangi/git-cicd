---
name: archive-epic
description: Archive a closed epic and its closed descendants
parameters:
  epic_id:
    required: true
    description: Epic ID to archive
    hint: "epic-id"
---

Archive the epic. `prl archive` moves the epic and all its descendants to `.pearls/archive/<epic-id>.jsonl`. It refuses (exit 1) while the epic or any descendant is not closed, and lists them; if it refuses, report the error and stop.

```
prl archive $epic_id
```

Commit and push:

```
git add .pearls/issues.jsonl .pearls/archive/
git commit -m "pearls: archive $epic_id"
git push
```
