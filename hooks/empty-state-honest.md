# Newly added empty-state copy sits in a function that knows whether its data resolved

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

"No runs found" rendered while the request is still in flight is a confident
statement about data that has not arrived. The same defect was repaired
independently three times in this tree — `search-modal.tsx`, `usage.tsx`,
`files-view.tsx` — and each fix left defensive prose behind, which is what
made it a rule. The `files-view.tsx` case is the instructive one: the file
DID contain an `error` token, in a download handler, with nothing guarding
the list fetch.

The rule was evaluated 177 times and its ledger retained no evidence text
from any of them. Its own body calls it genuinely non-programmable, and that
is half right: the JUDGMENT is not decidable, but the RECURRENCE SHAPE is —
empty copy in a function with no resolution vocabulary anywhere in it — and
that shape is what all three fixes changed.

## Mechanism

A closed proxy over the enclosing function, with the residue named rather
than implied.

| failure mode | mechanism |
|---|---|
| no loading words in scope | per-function scan at the copy |
| the guard is in a `catch` | those scopes blanked before the scan |
| the guard is in a `useEffect` | callback bodies blanked as well |
| the guard is only a comment | comments blanked, same length |
| copy outside any bounded scope | reported, so a parse gap is loud |
| no error vocabulary in scope | advisory on stderr; exit unchanged |
| the copy is in a story or test | not shipped UI, excluded |

Three decisions worth recording. **Errors are advisory and loading blocks**:
on the live tree, `search-modal.tsx` and `usage.tsx` — this rule's own
reference sites, both already fixed — carry no error vocabulary at all,
because their polling source has no separate error path to render, so a hard
error gate would fail the rule's own exemplars. `--strict-errors` promotes it
for a repo that wants it, and exit 3 is not used, because under lefthook
every nonzero exit blocks and an advisory that changed the exit code would be
a block wearing another name.

**The guard must be in the enclosing FUNCTION, and a control head is not a
function**: without that exclusion the scan reads `if (list.length === 0) {`
as the scope, sees no guard inside that branch, and fails the POST-FIX code,
which is the worst possible direction.

**Resolving the guard in an ancestor was rejected.** It is the obvious way to
kill the false positives, and measured it makes the hook decorative: the
pre-fix, genuinely broken `SearchModal` was rendered from a layout carrying
five loading-vocabulary hits of its own, so the ancestor form would have
passed the very defect the rule exists to catch.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`:
**0 in the shipping mode**, because with paths the hook judges only the lines
the staged diff ADDS — the rule's own condition rendered exactly. Whole-tree
runtime 0.10 s (three runs, all 0.10 s) over 222 shipped `.tsx` of 289
tracked.

The no-argument adoption sweep reports **17 blocking and 5 advisory**, and
they were checked rather than counted: 16 are `features/labs/views/*.tsx`,
whose two mount points both gate above them on `r.loadingEntries`, and one is
`features/gallery/invention-detail.tsx:239`, where the prop is a fully
materialised entry with no async source at all. So they are leaves trusting
an invariant held two levels up, plus one static surface — the honest
false-positive rate of the local form, and the price of rejecting ancestor
resolution, which would have been wrong on all three historical bugs. The
repo's own established remedy is to thread a resolution prop through those
views.

Proved to bite on the real files: seeded with the live `features/` and
`components/`, all three historical sites are green in their fixed state, and
renaming `runsResolved` to `runsPassed` in the real `search-modal.tsx` — that
is, reverting the fix — immediately reports it.

## Fragility

| refactor | effect | guard |
|---|---|---|
| `aii_frontend/` renamed | nothing found | floor of 50, exit 2 |
| the copy convention changes | trigger misses | not guarded |
| a new query library's words | guard unseen | one CONFIG regex |
| components move off `.tsx` | out of the glob | CONFIG knob |
| a function mis-bounded | guard invisible | reported, not skipped |

The trigger is an enumeration of copy patterns, inherited from the rule's own
condition; widening it raises the false-positive rate, and that is the honest
limit of a copy-pattern trigger.

## Residue

The hook proves vocabulary is IN SCOPE, never that the guard is WIRED — that
the flag gates the same query the copy is about, in the right direction,
before the right return. That is exactly what the 177 agent evaluations were
nominally for, and exactly what none of them recorded evidence of. A guard
expressed with no vocabulary at all — a bare `data === undefined` on an
oddly-named identifier — reads as a false positive here.

A stronger form exists and was measured: a registry mapping each empty-copy
site to a co-located story asserting loading precedence, which
`search-modal.stories.tsx` already does behaviourally under `vitest-sb-fe`.
Only 4 of the 22 sites have such a story today, so that form would land at 18
findings and demand 18 new stories before it could bite.
