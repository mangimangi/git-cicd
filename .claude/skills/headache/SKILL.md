---
name: headache
description: Capture friction or a recurring annoyance as a markdown doc
model: sonnet
effort: medium
argument-hint: freeform text
---

Capture the friction described in `$0` as a markdown doc in `.pearls/docs/headaches/`.

Steps:

1. Form a concise kebab-case slug and a human-readable title from `$0`.
2. Capture context about *what was happening when the friction occurred* — current task, command or file involved, error message if any.
3. Write to `.pearls/docs/headaches/<slug>.md` using this template:

   ```
   # <title>

   > Captured: YYYY-MM-DD

   ## What was happening

   (Current task, command or file involved, error if any)

   ## Headache

   $0
   ```

4. If the file already exists, append `-2`, `-3`, ... to the slug until you find a free name. Do not overwrite.
5. Inline (blocking) execution — do not `git commit` or `git push`. The doc stays unstaged so the user can edit before committing.
