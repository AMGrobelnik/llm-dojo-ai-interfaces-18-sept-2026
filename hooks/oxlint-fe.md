<!-- hook: oxlint-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_STAGED
# aii_frontend/ passes oxlint (type-aware, check-only), project-wide

Project-wide check (no `--fix`): every commit re-validates the whole
frontend, so a stale lint issue in any file blocks the next commit until
fixed.

`--type-aware` activates the `oxlint-tsgolint` backend (Go binary bundled
by the `oxlint-tsgolint` npm package) — runs the typescript-eslint
type-aware rules (`no-floating-promises`, `no-unnecessary-condition`,
`strict-boolean-expressions`, `switch-exhaustiveness-check`, …) using
`typescript-go` as the type checker.

`--quiet` suppresses warning-level output (this repo currently has ~500
advisory warnings, mostly stylistic strict-boolean-expressions and
no-unsafe-type-assertion). Without it, every run floods the terminal.
Errors still surface normally; the warning count appears in the summary
line. Whole-frontend scan is ~2.7 s.

Self-scoping mirrors the lefthook `root: "aii_frontend/"` filter: runs
only when the staged list contains a file under `aii_frontend/`.

Fix when blocked: from `aii_frontend/`, run
`./node_modules/.bin/oxlint --type-aware --fix .`, then `git add` your
files and re-commit. Apply the modern best-practice fix to the code
smell — do not silence with disable comments or config excludes.

Delete-check: tool-enforced, cannot delete — the lint rules ARE the
pinned conventions for the frontend; the rule only carries the gate.
