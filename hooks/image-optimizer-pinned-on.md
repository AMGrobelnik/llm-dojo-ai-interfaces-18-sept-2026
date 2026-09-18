<!-- hook: image-optimizer-pinned-on -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The Next image optimizer stays on and effective

The Next image optimizer stays on and effective: the images block in
aii_frontend/next.config.ts never regains `unoptimized`, keeps the avif/webp
formats and the trimmed deviceSizes/imageSizes ladders, and sharp stays pinned
in package.json overrides — so multi-MB gallery covers keep shipping as ~KB
optimized variants rather than full-size originals.

Filing (2026-08-28 audit): the statement names aii_frontend/next.config.ts,
and the engine defines general/ as portable to any repo — relocate under
rules-pending/aii/frontend/ before approval.

next.config.ts:49-79 documents the regression and its measured cost:
'unoptimized: true' was a leftover from the retired output:'export' build, and
public/ ships ~115 MiB of images (re-measured 2026-08-28: 62 tracked files, 60
of them `.png`-named, 114.3 MiB; the 37 gallery covers are 96.2 MiB, largest
`gallery/arch_276cb0.png` at 5.94 MB and 3584x4800 — and 28 of the 37 are
JPEG data by magic, so 'PNG' is a filename claim, not a format one). The
comment's own figures at :52-54 — 124MB / 106MB / 2.7MB and a 3168x1344 file
— are stale; no such file exists. With the flag on, one desktop gallery visit
downloaded 82.7MB; after the fix, 0.71MB. The whole regression is ONE config
line that nothing else
fails on, plus sharp (package.json:94, overrides-pinned ^0.35.0) which the
optimizer needs at runtime. deviceSizes was deliberately trimmed (:73-75: the
2048/3840 defaults 'only ever produced cache entries nothing requested') —
restoring Next's default ladder silently refills the image cache with unused
renditions. Complementary to (not overlapping) pending rule-public-images-
decode: that guards the INPUT files staying sharp-decodable (the C2PA byte-
strip incident at :62-69 where the optimizer silently fell back to full-size
originals); this guards the CONFIG and dependency staying present.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: performance-budgets)

Proposed command (implemented at approval):

    scripts/check_image_optimizer.sh   # superseded; prefix dropped so ready.py
                                       # does not read it as a script still owed — fail if grep finds 'unoptimized' in aii_frontend/next.config.ts; assert '"image/avif"' and '"image/webp"' present in its images block, deviceSizes max <= 1920, and '"sharp"' present in aii_frontend/package.json overrides


## IMPLEMENTED 2026-08-26 — `scripts/check_image_optimizer.py`

    .venv/bin/python $RULE_DIR/scripts/check_image_optimizer.py

Arrives green: optimizer on, avif+webp both emitted, neither oversize device
width present, sharp pinned and resolved. Seven checks, all from TRACKED files,
so it runs in CI rather than reporting cannot-run.

**The override alone does not prove sharp is there, so the lockfile is checked
too.** `sharp` is not a direct dependency — it arrives transitively and
`overrides` lifts it to ^0.35.0. An override binds nothing on its own: if the
package pulling sharp in ever stopped, the pin would go inert, sharp would
vanish, and the optimizer would lose the library it needs at runtime with the
config still looking correct. Measured: `overrides` asks ^0.35.0, a transitive
requester asks ^0.34.3, `bun.lock` resolves sharp@0.35.3.

**Comments are stripped before anything is matched, and the live config is why.**
`next.config.ts` says `unoptimized: true` twice in prose — once describing the
leftover and once as "To revert, put `unoptimized: true` back". A checker
reading the raw text sees the exact string it exists to forbid and fails on a
correct config. The `images:` block is also matched by BRACE DEPTH rather than
to the next `}`, since it contains nested arrays.

The ladder check pins the DECISION, not the list: it asserts 2048 and 3840 stay
out, because those "only ever produced cache entries nothing requested", rather
than freezing the whole array so a legitimate change reads as a defect.

Complementary to `rule-public-images-decode` and both are needed — the covers
incident required the flag removed AND the files repaired, and removing the flag
alone left a blank gallery.

Probed seven ways: `unoptimized: true`, a dropped avif format, a regained 3840
width, a removed `overrides.sharp` and a lock resolving no sharp all fire; the
real config and an explicit `unoptimized: false` do not.

Delete-check: The alternative delete — shrink the source PNGs and drop the optimizer — is
blocked by pending rule-gallery-covers-immutable (covers are published-run
artifacts, add-or-delete only, content-addressed by filename per
next.config.ts:77). The optimizer is therefore the only enforcement point, and
the flag's removal IS a completed deletion this rule pins in its end state.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Regression-shaped and measured (~115MB of PNGs, 5.9MB cover rendered
at 238x149 when unoptimized:true was live); pins a config block plus the sharp
override that nothing else guards. Complementary to pending rule-gallery-
covers-immutable and rule-public-images-decode — no dimension overlap.
- KEEP: Documented regression (~115MB of PNGs shipped raw via a leftover
unoptimized:true), trivially cheap config pin, and the alternative delete is
blocked by pending gallery-covers-immutable.
- KEEP: Measured regression (115MB of PNGs, 5.9MB cover into a 238px slot)
with a one-line failure mode (unoptimized: true creeping back); textual pin
over next.config.ts images block + package.json sharp override is trivial and
loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
CONFIG FACTS HOLD. Read /home/<user>/projects/
research-monorepo/aii_frontend/next.config.ts in full: the images block is :70-79 and
contains formats avif/webp, deviceSizes [360,420,640,828,1080,1200,1920],
imageSizes, minimumCacheTTL — and NO `unoptimized`. `grep -rn unoptimized
next.config.ts app components features lib` returns 4 hits, all comment prose
(next.config.ts:49, :60; pages-shared.tsx:64, :1

Corrected statement of fact:
Rule body should say: aii_frontend/next.config.ts's `images` block (:70-79)
never regains `unoptimized`, keeps formats [avif, webp] and the trimmed
deviceSizes/imageSizes ladders, and sharp stays pinned at package.json:94 in
`overrides` (^0.35.0; resolved 0.35.3 via next's own optionalDependency).
Measured cost of the flag: public/ ships 115 MB across 62 image files (60
.png-named, 114.3 MB), of which the 37 gallery covers are 96.2 MB (avg 2.60
MB, largest arch_276cb0.png at 5.94 MB, 3584x4800). Note 28 of those 37 `.png`
files are JPEG data by magic — sharp and browsers sniff content so this is
harmless, but the rule must not assert 'PNG'. Drop '67 files' and the
'3168x1344 -> 238x149' example (no such file). Live defects, comment-only:
next.config.ts:52-53 and :65 carry stale counts (124MB / 106MB / 2.7MB / 'all
39'), and features/landing-page/pages/pages-shared.tsx:169 still reads 'once
``images.unoptimized`` is lifted in ``next.config.ts``' — it was lifted. No
runtime defect: the flag is already off.
