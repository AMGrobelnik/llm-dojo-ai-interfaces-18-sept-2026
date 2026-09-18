<!-- hook: outside-dismiss-via-hook -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Outside-click dismissal goes through useOutsideClick; no inline document mousedown/pointerdown listeners in app/components/features

`lib/use-outside-click.ts` exists precisely to replace "the inline
`useEffect(document.addEventListener('mousedown', ...))` boilerplate scattered
across popover-style components" (its own docstring) and carries the
non-obvious correctness the inline form forgets: a `useStableCallback` pin so
the effect does not re-bind every render, a lazily-read refs array so the
listener binds ONCE while still seeing the current refs, and `pointerdown`
rather than `mousedown` — the hook's own comment records why, since mouse
events are synthesised for touch only AFTER the gesture resolves as a tap, so a
touch-drag starting outside an open menu never dismissed it.

The tree holds one document-level dismissal listener and it is the hook's, at
`lib/use-outside-click.ts:48` — outside the pathspec this rule bans, by design.
Measured 2026-09-05: the ban grep returns nothing over
`aii_frontend/{app,components,features}`, and **6** call sites go through the
hook —

| module | line |
|---|---|
| `labs/views/workflow-svg-view.tsx` | 76 |
| `run-views/topbar/playback-bar.tsx` | 62 |
| `sidebar/_sidebar/_account-menu.tsx` | 35 |
| `trace/…/linked-chain/chain-content.tsx` | 246 |
| `trace/…/trace-parts/chain-row.tsx` | 208 |
| `trace/…/trace-parts/transitions.tsx` | 44 |

Two element-level listeners remain and are unrelated: a drag handler at
`trace-parts/use-drag-scroll.ts:44` and a scroll-release at
`linked-chain/linked-chain.tsx:164`. Neither is on `document`, so neither is in
the ban's shape.

Type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: frontend-components)

## ADOPTED 2026-09-05 — the command is in the frontmatter, exactly as proposed

Condition: `aii_frontend/` staged. The added-lines COMMIT lane — carried by the
`lib/amg_hooks` dispatcher through `amg-hooks-env`, not the retired rule-engine's bare
`rules-grep` — only means anything at commit (in a sweep it reports the
whole-index stock advisorily), so the condition keeps the rule off every backend
commit for the cost of one `git diff`.

**Proven to bite, 2026-09-05**, in a throwaway `git init` tree under the
scratch dir — never against the repo's own files — with the ban run at commit
through `amg-hooks-env` (whose `commit` stage selects the added-lines lane):

| probe | result |
|---|---|
| clean tree | exit 0 |
| `document.addEventListener("pointerdown", …)` added | exit 1 |
| `document.addEventListener("mousedown", …)` added | exit 1 |
| same line added under `lib/` | exit 0 |

The last row is the one that matters for scope: the hook itself lives in
`lib/`, which the pathspec omits, so the rule cannot fire on the one door it
exists to protect.

### The enforcement carrier, and the drift this note fixed

The check is carried by the `lib/amg_hooks` dispatcher through `amg-hooks-env` — not the
retired rule-engine's bare `rules-grep`. The frontmatter carries no `--tree`
directive, so it maps to the dispatcher's COMMIT lane: the wired `amg-hooks-grep` line
(and the `dispatch.py` AST port that will replace it) judges only the lines the
staged diff ADDS within the pathspec, so committed stock never blocks a commit
and a newly hand-wired listener always does. In a sweep (`AMG_HOOKS_SWEEP=1`) the same
code reports the whole-index stock advisorily. No `$RULES_MODE` shell escape is
needed and none is used — the lane is a property of the carrier, not a
per-condition `[ "$RULES_MODE" = … ]` guard.

