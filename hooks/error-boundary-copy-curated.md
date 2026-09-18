<!-- hook: error-boundary-copy-curated -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A React error boundary shows curated copy plus the `digest` ref — never the raw `error.message`; the exception text goes to `console.error`, which every boundary already calls.

Stock today: **GREEN** — re-measured 2026-08-28, the shipped
`scripts/check-error-boundaries.sh` exits 0. All four boundaries
(`app/error.tsx`, `app/global-error.tsx`, `app/(app)/error.tsx`,
`app/(app)/runs/[runId]/error.tsx`) now render curated copy with a
`{/* Curated copy, never error.message */}` comment and an
`error.digest` ref, and keep `console.error` for the exception text. The
cleanup this rule was priced against is already done; approving it costs
nothing and pins the end-state. (The measurement and verification blocks
below predate the cleanup — they record the defect as proposed.)

The script enforces all three H1 clauses. Until 2026-08-28 it checked only
the first two (no raw `{error.message}`, an `error.digest` ref) while the
H1 also asserted the console.error routing — true of all four boundaries,
but a boundary dropping its `console.error` call would have kept passing
while the H1 went on claiming the exception text reaches the log. A third
grep now fails a boundary with no `console.error` call; probed 2026-08-28
(call renamed away in `app/error.tsx` → the script fails naming that file;
byte-identical restore).

## History — the defect as proposed (all four rendered the raw message)

Enumerated by directory rule: `git ls-files | grep -E
'aii_frontend/app/.*(^|/)(error|global-error)\.tsx$'` → 4 files
(`app/error.tsx`, `app/global-error.tsx`, `app/(app)/error.tsx`,
`app/(app)/runs/[runId]/error.tsx`). Ran a two-half check over them (`grep -qE
'\{ *error\.message'` / `grep -q 'error\.digest'`) → output: `RAW-MESSAGE` on
all 4; `NO-DIGEST-REF` on `app/error.tsx` and `app/global-error.tsx`;
verdict=1. I read all four files in full — no comment anywhere declares
rendering the raw message deliberate, and each already calls `console.error`
in a `useEffect`, so the diagnostic path exists and the page adds nothing.
These are `"use client"` boundaries and their own docstrings name CLIENT-side
triggers, which Next does not scrub: `app/(app)/runs/[runId]/error.tsx` lists
"A pure projection (derive-node-status / derive-node-stats / derive-trace)
hitting an unexpected message shape" and "An envelopeToSlim adapter
dereferencing an unknown-typed field with the wrong narrowing" — i.e. what
renders is a raw V8 string like `Cannot read properties of undefined`. The fix
shape is already established in-tree: 2 of the 4 print `<p>ref:
{error.digest}</p>` and offer both `reset()` and a "Back to runs" link, so
only the raw paragraph is out of line, and the two OUTERMOST boundaries are
the worst combination — jargon to the user, no ref for support. Distinct from
rule-toast-headline-curated (PENDING), which bans a raw `.message` as the
FIRST argument of `toast.*`: different surface (a full-page React boundary,
not a toast) and a different payload (a JS runtime exception, not a wire
`detail`).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: error-taxonomy-ux)

Command (BUILT — `scripts/check-error-boundaries.sh`):

    bash $RULE_DIR/scripts/check-error-boundaries.sh

Enumerates by directory rule, so a new boundary is covered the day it lands,
and fails a file that renders `{ error.message`, lacks an `error.digest`
reference, or has no `console.error` call.

**The enumeration in the sentence above is NOT the one the script uses, and
that is a correction rather than a preference.** This body documented
`aii_frontend/app/.*(^|/)(error|global-error)\.tsx$` and recorded it as
yielding 4 files. Inside a script file it yields 2: the `/` is consumed by the
literal `app/` prefix, so top-level `app/error.tsx` and `app/global-error.tsx`
reach `(^|/)` with nothing left, and `^` cannot match mid-string. The same
pattern text did match when run outside a script, so it is inconsistent across
contexts rather than simply wrong. Measured consequence: with it, the gate
reported "clean" while a planted raw `{error.message}` sat in one of the two
files it never looked at. The script uses the anchored
`^aii_frontend/app/(.*/)?(error|global-error)\.tsx$`, verified to enumerate 4.

