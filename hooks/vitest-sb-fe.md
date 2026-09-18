<!-- hook: vitest-sb-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_STAGED
# Storybook component tests related to the staged files pass

The 185 stories (re-measured 2026-08-22; 128 when this rule landed)
are the component test suite — 50 carry `play` functions asserting real
behaviour — but they were gated only by CI, so a broken component
surfaced minutes after the push instead of at the commit.

Runs the whole storybook project, not `related`: `RULES_STAGED` is the
whole tracked index (see `amg-hooks-env`), so `related --run` over it
selects every story anyway — measured identical 67 files / 241 tests,
16.0 s vs 13.2 s for the plain full run, the 2.8 s difference being a
graph walk with nothing left to narrow. Full suite ~13.2 s wall, ~6 s of
it a fixed Vite + Chromium boot that does not grow with the diff.

That boot floor is also why this cannot be made much faster:
--maxWorkers 8/12/16 were indistinguishable, because the run is already
CPU-saturated rather than under-parallelised.

The glob is narrowed to ts/tsx: the storybook project only renders
components, so js/mjs/cjs config edits have no stories to relate to and
would pay the browser boot for nothing.

Fix when blocked: from `aii_frontend/`, run
`bun run vitest --project storybook` (or the failing story in watch
mode) to see and fix the component regression.

Delete-check: tool-enforced, cannot delete — the stories with `play`
functions are the only automated check of real component behaviour; the
alternative (CI-only gating) is exactly the state this replaced.

All-mode note: commit-scoped by design — whole-tree vitest belongs to
the CI frontend group; running it again in the hooks sweep would double
the suite (the old watcher excluded exactly this via LEFTHOOK_EXCLUDE).
