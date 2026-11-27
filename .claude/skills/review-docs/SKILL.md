---
name: review-docs
description: Review docs in a configured category (planning, epics, ideas, headaches, retros, overview, assignment)
argument-hint: planning|epics|ideas|headaches|retros|overview|assignment [epic-id]
---

Review the docs in the configured category.

If "$0" is `overview`, read and print the single file at `.pearls/docs/overview.md`. If the file does not exist, error: "Overview doc not found at `.pearls/docs/overview.md`." This branch is a thin path wrapper — make no assumptions about the doc's internal schema.

If "$0" is `assignment`:

- If no epic id was supplied (`$1` is empty or is still an unfilled placeholder), error: "assignment category requires the epic_id parameter."
- Read and print whichever of the following exist (skip silently if a file or directory is missing — do not error):
  - `.pearls/docs/epics/$1.md` (scope doc)
  - `.pearls/docs/epics/$1/orchestrator.md` (orchestrator/assignment doc)
  - every `.pearls/docs/epics/$1/<repo>/<slug>.md` (per-repo planning docs; discovered by scanning `.pearls/docs/epics/$1/` for subdirectories and reading their `.md` files)

Otherwise, look up the path for "$0" below. List all `.md` files in that directory (skip `.archive/`). For each file, summarize its purpose in 1-2 sentences. Group by recency (modified within last 30 days vs older). Note any docs that look stale or duplicate.

If "$0" is not one of the listed categories below, error: "Unknown category. Configured categories: planning, epics, ideas, headaches, retros, overview, assignment."

Configured categories (interpolated from pearls.yaml docs.* at prl configure time):
- planning → .pearls/docs
- epics → .pearls/docs/epics
- ideas → .pearls/docs/ideas
- headaches → .pearls/docs/headaches
- retros → .pearls/docs/retros
- overview → .pearls/docs/overview.md (single file)
- assignment → .pearls/docs/epics/$1.md + .pearls/docs/epics/$1/orchestrator.md + .pearls/docs/epics/$1/<repo>/<slug>.md
