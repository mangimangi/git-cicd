---
name: create-scope-doc
description: Create a scope doc for an epic
parameters:
  epic_id:
    required: true
    description: Epic ID this scope doc is for
    hint: "epic-id"
  title:
    required: true
    description: Scope doc title (free text — quote it)
    hint: "title text"
---

Create a scope doc at `.pearls/docs/epics/$epic_id.md` using this template:

```markdown
# $title

> Epic: `$epic_id`

## Problem

(What's the problem this epic solves?)

## What ships

(Enumerate each delivery unit with its own per-unit fields. Cross-repo work splits into separate units — one per target repo.)

Worked example — two delivery units, one cross-repo:

- Add per-unit target-repo fields to scope-doc template
  - vehicle: type: issue
  - source repo: pearls
  - affected surface: `pearls_data/commands/create-scope-doc.md`
  - target repo: pearls
  - shape: Edit the embedded scope-doc template so each `What ships` unit demonstrates `title`, `vehicle`, `source repo`, `affected surface`, and `target repo` fields inline. Template-only change; no skill behavior change.

- Tighten plan-mode synthesize/propose to require cross-repo splits
  - vehicle: type: epic
  - source repo: pearls
  - affected surface: `medici/medici/data/modes/medici-plan.md`
  - target repo: medici
  - shape: Update plan-mode prompt language so synthesize/propose and pause-on-ambiguity gates require cross-repo delivery units to be split per target repo at planning time, rather than buried in per-repo planning doc prose.

## Acceptance criteria

(How we know it's done)

## Out of scope

(Explicitly what we're NOT doing)
```

Commit and push:

```
git add .pearls/docs/epics/$epic_id.md
git commit -m "docs: scope $epic_id"
git push
```

If the file already exists, error: "Scope doc already exists at .pearls/docs/epics/$epic_id.md. Edit it directly."
