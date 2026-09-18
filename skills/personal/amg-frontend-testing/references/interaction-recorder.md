# The interaction recorder

A screenshot shows what an interaction *looked* like. This shows what it
**did** — in the DOM, in the event system, on the network, in the console —
as a short readable summary you can diff between two runs.

It is the difference between "the panel appeared" and "the trigger flipped
`data-state` to open, the popper wrapper repositioned seven times, two nodes
were added at `body`, and one poll fired".

Verified working; the sample output below is real.

---

## The shape

```ts
await installRecorder(page)          // once, before goto — it is an initScript
await record(page, "hover a row", async () => { await row.hover() })
```

`installRecorder` puts an observer and an `addEventListener` shim in place
before any app code runs. It must be `addInitScript`, not `evaluate` — and
note that **`addInitScript` does not run for `page.setContent()` on a page's
initial `about:blank`**; navigate somewhere first or the hook is silently
absent. `record` arms the buffers, runs the action, waits
briefly for consequences to land, disarms, and prints a tally.

**The tally is the product.** Raw streams are thousands of entries and nobody
reads them; grouped counts are six lines and tell you the mechanism.

```ts
async function installRecorder(page: Page) {
  await page.addInitScript(() => {
    const rec = ((globalThis as any).__rec = { mut: [], evt: [], on: false })

    // A short, stable-ish path. Four levels is enough to identify a node and
    // short enough to group on. data-slot / id when present, because those
    // survive a re-render where a class list does not.
    const path = (n: Node | null): string => {
      const parts: string[] = []
      let el = n instanceof Element ? n : n?.parentElement ?? null
      while (el && parts.length < 4) {
        const slot = el.getAttribute?.("data-slot")
        parts.unshift(el.tagName.toLowerCase() + (el.id ? `#${el.id}` : "") + (slot ? `[${slot}]` : ""))
        el = el.parentElement
      }
      return parts.join(">")
    }

    // NOTE the missing `to:`. A MutationRecord carries oldValue and NEVER the
    // new value, and reading getAttribute() inside the callback returns the
    // value at CALLBACK time — after every mutation in that task has applied.
    // See "the new-value trap" below; the chain is reconstructed at stop().
    new MutationObserver((rs) => {
      if (!rec.on) return
      for (const r of rs) {
        if (r.type === "attributes") {
          const chain = `${idOf(r.target)}|${r.attributeName}`
          rec.chains.set(chain, r.target)          // close it with one live read later
          rec.mut.push({ k: "attr", at: path(r.target), name: r.attributeName, from: r.oldValue, chain })
        } else {
          for (const n of r.addedNodes)
            // `fresh` distinguishes a NEW node from one that was moved.
            rec.mut.push({ k: "+", at: path(r.target), node: n.nodeName, id: idOf(n), fresh: !hadId(n) })
          for (const n of r.removedNodes)
            rec.mut.push({ k: "-", at: path(r.target), node: n.nodeName, id: idOf(n) })
        }
      }
    }).observe(document, {
      subtree: true, childList: true, attributes: true, attributeOldValue: true,
      // The filter IS the noise budget. Unfiltered, a React app buries you.
      attributeFilter: ["class", "style", "data-state", "aria-expanded", "hidden", "aria-hidden"],
    })

    // Which handlers ran, and whether anything cancelled the event.
    const origAdd = EventTarget.prototype.addEventListener
    EventTarget.prototype.addEventListener = function (type, fn, opts) {
      if (typeof fn === "function" && ["click", "pointerdown", "keydown"].includes(type)) {
        const wrapped = function (this: EventTarget, e: Event) {
          if (rec.on)
            rec.evt.push({ type: e.type, on: this instanceof Element ? path(this) : this.constructor?.name,
                           phase: e.eventPhase, defaultPrevented: e.defaultPrevented })
          return (fn as EventListener).call(this, e)
        }
        return origAdd.call(this, type, wrapped, opts)
      }
      return origAdd.call(this, type, fn, opts)
    }
  })
}
```

`record` adds the Playwright-side halves — `page.on("request")` and
`page.on("console")` attached only for the duration of the action — then tallies
everything by frequency and prints the top few of each bucket.

## What it looks like

Real output, hovering a row that opens a Radix popover:

```
=== hover a feed row (983ms) ===
mutations: 19  handlers: 0  requests: 2  console-errors: 0
  attr changes: [["html>body>div.style",7],
                 ["div>div>div>div[popover-trigger].class",2],
                 ["div>div>div>div[popover-trigger].aria-expanded",1],
                 ["div>div>div>div[popover-trigger].data-state",1],
                 ["html>body>div#radix-_r_10_[popover-content].style",1]]
  nodes added : [["html>body",5]]
  requests    : [["GET /api/runs/<id>/events",2]]
