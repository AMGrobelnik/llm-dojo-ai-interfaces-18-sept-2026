# Whole-app invariants

The highest-leverage checks in this whole skill. One assertion, written once,
covers every screen and every story — including the ones nobody thought to
test. They hold without knowing what the page is *supposed* to look like.

Two hooks carry all of them:

| Hook | Covers |
|---|---|
| A `preview.tsx` `beforeEach`/`afterEach` | Every Storybook story |
| One `page.addInitScript` observer bundle | Every e2e page |

The story hook rides the existing test run; the observer bundle is installed
before any app code.

---

## A. Every story — one `preview.tsx` hook

Turns a whole story corpus into assertions for things nobody wrote a test for.
On one repo measured that was 61 story files / 154 story tests, at zero marginal cost —
they already run in CI.

```tsx
const seen: string[] = []
const NOISE = [/Download the React DevTools/, /Runtime config is deprecated/]

const preview: Preview = {
  beforeEach: () => {
    seen.length = 0
    const orig = console.error
    console.error = (...a) => {
      seen.push(a.join(" "))
      orig(...a)
    }
    return () => {
      console.error = orig
    }
  },
  afterEach: async ({ canvasElement }) => {
    // React funnels render errors, key warnings and prop-type complaints here
    // and nothing fails on them today.
    expect(seen.filter((s) => !NOISE.some((r) => r.test(s)))).toEqual([])

    const ids = [...canvasElement.querySelectorAll("[id]")].map((e) => e.id)
    expect(new Set(ids).size, "duplicate DOM ids").toBe(ids.length)

    // The three strings that mean a formatter got undefined.
    expect(canvasElement.textContent).not.toMatch(/\bNaN\b|\bundefined\b|\[object Object\]/)
  },
  parameters: { a11y: { test: "error" } },
}
```

The console guard alone earns its place: a probe on one such corpus found
`Received NaN for the strokeDashoffset attribute` passing green today.

**Migrate the a11y gate per-story, not globally.** Set the global to `"error"`
and escape-hatch the known-bad stories with
`parameters: { a11y: { test: "todo" } }`. Weakening the global instead means
someone quietly reverts it and the gate never lands.

## B. Every e2e page — one observer bundle

`addInitScript` runs before any app code, on every navigation. Install once,
assert per spec.

```js
await page.addInitScript(() => {
  const w = globalThis
  w.__loaf = []; w.__ev = []; w.__ls = []; w.__mut = []
  const safe = (type, cb, opts) => {
    if (!PerformanceObserver.supportedEntryTypes.includes(type)) return
    new PerformanceObserver(cb).observe({ type, buffered: true, ...opts })
  }

  // Long Animation Frames: WHICH handler blocked the frame, not just that one did.
  safe("long-animation-frame", (l) => {
    for (const e of l.getEntries())
      w.__loaf.push({
        blocking: Math.round(e.blockingDuration),
        scripts: e.scripts.map((s) => ({
          invoker: s.invoker,                                  // "#document.oninput"
          url: s.sourceURL,
          dur: Math.round(s.duration),
          forcedLayout: Math.round(s.forcedStyleAndLayoutDuration),   // layout thrash
        })),
      })
  })

  // INP, split into the three phases so the fix is obvious.
  safe("event", (l) => {
    for (const e of l.getEntries())
      if (e.interactionId)
        w.__ev.push({
          dur: e.duration,
          inputDelay: Math.round(e.processingStart - e.startTime),
          processing: Math.round(e.processingEnd - e.processingStart),
        })
  }, { durationThreshold: 16 })

  // Layout shifts, ATTRIBUTED to the element that jumped.
  safe("layout-shift", (l) => {
    for (const e of l.getEntries())
      if (!e.hadRecentInput)
        w.__ls.push({
          value: e.value,
          at: Math.round(e.startTime),
          sources: [...e.sources].map((s) => ({
            node: s.node?.tagName,
            cls: s.node?.getAttribute?.("class")?.slice(0, 40),
            to: [s.currentRect.x, s.currentRect.y],
          })),
        })
  })

  // A→B→A oscillation, in the DOM. Catches a flicker reverted inside one
  // frame, which no screencast can ever see.
  //
  // Observe `document`, NOT `document.documentElement`: in an init script the
  // latter is still null, the throw kills the rest of your init script, and
  // every observer above it silently stops existing.
  new MutationObserver((rs) => {
    for (const r of rs)
      if (r.type === "attributes")
        w.__mut.push({
          node: r.target.tagName + (r.target.id ? "#" + r.target.id : ""),
          attr: r.attributeName,
          from: r.oldValue,
          to: r.target.getAttribute(r.attributeName),
          at: performance.now(),
        })
  }).observe(document, {
    subtree: true,
    attributes: true,
    attributeOldValue: true,
    // Radix writes data-state on every dialog/popover/tooltip; sonner rewrites
    // style per toast. Those two carry most of the real oscillation.
    attributeFilter: ["style", "class", "hidden", "data-state", "aria-expanded"],
  })
})
```

