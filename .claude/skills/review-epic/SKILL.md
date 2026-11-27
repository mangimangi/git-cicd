---
name: review-epic
description: Show an epic's full state — details, children, planning doc
argument-hint: epic-id
---

```
prl show $0
prl list --parent $0
```

If a planning doc exists at `.pearls/docs/epics/$0.md`, also display it.
