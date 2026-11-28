# Sandbox blocks github.com archives, and an rm-guard wrapper breaks restricted-PATH tests

> Captured: 2026-11-28

## What was happening

While implementing gcd-1ee1.4 (bats tests for install.sh and the ci/ scripts),
ci/setup.sh needed to install a pinned bats-core. `curl -fsSL
https://github.com/bats-core/bats-core/archive/refs/tags/v1.11.1.tar.gz`
failed with `curl: (22) The requested URL returned error: 403` through the
session proxy, while `https://registry.npmjs.org/bats/-/bats-1.11.1.tgz`
worked. So setup downloads the npm tarball and checks it against a pinned
sha256 (cross-checked against npm's sha512 integrity record).

Separately, tests/bats/helper.bash `only_tools` first built a restricted PATH
by symlinking `$(command -v rm)` and similar. In the sandbox, `rm` resolves to
`/root/.claude/rm-guard/.../refuse/rm`, a wrapper that then failed with
`rm: command not found` under the restricted PATH, so ci/setup.sh and
ci/test.sh exited 127. The fix was to link /usr/bin/<tool> or /bin/<tool>
first.

## Headache

github.com release archives return 403 from the session sandbox (npm registry works), so pinned tool downloads in ci/setup.sh had to use npm tarballs; also a PATH rm-guard wrapper breaks tests that build a restricted PATH from command -v
