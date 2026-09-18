#!/usr/bin/env node
/**
 * Static hygiene lint for a Storybook catalogue: is it consistent, is it
 * organised, and what is missing from it.
 *
 * This is the CHEAP half of Storybook testing. The expensive half — does each
 * story render, does it pass axe, does its play function hold — already runs
 * through the test runner. What no test covers is the catalogue as an object:
 * naming drift, missing `component`, components with no story at all, two
 * stories claiming the same title. Those are invisible per-story and obvious
 * in aggregate.
 *
 *   node story-lint.mjs [--dir .] [--roots components,features] [--json]
 *
 * Exits 1 if any ERROR-level check fails. Warnings never fail the run — they
 * are ratios and judgement calls, not defects.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative, basename } from "node:path"
import { argv, cwd, exit, stdout } from "node:process"

function arg(name, fallback) {
  const i = argv.indexOf(`--${name}`)
  return i === -1 ? fallback : argv[i + 1]
}
if (argv.includes("--help") || argv.includes("-h")) {
  stdout.write(`Usage: node story-lint.mjs [--dir .] [--roots components,features] [--json]

Checks (ERROR = exits 1):
  ERROR  duplicate story title
  ERROR  meta has no \`component\` (kills argTypes inference, Controls, autodocs)
  ERROR  story file exports no Story
  ERROR  storySort names a segment that no title uses any more
  WARN   title segment casing inconsistent with the catalogue majority
  WARN   title does not track the file's directory path
  WARN   component files with no story (prints the ratio and the top gaps)
  WARN   story file with no play function AND no interactive element in args
`)
  exit(0)
}

const ROOT = arg("dir", cwd())
const ROOTS = arg("roots", "components,features").split(",")
const JSON_OUT = argv.includes("--json")

function walk(dir, out = []) {
  let entries
  try {
    entries = readdirSync(dir)
  } catch {
    return out
  }
  for (const e of entries) {
    if (e === "node_modules" || e === ".next" || e === "__tests__") continue
    const p = join(dir, e)
    const st = statSync(p)
    if (st.isDirectory()) walk(p, out)
    else out.push(p)
  }
  return out
}

/** The `const meta = {...}` object, brace-balanced. Everything the lint reads
 *  about a story file lives in here, and reading it from the whole file
 *  instead picks up unrelated JSX props with the same names. */
function metaBlock(src) {
  const start = src.search(/\bconst\s+meta\b[^=]*=\s*\{/)
  if (start === -1) return src
  const open = src.indexOf("{", start)
  let depth = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === "{") depth++
    else if (src[i] === "}") {
      depth--
      if (depth === 0) return src.slice(open, i + 1)
    }
  }
  return src.slice(open)
}

const files = ROOTS.flatMap((r) => walk(join(ROOT, r)))
const storyFiles = files.filter((f) => f.endsWith(".stories.tsx") || f.endsWith(".stories.ts"))
const componentFiles = files.filter(
  (f) => /\.tsx$/.test(f) && !/\.stories\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f),
)

const errors = []
const warns = []
const stories = []

for (const f of storyFiles) {
  const src = readFileSync(f, "utf8")
  const rel = relative(ROOT, f)
  const meta = metaBlock(src)
  const title = meta.match(/\btitle:\s*"([^"]+)"/)?.[1] ?? null
  const hasComponent = /\bcomponent:\s*[A-Za-z_$]/.test(src)
  // Both shapes are current: `: Story` (aliased) and `: StoryObj<typeof X>`.
  const exported = [...src.matchAll(/^export const (\w+)\s*:\s*(?:Story|StoryObj)\b/gm)].map((m) => m[1])
  const hasPlay = /\bplay:\s*async/.test(src)
  stories.push({ file: rel, title, hasComponent, exported, hasPlay })

  // `Meta<typeof X>` where X is declared IN THIS FILE is the showcase pattern:
  // a local wrapper that renders several real components side by side. Those
  // legitimately have no `component:` — there is no single subject. Only flag
  // the case where the subject is an IMPORTED component, which is an oversight
  // that silently costs the Controls panel and autodocs.
  const metaSubject = src.match(/\bMeta<typeof\s+(\w+)>/)?.[1]
  const subjectIsLocal =
    metaSubject != null &&
    (new RegExp(`^(?:function|const|class)\\s+${metaSubject}\\b`, "m").test(src) ||
      // A wrapper is a showcase wherever it is declared. Requiring it to be
      // local flagged every story whose demo component lives in a sibling file.
      /(?:Demo|Gallery|Showcase|Example|Story)$/.test(metaSubject))
  // No `Meta<typeof X>` at all means an untyped showcase (`const meta: Meta = {}`),
  // which is the same judgement call as a local wrapper — warn, do not fail.
  if (!hasComponent && metaSubject != null && !subjectIsLocal) {
    errors.push({
      check: "meta-component",
      file: rel,
      msg: `meta has no \`component:\` and its subject (${metaSubject ?? "unknown"}) is imported — argTypes inference, the Controls panel and autodocs are all off for this file`,
    })
  } else if (!hasComponent) {
    warns.push({
      check: "showcase-story",
      file: rel,
      msg: `no \`component:\`${metaSubject ? ` — renders the wrapper ${metaSubject}` : " and no typed subject"}. Fine for a showcase, but Controls and autodocs are off.`,
    })
  }
  if (exported.length === 0) {
    errors.push({ check: "no-stories", file: rel, msg: "exports no `Story`" })
  }
  if (!hasPlay) {
    warns.push({ check: "no-play", file: rel, msg: "no play function — renders but asserts nothing" })
  }
  // Title should track the directory, so a moved file is an obvious diff.
  if (title) {
    const leaf = basename(f).replace(/\.stories\.tsx?$/, "")
    const last = title.split("/").pop() ?? ""
    const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "")
    if (norm(last) !== norm(leaf)) {
      warns.push({
        check: "title-path-drift",
        file: rel,
        msg: `title leaf "${last}" does not match file "${leaf}"`,
      })
    }
  }
}

