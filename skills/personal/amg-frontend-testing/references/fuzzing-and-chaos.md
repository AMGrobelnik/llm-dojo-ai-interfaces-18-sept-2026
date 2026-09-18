# Fuzzing, monkey testing and chaos

Unguided exploration finds what a checklist cannot, because a checklist only
contains what someone thought of. The reason teams never turn it on is that a
random failure gets dismissed as flake — so the reproducibility half below is
not optional, it is the whole difference between a filed bug and an ignored
one.

---

## The headline: a seed does not reproduce a UI monkey run

Every "seed your monkey" article is wrong about this, and it is worth knowing
before you build anything.

**A seeded PRNG makes the *decision stream* deterministic. It does not make the
*app state* deterministic.** Replay the same seed and the app is a little
different — a poll landed at a different moment, an animation was mid-flight,
a fetch resolved in a different order — so decision #14 ("click the third
button") now lands on a different button, and the crash does not come back.
The agent concludes "flaky, ignore".

**What reproduces a run is the recorded action log**, not the seed. Record what
was actually done — resolved selector, action, value — and replay *that*.

```ts
type Step = { sel: string; act: "click" | "hover" | "fill" | "key"; val?: string }
const log: Step[] = []
// during the run, append the RESOLVED step, not the intent
// on failure, attach the log; to reproduce, replay the log
```

Keep the seed too — it is useful for regenerating a *similar* run — but never
present it as the repro.

## Shrink the log before reporting it

A 40-step log is a log nobody reads. **ddmin (delta debugging)** turns it into
the 2–3 steps that actually matter, in about twenty lines and no dependency:

```ts
async function shrink(log: Step[], stillFails: (l: Step[]) => Promise<boolean>) {
  let cur = log, n = 2
  while (cur.length >= 2) {
    const size = Math.ceil(cur.length / n)
    let reduced = false
    for (let i = 0; i < cur.length; i += size) {
      // try the complement: everything EXCEPT this chunk
      const candidate = [...cur.slice(0, i), ...cur.slice(i + size)]
      if (candidate.length && (await stillFails(candidate))) {
        cur = candidate
        n = Math.max(n - 1, 2)
        reduced = true
        break
      }
    }
    if (!reduced) {
      if (n >= cur.length) break
      n = Math.min(n * 2, cur.length)
    }
  }
  return cur
}
```

This is the step everyone skips, and it is what makes a random finding
actionable.

## Bounding the monkey

Without rails a monkey deletes data, revokes a key, signs itself out on step 3,
or opens a modal it cannot escape. Bound it before the first run:

```ts
// Catch-all guard FIRST, so nothing destructive can leave the browser.
for (const p of ["**/delete**", "**/stop**", "**/logout**", "**/start**", "**/fork**"])
  await page.route(p, (r) => r.fulfill({ status: 200, body: "{}" }))
```

Also: cap actions per screen, forbid navigation away from the area under test,
and re-assert after every step that the app is not inert
(`body { pointer-events }`) — a monkey trapped behind a stuck modal spends the
rest of its budget clicking nothing.

Route precedence is registration order, **last match wins**, so register the
guard before anything that might override it — and verify the guard actually
bit, rather than assuming.

## A measured negative result: don't monkey a component catalogue

Running a seeded monkey over **45 stories × 25 actions took ~13 minutes and
found zero errors.** The component layer is already hardened by the fact that
each story is a small, isolated, well-formed state.

Monkey the **app at route level**, where the interesting state lives:
interleaved navigation, overlays over overlays, actions fired mid-skeleton.

## Network chaos

The category that finds silent failure. A verified example, on a real app:
injecting **two connection resets, one 500, and a 900 ms delay** into its API
produced a page that rendered its normal full body, threw **zero** page errors,
and showed **no error UI at all**. Every existing test passed. A user on a bad
connection sees a confidently wrong page.

```ts
let n = 0
await page.route("**/api/**", async (route) => {
  n++
  if (n % 7 === 0) return route.abort("connectionreset")
  if (n % 11 === 0) return route.fulfill({ status: 500, body: "{}" })
  if (n % 5 === 0) await new Promise((r) => setTimeout(r, 900))   // jitter
  await route.continue()
})
```

Four traps in this area, all verified:

- **`context.setOffline()` is a silent no-op against a `page.route()` mock
  harness.** Route interception fulfils requests without touching the network
  stack, so the "offline" test is false-green while `navigator.onLine` and the
  `offline` event still fire. Offline is *two independent switches*; if your
  data is mocked, you must fail the routes too.
