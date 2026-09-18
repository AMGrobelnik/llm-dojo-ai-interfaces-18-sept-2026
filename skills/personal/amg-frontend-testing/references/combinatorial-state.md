# The combinatorial explosion of UI state

A real screen has dozens of independently-activatable things — drawers, modals,
popovers, tooltips, toasts, tabs, filters, sort orders, selection modes, theme,
density, viewport, flags, and the data state under all of it. A representative
12-factor model is **746,496** combinations. Nobody tests that by hand, and the
defects live exactly in the combinations nobody tried.

The method has five parts: **derive the axes, cover them, assert something
generic at every cell, localize what fails, and cover order separately.**

Numbers on this page are measured runs unless labelled otherwise.

---

## 0. You do not need a generator dependency

A ~30-line AETG greedy matches PICT and `covertable` to within ~5% on every
model tested, handles mixed arity, and expresses **true variable strength** for
free — because the coverage goal is just a list of factor-index subsets, so
"all 2-subsets, plus 3-subsets of the overlay cluster" is one heterogeneous
list.

```js
// goal = factor-index tuples to cover: combos(all,2), or [...combos(all,2), ...combos(OVERLAY,3)]
export function genCA(dom, goal, { pool = 25, seed = 1 } = {}) {
  const n = dom.length, key = (s, r) => s.join(",") + "|" + s.map(x => r[x]).join(",")
  const unc = new Set()
  for (const s of goal) {
    const rec = (i, a) => i === s.length
      ? unc.add(key(s, Object.fromEntries(s.map((f, j) => [f, a[j]]))))
      : dom[s[i]].forEach(v => { a.push(v); rec(i + 1, a); a.pop() })
    rec(0, [])
  }
  const cont = Array.from({ length: n }, () => []); goal.forEach(s => s.forEach(f => cont[f].push(s)))
  let st = seed >>> 0
  const rnd = () => ((st = Math.imul(st ^ (st >>> 15), 1 | st) + 0x6d2b79f5) >>> 0) / 2 ** 32
  const shuf = a => { a = [...a]; for (let i = a.length - 1; i > 0; i--) { const j = rnd() * (i + 1) | 0; [a[i], a[j]] = [a[j], a[i]] } return a }
  const rows = [], obligations = unc.size
  while (unc.size) {
    let best, bg = -1
    for (let c = 0; c < pool; c++) {
      const row = new Array(n).fill(null)
      for (const f of shuf([...Array(n).keys()])) {
        let bv, bgv = -1
        for (const v of shuf(dom[f])) {
          row[f] = v
          let g = 0
          for (const s of cont[f]) if (s.every(x => row[x] !== null) && unc.has(key(s, row))) g++
          if (g > bgv) { bgv = g; bv = v }
        }
        row[f] = bv
      }
      let g = 0; for (const s of goal) if (unc.has(key(s, row))) g++
      if (g > bg) { bg = g; best = row }
    }
    for (const s of goal) unc.delete(key(s, best))
    rows.push(best)
  }
  return { rows, obligations }   // `obligations` is the review gate — see §6
}
```

Deterministic for a fixed seed, zero deps, no postinstall toolchain. `pict-node`
shells out to a binary it `git clone`s and `make`s at install time, which fails
in hermetic CI; reach for it only if you already have it.

## 1. Derive the axes — never hand-write them

Union all five sources. A hand-written model is stale the day someone ships a
toggle.

| # | Source |
|---|---|
| 1 | CSS `@media` scrape of the **built** stylesheet |
| 2 | URL-state AST (nuqs / query-param hooks / router) |
| 3 | Type checker over discriminated unions + store state |
| 4 | Component catalogue (Storybook manifest / react-docgen) |
| 5 | Live-DOM harvest of ARIA + `data-state` |

Cost and yield, by source:

| # | Cost | Yields |
|---|---|---|
| 1 | <1 s | breakpoints, `prefers-*`, pointer/hover |
| 2 | <5 s | param names, literal domains, defaults |
| 3 | ~3 s | discriminant axis, nested axes, free exclusions |
| 4 | one fetch | prop domains, defaults, required-ness |
| 5 | ~300 ms/page | what is **actually mounted and activatable** |

Rules that all five need:

- **Key each DOM axis per source.** A Radix trigger carries `aria-expanded`
  *and* `data-state`; one key merges the domains into a bogus four-value
  `{true|false|open|closed}`. This was observed live before per-source keying
  was added.
