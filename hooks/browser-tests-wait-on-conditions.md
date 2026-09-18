<!-- hook: browser-tests-wait-on-conditions -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# A browser test waits on a condition, never on `networkidle` (the app polls, so the wait burns its timeout) and never clicks with `force: true` (needing it is the finding)

Both traps are recorded in `.claude/skills/amg-frontend-testing/SKILL.md`
under "Traps that have actually cost time here": "The network is never
idle; the wait burns its entire timeout. Two of them once ate a 60 s budget
before the code under test ran", and `force: true` "disables the
actionability check that catches an element under an overlay — so needing
it is the finding". A sibling vendored skill teaches the opposite for
generic apps, which is exactly why the house rule needs pinning here.

Measured 2026-09-03 in `aii_frontend/tests/e2e/`:

| form | sites |
|---|---|
| `waitForLoadState("networkidle")` | 5, all in wide-ui-sweep |
| `{ force: true }` | 8: starred-runs ×5, delete-run ×3 |

Those five `networkidle` waits were each wrapped in `.catch(() => {})`,
which suppressed the error but not the timeout; the same file already
carried two comments saying "NOT `networkidle` here". None of the eight
forced clicks cited the one documented exception (an element under an
infinite CSS animation).

Mechanism: `rules-grep` in `--tree` (whole-index) form over frontend
TypeScript. Stock is 0 as of 2026-09-14, so there is nothing pre-existing
to ride free: every match the ERE reports blocks, committed stock included.

The LIVE lane is still that bare `amg-hooks-grep` run line. `dispatch.py` is the
port that replaces it at the dispatcher cutover: the same ERE as a cheap
per-line PREFILTER, plus a structural confirmation from `lib/amg_hooks/tsast`.
Findings stay a subset of the grep's candidates, so nothing new is added.

The split is the ERE's own two alternatives, each with its own confirmation:

| alternative | what it is | confirmed by |
|---|---|---|
| `waitForLoadState\("networkidle"\)` | a call | a call node |
| `force: *true` | an object property | a property node + its call |

The wait is a real call expression, so the AST answers it: a call whose
member is `waitForLoadState` with a statically known `networkidle` first
argument. A `//` or `/* */` comment quoting the call, and a string literal
holding it, build no call node and are DROPPED — the class this tree is
already one edit away from, since lines 103, 242 and 301 of
`wide-ui-sweep.spec.ts` each name `networkidle` in prose.

`force: true` is a property node since 2026-09-17: `tsast` reports every
object-literal `key: value` with its own line and `arg_of`, the call the
object is a direct argument of. A `force: true` survives only when that
call's method tail is a Playwright actionability method (`_ACTION_METHODS`
in `dispatch.py`: click, dblclick, tap, hover, fill, check, uncheck,
setChecked, selectOption, selectText, clear, dragTo, dragAndDrop) or when
the port cannot place it (a bare `const opts = { force: true }`, an
unresolvable callee) — those keep the grep's verdict. Two former false
positives are dropped: a `/* force: true */` comment, and Node's
`rmSync(dir, { force: true })`, which was a live hit on an e2e fixture
teardown that could only be written by not writing it. A helper that
forwards the option under its own name is dropped too; the ban is read
where the flag reaches Playwright.

Measured against the consumer index 2026-09-14, whole-index lane: 724
files in the population (glob spelling since re-measured — see below), 0
candidates, 0 findings, 0 dropped, 0 added. The parser is started only when
a candidate exists, so the port adds no bun time to a dispatcher run on a
clean tree (~130 ms for the first file, ~147 ms for 25, all in one process
shared with the other TS checks).

One divergence, forced and measured. The port's PATHSPEC carries the run
line's two positives and NOT its `:!.claude/`. That exclude subtracts
nothing here — every path the positives select starts with `aii_frontend/`,
and `git ls-files` does not recurse into a gitlink — but spelt root-anchored
against deeper-rooted positives it makes `ls-files` return NOTHING: 724
paths without it, 0 with it. `git grep` does not share that behaviour, which
is why the live carrier never noticed. Carried verbatim it would trip the
port's empty-population floor on every commit, so it is recorded in the
PATHSPEC comment and pinned by two tests instead.

Re-measured 2026-09-14 over the consumer INDEX: **stock 0**. Zero
`waitForLoadState("networkidle")` calls and zero `force: true` anywhere
under `aii_frontend/`. The only `networkidle` strings left are three
comments in `tests/e2e/wide-ui-sweep.spec.ts` — lines 103, 242 and 301,
each of them saying NOT to use it — and the ERE correctly leaves those
alone, because it requires the CALL. That is the same distinction
`probe/miss.spec.ts` pins below. The zero is a clean stock and not an
empty search: under a loose `networkidle` grep the same pathspec still
returns those three lines.

That retired the reason this hook was wired commit-lane, and the flip has
now landed: the wired line carries `--tree`, and its glob spelling also
moved from `aii_frontend/**/*.ts` to `aii_frontend/**.ts` (`COND1 trigger
gaps`), which reaches 6 more files sitting directly under `aii_frontend/`
with no intervening directory (`next.config.ts` and siblings) — PATHSPEC is
updated to match, and the stock is still 0 under the wider population.

PORTED 2026-09-14 onto the one-pass AST dispatcher: the standalone
`amg-hooks-grep` line is removed from `research-monorepo/lefthook.yml`, and
`research-monorepo-ast-checks` (the shared dispatcher command) now discovers and
runs this hook's `dispatch.py` in the same pass as every other TypeScript
AST-confirmed hook. `SCOPE` is `"tree"`, matching the wired `--tree`: there
is one lane, and a committed violation blocks a later unrelated commit the
same as any other tree-mode hook.

Probes, both ways (2026-09-03, `rules-grep` in a scratch repo, probes staged
as added lines): `probe/hit.spec.ts` → both forms matched, exit 1;
`probe/miss.spec.ts` — a `toBeVisible` expectation, a plain click, a
comment naming `networkidle` (matches nothing: the ERE requires the call),
and since 2026-09-17 an `rmSync(..., { force: true })` (a candidate the
property fact drops) → exit 0.

Nearest existing rules: none names Playwright, e2e waits or actionability;
`rule-e2e-suite-actually-runs` (pending) is about the suite having a runner.

Delete-check: delete when the run viewer stops polling (a push transport
makes `networkidle` reachable) AND the overlay-under-click class has a
different guard; neither is planned.
