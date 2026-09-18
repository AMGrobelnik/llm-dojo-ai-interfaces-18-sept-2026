# Diagnostics

Capturing is easy; diagnosing is the job. These are the probes that turn "it
looked wrong" into a named cause.

All snippets are `@playwright/test` (TypeScript). For standalone `playwright`
scripts the same code works with `page` from a manually launched browser.

---

## The observer harness

Attach before `page.goto`, always, even for a one-line check. Four listeners,
because each misses what the others catch:

```ts
type Note = { kind: string; text: string }

function observe(page: import("@playwright/test").Page): Note[] {
  const notes: Note[] = []
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") {
      notes.push({ kind: `console.${m.type()}`, text: m.text() })
    }
  })
  // An uncaught exception often produces NO console message. This is the one
  // that catches the thing that actually broke.
  page.on("pageerror", (e) => notes.push({ kind: "pageerror", text: e.stack ?? e.message }))
  // Transport-level failure: DNS, refused, aborted. Never fires for 4xx/5xx.
  page.on("requestfailed", (r) =>
    notes.push({ kind: "requestfailed", text: `${r.url()} — ${r.failure()?.errorText}` }),
  )
  // …which is why this one exists. A 404 is a SUCCESSFUL exchange; without
  // this it shows only as an opaque "Failed to load resource" console line
  // with no URL attached.
  page.on("response", (r) => {
    if (r.status() >= 400) notes.push({ kind: `http.${r.status()}`, text: r.url() })
  })
  return notes
}
```

Print `notes` at the end of every run. **A passing assertion with a non-empty
`notes` is a finding**, not a pass.

Two caveats:

- Unhandled promise rejections surface as `pageerror` in Chromium but not
  everywhere. If you need them explicitly, add an init script:
  `await page.addInitScript(() => { window.addEventListener("unhandledrejection", (e) => console.error("unhandledrejection:", String(e.reason))) })`
- If the run inspects console output, screenshot with `caret: "initial"`.
  Playwright's default `caret: "hide"` writes `caret-color: transparent` into
  the live DOM, and landing mid-hydration that makes React log an attribute
  mismatch — the sweep manufactures its own failure. Measured: 0 errors
  without a screenshot, 1 with.

## Inventory

Run once per new page, before choosing any selector. Read the output; pick
from it.

```ts
const inventory = await page.evaluate(() => {
  const out: unknown[] = []
  const sel = 'button, a[href], input, textarea, select, [role="button"], [role="tab"], [role="link"], [tabindex]:not([tabindex="-1"])'
  document.querySelectorAll<HTMLElement>(sel).forEach((el, i) => {
    const r = el.getBoundingClientRect()
    if (r.width === 0 && r.height === 0) return
    out.push({
      i,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role"),
      testid: el.getAttribute("data-testid") ?? el.getAttribute("data-slot"),
      name: el.getAttribute("aria-label") ?? (el.textContent ?? "").trim().slice(0, 50),
      rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
      visible: getComputedStyle(el).visibility !== "hidden" && getComputedStyle(el).display !== "none",
    })
  })
  return out
})
console.log("INVENTORY " + JSON.stringify(inventory, null, 1))
```

Better still, in 1.59+, ask Playwright for the semantic tree with element
handles attached:

```ts
const snap = await page.ariaSnapshot({ mode: "ai" })   // emits [ref=eN] handles
// …then act on one:
await page.locator("aria-ref=e12").hover()
```

`mode: "ai"` includes `<iframe>` contents and skips auto-waiting. This is what
a screen reader sees, so a mismatch between it and the screenshot is itself a
bug. `page.ariaSnapshot({ depth: 1 })` and `locator.ariaSnapshot()` scope it.

Two dead APIs — do not reach for either:

- `page._snapshotForAI()` **does not exist** in 1.59.1 (verified `undefined`
  at runtime and absent from `playwright-core/lib`). `ariaSnapshot({ mode: "ai" })`
  replaced it.
- `page.accessibility` **does not exist** either. The old
  `page.accessibility.snapshot()` is gone; use `ariaSnapshot` or
  `expect(locator).toMatchAriaSnapshot()`.

## Overflow probe

Catches the single most common responsive defect.

```ts
const overflow = await page.evaluate(() => {
  const doc = document.documentElement
  const offenders: unknown[] = []
  if (doc.scrollWidth > doc.clientWidth) {
    document.querySelectorAll<HTMLElement>("*").forEach((el) => {
      const r = el.getBoundingClientRect()
      if (r.right > doc.clientWidth + 1 || r.left < -1) {
        offenders.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.getAttribute("class") ?? "").slice(0, 60),
          right: Math.round(r.right),
          text: (el.textContent ?? "").trim().slice(0, 40),
        })
      }
    })
  }
  return {
    pageOverflows: doc.scrollWidth - doc.clientWidth,
    offenders: offenders.slice(0, 10),
  }
})
```

`pageOverflows > 0` means the page scrolls sideways. The offender list names
the element that did it — usually a long unbroken string or a px-pinned box
inside a rem-sized layout.

## Overlap probe

For "is this thing covered by that thing".

