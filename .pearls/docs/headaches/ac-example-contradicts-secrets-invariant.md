# An acceptance criterion's example contradicts the secrets invariant

> Captured: 2026-11-28

## What was happening

Implementing gcd-1dec.2 (included jobs behave as the repository's own). I was writing
`test_verify_follows_a_change_to_an_included_job` in `tests/test_workflow.py`. Acceptance
criterion 6 gives "its `on`, `branches` or `secrets`" as examples of a change to a taken job
that makes `git-cicd verify` fail. The existing test
`test_secret_declarations_write_nothing_into_the_workflows` shows that secret declarations
write nothing into the generated workflows, so a change to secrets alone can never fail
verify. The test changes `branches` and `on` instead, and the commit message records why.

## Headache

gcd-1dec.2 acceptance criterion 6 says changing an included job's secrets makes verify fail, but secret declarations never reach the generated workflows (they are decide's output), so verify cannot fail on a secrets-only change; refinement should check AC examples against existing invariants
