# The anatomy of an action

`click()` is a lie of convenience. It collapses press-and-release into one
instant, at one point, with no path, no duration, no interruption and no
neighbours. Real interactions have all of those, and **the bugs live in the
dimensions the API collapsed.**

This page is not a list of actions to try. It is how to take *any* action and
work out what its hidden dimensions are, so you can generate the cases nobody
listed — including the ones this page does not mention.

---

## Every action has these dimensions

Take the action under test and fill this in. Each row that is not "n/a" is a
test you have not run.

| Dimension | The question |
|---|---|
| Path | Does it matter *how* you got there, or only the endpoint? |
| Duration | What if it takes 5 ms? 2 s? What if you hold? |
| Speed | Fast vs slow — does the app care? |
| Repetition | Twice fast. Ten times. While the first is in flight |
| Interruption | Quit halfway. Escape mid-drag. Navigate mid-request |
| Concurrency | Do it *while* something else is happening |
| Termination | Release outside the target, or on another element |
| Modality | Mouse, keyboard, touch, pen, screen reader, URL |
| Modifiers | Shift, Ctrl/Cmd, Alt, middle-click, right-click |

What hides in each:

- **Path** — overlays crossed on the way; hover-intent regions; a panel that
  dies over a 2 px gap
- **Duration** — long-press thresholds, tooltips, click-vs-hold branches,
  spinners that never clear
- **Speed** — momentum, hover intent, debounce, fling detection, "the user is
  still typing"
- **Repetition** — double-fire, double-submit, toggles that desync, request
  storms
- **Interruption** — stuck locks, orphan overlays, state that never rolls back
- **Concurrency** — poll landing mid-hover; animation vs data; two in-flight
  mutations
- **Termination** — drop handlers that assume you released where you started
- **Modality** — two code paths for one outcome, and only one of them tested
- **Modifiers** — range-select, open-in-new-tab, context menus nobody wrote

The last three are the most commonly skipped and among the most productive.

## Discrete actions are the easy case. Continuous ones are where it hurts.

A click has a value. A **scrub, drag, resize, wheel, slider, pinch, or pan has
a *trajectory*** — an ordered series of values over time — and asserting only
the endpoint tests almost none of it.

For every continuous action, the endpoint is one test and these are the rest:

- **Overshoot and come back.** End at the same value you would have set
  directly. Does the result match the direct set?
- **Reverse mid-gesture.** Go up, then down, without releasing.
- **Stop exactly at the boundary** — min, max, a snap point, a breakpoint —
  and one unit either side of it.
- **Release outside** the control, and outside the window.
- **Move fast vs slow between the same two points.** Any difference means a
  velocity-sensitive code path exists, and it is almost never tested.
- **Pause mid-gesture** for longer than any debounce in the system.
- **Start on the handle vs start on the track.**
- **Emit few large steps vs many small ones** between identical endpoints.

That last one is the one people get wrong in Playwright specifically:

```ts
// one mousemove at the destination — a teleport, not a gesture
await page.mouse.move(x, y)

// a hand: intermediate events actually dispatched
await page.mouse.move(x, y, { steps: 20 })
```

A scrub is `mouse.down()` → several `mouse.move(..., { steps })` → `mouse.up()`,
and **what the app does between down and up is the thing under test.** Sample
the value at every waypoint, not just at the end:

```ts
await page.mouse.move(x0, y0); await page.mouse.down()
const trace = []
for (const x of waypoints) {
  await page.mouse.move(x, y0, { steps: 8 })
  trace.push(await readValue())          // the trajectory IS the assertion
}
await page.mouse.up()
```

Then assert on the *shape* of `trace`: monotonic where it should be, no jumps
back to zero, no `NaN`, final value equal to the value you would get by setting
it directly.

## Micro-behaviours are thresholds, and thresholds have three tests

Any delay, distance or count in the system is a threshold, and every threshold
has the same three cases: **just under, just over, exactly at.**