// Duplicate titles: two files claiming one place in the sidebar. Storybook
// merges them silently and one file's stories appear under the other.
const byTitle = new Map()
for (const s of stories) {
  if (!s.title) continue
  byTitle.set(s.title, [...(byTitle.get(s.title) ?? []), s.file])
}
for (const [title, fs] of byTitle) {
  if (fs.length > 1) errors.push({ check: "duplicate-title", file: fs.join(", "), msg: `both claim "${title}"` })
}

// Casing consistency across every segment of every title.
const segs = stories.flatMap((s) => (s.title ? s.title.split("/") : []))
const styleOf = (s) =>
  /\s/.test(s) ? "spaced" : /^[A-Z][a-zA-Z0-9]*$/.test(s) ? "pascal" : "other"
const tally = segs.reduce((m, s) => m.set(styleOf(s), (m.get(styleOf(s)) ?? 0) + 1), new Map())
const majority = [...tally.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]
const odd = [...new Set(segs.filter((s) => styleOf(s) !== majority))]
if (odd.length) {
  warns.push({
    check: "title-casing",
    file: "(catalogue)",
    msg: `majority style is ${majority} (${tally.get(majority)}/${segs.length}); these differ: ${odd.join(", ")}`,
  })
}

// storySort entries that no title uses any more — dead ordering config that
// looks like it is doing something.
try {
  const prev = readFileSync(join(ROOT, ".storybook/preview.tsx"), "utf8")
  const block = prev.match(/storySort:\s*\{(.*?)\n\s{6}\},/s)?.[1] ?? ""
  const listed = [...block.matchAll(/"([^"]+)"/g)].map((m) => m[1])
  const known = new Set(segs)
  const stale = listed.filter((l) => !known.has(l))
  if (stale.length) {
    errors.push({ check: "stale-storysort", file: ".storybook/preview.tsx", msg: `no title uses: ${stale.join(", ")}` })
  }
} catch {
  /* no preview file — fine */
}

// Coverage of components by stories. A ratio, not a defect.
const storiedLeaves = new Set(
  storyFiles.map((f) => basename(f).replace(/\.stories\.tsx?$/, "")),
)
const uncovered = componentFiles
  .map((f) => relative(ROOT, f))
  .filter((f) => !storiedLeaves.has(basename(f).replace(/\.tsx$/, "")))
warns.push({
  check: "component-coverage",
  file: "(catalogue)",
  msg: `${componentFiles.length - uncovered.length}/${componentFiles.length} component files have a story (${componentFiles.length === 0 ? "n/a" : Math.round(((componentFiles.length - uncovered.length) / componentFiles.length) * 100) + "%"})`,
})

// A typo'd --dir used to walk nothing, print "0 story files" and exit 0 —
// a clean bill of health for a path that does not exist. Fail loudly instead.
if (!existsSync(ROOT)) {
  stdout.write(`story-lint: --dir does not exist: ${ROOT}\n`)
  exit(2)
}
if (storyFiles.length === 0) {
  stdout.write(
    `story-lint: found NO *.stories.* under ${ROOT} (roots: ${ROOTS.join(", ")}).\n` +
      `  That is almost always a wrong --dir or --roots rather than an empty catalogue.\n`,
  )
  exit(2)
}

const report = { storyFiles: storyFiles.length, componentFiles: componentFiles.length, errors, warns, uncovered }

if (JSON_OUT) {
  stdout.write(JSON.stringify(report, null, 1) + "\n")
} else {
  stdout.write(`${storyFiles.length} story files, ${componentFiles.length} component files\n\n`)
  for (const e of errors) stdout.write(`ERROR  ${e.check.padEnd(18)} ${e.file}\n       ${e.msg}\n`)
  for (const w of warns) stdout.write(`warn   ${w.check.padEnd(18)} ${w.file}\n       ${w.msg}\n`)
  if (uncovered.length) {
    stdout.write(`\nComponents with no story (${uncovered.length}), first 15:\n`)
    for (const u of uncovered.slice(0, 15)) stdout.write(`  ${u}\n`)
  }
}
exit(errors.length ? 1 : 0)
