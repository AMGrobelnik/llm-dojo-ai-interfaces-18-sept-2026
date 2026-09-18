# Systematic coverage

Example-based tests check the states someone thought of. These techniques
enumerate the ones nobody did — combinations, sequences, and the branches no
test has ever entered.

> **If the state space is genuinely too large to enumerate** — a dozen
> overlays, filters, viewports and data states all active at once — the
> pairwise sketch below is only the opening move. The full method (deriving
> axes instead of writing them, variable-strength covering, the generic
> per-cell oracle, fault localization, sequence coverage) is in
> `combinatorial-state.md`.

Ordered by bugs-caught ÷ (effort + maintenance).

---

## 1. Pairwise the configuration matrix

"Different configurations of things opened / clicked" is a combinatorial
problem, and the full cross-product is the wrong answer — it is huge and most
of it is redundant. **Almost all combination defects involve only two or three
factors interacting**, so a covering array over pairs finds them at a fraction
of the cost.

Measured on a 5 × 3 × 5 × 2 matrix: **25 cases cover all 81 pairs**, versus
150 for the full cross.

```ts
// tests/e2e/helpers/matrix.ts
import { pict } from "pict-node"

export const overlayMatrix = await pict({
  model: [
    { key: "overlay",  values: ["none", "settings", "share", "deleteConfirm", "tooltip"] },
    { key: "viewport", values: ["390x844", "768x1024", "1440x900"] },
    { key: "data",     values: ["empty", "one", "many", "error", "loading"] },
    { key: "theme",    values: ["light", "dark"] },
  ],
})
// order: 3 when a bug genuinely needs three things at once → 75 cases.
```

Then one generic spec loops the cases and asserts the whole-app invariants at
each: body pointer-events restored, the overlay in-viewport, no sideways
scroll.

Two rules that make it work rather than look like it works:

- **Exclude impossible combinations with a `constraint`, not with a filter.**
  Filtering afterwards silently destroys pair coverage — the pairs that were
  only present in the removed rows are now untested and the tool still reports
  success.
- **Scope it as a test file, not a Playwright project.** With
  `workers: 1, fullyParallel: false`, adding a project axis multiplies the
  whole suite's wall clock: 6 projects × 38 spec files ≈ 16 minutes serial.
  Gate any sweep project with `testMatch: /matrix\..*\.spec\.ts/`.

`pict-node` (`bun add -d pict-node`) supports constraints and real *t*>2.
`covertable` is actively maintained but its `length: 3` did not produce a true
3-wise covering array when checked (86 of 185 triples), so do not use it above
pairs.

## 2. Enumerate the URL state space

If the app puts its state in the URL, the state space is directly
**addressable** — no path exploration required. Cross the view with a handful
of hostile parameter values and load each one cold.

This is the highest value-per-effort item on this list, for three reasons: it
needs no new dependency, it turns a path-explosion problem into a few dozen
`goto`s, and it is the only technique here that exercises the **hydration**
path — clicking into a state and loading it from a URL are different code.

Hostile values worth including: a null/absent param, a valid one, an id that
does not exist, an empty string, a percent-encoded unicode string, a negative
number, and a number past the end of the data. Then `goBack()` / `goForward()`
and assert the search string round-trips.

Full loop in `whole-app-invariants.md § C`.

## 3. Property-based tests over pure derivations

For every function that turns an event stream into state. Generators produce
the inputs no fixture author would write: out-of-order timestamps, duplicate
starts, an end before its start, empty arrays, 10k elements, zero-length names.

```ts
import fc from "fast-check"
import { test } from "@fast-check/vitest"     // prints the SHRUNK counterexample

const envelope = fc.record({
  function_id: fc.integer({ min: 0, max: 5 }),
  ts_ms: fc.integer({ min: 0, max: 10_000 }),        // deliberately unordered
  message: fc.oneof(
    fc.record({ type: fc.constant("task_start"), node_id: fc.constantFrom("a", "b", "c") }),
    fc.record({ type: fc.constant("task_end"),   node_id: fc.constantFrom("a", "b", "c") }),
  ),
})

test.prop([fc.array(envelope, { maxLength: 80 })])("status derivation invariants", (evts) => {
  const s = derive(evts)
  expect(Object.values(s).every((v) => STATUSES.includes(v))).toBe(true)
  expect(derive([...evts, ...evts])).toEqual(s)     // replay-idempotent
  expect(derive([])).toEqual({})                    // total on empty
})
```

