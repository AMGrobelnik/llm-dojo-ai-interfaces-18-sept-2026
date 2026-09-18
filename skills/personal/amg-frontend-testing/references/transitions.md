# Capturing transitions

A single screenshot cannot show a flicker, a stuck animation, a panel that
appears in the wrong place before settling, or a state that exists for 200 ms.

Everything below was verified against the installed **Playwright 1.59.1**,
including the measured frame rates. Where a number appears, it was measured,
not assumed.

| Question | Tool |
|---|---|
| "How does it look *mid-change*?" | `page.screencast` (~52 fps) |
| "≤20 moments, and I want files" | Screenshot burst (~8–22 fps) |
| "Where exactly did it go wrong?" | Trace + `playwright trace` CLI |
| "Does it settle in the right place?" | Immediate + settled boxes |
| "Is it animating?" | Computed-style / `getAnimations()` poll |
| "Does it depend on a timer?" | `page.clock` |

---

## page.screencast — the right tool for motion

New public API in 1.59. Records at roughly **52 fps**, versus a hard ceiling
of 8–22 fps for looped screenshots. If the transition is shorter than about
half a second, a burst physically cannot capture it faithfully and this is the
only honest option.

```ts
await page.screencast.start({ path: "/tmp/run.webm", size: { width: 1280, height: 800 } })
// …drive the interaction…
await page.screencast.stop()
```

It can annotate itself, which makes the recording readable without editing:

```ts
await page.screencast.showActions({ duration: 1500, position: "bottom", fontSize: 16 })
await page.screencast.showChapter("hover row, then move onto the panel")
await page.screencast.showOverlay("<b>expecting the panel to survive</b>", { duration: 1200 })
```

`showActions` draws the action title and highlights the element being
interacted with, on every subsequent action.

Two traps, both verified:

- **`start({ annotate })` type-checks but is silently inert.** The option is
  declared in `types.d.ts`, but the client only forwards `{size, quality,
  sendFrames, record}`. Use `showActions` / `showChapter` instead.
- **There is no `screencast.on('screencastFrame')`**, despite the doc comment
  showing one. The runtime prototype is exactly `start, stop, showActions,
  hideActions, showOverlay, showChapter, showOverlays, hideOverlays`. For
  per-frame access pass `start({ onFrame })`.

Also: sizes are floored to even numbers, and omitting `size` derives one by
scaling the viewport to a max dimension of 800 — so the recording silently
differs in resolution from the viewport unless you pass `size`.

The test runner can do the same declaratively:

```ts
video: { mode: "on", size: { width: 1280, height: 720 },
         show: { actions: { duration: 1500, position: "bottom" }, test: { level: "step" } } }
```

## Screenshot burst

Still the right call when you want a handful of **discrete, inspectable files**
rather than a video — one per moment you can point at.

Measured cadence at 1280×800:

| Call | ms/shot |
|---|---|
| `page.screenshot()` full page | 65 |
| `page.screenshot({ clip })` | 54 |
| `page.screenshot({ type: "jpeg", quality: 50 })` | 45 |
| `locator.screenshot()` | 133 |

So ~8–22 fps, jittering 28–93 ms in one run. Name frames by **measured**
elapsed time, never by intended interval — the interval is a lie.

```ts
async function burst(page, action: () => Promise<void>, { frames = 12, dir = "/tmp/burst" } = {}) {
  const t0 = Date.now()
  const running = action()                  // do not await: capture alongside it
  const shots: string[] = []
  for (let i = 0; i < frames; i++) {
    const path = `${dir}/f${String(i).padStart(2, "0")}-${Date.now() - t0}ms.png`
    await page.screenshot({ path, caret: "initial", clip: undefined })
    shots.push(path)
  }
  await running
  return shots
}
```

Then **look at the frames**, in order, as images. The bug is usually visible in
one and gone by the next.

### The animations option, which differs by API

| API | `animations` default | `scale` default |
|---|---|---|
| `page.screenshot` / `locator.screenshot` | `"allow"` | `"device"` |
| `expect(...).toHaveScreenshot` | `"disabled"` | `"css"` |

`"disabled"` **fast-forwards finite animations to completion** — measured, an
element mid-transition captured with `"disabled"` showed its final
`matrix(1,0,0,1,300,0)`, not the middle — and cancels infinite ones. So it is
correct for a stable diff and actively wrong for transition capture. The
defaults are already right for each API; the mistake is overriding them.

