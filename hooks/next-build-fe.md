<!-- hook: next-build-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 80s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_STAGED
# The frontend's production `next build` passes

Nothing else in the gate runs the production compiler. `tsgo-fe` typechecks,
`oxlint-fe` lints and `vitest-fe` runs the unit suite, and all three pass on a
tree whose `next build` fails: a server-only module imported from a client
component, a duplicate route, a `generateStaticParams` that throws, a
prerendered page that reads a request header — every one of them is a
build-time error and none of them is a type error. Before this hook those
landed on `main` and were found by the deploy.

Scope is the whole frontend because a production build is a property of the
whole module graph; the lefthook `glob:` is what keeps a commit that touches no
frontend file from paying for it.

## Where it builds, and why not in place

`next build` empties and rewrites `distDir` (`.next`). Run in the frontend
directory it destroys a running `next dev`'s `.next` mid-session, which is the
one thing this hook must never do. So the build gets a tree of its own: an
rsync mirror of the frontend at

```
<git common dir>/amg-hooks/cache/next-build-fe/<worktree-id>/
```

whose `.next` is its own. Under the COMMON dir because every linked worktree
has one; keyed by a digest of the worktree's path because two worktrees hold
different trees at the same relative paths.

The mirror is not the index snapshot the rest of the frontend gate runs in, and
that is measured rather than assumed. webpack's filesystem cache is keyed on
absolute module paths, and the snapshot's root carries the index digest, so it
is a different directory every commit. The identical tree built at a new path
took **68.5 s** against **23.5 s** warm at the old one — every commit a cold
build. A mirror at a path fixed per worktree keeps the cache warm, and the
price is that the build judges the working tree rather than the index, the same
exception `vitest-sb-fe` carries.

rsync copies rather than hard-links (`--link-dest`). `next build` rewrites
`tsconfig.json` and `next-env.d.ts` in place, and an in-place write through a
hard link reaches the inode it shares — the checkout's own file. `node_modules`
is excluded and symlinked instead, and `.next` is excluded so `--delete` cannot
take the cache.

The sync is `-c`, not the default quick check. rsync compares size and a
whole-second mtime and preserves only whole seconds, so an edit that keeps a
file's size and lands in the same second as the copy already in the mirror is
invisible to it — and a build of a stale tree is the one way this hook could
pass a commit it should reject. On this frontend (867 files, 126 MB) that is
0.25 s against a 24 s build; the cold copy is 1.3 s.

## Budget

This hook does not fit the 30 s the rest of this set is held to,
and cannot be made to. A production `next build` of a 26-route app is tens of
seconds of compilation; there is no smaller version of it, and the increments
the cache already buys are counted below. So the choice is a pre-commit gate
that costs a build or a class of defect that reaches the deploy, and the second
is what this hook exists to stop. `tools/gate_timing.py` will report it over
the 30 s per-command cap; that is the cap being wrong for this one command, not
the command being slow.

Measured in research-monorepo (Next 15.5.21, webpack, 26 routes):

| run | wall |
|---|---|
| cold (empty cache) | 79.5 s |
| warm, no changes | 42.8 s |
| warm, one-line edit to `lib/utils.ts` | 38.6 s |

Those are a loaded machine (load average 28 to 74 on 10 cores, two other
suites running throughout). Uncontended the same warm build is 23.5 s, so read
the table as the bad case rather than the typical one.

`tools/gate_timing.py` on a commit touching one frontend file, with this hook
present, put the parallel gate wall at **107.6 s** over 88 commands, of which
this one was 87.1 s run alone -- so on that box it is most of the gate. The two
ast-check lanes were also over the 30 s per-command cap, which is the same
conversation, not one this hook started.

The build runs inside `app-amg-hooks-tests.slice`, the shared slice the
unit-test lane uses (`lib/amg_hooks/run_groups.py`), so whatever resource policy
the machine puts on that slice covers the build too and a build shares it with a
concurrent test run instead of competing with it. Where there is no systemd user
manager it runs as-is, exactly as `run_groups` does it.
`AMG_HOOKS_NEXT_BUILD_TIMEOUT_S` caps the wall clock, 600 s by default.

Output is captured and printed only when the build fails; a passing build
prints one line with its elapsed time. The exit code is the build's.

Fix when blocked: read the build error and fix it. A build error is a real
defect in the shipped bundle — there is no suppression to reach for.

Delete-check: tool-enforced, cannot delete — a production build failure is
invisible to every other gate in this set and shows up first as a broken
deploy.
