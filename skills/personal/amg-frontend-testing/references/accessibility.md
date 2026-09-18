# Accessibility

Two things make this worth its own reference rather than a checklist entry:
most teams run the automated half wrong, and the automated half covers far
less than people assume.

---

## How much automation actually covers

**The honest answer is a contested range, and you should quote the range.**

| Source (2026) | Claim |
|---|---|
| Deque, axe-core's vendor | ~**57%** of WCAG issues auto-detected |
| Independent write-ups | **30–40%**; automation misses 60–70% |

Both figures are current. Deque's is a vendor number for its own engine on a
curated issue set; the lower figures come from people auditing real sites. Do
not average them. What both agree on is that **the majority of the remaining
issues are keyboard, focus order, reading order, and whether the experience
actually makes sense** — none of which a rule engine can decide.

The six issues automation catches reliably, year after year: **low contrast,
missing alt text, missing form labels, empty links, empty buttons, missing
document language**. If your automated report only ever shows those, that is
the tool working correctly, not a clean app.

Of the nine criteria added in WCAG 2.2, **only target-size (2.5.8) is reliably
automatable.**

## The mistake almost everyone makes

> Accessibility is a property of every state a page can reach, and most of
> those states only exist after someone interacts.

Running axe once on initial render tests the emptiest state the app has. The
dialog, the popover, the error message, the loaded list, the expanded
disclosure — none of them existed when the scan ran.

**Scan after each interaction, not once per page.**

```ts
import AxeBuilder from "@axe-core/playwright"

const scan = async (label: string) => {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze()
  expect(violations, `${label}: ${violations.map((v) => `${v.id}@${v.nodes.length}`).join(", ")}`).toEqual([])
}

await scan("initial")
await openTheDialog()
await scan("dialog open")          // ← the state that was never tested
await submitWithAnError()
await scan("validation error")
```

The same applies per-story in a component catalogue: a story *is* a state, so
a story-level scan is the cheapest way to cover many states at once.

## In a Storybook catalogue

If `@storybook/addon-a11y` is installed, axe is very likely **already running
and gating nothing**. The parameter has three values:

```ts
a11y: { test: "off" | "todo" | "error" }
```

`"todo"` runs the scan and reports violations as warnings that fail nothing —
the default in many setups, and easy to mistake for "we're clean". Measured on
one app: switching to `"error"` failed **10 of 153 story tests**, all
colour-contrast.

Migrate **per story**: set the global to `"error"` and escape-hatch the known
failures with `parameters: { a11y: { test: "todo" } }`. Setting the global back
to `"todo"` to make CI green means the gate never lands.

## A measured example: 0 violations, 3 real defects, same screens

Run this comparison once and you will never quote a violation count again.
Eight chart views, axe-core scoped to `main`:

    cost tokens models heatmap timemap types burnup rhythm  ->  0 violations each

The probe was validated first — `passes=23` on the clean page (proving rules
actually ran), three deliberately broken elements injected and all three caught
(`button-name`, `color-contrast`, `image-alt`), then back to 0 on removal. The
zeros are real.

On those same eight screens, three real defects were sitting in plain view:

- **All 8 charts are unnamed graphics** — `role=null`, no `aria-label`, no
  `<title>`, 12-26 loose `<text>` nodes each. *Why axe is silent:* no rule
  fires on a bare inline `<svg>` with no role. It is not an `img`, so
  `image-alt` does not apply; it has no role, so no name-required rule
  applies.
- **The active item in a 6-button switcher is indicated by background tint
  and font-weight alone** — no `aria-pressed`/`aria-current`/`aria-selected`.
  *Why axe is silent:* every button HAS an accessible name, so `button-name`
  passes. Nothing checks whether *state* is exposed.
- **A keyboard key that does nothing** (the arrow step swallowed by a snap
  window). *Why axe is silent:* behaviour is not markup. No static audit can
  see it.