Verified to bite, three probes with byte-identical restores: a raw
`{error.message}` planted in the top-level boundary fails by name, stripping a
`digest` ref fails by name, and running where no boundary exists exits 2
"could not run" rather than passing over an empty set.

Delete-check: The delete IS the end-state: remove the raw-message `<p>` outright. The
heading already names the class ("This run hit a render error"), `digest` is
the handle support needs, and `console.error` already has the text — so the
paragraph carries nothing a user or an operator gains from. Two of four
boundaries are already at that end-state minus the paragraph. Considered
deleting further: collapse all four into one shared boundary component
parameterised by heading + escape link (they differ in nothing else), which
would make the rule "the shared component is the only body an error.tsx has" —
worth doing, but the root `global-error.tsx` must render its own
`<html>/<body>` with inline styles (no Tailwind, no layout), so it cannot
share, and a 3-of-4 collapse is not obviously better than the grep.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
`git ls-files | grep -E 'aii_frontend/app/.*(^|/)(error|global-error)\.tsx$'`
-> exactly 4: app/(app)/error.tsx, app/(app)/runs/[runId]/error.tsx,
app/error.tsx, app/global-error.tsx. Per-file `grep -nE
'error\.message|error\.digest|console\.error|use client'`: ALL FOUR render a
raw message — app/(app)/error.tsx:35 `{error.message || "Unexpected
exception."}`, app/(app)/runs/[runId]/error.tsx:47 `{error.message ||
"Unexpected exception while rendering the run viewer."}`, app/error.tsx:21 and
app/global-error.tsx:35 both `{error.message || "An unexpected error
occurred"}`. digest ref present in only 2 (app/(app)/error.tsx:36-37,
runs/[runId]/error.tsx:49-50), absent in app/error.tsx and app/global-
error.tsx — matching the claimed RAW-MESSAGE x4 / NO-DIGEST-REF x2 split. All
four are `"use client"` (line 1) and all four already `console.error` in a
useEffect (lines 26, 35, 13, 16). I `cat`ed app/error.tsx and app/global-
error.tsx in full: the only comment in either is global-error's note
explaining why console.error must be explicit — nothing declares rendering the
raw message deliberate. The runs/[runId] docstring (sed -n '1,40p') does list
client-side triggers verbatim: "A pure projection (``derive-node-status`` /
``derive-node-stats`` / ``derive-trace``) hitting an unexpected message shape"
and "An ``envelopeToSlim`` adapter dereferencing an ``unknown``-typed field
with the wrong narrowing". In-tree fix shape confirmed: `grep -n
'Link|href|reset()'` on the two inner boundaries shows both carry `<Link
href="/runs">` alongside reset(). Guard search `grep -rl
'error.tsx|QueryClient' .claude/skills/amg-hooks/rules/` -> no output;
no existing rule or test covers this. Dedupe: grep of claimed_r3.txt for
'boundary|digest|error\.message|curated' returns only rule-toast-headline-
curated [PENDING] (toast first-argument surface) and unrelated
pod/gallery/json rules — different surface, no conflict.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Four boundary files, verified, and it covers both halves (no raw
error.message, digest ref kept) so it subsumes error-boundary-shows-digest.
Distinct from claimed rule-toast-headline-curated, which is scoped to toast.*
call sites.
- KEEP: Ban form over the four enumerated boundaries, with the glob's file
count as the floor. Kept as the single rule for what a boundary renders; I
killed error-boundary-shows-digest as its complement on the identical four-
file population rather than shipping two rules over four files.
- KILL: Same four files and the same fix as error-boundary-shows-digest — at
most one of the pair can survive, and neither should: both delete-checks
converge on collapsing the four hand-written boundaries onto one shared
<ErrorFallback>, after which raw `error.message` is unrepresentable because
only one component renders anything. Also inside the claimed curated-copy
family …
