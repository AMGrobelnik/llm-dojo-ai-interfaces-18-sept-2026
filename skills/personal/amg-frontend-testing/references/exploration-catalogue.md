# Exploration catalogue

The list a human tester works through. Do not improvise it from memory — the
bugs live in the entries you would have skipped.

Work an axis at a time. After each entry, read the ledgers and look at the
before/after pair. An entry that produced no console noise and no unexpected
visual change is a pass; **write down that you checked it** — the report is a
matrix, and an unmentioned cell reads as untested.

Loop mechanics, helpers (`settle`, `shot`) and the reporting format:
`exploratory-loop.md`.

---

## 1. Pointer states, and the transitions between them

Static hover is the easy half. Almost every real bug is in a **transition**.

> **There is no `unhover()` in Playwright.** Hover-out is
> `await page.mouse.move(0, 0)` or hovering a neutral element. Every hover
> assertion needs a matching hover-out assertion, or it only proves half the
> state machine. (`userEvent.unhover` exists in Storybook/testing-library —
> different tool, do not confuse them.)

- [ ] Hover. Does something appear, where you expect, after the delay you expect?
- [ ] Leave **the way you came in**. Does it clean up?
- [ ] Leave in **each other direction** — up, down, left, right. Different
      directions cross different neighbours.
- [ ] Hover A → adjacent B. Does A clear before B appears? Do you end with one?
- [ ] **Rapid re-entry**: A → B → A with ~80 ms dwells, then assert
      `toHaveCount(1)`. Delay/skip-delay windows make two-open-at-once reachable.
- [ ] **Move the pointer into whatever appeared.** Radix renders portals at
      `document.body`, so travelling from trigger to content physically leaves
      the trigger. This is the single most common hover bug class. A popover
      must survive it; a tooltip has its own rule — know which you have.
- [ ] Inside the overlay: **wheel-scroll** it. Does it scroll, or does the page
      behind it? Then **PageDown** it — the keyboard path is the one that
      matters and the one usually missing.
- [ ] **Do not assert a scrollbar drag in headless** — scrollbars there have
      zero layout width and are not hit-testable, so the test measures the
      harness. `pointer-paths.md` has the measurements.
- [ ] **Select text** in it by dragging. Does straying outside kill it?
- [ ] Does it **cover** something you still need? Try to reach the element behind.
- [ ] Move over the overlay toward an element behind it. Does the overlay
      swallow the event? Playwright's *"intercepts pointer events"* failure
      **is** this finding — the error names the covering node.
- [ ] **Scroll the list while hovering, without moving the pointer.** No
      `mousemove` fires, so the hover target silently becomes wrong. Assert the
      overlay hid and the highlight left the old row.
- [ ] **The hovered element unmounts under a stationary pointer** (a live feed
      re-rendering). No orphaned overlay; hover styling re-applies to the new node.
- [ ] Pointer leaves the **window** entirely. Tab-switch and return.
- [ ] **Double-click a single-click control.** Exactly one request, one toast,
      one navigation.
- [ ] **Click during an in-flight request.** Delay the mutation 2 s, click
      twice: the control disabled itself, or the second call was deduped.
- [ ] **Right-click.** If there is a custom menu, Escape and outside-click both
      close it. If not, the native menu is not suppressed.
- [ ] **Middle-click and Cmd/Ctrl-click a link.** Must open a new tab
      (`context.waitForEvent("page")`) and leave `page.url()` unchanged —
      catches `<div onClick={router.push}>` posing as a link.
- [ ] **Drag with real intermediate moves.** `dragTo()` skips them; use
      `mouse.down()` → several `mouse.move(x, y, { steps: 10 })` → `mouse.up()`,
      asserting the live preview mid-drag.
- [ ] **Cancel a drag** — Escape mid-drag, then release. Zero mutation
      requests, no ghost node left behind.
- [ ] **Text-selection drag inside a clickable row.** Must select; must not
      fire the row's `onClick`.
- [ ] **Sticky hover after navigation.** Hover a link, click, land on the new
      route, move 1 px: the old hover styling must be gone.
- [ ] **Resize while an overlay is open.** It repositions or dismisses — never
      a floating element stranded off-screen.
- [ ] **Back/forward with an overlay open.** Overlay removed, body not inert.
- [ ] **Opening a panel must not scroll the page.** Capture `window.scrollY`
      before and after.

> Three real bugs from this section, in one component. Leaving a row restored
> focus to it, which re-fired its own `onFocus` and reopened its panel — so
> moving down the list left the old panel up *and* a focus ring stuck on the
> old row. The panel captured pointer events over the rows behind it, so the
> next row never opened. And it closed on the row's `pointerleave`, so the
> pointer dismissed it on the way in and its scrollbar was decorative.

