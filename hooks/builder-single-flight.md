# Every `docker buildx bake` caller waits on one shared flock, and every caller resolves that lock to the same path

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

A build started while the watcher was already building took
`mathlib_warmup` from CACHED to a full Mathlib re-clone (`git index-pack`
running 13+ min), and the whole build from 386 s to 2712 s, with load at
17-18 on 10 cores. Two emulated bakes do not halve wall-clock: they lengthen
both and evict the registry buildcache that `aii-builder-keepalive.sh`
exists to keep warm. Downstream, that eviction produced a 1.98 GB layer
which could not be pushed, and deploys sat on a stale image for two days.

Three bake entry points exist by design — a poll loop
(`aii-image-watcher.sh`), a cron (`aii-builder-keepalive.sh`) and a manual
build (`build_push_image.sh`) — so the concurrency dimension cannot be
deleted. `d1bafb661` collapsed it instead: one shared lock file that every
entry point takes before it bakes.

The obvious check for that is `grep 'flock.*aii-builder.lock'`, and it is
wrong in both directions. It needs both tokens on one line, while the landed
code names the path in a variable and spends it far away, so it matches
nothing in any of the three correct files. And a check that only looks for
`flock` passes three callers that each lock correctly on three different
paths, which serializes nothing at all.

## Mechanism

`check.py` discovers the population by CONTENT — every git-tracked `*.sh`
whose index blob runs the bake verb — so a fourth caller, or a renamed one,
joins the population instead of escaping a hard-coded list. Content comes
from the index (`git ls-files -s` then one `git cat-file --batch`), never
from the working tree, because a hook runs while other agents hold unstaged
edits that the commit will not contain.

| failure mode | mechanism |
|---|---|
| a new or renamed caller | population found by content |
| a caller loses its `flock` | per bake invocation, `-w <n>` first |
| each caller locks a different path | values compared across files |
| one file, two bakes, two locks | per-file value set > 1 |
| a lock variable never assigned | reported; cannot be compared |
| prose naming the bake verb | full-line `#` comments dropped |
| the population collapses | below 3 callers, exit 2 |

Continuation lines are joined first, so a `flock` and the bake it guards
count as one command however the invocation is wrapped. The lock variable is
resolved to its first literal assignment in the same file, and the majority
value is treated as the shared lock, so the minority caller is named as the
outlier rather than the two that agree.

The relation is whole-population: "does my lock agree with every OTHER
caller's" cannot be answered from one changed file. Discovery therefore
always runs in full, and PATH arguments narrow only REPORTING. When no PATH
names a discovered caller — a commit touching `docker-bake.hcl` alone — the
whole population is reported, so the run cannot be triggered and then say
nothing.

Vacuity is split two ways. Fewer than three callers means the walk went
blind, not that the tree got safer: `cannot run:` and exit 2. No caller at
all, or no git checkout, means this is not the repository the hook is about:
`skipped:` and exit 0.

## Stock

**0 findings.** Measured against `/home/<user>/projects/research-monorepo` at
`3f1060fa7499` (index, 2026-09-08), whole tree, three runs: 0.04 / 0.03 /
0.03 s, median **0.03 s** over 37 tracked `*.sh` files.

Population: three callers, all resolving to the byte-identical
`"$HOME/.local/share/aii-builder.lock"`.

| caller (under `scripts/`) | var | `flock -w` |
|---|---|---|
| `local/build_push_image.sh` | :67 | 7200 @ :161, :176 |
| `local/watchers/aii-builder-keepalive.sh` | :65 | 7200 @ :287 |
| `local/watchers/aii-image-watcher.sh` | :55 | 5400 @ :243 |

Two of those files also mention the bake verb in prose (`:34` and `:155`);
both are full-line comments and neither is a finding.

Re-measured after the consumer moved on, at HEAD `eaf82761cddc` (2026-09-08), in one sequential pass over all eleven hooks of this
integration: **0 findings**, whole-tree 0.02 s. The figures above are
from the earlier HEAD and are unchanged by the move.

## Fragility

| refactor | effect | guard |
|---|---|---|
| bake hidden in a helper | marker gone | floor -> exit 2 |
| a caller in Python or Make | unseen | glob is a CONFIG knob |
| `flock` moved into systemd | red | correct for the statement |
| one caller's lock renamed | drift | outlier named by value |

Every one of those knobs — the bake marker, the shell glob, the caller
floor, the name `flock` — is an entry in the `CONFIG` dict at the top of
`check.py`, each with a comment saying what breaks when that thing moves.

## Residue

Presence is asserted, not serialization. A lock taken through a file
descriptor (`exec 9>lock; flock 9`), through a systemd unit, or by a wrapper
script reads as absent, and a `flock -w` whose wait is itself a variable is
not recognised. Whether a given wait is long enough for the build it guards
is not judged either — the keepalive's own timeout budget is a separate
question, argued in `aii-builder-keepalive.sh`. Nothing here observes two
builds actually colliding; the behavioural guarantee follows from the
presence of one agreed lock, which is what the rule's own filter verdicts
accepted.

One consumer document is now wrong and this hook does not repair it:
`scripts/local/watchers/README.md:398` still opens "It is enforced by
nothing" under a heading saying `--once` can collide with the service, which
stopped being true when the shared lock landed and is false again once this
hook ships — a one-line doc fix for the owner, not for the checker.
