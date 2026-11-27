---
name: create-epic
description: Create an epic in the pearls tracker
parameters:
  title:
    required: true
    description: Epic title (free text — quote it)
    hint: "title text"
  body:
    required: true
    description: Epic body — problem, scope, acceptance criteria (free text — quote it)
    hint: "description"
---

Create an epic using prl. Run from the repo's working directory. `title` and `body` are free text and must each be passed as one quoted argument.

```
prl create --type epic --title "$title" --body "$body"
```

The free-text arguments are data, not shell. When you run the command, pass each one in single quotes (escaping any single quote inside it as `'\''`) so that `$`, backticks and double quotes in the text are not interpreted by the shell.

prl outputs `Created <id>: <title>` — capture the ID.

Commit and push, including the epic ID in the message:

```
git add .pearls/issues.jsonl
git commit -m "pearls: create epic <id>"
git push
```

Echo the created epic ID for the caller.
