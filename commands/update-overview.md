---
name: update-overview
description: Read and display the workspace overview doc so the caller can edit it
---

Resolve the path to the workspace overview doc at `.pearls/docs/overview.md`.

If the file does not exist, error: "Overview doc not found at `.pearls/docs/overview.md`. Create it first."

Otherwise, print the file's full contents and instruct the caller to edit the file directly at the resolved path. Do NOT embed any schema assumptions about the overview doc — its format varies per workspace, so this command is a thin path wrapper only.
