---
name: eval
description: Evaluate and score implemented issues in an epic
argument-hint: epic-id
---

Evaluate the implemented issues in $0. **Treat every `implemented`-status child as having stale scores and re-evaluate it against current code state on every eval pass** — even if it already has a `/create-issue-eval` score recorded from a prior pass. Prior scores are stale because the codebase, sibling issues, and caused defects may have moved since they were written; an `implemented` issue that is still `implemented` (not `closed`) is by definition unfinished, and re-scoring is unconditional within this session.

For each implemented child:

1. Analyze the issue details, evaluate the implemented code changes. If it has a `pr_number`, use `madp pr diff <pr_number>`. Otherwise `git show <commit>`.

2. **Diff hygiene check** — run `git diff <base>..HEAD --name-only` and verify against these categories:
   - **build artifacts** (strict — affects `hygiene` score): `build/`, `dist/`, `*.egg-info/`, `__pycache__/`, `*.pyc`, `node_modules/`, `target/`, `.DS_Store`, `*.log`, `*.tmp`
   - **sensitive content** (strict — affects `hygiene` score): hardcoded credentials, API keys, tokens, large binary blobs (heuristic: non-text files >100KB)
   - **expected metadata — NOT a hygiene violation**: files under `.madreperla/` are tooling metadata produced by normal madreperla operation, not build artifacts. Known paths include `.madreperla/sessions.jsonl` and `.madreperla/.gitattributes` (and any other tracked files under `.madreperla/`). These MUST NOT affect the `hygiene` score even if they resemble build-artifact patterns.
   - **out-of-scope files** (advisory — affects `completeness` score): every changed file should be traceable to a requirement in the issue or planning doc

   If build artifacts or sensitive content are found, file a defect via `/create-defect "<title>" "<body>" <original-issue-id>` rather than passing eval.

3. **Collect testing evidence, then score the `testing` dimension.** Both signals below are MANDATORY — the testing-dimension score flows from the combination of CI evidence and in-session run, and you have no discretion to skip either.

   **3a. CI evidence (required before any `testing` score is written).** If the issue has a `pr_number`, run `madp pr checks <pr_number>` (it prints a JSON list of `{name, state, link}`) and paste the output into the transcript verbatim. This is imperative — there is no decision point on whether to collect it. If the issue has no `pr_number`, paste a single line stating `no pr_number — CI evidence skipped` into the transcript and proceed; the in-session run in 3b still applies.

   When the pasted CI output contains any check in state `FAILURE` or `ERROR`:
   - The `testing` dimension score is **auto-pinned to ≤ 70** (pick a value in 0–70 reflecting how bad the CI signal looks; you cannot score `testing` above 70 on this pass).
   - You MUST auto-fire `/create-defect "<title>" "<body>" <implemented-issue-id>`, which links the defect to the originating issue. The defect body must identify the failing check(s): list each failing check name on its own line, include the run URL when present, and reference the PR number. Suggested filter: `madp pr checks <pr> | jq '[.[] | select(.state == "FAILURE" or .state == "ERROR")]'`.

   States `NEUTRAL`, `SKIPPED`, `STALE`, and `PENDING` do NOT trigger the auto-pin and do NOT fire `/create-defect` — skipped checks may be intentional (path filter, opt-in workflow), so penalizing them would generate false-positive defects.

   **3b. In-session test run (required, unchanged).** Discover the repo's test command (bats, pytest, unittest, npm test, etc.) and execute the full suite. The `testing` dimension score MUST directly reflect the pass/fail outcome — do not score `testing` on code review alone. On any test failure, you MUST file a defect via `/create-defect` linked to the original issue. A failing suite is always a defect; there is no discretion to skip this.

   Both signals flow through this same step-3 contract: a red CI gate caps `testing` at 70 and fires its own defect; an in-session failure additionally fires its own defect. Step 5's threshold-defect path then naturally fires if the resulting `testing` score still falls below the configured threshold.

4. Score the issue, then record the scores with `/create-issue-eval <issue-id> <evaluator-model-id> "<name>=<score> <name>=<score> ..."`. Score honestly — do not aim for thresholds.
   - Run `/list-eval-dimensions` once to get the configured dimension names and thresholds. The third argument is ONE quoted string with a `name=score` pair (integer 0-100) for **every** configured dimension; the tracker rejects a missing or unknown dimension.
   - `<evaluator-model-id>` is your own model id.
   - The skill only records what you pass. You are the evaluator: the scores must come from the analysis in steps 1-3, never from the skill.

5. **File a defect for every dimension scored below its threshold.** After scoring, compare each score against the configured threshold (default `eval.threshold`, overridden by per-dimension `threshold`). For each failing dimension, create a defect via `/create-defect` linked to the original. The defect body must include:
   - the **dimension name** that failed
   - the **score** you gave
   - the **threshold** it fell below
   - **guidance** on what to fix — be specific about what change would raise the score (e.g., "add tests covering the empty-input branch in `foo.py:42`", "rename `x` to something descriptive and split the 200-line function").

   File one defect per failing dimension so implement has a clear, actionable punch list. Hygiene violations from step 2 and test failures from step 3 also go through this same path.

Score each child issue individually. Issues auto-close when all scores meet configured thresholds — do NOT pass `--no-close` to individual issue evaluations inside this eval session. Passing `--no-close` suppresses auto-close and breaks the walker pipeline: the next stage expects every evaluated child to be closed, and implemented-but-open children fail the eval validation gate. Leave the epic itself open when finished.

6. **Defect-loop close-out** — for any child that remains `implemented` after re-scoring (auto-close didn't fire), check whether its caused defects have all closed. A "caused defect" is a child with `issue_type: bug` AND a `deps` entry of type `caused_by` pointing at this implemented issue; enumerate them via `prl list --parent $0` and `prl show <id>` to inspect each `deps` array. If **all** of the following hold, close the implemented issue via `/close-issue <issue-id>`:
   - all dimension scores from the just-completed re-score meet their thresholds
   - every caused defect (bug child with `caused_by` → this issue) is `closed`

   This unblocks the defect loop: when a defect ships and closes, the causing issue no longer stays stuck in `implemented` limbo on the next eval pass. If the issue has no caused defects and all scores pass, auto-close already handled it in step 4 — this step is specifically the recovery path for issues whose first pass scored below threshold and spawned defects that have since landed.

The `--no-close` flag exists for standalone or interactive evaluations run outside the walker (e.g. an ad-hoc re-score). It is NOT appropriate when scoring children as part of an eval-mode session.

If you hit friction during evaluation, fire off a `/headache` inline and move on. If you spot an improvement opportunity, fire off an `/idea` inline. Do not list `.pearls/docs/headaches/` or `.pearls/docs/ideas/`, do not check for existing or similar entries, and do not deduplicate. Dedup happens later during triage.

## Calling the tracker skills

The tracker skills run in a separate context that cannot see this conversation. They receive only the arguments you pass, split on spaces, in order. Pass every argument, in the order shown, and put quotes around any argument that contains spaces. If a skill replies `MISSING ARGUMENT`, call it again with the full argument list; do not work around it by calling `prl` yourself.

## Completion criteria

You are done when all implemented children of $0 are scored via `/create-issue-eval`. Do NOT pass `--no-close` when scoring individual issues in this session — doing so leaves them in `implemented` state instead of `closed` and breaks the walker pipeline (the next stage expects all evaluated children to be closed). Do not implement code, archive issues, or close the epic — those are separate modes.