- **Optional booleans get 2 levels, not 3.** `flag?: boolean` read as
  `if (flag)` means absent ≡ false. Adding `absent` takes 7 optional booleans
  from 128 to 2,187 — measured.
- **Scrape the built stylesheet**, or you miss every utility-class breakpoint
  (`md:hidden`).
- **Unwrap `satisfies` as well as `as const`**, or literal domains resolve to
  nothing.
- **Diff the static catalogue against the runtime one.** Memo/forwardRef exports
  under-report at runtime; docgen under-reports union props. Neither is
  authoritative alone.

### Collapse instances, and make multiplicity an axis

200 list rows must not become 200 factors. Key each axis by its **structural
position** (ancestor-role path), not its accessible name — names change with
data. Then emit two factors per class:

```
<class>          the widget's own domain      {open, closed}
<class>.count    ["none", "one", "many"]      ← multiplicity IS the axis
```

`many` (bind to ≥2 in the applicator) is what surfaces two stacked overlays,
two open row menus, a selection active under a filter. Worked example:
1,168–1,326 raw activatable instances collapsed to **19** classes on the
structural key, **76** with className included. Neither is "right" — 19 merges
different widgets sharing a DOM shape, 76 splits colour-only variants. Treat the
number as a review artifact: a 3× jump means a new widget family shipped.

### Mine constraints; do not guess them

- **Static, free:** every `[aria-controls]` whose target id is **absent** from
  the DOM proves a latent sub-model behind that trigger. Every present target
  gives `IF [parent]="closed" THEN [child]="n/a"`.
- **Dynamic, ~2 s per axis:** reset → actuate → re-harvest → set-diff. Axes that
  **disappear** are nested under the actuated one; axes that **appear** are
  latent; two overlays never observed co-present are mutually exclusive. Recurse
  to depth 2; depth 3 rarely pays.

Run this as a nightly model refresh, never per commit.

### Cap every domain at ~4 equivalence classes

The highest-leverage step and the one everyone skips — **values are quadratic
while factors are logarithmic** (§3). Collapsing a 6-value axis to 4 saves more
than deleting three whole axes. Open scalars (strings, numbers, ids, arrays) are
not axes: give them a named fixture set `{empty, one, many, huge, garbage}`.
`garbage` is where the crashes are.

### Lock the model

`axes.lock.json`, committed, regenerated every run, **exit 1 on added or widened
axes**; `removed` is not a failure. A new toggle is an untested toggle by
construction. Lock static sources unconditionally; lock DOM axes only as class
keys under a fixed fixture seed, or the file churns.

## 2. The applicator is where sweeps fail silently

```ts
type Axis<V = string> = {
  id: string; values: V[]; baseline: V; tier: number   // tier = apply order
  set(page: Page, v: V): Promise<void>
  read(page: Page): Promise<V | null>                  // MANDATORY
}

async function applyCell(page, axes, cell) {
  await page.goto("/")                                 // FRESH page per cell — never incremental
  for (const ax of [...axes].sort((a, b) => a.tier - b.tier)) {
    const want = cell[ax.id]
    if (want === "n/a") continue
    await ax.set(page, want)
    if ((await ax.read(page)) !== want) return { unreachable: true, axis: ax.id }
  }
  return { ok: true }
}
```

Three rules the read-back enforces:

- **Apply in dependency order** from the mined containment edges: data →
  viewport/theme/density → route → panels → **overlays last**. Setting
  `data=empty` after opening a drawer closes the drawer, and you silently test a
  different cell.
- **Fresh page per cell.** An incremental applicator is an untracked *sequence*
  test wearing a combination test's clothes.
- **A cell whose read-back disagrees is UNREACHABLE, not passing.** Count them,
  and fail CI when reachability drops below a committed threshold. This is the
  single most common way a sweep goes green while testing nothing.

Seed the data axis by network interception, not a live backend, or data is not a
factor at all.

## 2b. The realization PREDICATE fails as often as the applicator

Section 2 says a sweep fails silently when the applicator cannot act. There is a
second, subtler version: the applicator acts, and your check for *whether it
worked* is wrong. Then the cell is labelled unrealized (or worse, realized) on
the strength of a bad measurement, and you tune the wrong half.

Measured twice on one project, same sweep:

