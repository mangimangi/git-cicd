---
name: create-repo-planning-doc
description: Create a per-repo planning doc for a cross-repo epic
argument-hint: epic-id repo-name slug title text
---

Resolve the target path to `.pearls/docs/epics/$0/$1/$2.md`.

If the file already exists, error: "Repo planning doc already exists at `.pearls/docs/epics/$0/$1/$2.md`. Edit it directly."

Otherwise, ensure `.pearls/docs/epics/$0/$1/` exists (`mkdir -p`) and write the following template body to the target file:

```markdown
# $3

## This repo delivers

- <deliverable with acceptance criteria>

## Design decisions (settled)

- <what was decided and why — refine treats these as constraints>

## Cross-repo context (reference only — not this repo's scope)

- <what other repos handle>

## Implementation notes

- <file paths, patterns, gotchas the implement agent needs>
```

Commit and push:

```
mkdir -p .pearls/docs/epics/$0/$1
git add .pearls/docs/epics/$0/$1/$2.md
git commit -m "docs: plan $0/$1/$2"
git push
```
