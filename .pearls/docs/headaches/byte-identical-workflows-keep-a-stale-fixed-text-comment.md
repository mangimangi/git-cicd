# Byte-identical Open/Merge/Cron workflows keep a stale "fixed text" comment

> Captured: 2026-11-28

## What was happening

Refining epic gcd-8f83 (the Manual workflow's form generated from the config). Its acceptance criteria require `git-cicd-open.yml`, `git-cicd-merge.yml` and `git-cicd-cron.yml` to be byte-identical to before the unit.

## Headache

`templates/workflows/open.yml`, `merge.yml` and `cron.yml` (line 13) say "Every generated file is fixed text except the cron workflow's schedule block". Once the Manual form varies with the config that sentence is wrong, but changing it breaks the byte-identical criterion, so the three generated files will carry a stale comment until a later unit is allowed to touch them. Every template repeating the cross-file rule in its header means any rule change touches every generated file.
