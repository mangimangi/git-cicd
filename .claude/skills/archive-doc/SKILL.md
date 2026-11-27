---
name: archive-doc
description: Move a doc to the archive directory
argument-hint: path/to/doc.md
---

If `$0` does not exist, print an error and exit non-zero — do not attempt the move.

Move the doc to `.pearls/archive/docs/`:

```
mkdir -p .pearls/archive/docs
git mv $0 .pearls/archive/docs/$(basename $0)
```

Commit and push:

```
git commit -m "archive: $(basename $0)"
git push
```
