<!-- hook: bun-audit-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 5s | active |
# The resolved frontend dependency set carries no high or critical advisory

`bun audit` over `bun.lock` — the whole resolved tree, direct and transitive —
against npm's advisory service. Triggered by `bun.lock` and `package.json`,
the only two files that can change the answer.

The **lock** is audited, not `node_modules`. A stale install cannot hide a
finding and a missing one cannot fake a clean, which matters here because
every session's worktree symlinks `node_modules` at the primary checkout.

## The floor is high+

`bun audit` reports everything it knows and has no severity floor of its own,
so the JSON is filtered in the hook. Today's research-monorepo tree carries three
findings below the line — an `esbuild` dev-server file read on Windows, a
`@babel/core` `sourceMappingURL` read, a `@vitest/mocker` path traversal —
all dev-only, none reachable from a deployed artifact, and blocking on them is
how a gate gets routed around. high and critical are the ones that describe
something an attacker can do to a running deployment.

## The allowlist

`BUN_AUDIT_IGNORE` names a file of `GHSA-xxxx-xxxx-xxxx  # reason` lines (the
numeric advisory id also matches). Everything else blocks, so a NEW finding
still fails while a tracked one does not. A path naming no file warns and
audits with nothing allowlisted — the gitleaks posture: a missing config must
never silently disarm the scan. research-monorepo needs no entries today; the four
findings that existed when this hook landed were fixed at the root instead:

| package | advisory | fix |
|---|---|---|
| next 15.5.21 | GHSA-p293-qw3h-jr36, GHSA-2xp9-vwfh-vxw4 (critical, RCE) | → 15.5.25 |
| sharp 0.35.3 | GHSA-rgj7-g3m4-5g8c (high, libheif) | override → ^0.35.4 |
| js-yaml 4.3.1 | GHSA-2883-xcg3-v3hh (high, CPU exhaustion) | override → ^4.3.2 |

Both transitive ones were already pinned through `overrides` in
`package.json`, so the fix was raising the floor and re-locking — which is the
normal shape of a transitive fix and the reason an allowlist entry is rarely
the honest answer.

## Cache, and the timings

Keyed on a sha256 of `bun.lock` plus the allowlist, under
`<git-common-dir>/amg-hooks/cache/bun-audit-fe/` of the REAL checkout —
resolved from `AMG_HOOKS_WORKTREE`, since the hook can run inside the
whole-index snapshot, whose `.git` is reaped at post-commit. Sibling worktrees
share one warm cache.

Measured 2026-09-16 against research-monorepo (691 packages, aarch64, bun 1.3.14):

| run | wall |
|---|---|
| unchanged lock (cache hit) | **0.29 s** |
| lock changed, service reached | 0.52 s |
| lock changed, four findings to print | 0.39 s |

bun audits the lock server-side in one request, so even the miss is cheap —
unlike the Python side, where the cold path costs 51 s. The cache is still
worth having: it removes the network from the common case, which is what makes
this hook safe on a flight.

## Offline

An advisory service that cannot be reached is not a finding: `check.sh` warns
and exits 0. Nothing is skipped, only deferred — the lock is unchanged, so the
next commit on a reachable network audits the same content and blocks then. A
non-connection failure with no report is exit 2 (`cannot run`), which blocks:
that one IS a broken check rather than a missing network.

Delete-check: tool-enforced, cannot delete. A transitive advisory arrives
without a diff anyone here writes, so nothing else in the gate can see it.