## 2. Focus and keyboard

- [ ] Tab from the top. Is the order the visual order? Capture the transcript
      (`diagnostics.md § focus`) and read the `y` values — a jump backwards is
      a mismatch.
- [ ] Is every stop **visible** when focused, and in the viewport?
- [ ] Is the indicator the app's own ring, or the **browser default black box**?
      A default outline on a custom element is almost always an oversight.
- [ ] Click a custom control with the mouse. Does a ring appear that should
      not? `:focus-visible` must not match a mouse click on a non-text element;
      `:focus` does. **Drive it with a real `click()`** — `locator.focus()`
      reports `:focus-visible` true on a page that never saw a keyboard, so
      testing ring suppression that way is a guaranteed false pass.
- [ ] Anything focusable that does nothing? A tab stop that opens nothing is noise.
- [ ] **Enter and Space parity.** Everything clickable responds to Enter,
      buttons and checkboxes to Space, producing exactly one request. Catches
      non-semantic click handlers.
- [ ] Arrow keys in lists, menus, sliders, tab strips.
- [ ] **Focus restore after close.** Record the trigger, close with Escape,
      then poll `document.activeElement` — it must come back to the trigger.
      Untested focus restore is the most common a11y regression in Radix apps.
      (And a trigger whose `onFocus` reopens the thing turns restore into a loop.)
- [ ] **Focus trap integrity** in a modal: COUNT the dialog's focusables, then
      Tab (that count + 2) times — reduce the dialog to a small known set first if
      it lists many items, or a fixed budget will "pass" without ever reaching
      the end (measured: 14 Tabs in a 200-option modal never escaped, and the
      modal had no trap at all);
      `[role=dialog]` must still contain `document.activeElement` every time.
- [ ] **Escape ordering with stacked overlays.** Popover inside dialog: first
      Escape closes the popover only, second closes the dialog.
- [ ] **Outside-click must not click through.** Clicking outside a popover
      closes it *and* must not activate the control underneath — assert via the
      request ledger, not by eye.
- [ ] Tab *into* an overlay. Can you get back out?

## 3. Text input

Detail and measured event traces: `forms-and-input.md`.

- [ ] **The same value through all five arrival channels** — `fill`,
      `pressSequentially`, `keyboard.insertText`, Ctrl+V, and a native-setter
      write — must produce the same end state. They fire different events;
      `fill()` fires no key events and no `change` at all.
- [ ] **Autofill shapes**: silent / input-only / change-only / both. The submit
      button must end up correct for each.
- [ ] `:user-invalid` is false while pristine *and* after focus+blur, true
      after a submit attempt — and the app's own error UI agrees with it.
- [ ] The whole validation state machine: pristine → touched → dirty → fix →
      slow server error → edit-clears-it. Submit latch engages *and* releases.
- [ ] Reload after a mutating submit does not re-POST. `dblclick` and
      double-Enter produce exactly one request.
- [ ] The submitted **body** — not the toast — carries trimmed values, every
      field, and sanitized filenames.
- [ ] Errors are announced: `aria-invalid` set, an accessible error message
      wired, and both cleared on fix.
- [ ] Enter vs Shift+Enter in a composer. Ctrl+A then type. Ctrl+Z after a
      programmatic value set. Paste 50 KB.
- [ ] `input[type=number]` with junk, and an over-length value reached past
      `maxlength` via the native setter.
- [ ] IME: Enter mid-composition confirms the candidate and does **not** submit.

## 4. Data shapes that break layouts

Force each; do not wait to meet it.

- [ ] **Empty** — assert both `toHaveCount(0)` on rows *and* a visible
      empty-state node. A blank box is not an empty state.
- [ ] **Exactly one**, and **exactly two** — separator, `.at(-1)` and
      pagination off-by-ones live here.
- [ ] **1000 rows** — render-time budget, and if it virtualises, prove it:
      `expect(domRowCount).toBeLessThan(200)`.
- [ ] **A 200-char unbroken string** in a title, label or tool input, then run
      the overflow detector. Highest-yield single data case there is.
- [ ] **A long word in a flex row lacking `min-width: 0`** — assert the
      sibling's width is still > 0 and its text is not crushed.
- [ ] **A 2 MB body** — truncation UI appears, expand works, page stays responsive.
- [ ] **Empty string vs null vs missing key** — three different renders.
- [ ] Whitespace-only / empty title → a fallback label, not a zero-height row.
- [ ] **All optional fields absent**, plus the global sweep:
      `await expect(page.getByText(/undefined|NaN|Invalid Date|\[object Object\]/)).toHaveCount(0)`
