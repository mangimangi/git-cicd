# mangimangi — Agent Context

This is a single-repo medici workspace: this directory IS the target repo.

## Planning Structure

Planning lives in `.pearls/docs/`:

- `epics/` — epic-level scope and planning docs
- `ideas/` — captured ideas
- `headaches/` — captured friction
- `overview.md` — project overview

## Workflow

1. **Plan** — use `/planning` to discover scope and create epics
2. **Configure** — run `medici configure` to materialize modes and skills for this repo
3. **Run the lifecycle** — `medici session --repo mangimangi --epic <id> --mode <mode>` launches a containerized session that walks refine → estimate → implement → eval → cleanup

## Issue Tracking

Issues live in this workspace's `.pearls/issues.jsonl`. Use the `prl` CLI:

```bash
prl list                              # list open issues
prl create --title "title"            # create task
prl show <id>                         # show issue details
```