`passes` is the number to check, not `violations`. A run reporting 0 violations
and 0 passes evaluated nothing, and reads identically in a summary. And a clean
axe run means "no machine-detectable violations in the rules that applied" —
which is a floor worth having and is not the same claim as "accessible".

## The states axe never sees

axe scans the DOM as it is, so every style that exists only under a pointer or
a keyboard is invisible to it. Two of those were real defects on one app:

**Hover that LOWERS contrast.** A control passes 1.4.3 at rest and fails while
hovered, because the hover rule lightens the text. Measured twice on one
codebase: a dropdown trigger 4.58:1 → **3.85:1** hovered, and a badge
4.58:1 → **3.81:1** hovered. Invisible to a page-load scan, and invisible to an
after-interaction scan unless you happen to hover that exact control. Cheap to
find statically — parse the class string and compare luminance of the
`text-*` / `hover:text-*` pair. Hover should raise emphasis; any rule that
lowers it deserves a look even when it stays above threshold.

**Focus rings.** 1.4.11 wants 3:1 for the indicator against what surrounds it.
A low-opacity ring (`focus:ring-blue-400/30`) can be well under that, and no
scan of the resting DOM will say so. Focus the element, read the computed
`outline` / `box-shadow` colour, and compare it against the adjacent
background.

**Selected / active states.** `aria-selected`, `data-state=active` and friends
swap foreground and background together; scan them with the state applied.

## Checks worth automating that axe does not do

Rule engines check rules. These check *behaviour*, and each catches a class
axe cannot:

- **Focus order matches visual order** — Tab N times, record
  `document.activeElement` and its `y`. Mostly increasing; a jump backwards is
  the finding.
- **Every interactive element is reachable by keyboard** — compare the
  tab-stop set against the inventory of interactive elements.
- **Focus is never invisible** — at each stop assert `toBeInViewport()` and
  that an outline or ring is computed.
- **Focus returns after an overlay closes** — record the trigger, close with
  Escape, poll `document.activeElement` back to it.
- **A modal traps focus; a hover panel does not** — Tab (focusable count + 2)
  times and assert containment holds — or does not. **Count first, and if the
  dialog is big, shrink it first.** A fixed Tab budget proves nothing: 14 Tabs
  inside a search modal listing 200 runs as `role=option` never left the
  dialog, and was recorded as "trap works, 0 escapes". Filtering the list to 2
  focusables and tabbing 12 times showed **11 of 12 stops outside** — the
  modal declares `aria-modal="true"` and does not trap at all.
- **Escape unwinds one layer at a time** — popover inside dialog: first Escape
  closes the popover only.
- **Nothing is left inert after close** —
  `getComputedStyle(document.body).pointerEvents !== "none"`, no stray
  `aria-hidden` on body.
- **Structural drift** — `toMatchAriaSnapshot`; a button losing its accessible
  name fails it, and axe will not.
- **Reflow at 320 px** (WCAG 1.4.10) — no horizontal scroll at 320 wide.
- **200% text zoom** (WCAG 1.4.4) — enlarge the root font, assert no overflow
  or clipping.
- **Target size** (2.5.8, 24×24) — `boundingBox()` alone **over-reports**:
  2.5.8 exempts targets whose 24 px-diameter circles do not intersect.
  Measured on one page: 19 under-size targets, **0** real failures. 44×44 is
  2.5.5 (AAA), not this.
- **Motion honoured** — under `reducedMotion: "reduce"`, motion actually stops
  — and anything gated on `transitionend` still completes.
- **Forced colors** — box-shadow focus rings vanish; assert
  `outlineStyle !== "none"` on focus.

Code for the focus transcript and the invariant probes is in
`diagnostics.md`; the environment axes are in `exploration-catalogue.md § 6`.

## Screen reader testing

Real screen readers are drivable, but only on two platforms:
**`@guidepup/playwright`** automates **VoiceOver on macOS** and **NVDA on
Windows**. There is **no Linux support** — do not plan a Linux CI job around
it.

