---
name: create-issue
description: Create a child issue under a parent in the pearls tracker
parameters:
  title:
    required: true
    description: Issue title (free text — quote it)
    hint: "title text"
  type:
    required: true
    description: Issue type, one of task, bug, feature, chore, epic
    hint: "task|bug|feature|chore|epic"
  parent:
    required: true
    description: Parent issue or epic ID
    hint: "parent-id"
  body:
    required: true
    description: Issue body — acceptance criteria, scope, context (free text — quote it)
    hint: "description"
---

Create an issue under its parent and push it in one step. Run from the repo's working directory. All four arguments are required; `title` and `body` are free text and must each be passed as one quoted argument.

```
prl create --push --title "$title" --type $type --parent $parent --body "$body"
```

The free-text arguments are data, not shell. When you run the command, pass each one in single quotes (escaping any single quote inside it as `'\''`) so that `$`, backticks and double quotes in the text are not interpreted by the shell.

prl outputs `Created <id>: <title>` — echo the created issue ID for the caller.

Variant — top-level issue with no parent. This is a different command, not this one with an argument left out; the caller runs it directly:

```
prl create --push --title "<title>" --type <type> --body "<body>"
```
