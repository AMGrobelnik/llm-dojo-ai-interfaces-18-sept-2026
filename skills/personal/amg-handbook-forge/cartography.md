# Cartography — P0 recipes (map the field before you mine it)

**Effort gate (read first).** Building a handbook is a one-time, high-impact setup, so spend the maximum
worthwhile effort — never skimp to save compute. Scale *up* (more parallel miners, deeper recency sweeps,
extra verification) wherever it clearly helps; scale down only where a field genuinely lacks the material.
For a research-lifecycle consumer, build all of it: the "ceiling" maps (assumptions, important problems,
dead ends, taste → open questions) *and* the recency substrate.

## Charter card (5 fields, a few minutes)
- **Purpose** — one line.
- **Scope** — what's in, what's out.
- **Consumer persona** — the base LLM + its tools + its version window.
- **Scenarios** — see next section.
- **Constraints** — budget, and how fast the field's facts go stale.

## Motivating scenarios (3-7)
Concrete tasks the consuming LLM will actually face, **spanning the pipeline's real stages, not just one.**
For a research-lifecycle consumer that means: hypothesis generation; artifact generation
(research / experiment / dataset / evaluation / proof); paper text; review. **At least 2 posed at the
"ceiling"** — e.g. "which assumption should we challenge?", "which important problem, and why now?"
- Ground each scenario with 2-3 fetches from real practitioners.
- Every later comprehension-question, source, segment, and row must trace back to a scenario, or it's cut.
- These same scenarios are reused as the P1 baseline and the P6 A/B test.

## Bootstrap the field's structure, and classify each subarea
Fetch 3-5 overviews: the newest credible survey; the official-docs navigation tree; an "awesome-<X>" list
(for enumeration only, never as an endorsement); an encyclopedia / WikiProject page. Then:
- **Diff their taxonomies:** where they agree = your provisional skeleton; nodes only one source has, or axes
  that don't line up = controversy seeds; their open-problems sections = important-problem seeds.
- **Classify each subarea's type** from the same artifacts (no extra probes): empirical, normative, or craft.
  This type decides how you rank sources later (see Trust ladder).

## Borrow the settled canon from the newest survey
The newest credible survey hands you both a taxonomy and the field's settled canon:
- its emphasized references = the base-model exclusion set (Tier D) **and** the settled-canon lane (quote them,
  so the consumer neither reinvents nor re-proposes them);
- its open-problems / limitations sections = ceiling payload (Tier L);
- mature-field guard: do one textbook/syllabus check — the deepest canon is often too basic to be cited anywhere.

## Trust ladder (how much to believe a source)
**Look for the field's OWN ready-made ladder first:** search `Wikipedia:Reliable sources/Perennial sources`,
`WikiProject <domain> sources`, `<domain> levels of evidence`, library guides, standards bodies, registries.
If no such ladder exists, that itself tells you the field is craft-based.

The field's type decides which sources win:
- **normative** (specs / APIs) → the primary text wins; secondary sources are just finding aids.
- **empirical** → flip it: the best synthesis beats a lone primary result.
- **craft** → no ladder; instead gate on two tests — *recognized* (≥3 independent, unaffiliated sources assert
  it) AND *accepted* (search for dissent — `considered harmful`, `myth`, `vs` — and find none credible; if you
  do find credible dissent, it becomes a controversy row).

## Source-trust ledger (record once, reuse; from fetched evidence, never model opinion)
Do one "lateral read" per recurring source/author/venue (the how-to and search queries are in `credibility.md`).
When sources conflict, believe the independent ones.
- Record each source **once**: green / orange / red + why + what it's reliable *for*. Reuse that verdict for every quote.
- A source with no independent coverage can't be cited, but it can still be a mining *lead* (it earns its place by grounding).
- **Calibration:** before scaling up, resolve 3 sampled disagreements with the ladder; anything you can't adjudicate becomes a controversy row.

## Which source type to fetch for which claim (by claim type, not by field)
- Version facts → changelog > migration guide > issues > blogs.
- API semantics → spec > source code > maintainer answers > tutorials.
- Design judgment → the craft gate above.
- A correction always outranks the thing it corrects.
- Rule of thumb: **cite the authoritative source, mine the revealing one.**
- Misconceptions: one cheap search — `"concept inventory" <domain>` or `<domain> common mistakes`.