The portable substitute is **`@guidepup/virtual-screen-reader`**: a screen
reader *simulator* that runs virtually over the DOM, is test-framework
agnostic (vitest, Jest, Web Test Runner, Storybook), and therefore runs
anywhere including Linux CI. It asserts on **what a screen reader would
announce**, which is a different and stricter question than "does the element
have a label":

```ts
import { virtual } from "@guidepup/virtual-screen-reader"

await virtual.start({ container: document.body })
await virtual.next()
expect(await virtual.lastSpokenPhrase()).toBe("button, Save")
await virtual.stop()
```

It is a simulation, so it agrees with a real screen reader on structure and
naming and cannot tell you how NVDA actually behaves in a specific mode. Use
it as a fast structural gate per component, not as proof of the real
experience.

## Reporting

An accessibility finding is only actionable with the numbers attached. Not
"contrast is bad" but:

> `.text-black/40` renders `#8f9499` on `#eff6ff` at 10 px — **2.81:1**,
> against a 4.5:1 requirement (WCAG 1.4.3).

And be explicit about what was *not* checked. Given that automation covers
somewhere between a third and a half of the criteria, a report that does not
say "these are the automated findings; the keyboard, focus-order and
reading-order pass is separate" is overclaiming by construction.

Sources: [Deque automated coverage report](https://www.deque.com/automated-accessibility-coverage-report/) ·
[axe-core](https://github.com/dequelabs/axe-core) ·
[What axe and Lighthouse miss](https://www.davidmello.com/software-testing/test-automation/playwright-accessibility-testing-axe-lighthouse-limitations) ·
[Guidepup](https://www.guidepup.dev/) ·
[virtual-screen-reader](https://github.com/guidepup/virtual-screen-reader)

## axe accepts a placeholder as an accessible name

A field with only a `placeholder` — no `<label>`, no `aria-label` — passes
axe's `label` rule. It is treated as a last-resort accessible name, so a
form can report **0 violations** while none of its fields is really
labelled. Measured once: `/contact`, 39 passes, 0 violations, and all three
inputs placeholder-only.

The defect is real: a placeholder disappears the moment the field has
content, so the only naming vanishes exactly when someone reviewing their
entry needs it.

Automated audits cannot find this. Probe the fields directly:

    [...document.querySelectorAll("input:not([type=hidden]), textarea")].map((e) => ({
      field: e.getAttribute("name"),
      label: e.id ? !!document.querySelector(`label[for="${e.id}"]`) : false,
      ariaLabel: e.getAttribute("aria-label"),
      placeholder: e.getAttribute("placeholder"),
    }))

A row with `label:false, ariaLabel:null, placeholder:"…"` is the finding.
Exclude honeypots (`aria-hidden`, off-screen) — they need no name.

The fix is `sr-only` `<label htmlFor>` with ids from `useId()`: nothing
about the visual design changes. Confirm it landed by watching the axe
PASS count rise (39 -> 40 here) — violations stay 0 in both states, so
passes are the only signal that anything changed.

## An async error needs a live region, and only a failure path shows it

An error that renders only after a submit fails is a status message
(WCAG 4.1.3). Walk every ancestor from the message to `<body>` looking for
`role` / `aria-live`; if both are null the failure is silent to a screen
reader, however obvious the red text is. This cannot be seen on a healthy
page — you have to break the request first.

Check the recovery in the same probe: the submit must re-enable and the
typed content must survive, or the user is told about a failure they cannot
retry.

## A full-page failure state IS the page — audit it as one

Loading / error / empty branches that replace the whole view usually get
written as a bare centred `<div>` with an `<h2>`, because they read as
"a message", not "a page". They are the page: no `<main>`, no `<h1>`, so
axe reports `landmark-one-main`, `page-has-heading-one` and `region` —
but ONLY while that branch is rendered, which is why a route audited in its
success state comes back clean.

Measured once: a public share route was clean on success (its shell renders
`<main>`) and had three violations in each of its two failure branches — the
states reached by people following a dead link, i.e. the visitors least
likely to have an account and most likely to be lost.

Audit every branch, not every route:

- success (the control — it usually passes, which is the trap)
- empty / not-found
- transient failure
- loading, held open

When you fix these, check no single branch ends up with two `<main>`s: the
tags are mutually exclusive across branches, so counting them in the source
overcounts. Read which component each one sits in.

## Grepping for live-region attributes cannot see a toast

A component that reports failures with `toast.error(...)` has no `role` or
`aria-live` of its own and looks identical, to grep, to one that renders a
silent inline banner. It is not a defect: the toast host owns the live
region. Confirm which channel a surface uses before filing — one measured
sweep turned up a form that the attribute grep flagged and that was
correct.

## Compute the ratio before changing a colour, and after

Tailwind palette pairs that "look fine" sit right on the boundary, and the
same token passes on one ground and fails on another. Measure each pair:

    def lum(h):
        h = h.lstrip("#"); c = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
        c = [x/12.92 if x <= 0.03928 else ((x+0.055)/1.055)**2.4 for x in c]
        return 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]
    ratio = lambda a, b: (max(lum(a), lum(b))+0.05)/(min(lum(a), lum(b))+0.05)

Measured on one palette: `red-600` on `red-50` is **4.41:1** (fails 4.5) but
`red-600` on **white** is 4.83:1 (passes). Same text token, opposite verdicts
— so "we use red-600 for errors everywhere" is not one decision to audit,
it is one per ground. In the same sweep `amber-700`/`amber-50` (4.84) and
`emerald-700`/`emerald-50` (5.21) already passed, so only one tone needed
moving. Computing first is what kept the change to one line instead of
restyling three tones that were fine.

## A shared branch component fails once, not N times

When N routes all report the IDENTICAL violation, suspect one shared
component rather than N defects. Measured once: five run sub-routes each
reported `page-has-heading-one(1)` — one 404 component behind all five. File
it as one finding with N surfaces, and fix it once.

The inverse is the trap that produced it: a heading added to a layout's
SUCCESS branch leaves the 404 branch with none. When you fix a landmark or
heading, ask which branch you just fixed and which sibling branch still
renders instead of it.

## axe disables 8 rules by default — including target-size

`axe.run(document)` does NOT run every rule. In 4.11 these are off unless
you enable them explicitly:

    aria-roledescription, audio-caption, color-contrast-enhanced,
    duplicate-id-active, duplicate-id, identical-links-same-purpose,
    meta-refresh-no-exceptions, target-size

`target-size` is WCAG 2.5.8 **AA**, so a report of "0 violations" says
nothing about touch targets. Enable the AA-relevant set deliberately:

    axe.run(document, { rules: {
      "target-size": { enabled: true },
      "duplicate-id-active": { enabled: true },
      "identical-links-same-purpose": { enabled: true },
      "aria-roledescription": { enabled: true },
    }})

Check the list for your version rather than trusting this one:

    axe._audit.rules.filter(r => r.enabled === false).map(r => r.id)

Run target-size on a real touch device (`devices["Pixel 7"]`), not just a
narrow viewport — `pointer-coarse:` variants only apply with a coarse
pointer, so a resized desktop browser measures the wrong element sizes.

## A positive control can fail because the CONTROL is wrong

WCAG 2.5.8 is satisfied by size **or** spacing: an undersized target with
no neighbour within 24px legitimately passes. So injecting ONE tiny button
to prove `target-size` works produces a pass — which looks exactly like a
rule that never ran.

Measured: a lone 10x10 button -> `passes`, 0 violations. Two 10x10 buttons
2px apart -> `violations`, 2 nodes. Only the second is a valid control.

Generally: when a control does not trip, suspect the control before
concluding the detector is broken — and confirm by asking WHICH bucket the
rule landed in. `passes` means it ran and was satisfied; `inapplicable` or
absent from every bucket means it never evaluated anything, and only then is
your sweep worthless.
