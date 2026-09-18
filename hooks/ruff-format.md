<!-- hook: ruff-format -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |
# The whole Python tree is ruff-formatted (check-only, project-wide)

Same footing as the lint half: native `ruff` binary instead of uvx — kills
uvx package-resolve overhead. Install once: `uv tool install ruff==0.14.0`
(or pin whatever version this repo standardizes on).

Project-wide and check-only: the gate verifies rather than rewrites, so the
working tree is never mutated behind your back; every commit re-validates
the whole tree and a stale formatting drift in any file blocks the next
commit until fixed. Exclusions come from `[tool.ruff] extend-exclude` in
pyproject.toml — the one config ruff uses everywhere — so no duplication
here.

Fix when blocked: run `ruff format .`, review the diff, `git add`, re-commit.

Delete-check: tool-enforced, cannot delete — one canonical formatting is the
point; deleting the check reopens the dimension file by file.