- **First pass** — the axis triggers were named for desktop (`Toggle sidebar`),
  and at 360px the control is called `Open menu`. 6 of 12 cells no-op'd. Fixed
  by discovering the trigger per viewport instead of hard-coding a name.
- **Second pass** — triggers now worked, and 5 of 8 cells still reported
  unrealized. The applicator was fine; the *predicate* was wrong. The rail was
  modelled as binary open/closed with `width > 0`, and it actually has THREE
  states: `0` hidden (on mobile the drawer opens as a `role=dialog` instead,
  so the nav keeps zero width), `~51` collapsed, `>200` expanded. A cell asking
  for "closed" at 768px — already collapsed at 51 — measured `51 > 0`, decided
  it was open, clicked, and *expanded* it. The sweep drove the app away from the
  cell it was trying to reach.

Two rules:

- **Enumerate the states by measuring them before you write the predicate.**
  Probe each viewport, print the actual values, and bucket from the data. A
  state you did not know about is indistinguishable from a broken applicator.
- **Assert realization and let an unrealized cell FAIL the run.** An unrealized
  cell is not a passing cell — it is a cell that never happened. Print
  `want=` and `got=` for every axis, not a boolean, or you cannot tell "the
  applicator did nothing" from "the predicate misread the result".

The oracle readings from unrealized cells are still worth keeping — in that run
`overflowX=0`, `dupIds=0` and `focusInHidden=false` held across all 8 cells
regardless of whether the axes landed. Just do not count them as coverage of the
combination you meant to test.

## 3. The generic oracle

You cannot hand-write an assertion per cell, so assert **invariants that must
hold in every state**. Ordered by how often each catches something:

1. **Ledger empty** — no console errors, no `pageerror`, no failed requests.
2. **Focus is never inside `[aria-hidden]` or `[inert]`.**
3. **At most one `aria-modal` dialog.**
4. **The topmost overlay is hit-testable** — but define "topmost" and "centre"
   carefully, because the naive version is a false-positive factory. Measured
   on a real sweep: an oracle selecting
   `[role=dialog],[role=menu],[role=listbox],[role=alertdialog]` and taking
   `.at(-1)` picked the search results **listbox** (last in DOM order, not
   topmost in stacking order), whose rect was `498 x 6808` in a 900px viewport
   because it held 200 options. Its geometric centre sat ~3100px below the
   fold, `elementFromPoint` there returned the backdrop, and the check "failed"
   on two cells — **identically across two full runs**, because DOM order is
   deterministic. Reproducibility read as a real defect for two rounds.
   So: pick the overlay by **stacking order** (or restrict to the
   `[role=dialog]` subset), and probe the element's **visible intersection with
   the viewport**, never its geometric centre.
5. **No horizontal page overflow** (`scrollWidth ≤ clientWidth + 1`).
6. **No zero-size interactive elements.**
7. **Scroll-lock refcount biconditional** — the lock attribute is present *iff*
   at least one locking layer is open. Marker strings are library-specific
   (`data-scroll-locked`, `--removed-body-scroll-bar-size` for
   `react-remove-scroll`); **the principle ports, the strings do not.**
8. **Identity integrity** — no duplicate ids, no dangling IDREFs.
9. **Render-garbage text scan** — `undefined`, `NaN`, `[object Object]`,
   `null` in visible text.

Two stronger, budget-permitting oracles:

- **Round-trip / idempotence.** Apply a factor, undo it, assert the state
  matches the start. It needs no knowledge of what correct looks like, which is
  what makes it the strongest generic oracle available. Measured catching a
  seeded leak — a stale focusable left behind after a drawer closed — that the
  static invariant set missed because the node was offscreen.
- **Commutativity.** For factors that are supposed to be independent, A-then-B
  and B-then-A must reach the same state.

If a sweep has never found a bug, **the oracle is the suspect, not the model.**

## 4. Sizing — three measured laws

12-factor model, `viewport4 theme2 density2 drawer3 modal4 popover3 selection3
filter4 sort3 data6 flag2 toast3` = 746,496 cartesian:

| Design | Rows | Obligations |
|---|---|---|
| t=2 | **31** | 690 |
| t=3 | **140** (4.5×) | 7,326 |
| t=2 + overlay cluster @3 | **41** | 825 |
| t=2 + data cluster @3 | **72** | 924 |
| t=2 + **both** clusters @3 | **75** | 1,059 |

Three levers, each with its measurement and its shape:

