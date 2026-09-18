<!-- hook: tsgo-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_STAGED
# aii_frontend/ typechecks clean (tsgo --noEmit), project-wide

Incremental compile per tsconfig.json's `incremental: true` — cold run
~8 s, warm run ~1-2 s after the first. tsbuildinfo lives at
`aii_frontend/tsconfig.tsbuildinfo` and is gitignored.

Self-scoping mirrors the lefthook `root: "aii_frontend/"` +
`glob: "**/*.{ts,tsx,js,jsx,mjs,cjs,json}"` filter: runs only when the
staged list contains a matching frontend file; a Python-only change
skips it entirely.

Fix when blocked: read the reported type errors and fix the types at the
root cause — no `any` casts or `@ts-ignore` to get past the gate.

Delete-check: tool-enforced, cannot delete — the typecheck is a property
of the whole module graph, so it must run project-wide whenever frontend
code changes.
