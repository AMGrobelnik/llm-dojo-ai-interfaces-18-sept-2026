<!-- hook: check-yaml -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tracked YAML file parses cleanly (project-wide, relaxed parser)

Uses the bare `check-yaml` binary from the pre-commit-hooks package
(`uv tool install pre-commit-hooks==5.0.0` puts its console scripts on
PATH), skipping uvx's per-run package-resolve overhead. Runs project-wide
(every commit re-scans the whole tree) so stale issues outside the staged
set still block.

`*.private.yaml` siblings sometimes carry comments or values that
`yaml.safe_load` handles fine but the strict parser flags. Keep relaxed
(`--allow-multiple-documents`). Vendored skill bundles under
`.claude/skills/` and `.agents/skills/` are excluded.

Fix when blocked: the error names the file and line — fix the YAML syntax
there; do not exclude the file.

Delete-check: tool-enforced syntax validity, cannot delete — configs are
`.yaml` by repo convention (Rule 6), so a broken one breaks the consumer
at runtime with a worse error.
