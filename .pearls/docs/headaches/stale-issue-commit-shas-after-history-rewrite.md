# Recorded issue commit SHAs go stale after history rewrite

> Captured: 2026-11-27

## What was happening

Running `/eval gcd-e74c`. Eval step 1 says to `git show <commit>` for an issue
without a `pr_number`. The `commit` field on gcd-e74c.1 through .7 (c66ae3d,
6219b43, 73962b8, b548d44, 3827bcb, be492bf, 59b069b) names objects that no
longer exist in the repository (`fatal: Not a valid object name`). The branch
history was rewritten after `mark-issue-implemented` recorded them. Each
issue's real commit had to be found by grepping commit messages (fa8f0ec,
8280bae, 9b65599, b4e801a, a0ff02d, d393da4, 317cd1a). gcd-e74c.8 and .9 also
share commit 2acc6b5, although .8's work is in d6ce76d and fc9356f.

## Headache

Recorded issue commit SHAs go stale after history rewrite
