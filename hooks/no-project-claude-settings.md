<!-- hook: no-project-claude-settings -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

# No project-level Claude settings file is committed

The author keeps one global `~/.claude/settings.json` so every session behaves
the same way. Project-level `.claude/settings.json` files silently
diverged — one turned cross-session messaging off — and a session then
behaves differently depending on which repo it started in, invisibly.
Checks the index — `git ls-files -- .claude/settings.json` and `git
ls-files -- .claude/settings.local.json`, respecting `GIT_INDEX_FILE`
under `git commit --only` the same way every other rule here does — so it
fails equally on a commit that still carries an old tracked settings file
and on one that adds a new one.

Fix when blocked: delete the tracked `.claude/settings.json` (or
`.claude/settings.local.json`) and stage the deletion; move any setting
that must persist into the global `~/.claude/settings.json` instead.

Note: `.claude/settings.local.json` is gitignored in both `notes-repo` and
`research-monorepo`, so this hook can only stop the tracked file from coming
back — it cannot see an untracked one.

Delete-check: cannot delete — the whole rule IS the policy; nothing else in
this hook set stops a project-level Claude settings file from coming back.
