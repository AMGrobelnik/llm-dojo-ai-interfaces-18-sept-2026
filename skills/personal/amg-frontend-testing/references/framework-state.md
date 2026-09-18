# Framework state: which component actually did that

`interaction-recorder.md` tells you **what changed in the DOM**. This tells you
**which component decided to change it** — and, more usefully, which components
re-rendered for nothing.

Written against React 19 because that is what most apps under test are. The
general move transfers: every framework ships an instrumentation channel for
its own devtools, and you can register on it yourself instead of installing an
extension.

---

## The trap: the hook exists and is empty

The obvious first move is `window.__REACT_DEVTOOLS_GLOBAL_HOOK__`. On a Next
dev server it is **present** — `typeof` is `"object"` — so a naive
`if (hook) { ... }` guard passes. Measured on a real app:

| | |
|---|---|
| `typeof __REACT_DEVTOOLS_GLOBAL_HOOK__` | `"object"` |
| `hook.renderers.size` | **0** |

React only *uses* a hook that already exists; without the extension nothing
registers a renderer, so the hook is a shell. **Never gate on the hook's
existence.** Gate on `renderers.size > 0`, or install your own (below).

## Route A — DOM node to fiber, no setup at all

Every host DOM node React rendered carries two expando keys with a
per-page-load random suffix:

```ts
const fiberOf = (el: Element) => {
  const k = Object.keys(el).find((k) => k.startsWith("__reactFiber$"))
  return k ? (el as never)[k] : null
}
const propsOf = (el: Element) => {
  const k = Object.keys(el).find((k) => k.startsWith("__reactProps$"))
  return k ? (el as never)[k] : null
}
```

Measured present on a live app: `__reactFiber$ygao5s6…`, `__reactProps$ygao5s6…`
(same suffix on every node in one load, new suffix each load — **never hardcode
it**).

`propsOf` returns the props React actually passed to that host element — the
authoritative answer to "is `onClick` even attached", which you cannot get by
patching `addEventListener` because React delegates to the root container.

Walking `fiber.return` gives the owner chain. Measured on a real page, from a
button up:

```
button → div → div → CookiesBanner → div → SegmentViewNode → …
       → LoadingBoundary → ErrorBoundary → ScrollAndFocusHandler → …
```

Fibers with no nameable type come back as `tagN`; those are React internals and
you can skip them. Useful fields on a fiber: `memoizedProps`, `memoizedState`,
`stateNode`, `alternate`, `flags`, and — **dev builds only** — `_debugOwner`
and `_debugStack`.

This route needs no init script and works on a page that is already open, so it
is the right one for "what is this element, really".

## Route B — install your own hook and see every commit

To answer "what happened when I clicked", you need commits, not a snapshot.
Register a stub **before any app script runs**:

```ts
await page.addInitScript(() => {
  window.__commits = []
  const stub = {
    renderers: new Map(), supportsFiber: true, _id: 0,
    inject(r) { const id = ++this._id; this.renderers.set(id, r); return id },
    onCommitFiberRoot(_id, root) { window.__commits.push(summarise(root.current)) },
    // React calls all of these; missing ones throw inside React's own code.
    onCommitFiberUnmount() {}, onPostCommitFiberRoot() {}, checkDCE() {},
    on() {}, off() {}, sub() { return () => {} }, emit() {},
    getFiberRoots() { return new Set() }, getInternalModuleRanges() { return [] },
  }
  Object.defineProperty(window, "__REACT_DEVTOOLS_GLOBAL_HOOK__",
    { value: stub, configurable: false, writable: false })
})
```

`configurable: false` matters — the framework's own bootstrap will otherwise
overwrite it with the empty shell.

Verified this works: `renderers.size` went **0 → 2** (an app renderer and the
dev-overlay renderer). Two numbers worth having as a baseline:

| Measured | Count |
|---|---|
| Commits during initial page load | **35** |
| Commits from one click on a "Decline" button | **22** |

22 commits for one click is the kind of number that starts an investigation.