### The infinite-animation hang

`locator.screenshot()` with default options **times out** on any element
running an infinite CSS animation — the actionability "stable" check never
passes. Reproduced deterministically at both 8 s and 30 s. `locator.click()`
and `locator.hover()` hit the same wall.

- For `click` / `hover`: `{ force: true }` skips the stability wait.
- For `locator.screenshot()` there is **no `force` option**. Escapes are
  `animations: "disabled"`, `page.screenshot({ clip: await locator.boundingBox() })`,
  or injecting `animation: none !important` first.

## Trace, and the trace CLI

The richest artifact, and in 1.59 it is genuinely agent-friendly — there is a
**headless CLI**, so you no longer need the GUI trace viewer.

```ts
await context.tracing.start({ screenshots: true, snapshots: true, sources: true })
// …drive…
await context.tracing.stop({ path: "/tmp/trace.zip" })
```

A 2.8 MB trace held 389 screencast frames — the trace *is* a frame-by-frame
record of the run.

```bash
npx playwright trace actions  /tmp/trace.zip      # list every action with ids
npx playwright trace action   <id>                # params, source file:line, and the
                                                  #   actionability call log — this is
                                                  #   how you learn WHY a hover failed
npx playwright trace snapshot <id> --name before  # replay that DOM, return an aria snapshot
npx playwright trace screenshot <id> -o out.png   # pull the visual state at that step
npx playwright trace console|errors|requests|attachments <id>
```

`npx playwright trace snapshot <id> -- eval "document.querySelector('.x').textContent"`
queries the recorded DOM. Use **CSS selectors** inside `eval`: `aria-ref`
handles are only live within the invocation that produced them, and reusing one
across CLI calls fails with *"Ref e4 not found in the current page snapshot"*.

`npx playwright trace install-skill` writes Playwright's own trace skill into
`.claude/skills/playwright-trace/`. Read or vendor that rather than
re-deriving the CLI.

In a repo harness, `trace: "retain-on-failure"` is usually already configured —
check `test-results/` before adding your own.

## Immediate vs settled

The cheapest useful pair. Catches "it appears in the wrong place, then jumps".

```ts
await row.hover()
const a = await panel.boundingBox()
await page.waitForTimeout(400)        // deliberate dwell, not synchronisation
const b = await panel.boundingBox()
// Movement after the element is already visible is a layout-shift finding.
```

## Is it animating at all?

```ts
const samples = []
for (let i = 0; i < 10; i++) {
  samples.push(await el.evaluate((e) => {
    const cs = getComputedStyle(e)
    return {
      css: `${cs.opacity}|${cs.transform}|${cs.animationName}`,
      waapi: e.getAnimations().map((a) => `${(a as any).animationName ?? "?"}:${a.playState}`),
    }
  }))
  await page.waitForTimeout(50)
}
```

Ten identical samples where you expected motion means the animation never
started — a different bug from one that runs wrong. `getAnimations()` also
catches WAAPI-driven motion, which has no `animationName` in CSS.

## Freezing motion

For a stable diff:

```ts
await expect(page).toHaveScreenshot("overview.png", {
  mask: [page.locator("[data-live-timer]")],
  maskColor: "#00FF00",
  maxDiffPixels: 50,
})
```

`toHaveScreenshot` retries until two consecutive screenshots are identical
before comparing, which is what makes it safe on an animating page. On failure
it writes `-actual.png`, `-expected.png`, `-diff.png` **and an
`error-context.md` containing the call log and the page's aria snapshot** —
read that file first when triaging. Baselines: `--update-snapshots
[all|changed|missing|none]` (bare `-u` means `changed`).

Only introduce it where a stable baseline is maintainable. In a live-data app
most of the screen is volatile and you will spend longer masking than testing;
prefer behavioural assertions.

The blunt instrument, when the API-level option is unavailable:

```ts
await page.addStyleTag({
  content: "*,*::before,*::after{animation:none!important;transition:none!important}",
})
```

And the one that also tells you something:

```ts
await page.emulateMedia({ reducedMotion: "reduce" })
```

If motion looks identical under `reduce`, the app is ignoring the preference —
an accessibility finding, not just a test setting.

## Timer-driven states

