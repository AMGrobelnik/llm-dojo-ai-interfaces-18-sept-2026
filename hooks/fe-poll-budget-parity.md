<!-- hook: fe-poll-budget-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: condition had extra logic not mapped: "engine-git diff --cached --name-only -- 'research-monorepo/hooks/fe-poll-budget-parity/' | grep -q ." runs through lib/amg_hooks/amg-hooks-env: RULES_REPO, RULE_DIR
# Frontend poll cadences and the server's rate limits are checked against each other, so a cadence change cannot silently exceed a throttle bucket.

In full, the proposed gate: every frontend steady-state poll cadence and
every backend throttle rate is enumerated in one recomputable parity
manifest (`poll_budget.yaml` in this rule's directory); the check re-derives
both sides from source — the interval constants in the polling hooks and
`auth.rate_limits` in server.yaml — recomputes the per-tab requests/min
budget against the per-user and per-IP buckets, and fails on any drift, so a
cadence or rate change is a visible decision instead of a silent regression.

BLOCKED today: neither `poll_budget.yaml` nor `scripts/check_poll_budget.py`
exists yet — both must be built before this can be approved.

The two sides live in different languages with no shared source: FE cadences
at aii_frontend/lib/use-run-events.ts:65 (POLL_INTERVAL_MS=500 → 120/min),
features/settings/cost-poll.ts:21 (1500ms → 40/min), lib/use-runs-list.ts:20
(2000ms → 30/min), features/run-viewer/public-run-viewer-context.tsx:77-78
(5000ms meta poll), use-run-files.ts:51 (60000ms); BE buckets at
aii_config/server/server.yaml:66-67 (anon '200/min', user '600/min').
Computed correctly (2026-08-22 verification, below): the per-visible-tab
maxima are 151 req/min (run viewer: events 120 + runs-list 30 + files 1) and
70 req/min (Usage: cost 40 + runs-list 30) — the 1500ms cost poll never
coexists with the 500ms events poll, and hidden tabs contribute ~0 because
both hooks set refetchIntervalInBackground:false, so the 600/min user bucket
trips only with four concurrently VISIBLE windows (4 × 151 = 604). The live
defect is the anon side: a visible anonymous share viewer sums to ~132
req/min (120 events + 12 meta), so two viewers behind one NAT IP exceed the
200/min anon bucket — invisible because nothing computes this sum, and
api/__init__.py:85-97 (the `aii_optional_auth` docstring) documents the
identical failure shape having reached production once. Cadence changes have
production-shaped consequences here before: runs_list_poll.py:425-431 records the 1.5s cost poll parking pooled
connections until /runs/list died on PoolTimeout (5 of 101 requests 500'd
live). And one pairing is already hand-mirrored prose: cost-poll.ts:19-20
'matches the server's own freeze cadence' ↔ run_cost_sweeper.py:66
COST_SWEEP_INTERVAL_S=60. Distinct from rule-server-events-poll-feed
(server-side feed cheapness) and from killed rule-outbound-throttle-scope
(scope existence for outbound third-party calls — different mechanism
entirely: this is cross-tree cadence-vs-rate arithmetic).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: performance-budgets)

Proposed command (implemented at approval):

    $RULE_DIR/scripts/check_poll_budget.py — regex the pinned cadence constants out of the five polling hooks, parse auth.rate_limits from server.yaml, recompute per-tab and per-anon-viewer req/min sums, diff everything against $RULE_DIR/poll_budget.yaml and fail listing the drifted entries

Delete-check: Deleting the dimension means replacing polling with push — the repo went the
other way on purpose (runs_list_poll.py:11: the SSE snapshot stream is the
LEGACY this endpoint replaced), so cadences are here to stay. The constants
cannot collapse to one source across the TS/YAML boundary; a recomputed
manifest is the established cross-language pin (same pattern rule-parity-
fixture-two-readers protects for tests/fixtures).

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: FE cadences and server rate buckets live in two languages with no
shared source; drift ends in 429s on the steady-state poll. Enforced rule-
server-events-poll-feed covers server-side feed cost, not cadence-vs-throttle
budget arithmetic. The recomputable manifest is heavier than average but both
sides are re-derived from source, so it can't rot into prose.
- KEEP: Two-language seam with no shared source and a real silent failure mode
(cadence change trips server throttles); the manifest recompute is build-once,
fast at commit time. Distinct arithmetic parity, not the literal-parity class
rule-server-frontend-parity owns.
- KEEP: Real cross-language seam with no shared source. Keep only with the
detection sweep: any setInterval/refetchInterval/poll-constant in lib/features
not enumerated in poll_budget.yaml must FAIL — without it the manifest is
open-world vacuous for every new poll, the exact class that bit early rules.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
All eight file:line refs are exact — verified individually (line numbers
repointed 2026-08-28 where the files have since shifted): use-run-
events.ts:65 `export const POLL_INTERVAL_MS = 500`; cost-poll.ts:19-20
`Matches the server's own freeze cadence closely enough...` and :21 `export
const COST_POLL_INTERVAL_MS = 1500`; use-runs-list.ts:20 `const
POLL_INTERVAL_MS = 2_000`; public-run-viewer-context.tsx:77-78
`refetchInterval: (q) => q.state.data == null || q.state.data.status ===
"running" ? 5000 : false`; use-run-files.ts:51 `refetchInterval: isRunning ?
60_000 : false`; server.yaml:66-67 `anon: "200/min"` / `user: "600/min"`;
runs_list_poll.py:425-431 the PoolTimeout record; run_cost_sweeper.py:66
`COST_SWEEP_INTERVAL_S = 60`.

