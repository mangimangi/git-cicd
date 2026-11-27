---
name: archive-scope-doc
description: Move a scope doc to the archive directory
model: sonnet
effort: medium
context: fork
argument-hint: epic-id
---

Move the scope doc to `.pearls/docs/epics/.archive/$0.md`:

```
mkdir -p .pearls/docs/epics/.archive
git mv .pearls/docs/epics/$0.md .pearls/docs/epics/.archive/$0.md
```

Commit and push:

```
git commit -m "docs: archive scope $0"
git push
```

If the scope doc doesn't exist, skip without error.

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
