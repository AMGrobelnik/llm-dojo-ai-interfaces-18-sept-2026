<!-- hook: selector-stable-refs -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Exported select* factories return fallbacks only as module-level frozen constants or scalars, never a []/{} or new expression minted per call, so snapshot reference equality short-circuits re-renders

run-events-store.ts is built on exactly this contract: the comment above its
selector block (:690) says 'reference equality short-circuits per-component
re-renders', EMPTY_STATE is Object.freeze'd at :131, and every exported
selector there falls back to an EMPTY_STATE field, null, or a scalar. The
store is written on every 500 ms poll tick (use-run-events.ts:65
POLL_INTERVAL_MS = 500; run-events-store.ts:15-24 explains the store exists to
decouple that cadence from React), so one future `?? []` in a new selector
re-renders every subscriber twice a second — and React's only symptom is a
console 'getSnapshot should be cached' warning nobody gates on. Out of reach
of ENFORCED rule-react-compiler-fe: the compiler memoizes component-level
computation, not external-store snapshot identity (useSyncExternalStore
semantics). Which modules the factories live in is NOT part of the contract —
the checker finds them by name pattern across the whole frontend, and the only
census this body keeps is the IMPLEMENTED table below (earlier drafts carried
two others, both wrong about the modules).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: performance-budgets)

Proposed command (implemented at approval):

    scripts/check_selector_stable_refs.py   # superseded; prefix dropped
                                       # so ready.py does not read it as owed — locate exported select*-named factory functions in aii_frontend/{lib,features} store modules, fail on `?? []`, `?? {}`, or `?? new ` inside their bodies (pointing at the module-level frozen-constant pattern EMPTY_STATE establishes)


## IMPLEMENTED 2026-08-26 — `scripts/check_selector_fallbacks.py`

    .venv/bin/python $RULE_DIR/scripts/check_selector_fallbacks.py

Arrives green: 14 exported selectors, 0 unstable fallbacks. Re-measured
2026-08-28: still 14 (10 + 3 + 1), exit 0.

**An earlier draft's account of WHERE the 14 live was wrong twice, and a
checker built from it would have inspected almost nothing.** It said they sat
"across the two stores (`lib/run-events-store.ts`, `features/playbook
playback-store.ts`)". Measured: the directory is `playback`, not `playbook` —
and `playback-store.ts` exports **no** selector at all, only
`usePlaybackStore`. That account no longer appears in the opening; this table
is the census it kept. The 14 are spread over THREE modules:

| module | selectors |
|---|---|
| `lib/run-events-store.ts` | 10 |
| `features/run-viewer/use-details-selection.ts` | 3 |
| `components/progress/node-tree/styles.ts` | 1 |

So the checker scans the tree for `export const select*` / `export function
select*` rather than reading a list. A hardcoded list would have opened two
files, one of which has nothing in it. The name pattern is deliberately loose:
the 3 in use-details-selection.ts are `selection*` helpers and the 1 in
styles.ts is `selectedRowStyle`, not store selectors, and a `select[A-Z]` grep
finds only the store's 10 — which is why an earlier census said 10. Sweeping
the helpers costs nothing, and a per-call literal there would be a real
finding anyway.

What fails is a fallback minted per call — `[]`, `{}`, or a `new` expression.
A module-level constant, `null` or a scalar all pass, because their identity
survives the call, which is the whole point: the store is written every 500 ms,
so a fresh reference re-renders every subscriber each tick and React's only
symptom is a `getSnapshot` console warning.

Bodies are read to the next top-level `export` rather than to end-of-line —
probed with a multi-line selector whose fallback sits on a `return` two lines
below the signature.

Probed nine ways: `?? []`, `?? {}`, `|| []`, `?? new Map()` and the multi-line
form all fire; a frozen constant, `null`, a scalar, and a non-selector export
with the same shape do not.

Delete-check: The delete — dropping the external store for per-component queries — reverses
the store's documented reason to exist (decoupling the poll from React, run-
events-store.ts:15-24). No collapse is available: the fallback constants ARE
the collapsed form. The rule pins the reference-stability contract the store's
design depends on.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Real perf contract the store's own comments declare (reference
equality under a 500ms write cadence), 14/14 conforming factories today, and
no lint tool catches an inline []/{} fallback minted per call in a select*
factory. Narrow, mechanizable, no claimed overlap.
- KEEP: Constrained detection surface (exported select* factories, inline
literal fallbacks) keeps false positives low; the store's documented reason to
exist is this equality contract, and a regression is invisible until the 500ms
poll makes it a render storm.
- KEEP: Documented contract (store comment + frozen EMPTY_STATE) with 14/14
compliance to lock in; scan of exported select* bodies in the two pinned store
modules for inline []/{}/new fallbacks is closed-world and loud. oxlint has no
selector-aware rule for this, so cmd is right.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
THE CONTRACT EXISTS BUT THE 'NO GATE' CLAIM IS WRONG. (Its own selector
census — a `select[A-Z]` grep — is superseded by the IMPLEMENTED table above,
which counts by the checker's pattern; that table is the only census kept.)

Corrected statement of fact:
Every store selector falls back to a frozen EMPTY_STATE field or a scalar
('', false, 0, null) — zero inline literals today. The invariant is NOT
ungated: lib/__tests__/run-events-store.test.ts already fails an inline `??
[]` for any selector registered in FIELD_SELECTORS, and the
`Record<Exclude<keyof RunEventState,"staged">,...>` type plus the key-set case
make registration mandatory for every published state field. The only
residual slice a rule could add is (a) a NEW selector that maps to no
RunEventState field, which the type cannot force into the table, and (b) the
across-a-write identity case, which hardcodes 4 of the store's selectors.
Write the rule to that narrow gap or drop it; the 'no existing gate can catch
this' premise is false.
