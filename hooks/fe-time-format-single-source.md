<!-- hook: fe-time-format-single-source -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Date/time display strings come from lib/format.ts helpers — no inline toLocaleDateString/toLocaleTimeString in features, app, or components

lib/format.ts's own header declares it the 'single source of truth' born
from 'per-file copies with subtly drifting rounding rules' — but date/time
formatting never made it in: its only exports were formatDurationMinutes,
formatUsd and formatTokensPerMin, none of them date/time. Four inline sites
formatted four different things (date, date, month+year, clock), and two of
them had already drifted apart.

## LANDED 2026-09-04

`lib/format.ts` gained three exports — `formatDate`, `formatMonthYear`,
`formatTime` — and all four inline sites now call them. Whole-tree hit count
under the command above is **0**, which is what earns the `--tree`.

Sites, each `was` an inline call, `now` a `lib/format.ts` helper:

- `run-config/sections/usage.tsx:34` — `toLocaleDateString` with
  month/day/year fields → `formatDate`
- `labs/views/story-view.tsx:133` — `toLocaleDateString` with
  `dateStyle: "medium"` → `formatDate`
- `gallery/invention-detail.tsx:25` — `toLocaleString` with
  month/year fields → `formatMonthYear`
- `run-views/_shared/render-message.tsx:215` — `toLocaleTimeString`
  with 2-digit hour/minute, `hourCycle: "h23"` → `formatTime`

### The drift was real, and it was invisible from an en-US desk

The two date sites are the pair worth the rule. `dateStyle: "medium"` and the
explicit-field spelling are the **same string** in en-US, en-GB and fr-FR —
and a different one everywhere else:

| locale | usage table | run report | now |
|---|---|---|---|
| en-US | `Sep 4, 2026` | `Sep 4, 2026` | `Sep 4, 2026` |
| de-DE | `4. Sept. 2026` | `04.09.2026` | `4. Sept. 2026` |
| ja-JP | `2026年9月4日` | `2026/09/04` | `2026年9月4日` |

So a German reader saw the same run's date written two ways in two places,
and no test, no reviewer and no lint could see it from an en-US default. That
convergence — story-view onto the majority field spelling — is the **only**
visible output change of the migration; every other site is byte-identical,
measured from the old code before it was touched and pinned in
`aii_frontend/lib/__tests__/format.test.ts` across en-US/en-GB/de-DE/ja-JP.

### Why the pattern is wider than the statement's two spellings

`toLocaleDateString`/`toLocaleTimeString` alone would have missed
`invention-detail.tsx`, which spelled its month+year with plain
`toLocaleString(...)`. The command therefore also bans `Intl.DateTimeFormat(`
and `toLocaleString(` **with arguments** — `\([^)]`, not `\(`.

That last character class is load-bearing, not decoration. Eight live sites
format NUMBERS with a bare `n.toLocaleString()` (`message-list.tsx`,
`use-run-panels.ts`, `stats-view.tsx`, `render-message.tsx`), which is a
different concern and outside this door. Banning `toLocaleString\(` flat would
have made the rule RED on arrival against those eight — the exact thing the
`--tree` directive forbids — so the pattern distinguishes the empty-parens
number spelling from the argument-passing date spelling.

In the TypeScript-AST port that distinction becomes a STRUCTURAL fact rather
than a character class — but the port is written and INERT. Re-verified
2026-09-14: no set wires a dispatcher command
(`tools/_dispatch_wiring.py`'s `dispatcher_commands()` returns nothing for all
four sets), so the `\([^)]` class in the ERE at
`research-monorepo/lefthook.yml:335` is what decides today, and the paragraphs below
describe the cutover rather than the present. In the port the token grep is a
line-level prefilter (the
sole candidate source); `dispatch.py` then confirms each candidate against a
real parse and bans `toLocaleString` when the call node actually carries an
argument — read from the AST, not from the character after `(`. That drops the
string/comment lookalikes a flat ERE would catch, and it closes a same-line
hole the `\([^)]` span has: when the open paren sits at end-of-line, or the
call is reached through `?.`, `[^)]` has nothing to match on that line and the
raw ERE misses the site while the parser does not.

### Two scope decisions

`aii_frontend/lib/**` is in the pathspec even though the statement names only
features/app/components. The statement names where the drift **was**; the
sweep also covers where a fifth copy would most plausibly go next, since
`lib/` is where the derivation modules live and where `render-message`'s own
tests already sit. `lib/format.ts` is excluded by name — it is the door, and
excluding the one legal home rather than counting to one degrades correctly if
the file ever moves.

