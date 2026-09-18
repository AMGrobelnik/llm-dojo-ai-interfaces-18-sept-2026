<!-- hook: uv-lock -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |
# uv.lock is consistent with every workspace pyproject.toml

`uv lock --check` asserts uv.lock is up to date with every workspace
pyproject.toml (root + aii_lib/aii_pipeline/aii_server/aii_runpod/
aii_launcher) WITHOUT writing. Catches the classic "edited pyproject
deps, forgot to run `uv lock`" commit that breaks `uv sync` for everyone
else. Runs unconditionally — no path filter — because at ~55 ms a skip
heuristic costs more than the check; the clean-tree path resolves from
cache, no network.

Self-scoping: project-wide by design; a consistent lock exits 0 whatever
is staged.

Fix when blocked: run `uv lock` and stage the updated uv.lock together
with the pyproject change. (Reminder from the repo notes: `uv sync`
uninstalls `claude_cred_manager` — reinstall it with
`uv pip install --python .venv/bin/python -e claude_cred_manager --no-deps -q`.)

Delete-check: tool-enforced consistency, cannot delete — the lockfile
exists precisely so the resolved environment is one artifact; letting it
drift silently reintroduces the dimension the lock removed.
