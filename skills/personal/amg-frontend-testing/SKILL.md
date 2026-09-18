---
name: amg-frontend-testing
description: "Drives a real browser against a frontend the way a human tester does — hover, click, tab, drag, resize, scroll, burst-capture a transition — to prove a fix or hunt UI bugs nobody has reported yet, with a selector ladder, console/network/pageerror observers, responsive and keyboard sweeps, and screenshot evidence. Use whenever the request is to test, try, QA, poke at, or click around a UI, whenever a visual or interaction defect is reported (flickers, sticks, overlaps, disappears, looks different), and whenever a change must be proven in the real app rather than in unit tests. Triggers: UI bug hunt, exploratory pass, hover or focus state, animation and transition capture, responsive sweep, layout overlap, Storybook catalogue, interaction that looks flaky. NOT for: plain scripted automation such as scraping, form filling, or broken-link checks — use playwright; NOT for standing a local server up and smoke-testing it in Python — use anthropic-webapp-testing."
---

# Frontend Testing

Browser-driving for two jobs, and they need different postures:

| Job | Posture |
|---|---|
| **Verify** a change or bug fix | Targeted spec, assert, delete |
| **Explore** unreported bugs | Catalogue sweep, shots, findings |

Both run through Playwright. Neither is done until you have looked at the
artifacts — a run that "passed" while you never opened a screenshot has told
you almost nothing.

## The disposition

The checklists in this skill are quirks somebody already found. The valuable
ones are the quirks nobody has found yet, so **the point is not to work a list
— it is to hunt.**

Three habits carry most of it:

- **Treat every "that's probably fine" as an unmeasured claim.** If you can say
  it without a number, you have not checked it.
- **Go to the seams.** A component in a state is usually correct; somebody
  looked at it. Defects collect between two states, between two elements,
  between two code paths for one outcome, and wherever a default was inherited
  rather than chosen.
- **Escalate a feeling into a finding.** "It looks weird" → walk the path and
  capture → produce a number → name the mechanism → minimise the repro. Stopping
  at "it looks weird" is how real bugs get filed as flake.
- **Look at one thing every way it can be looked at.** A screenshot, a burst of
  screenshots, the hit test, the geometry, the aria snapshot, the console and
  network ledgers, the DOM mutations, the framework's commit stream — each is
  blind to a failure class the others catch, and **when two channels disagree
  that disagreement is the finding**. `references/observation-channels.md`.
- **Never test an action as if it were a point.** `click()` collapses path,
  duration, speed, repetition, interruption and termination into one instant,
  and the bugs live in the dimensions it collapsed — scrubbing and dragging have
  a *trajectory*, hovering is a state you hold while doing something else, and
  every delay in the system is a threshold with three cases.
  `references/action-anatomy.md`.

`references/finding-nuances.md` is the generative half of this skill: the seam
taxonomy, seventeen questions that reliably produce candidates, the tells worth
chasing, and how to feed what you find back into the catalogue. **Read it
before an exploratory pass**, not after.

## Step 0 — decide which harness you are in

```
Does the repo already have @playwright/test wired up?
  (playwright.config.ts + tests/e2e/ or similar)
    │
    ├─ YES → USE IT. Write a temp spec inside its testDir and run it with the
    │        project's runner. You inherit its auth setup, its backend mocks,
    │        its baseURL, its timeouts. This is almost always the right answer
    │        in a real repo, and it is why standalone scripts are the fallback
    │        and not the default.
    │
    └─ NO  → standalone script mode. Write ONE .mjs to a scratch dir, run it
             with `node`. See references/playwright-notes.md § standalone.
```

Then, for the target app:

```
Is a dev server already running?
  ├─ Probe first:  node scripts/detect-servers.mjs
  ├─ Exactly one hit  → use it, and say which one you picked
  ├─ Several hits     → ask which; do not guess
  └─ None             → start one with scripts/with-server.mjs, or ask for a URL
```

Never hardcode a port. Never assume `3000`.

A repo harness usually has **no `webServer` block**, which means nothing starts
the app for you — and if its auth setup logs in for real, the **backend must be
up too, even for fully mocked specs**. Check that before concluding the app is
broken; the first thing that fails will be the setup project, not your spec.

## Step 1 — reconnaissance before action

Never write a selector from assumption. Navigate, let the app settle, then read
the *rendered* state and pick selectors out of it.

```
navigate → wait for a concrete render signal → dump the interactive inventory
        → choose selectors → act
```

"A concrete render signal" means `await expect(someRealElement).toBeVisible()`.
It does **not** mean `waitForLoadState("networkidle")` — see the traps below.

