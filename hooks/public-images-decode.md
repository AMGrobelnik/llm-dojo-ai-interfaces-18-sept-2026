<!-- hook: public-images-decode -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every raster asset under aii_frontend/public decodes cleanly with sharp

Documented incident, next.config.ts:62-69: every file in public/gallery
carried a byte-strip inside its APP11 (C2PA) segment, sharp threw on all 39,
the Next image optimizer silently fell back to serving untouched originals at
every width, and Chrome painted blank rectangles — one desktop gallery visit
downloaded 82.7 MB and showed not a single picture (0.71 MB after restore).
Nothing gates this today: a re-damaged or corrupt image commits green and
fails only in production, silently. Measured now: 61 rasters, 115 MB under
public/, so an all-mode sweep is a few seconds of sharp decode; commit mode is
condition-gated to staged public files.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: frontend-config)

Mechanism (implemented 2026-08-26, `scripts/decode-public-images.ts`):

    bun $RULE_DIR/scripts/decode-public-images.ts

Arrives green: 61 tracked rasters, 115 MB, all decoding, in **10 s** — so the
all-mode sweep costs what the body estimated. The proposal's `cd aii_frontend`
is gone; the script locates the frontend from the repo root itself.

**IT DECODES RATHER THAN READING HEADERS, and that is not a preference — it is
measured.** Damaging a tracked JPEG 4 KB past its midpoint, the shape the APP11
strip had, gives:

| call | on the damaged file |
|---|---|
| `metadata()` | **passes** — header intact, never reads the strip |
| `stats()` | throws `VipsJpeg: Corrupt JPEG data` |

`stats()` pulls every pixel through the decoder, which is exactly what the
optimizer does at request time, so a file passing here cannot fail there for a
reason this check could have seen.

**Resolving sharp is the trap.** A bare `import("sharp")` resolves upward from
the SCRIPT's directory, which lives under `.claude/skills/` and has no
`node_modules` — so it reports "not importable" on a perfectly well-installed
tree, which reads as cannot-run and checks nothing. The first version did
exactly that. It now resolves through `createRequire` against
`aii_frontend/package.json`.

A genuinely uninstalled checkout still reports cannot-run, which is the third
outcome and deliberately not a pass — CI's python group has no `node_modules`,
so the rule is listed in the pending-mechanism runner's permission list.

Enumeration is `git ls-files`, per `rule-guards-ask-git-what-is-tracked`.

Probed six ways: a mid-file corruption fires with the real sharp error; a
clean 25-raster tree, and the same corrupt file left UNTRACKED, do not; the
moment that file is tracked it does; and a tree truncated below the floor says
cannot-run rather than reporting a comfortable pass.

Superseded proposal (written without the `$RULE_DIR` prefix, which `ready.py`
would otherwise read as a script still owed):

    cd aii_frontend && bun scripts/decode-public-images.ts

Proposed condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only -- 'aii_frontend/public/' | grep -q .`

Delete-check: Cannot delete the dimension — the covers are product content and the optimizer
pipeline (sharp at runtime) is the fix for the 124 MB-of-full-size-PNGs
problem, so images must stay decodable by exactly that library. The check uses
the same sharp the optimizer uses, so it cannot disagree with production.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Documented incident: all 39 covers carried corrupt segments, the
optimizer fell back silently, and the gallery painted blank. sharp-decode over
public/ is the exact regression pin and nothing else checks asset bytes.
- KEEP: Documented incident: all 39 covers silently broken, blank gallery,
zero errors surfaced. A sharp decode pass condition-gated on public/ changes
is the only detection point for byte-level asset corruption.
- KEEP: Node script running sharp decode over public/** rasters — the exact
C2PA incident detector. Deterministic; scope to staged image changes for cost.
Fails loudly (sharp throws).