## When to stop mining a segment (P2 stop rules)
- Stop a segment when the last ~5 fetches added no new candidate rows, or ~5 in a row yielded nothing.
- Move that budget to the segments still producing.
- Once breadth is saturated, switch to depth (more quotes, contrast pairs, dissent).
- Before closing a *core* segment, run one probe with different vocabulary; if it surfaces mostly new material, extend.

## Comprehension questions (≤25)
One pass of ~15-20 informal questions per scenario family (top-down and bottom-up), then prune hard: each
question short, one concept, with a concrete, externally checkable expected answer.
- These questions **test** coverage — they never generate content.
- Pick key terms from both the questions AND their expected answers (the answers hide the non-obvious concepts).
- Used downstream at: the P1 baseline (what the tool-equipped agent still misses = your mining agenda), the P5
  per-segment check, and the P6 coverage report. The final list ships in SOURCES.md as the re-generation acceptance test.

## Recency map — the SUBSTRATE (rank-first value; build this BEFORE the lens maps)
The most reliable, checkable value is situational awareness the model's training cutoff denies it.
- **Sweep many recent works** (breadth over depth; weight the last ~6-12 months most; one compact insight per
  work, not a summary). Fan out over paper batches if the field is large.
- **Tier by recency, like expert memory:**
  - *Frontier* — high detail, the bulk: live results, shifts, tools, debates.
  - *Recent (~1-2 yr)* — compressed, still load-bearing.
  - *Durable core* — the few older foundations still in use; the older it is, the terser.
- **Extract organizing principles** — the mental models the field actually reasons with (from position/synthesis
  pieces, "how the field thinks"), not just bare results.
