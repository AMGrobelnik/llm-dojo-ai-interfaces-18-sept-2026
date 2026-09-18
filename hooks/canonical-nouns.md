# New identifiers use the canonical run-tree nouns: phase, module, iteration, task

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 2s | active |

`status` is `active` even though the tree carries 855 findings: the hook is
file-scoped and judges only the lines a commit ADDS, so the backlog never
blocks a commit that does not create new debt. See **Stock**.

## Why

The top-level run-tree concept answers to several names at once, and the
cost lands on whoever reads the tree next. The vocabulary is fixed —
**phase** (not `mdgroup`, `cardgroup`), **iteration** (not `round`,
`cycle`), **module** / **task** (not `substep`) — and the proof that two of
these are one concept is in the code: `_5_deploy_gh.py` contains
`a.iteration == round_no`, the two spellings inside a single expression.

The rule this replaces was verified by an agent, and its pre-gate regressed
on ordinary English. Matching a bare `round` fired on "around",
"background", "grounds" and on builtin `round()`: measured over the last 30
commits touching `*.py`/`*.ts`/`*.tsx`, it demanded judgement 5 times where
1 was warranted, and 4 of the 5 diffs contained no run-tree vocabulary at
all. That is the expensive false positive — a check that keeps asking for
judgement on nothing trains its reader to answer without looking. The
compound rule below is the mechanical form of the fix.

## Mechanism

`check.py [PATH...]` tokenizes the lines the staged diff ADDS for those
paths, splits every identifier into word parts on `_`, `-` and camelCase,
and matches the parts — plus every contiguous join of them, plus their
singular forms — against the synonym map in `CONFIG`.

| case | mechanism |
|---|---|
| new compound name | split into parts, match the map |
| new file name | the stem is split the same way |
| plural spelling | singularised parts match too |
| cites a name in HEAD | a HEAD grep, gitlink excluded, passes it |
| bare `round(x)` | a candidate must be a compound |
| `round-trip` in prose | content tokenizer excludes `-` |
| `roundRobin`, `hourCycle` | joined-spelling allow list |

Two of those rows carry the design.

**The HEAD lookup replaces a judgement.** An added line that mentions
`mdgroup_start` or a `round_no` parameter is a reference to stock, not a
new name; an identifier that already exists at HEAD is therefore passed.
One lookup, no parser, so comments and docstrings are covered and `.ts` and
`.tsx` behave exactly as `.py` does. A file name is treated the same way,
and additionally must be absent from `git ls-tree HEAD` to count as new.

HEAD rather than the index, deliberately: `git commit --only` builds a
temporary index of HEAD plus the named paths, so every identifier the commit
ADDS is in the index by construction and asking the index there would score
all of them as stock. The grep declines recursion — research-monorepo sets
`submodule.recurse=true`, and a rev grep obeys it, so an identifier present
only in the vendored hooks repo answered "already stock" and the ban stopped
biting for it. A gitlink is another repository and carries its own gate.

**A candidate must be a compound.** A single-word token is prose or a
builtin call. This is what keeps "around" and `round(x)` out, and the
content tokenizer excludes the hyphen for the same reason: no Python or
TypeScript identifier contains one, so allowing it only glues English
together. Measured: dropping the hyphen removed 44 census lines, all of
them "round-trip", "per-round" or "round 1".