- **Factors *k*** (v=3), **logarithmic** — 5→12, 10→17, 20→23, 40→27, 80→33,
  160→40, 320→**44** rows.
- **Values *v*** (k=12), **quadratic** — 2→9, 3→19, 4→31, 5→48, 6→70,
  8→**112** rows.
- **Strength *t*** (k=12,v=3), **exponential** — 2→19, 3→78, 4→**267** rows.

Consequences, in priority order:

- **Model every axis you can name.** 64× more factors costs 3.7× more cases.
  The 13th axis costs 1–3 rows.
- **Collapsing values is the only cheap win.**
- **Never raise `t` globally.** t=2 with both clusters at 3 is **75 rows vs
  140** — full 3-wise where the bugs are, at 54% of the price.

**Which factors deserve t=3** — exactly two rules:

1. Factors sharing **one rendering resource** — z-index, portal root, focus
   trap, scroll-lock refcount. That is the overlay cluster. This is not taste:
   those refcounts are module-level singletons, so the interaction is
   *structurally* 3-wise.
2. Factors in a **real conditional chain**: data → filter → selection → sort.

Everything else stays at 2-wise. Note the floor: a mixed-arity model needs at
least the product of its two largest domains.

**Prefix budgeting.** Greedy emits high-value rows first, so a truncated
committed array degrades gracefully — measured on a 148-row t=3 suite:

```
first  5 rows ( 3%) → 44.9% of 2-way pairs
first 10 rows ( 7%) → 71.0%
first 20 rows (14%) → 91.9%
first 38 rows (26%) → 100.0%   ← full 2-way reached here
```

PR runs the prefix, nightly runs all, case indices shared so triage history
survives. **Measure your own crossover** — it moved from 26% to 50% between two
runs of a nominally identical model, so it is a property of your generator run,
not a law.

Run the sweep at the **component layer first** (~100 ms/case) and promote only
surviving axes to e2e (~2–3 s/case).

## 5. When a case fails

A failing row names 12 factor values; 2–3 of them matter. Reporting "case #37"
is worthless — regeneration renumbers everything.

```
0. Re-run the exact cell twice. 2/2 fail → real. 1/2 → quarantine, never localize a flake.
1. Confirm the baseline cell passes. If it fails too, the defect is unconditional. Stop.
2. One-factor-at-a-time reduction (k runs): reset each differing factor to baseline;
   if it still fails, that factor was irrelevant — keep it reset.
3. Verify minimality (|S| runs): from baseline, set ONLY S. It must fail.
   If it passes, fall back to ddmin over the factors reset in step 2 (non-monotone case).
4. Drop test: removing any one member of S must make it pass.
```

Cost ≈ `k + |S|` runs ≈ 15 runs, ~45 s at e2e, ~2 s at the component layer.
**Localize per violation code, never per failing case** — one sweep produced 5
distinct codes across overlapping cells, and keying on "any failure" gives the
reducer five targets at once.

Report as a **constraint-shaped statement plus a seed row**:

```
INTERACTION  data=empty ∧ drawer=filters ∧ viewport=xs
  effect     scroll-lock attribute persists after the drawer closes
  minimal    3 of 12 factors; all 3 required (verified by drop test)
  order      not order-dependent (both apply orders reproduce)
  repro      sweep --cell '{"data":"empty","drawer":"filters","viewport":"xs"}'
```

Then: write the named regression test, append the **full-width** row to
`cases.seed.json` so it is in every future array, and — only if the state is
genuinely unreachable in the product — add it as a generator **constraint** and
justify the obligation delta. "The sweep generated an impossible state" is a
*model* bug; never fix it by filtering rows afterwards or adding a skip.

## 6. Order is a separate problem

**Combinations test state; sequences test transitions.** A combination sweep
uses a fresh page per cell and therefore has *no history*, so it is structurally
blind to module-level counters, mount-order effects, focus-restore chains,
portal stacking and effect cleanup.

| Design | n=8 | n=12 | n=20 |
|---|---|---|---|
| **List + its exact reverse** | 2 tests | 2 | 2 |
| Greedy 3-way sequence array | 12 | 18 | 22 |
| **Eulerian adjacent walk** | 1 test, 57 steps | 1, 133 | 1, 381 |

What each covers:

- **List + its exact reverse** — **100% of ordered pairs** (56/56, 132/132,
  380/380) vs 20! ≈ 2.4e18.
