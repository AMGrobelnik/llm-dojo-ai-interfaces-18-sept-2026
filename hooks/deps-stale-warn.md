<!-- hook: deps-stale-warn -->

| stage | scope | budget | status |
|---|---|---|---|
| post-checkout | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_HOOK_ARGS, RULES_MODE
# After a checkout or merge that changes a lockfile or a migration, the engine says so and names the fix — a notice, never a block

Was the `deps-stale-warn` post-checkout and post-merge lefthook command
until 2026-09-03 (two copies; now one script with the old/new HEAD pair
supplied by the engine as `RULES_HOOK_ARGS`). It is the model for the
engine's exit code 3: WARN — printed like a failure, counted separately,
and never blocking, because a stale venv is a thing to tell the human, not
a thing to refuse a checkout over. Auto-running `uv sync` here could
remove packages installed via optional extras (`--extra runpod`), since
the hook cannot know each clone's intended extras; so it points, and the
human runs it.

`RULES_STAGED` in checkout mode is the old..new file span, but this rule
reads the two shas directly because it needs `git diff` on named paths;
the branch flag (`{3}`) skips file checkouts, which cannot change the
lockfiles' HEAD state. In all-mode it exits 0 — there is no checkout to
describe.

Probes (2026-09-03): `RULES_MODE=checkout RULES_HOOK_ARGS="<sha-before-a-lock-bump> <sha-after> 1"`
prints the `[deps]` notice and exits 3; the same span with flag 0 exits 0
silently; two shas with no lockfile or migration change exit 0; all-mode
exits 0.

Delete-check: delete when the venv and node_modules are provisioned by a
tool that reconciles them on every command (e.g. `uv run` for every
entrypoint), at which point staleness cannot be observed.
