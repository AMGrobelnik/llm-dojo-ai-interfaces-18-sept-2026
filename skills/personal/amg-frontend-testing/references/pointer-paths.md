# Pointer paths and the small nuances

`locator.hover()` teleports. Real users move along a **path**, and the bugs
live between the endpoints — the overlay that swallows the pointer halfway, the
panel that dies crossing a 2px gap, the row that highlights but is no longer
under the cursor.

This is how to walk a path, capture at each step, and check the nuances that
only show up mid-journey.

---

## Walk, don't jump

```ts
async function walk(page, label: string, pts: [number, number][], probe: () => Promise<unknown>) {
  const log: unknown[] = []
  for (const [i, [x, y]] of pts.entries()) {
    await page.mouse.move(x, y, { steps: 12 })     // steps, or you teleport
    await page.waitForTimeout(140)                 // deliberate dwell
    log.push({ i, at: [x | 0, y | 0], under: await whatIsAt(page, x, y), state: await probe() })
    await page.screenshot({ path: `${DIR}/${label}-${String(i).padStart(2, "0")}.png`, caret: "initial" })
  }
  console.log(`PATH[${label}]\n` + log.map((l) => JSON.stringify(l)).join("\n"))
}
```

`steps` is load-bearing: without it `mouse.move` dispatches **one**
`mousemove` at the destination, and every hover-intent, hover-region and
overlay bug is skipped over. 10–20 steps models a hand.

The captured log — position, what was under the cursor, the state you care
about — is more useful than the screenshots. **Read the log first, open the
frames only where it changed.**

### What is actually under the cursor

```ts
const whatIsAt = (page, x: number, y: number) =>
  page.evaluate(([px, py]) => {
    const el = document.elementFromPoint(px, py)
    if (!el) return { tag: null }
    return {
      tag: el.tagName.toLowerCase(),
      slot: el.closest("[data-slot]")?.getAttribute("data-slot") ?? null,
      text: (el.textContent ?? "").trim().slice(0, 28),
    }
  }, [x, y])
```

This is the check that catches "the row is highlighted but the pointer is
actually over the panel that opened on top of it".

### Paths worth walking

Each path, and what it catches:

- **Below the target → onto it → up into whatever opened** — the
  trigger-to-content gap; a panel that dies on the way in.
- **Straight down a list, one row pitch at a time** — stuck previous state;
  two panels open at once; a panel covering the next row.
- **Diagonal exit** — leave-handlers that only fire on a straight axis.
- **Out and back within the grace window** — re-entry that opens a second
  copy.
- **Along the edge of a trigger** — off-by-one hit areas.
- **Into the overlay, then out the far side** — close logic that only
  considers the trigger.

## Clipping

Whether an element is cut off, and by what:

```ts
const clipping = (page, sel: string) =>
  page.evaluate((s) => {
    const el = document.querySelector(s)!
    const r = el.getBoundingClientRect()
    const clippers: unknown[] = []
    let p = el.parentElement
    while (p) {
      const cs = getComputedStyle(p)
      if (/hidden|clip|auto|scroll/.test(cs.overflow + cs.overflowX + cs.overflowY)) {
        const pr = p.getBoundingClientRect()
        const cut = { top: Math.max(0, pr.top - r.top), bottom: Math.max(0, r.bottom - pr.bottom),
                      left: Math.max(0, pr.left - r.left), right: Math.max(0, r.right - pr.right) }
        if (cut.top + cut.bottom + cut.left + cut.right > 1)
          clippers.push({ by: p.tagName.toLowerCase(), cut })
      }
      p = p.parentElement
    }
    return {
      clippers,                                    // clipped by an ancestor
      offViewport: {                               // clipped by the window
        top: Math.max(0, -r.top), left: Math.max(0, -r.left),
        right: Math.max(0, r.right - innerWidth), bottom: Math.max(0, r.bottom - innerHeight),
      },
    }
  }, sel)
```

