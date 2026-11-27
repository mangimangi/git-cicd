---
name: create-scope-doc
description: Create a scope doc for an epic
model: sonnet
effort: medium
context: fork
argument-hint: epic-id title text
---

Create a scope doc at `.pearls/docs/epics/$0.md` using this template:

```markdown
# $1

> Epic: `$0`

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
git add .pearls/docs/epics/$0.md
git commit -m "docs: scope $0"
git push
```

If the file already exists, error: "Scope doc already exists at .pearls/docs/epics/$0.md. Edit it directly."

Before running anything, check the command above for an unfilled placeholder: a dollar sign immediately followed by a single digit. Every argument the caller supplied has already been substituted into the command, so such a placeholder means that argument was not supplied. If you find one, run nothing, change nothing, and reply with exactly `MISSING ARGUMENT: <position>`, giving the digit. If there is none, proceed. Never guess or invent a value for a missing argument.

Run the command above and report its output. Do not invoke any other commands or skills.
