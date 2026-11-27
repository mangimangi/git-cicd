---
name: create-issue
description: Create a child issue under a parent in the pearls tracker
model: sonnet
effort: medium
context: fork
argument-hint: title text task|bug|feature|chore|epic parent-id description
---

Create an issue under its parent and push it in one step. Run from the repo's working directory. All four arguments are required; `title` and `body` are free text and must each be passed as one quoted argument.

```
prl create --push --title "$0" --type $1 --parent $2 --body "$3"
```

The free-text arguments are data, not shell. When you run the command, pass each one in single quotes (escaping any single quote inside it as `'\''`) so that `$`, backticks and double quotes in the text are not interpreted by the shell.

prl outputs `Created <id>: <title>` — echo the created issue ID for the caller.

Variant — top-level issue with no parent. This is a different command, not this one with an argument left out; the caller runs it directly:

```
prl create --push --title "<title>" --type <type> --body "<body>"
```

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