Corrected statement of fact:
Corrected statement for the rule body: the FE/BE cadence-vs-budget link is
genuinely unguarded (no shared source, no test), and the file:line inventory
is accurate — but the two computed sums are not. Replace '~191 req/min for a
live-run dashboard tab, 4 tabs -> 429s' with: the 1500ms cost poll never
coexists with the 500ms events poll (its only consumer, useRunsAggregateStats,
mounts on the Usage section and the settings page, gated at configure-
page.tsx:438), so the true per-visible-tab maxima are 151/min (run viewer:
events 120 + runs-list 30 + files 1) and 70/min (Usage: cost 40 + runs-list
30); and because use-run-events.ts:514 and use-runs-list.ts:130 both set
refetchIntervalInBackground:false, hidden tabs contribute ~0, so the user-
bucket ceiling needs four concurrently VISIBLE windows (4 x 151 = 604 > 600),
not four tabs — still true, but only barely and only under an unusual setup.
The anon computation stands as written: 132/min per visible anonymous share
viewer (120 events + 12 meta), two behind one NAT = 264 > 200/min. THAT is the
live defect worth fixing regardless of the rule, and api/__init__.py:85-97
(the `aii_optional_auth` docstring) already documents the identical failure
shape having reached production once. Fix risk: raising `anon` in server.yaml is a one-line config change but
deploy-facing (it widens a rate bucket, so it needs a deliberate call, not a
drive-by edit); changing any poll cadence is behavioural and riskier —
runs_list_poll.py:425-431 is the standing record of a cadence change with
production consequences.

## Mechanism (built 2026-09-03)

**The BLOCKED paragraph above is retired.** Both halves it named now exist:
`poll_budget.yaml` beside this file, and `scripts/check_poll_budget.py`, wired
as the rule's command. Everything else in the body — including the
independent-verification section and its correction of the two computed sums —
is kept as written, because the arithmetic recorded there is the arithmetic the
manifest now pins.

### What the checker asserts

`scripts/check_poll_budget.py` re-derives every number in `poll_budget.yaml`
from source and fails on any disagreement. Five checks plus a sweep:

1. **Interval literals**, read at a NAMED ANCHOR rather than by grepping for a
   number. An anchor is either a constant declaration (`const POLL_INTERVAL_MS
   = 500`) or a site (`refetchInterval:` / `setInterval(`), numbered
   `refetchInterval#2` where a file has more than one. A moved line is still
   found; a renamed constant fails loudly instead of silently matching nothing.
   An anchor whose expression yields more than one numeric literal is itself a
   finding — which one is the cadence has become a judgement the manifest has
   to record.
2. **`per_min` per poll**, as `60000 / interval_ms`.
3. **Both throttle buckets**, parsed out of `auth.rate_limits` in the TRACKED
   `aii_config/server/server.yaml` with PyYAML — the literal string AND the
   per-minute rate it means (`<count>/<s|min|hour|day>`, so a unit change is
   caught rather than crashing the parser).
4. **Every tab composition's sum**, from the SOURCE-derived poll rates rather
   than from the manifest's own numbers, so a stale manifest cannot certify
   itself.
5. **`visible_windows_to_trip`**, as `floor(bucket per_min / tab per_min)`.

**And a SWEEP, which is the half that keeps this from going open-world
vacuous** — the condition all three filter verdicts attached to their KEEP.
Every `refetchInterval`, every `setInterval(`, and every `const` whose name
matches `[A-Z_]*(POLL|INTERVAL)[A-Z_]*_MS` in tracked `*.ts`/`*.tsx` under
`aii_frontend/{app,features,lib}` — excluding `*.test.*`, `__tests__/`,
`*.stories.*` and the generated `lib/api/_hey-api/` client — must be claimed by
an entry in `polls` or in `not_polls` with a reason. An unclaimed one fails as
an *unenumerated interval*. The check runs in **both** directions: a claimed
anchor that no longer resolves also fails, because an entry pointing at a
renamed constant is an entry checking nothing while staying green.

Comments and string bodies are blanked before anything is matched, by a small
string-aware scanner that preserves line structure so findings name true line
numbers. These hooks document themselves heavily — `use-run-events.ts` alone
mentions `POLL_INTERVAL_MS` and `refetchInterval` in prose eleven times — and
matching those would invent anchors that are not code.

Two floors, both exit 2 rather than 0: no tracked in-scope frontend source at
all, and no interval-shaped anchor found in the ones that exist. Finding
nothing to check is never a pass.

### What the build found that the body did not

