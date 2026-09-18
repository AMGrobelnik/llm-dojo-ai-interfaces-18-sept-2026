<!-- hook: hadolint -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tracked Dockerfile passes hadolint (warning threshold, policy ignore list)

Static Haskell binary, ~0.5 s for both root Dockerfiles. Install once:
download `hadolint-linux-x86_64` from
https://github.com/hadolint/hadolint/releases and place on PATH.

`--failure-threshold warning` gates on warnings and errors. The ignore
list is policy, not cleanup debt: DL3008/DL3018 (pin every apt/apk
package version) is impractical against moving Debian/Alpine repos, and
DL3059 (consolidate consecutive RUNs) fights the deliberate
layer-caching layout. Everything else — notably DL4006
pipe-without-pipefail and DL3003 cd-in-RUN — is enforced; the
Dockerfiles carry per-stage `SHELL -o pipefail` accordingly.
Whole-tree scope in both modes: check.sh enumerates every tracked
Dockerfile from `git ls-files` (flipped 2026-08-22 from staged-only;
the tree measured clean under these ignores), so any commit re-lints
them all — cheap at ~0.5 s.

Fix when blocked: hadolint names the file, line and DLxxxx rule — apply
the fix it describes; do not grow the ignore list without owner
approval, it is policy.

Delete-check: tool-enforced, cannot delete — Dockerfile mistakes
(missing pipefail, unpinned cd) surface only at build or runtime, far
from the edit.
