---
name: review-issue
description: Show an issue's full details
argument-hint: issue-id
---

```
prl show $0
```

If the issue has any code references (`refs` field), show those files/commits too. For files larger than 200 lines, show the relevant section based on the ref's line range.
