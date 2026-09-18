<!-- hook: rotating-loader-one-door -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Rotating-loader UI funnels through the Spinner primitive or registers with useAlignedAnimationStart — no raw animate-spin outside components/ui — so spinners share one phase and the a11y protocol

Rotating-loader UI funnels through the Spinner primitive or registers
with useAlignedAnimationStart — no raw animate-spin element outside
components/ui — so all spinners share one phase and the label/decorative
a11y protocol.

components/ui/spinner.tsx's own docstring declares the invariant ("ALL
rotating-loader UI in the app should funnel through this") and encodes the
a11y protocol (label only when the spinner is the sole state carrier — the
case search-modal.tsx:43-47 documents). Conforming: node-tree/active-
spinner.tsx:27, _starting-run-row.tsx:31, pending-icon-ring.tsx:14 all call
useAlignedAnimationStart. Violations at proposal time — all since migrated
or exempted (see ADOPTION below; the gate now exits 0): welcome-page.tsx:258
(raw Loader2 — its submit spinner was out of phase with every aligned peer,
the exact jumble spinner.tsx describes; now Spinner at :258),
api-keys.tsx:332 (raw Loader2; now Spinner at :333), app/loading.tsx:5
(hand-rolled border div; kept and exempted, the `spinner-phase-deliberate:`
rationale at :14-22 and the ring at :23), files-view.tsx:389,432 (RefreshCw
spin-on-refetch, unaligned; now registered via useAlignedAnimationStart at
:321-322, the sites at :403 and :448).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: fe-a11y-ux)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_spinner_door.py  # tracked .tsx under app/components/features, comments stripped: each animate-spin file imports the primitive, calls useAlignedAnimationStart, or carries a justified opt-out

Condition: `git diff --cached --name-only -- 'aii_frontend/app/**' 'aii_frontend/components/**' 'aii_frontend/features/**' | grep -q .`

Delete-check: This is a delete rule: the four raw duplicates get migrated onto the existing
primitive/hook and the rule enforces the deleted end-state (zero raw animate-
spin outside components/ui, stories excluded). Deleting the primitive instead
would forfeit both phase sync and the labeled-vs-decorative protocol two files
document.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: One-door onto an existing primitive whose own docstring declares the
invariant; four raw animate-spin duplicates to migrate then hold at zero.
Sibling of pending rule-one-help-tip — same accepted house shape, real a11y
protocol behind it.
- KEEP: Four live raw animate-spin duplicates outside the primitive; enforcing
the deleted end-state after migration is a one-line grep — exactly the house
one-door pattern.
- KEEP: Deletion-shaped: migrate 4 raw animate-spin sites onto the documented
primitive, then hold at zero outside components/ui. Trivially mechanizable,
non-vacuous by construction (fires on any new raw spinner).

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **exact.**

The violation list reproduces to the file and line. Measuring "raw
`animate-spin` outside `components/ui/`, in a file that does not call
`useAlignedAnimationStart`", excluding stories and tests:

| file | verdict |
|---|---|
| `welcome-page.tsx:258` | violation |
| `api-keys.tsx:332` | violation |
| `app/loading.tsx:5` | violation |
| `files-view.tsx:389,432` | violation |
| `active-spinner.tsx` | conforms (registers) |
| `_starting-run-row.tsx` | conforms (registers) |

Four files, five sites, and the two conforming files are excluded for the
stated reason rather than by luck — each calls `useAlignedAnimationStart`
twice.

Not fixed here. Routing four call sites through the `Spinner` primitive
changes rendered markup across three features and is a design decision,
unlike the `motion-reduce` variant removed alongside this, which was a
provable no-op. `app/loading.tsx` is named by BOTH this rule and
`rule-reduced-motion-covenant`, so one file carries two independent
findings — the same pattern as `run_resume.py` in the enforced tree.

ADOPTION (2026-08-25): four of the five sites are MIGRATED, the fifth is
exempted with its argument in the file, and the gate holds the result at zero.

`welcome-page.tsx`, `api-keys.tsx` and both `files-view.tsx` sites were raw
`Loader2` — the same glyph the primitive renders — so routing them through
`Spinner` was visually neutral. It was neutral only because the primitive grew a
`strokeWidth` passthrough first: welcome-page pairs its spinner with an `ArrowUp`
at 2.5, and without that, adopting the primitive would have silently thinned one
glyph. "Adopt the door" must not cost a visual regression nobody asked for.

`app/loading.tsx` is a different case and is NOT migrated. It draws a
border-ring, not a `Loader2`, so the primitive would change a user-visible
shape; and the phase argument does not reach it. Phase is a claim about
SIBLINGS, and this loader has none — measured: `app/layout.tsx` renders only
`Providers` around `children`, and route-level loading UI REPLACES those
children, so nothing else can be on screen spinning beside it. The second door
is no better: `useAlignedAnimationStart` would ship hydration JS to align a lone
element with itself. Changing a rendered glyph to make a check green is the
wrong trade, so the file carries `spinner-phase-deliberate:` with the reason
stated where the next reader meets the code. A raw spinner anywhere else — a
copy of this one included — is still caught, because the exemption is per-file
and carries its own argument.

**Python, not the proposed shell one-liner, because comments must be stripped.**
That is not tidiness: `rule-reduced-motion-covenant` recorded the trap on this
exact file — after its fix, a grep for `motion-reduce:animate-` STILL matched
`app/loading.tsx`, because the comment left behind quotes the class that was
removed. A `grep -rl 'animate-spin'` gate would flag files that only discuss
spinners, and would have read the very comment written to explain compliance as
the violation. The checker removes block and line comments first.

A bare marker does not pass. Taking the text after it and stripping would have
eaten the newline and read the FOLLOWING line as the reason, so
`spinner-phase-deliberate:` alone would have borrowed the justification under
it; the rest of that LINE is taken first, then stripped.

Proven to bite in a throwaway tree: a raw spinner and a reason-less marker are
both named, while the primitive, the hook, a justified marker, a comment-only
mention, `components/ui/` and `.stories.tsx` all stay silent. Real tree: 0.
