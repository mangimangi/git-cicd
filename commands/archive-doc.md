---
name: archive-doc
description: Move a doc to the archive directory
parameters:
  path:
    required: true
    description: Path to the doc to archive, relative to repo root
    hint: "path/to/doc.md"
---

If `$path` does not exist, print an error and exit non-zero — do not attempt the move.

Move the doc to `.pearls/archive/docs/`:

```
mkdir -p .pearls/archive/docs
git mv $path .pearls/archive/docs/$(basename $path)
```

Commit and push:

```
git commit -m "archive: $(basename $path)"
git push
```
