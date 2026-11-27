---
name: idea
description: Capture an idea as a markdown doc in the configured ideas directory
parameters:
  prompt:
    required: true
    description: Freeform description of the idea (free text — quote it)
    hint: "freeform text"
---

Capture the idea described in `$prompt` as a markdown doc in `.pearls/docs/ideas/`.

Steps:

1. Form a concise kebab-case slug and a human-readable title from `$prompt`.
2. Capture relevant session context — what was being worked on; recent files or commits if relevant — plus the user-provided framing.
3. Write to `.pearls/docs/ideas/<slug>.md` using this template:

   ```
   # <title>

   > Captured: YYYY-MM-DD

   ## Context

   (What was happening when this idea came up — current task, files, or discussion)

   ## Idea

   $prompt
   ```

4. If the file already exists, append `-2`, `-3`, ... to the slug until you find a free name. Do not overwrite.
5. Inline (blocking) execution — do not `git commit` or `git push`. The doc stays unstaged so the user can edit before committing.
