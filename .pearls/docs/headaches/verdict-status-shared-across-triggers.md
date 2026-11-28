# The Verdict status context is shared across triggers

> Captured: 2026-11-28

## What was happening

I was refining epic gcd-bbdd (merge, cron and manual triggers) into issues gcd-bbdd.1 to .5, working from the planning doc .pearls/docs/epics/gcd-bbdd.md and templates/workflows/open.yml.

## Headache

Every git-cicd trigger writes the same commit status context, `Verdict / git-cicd:verdict`. When Open and Merge (or Cron, Manual and Merge) run on the same commit, the last writer wins. A run that needs nothing can then turn another run's failed verdict green.

Refinement worked around it in gcd-bbdd.1: a non-open run posts the status only when no open pull request has the commit as its head. Two cases are still not covered:
- a cron run on a commit that a merge run already reported;
- a manual run on such a commit.

The interface agreed on 2026-11-27 did not consider several runs per commit.
