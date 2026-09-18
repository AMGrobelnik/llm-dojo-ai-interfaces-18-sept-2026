<!-- hook: color-tokens -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Colors come from the registered palette tokens; no arbitrary [#hex] Tailwind color utilities in frontend source

app/globals.css registers a full token palette (--color-
background/-foreground/-primary/-muted/-destructive/… lines 8-27) yet 523
arbitrary hex color utilities live in app/components/features .tsx. The top
literals are one value re-typed at scale: text-[#1a1a2e] x104, bg-[#fafaf9]
x41, text-[#6e6e87] x31, text-[#3a3a4a] x24, bg-[#0d9488] x21 — unregistered
de-facto tokens that can fork one shade at a time with nothing saying no. This
is precisely the situation aii/frontend/rule-font-tokens fixed for fonts ("the
rule is not about the families, it is about the absence of anything that says
no"); color is the same dimension left open.

Filed as a member of meta-rule `rule-one-sanctioned-form`
(general/meta-rules; its `one-sanctioned-form.tsv` carries this rule's
statement verbatim) — the same meta-rule that holds the enforced
`rule-font-tokens` precedent cited above, so both sit under one owner
decision surface.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: frontend-components)

Proposed command (implemented at approval):

    rules-grep '(text|bg|border|ring|shadow|fill|stroke|divide|outline|from|via|to|accent|caret)-\[#[0-9a-fA-F]{3,8}\]' -- 'aii_frontend/app/**' 'aii_frontend/components/**' 'aii_frontend/features/**' ':!**/*.stories.tsx' ':!**/__tests__/**'

Delete-check: Yes — register the ~15 recurring hexes as named tokens in globals.css and sed
the utilities to token classes (mechanical: the top 15 literals cover the bulk
of the 523); the rule then enforces the collapsed end-state. Enforcement must
land AFTER that migration, or 523 pre-existing hits block every commit.

OWNER-GATED: green requires the palette migration first — 54 distinct hex shades are in use and none appears in the oklch palette in globals.css, so each needs an owner decision (map to an existing token or register a new one) before the 522 call sites can be mechanically rewritten; gating before that is red on 522 sites.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: 523 arbitrary hex utilities where ~15 recurring values are one palette
re-typed at scale; the sibling font-tokens rule is the established precedent.
Register tokens, sed the utilities, enforce.
- KEEP: 523 arbitrary hex utilities with one value re-typed 104 times; exact
sibling of the already-enforced font-tokens rule. Adoption is a mechanical sed
of ~15 recurring hexes; post-migration grep is cheap. Carve out chart/dataviz
palettes explicitly to control FPs.
- KEEP: Grep for Tailwind arbitrary-hex utilities (-[#) in FE source —
deterministic, zero-FP pattern. Big one-time migration (523 sites) is adoption
cost, not check cost; check itself is sound and loud.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **holds**. The most
accurate census checked in this pass.

| claim | measured today |
|---|---|
| 523 arbitrary hex utilities | **522** |
| `text-[#1a1a2e]` x104 | x104 |
| `bg-[#fafaf9]` x41 | x41 |
| `text-[#6e6e87]` x31 | x31 |
| `text-[#3a3a4a]` x24 | x24 |
| tokens at `globals.css` 8-27 | 20 `--color-*` there |

Measured over `app`, `components`, `features` with the utility prefixes
that can carry a colour (`text`/`bg`/`border`/`ring`/`fill`/`stroke`/
`from`/`to`/`via`/`shadow`/`decoration`/`outline`/`accent`/`caret`/
`divide`/`placeholder`). 522 against 523 is within a commit's drift, and
four of the five named literals reproduce exactly.

**One entry does not.** The census lists `bg-[#0d9488]` x21 as fifth;
today two others sit above it — `text-[#666676]` x22 and
`text-[#4a4a5a]` x22 — so it is seventh at best. That does not weaken the
argument; if anything it strengthens it, since the point is that
unregistered shades multiply, and two more have climbed the table since
the proposal was written.

**What this means for adoption is the 522, not the rule.** The check
itself is trivial and near-zero false-positive; the cost is a migration
across 522 call sites, which is why the proposal calls it "adoption cost,
not check cost". That framing is right, and the number is real, so the
decision is whether to accept a large mechanical diff — not whether the
invariant is worth having.

### The migration is not mechanical — 54 decisions, not 522 edits

Applied the "try to use the rule" test: attempt the fix it prescribes and
see whether it resists. It resists.

| | |
|---|---|
| palette defined in | **oklch** |
| distinct hex values in use | **54** |
| of those present in `globals.css` | **0** |

`app/globals.css:94` defines the palette as `--background: oklch(1 0 0)`,
`--primary: oklch(0.62 0.19 259.76)` and so on. Not one of the 54 hex
literals appears anywhere in that file. So `text-[#1a1a2e]` cannot be
rewritten to a token by lookup: somebody has to decide which oklch token
that shade was MEANT to be — a colour-space conversion plus a judgement
about intent — or register a new token for it.

**That reframes the cost, and in a useful direction.** The body says the
523 sites are "adoption cost, not check cost", which is right but reads
as a large mechanical diff. It is not: it is **54 design decisions**,
after which the 522 rewrites really are mechanical. Fewer decisions than
sites, but each needs a person.

Nothing here weakens the invariant — an unregistered shade that can fork
one value at a time is exactly the problem, and 54 unregistered shades
against ~20 registered tokens is the measurement that makes the case.
What changes is the shape of the work: this is a palette-design task with
a codemod attached, not a codemod.

## Migrated 2026-09-03

The owner-gated palette decision is made and the call sites are rewritten,
so the command above is now in the frontmatter and runs `--tree`.

| measurement | before | after |
|---|---|---|
| rule-pattern occurrences | 483 | 11 |
| distinct hex values | 54 | 2 |
| files carrying one | 118 | 1 |

The residue is a single file, `features/run-views/topbar/share-button.tsx`,
which carried an unrelated uncommitted edit from another agent while this
migration ran and was therefore left alone. Its 11 occurrences use four
values already mapped below (`#1a1a2e`, `#67677d`, `#4a4a5e`, `#3b82f6`,
`#2563eb`), so finishing it is the same substitution, not a new decision.

### The palette was not retuned — every token carries its exact value

Seven of the 54 literals needed no new token because they round-trip
bit-for-bit onto tokens Tailwind already registers. That had to be
computed rather than assumed: v4's default palette is oklch and most of it
does NOT land on the v3 hexes people remember — `teal-600` is `#009689`,
not `#0d9488`, and `violet-600` is `#7f22fe`, not `#7c3aed`. Reaching for
the familiar-looking built-in would have shifted those surfaces.

| hex | existing token | n |
|---|---|---|
| #fafaf9 | stone-50 | 29 |
| #fafafa | neutral-50 | 2 |
| #f5f5f5 | neutral-100 | 2 |
| #f4f4f5 | zinc-100 | 2 |
| #e5e7eb | gray-200 | 1 |
| #e5e5e5 | neutral-200 | 1 |
| #ffffff | white | 1 |

The other 47 are registered in `app/globals.css` with the EXACT hex the
call site rendered. Shade numbers track Oklch lightness in Tailwind's
orientation (higher is darker), so the ramp reads in the usual direction.

Cool neutrals — the dominant text/surface ramp:

| hex | token | n |
|---|---|---|
| #07070d | ink-975 | 3 |
| #0b0b14 | ink-950 | 1 |
| #1a1a2e | ink-900 | 112 |
| #1a1d26 | ink-880 | 5 |
| #2a2a3e | ink-850 | 1 |
| #3a3a4a | ink-800 | 24 |
| #3a3a4e | ink-780 | 1 |
| #3d3d56 | ink-760 | 9 |
| #4a4a5a | ink-700 | 21 |
| #4a4a5e | ink-680 | 12 |
| #5a5a6a | ink-600 | 10 |
| #666676 | ink-560 | 21 |
| #66667a | ink-550 | 12 |
| #616979 | ink-540 | 9 |
| #67677d | ink-530 | 11 |
| #666685 | ink-520 | 15 |
| #6a6a7a | ink-510 | 1 |
| #6c6c85 | ink-500 | 1 |
| #6e6e87 | ink-490 | 27 |
| #6b7280 | ink-480 | 1 |
| #7a7a88 | ink-450 | 1 |
| #8a8a99 | ink-400 | 3 |
| #9a9aa8 | ink-350 | 1 |
| #b0b0be | ink-300 | 2 |
| #c0c0cc | ink-250 | 3 |
| #e8e8ec | ink-150 | 2 |
| #f8f9fb | ink-75 | 20 |
| #fafbfc | ink-50 | 3 |

Achromatic neutrals, warm neutrals, and the four hues:

| hex | token | n |
|---|---|---|
| #1a1a1a | graphite-900 | 4 |
| #2a2a2a | graphite-800 | 1 |
| #4a4a4a | graphite-600 | 1 |
| #706756 | sand-600 | 9 |
| #7c705a | sand-500 | 1 |
| #b0a0a0 | sand-400 | 1 |
| #c0b8a8 | sand-300 | 3 |
| #f8f5ee | sand-100 | 1 |
| #fbfaf8 | sand-50 | 1 |
| #134e4a | brand-900 | 1 |
| #0d9488 | brand-600 | 39 |
| #f0f7f6 | brand-50 | 2 |
| #2563eb | azure-600 | 2 |
| #3b82f6 | azure-500 | 17 |
| #7c3aed | iris-600 | 16 |
| #6366f1 | iris-550 | 1 |
| #8b5cf6 | iris-500 | 10 |
| #c4b5fd | iris-300 | 1 |
| #5b8a5b | moss-500 | 2 |

Near-neighbours were deliberately NOT collapsed. `ink-490` through
`ink-560` are seven mid greys within 0.035 Oklch lightness of each other —
visible drift from one shade being re-typed by hand. Merging them is a
redesign, not a migration, and the point of naming them is that the choice
is now visible in one file instead of spread over 118. The 54-to-fewer
consolidation is the follow-up this migration makes possible; it is not
this change.

### How "no pixel moved" was established

Two independent checks, because the first one lies about the built-ins.

1. Every changed source line is a pure rename. Per file, added lines equal
   removed lines and every removed line carries a `-[#hex]` utility — 407
   lines across 117 files, no other edit rode along.
2. Both spellings were compiled and rendered. A probe stylesheet built
   `globals.css` with the old arbitrary utilities safelisted alongside the
   new token ones, and Chromium painted all 54 pairs at full opacity and
   at `/40`: the rendered 8-bit sRGB value is identical for all 108.

The second check is what the first cannot see. `getComputedStyle` reports
48 of the 54 pairs as byte-identical strings and the six Tailwind built-ins
as DIFFERENT — `rgb(229, 229, 229)` against `oklch(0.922 0 0)` — because
Chromium leaves an oklch colour unresolved in the computed value. Reading
that as a defect would have been wrong: those six agree to within 0.0004
Oklch lightness and quantize to the same byte. Comparing computed strings
is a serialization test; comparing painted pixels is the rendering test,
and only the second answers the question.

Opacity modifiers survive the rename in both spellings. Tailwind emits
`color-mix(in oklab, var(--color-ink-900) 40%, transparent)` for
`bg-ink-900/40` and the same mix for `bg-[#1a1a2e]/40`, so the 16
`/[0.06]`-style arbitrary modifiers and the 13 `/40`-style ones needed no
special handling.

### One more prefix than the rule catches

`border-r-[#0d9488]` is a colour literal the rule's ERE does not match —
the pattern requires `border-[`, and side-scoped variants (`border-r-`,
`border-t-`, …) slip past it. It was migrated anyway, so the tree is clean
of every `-[#hex]` utility and not merely of the ones the grep names. Worth
knowing before trusting the count: the rule measured 483 occurrences where
the tree actually held 484.

### AST port (2026-09-14)

Mechanism: `rules-grep` in whole-tree form — `research-monorepo/lefthook.yml`
carries `amg-hooks-grep --tree` with no lane split, so the enforced stock is zero
and every occurrence blocks, committed or freshly added alike. `dispatch.py`
is the port that replaces it at the dispatcher cutover: the same ERE as a
cheap per-line PREFILTER, plus a structural confirmation from
`lib/amg_hooks/tsast`. Findings stay a subset of the grep's candidates.

The banned text is a Tailwind utility CLASS NAME, which exists only as a
STRING — a JSX `className` attribute, a `cva()` variant literal, a plain
constant — never as a call argument, so this is the first hook to read
`tsast.FileFacts.strings` rather than `calls`. `tsast.ts` grew a `strings`
field (every `StringLiteral`/`NoSubstitutionTemplateLiteral`/
`TemplateExpression` span in a file, line-granular) for exactly this: a
candidate line survives iff it falls inside a recorded span, and one
outside every span is provably prose — a `//` or `/* */` comment naming the
class — since a comment can never be part of any of those three node
kinds. No specimen of that class exists in the live tree today; the drop is
exercised by the bites suite's synthetic fixture.

One divergence, forced and measured, unlike
`browser-tests-wait-on-conditions`'s single inert `:!.claude/` (simply
dropped). This rule's two excludes — `:!*.stories.tsx` and
`:!*/__tests__/*` — are NOT inert: 16 real `-[#hex]` utilities live in
`.stories.tsx` files under the positive roots today (e.g.
`aii_frontend/components/ui/hover-tip.stories.tsx:115`), so dropping them
would leak all 16 in as findings the live gate never reports. They are
carried instead, RE-ROOTED under `aii_frontend/` — the same fix
`fe-time-format-single-source` already carries for its own `__tests__`
exclude — because the live, root-anchored spelling makes `git ls-files`
(what the port's population read calls) return NOTHING when combined with
positives rooted deeper than the repo root: 372 files with the re-rooted
excludes, 0 with the live spelling carried verbatim. `git grep` does not
share that bug, which is why the live carrier never noticed it. Re-rooting
is not a narrowing — every path either exclude can select already starts
with `aii_frontend/` — and the bites suite measures the re-rooted
population against the positives-only population minus every
`.stories.tsx` path and every `__tests__/` path, rather than trusting the
live spelling to evaluate at all.

Measured against the consumer index 2026-09-14, whole-tree: 372 files in
the re-rooted population (365 `.ts`/`.tsx`), 0 candidates, 0 findings, 0
dropped, 0 added — the palette migration above left the tree clean, and the
true live grep (the root-anchored spelling, which `git grep` evaluates
correctly) agrees: 0 hits over the same pathspec.

PORTED 2026-09-14 onto the one-pass AST dispatcher: the standalone
`amg-hooks-grep` line is removed from `research-monorepo/lefthook.yml`, and
`research-monorepo-ast-checks` (the shared dispatcher command) now discovers and
runs this hook's `dispatch.py` in the same pass as every other TypeScript
AST-confirmed hook. `SCOPE` is `"tree"`, matching the retired `--tree`:
there is one lane, and a committed violation blocks a later unrelated
commit the same as any other tree-mode hook.
