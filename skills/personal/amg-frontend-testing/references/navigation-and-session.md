# Navigation, history and session

Bugs that live between pages rather than on one. Most are invisible to a suite
that navigates only by `goto`.

Start with the correction, because it invalidates a test many suites already
have.

---

## Tab visibility is never exercised by default

**Every Playwright page reports `visibilityState: "visible"` and
`document.hasFocus() === true` at the same time, and `bringToFront()` does not
hide the others.** So:

- pause-polling-when-hidden
- refetch-on-window-focus
- idle logout
- pause-media-when-hidden

are **never tested**, and a test that "blurs the window" by dispatching a
`blur` event is testing nothing the app's own code path uses.

Emulate it properly, in an init script:

```ts
await context.addInitScript(() => {
  let state: DocumentVisibilityState = "visible"
  Object.defineProperty(document, "visibilityState", { get: () => state, configurable: true })
  Object.defineProperty(document, "hidden", { get: () => state === "hidden", configurable: true })
  ;(window as any).__setVisibility = (v: DocumentVisibilityState) => {
    state = v
    document.dispatchEvent(new Event("visibilitychange"))
    window.dispatchEvent(new Event(v === "hidden" ? "blur" : "focus"))
  }
})
```

Then assert the behaviour that matters, with the request ledger:

```ts
await page.evaluate(() => (window as any).__setVisibility("hidden"))
const before = tally.size
await page.waitForTimeout(5_000)
expect(tally.size, "polling must stop while hidden").toBe(before)
await page.evaluate(() => (window as any).__setVisibility("visible"))
await expect.poll(() => tally.size).toBeGreaterThan(before)   // refetch on return
```

## Is it still the same document?

A stray `<a href>` or a `location =` that reboots the SPA loses all in-memory
state and refills every cache — and looks identical in a screenshot.

```ts
await context.addInitScript(() => { (window as any).__docId = Math.random() })
// same id after an in-app navigation = same document; a new id = full reload
```

One sentinel, and every navigation assertion in the suite can use it.

## History discipline

Record what the app pushes:

```ts
await context.addInitScript(() => {
  ;(window as any).__nav = []
  ;(navigation as any)?.addEventListener("navigate", (e: any) =>
    (window as any).__nav.push({ type: e.navigationType, to: e.destination.url }))
})
```

The `navigation` API is in Chromium, Firefox and WebKit. What it catches:

- A filter or search box that **pushes per keystroke** — Back then takes twenty
  presses to leave the page.
- A modal that **pushes and never pops**.
- A redirect that **pushes instead of replacing**, so Back bounces you forward
  again.

Rule of thumb: transient UI (modal, menu, tooltip) pushes nothing; a filter
change **replaces**; a real destination change **pushes**.

## Back, and what it restores

Three distinct failures, all common:

- **Restoration desync.** The browser refills *uncontrolled* inputs after Back
  while framework state, the dirty flag and validation all reset to defaults.
  The user sees their text on screen and submits an empty payload. After
  `goBack()`, read `inputValue()` and assert the **submitted body matches what
  is displayed**.
- **Scroll restoration**, with a harness trap: `page.click()` scrolls its
  target into view first, so clicking an above-the-fold link zeroes `scrollY`
  and your test measures Playwright, not the app. Scroll, navigate via
  `location.href` or an on-screen link, `goBack()`, then `expect.poll` on
  `scrollY`. Assert **inner** `overflow` containers too — browsers never
  restore those.
- **Refresh mid-state**, three rules: `history.state` and the URL survive
  `reload()` byte-for-byte; the aria snapshot of `main` is identical before and
  after for the same URL; and state that is *not* in the URL — an open dialog,
  a drawer — **must be gone** after reload. A modal that survives F5 is a bug in
  the other direction.

## Navigating with an overlay open

Leaves scroll locked, siblings `inert` or `aria-hidden`, focus on a removed
node, or the overlay floating over the new route. Snapshot a residue probe
clean, then again after navigating mid-overlay:

```ts
const residue = () => page.evaluate(() => ({
  bodyOverflow: getComputedStyle(document.body).overflow,
  pointerEvents: getComputedStyle(document.body).pointerEvents,
  inertCount: document.querySelectorAll("[aria-hidden=true],[inert]").length,
  focusAttached: document.body.contains(document.activeElement),
}))
```

Then **click something** to prove the page is still interactive. A residue
probe that passes while the app is inert is not enough.

## Unsaved-changes guards

**Without a `page.on("dialog")` listener, Playwright lets the navigation
straight through — so every `beforeunload` test is a false green.** Attach a
dismissing listener and treat the rejected `reload()`/`goto()` as the pass.

Test it in **both** directions: a guard that fires on a *clean* form is equally
a bug, and so is one that keeps firing after a successful save.

## Multiple tabs

Two pages in one context are two real tabs sharing cookies and storage.

```ts
const b = await context.newPage()
// log out in A…
await expect(bIsLoggedOut(b)).toBeTruthy()      // B reacts without a reload
expect((await context.storageState()).cookies.find((c) => c.name === "session")).toBeUndefined()
```

Assert B **stops calling the API** with a dead session, not just that it
re-rendered.

The blind spot: **`storage` events do not fire in the tab that wrote them.** An
app that syncs tabs via `localStorage` will look broken in the writer and fine
in the reader, or vice versa — so assert both tabs, never one.

For concurrent writes, gate a route on a promise to force a deterministic
interleaving: two tabs writing one record, a 401 landing while a mutation is in
flight, and N concurrent 401s → assert the token refresh is **single-flight**
(`refreshes.length === 1`).

## bfcache

Only matters for apps with live data — polling, sockets, feeds, a cart — and
only testable in Chromium.

**The cheap check first, no config change needed:** a single `unload` listener
anywhere, including in a third-party script, makes the whole app
bfcache-ineligible.

```ts
const { listeners } = await cdp.send("DOMDebugger.getEventListeners", { objectId })
expect(listeners.filter((l) => l.type === "unload")).toEqual([])
```

If it matters beyond that, bfcache needs its own project — Playwright disables
it by default (`ignoreDefaultArgs: ["--disable-back-forward-cache"]`, real
`channel: "chromium"`), so keep it in a separate lane rather than slowing every
spec. Then probe `pageshow.persisted` and `notRestoredReasons`. The bug class:
a restored page showing minutes-old data because nothing refreshed on
`pageshow`.

## Popups and external links

`<a target="_blank">` is opener-safe in current browsers.
`window.open(url, "_blank")` **without** `"noopener"` is not.

```ts
const [popup] = await Promise.all([context.waitForEvent("page"), link.click()])
expect(await popup.evaluate(() => !!window.opener)).toBe(false)
```

Assert the popup **opened at all** — a blocked or silently-failed
`window.open` is the other half of this test.

## Interrupted navigation

A superseded `goto` rejects with `net::ERR_ABORTED`; that is expected, not a
failure. What to assert is that **the last navigation wins** and no spinner is
left stuck. And that `setOffline(true)` produces a real offline state, with
recovery on `setOffline(false)` that does **not** require a reload — see the
offline caveat in `fuzzing-and-chaos.md`, since `setOffline` is a no-op against
a route-mocked API.

## Fragment links

Only when `a[href^="#"]` exists. Focus must actually **move** to the target —
which needs `tabindex="-1"` on it — not just scroll. `document.querySelector(":target")`
must match, and `scrollY > 0`. Back over a hash change resolves `null` and must
not reload the document.
