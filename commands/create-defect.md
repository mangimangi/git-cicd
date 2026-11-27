---
name: create-defect
description: Create a defect issue linked to the original implementation
parameters:
  title:
    required: true
    description: Short description of the defect (free text — quote it)
    hint: "title text"
  body:
    required: true
    description: Defect details — what's wrong, where, what should happen (free text — quote it)
    hint: "description"
  defect_of:
    required: true
    description: Original issue ID this defect is about (must have a recorded commit)
    hint: "original-issue-id"
---

Create a defect issue linked to the original implementation issue. All three arguments are required, in this order: title, body, original issue ID. `title` and `body` are free text and must each be passed as one quoted argument.

```
prl create --type bug --defect-of $defect_of --title "$title" --body "$body"
```

The free-text arguments are data, not shell. When you run the command, pass each one in single quotes (escaping any single quote inside it as `'\''`) so that `$`, backticks and double quotes in the text are not interpreted by the shell.

prl outputs `Created <id>: <title>` — capture the ID.

Commit and push:

```
git add .pearls/issues.jsonl
git commit -m "pearls: create defect <id> for $defect_of"
git push
```
