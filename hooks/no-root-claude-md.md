<!-- hook: no-root-claude-md -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

# No CLAUDE.md is committed at the repo root

The author keeps no root `CLAUDE.md` in `notes-repo` or `research-monorepo`: project
instructions live elsewhere (a skill, a nested `CLAUDE.md`, README prose),
never in a root file every agent auto-loads. Checks the index — `git
ls-files -- CLAUDE.md`, respecting `GIT_INDEX_FILE` under `git commit
--only` the same way every other rule here does — so it fails equally on a
commit that still carries an old tracked root `CLAUDE.md` and on one that
adds a new one, and it does not fire on a nested `pkg/CLAUDE.md`.

Fix when blocked: delete the root `CLAUDE.md` (and stage the deletion), or
move its content into a nested `CLAUDE.md`, a skill, or README prose, and
commit that instead.

Delete-check: cannot delete — the whole rule IS the policy; nothing else in
this hook set stops a root `CLAUDE.md` from coming back.
