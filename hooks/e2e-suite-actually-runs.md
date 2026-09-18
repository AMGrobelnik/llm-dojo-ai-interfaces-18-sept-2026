<!-- hook: e2e-suite-actually-runs -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 5s | active |

> Static commit-time guard. Runs NO browser and needs NO live stack. The LIVE
> "one measured run" the proposal calls owner-gated is a CI-lane job, not this
> hook — see "The live half" below.
# The e2e suite is wired to run somewhere, and has not been gutted

The invariant: the frontend Playwright e2e suite must ACTUALLY RUN in some gate,
not merely exist. A flow nobody runs is green by definition. This hook is the
COMMIT-TIME half of `docs/proposals/e2e-suite-actually-runs.md` — a STATIC check,
because a commit hook must never run 183 specs that start, stop and DELETE live
runs.

## The incident

Measured 2026-08-28: nothing runs this suite. `aii_frontend`'s `test:e2e` script
(`playwright test`) is invoked by no CI job, no lefthook/pre-push hook, no rule
command, no `scripts/` entry, no crontab, and none of the six watcher units.
`bunx playwright test --list` resolves it to **183 tests across 39 spec files**
(4,983 lines, and still edited while never run). CI even installs Playwright's
Chromium (`bunx playwright install chromium`) and then never runs a Playwright
test — so anyone reading CI top-to-bottom assumes the e2e suite runs, and it does
not. That install-without-a-test is the exact trap this gate is built to catch.

**Closed 2026-09-14** by consumer commit `2da7264ee`, which added the `e2e` job
and taught the `aii-ci-watcher` to replay it as a fifth job group. The trap above
is now what predicate 1 holds SHUT, not what it reports.

## What it checks (four static facts, all from the git INDEX)

1. **A CI job invokes Playwright.** `.github/workflows/ci.yml` (the workflow the
   `aii-ci-watcher` replays as its job groups) must carry a `playwright test` /
   `test:e2e` invocation — NOT merely `playwright install` (a browser install
   that runs no test). **GREEN since 2026-09-14**: the `e2e` job's
   `bun run test:e2e:hermetic` (ci.yml:331) matches on `test:e2e`, the word
   boundary falling before the `:hermetic` suffix. This is the predicate that
   turns RED again if that job is ever deleted or degraded back to a bare
   install.
2. **The suite is non-empty.** At least one tracked `*.spec.ts` under
   `aii_frontend/tests/e2e` (the config's `testDir`). Zero specs is a dead suite.
3. **No blanket disable at the suite ROOT.** No `.only` (Playwright then runs
   ONLY marked tests, gutting the rest — `playwright.config`'s `forbidOnly` is
   dead without a CI run), and no top-level (column-0) `describe.skip` /
   `test.skip` / `describe.fixme` disabling a whole file or describe. A per-test
   conditional skip inside a test body (`if (!x) test.skip(true, ...)`) is fine
   and is NOT flagged — all 39 specs use exactly that form and pass.
4. **The config points somewhere.** `playwright.config.ts`'s `baseURL` is present
   and not empty / `undefined` / `null` (today it is
   `process.env.AII_FE_BASE_URL ?? "http://localhost:3000"`, which passes).

"Not this tree" -> skip clean: with no `aii_frontend/playwright.config.ts` in the
index there is no Playwright suite here, and the check exits 0 with a note. All
reads come from the INDEX, so a concurrent unstaged edit cannot move the verdict.

## Why static, and why NOT the env-var-gated runner

An earlier design ran the suite behind `[ -n "$RULES_APP_URL" ] || exit 0` (the
`flow-share-link` idiom). That is the wrong shape for a commit gate: the specs are
NOT read-only — they start, stop, fork and DELETE runs — so a commit hook that
ever runs them mutates a live deployment. This gate touches no browser and no
stack; it only proves the suite is wired to run and has not been gutted.

## The live half — a CI-lane job, owner-gated, not this hook

The proposal's literal "one measured run against a live app" is a CI-LANE job, not
a commit gate: add a Playwright job group to `ci.yml` that runs

    cd aii_frontend && AII_FE_BASE_URL="<live stack URL>" CI=1 bunx playwright test

against a live stack the OWNER designates. It cannot be defaulted — the specs
mutate state, so which deployment "eats" the suite is the author's call — and a
deployed target also needs `AII_E2E_USER` / `AII_E2E_PASS` (`auth.setup.ts`
defaults to the DEBUG-only `admin`/`admin`); `AII_FE_BASE_URL` and the CSRF
`Origin`/`Referer` headers already work against https with no code change. That
first run's verdict — mostly green, or deeply red — decides whether to wire the
CI job permanently or delete rotted specs. **This static gate is the commit-time
half; the measurement against an owner-designated deployment is still the owner's
step.** What landed on 2026-09-14 is the HERMETIC tier — CI stands up its own
Next and Django on `127.0.0.1` — so predicate 1 is satisfied by a stack CI builds
itself, not by the live one the proposal asks about. That greens predicate 1; it
does not answer the live question.

## Status: GREEN on arrival

Dry-run against `research-monorepo` today: **rc 0, no findings.** All four predicates
pass — the `e2e` job runs `bun run test:e2e:hermetic` (ci.yml:331), 39 specs, no
root disable, baseURL set. This section used to read "RED on arrival, by design",
which was true when the hook was written and stopped being true on 2026-09-14:
consumer commit `2da7264ee` added the very CI job the gate was built to ask for,
and the `aii-ci-watcher` replays it as its fifth job group
(`scripts/local/watchers/aii-ci-watcher.sh:572`).

RED is now the REGRESSION, not the status quo. Predicate 1 fires if that job is
deleted, commented out, or degraded back to a bare `playwright install` — and do
not weaken the check to hide such a finding, because an install-without-a-test is
the exact shape this gate exists to catch.

Wiring remains the merge owner's step, not a docs one: the hook still ships
**unwired** (the `status` cell in the header table above). What it is no longer
blocked on is the CI job, which has landed — so turning it on no longer risks
blocking every commit that touches CI, the config, or a spec.

## Delete-check

Cannot delete — this is the executable, commit-time half of a product invariant
(the e2e suite must run somewhere). It supersedes the "checked by a human,
occasionally, on purpose" status quo whose cheap half `test_e2e_routes_still_exist.py`
guards; that route-existence guard "is not a substitute" for running the suite,
and this pair (static gate + CI-lane job) is the substitute. Retire it only if the
suite is deleted or folded into a cheaper mocks-only tier.