```

That is the component's whole mechanism in five lines: the trigger flipped
`data-state` and `aria-expanded`, the content mounted at `body` (portalled),
and the popper wrapper repositioned seven times while it settled.

And clicking a route tab:

```
=== click the Details tab (1184ms) ===
mutations: 35  handlers: 9  requests: 10  console-errors: 0
  nodes added : [["html>head",13], ["div>div>div>div",2], ["html>body",1]]
  handlers ran: [["pointerdown@HTMLDocument",3], ["click@html>body",2]]
  requests    : [["GET /_next/static/chunks/…details_page…js",2],
                 ["GET /runs/<id>/details",1], ["GET /api/runs/list",1]]
```

Thirteen nodes into `<head>` is the framework injecting the route's CSS and
chunks — visible here, invisible in any screenshot.

## The new-value trap

**A `MutationRecord` carries `oldValue` and never the new value.** The obvious
fix — reading `target.getAttribute(name)` inside the callback — is wrong for
every record but the last, because the callback runs *after* every mutation in
that task has already applied.

Verified: four `setAttribute("data-s", …)` calls in one task produced four
records with `oldValue` `null, b, c, d` — while the live read returned `"e"` in
**all four** callbacks. So the naive recorder reports `null → e` four times and
the intermediate states, which are the whole point of an interaction recorder,
vanish.

The correct reconstruction is free: **`record[i].oldValue` *is*
`record[i-1]`'s new value.** One live read at `stop()` closes each chain.

```ts
function timelines(dump) {
  const out = new Map()
  for (const r of dump.mut) {
    if (r.k !== "attr") continue
    if (!out.has(r.chain)) out.set(r.chain, { name: r.name, at: r.at, vals: [], writes: 0 })
    const c = out.get(r.chain)
    c.vals.push(r.from)
    c.writes++
  }
  for (const [k, c] of out) {
    c.vals.push(dump.finals[k])                                   // the one live read
    c.seq = c.vals.filter((v, i) => i === 0 || v !== c.vals[i - 1])
    c.transient = c.seq.length > 2 && c.seq[0] === c.seq.at(-1)   // changed and changed back
    c.noopWrites = c.writes - (c.seq.length - 1)                  // wrote, changed nothing
  }
  return out
}
```

Two derived signals fall straight out and are usually the finding:

- **`transient`** — the value ended where it started. That is a flicker, whether
  or not anything rendered.
- **`noopWrites`** — the app wrote a value that was already set. Cheap, but it
  is what a wasted render looks like from the DOM side.

Print the deduped sequence, not first-and-last: collapsing to `first → last`
destroys exactly the transient state you were hunting. Cap each value at ~44
characters or one per-keystroke chain prints a 1,500-character line.

## Patched or replaced?

Every position-based technique — aria snapshots, path-keyed DOM diffs,
screenshots — keys on **where** a node sits, so a React remount reads as "an
attribute changed". Only per-node identity tells them apart.

Verified: clicking a password-visibility toggle. A path-keyed DOM snapshot diff
reported `svg [class] lucide-eye → lucide-eye-off` — a patch. The identity
recorder reported `removed svg.lucide-eye` + `added svg.lucide-eye-off` under
the same parent: a genuine **remount**, because those are two different
component types occupying one slot. Different diagnosis, different fix.

Tag with a `Symbol`, not an attribute:

```ts
const ID = Symbol.for("rec.id")     // invisible to JSON, for-in, outerHTML, React
let seq = 0
const hadId = (n) => n[ID] !== undefined
const idOf = (n) =>
  n[ID] ?? (Object.defineProperty(n, ID, { value: "n" + ++seq, configurable: true }), n[ID])