Added lines come from `git diff --cached -U0 -- <path>` — HEAD to index, the
lines the commit adds — falling back, only for a path git does not track at
all, to the whole file on disk, so a person can run it by hand on a
brand-new file they have not staged yet. The UNSTAGED diff used to sit
between those two and was the working-tree read this checker had left: it
fires exactly when a path's staged diff is empty, which is the ordinary case
in a checkout several agents share, so a peer's half-written identifier
failed a commit that did not contain the line. The no-argument
mode is the whole-tree census; it reads the INDEX (`git ls-files -s` plus
one `git cat-file --batch`), never the working tree, so a concurrent
agent's unstaged edit cannot move the count. **The census is a reporting
mode, not a gate** — the lefthook fragment always passes `{staged_files}`,
so the census never runs at commit.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7499` (2026-09-08), population 1482 tracked `.py`/`.ts`/`.tsx`.
The census reports **855 findings in 150 files**:

| synonym | lines | files | names |
|---|---|---|---|
| `round` | 468 | 79 | 77 |
| `mdgroup` | 326 | 74 | 30 |
| `substep` | 55 | 10 | 16 |
| `cycle` | 6 | 2 | 2 |
| `cardgroup` | 0 | 0 | 0 |

By top-level directory:

| directory | findings |
|---|---|
| aii_frontend | 662 |
| aii_pipeline | 111 |
| aii_lib | 73 |
| aii_server | 9 |

Three of those are FILE names: `round-row.tsx` and `substep-row.tsx` under
`aii_frontend/components/progress/node-tree/`, and
`aii_frontend/features/trace/slice-trace-by-rounds.ts`.

**This backlog is wire-frozen and is not to be driven to zero.** The
`mdgroup_*` event names are pinned by historical journals, which can no
longer be rewritten; `round_commit_message` builds the subject
`Round {n}: {k} artifacts` for commits already pushed into generated paper
repos that are no longer ours; and "subsequent rounds" appears in reviewer
prompt text, where a rename is a behaviour change rather than a rename.
Whether any of the remainder is renamed is an owner call. The hook exists
to stop new debt, and it ships `active` because file scope means the stock
can never block a commit that does not touch it.

Runtime: whole-tree census **1.81 s** (median of three: 2.27 / 1.81 /
1.74 s; eight runs on a contended box spanned 1.74-3.92 s). Run over the 25
currently-modified `.py`/`.ts`/`.tsx` files in the working tree — 1555 added
lines — it exits 0 in **0.13 s** with no findings. A candidate identifier
adds one `git grep` over HEAD, measured at ~0.2 s and memoised per name.

Re-measured after the consumer moved on, at HEAD `eaf82761cddc` (2026-09-08), in one sequential pass over all eleven hooks of this
integration: the same **855 findings in 150 files** with an identical per-synonym and per-directory breakdown, census 1.53 s. The figures above are
from the earlier HEAD and are unchanged by the move.

## Fragility

| refactor | effect | guard |
|---|---|---|
| the synonym map is trimmed | passes all | probe self-test |
| an allow entry hides a word | passes all | probe self-test |
| the splitter drops camelCase | passes all | probe self-test |
| the frontend changes suffix | population falls | min-population |
| the backlog is renamed | census goes green | correct by design |

The first three are the ones a population count cannot see: the file count
is unchanged while the check has stopped detecting anything. So before any
real result is trusted, a synthetic `probe_<word>_name` built from the
configured map itself must be flagged; if it is not, the check exits 2 with
`cannot run:` rather than reporting a clean tree. The population floor is
100 against a measured 1482. Outside a git checkout it prints `skipped:`
and exits 0 — that is an environment it cannot run in, not a tree that
moved.

## Residue

Deliberately not enforced, each with its reason:

- **`group`, `stage` and `step` are dropped** from the original synonym
  list. They are ordinary English and ordinary technical vocabulary here —
  Docker build stages, the `steps/` package, "group by" — so banning them
  reproduces the false positive this hook exists to avoid. The unambiguous
  compounds `mdgroup`, `cardgroup` and `substep` are kept.
- **A single-word rename** (`stage = 3`, `cycle = 2`) is not caught. That
  is the price of the compound rule, and it is worth paying at a measured
  5-to-1 false-positive ratio for the alternative.
- **A new name that reuses a spelling already elsewhere in the tree** reads
  as a citation and passes. The original rule's own PASS clause has the
  same hole; closing it would need the judgement the HEAD lookup replaces.
- **Whether an existing synonym should be renamed** is not judged at all.
  The census prints the backlog; sizing and sequencing it is an owner call,
  and part of it cannot be renamed at any price.

This hook stays in the `research-monorepo` set: the vocabulary is this project's
run tree, not a general convention.
