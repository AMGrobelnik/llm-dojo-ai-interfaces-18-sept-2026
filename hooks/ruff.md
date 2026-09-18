<!-- hook: ruff -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |
# The whole Python tree passes ruff lint (check-only, project-wide)

Native `ruff` binary instead of uvx — kills uvx package-resolve overhead.
Install once: `uv tool install ruff==0.14.0` (or pin whatever version this
repo standardizes on).

Project-wide check (no `--fix`): every commit re-validates the whole tree,
so a stale lint issue in any file blocks the next commit until fixed. Skill
bundles and generated code are filtered via `[tool.ruff] extend-exclude` in
pyproject.toml — the same config ruff uses everywhere — so no duplication
here. The whole project scan runs in ~0.08s so the friction is small.

Fix when blocked: `ruff check --fix .` for the auto-fixable findings, hand
fixes for the rest — never a `# noqa` to silence a real code smell. Then
`git add` your files and re-commit.

Delete-check: tool-enforced, cannot delete — lint findings are a dimension
of variation only a linter closes; scope tuning lives in pyproject.toml, not
in this rule.
