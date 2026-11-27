# madp pr cannot edit a pull request body after create

> Captured: 2026-11-27

## What was happening

Solo session for gcd-d9eb. The acceptance criteria need platform timings in the pull request description. Those timings come from two pushes to the pull request after it is open. `madp pr create` returns the existing PR without changing its body, so the body had to be updated with a raw REST `PATCH /repos/{owner}/{repo}/pulls/6`. The first try got HTTP 415 because the Content-Type header was missing.

## Headache

madp pr has no way to edit a PR body after create. Solo flows that must put platform timings (known only after pushes to the open PR) in the description need a raw REST PATCH.
