---
name: annotate-assignment
description: Append a note to the Friction journal section of an epic's orchestrator doc
model: sonnet
effort: medium
argument-hint: epic-id note text
---

Resolve the path `.pearls/docs/epics/$0/orchestrator.md`.

If the orchestrator file does not exist, error: "Orchestrator doc not found at `.pearls/docs/epics/$0/orchestrator.md`."

If a `## Friction journal` heading exists in the file, append `$1` at the end of that section — directly before the next `##` heading, or at end of file if Friction journal is the last section.

If no `## Friction journal` heading exists, append a new `## Friction journal` section at the bottom of the file (preceded by a blank line) with `$1` below it.

Content appended is free-form text — do not prescribe any format beyond placing it under the heading.

After the append, commit and push:

```
git add .pearls/docs/epics/$0/orchestrator.md
git commit -m "docs: annotate $0"
git push
```
