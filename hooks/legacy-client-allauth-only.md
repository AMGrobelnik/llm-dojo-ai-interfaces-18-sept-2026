<!-- hook: legacy-client-allauth-only -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The legacy apiFetch transport carries only /_allauth traffic and the binary download_file blob fetch; every other /api operation goes through the generated SDK

The migration to the Hey API SDK stalled halfway: features/run-config/use-api-
keys.ts:54 ('/api/settings/api-keys'), features/run-views/advanced-view/right-
panel/views/files-view.tsx ('/api/runs/.../download_file' — cited by file,
not line: the :329 pin drifted to :343 once already), and
features/guided-setup/api.ts:66,79 ('/api/runs/guided-intake',
'/api/runs/guided-followups') all drive /api endpoints through
lib/api/client.ts's apiFetch — the '6 of 40 operations bypass' the existing
rule-api-via-sdk measured but cannot block, because it greps only raw 'fetch('
and apiFetch importers never write one. Bypassed operations get no generated
types and survive schema drift the SDK would catch at build. The allauth
surface (/login, /signup, /password, /verify-email, features/auth/api.ts)
legitimately keeps apiFetch: /_allauth is outside the Ninja OpenAPI schema.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: frontend-config)

Proposed command (implemented at approval):

    python3 $RULE_DIR/scripts/check_legacy_client_scope.py  # for each file importing apiFetch/API_BASE from lib/api/client, fail if it contains a '/api/' URL literal; extractApiErrorMessage-only importers pass

## IMPLEMENTED 2026-08-28 — `scripts/check_legacy_client_scope.py`, with the blob carve-out

    python3 $RULE_DIR/scripts/check_legacy_client_scope.py

The checker walks the tracked `aii_frontend` TS/TSX sources through git
(tests excluded), keeps every file importing `apiFetch` or `API_BASE` from
`lib/api/client` (importers of only the error/CSRF helpers pass), and fails
on any non-comment `/api/` URL literal in them — module specifiers like
`@/lib/api/client` are recognised and skipped. One carve-out, matching the
H1: a literal containing `download_file`. files-view.tsx routes that endpoint
through `apiFetch` on purpose — the hey-api SDK assumes JSON, and the comment
two lines above the call says exactly that — so an unqualified allauth-only
statement would contradict live in-repo intent (the 08-22 verification's
point, now carved into the H1).

Measured on arrival: RED, as the OWNER-GATED note below expects — 3 URL
literals in 2 files, behind which sit the 5 untyped operations:
`features/guided-setup/api.ts:66,79` (guided-intake, guided-followups) and
`features/run-config/use-api-keys.ts:54` (the api-keys endpoint; its GET/PUT
and the derived `/verify` POST all flow through that one literal). The five
allauth pages under `app/` and `features/auth/api.ts` pass — their traffic is
`/_allauth` — as do the two `extractApiErrorMessage`-only importers.