- **Tag what's now crowded** (don't-redo) and emit it as an explicit "go elsewhere, the blank space is not here"
  repeller section. (Tested: a negative don't-redo list escapes the substrate's pull; a positive "adjacent
  fields are relevant" note does not.) **Confirm each crowded lane — and hunt for lanes you HAVEN'T listed — with a dated, fetched saturation search
  (P3 re-verifies this right before ship). A static map is never complete, so the shipped section must also
  carry the reader-side backstop: map-silence = not-yet-checked, and the reader re-verifies its own pick (the
  template's standing directive).**
- **Theme-balance the frontier — the strongest escape lever (validated).** Recency-weighting alone amplifies
  whatever thread is hottest, so the consumer channels straight into it. Deliberately trim the dominant thread
  so ~5-6 threads carry roughly equal weight. (Balancing the content beat every wording tweak and the repeller
  alone: balanced substrate 40% channeling, vs repeller-only 60%, vs unbalanced 80%, vs prescriptive 100%.)
  Balance the content first, then add the repeller.
- **Select by centrality (breadth without bloat):** rank claims by how many independent sources assert them, or
  how load-bearing they are for the field's reasoning; only each section's most-recurring / load-bearing claims
  ship. Broad mining still pays — it feeds the tallies, the crowded-lane evidence, and the graveyard — but the
  long tail stays in the `.forge/` mining files, unshipped. **No depth annexes:** fine-grained depth measurably
  anchors ideation onto existing work (A/B numbers in `output-template.md`); execution-stage fine detail is
  live-tool territory (P1).
- Date every line and tag its [Sn] source; anything short-lived → `volatile.md`.

## Load-bearing assumptions (problematization — the lens's #1 payload)
Gap-spotting is competent but incremental; groundbreaking work challenges what the field takes for granted.
- Field-level assumptions only (practice/tool disputes belong in the Decision guide as "use X when…").
- Each row = the assumption **as the field states it** (quote the canon/survey that relies on it) + at least one
  independent, credible **challenge**, verbatim (a critique / position paper, a replication failure, a "we were
  wrong" / "rethinking X" / "against X" piece, or a methodological critique of the standard metric/benchmark) +
  what falls apart if it breaks.
- Don't require quoted *defenses* — the mass of reliant work is the implicit defense.
- A row is a *live* controversy only if there are ≥2 recent independent sources per side; if one side is thin,
  it's settled-with-dissent (known-lane).

## Important problems (importance-gated — not just any gap)
Include a problem only with BOTH quoted:
- **Why it's important** — what it unlocks, and for whom.
- **Why it's tractable now** — the tool/result/dataset that just opened it (Hamming's "why isn't this being worked on?" test).

Mine: surveys' future-work sections; `open problems in <domain>`; workshop calls-for-papers;
`<domain> "unexplained" OR "puzzling result" OR anomaly` (anomalies seed open questions). Check the newest work
per problem; still open → a gap row stamped `as_of`; a gap with no stated importance → cut.
- Quoted importance but no tractability quote: before cutting, spend one condition-keyed search — name the
  missing enabler in field-neutral terms and look for a dated satisfier at large (the why-now evidence may live
  outside the field). Found [Sn] → the row ships; nothing → cut as before.

## Graveyard (dead ends + how they'd reopen)
Search `"doesn't work" OR "negative result" OR "we tried"`, failed replications, `why we abandoned <X>`.
- The value: if the un-primed baseline agent proposes, endorses, or fails to flag something experts have killed,
  that's a real ideation delta (rank it in P3).
- Ship the verbatim dismissal + date + reason **+ the reopening condition** (the later result that would void the
  reason). One revival search per row (`<X> revisited`, `recent results`); a credible counter promotes it to an assumptions row.
- **Second search per row, keyed on the CONDITION, not the approach:** restate the reopening condition in
  field-neutral terms and search for a dated satisfier at large — the enabler often lands in another field
  first; `<X> revisited` fires only after this field has noticed. Satisfier [Sn] × dismissal [Sn] → a ripeness
  open question (state the match, never a mechanism).

## Field taste (what "deep" means here — worked contrasts, not the rigor floor)
Don't mine the generic floor (baselines, ablations, claims-match-evidence — the pipeline already ships that).
Mine what *deep* means in THIS field:
- award / best-paper / oral **rationales**; area-chair or meta-review commentary; top researchers' "what makes a
  great <domain> paper" essays; test-of-time retrospectives.
- Payload = worked contrasts: a celebrated-deep paper vs its competent-but-incremental sibling + the quoted cue
  that separates them, plus where this field draws the line between science and application.
- One quote per contrast (taste without a quote is just prior); evaluation canon → one execution row.

## Open questions (the last P0 step — the lens, emitted AS QUESTIONS, never prescriptions)
From the substrate + lens + taste, derive 3-6 broad open questions the consumer answers alone — never a
prescribed direction (tested: prescriptions overfit; facts + questions generalize).
- **Ripeness first (an expert's edge is timing):** cross the frontier substrate against the graveyard's reopening
  conditions — a frontier result that satisfies a dead-end's reopening condition (or makes an important problem
  newly tractable) is a *ripe* space, the highest-value kind; the satisfier may sit **outside the field's own
  literature** (the condition-keyed graveyard/problem searches feed this cross — an in-field-only sweep finds
  ripeness only after the field has, i.e. late).
- Other spaces: a shaky assumption; an unresolved anomaly (two frontier results that clash); a neighboring field
  whose relevance no one has remarked on; a blank on the map.
- State the tension/observation + [Sn] (+ the dated trigger where it's ripe) — **never** the solution, mechanism,
  or method (a prescribed idea causes tunnel vision and is redundant). No quoted parent → it's just model prior → cut.

## Segmentation (only if the field is big)
- **Default: don't segment.** If it fits one chapter or under ~8 knowledge clusters, keep it inline. If it seems
  to need >7 segments, the charter is too broad — re-scope.
- Segment axis = **what one scenario family loads together**, never a topic taxonomy.
- Confirm a boundary with: ≥2 artifacts converging on it, plus a "same term, different meaning across segments"
  check (different meanings confirm a real boundary; shared vocabulary argues for merging).
- Heavy cross-referencing between two candidate segments → keep them in one mining context.
- Triage each segment core / supporting / generic + its predicted value (core = high churn + controversy → mine
  heavily; supporting → sample; generic → skip).

## The map artifact (an llms.txt-style file, forge-internal)
- H1 = the domain; a blockquote for scope; one line per segment: `[source](https://example.com): what it is / when to consult it`.
- Use URLs from fetches you've already made (no separate liveness pass).

## Persistence (write as you go; don't synthesize at the end)
- Keep the map, trust ledger, controversy register, and per-concept source tallies as incremental files, one
  update per fetch — never synthesized at the end (≥3 independent sources → canonical; 1 → flag it).
- At P2 exit, scan the tallies for blind spots: one domain owning most of the top concepts; too few distinct
  origins per URL; everything recent in an old field. Each red flag buys one counter-query (`mining-annex.md`)
  plus a noted blind spot on the map.

---
All the numeric thresholds here and in `regen.md` are starting defaults — tune them from run-log evidence,
changing at most one per round so any regression stays traceable.
