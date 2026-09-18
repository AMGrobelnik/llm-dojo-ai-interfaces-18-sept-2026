<!-- hook: bun-lock-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root
# aii_frontend/bun.lock stays in sync with package.json

Same contract as `uv lock --check` on the Python side, for the frontend:
package.json ↔ bun.lock drift fails with "lockfile had changes, but
lockfile is frozen". `--dry-run` resolves without installing; the clean
path is ~11 ms. Catches the classic "edited package.json deps, forgot to
update bun.lock" commit that breaks install for everyone else. Runs
unconditionally — no staged-file scoping — because at this cost a skip
heuristic costs more than the check.

Fix when blocked: run `bun install` in `aii_frontend/` and commit the
updated `bun.lock` together with the `package.json` change.

Delete-check: tool-enforced consistency between two files that must
co-evolve; cannot delete — a stale lockfile silently ships different
dependency versions than the manifest declares.
