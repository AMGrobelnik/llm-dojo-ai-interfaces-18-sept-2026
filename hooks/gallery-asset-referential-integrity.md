<!-- hook: gallery-asset-referential-integrity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every /gallery, /landing and /about asset path in frontend source resolves to a tracked file under public/, and every tracked file there is referenced or recorded as a deliberate exception.

In full: every "/gallery/…", "/landing/…", "/about/…" asset path in
frontend app/components/features/lib resolves to a tracked file under
aii_frontend/public/, and every tracked file in those dirs is referenced by
at least one source file (stories/tests excluded) — with deliberate
exceptions recorded in the checker, not silenced. Distinct from
rule-gallery-covers-immutable (in-place mutability) and
rule-public-images-decode (decodability): neither checks reference
resolution.

IMPLEMENTED (2026-08-26) and green: `scripts/check_assets.py` checks 57
references against 56 tracked assets in both directions.

The two dangling `/gallery/` references the original proposal (History,
below) reported as broken covers are DELIBERATE, and `_local-runs.ts` says
so three lines above each: the 404 trips `CoverImg`'s `onError` and shows
"Preview unavailable" — honest, where the damaged source file loaded
"successfully" and painted a blank rectangle. A third,
`__does_not_exist__.png`, is a Storybook fixture doing the same. Reported
as defects they would be "fixed" by adding the files — silently deleting
the only coverage that error path has. They are recorded in
`DELIBERATE_404` with the reason instead.

The reverse direction found two real orphans: `public/landing/details.png`
(127 KB) and `public/landing/gallery.png` (710 KB), unreferenced since
2026-05-10 while every sibling in that directory is used. Recorded in
`UNREFERENCED_ALLOWED`, not deleted: removing a committed asset is a
content decision, and deleting 837 KB would invalidate the whole 128 MB
`public/` image layer for one full re-push (layer-cost note under History)
— the right moment is the next commit that touches `public/` anyway.

Both lists are checked the OTHER way: a recorded 404 whose file appears,
and a recorded orphan that becomes referenced, are both reported. Verified
by probe — planting `public/landing/github.png` in the orphan list is
caught, because that one IS referenced.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: data-contracts)

Proposed command (implemented at approval):

    bash check_assets.sh  # SUPERSEDED — built as scripts/check_assets.py. comm -3 <(git ls-files 'aii_frontend/public/{gallery,landing,about}/**') <(grep -rhoE '"/(gallery|landing|about)/[^"]+"' app components features lib --exclude='*.stories.tsx' --exclude-dir='__tests__' | tr -d '"' | sed 's|^|aii_frontend/public|' | sort -u); both directions must be empty

Proposed condition: `git diff --cached --name-only -- 'aii_frontend/public/' 'aii_frontend/features/' 'aii_frontend/app/' 'aii_frontend/components/' 'aii_frontend/lib/' | grep -q .`

