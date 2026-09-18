<!-- hook: fe-session-boundary-hard-nav -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Every navigation across a session boundary is a full-document load, so the shared QueryClient and the module-level run-events store go away with the session

`aii_frontend/features/auth/use-auth.ts` lines 28-31 (read via sed) states the
design: "Cache invalidation isn't wired here because every auth state change
(login / signup / logout) navigates with ``window.location.href``, which
discards the QueryClient instance entirely." That is the ONLY thing scrubbing
account-scoped data, and both halves of that claim were re-measured 2026-09-05.
`git grep -nE 'queryClient\.clear\(|qc\.clear\(|resetAll' -- .
':!lib/api/_hey-api/**' ':!**/__tests__/**'` now returns TWO lines —
`features/auth/use-auth-page.ts:24` and `features/runs-list/use-dashboard.ts:928`
— and neither is a call: both are prose naming the absent API, added by
`6909512b6` (2026-09-04), the same commit that converted the two soft legs. No
code anywhere clears the cache, exactly as before; the grep is simply no longer
empty, so read its hits before treating a non-zero result as a regression.
`git grep -nE '\.reset\(' ...` over the same pathspec returns THREE, none of
them session-scoped: `features/playback/url-sync.tsx:69` and
`features/playback/use-playback-controller.ts:61` both call
`usePlaybackStore.getState().reset()` on a run SWAP, and
`features/runs-list/optimistic-delete.ts:177` calls
`useRunEventsStore.getState().reset(runId)` per-run, on delete. The body
claimed only the third for months; the 2026-08-24 audit below already reported
all three, and that correction is now carried here rather than only there.
One site broke the assumption, and it is FIXED. `features/runs-list/use-
dashboard.ts` bounced a lapsed session with `router.replace("/login")` — the
auth guard, then at :921, later :927 — and now hard-navigates to the base-path
form of /login at :937. Every other exit was already hard: `git grep -cnE
'window\.location\.href\s*=.*\/login'` -> `features/auth/api.ts:1`,
`features/sidebar/sidebar.tsx:1`, `lib/api/hey-api-client.ts:1`. A soft bounce
there would have left the previous session's `RUNS_LIST_QUERY_KEY`,
`["auth","me"]`, `getConfig`, `getApiKeysQueryKey()` (masked key hints) in the
live QueryClient, plus the module-level `useRunEventsStore` and its IndexedDB
records (`lib/run-events-persist.ts`, DB `aii-run-events`), none of which are
auth-scoped. The return leg was soft too — `features/auth/use-auth-page.ts:32
router.replace("/runs")` in `useRedirectIfAuthenticated` — and now hard-
navigates to the base-path form of /runs at :50; that leg is same-session, so
it was an asymmetry rather than a carryover, but it left the boundary hard in
three legs out of four with no stated reason. NOT rule-hard-nav-base-path
(proposed, then KILLED 2026-08-28 as already enforced by `rules/aii/unit-
tests/rule-runtime-hazards-stay-fixed/test_hard_navigation_keeps_the_base_path.py`):
that governs how a hard nav is SPELLED (carry resolveBasePath, never a bare
'/'); this governs WHICH navigations must be hard at all — its scan reads
`hardNavigate(` call sites and is structurally blind to
`router.replace("/login")`.

Type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: fe-fetch-and-cache)

Command — IMPLEMENTED 2026-09-04, in the frontmatter above, exactly as
proposed and now that both sites are converted. Two `--tree` lanes: the first
bans a soft navigation TO an auth route from anywhere in the app, the second
bans a soft navigation of any kind INSIDE the auth flow (its pages and
feature), which is where the return leg lived. The quote class lists all three
JS string delimiters — double, single and backtick — so no spelling of the
literal slips past; verified against a probe holding each one, and verified to
bite through the runner on both lanes before this was written —
`router.replace('/login')` in use-dashboard and `router.replace("/runs")` in
use-auth-page each turned the rule FAIL with the offending line printed.

Condition: `none` — `--tree` blocks in both lanes, so the invariant is asked
on every commit and every sweep rather than only when a frontend file happens
to be staged. Two `git grep`s over four pathspecs, measured at 0.01-0.06 s.

