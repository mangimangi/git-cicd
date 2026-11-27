---
name: review-issue
description: Show an issue's full details
parameters:
  issue_id:
    required: true
    description: Issue ID to review
    hint: "issue-id"
---

```
prl show $issue_id
```

If the issue has any code references (`refs` field), show those files/commits too. For files larger than 200 lines, show the relevant section based on the ref's line range.