```ts
await page.clock.install()
await page.clock.fastForward(5_000)                       // jump an auto-dismiss
await page.clock.pauseAt(new Date("2026-01-01T12:00:00Z"))  // pin a live clock
await page.clock.runFor(200)                              // advance in slices
await page.clock.resume()
```

Three verified caveats:

- **It is context-scoped, not page-scoped**, despite hanging off `page`.
  Installing on one page changed `new Date()` for sibling pages in the same
  context, created both before and after. `context.clock` is the honest name.
- **It does not stop CSS animations or transitions.** `pauseAt` freezes
  `requestAnimationFrame` (measured 0 ticks) but a `animation: spin 1s infinite`
  element kept rotating straight through the pause. It is a *timer* control,
  not an animation freeze.
- **An exception thrown from a clock-driven timer does not fire `pageerror`.**
  It surfaces only as a `console` error with a `ClockController._callFirstTimer`
  stack, so an error-capture assertion can pass while the app is throwing.

## Pointer control at the frame level

`locator.hover()` teleports. So does `page.mouse.move()` — **`steps` defaults
to 1**, a single `mousemove` at the destination. Real pointer travel, which is
what exposes hover-region, hover-intent and overlay bugs, needs steps:

```ts
const box = await panel.boundingBox()
await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 20 })
```

Verified: `steps: 25` emits 25 interpolated `mousemove` events. Use 10–20 for
any move meant to model a hand.

There is **no way to read the current mouse position** — no `page.mouse.position`.
Track coordinates yourself for any relative-move logic.

Related pointer tools, all present: `mouse.wheel(dx, dy)`, `mouse.dblclick`,
`mouse.down/up({ button: "right"|"middle", clickCount })`, `touchscreen.tap`,
`locator.click({ modifiers: ["Shift"], position, delay, clickCount })`,
`locator.hover({ position, trial: true, force: true })` — `trial: true` asks
"could I hover this?" without firing the event.

Drag has three forms; use the manual one when the app needs intermediate moves:

```ts
await source.dragTo(target, { sourcePosition, targetPosition })
await page.dragAndDrop(srcSel, tgtSel)
await page.mouse.move(x1, y1); await page.mouse.down()
await page.mouse.move(x2, y2, { steps: 20 }); await page.mouse.up()
```

## Detecting a flicker automatically

"Look at the frames in order" does not scale and misses a one-frame flash.
The signature of a flicker is arithmetic: frame *i* differs from *i-1* and from
*i+1*, but *i-1* and *i+1* are nearly identical — the change was reverted, so
the net movement across the pair is ~0.

```ts
// Playwright vendors pixelmatch. Do not install a diff library.
// The absolute path is required: the package `exports` map blocks the subpath.
const { getComparator } = require(
  "<abs>/node_modules/playwright-core/lib/server/utils/comparators.js",
)
const cmp = getComparator("image/png")

const frames = shots.map((p) => readFileSync(p))
for (let i = 1; i < frames.length - 1; i++) {
  const back = cmp(frames[i], frames[i - 1])
  const fwd = cmp(frames[i], frames[i + 1])
  const net = cmp(frames[i - 1], frames[i + 1])
  // changed and changed back
  if (back && fwd && !net) console.log(`FLICKER at frame ${i}`)
}
```

Measured ~30 ms per 400x120 comparison, so a 40-frame burst diffs in about a
second.

Playwright also ships its own **ffmpeg** (at
`~/.cache/ms-playwright/ffmpeg-*/ffmpeg-linux`), which is how you get frames
out of a `screencast` recording without a system install. It is built
`--disable-everything` — only pad/crop/scale filters exist — so extract frames
with it and do the diffing in Node, not in a filtergraph.

The DOM-level equivalent catches what no frame capture can: an attribute that
changes and changes back **within a single frame** is invisible to a camera and
obvious to a `MutationObserver`. See `whole-app-invariants.md § B`.

## Structuring an exploratory run

So the artifacts are readable afterwards rather than a pile of PNG files:

```ts
await test.step("hover row, move onto panel", async () => {
  await row.hover()
  await testInfo.attach("after-hover", { body: await page.screenshot(), contentType: "image/png" })
  await testInfo.attach("aria", { body: await page.ariaSnapshot(), contentType: "text/plain" })
})
```

Every step and attachment lands in the HTML report.
