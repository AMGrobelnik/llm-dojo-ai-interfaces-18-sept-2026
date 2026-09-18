# The exploratory loop

Verifying a known bug is a spec. **Exploring** is a different activity, and
running it ad-hoc is how you end up with forty screenshots and no findings.

This is the loop. It is bounded, it records as it goes, and it reports a
matrix — including the cells it did not test.

---

## Before you start

**Decide the driving mode.**

- **Live MCP** (`browser_snapshot`, `browser_click`, `browser_hover`,
  `browser_console_messages`, `browser_network_requests`) — free-form poking,
  when you do not yet know what you are looking for. `browser_snapshot`
  returns an accessibility tree with stable refs, strictly better than
  guessing selectors off a screenshot.
- **A spec file** — anything you want to re-run, and anything that needs
  fixtures, mocked backends, or a viewport matrix.

Start live, switch to a spec the moment you find something worth keeping.

**Guard the destructive endpoints.** An exploratory pass clicks things. On a
real backend that means it will eventually click Delete.

```ts
for (const p of ["**/delete**", "**/stop**", "**/fork**", "**/submit_review**"]) {
  await page.route(p, (r) => r.fulfill({ status: 200, body: "{}" }))
}
```

Either mock them, or explicitly allowlist the ones you intend to exercise and
say so in the report. Never discover the list by triggering it.

**Decide teardown.** State mutated during a live pass persists in the dev
database. Either work entirely against mocks, or use run-unique ids and clean
up after yourself.

**Pin the nondeterminism**, or every screenshot differs for reasons that are
not bugs:

```ts
await page.clock.install()
await page.clock.setFixedTime(new Date("2026-01-01T00:00:00Z"))   // before goto
```

## The loop

```
for each screen in scope:
  navigate → settle → shot("00-initial") → diagnostics baseline

  enumerate interactive elements (aria snapshot or the inventory dump)

  for each element, up to a HARD CAP on actions:
      assert it is topmost (§ covered-element check)
      shot("NN-before")
      act (hover / click / focus / type)
      settle
      shot("NN-after")
      read: console ledger, request ledger, overflow, orphan portals
      if anything changed unexpectedly → minimise and record a finding

  run the state-machine passes: hover-out, re-entry, keyboard-only, Escape
  run the environment axes for this screen
```

The hard cap matters. An uncapped loop on a 200-element page produces an
unreadable pile and burns the session. 30–50 actions per screen is plenty;
say in the report that you capped it.

## The two helpers everything depends on

**`settle`** — the honest alternative to `waitForTimeout`. Wait for animations
to actually finish, not for a guessed duration:

```ts
async function settle(page) {
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((a) => a.effect?.getTiming().iterations !== Infinity)
        .map((a) => a.finished.catch(() => {})),
    ),
  )
  await expect(page.locator("[data-loading], .animate-pulse")).toHaveCount(0)
  await page.evaluate(() => new Promise(requestAnimationFrame))
}
```

**`shot`** — no raw `page.screenshot()` anywhere in an exploratory pass. Every
capture settles first, and is named by sequence and action so the frames read
as a story:

```ts
let seq = 0
async function shot(page, action: string) {
  await settle(page)
  const name = `${String(seq++).padStart(2, "0")}-${action}.png`
  await page.screenshot({
    path: `${DIR}/${name}`,
    caret: "initial",
    mask: [page.locator("[data-ts], [data-live-timer]")],
  })
  return name
}
```

A screenshot taken before settle shows the *previous* state. That single
mistake has produced more wrong conclusions than any other.

## Ledgers

Install once, in `beforeEach`, and fail on a non-empty ledger unless the test
opted out. Details and code in `diagnostics.md`; the exploratory-specific
additions are:

**Request ledger with a budget.** Record method, url, status, duration for
everything. Then assert no endpoint fired more than N times:

```ts
const overBudget = [...tally.entries()].filter(([, n]) => n > POLL_BUDGET)
expect(overBudget, JSON.stringify(overBudget)).toEqual([])
```

This is what catches an infinite refetch loop. Every UI assertion passes
straight through one.