Delete-check: This rule IS the deletion: the variation (two transports for one API surface)
collapses once the three /api consumers move to the SDK, after which apiFetch
shrinks to the allauth-only helper and the rule enforces that end-state. Fully
deleting apiFetch is not possible — /_allauth endpoints are not in the OpenAPI
schema, so the SDK can never cover them.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Winner of the four legacy-transport proposals: /_allauth traffic
legitimately cannot ride the generated SDK, so 'apiFetch carries only
/_allauth' is the enforceable end-state that still shrinks the wrapper
maximally. Absorbs rule-legacy-api-client-retired, rule-fe-single-http-door,
rule-legacy-fetch-client-shrinks.
- KEEP: Canonical of the four-way legacy-client cluster. The allauth-only end-
state is achievable (three /api consumers to migrate) and honest about why the
wrapper survives. Post-migration check: no '/api/' path literal passes through
apiFetch — cheap grep. Absorbs rule-legacy-api-client-retired, rule-fe-single-
http-door, rule-legacy-fetch-client-shrinks.
- KEEP: The survivor of the four legacy-client proposals: honest terminal
state (allauth flows legitimately stay off the SDK). Check: grep apiFetch call
sites for '/api' path literals — only '/_allauth' allowed. Implementable,
loud; verified 11 importers exist today so this bites immediately.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
All three line citations are exact: use-api-keys.ts:54 is `const ENDPOINT =
`${API_BASE}/api/settings/api-keys`` (apiFetch at 58, 64, 76); guided-
setup/api.ts:66 is `return postGuided("/api/runs/guided-intake", { questions
})` and :79 `return postGuided("/api/runs/guided-followups", { answers })`
(apiFetch at :43); files-view.tsx:328-329 is the download_file apiFetch. The
counts check out: the committed openapi.json has 35 paths / 40 operations, and
all five endpoints are present in it (`/api/se

Corrected statement of fact:
5 of the 6 bypassed operations (api-keys GET/POST/verify, guided-intake,
guided-followups) are untyped with no recorded rationale; the 6th
(download_file) is bypassed on purpose and its reason is in a comment two
lines above the cited line — a rule phrased as 'only allauth may keep
apiFetch' would contradict live in-repo intent and must carve out the binary-
blob case too. Separately, the gap is already named in rule-api-via-sdk's own
text, so this is a rule that can BLOCK something the existing rule only
documents, not a newly found gap.

OWNER-GATED: green requires migrating the remaining /api consumers off apiFetch onto the generated SDK. CLAUDE.md lists api-via-sdk exemptions as an owner call, and gating before the migration would be red on arrival.

## Migrated 2026-09-03 — the five operations are on the SDK; the rule is wired

The OWNER-GATED condition above is MET, and the migration turned out to be
frontend-only. Every one of the five operations was ALREADY in the committed
schema (`aii_frontend/lib/api/openapi.json` — 36 paths / 41 operations) with
a generated SDK function and generated TanStack helpers, so nothing had to be
registered on the Django side. `openapi.json` and `lib/api/_hey-api/**` are
byte-unchanged; no `codegen:*` script was run.

Per operation — schema presence, and the path each now takes:

- **`guided_intake`** — `POST /api/runs/guided-intake`, in schema.
  Was `apiFetch(\`${API_BASE}/api/runs/guided-intake\`)`; now
  `guidedIntake({body: {questions}, throwOnError: true})` from
  `lib/api/_hey-api/sdk.gen`, in `features/guided-setup/api.ts`.
- **`guided_followups`** — `POST /api/runs/guided-followups`, in schema.
  Now `guidedFollowups({body: {answers}, throwOnError: true})`, same module.
- **`get_api_keys`** — `GET /api/settings/api-keys`, in schema.
  Now `useQuery({...getApiKeysOptions(), select: parseStatus})` in
  `features/run-config/use-api-keys.ts` — the generated options, so the
  generated queryFn AND the generated key.
- **`save_api_keys`** — `PUT /api/settings/api-keys`, in schema.
  Now `saveApiKeys({body: toWirePayload(body), throwOnError: true})`, same
  module, with `qc.setQueryData(getApiKeysQueryKey(), data)` on success. This
  is the operation the `${ENDPOINT}` literal shared with the GET.
- **`verify_api_key`** — `POST /api/settings/api-keys/verify`, in schema.
  It had no literal of its own — `VERIFY_ENDPOINT` was DERIVED from
  `ENDPOINT`, which is why one URL literal hid three operations. Now
  `verifyApiKey({body: {provider, key}, throwOnError: true})`.

Both modules keep their runtime narrowing (`narrowQuestions`,
`parseStatus` / `parseVerified` / `parseVerifyResult`). A generated type is a
claim about the schema, not a check of the body that arrived, and the
narrowing is what makes a disagreeing field degrade instead of crashing the
tab. The `null` vs `[]` distinction in the guided flow survives intact:
`throwOnError: true` puts a non-2xx and a network failure on the same throw
branch, and that branch is the `null`.

`ensureOk` is no longer needed here — the app-wide error interceptor
(`lib/api/install-error-interceptor.ts`) already wraps whatever the SDK
throws into an `Error` whose `message` is the backend's `detail`, which is
exactly what `sections/api-keys.tsx` renders via `extractApiErrorMessage`.
`ensureOk` itself stays: `files-view.tsx` still uses it for the blob fetch.

The api-keys pair needed more than a transport swap, and the reason is worth
recording: the hand-kept `API_KEYS_QUERY_KEY` is GONE, replaced by
`getApiKeysQueryKey()`. Moving the GET and the PUT onto the SDK made them a
recognisable same-path write/reader pair for the first time, and
`rule-fe-write-invalidates-its-reader` immediately reported both halves —
"nothing in scope consumes `getApiKeysOptions()`" and "no setQueryData names
`getApiKeysQueryKey()`". A hand-kept key beside a generated one is two cache
entries for one resource, which is precisely the staleness that rule exists to
stop, so the fix was to adopt the generated key rather than to exempt the
module. Measured A/B on an isolated copy of the tree: the intermediate
(SDK calls, hand-kept key) reports both findings; the landed version reports
neither.

`apiFetch` now carries `/_allauth` only (the five auth pages plus
`features/auth/api.ts`) plus the one `download_file` blob call — the H1's
end-state, verified by the checker rather than asserted.

One checker fix came out of running it: it walked `git ls-files` and read
every path, so a file tracked in the index but deleted in the working tree
(a concurrent agent mid-refactor, unstaged) crashed it with exit 2. A
deleted file carries no content and can hold no violation, so it is now
skipped — the rule's verdict must not depend on who else is mid-edit in the
same checkout.

Verified 2026-09-03: checker exit **0**; and still BITING — replayed against
the pre-migration `HEAD` copies of the two modules in a scratch repo it
exits **1** on exactly the three original literals, while `files-view.tsx`
passes on the `download_file` carve-out.