Which carrier, precisely: TODAY it is `amg-hooks-env`'s `commit` stage plus
`amg-hooks-grep`, which with no `--tree` greps the staged diff through `grep -nE`.
`svc.sweeping` (`lib/amg_hooks/astcheck.py:406`) is the dispatcher's half of the same
property and it exists, but nothing reaches it — re-verified 2026-09-14, no
set wires a dispatcher command (`tools/_dispatch_wiring.py`'s
`dispatcher_commands()` returns nothing for all four sets), so the
`dispatch.py` port here runs nowhere until one does.

This paragraph is the drift fix. An earlier version of this card described
enforcement through the retired amg-rule-engine bare carrier (`RULES_MODE` /
bare `rules-grep`), which is no longer how any wired hook runs. The live
`research-monorepo/lefthook.yml` line is
`amg-hooks-env … commit -- amg-hooks-grep 'document\.addEventListener\("(mouse|pointer)down"' -- <roots>`,
exactly the shape the `fe-time-format-single-source` sibling reads.

Beside that live grep now sits a TypeScript-AST port (`dispatch.py`, on the
`tsast` helper), inert until cutover: it keeps the grep ERE VERBATIM as a
line-level prefilter (the sole candidate source) and then confirms each
candidate against a real parse — a genuine `document` / `window`
`.addEventListener` call for a dismiss-class event — so a listener quoted inside
a string or a comment is dropped where the flat ERE would falsely match it.
Because the candidate pattern is unchanged, the port only ever removes false
positives; it never widens the ban.

Delete-check: Yes — the hook already deleted this dimension once, and the last
bypass went with it (`040911eca`, 2026-09-04, "fix(frontend): the workflow tip
dismisses through useOutsideClick"). The rule enforces that collapsed
end-state; without it the boilerplate regrows one paste at a time, which is
what the proposal caught.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The hook exists precisely because this boilerplate recurs, and it
carries non-obvious correctness the inline form forgets; one stray to migrate,
then a cheap grep. Distinct mechanism from the Escape-layer rule.
- KEEP: The hook exists precisely to delete this boilerplate and carries non-
obvious correctness the inline form forgets. One offender; post-migration grep
for inline document mousedown/pointerdown listeners is cheap and low-FP.
- KEEP: Grep for document.addEventListener('mousedown'|'pointerdown') in
app/components/features outside the hook. One site to migrate, then a clean
literal ban.

## History — the audit was right, and the migration answered it anyway

The proposal named `features/labs/views/workflow-svg-view.tsx` as a live
bypass. An INDEPENDENT VERIFICATION on 2026-08-22 re-ran every measurement and
returned **wrong**: that site was dismiss-on-any-pointerdown, not
outside-click, a four-line comment declared the difference deliberate (tapping
a different edge must swap the tip, so there is no ref to exclude), and both
properties the "why" said the inline form forgets were in fact present — the
deps array was a boolean, the handler was created inside the effect, and the
phase was already `pointerdown`. Its verdict was that nothing there was the
pre-consolidation state regrowing.

That correction stands and is why the migration was not a bug fix. What it
missed is that the hook already expresses the behaviour: `useOutsideClick`
takes the refs array as a parameter, so an **empty** refs list means nothing
counts as "inside" and every pointer-down dismisses — the exact semantics the
hand-wired listener implemented. `040911eca` passes `[]` and rewrites the
comment explaining the intent, five lines where the audit's were four — it is
at `workflow-svg-view.tsx:70-74` today. That commit is one file, 11+/12-, and
contains no `tipTimer`, `pendingTip` or `clearTimeout` line at all: the tip's
pending-timer cleanup was folded into the same callback LATER, by `c41f25fe0`
(2026-09-04 17:42), and sits at `workflow-svg-view.tsx:78-88`. So the site
reads the same way to a maintainer as the five popovers, and the ban has no
exception to carve out.

The audit's census was four `addEventListener` hits for mouse/pointer/click
across `app`, `components`, `features`, `lib` minus tests and stories: the hook
at `use-outside-click.ts:48`, two element-level handlers, and
`workflow-svg-view.tsx:60`. Re-run 2026-09-05 it returns **three** — the fourth
is now the hook call at `workflow-svg-view.tsx:76`.
