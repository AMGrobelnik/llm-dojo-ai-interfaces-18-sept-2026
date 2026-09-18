<!-- hook: vitest-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_STAGED
# Frontend unit tests related to the staged files pass

`vitest related {staged}` runs every test file whose static import graph
(transitively) touches a staged file — a leaf-component edit runs its
handful of tests (~5 s incl. the ~4.5 s vitest boot floor), while
editing a hub like lib/utils.ts correctly fans out to 460+ tests. This
replaced the full-suite run (~9-15 s on every FE commit); the full
`unit` project still gates every commit via the `vitest-fe-full` hook
(research-monorepo's own set), so a test broken by something OUTSIDE the
staged set (or via a non-import dependency the graph can't see) is
caught at commit rather than missed entirely. The storybook project
gets the same treatment in `rule-vitest-sb-fe`.

## Skipped when a whole-project run already covers the commit

`covering_full_run.py` reads the gate's own merged configuration
(`lefthook dump`) and looks for another pre-commit command that runs
`vitest run --project unit` -- the whole project -- and whose `glob`
selects a staged file, so it really runs this commit. `vitest related`
over that same commit can only select test files that run already, from
the same project, config and tree, so this hook skips and reports
`skipped: the whole 'unit' project is already run this commit by '<name>'`.
Coverage is unchanged; only the second execution of it is gone.

Measured on research-monorepo at 2ea25bd0b91e (2026-09-16): this hook and
`vitest-fe-full` each reported **158 test files / 2187 tests** -- the
entire `unit` project, run twice, because the staged set reached a hub
module and `related` fanned out to all of it. The duplicate cost 70 s of
the 186.6 s gate wall and ~200 CPU-seconds, on a box whose critical path
(the unit-test lane, weighted at 25 inside `app-amg-hooks.slice`) was
starved of exactly that.

The covering command is found by shape, never by name: `general/` is the
portable set and the full run belongs to whichever set a consumer wires
(here `vitest-fe-full`, in research-monorepo's own). Every uncertainty -- no
lefthook, an unparseable dump, a `skip:`/`only:`/`root:` this cannot
evaluate, a glob that will not compile -- means the related run goes
ahead, so the failure direction is always "run more", never "report
less".

`--pool=forks`: vitest's default process pool. vmThreads (V8 VM-context
worker threads) benched faster but its pool fails to terminate after
the run finishes — the process hangs, stalling the hook indefinitely
(verified: `--pool=vmThreads` times out, `--pool=forks`
exits 0 with all 756 tests green — 756 being the suite's size at the
time of the pool benchmark; it is ~1950 today, see the re-measurement
below). (forks + `--isolate=false` and Bun's vmForks were faster still
but had test failures / runtime incompatibilities.)

`--passWithNoTests`: a staged set with zero related tests (config
files, scripts) must not fail. Verified vitest 4 already exits 0 there;
the flag pins that across upgrades. Deleted staged files are passed as
nonexistent paths — verified harmless.

Fix when blocked: from `aii_frontend/`, run `bun run test:unit` to see
failures. Iterate with `bun run test:unit --watch` for sub-second
feedback.

Delete-check: tool-enforced, cannot delete — the tests are the
product's behavioural contract; the only alternative (full suite every
commit) was tried and cost 9-15 s per commit for the same coverage.

All-mode note: commit-scoped by design — whole-tree vitest belongs to
the CI frontend group; running it again in the hooks sweep would double
the suite (the old watcher excluded exactly this via LEFTHOOK_EXCLUDE).

RE-MEASURED 2026-08-24 — the pool guidance stands; the **756 is now
~1950**, the largest census drift found in this tree.

Two independent counts agree the suite has grown roughly 2.6x:
`vitest list --project=unit` enumerates **1952** cases, and a static
count of `it(` / `test(` call sites over the 145 tracked unit test files
gives **1743** — the 209 gap being `.each` parametrisation, where one
call site yields many cases.

This does not touch what the rule is for. The 756 appears inside a POOL
comparison (`--pool=vmThreads` times out where `--pool=forks` exits 0),
so it is incidental to the finding rather than the finding itself, and a
larger suite only sharpens the argument for the pool that completes.