Nothing in the frontend or the server was changed — this rule records and pins;
it does not retune. Three corrections to the inventory, all recorded in the
manifest:

- **There is a SIXTH steady-state poll.** `use-backend-capacity.ts:33`
  (`CAPACITY_REFETCH_MS = 60_000`, `GET /api/config/backend-capacity`) is a
  real network poll at 1/min that the body's five-hook inventory does not name.
  It is enumerated in `polls` so the sweep is complete, but deliberately NOT
  folded into any of the three tab rows — those are the compositions the body
  derives, and adding a row is an owner call, not a build-time one. At 1/min it
  moves no verdict either way.
- **`use-run-files.ts` lives at
  `aii_frontend/features/run-viewer/use-run-files.ts`**, not under `lib/`. The
  body names it unqualified in both its inventory and its verification section,
  which reads as a `lib/` sibling of the two hooks listed beside it.
- **`public-run-viewer-context.tsx`'s `refetchInterval` is at :78-79**, not
  :77-78. Every other file:line in the body re-verified exact.

Five `not_polls` entries carry the interval-shaped literals that are NOT
steady-state polls, each with its reason: three local wall-clock/playback
tickers that issue no request (`use-playback-controller.ts`,
`use-run-timing.ts`, `use-messages.ts`), one IndexedDB write-batch debounce
(`run-events-store.ts` `PERSIST_MIN_INTERVAL_MS`), and one consumer of a
cadence pinned elsewhere (`use-runs-aggregate-stats.ts`, which delegates to
`costPollIntervalMs` in `cost-poll.ts`).

The manifest also pins `background_suspended` per poll, and the checker fails
any poll file that sets `refetchIntervalInBackground: true`. That flag is what
the whole tab arithmetic rests on — a hidden tab contributes ~0 — and TanStack
Query's default is `false`, with two of the six hooks pinning it explicitly.
Left unchecked it would be the one load-bearing assumption in this rule still
held as prose.

### `visible_windows_to_trip` is a FIT count, and anon fits exactly one

The field is `floor(bucket per_min / tab per_min)`: the number of concurrently
VISIBLE windows that fit inside the bucket. The bucket is first exceeded at one
MORE than the recorded value — `run_viewer` records 3 because a fourth window
sums to 604 against 600, which is the body's own figure read the other way
round. Worth stating plainly, since the field name reads as if it were the
tripping count.

`anon_share_viewer` records **1**: 132 req/min per visible anonymous share
viewer (events 120 + share_meta 12) against a 200/min `anon` bucket. One viewer
fits; a second on the same egress IP sums to 264 and exceeds it. **That is a
recorded fact for the owner, not something this rule fixes.** Both remedies —
widening `anon` in `server.yaml`, or slowing the share-view event poll — are
deliberate, deploy-facing calls of exactly the kind the body's fix-risk
paragraph describes. The rule exists so the next cadence change is made with
this number in view.

### Measured

Green on the live tree (re-measured 2026-09-14 against
`/home/<user>/projects/research-monorepo`): **exit 0**, sweeping 380 tracked
frontend sources and finding **13 interval anchors** — precisely the 13 the
manifest claims (8 across the six polls, 5 across the `not_polls`), so the
sweep is neither over- nor under-matching. 6 polls, 2 buckets, 3 tab
compositions. Runs in well under a second.

The lefthook line passes no `{staged_files}`, so the checker always judges the
whole frontend tree; the `glob:` list only decides WHETHER it runs. That is
why the header table reads `tree` and not `file`.

The gate bites, and the drift propagates. Probe: halve the runs-list cadence
(`2_000` -> `1_000`) in a throwaway fixture tree — **exit 1**, five findings
from one edit:

```
aii_frontend/lib/use-runs-list.ts:20: poll 'runs_list' is 1000 ms in source but 2000 ms in …/poll_budget.yaml
…/poll_budget.yaml:67:  poll 'runs_list' records per_min 30 but 1000 ms is 60/min
…/poll_budget.yaml:176: tab 'run_viewer' records per_min 151 but its polls sum to 181 (120 + 60 + 1)
…/poll_budget.yaml:188: tab 'usage' records per_min 70 but its polls sum to 100 (40 + 60)
…/poll_budget.yaml:188: tab 'usage' against bucket 'user' fits 6 concurrently visible window(s) (floor(600/100)) but the manifest records 8
```

`test_the_poll_budget_gate_catches_a_cadence_that_outruns_its_bucket.py` pins
all of it — **8 tests** (re-counted 2026-09-14): the real tree passes, the
fixture reproduces that pass (so a drift finding is the drift and not the
fixture), and four separate drifts each fail — a changed interval literal, a
widened `anon` bucket, a new unenumerated poll, and an anchor renamed out from
under a manifest entry — plus a tracked file deleted in the worktree not
crashing the sweep, and an empty population reporting cannot-run rather than a
pass.

The module resolves the consumer root as `RULE_DIR.parents[5]`, i.e. it
assumes the submodule sits at `<consumer>/.claude/skills/amg-hooks/`.
Run it from a consumer checkout; from a bare clone of this repo that path
lands outside the repo entirely and all 8 fail rather than skipping.
