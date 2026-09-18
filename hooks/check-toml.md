<!-- hook: check-toml -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tracked .toml parses cleanly (taplo lint, project-wide)

taplo lint replaces uvx-wrapped check-toml — same syntax-error detection
(`uv sync` / ruff / ty all blow up on malformed TOML) but native Rust
binary, no uvx cold-start. `lint` validates without writing; `check`
would also enforce formatting. Scope to `*.toml` files only — bare
`taplo lint` walks the whole tree (10+ s in this repo) for no benefit.

Runs project-wide (every commit re-scans the whole tree) so stale issues
outside the staged set still block.

Fix when blocked: taplo's error names the file and line — fix the syntax
error there; do not exclude the file.

Delete-check: tool-enforced syntax validity, cannot delete — malformed
TOML breaks uv/ruff/ty downstream with worse errors.