Two distinct failures with the same symptom: an **ancestor's `overflow`** cuts
it, or it hangs **off the viewport**. The fixes are different, so measure which.

Run it on every overlay at every viewport in the matrix — a floating panel that
fits at 1440 routinely hangs off at 390.

## Can you actually scroll that popup?

Four independent questions, and most tests answer only the first:

```ts
const m = await panel.evaluate((el) => {
  const cs = getComputedStyle(el)
  return {
    scrollable: el.scrollHeight > el.clientHeight,       // 1. is there overflow
    overflowY: cs.overflowY,                             // 2. is scrolling allowed
    gutterAfterBorders: el.offsetWidth - el.clientWidth  // 3. does the bar take space
      - parseFloat(cs.borderLeftWidth) - parseFloat(cs.borderRightWidth),
  }
})
// 4. does it MOVE
await page.mouse.move(cx, cy, { steps: 6 })
const before = await panel.evaluate((el) => el.scrollTop)
await page.mouse.wheel(0, 400)
const afterWheel = await panel.evaluate((el) => el.scrollTop)
await panel.evaluate((el) => { el.scrollTop = 0; (el as HTMLElement).focus() })
await page.keyboard.press("PageDown")
const afterKey = await panel.evaluate((el) => el.scrollTop)
```

`scrollHeight > clientHeight` only says content overflows. A panel can overflow
and still be unscrollable — `overflow: hidden`, a parent capturing the wheel, or
a close-on-pointerleave that kills it before the wheel lands.

### Scrollbar dragging is not testable in headless Chromium

Measured, and worth knowing before you write the assertion:

| Measurement | Result |
|---|---|
| `gutterAfterBorders` on the panel | **0** |
| Same on a `::-webkit-scrollbar { width: 4px }` element | **0** |
| `window.innerWidth - documentElement.clientWidth` | **0** |
| Drag 0.5/1.5/3/5/8/12/16 px from right edge | **none scrolled** |
| `--disable-features=OverlayScrollbar` | **no change** |
| Wheel | works |
| PageDown | works |

The document itself has a zero gutter, so **the whole environment is on overlay
scrollbars** — zero layout width, not hit-testable, `elementFromPoint` at the
bar returns the content beneath it. This is a property of the harness, not of
the app.

So:

- **Do not write a scrollbar-drag assertion in headless.** It will fail
  regardless of the app, and a test that "passes" it is measuring something
  else.
- **Assert the wheel and the keyboard paths instead.** Those are what actually
  break, and the keyboard path is the accessible one anyone should care about
  more.
- If scrollbar drag genuinely matters, it needs a **headed** run or a real
  browser channel — and check `gutterAfterBorders` first to know which
  scrollbar model you are in.
- A scroll container the keyboard cannot reach is a real finding at any
  scrollbar width: it needs `tabindex="0"` plus a role and a name.

## Rapid capture along a path

Screenshot cadence is 45–133 ms per frame (see `transitions.md`), so a
per-waypoint capture is honest and a "capture every 10 ms" loop is not. For
anything faster than the path itself, record with `page.screencast` and step
the video.

Name frames by **measured** elapsed time, and put the probe log next to them —
the log tells you which frame to open.

## The nuance checklist

- [ ] Pointer travels **into** the overlay without it dying (`steps: 12`).
- [ ] `elementFromPoint` at each waypoint is the element you think it is.
- [ ] The overlay is not clipped by an ancestor, at any viewport in the matrix.
- [ ] The overlay is not off-viewport, at any viewport in the matrix.
- [ ] Overflowing content scrolls by **wheel**.
- [ ] Overflowing content scrolls by **keyboard**, and the container is
      reachable by Tab.
- [ ] Scrolling the overlay does not scroll the page behind it.
- [ ] The overlay survives the whole scroll interaction.
- [ ] Moving diagonally out closes it exactly once.
- [ ] Out-and-back inside the grace window leaves exactly one overlay.
- [ ] Nothing is left behind: no orphan portal, body not inert.