- **Greedy 3-way sequence array** — 100% of ordered triples.
- **Eulerian adjacent walk** — 100% of *adjacent* ordered pairs.

Start with the reverse sweep. It is two tests, it covers every ordered pair, and
almost nobody runs it. *(Both rows independently re-verified here: n=20 gives
380/380 pairs from two sequences, and the Eulerian walk length is exactly
n(n−1)+1 at n=4, 8, 12, 20.)*

**Model overlays as `open_i`/`close_i` event pairs** with precedence
`open_i < close_i`, or you can never express "B opened *while* A is open, A
closed first" — the shape that breaks focus-restore chains. Generate candidates
by **random topological sort** so constraints hold by construction, and shrink
the coverage goal to **reachable** tuples via transitive closure; leave
unreachable tuples in and the greedy loop never terminates, hunting
`(close_A, open_A)` forever. Six overlays = 12 events = 479,001,600
permutations, covered 3-wise in **18 tests** (1140/1140 reachable triples).

**Bound runtime by partitioning the alphabet, never by truncating sequence
length.** Truncation is measurably the wrong lever — capping at 3 steps needs
~8× the total actions and still plateaus below 100%. Use one global t=2 sweep
plus per-interference-group t=3 sweeps, and add a "mixed" group holding one
representative of each, because the classic bugs are cross-group (a drawer open
across a breakpoint change).

The Eulerian walk needs **repeatable, idempotent** events — each fires n−1
times — so split out strictly-once events (submit, delete), and raise the
timeout for that spec: 20 events is 381 actions.

## 7. How the whole approach goes wrong

Each failure below is followed by the rule that prevents it.

- **The applicator lies** — `set()` no-ops, the cell is never established, the
  oracle asserts about the default state. **Rule:** mandatory `read()`
  back-check; count unreachable cells; fail CI below a committed threshold.
  **The most common real failure.**
- **An over-broad constraint deletes reachable states** — the suite gets
  *smaller*, exits 0, prints nothing. **Rule:** snapshot the **obligation
  count** as a reviewed number. Measured: one over-broad constraint pruned 6
  pairs instead of 3, and the 3 extra were real bug-prone states.
- **A constraint references a renamed value**, so half an axis becomes
  unreachable. **Rule:** assert every declared value appears in ≥1 row. Some
  generators warn only on stderr, which CI wrappers discard with exit 0.
- **Oracle is "it didn't crash"** — **Rule:** assert the §3 invariants at
  every cell.
- **Regeneration churns 100% of rows** — **Rule:** commit the array;
  regenerate seeded with the committed file; seed rows must be **full width**
  or they are silently dropped.
- **Someone asserts a row count** — **Rule:** greedy is non-monotonic — 75
  rows for *two* 3-wise clusters vs 72 for *one*. Assert coverage properties,
  never counts.
- **Model drift** — **Rule:** `axes.lock.json`, exit 1 on added or widened.
- **Flake amplification** — 40 cells × 5% flake = **87% chance of a red run**,
  and the sweep is disabled within two weeks. **Rule:** `retries: 0`,
  automatic localization on failure, a reviewed quarantine list. A sweep's
  flake budget must be an order of magnitude tighter than hand-written tests.
- **The sweep becomes the only test** — **Rule:** a covering array covers the
  **model**, not the app. An axis never derived is covered by no `t`, and it
  says nothing about order. Keep the journey specs — the sweep is a floor.

## 8. What is not verified here

- Row counts differ per implementation — PICT 27, `covertable` 33, this
  generator 31 on the same t=2 model; 138 / 139 / 140 at t=3. The *shapes* agree
  exactly and the numbers never will, which is the argument for asserting
  coverage rather than counts.
- Storybook manifest and `__STORYBOOK_PREVIEW__` extraction shapes were reported
  from a live server in one research pass and **not re-exercised** in the final
  synthesis. `__STORYBOOK_PREVIEW__` is internal, unversioned API — feature-check
  it.
- Wall-clock per-case figures at the e2e layer are arithmetic, not measurement.
  The one measured execution figure is the component layer: 128 stories in
  11.98 s (~94 ms/story with `isolate: false`).
- Registry metadata for `covertable` / `pict-node` / `fast-check` is
  second-hand; all three were confirmed *absent* from the repo used for
  availability checks. Pin exact versions if you adopt one.