- [ ] **Unknown event type / wrong-typed field** → graceful render, not a crash.
      This is the mock-drift risk, made testable.
- [ ] Unicode: emoji with ZWJ, combining accents, CJK (no spaces → wrapping),
      RTL mixed with LTR. No mirroring leaks, no tofu.
- [ ] Injection-shaped payloads rendered as text — `<script>`,
      `<img onerror=…>`, backticks, raw JSON. Then
      `await expect(page.locator("img[onerror]")).toHaveCount(0)`.
- [ ] Numbers: 0, negative, 1e9, 0.000001, >100 % progress, 0 ms and 99 h durations.
- [ ] Time: future timestamp, one older than the app's trailing window,
      identical `ts_ms` across many events (sort stability).
- [ ] A duplicate id/key in a list — React silently drops or duplicates rows.
- [ ] Deep nesting, if there is a tree.

## 5. Network, time, and in-flight states

- [ ] **Enumerate the dependency graph before breaking anything.** Record live
      requests per route (`page.on("request")`, normalise ids out) to learn
      which endpoints each route actually consumes. You will otherwise test
      the one endpoint you already know about. Measured once: six distinct
      GETs across six routes, of which four had never been failure-tested,
      and the defect was in one of the four.
- [ ] **Loading** — hold a route open to make it observable.
- [ ] **Slow network** — 3 s delay on every `/api/**`: skeleton appears, no
      layout jump on resolve, no duplicate requests during the wait.
- [ ] **Failure, both shapes** — `fulfill({ status: 500 })` and
      `abort("failed")` hit different code paths. Then prove retry actually
      re-requests, using `page.route(url, handler, { times: 1 })` then success.
- [ ] **Malformed JSON** (`body: "{oops"`), **empty 200**, and **204** — three
      more distinct paths.
- [ ] **Ask three questions of every failure case**: is there a MESSAGE, is
      there a RETRY, did anything get LOGGED? Three noes is a finding. A
      truncated-JSON case that renders blank with zero console output is a
      silent failure, and silence is the part that makes it survive.
- [ ] **Count polls from the SETTLED point, not from page load.** A client
      that retries and a client that polls forever both show a rising request
      count early on. Wait until the query has settled (the error affordance
      appears), record the count THEN, and assert no growth over the next
      10-15 s. Measured once: a fix that stopped the poll loop still showed
      "one more request" when counted from 6 s — that was the retry tail, and
      reading it as a surviving loop would have condemned a correct fix.
      A stop-on-error predicate that reads `state.data` is the usual culprit:
      an error leaves `data` undefined, which reads as "no answer yet".
- [ ] **Let the retries finish before you conclude "no error affordance".**
      TanStack retries several times with backoff before it reports an error,
      so a probe 8 s after load samples a query that is still RETRYING and
      reads exactly like a page with no error handling. Poll for the settled
      state (`waitForFunction` on the message) rather than sampling once.
      Measured twice on the same fix: 3 requests and no message mid-retry,
      4 requests and the message present once settled.
- [ ] **Hold the failure under observation for 15 s**, sampling more than once.
      "Still loading" and "permanently stuck" are identical at 3 s. Measured
      once: 70 skeleton nodes, unchanged at 3 s, 8 s and 15 s — the same
      reading three times is what turned it from a guess into a finding.
- [ ] **Hunt the `?? []` fallback: a failed fetch that degrades to an empty
      collection renders IDENTICALLY to a genuinely empty one.** The page
      looks completely healthy — seeded, editable, no skeleton, no error
      boundary — while silently offering a fraction of its real options. You
      cannot see this without a working-endpoint control: capture the route
      with the endpoint UP, then again with it 500ing, and diff. Measured
      once: a mode selector showed five choices healthy and ONE broken, with
      no message, no retry and no `role="alert"`. Grep the consuming
      component for `isError` — if every sibling query has an error branch
      and one does not, that one is the finding.
- [ ] **Use the empty 200 as your positive control.** If the designed empty
      state does not render, your route interception is not reaching the
      endpoint and every failure-case conclusion is worthless. Empty is a
      SUCCESSFUL response and takes a different path from failure — testing
      "no data" does not test "no answer".
- [ ] **401 mid-session** on a poll → re-auth prompt, not an infinite spinner.
- [ ] **429 with `Retry-After`** → assert backoff by counting requests over
      10 s, not a hot loop.
- [ ] **Offline** — `context.setOffline(true)` mid-session, then back. Recovery
      without a reload.