`addInitScript` does **not** run for `page.setContent()` on the initial
`about:blank` — navigate to a real URL (`file://` is fine for a fixture).

## Which components actually rendered — do not guess this

Three plausible predicates inside `onCommitFiberRoot`. I built a fixture with
known ground truth (each component increments a counter in its render body) and
ran them against it.

Fixture: `App` holds state; `Middle` takes the changing value; `Leaf` takes it
from `Middle`; `Static` is `memo()` with no props; `Waste` takes a constant
string prop; `Sibling` takes nothing. One click bumps `App`'s state.

**Ground truth for that click: App, Middle, Leaf, Waste, Sibling rendered.
`Static` did not.**

Each predicate, the result it gave on that fixture, and the verdict:

- **`fiber.actualDuration > 0`** — varied run to run: `[App, Middle]`, then
  `[App, Middle, Leaf]`, then all five. **Non-deterministic — right 1 run in
  4.** `actualDuration` accumulates the subtree and depends on timer
  resolution.
- **`alternate === null || alternate.memoizedProps !== memoizedProps`** —
  `[Middle, Leaf, Waste, Sibling]`. **Misses `App`** — it re-rendered from
  *state*, and its props never changed.
- **`fiber.flags & 1`** (`PerformedWork`) —
  `[App, Middle, Leaf, Waste, Sibling]`, **identical across 4 runs**.
  **Exact.** Correctly excludes the `memo` bailout.

Use `flags & 1`. It is the flag React itself sets on a fiber that performed
work in the commit, it is stable, and it gets memo bailouts right — which is
the entire reason you are looking.

```ts
const walk = (f, out) => {
  if (!f) return
  if (f.flags & 1) out.add(nameOf(f))
  walk(f.child, out); walk(f.sibling, out)
}
```

### Wasted renders

A component that performed work while nothing it depends on changed is a
`memo()` candidate and often the cause of a janky interaction:

```ts
const wasted = (f) =>
  (f.flags & 1) && f.alternate
  && shallowEqual(f.memoizedProps, f.alternate.memoizedProps)
  && f.memoizedState === f.alternate.memoizedState
```

On the fixture this returned **`[Waste, Sibling]`** on all four runs — exactly
the two that re-rendered for nothing. It correctly excluded `Leaf` (its prop
really changed) and `App` (its state really changed).

That is a finding you can hand to someone: *"clicking this re-renders `Waste`
and `Sibling`, and neither had a reason to."*

## Production builds

Verified against a minified production bundle of the same fixture:

- The hook, the commit stream and `flags & 1` **all still work** — the
  predicate returned the same five components and the same two wasted ones.
- **Names are minified**: `[eM, rM, nM, tM, iM]` instead of
  `[App, Middle, Leaf, Waste, Sibling]`.
- `_debugOwner` / `_debugStack` are dev-only and simply absent.

So the *shape* of the answer survives production; the *labels* do not. Anchor a
production run to DOM elements (Route A from a known element, then walk up),
not to component names.

## What to assert

Counts, not names — names drift with every refactor, counts encode the bug:

```ts
expect(commitsFor(() => row.click())).toBeLessThan(5)
expect(wastedIn(lastCommit)).toEqual([])
```

Two more that have earned their place:

- **Run the same interaction 5× and diff the commit counts.** Anything not
  identical is a state leak — the fifth click should cost what the first did.
- **Compare a working and a broken run's commit list.** The component that
  appears in one and not the other is usually the answer, and no screenshot
  was going to tell you.

## Cost and limits

- The walk is over the whole fiber tree per commit. Measured ~200 fibers on a
  small page; keep the callback to flag checks and a name lookup, and do the
  analysis after `stop()`.
- The stub replaces the real hook, so **React DevTools cannot attach during the
  run**. That is fine headless and a nuisance headed.
- Everything here is React-internal and unversioned. `flags & 1` has been
  `PerformedWork` for the whole fiber era, but **re-run the ground-truth
  fixture after a major React upgrade** rather than trusting this page.
