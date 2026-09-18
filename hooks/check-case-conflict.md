<!-- hook: check-case-conflict -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# No tracked filenames that conflict on case-insensitive filesystems

Uses the bare `check-case-conflict` binary from the pre-commit-hooks
package (`uv tool install pre-commit-hooks==5.0.0` puts the 33 console
scripts on PATH), skipping uvx's per-run package-resolve overhead. Runs
project-wide — every commit re-scans the whole tree — so stale issues
outside the staged set still block.

Fix when blocked: rename one of the conflicting paths (`git mv`) so no
two tracked names collapse to the same case-folded string.

Delete-check: cannot delete — the repo must stay checkout-able on
case-insensitive filesystems (macOS/Windows), and only a tree-wide scan
proves it.
