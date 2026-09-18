<!-- hook: fallow-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_STAGED
# aii_frontend/ carries no dead code (Fallow scan)

Replaces `knip`. Fallow is the Rust-native equivalent — same scope
(unused files, exports, deps, duplicate exports), 3-36× faster on this
codebase (0.15 s vs ~12 s for knip cold). Drop-in via `fallow migrate`
for existing knip.json configs.

Self-scoping mirrors the lefthook `root: "aii_frontend/"` +
`glob: "**/*.{ts,tsx,js,jsx,mjs,cjs,json}"` filter: runs only when the
staged list contains a matching frontend file.

Fix when blocked: delete the dead file/export/dep it names — that is the
point of the gate. If a symbol is genuinely used through a path the
scanner cannot see, fix the config at its root rather than allowlisting
reflexively.

Delete-check: tool-enforced, cannot delete — dead code accumulates
silently by default; the gate is what keeps the "no unused exports"
dimension closed.
