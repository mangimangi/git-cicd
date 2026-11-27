---
name: bleached
description: Sweep the repo for dead code, stale config, and legacy artifacts
model: opus
effort: high
argument-hint: [hooks|config|imports|all]
---

Sweep the repo for dead code, stale config, and legacy artifacts. Remove high-confidence dead items directly; file issues for anything ambiguous so a human can decide.

Steps:

1. Read AGENTS.md README.md docs/ for repo orientation.
2. If `$0` is empty, default to `all`. If `$0` is not one of `hooks|config|imports|all`, error: "Unknown scope. Allowed: hooks, config, imports, all."
3. Scan the requested scope(s) for:
   - **hooks** — unreferenced git/pre-commit hooks, disabled hook scripts, leftover hook configuration.
   - **config** — stale keys in config files, dead env vars, unreferenced fixtures, legacy feature flags.
   - **imports** — unused imports, unreferenced modules/files, dead symbols with zero inbound references.
4. Classify every finding by confidence:
   - **certain dead** — zero inbound references and no plausible runtime/dynamic use (reflection, plugin discovery, entry points, etc.).
   - **possibly dead** — uncertain (dynamic reference patterns, string-keyed lookups, potentially consumed by external tooling).
5. Remove certain-dead items and **commit per category** — one commit per scope category (for example `chore: remove dead imports`). Do not batch all categories into one commit.
6. For possibly-dead items, file an issue per item so a human can review and decide:
   - First create one tracking epic for this sweep with `/create-epic "<title>" "<body>"` (both arguments required and quoted; for example the title `Bleached sweep: possibly-dead items`). Note the epic ID it reports. Skip this if there are no possibly-dead items.
   - Then file each item under it with `/create-issue "<title>" chore <epic-id> "<body>"`. All four arguments are required, in that order; quote the title and the body. Include the file path and the reason it is ambiguous in the body. The skill runs in a separate context and sees only these arguments.
7. Push when done.

## Completion criteria

You are done when every category in the requested `$0` has been swept, certain-dead items are removed and committed per category, possibly-dead items are filed as issues, and changes are pushed. Do not ask what to do. Do not list findings and wait. Make the changes.