| Micro-behaviour | Typical threshold |
|---|---|
| Hover intent | 100–300 ms dwell |
| Close grace window | 100–200 ms |
| Drag threshold | 3–8 px |
| Long-press | 400–600 ms |
| Double-click window | ~300 ms |
| Debounce / throttle | 150–500 ms |
| Snap radius | 8–20 px |
| Momentum / inertia | velocity-gated |
| Auto-scroll on drag-to-edge | edge band + rate |

The bug each one hides:

- **Hover intent** — opens on pass-through; never opens on a slow hand
- **Close grace window** — re-entry opens a second copy; panel unreachable
- **Drag threshold** — a click registers as a drag; a drag as a click
- **Long-press** — both branches fire; neither fires
- **Double-click window** — third click starts a new pair, or does not
- **Debounce / throttle** — request per keystroke; last keystroke lost
- **Snap radius** — cannot select the value next to a snap point
- **Momentum / inertia** — overshoots past the end and cannot come back
- **Auto-scroll on drag-to-edge** — runs away; never triggers

You often do not know the number. **Find it by bisection**, then test around
what you found — and if the app has no threshold where you expected one, that
absence is itself worth reporting.

`page.clock` makes the timing ones deterministic instead of flaky: pin the
clock, advance it in slices either side of the threshold, and assert what
exists at each slice.

## Compound actions: the pointer is not one thing

"Hover" is not an action, it is a *state you are holding while doing something
else*. The productive cases are almost all compounds:

- hover **and keep moving** inside the target — does anything re-fire per
  `mousemove`?
- hover, then **move onto whatever opened** — the classic trigger-to-content
  gap
- hover, then **scroll without moving the pointer** — what is under the cursor
  changed with no `mousemove`; does the app know?
- hover, then **Tab away** — mouse state and focus state now disagree
- **press and hold, then move** — drag vs click disambiguation
- **hold a modifier, then act** — a second code path
- **two overlays deep** — hover a trigger inside something already open
- hover, then let **data arrive underneath** — a poll changing the row beneath
  a stationary pointer

The general form: **take a state you can hold, and a thing you can do, and cross
them.** Most of the list above is that one operation applied to "hovering".

## Chains: state accumulates, and order is a dimension

A chain is not a longer test. It is a test of *accumulation*, and it fails
differently from any of its steps:

- **The same action N times.** The fifth should cost what the first did.
  Diverging commit counts, growing listener counts, or a ledger that grows are
  leaks.
- **A then B, versus B then A.** If both are supposed to be independent, the
  end states must match. When they do not, you have found an ordering bug and
  a *confluence* oracle to guard it.
- **Open, open, close, close** across two overlays — nesting, not just order.
  Refcounted things (scroll locks, focus traps, `inert`) fail here and nowhere
  else.
- **Interrupt step N with step N+1** before it settles.
- **Undo the chain** and assert you are back where you started. A round-trip
  that does not close is the strongest generic oracle available, because it
  needs no knowledge of what the correct state looks like.

For long chains, do not enumerate permutations — that space is factorial.
Cover *ordered pairs* instead: for n actions, running the sequence and its
exact reverse covers **every** ordered pair, in two tests. Verified: n=8 → 56
of 56 pairs, n=20 → 380 of 380. When adjacency matters rather than order, an
Eulerian walk over the complete digraph covers every ordered adjacent pair in
one run of length exactly n(n−1)+1 — verified at n=4, 8, 12 and 20.

## Generating your own

For anything you are about to test, in order:

1. **Name the action's continuous parameters.** If it has any, the endpoint is
   one test out of eight.
2. **Name every number in it** — delay, distance, count, rate. Each is a
   threshold with three cases.
3. **Name what you are holding while you do it** — a pointer, a key, a
   selection, an open overlay. Cross them.
4. **Name what could interrupt it** — a poll, an animation, a route change,
   another user action, a resize.
5. **Ask what "doing it again" means**, and do it five times.
6. **Ask what the inverse is**, and check the round-trip closes.

Anything that survives all six with no surprises is genuinely well-tested. In
practice something falls out at step 2 or step 4 almost every time.
