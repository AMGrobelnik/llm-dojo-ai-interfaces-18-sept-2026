# Playwright notes

Verified against **1.59.1**. Check what you actually have before trusting any
of it:

```bash
node -p "require('@playwright/test/package.json').version"
```

---

## Mode A — the repo already has a runner

This is the default in a real repo, and it is a much better position than a
standalone script: you inherit auth, backend mocks, `baseURL`, timeouts and
artifact handling for free.

**Write a temp spec into the runner's own `testDir`, run it, delete it in the
same turn.**

```bash
# from the frontend package root
bunx playwright test tests/e2e/tmp-<what>.spec.ts --reporter=list
# then, same turn:
rm -f tests/e2e/tmp-<what>.spec.ts && rm -rf test-results
```

Name it `tmp-*` so it is obvious it is not a real spec, and never leave one
behind — a stray temp spec joins the suite and fails for someone else later.

### Survey the harness before you write anything

Five questions, all answerable in under a minute. Do not skip them and then
wonder why the setup project failed.

- **Where do specs live, and what is `baseURL`?** Read
  `playwright.config.ts`: `testDir`, `use.baseURL`, `timeout`,
  `expect.timeout`.
- **Does anything START the app?** Look for a `webServer` block. **Usually
  absent** — then the dev server, and often a backend too, must already be
  running.
- **How does a spec get authenticated?** Look for a `setup` project +
  `storageState`. If auth logs in for real, the **backend is required even for
  fully mocked specs**.
- **Is the backend mocked, and how?** Grep the helpers dir for `page.route(`.
  A shared mock installer is the single most valuable thing to find.
- **Are there page objects?** A `pages/` or `po/` dir. Put new selectors there,
  not in your spec.

Then read **one existing spec end to end** before writing your own. It shows
the fixture-building idiom, the settle gate, and the assertion style — copying
it is faster and less wrong than inventing a parallel style.

Two config traps worth checking for specifically:

- **`workers: 1` + `fullyParallel: false`** is common for a single-tenant dev
  server. It means any axis you add multiplies wall-clock linearly, and it
  makes `test.describe.parallel` a no-op while `test.describe.serial` still
  skips every remaining case after the first failure.
- **A config docstring that contradicts the suite.** Comments rot; the specs
  are the truth. One real example: a config arguing at length against
  `page.route()` mocking, in a suite where 29 of 38 specs use exactly that,
  because the policy changed and the comment did not. Read what the specs do.

### Using a mock harness

If the repo has one, use it — hand-rolling `page.route()` per spec is how
fixtures drift apart. The shape is nearly always the same:

```ts
const EVENTS = buildFixture(ID, [ /* factory calls, in order */ ])
await installMocks(page, [{ id: ID, status: "running", events: EVENTS }])
await page.goto(`/some/${ID}/view`)
await expect(page.getByText("something real").first()).toBeVisible({ timeout: 20_000 })
```

Learn its API from its **exported symbols**, not from a spec that happens to
use three of them:

```bash
grep -n "^export " tests/e2e/helpers/*.ts
```

Things worth finding out before you rely on it:

- **Which endpoints it installs, and which it deliberately does not.** A
  harness usually omits the ones individual specs need to own with counting or
  delaying variants. Calling an un-mocked endpoint gives a 404 that looks like
  an app bug.
- **Route precedence: the LAST matching handler wins.** A narrow override must
  be registered *after* the general installer.
- **How it anchors timestamps.** A fixed date drifts out of any trailing time
  window the app applies and flakes on a clock that never changed;
  `Date.now() - 60_000` does not.
- **Whether it can model liveness** (serving a second batch on a later poll)
  and **truncated bodies** (an on-demand fetch path). Both are common, and
  both let you assert something the UI alone cannot.

A held-open route is the only reliable way to make a loading state observable —
and an unresolved one hangs teardown, which reads as a test timeout:

```ts
let release!: () => void
const held = new Promise<void>((r) => { release = r })
await page.route("**/api/**", async (r) => { await held; await r.continue() })
// …assert the skeleton…
release()   // ALWAYS
```

### A worked example

Measured on one repo (`research-monorepo/aii_frontend`), to show what the survey
above actually returns — **not** as instructions for your repo:

- `playwright.config.ts`: testDir `./tests/e2e`, baseURL `http://localhost:3000`,
  `workers: 1`, `fullyParallel: false`, 60 s test / 10 s assertion timeouts.
- No `webServer` block. The Next dev server **and** a Django backend on `:8020`
  must both be up — the backend even for fully mocked specs, because
  `auth.setup.ts` performs a real login to produce `storageState`.
- `aii_frontend/tests/e2e/helpers/mock-run.ts` exports exactly five symbols:
  `mockRuns(page, fixtures)`, `buildEvents(runId, factories)`, a `MockEvent.*`
  factory namespace (~23 event types), and the `MockRunFixture` /
  `MockEnvelope` types — the latter mirroring a named backend serializer.
- Page objects in `tests/e2e/pages/`: `auth, composer, feed, panels, playback,
  sidebar, topbar, tree`.
- Its `JOURNEYS.md` ✅ column means "a spec exists", **not** "this passed
  recently" — nothing runs the e2e suite automatically; CI runs lint,
  typecheck, unit and storybook only. Check that assumption in any repo before
  trusting a manifest.

## Mode B — standalone script

No runner in the repo, or the target is a deployed site.

### Resolve Playwright by absolute path, or the script cannot start

A scratch-dir script fails with `ERR_MODULE_NOT_FOUND: Cannot find package
'playwright'` — and **`cd`-ing into the repo first does not fix it.** Measured:
identical failure from the repo root, because ESM resolves bare specifiers from
the **importing file's** directory, never from `cwd`.

Two fixes; pick by whether you want the file in the repo:

```js
import { chromium } from "/abs/path/to/repo/node_modules/playwright/index.mjs"
```

or write the script inside the repo tree and delete it in the same turn. The
absolute import keeps the scratch dir clean and is the default here.

`node_modules/.bin/playwright --version` tells you the version you are actually
importing; do not assume it matches the docs you remember.

```js
// /scratch/probe.mjs   — node /scratch/probe.mjs
import { chromium } from "/abs/path/to/repo/node_modules/playwright/index.mjs"

const URL = process.env.TARGET_URL ?? "http://localhost:3000"
const browser = await chromium.launch({ headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  const page = await context.newPage()
  const notes = []
  page.on("console", (m) => m.type() === "error" && notes.push(`console: ${m.text()}`))
  page.on("pageerror", (e) => notes.push(`pageerror: ${e.message}`))
  page.on("requestfailed", (r) => notes.push(`requestfailed: ${r.url()}`))
  page.on("response", (r) => r.status() >= 400 && notes.push(`http ${r.status()}: ${r.url()}`))

  await page.goto(URL)
  await page.getByRole("main").waitFor()      // a real render signal, not networkidle

  // …drive…

  console.log(JSON.stringify({ notes }, null, 1))
  if (notes.length) process.exit(1)            // assert, don't demo
} finally {
  await browser.close()
}
```

Rules that matter here: explicit viewport (deterministic screenshots),
`headless: true`, `try/finally` close, a non-zero exit on findings, and
artifacts to an absolute scratch path — never a relative filename, never the
skill directory.

Locale is worth pinning too if anything renders dates:
`newContext({ locale: "en-US", timeZoneId: "UTC" })`. Leaving it implicit
means the machine's timezone leaks into your comparisons.

## CLI worth knowing

```bash
npx playwright screenshot <url> out.png --device="iPhone 15" --color-scheme=dark \
                                        --full-page --wait-for-selector=main
npx playwright test --headed --debug          # a human is watching
npx playwright test --last-failed             # re-run only what broke
npx playwright test --only-changed [ref]      # specs touching changed files
npx playwright trace actions /tmp/trace.zip   # headless trace inspection — see transitions.md
npx playwright trace install-skill            # Playwright's own trace skill
npx playwright init-agents --loop claude
```

## Device / viewport emulation traps

- `options.isMobile` **throws on Firefox**, so spreading a mobile device
  descriptor breaks any cross-browser sweep that includes it.
- With `isMobile: true` on a page lacking `<meta name="viewport">`,
  `innerWidth` reports **980** (the mobile layout viewport), not the device
  width — measured 980 for an iPhone 15 context declaring 393. Responsive
  assertions on `innerWidth` will read wrong.
