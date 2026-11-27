---
name: cleanup
description: Archive a completed epic and its children
argument-hint: epic-id
---

Archive **only** $0 and its children — never any other epic, issue, or tracker-wide operation. Other closed epics will be archived by their own cleanup runs.

1. Close the epic, then archive it. `prl archive` refuses an epic that is not closed, so the order matters:
   1. Run `prl show $0`. If the epic is not `closed` yet and every one of its children is `closed`, close it with `/close-issue $0`. If a child is not closed, STOP and report it — implement and eval are not finished, and cleanup does not close, score or reopen children.
   2. Archive the epic and its closed children with `/archive-epic $0`.
2. Move the planning doc using `/archive-scope-doc $0`
3. Create a PR from the impl branch to the base branch with `madp pr create`, using the title and body from [PR format](#pr-format) below:

   ```
   git push -u origin HEAD
   madp pr create --base "${MEDICI_PR_TARGET:-main}" --title "<title>" --body "<body>"
   ```

   The PR must target `${MEDICI_PR_TARGET:-main}`. `MEDICI_PR_TARGET` is set by the dispatcher when this session is running under a workspace orchestrator; falling back to `main` keeps the command correct in standalone runs. The command prints the PR as JSON, including its `number`; if an open PR already exists for this branch it returns that one instead of creating a second. Use `madp pr`, not `gh pr`: the `gh pr` subcommands do not work on every host these sessions run on.
4. Sync the PR head with the current base, so the later squash produces a clean result and any JSONL conflicts resolve deterministically via the pearls merge driver registered in `.gitattributes`:

   ```
   git fetch origin "${MEDICI_PR_TARGET:-main}" --quiet
   git merge "origin/${MEDICI_PR_TARGET:-main}" --no-edit  # resolves JSONL conflicts via the pearls merge driver
   git push
   ```

   If the merge stops on a conflict outside the JSONL files that you cannot resolve cleanly, STOP and report it; do not force anything.
5. STOP here. **Do NOT merge the PR**, and do not wait for its checks. Session finalization merges it after you exit: it records this session's final row, pushes the final commit, waits for the PR's checks, and — only if no check failed — squash-merges the PR. Merging in the session would land the PR without this session's final record and would make finalization fail.

Step 1 is about $0 only. If you notice OTHER open epics that have no open children, you may close each of them with `/close-issue <epic-id>`, but do NOT archive them — they may be long-lived collection epics, and each closed epic is archived by its own cleanup run.

If you hit friction during cleanup, fire off a `/headache` inline and move on. Do not list `.pearls/docs/headaches/`, do not check for existing or similar headaches, and do not deduplicate. Dedup happens later during triage.

**This is an automated session.** Nobody reads a report at the end of your turn, and a turn that simply ends is a success (exit 0). Wherever the steps above say to STOP and report, run `madp stop --mode cleanup "<what blocked you>"` as your last action instead, so the session ends as a failure with the reason recorded. Step 5's STOP (do not merge the PR) is the normal end of the session, not a failure.

## PR format

Give `madp pr create` a title and body in this exact format.

**Title:** `<epic-title> (<epic-id>)`

**Body:**

```
## Summary

<2-3 sentence description of what this epic delivered>

## Issues

- **<issue-id>**: <title> (score: <N>)
- ...

## Session cost

- Input tokens: N
- Output tokens: N
- Cache read: N (if available)
- Cache create: N (if available)
- Sessions: N
```

Gather the content:

- Epic title: from `prl show $0`
- Issues with scores: run `prl list --parent $0` to enumerate children, then `prl show <id>` for each to read scores
- Session cost totals: sum from `.madreperla/sessions.jsonl`

## Completion criteria

You are done when $0 is closed and archived together with its closed children, the planning doc is archived, a PR from the impl branch to `${MEDICI_PR_TARGET:-main}` exists (created with `madp pr create`), and the impl branch has been synced with the base and pushed. The PR is still open when you finish: you do not merge it — session finalization squash-merges it after pushing the final commit and after its checks pass. Do not implement, evaluate, or reopen issues — those are separate modes.