- [ ] **Navigate away mid-request** — no AbortError, no "setState on unmounted".
- [ ] **Destructive action mid-flight** — delay it 2 s, click Stop/Delete
      during it, assert idempotence and the right final state.
- [ ] **Out-of-order / duplicate events** — same id twice, a batch that goes
      backwards → dedupe, no duplicated rows.
- [ ] **Two tabs on the same record** — `context.newPage()`, mutate in one,
      the other converges on its next poll.
- [ ] **Corrupt persisted client state** —
      `addInitScript(() => localStorage.setItem(key, "{corrupt"))` → boots to
      defaults, does not white-screen.
- [ ] **Tab hidden, then visible again.** Note the trap: a Playwright page
      reports `visible` AND `hasFocus() === true` at once, and `bringToFront()`
      hides nothing — so pause-when-hidden, refetch-on-focus and idle logout are
      **never exercised** by default, and dispatching a bare `blur` event tests
      nothing. Emulate visibility properly first
      (`navigation-and-session.md § Tab visibility`), then assert polling stops
      while hidden and refetches on return without a duplicated mutation.
- [ ] **A component unmounting with a timer pending** — any `setTimeout` that
      outlives its component calls `setState` on a corpse.
- [ ] **Toast lifecycle** — appears, has `role="status"`, auto-dismisses,
      hovering pauses the timer, N stacked toasts do not overlap.

- [ ] **Dedupe triggers by component before counting coverage.** Taking the
      first N `[aria-haspopup]` elements on a page usually takes N copies of
      ONE list-row menu. Measured once: 6 triggers, 6 passes, all the same
      sidebar component — the share button, settings chip and attach-file
      overlays were never reached. Dedupe by class signature (or component
      identity) and the same page yields 3 DISTINCT triggers. A sweep that
      does not dedupe reports its sample size as coverage.
- [ ] **Focus restore is the half of keyboard testing a tab trail misses.**
      For each overlay: open by keyboard, does focus move IN; press Escape,
      does it come BACK to the opener. Non-modal popups (hover cards,
      tooltips) correctly do NOT take focus — for those, "focus restored" is
      trivially true and should be named, not counted as the same kind of
      pass.

## 6. Environment axes

One test per cell. Never a loop over cells inside one test — the first failure
would hide the rest of the map.

- [ ] **Widths**: 320, 360, 375, **767 / 768 / 769** (test *at* the
      breakpoint), 1024, 1280, 1920, 2560. Plus short-height (1280×400) and
      landscape phone.
- [ ] **No sideways scroll** at any width.
- [ ] **200 % text zoom**, distinct from a narrow viewport:
      `addInitScript(() => document.documentElement.style.fontSize = "32px")`.
      This is where px-pinned chrome and rem-sized text collide.
- [ ] **Touch** — `test.use({ ...devices["iPhone 13"] })`, then `tap()` not
      `click()`. Targets ≥ 44 CSS px. **Any control revealed only by `:hover`
      is unreachable** — it must also be reachable by focus or a visible tap
      target.
- [ ] **Keyboard-only** for a whole journey, from a cold load.
- [ ] **Reduced motion** — `test.use({ reducedMotion: "reduce" })`. Animations
      must actually shorten, *and* anything gated on
      `transitionend`/`animationend` must still complete. A skeleton waiting on
      a suppressed animation never resolves.
- [ ] **Dark mode** across the whole sweep, not one screen. Assert no element
      has computed `color === background-color`.
- [ ] **Forced colors** — `forcedColors: "active"`. Box-shadow focus rings
      vanish here, so assert `outlineStyle !== "none"` on focus, and that
      icon-only buttons stay distinguishable.
- [ ] **Resize across a breakpoint with a drawer/modal open.** Radix keeps
      `pointer-events: none` on `<body>` while it thinks a modal is open, so a
      CSS-only `md:hidden` leaves the whole app inert. Assert computed body
      pointer-events, not just panel visibility.
- [ ] **Slow CPU** — `Emulation.setCPUThrottlingRate: 4` via CDP. The highest-
      yield race amplifier available.
- [ ] **Locale / timezone** — `locale: "de-DE", timezoneId: "Asia/Tokyo"`:
      comma decimals, date order.
- [ ] **Print media** — `emulateMedia({ media: "print" })`, if there is a
      share or export path.
- [ ] **Non-Chromium** — webkit for layout (`100dvh`, flex `gap`, date inputs),
      firefox for focus and scroll behaviour. Note `isMobile` throws on Firefox.
