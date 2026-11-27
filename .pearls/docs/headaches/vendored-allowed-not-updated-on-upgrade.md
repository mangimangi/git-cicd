# git-vendored never updates a vendor's allowed list on upgrade

> Captured: 2026-11-27

## What was happening

Solo session for gcd-f7ce: moving from the single `.github/workflows/git-cicd.yml` to per-moment workflow files (`.github/workflows/git-cicd-<moment>.yml`). `templates/config.json` now sets `_vendor.allowed` to `.github/workflows/git-cicd-*.yml`, so the vendor check also covers the files of moments that come later.

## Headache

git-vendored reads a vendor's `_vendor.allowed` only when the vendor is first added (`save_vendor_config` moves it into `.vendored/manifests/<vendor>.registry`). On an upgrade, neither `install.sh` nor the framework refreshes that list. A repository that installed git-cicd before this change keeps `.github/workflows/git-cicd.yml` as allowed. Its install PRs still pass because they come from the install branch. Later, though, the cron file's schedule block will change with the config. Regenerating it on an ordinary branch would then be rejected by Check Vendor Files. A vendor needs a way to update its registry fields on upgrade, and git-vendored is the place to add it.
