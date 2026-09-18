<!-- hook: escape-owned-by-layer -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Window/document-level Escape handlers either register with the dismissable-layer stack or stand down on e.defaultPrevented

lib/dismissable-layer.ts pins the contract in prose only ("topmost open layer
owns Escape... defaultPrevented-guarded peers stand down", citing the guided-
setup history where focus-based ownership failed both ways). Two window-level
peers comply: features/search/search-modal.tsx:168 and features/human-
feedback/feedback-input.tsx:184 both check e.defaultPrevented. One does not:
features/gallery/invention-detail.tsx:71-75 adds a window keydown that fires
onBack() on ANY Escape with neither the guard nor layer registration — with a
confirm dialog open above the detail page, one keypress both dismisses the
dialog and navigates away. The convention exists only as a docstring; nothing
says no to the next bypass.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: frontend-components)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_escape_handlers.py  # flags window/document keydown handlers testing "Escape" without defaultPrevented or useDismissableLayer nearby

ADOPTION (2026-08-25): the violation is FIXED. `invention-detail.tsx` now
guards on `e.defaultPrevented` and `e.isComposing`, matching
`feedback-input`'s window-level shape. The page has no text-entry elements,
so that peer's TEXTAREA/INPUT exclusion does not apply here and was not copied.

Verified against history rather than a synthetic fixture: run over the tree
before the fix the gate exits 1 and names `invention-detail.tsx:73` and
nothing else, with the two compliant peers (`search-modal.tsx`,
`feedback-input.tsx`) and the fourth registrar silent. On today's tree it
exits 0.

**Scoping is a heuristic and the script says so.** There is no TS parser on
the Python side, so rather than resolving each listener's callback it reads a
±12-line window around every Escape comparison in a file that registers a
window/document `keydown`. Handlers further apart than that are judged
separately, which is the intent; two interleaved inside one span could mask
each other. That limit is stated in the script's own docstring rather than
left for the next reader to discover.

Delete-check: Mostly deletable: the layer stack IS the collapsed implementation, so the
strongest form migrates invention-detail onto useDismissableLayer and bans
inline window-level Escape listeners outside lib/ entirely; element-level
onKeyDown Escape (inputs, inline-rename) stays exempt — the layer contract
itself documents that target-phase handlers keep local meaning.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Contract exists only in prose with a documented history of failing
both ways; one live divergent handler. Migrate invention-detail onto the layer
stack, then enforce the two allowed shapes.
- KEEP: The contract exists in prose with a documented both-ways failure
history; exactly one non-compliant peer today. Migrate it, then a scoped grep
for window-level keydown/Escape outside the layer stack — small surface, low
FP.
- KEEP: Heuristic but loud: files registering a window/document keydown
listener that handles 'Escape' must reference useDismissableLayer or
defaultPrevented. Small file population, migration of invention-detail first.
Implementable.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
`grep -rn '"Escape"' app components features lib --include=*.tsx
--include=*.ts` (minus tests/stories) returns 9 hits. Only two are
window/document-level outside the stack: `feedback-input.tsx:184` (`if (e.key
!== "Escape" || e.defaultPrevented) return`) and `invention-detail.tsx:73`
(`if (e.key === "Escape") onBack()`, inside a
`window.addEventListener("keydown", onKey)` effect spanning 71-79). `search-
modal.tsx:168` is a React `onKeyDown` on the overlay div, and the same file
registers with th

Corrected statement of fact:
The defect is real and is the only one of its kind: `invention-
detail.tsx:71-79` binds a window keydown that calls `onBack()` on any Escape,
with no `defaultPrevented` guard, no `isComposing` guard, and no layer
registration. Two supporting claims are wrong. (1) search-modal is not a
'window-level peer that complies' — it is a REGISTERED layer
(`useDismissableLayer` at :104); the only genuine window-level guarded peer is
feedback-input.tsx:184. (2) The stated trigger ('a confirm dialog open above
the detail page') does not exist — the gallery renders no dialog. The real co-
open layer is the app-wide SearchModal mounted at app/(app)/layout.tsx:141,
which sits above every (app) route including the detail view; opening it and
pressing Escape closes it (the stack preventDefaults) and still navigates
back, because the unguarded window listener does not read the flag. An IME
composition cancel navigates back too.
