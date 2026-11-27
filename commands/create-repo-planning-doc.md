---
name: create-repo-planning-doc
description: Create a per-repo planning doc for a cross-repo epic
parameters:
  epic_id:
    required: true
    description: Epic id this planning doc belongs to
    hint: "epic-id"
  repo:
    required: true
    description: Repo name (subdirectory under the epic doc tree)
    hint: "repo-name"
  slug:
    required: true
    description: Filename slug for this planning doc
    hint: "slug"
  title:
    required: true
    description: Planning doc title (free text — quote it)
    hint: "title text"
---

Resolve the target path to `.pearls/docs/epics/$epic_id/$repo/$slug.md`.

If the file already exists, error: "Repo planning doc already exists at `.pearls/docs/epics/$epic_id/$repo/$slug.md`. Edit it directly."

Otherwise, ensure `.pearls/docs/epics/$epic_id/$repo/` exists (`mkdir -p`) and write the following template body to the target file:

```markdown
# $title

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
mkdir -p .pearls/docs/epics/$epic_id/$repo
git add .pearls/docs/epics/$epic_id/$repo/$slug.md
git commit -m "docs: plan $epic_id/$repo/$slug"
git push
```
