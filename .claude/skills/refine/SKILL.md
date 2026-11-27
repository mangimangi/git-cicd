---
name: refine
description: Refine features into trackable issues with clear acceptance criteria
---

**This is an automated session.** Nobody will read your replies or answer a question, and a turn that ends on a question delivers nothing. Never end your turn on a question, on a proposal for someone to confirm, or waiting for input.

Refine the features below into straightforward issues that are small in scope with clear acceptance criteria. If applicable, specify requirements for extending docs and tests based on existing patterns in addition to implementing the functionality. As part of refinement, discern what epic the issue(s) will be created in (or if a new epic will be created).

**Decide, record, proceed.** Where the planning doc leaves a choice open, take the option that best meets the doc's acceptance criteria and this repository's rules (AGENTS.md and the docs above), write the decision and its reason into the body of the issue it affects, and go on. A proposal you would have put to a person for confirmation is a decision you record. Before you finish, record every decision in the planning doc under one heading, `## Refinement decisions`: one bullet per decision, naming what was decided, the issue ID it affects, and the reason.

**Or stop as a failure.** Stop only when no breakdown would be right whatever the answer — the doc contradicts itself, or it names work that does not exist. Then write the blocking question in the planning doc under `## Blocking question`, commit and push it, and run `madp stop --mode refine "<the blocking question>"` as your last action. Do the same whenever you end without creating every issue you set out to create: run `madp stop --mode refine "<which issues were not created, and why>"`. `madp stop` makes the session end as a failure instead of exit 0; a refine that is missing issues never ends without it.

If an epic id is provided, use `/review-epic <id>` to show the epic's planning doc inline for context.

**Scope to this repo first.** Before creating any issue, read the planning doc's `repo:` frontmatter field. If `repo:` is set, the issues you create here MUST cover only the work this repo delivers — sections of the doc that describe work happening in other repos are reference-only context, not issues to create in this tracker. Restating cross-repo work as in-scope produces issues that cannot be implemented. If the `repo:` field is absent, fall back to the default scoping behavior.

**Carry forward all concrete details from input docs (planning docs, idea docs, headache docs).** You may add clarity but never drop or summarize away details — specific code references, paths, function names, line numbers, and implementation caveats from upstream docs MUST appear in the issues you create. Re-validate concrete code references against current code before producing downstream artifacts; if a reference is stale, fix it rather than dropping it.

Create issues using `/create-issue "<title>" <type> <parent-id> "<body>"`. All four arguments are required, in that order: quote the title and the body, `<type>` is one of task, bug, feature, chore, and `<parent-id>` is the epic. The skill runs in a separate context and sees only these arguments, so the body must carry everything. Each issue should have:
- A clear, actionable title
- A body fully and explicitly covering acceptance criteria and scope
- The parent epic ID set

After creating issues, update the planning doc to reflect the work scoped to each issue ID. Commit and push your changes when done.

If you hit friction during refinement, fire off a `/headache` inline and move on. If you spot an improvement opportunity, fire off an `/idea` inline. Do not list `.pearls/docs/headaches/` or `.pearls/docs/ideas/`, do not check for existing or similar entries, and do not deduplicate. Dedup happens later during triage.

## Completion criteria

You are done when all items in scope are refined into issues with clear acceptance criteria, the planning doc is updated, and changes are committed and pushed. Do not implement, estimate, or evaluate — those are separate modes.

The scope of the work I want to refine is:
$ARGUMENTS
