# mark-issue-implemented push fails on a branch with no upstream

> Captured: 2026-11-28

## What was happening

Implementing the children of epic gcd-bbdd on the session branch
`gcd-bbdd/impl`, which was created locally and never pushed. After each
child, `/mark-issue-implemented <id> <sha>` ran `prl impl` and committed
`.pearls/issues.jsonl` ("pearls: gcd-bbdd.N implemented"), then ran a plain
`git push`, which failed every time with:

    fatal: The current branch gcd-bbdd/impl has no upstream branch.

The skill only allows a plain `git push`, so it would not run
`git push --set-upstream origin gcd-bbdd/impl`. All five tracker commits
stayed local.

## Headache

mark-issue-implemented pushes with a plain git push, which fails on a fresh session branch with no upstream (gcd-bbdd/impl); every mark left the tracker commit local only