Delete-check: The seed-data dimension cannot be deleted — gallery and landing are shipped
product surfaces. The orphan half of the rule IS a deletion enforcement:
unreferenced assets must be removed from the tracked tree, which is exactly
the deleted end-state for the two dead landing shots.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Verified live: _local-runs.ts:75/:189 reference
/gallery/arch_dt_single.png and arch_ml_simple.png, neither tracked (37 files
vs 39 refs). Bidirectional, shipped-product surface, no claimed rule covers
asset-path resolution (rule-dashboard-copy-parity is copy text; it's enforced
and didn't catch this). Absorb public-assets-live's whole-public/ orphan scan
so one rule owns both directions.
- KEEP: Live defects in both directions (2 broken /gallery refs, orphaned
bytes), shipped product surface, cheap bidirectional set-compare; absorbs
public-assets-live so one rule owns asset liveness for public/.
- KEEP: Verified live: 37 tracked gallery files, refs to
arch_dt_single.png/arch_ml_simple.png resolve to nothing. Keep as the
surviving bidirectional rule but widen the orphan half to all of public/
(absorbing public-assets-live); basename matching for the reference direction
to survive constructed paths.

## History — the original measurement and its corrections

As originally proposed (since corrected):

Live defects both directions, measured now: features/gallery/_gallery-
inventions/_local-runs.ts:75 and :189 reference /gallery/arch_dt_single.png
and /gallery/arch_ml_simple.png — neither exists among the 37 tracked files in
aii_frontend/public/gallery/ (39 refs vs 37 files), so two seeded gallery
cards render broken covers today. Reverse: public/landing/details.png and
public/landing/gallery.png are tracked, ship in the public/ image layer
CLAUDE.md documents as a measured 128 MB push cost, and are referenced by zero
source files (verified against app/components/features/lib including page-
variants; no template-literal asset paths exist).
features/gallery/gallery.stories.tsx:37 deliberately uses
__does_not_exist__.png as a story probe, hence the stories/tests exclusion.
Distinct from rule-gallery-covers-immutable (in-place mutability) and rule-
public-images-decode (decodability): neither checks reference resolution.

OWNER-FACING CORRECTION (verified 2026-08-22, after the proposal was
written): the headline "two broken gallery cards" evidence is WRONG. Both
refs are DELIBERATE 404s, and `_local-runs.ts` says so in a comment
directly above each: the source covers were damaged (a strip inside the
APP11/PNG chunk stream) and those two runs have no published repo to
recover them from, so the missing file trips `CoverImg`'s `onError` and
renders "Preview unavailable" — honest, where the damaged file loaded
"successfully" and painted a blank rectangle. A rule shipped as proposed
would fail on intent, every run. If approved, the reference half needs an
exemption channel (an inline marker beside the deliberate ref, so the
exemption lives where the decision does).

The orphan half re-measured correctly (the original scan matched
`landing/<basename>`, which can never match `/landing/views/<basename>` —
a vacuous check of exactly the kind this repo's rules warn about): 67
tracked images, 60 referenced paths, 10 genuine orphans totalling 10.5 MB.
Five were `create-next-app` scaffold leftovers and are now deleted. The
remaining five are NOT safely mechanical: `bimi-logo.svg` is fetched by
mail clients via a DNS BIMI record and is referenced from no code by
design; `logo_4096.png` (8.6 MB) and `logo_mini.png` are plausibly master
assets; `landing/{gallery,details}.png` are unreferenced page shots. A
rule that deletes-on-sight would have taken the BIMI asset out.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **partly-wrong**, and the
wrong half would make the rule harmful to adopt.

**Forward direction: the facts hold, the interpretation does not.**
`_local-runs.ts:75` and `:189` do reference `/gallery/arch_dt_single.png`
and `/gallery/arch_ml_simple.png`, and neither exists among the 37 tracked
files. Confirmed. But "two seeded gallery cards render broken covers
today" mis-reads what that is. Four lines above each citation the source
says:

> The 404 is deliberate — it trips CoverImg's `onError` and shows
> "Preview unavailable", which is honest, where the damaged file loaded
> "successfully" and painted a blank rectangle.

So the missing file IS the chosen behaviour. The alternative was a
corrupt PNG that loads without error and paints blank — dishonest, and
harder to notice. `gallery.stories.tsx:25` records the same reasoning
("`onError` only ever covered the missing-file case"), and the
`arch_dt_full.png` / `arch_ml_full.png` counterparts exist, so the two
absent files are deliberate omissions rather than losses.

**Adopting this rule as written would flag both and push someone to
"fix" them by restoring the damaged images** — precisely the outcome the
comment exists to prevent. Any implementation needs an opt-out marker
that these two sites can carry, and the rule body should cite the
comment rather than count the sites.

**Reverse direction: stands, and is worth acting on.** `public/landing/
details.png` and `public/landing/gallery.png` are tracked and referenced
by zero source files outside `public/` — verified by `git grep -l`
excluding `public/` itself. They ship in the image layer CLAUDE.md
measures at 128 MB. Two dead assets is a small win, but it is a real one
and needs no design decision.

Method note for the next reader: the forward finding took thirty seconds
to confirm and would have been reported as a live user-facing bug. What
changed the verdict was reading the four lines ABOVE the cited line. A
citation that names a file and a line number invites checking the line;
the reason usually sits in the lines around it.

### The two dead landing images should NOT be deleted yet

Follow-up on the reverse finding, because the obvious action is the wrong
one and the reason is in CLAUDE.md.

Measured: `public/landing/details.png` is 127,291 bytes and
`public/landing/gallery.png` is 710,306 bytes — **818 KB** of assets with
**zero** references anywhere in the tracked tree, checked across all file
types and for dynamically constructed `/landing/` paths.

Deleting them is still the wrong move today. `Dockerfile.server:414`
gives `aii_frontend/public/` its own `COPY`, hoisted above the
per-package source copies, and CLAUDE.md records what that buys:

| layer | size | keyed on | touched |
|---|---|---|---|
| `public/` | 128.1 MB | its own files | 0 of 200 |

That "0 of 200" is the product of deliberate layer-ordering work — the
same note says `public/` "still re-pushed 128 MB on 100% of commits until
it was moved". **Removing 818 KB invalidates the whole 128.1 MB layer and
costs one full re-push**, roughly 160x the space it reclaims, and resets
a counter somebody worked to get to zero.

So: real dead weight, correctly identified, and the right time to remove
it is the next commit that invalidates that layer for another reason —
adding or changing any asset under `public/`. Worth carrying as a note
attached to this rule rather than as a standalone task, because whoever
next touches `public/` is exactly the person for whom it is free.

This also bounds what the rule should DO about reverse findings: report
them, do not demand immediate deletion. A rule that blocks a commit until
an unreferenced asset is removed would force the expensive push at the
worst possible moment.