`.stories.tsx` is **not** excluded, unlike `rule-color-tokens`. A story renders
the same UI a reader looks at, the stock is clean without the exclusion, and a
story that wants a date can call the helper like everything else. Only tests
are out (`__tests__/`, `*.test.*`), because the test file necessarily quotes
the old spellings to prove the new ones reproduce them.

### The enforcement carrier, and how the sweep still runs

The check is carried by `lib/amg_hooks` through `amg-hooks-env` — not the retired
rule-engine's bare `rules-grep`. Today that carrier is `lib/amg_hooks/amg-hooks-grep`'s own
`--tree` flag on the lefthook line, which lists the whole index with
`git grep --cached`; at the cutover the same `--tree` becomes the
`dispatch.py` `SCOPE = "tree"` the dispatcher reads. Either way the whole git
index is judged unconditionally and any committed stock blocks at commit; no
`$RULES_MODE` shell escape is needed and none is used. The old
`[ "$RULES_MODE" = all ] || …` guard (copied from
`rule-classname-prop-merged-with-cn`) existed only so the raw grep would not
skip a whole-tree rule during a sweep where nothing is staged — the drift
audit the `--tree` exists for would otherwise never run, and the rule would be
green while checking nothing. TREE-mode makes that a property of the carrier
instead of a per-condition workaround.

## The cache is real, and so is its invalidation

`lib/format.ts` builds each formatter ONCE. Measured over 200k calls on this
box, a cached `Intl.DateTimeFormat.format` costs **376 ns** against **27,631
ns** for a per-call `Date#toLocaleTimeString(undefined, opts)` — 73x, or
0.26 ms against 3.9 ms for the activity feed's 200-row derivation, per
re-derivation.

A plain module-level constant would have been WRONG, and quietly so. A cached
`Intl.DateTimeFormat` resolves its timezone at construction and keeps it
forever, while `toLocale*` resolves per call — so a naive cache freezes the
zone at import time. `lib/__tests__/render-message.test.ts` pins the
195aed871 incident fix by setting `process.env.TZ = "Asia/Tokyo"` **inside the
test body**, long after the module is imported; with an uninvalidated cache
that guard reads `02:00` for the expected `09:00`. Verified by planting
exactly that regression: both it and the new
`format.test.ts` invalidation test fail, and pass again once the guard is
restored.

The guard is a re-read of the ambient zone at a FIXED instant
(`new Date(0).getTimezoneOffset()`, so DST cannot move it) costing 213 ns —
still 50x cheaper than the call it replaced.

## Delete-check

The fix WAS a deletion: three helpers added to lib/format.ts, four inline
formatters removed, `invention-detail.tsx`'s private `fmtMonth` deleted
outright and `render-message.tsx`'s NaN ternary deleted with it (the shared
helper renders `""` for an unusable instant, where `toLocale*` returned the
literal string `"Invalid Date"` — which is what a bad `inv.date` used to put on
the gallery page). Exactly how formatDurationMinutes/formatUsd already ended
the duration/cost drift.

## History

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Winner of the time-rendering pair: routing through lib/format.ts
helpers deletes the per-site locale/UTC dimension and enforces reader-local by
construction. Absorbs rule-timestamps-reader-local.
- KEEP: lib/format.ts exists precisely because per-file formatting drifted,
and date/time never made it in. Two helpers, four migrations, then a cheap
grep. Absorbs rule-timestamps-reader-local structurally.
- KEEP: Survivor absorbing rule-timestamps-reader-local: add
formatDate/formatTime to lib/format.ts, then grep bans
toLocaleDateString/toLocaleTimeString/getUTC* outside it. Literal ban, four
sites to migrate, incident-backed (195aed871). Loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate
agent re-ran every measurement against the live tree and corrected two claims
this card used to make. Both corrections survived into the migration and are
worth keeping:

- `render-message.tsx:215` was the OPPOSITE of hand-rolled — it was the site
  195aed871 converted to Intl, with every choice documented in the comment
  above it. That incident fix added one CORRECT copy instead of one shared
  helper, which is the whole shape of this rule; its comment moved with the
  call rather than being deleted.
- The card claimed `invention-detail.tsx` pinned `'en-US'`. By 2026-08-22 it
  already passed `undefined` — the en-US pin had been fixed in place, leaving
  a comment that still explained it. All four sites agreed on reader locale
  before this migration; what had NOT converged was the format itself, which
  is the drift the table above records.

Delete-check: The fix WAS a deletion: formatDate()/formatMonthYear()/formatTime()
live in lib/format.ts (reader-locale, per 195aed871), the four inline sites are
migrated, and the command enforces the collapsed end-state — exactly how
formatDurationMinutes/formatUsd already ended the duration/cost drift.