```

**Never tag with `data-*`.** Every write would queue its own MutationRecord —
a feedback loop — and it would pollute DOM snapshots, aria diffs and CSS
attribute selectors.

Walk the tree once at `arm()` and tag everything alive. Then anything untagged
at mutation time was **created during the interaction** — a birth certificate,
for free.

## Cost, measured

| Mode | 1,200 mutations |
|---|---|
| No observer | 0.4 ms |
| Observer, no-op callback | 0.6 ms |
| Full labelling callback | 32.3 ms (~26 µs/record) |
| Refs-only, format deferred to `stop()` | 3.7 ms (~2.6 µs/record) |

Use refs-only mode if you are measuring INP or LoAF in the same session — but
it holds **strong references to detached nodes**, so it invalidates any leak
check running alongside it. Pick one.

## What it cannot see, and why

**`handlers: 0` on hover is not a bug in the recorder.** Two real limits:

- **React delegates.** React 17+ attaches its listeners at the **root
  container**, not at each element, so patching `addEventListener` shows you
  `click@html>body` and `pointerdown@HTMLDocument` — the delegation root — and
  never the component's `onClick`. You learn that the event reached React, not
  which component handled it. For that, read the fiber (below) or set a
  breakpoint.
- **The shim only sees listeners registered after it installs**, and only the
  types you list. Anything attached by inline attributes or before the init
  script is invisible.

**For the listeners genuinely attached to a node**, use CDP instead — verified
working:

```ts
const cdp = await page.context().newCDPSession(page)
await cdp.send("DOM.enable"); await cdp.send("Runtime.enable")
const { result } = await cdp.send("Runtime.evaluate", { expression: `document.querySelector('a[href*="details"]')` })
const { listeners } = await cdp.send("DOMDebugger.getEventListeners", { objectId: result.objectId! })
// → [{ type: "click", useCapture: false, passive: false, once: false, scriptId, lineNumber }]
```

`scriptId:lineNumber` is the registration site — the closest thing to "who
attached this".

## The noise budget

Every stream has one dominant noise source. Filter it or the output is
unreadable.

Per stream — the dominant noise, then the filter for it:

- **Mutations / ambient animation.** Measured: one click produced 32 records,
  31 of them an unrelated typewriter effect. **Filter:** subtract a baseline
  captured over an equal idle window — this is the highest-payoff filter by
  far.
- **Mutations / framework bookkeeping** — a client route change wrote 5
  `<script>` and 3 `<meta>` into `<head>` plus no-op `img src` rewrites.
  **Filter:** drop `<head>` and dev-overlay roots.
- **Mutations / redundant descendants** — a node whose parent was also added
  in this window. **Filter:** report only top-level additions.
- **Mutations / every class toggle in a utility-CSS app.** **Filter:**
  `attributeFilter` to the state-bearing attributes: `data-state`,
  `aria-expanded`, `hidden`, `aria-hidden`, plus `class`/`style` only if you
  tally rather than list.
- **Mutations / positioning libraries rewriting `style` on a floating
  wrapper.** **Filter:** expected — read it as "it repositioned N times", not
  as N findings.
- **Requests / background polling that had nothing to do with the click.**
  **Filter: attribution by time window is wrong.** A poll that happened to
  land inside the window looks caused. Subtract a baseline captured over an
  equal idle window, or key on the initiator.
- **Console / framework dev-mode chatter.** **Filter:** an explicit allowlist
  of regexes, kept small.
- **Handlers / delegation roots firing for everything.** **Filter:** group by
  `type@root`; a count change between two runs is the signal, not the absolute
  number.

The attribution caveat is real and was visible in the first run: a 404 for an
un-mocked endpoint appeared under "move pointer away" purely because the poll
fired during that window.

## Deeper layers, when the tally is not enough

Reach for these in order; each costs more than the last.

**Fiber inspection** — what props/state the component that owns a node
actually has:

```ts
await el.evaluate((node) => {
  const key = Object.keys(node).find((k) => k.startsWith("__reactFiber$"))
  const fiber = (node as any)[key!]
  return { type: typeof fiber.type === "string" ? fiber.type : fiber.type?.name,
           props: Object.keys(fiber.memoizedProps ?? {}) }
})
```

Version-fragile by construction — the key name is a React internal. Fine for
diagnosis, never for an assertion.

**Store observation** — for a zustand/Redux/query cache, the honest route is
for the app to expose the store on `window` in dev. Anything else is reaching
into internals that change between minor versions.

**Computed-style diff** — snapshot a property set before and after, diff. This
catches "the style changed but nothing moved" and its inverse.

**`document.getAnimations()`** before and after — names, `playState` and
timings of everything currently animating. This is also what `settle()` waits
on.

**CDP `DOMSnapshot.captureSnapshot`** returns the whole tree *with computed
styles* in one call; diffing two of them is the heaviest and most complete
version of this idea. Use it when you are stuck, not by default.

## Using it

- **Record a baseline of an idle window first.** Anything that appears in both
  is background behaviour, not your action.
- **Compare two runs**, not one run against intuition. The recorder's real
  power is diffing "before the fix" against "after".
- **A count that changes when it should not is a finding** — 2,040 renders for
  5 keystrokes, a poll firing four times per click, a node added and removed
  in the same interaction.
- Keep it **out of assertions** except for counts you have deliberately
  baselined. It is a diagnostic instrument, and its output moves with framework
  versions.