- Set emulation at **context** level (`colorScheme`, `reducedMotion`,
  `forcedColors`, `contrast`, `hasTouch`, `deviceScaleFactor`) rather than
  calling `emulateMedia` after navigation — an app that reads the preference
  during hydration will already have made its decision.
- `emulateMedia` accepts `contrast: "no-preference"|"more"` and
  `forcedColors: "active"|"none"` only; pass `null` per key to clear.
- 143 device descriptors ship in 1.59.1 (`devices["iPhone 15"]`).

## Existence check, since it changes between versions

Present in 1.59.1: `page.screencast`, `page.clock`, `page.ariaSnapshot`,
`locator.ariaSnapshot`, `expect(...).toHaveScreenshot`, `toMatchAriaSnapshot`,
`toPass`, `expect.poll`, `locator.pressSequentially`, `page.emulateMedia`,
`page.mouse`, `page.touchscreen`, `locator.highlight`, `browser.startTracing`.

**Absent** in 1.59.1: `page._snapshotForAI()`, `page.accessibility`. Both were
real once and are gone.

Deprecated, do not teach: `page.waitForNavigation()`, `page.type()` /
`locator.type()` (use `fill` or `pressSequentially`), `page.$$eval` (use
locators), `page.waitForLoadState("networkidle")`.

`page.pickLocator()` exists but **never resolves in headless** — it blocks
waiting for a human in the Inspector. Keep it out of automated flows.

## `window.scrollTo` scrolls nothing in an app-shell layout

A shell that sizes itself to the viewport (`h-dvh`, `flex-1`,
`overflow-hidden` on `main`) puts the scrollbar on an INNER div. The window
does not scroll, so `window.scrollTo`, `document.body.scrollHeight` and any
loop built on them are no-ops that fail silently — the page looks unchanged
because it IS unchanged.

Everything viewport-triggered then reports a false result: lazy images stay
unloaded, infinite scroll never pages, sticky headers never engage,
`IntersectionObserver` never fires. Measured once: a gallery reported
"12 skeletons, unchanged after scrolling, 0 network requests started",
which reads exactly like a stuck loading state. The real scroller was
`DIV.flex-1.overflow-y-auto` at 5845/900; driving it took skeletons 12 -> 0
and images 29 -> 41/41. The feature was correct the whole time.

Find the scroller, then assert you moved it:

    const el = [...document.querySelectorAll("*")].filter((e) =>
      e.scrollHeight > e.clientHeight + 200 && e.clientHeight > 300
    ).sort((a, b) => b.scrollHeight - a.scrollHeight)[0]

Return the maximum `scrollTop` actually reached and assert it is non-zero.
A scroll test that cannot prove it scrolled proves nothing.

`page.mouse.wheel` does scroll the hovered element, so it can work where
`window.scrollTo` does not — but it depends on pointer position, so it is
not a substitute for asserting displacement.

## Unroute before the page closes

A handler doing `route.fetch()` throws "Target page, context or browser has
been closed" when a background poll fires during teardown, and the test is
reported as FAILED even though every assertion already passed. Either
`await page.unrouteAll({ behavior: "ignoreErrors" })` at the end, or capture
the passthrough body once up front and `fulfill` from it instead of
re-fetching per request.

## Check which engines the config actually defines

A `playwright.config.ts` with only a `chromium` project means every finding
and every clean sweep is single-engine — a coverage gap that never announces
itself. Check `~/.cache/ms-playwright/` for `firefox-*` / `webkit-*` builds:
if they are present, cross-engine costs nothing but wall-clock.

Drive them straight from the API rather than editing the shared config:

    import { chromium, firefox, webkit } from "@playwright/test"
    const ctx = await engine.launch().then((b) =>
      b.newContext({ storageState: "tests/e2e/.auth/admin.json" }))

Two practical notes: a standalone script must live INSIDE the project or it
cannot resolve `@playwright/test` from node_modules; and compare structural
signals (axe violations, landmark/heading counts, overflow, console errors)
rather than screenshots, which differ across engines for reasons that are
never defects.
