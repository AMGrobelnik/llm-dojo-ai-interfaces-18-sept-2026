<!-- hook: check-json -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tracked .json file is strict JSON (project-wide, curated exclusions)

Mirrors check-yaml / check-toml: YAML + TOML were validated, tracked
`.json` (configs, openapi.json, schemas) were not — 29 tracked today, 16
in scope after the exclusions below (measured 2026-08-28). Native
`check-json` binary (on PATH via the pre-commit-hooks uv tool).
Project-wide ls-files walk so a stale broken JSON anywhere blocks the
next commit. Excludes are non-strict-JSON BY DESIGN:

- vendored skill bundles (`.claude/skills`, `.agents/skills`).
- `*llm_judge_messages.json` are JSONL/NDJSON streaming logs.
- `aii_frontend/.fallowrc.json` is JSONC (// comments).

Fix when blocked: the error names the file — fix the JSON syntax there.
Only a file that is non-strict-JSON *by format* (JSONL, JSONC) earns a
new exclusion, added in the same commit so the diff shows it.

Delete-check: tool-enforced syntax validity, cannot delete — a broken
config/schema fails its consumer at runtime with a worse error.
