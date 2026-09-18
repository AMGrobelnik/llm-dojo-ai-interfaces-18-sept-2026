<!-- hook: classname-prop-merged-with-cn -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A component's className prop is merged with cn(), never concatenated

`cn` is `twMerge(clsx(...))` (`aii_frontend/lib/utils.ts`). Interpolating a
caller's `className` into a template literal leaves BOTH the base token and
the caller's token in the class attribute, and **Tailwind's emission order —
not the caller — then decides which wins.**

That is the part worth stating precisely, because it is invisible in the
source. Measured in the compiled stylesheet
(`.next/static/chunks/app_globals_css_*.css`):

    .p-4   first emitted at offset 155281
    .p-6   first emitted at offset 155445

`.p-4` comes first, so a component whose base carries `p-6` silently ignores
a caller passing `p-4` — the override is later in the attribute and loses
anyway. `twMerge` resolves it by dropping the conflicting base token, so the
caller wins regardless of emission order.

## Stock: zero

Commit `3c9fa98d7` converted the last three sites, so this sweeps the whole
tracked tree rather than added lines only. **35 files compose a `className`
prop through `cn()`, across 45 call sites, out of the 50 files that carry
such a prop**; the three were the remainder, and one of them —
`about-07-bento.tsx`'s `Tile`, base `p-6` — is the exact shape measured
above.

This line used to read "92 files already composed through `cn()`". That
number is real but measures a different set — files using `cn()` for
ANYTHING, which is 91 today — and most of those never receive a `className`
prop, so they could not violate this rule either way. Quoted here it read as
"92 files already do what this rule asks", overstating demonstrated adoption
by about 2.6x. The narrower figure is the one that supports the argument
actually being made: the convention has already won on the population that
can express it, 35 of 50.

Worth being honest about severity: today's `Tile` callers pass only
`md:col-span-*`, which does not collide with anything in the base. So this
was a latent trap rather than a visible bug, and the rule is here to stop
the trap being sprung by the next caller, not to fix a broken screen.

## What the check does NOT flag, verified by running it

- **Template-literal class strings that do not involve the prop.** ~34 sites
  interpolate ternaries over tone/active classes, `${DENSE_ONLY}`,
  `${sans.variable}`. The pattern requires the identifier `className` inside
  the interpolation, which is what excludes them.
- **Untracked scratch**, since the population comes from `git ls-files`.

The `+`-concatenation form is covered too. It has zero occurrences today and
is included so it cannot become the escape hatch once the template-literal
form is closed.

Driven both ways: clean on the tracked tree, and restoring one concatenation
reports it by file and line.

Fix when blocked: `className={cn("...base...", className)}`.

Delete-check: **not deletable, and no cheaper mechanism exists.** oxlint has
no Tailwind plugin (checked, 1.62.0), and `eslint-plugin-tailwindcss`'s
`no-contradicting-classname` would not see across a component boundary in
any case. A lint rule would be preferable to an engine rule if one existed;
it does not.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **the rule holds and stock
is zero; one figure in the prose needs narrowing.**

`check.py` exits 0. Both violating forms measure zero independently: no
`className` interpolated into a template literal, and no `+` concatenation.

**"92 files already composed through `cn()`" does not measure this rule's
population.** Measured today:

| population | count |
|---|---|
| files using `cn()` at all | 91 |
| same, excluding tests/stories | 89 |
| files mentioning a `className` prop | 50 |
| files passing `className` INTO `cn()` | 35 |
| such call sites | 45 |

So 92 is the count of files that use `cn()` for anything — near enough to
today's 91 that it was almost certainly right when written, and the drift
is just the tree moving. The problem is not the arithmetic, it is that the
sentence reads as "92 files already do the thing this rule asks", when the
set that could even violate it is 50 and the set demonstrably composing a
`className` prop through `cn()` is **35**.

That overstates the demonstrated adoption by about 2.6x, and it matters for
exactly the reason the rule is worth having: the argument for shipping at
zero stock is "the convention has already won", and 35 of 50 supports that
claim honestly while 92 supports a claim nobody made. Recommend the body say
35 files / 45 sites, out of 50 that carry the prop.

Nothing about the mechanism changes — the check already scopes itself
correctly, which is why it reports zero rather than 57 false positives.