**Console allowlist.** Without an explicit array of known-benign regexes,
people mute the whole check. With one, the check survives. Two entries every
Next.js dev run needs, both measured rather than assumed:

```ts
const BENIGN = [
  // Route prefetches aborted on navigation. Fires several times per page load
  // and means nothing.
  /net::ERR_ABORTED.*\/runs\//,
  // Endpoints the mock harness deliberately does not install.
  /\/api\/runs\/[^/]+\/config/,
]
```

**React error boundaries swallow render errors into `console.error`**, so match
on the text: `/Uncaught|The above error occurred|hydrat|did not match/i`.

**Do not assert `nextjs-portal` has count 0.** Measured: it is present on every
page in dev — it is the dev-tools indicator, not an error marker — so that
assertion fails on a perfectly healthy app. The console patterns above are the
signal; the overlay is not.

**Orphan portals**, after closing everything:

```ts
await expect(
  page.locator('[data-radix-popper-content-wrapper], [role="tooltip"], [data-sonner-toast]'),
).toHaveCount(0)
```

**Body left inert** — the universal post-overlay-close check:

```ts
const body = await page.evaluate(() => ({
  pointerEvents: getComputedStyle(document.body).pointerEvents,
  ariaHidden: document.body.getAttribute("aria-hidden"),
  scrollLocked: document.body.hasAttribute("data-scroll-locked"),
  overflow: getComputedStyle(document.body).overflow,
}))
```

Radix keeps `pointer-events: none` on `<body>` in JS while it believes a modal
is open. If something goes wrong on close, the whole app is inert and every
subsequent step in your pass fails for one reason.

**`page.on("dialog")`.** Playwright auto-dismisses an unhandled
`window.confirm` *silently*, which can make a destructive-action test pass for
entirely the wrong reason. Always attach a handler and record what appeared.

## Amplifiers

Cheap ways to make latent races actually happen:

```ts
// Slow CPU — the highest-yield race amplifier there is.
const cdp = await page.context().newCDPSession(page)
await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 })

// Slow network
await page.route("**/api/**", async (r) => {
  await new Promise((s) => setTimeout(s, 3000))
  await r.continue()
})

// Jank, as a number rather than an adjective. Use the LoAF + INP +
// layout-shift bundle in `whole-app-invariants.md § B` rather than a bare
// `longtask` observer: LoAF names the HANDLER that blocked the frame and
// reports forced-layout time, where `longtask` only says a frame was slow.
```

## Findings

A finding is not "this looks wrong". It is:

| Field | |
|---|---|
| **What** | One sentence, the defect |
| **Where** | `file:line` if found in the code, else screen/element |
| **Repro** | The *minimised* steps — strip what is not required |
| **Evidence** | Before/after pair, ledger line, measured number |
| **Severity** | see below |

**Severity:**

- **Blocking** — data loss, a destructive action firing wrongly, the app
  becoming inert or unusable.
- **Broken** — a feature does not work; a stuck or duplicated overlay; an
  uncaught error.
- **Degraded** — works, but wrong: layout overflow, clipped text, missing
  focus ring, ignored `prefers-reduced-motion`.
- **Cosmetic** — visible but harmless.

**Minimise before reporting.** Six screens showing the same stuck-portal
behaviour is *one* finding about the portal, not six. Dedupe by root cause,
and say where else it shows.

**Reproduce under the real backend** before reporting anything found under
mocks — otherwise the finding may be a fixture artifact.

**No unmeasured subjective claims.** "Janky", "slow", "flickers" need a
number: long-task durations, `getAnimations()` timings, a frame index from the
burst. Otherwise do not report it.

## The report

Always a matrix, always including what you did **not** cover:

```
Screens:   overview ✓  details ✓  trace ✗ (not reached)
Axes:      1280 ✓  375 ✓  768 ✓ | keyboard ✓ | dark ✗ | touch ✗ | reduced-motion ✓
Capped at: 40 actions/screen
Findings:  2 broken, 1 degraded, 3 cosmetic
Not tested: forced-colors, 200% zoom, webkit, offline
```

"Looks fine" from a single 1920 px screenshot, when the bug is at 375 px, is
the default failure mode of this whole activity. The list of untested axes is
the part that keeps the report honest.
