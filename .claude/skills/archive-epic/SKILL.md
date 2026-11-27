---
name: archive-epic
description: Archive a closed epic and its closed descendants
model: sonnet
effort: medium
context: fork
argument-hint: epic-id
---

Archive the epic. `prl archive` moves the epic and all its descendants to `.pearls/archive/<epic-id>.jsonl`. It refuses (exit 1) while the epic or any descendant is not closed, and lists them; if it refuses, report the error and stop.

```
prl archive $0
```

Commit and push:

```
git add .pearls/issues.jsonl .pearls/archive/
git commit -m "pearls: archive $0"
git push
```

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
