---
name: annotate-assignment
description: Append a note to the Friction journal section of an epic's orchestrator doc
parameters:
  epic_id:
    required: true
    description: Epic id whose orchestrator doc should be annotated
    hint: "epic-id"
  note:
    required: true
    description: Free-form note to append to the Friction journal section (free text — quote it)
    hint: "note text"
---

Resolve the path `.pearls/docs/epics/$epic_id/orchestrator.md`.

If the orchestrator file does not exist, error: "Orchestrator doc not found at `.pearls/docs/epics/$epic_id/orchestrator.md`."

If a `## Friction journal` heading exists in the file, append `$note` at the end of that section — directly before the next `##` heading, or at end of file if Friction journal is the last section.

If no `## Friction journal` heading exists, append a new `## Friction journal` section at the bottom of the file (preceded by a blank line) with `$note` below it.

Content appended is free-form text — do not prescribe any format beyond placing it under the heading.

After the append, commit and push:

```
git add .pearls/docs/epics/$epic_id/orchestrator.md
git commit -m "docs: annotate $epic_id"
git push
```
