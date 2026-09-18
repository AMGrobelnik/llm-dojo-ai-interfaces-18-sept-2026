<!-- hook: query-keys-single-source -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every hand-rolled TanStack queryKey namespace literal is declared exactly once, in a shared constants module

The 'run-event-body' key is re-typed in three files
(features/labs/views/errors-view.tsx:74, lib/api/use-full-message.ts:88,
features/run-viewer/use-run-pane.ts:675; 6 occurrences total counting
invalidation sites) and 'public-run-meta' in two (features/run-viewer/public-
run-viewer-context.tsx:58, lib/use-run-events.ts:374). A typo in one silently
splits the cache — invalidations miss, the UI shows stale data, nothing
errors. This is defect class #1 (one name re-implemented per view; the task-
slug incident 69279ba42 + 6dc7c4d8a is the same shape). The SDK-covered
operations already have generated queryKeys factories (openapi-ts.config.ts:43
queryKeys:true); only the hand-rolled BFF/custom keys lack a single source,
and constants/ already exists as the natural home.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: frontend-config)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_query_key_sources.py  # extracts the first string literal of every raw 'queryKey: [' / 'queryKey={[' in tracked aii_frontend source, fails when one namespace is used by more than one reader

**Two readers is the threshold, not one.** A namespace used at a single site
cannot disagree with itself, so hoisting it buys nothing and costs a layer of
indirection. Six are single-use today (`runs-cost`, `run-events`,
`public-run-access`, `poll`, `me`, `auth`) and the gate is deliberately
silent about all of them; it fires the moment a second reader appears, which
is the moment the invariant starts to matter.

ADOPTION (2026-08-25): both defects are FIXED — `constants/query-keys.ts`
now exports `runEventBodyKey` and `publicRunMetaKey`, and the five call
sites build their keys through it. Factories rather than exported namespace
strings, because the namespace was never the only thing repeated: all three
`run-event-body` readers pass `(runId, workflowId, functionId)` while
spelling the source fields three different ways, so exporting the string alone
would leave the ARGUMENT ORDER re-typed at every site.

Verified against history rather than against a synthetic fixture. Run over the
tree one commit before the fix, the gate exits 1 and names both duplicates at
exactly the sites this proposal recorded — `run-event-body` at
errors-view.tsx:74, use-run-pane.ts:675, use-full-message.ts:88 and
`public-run-meta` at public-run-viewer-context.tsx:58, use-run-events.ts:374.
On today's tree it exits 0.

That test caught a real flaw in the first draft: it treated a missing
`constants/query-keys.ts` as "could not run" and exited 2. On the pre-fix
tree the module did not exist yet, so the gate went SILENT on precisely the
state it exists to catch. A gate must not require its own remedy to be present
in order to speak; the absence now changes only the wording of the fix hint.

Delete-check: Deletion is the fix and the end-state: collapse each namespace literal to one
exported const (constants/query-keys.ts) and import it everywhere — the rule
then enforces that no literal reappears inline. The dimension cannot vanish
entirely because non-SDK fetches (public share view, event-body reads)
legitimately need hand-rolled keys.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Key namespaces re-typed across 3 files break cache invalidation
silently on rename; collapse to constants/query-keys.ts then enforce — new
keys are added constantly, so recurrence is structural.
- KEEP: 'run-event-body' re-typed across three files means a rename silently
breaks invalidation — a cache-coherence defect that ships green. Collapse to
constants/query-keys.ts; the duplicate-literal detection over queryKey first
elements is mechanical.
- KEEP: After collapsing to constants/query-keys.ts: for each exported key
literal, grep bans its re-typing elsewhere. Self-updating (keys enumerated
from the constants file), so no stale-registry vacuity.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
`grep -rn 'queryKey: ["' --include=*.ts --include=*.tsx` (excluding generated)
returned 9 hand-rolled keys total; the cited three run-event-body literals are
exactly at features/labs/views/errors-view.tsx:74, lib/api/use-full-
message.ts:88, features/run-viewer/use-run-pane.ts:675, and public-run-meta at
features/run-viewer/public-run-viewer-context.tsx:58 and lib/use-run-
events.ts:374 — all five line numbers exact. Two supporting facts do NOT hold.
(a) `grep -rn 'run-event-body'` gives 6 lines b

Corrected statement of fact:
Three re-typed literals confirmed, but there are no invalidation sites (3 of
the 6 grep hits are comments), and the operation IS SDK-covered —
getRunEventBodyQueryKey is generated at react-query.gen.ts:402 and unused, so
the single source already exists and is bypassed rather than absent. All keys
currently agree, so nothing is broken today.