- [ ] **Signed out**, if the route is reachable that way. Auth pages visited
      while signed in just redirect into the app and test nothing.
- [ ] **Long session** — hold a polling page open 5 min; DOM node, listener and
      portal counts stay bounded.

## 6b. Navigation, history and session

Detail: `navigation-and-session.md`.

- [ ] In-app navigation keeps the same document (`__docId` sentinel) — a stray
      `href` that reboots the SPA looks identical on screen.
- [ ] Transient UI pushes no history entry; a filter change replaces rather
      than pushes; Back leaves in one press, not twenty.
- [ ] Back from detail to list restores scroll — outer **and** inner containers.
      (`page.click()` scrolls its target into view first, so a careless test
      measures the harness.)
- [ ] After Back, what is displayed equals what gets submitted.
- [ ] `history.state` and the URL survive reload; a modal does **not**.
- [ ] Navigating with an overlay open leaves no scroll lock, no `inert`
      residue, no detached focus — then click something to prove it.
- [ ] The unsaved-changes guard fires on a dirty form, does **not** on a clean
      one, and stops after a save. (Without a `dialog` listener this test is a
      false green.)
- [ ] Log out in tab A → tab B reacts and stops calling the API. Assert both
      tabs: `storage` events never fire in the writing tab.
- [ ] N concurrent 401s trigger exactly one token refresh.
- [ ] Popups carry no `window.opener` — and actually opened.
- [ ] A superseded navigation: the last one wins, no stuck spinner.

## 6c. Files in and out

Detail: `forms-and-input.md`.

- [ ] Upload battery: wrong type against `accept`, zero bytes, unicode name,
      traversal-shaped name, 300-char name, 200 files, clearing the selection.
- [ ] The drag-drop path validates identically to the picker path — they are
      two code paths and usually only one has the checks.
- [ ] Copy writes the right payload and flavors; a **failed** copy does not
      show a success toast.
- [ ] Download is not zero bytes, has the right filename, and `failure()` is
      null.
- [ ] Pasting an image (no text flavor) previews, uploads, or explains — never
      silently no-ops.

## 7. What to look at afterwards

A screenshot is not a result until you have read it.

- [ ] **Overlap** — anything covering anything it should not.
- [ ] **Overflow** — the document, and any element past its container.
- [ ] **Clipped text** — `scrollWidth > clientWidth` *with*
      `text-overflow !== "ellipsis"` is text cut with no affordance.
- [ ] **Orphan portals** after closing everything.
- [ ] **Body left inert** after any overlay closes.
- [ ] Contrast in every state, including hover and active — styled last,
      checked never.
- [ ] The ledgers. **A clean assertion with a dirty console is a finding.**

## 8. How you fool yourself

Check these before believing a green run.

- **Screenshot before settle** — the capture shows the previous state. Never
  call `page.screenshot()` raw; go through `shot()`.
- **`toBeVisible()` passes on `opacity: 0`.** A mid-transition element is
  "visible" to Playwright. When the claim is "the user can see it", add
  `toHaveCSS("opacity", "1")`.
- **`toBeVisible()` passes off-screen.** An element translated outside the
  viewport still passes. Add `toBeInViewport()`.
- **`locator.all()` snapshots handles.** After any await that can re-render,
  every handle is detached. Use `count()` + `nth(i)` inside the loop instead.
- **`.first()` without proving uniqueness.** Require `toHaveCount(1)` first, or
  `filter({ visible: true })`. A case-insensitive text match once collided with
  a run title, and an index-based locator once measured a different scroller
  entirely — neither failed, both lied.
- **`force: true` is banned.** It disables exactly the actionability check that
  catches an overlay. If a click needs `force`, that **is** the finding.
- **The assertion cannot fail.** `expect(a === b || a !== b)` is a real example.
  Ask what input makes it red.
- **The test skipped itself.** `test.skip(true, "no data")` reports green.
- **You proved the mock, not the app.** Every interaction claim should assert
  one wire fact alongside the UI fact.
- **You did not prove the data arrived.** An empty state and a broken fetch
  look identical. Assert the request fired and returned 200, then judge the UI.
- **You tested a stale build.** Assert build identity once per run
  (`__NEXT_DATA__.buildId` or a health field), or a green run against a dev
  server that never recompiled looks like a pass.
- **A held-open route left unresolved** hangs teardown and reads as a timeout.
- **The regression test never failed.** Break the fix, watch it go red, restore.
  Mandatory for negative assertions (`toHaveCount(0)`, `not.toBeVisible()`) —
  those pass when the selector is merely wrong.
- **You reported one root cause six times.** Dedupe by cause; say where else it
  shows.
