# Storybook: consistency, organisation, and what it can test for free

A Storybook catalogue is the cheapest whole-app test surface a repo has —
every story is a mounted component with a known state, already isolated,
already in a browser. Most repos use ~10% of that.

Three layers, cheapest first:

| Layer | Cost |
|---|---|
| **Catalogue lint** (static) | seconds, no browser |
| **Runtime gates** | already in the test run |
| **Visual regression** | a service or a baseline dir |

What each layer checks:

- **Catalogue lint** — naming drift, missing `component`, duplicate titles,
  dead sort config, coverage ratio.
- **Runtime gates** — already installed, usually off: every story renders,
  passes axe, has no console errors.
- **Visual regression** — every story's pixels, per commit.

---

## 1. Catalogue lint

`.claude/skills/amg-frontend-testing/scripts/story-lint.mjs`. Static, no browser, exits 1 on ERROR.

```bash
node scripts/story-lint.mjs [--dir .] [--roots components,features] [--json]
```

| Check | Level |
|---|---|
| duplicate story title | ERROR |
| `meta` has no `component:` and its subject is a component | ERROR |
| story file exports no story | ERROR |
| `storySort` names a segment no title uses | ERROR |
| title segment casing vs the catalogue majority | warn |
| title leaf ≠ file name | warn |
| showcase story (wrapper, no `component:`) | warn |
| component files with no story | warn |
| story with no `play` | warn |

Why each matters:

- **duplicate story title** — Storybook merges them silently; one file's
  stories appear under the other and you never notice.
- **`meta` with no `component:`** (on a real component) — kills argTypes
  inference, the Controls panel and autodocs for that file.
- **story file exports no story** — dead file.
- **`storySort` names a segment no title uses** — dead ordering config that
  looks like it is working.
- **title segment casing vs the catalogue majority** — `Models View` next to
  184 PascalCase siblings is drift, not a decision.
- **title leaf ≠ file name** — a renamed component whose story kept the old
  sidebar entry.
- **showcase story** (wrapper, no `component:`) — legitimate, but Controls
  and autodocs are off — know that you chose it.
- **component files with no story** — the ratio, plus the biggest gaps.
- **story with no `play`** — renders but asserts nothing.

Two traps the lint itself had to be fixed for, and which any home-grown
version will hit:

- **Read `title:` out of the `meta` object, not the file.** A file-wide regex
  matches the first `title=` JSX prop instead, which then reports a phantom
  stale-sort entry for a story that is perfectly fine.
- **A wrapper is a showcase wherever it is declared.** Requiring it to be
  declared locally flags every story whose demo component lives in a sibling
  file.

Measured on one mid-size React app: 0 errors, 42 stories with no `play`,
19 title/file mismatches, 17 showcase stories, 1 casing family (the numbered
`N Name` Trace titles, deliberate — they force sidebar order), and **49 of 172
component files have a story (28%)**.

## 2. Runtime gates that are already installed

Check what the repo already pays for before adding anything. What one app
measured turned out to have, all of it installed and none of it enforcing:

**axe runs on every story and fails nothing.** `.storybook/preview.tsx`:

```ts
a11y: { test: "todo" }    // "off" | "todo" | "error"
```

`"todo"` means: run axe, report violations as warnings, fail nothing — so the
scan runs on every story and gates nothing. Measured on that app: flipping to
`"error"` fails **10 of 153 story tests across 3 files**, all `color-contrast`
— e.g. `#8f9499` on `#eff6ff` at 10px is **2.81:1** against a 4.5:1 threshold.

The migration path is per-story, not global: leave the default at `"todo"`,
set `parameters: { a11y: { test: "error" } }` on the stories that already pass,
and flip the global default once the backlog is clear. Flipping globally on day
one just means someone sets it back.

**Storybook stories run under vitest**, so a story's `play` function is a real
test in CI. That makes `play` the cheapest interaction test available — no
server, no auth, no mocks.

**Chromatic may be installed and unwired.** Check for a project token, a
config file, and a CI job before concluding it is in use — `@chromatic-com/storybook`
in `devDependencies` and listed in `.storybook/main.ts` addons proves neither.

## 3. Coverage, and the trap that breaks it

`@vitest/coverage-v8` gives per-branch coverage of what the stories actually
exercise, which is the input for coverage-guided exploration: find the branches
no story has ever entered, then write the story that enters them.

**But `browser.isolate: false` breaks it.** Measured: a `test:coverage` script
that looks correct dies with

```
Error: ENOENT: no such file or directory, open 'coverage/.tmp/coverage-25.json'
```

`isolate: false` reuses one browser context across story files (a real
speed win — 16.7 s → 12.0 s measured), and v8 coverage expects a per-file dump.
Confirmed by re-running with `--browser.isolate=true`, which produces a clean
report. So:

```bash
# coverage of the story suite
bunx vitest run --project storybook --coverage.enabled=true --browser.isolate=true
# coverage of pure-node unit tests (unaffected)
bunx vitest run --project unit --coverage.enabled=true
```

Measured baseline: **storybook project 25.7% statements / 22.5% branches**;
**unit project 29.1% / 28.3%**.

Do not "fix" the script by deleting `isolate: false` — that trades a permanent
30% slowdown on every run for a number you want occasionally. Pass the flag
when you want coverage.

## 4. What to add, in order

1. **Wire the lint into the pre-commit hook or CI.** Seconds, catches drift
   permanently.
2. **Per-story `a11y: { test: "error" }` on everything that passes today.**
   Free — the scan already runs.
3. **A `play` function on every story that has none.** Even
   `await expect(canvas.getByRole("button")).toBeVisible()` turns a render
   check into an assertion.
4. **Stories for the biggest uncovered components** — pick them off the lint's
   uncovered list, not by guessing.
5. **Visual regression**, last: it needs a maintained baseline, and the three
   above find more per hour spent.

## 5. Writing a story that is worth testing

- One story per **state**, not per prop permutation. Empty, one, many, loading,
  error, and the specific state a bug lived in.
- Name a story after the state it captures, and where it exists as a
  regression guard, after the guarantee — `RowOpensItsFullBody`,
  `MovingBetweenRowsLeavesOnePanel`, `PanelSurvivesThePointerMovingOntoIt`.
  A name like `Default2` documents nothing.
- Put the fixture at module scope and derive it once; a fixture rebuilt per
  render makes a live-updating component re-render forever.
- `findByRole` (singular) **throws on more than one match**, which is exactly
  what you want when the bug being guarded is "two of these appear".
- Radix portals render at `document.body`, outside `canvasElement`. Query them
  from `screen`, not `within(canvasElement)`.
- When a component closes on a delay, `waitFor` the assertion — the old
  element is legitimately still there for a moment.
- **Verify the guard**: break the fix, run the story, watch it fail, restore.
  A story that has never been red is decoration.
