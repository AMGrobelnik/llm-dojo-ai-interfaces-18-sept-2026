# Every fetch wrapper lays down a shared default deadline and combines it with the caller's signal

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

The frontend funnels all HTTP through two hand-written wrappers
(`aii_frontend/lib/api/client.ts` and `hey-api-client.ts`), and for a long
time neither set a default request deadline: a request without a
caller-supplied signal had none, and `apiFetch` retries idempotent methods up
to three times, which multiplies a hang. The measured asymmetry that opened
the rule was Python at 40 of 41 call sites explicit on httpx timeouts against
zero on the frontend side.

The rule was minted before its fix and spent its life being excused — 40
applies, 24 fails and five work-in-progress verdicts, all five saying the
same thing: red at HEAD independent of the diff, awaiting sign-off. That
premise is now stale. `http-common.ts` exports `DEFAULT_REQUEST_TIMEOUT_MS`,
`anySignal()`, `requestTimeoutError()` and `isTimeoutAbort()`, and both
wrappers consume them, so this ships as an ordinary regression guard at zero
stock rather than as a standing exception.

The fix was never two-files-simple, which is why the shape matters as much as
the presence: a blanket default must spare the events long-poll, the
generated SSE runtime and uploads, so the budget has to be nullable per call
and the deadline has to be COMBINED with the caller's signal, never
substituted for it.

## Mechanism

A wrapper is DISCOVERED, never listed: any tracked module under the API
directory whose code calls `fetch(` is a wrapper from the moment it lands.
Comments are blanked length-preserving first, because these modules are
largely prose and the prose quotes every token the check looks for.

| failure mode | mechanism |
|---|---|
| no deadline built at all | no timeout, no controller |
| the caller's signal replaced | reads `.signal`, no combinator |
| the budget inlined per wrapper | no imported `*TIMEOUT*` name |
| the constant has two homes | specifiers resolved; one home |
| no per-call escape hatch | the budget does not accept null |
| a third wrapper skips it | discovery is by content |
| the API directory renamed | no tracked source under it, exit 2 |
| a wrapper merged or deleted | fewer than two left, exit 2 |
| the deadline promised in prose | comments blanked first |

With paths it judges the changed wrappers plus every wrapper importing the
shared constant from a changed module; the import specifiers are resolved to
repo paths (relative and the `@/` alias) against the index.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`
(a clean snapshot of that commit): **0 findings**, exit 0. It reads 6 of the
29 tracked files under `aii_frontend/lib/api/`. Whole-tree runtime 0.03 s
(three runs, all 0.03 s).

Proved to bite on the real files rather than only on fixtures: seeded with
the live `lib/api/`, single-token mutations of `client.ts` each turn it red
with the right message — `anySignal(` to `replaceSignal(` gives "never
combines signals", the constant replaced by `60_000` gives "no shared timeout
constant", `AbortSignal.timeout(` to `passthrough(` gives "never builds a
deadline" — and restoring the token returns it to 0.

## Fragility

| refactor | effect | guard |
|---|---|---|
| `lib/api/` renamed or moved | scan sees nothing | exit 2 |
| wrappers merged into one | one wrapper left | exit 2, floor is 2 |
| a wrapper renamed or split | none | discovery is by content |
| the constant renamed | none | matched by shape, not name |
| traffic moves to `lib/http/` | ban is empty | not guarded (below) |

CONFIG names one directory, so HTTP moving out of it is uncovered here. It is
partly covered by `api-via-sdk`, the hook that funnels traffic into that
directory in the first place; closing it properly means sweeping the whole
frontend for `fetch(`, which duplicates that hook.

## Residue

The check proves the four properties are present in the module. It does not
prove the deadline reaches the `fetch()` call on every branch, nor that 60 s
is the right number. Both are pinned behaviourally by
`lib/api/__tests__/client.test.ts`, `hey-api-client.test.ts` and
`http-common.test.ts`, which run under `vitest-sb-fe`; this hook adds the
structural half — that the wiring still exists, and that a NEW wrapper cannot
skip it.