A hand-found "duplicate start event" test is one instance of a class this
enumerates.

**`fc.commands` / `fc.modelRun`** extends it to sequences — `pause → scrub →
play → scrub` landing on a different position than it should. The rule that
makes a model useful: the model must be a **plain simplified shadow**, never a
second copy of the implementation. If the model is as complex as the code, it
has the same bugs.

**`fc.scheduler()`** is the one that catches what nothing else can: async
interleaving. A stale poll landing after you switch runs and overwriting the
newer cache; an unmount between a fetch and its `setState`. For a UI that polls
continuously behind a query cache, that is the defect shape. Failures print a
replayable `{ seed, path }`.

`bun add -d fast-check @fast-check/vitest`. Run it in the **node** project —
the e2e mocks are `page.route()`, which gives no scheduling control.

## 4. Golden snapshots of computed state and structure

Two matchers, both usually already installed, both usually unused:

- **`toMatchFileSnapshot`** catches silent drift in a derivation — a
  projection quietly dropping a row type, a tree reordering siblings.
- **`toMatchAriaSnapshot`** catches structural drift — a button losing its
  accessible name, a heading level changing, an element leaving the a11y tree.

The corpus is free: every fixture the e2e mock harness already defines is a
serialized event stream. Dump them once to a fixtures directory and snapshot
what each derivation produces from them.

Golden snapshots are worth exactly as much as the review they get. A diff that
gets `-u`'d without reading is worse than no test, because it looks like
coverage.

## 5. Coverage-guided targeting

Not a bug class — a **blind-spot** class. It is the only technique that answers
"what have I never rendered?".

```bash
bun run test:coverage --coverage.reporter=json
```

Then rank the misses out of `coverage/coverage-final.json`: for each file,
branches where `d.b[id].some((x) => x === 0)`, mapped back through
`d.branchMap[id].loc.start.line`. Aim a story at the worst file, re-measure,
repeat.

Measured on one mid-size React app: **48.65% of branches never taken
(5,430 of 11,161)**,
with whole files at zero — `use-run-panels.ts` 164/164 unvisited,
`files-view.tsx` 123/123, `sidebar.tsx` 113/113. Those three are where the next
stories should go, and no amount of intuition would have named them.

Ratchet it with `coverage: { thresholds: { branches: N, autoUpdate: true } }`
so it can only go up.

**Pin which command produced the number.** Coverage denominators here are not
comparable: 48.65% is both vitest projects, 28.86% is the storybook project
alone, and neither includes the e2e specs at all. An unpinned ratchet gets
gamed by accident.

## 6. Wasted-render detection

Attach a shim to React DevTools' global hook before the app loads, and count
renders per component with a props-identity check.

A probe on one Radix-based app recorded **5 keystrokes → 2,040 `PopoverTrigger`
re-renders, 0 mounts**, and 1,060 `TooltipTrigger` renders of which 1,000 had
identical props.

Two caveats that must ship with the technique:

- **Strict mode and dev double-render inflate every count.** Assert against a
  captured baseline, or run against a production build — never an absolute
  number.
- **With the React compiler enabled, a same-props re-render means the compiler
  bailed out** on that component. That is high signal and worth chasing.

## 7. What not to do

- **Model-based path generation from a hand-written state machine.** The
  machine is a second artifact that drifts from the UI with no compiler to
  catch it, and path explosion is real — a six-state toy yields 11 shortest
  paths but 1,290 simple ones. URL enumeration reaches the same states with no
  second artifact to maintain. Revisit only when a transition-*order* defect
  actually bites.
- **Full cross-product matrices.** See §1.
- **A second visual-diff stack** (BackstopJS, jest-image-snapshot,
  odiff/pixelmatch as installs). Playwright already vendors pixelmatch, and the
  runner already has a screenshot matcher.
- **Raising a pixel comparator's `threshold` to fight flake.** It is a
  per-pixel colour-distance gate, not a noise budget — measured, at `0.5` the
  comparator cannot see black text turn red. Use `maxDiffPixelRatio`, and fix
  flake by shrinking the diff area (clip, locator-scope, mask) instead.
- **Perceptual/SSIM comparators as an anti-flake measure.** Measured, an
  SSIM-CIE94 comparator scored a 0.4 px subpixel shift as *more* different than
  a black→red colour change — the opposite of the premise. Treat both the
  vendor claims and the folklore as unsupported.