### The assertions

```ts
const perf = await page.evaluate(() => ({ loaf: __loaf, ev: __ev, ls: __ls, mut: __mut }))

// Worst blocked frame. The LoAF entry names the handler, so a failure is a diagnosis.
const worst = Math.max(0, ...perf.loaf.map((f) => f.blocking))
expect(worst, JSON.stringify(perf.loaf.filter((f) => f.blocking > 150), null, 1)).toBeLessThan(150)

// INP. 200 ms is the Core Web Vitals "good" threshold.
expect(Math.max(0, ...perf.ev.map((e) => e.dur))).toBeLessThan(200)

// Layout shift. Assert BOTH the score and "no unprompted shift after settle" —
// the second is stricter and more actionable, because a CLS budget happily
// ignores several 0.0000-value shifts that are still a visible jump.
expect(perf.ls.reduce((a, s) => a + s.value, 0)).toBeLessThan(0.1)
expect(perf.ls.filter((s) => s.at > 500)).toEqual([])
```

**Oscillation detector** — an attribute that changes and changes back:

```ts
const flips = new Map<string, {to: string, at: number}[]>()
for (const m of perf.mut) {
  const k = `${m.node}.${m.attr}`
  flips.set(k, [...(flips.get(k) ?? []), { to: m.to, at: m.at }])
}
const oscillating = [...flips].filter(([, vs]) =>
  vs.some((v, i) => i >= 2 && v.to === vs[i - 2].to && v.at - vs[i - 2].at < 400),
)
expect(oscillating, JSON.stringify(oscillating)).toEqual([])
```

`A → B → A` inside 400 ms is a flicker whether or not a human saw it.

## C. Every URL state

The cheapest structural coverage of a whole route surface. Enumerate the
addressable state instead of trying to click your way into it — and it is the
only technique here that exercises the **hydration** path, because loading a
state from a URL is not the same code path as clicking into it.

```ts
const views = ["overview", "details", "trace", "review"] as const
const nodes = [null, "task_gen", "iter_1", "mod_does_not_exist", "", "%E2%9C%93"]
const times = [0, -1, 7, 999999]

for (const view of views)
  for (const node of nodes)
    for (const t of times) {
      test(`deep-link ${view}?node=${node}&t=${t}`, async ({ page }) => {
        const notes = observe(page)
        await mockRuns(page, [FIXTURE])
        const q = new URLSearchParams({ t: String(t) })
        if (node !== null) q.set("node", String(node))
        await page.goto(`/runs/${RUN_ID}/${view}?${q}`)
        await expect(page.getByRole("main")).toBeVisible()
        expect(notes).toEqual([])
        // Round-trip: back/forward must restore the same state.
        await page.goBack()
        await page.goForward()
        expect(new URL(page.url()).search).toBe(`?${q}`)
      })
    }
```

Add one `toMatchAriaSnapshot` per view and the same loop also becomes a
structural contract — a button losing its accessible name fails it.

