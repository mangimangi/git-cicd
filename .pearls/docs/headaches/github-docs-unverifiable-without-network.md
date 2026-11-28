# GitHub docs can't be checked from implementation sessions with no network

> Captured: 2026-11-28

## What was happening

I was evaluating epic gcd-cf98. gcd-cf98.1 told the implementer to confirm against GitHub's documentation that the per-matrix-entry secret selection works: `contains(fromJSON(needs.decide.outputs.secrets)[matrix.job], 'X') && secrets.X || ''` in a step's `env`. gcd-cf98.2 told them to confirm that job-level `permissions` accept no expressions. Both implementation commits say the docs could not be fetched because the session had no network. The mechanisms therefore rest on recalled behaviour. Local tests pass (510 pytest, 100% coverage, 35 bats), but only a real Actions run can prove the mechanisms work.

## Headache

Issues require confirming workflow mechanisms against GitHub docs, but impl sessions have no network. Either give the sessions read access to the docs, or plan a real workflow run after merge that checks these points.
