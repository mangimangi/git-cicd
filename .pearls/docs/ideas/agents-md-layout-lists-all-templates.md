# AGENTS.md layout line should list all four workflow templates

> Captured: 2026-11-28

## Context

Eval pass over epic gcd-bbdd (merge, manual, declared inputs, cron and own jobs;
commits 64343d1..a4b598f on `gcd-bbdd/impl`). The epic updated the AGENTS.md
paragraph on generated workflows, but the Layout section was missed.

## Idea

AGENTS.md Layout line is stale: templates/workflows/<trigger>.yml still says '(open.yml)' though merge.yml, cron.yml and manual.yml now exist; list all four
