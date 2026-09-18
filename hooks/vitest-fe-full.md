<!-- hook: vitest-fe-full -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 30s | active |
# Before a commit that carries frontend source, the whole frontend unit suite passes — the related-only hook (`vitest-fe`) covers the common case; this is the full run, once per commit

Was the `vitest-fe-full` pre-push lefthook command from 2026-09-03 until
amg-hooks dropped the pre-push stage entirely (owner decision: amg-hooks is
pre-commit only). Re-measured at that move: `vitest run --project unit
--pool=forks` over the whole suite (155 files, 2169 tests) took 8.1 s wall
(`time timeout 600 ./node_modules/.bin/vitest run --project unit
--pool=forks`, 2026-09-15) — over the 5 s per-hook target but comfortably
inside the 30 s hard cap, so it moved to pre-commit rather than being
deleted. Its condition is the same file glob the hook carried before.

Why it exists alongside `vitest-fe`: that hook runs the tests RELATED to
the staged files at every commit, which is the right cost for the common
case; this is the cross-check that related-test selection missed nothing.
Both now run at commit. In all-mode it exits 0 — CI's `frontend` group runs
`bun run test:unit`, the same project, so the sweep would only duplicate it.

Delete-check: delete when `rule-vitest-fe`'s related-test selection is
proven complete (it is vitest's own `--changed` heuristic today), or
re-measure and drop this hook if the suite grows past the 30 s cap with no
cheaper way to run it whole at commit.