```ts
async function isReallyOnTop(page, target: string) {
  return page.evaluate((sel) => {
    const el = document.querySelector<HTMLElement>(sel)
    if (!el) return { found: false }
    const r = el.getBoundingClientRect()
    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
    return {
      found: true,
      onTop: hit === el || el.contains(hit),
      covering: hit
        ? { tag: hit.tagName.toLowerCase(), cls: (hit.getAttribute("class") ?? "").slice(0, 80) }
        : null,
    }
  }, target)
}
```

Playwright gives you this for free on a real interaction: if a hover or click
fails with *"<div …> intercepts pointer events"*, the element it names **is**
the covering node. Do not treat that as a flaky test — it is the answer.

## Focus probe

For "why is there a black box on that row", and for keyboard sweeps.

```ts
const focus = await page.evaluate(() => {
  const el = document.activeElement as HTMLElement | null
  if (!el || el === document.body) return { on: "body" }
  const cs = getComputedStyle(el)
  return {
    tag: el.tagName.toLowerCase(),
    role: el.getAttribute("role"),
    text: (el.textContent ?? "").trim().slice(0, 50),
    // The distinction that matters: :focus matches a mouse click, :focus-visible
    // does not (on non-text elements). A ring that shows for a click is a
    // default UA outline that nobody styled.
    focusVisible: el.matches(":focus-visible"),
    outline: `${cs.outlineStyle} ${cs.outlineWidth} ${cs.outlineColor}`,
    boxShadow: cs.boxShadow,
  }
})
```

**Drive focus the way a user would, or the probe lies.** Measured in 1.59.1:

| How focus arrived | `:focus` | `:focus-visible` |
|---|---|---|
| `locator.click()` | true | **false** |
| `keyboard.press("Tab")` | true | true |
| `locator.focus()` / `el.focus()` | true | **true** |

So `locator.focus()` reports a focus ring on a page that has never seen a
keyboard — testing focus-ring suppression that way is a guaranteed false pass.
Only a real click discriminates. Use `click` for the mouse case and `Tab` for
the keyboard case, never `.focus()`.

To sweep tab order:

```ts
const order: string[] = []
for (let i = 0; i < 30; i++) {
  await page.keyboard.press("Tab")
  order.push(await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null
    const r = el?.getBoundingClientRect()
    return `${el?.tagName}:${(el?.textContent ?? "").trim().slice(0, 24)}@${Math.round(r?.y ?? -1)}`
  }))
}
```

Read the `y` values: they should mostly increase. A jump backwards is a tab
order that does not match the visual order.

## Holding a route open

The only reliable way to make a loading state observable.

```ts
let release!: () => void
const held = new Promise<void>((r) => { release = r })
await page.route("**/api/runs/*/events*", async (route) => {
  await held
  await route.continue()
})
// …assert the skeleton is up…
release()   // ALWAYS. An unresolved route hangs teardown on a pending request.
```

Forcing an error state is the same shape:

```ts
await page.route("**/api/whatever", (route) => route.fulfill({ status: 500, body: "{}" }))
await page.route("**/api/whatever", (route) => route.abort("failed"))       // network error
```

Route precedence is registration order and **the last matching handler wins**,
so a narrow override must be registered *after* the general mock.

## Asserting what the app sent

Pixels are half the story. `page.on("request")` fires before route
interception, so it sees everything:

```ts
function captureRequests(page, urlPart: string) {
  const seen: { method: string; url: string; body: string | null }[] = []
  page.on("request", (r) => {
    if (r.url().includes(urlPart)) seen.push({ method: r.method(), url: r.url(), body: r.postData() })
  })
  return seen
}
```

`expect(seen).toHaveLength(0)` is how you prove a destructive call did **not**
fire — an assertion the UI alone cannot make.

## Assertions worth knowing about

Beyond `toBeVisible` / `toHaveText`, these turn a vague "looks wrong" into a
specific failure:

- `toHaveCSS("background-color", "rgb(1, 2, 3)")` — a state's actual computed
  style, after `hover()`.
- `toBeFocused()` — focus landed where it should.
- `toBeInViewport()` — focused/selected item is actually on screen.
- `toHaveRole("button")` — the semantic contract, not the tag.
- `toHaveAccessibleName()` / `…Description()` / `…ErrorMessage()` — named for a
  screen reader.
- `toMatchAriaSnapshot(\`- button "One"\`)` — whole subtree shape, inline or
  from a file.
- `expect.poll(fn, { intervals: [50, 50, 100] })` — something that settles
  asynchronously.
- `expect(async () => {…}).toPass({ timeout })` — retry a click+navigate
  **pair** as one unit.

For a pseudo-element or an arbitrary property, drop to `evaluate`:

```ts
await el.evaluate((e) => getComputedStyle(e).outlineColor)
await page.evaluate(() => getComputedStyle(document.body, "::before").content)
```

`:active` needs the button held down — there is no other way to observe it:

```ts
await page.mouse.move(cx, cy)
await page.mouse.down()
const activeBg = await el.evaluate((e) => getComputedStyle(e).backgroundColor)
await page.mouse.up()
```

