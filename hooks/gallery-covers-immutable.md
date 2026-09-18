# Files under a hard-cached asset prefix are add-or-delete only

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

`next.config.ts` caches the gallery covers for 30 days
(`minimumCacheTTL = 60 * 60 * 24 * 30`) on a comment that used to claim the
filenames are content-addressed. Re-measured independently rather than
trusted: of 37 tracked covers, 32 carry a hash-shaped `_[0-9a-f]{6,}` suffix
and **0 of those 32** are an md5, sha1 or sha256 prefix of their own bytes.
The address contract does not exist. The hard cache rests entirely on nobody
editing a cover in place, and an edit under an unchanged filename serves
stale bytes to every returning client for a month. That has happened once
already, to all 39 covers at once, during a C2PA metadata pass.

The rule was never evaluated: it appears in no verdict snapshot and its
ledger entry is null. There is no practice to reproduce here, only a
well-measured body.

## Mechanism

This is the one converted rule that is a property of the DIFF rather than of
the tree, which is why it is cheap — git already computes it. Both modes
compare the INDEX against `HEAD`, so the question asked is always "what does
this commit change".

| failure mode | mechanism |
|---|---|
| a cover edited under its name | `--diff-filter=M` over the prefix |
| a rename, which is permitted | `--no-renames`: add plus delete |
| the directory moved | population floor, exit 2 |
| an unborn branch | no baseline, exit 2 |

`--no-renames` is passed deliberately: a pure rename IS an add plus a delete
and the rule permits it, so it can never be reported as a modification.
Immutability is not visible in a snapshot of the tree — a whole-tree sweep
would report the original incident forever — so there is no per-file form of
this check and no snapshot form that means anything.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`:
**0 findings**, exit 0 — no cover is modified in the index. Whole-tree
runtime 0.02 s (three runs, all 0.02 s); two git calls and no file reads.

## Fragility

| refactor | effect | guard |
|---|---|---|
| `public/gallery/` renamed | diff matches nothing | floor, exit 2 |
| covers under a second prefix | unguarded | CONFIG is a list |
| run where there is no HEAD | no baseline | exit 2 |
| a cover becomes a symlink | git sees `T`, not `M` | minor gap |

## Residue

The hook cannot tell a legitimate re-export from an accidental one:
add-or-delete is the whole contract, by design.

The rule's own delete-check names the strictly better end state — rename all
37 covers to real content-hash names, after which a whole-tree check verifies
filename against bytes forever and this hook becomes redundant. That was not
implemented here because it is a repo change (renaming 37 assets and every
reference to them), not a checker change, and until it lands modification
really is a property of the diff.

No other hook or unit-test group covers any part of this; the nearest
neighbour is the corrected comment in `next.config.ts`, which is
documentation rather than a gate.
