<!-- hook: api-via-sdk -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

# New frontend code calls the API through the generated SDK, not raw fetch

A bypassed operation gets no types, no error interceptor, and silently
survives schema drift the SDK would have caught at build. The wrapper layer
itself (`aii_frontend/lib/api/`) legitimately owns raw fetch — `apiFetch` and
the hey-api client are how everything else reaches Django.

Fix when blocked: import the operation from `@/lib/api/_hey-api` (or add the
endpoint to the schema and regenerate — `bun run codegen`). For the one
surface the generated client does not own, allauth headless, the wrapper is
`apiFetch`, which is what `app/page.tsx`'s session probe uses.

Delete-check: cannot delete — HTTP happens; one typed door is the point.

## Mechanism

`check.py` reads the staged frontend sources from the INDEX, blanks comments
length-preserving, and reports every bare `fetch(` whose TARGET is the
backend. A same-origin path belongs to Next unless its first segment is one
Next proxies to Django, and that set is derived from `next.config.ts`'s own
`rewrites()` block — the same parse
`unit-tests/server-frontend-parity/test_django_prefixes_are_reachable.py`
makes, and the place where "this prefix is Django's" is actually declared.
Today it yields `_allauth`, `accounts`, `admin`, `api`, `static`.

| target | verdict |
|---|---|
| `fetch("/api/runs")` | finding — proxied to Django |
| a template opening `${upstream}` | finding — leaves the origin |
| `fetch(url, …)` | finding — unreadable, so not assumed |
| a template opening `/runs/` | clean — a Next route |
| `fetch("/runs/" + id)` | clean — head `/runs/`, a route |
| `apiFetch(…)` | clean — that is the wrapper |

A `+` concatenation is judged on its leading literal, which is a prefix of
whatever it evaluates to. `dispatch.py`, the AST port, reads that same head
off the argument node (`tsast`'s `concat` argument kind) rather than off the
characters past the `(`, so the two readers agree line for line.

## Why the token-grep was replaced

Until 2026-09-10 the hook was `git grep -E '\bfetch\('` over the frontend
minus `lib/api/`. It reported three hits — two in
`app/(app)/runs/[runId]/layout.tsx`, one in `app/page.tsx` — of which **none
was a bypass by the time it was read**:

| site | what it is |
|---|---|
| `layout.tsx:306` | a dev-only RSC warm loop, `RSC: "1"` |
| `layout.tsx:27` | that loop's own docstring |
| `app/page.tsx:24` | a real bypass, now on `apiFetch` |

The first targets a route this app owns: Next 15.5 makes `router.prefetch()`
a no-op in development, so the effect issues the RSC request the router would
have, and the generated SDK — which covers Django operations — has nothing to
offer it. The second is prose describing the first, and a ban that fires on
the documentation is answering about the wrong text; `fe-fetch-timeout-signal`
blanks comments for exactly this reason. Only the third was the invariant
being broken, and it is fixed rather than exempted.

An earlier body called the first two "exemption candidates" and left the call
to the owner. Reading the target instead settles it without an exemption
list: the rule is about reaching the BACKEND, and neither of them does.

## Stock

Whole tree, at the index: **0 findings**, 0.28-0.34 s over 412 of 807 tracked
frontend files (three runs). The commit lane judges only the staged files, so
it reads a handful.

Proved to bite rather than merely to be present: unstaging the `apiFetch`
migration puts `app/page.tsx:24` back and the check returns
`raw fetch( — it targets ${…}…, which leaves this origin`, exit 1.

## Fragility

| refactor | effect and guard |
|---|---|
| the frontend moves | no tracked files, exit 2 |
| `next.config.ts` moves | not in the index, exit 2 |
| `rewrites()` renamed | fewer than 3 prefixes, exit 2 |
| a new Django prefix | picked up from the rewrite table |
| `lib/api/` renamed | `SKIP_CONTAINS`; the sibling hook exits 2 |

The three exit-2 paths matter more than usual here: every one of them would
otherwise turn a bypass into a pass, because an unreadable rewrite table
makes `/api/…` look like a Next route.

## History

An earlier body led with "6 of 40 API operations bypass the typed client
(download_run_file, the api-keys trio...)". The denominator was exact —
`sdk.gen.ts` exports exactly 40 operations — but the numerator was worked
down, not disproven, and no longer reproduces: `api-keys-wire.ts` imports
only `isObjectLike` and a local type and issues no request at all, and
`download_run_file` appears as an `operationId` in `openapi.json` — i.e. it
is IN the schema, which is where the fix was supposed to put it.

## Residue

A call the check cannot read — `fetch(url, …)` — is reported rather than
resolved; the fix is the SDK either way, so a data-flow analysis would buy
nothing. Nothing here proves the SDK operation a caller picked is the RIGHT
one, and a request made from a Server Component to a Next route of this app
is indistinguishable from one made in the browser.