## D. Every derivation module

Three properties, the same three every time:

```ts
expect(derive([])).toEqual({})                       // total on empty, not a throw
expect(shapeOf(derive(events))).toBeClosedOverEnum() // output shape holds
expect(derive([...events, ...events])).toEqual(derive(events))   // replay-idempotent
```

Replay-idempotence is the one that matters for a polling app: the same
envelopes arrive again on the next tick, constantly.

## E. Per-element invariants

Run these across every page and every story. Each is cheap and each catches a
class rather than an instance.

- **Tabbable elements before `<main>`** — the cheapest high-yield a11y number
  there is, and almost nobody measures it. Count visible tabbables in DOM
  order and find the index of the first one inside `main`. Measured on one
  real app: **407** on every route, with no skip link anywhere — 60 Tab
  presses never reached the content. That is WCAG 2.4.1 (level A) and it is
  invisible to axe, which cannot know your nav is 200 rows long.
- **A skip link exists** — `a[href^="#"]` whose text matches
  /skip|main content/. Pairs with the entry above: if the count is large and
  this is absent, keyboard users have no way out of the nav.
- **No duplicate DOM `id`** — breaks `<label for>`, `aria-labelledby`, and any
  `#id` selector.
- **Nothing overflows the viewport horizontally** — the single most common
  responsive defect.
- **Every page has exactly one `h1`, and headings do not skip levels** — the
  other bypass mechanism. Measured on the same app: 4 of 8 routes had **zero
  headings of any level**, 2 more started at `h3` with no `h1`. With no skip
  link either, both standard ways to bypass repeated navigation were absent on
  exactly the routes that needed them.
- **No clipped text without an ellipsis affordance** —
  `scrollWidth > clientWidth` **and** `text-overflow !== "ellipsis"`.
- **Interactive targets meet WCAG 2.5.8** — **24×24 CSS px, not 44×44** — 44
  is 2.5.5 (AAA). And 2.5.8 has a *spacing exception*, so a bare size check
  over-reports badly: one real page had 19 in-viewport targets under 24 px and
  **zero** actual failures. Test the exception, not the size — see
  `diagnostics.md`.
- **No nested interactives (button inside a link)** — ambiguous activation,
  invalid HTML.
- **No element with a click handler but no role or accessible name** —
  invisible to keyboard and screen reader.
- **No focusable element outside the viewport and outside every scroll
  container** — a tab stop nobody can reach. The qualifier is load-bearing: an
  item scrolled below the fold of an `overflow: auto` list is off-viewport and
  perfectly reachable — the browser scrolls to it on focus. Without it this
  invariant fired 366 times on a healthy page.
- **Computed `color !== background-color`** — the cheap contrast smoke test;
  axe does the real one.
- **`body` pointer-events restored after every overlay closes** — Radix leaves
  the app inert if a close goes wrong.
- **No orphan portals after closing everything** —
  `[data-radix-popper-content-wrapper], [role=tooltip], [data-sonner-toast]`.
- **A component is not mounted twice** — desktop + mobile copies both in the
  DOM; `.first()` then resolves the hidden one.

Code for the overflow, overlap, clipped-text and focus probes is in
`diagnostics.md`.

## F. Memory, per interaction

The named version of "does closing this leak", with the culprit in the message:

```ts
await page.evaluate(() => {
  globalThis.__ref = new WeakRef(document.querySelector("[data-panel]"))
})
await closeThePanel()
await page.requestGC()                       // present in Playwright 1.59.1
expect(await page.evaluate(() => globalThis.__ref.deref() === undefined)).toBe(true)
```

For a slow leak, take CDP `Performance.getMetrics` before and after N loops and
assert listener count is **exactly** flat — measured noise floor on a
route-to-route loop here was 0 nodes / 0 listeners / +0.2 MB over 12 iterations,
which is tight enough to assert equality rather than a threshold.

Do **not** use `Memory.forciblyPurgeJavaScriptMemory` — it wedges the CDP
session and every later `send` times out.
