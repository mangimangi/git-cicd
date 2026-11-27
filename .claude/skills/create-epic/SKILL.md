---
name: create-epic
description: Create an epic in the pearls tracker
model: sonnet
effort: medium
context: fork
argument-hint: title text description
---

Create an epic using prl. Run from the repo's working directory. `title` and `body` are free text and must each be passed as one quoted argument.

```
prl create --type epic --title "$0" --body "$1"
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

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
