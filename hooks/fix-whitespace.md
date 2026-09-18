<!-- hook: fix-whitespace -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MODE, RULES_STAGED
# Trailing whitespace / EOF newlines / non-Linux line endings are flagged, never fixed

Check-only (`whitespace-format --check-only`): reports, but never writes,
trailing whitespace, a missing trailing newline or a non-Linux line ending,
over config/docs/shell extensions
(json|toml|yaml|yml|md|sh|bash|html|sql|xml|txt|cfg|ini) — not over all text.
Source files — .py, .ts/.tsx, .js, .css — are deliberately outside the
list: ruff-format and oxfmt own their formatting. Binaries would choke the
UTF-8 decode; vendored skill bundles are excluded; files over 1 MiB are
skipped (two 48 MiB dumps once cost ~80 s by themselves); parallel via
xargs -P.

NO HOOK WRITES FILES (2026-09-15). This hook used to be a fixer: it
mutated files in place and lefthook re-staged them (`stage_fixed: true`).
That broke the moment `RULES_STAGED` stopped being just this commit's own
staged paths and became the whole tracked index like every other hook's
population: the fixer silently reformatted and re-staged 1151 files across
the whole repo it ran in, on an unrelated agent's commit. A hook that
writes the working tree in a checkout other agents share can rewrite their
concurrently-edited, uncommitted work; a hook that only reports cannot. Fix
the flagged files yourself and recommit.
