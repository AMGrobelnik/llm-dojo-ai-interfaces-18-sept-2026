<!-- hook: oxfmt-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_STAGED
# aii_frontend/ is oxfmt-formatted, project-wide

`--check` reports unformatted files but does NOT rewrite. So this is a
strict gate: any drift across the whole frontend blocks the commit.
Project-wide check is ~0.5 s; the friction is small.

Self-scoping mirrors the lefthook `root: "aii_frontend/"` filter: the rule
runs only when the staged list contains a file under `aii_frontend/`
(in all-mode the tracked-file list always does, so the sweep covers the
whole frontend).

The bytes checked come from the INDEX, not the working copy: `check.sh`
materializes the frontend's formattable files into a scratch tree with
`git checkout-index --prefix` and runs oxfmt there. A whole-tree gate that
reads disk judges whatever a concurrent agent has half-written — on
2026-09-05 a peer's unstaged file failed unrelated commits twice across this
family of rules — while the index is exactly the tree under judgment
(`git commit --only` points `GIT_INDEX_FILE` at a temporary index of HEAD
plus the named paths; a plain commit's `.git/index` is what lands). Only
oxfmt's own input is copied: the eight formattable extensions plus the
`.oxfmtrc.json`, `.gitignore` and `.prettierignore` it reads. Copying every
tracked frontend file would move the ~120 MB of `public/` assets oxfmt never
opens; this moves ~6.6 MB in ~60 ms, and the whole rule measures ~0.6 s over
701 files (2026-09-06).

Fix when blocked: from `aii_frontend/`, run `./node_modules/.bin/oxfmt`
(no flag — writes fixes), then `git add` and re-commit.

Delete-check: tool-enforced, cannot delete — formatting is the canonical
"one sanctioned way" dimension; without the gate every diff carries
formatting noise.