The inventory dump is in `references/diagnostics.md § inventory`. Run it once
per new page; paste its output into your reasoning, and pick from it.

## Step 2 — attach the observers BEFORE you navigate

Every run gets the full observer set, always, even a one-line check. This is
the difference between "it didn't work" and a diagnosis. Console alone is not
enough: an uncaught exception often produces no console message, and a 404 is
a *successful* HTTP exchange that never reaches `requestfailed`.

```ts
const notes: string[] = []
page.on("console", (m) => { if (m.type() === "error") notes.push(`console: ${m.text()}`) })
page.on("pageerror", (e) => notes.push(`pageerror: ${e.message}`))
page.on("requestfailed", (r) => notes.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`))
page.on("response", (r) => { if (r.status() >= 400) notes.push(`http ${r.status()}: ${r.url()}`) })
```

Register these before `page.goto`. Print `notes` at the end of every run, and
treat a non-empty `notes` as a finding even when the assertions passed.

Full harness, plus layout-overflow / overlap / focus tracking:
`references/diagnostics.md`.

## Step 3 — the work

**Verifying a fix?** Write the smallest spec that would have caught the bug.
Then prove it is a real guard: **break the fix, watch the spec fail, restore
the fix.** A regression test you never saw fail is a test you have not written.

**Covering systematically?** When the question is "have I tried every
combination / every URL / every branch", stop improvising and read
`references/systematic-coverage.md`. When the honest answer is that there are
more reachable combinations than anyone could ever try — a dozen overlays,
filters, viewports and data states that can each be active at once — that is its
own discipline: `references/combinatorial-state.md` covers deriving the axes
instead of hand-writing them, covering them at a size you can afford, asserting
something generic at every cell, and reducing a failure to the two or three
factors that actually caused it. When the question is "what happens under
conditions nobody designed for" — a bad connection, a corrupt client store, a
hostile paste, an out-of-order server — read `references/fuzzing-and-chaos.md`. And whatever else you do, install the
whole-app invariants from `references/whole-app-invariants.md` first — one
story hook and one observer bundle assert more, across more screens, than any
number of hand-written cases.

**Exploring?** Run the bounded loop in `references/exploratory-loop.md` and
work the checklist in `references/exploration-catalogue.md`. The loop covers
the process — guarding destructive endpoints, pinning nondeterminism, the
`settle`/`shot` helpers, ledgers, the findings taxonomy and the report format.
The catalogue is the *what*: pointer states and the transitions between them,
keyboard traversal, the data shapes that break layouts, the environment axes.
Do not improvise either from memory; the bugs live in the entries you would
have skipped.

Then go past it. The catalogue is finite and the quirks are not — work
`references/finding-nuances.md` on whatever the component actually is, and add
what you find back to the catalogue so the next pass starts further along.

For free-form poking where you do not yet know what you are looking for, drive
the browser **live via the MCP Playwright tools** (`browser_snapshot`,
`browser_click`, `browser_hover`, `browser_console_messages`,
`browser_network_requests`) rather than writing a spec — `browser_snapshot`
returns an accessibility tree with stable refs, which beats guessing selectors
off a screenshot. Switch to a spec file the moment you find something worth
re-running.

**Capturing a transition** (something flickers, animates, sticks, or "looks
different for a moment"): a single screenshot cannot show it. Take a burst, or
record. `references/transitions.md`.

**Diagnosing rather than observing.** When you can see that something is wrong
but not why, stop screenshotting and instrument the interaction — the DOM
mutations it caused, the handlers that ran, the requests it fired.
`references/interaction-recorder.md` wraps one action and returns that as a
six-line tally. Diffing that tally between a working and a broken run finds
causes that no image can.

That tells you what changed. When you also need to know **which component
decided** — or which ones re-rendered for nothing — read
`references/framework-state.md`. One click on a real app measured **22 React
commits**; that number, and the list of components that performed work in them,
is reachable without any browser extension.

## Rules

**Selector ladder.** In order; drop a rung only when the one above is
genuinely unavailable:

1. `getByRole(role, { name })` with an **exact** name
2. A purpose-built test contract already in the app — `data-status`,
   `data-slot`, `data-feed-row`, `data-testid`
3. `aria-label`, `name`, `type`
4. Visible text, scoped to a container

`getByRole` matches the **computed ARIA role, not the tag**: a
`<button role="tab">` is NOT `getByRole("button")`. A click wrapped in
`.catch(() => {})` swallows the resulting timeout whole, so the run reports
a clean pass while the tab was never opened and the component under test
never mounted. Two rules follow: resolve the role from the DOM before
trusting a selector, and never `.catch()` a click whose success your
conclusion depends on — assert the state it was supposed to produce
(`expect(onModelsTab).toBe(true)`) so a miss fails loudly instead of
silently reading as "the feature does nothing".

**Measure the ladder before you trust it.** "Prefer `data-testid`" is the
usual advice and it is wrong wherever the codebase does not actually use them —
one repo measured had exactly **one** `data-testid` in the whole app, so rung 2
was nearly empty and the advice would have pushed every selector down to text
matching. Check first:

```bash
grep -ro 'data-testid' --include=*.tsx . | wc -l
grep -roh 'data-[a-z-]*=' --include=*.tsx . | sort | uniq -c | sort -rn | head
```

Whatever that returns is your real rung 2. Role plus exact accessible name
usually wins anyway, because it asserts the accessibility contract while it
selects.

**When no stable handle exists, add a `data-*` attribute to the component.** A
purpose-built attribute is cheaper than a fragile selector and it documents the
contract. Do that rather than reaching for rung 4.

Never CSS classes, never DOM position (`.nth(1)`, `scrollers[1]`), never store
internals. Both have silently measured the wrong element in real suites — a
case-insensitive text match that collided with a user-supplied title, and an
index-based locator that measured a different scroll container once a sibling
rendered. Neither failed; both lied.

**Prove uniqueness before asserting on content.** `await expect(loc).toHaveCount(1)`,
or `filter({ visible: true })` — not a bare `.first()`.

**`force: true` is banned.** It disables exactly the actionability check that
catches an element hidden under an overlay. If an interaction needs `force`,
that **is** the finding. (The one legitimate exception is documented in
`references/transitions.md` — an element under an infinite CSS animation.)

**Waiting.** Wait on conditions, never on the clock. `expect(locator).toBeVisible()`,
`waitForURL`, `waitForResponse`, `expect.poll`, `expect(...).toPass()`. A bare
`waitForTimeout` is acceptable **only** as a deliberate dwell — "is it still
open 800 ms later" — and never as a synchronisation primitive; when you use one,
a comment must name the window being probed.

For "has the UI finished moving", use the `settle()` helper in
`references/exploratory-loop.md` — it awaits `document.getAnimations()` rather
than guessing a duration.

**Visible does not mean visible.** `toBeVisible()` passes on `opacity: 0` and
on an element translated off-screen. When the claim is "the user can see it",
add `toHaveCSS("opacity", "1")` and `toBeInViewport()`.

**There is no `unhover()`.** Hover-out is `page.mouse.move(0, 0)`. Every hover
assertion needs a matching hover-out assertion, or it proves half the state
machine.

**`mouse.move` teleports unless you pass `steps`.** The default is a single
`mousemove` at the destination, which skips every hover-intent, hover-region
and overlay bug on the way. Use `steps: 10–20` for any move meant to model a
hand — see `references/pointer-paths.md`.

**Headless by default.** Headed only when a human is watching the screen.
Headed launches need a display and hang over SSH, in CI, and in backgrounded
calls.

**Artifacts and temp files.** Specs, scripts, screenshots and traces go to the
scratch dir or the runner's own output dir. A temp spec written into the repo's
`testDir` is deleted **in the same turn**. Never leave `tmp-*.spec.ts` or a
stray `.png` behind, and never write into the skill directory.

**Assert, don't demo.** A script that never fails makes the whole harness
green forever. Every run ends in an assertion or a non-zero exit.

**Every `expect(filtered).toEqual([])` needs a non-vacuity floor.** An empty
collection satisfies it trivially, so a blank render — or a selector that
silently stopped matching — reads as a clean pass. Assert the *unfiltered* set
was non-empty first:

```ts
expect(controls.length, "no controls collected — the probe, not the app").toBeGreaterThan(5)
expect(nameless).toEqual([])
```

Measured on one project: **88 of 153 story tests (58%) passed against a
component rendering nothing at all**, and a guard added in that same session
had the identical hole until it was break-tested by pointing its selector at an
element that does not exist.

**Concurrent agents.** Other agents may hold the same checkout. Only remove
files you created, and check `git status` before assuming a failure is yours —
an unrelated failing test in an untracked file is someone else's work in
progress.

## Traps that have actually cost time here

Each entry names the trap, what it actually does, then what to do instead.

- **`waitForLoadState("networkidle")` on a polling app.** The network is never
  idle; the wait burns its entire timeout. Two of them once ate a 60 s budget
  before the code under test ran. **Do instead:** wait for a real element.
- **Default `screenshot({ caret: "hide" })`.** Injects
  `caret-color: transparent` into the live DOM; mid-hydration React logs an
  attribute mismatch — a console-cleanliness sweep manufactures its own
  failure. **Do instead:** `screenshot({ caret: "initial" })` in any run that
  inspects console.
- **Only listening to `requestfailed`.** HTTP 4xx never fires it. **Do
  instead:** also listen on `response` with `status >= 400`.
- **Hovering an element under an overlay.** Playwright retries for the full
  timeout, then fails with "intercepts pointer events" — which is itself the
  finding. **Do instead:** read the intercepting element's name out of the
  error; it names the covering node.
- **A component rendered twice (desktop + mobile copies).** `.first()` resolves
  the `display: none` copy and reports a visible control missing. **Do
  instead:** scope to the container that is actually mounted.
- **Fixed-date fixture timestamps.** Drift out of the app's trailing time
  window and flake on a clock that did not change. **Do instead:** anchor to
  `Date.now() - 60_000`.
- **Route handlers registered before a needed override.** The last matching
  `page.route()` wins; an override registered first never runs. **Do instead:**
  register the narrower handler after the general one.
- **`test.describe.serial` for a wide sweep.** The first failure skips every
  remaining case, hiding the rest of the map. **Do instead:** independent
  tests; one per axis.
- **A held-open route left unresolved.** Teardown hangs on the pending request.
  **Do instead:** resolve it before the test ends.
- **`browser.newContext()` when you want an ANONYMOUS context.** It inherits
  the project's `use.storageState`, so your "logged-out" context is fully
  authenticated. Measured: a share-route test rendered the whole authed
  dashboard — 480 controls, sidebar, every run title — which reads exactly like
  a serious access-control leak and was purely the harness. **Do instead:**
  `browser.newContext({ storageState: undefined })`. And **prove** it: dump
  `ctx.cookies()` and hit a known-protected endpoint expecting 401 BEFORE
  concluding anything from the rendered page.
- **A long `--timeout` with no `actionTimeout`.** Playwright's default action
  timeout is **0 — unbounded**; only the test timeout bounds it. One ambiguous
  locator then retries for the entire test budget with no output, which is
  indistinguishable from a hung app. Measured: a single `.click()` stalled a
  240 s test. **Do instead:** bound every action (`click({ timeout: 4000 })`)
  and catch the rejection into your ledger, so an unactionable control is a
  *finding* rather than a stall.
- **Racing a navigation against a timer to detect a hang.**
  `Promise.race([page.goto(...), timer])` returns while the navigation is still
  in flight; the next command starts a second one, the first aborts, and the
  page lands on `about:blank`. Every later assertion is then an artifact — seen
  as `goBack: net::ERR_ABORTED; maybe frame was detached?`. **Do instead:**
  give the action its own `{ timeout }` and catch the rejection. Never race a
  navigation.
- **`pkill -f` / `pgrep -f` where the pattern is in your own command line.** It
  matches the invoking shell too. `pkill` kills the script mid-run — the tell
  is exit code **144**, not 124/143. `pgrep -c` silently inflates the COUNT, so
  a leak check reads "2 processes" when the real answer is 0. Both happened
  repeatedly in one session even after the rule was written down. **Do
  instead:** resolve the pid first and exclude `$$`, match on something your
  own line does not contain, or assert on a side effect instead —
  `ss -ltnp | grep -c :PORT` cannot self-match.
- **`nohup cmd &` inside an already-backgrounded call.** The wrapper shell
  exits instantly, so the harness reports "completed, exit 0" while the real
  run is still going and its log is empty — you then read an empty log and
  conclude the run produced nothing. **Do instead:** background a **plain
  foreground command**, or leave it detached and watch the log with a monitor
  that greps for the runner's own result line.
- **A server probe whose timeout covers the body read.** A dev server that IS
  running is reported as absent, and you start a duplicate or call the app
  broken. Measured: a Next dev server compiling `/` on demand was missed at a
  700 ms budget, found at 1500 ms. **Do instead:** end the timeout when
  **headers** arrive — those prove it is alive — and give the body its own
  budget. Closed ports are refused in ~3 ms, so a generous timeout never costs
  anything.
- **`querySelector("main svg")` (or any FIRST match) in an icon-rich app.**
  Icons are SVGs too. Measured: a chart-interaction sweep took every coordinate
  and every ARIA reading from a ~16px icon and reported
  `tooltip 0/3, role=null, tabIndex=0` on 8 chart views. Uniform nulls across N
  independent views is the tell — a real defect rarely lands identically
  everywhere, a misaimed probe always does. **Do instead:** size-rank the
  candidates and take the largest, or assert the match's dimensions before
  measuring anything about it.
- **Measuring page content with `body.textContent`.** It includes `<script>`
  and `<style>` text. Measured: a page whose real visible content was **141
  characters** ("This run isn't shared") reported **32,679** — the rest was
  Next.js inline flight data. Any `chars > N` assertion passes on an
  effectively blank page, and any content diff is swamped. **Do instead:** walk
  the tree, skip `SCRIPT`/`STYLE`/`NOSCRIPT` and
  `display:none`/`visibility:hidden` subtrees, and measure what a person could
  actually read.
- **A test that mutates shared state, run in the foreground.** If the harness
  kills the command on a timeout, the `finally` that was going to restore the
  state may never run — and you have silently left the app changed. Measured: a
  share-then-unshare test survived only because cleanup happened to finish
  before the 2-minute kill. **Do instead:** background it, give it its own
  generous timeout, and **verify the restore from a separate later process**
  rather than trusting the in-test cleanup log.
- **Hovering a chart's plot AREA to test its tooltip.** ECharts' default
  `trigger` is `"item"`: the tooltip appears only over a rendered mark, so
  empty-plot hover showing nothing is CORRECT behaviour being filed as a bug.
  And some views configure no tooltip at all — check before concluding. **Do
  instead:** enumerate the series marks (`path`/`rect` with real area,
  excluding the plot-sized background) and hover their centres.

## References

Each entry is the file and when to reach for it.

- `references/finding-nuances.md` — how to find quirks nobody has listed: the
  seam taxonomy, the question generators, feeling→finding escalation.
- `references/observation-channels.md` — every channel you can point at one
  interaction, what each uniquely catches, and the measured cases where one
  lied.
- `references/action-anatomy.md` — decomposing any action into its hidden
  dimensions: trajectories, thresholds, compounds, chains.
- `references/exploratory-loop.md` — running an exploratory pass: the loop,
  `settle`/`shot`, ledgers, findings taxonomy, the report.
- `references/exploration-catalogue.md` — what to try; the checklist.
- `references/interaction-recorder.md` — what an interaction actually DID: DOM
  mutations, handlers, requests and console, tallied into a readable summary.
- `references/framework-state.md` — which component actually rendered, and
  which re-rendered for nothing: fibers, the commit stream, the verified render
  predicate.
- `references/diagnostics.md` — observer harness, inventory dump, overflow /
  overlap / focus probes, assertions worth knowing.
- `references/pointer-paths.md` — walking the pointer along a path with capture
  at each waypoint; clipping detection; whether an overlay can really be
  scrolled.
- `references/transitions.md` — capturing motion: screencast, bursts, trace
  CLI, clock, animation freeze.
- `references/playwright-notes.md` — verified API surface, repo-harness
  specifics, standalone mode, emulation traps.
- `references/whole-app-invariants.md` — the highest-leverage checks: one story
  hook and one observer bundle that assert across every screen.
- `references/fuzzing-and-chaos.md` — monkey testing, network/state/input/clock
  chaos, and the reproducibility kit that stops a random finding being
  dismissed as flake.
- `references/systematic-coverage.md` — enumerating what nobody thought of:
  pairwise matrices, URL-state enumeration, property-based tests, goldens,
  coverage-guided targeting.
- `references/combinatorial-state.md` — when the reachable state space is far
  larger than you can test: axis derivation, covering arrays that fit a CI
  budget, the generic per-cell oracle, fault localization, sequence coverage.
- `references/forms-and-input.md` — the five value-arrival channels and their
  measured event traces, validation state machines, files, clipboard, IME.
- `references/navigation-and-session.md` — tab visibility (never exercised by
  default), history discipline, Back restoration, multi-tab, bfcache, overlay
  residue.
- `references/accessibility.md` — what automation covers and what it does not;
  scanning after interactions, not once per page; the behaviour checks axe
  cannot do.
- `references/storybook-hygiene.md` — Storybook as a test surface: catalogue
  lint, the a11y gate that is already installed, coverage, story-writing rules.

## Scripts

Both are small enough to read, and you should read one before depending on it
for correctness. Run with `--help` first.

- `scripts/detect-servers.mjs` — concurrent probe for a running dev server
  across the usual ports, on both IPv4 and IPv6.
- `scripts/with-server.mjs` — start server(s), wait for real HTTP readiness,
  run a command, tear the whole process group down.
- `scripts/story-lint.mjs` — static hygiene lint over a Storybook catalogue:
  naming drift, missing `component`, duplicate titles, dead sort config,
  coverage ratio.
