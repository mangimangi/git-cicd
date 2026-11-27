---
name: review-epic
description: Show an epic's full state — details, children, planning doc
parameters:
  epic_id:
    required: true
    description: Epic ID to review
    hint: "epic-id"
---

```
prl show $epic_id
prl list --parent $epic_id
```

If a planning doc exists at `.pearls/docs/epics/$epic_id.md`, also display it.
