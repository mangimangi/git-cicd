---
name: archive-scope-doc
description: Move a scope doc to the archive directory
parameters:
  epic_id:
    required: true
    description: Epic ID whose scope doc should be archived
    hint: "epic-id"
---

Move the scope doc to `.pearls/docs/epics/.archive/$epic_id.md`:

```
mkdir -p .pearls/docs/epics/.archive
git mv .pearls/docs/epics/$epic_id.md .pearls/docs/epics/.archive/$epic_id.md
```

Commit and push:

```
git commit -m "docs: archive scope $epic_id"
git push
```

If the scope doc doesn't exist, skip without error.
