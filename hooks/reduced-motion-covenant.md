<!-- hook: reduced-motion-covenant -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Reduced motion is honored end to end

Reduced motion is honored end to end: globals.css keeps the blanket
prefers-reduced-motion guard (0.01ms duration, single iteration,
scroll-behavior auto — all !important), no motion-reduce: utility
re-introduces motion, and every file issuing a JS smooth scroll
(`behavior: "smooth"`) consults the reduced-motion query itself.

The blanket at app/globals.css:452-461 is load-bearing beyond CSS:
lib/spinner-phase.ts:58-67 sizes its bounded rAF retry to the guard's exact
behavior (animation finishes in 0.01ms and drops out of getAnimations()). The
blanket provably cannot reach JS scrolls — components/progress/node-tree/node-
tree.tsx:372-381 documents this (WCAG 2.3.3) and gates its scrollBy on
window.matchMedia("(prefers-reduced-motion: reduce)"); use-flying-dots.ts:41
gates its rAF loop the same way. Live violation of clause two at proposal time (since fixed — see below):
app/loading.tsx:5 carried `motion-reduce:animate-[spin_1.5s_linear_infinite]`
— a backwards variant that re-declared spinning FOR reduce users, defeated
only by the blanket's !important; it also bypassed the Spinner primitive.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: fe-a11y-ux)

Mechanism (implemented 2026-08-26, `scripts/check_reduced_motion.py`):

    .venv/bin/python $RULE_DIR/scripts/check_reduced_motion.py

Python rather than the proposed shell script, because stripping comments is
the whole check and doing it in `sh` would be the fragile part.

**The clause-two violation is FIXED, and its remains are a trap.** The only
occurrence of `motion-reduce:animate-` in the tree is now inside a JSX comment
in `app/loading.tsx` explaining why the variant was removed. A grep flags that
fix as the defect, so comments are stripped before anything is matched.

**Clause three does not contain its own literal, and missing that checks an
empty population.** `node-tree.tsx` writes `behavior: reduceMotion ? "auto" :
"smooth"`, so searching for `behavior: "smooth"` finds ZERO sites and reports
a clean result that means nothing. Matching a code-context `"smooth"` finds
the 1 real site, which is gated.

Measured 2026-08-26: the blanket is present with 4 `!important` declarations;
703 frontend sources carry 0 live `motion-reduce:` motion variants; 1 file
issues a JS smooth scroll and it consults the query, citing WCAG 2.3.3.

Probed seven ways: a removed blanket, a blanket losing `!important`, a live
variant and an ungated smooth scroll all fire; a compliant baseline, a variant
appearing only in a comment, and the gated ternary form do not.

Superseded proposal:

    scripts/check_reduced_motion.sh  # (a) grep the 4 declarations inside globals.css's @media (prefers-reduced-motion: reduce) block; (b) ! grep -rE 'motion-reduce:(animate|transition)-' --include='*.tsx' | grep -v -- '-none'; (c) for f in $(grep -rl 'behavior: "smooth"' app components features lib); do grep -q 'prefers-reduced-motion' "$f"; done

Delete-check: The blanket already IS the deleted form — one guard instead of per-keyframe
gating (its own comment: tw-animate-css ships none). The per-site JS checks
cannot be deleted into it because CSS cannot suppress an explicit smooth
argument; the rule pins that division of labor. The loading.tsx motion-reduce
utility gets deleted outright.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The CSS blanket provably cannot reach JS smooth scrolls, so the per-
site media-query consultation is a real, unguarded contract that spinner-
phase.ts already depends on structurally. No claimed a11y rule exists at all.
Keep.
- KEEP: The blanket guard is load-bearing beyond CSS (spinner-phase rAF sizing
depends on it) and JS smooth-scrolls provably escape it; three grep-able
clauses, real a11y class, cheap.
- KEEP: Three concrete greps (globals.css guard text, motion-reduce:-with-
animate utilities, behavior:'smooth' files must reference prefers-reduced-
motion or the shared helper) — each closed and loud. The JS-scroll half is the
real gap the CSS blanket provably cannot reach.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **held; the clause-two
violation was real and is now FIXED.**

`app/loading.tsx:5` did carry
`motion-reduce:animate-[spin_1.5s_linear_infinite]`, and it was the only
`motion-reduce:animate-` in `app/`, `components/` or `features/`. Removed
in `0949ac964`.

The blanket guard is exactly as described — `globals.css` applies
`animation-duration: 0.01ms !important`, `animation-iteration-count: 1
!important`, `transition-duration: 0.01ms !important` and
`scroll-behavior: auto !important` to `*, *::before, *::after`. That is
why the backwards variant rendered harmlessly, and why the covenant's
first clause matters: narrow the blanket and the variant would have taken
effect at 1.5s infinite.

**Implementation note that bit immediately.** After the fix, a grep for
`motion-reduce:animate-` STILL matches `app/loading.tsx` — the comment
left in place quotes the removed class so the next reader knows why it is
absent. Any check for this rule must exclude comments, or it flags the
one file that documents compliance.