One more listener worth adding at context level: `context.on("weberror", …)`
catches errors from any page in the context, including ones you did not attach
to individually.

`locator.highlight()` draws Playwright's red inspector box on an element —
useful for annotating a screencast without writing overlay CSS.

## Take the first N elements and you will test the off-canvas menu

Hit three separate times on one app, each time costing a wasted run:

| Attempt | Selector |
|---|---|
| Hover paths | first 40 of 253 `[aria-haspopup=dialog]` |
| Combinatorial cell | first matching row |
| Tap on mobile | first 8 of 203 `[data-slot=tooltip-trigger]` |

What the first N actually were:

- **Hover paths** — 200 sidebar star buttons, 20x20; the feed rows started at
  index 200.
- **Combinatorial cell** — same.
- **Tap on mobile** — all zero-size: the off-canvas sidebar. Reported
  `tested: 0`.

A collapsed off-canvas menu is **still in the DOM**, still matches your
selector, and sorts FIRST because it is early in document order. On a phone
profile it can be 95% of your matches at zero size.

Never take `first N` from a broad selector. Filter to what is genuinely on
screen, then take N from that:

```ts
const usable: number[] = []
for (let i = 0; i < await loc.count() && usable.length < N; i++) {
  const b = await loc.nth(i).boundingBox()
  if (b && b.width >= 8 && b.height >= 8 && b.y >= 0 && b.y + b.height <= viewportH) usable.push(i)
}
```

If that filter leaves you with **zero** candidates, that is a result worth
printing — it means the thing you meant to test is not on this screen at all,
which is different from "it did not respond".

## Scroll containers invalidate naive geometry checks

Three separate invariants measured on one real app produced a false positive
each, all from the same omission — **not asking whether the element is inside a
scroll container, and whether it is on screen at all.**

| Naive check | Reported |
|---|---|
| "no zero-size interactive elements" | **408** at ≤640 px |
| "nothing is clipped by an ancestor" | **366** |
| "no target under 24 px" (WCAG 2.5.8) | **200** |

The truth behind each:

- **"no zero-size interactive elements"** — the collapsed off-canvas sidebar.
  A tab trail proved they are not in the tab order — 16 stops at 360 px, 28 at
  1440 px.
- **"nothing is clipped by an ancestor"** — sidebar rows scrolled below the
  fold of a legitimate `overflow: auto` list.
- **"no target under 24 px" (WCAG 2.5.8)** — counted off-screen targets and
  ignored the spacing exception. In-viewport truth: **19**, and **0** actually
  fail.

Each would have been filed as a bug. Three rules fix all three:

- **An overflow number is not a defect until you show the content is UNREACHABLE.**
  This is the rule both axes share, and it is worth stating once:
  `scrollHeight - clientHeight` (vertical) and `right > innerWidth`
  (horizontal) both measure *overflow*, and overflow is normal. Before filing,
  walk the ancestors for one that scrolls that axis with
  `scrollWidth > clientWidth`. Measured on one app at 390px: a raw sweep
  flagged **3** views as spilling (79 + 10 + 1 elements); reachability analysis
  said **one** did — the 79 were a data table inside a horizontal scroller,
  working exactly as intended. The same mistake in the vertical direction
  reported 2,566px of "lost" content in print mode where every element had
  `overflow: visible` and simply paginated.
- **Stop walking at the NEAREST ancestor that scrolls that axis.** This is the
  subtle half, and it produced a false positive even after per-axis checking was
  in place. A common layout is an inner `overflow-y: auto` scroller inside an
  outer `overflow-y: hidden` shell. An ancestor walk looking for `hidden` skips
  straight past the `auto` scroller and blames the outer shell, reporting every
  element below the scroller's fold as clipped. Measured: **144 "clipped"
  elements on one page at 200% text, worst 10,589px** — all of them reachable,
  confirmed by `scrollIntoView` bringing the last one to `inViewport: true`.
- **Only count a cut on an axis the ancestor does not scroll.** Check
  `overflow-y` for vertical cuts and `overflow-x` for horizontal ones, and
  count the cut only when that axis is `hidden` or `clip`. `auto`/`scroll`
  means the user reaches it by scrolling — that is not clipping.
- **Restrict geometry assertions to what is in the viewport**
  (`r.top >= 0 && r.bottom <= innerHeight`), or you are asserting about content
  that was never meant to be laid out yet.
- **Assert on tabbability, not on presence.** "Is it focusable" is answered by
  walking Tab and recording where focus lands, not by querying for
  `[tabindex]` and measuring rectangles. The tab trail is a few hundred
  milliseconds and it is the only honest answer.

And a rule about the standard itself: **WCAG 2.5.8 has a spacing exception**,
so a size check alone over-reports. The real test is whether a 24 px-diameter
circle centred on the target intersects another target's circle:

```ts
const cx = r.x + r.width / 2, cy = r.y + r.height / 2
const nearest = Math.min(...others.map((o) =>
  Math.hypot(cx - (o.r.x + o.r.width / 2), cy - (o.r.y + o.r.height / 2))))
const fails = nearest < 24
```