Delete-check: Two deletions are available and the cheap one is the rule. Expensive: give the
cache an identity — queryClient.clear() + a useRunEventsStore purge + a
clearPersistedRun sweep on every identity change — strictly more machinery
than the one-line fix, and it must then be remembered at every future
transition. Cheap: collapse the option so /login has exactly one door
(hardNavigate, whose spelling rule-hard-nav-base-path already governs) and
router.push/replace to it does not exist. The rule enforces that collapsed end
state. Both lanes are green as of 2026-09-04 and neither is vacuous: each was
run against a deliberately reintroduced violation and failed with the offending
line, and `features/auth/__tests__/session-boundary-hard-nav.guard.test.ts`
additionally pins the positive half the ban-greps structurally cannot see —
that the two converted sites still CALL `hardNavigate`, with the base path.
A ban is satisfied by deleting the redirect outright.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **partly-wrong**.
A different agent re-ran every measurement before this reached the owner.

What it found:
Design comment confirmed: `sed -n '28,31p' aii_frontend/features/auth/use-
auth.ts` -> 'Cache invalidation isn't wired here because every auth state
change (login / signup / logout) navigates with ``window.location.href``,
which discards the QueryClient instance entirely.' Cache-clear grep confirmed
empty: `git grep -nE 'queryClient\.clear\(|qc\.clear\(|resetAll' -- .
':!lib/api/_hey-api/**' ':!**/__tests__/**'` -> no output. Soft bounce
confirmed: `git grep -nE 'router\.(push|replace)\(\s*.?/login' -- 'app/**'
'features/**' 'components/**' 'lib/**'` -> exactly one hit, features/runs-
list/use-dashboard.ts:921, and `sed -n '917,922p'` shows it is the auth guard.
Hard-nav sites confirmed: `git grep -nE 'window\.location\.href\s*=' --
'app/**' 'features/**' 'components/**' 'lib/**' ':!lib/api/_hey-api/**'` ->
features/auth/api.ts:64, features/auth/use-auth-page.ts:21,
features/sidebar/sidebar.tsx:609, lib/api/hey-api-client.ts:68. Provider scope
confirmed: `git grep -n 'QueryClientProvider|new QueryClient\(' -- 'app/**'
...` -> app/providers.tsx:32/43, root-level, so it does survive a soft route
change. DB name confirmed: `grep -n 'aii-run-events' aii_frontend/lib/run-
events-persist.ts` -> 39:const DB_NAME = "aii-run-events". BUT the return-leg
claim fails: `git grep -n 'hardNavigate' -- 'app/**' 'features/**'
'components/**'` -> app/login/page.tsx:68 and app/signup/page.tsx:65 both call
hardNavigate("/runs"), and `sed -n '66,70p' app/login/page.tsx` shows it on
the 200 branch with the comment 'Hard nav so all hooks (auth probe, etc.) re-
fetch with the new session.' And `git grep -nE '\.reset\(' -- .
':!lib/api/_hey-api/**' ':!**/__tests__/**'` returns THREE hits
(features/playback/url-sync.tsx:69, features/playback/use-playback-
controller.ts:61, features/runs-list/optimistic-delete.ts:177), not the one
claimed.

Corrected statement of fact:
The single soft `/login` bounce is real, but the stated consequence is not.
The proposal says 'The return leg is soft too: features/auth/use-auth-
page.ts:32 router.replace("/runs") in useRedirectIfAuthenticated, so nothing
in that round trip discards the cache.' That hook only fires for a user who is
ALREADY authenticated and lands on /login — same session, so no cross-account
carryover. The actual sign-in leg is hard: app/login/page.tsx:68 and
app/signup/page.tsx:65 both call hardNavigate("/runs"), which is
window.location.href (use-auth-page.ts:20-21) and does discard the QueryClient
exactly as use-auth.ts documents. So the exposure window is 'stale cache
retained while sitting on /login after a session lapse', with no account-
scoped UI rendering from it and a hard nav closing it — much narrower than
'the previous session's runs list, masked API-key hints and IndexedDB records
survive into the next session'. The rule is still defensible as a hardening
pin (make the guard's bounce hard, or clear on 401), but the measured defect
is a design inconsistency, not a data-scoping leak, and the proposal's
`.reset(` grep result is misreported.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Confirmed all four session-boundary navigations use
window.location.href, and use-auth.ts documents that this IS the cache-
invalidation mechanism. Converting one to router.push leaves the previous
identity's QueryClient and module-level run store intact — a data-scoping
defect a comment currently guards.
- KEEP: Population is derivable from the allauth login/signup/logout
operations rather than a hand-listed set, so a new auth flow cannot slip past,
and the assertion (window.location.href, not router.push) is a grep. A shared
QueryClient surviving a logout is a data-scoping defect; rule-hard-nav-base-
path assumes hard navs exist rather than requiring them.
- KEEP: The dimension is cross-account state survival, and the cheap correct
end state is a whole-tree ban-grep with no deletion that removes it: the
module-level run-events store lives outside React and cannot be reset by
`queryClient.clear()` alone, so the delete-check's 'expensive' option does not
actually close it. Unclaimed — PENDING rule-hard-nav-base-path governs the …

CONVERTED 2026-09-04 — the two sections above are the record of what was
measured on 2026-08-24 and are left as written; this is the present.

Both soft legs are gone and the rule is a cmd-check, so the invariant is now
asserted mechanically rather than by an agent verdict on every frontend
commit. What changed, and what it does today:

| site | was | is |
|---|---|---|
| use-dashboard.ts | `router.replace("/login")` :927 | hard, :937 |
| use-auth-page.ts | `router.replace("/runs")` :32 | hard, :50 |

Both new call sites read `hardNavigate` with a `resolveBasePath()`-prefixed
template literal — the spelling `test_hard_navigation_keeps_the_base_path.py`
requires and which that guard now covers for two more sites.

`useRedirectIfAuthenticated` no longer imports `useRouter` at all. The exit
leg is the one that mattered — it is where a lapsed session's QueryClient
survived into the next sign-in on the same tab — and the return leg is
converted for symmetry, at the cost of one document load on a path that only
fires for a visitor who is already signed in and lands on an auth page.

The audit's "exposure window is 'stale cache retained while sitting on /login
after a session lapse'" is therefore closed: the bounce that opened it now
discards the document. Its narrowing of the ORIGINAL claim still stands and is
why this reads as a hardening pin rather than an incident — the sign-in leg
was already hard, so no cross-account carryover was ever observed.

HARDENED 2026-09-14 — both lanes are judged on every run, and a missing tool
is a refusal. `run.sh` was `lane_a && lane_b`, and the correction is worth
stating precisely because the obvious reading of that chain is wrong: it WAS
rc-correct. Measured against a staged fixture, a violating lane exited 1, a
rules-grep that could not run exited 2, and an absent rules-grep exited 127 — the
hook never read as a clean pass. What `&&` actually did was make the second
question conditional on the first having no answer: staged against a fixture
violating BOTH legs, only lane A's line printed and lane B never ran. That is
standing rather than per-commit — while any finding sits in lane A, lane B is
never asked and reports nothing for as long as that lasts, which is a lane
passing without being run. The script now runs both lanes, collects each
status, and returns the worst: 0 both clean, 1 a soft navigation, 2 cannot
run. `set -euo pipefail` replaces `set -uo pipefail` so a failure between the
lanes cannot fall through to the final `exit "$rc"` with a stale 0, and an
absent or non-executable `rules-grep` is now a named `cannot run:` at rc 2
instead of bash's bare 127. `test_fe_session_boundary_hard_nav_bites.py` pins
all of it, and the lane-B test asserts on the printed lines rather than the
exit code, since both versions exit 1 when both lanes are violated. Sweep over
the consumer: rc 0, unchanged.

Line numbers re-measured the same day: `features/auth/api.ts:64`,
`features/sidebar/sidebar.tsx:623` (was :609), `lib/api/hey-api-client.ts:68`,
`app/login/page.tsx:69` (was :68), `app/signup/page.tsx:66` (was :65), and
`use-auth-page.ts:32` is now the `window.location.href` assignment inside
`hardNavigate` itself rather than a `router.replace`.