- **`route.fulfill()` cannot truncate a body.** It always writes a complete
  one, so "headers arrived, body cut off mid-stream" — the case that breaks
  every parser assuming completeness — is invisible to a pure route harness.
  It needs a real server that closes the socket early.
- **Flapping, not a single toggle, is what breaks reconnect logic.** Duplicate
  in-flight requests, cursors that advance twice, a "Reconnecting…" banner that
  never clears. Toggle offline/online several times.
- **A query library may ignore `Retry-After`.** TanStack Query v5 uses its own
  exponential backoff regardless of the header, so a 429 combined with an
  unconditional `refetchInterval` hammers a rate-limited backend *harder*.
  Assert the request count over a window rather than trusting the library.

## State fuzzing

**Corrupt the client store before first paint.** The classic "user cannot load
the app and clearing site data is the only fix" bug:

```ts
await page.addInitScript(() => {
  localStorage.setItem("<app-key>", "{half-written")
  sessionStorage.setItem("<app-key>", "null")
})
```

**Then deny storage entirely** — a different branch, and usually the one with
a comment saying "if this fails we fall back to…" that nothing has ever
exercised. Private browsing, storage-blocked, and quota-exceeded all land here:

```ts
await page.addInitScript(() => {
  Object.defineProperty(window, "indexedDB", { get() { throw new DOMException("blocked") } })
  const set = Storage.prototype.setItem
  Storage.prototype.setItem = function (k, v) {
    if (v.length > 1000) throw new DOMException("QuotaExceededError")
    return set.call(this, k, v)
  }
})
```

**Fuzz the event stream, not just the payloads.** If the app consumes a
cursor-paged stream, its test double almost certainly hard-codes monotonic,
in-order, never-duplicated delivery — which means no test can see what happens
when reality does otherwise. Real polling over a cursor delivers **duplicates
on retry** and **gaps after a backend restart**. Feed it: out-of-order,
duplicated, replayed, and gapped batches.

**Clock skew is not time travel.** Time travel moves the client's clock;
skew is the client and server *disagreeing*, which is true for every user in a
non-UTC timezone with a slightly wrong clock. It produces negative durations,
"in 2 hours" on a completed item, and progress past 100%. Set the context
timezone and the fixture timestamps independently.

## Input fuzzing

One shared corpus, reused for every text field:

- The **naughty-strings** list (`big-list-of-naughty-strings`, or hand-pick 30
  of them — the full list is mostly noise for a UI).
- **RTL override** `U+202E` — flips the rendering of everything after it, and
  escapes its container in a way nothing else does.
- **ZWJ emoji families** — break `.slice()` into a lone surrogate.
- **Zalgo** — stacks past the line box.
- **A 5,000-char unbroken token** — the layout blowout.
- **A 100k-char paste** — freezes the main thread if handled per-keystroke.
- **Schema boundary values** — one below, exactly at, one above every declared
  min/max.

Use `pressSequentially`, not `fill`, whenever per-keystroke handling is the
thing under test.

## URL fuzzing

The cheapest fuzz surface in any app that parses typed state out of query
params, and usually completely unguarded — a hostile deep link injects
out-of-range state that no UI interaction can produce. A parser with
`.withDefault(0)` will happily accept a negative or absurd value and hand it to
code that assumes a valid index. See `systematic-coverage.md § 2`.

## Auditing the tests themselves

**Mutation testing** answers the question coverage cannot: *if I break this
line, does anything go red?* With a large green suite the real risk is false
confidence. Stryker is the tool; point it at pure logic modules — cursor
arithmetic, TTLs, comparisons — where a flipped operator would be silent.

It does not support browser-mode component tests. For those, do it by hand and
sparingly: invert one condition, run the suite, confirm something fails,
revert. That is the same discipline as "break the fix and watch the test fail",
applied to code you did not just write.

## The reproducibility kit

Every random-input technique above must attach, on failure:

| Attachment | Why |
|---|---|
| The **action log** (shrunk) | The actual repro |
| The **seed** | Regenerates a similar run, not the same one |
| The **trace** | The full record of what happened |
| An **environment fingerprint** | Distinguishes environments |

The fingerprint is browser version, viewport, timezone and app build id, so
"cannot reproduce" can be distinguished from "different environment".

Without these, every finding from this page becomes flake.
