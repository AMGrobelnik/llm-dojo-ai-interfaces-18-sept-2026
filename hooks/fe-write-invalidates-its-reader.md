<!-- hook: fe-write-invalidates-its-reader -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_REPO
# Every write operation that shares an OpenAPI path with a GET operation has that GET in the QueryClient, and the write's wiring invalidates or patches it

I derived the pair set from `aii_frontend/lib/api/openapi.json` with a python3
script over spec['paths'] (write ops joined to same-path GETs). Four pairs
exist: `saveConfig -> /api/config -> ['getConfig']`, `saveApiKeys ->
/api/settings/api-keys -> ['getApiKeys']`, `shareRun` and `unshareRun` ->
`/api/runs/{run_id}/share` -> `['getRunShare']`, `sideChatSend ->
/api/runs/{run_id}/side_chat -> ['sideChatEligibility']`. Three are wired:
`git grep -n 'invalidateQueries\|setQueryData'` gives `features/run-
config/configure-page.tsx:174` and `features/run-config/use-run-
settings.ts:132` (both `invalidateQueries({ queryKey:
getConfigOptions().queryKey })`) and `features/run-config/use-api-keys.ts:111`
(`qc.setQueryData(getApiKeysQueryKey(), data)`). sideChatSend is a genuine
non-edge, and I checked rather than assumed:
`aii_server/dashboard/api/run_side_chat.py`'s docstring says eligibility
"holds for a run whose workflow ended hours ago — the sessions outlive the
run", so a send cannot flip the answer and the hook's `staleTime:
Number.POSITIVE_INFINITY` is correct. The share pair is the real gap, and it
is worse than a missing invalidation — the resource is not in the cache at
all. `git grep -nE 'getRunShare|shareRun|unshareRun' -- 'app/**' 'features/**'
'lib/**' ':!lib/api/_hey-api/**'` returns four lines, all in `features/run-
views/topbar/share-button.tsx` (:6 import, :53 getRunShare, :104 shareRun,
:122 unshareRun), and `git grep -c 'queryClient\|useQuery' features/run-
views/topbar/share-button.tsx` -> 0. The state lives in five useState/useRef
slots there, with a hand-rolled coherence protocol at :74-79 ("afterwards
local state is kept current by the share/unshake handlers, and re-reading
could race a just-completed POST/DELETE") — i.e.
cancelQueries/invalidateQueries re-implemented by hand. The generated door
already exists and is unused: `grep -oE 'export const
(getRunShare|shareRun|unshareRun)[A-Za-z]*' lib/api/_hey-api/@tanstack/react-
query.gen.ts` -> getRunShareOptions, getRunShareQueryKey, shareRunMutation,
unshareRunMutation. Distinct from rule-api-via-sdk [ENFORCED] (that one bans
raw fetch; share-button already uses the SDK) and from rule-query-keys-single-
source [PENDING] (that one is about a key literal being typed once; this is
about a resource having a cache entry and an invalidation edge at all).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: fe-fetch-and-cache)

Proposed command (implemented at approval):

    python3 $RULE_DIR/scripts/check_write_reader_edges.py  # joins openapi.json write ops to same-path GET ops; for each pair asserts the GET is consumed via <getOp>Options(/useQuery in app|features|lib, and that every module composing <writeOp>Mutation() names <getOp>QueryKey( (or the shared key const) in an invalidateQueries/setQueryData/removeQueries call; a pair may be exempted only by a same-file comment stating why the read cannot change

Proposed condition: `git diff --cached --name-only | grep -qE '^aii_frontend/(app|features|lib)/|^aii_frontend/lib/api/openapi\.json$'`

Delete-check: Deletion IS the fix, and the target already exists: delete share-button's five
state slots and the probeDone/'local state is authoritative' protocol, and
wire the four unused generated factories (getRunShareOptions +
shareRunMutation/unshareRunMutation with an invalidate on
getRunShareQueryKey). That removes hand-rolled code rather than adding a
policy. The dimension itself cannot vanish while a resource has both a reader
and a writer — but the rule needs no registry: the pair set is recomputed from
openapi.json on every run, so a new endpoint pair enters scope automatically
and a retired one leaves.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **partly-wrong**.
A different agent re-ran every measurement before this reached the owner.

What it found:
Pair derivation reproduced exactly. My python3 over
aii_frontend/lib/api/openapi.json joining same-path GETs to write ops ->
`/api/runs/{run_id}/share ['get_run_share']
[('post','share_run'),('delete','unshare_run')]`; `/api/config ['get_config']
[('put','save_config')]`; `/api/runs/{run_id}/side_chat
['side_chat_eligibility'] [('post','side_chat_send')]`; `/api/settings/api-
keys ['get_api_keys'] [('put','save_api_keys')]`. Wiring for config/api-keys
confirmed at features/run-config/configure-page.tsx:174, features/run-
config/use-run-settings.ts:132, features/run-config/use-api-keys.ts:111.
side_chat rationale confirmed: `grep -n 'sessions outlive'
aii_server/dashboard/api/run_side_chat.py` -> line 13, 'the sessions outlive
the run (measured on ``run_oQQwThF8kM-b`` a day later: 30...'. Share pair
confirmed absent from the cache: `git grep -nE
'getRunShare|shareRun|unshareRun' -- 'app/**' 'features/**' 'lib/**'
':!lib/api/_hey-api/**'` -> 4 lines, all features/run-views/topbar/share-
button.tsx (6, 53, 104, 122); `git grep -c 'queryClient|useQuery'
features/run-views/topbar/share-button.tsx` -> no output (zero). Generated
hooks exist: `grep -oE 'export const
(getRunShare|shareRun|unshareRun)[A-Za-z]*' lib/api/_hey-api/@tanstack/react-
query.gen.ts` -> unshareRunMutation, getRunShareQueryKey, getRunShareOptions,
shareRunMutation. HOWEVER `sed -n '1,135p' features/run-views/topbar/share-
button.tsx` shows the module docstring at lines 24-28 states the contract
deliberately: 'On first open the button reads the share state via the owner-
gated GET /api/runs/{id}/share ... After one *successful* read, in-session
state is authoritative (share/unshare handlers update it directly); a failed
read is retried on the next popover open.' And `git grep -nE '\bshared\b' --
'features/run-views/**' 'features/runs-list/**' | grep -v share-button` -> no
second reader of share state anywhere.

Corrected statement of fact:
The derivation and the three wired pairs verify precisely; the
characterisation of the fourth as a defect does not. Share state has exactly
ONE reader — the component that owns it — so there is no cross-component
staleness a QueryClient entry would resolve, and the module docstring (share-
button.tsx:24-28) plus the inline comment at :74-79 declare the component-
local protocol as the design, including WHY re-reading is avoided ('re-reading
could race a just-completed POST/DELETE'). This is the round's known failure
mode: a docstring directly above the finding declaring it deliberate.
Reframing five useState slots as 'cancelQueries/invalidateQueries re-
implemented by hand' is a preference for a different mechanism, not a measured
incoherence — no state the user can observe goes stale. Two lesser
inaccuracies: the quoted `git grep 'invalidateQueries|setQueryData'` actually
returns 13 lines, not 3 (it also hits use-run-files.ts:82, use-
dashboard.ts:648/657, the three optimistic-* modules and one .stories.tsx), so
the 'three are wired' framing is a filtered view presented as raw output. The
rule survives only as 'a write op sharing a path with a GET either invalidates
that GET or documents why it need not' — which is what all four already do.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Derivable mechanically from openapi.json (same-path GET vs write op),
unclaimed, and the failure is user-visible stale UI that gets papered over
with local component state instead of cache wiring.
- KEEP: Best non-vacuity story here: the GET/write pairs come out of
openapi.json by join, so the population is generated and provably non-empty,
and the invalidation edge is greppable once query keys are single-sourced.
High value and no claimed rule covers write-to-reader wiring.
- KEEP: Mechanized from openapi.json (same-path GET joined to write ops), so
the population is derived rather than hand-listed and grows with the API. The
delete-check's fix — delete share-button's five duplicated state slots —
repairs today's violation but does nothing about the next write op added
beside an existing GET. Not claimed: rule-api-via-sdk pins the transport, …

## Recorded debt

Three writer sites are listed in the checker's `RECORDED_DEBT` (`shareRun` and
`unshareRun` in `share-button.tsx`, `sideChatSend` in `use-run-pane.ts`): the
2026-09-08 adoption sweep found them unwired, and without the entries every
frontend commit would block on stock it did not touch. Wire the invalidation
and delete the entry; `docs/decisions/adoption-debt.md` carries the list.

## Mechanism (built 2026-09-03)

`scripts/check_write_reader_edges.py`. Exit 0 clean, exit 1 per finding as
`path:line: <pair> — <what is missing>`, exit 2 when it cannot run.

**What it asserts.** The population is re-derived on every run, never listed:
`aii_frontend/lib/api/openapi.json` is joined path-by-path, each write method
(post/put/patch/delete) against a GET on the same path. Each operationId is
mapped to its generated SDK name by the generator's own convention
(`get_run_share` -> `getRunShare`) and that mapping is *confirmed* against the
`export const` names in `lib/api/_hey-api/sdk.gen.ts` and
`_hey-api/@tanstack/react-query.gen.ts` — a name the generated client does not
publish is cannot-run, not a finding, because every downstream grep would then
be looking for a spelling that cannot occur.

For each pair, tracked modules under `aii_frontend/{app,features,lib}` (minus
`lib/api/_hey-api/`, tests, stories, `.d.ts`) that call `<writeOp>(` or
`<writeOp>Mutation(` must satisfy one of:

- **an edge** — `<getOp>QueryKey(` or `<getOp>Options(` named inside an
  `invalidateQueries` / `setQueryData` / `removeQueries` call. Matched over the
  call's balanced-paren argument text, not one line, because the idiomatic form
  here wraps;
- **an exemption** — a same-file comment
  `rule-fe-write-invalidates-its-reader: <reason>` saying why the read cannot go
  stale. A marker with a token reason (`: n/a`) is reported, not honoured.

A pair with any non-exempt writer must also have its GET in the QueryClient at
all — `<getOp>Options(` somewhere in scope, or a `useQuery` naming its key.
That is reported separately: a missing invalidation is a stale read, while a
resource with no cache entry is a read that was never wired.

Comments and string bodies are masked before any call is looked for, so a
commented-out write is not a write; the exemption marker is read from the RAW
text, since masking is exactly what would erase it.

**Discovery cannot fail open.** Zero pairs, zero modules in scope, or zero
writer call sites each exit 2 with a message. Finding nothing to check is not a
pass — which matters more here than usual, because the whole population is
derived and a renamed generator convention would otherwise read as green.

**Stock edits — two, both recording a design this rule's own verification
established, neither changing behaviour.** The INDEPENDENT VERIFICATION above
is what they encode, so the exemption path is not a courtesy: it is the half of
the rule that survived review.

- `aii_frontend/features/run-views/topbar/share-button.tsx` — one comment line
  appended to the module docstring that already declares the protocol
  (`:24-28`). Share state has exactly one reader, this component, and
  re-reading could race a just-completed POST/DELETE. Not rewritten: the
  verification found the component-local design deliberate and documented, and
  the round's known failure mode is reporting a finding a docstring directly
  above it already answers.
- `aii_frontend/features/run-viewer/use-run-pane.ts` — one comment line beside
  the existing `side_chat` block comment at the `sideChatSend` call. Eligibility
  cannot flip: `aii_server/dashboard/api/run_side_chat.py`'s docstring records
  that the sessions outlive the run, and `useSideChatEligibility` sets
  `staleTime: Number.POSITIVE_INFINITY` for that reason.

Both files still pass `oxfmt --check` and `oxlint` (0 warnings, 0 errors).

**The two wired pairs are the positive control and they were not touched.**
`saveConfig` at `features/run-config/configure-page.tsx:156` and
`features/run-config/use-run-settings.ts:119` both carry
`invalidateQueries({ queryKey: getConfigOptions().queryKey })`, and the checker
passes them while reporting the unwired ones — so exit 1 was never "everything
is red".

**A near miss the count caught, not the verdict.** The first lookbehind
rejected any preceding `.`, which is right for member access and wrong for the
spread the mutation factories are composed with
(`...saveConfigMutation(),`). Both `saveConfig` sites were silently dropped
from the scan. The tree still read green — those two sites are correctly wired
— so only the reported writer-site count (3, where 5 exist) exposed it. Fixed,
and pinned by `test_the_spread_form_of_a_mutation_factory_counts`.

**Probe.** `test_a_write_op_without_its_readers_invalidation_is_reported.py`,
8 tests, all green (`.venv/bin/python -m pytest <rule dir> -q` -> `8 passed`).
It runs the checker on the real tree and expects 0, and plants each shape in a
synthetic `tmp_path` frontend that is `git init` + `git add`-ed, since the scan
asks git what exists and an untracked fixture would be invisible: a write with
no edge and no exemption -> exit 1 naming both findings; an invalidating write
-> 0; a reasoned exemption -> 0; a token reason -> 1; the spread form -> 1; a
spec joining no pair -> 2; a tree whose only write is commented out -> 2.

**Measured on the real tree, 2026-09-03:** 4 pairs, 5 writer call sites,
**exit 0**. Before the two exemption comments it was exit 1 with exactly the
four findings this rule's body predicts and no others — the three share-pair
lines and the one side-chat line — which is the check reproducing the
derivation rather than agreeing with it by construction.

**One thing this does not yet cover, and it is not the checker's to fix.**
`/api/settings/api-keys` joins a pair, but neither side goes through the
generated SDK: `features/run-config/use-api-keys.ts` is hand-written against
`apiFetch` (its docstring says so, :18-20) and single-sources its key as
`getApiKeysQueryKey()`. It is correctly wired — `qc.setQueryData(getApiKeysQueryKey(),
status)` at :108 — but by a name this checker does not look for, so the pair
contributes zero writer sites and is neither passed nor failed. Widening the
scan to hand-written transports belongs to `rule-api-via-sdk`, which owns that
dimension.

**Not collected by the default pytest run while pending.** `pytest.ini`'s
`testpaths` names `.claude/skills/amg-hooks/rules`, not `rules-pending`,
so the probe module runs only when pointed at directly — it will be collected
automatically the moment the rule is approved and moves. In the meantime the
mechanism itself is exercised in CI by
`test_every_pending_mechanism_still_passes.py`, which runs every tracked
pending `command:` and expects exit 0; this one needs no `_EXPECTED_FAILING`
entry.
